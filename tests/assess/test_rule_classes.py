"""The tighten-only rule asks a key's class first (`assess.rule._row`): a key no gate judges a pull
request by — a preference, the machine owner's, the plugin's — is `neutral` whatever the base
enforces; a budget, a gate's or a session's, may only be lowered; and the two ledger lists only
grow. `tests/assess/test_rule.py` holds every other row."""

from __future__ import annotations

from pathlib import Path

import pytest

from stayfixed.assess.rule import Verdict
from tests.assess.test_rule import LOOSE, STRICT, _judge, _verdicts

LEDGER = '\n[ledger]\ncode_roots = ["src", "tests", "scripts"]\n'


def test_a_pull_request_still_only_lowers_a_gate_budget(tmp_path: Path) -> None:
    # The base raised the budget above the preset (900 > 300); the change is judged against that.
    # Mutations (`mutations/`'s "a budget is still only ever lowered" -> both sides read the
    # preset's 300 and the lowering is no change; "a raised budget is read as a tightening" ->
    # the raise is admitted).
    base = STRICT.replace("= 250", "= 900")
    raised = _judge(base, STRICT.replace("= 250", "= 950"), tmp_path)
    assert _verdicts(raised) == {"budgets.agents_md_lines": Verdict.REFUSED}
    lowered = _judge(base, STRICT.replace("= 250", "= 600"), tmp_path)
    assert _verdicts(lowered) == {"budgets.agents_md_lines": Verdict.TIGHTENED}


@pytest.mark.parametrize(
    ("value", "expected"),
    [(9000, Verdict.REFUSED), (10, Verdict.TIGHTENED)],
    ids=["raised", "lowered"],
)
def test_a_pull_request_only_lowers_a_session_budget(
    tmp_path: Path, value: int, expected: Verdict
) -> None:
    # A gate the base enforces may read a session budget (`memory index --check` reads
    # `memory_index_words`), so a pull request that raised one would loosen the gate judging it.
    # Mutation (`mutations/`'s "a session's budget is neutral by its class"): the raise is
    # admitted as neutral.
    tree = f"{STRICT}memory_index_words = {value}\n"
    verdict = _judge(STRICT, tree, tmp_path)
    assert _verdicts(verdict) == {"budgets.memory_index_words": expected}


def test_a_pull_request_may_change_memory_mode(tmp_path: Path) -> None:
    # A preference. Mutation (`mutations/`'s "the ratchet judges no key by its class"): the key
    # reaches `_other` and is refused while the base enforces a gate.
    verdict = _judge(STRICT, f'{STRICT}\n[memory]\nmode = "in-repo"\n', tmp_path)
    assert _verdicts(verdict) == {"memory.mode": Verdict.NEUTRAL}
    assert not verdict.refused


@pytest.mark.parametrize(
    ("tree", "key", "expected"),
    [
        pytest.param(
            STRICT + LEDGER.replace('"scripts"]', '"scripts", "lib"]'),
            "ledger.code_roots",
            Verdict.TIGHTENED,
            id="root-added",
        ),
        pytest.param(
            STRICT + LEDGER.replace('["src", "tests", "scripts"]', '["src"]'),
            "ledger.code_roots",
            Verdict.REFUSED,
            id="root-removed",
        ),
        pytest.param(
            STRICT + LEDGER.replace('"scripts"]', '"lib"]'),
            "ledger.code_roots",
            Verdict.REFUSED,
            id="root-swapped",
        ),
        pytest.param(
            STRICT + LEDGER.replace('["src", "tests", "scripts"]', '["scripts", "src", "tests"]'),
            "ledger.code_roots",
            Verdict.NEUTRAL,
            id="roots-reordered",
        ),
        pytest.param(
            f'{STRICT}\n[ledger]\nevidence_boundary_required_for = ["high", "medium"]\n',
            "ledger.evidence_boundary_required_for",
            Verdict.TIGHTENED,
            id="severity-added",
        ),
        pytest.param(
            f"{STRICT}\n[ledger]\nevidence_boundary_required_for = []\n",
            "ledger.evidence_boundary_required_for",
            Verdict.REFUSED,
            id="severity-removed",
        ),
    ],
)
def test_adding_a_code_root_tightens_and_removing_one_is_refused_while_enforcing(
    tmp_path: Path, tree: str, key: str, expected: Verdict
) -> None:
    # A superset tightens, the same set is no loosening, and anything else is a key the rule
    # cannot tell the direction of. Mutation (`mutations/`'s "a ledger list that lost an entry
    # reads as grown"): `root-removed`, `root-swapped` and `severity-removed` are admitted.
    verdict = _judge(STRICT + LEDGER, tree, tmp_path)
    assert _verdicts(verdict)[key] is expected
    assert verdict.refused is (expected is Verdict.REFUSED)


def test_removing_a_code_root_is_noted_when_nothing_enforces(tmp_path: Path) -> None:
    # `_other`'s second arm, reached through the ledger row. No mutation of its own: `_other` is
    # held by `tests/assess/test_rule.py`, and this case says only that the ledger row hands a
    # shrunk list to it rather than refusing outright.
    tree = LOOSE + LEDGER.replace('["src", "tests", "scripts"]', '["src"]')
    verdict = _judge(LOOSE + LEDGER, tree, tmp_path)
    assert _verdicts(verdict) == {"ledger.code_roots": Verdict.NOTED}
