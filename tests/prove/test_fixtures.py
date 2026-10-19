"""The recorded runner reports, held to the README that says where each one came from.

`tests/fixtures/prove/reports/` holds the bytes five test runners wrote, recorded once with the
runner's own command at a pinned version, so the readers under `stayfixed.prove` are tested
against what a runner really writes rather than against what a test author remembers of it. A
report nobody can trace to a runner, a version and a command is a hand-written guess, and a README
row naming a file that is gone is a claim about nothing; this test refuses both.

No mutation reddens it: the oracle mutates the package's source, and this test reads only the
fixture directory and its README.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures" / "prove"
REPORTS = FIXTURES / "reports"
README = FIXTURES / "README.md"

# A row of the README's table: `| `file` | runner | version | command | day |`.
_ROW = re.compile(r"^\|\s*`(?P<file>[^`]+)`\s*\|(?P<rest>.*)\|\s*$")
_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _rows() -> dict[str, list[str]]:
    rows: dict[str, list[str]] = {}
    for line in README.read_text(encoding="utf-8").splitlines():
        match = _ROW.match(line)
        if match is None:
            continue
        cells = [cell.strip() for cell in match["rest"].split("|")]
        assert match["file"] not in rows, f"{match['file']} is listed twice"
        rows[match["file"]] = cells
    return rows


def test_every_recorded_report_is_listed_with_its_version() -> None:
    recorded = sorted(path.name for path in REPORTS.iterdir() if path.is_file())
    assert recorded, "no report is recorded"
    rows = _rows()
    assert sorted(rows) == recorded
    for name, cells in rows.items():
        assert len(cells) == 4, f"{name}: runner, version, command and day, got {cells}"
        runner, version, command, day = cells
        assert runner and command, name
        assert re.search(r"\d+\.\d+\.\d+", version), f"{name}: no version in {version!r}"
        assert _DAY.match(day), f"{name}: {day!r} is not a day"
