"""The overlay's executable parts, rendered into a local plugin named by the binding id.

**What runs is this directory, in place.** `claude plugin install --scope local` keeps a cache
copy, but a session runs the plugin from its marketplace's own directory, `<data>/delivery/<id>/`:
an edit there reaches the next session with no reinstall, and with the directory gone the plugin
does not load and nothing says so. So `attach` re-renders here on every run and installs only once,
and the directory is always derived from the id, never read from a record a checkout keeps.

**The names are the defence.** Claude Code records a local-scope marketplace machine-wide, and a
clone that commits an `enabledPlugins` entry naming a plugin this machine knows runs its hooks. So
the marketplace is `stayfixed-delivery-<id>` and the plugin `overlay-<id>`, each carrying the whole
binding id, which never leaves this machine (`stayfixed.binding`): a clone cannot name what it never
saw. No other name of a delivered part is predictable, and none of these is ever printed.

**What is rendered.** The union of `<overlay>/common/claude/hooks.json` and
`<overlay>/projects/<project>/claude/hooks.json`, each event's entry groups common first, as the
overlay wrote them; and `skills/` and `agents/` copied from the same two directories, this
project's copy of a file winning over the common one. `<project>` is the project this machine's
binding record names, which the caller passes. Every source is read before anything is written
(`read_parts`), so a file that cannot be read stops the run while the render is as it was.

**The overlay's path-scoped rules** (`attach.rules`) add one entry: on `PostToolUse`, matching
`Read|Edit|Write`, `hook PostToolUse` run through whatever launched the stayfixed that renders
(`scoped_command`), by absolute paths, since the render is no part of the core plugin and has no
`${CLAUDE_PLUGIN_ROOT}` naming it. Run from the core plugin, or a checkout of it, that is the
plugin's own hook wrapper, `hooks/run-hook.sh` beside the running module's `src/`, which runs the
interpreter with `-I` and answers any fault with exit 0, as for the core plugin's own entries; run
from an installed package, which has no plugin root, it is the running interpreter with
`-I -m stayfixed`. Only what the running process knows about itself is asked. The entry is rendered
only when the overlay holds a rule with `paths:`. No entry is added to the core plugin's
`hooks/hooks.json`.

**The digest is a convenience, not a gate.** It is sha256 over every rendered file's path relative
to the render directory and its bytes, which the ledger keeps beside those paths so a later run can
say what changed and take back what the overlay no longer holds. The overlay is the owner's, and
its hooks run scripts from the overlay checkout in place, so a digest of this text would not even
cover what runs.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple

import stayfixed
from stayfixed import fsops
from stayfixed.attach.permissions import HOOKS_FILE, PROJECT_CLAUDE, hook_groups
from stayfixed.attach.rules import scoped_exist
from stayfixed.config.paths import data_directory
from stayfixed.errors import Failure
from stayfixed.memory.api import PROJECTS
from stayfixed.overlay.api import COMMON_CLAUDE
from stayfixed.printed import quoted

# Under the machine's data directory: one render per binding id.
DELIVERY = "delivery"
MARKETPLACE_PREFIX = "stayfixed-delivery-"
PLUGIN_PREFIX = "overlay-"
# The plugin's directory inside the marketplace, as the marketplace's `source` names it.
PLUGIN_DIRECTORY = "plugin"
MARKETPLACE_FILE = ".claude-plugin/marketplace.json"
PLUGIN_FILE = f"{PLUGIN_DIRECTORY}/.claude-plugin/plugin.json"
# The plugin's hook file, by its path inside the plugin directory.
HOOK_FILE = "hooks/hooks.json"
# The two directories copied whole from each source, beside the hook file.
COPIED = ("skills", "agents")
# The entry that delivers path-scoped rules: the event, the tools whose input names a file, and the
# core plugin's hook wrapper, by its path in the plugin root, beside `src/`.
SCOPED_EVENT = "PostToolUse"
SCOPED_MATCHER = "Read|Edit|Write"
WRAPPER = "hooks/run-hook.sh"
# The core plugin's own hook timeout, in seconds (`hooks/hooks.json`).
SCOPED_TIMEOUT = 10
_DESCRIPTION = "The hooks, skills and agents of your stayfixed overlay, rendered for this checkout."

# The two `claude plugin` calls that make the render a plugin of this checkout, run from the main
# checkout, whose `settings.local.json` Claude Code reads from every worktree: `SLOT` is filled with
# the render directory and with `overlay-<id>@stayfixed-delivery-<id>`.
SLOT = "<slot>"
PLUGIN_MARKETPLACE_ADD_LOCAL = ("claude", "plugin", "marketplace", "add", SLOT, "--scope", "local")
PLUGIN_INSTALL_LOCAL = ("claude", "plugin", "install", SLOT, "--scope", "local")


class Part(NamedTuple):
    """One file the plugin carries: its text, and the permission bits it is written with, `None`
    for a file stayfixed generates, which keeps the mode it has or is made with the default."""

    text: str
    mode: int | None = None


@dataclass(frozen=True)
class Rendered:
    """What the attach ledger keeps of a render: its digest and its parts, never the id and never
    a path on this machine, since the directory is always `delivery_directory(id)`."""

    digest: str
    parts: tuple[str, ...]


@dataclass(frozen=True)
class RenderRecord:
    """One render: the id it is named by, the digest over its files, and those files' paths
    relative to the render directory, sorted."""

    id: str
    digest: str
    parts: tuple[str, ...]

    @property
    def rendered(self) -> Rendered:
        return Rendered(self.digest, self.parts)


def marketplace_name(id: str) -> str:
    return f"{MARKETPLACE_PREFIX}{id}"


def plugin_name(id: str) -> str:
    return f"{PLUGIN_PREFIX}{id}"


def delivery_directory(id: str) -> Path:
    """`<data>/delivery/<id>/`, derived from the id and nothing else."""
    return data_directory() / DELIVERY / id


def filled(table: tuple[str, ...], value: str) -> list[str]:
    """`table`'s argv with its `SLOT` replaced by `value`."""
    return [value if word == SLOT else word for word in table]


