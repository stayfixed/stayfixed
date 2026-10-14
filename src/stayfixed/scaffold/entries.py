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
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any

from stayfixed.errors import Refusal
from stayfixed.jsonobject import json_object, json_text
from stayfixed.printed import clipped

ENTRY_MARKER = "# stayfixed:"
_MARKER = re.compile(r"#\s*stayfixed:([A-Za-z0-9][A-Za-z0-9._-]*)\s*$")
# What every refusal of a settings document calls it: the engine is handed text, never a path.
_DOCUMENT = "settings document"


class EntriesError(Refusal):
    """A settings document the engine cannot rewrite without guessing."""


class ParserLimitError(EntriesError):
    """A settings document that is valid JSON and passes a limit of this interpreter's parser.

    Its own kind, because it is not malformed: a harness whose parser has no such limit reads it,
    and may run the hooks in it. A reader that reports on such a file cannot say "it would not
    load anyway", which it may say of one that does not parse.
    """


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


def _past_parser(label: str) -> Callable[[str], ParserLimitError]:
    """The refusal for a settings document past a limit of the parser, named by `label`: a kind of
    its own, for the reason `ParserLimitError` gives."""
    return lambda clause: ParserLimitError(f"{label} {clause}")


def settings_object(
    document: str, label: str = _DOCUMENT, *, numbers: Callable[[str], object] = int
) -> dict[str, Any]:
    """The document as an object, with each integer literal handed to `numbers`, and empty text
    as an empty one. `label` names it in every refusal.

    Public because `attach` reads the settings file it merges into, and the overlay's files it
    merges from, by this rule: one reader, so a document the engine would refuse is one `attach`
    refuses too.
    """
    if not document.strip():
        return {}
    # A settings document may be one a clone committed, so valid JSON past the parser's reach is
    # refused rather than left to escape the callers that catch the refusal, and refused as a
    # limit and not as a shape: see `ParserLimitError`.
    return json_object(
        document,
        label,
        error=EntriesError,
        limit=_past_parser(label),
        numbers=numbers,
    )


def settings_text(raw: dict[str, Any], label: str = _DOCUMENT, *, sort_keys: bool = False) -> str:
    """A settings document `settings_object` read, as the indented text written back, or the
    refusal `settings_object` gives a document nested past the parser: see `jsonobject.json_text`
    for why one the parser read can still be too deep to write. Public for `attach`, which writes
    the settings file it merges into by this rule too."""
    return json_text(
        raw,
        label,
        error=EntriesError,
        limit=_past_parser(label),
        indent=2,
        sort_keys=sort_keys,
    )


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
    # The event through `printed.clipped`: it is a key of a document a clone can commit, and this
    # refusal reaches a terminal and a model.
    if not isinstance(groups, list):
        raise EntriesError(f"'hooks.{clipped(event)}' is not a list")
    for group in groups:
        if not isinstance(group, dict):
            raise EntriesError(
                f"'hooks.{clipped(event)}' holds an entry group that is not an object"
            )
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


def _read_entries(document: str) -> Iterator[tuple[str, dict[str, Any], dict[str, Any]]]:
    """Every hook entry in the document with its event and the group holding it, in document
    order, read as strictly as `apply_entries` reads it: a shape the merge would refuse is refused
    here too, so a reader reporting on a settings file never accounts for one the engine could not
    rewrite.

    Integers are read as their text: no entry's id, event or marker is a number, and one longer
    than the interpreter converts must not keep a reader from the entries beside it. A settings
    file is one a clone can commit, and the harness reads such a number.
    """
    raw = _entry_document(document)
    for event in _hooks_table(raw):
        for group in _groups(raw, event):
            for entry in _entries_of(group):
                yield event, group, entry


def _entry_document(document: str) -> dict[str, Any]:
    """The settings document as every walk for entries reads it: integers as their text, for the
    reason `_read_entries` gives."""
    return settings_object(document, numbers=str)


def owned_ids(document: str) -> dict[str, str]:
    """Every id stayfixed claims in this document, mapped to its event."""
    return {
        claimed: event
        for event, _, entry in _read_entries(document)
        if (claimed := _claimed(entry)) is not None
    }


