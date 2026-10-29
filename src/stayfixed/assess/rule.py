"""The rule that judges a change's `stayfixed.toml` against its base's.

A pull request may tighten what its base branch enforces and may not loosen it, so the base's
configuration is the one that governs the run and the change's own is judged against it. Which
commit the base is, and where in it the base's copy is, are `stayfixed.assess.base`'s.

**What the change may do.** Each side goes through the loader and the rule compares what it
derives, key by dotted key: each budget by its effective value, each custom gate as one key per
field. A comment, a key spelled out at its default and a reordered `enforced` or `[gates] builtin`
are therefore no change. Every changed key gets one verdict, and a key's class (`config.classes`)
is asked first: a preference, the machine owner's key and the plugin's are neutral, because no
gate judges a pull request by them. The change may enforce more gates, by listing them in
`[stayfixed] enforced`; add a gate, and drop or re-command one the base does not enforce; lower a
budget, a gate's or a session's, which the base branch may set above the preset or below it; and
add to `[ledger] code_roots` and `evidence_boundary_required_for`. The preset's name, the
harnesses and the project's name are neutral too, because no gate reads them; every value a preset
switch moves is judged by its own key. The recorded version and the workflow pin move together as
an upgrade: to exactly the running stayfixed, never below the base's by the reader `stayfixed
upgrade` refuses by, and a moved pin only at the commit the platform says is running and a public
release tag names. Any other key is refused while the base enforces any gate, because the rule
cannot know which way a free-form key moves, and noted while it enforces none; routine upkeep
under enforcement lands by a direct push to the base branch.

The run then uses the tree's configuration, or the base's when anything was refused, and
enforces the gates either side enforces: adding the tree's never loosens, and a refusal already
fails the run. A custom gate executes only with the base's own command (`ConfigVerdict.landed`),
so a gate the change adds or re-commands waits until it lands on the base. Key names print;
values never do.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, fields, replace
from enum import StrEnum
from pathlib import Path

# Imported under a private name: `rule` judges what the read returns, and publishes none of it.
from stayfixed.assess.base import read_base as _read_base
from stayfixed.config.classes import KeyClass, class_of
from stayfixed.config.loader import CONFIG_FILE, loads
from stayfixed.config.owner import Owner
from stayfixed.config.schema import Budgets, Config, CustomGate
from stayfixed.errors import Failure, Refusal
from stayfixed.semver import later

# What the loader calls the base's copy, so its reason names the right file: the loader's own
# words would name `<root>/stayfixed.toml`, which is the change's copy.
BASE_COPY = f"the base's {CONFIG_FILE}"
# A refusal the base's own load raised against this tree's disk, such as a symlink the change
# planted on a path only the base's `[paths]` names: still a refusal, and said to be the base's.
# The reason is the loader's own, bounded where it was raised.
BASE_REFUSED = (
    "the base's stayfixed.toml governs this change, and loading it against this tree met a "
    "refusal: {reason}"
)
BASE_DOES_NOT_LOAD = (
    "the base's stayfixed.toml governs this change and does not load, so the change cannot be "
    "judged; fix it on the base branch by a direct push ({reason})"
)


class Verdict(StrEnum):
    TIGHTENED = "tightened"
    NEUTRAL = "neutral"
    UPGRADE = "upgrade"
    REFUSED = "refused"
    NOTED = "noted"


@dataclass(frozen=True)
class Change:
    """One key whose derived value differs between the base and the tree. The key is a schema
    field's dotted path or a custom gate's, whose name the loader holds to a grammar, so it
    prints; the values never do."""

    key: str
    verdict: Verdict


@dataclass(frozen=True)
class ConfigVerdict:
    changes: tuple[Change, ...]  # sorted by key
    config: Config  # the tree's, or the base's when anything was refused
    enforcing: frozenset[str]  # the base's and the tree's
    # The base's own custom gates and enforcing set, which decide which of the run's custom
    # gates execute and in what order; none under the bootstrap.
    base_custom: Mapping[str, CustomGate] = field(default_factory=dict)
    base_enforcing: frozenset[str] = frozenset()
    bootstrap: bool = False  # the base has no copy at this path, so the tree decides

    @property
    def refused(self) -> bool:
        return any(change.verdict is Verdict.REFUSED for change in self.changes)

    @property
    def landed(self) -> frozenset[str]:
        """The run's custom gates whose command is the base's own, and so the ones that execute.

        A gate the change adds or re-commands is a command only the change has vouched for: run
        in the same step as the base's enforced gates, it could rewrite the files they execute
        before they run. It runs once it has landed on the base. Under the bootstrap no gate
        has, and under a refusal the run is the base's configuration, so every gate has.
        """
        custom = self.config.gates.custom
        return frozenset(
            name for name, gate in custom.items() if self.base_custom.get(name) == gate
        )


@dataclass(frozen=True)
class _Sides:
    base: Config
    tree: Config
    running: str  # the stayfixed running this judgement: the one the workflow's pin checked out
    workflow_sha: str | None  # the commit of the reusable workflow the platform says is running
    released: Callable[[str], bool | None]  # whether a public release tag names this commit


Row = Callable[[str, _Sides], Verdict]

# Lists whose order no reader sees: `enforcing` is a set, and `gate_names` orders built-ins itself.
_UNORDERED = frozenset({"stayfixed.enforced", "gates.builtin"})


def _neutral(key: str, sides: _Sides) -> Verdict:
    return Verdict.NEUTRAL


def _other(key: str, sides: _Sides) -> Verdict:
    """A key the rule cannot tell the direction of: refused while the base enforces anything."""
    return Verdict.REFUSED if sides.base.stayfixed.enforcing else Verdict.NOTED


def _enforced(key: str, sides: _Sides) -> Verdict:
    """`enforced`, the one adoption key: every gate the base lists is still listed, and a list
    that names more tightens."""
    before, after = sides.base.stayfixed.enforcing, sides.tree.stayfixed.enforcing
    if not after >= before:
        return Verdict.REFUSED
    return Verdict.TIGHTENED if after > before else Verdict.NEUTRAL


def _builtin_gates(key: str, sides: _Sides) -> Verdict:
    before, after = set(sides.base.gates.builtin), set(sides.tree.gates.builtin)
    if (before - after) & sides.base.stayfixed.enforcing:
        return Verdict.REFUSED
    return Verdict.TIGHTENED if after - before else Verdict.NEUTRAL


def _custom_gate(key: str, sides: _Sides) -> Verdict:
    """A custom gate's field, `gates.custom.<name>.<field>`: a gate the base enforces keeps its
    command, and one it does not may change it or go."""
    name = key.removeprefix("gates.custom.").rpartition(".")[0]
    if name not in sides.base.gates.custom:
        return Verdict.TIGHTENED
    return Verdict.REFUSED if name in sides.base.stayfixed.enforcing else Verdict.NEUTRAL


def _additive(key: str, sides: _Sides) -> Verdict:
    """A list a gate reads more of as it grows: a superset tightens, the same set in another
    order is neutral, and anything else is a key the rule cannot tell the direction of."""
    section, _, name = key.partition(".")
    before = set(getattr(getattr(sides.base, section), name))
    after = set(getattr(getattr(sides.tree, section), name))
    if after > before:
        return Verdict.TIGHTENED
    return Verdict.NEUTRAL if after == before else _other(key, sides)


def _budget(key: str, sides: _Sides) -> Verdict:
    name = key.removeprefix("budgets.")
    lower = sides.tree.budgets.effective(name) <= sides.base.budgets.effective(name)
    return Verdict.TIGHTENED if lower else Verdict.REFUSED


def _upgrade(key: str, sides: _Sides) -> Verdict:
    """`[stayfixed] version` and `[ci] ref` are one upgrade, judged together. "Not below the
    base's" is `later`, the reader `stayfixed upgrade` refuses by, so the two agree. A moved pin
    is admitted only at the commit the platform says is running, and only when a release tag
    names it."""
    old, new, pin = sides.base.stayfixed.version, sides.tree.stayfixed.version, sides.tree.ci.ref
    at_running = new == sides.running
    upward = later(old, new) is False
    vouched = bool(sides.workflow_sha) and pin == sides.workflow_sha
    pinned = pin == sides.base.ci.ref or (vouched and sides.released(pin) is True)
    return Verdict.UPGRADE if at_running and upward and pinned else _other(key, sides)


ROWS: Mapping[str, Row] = {
    "stayfixed.enforced": _enforced,
    "gates.builtin": _builtin_gates,
    "stayfixed.version": _upgrade,
    "ci.ref": _upgrade,
    "ledger.code_roots": _additive,
    "ledger.evidence_boundary_required_for": _additive,
    # The repository's own keys no gate reads. The preset's name is one: each value it moves is
    # judged by its own row.
    "stayfixed.preset": _neutral,
    "stayfixed.agents": _neutral,
    "project.name": _neutral,
}
# Every budget, a gate's and a session's: a session's bounds what a session loads, and a gate
# the base enforces may read it (`stayfixed memory index --check`), so a pull request that raised
# one would loosen the gate that judges it.
PREFIX_ROWS: tuple[tuple[str, Row], ...] = (
    ("budgets.", _budget),
    ("gates.custom.", _custom_gate),
)
# The classes no gate judges a pull request by. `personal.*` and `native_caps.*` reach a `Config`
# from the machine file and the preset, which both sides share, so either moves only with a
# preset switch; a preference is what the repository may choose.
_NEUTRAL_CLASSES = frozenset(
    {
        KeyClass.PREFERENCE,
        KeyClass.MACHINE_ONLY,
        KeyClass.PLUGIN_OWNED,
    }
)


def _class(key: str) -> KeyClass | None:
    """`key`'s class, or `None` for a custom gate's field, which has no row of its own."""
    try:
        return class_of(key)
    except KeyError:
        return None


def _row(key: str) -> Row:
    """The class first, then this rule's own table, then the key the rule cannot read."""
    if _class(key) in _NEUTRAL_CLASSES:
        return _neutral
    if key in ROWS:
        return ROWS[key]
    return next((row for prefix, row in PREFIX_ROWS if key.startswith(prefix)), _other)


