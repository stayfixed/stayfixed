"""`check.yml`'s one job, held to its shape and its two gate steps run as the scripts they are.

The repository carries no YAML parser, so the file is read by `tests.workflow_yaml`, one strict
reader that returns the whole document or fails naming the line it cannot read, and each gate
step's script is taken from it by `step_script` and run with `bash` in a workspace laid out as
the runner lays it out — the caller's checkout at `project/`, against a real clone, with the
real `stayfixed gate`. Only the two checkouts and `setup-python` are the platform's and are not
run here; the base step's own cases are in `tests/test_fixtures.py`.

**What the judging step must hold.** It is the step whose exit status is the verdict, so it runs
no command the repository wrote (`--builtin`) and imports nothing from the working directory or a
user site directory (`python3 -P -s`), it judges the configuration whatever `only:` names, and it
may not fail quietly. The project's own gates run in the next step, and only after it passed.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

import stayfixed
from stayfixed.config.loader import CONFIG_FILE
from tests import scriptload
from tests.assess.baserepo import clone, commit
from tests.floor import floor_env
from tests.gitfixture import git, needs_git
from tests.ownerhome import checkout_with_owner_home
from tests.test_fixtures import (
    CHECK_WORKFLOW,
    needs_bash,
    needs_workflow,
    step_script,
)
from tests.workflow_yaml import Node, load

JUDGE = "The configuration and the built-in gates"
CUSTOM = "The project's own gates"
PROOF = "stayfixed runs at all"
BASE_STEP = "The base ref and the project root"
BOUND_STEP = "The time limit is inside its bounds"
# The job's time limit, in minutes: the least and the most a caller may pass, and what it gets
# when it passes nothing. `docs/cli.md#the-reusable-workflow` says why these three.
TIMEOUT_LEAST, TIMEOUT_MOST, TIMEOUT_DEFAULT = 5, 60, 15

BASE = f"""[stayfixed]
version = "{stayfixed.__version__}"
state = "adopting"
enforced = ["docs"]

