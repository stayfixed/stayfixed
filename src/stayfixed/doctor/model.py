"""What a `doctor` row is made of, and what an area hands the report to add rows of its own.

The vocabulary lives here rather than in `checks.py` because two kinds of module speak it: the
core's checks in `checks.py`, and an area's own `doctor.py`, which `checks.run_checks` discovers by
name and which reaches this module through `doctor/api.py`. `checks.py` is the core's checks and
the run; this module is only the shapes they share, so it imports nothing of any area.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final, Literal

from stayfixed.config.schema import Config
from stayfixed.runner import Runner

OK: Final = "ok"
WARN: Final = "warn"
RED: Final = "red"
SKIP: Final = "skip"
Status = Literal["ok", "warn", "red", "skip"]
STATUSES: tuple[Status, ...] = (OK, WARN, RED, SKIP)


@dataclass(frozen=True)
class Check:
    """One row of the report: what was asked, what the answer was, and what to do about it.

    `remedy` is empty for a row nothing can be done about, and a `skip` is **not** entitled to
    an empty remedy merely for being a skip: seven of the report's sixteen skip arms carry one,
    counting the two arms `pre-commit` and `overlay-requires` share once for each of those rows.
    The line is not "always" versus "on a state" — eight state arms over seven rows are empty
    (`checks._files` on a build with no release record, `bundles`, `store-debris`, `diagnostics`,
    `ci-ref`, `overlay-requires` twice, and `pre-commit`), and `pre-commit`'s state is changed by
    the very command `attached` names when it skips for a machine that records no overlay. It is
    whether **the skip is itself worth acting on**: the two rows that report a plugin root nothing
    can find, which is every hook entry on this machine silent; `wrapper`'s row for a root it will
    read and never execute; the two ways a ledger's recorded attach cannot be corroborated; and
    the two rows that report an overlay root this machine records and cannot find, which is the
    store broken as well as them.
    Those seven say what to do. The other nine report a measurement that is simply not available —
    no store, no overlay, no overlay requirement, no harness data root, no `[ci] ref`, no release
    record in this build, no way to ask Codex — and no command in that row's gift changes it. A
    reader is never handed a command that would not help, and never denied one that would.

    The two overlay rows have *both* kinds of arm, and share both: the empty one is the machine
    that never recorded an overlay, and the one with a remedy is the machine that recorded one and
    moved it. They used to be one arm with one sentence, and the sentence was the first one.
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


@dataclass
class Context:
    """Everything a check may read, resolved once per run.

    Built by `checks.run_checks` after `not-initialised` has passed, so `config` is never `None`
    here: a repository whose configuration does not load has nothing else worth asking about, and
    the first check says so and the rest skip.

    Only what the core answers for. An area that needs more — the overlay root, the note store —
    resolves it inside its own `doctor.py`, so nothing an area owns is reachable from here.
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


@dataclass(frozen=True)
class Claims:
    """What an area put into settings files, for `hook-entries`' provenance column.

    `recorded` is the marker ids the area's record says it wrote, by event, and may be repository
    bytes: `attach`'s record is a file a clone can commit. `granted` is the marked commands the area
    grants right now, and **must come from a source the repository cannot choose** — `attach` asks
    the overlay whose root the machine file records — because it is the half that vouches. An entry
    is absolved only when one area both records its id and grants its command; one area's record
    never stands on another area's grant. `wording` is how the row names that record, that source
    and the commands that repair them, and holds `Wording`'s invariant: stayfixed's own fixed
    strings, never anything a repository authored.

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
    granted: frozenset[str] | None
    sourced: bool = True
    # Keyword-only and required: an area's claims without its own words would be told in some
    # other area's, which is the defect this field exists to end.
    wording: Wording = field(kw_only=True)


@dataclass(frozen=True)
class Contribution:
    """What an area's `doctor.py` hands the report from its `register()`.

    `checks` are `(name, check)` pairs, asked after the core's own in area-name order and each
    through the guard the core's go through, so one that raises costs its own row. A name is
    unique in the report: discovery refuses one equal to a core check's or another area's.
    """

    checks: tuple[tuple[str, Callable[[Context], Row]], ...]
    # Must not raise on repository bytes: an answer it cannot read is a `None` field of `Claims`.
    # `hook-entries` asks it under its own guard, so one that raises costs that row, red.
    claims: Callable[[Context], Claims] | None = None
