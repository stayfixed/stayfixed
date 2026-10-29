"""A pull request may tighten what its base enforces and may not loosen it: the rule, judged over
what the loader derives on each side rather than over the bytes.

Each row of the rule has a case here, and each anchor a case that fails without it. A refusal is
the answer that fails a run; `neutral`, `tightened` and `upgrade` let it through, so every case
that expects one of them has a sibling that expects the refusal it must not become.
"""

from __future__ import annotations

import copy
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

import stayfixed
from stayfixed.assess.rule import ConfigVerdict, Verdict, judge
from stayfixed.config.loader import preset_defaults
from stayfixed.config.paths import PathEscape
from stayfixed.config.schema import BUILTIN_GATES
from stayfixed.errors import Failure

SHA = "d" * 40
STRICT = f"""[stayfixed]
version = "{stayfixed.__version__}"
enforced = ["plan"]

[project]
name = "widget"

[budgets]
agents_md_lines = 250
"""
LOOSE = STRICT.replace('enforced = ["plan"]\n', "")
TESTS = '\n[gates.custom.tests]\nrun = ["pytest", "-q"]\n'
BUILTIN_BUT_TRAIL = '\n[gates]\nbuiltin = ["docs", "bugs", "plan", "commit"]\n'
DEFAULT_BUGS = preset_defaults("widget").paths.bugs


def _judge(
    base: str | None,
    tree: str,
    tmp_path: Path,
    *,
    running: str = stayfixed.__version__,
    workflow_sha: str | None = None,
    released: bool | None = True,
) -> ConfigVerdict:
    return judge(
        tmp_path,
        base,
        tree,
        machine=tmp_path / "absent.toml",
        running=running,
        workflow_sha=workflow_sha,
        released=lambda sha: released,
    )


def _verdicts(verdict: ConfigVerdict) -> dict[str, Verdict]:
    return {change.key: change.verdict for change in verdict.changes}


def _second_preset(monkeypatch: pytest.MonkeyPatch, edit: Callable[[dict[str, Any]], None]) -> None:
    """Every preset name but `recommended` loads as `recommended` with `edit` applied, in both
    readers of a preset a load asks: the project loader's and the owner's layer's."""
    import stayfixed.config.loader as loader
    import stayfixed.config.owner as owner
    from stayfixed import presets

    real = presets.load_preset

    def load(name: str, *, key: str = "[stayfixed] preset") -> dict[str, Any]:
        preset = copy.deepcopy(real("recommended", key=key))
        if name != "recommended":
            edit(preset)
        return preset

    monkeypatch.setattr(loader, "load_preset", load)
    monkeypatch.setattr(owner, "load_preset", load)


def _with(document: str, line: str) -> str:
    """`document` with `line` added to its `[stayfixed]` table."""
    return document.replace("[stayfixed]\n", f"[stayfixed]\n{line}", 1)


def _enforced(*names: str) -> str:
    """`STRICT` with `enforced` listing `names` in that order, or with no `enforced` line."""
    listed = ", ".join(f'"{name}"' for name in names)
    return STRICT.replace('enforced = ["plan"]\n', f"enforced = [{listed}]\n" if names else "")


# Every built-in gate listed: what a project that promoted each of them holds.
EVERY_GATE = _enforced(*BUILTIN_GATES)
# The same with the `tests` custom gate configured and listed beside them.
EVERY_GATE_AND_TESTS = _enforced(*BUILTIN_GATES, "tests") + TESTS


def _version(document: str, version: str) -> str:
    return document.replace(f'version = "{stayfixed.__version__}"', f'version = "{version}"')


def _ref(document: str, ref: str) -> str:
    return f'{document}\n[ci]\nref = "{ref}"\n'


def test_a_comment_is_not_a_change(tmp_path: Path) -> None:
    verdict = _judge(STRICT, f"# a note\n{STRICT}", tmp_path)
    assert verdict.changes == ()
    assert not verdict.refused


@pytest.mark.parametrize(
    ("base", "tree"),
    [
        pytest.param(
            STRICT,
            f'{STRICT}\n[paths]\nbugs = "{DEFAULT_BUGS}"\n',
            id="path-spelled-at-its-default",
        ),
        pytest.param(STRICT, _with(STRICT, 'preset = "recommended"\n'), id="preset-spelled-out"),
        pytest.param(_enforced("plan", "docs"), _enforced("docs", "plan"), id="enforced-reordered"),
        pytest.param(
            STRICT + BUILTIN_BUT_TRAIL,
            STRICT + '\n[gates]\nbuiltin = ["commit", "plan", "bugs", "docs"]\n',
            id="builtin-reordered",
        ),
    ],
)
def test_what_no_reader_can_tell_apart_is_no_change(base: str, tree: str, tmp_path: Path) -> None:
    # Bytes and raw keys are never compared. Emptying `_UNORDERED` reddens the two reordered
    # cases: each becomes a `neutral` change that no reader can see. It admits and refuses
    # nothing more, so it is not declared as a mutation.
    assert _judge(base, tree, tmp_path).changes == ()


