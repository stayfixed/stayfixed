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

**The platform's values.** The reusable workflow hands `stayfixed gate` what the platform and the
caller file said, raw: the pull request's base, the caller's `base:` and `path:`, and the
repository's default branch. `platform_base` turns the first three into the commit, and
`platform_root` the last into the project root, each checking what the workflow's shell step
used to check, in its order.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from stayfixed.committed import (
    committed_document,
    repository_prefix,
)
from stayfixed.config.loader import CONFIG_FILE
from stayfixed.config.reading import NOT_UTF8
from stayfixed.errors import Failure, Refusal
from stayfixed.gitenv import git_run
from stayfixed.printed import quoted

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
# Formatted with the pull request's base through `printed.quoted`; never with `base:`'s value.
BASE_DISAGREES = (
    "base: names another branch, but this pull request's base is {pr_base}; the gates' "
    "configuration is read from the base the platform reports"
)
NO_BASE = "no base ref: pass 'base:'"
BASE_NOT_A_BRANCH = (
    "the base is not a valid branch name (git check-ref-format --branch refuses it), so no "
    "remote-tracking ref can be read for it"
)
PLATFORM_BASE_MISSING = (
    "the base branch is not in this checkout as refs/remotes/origin/<base>; check out with "
    "fetch-depth: 0, or name a base that exists"
)
PATH_LEAVES = "path: must not leave the checkout"


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


@dataclass(frozen=True)
class PlatformBase:
    """The base as the platform and the caller file name it, raw, and the checkout git resolves
    it in: `stayfixed gate`'s `--pr-base`, `--base-input` and `--default-branch`, and its
    `--root`."""

    checkout: Path
    pr_base: str
    base_input: str
    default_branch: str


def platform_base(root: Path, *, pr_base: str, base_input: str, default_branch: str) -> str:
    """The base commit's full id, read from the platform's values in `root`'s repository.

    `pr_base` is the pull request's base as the platform reports it (`github.base_ref`, empty on
    any other event), `base_input` the caller file's `base:`, and `default_branch` the
    repository's. The branch is the first of `base_input`, `pr_base` and `default_branch` that
    is not empty, and its commit is the remote-tracking ref of that name.
    """
    # The adversary is a pull request whose caller file names another `base:`: on a
    # `pull_request` the platform runs the caller from the merge commit, the author's copy, so a
    # `base:` naming a branch the author pushed would choose the configuration the change is
    # judged against. The anchor is `github.base_ref`, the platform's report of the pull
    # request's base, which the pull request cannot write. So where both are given and differ
    # this refuses, naming the platform's value and never the author's, which nothing has
    # checked yet. Agreeing costs a caller nothing: on a pull request `base:` decides nothing.
    if pr_base and base_input and base_input != pr_base:
        raise Refusal(BASE_DISAGREES.format(pr_base=quoted(pr_base)))
    # The three, in the order the workflow read them, and none of them is the tree under
    # review: the caller's `base:`, which decides on every event that reports no base, the pull
    # request's base, and the repository's default branch. With none of them this refuses
    # rather than guess a branch.
    branch = base_input or pr_base or default_branch
    if not branch:
        raise Refusal(NO_BASE)
    # A plain call, refusing nothing a legitimate branch is named: the qualified ref below already
    # decides which commit is read. Never echoed, since `base:` may be what it refuses.
    if git_run(root, "check-ref-format", "--branch", branch)[0] != 0:
        raise Refusal(BASE_NOT_A_BRANCH)
    # The adversary is a tag called `origin/<base>`: git resolves a short `origin/<base>`
    # through `refs/tags/` before `refs/remotes/`, and `fetch-depth: 0` fetches every tag, so
    # whoever may push a tag of that name would choose the commit every pull request is judged
    # against. The anchor is `refs/remotes/origin/<base>`, which `actions/checkout` writes from
    # the remote's branches. `fetch-depth: 0` has already fetched every branch, and
    # `persist-credentials: false` leaves no token for a second fetch, so a missing ref fails
    # naming the remedy and is never a default.
    code, out = git_run(
        root,
        "rev-parse",
        "--verify",
        "--quiet",
        "--end-of-options",
        f"refs/remotes/origin/{branch}^{{commit}}",
    )
    if code != 0:
        raise Failure(PLATFORM_BASE_MISSING)
    return out.strip()


def platform_root(checkout: Path, path: str) -> Path:
    """The project root the caller file's `path:` names inside `checkout`, with one leading `./`
    dropped: `""`, `.` and `./` are the checkout itself. No character is refused, and every
    message that names the root prints it through `printed.quoted`. A `..` component is
    `committed.repository_prefix`'s refusal, and a symlink on the way `stayfixed gate`'s.
    """
    value = path.removeprefix("./")
    # The adversary is a caller file whose `path:` points the gates at another checkout's
    # configuration; an absolute one leaves the checkout without a `..`. Never echoed.
    if value.startswith("/"):
        raise Refusal(PATH_LEAVES)
    return checkout / value
