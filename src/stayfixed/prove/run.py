"""`stayfixed prove`: run a test command where it is typed, count only its runner's report, and
say what that proves.

What `prove` does, in order. The project it answers for is the git top-level of the directory the
command is typed in, or that directory itself outside a repository; the command runs in the
directory, never in the top-level. `guards.api.read_launch` reads the command past its
assignments, `env` and `uv run …` (the launch), and the first runner adapter that recognises what
is left plans the run. Every `NAME=value` the launch holds, wherever it stands, is an assignment
of the command: one of a variable in the adapter's `forging` set, or in the launcher's own
file-loading set where the launch runs a launcher, is `refused`, and so is a launcher option that
loads a file, both before anything is planned; every other assignment goes into the run's
environment. The adapter is handed the launcher's words alone, never an assignment or an `env`.
The plan names the argv to execute, the realpath of its
program, where the report arrives and in which format, what the run's environment gains and loses,
and the globs of the files that shape the report. The tree's state is taken, the program is checked
to be the file the adapter resolved, and the command runs in a session of its own; then the report
is counted, the tree's state is taken again, and `CASCADE` says what the run proved. The plan's
scratch directory, made outside the project and readable by its owner alone, is removed on every
path.

The bound, `BOUND`, which `docs/cli.md` states word for word: what a file in the tree, and the
environment, can do to the report is conceded, never checked. So the tree's state is information
for a reader of the receipt and never an input to the verdict: everything it reads, the agent that
typed the command can write.

**Every control here, with its adversary and its anchor.**

- `ASSIGNED_FORGING`: an agent steering the report with a variable it assigns in the command
  itself, before a launcher or after it, bare or after `env`. The anchor is the command's own
  words, which stayfixed reads before anything runs; the control is a closed list the adapter
  names, and the launcher's variables that load a file (`guards.api.LAUNCHER_FILE_VARIABLES`)
  where the launch runs a launcher, and refuses nothing outside them. A variable the run inherits
  is the adapter's to scrub or set, and an inherited launcher variable that loads a file is
  scrubbed, which changes the run and refuses nothing.
- `REFUSED_LAUNCHER_OPTION`: the same agent having the launcher load an environment or a
  configuration file it names (`guards.api.LAUNCHER_FILE_OPTIONS`), past every channel stayfixed
  controls, or run the command in another directory or project
  (`guards.api.LAUNCHER_DIRECTORY_OPTIONS`), so that the tree whose state the receipt and the
  record carry is not the tree that ran: the way on is to run `prove` from that directory. The
  anchor is again the command's own words; the option's spelling is refused wherever it stands
  among the launcher's words, which the launcher itself never reads as a value, so it refuses no
  command the launcher would run. `--with`, `--python` and `--isolated` stay free: they shape the
  environment the runner reads, which the bound concedes.
- `RESOLVED_ELSEWHERE`: a program swapped between the plan and the launch, the anchor being the
  filesystem, which the agent can write. A run whose program did not move passes, so it refuses no
  legitimate user; it is a convenience that names the swap, not a guarantee against one.
- The report is read where the adapter put it, in the scratch directory, and where it is the
  runner's standard output, off the pipe: a file the repository committed, or text a test printed
  outside the format's own framing, is never counted. The anchor, the scratch directory and the
  pipe, is stayfixed's own; a test that writes the format's framing itself is the bound's.
- The process group: a child the command left in the background goes on writing into the tree
  after the verdict. The group is stayfixed's own anchor and is ended however the run finishes
  (`stayfixed.processes`); a descendant that leaves it is not reached, and the tee lets go of the
  pipe such a descendant holds once it has copied what is there.
- The runner's standard input: the agent, or anything upstream of `prove`, feeding it what drives
  the runner, such as the commands of pytest's debugger. The anchor is the launch stayfixed makes,
  which no one else writes: the run's standard input is `/dev/null`. It refuses no one; a test that
  reads standard input sees its end.
- `PROVE_TIMEOUT_SECONDS`: a suite that hangs. A named cap with its flag, `not proven` past it.
- `--junit PATH` (`prove(junit=…)`), for a runner no adapter knows: the command runs as typed, no
  adapter is asked to plan it, and the report is the file at `PATH`, read from the directory the
  command runs in. `JUNIT_BESIDE_ADAPTER`: an agent routing a runner an adapter knows around that
  adapter's refusals and forging set; the anchor is the command's own words, and the refusal costs
  that runner nothing, since `prove` without `--junit` counts it. `JUNIT_UNCHANGED`: a stale or
  committed report the run never wrote, or a link to one; the anchor is the file's state as the
  run found it before it started (absent, or its inode, size and modification time), which the
  agent can write too, so it is a convenience and never a guarantee. The receipt marks the runner
  not verified, and the verdict is the cascade's as for any other run.
"""

