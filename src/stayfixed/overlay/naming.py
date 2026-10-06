"""What an overlay's manifests are called, how `overlay init` names them after an owner, and how
that owner is read back.

One module, so the three places that need the rule — `identity` asking whether a tree is an
overlay, `create.init_instance` renaming the manifests, and `upgrade` refreshing them — read it
from one table rather than each keeping an ordered copy. And one reader of the manifests
themselves, `manifest`, for the probe, the owner and the version floor `requires` reads. A leaf:
it imports no command module, so `upgrade` reaches the rename without importing `create`, the
module that runs `gh`.

`NAMED` is the table. Each row is a manifest, the name the shipped template gives it, the key
its account goes under (a marketplace has to name an `owner` for `claude plugin validate` to
accept it, and a plugin manifest an `author` for it to stop warning), and whether
`identity.overlay_fault` asks it: the two `.claude-plugin/` manifests are what makes a tree an
overlay, and the Codex one is absent from an overlay generated before the Codex half shipped.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING, Any

from stayfixed.config.schema import PROJECT_NAME
from stayfixed.errors import Failure
from stayfixed.fsops import read_regular_text
from stayfixed.jsonobject import json_object, json_text
from stayfixed.overlay.layout import CODEX_PLUGIN_MANIFEST, MARKETPLACE_MANIFEST, PLUGIN_MANIFEST

if TYPE_CHECKING:
    from stayfixed.scaffold import Template

# One path segment: `config.schema.PROJECT_NAME`, the one name grammar. An owner name becomes a
# directory, half a remote path, a marketplace selector and the suffix on both manifest names, so
# it is checked once rather than at each of those; the leading class is what keeps a value
# shaped like an option (`-flag`) out of an option's position in an argv. It lives with the names
# because the suffix grammar and the manifest-name grammar are the same grammar.
SEGMENT = PROJECT_NAME
# What the shipped template calls itself, and what `init_instance` suffixes.
OVERLAY_PLUGIN = "stayfixed-overlay"
OVERLAY_MARKETPLACE = "stayfixed-overlay-marketplace"
# What the template carries where an account goes, and what `init_instance` replaces with the
# owner's. Neither key can name the owner before there is an owner, so the shipped file holds this
# neutral stand-in. `templates/overlay/` carries the same string, and `tests/overlay/
# test_create.py`'s `test_init_names_the_owner_and_the_author_the_harness_asks_for` renders the
# template and fails when the two drift apart.
PLACEHOLDER_ACCOUNT = "your-account"


@dataclass(frozen=True)
class Named:
    path: str
    name: str
    account_key: str
    probed: bool


# The three manifests `init_instance` names after the owner, in the order it writes them. The
# Codex one was left out of the first draft, so the collision the suffix exists to prevent still
# happened on Codex: two owners' overlays under one Codex configuration were one plugin fighting
# itself.
NAMED = (
    Named(PLUGIN_MANIFEST, OVERLAY_PLUGIN, "author", probed=True),
    Named(MARKETPLACE_MANIFEST, OVERLAY_MARKETPLACE, "owner", probed=True),
    Named(CODEX_PLUGIN_MANIFEST, OVERLAY_PLUGIN, "author", probed=False),
)
MANIFESTS = tuple(row.path for row in NAMED)
_ROW = {row.path: row for row in NAMED}


def owner_in(value: object, expected: str) -> str | None:
    """The `<owner>` in a manifest name `expected-<owner>`, or `None` for any other value.

    A marketplace is matched against its own name, because `stayfixed-overlay-marketplace-<owner>`
    also starts with the plugin's `stayfixed-overlay-`; that is why every caller passes the row's
    own `name`.
    """
    if not isinstance(value, str):
        return None
    suffix = value.removeprefix(f"{expected}-")
    return suffix if suffix != value and SEGMENT.match(suffix) else None


def claims(value: object, expected: str) -> bool:
    """Whether a manifest's `name` is `expected`, or `expected-<owner>` after `overlay init`."""
    return value == expected or owner_in(value, expected) is not None


class NotAnObject(ValueError):
    """A manifest that parses as JSON and is not an object, so it names nothing. A `ValueError`, so
    a reader with no sentence of its own for it reads it as any manifest it cannot read."""


