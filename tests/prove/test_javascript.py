"""The JavaScript adapters: what jest's, vitest's and `node --test`'s recognise, how each plans the
command as typed and names its entry, what each refuses, and what a real run under each proves.

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
from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from pathlib import Path

import pytest

from stayfixed.printed import CLIPPED_CHARS, clipped
from stayfixed.profiles.javascript.adapters import (
    ADAPTERS,
    CONFIGS,
    JEST_DISCOVERY,
    JEST_REPORT,
    NEVER_ENDS_DETAIL,
    NO_TEST_RUN,
    NO_TEST_RUN_DETAIL,
    NODE_DISCOVERY,
    NODE_REPORT,
    NOT_A_LINK,
    NOT_THE_ENTRY,
    UNRESOLVED,
    VITEST_DISCOVERY,
    VITEST_REPORT,
    JestAdapter,
    NodeTestAdapter,
    VitestAdapter,
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
    ALL_SKIPPED,
    FAILING,
    NONE_RAN,
    NOT_RECOGNISED,
    Receipt,
    Verdict,
    line,
    prove,
)
from tests.gitfixture import git
from tests.prove.real_runners import (
    installed_packages,
    needs_packages,
    needs_runner,
    runner_directory,
)

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
    root: Path | None = None,
    path: str = "",
    launch: Sequence[str] = (),
    variables: Mapping[str, str] | None = None,
) -> Plan | Refused | Unresolved:
    return adapter.plan(
        launch,
        command,
        cwd=cwd,
        root=root if root is not None else cwd,
        scratch=cwd / "scratch",
        environ={"PATH": path, **(variables or {})},
    )


def plan_of(
    adapter: Adapter,
    command: Sequence[str],
    cwd: Path,
    *,
    root: Path | None = None,
    path: str = "",
) -> Plan:
    got = planned(adapter, command, cwd, root=root, path=path)
    assert isinstance(got, Plan), got
    return got


def installed(project: Path) -> tuple[Path, Path, Path]:
    """`project` with jest and vitest installed as npm installs them, and a `node`, an `npx`, a
    `jest` and a `vitest` in a directory of its own for `PATH`: the jest entry, the vitest entry
    and the `node`."""
    modules = project / "node_modules"
    tools = project / ".tools"
    executable(tools / "jest")
    executable(tools / "vitest")
    return jest_package(modules), vitest_package(modules), node_on_path(tools)


# --- What is recognised ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("command", "adapter"),
    [
        (["jest"], JEST),
        (["npx", "jest", "-i"], JEST),
        (["npx", "--no-install", "jest"], JEST),
        (["npx", "--no", "jest"], JEST),
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
    # What a script runs is the script's; `npx` is read only bare or with `--no-install` or
    # `--no`, and with a runner's bare name. Mutations (declared): `npm test` read as jest -> the
    # first case is;
    # a word that can only be node's script read past -> `node x.js <entry>` is.
    assert [each.name for each in ADAPTERS if each.recognises(command)] == []


def test_the_adapters_this_stack_ships() -> None:
    # No variable is refused or removed: `NODE_OPTIONS` reaches the run as it does outside it.
    assert [adapter.name for adapter in ADAPTERS] == ["jest", "vitest", "node-test"]
    assert JEST.forging == VITEST.forging == NODE_TEST.forging == frozenset()


# --- How the entry point resolves -----------------------------------------------------------


def test_npx_runs_as_typed(tmp_path: Path) -> None:
    # The run is the command as typed, `npx` and its option found on `PATH`, the report's options
    # after the runner's arguments: npx puts every `node_modules/.bin` above the directory on
    # `PATH`, which a test may need (measured: npm 11.6.0 on Node 24.10.0), and reads `.npmrc`.
    # The entry npx finds is named on the receipt. Mutations (declared): `npx` dropped from the
    # typed words -> the plan runs `jest` alone; the entry left unnamed -> `entry` is `None`.
    project = tmp_path / "project"
    entry, _, node = installed(project)
    npx = node.parent / "npx"
    got = plan_of(JEST, ["npx", "jest", "-i"], project, path=str(node.parent))
    report = project / "scratch" / JEST_REPORT
    assert got == Plan(
        argv=(str(npx), "jest", "-i", "--json", f"--outputFile={report}"),
        kind=ReportKind.RESULTS_JSON,
        source=ReportSource.FILE,
        report=report,
        discovery=("*.test.*", "*.spec.*", "__tests__/*"),
        configs=("package.json", ".npmrc", "jest.config.*", "vitest.config.*", "vite.config.*"),
        entry=entry,
    )
    assert (got.discovery, got.configs) == (JEST_DISCOVERY, CONFIGS)
    offline = plan_of(JEST, ["npx", "--no-install", "jest"], project, path=str(node.parent))
    assert offline.argv == (str(npx), "--no-install", "jest", "--json", f"--outputFile={report}")
    bare = plan_of(JEST, ["jest", "-i"], project, path=str(node.parent))
    assert bare.argv == (str(node.parent / "jest"), "-i", "--json", f"--outputFile={report}")
    # The program a bare runner on `PATH` is, is the receipt's to name: no entry beside it.
    assert bare.entry is None


def test_vitest_without_run_runs_once(tmp_path: Path) -> None:
    # `run` first, so it runs once and never watches; `--reporter=default` for the person where
    # the command names no reporter of its own. Mutations (declared): `run` never added -> the
    # first plan starts at `-t`; the default reporter added beside the command's own -> the third
    # plan holds two.
    project = tmp_path / "project"
    _, entry, node = installed(project)
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
    assert (got.discovery, got.configs, got.drop) == (VITEST_DISCOVERY, CONFIGS, None)
    again = plan_of(VITEST, ["npx", "vitest", "run", "a"], project, path=path)
    assert again.argv == (npx, "vitest", "run", "a", *ours, "--reporter=default")
    assert again.entry == entry
    named = plan_of(VITEST, ["vitest", "run", "--reporter", "dot"], project, path=path)
    assert named.argv == (vitest, "run", "--reporter", "dot", *ours)


def test_node_s_own_options_go_in_front_of_the_runner_s_entry(tmp_path: Path) -> None:
    # jest's documented ESM recipe passes `--experimental-vm-modules` to node, here or in
    # `NODE_OPTIONS`. The entry named must be the one its package's `bin` names; the run is the
    # words as typed, and the receipt names the entry by its realpath; node's preload of a file is
    # named among the configuration files. Mutation (declared): the node shape not read -> no
    # plan.
    project = tmp_path / "project"
    jest_entry, _, node = installed(project)
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
    assert (got.argv[0], got.entry) == (str(node), jest_entry)
    assert got.configs == (*CONFIGS, os.path.realpath(project / "setup.cjs"))
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
    # the first word node may run as its script that is the file its package's `bin` names
    # (measured on Node 24.10.0: `--max-old-space-size 4096` is refused by node itself, exit 9,
    # and so is `not proven` under `prove` as outside it). Mutation (declared): node's options
    # read only up to the first that takes a value -> `--max-old-space-size 4096` is no plan.
    project = tmp_path / "project"
    entry, _, node = installed(project)
    command = ["node", *node_words, "node_modules/jest/bin/jest.js", "-i"]
    got = plan_of(JEST, command, project, path=str(node.parent))
    assert got.argv[: len(command)] == (str(node), *command[1:])
    assert got.entry == entry


def test_the_entry_is_the_first_word_that_is_the_package_s_bin(tmp_path: Path) -> None:
    # A preload's value may be a path into the runner's own package; the entry is the first word
    # node may run as its script that is the file the package's `bin` names. Mutation (declared):
    # the first word shaped like an entry taken -> `NOT_THE_ENTRY`.
    project = tmp_path / "project"
    entry, _, node = installed(project)
    executable(project / "node_modules" / "jest" / "setup.js")
    command = ["node", "-r", "node_modules/jest/setup.js", "node_modules/jest/bin/jest.js", "-i"]
    got = plan_of(JEST, command, project, path=str(node.parent))
    assert got.argv[:5] == (str(node), *command[1:])
    assert got.entry == entry


def test_a_node_named_by_its_path_runs_the_runner_s_entry(tmp_path: Path) -> None:
    project = tmp_path / "project"
    entry, _, _ = installed(project)
    node = executable(tmp_path / "opt" / "node")
    got = plan_of(JEST, [str(node), "node_modules/jest/bin/jest.js"], project)
    assert (got.argv[:2], got.entry) == ((str(node), "node_modules/jest/bin/jest.js"), entry)


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


# The values a preload runs with, unnamed: a package's name, a URL of a scheme but `file:` (code
# the command spells, which is the command's to run), and a file whose reading is in doubt -- a
# schemeless value with a `.` or `..` segment, a relative `file:` URL or another host's, and a path
# holding a character node may read otherwise (`%`, `?` and `#` in a URL, a `\`, a control
# character).
PRELOADS_UNNAMED = [
    "tsx",
    "ts-node/register",
    "@swc-node/register/esm",
    "data:text/javascript,process.exit(0)",
    "node:fs",
    "https://example.com/l.mjs",
    "pkg/../../evil.mjs",
    "a/..",
    ".pnp.cjs",
    "file:rel.mjs",
    "file:../up/u.mjs",
    "file://elsewhere/abs/no.mjs",
    "./a%20b.mjs",
    "./x.mjs?v=1",
    "../y.mjs#h",
    "./back\\slash.mjs",
    "./tab\tname.mjs",
    "./line\nbreak.mjs",
    "x://]",
    "http://[x",
    "",
]


@pytest.mark.parametrize("value", PRELOADS_UNNAMED, ids=[repr(v) for v in PRELOADS_UNNAMED])
def test_a_preload_whose_file_is_in_doubt_runs_unnamed(tmp_path: Path, value: str) -> None:
    # Naming a preloaded file is the receipt's convenience: no verdict reads it, and a file in the
    # tree is the bound's. So a value whose file is in doubt is never refused for it; it runs as it
    # is, and the receipt names nothing. Mutations (declared): a path holding `%`, `?` or `#`
    # named; a relative `file:` URL named; another host's named.
    project = tmp_path / "project"
    _, _, node = installed(project)
    path = str(node.parent)
    for option in ("--import", "--loader", "-r"):
        word = f"{option}={value}" if option != "-r" else None
        words = [word] if word else [option, value]
        entry = plan_of(JEST, ["node", *words, "node_modules/jest/bin/jest.js"], project, path=path)
        assert entry.configs == CONFIGS
        tested = plan_of(NODE_TEST, ["node", "--test", *words], project, path=path)
        assert tested.configs == CONFIGS


@pytest.mark.parametrize(
    "value",
    ["/abs/x.mjs", "./setup.cjs", "../shared/s.cjs", "./A-z_0.9/@scope+x~/s p.mjs"],
)
def test_a_preload_path_whose_reading_is_plain_is_named(tmp_path: Path, value: str) -> None:
    # Mutation (declared): a path not named -> the receipt names nothing.
    node = node_on_path(tmp_path / "bin")
    got = plan_of(NODE_TEST, ["node", "--test", "--import", value], tmp_path, path=str(node.parent))
    assert got.configs == (*CONFIGS, os.path.realpath(tmp_path / value))


@pytest.mark.parametrize(
    ("words", "named"),
    [
        (("--watch",), "--watch"),
        # jest's documented recipe for debugging: node holds the code until a debugger attaches,
        # which under `prove` none does (measured on Node 24.10.0: past any time limit).
        (("--inspect-brk",), "--inspect-brk"),
        (("--inspect-brk=127.0.0.1:9229",), "--inspect-brk"),
        (("--inspect_wait", "--no-warnings"), "--inspect-wait"),
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
    assert got == Unresolved(NEVER_ENDS, NEVER_ENDS_DETAIL.format(option=named))
    # `--inspect` alone waits for nobody: it runs as typed.
    inspected = ["node", "--inspect", "node_modules/vitest/vitest.mjs"]
    assert isinstance(planned(VITEST, inspected, project, path=str(node.parent)), Plan)


def test_the_runner_s_own_refusals_hold_behind_node(tmp_path: Path) -> None:
    project = tmp_path / "project"
    _, _, node = installed(project)
    command = ["node", "node_modules/jest/bin/jest.js", "--json"]
    assert planned(JEST, command, project, path=str(node.parent)) == Refused(
        REFUSED_OPTION, "--json"
    )


@pytest.mark.parametrize(
    "script",
    ["node_modules/jest/other.js", "node_modules/jest/bin/missing.js", "node_modules/.bin/jest"],
)
def test_a_file_that_is_not_the_package_s_bin_does_not_resolve(tmp_path: Path, script: str) -> None:
    # The file node is handed must be the entry its package's `bin` names, as the search's own
    # check reads it: `.bin/jest` here is pnpm's shim, no link, and is never read.
    project = tmp_path / "project"
    _, _, node = installed(project)
    executable(project / "node_modules" / "jest" / "other.js", "#!/usr/bin/env node\n")
    executable(project / "node_modules" / ".bin" / "jest", "#!/bin/sh\nexec node x\n")
    got = planned(JEST, ["node", script], project, path=str(node.parent))
    assert got == Unresolved(ENTRY_NOT_FOUND, NOT_THE_ENTRY.format(package="jest"))
    assert len(NOT_THE_ENTRY.format(package="jest-cli")) <= CLIPPED_CHARS


def test_a_runner_named_by_its_link_runs_as_typed(tmp_path: Path) -> None:
    # npm's `node_modules/.bin/jest` is a link to the file the package's `bin` names: the run is
    # that link, as typed, which its entry's own `#!/usr/bin/env node` runs; the program the
    # receipt names is the entry, by its realpath, so no entry is named beside it. Mutation
    # (declared): a path to the runner not read -> no plan.
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
    assert got.entry is None
    again = plan_of(VITEST, ["node_modules/.bin/vitest"], project, path=str(node.parent))
    assert again.argv[:2] == (str(linked / "vitest"), "run")
    # The runner's own refusals and watch modes hold there as anywhere.
    assert planned(JEST, ["./node_modules/.bin/jest", "-u"], project, path=str(node.parent)) == (
        Refused(REFUSED_OPTION, "-u")
    )


def test_a_runner_named_by_a_path_that_is_no_link_is_never_run(tmp_path: Path) -> None:
    # pnpm's `.bin/jest` is an `sh` shim, no link, which may run anything: nothing tells that it is
    # jest's, so it is never read or run, nor is the entry itself named by a path that is no link;
    # nor a link to a file no package's `bin` names. A bare `jest` on `PATH` is the runner by its
    # name, as a shell finds it, and runs as typed.
    # Mutation (declared): a file that is not a link followed as one -> the entry named by its own
    # path resolves.
    project = tmp_path / "project"
    package(project / "node_modules" / "jest", "jest", "./bin/jest", "bin/jest")
    node = node_on_path(tmp_path / "bin")
    shims = project / "node_modules" / ".bin"
    executable(shims / "jest", '#!/bin/sh\nexec node ../jest/bin/jest "$@"\n')
    executable(project / "node_modules" / "jest" / "other" / "jest")
    (project / "elsewhere").mkdir()
    (project / "elsewhere" / "jest").symlink_to("../node_modules/jest/other/jest")
    detail = NOT_A_LINK.format(bin="jest", package="jest")
    for word in ("./node_modules/.bin/jest", "node_modules/jest/bin/jest", "elsewhere/jest"):
        got = planned(JEST, [word], project, path=str(node.parent))
        assert got == Unresolved(ENTRY_NOT_FOUND, detail), word
    assert len(NOT_A_LINK.format(bin="vitest", package="jest-cli")) <= CLIPPED_CHARS


def test_a_launcher_is_handed_the_command_as_typed(tmp_path: Path) -> None:
    # `uv run npx jest`: the launcher is found and runs, its words kept in front, and the
    # command's words are handed to it as typed, for it to resolve on its own `PATH` (uv puts the
    # project's `.venv/bin` first): nothing is looked for on the caller's, so a `PATH` holding uv
    # alone plans the run. Mutations (declared): the launcher dropped -> the plan runs `npx`
    # alone; the command's program handed by the caller's path -> `npx` is absolute.
    project = tmp_path / "project"
    entry, _, node = installed(project)
    launcher = executable(tmp_path / "tools" / "uv")
    # The caller's `PATH` holds `npx`, `node` and `jest` too: none of them is handed to uv.
    path = os.pathsep.join([str(launcher.parent), str(node.parent)])
    alone = str(launcher.parent)
    report = project / "scratch" / JEST_REPORT
    got = planned(JEST, ["npx", "jest"], project, path=path, launch=("uv", "run"))
    assert isinstance(got, Plan), got
    assert got.argv == (str(launcher), "run", "npx", "jest", "--json", f"--outputFile={report}")
    assert got.entry == entry
    tested = planned(NODE_TEST, ["node", "--test"], project, path=path, launch=("uv", "run"))
    assert isinstance(tested, Plan), tested
    assert tested.argv[:4] == (str(launcher), "run", "node", "--test-reporter=junit")
    assert tested.argv[-1] == "--test"
    bare = planned(JEST, ["jest"], project, path=path, launch=("uv", "run", "--frozen"))
    assert isinstance(bare, Plan), bare
    assert bare.argv[:4] == (str(launcher), "run", "--frozen", "jest")
    # A `.bin` link behind a launcher: the program is the launcher, so the entry is named.
    (project / "node_modules" / ".bin").mkdir()
    (project / "node_modules" / ".bin" / "jest").symlink_to("../jest/bin/jest.js")
    linked = planned(JEST, ["node_modules/.bin/jest"], project, path=path, launch=("uv", "run"))
    assert isinstance(linked, Plan), linked
    assert (linked.argv[2], linked.entry) == ("node_modules/.bin/jest", entry)
    # Nothing the launcher resolves is looked for on the caller's `PATH`: uv alone plans each.
    for adapter, command in (
        (JEST, ["npx", "jest"]),
        (JEST, ["jest"]),
        (NODE_TEST, ["node", "--test"]),
    ):
        alone_plan = planned(adapter, command, project, path=alone, launch=("uv", "run"))
        assert isinstance(alone_plan, Plan), alone_plan
        assert alone_plan.argv[2] == command[0]
    missing = planned(JEST, ["npx", "jest"], project, path="", launch=("uv", "run"))
    assert missing == Unresolved(ENTRY_NOT_FOUND, "no uv on PATH")


def test_vitest_related_keeps_its_subcommand_and_runs_once(tmp_path: Path) -> None:
    # vitest reads its first positional word as a subcommand (measured on 5.0.5): `run` put in
    # front of `related` made it a name filter, and a run that passes directly `failed`. So `run`
    # is added only where the command's first word is no subcommand, and `related` gets `--run`,
    # unless the command sets it (vitest refuses two settings of it before any run). Mutation
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
    off = plan_of(VITEST, ["vitest", "related", "--no-run", "src/a.js"], project, path=path)
    assert off.argv == (vitest, "related", "--no-run", "src/a.js", *ours)


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


# The entry `npx` runs is named on the receipt where it is found here: a package under
# `node_modules` from the directory the command runs in up to the top-level, then a link on
# `PATH`. Naming is the receipt's: the run is `npx`'s either way, and one found nowhere is unnamed.


def entry_of(
    command: Sequence[str], cwd: Path, root: Path | None = None, path: str = ""
) -> Path | None:
    """The entry the plan of `command` names, the plan's `argv` checked to be `command` as typed."""
    got = plan_of(JEST, command, cwd, root=root, path=path)
    assert got.argv[1 : len(command)] == tuple(command[1:])
    return got.entry


