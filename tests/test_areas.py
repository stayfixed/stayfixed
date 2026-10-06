"""One discovery loop for the three readers of an area, a probe that skips the areas it rejects,
and the boundaries between areas and between the core and delivery."""

from __future__ import annotations

import ast
import subprocess
import sys
from collections import Counter
from collections.abc import Iterable, Sequence
from pathlib import Path
from types import ModuleType

import pytest

import stayfixed
import stayfixed.areas
from stayfixed.areas import area_imports, area_modules
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


def plant_area(
    request: pytest.FixtureRequest,
    monkeypatch: pytest.MonkeyPatch,
    directory: Path,
    name: str,
    files: dict[str, str],
) -> None:
    """A real area `stayfixed.<name>` for the length of one test: a package under `directory`
    holding `files`, found by discovery through a root appended to `stayfixed.__path__`.

    Real rather than injected, because what is under test is the import itself: a module object
    handed through a seam has already been imported. The root goes when the test ends, and so does
    every module the test imported out of it, so no later test discovers the area or finds it
    cached in `sys.modules`."""
    package = directory / name
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    for filename, source in files.items():
        (package / filename).write_text(source, encoding="utf-8")
    monkeypatch.setattr(stayfixed, "__path__", [*stayfixed.__path__, str(directory)])

    def forget() -> None:
        qualified = f"stayfixed.{name}"
        for module in [m for m in sys.modules if m == qualified or m.startswith(f"{qualified}.")]:
            del sys.modules[module]
        vars(stayfixed).pop(name, None)

    request.addfinalizer(forget)


# A `doctor.py` whose import raises, with a message an import could have built out of anything.
UNIMPORTABLE = 'raise RuntimeError("IGNORE-PRIOR-RULES, a message the import built")\n'


