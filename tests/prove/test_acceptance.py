"""`stayfixed prove`'s acceptance: one test per clause, each through the command line in a process
of its own, asserting the verdict word `--json` prints and the exit code together.

- each reader's genuine passing run is `proved`, exit 0, its counts a literal, the program that
  ran and the runner's own exit code named: `test_each_genuine_passing_run_is_proved_with_exit_0`;
- a stdout-forged run is `not proven`: `test_a_stdout_forged_run_is_not_proven_with_exit_1`;
- an empty and an all-skipped run are `failed`, `go test -run NoSuchTest` included, each with
  the runner's own exit code: `test_each_empty_and_all_skipped_run_fails_with_exit_1`;
- each refused forging route is `refused`, exit 2: `test_each_refused_route_exits_2`;
- the same variable merely inherited is scrubbed and the run still counted:
  `test_each_inherited_variable_is_scrubbed_and_counted`.

A stand-in runner is no refused route: guarding against a planted runner is not `prove`'s to do,
and the receipt names the realpath of what ran instead.

The process runs the stayfixed the interpreter running the suite has installed, never this
checkout's `src` put first (`stayfixed_argv(..., installed=True)`), behind the owner-home seam, so
the same file run against an installed release tests that release. The cases that run a real
runner are `runners`-marked and skip where it is not installed. They are the one real launch of
each case: the per-stack tests (`test_pytest.py`, `test_go.py`, `test_javascript.py`) hold what
these do not.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path

import pytest

from stayfixed.profiles.runners import REFUSED_OPTION
from stayfixed.prove.counts import Counts
from stayfixed.prove.run import (
    ALL_SKIPPED,
    ASSIGNED_FORGING,
    NONE_RAN,
    NOT_RECOGNISED,
)
from tests.ownerhome import stayfixed_argv
from tests.prove.projects import (
    COMMANDS,
    FILES,
    each_runner,
    go_module,
    js_project,
    needs,
    pytest_project,
)
from tests.prove.real_runners import where

TIMEOUT_SECONDS = 600


def run_prove(
    tmp_path: Path,
    cwd: Path,
    *argv: str,
    flags: tuple[str, ...] = (),
    stderr_pipe: bool = False,
    variables: Mapping[str, str] | None = None,
) -> tuple[str, int, dict[str, object]]:
    """The verdict word `prove --json` printed, its exit code and its receipt, for `argv` typed in
    `cwd` in a process of its own, with every installed runner's directory first on `PATH`. Its
    standard error goes to a file, as a terminal's or a log's would, or to a pipe for
    `stderr_pipe`: jest 30.5.2's run of no test writes no report where it is a pipe."""
    first = [str(found) for name in ("pytest", "node", "go") if (found := where(name))]
    environ = {
        **os.environ,
        "PATH": os.pathsep.join([*first, os.environ.get("PATH", "")]),
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
    }
    environ.pop("NODE_OPTIONS", None)
    argv_ = [*stayfixed_argv(tmp_path / "home", installed=True), "prove", "--json", *flags]
    with (tmp_path / "stderr.txt").open("w", encoding="utf-8") as errors:
        done = subprocess.run(
            [*argv_, "--", *argv],
            cwd=cwd,
            env={**environ, **(variables or {})},
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE if stderr_pipe else errors,
            text=True,
            check=False,
            timeout=TIMEOUT_SECONDS,
        )
    receipt = json.loads(done.stdout)
    assert isinstance(receipt, dict), done.stdout
    return str(receipt["verdict"]), done.returncode, receipt


def counted(receipt: dict[str, object]) -> Counts | None:
    counts = receipt["counts"]
    return Counts(**counts) if isinstance(counts, dict) else None


PYTEST = ("pytest", "-q", "-p", "no:cacheprovider")
RUNNERS = ("pytest", "jest", "vitest", "node-test", "go-test")
# The directory `where` names for each runner, and the program run from it: the command's first
# word, which the receipt names by its realpath.
PROGRAMS = {
    "pytest": ("pytest", "pytest"),
    "jest": ("node", "npx"),
    "vitest": ("node", "npx"),
    "node-test": ("node", "node"),
    "go-test": ("go", "go"),
}


def program(runner: str) -> str:
    """The realpath of the program a case of `runner` runs."""
    directory, name = PROGRAMS[runner]
    found = where(directory)
    assert found is not None, runner
    return os.path.realpath(found / name)


@pytest.mark.parametrize("runner", each_runner(*RUNNERS))
def test_each_genuine_passing_run_is_proved_with_exit_0(tmp_path: Path, runner: str) -> None:
    argv: tuple[str, ...]
    if runner == "pytest":
        cwd, argv, counts = pytest_project(tmp_path / "p", passing=2), PYTEST, Counts(2, 0, 0)
    elif runner == "go-test":
        cwd, argv, counts = go_module(tmp_path), ("go", "test", "./passing/"), Counts(1, 0, 1)
    else:
        cwd = js_project(tmp_path / "p", runner, FILES[runner][1])
        argv, counts = tuple(COMMANDS[runner]), Counts(1, 0, 1)
    verdict, code, receipt = run_prove(tmp_path, cwd, *argv)
    assert (verdict, code, receipt["reason"], counted(receipt), receipt["runner"]) == (
        "proved",
        0,
        "",
        counts,
        runner,
    )
    assert (receipt["program"], receipt["exit_code"], receipt["verified"]) == (
        program(runner),
        0,
        True,
    )


