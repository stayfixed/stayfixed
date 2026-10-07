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


def _package_imports(where: str, text: str, packages: frozenset[str]) -> set[tuple[str, str]]:
    """The package graph's edges one file gives: `(its package, a package it imports)` for every
    import statement that runs when the file is imported (`_imports_run_on_import`), to a package
    out of `packages` other than its own. A package is a subpackage or a module directly under
    `src/stayfixed/`, named by its first path component."""
    parts = Path(where).parts
    importer = parts[0].removesuffix(".py")
    edges: set[tuple[str, str]] = set()
    for node in _imports_run_on_import([ast.parse(text)]):
        for _, module in _imported_modules(node, ("stayfixed", *parts[:-1])):
            bits = module.split(".")
            if bits[0] == "stayfixed" and bits[1:2] and bits[1] in packages - {importer}:
                edges.add((importer, bits[1]))
    return edges


def _cycles(edges: set[tuple[str, str]]) -> list[list[str]]:
    """Every strongly connected component of more than one package, each sorted, in sorted
    order: the packages that import one another, directly or around a longer loop."""
    after: dict[str, set[str]] = {}
    for importer, imported in edges:
        after.setdefault(importer, set()).add(imported)

    def reachable(start: str) -> set[str]:
        seen: set[str] = set()
        pending = [start]
        while pending:
            for following in after.get(pending.pop(), set()) - seen:
                seen.add(following)
                pending.append(following)
        return seen

    reach = {package: reachable(package) for package in sorted(after)}
    components = {
        frozenset(
            {package} | {other for other in reach if package in reach[other] and other in found}
        )
        for package, found in reach.items()
    }
    return sorted(sorted(component) for component in components if len(component) > 1)


def test_the_packages_import_one_another_without_a_cycle_at_module_level() -> None:
    # Two package cycles stood in the tree: the session guard imported the profiles' hint
    # machinery while the Python profile's hint imported the guard's roots, and the configuration
    # loader printed through `findings`, which printed through `printed`, which read its grammar
    # from the configuration's schema. Neither failed an import, because each was entered from
    # one side only, so nothing said so until a review drew the graph.
    #
    # What is counted is an import that runs when its module is imported -- the same reading the
    # doctor rule above makes: module level, a class body, a `try`, a `with`, an `if` and the
    # `else` of `if TYPE_CHECKING:`. What is not: an import inside a function, which is how this
    # codebase defers a load until a command asks for it (the pinned crossing into the overlay
    # area, every import of a discovered `hooks.py` and `doctor.py`), cannot leave a module
    # half-initialised, and is held where it crosses into delivery by
    # `test_core_never_imports_delivery`; and an `if TYPE_CHECKING:` body, which never runs and
    # is the idiom for naming a type from a package that depends on this one. The nodes are the
    # packages under `src/stayfixed/`, delivery areas included, and imports within one package are
    # not edges.
    #
    # Mutations (declared): `mutations/`'s "the Python profile's hint imports the session guard
    # again" and "printed reads the configuration's schema again".
    source = ROOT / "src" / "stayfixed"
    packages = frozenset(
        path.name.removesuffix(".py")
        for path in source.iterdir()
        if path.suffix == ".py" or (path / "__init__.py").is_file()
    )
    edges: set[tuple[str, str]] = set()
    for path in sorted(source.rglob("*.py")):
        relative = path.relative_to(source).as_posix()
        edges |= _package_imports(relative, path.read_text(encoding="utf-8"), packages)
    # The walk reads the edges the two cycles were made of, so a reader that stopped finding
    # imports cannot pass by finding no cycle.
    assert {("config", "findings"), ("findings", "printed"), ("guards", "profiles")} <= edges
    assert _cycles(edges) == []


def test_the_package_graph_reads_imports_that_run_and_finds_every_cycle() -> None:
    # The walk above can show the reading only for the spellings the tree carries. Measured by
    # hand: reading function bodies, reading `if TYPE_CHECKING:` bodies or dropping the
    # own-package filter each reddens the first assertion, and a `_cycles` that kept components
    # of one package, or read reachability one way only, reddens the second.
    packages = frozenset({"config", "findings", "guards", "printed", "profiles"})
    text = (
        "from stayfixed.findings import listed\n"
        "if TYPE_CHECKING:\n    from stayfixed.config.schema import Config\n"
        "else:\n    import stayfixed.printed\n"
        "def f():\n    from stayfixed.guards.api import contained_roots\n"
        "from . import sibling\nfrom stayfixed.profiles import shipped\n"
        "from stayfixed import nothing_here\n"
    )
    assert _package_imports("profiles/python/hygiene.py", text, packages) == {
        ("profiles", "findings"),
        ("profiles", "printed"),
    }
    edges = {("a", "b"), ("b", "c"), ("c", "a"), ("c", "d"), ("d", "e"), ("e", "d"), ("f", "a")}
    assert _cycles(edges) == [["a", "b", "c"], ["d", "e"]]


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


