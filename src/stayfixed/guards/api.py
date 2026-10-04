"""The import surface: everything a consumer may import from this area.

A module and not the package's `__init__`, for the same measured reason `stayfixed.memory.api`
gives: `stayfixed.hooks.registry` imports `stayfixed.guards.hooks`, which imports the package
first, so a re-export list in `__init__.py` would pull this whole area into every `discover()`
call and reddens `tests/test_areas.py`. Keeping the surface one level down costs a consumer six
characters and keeps discovery cheap.

The list is what consumers outside this area actually reach for: the git hook, one shared rule
and one gate:

- `setup` offers and undoes the git hook (`install`, `uninstall`, `HOOK_NAME`), and `Installed`
  and `Removed` come with the two verbs, because a return type absent from this list is a value
  `setup` can hold and cannot declare.
- `attach`, `doctor` and `setup`'s own tests ask where an overlay's hooks really live rather
  than assume `.git/hooks` (`hooks_dir`, `HOOK_MARKER`) — an overlay with `core.hooksPath` set,
  or one that is a worktree or a submodule, keeps them somewhere else, and both areas had the
  same wrong spelling hardcoded.
- `attach` and `detach` resolve the repository's `info/exclude` through the same resolver
  (`git_path`), so the block they keep there is the one file every worktree shares, found the
  way `setup --git-hooks` finds its hooks directory rather than by a second spelling.
- `ledger.scan`, `memory.refs` and `assess`'s probes all ask which roots a configuration's paths
  may reach (`contained_roots`), and two spellings of that would be two answers.
- `assess` runs the `commit` gate (`commit_gate`), `(root, config, base) -> list[Finding]`;
  `commit check` reads the same range through the same `check_range`.

An area that needs something absent from this list grows it deliberately, in a commit that says
which area and why.

**What is not here.** The commit rules (`offending_lines`, `check_range`, `strip_message` and
their records), the hygiene surface, the scanner a guard is built on, the failure
attribution and the background-cleanup judge stay in the modules that define them, each
reachable there: no other area imports them, and a name published for a consumer that does not
exist is a claim nothing checks. `assess` needs one name from this area, `commit_gate`, and it is
above.
"""

from stayfixed.guards.commit import commit_gate
from stayfixed.guards.githooks import (
    HOOK_MARKER,
    HOOK_NAME,
    Installed,
    Removed,
    git_path,
    hooks_dir,
    install,
    uninstall,
)
from stayfixed.guards.roots import contained_roots

__all__ = [
    "HOOK_MARKER",
    "HOOK_NAME",
    "Installed",
    "Removed",
    "commit_gate",
    "contained_roots",
    "git_path",
    "hooks_dir",
    "install",
    "uninstall",
]
