"""File a new entry, or move one to a free identifier taking every reference along."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

from stayfixed import fsops
from stayfixed.gitenv import NO_ANSWER, QUERY_TIMEOUT_SECONDS, git_run, in_work_tree
from stayfixed.identifiers import DIGITS
from stayfixed.ledger.entries import (
    ID_LINE,
    Entry,
    LedgerError,
    entry_dir,
    field_line,
    load_entries,
    parse_entry,
    quote,
    read_ledger_text,
    related_field,
    scalar,
)
from stayfixed.ledger.index import index_path, index_text, refuse_index_overwrite, render_index
from stayfixed.ledger.register import Register
from stayfixed.ledger.scan import citation_roots, scannable
from stayfixed.printed import quoted

if TYPE_CHECKING:
    from stayfixed.config.schema import Config

# Bound on the pre-allocation `git fetch`: an offline machine or a stalled remote must not hang
# `new`, and a skipped fetch is reported rather than silent. A named cap
# (CONTRIBUTING.md#named-caps), and no shipped file changes with it.
FETCH_TIMEOUT_SECONDS = 10

# What `renumber` says of an occupied target it cannot tell from this move half-done. Built from
# the two identifiers alone, which the identifier grammar has held, and the register's command
# group, which is stayfixed's: nothing the repository wrote reaches the line.
# `{why}` is empty, or `LINE_BREAKS_ONLY` when those are the only difference: an end-of-file
# fixer's newline is invisible in an editor, and the remedy is then one keystroke.
OCCUPIED = (
    "{new} already has an entry file that is not this move half done{why}; pick a free "
    "identifier, or, if an interrupted `stayfixed {name} renumber {old} {new}` wrote it and it was "
    "edited since, make it {old}'s text again with only its `id:` line changed and run this again"
)
LINE_BREAKS_ONLY = " — it differs from {old}'s moved text only in the line breaks at its end"
# What `renumber` says of a write of its own that failed. Whichever write it was, running the same
# move again once the file can be written finishes it, since a re-run makes only the writes still
# missing; the move's own failure, exit 1, and never an internal error that names no way on.
UNFINISHED = (
    "the move is not finished: {path} could not be written ({reason}); once it can be, run "
    "`stayfixed {name} renumber {old} {new}` again to finish it"
)
# What `new` says of an index it could not write after filing the entry. The entry is on disk by
# then, so running `new` again files the same report twice; `index` writes the index and files
# nothing. Built as `UNFINISHED` is: the paths are the register's, root-relative through `quoted`.
FILED_UNINDEXED = (
    "filed {path}, but {index} could not be written ({reason}); once it can be, run "
    "`stayfixed {name} index`, not this command again, which would file it a second time"
)
_VOID_BODY = """
Renumbered to [{new}]({new}.md) to resolve an identifier collision. The number stays
occupied so a reference written before the repair still lands on an explanation.
"""


@dataclass(frozen=True)
class Allocation:
    identifier: str
    warning: str | None


@dataclass(frozen=True)
class Filed:
    path: Path
    identifier: str
    warning: str | None


@dataclass(frozen=True)
class Unswept:
    """A file the sweep could not rewrite: its repo-relative path and why, the two fields
    `--json`'s `unswept` carries per file.

    Two fields and never one `"path: reason"` string, because a path may itself hold `": "`, so
    no reader could split such a string back into the two. The reason names no absolute path
    (`fsops.said`); a refusal of stayfixed's own may repeat the root-relative path."""

    path: str
    reason: str


@dataclass(frozen=True)
class Renumbered:
    void: Path
    unswept: tuple[Unswept, ...]
    # False for a re-run of a move that had already finished, which wrote nothing.
    moved: bool = True


def _fetch(root: Path) -> str | None:
    """Best-effort, bounded; a skipped fetch says so rather than let a collision pass."""
    # Refs are all the allocator reads, so it fetches no submodule: under git's default
    # `fetch.recurseSubmodules=on-demand` the fetch would also ask the remote of each populated
    # submodule whose recorded commit it brings in, a destination of its own whose failure fails
    # the whole fetch.
    code, _ = git_run(
        root,
        "fetch",
        "--quiet",
        "--no-recurse-submodules",
        "origin",
        timeout=FETCH_TIMEOUT_SECONDS,
    )
    if code == 0:
        return None
    # `-1` is every cause `NO_ANSWER` names, not one of them: the warning says which question
    # went unanswered and does not guess why.
    cause = (
        f"{NO_ANSWER}, so git fetch origin gave no answer"
        if code < 0
        else "git fetch origin failed"
    )
    return f"{cause}; identifiers may collide with branches this checkout has not fetched"


