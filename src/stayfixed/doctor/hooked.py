"""The walk for skill, command and agent files whose frontmatter declares hooks.

`hook-entries` judges the entries of settings files, and names, without judging, every file a
harness reads Markdown frontmatter hooks out of whose frontmatter declares them. This module finds
those files and reads them: the root's own places off the disk, the places below the root as git
lists them, or, where git cannot answer, by a bounded walk. What it reports of each path is a
`Seen`, and `doctor.entries` tells each in the row's words; whether a file's text declares hooks is
`doctor.frontmatter`'s to answer. It imports nothing of the row's, so `entries` can import it
without a cycle.
"""

from __future__ import annotations

import os
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path, PurePosixPath
from stat import S_ISDIR

from stayfixed import fsops
from stayfixed.doctor.frontmatter import declares_hooks
from stayfixed.fsops import NAMES_NO_FILE, read_regular_bytes
from stayfixed.gitenv import QUERY_TIMEOUT_SECONDS, git_run, in_work_tree
from stayfixed.harnesses import HARNESSES, Hooked
from stayfixed.printed import printable

# Every place a registered harness reads Markdown whose frontmatter can declare hooks
# (`harnesses.Hooked`), read off the registry, so a harness added there is walked here without an
# edit. The row names each such file whose frontmatter declares hooks as one it does not judge
# (`hooked`).
HOOKED = tuple(place for harness in HARNESSES for place in harness.hooked)
# Git's own directory, which the walk below the root never enters: git refuses to check out a path
# with a `.git` component, so nothing in one is the repository's, and it can hold many entries.
_GIT_DIR = ".git"
# What a file whose path is outside the path grammar is named as: the path is the repository's,
# and the row's detail is what `--json` carries too, so there is nowhere else to point.
_UNPRINTED = "a skill, command or agent file whose path this row does not print"


class Seen(Enum):
    """What the walk reports of one path, which `doctor.entries` tells as a kind of finding."""

    # A file whose frontmatter declares hooks.
    DECLARES = "declares"
    # A file or directory that could not be read, so nothing can be said of what it holds.
    UNREAD = "unread"
    # A link that leads out of the checkout, which is not followed.
    LINKED_OUT = "linked-out"
    # The walk stopped at `fsops.WALK_ENTRIES`; it names no path.
    STOPPED = "stopped"


# One report of the walk: what it saw, and the path it names, `None` for `Seen.STOPPED`.
Found = tuple[Seen, str | None]


class _Spent(Exception):
    """The walk for hooked files listed more than `fsops.WALK_ENTRIES` entries."""


@dataclass
class _Budget:
    """What is left of `fsops.WALK_ENTRIES` for one walk: the cap every walk over a repository's
    tree reads, below the root's own directories and through the whole tree for the nested
    ones."""

    left: int = field(default_factory=lambda: fsops.WALK_ENTRIES)

    def spend(self, entries: int) -> None:
        self.left -= entries
        if self.left < 0:
            raise _Spent


def _label(relative: str) -> str:
    """A path under the root as the row names it: the path is the repository's."""
    return printable(relative, _UNPRINTED)


def _reads(place: Hooked, name: str) -> bool:
    """Whether a file named `name` below `place` is one whose frontmatter is read. Compared
    without case, because a filesystem that folds case finds `skill.md` at `SKILL.md`."""
    folded = name.casefold()
    if place.name is None:
        return folded.endswith(".md")
    return folded == place.name.casefold()


def _inside(real_root: Path, path: Path) -> bool:
    """Whether `path`, every link in it followed, is still under `real_root`, the root's own
    resolved path. Asked through `os.path.realpath`, which answers for a link that loops too."""
    return Path(os.path.realpath(path)).is_relative_to(real_root)


def _frontmatter(root: Path, real_root: Path, relative: str) -> list[Found]:
    """The report for one file whose frontmatter is read: it declares hooks, or it could not be
    read, or it leads out of the checkout, or none. A link that leads out is not followed and is
    named as one that does (`Seen.LINKED_OUT`): what it leads to is not the repository's. Whether
    a path names a file is asked first, so a dangling link names none wherever it points. Read
    through `fsops.read_regular_bytes`, `fsops`' one bounded reader at the regular-file cap, which
    every reader of a committed file goes through at its own cap: a device or a FIFO is refused
    unread, and a file past the cap is refused, each one this row could not read; a path that
    names no file is passed over."""
    path = root / relative
    try:
        path.stat()
    except OSError as exc:
        if exc.errno in NAMES_NO_FILE:
            return []
        return [(Seen.UNREAD, _label(relative))]
    if not _inside(real_root, path):
        return [(Seen.LINKED_OUT, _label(relative))]
    try:
        content = read_regular_bytes(path)
    except OSError as exc:
        if exc.errno in NAMES_NO_FILE:
            return []
        return [(Seen.UNREAD, _label(relative))]
    # Replaced rather than refused, for the reason the settings walk replaces: the key is
    # ASCII, so a byte that is not UTF-8 elsewhere changes no answer.
    if declares_hooks(content.decode("utf-8", errors="replace")):
        return [(Seen.DECLARES, _label(relative))]
    return []


