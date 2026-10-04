"""Create the owner's private overlay, and make an instance theirs.

Two sources, one result. `--template` asks GitHub to generate a private repository from a public
template and clone it — the owner's own `<owner>/stayfixed-overlay-template` when they have
published one, and the publisher's otherwise; `--local` renders `templates/overlay/` here through
the scaffold engine, makes a git repository of it, and touches no network. A template and not a
fork: a fork's visibility is bound to the upstream network and cannot be made private, and an
overlay that is not private is the one outcome this whole area exists to prevent.

`init_instance` is what makes a generated repository *this owner's*: the plugin and marketplace
names carry their account, so two overlays installed into one harness never collide, and the
commit-time secret scan is installed. Neither step is destructive and both are idempotent —
`gh` may give up on the clone with the repository already created, so a second run is the
ordinary case rather than the exception.
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal

from stayfixed import fsops
from stayfixed.config.loader import preset_defaults
from stayfixed.errors import Failure, Refusal
from stayfixed.overlay.identity import require_overlay, segment
from stayfixed.overlay.layout import (
    CODEX_PLUGIN_MANIFEST,
    MARKETPLACE_MANIFEST,
    OVERLAY_FILES,
    PLUGIN_MANIFEST,
    SUCCESSORS,
)
from stayfixed.overlay.template import retired, templates
from stayfixed.printed import answered, quoted
from stayfixed.runner import NOT_FOUND, TIMED_OUT, Completed, Runner
from stayfixed.scaffold import Manifest, Verb, apply, digest, plan, unlinks

Source = Literal["template", "local"]
TEMPLATE_REPOSITORY = "stayfixed-overlay-template"
# Whose public copy of that repository `--template` falls back to when the owner has published none
# of their own. The publisher's account is a fact about where this project's template lives, and
# `publish-template` keeps reading `TEMPLATE_REPOSITORY` alone for its `--name` default: what an
# owner *publishes* is theirs to name, what they *generate from* has this one fallback.
TEMPLATE_PUBLISHER = "stayfixed"
# The fallback named with its host, and never host-relative: `gh` resolves an unqualified
# `OWNER/REPO` on `GH_HOST`, which the runner keeps, so on a GitHub Enterprise host the fallback
# would be whoever owns `stayfixed` there, and the owner's private overlay, whose hooks run in
# every session, would be generated from it. `gh repo create --template` and `gh repo view` look a
# `HOST/OWNER/REPO` name up on that host whatever `GH_HOST` says (measured against gh 2.101.0).
# The owner's own `<owner>/…` probe stays host-relative: that repository is on the owner's host.
TEMPLATE_PUBLISHER_HOST = "github.com"
PUBLISHED_TEMPLATE = f"{TEMPLATE_PUBLISHER_HOST}/{TEMPLATE_PUBLISHER}/{TEMPLATE_REPOSITORY}"
# The directory whose presence says a generated repository actually arrived — the exact probe the
# spike record (`docs/plans/2026-09-05-agent-harness-p0-spikes.md`) used in its *template creation
# race and renaming* trial, and the one thing a repository created from this template always
# carries. Deliberately weaker than `identity.overlay_fault`, and `identity`'s own docstring says
# why: this one answers "did a tree arrive here", which is the question idempotence asks of a clone
# `gh` gave up on half way through.
PROBE = ".claude-plugin"
# How long to wait before the one retry, when `gh` says the repository exists and the clone brought
# nothing down. The spike record's *template creation race and renaming* trial did not reproduce
# that race in its one attempt, so this is carried on the strength of reasoning rather than of a
# measurement: generation is asynchronous on GitHub's side and one clean run cannot rule out a slow
# one.
RETRY_WAIT_SECONDS = 10
# What `docs/cli.md` says about the template, and what a failure has to say too. `--template`
# generates from the owner's own copy when they have published one with `stayfixed overlay
# publish-template`, and from the publisher's public copy otherwise, so an account that never
# published one still has somewhere to generate from. A failure that does not say so sends the
# owner to `gh auth status` for a repository that was never there.
TEMPLATE_PRECONDITION = (
    f"`--template` generates from <owner>/{TEMPLATE_REPOSITORY} when the owner has published one "
    f"with `stayfixed overlay publish-template`, and from {PUBLISHED_TEMPLATE} otherwise; "
    f"`stayfixed overlay create --local` renders the same tree here with no network call"
)
# What `gh repo view` prints on stderr, whatever the name, when the repository does not exist or
# this token cannot see it (measured against gh 2.101.0, `stayfixed/definitely-missing-xyz`):
# `GraphQL: Could not resolve to a Repository with the name '<slug>'. (repository)`, exit 1. It is
# the only thing that tells "not found" from an expired token (`HTTP 401: Bad credentials`, also
# exit 1) and from a network failure, so it is matched as the whole phrase and never as the
# shorter "Could not resolve", which `Could not resolve host` shares. A named string, not a cap:
# it bounds nothing and no shipped file changes with it.
NOT_FOUND_ANSWER = "Could not resolve to a Repository"
# The three manifests `init_instance` names after the owner. The Codex one was left out of the
# first draft, so the collision the suffix exists to prevent still happened on Codex: two
# owners' overlays under one Codex configuration were one plugin fighting itself, which is the
# exact wording `init_instance`'s own docstring gives as the rationale.
MANIFESTS = (PLUGIN_MANIFEST, MARKETPLACE_MANIFEST, CODEX_PLUGIN_MANIFEST)
# What the template carries where an account goes, and what `init_instance` replaces with the
# owner's. A marketplace has to name an `owner` for `claude plugin validate` to accept it, and a
# plugin manifest an `author` for it to stop warning; neither can be the owner's before there is
# an owner, so the shipped file holds this neutral stand-in. `templates/overlay/` carries the same
# string, and `tests/overlay/test_create.py`'s
# `test_init_names_the_owner_and_the_author_the_harness_asks_for` renders the template and fails
# when the two drift apart.
PLACEHOLDER_ACCOUNT = "your-account"
# Which key of each manifest names the account: the marketplace's owner, the plugins' author.
ACCOUNT_KEYS = {
    PLUGIN_MANIFEST: "author",
    MARKETPLACE_MANIFEST: "owner",
    CODEX_PLUGIN_MANIFEST: "author",
}


@dataclass(frozen=True)
class Created:
    root: Path
    source: Source
    notes: tuple[str, ...]
    # The template repository a `--template` run generated from (`<account>/<name>`), so a caller
    # that reports the run can name it without parsing a note. `None` for `--local` and for a
    # directory that was already there and was left alone.
    template: str | None = None


@dataclass(frozen=True)
class Initialised:
    renamed: tuple[str, ...]
    notes: tuple[str, ...]
    # Every overlay file the run rewrote, removed or wrote, the renamed manifests included, so a
    # caller that reports on an overlay it found can say whether `init` changed it.
    changed: tuple[str, ...] = ()


def target_root(root: Path, owner: str, name: str) -> tuple[Path, str]:
    """Where `create(owner, name, root=root)` would put the overlay, and the folded owner.

    Nothing is created and nothing is asked of the network, which is the point: `setup
    --overlay create:<owner>/<name>` has to be able to refuse the *destination* — for lying
    inside the project root, say — before it runs `gh repo create` on somebody's account. The
    destination is knowable from the arguments alone, and it used to be computed only by the
    call that had already created the repository.

    Folded before it is validated, and `init_instance` folds the same way, because `SEGMENT` has
    a lowercase leading class and a mixed-case GitHub login is ordinary. Validating the raw
    value refused `--owner OctoCat` from this command while the other accepted it — one owner
    string with two answers, and the refusal said "is not one path segment" about a value that
    plainly is one. Folding is safe: GitHub logins are case-insensitive, and the folded value is
    what reaches the slug, the remote and the manifest suffix alike.
    """
    account = segment("owner", owner.strip().lower())
    segment("name", name)
    return root / name, account


def _populated(target: Path) -> bool:
    return (target / PROBE).is_dir()


def _render_locally(root: Path, name: str) -> Path:
    target = root / name
    # **Everything that can refuse runs before anything is created**, and the order is
    # load-bearing rather than tidy. `mkdirs_within` below creates `<name>/.claude-plugin`,
    # which is exactly `PROBE` — so a render that failed after it (`templates()` on a stayfixed
    # installed without the tree, a manifest that will not parse, a refused path) would leave
    # behind the one directory that makes a later `overlay create --template` answer "already
    # exists and was left alone" and never create the repository at all. The idempotence rule
    # would silently swallow the real command. A refusal has to cost nothing on disk.
    #
    # `plan` reads and decides and writes nothing, and it is happy with a root that does not
    # exist yet: `Manifest.read` finds no file and every artifact reads as absent.
    planned = plan(target, preset_defaults(name), templates())
    # The engine writes through `fsops` and walks every component with `O_NOFOLLOW`, but it
    # cannot open a root that is not there yet. `mkdirs_within` creates a target's *parents*, so
    # the instance directory is asked for as the parent of the first file that goes into it —
    # through the same walk, rather than with the `Path.mkdir(parents=True)` this project does
    # not allow into a module that puts files into a repository.
    fsops.mkdirs_within(root, f"{name}/{OVERLAY_FILES[0]}")
    apply(target, planned)
    return target


def create(
    owner: str,
    name: str,
    *,
    source: Source,
    root: Path,
    runner: Runner,
    wait: Callable[[float], None] = time.sleep,
) -> Created:
    """Create `root/<name>`, from the template repository or from the shipped tree."""
    # One spelling of "where this lands and what the owner is called", shared with the caller
    # that has to ask before it calls (`setup`'s `--overlay create:`); see `target_root`.
    _, account = target_root(root, owner, name)
    if not root.is_dir():
        # Both branches below start by opening this directory — the contained walk for the
        # local render, the subprocess `cwd` for the other — and a missing one is a mistyped
        # `--root`, which is a refusal a person can act on rather than an internal error.
        raise Refusal(f"{root} is not a directory; name one that exists with --root")
    if source == "local":
        target = _render_locally(root, name)
        # Here and not in `_render_locally`, which `publish-template` also renders through: its
        # scratch tree is cloned over and replaced, and a repository of its own there would be
        # pushed as a nested one. A repository is what this owner does next with the tree (commit
        # it, give it a private remote), so it is made now, on `main`, with no remote: the remote
        # is a repository that has to exist on GitHub first, and that is the owner's to create.
        return Created(target, source, _initialise_repository(target, account, name, runner))
    return _from_template(account, name, root=root, runner=runner, wait=wait)


def _initialise_repository(
    target: Path, account: str, name: str, runner: Runner
) -> tuple[str, str]:
    """The notes a `--local` run ends with: the repository it made, and how to give it a remote.

    A `git` that cannot run is a note and not a failure: the tree is on disk by now, so refusing
    would hide a directory that exists, and the note says the one command that finishes the job.

    A directory that is already a repository is left as it is: `git init` over one changes
    neither its branch nor its remotes, so a note saying it was made one on `main` with no remote
    would be false about a repository on another branch with an `origin`.
    """
    rendered = "rendered from the shipped template; no network call was made"
    git_dir = target / ".git"
    if git_dir.exists() or git_dir.is_symlink():
        return (
            rendered,
            "it was already a git repository, and its branch and remotes were left as they were",
        )
    # `git init` and then the branch, and not `git init -b main`: `-b` arrived in git 2.28, and an
    # older `git` refuses the option, so the one command that makes the repository failed there.
    # `symbolic-ref` names the unborn branch on every version.
    remote = (
        f"`git remote add origin git@github.com:{account}/{name}.git` and "
        f"`git push -u origin main` once you have created the private repository "
        f"{account}/{name} on GitHub"
    )
    step = "git init"
    done = runner.launch(["git", "init"], target)
    if done.code == 0:
        step = "git symbolic-ref HEAD refs/heads/main"
        done = runner.launch(["git", "symbolic-ref", "HEAD", "refs/heads/main"], target)
    if done.code != 0:
        return (
            rendered,
            f"`{step}` {_ended(done)} ({_detail(done)}), so this is not a git repository on main "
            f"yet: run `git init` and `git symbolic-ref HEAD refs/heads/main` in it, then {remote}",
        )
    return (rendered, f"made it a git repository on main with no remote; give it one with {remote}")


def _ended(done: Completed) -> str:
    """How a subprocess that did not succeed ended, in words true of each way: one that could
    not be launched did not run, one that hung did not finish, and one that ran has an exit
    code."""
    if done.code == NOT_FOUND:
        return "could not be run"
    if done.code == TIMED_OUT:
        return "did not finish"
    return f"exited {done.code}"


def _detail(done: Completed) -> str:
    """What a subprocess said about itself, in the order a reader wants it.

    `Completed` has carried `code` and `stderr` since this seam was written and this module threw
    both away: with `gh` absent from `PATH`, every call answered `Completed(127, "", "gh could
    not be run: …")` and the failure below still said "GitHub did not confirm the repository
    exists; check `gh auth status`" — a cause that was not the cause, about a binary that was
    not there. The same idiom `setup.run` uses for its notes.

    **Clipped, in `printed.answered`**, which every command quoting a subprocess goes through.
    What `gh`, `git` and `pre-commit` print is not text this project wrote: a proxy or a wrapper
    can put a line break and `::error::` in it, which a CI runner reads as a workflow command, or
    an escape sequence, which drives a terminal.
    """
    return answered(done)


def _template_for(owner: str, *, root: Path, runner: Runner) -> str:
    """The template repository to generate from: the owner's own when it is published, else the
    publisher's.

    One question, asked once: `gh repo view <owner>/<TEMPLATE_REPOSITORY> --json isTemplate`. A
    template there is used. A repository that is not one, and `gh`'s explicit not-found answer,
    both mean the owner has published nothing, and the publisher's public copy is used.

    **Anything else refuses, and never falls back.** `gh` exits 1 for a missing repository and
    for an expired token alike, so the exit code cannot be read as "not found"; only the phrase
    `NOT_FOUND_ANSWER` on stderr can. A launch failure, a timeout, an authentication or network
    failure and an answer that is not the JSON asked for are each a state in which this run does
    not know whether the owner has a template, and guessing "no" would silently generate the
    overlay of somebody who has one from somebody else's. What `gh` said is quoted through
    `_detail`, which clips it.
    """
    mine = f"{owner}/{TEMPLATE_REPOSITORY}"
    theirs = PUBLISHED_TEMPLATE
    probe = runner.launch(["gh", "repo", "view", mine, "--json", "isTemplate"], root)
    if probe.code == 0:
        answer = _is_template(probe.stdout)
        if answer is not None:
            return mine if answer else theirs
    elif probe.code not in (NOT_FOUND, TIMED_OUT) and NOT_FOUND_ANSWER in probe.stderr:
        return theirs
    # `gh` could not be launched, hung, was declined, or answered something this cannot read.
    # `gh repo create` is the irreversible act, and it has not run.
    launched = probe.code not in (NOT_FOUND, TIMED_OUT)
    if not launched:
        what = "could not be run"
    elif probe.code == 0:
        what = "answered something other than the `isTemplate` object it was asked for"
    else:
        what = f"exited {probe.code}"
    raise Failure(
        f"`gh repo view {mine} …` {what} ({_detail(probe)}), so it is not known whether "
        f"you have published a template, and nothing was created."
        + ("" if launched else " Install `gh` and authenticate it, or render the overlay locally.")
        + f" {TEMPLATE_PRECONDITION}"
    )


def _is_template(printed_json: str) -> bool | None:
    """`isTemplate` from what `gh repo view --json isTemplate` printed, or `None` for anything
    that is not exactly an object carrying a boolean there."""
    try:
        document = json.loads(printed_json)
    except json.JSONDecodeError:
        return None
    value = document.get("isTemplate") if isinstance(document, dict) else None
    return value if isinstance(value, bool) else None


def _from_template(
    owner: str, name: str, *, root: Path, runner: Runner, wait: Callable[[float], None]
) -> Created:
    target = root / name
    if _populated(target):
        # Creating the overlay is idempotent by rule: `gh` may give up on the clone with the
        # repository already created, so the second run finds a tree and must not re-create.
        return Created(target, "template", (f"{target} already exists and was left alone",))
    template = _template_for(owner, root=root, runner=runner)
    slug = f"{owner}/{name}"
    created = runner.launch(
        [
            "gh",
            "repo",
            "create",
            slug,
            "--private",
            "--template",
            template,
            "--clone",
        ],
        root,
    )
    if _populated(target):
        return Created(target, "template", (f"created {slug} from {template}",), template)
    if created.code in (NOT_FOUND, TIMED_OUT):
        # `gh` could not be launched at all, or hung until the seam gave up. Neither is a state two
        # further subprocesses and a ten-second wait can learn anything about: `gh repo view` would
        # ask the same absent binary a second question, get the same answer, and the failure would
        # then name GitHub for a fault that is this machine's. stayfixed does not install `gh`, so
        # its absence is the machine owner's to fix: a reported finding that names it, never a
        # traceback.
        raise Failure(
            f"`gh repo create {slug} …` could not be run ({_detail(created)}), so nothing was "
            f"created and nothing was cloned. Install `gh` and authenticate it, or render the "
            f"overlay locally: {TEMPLATE_PRECONDITION}"
        )
    if created.code != 0:
        # `gh` ran and declined. Its own stderr is the cause — a missing template repository, an
        # expired token, a name already taken — and it is quoted rather than replaced by a
        # guess. The clone is still retried below only when `gh` *succeeded* and nothing
        # arrived, which is the one shape the race can take.
        raise Failure(
            f"`gh repo create {slug} …` exited {created.code} ({_detail(created)}), so no tree "
            f"arrived at {target}. {TEMPLATE_PRECONDITION}"
        )

    # `gh` reported success and nothing arrived. Which of the two failures it was decides whether
    # waiting can help, so ask before retrying: `gh repo view` printing the name back is the
    # evidence the repository exists and the clone raced its generation.
    view = runner.launch(["gh", "repo", "view", slug, "--json", "name", "--jq", ".name"], root)
    raced = view.code == 0 and bool(view.stdout.strip())
    if raced:
        wait(RETRY_WAIT_SECONDS)
    # The clone is retried either way, and that is deliberate: `gh repo view` answering nothing
    # is not proof of absence — a rate limit or an expired token answers the same — and one fast
    # failure is cheaper than refusing to try.
    cloned = runner.launch(["git", "clone", "--", f"git@github.com:{slug}.git", name], root)
    if _populated(target):
        return Created(
            target,
            "template",
            (f"cloned {slug}, generated from {template}, on the second attempt",),
            template,
        )
    raise Failure(
        f"{slug} produced no tree at {target}: `gh repo create --clone` reported success and "
        f"left nothing, and the "
        + ("retried" if raced else "one further")
        + f" `git clone` exited {cloned.code} ({_detail(cloned)}). "
        + (
            "GitHub reports the repository exists, so generation may still be running — wait and "
            "clone it by hand"
            if raced
            else f"`gh repo view` did not confirm the repository exists ({_detail(view)}); "
            f"check `gh auth status`. {TEMPLATE_PRECONDITION}"
        )
    )


def _suffixed(value: object, suffix: str) -> str | None:
    """The renamed value, or `None` when it is already suffixed or not a name at all."""
    if not isinstance(value, str) or not value or value.endswith(f"-{suffix}"):
        return None
    return f"{value}-{suffix}"


NOT_AN_OVERLAY = (
    "`stayfixed overlay init --root` must name an overlay. It rewrites the tree's plugin "
    "manifests and installs a commit hook there, so pointed at anything else -- a project, or "
    "the stayfixed checkout itself -- it renames somebody else's manifests"
)


def init_instance(root: Path, owner: str, *, runner: Runner) -> Initialised:
    """Make a generated overlay this owner's: name it after them, and install the secret scan.

    The suffix is there so two overlays never collide — a harness installs a plugin by the name
    in its manifest, so two owners' overlays under one configuration directory would be one
    plugin fighting itself. **All three manifests**, because the project ships a Codex half of
    everything else and `.codex-plugin/plugin.json` left unsuffixed is that collision still
    happening, one harness over. Each is rewritten through `fsops.write_within`: the overlay
    root *is* a root, so the contained walk applies and there is no carve-out to take.

    **A rewrite of a file stayfixed wrote is re-stamped into the scaffold ledger.** `create
    --local` renders these files through the engine, which records each one's digest; a rewrite
    behind the ledger's back makes the file read as hand-edited for ever after, so `overlay
    upgrade` reported `skip_modified .claude-plugin/plugin.json (hand-edited)` and never
    refreshed it again — for the one file carrying `stayfixed.requires`, the
    version-compatibility declaration the README advertises, and attributing to the owner an
    edit stayfixed itself made. Re-stamping is the narrow answer of the two the review offered;
    rendering the suffix through the `Template` instead would put an owner-dependent value into
    the shipped tree, which every *other* consumer of that tree (`upgrade`'s hash rule, `overlay
    publish-template`) would then have to know about. **Only a file whose bytes before the
    rewrite were the recorded ones**: a manifest the owner edited is still renamed, but
    re-stamping it recorded their edit as stayfixed's, and the next `upgrade` refreshed it away.
    Its record stays, and `upgrade` goes on naming it. A `--template` clone carries no ledger at
    all, and gets no record written for it.

    A manifest that is *absent* is a note rather than a failure. An overlay generated before the
    Codex half shipped carries two of the three, and refusing to name the other two over it
    would make this command unusable on exactly the overlays that most need it; one that exists
    and cannot be read is still a failure, because that is a file saying something this command
    cannot act on.

    **Asked whether `root` is an overlay before anything is touched**, the way `upgrade` asks
    and `setup` asks twice. `--root` defaults to `.`, and run inside the stayfixed checkout this
    renamed all three of its plugin manifests and installed a hook into it.
    """
    require_overlay(root, because=NOT_AN_OVERLAY)
    suffix = segment("owner", owner.strip().lower())
    ledger = Manifest.read(root)
    ledgered = bool(ledger.records)
    # Every manifest is read and decided before any is written, so one that cannot be read stops
    # the run with nothing rewritten, rather than after the ones before it were rewritten and
    # before their records were re-stamped.
    rewrites: list[tuple[str, str, str]] = []
    absent: list[str] = []
    notes: list[str] = []
    for relative in MANIFESTS:
        if not (root / relative).is_file():
            absent.append(relative)
            continue
        before = _read_manifest(root, relative)
        body = _renamed(before, relative, suffix)
        if body is not None:
            rewrites.append((relative, before, body))
    restamped = False
    for relative, before, body in rewrites:
        fsops.write_within(root, relative, body)
        record = ledger.get(relative)
        # Only a file that held what stayfixed wrote there is vouched for again. One the owner
        # edited is still renamed, and its record is left as it was, so `upgrade` goes on naming
        # it as hand-edited rather than refreshing their edit away.
        if record is not None and digest(before) == record.sha256:
            ledger = ledger.with_record(replace(record, sha256=digest(body)))
            restamped = True
    # Written before anything is removed: a removal that fails below must not take the records of
    # the renames with it.
    if restamped:
        ledger.write(root)
    ledger, retirement, retired_paths, changed = _retire(root, ledger, ledgered=ledgered)
    if changed:
        ledger.write(root)
    renamed = [relative for relative, _, _ in rewrites]
    if renamed:
        notes.append(f"named this overlay after {suffix}: {', '.join(renamed)}")
    else:
        notes.append(f"the manifests already name {suffix}; nothing was renamed")
    if absent:
        notes.append(
            f"this overlay carries no {', '.join(absent)}, so there was nothing to name there; "
            f"`stayfixed overlay upgrade` adds what a newer template ships"
        )
    notes += retirement
    notes.append(_install_secret_scan(root, runner))
    return Initialised(tuple(renamed), tuple(notes), (*renamed, *retired_paths))


def _retire(
    root: Path, ledger: Manifest, *, ledgered: bool
) -> tuple[Manifest, list[str], list[str], bool]:
    """Remove each file a release no longer ships that still holds what stayfixed wrote there,
    name each one kept, and say which paths this changed and whether the ledger did.

    `overlay upgrade` removes them too, but nobody is told to run it on an overlay just made:
    `overlay create --template` and `setup --overlay create:` generate one from a template
    repository, and a template published at an earlier release ships
    `common/memory/README.md`, which the note reader reads as a note, so `memory index --check`
    failed right after the first attach. `init` is the step every such overlay runs.

    The engine's `plan` decides, by the digest the ledger records or, in a tree generated from a
    template, which carries none, by the digest a release shipped (`template.retired`). Its
    verdict is acted on here rather than through `apply`, which would write a ledger into a tree
    that arrived without one. A file `plan` cannot read, one that cannot be removed and a
    successor that cannot be written are each named and passed over, never a reason to stop
    `init`: stopping lost the lines of the files already removed and left their records in a
    ledger nothing then wrote, and a later run, finding the file absent, kept the record for good.
    The ledger returned drops the records of the files actually removed, and only those.

    A removed file whose successor (`layout.SUCCESSORS`) is absent gets the shipped successor in
    its place: such a template carried the old name only, and a directory left empty is one git
    does not keep, so a clone of the overlay elsewhere would have no `common/memory/` for the
    `developer` link to reach. Each directory above a file this run removed then goes once it is
    empty, as `overlay upgrade` does it, and only above a file that was there to remove.

    **A path the ledger supplied prints through `printed.quoted`.** The ledger is committed with
    the overlay, and a record whose target this release cannot produce is named at that target,
    so a line break or an escape sequence in it would reach the terminal and a CI runner as it
    stood. A record whose target only case-folds to a place this release's file can be is
    removed, or left, at the target it names, which may hold letters outside the grammar. A path
    inside the path grammar prints as itself. A successor's path is this build's own, and so is
    every path `plan` refuses here: the one refusal that names a recorded target is a region's or
    an entry's, and a retired overlay file is a whole file, so the wrap on that line guards
    nothing a ledger can reach today.
    """
    planned = plan(root, preset_defaults(root.name), retired())
    notes = [f"left {quoted(r.target)}: {r.reason}" for r in planned.refusals]
    changed = False
    removed: list[str] = []
    emptied: list[str] = []
    written: list[str] = []
    for action in planned.actions:
        if action.verb is Verb.SKIP_MODIFIED:
            notes.append(f"left {quoted(action.target)} ({action.reason})")
            continue
        if not unlinks(action):
            continue
        present = os.path.lexists(root / action.target)
        try:
            fsops.remove_within(root, action.target)
        except OSError as exc:
            notes.append(f"left {quoted(action.target)}: cannot be removed: {fsops.said(exc)}")
            continue
        notes.append(f"removed {quoted(action.target)}, which this release no longer ships")
        removed.append(action.target)
        if present:
            emptied.append(action.target)
        if ledger.get(action.artifact_id) is not None:
            ledger = ledger.without(frozenset({action.artifact_id}))
            changed = True
    successors = {SUCCESSORS[target] for target in removed if target in SUCCESSORS}
    shipped = [template for template in templates() if template.id in successors]
    for action in plan(root, preset_defaults(root.name), shipped).actions:
        if action.verb is not Verb.CREATE or action.payload is None:
            continue
        try:
            fsops.write_within(root, action.target, action.payload)
        except OSError as exc:
            notes.append(
                f"{action.target} cannot be written: {fsops.said(exc)}; "
                "`stayfixed overlay upgrade` writes it"
            )
            continue
        notes.append(f"wrote {action.target} in its place")
        written.append(action.target)
        if ledgered and action.record is not None:
            ledger = ledger.with_record(action.record)
            changed = True
    # Last, once each successor is in place, so a directory one is written into is never emptied
    # on the way.
    for target in emptied:
        fsops.rmdir_parents_within(root, target)
    return ledger, notes, [*removed, *written], changed


def _read_manifest(root: Path, relative: str) -> str:
    try:
        return (root / relative).read_text(encoding="utf-8")
    except OSError as exc:
        raise Failure(f"{relative} cannot be read: {exc}") from exc
    except UnicodeDecodeError:
        raise Failure(f"{relative} is not UTF-8 text") from None


def _renamed(text: str, relative: str, suffix: str) -> str | None:
    """The manifest named after the owner, or `None` when it already named them.

    The text and not a boolean, because the caller re-stamps the scaffold ledger with exactly
    what goes to disk — reading the file back to hash it would hash whatever is there then.
    Nothing is written here: every manifest is decided before any is written.
    """
    try:
        document = json.loads(text)
    except json.JSONDecodeError as exc:
        raise Failure(f"{relative} is not valid JSON: {exc}") from exc
    if not isinstance(document, dict):
        raise Failure(f"{relative} is not a JSON object")
    changed = False
    if (renamed := _suffixed(document.get("name"), suffix)) is not None:
        document["name"] = renamed
        changed = True
    if _named_for(document, ACCOUNT_KEYS[relative], suffix):
        changed = True
    # The marketplace's entries name the plugin they publish, so an entry left unsuffixed would
    # advertise a plugin whose manifest no longer answers to that name.
    entries = document.get("plugins")
    if isinstance(entries, list):
        for entry in entries:
            if isinstance(entry, dict) and (name := _suffixed(entry.get("name"), suffix)):
                entry["name"] = name
                changed = True
    if not changed:
        return None
    return json.dumps(document, indent=2) + "\n"


def _named_for(document: dict[str, object], key: str, account: str) -> bool:
    """Put `account` under `document[key]["name"]` where nobody has put a name; whether it changed.

    "Where nobody has": the key is absent (an overlay generated from a template that predates it,
    which is exactly what an owner's own published copy can be), or its name is the template's
    `PLACEHOLDER_ACCOUNT`. A name the owner wrote, and any other field beside it (an email, a
    URL), stay: `init` is run more than once and by people who edited the file first, and an
    account name that overwrote a person's own would be a rewrite of something stayfixed does not
    own. A value of another shape (`"author": "a string"`) is left alone for the same reason.
    """
    current = document.get(key)
    if current is None:
        document[key] = {"name": account}
        return True
    if (
        isinstance(current, dict)
        and current.get("name", PLACEHOLDER_ACCOUNT) == PLACEHOLDER_ACCOUNT
    ):
        current["name"] = account
        return True
    return False


def _install_secret_scan(root: Path, runner: Runner) -> str:
    """Install the commit-time secret scan, or say why it is not installed.

    The overlay's secret scanning runs gitleaks twice and this is one of the two; the other is
    the push workflow the template ships, which is what makes `--no-verify` not the last word.
    A missing `pre-commit` is a reported finding, never a traceback.
    """
    done: Completed = runner.launch(["pre-commit", "install"], root)
    if done.code == 0:
        return "installed the commit-time secret scan with `pre-commit install`"
    return (
        f"`pre-commit install` did not run ({_detail(done)}), so the commit-time secret scan "
        f"is not installed; install pre-commit and run it in {root}. The push-time scan still runs"
    )
