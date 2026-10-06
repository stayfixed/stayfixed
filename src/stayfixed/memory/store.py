"""Where the notes are, and the four ways that answer can be a lie.

A store is a per-project value with no machine-level default, because the wrong answer is not
"no memory" but *another project's* memory reaching this session. Four things are therefore
checked, and each closes a hole the other three leave open:

1. **The shape.** In overlay mode `paths.memory` is a real directory holding one link per
   group. It is not one link: `developer` points into the overlay's `common/memory`,
   which is shared across projects and cannot live under `projects/<name>/`. A single link at
   `paths.memory` would lose the cross-project half of the store outright.
2. **Containment inside the store.** A group name is repository-controlled — `memory.groups`
   is an ordinary `stayfixed.toml` list — so `groups = ["../secret"]` must not become a read,
   and certainly not a write, outside the store. `config/paths.py` says in as many words that
   this field reaches no guard of its own and that the module consuming it owns the check.
3. **The link's target.** A link is honoured only when it lands inside *this project's* share
   of the recorded overlay: `common/memory`, or `projects/<the bound name>/memory`. Testing
   containment in the overlay root alone lets an honestly-named, honestly-bound project point
   one directory sideways at another client's notes.
4. **The binding.** The overlay's `projects/<name>/project.toml` must record this
   repository's own `origin`. `git` runs with a scrubbed environment, because an inherited
   `GIT_DIR` would otherwise answer for a different repository altogether.

**What the environment can and cannot choose.** The store's *location* is never named by a variable
this process reads: `resolve` takes an `env` mapping and ignores it by contract, and
`gitenv.git_answer` runs with a scrubbed environment, so neither a `STAYFIXED_STORE`-shaped variable
nor an inherited `GIT_DIR` can point this module at another project's notes. Both halves are pinned
by tests, and both matter because a committed `.claude/settings.json` may carry an `env` block that
applies with no trust prompt in a non-interactive session.

**The machine file makes the same claim.** `machine_config_path` gates `STAYFIXED_CONFIG`,
`XDG_CONFIG_HOME` and `HOME` alike behind `interactive` (off a terminal the home directory is the
password database's), since gating one alone is worth nothing: each of them reaches the same
file, and this area routes the store's overlay anchor
(`overlay_root(None)`) and the trust record (`trust._trust_file(None)`) through it. A committed
`env` block that could set either would choose which overlay root `permitted_roots` is computed
from, and which `trust.json` `may_inject` consults, wherever no `--machine` is threaded.

Stated exactly, because the exposure is not the same size as the invariant: pointing a variable
somewhere of the author's choosing would **suppress** memory — no overlay root and no recorded
digest means overlay stores refuse to resolve and the gate fails closed — while making it
*grant* anything would additionally require a pre-recorded hash matching a digest of the store
at the clone's absolute path, which is the key `trust` records under. It is still an invariant
two other properties lean on, and holding it in `config/machine.py` — the foundation's file — is
what makes the claim above about `env` a claim about the whole module rather than about
`resolve` alone.
"""

from __future__ import annotations

import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from stayfixed.config.loader import UNPARSEABLE
from stayfixed.config.overlay import overlay_root
from stayfixed.config.paths import PathEscape, contained
from stayfixed.config.schema import Config
from stayfixed.findings import listed
from stayfixed.fsops import read_regular_text
from stayfixed.gitenv import GitUnavailable, git_answer, origin_remote
from stayfixed.printed import clipped, quoted

LOCAL_STORE = Path(".stayfixed") / "local" / "memory"
# The overlay's per-project directory, named once: the two call sites below and the `overlay` area
# all spell it, and a literal at each is the drift `_inside` names: "two spellings of a containment
# rule is one more place for them to stop agreeing". It lives here, with `COMMON`, because this
# module is the one that resolves the overlay layout for the hook path; `overlay` imports it from
# the surface.
PROJECTS = "projects"
PROJECT_RECORD = "project.toml"
# The one directory under `projects/<name>/` that holds notes, named once: `permitted_roots`
# builds the path with it, and `attach` states the path's shape with it where it may not print
# the project's name, and lays out the group directories under it.
STORE_DIR = "memory"
COMMON = Path("common") / "memory"


