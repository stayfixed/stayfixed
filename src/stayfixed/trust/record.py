"""The machine's one trust record: `trust.json`, beside the machine file, as a versioned document.

A version-1 record is a JSON object with two keys, `version` and `approvals`, and each approval
names its kind, its subject, the digest approved and when it was recorded:

    {"approvals": [{"approved_at": "2026-10-16T09:30:00+00:00", "digest": "…",
                    "kind": "memory", "subject": "/home/me/project/.stayfixed/memory"}],
     "version": 1}

`0.3.0` kept a flat object instead, a store's resolved path to its digest, and every such file is
read here as approvals of kind `memory`, one per entry, so an upgrade keeps them; the first write
upgrades the file in place. `0.3.0`'s own reader keeps only the entries whose value is a string,
and a version-1 record has none, so a `0.3.0` that meets one reads no approval and asks again,
never an approval it would misread.

**Absent and unreadable are not the same answer.** An absent file is the ordinary state of a fresh
machine and holds no approval. A file that is there and is neither a version-1 record nor `0.3.0`'s
flat map — not JSON, not UTF-8, a later version, an approval missing a field — refuses with
`UnreadableTrust`, and nothing here overwrites it: it holds every project's approval on the
machine, and reading it as empty would let the next write persist the loss.

Every write replaces the whole file through `fsops` in one atomic step. No lock is taken: two
writers at once each replace the file whole, the last one wins, and neither leaves it torn. The
one writer that is not a person's, `refresh`, re-reads the record just before its write and writes
only while it still holds the digest its caller read, so a revoke made before that final re-read
is never undone; one that lands between the re-read and the write is the window no lock closes,
and the last writer wins it.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass, fields, replace
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from stayfixed import fsops
from stayfixed.config.machine import machine_config_path
from stayfixed.errors import Failure, Refusal
from stayfixed.jsonobject import json_object
from stayfixed.trust.boundary import RUN_OUTSIDE, SANDBOX_REFUSED, sandbox_refused

RECORD = "trust.json"
VERSION = 1
NO_HOME = (
    "HOME names no home directory, so there is no trust record to write; pass --machine PATH to "
    "keep one beside that file, which no hook reads"
)
# The close of every refusal of a record that is there and cannot be read.
_HOLDS = "it holds every project's approval on this machine, so nothing here will overwrite it"
_KEPT = f"{_HOLDS} — repair or delete it"
# A record a later stayfixed wrote is met after a downgrade, where deleting it would destroy the
# later release's approvals: the remedy is the later release.
LATER_VERSION = (
    "{path} is a trust record of a version this stayfixed does not read, which a later stayfixed "
    f"wrote; {_HOLDS} — update stayfixed to read it"
)
NOT_A_RECORD = "{path} is neither a trust record nor the flat map 0.3.0 wrote; " + _KEPT
# A write to the record that was refused the way an agent's sandbox refuses one (`boundary`'s
# docstring): run from an agent's shell, nothing it asks of the record can be written.
SANDBOXED = SANDBOX_REFUSED.format(
    outcome="the trust record was not written",
    directory="its directory",
    remedy=RUN_OUTSIDE.format(command="this command"),
)


@dataclass(frozen=True)
class Approval:
    """One approval: what was approved (`kind`, `subject`), the digest it held, and when it was
    recorded, in ISO 8601 (empty for one `0.3.0` recorded, which kept no time)."""

    kind: str
    subject: str
    digest: str
    approved_at: str


class State(StrEnum):
    """What the record says of one subject, against the digest it has now."""

    APPROVED = "approved"
    # Recorded with another digest: approved once, and what was approved has changed since.
    LAPSED = "lapsed"
    MISSING = "missing"


class SandboxedWrite(Refusal):
    """A write to the record refused as an agent's sandbox refuses one: `SANDBOXED`, exit 2, and
    nothing written, since the write is one atomic replacement."""


class UnreadableTrust(Refusal):
    """`trust.json` exists and is neither a version-1 record nor `0.3.0`'s flat map.

    A refusal and not a `Failure`: every caller of `state` reads anything but `APPROVED` as "not
    approved", and a broken file must never be answered that way twice — once by reporting the
    subject unapproved, and again by the next write overwriting what could not be read. Exit 2 is
    the code a caller may not read as permission.
    """


_FIELDS = frozenset(field.name for field in fields(Approval))


def record_path(machine: Path | None) -> Path | None:
    """`trust.json` beside the machine file `machine`, or beside the one `config.machine` names.

    That one is under `HOME`, never `XDG_CONFIG_HOME`: a file the clone commits can set it for
    direnv, mise or a devcontainer, and a record it chose would be one the repository wrote.
    `None` for a machine with no home: it holds no record, so nothing is approved, and a write
    refuses to invent a place for one.
    """
    base = machine_config_path() if machine is None else machine
    return None if base is None else base.parent / RECORD


def recorded(machine: Path | None) -> dict[tuple[str, str], Approval]:
    """Every approval on this machine by `(kind, subject)`, or `UnreadableTrust` when the record
    is there and cannot be read."""
    path = record_path(machine)
    if path is None or not fsops.is_file(path):
        return {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise UnreadableTrust(
            f"{path} cannot be read ({fsops.said(exc)}); refusing to answer about trust or to "
            "overwrite it"
        ) from exc
    except UnicodeDecodeError:
        raise UnreadableTrust(f"{path} is not UTF-8 text; {_KEPT}") from None
    # Through `jsonobject`, whose parser-limit arms a bare `json.loads` lacks: a record nested
    # past the parser or holding an integer longer than it converts is valid JSON that
    # `json.loads` meets with no `JSONDecodeError`. Each sentence is this record's refusal.
    raw = json_object(text, str(path), error=lambda reason: UnreadableTrust(f"{reason}; {_KEPT}"))
    if "version" not in raw and "approvals" not in raw:
        # `0.3.0`'s flat map. A store's key is a resolved absolute path, so no store is named
        # `version` or `approvals`, and an object holding either is a record, read whole or
        # refused: read as a flat map, `{"approvals": [...]}` was no approval, and the next write
        # erased it. A value that is not a string is one entry `0.3.0` could not interpret
        # either, and dropping it costs that store a re-approval, as it did there.
        return {
            ("memory", subject): Approval("memory", subject, digest, "")
            for subject, digest in raw.items()
            if isinstance(digest, str)
        }
    return _approvals(raw, path)


def _approvals(raw: dict[str, Any], path: Path) -> dict[tuple[str, str], Approval]:
    """A version-1 record's approvals, or the refusal for one this stayfixed cannot read whole."""
    version = raw.get("version")
    # Only an integer above this one is a later stayfixed's: `0`, `-1`, `"1"` or `true` is no
    # version any release writes, and sending its reader to upgrade would send them nowhere.
    if type(version) is int and version > VERSION:
        raise UnreadableTrust(LATER_VERSION.format(path=path))
    entries = raw.get("approvals")
    if type(version) is not int or version != VERSION:
        raise UnreadableTrust(NOT_A_RECORD.format(path=path))
    if set(raw) != {"version", "approvals"} or not isinstance(entries, list):
        raise UnreadableTrust(NOT_A_RECORD.format(path=path))
    found: dict[tuple[str, str], Approval] = {}
    for entry in entries:
        if (
            not isinstance(entry, dict)
            or set(entry) != _FIELDS
            or not all(isinstance(value, str) for value in entry.values())
        ):
            raise UnreadableTrust(NOT_A_RECORD.format(path=path))
        approval = Approval(**entry)
        key = (approval.kind, approval.subject)
        if key in found:
            raise UnreadableTrust(NOT_A_RECORD.format(path=path))
        found[key] = approval
    return found