from __future__ import annotations

import codecs
import contextlib
import hashlib
import os
import re
import selectors
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import threading
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import IO, BinaryIO, TextIO

from stayfixed import fsops, processes
from stayfixed.gitenv import checkout_root
from stayfixed.guards.api import (
    LAUNCHER_DIRECTORY_OPTIONS,
    LAUNCHER_DIRECTORY_VARIABLES,
    LAUNCHER_FILE_OPTIONS,
    LAUNCHER_FILE_VARIABLES,
    Launch,
    read_launch,
)
from stayfixed.printed import clipped, printable
from stayfixed.profiles.adapters import shipped_adapters
from stayfixed.profiles.runners import (
    Plan,
    Refused,
    ReportKind,
    ReportSource,
    RunnerAdapter,
    Unresolved,
)
from stayfixed.prove import tree
from stayfixed.prove.counts import (
    MAX_REPORT_BYTES,
    REPORT_DOCTYPE,
    REPORT_ENTITY,
    REPORT_MALFORMED,
    REPORT_NOT_UTF8,
    REPORT_TOO_LARGE,
    Counts,
    ReportError,
)
from stayfixed.prove.reports import read_report


class Verdict(StrEnum):
    """What a run proved, each a word the receipt and `--json` carry as it is."""

    PROVED = "proved"
    FAILED = "failed"
    NOT_PROVEN = "not proven"
    REFUSED = "refused"


# What `proved` means, in the one sentence `docs/cli.md` quotes word for word.
BOUND = (
    "The code under test, any file in the runner's load path, tracked or not, and the environment "
    "the runner reads can shape its report, so `proved` means the runner reported green on this "
    "tree, for the tests this command selected."
)

# The exit code of each verdict: a refusal is the 2 every refusal exits with, so a caller never
# reads it as a run that failed.
EXIT: Mapping[Verdict, int] = {
    Verdict.PROVED: 0,
    Verdict.FAILED: 1,
    Verdict.NOT_PROVEN: 1,
    Verdict.REFUSED: 2,
}

# A named cap: how long a run may take before its process group is ended and it is `not proven`.
# An hour bounds a suite that hangs and is no suite's budget; `--timeout` raises or lowers it. No
# shipped file states it.
PROVE_TIMEOUT_SECONDS = 3600

# The reasons, each one arm of `CASCADE` or the step that stopped the run before it. An adapter's
# own refusals and unresolved plans are its module's constants, and the reports' are
# `stayfixed.prove.counts`'.
NOT_RECOGNISED = "not-recognised"
ASSIGNED_FORGING = "assigned-forging"
REFUSED_LAUNCHER_OPTION = "launcher-option"
RESOLVED_ELSEWHERE = "resolved-elsewhere"
NOT_STARTED = "not-started"
TIMED_OUT = "timed-out"
INTERRUPTED = "interrupted"
NO_REPORT = "no-report"
FAILING = "failing"
NONE_RAN = "none-ran"
ALL_SKIPPED = "all-skipped"
GREEN_BUT_EXITED = "green-but-exited"
JUNIT_BESIDE_ADAPTER = "junit-beside-adapter"
JUNIT_UNCHANGED = "junit-unchanged"

