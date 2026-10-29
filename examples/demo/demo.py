"""A demonstration of stayfixed, run against a small repository it builds in a scratch directory.

    python3 -I examples/demo/demo.py STAYFIXED [--require-claude] [--keep]

`STAYFIXED` is the `stayfixed` program under test. Each act runs it as a user would and passes
only on the product's own answer: its exit code and the fields of the one JSON object its
`--json` prints on standard output. Nothing this script prints is ever read back, so an act
cannot pass on the script's word.

Every command runs with `HOME` inside the scratch directory, `GIT_CONFIG_NOSYSTEM=1`, fixed
author and committer names, emails and dates, and a `bin/` directory first on `PATH` that holds a
link named `stayfixed` to `STAYFIXED`, so a configured `["stayfixed", ...]` runs the program under
test. Nothing reaches the network: `pytest` and `git` come from the caller's `PATH`.

Exit 0 when no act failed, 1 when one did, 2 on a usage error.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import FrameType

# The whole run's wall time is printed beside this goal, in seconds; it is a goal and not a bound.
GOAL_SECONDS = 60
# How long one command may run before its act fails: a named cap, so a hung command ends the act
# instead of the demo. Ten times what the slowest act's commands take on a laptop.
COMMAND_TIMEOUT_SECONDS = 300

# The fixed identity and date every commit in the fixture carries, so two runs build the same
# history.
IDENTITY = "Demo Author"
EMAIL = "demo@example.com"
DATE = "2026-01-01T00:00:00+00:00"

# The fixture repository, by its path inside it. `conftest.py` at the root is what makes pytest
# put the root on the import path, so the tests import `total` without an install.
FIXTURE = {
    ".gitignore": "__pycache__/\n.pytest_cache/\n",
    "conftest.py": "# Here so that pytest puts this directory on the import path.\n",
    "total.py": ('def total(items):\n    """The sum of every item."""\n    return sum(items)\n'),
    "tests/test_total.py": (
        "from total import total\n"
        "\n"
        "\n"
        "def test_total_adds_every_item():\n"
        "    assert total([1, 2, 3]) == 6\n"
        "\n"
        "\n"
        "def test_total_of_nothing_is_zero():\n"
        "    assert total([]) == 0\n"
    ),
    "tests/test_skipped.py": (
        "import pytest\n"
        "\n"
        "\n"
        '@pytest.mark.skip(reason="a test that never runs")\n'
        "def test_never_runs():\n"
        "    raise AssertionError\n"
    ),
}


class ActFailed(Exception):
    """An act's command did not answer as the act expects; the message says what differed."""


class Skipped(Exception):
    """An act could not run here; the message says why."""


@dataclass(frozen=True)
class Field:
    """One field of a `--json` object an act asserts.

    `path` is dotted into the object; a segment `rows[name=x]` takes the one element of the list
    `rows` whose `name` is `x`. `how` says what the value must be: `is` equal to `expected`,
    `holds` a list holding it, `lacks` a list without it, `names` a string containing it.
    """

    path: str
    expected: object
    how: str = "is"

    def describe(self) -> str:
        return f"{self.path} {self.how} {json.dumps(self.expected)}"


@dataclass(frozen=True)
class Ran:
    code: int
    stdout: str
    stderr: str


_MISSING = object()
_SELECTOR = re.compile(r"^(?P<key>[^\[]+)\[(?P<field>[^=\]]+)=(?P<value>[^\]]*)\]$")


def _lookup(document: object, path: str) -> object:
    """The value at `path` in `document`, or `_MISSING`."""
    value = document
    for segment in path.split("."):
        selector = _SELECTOR.match(segment)
        key = selector.group("key") if selector else segment
        if not isinstance(value, dict) or key not in value:
            return _MISSING
        value = value[key]
        if selector:
            if not isinstance(value, list):
                return _MISSING
            rows = [
                row
                for row in value
                if isinstance(row, dict)
                and row.get(selector.group("field")) == selector.group("value")
            ]
            if len(rows) != 1:
                return _MISSING
            value = rows[0]
    return value


def _holds(field: Field, value: object) -> bool:
    if field.how == "is":
        # `True == 1` in Python; a JSON `true` is not the number 1, so the types must match too.
        return type(value) is type(field.expected) and value == field.expected
    if field.how == "holds":
        return isinstance(value, list) and field.expected in value
    if field.how == "lacks":
        return isinstance(value, list) and field.expected not in value
    if field.how == "names":
        return (
            isinstance(value, str) and isinstance(field.expected, str) and field.expected in value
        )
    raise ValueError(f"unknown comparison {field.how!r}")


