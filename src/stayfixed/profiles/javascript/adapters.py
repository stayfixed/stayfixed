"""JavaScript's runner adapters: a jest, vitest or `node --test` run, proved from the report the
runner writes to a file `prove` hands it.

**What is recognised.** `jest` and `vitest`, bare or after `npx`, `npx --no-install` or `npx --no`,
or as `node [node's options] <entry> …`, the entry a path into `node_modules/<package>` or
`node_modules/.bin/<runner>` (`node_entry`), which must be, by its realpath, the file its
package's `bin` names; and `node` (or a path to one) with `--test` among its options. `npm test`,
`npm run`, `yarn`, `pnpm` and every other package manager's script runner are recognised by none
of them: what a script runs is the script's, never read here, and `prove --junit` counts its
report.

**No `npx` is executed, and no package manager's shim is.** The entry point is found the way Node
finds a package: `node_modules/<package>/package.json` in the directory the command runs in, then
in each directory above it up to the project's top-level (`jest`, then `jest-cli`; `vitest`), its
`bin` (a string, or a mapping holding the runner's name) naming the entry, a file inside the
package. Then the runner's name on `PATH`, where the first one found is a symbolic link to a file a
package's `bin` names, as npm links a global install. A `.bin` file or a `PATH` entry that is not a
link (pnpm's `sh` shim, Yarn Plug'n'Play's) is never read or run, and nothing is installed: no entry
found is `ENTRY_NOT_FOUND`, whose detail names `prove --junit` as the way on. The run is `[<node>,
<entry's realpath>, …]`, `<node>` the first `node` on the run's `PATH`; `--test` runs that `node`
too, or the one the command names by its path (`stayfixed.profiles.programs.found`). Behind a
launcher the core read past (`uv run …`), its words are kept in front, the program is the
launcher's realpath, and the `node` it is handed is the one found, by that path.

**The report.** jest: `--json --outputFile=<report>`. vitest: `run` first where the command's
first word is none of vitest's subcommands, so it runs once; `related` kept, with `--run` where the
command does not set it; `watch` and `dev` are `NEVER_ENDS`, and `bench`, `list`, `init` and
`doctor`, which run no test suite that reports, `NO_TEST_RUN` (`vitest_unplanned`); then
`--reporter=json --outputFile=<report>`, and
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
  rewrites the results before they are written), `-c`/`--config` given a configuration's own text (a
  value jest's `isJSONString` reads as JSON, which can set `testResultsProcessor` in the command
  itself and names no file the receipt could name), `-u`/`--updateSnapshot` (which rewrites a
  failing snapshot so that it passes), and `--collectTests` (which exits 0 reporting a failing
  test as passed). `--ci=false`/`--no-ci` is free: jest then writes a snapshot that is missing and
  passes it, as it does by default wherever `CI` is unset or false, and a snapshot the run writes
  is the bound's, as deleting the snapshot file is.
- vitest 5.0.5: `--outputFile` in any form, `-u`/`--update` but `--update=none`, `--no-update`
  and `--update=new` (each other rewrites a failing snapshot so that it passes; `new`, vitest's
  own default where `CI` is unset, only writes a missing one), `--mergeReports` (which runs
  nothing and reports the blob files it reads as results), and
  `--dangerouslyIgnoreUnhandledErrors` (which exits 0 past an error no test reported).
- `node --test` on Node 26.12.0: any `--test-reporter…` of the command's own; `--env-file`,
  `--env-file-if-exists` and the configuration file options (`--config-file`,
  `--experimental-config-file`, `--experimental-default-config-file`), which load what the run
  reads; code the command spells, `-e`/`--eval`, `-p`/`--print`, and a preload given a URL of any
  scheme but `file:` (`inline_preload`), a `data:` URL among them, which runs before the tests and
  can write the report, as jest's `--config` given JSON text is;
  `--test-update-snapshots` (which rewrites a failing snapshot so that it passes); and
  `--test-rerun-failures` (which reports as passed, unrun, every test the state file it names says
  passed before). Node reads an option written with `_` as with `-`, and after the files under
  `--test` as before them, and so are these.

A watch mode -- jest's `--watch` and `--watchAll`, vitest's `-w`/`--watch`, node's `--watch` and
`--watch-path` -- moves no report and forges no pass, but it never ends: it waits for changes
after the run, so no report is ever finished. It is not refused, which is for a command that
steers the report; it is `NEVER_ENDS` (`not proven`), naming the option, read as the closed lists
are, and a refusal in the same command wins.

`-r`/`--require`, `--import` and `--loader` are free (TypeScript through `tsx`, Plug'n'Play's
`.pnp.cjs`) but for code the command spells, above; where one is given a path or an absolute
`file:` URL whose reading is not in doubt, that file is named among the receipt's configuration
files by its realpath (`_preloaded_file`), and any other value runs as it is, unnamed: the name is
the receipt's convenience, and a file in the tree is the bound's.

Each reader follows the runner's own parser, measured on the pinned version: jest's yargs (a short
option in a cluster takes the rest of the word as its value after a `=`, a character other than a
letter, digit or `_`, or a number, so `-c/etc/x.js` names `/etc/x.js`; a boolean takes `true` or
`false` as its next word, so `-u false` is off, and any `=` value but `true` turns it off);
vitest's cac (every character of a short cluster up to a `=` is an option of its own, so `-t.u` sets
`-u`; a boolean is off only by `--no-` or `false`, and `--update=false` is the text `false`, which
rewrites snapshots as `--update` does).

`-c`/`--config` naming a file is free for both: a configuration the command names outside the
project is one the same agent could write inside it, which is the bound's, so a refusal of it would
stop nobody. The file it names is named among the receipt's configuration files by its realpath
(`Plan.configs`), read from the directory the command runs in for jest, and from vitest's `--root`
where the command gives one; a configuration's own text jest is given there is refused, above. Every
other option that names code to load or where to look -- jest's `--setupFiles`, `--globalSetup`,
`--testRunner`, `--testEnvironment`, `--projects`, `--rootDir`, `--roots` and `--reporters`,
vitest's `--root`, `--dir` and `--setupFiles` -- is free too, since the code it loads is the bound's
and the lists stay closed.

`FORGING`, assigned in the command (refused) or inherited (scrubbed): `NODE_OPTIONS`, which Node
reads as options of every run, `--require` and the reporters among them; for `node --test` also
`NODE_TEST_CONTEXT`, under which it runs no file and exits 0 (measured on 26.12.0, any value). The
scrub can turn a legitimate run red (jest's ES modules recipe sets `NODE_OPTIONS`), so the receipt
names it, and node's flags are given in front of the entry instead (`node --experimental-vm-modules
node_modules/jest/bin/jest.js`). There node's options are read from a closed list of its own,
drawn from `node --help` on Node 26.12.0 (`_entry_options`): an option outside it, or a valued one
given its value as the next word, would make the entry that option's value and the next word the
script node runs, so the command is recognised by none rather than guessed. Of the list, the same
options `node --test` refuses (files loaded, code spelled) and node's test runner's own (any
`--test…`) are `REFUSED_OPTION`, and its watch modes `NEVER_ENDS`. The adversary is the agent
typing the command, the anchor its words, as for every list here.

What a file in the tree can do -- a configuration's reporters, `testResultsProcessor` or setup
files, a test that writes the report, a `package.json` that points `bin` elsewhere -- is the
bound's: the receipt names the configuration files (`CONFIGS`) and the untracked files each runner
collects from (`*_DISCOVERY`), and the realpath of the `node` that ran.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import SplitResult, unquote, urlsplit

from stayfixed import fsops
from stayfixed.profiles.programs import before_separator, found, launched
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
# The reason a vitest subcommand that runs no test suite is not proven, and its detail.
NO_TEST_RUN = "no-test-run"
# The reasons these adapters name: `stayfixed.profiles.runners`' three (an option a closed list
# refuses, an entry point that does not resolve from where the command runs, a watch mode), and
# their own, a vitest subcommand that runs no test suite.
REASONS = (REFUSED_OPTION, ENTRY_NOT_FOUND, NEVER_ENDS, NO_TEST_RUN)
NO_TEST_RUN_DETAIL = (
    "vitest {subcommand} runs no test suite that reports; prove `vitest run` instead"
)
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
# vitest 5.0.5's subcommands, which its parser reads in the first positional word: `run` runs
# once; `related` runs the tests that import the files it names, once under `--run`; `watch` and
# `dev` watch; `bench`, `list`, `init` and `doctor` run no test suite that reports (benchmarks; a
# list of the tests collected; a project scaffold; the suite timed under each pool, no report).
_VITEST_RELATED = "related"
_VITEST_WATCHING = frozenset({"watch", "dev"})
_VITEST_NO_TEST_RUN = frozenset({"bench", "list", "init", "doctor"})
_VITEST_SUBCOMMANDS = frozenset({_RUN, _VITEST_RELATED, *_VITEST_WATCHING, *_VITEST_NO_TEST_RUN})

# Short enough for the receipt's line to carry whole (`printed.CLIPPED_CHARS`).
UNRESOLVED = (
    "no node_modules/{package} up to the top-level, nor a {bin} on PATH linked into one; "
    "`prove --junit` counts a report"
)
_NO_NODE = "no node on PATH"
_NO_LAUNCHER = "no {launcher} on PATH"
# Where `node` is handed a file that is not the entry its package's `bin` names.
NOT_THE_ENTRY = (
    "the file node is given is not the entry a {package} package's bin names; "
    "`prove --junit` counts a report you name"
)


def _launched(
    launch: Sequence[str], argv: tuple[str, ...], cwd: Path, environ: Mapping[str, str]
) -> tuple[str, ...] | Unresolved:
    """The argv that runs `argv`, its program a `node` already found, behind `launch`, the
    launcher's words kept in front (`stayfixed.profiles.programs.launched`)."""
    planned = launched(launch, argv, cwd, environ)
    if planned is None:
        return Unresolved(ENTRY_NOT_FOUND, _NO_LAUNCHER.format(launcher=Path(launch[0]).name))
    return planned


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
    # A NUL names no file: the path calls refuse it (`ValueError`), and a manifest may hold one.
    if not isinstance(declared, str) or not declared or "\0" in declared:
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


