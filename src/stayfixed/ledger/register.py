"""What one ledger is, as a value the engine is handed: its paths, its identifiers, its schema.

The engine — reading entries, rendering the index, filing and moving an entry, checking the
ledger against the tree and its base — knows no ledger by name. Everything that makes the bug
ledger the bug ledger is here: the keys an entry carries, the statuses and severities it may hold,
the body `bugs new` scaffolds, the index's sections, and where it lives. A second ledger is a
second `Register`, not a second engine.

A leaf of this area: every other module of it imports this one, and it imports none of them.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from string import Formatter
from typing import TYPE_CHECKING

from stayfixed.identifiers import Identifiers

if TYPE_CHECKING:
    from stayfixed.config.schema import Config

EVIDENCE_LABEL = "**What this evidence does not establish:**"
# The template writes this after the label; a `high` entry with the placeholder untouched has
# not filled the line in. One constant feeds both the template and the rule so they cannot
# drift apart.
EVIDENCE_PLACEHOLDER = "the reading a later plan must not inherit"

# The keys the engine reads and writes itself, whatever the register: every entry's `id`, `title`
# and `status`, and the `related` list `renumber`'s void entry names the new number in. `Entry`
# carries them as fields of its own, `new` spells them rather than take a value for them (`status`
# as the template's own literal, the rest through `{identifier}`, `{title}` and `{related}`), and
# the void entry fills each. Every other key is the register's.
ENGINE_KEYS = ("id", "title", "status", "related")


@dataclass(frozen=True)
class Section:
    """One section of the generated index: its heading, the statuses it gathers, its table.

    `columns` is `(heading, key)` per column. The `id` key renders as the link to the entry's
    file; every other key renders the entry's value for it, inside its cell.
    """

    heading: str
    statuses: tuple[str, ...]
    columns: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class Schema:
    """What an entry of one register holds, and how its index reads.

    Built consistent or not at all: a key or a status that one part names and another lacks is
    refused here, where the register is written, rather than as a `KeyError` on the first entry
    that reaches it. The template is not read here: the entry reader owns the grammar of what it
    writes, and a test round-trips every shipped register's scaffold and void entry through that
    reader (`tests/ledger/test_register.py`), so a template is held to the one grammar there is.
    """

    keys: tuple[str, ...]  # frontmatter keys, in the order an entry writes them
    required: tuple[str, ...]
    # The void status records a number that was allocated and never carried an entry, so it has
    # none of these to record.
    required_unless_void: tuple[str, ...]
    statuses: tuple[str, ...]
    void: str  # the status of a number that never carried an entry
    level: str  # the key whose value is one of `levels`
    levels: tuple[str, ...]  # the values `level` may hold: the bug ledger's severities
    dates: tuple[str, ...]  # keys whose value is an ISO date
    # The file `new` writes. The writer fills `{identifier}`, `{title}`, `{today}` and
    # `{related}`; any other placeholder names a key outside `ENGINE_KEYS` and stands for that
    # key's whole `key: value` line, so an absent value leaves a bare `key:` behind (the trailing
    # space of `source: ` is whitespace an editor strips on save). A key with no placeholder is
    # one the template spells itself, as the bug ledger's does `found` and `fixed_in`.
    template: str
    sections: tuple[Section, ...]  # in the order the index reads

    def __post_init__(self) -> None:
        problems = list(_inconsistencies(self))
        if problems:
            raise ValueError(f"inconsistent ledger schema: {'; '.join(problems)}")

    @property
    def line_keys(self) -> tuple[str, ...]:
        """The keys the template leaves to a value the writer is handed, in the order of `keys`."""
        placeholders = _placeholders(self.template)
        return tuple(key for key in self.keys if key in placeholders and key not in ENGINE_KEYS)


def _placeholders(template: str) -> set[str]:
    return {name for _, name, _, _ in Formatter().parse(template) if name}


def _inconsistencies(schema: Schema) -> Iterator[str]:
    """Every way one part of `schema` names what another part lacks."""
    keys = set(schema.keys)
    # A key listed twice is written twice by `new` and read once.
    duplicated = sorted({key for key in schema.keys if schema.keys.count(key) > 1})
    for key in duplicated:
        yield f"key `{key}` is listed more than once"
    # Every entry is read for its `id`, `title` and `status`; its `related` list may be empty.
    for key in ENGINE_KEYS:
        if key != "related" and key not in schema.required:
            yield f"`{key}` is read from every entry, so it must be required"
    for name, named in (
        ("required", schema.required),
        ("required_unless_void", schema.required_unless_void),
        ("dates", schema.dates),
    ):
        for key in named:
            if key not in keys:
                yield f"{name} names `{key}`, which is not a key"
    if schema.level not in keys:
        yield f"level `{schema.level}` is not a key"
    if schema.void not in schema.statuses:
        yield f"void `{schema.void}` is not a status"
    # Each status in exactly one section: an entry whose status no section gathers is left out of
    # the index in silence, and one gathered twice is listed twice.
    gathered = [status for section in schema.sections for status in section.statuses]
    for status in schema.statuses:
        if gathered.count(status) != 1:
            yield f"status `{status}` is gathered by {gathered.count(status)} sections, not one"
    for section in schema.sections:
        for status in section.statuses:
            if status not in schema.statuses:
                yield f"section `{section.heading}` gathers `{status}`, which is not a status"
        for _, key in section.columns:
            # `related` is a list, which no cell renders.
            if key not in keys or key == "related":
                yield (
                    f"section `{section.heading}` shows `{key}`, which is not a key a cell can show"
                )
    # A non-void entry must carry its level: `check` holds the entry's body to it.
    if schema.level not in (*schema.required, *schema.required_unless_void):
        yield f"level `{schema.level}` is neither required nor required_unless_void"
    # `renumber` leaves a void entry at the number it moves from, and that entry is held to
    # `required` like any other. It knows the engine's own keys, with the new number in `related`,
    # and the day of the move for a date; nothing else.
    for key in schema.required:
        if key not in ENGINE_KEYS and key not in schema.dates:
            yield f"required `{key}` is not a date, so `renumber`'s void entry cannot fill it"
    if "related" not in keys:
        yield "`related` is not a key, so `renumber`'s void entry cannot name the new number"


@dataclass(frozen=True)
class Register:
    """One ledger the engine serves.

    `directory` and `index` come from one of two places: `[paths]` values the configuration
    loader validated (`src/stayfixed/config/paths.py`: inside the root, no `.git`, no
    `.stayfixed`), or the shipped preset's own defaults (`preset_defaults`), which this package
    writes and a repository cannot. The engine does not check their spelling again, and still
    resolves each through `contained`, which refuses a symlink the tree holds when the engine
    reads or writes. `runbook` is a root-relative file and `audits` one plain directory name
    under `directory`, each `None` for a register without one. The index links both, and `init`
    writes a file at the bug ledger's two, so they must stay where a `[paths]` value may point:
    the runbook is `BUG_RUNBOOK` under `[paths] runbooks`, and `audits` is `BUG_AUDITS`, with no
    separator of its own. A register built from anything else is a defect."""

    name: str  # "bugs": the command group, and the noun in messages
    title: str  # "Bug reports": the index's heading
    directory: str
    index: str
    ids: Identifiers  # the bug ledger's is built from `[ledger] id_prefix`
    schema: Schema
    # The levels whose entries need a filled evidence line: the bug ledger's are `[ledger]
    # evidence_boundary_required_for`.
    evidence_boundary_for: tuple[str, ...]
    runbook: str | None  # the bug ledger's "<[paths] runbooks>/<BUG_RUNBOOK>", the index's link
    # the bug ledger's `BUG_AUDITS`: the subdirectory of `directory` holding audit records, which
    # the index links.
    audits: str | None


_BUG_TEMPLATE = f"""---
id: {{identifier}}
title: {{title}}
status: open
{{severity}}
{{area}}
found: {{today}}
{{source}}
fixed_in:
{{related}}
---

