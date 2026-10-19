"""JavaScript's runner adapters: a jest, vitest or `node --test` run, proved from the report the
runner writes to a file `prove` hands it, run as the command typed it.

**What is recognised.** `jest` and `vitest`, bare or after `npx` or `npx --no-install` (not `npx
--no`: npm reads the runner's options after it as its own, so the report's never reach the runner);
a path to one as the command's first word (`./node_modules/.bin/jest`); `node [node's options]
<entry> …`, the entry a path into `node_modules/<package>` or `node_modules/.bin/<runner>`
(`node_entry`); and `node` (or a path to one) with `--test` among its options. `npm test`, `npm
run`, `yarn`, `pnpm` and every other package manager's script runner are recognised by none of
them: what a script runs is the script's, never read here, and `prove --junit` counts its report.

**The run is the command as typed** (`stayfixed.profiles.programs.launched`): its first word found
as a shell finds it, every other word as typed, and the report's options in their place, below.
Behind a launcher the core read past (`uv run …`), the launcher is found and the command's words are
handed to it as typed. `npx` runs as it does outside `prove`, and given a runner no `node_modules`
holds it installs one without asking, since the run's standard input is no terminal. A first word
that names nothing there is `ENTRY_NOT_FOUND`; a file `node` is handed that is not the runner's
entry writes no report, and the run is `not proven`.

**Node's options** are read with no table of node's (`_node_read`): a word starting with `-` is an
option, and the word after one that gives itself no value with `=` may be that option's value. A
command whose node options name `--test` is `node --test`'s.

**The report.** jest: `--json --outputFile=<report>`. vitest: `run` first where the command's first
word is none of vitest's subcommands, so it runs once; `related` kept, with `--run` where the
command does not set it; `watch` and `dev` are `NEVER_ENDS`, and `bench`, `list`, `init` and
`doctor`, which run no test suite that reports, `NO_TEST_RUN` (`vitest_unplanned`); then
`--reporter=json --outputFile=<report>`, and `--reporter=default` where the command names no
reporter of its own. `node --test`: `--test-reporter=junit --test-reporter-destination=<report>
--test-reporter=spec --test-reporter-destination=stdout`, right after `node`. Each is added before a
`--`, which ends the options. node writes one testcase for a whole file that ran no test, named by
the file's path from the directory node runs in, `classname` `test`, and passed: `drop`
(`whole_file`) leaves it out, unless it carries a failure, which counts as failed.

**What is refused** (`REFUSED_OPTION`, naming the option): only what a person or an agent could
type by mistake and get a green report for tests that never ran or never checked anything. Each is
read in its documented spelling alone, or as `--option=value` (`_spelled`); every other option is
free.

- jest: `-u`/`--updateSnapshot` (rewrites a failing snapshot so that it passes) and
  `--collectTests` (exits 0 reporting a failing test as passed).
- vitest: `-u`/`--update` but `--update=none` and `--update=new` (each other value rewrites a
  failing snapshot so that it passes; `new` only writes a missing one); the same values of
  `UPDATE_SNAPSHOT`, which vitest reads as `--update` (`FORGING`); `--mergeReports` (runs nothing
  and reports an earlier run's blob files as results); and `--dangerouslyIgnoreUnhandledErrors`
  (exits 0 past an error no test reported).
- `node --test`: `--test-update-snapshots` and `--test-rerun-failures` (reports as passed, unrun,
  every test its state file says passed before), on the command line or among the run's
  `NODE_OPTIONS` words.

A watch mode -- jest's `--watch` and `--watchAll`, vitest's `-w`/`--watch`, node's `--watch` and
`--watch-path` -- never ends, and nor do node's `--inspect-brk` and `--inspect-wait`, on the command
line or in `NODE_OPTIONS`: each is `NEVER_ENDS` (`not proven`), naming the option, and a refusal in
the same command wins.

What the environment and a file in the tree can do -- a preload, a configuration's reporters,
`testResultsProcessor` or setup files, a test that writes the report -- is the bound's.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from stayfixed import fsops
from stayfixed.profiles.programs import (
    SEPARATOR,
    before_separator,
    launched,
    not_found,
    options,
)
from stayfixed.profiles.runners import (
    ENTRY_NOT_FOUND,
    NEVER_ENDS,
    REFUSED_OPTION,
    Plan,
    Refused,
    ReportKind,
    ReportSource,
    Unresolved,
)

JEST = "jest"
VITEST = "vitest"
NODE_TEST = "node-test"
# The detail of a watch mode's reason, `NEVER_ENDS`, which names the option.
# Short enough for the receipt's line to carry whole beside the longest option it names
# (`printed.CLIPPED_CHARS`).
NEVER_ENDS_DETAIL = (
    "{option} watches for changes and never ends, so no report is ever finished; "
    "prove one run without it"
)
# The same reason's detail for node's options that hold the code until a debugger attaches.
WAITS_DETAIL = (
    "{option} waits for a debugger to attach, so no report is ever finished; "
    "prove one run without it"
)
# The reason a vitest subcommand that runs no test suite is not proven, and its detail.
NO_TEST_RUN = "no-test-run"
# The reasons these adapters name: `stayfixed.profiles.runners`' three (an option a closed list
# refuses, an entry point that does not resolve from where the command runs, a watch mode), and
# their own, a vitest subcommand that runs no test suite.
REASONS = (REFUSED_OPTION, ENTRY_NOT_FOUND, NEVER_ENDS, NO_TEST_RUN)
NO_TEST_RUN_DETAIL = (
    "vitest {subcommand} runs no test suite that reports; prove `vitest run` instead"
)
# Each runner's default test files, as `stayfixed.prove.tree` matches a glob, from the right.
JEST_DISCOVERY = ("*.test.*", "*.spec.*", "__tests__/*")
VITEST_DISCOVERY = ("*.test.*", "*.spec.*")
NODE_DISCOVERY = ("*.test.*", "*-test.*", "*_test.*", "test-*.*", "test.*", "test/*")
JEST_REPORT = "jest.json"
VITEST_REPORT = "vitest.json"
NODE_REPORT = "junit.xml"

_NPX = "npx"
# The `npx` option that installs nothing, the only one read before the runner's name.
_NPX_NO_INSTALL = "--no-install"
_NODE = "node"
_MODULES = "node_modules"
_BIN_LINKS = ".bin"
_TEST = "--test"
_RUN = "run"
# vitest's subcommands, which its parser reads in the first positional word: `run` runs once;
# `related` runs the tests that import the files it names, once under `--run`; `watch` and `dev`
# watch; `bench`, `list`, `init` and `doctor` run no test suite that reports.
_VITEST_RELATED = "related"
_VITEST_WATCHING = frozenset({"watch", "dev"})
_VITEST_NO_TEST_RUN = frozenset({"bench", "list", "init", "doctor"})
_VITEST_SUBCOMMANDS = frozenset({_RUN, _VITEST_RELATED, *_VITEST_WATCHING, *_VITEST_NO_TEST_RUN})

# Where the runner the command names bare is on no `PATH` entry, so nothing the command names can
# run. Short enough for the receipt's line to carry whole (`printed.CLIPPED_CHARS`).
UNRESOLVED = (
    "no {bin} on PATH; `npx {bin}` runs a project's own, or `prove --junit` counts a report"
)


def _launched(
    launch: Sequence[str],
    argv: tuple[str, ...],
    cwd: Path,
    environ: Mapping[str, str],
    missing: str | None = None,
) -> tuple[str, ...] | Unresolved:
    """The argv that runs `argv` as typed behind `launch` (`stayfixed.profiles.programs.launched`).
    `ENTRY_NOT_FOUND` where its first word names nothing there, `missing` its detail where given,
    else what was looked for (`stayfixed.profiles.programs.not_found`)."""
    planned = launched(launch, argv, cwd, environ)
    if planned is None:
        return Unresolved(ENTRY_NOT_FOUND, missing or not_found((*launch, *argv)[0]))
    return planned


# The values that turn a boolean option off, given as `--option=value`.
_OFF = frozenset({"false"})


def _spelled(words: Sequence[str], names: frozenset[str], off: frozenset[str] = _OFF) -> str | None:
    """The first of `names` among `words` before a `--`, spelled exactly or as `name=value` with a
    value outside `off`; `None` where none is. No other spelling is read: a cluster of short
    options (`-cu`), a value given as the next word, or a kebab-case form is the bound's."""
    for word in options(words):
        name, equals, value = word.partition("=")
        if name in names and not (equals and value in off):
            return name
    return None


