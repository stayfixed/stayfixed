"""Make the store reachable from a git worktree.

A worktree is a separate checkout, and the store is git-ignored, so a session working in one
sees none of it — and the harness keys its own project-memory directory by working directory,
so that is missing too. Both gaps are closed with symlinks, never copies: a copy answers reads
and breaks writes, because a note created from a worktree would live only there, diverge from
the canonical store, and vanish with the worktree.

Three rules the shell version of this paid for:

- **A real file or directory at a target is never clobbered.** It is either unmerged work or a
  store the harness created on its own, and destroying either silently is worse than the gap.
- **A dangling symlink is replaced.** `Path.exists()` reports it as absent while `symlink_to`
  still refuses, which aborted the whole hook.
- **The list of what to link is derived, never hand-maintained.** The shell version carried an
  allowlist, and a group added to the store and not to that line was absent from the tree, and
  therefore absent from the floor the reference guard derived from the tree — invisible twice.

Links point at the *resolved* group target, not at the main checkout's own link: in overlay
mode that link is itself a symlink, and a chain breaks the moment `detach` removes the first
hop. It also matters for a group the store's own checks refused: such a group never makes
it into `store.groups`, so sourcing from that dict (and never from `store.path / name`) is what
keeps a boundary the store already enforced from being bypassed a second time here.

The index gets no exemption from that boundary. `store.py` does not track `MEMORY.md` as a
group — it is not a `memory.groups` entry — so nothing upstream ever applies the per-link
target rule to it the way `_group_targets` applies it to every configured group. A symlinked
index is a legitimate member of the tree `attach` creates, so the fix cannot be "refuse a
symlinked index"; it has to be the identical rule a group gets: in overlay mode, honoured only
inside this project's own share of the recorded overlay (`permitted_roots`), and outside overlay
mode refused outright, exactly as an ungoverned group symlink would be.

That rule lives in `index.index_source`, not here, because linking is not its only reader:
`memory index` writes through the same file and its `--check` compares against it, and the
harvest reads it. Two copies of one boundary rule is one copy too many.

One of the two gaps is not like the other. The links inside the worktree are read by this
area's own bundles, which gate on `trust.may_inject` and wrap what they emit; the harness
project-memory link is read by the harness's own memory reader, outside both — so it is the one
hop that leaves this area's gate entirely, and the one place where asking the gate a slightly
wrong question costs everything the gate was for. `link` asks it about the directory the link
exposes, which in overlay mode is repository data even though the notes are not; see the note
on `link` itself.

**And it asks in both directions.** A gate evaluated once, at creation, over state that
persists is not a gate: `~/.claude/projects/<slug>/memory` outlived the record that authorised
it, so a `git pull` that adds a note to a trusted in-repo store lapses the record, closes every
channel this area controls — and left the one channel it does not controlling a live link to
the new bytes. `link` therefore removes that link when the gate now answers False, in the same
call that would have created it: it already knows both facts, and the only state it may act on
is a symlink pointing at this store, never a real directory and never somebody else's link.
"""

from __future__ import annotations

import contextlib
import errno
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from stayfixed import fsops
from stayfixed.config.machine import owner_home
from stayfixed.config.overlay import overlay_root
from stayfixed.config.paths import PathEscape, contained
from stayfixed.config.schema import OVERLAY_MODE, Config
from stayfixed.errors import Failure, Refusal
from stayfixed.harnesses import CLAUDE
from stayfixed.memory import trust
from stayfixed.memory.index import (
    INDEX_NAME,
    index_source,
    reconcile,
    render_index,
    write_index,
)
from stayfixed.memory.store import (
    Store,
    in_repository,
    main_checkout,
    overlay_group_target,
    permitted_roots,
    resolve,
)
from stayfixed.trust.api import SandboxedWrite


class PartialLink(OSError):
    """An `OSError` part-way through `link`, carrying the links that were already made.

    Links are created one at a time, so a failure half way through leaves the tree holding
    some names and not the rest — and per this module's docstring above, a group missing from
    the tree is also missing from the floor the reference guard derives from it: invisible
    twice. The `SessionStart` handler degrades open, which is right (a memory handler never
    costs a session), but degrading open on a bare `OSError` threw `created` away with the
    exception, so nothing anywhere could say that half a tree existed.

    An `OSError` and not a `Refusal`: nothing crossed a boundary here, a write failed. A
    `PathEscape` from `contained` still leaves this function as itself, and the caller decides
    separately what a containment refusal means — see `stayfixed.memory.hooks`.
    """

    def __init__(
        self, created: Sequence[Path], cause: OSError, *, harness_refused: str | None = None
    ) -> None:
        super().__init__(str(cause))
        self.created = list(created)
        # `Links.harness_refused`, carried so a half-built tree does not lose it.
        self.harness_refused = harness_refused