def _linked(name: str, cwd: Path, environ: Mapping[str, str]) -> Path | None:
    """The entry the first `name` on `environ`'s `PATH` links to, where it is a link to a file a
    package's `bin` names for `name`; a file that is not a link is never read."""
    on_path = found(name, cwd, environ)
    if on_path is None or not fsops.is_symlink(on_path):
        return None
    return package_entry(Path(os.path.realpath(on_path)), name)


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
    its report, its closed list and how its report options read."""

    name: str
    packages: tuple[str, ...]
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
    `npx`, `npx --no-install` or `npx --no`; else `None`."""
    words = list(command)
    if words[:1] == [_NPX]:
        words = words[1:]
        if words[:1] and words[0] in _NPX_OFFLINE:
            words = words[1:]
    if words[:1] != [name]:
        return None
    return tuple(words[1:])


def _options(args: Sequence[str]) -> list[str]:
    """The words of `args` before a `--`, which ends a runner's options."""
    words = list(args)
    return words[: words.index(_SEPARATOR)] if _SEPARATOR in words else words


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
# jest's options this reader reads a value for: the configuration file, and the booleans on its
# closed list, which take `true` or `false` as their next word.
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
    if word == _SEPARATOR or not word.startswith("-") or word == "-":
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
_VITEST_VALUED = frozenset({"config", "root", "update", "mergeReports", "outputFile"})


