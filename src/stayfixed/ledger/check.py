"""Every violation of one register under a root, most structural first, as `Finding`s.

The register is handed in: its directory, index, identifiers and schema are the register's, and
`config` is read only for what no register owns, the roots the scan walks. Every text below
names the register's paths and its command group, so the bug ledger's read as they always have.
"""

from __future__ import annotations

import os
import re
from collections import defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING

from stayfixed.errors import Failure, Refusal
from stayfixed.findings import Finding, listed
from stayfixed.gitenv import ForkUnknown, fork_points, git_run
from stayfixed.ledger.entries import (
    Entry,
    LedgerError,
    entry_dir,
    parse_entry,
    read_ledger_text,
)
from stayfixed.ledger.index import (
    ENTRIES_MISSING,
    FOREIGN_CONTENT,
    foreign_index_lines,
    index_text,
    is_generated_index,
    render_index,
)
from stayfixed.ledger.register import EVIDENCE_LABEL, EVIDENCE_PLACEHOLDER, Register, bug_register
from stayfixed.ledger.scan import code_mentions, entry_citations

if TYPE_CHECKING:
    from pathlib import Path

    from stayfixed.config.schema import Config


# The negative lookahead is the point: the scaffold writes this line with its own placeholder
# text, so a bare match on the label would let every freshly filed entry satisfy the rule
# without anyone having written a word — a placeholder that satisfies its own check is the
# failure mode this rule exists to prevent.
# `[^\S\n]*` (same-line whitespace) and not `\s*`: the latter crosses newlines under MULTILINE
# and would let a bare label pass as long as anything followed it anywhere later in the body.
_EVIDENCE_BOUNDARY = re.compile(
    rf"^{re.escape(EVIDENCE_LABEL)}[^\S\n]*(?!{re.escape(EVIDENCE_PLACEHOLDER)})\S", re.MULTILINE
)
_CONFLICT_MARKER = re.compile(r"^(<{7} |={7}$|>{7} )", re.MULTILINE)
# `{name}` is the register's command group, `bugs` for the bug ledger; `{directory}` and `{index}`
# are its paths, and `{void}` its schema's void status.
LEDGER_REMOVED = (
    "a commit this change forked from the base at carries the ledger ({directory} or {index}) "
    "and this tree has neither; deleting the ledger does not switch the {name} gate off: restore "
    "it from the base"
)
ENTRY_REMOVED = (
    "a commit this change forked from the base at carries this entry and this tree does not; "
    "ledger entries are never deleted: restore it from the base, and move one with `stayfixed "
    "{name} renumber`, which leaves a `{void}` entry at the old number"
)
_BASE_UNREAD = (
    "what the commits HEAD forked from `{base}` at hold of {directory} and {index} is unknown "
    "under {root} ({cause}), so whether this change deleted the ledger or an entry of it is "
    "unknown and the {name} gate proved nothing. Fetch the whole history (`fetch-depth: 0` in "
    "CI), or pass a `--base` this clone holds that shares history with HEAD"
)


@dataclass(frozen=True)
class _BaseLedger:
    carried: bool  # the fork point has the ledger directory or the index
    entries: tuple[str, ...]  # the entry files directly under the directory there, by name


def _body_state_bullet(register: Register) -> re.Pattern[str]:
    """A body bullet restating the status or the level, which live in the frontmatter alone:
    `**Status:**` and, for the bug ledger, `**Severity:**`."""
    level = re.escape(register.schema.level.capitalize())
    return re.compile(rf"^- \*\*(Status|{level}):\*\*", re.MULTILINE)


def uninitialised(root: Path, register: Register) -> bool:
    """No ledger yet: no ledger directory *and* no index this tool generated. The second half
    is the point — the directory missing on its own also describes a ledger whose entry files
    were deleted under a generated index that still links every one of them. Only citations
    are checked here, so the gate can be registered before the first entry."""
    directory = entry_dir(root, register)
    return not directory.is_dir() and not is_generated_index(index_text(root, register))


