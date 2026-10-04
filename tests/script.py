"""The repository's scripts, loaded by path for the tests that drive them.

`scripts/` is not an importable package, so each script is loaded from its file. `load` is the one
loader: the mutation oracle's declarations (`tests/declarations.py`), the release script, the two
smoke scripts and the artifact checker all go through it, so a change to how a script is loaded is
made once. `release` is the release script, loaded once for every module that reads it — its own
tests, the repository's manifest test, `doctor`'s tests that write a release record, and the two
walks over every reader of a document that may not parse.
"""

from __future__ import annotations

import functools
import importlib.util
import sys
from pathlib import Path
from types import ModuleType

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def load(path: Path, name: str) -> ModuleType:
    """A fresh copy of the script at `path`, under the module name `name`.

    Registered in `sys.modules` before it is executed: every script is written under
    `from __future__ import annotations`, so every annotation is a string, and `@dataclass`
    resolves a field's annotations through `sys.modules[cls.__module__]` — a module absent from
    there makes the decorator raise before any test runs. A script that fails to load is taken
    out again, so the next load does not find half a module under its name.
    """
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        del sys.modules[name]
        raise
    return module


@functools.cache
def release() -> ModuleType:
    """`scripts/release.py` as a module, loaded once."""
    return load(SCRIPTS / "release.py", "release_script_under_test")