def vitest_settings(word: str, following: str | None) -> list[Setting]:
    """What vitest's parser (its own cac and mri) reads `word` as setting; `[]` for a word that is
    no option. Measured on vitest 5.0.5: every character of a cluster of short options up to a
    `=` is an option of its own (`-t.u` sets `-u`), and only the last takes the `=`'s value or
    the next word, which an option that takes a value takes unless it starts with `-`, and a
    boolean only where it is `true` or `false`."""
    if word == _SEPARATOR or not word.startswith("-") or word == "-":
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
    words = _options(args)
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
    names that one file. A configuration's own text there was refused before the plan."""
    values = _config_values(_settings(jest_settings, args))
    return tuple(os.path.realpath(cwd / value) for value in values)


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


# jest's closed list, each a name as yargs reads it, past `--no-` and camel-casing.
_JEST_REPORT_OPTIONS = frozenset({"json", "outputFile", "testResultsProcessor"})
# Booleans refused where they are on.
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
        if name in _JEST_REPORT_OPTIONS:
            return f"--{name}"
        if name in _JEST_RUNS_NO_TEST and _yargs_on(setting):
            return f"--{name}"
        if name in _JEST_SNAPSHOTS and _yargs_on(setting):
            return word if len(name) == 1 else f"--{name}"
    if any(jest_config_text(value) for value in _config_values(settings)):
        return "--config"
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


