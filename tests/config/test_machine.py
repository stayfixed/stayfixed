from __future__ import annotations

from pathlib import Path

import pytest

from stayfixed.config.machine import machine_config_path, override_is_honoured, owner_home


@pytest.mark.parametrize(
    "variables",
    [
        {"STAYFIXED_CONFIG": "hostile.toml", "XDG_CONFIG_HOME": "hostile-dir"},
        {"XDG_CONFIG_HOME": "hostile-dir"},
    ],
    ids=["both", "xdg-alone"],
)
def test_no_variable_moves_the_machine_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, variables: dict[str, str]
) -> None:
    # Both variables reach the same file, so the assertion is the *fallback* path and not the
    # one either variable chose. Asserting `tmp_path / "stayfixed" / "config.toml"` here — the
    # location `XDG_CONFIG_HOME` picks — is what let the gate on `STAYFIXED_CONFIG` pass while
    # its ungated sibling three lines below honoured the repository's choice anyway. The variable
    # on its own costs a repository a path segment and nothing else, so it is a case alone.
    # Mutation (oracle): `mutations/`'s "the machine path honours XDG_CONFIG_HOME again".
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    for name, value in variables.items():
        monkeypatch.setenv(name, str(tmp_path / value))
    assert machine_config_path() == home / ".config" / "stayfixed" / "config.toml"


def test_the_default_is_not_interactive_under_a_pipe(monkeypatch: pytest.MonkeyPatch) -> None:
    class NotATty:
        def isatty(self) -> bool:
            return False

    monkeypatch.setattr("sys.stdin", NotATty())
    assert override_is_honoured() is False


def test_a_stdin_that_cannot_answer_is_not_interactive(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.stdin", None)
    assert override_is_honoured() is False


def test_an_empty_home_names_no_home(monkeypatch: pytest.MonkeyPatch) -> None:
    # `Path.home` reads an empty `HOME` as `/`, so `attach` aimed the harness memory link at
    # `/.claude/projects/...`. Mutation (oracle): `mutations/`'s "an empty HOME is read as the
    # root directory".
    monkeypatch.setenv("HOME", "")
    assert owner_home() is None
    assert machine_config_path() is None


@pytest.mark.parametrize("value", ["h", "./h", "~", "h/../home"])
def test_a_relative_home_names_no_home(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    # Taken as typed, a relative `HOME` put the machine file and the trust record under whatever
    # directory a command ran from, inside a clone on the hook path. Mutation (oracle):
    # `mutations/`'s "a relative HOME is read against the working directory".
    monkeypatch.setenv("HOME", value)
    assert owner_home() is None
    assert machine_config_path() is None


def test_an_absolute_and_an_unset_home_still_name_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The vacuity guard for the case above: a check that refused every `HOME` would pass it.
    monkeypatch.setenv("HOME", str(tmp_path))
    assert owner_home() == tmp_path
    monkeypatch.delenv("HOME")
    unset = owner_home()
    assert unset is not None and unset.is_absolute()
