"""`stayfixed trust list | revoke` (`src/stayfixed/trust/commands.py`): every approval recorded on
this machine, listed, and one withdrawn by its kind and subject."""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

from stayfixed.printed import CLIPPED_CHARS
from stayfixed.trust.commands import NOTHING_TO_REVOKE
from stayfixed.trust.record import RECORD, approve_all, recorded
from tests.boundaries.test_delivery import IMPORT_EACH
from tests.crafted import CRAFTED, assert_never_raw
from tests.floor import developer_free_environ
from tests.memory.test_commands import invoke
from tests.sandboxed import refuse_writes_under

ROOT = Path(__file__).resolve().parents[2]
LAUNCHER = [sys.executable, str(ROOT / "scripts" / "stayfixed")]
T0 = datetime(2026, 10, 16, 9, 30, tzinfo=UTC)


def _machine(tmp_path: Path) -> Path:
    return tmp_path / "machine.toml"


def test_revoke_needs_no_terminal(tmp_path: Path) -> None:
    # Withdrawing is the direction that fails safe, so it runs from an agent's shell tool too.
    # Mutation (`mutations/`'s "trust revoke revokes nothing"): the approval stays.
    approve_all(_machine(tmp_path), "memory", {"/s": "d"}, now=T0)
    proc = subprocess.run(
        [
            *LAUNCHER,
            "trust",
            "revoke",
            "memory",
            "--subject",
            "/s",
            "--machine",
            str(_machine(tmp_path)),
        ],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        check=False,
        env=developer_free_environ(),
    )
    assert proc.returncode == 0, proc.stderr
    assert recorded(_machine(tmp_path)) == {}


def test_a_record_write_a_sandbox_refused_says_a_person_must_run_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    # From an agent's sandboxed shell the machine directory cannot be written (`EPERM`, as macOS's
    # sandbox answers), so a revoke there ends in exit 2 and the record's constant sentence,
    # nothing written, never a traceback. Mutation (`mutations/`'s "the trust record says nothing
    # of the sandbox that refused its write"): exit 1 and the sentence about a directory that
    # cannot be written.
    from stayfixed.trust.record import SANDBOXED

    approve_all(_machine(tmp_path), "memory", {"/s": "d"}, now=T0)
    before = recorded(_machine(tmp_path))
    refused = refuse_writes_under(monkeypatch, tmp_path / RECORD)
    argv = ["trust", "revoke", "memory", "--subject", "/s", "--machine", str(_machine(tmp_path))]
    assert invoke(argv) == 2
    err = capsys.readouterr().err
    assert refused == [tmp_path / RECORD]
    assert err == f"stayfixed: refused: {SANDBOXED}\n"
    assert recorded(_machine(tmp_path)) == before