def _read_place(
    root: Path, real_root: Path, top: str, place: Hooked, budget: _Budget
) -> list[Found]:
    """A report for each file below `top`, a directory `place` names, whose frontmatter declares
    hooks or could not be read, in name order, depth first.

    Links are followed, as the harness follows them, while they lead to a directory still inside
    the checkout; one that leads out is named as one that does (`Seen.LINKED_OUT`), and one that
    cannot be listed as a directory this row could not read. A directory reached twice is listed
    once, so a link back up the tree ends rather than circling until the cap. A name `place` reads
    goes to `_frontmatter`, which reads a link to a file inside the checkout and names one that
    leads out; any other link that names no directory is passed over, as `top` itself is when there
    is none."""
    found: list[Found] = []
    listed_once: set[tuple[int, int]] = set()
    pending = [top]
    while pending:
        relative = pending.pop()
        directory = root / relative
        try:
            status = directory.stat()
            if not S_ISDIR(status.st_mode):
                continue
            if not _inside(real_root, directory):
                found.append((Seen.LINKED_OUT, _label(relative)))
                continue
            if (status.st_dev, status.st_ino) in listed_once:
                continue
            listed_once.add((status.st_dev, status.st_ino))
            with os.scandir(directory) as listing:
                names = sorted(entry.name for entry in listing)
        except OSError as exc:
            if exc.errno not in NAMES_NO_FILE:
                found.append((Seen.UNREAD, _label(relative)))
            continue
        budget.spend(len(names))
        below: list[str] = []
        for name in names:
            child = f"{relative}/{name}"
            if _reads(place, name):
                found.extend(_frontmatter(root, real_root, child))
            # Two answers to one fault, kept apart on purpose: a name too long to ask about is
            # a directory that is not there to `fsops.is_dir`, and passed over, while the `stat`
            # above and in `_frontmatter` asks with `NAMES_NO_FILE`, where it is a path this row
            # could not read and is named. A child is only asked whether to descend; a path the
            # row reads or lists is one it reports on when it cannot.
            elif fsops.is_dir(root / child):
                below.append(child)
        pending.extend(reversed(below))
    return found


def _owned(relative: str, places: Sequence[Hooked]) -> Hooked | None:
    """The place among `places` whose directory `relative`, a directory below the root, is, or
    ends in, compared without case: a filesystem that folds case finds `.Claude/Skills` where
    `.claude/skills` is looked for."""
    folded = f"/{relative}".casefold()
    return next((p for p in places if folded.endswith(f"/{p.directory}".casefold())), None)


# The file whose presence says a work tree has submodules, at its top level.
_GITMODULES = ".gitmodules"


def _listing(asked: tuple[int, str]) -> set[str] | None:
    """The names a `git ls-files -z` answer lists, or `None` where it gives no answer: a `git` that
    fails or runs past `QUERY_TIMEOUT_SECONDS`, the bound for a query over a whole tree."""
    code, answer = asked
    if code != 0:
        return None
    return {name for name in answer.split("\0") if name}


