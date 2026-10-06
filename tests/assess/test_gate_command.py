"""`stayfixed gate` through the real parser, over a real clone: the verdict a pull request faces.

Every case commits its edit, because CI checks out a committed head, except the one that asks
about an uncommitted loosening on purpose. A refusal, a failure and an internal error all print
on standard error, so every case that must not quote a name reads both streams.
"""

from __future__ import annotations

import io
import json
from contextlib import redirect_stdout
from pathlib import Path

import pytest

import stayfixed
from stayfixed.assess import rule
from stayfixed.assess.gates import STOPPED
from stayfixed.assess.report import (
    BOOTSTRAP,
    BUILTIN_FINDINGS_ELSEWHERE,
    FINDINGS_ELSEWHERE,
    NOT_ON_BASE,
)
from stayfixed.cli import build_parser, discover_registrars, run
from stayfixed.config.loader import CONFIG_FILE
from tests.assess.baserepo import AGENTS, clone, commit
from tests.cli import cli, custom_gate
from tests.gitfixture import git, needs_git

pytestmark = needs_git

BASE = f"""[stayfixed]
version = "{stayfixed.__version__}"
state = "adopting"
enforced = ["docs"]

[project]
name = "widget"
"""
LOOSENED = BASE.replace('["docs"]', "[]")
BUILTINS = ["docs", "bugs", "plan", "commit", "trail"]
SHA = "b" * 40
# Well past the preset's `AGENTS.md` budget, so the `docs` gate has a finding.
OVER_BUDGET = "".join("word\n" for _ in range(400))
NOTHING_TO_RUN = "nothing to run: no configured gate of the kind asked for"


MARKER = custom_gate("tests", "open('marker', 'w').close()")


def _heads(out: str) -> list[str]:
    return [line.split(":", 1)[0] for line in out.splitlines()]


def _change(project: Path, text: str, *, agents: str | None = None) -> None:
    """Commit `text` as the tree's `stayfixed.toml`, and `agents` as its `AGENTS.md`."""
    (project / CONFIG_FILE).write_text(text, encoding="utf-8")
    if agents is not None:
        (project / "AGENTS.md").write_text(agents, encoding="utf-8")
    commit(project, "chore: the change under review")


def test_a_loosening_change_fails_the_configuration_check(tmp_path: Path) -> None:
    project = clone(tmp_path, BASE)
    _change(project, LOOSENED)
    code, out, _ = cli(project, tmp_path, "gate", "--only", "config")
    assert code == 1
    assert "stayfixed.enforced" in out


def test_the_bare_command_judges_the_configuration_and_runs_every_configured_gate(
    tmp_path: Path,
) -> None:
    project = clone(tmp_path, BASE)
    code, out, _ = cli(project, tmp_path, "gate")
    assert code == 0, out
    assert _heads(out) == ["config", *BUILTINS]


def test_json_carries_the_verdict_and_each_gate_s_count_and_no_finding(tmp_path: Path) -> None:
    # Advice: the shape `docs/cli.md` promises. Mutation: drop `"refused"` from the `config`
    # object -> the key comparison reddens.
    project = clone(tmp_path, BASE)
    _change(project, LOOSENED)
    code, out, _ = cli(project, tmp_path, "gate", "--only", "config", "--only", "docs", "--json")
    assert code == 1
    printed = json.loads(out)
    assert set(printed["config"]) == {"judged", "base_state", "changes", "refused", "enforcing"}
    assert printed["config"]["changes"] == [{"key": "stayfixed.enforced", "verdict": "refused"}]
    assert printed["config"]["refused"] is True
    assert printed["gates"] == [
        {
            "name": "docs",
            "enforcing": True,
            "answered": True,
            "reason": "",
            "count": 0,
            "failing": False,
        }
    ]


def test_an_enforced_custom_gate_runs_its_command_and_fails_on_its_exit_status(
    tmp_path: Path,
) -> None:
    # The base has the command; the change enforces it, and is held to it in its own run.
    failing = custom_gate("tests", "raise SystemExit(3)")
    project = clone(tmp_path, BASE + failing)
    _change(project, BASE.replace('["docs"]', '["docs", "tests"]') + failing)
    code, out, _ = cli(project, tmp_path, "gate")
    assert code == 1
    assert "tests: enforcing, 1 finding(s)" in out.splitlines()


def test_a_built_in_gate_added_under_installed_enforces_in_the_run_that_adds_it(
    tmp_path: Path,
) -> None:
    # Under `installed` every gate the project runs enforces, so the pull request that adds a
    # built-in gate is held to it at once: the enforcing set is the base's and the tree's.
    # Mutation: `judge` enforcing the base's set alone (declared against the rule's own tests)
    # -> `docs` is advisory here and the run passes.
    installed = BASE.replace('state = "adopting"\nenforced = ["docs"]\n', 'state = "installed"\n')
    project = clone(tmp_path, installed + '\n[gates]\nbuiltin = ["bugs"]\n')
    _change(project, installed + '\n[gates]\nbuiltin = ["docs", "bugs"]\n', agents=OVER_BUDGET)
    code, out, _ = cli(project, tmp_path, "gate")
    assert code == 1
    lines = out.splitlines()
    assert lines[0] == "config: 2 change(s), 0 refused"
    # The 400-line `AGENTS.md` breaks two budgets; "could not run" would not be this line.
    assert lines[1] == "docs: enforcing, 2 finding(s)"


def test_builtin_runs_no_command_the_repository_wrote_and_custom_runs_only_those(
    tmp_path: Path,
) -> None:
    project = clone(tmp_path, BASE + MARKER)
    code, out, _ = cli(project, tmp_path, "gate", "--builtin")
    assert code == 0, out
    assert not (project / "marker").exists()
    assert _heads(out) == ["config", *BUILTINS]
    code, out, _ = cli(project, tmp_path, "gate", "--custom")
    assert code == 0, out
    assert (project / "marker").exists()
    assert _heads(out) == ["tests"]


def test_custom_alone_leaves_the_verdict_to_the_judging_run(tmp_path: Path) -> None:
    # The judging run refuses this change and the workflow never reaches the custom step; run by
    # hand, `--custom` reports the gates and nothing else. No mutation: counting the refusal here
    # would only fail a run that already failed.
    passing = custom_gate("tests", "pass")
    project = clone(tmp_path, BASE + passing)
    _change(project, LOOSENED + passing)
    code, out, _ = cli(project, tmp_path, "gate", "--custom")
    assert code == 0, out
    assert _heads(out) == ["tests"]


