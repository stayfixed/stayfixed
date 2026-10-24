"""Whether a note counts as the owner's: promoted, at the bytes it holds now.

A note is reviewed when the machine's trust record (`trust.json`, beside the machine file) holds a
`reviewed` entry for the note's resolved path at the sha256 of the note's current bytes. `memory
promote` writes the entry, `trust list` lists it and `trust revoke reviewed --subject PATH`
withdraws it; the record kind is no registered approval kind, so nothing else asks about it.

**What it stops, and what it rests on.** Every writer of a note but the owner's own review: a clone
that commits a note ranked `startup: 1`, the harness's memory writer, an agent writing while it
works, and the owner's own edit after promoting. Each of them writes the note's bytes, and none
writes the record, which is outside every tree a repository or a store can carry, so each reaches a
session unreviewed: as data, labelled, and never as a standing rule. Against the agent in the
session, which can run `memory promote` from its shell, the record is a label and not a gate.

**Closed where it cannot answer.** A note that cannot be read, or a record that cannot be, is
unreviewed: nothing is lost, since an unreviewed note still reaches the session as data.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from stayfixed import fsops
from stayfixed.memory.notes import Note
from stayfixed.memory.store import Store
from stayfixed.trust.api import Approval, State, UnreadableTrust, approve_all, recorded, state_in

KIND = "reviewed"
REVIEWED: Literal["reviewed"] = "reviewed"
UNREVIEWED: Literal["unreviewed"] = "unreviewed"
Status = Literal["reviewed", "unreviewed"]
Record = Mapping[tuple[str, str], Approval]


def digest(note: Path) -> str:
    """The sha256 of the note's bytes, read as every note is, to the regular-file read cap."""
    return hashlib.sha256(fsops.read_regular_bytes(note)).hexdigest()


def subject(note: Path) -> str:
    """The path the record names a note by: resolved, so a note reached through a group link
    (`developer` in every composed store) is one note, promoted once."""
    return str(fsops.resolved(note))


def record(store: Store) -> Record:
    """The machine's trust record, read once for a caller asking of many notes, or nothing where
    it cannot be read."""
    try:
        return recorded(store.machine)
    except UnreadableTrust:
        return {}


def status(store: Store, note: Note, approvals: Record | None = None) -> Status:
    """`reviewed` iff the record holds the note's current digest for its path."""
    held = record(store) if approvals is None else approvals
    try:
        current, named = digest(note.path), subject(note.path)
    except OSError:
        return UNREVIEWED
    return REVIEWED if state_in(held, KIND, named, current) is State.APPROVED else UNREVIEWED


def unreviewed(store: Store, notes: Iterable[Note]) -> list[Note]:
    """The notes of `notes` the record does not hold at their current bytes, in their order."""
    held = record(store)
    return [note for note in notes if status(store, note, held) == UNREVIEWED]


def promote(store: Store, notes: Iterable[Note]) -> dict[Path, str]:
    """Record each note at its current digest in one write of the record, and answer each note's
    path and the digest recorded. A record that cannot be read refuses (`UnreadableTrust`) rather
    than being replaced."""
    found = {note.path: digest(note.path) for note in notes}
    approve_all(
        store.machine,
        KIND,
        {subject(path): value for path, value in found.items()},
        now=datetime.now(UTC),
    )
    return found