def next_identifier(root: Path, register: Register, *, fetch: bool = True) -> Allocation:
    """`1 + max` over every identifier this repository can see: the working tree by filename
    and by `id:` (either alone leaves an occupied number invisible), and every entry ever added
    on any ref.

    Two sources, each one process. The working tree is read twice over because an entry whose
    filename and `id:` disagree is a defect `check` reports and a human repairs, but until
    they do, an id-only reader hands out the number of a file that already exists — and the
    write that follows lands on it. The other source already counts by filename, so this is
    one rule everywhere rather than a new one.
    """
    warning = _fetch(root) if fetch else None
    ids = register.ids
    directory = entry_dir(root, register)
    numbers: set[int] = set()
    if fsops.is_dir(directory):
        numbers.update(entry.number for entry in load_entries(root, register))
        numbers.update(
            ids.number(path.stem)
            for path in directory.glob(f"{ids.prefix}-*.md")
            if ids.is_identifier(path.stem)
        )
    # Built from the register's directory like every other path here: spelled literally, a
    # rename would make the allocator silently under-count and hand out a number some ref
    # already holds.
    tracked = f"{register.directory}/"
    # Quoting forced on, so under an owner's `core.quotePath=false` a name in this history that
    # is not UTF-8 still comes back as ASCII, whatever decodes it; `git_run` reads the raw bytes
    # losslessly too, so this is the second of two holds and not the only one. An entry's own
    # name is ASCII, so quoting changes none of the names this counts.
    code, added = git_run(
        root,
        "-c",
        "core.quotePath=true",
        "log",
        "--all",
        "--diff-filter=A",
        "--format=",
        "--name-only",
        "--",
        tracked,
        timeout=QUERY_TIMEOUT_SECONDS,
    )
    if code != 0:
        warning = _joined(warning, _uncounted(root, code))
    numbers.update(
        int(m)
        for m in re.findall(
            rf"{re.escape(tracked)}{re.escape(ids.prefix)}-({DIGITS})\.md",
            added if code == 0 else "",
        )
    )
    return Allocation(ids.format(max(numbers, default=0) + 1), warning)


def _uncounted(root: Path, code: int) -> str | None:
    """What an unread history costs the allocator, or `None` where there is no history to miss.

    A failed log was an empty one, so every entry another ref holds went uncounted with no
    word. Where no `.git` entry exists there is no history at all, which is not a miss: `bugs
    new` in a directory git does not know stays one line. That is read off the disk
    (`gitenv.in_work_tree`), because git refuses a question about a checkout it will not read —
    dubious ownership, a worktree whose gitdir is gone — the same way it refused the log, and
    asking it again read that repository as none. Every other failure is a miss, and says so.
    """
    if not in_work_tree(root):
        return None
    cause = NO_ANSWER if code == -1 else f"git log exited {code}"
    return (
        f"{cause}, so entries on other refs were not counted; identifiers may collide with "
        "numbers the history holds"
    )


def _joined(first: str | None, second: str | None) -> str | None:
    return "; ".join(part for part in (first, second) if part) or None


def _write_index(root: Path, register: Register) -> None:
    rendered = render_index(load_entries(root, register), register)
    if index_text(root, register) != rendered:
        fsops.write_within(root, register.index, rendered)


