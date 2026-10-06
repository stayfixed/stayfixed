"""Python's red-run hint: a failed pytest run may have imported bytecode older than its source.

Bytecode newer than its source's last recorded edit is one of the two environment faults that
produce a red run no baseline A/B can attribute, because both halves of the A/B run inside it:
the interpreter imports a build that predates a fix on disk -- deterministically, in the shape of
the very defect the test pins. It has cost real time: a high-severity ledger entry rejected as a
stale cache. The other fault, uncommitted work in the tree, belongs to no stack, and the core
names it (`stayfixed.guards.hygiene`).

Matching an actual pytest invocation, not the six letters "pytest" appearing anywhere in the
command text: `recognises` reads one simple command, unwrapped as `RedRunHint.recognises`
describes, and anchors on its first word. Under-reporting an unrecognised launcher is the safe
direction for a warn-only note.

Nothing a repository authored leaves this module: `note` renders a fixed sentence from a count,
and a `ledger.code_roots` entry is walked and never printed.
"""

from __future__ import annotations

import importlib.util
import os
import struct
from collections.abc import Iterable, Mapping, Sequence
from itertools import pairwise
from pathlib import Path
from typing import TYPE_CHECKING

from stayfixed.fsops import open_directory, read_bounded
from stayfixed.guards.api import contained_roots

if TYPE_CHECKING:
    from stayfixed.config.schema import Config
    from stayfixed.profiles.hints import RedRunHint

_PYTEST = "pytest"
_PYTHON_ARGV0_PREFIX = "python"
# PEP 552: every .pyc opens with a 4-byte magic, then a 4-byte little-endian flags word, then
# four more bytes whose MEANING is decided by bit 0 of those flags.
#
# Bit 0 clear -- timestamp-based, the default -- makes them the source's mtime as a uint32, the
# value CPython itself compares against the source's current mtime. That is the only comparison
# that agrees with the interpreter's own staleness verdict, which is why it is the one made here
# and not a `pyc mtime > source mtime` on the filesystem.
#
# Bit 0 SET -- hash-based -- makes them the first half of the source's hash instead, and nothing
# in them can be compared to an mtime at all: doing so declares every such file stale, forever.
# That is not a rare shape. `py_compile` switches to it on its own whenever `SOURCE_DATE_EPOCH`
# is set in the environment, and `compileall --invalidation-mode checked-hash` asks for it
# outright, so a reproducible build produces a whole tree of them. A hash-based `.pyc` is
# therefore NOT JUDGED: under-reporting is this module's safe direction throughout, and telling
# somebody their bytecode predates a fix -- delete `__pycache__` and re-run -- when it is in
# fact current is exactly the false alarm that direction exists to avoid.
#
# The MAGIC decides whether this interpreter would ever open the file at all, and reading past a
# foreign one is the same class of defect as reading a hash-based header as an mtime. A
# `__pycache__` accumulates one `.pyc` per interpreter tag and nothing removes the old ones, so
# a `mod.cpython-311.pyc` left by a 3.11 run sits beside the current tag's file forever,
# recording the source mtime as of THAT run. Any edit since makes it mismatch -- while the
# bytecode the running interpreter actually imports is fresh. Measured on a tree whose current
# bytecode had just been compiled: one foreign-tag leftover, `_stale_bytecode` -> 1, and the
# notice fires on every red run for as long as the file is on disk. So a header whose first four
# bytes are not this interpreter's magic takes the same skip path as a hash-based one.
_PYC_HEADER = 12
_PYC_MAGIC = slice(0, 4)
_PYC_FLAGS = slice(4, 8)
_PYC_TIMESTAMP = slice(8, 12)
_PYC_HASH_BASED = 0b1
# CPython's own mask on the source mtime before it writes the header (`importlib._bootstrap_
# external._code_to_timestamp_pyc`). Without it a source mtime past 2106 -- or a clock skewed
# there -- compares a 33-bit number against the 32 bits the header can hold and mismatches
# forever.
_PYC_MTIME_MASK = 0xFFFFFFFF
# The two bounds on the walk for `.pyc` files, past either of which it stops and reports that it
# could not tell. Named caps (CONTRIBUTING.md#named-caps), and the shipped file that changes with
# them is `hooks/hooks.json`: the `PostToolUse` `Bash` hook that runs this walk after a red test
# run has a 10 s timeout there, which the two together must stay well under. A hook that times
# out delivers nothing and never banks its once-key, so an unbounded walk over a large tree was
# paid again after every red run.
#
# The walk has two halves of very different cost, so each has its own count. Listing charges
# every directory entry under the code roots, not only the bytecode. Reading charges every `.pyc`
# the listing found, before its source is stat'ed and it is opened and read: tens of times a
# listed entry, and the entry cap alone does not bound it, since any number of `.pyc` files share
# one source (the name before the first dot) -- 200k of them under one `m.py` took 18 s with the
# entry cap alone. Measured on a laptop with a warm cache, over 499,990 `.pyc` files sharing one
# source, the worst tree for both halves: listing them took 0.26-0.46 s, and listing plus reading
# up to the read cap took 1.2-1.6 s at 10k reads, 1.6-3.0 s at 20k and 3.8-7.6 s at 50k. 20k is
# the largest of those under a third of the timeout, which leaves room for a slower disk, a cold
# cache and the `git status` the same hook runs; it is more bytecode, and 500k more entries, than
# a code root holds once virtual environments and dependency trees are outside it.
# `docs/cli.md`'s `test hygiene` section states both numbers.
BYTECODE_WALK_ENTRIES = 500_000
BYTECODE_READ_FILES = 20_000

