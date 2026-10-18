"""`stayfixed prove -- COMMAND …` through the real parser, as a person types it.

`tests/cli.py`'s runner appends `--root` and `--machine` to the line, which here would land inside
the command `prove` runs, and `prove` takes neither: so these cases run the parser on the line
alone, in the directory the command is typed in.
"""

from __future__ import annotations

import io
import json
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import pytest

from stayfixed.cli import build_parser, discover_registrars, run
from stayfixed.profiles.runners import ReportSource
from stayfixed.prove import run as prove_run
from tests.gitfixture import git
from tests.prove.stand_in import NAME, StandIn


def prove_cli(
    cwd: Path, monkeypatch: pytest.MonkeyPatch, *argv: str, adapter: StandIn | None = None
) -> tuple[int, str, str]:
    """The exit code, standard output and standard error of `stayfixed prove <argv>` typed in
    `cwd`, with the stand-in as the one adapter shipped."""
    monkeypatch.chdir(cwd)
    monkeypatch.setattr(prove_run, "shipped_adapters", lambda: (adapter or StandIn(),))
    parser = build_parser(discover_registrars())
    with redirect_stdout(io.StringIO()) as out, redirect_stderr(io.StringIO()) as err:
        try:
            code = run(["prove", *argv], parser=parser)
        except SystemExit as exc:
            code = int(exc.code or 0)
    return code, out.getvalue(), err.getvalue()


CASES = {
    "proved": ([NAME], 0),
    "failed": ([NAME, "--report", "fail", "--code", "1"], 1),
    "not proven": ([NAME, "--report", "none"], 1),
    "refused": (["FORGE=x", NAME], 2),
}


@pytest.mark.parametrize(("verdict", "code"), [(v, c) for v, (_, c) in CASES.items()])
def test_the_command_exits_by_verdict_and_words_each_apart(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, verdict: str, code: int
) -> None:
    argv, _ = CASES[verdict]
    got, out, _ = prove_cli(tmp_path, monkeypatch, "--", *argv)
    assert got == code
    assert out.startswith(f"{verdict}: ")
    shown, out, _ = prove_cli(tmp_path, monkeypatch, "--json", "--", *argv)
    assert shown == code
    receipt = json.loads(out)
    assert receipt["verdict"] == verdict
    assert receipt["summary"].startswith(f"{verdict}: ")


def test_every_arm_is_worded_apart(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    lines = {
        verdict: prove_cli(tmp_path, monkeypatch, "--", *argv)[1]
        for verdict, (argv, _) in CASES.items()
    }
    assert len(set(lines.values())) == len(lines)
    words = prove_run.WORDS
    assert len(set(words.values())) == len(words)


def test_the_line_names_the_counts_the_runner_and_the_files_that_shape_the_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    git(tmp_path, "init", "-q")
    (tmp_path / "stand-in.toml").write_text("", encoding="utf-8")
    (tmp_path / "test_new.py").write_text("", encoding="utf-8")
    code, out, _ = prove_cli(tmp_path, monkeypatch, "--", NAME, "--report", "fail", "--code", "1")
    assert code == 1
    assert "1 passed, 1 failed, 0 skipped" in out
    assert f"runner {NAME}" in out
    assert "stand-in.toml" in out
    assert "test_new.py" in out


@pytest.mark.parametrize(
    "argv",
    [
        [],
        ["--"],
        [NAME],
        ["--timeout", "5"],
        ["--timeout", "soon", "--", NAME],
        ["--timeout", "0", "--", NAME],
        ["--timeout", "nan", "--", NAME],
    ],
)
def test_a_missing_separator_or_command_is_a_usage_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, argv: list[str]
) -> None:
    code, out, err = prove_cli(tmp_path, monkeypatch, *argv)
    assert code == 2
    assert out == ""
    assert "usage: stayfixed prove" in err


def test_the_timeout_reaches_the_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    asked: list[float] = []
    real = prove_run.prove

    def spy(argv: list[str], **kwargs: object) -> object:
        asked.append(kwargs["timeout"])  # type: ignore[arg-type]
        return real(argv, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr("stayfixed.prove.commands.prove", spy)
    prove_cli(tmp_path, monkeypatch, "--timeout", "7", "--", NAME)
    prove_cli(tmp_path, monkeypatch, "--", NAME)
    assert asked == [7.0, prove_run.PROVE_TIMEOUT_SECONDS]


def test_prove_needs_no_stayfixed_toml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # `prove` reads no configuration: a repository with none, and one whose file the loader
    # refuses, are proved alike.
    git(tmp_path, "init", "-q")
    assert prove_cli(tmp_path, monkeypatch, "--", NAME)[0] == 0
    (tmp_path / "stayfixed.toml").write_text("[[[ not toml\n", encoding="utf-8")
    assert prove_cli(tmp_path, monkeypatch, "--", NAME)[0] == 0


def test_a_report_on_standard_output_reaches_a_text_only_stream_before_the_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A caller whose standard output takes text alone, as a test's capture does, still gets the
    # runner's every byte, ahead of the verdict's line. Mutation (declared): the tee writing to a
    # binary stream alone -> the events never reach it.
    adapter = StandIn(source=ReportSource.STDOUT)
    code, out, _ = prove_cli(tmp_path, monkeypatch, "--", NAME, adapter=adapter)
    assert code == 0
    event = json.dumps({"Action": "pass", "Package": "p", "Test": "TestA"})
    assert out.startswith(f"{event}\n")
    assert out.splitlines()[-1].startswith("proved: ")