# What the receipt's line says for each reason, every arm in words of its own.
WORDS: Mapping[str, str] = {
    "": "the runner reported every test it ran as passed",
    NOT_RECOGNISED: "no runner adapter recognises this command, so nothing can count its report",
    ASSIGNED_FORGING: "the command assigns a variable its runner reads to shape the report",
    REFUSED_LAUNCHER_OPTION: (
        "the command's launcher loads an environment or configuration file, or runs elsewhere"
    ),
    RESOLVED_ELSEWHERE: "the program changed between the plan and the launch",
    NOT_STARTED: "the command could not be started",
    TIMED_OUT: "the run passed its time limit and was ended",
    INTERRUPTED: "the run was interrupted and ended",
    NO_REPORT: "the runner wrote no report",
    FAILING: "the runner reported a failed test",
    NONE_RAN: "the runner reported no test run",
    ALL_SKIPPED: "the runner reported every test skipped",
    GREEN_BUT_EXITED: "the runner reported green and the command exited non-zero",
    JUNIT_BESIDE_ADAPTER: "a runner adapter knows this command, so `--junit` does not count it",
    JUNIT_UNCHANGED: "the run did not write the `--junit` report as a file of its own",
    REPORT_TOO_LARGE: "the report is past the size `prove` reads",
    REPORT_NOT_UTF8: "the report is not UTF-8",
    REPORT_MALFORMED: "the report does not parse as its format",
    REPORT_DOCTYPE: "the report declares a doctype",
    REPORT_ENTITY: "the report names an entity it never declared",
}
# The words for a reason an adapter names, by the verdict it stopped the run with.
_ADAPTER_WORDS: Mapping[Verdict, str] = {
    Verdict.REFUSED: "the runner's adapter refuses this command",
    Verdict.NOT_PROVEN: "the runner's adapter cannot plan this run",
}

# A shell assignment, `NAME=value`, as the shell reads one before a command and `env` after it.
_ASSIGNMENT = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)=(.*)", re.DOTALL)
# An option given its value in the same word, `--name=value`.
_OPTION_VALUE = re.compile(r"(--[^=]+=).*", re.DOTALL)
REDACTED = "…"


@dataclass(frozen=True)
class Receipt:
    """What one run of `prove` came to, and what a reader needs to weigh it.

    `argv` is the command as given with every `NAME=value` and `--option=value` value replaced by
    `REDACTED`; a value passed as the word after its option is kept, since nothing tells it from an
    operand. `detail` is where the step that stopped the run stopped: the variable assigned, the
    launcher option refused, the option or word the runner's adapter refused, what the adapter
    looked for or was asked for where it could not plan the run, the `--junit` path the run did not
    write (`JUNIT_UNCHANGED`), or where a report stopped reading. `program` is the realpath of what
    ran, and `entry` the realpath of the file it ran as the runner where the program is an
    interpreter running one (`node` and jest's or vitest's entry); `verified` is false on every
    `--junit` receipt, a plan made or not, and true on every other. `scrubbed` names, sorted, each
    variable the caller's environment held that the run did not get as it was: removed (the
    adapter's `scrub`, a launcher's file variable) or given the adapter's own value (`set_env`),
    since such a removal can turn a legitimate run red. `commit` and `dirty_before` are
    the tree's state before the run, `dirty_after` after it, and `untracked` (at most
    `tree.UNTRACKED_LISTED`, `untracked_more` past it) and `configs` (at most as many,
    `configs_more` past it, and `ignored_configs` the count of those git ignores) after it, or
    before it where git could not answer after: none of them is an input to the verdict.
    """

    verdict: Verdict
    reason: str
    detail: str
    argv: tuple[str, ...]
    runner: str | None = None
    program: str | None = None
    entry: str | None = None
    verified: bool = True
    scrubbed: tuple[str, ...] = ()
    counts: Counts | None = None
    exit_code: int | None = None
    report_digest: str | None = None
    commit: str | None = None
    dirty_before: bool | None = None
    dirty_after: bool | None = None
    untracked: tuple[str, ...] = ()
    untracked_more: int = 0
    configs: tuple[str, ...] = ()
    configs_more: int = 0
    ignored_configs: int = 0


_NO_COUNTS = Counts(0, 0, 0)


@dataclass(frozen=True)
class _Outcome:
    """What the run came to before the cascade reads it: the reason of a step that refused or
    could not go on, or the counts and the exit code."""

    refused: str | None = None
    unproven: str | None = None
    counts: Counts | None = None
    exit_code: int | None = None

    @property
    def counted(self) -> Counts:
        """The counts, or none of each where there are none: only the rows past the first two
        read them, and an outcome without counts holds one of those two."""
        return self.counts if self.counts is not None else _NO_COUNTS


# The verdict cascade, one ordered table and the first row that holds wins; `docs/cli.md` states
# it row for row. A row is the verdict, its reason (`None` for the reason the step that stopped the
# run named), and what must hold. A run that ran no test, or skipped every one, has proved
# nothing whatever its exit code, so those rows stand before the exit code's.
CASCADE: tuple[tuple[Verdict, str | None, Callable[[_Outcome], bool]], ...] = (
    (Verdict.REFUSED, None, lambda outcome: outcome.refused is not None),
    (Verdict.NOT_PROVEN, None, lambda outcome: outcome.unproven is not None),
    (Verdict.FAILED, FAILING, lambda outcome: outcome.counted.failed > 0),
    (Verdict.FAILED, NONE_RAN, lambda outcome: outcome.counted.total == 0),
    (Verdict.FAILED, ALL_SKIPPED, lambda outcome: outcome.counted.skipped == outcome.counted.total),
    (Verdict.NOT_PROVEN, GREEN_BUT_EXITED, lambda outcome: outcome.exit_code != 0),
    (Verdict.PROVED, "", lambda outcome: True),
)


