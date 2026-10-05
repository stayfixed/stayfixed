"""What a `doctor` row is made of, and what an area hands the report to add rows of its own.

The vocabulary lives here rather than in `checks.py` because two kinds of module speak it: the
core's checks in `checks.py` and `entries.py`, and an area's own `doctor.py`, which
`registry.contributions` discovers by name and which reaches this module through `doctor/api.py`.
`checks.py` is the core's checks and the run; this module is the shapes they share and the one
answer every area reads alike, the overlay root (`Context.overlay_root`), so it imports nothing of
any area. `REPORT_THIS` is here too: the run's guard in `checks.py` and the rows `registry.py`
builds for an area that could not contribute both give it, and it is a remedy, part of what a row
is made of, rather than anything of the run's or of discovery's.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path
from typing import Final, Literal

from stayfixed.config.overlay import overlay_root as recorded_overlay_root
from stayfixed.config.schema import Config
from stayfixed.errors import resolved_or_none
from stayfixed.runner import Runner
from stayfixed.scaffold import Placed

OK: Final = "ok"
WARN: Final = "warn"
RED: Final = "red"
SKIP: Final = "skip"
Status = Literal["ok", "warn", "red", "skip"]
STATUSES: tuple[Status, ...] = (OK, WARN, RED, SKIP)
# The remedy of a row that is red because stayfixed's own code broke: nothing the reader did can
# clear it, and the command they ran is what a fix starts from.
REPORT_THIS = "report this, with the command you ran"


@dataclass(frozen=True)
class Check:
    """One row of the report: what was asked, what the answer was, and what to do about it.

    `remedy` is empty for a row nothing can be done about, and a `skip` is **not** entitled to
    an empty remedy merely for being a skip. The line is not "always" versus "on a state of the
    machine or the repository", and it is not whether some command elsewhere in the report would
    change that state: it is whether **the skip is itself worth acting on**. A skip that reports
    something wrong which no other row will say — a plugin root nothing can find, which is every
    hook entry on this machine silent; a recorded state nothing could corroborate; a recorded path
    that is not there — says what to do. A skip that reports a measurement that is simply not
    available — nothing recorded to measure, no data root, no way to ask — and that no command in
    that row's gift changes, carries nothing. A reader is never handed a command that would not
    help, and never denied one that would.

    One row may have both kinds of arm: a machine that never recorded something and one that
    recorded it and then moved it are two states with two sentences, and only the second carries
    a remedy. Which of the report's rows skip, on what, and which of those arms carry a remedy is
    `docs/cli.md`'s census, not this type's.
    """

    name: str
    status: Status
    detail: str
    remedy: str = ""


@dataclass(frozen=True)
class Row:
    """What one check answers. The name is the registry's, stamped by `checks._guarded`."""

    status: Status
    detail: str
    remedy: str = ""


@dataclass(frozen=True)
class Context:
    """Everything a check may read for one report, built whole by `checks.run_checks` and never
    changed after.

    Built only once the configuration has loaded, so `config` is never `None` here: a repository
    whose configuration does not load has nothing else worth asking about, and the first check
    says so and the rest skip.

    **What the core answers for, and what every area reads alike.** The fields are the core's:
    the run's inputs, the configuration, the two plugin roots, and the `claims` the areas
    contributed. `overlay_root` is the core's too — `[overlay] root` is a key of the machine file,
    which the core owns (`config.overlay`) — and is here because more than one area reads it, so
    it is resolved once per report for all of them. What an area owns — the note store, the
    attach ledger, the binding — is resolved inside that area's own `doctor.py` and never reaches
    this type, so building it imports nothing of any area.
    """

    root: Path
    home: Path | None
    machine: Path | None
    runner: Runner
    env: Mapping[str, str]
    config: Config
    plugin_root: Path | None = None
    # The plugin root this process can vouch for, which is the only one anything here executes.
    # `plugin_root` may be a root the environment named; this is `None` unless self-derivation
    # answered. Two fields and not a flag, because the check that runs the wrapper should not be
    # able to reach the other answer at all.
    own_root: Path | None = None
    # Every contributing area's `Contribution.claims`, in area-name order. Carried and not
    # answered: `hook-entries` asks each under its own guard, so claims that raise cost that row,
    # red, as `Contribution.claims` promises, and never the report.
    claims: tuple[Callable[[Context], Claims], ...] = ()

    @cached_property
    def overlay_root(self) -> Path | None:
        """The overlay root the machine file records, whether or not anything is there; `None`
        when it records none, or when it cannot be read.

        Resolved on first read and never again for this report: `cached_property` keeps the
        answer in the instance's `__dict__` without going through `__setattr__`, which is why a
        frozen dataclass without slots can carry it, and an answer that is itself `None` is kept
        as well. A fresh `Context` per report is a fresh answer per report, so nothing one run
        resolved reaches the next.

        A resolution that fails is `None`, as a machine that records no overlay is
        (`errors.resolved_or_none`): a machine file that names an overlay nothing can read is a
        row's skip, never "this check could not run", which is red and gates the exit code for
        something the repository did not do wrong.
        """
        return resolved_or_none(lambda: recorded_overlay_root(self.machine))