[project]
name = "widget"
"""
LOOSENED = BASE.replace('["docs"]', "[]")
# Well past the preset's `AGENTS.md` budget, so the `docs` gate has a finding.
OVER_BUDGET = "".join("word\n" for _ in range(400))

# Every line that names an interpreter, whole, in the order the job runs them. Only three are
# stayfixed's, and a whitelist rather than a list of bad spellings: `-c` with flags before it,
# `-Pc`, a program on standard input, a script path, an assignment in front of the command
# (`PYTHONUSERBASE=… python3 …`), a wrapper (`env`, `exec`) or a second command packed onto the
# line after a `;` are each a way the checkout reaches the interpreter, and a pattern for each
# is a pattern for the ones thought of. Whole lines and not a prefix, because a prefix is
# satisfied by a line that goes on to run something else.
_PYTHON = re.compile(r"\bpython[\d.]*\b")
STAYFIXED_INVOCATIONS = (
    "python3 -m stayfixed --version",
    'python3 -P -s -m stayfixed gate --builtin --root "$ROOT" --base "$BASE_SHA" \\',
    'python3 -P -s -m stayfixed gate --custom --root "$ROOT" --base "$BASE_SHA" \\',
)
GATE_ENV: dict[str, Node] = {
    "PYTHONPATH": "stayfixed/src",
    "ROOT": "${{ steps.base.outputs.root }}",
    "BASE_SHA": "${{ steps.base.outputs.base_sha }}",
    "WORKFLOW_SHA": "${{ steps.stayfixed.outputs.sha }}",
    "ONLY": "${{ inputs.only }}",
}
SCRIPT = "<script>"
# The job, every step whole but its script, in order; an action is named without its ref, so a
# pin moving is not a change here. Everything that reaches a step's process other than the
# platform's own variables is in this list: its `env:`, its working directory, its action's
# inputs, and whether it may fail or be skipped (a key the list does not carry).
STEPS: list[dict[str, Node]] = [
    {
        "name": BOUND_STEP,
        "env": {"TIMEOUT_MINUTES": "${{ inputs.timeout-minutes }}"},
        "run": SCRIPT,
    },
    {
        "name": "The caller's repository",
        "uses": "actions/checkout",
        "with": {"path": "project", "fetch-depth": "0", "persist-credentials": "false"},
    },
    {
        "name": "stayfixed, at this workflow's own commit",
        "uses": "actions/checkout",
        "with": {
            "repository": "${{ job.workflow_repository }}",
            "ref": "${{ job.workflow_sha }}",
            "path": "stayfixed",
            "persist-credentials": "false",
        },
    },
    {
        "name": "The checkout is the commit this workflow file is at",
        "id": "stayfixed",
        "env": {"EXPECTED": "${{ job.workflow_sha }}"},
        "run": SCRIPT,
    },
    {"uses": "actions/setup-python", "with": {"python-version": "${{ inputs.python-version }}"}},
    {"name": PROOF, "env": {"PYTHONPATH": "stayfixed/src"}, "run": SCRIPT},
    {
        "name": BASE_STEP,
        "id": "base",
        "working-directory": "project",
        "env": {
            "INPUT_BASE": "${{ inputs.base }}",
            "INPUT_PATH": "${{ inputs.path }}",
            "PR_BASE": "${{ github.base_ref }}",
            "DEFAULT_BRANCH": "${{ github.event.repository.default_branch }}",
        },
        "run": SCRIPT,
    },
    {"name": JUDGE, "env": GATE_ENV, "run": SCRIPT},
    {"name": CUSTOM, "env": GATE_ENV, "run": SCRIPT},
]
# And each script's text, line for line, comments and blank lines aside: `STEPS` holds what a
# step is given, and this holds what it does with it. A line that is not an invocation can still
# change the verdict's process — `export PYTHONUSERBASE=…` or `. project/.ci-env` in a gate step,
# or a copy into `stayfixed/src/` from an earlier one, where the verdict's `PYTHONPATH` imports a
# `sitecustomize.py` at start-up — and every such line is a line this list does not carry.
CHECKOUT_STEP = "The checkout is the commit this workflow file is at"
SCRIPTS: dict[str, list[str]] = {
    BOUND_STEP: [
        'case "$TIMEOUT_MINUTES" in',
        "  [5-9]|[1-5][0-9]|60) ;;",
        "  *)",
        '    echo "::error::timeout-minutes: must be a whole number of minutes from 5 to 60"',
        "    exit 1",
        "    ;;",
        "esac",
    ],
    CHECKOUT_STEP: [
        'expected="$(git -C stayfixed rev-parse --verify --quiet "$EXPECTED^{commit}")" || { echo'
        " \"::error::the workflow's own ref '$EXPECTED' names no commit in the checkout\";"
        " exit 1; }",
        'actual="$(git -C stayfixed rev-parse HEAD)"',
        '[ "$actual" = "$expected" ] || { echo "::error::checked out $actual, not the workflow\'s'
        ' own $expected"; exit 1; }',
        'echo "sha=$expected" >> "$GITHUB_OUTPUT"',
    ],
    PROOF: ["python3 -m stayfixed --version"],
    BASE_STEP: [
        'case "$INPUT_PATH" in',
        '  ""|.|./) p="" ;;',
        '  *) p="${INPUT_PATH#./}"; p="${p%/}" ;;',
        "esac",
        'case "$p" in',
        "  *[!A-Za-z0-9._/-]*)",
        "    echo \"::error::path: must be a plain relative path — letters, digits, '.', '_', '-'"
        " and '/'\"",
        "    exit 1",
        "    ;;",
        "  ..|../*|*/..|*/../*)",
        '    echo "::error::path: must not leave the checkout"',
        "    exit 1",
        "    ;;",
        "esac",
        'if [ -n "$PR_BASE" ] && [ -n "$INPUT_BASE" ] && [ "$INPUT_BASE" != "$PR_BASE" ]; then',
        "  echo \"::error::base: names another branch, but this pull request's base is"
        " '$PR_BASE'; the gates' configuration is read from the base the platform reports\"",
        "  exit 1",
        "fi",
        'base="$INPUT_BASE"',
        '[ -n "$base" ] || base="$PR_BASE"',
        '[ -n "$base" ] || base="$DEFAULT_BRANCH"',
        '[ -n "$base" ] || { echo "::error::no base ref: pass \'base:\'"; exit 1; }',
        'git check-ref-format --branch "$base" >/dev/null',
        'base_sha="$(git rev-parse --verify --quiet "refs/remotes/origin/$base^{commit}")" ||',
        '  { echo "::error::origin/$base is not in this checkout — check out with fetch-depth: 0,'
        ' or name a base that exists"; exit 1; }',
        "{",
        '  echo "base_sha=$base_sha"',
        '  echo "root=project/${p:-.}"',
        '} >> "$GITHUB_OUTPUT"',
    ],
    JUDGE: [
        "set -f",
        "only=()",
        'for name in $ONLY; do only+=("--only=$name"); done',
        "set +f",
        STAYFIXED_INVOCATIONS[1],
        '  --workflow-sha "$WORKFLOW_SHA" --annotate --summary "$GITHUB_STEP_SUMMARY" "${only[@]}"',
    ],
    CUSTOM: [
        "set -f",
        "only=()",
        'for name in $ONLY; do only+=("--only=$name"); done',
        "set +f",
        STAYFIXED_INVOCATIONS[2],
        '  --workflow-sha "$WORKFLOW_SHA" --annotate --summary "$GITHUB_STEP_SUMMARY" "${only[@]}"',
    ],
}


def _workflow() -> dict[str, Node]:
    """`check.yml`, read at call time (the sdist carries no `.github/`) by the strict reader."""
    document = load(CHECK_WORKFLOW.read_text(encoding="utf-8"))
    assert isinstance(document, dict), document
    return document


def _job() -> dict[str, Node]:
    jobs = _workflow()["jobs"]
    assert isinstance(jobs, dict) and list(jobs) == ["gates"], jobs
    job = jobs["gates"]
    assert isinstance(job, dict), job
    return job


def _steps() -> list[dict[str, Node]]:
    steps = _job()["steps"]
    assert isinstance(steps, list) and all(isinstance(step, dict) for step in steps), steps
    return [step for step in steps if isinstance(step, dict)]


def _name(step: dict[str, Node]) -> str:
    name = step.get("name") or step.get("uses")
    assert isinstance(name, str), step
    return name.split("@")[0]


def _step(name: str) -> dict[str, Node]:
    return next(step for step in _steps() if _name(step) == name)


def _shape(step: dict[str, Node]) -> dict[str, Node]:
    """The step without its script's text and its action's ref."""
    shaped: dict[str, Node] = {}
    for key, value in step.items():
        if key == "run":
            shaped[key] = SCRIPT
        elif key == "uses" and isinstance(value, str):
            shaped[key] = value.split("@")[0]
        else:
            shaped[key] = value
    return shaped


def _scripts() -> list[str]:
    return [step["run"] for step in _steps() if isinstance(step.get("run"), str)]  # type: ignore[misc]


def _commands(script: str) -> list[str]:
    """The script's lines, less its blank lines and comment lines — except one that follows a
    line continued with `\\`, because there bash ends the command the line above says goes on,
    and the lines after it run as a command of their own."""
    kept: list[str] = []
    previous = ""
    for line in script.splitlines():
        bare = line.strip()
        if (bare and not bare.startswith("#")) or previous.endswith("\\"):
            kept.append(line)
        previous = line
    return kept


def _clone(tmp_path: Path, base: str = BASE) -> tuple[Path, str]:
    """The runner's workspace, with the caller's checkout at `project/` on a branch `change`,
    and the base commit the base step would have resolved."""
    workspace = tmp_path / "workspace"
    clone(workspace, base)
    base_sha = git(workspace / "project", "rev-parse", "refs/remotes/origin/main").strip()
    return workspace, base_sha


def _commit(workspace: Path, path: str, text: str) -> None:
    project = workspace / "project"
    (project / path).write_text(text, encoding="utf-8")
    commit(project, "chore: the change under review")


def _step_env(step: str) -> dict[str, str]:
    """The named step's `env:` block, as the strict reader reads it: every key, a comment or a
    blank line anywhere in it notwithstanding, and a key written twice refused."""
    env = _step(step).get("env")
    assert isinstance(env, dict) and all(isinstance(v, str) for v in env.values()), env
    return {key: value for key, value in env.items() if isinstance(value, str)}


def _judge(
    workspace: Path,
    base_sha: str,
    only: str,
    step: str = JUDGE,
    *,
    interpreter: Path | None = None,
    extra: dict[str, str] | None = None,
) -> tuple[int, str, str]:
    """The named gate step, run as the runner runs it: from the workspace, with the environment
    its own `env:` block names and the runner's few variables, and nothing else — unless a case
    passes `extra`, a variable the step's `env:` could name, or `interpreter`, the directory
    whose `python3` stands in for `setup-python`'s.

    The `env:` block is read off the shipped file rather than retyped here, so a value it gains
    — a `PYTHONPATH` that reaches into the checkout, say — is a value these cases run under.
    Each `${{ }}` in it is replaced by what the runner would put there in this case, and one this
    reader does not know is a failure rather than a guess. stayfixed's own checkout is where the
    runner puts it, `stayfixed/` beside `project/`.
    """
    runner = {
        "${{ steps.base.outputs.root }}": "project/.",
        "${{ steps.base.outputs.base_sha }}": base_sha,
        "${{ steps.stayfixed.outputs.sha }}": "0" * 40,
        "${{ inputs.only }}": only,
    }
    named = {
        key: runner[value] if value.startswith("${{") else value
        for key, value in _step_env(step).items()
    }
    checkout = workspace / "stayfixed"
    if not checkout.exists():
        # This checkout, with the password database answering the workspace as `HOME` does: the
        # gate reads the machine file under the database's home, never the developer's.
        checkout_with_owner_home(checkout, workspace)
    summary = workspace / "step-summary.md"
    summary.unlink(missing_ok=True)
    done = subprocess.run(
        ["bash", "-e", "-c", step_script(CHECK_WORKFLOW, step)],
        cwd=workspace,
        capture_output=True,
        text=True,
        check=False,
        env={
            # The interpreter running this suite stands in for `setup-python`'s: the step names
            # `python3`, and a system one below the floor would fail for a reason CI never meets.
            "PATH": f"{interpreter or Path(sys.executable).parent}:/usr/bin:/bin:/usr/local/bin",
            "HOME": str(workspace),
            "GITHUB_STEP_SUMMARY": str(summary),
            # The suite's floor under the product's `git`, for the `stayfixed gate` the step runs.
            **floor_env(),
            **named,
            **(extra or {}),
        },
    )
    written = summary.read_text(encoding="utf-8") if summary.exists() else ""
    return done.returncode, done.stdout + done.stderr, written


def _marker_gate(marker: Path) -> str:
    """A `[gates.custom.tests]` table whose command writes `marker`."""
    argv = json.dumps([Path(sys.executable).as_posix(), "-c", f"open({str(marker)!r}, 'w')"])
    return f"\n[gates.custom.tests]\nrun = {argv}\n"


@needs_workflow
def test_one_job_whose_judging_steps_may_not_fail_and_run_in_order() -> None:
    # The verdict is the job's status, so a step that may fail — `continue-on-error`, or an
    # `if:` that runs it after a failure or skips it — is a verdict that can be turned green.
    # `stayfixed gate` already exits 0 for an advisory gate's findings, so no step here needs
    # either. Mutations (declared): the judging step gains `continue-on-error: true`; the custom
    # step gains `if: always()`, which would run the repository's commands after a refusal.
    job = _job()
    # And the job itself carries neither: an `if:` on `gates` skips it, and a skipped job is a
    # required check the platform reports as passing. So the job's keys are held whole, which
    # also keeps a job-level `env:` from reaching every step. Mutation (declared): the job gains
    # an `if:`.
    assert list(job) == ["runs-on", "timeout-minutes", "defaults", "steps"], list(job)
    steps = _steps()
    names = [_name(step) for step in steps]
    # Every step's keys, whole and in order: a step that may fail or may be skipped carries a
    # key the list does not, and a step with no name is a tenth step. Mutation (declared): such
    # a step before the proof step.
    found = [(_name(step), list(step)) for step in steps]
    assert found == [(_name(step), list(step)) for step in STEPS], found
    # A stayfixed that cannot run fails under its own name before anything reads as a finding,
    # the base is resolved before either gate step reads it, and the repository's own commands
    # run last.
    assert names.index(PROOF) < names.index(BASE_STEP) < names.index(JUDGE) < names.index(CUSTOM)
    assert names[-2:] == [JUDGE, CUSTOM], names
    # And the time limit is judged before anything else runs, the checkouts included: a value
    # outside its bounds fails the job in seconds, under the default bound, having fetched and
    # run nothing.
    assert names[0] == BOUND_STEP, names


# The job's bound as `check.yml` spells it: the caller's value when it is inside the bounds, and
# the default otherwise, so the expression can yield nothing but a number from the least to the
# most. An expression that yields something the platform does not read as a number is an error
# that fails the job before it starts ("Unexpected value"), which is closed too; this shape never
# reaches that, and never hands the platform a number outside the range. A fraction inside it is
# handed over as it is, and the bound step then fails the job under that bound.
_BOUND = re.compile(
    r"\$\{\{ inputs\.timeout-minutes >= (\d+) && inputs\.timeout-minutes <= (\d+) "
    r"&& inputs\.timeout-minutes \|\| (\d+) \}\}"
)


@needs_workflow
def test_the_job_s_time_limit_is_an_input_the_expression_holds_inside_its_bounds() -> None:
    # The caller file is pull-request content, so `timeout-minutes:` is a value a pull request
    # can move. What it may move is a bounded limit: the input is a number, its default is the
    # bound the job had when it had no input, and the job's `timeout-minutes` reads it only
    # between the least and the most, the default standing in for anything else. Mutation
    # (declared): the expression's upper bound becomes 600, so a pull request could buy ten
    # runner-hours per run of this job.
    inputs = _workflow()["on"]
    assert isinstance(inputs, dict), inputs
    call = inputs["workflow_call"]
    assert isinstance(call, dict) and isinstance(call["inputs"], dict), call
    declared = call["inputs"]["timeout-minutes"]
    assert isinstance(declared, dict), declared
    assert declared["type"] == "number", declared
    assert declared["default"] == str(TIMEOUT_DEFAULT), declared
    bound = _job()["timeout-minutes"]
    assert isinstance(bound, str), bound
    match = _BOUND.fullmatch(bound)
    assert match is not None, bound
    assert tuple(int(n) for n in match.groups()) == (TIMEOUT_LEAST, TIMEOUT_MOST, TIMEOUT_DEFAULT)
    assert TIMEOUT_LEAST <= TIMEOUT_DEFAULT <= TIMEOUT_MOST


def _bound_step(value: str) -> tuple[int, str]:
    """The bound step's script, out of the shipped file, with the value the runner would put in
    its `env:` for a caller's `timeout-minutes:`."""
    done = subprocess.run(
        ["bash", "-e", "-c", step_script(CHECK_WORKFLOW, BOUND_STEP)],
        capture_output=True,
        text=True,
        check=False,
        env={"PATH": "/usr/bin:/bin", "TIMEOUT_MINUTES": value},
    )
    return done.returncode, done.stdout + done.stderr


