"""No gate reads a key the tighten-only rule calls `neutral`.

The rule lets a pull request change `stayfixed.preset`, `stayfixed.profile`, `stayfixed.agents`,
`project.name`, `memory.mode` and a session's budget whatever the base enforces, on the ground that
no gate reads them. That ground is
a fact about the gates, so it is executed rather than asserted: every built-in gate runs over a
clone once under the loaded configuration and once per neutral key moved, and must answer the
same. The unchanged run has a finding, so "the same" is not two empty answers.

No mutation of the rule reaches this, because the rule is not what it checks: the gates are. To
watch it fail, make `stayfixed.docs.hygiene.docs_gate` return `[]` when
`config.project.name == "gadget"`.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

import stayfixed
from stayfixed.assess.gates import GateContext, run_gates
from stayfixed.config.loader import load
from stayfixed.config.schema import BUILTIN_GATES, Config
from tests.assess.baserepo import AGENTS, clone, commit
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
# The keys `tests/assess/test_rule.py` and `tests/assess/test_rule_classes.py` hold to `neutral`
# whatever the base enforces.
NEUTRAL = (
    "stayfixed.preset",
    "stayfixed.profile",
    "stayfixed.agents",
    "project.name",
    "memory.mode",
    "budgets.memory_index_words",
)


def _moved(config: Config, key: str) -> Config:
    if key == "stayfixed.preset":
        return replace(config, stayfixed=replace(config.stayfixed, preset="other"))
    if key == "stayfixed.profile":
        return replace(config, stayfixed=replace(config.stayfixed, profile="python"))
    if key == "stayfixed.agents":
        return replace(config, stayfixed=replace(config.stayfixed, agents=("codex",)))
    if key == "memory.mode":
        return replace(config, memory=replace(config.memory, mode="in-repo"))
    if key == "budgets.memory_index_words":
        budgets = config.budgets
        configured = {**budgets.configured, "memory_index_words": 1}
        return replace(config, budgets=replace(budgets, configured=configured))
    assert key == "project.name"
    return replace(config, project=replace(config.project, name="gadget"))


@pytest.mark.parametrize("key", NEUTRAL)
def test_no_gate_reads_a_key_the_rule_calls_neutral(key: str, tmp_path: Path) -> None:
    project = clone(tmp_path, BASE)
    (project / "AGENTS.md").write_text(f"{AGENTS}- Changed.\n", encoding="utf-8")
    commit(project, "docs: say what changed")
    base = git(project, "rev-parse", "refs/remotes/origin/main").strip()
    config = load(project, machine=tmp_path / "absent.toml")

    unchanged = run_gates(GateContext(project, config, base), BUILTIN_GATES)
    moved = run_gates(GateContext(project, _moved(config, key), base), BUILTIN_GATES)

    assert any(result.findings for result in unchanged)
    assert moved == unchanged