@pytest.mark.parametrize(
    ("tree", "key", "expected"),
    [
        pytest.param(
            STRICT.replace("= 250", "= 200"),
            "budgets.agents_md_lines",
            Verdict.TIGHTENED,
            id="budget-lowered",
        ),
        pytest.param(
            STRICT.replace("= 250", "= 260"),
            "budgets.agents_md_lines",
            Verdict.REFUSED,
            id="budget-raised",
        ),
        pytest.param(
            _enforced("plan", "docs"), "stayfixed.enforced", Verdict.TIGHTENED, id="gate-promoted"
        ),
        pytest.param(_enforced(), "stayfixed.enforced", Verdict.REFUSED, id="gate-dropped"),
        pytest.param(
            STRICT.replace('name = "widget"', 'name = "gadget"'),
            "project.name",
            Verdict.NEUTRAL,
            id="renamed",
        ),
        pytest.param(
            _with(STRICT, 'profile = "python"\n'),
            "stayfixed.profile",
            Verdict.NEUTRAL,
            id="profile-chosen",
        ),
        pytest.param(
            _with(STRICT, 'agents = ["codex"]\n'),
            "stayfixed.agents",
            Verdict.NEUTRAL,
            id="harnesses-chosen",
        ),
        pytest.param(
            f'{STRICT}\n[paths]\nbugs = "elsewhere"\n',
            "paths.bugs",
            Verdict.REFUSED,
            id="path-moved-while-enforcing",
        ),
        pytest.param(
            STRICT + TESTS, "gates.custom.tests.run", Verdict.TIGHTENED, id="custom-gate-added"
        ),
        pytest.param(
            STRICT + BUILTIN_BUT_TRAIL, "gates.builtin", Verdict.NEUTRAL, id="advisory-gate-removed"
        ),
    ],
)
def test_each_row_of_the_table_while_a_gate_enforces(
    tree: str, key: str, expected: Verdict, tmp_path: Path
) -> None:
    # Refusing more is not declared as a mutation, and reddens a case each: `stayfixed.agents` out
    # of `ROWS` reddens `harnesses-chosen`, and a custom gate's addition refused reddens
    # `custom-gate-added`.
    verdict = _judge(STRICT, tree, tmp_path)
    assert _verdicts(verdict)[key] is expected
    assert verdict.refused is (expected is Verdict.REFUSED)


def test_enforced_that_loses_a_gate_the_base_lists_is_refused(tmp_path: Path) -> None:
    # A gate the base enforces leaves the list: refused, whatever the list gains beside it.
    verdict = _judge(_enforced("plan", "commit"), _enforced("docs"), tmp_path)
    assert _verdicts(verdict) == {"stayfixed.enforced": Verdict.REFUSED}
    assert verdict.refused


def test_a_base_that_still_spells_state_does_not_load_and_names_the_direct_push(
    tmp_path: Path,
) -> None:
    # A base whose copy still spells the removed `[stayfixed] state` no longer loads, so the
    # change cannot be judged, and the remedy is a direct push of the new spelling to the base.
    base = STRICT.replace("[stayfixed]\n", '[stayfixed]\nstate = "installed"\n', 1)
    with pytest.raises(Failure) as caught:
        _judge(base, STRICT, tmp_path)
    message = str(caught.value)
    assert message.startswith("the base's stayfixed.toml governs this change and does not load")
    assert "a direct push" in message and "unknown key(s): state" in message


def test_a_built_in_gate_added_is_a_tightening(tmp_path: Path) -> None:
    verdict = _judge(STRICT + BUILTIN_BUT_TRAIL, STRICT, tmp_path)
    assert _verdicts(verdict) == {"gates.builtin": Verdict.TIGHTENED}


@pytest.mark.parametrize(
    ("base", "tree", "key"),
    [
        pytest.param(
            EVERY_GATE,
            _enforced("docs", "bugs", "plan", "commit") + BUILTIN_BUT_TRAIL,
            "gates.builtin",
            id="built-in-removed",
        ),
        pytest.param(
            EVERY_GATE_AND_TESTS, EVERY_GATE, "gates.custom.tests.run", id="custom-removed"
        ),
        pytest.param(
            EVERY_GATE_AND_TESTS,
            EVERY_GATE_AND_TESTS.replace('["pytest", "-q"]', '["true"]'),
            "gates.custom.tests.run",
            id="custom-run-changed",
        ),
        pytest.param(
            EVERY_GATE_AND_TESTS,
            _enforced(*BUILTIN_GATES, "unit") + TESTS.replace("custom.tests", "custom.unit"),
            "gates.custom.tests.run",
            id="custom-renamed",
        ),
    ],
)
def test_a_gate_the_base_enforces_cannot_be_removed_or_given_another_command(
    base: str, tree: str, key: str, tmp_path: Path
) -> None:
    # The key's own verdict, not only `refused`: a gate removed or renamed also leaves
    # `enforced`, whose refusal alone would let a gate row that answered `neutral` through unseen.
    verdict = _judge(base, tree, tmp_path)
    assert _verdicts(verdict)[key] is Verdict.REFUSED
    assert verdict.refused


