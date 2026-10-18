"""What the bug ledger writes and prints, held to the bytes it wrote and printed before the register
engine learnt a list field.

A change to the engine is meant to leave every other byte of the ledger where it was: `bugs new`'s
entry, index and output, `bugs check`'s line and `--json`, and `renumber`'s files and output. A
test that asserts a fragment of each lets a reworded line or a reordered key through, so these
compare whole files with literals captured from the tree before the engine changed, under
`tests/fixtures/ledger/expected/`, outside the copied project so no sweep or scan reads them. The
capture day is written `{today}` there.

stayfixed:ledger:fixtures — the identifiers below are sample data, not claims about a ledger.
"""

from __future__ import annotations

import shutil
from datetime import date
from pathlib import Path
from typing import Literal

import pytest

from tests.cli import cli
from tests.gitfixture import git, needs_git

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "ledger"
PROJECT = FIXTURES / "project"
# The files the broken variant lays over the project, inside it only as the fixture keeps them.
BROKEN = "broken"
LITERALS = FIXTURES / "expected"

CASES = [
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
    ),
    # An empty `--source`: the bare `source:` line.
    (
        "new-bare",
        "clean",
        ["bugs", "new", "Plain", "--severity", "low", "--area", "ledger", "--no-fetch"],
    ),
    ("check-clean", "clean", ["bugs", "check"]),
    # Each of `unreadable-entry`, `dangling-related`, `evidence-boundary` and `stale-index` once.
    ("check-broken", "broken", ["bugs", "check"]),
    ("renumber", "clean", ["bugs", "renumber", "BR-002", "BR-009"]),
]
ARGV = {case: argv for case, _, argv in CASES}


def ledger_copy(tmp_path: Path, *, variant: Literal["clean", "broken"] = "clean") -> Path:
    """The fixture project in a fresh git repository of one commit, its broken files laid over it
    for `broken`.

    Committed, so the allocator's history query answers rather than warns, and the repository is
    the top of the checkout, so the scan and the sweep list the files git would.
    """
    root = tmp_path / "ledger"
    shutil.copytree(
        PROJECT, root, ignore=lambda where, _: [BROKEN] if where == str(PROJECT) else []
    )
    if variant == "broken":
        shutil.copytree(PROJECT / BROKEN, root, dirs_exist_ok=True)
    git(root, "init", "-q", "-b", "main")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "the ledger fixture")
    return root


def literal(name: str, today: str) -> str:
    # `str.replace`, never `str.format`: the `--json` literals hold braces of their own.
    return (LITERALS / name).read_text(encoding="utf-8").replace("{today}", today)


def on_one_day(
    tmp_path: Path, variant: Literal["clean", "broken"], argv: list[str]
) -> tuple[Path, str, tuple[int, str, str]]:
    """The copy, the day and what `argv` printed, from a run that began and ended on one day.

    A run across midnight writes one day and is compared with the other, so it runs once more on
    a fresh copy, which cannot cross midnight again.
    """
    for attempt in ("first", "again"):
        before = date.today().isoformat()
        root = ledger_copy(tmp_path / attempt, variant=variant)
        printed = cli(root, tmp_path, *argv)
        if date.today().isoformat() == before:
            break
    return root, before, printed


@needs_git
@pytest.mark.parametrize(("case", "variant", "argv"), CASES, ids=[case for case, _, _ in CASES])
@pytest.mark.parametrize("json_output", [False, True], ids=["text", "json"])
def test_the_ledger_prints_what_it_printed_before_the_list_field(
    tmp_path: Path,
    case: str,
    variant: Literal["clean", "broken"],
    argv: list[str],
    json_output: bool,
) -> None:
    # Mutation (oracle): `mutations/`'s "the stale index's finding drops its remedy" ->
    # check-broken's `--json` case, whose detail carries the remedy; the text line carries labels
    # only.
    stem = f"{case}.json" if json_output else case
    _, today, (code, out, err) = on_one_day(
        tmp_path, variant, [*argv, "--json"] if json_output else argv
    )
    assert out == literal(f"{stem}.out", today)
    assert err == literal(f"{stem}.err", today)
    assert f"{code}\n" == literal(f"{stem}.code", today)


@needs_git
@pytest.mark.parametrize("case", ["new", "new-bare"])
def test_new_writes_the_entry_it_wrote(tmp_path: Path, case: str) -> None:
    # Mutation (oracle): `mutations/`'s "an empty field is written with a trailing space" ->
    # new-bare, whose `source:` is the one empty field a line is written for; "every frontmatter
    # value is quoted" -> both.
    root, today, _ = on_one_day(tmp_path, "clean", ARGV[case])
    written = (root / "docs" / "bugs" / "BR-005.md").read_text(encoding="utf-8")
    assert written == literal(f"{case}.entry.md", today)


@needs_git
def test_renumber_leaves_the_files_it_left(tmp_path: Path) -> None:
    # The moved entry, the void pointer left at its old number, and the one entry the sweep
    # rewrites: BR-003 names BR-002 in its title, its `related` list and its body.
    root, today, _ = on_one_day(tmp_path, "clean", ARGV["renumber"])
    bugs = root / "docs" / "bugs"
    for name, expected in (
        ("BR-009.md", "renumber.moved.md"),
        ("BR-002.md", "renumber.void.md"),
        ("BR-003.md", "renumber.swept.md"),
    ):
        assert (bugs / name).read_text(encoding="utf-8") == literal(expected, today), name


@needs_git
def test_the_index_is_the_one_it_rendered(tmp_path: Path) -> None:
    root, today, _ = on_one_day(tmp_path, "clean", ARGV["new"])
    index = (root / "docs" / "bug-reports.md").read_text(encoding="utf-8")
    assert index == literal("index.md", today)
