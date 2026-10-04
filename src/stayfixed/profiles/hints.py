"""What a stack's profile says after that stack's test runner failed.

The core knows a red run and a dirty tree and nothing about any stack; a profile that has more to
say ships it as `HINT` in a `hygiene.py` beside its data. The test command that failed chooses
which hints speak, through `RedRunHint.recognises`, and `[stayfixed] profile` plays no part: a
repository in several languages runs several stacks' suites, and the stack whose runner failed is
the one whose advice applies.

`note` receives counts and nothing else: the core passes every report through
`stayfixed.guards.hygiene.plain_counts`, which keeps string keys with plain integer values and
drops the rest, before it reaches `note` or `stayfixed test hygiene --json`. So no path, file
name or command text a repository authored reaches a hint's line through what the hint is
handed, and the trust rule (`CONTRIBUTING.md`, "Repository bytes are data") holds for every hint
that renders from its argument alone, which is the contract below; a hint that kept a string
from `report` on itself for `note` to print would break the contract, and nothing but review
catches that.

The listing goes through `importlib.resources` over this package, never over a repository path,
so only a hint stayfixed itself ships is ever imported.
"""

from __future__ import annotations

import importlib
from collections.abc import Mapping, Sequence
from importlib import resources
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from stayfixed.profiles import shipped

if TYPE_CHECKING:
    from stayfixed.config.schema import Config

HINT_FILE = "hygiene.py"


class RedRunHint(Protocol):
    """A stack's advice after its test runner failed. A profile ships one as `HINT` in its
    `hygiene.py`; the profile's name is its directory's, never a second attribute."""

    def recognises(self, argv: Sequence[str]) -> bool:
        """Whether this simple command, already unwrapped of assignments and launchers, runs
        this stack's tests."""
        ...

    def report(self, root: Path, config: Config) -> Mapping[str, int]:
        """The one walk: counts of what could have falsified the run, under `root`."""
        ...

    def note(self, counts: Mapping[str, int]) -> str | None:
        """One line for `counts`, or `None` when nothing in them is worth saying."""
        ...


def hint_modules() -> tuple[str, ...]:
    """The shipped profiles that carry a `hygiene.py`, by name."""
    package = resources.files(__package__)
    return tuple(name for name in shipped() if package.joinpath(name).joinpath(HINT_FILE).is_file())


def shipped_hints() -> tuple[tuple[str, RedRunHint], ...]:
    """(profile name, its `HINT`), in name order."""
    found: list[tuple[str, RedRunHint]] = []
    for name in sorted(hint_modules()):
        module = importlib.import_module(f"{__package__}.{name}.hygiene")
        found.append((name, module.HINT))
    return tuple(found)