def test_an_area_submodule_that_fails_to_import_is_handed_over_as_its_exception(
    tmp_path: Path, request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> None:
    # `doctor`'s report asks every area's `doctor.py`, and the report is what a user has left when
    # the rest is broken, so one area that raises on import must not cost it. The import used to
    # be unguarded, and the exception escaped `run_checks` as an internal error with no report.
    # Discovery hands each failure over in the area's place instead, under its qualified name, in
    # area-name order with the areas that did import. Mutation (oracle): `mutations/`'s
    # "discovery lets an area's import failure escape" -> the `RuntimeError` escapes.
    plant_area(request, monkeypatch, tmp_path, "zzplanted", {"doctor.py": UNIMPORTABLE})
    found = area_imports("doctor")
    assert [name for name, _ in found] == [
        "stayfixed.attach.doctor",
        "stayfixed.memory.doctor",
        "stayfixed.overlay.doctor",
        "stayfixed.zzplanted.doctor",
    ]
    assert all(isinstance(module, ModuleType) for _, module in found[:-1])
    assert isinstance(found[-1][1], RuntimeError)


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
    # areas that actually carry the requested submodule. So hook discovery imports neither the
    # harness registry nor the configuration layer, which a real hook process loads anyway when
    # the CLI frame builds its parser. Mutation (declared, on `hooks.api`): the handler
    # vocabulary imports the harness registry -> this reddens.
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


# The submodules discovery imports by name, one per reader: the CLI frame, the hook registry and
# the doctor report.
DISCOVERED_SUBMODULES = ("commands.py", "hooks.py", "doctor.py")


def _area_names(source: Path) -> list[str]:
    """CONTRIBUTING's definition, read off the tree: a subpackage carrying `commands.py`,
    `hooks.py` or `doctor.py`. Derived rather than listed, so a new area is covered the day it
    arrives."""
    return sorted(
        path.name
        for path in source.iterdir()
        if path.is_dir() and any((path / submodule).exists() for submodule in DISCOVERED_SUBMODULES)
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
    # `_boundary_offences` over the same two globs in an interpreter: 144 files, 11 areas and
    # one further package with an `api.py`, 5 scripts and 242 crossings, with a walk narrowed to
    # `commands.py` alone counting 9 under `src/` and 24 with the scripts — which is what the
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
# the importing file relative to `src/stayfixed/`, the module the statement names cut to three
# dotted parts, and the names it takes out of that module. Held as a multiset and by equality in
# both directions, so a new crossing reddens the test, and so do a row whose import has gone, a
# second statement beside a pinned one, and a pinned statement that takes one more name: the pardon
# covers exactly the statements and names written here, and cutting a crossing is deleting its rows
# in the same commit.
#
# One crossing is left, and it is meant to stay. `stayfixed setup --overlay` creates or records the
# private overlay as the last step of machine setup, so `setup/run.py` calls into the overlay area
# by design, and its rows stay until that step leaves `setup`: one statement in
# `_requested_overlay`, which refuses before the first write, and one in `_apply_overlay`, which
# creates and records. Both sit inside the functions, so importing `setup` — which `doctor` does —
# loads none of it (`test_in_isolation_no_core_module_loads_a_delivery_area`).
CORE_TO_DELIVERY = (
    (
        "setup/run.py",
        "stayfixed.overlay.api",
        frozenset({"require_overlay", "target_root"}),
    ),
    (
        "setup/run.py",
        "stayfixed.overlay.api",
        frozenset({"create", "init_instance", "overlay_fault", "require_overlay"}),
    ),
)

DeliveryRow = tuple[str, str, frozenset[str]]


def _delivery_offences(where: str, text: str, areas: frozenset[str]) -> list[DeliveryRow]:
    """The delivery rule, for one file: every import statement by which a core module reaches a
    delivery area, as `(where, module, names)` with the module cut to three dotted parts.

    One row per import statement, keyed on the module the statement names and never on its
    aliases: `_imported_modules` also yields `stayfixed.overlay.api.create` for every name a
    `from` imports, which would turn one import of four names into four rows. The names are the
    row's third part instead, as written, so a pardon is for one statement and what it takes; a
    statement that imports a module itself (`import stayfixed.overlay.api`) takes no names. The
    one spelling whose aliases are the modules is `from stayfixed import memory`, and it is read
    as such: a row per area, importing the area itself. A module is core when the first part of
    its path is not a delivery area, so `cli.py`, `config/` and every other subpackage that is not
    an area are core too. Delivery importing core, or delivery importing delivery, is not this
    rule's business.
    """
    parts = Path(where).parts
    core = parts[0] not in areas
    rows: list[DeliveryRow] = []
    for node in ast.walk(ast.parse(text)):
        if isinstance(node, ast.Import):
            taken = [(alias.name, frozenset[str]()) for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            # `_imported_modules` yields the statement's own module first, resolved when the
            # import is relative, and then one name per alias.
            module = _imported_modules(node, ("stayfixed", *parts[:-1]))[0][1]
            taken = [(module, frozenset(alias.name for alias in node.names))]
            if module == "stayfixed":
                taken = [(f"{module}.{alias.name}", frozenset[str]()) for alias in node.names]
        else:
            continue
        for module, names in taken:
            bits = module.split(".")
            delivery = bits[0] == "stayfixed" and len(bits) > 1 and bits[1] in areas
            if core and delivery:
                rows.append((where, ".".join(bits[:3]), names))
    return rows


def test_core_never_imports_delivery() -> None:
    # CONTRIBUTING, "Areas": the delivery areas may import the core, and the core may not import
    # them, through `api.py` or not, at module level or inside a function, but for the statements
    # `CORE_TO_DELIVERY` pins. The walk is the whole package, so the equality below also fails on
    # a walk that stopped walking: it would find no rows, and the pinned rows are never empty.
    #
    # Mutation (declared): `mutations/`'s "setup imports one more name from the overlay area in a
    # statement of its own", which a comparison of `(file, module)` sets let through.
    source = ROOT / "src" / "stayfixed"
    rows: list[DeliveryRow] = []
    for path in sorted(source.rglob("*.py")):
        rows += _delivery_offences(
            path.relative_to(source).as_posix(),
            path.read_text(encoding="utf-8"),
            stayfixed.areas.DELIVERY_AREAS,
        )
    assert len(CORE_TO_DELIVERY) == 2
    found, pinned = Counter(rows), Counter(CORE_TO_DELIVERY)
    assert found == pinned, {"unpinned": found - pinned, "gone": pinned - found}


# Imports every module it is handed, then prints every `stayfixed` module the interpreter loaded.
IMPORT_EACH = (
    "import importlib, sys\n"
    "for name in sys.argv[1:]:\n"
    "    importlib.import_module(name)\n"
    "print(' '.join(sorted(m for m in sys.modules if m.startswith('stayfixed'))))\n"
)


def _core_modules(source: Path) -> list[str]:
    """Every core module under `source`, dotted. `__main__` is left out because importing it runs
    the CLI: its whole body is `main()`."""
    names: list[str] = []
    for path in sorted(source.rglob("*.py")):
        relative = path.relative_to(source).with_suffix("")
        if relative.parts[0] in stayfixed.areas.DELIVERY_AREAS or relative.name == "__main__":
            continue
        dotted = ".".join(("stayfixed", *relative.parts))
        names.append(dotted.removesuffix(".__init__"))
    return names


def test_in_isolation_no_core_module_loads_a_delivery_area() -> None:
    # The source rule above reads statements, and a statement inside a function is pardoned there
    # because it is the pinned crossing. What it cannot see is when that statement runs: the
    # crossing stood at module level in `setup/run.py`, `setup/api.py` re-exports from that
    # module, and `doctor/entries.py` imported `setup.api` for `USER_SETTINGS` — so importing
    # `doctor`'s report loaded `overlay.api`, `overlay.create`, `memory.store` and the rest of the
    # private layer, with every rule green. So every core module is imported in one clean
    # interpreter, which loads the union of their import closures, and no delivery module may be
    # among what it loaded: the private layer is loaded by the core only when a command asks for
    # it, here `setup --overlay`.
    #
    # Mutation (declared): `mutations/`'s "setup loads the overlay area at import again".
    source = ROOT / "src" / "stayfixed"
    modules = _core_modules(source)
    # The walk names the modules the crossing reached, so a list that stopped holding them
    # cannot keep this green.
    assert {
        "stayfixed.cli",
        "stayfixed.doctor.api",
        "stayfixed.doctor.checks",
        "stayfixed.setup.api",
        "stayfixed.setup.run",
    } <= set(modules), modules
    completed = subprocess.run(
        [sys.executable, "-c", IMPORT_EACH, *modules],
        capture_output=True,
        text=True,
        check=False,
        env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(source.parent)},
    )
    assert completed.returncode == 0, completed.stderr
    loaded = completed.stdout.split()
    assert "stayfixed.doctor.checks" in loaded, "the probe imported nothing"
    delivery = [
        name
        for name in loaded
        if name.split(".")[1:2] and name.split(".")[1] in stayfixed.areas.DELIVERY_AREAS
    ]
    assert delivery == []


_FUNCTIONS = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)


def _type_checking(test: ast.expr) -> bool:
    """Whether an `if` tests `TYPE_CHECKING` itself, bare or as `typing.TYPE_CHECKING`."""
    if isinstance(test, ast.Name):
        return test.id == "TYPE_CHECKING"
    return (
        isinstance(test, ast.Attribute)
        and test.attr == "TYPE_CHECKING"
        and isinstance(test.value, ast.Name)
        and test.value.id == "typing"
    )


def _imports_run_on_import(nodes: Iterable[ast.AST]) -> list[ast.Import | ast.ImportFrom]:
    """Every import statement under `nodes` that runs when its module is imported: the whole
    tree, less what a function body holds and what the body of an `if TYPE_CHECKING:` holds. A
    class body, a `try`, a `with`, an `else` of `if TYPE_CHECKING:` and an `if` of any other test
    all run on import."""
    found: list[ast.Import | ast.ImportFrom] = []
    for node in nodes:
        if isinstance(node, _FUNCTIONS):
            continue
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            found.append(node)
        elif isinstance(node, ast.If) and _type_checking(node.test):
            found += _imports_run_on_import(node.orelse)
        else:
            found += _imports_run_on_import(ast.iter_child_nodes(node))
    return found


# The modules an area's `doctor.py` may import at module level: neither costs the report anything,
# and `typing` is what `TYPE_CHECKING` is read from, bare or as `typing.TYPE_CHECKING`.
MODULE_LEVEL = frozenset({"__future__", "typing"})


def _doctor_offences(where: str, tree: ast.AST) -> list[str]:
    """Every import that runs when `tree` is imported, as `where:line`, less those of
    `MODULE_LEVEL` modules alone, in either spelling (`from typing import …`, `import typing`)."""
    offences: list[str] = []
    for node in _imports_run_on_import([tree]):
        if isinstance(node, ast.ImportFrom) and node.module in MODULE_LEVEL:
            continue
        if isinstance(node, ast.Import) and all(a.name in MODULE_LEVEL for a in node.names):
            continue
        offences.append(f"{where}:{node.lineno}")
    return offences


def test_an_areas_doctor_module_imports_only_inside_its_functions() -> None:
    # CONTRIBUTING, "Areas": in an area's `doctor.py`, as in a `hooks.py`, every import sits
    # inside a function body. The module is imported by discovery, for every `doctor` run, so a
    # module-level import there is paid before the report has asked anything. Only `typing` and
    # what `TYPE_CHECKING` guards stand at module level. The walk is the whole tree, because a
    # walk of the top-level statements let an import nested in a `try` through, which runs on
    # import all the same. Mutations (oracle): `mutations/`'s "an area's doctor.py imports
    # stayfixed at module level" and "an area's doctor.py imports stayfixed at module level
    # inside a try".
    source = ROOT / "src" / "stayfixed"
    found = sorted(source.glob("*/doctor.py"))
    # The three delivery areas carry one each, and the walk says so before it judges them.
    assert [path.parent.name for path in found] == ["attach", "memory", "overlay"]
    offences: list[str] = []
    for path in found:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        offences += _doctor_offences(f"{path.parent.name}/doctor.py", tree)
    assert offences == []


def test_the_doctor_import_rule_reads_both_spellings_of_type_checking() -> None:
    # `if typing.TYPE_CHECKING:` needs a module-level `import typing`, which the rule once flagged,
    # so the guard's second spelling could never be used. Both spellings are allowed, and what
    # either guards; an `import typing` that carries any other module is not. Measured by hand:
    # dropping the `ast.Import` arm of `_doctor_offences` reddens the first assertion, and
    # dropping the `typing.TYPE_CHECKING` arm of `_type_checking` reddens it too.
    guarded = (
        "import typing\nif typing.TYPE_CHECKING:\n    from stayfixed.memory.store import Store\n"
        "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    import stayfixed.errors\n"
    )
    assert _doctor_offences("x.py", ast.parse(guarded)) == []
    carried = (
        "import typing, os\nimport os.path\nif typing.TYPE_CHECKING:\n    pass\n"
        "else:\n    import json\n"
    )
    assert _doctor_offences("x.py", ast.parse(carried)) == ["x.py:1", "x.py:2", "x.py:6"]


def test_the_delivery_areas_are_attach_memory_and_overlay() -> None:
    # The three areas CONTRIBUTING's "Areas" names as delivery, pinned as a literal rather than
    # read back: the crossing meant to stay exercises only `overlay`, so a change that dropped
    # `memory` or `attach` from the constant beside a new crossing into it would otherwise keep
    # `test_core_never_imports_delivery` green.
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
    ) == [("docs/commands.py", "stayfixed.memory", frozenset({"api"}))]
    assert _delivery_offences("memory/x.py", "import stayfixed.overlay.api\n", delivery) == []

    # The one spelling whose module is the package itself, so the area is in an alias: read by
    # alias, and only for that spelling. Mutation (declared): `mutations/`'s "the delivery rule
    # reads `from stayfixed import memory` as importing nothing".
    assert _delivery_offences("cli.py", "from stayfixed import ledger, memory\n", delivery) == [
        ("cli.py", "stayfixed.memory", frozenset())
    ]

    # Two statements naming one module are two rows, each with the names it takes, so a pardon
    # for one statement is never a pardon for a second one beside it. Mutation (declared):
    # `mutations/`'s "the delivery rule forgets which names a statement takes".
    two = "from stayfixed.overlay.api import create\nfrom stayfixed.overlay.api import create\n"
    assert _delivery_offences("setup/run.py", two, delivery) == [
        ("setup/run.py", "stayfixed.overlay.api", frozenset({"create"})),
        ("setup/run.py", "stayfixed.overlay.api", frozenset({"create"})),
    ]
    assert _delivery_offences(
        "setup/run.py", "from stayfixed.overlay.api import create, target_root\n", delivery
    ) == [("setup/run.py", "stayfixed.overlay.api", frozenset({"create", "target_root"}))]


