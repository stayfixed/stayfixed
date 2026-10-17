"""The machine owner's layer: personal values, the guards' switches and the session budgets.

The preset's `[defaults.personal]`, `Guards()` and no session budget, overridden by the machine
file's `[personal]`, `[guards]` and `[budgets]`, resolved through `classes.resolve` as the layers
`PRESET` and `MACHINE_FILE`. The machine file is the owner's, never a repository's
(`config.machine` says why no variable moves it), so it is the one place a guard may be switched
off; a repository's `[guards]` is a layer `classes.ALLOWED` does not admit.

Two readers ask, and they differ only over a file that does not load. A command the owner runs
refuses it (`Unknown.REFUSE`, which `config.loader` asks for every load of a command), as
`config.overlay.overlay_root` refuses it; a session must go on (`Unknown.NOTE`), and the preset's
values stand in, with `MACHINE_FILE_NOTE`. In a file that loads, an unknown key, a gate's budget
or an unusable value costs that key alone, with a note, for both: what the owner sets is honoured,
and what this stayfixed cannot use is said and never a block. Refused, a key a later release's
`setup` writes would stop every older command on the machine — the CLI and the plugin's hooks are
easily two versions — over a key none of them reads, and no boundary rests on the refusal: no
repository writes this file. A command says the notes on stderr (`said_on_stderr`). Every
sentence names the file and the key — the key through `printed.clipped`, since a TOML key is any
quoted text — and never a value.
"""

from __future__ import annotations

import sys
from collections.abc import Mapping
from dataclasses import dataclass, fields
from pathlib import Path
from types import MappingProxyType
from typing import Any, cast

from stayfixed.config.classes import GATE_BUDGETS, Layer, LayerName, resolve
from stayfixed.config.reading import (
    ConfigError,
    MachineConfigError,
    Unknown,
    coerced,
    read_machine_toml,
    schema_types,
)
from stayfixed.config.schema import Budgets, Personal
from stayfixed.presets import DEFAULT_PRESET, load_preset
from stayfixed.printed import clipped


@dataclass(frozen=True)
class Guards:
    """The session guards' switches. On unless the owner's machine file switches one off."""

    bg_cleanup: bool = True


@dataclass(frozen=True)
class Owner:
    """The owner's resolved values, where each came from, and what could not be used."""

    personal: Personal
    guards: Guards
    # The session budgets the machine file set, by budget name: what the owner's layer adds to a
    # project's `[budgets]`, and nothing where the file says nothing.
    session_budgets: Mapping[str, int]
    provenance: Mapping[str, LayerName]
    notes: tuple[str, ...]


# A machine file that does not load. `error` is `read_machine_toml`'s refusal, which names the file
# and the parser's position or the error's class, and never the file's text.
MACHINE_FILE_NOTE = (
    "{error}, so the preset's personal values and guards stand in for the machine file's"
)
# What one table or key of a readable machine file got wrong, in the note that says what happened
# to the value.
UNKNOWN_KEY = "[{table}] has a key this stayfixed does not read: {key}"
GATE_BUDGET = (
    "budgets.{name} is a gate's budget, which only a repository's stayfixed.toml sets; the "
    "machine file sets only a session's"
)
NOT_A_TABLE = "[{table}] must be a table"
IGNORED_NOTE = "{path}: {problem}; it is ignored"
MACHINE_RESET_NOTE = "{path}: {problem}; the preset's value applies"


