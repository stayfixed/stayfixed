"""The register engine's list field, and the bug entry's `regression` it carries, read-only.

A `regression` is an argv: the items are the words a later command runs, so an item may hold a
comma, a space or a bracket, and a reader that split on commas would hand back other words than the
ones written. Nothing writes one yet, so the reader, `bugs check` and `renumber` are what hold it.

stayfixed:ledger:fixtures — the identifiers below are sample data, not claims about a ledger.
"""

from __future__ import annotations

import json
import re
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from stayfixed.config.loader import preset_defaults
from stayfixed.ledger.entries import (
    CONTROL_IN_ITEM,
    EMPTY_ITEM,
    LIST_SHAPE,
    Entry,
    LedgerError,
    list_value_spans,
    parse_entry,
)
from stayfixed.ledger.register import BUG_SCHEMA, Section, bug_register
from stayfixed.printed import quoted
from tests.cli import cli
from tests.gitfixture import needs_git
from tests.ledger.test_literals import ledger_copy, literal

REGISTER = bug_register(preset_defaults("widget"))
PATH = Path("docs/bugs/BR-042.md")

ENTRY = """---
id: BR-042
title: a widget renders the wrong total
status: open
severity: low
area: widget rendering
found: 2026-10-18
source:
fixed_in:
related:
regression: {regression}
---

Body prose.
"""


def parse(text: str) -> Entry:
    return parse_entry(text, path=PATH, register=REGISTER)


def test_a_regression_reads_as_its_argv() -> None:
    # Mutations (oracle): `mutations/`'s "the list reader ends an item at a comma inside its
    # quotes" -> the two items holding a comma come back split; "a list key is read as a scalar
    # again" and "the bug ledger declares no list" -> the value is refused for its leading `[`.
    entry = parse(ENTRY.format(regression='["pytest", "tests/t.py::test[1,2]", "-k", "a, b"]'))
    assert entry.lists["regression"] == ("pytest", "tests/t.py::test[1,2]", "-k", "a, b")
    assert "regression" not in entry.fields
    with pytest.raises(KeyError):
        entry.value("regression")


@pytest.mark.parametrize("raw", ["", "[]", "[ ]"], ids=["bare", "brackets", "spaced"])
def test_an_empty_regression_is_no_regression(raw: str) -> None:
    # Mutations (oracle): `mutations/`'s "the list reader refuses an empty value" -> `bare`;
    # "the list reader refuses an empty list" -> `brackets` and `spaced`; "the list reader takes no
    # space after its opening bracket" -> `spaced`.
    assert parse(ENTRY.format(regression=raw)).lists == {"regression": ()}


def test_a_regression_left_out_is_no_regression() -> None:
    # Mutations (oracle): `mutations/`'s "the list reader refuses an empty value" -> refused as a
    # shape; "an entry carries none of its lists" -> the mapping is empty, not one empty list.
    assert parse(ENTRY.replace("regression: {regression}\n", "")).lists == {"regression": ()}


def test_escapes_read_as_titles_read_them() -> None:
    # The items go through the reader a quoted title goes through, so the two escapes are one rule.
    # Mutation (oracle): `mutations/`'s "the list reader skips one character after a backslash" ->
    # the escaped quote closes the first item.
    entry = parse(ENTRY.format(regression='["a\\"b", "c\\\\"]'))
    assert entry.lists["regression"] == ('a"b', "c\\")


def test_two_entries_that_differ_only_in_their_regression_are_two_values() -> None:
    # Mutation (oracle): `mutations/`'s "an entry leaves its lists out of its equality" -> equal.
    assert parse(ENTRY.format(regression='["a"]')) != parse(ENTRY.format(regression='["b"]'))


