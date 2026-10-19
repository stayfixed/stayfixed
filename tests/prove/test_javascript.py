"""The JavaScript adapters: what jest's, vitest's and `node --test`'s recognise, how each plans the
command as typed, what each refuses, and what a real run under each proves.

The plan tests run no runner: `plan` is a pure function of its arguments and of the files it reads,
so each builds the files a project holds (a `node_modules/<package>/package.json` and the entry its
`bin` names, a `node` and an `npx` on `PATH`) and reads the plan. The tests that run through
`prove` without a real runner use `fake_node`, a shell script standing in for `node`, `npx`,
`jest` and `vitest` that writes the report it was told to. The tests marked `runners` run the
`node` and `npx` on `PATH` (Node 26.12.0 in CI's `runners` job, and also run on 24.10.0) and the
jest and vitest an `npm ci` of `tests/fixtures/prove/node/` installed
(`tests/prove/real_runners.py`).
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping, Sequence
from dataclasses import replace
from pathlib import Path

import pytest

from stayfixed.printed import CLIPPED_CHARS, clipped
from stayfixed.profiles.javascript.adapters import (
    ADAPTERS,
    JEST_DISCOVERY,
    JEST_REPORT,
    NEVER_ENDS_DETAIL,
    NO_TEST_RUN,
    NO_TEST_RUN_DETAIL,
    NODE_DISCOVERY,
    NODE_REPORT,
    UNRESOLVED,
    VITEST_DISCOVERY,
    VITEST_REPORT,
    WAITS_DETAIL,
    JestAdapter,
    NodeTestAdapter,
    VitestAdapter,
    snapshots_rewritten,
    whole_file,
)
from stayfixed.profiles.runners import (
    ENTRY_NOT_FOUND,
    NEVER_ENDS,
    REFUSED_OPTION,
    Plan,
    Refused,
    ReportKind,
    ReportSource,
    Unresolved,
)
from stayfixed.prove.counts import Counts
from stayfixed.prove.junit import read_junit
from stayfixed.prove.run import (
    ASSIGNED_FORGING,
    FAILING,
    NONE_RAN,
    NOT_RECOGNISED,
    Receipt,
    Verdict,
    environment,
    line,
    prove,
)
from tests.gitfixture import git
from tests.prove.projects import (
    COMMANDS,
    JEST_PASSING,
    NODE_HEAD,
    NODE_PASSING,
    VITEST_HEAD,
    js_project,
)
from tests.prove.real_runners import (
    installed_packages,
    needs_packages,
    needs_runner,
    runner_directory,
)
from tests.prove.test_run import fake_uv, with_uv

PROVED, FAILED, NOT_PROVEN, REFUSED = (
    Verdict.PROVED,
    Verdict.FAILED,
    Verdict.NOT_PROVEN,
    Verdict.REFUSED,
)
ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests" / "fixtures" / "prove" / "node"
REPORTS = ROOT / "tests" / "fixtures" / "prove" / "reports"
JEST, VITEST, NODE_TEST = JestAdapter(), VitestAdapter(), NodeTestAdapter()
Adapter = JestAdapter | VitestAdapter | NodeTestAdapter


def executable(path: Path, text: str = "#!/bin/sh\nexit 0\n") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    path.chmod(0o755)
    return path


def package(directory: Path, name: str, bin_: object, entry: str) -> Path:
    """A package at `directory` named `name`, whose `package.json` holds `bin_` and whose entry
    file `entry` exists; the entry's realpath."""
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "package.json").write_text(
        json.dumps({"name": name, "bin": bin_}), encoding="utf-8"
    )
    executable(directory / entry, "#!/usr/bin/env node\n")
    return Path(os.path.realpath(directory / entry))


def jest_package(modules: Path, name: str = "jest") -> Path:
    if name == "jest-cli":
        return package(modules / name, name, {"jest": "./bin/jest.js"}, "bin/jest.js")
    return package(modules / name, name, "./bin/jest.js", "bin/jest.js")


def vitest_package(modules: Path) -> Path:
    return package(modules / "vitest", "vitest", {"vitest": "./vitest.mjs"}, "vitest.mjs")


def node_on_path(where: Path) -> Path:
    """A `node` the plan finds on `PATH`, in its own directory, and the `npx` Node ships beside
    it."""
    executable(where / "npx")
    return executable(where / "node")


def planned(
    adapter: Adapter,
    command: Sequence[str],
    cwd: Path,
    *,
    path: str = "",
    launch: Sequence[str] = (),
    variables: Mapping[str, str] | None = None,
) -> Plan | Refused | Unresolved:
    return adapter.plan(
        launch,
        command,
        cwd=cwd,
        scratch=cwd / "scratch",
        environ={"PATH": path, **(variables or {})},
    )


def plan_of(
    adapter: Adapter,
    command: Sequence[str],
    cwd: Path,
    *,
    path: str = "",
) -> Plan:
    got = planned(adapter, command, cwd, path=path)
    assert isinstance(got, Plan), got
    return got


def bin_link(modules: Path, name: str, target: str) -> Path:
    """`modules/.bin/<name>`, a link to `target` (read from `.bin`), as npm links a package's
    `bin`."""
    link = modules / ".bin" / name
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(target)
    return link


def installed(project: Path) -> tuple[Path, Path, Path]:
    """`project` with jest and vitest installed as npm installs them, and a `node`, an `npx`, a
    `jest` and a `vitest` in a directory of its own for `PATH`: the jest entry, the vitest entry
    and the `node`."""
    modules = project / "node_modules"
    tools = project / ".tools"
    executable(tools / "jest")
    executable(tools / "vitest")
    return jest_package(modules), vitest_package(modules), node_on_path(tools)


def link_bins(project: Path) -> None:
    """`project`'s jest and vitest (`installed`) linked in `node_modules/.bin`, as npm links each
    package's `bin`."""
    bin_link(project / "node_modules", "jest", "../jest/bin/jest.js")
    bin_link(project / "node_modules", "vitest", "../vitest/vitest.mjs")


# node's two options that hold the code until a debugger attaches.
DEBUGGER_WAITS = ("--inspect-brk", "--inspect-wait")


def never_detail(option: str) -> str:
    """The detail of `NEVER_ENDS` naming `option`: that it waits for a debugger, for node's two
    options that do, and that it watches for changes, for every watch mode."""
    return (WAITS_DETAIL if option in DEBUGGER_WAITS else NEVER_ENDS_DETAIL).format(option=option)


# --- What is recognised ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("command", "adapter"),
    [
        (["jest"], JEST),
        (["npx", "jest", "-i"], JEST),
        (["npx", "--no-install", "jest"], JEST),
        (["vitest"], VITEST),
        (["npx", "vitest", "run"], VITEST),
        (["node", "--test"], NODE_TEST),
        (["node", "--import", "tsx", "--test", "src/"], NODE_TEST),
        (["/usr/local/bin/node", "--test-only", "--test"], NODE_TEST),
        # A path to the runner, which the plan runs where it is a link to its entry.
        (["./node_modules/.bin/jest", "-i"], JEST),
        (["node_modules/.bin/vitest", "run"], VITEST),
        # Node's own options, whatever they are, go to `node` in front of the runner's entry.
        (["node", "--experimental-vm-modules", "node_modules/jest/bin/jest.js"], JEST),
        (["node", "./node_modules/.bin/jest", "-i"], JEST),
        (["/usr/bin/node", "--import", "tsx", "../node_modules/jest-cli/bin/jest.js"], JEST),
        (["node", "--max-old-space-size=4096", "node_modules/vitest/vitest.mjs", "run"], VITEST),
        (["node", "node_modules/.bin/vitest"], VITEST),
        (["node", "--max-old-space-size", "4096", "node_modules/jest/bin/jest.js"], JEST),
        (["node", "--inspect", "node_modules/jest/bin/jest.js", "-i"], JEST),
        (["node", "--frobnicate", "node_modules/jest/bin/jest.js"], JEST),
        (["node", "--env-file=.env", "--no-warnings", "node_modules/vitest/vitest.mjs"], VITEST),
        # node runs its test runner where its options name `--test`: `node --test`'s to plan.
        (["node", "--test", "node_modules/jest/bin/jest.js"], NODE_TEST),
    ],
)
def test_each_runner_s_commands_are_recognised(command: list[str], adapter: Adapter) -> None:
    # Mutations (declared): a path to the runner not read; node's options read only up to the
    # first that takes a value -> the cases after `--max-old-space-size 4096` are recognised by
    # none.
    assert [each.name for each in ADAPTERS if each.recognises(command)] == [adapter.name]


@pytest.mark.parametrize(
    "command",
    [
        ["npm", "test"],
        ["npm", "run", "test"],
        ["npm", "exec", "jest"],
        ["yarn", "jest"],
        ["pnpm", "jest"],
        ["pnpm", "exec", "vitest"],
        ["npx", "--yes", "jest"],
        # npm 11.6.0 reads the runner's options after `--no` as its own (measured): the report's
        # would never reach the runner.
        ["npx", "--no", "jest"],
        ["npx", "--no", "vitest", "run"],
        ["npx", "jest@30"],
        ["npx", "./node_modules/.bin/jest"],
        ["node_modules/.bin/jest-cli"],
        ["node", "script.js", "--test"],
        ["node", "--import", "tsx", "app.js"],
        # A script of the project's own, which may run anything, before the entry or as it.
        ["node", "scripts/jest.js"],
        ["node", "-", "node_modules/jest/bin/jest.js"],
        ["node", "x.js", "node_modules/jest/bin/jest.js"],
        ["node", "--inspect", "x.js", "y.js", "node_modules/jest/bin/jest.js"],
        ["node", "--max-old-space-size=4096", "x.js", "node_modules/jest/bin/jest.js"],
        ["node", "node_modules/jest"],
        ["node", "--", "node_modules/jest/bin/jest.js"],
        ["node"],
        ["npx"],
        [],
    ],
)
def test_npm_test_is_not_recognised(command: list[str]) -> None:
    # What a script runs is the script's; `npx` is read only bare or with `--no-install`, and
    # with a runner's bare name. Mutations (declared): `npm test` read as jest -> the first case
    # is; `--no` read as `--no-install` -> `npx --no jest` is; a word that can only be node's
    # script read past -> `node x.js <entry>` is.
    assert [each.name for each in ADAPTERS if each.recognises(command)] == []


