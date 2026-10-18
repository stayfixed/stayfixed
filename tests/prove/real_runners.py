"""The real test runners some of `prove`'s tests run, and what a test that needs one says.

A test that runs a real runner carries the `runners` marker and skips where the runner is not
installed, so the suite runs anywhere and the mutation oracle, which installs none, never depends
on one: every mutation is reddened by a test that runs no real runner. Where the
`STAYFIXED_REQUIRE_RUNNERS` variable is `1`, as in the CI job that installs every runner, a missing
runner fails the test instead, so a job that meant to run them cannot pass by skipping them all.

pytest comes from the project's own environment, the one running the suite: its console script
stands beside the interpreter (`sys.executable`'s directory), and nothing is installed for it.
"""

from __future__ import annotations

import os
import shutil
import sys
from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

import pytest

MARK = "runners"
REQUIRE = "STAYFIXED_REQUIRE_RUNNERS"

_Test = TypeVar("_Test", bound=Callable[..., object])


def where(name: str) -> Path | None:
    """The directory that holds the runner `name`'s program: the running interpreter's own first,
    then the first on `PATH`; `None` where neither does."""
    beside = Path(sys.executable).parent / name
    if beside.is_file() and os.access(beside, os.X_OK):
        return beside.parent
    found = shutil.which(name)
    return Path(found).parent if found is not None else None


def required() -> bool:
    """Whether a missing runner fails a test rather than skipping it."""
    return os.environ.get(REQUIRE) == "1"


def needs_runner(name: str) -> Callable[[_Test], _Test]:
    """Mark a test `runners`, and skip it where `name` is not installed and not `required()`."""

    def marked(test: _Test) -> _Test:
        test = pytest.mark.runners(test)
        if where(name) is None and not required():
            test = pytest.mark.skip(reason=f"{name} is not installed here")(test)
        return test

    return marked


def runner_directory(name: str) -> Path:
    """The directory `where(name)` names; a missing runner fails the test that asked, which only a
    test `needs_runner` did not skip can reach."""
    found = where(name)
    if found is None:
        pytest.fail(f"{name} is not installed and {REQUIRE}=1 requires it")
    return found