def test_custom_on_a_project_with_no_custom_gate_exits_zero(tmp_path: Path) -> None:
    # The reusable workflow runs `--custom` on every caller, most of which configure no gate of
    # their own. Mutation (advice): `raise Refusal(NOTHING_TO_RUN)` in place of the `Result` ->
    # exit 2, and every such project's pull requests fail.
    project = clone(tmp_path, BASE)
    code, out, _ = cli(project, tmp_path, "gate", "--custom")
    assert (code, out.strip()) == (0, NOTHING_TO_RUN)


def test_builtin_skips_a_custom_gate_named_by_only(tmp_path: Path) -> None:
    # A matrix caller's `only:` may name a custom gate in the judging step: it is the next
    # step's to run, so it is skipped here and not refused, and the configuration is judged.
    project = clone(tmp_path, BASE + MARKER)
    code, out, _ = cli(project, tmp_path, "gate", "--builtin", "--only", "tests")
    assert (code, _heads(out)) == (0, ["config"])
    assert not (project / "marker").exists()


def test_builtin_judges_the_configuration_whatever_only_names(tmp_path: Path) -> None:
    # The rule that makes the judging step a judge lives in the command, not in the workflow's
    # shell: a caller's own matrix, a person reproducing CI, or a later edit to the YAML each
    # ran `--builtin --only docs` and passed a change that loosens what the base enforces.
    # Mutation (declared): the configuration check left to `--only` -> exit 0.
    project = clone(tmp_path, BASE)
    _change(project, LOOSENED)
    code, out, _ = cli(project, tmp_path, "gate", "--builtin", "--only", "docs")
    assert code == 1
    assert out.splitlines()[:2] == [
        "config: 1 change(s), 1 refused: stayfixed.enforced",
        "docs: enforcing, 0 finding(s)",
    ]
    # Run bare, `--only` still means only: that run is a person's own question.
    code, out, _ = cli(project, tmp_path, "gate", "--only", "docs")
    assert (code, _heads(out)) == (0, ["docs"])


def test_a_gate_only_the_refused_tree_defines_is_not_run_and_the_run_fails(
    tmp_path: Path,
) -> None:
    # A refused change runs under the base's configuration, and the enforcing set is still both
    # sides': here it names `tests`, which only the tree defines. The run neither runs the tree's
    # command nor trips over the name — it fails on the refusal. With the names to run read off
    # the tree, `run_gates` raises `KeyError('tests')`: exit 2, which this case catches, but the
    # same mutation makes the custom step of the dropped-gate case below pass with nothing run.
    project = clone(tmp_path, BASE)
    tree = BASE.replace('["docs"]', '["docs", "tests"]') + MARKER
    _change(project, tree + '\n[paths]\nbugs = "elsewhere"\n')
    code, out, err = cli(project, tmp_path, "gate")
    assert code == 1, err
    assert out.splitlines()[0].endswith("refused: paths.bugs")
    assert _heads(out) == ["config", *BUILTINS, "details"]
    assert not (project / "marker").exists()


ENFORCES_TESTS = BASE.replace('["docs"]', '["docs", "tests"]')


def test_a_refused_change_runs_the_base_s_command_for_a_gate_the_base_enforces(
    tmp_path: Path,
) -> None:
    # A custom gate's command is fixed by the base while the base enforces it: the change that
    # re-commands it is refused, the judging step fails on that, and the custom step runs the
    # base's command, never the change's.
    project = clone(tmp_path, ENFORCES_TESTS + custom_gate("tests", "pass"))
    _change(project, ENFORCES_TESTS + MARKER)
    code, out, _ = cli(project, tmp_path, "gate", "--builtin")
    assert code == 1
    assert out.splitlines()[0] == "config: 1 change(s), 1 refused: gates.custom.tests.run"
    assert _heads(out) == ["config", *BUILTINS, "details"]
    code, out, _ = cli(project, tmp_path, "gate", "--custom")
    assert (code, out.strip()) == (0, "tests: enforcing, 0 finding(s)")
    assert not (project / "marker").exists()


def test_a_refused_change_is_checked_at_the_base_s_paths(tmp_path: Path) -> None:
    # A refused `[paths]` value does not move where the gates look: here the change points
    # `agents_md` at a small file and leaves the over-budget one where the base reads it.
    project = clone(tmp_path, BASE)
    (project / "NOTES.md").write_text(AGENTS, encoding="utf-8")
    _change(project, BASE + '\n[paths]\nagents_md = "NOTES.md"\n', agents=OVER_BUDGET)
    code, out, _ = cli(project, tmp_path, "gate", "--only", "config", "--only", "docs")
    assert code == 1
    lines = out.splitlines()
    assert lines[0] == "config: 1 change(s), 1 refused: paths.agents_md"
    # The 400-line `AGENTS.md` breaks two budgets; "could not run" would not be this line.
    assert lines[1] == "docs: enforcing, 2 finding(s)"


def test_a_custom_gate_the_base_does_not_enforce_waits_for_its_new_command_to_land(
    tmp_path: Path,
) -> None:
    # The legitimate side of the two cases above: re-commanding a gate the base does not
    # enforce is neutral, so the judging step passes. The new command is the change's own, and
    # it runs once it has landed on the base; until then the gate is named as waiting, and
    # waiting fails nothing, since the base enforces no command it lacks.
    project = clone(tmp_path, BASE + custom_gate("tests", "pass"))
    _change(project, BASE + MARKER)
    code, out, _ = cli(project, tmp_path, "gate", "--builtin")
    assert code == 0, out
    assert out.splitlines()[0] == "config: 1 change(s), 0 refused"
    assert not (project / "marker").exists()
    code, out, _ = cli(project, tmp_path, "gate", "--custom")
    assert (code, out.strip()) == (0, f"tests: advisory, {NOT_ON_BASE}")
    assert not (project / "marker").exists()


POLICY_BASE = f"""[stayfixed]
version = "{stayfixed.__version__}"
state = "adopting"
enforced = ["policy"]

[project]
name = "widget"

[gates.custom.policy]
run = ["sh", "scripts/policy.sh"]
"""
POLICY = {"scripts/policy.sh": "test ! -e forbidden.txt\n"}
# A command that rewrites the enforced gate's script so that it passes whatever the tree holds.
REWRITE_POLICY = """["sh", "-c", "printf 'exit 0\\n' > scripts/policy.sh"]"""


