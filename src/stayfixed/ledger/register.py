"""What one ledger is, as a value the engine is handed: its paths, its identifiers, its schema.

The engine — reading entries, rendering the index, filing an entry — knows no ledger by name.
Everything that makes the bug ledger the bug ledger is here: the keys an entry carries, the
statuses and severities it may hold, the body `bugs new` scaffolds, the index's sections, and
where it lives. A second ledger is a second `Register`, not a second engine.

A leaf of this area: `entries`, `index` and `write` import it, and it imports none of them.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from stayfixed.identifiers import Identifiers

if TYPE_CHECKING:
    from stayfixed.config.schema import Config

EVIDENCE_LABEL = "**What this evidence does not establish:**"
# The template writes this after the label; a `high` entry with the placeholder untouched has
# not filled the line in. One constant feeds both the template and the rule so they cannot
# drift apart.
EVIDENCE_PLACEHOLDER = "the reading a later plan must not inherit"


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
    keys: tuple[str, ...]  # frontmatter keys, in the order an entry writes them
    required: tuple[str, ...]
    # `void` records a number that was allocated and never carried an entry, so it has none of
    # these to record.
    required_unless_void: tuple[str, ...]
    statuses: tuple[str, ...]
    level: str  # the key whose value is one of `levels`
    levels: tuple[str, ...]  # the bug ledger's severities
    evidence_boundary_for: tuple[str, ...]  # levels whose entries need the evidence line
    # The file `new` writes. `{identifier}`, `{title}`, `{today}` and `{related}` are filled by
    # the writer; every key of `keys` other than `id`, `title`, `status` and `related` is a
    # placeholder for its whole `key: value` line, so an absent value leaves a bare `key:`
    # behind — the trailing space of `source: ` is whitespace an editor strips on save.
    template: str
    sections: tuple[Section, ...]  # in the order the index reads


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
    level="severity",
    levels=("high", "medium", "low"),
    evidence_boundary_for=(),
    template=_BUG_TEMPLATE,
    # The sections' statuses and `statuses` are pinned equal as sets by
    # `test_every_status_has_a_section_to_be_rendered_into`, which pins this reading order
    # separately as a literal; no module-level `assert`, which `python -O` would drop.
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
    )
