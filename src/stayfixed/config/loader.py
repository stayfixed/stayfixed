"""Read stayfixed.toml, merge it under the preset, validate it.

The machine config is merged too: `[personal]` read here, or the owner's layer
(`config.owner`) handed in, which adds its session budgets. `loads` refuses what it cannot use;
`loads_noting` reads what it can and says what it ignored or reset.
"""

from __future__ import annotations

import re
import tomllib
from collections.abc import Collection
from dataclasses import MISSING, dataclass, fields, replace
from enum import StrEnum
from functools import cache
from pathlib import Path
from typing import TYPE_CHECKING, Any, TypeVar, cast, get_origin, get_type_hints

from stayfixed import __version__, fsops
from stayfixed.config.classes import REFUSED_LAYER_NOTE, Layer, LayerName, resolve
from stayfixed.config.machine import machine_config_path
from stayfixed.config.paths import PathEscape, contained, validate_paths
from stayfixed.config.schema import (
    BRANCH_NAME,
    BRANCH_RULE,
    BUILTIN_GATES,
    CI_MODES,
    CONFIG_CHECK,
    MEMORY_MODES,
    NAME_RULE,
    PROJECT_NAME,
    SECTION_NAME,
    STATES,
    Artifacts,
    Budgets,
    Ci,
    CommitMessages,
    Config,
    CustomGate,
    Gates,
    Ledger,
    Memory,
    NativeCaps,
    Paths,
    Personal,
    Project,
    Stayfixed,
)
from stayfixed.errors import Failure
from stayfixed.findings import LISTED_LIMIT, listed
from stayfixed.fsops import read_regular_text, said
from stayfixed.presets import available, load_preset
from stayfixed.printed import clipped

if TYPE_CHECKING:
    # `config.owner` imports this module for `Unknown` and its reader of the machine file; a
    # loader that only reads an `Owner`'s two fields needs the type for its annotations alone.
    from stayfixed.config.owner import Owner

CONFIG_FILE = "stayfixed.toml"
# Where `tomllib` stopped, and nothing else it had to say. Every `TOMLDecodeError` this
# package can raise is about a document somebody else wrote — a project's `stayfixed.toml`, the
# machine file `--machine` named — and `tomllib` builds its message as `f"{msg} (at line N,
# column M)"`, where `msg` embeds the source for at least five of its own faults: `Cannot
# declare ('x',) twice`, `Duplicate inline table key 'k'`, `Cannot redefine namespace k`,
# `Found invalid character 'c'`, `Cannot overwrite a value`. A TOML key is arbitrary quoted
# text, so interpolating the exception whole puts unbounded repository bytes into a refusal a
# skill is instructed to relay to a model. The position is the actionable half and it is
# stayfixed-shaped: two integers, or the parser's end-of-document form. Measured against CPython
# 3.11 and 3.12; the suffix is what `tomllib` appends, not what its `msg` says, so a `msg`
# reworded upstream does not move it.
_TOML_POSITION = re.compile(r"\((?:at line \d+, column \d+|at end of document)\)\Z")
NO_POSITION = "(at a position tomllib did not report)"
# `tomllib` reads nested arrays and inline tables by recursion, so a document nested a few
# thousand levels deep — `a = [[[…]]]` — raises `RecursionError` and not `TOMLDecodeError`.
# Uncaught, that is an internal error, the class stayfixed keeps for its own defects, and in a
# gate run it ended every gate. And an integer literal longer than the interpreter converts
# (4,300 digits by default, `sys.get_int_max_str_digits`) is valid TOML that `tomllib` answers with
# a plain `ValueError`, which is not a `TOMLDecodeError`: one line of a committed file ended
# `doctor`, `gate` and `init` the same way. Every reader of a document somebody else wrote catches
# all three. `ValueError` is caught whole, `TOMLDecodeError` being one: no reader's `try` holds
# anything else that raises it but a decode, whose `UnicodeDecodeError` it catches first or
# answers as it answers a record that does not parse.
UNPARSEABLE = (tomllib.TOMLDecodeError, RecursionError, ValueError)
TOO_DEEP = "(nested deeper than the parser reads)"
TOO_LONG = "(holds a number longer than the parser converts)"
SECTIONS = (
    "stayfixed",
    "project",
    "paths",
    "memory",
    "budgets",
    "ledger",
    "artifacts",
    "ci",
    "gates",
    "commit_messages",
)
# The machine owner's tables, which a repository's `stayfixed.toml` cannot set: refused outright
# by `loads` as unknown sections, and refused key by key by `classes.resolve` under NOTE.
MACHINE_ONLY_SECTIONS = ("personal", "guards", "setup")
PRESET_KEY = "stayfixed.preset"
# What the NOTE path says. A name is printed through `printed.clipped`, since a TOML key is any
# quoted text; `reason` is the refusal `loads` would have raised, which names its key. The one
# such refusal that quotes a value the document wrote is `contained()`'s, through `repr`, for a
# `[paths]` value `validate_paths` has already held to `grammar.PATH_VALUE`: ASCII letters,
# digits, `.`, `_` and `-` in `/`-separated segments.
UNKNOWN_NOTE = "{name} is not a setting this stayfixed reads; it is ignored"
RESET_NOTE = "{key} is left out ({reason}); the preset's value applies"
# `UnusableKey`'s two sentences, in the same words as the notes: a key removed that has no
# default, and a key whose preset value fails too. `reason` is again the refusal `loads` would
# have raised for that key.
UNUSABLE_REQUIRED = "{key} is left out ({reason}), and it has no default to fall back to"
UNUSABLE_PRESET = (
    "{key} falls back to the preset's value, which does not hold in this repository either "
    "({reason})"
)
# Every refusal below names its key and quotes no value from the document. A state is a member
# of `STATES`, a count is a count, and the names a refusal lists are stayfixed's own tuple or
# configured names that have already matched `PROJECT_NAME`.
GATES_BUILTIN_UNKNOWN = (
    "[gates] builtin names {count} gate(s) stayfixed does not have; the built-in gates are {known}"
)
GATES_BUILTIN_TWICE = "[gates] builtin names a gate twice"
GATES_CUSTOM_NAME = (
    "[gates] custom names {count} gate(s) stayfixed cannot run under that name: a custom gate's "
    "name is {rule}, and neither a built-in gate's name nor `config`"
)
GATES_CUSTOM_TABLE = "[gates.custom.{name}] must be a table"
GATES_CUSTOM_EMPTY = "gates.custom.{name}.run must name a command"
GATES_CUSTOM_NUL = "gates.custom.{name}.run holds a NUL character, which no argv can carry"
GATES_UNKNOWN = (
    "[stayfixed] enforced names {count} gate(s) this project does not run; the gates it runs are "
    "{known}"
)
GATES_TWICE = "[stayfixed] enforced names a gate twice"
# The key every refusal of `[stayfixed] enforced` is about: left out, the project enforces what
# its state alone says.
ENFORCED = "stayfixed.enforced"
GATES_EARLY = (
    "[stayfixed] state is initialised and enforced lists {count} gate(s), but an initialised "
    "project enforces nothing: promoting a gate is what moves a project to adopting"
)
GATES_PARTIAL = (
    "[stayfixed] state is installed and enforced lists {count} of the project's {total} gate(s), "
    "but installed means every gate enforces: list every gate, or none"
)


