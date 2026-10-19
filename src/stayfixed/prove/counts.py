"""What a runner's report says, as three numbers, and the ways a report fails to say it.

Every reader under `stayfixed.prove` answers one `Counts` or raises one `ReportError`, whose
`reason` is one of the constants below and never the parser's own message, so the verdict that
reads it can word each one itself. A reader counts the tests the report lists and never a total
the report states: a total is the runner's claim about its tests, and the tests are what is counted.

`within_cap` is the one size check. Each reader calls it before it reads a byte, so a report past
`MAX_REPORT_BYTES` is refused the same way whichever reader is asked, and
`stayfixed.prove.reports.read_report`, which picks the reader by the report's kind, checks nothing
itself. `utf8` and `strict_json` are the two JSON readers' shared first steps.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

# The report is larger than `MAX_REPORT_BYTES`.
REPORT_TOO_LARGE = "report-too-large"
# A format read as UTF-8 holds bytes that are not.
REPORT_NOT_UTF8 = "report-not-utf8"
# The bytes do not parse, or parse into a shape the format does not have.
REPORT_MALFORMED = "report-malformed"
# An XML report declares a doctype, which is where every entity declaration has to stand.
REPORT_DOCTYPE = "report-doctype"
# An XML report names an entity it never declared.
REPORT_ENTITY = "report-entity"

# A named cap: the longest report any reader here reads. A report is read whole into memory before
# it is counted, so this bounds what one run can make `prove` hold. 64 MiB is room for a suite of a
# few hundred thousand cases (a JUnit testcase with a long name and a short failure message is
# under 200 bytes) and far short of a CI runner's memory. An event stream's report holds only the
# lines its reader reads anything from (`stayfixed.prove.events.read_line`), so what a test prints
# never counts against it. No shipped file states it.
MAX_REPORT_BYTES = 64 * 1024 * 1024


@dataclass(frozen=True)
class Counts:
    """How many tests a report says passed, failed and were skipped."""

    passed: int
    failed: int
    skipped: int

    @property
    def total(self) -> int:
        return self.passed + self.failed + self.skipped


class ReportError(Exception):
    """A report that cannot be counted: `reason` is one of this module's `REPORT_*` constants,
    and `detail`, when there is one, is where the reader stopped, for a receipt to print.

    A value the report holds enters `detail` only through `printed.clipped`, so the detail is
    bounded in length and escaped however long or strange the value; nothing upstream bounds a
    status or a key but the report's own size."""

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(reason if not detail else f"{reason}: {detail}")
        self.reason = reason
        self.detail = detail


def within_cap(data: bytes) -> None:
    """Refuse `data` as `REPORT_TOO_LARGE` when it is longer than `MAX_REPORT_BYTES`."""
    if len(data) > MAX_REPORT_BYTES:
        raise ReportError(REPORT_TOO_LARGE, f"{len(data)} bytes, past {MAX_REPORT_BYTES}")


def utf8(data: bytes) -> str:
    """`data` decoded as UTF-8, or `REPORT_NOT_UTF8`."""
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ReportError(REPORT_NOT_UTF8, f"byte {exc.start}") from None


def strict_json(text: str) -> Any:
    """`text` parsed as JSON, or `REPORT_MALFORMED` when it does not parse or is past what the
    parser follows."""
    try:
        return json.loads(text)
    except RecursionError:
        raise ReportError(REPORT_MALFORMED, "nested deeper than this reader follows") from None
    except ValueError as exc:
        # `JSONDecodeError` is a `ValueError`, and so is an integer literal longer than the
        # interpreter converts.
        raise ReportError(REPORT_MALFORMED, type(exc).__name__) from None