def _forbidden(project: Path) -> None:
    (project / "forbidden.txt").write_text("", encoding="utf-8")
    commit(project, "feat: the file the enforced gate forbids")


def test_a_custom_gate_the_change_adds_cannot_rewrite_what_an_enforced_gate_runs(
    tmp_path: Path,
) -> None:
    # The attack, step by step. The base enforces `policy`, whose script refuses `forbidden.txt`,
    # and the change adds that file. With nothing else, the custom step fails. The change also
    # adds a gate `aaa`, which sorts first and rewrites the script to `exit 0`: adding a gate is
    # a tightening, so the judging step passes, and before this fix the custom step ran `aaa`
    # first and `policy` then passed over a script it never had on the base. Mutation (declared):
    # the gates waiting for the base emptied, so `aaa` runs -> its line and the script reddens.
    project = clone(tmp_path, POLICY_BASE, also=POLICY)
    _forbidden(project)
    code, out, _ = cli(project, tmp_path, "gate", "--custom")
    assert (code, out.splitlines()[0]) == (1, "policy: enforcing, 1 finding(s)")
    _change(project, POLICY_BASE + f"\n[gates.custom.aaa]\nrun = {REWRITE_POLICY}\n")
    code, out, _ = cli(project, tmp_path, "gate", "--builtin")
    assert (code, out.splitlines()[0]) == (0, "config: 1 change(s), 0 refused")
    code, out, _ = cli(project, tmp_path, "gate", "--custom")
    assert code == 1
    assert out.splitlines() == [
        "policy: enforcing, 1 finding(s)",
        f"aaa: advisory, {NOT_ON_BASE}",
        FINDINGS_ELSEWHERE,
    ]
    assert (project / "scripts" / "policy.sh").read_text(encoding="utf-8") == POLICY[
        "scripts/policy.sh"
    ]
    assert git(project, "status", "--porcelain") == ""


def test_the_base_s_enforced_gates_run_before_an_advisory_gate_that_sorts_first(
    tmp_path: Path,
) -> None:
    # The same attack with no new gate: the base already has an advisory gate that sorts first
    # and runs files the change can edit, a test runner and its `conftest.py`, say, here reduced
    # to the rewrite itself. The base's enforced gates run first, so what they execute is the
    # change's as committed. Mutation (declared): every gate in configured order -> `a-tests`
    # runs first, `policy` passes, and the run exits 0.
    tests = f"\n[gates.custom.a-tests]\nrun = {REWRITE_POLICY}\n"
    project = clone(tmp_path, POLICY_BASE + tests, also=POLICY)
    _forbidden(project)
    code, out, _ = cli(project, tmp_path, "gate", "--custom")
    assert code == 1
    assert out.splitlines() == [
        "policy: enforcing, 1 finding(s)",
        f"a-tests: advisory, {STOPPED}",
        FINDINGS_ELSEWHERE,
    ]


def test_no_other_custom_gate_starts_once_an_enforced_custom_gate_has_failed(
    tmp_path: Path,
) -> None:
    # The verdict of the custom step is its exit status, and the process that holds it would go
    # on to run every advisory gate: files the change can edit, which on a hosted runner run with
    # passwordless `sudo` and can rewrite or end the waiting parent. So once a gate the base
    # enforces has failed, no other custom gate starts; here the one that would have started
    # writes `marker`. Mutation (declared): the check before the later gates made `if False:`
    # -> `later` runs and writes `marker`.
    later = custom_gate("later", "open('marker', 'w').close()")
    project = clone(tmp_path, POLICY_BASE + later, also=POLICY)
    _forbidden(project)
    code, out, _ = cli(project, tmp_path, "gate", "--custom")
    assert code == 1
    assert out.splitlines() == [
        "policy: enforcing, 1 finding(s)",
        f"later: advisory, {STOPPED}",
        FINDINGS_ELSEWHERE,
    ]
    assert not (project / "marker").exists()
    code, out, _ = cli(project, tmp_path, "gate", "--custom", "--json")
    assert code == 1
    assert json.loads(out)["gates"][1] == {
        "name": "later",
        "enforcing": False,
        "answered": False,
        "reason": STOPPED,
        "count": 0,
        "failing": True,
    }
    assert not (project / "marker").exists()
    # And `--only` narrows the same run rather than going round it.
    code, out, _ = cli(project, tmp_path, "gate", "--custom", "--only", "policy", "--only", "later")
    assert (code, out.splitlines()[1]) == (1, f"later: advisory, {STOPPED}")
    assert not (project / "marker").exists()
    # The other side: once every enforced gate passes, the rest run as they always did.
    (project / "forbidden.txt").unlink()
    commit(project, "fix: the forbidden file is gone")
    code, out, _ = cli(project, tmp_path, "gate", "--custom")
    assert (code, out.splitlines()) == (
        0,
        ["policy: enforcing, 0 finding(s)", "later: advisory, 0 finding(s)"],
    )
    assert (project / "marker").exists()


def test_no_enforced_custom_gate_starts_once_another_has_failed_the_run(tmp_path: Path) -> None:
    # Two gates the base enforces, as the docs suggest: a pinned policy and a test runner, which
    # runs files the change can edit. The policy sorts first and fails, so the run has failed,
    # and the test runner would then run the change's code in the process holding that verdict:
    # the same premise as an advisory gate, with the gate enforced. So it is not started either;
    # it would have written `marker`. Mutation (declared): the question asked only before a gate
    # outside the base's enforced ones -> `tests` runs and writes `marker`.
    tests = custom_gate("tests", "open('marker', 'w').close()")
    both = POLICY_BASE.replace('["policy"]', '["policy", "tests"]') + tests
    project = clone(tmp_path, both, also=POLICY)
    _forbidden(project)
    code, out, _ = cli(project, tmp_path, "gate", "--custom")
    assert code == 1
    assert out.splitlines() == [
        "policy: enforcing, 1 finding(s)",
        f"tests: enforcing, {STOPPED}",
        FINDINGS_ELSEWHERE,
    ]
    assert not (project / "marker").exists()
    code, out, _ = cli(project, tmp_path, "gate", "--custom", "--json")
    assert code == 1
    assert json.loads(out)["gates"][1] == {
        "name": "tests",
        "enforcing": True,
        "answered": False,
        "reason": STOPPED,
        "count": 0,
        "failing": True,
    }
    assert not (project / "marker").exists()
    # The other side: with the policy passing, the test runner runs as it always did.
    (project / "forbidden.txt").unlink()
    commit(project, "fix: the forbidden file is gone")
    code, out, _ = cli(project, tmp_path, "gate", "--custom")
    assert (code, out.splitlines()) == (
        0,
        ["policy: enforcing, 0 finding(s)", "tests: enforcing, 0 finding(s)"],
    )
    assert (project / "marker").exists()


