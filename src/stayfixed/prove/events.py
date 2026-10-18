"""Count the test-level events of a test event stream, one JSON object a line.

An event counts when its `Action` is `pass`, `fail` or `skip` and its `Test` names a test; a
subtest is a test of its own, and so is the test it ran in. Every other event counts nothing:
`run`, `pause`, `cont` and `output` say a test is under way or what it printed, and text a test
printed reaches the stream only inside an `output` event's `Output`, so no line a test writes is
ever read as an event. What the runner frames itself is counted as it frames it, which is the
bound `prove` states rather than a gap in it: "The code under test, any file in the runner's load
path, tracked or not, and the environment the runner reads can shape its report, so `proved` means
the runner reported green on this tree, for the tests this command selected."

A package-level event (no `Test`) counts nothing either, with two exceptions, so that a package
that failed with no failed test still fails the run:

- a package-level `fail` adds one failed when no test in that `Package` failed: a test program
  that exits non-zero before or after its tests, a panic before any test ran, a package that did
  not build;
- a `build-fail` event, which names an `ImportPath` (`p [p.test]`) and no `Package`, adds one
  failed when no package-level `fail` names the package its `ImportPath` starts with (the first
  space-separated word).

Both rules exist because a build failure arrives either way. The runners this was measured on
write a `build-fail` and then the package's own `fail` with no failed test, and that is one
package that did not build, counted once by the first rule; a stream holding the `build-fail`
alone still counts it by the second. Were the two ever counted together, a build failure would
count twice, which changes a count and never a verdict.

A line that is not a JSON object, an event with no string `Action`, or a `Test`, `Package` or
`ImportPath` of the wrong type is `REPORT_MALFORMED`: the stream is the runner's own, and a line in
it the runner did not write as an event is not one to count around. Empty lines are skipped. A
refusal names the line by its number and a key by its fixed name, never a value the stream holds.
"""

from __future__ import annotations

from collections import Counter

from stayfixed.prove.counts import (
    REPORT_MALFORMED,
    Counts,
    ReportError,
    strict_json,
    utf8,
    within_cap,
)

_PASSED = "pass"
_FAILED = "fail"
_SKIPPED = "skip"
_BUILD_FAIL = "build-fail"


def _optional_string(event: dict[str, object], key: str, line: int) -> str | None:
    value = event.get(key)
    if value is not None and not isinstance(value, str):
        raise ReportError(REPORT_MALFORMED, f"line {line}: {key} is not a string")
    return value


def read_events(data: bytes) -> Counts:
    """The test-level outcomes `data` streams, counted; `ReportError` when it cannot be counted."""
    within_cap(data)
    passed = failed = skipped = 0
    # Packages, by name: those with a failed test, and those that failed at package level.
    failed_a_test: set[str | None] = set()
    failed_whole: set[str | None] = set()
    # The package each `build-fail` names, once per event.
    unbuilt: Counter[str | None] = Counter()
    for number, line in enumerate(utf8(data).split("\n"), start=1):
        if not line.strip():
            continue
        event = strict_json(line)
        if not isinstance(event, dict):
            raise ReportError(REPORT_MALFORMED, f"line {number} is not a JSON object")
        action = event.get("Action")
        if not isinstance(action, str):
            raise ReportError(REPORT_MALFORMED, f"line {number} has no string Action")
        test = _optional_string(event, "Test", number)
        package = _optional_string(event, "Package", number)
        import_path = _optional_string(event, "ImportPath", number)
        if test == "":
            raise ReportError(REPORT_MALFORMED, f"line {number} names an empty Test")
        if test is not None:
            if action == _PASSED:
                passed += 1
            elif action == _FAILED:
                failed += 1
                failed_a_test.add(package)
            elif action == _SKIPPED:
                skipped += 1
        elif action == _FAILED:
            failed_whole.add(package)
        elif action == _BUILD_FAIL:
            unbuilt[import_path.split(" ", 1)[0] if import_path else None] += 1
    failed += len(failed_whole - failed_a_test)
    failed += sum(times for name, times in unbuilt.items() if name not in failed_whole)
    return Counts(passed, failed, skipped)
