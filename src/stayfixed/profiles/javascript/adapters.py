"""JavaScript's runner adapters: a jest, vitest or `node --test` run, proved from the report the
runner writes to a file `prove` hands it, run as the command typed it.

**What is recognised.** `jest` and `vitest`, bare or after `npx` or `npx --no-install` (not `npx
--no`: npm 11.6.0 reads the runner's options after it as its own, so the report's never reach the
runner, measured); a path to one as the command's first word (`./node_modules/.bin/jest`),
npm's link or pnpm's `sh` shim alike, run as typed; `node [node's options] <entry>
…`, the entry a path into `node_modules/<package>` or `node_modules/.bin/<runner>` (`node_entry`)
that is, by its realpath, the file its package's `bin` names; and `node` (or a path to one) with
`--test` among its options. `npm test`, `npm run`, `yarn`, `pnpm` and every other package
manager's script runner are recognised by none of them: what a script runs is the script's, never
read here, and `prove --junit` counts its report.

**The run is the command as typed** (`stayfixed.profiles.programs.launched`): its first word
(`npx`, `jest`, `node`, the `.bin` link) found as a shell finds it, on the run's `PATH` or from the
directory the command runs in, every other word as typed, and the report's options in their place,
below. Behind a launcher the core read past (`uv run …`), the launcher is found and the command's
words are handed to it as typed, for it to resolve on its own `PATH`; nothing is looked for on the
caller's. `npx` runs as it does outside `prove`: it reads `.npmrc` and puts every
`node_modules/.bin` above the directory on `PATH` (measured with npm 11.6.0 on Node 24.10.0), and
given a runner no `node_modules` holds it installs one without asking: the run's standard input
is `/dev/null`, and npm 11.6.0 asks only where standard input is a terminal, and otherwise warns
and installs.

What stays `ENTRY_NOT_FOUND`: a first word that names nothing there (a bare `jest` on no `PATH`
entry, whose detail names `npx jest` and `prove --junit`: nothing the command names can run;
otherwise what was looked for, a path at that path or a name on `PATH`,
`stayfixed.profiles.programs.not_found`); and a file `node` is handed that is not the entry its
package's `bin` names, which nothing then tells is the runner's. A bare `jest` on `PATH`, or a
path to one, is the runner by its name, and runs whatever that file is.

**The entry the receipt names** (`Plan.entry`), by its realpath, where it is not the program itself:
the file `node` is handed; the file a path to the runner reaches, where that is the entry its
package's `bin` names (npm's link; a shim is unnamed); and for `npx`, the
`node_modules/.bin/<runner>` npx runs (`npx_bin`), the first there is in npm's local prefix and
then in each directory above it, as npm walks: the directory the command runs in, or inside an npm
workspace the workspace's root (`npm_prefix`). Where there is none, or the prefix cannot be told
(a `workspaces` pattern this does not read), npx resolves the runner its own way, unnamed. Naming
is the receipt's: no verdict reads it.

**Node's options** are read with no table of node's (`_node_read`): a word starting with `-` is an
option, and the word after one that gives itself no value with `=` may be that option's value. In
front of a runner's entry every option is accepted, and the entry is the first word that may be
node's script and is the file its package's `bin` names: `node --inspect
node_modules/jest/bin/jest.js` and `node --max-old-space-size=4096 …` run as typed. A command whose
node options name `--test` is `node --test`'s.

**The report.** jest: `--json --outputFile=<report>`. vitest: `run` first where the command's
first word is none of vitest's subcommands, so it runs once; `related` kept, with `--run` where the
command does not set it; `watch` and `dev` are `NEVER_ENDS`, and `bench`, `list`, `init` and
`doctor`, which run no test suite that reports, `NO_TEST_RUN` (`vitest_unplanned`); then
`--reporter=json --outputFile=<report>`, and `--reporter=default` where the command names no
reporter of its own; the string form of `--outputFile` wins over a configuration's `outputFile` in
either form, and a configuration's reporter that carries its own `outputFile` wins over it, so that
report never arrives (`no-report`). A file-writing reporter of the command's own
(`--reporter=junit`) shares the adapter's `--outputFile`, and the run ends `not proven`
(`report-malformed`). `node --test`: `--test-reporter=junit
--test-reporter-destination=<report> --test-reporter=spec --test-reporter-destination=stdout`,
right after `node`. Each is added before a `--`, which ends the options. node writes one testcase
for a whole file when the file ran no test (a name pattern that matched nothing in it, no test
defined, an early `process.exit`), named by the file's path from the directory node runs in,
`classname` `test`, and passed: `drop` (`whole_file`) leaves it out, unless it carries a failure,
which is a file that did not load and counts as failed.

**What is refused** (`REFUSED_OPTION`, naming the option): only what a person or an agent could
type by mistake and get a green report for tests that never ran or never checked anything, each
measured on the pinned runner over a failing test with the report options appended; every other
option is free.

- jest 30.5.2: `-u`/`--updateSnapshot` (which rewrites a failing snapshot so that it passes);
  and `--collectTests` (which exits 0 reporting a failing test as passed). `--ci=false`/`--no-ci`
  is free: jest then writes a snapshot that is missing and passes it, as it does by default
  wherever `CI` is unset or false. The command's own `--json` and `--outputFile` are free: the
  adapter's come last and win.
- vitest 5.0.5: `-u`/`--update` but `--update=none`, `--no-update` and `--update=new` (each other
  rewrites a failing snapshot so that it passes; `new`, vitest's own default where `CI` is unset,
  only writes a missing one); the same values of `UPDATE_SNAPSHOT`, which vitest reads as
  `--update` where the command gives none (`FORGING`: assigned a rewriting value, the command is
  refused; inherited with one, the variable is removed from the run's environment and named on the
  receipt); `--mergeReports` (which runs nothing and reports the blob files it reads, written by an
  earlier run, as results); and `--dangerouslyIgnoreUnhandledErrors` (which exits 0 past an error
  no test reported, a run vitest itself fails). The command's own `--outputFile` is free: the run
  ends `not proven` or reads the adapter's report.
- `node --test`: `--test-update-snapshots` (which rewrites a failing snapshot so that it passes);
  and `--test-rerun-failures` (which reports as passed, unrun, every test the state file it names
  says passed before), on the command line or in the run's `NODE_OPTIONS`, which Node 24.10.0
  reads it from too (`node_refused`, `node_options_words`). Node reads an option written with `_`
  as with `-`, and so are these; and they are read after the files under `--test` too, where Node
  26.12.0 reads an option as before them (Node 24.10.0 reads none there, measured, so on it a
  refusal there is only the safe side). A reporter of the command's own is free: one given no
  destination stops node before any test runs, so the adapter's report is never written (`not
  proven`), and one with its own is written beside it.

A watch mode -- jest's `--watch` and `--watchAll`, vitest's `-w`/`--watch`, node's `--watch` and
`--watch-path` -- moves no report and forges no pass, but it never ends: it waits for changes
after the run, so no report is ever finished. Nor do node's `--inspect-brk` and `--inspect-wait`
(jest's documented recipe for debugging), which hold the code until a debugger attaches, under
`--test` too (measured on Node 24.10.0), on the command line or in the run's `NODE_OPTIONS`, which
reaches every node the run starts. Each is not refused; it is `NEVER_ENDS` (`not proven`),
naming the option, its detail saying it watches or waits for a debugger (`never_ends`), and a
refusal in the same command wins.

Each reader follows the runner's own parser, measured on the pinned version: jest's yargs (a short
option in a cluster takes the rest of the word as its value after a `=`, a character other than a
letter, digit or `_`, or a number, so `-c/etc/x.js` names `/etc/x.js`; a boolean takes `true` or
`false` as its next word, so `-u false` is off, and any `=` value but `true` turns it off);
vitest's cac (every character of a short cluster up to a `=` is an option of its own, so `-t.u` sets
`-u`; a boolean is off only by `--no-` or `false`, and `--update=false` is the text `false`, which
rewrites snapshots as `--update` does).

**What else the receipt names.** The file `-c`/`--config` names, by its realpath (`Plan.configs`),
read from the directory the command runs in for jest, and from vitest's `--root` where the command
gives one; a configuration's own text jest is given there names no file. A file node's `-r`,
`--require`, `--import` or `--loader` names, where its reading is not in doubt
(`_preloaded_file`); any other value runs as it is, unnamed. The configuration files (`CONFIGS`,
`.npmrc` among them, which npx reads) and the untracked files each runner collects from
(`*_DISCOVERY`), and the realpath of the program that ran.

No other variable is refused or removed (jest's and node's `forging` is empty): `NODE_OPTIONS`,
jest's documented recipe for ES modules among its uses, reaches the run as it reaches it outside
`prove`. What the environment and a file in the tree can do -- a preload, a configuration's
reporters, `testResultsProcessor` or setup files, a test that writes the report, a `package.json`
that points `bin` elsewhere -- is the bound's.
"""