def judged(outcome: _Outcome) -> tuple[Verdict, str]:
    """The first row of `CASCADE` that holds for `outcome`: its verdict and its reason."""
    verdict, reason = next(
        (verdict, reason) for verdict, reason, holds in CASCADE if holds(outcome)
    )
    return verdict, reason if reason is not None else outcome.refused or outcome.unproven or ""


def redacted(argv: Sequence[str]) -> tuple[str, ...]:
    """`argv` with the value of every `NAME=value` and `--option=value` word replaced."""
    shown: list[str] = []
    for word in argv:
        if assignment := _ASSIGNMENT.fullmatch(word):
            shown.append(f"{assignment.group(1)}={REDACTED}")
        elif option := _OPTION_VALUE.fullmatch(word):
            shown.append(f"{option.group(1)}{REDACTED}")
        else:
            shown.append(word)
    return tuple(shown)


def assignments(words: Sequence[str]) -> dict[str, str]:
    """The variables `words`, a launch's assignments (`guards.api.Launch.assignments`, each a
    `NAME=value`), assign, in order, the last of two for one name winning."""
    assigned: dict[str, str] = {}
    for word in words:
        name, _, value = word.partition("=")
        assigned[name] = value
    return assigned


# The launcher's options refused for every adapter: those that load a file of the command's
# choosing, and those that run it in another directory or project than the one `prove` judges;
# and their variables, refused assigned and removed inherited.
_LAUNCHER_REFUSED = LAUNCHER_FILE_OPTIONS | LAUNCHER_DIRECTORY_OPTIONS
_LAUNCHER_VARIABLES = LAUNCHER_FILE_VARIABLES | LAUNCHER_DIRECTORY_VARIABLES


def file_option(launcher: Sequence[str]) -> str | None:
    """The first of the launcher's options that loads a file, or runs the command elsewhere,
    which `launcher`'s words spell, as `--name value` or `--name=value`, by its name; `None` where
    none does."""
    return next(
        (name for word in launcher if (name := word.partition("=")[0]) in _LAUNCHER_REFUSED),
        None,
    )


class _Signalled(Exception):
    """A terminating signal reached `prove` while its command ran."""


@contextlib.contextmanager
def _signals_end_the_run() -> Iterator[None]:
    """`SIGTERM` and `SIGHUP` raise `_Signalled` while the block runs, so a run ended from outside
    ends its command's process group as an interrupt does, instead of leaving it running. Only
    where Python lets a handler be set, the main thread; the handlers before are put back."""
    if threading.current_thread() is not threading.main_thread():
        yield
        return

    def raised(signum: int, frame: object) -> None:
        raise _Signalled(signum)

    kept = {number: signal.signal(number, raised) for number in (signal.SIGTERM, signal.SIGHUP)}
    try:
        yield
    finally:
        for number, handler in kept.items():
            signal.signal(number, handler)


