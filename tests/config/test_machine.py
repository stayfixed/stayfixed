from __future__ import annotations

from pathlib import Path

import pytest

from stayfixed.config.machine import (
    anchor_home,
    home_is_empty,
    homes_agree,
    machine_config_path,
    override_is_honoured,
    owner_home,
    passwd_home,
)
from tests.ownerhome import as_owner_home


@pytest.mark.parametrize("terminal", [False, True], ids=["off-a-terminal", "at-a-terminal"])
@pytest.mark.parametrize(
    "variables",
    [
        {"STAYFIXED_CONFIG": "hostile.toml", "XDG_CONFIG_HOME": "hostile-dir"},
        {"XDG_CONFIG_HOME": "hostile-dir"},
    ],
    ids=["both", "xdg-alone"],
)
def test_no_variable_moves_the_machine_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, variables: dict[str, str], terminal: bool
) -> None:
    # Both variables reach the same file, so the assertion is the *fallback* path and not the
    # one either variable chose. Asserting `tmp_path / "stayfixed" / "config.toml"` here — the
    # location `XDG_CONFIG_HOME` picks — is what let the gate on `STAYFIXED_CONFIG` pass while
    # its ungated sibling three lines below honoured the repository's choice anyway. The variable
    # on its own costs a repository a path segment and nothing else, so it is a case alone. And
    # from a terminal too: every reader and writer asks for one file, so the file a person writes
    # is the file a hook reads. Mutation (oracle): `mutations/`'s "the machine path honours
    # XDG_CONFIG_HOME again".
    home = tmp_path / "home"
    as_owner_home(monkeypatch, home)
    monkeypatch.setattr("sys.stdin.isatty", lambda: terminal)
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


@pytest.mark.parametrize("spelling", ["relative", "absolute"])
def test_home_is_ignored_when_the_caller_is_not_interactive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, spelling: str
) -> None:
    # A direnv, mise or devcontainer setup can set `HOME` for a hook from a file the clone
    # commits (Claude Code's `env` block cannot), and relative, it lands inside the clone the
    # hook runs in. Off a terminal the home directory is the password database's, so the file is
    # the owner's whatever `HOME` says. Mutations (oracle): `mutations/`'s "the hook path takes the
    # home directory from HOME again" -> `owner_home`; "the machine file follows HOME again".
    owner = tmp_path / "owner"
    as_owner_home(monkeypatch, owner)
    monkeypatch.chdir(tmp_path)
    planted = "fakehome" if spelling == "relative" else str(tmp_path / "fakehome")
    monkeypatch.setenv("HOME", planted)
    assert owner_home(interactive=False) == owner
    assert machine_config_path() == owner / ".config" / "stayfixed" / "config.toml"


def test_home_is_honoured_from_an_interactive_shell(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The other half of the same gate: a person at a terminal whose `HOME` differs from the
    # database's entry, as in a container, keeps the `HOME` they set for what it decides there,
    # and the machine file stays under the database's home, where a hook reads it.
    as_owner_home(monkeypatch, tmp_path / "owner")
    monkeypatch.setenv("HOME", str(tmp_path / "chosen"))
    assert owner_home(interactive=True) == tmp_path / "chosen"
    assert machine_config_path() == tmp_path / "owner" / ".config" / "stayfixed" / "config.toml"


def test_a_user_the_password_database_does_not_list_has_no_home_off_a_terminal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A container run under a uid with no entry. There is no anchor but the environment, and the
    # environment is what this rule exists not to trust: there is no machine file, rather than one
    # `HOME` chose.
    as_owner_home(monkeypatch, None)
    monkeypatch.setenv("HOME", str(tmp_path))
    assert owner_home(interactive=False) is None
    assert machine_config_path() is None


@pytest.mark.parametrize("recorded", ["", "relative/home"])
def test_a_home_the_database_records_as_no_absolute_path_is_no_home(
    monkeypatch: pytest.MonkeyPatch, recorded: str
) -> None:
    as_owner_home(monkeypatch, recorded)
    assert passwd_home() is None


def test_the_anchor_is_the_databases_home_resolved_and_home_as_typed_at_a_terminal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = tmp_path / "real"
    real.mkdir()
    linked = tmp_path / "linked"
    linked.symlink_to(real, target_is_directory=True)
    as_owner_home(monkeypatch, linked)
    monkeypatch.setenv("HOME", str(linked))
    assert anchor_home(interactive=False) == real.resolve()
    assert anchor_home(interactive=True) == linked


@pytest.mark.parametrize(
    ("home", "agrees"),
    [("the-databases", True), ("unset", True), ("empty", False), ("another", False)],
)
def test_an_empty_home_is_a_value_that_names_no_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, home: str, agrees: bool
) -> None:
    # An unset `HOME` sends every program to the password database, so it agrees; an empty one is
    # read as `""` by the shells' `~`, git and Node's `os.homedir` and as `/` by Python's
    # `Path.home`, never as the database's home, so it does not, even run from the database's home,
    # where `Path("").resolve()` is that home. Mutations (oracle): `mutations/`'s "an empty HOME
    # agrees with the password database's home" -> `empty`; "an empty HOME is read as the
    # directory a command runs in" -> `empty` too, because the process runs in the database's home
    # here; "any HOME agrees with the password database's home" -> `another`.
    owner = tmp_path / "owner"
    owner.mkdir()
    as_owner_home(monkeypatch, owner)
    monkeypatch.chdir(owner)
    env = {
        "the-databases": {"HOME": str(owner)},
        "unset": {},
        "empty": {"HOME": ""},
        "another": {"HOME": str(tmp_path)},
    }[home]
    assert homes_agree(env) is agrees


def test_an_empty_home_at_a_terminal_names_no_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # At a terminal `HOME` is the home asked, and an empty one names none, as `homes_agree` reads
    # it. `Path.home` answers `/` for it, so `attach` there aimed the harness memory link at
    # `/.claude/projects/...` and ended in an internal error where the root was read-only. Off a
    # terminal the home is the database's, whatever `HOME` holds. Mutation (oracle): `mutations/`'s
    # "an empty HOME at a terminal is read as the root directory" -> `/` at a terminal.
    owner = tmp_path / "owner"
    owner.mkdir()
    as_owner_home(monkeypatch, owner)
    monkeypatch.setenv("HOME", "")
    assert home_is_empty()
    assert owner_home(interactive=True) is None
    assert anchor_home(interactive=True) is None
    assert owner_home(interactive=False) == owner
    assert anchor_home(interactive=False) == owner.resolve()
    monkeypatch.delenv("HOME")
    assert not home_is_empty()
    assert owner_home(interactive=True) == owner
