"""The `hook-entries` row: every hook entry in every settings file, with its provenance.

A core check, listed in `checks.CHECKS` and asked through the run's guard like the others. The walk
over the settings files and the sentences each kind of finding is told in are one unit that no
other check reads, so they sit in a module of their own and `checks.py` stays the list of checks
and the run. It imports nothing of the run's, so `checks.py` can import it without a cycle.

What it may print is held to `checks.py`'s module docstring: the row names settings files by
their paths and counts the entries in them, and never prints what an entry holds.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from stayfixed.doctor.model import OK, WARN, Context, Row, Status
from stayfixed.errors import Refusal
from stayfixed.findings import listed
from stayfixed.fsops import names_regular_file, read_regular_bytes
from stayfixed.harnesses import CLAUDE, HARNESSES, LENIENT_SETTINGS
from stayfixed.scaffold import ParserLimitError, judged_entries, marker_id

# Every file a hook entry can be installed into, as a path relative to a root: each harness's
# committed settings files and the ones it keeps out of git, read off the harness registry, so a
# harness added there is walked here without an edit. The two roots are the project (all of
# them) and `home` (`USER_SETTINGS` alone, which is where `setup` merges the preset's deny
# rules: the same file under another root).
SETTINGS_FILES = tuple(
    relative for harness in HARNESSES for relative in (*harness.settings, *harness.local_settings)
)
# Claude Code's settings file under the home directory, read off the registry as `setup` reads it,
# and not asked of `setup`, whose import surface loads the command that writes it.
(USER_SETTINGS,) = CLAUDE.settings

# How the machine-scope copy of `USER_SETTINGS` is named in the report. A label and not a path:
# `home` is a directory this process was handed, and `~/.claude/settings.json` is what a reader
# would type. The project-relative members of `SETTINGS_FILES` name themselves.
_MACHINE_LABEL = f"~/{USER_SETTINGS}"


@dataclass(frozen=True)
class _Kind:
    """One kind of finding `hook-entries` reports, and how it is told.

    `tell` is the part the row prints for the files it names, and `remedy` the way out. `step` says
    which remedies the row carries: those of the highest step among its findings.
    """

    step: int
    tell: Callable[[list[str]], str]
    remedy: str


def _unchecked(wheres: list[str]) -> str:
    return (
        f"{len(wheres)} settings file(s) are nested deeper than this check can follow, so "
        f"nothing here can check the entries in them: {listed(wheres)}"
    )


def _blind(wheres: list[str]) -> str:
    return (
        f"{len(wheres)} settings file(s) exist and could not be read as hook entries, so "
        f"nothing here accounts for what is in them: {listed(wheres)}"
    )


# Each kind of finding, in the order the row tells them, each a warning: a file nested past the
# parser's reach, which a harness may still run and nothing here can check; and a file the walk
# cannot read, at the lowest step, so its remedy is offered only where no other finding has one.
_UNCHECKED = _Kind(
    1,
    _unchecked,
    "open each file named above and remove what you did not put there; stayfixed writes no "
    "settings file nested that deep",
)
_BLIND = _Kind(0, _blind, "check that each file named above is readable and is valid JSON")
_KINDS = (_UNCHECKED, _BLIND)


@dataclass(frozen=True)
class _Finding:
    """What the row tells of one kind: the kind, and the files it names in the order the walk met
    them."""

    kind: _Kind
    wheres: list[str]


def _gathered(found: Sequence[tuple[_Kind, str]]) -> list[_Finding]:
    """`found`, each a kind and the file it names, as one finding per kind in `_KINDS`' order."""
    gathered = []
    for kind in _KINDS:
        mine = [where for each, where in found if each is kind]
        if mine:
            gathered.append(_Finding(kind, mine))
    return gathered


