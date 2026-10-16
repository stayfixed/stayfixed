"""No gate reads a key the tighten-only rule calls `neutral`.

The rule lets a pull request change every key of a class no gate judges by — a preference, a
session's parameter, the machine owner's keys and the plugin's — and the repository's own
`stayfixed.preset`, `stayfixed.agents` and `project.name`, whatever the base enforces, on the
ground that no gate reads them. That ground is a fact about the gates, so it is executed rather
than asserted: every built-in gate runs over a clone once under the loaded configuration and once
per neutral key moved, and must answer the same. The unchanged run has a finding, so "the same" is
not two empty answers. The keys are derived from the class table and the rule's own rows, so a key
reclassified as neutral tomorrow is run here the day it is.

No mutation of the rule reaches this, because the rule is not what it checks: the gates are. To
watch it fail, make `stayfixed.docs.hygiene.docs_gate` return `[]` when
`config.project.name == "gadget"`.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

import stayfixed
from stayfixed.assess import rule
from stayfixed.assess.gates import GateContext, run_gates
from stayfixed.config.classes import class_of
from stayfixed.config.loader import load
from stayfixed.config.schema import BUILTIN_GATES, Config
from tests.assess.baserepo import AGENTS, clone, commit
from tests.config.test_classes import schema_keys
from tests.gitfixture import git, needs_git

pytestmark = needs_git

# `AGENTS` is five lines, so it breaks this budget and the `docs` gate has a finding.
BASE = f"""[stayfixed]
version = "{stayfixed.__version__}"
state = "initialised"

[project]
name = "widget"

[budgets]
agents_md_lines = 3
"""
# Every key the rule holds to `neutral` whatever the base enforces: each schema key of a class no
# gate judges by, and each key the rule's own table rows `neutral`.
NEUTRAL = tuple(
    sorted(
        {key for key in schema_keys() if class_of(key) in rule._NEUTRAL_CLASSES}
        | {key for key, row in rule.ROWS.items() if row is rule._neutral}
    )
)
# A value a gate could tell from the loaded one, where any other would not do: an enumerated
# string moved to another of its values. Every other key is moved by its type.
MOVED_TO: dict[str, object] = {
    "stayfixed.preset": "other",
    "stayfixed.profile": "python",
    "stayfixed.agents": ("codex",),
    "memory.mode": "in-repo",
    "personal.preset": "other",
    "project.name": "gadget",
}


def _moved(config: Config, key: str) -> Config:
    """`config` with `key` alone holding another value."""
    section, name = key.split(".", 1)
    table = getattr(config, section)
    if section == "budgets":
        configured = {**table.configured, name: table.effective(name) + 1}
        return replace(config, budgets=replace(table, configured=configured))
    value = getattr(table, name)
    if key in MOVED_TO:
        other = MOVED_TO[key]
    elif isinstance(value, bool):
        other = not value
    elif isinstance(value, int):
        other = value + 1
    elif isinstance(value, str):
        other = f"{value}-moved"
    else:
        other = (*value, "moved")
    return replace(config, **{section: replace(table, **{name: other})})


def test_the_neutral_keys_are_derived_whole() -> None:
    # A floor against a derivation that finds nothing, and the gap this file had: it ran six keys
    # by hand while the rule made every preference, session budget, machine key and plugin cap
    # neutral. No mutation of the source reaches it: it holds this file's own derivation.
    assert {
        "memory.groups",
        "memory.index_extra",
        "budgets.volatile_ttl_days",
        "native_caps.hook_output_chars",
        "personal.reply_language",
        "stayfixed.preset",
        "project.name",
    } <= set(NEUTRAL)


@pytest.mark.parametrize("key", NEUTRAL)
def test_no_gate_reads_a_key_the_rule_calls_neutral(key: str, tmp_path: Path) -> None:
    project = clone(tmp_path, BASE)
    (project / "AGENTS.md").write_text(f"{AGENTS}- Changed.\n", encoding="utf-8")
    commit(project, "docs: say what changed")
    base = git(project, "rev-parse", "refs/remotes/origin/main").strip()
    config = load(project, machine=tmp_path / "absent.toml")
    moved_config = _moved(config, key)
    # The key moved, and nothing else did: a move that changed nothing would make the comparison
    # below hold for any gate.
    before, after = rule._values(config), rule._values(moved_config)
    assert {name for name in before if before[name] != after[name]} == {key}

    unchanged = run_gates(GateContext(project, config, base), BUILTIN_GATES)
    moved = run_gates(GateContext(project, moved_config, base), BUILTIN_GATES)

    assert any(result.findings for result in unchanged)
    assert moved == unchanged
