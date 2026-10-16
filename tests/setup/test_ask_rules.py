"""The `ask` rules `setup` writes for approvals, and `setup --approval-boundary`'s deny rule.

Each rule is a literal measured on Claude Code 2.1.296 (macOS) on 2026-10-16: with
`Bash(stayfixed trust approve:*)` in the user's `permissions.ask`, the bare spelling and the
`script -q /dev/null` wrapper asked (and `-p`, which treats `ask` as deny, refused them), while
`python -m stayfixed`, `uvx stayfixed` and the absolute path each ran unasked, so each needs a rule
of its own; and `Edit(//<absolute path>/**)` in `permissions.deny` stopped both the sandboxed shell
and the file tools, where one leading slash and a `Write(...)` rule stopped neither. Every path
the tests write is under `tmp_path`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from stayfixed.cli import build_parser, discover_registrars
from stayfixed.cli import run as cli_run
from stayfixed.errors import Refusal
from stayfixed.printed import quoted
from stayfixed.setup import run
from stayfixed.setup.api import USER_SETTINGS, SetupReport, setup
from stayfixed.setup.machine import read_machine, write_machine
from stayfixed.trust.api import deny_rule, managed_settings
from tests.runners import Recorder

# Every spelling an agent's shell reaches stayfixed by that the bare rule does not cover, for the
# approval and for its old spelling, as measured on Claude Code 2.1.296. Never `revoke`.
MEASURED_ASK = (
    "Bash(stayfixed trust approve:*)",
    "Bash(python -m stayfixed trust approve:*)",
    "Bash(python3 -m stayfixed trust approve:*)",
    "Bash(uvx stayfixed trust approve:*)",
    "Bash(stayfixed memory trust:*)",
    "Bash(python -m stayfixed memory trust:*)",
    "Bash(python3 -m stayfixed memory trust:*)",
    "Bash(uvx stayfixed memory trust:*)",
)
# A rule the owner wrote for something else, which no switch of stayfixed's may take away.
OWNERS_OWN = "Bash(rm:*)"


def _own(tmp_path: Path) -> Path:
    return tmp_path / "bin" / "stayfixed"


def _setup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    boundary: bool = False,
    own: Path | None = None,
) -> SetupReport:
    monkeypatch.setattr(run, "running_command", lambda: own)
    return setup(
        "recommended",
        home=tmp_path / "home",
        machine=tmp_path / "config.toml",
        runner=Recorder(),
        yes=False,
        overlay=None,
        project_root=tmp_path / "project",
        boundary=boundary,
    )


def _settings(tmp_path: Path) -> dict[str, Any]:
    document: dict[str, Any] = json.loads(
        (tmp_path / "home" / USER_SETTINGS).read_text(encoding="utf-8")
    )
    return document


def _ask(tmp_path: Path) -> list[str]:
    asked: list[str] = _settings(tmp_path)["permissions"].get("ask", [])
    return asked


def _added(tmp_path: Path) -> dict[str, list[str]]:
    table = read_machine(tmp_path / "config.toml").get("setup", {})
    added: dict[str, list[str]] = table.get("added_rules", {})
    return added


def _switch_off(tmp_path: Path) -> None:
    raw = read_machine(tmp_path / "config.toml")
    write_machine(
        tmp_path / "config.toml",
        personal={},
        overlay_root=None,
        machine={},
        setup={**raw.get("setup", {}), "ask_rules": False},
    )


def _seed_settings(tmp_path: Path, document: dict[str, Any]) -> None:
    path = tmp_path / "home" / USER_SETTINGS
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document), encoding="utf-8")


def test_the_measured_rules_are_the_constant() -> None:
    # The spellings are a fact about Claude Code, held here as the literals measured, so a change
    # to `ASK_RULES` is a change to this list too. No mutation of its own: it is the anchor every
    # case below compares against, and a rule dropped from the constant reddens here.
    assert run.ASK_RULES == MEASURED_ASK
    assert not any("revoke" in rule for rule in run.ASK_RULES)


def test_setup_adds_the_ask_rules_once_and_records_them(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The measured spellings, and the one this run's own `stayfixed` is reached by, for both the
    # approval and its old spelling; recorded in the machine file as stayfixed's, and added once
    # however often `setup` runs. Mutations (`mutations/`'s "setup adds the ask rules it already
    # wrote again" -> the second run doubles them; "setup records none of the ask rules it adds"
    # -> the record is empty; "setup asks nothing for the absolute path it runs as" -> the two
    # path rules are missing).
    own = _own(tmp_path)
    expected = [
        *MEASURED_ASK,
        f"Bash({own} trust approve:*)",
        f"Bash({own} memory trust:*)",
    ]
    report = _setup(tmp_path, monkeypatch, own=own)
    assert _ask(tmp_path) == expected
    assert _added(tmp_path) == {"ask": expected}
    assert report.ask_added == tuple(expected)
    again = _setup(tmp_path, monkeypatch, own=own)
    assert _ask(tmp_path) == expected
    assert _added(tmp_path) == {"ask": expected}
    assert again.ask_added == ()


def test_an_ask_rule_the_owner_typed_first_is_never_recorded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A rule already in the owner's file is theirs: `setup` neither adds it again nor records it,
    # so switching the rules off later leaves it. Mutation (`mutations/`'s "setup records an ask
    # rule the owner wrote"): the owner's rule lands in the record.
    _seed_settings(tmp_path, {"permissions": {"ask": [MEASURED_ASK[0]]}})
    _setup(tmp_path, monkeypatch)
    assert _ask(tmp_path) == list(MEASURED_ASK)
    assert _added(tmp_path) == {"ask": list(MEASURED_ASK[1:])}


def test_switching_off_removes_only_recorded_rules(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # `[setup] ask_rules = false` takes back exactly what the record says stayfixed added: an
    # identical rule the owner typed first stays, and so does a rule of the owner's own. Mutation
    # (`mutations/`'s "switching the ask rules off takes every ask rule"): both of the owner's
    # rules go.
    _seed_settings(tmp_path, {"permissions": {"ask": [MEASURED_ASK[0], OWNERS_OWN]}})
    _setup(tmp_path, monkeypatch)
    _switch_off(tmp_path)
    report = _setup(tmp_path, monkeypatch)
    assert _ask(tmp_path) == [MEASURED_ASK[0], OWNERS_OWN]
    assert _added(tmp_path) == {}
    assert report.ask_removed == MEASURED_ASK[1:]
    # And a run with the switch still off adds nothing back.
    _setup(tmp_path, monkeypatch)
    assert _ask(tmp_path) == [MEASURED_ASK[0], OWNERS_OWN]


def test_a_run_stopped_at_the_record_converges_on_the_next(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The record is written before the settings file gains a rule, so a run that stops between
    # the two leaves rules recorded and not yet written, which the next run writes: the record
    # always covers every rule stayfixed put in the file. Written the other way round, a run that
    # stopped there left rules in the file that no record names, which the next run reads as the
    # owner's and switching off never takes back. Mutation (`mutations/`'s "setup writes the ask
    # rules before it records them"): the record stays empty after the second run.
    real = write_machine

    def stops_at_the_record(path: Path, **tables: Any) -> object:
        if tables.get("setup"):
            raise OSError("the machine file stopped taking writes")
        return real(path, **tables)

    monkeypatch.setattr("stayfixed.setup.run.write_machine", stops_at_the_record)
    with pytest.raises(OSError):
        _setup(tmp_path, monkeypatch)
    monkeypatch.setattr("stayfixed.setup.run.write_machine", real)
    _setup(tmp_path, monkeypatch)
    assert _ask(tmp_path) == list(MEASURED_ASK)
    assert _added(tmp_path) == {"ask": list(MEASURED_ASK)}


def test_a_switch_off_stopped_at_the_settings_file_converges_on_the_next(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Taking the rules back writes the settings file first and the record after, so a run that
    # stops at the settings file leaves the record whole, and the next run takes the rules back.
    # Written the other way round, the record went first and the rules stayed for ever. Mutation
    # (`mutations/`'s "switching the ask rules off forgets them before it removes them"): the
    # rules are still in the file after the second run.
    _setup(tmp_path, monkeypatch)
    _switch_off(tmp_path)
    real = run._write_user_settings

    def stops_at_the_settings(*args: Any, **kwargs: Any) -> bool:
        if kwargs.get("ask_remove"):
            raise OSError("the settings file stopped taking writes")
        written: bool = real(*args, **kwargs)
        return written

    monkeypatch.setattr(run, "_write_user_settings", stops_at_the_settings)
    with pytest.raises(OSError):
        _setup(tmp_path, monkeypatch)
    monkeypatch.setattr(run, "_write_user_settings", real)
    _setup(tmp_path, monkeypatch)
    assert _ask(tmp_path) == []
    assert _added(tmp_path) == {}


def test_setup_never_writes_a_sandbox_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # `--approval-boundary` adds the measured deny rule over the trust record's directory,
    # records it as stayfixed's, and says which sandbox settings to set: the sandbox is the
    # person's to switch on, and a setting this command wrote would be one it could not tell from
    # theirs. Mutations (`mutations/`'s "the approval boundary is never added" -> no deny rule;
    # "the approval boundary is spelled with one leading slash" -> the rule anchors at the working
    # directory, which was measured to stop nothing outside it).
    report = _setup(tmp_path, monkeypatch, boundary=True)
    settings = _settings(tmp_path)
    assert "sandbox" not in settings
    rule = "Edit(/" + str(tmp_path) + "/**)"
    assert rule.startswith("Edit(//")
    assert rule in settings["permissions"]["deny"]
    assert _added(tmp_path)["deny"] == [rule]
    assert report.boundary == rule
    assert run.SANDBOX_ADVICE.format(
        rule=rule, settings=tmp_path / "home" / USER_SETTINGS, managed=managed_settings()
    ) in (report.notes)
    # Without the flag a second run leaves the rule where it is and adds nothing.
    again = _setup(tmp_path, monkeypatch)
    assert rule in _settings(tmp_path)["permissions"]["deny"]
    assert again.boundary is None


def test_the_flag_reaches_setup_through_the_cli(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # `--approval-boundary` on the command line is the run above, and `--json` carries what it
    # added; with `--git-hooks` it is refused, since the two write different places. Mutation
    # (`mutations/`'s "setup's command line drops --approval-boundary"): no rule is added.
    stub = Recorder()
    monkeypatch.setattr("stayfixed.setup.commands.subprocess_runner", lambda: stub)
    monkeypatch.setattr(run, "running_command", lambda: None)
    machine = tmp_path / "config.toml"
    argv = ["setup", "--home", str(tmp_path / "home"), "--machine", str(machine), "--json"]
    assert cli_run([*argv, "--approval-boundary"], parser=build_parser(discover_registrars())) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["boundary"] == deny_rule(tmp_path)
    assert data["ask_added"] == list(MEASURED_ASK)
    assert data["ask_removed"] == []
    hooks = ["setup", "--git-hooks", "--approval-boundary", "--root", str(tmp_path)]
    assert cli_run(hooks, parser=build_parser(discover_registrars())) == 2


def test_the_deny_rule_is_the_measured_spelling() -> None:
    # Two leading slashes: one anchors the path at the working directory, which was measured to
    # stop nothing outside it. Mutation (`mutations/`'s "the approval boundary is spelled with one
    # leading slash"): `Edit(/Users/...)`.
    assert deny_rule(Path("/Users/me/.config/stayfixed")) == "Edit(//Users/me/.config/stayfixed/**)"


def test_a_path_a_rule_cannot_hold_gets_no_rule_and_a_note(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A command path with a space or a parenthesis would be a rule no command line matches, which
    # reads as protection and is none; it is left out and said. Mutation (`mutations/`'s "setup
    # writes an ask rule for a path no rule can hold"): the rules for the spaced path appear.
    spaced = tmp_path / "my tools" / "stayfixed"
    report = _setup(tmp_path, monkeypatch, own=spaced)
    assert _ask(tmp_path) == list(MEASURED_ASK)
    assert run.UNRULABLE_PATH.format(path=quoted(str(spaced))) in report.notes


@pytest.mark.parametrize(
    ("table", "refusal"),
    [
        pytest.param('ask_rules = "no"', "ASK_RULES_NOT_A_SWITCH", id="switch-not-a-bool"),
        pytest.param("added_rules = 3", "ADDED_RULES_UNREADABLE", id="record-not-a-table"),
        pytest.param(
            "added_rules = { ask = [1] }", "ADDED_RULES_UNREADABLE", id="record-not-rules"
        ),
        pytest.param(
            'added_rules = { allow = ["Bash(x)"] }', "ADDED_RULES_UNREADABLE", id="record-stray"
        ),
    ],
)
def test_a_setup_table_setup_cannot_read_refuses_before_any_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, table: str, refusal: str
) -> None:
    # The switch is the owner's and the record is stayfixed's, and a value of neither shape is
    # refused naming the machine file and the key, before the settings file is touched: a record
    # read as empty would leave stayfixed's rules for the owner's, and a switch read as on would
    # write what the owner turned off. Mutations (`mutations/`'s "setup reads a switch that is not
    # true or false as on" -> `switch-not-a-bool` writes; "setup reads a record it cannot read as
    # empty" -> the three record cases write).
    machine = tmp_path / "config.toml"
    machine.write_text(f"[setup]\n{table}\n", encoding="utf-8")
    with pytest.raises(Refusal) as caught:
        _setup(tmp_path, monkeypatch)
    assert str(caught.value) == getattr(run, refusal).format(path=machine)
    assert not (tmp_path / "home" / USER_SETTINGS).exists()
