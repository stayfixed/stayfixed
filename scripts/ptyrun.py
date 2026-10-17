"""Run a command with a pseudo-terminal on its standard streams, as a person at a terminal would.

`stayfixed trust approve` refuses unless standard input is a terminal, so a smoke script or a test
that approves through a real subprocess needs one. `run_in_pty` opens a pseudo-terminal pair and
starts the command with the terminal end as its stdin, stdout and stderr, then reads everything it
printed off the other end until it exits, or until `deadline` seconds have passed, when it kills the
command's process group and raises `TimeoutError`.

`pty.openpty` and `subprocess.Popen`, not `pty.fork`: forking a process that runs threads, as a
test runner's worker may, can deadlock the child, and Python warns of it, which this suite turns
into an error. `Popen` starts the child without running Python in it between the fork and the exec.
"""

from __future__ import annotations

import contextlib
import os
import pty
import select
import signal
import subprocess
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import NoReturn

# How many bytes one read of the terminal's other end asks for. A named cap: any size works, the
# loop reads until the child closes its end.
_CHUNK = 4096
# How long `run_in_pty` gives a command, from its start to its exit, in seconds. A named cap, and no
# shipped file agrees with it: it bounds a command that hangs, one that leaves a process holding the
# terminal open after it exits, and one that closes the terminal and goes on running, each of which
# blocked the caller for ever, and a CI job with it until the job's own timeout. The commands run
# under it, an approval and the smokes' hook runs, are short ones, and the bound is meant to sit
# far above them on a loaded runner rather than to measure them.
DEADLINE_SECONDS = 120.0
# How many of the last characters the command printed a `TimeoutError` carries: where it stopped.
_TAIL = 400


def run_in_pty(
    argv: Sequence[str],
    *,
    env: Mapping[str, str],
    cwd: Path | None = None,
    deadline: float = DEADLINE_SECONDS,
) -> tuple[int, str]:
    """`argv`'s exit code and everything it printed, run under a pseudo-terminal; `TimeoutError`,
    its process group killed, when it has not exited within `deadline` seconds."""
    controller, terminal = pty.openpty()
    try:
        child = subprocess.Popen(  # noqa: S603 - the caller's own argv, never a shell
            list(argv),
            stdin=terminal,
            stdout=terminal,
            stderr=terminal,
            env=dict(env),
            cwd=cwd,
            start_new_session=True,
        )
    except BaseException:
        # No child will close its end and nothing below will read this one, so it is closed here.
        os.close(controller)
        raise
    finally:
        os.close(terminal)
    chunks: list[bytes] = []
    give_up = time.monotonic() + deadline
    try:
        while True:
            left = give_up - time.monotonic()
            if left <= 0 or not select.select([controller], [], [], left)[0]:
                _give_up(child, argv[0], deadline, chunks)
            try:
                data = os.read(controller, _CHUNK)
            except OSError:  # Linux answers EIO once the child has closed its end
                break
            if not data:  # macOS answers end of file
                break
            chunks.append(data)
    finally:
        os.close(controller)
    # The terminal closed, and the command may still be running: the deadline bounds its exit too.
    try:
        code = child.wait(timeout=max(give_up - time.monotonic(), 0))
    except subprocess.TimeoutExpired:
        _give_up(child, argv[0], deadline, chunks)
    return code, b"".join(chunks).decode("utf-8", "replace")


def _give_up(
    child: subprocess.Popen[bytes], program: str, deadline: float, chunks: list[bytes]
) -> NoReturn:
    """Kill `child`'s process group and raise the `TimeoutError` that says so, with the tail of
    what it printed."""
    _kill(child)
    tail = b"".join(chunks).decode("utf-8", "replace")[-_TAIL:]
    raise TimeoutError(
        f"{program} did not exit within {deadline:g} s under a pseudo-terminal, so its process "
        f"group was killed; the last it printed: {tail!r}"
    )


def _kill(child: subprocess.Popen[bytes]) -> None:
    """Kill `child`'s process group, which `start_new_session` made its own, and reap it."""
    # `ProcessLookupError`: every process in the group has exited already.
    with contextlib.suppress(ProcessLookupError):
        os.killpg(child.pid, signal.SIGKILL)
    child.wait()