from __future__ import annotations

import fnmatch
import json
import os
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import SplitResult, unquote, urlsplit

from stayfixed import fsops
from stayfixed.profiles.programs import (
    SEPARATOR,
    before_separator,
    found,
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
CONFIGS = ("package.json", ".npmrc", "jest.config.*", "vitest.config.*", "vite.config.*")
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
_MANIFEST = "package.json"
# A named cap: how much of a package's `package.json` is read for its `bin`. jest's and vitest's
# are under 6 KiB; one past this is no package this reads.
_MANIFEST_BYTES = 1024 * 1024
_TEST = "--test"
_RUN = "run"
_REPORTER = "reporter"
# vitest 5.0.5's subcommands, which its parser reads in the first positional word: `run` runs
# once; `related` runs the tests that import the files it names, once under `--run`; `watch` and
# `dev` watch; `bench`, `list`, `init` and `doctor` run no test suite that reports (benchmarks; a
# list of the tests collected; a project scaffold; the suite timed under each pool, no report).
_VITEST_RELATED = "related"
_VITEST_WATCHING = frozenset({"watch", "dev"})
_VITEST_NO_TEST_RUN = frozenset({"bench", "list", "init", "doctor"})
_VITEST_SUBCOMMANDS = frozenset({_RUN, _VITEST_RELATED, *_VITEST_WATCHING, *_VITEST_NO_TEST_RUN})

# Where the runner the command names bare is on no `PATH` entry, so nothing the command names can
# run. Short enough for the receipt's line to carry whole (`printed.CLIPPED_CHARS`).
UNRESOLVED = (
    "no {bin} on PATH; `npx {bin}` runs a project's own, or `prove --junit` counts a report"
)
# Where `node` is handed a file that is not the entry its package's `bin` names.
NOT_THE_ENTRY = (
    "the file node is given is not the entry a {package} package's bin names; "
    "`prove --junit` counts a report you name"
)


def _launched(
    launch: Sequence[str],
    argv: tuple[str, ...],
    cwd: Path,
    environ: Mapping[str, str],
    missing: str | None = None,
) -> tuple[str, ...] | Unresolved:
    """The argv that runs `argv` as typed behind `launch` (`stayfixed.profiles.programs.launched`):
    the first word found and named by that path, every other word as typed, so that a launcher
    resolves the command's program as it does outside `prove`. `ENTRY_NOT_FOUND` where that first
    word names nothing there, `missing` its detail where given, else what was looked for
    (`stayfixed.profiles.programs.not_found`)."""
    planned = launched(launch, argv, cwd, environ)
    if planned is None:
        return Unresolved(ENTRY_NOT_FOUND, missing or not_found((*launch, *argv)[0]))
    return planned


def _manifest_bin(package: Path, name: str) -> Path | None:
    """The realpath of the file the `bin` of `package`'s `package.json` names for `name` (a
    string, or a mapping holding `name`), where it is a file; else `None`. Its one reader,
    `package_entry`, takes it only where it is the file it started from, which lies under
    `package`, so a `bin` naming a file outside the package is never the entry."""
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
    # A NUL names no file: the path calls refuse it (`ValueError`), and a manifest may hold one.
    if not isinstance(declared, str) or not declared or "\0" in declared:
        return None
    entry = Path(os.path.realpath(package / declared))
    return entry if fsops.is_file(entry) else None


def _linked(word: str, name: str, cwd: Path, environ: Mapping[str, str]) -> Path | None:
    """The entry the program `word` names (a path read from `cwd`, or the first on `environ`'s
    `PATH`) reaches, by its realpath, where that is the file a package's `bin` names for `name`:
    npm's `.bin` link. A file that reaches no such entry, pnpm's `sh` shim among them, runs as
    typed, its entry unnamed: naming it is the receipt's, and no verdict reads it."""
    on_path = found(word, cwd, environ)
    return None if on_path is None else package_entry(Path(os.path.realpath(on_path)), name)


def package_entry(target: Path, name: str) -> Path | None:
    """`target`, a realpath, where it is the entry its package's `bin` names for `name`, the
    package being the nearest directory above it that holds a `package.json`; else `None`."""
    package = next((p for p in target.parents if fsops.is_file(p / _MANIFEST)), None)
    if package is None or _manifest_bin(package, name) != target:
        return None
    return target


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
    configs: Callable[[Sequence[str], Path], tuple[str, ...]]
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


def _camel(name: str) -> str:
    """A long option's name as yargs and cac read it: `output-file` is `outputFile`."""
    head, *rest = name.split("-")
    return head + "".join(part[:1].upper() + part[1:] for part in rest)


@dataclass(frozen=True)
class Setting:
    """One option a word of the command sets, as the runner's own parser reads it: its name (a
    long option's, camel-cased and cut at its first `.`; a short option's letter), the value it is
    given (`None` where it is given none, so that a boolean reads as on), whether `--no-` turned it
    off, and whether a `.` made it an object (`--ci.x`, `-u.x`), which reads as on."""

    name: str
    value: str | None = None
    negated: bool = False
    dotted: bool = False


# The values a boolean is given as the next word, by both parsers: any other word is not its
# value.
_BOOLEAN_WORDS = frozenset({"true", "false"})
# What yargs reads as a number: a short option followed by one takes it as its value.
_YARGS_NUMBER = re.compile(r"-?\d+(\.\d*)?(e-?\d+)?")
# A word yargs never takes as an option's value: an option of its own, not a negative number.
_YARGS_OPTION = re.compile(r"-{1,2}[^-]")
_YARGS_NEGATIVE = re.compile(r"-+(\d+|\d*\.\d+)")
# jest 30.5.2's short options that take a value: `-c` (`--config`), `-w` (`--maxWorkers`) and
# `-t` (`--testNamePattern`); every other letter is a boolean.
_JEST_VALUED_LETTERS = frozenset("cwt")
# jest's long options this reader reads a value for, the next word where `=` gives none: the
# configuration file alone. Every other long option is read as a boolean, which takes `true` or
# `false` as its next word (`_long_setting`).
_JEST_VALUED = frozenset({"config"})


def _yargs_takes(following: str | None) -> bool:
    return following is not None and (
        not _YARGS_OPTION.match(following) or bool(_YARGS_NEGATIVE.fullmatch(following))
    )


def _long_setting(word: str, following: str | None, *, valued: bool, takes: bool) -> Setting:
    """A `--name[=value]` word as both parsers read it; `following` is its value where `=` gives
    none and the option takes the next word (`takes`, for an option `valued`), or, for a
    boolean, where the next word is `true` or `false`."""
    name, equals, value = word[2:].partition("=")
    negated = name.startswith("no-")
    camel = _camel(name.removeprefix("no-"))
    head, dot, _ = camel.partition(".")
    if equals:
        given: str | None = value
    elif valued:
        given = following if takes else None
    else:
        given = following if following in _BOOLEAN_WORDS else None
    return Setting(head, given, negated=negated, dotted=bool(dot))


def jest_settings(word: str, following: str | None) -> list[Setting]:
    """What jest's parser (yargs 17.7.3) reads `word` as setting, `following` the word after it;
    `[]` for a word that is no option. Measured on jest 30.5.2: in a cluster of short options
    (`-iu`), a letter takes the rest of the word as its value where a `=`, a character other than
    a letter, digit or `_`, or a number follows it (`-c/etc/x.js` names `/etc/x.js`), and only the
    last letter takes the next word; `-c.x` is an object."""
    if word == SEPARATOR or not word.startswith("-") or word == "-":
        return []
    if word.startswith("--"):
        name = _camel(word[2:].partition("=")[0].removeprefix("no-")).partition(".")[0]
        valued = name in _JEST_VALUED
        return [_long_setting(word, following, valued=valued, takes=_yargs_takes(following))]
    if _YARGS_NEGATIVE.fullmatch(word):
        return []
    body = word[1:]
    if len(body) > 2 and body[1] == ".":
        return [Setting(body[0], dotted=True)]
    letters = body[:-1]
    found: list[Setting] = []
    for index, letter in enumerate(letters):
        after = letters[index + 1] if index + 1 < len(letters) else None
        rest = body[index + 1 :]
        if after == "=":
            return [*found, Setting(letter, body[index + 2 :])]
        if rest == "-":
            found.append(Setting(letter, rest))
            continue
        if letter.isalpha() and _YARGS_NUMBER.fullmatch(rest):
            return [*found, Setting(letter, rest)]
        if after is not None and not (after.isalnum() or after == "_"):
            return [*found, Setting(letter, rest)]
        found.append(Setting(letter, "" if letter in _JEST_VALUED_LETTERS else None))
    last = body[-1]
    if last == "-":
        return found
    if last in _JEST_VALUED_LETTERS and _yargs_takes(following):
        return [*found, Setting(last, following)]
    if following in _BOOLEAN_WORDS:
        return [*found, Setting(last, following)]
    return [*found, Setting(last, "" if last in _JEST_VALUED_LETTERS else None)]


# vitest 5.0.5's short options that take a value (`-c`, `-t`, `-r`, `-p`, and `-u`, whose value
# is optional); every other letter is a boolean.
_VITEST_VALUED_LETTERS = frozenset("ctrpu")
# vitest's options this reader reads a value for.
_VITEST_VALUED = frozenset({"config", "root", "update", "mergeReports"})


def vitest_settings(word: str, following: str | None) -> list[Setting]:
    """What vitest's parser (its own cac and mri) reads `word` as setting; `[]` for a word that is
    no option. Measured on vitest 5.0.5: every character of a cluster of short options up to a
    `=` is an option of its own (`-t.u` sets `-u`), and only the last takes the `=`'s value or
    the next word, which an option that takes a value takes unless it starts with `-`, and a
    boolean only where it is `true` or `false`."""
    if word == SEPARATOR or not word.startswith("-") or word == "-":
        return []
    takes = following is not None and not following.startswith("-")
    if word.startswith("--"):
        name = _camel(word[2:].partition("=")[0].removeprefix("no-")).partition(".")[0]
        return [_long_setting(word, following, valued=name in _VITEST_VALUED, takes=takes)]
    letters, _, value = word[1:].partition("=")
    found = [Setting(letter) for letter in letters[:-1]]
    last = letters[-1:]
    if not last:
        return found
    if value:
        given: str | None = value
    elif last in _VITEST_VALUED_LETTERS:
        given = following if takes else None
    else:
        given = following if following in _BOOLEAN_WORDS else None
    return [*found, Setting(last, given)]


def _settings(
    reader: Callable[[str, str | None], list[Setting]], args: Sequence[str]
) -> list[tuple[str, Setting]]:
    """Every option the words of `args` before a `--` set, each with the word that set it."""
    words = options(args)
    return [
        (word, setting)
        for index, word in enumerate(words)
        for setting in reader(word, words[index + 1] if index + 1 < len(words) else None)
    ]


def _yargs_on(setting: Setting) -> bool:
    """Whether yargs reads a boolean's setting as on: given no value, `true`, or an object."""
    return not setting.negated and (setting.dotted or setting.value in (None, "true"))


def _mri_on(setting: Setting) -> bool:
    """Whether vitest's parser reads a boolean's setting as on: anything but `--no-` or `false`."""
    return not setting.negated and setting.value != "false"


def _next(words: Sequence[str], index: int) -> str | None:
    return words[index + 1] if index + 1 < len(words) else None


def _config_values(settings: Sequence[tuple[str, Setting]]) -> list[str]:
    """Every configuration file `-c` or `--config` names among `settings`."""
    return [
        setting.value
        for _, setting in settings
        if setting.name in ("c", "config")
        and setting.value
        and not setting.negated
        and not setting.dotted
    ]


# What jest reads as a configuration's own text rather than a file's name: jest-config 30.5.2's
# `isJSONString`, a value that starts with `{` and ends with `}`, nothing stripped.
_CONFIG_TEXT = ("{", "}")


def jest_config_text(value: str) -> bool:
    """Whether jest reads a `--config` value as a configuration's own text, as its
    `isJSONString` does."""
    return value.startswith(_CONFIG_TEXT[0]) and value.endswith(_CONFIG_TEXT[1])


def _jest_configs(args: Sequence[str], cwd: Path) -> tuple[str, ...]:
    """The realpath of each configuration file jest's `-c` or `--config` names, read from `cwd`
    (measured on 30.5.2: whatever `--rootDir` says): an absolute entry of `Plan.configs`, which
    names that one file. A configuration's own text there names none."""
    values = _config_values(_settings(jest_settings, args))
    return tuple(os.path.realpath(cwd / value) for value in values if not jest_config_text(value))


# vitest's options that name the directory its configuration file is read from.
_VITEST_ROOT = frozenset({"root", "r"})


def _vitest_configs(args: Sequence[str], cwd: Path) -> tuple[str, ...]:
    """The realpath of each configuration file vitest's `-c` or `--config` names, read from the
    directory `-r` or `--root` names where the command gives one, itself read from `cwd`
    (measured on 5.0.5, in either order), else from `cwd`. A `--no-root`, a `--root.x` or an empty
    `--root=` names no directory here (vitest reads the first two as the directory `false` or
    stops, and the last as the directory `true`), and of two the last is taken (vitest stops at
    two, "Expected a single value", before any run)."""
    settings = _settings(vitest_settings, args)
    roots = [
        setting.value
        for _, setting in settings
        if setting.name in _VITEST_ROOT
        and not setting.negated
        and not setting.dotted
        and setting.value
    ]
    base = cwd / roots[-1] if roots else cwd
    return tuple(os.path.realpath(base / value) for value in _config_values(settings))


# jest's closed list, each a name as yargs reads it, past `--no-` and camel-casing: booleans
# refused where they are on.
_JEST_RUNS_NO_TEST = frozenset({"collectTests"})
_JEST_SNAPSHOTS = frozenset({"updateSnapshot", "u"})
# Its watch modes, not proven where they are on: they never end.
_JEST_NEVER_ENDS = frozenset({"watch", "watchAll"})


def jest_refused(args: Sequence[str]) -> str | None:
    """The first word of jest's `args` that sets an option on its closed list, as the receipt
    names it; `None` where none does."""
    settings = _settings(jest_settings, args)
    for word, setting in settings:
        name = setting.name
        if name in _JEST_RUNS_NO_TEST and _yargs_on(setting):
            return f"--{name}"
        if name in _JEST_SNAPSHOTS and _yargs_on(setting):
            return word if len(name) == 1 else f"--{name}"
    return None


def jest_never_ends(args: Sequence[str]) -> str | None:
    """The watch mode of jest's whose last setting in `args` turns it on, the later of the two
    where both are, as the receipt names it; `None` where none is. yargs keeps the last setting
    of an option, and each of the two watch modes is an option of its own (measured on 30.5.2:
    `--watch --no-watch` runs once, `--watchAll --watch=false` watches). One measured case it
    reads otherwise: `--watch --watchAll=false` ends (exit 0), and is read as `--watch`; not
    proven either way, so the cost is the receipt's word."""
    last: dict[str, tuple[int, Setting]] = {}
    for index, (_, setting) in enumerate(_settings(jest_settings, args)):
        if setting.name in _JEST_NEVER_ENDS:
            last[setting.name] = (index, setting)
    on = [(index, name) for name, (index, setting) in last.items() if _yargs_on(setting)]
    return f"--{max(on)[1]}" if on else None


# vitest's closed list: an option that reports results no test of this run produced.
_VITEST_REPORT_OPTIONS = frozenset({"mergeReports"})
# A boolean refused where it is on.
_VITEST_EXIT_PAST_ERRORS = frozenset({"dangerouslyIgnoreUnhandledErrors"})
_VITEST_SNAPSHOTS = frozenset({"update", "u"})
# The `--update` values that rewrite no failing snapshot: `none`, and `new`, vitest's own default
# where `CI` is unset, which writes a missing one (measured: `--update=false` is the text `false`,
# and rewrites them as `--update` does); `--no-update` is another spelling of `none`.
_VITEST_NO_UPDATE = "none"
_VITEST_NEW_ONLY = "new"
# Its watch mode, not proven where it is on: it never ends.
_VITEST_NEVER_ENDS = frozenset({"watch", "w"})
# The variable vitest 5.0.5 reads as `--update` where the command gives none: any value but the
# empty one, `none` and `new` rewrites a failing snapshot so that it passes (its `resolveConfig`
# reads the empty value as unset; measured).
_VITEST_UPDATE_VARIABLE = "UPDATE_SNAPSHOT"
_VITEST_KEEPS_SNAPSHOTS = frozenset({"", _VITEST_NO_UPDATE, _VITEST_NEW_ONLY})


def snapshots_rewritten(value: str) -> bool:
    """Whether vitest, given `UPDATE_SNAPSHOT=value`, rewrites a failing snapshot."""
    return value not in _VITEST_KEEPS_SNAPSHOTS


def vitest_refused(args: Sequence[str]) -> str | None:
    """The first word of vitest's `args` that sets an option on its closed list, as the receipt
    names it; `None` where none does."""
    settings = _settings(vitest_settings, args)
    for word, setting in settings:
        name = setting.name
        if name in _VITEST_REPORT_OPTIONS:
            return f"--{name}"
        if name in _VITEST_SNAPSHOTS and not (
            setting.negated
            or (setting.value in (_VITEST_NO_UPDATE, _VITEST_NEW_ONLY) and not setting.dotted)
        ):
            return word if len(name) == 1 else f"--{name}"
        if name in _VITEST_EXIT_PAST_ERRORS and _mri_on(setting):
            return f"--{name}"
    return None


def vitest_never_ends(args: Sequence[str]) -> str | None:
    """`-w` or `--watch`, as the receipt names the one whose setting turns vitest's watch mode on
    as its parser reads `args`; `None` where none does. Measured on vitest 5.0.5, as its mri reads
    them: a `--no-` setting replaces what came before it, a second setting after one makes two
    values, which vitest refuses before any run ("Expected a single value"), and `-w` and
    `--watch` are copied onto each other in the order they were first set, so `-w --no-watch`
    watches and `--no-watch -w` does not."""
    held: dict[str, list[tuple[str, Setting]]] = {}
    for word, setting in _settings(vitest_settings, args):
        if setting.name not in _VITEST_NEVER_ENDS:
            continue
        if setting.negated or setting.name not in held:
            held[setting.name] = [(word, setting)]
        else:
            held[setting.name].append((word, setting))
    final: list[tuple[str, Setting]] = []
    for name in list(held):
        for alias in _VITEST_NEVER_ENDS - {name}:
            held[alias] = final = held[name]
    if len(final) != 1 or not _mri_on(final[0][1]):
        return None
    name = final[0][1].name
    return f"-{name}" if len(name) == 1 else f"--{name}"


def _jest_ours(args: Sequence[str], report: Path) -> tuple[str, ...]:
    return ("--json", f"--outputFile={report}")


def _vitest_ours(args: Sequence[str], report: Path) -> tuple[str, ...]:
    settings = _settings(vitest_settings, args)
    ours: tuple[str, ...] = ("--reporter=json", f"--outputFile={report}")
    if not any(setting.name == _REPORTER for _, setting in settings):
        ours = (*ours, "--reporter=default")
    # `related` runs once under `--run`; vitest refuses a second setting of it before any run.
    if args[:1] == (_VITEST_RELATED,) and not any(setting.name == _RUN for _, setting in settings):
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
    for `run`, `related` and a first word that is no subcommand. Only the first word is read:
    vitest reads the first positional word, past its options, and a word after an option may be
    that option's value, so `vitest --globals watch` is planned as `run` with `watch` a filter:
    the run of the tests whose paths hold it, as `vitest run watch` would be, `failed` where none
    does."""
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
    configs=_jest_configs,
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
    configs=_vitest_configs,
    ours=_vitest_ours,
    words=_vitest_words,
)


_BIN_LINKS = ".bin"


# What a workspace pattern of `package.json` may hold for `_covers` to read it: npm reads it as a
# glob (`@npmcli/map-workspaces` 4.0.2, minimatch), and a negation, a brace, a class, an extended
# glob (`+(…)`, `@(…)`) or an escape is read here as one that cannot be told.
_UNREAD_GLOB = frozenset("!{}[]()\\")
_ANY_DEPTH = "**"


def _reaches(test: Callable[[Path], bool], path: Path) -> bool:
    """`test` (`fsops.is_file`, `fsops.is_dir`) of `path`, a path that cannot be asked about
    (`EACCES`) reaching nothing, as npm's own `stat` that fails reads it."""
    try:
        return test(path)
    except OSError:
        return False


def _segment_matches(pattern: str, name: str) -> bool:
    """Whether a pattern's segment, with `*` and `?` and nothing else special, matches `name` as
    minimatch does by default: neither reaches past a `/`, and neither matches a leading `.`."""
    if name.startswith(".") and not pattern.startswith("."):
        return False
    # A segment holds no `/` and, past `_UNREAD_GLOB`, no class: `fnmatch` reads it as minimatch.
    return fnmatch.fnmatchcase(name, pattern)


def _path_matches(pattern: Sequence[str], parts: Sequence[str]) -> bool:
    """Whether the segments of a pattern match the segments of a path, `**` any number of them
    that do not start with `.`."""
    if not pattern:
        return not parts
    head, rest = pattern[0], pattern[1:]
    if head == _ANY_DEPTH:
        return _path_matches(rest, parts) or (
            bool(parts) and not parts[0].startswith(".") and _path_matches(pattern, parts[1:])
        )
    return bool(parts) and _segment_matches(head, parts[0]) and _path_matches(rest, parts[1:])


def _covers(declared: object, parts: tuple[str, ...]) -> bool | None:
    """Whether the `workspaces` a `package.json` declares (a list of patterns, or a mapping whose
    `packages` is one) lists the directory at `parts` below it, as npm maps them; `None` where
    that cannot be told: a declaration npm itself refuses, a negated pattern, or a pattern past
    the glob this reads (`_UNREAD_GLOB`). npm never lists a directory inside a `node_modules`."""
    if isinstance(declared, dict) and isinstance(declared.get("packages"), list):
        declared = declared["packages"]
    if not isinstance(declared, list) or not all(isinstance(item, str) for item in declared):
        return None
    patterns = [
        [part for part in re.sub(r"^\.?/+", "", pattern).split("/") if part] for pattern in declared
    ]
    if any(_UNREAD_GLOB & set(pattern) for pattern in declared) or any(
        part in (".", "..") for segments in patterns for part in segments
    ):
        return None
    return _MODULES not in parts and any(_path_matches(segments, parts) for segments in patterns)


def npm_prefix(cwd: Path) -> Path | None:
    """The directory npm (11.6.0) runs a command run in `cwd` from, its local prefix: the nearest
    of `cwd` and the directories above it that holds a `package.json` or a `node_modules`, unless
    a `package.json` above that one lists it among its `workspaces`, where it is the nearest such
    workspace root (`@npmcli/config`'s `loadLocalPrefix`); `cwd` where none holds either. `None`
    where that cannot be told (`_covers`), or a `package.json` above is past what this reads."""
    here = Path(os.path.realpath(cwd))
    ancestors = (here, *here.parents)
    at = next(
        (
            index
            for index, directory in enumerate(ancestors)
            if _reaches(fsops.is_file, directory / _MANIFEST)
            or _reaches(fsops.is_dir, directory / _MODULES)
        ),
        None,
    )
    if at is None:
        return here
    prefix = ancestors[at]
    if not _reaches(fsops.is_file, prefix / _MANIFEST):
        return prefix
    for root in ancestors[at + 1 :]:
        if not _reaches(fsops.is_file, root / _MANIFEST):
            continue
        try:
            data, more = fsops.read_bounded(root / _MANIFEST, _MANIFEST_BYTES)
        except OSError:
            continue
        if more:
            return None
        try:
            manifest = json.loads(data)
        except (ValueError, RecursionError):
            continue
        declared = manifest.get("workspaces") if isinstance(manifest, dict) else None
        if declared is None or declared is False or declared in ("", 0):
            continue
        covered = _covers(declared, prefix.relative_to(root).parts)
        if covered is None:
            return None
        if covered:
            return root
    return prefix


def npx_bin(name: str, cwd: Path) -> Path | None:
    """The realpath of the `node_modules/.bin/<name>` npx runs for a command run in `cwd`: the
    first that reaches a file, in npm's local prefix (`npm_prefix`) and then in each directory
    above it up to the file system's root (measured with npm 11.6.0: the nearest wins, the walk
    goes on past a directory's own `package.json`, in a workspace it starts at the workspace's
    root, and the file run is the link's target, or the file itself where it is no link); `None`
    where there is none, or where the prefix cannot be told."""
    prefix = npm_prefix(cwd)
    if prefix is None:
        return None
    for directory in (prefix, *prefix.parents):
        candidate = directory / _MODULES / _BIN_LINKS / name
        if _reaches(fsops.is_file, candidate):
            return Path(os.path.realpath(candidate))
    return None


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
) -> list[tuple[tuple[str, ...], str, tuple[str, ...]]]:
    """Each way `command` reads as `node [node's options] <entry> [the runner's arguments]`, the
    entry a word node may run as its script (`_node_read`) that is a path into
    `node_modules/<package>` (a package of `packages`) or `node_modules/.bin/<name>`: node's
    options, the entry as given, and the runner's arguments, in the order of the words; none for
    any other command, and for one whose node options name `--test`, which runs node's test
    runner. Which of them is the entry the package's `bin` names is the plan's to check, from
    where the command runs."""
    if not command or Path(command[0]).name != _NODE:
        return []
    words = tuple(command[1:])
    options, scripts = _node_read(words)
    if _TEST in options:
        return []
    return [
        (words[:index], words[index], words[index + 1 :])
        for index in scripts
        if _entry_shaped(words[index], name, packages)
    ]


