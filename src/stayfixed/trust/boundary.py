"""What keeps an agent from writing the trust record itself: the harness's sandbox and a deny rule.

An approval holds against repository bytes and a `git pull`. Against an agent whose shell can write
`trust.json`, the terminal check `trust approve` makes and the `ask` rules `setup` writes are speed
bumps (`kinds`' docstring says why). What stops such an agent is Claude Code's own: its sandbox,
which confines what the shell tool writes, and a `permissions.deny` rule over the record's
directory, which the sandboxed shell and the file tools both honour. `setup --approval-boundary`
adds the rule and prints the sandbox settings for the person to set, and never sets them itself;
`doctor`'s `approval-boundary` row reads whether both are in force for a project. This module holds
the spellings both use, and nothing here reads or writes a file.

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

**Which user settings directory is Claude Code's** (`user_settings`): `CLAUDE_CONFIG_DIR` when it is
set and standard input is a terminal, and `.claude` under the home the password database records
otherwise. A repository's committed `env` block can set `CLAUDE_CONFIG_DIR` for an agent's shell,
and a directory it chose would let `doctor` judge a decoy and `setup` write rules where no session
reads them; a person at a terminal set the one they have. The terminal check is `kinds.interactive`,
the seam `trust approve` asks.

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
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from stayfixed.config.machine import passwd_home
from stayfixed.harnesses import CLAUDE_DIR
from stayfixed.trust import kinds

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
    """Claude Code's user settings directory as stayfixed reads it: the directory (`None` for no
    home), whether `CLAUDE_CONFIG_DIR` named it, and whether one was set and passed over."""

    directory: Path | None
    from_variable: bool
    ignored: bool


def user_settings(env: Mapping[str, str], home: Path | None = None) -> UserSettings:
    """The user settings directory (the module docstring says which): `CLAUDE_CONFIG_DIR` only when
    standard input is a terminal, and otherwise `.claude` under `home`, a home the person named on
    the command line, or under the password database's home."""
    chosen = env.get(CONFIG_DIR_VARIABLE)
    # Through the module, so the one seam a test replaces is the one asked here.
    if chosen and kinds.interactive():
        return UserSettings(Path(chosen), from_variable=True, ignored=False)
    base = home if home is not None else passwd_home()
    return UserSettings(
        None if base is None else base / CLAUDE_DIR, from_variable=False, ignored=bool(chosen)
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