@dataclass(frozen=True)
class Store:
    path: Path
    mode: str
    root: Path
    groups: dict[str, Path] = field(default_factory=dict)
    # Per-group refusal prose from `_group_targets`, built the same way `refusal_reason` builds
    # its message: it embeds the raw `memory.groups` entry, a field with no schema constraint
    # (a TOML multi-line string carries literal newlines through unchanged). Same hazard, same
    # rule — never put a value out of this dict into model context unwrapped; `trust.wrap` it
    # first if a consumer must show the detail.
    unavailable: dict[str, str] = field(default_factory=dict)
    # The machine file this store was resolved against, carried rather than re-passed.
    #
    # Not an optional keyword on every function that reads the store: a `None` there is not
    # inert — it re-reads `$XDG_CONFIG_HOME/stayfixed/config.toml` out of the process
    # environment, silently changing `permitted_roots`, the index destination, and which
    # `trust.json` is consulted — so a caller that forgot one argument would get a different
    # overlay, a different write target and a different trust record, with nothing to say so.
    #
    # `Store` is frozen and `resolve` builds it exactly once, from the `machine` it was given.
    # Putting the value here makes the mismatch unrepresentable instead of documented.
    machine: Path | None = None


@dataclass(frozen=True)
class Unresolved:
    """Why no store resolved: stayfixed's own sentence, and the repository's words it is about.

    Two fields because the two reach a reader differently. `said` is built of nothing a
    repository chose, so it prints as it is and a command puts it *before* the region
    `trust.wrap` marks as data — which is where a way out has to be for anyone to act on it.
    `detail` may carry `memory.groups` entries, `paths.memory` or the project's name, and reaches
    a reader only inside that region (`memory.commands._no_store`). Every cause has a sentence of
    its own, so only `detail` may be absent; `str()` joins what there is, for a caller that only
    reports it wrapped.
    """

    said: str
    detail: str | None = None

    def __str__(self) -> str:
        return ": ".join(part for part in (self.said, self.detail) if part)


def main_checkout(root: Path) -> Path:
    """The checkout that owns the store, for a session running inside a worktree.

    The result must be an ancestor of nothing and a sibling of anything — but it must be a
    real git answer, not one an inherited `GIT_DIR` produced, which is why `git_answer` scrubs.

    Raises `GitUnavailable` rather than answering `root` when `git` could not be run. Answering
    `root` would make `worktree.link` open with "this is the main checkout" and become a silent
    no-op: no group links, no index link, no harness link, and `hooks.py` emitting its "nothing
    to do" answer while every memory bundle is empty and nothing reports a failure.
    """
    common = git_answer(root, "rev-parse", "--path-format=absolute", "--git-common-dir").require(
        "`git` could not answer which checkout owns this worktree in this checkout; stayfixed "
        "cannot tell where the store is without it — check that `git` runs here"
    )
    return Path(common).parent if common else root


_WORKTREES = "worktrees"
_BACK_POINTER = "gitdir"


def _registered_worktree(root: Path) -> Path | None:
    """The checkout `root` is genuinely a registered worktree of, or `None` when it is not one.

    Not whether the worktree lives *under* the main checkout: in git's own documented layout,
    `git worktree add ../side` puts the tree beside the checkout, so a containment test would
    answer that there is no store at all — and nothing would be linked in the one place this
    module exists for.

    **Registration is the question containment would only stand in for.** A linked worktree's
    private git directory is `<common-dir>/worktrees/<name>`, and that directory holds a
    `gitdir` file naming the `.git` file the worktree was created for. Both halves are
    checked, because only the first is written by whoever owns `root`: a `.git` may be a plain
    text pointer, so any directory can *claim* to be a worktree of a repository it was never
    added to, and `git rev-parse` will answer for that repository. The back-pointer is the
    half the claimed repository wrote. (A clone cannot ship either — git refuses to track a
    path named `.git` — but the fallback reads a store out of another repository, so it does
    not rest on that.)

    Both queries go through `git_answer`, which scrubs the environment. That is a second lock on
    the same door rather than this one's support: an inherited `GIT_DIR` answers for whatever
    repository it names, and there it is also its own common dir, so a redirected fallback
    fails the registration test above anyway. Because they are redundant, each is pinned by its
    own test rather than by one that dies only when both are gone —
    `test_an_inherited_git_dir_never_reaches_the_git_helper` for the scrubbing and
    `test_a_directory_that_merely_sits_under_a_checkout_is_not_a_worktree_of_it` for this.
    """
    common = git_answer(root, "rev-parse", "--path-format=absolute", "--git-common-dir")
    private = git_answer(root, "rev-parse", "--path-format=absolute", "--git-dir")
    if not (common.ran and private.ran):
        raise GitUnavailable(
            "`git` could not answer whether this is a registered worktree; stayfixed cannot "
            "fall back to the checkout that owns the store without it — check that `git` "
            "runs here"
        )
    if common.value is None or private.value is None:
        return None
    common_dir, private_dir = Path(common.value).resolve(), Path(private.value).resolve()
    if private_dir.parent != common_dir / _WORKTREES:
        return None
    try:
        recorded = (private_dir / _BACK_POINTER).read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError):
        return None
    if not recorded or Path(recorded).parent.resolve() != root.resolve():
        return None
    owner = common_dir.parent
    return None if owner == root.resolve() else owner