@dataclass(frozen=True)
class Placed:
    """One hook entry where a harness reads it: its event, its group's matcher, its command, and
    the whole entry.

    Each decides what the entry does: the event is when the harness runs it and the matcher is for
    which tools, so one entry under another event or matcher is another hook; and every field of
    the entry besides its command says what the harness does with it -- an entry of `type`
    `http` posts the event's input to its `url` and ignores `command`, and `args`, `shell` or
    `async` change what runs, or when. That is why `doctor` compares a grant as a `Placed` and
    never as a command alone: a repository that hung a granted command somewhere it was not
    granted, or inside an entry that does something else, would otherwise be vouched for.
    `command` is kept beside the whole because the marker is read off it.

    `matcher` is `None` for a group with no matcher, and otherwise the matcher as JSON text, with
    each integer in it as its text, as `_read_entries` reads it: a string and anything else a
    clone may commit there are each one value, and a matcher that is absent stays apart from one
    that is empty or `*`, which a harness may read alike — this says where the entry *is*, and
    never guesses what a harness makes of it. `entry` is the entry as JSON text by the same rule,
    with its keys sorted, so the order a file spells them in changes nothing and any field it adds,
    drops or changes does. One difference the rule cannot see: an integer and the string of its
    digits read alike, so a `"timeout": "30"` equals a granted `30`. That is benign, because it
    vouches for no entry that runs anything the grant does not: the command, the `type` and every
    other field still have to match, and a timeout is how long, not what. Never printed: an event,
    a matcher and an entry are bytes a repository chose.
    """

    event: str
    matcher: str | None
    command: str
    entry: str


def _matcher(group: dict[str, Any]) -> str | None:
    """A group's matcher as `Placed` holds it."""
    if "matcher" not in group:
        return None
    return json.dumps(group["matcher"], sort_keys=True)


def placed_entries(document: str) -> list[Placed]:
    """Every hook entry in the document where it is, in document order, **one element per entry**
    — `doctor`'s provenance.

    One per entry and not one per readable command, and never keyed by id: the position in this
    list is what the report names, and two entries sharing one id are two entries. So an entry
    whose `command` is absent, or is neither a string nor an integer, still occupies its place and
    contributes `""`; an integer, which the walk reads as its text, contributes that text. Either
    is one `marker_id` reads as unmarked — which it certainly is. Refuses what `owned_ids`
    refuses, read by the same walk.
    """
    return [_placed(event, group, entry) for event, group, entry in _read_entries(document)]


def _whole(entry: dict[str, Any]) -> str:
    """An entry as `Placed.entry` holds it: JSON text with sorted keys, each integer as the walk
    read it. Refused as `settings_text` refuses a document, where the encoder cannot follow the
    entry or its text would pass the read cap: an entry the reader took meets neither, short of
    one holding tens of megabytes of text outside ASCII, which the encoder escapes."""
    return json_text(
        entry, _DOCUMENT, error=EntriesError, limit=_past_parser(_DOCUMENT), sort_keys=True
    )


def _placed(event: str, group: dict[str, Any], entry: dict[str, Any]) -> Placed:
    """One entry as `Placed` holds it: one place for every walk, so a grant read back through
    `placed_entries` and an entry `live_entries` reads are compared in the same terms."""
    command = entry.get("command")
    text = command if isinstance(command, str) else ""
    return Placed(event, _matcher(group), text, _whole(entry))


@dataclass(frozen=True)
class Walked:
    """What a walk for live hook entries read out of a settings document.

    `entries` holds each entry it read with its place, 1-based, among `places`: every element of
    every group's `hooks` list, read or skipped, in document order, so a reader names an entry
    where a person opening the file finds it. `partly` is whether it skipped a part that could
    hold a command; `hidden`, whether a command claiming the stayfixed marker sits in such a part.
    """

    entries: tuple[tuple[int, Placed], ...]
    places: int
    partly: bool
    hidden: bool


def _admitted(value: object, kind: type, skipped: list[object]) -> bool:
    """Whether `value` is the `kind` the walk reads at its place in the `hooks` section.

    The measured rule, stated once: a scalar where a list or an object belongs holds no command
    and is skipped, as Claude Code skipped it (`harnesses.LENIENT_SETTINGS` says what, where
    and when that was measured); a container of the wrong kind was not measured and may hold a
    command, so it is skipped and kept in `skipped`, for the reader to say so.
    """
    if isinstance(value, kind):
        return True
    if isinstance(value, dict | list):
        skipped.append(value)
    return False


