"""Go's runner adapter: a `go test` run, proved from the test event stream `go test -json` prints.

**What is recognised.** `go test …`, the `go` the command names found on `PATH`. The run is
`<go> test -json <args>`: `-json` after a leading `-C dir`, which the `go` command reads only
first, and a `-json` of the command's own kept once. The report is the run's standard output,
which `prove` copies to the caller whole and counts only the events of: a line a test prints is
an `output` event, never a result.

**The environment.** Every variable of `FORGING` the run inherits is removed from its
environment, and the receipt names it; the go command then reads its own defaults for them.

**Every control here, with its adversary and its anchor.** The adversary is the agent typing the
command; the anchor of each refusal is the command's own words.

- `REFUSED_OPTION`, naming the flag: `-exec` and `-toolexec` (which run the test binary, or every
  tool that builds it, under a program of the command's choosing), `-overlay` (which replaces
  source files with others the command names), `-c` (which builds the test binary and does not
  run it; `-c=false` is free), `-o` (which writes the test binary where the command says; measured
  on Go 1.27.2 it still runs the tests), and a `-json=` of a false value (which turns the report
  off). Each is read as the go command reads it: spaced or with `=`, with one dash or two, before
  the packages or after them, a boolean's `=` value as `strconv.ParseBool` reads it, a word that is
  a flag's value never as a flag (a build flag spelled `-test.`, which the go command does not
  know, taking none), and nothing past a bare `-args`, `--args` or `--`, which is the test
  binary's. The list is closed, drawn by running every flag `go test` and `go build` register over
  a failing test with `-json` added, and every other flag is free.
- `FORGING`, assigned in the command (refused) or inherited (removed): `GOFLAGS`, `GOENV` and
  `GOTOOLCHAIN`, through which the user's go env file (`go env -w`) and an inherited `GOFLAGS`
  reach the run (measured on Go 1.27.2, a `GOFLAGS=-toolexec=<script>` in the file `GOENV` names
  runs the script); `GOROOT`, which names the standard library and the tools the run builds with,
  `testing` among them; and `GOOS` and `GOARCH`, under which a target the host cannot run has the
  go command run the test binary under the `go_$GOOS_$GOARCH_exec` it finds on `PATH` (measured:
  `GOOS=js GOARCH=wasm` and a `go_js_wasm_exec` that prints a pass exit 0, the failing test never
  run).
- `CC`, `CXX`, the `CGO_*` variables, `-ldflags` and `-gcflags` (`-extld` among their values) and
  `-compiler` are free: they shape how the code under test is built, and a built test binary can
  already print test2json's framing, which is the bound's Go case below.
- The `go` is the one on the run's `PATH` (`stayfixed.profiles.programs.found`), and the receipt
  carries its realpath. Behind a launcher the core read past (`uv run …`), its words are kept in
  front and the program is the launcher's realpath; the `go` it is handed is the one found, by
  its path.

What a file in the tree can do -- a test that prints test2json's own framing (`\\x16--- PASS:`),
which test2json reads as a result, a `TestMain` that exits 0 before any test, a `go.mod` that
replaces a dependency -- is the bound's: the receipt names `go.mod` and `go.work` and the
untracked test files, and the file `-modfile` names by its realpath.
"""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from pathlib import Path

from stayfixed.profiles.programs import found, launched
from stayfixed.profiles.runners import (
    ENTRY_NOT_FOUND,
    REFUSED_OPTION,
    Plan,
    Refused,
    ReportKind,
    ReportSource,
    Unresolved,
)

NAME = "go-test"
# The reasons this adapter names, both `stayfixed.profiles.runners`': a flag the closed list
# refuses, and no `go` to run.
REASONS = (REFUSED_OPTION, ENTRY_NOT_FOUND)
FORGING = frozenset({"GOENV", "GOFLAGS", "GOTOOLCHAIN", "GOROOT", "GOOS", "GOARCH"})
DISCOVERY = ("*_test.go",)
CONFIGS = ("go.mod", "go.work")
REPORT_NAME = "events.jsonl"

_GO = "go"
_TEST = "test"
_JSON = "json"
# The words that end the go command's own flags: `-args`, `--args` and the terminator `--`,
# bare; every word after one is the test binary's. Measured on Go 1.27.2: `-args=x`,
# `-args=false` and `-test.args` end nothing, and a refused flag after one runs; past `--` none
# does.
_ENDS = frozenset({"-args", "--args", "--"})
_CHANGE_DIRECTORY = "C"
_MODFILE = "modfile"
_NO_GO = "no go on PATH"
_NO_LAUNCHER = "no {launcher} on PATH"
# The closed list, each a flag as the receipt names it: the four that take a value, refused
# whatever it is, and `-c`, refused unless it is turned off.
_REFUSED = frozenset({"-exec", "-toolexec", "-overlay", "-o"})
_BUILD_ONLY = "c"
# What the go command's flags read a boolean's `=` value as (`strconv.ParseBool`).
_TRUE = frozenset({"1", "t", "T", "TRUE", "true", "True"})
_FALSE = frozenset({"0", "f", "F", "FALSE", "false", "False"})
# The prefix the go command reads a flag of the test binary's by as well (`-test.run`). It
# registers no such spelling for a build flag: to it `-test.exec`, `-test.c` or `-test.p` is a flag
# it does not know, handed to the test binary, which takes no value, so the next word is read as a
# flag of the go command's (measured on Go 1.27.2: `./pkg -test.p -exec=X` runs X).
_TEST_PREFIX = "test."
# The go command's own flags that take their value as the next word where `=` does not give it,
# as Go 1.27.2 registers them for `go test` (`go help build`, `go help testflag`, and the hidden
# `-debug-*`), so that the word after one is never read as a flag of its own: the build flags, by
# their bare name only, and the test binary's, by their bare name and their `test.` name.
_BUILD_VALUED = frozenset(
    {
        "-C",
        "-p",
        "-covermode",
        "-coverpkg",
        "-asmflags",
        "-buildmode",
        "-compiler",
        "-gccgoflags",
        "-gcflags",
        "-installsuffix",
        "-ldflags",
        "-mod",
        "-modfile",
        "-overlay",
        "-pgo",
        "-pkgdir",
        "-tags",
        "-toolexec",
        "-exec",
        "-o",
        "-vet",
        "-debug-actiongraph",
        "-debug-runtime-trace",
        "-debug-trace",
    }
)
_TEST_VALUED = frozenset(
    {
        "-bench",
        "-benchtime",
        "-count",
        "-cpu",
        "-fuzz",
        "-fuzztime",
        "-fuzzminimizetime",
        "-list",
        "-outputdir",
        "-parallel",
        "-run",
        "-skip",
        "-timeout",
        "-shuffle",
        "-blockprofile",
        "-blockprofilerate",
        "-coverprofile",
        "-cpuprofile",
        "-memprofile",
        "-memprofilerate",
        "-mutexprofile",
        "-mutexprofilefraction",
        "-trace",
    }
)


