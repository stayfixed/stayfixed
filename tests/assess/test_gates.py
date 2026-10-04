"""Every configured gate as a value: the five built-ins in the loader's order, each finding what
its area's command finds, and a project's own gate as its argv — bounded, and ended whole."""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
import time
from dataclasses import replace
from pathlib import Path

import pytest

from stayfixed.assess import gates
from stayfixed.assess.gates import (
    BASE,
    BUILTIN,
    GateContext,
    GateResult,
    configured,
    run_gates,
    stopped,
)
from stayfixed.cli import build_parser, discover_registrars
from stayfixed.config.loader import load
from stayfixed.config.schema import BUILTIN_GATES, Config, CustomGate, Gates
from stayfixed.errors import Failure
from tests.assess.smoke import BASE as SMOKE_BASE
from tests.assess.smoke import FIXTURE, smoke_repo
from tests.gitfixture import git, needs_git

# The command starts a child and then sleeps. The child writes `started` at once and `late`
# 2.5 s after: a gate that ended only the command it started leaves this one to write `late`.
# `started` is what proves the descendant existed before the gate ended the command; without
# it, a loaded machine that had not yet started the child would pass these cases vacuously.
DELAYED_WRITER = (
    "import subprocess, sys, time\n"
    "subprocess.Popen([sys.executable, '-c', "
    '\'import pathlib, sys, time; pathlib.Path(sys.argv[1]).write_text("x"); '
    'time.sleep(2.5); pathlib.Path(sys.argv[2]).write_text("x")\', '
    "sys.argv[1], sys.argv[2]])\n"
    "time.sleep(30)\n"
)
# The same child, from a command that exits 0 as soon as the child has written `started`: a
# gate that passed and left its background work running into the gates after it.
EXITING_WRITER = DELAYED_WRITER.replace(
    "time.sleep(30)\n",
    "import pathlib\nwhile not pathlib.Path(sys.argv[1]).exists():\n    time.sleep(0.05)\n",
)
# Past the child's own 2.5 s from any moment it could have started in the cases below.
LATE_WAIT_SECONDS = 3.0
STARTED_WAIT_SECONDS = 20


def delayed_writer(tmp_path: Path) -> tuple[list[str], Path, Path]:
    started, late = tmp_path / "started", tmp_path / "late"
    return [sys.executable, "-c", DELAYED_WRITER, str(started), str(late)], started, late


def fixture_config(tmp_path: Path) -> Config:
    """The smoke fixture's configuration, read in place: a custom gate needs no repository."""
    return load(FIXTURE, machine=tmp_path / "m.toml")


def smoke(tmp_path: Path) -> tuple[Path, Config]:
    root = smoke_repo(tmp_path)
    return root, load(root, machine=tmp_path / "m.toml")


def results(root: Path, config: Config, *names: str, base: str = SMOKE_BASE) -> list[GateResult]:
    return list(run_gates(GateContext(root, config, base), names or config.gate_names))


def with_custom(config: Config, argv: list[str], *, seconds: int = 60) -> Config:
    gates = Gates(
        builtin=(), custom_timeout_seconds=seconds, custom={"probe": CustomGate(tuple(argv))}
    )
    return replace(config, gates=gates)


def test_the_built_in_gates_are_the_loader_s_vocabulary_in_its_order() -> None:
    # The loader validates `[gates] builtin` against `BUILTIN_GATES`; a gate it accepts that
    # this table does not hold is a `KeyError` at run time. Mutation (advisory): delete the
    # `bugs` entry from `BUILTIN` — this reddens.
    assert tuple(gate.name for gate in BUILTIN) == BUILTIN_GATES


def test_each_gate_s_command_is_one_the_real_parser_accepts() -> None:
    # `command` is what a remedy tells a person to run, so it must be a command. Mutations
    # (advisory): `"docs trail --check"` becomes `"trail --check"` (no such group), and
    # `"bugs check"` becomes `"bugs"` (a group alone has no `func`) — each reddens.
    parser = build_parser(discover_registrars())
    for gate in BUILTIN:
        args = parser.parse_args(shlex.split(gate.command.replace(BASE, "0" * 40)))
        assert callable(getattr(args, "func", None)), gate.command


@needs_git
def test_the_smoke_fixture_passes_every_gate(tmp_path: Path) -> None:
    root, config = smoke(tmp_path)
    found = results(root, config)
    assert [result.name for result in found] == list(BUILTIN_GATES)
    assert [result for result in found if result.failing] == []


