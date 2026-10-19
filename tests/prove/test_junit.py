"""The JUnit reader counts what a runner's report holds, one `testcase` at a time.

Every dialect the recorded runners write is read the same way: each `testcase` at any depth is one
test, failed with a `failure` or `error` child, skipped with a `skipped` child, passed otherwise. A
suite's own totals are a claim about its testcases, so they are never read. The document is
streamed, and one that declares a doctype is refused before anything in it is read, because that
is where every entity declaration, and so every entity-expansion bomb, has to stand.
"""

from __future__ import annotations

import tracemalloc
from collections.abc import Mapping

import pytest

from stayfixed.prove.counts import (
    MAX_REPORT_BYTES,
    REPORT_DOCTYPE,
    REPORT_ENTITY,
    REPORT_MALFORMED,
    REPORT_TOO_LARGE,
    Counts,
    ReportError,
)
from stayfixed.prove.junit import read_junit
from tests.prove.test_fixtures import REPORTS


def fixture(name: str) -> bytes:
    return (REPORTS / name).read_bytes()


def refusal(data: bytes) -> str:
    with pytest.raises(ReportError) as caught:
        read_junit(data)
    return caught.value.reason


@pytest.mark.parametrize(
    ("report", "expected"),
    [
        ("pytest-xunit1.xml", Counts(1, 1, 1)),
        ("pytest-xunit2.xml", Counts(1, 1, 1)),
        ("pytest-record-xml-attribute.xml", Counts(1, 1, 1)),
        ("node-junit.xml", Counts(1, 1, 1)),
    ],
)
def test_each_dialect_counts_its_testcases(report: str, expected: Counts) -> None:
    assert read_junit(fixture(report)) == expected


@pytest.mark.parametrize("report", ["pytest-empty.xml", "node-empty.xml"])
def test_an_empty_run_counts_nothing(report: str) -> None:
    assert read_junit(fixture(report)).total == 0


@pytest.mark.parametrize(
    ("report", "skipped"), [("pytest-all-skipped.xml", 1), ("node-all-skipped.xml", 2)]
)
def test_an_all_skipped_run_counts_only_skips(report: str, skipped: int) -> None:
    assert read_junit(fixture(report)) == Counts(0, 0, skipped)


def test_the_whole_file_testcases_are_testcases_like_any_other() -> None:
    # Two files that did not load, beside one passing test: without a `drop`, the reader has no
    # notion of a whole-file testcase, and a failed one is a failure.
    assert read_junit(fixture("node-load-failure.xml")) == Counts(1, 2, 0)


def test_total_is_the_sum_of_the_three() -> None:
    assert Counts(2, 3, 4).total == 9


def test_suite_attributes_are_never_read() -> None:
    report = (
        b'<testsuites tests="99" failures="0"><testsuite tests="99" failures="0" errors="0" '
        b'skipped="7"><testcase name="t"><failure message="no"/></testcase></testsuite>'
        b"</testsuites>"
    )
    assert read_junit(report) == Counts(0, 1, 0)


def test_an_error_child_is_failed() -> None:
    report = (
        b'<testsuite><testcase name="setup broke"><error message="fixture"/></testcase>'
        b'<testcase name="ok"/></testsuite>'
    )
    assert read_junit(report) == Counts(1, 1, 0)


@pytest.mark.parametrize(
    "inside", [b'<skipped/><failure message="no"/>', b'<error message="no"/><skipped/>']
)
def test_a_failure_beside_a_skip_is_failed(inside: bytes) -> None:
    # Both orders: a skip met after the failure must not take its place.
    report = b'<testsuite><testcase name="t">' + inside + b"</testcase></testsuite>"
    assert read_junit(report) == Counts(0, 1, 0)


def test_a_testcase_at_any_depth_is_one_test() -> None:
    report = (
        b'<testsuites><testsuite name="outer"><testsuite name="inner">'
        b'<testcase name="deep"><skipped/></testcase></testsuite>'
        b'<testcase name="shallow"/></testsuite><testcase name="loose"/></testsuites>'
    )
    assert read_junit(report) == Counts(2, 0, 1)


def test_predefined_entities_and_character_references_read() -> None:
    seen: list[str] = []

    def keep(attributes: Mapping[str, str]) -> bool:
        seen.append(attributes["name"])
        return False

    report = b'<testsuite><testcase name="&lt;&gt;&amp;&apos;&quot; &#233;&#x41;"/></testsuite>'
    assert read_junit(report, drop=keep) == Counts(1, 0, 0)
    assert seen == ["<>&'\" éA"]


def test_a_billion_laughs_document_stops_at_its_doctype() -> None:
    entities = b"".join(
        b'<!ENTITY lol%d "%s">' % (level, b"&lol%d;" % (level - 1) * 10) for level in range(1, 10)
    )
    report = (
        b'<?xml version="1.0"?><!DOCTYPE lolz [<!ENTITY lol0 "lol">'
        + entities
        + b']><testsuite><testcase name="&lol9;"/></testsuite>'
    )
    assert refusal(report) == REPORT_DOCTYPE


def test_a_doctype_with_nothing_in_it_is_refused_too() -> None:
    assert refusal(b"<!DOCTYPE testsuite><testsuite/>") == REPORT_DOCTYPE