def linked_names(config: Config) -> tuple[str, ...]:
    """Every name a worktree's link tree should hold: the index, then each configured group."""
    return (INDEX_NAME, *config.memory.groups)


def link_sources(overlay: Path, config: Config) -> tuple[Path, ...]:
    """Every path in the overlay an overlay-mode link tree points at, in `linked_names` order.

    `_link_source`'s rule, the one `attach_main` builds the tree by and `detach_main` reads it
    back by, applied to every name the tree holds. `attach` asks each of these paths, above its
    first write, whether a path that long can exist on this machine
    (`attach.binding.refuse_unless_share_can_exist`): the index's is where `_render_missing_index`
    writes the first index and every group's but the common one is a directory `attach` creates,
    so a project's share that fits while one of these does not ended the run in a `PartialLink`
    after every write before it. One list, so the check and the tree cannot come to disagree
    about which paths they are.
    """
    return tuple(_link_source(overlay, config.project.name, name) for name in linked_names(config))


def _link_source(overlay: Path, project: str, name: str) -> Path:
    """Where the link tree's entry `name` points in the overlay: the index inside this project's
    own store, and a group where `overlay_group_target` routes it. `attach_main` links the index
    at the `--store` it was handed, which it has just held to that same store (`permitted_roots`).
    """
    if name == INDEX_NAME:
        return permitted_roots(overlay, project)[1] / INDEX_NAME
    return overlay_group_target(overlay, project, name)


def harness_link_parts(worktree: Path, home: Path | None = None) -> tuple[Path, str]:
    """The home the harness link is under, and the link's path inside it.

    `home` is `--home`, or `config.machine.owner_home`; neither is anything the repository
    authored. A home that is not there is a refusal, for a user with none and an empty `HOME`.
    """
    base = owner_home() if home is None else home
    if base is None:
        raise Refusal(
            "HOME names no home directory, so there is nowhere to put the harness memory link; "
            "set HOME to your home directory and run this again"
        )
    # Read off the harness registry (`harnesses.CLAUDE.memory_dir`): the one harness whose memory
    # the store is linked into, whichever harnesses a project lists.
    return base, CLAUDE.memory_dir(str(worktree.resolve()))


def harness_memory_path(worktree: Path, home: Path | None = None) -> Path:
    """`~/.claude/projects/<slug>/memory`; the slug is the path with `/` and `.` as `-`."""
    root, relative = harness_link_parts(worktree, home)
    return root / relative


def harness_anchor(where: Path, home: Path | None) -> tuple[Path, str]:
    """`harness_link_parts` as the root the `O_NOFOLLOW` walk opens and the path below it.

    `~/.claude` is resolved once and is the root, since a stow- or chezmoi-managed one is the
    owner's link, and the walk follows no link below it; with no `.claude` yet the root is the
    home, resolved. The home is found and never created: one that is not a directory is a
    mistyped `--home`. Both are refused here, above every write, as is a root that is not a
    directory and a path below it the walk cannot open.
    """
    root, relative = harness_link_parts(where, home)
    if not fsops.is_dir(root):
        raise Refusal(
            f"{root} is not a directory, so there is nowhere to put the harness memory link; "
            f"stayfixed writes inside the home directory and never creates the home directory "
            f"itself, so it has to exist already"
        )
    first, _, below = relative.partition("/")
    claude = root / first
    try:
        if fsops.exists(claude) or fsops.is_symlink(claude):
            root, relative = fsops.resolved(claude), below
        else:
            root = fsops.resolved(root)
        if not fsops.is_dir(root):
            raise NotADirectoryError(errno.ENOTDIR, "it is not a directory")
        fsops.check_within(root, relative)
    except OSError as exc:
        raise Refusal(
            f"the harness memory link cannot be reached under {root}: {fsops.said(exc)}; "
            f"stayfixed follows the links up to `.claude` and none below it"
        ) from exc
    return root, relative


def _link(root: Path, relative: str, source: Path) -> bool:
    """Create or repair a symlink inside `root`; report whether it did anything.

    A real file or directory at the target is left alone (`readlink_within` raises
    `NotASymlink`). A symlink already pointing at `source` is left alone too — this is what
    makes linking twice a no-op. Everything else — nothing there, or a symlink pointing
    anywhere else, dangling included — is replaced.

    **Every hop goes through the `O_NOFOLLOW` walk, and that is the whole fix.** The old
    form asked `Path.exists()` and then wrote through the same `Path`: a component swapped
    for a symlink between the two questions redirected the link wherever the swapped
    component pointed, and `mkdir(parents=True)` created the directories to land it. Here the
    read, the removal and the creation each reach the entry through a descriptor the walk
    just opened, so there is no window between the check and the act. `root` is the
    containment anchor and never comes from the repository: it is the worktree `link` was
    handed, the checkout `attach_main` was handed, or the directory `~/.claude` resolves into
    (`harness_anchor`). `relative` is the half the repository can influence, and it is walked one
    component at a time.

    A `FileNotFoundError` from the read is "nothing is there": it means a directory above the
    target does not exist yet, which is the ordinary case on a first link — `symlink_within`
    creates those parents through the same walk. A root that is not there is refused before any
    of this (`harness_anchor`).
    """
    try:
        current = fsops.readlink_within(root, relative)
    except fsops.NotASymlink:
        return False  # a real file or directory is left alone
    except FileNotFoundError:
        current = None  # no directory above it yet; `symlink_within` makes them
    if current == source:
        return False
    if current is not None:
        fsops.unlink_within(root, relative)
    fsops.symlink_within(root, relative, source)
    return True


