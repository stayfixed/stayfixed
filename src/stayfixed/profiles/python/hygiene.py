"""Python's red-run hint: a failed pytest run may have imported bytecode older than its source.

Bytecode newer than its source's last recorded edit is one of the two environment faults that
produce a red run no baseline A/B can attribute, because both halves of the A/B run inside it:
the interpreter imports a build that predates a fix on disk -- deterministically, in the shape of
the very defect the test pins. It has cost real time: a high-severity ledger entry rejected as a
stale cache. The other fault, uncommitted work in the tree, belongs to no stack, and the core
names it (`stayfixed.guards.hygiene`).

Matching an actual pytest invocation, not the six letters "pytest" appearing anywhere in the
command text: the core has already split the command into simple commands and unwrapped each one
past a leading shell assignment (`FOO=1 pytest`) and its small, exact wrapper set (`env cmd`,
`uv run cmd`), so `recognises` reads one argv and anchors on its first word. Under-reporting an
unrecognised launcher is the safe direction for a warn-only note.

Nothing a repository authored leaves this module: `note` renders a fixed sentence from a count,
and a `ledger.code_roots` entry is walked and never printed.
"""

from __future__ import annotations

import importlib.util
import struct
from collections.abc import Iterable, Mapping, Sequence
from itertools import pairwise
from pathlib import Path
from typing import TYPE_CHECKING

from stayfixed.guards.api import contained_roots

if TYPE_CHECKING:
    from stayfixed.config.schema import Config

PYTEST = "pytest"
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


def _recorded_source_mtime(pyc: Path) -> int | None:
    """The source mtime CPython recorded in `pyc`'s header, or `None` when there is not one.

    Four things produce `None` and they all mean the same thing to the caller -- skip this
    file: the header could not be read, it is short, it was written by another interpreter and
    this one will never open it (see `_PYC_MAGIC` above), or it is hash-based and therefore
    carries a hash fragment where an mtime would be (see `_PYC_HASH_BASED` above).
    """
    try:
        with pyc.open("rb") as handle:
            header = handle.read(_PYC_HEADER)
    except OSError:
        return None
    if len(header) < _PYC_HEADER:
        return None
    if header[_PYC_MAGIC] != importlib.util.MAGIC_NUMBER:
        return None
    if int(struct.unpack("<I", header[_PYC_FLAGS])[0]) & _PYC_HASH_BASED:
        return None
    return int(struct.unpack("<I", header[_PYC_TIMESTAMP])[0])


def _stale_bytecode(roots: Iterable[Path]) -> int:
    stale = 0
    for directory in roots:
        for pyc in directory.rglob("*.pyc"):
            if pyc.parent.name != "__pycache__":
                continue
            source = pyc.parent.parent / (pyc.name.split(".")[0] + ".py")
            try:
                if not source.is_file():
                    continue
                recorded = _recorded_source_mtime(pyc)
                if recorded is None:
                    continue
                if recorded != int(source.stat().st_mtime) & _PYC_MTIME_MASK:
                    stale += 1
            except OSError:
                continue
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
        if argv0 == PYTEST:
            return True
        if not argv0.startswith(_PYTHON_ARGV0_PREFIX):
            return False
        if f"-m{PYTEST}" in argv:
            return True
        # `pairwise`, not `zip(argv, argv[1:])`: identical semantics, and ruff's RUF007 refuses
        # the `zip` form on this tree.
        return any(current == "-m" and following == PYTEST for current, following in pairwise(argv))

    def report(self, root: Path, config: Config) -> Mapping[str, int]:
        roots = contained_roots(root, config)
        return {STALE_KEY: _stale_bytecode(roots), ROOTS_KEY: len(roots)}

    def note(self, counts: Mapping[str, int]) -> str | None:
        stale = counts.get(STALE_KEY, 0)
        if not stale:
            return None
        return STALE.format(count=stale)


HINT = PythonHint()
