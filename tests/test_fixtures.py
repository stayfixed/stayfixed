"""The two fixture projects the smoke workflow runs against, held to what they claim.

`smoke-project` is a project every gate passes on, with `state = "installed"` so the gates
enforce; `hostile-project` is the clone the clone-to-exfiltration scenario runs. Both are read
by CI from this tree, so a fixture that drifted from what a gate accepts would fail the smoke
workflow with a message about the fixture rather than about stayfixed.
"""

from __future__ import annotations

import io
import re
import shutil
import subprocess
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any

import pytest

from stayfixed.cli import build_parser, discover_registrars, run
from tests.declarations import declared
from tests.gitfixture import git, needs_git
from tests.workflow_yaml import load, runs

ROOT = Path(__file__).resolve().parents[1]
SMOKE = ROOT / "tests" / "fixtures" / "smoke-project"
HOSTILE = ROOT / "tests" / "fixtures" / "hostile-project"
PLAN = "docs/plans/2026-09-19-the-fixtures-own-plan.md"


def _copy_as_repository(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    shutil.copytree(SMOKE, root)

    # Two commits, so that `commit check --range HEAD~1..HEAD` checks one message rather than
    # an empty range that proves nothing. The second one touches the fixture's own plan rather
    # than being empty, for the same reason one step further on: `plan check --base HEAD~1`
    # lints the plans that range touches, and a range that touches none exits 0 having linted
    # nothing. `test_plan_check_on_the_fixture_lints_the_plan_it_touched` is what says so.
    git(root, "init", "-q", "-b", "main")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "chore: the fixture")
    plan = root / PLAN
    added = plan.read_text(encoding="utf-8") + "\nA line the second commit adds.\n"
    plan.write_text(added, encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "docs: a second one")
    return root


def _invoke(root: Path, tmp_path: Path, argv: list[str]) -> tuple[int, str]:
    parser = build_parser(discover_registrars())
    flags = ["--root", str(root), "--machine", str(tmp_path / "m.toml")]
    with redirect_stdout(io.StringIO()) as out:
        code = run([*argv, *flags], parser=parser)
    return code, out.getvalue()


@needs_git
@pytest.mark.parametrize(
    "argv",
    [
        ["docs", "check"],
        ["bugs", "check"],
        ["docs", "trail", "--check"],
        ["plan", "check", "--base", "HEAD~1"],
        ["commit", "check", "--range", "HEAD~1..HEAD"],
    ],
    ids=lambda argv: " ".join(argv),
)
def test_every_gate_the_workflow_runs_passes_on_the_smoke_fixture(
    tmp_path: Path, argv: list[str]
) -> None:
    # Mutation: delete `docs/roadmap.md`'s trail marker in the fixture -> `docs trail --check`
    # reddens (measured by hand, not declared: the fixture is data and the oracle mutates
    # source).
    #
    # `--base HEAD~1` and not the default: `plan check` defaults to
    # `refs/remotes/origin/<base_branch>`, and this copy is a fresh repository with no remote,
    # where an unresolvable base is a finding (`docs/cli.md`: "A base that does not resolve is a
    # finding (1), never an OK"). CI's `stayfixed gate` passes the base as the commit it
    # resolved; the fixture's own two commits are the equivalent here.
    root = _copy_as_repository(tmp_path)
    code, printed = _invoke(root, tmp_path, argv)
    assert code == 0, printed


@needs_git
@pytest.mark.parametrize(
    ("argv", "examined"),
    [
        (["bugs", "check"], {"checked": True, "findings": []}),
        (["commit", "check", "--range", "HEAD~1..HEAD"], {"commits": 1, "violations": []}),
        (["docs", "trail", "--check"], {"stale": False}),
    ],
    ids=("bugs check", "commit check", "docs trail --check"),
)
def test_the_gates_on_the_fixture_report_what_they_examined(
    tmp_path: Path, argv: list[str], examined: dict[str, object]
) -> None:
    # The non-vacuity companions for three more of the five rows above, written for the reason
    # the `plan check` one was: `exit 0` is also what a gate that examined nothing produces,
    # and the author closed that for one row and not for the rest. Measured on this tree, each
    # guard torn out on its own and `tests/test_fixtures.py` run:
    #   `ledger/check.py`'s `uninitialised()` -> `return True`, so `bugs check` takes its inert
    #     arm and reports `{"checked": False}` having read no ledger — 30 passed;
    #   `guards/commit.py`'s `commits = commits_in(root, rev_range)` -> `commits = []`, so the
    #     range is empty and the gate says "OK: 0 commit message(s) checked" — 30 passed.
    # The quantity each row is about is what is asserted here, so those two now redden.
    # `docs trail --check` carries `stale` for the same reason; its own guard is held by the
    # hand-measured fixture mutation named above.
    #
    # Mutations (declared): the bug ledger reports itself uninitialised; the commit gate reads
    # an empty range.
    import json

    root = _copy_as_repository(tmp_path)
    code, printed = _invoke(root, tmp_path, [*argv, "--json"])
    assert code == 0, printed
    data = json.loads(printed)
    for key, value in examined.items():
        assert data[key] == value, (key, data)