class Demo:
    """The scratch directory, the fixture repository in it and the environment every command
    runs under."""

    def __init__(self, scratch: Path, stayfixed: Path, caller_path: str) -> None:
        self.scratch = scratch
        self.repo = scratch / "repo"
        self.home = scratch / "home"
        self.bin = scratch / "bin"
        self.tmp = scratch / "tmp"
        for directory in (self.repo, self.home, self.bin, self.tmp):
            directory.mkdir()
        (self.bin / "stayfixed").symlink_to(stayfixed)
        self.env = {
            "PATH": os.pathsep.join([str(self.bin), caller_path]),
            "HOME": str(self.home),
            "TMPDIR": str(self.tmp),
            "LANG": "C.UTF-8",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_AUTHOR_NAME": IDENTITY,
            "GIT_AUTHOR_EMAIL": EMAIL,
            "GIT_AUTHOR_DATE": DATE,
            "GIT_COMMITTER_NAME": IDENTITY,
            "GIT_COMMITTER_EMAIL": EMAIL,
            "GIT_COMMITTER_DATE": DATE,
            # Claude Code's switch for every request that is not a model call, of which the
            # demo makes none.
            "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
        }

    def which(self, program: str) -> str | None:
        return shutil.which(program, path=self.env["PATH"])

    def run(self, argv: Sequence[str], *, cwd: Path | None = None) -> Ran:
        """Run `argv` in the fixture (or `cwd`) under the act environment, never through a
        shell, and capture what it printed."""
        try:
            # The argv is this script's own, run as typed and never through a shell.
            done = subprocess.run(  # noqa: S603
                list(argv),
                cwd=cwd or self.repo,
                env=self.env,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=COMMAND_TIMEOUT_SECONDS,
                check=False,
            )
        except subprocess.TimeoutExpired as expired:
            raise ActFailed(f"{shlex.join(argv)} ran past {COMMAND_TIMEOUT_SECONDS} s") from expired
        except OSError as error:
            raise ActFailed(f"{shlex.join(argv)} could not start: {error}") from error
        return Ran(done.returncode, done.stdout, done.stderr)

    def git(self, *args: str) -> str:
        """A git command the act needs to set the scene; any failure fails the act."""
        ran = self.run(["git", *args])
        if ran.code != 0:
            raise ActFailed(f"git {shlex.join(args)} exited {ran.code}: {ran.stderr.strip()}")
        return ran.stdout

    def write(self, relative: str, text: str) -> None:
        path = self.repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def stayfixed(self, args: Sequence[str], *, code: int, fields: Sequence[Field]) -> object:
        """Run `stayfixed ARGS` and assert its exit code and every field of its `--json` object.

        Prints the command as typed, the exit code and each field asserted. Returns the object, so
        an act may take a value the product named (a path it wrote) for its next step.
        """
        argv = ["stayfixed", *args]
        print(f"  $ {shlex.join(argv)}")
        ran = self.run(argv)
        problems: list[str] = []
        if ran.code != code:
            problems.append(f"exit: expected {code}, got {ran.code}")
        print(f"  exit {ran.code}")
        try:
            document: object = json.loads(ran.stdout)
        except json.JSONDecodeError:
            document = None
        if not isinstance(document, dict):
            problems.append("stdout is not one JSON object")
        else:
            for field in fields:
                value = _lookup(document, field.path)
                if value is _MISSING:
                    problems.append(
                        f"{field.path}: expected {field.how} "
                        f"{json.dumps(field.expected)}, got no such field"
                    )
                elif _holds(field, value):
                    print(f"  {field.describe()}")
                else:
                    problems.append(
                        f"{field.path}: expected {field.how} "
                        f"{json.dumps(field.expected)}, got {json.dumps(value)}"
                    )
        if problems:
            tail = ran.stderr.strip().splitlines()[-5:]
            raise ActFailed("\n".join(problems + [f"stderr: {line}" for line in tail]))
        return document


def act_proved(demo: Demo) -> None:
    demo.stayfixed(
        ["prove", "--json", "--", "pytest", "-q", "tests/test_total.py"],
        code=0,
        fields=[
            Field("verdict", "proved"),
            Field("counts.passed", 2),
            Field("counts.failed", 0),
        ],
    )


def act_not_recognised(demo: Demo) -> None:
    demo.stayfixed(
        ["prove", "--json", "--", "sh", "-c", 'echo "42 passed"'],
        code=1,
        fields=[Field("verdict", "not proven"), Field("reason", "not-recognised")],
    )


