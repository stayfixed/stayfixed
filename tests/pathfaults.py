"""Paths that make `stat` and `lstat` meet each fault a path query can meet.

For the tests that hold `fsops`' path predicates and `config.paths.contained` to one answer per
fault on every interpreter: `pathlib`'s own predicates raise on some of these up to Python 3.13
and answer `False` from 3.14, so a suite that ran on one interpreter proved nothing about the
other. Each shape is built under a scratch root, and `LSTAT_FAULT` says what an `lstat` of its
path meets, which the tests assert before they assert anything else: a shape that stopped
meeting its fault would prove nothing either.
"""

from __future__ import annotations

import contextlib
import errno
import os
from pathlib import Path

# What an `lstat` of each shape's path meets: an errno, `ValueError` for a NUL, or `None` when it
# finds something there.
LSTAT_FAULT: dict[str, int | type[ValueError] | None] = {
    "a-regular-file": None,
    "a-directory": None,
    "a-link-to-a-file": None,
    "a-link-to-a-directory": None,
    "a-dangling-link": None,
    "a-link-loop": None,
    "a-link-to-a-name-longer-than-a-name": None,
    "nothing-there": errno.ENOENT,
    "below-a-file": errno.ENOTDIR,
    "through-a-link-loop": errno.ELOOP,
    "a-name-longer-than-a-name": errno.ENAMETOOLONG,
    "past-the-longest-path": errno.ENAMETOOLONG,
    "through-a-link-to-a-name-longer-than-a-name": errno.ENAMETOOLONG,
    "below-a-directory-that-cannot-be-searched": errno.EACCES,
    "a-nul": ValueError,
}

# Longer than any filesystem here takes as one name: 255 on Linux and macOS alike.
_OVERLONG = 300


def shaped(root: Path, shape: str) -> str:
    """Build `shape` under `root`, and answer its path relative to `root`.

    `below-a-directory-that-cannot-be-searched` leaves `root / "locked"` without its search bit;
    `unlock` gives it back, so the scratch directory can be removed.
    """
    (root / "file").write_text("text\n", encoding="utf-8")
    (root / "directory").mkdir()
    if shape == "a-regular-file":
        return "file"
    if shape == "a-directory":
        return "directory"
    if shape == "a-link-to-a-file":
        (root / "to-file").symlink_to(root / "file")
        return "to-file"
    if shape == "a-link-to-a-directory":
        (root / "to-directory").symlink_to(root / "directory", target_is_directory=True)
        return "to-directory"
    if shape == "a-dangling-link":
        (root / "dangling").symlink_to(root / "nowhere")
        return "dangling"
    if shape in ("a-link-loop", "through-a-link-loop"):
        (root / "loop").symlink_to(root / "loop")
        return "loop" if shape == "a-link-loop" else "loop/below"
    if shape in (
        "a-link-to-a-name-longer-than-a-name",
        "through-a-link-to-a-name-longer-than-a-name",
    ):
        # A link is only text, so a clone can commit one whose target no file can have.
        (root / "far").symlink_to("a" * _OVERLONG)
        return "far" if shape.startswith("a-link") else "far/below"
    if shape == "nothing-there":
        return "absent/below"
    if shape == "below-a-file":
        return "file/below"
    if shape == "a-name-longer-than-a-name":
        return "n" * _OVERLONG
    if shape == "past-the-longest-path":
        longest = os.pathconf(root, "PC_PATH_MAX")
        parts = ["d" * 200] * (longest // 200 + 1)
        return "/".join(parts)
    if shape == "below-a-directory-that-cannot-be-searched":
        (root / "locked" / "child").mkdir(parents=True)
        (root / "locked").chmod(0o600)
        return "locked/child"
    if shape == "a-nul":
        return "a\x00b"
    raise AssertionError(shape)


def unlock(root: Path) -> None:
    """Give `root / "locked"` its search bit back, where `shaped` took it."""
    with contextlib.suppress(FileNotFoundError):
        (root / "locked").chmod(0o700)


def lstat_fault(path: Path) -> int | type[ValueError] | None:
    """What an `lstat` of `path` meets, in `LSTAT_FAULT`'s terms."""
    try:
        os.lstat(path)
    except OSError as exc:
        return exc.errno
    except ValueError:
        return ValueError
    return None
