"""The `hook-entries` row: every hook entry in every settings file, with its provenance.

A core check, listed in `checks.CHECKS` and asked through the run's guard like the others, and
the only one that reads what the areas contribute besides rows: each area's `Claims`, the ids it
recorded and the entries it grants, told in the area's own `Wording`. The walk over the settings
files, the rules for which area vouches for an entry, and the sentences each kind of finding is
told in are one unit that no other check reads, so they sit in a module of their own and
`checks.py` stays the list of checks and the run. It imports nothing of the run's, so `checks.py`
can import it without a cycle.

What it may print is held to `checks.py`'s module docstring, and this row is where that ruling is
most tempting to break: an entry is named by its position in its file, never by the marker id it
claims, and that docstring says why.
"""

from __future__ import annotations

import os
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from stayfixed.doctor.model import OK, RED, WARN, Claims, Context, Row, Status, Wording
from stayfixed.errors import Refusal
from stayfixed.findings import listed
from stayfixed.fsops import NAMES_NO_FILE, names_regular_file, read_regular_bytes
from stayfixed.harnesses import HARNESSES, LENIENT_SETTINGS
from stayfixed.printed import printable
from stayfixed.scaffold import ParserLimitError, Placed, judged_entries, marker_id
from stayfixed.setup.api import USER_SETTINGS

# Every file a hook entry can be installed into, as a path relative to a root: each harness's
# committed settings files and the ones it keeps out of git, read off the harness registry, so a
# harness added there is walked here without an edit. The two roots are the project (all of
# them) and `home` (`USER_SETTINGS` alone, which is where `setup` merges the preset's deny
# rules, and which `setup` reads off `CLAUDE.settings`: the same file under another root).
SETTINGS_FILES = tuple(
    relative for harness in HARNESSES for relative in (*harness.settings, *harness.local_settings)
)

# Where Claude Code finds a project's skills, each one a directory holding `SKILL.md`. A skill's
# YAML frontmatter can declare hooks, and Claude Code ran one so declared once the skill was
# invoked (2.1.288, measured 2026-10-06), so this row names every skill whose frontmatter has a
# top-level `hooks:` key as one it does not judge (`_skills`).
SKILLS = ".claude/skills"
_SKILL_FILE = "SKILL.md"
# The line that opens a frontmatter and the next one that closes it.
_FENCE = "---"
# A top-level `hooks` key: at the start of its line, not indented under another key, and the whole
# key, not the start of a longer one. Nothing else of YAML is parsed.
_HOOKS_KEY = re.compile(r"hooks[ \t]*:(?:[ \t]|$)")
# What a skill whose directory name is outside the path grammar is named as: the name is the
# repository's, and this row's detail is what `--json` carries too, so there is nowhere else to
# point.
_UNPRINTED_SKILL = "a skill whose name this row does not print"

# How the machine-scope copy of `USER_SETTINGS` is named in the report. A label and not a path:
# `home` is a directory this process was handed, and `~/.claude/settings.json` is what a reader
# would type. The project-relative members of `SETTINGS_FILES` name themselves.
_MACHINE_LABEL = f"~/{USER_SETTINGS}"


class UnansweredClaims(RuntimeError):
    """An area's claims raised. Never an `OSError`, whatever they raised, so the report's guard
    reads it as the red it is and not as the machine's warning.

    It carries no message: the guard prints an exception's type and never its message, so the
    type is all of it the report shows, and the exception it is raised from carries the rest."""