T = TypeVar("T")

# A named cap: every integer a configuration key holds is below it. `tomllib` converts a hex,
# octal or binary literal of any length (a power-of-two base is exempt from the interpreter's
# 4,300-digit limit), and a decimal of 401 digits is inside that limit, so a key checked only for
# `<= 0` handed its reader a number no `str` could print or no `float` could hold: `[gates]
# custom_timeout_seconds` ended `assess` and `gate` in an internal error. 2**31 is what a signed
# 32-bit count holds, far above any budget, cap or timeout a project writes (the preset's largest
# integer is `memory_index_bytes = 25600`), and below what every reader of one handles: `str`,
# `float`, a comparison. No shipped file states it.
INTEGER_LIMIT = 2**31


class Unknown(StrEnum):
    """What a reader does with a name it does not know or a value it cannot use.

    `REFUSE` is every CLI command's: a file somebody is about to act on is refused whole, naming
    the key. `NOTE` is for a reader that must go on — a session, `doctor` — and reads the file it
    can, ignoring the name, resetting the value to the preset's, and saying so in a note.
    """

    REFUSE = "refuse"
    NOTE = "note"


class ConfigError(Failure):
    """A stayfixed.toml that cannot be trusted as written.

    `key` is the dotted key a refusal of one key is about — `memory.mode`, `paths.bugs`, a
    section's name for a section that is not a table, `gates.custom.<name>` for a custom gate
    that cannot run — and `None` for a refusal of the whole document. It is what the NOTE path
    removes before it tries again (`loads_noting`); it is never printed, so it may be any text
    the document chose.
    """

    def __init__(self, message: str, *, key: str | None = None) -> None:
        super().__init__(message)
        self.key = key


class MissingKeys(ConfigError):
    """A section without a key that has no default: a refusal of the whole document, so `key`
    is `None`. `missing` is every such key, dotted, for the NOTE path to tell a key the document
    never wrote from one it removed itself (`loads_noting`); never printed."""

    def __init__(self, message: str, *, missing: tuple[str, ...]) -> None:
        super().__init__(message)
        self.missing = missing


class UnusableKey(ConfigError):
    """A key the NOTE path could not stand anything in for: a required key it removed, which has
    no default, or a key whose preset value does not hold in this repository either.

    A reader that must go on cannot keep the project's configuration without it, so it drops the
    configuration whole, naming `key`, rather than relaying the refusal the next attempt would
    have raised: that one said a key the document holds was missing, or named the preset's value
    as the fault. `notes` are what the load had noted before it stopped. Raised only by
    `loads_noting`; `loads` refuses as it always has.
    """

    def __init__(self, message: str, *, key: str, notes: tuple[str, ...]) -> None:
        super().__init__(message, key=key)
        self.notes = notes


# Fixed text and a path stayfixed chose or the owner typed. Not the decoder's message: it is only
# a byte and an offset, but the one sentence says what to do about every such file.
NOT_UTF8 = "{path} is not UTF-8 text; stayfixed reads it only as UTF-8"
# What the error says, in `fsops.said`'s words, and not its message, which repeats the path and
# adds nothing to act on; never its class's name, which for a reader's own refusal is a name of
# stayfixed's internals (`fsops.TooLarge`, `fsops.NotRegularFile`) and names no condition.
UNREADABLE = "{path} cannot be read ({error})"
NOT_THERE = "{path} does not exist; run `stayfixed init` first"


class MachineConfigError(ConfigError):
    """The **machine** file could not be read, which is not `stayfixed.toml`'s doing.

    A subclass and not a message, because the one caller that has to tell them apart must not
    do it by reading the text: `doctor` deliberately never quotes a loader message — the loader
    builds it out of the file's own keys and values — so its only way to say which of the two
    files is broken is the type. Without it, a `~/.config/stayfixed/config.toml` with a stray
    bracket in it would read as `stayfixed.toml is here and does not load`, sending the owner to
    edit a file with nothing wrong with it.
    """


