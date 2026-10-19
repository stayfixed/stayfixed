"""Where a test command's program is, found the way a shell running the command finds it.

A leaf of the standard library alone, which every runner adapter and the `prove` core use, so
that a run an adapter plans and a `--junit` run find their program by one rule: a word holding a
`/` is read from the directory the command runs in, and a bare name is the first on the run's own
`PATH`, each entry of which is read from that directory too. The run's `PATH` is the one the
command runs under, its own assignment of `PATH` included, never the caller's alone.
"""

from __future__ import annotations

import os
import stat
from collections.abc import Mapping, Sequence
from pathlib import Path

# The word after which a runner reads no option of its own.
SEPARATOR = "--"


def executable(path: Path) -> bool:
    """Whether `path`, followed through links, is a regular file this process may execute; a path
    that cannot be asked about is not one."""
    try:
        return stat.S_ISREG(os.stat(path).st_mode) and os.access(path, os.X_OK)
    except (OSError, ValueError):
        return False


def found(word: str, cwd: Path, environ: Mapping[str, str]) -> Path | None:
    """The executable `word` names for a command run in `cwd` under `environ`: a word holding a
    `/`, read from `cwd`; a bare name, the first of `environ`'s `PATH` (`os.defpath` where it has
    none) that holds one, each entry read from `cwd`. The path it is found by, not its realpath:
    a virtual environment's `bin/python` is a link, and the file it points at, run by its own
    path, runs outside the environment. `None` where nothing is there."""
    if os.sep in word:
        candidates = [cwd / word]
    else:
        path = environ.get("PATH", os.defpath)
        candidates = [cwd / entry / word for entry in path.split(os.pathsep)]
    return next((candidate for candidate in candidates if executable(candidate)), None)


def not_found(word: str) -> str:
    """What a receipt says was looked for where `word`, a command's first word, names nothing
    (`found`): a word holding a `/` is a path, read where the command runs and never looked up
    on `PATH`; a bare name is looked up on `PATH`."""
    return f"no executable file at {word}" if os.sep in word else f"no {word} on PATH"


def launched(
    launch: Sequence[str], argv: Sequence[str], cwd: Path, environ: Mapping[str, str]
) -> tuple[str, ...] | None:
    """The argv that runs `argv` behind `launch`, the launcher's words (`uv run` and its options,
    as typed), kept in front: the first of all the words found (`found`) and named by that path,
    every other word as it is. Without a launcher it is `argv`, its first word found. `None` where
    that first word names nothing there."""
    words = (*launch, *argv)
    program = found(words[0], cwd, environ) if words else None
    return None if program is None else (str(program), *words[1:])


def options(args: Sequence[str]) -> tuple[str, ...]:
    """The words of `args` before a `--`, which ends a runner's options: every word after it is an
    operand."""
    return tuple(args[: _cut(args)])


def before_separator(args: Sequence[str], ours: Sequence[str]) -> tuple[str, ...]:
    """`args` with `ours` added last among its options (`options`), before a `--` where there is
    one."""
    cut = _cut(args)
    return (*args[:cut], *ours, *args[cut:])


def _cut(args: Sequence[str]) -> int:
    return list(args).index(SEPARATOR) if SEPARATOR in args else len(args)
