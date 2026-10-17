"""`scripts/ptyrun.py`: a command run under a pseudo-terminal, as a person at a terminal would run
it. Its working cases run wherever an approval is made through a subprocess
(`tests/trust/test_commands.py`); this file holds what those never reach."""

from __future__ import annotations

import os
import pty
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from tests.scriptload import SCRIPTS, load


def test_a_command_that_cannot_start_leaves_no_descriptor_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # `Popen` raising left the controller end open: nothing closed it on that path, and a suite
    # that starts many approvals leaked one descriptor per command that could not start. Mutation
    # (`mutations/`'s "a pseudo-terminal whose command cannot start keeps its controller open"):
    # the controller stays open.
    ptyrun = load(SCRIPTS / "ptyrun.py", "ptyrun_for_its_own_tests")
    opened: list[int] = []
    real_openpty = pty.openpty

    def openpty() -> tuple[int, int]:
        pair = real_openpty()
        opened.extend(pair)
        return pair

    closed: list[int] = []
    real_close = os.close

    def close(fd: int) -> None:
        closed.append(fd)
        real_close(fd)

    monkeypatch.setattr(pty, "openpty", openpty)
    monkeypatch.setattr(os, "close", close)
    with pytest.raises(FileNotFoundError):
        ptyrun.run_in_pty([str(tmp_path / "no-such-program")], env={})
    assert len(opened) == 2
    assert sorted(fd for fd in closed if fd in opened) == sorted(opened)


def test_a_command_that_does_not_finish_is_killed_at_the_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The read had no deadline: a command that hung, or left a process holding the terminal open,
    # blocked the caller for ever, and a CI job with it. Mutations (`mutations/`'s "a
    # pseudo-terminal read waits past its deadline" -> the command runs out its five seconds and
    # no `TimeoutError` comes; "a pseudo-terminal command past its deadline is left running" ->
    # it is still running when the caller is told it was killed).
    ptyrun = load(SCRIPTS / "ptyrun.py", "ptyrun_for_its_own_tests")
    started: list[subprocess.Popen[bytes]] = []
    real_popen = subprocess.Popen

    def popen(*args: Any, **kwargs: Any) -> subprocess.Popen[bytes]:
        child: subprocess.Popen[bytes] = real_popen(*args, **kwargs)
        started.append(child)
        return child

    monkeypatch.setattr(subprocess, "Popen", popen)
    sleeper = [sys.executable, "-c", "import time; time.sleep(5)"]
    with pytest.raises(TimeoutError):
        ptyrun.run_in_pty(sleeper, env=dict(os.environ), deadline=0.5)
    try:
        assert len(started) == 1
        assert started[0].poll() is not None
    finally:
        for child in started:
            child.kill()
            child.wait()
