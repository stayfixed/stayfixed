"""Keyed entries inside a settings file a person and several tools share.

Keying on a marker inside the command string rather than on position is what lets `upgrade`
replace what stayfixed installed while a foreign entry beside it — another plugin's, or the
owner's own — survives untouched and stays visible to `doctor`.

Two rules make "foreign entries untouched" true rather than approximately true. A group that
mixes a marked entry with an unmarked one is **split**, not replaced: the unmarked half keeps
its matcher and its position. And what the manifest stamps is `owned(document)` — the marked
entries alone — never the whole file, so a user adding a `permissions` block beside the hooks
does not freeze stayfixed's own entries forever.

The second rule is why an *unmarked* entry arriving from a caller is a refusal and not a thing
to install: unmarked, it is by definition one of the foreign entries those two rules exist to
leave alone, so nothing downstream can tell stayfixed's own wiring from somebody else's ever
again. `unmarked()` is that check, and `mark()` is what a caller is supposed to have called.
"""

from __future__ import annotations

import json
import re
from typing import Any

from stayfixed.errors import Refusal

ENTRY_MARKER = "# stayfixed:"
_MARKER = re.compile(r"#\s*stayfixed:([A-Za-z0-9][A-Za-z0-9._-]*)\s*$")


class EntriesError(Refusal):
    """A settings document the engine cannot rewrite without guessing."""


def marker_id(command: str) -> str | None:
    match = _MARKER.search(command)
    return match.group(1) if match else None


def mark(command: str, entry_id: str) -> str:
    if marker_id(command) == entry_id:
        return command
    return f"{command}  {ENTRY_MARKER}{entry_id}"


def unmarked(wanted: dict[str, list[dict[str, Any]]]) -> list[str]:
    """Every command in a caller's `entries` that carries no `# stayfixed:<id>` marker.

    The marker is not decoration: it is the key this whole module is built on. `owned()`
    renders the marked entries alone, and the engine stamps that rendering — so entries with
    no marker make `owned()` answer `{}` on both sides of the comparison, the digests match,
    and the artifact is reported *unchanged* while the user's settings file was never written
    and the wiring was never installed.

    Reported as a list rather than a bool so the refusal can name the offending command. The
    shape is checked on the way past for the same reason the marker is: `apply_entries` writes
    `wanted` into the user's file verbatim, and nothing between a caller and that write looks at
    it — `_entries_of` validates the *document*, never the mapping coming in. An entry that is
    not an object, or whose command is not a string, cannot be keyed either, and `marker_id`
    raises on a non-string rather than answering about one.
    """
    found: list[str] = []
    for groups in wanted.values():
        for group in groups:
            for entry in group.get("hooks") or []:
                command = entry.get("command") if isinstance(entry, dict) else entry
                if not isinstance(command, str) or marker_id(command) is None:
                    found.append(str(command))
    return found


def _load(document: str) -> dict[str, Any]:
    if not document.strip():
        return {}
    try:
        raw = json.loads(document)
    except json.JSONDecodeError as exc:
        raise EntriesError(f"settings document is not valid JSON: {exc}") from exc
    except RecursionError:
        # Valid JSON nested past what the parser follows. A settings document may be one a clone
        # committed, so it is refused like any other shape this cannot read, and never left to
        # escape the callers that catch the refusal.
        raise EntriesError("settings document is nested deeper than this reader follows") from None
    if not isinstance(raw, dict):
        raise EntriesError("settings document is not a JSON object")
    return raw


def _hooks_table(raw: dict[str, Any]) -> dict[str, Any]:
    hooks = raw.get("hooks", {})
    if not isinstance(hooks, dict):
        raise EntriesError("'hooks' is not an object")
    return hooks


def _groups(raw: dict[str, Any], event: str) -> list[dict[str, Any]]:
    """The groups under one event, or a refusal — a shape this module cannot read is never
    filtered away. `apply_entries` writes the structure it built back over the user's file, so
    dropping a group it did not recognise deletes somebody else's hook and says nothing."""
    groups = _hooks_table(raw).get(event, [])
    if not isinstance(groups, list):
        raise EntriesError(f"'hooks.{event}' is not a list")
    for group in groups:
        if not isinstance(group, dict):
            raise EntriesError(f"'hooks.{event}' holds an entry group that is not an object")
    return groups


def _entries_of(group: dict[str, Any]) -> list[dict[str, Any]]:
    """One group's entries, or a refusal, for the reason `_groups` gives. Both the list and the
    entries inside it are checked: an entry filtered out of an otherwise well-formed group is
    deleted just as silently as a whole group is, and hides better."""
    entries = group.get("hooks", [])
    if not isinstance(entries, list):
        raise EntriesError("an entry group's 'hooks' is not a list")
    for entry in entries:
        if not isinstance(entry, dict):
            raise EntriesError("an entry group holds an entry that is not an object")
    return entries


def _claimed(entry: dict[str, Any]) -> str | None:
    command = entry.get("command")
    return marker_id(command) if isinstance(command, str) else None


def _without_marked(group: dict[str, Any]) -> dict[str, Any] | None:
    """The group with stayfixed's own entries removed, or `None` when nothing foreign is left."""
    kept = [entry for entry in _entries_of(group) if _claimed(entry) is None]
    if not kept:
        return None
    return {**group, "hooks": kept}


def owned_ids(document: str) -> dict[str, str]:
    """Every id stayfixed claims in this document, mapped to its event — `doctor`'s provenance."""
    raw = _load(document)
    return {
        claimed: event
        for event in _hooks_table(raw)
        for group in _groups(raw, event)
        for entry in _entries_of(group)
        if (claimed := _claimed(entry)) is not None
    }


def owned(document: str) -> str:
    """A canonical rendering of only the entries stayfixed claims — what the manifest stamps."""
    raw = _load(document)
    claimed: dict[str, list[dict[str, Any]]] = {}
    for event in sorted(_hooks_table(raw)):
        for group in _groups(raw, event):
            mine = [entry for entry in _entries_of(group) if _claimed(entry) is not None]
            if mine:
                claimed.setdefault(event, []).append({**group, "hooks": mine})
    return json.dumps(claimed, indent=2, sort_keys=True)


def apply_entries(document: str, wanted: dict[str, list[dict[str, Any]]]) -> str:
    raw = _load(document)
    hooks = dict(_hooks_table(raw))
    for event in sorted(set(hooks) | set(wanted)):
        foreign = [kept for group in _groups(raw, event) if (kept := _without_marked(group))]
        merged = foreign + list(wanted.get(event, []))
        if merged:
            hooks[event] = merged
        else:
            hooks.pop(event, None)
    if hooks:
        raw["hooks"] = hooks
    else:
        raw.pop("hooks", None)
    return json.dumps(raw, indent=2) + "\n"
