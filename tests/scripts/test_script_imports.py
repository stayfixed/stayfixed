"""No script under `scripts/` imports another, but the one exemption named here.

The rule exists for two reasons. `scripts/publish_plugin.py` runs `scripts/plugin_tree.py` and
`src/stayfixed` read out of the tag's objects, so nothing it runs may reach for a sibling script
that extraction does not carry. And the constants two scripts share are copied, each into its own
file, and held equal by tests (`tests/test_check_workflow.py`'s
`test_one_commit_id_shape_everywhere` and `test_one_plugin_repository_everywhere`) rather than
imported.

The walk reads import statements in the syntax tree of every `scripts/*.py` and of the launcher
`scripts/stayfixed`, at module level or inside a function. A script is importable by its stem
only through a `.py` file, so the stems of those files are the names an offence can take; the
launcher is read as an importer and never as a module. The walk's limits: a script run through
`runpy` or loaded through `importlib` is not seen, nor one reached by a name built at run time; and
`sys.path` is not followed, so an import statement is judged by its name alone, and a module of a
sibling's name that `sys.path` would find elsewhere is an offence all the same. What the walk
cannot see is reviewed by hand.
"""

from __future__ import annotations

import ast
from pathlib import Path

from tests.scriptload import SCRIPTS

# The scripts allowed to import a sibling, as (the importing file's name, the module it imports).
# Both are CI smoke drivers run from the checkout, never from the tag's objects, so the sibling is
# always beside it: `smoke_exfiltration.py` reuses `smoke_hooks`'s fixture repository, owner home
# and developer-free environment rather than keep a second copy of each.
EXEMPT: frozenset[tuple[str, str]] = frozenset({("smoke_exfiltration.py", "smoke_hooks")})


def _script_files() -> list[Path]:
    """Every script the walk reads: the `*.py` files and the launcher."""
    return [*sorted(SCRIPTS.glob("*.py")), SCRIPTS / "stayfixed"]


def _script_modules() -> frozenset[str]:
    """The names a script is importable under: the stems of the `*.py` files."""
    return frozenset(path.stem for path in SCRIPTS.glob("*.py"))


def _top_level_names(node: ast.Import | ast.ImportFrom) -> list[str]:
    """The top-level module names an import statement reaches for.

    A relative import has no package to be relative to in a script, so it names the module after
    its dots, or each imported name when there is none: `from . import smoke_hooks` reaches for
    `smoke_hooks` all the same.
    """
    if isinstance(node, ast.Import):
        return [alias.name.split(".")[0] for alias in node.names]
    if node.module is not None:
        return [node.module.split(".")[0]]
    return [alias.name.split(".")[0] for alias in node.names]


def _script_imports() -> set[tuple[str, str]]:
    """Every (file name, script module) pair an import statement in a script names."""
    modules = _script_modules()
    found: set[tuple[str, str]] = set()
    for path in _script_files():
        tree = ast.parse(path.read_text("utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import | ast.ImportFrom):
                found |= {(path.name, n) for n in _top_level_names(node) if n in modules}
    return found


def test_the_walk_reads_every_script() -> None:
    # A walk-based assertion states its walk is non-empty, and the launcher is in it.
    files = _script_files()
    assert len(files) > 5, files
    assert all(path.is_file() for path in files), files
    assert {"release", "plugin_tree", "smoke_hooks"} <= _script_modules()


def test_no_script_imports_another_but_the_named_exemption() -> None:
    # Mutation (oracle): `mutations/`'s "the release script imports the plugin tree script" ->
    # `release.py` imports a sibling and this reddens.
    offences = sorted(_script_imports() - EXEMPT)
    assert offences == []


def test_every_exemption_is_still_used() -> None:
    # Non-vacuous: the walk saw the exempt import, so an exemption whose import is gone reddens
    # here and is dropped rather than left to excuse a later one. Mutation (oracle): `mutations/`'s
    # "the exfiltration smoke stops importing the hooks smoke" -> this reddens, and the test above
    # stays green.
    found_imports = _script_imports()
    assert sorted(EXEMPT - found_imports) == []  # EXEMPT <= found_imports, naming what is gone
