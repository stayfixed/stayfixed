"""JavaScript's runner adapters: a jest, vitest or `node --test` run, proved from the report the
runner writes to a file `prove` hands it.

**What is recognised.** `jest` and `vitest`, bare or after `npx`, `npx --no-install` or `npx --no`;
and `node` (or a path to one) with `--test` among its options. `npm test`, `npm run`, `yarn`, `pnpm`
and every other package manager's script runner are recognised by none of them: what a script runs
is the script's, never read here, and `prove --junit` counts its report.

**No `npx` is executed, and no package manager's shim is.** The entry point is found the way Node
finds a package: `node_modules/<package>/package.json` in the directory the command runs in, then
in each directory above it up to the project's top-level (`jest`, then `jest-cli`; `vitest`), its
`bin` (a string, or a mapping holding the runner's name) naming the entry, a file inside the
package. Then the runner's name on `PATH`, where the first one found is a symbolic link to a file a
package's `bin` names, as npm links a global install. A `.bin` file or a `PATH` entry that is not a
link (pnpm's `sh` shim, Yarn Plug'n'Play's) is never read or run, and nothing is installed: no entry
found is `ENTRY_NOT_FOUND`, whose detail names `prove --junit` as the way on. The run is `[<node>,
<entry's realpath>, …]`, `<node>` the first `node` on `PATH`; `--test` runs that `node` too, or the
one the command names by its path.

**The report.** jest: `--json --outputFile=<report>`. vitest: `run` first where the command does
not start with it, so it runs once; then `--reporter=json --outputFile=<report>`, and
`--reporter=default` where the command names no reporter of its own; the string form of
`--outputFile` wins over a configuration's `outputFile` in either form, and a configuration's
reporter that carries its own `outputFile` wins over it, so that report never arrives
(`no-report`). `node --test`: `--test-reporter=junit --test-reporter-destination=<report>
--test-reporter=spec --test-reporter-destination=stdout`, right after `node`. Each is added before
a `--`, which ends the options. node writes one testcase for a whole file when the file ran no test
(a name pattern that matched nothing in it, no test defined, an early `process.exit`), named after
the file, `classname` `test`, and passed: `drop` leaves it out, unless it carries a failure, which
is a file that did not load and counts as failed.

**Every control here, with its adversary and its anchor.** The adversary is the agent typing the
command; the anchor of every refusal is the command's own words; each list is closed, drawn by
running every option the pinned runner registers over a failing test with the report options
appended, and every other option is free. `REFUSED_OPTION`, naming the option:

- jest 30.5.2: `--json` and `--outputFile` (the report's own), `--testResultsProcessor` (which
  rewrites the results before they are written), `-u`/`--updateSnapshot` (which rewrites a failing
  snapshot so that it passes), `--ci=false`/`--no-ci` (which writes a missing snapshot rather than
  failing it), `--collectTests` (which exits 0 reporting a failing test as passed), `--watch` and
  `--watchAll` (which never end), and `-c`/`--config` given a JSON text or naming a file outside the
  project. A configuration file inside the project is named among the receipt's configuration
  files by its realpath (`Plan.configs`).
- vitest 5.0.5: `--outputFile` in any form, `-u`/`--update` but `--update=none` (each rewrites a
  failing or missing snapshot so that it passes), `--mergeReports` (which runs nothing and reports
  the blob files it reads as results), `--dangerouslyIgnoreUnhandledErrors` (which exits 0 past an
  error no test reported), `-w`/`--watch` (which never ends), and `-c`/`--config` naming a file
  outside the project, one inside it named as jest's is.
- `node --test` on Node 26.12.0: any `--test-reporter…` of the command's own; `--env-file`,
  `--env-file-if-exists` and the configuration file options (`--config-file`,
  `--experimental-config-file`, `--experimental-default-config-file`), which load what the run
  reads; `--test-update-snapshots` (which rewrites a failing snapshot so that it passes);
  `--test-rerun-failures` (which reports as passed, unrun, every test the state file it names says
  passed before); and `--watch` and `--watch-path` (which never end). Node reads an option written
  with `_` as with `-`, and after the files under `--test` as before them, and so are these.
  `--import`, `--require` and `--loader` are free (TypeScript through `tsx`, Plug'n'Play's
  `.pnp.cjs`).

`FORGING`, assigned in the command (refused) or inherited (scrubbed): `NODE_OPTIONS`, which Node
reads as options of every run, `--require` and the reporters among them; for `node --test` also
`NODE_TEST_CONTEXT`, under which it runs no file and exits 0 (measured on 26.12.0, any value).

What a file in the tree can do -- a configuration's reporters, `testResultsProcessor` or setup
files, a test that writes the report, a `package.json` that points `bin` elsewhere -- is the
bound's: the receipt names the configuration files (`CONFIGS`) and the untracked files each runner
collects from (`*_DISCOVERY`), and the realpath of the `node` that ran.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from stayfixed import fsops
from stayfixed.profiles.runners import Plan, Refused, ReportKind, ReportSource, Unresolved

JEST = "jest"
VITEST = "vitest"
NODE_TEST = "node-test"
# The reasons these adapters name: an option a closed list refuses, and an entry point that does
# not resolve from where the command runs.
REFUSED_OPTION = "refused-option"
ENTRY_NOT_FOUND = "entry-not-found"
FORGING = frozenset({"NODE_OPTIONS"})
NODE_TEST_FORGING = FORGING | {"NODE_TEST_CONTEXT"}
CONFIGS = ("package.json", ".npmrc", "jest.config.*", "vitest.config.*", "vite.config.*")
# Each runner's default test files, as `stayfixed.prove.tree` matches a glob, from the right.
JEST_DISCOVERY = ("*.test.*", "*.spec.*", "__tests__/*")
VITEST_DISCOVERY = ("*.test.*", "*.spec.*")
NODE_DISCOVERY = ("*.test.*", "*-test.*", "*_test.*", "test-*.*", "test.*", "test/*")
JEST_REPORT = "jest.json"
VITEST_REPORT = "vitest.json"
NODE_REPORT = "junit.xml"

_NPX = "npx"
# The `npx` options that install nothing, the only ones read before the runner's name.
_NPX_OFFLINE = frozenset({"--no-install", "--no"})
_NODE = "node"
_MODULES = "node_modules"
_MANIFEST = "package.json"
# A named cap: how much of a package's `package.json` is read for its `bin`. jest's and vitest's
# are under 6 KiB; one past this is no package this reads.
_MANIFEST_BYTES = 1024 * 1024
_SEPARATOR = "--"
_TEST = "--test"
_RUN = "run"
_REPORTER = "reporter"

_UNRESOLVED = (
    "no node_modules/{package} from here up to the project's top-level, and no {bin} on PATH "
    "linked into one; `prove --junit` counts a report you name"
)
_NO_NODE = "no node on PATH"


def _executable(path: Path) -> bool:
    try:
        return fsops.is_file(path) and os.access(path, os.X_OK)
    except OSError:
        return False


def _on_path(name: str, cwd: Path, path: str) -> Path | None:
    """The first `name` on `path` that can be executed, a relative entry read from `cwd`."""
    candidates = [cwd / directory / name for directory in path.split(os.pathsep)]
    return next((candidate for candidate in candidates if _executable(candidate)), None)


def _manifest_bin(package: Path, name: str) -> Path | None:
    """The realpath of the file the `bin` of `package`'s `package.json` names for `name` (a
    string, or a mapping holding `name`), where it is a file inside the package; else `None`."""
    try:
        data, more = fsops.read_bounded(package / _MANIFEST, _MANIFEST_BYTES)
    except OSError:
        return None
    if more:
        return None
    try:
        manifest = json.loads(data)
    except (ValueError, RecursionError):
        return None
    declared = manifest.get("bin") if isinstance(manifest, dict) else None
    if isinstance(declared, dict):
        declared = declared.get(name)
    if not isinstance(declared, str) or not declared:
        return None
    entry = Path(os.path.realpath(package / declared))
    home = Path(os.path.realpath(package))
    if home not in entry.parents or not fsops.is_file(entry):
        return None
    return entry


def _upward(cwd: Path, root: Path) -> list[Path]:
    """`cwd` and each directory above it, up to `root` and no further."""
    here, top = Path(os.path.realpath(cwd)), Path(os.path.realpath(root))
    above = [parent for parent in here.parents if parent == top or top in parent.parents]
    return [here, *above] if top == here or top in here.parents else [here]


def _linked(name: str, cwd: Path, path: str) -> Path | None:
    """The entry the first `name` on `path` links to, where it is a link to a file a package's
    `bin` names for `name`; a file that is not a link is never read."""
    found = _on_path(name, cwd, path)
    if found is None or not fsops.is_symlink(found):
        return None
    target = Path(os.path.realpath(found))
    package = next((p for p in target.parents if fsops.is_file(p / _MANIFEST)), None)
    if package is None or _manifest_bin(package, name) != target:
        return None
    return target


@dataclass(frozen=True)
class _Runner:
    """What tells jest's and vitest's plans apart: the runner's name, the packages that ship it,
    its report, its closed list and how its report options read."""

    name: str
    packages: tuple[str, ...]
    discovery: tuple[str, ...]
    report_name: str
    refused: Callable[[Sequence[str], Path, Path], str | None]
    configs: Callable[[Sequence[str], Path], tuple[str, ...]]
    ours: Callable[[Sequence[str], Path], tuple[str, ...]]
    words: Callable[[Sequence[str]], tuple[str, ...]]


def runner_args(command: Sequence[str], name: str) -> tuple[str, ...] | None:
    """The words after the runner's name in `command`, where `command` is `name` bare or after
    `npx`, `npx --no-install` or `npx --no`; else `None`."""
    words = list(command)
    if words[:1] == [_NPX]:
        words = words[1:]
        if words[:1] and words[0] in _NPX_OFFLINE:
            words = words[1:]
    if words[:1] != [name]:
        return None
    return tuple(words[1:])


def _with(args: Sequence[str], ours: Sequence[str]) -> tuple[str, ...]:
    """`args` with `ours` added last, before a `--` where there is one."""
    cut = list(args).index(_SEPARATOR) if _SEPARATOR in args else len(args)
    return (*args[:cut], *ours, *args[cut:])


def _options(args: Sequence[str]) -> list[str]:
    """The words of `args` before a `--`, which ends a runner's options."""
    words = list(args)
    return words[: words.index(_SEPARATOR)] if _SEPARATOR in words else words