def test_an_undefined_entity_is_refused() -> None:
    assert refusal(b"<testsuite>&foo;</testsuite>") == REPORT_ENTITY


@pytest.mark.parametrize(
    "report",
    [b"", b"<testsuite>", b"<testsuite></testcase>", b"not xml at all", b"<a/><b/>"],
)
def test_a_document_that_does_not_parse_is_malformed(report: bytes) -> None:
    assert refusal(report) == REPORT_MALFORMED


def test_past_the_cap_is_refused_before_parsing() -> None:
    # One byte past the cap and not XML at all: the refusal is the cap's, so the length was asked
    # before the parser was.
    assert refusal(b"x" * (MAX_REPORT_BYTES + 1)) == REPORT_TOO_LARGE


def test_at_the_cap_is_read() -> None:
    head, tail = b"<testsuite><testcase/>", b"</testsuite>"
    padding = b" " * (MAX_REPORT_BYTES - len(head) - len(tail))
    assert read_junit(head + padding + tail) == Counts(1, 0, 0)


def test_drop_counts_a_testcase_nowhere() -> None:
    # Two testcases that stand for a whole file, neither failing: whether a failed one is dropped
    # is the predicate's to decide from the attributes, and this reader leaves that to it.
    report = (
        b'<testsuite><testcase name="one.test" file="/w/one.test"/>'
        b'<testcase name="two.test" file="/w/two.test"><system-out>x</system-out></testcase>'
        b'<testcase name="kept" file="/w/one.test"><skipped/></testcase></testsuite>'
    )
    asked: list[dict[str, str]] = []

    def whole_file(attributes: Mapping[str, str]) -> bool:
        asked.append(dict(attributes))
        return attributes["file"].endswith("/" + attributes["name"])

    assert read_junit(report, drop=whole_file) == Counts(0, 0, 1)
    assert asked == [
        {"name": "one.test", "file": "/w/one.test"},
        {"name": "two.test", "file": "/w/two.test"},
        {"name": "kept", "file": "/w/one.test"},
    ]


def test_a_refusal_quotes_nothing_the_document_holds() -> None:
    # A mismatched end tag a million characters long: the detail names the error from expat's
    # fixed table and where, and nothing else. Expat's own message quotes no document text either,
    # so length cannot tell the two apart; the exact detail does, since the exception's own text
    # is `mismatched tag: line 1, …`. Mutation (declared): the detail built from `str(exc)` ->
    # the detail differs.
    name = b"t" * 1_000_000
    with pytest.raises(ReportError) as caught:
        read_junit(b"<testsuite><" + name + b"></x></testsuite>")
    assert caught.value.reason == REPORT_MALFORMED
    assert caught.value.detail == "mismatched tag, line 1, column 1000015"
    assert len(str(caught.value)) < 250


def test_a_hundred_thousand_cases_count_in_bounded_memory() -> None:
    cases = 100_000
    report = (
        b'<?xml version="1.0" encoding="utf-8"?><testsuites><testsuite name="big">'
        + b"".join(
            b'<testcase classname="suite.module" name="test_case_%d" time="0.001"/>' % index
            for index in range(cases)
        )
        + b"</testsuite></testsuites>"
    )
    tracemalloc.start()
    try:
        counted = read_junit(report)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert counted == Counts(cases, 0, 0)
    assert peak < 8 * 1024 * 1024, f"peak {peak} bytes while reading {len(report)} bytes"


@pytest.mark.parametrize("child", ["failure", "error"])
def test_a_dropped_testcase_that_failed_counts_as_failed(child: str) -> None:
    # `drop` leaves a testcase out by its attributes alone, and a failure inside it is never left
    # out with it; a passed or skipped one is. Mutation (declared): a dropped testcase's children
    # unread -> the failure counts nowhere.
    report = (
        f'<testsuite><testcase name="a"><{child}/></testcase>'
        '<testcase name="b"/><testcase name="c"><skipped/></testcase></testsuite>'
    ).encode()
    assert read_junit(report, drop=lambda attributes: True) == Counts(0, 1, 0)


@pytest.mark.parametrize(
    ("inside", "counts"),
    [
        ('<skipped type="todo" message="true"/><failure message="not yet"/>', Counts(1, 0, 1)),
        ('<failure message="not yet"/><skipped type="todo"/>', Counts(1, 0, 1)),
        ('<skipped type="todo" message="reason"/>', Counts(1, 0, 1)),
        ('<skipped type="pytest.skip"/><failure/>', Counts(1, 1, 0)),
    ],
    ids=["failing", "failure-first", "passing", "another-skip"],
)
def test_a_todo_testcase_is_skipped_whatever_else_stands_in_it(inside: str, counts: Counts) -> None:
    # Node 24.10.0's JUnit reporter writes a `todo` test that fails as `<skipped type="todo"/>`
    # beside its `<failure>`, and node itself counts it as neither (its summary says `fail 0`, and
    # it exits 0): it is skipped here too. A failure beside any other skip is still a failure.
    # Mutation (declared): the todo skip not read -> the failing todo counts as failed.
    report = f'<testsuites><testcase name="real"/><testcase name="later">{inside}</testcase>'
    assert read_junit(f"{report}</testsuites>".encode()) == counts
