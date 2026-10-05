"""The `hook-entries` row: every hook entry in every settings file, with its provenance.

A core check, listed in `checks.CHECKS` and asked through the run's guard like the others, and
the only one that reads what the areas contribute besides rows: each area's `Claims`, the ids it
recorded and the commands it grants, told in the area's own `Wording`. The walk over the settings
files, the rules for which area vouches for an entry, and the sentences each red list is told in
are one unit that no other check reads, so they sit in a module of their own and `checks.py`
stays the list of checks and the run. It imports nothing of the run's, so `checks.py` can import
it without a cycle.

What it may print is held to `checks.py`'s module docstring, and this row is where that ruling is
most tempting to break: an entry is named by its position in its file, never by the marker id it
claims, and that docstring says why.
"""

from __future__ import annotations

from collections.abc import Sequence

from stayfixed.doctor.model import OK, RED, WARN, Claims, Context, Row, Status, Wording
from stayfixed.errors import Refusal
from stayfixed.findings import listed
from stayfixed.fsops import names_regular_file
from stayfixed.harnesses import HARNESSES
from stayfixed.scaffold import ParserLimitError, entry_commands, marker_id
from stayfixed.setup.api import USER_SETTINGS

# Every file a hook entry can be installed into, as a path relative to a root: each harness's
# committed settings files and the ones it keeps out of git, read off the harness registry, so a
# harness added there is walked here without an edit. The two roots are the project (all of
# them) and `home` (`USER_SETTINGS` alone, which is where `setup` merges the preset's deny
# rules, and which `setup` reads off `CLAUDE.settings`: the same file under another root).
SETTINGS_FILES = tuple(
    relative for harness in HARNESSES for relative in (*harness.settings, *harness.local_settings)
)

# How the machine-scope copy of `USER_SETTINGS` is named in the report. A label and not a path:
# `home` is a directory this process was handed, and `~/.claude/settings.json` is what a reader
# would type. The project-relative members of `SETTINGS_FILES` name themselves.
_MACHINE_LABEL = f"~/{USER_SETTINGS}"


class UnansweredClaims(RuntimeError):
    """An area's claims raised. Never an `OSError`, whatever they raised, so the report's guard
    reads it as the red it is and not as the machine's warning."""


def _claimed(context: Context) -> tuple[list[Claims], bool, bool]:
    """Every area's `Claims`, and whether every record could be read and every source asked.

    An area's own record is the only thing that can say what it put into settings files, so the
    core asks each area that has one — `context.claims` — with this report's context and under
    this row's guard. The
    answers are kept apart rather than pooled: an entry is vouched for only by the one area that
    both records its id and grants its command, because a record is a file a repository can
    write, and one area's record standing on another area's grant vouches for an entry neither
    area put there whole. A `None` is still one for the whole: an id one record could not be read
    for, or a command one source could not be asked about, is not one the rest can vouch for.
    With no area claiming anything, nothing is recorded and nothing granted, so every entry
    claiming the marker is one no area put there.

    **Claims that raise are red, whatever they raise.** An area answers what it cannot read as a
    `None` field, so one that raises is a defect in its code, and `Contribution.claims` promises
    red for it. The guard reads an `OSError` as the machine's and warns, so a `PermissionError` out
    of an area's claims, reaching it as itself, would turn the row — and every forged entry it
    would have listed — into a warning and an exit of 0. It is raised on as `UnansweredClaims`,
    which the guard names in the row; the exception it chains carries the original, whose message is
    never printed, because an area may have built it from repository bytes.
    """
    try:
        answers = [ask(context) for ask in context.claims]
    except Exception as exc:  # an area's own code: red, never the guard's warning for `OSError`
        raise UnansweredClaims(type(exc).__name__) from exc
    readable = all(answer.recorded is not None for answer in answers)
    askable = all(answer.granted is not None for answer in answers)
    return answers, readable, askable


