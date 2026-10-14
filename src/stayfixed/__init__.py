"""stayfixed: a methodology harness for coding agents."""

__version__ = "0.2.0"

# The public repository, spelled once — the install hint, the workflow pin and the
# `ci-ref` row all derive from it. `scripts/release.py check` reads `__version__` through a regex
# anchored on that name alone, and does not see these two lines.
REPOSITORY_SLUG = "stayfixed/stayfixed"
REPOSITORY_URL = f"https://github.com/{REPOSITORY_SLUG}"
