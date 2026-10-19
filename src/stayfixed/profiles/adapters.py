"""Every runner adapter this stayfixed ships, found by discovery and never by name, beside the
red-run hints' discovery (`hints.py`): both walk the stacks this package ships.

A stack ships its adapters as `ADAPTERS` in `profiles/<stack>/adapters.py`, with a profile beside
them or without one, and `stayfixed.profiles.stack_directories` is the one walk that finds them,
as it finds the profiles and their red-run hints: so the core names no stack, and adding a
runner is adding its stack's file.
"""

from __future__ import annotations

from importlib.resources.abc import Traversable

from stayfixed.profiles import stack_directories, stack_module
from stayfixed.profiles.runners import RunnerAdapter

ADAPTER_FILE = "adapters.py"


def shipped_adapters(*, source: Traversable | None = None) -> tuple[RunnerAdapter, ...]:
    """Every stack's `ADAPTERS`, the stacks in name order and each tuple in its own order.
    `source` lists another tree in this package's place, for a test; the modules are imported by
    this package's names all the same.

    A module that does not import, or that holds no `ADAPTERS`, raises: it is a defect in
    stayfixed, and a runner skipped for it would be a command `prove` silently cannot count.
    """
    found: list[RunnerAdapter] = []
    for name in stack_directories(ADAPTER_FILE, source=source):
        found.extend(stack_module(name, ADAPTER_FILE.removesuffix(".py")).ADAPTERS)
    return tuple(found)
