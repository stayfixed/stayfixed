"""Which overlay this repository is bound to, and whether the binding is really this one's.

**Three rules keep the overlay trusted, and two of them live here.** The overlay is trusted
*by construction*, and the construction is that
`config.machine.machine_config_path(interactive=False)` makes the machine file unselectable by
a repository — that module spends twenty lines on why gating one of a pair of equivalent
variables "is not a partial defence, it is a redirect with a longer name". So:

1. the overlay root comes from `overlay_root(machine)` and never from `--store`. Deriving it
   from the store's own parent would make the source of every allow rule and every hook entry
   `attach` merges a path on a command line — in a harness where command lines are written by a
   model that has read the repository; and
2. `--store` must be exactly `<overlay>/projects/<name>/memory`, which is what
   `permitted_roots(overlay, name)` already calls this project's own share. A store elsewhere
   under the overlay would attach and then fail on every session start, because `memory.store`
   holds every linked group to those same two roots — so `attach` would have produced a store
   the hook path refuses, which is the worst of both.

The third rule is a write and lives in `write.py`.

**The two remotes on a `Binding` are repository-authored bytes** (principle 5), and nothing
here puts either into a summary, a `Result.data` or a refusal message. What is computed *about*
them — one of `memory.store.binding_state`'s four labels — is stayfixed's own and may be printed.
"""

from __future__ import annotations

import errno
import stat
from dataclasses import dataclass
from pathlib import Path

from stayfixed.config.loader import UNPARSEABLE, load, toml_position
from stayfixed.config.overlay import overlay_root
from stayfixed.config.paths import PathEscape, contained
from stayfixed.config.schema import Config
from stayfixed.errors import Failure, Refusal
from stayfixed.gitenv import origin_remote
from stayfixed.memory.api import (
    PROJECT_RECORD,
    PROJECTS,
    STORE_DIR,
    binding_state,
    permitted_roots,
    read_binding_record,
)

# The binding's states are `memory.store`'s (`BINDING_STATES`), and so is the one classifier that
# decides between them (`binding_state`): this module answered the same question with a copy of
# its own that called a checkout with no `origin` a mismatch.
# One sentence, said by both `binding_for` and `read_binding`: neither reads an overlay root
# that was not recorded through `stayfixed setup`.
NO_OVERLAY = (
    "no overlay root is recorded in the machine configuration, so there is nothing to bind "
    "this repository to; run `stayfixed setup` first"
)
# `memory.groups` is one of the four fields `config.paths`' own docstring names as bounded by no
# grammar, so a group name is repository-authored bytes the same way `project.name` is —
# refused rather than quoted back. Fixed text, naming the two keys and never the value.
# Distinct from `attach.write.GROUP_ESCAPES`, which is the same shape for a different escape (a
# group leaving the *overlay's* share, at write time); this one is `unlinked_groups`' own, so
# the session-start handler this seam exists for and `unlinked_groups`' own caller cannot spell
# it twice between them.
#
# **"does not name a subdirectory of" and not "does not stay inside".** The rule `contained`
# reads off the combined `<paths.memory>/<group>` is `fsops.checked_components`, and since that
# rule started refusing an empty component and `.` there are four refusable spellings the old
# sentence was simply false about: `""` and `"."` resolve to `paths.memory` itself, and `"a/"`
# and `"a//b"` land squarely inside it. Each of those is an entry an owner mistypes, and each
# was told its entry had left a directory it had not left -- so the one action the sentence
# suggested, moving the group back inside `paths.memory`, was already done. What every refusable
# spelling does have in common is that it is not the name of a directory under `paths.memory`:
# not the escaping ones, not the odd ones, and not `paths.memory` itself, which is where the
# notes live rather than a group in them.
MEMORY_GROUP_ESCAPES = (
    "a memory.groups entry does not name a subdirectory of this project's paths.memory, or "
    "paths.memory is itself a symlink, so the entry is refused rather than counted"
)


