"""`prove` runs a test command where it is typed and answers from the runner's own report alone.

Every case runs `tests/prove/stand_in.py`'s adapter and runner, so none needs a real test runner:
the adapter plans, the run launches what it planned in the directory the command was typed in,
and the verdict comes from the report the runner wrote and the code it exited with, in the order
`stayfixed.prove.run.CASCADE` gives, the first row that holds winning.
"""

from __future__ import annotations

import contextlib
import dataclasses
import fcntl
import hashlib
import io
import json
import os
import signal
import subprocess
import sys
import tempfile
import threading
import time
import types
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any, TextIO

import pytest

from stayfixed import processes
from stayfixed.profiles import adapters
from stayfixed.profiles.python.adapters import PytestAdapter
from stayfixed.profiles.runners import ReportSource
from stayfixed.prove import counts as counts_module
from stayfixed.prove import run as run_module
from stayfixed.prove import tree
from stayfixed.prove.counts import REPORT_DOCTYPE, REPORT_TOO_LARGE, Counts
from stayfixed.prove.events import read_line
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
    TIMED_OUT,
    WORDS,
    Receipt,
    Verdict,
    assignments,
    environment,
    line,
    prove,
)
from tests.gitfixture import git
from tests.prove.stand_in import (
    JUNIT,
    LATE_AFTER_SECONDS,
    NAME,
    PROGRAM,
    StandIn,
    forges,
    held,
)

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
    junit: Path | None = None,
) -> Receipt:
    return prove(
        argv,
        cwd=cwd,
        environ=dict(os.environ) if environ is None else environ,
        timeout=timeout,
        adapters=[adapter or StandIn()],
        echo=echo,
        junit=junit,
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
    # Mutations (declared): the digest taken of nothing -> it differs; the program named as
    # planned -> the virtual environment's `python` link, not the interpreter it reaches.
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
        # Wherever the command spells the assignment: before the launcher, bare or after `env`,
        # or after an `env` the launcher runs.
        ["uv", "run", "env", "FORGE=x", NAME],
        ["env", "A=1", "uv", "run", "env", "FORGE=x", NAME],
        ["FORGE=x", "uv", "run", NAME],
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


def test_an_assigned_value_that_forges_nothing_reaches_the_runner(tmp_path: Path) -> None:
    # The adapter's test of the value decides, not the name alone (`PYTHONOPTIMIZE=0` optimises
    # nothing). Mutation (declared): the value's test left unasked -> the stand-in's `FORGE=keep`
    # is refused.
    got = run(tmp_path, "FORGE=keep", NAME, "--expect-env", "FORGE=keep")
    assert (got.verdict, got.reason) == (PROVED, "")


# A command no adapter recognises that writes a green JUnit report at `out.xml`, for `--junit`.
GREEN_JUNIT_WRITER = [
    sys.executable,
    str(PROGRAM),
    "--report-path",
    "out.xml",
    "--source",
    "file",
    "--report",
    "pass",
]


@pytest.mark.parametrize(
    ("argv", "junit"),
    [
        pytest.param(["uv", "run", "TYPED=yes", "pytest"], None, id="argv0"),
        pytest.param(["uv", "run", "--", "TYPED=yes", "pytest"], None, id="argv1"),
        pytest.param(["env", "A=1", "uv", "run", "TYPED=yes", "B=2", "pytest"], None, id="argv2"),
        pytest.param(
            ["uv", "run", "env", "A=1", "uv", "run", "TYPED=yes", "pytest"], None, id="argv3"
        ),
        pytest.param(["uv", "run", "TYPED=yes", *GREEN_JUNIT_WRITER], "out.xml", id="junit"),
    ],
)
def test_an_assignment_right_after_a_launcher_is_handed_to_it_and_runs_no_test(
    tmp_path: Path, argv: list[str], junit: str | None
) -> None:
    # Typed as it is, uv runs `TYPED=yes` as its program (uv 0.12.19: "Failed to spawn", exit 2),
    # and no test runs; read as an assignment, the run would be `proved` for a command that runs
    # nothing, with an adapter or under `--junit`, whose writer would leave a green report.
    environ = with_uv(fake_uv(tmp_path / "bin"))
    report = None if junit is None else Path(junit)
    got = prove(argv, cwd=tmp_path, environ=environ, timeout=600, junit=report)
    assert got.verdict == NOT_PROVEN
    assert "yes" not in line(got)


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


def test_an_inherited_forging_variable_is_removed_and_counted(tmp_path: Path) -> None:
    adapter = StandIn(forging={"SCRUBBED": forges})
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


def test_a_forging_variable_the_run_did_not_inherit_is_not_named(tmp_path: Path) -> None:
    adapter = StandIn(forging={"SCRUBBED": forges})
    environ = {name: value for name, value in os.environ.items() if name != "SCRUBBED"}
    got = run(tmp_path, NAME, adapter=adapter, environ=environ)
    assert (got.verdict, got.scrubbed) == (PROVED, ())
    assert "removed from the run's environment" not in line(got)


def test_the_run_s_environment_is_the_caller_s_less_forging_then_the_assignments() -> None:
    # As a shell builds it: an assignment wins over the inherited value, and the names lost are
    # the inherited ones alone. Mutation (declared): the assignments put under the inherited
    # values -> `KEPT` is `1`.
    # An inherited value its test says forges nothing is kept. Mutation (declared): the value's
    # test left unasked when scrubbing -> `SAFE=keep` is removed.
    env, scrubbed = environment(
        {"KEPT": "1", "FORGE": "x", "OTHER": "o", "SAFE": "keep"},
        {"FORGE": forges, "ABSENT": forges, "SAFE": forges},
        {"KEPT": "2"},
    )
    assert env == {"KEPT": "2", "OTHER": "o", "SAFE": "keep"}
    assert scrubbed == ("FORGE",)


def test_the_plan_is_made_in_the_run_s_own_environment(tmp_path: Path) -> None:
    # An adapter finds its program on the `PATH` the command runs under, the command's own
    # assignment of `PATH` included, as a shell would, and never sees a variable the run does not
    # get. Mutations (declared): the plan handed stayfixed's own environment -> it sees another
    # `PATH`; the forging set kept in it -> it sees `SCRUBBED`.
    adapter = StandIn(forging={"SCRUBBED": forges})
    environ = {**os.environ, "PATH": "/inherited", "SCRUBBED": "1"}
    got = run(
        tmp_path,
        "PATH=/typed",
        NAME,
        "--expect-env",
        "PATH=/typed",
        adapter=adapter,
        environ=environ,
    )
    assert got.verdict == PROVED
    [seen] = adapter.environs
    assert seen["PATH"] == "/typed"
    assert "SCRUBBED" not in seen


def test_an_assignment_wins_over_the_inherited_value(tmp_path: Path) -> None:
    environ = {**os.environ, "TYPED": "inherited"}
    got = run(tmp_path, "TYPED=typed", NAME, "--expect-env", "TYPED=typed", environ=environ)
    assert got.verdict == PROVED


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
    (package / "test_new.py").write_text("", encoding="utf-8")
    adapter = StandIn()
    got = run(package, NAME, "--expect-cwd", str(package), adapter=adapter)
    assert got.verdict == PROVED
    assert got.commit == git(root, "rev-parse", "HEAD").strip()
    # Named from the repository's top-level: the project is the repository, not the package.
    assert got.untracked == ("packages/web/test_new.py",)


def test_outside_a_repository_the_project_is_the_directory_itself(tmp_path: Path) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    adapter = StandIn()
    got = run(plain, NAME, "--expect-cwd", str(plain), adapter=adapter)
    assert got.verdict == PROVED
    assert (got.commit, got.dirty_before, got.dirty_after) == (None, None, None)
    assert got.untracked == ()


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
    "words",
    [
        ["--with", "x"],
        ["--python", "3.13"],
        ["--isolated"],
        ["--no-project"],
        ["--env-file", ".env"],
        ["--no-env-file", "--locked"],
        ["--project", "../other"],
    ],
    ids=lambda words: "_".join(words),
)
def test_a_launcher_s_options_are_kept_as_typed(tmp_path: Path, words: list[str]) -> None:
    # The launcher runs the command as it was typed, whatever its options load or where they
    # point: what the command selects is what runs, and the receipt names the directory it was
    # typed in.
    adapter = StandIn()
    assert run(tmp_path, "uv", "run", *words, NAME, adapter=adapter).verdict == PROVED
    assert adapter.launches == [("uv", "run", *words)]


