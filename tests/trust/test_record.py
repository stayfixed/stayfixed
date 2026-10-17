"""The machine's one trust record (`src/stayfixed/trust/record.py`): a versioned document of kinds
and subjects beside the machine file, which still reads the flat map `0.3.0` wrote and which
`0.3.0` reads as holding no approval."""

from __future__ import annotations

import errno
import json
import os
from datetime import UTC, datetime
from pathlib import Path

import pytest

from stayfixed import fsops
from stayfixed.config.machine import machine_config_path
from stayfixed.errors import Failure
from stayfixed.trust.record import (
    LATER_VERSION,
    NOT_A_RECORD,
    RECORD,
    SANDBOXED,
    VERSION,
    Approval,
    SandboxedWrite,
    State,
    UnreadableTrust,
    approve,
    approve_all,
    record_path,
    recorded,
    refresh,
    revoke,
    state,
)
from tests.ownerhome import as_owner_home
from tests.sandboxed import refuse_writes_under

T0 = datetime(2026, 10, 16, 9, 30, tzinfo=UTC)
# One approval as a version-1 record spells it, every field a string.
APPROVAL = {"kind": "memory", "subject": "/s", "digest": "d", "approved_at": ""}


def legacy_reader(path: Path) -> dict[str, str]:
    """`0.3.0`'s reader of the record, copied as a literal: its filter keeps the entries whose
    value is a string, which is every approval it can interpret."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {k: v for k, v in raw.items() if isinstance(v, str)}


def machine(tmp_path: Path) -> Path:
    return tmp_path / "config.toml"


def test_a_0_3_0_record_keeps_every_memory_approval(tmp_path: Path) -> None:
    # Upgrading over a record `0.3.0` wrote keeps every approval in it. Mutation (`mutations/`'s
    # "the trust record no longer reads 0.3.0's flat map"): the approval reads missing.
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
    # Downgrading: a `0.3.0` reading the record this release wrote reads no approval and asks again,
    # never a stale one. No mutation of the source reaches it — it is a property of the record's
    # shape against a reader frozen in `0.3.0` — so the shape is held exactly in the test above.
    approve(machine(tmp_path), "memory", "/s", "d", now=T0)
    assert legacy_reader(tmp_path / RECORD) == {}


@pytest.mark.parametrize(
    ("document", "sentence"),
    [
        pytest.param("{", None, id="not-json"),
        pytest.param(json.dumps({"version": 2, "approvals": []}), LATER_VERSION, id="version-2"),
        pytest.param(json.dumps({"version": True, "approvals": []}), NOT_A_RECORD, id="bool"),
        pytest.param(json.dumps({"version": 0, "approvals": []}), NOT_A_RECORD, id="version-0"),
        pytest.param(json.dumps({"version": -1, "approvals": []}), NOT_A_RECORD, id="negative"),
        pytest.param(json.dumps({"version": "1", "approvals": []}), NOT_A_RECORD, id="text"),
        pytest.param(json.dumps({"approvals": [APPROVAL]}), NOT_A_RECORD, id="no-version"),
        pytest.param(json.dumps({"version": 1}), NOT_A_RECORD, id="no-approvals"),
        pytest.param(
            json.dumps({"version": 1, "approvals": [{"kind": "memory", "subject": "/s"}]}),
            NOT_A_RECORD,
            id="approval-short-a-field",
        ),
        pytest.param(
            json.dumps({"version": 1, "approvals": {}}), NOT_A_RECORD, id="approvals-not-a-list"
        ),
        pytest.param(
            json.dumps({"version": 1, "approvals": [], "note": "hand-added"}),
            NOT_A_RECORD,
            id="stray-key",
        ),
        pytest.param(
            json.dumps({"version": 1, "approvals": [{**APPROVAL, "digest": 1}]}),
            NOT_A_RECORD,
            id="digest-not-a-string",
        ),
        pytest.param(
            json.dumps({"version": 1, "approvals": [APPROVAL, {**APPROVAL, "digest": "e"}]}),
            NOT_A_RECORD,
            id="duplicate-pair",
        ),
        pytest.param(
            json.dumps({"version": 1, "approvals": [sorted(APPROVAL)]}),
            NOT_A_RECORD,
            id="entry-not-an-object",
        ),
    ],
)
def test_an_unreadable_record_refuses_and_is_never_overwritten(
    tmp_path: Path, document: str, sentence: str | None
) -> None:
    # Each arm of the version-1 reader has a case of its own: every other version-1 record in the
    # suite is one `approve` wrote, and it can write none of these. Only a version above this one
    # sends its reader to a later stayfixed, and an object holding `approvals` is never `0.3.0`'s
    # flat map. Mutations (`mutations/`'s "a trust record of a later version is read as empty" ->
    # version 2 reads as no approval and the write replaces it; "a trust record of any other version
    # is sent to a later stayfixed" -> `bool`, `version-0`, `negative` and `text` say
    # `LATER_VERSION`; "a trust record with approvals and no version reads as 0.3.0's flat map" ->
    # `no-version` reads as no approval and the next write erases it; "an approval over an
    # unreadable trust record writes the record anyway" -> the write replaces every case; "a trust
    # record's approvals that are not a list read as none" -> `approvals-not-a-list` reads as no
    # approval; "a trust record with a stray key is read" -> `stray-key` reads; "a trust record's
    # digest that is not a string is read" -> `digest-not-a-string` reads as a lapsed approval; "a
    # trust record naming one approval twice keeps the last" -> `duplicate-pair` reads, and the next
    # write persists the survivor; "a trust record's approval that is not an object is read" ->
    # `entry-not-an-object` raises an `AttributeError` instead of refusing).
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


# What every refusal of a record that is there and cannot be read ends with, written out rather than
# imported, so the sentence a person reads is held here and not only by the module that says it.
KEPT = (
    "it holds every project's approval on this machine, so nothing here will overwrite it — repair "
    "or delete it"
)


def _json_says(text: str) -> str:
    """What the standard library's parser says of `text`, which the refusal quotes."""
    try:
        json.loads(text)
    except json.JSONDecodeError as exc:
        return str(exc)
    raise AssertionError(f"{text!r} parses")


