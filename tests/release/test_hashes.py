"""The record of the three files the harness executes without Python, as an installed stayfixed
reads it: `digests`, which hashes the files, and `read_record`, which `doctor files` compares the
installed copy against. Writing the record and its drift belong to the repository's release
tooling and are tested in `tests/scripts/test_release.py`; the records here are written by hand,
so what the reader accepts is held without the writer."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from stayfixed.release.hashes import (
    FORMAT,
    HASHED_FILES,
    RECORD,
    UnreadableRecord,
    digests,
    read_record,
)


def hashed_plugin(tmp_path: Path) -> Path:
    """A plugin root holding each hashed file, each one's text a comment naming it."""
    for relative in HASHED_FILES:
        (tmp_path / relative).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / relative).write_text(f"# {relative}\n", encoding="utf-8")
    return tmp_path


def test_each_file_is_hashed_to_its_full_sha256(tmp_path: Path) -> None:
    # Against a literal rather than against itself. Every other assertion about the record
    # compares one side of it to the other, so both move together: measured, the digest
    # truncated to its first eight characters left every record test passing — the algorithm and
    # the digest length are what a downstream verifier depends on and nothing pinned either.
    # `tests/scaffold/test_manifest.py` makes the same claim the same way.
    #
    # Mutation (declared): `mutations/`'s "the release record records a truncated digest".
    root = hashed_plugin(tmp_path)
    found = digests(root)
    assert list(found) == list(HASHED_FILES)
    for relative in HASHED_FILES:
        expected = hashlib.sha256(f"# {relative}\n".encode()).hexdigest()
        assert found[relative] == expected, relative


def test_no_record_reads_as_none_and_a_record_reads_back_as_written(tmp_path: Path) -> None:
    # The two answers the callers branch on: no record is `None`, which `doctor` skips, and a
    # record is the digests it names, keys and values as written. The record is written here by
    # hand, in the shape the release script writes, so the reader is held without the writer.
    # Mutation (declared): `mutations/`'s "no release record reads as a record naming nothing"
    # and "the release record reader truncates the digests it read".
    root = hashed_plugin(tmp_path)
    assert read_record(root) is None
    written = {relative: f"{index:064x}" for index, relative in enumerate(HASHED_FILES)}
    (root / RECORD).write_text(
        json.dumps({"format": FORMAT, "files": written}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    assert read_record(root) == written


def test_a_record_that_is_not_json_is_unreadable_rather_than_absent(tmp_path: Path) -> None:
    # The two answers are different on purpose and the callers branch on the difference: an
    # absent record skips in `doctor` and an unreadable one must be red. A decoder error that
    # read as `None` would turn a corrupted record into a quiet skip — the loudest possible
    # way to say nothing. Mutation (declared): return `None` instead -> the raise reddens.
    root = hashed_plugin(tmp_path)
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
    root = hashed_plugin(tmp_path)
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
    root = hashed_plugin(tmp_path)
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
    root = hashed_plugin(tmp_path)
    (root / RECORD).write_text(body + "\n", encoding="utf-8")
    with pytest.raises(UnreadableRecord):
        read_record(root)
