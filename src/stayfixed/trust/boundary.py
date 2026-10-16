"""What keeps an agent from writing the trust record itself: the harness's sandbox and a deny rule.

An approval holds against repository bytes and a `git pull`. Against an agent whose shell can write
`trust.json`, the terminal check `trust approve` makes and the `ask` rules `setup` writes are speed
bumps (`kinds`' docstring says why). What stops such an agent is Claude Code's own: its sandbox,
which confines what the shell tool writes, and a `permissions.deny` rule over the record's
directory, which the sandboxed shell and the file tools both honour. `setup --approval-boundary`
adds the rule and prints the sandbox settings for the person to set, and never sets them itself;
`doctor`'s `approval-boundary` row reads whether both are in force for a project. This module holds
the spellings both use, and nothing here writes a file.

Every literal below was measured on Claude Code 2.1.296 (macOS) on 2026-10-16; the record is the
findings at the end of the 2026-10-15 floor, layers and trust plan in `docs/plans/`.

- **The sandbox.** A project's `.claude/settings.json` or `.claude/settings.local.json` setting
  `sandbox.enabled = false` turns a user's `sandbox.enabled = true` off for that project, and a
  user's `sandbox.allowUnsandboxedCommands = false` does not stop it. Only managed settings (or
  `--settings` on the command line) make the sandbox admin-required, and then a repository's
  `false` is ignored. While `allowUnsandboxedCommands` is not false, an agent the sandbox blocks may
  retry the command with `dangerouslyDisableSandbox`, which runs it outside.
- **The rule.** `Edit(//<absolute path>/**)` stopped a sandboxed shell write and a file-tool write
  into that directory; one leading slash anchors the path at the working directory and stopped
  neither outside it, and a `Write(...)` rule stopped neither in any spelling.
- **Where an administrator's settings live:** `MANAGED_SETTINGS`, each with an optional directory
  of drop-in files beside it.

**Which user settings directory is Claude Code's** (`user_settings`): `.claude` under the home the
password database records, and the directory `CLAUDE_CONFIG_DIR` names where it is set and is not
spelled byte for byte as that one. Nothing tells whether a person chose the variable: a
repository's committed `env` block can set it for an agent's shell, and direnv or mise can set it
from a file the repository commits in a person's own terminal, so a terminal on standard input
proves nothing either. So the home's directory is always the primary subject, and the variable's
may only make an answer worse: `doctor` judges the home's and lets the variable's worsen it, judges
the variable's alone only where the home has none and then never above a warning, and never judges
one inside the project or another checkout of its repository; `setup` always writes the home's,
and the variable's as well only where that directory exists outside them. Neither asks the
filesystem about a variable's directory under neither a home nor the project (`placement`).

**A write the sandbox refuses** (`sandbox_refused`): with Claude Code's sandbox on, an agent's shell
writes only the working directory and the temporary directory, so stayfixed's own writes to the
machine directory -- the trust record, the machine file -- and to the user settings fail there with
a permission error, whether or not the deny rule is in place. Claude Code's sandboxing reference
gives the error for such a write: `Operation not permitted` (`EPERM`) on macOS, and `Read-only file
system` (`EROFS`) on Linux and WSL2. macOS's was also measured here (with `sandbox-exec` on macOS 27
on 2026-10-16: an open and a `mkdir` in a denied directory each raised `PermissionError` `EPERM`);
Linux's was not. So `EPERM` and `EROFS` are read as that refusal, and each writer says so in its own
words, naming a person outside the agent's sandbox as the one to run it. A read-only mount and an
immutable flag answer the same, so the sentences of the two commands a person runs, `setup` and
the trust record's writers, end with `OWN_TERMINAL_TOO`, lest a person already in their own terminal
be sent there again. A directory whose mode refuses the user answers `EACCES`, which is not the
sandbox, and keeps each writer's sentence naming the directory.

**Comparing two paths** (`folded`, `in_project`): the macOS default volume folds case, and hands
names back composed or decomposed, so there a spelling is compared in NFC, case-folded; elsewhere
as it is. `doctor` compares a settings entry with the record's directory this way, and
`in_project` compares a directory with the project root the same way, so a case variant of the
project's path is inside it.
"""

from __future__ import annotations

import errno
import os
import sys
import unicodedata
from collections.abc import Mapping, Sequence, Set
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType

from stayfixed import fsops
from stayfixed.config.machine import passwd_home
from stayfixed.gitenv import answer_lines, git_run, in_work_tree
from stayfixed.harnesses import CLAUDE_DIR

