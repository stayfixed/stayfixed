"""What a session runs on: the project's configuration, read the way a session must, and the owner's
layer.

A session never dies of its configuration. A command refuses a `stayfixed.toml` it cannot use whole,
because a person is about to act on it; a hook has no person to tell, and a `PreToolUse` that
refused because a file did not load would stop every tool call for something no guard decided. So
`session_config` answers for anything the repository or the machine file holds, and says what it
could not use in one warning, which `SessionStart` shows (`hooks.dispatch`):

- no `stayfixed.toml`: no project configuration, and nothing to say;
- one that is a symbolic link, is not UTF-8, cannot be read or is not TOML: no project
  configuration, and `FALLBACK_WARNING`;
- one whose key cannot be used and has nothing to stand in for it — a required key, or a section
  holding one, that the document got wrong or never wrote, or a preset value that does not hold in
  this repository — no project configuration, and `UNUSABLE_WARNING` naming the key;
- one that loads with notes (`loader.loads_noting`): the configuration, and `NEWER_RELEASE_WARNING`
  when its `[stayfixed] version` is later than the running one, `NOTED_WARNING` otherwise.

The owner's layer is resolved under `Unknown.NOTE` whatever the project holds, so the guards run on
the preset and the machine file in every one of those cases, and a machine file that could not be
used whole adds `MACHINE_FILE_WARNING`. Every warning is a constant in stayfixed's own words: it
reaches the model, so the one value of the repository's it carries, a key, is printed through
`printed.printable`.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

from stayfixed import __version__
from stayfixed.config.loader import (
    UNPARSEABLE,
    ConfigError,
    MissingKeys,
    UnusableKey,
    loads_noting,
    read_document,
)
from stayfixed.config.machine import machine_config_path
from stayfixed.config.owner import FALLBACK_PRESET, Owner, resolve_owner
from stayfixed.config.paths import PathEscape
from stayfixed.config.schema import Config
from stayfixed.presets import shipped_presets
from stayfixed.printed import printable
from stayfixed.semver import later

# How every warning opens, and how the two that drop the project configuration close: `doctor`
# shows the words between (`cause`), since it is where that pointer leads.
PREFIX = "stayfixed: "
DOCTOR_DETAIL = "; run `stayfixed doctor` for the detail"
FALLBACK_WARNING = (
    f"{PREFIX}stayfixed.toml does not load — it is a symbolic link, is not UTF-8 text, cannot "
    "be read or is not TOML — so this session runs the guards on the preset and the machine "
    f"owner's layer, without the project's settings{DOCTOR_DETAIL}"
)
UNUSABLE_WARNING = (
    f"{PREFIX}in stayfixed.toml, {{key}} cannot be used and nothing can stand in for it, so this "
    "session runs the guards on the preset and the machine owner's layer, without the project's "
    f"settings{DOCTOR_DETAIL}"
)
# What `UNUSABLE_WARNING` says for a key `printable` withholds, or for a refusal that named none.
UNNAMED_KEY = "a setting"
NOTED_WARNING = (
    "stayfixed: stayfixed.toml loaded with {count} setting(s) ignored or put back to the "
    "preset's; run `stayfixed doctor` for the list"
)
# The remedy is `doctor`'s `VERSION_AHEAD`'s: `stayfixed upgrade` never moves a project backward,
# so the way out of a file a later release wrote is a later plugin.
NEWER_RELEASE_WARNING = (
    "stayfixed: stayfixed.toml was written by a newer stayfixed, so {count} setting(s) this one "
    "does not read were ignored or put back to the preset's; update the stayfixed plugin, and run "
    "`stayfixed doctor` for the list"
)
MACHINE_FILE_WARNING = (
    "stayfixed: the machine file, ~/.config/stayfixed/config.toml, could not be used whole, so the "
    "preset's personal values and guards stand in for what it could not give; run `stayfixed "
    "doctor` for the detail"
)


@dataclass(frozen=True)
class SessionConfig:
    """The project's configuration, or `None` where there is none to use; the owner's layer, which
    there always is; and the warnings `SessionStart` shows, at most one about each file.

    `noted` is the dotted key of every setting the project's file had ignored or reset, in the
    order of its notes, for `doctor` to list by key alone: a key is text the document chose."""

    config: Config | None
    owner: Owner
    warnings: tuple[str, ...]
    noted: tuple[str, ...] = ()


def session_config(root: Path | None, *, machine: Path | None = None) -> SessionConfig:
    """The configuration a session runs on in `root`, which never raises for anything the
    repository or the machine file holds.

    `machine` is the machine file; `None` is the one `config.machine` names, which no variable
    moves, as `loader.load` reads it. `root` is `None` for a hook with no project root, which has
    no project configuration.
    """
    path = machine if machine is not None else machine_config_path()
    try:
        text = None if root is None else read_document(root)
    except (ConfigError, PathEscape):
        # `read_document` refuses a symlink through `contained()` before it follows it, so a link
        # to a loadable file and one to `/dev/zero` meet the same rule.
        return _fallback(path, FALLBACK_WARNING)
    if root is None or text is None:
        return SessionConfig(None, resolve_owner(path), ())
    try:
        raw = tomllib.loads(text)
    except UNPARSEABLE:
        return _fallback(path, FALLBACK_WARNING)
    owner = resolve_owner(path, preset=_preset(raw))
    try:
        noted = loads_noting(text, root, owner=owner)
    except UnusableKey as exc:
        return _with_owner(owner, _unusable(exc.key))
    except MissingKeys as exc:
        return _with_owner(owner, _unusable(exc.missing[0]))
    except (ConfigError, PathEscape) as exc:
        # Every refusal `loads_noting` raises past the two above names a key or is the document
        # not parsing, which `tomllib` already answered; this arm is for one it has not, so that a
        # session still goes on.
        return _with_owner(owner, _unusable(exc.key))
    warnings: tuple[str, ...] = ()
    if noted.notes:
        newer = later(noted.config.stayfixed.version, __version__) is True
        template = NEWER_RELEASE_WARNING if newer else NOTED_WARNING
        warnings = (template.format(count=len(noted.notes)),)
    return SessionConfig(noted.config, owner, warnings + _owners(owner), noted.keys)


def cause(warning: str) -> str:
    """`warning` without its opening and without the pointer at `doctor`: what `doctor` says of
    the same state, where pointing at itself would say nothing."""
    return warning.removeprefix(PREFIX).removesuffix(DOCTOR_DETAIL)


def _preset(raw: dict[str, object]) -> str:
    """The preset the owner's layer stands on: the document's, when it names one this build ships,
    and `FALLBACK_PRESET` otherwise, which is what the NOTE load resets an unshipped one to. So an
    unshipped name is one note, the loader's, and not the owner's `UNKNOWN_PRESET_NOTE` too.
    """
    head = raw.get("stayfixed")
    named = head.get("preset", FALLBACK_PRESET) if isinstance(head, dict) else FALLBACK_PRESET
    return named if isinstance(named, str) and named in shipped_presets() else FALLBACK_PRESET


def _unusable(key: str | None) -> str:
    return UNUSABLE_WARNING.format(key=printable(key, UNNAMED_KEY) if key else UNNAMED_KEY)


def _owners(owner: Owner) -> tuple[str, ...]:
    return (MACHINE_FILE_WARNING,) if owner.notes else ()


def _with_owner(owner: Owner, warning: str) -> SessionConfig:
    return SessionConfig(None, owner, (warning, *_owners(owner)))


def _fallback(machine: Path | None, warning: str) -> SessionConfig:
    return _with_owner(resolve_owner(machine), warning)
