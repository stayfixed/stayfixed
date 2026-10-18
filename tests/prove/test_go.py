"""The `go test` adapter: what it recognises, how it plans a run, what it refuses, and what a real
`go test` run under it proves.

The plan tests run no `go`: `plan` is a pure function of its arguments and of the files it reads.
The tests through `prove` that run no real `go` use `fake_go`, a shell script standing in for `go`
that prints a recorded event stream (`tests/fixtures/prove/reports/go*.jsonl`) and writes down the
arguments and the environment it was run with. The tests marked `runners` run the `go` on `PATH`
over the module `tests/fixtures/prove/go/`, copied into a scratch directory.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from stayfixed import fsops
from stayfixed.profiles.go.adapters import (
    ADAPTERS,
    CONFIGS,
    DISCOVERY,
    FORGING,
    NAME,
    REPORT_NAME,
    SCRUB,
    SET_ENV,
    GoTestAdapter,
)
from stayfixed.profiles.runners import (
    ENTRY_NOT_FOUND,
    REFUSED_OPTION,
    Plan,
    Refused,
    ReportKind,
    ReportSource,
    Unresolved,
)
from stayfixed.prove.counts import Counts
from stayfixed.prove.run import (
    ALL_SKIPPED,
    ASSIGNED_FORGING,
    FAILING,
    NONE_RAN,
    Receipt,
    Verdict,
    prove,
)
from tests.prove.real_runners import needs_runner, runner_directory

PROVED, FAILED, NOT_PROVEN, REFUSED = (
    Verdict.PROVED,
    Verdict.FAILED,
    Verdict.NOT_PROVEN,
    Verdict.REFUSED,
)
ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "tests" / "fixtures" / "prove" / "go"
REPORTS = ROOT / "tests" / "fixtures" / "prove" / "reports"
GO = GoTestAdapter()


def executable(path: Path, text: str = "#!/bin/sh\nexit 0\n") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    path.chmod(0o755)
    return path


def planned(command: list[str], cwd: Path, *, path: str = "") -> Plan | Refused | Unresolved:
    return GO.plan((), command, cwd=cwd, root=cwd, scratch=cwd / "scratch", environ={"PATH": path})


def argv_of(command: list[str], cwd: Path) -> tuple[str, ...]:
    go = executable(cwd / "bin" / "go")
    got = planned(command, cwd, path=str(go.parent))
    assert isinstance(got, Plan), got
    assert got.argv[:2] == (str(go), "test")
    return got.argv[2:]


# --- What is recognised ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("command", "recognised"),
    [
        (["go", "test"], True),
        (["go", "test", "./...", "-run", "TestX"], True),
        (["go", "vet", "./..."], False),
        (["go", "build"], False),
        (["go"], False),
        (["gotest", "./..."], False),
        (["test", "go"], False),
    ],
)
def test_go_test_is_recognised(command: list[str], recognised: bool) -> None:
    assert GO.recognises(command) is recognised


def test_the_adapters_this_stack_ships() -> None:
    assert [adapter.name for adapter in ADAPTERS] == [NAME] == ["go-test"]
    assert GO.forging == FORGING
    assert frozenset({"GOFLAGS", "GOENV", "GOTOOLCHAIN", "GOROOT", "GOOS", "GOARCH"}) == FORGING


# --- How a run is planned -------------------------------------------------------------------


def test_the_plan_neutralises_the_go_environment(tmp_path: Path) -> None:
    # The user's go env file, an inherited `GOFLAGS` and a `toolchain` line cannot change what
    # runs; an inherited `GOROOT` goes, and the `go` that runs finds its own. Mutations
    # (declared): `GOENV` scrubbed instead of set; `GOROOT` handed to the run -> this plan
    # differs.
    go = executable(tmp_path / "bin" / "go")
    got = planned(["go", "test", "./..."], tmp_path, path=str(go.parent))
    assert got == Plan(
        argv=(str(go), "test", "-json", "./..."),
        program=Path(os.path.realpath(go)),
        kind=ReportKind.EVENTS,
        source=ReportSource.STDOUT,
        report=tmp_path / "scratch" / "events.jsonl",
        set_env={"GOENV": "off", "GOFLAGS": "", "GOTOOLCHAIN": "local"},
        scrub=frozenset({"GOROOT", "GOOS", "GOARCH"}),
        discovery=("*_test.go",),
        configs=("go.mod", "go.work"),
    )
    assert (got.set_env, got.scrub, got.discovery, got.configs) == (
        SET_ENV,
        SCRUB,
        DISCOVERY,
        CONFIGS,
    )
    assert got.report.name == REPORT_NAME


@pytest.mark.parametrize(
    ("command", "args"),
    [
        (["go", "test", "-json", "./..."], ("-json", "./...")),
        (["go", "test", "-v", "--json", "./p"], ("-json", "-v", "./p")),
        (["go", "test", "-json=true"], ("-json",)),
        (["go", "test", "-C", "sub", "./..."], ("-C", "sub", "-json", "./...")),
        (["go", "test", "-C=sub", "-json"], ("-C=sub", "-json")),
        (["go", "test", "./...", "-C", "sub"], ("-json", "./...", "-C", "sub")),
        (["go", "test", "-args", "-json"], ("-json", "-args", "-json")),
        (["go", "test", "./...", "--", "-json"], ("-json", "./...", "--", "-json")),
        (["go", "test", "-test.p", "-json", "./..."], ("-json", "-test.p", "./...")),
    ],
    ids=[
        "kept-once",
        "two-dashes",
        "true",
        "after-C",
        "after-C-with-equals",
        "C-not-first",
        "args",
        "terminator",
        "test-prefixed-build-flag",
    ],
)
def test_one_json_after_a_leading_C(
    tmp_path: Path, command: list[str], args: tuple[str, ...]
) -> None:
    # `-C` is read only as the first flag, a word past `-args` or `--` is the test binary's, and
    # a build flag spelled `-test.` takes no value. Mutations (declared): the command's own
    # `-json` kept beside the report's -> `kept-once` holds two; `-json` put before a leading `-C`
    # -> `after-C` starts with it.
    assert argv_of(command, tmp_path) == args


def test_a_path_entry_that_cannot_be_asked_about_is_passed_over(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    go = executable(tmp_path / "bin" / "go")
    blind = tmp_path / "blind"
    asked = fsops.is_file

    def is_file(path: Path) -> bool:
        if path.parent == blind:
            raise PermissionError(13, "denied", str(path))
        return asked(path)

    monkeypatch.setattr(fsops, "is_file", is_file)
    got = planned(["go", "test"], tmp_path, path=os.pathsep.join([str(blind), str(go.parent)]))
    assert isinstance(got, Plan) and got.argv[0] == str(go)


def test_no_go_on_path_does_not_resolve(tmp_path: Path) -> None:
    assert planned(["go", "test"], tmp_path) == Unresolved(ENTRY_NOT_FOUND, "no go on PATH")


@pytest.mark.parametrize("where", ["root", "home"])
def test_the_go_on_path_runs_wherever_it_lies(tmp_path: Path, where: str) -> None:
    # No stand-in is refused: the `go` on `PATH` runs, inside the project or outside it, and the
    # receipt names its realpath.
    project = tmp_path / "project"
    project.mkdir()
    directory = project / "tools" if where == "root" else tmp_path / "home" / "sdk" / "bin"
    go = executable(directory / "go")
    got = GO.plan(
        (),
        ["go", "test"],
        cwd=project,
        root=project,
        scratch=tmp_path / "scratch",
        environ={"PATH": str(directory)},
    )
    assert isinstance(got, Plan), got
    assert (got.argv[0], got.program) == (str(go), Path(os.path.realpath(go)))


def test_a_launcher_is_kept_in_front_of_the_go_on_path(tmp_path: Path) -> None:
    # `uv run go test ./...`: the launcher runs, its words kept in front, as every adapter keeps
    # them, so the core's refusal of its file options guards the run that happens. The program is
    # the launcher's realpath; the `go` it is handed is the caller's `PATH`'s, by its path.
    # Mutation (declared): the launcher dropped -> the plan runs `go` alone.
    tools = tmp_path / "tools"
    launcher = executable(tools / "uv")
    go = executable(tmp_path / "bin" / "go")
    got = GO.plan(
        ("uv", "run", "--locked"),
        ["go", "test", "./..."],
        cwd=tmp_path,
        root=tmp_path,
        scratch=tmp_path / "scratch",
        environ={"PATH": os.pathsep.join([str(tools), str(go.parent)])},
    )
    assert isinstance(got, Plan), got
    assert got.argv == (str(launcher), "run", "--locked", str(go), "test", "-json", "./...")
    assert got.program == Path(os.path.realpath(launcher))


def test_a_launcher_not_on_path_does_not_resolve(tmp_path: Path) -> None:
    go = executable(tmp_path / "bin" / "go")
    got = GO.plan(
        ("uv", "run"),
        ["go", "test"],
        cwd=tmp_path,
        root=tmp_path,
        scratch=tmp_path / "scratch",
        environ={"PATH": str(go.parent)},
    )
    assert got == Unresolved(ENTRY_NOT_FOUND, "no uv on PATH")


def test_the_file_modfile_names_is_among_the_configs(tmp_path: Path) -> None:
    # Mutation (declared): the named file left out -> the adapter's own globs alone.
    go = executable(tmp_path / "bin" / "go")
    got = planned(
        [
            *("go", "test", "-modfile", "ci/go.mod", "--modfile=../alt.mod"),
            *("-test.tags", "-modfile=t.mod", "-args", "-modfile=x"),
        ],
        tmp_path,
        path=str(go.parent),
    )
    assert isinstance(got, Plan), got
    real = Path(os.path.realpath(tmp_path))
    assert got.configs == (
        *CONFIGS,
        str(real / "ci" / "go.mod"),
        str(real.parent / "alt.mod"),
        str(real / "t.mod"),
    )


@pytest.mark.parametrize(
    ("command", "named"),
    [
        (["go", "test", "-C", "sub", "-modfile=alt.mod"], "sub/alt.mod"),
        (["go", "test", "--C=sub", "-modfile", "alt.mod"], "sub/alt.mod"),
        (["go", "test", "-modfile=alt.mod", "-C", "sub"], "alt.mod"),
        (["go", "test", "./...", "--", "-modfile=x", "-modfile=alt.mod"], None),
    ],
    ids=["C", "C-with-equals", "C-not-first", "terminator"],
)
def test_the_file_modfile_names_is_read_from_where_go_reads_it(
    tmp_path: Path, command: list[str], named: str | None
) -> None:
    # Measured on Go 1.27.2: under a leading `-C sub`, `-modfile=alt.mod` reads `sub/alt.mod`,
    # and a word past `--` is the test binary's. Mutation (declared): `-modfile` read from the
    # run's directory under a leading `-C` -> `C` names `alt.mod`.
    go = executable(tmp_path / "bin" / "go")
    got = planned(command, tmp_path, path=str(go.parent))
    assert isinstance(got, Plan), got
    real = Path(os.path.realpath(tmp_path))
    assert got.configs == (*CONFIGS, *(() if named is None else (str(real / named),)))


# --- What is refused ------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("flag", "named"),
    [
        (("-exec=echo",), "-exec"),
        (("-exec", "echo"), "-exec"),
        (("--exec=echo",), "-exec"),
        (("-toolexec=x",), "-toolexec"),
        (("--toolexec", "x"), "-toolexec"),
        (("-overlay=o.json",), "-overlay"),
        (("-overlay", "o.json"), "-overlay"),
        (("-c",), "-c"),
        (("-c=true",), "-c"),
        (("-c=1",), "-c"),
        (("--c",), "-c"),
        (("-o=x",), "-o"),
        (("-o", "x"), "-o"),
        (("-json=false",), "-json"),
        (("--json=0",), "-json"),
        (("-json=F",), "-json"),
        (("./...", "-exec=echo"), "-exec"),
        # Only a bare `-args` or `--args` ends the go command's flags (measured on Go 1.27.2:
        # past these a refused flag runs).
        (("-args=x", "-toolexec=y"), "-toolexec"),
        (("-args=true", "-exec=x"), "-exec"),
        (("-args=false", "-exec=x"), "-exec"),
        (("-test.args", "-exec=x"), "-exec"),
        # A build flag spelled `-test.` is no flag of the go command's, so it takes no value
        # (measured on Go 1.27.2: `./pkg -test.p -exec=X` runs X).
        (("./...", "-test.p", "-exec=x"), "-exec"),
        (("-test.tags", "x", "-toolexec=y"), "-toolexec"),
        # Past a word after the package list the go command reads no flag of its own (measured
        # on Go 1.27.2: `./three/ -v foo -exec=X` runs no X), but where it stops depends on
        # which flags each Go version knows (`-artifacts` is Go 1.27.2's and not Go 1.24.7's),
        # and a reader that stopped there would let a version that reads on run the flag. So the
        # reading fails closed: a contrived over-refusal, accepted over a version-dependent
        # bypass; `-args` is the way to hand the test binary a flag.
        (("./...", "-v", "foo", "-exec=x"), "-exec"),
        (("./...", "-artifacts", "foo", "-exec=x"), "-exec"),
    ],
    ids=lambda value: "_".join(value) if isinstance(value, tuple) else value,
)
def test_each_forging_flag_is_refused(tmp_path: Path, flag: tuple[str, ...], named: str) -> None:
    # Refused before anything is resolved: no `PATH` holds a `go` here. Each form is one the go
    # command reads so (measured on Go 1.27.2: `-exec X`, `--exec X` and `./pkg -exec=X` run X).
    # Mutations (declared): `-toolexec` allowed; a flag given two dashes read as no flag;
    # `-json=false` read as `-json`; a flag after the packages left unread -> each one's case is
    # planned or unresolved.
    assert planned(["go", "test", *flag], tmp_path) == Refused(REFUSED_OPTION, named)


@pytest.mark.parametrize(
    "flags",
    [
        ("-v", "-count=1", "-race", "-cover", "-failfast", "-shuffle", "on"),
        ("-run", "-c"),
        ("-run=TestX", "-skip", "-exec"),
        ("-args", "-c", "-o", "x", "-exec=y"),
        ("--args", "-toolexec=y"),
        ("-run", "X", "-args", "-exec=y"),
        ("-tags", "integration", "-vet=off", "-n", "-list", "."),
        ("-modfile=alt.mod", "-ldflags=-s", "-gcflags", "-N"),
        ("-json",),
        ("-json=true",),
        ("-json=1",),
        # A boolean turned off by its value, as the go command reads one, builds and runs as
        # without it.
        ("-c=false",),
        ("-c=0",),
        # A build flag spelled `-test.` is no flag the go command takes: it ends the run in an
        # error before any test.
        ("-test.c",),
        ("-test.exec=x",),
        ("-test.run", "-exec"),
        # Nor is a word past a bare `--` (measured: `./pkg -- -exec=X` runs no X).
        ("--", "-exec=y"),
        ("./...", "--", "-c", "-o", "x", "-toolexec=y"),
    ],
    ids=lambda value: "_".join(value),
)
def test_every_other_flag_is_free(tmp_path: Path, flags: tuple[str, ...]) -> None:
    # A value is never read as a flag, nor is a word past `-args` (measured: `-run -exec=X` and
    # `-args -exec=X` run no X). Mutations (declared): the value of a flag that takes one read as a
    # flag; `-args` read past; `-c=false` refused as `-c` is -> each one's case is refused.
    go = executable(tmp_path / "bin" / "go")
    assert isinstance(planned(["go", "test", *flags], tmp_path, path=str(go.parent)), Plan)


# The go command's own flags that take a value (Go 1.27.2, `go help build` and `go help testflag`
# with the hidden `-debug-*`), as it registers them: a build flag by its bare name only, a flag
# the test binary takes by its bare name and by its `test.` name.
BUILD_FLAGS_TAKING_A_VALUE = (
    *("C", "p", "covermode", "coverpkg", "asmflags", "buildmode", "compiler", "gccgoflags"),
    *("gcflags", "installsuffix", "ldflags", "mod", "modfile", "overlay", "pgo", "pkgdir"),
    *("tags", "toolexec", "exec", "o", "vet"),
    *("debug-actiongraph", "debug-runtime-trace", "debug-trace"),
)
TEST_FLAGS_TAKING_A_VALUE = (
    *("bench", "benchtime", "blockprofile", "blockprofilerate", "count", "coverprofile", "cpu"),
    *("cpuprofile", "fuzz", "fuzzminimizetime", "fuzztime", "list", "memprofile"),
    *("memprofilerate", "mutexprofile", "mutexprofilefraction", "outputdir", "parallel"),
    *("run", "shuffle", "skip", "timeout", "trace"),
)


@pytest.mark.parametrize("name", BUILD_FLAGS_TAKING_A_VALUE)
def test_a_build_flag_spelled_test_takes_no_value(tmp_path: Path, name: str) -> None:
    # Measured on Go 1.27.2 for each: `go test ./three/ -test.<name> -exec=X` runs X, and
    # `-<name> -exec=X` runs none. Mutation (declared): a build flag's `test.` spelling read as
    # taking a value -> each case is planned.
    assert planned(["go", "test", "./...", f"-test.{name}", "-exec=x"], tmp_path) == Refused(
        REFUSED_OPTION, "-exec"
    )
    go = executable(tmp_path / "bin" / "go")
    got = planned(["go", "test", "./...", f"-{name}", "-exec=x"], tmp_path, path=str(go.parent))
    if name in ("exec", "toolexec", "overlay", "o"):
        assert got == Refused(REFUSED_OPTION, f"-{name}")
    else:
        assert isinstance(got, Plan), got


@pytest.mark.parametrize("spelling", ["", "test."])
@pytest.mark.parametrize("name", TEST_FLAGS_TAKING_A_VALUE)
def test_a_test_binary_flag_takes_its_value_in_either_spelling(
    tmp_path: Path, name: str, spelling: str
) -> None:
    # Measured on Go 1.27.2 for each: `-<name> -exec=X` and `-test.<name> -exec=X` run no X.
    go = executable(tmp_path / "bin" / "go")
    got = planned(
        ["go", "test", "./...", f"-{spelling}{name}", "-exec=x"], tmp_path, path=str(go.parent)
    )
    assert isinstance(got, Plan), got


# --- Through prove, with a go that prints a recorded stream ----------------------------------

FAKE_GO = """#!/bin/sh
# A stand-in for go: write down how it was run, print the recorded stream, exit as told.
printf '%s\\n' "$@" > "$GO_SEEN/argv"
env > "$GO_SEEN/env"
cat "$GO_REPORT"
exit "${GO_EXIT:-0}"
"""


def fake_go(where: Path) -> Path:
    return executable(where / "go", FAKE_GO)


def through_fake(tmp_path: Path, report: str, code: int, **inherited: str) -> Receipt:
    go = fake_go(tmp_path / "bin")
    seen = tmp_path / "seen"
    seen.mkdir()
    project = tmp_path / "project"
    project.mkdir()
    environ = {
        "PATH": f"{go.parent}{os.pathsep}/usr/bin{os.pathsep}/bin",
        "GO_SEEN": str(seen),
        "GO_REPORT": str(REPORTS / report),
        "GO_EXIT": str(code),
        **inherited,
    }
    return prove(["go", "test", "./..."], cwd=project, environ=environ, timeout=60)


@pytest.mark.parametrize(
    ("report", "code", "verdict", "reason", "counts"),
    [
        ("go.jsonl", 1, FAILED, FAILING, Counts(1, 1, 1)),
        ("go-run-no-such-test.jsonl", 0, FAILED, NONE_RAN, Counts(0, 0, 0)),
        ("go-testmain-exit0.jsonl", 0, FAILED, NONE_RAN, Counts(0, 0, 0)),
        ("go-build-fail.jsonl", 1, FAILED, FAILING, Counts(0, 1, 0)),
        # A `TestMain` printing test2json's framing: a `pass` for a test that never ran, which
        # the bound concedes.
        ("go-framing.jsonl", 0, PROVED, "", Counts(2, 0, 0)),
    ],
)
def test_a_recorded_stream_is_judged_through_prove(
    tmp_path: Path, report: str, code: int, verdict: Verdict, reason: str, counts: Counts
) -> None:
    got = through_fake(tmp_path, report, code)
    assert (got.verdict, got.reason, got.counts, got.runner) == (verdict, reason, counts, NAME)


def test_the_run_s_environment_is_pinned_whatever_it_inherits(tmp_path: Path) -> None:
    got = through_fake(
        tmp_path,
        "go-framing.jsonl",
        0,
        GOFLAGS="-exec=/bin/false",
        GOENV=str(tmp_path / "goenv"),
        GOTOOLCHAIN="go1.99.0",
        GOROOT=str(tmp_path / "forged-root"),
        GOOS="js",
        GOARCH="wasm",
    )
    assert got.verdict == PROVED
    env = dict(
        line.split("=", 1)
        for line in (tmp_path / "seen" / "env").read_text(encoding="utf-8").splitlines()
        if "=" in line
    )
    assert (env["GOENV"], env["GOFLAGS"], env["GOTOOLCHAIN"]) == ("off", "", "local")
    assert not {"GOROOT", "GOOS", "GOARCH"} & set(env)
    argv = (tmp_path / "seen" / "argv").read_text(encoding="utf-8").splitlines()
    assert argv == ["test", "-json", "./..."]


@pytest.mark.parametrize("name", ["GOFLAGS", "GOENV", "GOTOOLCHAIN", "GOROOT", "GOOS", "GOARCH"])
def test_an_assigned_goflags_is_refused(tmp_path: Path, name: str) -> None:
    # Mutations (declared): `GOROOT` left out of the forging set; `GOOS` and `GOARCH` left out of
    # it -> each one's case runs.
    go = fake_go(tmp_path / "bin")
    for argv in ([f"{name}=x", "go", "test"], ["env", f"{name}=-exec=x", "go", "test"]):
        got = prove(argv, cwd=tmp_path, environ={"PATH": str(go.parent)}, timeout=60)
        assert (got.verdict, got.reason, got.detail) == (REFUSED, ASSIGNED_FORGING, name), argv


# --- Real go test runs ----------------------------------------------------------------------


def module(tmp_path: Path) -> Path:
    """The fixture module, copied where the run may build it."""
    return Path(shutil.copytree(MODULE, tmp_path / "module"))


def real(cwd: Path, *argv: str, **variables: str) -> Receipt:
    """`argv` proved in `cwd` with the `go` on `PATH` first."""
    go = runner_directory("go")
    environ = {**os.environ, "PATH": os.pathsep.join([str(go), os.environ.get("PATH", "")])}
    return prove(argv, cwd=cwd, environ={**environ, **variables}, timeout=600)


@needs_runner("go")
def test_a_genuine_passing_run_is_proved(tmp_path: Path) -> None:
    got = real(module(tmp_path), "go", "test", "./passing/")
    assert (got.verdict, got.reason, got.counts, got.exit_code) == (PROVED, "", Counts(1, 0, 1), 0)
    assert got.program == os.path.realpath(runner_directory("go") / "go")


@needs_runner("go")
def test_the_three_tests_fail(tmp_path: Path) -> None:
    got = real(module(tmp_path), "go", "test", "./three/")
    assert (got.verdict, got.reason, got.counts, got.exit_code) == (
        FAILED,
        FAILING,
        Counts(1, 1, 1),
        1,
    )


@needs_runner("go")
def test_run_no_such_test_fails(tmp_path: Path) -> None:
    got = real(module(tmp_path), "go", "test", "-run", "NoSuchTest", "./three/")
    assert (got.verdict, got.reason, got.counts, got.exit_code) == (
        FAILED,
        NONE_RAN,
        Counts(0, 0, 0),
        0,
    )


@needs_runner("go")
def test_an_all_skipped_run_fails(tmp_path: Path) -> None:
    got = real(module(tmp_path), "go", "test", "./skipped/")
    assert (got.verdict, got.reason, got.counts) == (FAILED, ALL_SKIPPED, Counts(0, 0, 2))


@needs_runner("go")
def test_testmain_exiting_zero_fails(tmp_path: Path) -> None:
    got = real(module(tmp_path), "go", "test", "./testmain/")
    assert (got.verdict, got.reason, got.counts, got.exit_code) == (
        FAILED,
        NONE_RAN,
        Counts(0, 0, 0),
        0,
    )


@needs_runner("go")
def test_a_build_failure_fails(tmp_path: Path) -> None:
    got = real(module(tmp_path), "go", "test", "./broken/")
    assert (got.verdict, got.reason, got.counts) == (FAILED, FAILING, Counts(0, 1, 0))


@needs_runner("go")
def test_framing_printed_by_a_test_is_what_the_bound_concedes(tmp_path: Path) -> None:
    # A `TestMain` printing `\x16--- PASS: TestForged` gets a `pass` event for a test that never
    # ran: the code under test can shape the report.
    got = real(module(tmp_path), "go", "test", "./framing/")
    assert (got.verdict, got.counts) == (PROVED, Counts(2, 0, 0))


@needs_runner("go")
def test_an_event_a_test_prints_is_output(tmp_path: Path) -> None:
    # A test printing a whole `pass` event, without test2json's framing byte, is a line of
    # output, and its own failure is counted.
    got = real(module(tmp_path), "go", "test", "./printing/")
    assert (got.verdict, got.reason, got.counts) == (FAILED, FAILING, Counts(0, 1, 0))


@needs_runner("go")
def test_a_user_env_file_cannot_add_toolexec(tmp_path: Path) -> None:
    # The file `GOENV` names holds `GOFLAGS=-toolexec=<script>`, which the run never reads.
    marker = tmp_path / "toolexec-ran"
    script = executable(tmp_path / "toolexec.sh", f'#!/bin/sh\ntouch "{marker}"\nexit 1\n')
    env_file = tmp_path / "goenv"
    env_file.write_text(f"GOFLAGS=-toolexec={script}\n", encoding="utf-8")
    got = real(module(tmp_path), "go", "test", "./passing/", GOENV=str(env_file))
    assert (got.verdict, got.counts) == (PROVED, Counts(1, 0, 1))
    assert not marker.exists()


@needs_runner("go")
def test_an_inherited_cross_target_runs_no_exec_wrapper(tmp_path: Path) -> None:
    # Under `GOOS=js GOARCH=wasm` the go command runs the test binary under the
    # `go_js_wasm_exec` it finds on `PATH`, which here prints a pass; scrubbed, the run builds
    # for the host and the failing test fails.
    marker = tmp_path / "wrapper-ran"
    shim = executable(
        tmp_path / "wrap" / "go_js_wasm_exec",
        f'#!/bin/sh\ntouch "{marker}"\necho "--- PASS: TestForged (0.00s)"\nexit 0\n',
    )
    go = runner_directory("go")
    path = os.pathsep.join([str(shim.parent), str(go), os.environ.get("PATH", "")])
    got = real(module(tmp_path), "go", "test", "./three/", GOOS="js", GOARCH="wasm", PATH=path)
    assert (got.verdict, got.reason, got.counts) == (FAILED, FAILING, Counts(1, 1, 1))
    assert not marker.exists()
