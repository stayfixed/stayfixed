"""Where the machine-level configuration lives; the file is optional.

**Both variables that can name this file are gated, and for one reason.** A committed
`.claude/settings.json` may carry an `env` block, which applies without a trust prompt in a
non-interactive session and can set `STAYFIXED_CONFIG`; Claude Code ignores `XDG_CONFIG_HOME`
there (below), but direnv, mise or a devcontainer can set it from a file the repository commits.
So a repository able to redirect this path would declare its own overlay root and its own
pre-recorded trust hash — the two anchors that locating the note store and trusting in-repo
notes by hash rest on.

`STAYFIXED_CONFIG` was gated and `XDG_CONFIG_HOME` was not, which left the gate worth nothing:
the two variables reach the same file, and the second one costs a repository exactly one extra
path segment (`<dir>/stayfixed/config.toml` rather than the file itself). Gating one of a pair
of equivalent inputs is not a partial defence, it is a redirect with a longer name, so the
rule is now the variable-independent one: **in a non-interactive session this file is
`~/.config/stayfixed/config.toml` and nothing else.**

That is the XDG specification's own answer for an unset `XDG_CONFIG_HOME`, so a machine owner
who sets one really does lose it on the hook path rather than getting a wrong answer quietly —
`stayfixed doctor` is where that belongs once it exists. The cost is bounded and the exposure it
replaces was not: `permitted_roots`, `trust.json` and the overlay anchor were all selectable by
a file the clone ships.

A caller that knows it is a hook, the MCP server or a `stayfixed gate` run says
`interactive=False` rather than relying on the terminal check — `config.loader.load` takes the
same keyword for exactly that reason.

**`HOME` is a third such variable, and it is gated the same way.** Claude Code never applies
`HOME`, or any `XDG_*` variable, from a project's `env` block (its settings reference, "Variables
Claude Code ignores in `env`"; measured on 2.1.293), but a direnv, mise or devcontainer environment
can set it for a checkout, and `run-hook.sh` enters the project root before Python starts, so
`HOME=fakehome` names a directory inside the clone: a `trust.json` committed there approved the
clone's own notes with no word from the owner. So off a terminal the home directory is the password
database's entry for this process's user (`owner_home`), which no variable moves, and every reader
and writer of this file asks with `interactive=False` — `setup` and `memory trust` included, so the
file a person writes is the file a hook reads. A container or home-manager setup whose `HOME`
differs from that entry therefore keeps this file and `trust.json` under the entry's directory, and
`stayfixed doctor`'s `ignored-env` row says so. A user the database does not list has no home off a
terminal at all: no machine file is read, rather than one `HOME` chose.
"""

from __future__ import annotations

import os
import pwd
import sys
from collections.abc import Mapping
from pathlib import Path

DEFAULT_CONFIG_DIR = Path(".config")


def override_is_honoured(interactive: bool | None = None) -> bool:
    if interactive is not None:
        return interactive
    try:
        return sys.stdin.isatty()
    except (AttributeError, ValueError, OSError):
        return False


def passwd_home() -> Path | None:
    """This process's user's home directory as the password database records it.

    `None` for a user the database does not list — a container run under a bare uid — and for an
    entry whose directory is not an absolute path, which would otherwise be read against
    whatever directory the process happens to be in.
    """
    try:
        recorded = pwd.getpwuid(os.getuid()).pw_dir
    except KeyError:
        return None
    return Path(recorded) if os.path.isabs(recorded) else None


def owner_home(interactive: bool | None = None) -> Path | None:
    """The machine owner's home directory: `HOME` from a terminal, the database's everywhere else.

    The gate `override_is_honoured` keeps for the two variables that name the machine file, and
    for the same reason (the module docstring). `None` for a user `passwd_home` finds no directory
    for, off a terminal, and at one where `HOME` is unset too, where `Path.home` raises.
    """
    if override_is_honoured(interactive):
        try:
            return Path.home()
        except RuntimeError:
            return None
    return passwd_home()


def anchor_home(interactive: bool | None = None) -> Path | None:
    """`owner_home`, as a root a containment walk opens: the database's answer resolved once.

    `fsops.open_within` opens its root with `O_NOFOLLOW`, so an entry whose directory is itself
    a symlink (`/Users/me` linking to a volume) is refused there, while the release before read
    `HOME`, often the real directory, and made the link. The entry is the anchor this module
    trusts and its symlinks are the machine's, so resolving them changes nothing about whom the
    root belongs to. `HOME` from a terminal is used as typed, as it always was.
    """
    home = owner_home(interactive)
    if home is None or override_is_honoured(interactive):
        return home
    return home.resolve()


def homes_agree(env: Mapping[str, str] | None = None) -> bool:
    """Whether `HOME` names the home the password database records, or is not set at all.

    Where they agree, the home stayfixed trusts off a terminal is also the one every other program
    finds through `HOME` — the harness locating its memory directory among them. An unset `HOME`
    agrees, because a program with no `HOME` asks the database too; a user the database lists
    no home for never agrees, since there is nothing to agree with.
    """
    env = os.environ if env is None else env
    recorded = passwd_home()
    if recorded is None:
        return False
    chosen = env.get("HOME")
    return not chosen or Path(chosen).resolve() == recorded.resolve()


def in_owner_home(value: str) -> Path | None:
    """`value` with a leading `~` read as the machine owner's home directory, never as `HOME`.

    For a path the machine file records, which is read with `interactive=False` by every command:
    `~` there means the home that file lives under. `None` when `value` begins with `~` and there
    is no such home, rather than a `~` left to be read as a directory name. `~user` is the
    database's entry for that user already, which is what `expanduser` asks for it.
    """
    if value == "~" or value.startswith("~/"):
        home = passwd_home()
        return None if home is None else home / value[2:]
    return Path(value).expanduser()


def machine_config_path(
    env: Mapping[str, str] | None = None, *, interactive: bool | None = None
) -> Path | None:
    """The machine configuration file, or `None` off a terminal when `owner_home` has no answer."""
    env = os.environ if env is None else env
    honoured = override_is_honoured(interactive)
    explicit = env.get("STAYFIXED_CONFIG") if honoured else None
    if explicit:
        return Path(explicit)
    chosen = env.get("XDG_CONFIG_HOME") if honoured else None
    if chosen:
        return Path(chosen) / "stayfixed" / "config.toml"
    home = owner_home(honoured)
    if home is None:
        return None
    return home / DEFAULT_CONFIG_DIR / "stayfixed" / "config.toml"