def test_a_launcher_s_variable_is_any_variable(tmp_path: Path) -> None:
    # Assigned or inherited, `UV_ENV_FILE` reaches the run as any variable does.
    got = run(tmp_path, "UV_ENV_FILE=x", "uv", "run", NAME, "--expect-env", "UV_ENV_FILE=x")
    assert (got.verdict, got.scrubbed) == (PROVED, ())
    environ = {**os.environ, "UV_ENV_FILE": "inherited"}
    got = run(tmp_path, "uv", "run", NAME, "--expect-env", "UV_ENV_FILE=inherited", environ=environ)
    assert (got.verdict, got.scrubbed) == (PROVED, ())


# A stand-in for `uv run`, for the cases that run what the launcher launches: `run` and its
# options read past, the directory `--directory` (spaced or with `=`) or else `UV_WORKING_DIR`
# names changed to, exit 2 where it names none, as uv does, then the program run.
FAKE_UV = """#!/bin/sh
[ "$1" = run ] && shift
to="${UV_WORKING_DIR:-}"
while [ $# -gt 0 ]; do
  case "$1" in
    --directory) to="$2"; shift 2 ;;
    --directory=*) to="${1#--directory=}"; shift ;;
    --) shift; break ;;
    -*) shift ;;
    *) break ;;
  esac
done
if [ -n "$to" ]; then cd "$to" || exit 2; fi
exec "$@"
"""


