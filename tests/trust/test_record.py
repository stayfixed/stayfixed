"""The machine's one trust record (`src/stayfixed/trust/record.py`): a versioned document of kinds
and subjects beside the machine file, which still reads the flat map `0.3.0` wrote and which
`0.3.0` reads as holding no approval."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from stayfixed.config.machine import machine_config_path
from stayfixed.trust.record import (
    LATER_VERSION,
    NOT_A_RECORD,
    RECORD,
    VERSION,
    Approval,
    State,
    UnreadableTrust,
    approve,
    record_path,
    recorded,
    revoke,
    state,
)
from tests.ownerhome import as_owner_home

T0 = datetime(2026, 10, 16, 9, 30, tzinfo=UTC)


def legacy_reader(path: Path) -> dict[str, str]:
    """`0.3.0`'s reader of the record, copied as a literal: its filter keeps the entries whose
    value is a string, which is every approval it can interpret."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {k: v for k, v in raw.items() if isinstance(v, str)}


def machine(tmp_path: Path) -> Path:
    return tmp_path / "config.toml"


def test_a_0_3_0_record_keeps_every_memory_approval(tmp_path: Path) -> None:
    # Review Focus 4, the upgrade half. Mutation (`mutations/`'s "the trust record no longer reads
    # 0.3.0's flat map"): the approval reads missing.
    (tmp_path / RECORD).write_text(json.dumps({"/s": "d", "/t": "e"}), encoding="utf-8")
    assert state(machine(tmp_path), "memory", "/s", "d") is State.APPROVED
    assert state(machine(tmp_path), "memory", "/t", "e") is State.APPROVED
    assert recorded(machine(tmp_path))[("memory", "/s")] == Approval("memory", "/s", "d", "")


def test_the_first_write_upgrades_the_file_in_place(tmp_path: Path) -> None:
    # The old entry is carried into the version-1 record beside the new one. Mutation: as above,
    # the flat map's entry is lost on the write.
    (tmp_path / RECORD).write_text(json.dumps({"/s": "d"}), encoding="utf-8")
    approve(machine(tmp_path), "memory", "/t", "e", now=T0)
    written = json.loads((tmp_path / RECORD).read_text(encoding="utf-8"))
    assert written == {
        "version": VERSION,
        "approvals": [
            {"kind": "memory", "subject": "/s", "digest": "d", "approved_at": ""},
            {
                "kind": "memory",
                "subject": "/t",
                "digest": "e",
                "approved_at": "2026-10-16T09:30:00+00:00",
            },
        ],
    }


def test_0_3_0s_reader_sees_no_approval_in_a_version_1_record(tmp_path: Path) -> None:
    # Review Focus 4, the downgrade half: `0.3.0` reads no approval and asks again, never a stale
    # one. No mutation of the source reaches it — it is a property of the record's shape against a
    # reader frozen in `0.3.0` — so the shape is held exactly in the test above.
    approve(machine(tmp_path), "memory", "/s", "d", now=T0)
    assert legacy_reader(tmp_path / RECORD) == {}


@pytest.mark.parametrize(
    ("document", "sentence"),
    [
        pytest.param("{", None, id="not-json"),
        pytest.param(json.dumps({"version": 2, "approvals": []}), LATER_VERSION, id="version-2"),
        pytest.param(json.dumps({"version": True, "approvals": []}), LATER_VERSION, id="bool"),
        pytest.param(json.dumps({"version": 1}), NOT_A_RECORD, id="no-approvals"),
        pytest.param(
            json.dumps({"version": 1, "approvals": [{"kind": "memory", "subject": "/s"}]}),
            NOT_A_RECORD,
            id="approval-short-a-field",
        ),
    ],
)
def test_an_unreadable_record_refuses_and_is_never_overwritten(
    tmp_path: Path, document: str, sentence: str | None
) -> None:
    # Mutations (`mutations/`'s "a trust record of a later version is read as empty" -> version 2
    # reads as no approval and the write replaces it; "an approval over an unreadable trust record
    # writes the record anyway" -> the write replaces every case).
    path = tmp_path / RECORD
    path.write_text(document, encoding="utf-8")
    with pytest.raises(UnreadableTrust) as caught:
        recorded(machine(tmp_path))
    if sentence is not None:
        assert str(caught.value) == sentence.format(path=path)
    with pytest.raises(UnreadableTrust):
        approve(machine(tmp_path), "memory", "/s", "d", now=T0)
    with pytest.raises(UnreadableTrust):
        revoke(machine(tmp_path), "memory", "/s")
    assert path.read_text(encoding="utf-8") == document


def test_lapsed_missing_and_approved_are_told_apart(tmp_path: Path) -> None:
    # Mutations (`mutations/`'s "the trust record ignores the digest" -> the changed digest reads
    # approved; "a lapsed approval reads as missing" -> it reads missing).
    approve(machine(tmp_path), "memory", "/s", "d", now=T0)
    assert state(machine(tmp_path), "memory", "/s", "d") is State.APPROVED
    assert state(machine(tmp_path), "memory", "/s", "changed") is State.LAPSED
    assert state(machine(tmp_path), "memory", "/elsewhere", "d") is State.MISSING


def test_two_kinds_never_share_a_subject(tmp_path: Path) -> None:
    # Mutation (`mutations/`'s "the trust record keys an approval by its subject alone"): the
    # second approval replaces the first, and the first kind reads lapsed.
    approve(machine(tmp_path), "memory", "/s", "d", now=T0)
    approve(machine(tmp_path), "other", "/s", "e", now=T0)
    assert state(machine(tmp_path), "memory", "/s", "d") is State.APPROVED
    assert state(machine(tmp_path), "other", "/s", "e") is State.APPROVED
    assert revoke(machine(tmp_path), "other", "/s") is True
    assert state(machine(tmp_path), "memory", "/s", "d") is State.APPROVED


def test_revoke_of_nothing_says_so(tmp_path: Path) -> None:
    # False, and the file is not rewritten. Mutation (`mutations/`'s "a revoke of nothing rewrites
    # the trust record"): the file is replaced with the same approvals, under a new inode.
    approve(machine(tmp_path), "memory", "/s", "d", now=T0)
    path = tmp_path / RECORD
    before = (path.read_bytes(), path.stat().st_ino)
    assert revoke(machine(tmp_path), "memory", "/elsewhere") is False
    assert (path.read_bytes(), path.stat().st_ino) == before
    assert revoke(machine(tmp_path), "memory", "/s") is True
    assert state(machine(tmp_path), "memory", "/s", "d") is State.MISSING


def test_no_record_at_all_holds_no_approval(tmp_path: Path) -> None:
    # The fresh machine. No mutation of its own: the absent file is the arm every write test
    # passes through first.
    assert recorded(machine(tmp_path)) == {}
    assert state(machine(tmp_path), "memory", "/s", "d") is State.MISSING


def test_the_record_ignores_xdg_and_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # The record beside the machine file is under the password database's home, whatever `HOME`
    # and `XDG_CONFIG_HOME` say. Mutation (`mutations/`'s "the trust record follows HOME"): the
    # record moves under the environment's home.
    as_owner_home(monkeypatch, tmp_path / "owner")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    assert machine_config_path() == tmp_path / "owner" / ".config" / "stayfixed" / "config.toml"
    assert record_path(None) == tmp_path / "owner" / ".config" / "stayfixed" / RECORD
    assert record_path(machine(tmp_path)) == tmp_path / RECORD
    # No home in the database: no record, and nothing to fall back on.
    as_owner_home(monkeypatch, None)
    assert record_path(None) is None