def _base_ledger(root: Path, register: Register, base: str) -> _BaseLedger:
    """What the commits HEAD forked from `base` at carry of the ledger: whether any has the
    directory or the index, and the `<PREFIX>-nnn.md` entry files directly under the directory
    in any of them.

    Those commits are `git merge-base --all <base> HEAD`, every best common ancestor, the ones
    `plan` diffs against too. What the base gained after the change
    forked is not the change's to have kept, so a branch behind its base is not blamed for an
    entry filed since; and what the change forked with, it still answers for, on a stale branch
    as on the merge commit CI checks out, whose base parent the base can have moved past. A
    history the change shapes itself can give it several merge bases, and the one `merge-base`
    alone answers, the newest by date, can predate an entry another of them carries: a merge
    deletes that entry all the same. So each is listed with one `git ls-tree -r` of the two
    configured paths, whose names come back relative to `root`, and their entries are united.
    Entries are append-only, so on a base that kept its entries the union refuses no branch that
    deleted nothing; an entry removed from the base itself, by a direct push, is still named on
    a branch whose merge bases include one from before the removal, and is restored on the base.

    A base shaped like an option is refused, as `plan check` refuses it. Fork points
    `gitenv.fork_points` cannot name — a base git cannot resolve, one that shares no commit with
    HEAD, a shallow clone, and one git cannot say is shallow or not — and a listing git does not
    give, are a `Failure` — "could not run" to a gate — and never "the base has no ledger",
    which would pass exactly the change this question exists to catch.
    """
    if base.startswith("-"):
        raise Refusal(f"{base!r} looks like an option, not a base ref")
    directory, index = register.directory, register.index

    def unread(unknown: ForkUnknown) -> Failure:
        cause = unknown.cause
        return Failure(
            _BASE_UNREAD.format(
                directory=directory,
                index=index,
                name=register.name,
                base=base,
                root=root,
                cause=cause,
            )
        )

    forks = fork_points(root, base)
    if isinstance(forks, ForkUnknown):
        raise unread(forks)
    found: set[str] = set()
    for fork in forks:
        code, out = git_run(
            root, "ls-tree", "-r", "-z", "--name-only", fork, "--", directory, index
        )
        if code != 0:
            raise unread(ForkUnknown.of(code))
        found.update(name for name in out.split("\0") if name)
    names = sorted(found)
    ids = register.ids
    under = f"{directory}/"
    entries = tuple(
        name.removeprefix(under)
        for name in names
        if name.startswith(under)
        and name.endswith(".md")
        and ids.is_identifier(name.removeprefix(under).removesuffix(".md"))
    )
    return _BaseLedger(bool(names), entries)


def _removed_entries(root: Path, register: Register, base: _BaseLedger | None) -> list[Finding]:
    """Every entry file `base` carries whose exact name this tree's ledger directory does not
    hold, one finding each.

    Entries are append-only: `renumber` leaves a void entry at the number it moves from,
    so no command this project ships deletes one, and a change that does is refused whatever
    still mentions the identifier. The mentions cannot decide it, and nor can the fixtures
    marker, which is an exemption a file grants itself.

    The names are compared with the directory's own listing, never looked up one by one: a
    filesystem that folds case finds `BR-001.md` at `br-001.md`, which the ledger, loading its
    entries by exact name, does not, so a rename in case alone passed there and failed on Linux.
    A directory that is not there, or cannot be listed, holds no entry.
    """
    if base is None:
        return []
    try:
        present = set(os.listdir(entry_dir(root, register)))
    except OSError:
        present = set()
    removed = ENTRY_REMOVED.format(name=register.name, void=register.schema.void)
    return [
        Finding("entry-removed", f"{register.directory}/{name}", None, removed)
        for name in base.entries
        if name not in present
    ]


