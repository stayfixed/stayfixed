"""The release package's import surface: everything code outside it may import from it.

What stays here is what an installed stayfixed reads about its own releases. The repository's
release tooling — the version check, the changelog and the writing of the record — is
`scripts/release.py`, which is not shipped as a command and imports from here like any other
consumer.

`doctor` is the first consumer — `files` compares an installed plugin against the hashes the
release recorded, which needs the file list, the two readers and the class that says "present
and not a record". `RECORD` is not one of `doctor`'s: it names the record's path in prose
instead. The importers for that name are the two repository scripts: `scripts/check_artifacts.py`,
which asks whether a built sdist carries the three hashed files and the record beside them, and
`scripts/release.py`, which writes the record and reports its drift. `FORMAT` is the release
script's alone: the writer has to stamp the number the reader accepts, and one constant is how
the two cannot disagree.

`Pin`, `Resolution`, `released`, `resolve_pin` and `is_released` are published for `init`, which
writes the pin, `doctor`'s `ci-ref` row, which judges it, and `stayfixed gate`, which admits a
moved `[ci] ref` only at a released commit (`is_released`) — all ask this package because "which
commit is release X" is its own question. `released` is published so the row can ask the remote
once for the sha and the alias both. `tag_for` is published for the release script, whose
`check --tag` holds a tag to the tree's version by the same spelling the pin is looked up by.
"""

from stayfixed.release.hashes import (
    FORMAT,
    HASHED_FILES,
    RECORD,
    UnreadableRecord,
    digests,
    read_record,
)
from stayfixed.release.pins import Pin, Resolution, is_released, released, resolve_pin
from stayfixed.release.versions import tag_for

__all__ = [
    "FORMAT",
    "HASHED_FILES",
    "RECORD",
    "Pin",
    "Resolution",
    "UnreadableRecord",
    "digests",
    "is_released",
    "read_record",
    "released",
    "resolve_pin",
    "tag_for",
]