# The one answer to "does the overlay's record bind this checkout's `origin`", which `memory`
# commands, `attach`, `attach --check`, `doctor` and the session-start line all read
# (`binding_state`). A checkout with no `origin` is its own state and is asked first, and here
# alone: a second answer to it would be one more place to call it a different remote URL and point
# at `--trust-remote`, which refuses for the missing `origin`.
UNBOUND = "unbound"
BOUND = "bound"
MISMATCH = "mismatch"
NO_ORIGIN = "no-origin"
BINDING_STATES = (UNBOUND, BOUND, MISMATCH, NO_ORIGIN)

# Each cause, and the way out that fits it, rather than one sentence for all of them: "run
# `stayfixed attach`", for a changed remote, is the command that refuses. Fixed text: the
# project's name and the record's path, which the repository chooses, go in `Unresolved.detail`
# and never in these. The two a surface says with a way out of its own are kept apart from their
# way out, so every surface says the same cause.
NO_RECORD = (
    "the overlay records no remote for this project, so nothing binds it to this repository; "
    "run `stayfixed attach` to bind it"
)
RECORD_UNREADABLE = (
    "the overlay's record of this project cannot be read, so the binding cannot be checked; "
    "repair or remove the file named below, then run `stayfixed attach`"
)
NO_ORIGIN_CAUSE = (
    "this checkout has no `origin` remote, so there is nothing to bind to the overlay or to check "
    "its record against"
)
NO_ORIGIN_WAY_OUT = (
    "add the `origin` remote (the one this project was bound with, when the overlay records one), "
    "then run `stayfixed attach`"
)
NO_REMOTE = f"{NO_ORIGIN_CAUSE}; {NO_ORIGIN_WAY_OUT}"
DIFFERENT_REMOTE = (
    "the overlay records a different remote URL under this project's name (the same repository "
    "under another URL form, https or ssh, counts as different too)"
)
REMOTE_MISMATCH = (
    f"{DIFFERENT_REMOTE}; run `stayfixed attach --trust-remote` only if this checkout should be "
    f"bound to it"
)
_UNBOUND_CAUSES = {UNBOUND: NO_RECORD, NO_ORIGIN: NO_REMOTE, MISMATCH: REMOTE_MISMATCH}
# Asked before any of the four: a machine record naming an overlay root that is not there (the
# overlay moved, or this machine never cloned it) must not read as "no record of this project",
# whose way out, `stayfixed attach`, refuses a `--store` outside the root the machine records. The
# root is the owner's own configuration and not the repository's, so it is part of this sentence,
# through `printed.quoted`, rather than a detail printed inside the region that marks repository
# text.
OVERLAY_GONE = (
    "the overlay root the machine configuration records, {root}, is not a directory on this "
    "machine; record where the overlay is now with `stayfixed setup --preset NAME --overlay "
    "PATH`, then run `stayfixed attach`"
)


# Two of the resolver's own sentences, for the causes a store most often fails on. Each is
# stayfixed's text: the path it is about, and the groups that did not resolve, stay in the detail.
STORE_MISSING = "the memory store's directory does not exist"
BUILT_BY_ATTACH = "; run `stayfixed attach` to build it"


def binding_state(recorded: str | None, origin: str | None) -> str:
    """`no-origin`, `unbound`, `mismatch` or `bound`, for the remote the overlay records for this
    project and this checkout's `origin` — and never `bound` because nobody looked.

    A missing `origin` is answered first, whatever the record says: with nothing to compare, a
    record is neither a mismatch nor a binding, and the way out is the same with a record or
    without one. URLs are compared exactly: normalising `git@…` against `https://…` is a binding
    rule, and a hostile clone is caught by this comparison, since it chooses `project.name` and not
    which remote the overlay recorded under it.
    """
    if origin is None:
        return NO_ORIGIN
    if recorded is None:
        return UNBOUND
    return BOUND if recorded == origin else MISMATCH