def _rebuild(words: Wording) -> str:
    """How an owner gets an area's unreadable record back: remove it, and have the area write a
    new one from its source — an area that writes a record refuses to write over one it cannot
    read."""
    return f"remove {words.record} and run {words.vouch} to write a new one"


def _refused(words: Wording) -> str:
    """The clause saying an area's source does not vouch for entries it was asked about: that it
    does not grant them, or the area's own `ungranted` where that would be false."""
    return words.ungranted or f"{words.source} does not grant them"


def _by_area(
    answers: Sequence[Claims], told: Sequence[tuple[Claims, str]]
) -> list[tuple[Claims, list[str]]]:
    """`told`'s entries gathered under the area whose words tell them, in area order, leaving out
    an area with none."""
    gathered = [(answer, [where for owner, where in told if owner is answer]) for answer in answers]
    return [(answer, wheres) for answer, wheres in gathered if wheres]


def _hook_entries(context: Context) -> Row:
    """Every entry in every settings file, with provenance.

    Three provenances, and the third is the one a hostile clone makes necessary. An entry whose
    marker id one area records *and* whose command that same area still grants is that area's;
    an entry with no marker is foreign and is left alone by every merge this project ships; an
    entry that **claims** the marker and cannot be vouched for is a repository saying it is
    stayfixed, which is a stronger statement than "foreign" and the one a reader needs. It is
    reported by position — see `checks.py`'s module docstring for why not by name.

    What each area recorded and what it grants are the areas' to answer, because the areas wrote
    them: each hands its `Claims` to this row (`_claimed`), and the contract is the one `Claims`
    states. A record may be repository bytes — `attach`'s is `.stayfixed/local/attach.json`, a
    path a clone can commit — so **a record alone may never turn an entry green**: otherwise a
    repository that committed a marked entry and a ledger recording its id would get this row to
    answer "all accounted for". An id is credible only beside a grant from a source the repository
    cannot choose, and only the same area's grant, so one area's record never borrows another's. The
    grant is the *marked command* and not the id, because an id that is granted with a different
    command hung on it is the same attack one step down.

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

    The red lists are kept apart because their remedies differ. An entry in no record is one to
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
    area's words sends them to a record that does not hold it. So each red list is told one part
    per area, in area order: an entry a record holds by the first holder whose source refused it,
    or the first holder where none records a source; an entry only an unreadable record could
    hold by the first such area whose source refused it, or the first such area; and the remedy
    is the last part's. An unreadable record or an unaskable source is a part of its own per area,
    and their remedies are joined. An entry no record holds names every record it is missing
    from, and with no area claiming anything, none.

    **Entries are counted, never keys.** `scaffold.entry_commands` answers one command per entry,
    in document order, so N entries sharing one id are N entries and one id under two events is
    two. Keyed by id, as `owned_ids` answers, the claimed count would deflate and `foreign` inflate
    by exactly the difference. The count comes from `marker_id`, the predicate `owned_ids` is built
    on and the one `attach.write` keys its ledger with.

    **A file this walk could not read is `blind`, never silently absent.** An `OSError` on the
    read and a document the engine refuses are each named, because "all accounted for" is the one
    answer this check must never give about entries it did not see. `entry_commands` reads the
    document with the engine's own strict walk, the one `apply_entries` rewrites through, so a
    shape the merge would refuse is exactly the shape this walk admits it cannot account for. The
    report names the file and never its contents.

    **A byte that is not UTF-8 does not make a file `blind`.** The file is decoded with each such
    byte replaced, because the marker and the commands it marks are ASCII, so the entries in it
    are judged as they would be without the byte; a harness may read the file the same way, so
    a marked entry in it nothing vouches for is red. Only what then fails to parse is `blind` —
    a UTF-8 byte-order mark among it, which `json.loads` refuses as Node's parser does — and an
    `OSError` on the read.

    **A file this walk refuses only for a limit of Python's parser is red, never `blind`.** Blind
    is a warning, which is right for a file this machine will not let anything read and for one
    that will not parse, because the harness cannot load either. Valid JSON nested deeper than the
    parser follows is neither: a harness may read it (Claude Code's parser does), so the hooks in
    it may run, and a warning there would let a clone commit a marked entry beside such nesting and
    keep the exit code at 0 whatever the ledger or the overlay said. Only this machine's state may
    leave unknown the provenance of an entry a harness may run. A number longer than the
    interpreter converts is not refused at all: `entry_commands` reads it as its text, and the
    entries beside it are judged as they would be without it.
    """
    answers, readable, askable = _claimed(context)
    claimed = 0
    foreign = 0
    unrecorded: list[str] = []
    # Each red entry a record holds, or only an unreadable record could, beside the area whose
    # words tell it: a record and a remedy are an area's, so each list is told one part per area.
    unvouched: list[tuple[Claims, str]] = []
    ungranted: list[tuple[Claims, str]] = []
    unread_unvouched: list[tuple[Claims, str]] = []
    unread_ungranted: list[tuple[Claims, str]] = []
    unchecked: list[str] = []
    blind: list[str] = []
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
            blind.append(label)
            continue
        if not regular:
            continue
        try:
            # Replaced rather than refused: the marker and every command it marks are ASCII, so a
            # byte that is not UTF-8 elsewhere in the file changes no entry's verdict.
            document = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            blind.append(label)
            continue
        try:
            # The engine's own reader, so a document `apply_entries` would refuse is one this walk
            # names rather than silently tolerates.
            commands = entry_commands(document)
        except ParserLimitError:
            unchecked.append(label)
            continue
        except Refusal:
            blind.append(label)
            continue
        for position, command in enumerate(commands, start=1):
            entry_id = marker_id(command)
            if entry_id is None:
                foreign += 1
                continue
            claimed += 1
            where = f"{label} entry {position} of {len(commands)}"
            holders = [answer for answer in answers if entry_id in (answer.recorded or {})]
            # An area whose record could not be read may hold this id or may not, and nothing
            # here can say which. It is not an empty record: judged as one, every entry its area
            # installed would read as recorded nowhere, red, with a remedy telling the owner to
            # remove it.
            unread = [answer for answer in answers if answer.recorded is None]
            if not holders and not unread:
                # Needs the records alone, so a source that cannot be asked does not withhold
                # it: a committed record beside a committed entry it does not hold is red
                # whether or not this machine records a source.
                unrecorded.append(where)
            elif askable and not any(command in (answer.granted or ()) for answer in holders):
                # Needs the sources too, and only a holder's own grant vouches for its record:
                # absolving an entry on a record alone, or on one area's record and another's
                # grant, is what this row may never do. Without a grant to compare, the entry is
                # neither absolved nor accused.
                if any(command in (answer.granted or ()) for answer in unread):
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
                        unread_ungranted.append((asked[0], where))
                    else:
                        unread_unvouched.append((unread[0], where))
                elif refusing := [answer for answer in holders if answer.sourced]:
                    # Told in the words of the first holder whose source refused it.
                    ungranted.append((refusing[0], where))
                else:
                    # No holder's machine records a source to grant from, so nothing could vouch
                    # for the entry: red as surely as a refused grant, said differently, because
                    # the way out is to record one rather than to re-run what it grants.
                    unvouched.append((holders[0], where))
    parts = [f"{claimed} stayfixed entr(ies), {foreign} foreign"]
    status: Status = OK
    remedy = ""
    # Every sentence and remedy below about an area's record or source is told in that area's
    # `Wording`, never in one area's words for another's: a record the row names is the one the
    # reader opens, and a command it names is the one they run.
    if not readable:
        status = WARN
        unreadable = [answer for answer in answers if answer.recorded is None]
        parts.extend(
            f"{answer.wording.record} is there and {answer.wording.unreadable}"
            for answer in unreadable
        )
        # Rebuilding needs the source the area writes from, so where that area's source cannot
        # be asked the remedy stays with the file.
        remedy = "; ".join(
            _rebuild(answer.wording) if answer.granted is not None else answer.wording.inspect
            for answer in unreadable
        )
    elif not askable:
        status = WARN
        unasked = [answer for answer in answers if answer.granted is None]
        parts.extend(
            f"{answer.wording.unaskable}, so nothing here vouches for the ones claiming the marker"
            for answer in unasked
        )
        remedy = "; ".join(answer.wording.diagnose for answer in unasked)
    if unrecorded:
        status = RED
        # Every record was read and none holds these, so the sentence names each of them; with
        # no area claiming anything there is no record to name, and nothing records them.
        records = list(dict.fromkeys(answer.wording.record for answer in answers))
        missing = (
            f"are not recorded in {' or '.join(records)}" if records else "are recorded nowhere"
        )
        parts.append(
            f"{len(unrecorded)} entr(ies) claim the stayfixed marker and {missing}: "
            f"{listed(unrecorded)}"
        )
        remedy = "open each entry named above and remove the ones you did not install"
    for answer, wheres in _by_area(answers, unvouched):
        status = RED
        words = answer.wording
        parts.append(
            f"{len(wheres)} entr(ies) claim the stayfixed marker and are recorded in "
            f"{words.record}, and {words.unsourced}, so nothing on this machine vouches for them: "
            f"{listed(wheres)}"
        )
        remedy = (
            "open each entry named above and remove the ones you did not install; if you did "
            f"install them, {words.setup}, then {words.vouch}"
        )
    for answer, wheres in _by_area(answers, ungranted):
        status = RED
        words = answer.wording
        parts.append(
            f"{len(wheres)} entr(ies) claim the stayfixed marker and are recorded in "
            f"{words.record}, and {_refused(words)}: {listed(wheres)}"
        )
        remedy = words.regrant or (
            f"run {words.vouch}, which takes out every marked entry {words.source} no longer "
            f"grants; open any that survive it"
        )
    for answer, wheres in _by_area(answers, unread_unvouched):
        status = RED
        words = answer.wording
        parts.append(
            f"{len(wheres)} entr(ies) claim the stayfixed marker and {words.unsourced}, so "
            f"whatever {words.record} records, nothing on this machine vouches for them: "
            f"{listed(wheres)}"
        )
        remedy = (
            "open each entry named above and remove the ones you did not install; if you did "
            f"install them, {words.setup}; then {_rebuild(words)}"
        )
    for answer, wheres in _by_area(answers, unread_ungranted):
        status = RED
        words = answer.wording
        parts.append(
            f"{len(wheres)} entr(ies) claim the stayfixed marker and {_refused(words)}, so "
            f"whatever {words.record} records, nothing on this machine vouches for them: "
            f"{listed(wheres)}"
        )
        remedy = (
            "open each entry named above and remove the ones you did not install; then "
            f"{words.regrant or _rebuild(words)}"
        )
    if unchecked:
        status = RED
        parts.append(
            f"{len(unchecked)} settings file(s) are nested deeper than this check can follow, so "
            f"nothing here can check the entries in them: {listed(unchecked)}"
        )
        remedy = (
            "open each file named above and remove what you did not put there; stayfixed writes "
            "no settings file nested that deep"
        )
    if blind:
        # A file this walk cannot read softens a row with nothing else to say, never a red one.
        red = (unrecorded, unvouched, ungranted, unread_unvouched, unread_ungranted, unchecked)
        status = RED if any(red) else WARN
        parts.append(
            f"{len(blind)} settings file(s) exist and could not be read as hook entries, so "
            f"nothing here accounts for what is in them: {listed(blind)}"
        )
        remedy = remedy or "check that each file named above is readable and is valid JSON"
    if status == OK:
        parts.append("all accounted for")
    return Row(status, "; ".join(parts), remedy)