def toml_position(exc: tomllib.TOMLDecodeError | RecursionError | ValueError) -> str:
    """The `(at line N, column M)` suffix `tomllib` appends, with its message text dropped.

    One extractor for every caller in this package that reports a document it did not write,
    so that "what may print out of a parse failure" is one decision rather than one per site.
    See `_TOML_POSITION` for which of `tomllib`'s own messages embed the source and why that
    makes the whole exception unprintable.

    A suffix this cannot find is reported as absent rather than as the message: a `tomllib` that
    stopped appending a position would otherwise take this guard with it silently, which is the
    shape every other bounded value in this file refuses. A document nested past the parser's
    recursion has no position, and says so; so does one holding a number past the conversion
    limit, whose own message would tell the reader to raise a process-wide limit rather than fix a
    file somebody else wrote.
    """
    if isinstance(exc, RecursionError):
        return TOO_DEEP
    if not isinstance(exc, tomllib.TOMLDecodeError):
        return TOO_LONG
    found = _TOML_POSITION.search(str(exc))
    return found.group(0) if found is not None else NO_POSITION


def read_machine_toml(path: Path) -> dict[str, Any] | None:
    """The machine file at `path` as `tomllib` parses it, or `None` when no file is there.

    One reader for every reader of the file — `[personal]` here, `[overlay] root` in
    `config.overlay` — so a file that cannot be read, is not UTF-8 or is not TOML is one failure
    in one set of words: `MachineConfigError`, the type `doctor` tells it from a broken
    `stayfixed.toml` by, naming the error's class or the parser's position and never the parser's
    message, which quotes the file's own text. An absent file is the ordinary state before
    `stayfixed setup` has run, and each caller says what it means.
    """
    if not fsops.is_file(path):
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raise MachineConfigError(NOT_UTF8.format(path=path)) from None
    except OSError as exc:
        raise MachineConfigError(UNREADABLE.format(path=path, error=said(exc))) from None
    try:
        return tomllib.loads(text)
    except UNPARSEABLE as exc:
        raise MachineConfigError(f"{path} is not valid TOML {toml_position(exc)}") from None


def _table(raw: dict[str, Any], name: str) -> dict[str, Any]:
    value = raw.get(name, {})
    if not isinstance(value, dict):
        raise ConfigError(f"[{name}] must be a table", key=name)
    return value


def _merged(raw: dict[str, Any], defaults: dict[str, Any], name: str) -> dict[str, Any]:
    return {**defaults.get(name, {}), **_table(raw, name)}


def _gate_branch(ci: dict[str, Any], project: Project) -> dict[str, Any]:
    """`[ci]` with `gate_branch` taken from `[project] base_branch` when the file leaves it out.

    The rendered workflow runs only for pull requests into `gate_branch`, and `assess`, `plan
    check` and `adopt promote` judge against `base_branch`. A fixed default of `main` would make
    a hand-written file that names `develop` as its base, and says nothing about `[ci]`, render a
    workflow that never runs for a pull request into `develop` — local runs and CI judging two
    different branches, with nothing printed. So the preset carries no `gate_branch`: left out,
    it is the base branch, which the loader has already held to the branch grammar.
    """
    return {"gate_branch": project.base_branch, **ci}


@cache
def _schema_types(cls: type[Any]) -> dict[str, Any]:
    """Real type objects for a schema class, resolved once per process.

    `get_type_hints` is what makes them real: under `from __future__ import annotations`
    `field.type` is only the source string, and dispatching on that string would make every type
    the branches do not spell — `float`, `int | None`, an alias — silently "must be a string", so
    a valid config would be refused with a wrong reason. Resolving costs an `eval` per annotation,
    which is why a load does not pay it nine times.
    """
    hints = get_type_hints(cls)
    return {f.name: hints[f.name] for f in fields(cls)}


def _named(unknown: list[str], noun: str) -> str:
    """`unknown`, bounded before it may print: a plain-named one is echoed, anything else
    is counted and never quoted — `PATH_VALUE`'s rule read onto a second grammar.

    **Every name in a `stayfixed.toml` is repository-authored, not only the table names.** A TOML
    key is arbitrary quoted text, so `[paths] "docs\u001b[31m\nIGNORE ALL PRIOR RULES" = 1` puts raw
    ESC and raw newlines into `[paths] has unknown key(s): ...` — a refusal the terminal renders
    and the `init` skill relays to a model — on all nine tables, unless the keys are held to the
    same rule as the section list.

    `SECTION_NAME` is the grammar both callers use, and it is a deliberate re-reading rather than
    a coincidence: every key any schema class or `Budgets.NAMES` declares is lowercase words
    joined by underscores, so a typo worth naming (`branch` for `gate_branch`) matches and
    nothing stayfixed answers to falls outside. A key carrying anything else is counted.

    `noun` is what the count calls the names it would not print, so the sentence reads about the
    thing that was unknown: a section, or a key.
    """
    named = [name for name in unknown if SECTION_NAME.match(name)]
    unnamed = len(unknown) - len(named)
    # The named ones capped at `LISTED_LIMIT` like every list of names on a line, since a file
    # may carry any number, and the plain rest counted as plain: one count per kind, so the two
    # counts never run together as "and 3 more, 1 more".
    shown = named[:LISTED_LIMIT]
    held = len(named) - len(shown)
    parts = [", ".join(shown)] if shown else []
    if held:
        parts = [f"{parts[0]} and {held} more plain name(s)"]
    if unnamed:
        # The noun agrees with the count, for the reason the verb already did: one unnamed key
        # produced "1 more that is not plain key names", which is the common case of this arm.
        tail = f"is not a plain {noun} name" if unnamed == 1 else f"are not plain {noun} names"
        # "more" only when something was named: with every name failing the grammar the message
        # read "unknown section(s): 3 more that are not plain section names" — more than nothing.
        more = "more " if named else ""
        parts.append(f"{unnamed} {more}that {tail}")
    return ("; " if held else ", ").join(parts)


