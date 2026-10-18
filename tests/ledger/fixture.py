"""The ledger fixture project, its broken variant, and the literals captured from it.

Shared by `test_literals.py`, which holds what the ledger writes and prints to those literals, and
by the tests that run the same commands beside an entry the literals do not cover.

stayfixed:ledger:fixtures — the identifiers below are sample data, not claims about a ledger.
"""

from __future__ import annotations

import shutil
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Literal

from tests.cli import cli
from tests.gitfixture import git

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "ledger"
PROJECT = FIXTURES / "project"
# The files the broken variant lays over the project.
BROKEN = FIXTURES / "broken"
LITERALS = FIXTURES / "expected"

Variant = Literal["clean", "broken"]

# Each case: its name, which is its literals' stem, the variant it runs on, its argv, and its exit
# code, which `--json` does not change.
CASES: list[tuple[str, Variant, list[str], int]] = [
    (
        "new",
        "clean",
        [
            "bugs",
            "new",
            "A title: with a colon",
            "--severity",
            "high",
            "--area",
            "ledger",
            "--source",
            "#12 in the tracker",
            "--related",
            "BR-001",
            "--no-fetch",
        ],
        0,
    ),
    # An empty `--source`: the bare `source:` line.
    (
        "new-bare",
        "clean",
        ["bugs", "new", "Plain", "--severity", "low", "--area", "ledger", "--no-fetch"],
        0,
    ),
    ("check-clean", "clean", ["bugs", "check"], 0),
    # Each of `unreadable-entry`, `dangling-related`, `evidence-boundary` and `stale-index` once.
    ("check-broken", "broken", ["bugs", "check"], 1),
    ("renumber", "clean", ["bugs", "renumber", "BR-002", "BR-009"], 0),
]
ARGV = {case: argv for case, _, argv, _ in CASES}


def ledger_copy(tmp_path: Path, *, variant: Variant = "clean") -> Path:
    """The fixture project in a fresh git repository of one commit, the broken files laid over it
    for `broken`.

    Committed, so the allocator's history query answers rather than warns, and the repository is
    the top of the checkout, so the scan and the sweep list the files git would.
    """
    root = tmp_path / "ledger"
    shutil.copytree(PROJECT, root)
    if variant == "broken":
        shutil.copytree(BROKEN, root, dirs_exist_ok=True)
    git(root, "init", "-q", "-b", "main")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "the ledger fixture")
    return root


def literal(name: str, today: str) -> str:
    # `str.replace`, never `str.format`: the `--json` literals hold braces of their own.
    return (LITERALS / name).read_text(encoding="utf-8").replace("{today}", today)


def on_one_day(
    tmp_path: Path,
    variant: Variant,
    argv: list[str],
    *,
    prepare: Callable[[Path], object] = lambda _: None,
) -> tuple[Path, str, tuple[int, str, str]]:
    """The copy, the day and what `argv` printed, from a run that began and ended on one day;
    `prepare` is handed the copy before the run.

    A run across midnight writes one day and is compared with the other, so it runs once more on
    a fresh copy, which cannot cross midnight again.
    """
    for attempt in ("first", "again"):
        before = date.today().isoformat()
        root = ledger_copy(tmp_path / attempt, variant=variant)
        prepare(root)
        printed = cli(root, tmp_path, *argv)
        if date.today().isoformat() == before:
            break
    return root, before, printed