def _classify(context: Context) -> tuple[int, int, list[_Finding]]:
    """How many entries claim the marker, how many are foreign, and every finding about them."""
    found: list[tuple[_Kind, str]] = []
    claimed = 0
    foreign = 0
    walked = [(context.root, relative, relative) for relative in SETTINGS_FILES]
    if context.home is not None:
        walked.append((context.home, USER_SETTINGS, _MACHINE_LABEL))
    for base, relative, label in walked:
        path = base / relative
        # Asked of `fsops.names_regular_file`, for the reason `fsops.NAMES_NO_FILE` gives: a path
        # this walk cannot ask about is a file it is blind to, and one that names no file is
        # skipped, since there is nothing there for a harness to read either.
        try:
            regular = names_regular_file(path)
        except OSError:
            found.append((_BLIND, label))
            continue
        if not regular:
            continue
        try:
            # Replaced rather than refused: the marker and every command it marks are ASCII, so a
            # byte that is not UTF-8 elsewhere in the file changes no entry's verdict. Read by
            # `fsops`' one bounded reader, which every reader of a committed file goes through,
            # here at the regular-file cap, so a file that never ends, or one swapped for a device
            # after the question above, is one this walk cannot read.
            document = read_regular_bytes(path).decode("utf-8", errors="replace")
        except OSError:
            found.append((_BLIND, label))
            continue
        try:
            # The entries a harness runs out of the file, read as `harnesses.LENIENT_SETTINGS`
            # says its files were measured, and every other file strictly. A part this cannot
            # read for entries is named as one the walk is blind to.
            read = judged_entries(document, lenient=relative in LENIENT_SETTINGS)
        except ParserLimitError:
            found.append((_UNCHECKED, label))
            continue
        except Refusal:
            found.append((_BLIND, label))
            continue
        if read.partly:
            found.append((_BLIND, label))
        for placed in read.entries:
            if marker_id(placed.command) is None:
                foreign += 1
            else:
                claimed += 1
    return claimed, foreign, _gathered(found)


def _told(claimed: int, foreign: int, findings: Sequence[_Finding]) -> Row:
    """The row for `findings`: every finding's part, in order, after the count; a warning where
    there is any, and "all accounted for" where there is none; and the remedy of every finding at
    the highest step among them, each said once."""
    parts = [f"{claimed} stayfixed entr(ies), {foreign} foreign"]
    parts.extend(finding.kind.tell(finding.wheres) for finding in findings)
    status: Status = WARN if findings else OK
    if status == OK:
        parts.append("all accounted for")
    step = max((finding.kind.step for finding in findings), default=None)
    chosen = (finding.kind.remedy for finding in findings if finding.kind.step == step)
    return Row(status, "; ".join(parts), "; ".join(dict.fromkeys(chosen)))


def hook_entries(context: Context) -> Row:
    """Every entry in every settings file, counted by provenance.

    **An entry claiming the stayfixed marker is counted as stayfixed's, wherever it sits.** Where
    it sits is not judged: the files are this machine's or the repository's, and whoever can plant
    a marked entry in one can write the file. An entry with no marker is foreign, and every merge
    this project ships leaves it alone.

    **Entries are counted, never keys.** `scaffold.judged_entries` answers one element per entry,
    in document order, so N entries sharing one id are N entries and one id under two events is
    two. The count comes from `marker_id`, the predicate `owned_ids` is built on and the one
    `attach.write` keys its ledger with.

    **A file this walk could not read is `blind`, never silently absent.** An `OSError` on the
    read, a document that will not parse or is not an object, a `hooks` that is not an object, and
    a part of the `hooks` section that could hold a command it cannot read are each named, because
    "all accounted for" is the one answer this check must never give about entries it did not see.
    The report names the file and never its contents.

    **The entries a harness runs are counted, wherever they sit, in the files it was measured
    on.** For Claude Code's settings files (`harnesses.LENIENT_SETTINGS`, which says what was
    measured and when) the walk is not the engine's strict one, the one `apply_entries` rewrites
    through: Claude Code still ran the valid hooks of a file whose `hooks` section held a scalar
    where an event's list, a group, a group's `hooks` or an entry belongs, so an entry beside
    such a part is live and counted like any other. Every other file -- Codex's
    `.codex/hooks.json`, which no measurement covers -- is read by the strict walk. Not measured,
    and so not assumed: a container in one of those places, or an entry object where a group goes,
    which may hold a command, leaves the file `blind` as well as counting the entries beside it.

    **A byte that is not UTF-8 does not make a file `blind`.** The file is decoded with each such
    byte replaced, because the marker and the commands it marks are ASCII, so the entries in it
    are counted as they would be without the byte. In Claude Code's settings files a UTF-8
    byte-order mark ahead of the document is read past: `json.loads` refuses it, and Claude Code
    runs the hooks of such a file (`harnesses.LENIENT_SETTINGS`), so it is no reason to be
    `blind` there. In any other file it still is.

    **A file this walk refuses only for a limit of Python's parser is never `blind`.** Valid JSON
    nested deeper than the parser follows may still be read by a harness (Claude Code's parser
    does), so the hooks in it may run and nothing here can check them: a warning, named as such.
    A number longer than the interpreter converts is not refused at all: either walk reads it as
    its text, and the entries beside it are counted as they would be without it.
    """
    return _told(*_classify(context))
