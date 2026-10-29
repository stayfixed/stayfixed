"""A Claude Code `Stop` hook that runs `stayfixed prove` before the agent may finish.

    python3 -I prove_on_stop.py [--timeout SECONDS] -- COMMAND...

Claude Code runs it when the agent finishes responding, with the hook's input, one JSON object,
on standard input. It runs `stayfixed prove --json --timeout SECONDS -- COMMAND...` from `PATH`
at the top of the work tree that holds the input's `cwd`, and answers by its exit code alone:

- 0 when `prove` answered `proved`, and at once, without a run, when `stop_hook_active` says the
  agent is already working on because this hook blocked it;
- 2 on any other verdict, which keeps the agent working, with one line on stderr as the reason
  it is given;
- 1 when the input is not one JSON object, when the arguments are not the ones above, or when
  `stayfixed` cannot start or answers no JSON object. Claude Code shows that to the user and lets
  the stop go ahead, since no continuation repairs a missing install.

It prints nothing on standard output, ever: Claude Code reads a JSON object there on every exit
code, and `prove`'s own would be taken for this hook's answer.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
from collections.abc import Sequence
from typing import NoReturn

# The bound `prove` is given by default, below the 600 s Claude Code allows a command hook, so
# `prove` ends its own run and answers before the hook is cut off.
DEFAULT_TIMEOUT_SECONDS = "540"
# How long the `git` that finds the work tree's top level may take: it reads a few files, and a
# hung one must not hold the stop. No shipped file fixes the number.
GIT_TIMEOUT_SECONDS = 10
# A non-blocking error: the stop goes ahead and the user sees stderr. Exit 2 alone blocks.
NOT_BLOCKING = 1
BLOCKING = 2


class _Usage(Exception):
    pass


class _Parser(argparse.ArgumentParser):
    # argparse exits 2 on a usage error, which Claude Code would read as "keep working", every
    # time the agent stopped. A misconfigured hook is the user's to see, so it exits 1 instead.
    def error(self, message: str) -> NoReturn:
        raise _Usage(message)


def _seconds(text: str) -> str:
    """`text` as typed, once it reads as a number of seconds above 0: `prove` reads it again."""
    if not float(text) > 0:
        raise ValueError(text)
    return text


def _top_level(cwd: object) -> str | None:
    """The top of the work tree that holds `cwd`, or None when there is no such directory."""
    if not isinstance(cwd, str) or not os.path.isdir(cwd):
        return None
    try:
        # A fixed argv, never through a shell.
        done = subprocess.run(  # noqa: S603
            ["git", "-C", cwd, "rev-parse", "--show-toplevel"],  # noqa: S607
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    top = done.stdout.strip()
    return top if done.returncode == 0 and os.path.isdir(top) else None


def _say(line: str) -> None:
    print(f"prove_on_stop: {line}", file=sys.stderr)


def main(argv: Sequence[str] | None = None) -> int:
    parser = _Parser(prog="prove_on_stop.py", add_help=False)
    parser.add_argument("--timeout", type=_seconds, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("command", nargs="+")
    try:
        options = parser.parse_args(argv)
    except _Usage as usage:
        _say(f"usage: [--timeout SECONDS] -- COMMAND...: {usage}")
        return NOT_BLOCKING

    try:
        event = json.loads(sys.stdin.read())
    except (ValueError, UnicodeDecodeError) as error:
        _say(f"the hook's input is not JSON: {error}")
        return NOT_BLOCKING
    if not isinstance(event, dict):
        _say("the hook's input is not one JSON object")
        return NOT_BLOCKING
    # The agent is working on because this hook blocked its last stop. Claude Code's cap of eight
    # continuations resets on every tool call, so this is what keeps a tree the agent cannot make
    # green from blocking every stop.
    if event.get("stop_hook_active") is True:
        return 0

    command = list(options.command)
    argv_prove = ["stayfixed", "prove", "--json", "--timeout", options.timeout, "--"]
    try:
        # The user's own command from the hook's settings, run as typed and never through a shell.
        done = subprocess.run(  # noqa: S603
            [*argv_prove, *command],
            cwd=_top_level(event.get("cwd")),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except OSError as error:
        _say(f"stayfixed could not start: {error}")
        return NOT_BLOCKING
    try:
        answer = json.loads(done.stdout)
    except ValueError:
        answer = None
    verdict = answer.get("verdict") if isinstance(answer, dict) else None
    if not isinstance(answer, dict) or not isinstance(verdict, str):
        _say(f"stayfixed prove exited {done.returncode} and answered no verdict")
        return NOT_BLOCKING
    if verdict == "proved":
        return 0
    reason = answer.get("reason")
    because = f" ({reason})" if isinstance(reason, str) and reason else ""
    _say(
        f"stayfixed prove answered {verdict}{because} for {shlex.join(command)}. Run it to a"
        " green result, or say why there cannot be one, before finishing."
    )
    return BLOCKING


if __name__ == "__main__":
    sys.exit(main())