def file_entry(
    root: Path,
    register: Register,
    *,
    title: str,
    values: Mapping[str, str],
    related: tuple[str, ...] = (),
    today: str = "",
    fetch: bool = True,
) -> Filed:
    """File a new entry: allocate the next free identifier, write its entry, regenerate the index.

    `values` holds the keys the register's template leaves a whole `key: value` line for
    (`Schema.line_keys`) — for the bug ledger `severity`, `area` and `source`; a key left out is
    written bare. A key the template has no line for is a `ValueError`, the caller's mistake: it
    would otherwise be dropped in silence, since `str.format` ignores a keyword it has no field
    for.

    Every failure is raised before anything reaches disk: a rejected input leaves the tree
    exactly as it was, with no half-filed entry and no allocated-but-unused number. A level
    outside the vocabulary, an index that must not be regenerated over, an identifier whose
    file already exists and frontmatter the reader would reject are all rejected here.

    `fetch` is the one knob a caller turns off: the allocator asks the network what other
    branches hold, which tests and offline use skip.
    """
    schema = register.schema
    unlined = sorted(set(values) - set(schema.line_keys))
    if unlined:
        raise ValueError(
            f"the {register.name} register's template has no line for {', '.join(unlined)}"
        )
    if values.get(schema.level, "") not in schema.levels:
        raise LedgerError(f"--{schema.level} must be one of {', '.join(schema.levels)}")
    # Asked before allocating, not left to the `_write_index` call at the end: filing an entry
    # must not be what destroys a ledger, and refusing here leaves no half-filed entry behind.
    refuse_index_overwrite(root, register, index_text(root, register))
    allocation = next_identifier(root, register, fetch=fetch)
    identifier = allocation.identifier
    relative = f"{register.directory}/{identifier}.md"
    path = root / relative
    # The allocator reads what this repository can see, which is not the same question as
    # whether the file is there: it cannot see a branch this checkout never fetched (`_fetch`
    # says so when it fails), and `--root` need not be a git checkout at all. What it would
    # overwrite is the only copy of a bug report, so the file's existence decides — the same
    # refusal `renumber` makes about its target.
    if fsops.exists(path):
        raise LedgerError(
            f"{identifier} was allocated but {relative} already exists; nothing was written. "
            f"Run `stayfixed {register.name} check`: an entry file the allocator cannot account "
            "for is one this ledger is wrong about."
        )
    text = _scaffold(
        register,
        identifier=identifier,
        title=title,
        values=values,
        related=related,
        today=today or date.today().isoformat(),
    )
    # Validated the same way any other entry file is, before it touches disk: a malformed field
    # must fail cleanly here rather than be written and then fail the index re-render below,
    # leaving a broken entry file that every later `index`, `check` and `new` also fails on.
    parse_entry(text, path=Path(relative), register=register)
    fsops.write_within(root, relative, text)  # creates the ledger directory on the first entry
    try:
        _write_index(root, register)
    except OSError as error:
        unindexed = FILED_UNINDEXED.format(
            path=quoted(relative),
            index=quoted(register.index),
            reason=fsops.said(error),
            name=register.name,
        )
        # The allocator's warning too, as a filing that succeeds says it: a number that may be
        # taken on a branch this checkout has not fetched is what the operator acts on next.
        warned = f"{unindexed}; {allocation.warning}" if allocation.warning else unindexed
        raise LedgerError(warned) from error
    return Filed(path, identifier, allocation.warning)


def _scaffold(
    register: Register,
    *,
    identifier: str,
    title: str,
    values: Mapping[str, str],
    related: tuple[str, ...],
    today: str,
) -> str:
    """The entry `new` writes: the register's template, each key `values` holds on its own line
    (a key it leaves out written bare), and the number, title, day and related list filled in."""
    lines = {key: field_line(key, values.get(key, "")) for key in register.schema.line_keys}
    return register.schema.template.format(
        identifier=identifier,
        title=scalar(title),
        today=today,
        related=related_field(related),
        **lines,
    )


def _endpoints_written(
    register: Register,
    source_text: str,
    source: Entry,
    moved: str,
    target: Path,
    *,
    old: str,
    new: str,
) -> int:
    """How many of its two endpoint writes an interrupted run of this same move made — 0 when
    the target is free — or the occupied-target refusal.

    There is no journal, and each write is atomic on its own, so a kill between two of them
    leaves one of two states, and each is told by the bytes alone. Killed after the first write,
    the target is exactly the old entry's text with its `id:` line rewritten while the old file
    is untouched, and finishing leaves it as it is. Killed after the second, the old file is,
    byte for byte, the void pointer this move writes toward this target — its title only held to
    start as the move writes it, since the target may be retitled since, and its date its own.
    A finished move leaves that state too; `renumber` tells the two apart by the index, the
    move's last write. Anything else at the target is an entry of its own, which the move would
    destroy, and is refused as it always was, saying how to finish by hand a move whose target
    was edited after the kill. A symlink there is refused before it is read, as anything but a
    regular file is: the move writes its target, it never adopts one.
    """
    if not fsops.exists(target):
        return 0
    occupied = LedgerError(OCCUPIED.format(old=old, new=new, name=register.name, why=""))
    if fsops.is_symlink(target) or not fsops.is_file(target):
        raise occupied
    held = read_ledger_text(target, where=Path(register.directory) / f"{new}.md")
    if held == moved:
        return 1
    if held.rstrip("\r\n") == moved.rstrip("\r\n"):
        why = LINE_BREAKS_ONLY.format(old=old)
        raise LedgerError(OCCUPIED.format(old=old, new=new, name=register.name, why=why))
    # The pointer this move writes, rebuilt with the title and the date it carries and compared
    # byte for byte, its title held only to the prefix the move writes: the target's own title is
    # the owner's to change after the move, and a pointer rebuilt from it stopped matching then. A
    # pointer anyone wrote by hand toward a genuine `new`, and a live entry that merely relates to
    # it, still differ from it in their other bytes — the status, the related list, the body.
    if not source.title.startswith(f"renumbered to {new} — "):
        raise occupied
    schema = register.schema
    day = next((source.fields.get(key, "") for key in schema.dates if key in schema.required), "")
    pointer = _void_pointer(register, old=old, new=new, title=source.title, today=day)
    if source_text == pointer:
        return 2
    raise occupied