@pytest.mark.parametrize(
    ("raw", "constant"),
    [
        pytest.param("[pytest]", LIST_SHAPE, id="bare-item"),
        pytest.param('["a",]', LIST_SHAPE, id="trailing-comma"),
        pytest.param('["a"] x', LIST_SHAPE, id="text-after"),
        pytest.param('"a"', LIST_SHAPE, id="no-brackets"),
        pytest.param('("a"]', LIST_SHAPE, id="wrong-opening-bracket"),
        pytest.param('["a"', LIST_SHAPE, id="unclosed-list"),
        pytest.param('["a', LIST_SHAPE, id="unterminated-item"),
        pytest.param('["a",\t"b"]', LIST_SHAPE, id="tab-separator"),
        pytest.param('["a"b"]', LIST_SHAPE, id="unescaped-quote"),
        pytest.param('[""]', EMPTY_ITEM, id="empty-item"),
        pytest.param('["a\x01"]', CONTROL_IN_ITEM, id="c0-control"),
        pytest.param('["a\x7f"]', CONTROL_IN_ITEM, id="del"),
    ],
)
def test_a_malformed_regression_is_refused_in_its_own_words(raw: str, constant: str) -> None:
    """Measured against PyYAML 6.0.2 on 2026-10-18, since the frontmatter promises a subset of
    YAML and the repository carries no YAML parser, so the measurement is the record. Of the
    cases measured, it reads the argv, the empty and spaced lists and the escapes in this file to
    the same items (a bare `regression:` to null, which this reader takes for the empty list), and
    refuses the tab separator, a control character below U+0020 and DEL, the text after `]`, the
    unclosed list and the unescaped quote. The bare item, the trailing comma, the quoted scalar
    and the empty item it reads; this grammar refuses them, because an argv written any of those
    ways is one a reader could take for another. This grammar refuses a control character only
    below U+0020 and DEL, so it passes every code point from U+0080 to U+009F. Of those, PyYAML
    refuses `\x80` and `\x9b` with a ReaderError, and reads U+0085 as a line break folded to a
    space, `['a ']`, an argv other than the one written; this entry reader splits its frontmatter
    lines at U+0085 too, so it refuses that entry before the grammar reads the item.
    """
    # Mutations (oracle): `mutations/`'s "the list reader takes a tab for a separator" -> the tab
    # case reads; "the list reader accepts an empty item" -> `empty-item` reads; "the list reader
    # lets a control character into an item" -> both control cases read; "the list reader takes text
    # after its closing bracket" -> `text-after`, `unclosed-list` and `unescaped-quote` read; "the
    # list reader takes a bare item" -> `bare-item` reads; "the list reader takes a value with no
    # opening bracket" -> `wrong-opening-bracket` reads; "the list reader reads an unterminated
    # item as an empty one" -> `unterminated-item` says `EMPTY_ITEM`; "the list reader takes a
    # trailing comma" -> `trailing-comma` reads; "the list reader reads a lone quoted value as one
    # item" -> `no-brackets` reads.
    with pytest.raises(LedgerError) as caught:
        parse(ENTRY.format(regression=raw))
    assert str(caught.value) == constant.format(where=quoted(PATH.as_posix()), key="regression")


@pytest.mark.parametrize(
    "separator", ["\x85", "\u2028", "\x0b"], ids=["next-line", "line-separator", "vertical-tab"]
)
def test_a_line_break_inside_an_item_refuses_the_entry(separator: str) -> None:
    # The frontmatter's lines are split where `str.splitlines` splits them, so a line separator
    # inside an item cuts the line in two, and the second half is no `key: value`. PyYAML reads
    # U+0085 inside the item as a space, `['a ']`, an argv other than the one written, so the
    # refusal is the reading this reader may give. Mutation (oracle): `mutations/`'s "the
    # frontmatter reader reads a line separator as part of a line" -> the item reads.
    with pytest.raises(LedgerError) as caught:
        parse(ENTRY.format(regression=f'["a{separator}"]'))
    assert str(caught.value) == f"{quoted(PATH.as_posix())}:12: expected `key: value`, got '\"]'"


@pytest.mark.parametrize("ending", ["\n", "\r\n", "\r"], ids=["lf", "crlf", "cr"])
def test_a_list_value_lies_where_the_reader_reads_it_whatever_the_endings(ending: str) -> None:
    # `---` then `---` opens a block the first line of which is the second fence, closed only by a
    # later one, so the list is inside it on every ending. Mutation (oracle): `mutations/`'s "the
    # frontmatter reader knows only LF line endings" -> `crlf` and `cr` find no block, so no span.
    text = '---\n---\nregression: ["BR-002"]\n---\n'.replace("\n", ending)
    spans = list_value_spans(text, ("regression",))
    assert [text[start:end] for start, end in spans] == ['["BR-002"]']


def test_a_crlf_is_one_line_break_to_the_reader() -> None:
    # Translated to LF, `---` CRLF `---` CRLF is `---\n---\n`, which opens no block, and the reader
    # handed the CRLF text says the same. Read as a lone CR and then an LF, the CRLF would end an
    # empty block on the second line. Mutation (oracle): `mutations/`'s "the frontmatter reader
    # takes a CRLF for two line breaks" -> the entry is refused for a missing `id` instead.
    with pytest.raises(LedgerError) as caught:
        parse("---\r\n---\r\n")
    where = quoted(PATH.as_posix())
    assert str(caught.value) == f"{where}: no `---` frontmatter block at the top of the file"


