"""The `prove` command: run a test command where it is typed and say what its runner's report
proves.

`prove` reads no configuration and takes neither `--root` nor `--machine`: the command runs in the
directory it is typed in, and the project it answers for is that directory's git top-level, or the
directory itself outside a repository. The command is everything after `--`, so no word of it is
read as an option of `prove`'s; a line with no `--`, or nothing after it, is a usage error.
`--junit PATH`, read from that directory, names the JUnit report of a runner no adapter knows.
"""

from __future__ import annotations

import argparse
import dataclasses
import os
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from stayfixed.areas import SubParsers
from stayfixed.prove.run import EXIT, PROVE_TIMEOUT_SECONDS, line, prove
from stayfixed.result import Result

_SEPARATOR = "--"
_NO_COMMAND = (
    "the command to run goes after `--`: "
    "stayfixed prove [--timeout SECONDS] [--junit PATH] -- COMMAND …"
)
_NOT_SECONDS = "--timeout takes a number of seconds above 0"


class _Command(argparse.Action):
    """The words after `--`, which must be there and be followed by a command. argparse keeps the
    `--` in what a `REMAINDER` positional takes, on every supported interpreter, so its absence
    is what tells a line that never had one."""

    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: str | Sequence[Any] | None,
        option_string: str | None = None,
    ) -> None:
        words = list(values or [])
        if words[:1] != [_SEPARATOR] or len(words) < 2:
            parser.error(_NO_COMMAND)
        setattr(namespace, self.dest, words[1:])


def _seconds(value: str) -> float:
    try:
        seconds = float(value)
    except ValueError:
        raise argparse.ArgumentTypeError(_NOT_SECONDS) from None
    if not seconds > 0:  # false for NaN too
        raise argparse.ArgumentTypeError(_NOT_SECONDS)
    return seconds


def run_prove(args: argparse.Namespace) -> Result:
    # Under `--json` standard output is the one object the frame prints, so a report on the
    # runner's standard output is teed, every byte of it, to standard error instead.
    echo = sys.stderr if getattr(args, "as_json", False) else None
    receipt = prove(
        args.command,
        cwd=Path.cwd(),
        environ=os.environ,
        timeout=args.timeout,
        echo=echo,
        junit=args.junit,
    )
    return Result(line(receipt), dataclasses.asdict(receipt), exit_code=EXIT[receipt.verdict])


def register(groups: SubParsers) -> None:
    parser = groups.add_parser(
        "prove", help="run a test command here and say what its runner's own report proves"
    )
    parser.add_argument(
        "--timeout",
        type=_seconds,
        default=PROVE_TIMEOUT_SECONDS,
        metavar="SECONDS",
        help=f"end the run past this many seconds (default: {PROVE_TIMEOUT_SECONDS})",
    )
    parser.add_argument(
        "--junit",
        type=Path,
        metavar="PATH",
        help=(
            "count the JUnit report the command writes at PATH, for a runner no adapter knows; "
            "the runner is marked not verified"
        ),
    )
    parser.add_argument(
        "command",
        nargs=argparse.REMAINDER,
        action=_Command,
        metavar="-- COMMAND …",
        help="the test command, run as typed in this directory",
    )
    parser.set_defaults(func=run_prove)