# node's options that load a module before the tests run: free (TypeScript through `tsx`,
# Plug'n'Play's `.pnp.cjs`), and where the value is a path rather than a package's name, the file
# is named among the configuration files. Measured on 26.12.0: `-r` takes its value as the next
# word only (`-r=x` is a bad option); the others take it either way; a `file:` URL names a file.
_NODE_PRELOADS = frozenset({"--require", "--import", "--loader", "--experimental-loader"})
_NODE_PRELOAD_LETTER = "-r"
_PATH_STARTS = ("/", "./", "../")
_FILE_SCHEME = "file"
# The hosts a `file:` URL may name and still name a file of this machine, and where an absolute
# path starts.
_LOCAL_HOSTS = frozenset({"", "localhost"})
_ROOT = "/"
# The characters that make a path's reading ambiguous: node reads an ES module preload's path as a
# URL, where `%`, `?` and `#` change the file it names, and a `\\` or a control character is read
# differently again. A path holding one is not named; it runs as it is.
_AMBIGUOUS = frozenset("%?#\\") | frozenset(map(chr, range(32))) | {chr(127)}


def _node_name(word: str) -> str:
    """An option word's name as node reads it: up to an `=`, every `_` read as `-`."""
    return word.partition("=")[0].replace("_", "-")