# The two names through which a module is imported from a string rather than by a statement, which
# the delivery rule above reads no more than discovery's caller does.
DYNAMIC_IMPORTS = frozenset({"import_module", "__import__"})

# The one core module whose job is importing modules by name: discovery, which imports
# `stayfixed.<area>.<submodule>` for the submodules `area_modules` is called with (held below), and
# is how every area, delivery included, plugs into the core.
DISCOVERY_MODULE = "areas.py"

# Every other place a core module imports by a string, one row per reference: the file relative to
# `src/stayfixed/`, the innermost function, and the name it reaches. Held as a multiset and by
# equality in both directions, as `CORE_TO_DELIVERY` is.
#
# One row, meant to stay. `profiles/hints.py`'s `_hint` imports `stayfixed.profiles.<name>.hygiene`
# for a `name` that `hint_modules` listed from this package's own shipped profiles through
# `importlib.resources` — profile discovery, which CONTRIBUTING's "Areas" describes beside area
# discovery. It names no area and no repository path, so it is pinned here rather than moved into
# `areas.py`, which knows nothing of profiles.
DYNAMIC_IMPORTERS = (("profiles/hints.py", "_hint", "import_module"),)


def _dynamic_imports(tree: ast.AST) -> list[tuple[str, str]]:
    """Every reference in `tree` to `importlib.import_module` or `__import__`, as `(function,
    name)`, `function` being the innermost enclosing `def` or `<module>`.

    Read as: either name as an attribute of anything (`importlib.import_module`, the same through
    an alias of `importlib`, `builtins.__import__`), `__import__` by its bare name, any name a
    `from importlib import` binds either to, under its alias, that `from` statement itself and a
    `from importlib import *`, and either name as a string constant, which is how
    `getattr(importlib, "import_module")` spells it.
    """
    bound = {"__import__"} | {
        alias.asname or alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module == "importlib"
        for alias in node.names
        if alias.name in DYNAMIC_IMPORTS
    }
    found: list[tuple[str, str]] = []

    def visit(node: ast.AST, function: str) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.Attribute) and child.attr in DYNAMIC_IMPORTS:
                found.append((function, child.attr))
            elif isinstance(child, ast.Name) and child.id in bound:
                found.append((function, child.id))
            elif isinstance(child, ast.Constant) and child.value in DYNAMIC_IMPORTS:
                found.append((function, str(child.value)))
            elif (
                isinstance(child, ast.ImportFrom)
                and child.module == "importlib"
                and any(alias.name in DYNAMIC_IMPORTS | {"*"} for alias in child.names)
            ):
                found.append((function, "from importlib import"))
            inner = function
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                inner = child.name
            visit(child, inner)

    visit(tree, "<module>")
    return found