@dataclass(frozen=True)
class _Runner:
    """What tells jest's and vitest's plans apart: the runner's name, the packages that ship it,
    the variables that forge its report, its report, its closed list and how its report options
    read."""

    name: str
    packages: tuple[str, ...]
    forging: Mapping[str, Callable[[str], bool]]
    discovery: tuple[str, ...]
    report_name: str
    refused: Callable[[Sequence[str]], str | None]
    never_ends: Callable[[Sequence[str]], str | None]
    unplanned: Callable[[Sequence[str]], Unresolved | None]
    ours: Callable[[Sequence[str], Path], tuple[str, ...]]
    words: Callable[[Sequence[str]], tuple[str, ...]]


def runner_args(command: Sequence[str], name: str) -> tuple[str, ...] | None:
    """The words after the runner's name in `command`, where `command` is `name` bare or after
    `npx` or `npx --no-install`; else `None`. A path to the runner is `linked_args`'."""
    words = list(command)
    if words[:1] == [_NPX]:
        words = words[1:]
        if words[:1] == [_NPX_NO_INSTALL]:
            words = words[1:]
    if words[:1] != [name]:
        return None
    return tuple(words[1:])


def linked_args(command: Sequence[str], name: str) -> tuple[str, ...] | None:
    """The words after the first in `command`, where the first is a path to the runner `name`
    (`./node_modules/.bin/jest`), which the plan runs as typed; else `None`."""
    if not command or os.sep not in command[0] or Path(command[0]).name != name:
        return None
    return tuple(command[1:])