def test_the_adapters_this_stack_ships() -> None:
    # `NODE_OPTIONS` reaches the run as it does outside it; vitest's `UPDATE_SNAPSHOT` is the one
    # variable that forges a report.
    assert [adapter.name for adapter in ADAPTERS] == ["jest", "vitest", "node-test"]
    assert JEST.forging == NODE_TEST.forging == {}
    assert VITEST.forging == {"UPDATE_SNAPSHOT": snapshots_rewritten}


@pytest.mark.parametrize(
    ("value", "rewrites"),
    [
        ("all", True),
        ("1", True),
        ("true", True),
        ("false", True),
        ("none", False),
        ("new", False),
        ("", False),
    ],
)
def test_vitest_s_update_snapshot_variable_rewrites_unless_it_keeps_them(
    value: str, rewrites: bool
) -> None:
    # vitest 5.0.5 reads `UPDATE_SNAPSHOT` as `--update` where the command gives none: `none` and
    # `new` keep a failing snapshot failing, and the empty value is unset; every other value is
    # `all` (measured over a failing snapshot: `UPDATE_SNAPSHOT=true npx vitest run` rewrites it
    # and passes). Mutation (declared): every value read as rewriting -> `none`, `new` and the
    # empty value are refused.
    assert snapshots_rewritten(value) is rewrites


@pytest.mark.parametrize("value", ["all", "1"])
def test_an_assigned_update_snapshot_is_refused(tmp_path: Path, value: str) -> None:
    # Refused before anything is planned: no `PATH` holds a runner here. Mutation (declared):
    # `UPDATE_SNAPSHOT` left off vitest's forging set -> the run is planned, and here not found.
    for argv in (
        [f"UPDATE_SNAPSHOT={value}", "npx", "vitest", "run"],
        ["env", f"UPDATE_SNAPSHOT={value}", "vitest"],
    ):
        got = prove(argv, cwd=tmp_path, environ={"PATH": ""}, timeout=60)
        assert (got.verdict, got.reason, got.detail) == (
            REFUSED,
            ASSIGNED_FORGING,
            "UPDATE_SNAPSHOT",
        ), argv
    kept = prove(["UPDATE_SNAPSHOT=none", "vitest"], cwd=tmp_path, environ={"PATH": ""}, timeout=60)
    assert (kept.verdict, kept.reason) == (NOT_PROVEN, ENTRY_NOT_FOUND)
    # jest reads no such variable.
    jest = prove(["UPDATE_SNAPSHOT=all", "jest"], cwd=tmp_path, environ={"PATH": ""}, timeout=60)
    assert (jest.verdict, jest.reason) == (NOT_PROVEN, ENTRY_NOT_FOUND)


def test_an_inherited_update_snapshot_that_rewrites_is_removed_and_named() -> None:
    inherited = {"PATH": "", "UPDATE_SNAPSHOT": "true"}
    env, scrubbed = environment(inherited, VITEST.forging, {})
    assert (env, scrubbed) == ({"PATH": ""}, ("UPDATE_SNAPSHOT",))
    kept = {"PATH": "", "UPDATE_SNAPSHOT": "new"}
    assert environment(kept, VITEST.forging, {}) == (kept, ())


# --- How the entry point resolves -----------------------------------------------------------


def test_npx_runs_as_typed(tmp_path: Path) -> None:
    # The run is the command as typed, `npx` and its option found on `PATH`, the report's options
    # after the runner's arguments: npx puts every `node_modules/.bin` above the directory on
    # `PATH`, which a test may need (measured: npm 11.6.0 on Node 24.10.0), and reads `.npmrc`.
    # Mutation (declared): `npx` dropped from the typed words -> the plan runs `jest` alone.
    project = tmp_path / "project"
    _, _, node = installed(project)
    link_bins(project)
    npx = node.parent / "npx"
    got = plan_of(JEST, ["npx", "jest", "-i"], project, path=str(node.parent))
    report = project / "scratch" / JEST_REPORT
    assert got == Plan(
        argv=(str(npx), "jest", "-i", "--json", f"--outputFile={report}"),
        kind=ReportKind.RESULTS_JSON,
        source=ReportSource.FILE,
        report=report,
        discovery=("*.test.*", "*.spec.*", "__tests__/*"),
    )
    assert got.discovery == JEST_DISCOVERY
    offline = plan_of(JEST, ["npx", "--no-install", "jest"], project, path=str(node.parent))
    assert offline.argv == (str(npx), "--no-install", "jest", "--json", f"--outputFile={report}")
    bare = plan_of(JEST, ["jest", "-i"], project, path=str(node.parent))
    assert bare.argv == (str(node.parent / "jest"), "-i", "--json", f"--outputFile={report}")


def test_vitest_without_run_runs_once(tmp_path: Path) -> None:
    # `run` first, so it runs once and never watches; `--reporter=default` for the person where
    # the command names no reporter of its own. Mutation (declared): `run` never added -> the
    # first plan starts at `-t`.
    project = tmp_path / "project"
    _, _, node = installed(project)
    link_bins(project)
    path = str(node.parent)
    vitest, npx = str(node.parent / "vitest"), str(node.parent / "npx")
    report = project / "scratch" / VITEST_REPORT
    ours = ("--reporter=json", f"--outputFile={report}")
    got = plan_of(VITEST, ["vitest", "-t", "x"], project, path=path)
    assert got.argv == (vitest, "run", "-t", "x", *ours, "--reporter=default")
    assert (got.kind, got.source, got.report) == (
        ReportKind.RESULTS_JSON,
        ReportSource.FILE,
        report,
    )
    assert (got.discovery, got.drop) == (VITEST_DISCOVERY, None)
    again = plan_of(VITEST, ["npx", "vitest", "run", "a"], project, path=path)
    assert again.argv == (npx, "vitest", "run", "a", *ours, "--reporter=default")
    named = plan_of(VITEST, ["vitest", "run", "--reporter", "dot"], project, path=path)
    assert named.argv == (vitest, "run", "--reporter", "dot", *ours)


def test_node_s_own_options_go_in_front_of_the_runner_s_entry(tmp_path: Path) -> None:
    # jest's documented ESM recipe passes `--experimental-vm-modules` to node, here or in
    # `NODE_OPTIONS`. The run is the words as typed. Mutation: none here -- the node shape left
    # unread is held at recognition, by `mutations/`'s "the jest and vitest adapters read no node
    # in front of their entry".
    project = tmp_path / "project"
    _, _, node = installed(project)
    path = str(node.parent)
    report = project / "scratch" / JEST_REPORT
    got = plan_of(
        JEST,
        [
            "node",
            "--experimental-vm-modules",
            "-r",
            "./setup.cjs",
            "node_modules/jest/bin/jest.js",
            "-i",
        ],
        project,
        path=path,
    )
    assert got.argv == (
        str(node),
        "--experimental-vm-modules",
        "-r",
        "./setup.cjs",
        "node_modules/jest/bin/jest.js",
        "-i",
        "--json",
        f"--outputFile={report}",
    )
    linked = project / "node_modules" / ".bin"
    linked.mkdir()
    (linked / "vitest").symlink_to("../vitest/vitest.mjs")
    again = plan_of(VITEST, ["node", "node_modules/.bin/vitest"], project, path=path)
    assert again.argv[:3] == (str(node), "node_modules/.bin/vitest", "run")


@pytest.mark.parametrize(
    "node_words",
    [
        ("--max-old-space-size", "4096"),
        ("--inspect",),
        ("--inspect=127.0.0.1:0",),
        ("--env-file=.env",),
        ("--env-file-if-exists", ".env"),
        ("--config-file=node.config.json",),
        ("--test-reporter=dot",),
        ("--test_update_snapshots",),
        ("-e", "require('fs')"),
        ("--import=data:text/javascript,process.exit(0)",),
        ("-r", "node:fs"),
        ("--frobnicate",),
    ],
)
def test_node_s_options_in_front_of_the_entry_run_as_typed(
    tmp_path: Path, node_words: tuple[str, ...]
) -> None:
    # Whatever node's options are, they are no adapter's to judge: each runs as typed, the entry
    # the first word node may run as its script that is shaped like one. Mutation (declared):
    # node's options read only up to the first that takes a value -> `--max-old-space-size 4096`
    # is no plan.
    project = tmp_path / "project"
    _, _, node = installed(project)
    command = ["node", *node_words, "node_modules/jest/bin/jest.js", "-i"]
    got = plan_of(JEST, command, project, path=str(node.parent))
    assert got.argv[: len(command)] == (str(node), *command[1:])


def test_a_preload_into_the_runner_s_package_runs_as_typed(tmp_path: Path) -> None:
    # A preload's value may be a path into the runner's own package: every word runs as typed.
    project = tmp_path / "project"
    _, _, node = installed(project)
    executable(project / "node_modules" / "jest" / "setup.js")
    command = ["node", "-r", "node_modules/jest/setup.js", "node_modules/jest/bin/jest.js", "-i"]
    got = plan_of(JEST, command, project, path=str(node.parent))
    assert got.argv[:5] == (str(node), *command[1:])