def _core_files(source: Path) -> list[tuple[str, Path]]:
    """Every core file under `source`, relative to it: each module outside the delivery areas,
    `cli.py` and the subpackages that are not areas included."""
    return [
        (path.relative_to(source).as_posix(), path)
        for path in sorted(source.rglob("*.py"))
        if path.relative_to(source).parts[0] not in stayfixed.areas.DELIVERY_AREAS
    ]


def test_no_core_module_imports_by_a_string_but_discovery() -> None:
    # The delivery rule reads import statements, so a function-level
    # `importlib.import_module("stayfixed.memory.store")` or `__import__(...)` in a core file
    # crossed into the private layer with every boundary test green. A string import in the core
    # is discovery's alone, and the one other one — profile discovery — is pinned with its reason.
    # This reads the two names; the standard library's other ways to import by a string are held
    # where they must be imported from, by `test_no_core_module_reaches_the_import_machinery_…`.
    #
    # Mutations (declared): `mutations/`'s "a core function imports the note store through
    # importlib", "a core function imports the note store through __import__" and "a core function
    # imports the note store through an alias of import_module".
    source = ROOT / "src" / "stayfixed"
    rows: list[tuple[str, str, str]] = []
    discovery: list[tuple[str, str]] = []
    for where, path in _core_files(source):
        found = _dynamic_imports(ast.parse(path.read_text(encoding="utf-8")))
        if where == DISCOVERY_MODULE:
            discovery += found
        else:
            rows += [(where, function, name) for function, name in found]
    # The walk reads discovery's own `importlib.import_module`, so a reader that stopped seeing
    # the spelling the pardon is written in cannot keep the equality below green by finding nothing.
    assert ("area_modules", "import_module") in discovery, discovery
    found_rows, pinned = Counter(rows), Counter(DYNAMIC_IMPORTERS)
    assert found_rows == pinned, {"unpinned": found_rows - pinned, "gone": pinned - found_rows}


