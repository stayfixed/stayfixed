"""What one ledger is, as a value the engine is handed: its paths, its identifiers, its schema.

The engine — reading entries, rendering the index, filing an entry — knows no ledger by name.
Everything that makes the bug ledger the bug ledger is here: the keys an entry carries, the
statuses and severities it may hold, the body `bugs new` scaffolds, the index's sections, and
where it lives. A second ledger is a second `Register`, not a second engine.

A leaf of this area: `entries`, `index` and `write` import it, and it imports none of them.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, replace
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

# The keys the reader takes from every entry, whatever its status.
_READ_KEYS = ("id", "title", "status")
# The keys the writer spells itself rather than from a value it is handed: `id`, `title` and
# `related` through the placeholders below, and `status` as the template's own literal.
_WRITER_KEYS = ("id", "title", "status", "related")
# The placeholders the writer fills itself; every other placeholder is a key's whole line.
_WRITER_FILLS = ("identifier", "title", "today", "related")


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

    Built consistent or not at all: a key, a status or a placeholder that one part names and
    another lacks is refused here, where the register is written, rather than as a `KeyError` on
    the first entry that reaches it.
    """

    keys: tuple[str, ...]  # frontmatter keys, in the order an entry writes them
    required: tuple[str, ...]
    # The void status records a number that was allocated and never carried an entry, so it has
    # none of these to record.
    required_unless_void: tuple[str, ...]
    statuses: tuple[str, ...]
    void: str  # the status of a number that never carried an entry
    level: str  # the key whose value is one of `levels`
    levels: tuple[str, ...]  # the bug ledger's severities
    evidence_boundary_for: tuple[str, ...]  # levels whose entries need the evidence line
    dates: tuple[str, ...]  # keys whose value is an ISO date
    # The file `new` writes. The writer fills `{identifier}`, `{title}`, `{today}` and
    # `{related}`; any other placeholder names a key outside `_WRITER_KEYS` and stands for that
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
        return tuple(key for key in self.keys if key in placeholders and key not in _WRITER_KEYS)


def _placeholders(template: str) -> set[str]:
    return {name for _, name, _, _ in Formatter().parse(template) if name}


def _inconsistencies(schema: Schema) -> Iterator[str]:
    """Every way one part of `schema` names what another part lacks."""
    keys = set(schema.keys)
    for key in _READ_KEYS:
        if key not in schema.required:
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
    lines = keys - set(_WRITER_KEYS)
    for placeholder in sorted(_placeholders(schema.template) - set(_WRITER_FILLS)):
        if placeholder not in lines:
            yield f"the template's `{{{placeholder}}}` is not a line of a key the writer is handed"


@dataclass(frozen=True)
class Register:
    """One ledger the engine serves.

    `directory` and `index` must be `[paths]` values the configuration loader validated
    (`src/stayfixed/config/paths.py`: inside the root, no `.git`, no `.stayfixed`): the engine
    does not check their spelling again, and still resolves each through `contained`, which
    refuses a symlink the tree holds when the engine reads or writes. A register built from
    anything else is a defect."""

    name: str  # "bugs": the command group, and the noun in messages
    title: str  # "Bug reports": the index's heading
    directory: str
    index: str
    ids: Identifiers  # `Identifiers(config.ledger.id_prefix)`
    schema: Schema
    runbook: str | None  # "<[paths] runbooks>/bug-reports.md", the index's link
    # "audits": the subdirectory of `directory` holding audit records, which the index links.
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

_LIVE = (
    ("ID", "id"),
    ("Sev", "severity"),
    ("Area", "area"),
    ("Title", "title"),
    ("Found", "found"),
)

# The bug ledger's schema as far as it does not depend on a project: `evidence_boundary_for` is
# `[ledger] evidence_boundary_required_for`, which `bug_register` fills in.
BUG_SCHEMA = Schema(
    keys=("id", "title", "status", "severity", "area", "found", "source", "fixed_in", "related"),
    required=("id", "title", "status", "found"),
    required_unless_void=("severity", "area"),
    statuses=("open", "partial", "fixed", "rejected", "void"),
    void="void",
    level="severity",
    levels=("high", "medium", "low"),
    evidence_boundary_for=(),
    dates=("found",),
    template=_BUG_TEMPLATE,
    # `Schema` refuses a status no section gathers; the reading order is pinned as a literal by
    # `test_every_status_has_a_section_to_be_rendered_into`.
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
        schema=replace(
            BUG_SCHEMA, evidence_boundary_for=tuple(config.ledger.evidence_boundary_required_for)
        ),
        runbook=f"{paths.runbooks}/bug-reports.md",
        # `init` writes the audits README into `<[paths] bugs>/audits/`.
        audits="audits",
    )