def _void_pointer(register: Register, *, old: str, new: str, title: str, today: str) -> str:
    """The entry `renumber` leaves at `old`: the register's void status, the day of the move for
    each date every entry must carry, and `new` in `related`, in the order the schema's keys
    run. `Schema` refuses a register that requires any other key, which this could not fill."""
    schema = register.schema
    lines = {
        "id": f"id: {old}",
        "title": f"title: {quote(title)}",
        "status": f"status: {schema.void}",
        "related": f"related: [{new}]",
    }
    lines.update((key, f"{key}: {today}") for key in schema.dates if key in schema.required)
    frontmatter = "\n".join(lines[key] for key in schema.keys if key in lines)
    return f"---\n{frontmatter}\n---\n{_VOID_BODY.format(new=new)}"


def renumber(
    root: Path, config: Config, register: Register, old: str, new: str, *, today: str = ""
) -> Renumbered:
    """Move an entry to a free identifier, taking every reference to it along.

    Every check that can reject the call runs before any file is touched. Both endpoints are
    written before the slow sweep, so an interruption leaves the old identifier resolving to
    the void pointer rather than to nothing. Both files are excluded from the sweep itself: the
    moved entry's prose is the operator's to rewrite, not the sweep's, and the void pointer's
    own `id:` line would otherwise be corrupted by the substitution it exists to survive.

    A text file the sweep cannot read, or cannot write back, is not silently skipped: once the
    void pointer exists, `check.register_gate`' `known` set makes a stale `old` mention in that file
    look intentional forever, and it will never be reported as dangling again. So a file the
    sweep could not touch is collected and returned, and the command fails, rather than
    claiming a rewrite it did not fully deliver. A file that is not text at all is a different
    thing and is skipped in silence, exactly as the scan skips it: it holds no identifier to
    rewrite, and reporting one would fail this command on any repository tracking one image.

    A run killed part-way is finished by running the same move again (`_endpoints_written`): it
    skips the endpoint writes already on disk and makes the rest, so the tree it leaves is the
    one an uninterrupted run would have left — when resumed the same day, since a pointer still
    to be written carries the day it is written. A re-run of a move that finished, told by its
    fresh index, writes nothing and says so (`moved` is False). Refusing these re-runs, as the
    occupied-target check once did, left a half-moved ledger nothing could finish.
    """
    ids = register.ids
    if not (ids.is_identifier(old) and ids.is_identifier(new)):
        raise LedgerError(f"both identifiers must look like {ids.shape}")
    # Before anything is read: with the two the same, the target is the source, which is exactly
    # its own text with its `id:` line rewritten, and `_endpoints_written` would read it as a move
    # killed after its first write, so the entry would be overwritten with a void pointer to
    # itself.
    if old == new:
        raise LedgerError(f"there is nothing to move: {old} to itself")
    directory = register.directory
    source = root / directory / f"{old}.md"
    target = root / directory / f"{new}.md"
    if not fsops.is_file(source):
        raise LedgerError(f"{directory}/{old}.md does not exist")
    # The repo-relative form, which is `parse_entry`'s and `read_ledger_text`'s contract: it
    # names the file in every message either of them raises.
    where = Path(directory) / f"{old}.md"
    source_text = read_ledger_text(source, where=where)
    # Parsed once: the half-done check reads the pointer it may be, and the pointer this run
    # writes is titled from the entry it is.
    source_entry = parse_entry(source_text, path=where, register=register)
    # A literal `"id: {old}"` substring match would miss a hand-edited entry whose `id:` line
    # uses different spacing or quoting than this tool writes; `parse_entry` already accepts
    # those (`_KEY_VALUE` allows `[ \t]*` after the colon), so the rewrite must too.
    moved = ID_LINE.sub(f"id: {new}", source_text, count=1)
    written = _endpoints_written(
        register, source_text, source_entry, moved, target, old=old, new=new
    )
    # Every sibling is parsed here, with the tree still untouched. `_write_index` at the end
    # renders the index from every entry file in the directory, so one malformed sibling — a
    # file this call never touches — failed the command AFTER both endpoints and the whole sweep
    # were on disk: exit 1 naming a file the operator did not edit, a half-completed rename, and
    # a retry then refused with "already has an entry file", so the move could not be finished
    # at all. `file_entry` never had it, because `next_identifier` parses the siblings before
    # anything is written. The index `_write_index` writes is rendered from the files as they are
    # AFTER the move, so these entries serve only to ask whether the move has already finished.
    entries = load_entries(root, register)
    # The last of the checks that reject with the tree untouched, and the one this command
    # needs most: it regenerates the index at the end, by which time both endpoints and the
    # whole sweep are already on disk, so a refusal that came any later would come after the
    # damage. Bound to a local rather than inlined like `file_entry`'s identical call, so the
    # oracle entry that pins this call site names a line that appears once in this file.
    committed_index = index_text(root, register)
    refuse_index_overwrite(root, register, committed_index)
    # The index is the move's last write, so with the pointer in place a fresh index is a move
    # that finished, and a mention of `old` written since is one the pointer exists to resolve:
    # sweeping it again rewrote "BR-001 was renumbered to BR-009" into "BR-009 was renumbered to
    # BR-009". A stale one is a move killed in its sweep or before the index, which is finished.
    if written == 2 and committed_index == render_index(entries, register):
        return Renumbered(source, (), moved=False)

    def unfinished(path: str, error: OSError) -> LedgerError:
        reason = fsops.said(error)
        return LedgerError(
            UNFINISHED.format(
                path=quoted(path), reason=reason, name=register.name, old=old, new=new
            )
        )

    if written < 1:
        try:
            fsops.write_within(root, f"{directory}/{new}.md", moved)
        except OSError as error:
            raise unfinished(f"{directory}/{new}.md", error) from error
    if written < 2:
        # Overwritten in place, never unlinked-then-recreated: the old identifier must resolve
        # to something at every instant from here on, including if the sweep below is
        # interrupted.
        pointer = _void_pointer(
            register,
            old=old,
            new=new,
            title=f"renumbered to {new} — {source_entry.title}",
            today=today or date.today().isoformat(),
        )
        try:
            fsops.write_within(root, f"{directory}/{old}.md", pointer)
        except OSError as error:
            raise unfinished(f"{directory}/{old}.md", error) from error

    pattern = re.compile(rf"\b{re.escape(old)}\b")
    excluded = {source, target, index_path(root, register)}
    unswept: list[Unswept] = []
    for item in scannable(root, citation_roots(root, config)):
        if item.path in excluded:
            continue
        # Different from undecodable: the file may well be text this sweep must rewrite, and
        # there is no way to find out. Reported rather than assumed clean.
        if item.error is not None:
            reason = f"could not be read to check for {old} ({item.error})"
            unswept.append(Unswept(item.relative.as_posix(), reason))
            continue
        # `text is None` is a file that is not text, whatever its suffix said: no identifier can
        # match in it and the substitution could not rewrite it, so the scan's own verdict
        # applies and there is nothing to sweep. The substring test then decides the whole file,
        # exactly as it does for the scan that reads these same files — without it the regex
        # runs over every file in the tree to rewrite the handful that carry the identifier.
        if item.text is None or old not in item.text:
            continue
        rewritten = pattern.sub(new, item.text)
        if rewritten == item.text:
            continue
        try:
            fsops.write_within(root, item.relative.as_posix(), rewritten)
        except OSError as error:
            unswept.append(
                Unswept(item.relative.as_posix(), f"could not be written ({fsops.said(error)})")
            )
    try:
        _write_index(root, register)
    except OSError as error:
        raise unfinished(register.index, error) from error
    return Renumbered(source, tuple(unswept))
