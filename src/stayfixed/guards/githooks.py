"""The chained `prepare-commit-msg` hook and its per-repository installer.

Installed into `git rev-parse --git-path hooks`, never through `core.hooksPath`: a global
setting is overridden by any repository that sets its own and silently competes with husky
elsewhere on the machine, while `--git-path` honours a `core.hooksPath` the repository already
has — computing `<common-dir>/hooks` by hand would install into a directory git never reads
when one is set. Hooks resolve from the common directory, so one installation covers the main
checkout and every worktree.

A foreign hook of the same name is kept as `<name>.local` and the shipped hook `exec`s it
last, so nothing that was already running stops running. `uninstall` puts it back.

This is the one place this area writes outside a project root on purpose: the hooks directory is
git's, and in a worktree it is not under the checkout at all. The writes are
`fsops.write_atomically` on the hook path and a rename of the foreign hook beside it, and both paths
are named in `docs/cli.md`'s **Writes** paragraph for `stayfixed setup --git-hooks`, as the
enumerated-writes rule (CONTRIBUTING.md#enumerated-writes) asks of every path a command writes.
"""

from __future__ import annotations

import os
from enum import Enum
from pathlib import Path
from typing import NamedTuple

from stayfixed import fsops
from stayfixed.errors import Refusal
from stayfixed.gitenv import NO_ANSWER, git_run

HOOK_NAME = "prepare-commit-msg"
HOOK_MARKER = "# stayfixed:prepare-commit-msg"
LOCAL_SUFFIX = ".local"
# The mode the hook is given. Not a config key and not a bound on anything: git runs a hook
# only if it is executable, so any other value is a hook that silently never runs. Owner and
# group write are off for the same reason `fsops` picks conservative modes.
_EXECUTABLE = 0o755

_CHAIN_LINE = '    exec "$previous" "$@"'
# Every line of the hook stays under ruff's line length: the formatter never reflows a string
# literal, and a lint-suppression comment inside one would ship as hook text, so the long
# messages are shell variables. `{}` are absent from the shell on purpose; the only braces are
# the f-string's, which is why the command is chosen into a plain variable rather than into a
# shell function.
HOOK_TEXT = f"""#!/usr/bin/env bash
{HOOK_MARKER}
# Strip AI/tool attribution trailers before the commit message is presented.
#
# prepare-commit-msg rather than commit-msg on purpose: `git commit --no-verify` bypasses
# pre-commit and commit-msg, but not this hook. It is still only the local convenience layer;
# the authoritative gate is `stayfixed commit check` in CI, which sees commits this machine
# never produced. Written by `stayfixed setup --git-hooks`, and removed again, with the hook it
# chains to put back, by `stayfixed setup --git-hooks --uninstall`.
#
# Chains to whatever hook was here before, kept beside this one as `<hook>.local`, so
# installing this never silently disables husky, pre-commit, or what the repository had.
set -euo pipefail

msg_file="$1"
gate="CI's commit check is the gate"
failed="stayfixed: commit strip failed; $gate"
absent="stayfixed: not installed for this shell; trailers are not stripped locally; $gate"
quiet='^nothing to strip'

# Expanded unquoted where it is used, so the two-word form splits into words. It is only ever
# one of the two literals assigned just below, and never anything a repository chose.
runner=""
if command -v stayfixed >/dev/null 2>&1; then
    runner="stayfixed"
elif python3 -c 'import stayfixed' >/dev/null 2>&1; then
    runner="python3 -m stayfixed"
fi

# `commit strip` prints one line on stdout: "stripped N ..." or "nothing to strip". Only a
# rewrite is worth a line on the terminal, so the quiet one is filtered out and everything
# else is said. The branch is on the command's own status and never on `grep`'s: `grep -v`
# exits 1 when it selects no lines, which is exactly the quiet case, so a `||` hung off the
# pipe announces a failure on every clean commit. No outcome here may fail the commit.
if [ -z "$runner" ]; then
    printf '%s\\n' "$absent" >&2
elif out=$($runner commit strip "$msg_file"); then
    printf '%s\\n' "$out" | grep -v "$quiet" >&2 || true
else
    printf '%s\\n' "$failed" >&2
fi

previous="$0.local"
if [ -x "$previous" ]; then
{_CHAIN_LINE}
fi
"""


class Installed(NamedTuple):
    path: Path
    preserved: Path | None
    replaced: bool


class Found(Enum):
    """What `uninstall` found at the hook path. One value, so no answer can say that it both removed
    stayfixed's hook and left a foreign one; a report built from `restored` alone said "removed" of
    all three. A hook that cannot be read is none of them: `uninstall` refuses it."""

    REMOVED = "removed"  # stayfixed's hook, which is gone
    ABSENT = "absent"  # no hook at all
    FOREIGN = "foreign"  # a hook stayfixed did not write, left as it was


class Removed(NamedTuple):
    """What `uninstall` found at the hook path, and the hook it put back there, if any."""

    path: Path
    restored: Path | None
    found: Found