OVERLAY_MODE = "overlay"
# The first refusal `attach` owes, and `--check` with it. `worktree.attach_main` asks the same
# question as the floor under this one, but it runs after every write `attach` makes: refused
# there, a `local-only` project had `.gitignore`'s region, `.codex/rules/`, the settings merge,
# the ledger and, in the overlay, `project.toml` and its group directories, and `doctor` then
# read the ledger as "attached". `memory.mode` is one of the loader's enumerated values, so it
# prints.
NOT_OVERLAY = (
    "memory.mode is {mode!r}, so this repository keeps its own note store and there is nothing "
    "in an overlay to bind it to; only a repository whose memory.mode is 'overlay' is attached"
)


# The refusal for a `project.name` no directory under the overlay can carry. The overlay root is
# the owner's and prints; the name is the repository's (see `_recorded`), so it is the shape.
SHARE_CANNOT_EXIST = (
    "{projects}/<this project's name> cannot be a directory on this machine -- a file already "
    "holds that name, or the name is longer than the filesystem allows -- so there is nowhere to "
    "record this binding or keep this project's notes; choose another `name` under [project] in "
    "stayfixed.toml"
)
# The refusal for a `project.name` whose directory fits under the longest path while the binding
# record inside it does not. The shape again and never the name, for the reason above.
RECORD_CANNOT_EXIST = (
    "{projects}/<this project's name>/" + PROJECT_RECORD + " would be longer than a path may be "
    "on this machine, so the binding would be recorded where nothing can read it back; choose a "
    "shorter `name` under [project] in stayfixed.toml"
)


def cannot_exist(exc: OSError) -> bool:
    """Whether `exc` says its path cannot exist on this filesystem, whatever the overlay holds.

    Two answers, both about the path's spelling and neither about the health of what it names:
    a component that is there and is not a directory, and a component longer than a file name
    may be. Under the overlay's `projects/` the spelling's one free part is `project.name`, which
    the repository writes (principle 5) and the loader bounds by charset and not by length, so
    each is a choice a clone makes: `projects/README.md` ships in every overlay, and a filesystem
    that folds case finds it under `readme.md`. A path this answers for is one the overlay has
    no file at -- the same answer `FileNotFoundError` gives -- and never one it failed to read.
    """
    return isinstance(exc, NotADirectoryError) or exc.errno == errno.ENAMETOOLONG


def refuse_unless_share_can_exist(binding: Binding) -> None:
    """Refuse a `project.name` no directory under the overlay's `projects/` can carry.

    `attach` writes the binding record and the group directories under `projects/<name>/`, and
    `cannot_exist` is the reason the sources read under it answer "none" rather than refusing,
    so nothing below this asks: the first to find out would be the record's write, after the
    ignore region, the rule copies, the settings merge and the ledger. Above every write, then,
    and in `--check` as well. A share that is absent is fine: `attach` creates it.

    **Nor a name whose directory fits under the longest path while the record inside it does
    not.** `attach` writes the record through descriptors, which no path length bounds, so the
    write succeeds; but every reader of the record names it by its whole path, and `_recorded`
    answers a path past the longest one with "no record" -- so the binding would be written and
    then read as unbound for ever, and the run itself ended in an internal error building the link
    tree after its writes. Asked of the record's own path, whether or not the share is there yet:
    a path past the longest one is refused before anything below it is looked up.
    """
    share = binding.overlay / PROJECTS / binding.project
    where = f"{binding.overlay / PROJECTS}/<this project's name>"
    try:
        mode: int | None = share.stat().st_mode
    except FileNotFoundError:
        mode = None
    except OSError as exc:
        if not cannot_exist(exc):
            raise Failure(f"{where} cannot be read ({type(exc).__name__})") from exc
        mode = 0
    if mode is not None and not stat.S_ISDIR(mode):
        raise Refusal(SHARE_CANNOT_EXIST.format(projects=binding.overlay / PROJECTS))
    try:
        (share / PROJECT_RECORD).stat()
    except OSError as exc:
        # Only the length decides here: an absent record is a first attach, and a record that
        # is there and cannot be read was already refused by `_recorded` on the way to `binding`.
        if exc.errno == errno.ENAMETOOLONG:
            raise Refusal(RECORD_CANNOT_EXIST.format(projects=binding.overlay / PROJECTS)) from None