def state(machine: Path | None, kind: str, subject: str, current: str) -> State:
    """Whether `subject` of `kind` is approved at the digest `current`."""
    return state_in(recorded(machine), kind, subject, current)


def state_in(
    approvals: Mapping[tuple[str, str], Approval], kind: str, subject: str, current: str
) -> State:
    """`state`'s answer out of `approvals`, the record read once by a caller that asks of several
    subjects (`trust list`)."""
    approval = approvals.get((kind, subject))
    if approval is None:
        return State.MISSING
    return State.APPROVED if approval.digest == current else State.LAPSED


def approve_all(
    machine: Path | None, kind: str, digests: Mapping[str, str], *, now: datetime
) -> dict[str, State]:
    """Record every subject of `kind` in `digests` as approved at its digest, replacing any
    approval each had, in one write of the record; and answer what the record said of each before.

    One write, so a kind with several subjects is approved whole or not at all: a write that fails
    leaves the record as it was. Nothing is written for no subject."""
    approvals = recorded(machine)
    was = {
        subject: state_in(approvals, kind, subject, digest) for subject, digest in digests.items()
    }
    if not digests:
        return was
    when = now.isoformat(timespec="seconds")
    for subject, digest in digests.items():
        approvals[(kind, subject)] = Approval(kind, subject, digest, when)
    _write(machine, approvals)
    return was