def git_path(root: Path, name: str, what: str) -> Path:
    """Where git keeps `name` for `root`, as `git rev-parse --git-path` names it.

    The one resolver for a file inside git's own directory: `hooks` for `setup --git-hooks`,
    `attach` and `doctor`, and `info/exclude` for `attach` and `detach`. `--git-path` is what
    maps a name to the common directory every worktree shares, and honours a `core.hooksPath`
    for `hooks`, which a path computed by hand gets wrong either way. `name` is always one of
    the callers' constants, so nothing here is a value to close off; `what` is the caller's
    word for it in a refusal. No `--` after `name`: measured, git prints a literal `--` as a
    second line there.
    """
    code, out = git_run(root, "rev-parse", "--git-path", name)
    # Neither refusal carries a byte this module did not compute, for the reason
    # `commit.commits_in` states beside its own: `rev-parse`'s stderr is repository-authored — it
    # quotes the offending CONFIG VALUE, `core.hooksPath` included — and is never read. `root` is
    # the caller's own path and is the actionable part; it is all that is printed.
    if code == -1:
        raise Refusal(f"git could not name the {what} of {root} ({NO_ANSWER})")
    answer = out.removesuffix("\n")
    if code != 0 or not answer:
        raise Refusal(f"git could not name the {what} of {root}; run it yourself to see why")
    path = Path(answer)
    return path if path.is_absolute() else root / path


def hooks_dir(root: Path) -> Path:
    """The directory git runs `root`'s hooks from, as git names it: `core.hooksPath` when set.

    Through `git_path`, so a `core.hooksPath` in any bytes is the directory git names, and
    `setup --git-hooks`, `attach` and `doctor` each read it as that directory.
    """
    return git_path(root, "hooks", "hooks directory")


# What `install` and `uninstall` say of a hook they cannot read. `{path}` is git's own hooks
# directory, which the reports name absolutely, as every other line of this module does.
UNREADABLE = "{path} could not be read ({reason}); {outcome}"


def _ours(path: Path, outcome: str) -> bool:
    """Whether the hook at `path` is stayfixed's, by its marker; bytes that are not UTF-8 are not.

    Read as a regular file only, to the read cap (`fsops.read_regular_bytes`): a FIFO there is
    never waited on, as `read_text` waited on it. A hook that cannot be read is neither ours nor
    foreign, and is refused, ending in `outcome`, what the caller did not do: read as foreign, it
    was "not stayfixed's" to `uninstall` and renamed and chained by `install` when it was
    stayfixed's own at mode 000. A regular file past the cap is the exception, and is foreign:
    stayfixed's own hook is a couple of kilobytes, so one that long is certainly not it.
    """
    try:
        content = fsops.read_regular_bytes(path)
    except fsops.TooLarge:
        return False
    except OSError as exc:
        raise Refusal(
            UNREADABLE.format(path=path, reason=fsops.said(exc), outcome=outcome)
        ) from exc
    try:
        return HOOK_MARKER in content.decode("utf-8")
    except UnicodeDecodeError:
        return False


def install(root: Path) -> Installed:
    directory = hooks_dir(root)
    target = directory / HOOK_NAME
    local = directory / (HOOK_NAME + LOCAL_SUFFIX)
    if target.is_symlink():
        raise Refusal(f"{target} is a symlink; refusing to write through it")
    if target.is_dir():
        raise Refusal(f"{target} is a directory; refusing to install a hook over it")
    replaced = target.exists() and _ours(target, "nothing was installed")
    # A `.local` found where our hook is *not* installed was put there by somebody else, and
    # the shipped hook `exec`s whatever sits at that name, so installing over it would run a
    # stranger's file under stayfixed's name. Note the bound, which is the whole of the
    # contract: this fires only while our hook is absent. Once ours is installed, the `.local`
    # beside it is presumed to be the one we preserved, and a file that appears there
    # afterwards is vouched for by nothing here — see `uninstall`.
    if local.exists() and not replaced:
        raise Refusal(f"{local} already exists and was not preserved by stayfixed; move it aside")
    preserved: Path | None = None
    if target.exists() and not replaced:
        target.rename(local)  # beside the hook, in git's own directory, as `docs/cli.md` says
        # Its mode is kept as found: `chmod -x` is how a developer switches a hook off, and
        # the chain tests `-x` for exactly that reason.
        preserved = local
    fsops.write_atomically(target, HOOK_TEXT)
    os.chmod(target, _EXECUTABLE)  # a git hook must be executable to run at all
    return Installed(target, preserved, replaced)


def uninstall(root: Path) -> Removed:
    directory = hooks_dir(root)
    target = directory / HOOK_NAME
    local = directory / (HOOK_NAME + LOCAL_SUFFIX)
    if not os.path.lexists(target):
        return Removed(target, None, Found.ABSENT)
    if target.is_symlink() or not _ours(target, "nothing was removed"):
        return Removed(target, None, Found.FOREIGN)
    target.unlink()
    # Whatever sits at `.local` is restored, and this does *not* check that install put it
    # there. It cannot: `install` refuses a stray `.local` only while our hook is absent, so a
    # file dropped beside an installed hook is unexamined — and the installed hook has been
    # `exec`ing it on every commit since, which is the larger fact. Restoring it is therefore
    # the honest end of that state rather than a new exposure, and it is deliberate: the
    # `.local` name is the contract `setup` relies on, and a provenance marker or an
    # unconditional refusal here would be this module inventing a different one.
    if local.exists():
        local.rename(target)
        return Removed(target, target, Found.REMOVED)
    return Removed(target, None, Found.REMOVED)