def _area_claims(context: Context) -> list[Claims]:
    """Every area's `Claims`, in area order.

    An area's own record is the only thing that can say what it put into settings files, so the
    core asks each area that has one — `context.claims` — with this report's context and under
    this row's guard. The answers are kept apart rather than pooled: an entry is vouched for only
    by the one area that both records its id and grants it, because a record is a file a
    repository can write, and one area's record standing on another area's grant vouches for an
    entry neither area put there whole. A `None` is still one for the whole: an id one record could
    not be read for, or a command one source could not be asked about, is not one the rest can
    vouch for. With no area claiming anything, nothing is recorded and nothing granted, so every
    entry claiming the marker is one no area put there.

    **Claims that raise are red, whatever they raise.** An area answers what it cannot read as a
    `None` field, so one that raises is a defect in its code, and `Contribution.claims` promises
    red for it. The guard reads an `OSError` as the machine's and warns, so a `PermissionError` out
    of an area's claims, reaching it as itself, would turn the row — and every forged entry it
    would have listed — into a warning and an exit of 0. It is raised on as `UnansweredClaims`,
    which the guard names in the row; the exception it chains carries the original, whose message is
    never printed, because an area may have built it from repository bytes.
    """
    try:
        return [ask(context) for ask in context.claims]
    except Exception as exc:  # an area's own code: red, never the guard's warning for `OSError`
        raise UnansweredClaims from exc


def _grants(area: Claims, placed: Placed) -> bool:
    """Whether `area` grants the entry `placed` is, where it is: its command, under its event, in a
    group with its matcher, and the whole entry it sits in.

    All of them, because a granted command under another event or matcher is a hook the area never
    put there — the harness runs it at another time, or for other tools — and so is a granted
    command inside an entry that does something else with it: an `http` entry carrying it posts
    every event to a URL and ignores the command. Vouching for either would let a repository hang
    the owner's command anywhere it liked and read "all accounted for". The whole entry is the one
    the area writes, so a grant that carries more than a command, a `timeout` say, is compared
    with what it wrote. Told, where the area records the entry's id, as an entry its source does
    not grant, which it does not."""
    return any(
        grant.command == placed.command
        and grant.event == placed.event
        and grant.matcher == placed.matcher
        and grant.entry == placed.entry
        for grant in area.granted or ()
    )


def _rebuild(words: Wording) -> str:
    """How an owner gets an area's unreadable record back: remove it, and have the area write a
    new one from its source — an area that writes a record refuses to write over one it cannot
    read."""
    return f"remove {words.record} and run {words.vouch} to write a new one"


def _refused(words: Wording) -> str:
    """The clause saying an area's source does not vouch for entries it was asked about: that it
    does not grant them, or the area's own `ungranted` where that would be false."""
    return words.ungranted or f"{words.source} does not grant them"


# What a red entry's remedy opens with wherever the reader is the one to tell an entry they
# installed from one they did not.
_OPEN = "open each entry named above and remove the ones you did not install"


@dataclass(frozen=True)
class _Kind:
    """One kind of finding `hook-entries` reports, and how it is told.

    `status` is what a finding of the kind makes the row: red where any finding is red, a warning
    where any is a warning, and ok with none. `tell` is the part the row prints for one finding,
    given the areas it speaks for and the entries or files it names; `remedy` is the way out of
    that finding. `step` says which remedies the row carries: those of every finding of the
    highest step among its findings.

    Each takes the areas whose words the finding is told in — the one area whose record, source
    or entries it is about, or every area, for a finding about none of them in particular — so a
    sentence about an area's record or source is in that area's own words, never another's.
    """

    status: Status
    step: int
    tell: Callable[[Sequence[Claims], list[str]], str]
    remedy: Callable[[Sequence[Claims]], str]


def _one(areas: Sequence[Claims]) -> Claims:
    """The one area a finding about one area's record, source or entries is told for."""
    (area,) = areas
    return area


def _unreadable(areas: Sequence[Claims], wheres: list[str]) -> str:
    words = _one(areas).wording
    return f"{words.record} is there and {words.unreadable}"


def _rebuilt(areas: Sequence[Claims]) -> str:
    # Rebuilding needs the source the area writes from, so where that area's source cannot be
    # asked the remedy stays with the file.
    area = _one(areas)
    return _rebuild(area.wording) if area.granted is not None else area.wording.inspect


