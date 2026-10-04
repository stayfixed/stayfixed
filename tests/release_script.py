"""`scripts/release.py`, loaded by path for the tests that drive it.

`scripts/` is not an importable package, so the script is loaded the way `tests/declarations.py`
loads the mutation oracle. Here rather than in each test module that needs it — the script's own
tests, the repository's manifest test, `doctor`'s tests that write a release record, and the two
walks over every reader of a document that may not parse — so all of them read one copy.
"""

from __future__ import annotations

import functools
import importlib.util
import sys
from pathlib import Path
from types import ModuleType

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "release.py"
NAME = "release_script_under_test"


@functools.cache
def release() -> ModuleType:
    """The script as a module, loaded once.

    Registered in `sys.modules` before it is executed: `@dataclass` and the type hints a test
    resolves look the module up there by name, and under `from __future__ import annotations`
    a module absent from it cannot be resolved at all.
    """
    spec = importlib.util.spec_from_file_location(NAME, SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[NAME] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        del sys.modules[NAME]
        raise
    return module