def _claims_the_marker(skipped: list[object]) -> bool:
    """Whether any string anywhere inside `skipped` is a command claiming the stayfixed marker,
    asked without recursion: a skipped part may be nested as deep as the parser follows."""
    pending = list(skipped)
    while pending:
        node = pending.pop()
        if isinstance(node, str):
            if marker_id(node) is not None:
                return True
        elif isinstance(node, dict):
            pending.extend(node.values())
        elif isinstance(node, list):
            pending.extend(node)
    return False


def live_entries(document: str) -> Walked:
    """Every hook entry a harness runs out of the document, as `placed_entries` places it.

    `placed_entries` reads as strictly as `apply_entries` writes, because a merge must not rewrite
    a shape it cannot read; that is the wrong question for which entries are live. What is
    skipped is `_admitted`'s rule. One shape more is set aside without a measurement: an object
    where a group goes that carries a `command` or a `type`, as an entry does, and no `hooks` list
    -- a reader may run it as an entry, so it is kept with the skipped parts. A command claiming
    the stayfixed marker in any skipped part is `hidden`, which a reader judges as the
    conservative answer, not a measured one: whether a harness runs it is not known. Refuses what
    `placed_entries` refuses above the events -- a document that is not a JSON object, and a
    `hooks` that is not an object -- which was not measured either.
    """
    raw = _entry_document(document)
    found: list[tuple[int, Placed]] = []
    skipped: list[object] = []
    places = 0
    for event, groups in _hooks_table(raw).items():
        if not _admitted(groups, list, skipped):
            continue
        for group in groups:
            if not _admitted(group, dict, skipped):
                continue
            if "command" in group or "type" in group:
                skipped.append({key: value for key, value in group.items() if key != "hooks"})
            entries = group.get("hooks", [])
            if not _admitted(entries, list, skipped):
                continue
            for entry in entries:
                places += 1
                if _admitted(entry, dict, skipped):
                    found.append((places, _placed(event, group, entry)))
    return Walked(tuple(found), places, bool(skipped), _claims_the_marker(skipped))


def judged_entries(document: str, *, lenient: bool) -> Walked:
    """The hook entries a reader judges in a settings file, and what it skipped.

    `lenient` for a file a harness was measured running partly malformed (`harnesses.
    LENIENT_SETTINGS`): `live_entries`, past a leading byte-order mark. Otherwise the strict
    `placed_entries`, which refuses every shape the merge would, so it skips nothing. One
    spelling, for `doctor`'s `hook-entries` and `assess`'s `foreign-hooks`, so the two never
    give two answers about one file; and, strict, for `attach --check`'s reading of the settings
    file `attach` merges into, which must refuse what the merge refuses.
    """
    if lenient:
        return live_entries(document.removeprefix("\ufeff"))
    placed = placed_entries(document)
    return Walked(tuple(enumerate(placed, start=1)), len(placed), partly=False, hidden=False)


def wanted_placements(wanted: dict[str, list[dict[str, Any]]]) -> list[Placed]:
    """Where `apply_entries` puts each entry of `wanted`, as `placed_entries` reads it back.

    Read back through the document `apply_entries` would write and not off `wanted` itself,
    because what a grant is compared with is what the walk reads out of a settings file: an
    integer in a matcher or an entry, such as a `timeout`, is its text there, and a grant that kept
    it a number would never equal the entry it installed. Refuses what `placed_entries` refuses.
    """
    return placed_entries(json.dumps({"hooks": wanted}))


def owned(document: str) -> str:
    """A canonical rendering of only the entries stayfixed claims — what the manifest stamps."""
    raw = settings_object(document)
    claimed: dict[str, list[dict[str, Any]]] = {}
    for event in sorted(_hooks_table(raw)):
        for group in _groups(raw, event):
            mine = [entry for entry in _entries_of(group) if _claimed(entry) is not None]
            if mine:
                claimed.setdefault(event, []).append({**group, "hooks": mine})
    return settings_text(claimed, sort_keys=True)


def apply_entries(document: str, wanted: dict[str, list[dict[str, Any]]]) -> str:
    raw = settings_object(document)
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
    return settings_text(raw) + "\n"