def _unaskable(areas: Sequence[Claims], wheres: list[str]) -> str:
    unaskable = _one(areas).wording.unaskable
    return f"{unaskable}, so nothing here vouches for the ones claiming the marker"


def _unrecorded(areas: Sequence[Claims], wheres: list[str]) -> str:
    # Every record was read and none holds these, so the sentence names each of them; with no
    # area claiming anything there is no record to name, and nothing records them.
    records = list(dict.fromkeys(area.wording.record for area in areas))
    missing = f"are not recorded in {' or '.join(records)}" if records else "are recorded nowhere"
    return f"{len(wheres)} entr(ies) claim the stayfixed marker and {missing}: {listed(wheres)}"


def _unvouched(areas: Sequence[Claims], wheres: list[str]) -> str:
    words = _one(areas).wording
    return (
        f"{len(wheres)} entr(ies) claim the stayfixed marker and are recorded in "
        f"{words.record}, and {words.unsourced}, so nothing on this machine vouches for them: "
        f"{listed(wheres)}"
    )


def _sourced(areas: Sequence[Claims]) -> str:
    words = _one(areas).wording
    return f"{_OPEN}; if you did install them, {words.setup}, then {words.vouch}"


def _ungranted(areas: Sequence[Claims], wheres: list[str]) -> str:
    words = _one(areas).wording
    return (
        f"{len(wheres)} entr(ies) claim the stayfixed marker and are recorded in "
        f"{words.record}, and {_refused(words)}: {listed(wheres)}"
    )


def _vouched(areas: Sequence[Claims]) -> str:
    words = _one(areas).wording
    return words.regrant or (
        f"run {words.vouch}, which takes out every marked entry {words.source} no longer "
        f"grants; open any that survive it"
    )


def _unread_unvouched(areas: Sequence[Claims], wheres: list[str]) -> str:
    words = _one(areas).wording
    return (
        f"{len(wheres)} entr(ies) claim the stayfixed marker and {words.unsourced}, so "
        f"whatever {words.record} records, nothing on this machine vouches for them: "
        f"{listed(wheres)}"
    )


def _sourced_and_rebuilt(areas: Sequence[Claims]) -> str:
    words = _one(areas).wording
    return f"{_OPEN}; if you did install them, {words.setup}; then {_rebuild(words)}"


def _unread_ungranted(areas: Sequence[Claims], wheres: list[str]) -> str:
    words = _one(areas).wording
    return (
        f"{len(wheres)} entr(ies) claim the stayfixed marker and {_refused(words)}, so "
        f"whatever {words.record} records, nothing on this machine vouches for them: "
        f"{listed(wheres)}"
    )


def _regranted(areas: Sequence[Claims]) -> str:
    words = _one(areas).wording
    return f"{_OPEN}; then {words.regrant or _rebuild(words)}"


def _unchecked(areas: Sequence[Claims], wheres: list[str]) -> str:
    return (
        f"{len(wheres)} settings file(s) are nested deeper than this check can follow, so "
        f"nothing here can check the entries in them: {listed(wheres)}"
    )


def _hidden(areas: Sequence[Claims], wheres: list[str]) -> str:
    return (
        f"{len(wheres)} settings file(s) hold a command claiming the stayfixed marker where this "
        f"check reads no hook entry, so nothing here can check it: {listed(wheres)}"
    )


def _blind(areas: Sequence[Claims], wheres: list[str]) -> str:
    return (
        f"{len(wheres)} settings file(s) exist and could not be read as hook entries, so "
        f"nothing here accounts for what is in them: {listed(wheres)}"
    )


def _skill_hooks(areas: Sequence[Claims], wheres: list[str]) -> str:
    return (
        f"{len(wheres)} project skill(s) declare hooks in their frontmatter, which this row does "
        f"not judge: {listed(wheres)}"
    )


def _skill_unread(areas: Sequence[Claims], wheres: list[str]) -> str:
    return (
        f"{len(wheres)} project skill file(s) could not be read, so this row cannot say whether "
        f"they declare hooks: {listed(wheres)}"
    )


