"""The core names no language stack: what one stack's runner, artifacts or package manager need
lives in that stack's profile directory, `src/stayfixed/profiles/<name>/`, so a repository in
several languages works with no configuration.

The walk reads every module under `src/stayfixed/` outside those stack directories with `ast` --
the profiles' own machinery directly under `profiles/` is core and is read -- so comments and
docstrings are prose and are never read; string and bytes constants (an f-string's literal parts
included) and identifiers are code and are. A word counts where it stands alone, letters and
digits on neither side, so `PYTEST`, `is_pytest_run` and `"*.pyc"` are mentions and
`pipeline` is not.

`STACK_NAMED` is every mention the walk finds, each with the reason it stays in the core, and the
comparison is equality both ways: a new mention reddens this test, and so does a pardon whose
mention is gone, so the list never outlives what it excuses.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Iterator
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "src" / "stayfixed"
PROFILES = PACKAGE / "profiles"

# One stack's test runner, build artifacts or package manager, for the common stacks. `uv` stands
# for itself rather than for `uv run`: the walk reads one constant at a time, and the command
# scanner spells its wrapper as the two words `("uv", "run")`.
STACK_WORDS = (
    "pytest",
    "pyc",
    "pycache",
    "venv",
    "pip",
    "poetry",
    "tox",
    "uv",
    "node_modules",
    "npm",
    "npx",
    "yarn",
    "pnpm",
    "jest",
    "vitest",
    "cargo",
    "mvn",
    "gradle",
)
_MENTION = re.compile(
    r"(?<![a-z0-9])(" + "|".join(re.escape(word) for word in STACK_WORDS) + r")(?![a-z0-9])"
)

# How many core modules the walk read when the pardons below were last measured: 138 on
# 2026-10-04, once the release tooling and the test-file audit had left the package. A floor and
# not an equality, so a new core module does not redden this test; it exists so that a walk that
# read nothing -- a moved package, a wrong root -- cannot pass by finding no mention. A removed
# module lowers it, in the same commit.
CORE_MODULES_AT_LEAST = 138

STACK_NAMED = {
    # The ledger scan's exclusions. `EXCLUDED_DIRNAMES` (`node_modules`, `.git`, `.venv`, `dist`,
    # `build`, `__pycache__`) are directories neither the mention scan nor the sweep walks into,
    # because they hold vendored, installed or generated trees in which nobody filed a reference;
    # `BINARY_SUFFIXES` (images, a PDF, audio, web fonts, `.zip` and `.pyc`) are files no
    # identifier can be read out of. The lists are not even-handed across stacks: they name
    # Python's and Node's trees and Python's bytecode suffix, and no other stack's (no `target/`,
    # no `vendor/`), so another stack's generated tree is scanned where these are skipped. What
    # they decide is which files the ledger reads, never which stack's runner is asked or advised.
    ("src/stayfixed/ledger/scan.py", "node_modules"),
    ("src/stayfixed/ledger/scan.py", "venv"),
    ("src/stayfixed/ledger/scan.py", "pycache"),
    ("src/stayfixed/ledger/scan.py", "pyc"),
    # The command scanner unwraps `uv run <cmd>` to `<cmd>`, as it unwraps `env <cmd>`. `uv run`
    # is a Python launcher, and it stays in the shared scanner rather than in the Python profile
    # because more than the profiles read commands through that unwrapping: the background-
    # cleanup guard (`guards/bgcleanup.py`) judges the command `uv run` launches, as every
    # profile's `recognises` does.
    ("src/stayfixed/guards/bashscan.py", "uv"),
    # stayfixed's own installer, `uv tool install`, named in two of `doctor`'s remedies
    # (`cli-path`, `overlay-requires`) and in `setup`'s pinned install command: the tool
    # stayfixed itself is installed with, not a stack a project is written in.
    ("src/stayfixed/doctor/checks.py", "uv"),
    ("src/stayfixed/setup/run.py", "uv"),
}


def _docstrings(tree: ast.AST) -> set[int]:
    found: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            first = node.body[0] if node.body else None
            if (
                isinstance(first, ast.Expr)
                and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)
            ):
                found.add(id(first.value))
    return found


def _code_text(tree: ast.AST) -> Iterator[str]:
    """Every string constant that is not a docstring, and every name the code spells."""
    prose = _docstrings(tree)
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if id(node) not in prose:
                yield node.value
        elif isinstance(node, ast.Constant) and isinstance(node.value, bytes):
            # Latin-1 maps every byte to one character, so an ASCII word in a bytes literal reads
            # as that word and no byte makes the decode fail.
            yield node.value.decode("latin-1")
        elif isinstance(node, ast.Name):
            yield node.id
        elif isinstance(node, ast.Attribute):
            yield node.attr
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            yield node.name
        elif isinstance(node, ast.arg | ast.keyword) and node.arg is not None:
            yield node.arg
        elif isinstance(node, ast.alias):
            yield node.name
            if node.asname is not None:
                yield node.asname
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            yield node.module


def _in_a_stack_directory(path: Path) -> bool:
    """True under `profiles/<name>/`, where one stack's knowledge belongs; `profiles/hints.py`
    and the rest of the machinery beside it are core."""
    return PROFILES in path.parents and path.parent != PROFILES


def _core_modules() -> list[Path]:
    return [path for path in sorted(PACKAGE.rglob("*.py")) if not _in_a_stack_directory(path)]


def stack_mentions(modules: list[Path]) -> set[tuple[str, str]]:
    found: set[tuple[str, str]] = set()
    for path in modules:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        module = path.relative_to(ROOT).as_posix()
        for text in _code_text(tree):
            for match in _MENTION.finditer(text.lower()):
                found.add((module, match.group(1)))
    return found


def words(text: str) -> set[str]:
    return {match.group(1) for match in _MENTION.finditer(text)}


def test_the_walk_reads_words_and_not_fragments() -> None:
    # The matcher's two edges, pinned on samples rather than inferred from the tree: a word is a
    # mention wherever an underscore, a dot or a space bounds it, and a longer word that merely
    # contains one is not. Reddened by dropping the lookbehind from `_MENTION` (`unpip` reads as
    # `pip`), and by dropping the lookahead (`pytests` reads as `pytest`); both measured.
    assert words("is_pytest_run *.pyc __pycache__ .venv tox_ini") == {
        "pytest",
        "pyc",
        "pycache",
        "venv",
        "tox",
    }
    assert words("pipeline unpip uvula pytests") == set()


def test_no_core_module_names_a_stack_it_does_not_pardon() -> None:
    # Oracle: `mutations/`, "the core names pytest again".
    modules = _core_modules()
    assert len(modules) >= CORE_MODULES_AT_LEAST
    assert stack_mentions(modules) == STACK_NAMED
