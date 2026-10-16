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
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from stayfixed.memory.approvals import NO_CONFIGURATION
from stayfixed.printed import CLIPPED_CHARS
from stayfixed.trust import kinds
from stayfixed.trust.approving import NOT_A_TERMINAL, UNKNOWN_KIND
from stayfixed.trust.commands import NOTHING_TO_REVOKE, UNDESCRIBED
from stayfixed.trust.kinds import DUPLICATE_KIND, ApprovalKind
from stayfixed.trust.record import RECORD, State, approve, record_path, recorded, state
from tests.boundaries.test_delivery import IMPORT_EACH
from tests.crafted import CRAFTED, assert_never_raw
from tests.floor import developer_free_environ
from tests.memory.test_commands import common, invoke
from tests.memory.test_commands import project as project
from tests.ownerhome import ROOT, as_owner_home, stayfixed_argv
from tests.sandboxed import refuse_writes_under
from tests.scriptload import SCRIPTS, load

T0 = datetime(2026, 10, 16, 9, 30, tzinfo=UTC)

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
    # An agent's shell tool runs a command with no terminal on standard input, so both spellings
    # refuse there with exit 2, name the exact command for a person to run, and write no byte.
    # Mutations (`mutations/`'s "trust approve asks no terminal" -> the first spelling approves;
    # "the memory trust alias asks no terminal" -> the second does).
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


def test_the_refusal_asks_for_the_person_and_tells_an_agent_to_stop() -> None:
    # The refusal's likely reader is an agent's shell tool. It once told that reader to run the
    # command "yourself, in a terminal" and said the check guarantees nothing against an agent that
    # can open one, which pointed the agent at the way past it. It names the person instead, tells
    # an agent to stop, and says nothing of how a terminal could be had. Mutation (`mutations/`'s
    # "the terminal refusal tells its reader to run the approval itself"): the old wording reads
    # "yourself", and names no person.
    refusal = NOT_A_TERMINAL.format(command="stayfixed trust approve memory")
    assert (
        "ask the person at this machine to run `stayfixed trust approve memory` in their own "
        "terminal" in refusal
    )
    assert refusal.endswith("an agent must not run it for them")
    for said in ("yourself", "pseudo", "guarantee", "open a terminal", "pty"):
        assert said not in refusal


# The approval as every sentence below asks for it: of the person at the machine, with an agent
# told to stop, written out here so the words a reader meets are held whole.
ASKED = (
    "ask the person at this machine to run `stayfixed trust approve memory` in their own terminal "
    "— an agent must not run it for them"
)


def test_every_sentence_that_names_the_memory_approval_asks_for_the_person() -> None:
    # The sentences outside `trust` that name the approval reach a session's context or an agent's
    # shell tool, and each used to say "run `stayfixed trust approve memory` in a terminal", which
    # an agent able to open a pseudo-terminal reads as its instruction. Each asks for the person
    # now, in the words `trust approve`'s own refusal uses. `REVOKED` is written out in its module,
    # which imports nothing at module level that discovery would load, so it is held whole.
    # Mutations (`mutations/`'s "the terminal refusal tells its reader to run the approval itself"
    # -> every sentence built on the shared words; "the revoked link line tells its reader to
    # approve in a terminal" -> `REVOKED`; "memory asks no person for the store's approval" -> the
    # three `memory` sentences; "attach asks no person for the store's approval" -> the two
    # `attach` sentences).
    from stayfixed.attach.write import HARNESS_WAITS, REAPPROVE
    from stayfixed.memory.commands import _DROPPED, _LINK_WAITS, _UNTRUSTED
    from stayfixed.memory.hooks import REVOKED

    assert (
        "stayfixed: this store is no longer trusted, so the harness memory link was removed; once "
        f"what changed has been reviewed, {ASKED}"
    ) == REVOKED
    assert _UNTRUSTED.endswith(f"nor through the harness memory link; {ASKED}")
    assert _LINK_WAITS.endswith(f"volatile-notes bundles; to link it, {ASKED}")
    assert _DROPPED.endswith(f"if the store should reach a session, {ASKED}")
    assert HARNESS_WAITS.endswith(f"no approval yet; {ASKED}; then run `stayfixed attach` again")
    assert f"read what changed, then {ASKED}; then run `stayfixed attach` again" == REAPPROVE


@pytest.mark.parametrize("argv", SPELLINGS, ids=["trust-approve", "memory-trust"])
def test_a_terminal_approves(project: Path, tmp_path: Path, argv: list[str]) -> None:
    # The other half of `test_no_terminal_no_approval`: under a pseudo-terminal both spellings
    # approve the store at its digest now. No mutation of its own: it is the positive control for
    # that case, without which a refusal for any reason would pass it.
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


