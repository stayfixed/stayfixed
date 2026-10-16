"""`doctor`'s `approval-boundary` row: whether this project's effective Claude Code settings keep an
agent from writing the trust record itself.

The settings files are built from literals measured on Claude Code 2.1.296 (macOS) on 2026-10-16:
a project's or a local file's `sandbox.enabled = false` turns a user's sandbox off, and a user's
`sandbox.allowUnsandboxedCommands = false` does not stop that; managed settings setting it make
the sandbox admin-required, and then a repository's `false` is ignored; `Edit(//<path>/**)` in
`permissions.deny` stops the sandboxed shell and the file tools, and one leading slash stops
nothing outside the working directory. Every file is under `tmp_path`, the managed one included
(`tests/conftest.py` points the managed-settings path there for every test).
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

import stayfixed
from stayfixed.config.loader import CONFIG_FILE
from stayfixed.doctor import boundary
from stayfixed.doctor.api import OK, RED, SKIP, WARN, Check
from stayfixed.doctor.checks import run_checks
from stayfixed.harnesses import CLAUDE
from stayfixed.trust.api import approve, managed_settings
from tests.runners import Recorder

T0 = datetime(2026, 10, 16, 9, 30, tzinfo=UTC)

# The settings, as measured on Claude Code 2.1.296.
SANDBOX_ON: dict[str, Any] = {"sandbox": {"enabled": True}}
SANDBOX_OFF: dict[str, Any] = {"sandbox": {"enabled": False}}
ADMIN_REQUIRED: dict[str, Any] = {"sandbox": {"enabled": True, "allowUnsandboxedCommands": False}}
USER_NO_RETRY: dict[str, Any] = {"sandbox": {"enabled": True, "allowUnsandboxedCommands": False}}
MANAGED_NO_RETRY: dict[str, Any] = {"sandbox": {"allowUnsandboxedCommands": False}}


def _deny(*rules: str) -> dict[str, Any]:
    return {"permissions": {"deny": list(rules)}}


def _rule(directory: Path) -> str:
    """The measured spelling: `Edit(//` and the absolute path without its own leading slash."""
    return "Edit(/" + str(directory) + "/**)"


def _merged(*documents: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for document in documents:
        for key, value in document.items():
            out[key] = {**out.get(key, {}), **value}
    return out


def _write(path: Path, document: dict[str, Any] | str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = document if isinstance(document, str) else json.dumps(document)
    path.write_text(text, encoding="utf-8")


class Machine:
    """One machine and one project, every file under `tmp_path`."""

    def __init__(self, tmp_path: Path) -> None:
        self.tmp = tmp_path
        self.home = tmp_path / "home"
        self.root = tmp_path / "project"
        self.root.mkdir(parents=True, exist_ok=True)
        self.machine = tmp_path / "machine" / "config.toml"
        self.machine.parent.mkdir(parents=True, exist_ok=True)
        (self.home / ".claude").mkdir(parents=True, exist_ok=True)
        self.env: dict[str, str] = {"PATH": os.environ.get("PATH", ""), "HOME": str(self.home)}

    @property
    def record_directory(self) -> Path:
        return self.machine.parent

    def user(self, document: dict[str, Any] | str) -> None:
        _write(self.home / ".claude" / "settings.json", document)

    def project(self, document: dict[str, Any] | str) -> None:
        (relative,) = CLAUDE.settings
        _write(self.root / relative, document)

    def local(self, document: dict[str, Any] | str) -> None:
        (relative,) = CLAUDE.local_settings
        _write(self.root / relative, document)

    def managed(self, document: dict[str, Any] | str) -> None:
        path = managed_settings()
        assert path is not None
        _write(path, document)

    def approvals(self, count: int) -> None:
        for n in range(count):
            approve(self.machine, "memory", f"/store/{n}", "d", now=T0)

    def row(self) -> Check:
        rows = run_checks(
            self.root, home=self.home, machine=self.machine, runner=Recorder(), env=self.env
        )
        return next(row for row in rows if row.name == "approval-boundary")


@pytest.fixture
def m(tmp_path: Path) -> Machine:
    return Machine(tmp_path)


def _nothing(m: Machine) -> None:
    pass


def _sandbox_only(m: Machine) -> None:
    m.user(SANDBOX_ON)


def _deny_elsewhere(m: Machine) -> None:
    m.user(_merged(SANDBOX_ON, _deny(_rule(m.tmp / "elsewhere"))))


def _deny_one_slash(m: Machine) -> None:
    # Measured to anchor at the working directory and stop nothing outside it.
    m.user(_merged(SANDBOX_ON, _deny(f"Edit({m.record_directory}/**)")))


def _sandbox_and_deny(m: Machine) -> None:
    m.user(_merged(SANDBOX_ON, _deny(_rule(m.record_directory))))


def _user_forbids_retry(m: Machine) -> None:
    m.user(_merged(USER_NO_RETRY, _deny(_rule(m.record_directory))))


def _admin_required(m: Machine) -> None:
    m.user(_deny(_rule(m.record_directory)))
    m.managed(ADMIN_REQUIRED)


def _project_disables(m: Machine) -> None:
    _sandbox_and_deny(m)
    m.project(SANDBOX_OFF)


def _local_disables(m: Machine) -> None:
    _user_forbids_retry(m)
    m.local(SANDBOX_OFF)


def _project_disables_under_admin(m: Machine) -> None:
    # The measured case: the user turns the sandbox on, managed settings say only
    # `allowUnsandboxedCommands = false`, and the project's `false` is ignored.
    m.user(_merged(SANDBOX_ON, _deny(_rule(m.record_directory))))
    m.managed(MANAGED_NO_RETRY)
    m.project(SANDBOX_OFF)


def _admin_by_drop_in(m: Machine) -> None:
    m.user(_merged(SANDBOX_ON, _deny(_rule(m.record_directory))))
    path = managed_settings()
    assert path is not None
    _write(path.parent / "managed-settings.d" / "10-sandbox.json", ADMIN_REQUIRED)


def _deny_in_the_local_file(m: Machine) -> None:
    m.user(SANDBOX_ON)
    m.managed(ADMIN_REQUIRED)
    m.local(_deny(_rule(m.record_directory)))


@pytest.mark.parametrize(
    ("settings", "approvals", "expected"),
    [
        pytest.param(_nothing, 0, WARN, id="nothing-no-approval"),
        pytest.param(_nothing, 1, RED, id="nothing"),
        pytest.param(_sandbox_only, 1, RED, id="sandbox-only"),
        pytest.param(_deny_elsewhere, 1, RED, id="deny-elsewhere"),
        pytest.param(_deny_one_slash, 1, RED, id="deny-one-slash"),
        pytest.param(_sandbox_and_deny, 1, WARN, id="sandbox-and-deny"),
        pytest.param(_user_forbids_retry, 1, WARN, id="user-forbids-retry"),
        pytest.param(_admin_required, 1, OK, id="admin-required"),
        pytest.param(_admin_by_drop_in, 1, OK, id="admin-by-drop-in"),
        pytest.param(_deny_in_the_local_file, 1, OK, id="deny-in-the-local-file"),
        pytest.param(_project_disables, 1, RED, id="project-disables"),
        pytest.param(_project_disables, 0, WARN, id="project-disables-no-approval"),
        pytest.param(_local_disables, 1, RED, id="local-disables"),
        pytest.param(_project_disables_under_admin, 1, OK, id="project-disables-under-admin"),
    ],
)
def test_the_boundary_row(m: Machine, settings: Any, approvals: int, expected: str) -> None:
    # Red only once the machine holds an approval, and only for a gap a session of this project
    # has: no sandbox in force, or no deny rule over the record's directory. With both, a warning
    # until managed settings make the sandbox admin-required, since a repository's file can turn it
    # off and a user's own setting does not stop that. Mutations (`mutations/`'s "the boundary row
    # passes without the deny rule" -> `nothing`, `sandbox-only`, `deny-elsewhere` and
    # `deny-one-slash` read green or warn; "the boundary row ignores a project file that turns the
    # sandbox off" -> `project-disables` and `local-disables` warn; "the boundary row lets a
    # repository's false win over managed settings" -> `project-disables-under-admin` is red; "the
    # boundary row takes a user's allowUnsandboxedCommands for admin-required" ->
    # `user-forbids-retry` is ok; "the boundary row is red with no approval" -> the two
    # no-approval cases are red; "the boundary row reads no managed drop-in" -> `admin-by-drop-in`
    # warns).
    settings(m)
    m.approvals(approvals)
    row = m.row()
    assert row.status == expected, row


def test_a_gap_names_the_missing_setting_and_what_it_stops(m: Machine) -> None:
    # Every gap is said in its own sentence, each naming the setting and what it stops, and the
    # remedy is the command that adds the rule and prints the sandbox settings. Mutation
    # (`mutations/`'s "the boundary row names no gap"): the detail carries only the count.
    m.approvals(2)
    row = m.row()
    assert row.detail == "; ".join(
        (
            boundary.HELD.format(count=2),
            boundary.NO_SANDBOX,
            boundary.NO_DENY.format(rule=_rule(m.record_directory)),
        )
    )
    assert row.remedy == boundary.ADD_THE_BOUNDARY


def test_a_project_that_turns_the_sandbox_off_is_named(m: Machine) -> None:
    # The file that won is named, as the label a reader would type. Mutation (`mutations/`'s "the
    # boundary row ignores a project file that turns the sandbox off"): the project's `false` is
    # passed over and no gap is said.
    _sandbox_and_deny(m)
    m.local(SANDBOX_OFF)
    m.approvals(1)
    (local,) = CLAUDE.local_settings
    assert m.row().detail == "; ".join(
        (boundary.HELD.format(count=1), boundary.TURNED_OFF.format(label=local))
    )


def test_a_boundary_that_is_not_admin_required_says_where_to_make_it_so(m: Machine) -> None:
    # The warning names the managed-settings file and the two keys, and says what they stop.
    # Mutation (`mutations/`'s "the boundary row takes a user's allowUnsandboxedCommands for
    # admin-required"): the row reads ok and names nothing.
    _user_forbids_retry(m)
    m.approvals(1)
    row = m.row()
    managed = managed_settings()
    assert row.detail == "; ".join((boundary.HELD.format(count=1), boundary.NOT_ADMIN))
    assert row.remedy == boundary.MAKE_IT_ADMIN.format(managed=managed)
    for said in (
        "sandbox.enabled = true",
        "sandbox.allowUnsandboxedCommands = false",
        str(managed),
    ):
        assert said in row.remedy


def test_a_settings_file_that_is_not_json_is_read_as_absent_and_named(m: Machine) -> None:
    # Never a crash, and never red because of it alone: the file is read as absent for its layer,
    # named in the detail, and the row cannot be green beside it, since what Claude Code makes of
    # the file is not known here. Mutations (`mutations/`'s "a settings file that is not JSON ends
    # the boundary row" -> the row is red, its check unable to run; "the boundary row is green
    # beside a settings file it could not read" -> ok).
    _admin_required(m)
    m.project("{ not json")
    m.approvals(1)
    row = m.row()
    (project,) = CLAUDE.settings
    assert row.status == WARN, row
    assert row.detail == "; ".join(
        (
            boundary.HELD.format(count=1),
            boundary.GUARDED.format(rule=_rule(m.record_directory)),
            boundary.NOT_READ.format(label=project),
        )
    )


def test_the_row_skips_without_claude_code(m: Machine) -> None:
    # No user settings directory: Claude Code has never run here under this home, and there is
    # no sandbox or deny rule to read. Mutation (`mutations/`'s "the boundary row asks a machine
    # with no Claude Code"): the row warns instead.
    (m.home / ".claude").rmdir()
    m.approvals(1)
    row = m.row()
    assert (row.status, row.detail, row.remedy) == (SKIP, boundary.NO_CLAUDE_CODE, "")


def test_a_claude_config_dir_alone_is_judged_where_the_home_has_none(m: Machine) -> None:
    # Claude Code reads the user's settings from `CLAUDE_CONFIG_DIR` when it is set, so a home with
    # no `.claude` is not skipped then: the variable's directory is judged, alone, and said as
    # nothing else. Mutation (`mutations/`'s "the user settings directory ignores
    # CLAUDE_CONFIG_DIR"): the row skips.
    (m.home / ".claude").rmdir()
    config = m.tmp / "config-dir"
    _write(config / "settings.json", _merged(ADMIN_REQUIRED, _deny(_rule(m.record_directory))))
    m.env["CLAUDE_CONFIG_DIR"] = str(config)
    m.managed(ADMIN_REQUIRED)
    m.approvals(1)
    row = m.row()
    assert row.status == OK, row
    assert row.detail == "; ".join(
        (boundary.HELD.format(count=1), boundary.GUARDED.format(rule=_rule(m.record_directory)))
    )


@pytest.mark.parametrize("lacking", ["home", "chosen"])
def test_with_claude_config_dir_both_directories_are_judged_and_the_worse_is_said(
    m: Machine, lacking: str
) -> None:
    # Nothing tells whether a person chose `CLAUDE_CONFIG_DIR` or a repository did, through an
    # agent's `env` block or direnv in a person's own terminal, so where it names a directory
    # besides the home's both are judged: a decoy holding every setting does not make the row green
    # while the home's lacks the deny rule (`home`), nor does the home's while the variable's lacks
    # it (`chosen`). The detail says each answer with the file it was judged with. Mutations
    # (`mutations/`'s "the boundary row judges one user settings directory alone" -> `chosen` reads
    # ok and `home` names no file; "the user settings directory ignores CLAUDE_CONFIG_DIR" -> the
    # same for `home`; "the boundary row reports the better of two answers" -> both read ok).
    config = m.tmp / "config-dir"
    good = _merged(ADMIN_REQUIRED, _deny(_rule(m.record_directory)))
    lacks = ADMIN_REQUIRED
    m.user(lacks if lacking == "home" else good)
    _write(config / "settings.json", good if lacking == "home" else lacks)
    m.env["CLAUDE_CONFIG_DIR"] = str(config)
    m.managed(ADMIN_REQUIRED)
    m.approvals(1)
    row = m.row()
    guarded = "; ".join(
        (boundary.HELD.format(count=1), boundary.GUARDED.format(rule=_rule(m.record_directory)))
    )
    gap = "; ".join(
        (
            boundary.HELD.format(count=1),
            boundary.NO_DENY.format(rule=_rule(m.record_directory)),
        )
    )
    said = {
        boundary.USER_LABEL: gap if lacking == "home" else guarded,
        boundary.CHOSEN_LABEL: guarded if lacking == "home" else gap,
    }
    assert row.status == RED, row
    assert row.detail == "; ".join(
        boundary.JUDGED_WITH.format(label=label, detail=detail) for label, detail in said.items()
    )
    assert row.remedy == boundary.ADD_THE_BOUNDARY


def test_a_claude_config_dir_naming_the_home_s_own_is_judged_once(m: Machine) -> None:
    # The variable spelling the home's `.claude` (here with a trailing slash) is one directory,
    # judged once and said plainly. Mutation (`mutations/`'s "the user settings directory takes
    # CLAUDE_CONFIG_DIR spelling the home's own for another"): it is judged twice, each answer said
    # with its file.
    m.user(_merged(ADMIN_REQUIRED, _deny(_rule(m.record_directory))))
    m.env["CLAUDE_CONFIG_DIR"] = str(m.home / ".claude") + "/"
    m.managed(ADMIN_REQUIRED)
    m.approvals(1)
    row = m.row()
    assert row.status == OK, row
    assert not row.detail.startswith("judged with")


def test_the_row_skips_when_the_project_lists_no_claude(m: Machine) -> None:
    # A project whose `[stayfixed] agents` does not list `claude` runs no session the sandbox
    # guards; with no `stayfixed.toml` the preset's agents apply, which do. Mutation
    # (`mutations/`'s "the boundary row asks a project that lists no claude"): the row is red.
    (m.root / CONFIG_FILE).write_text(
        f'[stayfixed]\nversion = "{stayfixed.__version__}"\nstate = "installed"\n'
        'agents = ["codex"]\n\n[project]\nname = "p"\n',
        encoding="utf-8",
    )
    m.approvals(1)
    row = m.row()
    assert (row.status, row.detail, row.remedy) == (SKIP, boundary.NOT_LISTED, "")
    (m.root / CONFIG_FILE).unlink()
    assert m.row().status == RED


def test_an_unreadable_trust_record_is_taken_to_hold_approvals(m: Machine) -> None:
    # The record holds every project's approval on the machine, so one that cannot be read is not
    # read as holding none: a gap is red beside it. Mutation (`mutations/`'s "the boundary row
    # reads an unreadable trust record as empty"): the row warns.
    (m.record_directory / "trust.json").write_text("{ not json", encoding="utf-8")
    row = m.row()
    assert row.status == RED, row
    assert row.detail.startswith(boundary.RECORD_UNREAD + "; ")


@pytest.mark.parametrize(
    ("spelled", "missing"),
    [
        pytest.param(("named", "resolved"), None, id="both"),
        pytest.param(("resolved",), "named", id="resolved-only"),
        pytest.param(("named",), "resolved", id="named-only"),
    ],
)
def test_a_linked_record_directory_is_covered_only_by_both_rules_setup_writes(
    m: Machine, tmp_path: Path, spelled: tuple[str, ...], missing: str | None
) -> None:
    # Through a link the record's directory has two spellings, and `setup` writes a rule over each:
    # the harness compares a write against the path it resolves, and a tool call may carry the path
    # as named. The row counts the directory covered only while both stand, and names the one
    # missing. `both` is the positive control, without which a row that never saw a rule at all
    # would pass the other two. Mutations (`mutations/`'s "the boundary row takes a rule over the
    # directory as named for one over where it leads" -> `named-only` is ok; "the boundary row
    # counts the rule over where the directory leads alone" -> `resolved-only` is ok).
    real = tmp_path / "real-machine"
    real.mkdir()
    linked = tmp_path / "linked-machine"
    linked.symlink_to(real)
    m.machine = linked / "config.toml"
    rules = {"named": _rule(linked), "resolved": _rule(real.resolve())}
    m.user(_deny(*(rules[name] for name in spelled)))
    m.managed(ADMIN_REQUIRED)
    m.approvals(1)
    row = m.row()
    if missing is None:
        assert row.status == OK, row
    else:
        assert row.status == RED, row
        assert row.detail == "; ".join(
            (boundary.HELD.format(count=1), boundary.NO_DENY.format(rule=rules[missing]))
        )


@pytest.mark.parametrize(
    "spelling",
    [
        pytest.param(lambda d: f"Edit(/{d}/./**)", id="dot-component"),
        pytest.param(lambda d: f"Edit(/{d}//**)", id="doubled-slash"),
        pytest.param(lambda d: f"Edit(/{d}/x/../**)", id="parent-component"),
        pytest.param(lambda d: f"Edit(/{str(d).swapcase()}/**)", id="case-variant"),
        pytest.param(lambda d: f"Edit( /{d}/**)", id="leading-space"),
    ],
)
def test_a_deny_rule_in_any_spelling_but_setup_s_is_not_counted(
    m: Machine, monkeypatch: pytest.MonkeyPatch, spelling: Any
) -> None:
    # Only the rule as `setup` writes it, byte for byte, covers the record's directory: another
    # spelling of the same directory is one the harness may read otherwise, and the row does not
    # normalise a settings file's text to make it match. Case folding, which the row applies to
    # widening entries on macOS, is on here too and still does not count a case variant. Mutation
    # (`mutations/`'s "the boundary row counts a deny rule by its normalised spelling"): the
    # dot, doubled-slash, parent and case spellings read ok.
    monkeypatch.setattr(boundary, "CASE_FOLDS", True)
    m.user(_deny(spelling(m.record_directory)))
    m.managed(ADMIN_REQUIRED)
    m.approvals(1)
    row = m.row()
    assert row.status == RED, row
    assert row.detail == "; ".join(
        (boundary.HELD.format(count=1), boundary.NO_DENY.format(rule=_rule(m.record_directory)))
    )


@pytest.mark.parametrize(
    ("managed", "user_turns_it_on", "expected"),
    [
        pytest.param(MANAGED_NO_RETRY, True, OK, id="owner-true"),
        pytest.param(MANAGED_NO_RETRY, False, RED, id="owner-silent"),
        pytest.param(ADMIN_REQUIRED, False, OK, id="managed-true"),
    ],
)
def test_while_admin_required_a_repository_false_gives_way_only_to_an_owners_true(
    m: Machine, managed: dict[str, Any], user_turns_it_on: bool, expected: str
) -> None:
    # Admin-required, a repository's `sandbox.enabled = false` is ignored where managed settings
    # or the user's file set `true` (Claude Code's sandboxing reference); with no `true` from
    # either, it stands, and is named. Mutation (`mutations/`'s "while admin-required a
    # repository's false gives way to nothing at all"): `owner-silent` says no file turns the
    # sandbox on, instead of naming the project's `false`.
    m.managed(managed)
    m.user(_merged(SANDBOX_ON if user_turns_it_on else {}, _deny(_rule(m.record_directory))))
    m.project(SANDBOX_OFF)
    m.approvals(1)
    row = m.row()
    assert row.status == expected, row
    if expected == RED:
        (project,) = CLAUDE.settings
        assert row.detail == "; ".join(
            (boundary.HELD.format(count=1), boundary.TURNED_OFF.format(label=project))
        )


# What widens confinement. The keys are the sandboxing reference's; an entry is read as text, and is
# safe only when it is a literal path, of the allowed characters with no `.`, `..` or empty
# component, anchored outside the working directory as its key anchors it, outside the project,
# and neither the record's directory, above it, nor inside it. Every other entry is a gap.
(_PROJECT,) = CLAUDE.settings
(_LOCAL,) = CLAUDE.local_settings
_USER = f"~/{_PROJECT}"
_WRITE = "sandbox.filesystem.allowWrite"
_EDIT = "permissions.allow"
_DIRECTORIES = "permissions.additionalDirectories"


def _allow_write(*entries: str) -> dict[str, Any]:
    return {"sandbox": {"filesystem": {"allowWrite": list(entries)}}}


def _edit(*paths: str) -> dict[str, Any]:
    return {"permissions": {"allow": [f"Edit({path})" for path in paths]}}


def _directories(*entries: str) -> dict[str, Any]:
    return {"permissions": {"additionalDirectories": list(entries)}}


def _under_config(m: Machine, document: dict[str, Any]) -> dict[str, Any]:
    """`document`, with the machine file, and so the trust record, moved under the home's
    `.config`, where `config.machine` puts it."""
    m.machine = m.home / ".config" / "stayfixed" / "config.toml"
    m.machine.parent.mkdir(parents=True, exist_ok=True)
    return document


def _home_is(m: Machine, home: str, document: dict[str, Any]) -> dict[str, Any]:
    """`document`, with `HOME` in the session's environment set to `home`: Claude Code expands `~`
    from it, while the password database's home and `--home` stay as they were."""
    m.env["HOME"] = home
    return document