def _camel(name: str) -> str:
    """A long option's name as yargs and cac read it: `output-file` is `outputFile`."""
    head, *rest = name.split("-")
    return head + "".join(part[:1].upper() + part[1:] for part in rest)


@dataclass(frozen=True)
class _Long:
    """A `--name[=value]` word as jest's and vitest's parsers read it: its name camel-cased and cut
    at the first `.` (cac's nested options, `--outputFile.json`), whether `--no-` negated it, and
    its value where the word holds one."""

    name: str
    negated: bool
    value: str | None


def _long(word: str) -> _Long | None:
    if not word.startswith("--") or word == _SEPARATOR:
        return None
    name, equals, value = word[2:].partition("=")
    negated = name.startswith("no-")
    name = _camel(name.removeprefix("no-")).partition(".")[0]
    return _Long(name, negated, value if equals else None)


def _short_letters(word: str) -> str:
    """The letters of a single-dash word (`-u`, `-iu`, `-c=x`), each a short option, as yargs and
    cac read a cluster: up to an `=`."""
    if not word.startswith("-") or word.startswith("--"):
        return ""
    return word[1:].partition("=")[0]


def _short_value(words: Sequence[str], index: int, letter: str) -> str | None:
    """The value a cluster at `index` gives its short option `letter`: what follows one `=`, or
    the next word where `letter` closes the cluster; `None` where it gives none."""
    word = words[index]
    letters, equals, value = word[1:].partition("=")
    if not letters.endswith(letter):
        return None
    if equals:
        return value
    return words[index + 1] if index + 1 < len(words) else None


