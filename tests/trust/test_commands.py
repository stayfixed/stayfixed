"""`stayfixed trust list | approve | revoke` (`src/stayfixed/trust/commands.py`), the `memory`
kind the memory area contributes, and the `memory trust --in-repo-memory` alias.

`approve` is asked of a person: through a real subprocess whose standard input is not a terminal
it refuses and writes nothing, and under a pseudo-terminal (`scripts/ptyrun.py`) it approves.
In-process cases replace the terminal check (`kinds.interactive`) instead."""

from __future__ import annotations

import functools
import json
import shlex
import subprocess
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from stayfixed.trust import kinds
from stayfixed.trust.commands import NOT_A_TERMINAL, NOTHING_TO_REVOKE, UNKNOWN_KIND
from stayfixed.trust.kinds import DUPLICATE_KIND, ApprovalKind
from stayfixed.trust.record import RECORD, State, record_path, recorded, state
from tests.floor import developer_free_environ
from tests.memory.test_commands import common, invoke
from tests.memory.test_commands import project as project
from tests.ownerhome import stayfixed_argv
from tests.scriptload import SCRIPTS, load

SPELLINGS = [["trust", "approve", "memory"], ["memory", "trust", "--in-repo-memory"]]


@functools.cache
def _ptyrun() -> ModuleType:
    return load(SCRIPTS / "ptyrun.py", "ptyrun_for_trust_tests")


def _machine(project: Path) -> Path:
    return project.parent / "machine.toml"


def _store_key(project: Path) -> str:
    return str((project / ".stayfixed" / "local" / "memory").resolve())


def _approved(project: Path) -> bool:
    entries = recorded(_machine(project))
    return ("memory", _store_key(project)) in entries