@needs_git
def test_the_docs_gate_finds_an_over_budget_agents_file(tmp_path: Path) -> None:
    root, config = smoke(tmp_path)
    (root / config.paths.agents_md).write_text("line\n" * 400, encoding="utf-8")
    [docs] = results(root, config, "docs")
    assert "agents-lines" in [finding.rule for finding in docs.findings]


@needs_git
def test_the_bugs_gate_finds_a_broken_entry(tmp_path: Path) -> None:
    root, config = smoke(tmp_path)
    entry = root / config.paths.bugs / "BR-001.md"
    entry.write_text(entry.read_text(encoding="utf-8") + "<<<<<<< ours\n", encoding="utf-8")
    [bugs] = results(root, config, "bugs")
    assert "conflict-marker" in [finding.rule for finding in bugs.findings]


@needs_git
def test_a_base_the_bugs_gate_cannot_list_is_a_gate_that_could_not_run(tmp_path: Path) -> None:
    # With no ledger in the tree the gate asks the base whether it had one, and a base this
    # clone does not have is no answer: could not run, which fails an enforced gate, and never
    # "the base had none", which would pass the change that deleted the ledger.
    root, config = smoke(tmp_path)
    git(root, "rm", "-rq", config.paths.bugs, config.paths.bug_index)
    [bugs] = results(root, config, "bugs", base="refs/remotes/origin/absent")
    assert (bugs.answered, bugs.findings) == (False, ())
    [bugs] = results(root, config, "bugs")
    # The fixture's own code mentions its entry, which now dangles beside the removed ledger.
    assert [finding.rule for finding in bugs.findings] == ["ledger-removed", "dangling-mention"]


@needs_git
def test_the_plan_gate_finds_a_plan_the_change_touches(tmp_path: Path) -> None:
    root, config = smoke(tmp_path)
    (root / config.paths.plans / "2026-09-20-new.md").write_text("# New\n", encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "docs: a plan with no scope")
    [plan] = results(root, config, "plan")
    assert "scope-missing" in [finding.rule for finding in plan.findings]


@needs_git
def test_the_commit_gate_finds_an_attribution_trailer_after_the_base(tmp_path: Path) -> None:
    root, config = smoke(tmp_path)
    message = "fix: a change\n\nCo-Authored-By: Claude <noreply@anthropic.com>\n"
    git(root, "commit", "-q", "--allow-empty", "-m", message)
    sha = git(root, "rev-parse", "HEAD").strip()
    [commit] = results(root, config, "commit")
    assert [(finding.rule, finding.path) for finding in commit.findings] == [("attribution", sha)]


@needs_git
def test_a_stale_trail_is_a_failing_gate(tmp_path: Path) -> None:
    # The fixture's own listing is current, so the pass case cannot see the stale arm.
    root, config = smoke(tmp_path)
    (root / config.paths.plans / "2026-09-20-new.md").write_text("# New\n", encoding="utf-8")
    git(root, "add", "-A")
    [trail] = results(root, config, "trail")
    assert [finding.rule for finding in trail.findings] == ["trail-stale"]
    assert trail.failing


@needs_git
def test_a_commit_range_git_cannot_read_is_a_gate_that_did_not_answer(tmp_path: Path) -> None:
    # `check_range` refuses a range git cannot read. A gate that could not judge the tree is
    # failing, and its reason names the command with the base's placeholder, never the base:
    # the base is whatever a caller was handed.
    root, config = smoke(tmp_path)
    [commit] = results(root, config, "commit", base="no-such-ref")
    assert not commit.answered
    assert commit.failing
    assert "`stayfixed commit check --range <base>..HEAD`" in commit.reason
    assert "no-such-ref" not in commit.reason


def test_a_name_the_configuration_does_not_hold_is_a_caller_s_bug(tmp_path: Path) -> None:
    # Callers validate names first; one that reaches here is their bug, not a gate that passed.
    # Mutation (advisory): `wanted = {gates[name].name for name in names}` becomes
    # `wanted = set(names)` — the unknown name is silently dropped and this reddens.
    config = with_custom(fixture_config(tmp_path), ["true"])
    with pytest.raises(KeyError):
        run_gates(GateContext(tmp_path, config, SMOKE_BASE), ["lint"])


@needs_git
def test_each_named_gate_runs_once_in_the_configured_order(tmp_path: Path) -> None:
    root, config = smoke(tmp_path)
    found = results(root, config, "trail", "docs", "trail")
    assert [result.name for result in found] == ["docs", "trail"]