@pytest.mark.parametrize(
    "tree",
    [
        pytest.param(STRICT + TESTS.replace('["pytest", "-q"]', '["true"]'), id="run-changed"),
        pytest.param(STRICT, id="removed"),
    ],
)
def test_an_advisory_custom_gate_may_change_its_command_or_go(tree: str, tmp_path: Path) -> None:
    verdict = _judge(STRICT + TESTS, tree, tmp_path)
    assert _verdicts(verdict) == {"gates.custom.tests.run": Verdict.NEUTRAL}


def test_a_gate_added_and_listed_enforces_in_the_run_that_adds_it(tmp_path: Path) -> None:
    # A gate added later enforces only when the change lists it, which tightens; added and not
    # listed, it is advisory, whatever the base enforces.
    verdict = _judge(EVERY_GATE, EVERY_GATE_AND_TESTS, tmp_path)
    assert not verdict.refused
    assert _verdicts(verdict) == {
        "gates.custom.tests.run": Verdict.TIGHTENED,
        "stayfixed.enforced": Verdict.TIGHTENED,
    }
    assert "tests" in verdict.enforcing
    unlisted = _judge(EVERY_GATE, EVERY_GATE + TESTS, tmp_path)
    assert _verdicts(unlisted) == {"gates.custom.tests.run": Verdict.TIGHTENED}
    assert "tests" not in unlisted.enforcing


def _words(delta: int) -> Callable[[dict[str, Any]], None]:
    def edit(preset: dict[str, Any]) -> None:
        preset["budgets"]["agents_md_words"] += delta

    return edit


def _widen_types(preset: dict[str, Any]) -> None:
    preset["defaults"]["commit_messages"]["types"].append("perf")