def resolve_owner(
    machine: Path | None,
    *,
    preset: str = DEFAULT_PRESET,
    unknown: Unknown = Unknown.NOTE,
) -> Owner:
    """The owner's layer over the preset named `preset`.

    `preset` is a preset this build ships, and every caller holds it to that before it asks: the
    project loader hands the name its own `_preset` has already loaded, and a session the
    document's name only when it is shipped, `DEFAULT_PRESET` otherwise (`config.session`). The
    repository's value is the loader's to judge, so it is refused or reset once, in the loader's
    words. `machine` is the machine file; `None`, a machine with no home to hold one
    (`machine_config_path`), is read as no file, as an absent file is.
    """
    notes: list[str] = []
    shipped = load_preset(preset)
    lower: dict[str, object] = {
        f"personal.{key}": value
        for key, value in shipped.get("defaults", {}).get("personal", {}).items()
    }
    lower.update({f"guards.{field.name}": field.default for field in fields(Guards)})

    try:
        raw = None if machine is None else read_machine_toml(machine)
    except MachineConfigError as exc:
        if unknown is Unknown.REFUSE:
            raise
        raw = None
        notes.append(MACHINE_FILE_NOTE.format(error=exc))
    upper: dict[str, object] = {}
    if raw is not None and machine is not None:
        upper = _machine_values(raw, machine, notes)

    resolution = resolve([Layer(LayerName.PRESET, lower), Layer(LayerName.MACHINE_FILE, upper)])
    values = resolution.values
    personal = Personal(**_section(values, "personal"))
    guards = Guards(**_section(values, "guards"))
    # `_machine_values` admitted only a positive integer under `budgets.`, and the preset layer
    # carries none.
    session_budgets = {
        key.removeprefix("budgets."): cast(int, value)
        for key, value in values.items()
        if key.startswith("budgets.") and resolution.provenance[key] is LayerName.MACHINE_FILE
    }
    return Owner(
        personal=personal,
        guards=guards,
        session_budgets=MappingProxyType(session_budgets),
        provenance=resolution.provenance,
        notes=(*notes, *resolution.notes),
    )


def said_on_stderr(owner: Owner) -> Owner:
    """`owner`, after its notes are said on stderr, one line each: how a command tells its reader
    what it read past in the machine file, beside an answer on stdout that `--json` keeps whole."""
    for note in owner.notes:
        print(f"stayfixed: {note}", file=sys.stderr)
    return owner


def _section(values: Mapping[str, object], section: str) -> dict[str, Any]:
    prefix = f"{section}."
    return {
        key.removeprefix(prefix): value for key, value in values.items() if key.startswith(prefix)
    }


def _machine_values(raw: dict[str, Any], machine: Path, notes: list[str]) -> dict[str, object]:
    """The machine file's `[personal]`, `[guards]` and session `[budgets]` as dotted keys.

    Every other table is another reader's (`[overlay]`, `[machine]`) or nobody's, and is not this
    function's to judge. A problem is a note, and costs only its own key, or its own table when the
    table is not one. A value is held to its key's
    schema type by `coerced`, the project loader's rule, and kept as `coerced` gives it.
    """

    def problem(sentence: str, *, ignored: bool) -> None:
        template = IGNORED_NOTE if ignored else MACHINE_RESET_NOTE
        notes.append(template.format(path=machine, problem=sentence))

    found: dict[str, object] = {}
    for table in ("personal", "guards", "budgets"):
        if table not in raw:
            continue
        values = raw[table]
        if not isinstance(values, dict):
            problem(NOT_A_TABLE.format(table=table), ignored=False)
            continue
        types = _types(table)
        for key, value in values.items():
            if key not in types:
                problem(UNKNOWN_KEY.format(table=table, key=clipped(key)), ignored=True)
            elif table == "budgets" and key in GATE_BUDGETS:
                # Before `resolve`, which would refuse it too, so the note says which budgets the
                # owner does set rather than only that this layer may not.
                problem(GATE_BUDGET.format(name=key), ignored=True)
            else:
                try:
                    found[f"{table}.{key}"] = coerced(f"{table}.{key}", types[key], value)
                except ConfigError as exc:
                    problem(str(exc), ignored=False)
    return found


def _types(table: str) -> Mapping[str, Any]:
    """The keys `table` holds and the schema type of each, which `coerced` holds its value to:
    every budget is an integer, and `[personal]` and `[guards]` are their classes' fields."""
    if table == "budgets":
        return dict.fromkeys(Budgets.NAMES, int)
    return schema_types(Personal if table == "personal" else Guards)