def _project_in_a_work_tree(m: Machine) -> Path:
    """Move the project one directory down, so a directory holds it and not the record; the
    project's new root."""
    m.root = m.tmp / "work" / "project"
    m.root.mkdir(parents=True)
    return m.root


# (where the entry is written, a callable given the machine that may move its record or project and
# returns the document, whether managed settings make the sandbox admin-required, the status, and
# the gap said or `None` for none). A repository file is read while the sandbox is not
# admin-required, so with no gap it warns that it is not; the user's is read in every case, so
# under admin-required with no gap it is ok.
SAFE = [
    pytest.param("project", lambda m: _allow_write("~/.kube"), False, WARN, None, id="home-kube"),
    pytest.param(
        "project", lambda m: _allow_write("/tmp/build"), False, WARN, None, id="tmp-build"
    ),
    pytest.param("user", lambda m: _allow_write("~/.kube"), True, OK, None, id="user-home-kube"),
    pytest.param("user", lambda m: _directories("/tmp/build"), True, OK, None, id="user-tmp-dir"),
    pytest.param("project", lambda m: _edit("//tmp/build"), False, WARN, None, id="edit-absolute"),
    pytest.param("project", lambda m: _edit("~/.kube"), False, WARN, None, id="edit-home"),
    pytest.param(
        "project", lambda m: _allow_write("~/machine"), False, WARN, None, id="home-machine"
    ),
]