def _build(cls: type[T], name: str, values: dict[str, Any]) -> T:
    known = _schema_types(cast(Any, cls))
    unknown = sorted(set(values) - set(known))
    if unknown:
        raise ConfigError(
            f"[{name}] has unknown key(s): {_named(unknown, 'key')}", key=f"{name}.{unknown[0]}"
        )
    # A field with a default is filled by the section's own reader after `_build` (`Gates.custom`
    # is the one), so only a field without one is required of the merged table.
    required = {
        f.name
        for f in fields(cast(Any, cls))
        if f.default is MISSING and f.default_factory is MISSING
    }
    missing = sorted(required - set(values))
    if missing:
        raise MissingKeys(
            f"[{name}] is missing required key(s): {', '.join(missing)}",
            missing=tuple(f"{name}.{key}" for key in missing),
        )
    coerced: dict[str, Any] = {}
    for key, value in values.items():
        annotation = known[key]
        if get_origin(annotation) is tuple:
            if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
                raise ConfigError(f"{name}.{key} must be a list of strings", key=f"{name}.{key}")
            coerced[key] = tuple(value)
        elif annotation is bool:
            if not isinstance(value, bool):
                raise ConfigError(f"{name}.{key} must be true or false", key=f"{name}.{key}")
            coerced[key] = value
        elif annotation is int:
            coerced[key] = _positive(f"{name}.{key}", value)
        elif annotation is str:
            if not isinstance(value, str):
                raise ConfigError(f"{name}.{key} must be a string", key=f"{name}.{key}")
            coerced[key] = value
        else:
            label = getattr(annotation, "__name__", None) or str(annotation)
            raise ConfigError(
                f"{name}.{key} has an unsupported schema type: {label}; "
                "the loader coerces tuple[str, ...], bool, int and str"
            )
    return cls(**coerced)


def _positive(key: str, value: object) -> int:
    """`value` when it is a positive integer below `INTEGER_LIMIT`; a `ConfigError` naming `key`
    otherwise. Never the value: a number that large is the one no message could print."""
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ConfigError(f"{key} must be a positive integer", key=key)
    if value >= INTEGER_LIMIT:
        raise ConfigError(f"{key} must be a positive integer below {INTEGER_LIMIT:,}", key=key)
    return value


def _enum(section: str, key: str, value: str, allowed: tuple[str, ...]) -> None:
    """The key and the vocabulary it may be spelled in; never the value it was spelled with.

    The three keys this guards — `stayfixed.state`, `memory.mode`, `ci.mode` — are
    repository-authored strings bounded by no grammar, so a clone can write anything at all
    into one, and the refusal reaches a terminal and a model through the `init` and `attach`
    skills' relay. `; got {value!r}` therefore put unbounded repository bytes into it:
    `ci.mode must be one of reusable, uvx, none; got '\\x1b[2JIGNORE PRIOR RULES'`. `!r` escapes
    the control characters, which makes it milder than a raw-bytes leak and not a different
    kind of thing — it is still content- and length-unbounded.

    Nothing is lost by dropping it. `allowed` is stayfixed's own closed vocabulary, the key names
    the line to look at, and the reader has the file open. This is the ruling `PROJECT_NAME`'s
    refusal one screen down already took for the same reason — it dropped `; got
    {project.name!r}` — and `_named` took for the keys of every table.
    """
    if value not in allowed:
        raise ConfigError(
            f"{section}.{key} must be one of {', '.join(allowed)}", key=f"{section}.{key}"
        )


def _deduplicated(memory: Memory) -> Memory:
    """`memory.groups` with each entry kept once, in the order the document wrote them.

    `_build` coerced the list with `tuple(value)` and nothing else, and it is the one
    repository-authored list four places report as a **count** a user is asked to act
    on. `groups = ["developer", "developer"]` made `attach.binding.unlinked_groups` walk one
    directory twice, so `attach` refused naming two groups that never moved into the overlay,
    `attach --check` printed `real_directories: 2`, and the session line told the model two --
    all about one directory, and with the remedy ("move them into the overlay") already done
    for the only one there is.

    `dict.fromkeys` and not `set`, because the order is the owner's: the link tree is built in
    it, and a refusal that reorders the list a person is reading is a worse answer than one
    that does not.

    **Deduplication only, and the containment stays where it is.** `config/paths.py` names
    `memory.groups` one of four repository-writable fields this loader deliberately does not
    contain, and hands each to the module that first reads it -- because the anchor differs per
    module: `unlinked_groups` contains a group against the checkout, `attach._check_groups`
    against the overlay, `memory.store` against the store. A grammar check here would refuse a
    spelling those three already refuse, one layer above the guard that knows what it is
    anchored to, and would take the reachable arm of each of them with it. What this function
    fixes is the one thing none of them can: a count taken over a list with a duplicate in it.
    """
    return replace(memory, groups=tuple(dict.fromkeys(memory.groups)))