def manifest(root: Path, relative: str) -> dict[str, Any]:
    """The overlay manifest at `root/relative` as a JSON object: the one reader of an overlay's
    manifests, for `requires_of`, `owner_of` and `identity.overlay_fault`.

    Read through `fsops.read_regular_text`: a regular file only, followed through a link, and to
    the read cap. Two of the three read it with a bare `read_text`, so a FIFO at
    `.claude-plugin/plugin.json` blocked them for good, and `requires_of` is on the SessionStart
    hook path. Parsed through `jsonobject`, the one reader of a JSON object, so a manifest nested
    past the parser or holding an integer longer than it converts is one this cannot read.

    Raises `OSError` for one that cannot be read -- absent, not a regular file, past the cap --
    and `ValueError` for one that is not UTF-8 or not JSON, past the parser included, or
    `NotAnObject` for JSON that is not an object. Each caller says what those mean to it.
    """
    text = read_regular_text(root / relative)
    return json_object(text, relative, error=ValueError, shape=NotAnObject)


def owner_of(root: Path) -> str | None:
    """The account `overlay init` named this overlay after, or `None` where it named nobody.

    Read from the manifests, in `NAMED`'s order, and from the first that carries a suffix: an
    `init` that could not write one of them still named the others. Nothing read here is quoted
    anywhere; it only decides a rename, and `owner_in` admits one path segment and nothing else.
    """
    for row in NAMED:
        try:
            # Through `manifest`: one that cannot be read, is not an object, or is past the parser
            # or its depth bound is one this cannot read, and the next is asked.
            document = manifest(root, row.path)
        except (OSError, ValueError):
            continue
        name = document.get("name")
        if (owner := owner_in(name, row.name)) is not None:
            return owner
    return None


def _suffixed(value: object, suffix: str) -> str | None:
    """The renamed value, or `None` when it is already suffixed or not a name at all."""
    if not isinstance(value, str) or not value or value.endswith(f"-{suffix}"):
        return None
    return f"{value}-{suffix}"


def renamed(text: str, relative: str, suffix: str) -> str | None:
    """The manifest named after the owner, or `None` when it already named them.

    The text and not a boolean, because `init_instance` re-stamps the scaffold ledger with exactly
    what goes to disk — reading the file back to hash it would hash whatever is there then.
    Nothing is written here: every manifest is decided before any is written.
    """
    # Through `json_object`, whose sentences for a manifest that is not JSON or not an object are
    # the two this used to say, and which also answers valid JSON past the parser's reach: a bare
    # `json.loads` let `RecursionError` and the long-integer `ValueError` end `overlay init`.
    document = json_object(text, relative, error=Failure)
    changed = False
    if (name := _suffixed(document.get("name"), suffix)) is not None:
        document["name"] = name
        changed = True
    if _named_for(document, _ROW[relative].account_key, suffix):
        changed = True
    # The marketplace's entries name the plugin they publish, so an entry left unsuffixed would
    # advertise a plugin whose manifest no longer answers to that name.
    entries = document.get("plugins")
    if isinstance(entries, list):
        for entry in entries:
            if isinstance(entry, dict) and (entry_name := _suffixed(entry.get("name"), suffix)):
                entry["name"] = entry_name
                changed = True
    if not changed:
        return None
    return json_text(document, relative, error=Failure, indent=2) + "\n"


def _named_for(document: dict[str, object], key: str, account: str) -> bool:
    """Put `account` under `document[key]["name"]` where nobody has put a name; whether it changed.

    "Where nobody has": the key is absent (an overlay generated from a template that predates it,
    which is exactly what an owner's own published copy can be), or its name is the template's
    `PLACEHOLDER_ACCOUNT`. A name the owner wrote, and any other field beside it (an email, a
    URL), stay: `init` is run more than once and by people who edited the file first, and an
    account name that overwrote a person's own would be a rewrite of something stayfixed does not
    own. A value of another shape (`"author": "a string"`) is left alone for the same reason.
    """
    current = document.get(key)
    if current is None:
        document[key] = {"name": account}
        return True
    if (
        isinstance(current, dict)
        and current.get("name", PLACEHOLDER_ACCOUNT) == PLACEHOLDER_ACCOUNT
    ):
        current["name"] = account
        return True
    return False


def named_after(shipped: list[Template], owner: str | None) -> list[Template]:
    """`shipped`, with each manifest rendered as `init_instance` names it after `owner`.

    What `overlay upgrade` plans with, so a refresh matches the bytes `init` re-stamped:
    rendered through `renamed`, the function `init` writes through, a manifest the template has
    not moved renders to what `init` left and reads as unchanged, and one it has moved is
    refreshed and stays named. The shipped tree itself stays owner-free, which is what
    `publish-template` copies. `owner` is `owner_of`'s answer; `None` gets the template as it
    ships.
    """
    if owner is None:
        return shipped
    return [
        replace(item, render=partial(_render_named, item.render, item.id, owner))
        if item.id in _ROW
        else item
        for item in shipped
    ]


def _render_named(render: Callable[[], str], relative: str, owner: str) -> str:
    body = render()
    return renamed(body, relative, owner) or body