def _unreadable(sentence: str) -> Failure:
    return Failure(f"{sentence}, so nothing was written")


def _copied(source: Path) -> dict[str, Part]:
    """Every regular file under `source` by its path relative to it, its text with its own line
    endings and its permission bits, so a skill's script stays executable; dot-named files and
    directories are left out. The overlay is the owner's, so a path in it prints, through `quoted`
    since a project's directory carries `project.name`."""

    def refuse(error: OSError) -> None:
        raise error

    found: dict[str, Part] = {}
    with fsops.reading(quoted(str(source)), _unreadable):
        for directory, names, files in os.walk(source, onerror=refuse):
            # Pruned in place, which is how `os.walk` is told not to enter a directory.
            names[:] = sorted(name for name in names if not name.startswith("."))
            for name in sorted(files):
                path = Path(directory) / name
                if name.startswith(".") or not fsops.is_file(path):
                    continue
                with fsops.reading(quoted(str(path)), _unreadable):
                    text = fsops.read_regular_text(path, newline="")
                    # The permission bits alone: a set-id or sticky bit is not the overlay's to
                    # hand to a file under this machine's data directory.
                    mode = stat.S_IMODE(path.stat().st_mode) & 0o777
                found[path.relative_to(source).as_posix()] = Part(text, mode)
    return found


def _quoted(path: str) -> str:
    """`path` in double quotes, as the core plugin's entries quote theirs, with the four characters
    a shell still reads inside them escaped, so it arrives as one word, unexpanded."""
    for char in '\\"$`':
        path = path.replace(char, f"\\{char}")
    return f'"{path}"'


def scoped_command() -> str | None:
    """`hook PostToolUse` run through whatever launched this stayfixed: the plugin root's hook
    wrapper where the running module's `src/` has one beside it, as `scripts/stayfixed` puts that
    `src/` on `sys.path`; else the running interpreter, isolated; `None` where the process cannot
    name its interpreter."""
    wrapper = Path(stayfixed.__file__).resolve().parents[2] / WRAPPER
    if fsops.is_file(wrapper):
        return f"{_quoted(str(wrapper))} hook {SCOPED_EVENT}"
    if sys.executable:
        return f"{_quoted(sys.executable)} -I -m stayfixed hook {SCOPED_EVENT}"
    return None