def program(path: Path, text: str) -> Path:
    """An executable script at `path` holding `text`."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    path.chmod(0o755)
    return path


def fake_uv(where: Path) -> Path:
    """`FAKE_UV` as the `uv` in `where`."""
    return program(where / "uv", FAKE_UV)


def with_uv(uv: Path) -> dict[str, str]:
    """The suite's environment, `uv`'s directory first on its `PATH`."""
    return {**os.environ, "PATH": os.pathsep.join([str(uv.parent), os.environ.get("PATH", "")])}


@pytest.mark.parametrize(
    ("words", "assigned", "inherited"),
    [
        (["uv", "run", "--directory", "../other"], [], {}),
        (["uv", "run", "--directory=../other"], [], {}),
        (["uv", "--directory", "../other", "run", "--locked"], [], {}),
        (["uv", "run"], ["UV_WORKING_DIR=../other"], {}),
        (["uv", "run"], [], {"UV_WORKING_DIR": "../other"}),
        (["uv", "run", "--directory", "../other"], [], {"UV_WORKING_DIR": "nowhere"}),
        (["uv", "run", "--directory", "..", "uv", "run", "--directory", "other"], [], {}),
    ],
    ids=["spaced", "equals", "global", "assigned", "inherited", "over-the-variable", "nested"],
)
def test_the_command_is_judged_where_its_launcher_runs_it(
    tmp_path: Path, words: list[str], assigned: list[str], inherited: dict[str, str]
) -> None:
    # `uv run --directory` and `UV_WORKING_DIR` move where the program runs (measured on uv
    # 0.12.19, the option winning, a nested `uv run` reading its own from where the outer moved):
    # the adapter plans from there, the project is that directory's top-level, and the receipt
    # names it. The launch is still made where the command was typed, uv moving itself, and the
    # launcher is handed by the path it was found at from there. Mutations (declared): the
    # adapter handed the typed directory, the project read from it, the receipt naming it, uv's
    # `--directory` or its variable not read, the launch made in the moved directory, the
    # launcher handed as typed -> each case differs.
    typed = repository(tmp_path / "typed")
    other = repository(tmp_path / "other")
    (other / "test_there.py").write_text("", encoding="utf-8")
    uv = fake_uv(tmp_path / "bin")
    adapter = StandIn()
    environ = {**with_uv(uv), **inherited}
    argv = [*assigned, *words, NAME, "--expect-cwd", str(typed)]
    got = run(typed, *argv, adapter=adapter, environ=environ)
    real = Path(os.path.realpath(other))
    assert got.verdict == PROVED, got
    assert adapter.cwds == [real]
    assert got.directory == str(real)
    assert got.commit == git(other, "rev-parse", "HEAD").strip()
    assert got.untracked == ("test_there.py",)
    assert adapter.launches == [(str(uv), *words[1:])]


@pytest.mark.parametrize(
    ("words", "assigned", "on_path"),
    [
        (["uv", "run"], [], True),
        (["uv", "run", "--project", "../other"], ["UV_PROJECT=../other"], True),
        (["uv", "run", "--directory", "."], [], True),
        # uv runs nothing where the directory is not there, or is no directory (exit 2, measured).
        (["uv", "run", "--directory", "nowhere"], [], True),
        (["uv", "run", "--directory", "file"], [], True),
        (["uv", "run"], ["UV_WORKING_DIR="], True),
        # A launcher that is not there runs nothing wherever it would move.
        (["uv", "run", "--directory", "../other"], [], False),
    ],
    ids=["none", "project", "dot", "nowhere", "a-file", "empty-variable", "no-launcher"],
)
def test_a_launcher_that_moves_nowhere_leaves_the_command_where_it_was_typed(
    tmp_path: Path, words: list[str], assigned: list[str], on_path: bool
) -> None:
    # `--project` and `UV_PROJECT` move no directory (measured on uv 0.12.19); a directory that
    # names none, or a launcher that is not there, leaves the command judged where it was typed,
    # and its launcher handed as typed. Mutation (declared): a directory that names none taken
    # as the one the command runs in -> the adapter plans from it.
    typed = tmp_path / "typed"
    typed.mkdir()
    (typed / "file").write_text("", encoding="utf-8")
    (tmp_path / "other").mkdir()
    uv = fake_uv(tmp_path / "bin")
    environ = with_uv(uv) if on_path else {**os.environ, "PATH": str(tmp_path / "empty")}
    adapter = StandIn()
    got = run(typed, *assigned, *words, NAME, adapter=adapter, environ=environ)
    assert got.verdict == PROVED, got
    assert adapter.cwds == [typed]
    assert got.directory == str(typed)
    assert adapter.launches == [tuple(words)]


def test_a_pytest_plan_behind_uv_s_directory_is_made_there(tmp_path: Path) -> None:
    # The real pytest adapter, a stand-in uv that changes to the directory and a stand-in pytest
    # that writes a green report: the plan is made from `sub`, so the file `-c` names is read
    # there, and the receipt names `sub`. Mutation (declared): the adapter handed the typed
    # directory -> `ci.ini` is read from it.
    project = repository(tmp_path / "project")
    sub = project / "sub"
    sub.mkdir()
    (sub / "ci.ini").write_text("[pytest]\n", encoding="utf-8")
    uv = fake_uv(tmp_path / "bin")
    green = '<testsuite><testcase name="a"/></testsuite>'
    pytest_script = (
        "#!/bin/sh\n"
        'for word in "$@"; do case "$word" in\n'
        f"  --junitxml=*) printf '%s' '{green}' > \"${{word#--junitxml=}}\" ;;\n"
        "esac; done\n"
    )
    program(tmp_path / "bin" / "pytest", pytest_script)

    class Recording:
        def __init__(self, inner: PytestAdapter) -> None:
            self.inner, self.name, self.forging = inner, inner.name, inner.forging
            self.cwds: list[Path] = []

        def recognises(self, command: Sequence[str]) -> bool:
            return self.inner.recognises(command)

        def plan(self, launch: Sequence[str], command: Sequence[str], **kwargs: Any) -> object:
            self.cwds.append(kwargs["cwd"])
            return self.inner.plan(launch, command, **kwargs)

    adapter = Recording(PytestAdapter())
    got = prove(
        ["uv", "run", "--directory", "sub", "pytest", "-c", "ci.ini"],
        cwd=project,
        environ=with_uv(uv),
        timeout=60,
        adapters=[adapter],  # type: ignore[list-item]
    )
    real = Path(os.path.realpath(sub))
    assert (got.verdict, got.counts) == (PROVED, Counts(1, 0, 0)), got
    assert adapter.cwds == [real]
    assert got.directory == str(real)


def test_a_value_never_reaches_the_receipt(tmp_path: Path) -> None:
    # An assignment's value and an option's `=value` are replaced; a value passed as the word
    # after its option is kept, since nothing tells it from an operand.
    got = run(tmp_path, "API_TOKEN=s3cr3t", NAME, "--api-key=s3cr3t", "--name", "kept")
    assert got.argv == ("API_TOKEN=…", NAME, "--api-key=…", "--name", "kept")
    assert "s3cr3t" not in json.dumps(dataclasses.asdict(got))
    assert got.verdict == PROVED


def ended_before_late(late: Path) -> bool:
    """Whether `--hang`'s child has ended without writing `late`: its lock is free at once where
    its group was ended, and only once it has written `late` and exited where it was not, which
    the wait, past the child's own delay, covers."""
    deadline = time.monotonic() + LATE_AFTER_SECONDS + 1
    with held(late).open("w") as lock:
        while True:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() > deadline:
                    return False
                time.sleep(0.02)
    return not late.exists()


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


