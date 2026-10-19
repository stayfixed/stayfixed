"""The `go test` adapter: what it recognises, how it plans a run, and what a real `go test` run
under it proves.

The plan tests run no `go`: `plan` is a pure function of its arguments and of the files it reads.
The tests through `prove` that run no real `go` use `fake_go`, a shell script standing in for `go`
that prints a recorded event stream (`tests/fixtures/prove/reports/go*.jsonl`) and writes down the
arguments and the environment it was run with. The tests marked `runners` run the `go` on `PATH`
over the module `tests/fixtures/prove/go/`, copied into a scratch directory.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from stayfixed.profiles.go.adapters import (
    ADAPTERS,
    CONFIGS,
    DISCOVERY,
    NAME,
    REPORT_NAME,
    GoTestAdapter,
)
from stayfixed.profiles.runners import (
    ENTRY_NOT_FOUND,
    Plan,
    Refused,
    ReportKind,
    ReportSource,
    Unresolved,
)
from stayfixed.prove.counts import REPORT_MALFORMED, Counts
from stayfixed.prove.run import (
    FAILING,
    NONE_RAN,
    Receipt,
    Verdict,
    prove,
)
from tests.prove.projects import go_module
from tests.prove.real_runners import needs_runner, runner_directory

PROVED, FAILED, NOT_PROVEN = Verdict.PROVED, Verdict.FAILED, Verdict.NOT_PROVEN
ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "tests" / "fixtures" / "prove" / "reports"
GO = GoTestAdapter()


def executable(path: Path, text: str = "#!/bin/sh\nexit 0\n") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    path.chmod(0o755)
    return path


def planned(command: list[str], cwd: Path, *, path: str = "") -> Plan | Refused | Unresolved:
    return GO.plan((), command, cwd=cwd, scratch=cwd / "scratch", environ={"PATH": path})


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
        (["/opt/homebrew/bin/go", "test", "./..."], True),
        (["./bin/go", "test"], True),
        (["go", "vet", "./..."], False),
        (["go", "build"], False),
        (["go"], False),
        (["gotest", "./..."], False),
        (["/usr/bin/gofmt", "test"], False),
        (["test", "go"], False),
    ],
)
def test_go_test_is_recognised(command: list[str], recognised: bool) -> None:
    # A path to a `go` is recognised by its name, as the pytest and node adapters read theirs.
    # Mutations (declared): the bare word alone -> the paths are not; every go command -> `go vet`
    # is.
    assert GO.recognises(command) is recognised


def test_the_adapters_this_stack_ships() -> None:
    assert [adapter.name for adapter in ADAPTERS] == [NAME] == ["go-test"]
    assert GO.forging == {}


# --- How a run is planned -------------------------------------------------------------------


def test_the_plan_runs_go_test_with_json(tmp_path: Path) -> None:
    go = executable(tmp_path / "bin" / "go")
    got = planned(["go", "test", "./..."], tmp_path, path=str(go.parent))
    assert got == Plan(
        argv=(str(go), "test", "-json", "./..."),
        kind=ReportKind.EVENTS,
        source=ReportSource.STDOUT,
        report=tmp_path / "scratch" / "events.jsonl",
        discovery=("*_test.go",),
        configs=("go.mod", "go.work"),
    )
    assert (got.discovery, got.configs) == (DISCOVERY, CONFIGS)
    assert got.report.name == REPORT_NAME


@pytest.mark.parametrize("named", ["absolute", "relative"])
def test_a_path_to_go_is_the_program(tmp_path: Path, named: str) -> None:
    # The path the command gives is the `go` that runs, read from the directory the command runs
    # in, whatever `PATH` holds. Mutation (declared): the word `go` run for it -> the `go` on
    # `PATH` runs.
    go = executable(tmp_path / "bin" / "go")
    executable(tmp_path / "elsewhere" / "go")
    word = str(go) if named == "absolute" else "./bin/go"
    got = planned([word, "test", "./..."], tmp_path, path=str(tmp_path / "elsewhere"))
    assert isinstance(got, Plan), got
    assert got.argv == (str(tmp_path / word), "test", "-json", "./...")
    assert os.path.realpath(got.argv[0]) == os.path.realpath(go)


def test_a_path_to_no_go_does_not_resolve(tmp_path: Path) -> None:
    executable(tmp_path / "go")
    got = planned(["./bin/go", "test"], tmp_path, path=str(tmp_path))
    # A path is read from the directory the command runs in, never looked up on `PATH`, and the
    # detail says so (`programs.not_found`). Mutation: none -- the detail is wording.
    assert got == Unresolved(ENTRY_NOT_FOUND, "no executable file at ./bin/go")


@pytest.mark.parametrize(
    ("command", "args"),
    [
        (["go", "test", "./..."], ("-json", "./...")),
        (["go", "test", "-json", "./..."], ("-json", "-json", "./...")),
        (["go", "test", "-v", "--json", "./p"], ("-json", "-v", "--json", "./p")),
        (["go", "test", "-C", "sub", "./..."], ("-C", "sub", "-json", "./...")),
        (["go", "test", "-C=sub", "./..."], ("-C=sub", "-json", "./...")),
        (["go", "test", "--C", "sub"], ("--C", "sub", "-json")),
        (["go", "test", "./...", "-C", "sub"], ("-json", "./...", "-C", "sub")),
        (["go", "test", "-C"], ("-C", "-json")),
        (["go", "test", "./...", "--", "-json"], ("-json", "./...", "--", "-json")),
    ],
    ids=[
        "first",
        "own-json-kept",
        "two-dashes",
        "after-C",
        "after-C-with-equals",
        "after-C-two-dashes",
        "C-not-first",
        "C-with-no-directory",
        "terminator",
    ],
)
def test_json_is_added_after_a_leading_C(
    tmp_path: Path, command: list[str], args: tuple[str, ...]
) -> None:
    # `-C` is read only as the first flag, and the command's words stay as typed: the go command
    # reads a `-json` given twice as one (measured on Go 1.27.2). Mutations (declared): `-json`
    # put before a leading `-C` -> `after-C` starts with it; `-C=dir` read as taking the next word
    # too -> `after-C-with-equals` puts it after `./...`; a flag given two dashes read as no flag
    # -> `after-C-two-dashes` starts with it.
    assert argv_of(command, tmp_path) == args


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
        scratch=tmp_path / "scratch",
        environ={"PATH": str(directory)},
    )
    assert isinstance(got, Plan), got
    assert got.argv[0] == str(go)


def launched_plan(launch: tuple[str, ...], command: list[str], cwd: Path, path: str) -> Plan:
    got = GO.plan(launch, command, cwd=cwd, scratch=cwd / "scratch", environ={"PATH": path})
    assert isinstance(got, Plan), got
    return got


@pytest.mark.parametrize("word", ["go", "./bin/go"])
def test_a_launcher_is_handed_the_go_as_typed(tmp_path: Path, word: str) -> None:
    # `uv run go test ./...`: the launcher is the program, its words kept in front, and the
    # command's words are handed to it as typed, so the `go` that runs is the one the launcher
    # finds (`uv run` puts its environment's `bin` first), not the caller's `PATH`'s. Mutations
    # (declared): the launcher dropped -> the plan runs `go` alone; the `go` on the caller's
    # `PATH` handed by its path -> the plan names it.
    tools = tmp_path / "tools"
    launcher = executable(tools / "uv")
    executable(tmp_path / "bin" / "go")
    got = launched_plan(
        ("uv", "run", "--locked"),
        [word, "test", "./..."],
        tmp_path,
        os.pathsep.join([str(tools), str(tmp_path / "bin")]),
    )
    assert got.argv == (str(launcher), "run", "--locked", word, "test", "-json", "./...")


def test_a_go_only_the_launcher_finds_is_planned(tmp_path: Path) -> None:
    # A `go` only in the virtual environment `uv run` puts first, none on the caller's `PATH`:
    # the run is planned, the launcher finding its `go` as it does outside `prove`. Mutation
    # (declared): the `go` looked up on the caller's `PATH` behind a launcher -> `entry-not-found`.
    tools = tmp_path / "tools"
    launcher = executable(tools / "uv")
    executable(tmp_path / ".venv" / "bin" / "go")
    got = launched_plan(("uv", "run"), ["go", "test", "./q/"], tmp_path, str(tools))
    assert got.argv == (str(launcher), "run", "go", "test", "-json", "./q/")


@pytest.mark.parametrize(
    ("word", "detail"),
    [("uv", "no uv on PATH"), ("./tools/uv", "no executable file at ./tools/uv")],
    ids=["bare", "path"],
)
def test_a_launcher_that_names_nothing_does_not_resolve(
    tmp_path: Path, word: str, detail: str
) -> None:
    go = executable(tmp_path / "bin" / "go")
    got = GO.plan(
        (word, "run"),
        ["go", "test"],
        cwd=tmp_path,
        scratch=tmp_path / "scratch",
        environ={"PATH": str(go.parent)},
    )
    assert got == Unresolved(ENTRY_NOT_FOUND, detail)


def test_the_file_modfile_names_is_among_the_configs(tmp_path: Path) -> None:
    # Mutations (declared): the named file left out -> the adapter's own globs alone; a spaced
    # value not read -> `ci/go.mod` missing; a word past `-args` read -> `x` named; `-args=x` read
    # as `-args` -> `y.mod` missing.
    go = executable(tmp_path / "bin" / "go")
    got = planned(
        [
            *("go", "test", "-modfile", "ci/go.mod", "--modfile=../alt.mod"),
            *("-test.tags", "-modfile=t.mod", "-args=x", "-modfile=y.mod", "-args", "-modfile=x"),
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
        str(real / "y.mod"),
    )


@pytest.mark.parametrize(
    ("command", "named"),
    [
        (["go", "test", "-C", "sub", "-modfile=alt.mod"], "sub/alt.mod"),
        (["go", "test", "--C=sub", "-modfile", "alt.mod"], "sub/alt.mod"),
        (["go", "test", "-modfile=alt.mod", "-C", "sub"], "alt.mod"),
        (["go", "test", "./...", "--", "-modfile=x", "-modfile=alt.mod"], None),
        (["go", "test", "-modfile"], None),
    ],
    ids=["C", "C-with-equals", "C-not-first", "terminator", "no-value"],
)
def test_the_file_modfile_names_is_read_from_where_go_reads_it(
    tmp_path: Path, command: list[str], named: str | None
) -> None:
    # Measured on Go 1.27.2: under a leading `-C sub`, `-modfile=alt.mod` reads `sub/alt.mod`,
    # and a word past `--` is the test binary's. Mutations (declared): `-modfile` read from the
    # run's directory under a leading `-C` -> `C` names `alt.mod`; a bare `--` read as no end ->
    # `terminator` names `alt.mod`.
    go = executable(tmp_path / "bin" / "go")
    got = planned(command, tmp_path, path=str(go.parent))
    assert isinstance(got, Plan), got
    real = Path(os.path.realpath(tmp_path))
    assert got.configs == (*CONFIGS, *(() if named is None else (str(real / named),)))


# --- Nothing is refused ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "flags",
    [
        ("-exec", "qemu-arm"),
        ("-exec=sudo",),
        ("-toolexec=x",),
        ("-overlay", "o.json"),
        ("-o", "bin/x.test"),
        ("-c",),
        ("-json=false",),
        ("-v", "-count=1", "-race", "-cover", "-failfast", "-shuffle", "on"),
        ("-tags", "integration", "-ldflags=-s", "-gcflags", "-N"),
    ],
    ids=lambda value: "_".join(value),
)
def test_every_flag_runs_as_typed(tmp_path: Path, flags: tuple[str, ...]) -> None:
    # A flag that ends the run with no event stream (`-c`, a `-json=false` of the command's own)
    # is the cascade's: `test_a_run_with_no_event_stream_is_never_proved` below.
    assert argv_of(["go", "test", *flags, "./..."], tmp_path) == ("-json", *flags, "./...")


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


def through_fake(
    tmp_path: Path, report: str | Path, code: int, *argv: str, **inherited: str
) -> Receipt:
    """`argv` (`go test ./...` where none is given) proved with `fake_go` first on `PATH`,
    printing `report` (a recorded stream's name, or a path) and exiting `code`."""
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
    command = list(argv) or ["go", "test", "./..."]
    return prove(command, cwd=project, environ=environ, timeout=60)


def seen_env(tmp_path: Path) -> dict[str, str]:
    """The environment the fake `go` ran with."""
    return dict(
        line.split("=", 1)
        for line in (tmp_path / "seen" / "env").read_text(encoding="utf-8").splitlines()
        if "=" in line
    )


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


# What the go command prints on standard output, measured on Go 1.27.2 over the fixture's
# `./passing/` with `-json` first: under `-c`, nothing; under a later `-json=false`, text.
_NO_STREAM = {
    "-c": ("", FAILED, NONE_RAN),
    "-json=false": ("ok  \texample.com/prove/passing\t0.333s\n", NOT_PROVEN, REPORT_MALFORMED),
}


@pytest.mark.parametrize("flag", sorted(_NO_STREAM))
def test_a_run_with_no_event_stream_is_never_proved(tmp_path: Path, flag: str) -> None:
    stream, verdict, reason = _NO_STREAM[flag]
    report = tmp_path / "stream"
    report.write_text(stream, encoding="utf-8")
    got = through_fake(tmp_path, report, 0, "go", "test", flag, "./...")
    assert (got.verdict, got.reason) == (verdict, reason)
    argv = (tmp_path / "seen" / "argv").read_text(encoding="utf-8").splitlines()
    assert argv == ["test", "-json", flag, "./..."]


_GO_ENVIRONMENT = ("GOFLAGS", "GOENV", "GOTOOLCHAIN", "GOROOT", "GOOS", "GOARCH")


def test_the_go_environment_it_inherits_reaches_the_run(tmp_path: Path) -> None:
    # The go command reads its environment as it does outside `prove`: an inherited
    # `GOFLAGS=-tags=integration`, and the go env file `GOENV` names, which holds a `go env -w`
    # setting such as `GOPRIVATE`, reach it unchanged, and the receipt names nothing removed.
    env_file = tmp_path / "goenv"
    env_file.write_text("GOPRIVATE=github.com/acme/*\n", encoding="utf-8")
    inherited = {
        "GOFLAGS": "-tags=integration",
        "GOENV": str(env_file),
        "GOTOOLCHAIN": "auto",
        "GOROOT": str(tmp_path / "sdk"),
        "GOOS": "linux",
        "GOARCH": "arm64",
    }
    got = through_fake(tmp_path, "go-framing.jsonl", 0, **inherited)
    assert (got.verdict, got.scrubbed) == (PROVED, ())
    env = seen_env(tmp_path)
    assert {name: env.get(name) for name in _GO_ENVIRONMENT} == inherited


@pytest.mark.parametrize("name", _GO_ENVIRONMENT)
@pytest.mark.parametrize("spelling", ["bare", "env"])
def test_an_assigned_go_variable_is_planned(tmp_path: Path, name: str, spelling: str) -> None:
    # `env GOARCH=arm64 go test ./...` runs as typed, the variable in the run's environment.
    argv = [f"{name}=assigned", "go", "test", "./..."]
    typed = ["env", *argv] if spelling == "env" else argv
    got = through_fake(tmp_path, "go-framing.jsonl", 0, *typed)
    assert (got.verdict, got.reason) == (PROVED, "")
    assert seen_env(tmp_path)[name] == "assigned"


# --- Real go test runs ----------------------------------------------------------------------


def real(cwd: Path, *argv: str, **variables: str) -> Receipt:
    """`argv` proved in `cwd` with the `go` on `PATH` first."""
    go = runner_directory("go")
    environ = {**os.environ, "PATH": os.pathsep.join([str(go), os.environ.get("PATH", "")])}
    return prove(argv, cwd=cwd, environ={**environ, **variables}, timeout=600)


@needs_runner("go")
def test_the_three_tests_fail(tmp_path: Path) -> None:
    got = real(go_module(tmp_path), "go", "test", "./three/")
    assert (got.verdict, got.reason, got.counts, got.exit_code) == (
        FAILED,
        FAILING,
        Counts(1, 1, 1),
        1,
    )


@needs_runner("go")
def test_testmain_exiting_zero_fails(tmp_path: Path) -> None:
    got = real(go_module(tmp_path), "go", "test", "./testmain/")
    assert (got.verdict, got.reason, got.counts, got.exit_code) == (
        FAILED,
        NONE_RAN,
        Counts(0, 0, 0),
        0,
    )


@needs_runner("go")
def test_a_build_failure_fails(tmp_path: Path) -> None:
    got = real(go_module(tmp_path), "go", "test", "./broken/")
    assert (got.verdict, got.reason, got.counts) == (FAILED, FAILING, Counts(0, 1, 0))


@needs_runner("go")
def test_framing_printed_by_a_test_is_what_the_bound_concedes(tmp_path: Path) -> None:
    # A `TestMain` printing `\x16--- PASS: TestForged` gets a `pass` event for a test that never
    # ran: the code under test can shape the report.
    got = real(go_module(tmp_path), "go", "test", "./framing/")
    assert (got.verdict, got.counts) == (PROVED, Counts(2, 0, 0))


@needs_runner("go")
def test_an_event_a_test_prints_is_output(tmp_path: Path) -> None:
    # A test printing a whole `pass` event, without test2json's framing byte, is a line of
    # output, and its own failure is counted.
    got = real(go_module(tmp_path), "go", "test", "./printing/")
    assert (got.verdict, got.reason, got.counts) == (FAILED, FAILING, Counts(0, 1, 0))


@needs_runner("go")
def test_the_user_s_go_env_file_shapes_the_run(tmp_path: Path) -> None:
    # The file `GOENV` names holds `GOFLAGS=-tags=integration`, which the go command reads as it
    # does outside `prove`: the failing test behind the tag runs.
    project = go_module(tmp_path)
    (project / "passing" / "integration_test.go").write_text(
        '//go:build integration\n\npackage passing\n\nimport "testing"\n\n'
        'func TestIntegration(t *testing.T) { t.Fatal("tagged") }\n',
        encoding="utf-8",
    )
    env_file = tmp_path / "goenv"
    env_file.write_text("GOFLAGS=-tags=integration\n", encoding="utf-8")
    got = real(project, "go", "test", "./passing/", GOENV=str(env_file))
    assert (got.verdict, got.reason, got.counts) == (FAILED, FAILING, Counts(1, 1, 1))


@needs_runner("go")
@pytest.mark.parametrize(
    ("flag", "verdict", "reason"),
    [("-c", FAILED, NONE_RAN), ("-json=false", NOT_PROVEN, REPORT_MALFORMED)],
)
def test_a_flag_that_ends_the_stream_is_never_proved(
    tmp_path: Path, flag: str, verdict: Verdict, reason: str
) -> None:
    got = real(go_module(tmp_path), "go", "test", flag, "./passing/")
    assert (got.verdict, got.reason) == (verdict, reason)