@pytest.mark.parametrize(
    ("edit", "key", "expected"),
    [
        pytest.param(
            _words(-1), "budgets.agents_md_words", Verdict.TIGHTENED, id="lowers-a-budget"
        ),
        pytest.param(_words(+1), "budgets.agents_md_words", Verdict.REFUSED, id="raises-a-budget"),
        pytest.param(
            _widen_types, "commit_messages.types", Verdict.REFUSED, id="moves-another-default"
        ),
    ],
)
def test_a_preset_switch_is_judged_by_every_value_it_moves(
    edit: Callable[[dict[str, Any]], None],
    key: str,
    expected: Verdict,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # The preset's name is neutral because no gate reads it; what it moves is judged key by key,
    # by effective value, so a budget the preset raises is a raised budget.
    _second_preset(monkeypatch, edit)
    verdict = _judge(STRICT, _with(STRICT, 'preset = "other"\n'), tmp_path)
    assert _verdicts(verdict) == {"stayfixed.preset": Verdict.NEUTRAL, key: expected}


def test_a_path_moved_while_nothing_enforces_is_noted_and_the_run_uses_it(tmp_path: Path) -> None:
    verdict = _judge(LOOSE, f'{LOOSE}\n[paths]\nbugs = "elsewhere"\n', tmp_path)
    assert _verdicts(verdict) == {"paths.bugs": Verdict.NOTED}
    assert not verdict.refused
    assert verdict.config.paths.bugs == "elsewhere"


def test_a_promotion_is_enforced_in_its_own_run_under_the_tree_s_paths(tmp_path: Path) -> None:
    tree = f'{_enforced("bugs")}\n[paths]\nbugs = "elsewhere"\n'
    verdict = _judge(LOOSE, tree, tmp_path)
    assert not verdict.refused
    assert verdict.enforcing == {"bugs"}
    assert verdict.config.paths.bugs == "elsewhere"


def test_a_refusal_keeps_the_base_s_configuration_and_enforces_both_sides(tmp_path: Path) -> None:
    tree = _enforced("plan", "docs").replace("= 250", "= 260")
    verdict = _judge(STRICT, tree, tmp_path)
    assert verdict.refused
    assert verdict.config.budgets.effective("agents_md_lines") == 250
    assert verdict.enforcing == {"docs", "plan"}


def test_an_upgrade_to_the_running_release_at_the_workflow_s_commit_is_admitted(
    tmp_path: Path,
) -> None:
    base = _ref(_version(STRICT, "0.0.1"), "a" * 40)
    verdict = _judge(base, _ref(STRICT, SHA), tmp_path, workflow_sha=SHA)
    assert _verdicts(verdict) == {"ci.ref": Verdict.UPGRADE, "stayfixed.version": Verdict.UPGRADE}
    assert not verdict.refused


def test_a_version_move_under_a_ref_that_is_not_a_commit_is_an_upgrade(tmp_path: Path) -> None:
    # What `stayfixed upgrade` writes for a project pinned to `v1`: the version moves, the ref does
    # not. Dropping `pin == sides.base.ci.ref or` refuses this, which refuses more.
    base = _ref(_version(STRICT, "0.0.1"), "v1")
    verdict = _judge(base, _ref(STRICT, "v1"), tmp_path)
    assert _verdicts(verdict) == {"stayfixed.version": Verdict.UPGRADE}


@pytest.mark.parametrize(
    ("workflow_sha", "released"),
    [
        pytest.param(None, True, id="no-workflow-sha"),
        pytest.param("e" * 40, True, id="another-commit"),
        pytest.param(SHA, False, id="not-released"),
        pytest.param(SHA, None, id="tags-unreadable"),
    ],
)
def test_a_pin_the_platform_does_not_vouch_for_is_refused_while_enforcing(
    workflow_sha: str | None, released: bool | None, tmp_path: Path
) -> None:
    base = _ref(_version(STRICT, "0.0.1"), "a" * 40)
    verdict = _judge(
        base, _ref(STRICT, SHA), tmp_path, workflow_sha=workflow_sha, released=released
    )
    assert _verdicts(verdict)["ci.ref"] is Verdict.REFUSED


def test_a_version_moving_down_is_not_an_upgrade(tmp_path: Path) -> None:
    verdict = _judge(_version(STRICT, "99.0.0"), STRICT, tmp_path)
    assert _verdicts(verdict) == {"stayfixed.version": Verdict.REFUSED}


def test_a_release_moved_to_its_own_pre_release_is_not_an_upgrade(tmp_path: Path) -> None:
    # `stayfixed upgrade` refuses this move; a reader that compared the triples alone admitted it.
    base, tree = _version(STRICT, "9.9.9"), _version(STRICT, "9.9.9rc1")
    verdict = _judge(base, tree, tmp_path, running="9.9.9rc1")
    assert _verdicts(verdict) == {"stayfixed.version": Verdict.REFUSED}


def test_a_pre_release_moved_to_its_release_is_an_upgrade(tmp_path: Path) -> None:
    # A reader asking whether the running release satisfies the base's refused this, which
    # refuses more, so it is not declared as a mutation.
    base, tree = _version(STRICT, "9.9.9rc1"), _version(STRICT, "9.9.9")
    verdict = _judge(base, tree, tmp_path, running="9.9.9")
    assert _verdicts(verdict) == {"stayfixed.version": Verdict.UPGRADE}


def test_a_version_pair_stayfixed_does_not_order_is_not_an_upgrade(tmp_path: Path) -> None:
    base, tree = _version(STRICT, "9.9.9rc1"), _version(STRICT, "9.9.9rc2")
    verdict = _judge(base, tree, tmp_path, running="9.9.9rc2")
    assert _verdicts(verdict) == {"stayfixed.version": Verdict.REFUSED}


def test_a_version_that_is_not_the_running_stayfixed_s_is_not_an_upgrade(tmp_path: Path) -> None:
    base, tree = _version(STRICT, "0.0.1"), _version(STRICT, "0.0.9")
    verdict = _judge(base, tree, tmp_path, running="0.1.0")
    assert _verdicts(verdict) == {"stayfixed.version": Verdict.REFUSED}


def test_no_base_copy_is_the_bootstrap_and_the_tree_decides(tmp_path: Path) -> None:
    verdict = _judge(None, STRICT, tmp_path)
    assert verdict.bootstrap
    assert verdict.changes == ()
    assert verdict.enforcing == {"plan"}
    assert not verdict.refused


def test_the_same_document_on_both_sides_changes_nothing(tmp_path: Path) -> None:
    # What a push to the base branch judges: the base against itself.
    verdict = _judge(STRICT, STRICT, tmp_path)
    assert not verdict.bootstrap
    assert verdict.changes == ()
    assert verdict.enforcing == {"plan"}


def test_a_value_outside_the_path_grammar_is_refused_by_name_before_it_is_judged(
    tmp_path: Path,
) -> None:
    # No mutation of its own: the loader's path-grammar entry covers it.
    with pytest.raises(PathEscape, match=r"paths\.bugs") as raised:
        _judge(STRICT, f'{STRICT}\n[paths]\nbugs = "x\\u001b[31m"\n', tmp_path)
    assert "\x1b" not in str(raised.value)