def _url(value: str) -> SplitResult | None:
    """`value` split as a URL, `None` where it is none (`urlsplit` refuses `http://[x`)."""
    try:
        return urlsplit(value)
    except ValueError:
        return None


def _preloaded_file(given: str, cwd: Path) -> str | None:
    """The realpath of the file a preload option's value names, where its reading is not in
    doubt: a path starting `/`, `./` or `../` with none of `_AMBIGUOUS` in it, read from `cwd`;
    an absolute `file:` URL of this machine, its path percent-decoded. `None` for anything else
    -- a package's name, a URL of another scheme, a relative `file:` URL or another host's, a path
    holding `%`, `?`, `#`, `\\` or a control character -- which is not named: naming is the
    receipt's convenience, no verdict reads it, and a file in the tree is the bound's."""
    if given.startswith(_PATH_STARTS):
        return None if _AMBIGUOUS & set(given) else os.path.realpath(cwd / given)
    url = _url(given)
    if url is None or url.scheme != _FILE_SCHEME or url.netloc not in _LOCAL_HOSTS:
        return None
    if not url.path.startswith(_ROOT):
        return None
    decoded = unquote(url.path)
    # `%00` decodes to a NUL, which names no file and which the path calls refuse.
    return None if "\0" in decoded else os.path.realpath(decoded)