@pytest.mark.parametrize("failing", ["enforced-built-in", "refused-key"])
def test_a_bare_run_that_has_already_failed_starts_no_custom_gate(
    tmp_path: Path, failing: str
) -> None:
    # The same holding process, run bare: everything in one process, the configuration check and
    # the built-ins first. A refused key or a failing enforced built-in has decided the run, and
    # a custom gate the base does not enforce is not started after it. Mutations (declared): the
    # check made `if False:` -> both cases write `marker`; the configuration check not counted in
    # it -> the refused-key case writes it.
    project = clone(tmp_path, BASE + MARKER)
    if failing == "enforced-built-in":
        _change(project, BASE + MARKER, agents=OVER_BUDGET)
    else:
        _change(project, LOOSENED + MARKER)
    code, out, _ = cli(project, tmp_path, "gate")
    assert code == 1
    assert f"tests: advisory, {STOPPED}" in out.splitlines()
    assert not (project / "marker").exists()


def test_under_the_bootstrap_no_custom_gate_has_landed_and_none_runs(tmp_path: Path) -> None:
    # A base with no stayfixed.toml at this path has no command of its own, so the change's
    # gates wait, the one it enforces included, and the run passes: the base enforces nothing
    # that is left unrun. `--json` names them apart from the gates that ran.
    project = clone(tmp_path, BASE, under="sub")
    _change(project, BASE.replace('["docs"]', '["docs", "tests"]') + MARKER)
    code, out, err = cli(project, tmp_path, "gate", "--custom")
    assert (code, out.strip()) == (0, f"tests: enforcing, {NOT_ON_BASE}"), err
    assert not (project / "marker").exists()
    code, out, _ = cli(project, tmp_path, "gate", "--custom", "--json")
    printed = json.loads(out)
    assert (printed["gates"], printed["not_on_base"]) == ([], ["tests"])


def test_builtin_runs_no_custom_gate_the_base_keeps_when_the_change_drops_it(
    tmp_path: Path,
) -> None:
    # Which names are custom is the verdict's configuration's answer too: a change that drops
    # an enforced custom gate is refused and runs under the base's configuration, where the
    # gate still is. Read off the tree, the judging step would take it for a built-in and run
    # its command in the process that judges; and with the names to run read off the tree, the
    # custom step would find nothing to run and pass without running the gate the base enforces.
    project = clone(tmp_path, ENFORCES_TESTS + MARKER)
    _change(project, BASE)
    code, out, _ = cli(project, tmp_path, "gate", "--builtin")
    assert code == 1
    assert out.splitlines()[0] == (
        "config: 2 change(s), 2 refused: gates.custom.tests.run, stayfixed.enforced"
    )
    assert _heads(out) == ["config", *BUILTINS, "details"]
    assert not (project / "marker").exists()
    code, out, _ = cli(project, tmp_path, "gate", "--custom")
    assert (code, out.strip()) == (0, "tests: enforcing, 0 finding(s)")
    assert (project / "marker").exists()


NESTED = "a = " + "[" * 2000 + "]" * 2000 + "\n"  # past the parser's recursion


def test_a_trail_toml_nested_past_the_parser_is_one_gate_that_could_not_run(
    tmp_path: Path,
) -> None:
    # `tomllib` recurses on nested arrays, and a `RecursionError` out of `read_trail` was an
    # internal error that ended the whole run: no `config:` line, no result for the enforced
    # gate. It is one gate that could not run, and the rest still answer. No mutation here: the
    # reader's catch and `_guarded`'s backstop each answer this alone, so each is declared
    # against its own case (`tests/config/test_deep_toml.py`, `tests/assess/test_gates.py`).
    project = clone(tmp_path, BASE, also={"docs/roadmap.md": "# Roadmap\n"})
    (project / "docs" / "trail.toml").write_text(NESTED, encoding="utf-8")
    commit(project, "docs: a trail nested past the parser")
    code, out, err = cli(project, tmp_path, "gate", "--builtin")
    assert code == 0, err
    lines = out.splitlines()
    assert lines[:2] == [
        "config: stayfixed.toml unchanged from the base",
        "docs: enforcing, 0 finding(s)",
    ]
    assert "trail: advisory, could not run" in lines


@pytest.mark.parametrize("side", ["tree", "base"])
def test_a_stayfixed_toml_nested_past_the_parser_does_not_load_naming_the_side(
    tmp_path: Path, side: str
) -> None:
    # "Does not load", as for any document that does not parse, and never an internal error;
    # the base's copy is named as the base's. Mutation (declared): `loads` catching
    # `TOMLDecodeError` alone -> `internal error: RecursionError`, exit 2.
    nested = BASE + "\n[gates]\n" + NESTED.replace("a = ", "x = ")
    project = clone(tmp_path, nested if side == "base" else BASE)
    _change(project, nested if side == "tree" else BASE)
    code, out, err = cli(project, tmp_path, "gate", "--builtin")
    assert (code, out) == (1, ""), err
    assert "internal error" not in err
    assert "not valid TOML (nested deeper than the parser reads)" in err
    assert ("the base's stayfixed.toml" in err) is (side == "base")


def test_a_tree_without_stayfixed_toml_fails_and_names_the_file(tmp_path: Path) -> None:
    # `stayfixed uninstall` in a pull request: nothing says which gates run. Mutation (advice):
    # drop the `tree_text is None` check -> `loads(None)` is an internal error, exit 2, and the
    # exit code reddens. Not declared: exit 2 fails the run as well.
    project = clone(tmp_path, BASE)
    git(project, "rm", "-q", CONFIG_FILE)
    commit(project, "chore: uninstall")
    code, _, err = cli(project, tmp_path, "gate")
    assert code == 1
    assert "no stayfixed.toml" in err


def test_a_symlinked_stayfixed_toml_is_refused(tmp_path: Path) -> None:
    project = clone(tmp_path, BASE)
    outside = tmp_path / "outside.toml"
    outside.write_text(BASE, encoding="utf-8")
    (project / CONFIG_FILE).unlink()
    (project / CONFIG_FILE).symlink_to(outside)
    commit(project, "chore: a linked configuration")
    summary = tmp_path / "summary.md"
    code, out, err = cli(project, tmp_path, "gate", "--summary", str(summary))
    assert code == 2
    assert CONFIG_FILE in err
    assert out == ""
    assert not summary.exists()
    assert outside.read_text(encoding="utf-8") == BASE