# Claude Code's managed settings, by `sys.platform`: the file only an administrator writes, whose
# `sandbox` keys a repository's settings cannot override. Measured on Claude Code 2.1.296 (the
# module docstring); Linux's is WSL's too.
MANAGED_SETTINGS: Mapping[str, Path] = MappingProxyType(
    {
        "darwin": Path("/Library/Application Support/ClaudeCode/managed-settings.json"),
        "linux": Path("/etc/claude-code/managed-settings.json"),
    }
)
# The directory beside the managed file whose `*.json` files are merged over it, in name order.
MANAGED_DROP_INS = "managed-settings.d"
# The variable Claude Code finds the user's settings directory by, in place of `~/.claude`.
CONFIG_DIR_VARIABLE = "CLAUDE_CONFIG_DIR"
# The sandbox's keys, under the settings document's `sandbox` object.
SANDBOX = "sandbox"
ENABLED = "enabled"
UNSANDBOXED_ALLOWED = "allowUnsandboxedCommands"
# The key that makes Claude Code refuse to start where the sandbox cannot, instead of running
# commands outside it: named by Claude Code's sandboxing reference, whose recipe for enforcing the
# sandbox sets it in managed settings beside `enabled` and `allowUnsandboxedCommands`; not measured
# here.
FAIL_IF_UNAVAILABLE = "failIfUnavailable"
# The managed keys of Claude Code's sandboxing reference's recipe for enforcing the sandbox, as a
# person sets them: `setup --approval-boundary` prints them, and `doctor`'s approval-boundary row
# asks for each before it is green and names them in its remedy. One spelling, from the key names
# above, so the advice and the row cannot drift apart.
ENFORCING_SETTINGS = (
    f"{SANDBOX}.{ENABLED} = true, {SANDBOX}.{FAIL_IF_UNAVAILABLE} = true and "
    f"{SANDBOX}.{UNSANDBOXED_ALLOWED} = false"
)
# What a sentence names in managed settings' place on a platform where none was measured.
NO_MANAGED_PATH = "the managed settings file"
# The deny rule over a directory, measured on Claude Code 2.1.296: `Edit(/` and the absolute path,
# whose own leading slash makes the two the measurement needs.
DENY_RULE = "Edit(/{directory}/**)"


def deny_rule(directory: Path) -> str:
    """The `permissions.deny` rule that keeps the sandboxed shell and the file tools out of
    `directory`, an absolute path."""
    return DENY_RULE.format(directory=directory.as_posix())


def deny_rules(named: Path, resolved: Path) -> tuple[str, ...]:
    """The deny rules `setup` writes over the trust record's directory, spelled `named` and, where
    a symbolic link makes it differ, `resolved`: the only spellings `doctor` counts, byte for byte.
    """
    return tuple(dict.fromkeys((deny_rule(named), deny_rule(resolved))))


def record_deny_rules(record: Path | None) -> tuple[str, ...]:
    """The deny rules over the directory the trust record at `record` is kept in (`deny_rules`):
    over it as named, and over where it leads, since the harness compares a write against the path
    it resolves. None for no record, a machine with no home to hold one. The one computation
    `setup --approval-boundary` writes and `doctor`'s approval-boundary row asks for."""
    if record is None:
        return ()
    return deny_rules(record.parent, fsops.resolved(record.parent))


@dataclass(frozen=True)
class UserSettings:
    """Claude Code's user settings directories as stayfixed reads them: `directory`, `.claude`
    under the home (`None` for no home), and `chosen`, the one `CLAUDE_CONFIG_DIR` names where it
    is set and is not `directory`."""

    directory: Path | None
    chosen: Path | None


def user_settings(env: Mapping[str, str], home: Path | None = None) -> UserSettings:
    """The user settings directories (the module docstring says which): `.claude` under `home`, a
    home the person named on the command line, or under the password database's home; and the
    directory `CLAUDE_CONFIG_DIR` names, where it is set and differs from that one."""
    base = home if home is not None else passwd_home()
    directory = None if base is None else base / CLAUDE_DIR
    named = env.get(CONFIG_DIR_VARIABLE)
    # One directory only when the two are spelled alike to the byte: a variable spelled any other
    # way is judged on its own, since no normalisation of a name someone else chose is this
    # module's to prove.
    same = directory is not None and named == str(directory)
    return UserSettings(directory, Path(named) if named and not same else None)


# The macOS default volume folds case, and its names may arrive composed or decomposed, so a
# spelling is compared there in NFC, case-folded (the module docstring).
CASE_FOLDS = sys.platform == "darwin"


def folded(text: str) -> str:
    """`text`, a path, as this module and `doctor` compare it: as it is, or in NFC and
    case-folded where names fold."""
    return unicodedata.normalize("NFC", text).casefold() if CASE_FOLDS else text