def node_preloaded(words: Sequence[str], cwd: Path) -> tuple[str, ...]:
    """The realpath of each file node's `-r`, `--require`, `--import` or `--loader` names in
    `words` (the words after `node`), read from `cwd`: an absolute entry of `Plan.configs`. A
    package's name (`tsx`, `ts-node/register`) names no file of the project's and is left out."""
    given_options = options(words)
    found: list[str] = []
    for index, word in enumerate(given_options):
        name, equals, value = word.partition("=")
        name = name.replace("_", "-")
        if name == _NODE_PRELOAD_LETTER and not equals:
            given = _next(given_options, index)
        elif name in _NODE_PRELOADS:
            given = value if equals else _next(given_options, index)
        else:
            continue
        named = _preloaded_file(given, cwd) if given is not None else None
        if named is not None:
            found.append(named)
    return tuple(found)


# node's closed list: the test runner's options that rewrite a failing snapshot, or report tests
# that never ran as passed.
_NODE_REFUSED = frozenset({"--test-update-snapshots", "--test-rerun-failures"})
NODE_OPTIONS = "NODE_OPTIONS"
# node's watch modes, not proven: they never end. `--no-watch` turns `--watch` off again.
_NODE_WATCH = "--watch"
_NODE_WATCH_PATH = "--watch-path"
_NODE_NO_WATCH = "--no-watch"
# node's options that hold the code until a debugger attaches, which under `prove` none does
# (measured on Node 24.10.0, before a script and under `--test` alike: past any time limit):
# jest's documented recipe for debugging, `node --inspect-brk node_modules/.bin/jest`.
_NODE_INSPECT_WAITS = ("--inspect-brk", "--inspect-wait")


