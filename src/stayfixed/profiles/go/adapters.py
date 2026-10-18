"""Go's runner adapter: a `go test` run, proved from the test event stream `go test -json` prints.

**What is recognised.** `go test …`, the `go` a bare name or a path to one (`/usr/local/go/bin/go
test`). Without a launcher that `go` is the program, found as the shell running the command finds
it (`stayfixed.profiles.programs.found`), and the receipt carries its realpath. Behind a launcher
the core read past (`uv run …`) the launcher is the program, and the command's words are handed to
it as typed: the `go` that runs is the one the launcher finds (`uv run` puts its environment's
`bin` first), never looked up on the caller's `PATH`.

**The run** is the command as typed with `-json` added: after a leading `-C dir`, which the go
command reads only as its first flag, and otherwise first. The report is the run's standard
output, which `prove` copies to the caller whole and counts only the events of: a line a test
prints is an `output` event, never a result. Nothing is refused, and the environment is the run's
as a shell builds it: `GOFLAGS`, `GOENV`, `GOTOOLCHAIN`, `GOROOT`, `GOOS`, `GOARCH` and every other
variable are the user's, read by the go command as outside `prove`. A flag that ends the run with
no event stream is the cascade's, never `proved`: measured on Go 1.27.2, `-c` builds the test
binary and prints nothing (`none-ran`), and a `-json=false` of the command's own, which comes after
ours, turns the stream into text (`report-malformed`).

**The configuration files** are `go.mod`, `go.work` and the file each `-modfile` names, read from
the directory a leading `-C` names; the discovery set is `*_test.go`. What a file in the tree can do
-- a test that prints test2json's own framing (`\\x16--- PASS:`), which test2json reads as a
result, a `TestMain` that exits 0 before any test, a `go.mod` that replaces a dependency -- is the
bound's, which the receipt's list of those files lets a reader weigh.
"""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from pathlib import Path

from stayfixed.profiles.programs import launched
from stayfixed.profiles.runners import (
    ENTRY_NOT_FOUND,
    Plan,
    Refused,
    ReportKind,
    ReportSource,
    Unresolved,
)

NAME = "go-test"
# The one reason this adapter names, `stayfixed.profiles.runners`': no `go` to run.
REASONS = (ENTRY_NOT_FOUND,)
DISCOVERY = ("*_test.go",)
CONFIGS = ("go.mod", "go.work")
REPORT_NAME = "events.jsonl"

_GO = "go"
_TEST = "test"
_JSON = "-json"
# The words that end the go command's own flags: `-args`, `--args` and the terminator `--`,
# bare; every word after one is the test binary's (measured on Go 1.27.2: `-args=x` ends
# nothing).
_ENDS = frozenset({"-args", "--args", "--"})
_CHANGE_DIRECTORY = "C"
_MODFILE = "modfile"
_NOT_ON_PATH = "no {program} on PATH"
_NO_FILE = "no executable file at {program}"


def _flag(word: str) -> tuple[str, str | None] | None:
    """A flag word's name, past one or two dashes, and its value where `=` gives one; `None` for
    a word that is no flag."""
    if not word.startswith("-") or word in ("-", "--"):
        return None
    name, equals, value = word.lstrip("-").partition("=")
    return name, value if equals else None


def _leading_directory(args: Sequence[str]) -> tuple[int, str | None]:
    """How many words a leading `-C dir` (or `-C=dir`) takes, and the directory it names, which
    the go command changes to before anything else and reads only as the first word; `(0, None)`
    where the first word is no `-C`."""
    read = _flag(args[0]) if args else None
    if read is None or read[0] != _CHANGE_DIRECTORY:
        return 0, None
    if read[1] is not None:
        return 1, read[1]
    return 2, args[1] if len(args) > 1 else None


def _planned_args(args: Sequence[str]) -> tuple[str, ...]:
    """`args` with the report's `-json` added after a leading `-C dir`, and otherwise first. A
    `-json` of the command's own stays: the go command reads a boolean flag given twice as once
    (measured on Go 1.27.2)."""
    lead, _ = _leading_directory(args)
    return (*args[:lead], _JSON, *args[lead:])


def _modfiles(args: Sequence[str], cwd: Path) -> tuple[str, ...]:
    """The realpath of the file each `-modfile` names (`-modfile=f`, or `-modfile f`), up to a
    bare `-args`, `--args` or `--`, read from the directory a leading `-C` names, else from `cwd`
    (measured on Go 1.27.2: `-C sub -modfile=alt.mod` reads `sub/alt.mod`): an absolute entry of
    `Plan.configs`, which names that one file. A word read as `-modfile` that is another flag's
    value names one file more on the receipt, which is information and never the verdict's."""
    _, directory = _leading_directory(args)
    base = cwd / (directory or "")
    named: list[str] = []
    for index, word in enumerate(args):
        if word in _ENDS:
            break
        read = _flag(word)
        if read is None or read[0] != _MODFILE:
            continue
        value = read[1] if read[1] is not None else (args[index + 1 : index + 2] or [""])[0]
        if value:
            named.append(os.path.realpath(base / value))
    return tuple(named)


def _not_found(word: str) -> str:
    """What a run's first word that names nothing was looked up as: a word holding a `/` is read
    as a path, never looked up on `PATH`."""
    template = _NO_FILE if os.sep in word else _NOT_ON_PATH
    return template.format(program=word)


class GoTestAdapter:
    """`RunnerAdapter` for `go test`."""

    @property
    def name(self) -> str:
        return NAME

    @property
    def forging(self) -> frozenset[str]:
        return frozenset()

    def recognises(self, command: Sequence[str]) -> bool:
        return len(command) >= 2 and Path(command[0]).name == _GO and command[1] == _TEST

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
        argv = launched(launch, (command[0], _TEST, *_planned_args(args)), cwd, environ)
        if argv is None:
            return Unresolved(ENTRY_NOT_FOUND, _not_found((launch or command)[0]))
        return Plan(
            argv=argv,
            kind=ReportKind.EVENTS,
            source=ReportSource.STDOUT,
            report=scratch / REPORT_NAME,
            discovery=DISCOVERY,
            configs=(*CONFIGS, *_modfiles(args, cwd)),
        )


ADAPTERS = (GoTestAdapter(),)