class _Tee:
    """The runner's standard output, copied as it arrives to the caller's stream and, where it is
    the report, up to one byte past `MAX_REPORT_BYTES` to the report too, by a thread of its own
    that owns both descriptors.

    The thread reads until the pipe ends; once `finish` is asked, it stops at the first moment the
    pipe holds nothing, or once it has copied `MAX_REPORT_BYTES` more, so a descendant that left the
    process group and writes on cannot keep it. A caller's stream that takes text alone is handed
    whole characters, decoded across reads. A caller that has gone (`| head`, a closed stream) is
    written nothing more, and the report goes on filling.
    """

    def __init__(self, source: IO[bytes], report: int | None, caller: TextIO) -> None:
        self._source = source
        self._report = report
        self._room = MAX_REPORT_BYTES + 1 if report is not None else 0
        self._stop = threading.Event()
        self._out: BinaryIO | None = getattr(caller, "buffer", None)
        self._text = caller
        self._decoder = codecs.getincrementaldecoder("utf-8")("replace")
        self._gone = False
        self._thread = threading.Thread(target=self._pump, daemon=True)
        self._thread.start()

    def _echo(self, chunk: bytes, *, final: bool = False) -> None:
        if self._gone:
            return
        try:
            if self._out is not None:
                self._out.write(chunk)
                self._out.flush()
            else:
                self._text.write(self._decoder.decode(chunk, final))
        except (OSError, ValueError):
            # The reader of the caller's stream went away, or the stream was closed: the run is
            # not the caller's to end, and its report is not cut short.
            self._gone = True

    def _copy(self, chunk: bytes) -> None:
        self._echo(chunk)
        share = chunk[: self._room]
        self._room -= len(share)
        while share and self._report is not None:
            share = share[os.write(self._report, share) :]

    def _pump(self) -> None:
        after_stop = 0
        try:
            with selectors.DefaultSelector() as selector:
                selector.register(self._source, selectors.EVENT_READ)
                while True:
                    stopping = self._stop.is_set()
                    if not selector.select(timeout=0 if stopping else 0.1):
                        if stopping:
                            return
                        continue
                    chunk = os.read(self._source.fileno(), 64 * 1024)
                    if not chunk:
                        return
                    self._copy(chunk)
                    if stopping:
                        after_stop += len(chunk)
                        if after_stop > MAX_REPORT_BYTES:
                            return
        finally:
            if self._out is None:
                self._echo(b"", final=True)
            self._source.close()
            if self._report is not None:
                os.close(self._report)

    def finish(self) -> None:
        """Stop once the pipe is drained, and wait for the thread to end."""
        self._stop.set()
        self._thread.join()


def _open_report(path: Path) -> int:
    """A descriptor for the teed report, a file this run creates: refused if anything is there."""
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC
    return os.open(path, flags, 0o600)


def _launch(plan: Plan, cwd: Path, env: Mapping[str, str], piped: bool) -> subprocess.Popen[bytes]:
    # S603: the adapter's plan of the command the caller typed, list form, never a shell. A
    # session of its own puts what it starts in one process group, which is ended however it
    # finishes. Standard input is `/dev/null`, never the caller's: what feeds `prove`'s could
    # drive the runner (a debugger takes its commands there), and a test that reads it sees its
    # end. Standard error is the caller's; standard output is too, or a pipe the tee copies whole
    # to the caller's stream, when it is the report or the caller named a stream of its own.
    return subprocess.Popen(  # noqa: S603
        list(plan.argv),
        cwd=cwd,
        env=dict(env),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE if piped else None,
        start_new_session=True,
    )


@dataclass(frozen=True)
class _Ran:
    stopped: str | None
    exit_code: int | None


def _run(
    plan: Plan, cwd: Path, env: Mapping[str, str], timeout: float, echo: TextIO | None
) -> _Ran:
    """Run `plan` in `cwd` under `env`, its process group ended however it finishes. The runner's
    standard output is the caller's, and a pipe teed to it when it is the report; given `echo`, it
    is always a pipe, teed to `echo`, whatever the report's source."""
    teed = plan.source is ReportSource.STDOUT
    piped = teed or echo is not None
    caller = echo if echo is not None else sys.stdout
    report = _open_report(plan.report) if teed else None
    sys.stdout.flush()
    with contextlib.suppress(OSError, ValueError):
        caller.flush()
    try:
        process = _launch(plan, cwd, env, piped)
    except OSError:
        if report is not None:
            os.close(report)
        return _Ran(NOT_STARTED, None)
    tee = None if process.stdout is None else _Tee(process.stdout, report, caller)
    try:
        try:
            with _signals_end_the_run():
                processes.exited(process, timeout)
                # The command has exited; what it left in its group goes now, while its pid is
                # unreaped. An interrupt here, as in the wait, ends the group the same way.
                processes.kill_group(process)
                code = process.wait()
        except subprocess.TimeoutExpired:
            processes.end(process)
            return _Ran(TIMED_OUT, None)
        except (KeyboardInterrupt, _Signalled):
            # A terminal's Ctrl-C reaches stayfixed's process group and not the command's session,
            # so nothing but `prove` ends the command's group on the way out. One that landed after
            # the wait reaped the command leaves no group to end: its pid may be another's by now.
            if process.returncode is None:
                processes.end(process)
            return _Ran(INTERRUPTED, None)
        except BaseException:
            processes.end(process)
            raise
        return _Ran(None, code)
    finally:
        if tee is not None:
            tee.finish()


