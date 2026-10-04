"""The attach area's `api.py` is held to the same contract every other area's is.

CONTRIBUTING states it once for all of them: "`api.py` is the area's import surface. Other
areas import from it and from nothing else, and its `__all__` must equal exactly what it
imports — a test parses the file and checks."
"""

from __future__ import annotations

import stayfixed.attach.api as attach


def test_the_surface_carries_what_every_consumer_reaches_for() -> None:
    # An equality and not a subset, for the reason tests/guards/test_surface.py gives: a subset
    # lets an export arrive unnoticed. What each name is doing here is written beside it, so
    # this set states the policy `api.py`'s docstring states — a name is on the surface because
    # a consumer outside this area reaches for it, or because an exported name's signature or
    # vocabulary requires it — rather than freezing whatever the list happened to hold.
    #
    # `attach` and `detach` are not on it: `tests/test_install_path.py` drives them through the
    # argument parser and imports only `stayfixed.doctor.api` and `stayfixed.memory.api`.
    #
    # No mutation entry: the mutation is adding an export, which is two lines in `api.py` (the
    # import and the `__all__` entry) and not one substituted line. Measured by hand instead —
    # re-exporting `permissions.check` reddens this test and this test alone.
    required = {
        # the ledger, the binding and the overlay's granted entries, for doctor; the ledger's
        # path and the `.gitignore` block are `config.layout`'s, since the core names them too
        "ledger",
        "AttachLedger",  # what `ledger` returns; doctor cannot annotate it otherwise
        "read_binding",
        "Binding",
        "overlay_entries",
        "LOCAL_SETTINGS",  # the file those entries live in
    }
    assert required == set(attach.__all__)