def _gap(
    where: str, document: Any, key: str, admin: bool = False
) -> tuple[str, Any, bool, str, str]:
    """A case whose entry is a gap: red, with the sentence naming `key` in `where`'s file."""
    named = {"project": _PROJECT, "local": _LOCAL, "user": _USER}[where]
    return (where, document, admin, RED, boundary.WIDENED.format(label=named, key=key))


GAPS = [
    pytest.param(*_gap("project", lambda m: _allow_write("//**"), _WRITE), id="double-slash-glob"),
    pytest.param(*_gap("project", lambda m: _allow_write("**"), _WRITE), id="glob"),
    pytest.param(*_gap("project", lambda m: _allow_write("/"), _WRITE), id="root"),
    pytest.param(*_gap("project", lambda m: _allow_write("~"), _WRITE), id="bare-home"),
    pytest.param(*_gap("project", lambda m: _allow_write("~/"), _WRITE), id="home-slash"),
    pytest.param(
        *_gap("project", lambda m: _home_is(m, str(m.tmp), _allow_write("~/machine")), _WRITE),
        id="home-elsewhere",
    ),
    pytest.param(
        *_gap("project", lambda m: _home_is(m, "", _allow_write("~/.kube")), _WRITE),
        id="home-empty",
    ),
    pytest.param(
        *_gap("project", lambda m: _under_config(m, _allow_write("~/.config")), _WRITE),
        id="home-config",
    ),
    pytest.param(
        *_gap("local", lambda m: _allow_write(str(m.record_directory)), _WRITE),
        id="the-record-directory",
    ),
    pytest.param(
        *_gap("project", lambda m: _allow_write(f"{m.record_directory}/trust.json"), _WRITE),
        id="inside-the-directory",
    ),
    pytest.param(
        *_gap("project", lambda m: _directories(str(m.tmp)), _DIRECTORIES),
        id="above-the-directory",
    ),
    pytest.param(
        *_gap("project", lambda m: _allow_write(f"{m.root}/build"), _WRITE),
        id="inside-the-project",
    ),
    pytest.param(
        *_gap(
            "project",
            lambda m: _allow_write(str(_project_in_a_work_tree(m).parent)),
            _WRITE,
        ),
        id="above-the-project",
    ),
    pytest.param(*_gap("project", lambda m: _allow_write("./build"), _WRITE), id="dot-relative"),
    pytest.param(*_gap("project", lambda m: _allow_write("build"), _WRITE), id="relative"),
    pytest.param(
        *_gap("user", lambda m: _allow_write("build"), _WRITE, admin=True), id="user-relative"
    ),
    pytest.param(*_gap("project", lambda m: _edit("/tmp/build"), _EDIT), id="edit-one-slash"),
    pytest.param(*_gap("project", lambda m: _edit("./build"), _EDIT), id="edit-dot-relative"),
    pytest.param(
        *_gap("project", lambda m: _allow_write("//tmp/build"), _WRITE), id="path-two-slashes"
    ),
    pytest.param(*_gap("project", lambda m: _allow_write("/tmp/./build"), _WRITE), id="dot"),
    pytest.param(
        *_gap("project", lambda m: _allow_write("/tmp/x/../build"), _WRITE), id="parent-component"
    ),
    pytest.param(
        *_gap("project", lambda m: _allow_write("/tmp/build/"), _WRITE), id="trailing-slash"
    ),
    pytest.param(*_gap("project", lambda m: _allow_write("/tmp/b\x00"), _WRITE), id="nul"),
    pytest.param(*_gap("project", lambda m: _allow_write("/tmp/x]"), _WRITE), id="bracket"),
    pytest.param(*_gap("project", lambda m: _allow_write("/tmp/x\\"), _WRITE), id="backslash"),
    pytest.param(*_gap("project", lambda m: _allow_write("/tmp/a b"), _WRITE), id="space"),
    pytest.param(
        *_gap("project", lambda m: _allow_write("/tmp/caf" + chr(0xE9)), _WRITE), id="composed"
    ),
    pytest.param(
        *_gap("project", lambda m: _allow_write("/tmp/cafe" + chr(0x301)), _WRITE),
        id="decomposed",
    ),
    pytest.param(
        *_gap("project", lambda m: _allow_write("/" + "*a" * 5000), _WRITE),
        id="ten-thousand-wildcards",
    ),
    pytest.param(*_gap("project", lambda m: _allow_write("/tmp/*"), _WRITE), id="absolute-glob"),
    pytest.param(*_gap("project", lambda m: _edit("//tmp/**"), _EDIT), id="edit-glob"),
    pytest.param(
        *_gap("project", lambda m: _allow_write("/tmp/build", "**"), _WRITE),
        id="one-safe-one-not",
    ),
    pytest.param(
        *_gap("user", lambda m: {"permissions": {"allow": ["Edit"]}}, _EDIT, admin=True),
        id="user-bare-edit",
    ),
    pytest.param(
        *_gap("user", lambda m: _directories(str(m.record_directory)), _DIRECTORIES, admin=True),
        id="user-additional-directory",
    ),
    pytest.param(
        *_gap("user", lambda m: _edit("/" + str(m.record_directory)), _EDIT, admin=True),
        id="user-edit-record",
    ),
]