# The standard modules that import a module named by a string without either name the rule above
# reads: `pkgutil.resolve_name`, `importlib.util`'s `find_spec` and `module_from_spec` with a
# loader's `exec_module`, `runpy`'s `run_module` and `run_path`, a `zipimporter`. Reading every
# such function by name is a list that grows with the standard library, so the rule below reads
# the door instead: which core files import these modules at all, and what each reaches in them.
# `importlib.resources` reads package data and imports nothing, so it is outside the rule.
MACHINERY = frozenset({"importlib", "pkgutil", "runpy", "zipimport"})
DATA_ONLY = "importlib.resources"

# Every core import of `MACHINERY`, one row per statement: the file relative to `src/stayfixed/`,
# the module the statement names, and what the file reaches through it -- the names a `from`
# statement takes, or each attribute path read off the name an `import` binds (`<value>` when the
# name itself is handed on, where anything could be read off it). Held as a multiset and by
# equality in both directions, as `DYNAMIC_IMPORTERS` is.
MACHINERY_IMPORTERS = (
    # Discovery: imports `stayfixed.<area>.<submodule>` by name, and lists the areas.
    ("areas.py", "importlib", frozenset({"import_module"})),
    ("areas.py", "pkgutil", frozenset({"iter_modules"})),
    # Profile discovery: imports `stayfixed.profiles.<name>.hygiene`, pinned in `DYNAMIC_IMPORTERS`.
    ("profiles/hints.py", "importlib", frozenset({"import_module"})),
    # Reads the running interpreter's bytecode magic, the first four bytes of every `.pyc` it would
    # open; it imports nothing.
    ("profiles/python/hygiene.py", "importlib.util", frozenset({"util.MAGIC_NUMBER"})),
)