@needs_git
def test_a_gate_that_raises_did_not_answer_and_every_gate_after_it_still_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # `docs_gate` looks `check_budgets` up in its own module at call time, so the patch reaches
    # it through the function `gates` holds. The exception's text quotes the repository, and
    # must not travel into the reason.
    root, config = smoke(tmp_path)

    def raising(*args: object) -> list[object]:
        raise Failure("a message that quotes the repository")

    monkeypatch.setattr("stayfixed.docs.hygiene.check_budgets", raising)
    found = results(root, config)
    [docs] = [result for result in found if result.name == "docs"]
    assert not docs.answered
    assert "`stayfixed docs check`" in docs.reason
    assert "quotes" not in docs.reason
    assert [result.name for result in found if not result.answered] == ["docs"]
    assert [result.name for result in found] == list(BUILTIN_GATES)


@needs_git
def test_a_gate_that_recurses_past_the_limit_did_not_answer_and_the_rest_still_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A backstop behind every reader: a `RecursionError` out of any gate is that gate not
    # answering, never an internal error that ends the run. Mutation (declared): the
    # `RecursionError` arm dropped -> it escapes `run_gates`.
    root, config = smoke(tmp_path)

    def recursing(*args: object) -> list[object]:
        raise RecursionError("maximum recursion depth exceeded")

    monkeypatch.setattr("stayfixed.docs.hygiene.check_budgets", recursing)
    found = results(root, config)
    assert [result.name for result in found if not result.answered] == ["docs"]
    assert [result.name for result in found] == list(BUILTIN_GATES)


def test_the_configured_set_is_the_kept_built_ins_then_the_custom_gates(tmp_path: Path) -> None:
    # Mutation (advisory): `configured` returning every built-in and every custom gate, whatever
    # `[gates] builtin` keeps — this reddens.
    root = tmp_path / "project"
    root.mkdir()
    fixture = (FIXTURE / "stayfixed.toml").read_text(encoding="utf-8")
    gates = '\n[gates]\nbuiltin = ["docs"]\n\n[gates.custom.probe]\nrun = ["true"]\n'
    (root / "stayfixed.toml").write_text(fixture + gates, encoding="utf-8")
    config = load(root, machine=tmp_path / "m.toml")
    assert list(configured(config)) == ["docs", "probe"]


def test_a_custom_gate_that_exits_zero_passes(tmp_path: Path) -> None:
    # Mutation (advisory): `if code == 0:` becomes `if False:` — a passing command is one
    # finding and this reddens.
    config = with_custom(fixture_config(tmp_path), [sys.executable, "-c", "pass"])
    [probe] = results(tmp_path, config)
    assert probe.answered
    assert not probe.failing


def test_a_custom_gate_that_exits_non_zero_is_one_finding_and_its_output_passes_through(
    tmp_path: Path, capfd: pytest.CaptureFixture[str]
) -> None:
    # The command's bytes are the project's own and reach the terminal untouched — on standard
    # error, so `--json` on standard output stays one object — and reach no result: nothing
    # in the module reads them. One property per assertion below.
    marker = "stayfixed-probe-output"
    script = f"import sys; sys.stdout.write('\\x1b[31m{marker}\\n'); sys.exit(3)"
    config = with_custom(fixture_config(tmp_path), [sys.executable, "-c", script])
    [probe] = results(tmp_path, config)
    assert [(finding.rule, finding.detail) for finding in probe.findings] == [
        ("exit-status", "exited 3")
    ]
    out, err = capfd.readouterr()
    assert out == ""
    assert f"\x1b[31m{marker}" in err
    assert marker not in repr(probe)


def test_a_custom_gate_past_its_time_limit_did_not_answer(tmp_path: Path) -> None:
    command = [sys.executable, "-c", "import time; time.sleep(30)"]
    config = with_custom(fixture_config(tmp_path), command, seconds=1)
    [probe] = results(tmp_path, config)
    assert not probe.answered
    assert probe.failing
    assert probe.reason == "the command in [gates.custom.probe] run could not start, or ran past 1s"


