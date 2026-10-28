"""`hook-entries`, the core row that counts the hook entries in every settings file:
`stayfixed.doctor.entries`. The row's verdicts over a whole report are
`tests/doctor/test_checks.py`'s; these cases hold what the module states of itself.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from stayfixed.harnesses import CLAUDE

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")


def test_the_row_reads_the_machines_settings_file_off_the_harness_registry() -> None:
    # The row needs one fact of the machine's settings file, its path under the home directory,
    # which is Claude Code's and the registry states. Asked of `setup.api`, it loaded `setup.run`
    # with the report, and closed a dependency cycle between `doctor`, `setup` and `overlay`.
    # Mutation (oracle): `mutations/`'s "hook-entries asks setup for the machine's settings
    # file" -> `stayfixed.setup` is loaded.
    #
    # The tree this file sits in, put first on the path, and not `-I`, which drops `PYTHONPATH`:
    # the installed package would be imported instead, whichever tree the test belongs to.
    source = Path(__file__).resolve().parents[2] / "src"
    probe = (
        "import sys, stayfixed.doctor.entries as e\n"
        "print(e.__file__)\n"
        "print(e.USER_SETTINGS)\n"
        "print(' '.join(sorted(m for m in sys.modules if m.startswith('stayfixed.setup'))))\n"
    )
    done = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True,
        text=True,
        check=False,
        env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(source)},
    )
    assert done.returncode == 0, done.stderr
    imported, settings, loaded, _ = done.stdout.split("\n")
    assert Path(imported).is_relative_to(source), imported
    assert (settings, loaded) == (CLAUDE.settings[0], "")
