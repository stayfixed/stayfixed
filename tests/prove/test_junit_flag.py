"""`prove --junit PATH`: the JUnit report of a command no runner adapter knows, counted when the run
wrote it, and the runner marked as not verified.

The command is `tests/prove/stand_in.py` run as a program by the interpreter running the suite,
which no adapter recognises: it writes the JUnit report it is told to at the path it is told to,
relative to the directory it runs in, and exits with the code it is told to.
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path

import pytest

from stayfixed import processes
from stayfixed.printed import clipped
from stayfixed.profiles.runners import RunnerAdapter
from stayfixed.prove.counts import Counts
from stayfixed.prove.run import (
    ASSIGNED_FORGING,
    GREEN_BUT_EXITED,
    INTERRUPTED,
    JUNIT_BESIDE_ADAPTER,
    JUNIT_UNCHANGED,
    NONE_RAN,
    NOT_RECOGNISED,
    NOT_STARTED,
    REFUSED_LAUNCHER_OPTION,
    WORDS,
    Receipt,
    Verdict,
    line,
    prove,
)
from tests.gitfixture import git
from tests.prove.stand_in import JUNIT, NAME, PROGRAM, StandIn
from tests.prove.test_command import prove_cli

PROVED, FAILED, NOT_PROVEN, REFUSED = (
    Verdict.PROVED,
    Verdict.FAILED,
    Verdict.NOT_PROVEN,
    Verdict.REFUSED,
)
REPORT = "out.xml"
INTERPRETER = os.path.realpath(sys.executable)


def writer(shape: str = "pass", *more: str, at: str = REPORT) -> list[str]:
    """A command no adapter recognises that writes the JUnit report `shape` at `at`."""
    return [
        sys.executable,
        str(PROGRAM),
        "--report-path",
        at,
        "--source",
        "file",
        "--report",
        shape,
        *more,
    ]


def run(
    cwd: Path,
    argv: Sequence[str],
    junit: str | Path = REPORT,
    adapters: Sequence[RunnerAdapter] | None = None,
) -> Receipt:
    return prove(
        argv,
        cwd=cwd,
        environ=dict(os.environ),
        timeout=600,
        adapters=[StandIn()] if adapters is None else adapters,
        junit=Path(junit),
    )


def test_a_report_the_run_wrote_is_counted_and_marked_unverified(tmp_path: Path) -> None:
    # Mutation (declared): `verified` left true -> the receipt says the runner was verified.
    got = run(tmp_path, writer("pass"))
    assert (got.verdict, got.reason, got.counts, got.exit_code) == (PROVED, "", Counts(2, 0, 0), 0)
    assert (got.runner, got.verified, got.program) == (None, False, INTERPRETER)
    assert got.report_digest is not None


def test_a_report_rewritten_in_place_is_counted(tmp_path: Path) -> None:
    # The same file, its bytes rewritten: a runner that truncates and writes its report anew.
    # Mutation (declared): the file's state read as its inode alone -> `junit-unchanged`.
    report = tmp_path / REPORT
    report.write_bytes(JUNIT["fail"])
    inode = report.stat().st_ino
    got = run(tmp_path, writer("pass"))
    assert report.stat().st_ino == inode
    assert (got.verdict, got.counts) == (PROVED, Counts(2, 0, 0))


def test_a_report_older_than_the_run_is_not_proven(tmp_path: Path) -> None:
    # A committed or stale report the run never touched counts nothing. Mutation (declared): the
    # changed-file check dropped -> the stale green report is `proved`.
    (tmp_path / REPORT).write_bytes(JUNIT["pass"])
    got = run(tmp_path, writer("none"))
    assert (got.verdict, got.reason, got.detail) == (NOT_PROVEN, JUNIT_UNCHANGED, REPORT)
    assert got.counts is None
    assert line(got).startswith(f"not proven: {WORDS[JUNIT_UNCHANGED]}: {clipped(REPORT)};")


@pytest.mark.parametrize("made_by", ["before", "the run"])
def test_a_symlinked_report_is_not_proven(tmp_path: Path, made_by: str) -> None:
    # A link the run writes through, or one the run makes to a green report elsewhere. Mutation
    # (declared): any file the run changed read -> the link the run made is `proved`.
    green = tmp_path / "green.xml"
    green.write_bytes(JUNIT["pass"])
    if made_by == "before":
        (tmp_path / REPORT).symlink_to(green)
        command = writer("pass")
    else:
        command = ["sh", "-c", f"ln -s green.xml {REPORT}"]
    got = run(tmp_path, command)
    assert (tmp_path / REPORT).is_symlink()
    assert (got.verdict, got.reason) == (NOT_PROVEN, JUNIT_UNCHANGED)


def test_a_known_runner_beside_junit_is_refused(tmp_path: Path) -> None:
    # A runner an adapter recognises always gets its adapter's checks. Mutation (declared): the
    # refusal dropped -> the stand-in runs and its green report is `proved`.
    adapter = StandIn()
    got = run(tmp_path, [NAME, "--report-path", REPORT, "--source", "file"], adapters=[adapter])
    assert (got.verdict, got.reason, got.runner, got.verified) == (
        REFUSED,
        JUNIT_BESIDE_ADAPTER,
        NAME,
        False,
    )
    assert adapter.seen == []  # nothing was planned or run
    assert not (tmp_path / REPORT).exists()
    # And through the adapters this stayfixed ships.
    shipped = prove(
        ["pytest", "-q"], cwd=tmp_path, environ={"PATH": ""}, timeout=600, junit=Path(REPORT)
    )
    assert (shipped.verdict, shipped.reason, shipped.runner) == (
        REFUSED,
        JUNIT_BESIDE_ADAPTER,
        "pytest",
    )


def test_an_empty_junit_report_fails(tmp_path: Path) -> None:
    got = run(tmp_path, writer("empty"))
    assert (got.verdict, got.reason, got.counts) == (FAILED, NONE_RAN, Counts(0, 0, 0))


def test_the_cascade_is_unchanged(tmp_path: Path) -> None:
    got = run(tmp_path, writer("pass", "--code", "1"))
    assert (got.verdict, got.reason, got.exit_code) == (NOT_PROVEN, GREEN_BUT_EXITED, 1)


def test_the_line_says_the_runner_is_not_verified(tmp_path: Path) -> None:
    # Mutation (declared): the line says nothing of a runner no adapter resolved.
    got = run(tmp_path, writer("pass"))
    assert line(got) == (
        f"proved: {WORDS['']}; 2 passed, 0 failed, 0 skipped; "
        f"runner not verified, ran {clipped(INTERPRETER)}"
    )


def test_the_path_is_read_from_the_directory_the_command_is_typed_in(tmp_path: Path) -> None:
    # Typed in a subdirectory of the repository, the path is that directory's, as the command's own
    # relative paths are. Mutation (declared): the path read from the project's top-level -> no
    # report there, `junit-unchanged`.
    root = tmp_path / "repo"
    (root / "sub").mkdir(parents=True)
    git(root, "init", "-q")
    got = run(root / "sub", writer("pass"))
    assert (root / "sub" / REPORT).exists()
    assert (got.verdict, got.counts) == (PROVED, Counts(2, 0, 0))


def test_an_absolute_path_is_read_where_it_names(tmp_path: Path) -> None:
    elsewhere = tmp_path / "reports" / "r.xml"
    elsewhere.parent.mkdir()
    got = run(tmp_path / "reports", writer("pass", at=str(elsewhere)), junit=elsewhere)
    assert got.verdict == PROVED


def test_an_interrupted_junit_run_is_not_proven(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ended: list[int] = []

    def interrupted(process: object, seconds: float) -> None:
        raise KeyboardInterrupt

    def end(process: object) -> None:
        ended.append(1)
        real_end(process)  # type: ignore[arg-type]

    real_end = processes.end
    monkeypatch.setattr(processes, "exited", interrupted)
    monkeypatch.setattr(processes, "end", end)
    got = run(tmp_path, writer("pass", "--sleep", "30"))
    assert (got.verdict, got.reason, got.counts) == (NOT_PROVEN, INTERRUPTED, None)
    assert ended == [1]


def test_a_program_that_is_not_there_is_not_started(tmp_path: Path) -> None:
    # Mutation (declared): a receipt with no plan marked verified -> `verified` is true.
    got = run(tmp_path, ["no-such-program-for-prove"])
    assert (got.verdict, got.reason, got.verified) == (NOT_PROVEN, NOT_STARTED, False)


def test_a_command_of_assignments_alone_is_not_recognised(tmp_path: Path) -> None:
    got = run(tmp_path, ["A=1"])
    assert (got.verdict, got.reason, got.verified) == (NOT_PROVEN, NOT_RECOGNISED, False)


@pytest.mark.parametrize(
    ("argv", "reason"),
    [
        (["UV_ENV_FILE=e.env", "uv", "run", "mvn", "test"], ASSIGNED_FORGING),
        (["uv", "run", "--env-file", "e.env", "mvn", "test"], REFUSED_LAUNCHER_OPTION),
    ],
)
def test_the_launcher_s_file_options_are_refused_under_junit_too(
    tmp_path: Path, argv: list[str], reason: str
) -> None:
    got = run(tmp_path, argv)
    assert got.verdict == REFUSED
    assert got.reason == reason
    assert got.verified is False


def test_the_command_takes_junit_and_says_the_runner_is_not_verified(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Mutation (declared): the command never hands `--junit` on -> nothing counts the command.
    code, out, _ = prove_cli(tmp_path, monkeypatch, "--junit", REPORT, "--", *writer("pass"))
    assert code == 0
    assert out.startswith("proved: ")
    assert "runner not verified" in out
    code, out, _ = prove_cli(
        tmp_path,
        monkeypatch,
        "--json",
        "--junit",
        "again.xml",
        "--",
        *writer("pass", at="again.xml"),
    )
    receipt = json.loads(out)
    assert (code, receipt["verdict"], receipt["runner"], receipt["verified"]) == (
        0,
        "proved",
        None,
        False,
    )