def test_a_gate_the_base_does_not_enforce_passes_with_its_findings_reported(
    tmp_path: Path,
) -> None:
    plan = BASE.replace('["docs"]', '["plan"]')
    project = clone(tmp_path, plan)
    _change(project, plan, agents=OVER_BUDGET)
    code, out, _ = cli(project, tmp_path, "gate", "--only", "docs")
    assert code == 0
    assert out.strip() == "docs: advisory, 2 finding(s)"


def test_the_enforced_gate_fails_on_its_findings(tmp_path: Path) -> None:
    project = clone(tmp_path, BASE)
    _change(project, BASE, agents=OVER_BUDGET)
    code, out, _ = cli(project, tmp_path, "gate", "--only", "docs")
    assert code == 1
    assert out.splitlines()[0] == "docs: enforcing, 2 finding(s)"


def test_a_failing_run_ends_by_saying_where_the_findings_are(tmp_path: Path) -> None:
    # The printed lines are counts, and a first-time user had no pointer to the findings behind
    # them. One fixed line, and only on a run with a failing gate; under `--builtin` it names
    # `assess --builtin --json`, so the command it hands on runs no custom gate either. Mutation
    # (by hand): the line dropped -> the last line is the gate's. Mutation (oracle): "gate
    # --builtin hands on a command that runs the custom gates" -> the `--builtin` run ends with
    # the plain line and this reddens.
    project = clone(tmp_path, BASE)
    _change(project, BASE, agents=OVER_BUDGET)
    code, out, _ = cli(project, tmp_path, "gate", "--only", "docs")
    assert code == 1
    assert out.splitlines() == ["docs: enforcing, 2 finding(s)", FINDINGS_ELSEWHERE]
    code, out, _ = cli(project, tmp_path, "gate", "--builtin", "--only", "docs")
    assert code == 1
    assert out.splitlines()[-2:] == ["docs: enforcing, 2 finding(s)", BUILTIN_FINDINGS_ELSEWHERE]
    _change(project, BASE, agents=AGENTS)
    code, out, _ = cli(project, tmp_path, "gate", "--only", "docs")
    assert (code, out.splitlines()) == (0, ["docs: enforcing, 0 finding(s)"])


def test_a_root_spelled_with_dot_dot_is_refused_for_what_it_is(tmp_path: Path) -> None:
    # `--root ..` from a subdirectory was refused with the symlink sentence, and nothing was
    # linked: `..` after a linked component is not the directory the spelling suggests, so the
    # refusal stays and says why. Mutation (by hand): the check removed -> the symlink sentence.
    project = clone(tmp_path, BASE)
    (project / "sub").mkdir()
    code, out, err = cli(project / "sub" / "..", tmp_path, "gate", "--only", "config")
    assert (code, out) == (2, "")
    assert "`..`" in err and "symlink" not in err


def test_a_name_given_twice_runs_once(tmp_path: Path) -> None:
    project = clone(tmp_path, BASE)
    code, out, _ = cli(project, tmp_path, "gate", "--only", "docs", "--only", "docs")
    assert code == 0
    assert _heads(out) == ["docs"]


def test_a_name_the_configuration_does_not_have_is_refused_and_not_quoted(
    tmp_path: Path,
) -> None:
    # The `--only` list is the caller workflow's, which a pull request can edit. Without the
    # check, `run_gates` raises `KeyError('tset')` and the frame's internal error quotes it on
    # standard error — which is why both streams are read.
    project = clone(tmp_path, BASE)
    code, out, err = cli(project, tmp_path, "gate", "--only", "tset")
    assert code == 2
    assert "tset" not in out
    assert "tset" not in err
    assert "1 gate(s)" in err


def test_on_the_base_commit_the_tree_is_the_base(tmp_path: Path) -> None:
    project = clone(tmp_path, BASE)
    git(project, "checkout", "-q", "main")
    code, out, _ = cli(project, tmp_path, "gate", "--only", "config")
    assert code == 0
    assert out.strip() == "config: stayfixed.toml unchanged from the base"


def test_an_uncommitted_loosening_on_the_base_commit_is_still_refused(tmp_path: Path) -> None:
    # Deliberately uncommitted: the tree is the working tree, never `HEAD`, so a checkout of the
    # base commit is not the base's copy by position alone.
    project = clone(tmp_path, BASE)
    git(project, "checkout", "-q", "main")
    (project / CONFIG_FILE).write_text(LOOSENED, encoding="utf-8")
    code, out, _ = cli(project, tmp_path, "gate", "--only", "config")
    assert code == 1
    assert "stayfixed.enforced" in out


def test_a_base_with_no_copy_at_this_path_lets_the_tree_decide(tmp_path: Path) -> None:
    # The bootstrap, printed in the one spelling the job summary uses too.
    project = clone(tmp_path, BASE, under="sub")
    _change(project, BASE)
    code, out, _ = cli(project, tmp_path, "gate", "--only", "config")
    assert (code, out.strip()) == (0, f"config: {BOOTSTRAP}")


@pytest.mark.parametrize(
    "broken",
    [
        pytest.param(BASE + "\n[bogus]\nx = 1\n", id="unknown-section"),
        pytest.param(BASE + "\n[[broken\n", id="not-toml"),
        # The preset loader's own `Failure`, which the base's wrapper let through unnamed.
        pytest.param(
            BASE.replace("[project]", 'preset = "nosuch"\n\n[project]'), id="unshipped-preset"
        ),
    ],
)
def test_a_base_that_does_not_load_fails_the_run_and_names_the_base_s_copy(
    tmp_path: Path, broken: str
) -> None:
    # The base's copy governs the change, and one that does not load is never the bootstrap:
    # read as "no copy", the tree would decide its own configuration. The tree here is valid,
    # so a message naming the tree's file sends the owner to a file with nothing wrong in it.
    # Mutation (declared): the base's load failure answered as the bootstrap -> exit 0, and
    # every gate runs under the tree's configuration.
    project = clone(tmp_path, broken)
    _change(project, BASE)
    code, out, err = cli(project, tmp_path, "gate")
    assert code == 1
    assert out == ""
    assert "the base's stayfixed.toml" in err
    assert str(project) not in err