def with_regression(root: Path, name: str, regression: str) -> str:
    """Give the entry `name` a `regression:` line as the last of its frontmatter; its new text."""
    path = root / "docs" / "bugs" / name
    head, separator, body = path.read_text(encoding="utf-8").partition("\n---\n")
    text = f"{head}\nregression: {regression}{separator}{body}"
    path.write_text(text, encoding="utf-8")
    return text


@needs_git
def test_bugs_check_reports_a_malformed_regression_as_unreadable(tmp_path: Path) -> None:
    # Mutation (oracle): `mutations/`'s "the list reader takes a bare item" -> the check passes.
    root = ledger_copy(tmp_path)
    with_regression(root, "BR-004.md", "[pytest]")
    code, out, _ = cli(root, tmp_path, "bugs", "check")
    assert (code, out) == (
        1,
        "FAIL: 2 ledger problem(s): docs/bugs/BR-004.md [unreadable-entry], "
        "docs/bug-reports.md [stale-index]\n",
    )
    code, out, _ = cli(root, tmp_path, "bugs", "check", "--json")
    assert code == 1
    assert json.loads(out)["findings"][0] == {
        "rule": "unreadable-entry",
        "path": "docs/bugs/BR-004.md",
        "line": None,
        "detail": LIST_SHAPE.format(where="docs/bugs/BR-004.md", key="regression"),
    }


@needs_git
def test_an_entry_with_a_regression_passes_bugs_check(tmp_path: Path) -> None:
    # Mutation (oracle): `mutations/`'s "the bug ledger declares no list" -> `unreadable-entry`.
    root = ledger_copy(tmp_path)
    with_regression(root, "BR-001.md", '["pytest", "-k", "total and not slow"]')
    assert cli(root, tmp_path, "bugs", "check") == (
        0,
        "OK: bug ledger entries, index freshness, and identifier references\n",
        "",
    )


@needs_git
def test_renumber_carries_a_regression_byte_for_byte(tmp_path: Path) -> None:
    # Mutation (oracle): `mutations/`'s "the bug ledger declares no list" -> the move refuses the
    # entry.
    root = ledger_copy(tmp_path)
    text = with_regression(root, "BR-002.md", '["pytest", "tests/t.py::test[1,2]", "-k", "a, b"]')
    code, _, _ = cli(root, tmp_path, "bugs", "renumber", "BR-002", "BR-009")
    assert code == 0
    moved = (root / "docs" / "bugs" / "BR-009.md").read_text(encoding="utf-8")
    assert moved == text.replace("id: BR-002\n", "id: BR-009\n", 1)


@needs_git
def test_renumber_leaves_an_argv_naming_the_old_identifier(tmp_path: Path) -> None:
    # An argv names the test it runs, and a test is not renamed when its bug is renumbered. BR-003
    # names BR-002 in its title, its `related` list and its body too, all of which the sweep still
    # rewrites; BR-004 names it in its argv alone. Mutation (oracle): `mutations/`'s "the sweep
    # rewrites an argv inside a list value" -> both argvs name BR-009.
    root = ledger_copy(tmp_path)
    argv = '["pytest", "-k", "BR-002 and not slow"]'
    with_regression(root, "BR-003.md", argv)
    untouched = with_regression(root, "BR-004.md", argv)
    code, out, _ = cli(root, tmp_path, "bugs", "renumber", "BR-002", "BR-009")
    assert (code, out) == (0, "BR-002 -> BR-009; a void pointer remains at docs/bugs/BR-002.md\n")
    bugs = root / "docs" / "bugs"
    swept = literal("renumber.swept.md", "").replace(
        "related: [BR-009]\n", f"related: [BR-009]\nregression: {argv}\n", 1
    )
    assert (bugs / "BR-003.md").read_text(encoding="utf-8") == swept
    assert (bugs / "BR-004.md").read_text(encoding="utf-8") == untouched


