"""The `Stop`-hook recipe in `examples/stop-hook/`, run as Claude Code runs it.

Each case runs the recipe as a subprocess, from the checkout's root, with the hook's input on
standard input and a stub `stayfixed` first on `PATH`. The stub records the directory it ran in
and the arguments it was given, prints the answer the case gives it, and exits with the case's
code. The recipe is found from this file's own path, so a scratch checkout tests its own copy.

Every case asserts that the recipe printed nothing on standard output: Claude Code reads a JSON
object there on every exit code, so a word on stdout would be read as the hook's own answer.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from tests.gitfixture import env, git, needs_git

ROOT = Path(__file__).resolve().parents[1]
RECIPE = ROOT / "examples" / "stop-hook" / "prove_on_stop.py"
COMMAND = ["pytest", "-q"]

# The stub `stayfixed`: its first line of the record is where it ran, the rest its arguments.
STUB = """\
#!/bin/sh
{{ pwd -P; for word in "$@"; do printf '%s\\n' "$word"; done; }} > '{record}'
printf '%s\\n' '{answer}'
exit {code}
"""


def _stub(tmp_path: Path, answer: str, code: int) -> Path:
    """A `bin/` directory holding the stub, and the path its record will be written to."""
    directory = tmp_path / "bin"
    directory.mkdir()
    record = tmp_path / "record"
    program = directory / "stayfixed"
    program.write_text(STUB.format(record=record, answer=answer, code=code), encoding="utf-8")
    program.chmod(0o755)
    return record


def _verdict(verdict: str, reason: str | None = None) -> str:
    return json.dumps({"verdict": verdict, "reason": reason, "counts": {"passed": 2}})


def _stop(cwd: Path, *, active: bool = False) -> str:
    """A `Stop` input as Claude Code writes it."""
    return json.dumps(
        {
            "session_id": "abc123",
            "transcript_path": str(cwd / "transcript.jsonl"),
            "cwd": str(cwd),
            "permission_mode": "default",
            "hook_event_name": "Stop",
            "stop_hook_active": active,
            "last_assistant_message": "Done.",
        }
    )


def _run(tmp_path: Path, stdin: str) -> subprocess.CompletedProcess[str]:
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    path = os.pathsep.join([str(tmp_path / "bin"), os.environ.get("PATH", os.defpath)])
    return subprocess.run(
        [sys.executable, "-I", str(RECIPE), "--", *COMMAND],
        cwd=ROOT,
        input=stdin,
        capture_output=True,
        text=True,
        env=env(home, PATH=path),
        check=False,
        timeout=60,
    )


def test_a_proved_run_lets_the_stop_through(tmp_path: Path) -> None:
    record = _stub(tmp_path, _verdict("proved"), 0)
    done = _run(tmp_path, _stop(tmp_path))
    assert (done.returncode, done.stdout) == (0, ""), done.stderr
    # `prove` is asked for its JSON, under a bound below the hook's own 600 s, and the command is
    # passed on as typed after `--`.
    assert record.read_text(encoding="utf-8").splitlines()[1:] == [
        "prove",
        "--json",
        "--timeout",
        "540",
        "--",
        *COMMAND,
    ]


def test_a_failed_run_blocks_the_stop(tmp_path: Path) -> None:
    # Exit 2 keeps the agent working, with stderr as the reason it is given. Mutation (oracle):
    # `mutations/`'s "the stop recipe lets a failed run through".
    _stub(tmp_path, _verdict("failed", "tests-failed"), 1)
    done = _run(tmp_path, _stop(tmp_path))
    assert (done.returncode, done.stdout) == (2, ""), done.stderr
    assert "failed" in done.stderr
    assert "pytest -q" in done.stderr
    assert len(done.stderr.splitlines()) == 1, done.stderr


def test_a_continued_stop_is_let_through_without_a_run(tmp_path: Path) -> None:
    # The agent is already working on because this hook blocked it. Claude Code's cap of eight
    # continuations resets on every tool call, so only this let-through keeps a tree the agent
    # cannot make green from blocking every stop. Mutation (oracle): `mutations/`'s "the stop
    # recipe blocks a stop it is already continuing".
    record = _stub(tmp_path, _verdict("failed", "tests-failed"), 1)
    done = _run(tmp_path, _stop(tmp_path, active=True))
    assert (done.returncode, done.stdout) == (0, ""), done.stderr
    assert not record.exists()


def test_input_that_is_no_object_is_a_non_blocking_error(tmp_path: Path) -> None:
    record = _stub(tmp_path, _verdict("proved"), 0)
    for stdin in ("not json", "[]"):
        done = _run(tmp_path, stdin)
        assert (done.returncode, done.stdout) == (1, ""), done.stderr
        assert len(done.stderr.splitlines()) == 1, done.stderr
    assert not record.exists()


def test_a_stayfixed_that_cannot_answer_is_a_non_blocking_error(tmp_path: Path) -> None:
    # No continuation repairs a missing install, so the user is told and the agent is not sent
    # round: exit 1, never 2.
    _stub(tmp_path, "Traceback (most recent call last):", 1)
    done = _run(tmp_path, _stop(tmp_path))
    assert (done.returncode, done.stdout) == (1, ""), done.stderr
    assert len(done.stderr.splitlines()) == 1, done.stderr


@needs_git
def test_a_stop_from_a_subdirectory_runs_at_the_top_of_the_work_tree(tmp_path: Path) -> None:
    # `cwd` follows the agent's `cd`, and a command relative to the project finds no tests in a
    # subdirectory of it.
    repository = tmp_path / "repository"
    (repository / "src" / "deep").mkdir(parents=True)
    git(repository, "init", "-q")
    record = _stub(tmp_path, _verdict("proved"), 0)
    done = _run(tmp_path, _stop(repository / "src" / "deep"))
    assert (done.returncode, done.stdout) == (0, ""), done.stderr
    assert record.read_text(encoding="utf-8").splitlines()[0] == str(repository.resolve())