def test_revoke_of_nothing_lists_what_is_recorded(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    # Exit 1 and the kind's recorded subjects, named on the line and in `--json` whole. The
    # subject, an absolute path, used to print withheld, which named nothing. Mutations
    # (`mutations/`'s "a revoke of nothing exits 0" -> exit 0; "a recorded subject under the home
    # prints whole" -> the line names the whole path).
    home = tmp_path.resolve()
    monkeypatch.setenv("HOME", str(home))
    subject = str(home / "project" / ".stayfixed" / "local" / "memory")
    approve_all(_machine(tmp_path), "memory", {subject: "d"}, now=T0)
    argv = ["trust", "revoke", "memory", "--subject", "/elsewhere", "--json"]
    assert invoke([*argv, "--machine", str(_machine(tmp_path))]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["recorded"] == [subject]
    assert payload["summary"] == (
        f"{NOTHING_TO_REVOKE.format(kind='memory')}; recorded: ~/project/.stayfixed/local/memory"
    )
    assert ("memory", subject) in recorded(_machine(tmp_path))


def test_revoke_takes_the_subject_as_list_prints_it_from_the_home(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    # `trust list` names a subject under the home from `~/`, and that line is what a person copies:
    # matched only as the absolute path, it refused, listing the very spelling that just failed.
    home = tmp_path.resolve()
    monkeypatch.setenv("HOME", str(home))
    subject = str(home / "project" / "notes" / "developer" / "rule.md")
    approve_all(_machine(tmp_path), "reviewed", {subject: "d"}, now=T0)
    argv = ["trust", "revoke", "reviewed", "--subject", "~/project/notes/developer/rule.md"]
    assert invoke([*argv, "--machine", str(_machine(tmp_path))]) == 0, capsys.readouterr().err
    assert recorded(_machine(tmp_path)) == {}


def test_list_names_each_subject_from_the_home(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    # A subject under the home prints from `~`, one anywhere else
    # whole, both through `printed.clipped`. Mutation (`mutations/`'s "a recorded subject under the
    # home prints whole"): the first line names the whole path, quoted.
    home = tmp_path.resolve()
    monkeypatch.setenv("HOME", str(home))
    machine = tmp_path / "machine.toml"
    approve_all(machine, "memory", {str(home / "project" / ".stayfixed" / "memory"): "d"}, now=T0)
    approve_all(machine, "memory", {"/zz/elsewhere/memory": "e"}, now=T0)
    assert invoke(["trust", "list", "--machine", str(machine)]) == 0
    # In the order of the subjects themselves, and `/zz` sorts after any temporary directory.
    assert capsys.readouterr().out == (
        "memory ~/project/.stayfixed/memory: approved 2026-10-16T09:30:00+00:00\n"
        "memory '/zz/elsewhere/memory': approved 2026-10-16T09:30:00+00:00\n"
    )


def test_a_hostile_subject_prints_escaped_and_bounded(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    # A directory a clone named is a recorded subject's bytes: a line break and `::error::` start a
    # workflow command on a runner, an escape drives the terminal, and nothing bounds its length.
    # Both listings print it escaped and clipped. Mutations (`mutations/`'s "a recorded subject
    # prints raw" -> the listing carries the escape; "revoke's recorded list prints a subject raw"
    # -> the revoke line does).
    monkeypatch.setenv("HOME", str(tmp_path / "owner"))
    machine = tmp_path / "machine.toml"
    hostile, long = f"/{CRAFTED}", "/" + "a" * 300
    approve_all(machine, "memory", {hostile: "d"}, now=T0)
    approve_all(machine, "memory", {long: "e"}, now=T0)
    shown = (repr(hostile), f"{long[:CLIPPED_CHARS]!r}…({len(long)} chars)")
    assert invoke(["trust", "list", "--machine", str(machine)]) == 0
    listed = capsys.readouterr()
    assert_never_raw(listed.out, listed.err)
    assert listed.out == "".join(
        f"memory {name}: approved 2026-10-16T09:30:00+00:00\n" for name in sorted(shown)
    )
    argv = ["trust", "revoke", "memory", "--subject", "/elsewhere", "--machine", str(machine)]
    assert invoke(argv) == 1
    revoked = capsys.readouterr()
    assert_never_raw(revoked.out, revoked.err)
    assert revoked.out == (
        f"{NOTHING_TO_REVOKE.format(kind='memory')}; recorded: {', '.join(sorted(shown))}\n"
    )


def test_a_hostile_kind_prints_escaped_and_bounded(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # The kind is whatever was typed, and a revoke prints it back. No mutation of its own: printed
    # raw, the crafted bytes reach the line, which `assert_never_raw` names.
    argv = ["trust", "revoke", CRAFTED, "--subject", "/s", "--machine", str(_machine(tmp_path))]
    assert invoke(argv) == 1
    said = capsys.readouterr()
    assert_never_raw(said.out, said.err)


def test_list_names_every_record_on_the_machine(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # The listing reads the record, not a checkout. No mutation of its own: a listing with nothing
    # in it fails the equality below.
    approve_all(_machine(tmp_path), "memory", {"/s": "d"}, now=T0)
    approve_all(_machine(tmp_path), "other", {"/t": "e"}, now=T0)
    assert invoke(["trust", "list", "--json", "--machine", str(_machine(tmp_path))]) == 0
    approvals = json.loads(capsys.readouterr().out)["approvals"]
    assert [(a["kind"], a["subject"], a["digest"]) for a in approvals] == [
        ("memory", "/s", "d"),
        ("other", "/t", "e"),
    ]


def test_the_records_surface_loads_no_command_module() -> None:
    # The surface the record is reached through loads no command module and no CLI frame.
    # Imported from this checkout's own `src/`, and not under `-I`, which would ignore
    # `PYTHONPATH` and import whichever stayfixed the environment installed. No mutation of its
    # own: the surface imports `boundary` and `record`, neither of which imports a command module.
    source = ROOT / "src"
    probe = IMPORT_EACH + "print(sys.modules['stayfixed'].__file__)\n"
    completed = subprocess.run(
        [sys.executable, "-c", probe, "stayfixed.trust.api"],
        capture_output=True,
        text=True,
        check=True,
        env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(source)},
    )
    *lines, origin = completed.stdout.splitlines()
    loaded = " ".join(lines).split()
    assert Path(origin).is_relative_to(source), origin
    assert "stayfixed.trust.api" in loaded
    assert not {"stayfixed.trust.commands", "stayfixed.command"} & set(loaded)