def _state(path: Path) -> tuple[int, int, int, int] | None:
    """What is at `path`, not followed through a link: its mode, inode, size and modification
    time; `None` where nothing is."""
    try:
        found = os.lstat(path)
    except OSError:
        return None
    return found.st_mode, found.st_ino, found.st_size, found.st_mtime_ns


def _rewritten(before: tuple[int, int, int, int] | None, path: Path) -> bool:
    """Whether `path` is now a regular file, not a link, that is not the one `before` found:
    one the run created, or rewrote."""
    after = _state(path)
    return after is not None and stat.S_ISREG(after[0]) and after != before


def _unverified(launch: Launch, report: Path, cwd: Path, environ: Mapping[str, str]) -> Plan | None:
    """The plan of a command no adapter knows: its launcher's words and its command, run as typed,
    the program found from `cwd` as the run would find it, and the report the file at `report`;
    `None` where the program is not there."""
    words = (*launch.launcher, *launch.command)
    if os.sep in words[0]:
        found = shutil.which(str(cwd / words[0]))
    else:
        path = environ.get("PATH", os.defpath).split(os.pathsep)
        found = shutil.which(words[0], path=os.pathsep.join(str(cwd / entry) for entry in path))
    if found is None:
        return None
    return Plan(
        argv=(found, *words[1:]),
        program=Path(os.path.realpath(found)),
        kind=ReportKind.JUNIT,
        source=ReportSource.FILE,
        report=report,
        set_env={},
        scrub=frozenset(),
        discovery=(),
        configs=(),
    )


def _counted(plan: Plan) -> tuple[Counts | None, str | None, str, str | None]:
    """The report counted, or the reason it was not, its detail, and the digest of what was read."""
    try:
        data, _ = fsops.read_bounded(plan.report, MAX_REPORT_BYTES + 1)
    except OSError:
        return None, NO_REPORT, "", None
    digest = hashlib.sha256(data).hexdigest()
    try:
        return read_report(plan.kind, data, drop=plan.drop), None, "", digest
    except ReportError as exc:
        return None, exc.reason, exc.detail, digest


def prove(
    argv: Sequence[str],
    *,
    cwd: Path,
    environ: Mapping[str, str],
    timeout: float,
    adapters: Sequence[RunnerAdapter] | None = None,
    echo: TextIO | None = None,
    junit: Path | None = None,
) -> Receipt:
    """Run `argv` in `cwd` and say what its runner's report proves. `adapters` defaults to every
    adapter this stayfixed ships (`shipped_adapters`). Given `echo`, the runner's standard output,
    every byte, goes there whatever the report's source (`--json` hands standard error, so that
    standard output holds the one object); without it, the runner's standard output is the
    caller's.

    Given `junit`, a path read from `cwd`, the command is one no adapter knows: one an adapter
    recognises is refused (`JUNIT_BESIDE_ADAPTER`), and otherwise it runs as typed and its report is
    the JUnit file at that path, counted only where the run created or rewrote it as a regular file
    (`JUNIT_UNCHANGED`), its runner marked not verified.

    An adapter whose plan's program is not an absolute path is a defect in stayfixed, as a module
    that does not import is, and raises `ValueError`: a bare name would be found from stayfixed's
    own directory and `PATH`, never where the adapter looked. So is a plan whose report, a file the
    runner writes, lies outside the scratch directory the core handed it: a report anywhere else
    could be one the repository committed.
    """
    given = tuple(argv)
    shown = redacted(given)
    root = checkout_root(cwd) or cwd
    launch = read_launch(given)
    command = launch.command
    known = shipped_adapters() if adapters is None else adapters
    adapter = next((each for each in known if command and each.recognises(command)), None)
    # A `--junit` receipt says its runner is not verified on every path, a plan made or not.
    verified = junit is None
    if junit is not None and adapter is not None:
        return _receipt(
            _Outcome(refused=JUNIT_BESIDE_ADAPTER), shown, adapter.name, verified=verified
        )
    if adapter is None and (junit is None or not command):
        return _receipt(_Outcome(unproven=NOT_RECOGNISED), shown, verified=verified)
    runner = adapter.name if adapter is not None else None
    assigned = assignments(launch.assignments)
    # The launcher's own variables that load a file, where the launch runs one.
    loaders = _LAUNCHER_VARIABLES if launch.launcher else frozenset()
    forging = adapter.forging if adapter is not None else frozenset()
    forged = sorted(name for name in assigned if name in forging | loaders)
    if forged:
        return _receipt(
            _Outcome(refused=ASSIGNED_FORGING),
            shown,
            runner,
            detail=", ".join(forged),
            verified=verified,
        )
    loading = file_option(launch.launcher)
    if loading is not None:
        return _receipt(
            _Outcome(refused=REFUSED_LAUNCHER_OPTION),
            shown,
            runner,
            detail=loading,
            verified=verified,
        )
    # An inherited one goes from the run's environment as the plan's own scrub would go.
    kept = {name: value for name, value in environ.items() if name not in loaders}
    removed = frozenset(environ) & loaders
    # A Ctrl-C or a terminating signal anywhere from here on, the tree's state, the plan or the
    # reap as much as the wait, ends the run `not proven`, its scratch directory removed, and the
    # caller still records it: never an internal error.
    try:
        with _signals_end_the_run():
            return _planned_and_proved(
                adapter,
                launch,
                command,
                assigned,
                shown,
                cwd,
                root,
                environ,
                kept,
                removed,
                timeout,
                echo,
                junit=junit,
                verified=verified,
            )
    except (KeyboardInterrupt, _Signalled):
        return _receipt(_Outcome(unproven=INTERRUPTED), shown, runner, verified=verified)