def test_a_pnpm_layout_resolves(tmp_path: Path) -> None:
    # pnpm links `node_modules/jest` into its store and writes `.bin/jest` as an `sh` shim, which
    # is never read: the package's own `bin` names the entry, by its realpath in the store.
    project = tmp_path / "project"
    store = project / "node_modules" / ".pnpm" / "jest@30.5.2_x" / "node_modules" / "jest"
    entry = jest_package(store.parent)
    (project / "node_modules" / "jest").symlink_to(store)
    executable(project / "node_modules" / ".bin" / "jest", "#!/bin/sh\nexec node ../.pnpm/x\n")
    node = node_on_path(tmp_path / "bin")
    assert entry_of(["npx", "jest"], project, path=str(node.parent)) == entry
    assert ".pnpm" in str(entry)


def test_a_nested_workspace_resolves_from_the_root(tmp_path: Path) -> None:
    # A monorepo: the command runs in `packages/web`, and the runner is installed at the
    # project's top-level. Mutation (declared): the search stops at the directory the command runs
    # in -> nothing is named.
    root = tmp_path / "repo"
    web = root / "packages" / "web"
    web.mkdir(parents=True)
    entry, _, node = installed(root)
    assert entry_of(["npx", "jest"], web, root=root, path=str(node.parent)) == entry