def _config_values(args: Sequence[str]) -> list[str]:
    """Every value `-c` or `--config` is given in `args`, in either spelling."""
    words = _options(args)
    found: list[str] = []
    for index, word in enumerate(words):
        long = _long(word)
        if long is not None and long.name == "config" and not long.negated:
            given = long.value if long.value is not None else _next(words, index)
        elif "c" in _short_letters(word):
            given = _short_value(words, index, "c")
        else:
            continue
        if given is not None:
            found.append(given)
    return found


def _next(words: Sequence[str], index: int) -> str | None:
    return words[index + 1] if index + 1 < len(words) else None


def _outside(value: str, cwd: Path, root: Path) -> bool:
    """Whether the file `value` names, read from `cwd`, lies outside the project `root`."""
    named = Path(os.path.realpath(cwd / value))
    top = Path(os.path.realpath(root))
    return named != top and top not in named.parents


def _chosen(args: Sequence[str], cwd: Path) -> tuple[str, ...]:
    """The realpath of each configuration file `-c` or `--config` names: an absolute entry of
    `Plan.configs`, which names that one file."""
    return tuple(os.path.realpath(cwd / value) for value in _config_values(args))


def _config_refused(args: Sequence[str], cwd: Path, root: Path, *, text: bool) -> str | None:
    """`--config` where its value is a configuration's own text (jest reads a JSON object given
    there) or names a file outside the project."""
    for value in _config_values(args):
        if (text and value.lstrip().startswith("{")) or _outside(value, cwd, root):
            return "--config"
    return None


