"""What this area publishes. The three checks every surface is held to are
`tests/test_surfaces.py`'s; this list is the one thing that is this area's own."""

from __future__ import annotations

import stayfixed.docs.api as docs


def test_the_surface_carries_what_every_consumer_reaches_for() -> None:
    # An equality and not a subset, for the reason tests/guards/test_surface.py gives: a subset
    # lets an export arrive unnoticed. No mutation entry: the mutation is adding an export,
    # which is two lines in `api.py` (the import and the `__all__` entry) and not one
    # substituted line. Measured by hand instead — re-exporting `trail.TRAIL_FILE` reddens this
    # test and this test alone.
    #
    # Outside this area, `project` imports `trail_target`, and `stayfixed.assess.gates` imports
    # the three gate functions and what the docs and trail gates read by path; the other names
    # below have no importer and stay on the argument written beside them in `api.py`.
    required = {
        # three checks this area is, one call each
        "check_budgets",
        "check_links",
        "check_memory_graph",
        # the install path: `project` ships `trail.toml`
        # beside the roadmap and must put it where `docs trail` reads it, a location only
        "trail_target",
        # the three gates stayfixed.assess.gates runs, each this area's own command's function
        "docs_gate",
        "plan_gate",
        "trail_gate",
        # `assess` and `adopt promote` ask git whether each file the docs and trail gates read
        # by path is tracked, the link targets among them, as this area's link reader finds them
        "docs_reads",
        "trail_reads",
    }
    assert required == set(docs.__all__)
