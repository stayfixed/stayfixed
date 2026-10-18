"""What the bug ledger writes and prints, held whole to literals captured from the tree.

A change to the engine is meant to leave every other byte of the ledger where it was: `bugs new`'s
entry, index and output, `bugs check`'s line and `--json`, and `renumber`'s files and output. A
test that asserts a fragment of each lets a reworded line or a reordered key through, so these
compare whole files with literals under `tests/fixtures/ledger/expected/`, outside the copied
project so no sweep or scan reads them. The capture day is written `{today}` there. A change meant
to move a byte re-captures its literal: run the case's argv on `fixture.ledger_copy` and write
what it printed or wrote there, the day replaced by `{today}`.

stayfixed:ledger:fixtures — the identifiers below are sample data, not claims about a ledger.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.gitfixture import needs_git
from tests.ledger.fixture import ARGV, CASES, Variant, literal, on_one_day


@needs_git
@pytest.mark.parametrize(
    ("case", "variant", "argv", "code"), CASES, ids=[case for case, *_ in CASES]
)
@pytest.mark.parametrize("json_output", [False, True], ids=["text", "json"])
def test_the_ledger_prints_its_captured_output(
    tmp_path: Path,
    case: str,
    variant: Variant,
    argv: list[str],
    code: int,
    json_output: bool,
) -> None:
    # Mutations (oracle), one or two cases each: `mutations/`'s "the stale index's finding drops its
    # remedy" -> check-broken's `--json` case, whose detail carries the remedy, the text line
    # carrying labels only; "bugs new names its entry by its absolute path" -> new's text cases;
    # "bugs new's --json drops its warning" -> new's `--json` cases; "bugs check's clean line says
    # less" -> check-clean; "bugs check passes a ledger with findings" -> check-broken's exit code;
    # "bugs renumber's line names no void pointer" -> renumber's text; "bugs renumber's --json
    # drops its unswept files" -> renumber's `--json`.
    stem = f"{case}.json" if json_output else case
    _, today, printed = on_one_day(tmp_path, variant, [*argv, "--json"] if json_output else argv)
    assert printed == (code, literal(f"{stem}.out", today), "")


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
    # rewrites: BR-003 names BR-002 in its title, its `related` list and its body. Mutation
    # (oracle): `mutations/`'s "renumber's void pointer relates to nothing" -> the void literal.
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
    # Mutation (oracle): `mutations/`'s "the index stops counting a section's entries".
    root, today, _ = on_one_day(tmp_path, "clean", ARGV["new"])
    index = (root / "docs" / "bug-reports.md").read_text(encoding="utf-8")
    assert index == literal("index.md", today)