# Each kind of finding, in the order the row tells them. A record that cannot be read and a source
# that cannot be asked withhold judgement and warn; the kinds after them, up to the last, are an
# entry nothing vouches for or a file nothing can check, and red; and the last, a file the walk
# cannot read, warns, so it softens a row with nothing else to say and never a red one.
#
# The steps keep the order the row has always preferred remedies in — of two red kinds, the later
# one's — so a row with one claimant reads as it did. The two kinds that withhold judgement share a
# step, because each is one area's, one area's record may be unreadable while another's source
# cannot be asked, and each needs its own way out; a file the walk is blind to is the lowest, its
# remedy offered only where no other finding has one.
_UNREADABLE = _Kind(WARN, 1, _unreadable, _rebuilt)
_UNASKABLE = _Kind(WARN, 1, _unaskable, lambda areas: _one(areas).wording.diagnose)
_UNRECORDED = _Kind(RED, 2, _unrecorded, lambda areas: _OPEN)
_UNVOUCHED = _Kind(RED, 3, _unvouched, _sourced)
_UNGRANTED = _Kind(RED, 4, _ungranted, _vouched)
_UNREAD_UNVOUCHED = _Kind(RED, 5, _unread_unvouched, _sourced_and_rebuilt)
_UNREAD_UNGRANTED = _Kind(RED, 6, _unread_ungranted, _regranted)
_UNCHECKED = _Kind(
    RED,
    7,
    _unchecked,
    lambda areas: (
        "open each file named above and remove what you did not put there; stayfixed writes "
        "no settings file nested that deep"
    ),
)
# A marked command in a part of the file the live-entry walk skipped: red, conservatively, for
# the reason `_UNCHECKED` is -- a harness may run what nothing here can check.
_HIDDEN = _Kind(
    RED,
    8,
    _hidden,
    lambda areas: (
        "open each file named above and remove what you did not put there; stayfixed writes no "
        "marked command outside an event's list of entry groups"
    ),
)
_BLIND = _Kind(
    WARN,
    0,
    _blind,
    lambda areas: "check that each file named above is readable and is valid JSON",
)
# A project skill declaring hooks, and one whose file could not be read: warnings, never red, at
# the lowest step, so either one softens a row with nothing else to say and never a red one. This
# row judges settings files; a skill's hooks are named, not judged.
_SKILL_HOOKS = _Kind(
    WARN,
    0,
    _skill_hooks,
    lambda areas: (
        "open each skill named above and check the hooks its frontmatter declares: Claude Code "
        "runs them once the skill is invoked"
    ),
)
_SKILL_UNREAD = _Kind(
    WARN,
    0,
    _skill_unread,
    lambda areas: "check that each skill file named above is a readable regular file",
)
_KINDS = (
    _UNREADABLE,
    _UNASKABLE,
    _UNRECORDED,
    _UNVOUCHED,
    _UNGRANTED,
    _UNREAD_UNVOUCHED,
    _UNREAD_UNGRANTED,
    _UNCHECKED,
    _HIDDEN,
    _BLIND,
    _SKILL_HOOKS,
    _SKILL_UNREAD,
)


@dataclass(frozen=True)
class _Finding:
    """What the row tells of one kind for one area: the areas whose words tell it (`_Kind`'s), and
    the entries or files it names, in the order the walk met them."""

    kind: _Kind
    areas: tuple[Claims, ...]
    wheres: list[str]


# One finding as the walk makes it: its kind, the area whose words tell it — `None` for a finding
# that is no one area's — and the entry or file it names, `None` for a finding about an area's
# record or source, which names none.
_Found = tuple[_Kind, Claims | None, str | None]


