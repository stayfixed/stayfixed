"""The kinds of approval `stayfixed trust` asks about, each contributed by the area that owns it.

A kind is what a person approves — a store of notes committed to a repository, for `memory` — and
the area that knows how to find and hash it says so in its own `approvals.py`, as `KINDS`, a tuple
of `ApprovalKind`. The core reads every one through discovery (`areas.area_modules`) and imports
none by name, so a kind a delivery area owns reaches the core the way that area's commands do.

`interactive` is the terminal check the approve path asks first. It is a speed bump and no
guarantee: an agent's shell tool runs a command with no terminal on standard input (measured on
Claude Code 2.1.296, in a terminal session and on the desktop app's Code tab alike), so a bare call
from it is refused, and an agent able to open a pseudo-terminal passes it. Against such an agent
the harness's own write restriction is the boundary (`SECURITY.md`).
"""

from __future__ import annotations

import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

from stayfixed.areas import area_modules
from stayfixed.errors import Failure

# Two areas contributing a kind of one name: stayfixed's own code disagreeing with itself, and the
# names are stayfixed's, so they print.
DUPLICATE_KIND = "two areas contribute an approval kind named {name}: {first} and {second}"


@dataclass(frozen=True)
class Subject:
    """One thing of a kind a person approves: its key in the record, what a person reads for it,
    and its digest now. `label` is printed through `printed.printable`; `key` goes to `--json`."""

    key: str
    label: str
    digest: str


@dataclass(frozen=True)
class KindContext:
    """What a kind describes its subjects from: the checkout, the machine file, and the kind's own
    flags as they were given (`--store` for `memory`), by flag."""

    root: Path
    machine: Path | None
    options: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ApprovalKind:
    """A kind: its name, how it finds this checkout's subjects (one checkout may have several), and
    the flags of its own `trust approve` takes for it."""

    name: str
    describe: Callable[[KindContext], tuple[Subject, ...]]
    flags: tuple[str, ...] = ()


def kinds() -> dict[str, ApprovalKind]:
    """Every kind the areas contribute, by name, in area-name order; two of one name refuse."""
    found: dict[str, ApprovalKind] = {}
    owner: dict[str, str] = {}
    for module in area_modules("approvals"):
        for kind in module.KINDS:
            if kind.name in found:
                raise Failure(
                    DUPLICATE_KIND.format(
                        name=kind.name, first=owner[kind.name], second=module.__name__
                    )
                )
            found[kind.name] = kind
            owner[kind.name] = module.__name__
    return found


def interactive() -> bool:
    """Whether standard input is a terminal: the seam the approve path asks, and tests replace."""
    return sys.stdin is not None and sys.stdin.isatty()