def read_binding_record(record: Path) -> dict[str, str]:
    """The binding record at `record`, `projects/<name>/project.toml`: each key whose value is a
    non-empty string, mapped to it.

    The one reader of that file, and no failure policy: an `OSError`, a `UnicodeDecodeError` and
    each of `UNPARSEABLE` are raised as met, because what a record that cannot be read means is
    each caller's to say, and its three callers say three things, each at its own `except`.
    `_bound` answers the hook path "unreadable", which degrades closed; `attach`'s `_recorded`
    stops the run, so a broken record never becomes a first attach; and `attach`'s
    `_first_attach` keeps today's date, which is a note and binds nothing. Whether there is a
    record at all is the caller's question too, asked before this.

    Read through `fsops.read_regular_text`, so a record swapped for a FIFO or a device after that
    question is refused unread, an `OSError` like any other, and one past the cap is refused too.
    """
    raw = tomllib.loads(read_regular_text(record))
    return {key: value for key, value in raw.items() if isinstance(value, str) and value}


def _bound(overlay: Path, project: str, root: Path) -> Unresolved | None:
    """`None` when the overlay's record binds this checkout's `origin`, else which cause failed.

    The answers are the causes above, each with the project's name, or the record's path, as the
    detail they are about; the state is `binding_state`'s.
    """
    record = overlay / PROJECTS / project / PROJECT_RECORD
    recorded = None
    if record.is_file():
        try:
            recorded = read_binding_record(record).get("remote")
        except (OSError, UnicodeDecodeError, *UNPARSEABLE):
            # The path and never the exception: a TOML error's message quotes the file's own
            # text, and this file holds a remote URL.
            return Unresolved(RECORD_UNREADABLE, quoted(str(record)))
    cause = _UNBOUND_CAUSES.get(binding_state(recorded, origin_remote(root)))
    return None if cause is None else Unresolved(cause, f"project {quoted(project)}")


def _inside(candidate: Path, parent: Path) -> bool:
    """`candidate` is `parent` or sits under it, both resolved first.

    `Path.is_relative_to` and not a hand-rolled `== base or base in parents`, which is the same
    predicate written out longhand, beside `index._resolved_if_permitted`'s short spelling of
    it. Two spellings of a containment rule is one more place for them to stop agreeing.
    """
    return candidate.resolve().is_relative_to(parent.resolve())


def permitted_roots(overlay: Path, project: str) -> tuple[Path, Path]:
    """This project's whole share of the overlay: the common notes and its own."""
    return overlay / COMMON, overlay / PROJECTS / project / STORE_DIR


# The one group whose notes are not this project's, and `common/memory` *is* its store rather
# than its parent: this module's own docstring says so — "`developer` points into the overlay's
# `common/memory`, which is shared across projects and cannot live under `projects/<name>/`" —
# and the overlay template's README says it to the owner. Named here beside `COMMON` and
# `permitted_roots` because `attach` builds the link tree from this routing and `doctor` reports
# on it; a third spelling is one more place for them to stop agreeing.
COMMON_GROUP = "developer"


def overlay_group_target(overlay: Path, project: str, group: str) -> Path:
    """Where one group's notes live inside the overlay.

    A rule and deliberately not a probe over what happens to exist: a group directory that is
    not there yet is a first attach, not a reason to link somewhere else. The answer is always
    inside `permitted_roots`, which is what the resolver then checks the link against.
    """
    common, own = permitted_roots(overlay, project)
    return common if group == COMMON_GROUP else own / group


def _declared(root: Path, config: Config) -> Path | None:
    try:
        return contained(root, config.paths.memory, allow_final_symlink=True)
    except PathEscape:
        return None


def _group_targets(
    base: Path, config: Config, overlay: Path | None
) -> tuple[dict[str, Path], dict[str, str]]:
    groups: dict[str, Path] = {}
    unavailable: dict[str, str] = {}
    for group in config.memory.groups:
        try:
            target = contained(base, group, allow_final_symlink=True)
        except PathEscape as exc:
            unavailable[group] = str(exc)
            continue
        if not target.exists():
            unavailable[group] = f"{clipped(group)} is not in the store"
            continue
        if target.is_symlink():
            if overlay is None:
                unavailable[group] = f"{clipped(group)} is a link and no overlay is recorded"
                continue
            allowed = permitted_roots(overlay, config.project.name)
            if not any(_inside(target, permitted) for permitted in allowed):
                unavailable[group] = (
                    f"{clipped(group)} links outside this project's share of the overlay "
                    f"({', '.join(str(p) for p in allowed)})"
                )
                continue
        groups[group] = target
    return groups, unavailable