# jest's closed list, and its watch modes, which never end.
_JEST_REFUSED = frozenset({"-u", "--updateSnapshot", "--collectTests"})
_JEST_NEVER_ENDS = frozenset({"--watch", "--watchAll"})


def jest_refused(args: Sequence[str]) -> str | None:
    """The first option of jest's `args` on its closed list; `None` where none is."""
    return _spelled(args, _JEST_REFUSED)


def jest_never_ends(args: Sequence[str]) -> str | None:
    """The first of jest's watch modes among `args`; `None` where none is."""
    return _spelled(args, _JEST_NEVER_ENDS)


# vitest's closed list: `--update` but for the values that rewrite no failing snapshot, `none`
# and `new` (which writes a missing one); and two options refused in any spelling.
_VITEST_SNAPSHOTS = frozenset({"-u", "--update"})
_VITEST_KEEPS_SNAPSHOTS = frozenset({"none", "new"})
_VITEST_REFUSED = frozenset({"--mergeReports", "--dangerouslyIgnoreUnhandledErrors"})
_VITEST_NEVER_ENDS = frozenset({"-w", "--watch"})
# The variable vitest reads as `--update` where the command gives none; its empty value is unset.
_VITEST_UPDATE_VARIABLE = "UPDATE_SNAPSHOT"


def snapshots_rewritten(value: str) -> bool:
    """Whether vitest, given `UPDATE_SNAPSHOT=value`, rewrites a failing snapshot."""
    return value not in ("", *_VITEST_KEEPS_SNAPSHOTS)


def vitest_refused(args: Sequence[str]) -> str | None:
    """The first option of vitest's `args` on its closed list; `None` where none is."""
    return _spelled(args, _VITEST_REFUSED) or _spelled(
        args, _VITEST_SNAPSHOTS, _VITEST_KEEPS_SNAPSHOTS
    )


def vitest_never_ends(args: Sequence[str]) -> str | None:
    """`-w` or `--watch` among vitest's `args`; `None` where neither is."""
    return _spelled(args, _VITEST_NEVER_ENDS)


def _jest_ours(args: Sequence[str], report: Path) -> tuple[str, ...]:
    return ("--json", f"--outputFile={report}")


def _vitest_ours(args: Sequence[str], report: Path) -> tuple[str, ...]:
    ours: tuple[str, ...] = ("--reporter=json", f"--outputFile={report}")
    if _spelled(args, frozenset({"--reporter"}), frozenset()) is None:
        ours = (*ours, "--reporter=default")
    # `related` runs once under `--run`; vitest refuses a second setting of it before any run.
    if args[:1] == (_VITEST_RELATED,) and _spelled(args, frozenset({"--run"})) is None:
        ours = ("--run", *ours)
    return ours