def _gathered(answers: Sequence[Claims], found: Sequence[_Found]) -> list[_Finding]:
    """`found` as one finding per kind and area, kinds in `_KINDS`' order and areas in area order:
    each part of the row is one kind told in one area's words. An area is matched by identity,
    because two areas' claims may be equal and are still two areas' to tell."""
    gathered = []
    for kind in _KINDS:
        for area in (None, *answers):
            mine = [where for each, told, where in found if each is kind and told is area]
            if mine:
                areas = tuple(answers) if area is None else (area,)
                wheres = [where for where in mine if where is not None]
                gathered.append(_Finding(kind, areas, wheres))
    return gathered


def _declares_hooks(text: str) -> bool:
    """Whether `text`, a `SKILL.md`, opens with a frontmatter holding a top-level `hooks:` key.

    The frontmatter is the lines between a first line of `---` and the next `---` line; without
    the closing one there is none. Line breaks are YAML's (LF, CRLF, a lone CR) and no other, and
    a byte-order mark ahead of the first line is read past."""
    lines = text.removeprefix(chr(0xFEFF)).replace("\r\n", "\n").replace("\r", "\n").split("\n")
    if lines[0].rstrip() != _FENCE:
        return False
    for end, line in enumerate(lines[1:], 1):
        if line.rstrip() == _FENCE:
            return any(_HOOKS_KEY.match(key) for key in lines[1:end])
    return False


def _skills(root: Path) -> list[_Found]:
    """A finding for each project skill whose frontmatter declares hooks, and for each whose
    `SKILL.md` could not be read, in name order.

    Read through `fsops.read_regular_bytes`, as every reader of a committed file is: a link to a
    device or a FIFO is refused unread, and a file past the cap is refused, each a skill file this
    row could not read. A skill directory without a `SKILL.md`, and a path under `SKILLS` that is
    not a directory, name no skill and are passed over, as a `SKILLS` that names nothing is. Each
    skill is named by its path, through `printed.printable`, because its directory name is the
    repository's."""
    directory = root / SKILLS
    try:
        with os.scandir(directory) as listing:
            names = sorted(entry.name for entry in listing)
    except OSError as exc:
        if exc.errno in NAMES_NO_FILE:
            return []
        return [(_SKILL_UNREAD, None, SKILLS)]
    found: list[_Found] = []
    for name in names:
        label = printable(f"{SKILLS}/{name}/{_SKILL_FILE}", _UNPRINTED_SKILL)
        try:
            content = read_regular_bytes(directory / name / _SKILL_FILE)
        except OSError as exc:
            if exc.errno not in NAMES_NO_FILE:
                found.append((_SKILL_UNREAD, None, label))
            continue
        # Replaced rather than refused, for the reason the settings walk replaces: the key is
        # ASCII, so a byte that is not UTF-8 elsewhere changes no answer.
        if _declares_hooks(content.decode("utf-8", errors="replace")):
            found.append((_SKILL_HOOKS, None, label))
    return found


