"""The doctor area's `api.py` is held to the same contract every other area's is.

CONTRIBUTING states it once for all of them: "`api.py` is the area's import surface. Other
areas import from it and from nothing else, and its `__all__` must equal exactly what it
imports — a test parses the file and checks."
"""

from __future__ import annotations

import stayfixed.doctor.api as doctor


def test_the_surface_carries_what_every_consumer_reaches_for() -> None:
    # An equality and not a subset, for the reason tests/guards/test_surface.py gives: a subset
    # lets an export arrive unnoticed. What each name is doing here is written beside it, so
    # this set states the policy `api.py`'s docstring states rather than freezing today's list.
    # No mutation entry: the mutation is adding an export, which is two lines in `api.py` (the
    # import and the `__all__` entry) and not one substituted line. Measured by hand instead —
    # re-exporting `checks.NAMED_ROOT_CAVEAT` reddens this test and this test alone.
    required = {
        # the status vocabulary a reader of a `Check` branches on. `tests/test_install_path.py`
        # branches on RED and SKIP (`stayfixed assess` runs no doctor check); the set is the
        # export rather than the members that have a caller today, for the reason
        # `attach/api.py` gives about `Binding.state` — half a closed vocabulary is unreadable.
        "OK",
        "WARN",
        "RED",
        "SKIP",
        "STATUSES",
        # the report and the row it is made of
        "run_checks",
        "Check",
        # what an area's own `doctor.py` speaks: its `register()` returns a `Contribution`, whose
        # checks take the `Context` and answer a `Row`, and whose `Claims` say what the area put
        # into settings files
        "Row",
        "Context",
        "Claims",
        "Contribution",
    }
    assert required == set(doctor.__all__)
