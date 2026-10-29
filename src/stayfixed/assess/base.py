"""The base a change is judged against, and where in it the base's `stayfixed.toml` is.

The base's configuration governs the run, and the change's own is judged against it
(`stayfixed.assess.rule`). Both halves of that depend on reading the right document, and each way
of reading the wrong one ends in the same place: a base with no `stayfixed.toml` at the project's
path is the bootstrap, where the change decides its own configuration. So nothing here reads "git
did not answer" as "no copy", and every name and path git would resolve on the caller's behalf is
pinned first.

**Which commit.** In CI it is a full commit id the workflow resolved once from the remote-tracking
ref of the base branch, whose name comes from the platform or from the caller workflow's literal
input, which code owners guard (`docs/cli.md#the-reusable-workflow` names the repository
settings). Locally it is `config.layout.local_base`, the remote-tracking ref of `[project]
base_branch`, and
advice only: a local run judges nothing anyone else relies on. Either way `--base` is a full
commit id or a full `refs/…` name, never a short one, because git resolves a short name through
the tags first and a tag of the same spelling would stand in for the branch.

**Where in it.** At the project root's path inside the repository, as git spells it. A root
reached through a symlink below the repository's top, or spelled otherwise than git spells it (a
case-folding disk), is refused rather than guessed at: the base's copy would be looked for at the
place the link or the spelling names, which a change can make empty. A link above the
repository is the machine's (`/tmp` on macOS, a symlinked home) and is admitted.
"""

from __future__ import annotations

import re
from pathlib import Path

from stayfixed.committed import (
    committed_document,
    repository_prefix,
)
from stayfixed.config.loader import CONFIG_FILE
from stayfixed.config.reading import NOT_UTF8
from stayfixed.errors import Failure, Refusal
from stayfixed.gitenv import git_run

# Formatted with `[project] base_branch`, which the loader holds to the branch grammar.
BASE_UNREADABLE = (
    "the base is not in this checkout, or git could not read its stayfixed.toml, so the "
    "configuration that governs this change cannot be read; check out with full history "
    "(fetch-depth: 0), or pass a --base that exists, such as refs/heads/{branch} in a clone "
    "with no origin"
)
BASE_SHAPE = (
    "--base takes a full 40-character commit id or a full ref name starting with refs/: a "
    "shorter name is resolved by git, and a tag of the same spelling wins"
)
# The loader's own sentence for a tree copy that is not UTF-8, so the base's copy is refused in
# the words the tree's is: git hands the blob over losslessly, with a surrogate escape for each
# byte that is not UTF-8, and `tomllib` would parse those.
BASE_NOT_UTF8 = NOT_UTF8.format(path=f"the base's {CONFIG_FILE}")
BASE_REF = re.compile(r"\A(?:[0-9a-f]{40}|refs/[A-Za-z0-9._/-]+)\Z")


def _unreadable(branch: str) -> Failure:
    """ "git did not answer" is never read as "no copy". The failure's remedy names `branch`, the
    configured base branch."""
    return Failure(BASE_UNREADABLE.format(branch=branch))


def _read(root: Path, *args: str, branch: str) -> str:
    """git's answer, or the run fails as `_unreadable` says."""
    code, out = git_run(root, *args)
    if code != 0:
        raise _unreadable(branch)
    return out


def read_base(root: Path, base: str, *, branch: str, prefix: str | None = None) -> str | None:
    """The base's `stayfixed.toml` at the project's own path, or `None` when git listed nothing
    there: the bootstrap, and the only answer that means it. Any other git failure fails the run,
    and so does a copy that is not UTF-8 text, which is never parsed. `branch` is `[project]
    base_branch`, which a base the checkout lacks names as the local remedy. `prefix` is
    `repository_prefix(root)`, asked here unless the caller already has it.
    """
    if not BASE_REF.match(base):
        raise Refusal(BASE_SHAPE)
    if prefix is None:
        prefix = repository_prefix(root)
    if base.startswith("refs/"):
        # Exactly this ref: when it is missing, git would take `refs/tags/<base>` instead.
        _read(root, "show-ref", "--verify", "--quiet", "--end-of-options", base, branch=branch)
    commit = _read(
        root,
        "rev-parse",
        "--verify",
        "--quiet",
        "--end-of-options",
        f"{base}^{{commit}}",
        branch=branch,
    ).strip()
    raw = committed_document(
        root, commit, CONFIG_FILE, prefix=prefix, failed=lambda _code: _unreadable(branch)
    )
    if raw is None:
        return None
    # Read as UTF-8 the way the loader reads the tree's copy.
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        raise Failure(BASE_NOT_UTF8) from None