def test_a_change_cannot_make_the_base_s_copy_fail_to_load_and_pass(tmp_path: Path) -> None:
    # Both sides load against the tree's disk, so a change can plant what the base's `[paths]`
    # then meets: a symlink on a path only the base names. The base's load refuses, and the
    # refusal fails the run rather than letting the tree judge itself. Mutation (by hand): the
    # base's load wrapped to answer any error as the bootstrap -> exit 0.
    moved = BASE + '\n[paths]\nroadmap = "elsewhere/roadmap.md"\n'
    project = clone(tmp_path, moved)
    (tmp_path / "target").mkdir()
    (project / "elsewhere").symlink_to(tmp_path / "target", target_is_directory=True)
    _change(project, BASE)
    code, out, err = cli(project, tmp_path, "gate")
    assert code == 2
    assert out == ""
    assert "symlink" in err
    # Whose configuration met the link: the tree's `[paths]` does not name it. Mutation
    # (declared): the base's refusal passed through unwrapped -> the base is not named.
    assert "the base's stayfixed.toml" in err


def test_deleting_the_ledger_does_not_switch_an_enforced_bugs_gate_off(tmp_path: Path) -> None:
    # The base enforces `bugs` and has a ledger; the change deletes the ledger and cites an
    # entry file. "No ledger yet" was read off the tree the change wrote, and the gate reported
    # nothing. Mutation: the ledger's own entry (the uninitialised arm answering `[]`).
    enforced = BASE.replace('["docs"]', '["bugs"]')
    project = clone(tmp_path, enforced, also={"src.py": "# see docs/bugs/BR-001.md\n"})
    upstream = tmp_path / "upstream"
    bugs = upstream / "docs" / "bugs"
    bugs.mkdir(parents=True)
    (bugs / "BR-001.md").write_text(
        "---\nid: BR-001\ntitle: t\nstatus: open\nseverity: low\narea: a\nfound: 2026-01-01\n"
        "source:\nfixed_in:\nrelated:\n---\n\nbody\n",
        encoding="utf-8",
    )
    commit(upstream, "chore: a ledger")
    git(project, "fetch", "-q")
    git(project, "reset", "-q", "--hard", "origin/main")
    code, out, _ = cli(project, tmp_path, "gate", "--builtin", "--only", "bugs")
    # With the ledger in place the citation resolves; the stale index is the one finding.
    assert (code, out.splitlines()[1]) == (1, "bugs: enforcing, 1 finding(s)")
    git(project, "rm", "-rq", "docs/bugs")
    commit(project, "chore: drop the ledger")
    code, out, _ = cli(project, tmp_path, "gate", "--builtin", "--only", "bugs", "--json")
    assert code == 1
    # The ledger the base carries, and the citation, which names the identifier as well.
    [bugs] = json.loads(out)["gates"]
    assert (bugs["name"], bugs["count"]) == ("bugs", 3)


def _ledgered(tmp_path: Path, mention: str, *, base: str = "") -> Path:
    """A clone whose base enforces `bugs` (or is `base`), carries entry BR-001 and its index,
    and holds `mention` in `src/a.py`."""
    enforced = base or BASE.replace('["docs"]', '["bugs"]')
    project = clone(tmp_path, enforced, also={"src/a.py": mention})
    upstream = tmp_path / "upstream"
    bugs = upstream / "docs" / "bugs"
    bugs.mkdir(parents=True)
    (bugs / "BR-001.md").write_text(
        "---\nid: BR-001\ntitle: t\nstatus: open\nseverity: low\narea: a\nfound: 2026-01-01\n"
        "source:\nfixed_in:\nrelated:\n---\n\nbody\n",
        encoding="utf-8",
    )
    parser = build_parser(discover_registrars())
    common = ["--root", str(upstream), "--machine", str(tmp_path / "absent.toml")]
    with redirect_stdout(io.StringIO()):
        assert run(["bugs", "index", *common], parser=parser) == 0
    commit(upstream, "chore: a ledger")
    git(project, "fetch", "-q")
    git(project, "reset", "-q", "--hard", "origin/main")
    return project


@pytest.mark.parametrize(
    "mention",
    ["# workaround for BR-001\n", "# nothing about a bug\n"],
    ids=["mentioned", "unmentioned"],
)
def test_deleting_the_ledger_and_its_index_fails_an_enforced_bugs_gate(
    tmp_path: Path, mention: str
) -> None:
    # A change that deletes the ledger: a bare `BR-001` in code and the whole ledger deleted —
    # directory and index — answered "nothing to check" and passed. So did deleting the
    # mentions with it. The base's ledger is one finding, and a mention left behind is another.
    # Mutations (oracle): "the uninitialised arm ignores the base's ledger" reddens both cases;
    # "with no ledger a bare mention is not a finding" reddens `mentioned`.
    project = _ledgered(tmp_path, mention)
    code, out, _ = cli(project, tmp_path, "gate", "--builtin", "--only", "bugs")
    assert (code, out.splitlines()[1]) == (0, "bugs: enforcing, 0 finding(s)"), out
    git(project, "rm", "-rq", "docs/bugs", "docs/bug-reports.md")
    commit(project, "chore: drop the ledger")
    code, out, _ = cli(project, tmp_path, "gate", "--builtin", "--only", "bugs", "--json")
    assert code == 1
    [bugs] = json.loads(out)["gates"]
    assert (bugs["answered"], bugs["count"]) == (True, 2 if "BR-001" in mention else 1)


@pytest.mark.parametrize(
    "mention",
    ["", "# stayfixed:ledger:fixtures\n# workaround for BR-001\n"],
    ids=["mention-removed", "fixtures-marker"],
)
def test_deleting_every_entry_but_keeping_the_directory_fails_an_enforced_bugs_gate(
    tmp_path: Path, mention: str
) -> None:
    # The same deletion in substance as the case above, with one placeholder left in the
    # directory and the index regenerated empty: the ledger was then not "uninitialised", the
    # base was asked nothing, and the enforced gate passed. A file that marks itself as holding
    # sample identifiers passed with the mention kept. Mutation (declared): the base's entries
    # not compared with the tree's -> exit 0.
    project = _ledgered(tmp_path, "# workaround for BR-001\n")
    git(project, "rm", "-q", "docs/bugs/BR-001.md", "docs/bug-reports.md")
    (project / "docs" / "bugs").mkdir(parents=True, exist_ok=True)
    (project / "docs" / "bugs" / ".gitkeep").write_text("", encoding="utf-8")
    (project / "src" / "a.py").write_text(mention, encoding="utf-8")
    parser = build_parser(discover_registrars())
    common = ["--root", str(project), "--machine", str(tmp_path / "absent.toml")]
    with redirect_stdout(io.StringIO()):
        assert run(["bugs", "index", *common], parser=parser) == 0
    commit(project, "chore: empty the ledger")
    code, out, _ = cli(project, tmp_path, "gate", "--builtin", "--only", "bugs")
    assert (code, out.splitlines()[1]) == (1, "bugs: enforcing, 1 finding(s)"), out


