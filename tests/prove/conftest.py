"""The `runners` marker, registered here so that `pyproject.toml` stays the release's to edit:
`--strict-markers` refuses a marker nothing registered, and `tests/prove/real_runners.py` says
what the marker means."""

from __future__ import annotations

import pytest

from tests.prove.real_runners import MARK


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", f"{MARK}: runs a real test runner, skipped where none is")
