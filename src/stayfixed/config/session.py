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
- one longer than a session reads (`SESSION_READ_LIMIT`), read no further: no project
  configuration, and `TOO_LARGE_WARNING`;
- one holding more settings it cannot use than the NOTE load removes (`loader.NOTE_REMOVAL_LIMIT`,
  and fewer for a long file, `loader.NOTE_REBUILT_LIMIT`): no project configuration, and
  `TOO_MANY_WARNING`;
- one whose key cannot be used and has nothing to stand in for it — a required key, or a section
  holding one, that the document got wrong or never wrote, or a preset value that does not hold in
  this repository — no project configuration, and `UNUSABLE_WARNING` naming the key;
- one that loads with notes (`loader.loads_noting`): the configuration, and `NEWER_RELEASE_WARNING`
  when its `[stayfixed] version` is later than the running one, `NOTED_WARNING` otherwise.

The owner's layer is resolved, not `strict`, whatever the project holds, so the guards run on the
preset and the machine file in every one of those cases, and a machine file that could not be used
whole adds `MACHINE_FILE_WARNING`. Every warning is a constant in stayfixed's own words: it
reaches the model, so the one value of the repository's it carries, a key, is printed through
`printed.printable`.
"""

from __future__ import annotations

import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from stayfixed import __version__
from stayfixed.config.loader import (
    MissingKeys,
    TooLargeDocument,
    TooManyResets,
    UnusableKey,
    loads_noting,
    preset_named,
    read_document,
)
from stayfixed.config.machine import machine_config_path
from stayfixed.config.owner import Owner, resolve_owner
from stayfixed.config.paths import PathEscape
from stayfixed.config.reading import UNPARSEABLE, ConfigError
from stayfixed.config.schema import Config
from stayfixed.printed import printable
from stayfixed.semver import later

# A named cap: the most bytes of `stayfixed.toml` a session reads. A hook has the ten seconds
# `hooks/hooks.json` gives each entry, and a `PreToolUse` hook that runs past them loses its guard,
# so what the parse and the NOTE load cost,
# each in proportion to the file, is bounded by the file before either starts: a 2.8 MB file of
# custom gates kept a hook fourteen seconds, and at 1 MiB the costliest file a session read took 6
# to 7.5 s of CPU on a laptop's efficiency cores. A `stayfixed.toml` that `init` writes is a few
# hundred bytes, and one that spells out every setting and a few dozen gates is a few kilobytes;
# 256 KiB is still dozens of times the second, and the costliest file of that length takes 0.25 s
# on Python 3.13 and 1.4 to 1.5 s on efficiency cores (`loader.NOTE_REBUILT_LIMIT` gives its
# shape). A command reads the file to `fsops.REGULAR_READ_LIMIT`.
SESSION_READ_LIMIT = 256 * 1024
# How every warning opens, and how the two that drop the project configuration close: `doctor`
# shows the words between (`cause`), since it is where that pointer leads.
PREFIX = "stayfixed: "
DOCTOR_DETAIL = "; run `stayfixed doctor` for the detail"
FALLBACK_WARNING = (
    f"{PREFIX}stayfixed.toml does not load — it is a symbolic link, is not UTF-8 text, cannot "
    "be read or is not TOML — so this session runs the guards on the preset and the machine "
    f"owner's layer, without the project's settings{DOCTOR_DETAIL}"
)
TOO_LARGE_WARNING = (
    f"{PREFIX}stayfixed.toml is larger than the {SESSION_READ_LIMIT:,} bytes a session reads, so "
    "this session runs the guards on the preset and the machine owner's layer, without the "
    f"project's settings{DOCTOR_DETAIL}"
)
UNUSABLE_WARNING = (
    f"{PREFIX}in stayfixed.toml, {{key}} cannot be used and nothing can stand in for it, so this "
    "session runs the guards on the preset and the machine owner's layer, without the project's "
    f"settings{DOCTOR_DETAIL}"
)
# A file holding more settings this stayfixed cannot use than the NOTE load reads past one by one,
# `limit` (`loader.TooManyResets`): read key by key, it would cost a hook more than its timeout,
# which Claude Code answers by letting the call through.
TOO_MANY_WARNING = (
    f"{PREFIX}stayfixed.toml holds more than {{limit}} settings this stayfixed cannot use, so this "
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
# `path` is the machine file that was read, the owner's own path, never the repository's.
MACHINE_FILE_WARNING = (
    "stayfixed: the machine file, {path}, could not be used whole, so the preset's personal values "
    "and guards stand in for what it could not give; run `stayfixed doctor` for the detail"
)


@dataclass(frozen=True)
class SessionConfig:
    """The project's configuration, or `None` where there is none to use; the owner's layer, which
    there always is; and the warnings `SessionStart` shows, at most one about each file: the
    project file's (`project_warnings`) and the machine file's (`machine_warnings`).

    `noted` is the dotted key of every setting the project's file had ignored or reset, in the
    order of its notes, for `doctor` to list by key alone: a key is text the document chose.
    `document` is the project's file as the NOTE load used it (`loader.Noted.document`), for
    `doctor` to tell which values the repository set from the one read the session made."""

    config: Config | None
    owner: Owner
    project_warnings: tuple[str, ...] = ()
    machine_warnings: tuple[str, ...] = ()
    noted: tuple[str, ...] = ()
    document: Mapping[str, Any] = field(default_factory=dict)

    @property
    def warnings(self) -> tuple[str, ...]:
        """Every warning `SessionStart` shows: the project file's, then the machine file's."""
        return (*self.project_warnings, *self.machine_warnings)


def session_config(root: Path | None, *, machine: Path | None = None) -> SessionConfig:
    """The configuration a session runs on in `root`, which never raises for anything the
    repository or the machine file holds.

    `machine` is the machine file; `None` is the one `config.machine` names, which no variable
    moves, as `loader.load` reads it. `root` is `None` for a hook with no project root, which has
    no project configuration.
    """
    path = machine if machine is not None else machine_config_path()
    try:
        text = None if root is None else read_document(root, limit=SESSION_READ_LIMIT)
    except TooLargeDocument:
        return _fallback(path, TOO_LARGE_WARNING)
    except (ConfigError, PathEscape):
        # `read_document` refuses a symlink through `contained()` before it follows it, so a link
        # to a loadable file and one to `/dev/zero` meet the same rule.
        return _fallback(path, FALLBACK_WARNING)
    if root is None or text is None:
        # Nothing of the project's to read, and the machine file is read all the same: a broken one
        # is named here as beside any project file.
        owner = resolve_owner(path)
        return SessionConfig(None, owner, machine_warnings=_owners(owner, path))
    try:
        raw = tomllib.loads(text)
    except UNPARSEABLE:
        return _fallback(path, FALLBACK_WARNING)
    owner = resolve_owner(path, preset=preset_named(raw))
    try:
        # Parsed once, above: the NOTE load reads the same document rather than parsing it again.
        noted = loads_noting(text, root, owner=owner, parsed=raw)
    except UnusableKey as exc:
        return _with_owner(owner, path, _unusable(exc.key))
    except MissingKeys as exc:
        return _with_owner(owner, path, _unusable(exc.missing[0]))
    except TooManyResets as exc:
        return _with_owner(owner, path, TOO_MANY_WARNING.format(limit=exc.limit))
    except (ConfigError, PathEscape) as exc:
        # Every refusal `loads_noting` raises past the two above names a key or is the document
        # not parsing, which `tomllib` already answered; this arm is for one it has not, so that a
        # session still goes on.
        return _with_owner(owner, path, _unusable(exc.key))
    warnings: tuple[str, ...] = ()
    if noted.notes:
        newer = later(noted.config.stayfixed.version, __version__) is True
        template = NEWER_RELEASE_WARNING if newer else NOTED_WARNING
        warnings = (template.format(count=len(noted.notes)),)
    return SessionConfig(
        noted.config, owner, warnings, _owners(owner, path), noted.keys, noted.document
    )


def cause(warning: str) -> str:
    """`warning` without its opening and without the pointer at `doctor`: what `doctor` says of
    the same state, where pointing at itself would say nothing."""
    return warning.removeprefix(PREFIX).removesuffix(DOCTOR_DETAIL)


def _unusable(key: str | None) -> str:
    return UNUSABLE_WARNING.format(key=printable(key, UNNAMED_KEY) if key else UNNAMED_KEY)


def _owners(owner: Owner, machine: Path | None) -> tuple[str, ...]:
    # The owner's layer has notes only for a machine file it read, so `machine` is a path here.
    return (MACHINE_FILE_WARNING.format(path=machine),) if owner.notes else ()


def _with_owner(owner: Owner, machine: Path | None, warning: str) -> SessionConfig:
    return SessionConfig(None, owner, (warning,), _owners(owner, machine))


def _fallback(machine: Path | None, warning: str) -> SessionConfig:
    return _with_owner(resolve_owner(machine), machine, warning)
