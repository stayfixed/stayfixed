"""Python's runner adapter: a pytest run, proved from the JUnit report pytest writes, with the
project's environment kept.

What it recognises is what the red-run hint recognises, one reading (`hygiene.pytest_command`):
pytest's console script (`pytest`, `py.test`), or `python* -m pytest`, either behind `poetry run`;
`uv run` the core reads past and hands over as the launch.

**The run.** Never the console script: `<interpreter> [its options] -c <bootstrap> <args>
--junitxml=<report> -o junit_family=xunit2`, the report in the scratch directory `prove` made. The
run directory never shadows an installed module: the bootstrap takes it off the front of the
import path before anything is imported, so a `pytest.py` planted at the root is never what is
imported, and runs pytest as `-m pytest` would; for `python -m pytest`, which puts the run
directory first, it puts it back last, after the installed packages, so the project's own
packages import from it as they would. `-I` would also ignore every `PYTHON*` variable and the
user's site-packages, which are the project's (`PYTHONWARNINGS`, `PYTHONHASHSEED`, `PYTHONPATH`),
and `-P` is unknown to Python 3.10 and older and keeps the run directory off the path whole. The
interpreter is the one the
console script's first line names (`#!<python>`, `#!/usr/bin/env python3`, or an installer's
`#!/bin/sh` trampoline whose second line `exec`s `<python>`), by the path the line names it: a
virtual environment's `bin/python` is a link, and the interpreter it points at, run by its own
path, runs outside the environment. A script whose first line names no interpreter (a pyenv, asdf
or Nix shim) runs as `python3`, else `python`, on `PATH`; a `python*` the command names is found on
`PATH`. Under `uv run` or `poetry run` the launcher runs, kept in front, and its interpreter is its
choice. The receipt carries the realpath of what ran.

**Every control here, with its adversary and its anchor.**

- `REFUSED_OPTION`: an agent typing an option that moves, replaces or suppresses the report, or
  makes pytest report tests it never ran: `--junitxml`/`--junit-xml`, `-p no:junitxml`, `-o` or
  `--override-ini` setting a `junit_*` key or `addopts` (whose options pytest reads as typed),
  `--setup-plan` (which reports a failing test as passed), `--setup-only`, `--collect-only`,
  `--co`, and the undashed aliases pytest registers, `--setupplan`, `--setuponly` and
  `--collectonly`; `--trace`, which over a standard input that ends reports a failing test as
  passed; and an `@file` word, whose options pytest reads from that file, never read here. The
  anchor is the command's own words; the list is closed, every option pytest 9.1.1 registers was
  run over a failing test to draw it, and every other option is free. `--pdb` is among them: the
  run's standard input is `/dev/null` (`stayfixed.prove.run`), so its debugger reads the end and
  quits, pytest exiting 2 with the failure in its report.
- `REFUSED_OPTION` for the interpreter's own options too: an agent typing `-O` (`-OO`, or in a
  cluster such as `-bO`) before `-m pytest`, which compiles out every `assert` pytest does not
  rewrite (a helper module's, or every one under `--assert=plain`), so a failing test reports
  passed and the run exits 0. The anchor is the command's own words; a `-W` or `-X` value is no
  flag, and every other interpreter option is free.
- `FORGING`, assigned in the command (refused) or inherited (scrubbed): the same agent steering
  the report through the two variables pytest reads its options and plugins from, and through
  `PYTHONOPTIMIZE`, which is `-O`. `PYTHONPATH` and every other variable are the project's.
- The bootstrap: a module named `pytest` (or `runpy`, which it imports) in the directory the
  command runs in, which the agent can write. The anchor is the argv stayfixed runs. A module the
  project's own `PYTHONPATH` reaches is the bound's, since `PYTHONPATH` is the project's, and so
  is a package of the run directory's that `python -m pytest`'s tests import, which comes after
  every installed one.
- The file `-c`/`--config-file` (or the older `--inifile`) names: the same agent pointing pytest
  at a configuration of its choosing. Not refused, since a configuration file is the bound's as
  `pytest.ini` is, but named among the receipt's configuration files by its realpath
  (`Plan.configs`), wherever it lies; the anchor is the command's own words.

What a file in the tree can do -- a `conftest.py` that moves the report or rewrites it on the way
out, a configuration file's `addopts`, a shim on `PATH`, the interpreter a script's first line
names -- is the bound's: the receipt names the configuration files (`CONFIGS`) and the untracked
files pytest collects from (`DISCOVERY`), and the realpath of the program that ran.
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping, Sequence
from pathlib import Path

from stayfixed import fsops
from stayfixed.profiles.python.hygiene import PytestCommand, pytest_command
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
FORGING = frozenset({"PYTEST_ADDOPTS", "PYTEST_PLUGINS", "PYTHONOPTIMIZE"})
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

# What the interpreter runs in place of `-m pytest`: `-c` and a bootstrap that takes the run
# directory off the front of the import path, where `-c` put it, before anything is imported from
# there, then runs pytest as `-m` would, `sys.argv` and `__main__` as `-m pytest` sets them. Where
# the command spelled `python -m pytest`, which puts the run directory first, it is put back last,
# after the installed packages, so the project's own packages still import from it and none of them
# shadows an installed one. Where the interpreter put nothing there (`-P`, `-I`, `PYTHONSAFEPATH`),
# nothing is taken or put back. Every interpreter `prove` may run, any Python 3, reads it: no `-P`,
# which Python 3.10 and older do not know.
_BOOTSTRAP = (
    "import sys\n"
    "if sys.path and sys.path[0] == '':\n"
    "    del sys.path[0]\n"
    "{put_back}"
    "import runpy\n"
    "runpy.run_module('pytest', run_name='__main__', alter_sys=True)\n"
)
SCRIPT_BOOTSTRAP = _BOOTSTRAP.format(put_back="")
MODULE_BOOTSTRAP = _BOOTSTRAP.format(put_back="    import os\n    sys.path.append(os.getcwd())\n")
_RUN_TEXT = "-c"
_FAMILY = ("-o", "junit_family=xunit2")
_SEPARATOR = "--"
_INTERPRETERS = ("python3", "python")
# What an unresolved plan's detail says was looked for.
_NOT_ON_PATH = "no {program} on PATH"
# What the program a `#!` line names is called, where it is an interpreter.
_INTERPRETER_PREFIX = "python"
# Under a launcher, the interpreter it chooses.
_LAUNCHED_INTERPRETER = "python"

# The closed list of what is refused.
_REPORT_OPTIONS = frozenset({"--junitxml", "--junit-xml"})
_RUNS_NO_TEST = frozenset({"--setup-plan", "--setup-only", "--collect-only", "--co"})
# The aliases pytest registers beside them, which run as they do.
_RUNS_NO_TEST_ALIASES = frozenset({"--setupplan", "--setuponly", "--collectonly"})
# Runs each test under the debugger, which, its standard input ended, lets a failing test report
# as passed and the run exit 0.
_DEBUGS_EACH_TEST = "--trace"
# A word pytest's parser reads more words from, the file it names (`@args.txt`).
_FROM_FILE = "@"
_OVERRIDE_INI = "--override-ini"
_JUNIT_KEY = "junit_"
_ADDOPTS = "addopts"
# The options that name the configuration file pytest reads, its short one `-c`.
_CONFIG_OPTIONS = frozenset({"--config-file", "--inifile"})
_CONFIG_LETTER = "c"
_PLUGIN = "-p"
_NO_REPORT = "no:junitxml"
# pytest's own short options that take no value, which its parser lets stand in one word before
# one that takes a value (`-qo junit_family=x`, `-qc ci.ini`): a cluster is read up to the first
# letter outside them, which takes the rest of the word, or the next word, as its value.
_PYTEST_FLAGS = frozenset("hlqsvVx")
_INI_LETTER = "o"

# The interpreter's flag that compiles out every `assert` (`-O`, twice `-OO`), and its two options
# that take a value, fused (`-Wdefault`) or as the next word, an `O` in which is no flag.
_OPTIMIZE = "O"
_VALUED_INTERPRETER_OPTIONS = frozenset({"-W", "-X"})

# How much of a console script is read for the interpreter its first two lines name.
_SCRIPT_HEAD_BYTES = 4096
# The installer's trampoline for an interpreter path too long for a `#!` line, quoted either way.
_TRAMPOLINE = re.compile(r"""'''exec' (['"])(?P<python>.+?)\1 "\$0" "\$@"\s*""")


def _ini(option: str, value: str | None) -> str | None:
    """`option` and the key `value` sets, where it sets a `junit_*` key or `addopts`."""
    if value is None:
        return None
    key = value.partition("=")[0]
    if not key.startswith(_JUNIT_KEY) and key != _ADDOPTS:
        return None
    return f"{option} {key}"


def _short(word: str, following: str | None) -> tuple[str, str | None] | None:
    """The short option a single-dash word (`-o`, `-ojunit_x=1`, `-qo`, `-c=x`) ends in after
    pytest's flags, and its value: the rest of the word past one `=`, or else the next word;
    `None` where the word is flags alone."""
    for index, letter in enumerate(word[1:], start=1):
        if letter in _PYTEST_FLAGS:
            continue
        rest = word[index + 1 :]
        return letter, rest.removeprefix("=") if rest else following
    return None


def _single_dash(word: str) -> bool:
    return word.startswith("-") and not word.startswith(_SEPARATOR)


def refused_option(args: Sequence[str]) -> str | None:
    """The first option of `args`, pytest's arguments, on the closed list, as it is named on the
    receipt; `None` where none is."""
    # pytest reads `-p` in every word, before it parses any and past a `--`, its value stripped.
    for index, word in enumerate(args):
        if word == _PLUGIN:
            plugin = args[index + 1] if index + 1 < len(args) else ""
        elif word.startswith(_PLUGIN):
            plugin = word[len(_PLUGIN) :]
        else:
            continue
        if plugin.strip() == _NO_REPORT:
            return f"{_PLUGIN} {_NO_REPORT}"
    # Every other option is the parser's, which reads none after `--`.
    for index, word in enumerate(args):
        if word == _SEPARATOR:
            return None
        following = args[index + 1] if index + 1 < len(args) else None
        name, equals, value = word.partition("=")
        if name in _REPORT_OPTIONS or name in _RUNS_NO_TEST or name in _RUNS_NO_TEST_ALIASES:
            return name
        if word == _DEBUGS_EACH_TEST or word.startswith(_FROM_FILE):
            return word
        named = None
        if name == _OVERRIDE_INI:
            named = _ini(name, value if equals else following)
        elif _single_dash(word) and (short := _short(word, following)) is not None:
            letter, setting = short
            named = _ini(f"-{letter}", setting) if letter == _INI_LETTER else None
        if named is not None:
            return named
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
        if word == _SEPARATOR:
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


def _executable(path: Path) -> bool:
    try:
        return fsops.is_file(path) and os.access(path, os.X_OK)
    except OSError:
        return False


def _found(word: str, cwd: Path, path: str) -> Path | None:
    """The executable `word` names from `cwd`: a path, read from `cwd`; a bare name, the first on
    `path`, a relative entry read from `cwd` too, as the run itself would read it."""
    if os.sep in word:
        candidates = [cwd / word]
    else:
        candidates = [cwd / directory / word for directory in path.split(os.pathsep)]
    return next((candidate for candidate in candidates if _executable(candidate)), None)


def _named_interpreter(script: Path, cwd: Path, path: str) -> Path | None:
    """The interpreter the console script's first line names, or its second where the first is
    the installer's `#!/bin/sh`; `None` where neither names one."""
    try:
        head, _ = fsops.read_bounded(script, _SCRIPT_HEAD_BYTES)
    except OSError:
        return None
    first, _, rest = head.partition(b"\n")
    if not first.startswith(b"#!"):
        return None
    words = os.fsdecode(first[2:]).split()
    program = Path(words[0]).name if words else ""
    if program.startswith(_INTERPRETER_PREFIX):
        return cwd / words[0]
    if program == "env" and len(words) > 1 and words[1].startswith(_INTERPRETER_PREFIX):
        return _found(words[1], cwd, path)
    trampoline = _TRAMPOLINE.fullmatch(os.fsdecode(rest.partition(b"\n")[0]))
    if program == "sh" and trampoline is not None:
        return cwd / trampoline["python"]
    return None


def _interpreter(script: Path, cwd: Path, path: str) -> Path | None:
    """What runs `-m pytest` for the console script `script`: the interpreter it names, else
    `python3`, else `python`, on `path`."""
    named = _named_interpreter(script, cwd, path)
    if named is not None:
        return named
    return next(
        (found for name in _INTERPRETERS if (found := _found(name, cwd, path)) is not None), None
    )


def _with_report(args: Sequence[str], report: Path) -> tuple[str, ...]:
    """pytest's arguments with the report's options added last, before a `--` where there is
    one, since pytest reads every word after it as a path to collect."""
    ours = (f"--junitxml={report}", *_FAMILY)
    cut = args.index(_SEPARATOR) if _SEPARATOR in args else len(args)
    return (*args[:cut], *ours, *args[cut:])


def _argv(
    launch: Sequence[str], run: PytestCommand, cwd: Path, path: str, module: tuple[str, ...]
) -> tuple[Path, tuple[str, ...]] | str:
    """The program and the argv that run `module` (`… -c <bootstrap> …`), or, where the program
    is not where the command would find it, what was looked for, for the receipt."""
    front = tuple(launch) or run.launcher
    if front:
        launcher = _found(front[0], cwd, path)
        if launcher is None:
            return _NOT_ON_PATH.format(program=front[0])
        words = (*launch[1:], *run.launcher) if launch else run.launcher[1:]
        chosen = run.program if run.module else _LAUNCHED_INTERPRETER
        return launcher, (str(launcher), *words, chosen, *module)
    found = _found(run.program, cwd, path)
    if found is None:
        return _NOT_ON_PATH.format(program=run.program)
    python = found if run.module else _interpreter(found, cwd, path)
    if python is None:
        return _NOT_ON_PATH.format(program=" or ".join(_INTERPRETERS))
    return python, (str(python), *module)


class PytestAdapter:
    """`RunnerAdapter` for pytest."""

    @property
    def name(self) -> str:
        return NAME

    @property
    def forging(self) -> frozenset[str]:
        return FORGING

    def recognises(self, command: Sequence[str]) -> bool:
        return pytest_command(command) is not None

    def plan(
        self,
        launch: Sequence[str],
        command: Sequence[str],
        *,
        cwd: Path,
        root: Path,
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
        bootstrap = MODULE_BOOTSTRAP if run.module else SCRIPT_BOOTSTRAP
        module = (*run.options, _RUN_TEXT, bootstrap, *_with_report(run.args, report))
        resolved = _argv(launch, run, cwd, environ.get("PATH", os.defpath), module)
        if isinstance(resolved, str):
            return Unresolved(ENTRY_NOT_FOUND, resolved)
        program, argv = resolved
        return Plan(
            argv=argv,
            program=Path(os.path.realpath(program)),
            kind=ReportKind.JUNIT,
            source=ReportSource.FILE,
            report=report,
            set_env={},
            scrub=FORGING,
            discovery=DISCOVERY,
            configs=(*CONFIGS, *_configuration_files(run.args, cwd)),
        )


ADAPTERS = (PytestAdapter(),)