def node_options_words(value: str) -> list[str]:
    """The words `NODE_OPTIONS=value` hands node, split as node splits them: at spaces outside
    double quotes, each quote dropped, and inside quotes a backslash taking the character after
    it as it is (measured on Node 24.10.0: `--title="a b"` sets the title `a b`)."""
    words: list[str] = []
    word: list[str] | None = None
    quoted = False
    escaped = False
    for character in value:
        if escaped:
            escaped = False
        elif character == "\\" and quoted:
            escaped = True
            continue
        elif character == '"':
            quoted = not quoted
            word = word if word is not None else []
            continue
        elif character == " " and not quoted:
            if word is not None:
                words.append("".join(word))
            word = None
            continue
        word = word if word is not None else []
        word.append(character)
    if word is not None:
        words.append("".join(word))
    return words


def node_refused(words: Sequence[str], node_options: str = "") -> str | None:
    """The first of node's options on its closed list, by its name, never its value, among
    `words` (the words after `node`) and then `node_options` (the run's `NODE_OPTIONS`, which node
    reads as options given first: Node 24.10.0 runs `--test-rerun-failures` from there, and
    refuses `--test-update-snapshots` there itself); `None` where none is. Every word before a
    `--` is read, a file's name among them: Node 26.12.0 reads an option written after the files
    under `--test` as before them (Node 24.10.0 reads none there, measured, so there the refusal
    is only the safe side)."""
    names = [_node_name(word) for word in (*options(words), *node_options_words(node_options))]
    return next((name for name in names if name in _NODE_REFUSED), None)


