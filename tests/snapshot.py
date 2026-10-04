"""The tree-snapshot helpers five test modules share.

Here rather than in `tests/test_install_path.py`, because an `attach` test module that imports an
installer-focused module's private names is coupled to a module it does not test. The `git` this
module used to publish beside them is `tests/gitfixture.py`'s now: running `git` and reading a tree
back are two concerns, and only one of them was duplicated twenty-three times.
"""

from __future__ import annotations

import os
from pathlib import Path

# The only `.git` paths a defect this guard cares about could actually land in: a hook dropped
# into `.git/hooks/`, a rule written to `.git/config`, an ignore region added to
# `.git/info/exclude`. Everything else under `.git` — `objects/`, `logs/`, `refs/`, a fresh
# `commit-graph`, a pack, `gc.log`, `objects/maintenance.lock` — is git's own background
# bookkeeping. It ran between two snapshots taken moments apart while the fixtures that build
# these repositories left `gc.auto` and `maintenance.auto` at their defaults; they turn both off
# now (`tests/gitfixture.py`), and the walk stays this narrow because none of those paths is one
# that a write by `attach` or `detach` could land in.
_STABLE_GIT_FILES = (Path("config"), Path("info") / "exclude")


def stable_git_snapshot(root: Path) -> dict[str, bytes]:
    """The narrow slice of `.git` this guard reads: the two named files, plus every file
    under `hooks/`, by path relative to `root`."""
    git_dir = root / ".git"
    files: dict[str, bytes] = {}
    for relative in _STABLE_GIT_FILES:
        candidate = git_dir / relative
        if candidate.is_file():
            files[str(Path(".git") / relative)] = candidate.read_bytes()
    hooks = git_dir / "hooks"
    if hooks.is_dir():
        for path in sorted(hooks.iterdir()):
            if path.is_file():
                files[str(Path(".git") / "hooks" / path.name)] = path.read_bytes()
    return files


def snapshot(root: Path) -> dict[str, bytes]:
    """Every regular file under the root, by relative path.

    `.git` is included deliberately — this is the walk that would catch an ignore region
    written to `.git/info/exclude` or a hook dropped into `.git/hooks` — but narrowed to the
    paths a defect could actually land in. See `stable_git_snapshot` for why the rest of
    `.git` is pruned rather than walked: it is a moving target, not a place this guard watches.
    """
    files: dict[str, bytes] = {}
    for dirpath, dirnames, filenames in os.walk(root):
        current = Path(dirpath)
        if current == root:
            dirnames[:] = [name for name in dirnames if name != ".git"]
        for name in filenames:
            path = current / name
            if path.is_file():
                files[str(path.relative_to(root))] = path.read_bytes()
    files.update(stable_git_snapshot(root))
    return files


def describe_snapshot_diff(before: dict[str, bytes], after: dict[str, bytes]) -> str:
    """A failure message a person can read: which paths came, went or changed, not a dump of
    every file's bytes — which is what the bare `dict == dict` assertion this backs used to
    print, `.git` object tree included, on the one CI job the race actually hit.
    """
    added = sorted(set(after) - set(before))
    removed = sorted(set(before) - set(after))
    changed = sorted(path for path in before.keys() & after.keys() if before[path] != after[path])
    return f"snapshot differs: added={added} removed={removed} changed={changed}"


def assert_snapshot_unchanged(root: Path, before: dict[str, bytes]) -> None:
    after = snapshot(root)
    assert after == before, describe_snapshot_diff(before, after)


def assert_snapshot_changed(root: Path, before: dict[str, bytes]) -> dict[str, bytes]:
    after = snapshot(root)
    assert after != before, "expected at least one file under the root to differ; none did"
    return after