# The names through which a module is loaded without an import statement of its own, which the
# delivery rule above reads no more than discovery's caller does: `import_module` and `__import__`
# import by a string, a module's own `__spec__` and `__loader__` and the finders on `sys`'s
# `meta_path`, `path_hooks` and `path_importer_cache` load a module by its file with no import at
# all, and `sys.breakpointhook` and `sys.__breakpointhook__` import whatever `PYTHONBREAKPOINT`
# names. Each is read as an attribute of anything, as a bare name, and inside a string constant
# that is not a docstring: a message that names one is a row, to pin or to reword.
DYNAMIC_IMPORTS = frozenset(
    {
        "__breakpointhook__",
        "__import__",
        "__loader__",
        "__spec__",
        "breakpointhook",
        "import_module",
        "meta_path",
        "path_hooks",
        "path_importer_cache",
    }
)
# The builtins that run code built from text, and the module that holds every builtin, which hands
# `__import__` over by a computed name. Read as a bare name unless, by Python's scoping, it resolves
# to a function's own binding, a comprehension's variable or an import from any module but
# `builtins`, in that scope or one around it; as a binding made in a module or a class body, which
# Python looks up at run time, so that the binding may not have run, may have been deleted, or may
# be the builtin itself (`exec = exec`), and which therefore hides nothing and is a row to pin or
# rename; under any alias `from builtins import` gives one; and as a whole string constant (a
# choice spelled `"eval"` is a row too, to pin or to reword). Not as an attribute: `compile` is
# `re.compile` there, and `builtins.exec` needs `builtins`, which the machinery rule below holds.
# `__builtins__` is the exception: every module carries it, so it is read as an attribute of
# anything (`json.__builtins__`), and a `from` of it from any module is a row, under any alias.
TEXT_RUNNERS = frozenset({"__builtins__", "breakpoint", "compile", "eval", "exec"})

# The one core module whose job is importing modules by name: discovery, which imports
# `stayfixed.<area>.<submodule>` for the submodules `area_modules` is called with (held below), and
# is how every area, delivery included, plugs into the core.
DISCOVERY_MODULE = "areas.py"
# What discovery itself reads of the names below, by function: its two imports by name.
DISCOVERY_READS = (("area_modules", "import_module"), ("area_imports", "import_module"))

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


# The nodes that open a scope of their own, by Python's rules: a function, a lambda, a class body
# and a comprehension.
_FUNCTION_SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)
_COMPREHENSIONS = (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)
_SCOPES = (*_FUNCTION_SCOPES, ast.ClassDef, *_COMPREHENSIONS)
# The scopes Python looks a name up in at run time, in the namespace and then in the builtins.
_RUN_TIME_SCOPES = (ast.Module, ast.ClassDef)

_Chain = Sequence[tuple[ast.AST, tuple[set[str], set[str], set[str]]]]


def _scope_parts(node: ast.AST) -> tuple[list[ast.AST], list[ast.AST]]:
    """A scope node's children split by where Python evaluates them: in the enclosing scope (a
    function's decorators, type parameters, defaults and annotations, a class's decorators, type
    parameters and bases, a comprehension's first iterable) and in the scope the node opens (the
    body, a comprehension's targets and the rest). Type parameters are read through `getattr`,
    since the 3.11 syntax tree has none."""
    if isinstance(node, _FUNCTION_SCOPES):
        args = node.args
        every = [*args.posonlyargs, *args.args, args.vararg, *args.kwonlyargs, args.kwarg]
        outer: list[ast.AST] = [*args.defaults, *(d for d in args.kw_defaults if d is not None)]
        outer += [a.annotation for a in every if a is not None and a.annotation is not None]
        if isinstance(node, ast.Lambda):
            return outer, [node.body]
        outer += [*node.decorator_list, *getattr(node, "type_params", [])]
        outer += [node.returns] if node.returns else []
        return outer, list(node.body)
    if isinstance(node, ast.ClassDef):
        outer = [*node.decorator_list, *getattr(node, "type_params", [])]
        return [*outer, *node.bases, *node.keywords], list(node.body)
    if isinstance(node, _COMPREHENSIONS):
        first, *rest = node.generators
        results = [node.key, node.value] if isinstance(node, ast.DictComp) else [node.elt]
        return [first.iter], [first.target, *first.ifs, *rest, *results]
    return [], list(ast.iter_child_nodes(node))


def _bound_name(node: ast.AST) -> str | None:
    """The name `node` binds, an import aside: a name stored or deleted, a `def` or `class` name,
    or an `except … as` or `match` capture."""
    if isinstance(node, ast.Name) and type(node.ctx) is not ast.Load:
        return node.id
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return node.name
    if isinstance(node, (ast.ExceptHandler, ast.MatchAs, ast.MatchStar)):
        return node.name
    if isinstance(node, ast.MatchMapping):
        return node.rest
    return None


def _scope_bindings(node: ast.AST) -> tuple[set[str], set[str], set[str]]:
    """The names that hide a builtin throughout the scope `node` opens, and those it declares
    `global` and `nonlocal`.

    A function's names are fixed when it is compiled, so every name it binds hides there: its
    parameters, each `_bound_name` in its own body, an import from any module but `builtins`, and
    a walrus target in a comprehension inside it, which Python binds in the function. A
    comprehension hides only its own iteration variables. A module or a class body is looked up at
    run time, where a binding may not have run, may have been deleted, or may be the builtin
    itself (`exec = exec`), so only an import hides there. What a nested scope binds is that
    scope's own."""
    bound: set[str] = set()
    imported: set[str] = set()
    if isinstance(node, _FUNCTION_SCOPES):
        args = node.args
        every = [*args.posonlyargs, *args.args, args.vararg, *args.kwonlyargs, args.kwarg]
        bound |= {a.arg for a in every if a is not None}
    declared_global: set[str] = set()
    declared_nonlocal: set[str] = set()
    # Each part with whether it sits in a comprehension nested in this scope, where only a walrus
    # binds a name of this scope's.
    pending = [(part, False) for part in _scope_parts(node)[1]]
    while pending:
        child, nested = pending.pop()
        if isinstance(child, ast.NamedExpr):
            if not isinstance(node, _COMPREHENSIONS):
                bound.add(child.target.id)
            pending.append((child.value, nested))
            continue
        name = None if nested else _bound_name(child)
        if name is not None:
            bound.add(name)
        elif isinstance(child, ast.Global):
            declared_global |= set(child.names)
        elif isinstance(child, ast.Nonlocal):
            declared_nonlocal |= set(child.names)
        elif isinstance(child, ast.Import):
            imported |= {
                alias.asname or alias.name.split(".")[0]
                for alias in child.names
                if alias.name != "builtins"
            }
        elif isinstance(child, ast.ImportFrom) and child.module != "builtins":
            imported |= {alias.asname or alias.name for alias in child.names}
        if isinstance(child, _SCOPES):
            outer, inner = _scope_parts(child)
            pending += [(part, nested) for part in outer]
            if isinstance(child, _COMPREHENSIONS):
                pending += [(part, True) for part in inner]
        else:
            pending += [(part, nested) for part in ast.iter_child_nodes(child)]
    hiding = imported if isinstance(node, _RUN_TIME_SCOPES) else bound | imported
    return hiding - declared_global - declared_nonlocal, declared_global, declared_nonlocal