def _gates(raw: dict[str, Any], defaults: dict[str, Any]) -> Gates:
    """`[gates]`: which built-in gates run, and the project's own.

    A custom gate's name is a TOML key, which is arbitrary quoted text, so a name is counted
    and never quoted until it has matched `PROJECT_NAME`; after that it is printable, and every
    later refusal names it. `run` is never printed at all. The two argvs `subprocess` cannot run,
    an empty one and one carrying a NUL, are refused here rather than raised as an internal
    error by whatever runs the gate.
    """
    values = _merged(raw, defaults, "gates")
    tables = values.pop("custom", {})
    gates = _build(Gates, "gates", values)
    unknown = [name for name in gates.builtin if name not in BUILTIN_GATES]
    if unknown:
        known = ", ".join(BUILTIN_GATES)
        raise ConfigError(
            GATES_BUILTIN_UNKNOWN.format(count=len(unknown), known=known), key="gates.builtin"
        )
    if len(set(gates.builtin)) != len(gates.builtin):
        raise ConfigError(GATES_BUILTIN_TWICE, key="gates.builtin")
    if not isinstance(tables, dict):
        raise ConfigError("[gates.custom] must be a table", key="gates.custom")
    reserved = (*BUILTIN_GATES, CONFIG_CHECK)
    unusable = [name for name in tables if not PROJECT_NAME.match(name) or name in reserved]
    if unusable:
        # The key of the first unusable gate, which the NOTE path drops before it asks again; a
        # second unusable one is the next attempt's refusal.
        first = f"gates.custom.{unusable[0]}"
        raise ConfigError(GATES_CUSTOM_NAME.format(count=len(unusable), rule=NAME_RULE), key=first)
    custom: dict[str, CustomGate] = {}
    for name, table in sorted(tables.items()):
        # A custom gate has no preset value to fall back to, so every refusal of one is keyed to
        # the gate itself: the NOTE path leaves the gate out rather than one of its keys.
        gate_key = f"gates.custom.{name}"
        if not isinstance(table, dict):
            raise ConfigError(GATES_CUSTOM_TABLE.format(name=name), key=gate_key)
        try:
            gate = _build(CustomGate, gate_key, table)
        except ConfigError as exc:
            raise ConfigError(str(exc), key=gate_key) from None
        if not gate.run:
            raise ConfigError(GATES_CUSTOM_EMPTY.format(name=name), key=gate_key)
        if any("\0" in part for part in gate.run):
            raise ConfigError(GATES_CUSTOM_NUL.format(name=name), key=gate_key)
        custom[name] = gate
    return replace(gates, custom=custom)


def _enforcement(config: Config) -> Config:
    """`[stayfixed] enforced` held to the gates this project runs, and `installed` made explicit.

    `state` is the lifecycle and `enforced` what was promoted while adopting, so the two state
    one fact and this refuses the ways they can contradict each other. The list holds configured
    gate names, once each, only once the project is past `initialised`, and under `installed`
    either every gate or none. An entry outside the configured set is counted and never quoted:
    it is exactly the value no grammar has bounded. The names the refusal lists are the
    configured ones, each already held to a grammar.

    Under `installed` the loaded list becomes every configured gate, so `stayfixed.enforcing` is
    the list and nothing else, and a gate added to an installed project enforces from the run
    that adds it — for a custom gate under `stayfixed gate`, from the first run after it lands on
    the base, since that command runs none before.
    """
    stayfixed = config.stayfixed
    names = config.gate_names
    unknown = [name for name in stayfixed.enforced if name not in names]
    if unknown:
        # Capped: custom gates are the repository's to add, so the list is bounded by nothing.
        known = listed(list(names)) or "none"
        raise ConfigError(GATES_UNKNOWN.format(count=len(unknown), known=known), key=ENFORCED)
    if len(set(stayfixed.enforced)) != len(stayfixed.enforced):
        raise ConfigError(GATES_TWICE, key=ENFORCED)
    if stayfixed.state == "initialised" and stayfixed.enforced:
        raise ConfigError(GATES_EARLY.format(count=len(stayfixed.enforced)), key=ENFORCED)
    if stayfixed.state != "installed":
        return config
    if stayfixed.enforced and set(stayfixed.enforced) != set(names):
        total = len(names)
        raise ConfigError(
            GATES_PARTIAL.format(count=len(stayfixed.enforced), total=total), key=ENFORCED
        )
    return replace(config, stayfixed=replace(stayfixed, enforced=names))


def _budgets(raw: dict[str, Any], preset: dict[str, Any], owner: Owner | None) -> Budgets:
    configured = _table(raw, "budgets")
    unknown = sorted(set(configured) - set(Budgets.NAMES))
    if unknown:
        raise ConfigError(
            f"[budgets] has unknown key(s): {_named(unknown, 'key')}", key=f"budgets.{unknown[0]}"
        )
    for key, value in configured.items():
        _positive(f"budgets.{key}", value)
    # The owner's session budgets, which `config.owner` admitted only for the session's names,
    # are configured values that win over the document's.
    session = {} if owner is None else owner.session_budgets
    return Budgets(preset=dict(preset["budgets"]), configured={**configured, **session})


def _personal(machine: Path | None, preset: dict[str, Any]) -> Personal:
    values: dict[str, Any] = dict(preset.get("defaults", {}).get("personal", {}))
    # `None` is a machine with no home to hold the file (`machine_config_path`), read as no file.
    raw = None if machine is None else read_machine_toml(machine)
    if raw is None:
        # No machine file, so `values` is the preset's own `[personal]` defaults and nothing
        # else. A fault here would be the preset's, not a machine's, and must not be relabelled.
        return _build(Personal, "personal", values)
    try:
        values.update(_table(raw, "personal"))
        return _build(Personal, "personal", values)
    except ConfigError as exc:
        # Everything from here is this file's doing: what `values` gained between the arm above
        # and this one is exactly its `[personal]` table.
        raise MachineConfigError(f"{machine}: {exc}") from None