def _unlink(root: Path, relative: str, source: Path) -> bool:
    """Remove a symlink this module made; report whether it did anything.

    The mirror of `_link`, and deliberately narrower than it. Only a symlink whose own target
    is `source` is removed: a real file or directory is unmerged work or a store the harness
    created on its own, and a symlink pointing anywhere else belongs to somebody else — the
    same two things `_link` refuses to clobber. Withdrawing a link is not licence to delete a
    directory. A *dangling* link at `source` is still this module's own and still goes: what
    the gate refuses is the name, not the bytes behind it.

    `pointing_at` is what says "this module's own", and it is compared inside the walk rather
    than after it, so the link that is read is the link that is removed.

    A `FileNotFoundError` is "there is no such link": no directory above the target exists, so
    nothing at that name can be this module's to withdraw. Reporting it as a failure would
    turn every run on a machine with no `~/.claude/projects` into a `PartialLink`.
    """
    try:
        return fsops.unlink_within(root, relative, pointing_at=source)
    except fsops.NotASymlink:
        return False  # somebody else's file or directory is left standing
    except FileNotFoundError:
        return False  # no directory above the name, so there is no link of ours there
    except fsops.UnsafePath:
        return False  # a component that became a symlink after `harness_anchor` walked it


@dataclass(frozen=True)
class Links:
    """What `link` changed: the links it made, and the harness link it withdrew.

    Two lists and not one, because the caller says different things about them. `created` is
    "this worktree can now see the store"; `revoked` is "the harness can no longer see it,
    because the owner's approval has lapsed" — a security-relevant event, and the sort of
    thing this module's own history says must never be silent. A run that revokes reports no
    creations, so folding them together would render a revocation as "linked 1 path".
    """

    created: list[Path] = field(default_factory=list)
    revoked: list[Path] = field(default_factory=list)
    # The approval this run could not carry across the index it wrote, because the trust record's
    # directory refused the write as an agent's sandbox refuses one (`_render_missing_index`).
    refresh_refused: bool = False
    # Why `link` neither made nor withdrew the harness link: `harness_anchor`'s refusal, a fault
    # of the home's and not the worktree's, so it costs the harness link alone.
    harness_refused: str | None = None


def _tree_base(worktree: Path, store: Store) -> str | None:
    """The store's own place in the checkout, as a path **relative to the worktree**.

    A relative `str` and not an absolute `Path`, because the absolute form is precisely what a
    caller must not write through: `link` hands this to `fsops` as the first components of a
    path walked under `worktree` with `O_NOFOLLOW`, and a caller holding the joined path could
    only re-resolve it. The worktree is the containment anchor, and it comes from the hook or
    the command that named the checkout, never from the repository.

    Derived from `store`, never from `config.paths.memory`. Both halves of that matter. The
    value is repository-controlled and reaches no guard that resolves it — `validate_paths`
    passes `allow_final_symlink=True` for `memory` and `contained()` does not resolve a final
    component — so a committed symlink there loads without complaint, and the path-based
    directory creation this module used to do followed it out of the checkout onto any
    directory the author chose. And it is not even the right answer: `local-only`, the preset
    default, resolves the store at `.stayfixed/local/` and never consults `paths.memory`, so a
    tree built there landed where no reader looks and outside the `.gitignore` entry that mode
    relies on. The store already knows where it is.

    `None` means there is nothing to mirror: `--store` may point the store anywhere, and a
    store outside its own root has no counterpart position inside a worktree to build. That is
    a skip rather than a refusal — nothing escaped, there is simply no such directory — while a
    `relative` that leaves the worktree *is* a refusal, raised by `contained`.
    """
    try:
        relative = store.path.relative_to(store.root)
    except ValueError:
        return None
    if not relative.parts:
        return None
    # For the refusal and not for the path: `contained` is what makes an escape a `PathEscape`
    # — a `Refusal` — rather than the `UnsafePath` the walk below would raise, which
    # `stayfixed.memory.hooks` would catch as a `PartialLink` and report as "N links made".
    contained(worktree, str(relative))
    return str(relative)


