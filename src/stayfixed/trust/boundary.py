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
one inside the project; `setup` always writes the home's, and the variable's as well only where
that directory exists outside the project.

**A write the sandbox refuses** (`sandbox_refused`): with Claude Code's sandbox on, an agent's shell
writes only the working directory and the temporary directory, so stayfixed's own writes to the
machine directory -- the trust record, the machine file -- and to the user settings fail there with
a permission error, whether or not the deny rule is in place. macOS's sandbox answers `EPERM`
(measured with `sandbox-exec` on macOS 27 on 2026-10-16: an open and a `mkdir` in a denied directory
each raised `PermissionError` `EPERM`); a read-only mount answers `EROFS`, which Linux's sandbox was
not measured to give. So `EPERM` and `EROFS` are read as that refusal, and each writer says so in
its own words, naming a person outside the agent's sandbox as the one to run it. A directory whose
mode refuses the user answers `EACCES`, which is not the sandbox, and keeps each writer's sentence
naming the directory.
"""

from __future__ import annotations

import errno
import os
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from stayfixed import fsops
from stayfixed.config.machine import passwd_home
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


def in_project(directory: Path, root: Path) -> bool:
    """Whether `directory` is the project `root` or lies inside it, spelled as given (made absolute
    against the working directory, as Claude Code would read a relative one) or where its links
    lead; a directory whose links cannot be followed is taken to be inside, since what the
    repository commits there is the repository's to choose."""
    try:
        spellings = {os.path.abspath(directory), str(fsops.resolved(directory))}
    except OSError:
        return True
    roots = {str(root), str(fsops.resolved(root))}
    return any(
        place == held or place.startswith(held + "/") for place in spellings for held in roots
    )


# The errors a sandboxed write fails with (the module docstring says which were measured).
SANDBOX_ERRNOS = frozenset({errno.EPERM, errno.EROFS})


def sandbox_refused(exc: OSError) -> bool:
    """Whether `exc` is the refusal an agent's sandbox gives a write outside the working directory
    (the module docstring says which errors those are)."""
    return exc.errno in SANDBOX_ERRNOS


def managed_settings(platform: str | None = None) -> Path | None:
    """This platform's managed-settings file, or `None` where none was measured."""
    return MANAGED_SETTINGS.get(sys.platform if platform is None else platform)