def node_never_ends(words: Sequence[str], node_options: str = "") -> str | None:
    """node's option among `words` (the words after `node`) under which the run never ends, by
    its name, read as `node_refused` reads: `--watch-path` wherever it is (measured on 26.12.0:
    under `--test` node refuses to run with it), else `--inspect-brk` or `--inspect-wait`, there or
    in `node_options` (the run's `NODE_OPTIONS`, which reaches every node the run starts, `npx`'s
    and a runner's script's too), else `--watch` where the last of `--watch` and `--no-watch` is
    it; `None` where none is. `--watch` in `NODE_OPTIONS` is node's own error (measured on
    24.10.0)."""
    names = [_node_name(word) for word in options(words)]
    if _NODE_WATCH_PATH in names:
        return _NODE_WATCH_PATH
    waiting = (*names, *(_node_name(word) for word in node_options_words(node_options)))
    waits = next((name for name in waiting if name in _NODE_INSPECT_WAITS), None)
    if waits is not None:
        return waits
    settings = [name for name in names if name in (_NODE_WATCH, _NODE_NO_WATCH)]
    return _NODE_WATCH if settings[-1:] == [_NODE_WATCH] else None


def never_ends(option: str) -> Unresolved:
    """`NEVER_ENDS` for `option`, a watch mode's or one of node's that waits for a debugger
    (`node_never_ends`), its detail saying which of the two it is."""
    detail = WAITS_DETAIL if option in _NODE_INSPECT_WAITS else NEVER_ENDS_DETAIL
    return Unresolved(NEVER_ENDS, detail.format(option=option))