SMOKE_WORKFLOW = CHECK_WORKFLOW.parent / "smoke.yml"


@pytest.mark.skipif(not SMOKE_WORKFLOW.is_file(), reason="smoke.yml is not in the sdist")
def test_a_real_run_passes_the_time_limit_a_value_of_its_own() -> None:
    # The cases here hold the expression's text and run the bound step's script; neither proves
    # that the platform takes a value a caller passed, through the expression, as the job's bound.
    # Every caller `init` writes passes none, so only the smoke's own call of this file can: it
    # passes a value inside the bounds that is not the default. Mutation (declared): the smoke
    # call passes the default, and no run takes a caller's value any more.
    document = load(SMOKE_WORKFLOW.read_text(encoding="utf-8"))
    assert isinstance(document, dict) and isinstance(document["jobs"], dict), document
    job = document["jobs"]["same-repository-form"]
    assert isinstance(job, dict) and job["uses"] == "./.github/workflows/check.yml", job
    passed = job["with"]
    assert isinstance(passed, dict) and isinstance(passed["timeout-minutes"], str), passed
    value = int(passed["timeout-minutes"])
    assert TIMEOUT_LEAST <= value <= TIMEOUT_MOST and value != TIMEOUT_DEFAULT, value


def _demanded_summary(step_name: str, output: str) -> str:
    """The one line the named smoke step's `grep -qx` demands of the script output it saved."""
    script = step_script(SMOKE_WORKFLOW, step_name)
    pattern = rf'^\s*grep -qx "([^"]*)" "\$RUNNER_TEMP/{re.escape(output)}"$'
    found = re.findall(pattern, script, re.MULTILINE)
    assert len(found) == 1, script
    return str(found[0])


