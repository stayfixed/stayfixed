"""Create the owner's private overlay: generated on GitHub, or rendered here.

Two sources, one result, both reached through `stayfixed setup --overlay`. `generate` asks GitHub
to generate a private repository from a public template and clone it — the owner's own
`<owner>/stayfixed-overlay-template` when they have published one, and the publisher's
otherwise; `render` renders `templates/overlay/` at a path through the scaffold engine, makes a
git repository of it, and touches no network. A template and not a fork: a fork's visibility is
bound to the upstream network and cannot be made private, and an overlay that is not private is
the one outcome this whole area exists to prevent.

`finish` is what every overlay `setup` makes runs next: a generated one has the identity record
named after its owner, and every one gets the commit-time secret scan. Generating is idempotent —
`gh` may give up on the clone with the repository already created, so a second run is the
ordinary case rather than the exception — and so is `finish`.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from stayfixed import fsops
from stayfixed.config.loader import preset_defaults
from stayfixed.errors import Failure
from stayfixed.jsonobject import json_object
from stayfixed.overlay.identity import overlay_fault, segment
from stayfixed.overlay.layout import IDENTITY_RECORD, OVERLAY_FILES
from stayfixed.overlay.template import templates
from stayfixed.printed import answered
from stayfixed.runner import NOT_FOUND, TIMED_OUT, Completed, Runner
from stayfixed.scaffold import apply, plan

TEMPLATE_REPOSITORY = "stayfixed-overlay-template"
# Whose public copy of that repository `generate` falls back to when the owner has published none of
# their own. The publisher's account is a fact about where this project's template lives, and
# `scripts/publish_template.py` keeps reading `TEMPLATE_REPOSITORY` alone for its `--name` default:
# what an owner *publishes* is theirs to name, what they *generate from* has this one fallback.
TEMPLATE_PUBLISHER = "stayfixed"
# The fallback named with its host, and never host-relative: `gh` resolves an unqualified
# `OWNER/REPO` on `GH_HOST`, which the runner keeps, so on a GitHub Enterprise host the fallback
# would be whoever owns `stayfixed` there, and the owner's private overlay, whose hooks run in
# every session, would be generated from it. `gh repo create --template` and `gh repo view` look a
# `HOST/OWNER/REPO` name up on that host whatever `GH_HOST` says (measured against gh 2.101.0).
# The owner's own `<owner>/…` probe stays host-relative: that repository is on the owner's host.
TEMPLATE_PUBLISHER_HOST = "github.com"
PUBLISHED_TEMPLATE = f"{TEMPLATE_PUBLISHER_HOST}/{TEMPLATE_PUBLISHER}/{TEMPLATE_REPOSITORY}"
# How long to wait before the one retry, when `gh` says the repository exists and the clone brought
# nothing down. The spike record's *template creation race and renaming* trial did not reproduce
# that race in its one attempt, so this is carried on the strength of reasoning rather than of a
# measurement: generation is asynchronous on GitHub's side and one clean run cannot rule out a slow
# one.
RETRY_WAIT_SECONDS = 10
# What `docs/cli.md` says about the template, and what a failure has to say too. `create:`
# generates from the owner's own copy when they have published one, and from the publisher's public
# copy otherwise, so an account that never published one still has somewhere to generate from. A
# failure that does not say so sends the owner to `gh auth status` for a repository that was never
# there.
TEMPLATE_PRECONDITION = (
    f"`create:` generates from <owner>/{TEMPLATE_REPOSITORY} when the owner has published one, "
    f"and from {PUBLISHED_TEMPLATE} otherwise; `stayfixed setup --overlay <path>` renders the "
    f"same tree at a path with no network call"
)
# What the shipped identity record holds where an owner and a repository name go, and what
# `finish` replaces with a generated overlay's own. `templates/overlay/stayfixed-overlay.toml`
# carries the same two lines, and `tests/overlay/test_create.py` renders the template and fails
# when the two drift apart.
PLACEHOLDER_OWNER = 'owner = "your-account"'
PLACEHOLDER_NAME = 'name = "stayfixed-private"'
# What `gh repo view` prints on stderr, whatever the name, when the repository does not exist or
# this token cannot see it (measured against gh 2.101.0, `stayfixed/definitely-missing-xyz`):
# `GraphQL: Could not resolve to a Repository with the name '<slug>'. (repository)`, exit 1. It is
# the only thing that tells "not found" from an expired token (`HTTP 401: Bad credentials`, also
# exit 1) and from a network failure, so it is matched as the whole phrase and never as the
# shorter "Could not resolve", which `Could not resolve host` shares. A named string, not a cap:
# it bounds nothing and no shipped file changes with it.
NOT_FOUND_ANSWER = "Could not resolve to a Repository"


@dataclass(frozen=True)
class Created:
    root: Path
    notes: tuple[str, ...]
    # The template repository a `generate` run generated from (`<account>/<name>`), so a caller
    # that reports the run can name it without parsing a note. `None` for `render` and for a
    # directory that was already there and was left alone.
    template: str | None = None


def target_root(root: Path, owner: str, name: str) -> tuple[Path, str]:
    """Where `generate(owner, name, root=root)` would put the overlay, and the folded owner.

    Nothing is created and nothing is asked of the network, which is the point: `setup
    --overlay create:<owner>/<name>` has to be able to refuse the *destination* — for lying
    inside the project root, say — before it runs `gh repo create` on somebody's account. The
    destination is knowable from the arguments alone, and it used to be computed only by the
    call that had already created the repository.

    Folded before it is validated, because `SEGMENT` has a lowercase leading class and a
    mixed-case GitHub login is ordinary: validating the raw value refused `OctoCat` while another
    command folded it and accepted it, and the refusal said "is not one path segment" about a value
    that plainly is one. Folding is safe: GitHub logins are case-insensitive, and the folded value
    is what reaches the slug, the remote and the identity record alike.
    """
    account = segment("owner", owner.strip().lower())
    segment("name", name)
    return root / name, account


def render_template(root: Path, name: str) -> Path:
    """Render the shipped template at `root/<name>` through the scaffold engine, and nothing
    else: `render` makes a repository of it, and `scripts/publish_template.py` copies it into the
    template repository's clone."""
    target = root / name
    # **Everything that can refuse runs before anything is created**, and the order is
    # load-bearing rather than tidy. A render that failed after writing the identity record
    # (`templates()` on a stayfixed installed without the tree, a refused path) would leave behind
    # a tree `create:` takes for an overlay already there, and never create the repository at all.
    # A refusal has to cost nothing on disk.
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


