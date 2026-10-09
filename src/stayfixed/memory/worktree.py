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
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from stayfixed import fsops
from stayfixed.config.machine import anchor_home
from stayfixed.config.overlay import overlay_root
from stayfixed.config.paths import PathEscape, PathUnasked, contained
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

    def __init__(self, created: Sequence[Path], cause: OSError) -> None:
        super().__init__(str(cause))
        self.created = list(created)


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
    """The root the harness link is written under, and the link's path inside it.

    The root is `home` itself and the relative path is the whole of
    `.claude/projects/<slug>/memory`, so `mkdirs_within` creates every component through
    the `O_NOFOLLOW` walk — on a machine where `~/.claude/projects` does not exist yet
    (Codex-only, a fresh container) as much as on one where it does — and every component
    is inside the containment rather than resolved past it. A dotfiles layout that
    links `~/.claude` elsewhere is refused by that walk, and the refusal names the link;
    that is the same rule `setup` applies to `~/.claude/settings.json`, and `--settings`'s
    reason for existing.

    **Where the root comes from, because a containment rule that cannot say is not one.**
    `home` is the machine owner's own home directory: `config.machine.anchor_home`, which is
    `HOME` from a terminal and, everywhere else, the password database's entry, resolved once so
    that a home which is itself a symlink can be opened as a root, or a `--home` value only a
    person typing a command can supply. `HOME` alone was not that: direnv, mise or a
    devcontainer can set it from a file the clone commits, in a session no person is watching
    (Claude Code's `env` block cannot), and relative, it names a directory inside the clone. So
    the hook path never reads it. It is never read from `stayfixed.toml`, from a note, from a
    committed settings file or from anything else the repository authored, and the repository is
    the party being contained here:
    what it controls is `memory.groups` and `paths.memory`, which appear only in the *relative*
    half the walk refuses to follow out. The home directory itself is found and never created:
    `open_within` opens the root, and every component below it, without following a link, so
    the database's answer is resolved once before the walk while a `HOME` or `--home` that is
    itself a link fails at it; an anchor stayfixed made up would be an anchor the walk cannot
    vouch for — and a user the password database lists no home for has no anchor off a
    terminal, nor at one where `HOME` is unset, which is a refusal here.
    """
    base = anchor_home() if home is None else home
    if base is None:
        raise Refusal(
            "the password database lists no home directory for this user, so there is nowhere "
            "to put the harness memory link; at a terminal, set HOME to name one"
        )
    # Read off the harness registry (`harnesses.CLAUDE.memory_dir`): the one harness whose memory
    # the store is linked into, whichever harnesses a project lists.
    return base, CLAUDE.memory_dir(str(worktree.resolve()))


def harness_memory_path(worktree: Path, home: Path | None = None) -> Path:
    """`~/.claude/projects/<slug>/memory`; the slug is the path with `/` and `.` as `-`.

    The read-side name, defined as the join of `harness_link_parts` rather than as a second
    spelling of it, so the path `doctor` reports on and the path the walk writes cannot
    disagree.
    """
    root, relative = harness_link_parts(worktree, home)
    return root / relative


