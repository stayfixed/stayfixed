"""`setup --approval-boundary`: the advice that keeps an agent's shell out of the trust record.

The record holds against repository bytes, and against an agent only while the harness's sandbox
keeps that agent's shell out of its directory, which is the person's to set and stayfixed's never
to check (`trust.boundary` says why). So the command prints the deny rule measured on Claude Code
2.1.296 (macOS) on 2026-10-16 -- `Edit(//<absolute path>/**)` in `permissions.deny` stopped both the
sandboxed shell and the file tools, where one leading slash and a `Write(...)` rule stopped neither
-- and the sandbox settings, and writes nothing. Every path the tests write is under `tmp_path`.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from stayfixed.cli import build_parser, discover_registrars, run
from stayfixed.setup.commands import BOUNDARY_ADVICE
from stayfixed.setup.machine import USER_SETTINGS
from stayfixed.trust.api import ENFORCING_SETTINGS, SANDBOX_ON, managed_named
from stayfixed.trust.boundary import deny_rule


def invoke(argv: list[str]) -> int:
    return run(argv, parser=build_parser(discover_registrars()))


def _advice(tmp_path: Path, machine: Path, *extra: str) -> list[str]:
    home = tmp_path / "home"
    return [
        "setup",
        "--approval-boundary",
        "--home",
        str(home),
        "--machine",
        str(machine),
        *extra,
    ]


def test_the_advice_names_the_rule_and_the_sandbox_and_writes_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # The flag is advice only: the deny rule over the directory the trust record lies in, the
    # user settings file it belongs in, the setting that turns the sandbox on and the managed ones
    # that keep a repository from turning it off -- and no machine file, no settings file, not
    # even the home's `.claude`, since a rule stayfixed wrote would read as a boundary stayfixed
    # keeps. Mutation (`mutations/`'s "setup --approval-boundary runs the machine setup"): the
    # machine file and the settings are written, and the advice is never printed.
    machine = tmp_path / "machine" / "config.toml"
    assert invoke(_advice(tmp_path, machine)) == 0
    out = capsys.readouterr().out
    rule = deny_rule(machine.parent)
    settings = tmp_path / "home" / USER_SETTINGS
    assert out == (
        BOUNDARY_ADVICE.format(
            rules=rule,
            settings=settings,
            sandbox=SANDBOX_ON,
            enforcing=ENFORCING_SETTINGS,
            managed=managed_named(),
        )
        + "\n"
    )
    assert list(tmp_path.iterdir()) == []


def test_the_advice_s_json_carries_the_rule_and_the_files(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # `--json` carries the rule and the two files it names, for a skill that relays them.
    machine = tmp_path / "machine" / "config.toml"
    assert invoke(_advice(tmp_path, machine, "--json")) == 0
    data = json.loads(capsys.readouterr().out)
    assert {key: data[key] for key in ("deny_rules", "settings", "managed")} == {
        "deny_rules": [deny_rule(machine.parent)],
        "settings": str(tmp_path / "home" / USER_SETTINGS),
        "managed": managed_named(),
    }


def test_a_linked_machine_directory_gets_a_rule_for_each_spelling(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # The machine file's directory reached through a symbolic link: the harness compares a write
    # against the path it resolves, so a rule over the link's spelling alone denies nothing. Both
    # are named. Mutation (`mutations/`'s "the approval boundary covers only the directory as
    # named"): the resolved rule is missing.
    real = tmp_path / "real"
    real.mkdir()
    linked = tmp_path / "linked"
    linked.symlink_to(real)
    assert invoke(_advice(tmp_path, linked / "config.toml", "--json")) == 0
    rules = json.loads(capsys.readouterr().out)["deny_rules"]
    assert rules == [deny_rule(linked), deny_rule(real.resolve())]
    assert rules[0] != rules[1]


@pytest.mark.parametrize(
    "flag",
    [
        pytest.param(["--preset", "recommended"], id="preset"),
        pytest.param(["--overlay", "elsewhere"], id="overlay"),
        pytest.param(["--settings", "settings.json"], id="settings"),
        pytest.param(["--yes"], id="yes"),
        pytest.param(["--git-hooks"], id="git-hooks"),
    ],
)
def test_the_advice_beside_a_flag_that_writes_is_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], flag: list[str]
) -> None:
    # A flag that names something to write has no run to belong to beside advice that writes
    # nothing: refused, rather than dropped behind the person's back or run beside it. Mutations
    # (`mutations/`'s "setup --approval-boundary takes a flag that names a write" -> `preset`,
    # `overlay` and `settings` print the advice; "setup --approval-boundary takes --yes or
    # --git-hooks" -> `yes` and `git-hooks` do).
    machine = tmp_path / "machine" / "config.toml"
    assert invoke(_advice(tmp_path, machine, *flag)) == 2
    assert "--approval-boundary prints what to set and writes nothing" in capsys.readouterr().err
    assert list(tmp_path.iterdir()) == []


def test_the_deny_rule_is_the_measured_spelling() -> None:
    # Two leading slashes: one anchors the path at the working directory, which was measured to
    # stop nothing outside it. Mutation (`mutations/`'s "the approval boundary is spelled with one
    # leading slash"): `Edit(/Users/...)`.
    assert deny_rule(Path("/Users/me/.config/stayfixed")) == "Edit(//Users/me/.config/stayfixed/**)"
