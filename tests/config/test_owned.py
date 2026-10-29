"""`config.owned.rewrite`: three keys, rewritten in place, every other byte left alone."""

from __future__ import annotations

import tomllib

import pytest

from stayfixed.config.owned import OWNED, OwnedKeyError, Value, rewrite

HAND_WRITTEN = (
    "# The project's own configuration; the comments are part of it.\n"
    "[stayfixed]\n"
    'version = "0.1.0"   # bumped by stayfixed upgrade\n'
    'enforced = ["plan"]\n'
    'preset = "recommended"\n'
    "\n"
    "[project]\n"
    'name = "widget"  # never edited by the tool\n'
    "\n"
    "[ci]\n"
    'mode = "reusable"\n'
    'ref = "' + "a" * 40 + '"\n'
)


def test_a_value_is_replaced_and_every_other_byte_is_where_it_was() -> None:
    after = rewrite(HAND_WRITTEN, {("stayfixed", "version"): "0.2.0"})
    assert after == HAND_WRITTEN.replace('"0.1.0"', '"0.2.0"')


def test_a_list_of_gates_is_rewritten_as_one_line() -> None:
    after = rewrite(HAND_WRITTEN, {("stayfixed", "enforced"): ("docs", "plan")})
    assert 'enforced = ["docs", "plan"]\n' in after
    assert tomllib.loads(after)["stayfixed"]["enforced"] == ["docs", "plan"]


def test_two_keys_in_two_tables_are_rewritten_in_one_call() -> None:
    after = rewrite(HAND_WRITTEN, {("stayfixed", "enforced"): ("docs",), ("ci", "ref"): "b" * 40})
    document = tomllib.loads(after)
    assert document["stayfixed"]["enforced"] == ["docs"]
    assert document["ci"]["ref"] == "b" * 40
    assert "# never edited by the tool" in after


def test_a_missing_key_is_written_under_its_table_header() -> None:
    text = '[stayfixed]\npreset = "recommended"\n\n[project]\nname = "widget"\n'
    after = rewrite(text, {("stayfixed", "version"): "0.2.0"})
    assert after.startswith('[stayfixed]\nversion = "0.2.0"\npreset = "recommended"\n')


def test_a_missing_table_is_appended_and_nothing_above_it_moves() -> None:
    # A hand-written document with no `[stayfixed]` table at all: the table is appended after
    # everything the document already holds.
    text = '[project]\nname = "widget"\n'
    after = rewrite(text, {("stayfixed", "version"): "0.2.0"})
    assert after.startswith(text)
    assert tomllib.loads(after)["stayfixed"] == {"version": "0.2.0"}


@pytest.mark.parametrize(
    ("text", "change"),
    [
        (HAND_WRITTEN, {("stayfixed", "enforced"): ("docs",), ("ci", "ref"): "c" * 40}),
        # Inserting under an existing header: the first promotion writes `enforced` this way.
        ('[stayfixed]\npreset = "recommended"\n', {("stayfixed", "enforced"): ("docs",)}),
        # Appending a table the document does not have.
        ('[project]\nname = "widget"\n', {("stayfixed", "version"): "0.2.0"}),
    ],
    ids=["replace", "insert", "append"],
)
def test_a_crlf_document_stays_crlf(text: str, change: dict[tuple[str, str], Value]) -> None:
    # Mutation: `newline = "\n"` reddens the insert and append cases; a replaced line keeps its
    # own ending whatever `newline` says, which is why the replace case alone proved nothing.
    after = rewrite(text.replace("\n", "\r\n"), change)
    assert "\n" not in after.replace("\r\n", "")


def test_a_key_under_a_dotted_subtable_is_not_the_table_s_own() -> None:
    # `[stayfixed.sub]` ends `[stayfixed]` for the editor. Mutation: delete the `current = None`
    # reset after `_ANY_HEADER` and the sub-table's line is rewritten instead, which the
    # read-back refuses, so this reddens with an `OwnedKeyError`.
    text = '[stayfixed]\npreset = "recommended"\n\n[stayfixed.sub]\nversion = "x"\n'
    after = rewrite(text, {("stayfixed", "version"): "0.2.0"})
    document = tomllib.loads(after)
    assert document["stayfixed"]["version"] == "0.2.0"
    assert document["stayfixed"]["sub"] == {"version": "x"}


@pytest.mark.parametrize(
    "text",
    [
        # A dotted key at the top level: the editor finds no `[stayfixed]` header and would add a
        # second definition of the same table.
        'stayfixed.version = "0.1.0"\n[project]\nname = "widget"\n',
        'stayfixed = { version = "0.1.0" }\n',
        "[stayfixed]\nversion = 1\n",
        '[stayfixed]\n"version" = "0.1.0"\n',
    ],
    ids=["dotted", "inline-table", "not-a-string", "quoted-key"],
)
def test_a_shape_the_editor_does_not_rewrite_is_refused_and_never_written(text: str) -> None:
    with pytest.raises(OwnedKeyError, match=r"\[stayfixed\] version .* by hand"):
        rewrite(text, {("stayfixed", "version"): "0.2.0"})