# jest's closed list, each a name as yargs reads it, past `--no-` and camel-casing.
_JEST_REPORT_OPTIONS = frozenset({"json", "outputFile", "testResultsProcessor"})
_JEST_RUNS_NO_TEST = frozenset({"collectTests"})
_JEST_NEVER_ENDS = frozenset({"watch", "watchAll"})
_JEST_SNAPSHOTS = "updateSnapshot"
_JEST_SNAPSHOT_LETTER = "u"
_JEST_CI = "ci"
# The values yargs reads a boolean option as false by, where one is given.
_FALSE = frozenset({"false", "0"})


def _off(long: _Long) -> bool:
    """Whether a boolean option's word turns it off: `--no-x` or `--x=false`."""
    return long.negated or (long.value is not None and long.value in _FALSE)


def jest_refused(args: Sequence[str], cwd: Path, root: Path) -> str | None:
    """The first word of jest's `args` on its closed list, as the receipt names it; `None` where
    none is."""
    for word in _options(args):
        long = _long(word)
        if long is None:
            if _JEST_SNAPSHOT_LETTER in _short_letters(word):
                return word
            continue
        if long.name in _JEST_REPORT_OPTIONS or long.name in _JEST_RUNS_NO_TEST:
            return f"--{long.name}"
        if long.name in _JEST_NEVER_ENDS and not _off(long):
            return f"--{long.name}"
        if long.name == _JEST_SNAPSHOTS and not _off(long):
            return f"--{long.name}"
        if long.name == _JEST_CI and _off(long):
            return word
    return _config_refused(args, cwd, root, text=True)


# vitest's closed list.
_VITEST_REPORT_OPTIONS = frozenset({"outputFile", "mergeReports"})
_VITEST_EXIT_PAST_ERRORS = "dangerouslyIgnoreUnhandledErrors"
_VITEST_SNAPSHOTS = "update"
# The `--update` values that rewrite no snapshot.
_VITEST_NO_UPDATE = frozenset({"none", "false"})
_VITEST_NEVER_ENDS = "watch"
_VITEST_LETTERS = frozenset("uw")


def vitest_refused(args: Sequence[str], cwd: Path, root: Path) -> str | None:
    """The first word of vitest's `args` on its closed list, as the receipt names it; `None` where
    none is."""
    for word in _options(args):
        long = _long(word)
        if long is None:
            if _VITEST_LETTERS & set(_short_letters(word)):
                return word
            continue
        if long.name in _VITEST_REPORT_OPTIONS:
            return f"--{long.name}"
        if long.name == _VITEST_SNAPSHOTS and not (long.negated or long.value in _VITEST_NO_UPDATE):
            return f"--{long.name}"
        if long.name in (_VITEST_EXIT_PAST_ERRORS, _VITEST_NEVER_ENDS) and not _off(long):
            return f"--{long.name}"
    return _config_refused(args, cwd, root, text=False)


