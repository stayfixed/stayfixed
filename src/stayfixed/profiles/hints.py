"""What a stack's profile says after that stack's test runner failed.

The core knows a red run and a dirty tree and nothing about any stack; a profile that has more to
say ships it as `HINT` in a `hygiene.py` beside its data. The test command that failed chooses
which hints speak, through `RedRunHint.recognises`, and `[stayfixed] profile` plays no part: a
repository in several languages runs several stacks' suites, and the stack whose runner failed is
the one whose advice applies.

`note` receives counts and nothing else: both callers, the hook's notice and `stayfixed test
hygiene`, read a report through `counts`, which keeps a key only when it is a count name
(`COUNT_NAME`: lower-case letters, digits and underscores, at most 32 characters) and its value
only when it is a plain integer, and drops the rest before anything reaches `note` or `--json`.
A key is text a hint chose, and one built from the tree it walked would otherwise carry that
tree's names out; the grammar admits no `/`, `.`, space or upper case, so no path, file name or
command text a repository authored can pass as a count's name. So the trust rule
(`CONTRIBUTING.md`, "Repository bytes are data") holds for every hint that renders from its
argument alone, which is the contract below; a hint that kept a string from `report` on itself
for `note` to print would break the contract, and nothing but review catches that.

The listing goes through `importlib.resources` over this package, never over a repository path,
so only a hint stayfixed itself ships is ever imported.
"""

from __future__ import annotations

import importlib
import re
from collections.abc import Mapping, Sequence
from importlib import resources
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from stayfixed.profiles import shipped

if TYPE_CHECKING:
    from stayfixed.config.schema import Config

HINT_FILE = "hygiene.py"
# What a count may be called: a lower-case word of letters, digits and underscores, which is a
# fixed name in a hint's code and never something read off the tree. The length is a named cap
# (CONTRIBUTING.md#named-caps): 32 characters is room for any count's name and too little for a
# sentence, and no shipped file changes with it (the Python profile's names are `stale` and
# `roots`).
COUNT_NAME = re.compile(r"[a-z][a-z0-9_]{0,31}")


class RedRunHint(Protocol):
    """A stack's advice after its test runner failed. A profile ships one as `HINT` in its
    `hygiene.py`; the profile's name is its directory's, never a second attribute."""

    def recognises(self, argv: Sequence[str]) -> bool:
        """Whether this simple command, already unwrapped of assignments and launchers, runs
        this stack's tests."""
        ...

    def report(self, root: Path, config: Config) -> Mapping[str, int]:
        """The one walk: counts of what could have falsified the run, under `root`, each under a
        name `COUNT_NAME` matches; `counts` drops anything else."""
        ...

    def note(self, counts: Mapping[str, int]) -> str | None:
        """One line for `counts`, or `None` when nothing in them is worth saying."""
        ...


def hint_modules() -> tuple[str, ...]:
    """The shipped profiles that carry a `hygiene.py`, by name."""
    package = resources.files(__package__)
    return tuple(name for name in shipped() if package.joinpath(name).joinpath(HINT_FILE).is_file())


def shipped_hints() -> tuple[tuple[str, RedRunHint], ...]:
    """(profile name, its `HINT`), in name order.

    A profile whose `hygiene.py` does not import, or defines no `HINT`, is left out, and only
    that profile goes quiet: raised from here, the failure would reach the hook's dispatcher
    ahead of every per-hint guard and cost the whole notice, the dirty-tree line included.
    `stayfixed test hygiene` does not list such a profile either. The guard is broad for the
    reason the per-hint guards in `stayfixed.guards.hygiene` are: a module's import runs its
    code, and any exception can come out of it.
    """
    found: list[tuple[str, RedRunHint]] = []
    for name in sorted(hint_modules()):
        hint = _hint(name)
        if hint is not None:
            found.append((name, hint))
    return tuple(found)


def _hint(name: str) -> RedRunHint | None:
    try:
        hint: RedRunHint = importlib.import_module(f"{__package__}.{name}.hygiene").HINT
    except Exception:
        return None
    return hint


def counts(hint: RedRunHint, root: Path, config: Config) -> dict[str, int]:
    """`hint`'s report under `root` as a fresh mapping of count names to plain integers.

    A key that is not a string matching `COUNT_NAME` is dropped, and so is a value that is not
    an `int`, or is a `bool`, which is an `int` to Python and is not a count (`red_exit` refuses
    it for the same reason). What `report` raises reaches the caller: the hook's notice catches
    it per hint, and `stayfixed test hygiene` reports it as an internal error.
    """
    return {
        key: value
        for key, value in hint.report(root, config).items()
        if isinstance(key, str)
        and COUNT_NAME.fullmatch(key)
        and isinstance(value, int)
        and not isinstance(value, bool)
    }