@pytest.mark.skipif(not SMOKE_WORKFLOW.is_file(), reason="smoke.yml is not in the sdist")
def test_the_smoke_job_demands_the_summary_the_hook_script_prints_over_every_entry() -> None:
    # Each smoke script holds its own floor in constants and prints a summary that is green after
    # one row as after all of them; the job's `grep -qx` is the CI side of that floor, and a copy
    # of the counts written by hand stays behind when an entry is added or removed — the job then
    # fails on every pull request while the script and the suite agree. So the line is derived
    # from the script's constants; `tests/scripts/test_smoke_scripts.py` holds that a run prints
    # it. Mutation (declared, "the smoke job demands a hook summary the script no longer prints").
    smoke = scriptload.load(scriptload.SCRIPTS / "smoke_hooks.py", "smoke_hooks")
    expected = f"{smoke.EXPECTED_ENTRIES} entries, {smoke.EXPECTED_ROWS} row(s), 0 failure(s)"
    step = "Every hook entry, fed its sample event through the installed wrapper"
    assert _demanded_summary(step, "hooks.out") == expected


@pytest.mark.skipif(not SMOKE_WORKFLOW.is_file(), reason="smoke.yml is not in the sdist")
def test_the_smoke_job_demands_the_summary_the_exfiltration_scenario_prints_over_every_row() -> (
    None
):
    # The same derivation for the other script. Mutation (declared, "the smoke job demands an
    # exfiltration summary the scenario no longer prints").
    exfil = scriptload.load(scriptload.SCRIPTS / "smoke_exfiltration.py", "smoke_exfiltration")
    expected = f"{exfil.EXPECTED_ROWS} row(s), 0 failure(s)"
    assert _demanded_summary("The clone-to-exfiltration scenario", "hostile.out") == expected