def test_the_alias_keeps_its_old_json_keys(
    project: Path, capsys: pytest.CaptureFixture[str], at_a_terminal: None
) -> None:
    # The old spelling lives one release, and a caller of its `--json` read `was_trusted`,
    # `trusted` and `digest`; they stay beside the approve path's keys, each read off this run.
    # Mutations (`mutations/`'s "the memory trust alias drops its old JSON keys" -> no
    # `was_trusted`; "the memory trust alias says the store was trusted before it approved it" ->
    # the first run's `was_trusted` reads true).
    argv = ["memory", "trust", "--in-repo-memory", "--json", *common(project)]
    assert invoke(argv) == 0
    first = json.loads(capsys.readouterr().out)
    (approved,) = first["approved"]
    assert (first["was_trusted"], first["trusted"]) == (False, True)
    assert first["digest"] == approved["digest"]
    assert state(_machine(project), "memory", _store_key(project), first["digest"]) is (
        State.APPROVED
    )
    assert invoke(argv) == 0
    second = json.loads(capsys.readouterr().out)
    assert (second["was_trusted"], second["trusted"], second["digest"]) == (
        True,
        True,
        first["digest"],
    )


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


@pytest.mark.parametrize("verb", ["revoke", "approve"])
def test_a_record_write_a_sandbox_refused_says_a_person_must_run_it(
    project: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    at_a_terminal: None,
    verb: str,
) -> None:
    # From an agent's sandboxed shell the machine directory cannot be written (`EPERM`, as macOS's
    # sandbox answers), so a revoke there, and an approval from a pseudo-terminal there, end in
    # exit 2 and the record's constant sentence, nothing written, never a traceback. Mutation
    # (`mutations/`'s "the trust record says nothing of the sandbox that refused its write"):
    # exit 1 and the sentence about a directory that cannot be written.
    from stayfixed.trust.record import SANDBOXED

    assert invoke(["trust", "approve", "memory", *common(project)]) == 0
    if verb == "approve":
        assert invoke(["trust", "revoke", "memory", *common(project)]) == 0
    before = recorded(_machine(project))
    refused = refuse_writes_under(monkeypatch, _machine(project).parent / RECORD)
    capsys.readouterr()
    assert invoke(["trust", verb, "memory", *common(project)]) == 2
    err = capsys.readouterr().err
    assert refused == [_machine(project).parent / RECORD]
    assert err == f"stayfixed: refused: {SANDBOXED}\n"
    assert recorded(_machine(project)) == before


def test_revoke_of_nothing_lists_what_is_recorded(
    project: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    at_a_terminal: None,
) -> None:
    # Exit 1 and the kind's recorded subjects, named on the line and in `--json` whole. The
    # subject, an absolute path, used to print withheld, which named nothing. Mutations
    # (`mutations/`'s "a revoke of nothing exits 0" -> exit 0; "a recorded subject under the home
    # prints whole" -> the line names the whole path).
    as_owner_home(monkeypatch, tmp_path)
    assert invoke(["trust", "approve", "memory", *common(project)]) == 0
    capsys.readouterr()
    argv = ["trust", "revoke", "memory", "--subject", "/elsewhere", "--json", *common(project)]
    assert invoke(argv) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["recorded"] == [_store_key(project)]
    assert payload["summary"] == (
        f"{NOTHING_TO_REVOKE.format(kind='memory')}; recorded: ~/project/.stayfixed/local/memory"
    )
    assert _approved(project)