def act_all_skipped(demo: Demo) -> None:
    demo.stayfixed(
        ["prove", "--json", "--", "pytest", "-q", "tests/test_skipped.py"],
        code=1,
        fields=[Field("verdict", "failed"), Field("reason", "all-skipped")],
    )


def act_forging(demo: Demo) -> None:
    demo.stayfixed(
        ["prove", "--json", "--", "PYTHONOPTIMIZE=1", "pytest", "-q", "tests/test_total.py"],
        code=2,
        fields=[
            Field("verdict", "refused"),
            Field("reason", "assigned-forging"),
            Field("detail", "PYTHONOPTIMIZE", "names"),
        ],
    )


ACTS: tuple[tuple[str, Callable[[Demo], None]], ...] = (
    ("a green run is proved, from the runner's own report", act_proved),
    ("text that only looks like a test report proves nothing", act_not_recognised),
    ("a run whose every test was skipped is a failure", act_all_skipped),
    ("a variable that switches assertions off is refused", act_forging),
)


def build_fixture(demo: Demo) -> None:
    demo.git("init", "-q", "-b", "main")
    for relative, text in FIXTURE.items():
        demo.write(relative, text)
    demo.git("add", "-A")
    demo.git("commit", "-q", "-m", "a total and its tests")


def _first_line(ran: Ran) -> str:
    """The first line a `--version` printed, or what it exited with when it printed none."""
    lines = (ran.stdout.strip() or ran.stderr.strip()).splitlines()
    return lines[0] if ran.code == 0 and lines else f"exited {ran.code}"


def _on_signal(signum: int, _frame: FrameType | None) -> None:
    # A SIGTERM or SIGHUP leaves through `main`'s `finally`, as Ctrl-C does, so the scratch
    # directory is removed on that path too.
    raise SystemExit(128 + signum)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the stayfixed demo against STAYFIXED.")
    parser.add_argument("stayfixed", metavar="STAYFIXED", help="the stayfixed program to run")
    parser.add_argument(
        "--require-claude",
        action="store_true",
        help="fail the run when an act is skipped because claude is not on PATH",
    )
    parser.add_argument("--keep", action="store_true", help="keep the scratch directory")
    options = parser.parse_args(argv)

    program = Path(options.stayfixed)
    if not program.is_file() or not os.access(program, os.X_OK):
        print(f"usage error: {program} is not an executable file", file=sys.stderr)
        return 2
    caller_path = os.environ.get("PATH", os.defpath)
    for needed in ("pytest", "git"):
        if shutil.which(needed, path=caller_path) is None:
            print(f"usage error: {needed} is not on PATH", file=sys.stderr)
            return 2

    for signum in (signal.SIGTERM, signal.SIGHUP):
        signal.signal(signum, _on_signal)
    started = time.monotonic()
    scratch = Path(tempfile.mkdtemp(prefix="stayfixed-demo-"))
    try:
        return _run(Demo(scratch, Path(os.path.abspath(program)), caller_path), options, started)
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return 130
    finally:
        if not options.keep:
            shutil.rmtree(scratch, ignore_errors=True)


def _run(demo: Demo, options: argparse.Namespace, started: float) -> int:
    version = demo.run(["stayfixed", "--version"])
    pytest = demo.which("pytest") or ""
    pytest_version = demo.run(["pytest", "--version"])
    print(f"stayfixed: {os.path.realpath(options.stayfixed)}")
    print(f"stayfixed --version: {_first_line(version)}")
    print(f"pytest: {pytest}")
    print(f"pytest --version: {_first_line(pytest_version)}")
    if options.keep:
        print(f"scratch directory, kept: {demo.scratch}")

    try:
        build_fixture(demo)
    except ActFailed as failed:
        print(f"the fixture repository could not be built: {failed}", file=sys.stderr)
        return 1

    passed = skipped = failed_count = 0
    for number, (shows, act) in enumerate(ACTS, start=1):
        print()
        print(f"act {number}: {shows}")
        try:
            act(demo)
        except Skipped as skip:
            skipped += 1
            print(f"act {number} skipped: {skip}")
        except ActFailed as failure:
            failed_count += 1
            for line in str(failure).splitlines():
                print(f"  {line}")
            print(f"act {number} failed")
        else:
            passed += 1
            print(f"act {number} passed")

    elapsed = time.monotonic() - started
    print()
    if skipped and options.require_claude:
        print("--require-claude: an act was skipped, so the run fails")
    print(
        f"{passed} passed, {skipped} skipped, {failed_count} failed"
        f" in {elapsed:.1f} s (goal: {GOAL_SECONDS} s)"
    )
    return 1 if failed_count or (skipped and options.require_claude) else 0


if __name__ == "__main__":
    sys.exit(main())
