"""The results reader counts the assertions a JSON test-results report lists, by their status.

The report is the one object whose `testResults` lists a file entry per test file, each holding
its `assertionResults`. Each assertion's `status` is one of a closed set, and anything outside it
is a report this reader does not know how to count. The `num*` totals beside the list are the
runner's claim about it and are never read. A file entry's own `status` is read for one thing: a
file that failed with no failed assertion in it is a file that never loaded, and counts as one
failed test, where the totals the runner wrote count it nowhere.
"""

from __future__ import annotations

import json

import pytest

from stayfixed.profiles.runners import ReportKind
from stayfixed.prove.counts import (
    MAX_REPORT_BYTES,
    REPORT_MALFORMED,
    REPORT_NOT_UTF8,
    REPORT_TOO_LARGE,
    Counts,
    ReportError,
)
from stayfixed.prove.events import read_events
from stayfixed.prove.junit import read_junit
from stayfixed.prove.reports import read_report
from stayfixed.prove.results import read_results
from tests.prove.test_fixtures import REPORTS


def fixture(name: str) -> bytes:
    return (REPORTS / name).read_bytes()


def refusal(data: bytes) -> str:
    with pytest.raises(ReportError) as caught:
        read_results(data)
    return caught.value.reason


def report(*files: object) -> bytes:
    return json.dumps({"numPassedTests": 0, "testResults": list(files)}).encode()


def file_entry(*statuses: str, status: str = "passed") -> dict[str, object]:
    return {
        "name": "/work/a.test.js",
        "status": status,
        "assertionResults": [{"title": f"t{n}", "status": s} for n, s in enumerate(statuses)],
    }


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("jest.json", Counts(1, 1, 1)),
        ("vitest.json", Counts(1, 1, 1)),
        ("jest-todo.json", Counts(1, 0, 2)),
        ("vitest-todo.json", Counts(1, 0, 2)),
    ],
)
def test_results_count_assertions_by_status(name: str, expected: Counts) -> None:
    assert read_results(fixture(name)) == expected


@pytest.mark.parametrize(
    "name", ["jest-empty.json", "jest-empty-pass-with-no-tests.json", "vitest-empty.json"]
)
def test_an_empty_results_report_counts_nothing(name: str) -> None:
    assert read_results(fixture(name)).total == 0


@pytest.mark.parametrize("name", ["jest-all-skipped.json", "vitest-all-skipped.json"])
def test_an_all_skipped_results_report_counts_only_skips(name: str) -> None:
    assert read_results(fixture(name)) == Counts(0, 0, 2)


@pytest.mark.parametrize("name", ["jest-load-failure.json", "vitest-load-failure.json"])
def test_a_file_that_does_not_load_is_one_failed(name: str) -> None:
    # The recorded totals say one passed and none failed.
    assert read_results(fixture(name)) == Counts(1, 1, 0)


def test_a_failed_file_with_a_failed_assertion_adds_nothing_more() -> None:
    assert read_results(report(file_entry("passed", "failed", status="failed"))) == Counts(1, 1, 0)


@pytest.mark.parametrize("status", ["focused", "skipped", "passed", "runtime-error", None])
def test_a_file_entry_s_own_status_is_never_refused(status: str | None) -> None:
    # One runner writes `focused` for a file that holds a `todo`; whatever a file entry says of
    # itself, only `failed` is read.
    entry = file_entry("passed", "todo")
    if status is None:
        del entry["status"]
    else:
        entry["status"] = status
    assert read_results(report(entry)) == Counts(1, 0, 1)


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        ("passed", Counts(1, 0, 0)),
        ("failed", Counts(0, 1, 0)),
        ("pending", Counts(0, 0, 1)),
        ("skipped", Counts(0, 0, 1)),
        ("todo", Counts(0, 0, 1)),
        ("disabled", Counts(0, 0, 1)),
    ],
)
def test_each_assertion_status_counts_once(status: str, expected: Counts) -> None:
    assert read_results(report(file_entry(status))) == expected


def test_results_totals_are_never_read() -> None:
    document = json.loads(report(file_entry("failed", status="failed")))
    document.update(numPassedTests=99, numFailedTests=0, numTotalTests=99, success=True)
    assert read_results(json.dumps(document).encode()) == Counts(0, 1, 0)


def test_a_duplicate_key_is_malformed() -> None:
    # The last of two keys is what a plain parse keeps, so a second `status` could stand in for
    # the first; neither is read.
    data = b'{"testResults": [{"assertionResults": [{"status": "failed", "status": "passed"}]}]}'
    assert refusal(data) == REPORT_MALFORMED


def test_a_duplicate_key_anywhere_is_malformed() -> None:
    assert refusal(b'{"testResults": [], "testResults": []}') == REPORT_MALFORMED


@pytest.mark.parametrize("status", ["focused", "PASSED", "flaky", "", 1, None])
def test_an_unknown_status_is_malformed(status: object) -> None:
    data = json.dumps({"testResults": [{"assertionResults": [{"status": status}]}]}).encode()
    assert refusal(data) == REPORT_MALFORMED


@pytest.mark.parametrize(
    "document",
    [
        b"",
        b"not json",
        b"[]",
        b'"testResults"',
        b"{}",
        b'{"testResults": {}}',
        b'{"testResults": [1]}',
        b'{"testResults": [{}]}',
        b'{"testResults": [{"assertionResults": {}}]}',
        b'{"testResults": [{"assertionResults": ["passed"]}]}',
        b'{"testResults": [{"assertionResults": [{"title": "no status"}]}]}',
        b"[" * 100_000 + b"]" * 100_000,
        b'{"testResults": [], "n": ' + b"9" * 5_000 + b"}",
    ],
)
def test_a_report_of_another_shape_is_malformed(document: bytes) -> None:
    assert refusal(document) == REPORT_MALFORMED


def test_bytes_that_are_not_utf8_are_refused_as_such() -> None:
    assert refusal(b'{"testResults": [], "x": "\xff"}') == REPORT_NOT_UTF8


def test_past_the_cap_is_refused_before_decoding() -> None:
    assert refusal(b"\xff" * (MAX_REPORT_BYTES + 1)) == REPORT_TOO_LARGE


@pytest.mark.parametrize("kind", list(ReportKind))
def test_read_report_caps_every_kind(kind: ReportKind) -> None:
    with pytest.raises(ReportError) as caught:
        read_report(kind, b"\xff" * (MAX_REPORT_BYTES + 1))
    assert caught.value.reason == REPORT_TOO_LARGE


@pytest.mark.parametrize(
    ("kind", "name"),
    [
        (ReportKind.JUNIT, "pytest-xunit2.xml"),
        (ReportKind.RESULTS_JSON, "jest.json"),
        (ReportKind.EVENTS, "go.jsonl"),
    ],
)
def test_read_report_reads_each_kind_with_its_reader(kind: ReportKind, name: str) -> None:
    reader = {
        ReportKind.JUNIT: read_junit,
        ReportKind.RESULTS_JSON: read_results,
        ReportKind.EVENTS: read_events,
    }[kind]
    assert read_report(kind, fixture(name)) == reader(fixture(name)) == Counts(1, 1, 1)


def test_read_report_hands_drop_to_the_junit_reader() -> None:
    def everything(_attributes: object) -> bool:
        return True

    assert read_report(ReportKind.JUNIT, fixture("node-junit.xml"), drop=everything).total == 0