def load(root: Path, *, machine: Path | None = None) -> Config:
    """Read `stayfixed.toml` under the preset, and `[personal]` out of the machine file.

    With no `machine`, the machine file is `config.machine.machine_config_path`'s, the one file
    the overlay root's reader and `trust._trust_file` read too, which no variable moves: an
    interactive run with `XDG_CONFIG_HOME` set once read `[personal]` from the file it named and
    `[overlay] root` and `trust.json` from `~/.config/stayfixed/`, so an owner who wrote one file
    with both tables got `[personal]` honoured and the overlay silently unrecorded. `--machine`
    is the supported way to name another file, honoured by all three readers, because it is a
    path a person typed rather than one an environment chose.

    **One reader of the file.** Through `read_document`, which goes through `contained()`: a
    `stayfixed.toml` that is a symlink is refused by every command, as `stayfixed gate` refuses
    it. Read with a plain `read_text`, a clone's link to `/dev/zero` would keep `adopt`, `bugs
    check` and `plan check` reading until the machine ran out of memory.
    """
    text = read_document(root)
    if text is None:
        raise ConfigError(NOT_THERE.format(path=root / CONFIG_FILE))
    return loads(text, root, machine=machine)


def read_document(root: Path) -> str | None:
    """`stayfixed.toml` exactly as it is on disk, or `None` when there is none.

    `newline=""` and not `read_text`: this is the text a command hands to `config.owned.rewrite`,
    which keeps every byte but the values it sets, and universal-newline translation would have
    rewritten every CRLF in a file somebody else owns before the editor saw it. `contained`
    first, as for every configured path, so a symlinked `stayfixed.toml` is a refusal; then read
    to the read cap, a regular file only (`fsops.read_regular_text`), as every reader of a
    committed file reads one.
    """
    try:
        return read_regular_text(contained(root, CONFIG_FILE), newline="")
    except FileNotFoundError:
        return None
    except UnicodeDecodeError:
        raise ConfigError(NOT_UTF8.format(path=CONFIG_FILE)) from None
    except OSError as exc:
        raise ConfigError(UNREADABLE.format(path=CONFIG_FILE, error=said(exc))) from None


def loads(
    text: str,
    root: Path,
    *,
    machine: Path | None = None,
    label: str | None = None,
    personal: Personal | None = None,
    owner: Owner | None = None,
) -> Config:
    """Build a `Config` from `text` as `stayfixed.toml`'s contents, without reading a file.

    `load` is "read the file, then `loads`"; `init --yes` needs a `Config` for a document it
    has not written to disk yet, so the parse-and-validate half is this function on its own.
    `label` is what a refusal calls the document when it is not the file at `root`: the base's
    copy `stayfixed gate` reads out of git is validated against the tree's disk, and a refusal
    naming `<root>/stayfixed.toml` would send its owner to a file with nothing wrong in it.
    `personal` is the `[personal]` a load earlier in the same command already read, taken in
    place of reading the machine file again: a caller that holds a `Config` and not the path
    its machine file came from — a gate, handed `(root, config, base)` — loads a second
    document with it, and so reads no machine file but the one the command was given. Given
    both, `personal` wins and `machine` is never read. `owner` is the machine owner's layer
    (`config.owner.resolve_owner`), read once by the caller: its `personal` stands in for the
    machine file's, as `personal` does, and its session budgets are folded into `[budgets]` as
    configured values that win over the document's. Every argument after `root` is
    keyword-only.
    """
    path = label or root / CONFIG_FILE
    raw = _parsed(text, path)
    unknown = sorted(set(raw) - set(SECTIONS))
    if unknown:
        raise ConfigError(f"{path} has unknown section(s): {_named(unknown, 'section')}")
    return _built(raw, root, machine=machine, personal=personal, owner=owner)


def _parsed(text: str, path: Path | str) -> dict[str, Any]:
    """`text` as TOML, or a refusal of the whole document naming only where the parser stopped."""
    try:
        return tomllib.loads(text)
    except UNPARSEABLE as exc:
        raise ConfigError(f"{path} is not valid TOML {toml_position(exc)}") from None


def _preset(name: object) -> dict[str, Any]:
    """The preset `[stayfixed] preset` names, or a refusal keyed to `stayfixed.preset`.

    `load_preset` holds the name to `shipped_presets()` before it reads anything, and refuses
    with a plain `Failure` carrying no key, which the NOTE path could only propagate: a
    `stayfixed.toml` naming a preset a later release ships would cost a session the whole file.
    So its refusal, and nothing it read, is re-raised keyed. The words are still the preset
    loader's, which never quote the name.
    """
    if not isinstance(name, str):
        raise ConfigError(f"stayfixed.preset must be a string; {available()}", key=PRESET_KEY)
    try:
        return load_preset(name)
    except Failure as exc:
        raise ConfigError(str(exc), key=PRESET_KEY) from None