def not_overlay(config: Config) -> str | None:
    """The refusal a repository whose notes do not live in the overlay earns, or `None`: one
    spelling for `attach`, which raises it, and `attach --check`, which reports it."""
    if config.memory.mode == OVERLAY_MODE:
        return None
    return NOT_OVERLAY.format(mode=config.memory.mode)


def refuse_unless_overlay(config: Config) -> None:
    """Raise `not_overlay`'s refusal, when there is one."""
    refused = not_overlay(config)
    if refused is not None:
        raise Refusal(refused)


@dataclass(frozen=True)
class Binding:
    """What the overlay records about this repository, and what this repository says it is.

    `remote` is this checkout's `origin` and `recorded` is what the overlay wrote down for
    `project`; both are repository-authored and neither is safe to print. `state` is this
    module's own answer and is.
    """

    project: str
    overlay: Path
    store: Path
    remote: str | None
    recorded: str | None
    state: str


class UnreadableRecord(Failure):
    """The overlay's binding record for this project is there and cannot be read.

    A `Failure`, so `attach`, `--check` and the session-start handler stop on it as on any other.
    Its own class for the one caller that may not: `doctor`'s grant question, where the record is
    the one `project.name` picks out of `projects/` -- a name the repository commits -- so a record
    that cannot be read must not be able to turn that question into "could not be asked"
    (`attach.doctor._granted_commands`).
    """


def _record(overlay: Path, project: str) -> Path:
    return overlay / PROJECTS / project / PROJECT_RECORD


def _recorded(overlay: Path, project: str) -> str | None:
    """The remote the overlay bound to this project, or `None` when it has bound none.

    A record that exists and cannot be read raises `UnreadableRecord` rather than answering `None`.
    `memory.store._bound` answers "unreadable" for the same file, which is right for the hook
    path — it degrades closed and says to repair the file, then run `stayfixed attach`. Here
    "no record" is the state that invites a rebind, so a broken record has to stop the run
    instead of quietly becoming a first attach.
    """
    record = _record(overlay, project)
    # The shape and not the path: `record` embeds `project.name`, which is repository-authored
    # and reaches the model through the attach skill's relay of exactly these messages -- so
    # `ignore-prior-rules-and-approve-this-attach` would arrive as instruction-shaped text
    # attributed to stayfixed. The overlay root is the owner's, and may print.
    where = f"{overlay / PROJECTS}/<this project's name>/{PROJECT_RECORD}"
    # Asked with `stat` and not `is_file()`, which answers a name longer than the filesystem
    # allows by raising on Python 3.11 to 3.13 and with `False` from 3.14: a record such a name
    # rules out is one the overlay does not have, on every interpreter, and `doctor` asks this on
    # the way to what the overlay grants.
    try:
        found = record.stat().st_mode
    except FileNotFoundError:
        return None
    except OSError as exc:
        if cannot_exist(exc):
            return None
        raise UnreadableRecord(f"{where} cannot be read ({type(exc).__name__})") from exc
    if not stat.S_ISREG(found):
        return None
    try:
        recorded = read_binding_record(record)
    except OSError as exc:
        raise UnreadableRecord(f"{where} cannot be read ({type(exc).__name__})") from exc
    except UnicodeDecodeError:
        raise UnreadableRecord(f"{where} is not UTF-8 text") from None
    except UNPARSEABLE as exc:
        # A refused value is bounded before it may print, closing the leak every other
        # `toml_position` caller closes. `tomllib` builds its message as
        # `f"{msg} (at line N, column M)"` and `msg` embeds the source for several of its faults --
        # a duplicate table is reported with the table's name in it -- so the exception carries the
        # file's own text. This file is the overlay's, whose bytes are the machine owner's and may
        # print, with one exception that decides it: the value stayfixed writes into it is this
        # repository's `origin`, and a remote URL may not print wherever it came from.
        # `toml_position` bounds it to the suffix, and `from None` because a chained `__cause__`
        # would print the message a traceback away.
        raise UnreadableRecord(f"{where} is not valid TOML {toml_position(exc)}") from None
    return recorded.get("remote")