@needs_git
def test_docs_check_on_the_fixture_reads_the_documents_it_is_about(tmp_path: Path) -> None:
    # The fifth row's companion, and it has to be a planted violation rather than a count:
    # `docs check` reports `findings: []` and the same `OK:` line whether it examined the
    # documents or returned early, so no field of its success answer can tell the two apart.
    # Measured: `check_budgets` and `check_links` in `src/stayfixed/docs/hygiene.py` each given
    # `return []` as their first statement left `tests/test_fixtures.py` 30 green.
    #
    # Two plants and not one, because they are two walks: an always-loaded document blown past
    # its line budget, and a link out of it to a file that is not there.
    #
    # Mutations (declared): the budget walk returns nothing; the link walk returns nothing.
    import json

    root = _copy_as_repository(tmp_path)
    agents = root / "AGENTS.md"
    agents.write_text(
        agents.read_text(encoding="utf-8")
        + "\n[a link to nothing](docs/not-a-file.md)\n"
        + "\nfiller\n" * 2000,
        encoding="utf-8",
    )
    code, printed = _invoke(root, tmp_path, ["docs", "check", "--json"])
    assert code == 1, printed
    rules = {finding["rule"] for finding in json.loads(printed)["findings"]}
    assert "agents-lines" in rules, rules
    assert "missing-link" in rules, rules


@needs_git
def test_plan_check_on_the_fixture_lints_the_plan_it_touched(tmp_path: Path) -> None:
    # The non-vacuity guard for the `plan check` row above, and the reason the fixture's second
    # commit is not empty: `plan check` over a range that touches no plan exits 0 having linted
    # nothing, which is the shape `plans.py`'s own docstring calls "how a gate like this one
    # runs green for its whole life". One plan, named, is what the row is worth.
    root = _copy_as_repository(tmp_path)
    code, printed = _invoke(root, tmp_path, ["plan", "check", "--base", "HEAD~1", "--json"])
    assert code == 0, printed
    assert PLAN in printed, printed


def test_the_smoke_fixture_is_installed_so_the_gates_enforce() -> None:
    import tomllib

    config = tomllib.loads((SMOKE / "stayfixed.toml").read_text(encoding="utf-8"))
    assert config["stayfixed"]["state"] == "installed"
    assert config["project"]["name"] == "smoke"


def test_the_hostile_fixture_carries_the_three_properties_the_scenario_depends_on() -> None:
    # `scripts/smoke_exfiltration.py` asserts that each of these reaches nothing. A fixture
    # that had quietly lost one of them would make every row in that scenario green over a
    # clone that was never hostile, which is the shape this repository keeps finding.
    import json
    import tomllib

    raw = (HOSTILE / "stayfixed.toml").read_text(encoding="utf-8")
    config = tomllib.loads(raw)
    # The literal and not only the loaded value: `installed` is not the loader's default, and
    # a fixture that relied on a default would stop being the hostile case the day it moved.
    assert 'state = "installed"' in raw
    assert config["stayfixed"]["state"] == "installed"
    # The clone names ANOTHER project, which is the whole of the `mismatch` row.
    assert config["project"]["name"] == "smoke"
    assert config["memory"]["mode"] == "in-repo"

    note = (HOSTILE / "docs" / "memory" / "developer" / "canary.md").read_text(encoding="utf-8")
    assert "startup: -1" in note, note
    assert "CANARY-IN-REPO-RULE" in note

    settings = json.loads((HOSTILE / ".claude" / "settings.json").read_text(encoding="utf-8"))
    assert "STAYFIXED_CONFIG" in settings["env"]
    assert "PATH" in settings["env"]


# --- `check.yml`'s base-ref step, run as the shell script it is -------------------------
#
# The repository carries no YAML parser and adds no dependency to check its own prose, so a workflow
# is otherwise proven only by the run that first executes it. The one part of `check.yml` that is
# *logic* rather than platform plumbing is the step that decides which base commit the gates'
# configuration comes from and which project root the gates run in. That step's `run:` body is
# extracted from the shipped file — never retyped here, or the test would hold a copy and the file
# would be free to drift — and run with `bash` against real repositories.

CHECK_WORKFLOW = ROOT / ".github" / "workflows" / "check.yml"
BASE_STEP = "The base ref and the project root"
needs_bash = pytest.mark.skipif(shutil.which("bash") is None, reason="bash is not installed")
# `.github/` is outside `source-include`: it is this repository's own continuous integration
# and not source a downstream packager needs, and `scripts/check_artifacts.py` states that the
# sdist exists so such a packager can run the suite. So the cases below skip where the file
# they are about is not there, rather than the tree gaining a line to ship CI configuration.
# Five cases here really do run `check.yml`'s base step, and `tests/test_check_workflow.py`
# imports this marker for its own, which run the two gate steps.
needs_workflow = pytest.mark.skipif(
    not CHECK_WORKFLOW.is_file(), reason="check.yml is not in the sdist"
)
# And its own marker for the one guard that is not about `check.yml` at all. The tree-wide
# `${{ }}`-in-`run:` scan is the only assertion covering `ci.yml`, `release.yml` and
# `smoke.yml`, and it carried `needs_workflow` — so renaming or deleting `check.yml` would
# have switched off the guard over the other four, silently and green. A guard whose predicate
# is unrelated to what it guards is a guard that will eventually be off without anyone
# deciding it should be.
needs_workflows_dir = pytest.mark.skipif(
    not (ROOT / ".github" / "workflows").is_dir(), reason="the workflows are not in the sdist"
)


CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
needs_ci_workflow = pytest.mark.skipif(
    not CI_WORKFLOW.is_file(), reason="ci.yml is not in the sdist"
)
CONTRIBUTING = ROOT / "CONTRIBUTING.md"
PR_TEMPLATE = ROOT / ".github" / "pull_request_template.md"
_SHORT_VERSION = re.compile(
    r"^## The short version\n.*?^```bash\n(.*?)^```", re.MULTILINE | re.DOTALL
)
_TEMPLATE_BLOCK = re.compile(r"^## Verification\n.*?^```\n(.*?)^```", re.MULTILINE | re.DOTALL)
# The release's first step, "be on `main`, current, and green": a list item, so its block is
# indented under the item.
_RELEASE_BLOCK = re.compile(
    r"^1\. \*\*Be on `main`, current, and green\.\*\*.*?^   ```bash\n(.*?)^   ```",
    re.MULTILINE | re.DOTALL,
)
RELEASING = ROOT / "RELEASING.md"
# The release check, in the one spelling five places hold: the three blocks and `ci.yml` below,
# and `release.yml` (`test_the_release_workflow_runs_the_release_check_in_the_one_spelling`).
RELEASE_CHECK = "uv run python scripts/release.py check"
_COVERAGE_FLOOR = re.compile(r"--cov-fail-under=(\d+)")


@needs_ci_workflow
def test_the_block_a_contributor_copies_is_the_one_ci_runs() -> None:
    """The two blocks a contributor runs before pushing, against what CI actually runs.

    They listed five commands and CI ran seven: no coverage floor on the `pytest` line while
    `ci.yml` fails below 92%, and no mutation oracle at all — the project's headline
    obligation, missing from the one block a contributor copies. A contributor who followed
    `CONTRIBUTING.md` exactly got a green tree and a red pull request, twice over.

    Bound rather than restated: the floor is read out of `ci.yml`'s own `pytest` invocation, so
    raising it in CI reddens here until both documents move with it.
    """
    # Mutation: drop the mutation-oracle line from `CONTRIBUTING.md`'s block -> reddens naming
    # it. The floor first: a `run:` walk that returned nothing would satisfy every `in` below
    # by making `ci` the empty string.
    bodies = scripts(CI_WORKFLOW.read_text(encoding="utf-8"))
    assert bodies, "ci.yml runs no script"
    ci = "\n".join(bodies)
    floor = _COVERAGE_FLOOR.search(ci)
    assert floor is not None, "ci.yml no longer runs pytest with a coverage floor"

    blocks = {}
    match = _SHORT_VERSION.search(CONTRIBUTING.read_text(encoding="utf-8"))
    assert match is not None, "CONTRIBUTING.md has no `## The short version` bash block"
    blocks["CONTRIBUTING.md"] = match.group(1)
    match = _TEMPLATE_BLOCK.search(PR_TEMPLATE.read_text(encoding="utf-8"))
    assert match is not None, "the pull-request template has no `## Verification` block"
    blocks[".github/pull_request_template.md"] = match.group(1)
    # The release's own check ran the suite in one process and left the oracle out: a third
    # copy of the list, and the one run last before a tag. Mutation (by hand): drop `-n auto`
    # from `RELEASING.md`'s `pytest` line -> reddens naming it.
    match = _RELEASE_BLOCK.search(RELEASING.read_text(encoding="utf-8"))
    assert match is not None, "RELEASING.md's first step has no bash block"
    blocks["RELEASING.md"] = match.group(1)

    # Every gate the contributor is asked to run locally, in the spelling CI runs it in.
    # `pytest -n auto` among them, the suite across workers. Mutation: drop `-n auto` from
    # `ci.yml`'s `pytest` line -> reddens naming it.
    required = (
        "pytest -n auto",
        f"--cov-fail-under={floor.group(1)}",
        "scripts/mutation_oracle.py",
        "ruff check .",
        "ruff format --check .",
        "mypy",
        RELEASE_CHECK,
    )
    for name, text in blocks.items():
        assert text.strip(), name
        missing = [gate for gate in required if gate not in text]
        assert missing == [], (name, missing)
        # And each one is really a gate CI runs, so the block cannot drift into naming a
        # command nobody checks.
        assert all(gate in ci for gate in required), [g for g in required if g not in ci]
    # A gate CI runs and then excuses is a gate in name only: `uv run mypy || true` carries the
    # spelling every check above reads and lets the step pass whatever mypy found. Mutation
    # (declared): `mutations/`'s "ci lets a failed type check through" -> reddens.
    excused = [
        line for line in ci.splitlines() if any(gate in line for gate in required) and "||" in line
    ]
    assert excused == [], excused


