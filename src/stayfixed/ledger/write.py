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
from stayfixed.ledger.register import Register, bug_register
from stayfixed.ledger.scan import citation_roots, scannable

if TYPE_CHECKING:
    from stayfixed.config.schema import Config

# Bound on the pre-allocation `git fetch`: an offline machine or a stalled remote must not hang
# `new`, and a skipped fetch is reported rather than silent. A named cap
# (CONTRIBUTING.md#named-caps), and no shipped file changes with it.
FETCH_TIMEOUT_SECONDS = 10

# The keys `file_entry` writes itself; every other key of a register's schema is a placeholder in
# its template for that key's whole line.
_WRITER_KEYS = ("id", "title", "status", "related")

_ID_LINE = re.compile(r"^id:.*$", re.MULTILINE)
_VOID_POINTER = """---
id: {old}
title: {title}
status: void
found: {today}
related: [{new}]
---

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
    unswept: list[Unswept]


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
    if directory.is_dir():
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

    `values` holds the register's keys other than `_WRITER_KEYS` — for the bug ledger
    `severity`, `area` and `source` — each written as its template's whole `key: value` line; a
    key left out is written bare.

    Every failure is raised before anything reaches disk: a rejected input leaves the tree
    exactly as it was, with no half-filed entry and no allocated-but-unused number. A level
    outside the vocabulary, an index that must not be regenerated over, an identifier whose
    file already exists and frontmatter the reader would reject are all rejected here.

    `fetch` is the one knob a caller turns off: the allocator asks the network what other
    branches hold, which tests and offline use skip.
    """
    schema = register.schema
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
    if path.exists():
        raise LedgerError(
            f"{identifier} was allocated but {relative} already exists; nothing was written. "
            f"Run `stayfixed {register.name} check`: an entry file the allocator cannot account "
            "for is one this ledger is wrong about."
        )
    lines = {
        key: field_line(key, values.get(key, "")) for key in schema.keys if key not in _WRITER_KEYS
    }
    text = schema.template.format(
        identifier=identifier,
        title=scalar(title),
        today=today or date.today().isoformat(),
        related=related_field(related),
        **lines,
    )
    # Validated the same way any other entry file is, before it touches disk: a malformed field
    # must fail cleanly here rather than be written and then fail the index re-render below,
    # leaving a broken entry file that every later `index`, `check` and `new` also fails on.
    parse_entry(text, path=Path(relative), register=register)
    fsops.write_within(root, relative, text)  # creates the ledger directory on the first entry
    _write_index(root, register)
    return Filed(path, identifier, allocation.warning)


def renumber(root: Path, config: Config, old: str, new: str, *, today: str = "") -> Renumbered:
    """Move an entry to a free identifier, taking every reference to it along.

    Every check that can reject the call runs before any file is touched. Both endpoints are
    written before the slow sweep, so an interruption leaves the old identifier resolving to
    the void pointer rather than to nothing. Both files are excluded from the sweep itself: the
    moved entry's prose is the operator's to rewrite, not the sweep's, and the void pointer's
    own `id:` line would otherwise be corrupted by the substitution it exists to survive.

    A text file the sweep cannot read, or cannot write back, is not silently skipped: once the
    void pointer exists, `check.problems`' `known` set makes a stale `old` mention in that file
    look intentional forever, and it will never be reported as dangling again. So a file the
    sweep could not touch is collected and returned, and the command fails, rather than
    claiming a rewrite it did not fully deliver. A file that is not text at all is a different
    thing and is skipped in silence, exactly as the scan skips it: it holds no identifier to
    rewrite, and reporting one would fail this command on any repository tracking one image.
    """
    register = bug_register(config)
    ids = register.ids
    if not (ids.is_identifier(old) and ids.is_identifier(new)):
        raise LedgerError(f"both identifiers must look like {ids.shape}")
    bugs = register.directory
    source = root / bugs / f"{old}.md"
    target = root / bugs / f"{new}.md"
    if not source.is_file():
        raise LedgerError(f"{bugs}/{old}.md does not exist")
    if target.exists():
        raise LedgerError(f"{new} already has an entry file; pick a free identifier")
    # Every sibling is parsed here, with the tree still untouched. `_write_index` at the end
    # renders the index from every entry file in the directory, so one malformed sibling — a
    # file this call never touches — failed the command AFTER both endpoints and the whole sweep
    # were on disk: exit 1 naming a file the operator did not edit, a half-completed rename, and
    # a retry then refused with "already has an entry file", so the move could not be finished
    # at all. `file_entry` never had it, because `next_identifier` parses the siblings before
    # anything is written. The result is discarded on purpose: the index has to be rendered from
    # the files as they are AFTER the move, so this is a check and not a value.
    load_entries(root, register)
    # The last of the checks that reject with the tree untouched, and the one this command
    # needs most: it regenerates the index at the end, by which time both endpoints and the
    # whole sweep are already on disk, so a refusal that came any later would come after the
    # damage. Bound to a local rather than inlined like `file_entry`'s identical call, so the
    # oracle entry that pins this call site names a line that appears once in this file.
    committed_index = index_text(root, register)
    refuse_index_overwrite(root, register, committed_index)

    # The repo-relative form, which is `parse_entry`'s and `read_ledger_text`'s contract: it
    # names the file in every message either of them raises.
    where = Path(bugs) / f"{old}.md"
    source_text = read_ledger_text(source, where=where)
    entry = parse_entry(source_text, path=where, register=register)
    # A literal `"id: {old}"` substring match would miss a hand-edited entry whose `id:` line
    # uses different spacing or quoting than this tool writes; `parse_entry` already accepts
    # those (`_KEY_VALUE` allows `[ \t]*` after the colon), so the rewrite must too.
    fsops.write_within(root, f"{bugs}/{new}.md", _ID_LINE.sub(f"id: {new}", source_text, count=1))
    # Overwritten in place, never unlinked-then-recreated: the old identifier must resolve to
    # something at every instant from here on, including if the sweep below is interrupted.
    fsops.write_within(
        root,
        f"{bugs}/{old}.md",
        _VOID_POINTER.format(
            old=old,
            new=new,
            title=quote(f"renumbered to {new} — {entry.title}"),
            today=today or date.today().isoformat(),
        ),
    )

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
    _write_index(root, register)
    return Renumbered(source, unswept)
