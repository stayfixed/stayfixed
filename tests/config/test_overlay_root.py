"""Which overlay root this machine records: `None` for "not recorded", and a failure for a file
that cannot be read, never the one mistaken for the other."""

from __future__ import annotations

from pathlib import Path

import pytest

from stayfixed.config.loader import MachineConfigError
from stayfixed.config.overlay import overlay_root


def test_overlay_root_reads_the_machine_file(tmp_path: Path) -> None:
    overlay = tmp_path / "o"
    overlay.mkdir()
    machine = tmp_path / "machine.toml"
    machine.write_text(f'[overlay]\nroot = "{overlay}"\n', encoding="utf-8")
    assert overlay_root(machine) == overlay
    machine.write_text("", encoding="utf-8")
    assert overlay_root(machine) is None
    assert overlay_root(tmp_path / "absent.toml") is None


def test_a_machine_file_that_is_not_valid_toml_is_not_an_unrecorded_overlay(
    tmp_path: Path,
) -> None:
    # `config.loader._personal` raises `ConfigError` for this very file and this very syntax
    # error. This reader answered `None`, which the store renders as "no overlay root is
    # recorded … run `stayfixed setup`" — wrong advice for a file that is already there. The
    # loader's class, so the one file has one failure whichever reader meets it first.
    broken = tmp_path / "machine.toml"
    broken.write_text("[overlay\nroot = 'x'\n", encoding="utf-8")
    with pytest.raises(MachineConfigError, match=r"is not valid TOML \(at line 1"):
        overlay_root(broken)


def test_a_machine_file_recording_no_overlay_still_answers_none(tmp_path: Path) -> None:
    blank = tmp_path / "machine.toml"
    blank.write_text("[personal]\n", encoding="utf-8")
    assert overlay_root(blank) is None
    assert overlay_root(tmp_path / "absent.toml") is None


def test_the_overlay_root_never_asks_where_the_machine_file_is(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The overlay root anchors where the note store may resolve, and a committed
    # `.claude/settings.json` can set `STAYFIXED_CONFIG` in a session no person is watching. So
    # with no file named, the root is read from the one place a variable cannot move, even from a
    # terminal, where the variable is otherwise honoured. Mutation (declared): `mutations/`'s "the
    # overlay root reads the machine file a variable names".
    class ATty:
        def isatty(self) -> bool:
            return True

    home = tmp_path / "home"
    (home / ".config" / "stayfixed").mkdir(parents=True)
    (home / ".config" / "stayfixed" / "config.toml").write_text(
        '[overlay]\nroot = "/tmp/recorded"\n', encoding="utf-8"
    )
    chosen = tmp_path / "chosen.toml"
    chosen.write_text('[overlay]\nroot = "/tmp/chosen"\n', encoding="utf-8")
    monkeypatch.setattr("sys.stdin", ATty())
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    monkeypatch.setenv("STAYFIXED_CONFIG", str(chosen))
    assert overlay_root(None) == Path("/tmp/recorded")