def harness_link_needed(store: Store, config: Config) -> bool:
    """Whether `~/.claude/projects/<slug>/memory` may point at this store — asked in one place.

    `link` asks it for a worktree and `attach_main` asks it for the owning checkout, one spelling
    because the question is easy to ask slightly wrong and asking it wrong costs everything the
    gate was for: `repository_data=in_repository(store, store.path)` is what makes it a question
    about *the directory this link exposes* rather than about the notes behind it. Asked without
    that argument it falls through `inside_project(store)`, which is False in overlay mode by
    design while `store.path` is a real directory inside the repository — and a clone shipping a
    committed store then gets the link created for it on no trust record at all.
    """
    return trust.may_inject(store, config, repository_data=in_repository(store, store.path))


# `harness_gate`'s three answers. Not statuses and not sentences: each caller says its own.
GATE_OPEN = "open"
GATE_LAPSED = "lapsed"
GATE_UNAPPROVED = "unapproved"


def harness_gate(store: Store, config: Config) -> str:
    """`harness_link_needed`'s answer, and where it is no, why: `GATE_OPEN` where the harness link
    may point at this store; `GATE_LAPSED` where the machine records an approval for it and the
    store, or its `memory.index_extra`, has changed since (`trust.changed`); `GATE_UNAPPROVED`
    where none is recorded, which is a store never approved.

    Asked by `attach` and by its `doctor.py` to say which of the two closed gates it is, since
    both close the gate and only the second withdraws links a run before made: one line appended
    to one note is enough. One question and not two: the store is digested once, by the gate.
    A closed gate with a record behind it is a record the digest no longer matches, so whether
    one is recorded is the whole of the rest, and no second digest is taken to tell."""
    if harness_link_needed(store, config):
        return GATE_OPEN
    return GATE_LAPSED if trust.approval_recorded(store.path, store.machine) else GATE_UNAPPROVED


def _apply_harness_link(
    anchor: tuple[Path, str], store: Store, config: Config
) -> tuple[list[Path], list[Path]]:
    """Create or withdraw the harness memory link for one checkout; report which it did.

    One definition for `link` and `attach_main` both, and it earns its name three times over.
    This is the one hop that leaves this area's own channel, so it is the one place where asking
    the gate a slightly wrong question costs everything the gate was for. **The gate runs in
    both directions in the same call**, because a gate evaluated once over state that persists
    is not a gate: a `git pull` that adds a note lapses the record, every channel this area
    controls shuts, and an ungated withdrawal would leave the one it does not control pointing
    at the new bytes. And `_unlink` is deliberately narrower than `_link` — refusing to expose a
    directory is not licence to delete one.

    Three rules written down once and then copied is exactly how a pair stops agreeing, which is
    why they are not copied. `anchor` is `harness_anchor`'s answer, asked by the caller once.
    """
    root, relative = anchor
    harness = root / relative
    created: list[Path] = []
    revoked: list[Path] = []
    if harness_link_needed(store, config):
        if _link(root, relative, store.path.resolve()):
            created.append(harness)
    elif _unlink(root, relative, store.path.resolve()):
        revoked.append(harness)
    return created, revoked


