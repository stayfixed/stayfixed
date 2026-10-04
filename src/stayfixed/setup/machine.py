"""Write the machine configuration file, the one both existing readers already read.

**This module invents no schema.** `config.loader._personal` reads `[personal]` and
`config.overlay.overlay_root` reads `[overlay] root`, both with `interactive=False`, and neither
changes here. This writer adds `[machine]` beside them — what `setup` installed, so `doctor`
can check it later — and nothing else. A caller that wants a fourth table is asking for a third
reader of this file, which the same rule keeps out.

**A rewrite merges, table by table, key by key — including the tables this writer knows
nothing about.** `setup` runs again on a machine that already has a file, and the common case is
"set the personal languages, leave the overlay alone" or the reverse — `overlay_root=None` means
*this call does not know*, not *forget what was recorded*, so an unset value is simply not
written over and survives in the table it was spread onto. The three tests this file exists to
satisfy are the
three ways that can go wrong: nothing recorded stays nothing recorded, a value nobody touched
survives a rewrite that touched something else, and one table's `root` never collapses into a
fourth state (see `config.overlay.overlay_root`'s own docstring on that).

The docstring used to say "table by table" while the merge covered exactly three hard-coded
names and then replaced the whole file, so a `[trust]` table or a key at the top level was gone
after one `setup`. `README.md` lists this file under "Written by: **you**, or `stayfixed setup`",
which makes a table this writer does not recognise the ordinary case rather than the exotic one:
every one of them is carried through in the file's own order, and the three it owns are merged
in place.

**Two things a rewrite still costs, both stated rather than discovered.** Comments do not
survive — `tomllib` discards them on the way in, and there is no round-tripping parser in the
standard library to keep them — and a key that is not a bare TOML key cannot be re-emitted.
Neither may wedge the command: `tomlout` emits every *value* type a TOML document can hold, so
the float and the nested table that used to make every future run exit 2 round-trip now, and
the one refusal left names this file, the key, and what to do about it instead of naming a
serialiser the owner has never heard of.

**`fsops.write_atomically` on a bare `Path`, not `fsops.write_within`.** Every other writer
`setup` uses owns a root — a project checkout, the overlay — and walks into it with `O_NOFOLLOW`.
This file has no such root: `config.machine.machine_config_path` resolves to
`~/.config/stayfixed/config.toml` or wherever `--machine`/`STAYFIXED_CONFIG`/`XDG_CONFIG_HOME`
sends it, and that directory is not one this process was handed as "the thing to stay inside
of". `fsops.write_atomically`'s own docstring names exactly this caller: "for callers that
already hold a trusted absolute path". The path is trusted because it is built out of fixed
strings this module and `config.machine` wrote (`"stayfixed"`, `"config.toml"`) or a path the
machine owner typed on their own command line — never a segment a repository chose, which is
what `mkdirs_within`'s containment exists to stop.

Every string that reaches `tomlout.dumps` is repository-*adjacent* rather than
repository-authored — the overlay root and the personal languages are values the machine owner
typed — but it goes through the one serialiser anyway: `tomlout`'s own docstring says why a
second writer, hand-rolled for "just this one path", is the mistake this module exists to not
repeat.
"""

from __future__ import annotations

import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from stayfixed import fsops, tomlout
from stayfixed.errors import Refusal

# The one machine-scope settings file `setup` writes, relative to `home`, and the one `doctor`'s
# `hook-entries` check reads back. Codex has no equivalent: whether Codex has anything like a
# plugin's `userConfig` has never been measured, so nothing is written there and the report says
# so rather than guessing a path.
USER_SETTINGS = ".claude/settings.json"


@dataclass(frozen=True)
class Written:
    """What `write_machine` wrote. `path` is the file, for a caller that wants to say where."""

    path: Path