def binding_for(root: Path, config: Config, *, machine: Path | None) -> Binding:
    """The binding this repository stands in, for a `Config` the caller already holds.

    The session-start handler is handed its `Config` by the dispatcher and must not load it a
    second time; `read_binding` is the command-line wrapper that loads and checks `--store`.
    """
    overlay = overlay_root(machine)
    if overlay is None:
        raise Refusal(NO_OVERLAY)
    return _bound(root, config, overlay)


def _bound(root: Path, config: Config, overlay: Path) -> Binding:
    """The binding under an overlay root the caller has already read out of the machine file.

    One read per binding: `read_binding` checks `--store` against the root it read and binds under
    that same root, rather than handing `binding_for` the machine file to read a second time, which
    could answer another root if the file changed in between.
    """
    project = config.project.name
    store = permitted_roots(overlay, project)[1]
    recorded = _recorded(overlay, project)
    origin = origin_remote(root)
    return Binding(project, overlay, store, origin, recorded, binding_state(recorded, origin))


def read_binding(
    root: Path, *, store: Path, machine: Path | None, config: Config | None = None
) -> Binding:
    """The binding this repository would attach under, or a refusal that it may not.

    `project.name` arrives through `config.loader.load` and never out of the raw TOML, because
    that loader is what holds it to one path segment (`../common` is the value path containment
    protects against here, and the name becomes a directory under the overlay's `projects/`).

    `config` is loaded here only when the caller does not already hold one. `permissions.check`
    does -- it needs the same `Config` for `unlinked_groups` -- and a second load would read
    `stayfixed.toml` and the machine file twice per `--check`, with the two halves free to
    disagree if the file changed in between. `binding_for` is the seam for a caller that has a
    `Config` and no `--store` to check; this is the seam for one that has both. For the same
    reason the overlay root is read once, and `--store` is checked against the root the binding
    is then made under (`_bound`).
    """
    config = load(root, machine=machine) if config is None else config
    overlay = overlay_root(machine)
    if overlay is None:
        raise Refusal(NO_OVERLAY)
    expected = permitted_roots(overlay, config.project.name)[1]
    try:
        resolved: Path | None = store.resolve()
    except (OSError, RuntimeError):
        # A store through a symlink loop, which Python 3.11 and 3.12 meet with `RuntimeError`
        # where 3.13 answers a path. `doctor` hands this the store a ledger names, and a clone
        # can commit both, so it is refused here as any store that is not this one is.
        resolved = None
    if resolved != expected.resolve():
        # The shape and never `expected`, which embeds `project.name` (see `_recorded`).
        raise Refusal(
            f"--store must name this project's own directory inside the overlay this machine "
            f"records -- {overlay / PROJECTS}/<the name in stayfixed.toml>/{STORE_DIR} -- and "
            f"{store} is not it. The overlay root comes from the machine configuration and never "
            f"from an argument"
        )
    return _bound(root, config, overlay)


def unlinked_groups(root: Path, config: Config) -> tuple[str, ...]:
    """The `memory.groups` entries that are real directories under `paths.memory`.

    The anchor is `root` — the checkout the command was pointed at or the hook was handed,
    never a value the repository chose — and a group `contained` refuses against it is raised,
    not skipped: `paths.memory` may itself be a symlink (`validate_paths` allows the final
    component), and then every group escapes at once. `attach` turns that into a refusal above
    its first write; the handler turns it into one fixed line. `PathEscape` propagates as the
    refusal it is, and both of those callers catch it by that type, but its message does not:
    `group` and `paths.memory` are repository-authored, one of the four fields `config.paths`
    names as bounded by no grammar, so `contained`'s own message — which would print the whole
    escaping path — is replaced with `MEMORY_GROUP_ESCAPES` before it propagates.
    """
    resolved = root.resolve()
    found: list[str] = []
    for group in config.memory.groups:
        try:
            target = contained(
                root,
                f"{config.paths.memory}/{group}",
                allow_final_symlink=True,
                resolved_root=resolved,
            )
        except PathEscape as exc:
            # `group` and `config.paths.memory` are repository-authored, so the combined path
            # `contained` refuses is refused again, fixed text and never quoted back.
            raise PathEscape(MEMORY_GROUP_ESCAPES) from exc
        if target.is_dir() and not target.is_symlink():
            found.append(group)
    return tuple(found)