@pytest.fixture
def private_tempdir(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> Path:
    """`tempfile`'s directory for this test alone, beside its `tmp_path` and never inside it: a
    scratch directory a run leaves there, as under the mutation of its removal the oracle applies,
    goes with pytest's own temporary directories and never into the developer's `TMPDIR`."""
    where = tmp_path_factory.mktemp("tempdir")
    monkeypatch.setattr(tempfile, "tempdir", str(where))
    return where


@pytest.mark.usefixtures("private_tempdir")
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
    [scratch] = adapter.seen
    assert not scratch.exists()
    assert ended_before_late(late)


@pytest.mark.usefixtures("private_tempdir")
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
    [scratch] = adapter.seen
    assert not scratch.exists()
    assert ended_before_late(late)


@pytest.mark.parametrize("where", ["tree-state", "plan", "reap"])
@pytest.mark.parametrize("how", ["interrupt", "terminate"])
def test_an_interrupt_anywhere_in_the_run_ends_it_not_proven(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, where: str, how: str
) -> None:
    # Not only in the wait: a Ctrl-C or a `SIGTERM` while the tree's state is taken, while the
    # adapter plans, or while the exited command's group is reaped ends the run `not proven`,
    # `interrupted`, with its scratch directory removed, and never escapes as an internal error.
    # Mutations (declared): the interrupt caught only in the wait -> the first two escape; the
    # reap outside the wait's handling -> the child the runner left in its group lives on.
    def stop() -> None:
        if how == "interrupt":
            raise KeyboardInterrupt
        os.kill(os.getpid(), signal.SIGTERM)
        time.sleep(STARTED_WAIT_SECONDS)

    adapter = StandIn()
    if where == "tree-state":
        monkeypatch.setattr(tree, "state", lambda *args: stop())
    elif where == "plan":
        planned = StandIn.plan

        def plan(self: StandIn, *args: object, **kwargs: object) -> object:
            planned(self, *args, **kwargs)  # type: ignore[arg-type]
            stop()
            raise AssertionError("not reached")

        monkeypatch.setattr(StandIn, "plan", plan)
    else:
        # The first reap is stopped; the one the interrupt's handling makes runs.
        reap = processes.kill_group
        calls: list[object] = []

        def kill_group(process: subprocess.Popen[bytes], *signum: int) -> None:
            calls.append(process)
            if len(calls) == 1:
                stop()
            reap(process, *signum)

        monkeypatch.setattr(processes, "kill_group", kill_group)
    before = signal.getsignal(signal.SIGTERM)
    # The runner leaves a child in its group and exits: the reap is what ends that child.
    started, late = tmp_path / "started", tmp_path / "late"
    try:
        got = run(tmp_path, NAME, "--leave", str(started), str(late), adapter=adapter)
    except KeyboardInterrupt:  # would stop the whole session rather than fail this case
        pytest.fail("the interrupt escaped prove")
    assert (got.verdict, got.reason) == (NOT_PROVEN, INTERRUPTED)
    assert signal.getsignal(signal.SIGTERM) is before
    [scratch] = adapter.seen
    assert not scratch.exists()
    if where == "reap":
        assert ended_before_late(late)


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
    [scratch] = adapter.seen
    assert not scratch.exists()


def test_a_plan_whose_report_lies_outside_its_scratch_is_a_defect_and_raises(
    tmp_path: Path,
) -> None:
    # A report the adapter put anywhere but the scratch directory `prove` made could be one the
    # repository committed, or read from a place another run writes: a defect in the adapter, as a
    # program that is not absolute is. Mutation (declared): the check dropped -> the run goes ahead
    # and its report is read from where the adapter put it.
    adapter = StandIn(elsewhere=tmp_path / "elsewhere")
    (tmp_path / "elsewhere").mkdir()
    with pytest.raises(ValueError, match="outside its scratch directory"):
        run(tmp_path, NAME, adapter=adapter)
    [scratch] = adapter.seen
    assert not scratch.exists()
    assert not (tmp_path / "elsewhere" / "report").exists()


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


def test_the_cap_counts_the_events_and_never_what_a_test_printed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsysbinary: pytest.CaptureFixture[bytes]
) -> None:
    # An event stream's `output` events are copied to the caller and left out of the report, so a
    # passing suite that prints far past the cap is proved; its result events alone past the cap
    # are still too large. Mutations (declared): the tee handed no line test, `read_lines` naming
    # none for the event stream -> the first run is too large.
    cap = 4096
    monkeypatch.setattr(run_module, "MAX_REPORT_BYTES", cap)
    monkeypatch.setattr(counts_module, "MAX_REPORT_BYTES", cap)
    teed = StandIn(source=ReportSource.STDOUT)
    got = run(tmp_path, NAME, "--print-lines", "1000", adapter=teed)
    assert (got.verdict, got.reason, got.counts) == (PROVED, "", Counts(1, 0, 0))
    assert len(capsysbinary.readouterr().out) > 10 * cap
    got = run(tmp_path, NAME, "--passes", "1000", adapter=teed)
    assert (got.verdict, got.reason) == (NOT_PROVEN, REPORT_TOO_LARGE)
    capsysbinary.readouterr()