# vitest's closed list.
_VITEST_REPORT_OPTIONS = frozenset({"outputFile", "mergeReports"})
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
    discovery=VITEST_DISCOVERY,
    report_name=VITEST_REPORT,
    refused=vitest_refused,
    never_ends=vitest_never_ends,
    unplanned=vitest_unplanned,
    configs=_vitest_configs,
    ours=_vitest_ours,
    words=_vitest_words,
)


def entry_point(
    name: str, packages: Sequence[str], cwd: Path, root: Path, environ: Mapping[str, str]
) -> Path | None:
    """The realpath of the runner `name`'s entry: a package of `packages` under `node_modules` from
    `cwd` up to `root`, nearest first and each directory's packages in order; else the first `name`
    on `environ`'s `PATH`, where it links to a file a package's `bin` names."""
    for directory in _upward(cwd, root):
        for package in packages:
            entry = _manifest_bin(directory / _MODULES / package, name)
            if entry is not None:
                return entry
    return _linked(name, cwd, environ)


_BIN_LINKS = ".bin"
# node's test runner's options, refused in front of a runner's entry: any `--test…`.
_NODE_TEST_RUNNER = "--test"
# node's options that run code the command spells, never the script: refused wherever node reads
# them, as jest's `--config` given a configuration's own text is.
_NODE_INLINE_CODE = frozenset({"-e", "--eval", "-p", "--print", "-pe"})
# The options node may be given in front of a runner's entry: a closed list, drawn from
# `node --help` on Node 26.12.0, of the switches that change how the code under test runs and
# never what node runs. A word outside it, or one of `_ENTRY_VALUED` spelled with its value as the
# next word, makes the command one no adapter recognises: an option node takes a value for, read as
# a switch, would make the entry its value and the next word the script node runs.
_ENTRY_SWITCHES = frozenset(
    {
        "--abort-on-uncaught-exception",
        "--disallow-code-generation-from-strings",
        "--enable-source-maps",
        "--experimental-import-meta-resolve",
        "--experimental-strip-types",
        "--experimental-vm-modules",
        "--expose-gc",
        "--frozen-intrinsics",
        "--jitless",
        "--no-addons",
        "--no-deprecation",
        "--no-experimental-detect-module",
        "--no-experimental-require-module",
        "--no-experimental-strip-types",
        "--no-global-search-paths",
        "--no-require-module",
        "--no-warnings",
        "--openssl-legacy-provider",
        "--pending-deprecation",
        "--preserve-symlinks",
        "--preserve-symlinks-main",
        "--require-module",
        "--throw-deprecation",
        "--trace-deprecation",
        "--trace-exit",
        "--trace-promises",
        "--trace-sigint",
        "--trace-uncaught",
        "--trace-warnings",
        "--use-bundled-ca",
        "--use-openssl-ca",
        "--use-system-ca",
        "--zero-fill-buffers",
        # The watch modes, which never end (`node_never_ends`): read, so as to be said, as the
        # test runner's switches and the file loaders are, which are refused.
        "--watch",
        "--no-watch",
    }
)
# node's options in front of a runner's entry that take a value, accepted given it with `=` only.
_ENTRY_VALUED = frozenset(
    {
        "--conditions",
        "--disable-proto",
        "--disable-warning",
        "--dns-result-order",
        "--max-http-header-size",
        "--max-old-space-size",
        "--max-old-space-size-percentage",
        "--title",
        "--unhandled-rejections",
    }
)


def _entry_options(words: Sequence[str]) -> tuple[list[tuple[str, str | None]], int] | None:
    """node's options at the start of `words` (the words after `node`), each by its name and its
    value, and how many words they take; `None` where one is outside the closed list node may be
    given in front of a runner's entry, or is a valued one spelled with its value as the next word
    that the list does not take that way. The preloads, the inline code options and those node
    refuses to load a file or run its test runner with take their value either way, as node reads
    them."""
    read: list[tuple[str, str | None]] = []
    index = 0
    while index < len(words):
        word = words[index]
        if word in (_SEPARATOR, "-") or not word.startswith("-"):
            break
        name, equals, value = word.partition("=")
        name = name.replace("_", "-")
        spaced = (
            name in _NODE_PRELOADS
            or name in (_NODE_PRELOAD_LETTER, _NODE_WATCH_PATH)
            or name in _NODE_INLINE_CODE
            or (
                name in _NODE_VALUED
                and (name in _NODE_REFUSED or name.startswith(_NODE_TEST_RUNNER))
            )
        )
        refused = name in _NODE_REFUSED or name.startswith(_NODE_TEST_RUNNER)
        if equals and (name in _ENTRY_VALUED or spaced):
            read.append((name, value))
            index += 1
        elif not equals and spaced:
            if index + 1 >= len(words):
                return None
            read.append((name, words[index + 1]))
            index += 2
        elif not equals and (name in _ENTRY_SWITCHES or refused):
            read.append((name, None))
            index += 1
        else:
            return None
    return read, index


