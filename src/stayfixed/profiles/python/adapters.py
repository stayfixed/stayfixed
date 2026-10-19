"""Python's runner adapter: a pytest run, proved from the JUnit report pytest writes.

What it recognises is what the red-run hint recognises, one reading (`hygiene.pytest_command`):
pytest's console script (`pytest`, `py.test`), or `python* -m pytest`, either behind `poetry run`;
`uv run` and `uv run -m` the core reads past and hands over as the launch.

**The run.** The command as typed, with `--junitxml=<report> -o junit_family=xunit2` added last
among pytest's options, before a `--` where there is one, the report in the scratch directory
`prove` made. The program is the command's first word, the launcher's where there is one, found
as the shell running the command would find it (`stayfixed.profiles.programs`): the console
script, the interpreter the command names, `poetry` or `uv`, each run by that path. Coming last,
the two options win over the command's own `--junitxml` or `junit_family`, and over an `addopts`
of a configuration file, of `-o addopts=…` or of `PYTEST_ADDOPTS`, which pytest reads first
(measured on pytest 9.1.1: only the adapter's report is written, in its family). The receipt
carries the realpath of what ran.

**What is refused**, each a mistake that has pytest report as passed tests that never ran or
checked nothing; the anchor is the command's own words, and every other option is free.

- `REFUSED_OPTION`: `--setup-plan` (which reports a failing test as passed), `--setup-only`, and
  the undashed aliases pytest registers, `--setupplan` and `--setuponly`; and `--trace`, which
  over a standard input that ends reports a failing test as passed. An option that writes no
  report (`-p no:junitxml`) ends `not proven`, and one that runs no test (`--collect-only`)
  `failed`, by themselves. `--pdb` is free: the run's standard input is `/dev/null`
  (`stayfixed.prove.run`), so its debugger reads the end and quits, pytest exiting 2 with the
  failure in its report.
- `REFUSED_OPTION` for the interpreter's own options too: `-O` (`-OO`, or in a cluster such as
  `-bO`) before `-m pytest`, which compiles out every `assert` pytest does not rewrite (a helper
  module's, or every one under `--assert=plain`), so a failing test reports passed and the run
  exits 0. A `-W` or `-X` value is no flag, and every other interpreter option is free.
- `FORGING`: `PYTHONOPTIMIZE`, which is `-O` and which container images set, where its value
  optimises (`optimises`: any but the empty one and `0`, so `PYTHONOPTIMIZE=0` runs every
  `assert`): assigned in the command, refused; inherited, removed from the run's environment and
  named on the receipt. Every other variable is the project's.

What a file in the tree can do -- a `conftest.py` that moves the report or rewrites it on the way
out, a configuration file's `addopts`, a module that shadows an installed one, a shim on `PATH` --
is the bound's: the receipt names the untracked files pytest collects from (`DISCOVERY`), and the
realpath of the program that ran.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

from stayfixed.profiles.programs import SEPARATOR, before_separator, launched, not_found
from stayfixed.profiles.python.hygiene import pytest_command
from stayfixed.profiles.runners import (
    ENTRY_NOT_FOUND,
    REFUSED_OPTION,
    Plan,
    Refused,
    ReportKind,
    ReportSource,
    Unresolved,
)

NAME = "pytest"
# The reasons this adapter names, both `stayfixed.profiles.runners`': an option the closed list
# refuses, and a program that is not where the command would find it.
REASONS = (REFUSED_OPTION, ENTRY_NOT_FOUND)


def optimises(value: str) -> bool:
    """Whether `PYTHONOPTIMIZE=value` turns `assert` off: any value but the empty one and `0`.
    Another spelling of zero (`00`, `+0`) reads as on, the safe side."""
    return value not in ("", "0")


FORGING: Mapping[str, Callable[[str], bool]] = {"PYTHONOPTIMIZE": optimises}
DISCOVERY = (
    "conftest.py",
    "**/conftest.py",
    "test_*.py",
    "**/test_*.py",
    "*_test.py",
    "**/*_test.py",
)
REPORT_NAME = "junit.xml"

_FAMILY = ("-o", "junit_family=xunit2")

# The closed list of what is refused: the options that run no test and report the tests they set
# up as passed.
_RUNS_NO_TEST = frozenset({"--setup-plan", "--setup-only"})
# The aliases pytest registers beside them, which run as they do.
_RUNS_NO_TEST_ALIASES = frozenset({"--setupplan", "--setuponly"})
# Runs each test under the debugger, which, its standard input ended, lets a failing test report
# as passed and the run exit 0.
_DEBUGS_EACH_TEST = "--trace"
# The interpreter's flag that compiles out every `assert` (`-O`, twice `-OO`), and its two options
# that take a value, fused (`-Wdefault`) or as the next word, an `O` in which is no flag.
_OPTIMIZE = "O"
_VALUED_INTERPRETER_OPTIONS = frozenset({"-W", "-X"})


def refused_option(args: Sequence[str]) -> str | None:
    """The first option of `args`, pytest's arguments, on the closed list, as it is named on the
    receipt; `None` where none is. pytest's parser reads no option after `--`."""
    for word in args:
        if word == SEPARATOR:
            return None
        name = word.partition("=")[0]
        if name in _RUNS_NO_TEST or name in _RUNS_NO_TEST_ALIASES:
            return name
        if word == _DEBUGS_EACH_TEST:
            return word
    return None


def optimizing_option(options: Sequence[str]) -> str | None:
    """The first of the interpreter's own options (`options`, the words before `-m pytest`) that
    turns `assert` off, a word of flags holding `O` (`-O`, `-OO`, `-bO`), as the receipt names it;
    `None` where none does."""
    value = False
    for word in options:
        if value:
            value = False
        elif word in _VALUED_INTERPRETER_OPTIONS:
            value = True
        elif word[:2] in _VALUED_INTERPRETER_OPTIONS:
            continue
        elif word.startswith("-") and _OPTIMIZE in word[1:]:
            return word
    return None


class PytestAdapter:
    """`RunnerAdapter` for pytest."""

    @property
    def name(self) -> str:
        return NAME

    @property
    def forging(self) -> Mapping[str, Callable[[str], bool]]:
        return FORGING

    def recognises(self, command: Sequence[str]) -> bool:
        return pytest_command(command) is not None

    def plan(
        self,
        launch: Sequence[str],
        command: Sequence[str],
        *,
        cwd: Path,
        scratch: Path,
        environ: Mapping[str, str],
    ) -> Plan | Refused | Unresolved:
        run = pytest_command(command)
        if run is None:
            return Unresolved(ENTRY_NOT_FOUND)
        refused = refused_option(run.args) or optimizing_option(run.options)
        if refused is not None:
            return Refused(REFUSED_OPTION, refused)
        report = scratch / REPORT_NAME
        # pytest's arguments are the command's last words, and every word before them runs as
        # it was typed.
        typed = tuple(command[: len(command) - len(run.args)])
        ours = (f"--junitxml={report}", *_FAMILY)
        argv = launched(launch, (*typed, *before_separator(run.args, ours)), cwd, environ)
        if argv is None:
            return Unresolved(ENTRY_NOT_FOUND, not_found((*launch, *command)[0]))
        return Plan(
            argv=argv,
            kind=ReportKind.JUNIT,
            source=ReportSource.FILE,
            report=report,
            discovery=DISCOVERY,
        )


ADAPTERS = (PytestAdapter(),)
