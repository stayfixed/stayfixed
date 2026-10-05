"""What an overlay declares it needs, and whether a running stayfixed meets it.

The declaration is read in the one form the template ships, `>=X.Y.Z`, and no other: a caller
that wants a different comparison has a different question, and answering it here would grow
a parser nothing has asked for yet. `requires_of`'s return value is the normalised string a
caller may print — it is what the overlay itself declared, stripped, not a value this module
built out of parts.
"""

from __future__ import annotations

import re
from pathlib import Path

from stayfixed.jsonobject import json_object
from stayfixed.overlay.layout import PLUGIN_MANIFEST
from stayfixed.semver import COMPONENT, VERSION

# A floor is built from `semver`'s component, so a declared floor and a running version bound each
# component alike; `semver.COMPONENT` says why the bound is what it is.
_FLOOR = re.compile(rf"^>={COMPONENT}\.{COMPONENT}\.{COMPONENT}$")


def requires_of(root: Path) -> str | None:
    """The `stayfixed.requires` string an overlay's manifest declares, stripped.

    `None` when the manifest is absent, unreadable, or does not carry a non-empty string —
    every one of those is "nothing declared", and none of them is this reader's business to
    tell apart.
    """
    path = root / PLUGIN_MANIFEST
    try:
        raw = json_object(path.read_text(encoding="utf-8"), PLUGIN_MANIFEST, error=ValueError)
    except (OSError, ValueError):  # bytes that are not UTF-8 are a `ValueError` too
        return None
    head = raw.get("stayfixed")
    value = head.get("requires") if isinstance(head, dict) else None
    return value.strip() if isinstance(value, str) and value.strip() else None


def satisfies(spec: str, version: str) -> bool | None:
    """`True`/`False` for `>=X.Y.Z` against an `X.Y.Z[...]` version, compared as integer tuples.

    `None` for any other spec shape or a version this reader cannot parse — a caller that gets
    `None` back has an unreadable declaration, not a false one.

    **It answers, for every string.** `None` is the whole of "this reader cannot read it", and
    the two grammars, `_FLOOR` and `semver.VERSION`, are what make that true: every component
    they admit is an integer `int()` converts, so no input reaches this function's arithmetic
    that could raise out of it.
    Both callers rest on that — `doctor`'s row turns an exception into "this check could not
    run", and the session handler's backstop turns one into silence for the whole line — so a
    reader that raises for an input a repository or an owner can write is a reader that deletes
    the lines around it.
    """
    floor = _FLOOR.match(spec)
    running = VERSION.match(version)
    if floor is None or running is None:
        return None
    return tuple(int(part) for part in running.groups()) >= tuple(
        int(part) for part in floor.groups()
    )