def node_entry(
    command: Sequence[str], name: str, packages: Sequence[str]
) -> tuple[tuple[str, ...], str, tuple[str, ...]] | None:
    """`command` read as `node [node's options] <entry> [the runner's arguments]`, where the entry
    is a path into `node_modules/<package>` (a package of `packages`) or `node_modules/.bin/<name>`:
    node's options, the entry as given, and the runner's arguments; `None` for any other command,
    and for one whose node options are not all on the closed list `_entry_options` reads. Whether
    the path is the entry the package's `bin` names is the plan's to check, from where the command
    runs."""
    if not command or Path(command[0]).name != _NODE:
        return None
    words = tuple(command[1:])
    parsed = _entry_options(words)
    if parsed is None:
        return None
    _, index = parsed
    if index >= len(words) or words[index] in (_SEPARATOR, "-"):
        return None
    script = words[index]
    parts = Path(script).parts
    for at, part in enumerate(parts[:-1]):
        if part != _MODULES:
            continue
        after = parts[at + 1 :]
        if after[0] in packages and len(after) > 1:
            return words[:index], script, words[index + 1 :]
        if after == (_BIN_LINKS, name):
            return words[:index], script, words[index + 1 :]
    return None


def _node_entry_refused(options: Sequence[str]) -> str | None:
    """The first of node's options in front of a runner's entry that runs code the command spells
    (`-e`, a preload of inline code), loads a file the command names, or runs node's test runner,
    by its name, never its value; `None` where none does."""
    parsed = _entry_options(options)
    for name, value in parsed[0] if parsed is not None else []:
        if name in _NODE_INLINE_CODE or name.startswith(_NODE_TEST_RUNNER) or name in _NODE_REFUSED:
            return name
        preload = name in _NODE_PRELOADS or name == _NODE_PRELOAD_LETTER
        if preload and value is not None and inline_preload(value):
            return name
    return None


class _PackageRunner:
    """`RunnerAdapter` for a runner a package ships, run by `node` from its entry point: found by
    the search `entry_point` makes, or named after `node` and node's own options."""

    def __init__(self, runner: _Runner) -> None:
        self._runner = runner

    @property
    def name(self) -> str:
        return self._runner.name

    @property
    def forging(self) -> frozenset[str]:
        return FORGING

    def recognises(self, command: Sequence[str]) -> bool:
        runner = self._runner
        return (
            runner_args(command, runner.name) is not None
            or node_entry(command, runner.name, runner.packages) is not None
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
        runner = self._runner
        args = runner_args(command, runner.name)
        node_words: tuple[str, ...] = ()
        script: str | None = None
        if args is None:
            named = node_entry(command, runner.name, runner.packages)
            if named is None:
                return Unresolved(ENTRY_NOT_FOUND)
            node_words, script, args = named
            refused_by_node = _node_entry_refused(node_words)
            if refused_by_node is not None:
                return Refused(REFUSED_OPTION, refused_by_node)
        refused = runner.refused(args)
        if refused is not None:
            return Refused(REFUSED_OPTION, refused)
        never = node_never_ends(node_words) or runner.never_ends(args)
        if never is not None:
            return Unresolved(NEVER_ENDS, NEVER_ENDS_DETAIL.format(option=never))
        unplanned = runner.unplanned(args)
        if unplanned is not None:
            return unplanned
        if script is None:
            entry = entry_point(runner.name, runner.packages, cwd, root, environ)
            if entry is None:
                detail = UNRESOLVED.format(package=runner.packages[0], bin=runner.name)
                return Unresolved(ENTRY_NOT_FOUND, detail)
        else:
            entry = package_entry(Path(os.path.realpath(cwd / script)), runner.name)
            if entry is None:
                detail = NOT_THE_ENTRY.format(package=runner.packages[0])
                return Unresolved(ENTRY_NOT_FOUND, detail)
        node = found(command[0] if script is not None else _NODE, cwd, environ)
        if node is None:
            return Unresolved(ENTRY_NOT_FOUND, _NO_NODE)
        report = scratch / runner.report_name
        words = runner.words(args)
        planned = before_separator(words, runner.ours(words, report))
        argv = _launched(launch, (str(node), *node_words, str(entry), *planned), cwd, environ)
        if isinstance(argv, Unresolved):
            return argv
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
        "-e",
        "--eval",
        "-p",
        "--print",
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
    }
)
# node's watch modes, not proven: they never end. `--no-watch` turns `--watch` off again.
_NODE_WATCH = "--watch"
_NODE_WATCH_PATH = "--watch-path"
_NODE_NO_WATCH = "--no-watch"


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