def link(
    worktree: Path,
    store: Store,
    config: Config,
    *,
    home: Path | None = None,
) -> Links:
    """Create what is missing, withdraw what is no longer authorised, and report both.

    A no-op for the main checkout itself: it already holds the real store, not a link to it,
    so there is nothing for this function to do there. Validating a symlinked index in overlay
    mode (`index.index_source`) needs the machine file, and takes it from `store.machine`, so
    the two can no longer disagree about where the overlay is.

    Raises `PathEscape` rather than skipping when a name leaves the tree. Every `name` here is
    repository-controlled (`memory.groups` is an ordinary `stayfixed.toml` list, and it reaches no
    guard of its own), and `store.groups` was validated against the *main checkout's* tree — a
    worktree is a separate checkout of a separate branch, so its own copy of that subtree can hold a
    symlink the main one does not. Skipping one escaping name would leave the next name in the list
    free to try the same thing.

    **The harness link is the one hop that leaves stayfixed's gate, so it is the one that asks
    about trust.** Every link above lands inside the worktree, where the only reader is this
    area's own `bundles.blocks` — which calls `trust.may_inject` and wraps what it emits in
    `trust.wrap`'s nonce region. `~/.claude/projects/<slug>/memory` is read by the *harness's*
    native memory reader instead: whatever sits behind it reaches the model with no gate, no
    delimiter and no trust record. In `local-only` — the preset default — and in `in-repo` the
    store is content the clone shipped, so creating that link before the owner has said
    `stayfixed trust approve memory` hands repository-authored text to the model
    through a channel this area does not control.

    The condition is `trust.may_inject`, and it must be asked **about the directory this link
    exposes**, which is what `repository_data=in_repository(store, store.path)` says. Asked
    without that argument it fell through `inside_project(store)`, and in overlay mode that is
    False by design — every group resolves out into the overlay — while `store.path` is a real
    directory *inside the repository*. So a clone shipping a committed index at the configured
    memory path got the harness link created for it on no trust record at all, and the harness's
    own **native** memory reader then injected the file with no delimiter, no nonce and no gate.
    This area's own injection channel refused the file in the same session while `link` created
    the harness symlink: it would not inject the file through the channel it controls, and
    created the link to the channel it does not.

    A link to a directory exposes every file under it, so the question here is whether the
    **directory** is repository data, not whether the notes or the index are. `memory index
    --check` and `memory fit` warn by this same question, so a store whose link waits is a store
    they warn about.

    Nothing narrower than `may_inject` will do. It is already the predicate that means "these
    bytes may reach the model at all": it short-circuits to True when neither
    `inside_project(store)` nor `repository_data` holds — here, only a store whose directory is
    outside the repository — and otherwise it demands a digest that matches what the owner
    approved. So in overlay mode, where the store's directory is inside the repository, the
    link waits for `stayfixed trust approve memory` even when every note behind it is
    the machine owner's own; the bundles deliver those notes with no record, and the link does
    not. Gating on `inside_project` alone would ask the wrong question (it would refuse a
    trusted store for ever); gating on the mode would ask the clone.

    **The same gate runs in the other direction, in the same call.** Creation was gated and
    removal was not, so the link outlived the record that authorised it: `record`, then a
    `git pull` adding one note, and `state(...).trusted` is False, `blocks(...)` is `[]` —
    every channel this area controls correctly shut — while `~/.claude/projects/<slug>/memory`
    still pointed at the store the new note is in, and the harness's native reader still read
    it with no gate, no delimiter and no trust record. A gate asked once about state that
    persists is not a gate. `_unlink` is deliberately narrower than `_link`: only a symlink
    already pointing at this store is withdrawn, because refusing to expose a directory is not
    licence to delete one.

    Raises `PartialLink` — an `OSError` carrying the links already made — when a write fails
    part-way, rather than letting `created` die with the exception. The caller degrades open;
    it needs to be able to say which half of the tree exists while it does. The withdrawal is
    last, so a failure there carries out the creations and revokes nothing.

    **The tree's own base directory is created by the first link that goes into it, and not
    before.** It used to be created unconditionally, which meant a store whose groups all
    resolved to nothing still left the configured directory behind, empty, in every worktree a
    `SessionStart` touched. `symlink_within` creates a target's parents through the same
    `O_NOFOLLOW` walk that creates the link, so when `linked_names(config)` yields no source
    the base is not created at all.

    **A home the anchor refuses costs the harness link alone.** The tree's links are inside the
    worktree and do not depend on the home, so they are made whatever it says, and the anchor's
    refusal is returned in `harness_refused` rather than raised: no harness link is made and
    none is withdrawn under that home. Raised, it ended the call before the first note link.
    """
    if main_checkout(worktree).resolve() == worktree.resolve():
        return Links()
    anchor: tuple[Path, str] | None = None
    unreachable: str | None = None
    try:
        anchor = harness_anchor(worktree, home)
    except Refusal as refused:
        unreachable = str(refused)
    created: list[Path] = []
    revoked: list[Path] = []
    try:
        base = _tree_base(worktree, store)
        if base is not None:
            sources: dict[str, Path] = dict(store.groups)
            found = index_source(store, config)
            if found is not None:
                sources[INDEX_NAME] = found
            for name in linked_names(config):
                source = sources.get(name)
                if source is None:
                    continue
                # `allow_final_symlink`, because replacing a wrong or dangling symlink already
                # sitting at the target is this function's job; every level above it is not.
                target = contained(worktree / base, name, allow_final_symlink=True)
                if _link(worktree, f"{base}/{name}", source.resolve()):
                    created.append(target)
        if anchor is not None:
            made, withdrawn = _apply_harness_link(anchor, store, config)
            created += made
            revoked += withdrawn
    except OSError as exc:
        raise PartialLink(created, exc, harness_refused=unreachable) from exc
    return Links(created, revoked, harness_refused=unreachable)


