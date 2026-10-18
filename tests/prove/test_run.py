"""`prove` runs a test command where it is typed and answers from the runner's own report alone.

Every case runs `tests/prove/stand_in.py`'s adapter and runner, so none needs a real test runner:
the adapter plans, the run launches what it planned in the directory the command was typed in,
and the verdict comes from the report the runner wrote and the code it exited with, in the order
`stayfixed.prove.run.CASCADE` gives, the first row that holds winning.
"""

from __future__ import annotations

import contextlib
import dataclasses
import hashlib
import io
import json
import os
import signal
import subprocess
import sys
import threading
import time
import types
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import TextIO

import pytest

from stayfixed import processes
from stayfixed.profiles.runners import ReportSource
from stayfixed.prove import adapters, tree
from stayfixed.prove import counts as counts_module
from stayfixed.prove import run as run_module
from stayfixed.prove.counts import REPORT_DOCTYPE, REPORT_TOO_LARGE, Counts
from stayfixed.prove.run import (
    ALL_SKIPPED,
    ASSIGNED_FORGING,
    EXIT,
    FAILING,
    GREEN_BUT_EXITED,
    INTERRUPTED,
    NO_REPORT,
    NONE_RAN,
    NOT_RECOGNISED,
    NOT_STARTED,
    REFUSED_LAUNCHER_OPTION,
    RESOLVED_ELSEWHERE,
    TIMED_OUT,
    WORDS,
    Receipt,
    Verdict,
    assignments,
    line,
    prove,
)
from tests.gitfixture import git
from tests.prove.stand_in import JUNIT, LATE_AFTER_SECONDS, NAME, StandIn

PROVED, FAILED, NOT_PROVEN, REFUSED = (
    Verdict.PROVED,
    Verdict.FAILED,
    Verdict.NOT_PROVEN,
    Verdict.REFUSED,
)
# How long a test waits for `--hang`'s runner to say it started: far past an interpreter's start,
# and a runner that never starts fails the assertion after the wait rather than hanging the suite.
STARTED_WAIT_SECONDS = 30
# How long an ended run's runner is left silent once it has started: past the tee's own wait on an
# idle pipe, a tenth of a second, so the tee is seen waiting.
IDLE_SECONDS = 0.5


def run(
    cwd: Path,
    *argv: str,
    adapter: StandIn | None = None,
    environ: dict[str, str] | None = None,
    timeout: float = 600,
    echo: TextIO | None = None,
) -> Receipt:
    return prove(
        argv,
        cwd=cwd,
        environ=dict(os.environ) if environ is None else environ,
        timeout=timeout,
        adapters=[adapter or StandIn()],
        echo=echo,
    )


@contextlib.contextmanager
def standard_input(data: bytes) -> Iterator[None]:
    """This process's standard input, the descriptor a launch inherits, a pipe that holds `data`
    and then ends, for as long as the block runs."""
    reader, writer = os.pipe()
    os.write(writer, data)
    os.close(writer)
    saved = os.dup(0)
    try:
        os.dup2(reader, 0)
        yield
    finally:
        os.dup2(saved, 0)
        for descriptor in (reader, saved):
            os.close(descriptor)