ORACLE_COMMAND = "scripts/mutation_oracle.py"
ORACLE_JOB = "oracle"
# Measured on the `oracle` job's own run of 2026-10-08: 719 s for the 1,869 entries `mutations/`
# held that day, four jobs on `ubuntu-latest` against a warm bytecode cache. It was 173 s for 566
# on an earlier run, 0.31 s an entry, and 751 s for 372 while the oracle ran one entry at a time
# and compiled from source on every run. Re-measure it from that job's runs; it is here as a
# number rather than as prose so that the budget below is checked rather than described.
ORACLE_SECONDS_PER_ENTRY = 719 / 1869
# Checkout, `setup-uv` against a warm cache and `uv sync --locked` — the whole of the job that
# is not the oracle itself. Estimated from the 128 s of non-oracle work in `checks` on the same
# runner, which also carries lint, types, the test run, the build and a wheel install.
ORACLE_SETUP_SECONDS = 60
# The runner-variance allowance the job's own comment in `ci.yml` reserves: a nominally 889 s job
# was cancelled at 918 s, about 30 s of slip, and this doubles it. Projected without it, this test
# stayed green some thirty entries past the point that comment says to raise the budget.
ORACLE_VARIANCE_SECONDS = 60


def _ci_jobs() -> dict[str, list[str]]:
    """Every job in `ci.yml`, as the raw lines underneath it.

    Indentation arithmetic over the raw lines, where `tests.workflow_yaml` reads mappings: the
    question below is which job's body names a command anywhere, a comment included. A job is a
    key at indent 2 under `jobs:` that ends in a colon; everything until the next one belongs to
    it.
    """
    jobs: dict[str, list[str]] = {}
    current: str | None = None
    inside = False
    for line in CI_WORKFLOW.read_text(encoding="utf-8").splitlines():
        if line.rstrip() == "jobs:":
            inside = True
            continue
        if not inside:
            continue
        bare = line.lstrip()
        opens_job = len(line) - len(bare) == 2 and line.rstrip().endswith(":")
        if bare and not bare.startswith("#") and opens_job:
            current = line.strip().rstrip(":")
            jobs[current] = []
            continue
        if current is not None:
            jobs[current].append(line)
    return jobs


@needs_ci_workflow
def test_the_mutation_oracle_has_a_job_of_its_own_with_a_budget_that_fits() -> None:
    """The oracle runs once, in a job nothing can skip, under a bound that fits the set.

    It used to be a step of `checks`, where it was 76% of the job: 751 s of 879 s on Linux
    against a 900 s bound, on all four configurations at once, and the branch that took
    `mutations/` past 380 entries took `checks (macos-latest, 3.13)` over the bound. Running
    it on one configuration was necessary and not sufficient — `timeout-minutes` is a per-job
    bound, so paying once instead of four times gave 751 s back to the three configurations that
    stopped running it and nothing to the one that still did.

    **Three things are asserted, and each is a way this has already gone wrong or could go
    quiet.** That exactly one job runs the oracle, because a second copy would pay twice again
    and a zeroth would be the set silently switched off. That the job carries no `if:` and no
    `strategy:`, because a skipped job reports as green — the "reads as coverage" failure in the
    costume of a condition — and because a matrix would reintroduce the multiplication. And that
    the budget still fits the set it has to prove.

    **The budget assertion is the one that earns its place.** The oracle grows by construction:
    the rule is that every new assertion ships with the mutation that reddens it, so the entry
    count only goes up, at about four tenths of a second each on four CPUs. Projecting the cost from
    the live entry count means the next branch to outgrow the bound reddens *here*, in a
    contributor's own test run, rather than as a cancelled job minutes into CI. That is the whole
    difference between arithmetic somebody can act on and arithmetic somebody discovers.

    No mutation travels with `ORACLE_SECONDS_PER_ENTRY` itself: lowering it weakens the
    projection without reddening anything, so there is nothing for an entry to catch. It is a
    measurement, and the comment beside it says to re-measure it from this job's own runs.
    """
    # Mutations (declared): the budget cut below the projection; the job given an `if:` that can
    # skip it. Both redden this case.
    jobs = _ci_jobs()
    # The walk first: an empty reading would make every "exactly one" below come out zero for a
    # reason that is not about the workflow.
    assert len(jobs) >= 2, jobs
    holding = [name for name, body in jobs.items() if any(ORACLE_COMMAND in x for x in body)]
    assert holding == [ORACLE_JOB], holding

    body = jobs[ORACLE_JOB]
    skippable = [x for x in body if x.strip().startswith("if:")]
    assert skippable == [], (
        f"the {ORACLE_JOB!r} job can be skipped, and a skipped job reports as a green check",
        skippable,
    )
    multiplied = [x for x in body if x.strip().startswith(("strategy:", "matrix:"))]
    assert multiplied == [], (
        f"the {ORACLE_JOB!r} job runs a matrix, which is the four-fold cost this shape removed",
        multiplied,
    )

    bounds = [x for x in body if x.strip().startswith("timeout-minutes:")]
    assert len(bounds) == 1, bounds
    budget = int(bounds[0].split(":", 1)[1].strip()) * 60
    entries = len(declared())
    assert entries > 0, "mutations/ declares nothing, so this projects no cost at all"
    projected = entries * ORACLE_SECONDS_PER_ENTRY + ORACLE_SETUP_SECONDS + ORACLE_VARIANCE_SECONDS
    assert budget >= projected, (
        f"{entries} mutation entries project ~{projected:.0f} s against a {budget} s bound — "
        f"raise `timeout-minutes` on the {ORACLE_JOB!r} job, and say in the comment what the "
        "new number buys in entries",
        budget,
        projected,
    )