def _built(
    raw: dict[str, Any],
    root: Path,
    *,
    machine: Path | None,
    personal: Personal | None,
    owner: Owner | None,
) -> Config:
    """The `Config` a parsed document holds, every section read and held under the preset."""
    head = _table(raw, "stayfixed")
    # Asked before anything spells it: a hex literal of any length converts, and its `str`
    # raises past 4,300 digits.
    preset_name = head.get("preset", "recommended")
    preset = _preset(preset_name)
    defaults = dict(preset.get("defaults", {}))
    defaults["stayfixed"] = {**defaults.get("stayfixed", {}), "preset": preset_name}

    stayfixed = _build(Stayfixed, "stayfixed", _merged(raw, defaults, "stayfixed"))
    _enum("stayfixed", "state", stayfixed.state, STATES)
    project = _build(Project, "project", _merged(raw, defaults, "project"))
    if not PROJECT_NAME.match(project.name):
        raise ConfigError(f"project.name must be {NAME_RULE}", key="project.name")
    for key in ("base_branch", "release_branch"):
        # Named, never quoted: the value becomes a git ref and reaches output lines, and it is
        # the text the grammar refused. The grammar is the one the rendered workflow holds
        # `[ci] gate_branch` to; git could not have such a branch anyway.
        if not BRANCH_NAME.match(getattr(project, key)):
            raise ConfigError(
                f"project.{key} is not a plain branch name: {BRANCH_RULE}", key=f"project.{key}"
            )
    paths = _build(Paths, "paths", _merged(raw, defaults, "paths"))
    memory = _deduplicated(_build(Memory, "memory", _merged(raw, defaults, "memory")))
    _enum("memory", "mode", memory.mode, MEMORY_MODES)
    ledger = _build(Ledger, "ledger", _merged(raw, defaults, "ledger"))
    artifacts = _build(Artifacts, "artifacts", _merged(raw, defaults, "artifacts"))
    ci = _build(Ci, "ci", _gate_branch(_merged(raw, defaults, "ci"), project))
    _enum("ci", "mode", ci.mode, CI_MODES)
    gates = _gates(raw, defaults)
    commit_messages = _build(
        CommitMessages, "commit_messages", _merged(raw, defaults, "commit_messages")
    )
    caps = _build(NativeCaps, "native_caps", dict(preset["native_caps"]))
    if personal is None and owner is not None:
        personal = owner.personal
    if personal is None:
        personal = _personal(machine or machine_config_path(), preset)
    config = Config(
        stayfixed=stayfixed,
        project=project,
        paths=paths,
        memory=memory,
        budgets=_budgets(raw, preset, owner),
        native_caps=caps,
        ledger=ledger,
        artifacts=artifacts,
        ci=ci,
        gates=gates,
        commit_messages=commit_messages,
        personal=personal,
    )
    config = _enforcement(config)
    validate_paths(config, root)
    return config


@dataclass(frozen=True)
class Noted:
    """What `loads_noting` read, a note for every name it ignored or value it reset, and the
    dotted key each note is about, in the same order. A key is any text the document chose: a
    reader prints one through `stayfixed.printed`."""

    config: Config
    notes: tuple[str, ...]
    keys: tuple[str, ...] = ()


def loads_noting(text: str, root: Path, *, owner: Owner, label: str | None = None) -> Noted:
    """`loads` under `Unknown.NOTE`: read what the document holds that this stayfixed can use.

    For a reader that must go on, a session above all, where one name a newer release added or
    one value nobody can use would otherwise cost every setting the project made. An unknown
    section or key is removed with `UNKNOWN_NOTE`; the repository's `[personal]`, `[guards]` and
    `[setup]` go through `classes.resolve`, which refuses the repository layer for every key in
    them, and are removed with its note. Then the document is built as `loads` builds it, and a
    refusal carrying a `key` — a `ConfigError`, or `validate_paths`' `PathEscape` — removes that
    key, so the preset's value applies, with `RESET_NOTE`, and the build is tried again. Each
    retry removes one key the document holds, so the attempts are bounded by the keys it holds.

    A refusal with no key is the whole document's and propagates, as a document that is not TOML
    does, except where nothing can stand in for a key: a required key the retry removed, which
    has no default, or a key whose value now comes from the preset and is refused all the same —
    the preset's own `[paths]` value through a symlink the repository committed. Then the load
    raises `UnusableKey`, naming that key and carrying the notes so far, never the refusal the
    attempt raised, which said a key the document holds was missing or blamed the preset. The
    owner's layer is folded in as `loads` folds it.
    """
    raw = _parsed(text, label or root / CONFIG_FILE)
    notes: list[str] = []
    keys: list[str] = []
    document = _known_only(raw, notes, keys)
    attempts = _held(document)
    # Why each removed key was removed, the reason `UnusableKey` gives for one that is needed,
    # and its reset note, which `UnusableKey` leaves out: no preset value applied after all.
    removed: dict[str, tuple[str, str]] = {}

    def unusable(message: str, key: str) -> UnusableKey:
        dropped = removed[key][1] if key in removed else None
        return UnusableKey(message, key=key, notes=tuple(n for n in notes if n != dropped))

    while True:
        try:
            config = _built(document, root, machine=None, personal=None, owner=owner)
        except MissingKeys as exc:
            lost = [key for key in exc.missing if key in removed]
            if not lost:
                raise
            reason = removed[lost[0]][0]
            message = UNUSABLE_REQUIRED.format(key=clipped(lost[0]), reason=reason)
            raise unusable(message, lost[0]) from None
        except (ConfigError, PathEscape) as exc:
            if exc.key is None or attempts == 0:
                raise
            if not _removed(document, exc.key):
                message = UNUSABLE_PRESET.format(key=clipped(exc.key), reason=exc)
                raise unusable(message, exc.key) from None
            attempts -= 1
            note = RESET_NOTE.format(key=clipped(exc.key), reason=exc)
            removed[exc.key] = (str(exc), note)
            notes.append(note)
            keys.append(exc.key)
            continue
        return Noted(config, tuple(notes), tuple(keys))