def _attribute_path(node: ast.AST, parents: dict[int, ast.AST]) -> str:
    """The dotted attributes read off the name `node`, outermost last (`util.MAGIC_NUMBER` for
    `importlib.util.MAGIC_NUMBER`), or `<value>` when the name is used as anything but the root
    of an attribute read."""
    path: list[str] = []
    while isinstance(parent := parents.get(id(node)), ast.Attribute) and parent.value is node:
        path.append(parent.attr)
        node = parent
    return ".".join(path) or "<value>"


def _machinery_imports(tree: ast.AST) -> list[tuple[str, frozenset[str]]]:
    """Every statement in `tree` that imports a `MACHINERY` module other than `DATA_ONLY`, as
    `(module, reach)`: for `from m import a, b` the names taken (`resources` dropped from
    `from importlib import`), for `import m.n [as x]` every attribute path read off the name it
    binds, anywhere in the file."""
    parents = {id(child): node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
    found: list[tuple[str, frozenset[str]]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and not node.level and node.module:
            module = node.module
            if module.split(".")[0] not in MACHINERY or module.startswith(DATA_ONLY):
                continue
            names = {alias.name for alias in node.names}
            if module == "importlib":
                names -= {"resources"}
            if names:
                found.append((module, frozenset(names)))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] not in MACHINERY:
                    continue
                data_only = alias.name.startswith(DATA_ONLY)
                if data_only and alias.asname:
                    continue
                bound = alias.asname or alias.name.split(".")[0]
                reach = {
                    _attribute_path(name, parents)
                    for name in ast.walk(tree)
                    if isinstance(name, ast.Name) and name.id == bound
                }
                # `import importlib.resources` binds `importlib` itself, and what is read off it
                # past `resources` is the machinery all the same.
                if data_only:
                    reach = {path for path in reach if path.split(".")[0] != "resources"}
                    if not reach:
                        continue
                found.append((alias.name, frozenset(reach)))
    return found


def test_no_core_module_reaches_the_import_machinery_but_where_pinned() -> None:
    # The rule above reads two names, and `pkgutil.resolve_name("stayfixed.memory.store")`, or
    # `importlib.util.find_spec` and a loader's `exec_module`, in a core function crossed into the
    # private layer with every boundary test green. So the core's imports of the modules that
    # can import by name are pinned, each with what it reaches: a new importer is a new row, and
    # a pinned importer reaching one more name changes its row. What stays unread is a module
    # reached without an import statement of its own -- `__import__`, which the rule above
    # reads, or `sys.modules` -- and code built from text, which no rule here reads.
    #
    # Mutations (declared): `mutations/`'s "a core function imports the note store through
    # pkgutil.resolve_name" and "profile discovery reaches importlib.util as well".
    source = ROOT / "src" / "stayfixed"
    rows = [
        (where, module, reach)
        for where, path in _core_files(source)
        for module, reach in _machinery_imports(ast.parse(path.read_text(encoding="utf-8")))
    ]
    found_rows, pinned = Counter(rows), Counter(MACHINERY_IMPORTERS)
    assert found_rows == pinned, {"unpinned": found_rows - pinned, "gone": pinned - found_rows}


def test_the_machinery_rule_reads_every_spelling() -> None:
    # The walk above can show the rule holding only for the spellings the tree carries, so it is
    # put in front of the ones it does not: a `from` import of a submodule, an aliased `import`,
    # the name handed on as a value, and `importlib.resources` in each spelling left alone, though
    # not what is read off the `importlib` its `import` binds. Measured by hand: dropping the
    # `resources` subtraction, the `<value>` fallback, or that filter each reddens it.
    spellings = (
        "from importlib import resources\nfrom importlib.resources.abc import Traversable\n"
        "import importlib.resources\nimportlib.resources.files('x')\n"
        "importlib.import_module('x')\nfrom importlib import resources, util\n"
        "from importlib.util import find_spec\nimport pkgutil as p\np.resolve_name('x')\n"
        "import runpy\nf(runpy)\nrunpy.run_module('x')\n"
    )
    assert sorted(_machinery_imports(ast.parse(spellings)), key=str) == sorted(
        [
            ("importlib.resources", frozenset({"import_module"})),
            ("importlib", frozenset({"util"})),
            ("importlib.util", frozenset({"find_spec"})),
            ("pkgutil", frozenset({"resolve_name"})),
            ("runpy", frozenset({"<value>", "run_module"})),
        ],
        key=str,
    )


# The two functions through which discovery imports `stayfixed.<area>.<submodule>`: the one the CLI
# frame and the hook registry ask, which lets an import failure raise, and the one `doctor` asks,
# which hands it back so it costs one row.
DISCOVERY_FUNCTIONS = frozenset({"area_modules", "area_imports"})


def _area_module_offences(where: str, tree: ast.AST, allowed: frozenset[str]) -> list[str]:
    """Every reference to a discovery function in `tree` that is not a call with one literal
    argument out of `allowed`: a call naming any other submodule, a computed argument, and the
    function handed on as a value, which would call it out of sight. Read by any name a `from …
    import` binds it to and as an attribute of anything (`stayfixed.areas.area_modules`)."""
    bound = set(DISCOVERY_FUNCTIONS) | {
        alias.asname
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
        if alias.name in DISCOVERY_FUNCTIONS and alias.asname
    }
    literal: set[int] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and not node.keywords
            and len(node.args) == 1
            and isinstance(node.args[0], ast.Constant)
            and node.args[0].value in allowed
        ):
            literal.add(id(node.func))
    lines = [
        node.lineno
        for node in ast.walk(tree)
        if (
            (isinstance(node, ast.Name) and node.id in bound)
            or (isinstance(node, ast.Attribute) and node.attr in DISCOVERY_FUNCTIONS)
        )
        and id(node) not in literal
    ]
    return [f"{where}:{line}" for line in sorted(lines)]