def test_a_node_named_by_its_path_runs_the_runner_s_entry(tmp_path: Path) -> None:
    project = tmp_path / "project"
    installed(project)
    node = executable(tmp_path / "opt" / "node")
    got = plan_of(JEST, [str(node), "node_modules/jest/bin/jest.js"], project)
    assert got.argv[:2] == (str(node), "node_modules/jest/bin/jest.js")


@pytest.mark.parametrize(
    "preload",
    [
        ("-r", "./setup.cjs"),
        ("--require=../shared/setup.cjs",),
        ("--import", "tsx"),
        ("--import=@swc-node/register/esm",),
        ("-r", "ts-node/register"),
        ("--import=file:///opt/hooks.mjs",),
    ],
)
def test_a_preload_of_a_file_or_a_package_is_free_in_front_of_the_entry(
    tmp_path: Path, preload: tuple[str, ...]
) -> None:
    project = tmp_path / "project"
    _, _, node = installed(project)
    command = ["node", *preload, "--max-old-space-size=4096", "node_modules/jest/bin/jest.js"]
    assert isinstance(planned(JEST, command, project, path=str(node.parent)), Plan)


@pytest.mark.parametrize(
    ("words", "named"),
    [
        (("--watch",), "--watch"),
        # jest's documented recipe for debugging: node holds the code until a debugger attaches,
        # which under `prove` none does (measured on Node 24.10.0: past any time limit).
        (("--inspect-brk",), "--inspect-brk"),
        (("--inspect-brk=127.0.0.1:9229",), "--inspect-brk"),
        (("--inspect-wait", "--no-warnings"), "--inspect-wait"),
    ],
    ids=["watch", "inspect-brk", "inspect-brk-port", "inspect-wait"],
)
def test_node_s_watch_mode_in_front_of_the_entry_never_ends(
    tmp_path: Path, words: tuple[str, ...], named: str
) -> None:
    # Mutation (declared): `--inspect-brk` and `--inspect-wait` planned -> their cases are plans.
    project = tmp_path / "project"
    _, _, node = installed(project)
    command = ["node", *words, "node_modules/vitest/vitest.mjs"]
    got = planned(VITEST, command, project, path=str(node.parent))
    assert got == Unresolved(NEVER_ENDS, never_detail(named))
    # `--inspect` alone waits for nobody: it runs as typed.
    inspected = ["node", "--inspect", "node_modules/vitest/vitest.mjs"]
    assert isinstance(planned(VITEST, inspected, project, path=str(node.parent)), Plan)


def test_a_debugger_wait_s_detail_says_it_waits_for_a_debugger(tmp_path: Path) -> None:
    # It watches nothing: its detail says what it waits for, and the receipt's line carries it
    # whole. Mutation (declared): the watch modes' detail given to it -> it says it watches.
    for option in DEBUGGER_WAITS:
        got = planned(NODE_TEST, ["node", option, "--test"], tmp_path)
        assert isinstance(got, Unresolved) and got.reason == NEVER_ENDS, got
        assert got.detail == WAITS_DETAIL.format(option=option)
        assert "debugger" in got.detail and "watches" not in got.detail
        assert len(got.detail) <= CLIPPED_CHARS
    watched = planned(NODE_TEST, ["node", "--watch", "--test"], tmp_path)
    assert watched == Unresolved(NEVER_ENDS, NEVER_ENDS_DETAIL.format(option="--watch"))


def test_the_runner_s_own_refusals_hold_behind_node(tmp_path: Path) -> None:
    project = tmp_path / "project"
    _, _, node = installed(project)
    command = ["node", "node_modules/jest/bin/jest.js", "-u"]
    assert planned(JEST, command, project, path=str(node.parent)) == Refused(REFUSED_OPTION, "-u")


def test_a_runner_named_by_its_link_runs_as_typed(tmp_path: Path) -> None:
    # npm's `node_modules/.bin/jest` is a link to the file the package's `bin` names: the run is
    # that link, as typed, which its entry's own `#!/usr/bin/env node` runs. Mutation (declared):
    # a path to the runner not read -> no plan.
    project = tmp_path / "project"
    installed(project)
    node = node_on_path(tmp_path / "bin")
    linked = project / "node_modules" / ".bin"
    linked.mkdir()
    (linked / "jest").symlink_to("../jest/bin/jest.js")
    (linked / "vitest").symlink_to("../vitest/vitest.mjs")
    report = project / "scratch" / JEST_REPORT
    got = plan_of(JEST, ["./node_modules/.bin/jest", "-i"], project, path=str(node.parent))
    assert got.argv == (str(linked / "jest"), "-i", "--json", f"--outputFile={report}")
    again = plan_of(VITEST, ["node_modules/.bin/vitest"], project, path=str(node.parent))
    assert again.argv[:2] == (str(linked / "vitest"), "run")
    # The runner's own refusals and watch modes hold there as anywhere.
    assert planned(JEST, ["./node_modules/.bin/jest", "-u"], project, path=str(node.parent)) == (
        Refused(REFUSED_OPTION, "-u")
    )


def test_a_runner_named_by_a_path_that_is_no_link_runs_as_typed(tmp_path: Path) -> None:
    # pnpm's `.bin/jest` is an `sh` shim, no link: the same file runs bare or through `npx`, so by
    # its path it runs as typed too; so do the entry itself named by a path and a link to a file
    # no package's `bin` names.
    project = tmp_path / "project"
    package(project / "node_modules" / "jest", "jest", "./bin/jest", "bin/jest")
    node = node_on_path(tmp_path / "bin")
    shims = project / "node_modules" / ".bin"
    executable(shims / "jest", '#!/bin/sh\nexec node ../jest/bin/jest "$@"\n')
    executable(project / "node_modules" / "jest" / "other" / "jest")
    (project / "elsewhere").mkdir()
    (project / "elsewhere" / "jest").symlink_to("../node_modules/jest/other/jest")
    report = project / "scratch" / JEST_REPORT
    for word in ("./node_modules/.bin/jest", "node_modules/jest/bin/jest", "elsewhere/jest"):
        got = plan_of(JEST, [word, "-i"], project, path=str(node.parent))
        assert got.argv == (str(project / word), "-i", "--json", f"--outputFile={report}"), word


def test_a_launcher_is_handed_the_command_as_typed(tmp_path: Path) -> None:
    # `uv run npx jest`: the launcher is found and runs, its words kept in front, and the
    # command's words are handed to it as typed, for it to resolve on its own `PATH` (uv puts the
    # project's `.venv/bin` first): nothing is looked for on the caller's, so a `PATH` holding uv
    # alone plans the run. Mutations (declared): the launcher dropped -> the plan runs `npx`
    # alone; the command's program handed by the caller's path -> `npx` is absolute.
    project = tmp_path / "project"
    _, _, node = installed(project)
    link_bins(project)
    launcher = executable(tmp_path / "tools" / "uv")
    # The caller's `PATH` holds `npx`, `node` and `jest` too: none of them is handed to uv.
    path = os.pathsep.join([str(launcher.parent), str(node.parent)])
    alone = str(launcher.parent)
    report = project / "scratch" / JEST_REPORT
    got = planned(JEST, ["npx", "jest"], project, path=path, launch=("uv", "run"))
    assert isinstance(got, Plan), got
    assert got.argv == (str(launcher), "run", "npx", "jest", "--json", f"--outputFile={report}")
    tested = planned(NODE_TEST, ["node", "--test"], project, path=path, launch=("uv", "run"))
    assert isinstance(tested, Plan), tested
    assert tested.argv[:4] == (str(launcher), "run", "node", "--test-reporter=junit")
    assert tested.argv[-1] == "--test"
    bare = planned(JEST, ["jest"], project, path=path, launch=("uv", "run", "--frozen"))
    assert isinstance(bare, Plan), bare
    assert bare.argv[:4] == (str(launcher), "run", "--frozen", "jest")
    via_link = planned(JEST, ["node_modules/.bin/jest"], project, path=path, launch=("uv", "run"))
    assert isinstance(via_link, Plan), via_link
    assert via_link.argv[2] == "node_modules/.bin/jest"
    # Nothing the launcher resolves is looked for on the caller's `PATH`: uv alone plans each.
    for adapter, command in (
        (JEST, ["npx", "jest"]),
        (JEST, ["jest"]),
        (NODE_TEST, ["node", "--test"]),
    ):
        alone_plan = planned(adapter, command, project, path=alone, launch=("uv", "run"))
        assert isinstance(alone_plan, Plan), alone_plan
        assert alone_plan.argv[2] == command[0]
    # A launcher on no `PATH` entry is what is missing, and the detail names it, a bare runner's
    # too. Mutation (declared): the bare runner's detail given behind a launcher -> it names jest.
    for command in (["npx", "jest"], ["jest"]):
        missing = planned(JEST, command, project, path="", launch=("uv", "run"))
        assert missing == Unresolved(ENTRY_NOT_FOUND, "no uv on PATH"), command