@needs_bash
@needs_workflow
@pytest.mark.parametrize(
    "value", [str(TIMEOUT_LEAST), str(TIMEOUT_DEFAULT), "30", str(TIMEOUT_MOST)]
)
def test_a_time_limit_inside_its_bounds_passes_the_bound_step(value: str) -> None:
    code, printed = _bound_step(value)
    assert code == 0, printed
    assert "::error::" not in printed, printed


@needs_bash
@needs_workflow
@pytest.mark.parametrize(
    "value",
    [str(TIMEOUT_LEAST - 1), str(TIMEOUT_MOST + 1), "0", "-5", "7.5", "", "1E+21", "05", "600"],
)
def test_a_time_limit_outside_its_bounds_fails_the_job_before_anything_runs(value: str) -> None:
    # The expression already keeps the job's bound inside the range whatever the caller passed,
    # so a value outside it would otherwise run silently under the default: the caller asked for
    # something it did not get. It fails instead, closed, as the first step, naming the range
    # and not the value. A fraction, an exponent, a sign, a leading zero and nothing at all are
    # each a spelling the runner could hand the step, and none is digits from 5 to 60.
    # Mutations (declared): the pattern admits anything; the refusal stops exiting.
    code, printed = _bound_step(value)
    assert code == 1, printed
    assert "::error::timeout-minutes: must be a whole number of minutes from 5 to 60" in printed


@needs_workflow
def test_both_gate_steps_start_python_without_the_working_directory_on_its_path() -> None:
    # Nothing the repository wrote may execute in the process that holds the verdict, and a
    # module the interpreter imports from its working directory is something the repository
    # wrote. The steps run from the workspace today, which the pull request writes nothing
    # into; `-P` keeps that true if a later edit gives a gate step `working-directory: project`,
    # as the base step it replaced had. And no step reads anything with `python3 -c` any more:
    # the base step that did is gone. `-s` is the user site's half, and its behaviour is the
    # `.pth` case below. Mutations (declared): `python3 -s -m` for `python3 -P -s -m` in the
    # judging step, and in the custom step.
    for step in (JUDGE, CUSTOM):
        assert "python3 -P -s -m stayfixed gate" in step_script(CHECK_WORKFLOW, step), step
    # And no interpreter the job starts runs anything but stayfixed, in any spelling: every
    # line that names one, comments aside, is one of stayfixed's three invocation lines, whole
    # and in order. Mutations (declared): the proof step runs `python3 -P -c`, `python3 -Pc`, or
    # a program on standard input; the judging step's command gains an assignment in front of
    # it. Whole, because `… gate --help >/dev/null; PYTHONUSERBASE=… python3 -P -m stayfixed gate
    # --builtin …`, written before `-s`, began with an invocation and passed a prefix match.
    # Mutation (declared): the judging step's command line runs a second command before the gate.
    invocations = [
        line.strip()
        for script in _scripts()
        for line in script.splitlines()
        if not line.strip().startswith("#") and _PYTHON.search(line)
    ]
    assert invocations == list(STAYFIXED_INVOCATIONS), invocations


