"""The release package's `api.py` is held to the same contract every area's is.

CONTRIBUTING states it once for all of them: "`api.py` is the area's import surface. Other
areas import from it and from nothing else, and its `__all__` must equal exactly what it
imports — a test parses the file and checks."
"""

from __future__ import annotations

import stayfixed.release.api as release


def test_the_surface_carries_what_every_consumer_reaches_for() -> None:
    # An equality and not a subset, for the reason tests/doctor/test_surface.py gives: a subset
    # lets an export arrive unnoticed. `doctor` reads the record's readers and the pins;
    # `scripts/check_artifacts.py` reads `HASHED_FILES` and `RECORD`; and `scripts/release.py`,
    # which writes the record and checks the version, reads `FORMAT`, `tag_for` and `PACKAGE`
    # besides. Writing the record is the script's and is not on the surface at all.
    required = {
        # what the record covers, and where it lives. This comment used to say `doctor` names
        # the file it compared; it does not, it says "beside `hooks/run-hook.sh`" in prose, so
        # the test was enforcing a dead export against a false premise until the artifact
        # checker stopped spelling all four paths by hand.
        "HASHED_FILES",
        "RECORD",
        # the number the record's writer stamps and its reader accepts
        "FORMAT",
        # the two answers about a record: what is there, and what was recorded
        "digests",
        "read_record",
        # "present and not a record" is a distinct answer from "absent" — absent skips in
        # `doctor` and unreadable must be red — so the consumer needs the class to branch on.
        "UnreadableRecord",
        # which commit a release is: `init` writes the pin, `doctor`'s `ci-ref` row
        # judges it
        "Pin",
        "Resolution",
        "released",
        "resolve_pin",
        "is_released",
        # what a release is tagged as, for the script's `check --tag`, and the package name the
        # platform's tag carries, which the script also looks the package up by in `uv.lock`
        "tag_for",
        "PACKAGE",
    }
    assert required == set(release.__all__)
