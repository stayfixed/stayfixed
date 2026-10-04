"""Which overlay root the machine file records: one key of a file the core owns.

The overlay itself is the private layer's, and this module reads nothing of it: only
`[overlay] root`, the machine file's record of where it is, which the note store, `attach`,
`doctor` and `init --questions` all ask for. Beside `config.loader` rather than in
`config.machine`, because the loader imports `config.machine` at module level and this reader
raises the loader's `MachineConfigError`.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

from stayfixed.config.loader import (
    NOT_UTF8,
    UNPARSEABLE,
    UNREADABLE,
    MachineConfigError,
    toml_position,
)
from stayfixed.config.machine import machine_config_path


def overlay_root(machine: Path | None) -> Path | None:
    """The overlay root this machine records, or `None` when it records none.

    `None` means **not recorded**, and nothing else. It used to mean six things — an absent
    file, an `OSError`, a TOML syntax error, a missing `[overlay]`, a non-dict `[overlay]` and
    a bad `root` — all collapsed into the one message the note store prints for it: "no overlay
    root is recorded in the machine configuration; run `stayfixed setup`". Three of those six
    are a broken file, and for a broken file that message is wrong advice.

    So a file that cannot be read or parsed raises the loader's `MachineConfigError`, in the
    loader's words for the same file, and the three shapes that genuinely record no overlay keep
    answering `None`: an absent file (the ordinary state before `setup` has run), no `[overlay]`
    table, and a table with no usable `root`.

    With no file named, the file is the one no variable can move (`interactive=False`): the
    root anchors where the note store may resolve, and a committed `.claude/settings.json` can
    set a variable in a session no person is watching.
    """
    path = machine_config_path(interactive=False) if machine is None else machine
    if not path.is_file():
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raise MachineConfigError(NOT_UTF8.format(path=path)) from None
    except OSError as exc:
        raise MachineConfigError(UNREADABLE.format(path=path, error=type(exc).__name__)) from None
    try:
        raw = tomllib.loads(text)
    except UNPARSEABLE as exc:
        raise MachineConfigError(f"{path} is not valid TOML {toml_position(exc)}") from None
    section = raw.get("overlay")
    if not isinstance(section, dict):
        return None
    value = section.get("root")
    return Path(str(value)).expanduser() if isinstance(value, str) and value else None