def _shadowed(name: str, chain: _Chain) -> bool:
    """Whether `name`, read in the innermost scope of `chain` (the module first), resolves to a
    binding of the file's rather than to the builtin: Python's own lookup, the innermost scope
    outward, past every enclosing class body, which a nested scope does not see, and through a
    `global` straight to the module, where only an import hides (`_scope_bindings`)."""
    for depth, (node, (bound, declared_global, _)) in enumerate(reversed(chain)):
        if depth and isinstance(node, ast.ClassDef):
            continue
        if name in declared_global:
            return name in chain[0][1][0]
        if name in bound:
            return True
    return False


def _binds_at_run_time(name: str, chain: _Chain, *, walrus: bool) -> bool:
    """Whether a binding of `name` made in the innermost scope of `chain` lands in a module or a
    class body, which Python looks up at run time: made there, made in a function under `global`,
    or a walrus target in a comprehension, which binds in the nearest scope around it that is not
    a comprehension."""
    depth = len(chain) - 1
    while walrus and isinstance(chain[depth][0], _COMPREHENSIONS):
        depth -= 1
    node, (_, declared_global, _) = chain[depth]
    return isinstance(node, _RUN_TIME_SCOPES) or name in declared_global


def _dynamic_imports(tree: ast.AST) -> list[tuple[str, str]]:
    """Every reference in `tree` to a `DYNAMIC_IMPORTS` or `TEXT_RUNNERS` name, as `(function,
    name)`, `function` being the innermost enclosing `def` or `<module>`.

    Read as: a `DYNAMIC_IMPORTS` name as an attribute of anything (`importlib.import_module`,
    `builtins.__import__`, `sys.meta_path`, `module.__spec__`), by its bare name, by any name a
    `from … import` binds it to, and anywhere inside a string constant that is not a docstring,
    which covers `getattr(importlib, "import_module")` and a string annotation that
    `typing.get_type_hints` would evaluate; a `TEXT_RUNNERS` name by its bare name unless it
    resolves, by Python's scoping (`_shadowed`), to a binding that hides it (`_scope_bindings`: a
    function's local or parameter, a comprehension's variable, or an import from any module but
    `builtins`), by any name `from builtins import` binds it to (`from` any module, for
    `__builtins__`, which is also read as an attribute of anything), as a whole string constant,
    which is how `getattr(builtins, "exec")` spells it, and as a binding that lands in a module or a
    class body (`exec = exec`, `del exec`, `def breakpoint`, a walrus in a module-level
    comprehension), which Python looks up at run time. The `from` statement itself is a row: of any
    module for a `DYNAMIC_IMPORTS` name or `__builtins__`, of `builtins` for another `TEXT_RUNNERS`
    one, and `from importlib import *`.
    """

    def binds(node: ast.ImportFrom, names: frozenset[str]) -> list[ast.alias]:
        if names is TEXT_RUNNERS and node.module != "builtins":
            return [alias for alias in node.names if alias.name == "__builtins__"]
        return [alias for alias in node.names if alias.name in names]

    bound = set(DYNAMIC_IMPORTS) | {
        alias.asname or alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for names in (DYNAMIC_IMPORTS, TEXT_RUNNERS)
        for alias in binds(node, names)
    }
    walrus = {id(node.target) for node in ast.walk(tree) if isinstance(node, ast.NamedExpr)}
    found: list[tuple[str, str]] = []

    def read(child: ast.AST, function: str, chain: _Chain) -> None:
        if (
            isinstance(child, ast.Expr)
            and isinstance(child.value, ast.Constant)
            and isinstance(child.value.value, str)
        ):
            return  # a docstring, or a string standing alone as a statement, which is prose
        if isinstance(child, ast.Attribute) and (
            child.attr in DYNAMIC_IMPORTS or child.attr == "__builtins__"
        ):
            found.append((function, child.attr))
        elif isinstance(child, ast.Name) and (
            child.id in bound
            or (
                child.id in TEXT_RUNNERS
                and type(child.ctx) is ast.Load
                and not _shadowed(child.id, chain)
            )
        ):
            found.append((function, child.id))
        elif isinstance(child, ast.Constant) and isinstance(child.value, str):
            if child.value in TEXT_RUNNERS:
                found.append((function, child.value))
            found.extend(
                (function, name) for name in sorted(DYNAMIC_IMPORTS) if name in child.value
            )
        elif isinstance(child, ast.ImportFrom) and (
            binds(child, DYNAMIC_IMPORTS)
            or binds(child, TEXT_RUNNERS)
            or (child.module == "importlib" and any(a.name == "*" for a in child.names))
        ):
            found.append((function, f"from {child.module} import"))
        elif (
            (binding := _bound_name(child)) is not None
            and binding in TEXT_RUNNERS
            and _binds_at_run_time(binding, chain, walrus=id(child) in walrus)
        ):
            found.append((function, binding))
        if isinstance(child, _SCOPES):
            outer, inner = _scope_parts(child)
            name = function
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                name = child.name
            for part in outer:
                read(part, function, chain)
            for part in inner:
                read(part, name, [*chain, (child, _scope_bindings(child))])
        else:
            for part in ast.iter_child_nodes(child):
                read(part, function, chain)

    module: _Chain = [(tree, _scope_bindings(tree))]
    for part in ast.iter_child_nodes(tree):
        read(part, "<module>", module)
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
    # So were a module's own loader (`type(__spec__.loader)(name, path).exec_module(module)`), a
    # finder on `sys.meta_path`, and `exec` of a string that imports. This reads those names; the
    # standard library's other ways to import by a string are held where they must be imported
    # from, by `test_no_core_module_reaches_the_import_machinery_…`.
    #
    # Mutations (declared): `mutations/`'s "a core function imports the note store through
    # importlib", "a core function imports the note store through __import__", "a core function
    # imports the note store through an alias of import_module", "a core function loads the note
    # store through its own module's loader", "a core function loads the note store through a
    # finder on sys.meta_path", "a core function imports the note store by running text", "a core
    # function reaches __import__ through __builtins__" and "a core function's string annotation
    # imports the note store".
    source = ROOT / "src" / "stayfixed"
    rows: list[tuple[str, str, str]] = []
    discovery: list[tuple[str, str]] = []
    for where, path in _core_files(source):
        found = _dynamic_imports(ast.parse(path.read_text(encoding="utf-8")))
        if where == DISCOVERY_MODULE:
            discovery += found
        else:
            rows += [(where, function, name) for function, name in found]
    # Discovery's exemption is its two `importlib.import_module` calls and nothing else, so an
    # `exec` or a `sys.meta_path` read in `areas.py` is caught like one anywhere else, and a reader
    # that stopped seeing the spelling the pardon is written in cannot pass by finding nothing.
    assert Counter(discovery) == Counter(DISCOVERY_READS), discovery
    found_rows, pinned = Counter(rows), Counter(DYNAMIC_IMPORTERS)
    assert found_rows == pinned, {"unpinned": found_rows - pinned, "gone": pinned - found_rows}


