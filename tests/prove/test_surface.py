"""What `stayfixed.prove.api` publishes, and for whom."""

from __future__ import annotations

from stayfixed.prove import api


def test_the_surface_is_what_consumers_reach_for() -> None:
    # The three checks every surface is held to are `tests/test_surfaces.py`'s; this is the list,
    # with the argument for each. No entry in `mutations/`: the mutation is adding an export,
    # two lines in `api.py`, as `tests/guards/test_surface.py` says of its own list.
    required = {
        # a command that runs a test command and judges it as `stayfixed prove` does
        "prove",
        "Receipt",
        "Verdict",
        # what a receipt counts
        "Counts",
    }
    assert required == set(api.__all__)