@dataclass(frozen=True)
class _Typed:
    """A recognised run of a package's runner, as typed: the command's words up to the runner's
    arguments (`npx --no-install jest`, `./node_modules/.bin/jest`, `node --inspect
    node_modules/jest/bin/jest.js`), node's own options where node runs the entry, the runner's
    arguments, and the realpath of the entry where it is named."""

    head: tuple[str, ...]
    node_words: tuple[str, ...]
    args: tuple[str, ...]
    entry: Path | None


def _typed(
    command: Sequence[str], runner: _Runner, *, cwd: Path, environ: Mapping[str, str]
) -> _Typed | Unresolved | None:
    """`command` read as a run of `runner`: the runner bare or after `npx` (its entry what
    `npx_bin` names, for `npx`); a path to the runner as the first word, run as typed (its entry
    named where it is a link to the file its package's `bin` names, `_linked`); or the first word
    after `node` that may be its script and is, by its realpath, the entry (`node_entry`).
    `ENTRY_NOT_FOUND` where no word after `node` is that entry, since nothing then tells that the
    file node runs is the runner's; `None` for a command that is none of them."""
    args = runner_args(command, runner.name)
    if args is not None:
        head = tuple(command[: len(command) - len(args)])
        entry = npx_bin(runner.name, cwd) if head[0] == _NPX else None
        return _Typed(head, (), args, entry)
    args = linked_args(command, runner.name)
    if args is not None:
        return _Typed((command[0],), (), args, _linked(command[0], runner.name, cwd, environ))
    ways = node_entry(command, runner.name, runner.packages)
    if not ways:
        return None
    for node_words, script, rest in ways:
        entry = package_entry(Path(os.path.realpath(cwd / script)), runner.name)
        if entry is not None:
            return _Typed((command[0], *node_words, script), node_words, rest, entry)
    return Unresolved(ENTRY_NOT_FOUND, NOT_THE_ENTRY.format(package=runner.packages[0]))


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
        runner = self._runner
        return (
            runner_args(command, runner.name) is not None
            or linked_args(command, runner.name) is not None
            or bool(node_entry(command, runner.name, runner.packages))
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
        runner = self._runner
        typed = _typed(command, runner, cwd=cwd, environ=environ)
        if not isinstance(typed, _Typed):
            return typed or Unresolved(ENTRY_NOT_FOUND)
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
        # The receipt names the program by its realpath; an entry that is the program is not
        # named twice (a `.bin` link run as typed).
        entry = typed.entry
        if entry is not None and os.path.realpath(argv[0]) == str(entry):
            entry = None
        return Plan(
            argv=argv,
            kind=ReportKind.RESULTS_JSON,
            source=ReportSource.FILE,
            report=report,
            discovery=runner.discovery,
            configs=(*CONFIGS, *runner.configs(args, cwd), *node_preloaded(node_words, cwd)),
            entry=entry,
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
            configs=(*CONFIGS, *node_preloaded(command[1:], cwd)),
            drop=whole_file(cwd),
        )


ADAPTERS = (JestAdapter(), VitestAdapter(), NodeTestAdapter())
