"""Bytecode for the stale-bytecode tests, written the way the interpreter writes it."""

from __future__ import annotations

import os
import py_compile
import sys
import time
from pathlib import Path


def compile_module(module: Path) -> Path:
    """Compile `module` to the `__pycache__` beside it, with a timestamp header.

    `py_compile.compile(..., cfile=None)` alone is NOT enough, and the mutation oracle is what
    proved it: the oracle runs pytest under `PYTHONPYCACHEPREFIX`, which sends every cached
    `.pyc` to a scratch tree instead of to a `__pycache__` next to the source — so `report`
    walked the code roots, found no bytecode at all, and both bytecode tests reported `stale
    == 0`. One of them then failed on a clean tree and the other SURVIVED its mutation, which
    is the "the run ran nothing" shape of a vacuous oracle exactly.

    `invalidation_mode` is pinned for the sibling reason: `py_compile` switches to a hash-based
    header when `SOURCE_DATE_EPOCH` is set in the environment, and a hash-based `.pyc` has no
    mtime at bytes 8-12 to compare. Only the destination and the mode are pinned here — the
    header bytes are still the ones the interpreter itself writes, which is the whole point of
    compiling rather than hand-assembling one.
    """
    cache = module.parent / "__pycache__" / f"{module.stem}.{sys.implementation.cache_tag}.pyc"
    py_compile.compile(
        str(module),
        cfile=str(cache),
        doraise=True,
        invalidation_mode=py_compile.PycInvalidationMode.TIMESTAMP,
    )
    return cache


def make_stale(*modules: Path) -> None:
    """Move each source past the mtime its bytecode recorded."""
    future = time.time() + 60
    for module in modules:
        os.utime(module, (future, future))