def _queried(root: Path) -> list[tuple[str, Hooked]] | None:
    """Every entry below the root inside a directory a `nested` place names, as git's index lists
    it, with that place, in name order; or `None` where git cannot answer: outside a work tree, or
    a `git` that fails.

    Tracked files and untracked ones git does not ignore, which is what a clone commits and what
    the owner is writing; never an ignored one, which no clone carries, and whose trees, an
    installed dependency's or a build's, are what made a walk of the whole checkout stop at its
    cap. Each place is asked with a pathspec git matches without case (`icase`), so a directory or
    file name in any case is listed as a filesystem that folds case finds it. Every entry is
    listed and not only the files a place reads, because git lists a link as an entry of its own
    and never what it leads to, and a link may lead to a skill (`hooked` reads it as a directory);
    so is an entry that is the place's directory itself, which is a link where git lists one.

    `--cached` lists a submodule as one entry and none of its files, and `--recurse-submodules`
    takes no `--others`, so a work tree with a `.gitmodules` at or above the root is asked a second
    time, through each checked-out submodule's index: what that index holds, its staged files as
    well as its committed ones. An entry under
    one of the root's own places is left out: those are read off the disk (`_read_place`)."""
    places = [place for place in HOOKED if place.nested]
    if not places or not in_work_tree(root):
        return None
    pathspecs = [
        spec
        for place in places
        for spec in (f":(glob,icase)**/{place.directory}", f":(glob,icase)**/{place.directory}/**")
    ]
    listed = _listing(
        git_run(
            root,
            "ls-files",
            "-z",
            "--cached",
            "--others",
            "--exclude-standard",
            "--",
            *pathspecs,
            timeout=QUERY_TIMEOUT_SECONDS,
        )
    )
    if listed is None:
        return None
    if any(os.path.lexists(directory / _GITMODULES) for directory in (root, *root.parents)):
        modules = _listing(
            git_run(
                root,
                "ls-files",
                "-z",
                "--cached",
                "--recurse-submodules",
                "--",
                *pathspecs,
                timeout=QUERY_TIMEOUT_SECONDS,
            )
        )
        if modules is None:
            return None
        listed |= modules
    own = tuple(f"{place.directory}/".casefold() for place in HOOKED)
    found: list[tuple[str, Hooked]] = []
    for name in sorted(listed):
        folded = f"/{name}/".casefold()
        place = next((p for p in places if f"/{p.directory}/".casefold() in folded), None)
        if place is not None and not f"{name}/".casefold().startswith(own):
            found.append((name, place))
    return found


def _nested(root: Path, budget: _Budget) -> Iterator[tuple[str, Hooked]]:
    """Every directory below the root that a `nested` place names, with that place, in name
    order, depth first: the bounded walk for a root git cannot answer for (`_queried`).

    No link is followed and `.git` is never entered: what a link leads to outside the tree is
    not the repository's, and inside it the walk meets it where it is. A link that is itself such
    a directory is handed out, as the query hands one out, for `_read_place` to follow while it
    stays in the checkout. A directory that cannot be
    listed is passed over, as the bytecode walk passes one over: git records no permission that
    keeps one from being listed. The root's own copy of a place is not one of these, and nothing
    below a directory handed out here is walked again."""
    places = [place for place in HOOKED if place.nested]
    pending = [""]
    while pending and places:
        relative = pending.pop()
        try:
            with os.scandir(root / relative) as listing:
                entries = sorted(
                    (entry.name, entry.is_dir(follow_symlinks=False), entry.is_symlink())
                    for entry in listing
                )
        except OSError:
            continue
        budget.spend(len(entries))
        below: list[str] = []
        for name, is_directory, is_link in entries:
            if not (is_directory or is_link) or name == _GIT_DIR:
                continue
            child = f"{relative}/{name}" if relative else name
            owner = _owned(child, places)
            if owner is None:
                if is_directory:
                    below.append(child)
            elif child.casefold() != owner.directory.casefold():
                yield child, owner
        pending.extend(reversed(below))


def hooked(root: Path) -> list[Found]:
    """A report for each skill, command or agent file whose frontmatter declares hooks, and for
    each such file or directory that could not be read or leads out of the checkout: the root's own
    places first, in `HOOKED`'s order, read off the disk, then each file a nested place names, as
    git lists it (`_queried`), or, where git cannot answer, as the bounded walk finds it
    (`_nested`). The walks list at most `fsops.WALK_ENTRIES` entries between them, past which they
    stop and say so (`Seen.STOPPED`). Each file is named by its path, through `printed.printable`,
    because every name in it is the repository's."""
    found: list[Found] = []
    budget = _Budget()
    real_root = Path(os.path.realpath(root))
    try:
        for place in HOOKED:
            found.extend(_read_place(root, real_root, place.directory, place, budget))
        queried = _queried(root)
        if queried is not None:
            for relative, place in queried:
                if _reads(place, PurePosixPath(relative).name):
                    found.extend(_frontmatter(root, real_root, relative))
                elif os.path.islink(root / relative):
                    found.extend(_read_place(root, real_root, relative, place, budget))
        else:
            for directory, place in _nested(root, budget):
                found.extend(_read_place(root, real_root, directory, place, budget))
    except _Spent:
        found.append((Seen.STOPPED, None))
    return found
