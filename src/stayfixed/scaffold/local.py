"""Where artifacts kept out of git live, and the ledger of what stayfixed last wrote there.

An `[artifacts] local` artifact lives under `LOCAL_ARTIFACTS`, a directory the footprint's ignore
block keeps out of git, and `.stayfixed/manifest.json` never records it: the manifest is committed,
and a record would put a machine's local state into every clone. With no record, the one oracle
for "stayfixed's bytes" was what the running build renders. So once a release changed a template,
every unedited artifact kept out of git read as somebody's: `upgrade` skipped it and `uninstall`
refused over it. And a copy whose id had left `[artifacts] local` was never judged at all, so
`uninstall` refused over it for good, suggesting a `--force` that no planned action could reach.

`LocalDigests` is the record those runs lacked, kept where the artifacts are and never committed:
`LOCAL_DIGESTS`, under `LOCAL_ROOT` beside `LOCAL_ARTIFACTS` rather than inside it, so no
`[artifacts] local` target can land on it. The engine updates it in `apply` for every write and
removal of a file under `LOCAL_ARTIFACTS`, and `uninstall` removes it before the ignore block goes.

**It is read as untrusted, and it authorizes little.** The ignore block keeps it out of git, but a
clone can force-add any file, and a clone's checkout then carries it. So it is read bounded
(`MAX_BYTES`, `MAX_ENTRIES`), through the same `O_NOFOLLOW` walk writes use, shape-checked entry by
entry, and a fault anywhere makes the whole ledger absent: absence sends the engine back to the
render rule at each artifact's own place and loses sight of copies left at earlier places, both of
which only ever keep a file where it is, so it is never worth a refusal. Nothing in it is ever
printed. An entry is consulted only under the id of a template this build produced, only for a
file under `LOCAL_ARTIFACTS`, never for a place there another artifact is built to write (the
rule, and the forged entry it stops: `project.templates.Owners`), and only to overwrite or remove
that file while its current bytes digest to exactly what the entry records; a file there whose
bytes differ is left and named. That is the manifest's boundary: a committed record reaches only
bytes its committer already controls.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from stayfixed.errors import Refusal
from stayfixed.fsops import read_bounded_within, remove_within, write_within
from stayfixed.grammar import PATH_VALUE
from stayfixed.jsonobject import json_object

LOCAL_ROOT = ".stayfixed/local"
# `[artifacts] local` artifacts live one directory further down, so no `[artifacts] local` entry
# can land one on a file another area keeps under `LOCAL_ROOT`: attach's ledger, the local-only
# note store, and the ledger below. `PATH_VALUE` refuses a `..` segment, so for that setting the
# prefix is a boundary and not a convention; the anchor is this constant in the installed package.
# A `[paths]` value never reaches `.stayfixed/` at all: `config.paths.validate_paths` refuses one
# that names it.
LOCAL_ARTIFACTS = f"{LOCAL_ROOT}/artifacts"
LOCAL_DIGESTS = f"{LOCAL_ROOT}/artifacts.json"
FORMAT = 1
MAX_BYTES = 64 * 1024
MAX_ENTRIES = 256
GENERATED = (
    "Written by stayfixed: the bytes it last wrote for each artifact kept out of git. Never "
    "commit it. Deleted, later runs judge a copy at its artifact's own place by what they "
    "render, and no longer find one left at an earlier place."
)
# An artifact id as this build spells them, bounded. An entry under any other id is a fault.
_ID = re.compile(r"\A[a-z0-9][a-z0-9._-]{0,63}\Z")
_SHA256 = re.compile(r"\A[0-9a-f]{64}\Z")


def _read_bounded(root: Path) -> bytes | None:
    """The bytes of a regular file at `LOCAL_DIGESTS`, or `None` for one past `MAX_BYTES` and for
    anything else there.

    Under `root` (`fsops.read_bounded_within`), so no component, the file included, is followed if
    it is a symlink, and a FIFO planted there cannot hang the run; anything but a regular file is
    absent.
    """
    try:
        raw, over = read_bounded_within(root, LOCAL_DIGESTS, MAX_BYTES)
    except OSError:
        return None
    return None if over else raw


Entries = dict[tuple[str, str], str]


def _entries(raw: bytes) -> Entries | None:
    """The entries `raw` holds, or `None` for anything but exactly this module's own shape."""
    try:
        data = json_object(raw.decode("utf-8"), LOCAL_DIGESTS, error=ValueError)
    except ValueError:  # bytes that are not UTF-8 too: `UnicodeDecodeError` is a `ValueError`
        return None
    if data.get("format") != FORMAT:
        return None
    artifacts = data.get("artifacts")
    if not isinstance(artifacts, dict):
        return None
    entries: Entries = {}
    for artifact_id, files in artifacts.items():
        if not isinstance(files, dict) or not _ID.match(artifact_id):
            return None
        for target, sha256 in files.items():
            if not (
                isinstance(sha256, str)
                and target.startswith(f"{LOCAL_ARTIFACTS}/")
                and PATH_VALUE.match(target)
                and _SHA256.match(sha256)
            ):
                return None
            entries[(artifact_id, target)] = sha256
            if len(entries) > MAX_ENTRIES:
                return None
    return entries


