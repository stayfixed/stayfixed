"""What a gate run hands a person: printed lines, the platform's workflow commands, a job summary.

Every string here can reach a pull request's annotations or its job summary, which a reviewer
reads as stayfixed's own words. So each case holds one of two things: a repository-authored
string (a finding's path outside the grammar a path may print in, a finding's detail) never
reaches them, or the platform's bound (ten annotations per level per step, the rest dropped
without a word) is counted rather than met silently.
"""

from __future__ import annotations

from collections.abc import Iterable

from stayfixed.assess.gates import ALREADY_FAILED, COULD_NOT_RUN, STOPPED, GateResult, stopped
from stayfixed.assess.report import (
    BOOTSTRAP,
    NOT_ON_BASE,
    UNCHANGED,
    GateRun,
    config_line,
    gate_line,
    gate_row,
    summary,
    workflow_commands,
)
from stayfixed.assess.rule import Change, ConfigVerdict, Verdict
from stayfixed.config.loader import preset_defaults
from stayfixed.findings import LISTED_LIMIT, Finding


def _run(
    results: Iterable[GateResult],
    enforcing: Iterable[str],
    changes: Iterable[Change] = (),
    prefix: str = "",
    judged: bool = True,
) -> GateRun:
    verdict = ConfigVerdict(
        "adopting", tuple(changes), preset_defaults("widget"), frozenset(enforcing)
    )
    return GateRun(verdict, tuple(results), judged=judged, prefix=prefix)


def _link(path: str, line: int | None = 1, detail: str = "a link to nowhere") -> Finding:
    return Finding("missing-link", path, line, detail)


def _level(command: str) -> str:
    """`error`, `warning` or `notice`: the word after the leading `::`."""
    return command.removeprefix("::").split("::")[0].split(" ")[0]


def test_a_path_outside_the_printable_grammar_is_annotated_without_a_location() -> None:
    # A committed file's name is anything a contributor chose: a newline and `::error::` in it
    # would forge an annotation of its own, and a space is merely outside the grammar. Both are
    # still annotated, at no location.
    run = _run(
        [GateResult("docs", (_link("a\n::error::forged:b,c%d", 3), _link("docs/My Notes.md")))],
        ["docs"],
    )
    assert workflow_commands(run) == ["::error::docs: missing-link", "::error::docs: missing-link"]


def test_an_advisory_gate_warns_and_an_enforcing_one_errors() -> None:
    run = _run(
        [GateResult("bugs", (_link(""),)), GateResult("docs", (_link(""),))],
        ["docs"],
    )
    assert [_level(line) for line in workflow_commands(run)] == ["warning", "error"]


def test_a_gate_that_could_not_run_is_annotated_at_its_level_with_its_fixed_reason() -> None:
    # A gate that could not judge the tree has no finding, so a pull request would see no
    # annotation for it at all where the run still fails on it. Its reason is stayfixed's own
    # fixed text, never an exception's. Mutation (oracle): `mutations/`'s "a gate that could not run
    # is not annotated" -> both lines are missing.
    reason = COULD_NOT_RUN.format(command="plan check --base <base>")
    run = _run(
        [
            GateResult("plan", (), answered=False, reason=reason),
            GateResult("docs", (), answered=False, reason=reason),
        ],
        ["plan"],
    )
    assert workflow_commands(run) == [f"::error::plan: {reason}", f"::warning::docs: {reason}"]


def test_past_the_cap_one_notice_counts_the_rest() -> None:
    # The platform shows ten annotations per level per step and drops the rest without a word,
    # so a reader who counts eleven lines would think eleven was all.
    run = _run([GateResult("docs", tuple(_link("") for _ in range(13)))], ["docs"])
    lines = workflow_commands(run, cap=10)
    assert len(lines) == 11
    assert lines[-1] == (
        "::notice::3 more error annotation(s) not shown; the job summary counts them all"
    )


def test_refusals_share_the_cap_with_findings() -> None:
    changes = [Change(f"paths.k{n:02}", Verdict.REFUSED) for n in range(12)]
    lines = workflow_commands(_run([], [], changes), cap=10)
    assert [_level(line) for line in lines[:-1]] == ["error"] * 10
    assert lines[-1].startswith("::notice::2 more error annotation(s)")


def test_a_run_that_did_not_judge_annotates_no_refusal() -> None:
    # The custom step runs after the judging step and does not judge: the refusal is that
    # step's to annotate, once. Mutation (advice): `if run.judged:` -> `if True:` in
    # `workflow_commands` -> the refused key is annotated here too, and this reddens. Not
    # declared: a second annotation of a refusal that already failed the run grants nothing.
    run = _run([GateResult("tests", ())], [], [Change("paths.bugs", Verdict.REFUSED)], judged=False)
    assert workflow_commands(run) == []


def test_a_path_is_written_from_the_repository_s_root() -> None:
    # The platform places an annotation by the repository's path, and a project kept in a
    # subdirectory reports paths from its own root.
    run = _run(
        [GateResult("docs", (_link("AGENTS.md", 2),))],
        ["docs"],
        [Change("paths.bugs", Verdict.REFUSED)],
        prefix="sub/",
    )
    assert workflow_commands(run) == [
        "::error file=sub/stayfixed.toml::paths.bugs may not change this way in a pull request",
        "::error file=sub/AGENTS.md,line=2::docs: missing-link",
    ]