def test_a_branch_behind_its_base_is_not_blamed_for_an_entry_the_base_filed_since(
    tmp_path: Path,
) -> None:
    # The legitimate user the append-only rule must not refuse: a colleague files BR-002 on the
    # base after this branch forked, and the branch, fetched but not rebased, deleted nothing.
    # Compared with the base's tip it read as deleting BR-002. A deletion on the same stale
    # branch is still named, and only that one. Mutation (declared): the entries listed at the
    # base's tip -> the first run fails.
    project = _ledgered(tmp_path, "# workaround for BR-001\n")
    upstream = tmp_path / "upstream"
    (upstream / "docs" / "bugs" / "BR-002.md").write_text(
        "---\nid: BR-002\ntitle: t\nstatus: open\nseverity: low\narea: a\nfound: 2026-01-01\n"
        "source:\nfixed_in:\nrelated:\n---\n\nbody\n",
        encoding="utf-8",
    )
    parser = build_parser(discover_registrars())
    with redirect_stdout(io.StringIO()):
        upstream_args = ["--root", str(upstream), "--machine", str(tmp_path / "absent.toml")]
        assert run(["bugs", "index", *upstream_args], parser=parser) == 0
    commit(upstream, "chore: file BR-002")
    git(project, "fetch", "-q")
    code, out, _ = cli(project, tmp_path, "gate", "--builtin", "--only", "bugs")
    assert (code, out.splitlines()[1]) == (0, "bugs: enforcing, 0 finding(s)"), out
    git(project, "rm", "-q", "docs/bugs/BR-001.md", "docs/bug-reports.md")
    (project / "docs" / "bugs").mkdir(parents=True, exist_ok=True)
    (project / "docs" / "bugs" / ".gitkeep").write_text("", encoding="utf-8")
    (project / "src" / "a.py").write_text("", encoding="utf-8")
    with redirect_stdout(io.StringIO()):
        project_args = ["--root", str(project), "--machine", str(tmp_path / "absent.toml")]
        assert run(["bugs", "index", *project_args], parser=parser) == 0
    commit(project, "chore: empty the ledger")
    code, out, _ = cli(project, tmp_path, "bugs", "check", "--base", "refs/remotes/origin/main")
    assert (code, out.strip()) == (
        1,
        "FAIL: 1 ledger problem(s): docs/bugs/BR-001.md [entry-removed]",
    )


def test_a_ledger_moved_by_paths_takes_no_entry_past_the_run_that_enforces_bugs(
    tmp_path: Path,
) -> None:
    # A base that enforces nothing refuses no `[paths]` change, so a change can move the ledger,
    # delete an entry on the way and enforce `bugs` itself. The base's entries were listed at the
    # change's paths, where the base had none: `bugs: enforcing, 0 finding(s)` and exit 0. They
    # are read where the base's own `stayfixed.toml` kept them. Mutation: `mutations/`, "the
    # base's entries are listed at the tree's paths again".
    project = _ledgered(tmp_path, "", base=LOOSENED)
    moved = BASE.replace('["docs"]', '["bugs"]')
    _change(project, moved + '\n[paths]\nbugs = "ledger"\nbug_index = "ledger-index.md"\n')
    git(project, "rm", "-rq", "docs/bugs", "docs/bug-reports.md")
    (project / "ledger").mkdir()
    (project / "ledger" / ".gitkeep").write_text("", encoding="utf-8")
    parser = build_parser(discover_registrars())
    common = ["--root", str(project), "--machine", str(tmp_path / "absent.toml")]
    with redirect_stdout(io.StringIO()):
        assert run(["bugs", "index", *common], parser=parser) == 0
    commit(project, "chore: move the ledger, and lose an entry on the way")
    code, out, _ = cli(project, tmp_path, "gate", "--builtin", "--only", "bugs")
    assert (code, out.splitlines()[1]) == (1, "bugs: enforcing, 1 finding(s)"), out
    code, out, _ = cli(project, tmp_path, "bugs", "check", "--base", "refs/remotes/origin/main")
    assert (code, out.strip()) == (
        1,
        "FAIL: 1 ledger problem(s): ledger/BR-001.md [entry-removed]",
    )


def test_a_project_root_a_change_made_a_symlink_is_refused_before_the_bugs_gate_runs(
    tmp_path: Path,
) -> None:
    # `bugs check --base` finds the base's `stayfixed.toml` where git puts the root, so a change
    # that turns the project's directory into a link to a copy without an entry is judged at the
    # copy, where the base has nothing: that run passes. Under `stayfixed gate` the root is asked
    # about first, and one reached through a symlink is refused before any gate runs, so the
    # deletion cannot pass the workflow. `docs/cli.md` says which of the two does what. Mutation:
    # `mutations/`, "a project root reached through a symlink reads the base at a path it never
    # had".
    enforced = BASE.replace('["docs"]', '["bugs"]')
    project = clone(tmp_path, enforced, under="proj")
    entry = (
        "---\nid: BR-00{n}\ntitle: t\nstatus: open\nseverity: low\narea: a\n"
        "found: 2026-01-01\nsource:\nfixed_in:\nrelated:\n---\n\nbody\n"
    )
    bugs = project / "proj" / "docs" / "bugs"
    bugs.mkdir(parents=True)
    for n in (1, 2):
        (bugs / f"BR-00{n}.md").write_text(entry.format(n=n), encoding="utf-8")
    parser = build_parser(discover_registrars())
    machine = ["--machine", str(tmp_path / "absent.toml")]
    with redirect_stdout(io.StringIO()):
        assert run(["bugs", "index", "--root", str(project / "proj"), *machine], parser=parser) == 0
    commit(project, "chore: a ledger")
    base = git(project, "rev-parse", "HEAD").strip()
    git(project, "mv", "proj", "other")
    (project / "other" / "docs" / "bugs" / "BR-002.md").unlink()
    (project / "other" / "docs" / "bug-reports.md").unlink()
    with redirect_stdout(io.StringIO()):
        assert (
            run(["bugs", "index", "--root", str(project / "other"), *machine], parser=parser) == 0
        )
    (project / "proj").symlink_to("other", target_is_directory=True)
    commit(project, "chore: the project as a link to a copy without BR-002")
    code, out, err = cli(project / "proj", tmp_path, "gate", "--builtin", "--base", base)
    assert code == 2 and "symlink" in err, (out, err)