@pytest.mark.parametrize(
    ("data", "said"),
    [
        pytest.param(b"{", f"is not valid JSON: {_json_says('{')}", id="not-json"),
        pytest.param(b"\xff{}", "is not UTF-8 text", id="not-utf-8"),
    ],
)
def test_a_record_that_does_not_parse_says_why_and_that_it_is_kept(
    tmp_path: Path, data: bytes, said: str
) -> None:
    # The two arms before the version-1 reader, each asserted whole: the refusal names the file and
    # why, and closes with what keeps the record from being overwritten. Mutations (`mutations/`'s
    # "a trust record that is not JSON is refused without saying it is kept" -> `not-json` loses
    # its close; "a trust record that is not UTF-8 is refused without saying why" -> `not-utf-8`
    # names no cause).
    path = tmp_path / RECORD
    path.write_bytes(data)
    with pytest.raises(UnreadableTrust) as caught:
        recorded(machine(tmp_path))
    assert str(caught.value) == f"{path} {said}; {KEPT}"


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


def test_a_refresh_moves_only_the_digest_it_was_read_at(tmp_path: Path) -> None:
    # A refresh is stayfixed's own write over an approval its caller read before writing: it keeps
    # when the person approved, and writes nothing once the record holds another digest — a new
    # approval given meanwhile is the person's. Mutations (`mutations/`'s "a refresh writes over an
    # approval it did not read" -> the stale refresh moves `e` to `f`; "a refresh restamps when
    # the person approved" -> `approved_at` reads now).
    approve(machine(tmp_path), "memory", "/s", "d", now=T0)
    assert refresh(machine(tmp_path), "memory", "/s", expected="d", digest="e") is True
    assert recorded(machine(tmp_path))[("memory", "/s")] == Approval(
        "memory", "/s", "e", "2026-10-16T09:30:00+00:00"
    )
    path = tmp_path / RECORD
    before = (path.read_bytes(), path.stat().st_ino)
    assert refresh(machine(tmp_path), "memory", "/s", expected="d", digest="f") is False
    assert (path.read_bytes(), path.stat().st_ino) == before


def test_a_refresh_to_the_digest_the_record_holds_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A move to the digest already recorded holds the approval as it is, so nothing is written:
    # from an agent's sandboxed shell, where the write is refused, a rewrite said the approval was
    # not refreshed while it held. Mutation (`mutations/`'s "a refresh rewrites the digest the
    # record already holds"): the refused write is attempted and raises `SandboxedWrite`.
    approve(machine(tmp_path), "memory", "/s", "d", now=T0)
    before = recorded(machine(tmp_path))
    refused = refuse_writes_under(monkeypatch, tmp_path / RECORD)
    assert refresh(machine(tmp_path), "memory", "/s", expected="d", digest="d") is True
    assert refused == []
    assert recorded(machine(tmp_path)) == before


