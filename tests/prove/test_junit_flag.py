"""`prove --junit PATH`: the JUnit report of a command no runner adapter knows, counted when the run
wrote it, and the runner marked as not verified.

The command is `tests/prove/stand_in.py` run as a program by the interpreter running the suite,
which no adapter recognises: it writes the JUnit report it is told to at the path it is told to,
relative to the directory it runs in, and exits with the code it is told to.
"""

from __future__ import annotations

import json
import os
import shlex
import sys
from collections.abc import Sequence
from pathlib import Path

import pytest

from stayfixed import processes
from stayfixed.printed import clipped
from stayfixed.profiles.runners import RunnerAdapter
from stayfixed.prove.counts import Counts
from stayfixed.prove.run import (
    GREEN_BUT_EXITED,
    INTERRUPTED,
    JUNIT_UNCHANGED,
    NONE_RAN,
    NOT_RECOGNISED,
    NOT_STARTED,
    WORDS,
    Receipt,
    Verdict,
    line,
    prove,
)
from tests.gitfixture import git
from tests.prove.stand_in import JUNIT, NAME, PROGRAM, StandIn
from tests.prove.test_command import prove_cli
from tests.prove.test_run import fake_uv, with_uv

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


def program(path: Path, *before: str) -> Path:
    """An executable at `path` that runs `before`, then the stand-in writing the JUnit report
    `REPORT` it is told to."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [*before, f'exec "{sys.executable}" "{PROGRAM}" --report-path {REPORT} --source file']
    path.write_text("#!/bin/sh\n" + "\n".join(lines) + "\n", encoding="utf-8")
    path.chmod(0o755)
    return path


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
    # The detail names the file as the run read it, by its realpath. Mutation: none -- the detail
    # is wording.
    resolved = os.path.realpath(tmp_path / REPORT)
    assert (got.verdict, got.reason, got.detail) == (NOT_PROVEN, JUNIT_UNCHANGED, resolved)
    assert got.counts is None
    assert line(got).startswith(f"not proven: {WORDS[JUNIT_UNCHANGED]}: {clipped(resolved)};")


def test_a_link_the_run_points_at_a_fresh_report_is_counted(tmp_path: Path) -> None:
    # A runner that writes `run-<stamp>.xml` and points `latest.xml` at it: the path is followed
    # to the file it reaches, which the run wrote. Mutation (declared): the path's state taken
    # without following the link -> the run's link is no regular file, `junit-unchanged`.
    (tmp_path / "old.xml").write_bytes(JUNIT["fail"])
    (tmp_path / REPORT).symlink_to("old.xml")
    fresh = shlex.join(writer("pass", at="fresh.xml"))
    command = ["sh", "-c", f"{fresh} && ln -sfn fresh.xml {REPORT}"]
    got = run(tmp_path, command)
    assert (tmp_path / REPORT).is_symlink()
    assert (got.verdict, got.counts) == (PROVED, Counts(2, 0, 0))


def test_a_report_written_through_a_link_is_counted(tmp_path: Path) -> None:
    # The run writes its report through a link that was there before it: the file the link
    # reaches is the one it rewrote.
    green = tmp_path / "green.xml"
    green.write_bytes(JUNIT["fail"])
    (tmp_path / REPORT).symlink_to(green)
    got = run(tmp_path, writer("pass"))
    assert (got.verdict, got.counts) == (PROVED, Counts(2, 0, 0))


def test_a_link_to_a_stale_report_the_run_never_touched_is_not_proven(tmp_path: Path) -> None:
    # Mutation (declared): the changed-file check dropped -> the stale green report is `proved`.
    green = tmp_path / "green.xml"
    green.write_bytes(JUNIT["pass"])
    (tmp_path / REPORT).symlink_to(green)
    got = run(tmp_path, writer("none"))
    assert (got.verdict, got.reason, got.detail) == (
        NOT_PROVEN,
        JUNIT_UNCHANGED,
        os.path.realpath(green),
    )


def test_a_link_the_run_newly_makes_to_a_stale_report_is_the_bound_s(tmp_path: Path) -> None:
    # A link that was not there before, made to a file that was: nothing before the run tells
    # it from a fresh report, so it is counted. What a file in the tree can do is the bound's.
    green = tmp_path / "green.xml"
    green.write_bytes(JUNIT["pass"])
    got = run(tmp_path, ["sh", "-c", f"ln -s green.xml {REPORT}"])
    assert (got.verdict, got.counts) == (PROVED, Counts(2, 0, 0))


def test_with_junit_no_adapter_is_consulted(tmp_path: Path) -> None:
    # A command an adapter recognises runs as typed and its `--junit` report is counted, its
    # runner not verified. Mutation (declared): the adapters asked under `--junit` -> the
    # stand-in's adapter plans the run.
    adapter = StandIn()
    stand_in = program(tmp_path / "bin" / NAME)
    got = run(tmp_path, [f"PATH={stand_in.parent}", NAME], adapters=[adapter])
    assert (got.verdict, got.counts, got.runner, got.verified) == (
        PROVED,
        Counts(2, 0, 0),
        None,
        False,
    )
    assert adapter.seen == []
    assert got.program == os.path.realpath(stand_in)


def test_the_program_is_found_on_the_path_the_command_assigns(tmp_path: Path) -> None:
    # As a shell finds it: the command's own `PATH`, never the caller's alone, through the
    # adapters this stayfixed ships, one of which recognises `pytest`. Mutations (declared): the
    # command's assignments left out of the run's environment, or the program looked up in
    # stayfixed's own -> it is not the `pytest` the command's `PATH` names.
    pytest_ = program(tmp_path / "tools" / "pytest")
    got = prove(
        [f"PATH={pytest_.parent}", "pytest", "-q"],
        cwd=tmp_path,
        environ={"PATH": str(tmp_path / "empty")},
        timeout=600,
        junit=Path(REPORT),
    )
    assert (got.verdict, got.runner, got.program) == (PROVED, None, os.path.realpath(pytest_))


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


def test_the_path_is_read_from_the_directory_the_launcher_runs_the_command_in(
    tmp_path: Path,
) -> None:
    # `uv run --directory sub env`, a launcher read up to its `env`, since no adapter recognises
    # the writer: the command writes its report in `sub`, as its own relative paths are read
    # there, and the path is read from there too. Mutation (declared): the path read from the
    # directory the command was typed in -> no report there, `junit-unchanged`.
    sub = tmp_path / "sub"
    sub.mkdir()
    uv = fake_uv(tmp_path / "bin")
    got = prove(
        ["uv", "run", "--directory", "sub", "env", *writer("pass")],
        cwd=tmp_path,
        environ=with_uv(uv),
        timeout=600,
        junit=Path(REPORT),
    )
    assert (sub / REPORT).exists()
    assert (got.verdict, got.counts, got.directory) == (
        PROVED,
        Counts(2, 0, 0),
        os.path.realpath(sub),
    )


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

    def end(process: object, *grace: float) -> None:
        ended.append(1)
        real_end(process, *grace)  # type: ignore[arg-type]

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


def test_a_launcher_runs_as_typed_under_junit(tmp_path: Path) -> None:
    # Its options and its variables are the command's: nothing of them is refused or removed.
    uv = program(tmp_path / "tools" / "uv", 'printf "%s\\n" "$UV_ENV_FILE" "$@" > argv.txt')
    argv = [f"PATH={uv.parent}", "UV_ENV_FILE=e.env", "uv", "run", "--env-file", "e.env", "mvn"]
    got = run(tmp_path, argv)
    assert (got.verdict, got.verified, got.scrubbed) == (PROVED, False, ())
    written = (tmp_path / "argv.txt").read_text(encoding="utf-8")
    assert written == "e.env\nrun\n--env-file\ne.env\nmvn\n"


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