def test_vitest_related_keeps_its_subcommand_and_runs_once(tmp_path: Path) -> None:
    # vitest reads its first positional word as a subcommand (measured on 5.0.5): `run` put in
    # front of `related` made it a name filter, and a run that passes directly `failed`. So `run`
    # is added only where the command's first word is no subcommand, and `related` gets `--run`,
    # unless the command gives it (vitest refuses two settings of it before any run). Mutation
    # (declared): `run` added in front of every command -> the first plan starts `run related`.
    project = tmp_path / "project"
    _, _, node = installed(project)
    path = str(node.parent)
    vitest, npx = str(node.parent / "vitest"), str(node.parent / "npx")
    report = project / "scratch" / VITEST_REPORT
    ours = ("--reporter=json", f"--outputFile={report}", "--reporter=default")
    got = plan_of(VITEST, ["npx", "vitest", "related", "src/a.js"], project, path=path)
    assert got.argv == (npx, "vitest", "related", "src/a.js", "--run", *ours)
    given = plan_of(VITEST, ["vitest", "related", "--run", "src/a.js"], project, path=path)
    assert given.argv == (vitest, "related", "--run", "src/a.js", *ours)


@pytest.mark.parametrize("subcommand", ["watch", "dev"])
def test_vitest_s_watching_subcommands_are_not_proven(tmp_path: Path, subcommand: str) -> None:
    # Measured on 5.0.5: `vitest watch` and `vitest dev` run, then wait for changes past any time
    # limit. Mutation (declared): the watching subcommands planned -> each is a plan.
    assert planned(VITEST, ["vitest", subcommand, "a"], tmp_path) == Unresolved(
        NEVER_ENDS, NEVER_ENDS_DETAIL.format(option=f"vitest {subcommand}")
    )


@pytest.mark.parametrize("subcommand", ["bench", "list", "init", "doctor"])
def test_vitest_s_subcommands_that_run_no_test_are_not_proven(
    tmp_path: Path, subcommand: str
) -> None:
    # Measured on 5.0.5, each with the report options: `bench` runs benchmarks (exit 1 with no
    # benchmark file, a report of no test); `list` prints the tests it collects and writes no
    # report (exit 0); `init` asks for a project to scaffold; `doctor` runs the suite under each
    # pool to time it and writes no report (exit 0). Mutation (declared): those subcommands
    # planned -> each is a plan, `run` in front.
    detail = NO_TEST_RUN_DETAIL.format(subcommand=subcommand)
    assert planned(VITEST, ["npx", "vitest", subcommand], tmp_path) == Unresolved(
        NO_TEST_RUN, detail
    )
    assert len(detail) <= CLIPPED_CHARS


def test_a_vitest_subcommand_after_an_option_is_read_as_a_name_filter(tmp_path: Path) -> None:
    # Only the first word is read as a subcommand: vitest itself reads the first positional word
    # (measured: `vitest --globals related a.js` runs `related`), and a word after an option may
    # be that option's value, so the plan stays `run` with the word as a filter: the tests whose
    # paths hold it run, as under `vitest run watch`, and `failed` where none does.
    project = tmp_path / "project"
    _, _, node = installed(project)
    got = plan_of(VITEST, ["vitest", "--globals", "watch"], project, path=str(node.parent))
    assert got.argv[1:4] == ("run", "--globals", "watch")


def test_the_report_options_go_before_a_separator(tmp_path: Path) -> None:
    # Every word after `--` is a test path to jest and vitest. Mutation (declared): the report's
    # options appended after `--` -> they are read as paths.
    project = tmp_path / "project"
    _, _, node = installed(project)
    got = plan_of(JEST, ["jest", "a", "--", "--b"], project, path=str(node.parent))
    report = project / "scratch" / JEST_REPORT
    jest = str(node.parent / "jest")
    assert got.argv == (jest, "a", "--json", f"--outputFile={report}", "--", "--b")


def test_a_bare_runner_on_no_path_entry_is_not_found(tmp_path: Path) -> None:
    # Typed bare, the runner is the one a shell finds on `PATH`: where there is none, nothing the
    # command names can run (a Yarn Plug'n'Play project, an install that never linked one). Nothing
    # is run or installed, and the detail names what to do instead. Mutation (declared): the
    # detail left off -> it names `jest` alone.
    project = tmp_path / "project"
    project.mkdir()
    (project / ".pnp.cjs").write_text("", encoding="utf-8")
    jest_package(project / "node_modules")
    node = node_on_path(tmp_path / "bin")
    for adapter in (JEST, VITEST):
        got = planned(adapter, [adapter.name], project, path=str(node.parent))
        assert got == Unresolved(ENTRY_NOT_FOUND, UNRESOLVED.format(bin=adapter.name)), got
        assert f"`npx {adapter.name}`" in got.detail and "`prove --junit`" in got.detail
    assert sorted(path.name for path in project.iterdir()) == [".pnp.cjs", "node_modules"]


def test_a_command_the_adapter_does_not_recognise_has_no_plan(tmp_path: Path) -> None:
    for adapter in (JEST, VITEST):
        assert planned(adapter, ["npm", "test"], tmp_path) == Unresolved(ENTRY_NOT_FOUND)


@pytest.mark.parametrize(
    ("adapter", "command", "program"),
    [
        (JEST, ["npx", "jest"], "npx"),
        (VITEST, ["npx", "--no-install", "vitest"], "npx"),
        (JEST, ["node", "node_modules/jest/bin/jest.js"], "node"),
        (NODE_TEST, ["node", "--test"], "node"),
        (NODE_TEST, ["tools/node", "--test"], "tools/node"),
    ],
)
def test_a_program_on_no_path_entry_is_not_found(
    tmp_path: Path, adapter: Adapter, command: list[str], program: str
) -> None:
    # The command's first word is found as a shell finds it; where it names nothing, nothing can
    # run, and the detail says how it was looked for: a word holding a `/` at that path, a bare
    # one on `PATH` (`programs.not_found`). Mutation: none -- the detail is wording.
    project = tmp_path / "project"
    installed(project)
    got = planned(adapter, command, project, path="")
    looked = f"no executable file at {program}" if "/" in program else f"no {program} on PATH"
    assert got == Unresolved(ENTRY_NOT_FOUND, looked)


def test_an_unresolved_entry_s_detail_is_on_the_receipt(tmp_path: Path) -> None:
    # Through `prove` and the adapters this stayfixed ships. Mutation (declared, `core`): the
    # adapter's detail left off the receipt -> `detail` is empty.
    node = node_on_path(tmp_path / "bin")
    project = tmp_path / "project"
    project.mkdir()
    got = prove(["jest"], cwd=project, environ={"PATH": str(node.parent)}, timeout=60)
    assert (got.verdict, got.reason, got.runner) == (NOT_PROVEN, ENTRY_NOT_FOUND, "jest")
    assert got.detail == (
        "no jest on PATH; `npx jest` runs a project's own, or `prove --junit` counts a report"
    )
    # The receipt's line carries it whole. Mutation (declared): the detail lengthened past the
    # clip -> vitest's is cut.
    for name in ("jest", "vitest"):
        assert len(UNRESOLVED.format(bin=name)) <= CLIPPED_CHARS
    assert "`prove --junit`" in line(got)


# --- node --test ----------------------------------------------------------------------------


def test_node_s_plan_puts_its_reporters_first(tmp_path: Path) -> None:
    node = node_on_path(tmp_path / "bin")
    got = plan_of(NODE_TEST, ["node", "--test", "src/"], tmp_path, path=str(node.parent))
    report = tmp_path / "scratch" / NODE_REPORT
    assert got.drop is not None
    assert replace(got, drop=None) == Plan(
        argv=(
            str(node),
            "--test-reporter=junit",
            f"--test-reporter-destination={report}",
            "--test-reporter=spec",
            "--test-reporter-destination=stdout",
            "--test",
            "src/",
        ),
        kind=ReportKind.JUNIT,
        source=ReportSource.FILE,
        report=report,
        discovery=("*.test.*", "*-test.*", "*_test.*", "test-*.*", "test.*", "test/*"),
    )
    assert got.discovery == NODE_DISCOVERY


def test_a_node_named_by_its_path_is_the_one_that_runs(tmp_path: Path) -> None:
    node = executable(tmp_path / "tools" / "node")
    got = plan_of(NODE_TEST, ["tools/node", "--test"], tmp_path, path="")
    assert got.argv[0] == str(tmp_path / "tools/node")
    assert os.path.realpath(got.argv[0]) == os.path.realpath(node)
    # A path is never looked up on `PATH`, and the detail says what was looked for there.
    # Mutation: none -- the detail is wording.
    assert planned(NODE_TEST, ["tools/missing/node", "--test"], tmp_path) == Unresolved(
        ENTRY_NOT_FOUND, "no executable file at tools/missing/node"
    )


# Each recorded report, the directory node ran in when it was recorded (the `/work` the README
# says each recording's scratch path was rewritten to), the files there that Node 24.10.0's names
# read from it (a run of 24.10.0 writes no `file` attribute, so the drop finds each file there),
# and its counts under the plan's drop.
WHOLE_FILE_REPORTS = [
    ("node-name-pattern.xml", "three", (), Counts(0, 0, 0)),
    ("node-no-tests.xml", "notests", (), Counts(0, 0, 0)),
    ("node-exit0.xml", "exit0", (), Counts(0, 0, 0)),
    ("node-load-failure.xml", "loadfail", (), Counts(1, 2, 0)),
    ("node-junit.xml", "three", (), Counts(1, 1, 1)),
    ("node24-name-pattern.xml", "three", ("three.test.mjs",), Counts(0, 0, 0)),
    ("node24-nested-pattern.xml", "nestedpattern", ("test/deep/three.test.mjs",), Counts(0, 0, 0)),
    ("node24-no-tests.xml", "notests", ("notests.test.mjs",), Counts(0, 0, 0)),
    ("node24-exit0.xml", "exit0", ("exit0.test.mjs",), Counts(0, 0, 0)),
    (
        "node24-nested.xml",
        "nested",
        ("test/real.test.mjs", "test/deep/empty.test.mjs"),
        Counts(1, 0, 0),
    ),
    (
        "node24-load-failure.xml",
        "loadfail",
        ("ok.test.mjs", "test/broken.test.mjs", "throws.test.mjs"),
        Counts(1, 2, 0),
    ),
]


