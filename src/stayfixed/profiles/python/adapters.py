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
  optimises as CPython reads it (`optimises`: any but the empty one and a zero, so
  `PYTHONOPTIMIZE=0` runs every `assert`): assigned in the command, refused; inherited, removed
  from the run's environment and named on the receipt. Every other variable is the project's.
- The file `-c`/`--config-file` (or the older `--inifile`) names is not refused, since a
  configuration file is the bound's as `pytest.ini` is, but named among the receipt's
  configuration files by its realpath (`Plan.configs`), wherever it lies.

What a file in the tree can do -- a `conftest.py` that moves the report or rewrites it on the way
out, a configuration file's `addopts`, a module that shadows an installed one, a shim on `PATH` --
is the bound's: the receipt names the configuration files (`CONFIGS`) and the untracked files
pytest collects from (`DISCOVERY`), and the realpath of the program that ran.
"""

from __future__ import annotations

import os
import re
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
# What CPython reads as no optimisation in `PYTHONOPTIMIZE`, past the empty value, which it reads
# as unset: a value `strtol` reads whole as zero, after leading white space and a sign (measured on
# 3.14.7: `0`, `00`, ` 0`, `+0`, `-0` are level 0; `0 `, `0_0`, `abc`, `-1` are level 1).
_ZERO = re.compile(r"[ \t\n\v\f\r]*[+-]?0+")


def optimises(value: str) -> bool:
    """Whether `PYTHONOPTIMIZE=value` turns `assert` off, as CPython reads it: any value but the
    empty one and one that reads as zero."""
    return bool(value) and _ZERO.fullmatch(value) is None


FORGING: Mapping[str, Callable[[str], bool]] = {"PYTHONOPTIMIZE": optimises}
DISCOVERY = (
    "conftest.py",
    "**/conftest.py",
    "test_*.py",
    "**/test_*.py",
    "*_test.py",
    "**/*_test.py",
)
CONFIGS = ("pytest.ini", "pyproject.toml", "setup.cfg", "tox.ini")
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
# The options that name the configuration file pytest reads, its short one `-c`.
_CONFIG_OPTIONS = frozenset({"--config-file", "--inifile"})
_CONFIG_LETTER = "c"
# pytest's own short options that take no value, which its parser lets stand in one word before
# one that takes a value (`-qc ci.ini`): a cluster is read up to the first letter outside them,
# which takes the rest of the word, or the next word, as its value.
_PYTEST_FLAGS = frozenset("hlqsvVx")

# The interpreter's flag that compiles out every `assert` (`-O`, twice `-OO`), and its two options
# that take a value, fused (`-Wdefault`) or as the next word, an `O` in which is no flag.
_OPTIMIZE = "O"
_VALUED_INTERPRETER_OPTIONS = frozenset({"-W", "-X"})


def _short(word: str, following: str | None) -> tuple[str, str | None] | None:
    """The short option a single-dash word (`-c`, `-cci.ini`, `-qc`, `-c=x`) ends in after
    pytest's flags, and its value: the rest of the word past one `=`, or else the next word;
    `None` where the word is flags alone."""
    for index, letter in enumerate(word[1:], start=1):
        if letter in _PYTEST_FLAGS:
            continue
        rest = word[index + 1 :]
        return letter, rest.removeprefix("=") if rest else following
    return None


def _single_dash(word: str) -> bool:
    return word.startswith("-") and not word.startswith(SEPARATOR)


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


def _configuration_files(args: Sequence[str], cwd: Path) -> tuple[str, ...]:
    """The realpath of each file `-c`, `--config-file` or `--inifile` names in `args`, read from
    `cwd`: an absolute entry of `Plan.configs`, which names that file wherever it lies."""
    found: list[str] = []
    for index, word in enumerate(args):
        if word == SEPARATOR:
            break
        following = args[index + 1] if index + 1 < len(args) else None
        name, equals, value = word.partition("=")
        named: str | None = None
        if name in _CONFIG_OPTIONS:
            named = value if equals else following
        elif _single_dash(word) and (short := _short(word, following)) is not None:
            letter, setting = short
            named = setting if letter == _CONFIG_LETTER else None
        if named:
            found.append(os.path.realpath(cwd / named))
    return tuple(found)


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
            configs=(*CONFIGS, *_configuration_files(run.args, cwd)),
        )


ADAPTERS = (PytestAdapter(),)