# The two counts `report` returns, and the names `stayfixed test hygiene --json` prints them under.
STALE_KEY = "stale"  # .pyc files whose recorded source mtime no longer matches the source
ROOTS_KEY = "roots"  # how many code roots were scanned
STALE = (
    "{count} .pyc file(s) whose recorded source mtime no longer matches their source, under "
    "the configured code roots -- the "
    "interpreter may be importing a build that predates a fix on disk, which fails "
    "DETERMINISTICALLY in the shape of the defect the test pins. Delete the `__pycache__` "
    "directories under those roots, then re-run before attributing anything."
)
# The note for a walk that stopped at either cap: it names both, numbers of this module's, since
# the counts do not say which one stopped it, and neither stale bytecode nor its absence.
UNTOLD = (
    "the configured code roots hold more than {entries} directory entries or {files} .pyc files, "
    "so the walk for .pyc files stopped there and could not tell whether the interpreter imported "
    "a build older than its source. If the failure could be a stale build, delete the "
    "`__pycache__` directories under those roots and re-run before attributing anything."
)


def _recorded_source_mtime(cache: int, name: str) -> int | None:
    """The source mtime CPython recorded in the header of the `.pyc` called `name` in the open
    `__pycache__` `cache`, or `None` when there is not one.

    Five things produce `None` and they all mean the same thing to the caller -- skip this
    file: it is not a regular file, the header could not be read, it is short, it was written by
    another interpreter and this one will never open it (see `_PYC_MAGIC` above), or it is
    hash-based and therefore carries a hash fragment where an mtime would be (see
    `_PYC_HASH_BASED` above).

    Bytecode the interpreter wrote is a regular file. A `.pyc` that is a symlink or a named pipe
    was put there by whoever wrote the tree, and opening it reads what it names, or waits on a
    pipe's writer for good (a link to `/dev/stdin` hung a terminal). So it is read under its
    `__pycache__`, opened once for all its files (`fsops.read_bounded` with a directory
    descriptor), which refuses a symlink, returns at once from a pipe, and judges what it opened by
    its descriptor, which nothing can swap between the check and the read. The source is not held
    to this: the interpreter follows a symlinked source too.
    """
    try:
        header, _ = read_bounded(name, _PYC_HEADER, root=cache)
    except OSError:
        return None
    if len(header) < _PYC_HEADER:
        return None
    if header[_PYC_MAGIC] != importlib.util.MAGIC_NUMBER:
        return None
    if int(struct.unpack("<I", header[_PYC_FLAGS])[0]) & _PYC_HASH_BASED:
        return None
    return int(struct.unpack("<I", header[_PYC_TIMESTAMP])[0])