def test_a_refresh_never_brings_back_a_revoked_approval(tmp_path: Path) -> None:
    # The revoke landed after the caller's read and before the refresh re-read the record. Mutation
    # (`mutations/`'s "a refresh brings back a revoked approval"): the approval is recorded again.
    approve(machine(tmp_path), "memory", "/s", "d", now=T0)
    assert revoke(machine(tmp_path), "memory", "/s") is True
    assert refresh(machine(tmp_path), "memory", "/s", expected="d", digest="e") is False
    assert recorded(machine(tmp_path)) == {}


@pytest.mark.parametrize(
    ("code", "sandboxed"),
    [
        pytest.param(errno.EPERM, True, id="eperm"),
        pytest.param(errno.EROFS, True, id="erofs"),
        pytest.param(errno.EACCES, False, id="eacces"),
    ],
)
def test_a_write_refused_as_a_sandbox_refuses_one_is_said_so(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, code: int, sandboxed: bool
) -> None:
    # `EPERM`, which macOS's sandbox answers, and `EROFS`, a read-only mount's answer, are read as
    # the sandbox's refusal and said in the record's constant sentence, a refusal; `EACCES`, a
    # directory whose mode refuses the user, keeps the sentence naming the directory, a failure.
    # Nothing is written either way. Mutations (`mutations/`'s "a read-only mount's refusal is not
    # read as the sandbox's" -> `erofs` names the directory; "a directory's mode is read as the
    # sandbox" -> `eacces` says the sandbox's sentence).
    path = machine(tmp_path).parent / RECORD

    def refusing(target: Path, text: str, **kwargs: object) -> None:
        raise OSError(code, os.strerror(code), str(target))

    monkeypatch.setattr(fsops, "write_atomically", refusing)
    with pytest.raises((SandboxedWrite, Failure)) as refused:
        approve(machine(tmp_path), "memory", "/s", "d", now=T0)
    if sandboxed:
        assert type(refused.value) is SandboxedWrite
        assert str(refused.value) == SANDBOXED
    else:
        assert type(refused.value) is Failure
        assert str(refused.value) == (
            f"{path.parent} cannot be written ({fsops.said(OSError(code, os.strerror(code)))}), "
            "so the trust record cannot be kept there; it is beside the machine configuration "
            "file --machine names"
        )
    assert not path.exists()


def test_the_sandbox_sentence_says_what_a_person_in_their_own_terminal_meets() -> None:
    # `EPERM` and `EROFS` are what the sandbox answers, and also what a read-only mount or an
    # immutable flag answers a person already in their own terminal, whom the sentence would
    # otherwise send there again. Mutation (`mutations/`'s "the trust record's sandbox sentence
    # sends a person in their own terminal there again"): the sentence ends at the sandbox.
    from stayfixed.trust.boundary import OWN_TERMINAL_TOO
    from stayfixed.trust.record import SANDBOXED

    assert SANDBOXED.endswith(OWN_TERMINAL_TOO)


def test_every_subject_of_a_kind_is_approved_in_one_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A kind with several subjects is approved whole or not at all: one replacement of the record,
    # so a write that fails part-way leaves it as it was. And it answers what the record said of
    # each before. Mutation (`mutations/`'s "approving a kind writes the record once per subject"):
    # two writes.
    machine = tmp_path / "config.toml"
    approve(machine, "memory", "/a", "old", now=T0)
    writes: list[Path] = []
    real = fsops.write_atomically

    def counting(path: Path, text: str) -> None:
        writes.append(path)
        real(path, text)

    monkeypatch.setattr(fsops, "write_atomically", counting)
    was = approve_all(machine, "memory", {"/a": "new", "/b": "d"}, now=T0)
    assert writes == [tmp_path / RECORD]
    assert was == {"/a": State.LAPSED, "/b": State.MISSING}
    assert state(machine, "memory", "/a", "new") is State.APPROVED
    assert state(machine, "memory", "/b", "d") is State.APPROVED


def test_approving_no_subject_writes_nothing(tmp_path: Path) -> None:
    # A kind with nothing to approve in this checkout leaves the record where it is, absent
    # included. Mutation (`mutations/`'s "approving no subject writes the record"): an empty
    # version-1 record appears.
    machine = tmp_path / "config.toml"
    assert approve_all(machine, "memory", {}, now=T0) == {}
    assert not (tmp_path / RECORD).exists()


def test_a_later_records_refusal_sends_its_reader_to_a_later_stayfixed() -> None:
    # A record a later stayfixed wrote is met after a downgrade, where deleting it would destroy
    # that release's approvals: the remedy is updating stayfixed, never deleting the file. No
    # mutation of its own: the refusal is a constant, asserted whole by the unreadable-record cases
    # above.
    assert LATER_VERSION.endswith("update stayfixed to read it")
    assert "delete" not in LATER_VERSION
