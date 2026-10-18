"""The tree a `prove` run ran on, as git sees it, for a reader of the receipt.

Taken before the run and after it, through `gitenv.git_run`: the commit `HEAD` names, whether the
work tree differs from it at all, the untracked and the ignored files in the runner's discovery
set, and the files that configure the runner that exist. Each value is `None` where git cannot
answer, outside a repository among them, and never a refusal. The untracked files that are not
ignored are listed before the ignored ones, so a file a change added is never hidden behind a count
of an ignored dependency tree's; a configuration file is one git tracks, or one it does not and
does not ignore, since an ignored dependency tree holds configuration-named files by the dozen
and none of them is the project's. Both lists stop at `UNTRACKED_LISTED` and count the rest.

Information and never an input to the verdict: everything it reads, the agent that typed the
command can write, and a file in the runner's load path, tracked or not, is what the bound concedes.
So the receipt names what could have shaped the report, and the reader weighs it.

A glob is matched the way `PurePosixPath.match` matches one, from the right: `test_*.py` names a
file of that name at any depth, and `tests/*.py` one directly under any `tests` directory.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from stayfixed import fsops
from stayfixed.gitenv import QUERY_TIMEOUT_SECONDS, git_run

# A named cap: how many untracked or ignored files in the discovery set, and how many configuration
# files, a receipt names before it counts the rest. Twenty is room for the handful a change adds
# and short enough for one line; a tree past it is said to be past it, with the number. No shipped
# file states it.
UNTRACKED_LISTED = 20


@dataclass(frozen=True)
class TreeState:
    """`commit`: `HEAD`'s sha. `dirty`: whether `git status` lists anything, untracked files
    included. `untracked`: the untracked files a discovery glob matches and then the ignored ones,
    each in path order, at most `UNTRACKED_LISTED`, and `more` the count past them. `configs`: the
    files a configuration glob matches that exist and that git tracks or does not ignore, in path
    order, at most `UNTRACKED_LISTED`, and `configs_more` the count past them."""

    commit: str | None
    dirty: bool | None
    untracked: tuple[str, ...] | None
    more: int
    configs: tuple[str, ...] | None
    configs_more: int


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


def state(root: Path, discovery: Sequence[str], configs: Sequence[str]) -> TreeState:
    """The tree under `root` as git answers for it now."""
    code, out = git_run(root, "rev-parse", "--verify", "--quiet", "HEAD")
    commit = out.strip() or None if code == 0 else None
    status = _listed(root, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    others = _listed(root, "ls-files", "-z", "--others", "--exclude-standard")
    ignored = _listed(root, "ls-files", "-z", "--others", "--ignored", "--exclude-standard")
    tracked = _listed(root, "ls-files", "-z", "--cached")
    untracked: tuple[str, ...] | None = None
    more = 0
    if others is not None and ignored is not None:
        untracked, more = _capped(_matching(others, discovery) + _matching(ignored, discovery))
    configured: tuple[str, ...] | None = None
    configs_more = 0
    if others is not None and tracked is not None:
        named = _matching([*tracked, *others], configs)
        configured, configs_more = _capped([name for name in named if fsops.exists(root / name)])
    return TreeState(
        commit=commit,
        dirty=bool(status) if status is not None else None,
        untracked=untracked,
        more=more,
        configs=configured,
        configs_more=configs_more,
    )