def test_the_nearest_package_wins_and_jest_before_jest_cli(tmp_path: Path) -> None:
    # Mutation (declared): the directories searched from the top-level down -> the root's jest.
    root = tmp_path / "repo"
    web = root / "packages" / "web"
    jest_package(root / "node_modules")
    nearer = jest_package(web / "node_modules", "jest-cli")
    path = str(node_on_path(tmp_path / "bin").parent)
    assert entry_of(["npx", "jest"], web, root=root, path=path) == nearer
    beside = jest_package(web / "node_modules")
    assert entry_of(["npx", "jest"], web, root=root, path=path) == beside


def test_the_search_stops_at_the_project_s_top_level(tmp_path: Path) -> None:
    # A `node_modules` above the project is another project's: npx runs as typed, nothing named.
    # Mutation (declared): the search runs past the top-level -> the outer jest is named.
    jest_package(tmp_path / "node_modules")
    project = tmp_path / "project"
    project.mkdir()
    node = node_on_path(tmp_path / "bin")
    assert entry_of(["npx", "jest"], project, path=str(node.parent)) is None


def test_a_runner_on_path_linked_into_its_package_resolves(tmp_path: Path) -> None:
    # A global install: `jest` on `PATH` is a link to the file its package's `bin` names.
    # Mutation (declared): the link's target taken without its package's `bin` -> the second
    # case, a link to a file no `bin` names, is named.
    entry = jest_package(tmp_path / "global" / "lib" / "node_modules")
    bin_ = tmp_path / "global" / "bin"
    bin_.mkdir(parents=True)
    (bin_ / "jest").symlink_to(entry)
    node = node_on_path(tmp_path / "bin")
    project = tmp_path / "project"
    project.mkdir()
    path = os.pathsep.join([str(node.parent), str(bin_)])
    assert entry_of(["npx", "jest"], project, path=path) == entry
    # Behind a launcher the `PATH` npx is run under is the launcher's own, not the caller's: no
    # link on the caller's is named. Mutation (declared): the caller's read behind a launcher ->
    # the global entry is named.
    uv = executable(tmp_path / "tools" / "uv")
    launched_path = os.pathsep.join([str(uv.parent), path])
    behind = planned(JEST, ["npx", "jest"], project, path=launched_path, launch=("uv", "run"))
    assert isinstance(behind, Plan) and behind.entry is None, behind
    stray = executable(entry.parent / "other.js")
    (bin_ / "jest").unlink()
    (bin_ / "jest").symlink_to(stray)
    assert entry_of(["npx", "jest"], project, path=path) is None