def test_a_passing_suite_that_prints_past_the_cap_is_proved(tmp_path: Path) -> None:
    # One passing test that prints 1.7 million short lines, past 64 MiB once each is framed as an
    # `output` event: measured on Go 1.27.2, `go test` passes it.
    with open(os.devnull, "w", encoding="utf-8") as sink:
        got = run(
            tmp_path,
            NAME,
            "--print-lines",
            "1700000",
            adapter=StandIn(source=ReportSource.STDOUT),
            echo=sink,
        )
    assert (got.verdict, got.reason, got.counts) == (PROVED, "", Counts(1, 0, 0))


def _tee(tmp_path: Path) -> tuple[run_module._Tee, int, Path]:
    """A tee of an event stream on a pipe that stays empty, its chunks handed to `_copy` by the
    test, its report at the returned path; the pipe's writer to close."""
    source, writer = os.pipe()
    path = tmp_path / "report"
    report = os.open(path, os.O_WRONLY | os.O_CREAT, 0o600)
    caller = io.StringIO()
    tee = run_module._Tee(os.fdopen(source, "rb"), report, caller, read_line)
    return tee, writer, path


def test_the_tee_reads_a_line_cut_between_two_reads_whole(tmp_path: Path) -> None:
    # Mutation (declared): a line's held start dropped -> the report holds the pass event's end
    # alone.
    tee, writer, path = _tee(tmp_path)
    printed = b'{"Action":"output","Package":"p","Output":"x\\n"}\n'
    passed = b'{"Action":"pass","Package":"p","Test":"TestA"}\n'
    stream = printed + passed + printed
    for cut in (30, 60, 90):
        tee._copy(stream[cut - 30 : cut])
    tee._copy(stream[90:])
    os.close(writer)
    tee.finish()
    assert path.read_bytes() == passed