WORKFLOWS = ROOT / ".github" / "workflows"
# The workflows that run a shell, so the walk below cannot pass by reading nothing: each holds a
# script. `smoke-release.yml` is two reusable-workflow calls and legitimately runs none.
SCRIPTED = {"ci.yml", "check.yml", "release.yml", "smoke.yml"}


def scripts(text: str) -> list[str]:
    """Every step script in a workflow, read by `tests.workflow_yaml`'s strict reader, which reads
    the whole file or refuses the first line outside its subset — so a script cannot be cut short
    or passed over, and a step spelled as a flow mapping, `- {"run":"…"}`, is refused rather
    than read as no step. `defaults: run:` is a mapping of settings, not a script, and is not
    one."""
    return [run for run in runs(load(text)) if isinstance(run, str)]


def spliced(text: str) -> list[str]:
    """The scripts in a workflow that carry a `${{ }}` expression."""
    return [script for script in scripts(text) if "${{" in script]


@needs_workflows_dir
def test_no_workflow_splices_an_expression_into_a_shell() -> None:
    # The one class of workflow defect a text scan can catch, and the one worth catching: a
    # `${{ }}` inside a `run:` is interpolated by the platform before the shell sees the script,
    # so a ref name, a branch name or a pull-request title that carries shell metacharacters
    # runs as the workflow's own code. Every value in these files reaches a shell through
    # `env:` instead. Mutation (oracle): `mutations/`'s "a workflow splices an expression into a
    # shell" puts one into `check.yml`'s checkout assertion.
    #
    # `*.y*ml`: the platform reads `.yaml` too, and a workflow added with the other spelling
    # would never be read while the `>=` assertion below went on passing.
    workflows = sorted(WORKFLOWS.glob("*.y*ml"))
    assert {p.name for p in workflows} >= SCRIPTED, workflows
    for workflow in workflows:
        text = workflow.read_text(encoding="utf-8")
        assert scripts(text) or workflow.name not in SCRIPTED, workflow.name
        assert spliced(text) == [], (workflow.name, spliced(text))


def test_an_expression_is_found_in_every_spelling_of_a_script(tmp_path: Path) -> None:
    # The check above is only as good as what it reads: a script in each spelling the reader
    # takes, each carrying an expression, is found, and one kept in `env:` is not. Mutation
    # (oracle): `mutations/`'s "the expression check reads no script" -> nothing is found and this
    # reddens.
    text = (
        "jobs:\n"
        "  one:\n"
        "    steps:\n"
        "      - run: |\n"
        "          echo block ${{ github.actor }}\n"
        "        env:\n"
        "          SAFE: ${{ github.sha }}\n"
        "      - run: echo inline ${{ github.job }}\n"
        "      - name: with a name of its own\n"
        "        run: echo named ${{ github.workflow }}\n"
        '      - run: "echo quoted ${{ github.head_ref }}"\n'
        "      - run: echo clean\n"
    )
    found = spliced(text)
    assert [script.split()[1] for script in found] == ["block", "inline", "named", "quoted"]
    assert all("SAFE" not in script for script in found)


def step_script(workflow: Path, step_name: str) -> str:
    """The named step's script, straight out of the shipped file.

    Read by `tests.workflow_yaml`'s strict reader, which reads the whole file or fails: the
    line reader this replaced looked for `run: |` from the step's name to the end of the file,
    so a step whose script was spelled another way handed back the next step's, and a case
    about one step ran another. Exactly one step of that name, in any job, and it has a script.
    """
    document = load(workflow.read_text(encoding="utf-8"))
    assert isinstance(document, dict), document
    jobs = document.get("jobs")
    assert isinstance(jobs, dict), jobs
    found = [
        step
        for job in jobs.values()
        if isinstance(job, dict) and isinstance(job.get("steps"), list)
        for step in job["steps"]  # type: ignore[union-attr]
        if isinstance(step, dict) and step.get("name") == step_name
    ]
    assert len(found) == 1, (step_name, found)
    script = found[0].get("run")
    assert isinstance(script, str), (step_name, found[0])
    # No `${{ }}` may survive into the script: every value the step uses arrives through
    # `env:`, and one spliced into `run:` would be a command injection the test would run.
    assert "${{" not in script, script
    return script if script.endswith("\n") else script + "\n"


def test_a_step_s_script_is_never_read_from_the_step_after_it(tmp_path: Path) -> None:
    # The cases that run `check.yml`'s steps name a step and get its script. A reader that
    # searched onward for `run: |` handed back the next step's script for a step spelled with a
    # one-line `run:`, so a case about the first step ran the second. The strict reader gives
    # each step its own.
    workflow = tmp_path / "two.yml"
    workflow.write_text(
        "jobs:\n"
        "  one:\n"
        "    steps:\n"
        "      - name: first\n"
        "        run: echo first\n"
        "      - name: second\n"
        "        run: |\n"
        "          echo second\n",
        encoding="utf-8",
    )
    assert step_script(workflow, "first") == "echo first\n"
    assert step_script(workflow, "second") == "echo second\n"