_SCHEMA_OF: dict[str, type[Any]] = {
    "stayfixed": Stayfixed,
    "project": Project,
    "paths": Paths,
    "memory": Memory,
    "ledger": Ledger,
    "artifacts": Artifacts,
    "ci": Ci,
    "gates": Gates,
    "commit_messages": CommitMessages,
}


def _keys_of(section: str) -> Collection[str]:
    """The keys this stayfixed reads in `section`: `Budgets.NAMES`, or the schema class's fields."""
    if section == "budgets":
        return Budgets.NAMES
    return _schema_types(cast(Any, _SCHEMA_OF[section])).keys()


def _known_only(raw: dict[str, Any], notes: list[str], keys: list[str]) -> dict[str, Any]:
    """`raw` without the names this stayfixed does not read, noting each one it removed and
    recording the key each note is about."""
    document: dict[str, Any] = {}
    machine_only: dict[str, object] = {}
    for name, value in raw.items():
        if name in MACHINE_ONLY_SECTIONS:
            if isinstance(value, dict) and value:
                machine_only.update({f"{name}.{key}": item for key, item in value.items()})
            else:
                notes.append(REFUSED_LAYER_NOTE.format(key=name, layer=LayerName.REPOSITORY))
                keys.append(name)
        elif name not in SECTIONS:
            notes.append(UNKNOWN_NOTE.format(name=clipped(name)))
            keys.append(name)
        elif isinstance(value, dict):
            document[name] = _known_keys(name, value, _keys_of(name), notes, keys)
        else:
            # Not a table: the section's own reader refuses it, keyed to the section.
            document[name] = value
    notes.extend(resolve([Layer(LayerName.REPOSITORY, machine_only)]).notes)
    # One note per key above: no machine-only key's class admits the repository layer.
    keys.extend(machine_only)
    return document


def _known_keys(
    dotted: str, table: dict[str, Any], known: Collection[str], notes: list[str], keys: list[str]
) -> dict[str, Any]:
    kept: dict[str, Any] = {}
    for key, value in table.items():
        if key not in known:
            notes.append(UNKNOWN_NOTE.format(name=clipped(f"{dotted}.{key}")))
            keys.append(f"{dotted}.{key}")
        elif dotted == "gates" and key == "custom" and isinstance(value, dict):
            fields_of_gate = _schema_types(CustomGate).keys()
            kept[key] = {
                name: _known_keys(f"gates.custom.{name}", gate, fields_of_gate, notes, keys)
                if isinstance(gate, dict)
                else gate
                for name, gate in value.items()
            }
        else:
            kept[key] = value
    return kept


def _held(table: dict[str, Any]) -> int:
    """How many keys `table` holds, at every depth: the most a NOTE load can remove."""
    return sum(1 + (_held(value) if isinstance(value, dict) else 0) for value in table.values())


def _removed(table: dict[str, Any], dotted: str) -> bool:
    """Remove the key `dotted` names from `table`; `False` when `table` holds no such key.

    A name may itself hold a dot (a custom gate's name may), so each level is asked for the
    whole remaining name first and then for every table whose name prefixes it.
    """
    if dotted in table:
        del table[dotted]
        return True
    return any(
        isinstance(value, dict)
        and dotted.startswith(f"{name}.")
        and _removed(value, dotted[len(name) + 1 :])
        for name, value in table.items()
    )


def preset_defaults(project: str, *, preset: str = "recommended") -> Config:
    """A `Config` built from a preset's `[defaults.*]` alone, for a directory that has no
    `stayfixed.toml` and never will.

    The overlay is a repository stayfixed writes into and does not manage: it has no project
    configuration, and the scaffold engine needs one (it reads `stayfixed.profile` and
    `artifacts.local`, and nothing else). `init --yes` will want the same constructor for the
    first write into a project, before the file it would load exists.

    `stayfixed.version` is the one value the preset does not carry and `_build` requires: the
    engine stamps it into every manifest `Record`, so it comes from `stayfixed.__version__`
    rather than from a default that would record an empty string.

    `validate_paths` is deliberately not called. It is about a project root this caller does
    not have, and the `[paths]` values it would check are the preset's own defaults pointing at
    documents an overlay does not carry.
    """
    raw = load_preset(preset)
    defaults = dict(raw.get("defaults", {}))
    head = {**defaults.get("stayfixed", {}), "preset": preset, "version": __version__}
    project_config = _build(Project, "project", {**defaults.get("project", {}), "name": project})
    return Config(
        stayfixed=_build(Stayfixed, "stayfixed", head),
        project=project_config,
        paths=_build(Paths, "paths", defaults.get("paths", {})),
        memory=_build(Memory, "memory", defaults.get("memory", {})),
        budgets=Budgets(preset=dict(raw.get("budgets", {}))),
        native_caps=_build(NativeCaps, "native_caps", dict(raw.get("native_caps", {}))),
        ledger=_build(Ledger, "ledger", defaults.get("ledger", {})),
        artifacts=_build(Artifacts, "artifacts", defaults.get("artifacts", {})),
        ci=_build(Ci, "ci", _gate_branch(dict(defaults.get("ci", {})), project_config)),
        gates=_gates({}, defaults),
        commit_messages=_build(
            CommitMessages, "commit_messages", defaults.get("commit_messages", {})
        ),
        personal=_build(Personal, "personal", defaults.get("personal", {})),
    )