def _classify(context: Context) -> tuple[int, int, list[_Finding]]:
    """How many entries claim the marker, how many are foreign, and every finding about them.

    The verdicts are `hook_entries`'; this decides each finding's kind and the area it is told
    for, and `_told` prints them.
    """
    answers = _area_claims(context)
    # An area whose record could not be read may hold any id, and nothing here can say which. It
    # is not an empty record: judged as one, every entry its area installed would read as
    # recorded nowhere, red, with a remedy telling the owner to remove it.
    unread = [answer for answer in answers if answer.recorded is None]
    askable = all(answer.granted is not None for answer in answers)
    found: list[_Found] = []
    for answer in answers:
        # An unreadable record is the area's finding whether or not its source can be asked: its
        # remedy says which way out is left.
        if answer.recorded is None:
            found.append((_UNREADABLE, answer, None))
        elif answer.granted is None:
            found.append((_UNASKABLE, answer, None))
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
            found.append((_BLIND, None, label))
            continue
        if not regular:
            continue
        try:
            # Replaced rather than refused: the marker and every command it marks are ASCII, so a
            # byte that is not UTF-8 elsewhere in the file changes no entry's verdict. Read to the
            # regular-file reader's cap, as every reader of a committed file is, so a file that
            # never ends, or one swapped for a device after the question above, is one this walk
            # cannot read.
            document = read_regular_bytes(path).decode("utf-8", errors="replace")
        except OSError:
            found.append((_BLIND, None, label))
            continue
        try:
            # The entries a harness runs out of the file, read as `harnesses.LENIENT_SETTINGS`
            # says its files were measured, and every other file strictly. A part this cannot
            # read for entries is named as one the walk is blind to, and a marked command in one
            # is red.
            read = judged_entries(document, lenient=relative in LENIENT_SETTINGS)
        except ParserLimitError:
            found.append((_UNCHECKED, None, label))
            continue
        except Refusal:
            found.append((_BLIND, None, label))
            continue
        if read.hidden:
            found.append((_HIDDEN, None, label))
        if read.partly:
            found.append((_BLIND, None, label))
        for position, placed in read.entries:
            entry_id = marker_id(placed.command)
            if entry_id is None:
                foreign += 1
                continue
            claimed += 1
            where = f"{label} entry {position} of {read.places}"
            holders = [answer for answer in answers if entry_id in (answer.recorded or {})]
            if not holders and not unread:
                # Needs the records alone, so a source that cannot be asked does not withhold
                # it: a committed record beside a committed entry it does not hold is red
                # whether or not this machine records a source.
                found.append((_UNRECORDED, None, where))
            elif askable and not any(_grants(answer, placed) for answer in holders):
                # Needs the sources too, and only a holder's own grant vouches for its record:
                # absolving an entry on a record alone, or on one area's record and another's
                # grant, is what this row may never do. Without a grant to compare, the entry is
                # neither absolved nor accused.
                if any(_grants(answer, placed) for answer in unread):
                    # An area whose record is unreadable grants it, so it may be that area's: the
                    # record that would say is the one missing, and the row warns that it is.
                    continue
                if not holders:
                    # Only an unreadable record could hold it and no grant covers it, so whatever
                    # that record says, nothing vouches: red, and said without claiming to know
                    # whether the record holds it. A record is a file a clone can commit, and an
                    # unreadable one withholding this verdict would turn a forged entry's red into
                    # a warning and an exit of 0.
                    # Told in the words of the first unreadable area whose source was asked and
                    # refused it, or, with none, of the first unreadable area.
                    asked = [answer for answer in unread if answer.sourced]
                    if asked:
                        found.append((_UNREAD_UNGRANTED, asked[0], where))
                    else:
                        found.append((_UNREAD_UNVOUCHED, unread[0], where))
                elif refusing := [answer for answer in holders if answer.sourced]:
                    # Told in the words of the first holder whose source refused it.
                    found.append((_UNGRANTED, refusing[0], where))
                else:
                    # No holder's machine records a source to grant from, so nothing could vouch
                    # for the entry: red as surely as a refused grant, said differently, because
                    # the way out is to record one rather than to re-run what it grants.
                    found.append((_UNVOUCHED, holders[0], where))
    found.extend(_skills(context.root))
    return claimed, foreign, _gathered(answers, found)


def _told(claimed: int, foreign: int, findings: Sequence[_Finding]) -> Row:
    """The row for `findings`: every finding's part, in order, after the count; red where any
    finding is red, a warning where any is one, and "all accounted for" where there is none; and
    the remedy of every finding of the highest step, each said once, joined as the parts are."""
    parts = [f"{claimed} stayfixed entr(ies), {foreign} foreign"]
    parts.extend(finding.kind.tell(finding.areas, finding.wheres) for finding in findings)
    statuses = {finding.kind.status for finding in findings}
    status: Status = RED if RED in statuses else WARN if statuses else OK
    if status == OK:
        parts.append("all accounted for")
    step = max((finding.kind.step for finding in findings), default=None)
    chosen = (
        finding.kind.remedy(finding.areas) for finding in findings if finding.kind.step == step
    )
    return Row(status, "; ".join(parts), "; ".join(dict.fromkeys(chosen)))


