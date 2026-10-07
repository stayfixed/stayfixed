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

from stayfixed.overlay.layout import PLUGIN_MANIFEST
from stayfixed.overlay.naming import manifest
from stayfixed.semver import COMPONENT, VERSION, later, pre_release

# A floor is built from `semver`'s component, so a declared floor and a running version bound each
# component alike; `semver.COMPONENT` says why the bound is what it is.
_FLOOR = re.compile(rf"^>={COMPONENT}\.{COMPONENT}\.{COMPONENT}$")


def requires_of(root: Path) -> str | None:
    """The `stayfixed.requires` string an overlay's manifest declares, stripped.

    `None` when the manifest is absent, unreadable, or does not carry a non-empty string —
    every one of those is "nothing declared", and none of them is this reader's business to
    tell apart.
    """
    try:
        # `naming.manifest`, the one reader of an overlay's manifests: a regular file only, so a
        # FIFO there cannot block the SessionStart hook this is asked on.
        raw = manifest(root, PLUGIN_MANIFEST)
    except (OSError, ValueError):  # bytes that are not UTF-8 are a `ValueError` too
        return None
    head = raw.get("stayfixed")
    value = head.get("requires") if isinstance(head, dict) else None
    return value.strip() if isinstance(value, str) and value.strip() else None


def satisfies(spec: str, version: str) -> bool | None:
    """`True`/`False` for `>=X.Y.Z` against an `X.Y.Z[...]` version: met unless `semver.later`
    says the floor comes after the version.

    One order with `later`, so a pre-release of the floor (`1.0.0rc1` against `>=1.0.0`) does not
    meet it, as `later` orders the release after it. Where `later` declines to order the two —
    equal triples and a suffix it does not read as a pre-release — a suffix carrying a pre-release
    segment anywhere (`semver.pre_release`: `1.0.0rc1.post2`, `1.0.0.dev3+g1234abc`) does not meet
    it either, and for any other (`.post1`, `+local`) the integer tuples decide, which is the
    answer such a build always had.

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
    after = later(".".join(floor.groups()), version)
    if after is not None:
        return not after
    # `later` declines a compound suffix on the floor's own triple; one with a pre-release segment
    # in it still comes before the release.
    if pre_release(version):
        return False
    return tuple(int(part) for part in running.groups()) >= tuple(
        int(part) for part in floor.groups()
    )