def test_a_runner_on_path_that_is_no_link_runs_unnamed(tmp_path: Path) -> None:
    # A `jest` on `PATH` that is a file of its own (pnpm's `sh` shim, or the package's own `bin`
    # directory put on `PATH`) is never read: typed bare, it runs as typed, as a shell runs it,
    # and under `npx` it names no entry. Mutation (declared): a file that is not a link followed as
    # one -> the package's own `bin` file is named.
    home = tmp_path / "global" / "lib" / "node_modules" / "jest"
    package(home, "jest", "./bin/jest", "bin/jest")
    executable(tmp_path / "shims" / "jest", "#!/bin/sh\nexec node /x\n")
    node = node_on_path(tmp_path / "bin")
    project = tmp_path / "project"
    project.mkdir()
    for directory in (home / "bin", tmp_path / "shims"):
        path = os.pathsep.join([str(node.parent), str(directory)])
        assert entry_of(["npx", "jest"], project, path=path) is None, directory
        bare = plan_of(JEST, ["jest"], project, path=path)
        assert (bare.argv[0], bare.entry) == (str(directory / "jest"), None), directory


def test_a_project_whose_top_level_is_not_above_the_directory_reads_that_directory_alone(
    tmp_path: Path,
) -> None:
    entry, _, node = installed(tmp_path / "here")
    here, elsewhere = tmp_path / "here", tmp_path / "elsewhere"
    assert entry_of(["npx", "jest"], here, root=elsewhere, path=str(node.parent)) == entry


@pytest.mark.parametrize(
    "bin_",
    [
        {"other": "./bin/jest.js"},
        "../outside.js",
        42,
        "",
    ],
    ids=["a-mapping-without-the-runner", "a-file-outside-the-package", "not-text", "empty"],
)
def test_a_package_whose_bin_names_no_entry_of_its_own_does_not_resolve(
    tmp_path: Path, bin_: object
) -> None:
    project = tmp_path / "project"
    package(project / "node_modules" / "jest", "jest", bin_, "bin/jest.js")
    executable(project / "node_modules" / "outside.js")
    node = node_on_path(tmp_path / "bin")
    assert entry_of(["npx", "jest"], project, path=str(node.parent)) is None
    got = planned(JEST, ["node", "node_modules/jest/bin/jest.js"], project, path=str(node.parent))
    assert got == Unresolved(ENTRY_NOT_FOUND, NOT_THE_ENTRY.format(package="jest"))


# Each a `package.json` that does not read as an object with a `bin`, built in the test.
MANIFESTS: dict[str, Callable[[], bytes]] = {
    "not-json": lambda: b"{not json",
    "not-an-object": lambda: b"[1]",
    "nested-past-the-parser": lambda: b"[" * 100_000 + b"]" * 100_000,
    "past-the-cap": lambda: b'{"bin": "./bin/jest.js"}' + b" " * (1024 * 1024),
}


@pytest.mark.parametrize("manifest", list(MANIFESTS))
def test_a_manifest_that_does_not_read_does_not_resolve(tmp_path: Path, manifest: str) -> None:
    project = tmp_path / "project"
    (project / "node_modules" / "jest").mkdir(parents=True)
    (project / "node_modules" / "jest" / "package.json").write_bytes(MANIFESTS[manifest]())
    # The entry a manifest cut at the cap would name is there: only the cap refuses it.
    executable(project / "node_modules" / "jest" / "bin" / "jest.js")
    node = node_on_path(tmp_path / "bin")
    assert entry_of(["npx", "jest"], project, path=str(node.parent)) is None


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
    ("args", "named"),
    [
        (("-c=ci/a.js",), ("ci/a.js",)),
        (("-ic", "ci/a.js"), ("ci/a.js",)),
        # `c` inside a cluster takes no value, and a `-c` at the end of the command none either.
        (("-ci",), ()),
        (("-t", "x", "-c"), ()),
        (("--config",), ()),
    ],
    ids=["equals", "closing-a-cluster", "inside-a-cluster", "last-word", "long-last-word"],
)
def test_the_configuration_a_short_option_names(
    tmp_path: Path, args: tuple[str, ...], named: tuple[str, ...]
) -> None:
    _, _, node = installed(tmp_path)
    got = plan_of(JEST, ["jest", *args], tmp_path, path=str(node.parent))
    real = Path(os.path.realpath(tmp_path))
    assert got.configs == (*CONFIGS, *(str(real / name) for name in named))


@pytest.mark.parametrize(
    ("adapter", "command", "program"),
    [
        (JEST, ["npx", "jest"], "npx"),
        (VITEST, ["npx", "--no", "vitest"], "npx"),
        (JEST, ["node", "node_modules/jest/bin/jest.js"], "node"),
        (NODE_TEST, ["node", "--test"], "node"),
        (NODE_TEST, ["tools/node", "--test"], "node"),
    ],
)
def test_a_program_on_no_path_entry_is_not_found(
    tmp_path: Path, adapter: Adapter, command: list[str], program: str
) -> None:
    # The command's first word is found as a shell finds it; where it names nothing, nothing can
    # run, and the detail names it.
    project = tmp_path / "project"
    installed(project)
    got = planned(adapter, command, project, path="")
    assert got == Unresolved(ENTRY_NOT_FOUND, f"no {program} on PATH")


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
        configs=CONFIGS,
    )
    assert got.discovery == NODE_DISCOVERY