def _dangling_mentions(
    root: Path, config: Config, register: Register, known: set[str]
) -> list[Finding]:
    """Every identifier the scanned files mention that `known` does not hold, one finding per
    identifier at its first mention."""
    found: list[Finding] = []
    for identifier, locations in sorted(code_mentions(root, config, register).items()):
        if identifier not in known:
            path_, line = locations[0]
            found.append(
                Finding(
                    "dangling-mention",
                    path_.as_posix(),
                    line,
                    f"mentions {identifier}, which has no entry file "
                    f"(referenced {len(locations)} time(s))",
                )
            )
    return found


def _unledgered(
    root: Path, config: Config, register: Register, base: _BaseLedger | None
) -> list[Finding]:
    """The findings for a tree with no ledger: the ledger the change forked with, when it
    forked with one, and every mention and citation of an entry, since with no ledger each one
    dangles.

    "No ledger" is read off the tree, which a pull request writes, so the tree's word for it
    cannot be what switches the gate off: the commits the change forked from the base at are
    asked whether it had one, and a mention of an identifier is as much a reference as a
    citation of its file. A project that registers the gate before its first entry has no
    ledger there and mentions none, and stays green, as does a branch forked before the base's
    first entry. With no `base` — `bugs check` run without `--base` — only the tree is judged.
    The one `ledger-removed` finding stands for every entry that commit carried.
    """
    found: list[Finding] = []
    if base is not None and base.carried:
        directory, index = register.directory, register.index
        removed = LEDGER_REMOVED.format(directory=directory, index=index, name=register.name)
        found.append(Finding("ledger-removed", directory, None, removed))
    empty: set[str] = set()
    found.extend(_dangling_mentions(root, config, register, empty))
    return found + _dangling_citations(root, config, register, empty)


def _dangling_citations(
    root: Path, config: Config, register: Register, known: set[str]
) -> list[Finding]:
    """Every entry file a document or source cites that `known` does not hold, one finding per
    identifier at its first citation."""
    found: list[Finding] = []
    for identifier, locations in sorted(entry_citations(root, config, register).items()):
        if identifier not in known:
            path_, line = locations[0]
            found.append(
                Finding(
                    "dangling-citation",
                    path_.as_posix(),
                    line,
                    f"cites {register.directory}/{identifier}.md, which does not exist "
                    f"(referenced {len(locations)} time(s))",
                )
            )
    return found