def _jest_words(args: Sequence[str]) -> tuple[str, ...]:
    return tuple(args)


def _vitest_words(args: Sequence[str]) -> tuple[str, ...]:
    """vitest's arguments, `run` first where the first word is no subcommand of vitest's, so that
    it runs once and never watches; a subcommand stays its own (`related` gets `--run`,
    `_vitest_ours`)."""
    return tuple(args) if args[:1] and args[0] in _VITEST_SUBCOMMANDS else (_RUN, *args)


def _jest_unplanned(args: Sequence[str]) -> Unresolved | None:
    return None


def vitest_unplanned(args: Sequence[str]) -> Unresolved | None:
    """Why vitest's subcommand in the first word of `args` cannot be proved: a watching one never
    ends (`NEVER_ENDS`), and one that runs no test suite has no report (`NO_TEST_RUN`); `None`
    for `run`, `related` and a first word that is no subcommand."""
    first = args[0] if args else None
    if first in _VITEST_WATCHING:
        return Unresolved(NEVER_ENDS, NEVER_ENDS_DETAIL.format(option=f"vitest {first}"))
    if first in _VITEST_NO_TEST_RUN:
        return Unresolved(NO_TEST_RUN, NO_TEST_RUN_DETAIL.format(subcommand=first))
    return None


_JEST = _Runner(
    name=JEST,
    packages=("jest", "jest-cli"),
    forging={},
    discovery=JEST_DISCOVERY,
    report_name=JEST_REPORT,
    refused=jest_refused,
    never_ends=jest_never_ends,
    unplanned=_jest_unplanned,
    ours=_jest_ours,
    words=_jest_words,
)
_VITEST = _Runner(
    name=VITEST,
    packages=("vitest",),
    forging={_VITEST_UPDATE_VARIABLE: snapshots_rewritten},
    discovery=VITEST_DISCOVERY,
    report_name=VITEST_REPORT,
    refused=vitest_refused,
    never_ends=vitest_never_ends,
    unplanned=vitest_unplanned,
    ours=_vitest_ours,
    words=_vitest_words,
)


def _option(word: str) -> bool:
    """Whether `word` is an option to node: it starts with `-`, and is neither `-` (standard
    input as the script) nor a `--`."""
    return word.startswith("-") and word not in ("-", SEPARATOR)


def _node_read(words: Sequence[str]) -> tuple[list[str], list[int]]:
    """node's own options at the start of `words` (the words after `node`), and the index of each
    word among them that node may run as its script, read with no table of node's options: a word
    starting with `-` is an option, and a word after one that gives itself no value with `=` may
    be that option's value or the script. The reading ends at the first word that can only be the
    script, or a `--`."""
    options: list[str] = []
    scripts: list[int] = []
    for index, word in enumerate(words):
        if word == SEPARATOR:
            break
        if _option(word):
            options.append(word)
            continue
        scripts.append(index)
        before = words[index - 1] if index else None
        if before is None or not _option(before) or "=" in before:
            break
    return options, scripts


def node_options(words: Sequence[str]) -> list[str]:
    """node's own options in `words` (the words after `node`), as `_node_read` reads them."""
    return _node_read(words)[0]


def _entry_shaped(script: str, name: str, packages: Sequence[str]) -> bool:
    """Whether `script` is a path into `node_modules/<package>` (a package of `packages`) or
    `node_modules/.bin/<name>`."""
    parts = Path(script).parts
    for at, part in enumerate(parts[:-1]):
        if part != _MODULES:
            continue
        after = parts[at + 1 :]
        if (after[0] in packages and len(after) > 1) or after == (_BIN_LINKS, name):
            return True
    return False