def _jest_ours(args: Sequence[str], report: Path) -> tuple[str, ...]:
    return ("--json", f"--outputFile={report}")


def _vitest_ours(args: Sequence[str], report: Path) -> tuple[str, ...]:
    ours = ("--reporter=json", f"--outputFile={report}")
    named = any((long := _long(word)) is not None and long.name == _REPORTER for word in args)
    return ours if named else (*ours, "--reporter=default")


def _jest_words(args: Sequence[str]) -> tuple[str, ...]:
    return tuple(args)


def _vitest_words(args: Sequence[str]) -> tuple[str, ...]:
    """vitest's arguments, `run` first, so that it runs once and never watches."""
    return tuple(args) if args[:1] == (_RUN,) else (_RUN, *args)


_JEST = _Runner(
    name=JEST,
    packages=("jest", "jest-cli"),
    discovery=JEST_DISCOVERY,
    report_name=JEST_REPORT,
    refused=jest_refused,
    configs=_chosen,
    ours=_jest_ours,
    words=_jest_words,
)
_VITEST = _Runner(
    name=VITEST,
    packages=("vitest",),
    discovery=VITEST_DISCOVERY,
    report_name=VITEST_REPORT,
    refused=vitest_refused,
    configs=_chosen,
    ours=_vitest_ours,
    words=_vitest_words,
)


def entry_point(
    name: str, packages: Sequence[str], cwd: Path, root: Path, path: str
) -> Path | None:
    """The realpath of the runner `name`'s entry: a package of `packages` under `node_modules` from
    `cwd` up to `root`, nearest first and each directory's packages in order; else the first `name`
    on `path`, where it links to a file a package's `bin` names."""
    for directory in _upward(cwd, root):
        for package in packages:
            entry = _manifest_bin(directory / _MODULES / package, name)
            if entry is not None:
                return entry
    return _linked(name, cwd, path)


class _PackageRunner:
    """`RunnerAdapter` for a runner a package ships, run by `node` from its entry point."""

    def __init__(self, runner: _Runner) -> None:
        self._runner = runner

    @property
    def name(self) -> str:
        return self._runner.name

    @property
    def forging(self) -> frozenset[str]:
        return FORGING

    def recognises(self, command: Sequence[str]) -> bool:
        return runner_args(command, self._runner.name) is not None

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
        runner = self._runner
        args = runner_args(command, runner.name)
        if args is None:
            return Unresolved(ENTRY_NOT_FOUND)
        refused = runner.refused(args, cwd, root)
        if refused is not None:
            return Refused(REFUSED_OPTION, refused)
        path = environ.get("PATH", os.defpath)
        entry = entry_point(runner.name, runner.packages, cwd, root, path)
        if entry is None:
            detail = _UNRESOLVED.format(package=runner.packages[0], bin=runner.name)
            return Unresolved(ENTRY_NOT_FOUND, detail)
        node = _on_path(_NODE, cwd, path)
        if node is None:
            return Unresolved(ENTRY_NOT_FOUND, _NO_NODE)
        report = scratch / runner.report_name
        words = runner.words(args)
        return Plan(
            argv=(str(node), str(entry), *_with(words, runner.ours(words, report))),
            program=Path(os.path.realpath(node)),
            kind=ReportKind.RESULTS_JSON,
            source=ReportSource.FILE,
            report=report,
            set_env={},
            scrub=FORGING,
            discovery=runner.discovery,
            configs=(*CONFIGS, *runner.configs(args, cwd)),
        )


class JestAdapter(_PackageRunner):
    """`RunnerAdapter` for jest."""

    def __init__(self) -> None:
        super().__init__(_JEST)


class VitestAdapter(_PackageRunner):
    """`RunnerAdapter` for vitest."""

    def __init__(self) -> None:
        super().__init__(_VITEST)


