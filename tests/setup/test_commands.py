"""The `setup` command surface: CLI wiring over `setup.run.setup` and `guards.githooks`.

`tests/setup/test_setup.py` and `tests/setup/test_git_hooks.py` already exercise the two
behaviours directly; what is untested until this file is the argparse wiring itself — the
group is registered, the flags reach the functions those tests call, and a real command-line
invocation exits 0.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from stayfixed.cli import build_parser, discover_registrars, run
from stayfixed.overlay.api import MARKETPLACE_MANIFEST, PLUGIN_MANIFEST
from stayfixed.setup.api import SetupReport
from tests.runners import Recorder


def invoke(argv: list[str]) -> int:
    return run(argv, parser=build_parser(discover_registrars()))


def test_the_command_is_discovered() -> None:
    help_text = build_parser(discover_registrars()).format_help()
    assert "setup" in help_text


def test_the_preset_flow_runs_through_the_cli_with_a_stubbed_runner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Patched at `stayfixed.setup.commands` itself, not at `overlay.api`: that module-level import
    # is what `run_setup` calls directly, so a test that wants to keep this command away from a real
    # `claude`/`codex` monkeypatches a name this module owns rather than reaching two hops into a
    # dependency's own attribute. The recorder answers every call with success, because installing
    # the preset's plugins is unconditional and a test here must never reach a real `claude` or
    # `codex`.
    stub = Recorder()
    monkeypatch.setattr("stayfixed.setup.commands.subprocess_runner", lambda: stub)
    home = tmp_path / "home"
    machine = tmp_path / "config.toml"
    code = invoke(
        [
            "setup",
            "--preset",
            "recommended",
            "--yes",
            "--home",
            str(home),
            "--machine",
            str(machine),
        ]
    )
    assert code == 0
    assert (home / ".claude" / "settings.json").is_file()
    assert machine.is_file()
    # The seam actually fired: at least the marketplace-add call reached the stub rather than
    # a real binary. An empty list here would mean the patch above stopped applying.
    assert stub.calls, "the stubbed runner was never called; the patch may have stopped applying"


def test_git_hooks_and_preset_refuse_to_combine_through_the_cli(tmp_path: Path) -> None:
    code = invoke(["setup", "--preset", "recommended", "--git-hooks", "--root", str(tmp_path)])
    assert code == 2


def test_the_machine_default_is_the_file_every_reader_reads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # `--machine`'s default was `machine_config_path()` with no argument — the only such call in the
    # tree — so it took the `isatty` sniff that every *reader* pins with `interactive=False`. With
    # `XDG_CONFIG_HOME` set, an owner running `stayfixed setup` in their own shell wrote
    # `/xdg/stayfixed/config.toml`, got exit 0, and every reader then said "no overlay root is
    # recorded in the machine configuration; run `stayfixed setup`" — the defect
    # `config.loader.load`'s docstring says it fixed, reintroduced on the write side.
    #
    # Mutation (`mutations/`, "setup's --machine default takes the interactive sniff"):
    # `interactive=False` is dropped from the call in `run_setup` → the file lands under
    # `XDG_CONFIG_HOME` and this reddens on both paths below.
    home = tmp_path / "home"
    xdg = tmp_path / "xdg"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg))
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    # An interactive shell is what makes the sniff answer yes; the reader's answer must not
    # depend on it.
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    stub = Recorder()
    monkeypatch.setattr("stayfixed.setup.commands.subprocess_runner", lambda: stub)
    assert invoke(["setup", "--preset", "recommended", "--yes", "--home", str(home)]) == 0
    assert (home / ".config" / "stayfixed" / "config.toml").is_file()
    assert not (xdg / "stayfixed" / "config.toml").exists()
    assert stub.calls, "the stubbed runner was never called; the patch may have stopped applying"


def test_setup_help_names_no_path_from_the_machine_the_parser_was_built_on(
    capsys: pytest.CaptureFixture[str],
) -> None:
    # The second half of the same finding: both defaults used to be computed when the parser is
    # built, so `stayfixed setup --help` printed the developer's own home directory — and it was
    # computed on every run of every command, since the parser is built for all of them.
    with pytest.raises(SystemExit):
        invoke(["setup", "--help"])
    printed = capsys.readouterr().out
    assert "--machine" in printed
    assert str(Path.home()) not in printed
    assert "~/.config/stayfixed/config.toml" in printed


def test_settings_reaches_setup_as_a_path_and_not_as_the_string_argparse_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The `--settings` flag, through argv rather than through the library seam: the parser accepts
    # `--settings` beside the other four, and `run_setup` hands `setup()` a `Path` under the keyword
    # `settings`. Asserted on the keyword's value and not merely on exit 0, because a `run_setup`
    # that parsed the flag and dropped it would exit 0 too.
    #
    # Mutation: none of its own. `mutations/`'s "setup ignores --settings and writes under
    # home" reddens the library-level test in `tests/setup/test_setup.py`; this test is about
    # the wiring above it, and the wiring's own failure mode is a `TypeError` at the call.
    seen: dict[str, object] = {}

    def fake_setup(preset: str, **kwargs: object) -> SetupReport:
        seen["preset"] = preset
        seen.update(kwargs)
        return SetupReport(
            machine_written=True,
            plugins_installed=(),
            deny_written=True,
            cli_on_path=True,
            overlay=None,
            notes=(),
        )

    monkeypatch.setattr("stayfixed.setup.run.setup", fake_setup)
    settings = tmp_path / "dotfiles" / "claude" / "settings.json"
    code = invoke(
        [
            "setup",
            "--preset",
            "recommended",
            "--home",
            str(tmp_path / "home"),
            "--machine",
            str(tmp_path / "config.toml"),
            "--settings",
            str(settings),
            "--root",
            str(tmp_path),
        ]
    )
    assert code == 0
    assert seen["settings"] == settings


def test_a_tilde_in_settings_is_expanded_the_way_home_and_machine_already_are(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # `--home` and `--machine` are both `expanduser`'d in `run_setup` and `--settings` was not,
    # while the README row this flag ships advertises `--settings ~/dotfiles/claude/settings.json`.
    # From a shell that works because the shell expands it; from an agent harness passing argv as a
    # list -- the harness this project is written for --
    # `Path("~/dotfiles/claude/settings.json").parent` is the *relative* path `~/dotfiles/claude`,
    # so the run either creates a literal `~` directory under the cwd or dies on the missing one.
    #
    # Mutation (declared): drop the `.expanduser()` -> the recorded keyword is the unexpanded
    # `Path("~/...")` and this reddens naming both.
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    seen: dict[str, object] = {}

    def fake_setup(preset: str, **kwargs: object) -> SetupReport:
        seen.update(kwargs)
        return SetupReport(
            machine_written=True,
            plugins_installed=(),
            deny_written=True,
            cli_on_path=True,
            overlay=None,
            notes=(),
        )

    monkeypatch.setattr("stayfixed.setup.run.setup", fake_setup)
    code = invoke(
        [
            "setup",
            "--preset",
            "recommended",
            "--home",
            str(home),
            "--machine",
            str(tmp_path / "config.toml"),
            "--settings",
            "~/dotfiles/claude/settings.json",
            "--root",
            str(tmp_path),
        ]
    )
    assert code == 0
    assert seen["settings"] == home / "dotfiles" / "claude" / "settings.json"
    assert "~" not in str(seen["settings"])


# Two manifests that are valid JSON past this interpreter's parser: nested deeper than it follows,
# and holding an integer longer than it converts (4,300 digits by default).
PAST_THE_PARSER = {
    "nested": "[" * 200_000 + "]" * 200_000,
    "long-number": '{"name": ' + "1" * 5_000 + "}",
}


@pytest.mark.parametrize("manifest", [PLUGIN_MANIFEST, MARKETPLACE_MANIFEST])
@pytest.mark.parametrize("case", sorted(PAST_THE_PARSER))
def test_an_overlay_manifest_past_the_parser_is_refused_as_unreadable_through_the_cli(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    case: str,
    manifest: str,
) -> None:
    # `overlay_fault` caught only `JSONDecodeError`, and `json.loads` meets neither document with
    # one: nesting past what it follows raises `RecursionError`, and the long integer a plain
    # `ValueError`. So `stayfixed setup --overlay` ended in an internal error instead of refusing
    # a tree whose manifests it cannot read. Each manifest in turn, the other one well-formed, so
    # the refusal is about the one asked. Nothing is recorded, and the runner is never reached:
    # the probe runs above every write.
    #
    # Mutation (oracle): `mutations/`'s "the overlay probe lets a manifest past the parser escape"
    # -> the internal error comes back and every case reddens.
    overlay = tmp_path / "overlay"
    (overlay / ".claude-plugin").mkdir(parents=True)
    (overlay / PLUGIN_MANIFEST).write_text(json.dumps({"name": "stayfixed-overlay"}), "utf-8")
    (overlay / MARKETPLACE_MANIFEST).write_text(
        json.dumps({"name": "stayfixed-overlay-marketplace", "plugins": []}), "utf-8"
    )
    (overlay / manifest).write_text(PAST_THE_PARSER[case], encoding="utf-8")
    stub = Recorder()
    monkeypatch.setattr("stayfixed.setup.commands.subprocess_runner", lambda: stub)
    machine = tmp_path / "config.toml"
    argv = ["setup", "--yes", "--overlay", str(overlay), "--home", str(tmp_path / "home")]
    code = invoke([*argv, "--machine", str(machine), "--root", str(tmp_path / "project")])
    err = capsys.readouterr().err
    assert "internal error" not in err
    assert f"stayfixed: refused: {overlay} carries a {manifest} that cannot be read as JSON" in err
    assert code == 2
    assert not machine.exists()
    assert stub.calls == []