# The standard library modules a core module may import with no row, by name or as a package whose
# submodules are all allowed: the 34 the core imports today, each one whose public functions import
# no module named by a string and run no code built from text but through a name the rule above
# reads (`sys.breakpointhook`, `typing.get_type_hints` of a string spelling `__import__`). Every
# other module is the machinery: a core import of one is a row of `MACHINERY_IMPORTERS` below, with
# what the file reaches in it.
# Read the other way round, a deny-list of the modules that can import by a string stayed open to
# every one nobody had measured yet (`timeit`, `xml.dom.pulldom`'s `xml.sax`, `inspect`'s
# `importlib`, `builtins`). `importlib` and `pkgutil` are not on the list: discovery imports through
# them, and their rows say what each file reaches. `urllib` is listed as `urllib.parse`: an import
# of any other submodule of it is a row, while a read off the `urllib` that `import urllib.parse`
# binds is not judged, since no read off an allowed import is (an attribute chain, below).
#
# This rule and the name rule above are a tripwire, not a proof: they read import statements and a
# list of names, so they catch a crossing written the ordinary way and prove nothing about one
# written to hide. What they cannot read: an attribute chain through an allowed module
# (`dataclasses.inspect.importlib`, `typing.sys.modules`), a module already in `sys.modules`, a
# loader or a finder reached by a computed name (`getattr(sys, "meta" + "_path")`), an import in a
# module or a class body that fails and is caught, which hides a builtin the name rule then takes
# for the file's own, code built from text at run time, and a string an allowed module evaluates
# (`typing.get_type_hints` of an annotation built at run time).
# `test_in_isolation_no_core_module_loads_a_delivery_area` sees what loads at import time and
# nothing a function does later.
STANDARD_IMPORTS = frozenset(
    {
        "__future__",
        "argparse",
        "collections",
        "configparser",
        "contextlib",
        "copy",
        "dataclasses",
        "datetime",
        "enum",
        "errno",
        "functools",
        "hashlib",
        "io",
        "itertools",
        "json",
        "os",
        "pathlib",
        "posixpath",
        "pwd",
        "re",
        "shlex",
        "shutil",
        "signal",
        "stat",
        "string",
        "struct",
        "subprocess",
        "sys",
        "tempfile",
        "time",
        "tomllib",
        "types",
        "typing",
        "urllib.parse",
    }
)
# `importlib.resources` reads package data, and imports a module only as the anchor `files` is
# handed: given a module's name, it imports that module. So it is outside the rule for exactly two
# reads, which import nothing that is not already loaded. One is `files` called on the package
# itself, `__package__` (a core module's own package) or the literal `"stayfixed"`, in a module
# that never binds `__package__` itself. The other is `importlib.resources.abc`, which holds types.
# Every other read of it, the same function given any other argument, the module handed on and the
# functions that take an anchor of their own (`read_text`, `open_binary` …), is the machinery.
RESOURCES = "importlib.resources"

# Every core import of a module off `STANDARD_IMPORTS`, one row per statement: the file relative
# to `src/stayfixed/`, the module the statement names, and what the file reaches through it -- the
# names a `from` statement takes, or each attribute path read off the name an `import` binds
# (`<value>` when the name itself is handed on, where anything could be read off it). Held as a
# multiset and by equality in both directions, as `DYNAMIC_IMPORTERS` is.
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