def register_gate(root: Path, config: Config, register: Register, base: str = "") -> list[Finding]:
    """One register's gate, whole: every violation of `register` under `root`, most structural
    first.

    Before the ledger directory exists *and* before this tool has written an index there is
    nothing it owns, which is what lets the check be registered in CI one change before the
    first entry is filed: only a reference to an entry is reported then, since with no ledger
    every one of them dangles, and, against a `base`, a ledger the change forked with
    (`_unledgered`). A generated index with no ledger directory behind it is the other thing
    that shape describes, and it is the ledger having been deleted. Against a `base`, every arm
    past that one also names each entry the change forked with and the tree lacks
    (`entry-removed`). Both are read at every commit HEAD forked from `base` at
    (`_base_ledger`).
    """
    carried = _base_ledger(root, register, base) if base else None
    if uninitialised(root, register):
        return _unledgered(root, config, register, carried)
    ids, schema = register.ids, register.schema
    directory = entry_dir(root, register)
    index_name = register.index
    # First: a deleted entry is the most structural finding a ledger can have.
    found = _removed_entries(root, register, carried)
    if not directory.is_dir():
        missing = ENTRIES_MISSING.format(directory=register.directory, index=index_name)
        return [Finding("entries-missing", index_name, None, missing), *found]

    entries: list[Entry] = []
    required = set(register.evidence_boundary_for)
    restated = _body_state_bullet(register)
    for path in sorted(directory.glob(f"{ids.prefix}-*.md")):
        # Parsed against the repo-relative path, which is the one every message here names:
        # these are printed by CI, where an absolute path is a runner's scratch directory.
        relative = path.relative_to(root).as_posix()
        try:
            text = read_ledger_text(path, where=path.relative_to(root))
        except LedgerError as error:
            found.append(Finding("unreadable-entry", relative, None, str(error)))
            continue
        if _CONFLICT_MARKER.search(text):
            found.append(Finding("conflict-marker", relative, None, "unresolved conflict marker"))
            continue
        try:
            entry = parse_entry(text, path=path.relative_to(root), register=register)
        except LedgerError as error:
            found.append(Finding("unreadable-entry", relative, None, str(error)))
            continue
        if entry.id != path.stem:
            found.append(
                Finding(
                    "id-mismatch", relative, None, f"`id` {entry.id} does not match its filename"
                )
            )
        if restated.search(entry.body):
            found.append(
                Finding(
                    "state-in-body",
                    relative,
                    None,
                    f"body restates `**Status:**`/`**{schema.level.capitalize()}:**`; those live "
                    "in the frontmatter alone",
                )
            )
        level = entry.fields[schema.level]
        if level in required and not _EVIDENCE_BOUNDARY.search(entry.body):
            found.append(
                Finding(
                    "evidence-boundary",
                    relative,
                    None,
                    f"{schema.level} `{level}` needs a filled `{EVIDENCE_LABEL}` line — a "
                    "plan built on this entry inherits its silences as premises",
                )
            )
        entries.append(entry)

    known = {entry.id for entry in entries}
    by_id: defaultdict[str, list[Entry]] = defaultdict(list)
    for entry in entries:
        by_id[entry.id].append(entry)
    for identifier, holders in sorted(by_id.items()):
        if len(holders) > 1:
            # Capped, and nothing is lost from `--json`: only one holder's file name can be the
            # identifier, and every other one has an `id-mismatch` finding naming it, so that
            # one is named first, inside the cap whatever the sort puts after it.
            first = sorted(holders, key=lambda h: h.path.stem != identifier)
            joined = listed([str(h.path) for h in first])
            found.append(
                Finding(
                    "duplicate-id",
                    "",
                    None,
                    f"{identifier} is claimed by more than one file: {joined}",
                )
            )
    for entry in entries:
        for identifier in entry.related:
            if identifier not in known:
                found.append(
                    Finding(
                        "dangling-related",
                        entry.path.as_posix(),
                        None,
                        f"`related` names {identifier}, which has no entry file",
                    )
                )

    current = index_text(root, register)
    foreign = foreign_index_lines(root, current, register)
    if foreign:
        found.append(
            Finding(
                "foreign-index-content",
                index_name,
                None,
                FOREIGN_CONTENT.format(index=index_name, count=len(foreign), first=foreign[0]),
            )
        )
    # Suppressed while the index holds foreign content: regenerating is what deletes it, so
    # recommending it here would hand the operator the destructive step.
    elif current != render_index(sorted(entries, key=lambda e: e.number), register):
        stale = f"is stale; run: stayfixed {register.name} index"
        found.append(Finding("stale-index", index_name, None, stale))

    found.extend(_dangling_mentions(root, config, register, known))
    # Wider than the scan above, and reported separately because a citation says something a
    # bare mention does not: it names a path, so a reader who follows it gets a 404 rather than
    # an unfamiliar identifier. Closing an entry and renaming its file is the shape that leaves
    # one behind, and it lands in a docs-only commit.
    return found + _dangling_citations(root, config, register, known)


def bugs_gate(root: Path, config: Config, base: str = "") -> list[Finding]:
    """The `bugs` gate: the bug ledger's `register_gate`, in the `(root, config, base)` shape every
    gate of `stayfixed assess` shares.

    `bugs check` gives the same answer, with `--base` as `base` or `""`, which judges the tree
    alone, through `register_gate` over a register it builds once; every gate run passes the base
    it judges against.
    """
    return register_gate(root, config, bug_register(config), base)
