"""The reader of the record of the three files the harness executes without Python, which
`doctor files` compares the installed copy against. Writing the record and its drift belong to
the repository's release tooling and are tested in `tests/scripts/test_release.py`."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from stayfixed.release.hashes import HASHED_FILES, RECORD, UnreadableRecord, read_record


def _plugin(tmp_path: Path) -> Path:
    for relative in HASHED_FILES:
        (tmp_path / relative).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / relative).write_text(f"# {relative}\n", encoding="utf-8")
    return tmp_path


def test_a_record_that_is_not_json_is_unreadable_rather_than_absent(tmp_path: Path) -> None:
    # The two answers are different on purpose and the callers branch on the difference: an
    # absent record skips in `doctor` and an unreadable one must be red. A decoder error that
    # read as `None` would turn a corrupted record into a quiet skip — the loudest possible
    # way to say nothing. Mutation (declared): return `None` instead -> the raise reddens.
    root = _plugin(tmp_path)
    (root / RECORD).write_text("{not json\n", encoding="utf-8")
    with pytest.raises(UnreadableRecord, match="not valid JSON"):
        read_record(root)


def test_a_record_that_is_not_utf8_is_unreadable_rather_than_an_internal_error(
    tmp_path: Path,
) -> None:
    """A truncated or half-copied record is exactly what this module's docstring is about.

    The decoder guard caught `json.JSONDecodeError` alone, so non-UTF-8 bytes raised
    `UnicodeDecodeError` past every caller. Measured before the fix, on a tree carrying the
    three hashed files::

        printf '{"format": 1, "files": {"hooks/hooks.json": "\xff\xfe"}}\n' > hooks/hashes.json

    the release checks (`hashes --check`, `check`) and `doctor files` all printed
    `stayfixed: internal error: UnicodeDecodeError: …` and exited **2** — the refusal code,
    where a finding is 1 — and `doctor`'s `except UnreadableRecord` arm did not catch it.

    Mutation (declared): the `UnicodeDecodeError` arm is removed -> the raise reddens.
    """
    root = _plugin(tmp_path)
    (root / RECORD).write_bytes(b'{"format": 1, "files": {"hooks/hooks.json": "\xff\xfe"}}\n')
    with pytest.raises(UnreadableRecord, match="is not UTF-8 text"):
        read_record(root)


def test_a_record_the_process_cannot_read_is_unreadable_rather_than_a_warning(
    tmp_path: Path,
) -> None:
    # The other escape through the same `try`, and it took the other wrong turn: an
    # `OSError` reached `doctor._guarded` as `warn — this check could not read something it
    # needed`, when the record is present and the answer "present and unreadable" is red.
    # Mutation (declared): the `OSError` arm is removed -> this reddens.
    root = _plugin(tmp_path)
    record = root / RECORD
    record.write_text('{"format": 1, "files": {}}\n', encoding="utf-8")
    record.chmod(0o000)
    try:
        if os.access(record, os.R_OK):  # pragma: no cover - a root-owned test run
            pytest.skip("this process can read a mode-000 file")
        with pytest.raises(UnreadableRecord, match="could not be read"):
            read_record(root)
    finally:
        record.chmod(0o644)


@pytest.mark.parametrize(
    "body",
    [
        '{"format": 2, "files": {}}',
        '{"format": 1, "files": []}',
        '{"format": 1, "files": {"hooks/hooks.json": 1}}',
        '{"files": {}}',
        "[]",
    ],
    ids=[
        "another-format",
        "files-not-a-table",
        "a-digest-that-is-not-a-string",
        "no-format",
        "not-an-object",
    ],
)
def test_a_record_of_the_wrong_shape_is_unreadable(tmp_path: Path, body: str) -> None:
    # Valid JSON of the wrong shape decodes cleanly, so the decoder catch above never sees it —
    # the same class of hole the release check's `_parse` had for a lockfile that was valid TOML
    # of the wrong shape. Mutation (declared): stop checking `format` -> the first case reads
    # as a record with no files and this reddens.
    root = _plugin(tmp_path)
    (root / RECORD).write_text(body + "\n", encoding="utf-8")
    with pytest.raises(UnreadableRecord):
        read_record(root)