def harness_anchor(where: Path, home: Path | None) -> tuple[Path, str]:
    """`harness_link_parts`, with every structural refusal made a refusal instead of an errno.

    The anchor is found and never created — `harness_link_parts` says why — so a home
    directory that is not there is a mistyped `--home` and not a tree to build. Saying so is
    the whole of what that decision buys, and without this line neither direction said it:

    * Creating, the walk raised a bare `FileNotFoundError` from `os.open(root)`. `link`
      wrapped it as a `PartialLink`, and `stayfixed.memory.hooks` rendered that as "0 links
      made" with the home path nowhere in the message — an error where a refusal belongs
      (exit 2, not 1), and one that never said what was wrong.
    * Withdrawing, `_unlink` caught the same errno and answered `False`, so `detach` against a
      wrong `--home` reported "nothing to withdraw" and exited 0. An anchor that is not there
      reading as success is the worse half: it is the one case where the caller would act on
      the answer.

    `is_dir()` and not `exists()`: a home whose *parent* is a symlink (`/home` linking to a
    volume) is the ordinary case and is fine, since the walk opens the root by its whole path. The
    root itself is opened with `O_NOFOLLOW` like every component below it — `.claude` included —
    so a home that is *itself* a symlink fails at the walk. That is why the password database's
    answer is resolved before it is used as a root (`config.machine.anchor_home`); a `--home`, or
    `HOME` at a terminal, that names a symlink fails there as it did in the release before. The
    rule below the root is the one `setup` applies to `~/.claude/settings.json`.
    """
    root, relative = harness_link_parts(where, home)
    if not fsops.is_dir(root):
        raise Refusal(
            f"{root} is not a directory, so there is nowhere to put the harness memory link; "
            f"stayfixed writes inside the home directory and never creates the home directory "
            f"itself, so it has to exist already"
        )
    try:
        contained(root, relative, allow_final_symlink=True)
    except PathUnasked as exc:
        raise Refusal(
            f"the harness memory link cannot be reached: {exc}; run again once that directory "
            f"can be read"
        ) from exc
    except PathEscape as exc:
        # `allow_final_symlink=True`, because the final component is the link this module
        # makes and removes; `open_within` applies `O_NOFOLLOW` to every component *above* it
        # and never opens it, so this asks the walk's own question and not a stricter one.
        raise Refusal(
            f"the harness memory link cannot be reached: {exc}, and stayfixed follows no "
            f"symlink below {root}. Make that component a real directory and have your "
            f"dotfiles manager adopt the files inside it, or run from a home directory whose "
            f"`.claude` is real — the same rule `stayfixed setup --settings` states for the "
            f"settings file"
        ) from None
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
    handed, the checkout `attach_main` was handed, or the machine owner's home directory
    (`harness_link_parts`). `relative` is the half the repository can influence, and it is
    walked one component at a time.

    A `FileNotFoundError` from the read is "nothing is there": it means a directory above the
    target does not exist yet, which is the ordinary case on a first link — `symlink_within`
    creates those parents through the same walk. A missing *root* is not created: see
    `harness_link_parts`.
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
        # A component the walk refuses, which is the third thing there is no link of ours
        # behind. `harness_anchor` asks the same question above every write and every
        # withdrawal, so this is the race and not the layout: a component that became a
        # symlink after that check. Degrading the way the two arms above degrade is what keeps
        # one checkout's odd home from being a `detach` that cannot finish.
        return False


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
    # The harness link this store is approved for, not made because the caller said not to make
    # one (`Withhold`): a third thing to say, since the harness cannot see the store.
    withheld: bool = False


@dataclass(frozen=True)
class MakeUnder:
    """`link` makes the harness link under `home`, the machine owner's home directory, or
    `config.machine.anchor_home`'s answer where it is `None` (`harness_link_parts` says why)."""

    home: Path | None = None


@dataclass(frozen=True)
class Withhold:
    """`link` makes no harness link, for a caller whose only trusted home is not the one the
    harness reads (`memory.hooks`): a link made there is a link nothing sees. A link under `under`
    that points at a store whose approval has lapsed is still withdrawn, where the caller names a
    home (`_withdraw_lapsed`)."""

    under: Path | None = None