REPOSITORY_SETTINGS = [
    pytest.param(
        "project",
        lambda m: {"sandbox": {"excludedCommands": ["docker"]}},
        False,
        RED,
        boundary.EXCLUDED.format(label=_PROJECT),
        id="excluded-commands",
    ),
    pytest.param(
        "project",
        lambda m: {"sandbox": {"excludedCommands": ["docker"]}},
        True,
        OK,
        None,
        id="excluded-commands-under-admin",
    ),
    pytest.param(
        "local", lambda m: _allow_write("**"), True, OK, None, id="local-allow-write-under-admin"
    ),
]


@pytest.mark.parametrize(
    ("where", "document", "admin", "expected", "said"), [*SAFE, *GAPS, *REPOSITORY_SETTINGS]
)
def test_a_setting_that_widens_confinement_is_a_gap_unless_shown_safe(
    m: Machine, where: str, document: Any, admin: bool, expected: str, said: str | None
) -> None:
    # The sandbox on and the deny rule in place, one approval, and one setting that may widen them.
    # `glob` and `double-slash-glob` are refused by the anchor and component tests before the
    # allowlist is asked, and `bare-home` by the anchor test, so each is held by those mutations.
    # Mutations (`mutations/`'s "the boundary row reads no excludedCommands" ->
    # `excluded-commands`; "the boundary row reads widening repository entries while
    # admin-required" -> the two `-under-admin` cases are red; "the boundary row reads no
    # repository entry that widens" -> the repository gaps but `excluded-commands` go; "the
    # boundary row reads no user entry that widens" -> the `user-` gaps go; "the boundary row
    # takes every entry for a gap" -> the safe cases are red; "the boundary row reads an entry
    # outside the allowlist" -> `nul`, `bracket`, `backslash`, `space`, `composed`, `decomposed`,
    # `ten-thousand-wildcards`, `absolute-glob` and `edit-glob` go; "the boundary row lets a dot,
    # parent or empty component through" -> `dot`, `parent-component`, `trailing-slash`,
    # `path-two-slashes`, `home-slash` and `root` go; "the boundary row anchors an Edit rule's
    # single slash at the root" -> `edit-one-slash` goes and `edit-absolute` is red; "the
    # boundary row reads a relative entry as absolute" -> `relative`, `dot-relative`,
    # `user-relative`, `edit-dot-relative` and `bare-home` go; "the boundary row takes an entry
    # in the project for one outside it" -> `inside-the-project` and `above-the-project` go; "the
    # boundary row takes an entry that holds the record for one that misses it" -> `home-config`,
    # `above-the-directory` and `above-the-project` go; "the boundary row takes an entry inside
    # the record for one that misses it" -> `inside-the-directory` and `inside-the-project` go;
    # "the boundary row judges a key by one entry" -> `one-safe-one-not` goes; "the boundary row
    # passes a bare Edit" -> `user-bare-edit` goes; "the boundary row reads a ~/ entry under the
    # password database's home alone" -> `home-elsewhere` goes; "the boundary row places a ~/ entry
    # under a HOME that names no directory" -> `home-empty` goes).
    written = document(m)
    base = _merged(SANDBOX_ON, _deny(_rule(m.record_directory)))
    if admin:
        m.managed(ADMIN_REQUIRED)
    if where == "user":
        m.user(_merged(base, written))
    else:
        m.user(base)
        getattr(m, where)(written)
    m.approvals(1)
    row = m.row()
    assert row.status == expected, row
    parts = row.detail.split("; ")
    if said is not None:
        assert said in parts, row.detail
        assert boundary.NARROW_THE_SETTINGS in row.remedy.split("; ")
    else:
        widened = ("holds an entry not shown", "sets sandbox.excludedCommands")
        assert not any(sentence in row.detail for sentence in widened), row.detail