def render(target: Path, *, runner: Runner) -> Created:
    """Render the shipped template at `target`, whose parent is a directory, and make it a git
    repository on `main` with no remote.

    The repository is made here and not in `render_template`, which the template's publisher
    also renders through: its scratch tree is cloned over and replaced, and a repository of its
    own there would be pushed as a nested one. A repository is what this owner does next with the
    tree (commit it, give it a private remote), so it is made now, with no remote: the remote is a
    repository that has to exist on GitHub first, and that is the owner's to create.
    """
    rendered = render_template(target.parent, target.name)
    return Created(rendered, _initialise_repository(rendered, runner))


def _initialise_repository(target: Path, runner: Runner) -> tuple[str, str]:
    """The notes a local render ends with: the repository it made, and how to give it a remote.

    A `git` that cannot run is a note and not a failure: the tree is on disk by now, so refusing
    would hide a directory that exists, and the note says the one command that finishes the job.
    `target` was not there before the render (`setup` renders only at a path that names nothing),
    so there is no repository of the owner's for `git init` to meet.
    """
    rendered = "rendered from the shipped template; no network call was made"
    # `git init` and then the branch, and not `git init -b main`: `-b` arrived in git 2.28, and an
    # older `git` refuses the option, so the one command that makes the repository failed there.
    # `symbolic-ref` names the unborn branch on every version.
    remote = (
        "`git remote add origin <the private repository>` and `git push -u origin main` once you "
        f"have created one on GitHub, and write its owner and name into {IDENTITY_RECORD}"
    )
    step = "git init"
    done = runner.launch(["git", "init"], target)
    if done.code == 0:
        step = "git symbolic-ref HEAD refs/heads/main"
        done = runner.launch(["git", "symbolic-ref", "HEAD", "refs/heads/main"], target)
    if done.code != 0:
        return (
            rendered,
            f"`{step}` {_ended(done)} ({answered(done)}), so this is not a git repository on main "
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
    `printed.answered`, which clips it.
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
        f"`gh repo view {mine} …` {what} ({answered(probe)}), so it is not known whether "
        f"you have published a template, and nothing was created."
        + ("" if launched else " Install `gh` and authenticate it, or render the overlay locally.")
        + f" {TEMPLATE_PRECONDITION}"
    )


def _is_template(printed_json: str) -> bool | None:
    """`isTemplate` from what `gh repo view --json isTemplate` printed, or `None` for anything
    that is not exactly an object carrying a boolean there."""
    try:
        # Through `jsonobject`, the one reader of a JSON object: an answer that is not one, or is
        # past the parser or its depth bound, says nothing about `isTemplate`.
        document = json_object(printed_json, "`gh repo view`", error=ValueError)
    except ValueError:
        return None
    value = document.get("isTemplate")
    return value if isinstance(value, bool) else None