def test_the_tee_keeps_a_last_line_with_no_line_break(tmp_path: Path) -> None:
    # Mutation (declared): the last line, cut short, dropped -> the report is empty.
    tee, writer, path = _tee(tmp_path)
    passed = b'{"Action":"pass","Package":"p","Test":"TestA"}'
    tee._copy(passed)
    os.close(writer)
    tee.finish()
    assert path.read_bytes() == passed


def test_the_tee_holds_no_line_past_the_cap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A line longer than the cap is copied as it stands, so no report holding it fits and none is
    # held whole in memory. Mutation (declared): the line held whatever its length -> nothing is
    # written while it lasts.
    cap = 1000
    monkeypatch.setattr(run_module, "MAX_REPORT_BYTES", cap)
    tee, writer, path = _tee(tmp_path)
    for _ in range(5):
        tee._copy(b"x" * 400)
    assert path.stat().st_size == cap + 1
    assert len(tee._line) == 0
    os.close(writer)
    tee.finish()
    assert path.stat().st_size == cap + 1


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
    assert pidfile.exists(), (
        f"the escaped child never named itself in {pidfile} within {STARTED_WAIT_SECONDS} s"
    )
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
    # No shipped adapter plans an unverified runner, so the receipt is built here: its line says
    # so of one, and of no other.
    receipt = Receipt(Verdict.PROVED, "", "", ("x",), runner="junit", verified=False)
    assert "runner junit, not verified" in line(receipt)
    assert "not verified" not in line(dataclasses.replace(receipt, verified=True))


