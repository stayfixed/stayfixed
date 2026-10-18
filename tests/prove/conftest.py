"""The `runners` marker, registered here so that `pyproject.toml` stays the release's to edit:
`--strict-markers` refuses a marker nothing registered, and `tests/prove/real_runners.py` says
what the marker means.

And the Go build cache those tests share. Every test runs under a `HOME` of its own
(`tests/conftest.py`), and `go` keeps its cache under it, so each real `go test` compiled the
standard library's `testing` and its dependencies afresh: about 7 s alone, about 20 s beside three
other workers, for each of some fifteen tests. The cache is content-addressed and safe to share
between processes, so the tests marked `runners` share one per worker, under pytest's own
temporary directory; nothing a test asserts reads it."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.prove.real_runners import MARK


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", f"{MARK}: runs a real test runner, skipped where none is")


@pytest.fixture(scope="session")
def _go_cache(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("go-build")


@pytest.fixture(autouse=True)
def _shared_go_cache(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch, _go_cache: Path
) -> None:
    if request.node.get_closest_marker(MARK) is not None:
        monkeypatch.setenv("GOCACHE", str(_go_cache))