def generate(
    owner: str,
    name: str,
    *,
    root: Path,
    runner: Runner,
    wait: Callable[[float], None] = time.sleep,
) -> Created:
    """Generate `<owner>/<name>` on GitHub from the template repository and clone it to
    `root/<name>`; `root` is a directory."""
    # One spelling of "where this lands and what the owner is called", shared with the caller
    # that has to ask before it calls (`setup`'s `--overlay create:`); see `target_root`.
    target, owner = target_root(root, owner, name)
    if overlay_fault(target) is None:
        # Creating the overlay is idempotent by rule: a second run finds the overlay the first
        # one cloned and must not create it again. Anything else already there is `setup`'s to
        # refuse, before this is called.
        return Created(target, (f"{target} already exists and was left alone",))
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
    # Whether a tree arrived, and not whether it is an overlay: what arrived is `setup`'s to judge,
    # and its refusal of one that is not says the repository now exists.
    if fsops.exists(target):
        return Created(target, (f"created {slug} from {template}",), template)
    if created.code in (NOT_FOUND, TIMED_OUT):
        # `gh` could not be launched at all, or hung until the seam gave up. Neither is a state two
        # further subprocesses and a ten-second wait can learn anything about: `gh repo view` would
        # ask the same absent binary a second question, get the same answer, and the failure would
        # then name GitHub for a fault that is this machine's. stayfixed does not install `gh`, so
        # its absence is the machine owner's to fix: a reported finding that names it, never a
        # traceback.
        raise Failure(
            f"`gh repo create {slug} …` could not be run ({answered(created)}), so nothing was "
            f"created and nothing was cloned. Install `gh` and authenticate it, or render the "
            f"overlay locally: {TEMPLATE_PRECONDITION}"
        )
    if created.code != 0:
        # `gh` ran and declined. Its own stderr is the cause — a missing template repository, an
        # expired token, a name already taken — and it is quoted rather than replaced by a
        # guess. The clone is still retried below only when `gh` *succeeded* and nothing
        # arrived, which is the one shape the race can take.
        raise Failure(
            f"`gh repo create {slug} …` exited {created.code} ({answered(created)}), so no tree "
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
    if fsops.exists(target):
        return Created(
            target, (f"cloned {slug}, generated from {template}, on the second attempt",), template
        )
    raise Failure(
        f"{slug} produced no tree at {target}: `gh repo create --clone` reported success and "
        f"left nothing, and the "
        + ("retried" if raced else "one further")
        + f" `git clone` exited {cloned.code} ({answered(cloned)}). "
        + (
            "GitHub reports the repository exists, so generation may still be running — wait and "
            "clone it by hand"
            if raced
            else f"`gh repo view` did not confirm the repository exists ({answered(view)}); "
            f"check `gh auth status`. {TEMPLATE_PRECONDITION}"
        )
    )


def finish(
    root: Path, *, runner: Runner, owner: str | None = None, name: str = ""
) -> tuple[str, ...]:
    """Name a generated overlay after its owner, and install the commit-time secret scan.

    `owner` and `name` go into the identity record in place of the template's placeholders, and
    only there: a value the owner wrote is a line this does not match, and a record that cannot be
    read or written is named and passed over, since the tree is already there and recorded either
    way. A rendered overlay has no owner to name (`owner` is `None`) and keeps the placeholders,
    which the render's note tells the owner to replace. Both are one path segment, so neither needs
    quoting inside a TOML string.
    """
    notes: list[str] = []
    if owner is not None:
        notes.append(_named(root, owner, name))
    notes.append(_install_secret_scan(root, runner))
    return tuple(notes)


def _named(root: Path, owner: str, name: str) -> str:
    try:
        text = fsops.read_regular_text(root / IDENTITY_RECORD, newline="")
        named = text.replace(PLACEHOLDER_OWNER, f'owner = "{owner}"', 1).replace(
            PLACEHOLDER_NAME, f'name = "{name}"', 1
        )
        if named == text:
            return f"{IDENTITY_RECORD} already names its owner and repository"
        fsops.write_within(root, IDENTITY_RECORD, named)
    except UnicodeDecodeError:
        return f"{IDENTITY_RECORD} could not be named after {owner}/{name} (it is not UTF-8)"
    except OSError as exc:
        return f"{IDENTITY_RECORD} could not be named after {owner}/{name} ({fsops.said(exc)})"
    return f"named the overlay after {owner}/{name} in {IDENTITY_RECORD}"


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
        f"`pre-commit install` did not run ({answered(done)}), so the commit-time secret scan "
        f"is not installed; install pre-commit and run it in {root}. The push-time scan still runs"
    )
