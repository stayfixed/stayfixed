"""`rewrite_owned`: the one way a command changes a tool-owned key in `stayfixed.toml`.

Three steps, each owned elsewhere. `config.owned.rewrite` edits the text and proves the edit by
parsing it back. `fsops.write_within` writes it. And the `config` record in
`.stayfixed/manifest.json` is re-stamped when it described the file before the edit, so a document
nobody but stayfixed has touched stays one `stayfixed uninstall` recognises, and an edited one is
never blessed.

**The record is re-stamped before the document is written, and put back when the write
fails.** In the other order an interruption between the two leaves the new file beside a record
naming the old bytes; the next run finds nothing to rewrite, and `uninstall` keeps an untouched
`stayfixed.toml` for good. In this order a write that fails leaves a record naming bytes the file
does not hold, and the next run may compute different ones (a later version, a new pin): it would
find the record describing neither, never re-stamp it again, and `uninstall` would keep the file
as edited for good. So a failed write puts the record back as it was, naming the bytes the file
still holds. What is left is a process killed between the two writes, which leaves the record
naming the new bytes; the next run computes the same bytes unless the version or the pin moved
in between, finds the record already naming them, and writes the file. A restore that fails too
leaves that same state, and the refusal still names `stayfixed.toml`'s own failure, the one to put
right, with the manifest's as its cause rather than in its place.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path

import stayfixed
from stayfixed.config.loader import CONFIG_FILE, read_document
from stayfixed.config.owned import Value, rewrite
from stayfixed.errors import Refusal
from stayfixed.fsops import said, write_within
from stayfixed.project.templates import CONFIG_ARTIFACT
from stayfixed.scaffold import Manifest, ManifestError, digest

NO_DOCUMENT = f"{CONFIG_FILE} is not there, so there is no tool-owned key to rewrite"


def rewrite_owned(root: Path, changes: Mapping[tuple[str, str], Value]) -> None:
    text = read_document(root)
    if text is None:
        raise Refusal(NO_DOCUMENT)
    document = rewrite(text, changes)
    if document == text:
        return
    manifest = Manifest.read(root)
    record = manifest.get(CONFIG_ARTIFACT)
    stamped = None
    if record is not None and record.sha256 == digest(text):
        stamped = replace(record, sha256=digest(document), version=stayfixed.__version__)
        manifest.with_record(stamped).write(root)
    try:
        write_within(root, CONFIG_FILE, document)
    except OSError as exc:
        failure = Refusal(f"{CONFIG_FILE} cannot be written: {said(exc)}")
        if stamped is not None:
            try:
                manifest.write(root)
            except ManifestError as restore:
                raise failure from restore
        raise failure from exc