def test_list_all_names_each_subject_from_the_home(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    # A subject under the home the password database records prints from `~`, one anywhere else
    # whole, both through `printed.clipped`. Mutation (`mutations/`'s "a recorded subject under the
    # home prints whole"): the first line names the whole path, quoted.
    home = tmp_path.resolve()
    as_owner_home(monkeypatch, home)
    machine = tmp_path / "machine.toml"
    approve(machine, "memory", str(home / "project" / ".stayfixed" / "memory"), "d", now=T0)
    approve(machine, "memory", "/zz/elsewhere/memory", "e", now=T0)
    assert invoke(["trust", "list", "--all", "--machine", str(machine)]) == 0
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
    # prints raw" -> both listings carry the escape; "revoke's recorded list prints a subject raw"
    # -> the revoke line does).
    as_owner_home(monkeypatch, tmp_path / "owner")
    machine = tmp_path / "machine.toml"
    hostile, long = f"/{CRAFTED}", "/" + "a" * 300
    approve(machine, "memory", hostile, "d", now=T0)
    approve(machine, "memory", long, "e", now=T0)
    shown = (repr(hostile), f"{long[:CLIPPED_CHARS]!r}…({len(long)} chars)")
    assert invoke(["trust", "list", "--all", "--machine", str(machine)]) == 0
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


def test_list_says_why_a_kind_has_nothing_to_approve(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # The line used to send its reader to `trust approve` for the reason, which refuses with no
    # terminal before it asks the kind anything, and left out `--root` and `--machine`. It says
    # the kind's own reason instead. Mutation (`mutations/`'s "trust list sends its reader to the
    # approve command for the reason"): the line names `trust approve` and no reason. The reason is
    # the one a session would have: the kind is described as a session reads the checkout.
    root = tmp_path / "uninitialised"
    root.mkdir()
    machine = tmp_path / "machine.toml"
    reason = NO_CONFIGURATION
    argv = ["trust", "list", "--root", str(root), "--machine", str(machine)]
    assert invoke(argv) == 0
    assert capsys.readouterr().out == f"memory: nothing to approve in this checkout: {reason}\n"
    assert invoke([*argv, "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["subjects"] == [
        {"kind": "memory", "state": "undescribed", "reason": reason}
    ]


def test_list_names_the_command_on_every_unapproved_line(
    project: Path, capsys: pytest.CaptureFixture[str], at_a_terminal: None
) -> None:
    # Mutation (`mutations/`'s "trust list names no command on an unapproved line"): the missing
    # line says only its state.
    command = shlex.join(["stayfixed", "trust", "approve", "memory", *common(project)])
    assert invoke(["trust", "list", *common(project)]) == 0
    assert capsys.readouterr().out == (
        f"memory .stayfixed/local/memory: missing — to approve it, ask the person at this machine "
        f"to run `{command}` in their own terminal — an agent must not run it for them\n"
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
    assert list(kinds.kinds()["memory"].flags) == ["--store"]


# --- list and revoke describe a checkout as the session reads it ---------------------------------


def _newer(project: Path) -> None:
    """A section a newer stayfixed added: a session reads past it, a command refuses the file."""
    with (project / "stayfixed.toml").open("a", encoding="utf-8") as document:
        document.write("\n[newer]\nx = 1\n")


def test_list_reports_an_approval_a_session_uses_past_a_newer_section(
    project: Path, capsys: pytest.CaptureFixture[str], at_a_terminal: None
) -> None:
    # A session keeps reading a `stayfixed.toml` a newer release added a section to, so it keeps
    # using the store's approval; `trust list` said there was nothing to approve. Mutation
    # (`mutations/`'s "trust list describes a checkout as a command reads it"): the line says the
    # kind has nothing to approve.
    assert invoke(["trust", "approve", "memory", *common(project)]) == 0
    _newer(project)
    capsys.readouterr()
    assert invoke(["trust", "list", "--json", *common(project)]) == 0
    (row,) = json.loads(capsys.readouterr().out)["subjects"]
    assert (row["kind"], row["state"]) == ("memory", "approved")


def test_revoke_withdraws_an_approval_a_session_uses_past_a_newer_section(
    project: Path, capsys: pytest.CaptureFixture[str], at_a_terminal: None
) -> None:
    # The fail-safe direction withdraws what a session would use, whatever a command would refuse
    # in the file: the documented spelling refused here while the session went on injecting.
    # Mutation (`mutations/`'s "trust revoke describes a checkout as a command reads it"): exit 1
    # and the approval stays.
    assert invoke(["trust", "approve", "memory", *common(project)]) == 0
    _newer(project)
    assert invoke(["trust", "revoke", "memory", *common(project)]) == 0
    assert not _approved(project)


def test_revoke_that_cannot_describe_the_checkout_names_the_spelling_that_can(
    project: Path, capsys: pytest.CaptureFixture[str], at_a_terminal: None
) -> None:
    # Once `stayfixed.toml` is gone the kind cannot describe the store, so a bare revoke cannot
    # find its key; it says why, names `--subject` and `trust list --all`, lists what is recorded,
    # and exits 1, rather than refusing with the loader's message. Mutation (`mutations/`'s "trust
    # revoke lets a kind that cannot describe the checkout refuse"): exit 2 and the kind's reason.
    assert invoke(["trust", "approve", "memory", *common(project)]) == 0
    (project / "stayfixed.toml").unlink()
    capsys.readouterr()
    assert invoke(["trust", "revoke", "memory", *common(project)]) == 1
    said = UNDESCRIBED.format(kind="memory", reason=NO_CONFIGURATION)
    out = capsys.readouterr().out
    assert out.startswith(f"{said}; recorded: "), out
    assert _approved(project)


def test_the_records_surface_loads_no_command_module() -> None:
    # `memory` imports `trust.api` on the hook path, so the surface the record is reached through
    # loads no command module and no CLI frame: the approve path both spellings run lives in
    # `trust.approving`. Mutation (`mutations/`'s "the trust surface takes the approve path from the
    # command module"): `stayfixed.trust.commands` and `stayfixed.command` load with it.
    loaded = subprocess.run(
        [sys.executable, "-I", "-c", IMPORT_EACH, "stayfixed.trust.api"],
        capture_output=True,
        text=True,
        check=True,
        env={**developer_free_environ(), "PYTHONPATH": str(ROOT / "src")},
    ).stdout.split()
    assert "stayfixed.trust.api" in loaded
    assert not {"stayfixed.trust.commands", "stayfixed.command"} & set(loaded)
