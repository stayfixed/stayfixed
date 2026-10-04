"""The tags one stayfixed release is published under.

`pins` asks the public repository which commit the workflow's tag names, and the repository's
own release check (`scripts/release.py`) holds a tag to the version the tree carries: both spell
the tag through `tag_for`, so the two can never disagree about what a release is called.
"""

from __future__ import annotations

PACKAGE = "stayfixed"


def tag_for(version: str) -> tuple[str, str]:
    """The two tags one release carries: the workflow's `vX.Y.Z` and the platform's own."""
    return f"v{version}", f"{PACKAGE}--v{version}"