def repository(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    git(root, "init", "-q")
    (root / "README").write_text("r\n", encoding="utf-8")
    git(root, "add", "README")
    git(root, "commit", "-q", "-m", "first")
    return root


@pytest.mark.parametrize(
    ("report", "code", "verdict", "reason"),
    [
        ("pass", 0, PROVED, ""),
        ("fail", 1, FAILED, FAILING),
        ("empty", 0, FAILED, NONE_RAN),
        ("empty", 5, FAILED, NONE_RAN),
        ("empty", 1, FAILED, NONE_RAN),
        ("all-skipped", 0, FAILED, ALL_SKIPPED),
        ("all-skipped", 5, FAILED, ALL_SKIPPED),
        ("pass", 1, NOT_PROVEN, GREEN_BUT_EXITED),
        ("none", 0, NOT_PROVEN, NO_REPORT),
        ("doctype", 0, NOT_PROVEN, REPORT_DOCTYPE),
    ],
)
def test_the_cascade(tmp_path: Path, report: str, code: int, verdict: Verdict, reason: str) -> None:
    # A runner that ran no test, or skipped every one, failed whatever it exited with, and one that
    # exited non-zero over a green report proved nothing. Mutation (declared): the non-zero-exit
    # row ordered before the zero-tests row -> the `("empty", 5)` and `("empty", 1)` rows read
    # `not proven`.
    got = run(tmp_path, NAME, "--report", report, "--code", str(code))
    assert (got.verdict, got.reason) == (verdict, reason)
    assert got.exit_code == code
    assert EXIT[got.verdict] == {PROVED: 0, FAILED: 1, NOT_PROVEN: 1, REFUSED: 2}[verdict]


def test_the_counts_and_the_report_s_digest_are_the_report_s(tmp_path: Path) -> None:
    # Mutation (declared): the digest taken of nothing -> it differs.
    got = run(tmp_path, NAME, "--report", "fail", "--code", "1")
    assert got.counts == Counts(1, 1, 0)
    assert got.report_digest == hashlib.sha256(JUNIT["fail"]).hexdigest()
    assert got.runner == NAME
    assert got.program == os.path.realpath(sys.executable)
    assert got.verified is True


def test_printed_text_is_never_counted(tmp_path: Path) -> None:
    # No mutation: the run reads no line its command prints where the report is a file, so a
    # mutation would have to add a reader; the tee's own entries cover the standard-output case.
    got = run(tmp_path, NAME, "--print", "3 passed", "--report", "fail")
    assert (got.verdict, got.reason) == (FAILED, FAILING)


def test_the_runner_reads_nothing_piped_into_prove(tmp_path: Path) -> None:
    # Standard input is a channel stayfixed controls: whatever feeds `prove`'s, the agent or a pipe
    # upstream, could drive the runner (pytest's `--pdb` takes debugger commands there), so the
    # run's is `/dev/null` and a runner that reads it sees its end. Mutation (declared): the
    # caller's standard input inherited -> the runner reads `pass` and reports its failing tests
    # as passed.
    with standard_input(b"pass\n"):
        got = run(tmp_path, NAME, "--report", "fail", "--report-from-stdin")
    assert (got.verdict, got.reason, got.counts) == (FAILED, FAILING, Counts(1, 1, 0))


@pytest.mark.parametrize(
    "argv",
    [
        ["sh", "-c", "echo 3 passed"],
        # An `env` option leaves the command unread rather than guessed at.
        ["env", "-i", NAME],
        ["env", "-u", "HOME", NAME],
        ["env", "-S", f"FORGE=x {NAME}"],
        ["uv", "run", "env", "-i", "FORGE=x", NAME],
        [],
    ],
)
def test_an_unrecognised_command_is_not_proven(tmp_path: Path, argv: list[str]) -> None:
    got = run(tmp_path, *argv)
    assert (got.verdict, got.reason) == (NOT_PROVEN, NOT_RECOGNISED)
    assert got.runner is None
    assert got.exit_code is None
    assert line(got) == f"not proven: {WORDS[NOT_RECOGNISED]}"


@pytest.mark.parametrize(
    "argv",
    [
        ["env", "FORGE=x", NAME],
        ["FORGE=x", NAME],
        # Wherever the command spells the assignment: before the launcher or after it, bare or
        # after `env`.
        ["uv", "run", "env", "FORGE=x", NAME],
        ["env", "A=1", "uv", "run", "env", "FORGE=x", NAME],
        ["FORGE=x", "uv", "run", NAME],
        ["uv", "run", "FORGE=x", NAME],
    ],
)
def test_an_assigned_forging_variable_is_refused(tmp_path: Path, argv: list[str]) -> None:
    # Mutations (declared): the assigned name scrubbed from the run's environment instead of
    # refused -> the run goes ahead and the stand-in's green report is `proved`; the forging scan
    # stopping at the launcher -> the shapes past `uv run` are `proved`.
    adapter = StandIn()
    got = run(tmp_path, *argv, adapter=adapter)
    assert (got.verdict, got.reason) == (REFUSED, ASSIGNED_FORGING)
    assert got.detail == "FORGE"
    assert EXIT[got.verdict] == 2
    assert adapter.seen == []  # refused before anything was planned or run


@pytest.mark.parametrize(
    "argv",
    [
        ["env", "TYPED=yes", NAME],
        ["TYPED=yes", NAME],
        ["uv", "run", "env", "TYPED=yes", NAME],
        ["TYPED=no", "uv", "run", "env", "TYPED=yes", NAME],
    ],
)
def test_an_assigned_variable_outside_the_forging_set_reaches_the_runner(
    tmp_path: Path, argv: list[str]
) -> None:
    # `Popen` reads no shell assignment: the run hands it in the environment, the last of two
    # winning, and the word itself never reaches the argv. Mutation (declared): the assignments
    # read only up to the launcher -> the one past `uv run` never reaches the runner.
    got = run(tmp_path, *argv, "--expect-env", "TYPED=yes")
    assert got.verdict == PROVED


def test_an_inherited_scrubbed_variable_is_removed_and_counted(tmp_path: Path) -> None:
    adapter = StandIn(scrub=frozenset({"SCRUBBED"}))
    environ = {**os.environ, "SCRUBBED": "1", "KEPT": "1"}
    got = run(
        tmp_path,
        NAME,
        "--expect-unset",
        "SCRUBBED",
        "--expect-env",
        "KEPT=1",
        adapter=adapter,
        environ=environ,
    )
    assert (got.verdict, got.reason) == (PROVED, "")
    assert got.counts == Counts(2, 0, 0)
    # The removal is said: it can turn a legitimate run red, and nothing else tells the reader
    # why. Mutation (declared): the removed variables left off the receipt -> `scrubbed` is empty.
    assert got.scrubbed == ("SCRUBBED",)
    assert "; removed from the run's environment: SCRUBBED" in line(got)


def test_a_scrubbed_variable_the_run_did_not_inherit_is_not_named(tmp_path: Path) -> None:
    adapter = StandIn(scrub=frozenset({"SCRUBBED"}), set_env={"SET": "by-adapter"})
    environ = {name: value for name, value in os.environ.items() if name not in ("SCRUBBED", "SET")}
    got = run(tmp_path, NAME, adapter=adapter, environ={**environ, "SET": "by-adapter"})
    assert (got.verdict, got.scrubbed) == (PROVED, ())
    assert "removed from the run's environment" not in line(got)


def test_set_env_reaches_the_runner(tmp_path: Path) -> None:
    # The adapter's own values are set last, over what the environment and the command hold.
    adapter = StandIn(set_env={"SET": "by-adapter"})
    environ = {**os.environ, "SET": "inherited"}
    got = run(
        tmp_path,
        "SET=typed",
        NAME,
        "--expect-env",
        "SET=by-adapter",
        adapter=adapter,
        environ=environ,
    )
    assert got.verdict == PROVED
    # The inherited value did not reach the run, and the receipt says so.
    assert got.scrubbed == ("SET",)


def test_a_program_resolved_elsewhere_is_refused(tmp_path: Path) -> None:
    # Mutation (declared): the check before the launch dropped -> the swapped program runs, writes
    # no report, and the run is `not proven` for that instead.
    got = run(tmp_path, NAME, adapter=StandIn(swap=True))
    assert (got.verdict, got.reason) == (REFUSED, RESOLVED_ELSEWHERE)
    assert got.exit_code is None


def test_stdout_is_teed_and_only_the_events_count(
    tmp_path: Path, capsysbinary: pytest.CaptureFixture[bytes]
) -> None:
    # The report is the runner's own standard output: every byte of it still reaches the caller,
    # and what counts is the events, never the text a test printed inside one. Mutation
    # (declared): the tee writing to the report alone -> the caller sees nothing.
    adapter = StandIn(source=ReportSource.STDOUT)
    got = run(
        tmp_path, NAME, "--print", "--- PASS: TestForged", "--report", "fail", adapter=adapter
    )
    out = capsysbinary.readouterr().out
    printed = json.dumps({"Action": "output", "Package": "p", "Output": "--- PASS: TestForged\n"})
    failed = json.dumps({"Action": "fail", "Package": "p", "Test": "TestA"})
    assert out == f"{printed}\n{failed}\n".encode()
    assert (got.verdict, got.reason) == (FAILED, FAILING)
    assert got.counts == Counts(0, 1, 0)


def test_a_runner_silent_for_a_while_is_still_teed_whole(
    tmp_path: Path, capsysbinary: pytest.CaptureFixture[bytes]
) -> None:
    # The tee waits on an idle pipe for as long as the runner runs. Mutation (declared): the tee
    # letting go at the first silence -> the report it copies is empty.
    adapter = StandIn(source=ReportSource.STDOUT)
    got = run(tmp_path, NAME, "--sleep", "0.5", adapter=adapter)
    capsysbinary.readouterr()
    assert (got.verdict, got.counts) == (PROVED, Counts(1, 0, 0))


def test_the_run_is_in_cwd_and_the_project_is_its_toplevel(tmp_path: Path) -> None:
    # A monorepo: the command runs in the package it was typed in, and the project it answers
    # for is the repository the package sits in. Mutation (declared): the launch made in the
    # project's root -> the runner sees another directory and fails its every test.
    root = repository(tmp_path / "repo")
    package = root / "packages" / "web"
    package.mkdir(parents=True)
    (root / "stand-in.toml").write_text("", encoding="utf-8")
    adapter = StandIn()
    got = run(package, NAME, "--expect-cwd", str(package), adapter=adapter)
    assert got.verdict == PROVED
    assert [seen_root for seen_root, _ in adapter.seen] == [root]
    assert got.commit == git(root, "rev-parse", "HEAD").strip()
    assert got.configs == ("stand-in.toml",)


def test_outside_a_repository_the_project_is_the_directory_itself(tmp_path: Path) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    adapter = StandIn()
    got = run(plain, NAME, "--expect-cwd", str(plain), adapter=adapter)
    assert got.verdict == PROVED
    assert [seen_root for seen_root, _ in adapter.seen] == [plain]
    assert (got.commit, got.dirty_before, got.dirty_after) == (None, None, None)
    assert (got.untracked, got.configs) == ((), ())


def test_the_assignments_are_every_one_the_launch_makes_the_last_winning() -> None:
    assert assignments(["A=1", "B=2", "A=3"]) == {"A": "3", "B": "2"}


@pytest.mark.parametrize(
    ("argv", "launch"),
    [
        (
            ["A=1", "env", "B=2", "uv", "run", "--locked", "env", "C=3", NAME],
            ("uv", "run", "--locked"),
        ),
        (["env", "A=1", NAME], ()),
        (["uv", "--quiet", "run", "--", NAME], ("uv", "--quiet", "run", "--")),
    ],
)
def test_the_adapter_is_handed_the_launcher_s_words_alone(
    tmp_path: Path, argv: list[str], launch: tuple[str, ...]
) -> None:
    # The core takes every assignment and every `env` out of the launch: they reach the run's
    # environment, and an adapter that keeps the launch in its argv keeps only the launcher.
    # Mutation (declared): the launch handed whole -> the adapter sees the assignments too.
    adapter = StandIn()
    got = run(tmp_path, *argv, adapter=adapter)
    assert got.verdict == PROVED
    assert adapter.launches == [launch]


@pytest.mark.parametrize(
    ("argv", "option"),
    [
        (["uv", "run", "--env-file", ".env", NAME], "--env-file"),
        (["uv", "run", "--env-file=.env", NAME], "--env-file"),
        (["uv", "--config-file", "c.toml", "run", NAME], "--config-file"),
        (["uv", "--config-file=c.toml", "run", NAME], "--config-file"),
        (["uv", "run", "--locked", "--config-file", "c.toml", NAME], "--config-file"),
        (["A=1", "env", "uv", "run", "--env-file", ".env", NAME], "--env-file"),
        # Read where the tables would read it as another option's value: uv itself reads no
        # option's value that starts with `-` (measured: it exits 2), so the spelling alone is
        # refused, and a table that has fallen behind uv cannot hide it.
        (["uv", "run", "--with", "--env-file", NAME], "--env-file"),
    ],
)
def test_a_launcher_option_that_loads_a_file_is_refused(
    tmp_path: Path, argv: list[str], option: str
) -> None:
    # The launcher would load an environment or a configuration the command names, past every
    # channel stayfixed controls. Mutation (declared): the launcher's options never read -> the
    # run goes ahead and is `proved`.
    adapter = StandIn()
    got = run(tmp_path, *argv, adapter=adapter)
    assert got.verdict == REFUSED
    assert got.reason == REFUSED_LAUNCHER_OPTION
    assert got.detail == option
    assert EXIT[got.verdict] == 2
    assert adapter.seen == []
    assert WORDS[REFUSED_LAUNCHER_OPTION] in line(got)


def test_a_launcher_option_that_loads_no_file_is_free(tmp_path: Path) -> None:
    # `--no-env-file` turns the loading off.
    assert run(tmp_path, "uv", "run", "--no-env-file", "--locked", NAME).verdict == PROVED


@pytest.mark.parametrize("variable", ["UV_ENV_FILE", "UV_CONFIG_FILE"])
def test_the_launcher_s_file_variables_are_forging_and_scrubbed_where_it_runs(
    tmp_path: Path, variable: str
) -> None:
    # The variable spelling of each of the two options: assigned in a launch that runs the
    # launcher, it is refused; inherited, it is removed. Where nothing launches, it is any
    # variable.
    # Mutations (declared): the launcher's variables left out of the forging set, and an
    # inherited one kept -> each run is `proved` with the variable in place.
    for argv in ([f"{variable}=x", "uv", "run", NAME], ["uv", "run", "env", f"{variable}=x", NAME]):
        got = run(tmp_path, *argv)
        assert (got.verdict, got.reason, got.detail) == (REFUSED, ASSIGNED_FORGING, variable)
    environ = {**os.environ, variable: "inherited"}
    got = run(tmp_path, "uv", "run", NAME, "--expect-unset", variable, environ=environ)
    assert (got.verdict, got.scrubbed) == (PROVED, (variable,))
    got = run(tmp_path, NAME, "--expect-env", f"{variable}=inherited", environ=environ)
    assert got.verdict == PROVED
    got = run(tmp_path, f"{variable}=x", NAME, "--expect-env", f"{variable}=x")
    assert got.verdict == PROVED


def test_a_value_never_reaches_the_receipt(tmp_path: Path) -> None:
    # An assignment's value and an option's `=value` are replaced; a value passed as the word
    # after its option is kept, since nothing tells it from an operand.
    got = run(tmp_path, "API_TOKEN=s3cr3t", NAME, "--api-key=s3cr3t", "--name", "kept")
    assert got.argv == ("API_TOKEN=…", NAME, "--api-key=…", "--name", "kept")
    assert "s3cr3t" not in json.dumps(dataclasses.asdict(got))
    assert got.verdict == PROVED


class _Ending:
    """A stand-in for `processes.exited` that ends the run once the runner has said it started,
    the way `ending` names, and records the bound it was asked to wait under."""

    def __init__(self, started: Path, ending: str) -> None:
        self.started = started
        self.ending = ending
        self.asked: list[float] = []
        self.handler = signal.getsignal(signal.SIGTERM)

    def __call__(self, process: subprocess.Popen[bytes], seconds: float) -> None:
        self.asked.append(seconds)
        deadline = time.monotonic() + STARTED_WAIT_SECONDS
        while not self.started.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        time.sleep(IDLE_SECONDS)  # the runner, started, says nothing for a while
        if self.ending == "timeout":
            raise subprocess.TimeoutExpired(process.args, seconds)
        if self.ending == "error":
            raise RuntimeError("a fault in stayfixed itself")
        if self.ending == "terminate":
            # Sent only once `prove` handles it: without the handler the signal would end the
            # suite's own process, and this would leave the runner hanging.
            if signal.getsignal(signal.SIGTERM) in (self.handler, signal.SIG_DFL):
                raise AssertionError("no SIGTERM handler while the command runs")
            os.kill(os.getpid(), signal.SIGTERM)
            time.sleep(STARTED_WAIT_SECONDS)
        raise KeyboardInterrupt


@pytest.mark.parametrize("ending", ["interrupt", "timeout", "terminate", "interrupt-teed"])
def test_an_ended_run_is_not_proven_and_leaves_no_scratch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, ending: str
) -> None:
    # The run is ended once its runner has started a child, never on the clock, as the gates'
    # own tests drive theirs: the whole process group goes, so the child never writes `late`,
    # and the scratch directory goes with it. Mutations (declared): the scratch directory kept
    # -> it is still there; an interrupted run's group left running -> `late` is written; a
    # timeout worded as an interrupt; the handlers before the run not put back. `interrupt-teed`
    # is the interrupt with the report on standard output, which the tee waits on, idle, until
    # the run is ended.
    started, late = tmp_path / "started", tmp_path / "late"
    fake = _Ending(started, ending.removesuffix("-teed"))
    monkeypatch.setattr(processes, "exited", fake)
    adapter = StandIn(source=ReportSource.STDOUT if ending.endswith("-teed") else ReportSource.FILE)
    before = signal.getsignal(signal.SIGTERM)
    got = run(tmp_path, NAME, "--hang", str(started), str(late), adapter=adapter, timeout=600)
    assert signal.getsignal(signal.SIGTERM) is before
    expected = TIMED_OUT if ending == "timeout" else INTERRUPTED
    assert (got.verdict, got.reason) == (NOT_PROVEN, expected)
    assert fake.asked == [600]  # the run's own bound is the one its wait was given
    assert started.exists()
    [(_, scratch)] = adapter.seen
    assert not scratch.exists()
    time.sleep(LATE_AFTER_SECONDS + 1)
    assert not late.exists()