def scoped_group(command: str) -> dict[str, object]:
    """The `PostToolUse` entry group that runs `command` on every file a session touches."""
    return {
        "matcher": SCOPED_MATCHER,
        "hooks": [{"type": "command", "timeout": SCOPED_TIMEOUT, "command": command}],
    }


def read_parts(overlay: Path, project: str) -> dict[str, Part]:
    """What the plugin carries, by path relative to the plugin directory, read and nothing
    written: the hook file's union, the path-scoped rules' entry where there is one, and the
    copied directories."""
    share = overlay / PROJECTS / project
    sources = ((overlay / COMMON_CLAUDE, None), (share / PROJECT_CLAUDE, share))
    hooks: dict[str, list[object]] = {}
    for source, owner in sources:
        for event, groups in hook_groups(source / HOOKS_FILE, share=owner).items():
            hooks.setdefault(event, []).extend(groups)
    # The rules are read whether or not there is a command, so a rule that cannot be read stops
    # every run alike.
    if scoped_exist(overlay, project) and (command := scoped_command()) is not None:
        hooks.setdefault(SCOPED_EVENT, []).append(scoped_group(command))
    parts = {HOOK_FILE: Part(json.dumps({"hooks": hooks}, indent=2) + "\n")}
    for source, _ in sources:
        for copied in COPIED:
            directory = source / copied
            if fsops.is_dir(directory):
                for relative, part in _copied(directory).items():
                    parts[f"{copied}/{relative}"] = part
    return parts


def _digest(files: Mapping[str, Part]) -> str:
    digest = hashlib.sha256()
    for relative in sorted(files):
        content = files[relative].text.encode("utf-8")
        digest.update(f"{relative}\0{len(content)}\0".encode())
        digest.update(content)
    return digest.hexdigest()


def write(id: str, parts: Mapping[str, Part], *, stale: tuple[str, ...] = ()) -> RenderRecord:
    """Write the marketplace, the plugin's manifest and `parts` under `<data>/delivery/<id>/`,
    replacing what is there, and remove each of `stale` this render no longer holds.

    `stale` is the parts an earlier render recorded, paths relative to the render directory, named
    before anything is looked at and each removed through the contained walk, so none can reach
    past the directory the id names."""
    marketplace = {
        "name": marketplace_name(id),
        "owner": {"name": "stayfixed"},
        "plugins": [
            {
                "name": plugin_name(id),
                "source": f"./{PLUGIN_DIRECTORY}",
                "description": _DESCRIPTION,
            }
        ],
    }
    plugin = {"name": plugin_name(id), "description": _DESCRIPTION}
    files = {
        MARKETPLACE_FILE: Part(json.dumps(marketplace, indent=2) + "\n"),
        PLUGIN_FILE: Part(json.dumps(plugin, indent=2) + "\n"),
        **{f"{PLUGIN_DIRECTORY}/{relative}": part for relative, part in parts.items()},
    }
    directory = delivery_directory(id)
    # The plain-path form for the directory itself, as `binding.record` writes this machine's own
    # data directory; every file inside it goes through the walk that refuses a symlink.
    directory.mkdir(parents=True, exist_ok=True)
    for relative, part in files.items():
        fsops.write_within(directory, relative, part.text, mode=part.mode)
    for relative in stale:
        if relative not in files:
            fsops.remove_within(directory, relative)
            fsops.rmdir_parents_within(directory, relative)
    return RenderRecord(id, _digest(files), tuple(sorted(files)))


def render(overlay: Path, project: str, id: str, *, stale: tuple[str, ...] = ()) -> RenderRecord:
    """`read_parts`, then `write`: the overlay's executable parts as the plugin `overlay-<id>`."""
    return write(id, read_parts(overlay, project), stale=stale)
