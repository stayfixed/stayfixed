"""The scratch projects `prove`'s real-runner tests run, built once for the acceptance cases and the
per-stack tests alike, and the marks a case of each runner carries.

Each builder writes a project its runner collects and nothing above it reads: pytest's has a
`pytest.ini`, a JavaScript one a `package.json` and its `node_modules` linked to the packages an
`npm ci` of `tests/fixtures/prove/node/` installed, and Go's is a copy of the fixture module.
"""

from __future__ import annotations

import shutil
from collections.abc import Mapping
from pathlib import Path

import pytest

from tests.prove.real_runners import installed_packages, node_modules, required, where

ROOT = Path(__file__).resolve().parents[2]
GO_MODULE = ROOT / "tests" / "fixtures" / "prove" / "go"

JEST_PASSING = 'test("passes", () => { expect(1).toBe(1); });\ntest.skip("skipped", () => {});\n'
JEST_SKIPPED = 'test.skip("one", () => {});\ntest.skip("two", () => {});\n'
VITEST_HEAD = 'import { test, expect } from "vitest";\n'
NODE_HEAD = 'import { test } from "node:test";\nimport assert from "node:assert/strict";\n'
NODE_PASSING = (
    NODE_HEAD + 'test("passes", () => { assert.ok(true); });\n'
    'test("skipped", { skip: true }, () => {});\n'
)
NODE_SKIPPED = (
    NODE_HEAD + 'test("one", { skip: true }, () => {});\ntest("two", { skip: true }, () => {});\n'
)
# Each JavaScript runner's test file name, its passing and its all-skipped text, and its
# `package.json`.
FILES = {
    "jest": ("three.test.js", JEST_PASSING, JEST_SKIPPED, '{"name": "case", "private": true}'),
    "vitest": (
        "three.test.js",
        VITEST_HEAD + JEST_PASSING,
        VITEST_HEAD + JEST_SKIPPED,
        '{"name": "case", "private": true, "type": "module"}',
    ),
    "node-test": (
        "three.test.mjs",
        NODE_PASSING,
        NODE_SKIPPED,
        '{"name": "case", "private": true}',
    ),
}
# The command each JavaScript runner is run by.
COMMANDS = {
    "jest": ["npx", "jest"],
    "vitest": ["npx", "vitest", "run"],
    "node-test": ["node", "--test"],
}
JS_RUNNERS = tuple(COMMANDS)


def pytest_project(
    root: Path,
    *,
    passing: int = 0,
    failing: int = 0,
    skipped: int = 0,
    files: Mapping[str, str] | None = None,
) -> Path:
    """A project pytest collects in `root`: a `pytest.ini`, so no configuration above it is read,
    and `test_scratch.py` with that many passing, failing and skipped tests, and `files` beside."""
    root.mkdir(parents=True, exist_ok=True)
    (root / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    tests = ["import pytest", ""]
    tests += [f"def test_pass_{index}():\n    pass\n" for index in range(passing)]
    tests += [f"def test_fail_{index}():\n    assert False\n" for index in range(failing)]
    tests += [
        f"@pytest.mark.skip(reason='scratch')\ndef test_skip_{index}():\n    pass\n"
        for index in range(skipped)
    ]
    (root / "test_scratch.py").write_text("\n".join(tests), encoding="utf-8")
    for name, text in (files or {}).items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text, encoding="utf-8")
    return root


def js_project(root: Path, runner: str, text: str | None = None) -> Path:
    """A project `runner` collects in `root`: its `package.json`, `node_modules` linked to the
    installed packages, and its test file holding `text` (none where `text` is empty)."""
    name, _, _, manifest = FILES[runner]
    root.mkdir(parents=True, exist_ok=True)
    (root / "package.json").write_text(manifest, encoding="utf-8")
    (root / "node_modules").symlink_to(installed_packages())
    if text:
        (root / name).write_text(text, encoding="utf-8")
    return root


def go_module(tmp_path: Path) -> Path:
    """The fixture module, copied where the run may build it."""
    return Path(shutil.copytree(GO_MODULE, tmp_path / "module"))


def needs(runner: str) -> list[pytest.MarkDecorator]:
    """The marks a case of `runner` carries: `runners`, and a skip where it is not installed and
    `STAYFIXED_REQUIRE_RUNNERS` does not require it, as `needs_runner` and `needs_packages` do."""
    if runner in JS_RUNNERS:
        missing = where("node") is None or node_modules() is None
    else:
        missing = where({"pytest": "pytest", "go-test": "go"}[runner]) is None
    marks = [pytest.mark.runners]
    if missing and not required():
        marks.append(pytest.mark.skip(reason=f"{runner} is not installed here"))
    return marks


def each_runner(*runners: str) -> list[object]:
    """One case per runner, each with its marks."""
    return [pytest.param(runner, marks=needs(runner)) for runner in runners]