def node_entry(
    command: Sequence[str], name: str, packages: Sequence[str]
) -> tuple[tuple[str, ...], tuple[str, ...]] | None:
    """`command` read as `node [node's options] <entry> [the runner's arguments]`: the words up to
    and including the entry, and the runner's arguments, the entry the first word node may run as
    its script (`_node_read`) that is a path into `node_modules/<package>` (a package of
    `packages`) or `node_modules/.bin/<name>`; `None` for any other command, and for one whose node
    options name `--test`, which runs node's test runner."""
    if not command or Path(command[0]).name != _NODE:
        return None
    words = tuple(command[1:])
    options, scripts = _node_read(words)
    if _TEST in options:
        return None
    for index in scripts:
        if _entry_shaped(words[index], name, packages):
            return (command[0], *words[: index + 1]), words[index + 1 :]
    return None


# node's closed list: the test runner's options that rewrite a failing snapshot, or report tests
# that never ran as passed.
_NODE_REFUSED = frozenset({"--test-update-snapshots", "--test-rerun-failures"})
NODE_OPTIONS = "NODE_OPTIONS"
# node's watch modes, and its options that hold the code until a debugger attaches, which under
# `prove` none does: each never ends.
_NODE_WATCHES = frozenset({"--watch", "--watch-path"})
_NODE_INSPECT_WAITS = frozenset({"--inspect-brk", "--inspect-wait"})


def node_refused(words: Sequence[str], node_options: str = "") -> str | None:
    """The first of node's options on its closed list among `words` (the words after `node`) and
    then the words of `node_options` (the run's `NODE_OPTIONS`, split at white space); `None` where
    none is."""
    return _spelled((*options(words), *node_options.split()), _NODE_REFUSED)


def node_never_ends(words: Sequence[str], node_options: str = "") -> str | None:
    """node's option among `words` (the words after `node`) under which the run never ends: a watch
    mode, or one that waits for a debugger there or among the words of `node_options` (the run's
    `NODE_OPTIONS`, which reaches every node the run starts); `None` where none is."""
    return _spelled(words, _NODE_WATCHES) or _spelled(
        (*options(words), *node_options.split()), _NODE_INSPECT_WAITS
    )


def never_ends(option: str) -> Unresolved:
    """`NEVER_ENDS` for `option`, a watch mode's or one of node's that waits for a debugger
    (`node_never_ends`), its detail saying which of the two it is."""
    detail = WAITS_DETAIL if option in _NODE_INSPECT_WAITS else NEVER_ENDS_DETAIL
    return Unresolved(NEVER_ENDS, detail.format(option=option))


@dataclass(frozen=True)
class _Typed:
    """A recognised run of a package's runner, as typed: the command's words up to the runner's
    arguments (`npx --no-install jest`, `./node_modules/.bin/jest`, `node --inspect
    node_modules/jest/bin/jest.js`), node's own options where node runs the entry, and the
    runner's arguments."""

    head: tuple[str, ...]
    node_words: tuple[str, ...]
    args: tuple[str, ...]


def _typed(command: Sequence[str], runner: _Runner) -> _Typed | None:
    """`command` read as a run of `runner`: the runner bare or after `npx`, a path to the runner as
    the first word, or the entry `node` is handed (`node_entry`); `None` for a command that is none
    of them."""
    args = runner_args(command, runner.name)
    if args is None:
        args = linked_args(command, runner.name)
    if args is not None:
        return _Typed(tuple(command[: len(command) - len(args)]), (), args)
    read = node_entry(command, runner.name, runner.packages)
    if read is None:
        return None
    head, rest = read
    return _Typed(head, head[1:-1], rest)


class _PackageRunner:
    """`RunnerAdapter` for a runner a package ships, run as the command types it (`_typed`): bare,
    after `npx`, by its `.bin` link, or as the entry `node` is handed."""

    def __init__(self, runner: _Runner) -> None:
        self._runner = runner

    @property
    def name(self) -> str:
        return self._runner.name

    @property
    def forging(self) -> Mapping[str, Callable[[str], bool]]:
        return self._runner.forging

    def recognises(self, command: Sequence[str]) -> bool:
        return _typed(command, self._runner) is not None

    def plan(
        self,
        launch: Sequence[str],
        command: Sequence[str],
        *,
        cwd: Path,
        scratch: Path,
        environ: Mapping[str, str],
    ) -> Plan | Refused | Unresolved:
        runner = self._runner
        typed = _typed(command, runner)
        if typed is None:
            return Unresolved(ENTRY_NOT_FOUND)
        args, node_words = typed.args, typed.node_words
        refused = runner.refused(args)
        if refused is not None:
            return Refused(REFUSED_OPTION, refused)
        waits = node_never_ends(node_words, environ.get(NODE_OPTIONS, ""))
        never = waits or runner.never_ends(args)
        if never is not None:
            return never_ends(never)
        unplanned = runner.unplanned(args)
        if unplanned is not None:
            return unplanned
        report = scratch / runner.report_name
        words = runner.words(args)
        planned = before_separator(words, runner.ours(words, report))
        # A bare runner on no `PATH` entry gets its detail; behind a launcher what is missing is
        # the launcher, which `_launched` names.
        bare = typed.head == (runner.name,) and not launch
        missing = UNRESOLVED.format(bin=runner.name) if bare else None
        argv = _launched(launch, (*typed.head, *planned), cwd, environ, missing)
        if isinstance(argv, Unresolved):
            return argv
        return Plan(
            argv=argv,
            kind=ReportKind.RESULTS_JSON,
            source=ReportSource.FILE,
            report=report,
            discovery=runner.discovery,
        )


