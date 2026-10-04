"""Areas discovered by name: the half `stayfixed.cli` and `stayfixed.hooks.registry` share.

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


def area_modules(submodule: str) -> list[ModuleType]:
    """Every `stayfixed.<area>.<submodule>` that exists, in area-name order, no shared registry."""
    modules: list[ModuleType] = []
    for entry in sorted(pkgutil.iter_modules(stayfixed.__path__), key=lambda m: m.name):
        if not entry.ispkg or not _has_submodule(entry.name, submodule):
            continue
        modules.append(importlib.import_module(f"stayfixed.{entry.name}.{submodule}"))
    return modules