def hook_entries(context: Context) -> Row:
    """Every entry in every settings file, with provenance.

    Three provenances, and the third is the one a hostile clone makes necessary. An entry whose
    marker id one area records *and* that same area still grants where it sits is that area's;
    an entry with no marker is foreign and is left alone by every merge this project ships; an
    entry that **claims** the marker and cannot be vouched for is a repository saying it is
    stayfixed, which is a stronger statement than "foreign" and the one a reader needs. It is
    reported by position — see `checks.py`'s module docstring for why not by name.

    What each area recorded and what it grants are the areas' to answer, because the areas wrote
    them: each hands its `Claims` to this row (`_area_claims`), and the contract is the one `Claims`
    states. A record may be repository bytes — `attach`'s is `.stayfixed/local/attach.json`, a
    path a clone can commit — so **a record alone may never turn an entry green**: otherwise a
    repository that committed a marked entry and a ledger recording its id would get this row to
    answer "all accounted for". An id is credible only beside a grant from a source the repository
    cannot choose, and only the same area's grant, so one area's record never borrows another's. The
    grant is the *marked command* and not the id, because an id that is granted with a different
    command hung on it is the same attack one step down; it is that command *where the area
    puts it*, under its event and its group's matcher (`_grants`), because the granted command
    hung under another event or matcher is the same attack one step further; and it is the whole
    entry the area writes, because the granted command inside an `http` entry, or beside an `args`
    or a `shell` of the repository's choosing, is that attack in one more field.

    Where a source this machine records cannot be asked, the answer is the one this check gives a
    file it could not parse: report it, never absolve it. That withholds the grant comparison and
    nothing more. Whether a record holds an entry's id needs only the records, so an entry no record
    holds is red whether or not a source can be asked: withholding that too would let a clone that
    commits a record beside its entry turn the row into a warning on any machine with no source. A
    machine that records no source at all is not one whose source could not be asked: there is
    nothing to ask and nothing vouches, so an entry a record holds is red there too, or a clone
    whose committed record holds its own entry would keep the exit code at 0. Where a record cannot
    be read, the row warns and names it, and withholds judgement only of an entry that record's own
    area grants: that entry may be one the record holds. An unreadable record is not an empty one,
    and judged as one it would report every entry its area installed as recorded nowhere, with a
    remedy telling the owner to remove it. But it is not a vouching one either: an entry no grant
    covers is red whatever the record would have said, because a clone can commit a record that
    will not parse as easily as one that does, and withholding the verdict there would turn a
    forged entry's red into a warning on every machine. Reading the record is the area's, which
    answers `None` rather than raising, so a committed file the area cannot parse never costs this
    row's guard.

    The red kinds are kept apart because their remedies differ. An entry in no record is one to
    open and delete; an entry a record holds and its source no longer grants is either a checkout
    that has drifted from the source or a forged record, and the area's `vouch` command settles
    which — it takes out every marked entry the source no longer grants, so anything surviving it
    was never stayfixed's; an entry a record holds on a machine that records no source is either
    the owner's checkout on a machine that has not recorded one yet or a forged record, and
    recording the source and then vouching settles which; and the last two again, for an entry
    only an unreadable record could hold, whose way out also writes the record anew.

    **Every sentence about a record or a source is in its area's own words** — `Claims.wording`,
    whose `Wording` says what each phrase is — because the record the row names is the file a
    reader opens and the command it names is the one they run: an area's entry told in another
    area's words sends them to a record that does not hold it. So the row is one table, `_KINDS`:
    each kind is told one part per area, in area order, and every kind's parts and remedies are
    joined the same way — an entry a record holds by the first holder whose source refused it, or
    the first holder where none records a source; an entry only an unreadable record could hold by
    the first such area whose source refused it, or the first such area; an unreadable record or an
    unaskable source by its own area. The remedy is every part's of the highest step, each said
    once, so two areas' entries of one kind each get their area's way out. An entry no record holds
    names every record it is missing from, and with no area claiming anything, none.

    **Entries are counted, never keys.** `scaffold.judged_entries` answers one element per entry,
    in document order, so N entries sharing one id are N entries and one id under two events is
    two. Keyed by id, as `owned_ids` answers, the claimed count would deflate and `foreign` inflate
    by exactly the difference. The count comes from `marker_id`, the predicate `owned_ids` is built
    on and the one `attach.write` keys its ledger with.

    **A file this walk could not read is `blind`, never silently absent.** An `OSError` on the
    read, a document that will not parse or is not an object, a `hooks` that is not an object, and
    a part of the `hooks` section that could hold a command it cannot read are each named, because
    "all accounted for" is the one answer this check must never give about entries it did not see.
    The report names the file and never its contents.

    **The entries a harness runs are judged, wherever they sit, in the files it was measured
    on.** For Claude Code's settings files (`harnesses.LENIENT_SETTINGS`, which says what was
    measured and when) the walk is not the engine's strict one, the one `apply_entries` rewrites
    through: Claude Code still ran the valid hooks of a file whose `hooks` section held a scalar
    where an event's list, a group, a group's `hooks` or an entry belongs, so a marked entry
    beside such a part is live, and one nothing vouches for is red. Every other file -- Codex's
    `.codex/hooks.json`, which no measurement covers -- is read by the strict walk, as before.
    Read strictly, Claude Code's whole file was `blind`, a warning, and a clone kept the exit code
    at 0 by committing one such scalar beside a forged entry. Not measured, and so not assumed: a
    container in one of those places, or an entry object where a group goes, which may hold a
    command, leaves the file `blind` as well as judging the entries beside it; and a command
    claiming the stayfixed marker inside one is red. That last is a conservative reading, not a
    measurement: whether a harness runs it is not known, and a clone could otherwise hide a
    forged entry there and keep the exit code at 0. Every element of an entry list holds a place
    in the count, so an entry is named where a person opening the file finds it.

    **A byte that is not UTF-8 does not make a file `blind`.** The file is decoded with each such
    byte replaced, because the marker and the commands it marks are ASCII, so the entries in it
    are judged as they would be without the byte; a harness may read the file the same way, so
    a marked entry in it nothing vouches for is red. In Claude Code's settings files a UTF-8
    byte-order mark ahead of the document is read past: `json.loads` refuses it, and Claude Code
    runs the hooks of such a file (`harnesses.LENIENT_SETTINGS`), so it is no reason to be
    `blind` there. In any other file it still is.

    **A file this walk refuses only for a limit of Python's parser is red, never `blind`.** Blind
    is a warning, which is right for a file this machine will not let anything read and for one
    that will not parse, because the harness cannot load either. Valid JSON nested deeper than the
    parser follows is neither: a harness may read it (Claude Code's parser does), so the hooks in
    it may run, and a warning there would let a clone commit a marked entry beside such nesting and
    keep the exit code at 0 whatever the ledger or the overlay said. Only this machine's state may
    leave unknown the provenance of an entry a harness may run. A number longer than the
    interpreter converts is not refused at all: either walk reads it as its text, and the
    entries beside it are judged as they would be without it.

    **A project skill's hooks are named, never judged.** Claude Code runs a hook a committed
    skill's frontmatter declares once the skill is invoked (`SKILLS` says what was measured), and
    this row judges settings files, so "all accounted for" beside such a skill would claim more
    than the row looked at. Each skill whose frontmatter holds a top-level `hooks:` key, and each
    whose `SKILL.md` could not be read, is a warning naming it (`_skills`): never red, because
    what a skill's hooks are and whether stayfixed put them there is nothing this row reads.
    """
    return _told(*_classify(context))