def in_project(directory: Path, root: Path, checkouts: Sequence[Path] = ()) -> bool:
    """Whether `directory` is the project `root`, one of the repository's other `checkouts`, or
    lies inside one, each compared `folded`: spelled as given (made absolute against the working
    directory, as Claude Code would read a relative one), and only where that spelling is not
    already inside, where its links lead. A directory whose links cannot be followed is taken to be
    inside, since what the repository commits there is the repository's to choose.

    A spelling inside is never followed: a link the repository commits there may lead under an
    automount root (`/net/<host>/...` on macOS), where one stat stalls until the network answers,
    and the answer is "inside" wherever it leads."""
    roots = {folded(str(place)) for place in (root, fsops.resolved(root), *checkouts)}
    if _inside(os.path.abspath(directory), roots):
        return True
    try:
        led = fsops.resolved(directory)
    except OSError:
        return True
    return _inside(str(led), roots)


def _inside(spelling: str, roots: Set[str]) -> bool:
    return any(_within(folded(spelling), held) for held in roots)


def _within(place: str, held: str) -> bool:
    return place == held or place.startswith(held.rstrip("/") + "/")


class Placement(StrEnum):
    """Where a directory an environment variable names lies, as `placement` answers."""

    # Outside the project and every checkout of its repository, under a home or the project
    # stayfixed may ask the filesystem about: judged, and written.
    OUTSIDE = "outside"
    # The project, a checkout of its repository, or inside one, or where links cannot be followed:
    # its contents are the repository's to choose, so it is named and never judged or written.
    INSIDE = "inside"
    # Under neither a home nor the project: never asked of the filesystem, since a path a committed
    # `env` block chose may lie under an automount root (`/net/<host>/...` on macOS), where one stat
    # stalls until the network answers; named, and never judged or written.
    UNJUDGED = "unjudged"


# How `git worktree list --porcelain` opens the line naming a checkout.
_WORKTREE = "worktree "


def checkouts(root: Path) -> tuple[Path, ...] | None:
    """Every checkout of the repository `root` lies in, as `git worktree list` names them; `()`
    with no `.git` at or above `root`, where there is no repository; `None` where there is one and
    git gives no answer, so which checkouts it has is not known."""
    code, out = git_run(root, "worktree", "list", "--porcelain")
    listed = tuple(
        Path(line[len(_WORKTREE) :]) for line in answer_lines(out) if line.startswith(_WORKTREE)
    )
    if code == 0 and listed:
        return listed
    return None if in_work_tree(root) else ()


def placement(directory: Path, root: Path, homes: Sequence[Path]) -> Placement:
    """Where `directory`, a directory `CLAUDE_CONFIG_DIR` names, lies against the project `root`.

    Read as text first, made absolute against the working directory and compared `folded`: only a
    directory under one of `homes` (the password database's home, and one the person typed), under
    the project or under one of its checkouts is asked of the filesystem at all; any other is
    `UNJUDGED`. Then `in_project`, against the project and every checkout `checkouts` names, since
    what a repository commits reaches each of its checkouts; a repository whose checkouts git
    cannot list is taken to hold this one, as a link that cannot be followed is."""
    known = checkouts(root)
    if known is None:
        return Placement.INSIDE
    text = folded(os.path.abspath(directory))
    bases = [folded(str(base)) for base in (*homes, root, *known)]
    if not any(_within(text, base) for base in bases):
        return Placement.UNJUDGED
    return Placement.INSIDE if in_project(directory, root, known) else Placement.OUTSIDE


# The errors a sandboxed write fails with (the module docstring cites where each is given).
SANDBOX_ERRNOS = frozenset({errno.EPERM, errno.EROFS})


# The end of the sentence `setup` and the trust record give a refused write (the module docstring).
OWN_TERMINAL_TOO = (
    "; met in a person's own terminal, it is the directory itself that refuses writes, as a "
    "read-only mount or an immutable flag does"
)


def sandbox_refused(exc: OSError) -> bool:
    """Whether `exc` is the refusal an agent's sandbox gives a write outside the working directory
    (the module docstring says which errors those are)."""
    return exc.errno in SANDBOX_ERRNOS


def managed_settings(platform: str | None = None) -> Path | None:
    """This platform's managed-settings file, or `None` where none was measured."""
    return MANAGED_SETTINGS.get(sys.platform if platform is None else platform)


def managed_named() -> str:
    """This platform's managed-settings file as a sentence names it: its path, or
    `NO_MANAGED_PATH` where none was measured."""
    managed = managed_settings()
    return NO_MANAGED_PATH if managed is None else str(managed)
