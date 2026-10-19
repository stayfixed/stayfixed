"""The tree a `prove` run ran on, as git sees it, for a reader of the receipt.

Taken before the run and after it, through `gitenv.git_run`: the commit `HEAD` names, whether the
work tree differs from it at all, and the untracked and the ignored files in the runner's discovery
set. Each value is `None` where git cannot answer, outside a repository among them, and never a
refusal. The untracked files that are not ignored are listed before the ignored ones, so a file a
change added is never hidden behind a count of an ignored dependency tree's; the list stops at
`UNTRACKED_LISTED` and counts the rest.

Information and never an input to the verdict: everything it reads, the agent that typed the
command can write, and a file in the runner's load path, tracked or not, is what the bound concedes.

A glob is matched the way `PurePosixPath.match` matches one, from the right: `test_*.py` names a
file of that name at any depth, and `tests/*.py` one directly under any `tests` directory.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from stayfixed.gitenv import QUERY_TIMEOUT_SECONDS, git_run

# A named cap: how many untracked or ignored files in the discovery set a receipt names before it
# counts the rest. Twenty is room for the handful a change adds
# and short enough for one line; a tree past it is said to be past it, with the number. No shipped
# file states it.
UNTRACKED_LISTED = 20


@dataclass(frozen=True)
class TreeState:
    """`commit`: `HEAD`'s sha. `dirty`: whether `git status` lists anything, untracked files
    included. `untracked`: the untracked files a discovery glob matches and then the ignored ones,
    each in path order, at most `UNTRACKED_LISTED`, and `more` the count past them."""

    commit: str | None
    dirty: bool | None
    untracked: tuple[str, ...] | None
    more: int


def _capped(found: Sequence[str]) -> tuple[tuple[str, ...], int]:
    return tuple(found[:UNTRACKED_LISTED]), max(len(found) - UNTRACKED_LISTED, 0)


def _listed(root: Path, *args: str) -> list[str] | None:
    """The NUL-separated names git printed for `args`, or `None` where it gave no answer."""
    code, out = git_run(root, *args, timeout=QUERY_TIMEOUT_SECONDS)
    if code != 0:
        return None
    return [name for name in out.split("\0") if name]


def _matching(names: Sequence[str], globs: Sequence[str]) -> list[str]:
    return sorted({name for name in names if any(PurePosixPath(name).match(g) for g in globs)})


def head(root: Path) -> tuple[str | None, bool | None]:
    """`HEAD`'s sha, and whether `git status` lists anything, untracked files included; each
    `None` where git gives no answer."""
    code, out = git_run(root, "rev-parse", "--verify", "--quiet", "HEAD")
    commit = out.strip() or None if code == 0 else None
    status = _listed(root, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    return commit, bool(status) if status is not None else None


def state(root: Path, discovery: Sequence[str]) -> TreeState:
    """The tree under `root` as git answers for it now."""
    commit, dirty = head(root)
    others = _listed(root, "ls-files", "-z", "--others", "--exclude-standard")
    ignored = _listed(root, "ls-files", "-z", "--others", "--ignored", "--exclude-standard")
    untracked: tuple[str, ...] | None = None
    more = 0
    if others is not None and ignored is not None:
        untracked, more = _capped(_matching(others, discovery) + _matching(ignored, discovery))
    return TreeState(commit=commit, dirty=dirty, untracked=untracked, more=more)