def _planned_and_proved(
    adapter: RunnerAdapter | None,
    launch: Launch,
    command: Sequence[str],
    assigned: Mapping[str, str],
    shown: tuple[str, ...],
    cwd: Path,
    root: Path,
    environ: Mapping[str, str],
    kept: Mapping[str, str],
    removed: frozenset[str],
    timeout: float,
    echo: TextIO | None,
    *,
    junit: Path | None,
    verified: bool,
) -> Receipt:
    if adapter is None:
        unverified = _unverified(launch, cwd / junit, cwd, environ) if junit is not None else None
        if unverified is None:
            return _receipt(_Outcome(unproven=NOT_STARTED), shown, verified=verified)
        return _proved(
            None,
            unverified,
            assigned,
            shown,
            cwd,
            root,
            kept,
            timeout,
            echo,
            junit=junit,
            removed=removed,
            verified=verified,
        )
    scratch = Path(tempfile.mkdtemp(prefix="stayfixed-prove-"))
    try:
        planned = adapter.plan(
            launch.launcher, command, cwd=cwd, root=root, scratch=scratch, environ=environ
        )
        if isinstance(planned, Refused):
            return _receipt(
                _Outcome(refused=planned.reason), shown, adapter.name, detail=planned.detail
            )
        if isinstance(planned, Unresolved):
            return _receipt(
                _Outcome(unproven=planned.reason), shown, adapter.name, detail=planned.detail
            )
        if planned.source is ReportSource.FILE and scratch not in planned.report.parents:
            raise ValueError(
                f"the {adapter.name} adapter planned a report outside its scratch directory"
            )
        return _proved(
            adapter.name,
            planned,
            assigned,
            shown,
            cwd,
            root,
            kept,
            timeout,
            echo,
            removed=removed,
        )
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def _proved(
    runner: str | None,
    plan: Plan,
    assigned: Mapping[str, str],
    shown: tuple[str, ...],
    cwd: Path,
    root: Path,
    environ: Mapping[str, str],
    timeout: float,
    echo: TextIO | None,
    *,
    junit: Path | None = None,
    removed: frozenset[str] = frozenset(),
    verified: bool = True,
) -> Receipt:
    if not os.path.isabs(plan.argv[0]):
        raise ValueError(f"the {runner} adapter planned a program that is not absolute")
    before = tree.state(root, plan.discovery, plan.configs)
    if Path(os.path.realpath(plan.argv[0])) != plan.program:
        return _receipt(
            _Outcome(refused=RESOLVED_ELSEWHERE),
            shown,
            runner,
            plan,
            before=before,
            verified=verified,
        )
    env = {name: value for name, value in environ.items() if name not in plan.scrub}
    env |= assigned
    env |= plan.set_env
    overridden = {name for name, value in plan.set_env.items() if environ.get(name, value) != value}
    scrubbed = tuple(sorted(removed | (frozenset(environ) & plan.scrub) | overridden))
    found = _state(plan.report)
    ran = _run(plan, cwd, env, timeout, echo)
    after = tree.state(root, plan.discovery, plan.configs)
    if ran.stopped is not None:
        outcome, detail, digest = _Outcome(unproven=ran.stopped), "", None
    elif junit is not None and not _rewritten(found, plan.report):
        outcome = _Outcome(unproven=JUNIT_UNCHANGED, exit_code=ran.exit_code)
        detail, digest = str(junit), None
    else:
        counts, unread, detail, digest = _counted(plan)
        outcome = _Outcome(unproven=unread, counts=counts, exit_code=ran.exit_code)
    return _receipt(
        outcome,
        shown,
        runner,
        plan,
        detail=detail,
        before=before,
        after=after,
        digest=digest,
        scrubbed=scrubbed,
        verified=verified,
    )