def read_machine(path: Path) -> dict[str, Any]:
    """The machine file as a raw `dict`, exactly as `tomllib` parses it.

    A file that is not UTF-8 or not TOML is the loader's `MachineConfigError`, the one failure
    every reader of this file gives, naming the position and never the parser's message.
    """
    from stayfixed.config.loader import NOT_UTF8, UNPARSEABLE, MachineConfigError, toml_position

    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except UnicodeDecodeError:
        raise MachineConfigError(NOT_UTF8.format(path=path)) from None
    except UNPARSEABLE as exc:
        raise MachineConfigError(f"{path} is not valid TOML {toml_position(exc)}") from None


def _existing(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    return read_machine(path)


def _table(raw: dict[str, Any], name: str) -> dict[str, Any]:
    value = raw.get(name)
    return dict(value) if isinstance(value, dict) else {}


def write_machine(
    path: Path,
    *,
    personal: Mapping[str, object],
    overlay_root: Path | None,
    machine: Mapping[str, object],
) -> Written:
    """Merge `personal`, `overlay_root` and `machine` into the file at `path`, and write it.

    Each of the three is merged over what the file already holds, key by key, rather than
    replacing its table outright — a second `setup` run that only sets one of them must not
    erase what an earlier run recorded, which both unchanged readers still read (the test this
    docstring's module comment names). `overlay_root=None` reads as "not given this run": the
    existing `[overlay] root`, if any, is carried over unchanged. There is no way to ask this
    function to *clear* a recorded overlay root; nothing in stayfixed needs one.

    Everything else in the file — a table this writer has never heard of, a key at the top
    level — is carried through untouched, in the order it was written in.
    """
    existing = _existing(path)

    merged_personal = {**_table(existing, "personal"), **personal}
    # All three spread over the existing table. `overlay` used to replace its table outright,
    # which the two lines around it did not: a hand-written `[overlay] note` was gone after
    # any `setup`, and an `[overlay]` carrying no `root` vanished whole -- on the file this
    # module's own docstring promises to merge "table by table, key by key".
    #
    # That spread is also what carries a recorded `root` through a run that was not given one.
    # There used to be an explicit read-back here -- `root = overlay_root` and, when it was
    # `None`, the existing `[overlay] root` parsed back into a `Path` -- written when this table
    # was still replaced wholesale. Once the spread arrived it was dead code that looked like a
    # guard: its entry disarmed it and every test stayed green. The property is declared now where
    # the spread keeps it, as `mutations/`'s "write_machine replaces the overlay table instead of
    # merging over it".
    owned: dict[str, dict[str, object]] = {
        "personal": merged_personal,
        "overlay": {
            **_table(existing, "overlay"),
            **({"root": str(overlay_root)} if overlay_root is not None else {}),
        },
        "machine": {**_table(existing, "machine"), **machine},
    }

    tables: dict[str, dict[str, object]] = {}
    # A key outside every table comes first, because TOML reads everything after a header as
    # belonging to it. Nothing this project writes here puts one there; a person might.
    loose = {key: value for key, value in existing.items() if not isinstance(value, dict)}
    if loose:
        tables[""] = loose
    for name, value in existing.items():
        if not isinstance(value, dict):
            continue
        if name in owned:
            if owned[name]:
                tables[name] = owned[name]
        else:
            tables[name] = dict(value)
    for name, table in owned.items():
        if table and name not in tables:
            tables[name] = table

    try:
        text = tomlout.dumps(tables)
    except Refusal as exc:
        # The one shape left that cannot be re-emitted: a key this serialiser cannot write bare.
        # It reached the owner as `Refusal: personal.scale holds a …` — no path, no remedy, and
        # the name of a module they have never heard of — on *every* future run, because the
        # file is read back at the top of every one of them.
        raise Refusal(
            f"{path} cannot be rewritten: {exc}. `stayfixed setup` rewrites this file, so it has "
            f"to be able to write back everything in it; remove or rename that key and run the "
            f"command again"
        ) from exc
    fsops.write_atomically(path, text)
    return Written(path)