@pytest.mark.parametrize(
    ("report", "directory", "files", "counts"),
    WHOLE_FILE_REPORTS,
    ids=[report for report, *_ in WHOLE_FILE_REPORTS],
)
def test_the_whole_file_testcase_is_dropped_unless_it_failed(
    tmp_path: Path, report: str, directory: str, files: tuple[str, ...], counts: Counts
) -> None:
    # node writes one testcase for a file that ran no test, named by the file's path from the
    # directory it runs in and passed; one that failed is a file that did not load. Node 24.10.0
    # writes no `file` attribute, so its names are read from the run's directory, where the files
    # are. The load failures count as failed though `drop` answers true for them: the JUnit reader
    # never drops a failure. Mutations (declared): `drop` left unset -> the whole-file cases count
    # one passed; a testcase without `file` never dropped -> the Node 24 cases count one passed;
    # `mutations/`'s "a dropped testcase's failure counts nowhere" -> the load failures read one
    # passed, none failed.
    node = node_on_path(tmp_path / "bin")
    # Node 26.12.0's `file` attribute names `/work/nt/<case>/...`: the run's directory is that
    # one, which exists nowhere here, and only Node 24.10.0's reports read the files there.
    cwd = tmp_path / "work" / "nt" / directory if files else Path("/work/nt") / directory
    for name in files:
        executable(cwd / name)
    drop = plan_of(NODE_TEST, ["node", "--test"], cwd, path=str(node.parent)).drop
    assert read_junit((REPORTS / report).read_bytes(), drop=drop) == counts


@pytest.mark.parametrize(
    ("attributes", "dropped"),
    [
        ({"name": "a.test.mjs", "classname": "test", "file": "{cwd}/a.test.mjs"}, True),
        # Node 26's naming of a nested file, by its path from the run's directory as 24.10.0
        # names it (no Node 26 here to record it).
        (
            {
                "name": "test/deep/a.test.mjs",
                "classname": "test",
                "file": "{cwd}/test/deep/a.test.mjs",
            },
            True,
        ),
        ({"name": "a.test.mjs", "classname": "test", "file": "{cwd}/b.test.mjs"}, False),
        ({"name": "a.test.mjs", "classname": "test", "file": "{cwd}/sub/a.test.mjs"}, False),
        ({"name": "a.test.mjs", "classname": "suite", "file": "{cwd}/a.test.mjs"}, False),
        ({"name": "a.test.mjs", "classname": "test"}, True),
        ({"name": "test/deep/a.test.mjs", "classname": "test"}, True),
        ({"name": "adds", "classname": "test"}, False),
        ({"name": "missing.test.mjs", "classname": "test"}, False),
        ({"name": "test", "classname": "test"}, False),
        ({"name": "", "classname": "test"}, False),
        ({"name": "a.test.mjs", "classname": "suite"}, False),
        # A failure attribute is not the predicate's: the reader counts a failed testcase as
        # failed whatever `drop` says (`test_the_whole_file_testcase_is_dropped_unless_it_failed`).
        (
            {"name": "a.test.mjs", "classname": "test", "file": "{cwd}/a.test.mjs", "failure": "x"},
            True,
        ),
        ({"name": "a.test.mjs", "classname": "test", "failure": "test failed"}, True),
    ],
    ids=[
        "whole-file",
        "whole-file-nested",
        "another-file",
        "another-directory",
        "another-classname",
        "no-file-attribute",
        "no-file-attribute-nested",
        "a-test",
        "no-such-file",
        "a-directory",
        "no-name",
        "no-file-attribute-another-classname",
        "failed",
        "no-file-attribute-failed",
    ],
)
def test_whole_file_reads_the_attributes_and_the_run_s_directory(
    tmp_path: Path, attributes: Mapping[str, str], dropped: bool
) -> None:
    # Mutations (declared): the name check dropped -> another file's testcase is; the classname
    # check dropped -> a suite's is; a name with no `file` read without the file -> a test named
    # `adds` is; a directory taken for the file -> `test` is.
    executable(tmp_path / "a.test.mjs")
    executable(tmp_path / "test" / "deep" / "a.test.mjs")
    filled = {key: value.format(cwd=tmp_path) for key, value in attributes.items()}
    assert whole_file(tmp_path)(filled) is dropped


def test_a_whole_file_name_that_cannot_be_asked_about_is_counted(tmp_path: Path) -> None:
    # Node 24.10.0 writes no `file` attribute, so the name is asked about from the run's
    # directory; a path there that cannot be asked about (`EACCES`) names no run's file, and the
    # testcase is counted, never an internal error. Mutation (declared): the `OSError` let
    # through -> `PermissionError` out of the reader.
    locked = tmp_path / "locked"
    executable(locked / "a.test.mjs")
    locked.chmod(0)
    try:
        report = b'<testsuites><testcase name="locked/a.test.mjs" classname="test"/></testsuites>'
        assert read_junit(report, drop=whole_file(tmp_path)) == Counts(1, 0, 0)
    finally:
        locked.chmod(0o755)


# A stand-in for node that writes, to the junit destination it is handed, the one testcase node
# writes for a whole file that ran no test: named by the file's path from where node runs,
# without `file` (Node 24.10.0) or with it, an absolute path (26.12.0).
WHOLE_FILE_NODE = """#!/bin/sh
for word in "$@"; do
  case "$word" in
    --test-reporter-destination=stdout) ;;
    --test-reporter-destination=*)
      printf '<testsuites><testcase name="three.test.mjs" classname="test"%s/></testsuites>' \\
        "{file}" > "${{word#--test-reporter-destination=}}" ;;
  esac
done
"""


@pytest.mark.parametrize(
    ("file", "words"),
    [
        ("", ["--directory", "sub"]),
        ("", ["--directory=sub"]),
        (" file='$PWD/three.test.mjs'", ["--directory", "sub"]),
    ],
    ids=["node24", "node24-equals", "node26"],
)
def test_a_whole_file_testcase_behind_uv_s_directory_is_dropped_where_node_ran(
    tmp_path: Path, file: str, words: list[str]
) -> None:
    # `uv run --directory sub node --test --test-name-pattern=no_such_test`: node runs in `sub`
    # and names the file from there, so the drop reads it from there and the run ran no test,
    # as the same command typed in `sub` did. Mutation (declared, `core`): the adapter handed
    # the directory the command was typed in -> `proved`, one test passed.
    project = tmp_path / "project"
    sub = project / "sub"
    sub.mkdir(parents=True)
    executable(sub / "three.test.mjs")
    node = fake_node(tmp_path / "bin", WHOLE_FILE_NODE.format(file=file))
    uv = fake_uv(node.parent)
    tail = ["node", "--test", "--test-name-pattern=no_such_test"]
    behind = ["uv", "run", "--no-project", "--offline", *words, *tail]
    got = through_prove(behind, project, with_uv(uv))
    assert (got.verdict, got.reason, got.counts) == (FAILED, NONE_RAN, Counts(0, 0, 0)), got
    assert got.directory == os.path.realpath(sub)
    typed_there = through_prove(tail, sub, with_uv(uv))
    assert (typed_there.verdict, typed_there.reason) == (FAILED, NONE_RAN)


# --- What is refused ------------------------------------------------------------------------


REFUSALS: list[tuple[Adapter, tuple[str, ...], str]] = [
    # jest 30.5.2
    (JEST, ("npx", "jest", "-u"), "-u"),
    (JEST, ("jest", "--updateSnapshot"), "--updateSnapshot"),
    (JEST, ("jest", "--update-snapshot"), "--update-snapshot"),
    (JEST, ("jest", "--collectTests"), "--collectTests"),
    # vitest 5.0.5
    (VITEST, ("npx", "vitest", "run", "--update"), "--update"),
    (VITEST, ("vitest", "-u"), "-u"),
    (VITEST, ("vitest", "--update=all"), "--update"),
    (VITEST, ("vitest", "--update=false"), "--update"),
    (VITEST, ("vitest", "--mergeReports"), "--mergeReports"),
    (VITEST, ("vitest", "--merge-reports=.vitest-reports"), "--merge-reports"),
    (VITEST, ("vitest", "--mergeReports=false"), "--mergeReports"),
    (
        VITEST,
        ("vitest", "--dangerouslyIgnoreUnhandledErrors"),
        "--dangerouslyIgnoreUnhandledErrors",
    ),
    # node --test
    (NODE_TEST, ("node", "--test", "--test-update-snapshots"), "--test-update-snapshots"),
    (NODE_TEST, ("node", "--test", "--test-rerun-failures=state.json"), "--test-rerun-failures"),
    # node reads `=false` as on, and rewrites the snapshot.
    (NODE_TEST, ("node", "--test", "--test-update-snapshots=false"), "--test-update-snapshots"),
    # After the files: Node 26.12.0 reads an option there as before them; Node 24.10.0 reads none
    # there (measured: the run as without it), so there the refusal is only the safe side.
    (
        NODE_TEST,
        ("node", "--test", "a.test.mjs", "--test-update-snapshots"),
        "--test-update-snapshots",
    ),
    (
        NODE_TEST,
        ("node", "--test", "a.test.mjs", "b.test.mjs", "--test-rerun-failures=s.json"),
        "--test-rerun-failures",
    ),
]


