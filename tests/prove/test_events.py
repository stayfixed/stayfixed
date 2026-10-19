"""The event-stream reader counts the test-level events a runner framed, one JSON object a line.

A test-level event is one whose `Test` names a test; `pass`, `fail` and `skip` each count it once,
and a subtest is a test of its own. Text a test printed reaches the stream inside `output` events,
which count nothing. What the runner itself frames is counted as it frames it, which is the bound
`prove` states rather than a gap in it:

    The code under test, any file in the runner's load path, tracked or not, and the environment
    the runner reads can shape its report, so `proved` means the runner reported green on this
    tree, for the tests this command selected.
"""

from __future__ import annotations

import json

import pytest

from stayfixed.prove.counts import (
    MAX_REPORT_BYTES,
    REPORT_MALFORMED,
    REPORT_NOT_UTF8,
    REPORT_TOO_LARGE,
    Counts,
    ReportError,
)
from stayfixed.prove.events import read_events, read_line
from tests.prove.test_fixtures import REPORTS


def fixture(name: str) -> bytes:
    return (REPORTS / name).read_bytes()


def refusal(data: bytes) -> str:
    with pytest.raises(ReportError) as caught:
        read_events(data)
    return caught.value.reason


def stream(*events: dict[str, object]) -> bytes:
    return b"".join(json.dumps(event).encode() + b"\n" for event in events)


def test_events_count_test_level_actions() -> None:
    assert read_events(fixture("go.jsonl")) == Counts(1, 1, 1)


def test_a_subtest_is_a_test_of_its_own() -> None:
    # Five test-level outcomes: the three tests, the subtest, and the parent it ran in. The
    # package's own `fail` follows a failed test, so it adds nothing.
    assert read_events(fixture("go-subtest.jsonl")) == Counts(3, 1, 1)


def test_no_such_test_counts_nothing() -> None:
    assert read_events(fixture("go-run-no-such-test.jsonl")).total == 0


def test_testmain_exiting_zero_counts_nothing() -> None:
    assert read_events(fixture("go-testmain-exit0.jsonl")).total == 0


def test_a_build_failure_is_one_failed() -> None:
    # A `build-fail` event, which names no `Package`, and then the package's own `fail`: one
    # package that did not build, counted once.
    assert read_events(fixture("go-build-fail.jsonl")) == Counts(0, 1, 0)


def test_a_build_failure_with_no_package_fail_is_one_failed() -> None:
    lone = stream(
        {"ImportPath": "example.com/p [example.com/p.test]", "Action": "build-output"},
        {"ImportPath": "example.com/p [example.com/p.test]", "Action": "build-fail"},
    )
    assert read_events(lone) == Counts(0, 1, 0)


def test_a_build_failure_beside_another_package_s_fail_still_counts() -> None:
    events = stream(
        {"ImportPath": "example.com/p [example.com/p.test]", "Action": "build-fail"},
        {"Action": "fail", "Package": "example.com/q"},
    )
    assert read_events(events) == Counts(0, 2, 0)


def test_a_package_that_fails_with_no_failed_test_is_one_failed() -> None:
    # A `TestMain` that exits non-zero, a panic before any test, a vet failure: the package failed
    # and no test says so.
    events = stream(
        {"Action": "start", "Package": "example.com/p"},
        {"Action": "pass", "Package": "example.com/p", "Test": "TestA"},
        {"Action": "output", "Package": "example.com/p", "Output": "FAIL\n"},
        {"Action": "fail", "Package": "example.com/p"},
        {"Action": "pass", "Package": "example.com/q"},
    )
    assert read_events(events) == Counts(1, 1, 0)


def test_a_package_fail_after_its_failed_test_adds_nothing() -> None:
    events = stream(
        {"Action": "fail", "Package": "example.com/p", "Test": "TestA"},
        {"Action": "fail", "Package": "example.com/p"},
        {"Action": "fail", "Package": "example.com/q", "Test": "TestB"},
        {"Action": "fail", "Package": "example.com/q"},
    )
    assert read_events(events) == Counts(0, 2, 0)


def test_package_level_pass_and_skip_count_nothing() -> None:
    events = stream(
        {"Action": "skip", "Package": "example.com/no-test-files"},
        {"Action": "pass", "Package": "example.com/p"},
    )
    assert read_events(events).total == 0


def test_printed_text_is_never_counted() -> None:
    events = stream(
        {"Action": "output", "Package": "p", "Test": "TestA", "Output": "--- PASS: TestB\n"},
        {"Action": "output", "Package": "p", "Output": '{"Action":"pass","Test":"TestC"}\n'},
        {"Action": "run", "Package": "p", "Test": "TestA"},
        {"Action": "pause", "Package": "p", "Test": "TestA"},
        {"Action": "cont", "Package": "p", "Test": "TestA"},
        {"Action": "bench", "Package": "p", "Test": "BenchmarkA"},
        {"Action": "fail", "Package": "p", "Test": "TestA"},
    )
    assert read_events(events) == Counts(0, 1, 0)