@pytest.mark.usefixtures("private_tempdir")
@pytest.mark.parametrize("verdict_report", ["pass", "none", "fail"])
def test_the_scratch_directory_is_removed_on_every_path(
    tmp_path: Path, verdict_report: str
) -> None:
    adapter = StandIn()
    run(tmp_path, NAME, "--report", verdict_report, adapter=adapter)
    [scratch] = adapter.seen
    assert not scratch.exists()
    assert not scratch.is_relative_to(tmp_path)


def test_the_receipt_names_untracked_and_ignored_files(tmp_path: Path) -> None:
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
    state = tree.state(root, ("test_*.py",))
    assert state.untracked is not None
    assert state.untracked[0] == "test_real.py"
    assert state.untracked[1] == "deps/test_00.py"
    assert (len(state.untracked), state.more) == (tree.UNTRACKED_LISTED, 6)


def test_the_untracked_list_stops_at_its_cap_and_counts_the_rest(tmp_path: Path) -> None:
    root = repository(tmp_path / "repo")
    for index in range(tree.UNTRACKED_LISTED + 5):
        (root / f"test_{index:02d}.py").write_text("", encoding="utf-8")
    state = tree.state(root, ("test_*.py",))
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
    state = tree.state(tmp_path, ("*",))
    assert state == tree.TreeState(None, None, None, 0)


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
