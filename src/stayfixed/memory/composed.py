"""The composed store: the one directory on this machine that the harness reads memory from.

**One directory, named by the binding id, outside every checkout.** `<data>/stores/<id>/` holds a
link per group into the overlay — `developer` to `<overlay>/common/memory`, the shared notes, and
each directory of `<overlay>/projects/<project>/memory/` to itself — and `MEMORY.md`, a link to the
index `stayfixed memory index` renders in that share. `attach` builds it in `overlay` mode and
writes its absolute path as `autoMemoryDirectory` into the main checkout's excluded
`settings.local.json`, which Claude Code reads from every worktree, so the harness reads the
overlay's notes through one key and no per-worktree link. `<project>` is the project this machine's
binding record names, which the caller passes, and the groups are the directories the overlay
holds for it: no name the repository chose becomes a path here.

**What stayfixed places here is links, and only links are taken.** The harness writes into the
directory it reads, so a file here that is not a link is a note it wrote, and neither a rebuild nor
a withdrawal removes it. `build` makes the store's links exactly the overlay's current set and
`withdraw` takes them all, then the directory where nothing else is left. Both list this
directory, which is derived from the id and never read from a record a checkout keeps, and only
`attach` puts links in it (CONTRIBUTING.md#enumerated-writes). The path names the whole id, so it
is never printed: a fault names the data directory and the id's short form (`binding.unwritten`).
"""

from __future__ import annotations

import os
from pathlib import Path

from stayfixed import fsops
from stayfixed.binding import unwritten
from stayfixed.config.paths import data_directory
from stayfixed.memory.index import INDEX_NAME
from stayfixed.memory.store import COMMON_GROUP, PROJECTS, STORE_DIR, overlay_group_target

# Under the machine's data directory: one composed store per binding id.
STORES = "stores"


def store_directory(id: str) -> Path:
    """`<data>/stores/<id>/`, derived from the id and nothing else."""
    return data_directory() / STORES / id


def _sources(overlay: Path, project: str) -> dict[str, Path]:
    """Each name the store holds and the path in the overlay its link points at."""
    share = overlay / PROJECTS / project / STORE_DIR
    found = {COMMON_GROUP: overlay_group_target(overlay, project, COMMON_GROUP)}
    if fsops.is_dir(share):
        for entry in sorted(os.listdir(share)):
            if not entry.startswith(".") and entry != COMMON_GROUP and fsops.is_dir(share / entry):
                found[entry] = overlay_group_target(overlay, project, entry)
    found[INDEX_NAME] = share / INDEX_NAME
    return found


def _links(directory: Path) -> list[str]:
    """The names of the links in `directory`, which is there."""
    return sorted(name for name in os.listdir(directory) if fsops.is_symlink(directory / name))


def build(overlay: Path, project: str, id: str) -> Path:
    """Make `<data>/stores/<id>/` hold a link to each of the overlay's groups for `project` and to
    its index, and no other link, and return it. A file that is not a link is left where it is."""
    directory = store_directory(id)
    sources = _sources(overlay, project)
    try:
        # The plain-path form for the data directory itself, as `binding.record` writes it.
        directory.mkdir(parents=True, exist_ok=True)
        for name in _links(directory):
            if name not in sources or fsops.readlink_within(directory, name) != sources[name]:
                fsops.unlink_within(directory, name)
        for name, source in sources.items():
            if not fsops.exists(directory / name) and not fsops.is_symlink(directory / name):
                fsops.symlink_within(directory, name, source)
    except OSError as exc:
        raise unwritten(directory.parent, id, exc) from None
    return directory


def withdraw(id: str) -> bool:
    """Take every link out of `<data>/stores/<id>/`, then the directory where nothing is left;
    whether no store is left. A note the harness wrote there keeps it."""
    directory = store_directory(id)
    if not fsops.is_dir(directory):
        return True
    try:
        for name in _links(directory):
            fsops.unlink_within(directory, name)
        if os.listdir(directory):
            return False
        fsops.rmdir_within(directory.parent, directory.name)
    except OSError as exc:
        raise unwritten(directory.parent, id, exc) from None
    return True