def test_a_commit_finding_is_annotated_without_a_file() -> None:
    # A `commit` finding's path is the commit's id, which is inside the grammar. `located_here =
    # True` would annotate a file named after it: a misplaced annotation, not a trust decision,
    # so it is not declared as a mutation.
    run = _run([GateResult("commit", (Finding("attribution", "d" * 40, None, "x"),))], ["commit"])
    assert workflow_commands(run) == ["::error::commit: attribution"]


def test_the_summary_and_the_commands_carry_counts_and_rules_never_a_path_s_detail() -> None:
    detail = "a-detail-we-wrote"
    run = _run(
        [GateResult("docs", (_link("private/path.md", 1, detail),))],
        ["docs"],
        [Change("paths.bugs", Verdict.REFUSED)],
    )
    text = summary(run)
    assert "| docs | enforcing | 1 | fails |" in text
    assert "| paths.bugs | refused |" in text
    assert "private/path.md" not in text
    assert detail not in text
    assert text.endswith("\n")
    assert not [line for line in workflow_commands(run) if detail in line]


def test_the_summary_says_how_the_configuration_was_judged() -> None:
    # Advice, not declared: each branch is fixed text. Mutation: drop `config_line`'s
    # `base_state is None` branch -> the bootstrap reads as "unchanged from the base" and the
    # first assertion reddens.
    bootstrap = GateRun(
        ConfigVerdict(None, (), preset_defaults("widget"), frozenset()), (), judged=True
    )
    assert summary(bootstrap) == f"config: {BOOTSTRAP}\n"
    assert summary(_run([], [])) == f"config: {UNCHANGED}\n"
    unanswered = GateResult("tests", (), answered=False, reason="could not start")
    advisory = _run([unanswered, GateResult("bugs", (_link(""),))], [], judged=False)
    text = summary(advisory)
    assert "| tests | advisory | could not run | would fail |" in text
    assert "| bugs | advisory | 1 | would fail |" in text
    assert "stayfixed.toml" not in text


def test_the_exit_code_counts_only_what_enforces_and_what_the_rule_refused() -> None:
    finding = GateResult("docs", (_link(""),))
    refused = [Change("paths.bugs", Verdict.REFUSED)]
    assert _run([finding], []).exit_code == 0
    assert _run([finding], ["docs"]).exit_code == 1
    assert _run([], [], refused).exit_code == 1
    assert _run([], [], refused, judged=False).exit_code == 0
    assert _run([GateResult("docs", ())], ["docs"], [Change("x", Verdict.NOTED)]).exit_code == 0


def test_a_gate_waiting_for_the_base_is_reported_and_fails_nothing() -> None:
    # A custom gate the base does not have the command of was not run: the summary and the
    # annotations say so, and even one the change enforces fails nothing, because the base
    # enforces no command it lacks. Advice: fixed text, and the exit code holds `blocking`,
    # which reads the results alone.
    run = _run([], ["aaa"])
    waiting = GateRun(run.verdict, (), judged=False, waiting=("aaa",))
    assert summary(waiting) == (
        "| gate | mode | findings | verdict |\n|---|---|---|---|\n"
        f"| aaa | enforcing | not run | {NOT_ON_BASE} |\n"
    )
    assert workflow_commands(waiting) == [f"::warning::aaa: {NOT_ON_BASE}"]
    assert waiting.exit_code == 0


def test_a_gate_not_started_after_the_run_failed_says_so_everywhere_a_gate_prints() -> None:
    # `stayfixed gate` starts no custom gate the base does not enforce once the run has failed.
    # Such a gate judged nothing, so it is not a passing one, and every place a gate prints
    # says it was not run and why, rather than `could not run`, which sends a reader to the
    # gate's own command to look for a fault it does not have. Advice: fixed text; the verdict
    # it stands beside is the failure before it, which reddens the run on its own.
    run = _run([GateResult("policy", (_link(""),)), stopped("lint")], ["policy"])
    assert gate_line(run.results[1], enforcing=False) == f"lint: advisory, {STOPPED}"
    assert gate_row(run.results[1], enforcing=False) == {
        "name": "lint",
        "enforcing": False,
        "answered": False,
        "reason": STOPPED,
        "count": 0,
        "failing": True,
    }
    assert summary(run).splitlines()[3] == f"| lint | advisory | not run | {ALREADY_FAILED} |"
    assert workflow_commands(run)[1] == f"::warning::lint: {STOPPED}"


def test_the_config_line_names_at_most_the_listed_limit_of_refused_keys() -> None:
    # A custom gate's key is the repository's to add, so the refused keys are bounded in number
    # by nothing; the line counts every one and names the first `LISTED_LIMIT`, and the job
    # summary's table below it carries each key's verdict. Mutation (oracle): `mutations/`'s "the
    # config line names every refused key" -> this reddens.
    keys = [f"gates.custom.g{n:02}" for n in range(LISTED_LIMIT + 3)]
    verdict = ConfigVerdict(
        "installed",
        tuple(Change(key, Verdict.REFUSED) for key in keys),
        preset_defaults("widget"),
        frozenset(),
    )
    named = ", ".join(keys[:LISTED_LIMIT])
    assert config_line(verdict) == (
        f"config: {len(keys)} change(s), {len(keys)} refused: {named}, and 3 more"
    )