- **Found:** {{today}}
- **Where:** `path/to/file.py::symbol`

What goes wrong, what the user sees, and the evidence for it.

**Suggested fix:** what to change, and what must not change with it.

{EVIDENCE_LABEL} {EVIDENCE_PLACEHOLDER} —
name what the evidence is silent about, and what would have to be observed to settle it.
"""

# The bug ledger's runbook, a file under `[paths] runbooks`, and its audits directory, a
# subdirectory of `[paths] bugs`. `bug_register` links both from the index and `init` writes a file
# at each, both from these two names joined by `ledger_path`, so a link and the file it points at
# cannot be spelled apart.
BUG_RUNBOOK = "bug-reports.md"
BUG_AUDITS = "audits"


def ledger_path(directory: str, name: str) -> str:
    """`name` under the root-relative `directory`: a register's runbook or audits directory, as
    the index names it and `init` writes a file at it. The one place either is joined."""
    return f"{directory}/{name}"


_LIVE = (
    ("ID", "id"),
    ("Sev", "severity"),
    ("Area", "area"),
    ("Title", "title"),
    ("Found", "found"),
)

BUG_SCHEMA = Schema(
    keys=("id", "title", "status", "severity", "area", "found", "source", "fixed_in", "related"),
    required=("id", "title", "status", "found"),
    required_unless_void=("severity", "area"),
    statuses=("open", "partial", "fixed", "rejected", "void"),
    void="void",
    level="severity",
    levels=("high", "medium", "low"),
    dates=("found",),
    template=_BUG_TEMPLATE,
    # `Schema` refuses a status no section gathers; the reading order is pinned with every other
    # byte of the index by `test_the_bug_register_renders_the_index_byte_for_byte`.
    sections=(
        Section("Open", ("open",), _LIVE),
        Section("Partially fixed", ("partial",), _LIVE),
        Section("Rejected", ("rejected",), _LIVE),
        Section("Fixed", ("fixed",), (("ID", "id"), ("Title", "title"), ("Fixed in", "fixed_in"))),
        Section("Void identifiers", ("void",), (("ID", "id"), ("Why", "title"))),
    ),
)


def bug_register(config: Config) -> Register:
    """The bug ledger, as this project configures it."""
    paths = config.paths
    return Register(
        name="bugs",
        title="Bug reports",
        directory=paths.bugs,
        index=paths.bug_index,
        ids=Identifiers(config.ledger.id_prefix),
        schema=BUG_SCHEMA,
        evidence_boundary_for=tuple(config.ledger.evidence_boundary_required_for),
        runbook=ledger_path(paths.runbooks, BUG_RUNBOOK),
        audits=BUG_AUDITS,
    )
