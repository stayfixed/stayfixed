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

The bound, which `docs/cli.md` states word for word: "The code under test, any file in the
runner's load path, tracked or not, and the environment the runner reads can shape its report, so
`proved` means the runner reported green on this tree, for the tests this command selected." So
the tree's state is information for a reader of the receipt and never an input to the verdict:
everything it reads, the agent that typed the command can write.

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
  controls. The anchor is again the command's own words; the option's spelling is refused
  wherever it stands among the launcher's words, which the launcher itself never reads as a
  value, so it refuses no command the launcher would run.
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
- `PROVE_TIMEOUT_SECONDS`: a suite that hangs. A named cap with its flag, `not proven` past it.
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
from stayfixed.guards.api import LAUNCHER_FILE_OPTIONS, LAUNCHER_FILE_VARIABLES, read_launch
from stayfixed.printed import clipped, printable
from stayfixed.profiles.runners import Plan, Refused, ReportSource, RunnerAdapter, Unresolved
from stayfixed.prove import tree
from stayfixed.prove.adapters import shipped_adapters
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
# own refusals and unresolved entry points are its module's constants, and the reports' are
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

# What the receipt's line says for each reason, every arm in words of its own.
WORDS: Mapping[str, str] = {
    "": "the runner reported every test it ran as passed",
    NOT_RECOGNISED: "no runner adapter recognises this command, so nothing can count its report",
    ASSIGNED_FORGING: "the command assigns a variable its runner reads to shape the report",
    REFUSED_LAUNCHER_OPTION: "the command's launcher loads an environment or configuration file",
    RESOLVED_ELSEWHERE: "the program changed between the plan and the launch",
    NOT_STARTED: "the command could not be started",
    TIMED_OUT: "the run passed its time limit and was ended",
    INTERRUPTED: "the run was interrupted and ended",
    NO_REPORT: "the runner wrote no report",
    FAILING: "the runner reported a failed test",
    NONE_RAN: "the runner reported no test run",
    ALL_SKIPPED: "the runner reported every test skipped",
    GREEN_BUT_EXITED: "the runner reported green and the command exited non-zero",
    REPORT_TOO_LARGE: "the report is past the size `prove` reads",
    REPORT_NOT_UTF8: "the report is not UTF-8",
    REPORT_MALFORMED: "the report does not parse as its format",
    REPORT_DOCTYPE: "the report declares a doctype",
    REPORT_ENTITY: "the report names an entity it never declared",
}
# The words for a reason an adapter names, by the verdict it stopped the run with.
_ADAPTER_WORDS: Mapping[Verdict, str] = {
    Verdict.REFUSED: "the runner's adapter refuses this command",
    Verdict.NOT_PROVEN: "the runner's entry point did not resolve",
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
    operand. `detail` is where the step that stopped the run stopped: the variable assigned, or
    where a report stopped reading. `program` is the realpath of what ran; `verified` is false only
    where the plan said its runner is not one an adapter resolved. `commit` and `dirty_before` are
    the tree's state before the run, `dirty_after` after it, and `untracked` (at most
    `tree.UNTRACKED_LISTED`, `untracked_more` past it) and `configs` (at most as many,
    `configs_more` past it) after it, or before it where git could not answer after: none of them
    is an input to the verdict.
    """

    verdict: Verdict
    reason: str
    detail: str
    argv: tuple[str, ...]
    runner: str | None = None
    program: str | None = None
    verified: bool = True
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


def file_option(launcher: Sequence[str]) -> str | None:
    """The first of the launcher's options that loads a file which `launcher`'s words spell, as
    `--name value` or `--name=value`, by its name; `None` where none does."""
    return next(
        (name for word in launcher if (name := word.partition("=")[0]) in LAUNCHER_FILE_OPTIONS),
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
    """The runner's standard output, copied as it arrives to the caller's stream and, up to one
    byte past `MAX_REPORT_BYTES`, to the report, by a thread of its own that owns both descriptors.

    The thread reads until the pipe ends; once `finish` is asked, it stops at the first moment the
    pipe holds nothing, or once it has copied `MAX_REPORT_BYTES` more, so a descendant that left the
    process group and writes on cannot keep it. A caller's stream that takes text alone is handed
    whole characters, decoded across reads. A caller that has gone (`| head`, a closed stream) is
    written nothing more, and the report goes on filling.
    """

    def __init__(self, source: IO[bytes], report: int, caller: TextIO) -> None:
        self._source = source
        self._report = report
        self._room = MAX_REPORT_BYTES + 1
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
        while share:
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
            os.close(self._report)

    def finish(self) -> None:
        """Stop once the pipe is drained, and wait for the thread to end."""
        self._stop.set()
        self._thread.join()


def _open_report(path: Path) -> int:
    """A descriptor for the teed report, a file this run creates: refused if anything is there."""
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC
    return os.open(path, flags, 0o600)


def _launch(plan: Plan, cwd: Path, env: Mapping[str, str], teed: bool) -> subprocess.Popen[bytes]:
    # S603: the adapter's plan of the command the caller typed, list form, never a shell. A
    # session of its own puts what it starts in one process group, which is ended however it
    # finishes. Standard input and standard error are the caller's; standard output is too, or
    # a pipe the tee copies to the caller's whole when it is the report.
    return subprocess.Popen(  # noqa: S603
        list(plan.argv),
        cwd=cwd,
        env=dict(env),
        stdout=subprocess.PIPE if teed else None,
        start_new_session=True,
    )


@dataclass(frozen=True)
class _Ran:
    stopped: str | None
    exit_code: int | None


def _run(plan: Plan, cwd: Path, env: Mapping[str, str], timeout: float, echo: TextIO) -> _Ran:
    """Run `plan` in `cwd` under `env`, its process group ended however it finishes, a report on
    standard output teed to `echo`."""
    teed = plan.source is ReportSource.STDOUT
    report = _open_report(plan.report) if teed else None
    sys.stdout.flush()
    with contextlib.suppress(OSError, ValueError):
        echo.flush()
    try:
        process = _launch(plan, cwd, env, teed)
    except OSError:
        if report is not None:
            os.close(report)
        return _Ran(NOT_STARTED, None)
    tee = None if report is None or process.stdout is None else _Tee(process.stdout, report, echo)
    try:
        try:
            with _signals_end_the_run():
                processes.exited(process, timeout)
        except subprocess.TimeoutExpired:
            processes.end(process)
            return _Ran(TIMED_OUT, None)
        except (KeyboardInterrupt, _Signalled):
            # A terminal's Ctrl-C reaches stayfixed's process group and not the command's session,
            # so nothing but `prove` ends the command's group on the way out.
            processes.end(process)
            return _Ran(INTERRUPTED, None)
        except BaseException:
            processes.end(process)
            raise
        # The command has exited; what it left in its group goes now, while its pid is unreaped.
        processes.kill_group(process)
        return _Ran(None, process.wait())
    finally:
        if tee is not None:
            tee.finish()


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
) -> Receipt:
    """Run `argv` in `cwd` and say what its runner's report proves. `adapters` defaults to every
    adapter this stayfixed ships (`shipped_adapters`); `echo`, where a report on the runner's
    standard output is teed, to the caller's standard output.

    An adapter whose plan's program is not an absolute path is a defect in stayfixed, as a module
    that does not import is, and raises `ValueError`: a bare name would be found from stayfixed's
    own directory and `PATH`, never where the adapter looked.
    """
    given = tuple(argv)
    shown = redacted(given)
    root = checkout_root(cwd) or cwd
    launch = read_launch(given)
    command = launch.command
    known = shipped_adapters() if adapters is None else adapters
    adapter = next((each for each in known if command and each.recognises(command)), None)
    if adapter is None:
        return _receipt(_Outcome(unproven=NOT_RECOGNISED), shown)
    assigned = assignments(launch.assignments)
    # The launcher's own variables that load a file, where the launch runs one.
    loaders = LAUNCHER_FILE_VARIABLES if launch.launcher else frozenset()
    forged = sorted(name for name in assigned if name in adapter.forging | loaders)
    if forged:
        return _receipt(
            _Outcome(refused=ASSIGNED_FORGING), shown, detail=", ".join(forged), runner=adapter.name
        )
    loading = file_option(launch.launcher)
    if loading is not None:
        return _receipt(
            _Outcome(refused=REFUSED_LAUNCHER_OPTION), shown, detail=loading, runner=adapter.name
        )
    scratch = Path(tempfile.mkdtemp(prefix="stayfixed-prove-"))
    try:
        planned = adapter.plan(
            launch.launcher, command, cwd=cwd, root=root, scratch=scratch, environ=environ
        )
        if isinstance(planned, Refused):
            return _receipt(_Outcome(refused=planned.reason), shown, adapter.name)
        if isinstance(planned, Unresolved):
            return _receipt(_Outcome(unproven=planned.reason), shown, adapter.name)
        # An inherited one goes from the run's environment as the plan's own scrub would go.
        kept = {name: value for name, value in environ.items() if name not in loaders}
        caller = echo if echo is not None else sys.stdout
        return _proved(adapter.name, planned, assigned, shown, cwd, root, kept, timeout, caller)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def _proved(
    runner: str,
    plan: Plan,
    assigned: Mapping[str, str],
    shown: tuple[str, ...],
    cwd: Path,
    root: Path,
    environ: Mapping[str, str],
    timeout: float,
    echo: TextIO,
) -> Receipt:
    if not os.path.isabs(plan.argv[0]):
        raise ValueError(f"the {runner} adapter planned a program that is not absolute")
    before = tree.state(root, plan.discovery, plan.configs)
    if Path(os.path.realpath(plan.argv[0])) != plan.program:
        return _receipt(_Outcome(refused=RESOLVED_ELSEWHERE), shown, runner, plan, before=before)
    env = {name: value for name, value in environ.items() if name not in plan.scrub}
    env |= assigned
    env |= plan.set_env
    ran = _run(plan, cwd, env, timeout, echo)
    after = tree.state(root, plan.discovery, plan.configs)
    if ran.stopped is not None:
        outcome, detail, digest = _Outcome(unproven=ran.stopped), "", None
    else:
        counts, unread, detail, digest = _counted(plan)
        outcome = _Outcome(unproven=unread, counts=counts, exit_code=ran.exit_code)
    return _receipt(
        outcome, shown, runner, plan, detail=detail, before=before, after=after, digest=digest
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
) -> Receipt:
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
        verified=plan.verified if plan is not None else True,
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
    )


def line(receipt: Receipt) -> str:
    """The receipt in one line: the verdict and its reason in words, the counts, the runner, and
    the files that can shape the report. A name the tree chose prints only inside the path
    grammar (`printed.printable`); `--json` carries every one."""
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
        if not receipt.verified:
            runner += ", not verified"
        parts.append(runner)
    if receipt.configs:
        listed = ", ".join(printable(name) for name in receipt.configs)
        more = f" and {receipt.configs_more} more" if receipt.configs_more else ""
        parts.append(f"configuration: {listed}{more}")
    if receipt.untracked:
        listed = ", ".join(printable(name) for name in receipt.untracked)
        more = f" and {receipt.untracked_more} more" if receipt.untracked_more else ""
        parts.append(f"untracked in the discovery set: {listed}{more}")
    return "; ".join(parts)