def _project_with_a_base(tmp_path: Path, *, on_base: str | None) -> Path:
    """A clone whose `origin/main` carries `on_base` as `stayfixed.toml`, or carries none.

    The upstream also has a branch `a-branch-the-author-pushed`, so the clone tracks it: the
    disagreement case then meets a `base:` naming a branch that exists, which is the attack,
    and not a missing ref that fails for another reason. Measured when the case was written:
    with the branch absent the step with its refusal removed still exits 1, "not in this
    checkout"; with it present it exits 0.
    """
    upstream = tmp_path / "upstream"
    upstream.mkdir()
    git(upstream, "init", "-q", "-b", "main")
    (upstream / "README.md").write_text("# a project\n", encoding="utf-8")
    if on_base is not None:
        (upstream / "stayfixed.toml").write_text(on_base, encoding="utf-8")
    git(upstream, "add", "-A")
    git(upstream, "commit", "-qm", "chore: base")
    git(upstream, "branch", "a-branch-the-author-pushed")
    project = tmp_path / "project"
    git(tmp_path, "clone", "-q", str(upstream), str(project))
    return project


def _run_base_step(
    project: Path, tmp_path: Path, **environment: str
) -> tuple[int, dict[str, str], str]:
    output = tmp_path / "github-output"
    output.write_text("", encoding="utf-8")
    done = subprocess.run(
        ["bash", "-e", "-c", step_script(CHECK_WORKFLOW, BASE_STEP)],
        cwd=project,
        capture_output=True,
        text=True,
        check=False,
        env={
            # The step runs no interpreter: git and the shell's own builtins are all it needs.
            "PATH": "/usr/bin:/bin:/usr/local/bin",
            "GITHUB_OUTPUT": str(output),
            "INPUT_BASE": "",
            "INPUT_PATH": ".",
            "PR_BASE": "",
            "DEFAULT_BRANCH": "",
            **environment,
        },
    )
    emitted = output.read_text(encoding="utf-8").splitlines()
    written = dict(line.split("=", 1) for line in emitted if "=" in line)
    return done.returncode, written, done.stdout + done.stderr


INSTALLED = '[stayfixed]\nversion = "0.1.0"\nstate = "installed"\n\n[project]\nname = "p"\n'


def _main(project: Path) -> str:
    """The commit the clone's remote-tracking `main` names: the base every case expects."""
    return git(project, "rev-parse", "refs/remotes/origin/main").strip()


@needs_git
@needs_bash
@needs_workflow
def test_a_tag_named_like_the_tracking_branch_does_not_choose_the_base(tmp_path: Path) -> None:
    """git resolves a short `origin/main` through `refs/tags/` before `refs/remotes/`, and
    `fetch-depth: 0` fetches every tag, so whoever may push a tag of that name would choose the
    configuration every pull request is judged against. The step resolves the fully qualified
    tracking ref, once, and every later read uses the commit it wrote.

    Mutation (declared): the short `origin/$base^{commit}` in place of the qualified name ->
    `base_sha` is the tag's commit.
    """
    project = _project_with_a_base(tmp_path, on_base=INSTALLED)
    (project / "stayfixed.toml").write_text(
        INSTALLED.replace('state = "installed"', 'state = "initialised"'), encoding="utf-8"
    )
    git(project, "add", "-A")
    git(project, "commit", "-qm", "chore: loosen")
    git(project, "tag", "origin/main")
    git(project, "checkout", "-q", "--detach", "HEAD~1")
    code, written, printed = _run_base_step(project, tmp_path, PR_BASE="main")
    assert code == 0, printed
    assert written["base_sha"] == _main(project), (written, printed)
    assert written["base_sha"] != git(project, "rev-parse", "refs/tags/origin/main").strip()


@needs_git
@needs_bash
@needs_workflow
def test_a_base_input_that_disagrees_with_the_pull_requests_own_base_is_refused(
    tmp_path: Path,
) -> None:
    """The caller's `base:` may not choose the configuration a pull request is judged against.

    On a `pull_request` event the platform runs the workflow file from the merge commit — the
    author's copy — and `with: base:` lives in it. So a pull request could point `base:` at a
    branch it had pushed, whose `stayfixed.toml` enforces nothing, and be judged against that
    without touching the tree's own `stayfixed.toml`.

    The platform's `github.base_ref` is the answer that cannot be written from the branch, so
    where both are present and they disagree the step refuses, and never echoes the author's
    value, which has not been validated and could carry a workflow command of its own. This
    costs a legitimate caller nothing: on a pull request `base:` decides nothing anyway, which
    the agreeing case below is here to keep true.

    Mutation (declared): the disagreement test is removed -> this reddens on the exit code.
    """
    project = _project_with_a_base(tmp_path, on_base=INSTALLED)
    code, written, printed = _run_base_step(
        project, tmp_path, INPUT_BASE="a-branch-the-author-pushed", PR_BASE="main"
    )
    assert code == 1, printed
    assert "this pull request's base is 'main'" in printed, printed
    assert "a-branch-the-author-pushed" not in printed, printed
    # Nothing was written, so no later step can read a base commit from this run.
    assert written == {}, written

    # Agreeing is not refused, and `base:` still decides on every event that reports no base —
    # which is what makes the refusal free.
    code, written, printed = _run_base_step(project, tmp_path, INPUT_BASE="main", PR_BASE="main")
    assert code == 0, printed
    assert written["base_sha"] == _main(project), written