def _receipt(
    outcome: _Outcome,
    shown: tuple[str, ...],
    runner: str | None = None,
    plan: Plan | None = None,
    *,
    detail: str = "",
    before: tree.TreeState | None = None,
    after: tree.TreeState | None = None,
    digest: str | None = None,
    verified: bool = True,
    scrubbed: tuple[str, ...] = (),
) -> Receipt:
    """The receipt of `outcome`; `verified` is false for a `--junit` run, and only for one."""
    verdict, reason = judged(outcome)
    files = after if after is not None and after.untracked is not None else before
    configs = after if after is not None and after.configs is not None else before
    return Receipt(
        verdict=verdict,
        reason=reason,
        detail=detail,
        argv=shown,
        runner=runner,
        program=str(plan.program) if plan is not None else None,
        entry=str(plan.entry) if plan is not None and plan.entry is not None else None,
        verified=verified,
        scrubbed=scrubbed,
        counts=outcome.counts,
        exit_code=outcome.exit_code,
        report_digest=digest,
        commit=before.commit if before is not None else None,
        dirty_before=before.dirty if before is not None else None,
        dirty_after=after.dirty if after is not None else None,
        untracked=(files.untracked or ()) if files is not None else (),
        untracked_more=files.more if files is not None else 0,
        configs=(configs.configs or ()) if configs is not None else (),
        configs_more=configs.configs_more if configs is not None else 0,
        ignored_configs=configs.ignored_configs if configs is not None else 0,
    )


def line(receipt: Receipt) -> str:
    """The receipt in one line: the verdict and its reason in words, the counts, the runner (the
    program, and the entry it runs where it is an interpreter), the inherited variables the run
    did not get as they were, and the files that can shape the report. A variable's name is one of
    an adapter's or a launcher's own sets, never one the environment chose. A name the tree chose
    prints only inside the path grammar (`printed.printable`); `--json` carries every one."""
    words = WORDS.get(receipt.reason) or _ADAPTER_WORDS.get(receipt.verdict, receipt.reason)
    head = f"{receipt.verdict}: {words}"
    if receipt.reason not in WORDS:
        head += f" ({receipt.reason})"
    if receipt.detail:
        head += f": {clipped(receipt.detail)}"
    parts = [head]
    if receipt.counts is not None:
        counts = receipt.counts
        parts.append(f"{counts.passed} passed, {counts.failed} failed, {counts.skipped} skipped")
    if receipt.exit_code not in (None, 0):
        parts.append(f"exit {receipt.exit_code}")
    if receipt.runner is not None:
        runner = f"runner {receipt.runner}"
        if receipt.program is not None:
            runner += f" at {clipped(receipt.program)}"
        if receipt.entry is not None:
            runner += f" running {clipped(receipt.entry)}"
        if not receipt.verified:
            runner += ", not verified"
        parts.append(runner)
    elif not receipt.verified:
        ran = f", ran {clipped(receipt.program)}" if receipt.program is not None else ""
        parts.append(f"runner not verified{ran}")
    if receipt.scrubbed:
        parts.append(f"removed from the run's environment: {', '.join(receipt.scrubbed)}")
    if receipt.configs or receipt.ignored_configs:
        listed = ", ".join(printable(name) for name in receipt.configs)
        more = f" and {receipt.configs_more} more" if receipt.configs_more else ""
        named = f"{listed}{more}"
        if receipt.ignored_configs:
            ignored = f"{receipt.ignored_configs} ignored"
            named = f"{named} and {ignored}" if named else ignored
        parts.append(f"configuration: {named}")
    if receipt.untracked:
        listed = ", ".join(printable(name) for name in receipt.untracked)
        more = f" and {receipt.untracked_more} more" if receipt.untracked_more else ""
        parts.append(f"untracked in the discovery set: {listed}{more}")
    return "; ".join(parts)
