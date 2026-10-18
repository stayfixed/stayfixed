"""What an env file is: the one answer the inventory's `tracked-env` probe and the `env-reads`
session guard both read, so a file the probe reports as committed credentials is the file the guard
keeps an agent from reading, and a template one passes the other passes too.

A leaf that imports nothing from the package. `assess` publishes no `api.py`, so the guard could
not read the probe's tuple where it used to live, and two copies of it would drift.
"""

from __future__ import annotations

# The suffixes a project gives the file it commits as a template for its env files: no value in
# it is a credential, and an agent is meant to read it and keep it in step with the code.
TEMPLATE_SUFFIXES = (".example", ".sample", ".template")


def is_env_file(name: str) -> bool:
    """Whether a file named `name` (one path component) is an env file that may hold credentials.

    `.env` itself, and `.env.<anything>` unless it ends in a template suffix. Compared case-folded:
    on a file system that ignores case, which is macOS's and Windows' default, `.ENV` opens the
    same file `.env` does, and a guard that compared exactly would let it through.
    """
    folded = name.casefold()
    return folded == ".env" or (
        folded.startswith(".env.") and not folded.endswith(TEMPLATE_SUFFIXES)
    )
