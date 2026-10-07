"""The release's record of the files the harness executes without Python (`hooks/hashes.json`).

This module is the record's reader; the writer is the repository's own release tooling
(`scripts/release.py hashes`), which keeps the record true on every commit and not only at a
tag, so a change to the wrapper that forgot to re-record fails CI. `doctor files` compares the
INSTALLED copies to the INSTALLED record; a determined attacker who edits both is not this
check's threat — tag protection and the pinned SHA are. Post-install modification, a broken
checkout, a partial update: those are.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from stayfixed.errors import Failure
from stayfixed.fsops import said
from stayfixed.jsonobject import json_object

# The three files the harness runs on its own, with no interpreter of ours in front of them:
# the wrapper every hook entry executes, the entry table that names it, and the launcher the
# wrapper hands control to. Python files are not here — a wheel's contents are the packaging
# tool's to attest, and `check_artifacts.py` is what looks at those.
HASHED_FILES = ("hooks/run-hook.sh", "hooks/hooks.json", "scripts/stayfixed")
# Beside what it hashes, so an installation that carried the files carries the record too.
RECORD = "hooks/hashes.json"
FORMAT = 1


class UnreadableRecord(Failure):
    """The record is there and is not a record: a distinct answer from "absent", because an
    absent record skips in `doctor` while an unreadable one must be red."""


def digests(root: Path) -> dict[str, str]:
    """sha256 per hashed file that exists under `root`, in `HASHED_FILES` order."""
    found: dict[str, str] = {}
    for relative in HASHED_FILES:
        path = root / relative
        if path.is_file():
            found[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    return found


def read_record(root: Path) -> dict[str, str] | None:
    """The digests the record names, `None` when there is no record at all.

    The two are different answers and the callers branch on the difference: a build with no
    record is one `doctor` skips, and a record that is present and is not a record is one it
    must be red about.

    **The keys are repository-authored and are validated here as shape and never as trust.**
    A caller that prints one prints bytes the record's author chose: the record is read from
    an installed plugin root, which `doctor.checks.plugin_root` explains a committed
    `.claude/settings.json` `env` block can name. Holding the keys to `HASHED_FILES` here is
    the rule this function must NOT apply — `doctor._files` walks the union of the record and
    this build's own list precisely so that a record naming a file this build does not ship is
    visible rather than dropped, and the release script's `drift` reports the same direction —
    so the rule belongs where the printing happens: `_files` prints the names it knows and
    counts the rest.
    """
    path = root / RECORD
    if not path.is_file():
        return None
    # **Three ways a present record is not readable, and all three are this class.** The guard
    # used to catch `json.JSONDecodeError` alone, so a record carrying non-UTF-8 bytes — a
    # truncated or half-copied file, which is exactly the threat this module's docstring names
    # — raised `UnicodeDecodeError` past every caller. The release checks (`hashes --check` and
    # `check`) turned it into `stayfixed: internal error`, **exit 2**, where a finding is 1;
    # and `doctor._files` reached it through `_guarded`'s `except Exception`, which reports
    # `this check could not run` with the remedy *"report this, with the command you ran"* —
    # telling the owner to file a bug against stayfixed for a corrupt file in their own install.
    # A record the process cannot read (`PermissionError`) took the other wrong turn, to `warn`.
    # Neither reached the `except UnreadableRecord` arm whose sentence is "present and
    # unreadable", which is the arm this class exists to select.
    try:
        raw = path.read_bytes()
        # Decoded as `json.loads` decodes bytes, which is how 0.2.0 read the record: UTF-8, with
        # or without a byte-order mark, UTF-16 or UTF-32, as the first bytes say.
        text = raw.decode(json.detect_encoding(raw), "surrogatepass")
    except UnicodeDecodeError as exc:
        raise UnreadableRecord(f"{RECORD} is present and is not UTF-8 text: {exc}") from None
    except OSError as exc:
        raise UnreadableRecord(f"{RECORD} is present and could not be read ({said(exc)})") from None
    # Through `jsonobject`, the one reader of a JSON object, so every way the parse can fail --
    # not JSON, nested past the parser or its depth bound, an integer longer than the interpreter
    # converts -- is this record's refusal in the words every reader uses.
    not_a_record = UnreadableRecord(f"{RECORD} is present and is not a format-{FORMAT} record")
    document = json_object(text, RECORD, error=UnreadableRecord, shape=lambda _: not_a_record)
    files = document.get("files")
    if (
        document.get("format") != FORMAT
        or not isinstance(files, dict)
        or not all(isinstance(value, str) for value in files.values())
    ):
        raise UnreadableRecord(f"{RECORD} is present and is not a format-{FORMAT} record")
    return {str(key): str(value) for key, value in files.items()}