@pytest.mark.parametrize(
    ("adapter", "argv", "named"),
    REFUSALS,
    ids=[f"{adapter.name}:{'_'.join(argv[1:])}" for adapter, argv, _ in REFUSALS],
)
def test_each_report_steering_option_is_refused(
    tmp_path: Path, adapter: Adapter, argv: tuple[str, ...], named: str
) -> None:
    # Refused before anything is resolved: no `PATH` holds a runner here. Mutations (declared):
    # `--collectTests`, `--mergeReports`, `--test-rerun-failures` and `--test-update-snapshots`
    # each left off its list; node's words read only up to its first file -> each one's case is
    # planned or unresolved.
    assert planned(adapter, argv, tmp_path) == Refused(REFUSED_OPTION, named)


FREE: list[tuple[Adapter, tuple[str, ...]]] = [
    (JEST, ("jest", "--reporters=default")),
    (JEST, ("jest", "--passWithNoTests")),
    (JEST, ("jest", "--ci")),
    # Off, jest writes a snapshot that is missing and passes it, as it does by default wherever
    # `CI` is unset or false: a snapshot the run writes is the bound's.
    (JEST, ("jest", "--no-ci")),
    (JEST, ("jest", "--ci=false")),
    (JEST, ("jest", "--ci", "false")),
    (JEST, ("jest", "--no-watch")),
    (JEST, ("jest", "--watchAll=false")),
    (JEST, ("jest", "--updateSnapshot=false")),
    (JEST, ("jest", "-t", "passes")),
    (JEST, ("jest", "--testFailureExitCode=0")),
    (JEST, ("jest", "-c", "ci/jest.config.js")),
    # A configuration's own text: it is the command's, as a `jest.config.js` would be.
    (JEST, ("jest", "--config", '{"testResultsProcessor": "./p.js"}')),
    (JEST, ("jest", "-c{}")),
    # A results processor sees the results before they are written; an honest one (jest-junit's)
    # returns them as they are (measured on 30.5.2: the report's counts unchanged).
    (JEST, ("jest", "--testResultsProcessor=./p.js")),
    (JEST, ("jest", "--test-results-processor", "./p.js")),
    (JEST, ("jest", "--", "--json")),
    # The report's own options, the command's beside the adapter's: the adapter's come last and
    # win, or the run ends `not proven` (`no-report`, `report-malformed`), never `proved` for
    # tests that did not earn it.
    (JEST, ("jest", "--json")),
    (JEST, ("jest", "--no-json")),
    (JEST, ("npx", "jest", "--outputFile=x")),
    (JEST, ("jest", "--output-file", "x")),
    (VITEST, ("vitest", "run", "--reporter=verbose")),
    (VITEST, ("vitest", "--update=none")),
    (VITEST, ("vitest", "--no-update")),
    # vitest's own default where `CI` is unset: a missing snapshot is written, a failing one
    # fails.
    (VITEST, ("vitest", "--update=new")),
    (VITEST, ("vitest", "--no-watch")),
    (VITEST, ("vitest", "--retry=2")),
    (VITEST, ("vitest", "-t", "passes")),
    (VITEST, ("vitest", "--passWithNoTests")),
    (VITEST, ("vitest", "-c", "vitest.ci.config.js")),
    (VITEST, ("vitest", "--", "--outputFile=x")),
    (VITEST, ("vitest", "run", "--outputFile=x")),
    (VITEST, ("npx", "vitest", "run", "--outputFile.json=x")),
    (VITEST, ("vitest", "--output-file.junit", "x")),
    (NODE_TEST, ("node", "--import=tsx", "--test")),
    (NODE_TEST, ("node", "--import", "tsx", "--test")),
    (NODE_TEST, ("node", "-r", "./.pnp.cjs", "--loader", "./l.mjs", "--test")),
    (NODE_TEST, ("node", "--test", "--test-name-pattern=passes", "--test-only")),
    (NODE_TEST, ("node", "--test", "--test-force-exit", "--test-isolation=none")),
    (NODE_TEST, ("node", "--test", "--", "--watch")),
    # A reporter given its own destination: node writes the adapter's report beside it (measured
    # on Node 24.10.0, the report's counts unchanged). One without it stops node before any test
    # runs, so the adapter's report is never written: `not proven` (`no-report`).
    (NODE_TEST, ("node", "--test", "--test-reporter=spec", "--test-reporter-destination=stdout")),
    (NODE_TEST, ("node", "--test-reporter", "tap", "--test-reporter-destination", "x", "--test")),
    (NODE_TEST, ("node", "--test", "--test-reporter=dot")),
    (NODE_TEST, ("node", "--test", "--test-reporter-destination=x")),
    # What node loads or runs is the command's: `--env-file`, a configuration file, code it spells.
    (NODE_TEST, ("node", "--env-file=.env", "--test")),
    (NODE_TEST, ("node", "--env-file-if-exists", ".env", "--test")),
    (NODE_TEST, ("node", "--experimental-config-file=c.json", "--test")),
    (NODE_TEST, ("node", "--test", "--import=data:text/javascript,x")),
    (NODE_TEST, ("node", "--eval=x", "--test")),
    (NODE_TEST, ("node", "--test", "-p", "1")),
]


@pytest.mark.parametrize(
    ("adapter", "argv"),
    FREE,
    ids=[f"{adapter.name}:{'_'.join(argv[1:])}" for adapter, argv in FREE],
)
def test_every_other_option_is_free(
    tmp_path: Path, adapter: Adapter, argv: tuple[str, ...]
) -> None:
    # Mutations (declared): `--update=none` and `--update=new` read as an update -> each one's
    # case is refused.
    _, _, node = installed(tmp_path)
    (tmp_path / "ci").mkdir()
    assert isinstance(planned(adapter, argv, tmp_path, path=str(node.parent)), Plan)


NEVER_ENDING: list[tuple[Adapter, tuple[str, ...], str]] = [
    (JEST, ("jest", "--watch"), "--watch"),
    (JEST, ("npx", "jest", "--watchAll"), "--watchAll"),
    (JEST, ("jest", "--watch-all"), "--watch-all"),
    (JEST, ("jest", "--watch", "0"), "--watch"),
    (VITEST, ("vitest", "--watch"), "--watch"),
    (VITEST, ("vitest", "run", "-w"), "-w"),
    (NODE_TEST, ("node", "--watch", "--test"), "--watch"),
    (NODE_TEST, ("node", "--test", "--watch-path=src"), "--watch-path"),
    (NODE_TEST, ("node", "--test", "a.test.mjs", "--watch"), "--watch"),
    # node watches under `--watch=false` too.
    (NODE_TEST, ("node", "--test", "--watch=false"), "--watch"),
    # node holds the code until a debugger attaches (measured on Node 24.10.0, under `--test` too).
    (NODE_TEST, ("node", "--inspect-brk", "--test"), "--inspect-brk"),
    (NODE_TEST, ("node", "--inspect-wait=0", "--test"), "--inspect-wait"),
]


@pytest.mark.parametrize(
    ("adapter", "argv", "named"),
    NEVER_ENDING,
    ids=[f"{adapter.name}:{'_'.join(argv[1:])}" for adapter, argv, _ in NEVER_ENDING],
)
def test_a_watch_mode_is_not_proven_for_it_never_ends(
    tmp_path: Path, adapter: Adapter, argv: tuple[str, ...], named: str
) -> None:
    # A watch mode moves no report and forges no pass: it waits for changes after the run, which
    # under `prove` (standard input `/dev/null`) is past any time limit, so nothing could count a
    # report. Not proven before anything is resolved: no `PATH` holds a runner here. Mutations
    # (declared): each runner's watch modes planned; a watch mode refused -> each case differs.
    assert planned(adapter, argv, tmp_path) == Unresolved(NEVER_ENDS, never_detail(named))


@pytest.mark.parametrize(
    ("adapter", "argv", "named"),
    NEVER_ENDING,
    ids=[f"{adapter.name}:{'_'.join(argv[1:])[:40]}" for adapter, argv, _ in NEVER_ENDING],
)
def test_a_watch_mode_s_detail_fits_the_line(
    tmp_path: Path, adapter: Adapter, argv: tuple[str, ...], named: str
) -> None:
    # The receipt's line clips a detail past `CLIPPED_CHARS`; a watch mode's is never cut.
    # Mutation (declared): the detail lengthened past the clip -> `--watch-path`'s is cut.
    got = planned(adapter, argv, tmp_path)
    assert isinstance(got, Unresolved)
    assert len(got.detail) <= CLIPPED_CHARS, got.detail


@pytest.mark.parametrize(
    "node_options",
    [
        "--test-rerun-failures=state.json",
        "--max-old-space-size=4096 --test-rerun-failures state.json",
        '--title="a b" --test-rerun-failures=s.json',
    ],
    ids=["plain", "spaced", "after-a-quoted-value"],
)
def test_a_rerun_of_failures_in_node_options_is_refused(tmp_path: Path, node_options: str) -> None:
    # Node 24.10.0 reads `--test-rerun-failures` from `NODE_OPTIONS` as from the command, so a
    # state file a green run wrote reports the failing tests passed there too, inherited or
    # assigned; the variable is read as words split at white space. Mutation (declared):
    # `NODE_OPTIONS` not read -> each case is planned.
    node = node_on_path(tmp_path / "bin")
    variables = {"NODE_OPTIONS": node_options}
    got = planned(
        NODE_TEST, ["node", "--test"], tmp_path, path=str(node.parent), variables=variables
    )
    assert got == Refused(REFUSED_OPTION, "--test-rerun-failures")
    # A reporter there is free: unpaired, node stops before any test runs, `not proven`.
    free = {"NODE_OPTIONS": "--test-reporter=dot"}
    plan = planned(NODE_TEST, ["node", "--test"], tmp_path, path=str(node.parent), variables=free)
    assert isinstance(plan, Plan), plan


