"""`rewrite_owned`: a tool-owned key moved, and the `config` record kept honest about it."""

from __future__ import annotations

import errno
import os
import tomllib
from pathlib import Path

import pytest

import stayfixed
from stayfixed.config.loader import CONFIG_FILE
from stayfixed.errors import Refusal
from stayfixed.project import rewrite as module
from stayfixed.project.rewrite import NO_DOCUMENT, rewrite_owned
from stayfixed.scaffold import MANIFEST_PATH, Manifest, ManifestError, digest
from tests.gitfixture import needs_git
from tests.project.repos import initialised

MOVED = {("stayfixed", "version"): "9.9.9"}


def _record_digest(root: Path) -> str:
    record = Manifest.read(root).get("config")
    assert record is not None
    return record.sha256


@needs_git
def test_an_untouched_document_is_restamped_with_its_new_bytes(tmp_path: Path) -> None:
    root = initialised(tmp_path)
    rewrite_owned(root, MOVED)
    text = (root / CONFIG_FILE).read_text(encoding="utf-8")
    assert 'version = "9.9.9"' in text
    assert _record_digest(root) == digest(text)


@needs_git
def test_an_edited_document_is_rewritten_and_its_record_never_blesses_the_edit(
    tmp_path: Path,
) -> None:
    root = initialised(tmp_path)
    path = root / CONFIG_FILE
    path.write_text(path.read_text(encoding="utf-8") + "# a note of ours\n", encoding="utf-8")
    stamped = _record_digest(root)
    rewrite_owned(root, MOVED)
    assert "# a note of ours\n" in path.read_text(encoding="utf-8")
    assert _record_digest(root) == stamped


@needs_git
def test_a_run_interrupted_between_its_two_writes_converges_on_the_next(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The record is written first. Interrupted there, nothing changed; interrupted after it, the
    # record names bytes the next run writes. Written the other way round, an interruption after
    # the document leaves a record no run will re-stamp, and `uninstall` keeps the file for good.
    root = initialised(tmp_path)
    original = Manifest.write

    def interrupted(self: Manifest, where: Path) -> None:
        raise OSError("interrupted")

    monkeypatch.setattr(Manifest, "write", interrupted)
    with pytest.raises(OSError):
        rewrite_owned(root, MOVED)
    monkeypatch.setattr(Manifest, "write", original)
    rewrite_owned(root, MOVED)
    assert _record_digest(root) == digest((root / CONFIG_FILE).read_text(encoding="utf-8"))


@needs_git
def test_a_write_that_fails_puts_the_record_back_so_a_run_with_other_bytes_still_restamps(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The record is re-stamped first, so a write that fails left it naming bytes the file never
    # held. The next run computing different bytes (a later version) then found the record
    # describing neither, never re-stamped it, and `uninstall` kept an untouched `stayfixed.toml`
    # as edited for good. Mutation (oracle): "a failed write of stayfixed.toml leaves its record
    # naming bytes the file never held" -> the first assertion after the failure reddens.
    root = initialised(tmp_path)
    before = _record_digest(root)

    def failing(where: Path, target: str, text: str) -> None:
        raise OSError("no space left on device")

    # A context of its own rather than `monkeypatch.undo()`, which also undid the suite's autouse
    # `HOME` seal: the fixture is shared, so the second run went on without it.
    with monkeypatch.context() as patched:
        patched.setattr(module, "write_within", failing)
        with pytest.raises(Refusal, match="cannot be written"):
            rewrite_owned(root, MOVED)
        assert _record_digest(root) == before
    rewrite_owned(root, {("stayfixed", "version"): "9.9.10"})
    text = (root / CONFIG_FILE).read_text(encoding="utf-8")
    assert 'version = "9.9.10"' in text and _record_digest(root) == digest(text)


@needs_git
def test_a_restore_that_fails_too_still_names_stayfixed_toml_s_own_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Both writes fail: the document, then the manifest put back. The manifest's refusal used to
    # replace the one naming `stayfixed.toml`, which is the failure to put right; it is the cause
    # now. The state is the documented "killed between the two writes" one. Mutation (advisory):
    # let the restore's `ManifestError` propagate -> the message names the manifest.
    root = initialised(tmp_path)
    original = Manifest.write
    calls: list[int] = []

    def failing(where: Path, target: str, text: str) -> None:
        raise OSError(errno.ENOSPC, os.strerror(errno.ENOSPC), f".stayfixed-1-{target}.tmp")

    def second_fails(self: Manifest, where: Path) -> Path:
        calls.append(1)
        if len(calls) > 1:
            raise ManifestError("the manifest cannot be written either")
        return original(self, where)

    monkeypatch.setattr(module, "write_within", failing)
    monkeypatch.setattr(Manifest, "write", second_fails)
    with pytest.raises(Refusal) as refused:
        rewrite_owned(root, MOVED)
    # The reason in words, `fsops.said`, and not the error's text, which names the temporary file
    # the write went through. Mutation: `mutations/`'s "a stayfixed.toml that cannot be written is
    # reported with the error's own text".
    reason = os.strerror(errno.ENOSPC)
    assert str(refused.value) == f"{CONFIG_FILE} cannot be written ({reason})"
    assert isinstance(refused.value.__cause__, ManifestError)


@needs_git
def test_nothing_to_move_writes_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # A promotion of a gate already enforced, or an upgrade with nothing to move, must not
    # rewrite identical bytes. Mutation (advisory): drop the early return -> this reddens.
    root = initialised(tmp_path)

    def refuse(*args: object) -> None:
        raise AssertionError("wrote a document that did not change")

    monkeypatch.setattr(module, "write_within", refuse)
    rewrite_owned(root, {("stayfixed", "version"): stayfixed.__version__})


def test_a_missing_document_is_a_refusal(tmp_path: Path) -> None:
    with pytest.raises(Refusal, match=NO_DOCUMENT):
        rewrite_owned(tmp_path, MOVED)


def test_a_hand_written_document_with_no_manifest_and_no_stayfixed_table_gets_the_key(
    tmp_path: Path,
) -> None:
    # `init` adopting a hand-written `stayfixed.toml` writes the tool-owned keys into it before any
    # manifest exists, and such a file may have no `[stayfixed]` table at all. Nothing is
    # re-stamped, because nothing is recorded yet, and no manifest is created.
    written = '[project]\nname = "widget"\n'
    (tmp_path / CONFIG_FILE).write_text(written, encoding="utf-8")
    rewrite_owned(tmp_path, MOVED)
    text = (tmp_path / CONFIG_FILE).read_text(encoding="utf-8")
    assert text.startswith(written)
    assert tomllib.loads(text) == {"project": {"name": "widget"}, "stayfixed": {"version": "9.9.9"}}
    assert not (tmp_path / MANIFEST_PATH).exists()