def test_a_node_named_by_its_path_is_the_one_that_runs(tmp_path: Path) -> None:
    node = executable(tmp_path / "tools" / "node")
    got = plan_of(NODE_TEST, ["tools/node", "--test"], tmp_path, path="")
    assert got.argv[0] == str(tmp_path / "tools/node")
    assert os.path.realpath(got.argv[0]) == os.path.realpath(node)
    assert planned(NODE_TEST, ["tools/missing/node", "--test"], tmp_path) == Unresolved(
        ENTRY_NOT_FOUND, "no node on PATH"
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
    # are. Mutations (declared): `drop` left unset -> the whole-file cases count one passed; the
    # failure kept out of the predicate -> the load failures are dropped and the run reads one
    # passed, none failed; a testcase without `file` never dropped -> the Node 24 cases count one
    # passed.
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
        (
            {"name": "a.test.mjs", "classname": "test", "file": "{cwd}/a.test.mjs", "failure": "x"},
            False,
        ),
        ({"name": "a.test.mjs", "classname": "test", "failure": "test failed"}, False),
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


# --- What is refused ------------------------------------------------------------------------


REFUSALS: list[tuple[Adapter, tuple[str, ...], str]] = [
    # jest 30.5.2
    (JEST, ("npx", "jest", "--outputFile=x"), "--outputFile"),
    (JEST, ("jest", "--output-file", "x"), "--outputFile"),
    (JEST, ("jest", "--json"), "--json"),
    (JEST, ("jest", "--no-json"), "--json"),
    (JEST, ("npx", "jest", "-u"), "-u"),
    (JEST, ("jest", "-iu"), "-iu"),
    (JEST, ("jest", "--updateSnapshot"), "--updateSnapshot"),
    (JEST, ("jest", "--update-snapshot"), "--updateSnapshot"),
    (JEST, ("jest", "--collectTests"), "--collectTests"),
    # vitest 5.0.5
    (VITEST, ("npx", "vitest", "run", "--outputFile.json=x"), "--outputFile"),
    (VITEST, ("vitest", "run", "--outputFile=x"), "--outputFile"),
    (VITEST, ("vitest", "--output-file.junit", "x"), "--outputFile"),
    (VITEST, ("npx", "vitest", "run", "--update"), "--update"),
    (VITEST, ("vitest", "-u"), "-u"),
    (VITEST, ("vitest", "--update=all"), "--update"),
    (VITEST, ("vitest", "--update=false"), "--update"),
    (VITEST, ("vitest", "--mergeReports"), "--mergeReports"),
    (VITEST, ("vitest", "--merge-reports=.vitest-reports"), "--mergeReports"),
    (
        VITEST,
        ("vitest", "--dangerouslyIgnoreUnhandledErrors"),
        "--dangerouslyIgnoreUnhandledErrors",
    ),
    # node --test: a reporter without a destination of its own, or a destination without its
    # reporter, leaves node unable to pair the adapter's reporters with theirs, and it stops before
    # any test runs (measured on Node 24.10.0).
    (NODE_TEST, ("node", "--test", "--test-reporter=dot"), "--test-reporter"),
    (NODE_TEST, ("node", "--test-reporter", "tap", "--test"), "--test-reporter"),
    (NODE_TEST, ("node", "--test", "--test-reporter-destination=x"), "--test-reporter-destination"),
    (NODE_TEST, ("node", "--test", "--test_reporter=dot"), "--test-reporter"),
    (
        NODE_TEST,
        ("node", "--test", "a.test.mjs", "b.test.mjs", "--test-reporter=dot"),
        "--test-reporter",
    ),
    (
        NODE_TEST,
        (
            "node",
            "--test",
            "--test-reporter=dot",
            "--test-reporter=tap",
            "--test-reporter-destination=x",
        ),
        "--test-reporter",
    ),
    (NODE_TEST, ("node", "--test", "--test-update-snapshots"), "--test-update-snapshots"),
    (NODE_TEST, ("node", "--test", "--test-rerun-failures=state.json"), "--test-rerun-failures"),
    # After the files: Node 26.12.0 reads an option there as before them; Node 24.10.0 reads none
    # there (measured: the run as without it), so there the refusal is only the safe side.
    (
        NODE_TEST,
        ("node", "--test", "a.test.mjs", "--test-update-snapshots"),
        "--test-update-snapshots",
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
    # each left off its list; an unpaired reporter let through; node's `_` read as itself; node's
    # words read only up to its first file -> each one's case is planned or unresolved.
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
    (VITEST, ("vitest", "run", "--reporter=verbose")),
    (VITEST, ("vitest", "--update=none")),
    (VITEST, ("vitest", "--no-update")),
    # vitest's own default where `CI` is unset: a missing snapshot is written, a failing one
    # fails.
    (VITEST, ("vitest", "--update=new")),
    (VITEST, ("vitest", "--update", "new")),
    (VITEST, ("vitest", "-u", "new")),
    (VITEST, ("vitest", "--no-watch")),
    (VITEST, ("vitest", "--retry=2")),
    (VITEST, ("vitest", "-t", "passes")),
    (VITEST, ("vitest", "--passWithNoTests")),
    (VITEST, ("vitest", "-c", "vitest.ci.config.js")),
    (VITEST, ("vitest", "--", "--outputFile=x")),
    (NODE_TEST, ("node", "--import=tsx", "--test")),
    (NODE_TEST, ("node", "--import", "tsx", "--test")),
    (NODE_TEST, ("node", "-r", "./.pnp.cjs", "--loader", "./l.mjs", "--test")),
    (NODE_TEST, ("node", "--test", "--test-name-pattern=passes", "--test-only")),
    (NODE_TEST, ("node", "--test", "--test-force-exit", "--test-isolation=none")),
    (NODE_TEST, ("node", "--test", "--", "--watch")),
    # A reporter given its own destination: node writes the adapter's report beside it (measured
    # on Node 24.10.0, the report's counts unchanged).
    (NODE_TEST, ("node", "--test", "--test-reporter=spec", "--test-reporter-destination=stdout")),
    (NODE_TEST, ("node", "--test-reporter", "tap", "--test-reporter-destination", "x", "--test")),
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
    # Mutations (declared): `--update=none` and `--update=new` read as an update; a reporter
    # with its own destination refused -> each one's case is refused.
    _, _, node = installed(tmp_path)
    (tmp_path / "ci").mkdir()
    assert isinstance(planned(adapter, argv, tmp_path, path=str(node.parent)), Plan)


NEVER_ENDING: list[tuple[Adapter, tuple[str, ...], str]] = [
    (JEST, ("jest", "--watch"), "--watch"),
    (JEST, ("npx", "jest", "--watchAll"), "--watchAll"),
    (JEST, ("jest", "--watch", "0"), "--watch"),
    (VITEST, ("vitest", "--watch"), "--watch"),
    (VITEST, ("vitest", "run", "-w"), "-w"),
    (VITEST, ("vitest", "-tw", "x"), "-w"),
    # A cluster names its watch letter, never the word, so the detail fits the line.
    (VITEST, ("vitest", "-" + "s" * 40 + "w"), "-w"),
    (NODE_TEST, ("node", "--watch", "--test"), "--watch"),
    (NODE_TEST, ("node", "--test", "--watch-path=src"), "--watch-path"),
    (NODE_TEST, ("node", "--test", "a.test.mjs", "--watch"), "--watch"),
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
    assert planned(adapter, argv, tmp_path) == Unresolved(
        NEVER_ENDS, NEVER_ENDS_DETAIL.format(option=named)
    )


# The last of a watch mode's settings is the one each runner applies (measured: jest 30.5.2's
# `--watch --no-watch` runs once and `--no-watch --watch` watches, each of its two watch modes on
# its own; vitest 5.0.5's `--no-watch` overwrites what came before it, a second setting after one
# is refused before any run ("Expected a single value"), and `-w` and `--watch` are copied onto each
# other in the order they were first set, so `-w --no-watch` watches and `--no-watch -w` does not;
# Node 26.12.0's last `--watch` or `--no-watch` wins, `_` spelling `-`, and `--watch-path` cannot
# run under `--test` at all).
LAST_SETTING_PLANNED: list[tuple[Adapter, tuple[str, ...]]] = [
    (JEST, ("jest", "--watch", "--no-watch")),
    (JEST, ("jest", "--watchAll", "--no-watchAll")),
    (JEST, ("jest", "--watchAll", "--watchAll", "false")),
    (VITEST, ("vitest", "--watch", "--no-watch")),
    (VITEST, ("vitest", "--no-watch", "-w")),
    (VITEST, ("vitest", "--no-watch", "--watch")),
    (VITEST, ("vitest", "--watch", "--watch=false")),
    (NODE_TEST, ("node", "--watch", "--no-watch", "--test")),
    (NODE_TEST, ("node", "--test", "--watch", "--no_watch", "a.test.mjs")),
    (NODE_TEST, ("node", "--test", "a.test.mjs", "--watch", "--no-watch")),
]
LAST_SETTING_NEVER_ENDS: list[tuple[Adapter, tuple[str, ...], str]] = [
    (JEST, ("jest", "--no-watch", "--watch"), "--watch"),
    (JEST, ("jest", "--watchAll", "--watch=false"), "--watchAll"),
    (JEST, ("jest", "--watchAll=false", "--watchAll"), "--watchAll"),
    (VITEST, ("vitest", "-w", "--no-watch"), "-w"),
    (NODE_TEST, ("node", "--no-watch", "--watch", "--test"), "--watch"),
    (NODE_TEST, ("node", "--test", "--no_watch", "--watch", "a.test.mjs"), "--watch"),
    (NODE_TEST, ("node", "--watch-path=.", "--no-watch", "--test"), "--watch-path"),
]


@pytest.mark.parametrize(
    ("adapter", "argv"),
    LAST_SETTING_PLANNED,
    ids=[f"{adapter.name}:{'_'.join(argv[1:])}" for adapter, argv in LAST_SETTING_PLANNED],
)
def test_a_watch_mode_the_command_turns_off_again_is_planned(
    tmp_path: Path, adapter: Adapter, argv: tuple[str, ...]
) -> None:
    # Mutation (declared): each runner's watch reader stops at the first watch setting -> each
    # case is not proven.
    _, _, node = installed(tmp_path)
    assert isinstance(planned(adapter, argv, tmp_path, path=str(node.parent)), Plan)


@pytest.mark.parametrize(
    ("adapter", "argv", "named"),
    LAST_SETTING_NEVER_ENDS,
    ids=[f"{adapter.name}:{'_'.join(argv[1:])}" for adapter, argv, _ in LAST_SETTING_NEVER_ENDS],
)
def test_the_last_watch_setting_decides(
    tmp_path: Path, adapter: Adapter, argv: tuple[str, ...], named: str
) -> None:
    assert planned(adapter, argv, tmp_path) == Unresolved(
        NEVER_ENDS, NEVER_ENDS_DETAIL.format(option=named)
    )


@pytest.mark.parametrize(
    ("adapter", "argv", "named"),
    [*NEVER_ENDING, *LAST_SETTING_NEVER_ENDS],
    ids=[
        f"{adapter.name}:{'_'.join(argv[1:])[:40]}"
        for adapter, argv, _ in [*NEVER_ENDING, *LAST_SETTING_NEVER_ENDS]
    ],
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
    ("node_options", "named"),
    [
        ("--test-reporter=spec", "--test-reporter"),
        ("--max-old-space-size=4096 --test-reporter dot", "--test-reporter"),
        ("--test-reporter-destination=x.txt", "--test-reporter-destination"),
        ("--test_reporter=tap", "--test-reporter"),
    ],
)
def test_an_unpaired_reporter_in_node_options_is_refused(
    tmp_path: Path, node_options: str, named: str
) -> None:
    # node reads `NODE_OPTIONS`' reporters with the command's: an unpaired one there stops it
    # before any test runs as one on the command line does (measured on Node 24.10.0:
    # `ERR_INVALID_ARG_VALUE`, the adapter's report never written), so it is the same refusal,
    # inherited or assigned. A pair of its own is free. Mutation (declared): `NODE_OPTIONS` not
    # read -> each case is planned.
    node = node_on_path(tmp_path / "bin")
    path = str(node.parent)
    variables = {"NODE_OPTIONS": node_options}
    got = planned(NODE_TEST, ["node", "--test"], tmp_path, path=path, variables=variables)
    assert got == Refused(REFUSED_OPTION, named)
    paired = {"NODE_OPTIONS": "--test-reporter=dot --test-reporter-destination=stdout"}
    free = planned(NODE_TEST, ["node", "--test"], tmp_path, path=path, variables=paired)
    assert isinstance(free, Plan), free
    # One in `NODE_OPTIONS`, its destination on the command line: node pairs them.
    split = planned(
        NODE_TEST,
        ["node", "--test", "--test-reporter-destination=stdout"],
        tmp_path,
        path=path,
        variables={"NODE_OPTIONS": "--test-reporter=dot"},
    )
    assert isinstance(split, Plan), split


def test_an_assigned_unpaired_reporter_in_node_options_is_refused(tmp_path: Path) -> None:
    # The command's own assignment is in the run's environment the plan reads.
    node = node_on_path(tmp_path / "bin")
    argv = ["NODE_OPTIONS=--test-reporter=dot", "node", "--test"]
    got = prove(argv, cwd=tmp_path, environ={"PATH": str(node.parent)}, timeout=60)
    assert (got.verdict, got.reason, got.detail) == (REFUSED, REFUSED_OPTION, "--test-reporter")


@pytest.mark.parametrize(
    ("adapter", "argv", "named"),
    [
        (JEST, ("jest", "--watch", "-u"), "-u"),
        (VITEST, ("vitest", "-w", "--outputFile=x"), "--outputFile"),
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


def test_the_configuration_file_the_command_names_is_among_the_configs(tmp_path: Path) -> None:
    # A configuration file the command names is the bound's, as `jest.config.js` is, inside the
    # project or outside it, since the same agent could write either: never refused, named by its
    # realpath, read from the directory the command runs in. Mutation (declared): the named files
    # left out -> the adapter's own globs alone.
    root = tmp_path / "project"
    web = root / "web"
    web.mkdir(parents=True)
    _, _, node = installed(root)
    got = plan_of(
        JEST,
        [
            "jest",
            "-c",
            "ci/jest.config.js",
            "--config=../shared.config.js",
            "--rootDir",
            "elsewhere",
            "--",
            "-c",
            "x.js",
        ],
        web,
        root=root,
        path=str(node.parent),
    )
    real = Path(os.path.realpath(root))
    assert got.configs == (
        *CONFIGS,
        str(real / "web" / "ci" / "jest.config.js"),
        str(real / "shared.config.js"),
    )
    again = plan_of(VITEST, ["vitest", "-c", "vitest.ci.ts"], web, root=root, path=str(node.parent))
    assert again.configs == (*CONFIGS, str(real / "web" / "vitest.ci.ts"))
    outside = plan_of(
        JEST, ["jest", "-c", "../../outside.js"], web, root=root, path=str(node.parent)
    )
    assert outside.configs == (*CONFIGS, str(real.parent / "outside.js"))


@pytest.mark.parametrize(
    ("args", "named"),
    [
        (("-c", "c.js"), "c.js"),
        (("--root", "sub", "--config", "c.js"), "sub/c.js"),
        (("-r", "sub", "-c", "c.js"), "sub/c.js"),
        (("--config", "./c.js", "--root=sub"), "sub/c.js"),
        (("--root", "a", "--root", "sub", "-c", "c.js"), "sub/c.js"),
        # Measured: vitest reads these as the directory `false`, an error, and the directory
        # `true`; none names a root here.
        (("--no-root", "sub", "-c", "c.js"), "c.js"),
        (("--root.x", "a", "-c", "c.js"), "c.js"),
        (("--root=", "-c", "c.js"), "c.js"),
    ],
    ids=[
        "no-root",
        "root-first",
        "short",
        "config-first",
        "the-last-root",
        "negated",
        "dotted",
        "empty",
    ],
)
def test_vitest_reads_its_configuration_from_its_root(
    tmp_path: Path, args: tuple[str, ...], named: str
) -> None:
    # Measured on vitest 5.0.5: a relative `--config` is read from `--root`, in either order; two
    # roots stop vitest before any run, and the last is taken. Mutations (declared): the
    # configuration read from the run's directory whatever `--root` says -> the cases with a root
    # name `c.js`; a negated, dotted or empty `--root` read as one -> its case names another.
    assert outcome(VITEST, ("run", *args), tmp_path) == f"named {named}"


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


def test_an_npmrc_is_named_in_the_receipt(tmp_path: Path) -> None:
    project = tmp_path / "project"
    entry = jest_package(project / "node_modules")
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
    # The program is npx, as typed; the receipt names the runner's own entry beside it, the one
    # npx finds in `node_modules`.
    assert got.entry == os.path.realpath(entry)
    assert f"runner jest at {clipped(got.program)} running {clipped(got.entry)}" in line(got)
    assert got.configs == (".npmrc", "jest.config.js", "package.json")
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

JEST_PASSING = 'test("passes", () => { expect(1).toBe(1); });\ntest.skip("skipped", () => {});\n'
JEST_SKIPPED = 'test.skip("one", () => {});\ntest.skip("two", () => {});\n'
VITEST_HEAD = 'import { test, expect } from "vitest";\n'
NODE_HEAD = 'import { test } from "node:test";\nimport assert from "node:assert/strict";\n'
NODE_PASSING = (
    NODE_HEAD + 'test("passes", () => { assert.ok(true); });\n'
    'test("skipped", { skip: true }, () => {});\n'
)
NODE_SKIPPED = (
    NODE_HEAD + 'test("one", { skip: true }, () => {});\ntest("two", { skip: true }, () => {});\n'
)
# Each runner's test file, and its `package.json`.
FILES = {
    "jest": ("three.test.js", JEST_PASSING, JEST_SKIPPED, '{"name": "case", "private": true}'),
    "vitest": (
        "three.test.js",
        VITEST_HEAD + JEST_PASSING,
        VITEST_HEAD + JEST_SKIPPED,
        '{"name": "case", "private": true, "type": "module"}',
    ),
    "node-test": (
        "three.test.mjs",
        NODE_PASSING,
        NODE_SKIPPED,
        '{"name": "case", "private": true}',
    ),
}
FIXTURE_TESTS = {
    "jest": FIXTURE / "jest" / "three.test.js",
    "vitest": FIXTURE / "vitest" / "three.test.js",
    "node-test": FIXTURE / "node-test" / "three.test.mjs",
}
COMMANDS = {
    "jest": ["npx", "jest"],
    "vitest": ["npx", "vitest", "run"],
    "node-test": ["node", "--test"],
}
RUNNERS = list(COMMANDS)


def js_project(root: Path, runner: str, text: str | None = None) -> Path:
    """A project `runner` collects in `root`: its `package.json`, `node_modules` linked to the
    installed packages, and its test file holding `text` (none where `text` is empty)."""
    name, _, _, manifest = FILES[runner]
    root.mkdir(parents=True, exist_ok=True)
    (root / "package.json").write_text(manifest, encoding="utf-8")
    (root / "node_modules").symlink_to(installed_packages())
    if text:
        (root / name).write_text(text, encoding="utf-8")
    return root


def real(cwd: Path, *argv: str, **variables: str) -> Receipt:
    """`argv` proved in `cwd` with the `node` on `PATH` first."""
    node = runner_directory("node")
    environ = {**os.environ, "PATH": os.pathsep.join([str(node), os.environ.get("PATH", "")])}
    environ.pop("NODE_OPTIONS", None)
    return through_prove(argv, cwd, {**environ, **variables})


@needs_packages
@pytest.mark.parametrize("runner", RUNNERS)
def test_a_genuine_passing_run_is_proved(tmp_path: Path, runner: str) -> None:
    project = js_project(tmp_path / "p", runner, FILES[runner][1])
    got = real(project, *COMMANDS[runner])
    assert (got.verdict, got.reason, got.counts, got.exit_code) == (PROVED, "", Counts(1, 0, 1), 0)
    assert got.runner == runner
    # The command as typed: `npx` (which ships beside `node`) or `node`.
    program = COMMANDS[runner][0]
    assert got.program == os.path.realpath(runner_directory("node") / program)


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
    assert got.entry == os.path.realpath(project / "node_modules" / "jest" / "bin" / "jest.js")


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
    # jest's entry is named: beside `npx` and `node`, or as the program the `.bin` link is.
    jest = os.path.realpath(project / "node_modules" / "jest" / "bin" / "jest.js")
    assert jest in (got.entry, got.program)


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
@pytest.mark.parametrize(("runner", "code"), [("jest", 1), ("vitest", 1), ("node-test", 0)])
def test_an_empty_run_fails(tmp_path: Path, runner: str, code: int) -> None:
    got = real(js_project(tmp_path / "p", runner), *COMMANDS[runner])
    assert (got.verdict, got.reason, got.counts, got.exit_code) == (
        FAILED,
        NONE_RAN,
        Counts(0, 0, 0),
        code,
    )


@needs_packages
@pytest.mark.parametrize("runner", RUNNERS)
def test_an_all_skipped_run_fails(tmp_path: Path, runner: str) -> None:
    got = real(js_project(tmp_path / "p", runner, FILES[runner][2]), *COMMANDS[runner])
    assert (got.verdict, got.reason, got.counts) == (FAILED, ALL_SKIPPED, Counts(0, 0, 2))


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


# --- Each option read as the runner's own parser reads it -----------------------------------
#
# Every case is a form measured on the pinned version with the runner's own parser (jest's yargs
# and option table, vitest's `parseCLI`), and the answer is what that reading makes of it: a
# refusal naming the word or option, the configuration files named, or free.


def outcome(adapter: Adapter, args: Sequence[str], root: Path) -> str:
    _, _, node = installed(root)
    got = planned(adapter, [adapter.name, *args], root, path=str(node.parent))
    if isinstance(got, Refused):
        return f"refused {got.detail}"
    if isinstance(got, Unresolved):
        assert got.reason == NEVER_ENDS, got
        return f"never ends {got.detail}"
    assert isinstance(got, Plan), got
    real = Path(os.path.realpath(root))
    named = [
        os.path.relpath(entry, real) if real in Path(entry).parents else entry
        for entry in got.configs
        if os.path.isabs(entry)
    ]
    return f"named {' '.join(named)}" if named else "free"


def ends(option: str) -> str:
    """What `outcome` says of a watch mode `option` turns on."""
    return f"never ends {NEVER_ENDS_DETAIL.format(option=option)}"


# A file outside the project is named by its real path, as the receipt names every file: on macOS
# `/etc` is a link to `/private/etc`, so an expected `/etc/...` is read through it too.
JEST_FORMS = [
    # A short option in a cluster takes the rest of the word after a `=`, a character that is not
    # a letter, digit or `_`, or a number; only the last letter takes the next word.
    (("-c", "a.js"), "named a.js"),
    (("-c=a.js",), "named a.js"),
    (("-ic", "a.js"), "named a.js"),
    (("-ic=a.js",), "named a.js"),
    (("-c/etc/jest.config.js",), f"named {os.path.realpath('/etc/jest.config.js')}"),
    (("-ic/etc/jest.config.js",), f"named {os.path.realpath('/etc/jest.config.js')}"),
    (("-ic.a.js",), "named .a.js"),
    # `-c` given the empty text, or an object, names no file.
    (("-ca.js",), "free"),
    (("-ci",), "free"),
    (("-ci", "a.js"), "free"),
    (("-c.a.js",), "free"),
    (("-c../out.js",), "free"),
    (("-u",), "refused -u"),
    (("-iu",), "refused -iu"),
    (("-ui",), "refused -ui"),
    (("-tu",), "refused -tu"),
    (("-uc", "a.js"), "refused -uc"),
    (("-cu", "a.js"), "refused -cu"),
    (("-u.x",), "refused -u.x"),
    (("-u=true",), "refused -u=true"),
    (("-u", "1"), "refused -u"),
    # Turned off: `false` as the next word, or any value `=` gives but `true`, or a number.
    (("-u=false",), "free"),
    (("-u", "false"), "free"),
    (("-u=yes",), "free"),
    (("-u1",), "free"),
    (("-t/u",), "free"),
    (("-t=u",), "free"),
    (("-t.u",), "free"),
    # A boolean takes `true` or `false` as its next word, and nothing else; any value `=` gives
    # it but `true` turns it off.
    (("--watch", "false"), "free"),
    (("--watch=0",), "free"),
    (("--watch=1",), "free"),
    (("--watch", "0"), ends("--watch")),
    (("--no-watch", "true"), "free"),
    (("--watchAll", "false"), "free"),
    (("--updateSnapshot", "false"), "free"),
    (("--updateSnapshot", "true"), "refused --updateSnapshot"),
    (("--updateSnapshot=1",), "free"),
    (("--updateSnapshot=yes",), "free"),
    (("--collectTests", "false"), "free"),
    (("--collectTests=true",), "refused --collectTests"),
    (("--config", "a.js"), "named a.js"),
    # A configuration's own text names no file: `{` first and `}` last, as jest's `isJSONString`
    # reads one, nothing stripped.
    (("--config", '{"a": 1}'), "free"),
    (("-c{}",), "free"),
    (("--config", ' {"a": 1}'), 'named  {"a": 1}'),
    (("--config", '{"a": 1} '), 'named {"a": 1} '),
    # A `-` after the letter is its value; a negative number is no option.
    (("-c-",), "named -"),
    (("-1",), "free"),
    (("-u", "-1"), "refused -u"),
]


@pytest.mark.parametrize(
    ("args", "expected"), JEST_FORMS, ids=["_".join(args) for args, _ in JEST_FORMS]
)
def test_jest_reads_each_form_as_yargs_does(
    tmp_path: Path, args: tuple[str, ...], expected: str
) -> None:
    # Mutations (declared): a short option's value after a character that is no letter read as
    # none -> `-c/etc/jest.config.js` is free; a boolean's next word never read ->
    # `--updateSnapshot false` is refused; any `=` value read as on -> `-u=yes` is refused; a
    # configuration's own text named -> `--config {"a": 1}` names it; jest's JSON rule stripping
    # the value -> ` {"a": 1}` names nothing.
    assert outcome(JEST, args, tmp_path) == expected


VITEST_FORMS = [
    (("-c", "a.js"), "named a.js"),
    (("-c=a.js",), "named a.js"),
    (("-c", "/etc/vitest.config.js"), f"named {os.path.realpath('/etc/vitest.config.js')}"),
    # Every character of a cluster is an option of its own, the last taking the value.
    (("-ca.js",), "free"),
    (("-c/abs/a.js",), "free"),
    (("-c", "-t"), "free"),
    (("-c../out.js",), "refused -c../out.js"),
    (("-t.u",), "refused -t.u"),
    (("-tu",), "refused -tu"),
    (("-tfoo",), "free"),
    (("-wc", "a.js"), ends("-w")),
    (("-cw", "a.js"), ends("-w")),
    (("-uc", "a.js"), "refused -uc"),
    (("-cu", "a.js"), "refused -cu"),
    (("-uw", "false"), "refused -uw"),
    (("-u",), "refused -u"),
    (("-u", "none"), "free"),
    (("-u=none",), "free"),
    (("--update", "none"), "free"),
    (("--no-update",), "free"),
    (("--update=new",), "free"),
    (("-u", "new"), "free"),
    # `false` given to `--update` is the text `false`, which rewrites snapshots.
    (("-u", "false"), "refused -u"),
    (("--update=false",), "refused --update"),
    (("--update", "false"), "refused --update"),
    (("--update", "true"), "refused --update"),
    (("--update.x",), "refused --update"),
    # A boolean is off by `--no-` or `false` alone.
    (("-w",), ends("-w")),
    (("-w", "x"), ends("-w")),
    (("-w=false",), "free"),
    (("-w", "false"), "free"),
    (("--watch", "false"), "free"),
    (("--no-watch",), "free"),
    (("--watch=0",), ends("--watch")),
    (("--watch=no",), ends("--watch")),
    (("--dangerouslyIgnoreUnhandledErrors", "false"), "free"),
    (("--dangerouslyIgnoreUnhandledErrors=0",), "refused --dangerouslyIgnoreUnhandledErrors"),
    (("--mergeReports=false",), "refused --mergeReports"),
    (("--config", "a.js"), "named a.js"),
    (("-=x",), "free"),
    (("-u", "-1"), "refused -u"),
]


@pytest.mark.parametrize(
    ("args", "expected"), VITEST_FORMS, ids=["_".join(args) for args, _ in VITEST_FORMS]
)
def test_vitest_reads_each_form_as_its_parser_does(
    tmp_path: Path, args: tuple[str, ...], expected: str
) -> None:
    # Mutations (declared): `--update=false` read as no update -> its case is free; a cluster
    # read only at its first letter -> `-t.u` is free; a boolean turned off by any `=` value ->
    # `--watch=0` is free.
    assert outcome(VITEST, ("run", *args), tmp_path) == expected


def test_a_preloaded_file_is_named_and_a_package_is_not(tmp_path: Path) -> None:
    # A preload's file is named where its reading is not in doubt: a plain path starting `/`, `./`
    # or `../`, by its realpath from the run's directory; an absolute `file:` URL of this machine,
    # by its path, percent-decoded. A package's name, and a file in doubt, run unnamed.
    # `-r=x` is a bad option to node, and a word after `--` is none of node's. Mutations
    # (declared): the preloaded files left out; a `file:` URL's escapes kept.
    node = node_on_path(tmp_path / "bin")
    got = plan_of(
        NODE_TEST,
        [
            "node",
            "-r",
            "./.pnp.cjs",
            "--import",
            "tsx",
            "--require=ts-node/register",
            "--loader=../l.mjs",
            "--experimental_loader",
            "/abs/x.mjs",
            "--import=file:///abs/y.mjs",
            "--import=file://localhost/abs/z%20q.mjs",
            "--import=file:/abs/w.mjs",
            "--import=@scope/pkg/esm",
            "--import=file://elsewhere/abs/no.mjs",
            "--import=file:rel.mjs",
            "--loader=./q%3F.mjs",
            "-r=./bad.cjs",
            "--test",
            "a.test.mjs",
            "--require",
            "./after.cjs",
            "--",
            "--import=./not.mjs",
        ],
        tmp_path,
        path=str(node.parent),
    )
    real = Path(os.path.realpath(tmp_path))
    assert got.configs == (
        *CONFIGS,
        str(real / ".pnp.cjs"),
        str(real.parent / "l.mjs"),
        "/abs/x.mjs",
        "/abs/y.mjs",
        "/abs/z q.mjs",
        "/abs/w.mjs",
        str(real / "after.cjs"),
    )
    last = plan_of(NODE_TEST, ["node", "--test", "-r"], tmp_path, path=str(node.parent))
    assert last.configs == CONFIGS


def test_a_nul_in_a_file_url_preload_names_no_file(tmp_path: Path) -> None:
    # `%00` decodes to a NUL, which `os.path.realpath` refuses with `ValueError`: the value runs
    # unnamed instead of crashing the plan. Mutation (declared): the NUL not looked for -> raises.
    node = node_on_path(tmp_path / "bin")
    got = plan_of(
        NODE_TEST,
        ["node", "--test", "--import=file:///abs/a%00b.mjs"],
        tmp_path,
        path=str(node.parent),
    )
    assert got.configs == CONFIGS


def test_a_bin_holding_a_nul_does_not_resolve(tmp_path: Path) -> None:
    # A manifest is the tree's to write, and a `bin` holding a NUL names no file. Mutation
    # (declared): the NUL not looked for -> `ValueError` out of the plan.
    project = tmp_path / "project"
    package(project / "node_modules" / "jest", "jest", "./bin/je\u0000st.js", "bin/jest.js")
    node = node_on_path(project / ".tools")
    assert entry_of(["npx", "jest"], project, path=str(node.parent)) is None