def test_an_assigned_rerun_of_failures_in_node_options_is_refused(tmp_path: Path) -> None:
    # The command's own assignment is in the run's environment the plan reads.
    node = node_on_path(tmp_path / "bin")
    argv = ["NODE_OPTIONS=--test-rerun-failures=s.json", "node", "--test"]
    got = prove(argv, cwd=tmp_path, environ={"PATH": str(node.parent)}, timeout=60)
    assert (got.verdict, got.reason, got.detail) == (
        REFUSED,
        REFUSED_OPTION,
        "--test-rerun-failures",
    )


@pytest.mark.parametrize(
    ("argv", "named"),
    [
        (["node", "--test"], "--inspect-brk"),
        (["npx", "jest"], "--inspect-brk"),
        (["node", "node_modules/jest/bin/jest.js"], "--inspect-brk"),
    ],
)
def test_a_debugger_wait_in_node_options_never_ends(
    tmp_path: Path, argv: list[str], named: str
) -> None:
    # `NODE_OPTIONS` reaches every node the run starts, npx's and the runner's, so a debugger
    # wait there holds the run as one on the command line does (measured on Node 24.10.0: past
    # any time limit). Mutation: none -- without it the run is `not proven` all the same, past
    # its time limit, so the reading saves only the wait.
    project = tmp_path / "project"
    _, _, node = installed(project)
    variables = {"NODE_OPTIONS": "--no-warnings --inspect-brk"}
    adapter = NODE_TEST if argv[:2] == ["node", "--test"] else JEST
    got = planned(adapter, argv, project, path=str(node.parent), variables=variables)
    assert got == Unresolved(NEVER_ENDS, WAITS_DETAIL.format(option=named))


@pytest.mark.parametrize(
    ("adapter", "argv", "named"),
    [
        (JEST, ("jest", "--watch", "-u"), "-u"),
        (VITEST, ("vitest", "-w", "--mergeReports"), "--mergeReports"),
        (
            NODE_TEST,
            ("node", "--watch", "--test", "--test-update-snapshots"),
            "--test-update-snapshots",
        ),
    ],
    ids=[JEST.name, VITEST.name, NODE_TEST.name],
)
def test_a_refusal_wins_over_a_watch_mode(
    tmp_path: Path, adapter: Adapter, argv: tuple[str, ...], named: str
) -> None:
    assert planned(adapter, argv, tmp_path) == Refused(REFUSED_OPTION, named)


def test_a_watch_mode_s_receipt_says_it_never_ends(tmp_path: Path) -> None:
    # The receipt's words fit every arm an adapter's unresolved plan stands for: not only an entry
    # point that did not resolve. Mutation (declared, core): the words say the entry point did
    # not resolve -> this line says so of a watch mode.
    got = prove(["npx", "jest", "--watch"], cwd=tmp_path, environ={"PATH": ""}, timeout=60)
    detail = NEVER_ENDS_DETAIL.format(option="--watch")
    assert (got.verdict, got.reason, got.detail, got.exit_code) == (
        NOT_PROVEN,
        NEVER_ENDS,
        detail,
        None,
    )
    shown = line(got)
    assert shown.startswith(f"not proven: the runner's adapter cannot plan this run ({NEVER_ENDS})")
    assert detail in shown


def test_node_import_is_free(tmp_path: Path) -> None:
    node = node_on_path(tmp_path / "bin")
    got = plan_of(NODE_TEST, ["node", "--import=tsx", "--test"], tmp_path, path=str(node.parent))
    assert got.argv[-2:] == ("--import=tsx", "--test")


# --- Through prove, with a node that writes the report it is told to -------------------------

GREEN_RESULTS = (
    '{"testResults": [{"status": "passed", "assertionResults": [{"status": "passed"}]}]}'
)
GREEN_JUNIT = '<testsuites><testcase name="a" classname="test" file="/w/a.test.mjs"/></testsuites>'
FAKE_NODE = f"""#!/bin/sh
# A stand-in for node: write a green report where the run was told to, then exit 0.
for word in "$@"; do
  case "$word" in
    --outputFile=*) printf '%s' '{GREEN_RESULTS}' > "${{word#--outputFile=}}" ;;
    --test-reporter-destination=stdout) ;;
    --test-reporter-destination=*)
      printf '%s' '{GREEN_JUNIT}' > "${{word#--test-reporter-destination=}}" ;;
  esac
done
exit 0
"""


def fake_node(where: Path, text: str = FAKE_NODE) -> Path:
    """A stand-in `node` holding `text` in `where`, and the same script as the `npx`, `jest` and
    `vitest` beside it, each run as typed; the `node`."""
    for name in ("npx", "jest", "vitest"):
        executable(where / name, text)
    return executable(where / "node", text)


def through_prove(argv: Sequence[str], cwd: Path, environ: Mapping[str, str]) -> Receipt:
    return prove(argv, cwd=cwd, environ=environ, timeout=60)


def test_npx_jest_names_its_program_and_the_untracked_test_files(tmp_path: Path) -> None:
    project = tmp_path / "project"
    jest_package(project / "node_modules")
    bin_link(project / "node_modules", "jest", "../jest/bin/jest.js")
    node = fake_node(tmp_path / "bin")
    for name in ("package.json", ".npmrc", "jest.config.js", "three.test.js"):
        (project / name).write_text("{}\n", encoding="utf-8")
    git(project, "init", "-q")
    (project / ".gitignore").write_text("node_modules/\n", encoding="utf-8")
    git(project, "add", ".gitignore", "package.json", ".npmrc", "jest.config.js")
    git(project, "commit", "-q", "-m", "first")
    got = through_prove(["npx", "jest"], project, {"PATH": str(node.parent)})
    assert (got.verdict, got.counts, got.runner) == (PROVED, Counts(1, 0, 0), "jest")
    assert got.program == os.path.realpath(node.parent / "npx")
    assert f"runner jest at {clipped(got.program)}" in line(got)
    assert got.untracked == ("three.test.js",)


ESM_FLAG = "--experimental-vm-modules"
# A stand-in for node that writes its green report only where the run's `NODE_OPTIONS` is jest's
# ES modules recipe, so the verdict says whether the run got it.
NODE_UNDER_OPTIONS = FAKE_NODE.replace(
    "for word in", f'[ "$NODE_OPTIONS" = "{ESM_FLAG}" ] || exit 3\nfor word in', 1
)


@pytest.mark.parametrize(
    ("argv", "inherited"),
    [
        (["NODE_OPTIONS=" + ESM_FLAG, "npx", "jest"], {}),
        (["env", "NODE_OPTIONS=" + ESM_FLAG, "vitest"], {}),
        (["npx", "jest"], {"NODE_OPTIONS": ESM_FLAG}),
        (["node", "--test"], {"NODE_OPTIONS": ESM_FLAG}),
    ],
    ids=["assigned-jest", "assigned-vitest", "inherited-jest", "inherited-node-test"],
)
def test_node_options_reaches_the_run(
    tmp_path: Path, argv: list[str], inherited: Mapping[str, str]
) -> None:
    # jest's documented recipe for ES modules is `NODE_OPTIONS=--experimental-vm-modules npx
    # jest`: planned and run as typed, assigned or inherited, and nothing is removed. Mutation
    # (declared): `NODE_OPTIONS` in the jest and vitest adapters' forging set -> the assigned
    # cases are refused, the inherited jest one `not proven`.
    project = tmp_path / "project"
    jest_package(project / "node_modules")
    vitest_package(project / "node_modules")
    node = fake_node(tmp_path / "bin", NODE_UNDER_OPTIONS)
    got = through_prove(argv, project, {"PATH": str(node.parent), **inherited})
    assert (got.verdict, got.reason, got.scrubbed, got.exit_code) == (PROVED, "", (), 0)


def test_npm_test_is_not_proven(tmp_path: Path) -> None:
    got = through_prove(["npm", "test"], tmp_path, {"PATH": ""})
    assert (got.verdict, got.reason, got.runner) == (NOT_PROVEN, NOT_RECOGNISED, None)


# --- Real runs ------------------------------------------------------------------------------

FIXTURE_TESTS = {
    "jest": FIXTURE / "jest" / "three.test.js",
    "vitest": FIXTURE / "vitest" / "three.test.js",
    "node-test": FIXTURE / "node-test" / "three.test.mjs",
}
RUNNERS = list(COMMANDS)


def real(cwd: Path, *argv: str, **variables: str) -> Receipt:
    """`argv` proved in `cwd` with the `node` on `PATH` first."""
    node = runner_directory("node")
    environ = {**os.environ, "PATH": os.pathsep.join([str(node), os.environ.get("PATH", "")])}
    environ.pop("NODE_OPTIONS", None)
    return through_prove(argv, cwd, {**environ, **variables})


NPX_PATH_TEST = (
    'test("node_modules/.bin is on PATH", () => {\n'
    '  expect(process.env.PATH.split(":").some((p) => p.endsWith("node_modules/.bin")))'
    ".toBe(true);\n"
    "});\n"
)