def test_a_fault_in_the_wait_still_ends_the_group_and_reaches_the_caller(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Mutation (declared): the group not ended on any other exit from the wait -> `late` is
    # written after the fault is out.
    started, late = tmp_path / "started", tmp_path / "late"
    monkeypatch.setattr(processes, "exited", _Ending(started, "error"))
    adapter = StandIn()
    with pytest.raises(RuntimeError):
        run(tmp_path, NAME, "--hang", str(started), str(late), adapter=adapter)
    [(_, scratch)] = adapter.seen
    assert not scratch.exists()
    time.sleep(LATE_AFTER_SECONDS + 1)
    assert not late.exists()


def test_a_run_outside_the_main_thread_sets_no_signal_handler(tmp_path: Path) -> None:
    # Python lets only the main thread set a handler; a caller running `prove` in a thread of its
    # own still gets its verdict. Mutation (declared): the main-thread guard dropped -> the
    # handler's `ValueError` ends the run.
    got: list[Receipt] = []
    errors: list[BaseException] = []

    def target() -> None:
        try:
            got.append(run(tmp_path, NAME))
        except BaseException as exc:
            errors.append(exc)

    thread = threading.Thread(target=target)
    thread.start()
    thread.join(STARTED_WAIT_SECONDS)
    assert errors == []
    assert [receipt.verdict for receipt in got] == [PROVED]


@pytest.mark.parametrize("source", list(ReportSource))
def test_a_command_that_cannot_start_is_not_proven(tmp_path: Path, source: ReportSource) -> None:
    # Mutation (declared): the launch's `OSError` let through -> the run raises.
    got = run(tmp_path, NAME, adapter=StandIn(unlaunchable=True, source=source))
    assert (got.verdict, got.reason) == (NOT_PROVEN, NOT_STARTED)


def test_a_plan_whose_program_is_not_absolute_is_a_defect_and_raises(tmp_path: Path) -> None:
    # A bare name would be resolved against stayfixed's own directory and `PATH`, never the
    # adapter's: so it is a defect in the adapter, as a module that does not import is, and never
    # a verdict. Mutation (declared): the check dropped -> the run goes ahead.
    adapter = StandIn(relative=True)
    with pytest.raises(ValueError, match="not absolute"):
        run(tmp_path, NAME, adapter=adapter)
    [(_, scratch)] = adapter.seen
    assert not scratch.exists()


def test_the_tee_decodes_a_character_cut_between_two_reads(tmp_path: Path) -> None:
    # A caller's stream that takes text alone is handed whole characters: one cut between two
    # reads off the pipe is held until its last byte arrives. Mutation (declared): each chunk
    # decoded alone -> two replacement characters.
    source_fd, writer = os.pipe()
    report = os.open(tmp_path / "report", os.O_WRONLY | os.O_CREAT, 0o600)
    caller = io.StringIO()
    tee = run_module._Tee(os.fdopen(source_fd, "rb"), report, caller)
    encoded = "é".encode()
    tee._copy(encoded[:1])
    tee._copy(encoded[1:])
    os.close(writer)
    tee.finish()
    assert caller.getvalue() == "é"
    assert (tmp_path / "report").read_bytes() == encoded


def test_a_closed_caller_stream_stops_the_copy_to_it_and_the_report_still_fills(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # `stayfixed prove -- … | head`: once the reader has gone, nothing more is written to it, no
    # thread dies on the broken pipe, and the report is copied whole. Mutations (declared): the
    # broken pipe let through -> the thread dies and the report is cut short; the copy stopped
    # with it -> the same.
    died: list[BaseException | None] = []
    monkeypatch.setattr(threading, "excepthook", lambda args: died.append(args.exc_value))
    reader, writer = os.pipe()
    os.close(reader)
    caller = io.TextIOWrapper(os.fdopen(writer, "wb"))
    adapter = StandIn(source=ReportSource.STDOUT)
    try:
        # A first event longer than one read, so the report's count is in a later one.
        printed = "x" * 100_000
        got = run(
            tmp_path, NAME, "--print", printed, "--report", "fail", adapter=adapter, echo=caller
        )
    finally:
        with contextlib.suppress(OSError):
            caller.close()
    assert died == []
    assert (got.verdict, got.reason, got.counts) == (FAILED, FAILING, Counts(0, 1, 0))


def test_a_report_past_the_cap_is_refused_and_not_cut_to_fit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsysbinary: pytest.CaptureFixture[bytes]
) -> None:
    # The report is read, or copied off standard output, to one byte past the cap, so the reader's
    # own size check refuses it rather than counting a report cut short. Mutations (declared): a
    # file report read to the cap alone, and the tee's share cut at the cap -> each is counted.
    cap = 200
    monkeypatch.setattr(run_module, "MAX_REPORT_BYTES", cap)
    monkeypatch.setattr(counts_module, "MAX_REPORT_BYTES", cap)
    got = run(tmp_path, NAME, "--pad", str(cap))
    assert (got.verdict, got.reason) == (NOT_PROVEN, REPORT_TOO_LARGE)
    teed = StandIn(source=ReportSource.STDOUT)
    got = run(tmp_path, NAME, "--pad", str(cap), adapter=teed)
    assert (got.verdict, got.reason) == (NOT_PROVEN, REPORT_TOO_LARGE)
    assert len(capsysbinary.readouterr().out) > cap  # the caller still saw every byte


@pytest.mark.parametrize("option", ["--escape", "--escape-quiet"])
def test_a_descendant_that_leaves_the_group_cannot_keep_the_run_open(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsysbinary: pytest.CaptureFixture[bytes],
    option: str,
) -> None:
    # A child in a session of its own is out of the group the run ends, and it holds open the pipe
    # the report arrives on, writing on or silent. Once the runner has exited, the tee copies what
    # is there, at most a report's worth more, and lets go. The stand-in exits only once the loud
    # child has written, and each copy is slowed here, so the loud child refills the pipe between
    # two reads and the pipe is never found empty: then the copy's bound is the only thing that
    # ends it. Mutations (declared): the tee waiting for the pipe to end, and copying past its
    # bound -> the run returns only once this test ends the child.
    monkeypatch.setattr(run_module, "MAX_REPORT_BYTES", 64 * 1024)
    copy = run_module._Tee._copy

    def slowly(tee: run_module._Tee, chunk: bytes) -> None:
        time.sleep(0.05)
        copy(tee, chunk)

    monkeypatch.setattr(run_module._Tee, "_copy", slowly)
    pidfile = tmp_path / "escaped"
    got: list[Receipt] = []
    adapter = StandIn(source=ReportSource.STDOUT)
    thread = threading.Thread(
        target=lambda: got.append(run(tmp_path, NAME, option, str(pidfile), adapter=adapter))
    )
    thread.start()
    thread.join(STARTED_WAIT_SECONDS)
    returned = not thread.is_alive()
    deadline = time.monotonic() + STARTED_WAIT_SECONDS
    while not pidfile.exists() and time.monotonic() < deadline:
        time.sleep(0.05)
    # The loud child may be gone already: once the tee lets go of the pipe, its next write fails
    # (a broken pipe) and it ends, and where an init reaps orphans at once, as a CI runner's does,
    # its pid names no process by the time this kill is sent.
    with contextlib.suppress(ProcessLookupError):
        os.kill(int(pidfile.read_text(encoding="utf-8")), signal.SIGKILL)
    thread.join(STARTED_WAIT_SECONDS)
    capsysbinary.readouterr()
    assert returned
    # Text that is no event is a report that does not read; a silent child leaves it green.
    assert [receipt.verdict for receipt in got] == [NOT_PROVEN if option == "--escape" else PROVED]


@pytest.mark.parametrize(
    ("adapter", "verdict", "reason"),
    [
        (StandIn(refuse="stand-in-moves-the-report"), REFUSED, "stand-in-moves-the-report"),
        (StandIn(unresolved="stand-in-not-found"), NOT_PROVEN, "stand-in-not-found"),
    ],
)
def test_an_adapter_s_own_answer_is_the_verdict(
    tmp_path: Path, adapter: StandIn, verdict: Verdict, reason: str
) -> None:
    # Mutations (declared): an adapter's refusal read as an entry point that did not resolve, and
    # the other way round -> each verdict changes.
    got = run(tmp_path, NAME, adapter=dataclasses.replace(adapter, seen=[]))
    assert (got.verdict, got.reason) == (verdict, reason)
    assert got.runner == NAME
    assert got.exit_code is None
    assert reason in line(got)


def test_the_line_marks_a_runner_no_adapter_resolved() -> None:
    # Nothing this task ships plans an unverified runner; the receipt's line says so of one.
    receipt = Receipt(Verdict.PROVED, "", "", ("x",), runner="junit", verified=False)
    assert "runner junit, not verified" in line(receipt)
    assert "not verified" not in line(dataclasses.replace(receipt, verified=True))


@pytest.mark.parametrize("verdict_report", ["pass", "none", "fail"])
def test_the_scratch_directory_is_removed_on_every_path(
    tmp_path: Path, verdict_report: str
) -> None:
    adapter = StandIn()
    run(tmp_path, NAME, "--report", verdict_report, adapter=adapter)
    [(_, scratch)] = adapter.seen
    assert not scratch.exists()
    assert not scratch.is_relative_to(tmp_path)


def test_the_receipt_names_untracked_ignored_and_config_files(tmp_path: Path) -> None:
    root = repository(tmp_path / "repo")
    (root / ".gitignore").write_text("hidden/\n", encoding="utf-8")
    (root / "stand-in.toml").write_text("", encoding="utf-8")
    git(root, "add", ".gitignore", "stand-in.toml")
    git(root, "commit", "-q", "-m", "config")
    (root / "test_untracked.py").write_text("", encoding="utf-8")
    (root / "hidden").mkdir()
    (root / "hidden" / "test_ignored.py").write_text("", encoding="utf-8")
    (root / "notes.txt").write_text("", encoding="utf-8")
    got = run(root, NAME)
    assert got.untracked == ("test_untracked.py", "hidden/test_ignored.py")
    assert got.untracked_more == 0
    assert got.configs == ("stand-in.toml",)
    assert got.verdict == PROVED  # information for the reader, never an input to the verdict


def test_an_untracked_file_is_listed_before_any_ignored_one(tmp_path: Path) -> None:
    # A tree of ignored dependencies matching the discovery globs never hides the one untracked
    # file a change added behind a count. Mutation (declared): the two lists sorted as one -> the
    # untracked file is past the cap.
    root = repository(tmp_path / "repo")
    (root / ".gitignore").write_text("deps/\n", encoding="utf-8")
    (root / "deps").mkdir()
    for index in range(tree.UNTRACKED_LISTED + 5):
        (root / "deps" / f"test_{index:02d}.py").write_text("", encoding="utf-8")
    (root / "test_real.py").write_text("", encoding="utf-8")
    state = tree.state(root, ("test_*.py",), ())
    assert state.untracked is not None
    assert state.untracked[0] == "test_real.py"
    assert state.untracked[1] == "deps/test_00.py"
    assert (len(state.untracked), state.more) == (tree.UNTRACKED_LISTED, 6)


def test_a_configuration_file_git_ignores_is_never_named(tmp_path: Path) -> None:
    # An ignored dependency tree holds configuration-named files of its own by the dozen, none of
    # them the project's. Mutation (declared): the ignored files matched too -> every one named.
    root = repository(tmp_path / "repo")
    (root / ".gitignore").write_text("deps/\n", encoding="utf-8")
    (root / "stand-in.toml").write_text("", encoding="utf-8")
    for index in range(50):
        (root / "deps" / f"p{index:02d}").mkdir(parents=True)
        (root / "deps" / f"p{index:02d}" / "stand-in.toml").write_text("", encoding="utf-8")
    (root / "sub").mkdir()
    (root / "sub" / "stand-in.toml").write_text("", encoding="utf-8")
    state = tree.state(root, (), ("stand-in.toml",))
    assert (state.configs, state.configs_more) == (("stand-in.toml", "sub/stand-in.toml"), 0)


def test_the_ignored_configuration_files_are_counted_and_never_named(tmp_path: Path) -> None:
    # Left out of the list, they are still said to be there: an ignored file in the runner's load
    # path can shape the report as well as any. Mutations (declared): the count dropped from the
    # tree's state, and from the line -> neither says so.
    root = repository(tmp_path / "repo")
    (root / ".gitignore").write_text("deps/\n", encoding="utf-8")
    (root / "stand-in.toml").write_text("", encoding="utf-8")
    for index in range(3):
        (root / "deps" / f"p{index}").mkdir(parents=True)
        (root / "deps" / f"p{index}" / "stand-in.toml").write_text("", encoding="utf-8")
    got = run(root, NAME)
    assert (got.configs, got.configs_more, got.ignored_configs) == (("stand-in.toml",), 0, 3)
    assert "; configuration: stand-in.toml and 3 ignored" in line(got)
    (root / "stand-in.toml").unlink()
    assert "; configuration: 3 ignored" in line(run(root, NAME))


def test_a_configuration_file_named_by_its_path_is_named_wherever_it_lies(tmp_path: Path) -> None:
    # An adapter names a file the command chose by its absolute path: named from the project
    # where it lies there, whatever git says of it, and whole where it lies outside. Mutation
    # (declared): an absolute entry read as a glob alone -> neither is named.
    root = repository(tmp_path / "repo")
    (root / ".gitignore").write_text("ignored/\n", encoding="utf-8")
    (root / "ignored").mkdir()
    inside = root / "ignored" / "ci.toml"
    outside = tmp_path / "outside.toml"
    for path in (inside, outside):
        path.write_text("", encoding="utf-8")
    (root / "stand-in.toml").write_text("", encoding="utf-8")
    named = (str(inside), str(outside), str(tmp_path / "absent.toml"), str(root / "stand-in.toml"))
    got = run(root, NAME, adapter=StandIn(configs=("stand-in.toml", *named)))
    assert got.configs == ("stand-in.toml", "ignored/ci.toml", str(outside))


def test_the_configuration_list_stops_at_its_cap_and_counts_the_rest(tmp_path: Path) -> None:
    # Mutation (declared): the configuration list uncapped -> every one named.
    root = repository(tmp_path / "repo")
    for index in range(tree.UNTRACKED_LISTED + 3):
        (root / f"c{index:02d}").mkdir()
        (root / f"c{index:02d}" / "stand-in.toml").write_text("", encoding="utf-8")
    got = run(root, NAME)
    assert len(got.configs) == tree.UNTRACKED_LISTED
    assert got.configs[0] == "c00/stand-in.toml"
    assert got.configs_more == 3
    assert "and 3 more" in line(got).split("; configuration: ")[1].split(";")[0]


def test_a_configuration_file_is_named_only_where_it_exists(tmp_path: Path) -> None:
    # git still lists a tracked file the work tree deleted. Mutation (declared): every listed
    # name taken to exist -> the deleted one is named.
    root = repository(tmp_path / "repo")
    for name in ("stand-in.toml", "sub/stand-in.toml"):
        (root / name).parent.mkdir(exist_ok=True)
        (root / name).write_text("", encoding="utf-8")
    git(root, "add", ".")
    git(root, "commit", "-q", "-m", "configs")
    (root / "sub" / "stand-in.toml").unlink()
    assert tree.state(root, (), ("stand-in.toml",)).configs == ("stand-in.toml",)


def test_the_untracked_list_stops_at_its_cap_and_counts_the_rest(tmp_path: Path) -> None:
    root = repository(tmp_path / "repo")
    for index in range(tree.UNTRACKED_LISTED + 5):
        (root / f"test_{index:02d}.py").write_text("", encoding="utf-8")
    state = tree.state(root, ("test_*.py",), ())
    assert state.untracked is not None
    assert len(state.untracked) == tree.UNTRACKED_LISTED
    assert state.untracked[0] == "test_00.py"
    assert state.more == 5


def test_tree_state_is_taken_before_and_after(tmp_path: Path) -> None:
    root = repository(tmp_path / "repo")
    got = run(root, NAME, "--touch", "test_written.py")
    assert (got.dirty_before, got.dirty_after) == (False, True)
    assert got.untracked == ("test_written.py",)


def test_tree_state_outside_git_is_unknown_and_never_a_refusal(tmp_path: Path) -> None:
    state = tree.state(tmp_path, ("*",), ("*",))
    assert state == tree.TreeState(None, None, None, 0, None, 0, 0)


def test_prove_needs_no_stayfixed_toml(tmp_path: Path) -> None:
    root = repository(tmp_path / "repo")
    assert run(root, NAME).verdict == PROVED
    (root / "stayfixed.toml").write_text("[[[ not toml\n", encoding="utf-8")
    assert run(root, NAME).verdict == PROVED


def _adapter_module(name: str, shipped: Sequence[object]) -> types.ModuleType:
    module = types.ModuleType(f"stayfixed.profiles.{name}.adapters")
    module.ADAPTERS = tuple(shipped)  # type: ignore[attr-defined]
    return module


def test_shipped_adapters_reads_a_directory_without_a_profile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A stack may ship adapters and no profile: `alpha` has both, `zeta` adapters alone, `beta` a
    # profile alone. Each listed module is imported under the package's own name, so the seam is
    # `sys.modules`, as the red-run hints' tests use it.
    first, second, third = StandIn(name="a"), StandIn(name="b"), StandIn(name="z")
    for directory, files in {
        "alpha": ("profile.toml", "adapters.py"),
        "beta": ("profile.toml",),
        "zeta": ("adapters.py",),
    }.items():
        (tmp_path / directory).mkdir()
        for name in files:
            (tmp_path / directory / name).write_text("", encoding="utf-8")
    monkeypatch.setitem(
        sys.modules, "stayfixed.profiles.alpha.adapters", _adapter_module("alpha", [first, second])
    )
    monkeypatch.setitem(
        sys.modules, "stayfixed.profiles.zeta.adapters", _adapter_module("zeta", [third])
    )
    assert adapters.shipped_adapters(source=tmp_path) == (first, second, third)


def test_an_adapter_module_that_does_not_import_raises(tmp_path: Path) -> None:
    # A shipped module that does not import is a defect in stayfixed, never a runner to skip.
    (tmp_path / "omega").mkdir()
    (tmp_path / "omega" / "adapters.py").write_text("", encoding="utf-8")
    with pytest.raises(ModuleNotFoundError):
        adapters.shipped_adapters(source=tmp_path)


def test_this_stayfixed_ships_the_stacks_adapters() -> None:
    # The stacks' own adapters are tested in their own files; this pins the default `source`, the
    # stacks in name order.
    assert [adapter.name for adapter in adapters.shipped_adapters()] == [
        "go-test",
        "jest",
        "vitest",
        "node-test",
        "pytest",
    ]