def attach_main(
    root: Path,
    store_path: Path,
    config: Config,
    *,
    machine: Path | None = None,
    home: Path | None = None,
) -> Links:
    """Build the link tree in the checkout that owns the store, in overlay mode.

    The case `link` excludes. `link` is right that the main checkout "already holds the real store,
    not a link to it" in `local-only` and `in-repo`; in `overlay` mode the real store lives in the
    overlay and the checkout holds a tree of links, so the owning checkout needs an entry point of
    its own. It lives here rather than in `attach` because the two share `_link`, `_unlink` and the
    gate above, and a second copy of that gate in another area would be a trust check that can drift
    from the first.

    **It takes a `store_path` and not a resolved `Store`, because there is nothing to resolve
    yet:** in overlay mode `resolve()` reads the link tree, and the link tree is what this
    function creates. So the links come first and `resolve()` second, which is also why the
    harness link is last.

    The overlay root comes from `overlay_root(machine)` and never from `store_path`, and
    `store_path` is checked against `permitted_roots` rather than trusted — `attach` refuses the
    same store one layer up, and this is the floor under that.

    Raises `PathEscape` rather than skipping when a group name leaves the tree, for the reason
    `link` gives: `memory.groups` is repository-controlled and skipping one escaping name leaves
    the next free to try the same thing.
    """
    if config.memory.mode != OVERLAY_MODE:
        raise Refusal(
            f"memory.mode is {config.memory.mode!r}, so this repository holds its own store and "
            f"there is no tree of links to build; only an overlay-mode repository is attached"
        )
    overlay = overlay_root(machine)
    if overlay is None:
        raise Refusal(
            "no overlay root is recorded in the machine configuration, so there is nothing to "
            "link into; run `stayfixed setup` first"
        )
    if store_path.resolve() != permitted_roots(overlay, config.project.name)[1].resolve():
        raise Refusal(
            f"{store_path} is not this project's own share of the recorded overlay "
            f"({permitted_roots(overlay, config.project.name)[1]}); linking there would put "
            f"another project's notes into this session"
        )
    base = contained(root, config.paths.memory)
    created: list[Path] = []
    revoked: list[Path] = []
    try:
        # `mkdirs_within` creates a target's *parents* through the `O_NOFOLLOW` walk, so the
        # store directory is asked for as the parent of the index link that goes into it.
        fsops.mkdirs_within(root, f"{config.paths.memory}/{INDEX_NAME}")
        for name in linked_names(config):
            source = (
                store_path / INDEX_NAME
                if name == INDEX_NAME
                else overlay_group_target(overlay, config.project.name, name)
            )
            # `allow_final_symlink`, because replacing a wrong or dangling symlink already
            # sitting at the target is this function's job; every level above it is not.
            target = contained(base, name, allow_final_symlink=True)
            # The anchor is `root`, the checkout this command was pointed at, so the whole of
            # `config.paths.memory` — which the repository authors — is walked component by
            # component rather than joined and resolved. `open_within` applies `O_NOFOLLOW` to
            # every component below the anchor and never to the anchor itself, so the anchor
            # has to be the one value here the repository cannot choose.
            if _link(root, f"{config.paths.memory}/{name}", source):
                created.append(target)
        store = resolve(root, config, machine=machine)
        if store is None:
            raise Failure(
                "the link tree was created and the store still does not resolve; "
                "`stayfixed memory index --check` reports why"
            )
        refused = _render_missing_index(store, config)
        made, withdrawn = _apply_harness_link(harness_anchor(root, home), store, config)
        created += made
        revoked += withdrawn
    except OSError as exc:
        raise PartialLink(created, exc) from exc
    return Links(created, revoked, refresh_refused=refused)


def _render_missing_index(store: Store, config: Config) -> bool:
    """Put an index behind the link `attach_main` just made, when the store has none yet; whether
    the trust record refused the refresh as an agent's sandbox refuses a write.

    A first attach linked `<paths.memory>/MEMORY.md` at a file nothing had written, so every
    session read a dangling link and `memory index --check` failed until someone ran
    `memory index` by hand. This is that command's own render — `reconcile`, `render_index`,
    `write_index` — with the notes left as they are (`write=False`: an attach adds no `index:`
    line to a note), and trust carried across the one file it wrote, as `memory index` carries
    it. After the link and not before it: the link is what makes the render's destination the
    overlay's copy (`index._to_machine`), so a render taken before it could differ from the one
    `--check` compares against. Before the harness link and every worktree's tree, so neither
    ever sees the index missing.
    """
    if index_source(store, config) is not None:
        return False
    before = trust.snapshot(store, config)
    rendered = render_index(reconcile(store, config, write=False), config, store)
    written = write_index(store, config, rendered)
    # A refresh an agent's sandbox refused leaves the approval at the person's digest, which the
    # store no longer matches: the harness link's gate then reads it as lapsed and says so, so
    # attach carries on rather than stopping with half its links made, and says why it lapsed.
    try:
        trust.refresh_if_trusted(store, config, before, [written])
    except SandboxedWrite:
        return True
    return False