@dataclass(frozen=True)
class LocalDigests:
    """`(artifact id, target)` -> sha256: each file stayfixed wrote under `LOCAL_ARTIFACTS`, for
    which artifact, and the digest of that artifact's own part of it, exactly as a manifest record
    stamps it. Keyed by both, because one artifact can have left a copy at a place the
    configuration no longer gives it (its id left `[artifacts] local`, or its `[paths]` value
    moved) while it has another at its current one, and because a region and the skeleton it
    lives in share one file."""

    entries: Entries = field(default_factory=dict)

    @classmethod
    def read(cls, root: Path) -> LocalDigests:
        raw = _read_bounded(root)
        entries = None if raw is None else _entries(raw)
        return cls(entries or {})

    @property
    def ids(self) -> frozenset[str]:
        return frozenset(artifact_id for artifact_id, _ in self.entries)

    # The lookups below are exact: an entry authorizes only at the path it names, as stayfixed
    # wrote it. Which entries are consulted at all is decided case-folded, in
    # `engine.left_copies`, so a case variant never widens what an entry reaches.
    def records(self, artifact_id: str, target: str) -> bool:
        return (artifact_id, target) in self.entries

    def targets_of(self, artifact_id: str) -> tuple[str, ...]:
        return tuple(sorted(target for owner, target in self.entries if owner == artifact_id))

    def matches(self, artifact_id: str, target: str, sha256: str) -> bool:
        """Whether stayfixed recorded writing exactly `sha256` for `artifact_id` at `target`."""
        return self.entries.get((artifact_id, target)) == sha256

    def with_entry(self, artifact_id: str, target: str, sha256: str) -> LocalDigests:
        return LocalDigests({**self.entries, (artifact_id, target): sha256})

    def without(self, artifact_id: str, target: str) -> LocalDigests:
        return LocalDigests({k: v for k, v in self.entries.items() if k != (artifact_id, target)})

    def without_file(self, target: str) -> LocalDigests:
        """Every entry at `target`, once the file itself is gone."""
        return LocalDigests({k: v for k, v in self.entries.items() if k[1] != target})

    def on_disk(self, root: Path) -> LocalDigests:
        """Only the entries whose file is still there: one a person deleted records nothing."""
        return LocalDigests({k: v for k, v in self.entries.items() if os.path.lexists(root / k[1])})

    def write(self, root: Path) -> None:
        """Replace the ledger through the `O_NOFOLLOW` walk, or remove it once it records nothing,
        and refuse rather than raise: this runs from `apply`'s `finally`, like the manifest."""
        try:
            if not self.entries:
                # A missing `.stayfixed/local/` is a ledger already gone, not a fault.
                with contextlib.suppress(FileNotFoundError):
                    remove_within(root, LOCAL_DIGESTS)
                return
            artifacts: dict[str, dict[str, str]] = {}
            for (artifact_id, target), sha256 in sorted(self.entries.items()):
                artifacts.setdefault(artifact_id, {})[target] = sha256
            body = {"_generated": GENERATED, "format": FORMAT, "artifacts": artifacts}
            write_within(root, LOCAL_DIGESTS, json.dumps(body, indent=2) + "\n")
        except OSError as exc:
            raise Refusal(f"{LOCAL_DIGESTS} cannot be written: {exc}") from exc
