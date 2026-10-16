"""Run a command with a pseudo-terminal on its standard streams, as a person at a terminal would.

`stayfixed trust approve` refuses unless standard input is a terminal, so a smoke script or a test
that approves through a real subprocess needs one. `run_in_pty` opens a pseudo-terminal pair and
starts the command with the terminal end as its stdin, stdout and stderr, then reads everything it
printed off the other end until it exits.

`pty.openpty` and `subprocess.Popen`, not `pty.fork`: forking a process that runs threads, as a
test runner's worker may, can deadlock the child, and Python warns of it, which this suite turns
into an error. `Popen` starts the child without running Python in it between the fork and the exec.
"""

from __future__ import annotations

import os
import pty
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path

# How many bytes one read of the terminal's other end asks for. A named cap: any size works, the
# loop reads until the child closes its end.
_CHUNK = 4096


def run_in_pty(
    argv: Sequence[str], *, env: Mapping[str, str], cwd: Path | None = None
) -> tuple[int, str]:
    """`argv`'s exit code and everything it printed, run under a pseudo-terminal."""
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
    finally:
        os.close(terminal)
    chunks: list[bytes] = []
    try:
        while True:
            try:
                data = os.read(controller, _CHUNK)
            except OSError:  # Linux answers EIO once the child has closed its end
                break
            if not data:  # macOS answers end of file
                break
            chunks.append(data)
    finally:
        os.close(controller)
    code = child.wait()
    return code, b"".join(chunks).decode("utf-8", "replace")