def _detach_source(config: Config, machine: Path | None, name: str) -> Path | None:
    """The one directory a link at `name` must point at to be this module's own, or `None`.

    `attach_main`'s own answer, read back: the index links to `store_path / INDEX_NAME` and a
    group links to `overlay_group_target(...)`, both inside `permitted_roots`. Deriving the
    expected target from the same two rules is what makes `detach_main` narrow — and it is also
    the whole of the mode check. Outside overlay mode, and on a machine that records no overlay
    root, there is no such rule, so there is no name in the tree this function may claim and
    `None` is the honest answer rather than a separate gate that could disagree with this one.
    """
    if config.memory.mode != OVERLAY_MODE:
        return None
    overlay = overlay_root(machine)
    if overlay is None:
        return None
    return _link_source(overlay, config.project.name, name)


def harness_targets(root: Path, owner: Path, config: Config) -> tuple[Path, ...]:
    """Every directory a harness memory link of `root`'s may point at and be stayfixed's: the
    owning checkout's `paths.memory`, resolved, and `root`'s own, once each.

    Two writers make that link and they do not agree. `attach` points every checkout's link at
    the owning checkout's tree (`attach.write._link_everywhere` hands `link` the owner's store),
    and the `SessionStart` re-link may point a worktree's at the worktree's own. So a reader that
    compared a link with `root`'s own tree alone never recognised the one `attach` made in a
    linked worktree: `detach` left it standing, dangling once the owner's tree went, and
    `doctor` called a normally attached worktree red. `detach_main` and `doctor`'s `attached` row
    both read through this one function, so the two cannot come to recognise different links.

    Both paths come from `paths.memory` under a checkout git named, never from a ledger: a
    ledger is a path a clone can commit, and a committed value must not steer a removal. Which
    of the two the writers should converge on is not decided here.

    **Every way the question fails is one refusal, a `PathEscape`, naming the checkout.** The
    owning checkout's `paths.memory` is one `root`'s own configuration never walked, so it is the
    one a directory that became a link reaches first; and `.resolve()` on a `paths.memory` that is
    a symlink loop raises `RuntimeError` up to Python 3.12 (3.13 reads the loop as the path it
    names). Each caller used to translate whichever of `PathEscape`, `PathUnasked`, `OSError` and
    `RuntimeError` it had met in its own words, or none: `doctor` called a loop "this check could
    not run", red, and `detach` an internal error. A final symlink at `paths.memory` is still
    followed, as `contained(..., allow_final_symlink=True)` allows everywhere a tree is read: the
    link tree is a directory of links, and a `paths.memory` that is itself a link to one is a
    layout the resolver reads too, so refusing it here alone would make `detach` refuse a checkout
    it attached.

    A checkout is the owner when the two resolve alike, as `doctor` compares them: `git` names the
    owner by its resolved path, and `--root` may spell the same checkout through a link.
    """
    found: list[Path] = []
    for checkout in (owner, root):
        target = _harness_target(checkout, config, owner=checkout.resolve() == owner.resolve())
        if target not in found:
            found.append(target)
    return tuple(found)


def _harness_target(checkout: Path, config: Config, *, owner: bool) -> Path:
    """`checkout`'s `paths.memory`, resolved, or the one `PathEscape` `harness_targets` promises.

    The checkout is named by its place — the main checkout, or a linked worktree — and never by
    its path, which says where this machine keeps it. `paths.memory` itself is printed: the loader
    holds it to `PATH_VALUE`, the grammar a value must match before a report may print it."""
    whose = "the main checkout's" if owner else "the linked worktree's"
    asked = f"where a harness memory link may point cannot be asked of {whose} paths.memory"
    value = config.paths.memory
    try:
        return fsops.resolved(contained(checkout, value, allow_final_symlink=True))
    except PathEscape as exc:
        raise PathEscape(f"{asked}: {exc}") from exc
    except OSError as exc:
        # A loop is `fsops.resolved`'s `ELOOP` on every interpreter, and said as what it is.
        if exc.errno == errno.ELOOP:
            raise PathEscape(f"{asked}: {value!r} is a symlink loop") from exc
        raise PathEscape(f"{asked}: {value!r} cannot be resolved ({fsops.said(exc)})") from exc


