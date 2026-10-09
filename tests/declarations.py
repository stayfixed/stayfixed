"""The mutation oracle, loaded for the tests that read what `mutations/` declares.

The script is loaded by path, through `tests.scriptload.load`. Here rather than in each test that
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

from tests.scriptload import SCRIPTS, load

SCRIPT = SCRIPTS / "mutation_oracle.py"
# How a comment cites an entry (CONTRIBUTING.md, "Tests"): the set, then the entry's quoted name.
# Built in two pieces so that this line is not itself read as a citation of whatever follows it.
ANCHOR = "`mutations" + "/`'s"
# The name runs to the next double quote and may wrap: a line break, the next line's indentation
# and a comment's `#` read as one space, there and between the anchor and the name. After it,
# `, "…"`, `and "…"` or `or "…"` cite further names under the same anchor.
_GAP = r"[\s#]*"
_QUOTED = re.compile(_GAP + r'"(?P<name>[^"]*)"')
_FURTHER = re.compile(_GAP + r"(?:," + _GAP + r"(?:and|or)?|and|or)" + _GAP + r'"(?P<name>[^"]*)"')
# So does an arrow list, which says what each name's mutation does: `"a" -> x; "b" -> y`. What
# follows the arrow runs to a `;` or a `,`, an `and` or an `or` may come next, and then the next
# name. It is read only within the citation's own lines (`_one_passage`), so that a quote in the
# code below a comment is never taken for a name.
_ARROW = re.compile(
    _GAP + r'->(?P<said>[^;"]*?)[;,](?:' + _GAP + r"(?:and|or))?" + _GAP + r'"(?P<name>[^"]*)"'
)
_WRAP = re.compile(r"\s*\n\s*(?:#\s*)?")
# The set's name followed by a quoted name through a comma or a colon rather than `'s` is a
# citation `cited_names` never reads, so nothing would notice that name going stale. Built in
# pieces for the reason `ANCHOR` is.
_UNREAD = re.compile("`mutations" + r'/`[,:]?[\s#(]*"')


@functools.cache
def _oracle() -> ModuleType:
    return load(SCRIPT, "mutation_oracle_declarations")


def declared() -> list[Any]:
    """Every entry `mutations/` declares, in the oracle's order, as its `Mutation`s."""
    return list(_oracle().declared())


def relative(path: Path) -> str:
    """An entry's `file` as the declaration spells it: from the repository root, with `/`."""
    return path.relative_to(SCRIPT.parents[1]).as_posix()


def _one_passage(said: str, comment: bool) -> bool:
    """Whether what an arrow says stays within the citation's lines: no blank line, and, for a
    citation in a comment, no line that is not a comment."""
    return all(
        line.strip() and (not comment or line.lstrip().startswith("#"))
        for line in said.split("\n")[1:]
    )


def cited_names(text: str) -> list[str]:
    """Every entry name `text` cites, each with its line wraps read as single spaces."""
    names: list[str] = []
    at = text.find(ANCHOR)
    while at != -1:
        comment = text[text.rfind("\n", 0, at) + 1 : at].lstrip().startswith("#")
        quoted = _QUOTED.match(text, at + len(ANCHOR))
        while quoted is not None:
            names.append(" ".join(_WRAP.sub(" ", quoted.group("name")).split()))
            further = _FURTHER.match(text, quoted.end())
            if further is None:
                further = _ARROW.match(text, quoted.end())
                if further is not None and not _one_passage(further.group("said"), comment):
                    further = None
            quoted = further
        at = text.find(ANCHOR, at + len(ANCHOR))
    return names


def unread_citations(text: str) -> list[int]:
    """The line of each citation in `text` spelled some other way than `ANCHOR`, which
    `cited_names` does not read."""
    return [text.count("\n", 0, found.start()) + 1 for found in _UNREAD.finditer(text)]
