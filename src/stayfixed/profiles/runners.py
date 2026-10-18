"""What a test runner's adapter and the core say to each other about a runner's report.

A leaf: the adapters under `profiles/<stack>/` and the `prove` core both import it, and it imports
nothing from either, so neither reaches the other through it and no package cycle forms.

No entry in `mutations/` covers this module: it declares names and decides nothing. Which reader a
kind is read with is `stayfixed.prove.counts.read_report`'s, and its entries cover that.
"""

from __future__ import annotations

from enum import StrEnum


class ReportKind(StrEnum):
    """The report formats `prove` counts, each by the format's own name and never a runner's."""

    # JUnit XML: `testcase` elements.
    JUNIT = "junit"
    # The JSON test-results report: `testResults`, each with its `assertionResults`.
    RESULTS_JSON = "results-json"
    # The test event stream: one JSON object a line, each with its `Action`.
    EVENTS = "events"