# `link`'s default: the harness link made under the machine owner's home.
_OWNER_HOME = MakeUnder()


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

    `link` asks it for a worktree, `attach_main` asks it for the owning checkout, and `attach`
    asks it again before taking its settings-file fallback. Three callers and one spelling,
    because the question is easy to ask slightly wrong and asking it wrong costs everything the
    gate was for: `repository_data=in_repository(store, store.path)` is what makes it a question
    about *the directory this link exposes* rather than about the notes behind it. Asked without
    that argument it falls through `inside_project(store)`, which is False in overlay mode by
    design while `store.path` is a real directory inside the repository — and a clone shipping a
    committed store then gets the link created for it on no trust record at all.
    """
    return trust.may_inject(store, config, repository_data=in_repository(store, store.path))


def _apply_harness_link(
    where: Path, store: Store, config: Config, home: Path | None
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
    why they are not copied.
    """
    root, relative = harness_anchor(where, home)
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
    harness: MakeUnder | Withhold = _OWNER_HOME,
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
    `stayfixed memory trust --in-repo-memory` hands repository-authored text to the model
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
    link waits for `stayfixed memory trust --in-repo-memory` even when every note behind it is
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

    `harness` says what becomes of the harness link: made under a home (`MakeUnder`), or not made
    (`Withhold`), when the tree's links are made and `withheld` reports whether the store is
    approved for one, and a lapsed link under the home `Withhold` names is withdrawn, which
    `revoked` reports.
    """
    if main_checkout(worktree).resolve() == worktree.resolve():
        return Links()
    # Above the loop, for the reason `attach` hoists the same call above its own first write:
    # the anchor is the one question here that can refuse, and discovered from inside
    # `_apply_harness_link` it was discovered *after* the note links were made. On the
    # ordinary stow / chezmoi / synced home that left three links in the worktree and no way
    # to take them out — `detach_main` refuses above every withdrawal, correctly, so no
    # shipped command will. `SessionStart` then caught the `Refusal` and told the model the
    # notes were not linked while they were.
    #
    # Below the early return and never above it. On the main checkout `link` does nothing at
    # all, so asking the question there would start refusing a call that has no write to put
    # the refusal in front of. `_apply_harness_link` asks the same question again as its first
    # statement, above its own gate, which is what keeps it correct when `attach_main` calls
    # it on its own; asked twice, it is the same answer.
    if isinstance(harness, MakeUnder):
        harness_anchor(worktree, harness.home)
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
        if isinstance(harness, Withhold):
            approved = harness_link_needed(store, config)
            if not approved and harness.under is not None:
                revoked += _withdraw_lapsed(worktree, store, harness.under)
            return Links(created, revoked, withheld=approved)
        made, withdrawn = _apply_harness_link(worktree, store, config, harness.home)
        created += made
        revoked += withdrawn
    except OSError as exc:
        raise PartialLink(created, exc) from exc
    return Links(created, revoked)


def _withdraw_lapsed(where: Path, store: Store, home: Path) -> list[Path]:
    """Remove the harness link under `home` that points at `store`, for a store not approved.

    `home` is one this module makes nothing under, so the narrowest withdrawal there is: only a
    symlink whose own target is this store goes (`_unlink`), a link to anything else is left
    standing, a relative `home` is ignored, and an anchor `harness_anchor` refuses is passed over
    rather than refused, because a hook never costs a session for a home it does not trust. So is
    one the walk cannot open — a `home` that is itself a symlink, which the walk never follows,
    or one it may not search — rather than reported as a link that could not be made.
    """
    if not home.is_absolute():
        return []
    try:
        root, relative = harness_anchor(where, home)
        removed = _unlink(root, relative, store.path.resolve())
    except (Refusal, OSError):
        return []
    return [root / relative] if removed else []


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
        _render_missing_index(store, config)
        made, withdrawn = _apply_harness_link(root, store, config, home)
        created += made
        revoked += withdrawn
    except OSError as exc:
        raise PartialLink(created, exc) from exc
    return Links(created, revoked)


def _render_missing_index(store: Store, config: Config) -> None:
    """Put an index behind the link `attach_main` just made, when the store has none yet.

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
        return
    before = trust.snapshot(store, config)
    rendered = render_index(reconcile(store, config, write=False), config, store)
    written = write_index(store, config, rendered)
    trust.refresh_if_trusted(store, config, before, [written])


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


def detach_main(
    root: Path, config: Config, *, machine: Path | None = None, home: Path | None = None
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
    is compared against the store directory rather than against what it happens to point at.

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
      fallback key and the `.codex/rules/` files are already withdrawn — so a `Refusal` here
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
    if _unlink(home_root, harness_relative, base.resolve()):
        revoked.append(harness)
    # The `<slug>` directory the link sat in, a name this run computed, when nothing else is in
    # it: the harness keeps its own transcripts there, and `rmdir` leaves a directory that holds
    # one. `OSError` covers "not empty", "not there" and a component the walk refuses.
    with contextlib.suppress(OSError):
        fsops.rmdir_within(home_root, str(PurePosixPath(harness_relative).parent))
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
        if pointed.resolve() != source.resolve():
            continue
        # Through the `O_NOFOLLOW` walk, so a component that became a symlink after
        # `contained()` passed cannot redirect the removal out of the checkout.
        fsops.remove_within(root, f"{config.paths.memory}/{name}")
        revoked.append(target)
    return Links([], revoked)