def _files(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


@pytest.fixture
def at_a_terminal(monkeypatch: pytest.MonkeyPatch) -> None:
    """The in-process seam: standard input reads as a terminal."""
    monkeypatch.setattr(kinds, "interactive", lambda: True)


@pytest.mark.parametrize("argv", SPELLINGS, ids=["trust-approve", "memory-trust"])
def test_no_terminal_no_approval(project: Path, tmp_path: Path, argv: list[str]) -> None:
    # Review Focus 5: an agent's shell tool runs a command with no terminal on standard input, so
    # both spellings refuse there with exit 2, name the exact command for a person to run, and
    # write no byte. Mutations (`mutations/`'s "trust approve asks no terminal" -> the first
    # spelling approves; "the memory trust alias asks no terminal" -> the second does).
    before = _files(tmp_path)
    proc = subprocess.run(
        [*stayfixed_argv(tmp_path / "owner"), *argv, *common(project)],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        check=False,
        env=developer_free_environ(),
    )
    command = shlex.join(["stayfixed", "trust", "approve", "memory", *common(project)])
    assert proc.returncode == 2, proc.stderr
    assert proc.stderr == f"stayfixed: refused: {NOT_A_TERMINAL.format(command=command)}\n"
    path = record_path(_machine(project))
    assert path is not None and not path.exists()
    assert _files(tmp_path) == before


@pytest.mark.parametrize("argv", SPELLINGS, ids=["trust-approve", "memory-trust"])
def test_a_terminal_approves(project: Path, tmp_path: Path, argv: list[str]) -> None:
    # The other half of Review Focus 5: under a pseudo-terminal both spellings approve the store
    # at its digest now. No mutation of its own: it is the positive control for the case above,
    # without which a refusal for any reason would pass it.
    code, output = _ptyrun().run_in_pty(
        [*stayfixed_argv(tmp_path / "owner"), *argv, *common(project)],
        env=developer_free_environ(),
    )
    assert code == 0, output
    assert _approved(project)
    assert "approved memory .stayfixed/local/memory at digest " in output


def test_the_alias_says_its_new_spelling(
    project: Path, capsys: pytest.CaptureFixture[str], at_a_terminal: None
) -> None:
    # The old spelling names the new one once it has run. Mutation: none of its own; the note is
    # one constant, and this asserts the line it prints.
    from stayfixed.memory.commands import ALIAS_NOTE

    assert invoke(["memory", "trust", "--in-repo-memory", *common(project)]) == 0
    assert capsys.readouterr().out.splitlines()[-1] == ALIAS_NOTE


def test_revoke_needs_no_terminal(project: Path, tmp_path: Path, at_a_terminal: None) -> None:
    # Withdrawing is the direction that fails safe, so it runs from an agent's shell tool too.
    # Mutation (`mutations/`'s "trust revoke revokes nothing"): the approval stays.
    assert invoke(["trust", "approve", "memory", *common(project)]) == 0
    assert _approved(project)
    proc = subprocess.run(
        [*stayfixed_argv(tmp_path / "owner"), "trust", "revoke", "memory", *common(project)],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        check=False,
        env=developer_free_environ(),
    )
    assert proc.returncode == 0, proc.stderr
    assert not _approved(project)


def test_revoke_of_nothing_lists_what_is_recorded(
    project: Path, capsys: pytest.CaptureFixture[str], at_a_terminal: None
) -> None:
    # Exit 1 and the kind's recorded subjects, in `--json` whole. Mutation (`mutations/`'s "a
    # revoke of nothing exits 0"): exit 0.
    assert invoke(["trust", "approve", "memory", *common(project)]) == 0
    capsys.readouterr()
    argv = ["trust", "revoke", "memory", "--subject", "/elsewhere", "--json", *common(project)]
    assert invoke(argv) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["recorded"] == [_store_key(project)]
    # The subject is an absolute path, outside the grammar a printed name keeps to.
    assert payload["summary"] == (
        f"{NOTHING_TO_REVOKE.format(kind='memory')}; recorded: <unprintable name; see --json>"
    )
    assert _approved(project)


def test_list_names_the_command_on_every_unapproved_line(
    project: Path, capsys: pytest.CaptureFixture[str], at_a_terminal: None
) -> None:
    # Mutation (`mutations/`'s "trust list names no command on an unapproved line"): the missing
    # line says only its state.
    command = shlex.join(["stayfixed", "trust", "approve", "memory", *common(project)])
    assert invoke(["trust", "list", *common(project)]) == 0
    assert capsys.readouterr().out == (
        f"memory .stayfixed/local/memory: missing — run `{command}` in a terminal to approve it\n"
    )
    assert invoke(["trust", "approve", "memory", *common(project)]) == 0
    capsys.readouterr()
    assert invoke(["trust", "list", *common(project)]) == 0
    assert capsys.readouterr().out == "memory .stayfixed/local/memory: approved\n"


def test_list_reads_lapsed_after_a_note_changes(
    project: Path, capsys: pytest.CaptureFixture[str], at_a_terminal: None
) -> None:
    # The digest moves with a note, and the record tells that from no approval at all. No mutation
    # of its own: `state`'s arms are held in `tests/trust/test_record.py`.
    assert invoke(["trust", "approve", "memory", *common(project)]) == 0
    note = project / ".stayfixed" / "local" / "memory" / "developer" / "a.md"
    note.write_text(note.read_text(encoding="utf-8") + "More.\n", encoding="utf-8")
    capsys.readouterr()
    assert invoke(["trust", "list", "--json", *common(project)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["subjects"] == [
        {"kind": "memory", "subject": _store_key(project), "state": "lapsed"}
    ]


def test_list_all_names_every_record_on_the_machine(
    project: Path, capsys: pytest.CaptureFixture[str], at_a_terminal: None
) -> None:
    # `--all` reads the record, not the checkout. No mutation of its own: a listing with nothing
    # in it fails the length assertion below.
    assert invoke(["trust", "approve", "memory", *common(project)]) == 0
    capsys.readouterr()
    assert invoke(["trust", "list", "--all", "--json", *common(project)]) == 0
    approvals = json.loads(capsys.readouterr().out)["approvals"]
    assert [(a["kind"], a["subject"]) for a in approvals] == [("memory", _store_key(project))]
    assert state(_machine(project), "memory", _store_key(project), approvals[0]["digest"]) is (
        State.APPROVED
    )


def test_an_unknown_kind_names_the_known_ones(
    project: Path, capsys: pytest.CaptureFixture[str], at_a_terminal: None
) -> None:
    # The name typed is not repeated, the known ones are. No mutation of its own: an unknown kind
    # reaching the approve path raises a `KeyError`, an internal error, which the exact line here
    # tells from this refusal.
    assert invoke(["trust", "approve", "nonsense", *common(project)]) == 2
    err = capsys.readouterr().err
    assert err == f"stayfixed: refused: {UNKNOWN_KIND.format(known='memory')}\n"
    assert not (_machine(project).parent / RECORD).exists()


def test_kind_discovery_refuses_a_duplicate_name(monkeypatch: pytest.MonkeyPatch) -> None:
    # Two areas naming one kind would let either answer for the other's subjects. Mutation
    # (`mutations/`'s "approval kind discovery accepts a duplicate name"): the second replaces the
    # first.
    from stayfixed.errors import Failure

    kind = ApprovalKind("memory", lambda context: ())
    first = SimpleNamespace(__name__="stayfixed.a.approvals", KINDS=(kind,))
    second = SimpleNamespace(__name__="stayfixed.b.approvals", KINDS=(kind,))
    monkeypatch.setattr(kinds, "area_modules", lambda submodule: [first, second])
    with pytest.raises(Failure) as refused:
        kinds.kinds()
    assert str(refused.value) == DUPLICATE_KIND.format(
        name="memory", first="stayfixed.a.approvals", second="stayfixed.b.approvals"
    )


def test_the_areas_contribute_the_memory_kind() -> None:
    # Discovery reads `stayfixed.memory.approvals` and no core module names it. No mutation of its
    # own: an empty discovery reddens every approve case above.
    assert list(kinds.kinds()) == ["memory"]
    assert kinds.kinds()["memory"].flags == ("--store",)
