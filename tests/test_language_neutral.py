"""The core names no language stack: what one stack's runner, artifacts or package manager need
lives in that stack's profile under `src/stayfixed/profiles/`, so a repository in several
languages works with no configuration.

The walk reads every module under `src/stayfixed/` outside `profiles/` with `ast`, so comments
and docstrings are prose and are never read; string constants (an f-string's literal parts
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

# How many core modules the walk read when the pardons below were measured. A floor and not an
# equality, so a new core module does not redden this test; it exists so that a walk that read
# nothing -- a moved package, a wrong root -- cannot pass by finding no mention.
CORE_MODULES_AT_LEAST = 135

STACK_NAMED = {
    # The scan's exclusion lists name every common stack's vendored and generated trees and
    # binary suffixes, so the ledger's mention scan and its sweep skip them all: polyglot by
    # construction, and acting on no single stack.
    ("src/stayfixed/ledger/scan.py", "node_modules"),
    ("src/stayfixed/ledger/scan.py", "venv"),
    ("src/stayfixed/ledger/scan.py", "pycache"),
    ("src/stayfixed/ledger/scan.py", "pyc"),
    # The command scanner unwraps `uv run <cmd>` to `<cmd>`, the shape CI writes its commands
    # in, as it unwraps `env <cmd>`: what it hands on is the command itself, so the unwrapping
    # is neutral in effect and every profile's recognition reads through it.
    ("src/stayfixed/guards/bashscan.py", "uv"),
    # stayfixed's own installer, `uv tool install`, named in `doctor`'s remedy and in `setup`'s
    # pinned install command: the runtime stayfixed itself is installed with, not a stack a
    # project is written in.
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


def _core_modules() -> list[Path]:
    return [path for path in sorted(PACKAGE.rglob("*.py")) if PROFILES not in path.parents]


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