def _values(config: Config) -> dict[str, object]:
    """Every value the loader derived, by dotted key: each budget by its effective value, each
    custom gate as one key per field. `native_caps` (the preset's) and `personal` (the machine
    file's) are `Config` fields and not `stayfixed.toml` sections; both sides load under one
    machine file, so either moves only with a preset switch, and is compared like any field, and
    neutral by its class."""
    values: dict[str, object] = {}
    for section in fields(config):
        table = getattr(config, section.name)
        if isinstance(table, Budgets):
            values |= {f"budgets.{name}": table.effective(name) for name in Budgets.NAMES}
            continue
        for item in fields(table):
            key, value = f"{section.name}.{item.name}", getattr(table, item.name)
            if isinstance(value, Mapping):  # `gates.custom`: one key per gate and field
                for name, entry in value.items():
                    values |= {
                        f"{key}.{name}.{f.name}": getattr(entry, f.name) for f in fields(entry)
                    }
            else:
                values[key] = frozenset(value) if key in _UNORDERED else value
    return values


def read_base_gates(
    root: Path, base: str, *, branch: str, machine: Path | None, owner: Owner | None = None
) -> Mapping[str, CustomGate]:
    """The base's custom gates by name, loaded as `judge` loads the base's copy; none when the
    base has no `stayfixed.toml` at the project's path. Raises as `read_base` and the loader do.
    `owner` is the owner's layer the command already resolved (`loads`' own)."""
    text = _read_base(root, base, branch=branch)
    if text is None:
        return {}
    config = loads(text, root, machine=machine, label=BASE_COPY, owner=owner)
    return config.gates.custom


