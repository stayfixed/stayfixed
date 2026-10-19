"""`stayfixed.profiles.programs`: a test command's program found the way a shell running the
command finds it, the one rule every runner adapter and `prove --junit` use."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from stayfixed.profiles.programs import before_separator, executable, found, launched


def program(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    path.chmod(0o755)
    return path


def test_a_bare_name_is_the_first_on_the_path(tmp_path: Path) -> None:
    # Mutation (declared): the entries searched last first -> the second.
    first = program(tmp_path / "a" / "tool")
    program(tmp_path / "b" / "tool")
    path = os.pathsep.join([str(first.parent), str(tmp_path / "b")])
    assert found("tool", tmp_path, {"PATH": path}) == first


def test_a_relative_path_entry_is_read_from_the_directory_the_command_runs_in(
    tmp_path: Path,
) -> None:
    tool = program(tmp_path / ".venv" / "bin" / "tool")
    assert found("tool", tmp_path, {"PATH": ".venv/bin"}) == tool


def test_a_word_holding_a_slash_is_read_from_the_directory_never_from_the_path(
    tmp_path: Path,
) -> None:
    # Mutation (declared): every word searched on `PATH` -> the relative path is not found.
    tool = program(tmp_path / "bin" / "tool")
    on_path = program(tmp_path / "elsewhere" / "bin" / "tool")
    assert found("bin/tool", tmp_path, {"PATH": str(on_path.parent.parent)}) == tool
    assert found("missing/tool", tmp_path, {"PATH": str(on_path.parent)}) is None


def test_without_a_path_the_default_search_path_is_read(tmp_path: Path) -> None:
    # As a shell with no `PATH`: `sh` is in `os.defpath` on every system this runs on.
    # Mutation (declared): `mutations/`'s "a run with no PATH searches nothing".
    assert found("sh", tmp_path, {}) is not None


def test_a_file_that_cannot_be_executed_and_a_directory_are_passed_over(tmp_path: Path) -> None:
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "tool").write_text("", encoding="utf-8")
    (tmp_path / "b" / "tool").mkdir(parents=True)
    tool = program(tmp_path / "c" / "tool")
    path = os.pathsep.join(str(tmp_path / name) for name in ("a", "b", "c"))
    assert found("tool", tmp_path, {"PATH": path}) == tool
    assert not executable(tmp_path / "a" / "tool")
    assert not executable(tmp_path / "b" / "tool")


def test_a_path_entry_that_cannot_be_asked_about_is_passed_over(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Root reads every directory, so the fault is stood in for. Mutation (declared):
    # `mutations/`'s "a PATH entry that cannot be asked about raises".
    tool = program(tmp_path / "bin" / "tool")
    blind = tmp_path / "blind"
    asked = os.stat

    def stat(path: Path, **options: bool) -> os.stat_result:
        if Path(path).parent == blind:
            raise PermissionError(13, "denied", str(path))
        return asked(path, **options)

    path = os.pathsep.join([str(blind), str(tool.parent)])
    # Undone before pytest reports, whose own cleanup asks `os.stat` (with `follow_symlinks`
    # from 3.13's pathlib); a raise left in place broke the run rather than reddening it.
    with monkeypatch.context() as patched:
        patched.setattr(os, "stat", stat)
        try:
            result: Path | OSError | None = found("tool", tmp_path, {"PATH": path})
        except OSError as raised:
            result = raised
    assert result == tool


def test_the_launcher_is_kept_in_front_and_found(tmp_path: Path) -> None:
    # Mutation (declared): `mutations/`'s "a launcher's words are dropped from the argv" -> the
    # argv is the command's alone.
    uv = program(tmp_path / "bin" / "uv")
    environ = {"PATH": str(uv.parent)}
    assert launched(("uv", "run", "--locked"), ("pytest", "-q"), tmp_path, environ) == (
        str(uv),
        "run",
        "--locked",
        "pytest",
        "-q",
    )
    assert launched((), ("uv", "--version"), tmp_path, environ) == (str(uv), "--version")
    assert launched(("missing", "run"), ("pytest",), tmp_path, environ) is None
    assert launched((), (), tmp_path, environ) is None


@pytest.mark.parametrize(
    ("args", "planned"),
    [
        (("-q",), ("-q", "OURS")),
        (("-q", "--", "tests"), ("-q", "OURS", "--", "tests")),
        (("--", "a", "--", "b"), ("OURS", "--", "a", "--", "b")),
        ((), ("OURS",)),
    ],
)
def test_the_runner_s_options_go_before_the_first_separator(
    args: tuple[str, ...], planned: tuple[str, ...]
) -> None:
    # Mutation (declared): `ours` added last -> it follows `--`, where the runner reads operands.
    assert before_separator(args, ("OURS",)) == planned