def _names_own_share(override: str | None, config: Config, overlay: Path | None) -> bool:
    """Whether `--store` names this project's own share of the recorded overlay, in overlay mode.

    That directory is the far end of the link tree, not a store of its own: `developer` lives in
    `common/memory`, beside it, so resolving groups *under* it would answer a smaller store — an
    index rendered from it has no developer notes, and `--check` would call that index current. A
    store is one store however it is named, so this name resolves as the plain run does.
    """
    if override is None or overlay is None or config.memory.mode != "overlay":
        return False
    own = permitted_roots(overlay, config.project.name)[1]
    return Path(override).expanduser().resolve() == own.resolve()


# A store and no reason, or no store and the reason: `resolved`'s answer, which never holds both
# and never neither.
Resolution = tuple[Store, None] | tuple[None, Unresolved]


def _resolve_at(
    root: Path, config: Config, override: str | None, machine: Path | None
) -> Resolution:
    mode = config.memory.mode
    overlay = overlay_root(machine)
    if _names_own_share(override, config, overlay):
        override = None
    if override is not None:
        base = Path(override).expanduser()
    elif mode == "local-only":
        try:
            # `contained` with no `allow_final_symlink` refuses a symlink at *any* level
            # between the root and the target, which testing `base.is_symlink()` would not:
            # it never looks at `.stayfixed` and `.stayfixed/local`, and a group directory
            # reached *through* one of those is not itself a symlink, so the per-group check
            # below would never run either. That is the same hazard the comment below documents for
            # `paths.memory`, left open one directory higher — and in the mode the preset
            # ships by default, where the whole store is otherwise ungoverned by `contained`.
            base = contained(root, str(LOCAL_STORE))
        except PathEscape as exc:
            return None, Unresolved(
                "the local-only store is not a real directory inside the project",
                f"{exc}; local-only memory must be a real directory",
            )
    else:
        declared = _declared(root, config)
        if declared is None:
            return None, Unresolved(
                "paths.memory does not stay inside the project",
                f"paths.memory ({config.paths.memory!r}) does not stay inside the project",
            )
        base = declared
        # Check 1, the shape: in every mode but `local-only` and an explicit `override`,
        # `paths.memory` itself must be a real directory — one link per group, not one link for the
        # whole store. This has to hold in overlay mode too, not just `in-repo`: a group directory
        # reached *through* a symlinked `paths.memory` is not itself a symlink, so the per-group
        # check below (`permitted_roots`) never runs, and the whole store silently becomes whatever
        # `paths.memory` was pointed at — including another project's share.
        if declared.is_symlink():
            return None, Unresolved(
                f"paths.memory is a symlink, and {mode} memory must be a real directory",
                f"{config.paths.memory} is a symlink; {mode} memory must be a real directory",
            )
    if mode == "overlay":
        if overlay is None:
            return None, Unresolved(
                "no overlay root is recorded in the machine configuration; run `stayfixed setup`"
            )
        if not overlay.is_dir():
            return None, Unresolved(OVERLAY_GONE.format(root=quoted(str(overlay))))
        unbound = _bound(overlay, config.project.name, root)
        if unbound is not None:
            return None, unbound
    if not base.is_dir():
        # `attach` builds the directory only in overlay mode, where it is the link tree; elsewhere
        # it refuses, so it is named as the way out only there.
        said = STORE_MISSING + (BUILT_BY_ATTACH if mode == "overlay" else "")
        return None, Unresolved(said, str(base))
    groups, unavailable = _group_targets(base, config, overlay if mode == "overlay" else None)
    if not groups:
        # Counted, and capped at `LISTED_LIMIT` like every list of names: `memory.groups` is
        # bounded in number by nothing, and this reason reaches a refusal with no `--json`. In
        # sorted order, as `_unavailable` gives the same failure, so "the first eight" means one
        # thing; each group clipped, since nothing bounds one group's length either.
        reasons = [f"{clipped(k)}: {unavailable[k]}" for k in sorted(unavailable)]
        if not reasons:
            return None, Unresolved("the store has no groups")
        head = f"none of the {len(reasons)} configured group(s) resolved"
        return None, Unresolved(head, listed(reasons))
    return Store(base, mode, root, groups, unavailable, machine), None


