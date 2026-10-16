"""The machine owner's layer: personal values, the guards' switches and the session budgets.

The preset's `[defaults.personal]`, `Guards()` and no session budget, overridden by the machine
file's `[personal]`, `[guards]` and `[budgets]`, resolved through `classes.resolve` as the layers
`PRESET` and `MACHINE_FILE`. The machine file is the owner's, never a repository's
(`config.machine` says why no variable moves it), so it is the one place a guard may be switched
off; a repository's `[guards]` is a layer `classes.ALLOWED` does not admit.

Two readers ask, and they want different answers to a file that is wrong. A command the owner
runs refuses it (`Unknown.REFUSE`, which `config.loader` asks for every load of a command), naming
the file and the key.
A session must go on (`Unknown.NOTE`): a file that does not load gives the preset's values and
`MACHINE_FILE_NOTE`, and an unknown key, a gate's budget or an unusable value costs that key alone,
with a note. Every sentence names the file and the key — the key through `printed.clipped`, since
a TOML key is any quoted text — and never a value.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping
from dataclasses import dataclass, fields
from pathlib import Path
from types import MappingProxyType
from typing import Any, cast

from stayfixed.config.classes import GATE_BUDGETS, Layer, LayerName, resolve
from stayfixed.config.reading import (
    NOT_A_PRESET_NAME,
    ConfigError,
    MachineConfigError,
    Unknown,
    positive,
    read_machine_toml,
    schema_types,
)
from stayfixed.config.schema import Budgets, Personal
from stayfixed.presets import DEFAULT_PRESET, available, load_preset, shipped_presets
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
# What one table or key of a readable machine file got wrong. Under `REFUSE` the sentence is the
# refusal, after the file's path; under `NOTE` it is the note, with what happened to the value.
UNKNOWN_KEY = "[{table}] has a key this stayfixed does not read: {key}"
GATE_BUDGET = (
    "budgets.{name} is a gate's budget, which only a repository's stayfixed.toml sets; the "
    "machine file sets only a session's"
)
NOT_A_TABLE = "[{table}] must be a table"
NOT_A_STRING = "{key} must be a string"
NOT_A_SWITCH = "{key} must be true or false"
IGNORED_NOTE = "{path}: {problem}; it is ignored"
MACHINE_RESET_NOTE = "{path}: {problem}; the preset's value applies"
# A preset name this build does not ship, under `NOTE`. The name is the repository's, so it is
# printed through `printed.clipped`; `REFUSE` raises the preset loader's refusal, which never
# prints it.
UNKNOWN_PRESET_NOTE = (
    "{name} is not a preset this stayfixed ships, so the owner's layer stands on the "
    f"{DEFAULT_PRESET} preset's personal values"
)
# A preset value that is not a string at all, which no name of a preset can be: there is nothing
# to print, and a `TOML` value of another type is none of `printed`'s to bound.
UNREADABLE_PRESET_NOTE = (
    "stayfixed.preset is not a string, so the owner's layer stands on the "
    f"{DEFAULT_PRESET} preset's personal values"
)


def resolve_owner(
    machine: Path | None,
    *,
    preset: object = DEFAULT_PRESET,
    unknown: Unknown = Unknown.NOTE,
) -> Owner:
    """The owner's layer over the preset named `preset`.

    `preset` is the repository's preset value as the document wrote it, else `recommended`. A
    name this build does not ship is refused under `REFUSE`, as the preset loader refuses it, and
    so is a value that is not a string; under `NOTE` the owner's layer stands on
    `DEFAULT_PRESET` with `UNKNOWN_PRESET_NOTE` or `UNREADABLE_PRESET_NOTE`, since a session
    reads the value from a `stayfixed.toml` before anything has held it to the shipped presets.
    `machine` is the machine file; `None`, a machine with no home to hold one
    (`machine_config_path`), is read as no file, as an absent file is.
    """
    notes: list[str] = []
    if not isinstance(preset, str):
        if unknown is Unknown.REFUSE:
            raise ConfigError(NOT_A_PRESET_NAME.format(available=available()))
        notes.append(UNREADABLE_PRESET_NOTE)
        preset = DEFAULT_PRESET
    elif unknown is Unknown.NOTE and preset not in shipped_presets():
        notes.append(UNKNOWN_PRESET_NOTE.format(name=clipped(preset)))
        preset = DEFAULT_PRESET
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
        upper = _machine_values(raw, machine, unknown, notes)

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


def _section(values: Mapping[str, object], section: str) -> dict[str, Any]:
    prefix = f"{section}."
    return {
        key.removeprefix(prefix): value for key, value in values.items() if key.startswith(prefix)
    }


def _machine_values(
    raw: dict[str, Any], machine: Path, unknown: Unknown, notes: list[str]
) -> dict[str, object]:
    """The machine file's `[personal]`, `[guards]` and session `[budgets]` as dotted keys.

    Every other table is another reader's (`[overlay]`, `[machine]`, `[setup]`) or nobody's, and
    is not this function's to judge. A problem raises under `REFUSE` and is a note under `NOTE`,
    where it costs only its own key, or its own table when the table is not one.
    """

    def problem(sentence: str, *, ignored: bool) -> None:
        if unknown is Unknown.REFUSE:
            raise MachineConfigError(f"{machine}: {sentence}")
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
        for key, value in values.items():
            if key not in _keys(table):
                problem(UNKNOWN_KEY.format(table=table, key=clipped(key)), ignored=True)
            elif table == "budgets" and key in GATE_BUDGETS:
                # Before `resolve`, which would refuse it too, so the note says which budgets the
                # owner does set rather than only that this layer may not.
                problem(GATE_BUDGET.format(name=key), ignored=True)
            elif (sentence := _invalid(table, key, value)) is not None:
                problem(sentence, ignored=False)
            else:
                found[f"{table}.{key}"] = value
    return found


def _keys(table: str) -> Collection[str]:
    if table == "budgets":
        return Budgets.NAMES
    return schema_types(Personal if table == "personal" else Guards).keys()


def _invalid(table: str, key: str, value: object) -> str | None:
    """What is wrong with a known `table.key = value`, or `None` when nothing is."""
    dotted = f"{table}.{key}"
    if table == "budgets":
        try:
            positive(dotted, value)
        except ConfigError as exc:
            return str(exc)
        return None
    if table == "guards":
        return None if isinstance(value, bool) else NOT_A_SWITCH.format(key=dotted)
    return None if isinstance(value, str) else NOT_A_STRING.format(key=dotted)