@needs_packages
@pytest.mark.parametrize(
    "argv", [("npx", "jest"), ("npx", "--no-install", "jest")], ids=["npx", "npx-no-install"]
)
def test_npx_runs_as_typed_with_its_bin_directories_on_path(
    tmp_path: Path, argv: tuple[str, ...]
) -> None:
    # npx puts every `node_modules/.bin` above the directory on `PATH` before it runs the runner,
    # and a test may rely on it (measured with npm 11.6.0 on Node 24.10.0: it passes as typed);
    # run as typed, it passes under `prove` too.
    project = js_project(tmp_path / "p", "jest", NPX_PATH_TEST)
    got = real(project, *argv)
    assert (got.verdict, got.reason, got.counts, got.exit_code) == (PROVED, "", Counts(1, 0, 0), 0)
    assert got.program == os.path.realpath(runner_directory("node") / "npx")


_ESM = (
    'import { strict as assert } from "node:assert";\ntest("ok", () => { assert.equal(1, 1); });\n'
)


@needs_packages
@pytest.mark.parametrize(
    ("argv", "inherited"),
    [
        (("NODE_OPTIONS=--experimental-vm-modules", "npx", "jest"), {}),
        (("npx", "jest"), {"NODE_OPTIONS": "--experimental-vm-modules"}),
        (("node", "--experimental-vm-modules", "node_modules/jest/bin/jest.js"), {}),
        (("NODE_OPTIONS=--experimental-vm-modules", "./node_modules/.bin/jest"), {}),
    ],
    ids=["assigned", "inherited", "node-flag-in-front", "bin-link"],
)
def test_jest_s_esm_recipe_is_proved(
    tmp_path: Path, argv: tuple[str, ...], inherited: Mapping[str, str]
) -> None:
    # jest's documented recipe for ES modules is `NODE_OPTIONS=--experimental-vm-modules npx
    # jest`: run as typed, assigned or inherited, as is Node's flag in front of jest's entry and
    # npm's `.bin` link.
    project = js_project(tmp_path / "p", "vitest", _ESM)
    got = real(project, *argv, **inherited)
    assert (got.verdict, got.reason, got.counts, got.exit_code) == (PROVED, "", Counts(1, 0, 0), 0)
    assert got.scrubbed == ()


@needs_packages
def test_vitest_related_is_proved(tmp_path: Path) -> None:
    # `vitest related` passes as typed, and so under `prove`: `related` is kept, with `--run`.
    project = js_project(tmp_path / "p", "vitest")
    (project / "src").mkdir()
    (project / "src" / "a.js").write_text("export const one = () => 1;\n", encoding="utf-8")
    (project / "a.test.js").write_text(
        VITEST_HEAD
        + 'import { one } from "./src/a.js";\ntest("one", () => expect(one()).toBe(1));\n',
        encoding="utf-8",
    )
    (project / "b.test.js").write_text(
        VITEST_HEAD + 'test("other", () => expect(2).toBe(2));\n', encoding="utf-8"
    )
    got = real(project, "npx", "vitest", "related", "src/a.js")
    assert (got.verdict, got.reason, got.counts, got.exit_code) == (PROVED, "", Counts(1, 0, 0), 0)


@needs_packages
@pytest.mark.parametrize("runner", RUNNERS)
def test_the_fixture_s_three_tests_fail(tmp_path: Path, runner: str) -> None:
    project = js_project(tmp_path / "p", runner, FIXTURE_TESTS[runner].read_text(encoding="utf-8"))
    got = real(project, *COMMANDS[runner])
    assert (got.verdict, got.reason, got.counts) == (FAILED, FAILING, Counts(1, 1, 1))


SNAPSHOT_TEST = 'test("s", () => { expect({ a: 1 }).toMatchSnapshot(); });\n'


@needs_packages
@pytest.mark.parametrize(
    ("runner", "argv", "verdict", "counts"),
    [
        ("jest", ("npx", "jest"), FAILED, Counts(0, 1, 0)),
        ("jest", ("npx", "jest", "--no-ci"), PROVED, Counts(1, 0, 0)),
        ("jest", ("npx", "jest", "--ci=false"), PROVED, Counts(1, 0, 0)),
        ("jest", ("CI=false", "npx", "jest"), PROVED, Counts(1, 0, 0)),
        ("vitest", ("npx", "vitest", "run"), FAILED, Counts(0, 1, 0)),
        ("vitest", ("npx", "vitest", "run", "--update=new"), PROVED, Counts(1, 0, 0)),
    ],
    ids=["jest", "jest-no-ci", "jest-ci-false", "jest-CI-false", "vitest", "vitest-update-new"],
)
def test_a_snapshot_the_run_writes_is_the_bound_s(
    tmp_path: Path, runner: str, argv: tuple[str, ...], verdict: Verdict, counts: Counts
) -> None:
    # The snapshot is missing and `CI=true` is inherited: jest off CI and vitest's `--update=new`
    # write it and pass, as each does by default where `CI` is unset or false, so a refusal of
    # either would stop nobody; what the run writes is the bound's.
    head = VITEST_HEAD if runner == "vitest" else ""
    project = js_project(tmp_path / "p", runner, head + SNAPSHOT_TEST)
    got = real(project, *argv, CI="true")
    assert (got.verdict, got.counts) == (verdict, counts)
    assert (project / "__snapshots__").is_dir() is (verdict == PROVED)


@needs_packages
def test_a_non_matching_name_pattern_fails(tmp_path: Path) -> None:
    # node reports the file as one passed testcase; the plan drops it, whether node names the file
    # (26.12.0) or not (24.10.0).
    project = js_project(tmp_path / "p", "node-test", NODE_PASSING)
    got = real(project, "node", "--test", "--test-name-pattern=no_such_test")
    assert (got.verdict, got.reason, got.counts, got.exit_code) == (
        FAILED,
        NONE_RAN,
        Counts(0, 0, 0),
        0,
    )


@needs_packages
@pytest.mark.parametrize(
    ("argv", "counts"),
    [
        (("node", "--test"), Counts(1, 0, 0)),
        (("node", "--test", "--test-name-pattern=no_such_test"), Counts(0, 0, 0)),
        (("node", "--test", "test/deep/empty.test.mjs"), Counts(0, 0, 0)),
    ],
    ids=["both", "pattern", "the-empty-one"],
)
def test_a_nested_file_s_whole_file_testcase_is_not_counted(
    tmp_path: Path, argv: tuple[str, ...], counts: Counts
) -> None:
    # A file in a subdirectory: node names its whole-file testcase by the path from the run's
    # directory (`test/deep/empty.test.mjs`, measured on Node 24.10.0), not by the file's name.
    project = js_project(tmp_path / "p", "node-test")
    (project / "test" / "deep").mkdir(parents=True)
    (project / "test" / "real.test.mjs").write_text(
        NODE_HEAD + 'test("passes", () => { assert.ok(true); });\n', encoding="utf-8"
    )
    (project / "test" / "deep" / "empty.test.mjs").write_text("// no test\n", encoding="utf-8")
    got = real(project, *argv)
    assert got.counts == counts
    assert got.verdict == (PROVED if counts.passed else FAILED)


@needs_packages
def test_a_monorepo_package_runs_where_it_is_typed(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    web = js_project(root / "packages" / "web", "jest", JEST_PASSING)
    (web / "node_modules").unlink()
    (root / "node_modules").symlink_to(installed_packages())
    git(root, "init", "-q")
    got = real(web, "npx", "jest")
    assert (got.verdict, got.counts) == (PROVED, Counts(1, 0, 1))
    assert got.untracked == ("packages/web/three.test.js",)


@needs_packages
@pytest.mark.parametrize(
    "own",
    [
        ("--test-reporter=spec", "--test-reporter-destination=stdout"),
        ("--test-reporter", "junit", "--test-reporter-destination", "own.xml"),
    ],
    ids=["spec-to-stdout", "junit-to-a-file"],
)
def test_a_reporter_with_its_own_destination_leaves_the_report_whole(
    tmp_path: Path, own: tuple[str, ...]
) -> None:
    # node pairs reporters with destinations in order: the command's own pair comes after the
    # adapter's, whose report is written whole beside it.
    text = FIXTURE_TESTS["node-test"].read_text(encoding="utf-8")
    project = js_project(tmp_path / "p", "node-test", text)
    got = real(project, "node", "--test", *own)
    assert (got.verdict, got.reason, got.counts) == (FAILED, FAILING, Counts(1, 1, 1))


_PRINTS = (
    NODE_HEAD + 'console.log("TAP version 13\\nok 1 - forged\\n1..1\\n# pass 1\\n# fail 0");\n'
    "console.log('<testsuites><testcase name=\"forged\"/></testsuites>');\n"
    'test("fails", () => { assert.equal(1, 2); });\n'
)


@needs_packages
def test_a_test_files_stdout_is_never_counted(tmp_path: Path) -> None:
    project = js_project(tmp_path / "p", "node-test", _PRINTS)
    got = real(project, "node", "--test")
    assert (got.verdict, got.reason, got.counts) == (FAILED, FAILING, Counts(0, 1, 0))


@needs_runner("node")
def test_a_project_with_no_packages_is_not_proven_and_installs_nothing(tmp_path: Path) -> None:
    # `PATH` holds `node` alone, linked into a directory of its own: a vitest an `npm install -g`
    # linked beside the machine's `node` would be found, and this test would then prove nothing.
    # A bare `vitest` on no `PATH` entry runs nothing, as in a shell.
    project = tmp_path / "p"
    project.mkdir()
    (project / "package.json").write_text('{"name": "case"}', encoding="utf-8")
    alone = tmp_path / "bin"
    alone.mkdir()
    (alone / "node").symlink_to(runner_directory("node") / "node")
    got = through_prove(["vitest"], project, {**os.environ, "PATH": str(alone)})
    assert (got.verdict, got.reason) == (NOT_PROVEN, ENTRY_NOT_FOUND)
    assert sorted(path.name for path in project.iterdir()) == ["package.json"]