def test_printed_framing_is_what_the_bound_concedes() -> None:
    # A `TestMain` printing the runner's own framing for a test that never ran gets a real `pass`
    # event for it from the runner, and that event is counted: the code under test can shape the
    # report, which is the first clause of the bound this module's docstring quotes.
    assert read_events(fixture("go-framing.jsonl")) == Counts(2, 0, 0)


@pytest.mark.parametrize(
    "line",
    [
        b"not json",
        b"[]",
        b'"pass"',
        b"{",
        b'{"Action": 1, "Package": "p"}',
        b'{"Package": "p"}',
        b'{"Action": "pass", "Package": "p", "Test": 7}',
        b'{"Action": "pass", "Package": "p", "Test": ""}',
        b'{"Action": "fail", "Package": ["p"]}',
        b'{"Action": "build-fail", "ImportPath": 3}',
    ],
)
def test_a_line_that_is_not_an_event_is_malformed(line: bytes) -> None:
    good = stream({"Action": "pass", "Package": "p", "Test": "TestA"})
    assert refusal(good + line + b"\n" + good) == REPORT_MALFORMED


@pytest.mark.parametrize(
    ("line", "detail"),
    [
        (b"not json", "line 2: JSONDecodeError"),
        (b"[]", "line 2 is not a JSON object"),
    ],
    ids=["no-json", "no-object"],
)
def test_a_refusal_names_the_line_it_stopped_at(line: bytes, detail: str) -> None:
    # A line that does not parse is named by its number like any other refusal. Mutation
    # (declared): the parser's refusal handed on as it is -> the detail names no line.
    good = stream({"Action": "pass", "Package": "p", "Test": "TestA"})
    with pytest.raises(ReportError) as caught:
        read_events(good + line + b"\n")
    assert (caught.value.reason, caught.value.detail) == (REPORT_MALFORMED, detail)


def test_a_stream_without_a_final_newline_reads() -> None:
    assert read_events(b'{"Action": "skip", "Package": "p", "Test": "TestA"}') == Counts(0, 0, 1)


def test_an_empty_stream_counts_nothing() -> None:
    assert read_events(b"").total == 0


def test_bytes_that_are_not_utf8_are_refused_as_such() -> None:
    assert refusal(b'{"Action": "output", "Output": "\xff"}\n') == REPORT_NOT_UTF8


def test_past_the_cap_is_refused_before_decoding() -> None:
    assert refusal(b"\xff" * (MAX_REPORT_BYTES + 1)) == REPORT_TOO_LARGE


# --- Which lines the reader reads anything from ----------------------------------------------

_OUTPUT_EVENT = {"Action": "output", "Package": "p", "Test": "TestA", "Output": "printed\n"}


@pytest.mark.parametrize("separators", [(",", ":"), (", ", ": ")], ids=["compact", "spaced"])
def test_an_output_event_is_the_one_line_left_unread(separators: tuple[str, str]) -> None:
    # test2json writes its events compact; the reader reads them however they are spaced.
    # Mutations (declared): every output event read -> the first assertion fails; no event read
    # -> the loop's.
    assert read_line(json.dumps(_OUTPUT_EVENT, separators=separators).encode() + b"\n") is False
    for event in (
        {"Action": "pass", "Package": "p", "Test": "TestA", "Output": "output"},
        {"Action": "run", "Package": "p", "Test": "output"},
        {"ImportPath": "p [p.test]", "Action": "build-output", "Output": "# p\n"},
    ):
        assert read_line(json.dumps(event, separators=separators).encode() + b"\n") is True


@pytest.mark.parametrize(
    "line",
    [
        b'{"Action":"output","Test":""}',
        b'{"Action":"output","Test":1}',
        b'{"Action":"output","Output":"\xff"}',
        b'[{"Action":"output"}]',
        b'"output"',
        b'{"Action":"output"',
        b"./x_test.go:3:1: syntax error",
    ],
    ids=[
        "empty-test",
        "test-not-a-string",
        "not-utf8",
        "not-an-object",
        "a-string",
        "cut",
        "text",
    ],
)
def test_a_line_the_reader_refuses_is_read_so_the_refusal_stands(line: bytes) -> None:
    # Mutations (declared): a refused line left unread -> each case reads as an output event's; a
    # line without the word `"output"` left unread -> `text`, a line go prints as text, is.
    assert read_line(line) is True
    with pytest.raises(ReportError):
        read_events(line)


@pytest.mark.parametrize(
    "name", ["go.jsonl", "go-subtest.jsonl", "go-build-fail.jsonl", "go-framing.jsonl"]
)
def test_the_lines_left_unread_change_no_count(name: str) -> None:
    whole = fixture(name)
    lines = whole.splitlines(keepends=True)
    kept = [line for line in lines if read_line(line)]
    assert len(kept) < len(lines)
    assert read_events(b"".join(kept)) == read_events(whole)