@needs_workflow
def test_the_judging_step_passes_the_platform_s_workflow_sha_through_env() -> None:
    # An upgrade's `[ci] ref` is admitted only at the commit the platform says is running, so
    # the judging step must hand `stayfixed gate` that commit, and from the platform's own record
    # peeled by the checkout step, below — through `env:`, never spliced into the script. No
    # clone case reaches an admitted move, which needs a released tag, so the wiring is held
    # here. Mutation (declared): drop `--workflow-sha "$WORKFLOW_SHA"`.
    assert '--workflow-sha "$WORKFLOW_SHA"' in step_script(CHECK_WORKFLOW, JUDGE)
    assert _step_env(JUDGE)["WORKFLOW_SHA"] == "${{ steps.stayfixed.outputs.sha }}"


def _checkout_step(workspace: Path, expected: str) -> tuple[int, str, str]:
    """The checkout-assertion step, run against `workspace/stayfixed` with `EXPECTED` as the
    platform's `job.workflow_sha`; its exit code, its stderr and what it wrote to the outputs."""
    output = workspace / "github-output"
    output.write_text("", encoding="utf-8")
    done = subprocess.run(
        ["bash", "-e", "-c", step_script(CHECK_WORKFLOW, CHECKOUT_STEP)],
        cwd=workspace,
        capture_output=True,
        text=True,
        check=False,
        env={**floor_env(), "EXPECTED": expected, "GITHUB_OUTPUT": str(output)},
    )
    return done.returncode, done.stdout + done.stderr, output.read_text(encoding="utf-8")


@needs_git
@needs_bash
@needs_workflow
def test_the_checkout_step_peels_an_annotated_tag_to_the_commit_the_gates_are_handed(
    tmp_path: Path,
) -> None:
    # A caller pinning `@vX.Y.Z` where that tag is annotated gets the tag object's sha as
    # `job.workflow_sha`, while the checkout lands on the commit: `v0.1.0` was tagged so, and
    # every run pinned to it refused with "checked out <commit>, not the workflow's own <tag>".
    # The step peels the value, and hands the commit on. Mutation (declared): the step compares
    # the raw value -> the annotated case refuses and this reddens.
    checkout = tmp_path / "stayfixed"
    checkout.mkdir()
    git(checkout, "init", "-q")
    (checkout / "a").write_text("a", encoding="utf-8")
    commit(checkout, "first")
    first = git(checkout, "rev-parse", "HEAD").strip()
    (checkout / "a").write_text("b", encoding="utf-8")
    commit(checkout, "second")
    head = git(checkout, "rev-parse", "HEAD").strip()
    git(checkout, "tag", "-a", "v9.9.9", "-m", "annotated")
    tag_object = git(checkout, "rev-parse", "v9.9.9").strip()
    assert tag_object != head
    for expected in (tag_object, head):
        code, said, output = _checkout_step(tmp_path, expected)
        assert (code, output) == (0, f"sha={head}\n"), said
    # And what still refuses: an empty value, which checks out the default branch, and a sha
    # that names some other commit.
    for expected in ("", first):
        code, said, output = _checkout_step(tmp_path, expected)
        assert (code, output) == (1, ""), said
        assert "::error::" in said


@needs_git
@needs_bash
@needs_workflow
@pytest.mark.parametrize("only", ["config", ""])
def test_the_judging_step_fails_a_change_that_loosens_what_the_base_enforces(
    tmp_path: Path, only: str
) -> None:
    # The base enforces `docs` and the change empties `enforced`: a pull request turning off a
    # gate it is about to face. The step must fail, say which key in an error annotation, and
    # write it into the job summary. Mutations (declared): the step judges the tree against
    # itself; it stops annotating; it writes no job summary.
    workspace, base_sha = _clone(tmp_path)
    _commit(workspace, CONFIG_FILE, LOOSENED)
    code, printed, summary = _judge(workspace, base_sha, only)
    assert code == 1, printed
    assert "::error" in printed and "stayfixed.enforced" in printed, printed
    assert "stayfixed.enforced" in summary, summary


@needs_git
@needs_bash
@needs_workflow
def test_the_judging_step_judges_the_configuration_whatever_only_names(tmp_path: Path) -> None:
    # `only:` is the caller's, and the caller is pull-request content: a pull request that
    # loosens `enforced` and sets `only: docs` in its own caller would otherwise run the `docs`
    # gate under the base's configuration, pass it, and never meet the configuration check. So
    # the judging step's `--builtin` runs `config` whatever else `only:` names. Mutation
    # (declared): `gate --builtin` stops adding it.
    workspace, base_sha = _clone(tmp_path)
    _commit(workspace, CONFIG_FILE, LOOSENED)
    code, printed, summary = _judge(workspace, base_sha, "docs")
    assert code == 1, printed
    assert "stayfixed.enforced" in printed and "stayfixed.enforced" in summary, printed