# node's options that take their value as the next word where `=` does not give it, so that the
# word after one is never read as the first file `--test` is given. An option missing here reads
# its value as that file, and the command is not recognised: `not proven`, never a wrong plan.
_NODE_VALUED = frozenset(
    {
        "-r",
        "--require",
        "--import",
        "--loader",
        "--experimental-loader",
        "-C",
        "--conditions",
        "--input-type",
        "--env-file",
        "--env-file-if-exists",
        "--config-file",
        "--experimental-config-file",
        "--test-reporter",
        "--test-reporter-destination",
        "--test-name-pattern",
        "--test-skip-pattern",
        "--test-concurrency",
        "--test-timeout",
        "--test-shard",
        "--test-isolation",
        "--experimental-test-isolation",
        "--test-global-setup",
        "--test-rerun-failures",
        "--test-coverage-include",
        "--test-coverage-exclude",
        "--test-coverage-lines",
        "--test-coverage-branches",
        "--test-coverage-functions",
        "--test-random-seed",
        "--experimental-test-tag-filter",
        "--watch-path",
        "--disable-warning",
        "--title",
    }
)
# node's closed list: the options a name starts with, and the ones it is.
_NODE_REPORTERS = "--test-reporter"
_NODE_REFUSED = frozenset(
    {
        "--env-file",
        "--env-file-if-exists",
        "--config-file",
        "--experimental-config-file",
        "--experimental-default-config-file",
        "--test-update-snapshots",
        "--test-rerun-failures",
        "--watch",
        "--watch-path",
    }
)


def _node_name(word: str) -> str:
    """An option word's name as node reads it: up to an `=`, every `_` read as `-`."""
    return word.partition("=")[0].replace("_", "-")


def node_options(words: Sequence[str]) -> list[str]:
    """node's own options in `words` (the words after `node`): up to the first word that is
    neither an option nor the value the option before it takes, or a `--`."""
    found: list[str] = []
    valued = False
    for word in words:
        if valued:
            valued = False
            continue
        if word == _SEPARATOR or not word.startswith("-"):
            break
        found.append(word)
        valued = "=" not in word and _node_name(word) in _NODE_VALUED
    return found


def node_refused(words: Sequence[str]) -> str | None:
    """The first word of `words` (the words after `node`) on node's closed list, by its name;
    `None` where none is. Every word before a `--` is read, a file's name among them: under
    `--test` node reads an option written after the files too."""
    for word in _options(words):
        name = _node_name(word)
        if name.startswith(_NODE_REPORTERS) or name in _NODE_REFUSED:
            return name
    return None


def whole_file(attributes: Mapping[str, str]) -> bool:
    """Whether a testcase is the one node writes for a whole file that ran no test: named after
    its file, `classname` `test`, and carrying no failure. A whole-file testcase with a failure is
    a file that did not load, and is counted."""
    file = attributes.get("file")
    return (
        file is not None
        and attributes.get("name") == os.path.basename(file)
        and attributes.get("classname") == "test"
        and "failure" not in attributes
    )


class NodeTestAdapter:
    """`RunnerAdapter` for `node --test`."""

    @property
    def name(self) -> str:
        return NODE_TEST

    @property
    def forging(self) -> frozenset[str]:
        return NODE_TEST_FORGING

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
        root: Path,
        scratch: Path,
        environ: Mapping[str, str],
    ) -> Plan | Refused | Unresolved:
        refused = node_refused(command[1:])
        if refused is not None:
            return Refused(REFUSED_OPTION, refused)
        path = environ.get("PATH", os.defpath)
        word = command[0]
        if os.sep in word:
            node: Path | None = cwd / word if _executable(cwd / word) else None
        else:
            node = _on_path(word, cwd, path)
        if node is None:
            return Unresolved(ENTRY_NOT_FOUND, _NO_NODE)
        report = scratch / NODE_REPORT
        ours = (
            "--test-reporter=junit",
            f"--test-reporter-destination={report}",
            "--test-reporter=spec",
            "--test-reporter-destination=stdout",
        )
        return Plan(
            argv=(str(node), *ours, *command[1:]),
            program=Path(os.path.realpath(node)),
            kind=ReportKind.JUNIT,
            source=ReportSource.FILE,
            report=report,
            set_env={},
            scrub=NODE_TEST_FORGING,
            discovery=NODE_DISCOVERY,
            configs=CONFIGS,
            drop=whole_file,
        )


ADAPTERS = (JestAdapter(), VitestAdapter(), NodeTestAdapter())
