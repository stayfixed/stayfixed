"""The mutation oracle, loaded for the tests that read what `mutations/` declares.

The script is loaded by path, through `tests.script.load`. Here rather than in each test that
counts or walks the entries, so that every one of them reads the declarations the one way the
oracle does — `declared()`, over `group_files()` — and the directory's glob is spelled once, in the
script. `tests/scripts/test_mutation_oracle.py` loads fresh copies of `SCRIPT` for the tests that
redirect the script's paths; everything else asks `declared()` here. `cited_names` reads the
other half of the contract, a comment's citation of an entry by its name.
"""

from __future__ import annotations

import functools
import re
from pathlib import Path
from types import ModuleType
from typing import Any

from tests.script import SCRIPTS, load

SCRIPT = SCRIPTS / "mutation_oracle.py"
# How a comment cites an entry (CONTRIBUTING.md, "Tests"): the set, then the entry's quoted name.
# Built in two pieces so that this line is not itself read as a citation of whatever follows it.
ANCHOR = "`mutations/`" + "'s"
# The name runs to the next double quote and may wrap: a line break, the next line's indentation
# and a comment's `#` read as one space, there and between the anchor and the name. After it,
# `, "…"`, `and "…"` or `or "…"` cite further names under the same anchor.
_GAP = r"[\s#]*"
_QUOTED = re.compile(_GAP + r'"([^"]*)"')
_FURTHER = re.compile(_GAP + r"(?:," + _GAP + r"(?:and|or)?|and|or)" + _GAP + r'"([^"]*)"')
_WRAP = re.compile(r"\s*\n\s*(?:#\s*)?")


@functools.cache
def _oracle() -> ModuleType:
    return load(SCRIPT, "mutation_oracle_declarations")


def declared() -> list[Any]:
    """Every entry `mutations/` declares, in the oracle's order, as its `Mutation`s."""
    return list(_oracle().declared())


def relative(path: Path) -> str:
    """An entry's `file` as the declaration spells it: from the repository root, with `/`."""
    return path.relative_to(SCRIPT.parents[1]).as_posix()


def cited_names(text: str) -> list[str]:
    """Every entry name `text` cites, each with its line wraps read as single spaces."""
    names: list[str] = []
    at = text.find(ANCHOR)
    while at != -1:
        quoted = _QUOTED.match(text, at + len(ANCHOR))
        while quoted is not None:
            names.append(" ".join(_WRAP.sub(" ", quoted.group(1)).split()))
            quoted = _FURTHER.match(text, quoted.end())
        at = text.find(ANCHOR, at + len(ANCHOR))
    return names