def inline_preload(value: str) -> bool:
    """Whether a preload option's value (`-r`, `--require`, `--import`, `--loader`,
    `--experimental-loader`) is code the command spells: a URL of any scheme but `file:`, a
    `data:` URL among them, which node runs before the tests and which can write the report, as
    jest's `--config` given JSON text can. The only refusal of a preload: every other value runs
    as it is. A value no URL parser reads (`x://]`) is no URL: node cannot load it either."""
    url = _url(value)
    return url is not None and bool(url.scheme) and url.scheme != _FILE_SCHEME


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
    -- a package's name, a relative `file:` URL or another host's, a path holding `%`, `?`, `#`,
    `\\` or a control character -- which is not named: naming is the receipt's convenience, no
    verdict reads it, and a file in the tree is the bound's."""
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
    options = _options(words)
    found: list[str] = []
    for index, word in enumerate(options):
        name, equals, value = word.partition("=")
        name = name.replace("_", "-")
        if name == _NODE_PRELOAD_LETTER and not equals:
            given = _next(options, index)
        elif name in _NODE_PRELOADS:
            given = value if equals else _next(options, index)
        else:
            continue
        named = _preloaded_file(given, cwd) if given is not None else None
        if named is not None:
            found.append(named)
    return tuple(found)


def node_refused(words: Sequence[str]) -> str | None:
    """The first word of `words` (the words after `node`) on node's closed list, by its name,
    never its value; `None` where none is: the reporters, the file loaders, code the command
    spells (`-e`, `-p`, and a preload given a URL of a scheme but `file:`, `inline_preload`).
    Every word before a `--` is read, a file's name among them: under `--test` node reads an
    option written after the files too."""
    options = _options(words)
    for index, word in enumerate(options):
        name = _node_name(word)
        if name.startswith(_NODE_REPORTERS) or name in _NODE_REFUSED or name in _NODE_INLINE_CODE:
            return name
        if name in _NODE_PRELOADS or name == _NODE_PRELOAD_LETTER:
            _, equals, value = word.partition("=")
            given = value if equals else _next(options, index)
            if given is not None and inline_preload(given):
                return name
    return None


def node_never_ends(words: Sequence[str]) -> str | None:
    """node's watch mode among `words` (the words after `node`), by its name, read as
    `node_refused` reads: `--watch-path` wherever it is (measured on 26.12.0: under `--test` node
    refuses to run with it), else `--watch` where the last of `--watch` and `--no-watch` is it;
    `None` where neither is."""
    names = [_node_name(word) for word in _options(words)]
    if _NODE_WATCH_PATH in names:
        return _NODE_WATCH_PATH
    settings = [name for name in names if name in (_NODE_WATCH, _NODE_NO_WATCH)]
    return _NODE_WATCH if settings[-1:] == [_NODE_WATCH] else None


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
        never = node_never_ends(command[1:])
        if never is not None:
            return Unresolved(NEVER_ENDS, NEVER_ENDS_DETAIL.format(option=never))
        node = found(command[0], cwd, environ)
        if node is None:
            return Unresolved(ENTRY_NOT_FOUND, _NO_NODE)
        report = scratch / NODE_REPORT
        ours = (
            "--test-reporter=junit",
            f"--test-reporter-destination={report}",
            "--test-reporter=spec",
            "--test-reporter-destination=stdout",
        )
        argv = _launched(launch, (str(node), *ours, *command[1:]), cwd, environ)
        if isinstance(argv, Unresolved):
            return argv
        return Plan(
            argv=argv,
            kind=ReportKind.JUNIT,
            source=ReportSource.FILE,
            report=report,
            discovery=NODE_DISCOVERY,
            configs=(*CONFIGS, *node_preloaded(command[1:], cwd)),
            drop=whole_file,
        )


ADAPTERS = (JestAdapter(), VitestAdapter(), NodeTestAdapter())