def _attribute_path(node: ast.AST, parents: dict[int, ast.AST]) -> tuple[str, ast.AST]:
    """The dotted attributes read off the name `node`, outermost last (`util.MAGIC_NUMBER` for
    `importlib.util.MAGIC_NUMBER`), or `<value>` when the name is used as anything but the root
    of an attribute read; and the outermost node of that read, which a call would be made on."""
    path: list[str] = []
    while isinstance(parent := parents.get(id(node)), ast.Attribute) and parent.value is node:
        path.append(parent.attr)
        node = parent
    return ".".join(path) or "<value>", node


def _within(module: str, listed: Iterable[str]) -> bool:
    return any(module == entry or module.startswith(f"{entry}.") for entry in listed)


def _reads_data(dotted: str, node: ast.AST, parents: dict[int, ast.AST], rebound: bool) -> bool:
    """Whether reading `dotted` at `node` is one of the two reads of `RESOURCES` that import
    nothing: anything in its `abc`, or a call of its `files` with one positional argument, the
    literal `"stayfixed"` or `__package__` in a module that never binds it (`rebound`)."""
    if _within(dotted, {f"{RESOURCES}.abc"}):
        return True
    call = parents.get(id(node))
    if dotted != f"{RESOURCES}.files" or not isinstance(call, ast.Call) or call.func is not node:
        return False
    if call.keywords or len(call.args) != 1:
        return False
    (anchor,) = call.args
    if isinstance(anchor, ast.Name):
        return anchor.id == "__package__" and not rebound
    return isinstance(anchor, ast.Constant) and anchor.value == "stayfixed"