@dataclass(frozen=True)
class Wording:
    """How `hook-entries` names one area's record, the source that grants, and the commands that
    repair them, so the core's sentences about an area's entries are in that area's words.

    Each field is a complete phrase the row composes into its sentences and remedies verbatim:
    `record` names the record ("are recorded in {record}"), and `unreadable` follows "{record} is
    there and"; `inspect` is the remedy for a record that cannot be read beside a source that
    cannot be asked either; `source` is the source as a noun phrase ("{source} does not grant
    them"), `unsourced` the clause for a machine that records none, `unaskable` the clause for one
    that could not be asked, and `diagnose` the remedy for that; `setup` is the remedy that records
    a source, and `vouch` the command, quoted as the row prints it, that writes the area's entries
    and its record anew from its source, taking out every marked entry the source no longer grants.
    `ungranted` and `regrant` are for a source that answered and does not grant *this checkout*
    what it grants the one it is for, where "{source} does not grant them" would be false and
    `vouch` may be refused: the clause that says why, in place of that one, and the remedy for the
    entries it leaves red, in place of the ones built from `vouch`. `None` keeps those, because
    then the source refusing is what happened.

    **These are stayfixed's own fixed strings, never repository bytes.** The row prints them
    unquoted into `Check.detail`, `--json` and the remedy a skill relays verbatim, so an area must
    not build one from anything a repository authored — a configured name, a path read from a
    record, a value a clone could commit. A repository's bytes are data (principle 5), and this is
    the one place a contributing area's text reaches the core's output whole.
    """

    record: str
    unreadable: str
    inspect: str
    source: str
    unsourced: str
    unaskable: str
    diagnose: str
    setup: str
    vouch: str
    ungranted: str | None = None
    regrant: str | None = None


@dataclass(frozen=True)
class Claims:
    """What an area put into settings files, for `hook-entries`' provenance column.

    `recorded` is the marker ids the area's record says it wrote, by event, and may be repository
    bytes: `attach`'s record is a file a clone can commit. `granted` is the entries the area
    grants right now, each a marked command **where the area puts it** — its event and its group's
    matcher, as `scaffold.Placed` holds them — and **must come from a source the repository cannot
    choose** — `attach` asks the overlay whose root the machine file records — because it is the
    half that vouches. An entry is absolved only when one area both records its id and grants it
    there: its command, under its event, in a group with its matcher. A granted command anywhere
    else is a hook the area never installed, because the event is when a harness runs it and the
    matcher for which tools. One area's record never stands on another area's grant. `wording` is
    how the row names that record, that source and the commands that repair them, and holds
    `Wording`'s invariant: stayfixed's own fixed strings, never anything a repository authored.

    Every answer the two sources can give is carried, their `None`s included: `recorded is None` is
    "the record could not be read" (the row warns and says so, and withholds judgement only of an
    entry this area grants, which may be one the record holds: an entry no grant covers is still
    red, so an area must answer `granted` whether or not its record could be read), `granted is
    None` is "the source could not be asked" (the row warns and withholds only the comparison with
    what is granted: an entry no record holds is still red). A `None` from any one area is `None`
    for every area's entries, because what it would have said is not something another area can.

    **Whether `granted` is `None` is decided by this machine's state alone, never by the record.**
    A `None` turns this row's red into a warning, so a record — repository bytes — that could choose
    it could silence the row about the very entry it records. That holds for a record that cannot
    be read too: an unreadable record is repository bytes as well, which is why it withholds no
    more than its own area's grant covers. A machine that records no source to grant from is not
    one: there is nothing to ask, nothing grants, `granted` is empty and `sourced` is `False`,
    which changes the row's sentence and remedy and never its verdict."""

    recorded: Mapping[str, str] | None
    granted: frozenset[Placed] | None
    sourced: bool = True
    # Keyword-only and required: an area's claims without its own words would be told in some
    # other area's, which is the defect this field exists to end.
    wording: Wording = field(kw_only=True)


@dataclass(frozen=True)
class Contribution:
    """What an area's `doctor.py` hands the report from its `register()`.

    `checks` are `(name, check)` pairs, asked after the core's own in area-name order and each
    through the guard the core's go through, so one that raises costs its own row. A name is
    unique in the report: an area that repeats a core check's, another area's or its own costs
    its rows and its claims, as one red row named after the area.
    """

    checks: tuple[tuple[str, Callable[[Context], Row]], ...]
    # Must not raise on repository bytes: an answer it cannot read is a `None` field of `Claims`.
    # `hook-entries` asks it under its own guard, so one that raises costs that row, red.
    claims: Callable[[Context], Claims] | None = None