@needs_git
@needs_bash
@needs_workflow
def test_only_runs_the_names_it_is_given_and_nothing_else(tmp_path: Path) -> None:
    # `AGENTS.md` over its budget under a base that enforces `docs`: only a run that includes
    # `docs` fails. `config` alone judges an unchanged configuration and passes, which is what a
    # matrix leg of its own is for. Mutation (declared): the loop that turns `only:` into
    # `--only` arguments is removed, so every leg runs every gate.
    workspace, base_sha = _clone(tmp_path)
    _commit(workspace, "AGENTS.md", OVER_BUDGET)
    code, printed, _ = _judge(workspace, base_sha, "config")
    assert code == 0, printed
    for only in ("", "config docs"):
        code, printed, _ = _judge(workspace, base_sha, only)
        assert code == 1, (only, printed)


@needs_git
@needs_bash
@needs_workflow
def test_an_only_name_is_never_expanded_as_a_file_pattern(tmp_path: Path) -> None:
    # `$ONLY` is split unquoted, which is also where the shell would glob: `d*` beside a file
    # called `docs` in the workspace would become the `docs` gate. With globbing off it stays
    # `d*`, a name no configuration has, and `stayfixed gate` refuses it (2). Mutation
    # (declared): `set -f` is removed.
    workspace, base_sha = _clone(tmp_path)
    (workspace / "docs").write_text("", encoding="utf-8")
    code, printed, _ = _judge(workspace, base_sha, "d*")
    assert code == 2, printed


@needs_git
@needs_bash
@needs_workflow
def test_the_judging_step_runs_no_custom_gate_and_the_next_step_runs_them(tmp_path: Path) -> None:
    # A custom gate executes files the pull request can change, so it must never run in the
    # process that decides the verdict. The next step runs it, once the judging step passed.
    # Mutation (declared): the judging step loses `--builtin` and the marker appears.
    # The gate is on the base: one the change adds waits until it lands there.
    marker = tmp_path / "marker"
    workspace, base_sha = _clone(tmp_path, BASE + _marker_gate(marker))
    code, printed, _ = _judge(workspace, base_sha, "")
    assert code == 0, printed
    assert not marker.exists(), printed
    code, printed, _ = _judge(workspace, base_sha, "", step=CUSTOM)
    assert code == 0, printed
    assert marker.exists(), printed


@needs_workflow
def test_the_verdict_s_process_gets_only_the_environment_its_step_names() -> None:
    """Everything that reaches a step's process, held whole for every step, because `-P -s`
    cover only the working directory and the user site directory: a `PYTHONPATH` entry inside the
    checkout, a `PYTHONHOME` pointing into it, a `working-directory: project`, or a `BASH_ENV`
    the step's non-interactive bash sources would each hand the pull request code in the process
    that decides the verdict — or, in an earlier step, code that writes `$GITHUB_ENV` or
    `$GITHUB_PATH` and so chooses the next steps' environment and interpreter.

    What reaches it: the workflow's keys (no `env:`), the job's (no `env:`, no `if:`), the job's
    `defaults:` (the shell and nothing else), and each step whole but for its script's text —
    `env:`, `with:`, `working-directory:` and every other key — read by the strict reader, so a
    comment or a blank line inside a block hides nothing, and a key written twice is refused.
    No script writes `$GITHUB_ENV` or `$GITHUB_PATH` at all, and the next case holds every
    script's text. The runner's own variables and the `PATH` `setup-python` extends are the
    platform's.
    """
    workflow = _workflow()
    assert list(workflow) == ["name", "on", "permissions", "jobs"], list(workflow)
    assert _job()["defaults"] == {"run": {"shell": "bash"}}, _job()["defaults"]
    assert [_shape(step) for step in _steps()] == STEPS, [_shape(step) for step in _steps()]
    # Mutation (declared): the base step appends to `$GITHUB_ENV`.
    assert [s for s in _scripts() if "GITHUB_ENV" in s or "GITHUB_PATH" in s] == []


@needs_workflow
def test_the_job_s_token_can_read_the_repository_and_nothing_more() -> None:
    # Every step runs with the job's token in reach of the platform, the project's own gates
    # included, and those execute files the pull request can change. The checkouts need to read
    # the repository and nothing else, so that is all the workflow grants; the workflow's keys
    # above hold that `permissions:` is there, and this holds what it says. The job carries no
    # `permissions:` of its own, which the job's keys hold. Mutation (declared): `contents:
    # write`.
    permissions = _workflow()["permissions"]
    assert permissions == {"contents": "read"}, permissions


@needs_workflow
def test_every_script_the_job_runs_is_held_line_for_line() -> None:
    """The class the environment case above leaves open: a script line that changes the
    verdict's process — its environment or the code it imports — without being an invocation.

    `-P` keeps the working directory off `sys.path` and nothing more. Measured with a
    `setup-python`-shaped interpreter (not a virtual environment), before the gate steps passed
    `-s`: a `.pth` under `project/.local` ran at start-up once the step exported
    `PYTHONUSERBASE=project/.local`, and a `sitecustomize.py` copied into `stayfixed/src/` ran at
    start-up under the step's own `PYTHONPATH`. `-s` answers the first, and nothing but this
    hold answers the second. `export`, `.`/`source`, `cd`, `eval`, `umask` and a write into either
    checkout are each one line, and a list of forbidden spellings is a list of the ones thought
    of; so every script is held whole, comments aside, and a line the list does not carry reddens
    here.
    Mutations (declared): the judging step exports `PYTHONUSERBASE`; the custom step sources a
    file from the caller's checkout; the base step copies a file into stayfixed's checkout.
    """
    found = {_name(step): _commands(str(step["run"])) for step in _steps() if "run" in step}
    assert found == SCRIPTS, found