def test_a_base_branch_outside_its_grammar_is_named_and_never_blamed_on_base(
    tmp_path: Path,
) -> None:
    # With no `--base`, the default is `refs/remotes/origin/<base_branch>`, and a value outside
    # git's branch grammar was refused in `--base`'s words, a flag nobody passed. The loader
    # names the key now, and prints none of the value.
    project = clone(tmp_path, BASE)
    _change(project, BASE + 'base_branch = "main ::error::forged"\n')
    code, out, err = cli(project, tmp_path, "gate")
    assert code == 1
    assert out == ""
    assert "project.base_branch is not a plain branch name" in err
    assert "--base" not in err and "forged" not in err


@pytest.mark.parametrize(
    "given", [("--base", "refs/remotes/origin/absent"), ()], ids=["named", "default"]
)
def test_a_base_the_checkout_lacks_fails_the_run_and_names_the_fix(
    tmp_path: Path, given: tuple[str, ...]
) -> None:
    # The local remedy, for a clone with no origin, is the base branch this tree configures,
    # spelled out as `assess` and `adopt promote` spell it: the refusal once printed a
    # placeholder for it. The loader holds the name to the branch grammar, so it prints as is.
    # `develop`, so neither `main` nor a placeholder passes. Mutation (advisory): `run_gate`
    # passing `branch="main"` to `read_base` -> both cases redden.
    project = clone(tmp_path, BASE)
    _change(project, BASE + 'base_branch = "develop"\n')
    code, _, err = cli(project, tmp_path, "gate", *given)
    assert code == 1
    assert "fetch-depth: 0" in err
    assert "such as refs/heads/develop in a clone with no origin" in err, err


def test_an_unexpected_error_reading_the_base_is_never_the_bootstrap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # "No copy on the base" lets the change decide its own configuration, so nothing reads a
    # failure as it: an error that is neither a failure nor a refusal is the frame's internal
    # error. Mutation (advice): `None` passed to `judge` in place of `read_base`'s answer, as a
    # handler that swallowed the error would -> the loosening is the bootstrap and exits 0.
    project = clone(tmp_path, BASE)
    _change(project, LOOSENED)

    # Whatever keywords `run_gate` passes, so the error is this one and not a `TypeError`.
    def broken(root: Path, base: str, **_: object) -> str | None:
        raise OSError("disk")

    monkeypatch.setattr(rule, "read_base", broken)
    code, _, err = cli(project, tmp_path, "gate", "--only", "config")
    assert code == 2
    assert "internal error: OSError: disk" in err, err


def test_a_short_base_name_is_refused_at_the_parser(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # A tag spelled `origin/main` wins git's lookup of the short name. The parser's own error,
    # so it is read off the real standard error rather than through `_gate`.
    project = clone(tmp_path, BASE)
    parser = build_parser(discover_registrars())
    argv = ["gate", "--root", str(project), "--base", "origin/main"]
    with pytest.raises(SystemExit) as exited:
        run(argv, parser=parser)
    assert exited.value.code == 2
    assert "refs/" in capsys.readouterr().err


def test_a_project_in_a_subdirectory_is_annotated_from_the_repository_s_root(
    tmp_path: Path,
) -> None:
    project = clone(tmp_path, BASE, under="sub")
    _change(project / "sub", LOOSENED)
    code, out, _ = cli(project / "sub", tmp_path, "gate", "--only", "config", "--annotate")
    assert code == 1
    assert "::error file=sub/stayfixed.toml::stayfixed.enforced may not change" in out


def test_what_prints_names_keys_and_rules_and_never_a_value_or_a_detail(tmp_path: Path) -> None:
    project = clone(tmp_path, BASE)
    tree = BASE + '\n[paths]\nbugs = "a-value-we-wrote"\n'
    _change(project, tree, agents="# widget\n\nSee [the notes](a-target-we-wrote.md).\n")
    summary = tmp_path / "summary.md"
    summary.write_text("an earlier step's summary\n", encoding="utf-8")
    code, out, _ = cli(project, tmp_path, "gate", "--annotate", "--summary", str(summary))
    assert code == 1
    written = summary.read_text(encoding="utf-8")
    assert written.startswith("an earlier step's summary\n")
    for text in (out, written):
        assert "paths.bugs" in text
        assert "a-value-we-wrote" not in text
        assert "a-target-we-wrote" not in text
    assert "docs: missing-link" in out


def _upgrade(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, released: bool) -> Path:
    """A base at an older stayfixed pinned to one commit, and a change to the running one pinned
    to `SHA`, with the release tags answering `released` for every commit."""
    older = BASE.replace(f'"{stayfixed.__version__}"', '"0.0.1"')
    project = clone(tmp_path, older + f'\n[ci]\nref = "{"a" * 40}"\n')
    _change(project, BASE + f'\n[ci]\nref = "{SHA}"\n')
    monkeypatch.setattr("stayfixed.release.api.is_released", lambda sha, runner, *, cwd: released)
    return project


def test_an_upgrade_at_a_released_workflow_commit_passes_the_judging_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Dropping `workflow_sha=args.workflow_sha` refuses more, so it is not declared.
    project = _upgrade(tmp_path, monkeypatch, released=True)
    code, out, _ = cli(project, tmp_path, "gate", "--only", "config", "--workflow-sha", SHA)
    assert code == 0, out
    assert out.strip() == "config: 2 change(s), 0 refused"


def test_an_upgrade_at_a_commit_no_release_names_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _upgrade(tmp_path, monkeypatch, released=False)
    code, out, _ = cli(project, tmp_path, "gate", "--only", "config", "--workflow-sha", SHA)
    assert code == 1
    assert "ci.ref" in out


def test_a_local_run_without_the_workflow_sha_refuses_a_moved_pin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # On a branch `stayfixed upgrade` made, the moved pin is vouched for by nothing until
    # `--workflow-sha` names it, and `docs/cli.md` names that flag as the remedy.
    project = _upgrade(tmp_path, monkeypatch, released=True)
    code, out, _ = cli(project, tmp_path, "gate", "--only", "config")
    assert code == 1
    assert "ci.ref" in out