def detach_main(
    root: Path,
    config: Config,
    *,
    machine: Path | None = None,
    home: Path | None = None,
    targets: tuple[Path, ...],
    keep_tree: bool = False,
) -> Links:
    """Withdraw the link tree a checkout holds, and the harness link with it.

    The mirror of `attach_main`, and here for the same reason: `_unlink` is deliberately
    narrower than `_link` — only a symlink whose own target is this store is removed, because a
    real directory at one of these names is unmerged work or a store the harness made, and
    withdrawing a link is not licence to delete a directory. A second copy of that rule in the
    attach area is the duplication this module's own history argues against.

    **The loop applies that rule and not half of it.** It used to test `is_symlink()` alone and
    remove whatever stood at a configured group name, with no comparison against
    `overlay_group_target(...)` — so an owner who added a group and pointed that group's own
    name inside the store at a directory of their own lost that link, reported under `revoked`, on
    a command that promises to remove exactly what `attach` added. `attach_main` two functions
    above has always compared; the asymmetry was inside one module, one screen apart, under a
    docstring that states the rule it was not applying.

    The comparison is between *resolved* paths, because the two functions that build these trees
    spell the same directory differently: `attach_main` links `overlay_group_target`'s answer as
    written, and `link` links `source.resolve()`. A dangling link still matches, which is right
    — `_unlink` says so for the harness link, and what the withdrawal is about is the name, not
    the bytes behind it.

    The harness link goes first, because it is the one hop that leaves this area's gate, and it
    is compared against `targets`, the directories `harness_targets` names — the owning
    checkout's tree, where `attach` points it, and `root`'s own — rather than against what it
    happens to point at. The caller asks `harness_targets` and passes its answer, because asking
    it walks the owning checkout's `paths.memory`, which is not `root`'s, and a walk that refuses
    must refuse before the first withdrawal, not here (`attach.write.detach`). Its `<slug>`
    directory is removed only when the link in it was.

    `keep_tree` withdraws the harness link and leaves the link tree: the caller's answer for the
    owning checkout while another checkout's ledger still stands, since that checkout's harness
    link points at this tree (`attach.write.detach`).

    Takes a `Config` and not a `Store`: by the time a repository is detached its store may no
    longer resolve — that is half of what detaching means — so the tree is found where the
    configuration says it is and each name is removed only if it is one of ours. `machine` is
    what names the overlay, for the same reason `attach_main` takes it.

    **`config.memory.mode` is checked here and it does not refuse, and that asymmetry with
    `attach_main` two functions above is deliberate.** This module's own history argues against
    duplicated rules, so an asymmetry left unexplained would read as drift rather than as the
    decision it is. Three reasons it is the decision:

    - `attach_main` can refuse because refusing costs nothing: it runs before the first write,
      so an early exit leaves the repository as it was. `detach_main` cannot. By the time
      `attach.write.detach` reaches it, the recorded allow rules, the marked hook entries, the
      pointer key and the `.codex/rules/` files are already withdrawn — so a `Refusal` here
      strands a half-detached repository with its ledger still on disk, which is a worse state
      than the one the check would be protecting against.
    - An owner who switched `memory.mode` to `in-repo` *after* attaching still needs `detach` to
      withdraw what `attach` wrote. A refusal would take that away and leave them no command
      that puts the tree back.
    - And a mode check spelled as its own gate is a second rule that can disagree with this
      one. `_detach_source` makes the mode load-bearing instead: outside overlay mode there is
      no rule naming what a link at one of these names would have pointed at, so no name in the
      tree can be claimed, and the loop removes nothing. That is the same sentence as "only a
      symlink whose own target is this store", not a weaker second one.
    """
    base = contained(root, config.paths.memory, allow_final_symlink=True)
    revoked: list[Path] = []
    home_root, harness_relative = harness_anchor(root, home)
    harness = home_root / harness_relative
    if any(_unlink(home_root, harness_relative, target) for target in targets):
        revoked.append(harness)
    # The `<slug>` directory the link sat in, a name this run computed, when nothing else is in
    # it: the harness keeps its own transcripts there, and `rmdir` leaves a directory that holds
    # one. `OSError` covers "not empty", "not there" and a component the walk refuses.
    with contextlib.suppress(OSError):
        fsops.rmdir_within(home_root, str(PurePosixPath(harness_relative).parent))
    if keep_tree:
        return Links([], revoked)
    for name in linked_names(config):
        target = contained(base, name, allow_final_symlink=True)
        if not fsops.is_symlink(target):
            continue
        source = _detach_source(config, machine, name)
        if source is None:
            continue
        # Resolved against the link's own directory when it is relative: `Path.resolve()` on a
        # relative `readlink()` would answer against the process's working directory, which is
        # nothing to do with where the link stands. Nothing this module writes is relative; a
        # link somebody else wrote may be, and it is exactly the case that must not match.
        pointed = target.readlink()
        if not pointed.is_absolute():
            pointed = target.parent / pointed
        try:
            reached = fsops.resolved(pointed)
        except OSError:
            # A symlink loop at one of these names, which `fsops.resolved` answers as `ELOOP` on
            # every interpreter: a link that cannot be followed is not one this function can
            # claim, so it stays, as any other link to elsewhere does. Raised, it ended `detach` in
            # an internal error after the settings were withdrawn.
            continue
        if reached != source.resolve():
            continue
        # Through the `O_NOFOLLOW` walk, so a component that became a symlink after
        # `contained()` passed cannot redirect the removal out of the checkout.
        fsops.remove_within(root, f"{config.paths.memory}/{name}")
        revoked.append(target)
    return Links([], revoked)