def _machinery_imports(tree: ast.AST) -> list[tuple[str, frozenset[str]]]:
    """Every statement in `tree` that imports a module neither `stayfixed`'s own nor on
    `STANDARD_IMPORTS`, as `(module, reach)`: for `from m import a, b` the names taken that are not
    allowed modules themselves (`from urllib import parse` takes none), for `import m.n [as x]`
    every attribute path read off the name it binds, anywhere in the file. A `RESOURCES` name,
    and an `import` of it, counts only for its reads `_reads_data` does not pass, and is no row
    when that leaves none."""
    parents = {id(child): node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
    # A module that binds `__package__` itself can point it at any module at all.
    rebound = any(
        (isinstance(node, ast.Name) and node.id == "__package__" and type(node.ctx) is not ast.Load)
        or (isinstance(node, ast.arg) and node.arg == "__package__")
        for node in ast.walk(tree)
    )

    def reached(bound: str, dotted: str) -> set[str]:
        """The reads off the name `bound`, which stands for `dotted`, past what imports nothing."""
        paths: set[str] = set()
        for name in ast.walk(tree):
            if isinstance(name, ast.Name) and name.id == bound:
                path, outer = _attribute_path(name, parents)
                full = dotted if path == "<value>" else f"{dotted}.{path}"
                if not _reads_data(full, outer, parents, rebound):
                    paths.add(path)
        return paths

    def allowed(module: str) -> bool:
        return module.split(".")[0] == "stayfixed" or _within(module, STANDARD_IMPORTS)

    found: list[tuple[str, frozenset[str]]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and not node.level and node.module:
            names: set[str] = set()
            for alias in node.names:
                dotted = f"{node.module}.{alias.name}"
                if allowed(node.module) or allowed(dotted):
                    continue
                data = alias.name != "*" and _within(dotted, {RESOURCES})
                if data and not reached(alias.asname or alias.name, dotted):
                    continue
                names.add(alias.name)
            if names:
                found.append((node.module, frozenset(names)))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                # An allowed import is no row, and nothing read off the name it binds is judged:
                # `import urllib.parse` binds `urllib`, and `urllib.request` read off it passes.
                if allowed(alias.name):
                    continue
                bound = alias.asname or alias.name.split(".")[0]
                dotted = alias.name if alias.asname else bound
                reach = reached(bound, dotted)
                if reach or not _within(alias.name, {RESOURCES}):
                    found.append((alias.name, frozenset(reach)))
    return found


def test_no_core_module_reaches_the_import_machinery_but_where_pinned() -> None:
    # The rule above reads a list of names, and `pkgutil.resolve_name("stayfixed.memory.store")`,
    # `importlib.util.find_spec` and a loader's `exec_module`, `importlib.resources.files` handed
    # the store's name, `pydoc.locate`, `pickle.loads`, `logging.config`'s resolver, `timeit` and
    # `xml.sax.make_parser` each crossed into the private layer from a core function with every
    # boundary test green. So the core imports the standard library from `STANDARD_IMPORTS` alone,
    # and any other import is pinned with what it reaches: a new importer is a new row, and a
    # pinned importer reaching one more name changes its row. `importlib.resources` is no row while
    # it only reads the package's own data. What this cannot see is in the comment over
    # `STANDARD_IMPORTS`: it is a tripwire, not a proof.
    #
    # Mutations (declared): `mutations/`'s "a core function imports the note store through
    # pkgutil.resolve_name", "profile discovery reaches importlib.util as well", "a core function
    # opens the note store's resources by its module name", "a core function opens the note
    # store's resources through files imported by name", "a core function imports the note store
    # through pydoc.locate", "a core function unpickles a reference to the note store", "a core
    # function loads code through marshal", "a core function resolves the note store through
    # logging.config", "a core function runs an import through timeit", "a core function reaches
    # xml.sax through a sibling submodule's import" and "a core function takes __import__ from
    # builtins by a computed name".
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
    # the name handed on as a value, and `importlib.resources` read for the package's own data in
    # each spelling left alone, though not what is read off the `importlib` its `import` binds.
    # Measured by hand: dropping the `RESOURCES` check of the `from` arm of `_machinery_imports`,
    # the `<value>` fallback, or `_reads_data`'s `files` arm each reddens it.
    spellings = (
        "from importlib import resources\nfrom importlib.resources.abc import Traversable\n"
        "import importlib.resources\nimportlib.resources.files(__package__)\n"
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


@pytest.mark.parametrize(
    ("source", "rows"),
    [
        pytest.param(
            "from importlib import resources\nresources.files(__package__).joinpath('x')\n"
            "resources.files('stayfixed')\n",
            [],
            id="files-on-the-package",
        ),
        pytest.param(
            "import importlib.resources\nimport importlib.resources as r\n"
            "importlib.resources.files(__package__)\nr.files('stayfixed')\n",
            [],
            id="files-on-the-package-through-import",
        ),
        pytest.param(
            "from importlib.resources.abc import Traversable\nx: Traversable\n", [], id="abc"
        ),
        pytest.param(
            "from importlib import resources\nresources.files('stayfixed.memory.store')\n",
            [("importlib", frozenset({"resources"}))],
            id="files-on-a-module-name",
        ),
        pytest.param(
            "import importlib.resources\nimportlib.resources.files(name)\n",
            [("importlib.resources", frozenset({"resources.files"}))],
            id="files-on-a-computed-name",
        ),
        pytest.param(
            "import importlib.resources as r\nr.files(anchor=__package__)\n",
            [("importlib.resources", frozenset({"files"}))],
            id="files-by-keyword",
        ),
        pytest.param(
            "from importlib.resources import files\nfiles('stayfixed.memory.store')\n",
            [("importlib.resources", frozenset({"files"}))],
            id="files-imported-by-name",
        ),
        pytest.param(
            "from importlib import resources\nresources.read_text(__package__, 'x')\n",
            [("importlib", frozenset({"resources"}))],
            id="an-anchor-of-its-own",
        ),
        pytest.param(
            "from importlib import resources\nload(resources)\n",
            [("importlib", frozenset({"resources"}))],
            id="handed-on",
        ),
        pytest.param(
            "from importlib import resources\n__package__ = 'stayfixed.memory.store'\n"
            "resources.files(__package__)\n",
            [("importlib", frozenset({"resources"}))],
            id="package-rebound",
        ),
        pytest.param(
            "from importlib import resources\ndef f(__package__):\n"
            "    return resources.files(__package__)\n",
            [("importlib", frozenset({"resources"}))],
            id="package-a-parameter",
        ),
        pytest.param(
            "import pydoc\npydoc.locate('x')\n", [("pydoc", frozenset({"locate"}))], id="pydoc"
        ),
        pytest.param(
            "from pickle import loads as load\n", [("pickle", frozenset({"loads"}))], id="pickle"
        ),
        pytest.param(
            "import marshal as m\nm.loads(data)\n",
            [("marshal", frozenset({"loads"}))],
            id="marshal",
        ),
        pytest.param(
            "import logging.config\nlogging.config.dictConfig({})\n",
            [("logging.config", frozenset({"config.dictConfig"}))],
            id="logging-config",
        ),
        pytest.param(
            "from logging import config, getLogger\n",
            [("logging", frozenset({"config", "getLogger"}))],
            id="logging-off-the-list",
        ),
        pytest.param(
            "from multiprocessing.reduction import ForkingPickler\n",
            [("multiprocessing.reduction", frozenset({"ForkingPickler"}))],
            id="a-submodule-off-the-list",
        ),
        pytest.param(
            "import xml.dom.pulldom\nxml.sax.make_parser(['x'])\n",
            [("xml.dom.pulldom", frozenset({"sax.make_parser"}))],
            id="a-sibling-read-off-the-package-an-import-binds",
        ),
        pytest.param(
            "from xml.dom import pulldom\n", [("xml.dom", frozenset({"pulldom"}))], id="xml-dom"
        ),
        pytest.param(
            "import timeit\ntimeit.timeit('x')\n", [("timeit", frozenset({"timeit"}))], id="timeit"
        ),
        pytest.param(
            "import builtins\ngetattr(builtins, name)\n",
            [("builtins", frozenset({"<value>"}))],
            id="builtins",
        ),
        pytest.param(
            "import inspect\ninspect.importlib\n",
            [("inspect", frozenset({"importlib"}))],
            id="inspect",
        ),
        pytest.param(
            "import os.path\nfrom collections.abc import Mapping\nimport urllib.parse\n"
            "from urllib import parse\nfrom os import path\nimport stayfixed.areas\n"
            "from . import sibling\n",
            [],
            id="on-the-list-or-our-own",
        ),
        pytest.param(
            "from urllib import parse, request\nimport urllib.request\n",
            [("urllib", frozenset({"request"})), ("urllib.request", frozenset())],
            id="a-package-allowed-in-part",
        ),
    ],
)
def test_the_machinery_rule_reads_resources_by_its_anchor_and_every_other_module(
    source: str, rows: list[tuple[str, frozenset[str]]]
) -> None:
    # `importlib.resources.files` imports the anchor it is handed when that names a module, so
    # it is data only on the package itself, and every other read of `importlib.resources` is a
    # row. Every module off `STANDARD_IMPORTS` is a row, a submodule of an allowed package
    # included, and nothing on it is. Measured by hand: dropping the `rebound` check, the keyword
    # check, the `abc` arm, the `RESOURCES` check of the `import` arm, the `allowed` check of
    # either statement, the dotted name's own check in the `from` arm, the `stayfixed` exemption,
    # or reading the list by top-level name each reddens a case.
    assert _machinery_imports(ast.parse(source)) == rows


# The two functions through which discovery imports `stayfixed.<area>.<submodule>`: the one the CLI
# frame and the hook registry ask, which lets an import failure raise, and the one `doctor` asks,
# which hands it back so it costs one row.
DISCOVERY_FUNCTIONS = frozenset({"area_modules", "area_imports"})


# Who asks discovery for what, one row per call: the file relative to `src/stayfixed/` and the
# submodule its call names. Held as a multiset and by equality in both directions, as
# `DYNAMIC_IMPORTERS` is. Each submodule has its one reader, the CLI frame, the hook registry and
# the doctor report, and no other module asks: any module that could ask for `commands` could pick
# one area's module out of the answer by its name and call into the private layer through the door
# the delivery rule leaves open, though every call named a submodule discovery is for.
DISCOVERY_CALLERS = (
    ("cli.py", "commands"),
    ("doctor/registry.py", "doctor"),
    ("hooks/registry.py", "hooks"),
)


# A reader's own seam that hands back what discovery found, by the one module allowed to refer to
# it: `cli.discover_registrars` returns every area's `register`, so any other module could pick one
# area's out of it by `__module__` as it could out of `area_modules`. The doctor report's seam and
# the hook registry's are private modules of their packages, which the surface rule already holds.
DISCOVERY_SEAMS = {"discover_registrars": "cli.py"}


def _discovery_references(
    tree: ast.AST, functions: frozenset[str] = DISCOVERY_FUNCTIONS
) -> list[ast.Name | ast.Attribute]:
    """Every reference to one of `functions` in `tree`: by any name a `from … import` binds it
    to, and as an attribute of anything (`stayfixed.areas.area_modules`)."""
    bound = set(functions) | {
        alias.asname
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
        if alias.name in functions and alias.asname
    }
    return [
        node
        for node in ast.walk(tree)
        if (isinstance(node, ast.Name) and node.id in bound)
        or (isinstance(node, ast.Attribute) and node.attr in functions)
    ]


def _discovery_asks(tree: ast.AST, allowed: frozenset[str]) -> dict[int, str]:
    """The submodule each call of a discovery function in `tree` names, keyed by the identity of
    the reference it calls, for every call with one literal argument out of `allowed`."""
    references = {id(node) for node in _discovery_references(tree)}
    return {
        id(node.func): str(node.args[0].value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and id(node.func) in references
        and not node.keywords
        and len(node.args) == 1
        and isinstance(node.args[0], ast.Constant)
        and node.args[0].value in allowed
    }


def _area_module_offences(where: str, tree: ast.AST, allowed: frozenset[str]) -> list[str]:
    """Every reference to a discovery function in `tree` that is not a call with one literal
    argument out of `allowed`: a call naming any other submodule, a computed argument, and the
    function handed on as a value, which would call it out of sight."""
    asks = _discovery_asks(tree, allowed)
    lines = [node.lineno for node in _discovery_references(tree) if id(node) not in asks]
    return [f"{where}:{line}" for line in sorted(lines)]


def test_discovery_is_asked_only_for_the_submodules_it_names() -> None:
    # `area_modules` and `area_imports` import `stayfixed.<area>.<submodule>` for every area that
    # has one, so a core caller asking for `"api"` loads every area's surface, the private layer's
    # included, through the one door the delivery rule leaves open. Every call under
    # `src/stayfixed/` names one of the three submodules discovery is for, as a literal, and is
    # made by that submodule's reader alone (`DISCOVERY_CALLERS`). No module but its own refers to a
    # reader's seam that hands discovery's answer on (`DISCOVERY_SEAMS`).
    #
    # Mutations (declared): `mutations/`'s "a core module asks discovery for every area's api.py",
    # "a core module picks one area's commands out of discovery" and "a core module picks one
    # area's commands out of the CLI frame's registrars".
    source = ROOT / "src" / "stayfixed"
    allowed = frozenset(name.removesuffix(".py") for name in DISCOVERED_SUBMODULES)
    offences: list[str] = []
    asked: list[tuple[str, str]] = []
    for path in sorted(source.rglob("*.py")):
        where = path.relative_to(source).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"))
        offences += _area_module_offences(where, tree, allowed)
        offences += [
            f"{where}:{node.lineno}"
            for seam, home in DISCOVERY_SEAMS.items()
            if where != home
            for node in _discovery_references(tree, frozenset({seam}))
        ]
        asked += [(where, submodule) for submodule in _discovery_asks(tree, allowed).values()]
    assert offences == []
    # Each reader's call is a row, so a walk that stopped finding calls cannot pass by finding no
    # offence, and a fourth caller is an unpinned row however it spells the call.
    found, pinned = Counter(asked), Counter(DISCOVERY_CALLERS)
    assert found == pinned, {"unpinned": found - pinned, "gone": pinned - found}


def test_the_string_import_rules_read_every_spelling() -> None:
    # The walks above can only show the rules holding for the spellings the tree carries, so they
    # are put in front of the ones it does not. Measured by hand: reading `from importlib import`
    # aliases no more reddens the first assertion, dropping the string-constant arm the second,
    # dropping the attribute arm of `_discovery_references` the third and the fourth, and reading a
    # call of any function as an ask the fourth. In the last, dropping the attribute arm of
    # `_dynamic_imports`, any one of its names, the bare reading of `TEXT_RUNNERS`, their whole
    # constant arm, the substring arm, reading `from` statements of `importlib` alone, or reading
    # `__builtins__` as no attribute or in a `from` of `builtins` alone each reddens it. In `quiet`,
    # reading docstrings, reading a `TEXT_RUNNERS` `from` of any module, or reading a name the file
    # binds itself (a local, a parameter, an import) each reddens it. In `scoped`, hiding a builtin
    # wherever the file binds its name, letting a class body be seen by its methods, not following
    # `global`, letting a `global` alone hide the builtin, giving a comprehension no scope, binding
    # no parameter, reading a store as a use, or reading a function's annotations in its own scope
    # each reddens it. In `generic`, on 3.12 and later, leaving a function's or a class's type
    # parameters unread reddens it. Mutations (declared): `mutations/`'s "the name rule hides a
    # builtin across the whole file again", "a module or a class body hides a builtin by any binding
    # again", "a binding of a text runner in a module or a class body is no row", "a function's
    # store of a text runner under global is no row", "a walrus in a comprehension binds in the
    # comprehension", "a walrus target is taken to land in its comprehension", "import builtins
    # under a text runner's name hides the builtin", "a function's type parameters are not read", "a
    # class's type parameters are not read", "__builtins__ read off another module is no row" and "a
    # from of __builtins__ out of another module is no row".
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
    asking = (
        "import stayfixed.areas\nstayfixed.areas.area_modules('commands')\n"
        "from stayfixed.areas import area_imports as ask\nask('doctor')\nprint('hooks')\n"
    )
    assert sorted(_discovery_asks(ast.parse(asking), allowed).values()) == ["commands", "doctor"]
    seams = (
        "from stayfixed.cli import discover_registrars as found\nfound()\n"
        "import stayfixed.cli\nstayfixed.cli.discover_registrars()\n"
    )
    seam = frozenset(DISCOVERY_SEAMS)
    assert [node.lineno for node in _discovery_references(ast.parse(seams), seam)] == [2, 4]
    texts = (
        "def f(x: \"__import__('stayfixed.memory.store')\"):\n    type(__spec__.loader)\n"
        "    sys.meta_path\n    m.__loader__\n    getattr(importlib, 'import_module')\n"
        "exec(text)\ngetattr(builtins, 'eval')\nfrom builtins import compile as c\nbreakpoint()\n"
        "__builtins__\nre.compile('x')\nfrom sys import path_hooks\nsys.path_importer_cache\n"
        "sys.breakpointhook(None, None)\nsys.__breakpointhook__\n"
        "json.__builtins__\nfrom re import __builtins__ as b\nb\n"
    )
    assert sorted(_dynamic_imports(ast.parse(texts))) == [
        ("<module>", "__breakpointhook__"),
        ("<module>", "__builtins__"),
        ("<module>", "__builtins__"),
        ("<module>", "__import__"),
        ("<module>", "b"),
        ("<module>", "breakpoint"),
        ("<module>", "breakpointhook"),
        ("<module>", "eval"),
        ("<module>", "exec"),
        ("<module>", "from builtins import"),
        ("<module>", "from re import"),
        ("<module>", "from sys import"),
        ("<module>", "path_importer_cache"),
        ("f", "__loader__"),
        ("f", "__spec__"),
        ("f", "import_module"),
        ("f", "meta_path"),
    ]
    # Prose and a name of the file's own are not the builtin: a docstring naming a finder, a
    # `compile` imported from another module under its name or an alias, and a parameter or a
    # local named after a builtin that runs text.
    quiet = (
        '"""Names no finder on sys.meta_path."""\n'
        "from re import compile as _c\n_R = _c('x')\nfrom re import compile\ncompile('y')\n"
        "def f(eval):\n    exec = 1\n    return eval, exec\n"
    )
    assert _dynamic_imports(ast.parse(quiet)) == []
    # A function's binding hides a builtin in that function and the scopes it encloses, never
    # beyond: the builtin read in another function, beside a comprehension's variable, in a method
    # beside a class attribute, or after another function's `global` names it, is still the
    # builtin, while a nested function reading its enclosing function's parameter, and a function
    # reading what a walrus in its comprehension bound, read the file's own. A binding that lands
    # in a module or a class body is a row of its own and hides nothing, since Python looks it up
    # at run time: a class attribute, a store under `global`, `__builtins__ = {}`, `exec = exec`
    # and a walrus in a module-level comprehension. `import builtins` under the name hides nothing.
    scoped = (
        "def g(exec):\n    return exec\nexec('x')\n"
        "_ = [0 for eval in ()]\ndef h():\n    return eval('x')\n"
        "class K:\n    compile = len\n    def m(self):\n        return compile('x')\n"
        "def r():\n    global breakpoint\n    breakpoint = print\ndef s():\n    breakpoint()\n"
        "def outer(compile):\n    def inner():\n        return compile\n    return inner\n"
        "__builtins__ = {}\ndef t():\n    return __builtins__\n"
        "def u(exec):\n    def v():\n        global exec\n        return exec('x')\n    return v\n"
        "exec = exec\n_ = [(eval := e) for e in ()]\n"
        "def w():\n    _ = [(compile := c) for c in ()]\n    return compile('x')\n"
        "import builtins as breakpoint\nbreakpoint.exec('x')\n"
    )
    assert sorted(_dynamic_imports(ast.parse(scoped))) == [
        ("<module>", "__builtins__"),
        ("<module>", "breakpoint"),
        ("<module>", "compile"),
        ("<module>", "eval"),
        ("<module>", "exec"),
        ("<module>", "exec"),
        ("<module>", "exec"),
        ("h", "eval"),
        ("m", "compile"),
        ("r", "breakpoint"),
        ("s", "breakpoint"),
        ("t", "__builtins__"),
        ("v", "exec"),
    ]
    # Type parameters are evaluated around the `def` or `class` they belong to. The syntax is
    # 3.12's, so this case is parsed from text there and has nothing to read on 3.11.
    if sys.version_info >= (3, 12):
        generic = "def f[T: exec('x')]():\n    pass\nclass C[T: __import__('x')]:\n    pass\n"
        assert _dynamic_imports(ast.parse(generic)) == [
            ("<module>", "exec"),
            ("<module>", "__import__"),
        ]