@needs_git
@pytest.mark.parametrize("ending", ["\r\n", "\r"], ids=["crlf", "cr"])
def test_renumber_leaves_an_argv_naming_the_old_identifier_whatever_the_line_endings(
    tmp_path: Path, ending: str
) -> None:
    # A checkout under `core.autocrlf=true` holds every entry with CRLF endings. The reader reads
    # such an entry with its endings translated, so it passes `bugs check`, and the sweep reads the
    # file as it is on disk: its argv is found on the file's own endings, or renamed. Mutation
    # (oracle): `mutations/`'s "the frontmatter reader knows only LF line endings" -> both argvs
    # name BR-009.
    root = ledger_copy(tmp_path)
    argv = '["pytest", "-k", "BR-002 and not slow"]'
    bugs = root / "docs" / "bugs"
    for name in ("BR-003.md", "BR-004.md"):
        text = with_regression(root, name, argv)
        (bugs / name).write_bytes(text.replace("\n", ending).encode("utf-8"))
    untouched = (bugs / "BR-004.md").read_bytes()
    code, out, _ = cli(root, tmp_path, "bugs", "renumber", "BR-002", "BR-009")
    assert (code, out) == (0, "BR-002 -> BR-009; a void pointer remains at docs/bugs/BR-002.md\n")
    swept = literal("renumber.swept.md", "").replace(
        "related: [BR-009]\n", f"related: [BR-009]\nregression: {argv}\n", 1
    )
    assert (bugs / "BR-003.md").read_bytes() == swept.replace("\n", ending).encode("utf-8")
    assert (bugs / "BR-004.md").read_bytes() == untouched


@needs_git
@pytest.mark.parametrize(
    "relative",
    ["docs/notes.md", "docs/bugs/notes.md", "docs/bugs/BR-005.txt"],
    ids=["outside-the-ledger", "in-the-ledger-unprefixed", "prefixed-not-markdown"],
)
def test_renumber_sweeps_a_regression_line_in_a_file_that_is_no_entry(
    tmp_path: Path, relative: str
) -> None:
    # Only an entry, a file the register reads, carries a `regression`; in any other file the
    # same line is text like the rest, and the sweep rewrites it. Mutation (oracle):
    # `mutations/`'s "the sweep keeps list values in every file it rewrites" -> each file keeps
    # BR-002.
    root = ledger_copy(tmp_path)
    notes = root / relative
    notes.write_text('---\nregression: ["BR-002"]\n---\n\nAbout BR-002.\n', encoding="utf-8")
    code, _, _ = cli(root, tmp_path, "bugs", "renumber", "BR-002", "BR-009")
    assert code == 0
    assert (
        notes.read_text(encoding="utf-8") == '---\nregression: ["BR-009"]\n---\n\nAbout BR-009.\n'
    )


AS_SECTION = (
    Section("Open", ("open",), (("ID", "id"), ("Regression", "regression"))),
    *BUG_SCHEMA.sections[1:],
)


@pytest.mark.parametrize(
    ("changes", "problem"),
    [
        pytest.param(
            {"lists": ("regression", "argv")}, "lists names `argv`, which is not a key", id="key"
        ),
        pytest.param(
            {"required": (*BUG_SCHEMA.required, "regression")},
            "list `regression` is required, and a list may be left out",
            id="required",
        ),
        pytest.param(
            {"required_unless_void": (*BUG_SCHEMA.required_unless_void, "regression")},
            "list `regression` is required_unless_void, and a list may be left out",
            id="required-unless-void",
        ),
        pytest.param(
            {"level": "regression"},
            "list `regression` is the level, which holds one value",
            id="level",
        ),
        pytest.param(
            {"dates": (*BUG_SCHEMA.dates, "regression")},
            "list `regression` is a date, which holds one value",
            id="date",
        ),
        pytest.param(
            {"sections": AS_SECTION},
            "list `regression` is shown in an index column, whose cell holds one value",
            id="column",
        ),
        pytest.param(
            {"template": BUG_SCHEMA.template.replace("{related}\n", "{related}\n{regression}\n")},
            "list `regression` is a placeholder of the template, and nothing writes a list",
            id="placeholder",
        ),
        pytest.param(
            {"lists": ("regression", "related")},
            "list `related` is `related`, which the reader reads as identifiers",
            id="related",
        ),
    ],
)
def test_a_list_key_is_held_to_what_reads_it(changes: dict[str, Any], problem: str) -> None:
    # Each rule keeps a list key off a path that reads one value: the presence checks, the level,
    # the date rule, an index cell, the writer's template, and `related`'s own reader. Mutations
    # (oracle): one per rule, each dropping its check -> its case constructs.
    with pytest.raises(ValueError, match=re.escape(problem)):
        replace(BUG_SCHEMA, **changes)


def test_the_bug_ledger_declares_regression_as_its_one_list() -> None:
    # Mutations (oracle): `mutations/`'s "the bug ledger declares no list" -> the first
    # assertion; "the bug ledger's regression key comes before related" -> the second; "a list
    # key is read as a scalar again" -> the last two.
    assert BUG_SCHEMA.lists == ("regression",)
    assert BUG_SCHEMA.keys[-2:] == ("related", "regression")
    assert "regression" not in BUG_SCHEMA.scalar_keys
    assert BUG_SCHEMA.scalar_keys == BUG_SCHEMA.keys[:-1]
