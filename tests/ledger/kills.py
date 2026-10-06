"""A process killed between two of a command's writes, as the ledger's write tests simulate it.

Shared by the tests of `renumber` itself and of `bugs check` over the tree a killed `renumber`
leaves, so the two read the same kill.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest


class Killed(BaseException):
    """A kill between two writes: a `BaseException`, so no `except Exception` on the way out can
    swallow it, as none swallows the `KeyboardInterrupt` of a real interrupt."""


@contextmanager
def killed_at(monkeypatch: pytest.MonkeyPatch, write: int) -> Iterator[list[str]]:
    """`fsops.write_within` raising `Killed` in place of its `write`-th call while the block runs,
    and as it was after; yields the targets written before the kill, in order."""
    from stayfixed import fsops

    real = fsops.write_within
    writes: list[str] = []

    def counted(within: Path, target: str, text: str, **kwargs: Any) -> None:
        if len(writes) + 1 == write:
            raise Killed(target)
        writes.append(target)
        real(within, target, text, **kwargs)

    with monkeypatch.context() as patched:
        patched.setattr(fsops, "write_within", counted)
        yield writes