def _bytecode(roots: Iterable[Path]) -> list[tuple[Path, list[str]]] | None:
    """Every `__pycache__` directory under `roots` with the names in it that end in `.pyc`, or
    `None` when the walk visited more than `BYTECODE_WALK_ENTRIES` entries and stopped. The cap
    is one total across `roots`, since every root a configuration lists would otherwise multiply
    the hook's time.

    Each root is followed, and below it no symlinked directory is entered, a `__pycache__`
    included; hidden directories are walked, names compare case-sensitively, and only a
    `__pycache__`'s `.pyc` files are kept, the one place the interpreter imports them from for
    the sources beside it. That is what
    `Path.rglob("*.pyc")` did on 3.11 to 3.13, measured on each: this walk replaces it because
    rglob counts nothing it skips, so no bound could be put on what it visits. A directory that
    cannot be listed is passed over, as rglob passed over it.
    """
    found: list[tuple[Path, list[str]]] = []
    visited = 0
    for root in roots:
        pending = [root]
        while pending:
            directory = pending.pop()
            names: list[str] = []
            try:
                with os.scandir(directory) as entries:
                    for entry in entries:
                        visited += 1
                        if visited > BYTECODE_WALK_ENTRIES:
                            return None
                        if entry.is_dir(follow_symlinks=False):
                            pending.append(directory / entry.name)
                        elif entry.name.endswith(".pyc"):
                            names.append(entry.name)
            except OSError:
                continue
            if names and directory.name == "__pycache__":
                found.append((directory, names))
    return found


def _stale_bytecode(roots: Iterable[Path]) -> int | None:
    """How many `.pyc` files under `roots` record a source mtime their source no longer has, or
    `None` when the walk stopped at either cap -- `BYTECODE_WALK_ENTRIES` on the listing,
    `BYTECODE_READ_FILES` on the `.pyc` files it goes on to read: a count of what it reached
    before then would be no answer, in either direction."""
    walked = _bytecode(roots)
    if walked is None:
        return None
    stale = 0
    read = 0
    for cache, names in walked:
        # Each `__pycache__` is opened once for every file read in it. One that cannot be opened
        # has no file this walk can read, and its files still count towards the cap.
        try:
            directory: int | None = open_directory(cache)
        except OSError:
            directory = None
        try:
            for name in names:
                read += 1
                if read > BYTECODE_READ_FILES:
                    return None
                if directory is None:
                    continue
                source = cache.parent / (name.split(".")[0] + ".py")
                try:
                    if not source.is_file():
                        continue
                    recorded = _recorded_source_mtime(directory, name)
                    if recorded is None:
                        continue
                    if recorded != int(source.stat().st_mtime) & _PYC_MTIME_MASK:
                        stale += 1
                except OSError:
                    continue
        finally:
            if directory is not None:
                os.close(directory)
    return stale


class PythonHint:
    def recognises(self, argv: Sequence[str]) -> bool:
        """True when this simple command actually invokes pytest -- as its own program, or as a
        module the interpreter loads (`-m pytest`, adjacent or fused as `-mpytest`) -- never a
        substring test against text that merely names it.

        Requiring the `-m` shape's argv0 to itself look like a Python interpreter (`python`,
        `python3`, `python3.13`, ...) is cheap insurance: "pytest" is a short enough word that an
        unrelated program taking it as some other flag's value is not implausible.
        """
        if not argv:
            return False
        argv0 = Path(argv[0]).name
        if argv0 == _PYTEST:
            return True
        if not argv0.startswith(_PYTHON_ARGV0_PREFIX):
            return False
        if f"-m{_PYTEST}" in argv:
            return True
        return any(
            current == "-m" and following == _PYTEST for current, following in pairwise(argv)
        )

    def report(self, root: Path, config: Config) -> Mapping[str, int] | None:
        roots = contained_roots(root, config)
        stale = _stale_bytecode(roots)
        if stale is None:
            return None
        return {STALE_KEY: stale, ROOTS_KEY: len(roots)}

    def note(self, counts: Mapping[str, int] | None) -> str | None:
        if counts is None:
            return UNTOLD.format(entries=BYTECODE_WALK_ENTRIES, files=BYTECODE_READ_FILES)
        stale = counts.get(STALE_KEY, 0)
        if not stale:
            return None
        return STALE.format(count=stale)


HINT: RedRunHint = PythonHint()