class JestAdapter(_PackageRunner):
    """`RunnerAdapter` for jest."""

    def __init__(self) -> None:
        super().__init__(_JEST)


class VitestAdapter(_PackageRunner):
    """`RunnerAdapter` for vitest."""

    def __init__(self) -> None:
        super().__init__(_VITEST)


def whole_file(cwd: Path) -> Callable[[Mapping[str, str]], bool]:
    """The JUnit reader's `drop` for a `node --test` run in `cwd`: whether a testcase is the one
    node writes for a whole file that ran no test. Measured on Node 24.10.0 and 26.12.0, that one
    is named by the file's path from the directory node runs in (`test/deep/a.test.mjs` for a
    nested file) and its `classname` is `test`. So a testcase is dropped where its `classname` is
    `test` and its name, read from `cwd`, is the run's file: the file its `file` attribute names,
    by realpath, where node writes one (26.12.0), else a regular file there (24.10.0, which writes
    none). A path that cannot be asked about (`EACCES`) names no such file, and the testcase is
    counted. One that failed, a file that did not load, counts as failed whatever this answers:
    the JUnit reader never drops a failure (`stayfixed.prove.junit`). A test of the project's own
    named after a file's path is dropped too, so its run reads `failed` (none ran), never
    `proved`."""

    def drop(attributes: Mapping[str, str]) -> bool:
        name = attributes.get("name")
        if not name or attributes.get("classname") != "test":
            return False
        file = attributes.get("file")
        try:
            if file is None:
                return fsops.is_file(cwd / name)
            return os.path.realpath(cwd / name) == os.path.realpath(file)
        except OSError:
            return False

    return drop


class NodeTestAdapter:
    """`RunnerAdapter` for `node --test`."""

    @property
    def name(self) -> str:
        return NODE_TEST

    @property
    def forging(self) -> Mapping[str, Callable[[str], bool]]:
        return {}

    def recognises(self, command: Sequence[str]) -> bool:
        return (
            bool(command) and Path(command[0]).name == _NODE and _TEST in node_options(command[1:])
        )

    def plan(
        self,
        launch: Sequence[str],
        command: Sequence[str],
        *,
        cwd: Path,
        scratch: Path,
        environ: Mapping[str, str],
    ) -> Plan | Refused | Unresolved:
        inherited = environ.get(NODE_OPTIONS, "")
        refused = node_refused(command[1:], inherited)
        if refused is not None:
            return Refused(REFUSED_OPTION, refused)
        never = node_never_ends(command[1:], inherited)
        if never is not None:
            return never_ends(never)
        report = scratch / NODE_REPORT
        ours = (
            "--test-reporter=junit",
            f"--test-reporter-destination={report}",
            "--test-reporter=spec",
            "--test-reporter-destination=stdout",
        )
        argv = _launched(launch, (command[0], *ours, *command[1:]), cwd, environ)
        if isinstance(argv, Unresolved):
            return argv
        return Plan(
            argv=argv,
            kind=ReportKind.JUNIT,
            source=ReportSource.FILE,
            report=report,
            discovery=NODE_DISCOVERY,
            drop=whole_file(cwd),
        )


ADAPTERS = (JestAdapter(), VitestAdapter(), NodeTestAdapter())
