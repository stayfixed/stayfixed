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
"""

from __future__ import annotations

import sys
from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType

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


def managed_settings(platform: str | None = None) -> Path | None:
    """This platform's managed-settings file, or `None` where none was measured."""
    return MANAGED_SETTINGS.get(sys.platform if platform is None else platform)