@needs_git
@needs_bash
@needs_workflow
def test_the_base_ref_falls_back_to_the_pull_requests_base_and_then_the_default_branch(
    tmp_path: Path,
) -> None:
    # The three anchors, in the order the workflow reads them, and none of them is the tree
    # under review: the caller's `with:`, the pull request's base as the platform reports it,
    # and the repository's default branch. With none of the three the step refuses rather than
    # guessing a branch name.
    project = _project_with_a_base(tmp_path, on_base=INSTALLED)
    _code, written, _printed = _run_base_step(project, tmp_path, PR_BASE="main")
    assert written["base_sha"] == _main(project), written
    _code, written, _printed = _run_base_step(project, tmp_path, DEFAULT_BRANCH="main")
    assert written["base_sha"] == _main(project), written
    code, written, printed = _run_base_step(project, tmp_path)
    assert code == 1, printed
    assert "no base ref" in printed, printed
    assert written == {}, written


@needs_git
@needs_bash
@needs_workflow
def test_a_path_input_cannot_write_the_steps_own_outputs(tmp_path: Path) -> None:
    # `p` is appended to `$GITHUB_OUTPUT`, which the runner parses line by line, so a `path:`
    # carrying a newline would write further `key=value` lines — and `base_sha` is the commit
    # whose configuration governs the gates. A forged one would choose it.
    project = _project_with_a_base(tmp_path, on_base=INSTALLED)
    code, written, printed = _run_base_step(
        project, tmp_path, INPUT_BASE="main", INPUT_PATH=f"sub\nbase_sha={'0' * 40}"
    )
    assert code == 1, printed
    assert "must be a plain relative path" in printed, printed
    assert written == {}, written
    # And the other half of the same check, so `root=` below stays inside the checkout.
    code, written, printed = _run_base_step(
        project, tmp_path, INPUT_BASE="main", INPUT_PATH="../elsewhere"
    )
    assert code == 1, printed
    assert "must not leave the checkout" in printed, printed
    assert written == {}, written


@needs_git
@needs_bash
@needs_workflow
def test_a_project_root_below_the_checkout_is_where_the_gates_run(tmp_path: Path) -> None:
    # The `path:` input, which is what the smoke workflow and a monorepo use. It reaches the
    # shell through `env:` and is used as a path prefix, never as a command.
    project = _project_with_a_base(tmp_path, on_base=None)
    code, written, printed = _run_base_step(
        project, tmp_path, INPUT_BASE="main", INPUT_PATH="./sub/project/"
    )
    assert code == 0, printed
    assert written["root"] == "project/sub/project", written


SMOKE_RELEASE = WORKFLOWS / "smoke-release.yml"
CALLED = "stayfixed/stayfixed/.github/workflows/check.yml"


@pytest.mark.skipif(not SMOKE_RELEASE.is_file(), reason="smoke-release.yml is not in the sdist")
def test_the_release_smoke_calls_the_release_this_tree_carries() -> None:
    """RELEASING.md's last step dispatches this workflow at every release, and `uses:` takes no
    expression, so the tag it calls is written out and moved by hand in the release commit.

    Held to the version the tree carries, which the release workflow's own suite run checks at
    the tag: a stale tag smokes the release before, and one past the tree names a tag that does
    not exist yet, so the dispatch fails at creation for want of a ref. The alias a `1.x`
    release moves is not called here: a `0.x` release has none, and a job naming a tag that
    does not exist fails the whole dispatch before any job runs. Mutation (declared): the
    release job calls `@v1` again.
    """
    import stayfixed

    document = load(SMOKE_RELEASE.read_text(encoding="utf-8"))
    assert isinstance(document, dict) and isinstance(document["jobs"], dict), document
    uses = {
        name: job.get("uses") for name, job in document["jobs"].items() if isinstance(job, dict)
    }
    assert uses == {
        "at-the-development-branch": f"{CALLED}@dev",
        "at-the-release": f"{CALLED}@v{stayfixed.__version__}",
    }, uses


RELEASE_WORKFLOW = WORKFLOWS / "release.yml"
GATE_JOB = "environment-gate"
GATE_STEP = "The pypi environment is a gate and not a name GitHub invented"
needs_release_workflow = pytest.mark.skipif(
    not RELEASE_WORKFLOW.is_file(), reason="release.yml is not in the sdist"
)


def _release_jobs() -> dict[str, dict[str, Any]]:
    """Every job in `release.yml`, as `tests.workflow_yaml`'s strict reader reads it.

    It reads the whole file or fails, so `needs:` is the list it says and a membership test on it
    is exact: a line reader that kept `needs:` as the text `[build, environment-gate-legacy]`
    passed a substring test for `environment-gate`. The callers below still assert the walk found
    something rather than trusting it to have.
    """
    document = load(RELEASE_WORKFLOW.read_text(encoding="utf-8"))
    assert isinstance(document, dict) and isinstance(document["jobs"], dict), document
    return {name: dict(job) for name, job in document["jobs"].items() if isinstance(job, dict)}


def _needs(job: dict[str, Any]) -> list[str]:
    """A job's `needs:`, one name or a list of them, as the list the platform reads."""
    needs = job.get("needs", [])
    return [needs] if isinstance(needs, str) else list(needs)


def _gate_environment() -> str:
    """The environment name the gate step reads, out of its own `env:` block."""
    text = RELEASE_WORKFLOW.read_text(encoding="utf-8")
    match = re.search(r"^\s+ENVIRONMENT: (\S+)$", text, re.M)
    assert match is not None
    return match.group(1)


