"""A runner adapter for the suite, and the runner program it plans, in one file.

No real test runner is installed where the mutation oracle runs, so the run, the verdict cascade
and the receipt are proved against this pair: `StandIn` recognises the word `stand-in` and plans
this file, run by the interpreter running the suite, as its runner; run as a program, the file
prints what it is told to, writes the report it is told to where the plan said, and exits with
the code it is told to. The real adapters' own plans are tested against recorded reports.

The program's options, all after the word `stand-in`:

- `--report SHAPE`: `pass`, `fail`, `empty`, `all-skipped`, `doctype` (a JUnit document that
  declares one; an event that is not JSON on standard output) or `none` (no report at all);
- `--code N`: the exit code;
- `--print TEXT`: a line printed first, as text, or framed as an `output` event when the report
  is standard output;
- `--expect-env NAME=VALUE`, `--expect-unset NAME`, `--expect-cwd PATH`: each turns the report's
  every test into a failure when it does not hold, so the verdict says what the runner saw;
- `--touch NAME`: a file written in the directory it runs in, before the report;
- `--sleep SECONDS`: a silence before anything is printed or written;
- `--report-from-stdin`: the report's shape is the first line standard input holds, where it holds
  one, as a runner a debugger drives takes its commands there;
- `--pad N`: `N` bytes of whitespace after the report's last element, or after its last event;
- `--hang STARTED LATE`: leave a child that holds a lock on `held(LATE)` for as long as it lives,
  writes `STARTED` once it holds it, and writes `LATE` a few seconds later; and never exit;
- `--escape PIDFILE` and `--escape-quiet PIDFILE`: leave a child in a session of its own, out of
  the run's process group, that holds standard output open for as long as it lives and writes to
  it without pause, or writes nothing, and exit once the child has written its pid in `PIDFILE`,
  which a loud one does only after its first write;

and any other option is ignored, as a runner ignores the options it does not take.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from stayfixed.profiles.runners import Plan, Refused, ReportKind, ReportSource, Unresolved

NAME = "stand-in"
PROGRAM = Path(__file__).resolve()
# How long `--hang`'s child waits before it writes `LATE`: past the point a test has ended the
# group and looked, short enough that a group left running is seen.
LATE_AFTER_SECONDS = 3

JUNIT = {
    "pass": b'<testsuite><testcase name="a"/><testcase name="b"/></testsuite>',
    "fail": b'<testsuite><testcase name="a"/><testcase name="b"><failure/></testcase></testsuite>',
    "empty": b'<testsuite tests="0"/>',
    "all-skipped": b'<testsuite><testcase name="a"><skipped/></testcase></testsuite>',
    "doctype": b"<!DOCTYPE testsuite><testsuite/>",
}
_EVENTS = {
    "pass": [{"Action": "pass", "Package": "p", "Test": "TestA"}],
    "fail": [{"Action": "fail", "Package": "p", "Test": "TestA"}],
    "empty": [{"Action": "pass", "Package": "p"}],
    "all-skipped": [{"Action": "skip", "Package": "p", "Test": "TestA"}],
}


@dataclass(frozen=True)
class StandIn:
    """`RunnerAdapter` for the word `stand-in`. `seen` collects each `plan` call's `root` and
    `scratch`, so a test can ask what the run handed it and whether the scratch is gone, and
    `launches` each call's `launch`."""

    name: str = NAME
    forging: frozenset[str] = frozenset({"FORGE"})
    source: ReportSource = ReportSource.FILE
    set_env: Mapping[str, str] = field(default_factory=dict)
    scrub: frozenset[str] = frozenset()
    discovery: tuple[str, ...] = ("test_*.py",)
    configs: tuple[str, ...] = ("stand-in.toml",)
    refuse: str | None = None
    unresolved: str | None = None
    # Plans a link to the interpreter and repoints it before the plan is returned: a program
    # swapped between the plan and the launch.
    swap: bool = False
    # Plans a program that is a file and cannot be executed.
    unlaunchable: bool = False
    # Plans its program by a bare name, as no adapter may.
    relative: bool = False
    seen: list[tuple[Path, Path]] = field(default_factory=list)
    launches: list[tuple[str, ...]] = field(default_factory=list)

    def recognises(self, command: Sequence[str]) -> bool:
        return bool(command) and Path(command[0]).name == NAME

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
        self.seen.append((root, scratch))
        self.launches.append(tuple(launch))
        if self.refuse is not None:
            return Refused(self.refuse)
        if self.unresolved is not None:
            return Unresolved(self.unresolved)
        program = Path(os.path.realpath(sys.executable))
        first = sys.executable
        if self.unlaunchable:
            first = str(scratch / "runner")
            Path(first).write_text("not a program\n", encoding="utf-8")
            program = Path(os.path.realpath(first))
        if self.relative:
            first = Path(sys.executable).name
        if self.swap:
            link = scratch / "runner"
            link.symlink_to(sys.executable)
            first = str(link)
            link.unlink()
            link.symlink_to(shutil.which("true") or "/bin/true")
        report = scratch / "report"
        kind = ReportKind.EVENTS if self.source is ReportSource.STDOUT else ReportKind.JUNIT
        argv = (first, str(PROGRAM), "--report-path", str(report), "--source", self.source)
        return Plan(
            argv=(*argv, *command[1:]),
            program=program,
            kind=kind,
            source=self.source,
            report=report,
            set_env=self.set_env,
            scrub=self.scrub,
            discovery=self.discovery,
            configs=self.configs,
        )