@needs_git
@needs_bash
@needs_workflow
@pytest.mark.parametrize("step", [JUDGE, CUSTOM], ids=["judging", "custom"])
def test_no_module_the_checkout_carries_is_imported_by_a_gate_step(
    tmp_path: Path, step: str
) -> None:
    # The behaviour the text above is about, run under the step's own `env:`: a pull request
    # that adds a `tomllib.py` at its top, which stayfixed's loader would import in place of the
    # standard library's if the checkout were on `sys.path`. Measured when this case was
    # written: with `PYTHONPATH: stayfixed/src:project` the planted module ran, and one that
    # re-exported the real `tomllib` left the step at exit 0. Mutations (declared): that
    # `PYTHONPATH` on the judging step, and on the custom step.
    workspace, base_sha = _clone(tmp_path)
    marker = tmp_path / "planted"
    _commit(workspace, "tomllib.py", f"open({str(marker)!r}, 'w').close()\n")
    code, printed, _ = _judge(workspace, base_sha, "", step=step)
    # The marker first: a planted module that ran is the finding, whatever it then broke.
    assert not marker.exists(), printed
    assert code == 0, printed


def _outside_any_virtual_environment(tmp_path: Path) -> Path:
    """A directory whose `python3` is this suite's interpreter outside its virtual environment.

    A virtual environment turns the user site directory off by itself, so the suite's own
    interpreter would pass a case about the user site whatever flags the step passed. The
    interpreter `setup-python` installs is not in one, and neither is this.
    """
    directory = tmp_path / "bin"
    directory.mkdir()
    # Not typed in the standard library's stubs; the case below asserts it is what it says.
    (directory / "python3").symlink_to(Path(getattr(sys, "_base_executable", sys.executable)))
    return directory


@needs_git
@needs_bash
@needs_workflow
@pytest.mark.parametrize("step", [JUDGE, CUSTOM], ids=["judging", "custom"])
def test_no_pth_file_under_a_user_base_in_the_checkout_runs_in_a_gate_step(
    tmp_path: Path, step: str
) -> None:
    # `-P` leaves the user site directory on, and a `.pth` file in it runs at the interpreter's
    # start-up, before anything stayfixed imports. The step's `env:` is held whole and names no
    # `PYTHONUSERBASE`; `-s` is what keeps a `.pth` the pull request commits out of the verdict's
    # process if it ever does. Measured before `-s`: with `PYTHONUSERBASE=project/.local`, a
    # committed `.pth` ran under `python3 -P`. Mutations (declared): `-s` dropped from the
    # judging step, and from the custom step.
    workspace, base_sha = _clone(tmp_path)
    marker = tmp_path / "planted"
    interpreter = _outside_any_virtual_environment(tmp_path)
    python3 = str(interpreter / "python3")
    user_base = {"PYTHONUSERBASE": "project/.local"}
    env = {"PATH": f"{interpreter}:/usr/bin:/bin:/usr/local/bin", "HOME": str(workspace)}
    site = subprocess.run(
        [python3, "-c", "import site; print(site.getusersitepackages())"],
        cwd=workspace,
        env={**env, **user_base},
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    planted = workspace / site / "planted.pth"
    planted.parent.mkdir(parents=True)
    planted.write_text(f"import os; open({str(marker)!r}, 'w').close()\n", encoding="utf-8")
    commit(workspace / "project", "chore: a user base inside the checkout")
    # The case can fail: this interpreter, started without `-s`, runs the file.
    subprocess.run(
        [python3, "-P", "-c", "pass"], cwd=workspace, env={**env, **user_base}, check=True
    )
    assert marker.exists(), "no user site directory is read here, so nothing below could fail"
    marker.unlink()
    code, printed, _ = _judge(
        workspace, base_sha, "", step=step, interpreter=interpreter, extra=user_base
    )
    # The marker first: a `.pth` that ran is the finding, whatever the step then said.
    assert not marker.exists(), printed
    assert code == 0, printed


@needs_git
@needs_bash
@needs_workflow
def test_the_custom_step_runs_only_the_custom_gates_only_names(tmp_path: Path) -> None:
    # A matrix leg's `only:` reaches the custom step too, so a leg named for a built-in gate
    # does not also run every command `[gates.custom]` names, and a leg named for a custom gate
    # runs that one. Mutation (declared): the custom step's loop is removed, and the `docs` leg
    # runs the marker gate.
    marker = tmp_path / "marker"
    workspace, base_sha = _clone(tmp_path, BASE + _marker_gate(marker))
    code, printed, _ = _judge(workspace, base_sha, "docs", step=CUSTOM)
    assert code == 0, printed
    assert not marker.exists(), printed
    code, printed, _ = _judge(workspace, base_sha, "tests", step=CUSTOM)
    assert code == 0, printed
    assert marker.exists(), printed