@needs_release_workflow
def test_the_release_workflow_runs_the_release_check_in_the_one_spelling() -> None:
    # The fifth place: the release workflow runs the check against the tag, and it runs no
    # mypy and no oracle, so it is held to this one gate rather than to the contributor's list.
    # Its spelling had moved with the other four only because one commit moved all five.
    # The whole command line, not a substring of it: `… check --tag "$GITHUB_REF_NAME" || true`
    # carries the spelling and lets a failed check through, and so would a second command after
    # a `;`. Mutation (declared): `release.yml` runs the command the CLI used to ship -> reddens;
    # and `mutations/`'s "the release workflow lets a failed release check through" -> reddens.
    bodies = scripts(RELEASE_WORKFLOW.read_text(encoding="utf-8"))
    assert bodies, "release.yml runs no script"
    checks = [body.strip() for body in bodies if RELEASE_CHECK in body]
    assert checks == [f'{RELEASE_CHECK} --tag "$GITHUB_REF_NAME"'], checks
    # And no step runs the commands the CLI used to ship, beside the one above or instead of it:
    # the line above filters to steps that already carry the new spelling, so a second step with
    # the old one passed it. Mutation (declared): `mutations/`'s "the release workflow builds
    # after running the release check the CLI no longer ships".
    for body in bodies:
        assert "stayfixed release" not in body, body


@needs_release_workflow
def test_every_job_behind_the_pypi_environment_waits_for_the_environment_gate() -> None:
    """The property, stated over the file rather than over two hand-kept copies of a step.

    GitHub auto-creates an environment a job names and the repository lacks, with no protection
    rules on it, so `environment: pypi` is a gate only if something checked. What has to hold is
    not "the gate job exists" but "no job that names the environment can start before it", and
    that has to keep holding for the third such job nobody has written yet. Mutation (declared):
    point the gate's `ENVIRONMENT` at another name -> the equality below reddens, so the gate
    cannot end up checking a name no job uses.
    """
    jobs = _release_jobs()
    assert GATE_JOB in jobs, sorted(jobs)
    gated = {name: job["environment"] for name, job in jobs.items() if "environment" in job}
    # The non-vacuity guard: a walk that found no `environment:` at all would satisfy every
    # assertion below by having nothing to check.
    assert len(gated) >= 2, gated
    assert set(gated.values()) == {_gate_environment()}, (gated, _gate_environment())
    for name in gated:
        assert GATE_JOB in _needs(jobs[name]), (name, jobs[name])
    # And the gate itself is not behind the environment it is asking about: it has to run in
    # the one case the environment asks nobody, which is the case it exists for.
    assert "environment" not in jobs[GATE_JOB], jobs[GATE_JOB]


def _run_gate(tmp_path: Path, gh: str, declared: str = "") -> tuple[int, str]:
    """The shipped gate script, out of the shipped file, against a `gh` that answers `gh`."""
    stub = tmp_path / "bin"
    stub.mkdir(exist_ok=True)
    (stub / "gh").write_text(f"#!/bin/sh\n{gh}\n", encoding="utf-8")
    (stub / "gh").chmod(0o755)
    done = subprocess.run(
        ["bash", "-e", "-o", "pipefail", "-c", step_script(RELEASE_WORKFLOW, GATE_STEP)],
        capture_output=True,
        text=True,
        check=False,
        env={
            "PATH": f"{stub}:/usr/bin:/bin",
            "GH_TOKEN": "t",
            "REPOSITORY": "owner/repository",
            "ENVIRONMENT": _gate_environment(),
            "DECLARED": declared,
        },
    )
    return done.returncode, done.stdout + done.stderr


@needs_bash
@needs_release_workflow
@pytest.mark.parametrize(
    ("gh", "declared", "code", "wanted"),
    [
        ("echo 2", "", 0, "2 protection rule(s)"),
        # The case the gate exists for: GitHub made the environment up on the spot.
        ("echo 0", "", 1, "no protection rules"),
        ("echo 0", "true", 1, "no protection rules"),
        # Unreadable — an endpoint the default token may not be allowed, or no `gh` at all.
        ("echo denied >&2; exit 1", "", 1, "could not be read"),
        ("echo denied >&2; exit 1", "true", 0, "stands in for the read"),
        ("echo denied >&2; exit 1", "false", 1, "could not be read"),
        # A body that is not a count is not a count, and `[ "$x" -eq 0 ]` would have died on it.
        ("echo null", "", 1, "could not be read"),
    ],
    ids=["two-rules", "no-rules", "no-rules-declared", "unreadable", "declared", "denied", "null"],
)
def test_the_gate_admits_a_release_only_where_the_environment_is_one(
    tmp_path: Path, gh: str, declared: str, code: int, wanted: str
) -> None:
    """Nothing here can run GitHub Actions, so the script is run instead, exactly as shipped.

    The two rows that matter are `no-rules-declared` and `declared`, and they are the whole of
    what the repository variable is allowed to do: it stands in for the **read** when the
    endpoint is closed to the token, and it does not answer for an environment that read back
    with zero rules. Mutations (declared): stop testing the count for zero; let the variable be
    consulted before the read has failed.
    """
    got, printed = _run_gate(tmp_path, gh, declared)
    assert got == code, (got, printed)
    assert wanted in printed, printed
