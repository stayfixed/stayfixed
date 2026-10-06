from __future__ import annotations

import hashlib
import json
import stat
from pathlib import Path
from typing import Any

import pytest

from stayfixed import fsops
from stayfixed.config.paths import PathEscape
from stayfixed.scaffold.manifest import (
    FORMAT,
    MANIFEST_PATH,
    Kind,
    Location,
    Manifest,
    ManifestError,
    Record,
    digest,
)


def a_record(**overrides: object) -> Record:
    values: dict[str, object] = {
        "id": "agents-md",
        "kind": Kind.TEMPLATE,
        "location": Location.REPO,
        "target": "AGENTS.md",
        "template": "project/AGENTS.md",
        "version": "0.1.0",
        "sha256": digest("hello"),
    }
    values.update(overrides)
    return Record(**values)  # type: ignore[arg-type]


def raw_of(root: Path) -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads((root / MANIFEST_PATH).read_text(encoding="utf-8"))
    return loaded


def test_a_missing_manifest_reads_as_empty(tmp_path: Path) -> None:
    assert Manifest.read(tmp_path).records == {}


def test_a_manifest_round_trips(tmp_path: Path) -> None:
    written = Manifest({}).with_record(a_record()).with_record(a_record(id="gitignore"))
    written.write(tmp_path)
    assert Manifest.read(tmp_path).records == written.records


def test_the_first_key_says_the_file_is_generated(tmp_path: Path) -> None:
    Manifest({}).with_record(a_record()).write(tmp_path)
    raw = raw_of(tmp_path)
    assert next(iter(raw)) == "_generated"
    assert "hand-edit" in str(raw["_generated"])


def test_the_format_is_recorded_so_a_migration_can_key_on_it(tmp_path: Path) -> None:
    Manifest({}).with_record(a_record()).write(tmp_path)
    assert raw_of(tmp_path)["format"] == FORMAT
    assert Manifest.read(tmp_path).format == FORMAT


def test_a_manifest_from_a_newer_stayfixed_refuses(tmp_path: Path) -> None:
    Manifest({}).with_record(a_record()).write(tmp_path)
    raw = raw_of(tmp_path)
    raw["format"] = FORMAT + 1
    (tmp_path / MANIFEST_PATH).write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ManifestError, match="newer"):
        Manifest.read(tmp_path)


def test_records_are_written_in_id_order(tmp_path: Path) -> None:
    manifest = Manifest({}).with_record(a_record(id="zulu")).with_record(a_record(id="alpha"))
    manifest.write(tmp_path)
    assert list(raw_of(tmp_path)["artifacts"]) == ["alpha", "zulu"]


def test_a_malformed_manifest_refuses_rather_than_reading_as_empty(tmp_path: Path) -> None:
    (tmp_path / ".stayfixed").mkdir()
    (tmp_path / MANIFEST_PATH).write_text("{not json", encoding="utf-8")
    with pytest.raises(ManifestError):
        Manifest.read(tmp_path)


def test_a_manifest_past_the_read_cap_is_unreadable_and_never_read_whole(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The manifest is committed, so a clone chooses its size: it is read to the read cap, as every
    # reader of a committed file is, and one past it is unreadable, named as the project names it
    # and never by the path it was opened by. The cap is lowered so the file is small. Mutation
    # (oracle): `mutations/`'s "the footprint manifest is read with no bound" -> it is read whole.
    Manifest({}).with_record(a_record()).write(tmp_path)
    limit = 4 * 1024
    path = tmp_path / MANIFEST_PATH
    path.write_text(path.read_text(encoding="utf-8") + " " * limit, encoding="utf-8")
    monkeypatch.setattr(fsops, "REGULAR_READ_LIMIT", limit)
    with pytest.raises(ManifestError) as refused:
        Manifest.read(tmp_path)
    assert str(refused.value) == f"{MANIFEST_PATH} is unreadable: larger than this reader reads"


def test_an_unknown_kind_refuses(tmp_path: Path) -> None:
    (tmp_path / ".stayfixed").mkdir()
    (tmp_path / MANIFEST_PATH).write_text(
        json.dumps(
            {
                "_generated": "x",
                "format": FORMAT,
                "artifacts": {
                    "a": {
                        "id": "a",
                        "kind": "sculpture",
                        "location": "repo",
                        "target": "a",
                        "template": "t",
                        "version": "0.1.0",
                        "sha256": digest(""),
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ManifestError, match="sculpture"):
        Manifest.read(tmp_path)


def test_a_record_missing_a_field_refuses(tmp_path: Path) -> None:
    (tmp_path / ".stayfixed").mkdir()
    (tmp_path / MANIFEST_PATH).write_text(
        json.dumps({"artifacts": {"a": {"id": "a", "kind": "template", "location": "repo"}}}),
        encoding="utf-8",
    )
    with pytest.raises(ManifestError, match="target"):
        Manifest.read(tmp_path)


def test_the_manifest_is_written_atomically_and_readably(tmp_path: Path) -> None:
    Manifest({}).with_record(a_record()).write(tmp_path)
    directory = tmp_path / ".stayfixed"
    assert sorted(p.name for p in directory.iterdir()) == ["manifest.json"]
    assert stat.S_IMODE((tmp_path / MANIFEST_PATH).stat().st_mode) == 0o644


def test_a_symlinked_stayfixed_directory_refuses_the_write(tmp_path: Path) -> None:
    # `write_atomically` takes a path, so it makes the parent with `Path.mkdir` and replaces
    # through `os.replace`: both follow a symlink at `.stayfixed` and neither is a containment
    # check. The ledger is the one file this module knows the location of, so the check is here.
    victim = tmp_path / "victim"
    victim.mkdir()
    (tmp_path / ".stayfixed").symlink_to(victim, target_is_directory=True)
    with pytest.raises(PathEscape, match="symlink"):
        Manifest({}).with_record(a_record()).write(tmp_path)
    assert list(victim.iterdir()) == []


def test_a_symlinked_stayfixed_directory_refuses_the_read_rather_than_trusting_it(
    tmp_path: Path,
) -> None:
    # Reading through the link is not merely a read outside the root: the records decide which
    # files `upgrade` rewrites and `uninstall` deletes, so a planted ledger is a planted
    # instruction list.
    victim = tmp_path / "victim"
    victim.mkdir()
    Manifest({}).with_record(a_record(target="somebody-elses.md")).write(victim)
    (tmp_path / ".stayfixed").symlink_to(victim, target_is_directory=True)
    with pytest.raises(PathEscape, match="symlink"):
        Manifest.read(tmp_path)


def test_digest_is_sha256_of_the_utf8_bytes() -> None:
    # Written against `hashlib` rather than a frozen hex literal: a literal would also pass an
    # implementation that encoded Latin-1, as long as someone regenerated the literal.
    assert digest("héllo") == hashlib.sha256("héllo".encode()).hexdigest()
