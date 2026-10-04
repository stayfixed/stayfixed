"""One discovery loop for both registries, and a probe that skips the areas it rejects."""

from __future__ import annotations

import ast
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

import stayfixed.areas
from stayfixed.areas import area_modules
from stayfixed.cli import discover_registrars

ROOT = Path(__file__).resolve().parents[1]
LIST_IMPORTS = (
    "import sys\n"
    "from stayfixed.hooks.registry import discover\n"
    "discover()\n"
    "print(' '.join(sorted(m for m in sys.modules if m.startswith('stayfixed'))))\n"
)


def test_commands_modules_are_found_in_area_name_order() -> None:
    names = [module.__name__ for module in area_modules("commands")]
    assert names == sorted(names)
    assert "stayfixed.hooks.commands" in names
    assert "stayfixed.doctor.commands" in names


def test_the_runner_is_a_leaf_and_not_an_area() -> None:
    # `runner.py` is a leaf: it sits beside `fsops.py`, `gitenv.py` and `tomlout.py` and imports
    # nothing from `stayfixed`. Pinned as an import check rather than by walking the tree, because
    # the tree walk above treats a leaf as invisible on purpose. No mutation: adding a stayfixed
    # import to a leaf is a review finding the import-boundary test does not catch, and this is the
    # one line that does.
    import ast
    from pathlib import Path

    source = Path(__file__).resolve().parents[1] / "src" / "stayfixed" / "runner.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    imported = [
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module
    ] + [
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    ]
    # The walk states it is non-empty first: an `imported` that came back empty — a parse that
    # found no imports at all, or a filter that stopped matching — satisfies the filter below
    # without reading a single name. `runner.py` imports five stdlib modules.
    assert imported
    assert not [name for name in imported if name.startswith("stayfixed")], imported


def test_the_cli_registry_reads_the_same_discovery_as_the_helper() -> None:
    assert [registrar.__module__ for registrar in discover_registrars()] == [
        module.__name__ for module in area_modules("commands")
    ]


def test_in_isolation_an_area_with_no_such_submodule_is_never_imported() -> None:
    # Deliberately isolates `discover()` from the CLI frame: the subprocess never calls
    # `discover_registrars()`, so nothing has imported the area packages beforehand. Production
    # is not this shape — `main()` runs `discover_registrars()` first, which already imports
    # every area's `commands` submodule before `hook` ever reaches this probe — but the helper's
    # own behaviour still holds here: given a clean interpreter, `area_modules` imports only the
    # areas that actually carry the requested submodule.
    completed = subprocess.run(
        [sys.executable, "-c", LIST_IMPORTS],
        capture_output=True,
        text=True,
        check=False,
        env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(ROOT / "src")},
    )
    assert completed.returncode == 0, completed.stderr
    imported = completed.stdout.split()
    assert "stayfixed.hooks.registry" in imported
    assert "stayfixed.release" not in imported
    assert "stayfixed.config" not in imported
    assert "stayfixed.presets" not in imported
    assert "stayfixed.profiles" not in imported
    assert "stayfixed.harnesses" not in imported


# The eleven areas CONTRIBUTING lists, and the one departure from the rule below. `cli.py` is the
# CLI frame and not an area — nothing discovers it, it has no `api.py`, and it owns the wiring
# of the `hook` command — so it reads `stayfixed.hooks.policy` directly. It is named here rather
# than skipped silently, because an exemption nobody can see is how the two violations this
# guard exists to catch were merged green.
SURFACE_EXEMPT = frozenset({("cli.py", "stayfixed.hooks.policy")})


def _area_names(source: Path) -> list[str]:
    """CONTRIBUTING's definition, read off the tree: a subpackage carrying `commands.py` or
    `hooks.py`. Derived rather than listed, so a new area is covered the day it arrives."""
    return sorted(
        path.name
        for path in source.iterdir()
        if path.is_dir() and ((path / "commands.py").exists() or (path / "hooks.py").exists())
    )