def test_a_custom_gate_past_its_time_limit_leaves_nothing_running(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A timeout case with one sleeping process cannot show this: it is the descendant — a test
    # runner a shell wrapper started — that must not run on after the gate has reported.
    # Driven as the interrupt case below is: the bound expires once the child has written
    # `started`, never on the clock, which raced a real 2 s limit against two interpreter
    # start-ups and could give up before there was a descendant to end.
    command, started, late = delayed_writer(tmp_path)
    config = with_custom(fixture_config(tmp_path), command, seconds=600)
    # The bound expires in the wait for the command's exit, `gates._exited`: patching
    # `Popen.wait` would instead fail the reap after the command's own exit, 30 s later.
    calls: list[int] = []

    def expired(process: subprocess.Popen[bytes], seconds: int) -> None:
        calls.append(seconds)
        deadline = time.monotonic() + STARTED_WAIT_SECONDS
        while not started.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        raise subprocess.TimeoutExpired(process.args, seconds)

    monkeypatch.setattr(gates, "_exited", expired)
    [probe] = results(tmp_path, config)
    assert not probe.answered
    assert calls == [600]  # the configured bound is the one the gate waited under
    assert started.exists()
    time.sleep(LATE_WAIT_SECONDS)
    assert not late.exists()


def test_an_interrupted_custom_gate_leaves_nothing_running(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A terminal's Ctrl-C reaches stayfixed's process group and not the command's own session,
    # so nothing but the gate itself can end the command's tree on the way out.
    # The interrupt arrives once the child has written `started`, so there is a descendant to
    # end; the wait for it is bounded, and a child that never starts fails the assertion below.
    command, started, late = delayed_writer(tmp_path)
    config = with_custom(fixture_config(tmp_path), command, seconds=600)
    # The interrupt lands in the wait for the command's exit, which is `gates._exited` on every
    # platform: `os.waitid` where there is one, `Popen.wait` where there is not.

    def interrupted(process: subprocess.Popen[bytes], seconds: int) -> None:
        deadline = time.monotonic() + STARTED_WAIT_SECONDS
        while not started.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        raise KeyboardInterrupt

    monkeypatch.setattr(gates, "_exited", interrupted)
    with pytest.raises(KeyboardInterrupt):
        results(tmp_path, config)
    assert started.exists()
    time.sleep(LATE_WAIT_SECONDS)
    assert not late.exists()


def test_a_custom_gate_that_exits_leaves_nothing_running(tmp_path: Path) -> None:
    # A command that passes and leaves a child behind, a watcher or a server, say: the child
    # would go on writing into the tree while a later gate runs, and after the result is out.
    # The command exits only once the child has written `started`, so there is a descendant to
    # end. Mutation (declared): the group kill after the command's own exit dropped -> `late`
    # is written.
    command, started, late = delayed_writer(tmp_path)
    command[2] = EXITING_WRITER
    config = with_custom(fixture_config(tmp_path), command, seconds=STARTED_WAIT_SECONDS)
    [probe] = results(tmp_path, config)
    assert probe.answered
    assert not probe.failing
    assert started.exists()
    time.sleep(LATE_WAIT_SECONDS)
    assert not late.exists()


@pytest.mark.skipif(not hasattr(os, "waitid"), reason="no os.waitid (macOS before 3.13)")
@pytest.mark.parametrize(("source", "found"), [("pass", []), ("raise SystemExit(3)", ["exited 3"])])
def test_the_group_is_ended_while_the_command_s_pid_is_still_held(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, source: str, found: list[str]
) -> None:
    # The group's id is the command's pid, and a reaped pid is free for the system to hand to an
    # unrelated process that then leads a group of its own: the group kill after the command's
    # exit must come while the exited command is still unreaped, holding the id. Mutation
    # (declared): the exit waited for with `process.wait`, which reaps -> the command's
    # `returncode` is already set when the group is killed. The exit status still reads the same.
    killed_with: list[int | None] = []
    kill = gates._kill_group

    def spy(process: subprocess.Popen[bytes]) -> None:
        killed_with.append(process.returncode)
        kill(process)

    monkeypatch.setattr(gates, "_kill_group", spy)
    [probe] = results(
        tmp_path, with_custom(fixture_config(tmp_path), [sys.executable, "-c", source])
    )
    assert killed_with == [None]
    assert [finding.detail for finding in probe.findings] == found


def test_without_waitid_a_custom_gate_still_answers_and_ends_its_group(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # macOS before 3.13 has no `os.waitid`: the command is reaped by `wait` as before, and the
    # group is still ended after it. Mutation (by hand): the fallback dropped, so `os.waitid` is
    # called regardless -> AttributeError escapes `run_gates` and this reddens.
    monkeypatch.delattr(os, "waitid", raising=False)
    command, started, late = delayed_writer(tmp_path)
    command[2] = EXITING_WRITER
    config = with_custom(fixture_config(tmp_path), command, seconds=STARTED_WAIT_SECONDS)
    [probe] = results(tmp_path, config)
    assert probe.answered
    assert not probe.failing
    assert started.exists()
    time.sleep(LATE_WAIT_SECONDS)
    assert not late.exists()


@pytest.mark.parametrize("source", ["pass", "raise SystemExit(3)"])
def test_a_group_the_gate_may_not_signal_still_leaves_the_exit_status(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, source: str
) -> None:
    # macOS answers `PermissionError` for a group left with only the exited, unreaped command,
    # and any platform does for a descendant stayfixed may not signal (a sudo or setuid one),
    # which is then not ended. Either way the command's own exit is the gate's answer. Driven
    # portably: every `killpg` refuses. Mutation (oracle): "a group the gate may not signal ends
    # the gate run" -> `PermissionError` escapes `run_gates` and this reddens.
    def refused(pid: int, sig: int) -> None:
        raise PermissionError(1, "Operation not permitted")

    monkeypatch.setattr(os, "killpg", refused)
    [probe] = results(
        tmp_path, with_custom(fixture_config(tmp_path), [sys.executable, "-c", source])
    )
    assert probe.answered
    assert [finding.detail for finding in probe.findings] == (
        [] if source == "pass" else ["exited 3"]
    )


def test_custom_gates_named_first_run_before_every_other_custom_gate(tmp_path: Path) -> None:
    # `stayfixed gate` names the base's enforced gates first, so no other custom gate runs files
    # before they do. The built-ins keep their place: they run nothing the repository wrote.
    # Mutation (declared): every gate in configured order -> `first` is ignored and this reddens.
    ran = tmp_path / "ran"
    gates = {
        name: CustomGate((sys.executable, "-c", f"open({str(ran)!r}, 'a').write({name!r})"))
        for name in ("a", "b", "c")
    }
    config = fixture_config(tmp_path)
    config = replace(config, gates=replace(config.gates, builtin=("docs",), custom=gates))
    found = run_gates(
        GateContext(tmp_path, config, SMOKE_BASE), ["c", "b", "a", "docs"], first=frozenset({"c"})
    )
    assert [result.name for result in found] == ["docs", "c", "a", "b"]
    assert ran.read_text(encoding="utf-8") == "cab"


def test_no_custom_gate_starts_once_the_run_has_failed(tmp_path: Path) -> None:
    # The question is asked before every custom gate, those named first included, with the
    # results so far: `c`, named first, runs because nothing has failed yet, and fails; `d`,
    # named first too, and `a` are never started, and say why. Each runs files the change can
    # edit, and would run in the process that holds the failed verdict. Mutations (declared,
    # with the command's cases): the check made `if False:` -> `d` and `a` run and write their
    # letters; the question asked only outside `first` -> `d` runs.
    ran = tmp_path / "ran"
    gates = {
        name: CustomGate(
            (sys.executable, "-c", f"open({str(ran)!r}, 'a').write({name!r}); exit({code})")
        )
        for name, code in (("a", 0), ("c", 1), ("d", 0))
    }
    config = fixture_config(tmp_path)
    config = replace(config, gates=replace(config.gates, builtin=(), custom=gates))
    asked: list[tuple[str, ...]] = []

    def failed(done: tuple[GateResult, ...]) -> bool:
        asked.append(tuple(result.name for result in done))
        return any(result.failing for result in done)

    found = run_gates(
        GateContext(tmp_path, config, SMOKE_BASE),
        ["a", "c", "d"],
        first=frozenset({"c", "d"}),
        failed=failed,
    )
    assert found[1:] == (stopped("d"), stopped("a"))
    assert [result.failing for result in found] == [True, True, True]
    assert ran.read_text(encoding="utf-8") == "c"
    assert asked == [(), ("c",), ("c", "d")]


def test_a_custom_gate_whose_command_does_not_exist_did_not_answer(tmp_path: Path) -> None:
    # Mutation (advisory): drop the `except OSError:` around `Popen` — `FileNotFoundError`
    # escapes `run_gates` and this reddens.
    config = with_custom(fixture_config(tmp_path), ["no-such-command-anywhere"])
    [probe] = results(tmp_path, config)
    assert not probe.answered
    assert probe.failing