def _takes_value(name: str) -> bool:
    """Whether the go command reads the flag `name` (past its dashes) as taking a value."""
    return f"-{name}" in _BUILD_VALUED or f"-{name.removeprefix(_TEST_PREFIX)}" in _TEST_VALUED


def _flag(word: str) -> tuple[str, str | None] | None:
    """A flag word's name, past one or two dashes, and its value where `=` gives one; `None` for
    a word that is no flag."""
    if not word.startswith("-") or word in ("-", "--"):
        return None
    name, equals, value = word.lstrip("-").partition("=")
    return name, value if equals else None


def _flags(args: Sequence[str]) -> list[tuple[int, str, str | None]]:
    """`go test`'s own flags in `args`: each one's index, name and value (`=`'s, or the next
    word's for a flag that takes one), up to a bare `-args`, `--args` or `--`."""
    found: list[tuple[int, str, str | None]] = []
    skip = False
    for index, word in enumerate(args):
        if skip:
            skip = False
            continue
        if word in _ENDS:
            break
        read = _flag(word)
        if read is None:
            continue
        name, value = read
        if value is None and _takes_value(name):
            value = args[index + 1] if index + 1 < len(args) else None
            skip = True
        found.append((index, name, value))
    return found


def refused_option(args: Sequence[str]) -> str | None:
    """The first of `go test`'s flags in `args` on the closed list, as the receipt names it;
    `None` where none is."""
    for _, name, value in _flags(args):
        if f"-{name}" in _REFUSED:
            return f"-{name}"
        if name == _BUILD_ONLY and value not in _FALSE:
            return f"-{name}"
        if name == _JSON and value is not None and value not in _TRUE:
            return f"-{name}"
    return None


def _leading_directory(flags: Sequence[tuple[int, str, str | None]]) -> str | None:
    """The directory a leading `-C` names, which the go command changes to before anything else
    and reads only as the first word."""
    if flags and flags[0][0] == 0 and flags[0][1] == _CHANGE_DIRECTORY:
        return flags[0][2]
    return None


def _planned_args(args: Sequence[str]) -> tuple[str, ...]:
    """`args` with the report's `-json` added, after a leading `-C dir`, and the command's own
    `-json` dropped."""
    flags = _flags(args)
    own = {index for index, name, value in flags if name == _JSON and value in (None, *_TRUE)}
    lead = 0
    if flags and flags[0][0] == 0 and flags[0][1] == _CHANGE_DIRECTORY:
        lead = 1 if "=" in args[0] else 2
    rest = [word for index, word in enumerate(args) if index >= lead and index not in own]
    return (*args[:lead], "-json", *rest)


def _modfiles(args: Sequence[str], cwd: Path) -> tuple[str, ...]:
    """The realpath of the file each `-modfile` names, read from the directory a leading `-C`
    names, else from `cwd` (measured on Go 1.27.2: `-C sub -modfile=alt.mod` reads
    `sub/alt.mod`): an absolute entry of `Plan.configs`, which names that one file."""
    flags = _flags(args)
    base = cwd / (_leading_directory(flags) or "")
    return tuple(
        os.path.realpath(base / value) for _, name, value in flags if name == _MODFILE and value
    )


class GoTestAdapter:
    """`RunnerAdapter` for `go test`."""

    @property
    def name(self) -> str:
        return NAME

    @property
    def forging(self) -> frozenset[str]:
        return FORGING

    def recognises(self, command: Sequence[str]) -> bool:
        return list(command[:2]) == [_GO, _TEST]

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
        args = command[2:]
        refused = refused_option(args)
        if refused is not None:
            return Refused(REFUSED_OPTION, refused)
        go = found(_GO, cwd, environ)
        if go is None:
            return Unresolved(ENTRY_NOT_FOUND, _NO_GO)
        argv = launched(launch, (str(go), _TEST, *_planned_args(args)), cwd, environ)
        if argv is None:
            named = Path(launch[0]).name
            return Unresolved(ENTRY_NOT_FOUND, _NO_LAUNCHER.format(launcher=named))
        return Plan(
            argv=argv,
            kind=ReportKind.EVENTS,
            source=ReportSource.STDOUT,
            report=scratch / REPORT_NAME,
            discovery=DISCOVERY,
            configs=(*CONFIGS, *_modfiles(args, cwd)),
        )


ADAPTERS = (GoTestAdapter(),)
