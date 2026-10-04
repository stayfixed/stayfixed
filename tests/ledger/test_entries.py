"""The reader and the writer helpers for one entry file.

stayfixed:ledger:fixtures — the identifiers below are sample data, not claims about a ledger.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from stayfixed.config.loader import preset_defaults
from stayfixed.ledger.entries import (
    Entry,
    LedgerError,
    field_line,
    parse_entry,
    quote,
    read_ledger_text,
    related_field,
    scalar,
)
from stayfixed.ledger.register import BUG_SCHEMA, bug_register

REGISTER = bug_register(preset_defaults("widget"))
PATH = Path("docs/bugs/BR-042.md")

ENTRY = """---
id: BR-042
title: "a widget treats a \\"0\\" string target as truthy"
status: open
severity: low
area: widget rendering
found: 2026-07-21
source: audit-2026-07-21
fixed_in:
related: [BR-039]
---

- **Found:** 2026-07-21 (audit)
- **Where:** `src/widget/bars.py`

Body prose.
"""


def test_parse_entry_reads_every_field() -> None:
    entry = parse_entry(ENTRY, path=PATH, register=REGISTER)
    assert entry == Entry(
        id="BR-042",
        title='a widget treats a "0" string target as truthy',
        status="open",
        related=("BR-039",),
        body="- **Found:** 2026-07-21 (audit)\n- **Where:** `src/widget/bars.py`\n\nBody prose.\n",
        path=PATH,
        fields={
            "severity": "low",
            "area": "widget rendering",
            "found": "2026-07-21",
            "source": "audit-2026-07-21",
            "fixed_in": "",
        },
    )
    assert entry.number == 42


@pytest.mark.parametrize(
    ("text", "fragment"),
    [
        ("no frontmatter\n", "no `---` frontmatter"),
        ("---\nid: BR-001\n  nested: x\n---\n", "nested frontmatter"),
        ("---\nid: BR-001\nbogus line\n---\n", "expected `key: value`"),
        ("---\nid: BR-001\ncolour: red\n---\n", "unknown frontmatter key"),
        ("---\nid: BR-001\nid: BR-002\n---\n", "duplicate key"),
        (
            "---\ntitle: x\nstatus: open\nfound: 2026-01-01\n---\n",
            "missing required frontmatter key `id`",
        ),
        (
            "---\nid: BR-4x\ntitle: x\nstatus: open\nfound: 2026-01-01\n---\n",
            "must look like BR-nnn",
        ),
        (
            "---\nid: BR-001\ntitle: x\nstatus: done\nfound: 2026-01-01\n---\n",
            "`status` must be one of",
        ),
        (
            "---\nid: BR-001\ntitle: x\nstatus: open\nfound: 2026-01-01\n---\n",
            "missing required frontmatter key `severity`",
        ),
        (
            "---\nid: BR-001\ntitle: x\nstatus: open\nseverity: huge\narea: a\n"
            "found: 2026-01-01\n---\n",
            "`severity` must be one of",
        ),
        (
            "---\nid: BR-001\ntitle: x\nstatus: open\nseverity: low\narea: a\n"
            "found: 2026/01/01\n---\n",
            "must be an ISO date",
        ),
        (
            '---\nid: BR-001\ntitle: x\nstatus: open\nseverity: low\narea: a\nfound: ""\n---\n',
            "must be an ISO date",
        ),
        (
            "---\nid: BR-001\ntitle: x\nstatus: open\nseverity: low\narea: a\n"
            "found: 2026-02-30\n---\n",
            "names a date that does not exist",
        ),
        (
            "---\nid: BR-001\ntitle: x\nstatus: open\nseverity: low\narea: a\n"
            "found: 2026-01-01\nrelated: BR-002\n---\n",
            "must be an inline list",
        ),
        (
            "---\nid: BR-001\ntitle: x\nstatus: open\nseverity: low\narea: a\n"
            "found: 2026-01-01\nrelated: [BR-2]\n---\n",
            "which is not a BR identifier",
        ),
        (
            '---\nid: BR-001\ntitle: "unterminated\nstatus: open\nseverity: low\n'
            "area: a\nfound: 2026-01-01\n---\n",
            "unterminated quoted value",
        ),
        (
            '---\nid: BR-001\ntitle: "bad \\q escape"\nstatus: open\nseverity: low\n'
            "area: a\nfound: 2026-01-01\n---\n",
            "unsupported escape",
        ),
    ],
)
def test_parse_entry_rejects_broken_frontmatter(text: str, fragment: str) -> None:
    # Each case is one rule; every message names the path so CI output is actionable.
    # Mutation for the date-exists rule: drop the `date.fromisoformat` call — the `2026-02-30`
    # row reddens alone. A quoted empty `found` passes the presence check and is still held to
    # the date rule, because the key is required: drop `or "found" in schema.required` from the
    # reader — the `found: ""` row reddens alone.
    with pytest.raises(LedgerError, match=fragment) as raised:
        parse_entry(text, path=PATH, register=REGISTER)
    assert str(PATH) in str(raised.value)


@pytest.mark.parametrize(
    "raw",
    [
        "#412 in the tracker",
        "- a dash",
        "a: b",
        "key #1",
        "ends in a colon:",
        "[x]",
        "{y}",
        "*star",
        "!bang",
        "|pipe",
        ">gt",
        "'q",
        "%p",
        "@at",
        "`tick`",
    ],
)
def test_a_value_that_is_not_a_plain_yaml_string_needs_quotes(raw: str) -> None:
    # The subset stays valid YAML: a bare `#412 …` reads as a comment to a real YAML reader
    # and the key as null. Mutation: narrow `_NEEDS_QUOTING`'s leading class to `[-?:,]` —
    # the `#412` row reddens.
    #
    # The one indicator absent from this list is `"` itself, and it cannot be here: a value
    # that *starts* with a double quote is the quoted form, so `_unquote` routes it to the
    # unterminated-value rule and never reaches the needs-quotes rule. The writer side below
    # is what holds `"` to the same contract.
    text = (
        "---\nid: BR-001\ntitle: x\nstatus: open\nseverity: low\narea: a\n"
        f"found: 2026-01-01\nsource: {raw}\n---\n"
    )
    with pytest.raises(LedgerError, match="needs double quotes"):
        parse_entry(text, path=PATH, register=REGISTER)


def test_the_writer_quotes_every_yaml_indicator_a_value_can_lead_with() -> None:
    # `_NEEDS_QUOTING` decides both what is written quoted and what is rejected when it is
    # written bare, so a missing indicator is a value written bare that means something else
    # to a YAML reader. This is the whole indicator set, `"` included, which the reader-side
    # test above cannot reach. Mutation: narrow the leading class to `[-?:,]` — this reddens
    # on the first indicator outside it.
    for indicator in "-?:,[]{}#&*!|>'\"%@`":
        value = f"{indicator}412 in the tracker"
        assert scalar(value).startswith('"'), value


@pytest.mark.parametrize(
    "value",
    [
        "plain",
        "#412 in the tracker",
        "ends in a colon:",
        "`f88a`",
        'say "hi"',
        "back\\slash",
        "trail\\",
    ],
)
def test_the_reader_accepts_every_value_the_writer_produces(value: str) -> None:
    # `scalar` quotes exactly when `_unquote` would refuse the bare form; the two are one pair.
    # The `trail\\` case is the title ending in a backslash: the renderer writes it and this
    # reader would refuse the file it just wrote, so one such entry breaks every pass over the
    # whole ledger. Mutation: test the last two characters in `_unquote` instead of the
    # backslash-run parity — that case reddens.
    text = (
        f"---\nid: BR-001\ntitle: {scalar(value)}\nstatus: open\nseverity: low\n"
        "area: a\nfound: 2026-01-01\n---\n"
    )
    assert parse_entry(text, path=PATH, register=REGISTER).title == value


def test_quote_escapes_only_backslash_and_double_quote() -> None:
    assert quote('a "b" \\ c') == '"a \\"b\\" \\\\ c"'


def test_an_entry_is_a_hashable_value() -> None:
    # `Entry` is a frozen record on this area's surface, and a dict among its hashed fields made
    # `hash(entry)` raise `TypeError`. Mutation (oracle): `fields` hashed with the rest -> raises.
    first = parse_entry(ENTRY, path=PATH, register=REGISTER)
    second = parse_entry(ENTRY, path=PATH, register=REGISTER)
    assert first == second
    assert len({first, second}) == 1


def test_void_entries_need_no_severity_or_area() -> None:
    text = (
        "---\nid: BR-005\ntitle: renumbered\nstatus: void\nfound: 2026-01-01\n"
        "related: [BR-009]\n---\n\nbody\n"
    )
    entry = parse_entry(text, path=PATH, register=REGISTER)
    assert (entry.status, entry.fields["severity"], entry.fields["area"]) == ("void", "", "")


def test_an_empty_optional_field_is_written_with_no_trailing_space() -> None:
    # An editor strips the space on save and the file stops matching what `new` wrote.
    assert field_line("source", "") == "source:"
    assert field_line("source", "audit") == "source: audit"
    assert related_field(()) == "related:"
    assert related_field(("BR-001", "BR-002")) == "related: [BR-001, BR-002]"


def test_the_writers_and_the_reader_agree_on_the_key_set() -> None:
    # The schema's keys are the reader's whole vocabulary; its statuses must each have an index
    # section, which `Schema` refuses to be built without. No mutation: a key added to one side
    # and not the other reddens `test_parse_entry_reads_every_field` or the render test, which is
    # the point.
    assert set(BUG_SCHEMA.keys) == {
        "id",
        "title",
        "status",
        "severity",
        "area",
        "found",
        "source",
        "fixed_in",
        "related",
    }
    assert BUG_SCHEMA.statuses == ("open", "partial", "fixed", "rejected", "void")


def test_a_ledger_file_that_is_not_utf8_is_a_ledger_error_naming_it(tmp_path: Path) -> None:
    # `cli.run` maps a `Failure` to exit 1 and everything else to exit 2, and 2 is reserved for
    # a refusal or an internal error. A stray byte in an entry is a repository condition
    # the operator can fix, so it must arrive as findings and not as "the tool is broken".
    # Mutation: read with `errors="replace"` — this reddens.
    path = tmp_path / "BR-001.md"
    path.write_bytes(b"---\nid: BR-001\ntitle: \xff\n---\n")
    with pytest.raises(LedgerError, match="is not valid UTF-8") as raised:
        read_ledger_text(path, where=PATH)
    assert str(PATH) in str(raised.value)


def test_a_ledger_file_that_cannot_be_read_is_a_ledger_error_naming_it(tmp_path: Path) -> None:
    # The other half of the same rule: a permission bit is the operator's to fix too.
    if os.geteuid() == 0:
        pytest.skip("root reads everything")
    path = tmp_path / "BR-001.md"
    path.write_text("---\nid: BR-001\n---\n", encoding="utf-8")
    path.chmod(0)
    try:
        with pytest.raises(LedgerError, match="could not be read"):
            read_ledger_text(path, where=PATH)
    finally:
        path.chmod(0o644)