def test_a_widening_gap_with_no_approval_is_a_warning(m: Machine) -> None:
    # As every gap: a warning until the machine holds an approval. Mutation (`mutations/`'s "the
    # boundary row is red with no approval"): red.
    m.user(_merged(SANDBOX_ON, _deny(_rule(m.record_directory))))
    m.project(_allow_write("**"))
    row = m.row()
    assert row.status == WARN, row
    assert row.detail == "; ".join(
        (boundary.NONE_HELD, boundary.WIDENED.format(label=_PROJECT, key=_WRITE))
    )
    assert row.remedy == boundary.NARROW_THE_SETTINGS


def test_with_no_trust_record_directory_no_entry_is_shown_safe(
    m: Machine, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A machine whose password database lists no home, run without `--machine`, has no record
    # directory to compare an entry with, so not even a literal path elsewhere is shown to stay
    # clear of it. Mutation (`mutations/`'s "the boundary row shows an entry safe with no record
    # directory to compare"): the entry is shown safe and only the deny rule's gap is said.
    monkeypatch.setattr(boundary, "record_path", lambda machine: None)
    m.user(SANDBOX_ON)
    m.project(_allow_write("/tmp/build"))
    row = m.row()
    assert row.status == WARN, row
    assert row.detail == "; ".join(
        (
            boundary.NONE_HELD,
            boundary.NO_DENY.format(rule=boundary.NO_RECORD_RULE),
            boundary.WIDENED.format(label=_PROJECT, key=_WRITE),
        )
    )


@pytest.mark.parametrize("carried", ["project", "local"])
def test_a_project_carrying_claude_code_settings_is_read_whatever_it_lists(
    m: Machine, carried: str
) -> None:
    # `[stayfixed] agents` is the repository's to write, so a project that lists no `claude` and
    # ships a Claude Code settings file is read all the same: listing `codex` alone must not be a
    # way to silence the row. Mutation (`mutations/`'s "the boundary row skips a project that ships
    # Claude Code settings for the agents it lists"): the row skips.
    (m.root / CONFIG_FILE).write_text(
        f'[stayfixed]\nversion = "{stayfixed.__version__}"\nstate = "installed"\n'
        'agents = ["codex"]\n\n[project]\nname = "p"\n',
        encoding="utf-8",
    )
    getattr(m, carried)({})
    m.approvals(1)
    assert m.row().status == RED


def test_an_entry_is_read_without_asking_the_filesystem(
    m: Machine, monkeypatch: pytest.MonkeyPatch
) -> None:
    # An entry under an automounted root -- `/net`, `/Network`, `/Volumes` -- can hang a `stat` or
    # reach the network, so the row asks nothing of the filesystem about an entry: these are read
    # as text, the one literal path outside the project and the record shown safe and the other a
    # gap. The stand-in calls refuse any path under `/net` rather than let one reach the machine.
    # Mutation (`mutations/`'s "the boundary row asks the filesystem about an entry"): the check
    # stats `/net`, and the row turns red, unable to run.
    asked: list[str] = []
    for name in ("stat", "lstat"):
        real = getattr(os, name)

        def refusing(path: Any, *args: Any, _real: Any = real, **kwargs: Any) -> Any:
            if str(path).startswith("/net"):
                asked.append(str(path))
                raise AssertionError(f"asked the filesystem about {path}")
            return _real(path, *args, **kwargs)

        monkeypatch.setattr(os, name, refusing)
    m.user(_merged(SANDBOX_ON, _deny(_rule(m.record_directory))))
    m.project(_merged(_allow_write("/net/host/share"), _directories("/net/host/x/../share")))
    m.approvals(1)
    row = m.row()
    monkeypatch.undo()
    assert asked == []
    assert row.status == RED, row
    assert row.detail.split("; ")[1:] == [boundary.WIDENED.format(label=_PROJECT, key=_DIRECTORIES)]


def test_a_case_variant_names_the_record_on_a_volume_that_folds_case(
    m: Machine, monkeypatch: pytest.MonkeyPatch
) -> None:
    # On macOS's default volume two spellings that differ in case are one directory, so a variant
    # of the record's directory reaches it. Mutation (`mutations/`'s "the boundary row compares
    # paths by their case where the volume folds it"): the entry is shown safe and the row only
    # warns.
    monkeypatch.setattr(boundary, "CASE_FOLDS", True)
    m.user(_merged(SANDBOX_ON, _deny(_rule(m.record_directory))))
    m.project(_allow_write(str(m.record_directory).swapcase()))
    m.approvals(1)
    row = m.row()
    assert row.status == RED, row
    assert boundary.WIDENED.format(label=_PROJECT, key=_WRITE) in row.detail.split("; ")


def test_composed_and_decomposed_spellings_compare_alike_where_names_fold(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # macOS hands back a name decomposed or composed, so the record's two spellings and an entry
    # compare in NFC there. Mutation (`mutations/`'s "the boundary row compares names composed
    # and decomposed as different"): the two spellings differ.
    monkeypatch.setattr(boundary, "CASE_FOLDS", True)
    assert boundary._folded("/Users/José") == boundary._folded("/Users/José")
    monkeypatch.setattr(boundary, "CASE_FOLDS", False)
    assert boundary._folded("/Users/José") != boundary._folded("/Users/José")


def test_the_row_runs_no_regular_expression_on_what_a_settings_file_holds() -> None:
    # A repository chooses what its settings files hold, and a pattern of its choosing compiled to
    # a backtracking expression is a way to hang `doctor`; so the module imports no `re` at all.
    # Mutation (`mutations/`'s "the boundary row imports re again"): the import is found.
    import ast

    tree = ast.parse(Path(boundary.__file__).read_text(encoding="utf-8"))
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    assert "re" not in imported