def test_the_refusal_names_the_key_that_failed_and_a_line_that_pastes() -> None:
    # Only `version` is in a shape the editor does not rewrite; `[ci] ref` is fine. A single
    # read-back after every edit named whichever pending key sorted first, `[ci] ref`, and
    # `upgrade` always changes the two together. Mutation: build the refusal from
    # `min(changes)` instead of the key in hand, and this reddens.
    text = '[stayfixed]\n"version" = "0.1.0"\n\n[ci]\nref = "' + "a" * 40 + '"\n'
    with pytest.raises(OwnedKeyError) as caught:
        rewrite(text, {("stayfixed", "version"): "0.2.0", ("ci", "ref"): "b" * 40})
    message = str(caught.value)
    assert message.startswith("[stayfixed] version ")
    assert '`version = "0.2.0"`' in message
    assert "[ci]" not in message


def test_a_table_header_inside_a_multi_line_string_is_not_where_the_key_is() -> None:
    # The line editor's blind spot, and the reason the read-back exists. A `[ci]` line and a
    # `ref = "…"` line inside a `"""` string look exactly like the real thing to a reader that
    # goes line by line. Whatever the editor does with them, the result may not come back.
    text = (
        "[ci]\n"
        'ref = "' + "a" * 40 + '"\n'
        "\n"
        "[project]\n"
        'name = "widget"\n'
        'notes = """\n'
        "[ci]\n"
        'ref = "old"\n'
        '"""\n'
    )
    with pytest.raises(OwnedKeyError):
        rewrite(text, {("ci", "ref"): "b" * 40})


@pytest.mark.parametrize(
    "text",
    [
        # U+0085 is a line break to `str.splitlines` and an ordinary character to TOML.
        '[stayfixed]\nversion = "0.1\x850"\n',
        # A header on the last line, with no newline after it.
        '[project]\nname = "widget"\n[stayfixed]',
    ],
    ids=["nel-inside-a-string", "header-without-a-newline"],
)
def test_a_valid_document_the_line_cutter_used_to_misread_is_rewritten(text: str) -> None:
    # Mutations: cut with `text.splitlines(keepends=True)` and the first is refused; drop the
    # newline `_set` adds after a bare last-line header and the second is.
    after = rewrite(text, {("stayfixed", "version"): "0.2.0"})
    assert tomllib.loads(after)["stayfixed"]["version"] == "0.2.0"


def test_a_document_that_does_not_parse_is_refused_by_position_alone() -> None:
    # `tomllib` quotes the document in its message (`Cannot declare ('stayfixed',) twice`), and a
    # refusal reaches a terminal and a model. Mutation: re-raise the `TOMLDecodeError` and this
    # reddens.
    header = "[stayfixed]"
    text = f"{header}\n{header}\n# \x1b[31m\n"
    with pytest.raises(OwnedKeyError) as caught:
        rewrite(text, {("stayfixed", "version"): "0.2.0"})
    # The position is the end of the repeated header, so the column is that header's width.
    assert str(caught.value) == (
        f"stayfixed.toml is not valid TOML (at line 2, column {len(header)}), "
        "so nothing was written"
    )


def test_only_the_owned_keys_can_be_named() -> None:
    stayfixed = {("stayfixed", "version"), ("stayfixed", "enforced")}
    assert stayfixed | {("ci", "ref")} == OWNED
    with pytest.raises(ValueError, match="not a tool-owned key"):
        rewrite(HAND_WRITTEN, {("project", "name"): "other"})


@pytest.mark.parametrize(
    "text",
    [
        HAND_WRITTEN,
        # Two spellings of an up-to-date value that the editor would otherwise rewrite, or refuse:
        # a literal string, and a quoted key.
        "[stayfixed]\nversion = '0.1.0'\nenforced = ['plan']\n",
        '[stayfixed]\n"version" = "0.1.0"\n"enforced" = ["plan"]\n',
    ],
    ids=["canonical", "literal-strings", "quoted-keys"],
)
def test_an_unchanged_value_returns_the_text_byte_for_byte(text: str) -> None:
    # Mutation: drop the "already that value" `continue` and the literal-string case comes back
    # rewritten with double quotes, and the quoted-key case is refused.
    same: dict[tuple[str, str], Value] = {
        ("stayfixed", "version"): "0.1.0",
        ("stayfixed", "enforced"): ("plan",),
    }
    assert rewrite(text, same) == text


def test_a_comment_holding_brackets_survives_an_array_rewrite() -> None:
    # A greedy array pattern read `["plan"]  # see [docs]` as one value and dropped the comment,
    # and the read-back accepted it: the comment is not part of the parsed document.
    text = HAND_WRITTEN.replace('enforced = ["plan"]\n', 'enforced = ["plan"]  # see [docs]\n')
    after = rewrite(text, {("stayfixed", "enforced"): ("docs", "plan")})
    assert 'enforced = ["docs", "plan"]  # see [docs]\n' in after