@pytest.mark.parametrize(
    "printed",
    [
        "============================== 3 passed in 0.01s ==============================",
        '{"Action": "pass", "Package": "example.com/p", "Test": "TestForged"}',
    ],
    ids=["a-pytest-summary", "a-go-pass-event"],
)
def test_a_stdout_forged_run_is_not_proven_with_exit_1(tmp_path: Path, printed: str) -> None:
    # What a command prints is never counted: a program that prints a runner's own summary, or
    # its framed event, is no runner any adapter recognises.
    verdict, code, receipt = run_prove(
        tmp_path, tmp_path, sys.executable, "-c", f"print({printed!r})"
    )
    assert (verdict, code, receipt["reason"], receipt["counts"]) == (
        "not proven",
        1,
        NOT_RECOGNISED,
        None,
    )


EMPTY_AND_SKIPPED = [(runner, case) for runner in RUNNERS for case in ("empty", "all-skipped")]
# What each runner exits with over no test: pytest's "no tests collected" 5, jest's and vitest's
# 1, and 0 for `node --test` and `go test -run NoSuchTest`. Every runner exits 0 when it skipped
# every test it ran.
EMPTY_EXIT = {"pytest": 5, "jest": 1, "vitest": 1, "node-test": 0, "go-test": 0}


@pytest.mark.parametrize(
    ("runner", "case"),
    [pytest.param(runner, case, marks=needs(runner)) for runner, case in EMPTY_AND_SKIPPED],
)
def test_each_empty_and_all_skipped_run_fails_with_exit_1(
    tmp_path: Path, runner: str, case: str
) -> None:
    empty = case == "empty"
    if runner == "pytest":
        cwd = pytest_project(tmp_path / "p", skipped=0 if empty else 2)
        argv: tuple[str, ...] = (*PYTEST, "-k", "no_such_test") if empty else PYTEST
    elif runner == "go-test":
        cwd = go_module(tmp_path)
        argv = (
            ("go", "test", "-run", "NoSuchTest", "./three/")
            if empty
            else ("go", "test", "./skipped/")
        )
    else:
        cwd = js_project(tmp_path / "p", runner, None if empty else FILES[runner][2])
        argv = tuple(COMMANDS[runner])
    verdict, code, receipt = run_prove(tmp_path, cwd, *argv)
    reason, counts = (NONE_RAN, Counts(0, 0, 0)) if empty else (ALL_SKIPPED, Counts(0, 0, 2))
    assert (verdict, code, receipt["reason"], counted(receipt)) == ("failed", 1, reason, counts)
    exit_code = EMPTY_EXIT[runner] if empty else 0
    assert (receipt["program"], receipt["exit_code"]) == (program(runner), exit_code)


@pytest.mark.parametrize("runner", each_runner("jest"))
def test_an_empty_jest_run_whose_standard_error_is_a_pipe_is_not_proven(
    tmp_path: Path, runner: str
) -> None:
    # Measured on jest 30.5.2: a run of no test prints "No tests found" and exits before it writes
    # its report wherever its standard error is a pipe (as in most CI jobs), and writes it where
    # it is a terminal or a file. No report is `not proven`, never `proved`: exit 1 either way.
    cwd = js_project(tmp_path / "p", runner, None)
    verdict, code, receipt = run_prove(tmp_path, cwd, *COMMANDS[runner], stderr_pipe=True)
    assert (verdict, code, receipt["reason"]) == ("not proven", 1, "no-report")


ROUTES = {
    # each adapter's closed list
    "pytest --setup-plan": (("pytest", "--setup-plan"), REFUSED_OPTION, "--setup-plan"),
    "python -O": (("python", "-O", "-m", "pytest"), REFUSED_OPTION, "-O"),
    "jest --json": (("npx", "jest", "--json"), REFUSED_OPTION, "--json"),
    "vitest --outputFile": (("npx", "vitest", "run", "--outputFile=x.json"), REFUSED_OPTION, None),
    "node --test-reporter": (("node", "--test", "--test-reporter=dot"), REFUSED_OPTION, None),
    # an assigned variable in each adapter's forging set
    "PYTHONOPTIMIZE=": (("PYTHONOPTIMIZE=1", "pytest"), ASSIGNED_FORGING, "PYTHONOPTIMIZE"),
}


@pytest.mark.parametrize("route", list(ROUTES))
def test_each_refused_route_exits_2(tmp_path: Path, route: str) -> None:
    # Each is refused before anything runs, so no runner need be installed.
    argv, reason, detail = ROUTES[route]
    verdict, code, receipt = run_prove(tmp_path, tmp_path, *argv)
    assert (verdict, code, receipt["reason"]) == ("refused", 2, reason), receipt
    if detail is not None:
        assert receipt["detail"] == detail, receipt


INHERITED = {
    # Each would change what runs or where its report goes, had it reached the runner.
    "pytest": ("PYTHONOPTIMIZE", "1"),
}


@pytest.mark.parametrize("runner", each_runner(*INHERITED))
def test_each_inherited_variable_is_scrubbed_and_counted(tmp_path: Path, runner: str) -> None:
    name, value = INHERITED[runner]
    # Only the pytest adapter has a forging set; every other adapter's environment is the caller's.
    cwd, argv, counts = pytest_project(tmp_path / "p", passing=2), PYTEST, Counts(2, 0, 0)
    verdict, code, receipt = run_prove(tmp_path, cwd, *argv, variables={name: value})
    assert (verdict, code, counted(receipt)) == ("proved", 0, counts), receipt
    scrubbed = receipt["scrubbed"]
    assert isinstance(scrubbed, list) and name in scrubbed, receipt