def _options(argv: list[str]) -> dict[str, list[str]]:
    """Each `--name value` pair, by name; `--name=value` and a bare word are ignored."""
    found: dict[str, list[str]] = {}
    takes = {"--report-path": 1, "--source": 1, "--report": 1, "--code": 1, "--print": 1}
    takes |= {"--expect-env": 1, "--expect-unset": 1, "--expect-cwd": 1, "--touch": 1}
    takes |= {"--pad": 1, "--escape": 1, "--escape-quiet": 1, "--sleep": 1}
    takes |= {"--hang": 2}
    index = 0
    while index < len(argv):
        word = argv[index]
        count = takes.get(word)
        if count is None:
            index += 1
            continue
        found.setdefault(word, []).extend(argv[index + 1 : index + 1 + count])
        index += 1 + count
    return found


def _holds(options: dict[str, list[str]]) -> bool:
    for pair in options.get("--expect-env", []):
        name, _, value = pair.partition("=")
        if os.environ.get(name) != value:
            return False
    if any(name in os.environ for name in options.get("--expect-unset", [])):
        return False
    return all(os.getcwd() == where for where in options.get("--expect-cwd", []))


def held(late: Path) -> Path:
    """The file `--hang`'s child holds a lock on for as long as it lives: the kernel lets go of it
    the moment the child ends, so a test sees that it has ended without waiting for `LATE`."""
    return late.with_name(f"{late.name}.held")


def _hang(started: str, late: str) -> None:
    child = (
        "import fcntl, time, pathlib\n"
        f"lock = open({str(held(Path(late)))!r}, 'w')\n"
        "fcntl.flock(lock, fcntl.LOCK_EX)\n"
        f"pathlib.Path({started!r}).touch()\n"
        f"time.sleep({LATE_AFTER_SECONDS})\n"
        f"pathlib.Path({late!r}).touch()\n"
    )
    subprocess.Popen([sys.executable, "-c", child])
    while True:
        time.sleep(1)


def _escape(pidfile: str, *, loud: bool) -> None:
    # The child names itself in `pidfile`, whole, once a loud one has written its first chunk, and
    # the runner exits only once it is there: the pipe is never found empty for want of a child
    # that had not started yet, so what ends the tee is its bound, not a race with the child.
    named = (
        "import os, pathlib, sys, time\n"
        "def named():\n"
        f"    part = pathlib.Path({pidfile + '.part'!r})\n"
        "    part.write_text(str(os.getpid()), encoding='utf-8')\n"
        f"    os.replace(part, {pidfile!r})\n"
    )
    writer = (
        "def write():\n"
        "    sys.stdout.write('x' * 4096)\n"
        "    sys.stdout.flush()\n"
        "write()\n"
        "named()\n"
        "while True:\n"
        "    write()\n"
    )
    quiet = "named()\ntime.sleep(600)\n"
    code = named + (writer if loud else quiet)
    child = subprocess.Popen([sys.executable, "-c", code], start_new_session=True)
    while not Path(pidfile).exists() and child.poll() is None:
        time.sleep(0.01)


def main(argv: list[str]) -> int:
    options = _options(argv)
    [report_path] = options["--report-path"]
    [source] = options["--source"]
    shape = (options.get("--report") or ["pass"])[0]
    if shape not in ("none", "doctype") and not _holds(options):
        shape = "fail"
    if "--report-from-stdin" in argv:
        shape = sys.stdin.buffer.readline().decode().strip() or shape
    time.sleep(float((options.get("--sleep") or ["0"])[0]))
    for name in options.get("--touch", []):
        Path(name).write_text("touched\n", encoding="utf-8")
    out = sys.stdout.buffer
    for text in options.get("--print", []):
        if source == ReportSource.STDOUT:
            event = {"Action": "output", "Package": "p", "Output": f"{text}\n"}
            out.write(json.dumps(event).encode() + b"\n")
        else:
            out.write(text.encode() + b"\n")
    pad = b" " * int((options.get("--pad") or ["0"])[0])
    if source == ReportSource.STDOUT:
        if shape == "doctype":
            out.write(b"not an event\n")
        for event in _EVENTS.get(shape, []):
            out.write(json.dumps(event).encode() + b"\n")
        out.write(pad)
    elif shape != "none":
        Path(report_path).write_bytes(JUNIT[shape] + pad)
    out.flush()
    if "--escape" in options:
        _escape(options["--escape"][0], loud=True)
    if "--escape-quiet" in options:
        _escape(options["--escape-quiet"][0], loud=False)
    if "--hang" in options:
        started, late = options["--hang"]
        _hang(started, late)
    return int((options.get("--code") or ["0"])[0])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
