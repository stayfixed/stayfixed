"""Count a JUnit XML report's testcases, streamed, refusing a doctype.

Every `testcase` element, at any depth, is one test: failed when a `failure` or `error` element
stands inside it, skipped when a `skipped` element does and nothing failed, passed otherwise; and
skipped whatever else stands inside it where its `skipped` is `type="todo"`, a test its runner
marks as not done yet and does not count as failed when it fails (`TODO`). A
suite's `tests`, `failures`, `errors` and `skipped` attributes are never read: they are what the
writer says about its testcases, and the testcases are what is counted. Each dialect the shipped
runners write reads the same way, the nested `testsuites`/`testsuite` form and the flat one alike.

The document is fed to `xml.parsers.expat` in chunks, and its handlers keep three counters and one
byte per testcase still open, never a tree, so a report of a hundred thousand cases is counted in
the memory of a few of them.

A doctype is refused before anything inside it is read (`REPORT_DOCTYPE`). Every entity
declaration has to stand in a doctype, so an entity-expansion bomb meets this refusal before it
declares anything; no runner this reads writes one. Without a doctype, the only entities a
document can name are XML's five predefined ones and character references, which read as the
characters they stand for, and any other name is `REPORT_ENTITY`.

`drop`, when given, is asked each testcase's attributes as it opens; a true answer counts that
testcase nowhere unless a `failure` or `error` stands inside it, so a failure is never dropped. It
is how an adapter leaves out a testcase that is not a test, such as one a writer emits for a whole
file rather than for a test in it: a passed or skipped one counts nothing, and a failed one counts
as failed, whatever the predicate said of its attributes.

No text the document holds reaches a refusal: `REPORT_ENTITY` and `REPORT_MALFORMED` carry the
parser's own fixed message for the error and where it stopped, never the name or token it stopped
at.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from xml.parsers import expat

from stayfixed.prove.counts import (
    REPORT_DOCTYPE,
    REPORT_ENTITY,
    REPORT_MALFORMED,
    Counts,
    ReportError,
    within_cap,
)

_TESTCASE = "testcase"
_FAILED_BY = frozenset({"failure", "error"})
_SKIPPED_BY = "skipped"
# The `type` of a `skipped` element that marks a test as not done yet. Node's JUnit reporter
# (measured on 24.10.0) writes `<skipped type="todo"/>` for a `todo` test, and beside it the
# `<failure>` where the test fails, which node itself counts as neither passed nor failed: its own
# summary says `fail 0`, and it exits 0. So such a testcase is skipped, failure or none.
TODO = "todo"

# What one open testcase has met so far, one byte each on the stack of open testcases.
_PASSED = 0
_FAILED = 1
_SKIPPED = 2
_DROPPED = 3
_TODO = 4

# A named cap: how many bytes are handed to the parser at once, which bounds the copy expat keeps
# of its input. Any size reads the same document the same way; 64 KiB keeps the copy far below the
# memory a report's own bytes take. No shipped file states it.
_CHUNK = 64 * 1024


class _Tally:
    """The parser's handlers and the little they keep: three counters and the open testcases."""

    def __init__(self, drop: Callable[[Mapping[str, str]], bool] | None) -> None:
        self.passed = 0
        self.failed = 0
        self.skipped = 0
        self._drop = drop
        # One byte per testcase that has opened and not closed: a testcase inside a testcase is a
        # test of its own, and what stands inside belongs to the innermost one.
        self._open = bytearray()

    def start(self, name: str, attributes: dict[str, str]) -> None:
        if name == _TESTCASE:
            dropped = self._drop is not None and self._drop(attributes)
            self._open.append(_DROPPED if dropped else _PASSED)
        elif not self._open:
            return
        elif name == _SKIPPED_BY and attributes.get("type") == TODO:
            if self._open[-1] != _DROPPED:
                self._open[-1] = _TODO
        elif name in _FAILED_BY:
            # A dropped testcase too: a failure is never dropped. A todo's failure is no failure.
            if self._open[-1] != _TODO:
                self._open[-1] = _FAILED
        elif name == _SKIPPED_BY and self._open[-1] == _PASSED:
            self._open[-1] = _SKIPPED

    def end(self, name: str) -> None:
        if name != _TESTCASE:
            return
        outcome = self._open.pop()
        if outcome == _FAILED:
            self.failed += 1
        elif outcome in (_SKIPPED, _TODO):
            self.skipped += 1
        elif outcome == _PASSED:
            self.passed += 1


def _refuse_doctype(*_declaration: object) -> None:
    raise ReportError(REPORT_DOCTYPE)


def read_junit(data: bytes, *, drop: Callable[[Mapping[str, str]], bool] | None = None) -> Counts:
    """The testcases `data` holds, counted; `ReportError` when it cannot be counted."""
    within_cap(data)
    tally = _Tally(drop)
    parser = expat.ParserCreate()
    parser.StartDoctypeDeclHandler = _refuse_doctype
    parser.StartElementHandler = tally.start
    parser.EndElementHandler = tally.end
    view = memoryview(data)
    try:
        for offset in range(0, len(view), _CHUNK):
            parser.Parse(view[offset : offset + _CHUNK], False)
        parser.Parse(b"", True)
    except expat.ExpatError as exc:
        where = f"line {exc.lineno}, column {exc.offset}"
        if exc.code == expat.errors.codes[expat.errors.XML_ERROR_UNDEFINED_ENTITY]:
            raise ReportError(REPORT_ENTITY, where) from None
        raise ReportError(REPORT_MALFORMED, f"{expat.errors.messages[exc.code]}, {where}") from None
    return Counts(tally.passed, tally.failed, tally.skipped)