def refresh(machine: Path | None, kind: str, subject: str, *, expected: str, digest: str) -> bool:
    """Move the approval of `subject` of `kind` from the digest `expected` to `digest`, keeping
    when the person gave it; `False`, and nothing written, when the record read here no longer
    holds `expected` for it.

    For a write stayfixed itself authored, whose caller read the approval before it wrote: a
    revoke, or a new approval, recorded since then is the person's, and a refresh that wrote
    anyway would undo it. The record is re-read here, just before the write, so a revoke made
    before that re-read is kept; one made between the re-read and the write is not, since no lock
    is taken (the module docstring says so).

    A move to the digest the record already holds writes nothing and answers `True`: the approval
    holds as it is. Rewritten, an index that changed nothing rewrote the record on every run, and
    from an agent's sandboxed shell, where the write is refused, it said the approval no longer
    matched the files while `trust list` said approved.
    """
    approvals = recorded(machine)
    held = approvals.get((kind, subject))
    if held is None or held.digest != expected:
        return False
    if digest != held.digest:
        approvals[(kind, subject)] = replace(held, digest=digest)
        _write(machine, approvals)
    return True


def revoke_all(machine: Path | None, kind: str, subjects: Iterable[str]) -> list[str]:
    """Remove the approval of every subject of `kind` in `subjects` that has one, in one write of
    the record, and answer those subjects in the order given; nothing is written when none had one.

    One write, as `approve_all`'s, so a kind with several subjects is withdrawn whole or not at
    all, and the record is not replaced once per subject."""
    approvals = recorded(machine)
    revoked = [subject for subject in subjects if approvals.pop((kind, subject), None) is not None]
    if revoked:
        _write(machine, approvals)
    return revoked


def _write(machine: Path | None, approvals: dict[tuple[str, str], Approval]) -> None:
    """Replace the record with `approvals` as version 1, and fail naming its directory when that
    cannot be written.

    There is no second place to put it that a hook would read, so the failure says which
    directory it was rather than ending as an internal error about a temporary file.
    """
    path = record_path(machine)
    if path is None:
        raise Failure(NO_HOME)
    document = {
        "version": VERSION,
        "approvals": [asdict(approvals[key]) for key in sorted(approvals)],
    }
    try:
        fsops.write_atomically(path, json.dumps(document, indent=2, sort_keys=True) + "\n")
    except OSError as exc:
        if sandbox_refused(exc):
            raise SandboxedWrite(SANDBOXED) from None
        where = (
            "it is under HOME, which is the only place a hook reads a trust record"
            if machine is None
            else "it is beside the machine configuration file --machine names"
        )
        raise Failure(
            f"{path.parent} cannot be written ({fsops.said(exc)}), so the trust record cannot be "
            f"kept there; {where}"
        ) from None