def resolved(
    root: Path,
    config: Config,
    *,
    override: str | None = None,
    machine: Path | None = None,
) -> Resolution:
    """The store and, when there is none, why — in **one** pass.

    `resolve` and `refusal_reason` each walk the whole resolution, and a caller that needs both
    (every `memory` command does: the store to work with, the reason to report) would walk it
    twice. Each walk runs up to four `git` queries with a five-second timeout apiece, so a
    hanging `git` would cost a refused command up to forty seconds — inside a `SessionStart`
    hook, once per bundle entry. The two functions below stay, because a caller that wants only one
    of the two answers should not have to say so; this is the one for callers that want both.

    The reason's `detail` is repository-authored text: see `refusal_reason` for what that
    obliges a consumer to do with it. Its `said` is stayfixed's own and prints as it is.

    There is always exactly one of the two, and the type says so (`Resolution`): a caller that
    tests `found[0] is None` holds a reason, and has no "no reason" case to invent words for.
    """
    found = _resolve_at(root, config, override, machine)
    if found[0] is not None:
        return found
    # A worktree resolves through the checkout it is *registered against*, never through
    # whatever a redirected `GIT_DIR` named and never merely because a directory sits above it.
    parent = _registered_worktree(root)
    if parent is None:
        return found
    return _resolve_at(parent, config, override, machine)


def resolve(
    root: Path,
    config: Config,
    *,
    override: str | None = None,
    machine: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> Store | None:
    # `env` is accepted and never read: a store is never selected through the
    # environment, and a parameter that exists and is ignored is a claim a test can pin.
    del env
    return resolved(root, config, override=override, machine=machine)[0]


def refusal_reason(
    root: Path,
    config: Config,
    *,
    override: str | None = None,
    machine: Path | None = None,
) -> str | None:
    """Why `resolve` returned no store for this call, or `None` when it would not have refused.

    The string is built out of `memory.groups` entries (`_group_targets`'s `unavailable`
    messages) and out of `config.paths.memory`, both repository-controlled and neither
    schema-constrained — a TOML multi-line string carries literal newlines through unchanged,
    so this can come back multi-line, and the same repository text can appear in it twice. It
    must never reach model context unwrapped: see `stayfixed.memory.hooks`, this area's own
    consumer, which refuses to put this text into `HookResult.context` for exactly that reason.
    A consumer that must show the detail wraps it first with `trust.wrap`.
    """
    reason = resolved(root, config, override=override, machine=machine)[1]
    return None if reason is None else str(reason)


def inside_project(store: Store) -> bool:
    """Whether any note actually lives in the repository — the predicate the trust gate turns on.

    Not `memory.mode`, which the clone chooses, and not the store directory, which in overlay
    mode is a real directory of links inside the project. What decides whether a note is the
    machine owner's or the repository's is where the note itself sits: `local-only` puts it
    under `.stayfixed/local/`, which a `.gitignore` keeps out of a clone the owner made and
    does not keep out of a clone the attacker authored.

    This asks the question of the *notes*, and deliberately keeps asking only that. Folding
    `store.path` in would make every overlay store repository data — the store directory is a
    real directory in the repository in exactly that mode — and so would gate the machine
    owner's own overlay notes behind a trust prompt and wrap them as data, defeating every
    standing rule in the mode this project actually ships. A file that is not a note and
    belongs to no group is asked about one at a time, with `in_repository` below.

    **Where it cannot answer, it answers closed.** In `local-only` and `in-repo` the notes are
    in the repository by construction — `.stayfixed/local/memory` and `paths.memory` are both
    resolved under `root` through `contained`, which refuses a symlink at every level — so a
    group landing outside `store.root` in those modes is a resolution that went wrong, not a
    store belonging to the machine owner. Answering False there is what let a clone that
    escaped the resolver reach the model with no trust record and no `trust.wrap`: a gate
    whose default for the unclassifiable is "ungated" is the wrong way round. `overlay` keeps
    its answer, because outside `store.root` is precisely where the overlay's layout puts those
    notes.
    """
    if any(_inside(target, store.root) for target in store.groups.values()):
        return True
    return store.mode != "overlay"


def in_repository(store: Store, path: Path) -> bool:
    """Whether one particular file this store yields sits in the repository itself.

    `inside_project` cannot answer this for `MEMORY.md`: the index is not a note, belongs to no
    `memory.groups` entry and lives at `store.path`, which in overlay mode is inside the
    repository while every group resolves far outside it. A caller that is about to inject a
    specific file asks about that file.
    """
    return _inside(path, store.root)
