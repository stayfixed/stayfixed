"""Areas discovered by name: the half `stayfixed.cli`, `stayfixed.hooks.registry` and
`stayfixed.doctor.registry` share.

Three submodules are discovered, each by the module that reads it: an area's `commands.py` gives
it a CLI group, its `hooks.py` hook handlers, and its `doctor.py` rows in `stayfixed doctor`'s
report. The CLI frame and the hook registry import through `area_modules`, so an area that
fails to import fails them; the report imports through `area_imports`, which hands that failure
over in the area's place, because the report must outlive any one area's broken code.

A leaf module on purpose. `cli.py` imports every area through this discovery, so an area that
imported back into `cli.py` would constrain what the frame may ever import; the aliases and
the loop live here instead, and `cli` re-exports the aliases.
"""

from __future__ import annotations

import argparse
import importlib
import pkgutil
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING

import stayfixed

if TYPE_CHECKING:
    SubParsers = argparse._SubParsersAction[argparse.ArgumentParser]
else:
    # Generic only in typeshed: subscripting the class at runtime raises TypeError.
    SubParsers = argparse._SubParsersAction

Registrar = Callable[[SubParsers], None]

# The areas that make up the private layer: `overlay` renders and upgrades the overlay, `attach`
# binds a repository to it and unbinds it, and `memory` keeps the note store. Every other module
# under `src/stayfixed/` is the core. The core may not import a delivery area, through its
# `api.py` or otherwise, and a delivery area may import the core, so the private layer can be
# reworked without touching the core. The rule reads source, as discovery does, so a module named
# to `importlib` is invisible to it. `tests/test_areas.py`'s `test_core_never_imports_delivery`
# holds it, against the import statements of the one crossing still pinned, and
# `test_in_isolation_no_core_module_loads_a_delivery_area` holds that importing the core loads
# none of the private layer.
DELIVERY_AREAS: frozenset[str] = frozenset({"attach", "memory", "overlay"})


def _has_submodule(area: str, submodule: str) -> bool:
    """A filesystem probe: it imports only the `<area>.<submodule>` modules that exist, instead
    of importing every area package merely to test whether one of them does.

    That saving is latent rather than realised on today's frame: `main()` runs
    `discover_registrars()` to build the full argparse parser before argparse can dispatch to
    `hook`, and building that parser already imports `stayfixed.config`, `stayfixed.config.schema`,
    `stayfixed.presets`, `stayfixed.release` and `stayfixed.release.pins` — so by the time this
    probe runs for `hooks`, those packages are already loaded. The probe would only pay off if
    discovery ever registered just the area named on the command line instead of the full set.
    """
    for root in stayfixed.__path__:
        directory = Path(root) / area
        if (directory / f"{submodule}.py").is_file():
            return True
        if (directory / submodule / "__init__.py").is_file():
            return True
    return False


def _qualified(submodule: str) -> list[str]:
    """The qualified name of each `stayfixed.<area>.<submodule>` that exists, in area-name
    order: the one probe both importers below read."""
    return [
        f"stayfixed.{entry.name}.{submodule}"
        for entry in sorted(pkgutil.iter_modules(stayfixed.__path__), key=lambda m: m.name)
        if entry.ispkg and _has_submodule(entry.name, submodule)
    ]


def area_modules(submodule: str) -> list[ModuleType]:
    """Every `stayfixed.<area>.<submodule>` that exists, in area-name order, no shared registry."""
    return [importlib.import_module(name) for name in _qualified(submodule)]


def area_imports(submodule: str) -> list[tuple[str, ModuleType | Exception]]:
    """Every `stayfixed.<area>.<submodule>` that exists, in area-name order, each under its
    qualified name with the module, or with the exception its import raised in the module's place.

    For a reader that must outlive an area's broken code: `doctor`'s report, which is what a user
    has left when everything else is broken, so one area's `doctor.py` that raises on import must
    cost that area's rows and not the report. The failure is handed over rather than judged here,
    because what it costs is the reader's to say. `Exception` and not `BaseException`, as for a
    check that raises: a `KeyboardInterrupt` during discovery stops the command.
    """
    found: list[tuple[str, ModuleType | Exception]] = []
    for name in _qualified(submodule):
        try:
            found.append((name, importlib.import_module(name)))
        except Exception as exc:  # an area's broken import is handed over, never raised here
            found.append((name, exc))
    return found