def _ruled_packages(source: Path) -> list[str]:
    """Every subpackage the import rule holds: each area, and each package that publishes an
    `api.py` whether or not anything discovers it.

    Discovery is how the CLI finds a command; the rule is about the surface. A package with an
    `api.py` and no `commands.py` (`release`) is held to that surface all the same, and an area
    with no `api.py` (`assess`) publishes nothing, so nothing outside it may import any of its
    modules."""
    surfaces = {path.parent.name for path in source.glob("*/api.py")}
    return sorted(set(_area_names(source)) | surfaces)


def _imported_modules(tree: ast.AST, package: tuple[str, ...]) -> list[tuple[int, str]]:
    """Every module name this file imports, as an absolute dotted name.

    Three spellings, and the third is the one this guard shipped without seeing.
    `from stayfixed.memory.api import X` and `import stayfixed.memory.api` are the obvious one;
    `from stayfixed.memory import worktree` is the one a rule that looked only at `node.module`
    would miss, and it reaches a private module just as squarely.

    **The third is the relative import**, and it used to be dropped on the floor: the condition
    read `and not node.level`, so `from ..hooks.sink import DIRECTORY` inside `doctor/checks.py`
    — the violation this guard exists to end, spelled the other way — walked straight past. There
    are no relative imports under `src/stayfixed/` today, but only by house style: ruff's `TID`
    rules are not selected, so nothing bans one, and the first contributor to write an idiomatic
    one would have reopened the boundary with the guard still green.

    Resolved rather than refused, so this test answers the question it is named for — does this
    import reach past an `api.py` — in whatever spelling, instead of imposing a second rule the
    project has not made. `level` counts the leading dots: one means this module's own package,
    and each further dot strips one component off it.
    """
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found += [(node.lineno, alias.name) for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = package[: len(package) - (node.level - 1)]
                # A relative import that climbs above `stayfixed` is a module Python could not
                # import at all; it must fail here rather than resolve to something shorter.
                assert base, f"line {node.lineno}: a relative import above the package root"
                prefix = ".".join((*base, *(node.module.split(".") if node.module else ())))
            else:
                assert node.module is not None
                prefix = node.module
            found.append((node.lineno, prefix))
            found += [(node.lineno, f"{prefix}.{alias.name}") for alias in node.names]
    return found


def _boundary_offences(where: str, text: str, ruled: Sequence[str]) -> tuple[list[str], list[str]]:
    """The rule, for one file: the imports it makes into a `ruled` package other than its own, and
    the ones that break it. `ruled` is every package the surface rule holds — each area, and each
    package that publishes an `api.py`.

    A function rather than a loop body, so the test below can put a spelling in front of it that
    `src/stayfixed/` does not currently contain. A guard whose rule can only be exercised by the
    tree it walks cannot be shown to hold for anything the tree does not happen to do.
    """
    parts = Path(where).parts
    here = parts[0] if len(parts) > 1 else None
    crossings: list[str] = []
    offences: list[str] = []
    for line, module in _imported_modules(ast.parse(text), ("stayfixed", *parts[:-1])):
        bits = module.split(".")
        if len(bits) < 3 or bits[0] != "stayfixed" or bits[1] not in ruled or bits[1] == here:
            continue
        crossings.append(f"{where} -> {module}")
        if bits[2] == "api" or (where, ".".join(bits[:3])) in SURFACE_EXEMPT:
            continue
        offences.append(f"{where}:{line} imports {module}")
    return crossings, offences


def test_no_module_reaches_into_another_packages_private_module() -> None:
    # CONTRIBUTING: "`api.py` is the area's import surface. Other areas import from it and from
    # nothing else." Nothing asserted it, and an external review found the first two violations
    # in this repository's history — `memory/commands.py` importing `hooks.dispatch` and
    # `doctor/checks.py` importing `hooks.sink` — both merged green.
    #
    # Three mutations in `mutations/`: "an area reaches past another area's api.py again" puts a
    # violation back (doctor reading the setup area's private `machine` module); "the cross-area
    # import guard walks ten files instead of the package" narrows the walk, because a guard that
    # silently stops walking reports no offences for the same reason a guard with nothing to
    # report does; and "the boundary rule ignores a relative import again" breaks the resolution
    # of a relative import — the test below is the one that holds that spelling, because this
    # walk has none to find.
    source = ROOT / "src" / "stayfixed"
    areas = _area_names(source)
    ruled = _ruled_packages(source)
    files = sorted(source.rglob("*.py"))
    # `scripts/` is walked too, and the reason is the violation that merged green under a walk
    # that was not: `scripts/check_artifacts.py` imported `stayfixed.overlay.layout` for the very
    # constant `overlay/api.py`'s docstring said had been trimmed *because* nothing outside the
    # area imported it. A walk one directory narrower than the code that can break the rule is a
    # walk that will eventually report nothing. The script paths are relative to `ROOT` rather
    # than to `source`, so `here` is `scripts` — not an area, so every stayfixed import a script
    # makes is a crossing and has to go through an `api.py`.
    scripts = sorted((ROOT / "scripts").glob("*.py"))
    crossings: list[str] = []
    offences: list[str] = []
    for path in files:
        found, broken = _boundary_offences(
            str(path.relative_to(source)), path.read_text(encoding="utf-8"), ruled
        )
        crossings += found
        offences += broken
    for path in scripts:
        found, broken = _boundary_offences(
            str(path.relative_to(ROOT)), path.read_text(encoding="utf-8"), ruled
        )
        crossings += found
        offences += broken
    # The walk is asserted before anything is asserted about it. Both floors are well under
    # today's numbers and are there to fail on a walk that stopped walking, not to be kept
    # current. Re-measured 2026-10-04, by running this module's own `_ruled_packages` and
    # `_boundary_offences` over the same two globs in an interpreter: 138 files, 11 areas and
    # one further package with an `api.py`, 5 scripts and 210 crossings, with a walk narrowed to
    # `commands.py` alone counting 11 under `src/` and 26 with the scripts — which is what the
    # crossings floor of 60 has to be below.
    assert len(areas) == 11, areas
    # The packages held to a surface without being discovered, pinned by name for the reason
    # `tests/test_surfaces.py` pins its list: gaining or losing one is a decision.
    assert sorted(set(ruled) - set(areas)) == ["release"], ruled
    assert len(files) >= 70, len(files)
    # The script walk's own floor: without it a `glob` that stopped matching would take the
    # `scripts/` half of this guard back to the state that hid the violation, and the crossing
    # count below has enough headroom to absorb the loss.
    assert len(scripts) >= 3, scripts
    assert len(crossings) >= 60, crossings
    # The exemption itself, in both directions. Nothing asserted its size, so a second entry
    # could be added and no test would move — measured, with the historical violation
    # `("memory/commands.py", "stayfixed.hooks.dispatch")` added to it: 6 passed, because
    # `crossings` still counts the crossing and only the offence is suppressed. And nothing
    # asserted the one crossing it names is still real, so the exemption would outlive the
    # import it excuses.
    #
    # Mutation (declared): a second live crossing joins the exemption.
    assert len(SURFACE_EXEMPT) == 1, sorted(SURFACE_EXEMPT)
    for where, module in SURFACE_EXEMPT:
        assert f"{where} -> {module}" in crossings, (where, module)
    assert not offences, "a module reached past another package's api.py:\n" + "\n".join(offences)


def test_the_boundary_rule_resolves_a_relative_import_before_judging_it() -> None:
    # The hole the guard above shipped with, and the reason it needs a test of its own: there is
    # not one relative import under `src/stayfixed/`, so the walk cannot exercise this spelling
    # and a synthetic module has to. `from ..hooks.sink import DIRECTORY` inside
    # `doctor/checks.py` is the violation this whole guard exists to end, written the way a
    # contributor who prefers relative imports would write it.
    #
    # Asserted as the exact offence rather than as "some offence": a rule that resolved the
    # module to any other name would also produce a non-empty list, from the wrong reading.
    ruled = ["doctor", "hooks", "memory", "setup"]
    crossings, offences = _boundary_offences(
        "doctor/checks.py", "from ..hooks.sink import DIRECTORY\n", ruled
    )
    assert offences == [
        "doctor/checks.py:1 imports stayfixed.hooks.sink",
        "doctor/checks.py:1 imports stayfixed.hooks.sink.DIRECTORY",
    ]
    assert crossings == [
        "doctor/checks.py -> stayfixed.hooks.sink",
        "doctor/checks.py -> stayfixed.hooks.sink.DIRECTORY",
    ]

    # The published spelling of the same import, relatively: a crossing and not an offence. This
    # is the arm that fails if the rule is made to refuse every relative import rather than read
    # it, which is the other repair this could have had.
    crossings, offences = _boundary_offences(
        "doctor/checks.py", "from ..hooks.api import DIRECTORY\n", ruled
    )
    assert crossings == [
        "doctor/checks.py -> stayfixed.hooks.api",
        "doctor/checks.py -> stayfixed.hooks.api.DIRECTORY",
    ]
    assert not offences

    # And an area's own modules, reached relatively, are its own business at any depth — a
    # module's package is itself for one dot, and `from . import x` carries no module at all.
    crossings, offences = _boundary_offences(
        "doctor/checks.py", "from .checks import OK\nfrom . import commands\n", ruled
    )
    assert (crossings, offences) == ([], [])


def test_a_package_that_publishes_an_api_py_is_held_to_it_without_being_an_area() -> None:
    # An area is how the CLI and the hook registry find code; the surface rule is about
    # `api.py`. `release` publishes one and carries neither `commands.py` nor `hooks.py`, so
    # while the rule was keyed on discovery alone, a reach past its surface — from a module
    # under `src/` or from a script — was not even a crossing. Read off the tree rather than
    # with a hand-picked list, so the probe is of the set the walk above actually uses.
    source = ROOT / "src" / "stayfixed"
    assert "release" not in _area_names(source)
    ruled = _ruled_packages(source)

    crossings, offences = _boundary_offences(
        "doctor/checks.py", "from stayfixed.release.hashes import digests\n", ruled
    )
    assert offences == [
        "doctor/checks.py:1 imports stayfixed.release.hashes",
        "doctor/checks.py:1 imports stayfixed.release.hashes.digests",
    ]
    crossings, offences = _boundary_offences(
        "scripts/release.py", "from stayfixed.release.hashes import write_record\n", ruled
    )
    assert offences == [
        "scripts/release.py:1 imports stayfixed.release.hashes",
        "scripts/release.py:1 imports stayfixed.release.hashes.write_record",
    ]

    # The published spelling is a crossing and not an offence: the arm that fails if the
    # package is refused outright instead of being held to its surface.
    crossings, offences = _boundary_offences(
        "scripts/release.py", "from stayfixed.release.api import digests\n", ruled
    )
    assert crossings == [
        "scripts/release.py -> stayfixed.release.api",
        "scripts/release.py -> stayfixed.release.api.digests",
    ]
    assert not offences


# Every import by which a core module reaches a delivery area today, one row per import statement:
# the importing file relative to `src/stayfixed/`, and the module it names cut to three dotted
# parts. Held by equality in both directions, so a new crossing reddens the test and so does a row
# whose import has gone: the set never carries a pardon for an import that no longer exists, and
# cutting a crossing is deleting its row in the same commit.
#
# One crossing is meant to outlive the rest. `stayfixed setup --overlay` creates or records the
# private overlay as the last step of machine setup, so `setup/run.py` calls into the overlay area
# by design, and the row stays until that step leaves `setup`.
CORE_TO_DELIVERY = frozenset(
    {
        ("assess/rule.py", "stayfixed.overlay.api"),
        ("docs/commands.py", "stayfixed.memory.api"),
        ("docs/graph.py", "stayfixed.memory.api"),
        ("doctor/checks.py", "stayfixed.attach.api"),
        ("doctor/checks.py", "stayfixed.memory.api"),
        ("doctor/checks.py", "stayfixed.overlay.api"),
        ("project/detect.py", "stayfixed.memory.api"),
        ("project/questions.py", "stayfixed.memory.api"),
        ("project/templates.py", "stayfixed.attach.api"),
        ("project/uninstall.py", "stayfixed.attach.api"),
        ("project/upgrade.py", "stayfixed.overlay.api"),
        ("setup/run.py", "stayfixed.overlay.api"),
    }
)


def _delivery_offences(where: str, text: str, areas: frozenset[str]) -> list[tuple[str, str]]:
    """The delivery rule, for one file: every import by which a core module reaches a delivery
    area, as `(where, module)` with the module cut to three dotted parts.

    One row per import statement, keyed on the module the statement names and never on its
    aliases: `_imported_modules` also yields `stayfixed.memory.api.WIKI_LINK` for every name a
    `from` imports, which would turn one import of sixteen names into sixteen rows. The one
    spelling whose aliases are the modules is `from stayfixed import memory`, and it is read as
    such. A module is core when the first part of its path is not a delivery area, so `cli.py`,
    `config/` and every other subpackage that is not an area are core too. Delivery importing
    core, or delivery importing delivery, is not this rule's business.
    """
    parts = Path(where).parts
    core = parts[0] not in areas
    rows: list[tuple[str, str]] = []
    for node in ast.walk(ast.parse(text)):
        if isinstance(node, ast.Import):
            modules = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            # `_imported_modules` yields the statement's own module first, resolved when the
            # import is relative, and then one name per alias.
            module = _imported_modules(node, ("stayfixed", *parts[:-1]))[0][1]
            modules = [module]
            if module == "stayfixed":
                modules = [f"{module}.{alias.name}" for alias in node.names]
        else:
            continue
        for module in modules:
            bits = module.split(".")
            delivery = bits[0] == "stayfixed" and len(bits) > 1 and bits[1] in areas
            if core and delivery:
                rows.append((where, ".".join(bits[:3])))
    return rows


def test_core_never_imports_delivery() -> None:
    # CONTRIBUTING, "Areas": the delivery areas may import the core, and the core never imports
    # them, through `api.py` or not, at module level or inside a function. The walk is the whole
    # package, so the equality below also fails on a walk that stopped walking: it would find no
    # rows, and the pinned set is never empty.
    source = ROOT / "src" / "stayfixed"
    rows: list[tuple[str, str]] = []
    for path in sorted(source.rglob("*.py")):
        rows += _delivery_offences(
            path.relative_to(source).as_posix(),
            path.read_text(encoding="utf-8"),
            stayfixed.areas.DELIVERY_AREAS,
        )
    assert len(CORE_TO_DELIVERY) == 12
    assert set(rows) == CORE_TO_DELIVERY, sorted(set(rows) ^ CORE_TO_DELIVERY)


def test_the_delivery_areas_are_the_three_the_design_names() -> None:
    # Pinned as a literal rather than read back: the crossing meant to stay exercises only
    # `overlay`, so a change that dropped `memory` or `attach` from the constant beside a new
    # crossing into it would otherwise keep `test_core_never_imports_delivery` green.
    #
    # Mutation (declared): `mutations/`'s "memory stops being a delivery area".
    declared = stayfixed.areas.DELIVERY_AREAS
    assert declared == frozenset({"attach", "memory", "overlay"})


def test_the_delivery_rule_judges_the_importer_and_the_imported() -> None:
    # The walk above can only show the rule holding for the imports the tree happens to make, so
    # the rule is put in front of spellings the tree does not carry. A core module reaching a
    # delivery area relatively and from inside a function is an offence, named exactly; a
    # delivery module reaching another delivery area is not, because only the core is held.
    #
    # Mutations (declared): `mutations/`'s "the delivery rule stops recognising a delivery
    # module", which reddens the first arm, and "the delivery rule holds a delivery module to the
    # core's rule", which reddens the second.
    delivery = frozenset({"attach", "memory", "overlay"})
    assert _delivery_offences(
        "docs/commands.py", "def check():\n    from ..memory import api\n", delivery
    ) == [("docs/commands.py", "stayfixed.memory")]
    assert _delivery_offences("memory/x.py", "import stayfixed.overlay.api\n", delivery) == []

    # The one spelling whose module is the package itself, so the area is in an alias: read by
    # alias, and only for that spelling. Mutation (declared): `mutations/`'s "the delivery rule
    # reads `from stayfixed import memory` as importing nothing".
    assert _delivery_offences("cli.py", "from stayfixed import ledger, memory\n", delivery) == [
        ("cli.py", "stayfixed.memory")
    ]