def judge(
    root: Path,
    base_text: str | None,
    tree_text: str,
    *,
    machine: Path | None,
    running: str,
    workflow_sha: str | None,
    released: Callable[[str], bool | None],
    owner: Owner | None = None,
) -> ConfigVerdict:
    """The tree's `stayfixed.toml` judged against the base's, key by derived key.

    Both sides go through the loader against the tree's disk, so what is compared is what a
    command would read: a comment, a key spelled at its default and a reordered list are no
    change. `base_text` is `None` for the bootstrap, where the tree decides. The run uses the
    tree's configuration unless something was refused, then the base's; it enforces what either
    side enforces. `owner` is the owner's layer the command already resolved, which both loads
    take, so the machine file is read once and its notes are said once (`loads`' own).
    """
    tree = loads(tree_text, root, machine=machine, owner=owner)
    if base_text is None:
        return ConfigVerdict((), tree, tree.stayfixed.enforcing, bootstrap=True)
    try:
        base = loads(base_text, root, machine=machine, label=BASE_COPY, owner=owner)
    except Failure as exc:
        # Never the bootstrap: read as "no copy", the change would decide its own configuration.
        # The machine file is not the base's: both sides read it, and the tree's load above has
        # already answered for it. A preset this stayfixed does not ship is the loader's keyed
        # `ConfigError` (`loader._preset`); `Failure` and not `ConfigError` alone, so a plain
        # refusal any load may raise is still named as the base's copy.
        raise Failure(BASE_DOES_NOT_LOAD.format(reason=exc)) from None
    except Refusal as exc:
        # A symlink the change planted on a path only the base's `[paths]` names: the run fails
        # as a refusal, and the message says whose configuration met it, since the tree's own
        # `[paths]` may not name that path at all.
        raise Refusal(BASE_REFUSED.format(reason=exc)) from None
    sides = _Sides(base, tree, running, workflow_sha, released)
    before, after = _values(base), _values(tree)
    changes = tuple(
        Change(key, _row(key)(key, sides))
        for key in sorted(before.keys() | after.keys())
        if before.get(key) != after.get(key)
    )
    enforcing = base.stayfixed.enforcing | tree.stayfixed.enforcing
    verdict = ConfigVerdict(
        changes,
        tree,
        enforcing,
        base_custom=base.gates.custom,
        base_enforcing=base.stayfixed.enforcing,
    )
    return replace(verdict, config=base) if verdict.refused else verdict
