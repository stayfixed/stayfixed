"""Count the assertions a JSON test-results report lists, by their status.

The report is one JSON object whose `testResults` is a list of file entries, one per test file,
each with `assertionResults`, a list of objects whose string `status` says how that test ended:
`passed` is passed, `failed` failed, and `pending`, `skipped`, `todo` and `disabled` skipped. The
set is closed: any other status, a missing key or a value of the wrong type is `REPORT_MALFORMED`,
a report this reader does not know how to count rather than one it guesses at.

The closed set is the assertions'. A file entry's own `status` is read for one rule only, and is
never refused: a file entry whose `status` is `failed` and which holds no failed assertion adds one
failed test, because that is a file that did not load, and its `assertionResults` is empty. Every
other file status, whatever a runner writes there (one writes `focused` for a file holding a
`todo`), counts nothing.

The `num*` totals beside the list are never read: for a file that did not load, the runners that
write this report count it nowhere in them, so a run with a broken test file reads one passed and
none failed.

The bytes are decoded as UTF-8 by `counts.utf8` and parsed by `jsonobject.json_object`.
"""

from __future__ import annotations

from typing import Any

from stayfixed.jsonobject import json_object
from stayfixed.printed import clipped
from stayfixed.prove.counts import (
    REPORT_MALFORMED,
    Counts,
    ReportError,
    malformed,
    utf8,
    within_cap,
)

_PASSED = frozenset({"passed"})
_FAILED = frozenset({"failed"})
_SKIPPED = frozenset({"pending", "skipped", "todo", "disabled"})
# What a file entry says of itself when it did not load.
_FILE_FAILED = "failed"


def _list_of_objects(value: object, where: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise ReportError(REPORT_MALFORMED, f"{where} is not a list of objects")
    return value


def read_results(data: bytes) -> Counts:
    """The assertions `data` lists, counted; `ReportError` when it cannot be counted."""
    within_cap(data)
    document = json_object(utf8(data), "the report", error=malformed)
    passed = failed = skipped = 0
    for entry in _list_of_objects(document.get("testResults"), "testResults"):
        assertions = _list_of_objects(entry.get("assertionResults"), "assertionResults")
        failed_here = 0
        for assertion in assertions:
            status = assertion.get("status")
            if not isinstance(status, str):
                raise ReportError(REPORT_MALFORMED, "an assertion has no string status")
            if status in _PASSED:
                passed += 1
            elif status in _FAILED:
                failed_here += 1
            elif status in _SKIPPED:
                skipped += 1
            else:
                raise ReportError(REPORT_MALFORMED, f"an assertion's status is {clipped(status)}")
        if entry.get("status") == _FILE_FAILED and failed_here == 0:
            failed_here = 1
        failed += failed_here
    return Counts(passed, failed, skipped)
