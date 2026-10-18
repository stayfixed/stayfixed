"""Count a report by the reader for its kind.

Its own module and not `counts`: each reader imports `counts` for `Counts`, `ReportError` and the
size check, so the one function that imports every reader cannot live there without a cycle.
`read_report` checks nothing itself; every reader asks `counts.within_cap` before it reads a byte.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping

from stayfixed.profiles.runners import ReportKind
from stayfixed.prove.counts import Counts
from stayfixed.prove.events import read_events
from stayfixed.prove.junit import read_junit
from stayfixed.prove.results import read_results


def read_report(
    kind: ReportKind,
    data: bytes,
    *,
    drop: Callable[[Mapping[str, str]], bool] | None = None,
) -> Counts:
    """`data` counted by the reader for `kind`. `drop` is the JUnit reader's: the other formats
    hold nothing that is not a test, and it is not asked for them."""
    if kind is ReportKind.JUNIT:
        return read_junit(data, drop=drop)
    if kind is ReportKind.RESULTS_JSON:
        return read_results(data)
    return read_events(data)
