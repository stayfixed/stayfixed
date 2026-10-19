"""The `runners` job of `ci.yml`: the one place the real test runners `prove`'s adapters run are
installed, at the versions the adapters' closed lists were drawn from, and run with a missing one
failing rather than skipping.

Read by `tests.workflow_yaml`'s strict reader, so a step cannot be skipped over unread. The pins
are held to the fixture they install from: the `node-version` the job asks for, the jest and vitest
the fixture's `package.json` and lockfile name, and the Go toolchain module the job fetches.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from tests.test_fixtures import CI_WORKFLOW, WORKFLOWS, needs_ci_workflow
from tests.workflow_yaml import Node, load

ROOT = Path(__file__).resolve().parents[1]
NODE_FIXTURE = ROOT / "tests" / "fixtures" / "prove" / "node"
FIXTURES_README = ROOT / "tests" / "fixtures" / "prove" / "README.md"
JOB = "runners"
NODE_VERSION = "26.12.0"
GO_VERSION = "1.27.2"
PINS = {"jest": "30.5.2", "vitest": "5.0.5"}


def _job() -> dict[str, Node]:
    document = load(CI_WORKFLOW.read_text(encoding="utf-8"))
    assert isinstance(document, dict), document
    jobs = document["jobs"]
    assert isinstance(jobs, dict), jobs
    job = jobs[JOB]
    assert isinstance(job, dict), job
    return job


def _steps() -> list[dict[str, Node]]:
    steps = _job()["steps"]
    assert isinstance(steps, list) and steps
    assert all(isinstance(step, dict) for step in steps)
    return [step for step in steps if isinstance(step, dict)]


@needs_ci_workflow
def test_the_runners_job_runs_the_runner_tests_with_a_missing_runner_failing() -> None:
    # Mutation (declared): `mutations/`'s "the runners job lets a missing runner skip" -> the
    # variable is not `1`, and a job missing every runner would pass by skipping them all.
    [last] = [step for step in _steps() if "pytest" in str(step.get("run", ""))]
    env = last["env"]
    assert isinstance(env, dict), last
    assert env["STAYFIXED_REQUIRE_RUNNERS"] == "1"
    # And the one job that opts the tests into the `node` and `go` on `PATH`, the pinned ones it
    # installed (`tests/prove/real_runners.py`).
    assert env["STAYFIXED_RUNNERS_ON_PATH"] == "1"
    assert env["STAYFIXED_NODE_MODULES"] == "${{ runner.temp }}/node/node_modules"
    assert "uv run pytest -n auto -m runners" in str(last["run"]).splitlines()
    # The job's last step, so nothing after it can end the job's answer otherwise.
    assert _steps()[-1] == last


@needs_ci_workflow
def test_the_job_installs_the_pinned_node_and_go() -> None:
    [node] = [step for step in _steps() if str(step.get("uses", "")).startswith("actions/setup")]
    assert node["with"] == {"node-version": NODE_VERSION}
    [go] = [step for step in _steps() if "proxy.golang.org" in str(step.get("run", ""))]
    env = go["env"]
    assert isinstance(env, dict), go
    assert env["GO_TOOLCHAIN"] == f"golang.org/toolchain@v0.0.1-go{GO_VERSION}.linux-amd64"
    assert re.fullmatch(r"[0-9a-f]{64}", str(env["GO_ZIP_SHA256"])), env
    # The digest is the one the fixtures' README records beside the pins, with where it came
    # from. Mutation (declared): `mutations/`'s "the runners job checks Go against a digest the
    # README does not record".
    recorded = re.findall(r"SHA-256 `([0-9a-f]{64})`", FIXTURES_README.read_text(encoding="utf-8"))
    assert recorded == [env["GO_ZIP_SHA256"]], recorded
    script = str(go["run"])
    # The digest is checked before anything the download holds is unpacked or put on `PATH`.
    # Mutation (declared): `mutations/`'s "the runners job unpacks Go unchecked".
    lines = script.splitlines()
    checked = next(i for i, line in enumerate(lines) if "sha256sum -c" in line)
    unpacked = next(i for i, line in enumerate(lines) if line.startswith("unzip"))
    assert checked < unpacked, lines
    assert f"v0.0.1-go{GO_VERSION}.linux-amd64.zip" in lines[0]


@needs_ci_workflow
def test_jest_and_vitest_come_from_the_fixture_s_lockfile_with_no_install_script() -> None:
    [npm] = [step for step in _steps() if "npm ci" in str(step.get("run", ""))]
    script = str(npm["run"])
    assert "tests/fixtures/prove/node/package-lock.json" in script
    assert "--ignore-scripts" in script and "$RUNNER_TEMP/node" in script
    manifest = json.loads((NODE_FIXTURE / "package.json").read_text(encoding="utf-8"))
    assert manifest["dependencies"] == PINS
    lock = json.loads((NODE_FIXTURE / "package-lock.json").read_text(encoding="utf-8"))
    for name, version in PINS.items():
        assert lock["packages"][f"node_modules/{name}"]["version"] == version
    assert lock["packages"][""]["dependencies"] == PINS


@needs_ci_workflow
def test_only_the_runners_job_opts_the_tests_into_the_runners_on_path() -> None:
    # Every other job leaves `node` and `go` on `PATH` unused, the hosted image's own among them,
    # so the tests that need one skip there. Mutation (declared): `mutations/`'s "the checks job
    # opts the tests into the runners on PATH" -> `checks` is found too.
    opted: list[tuple[str, str]] = []
    for workflow in sorted(WORKFLOWS.glob("*.y*ml")):
        document = load(workflow.read_text(encoding="utf-8"))
        assert isinstance(document, dict), workflow.name
        jobs = document.get("jobs")
        assert isinstance(jobs, dict), workflow.name
        outside = {key: value for key, value in document.items() if key != "jobs"}
        assert "STAYFIXED_RUNNERS_ON_PATH" not in str(outside), workflow.name
        opted += [
            (workflow.name, name)
            for name, job in jobs.items()
            if "STAYFIXED_RUNNERS_ON_PATH" in str(job)
        ]
    assert opted == [(CI_WORKFLOW.name, JOB)]


@needs_ci_workflow
def test_the_runners_job_puts_the_pinned_go_first_on_path() -> None:
    # The step that unpacks Go 1.27.2 adds its `bin` to `GITHUB_PATH`, which puts it before the
    # image's own `go` for every later step, and no later step adds a directory of its own there.
    # Mutation (declared): `mutations/`'s "the runners job leaves the pinned Go off PATH" -> the
    # line is gone.
    steps = _steps()
    [go] = [step for step in steps if "proxy.golang.org" in str(step.get("run", ""))]
    lines = str(go["run"]).splitlines()
    assert lines[-1] == 'echo "$RUNNER_TEMP/go/$GO_TOOLCHAIN/bin" >> "$GITHUB_PATH"', lines
    later = steps[steps.index(go) + 1 :]
    assert not any("GITHUB_PATH" in str(step.get("run", "")) for step in later)
    assert "go version" in str(steps[-1]["run"]).splitlines()