def test_discovery_is_asked_only_for_the_submodules_it_names() -> None:
    # `area_modules` and `area_imports` import `stayfixed.<area>.<submodule>` for every area that
    # has one, so a core caller asking for `"api"` loads every area's surface, the private layer's
    # included, through the one door the delivery rule leaves open. Every call under
    # `src/stayfixed/` names one of the three submodules discovery is for, as a literal.
    #
    # Mutation (declared): `mutations/`'s "a core module asks discovery for every area's api.py".
    source = ROOT / "src" / "stayfixed"
    allowed = frozenset(name.removesuffix(".py") for name in DISCOVERED_SUBMODULES)
    offences: list[str] = []
    asked: set[str] = set()
    for path in sorted(source.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        offences += _area_module_offences(path.relative_to(source).as_posix(), tree, allowed)
        asked |= {
            str(node.args[0].value)
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in DISCOVERY_FUNCTIONS
            and node.args
            and isinstance(node.args[0], ast.Constant)
        }
    assert offences == []
    # Each reader's call was seen, so a walk that stopped finding calls cannot pass by finding
    # no offence.
    assert asked == {"commands", "hooks", "doctor"}


def test_the_string_import_rules_read_every_spelling() -> None:
    # The walks above can only show the rules holding for the spellings the tree carries, so they
    # are put in front of the ones it does not. Measured by hand: reading `from importlib import`
    # aliases no more reddens the first assertion, dropping the string-constant arm the second,
    # and dropping the attribute arm of `_area_module_offences` the third.
    aliased = "from importlib import import_module as load\ndef f():\n    load('x')\n"
    assert _dynamic_imports(ast.parse(aliased)) == [
        ("<module>", "from importlib import"),
        ("f", "load"),
    ]
    reflected = "import importlib\ndef f():\n    getattr(importlib, 'import_module')('x')\n"
    assert _dynamic_imports(ast.parse(reflected)) == [("f", "import_module")]
    allowed = frozenset({"commands", "hooks", "doctor"})
    spellings = (
        "import stayfixed.areas\nstayfixed.areas.area_modules('api')\n"
        "from stayfixed.areas import area_modules as found\nfound(name)\nkept = found\n"
        "found('hooks')\n"
        "from stayfixed.areas import area_imports\narea_imports('api')\narea_imports('doctor')\n"
    )
    assert _area_module_offences("x.py", ast.parse(spellings), allowed) == [
        "x.py:2",
        "x.py:4",
        "x.py:5",
        "x.py:8",
    ]
