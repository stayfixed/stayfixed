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


def test_the_user_settings_directory_follows_claude_config_dir(m: Machine) -> None:
    # Claude Code reads the user's settings from `CLAUDE_CONFIG_DIR` when it is set, and so does
    # the row: a home with no `.claude` is not skipped then. Mutation (`mutations/`'s "the
    # boundary row ignores CLAUDE_CONFIG_DIR"): the row skips.
    (m.home / ".claude").rmdir()
    config = m.tmp / "config-dir"
    _write(config / "settings.json", _merged(ADMIN_REQUIRED, _deny(_rule(m.record_directory))))
    m.env["CLAUDE_CONFIG_DIR"] = str(config)
    m.managed(ADMIN_REQUIRED)
    m.approvals(1)
    assert m.row().status == OK


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


def test_a_deny_rule_over_the_resolved_directory_counts(m: Machine, tmp_path: Path) -> None:
    # The record's directory reached through a link: a rule spelled over where it leads covers it.
    # No mutation of its own: it is the positive control for the case below, without which a row
    # that never saw a rule at all would pass that one.
    real = tmp_path / "real-machine"
    real.mkdir()
    linked = tmp_path / "linked-machine"
    linked.symlink_to(real)
    m.machine = linked / "config.toml"
    m.user(_deny(_rule(real.resolve())))
    m.managed(ADMIN_REQUIRED)
    m.approvals(1)
    assert m.row().status == OK


def test_a_deny_rule_over_the_directory_as_named_is_not_enough(m: Machine, tmp_path: Path) -> None:
    # The harness compares a write against the path it resolves, so a rule over the link's
    # spelling alone denies nothing there; the gap names the rule over where it leads. Mutation
    # (`mutations/`'s "the boundary row takes a rule over the directory as named for one over where
    # it leads"): the row reads ok.
    real = tmp_path / "real-machine"
    real.mkdir()
    linked = tmp_path / "linked-machine"
    linked.symlink_to(real)
    m.machine = linked / "config.toml"
    m.user(_deny(_rule(linked)))
    m.managed(ADMIN_REQUIRED)
    m.approvals(1)
    row = m.row()
    assert row.status == RED, row
    assert row.detail == "; ".join(
        (boundary.HELD.format(count=1), boundary.NO_DENY.format(rule=_rule(real.resolve())))
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


def _directory(m: Machine) -> str:
    return str(m.record_directory)


# What widens confinement: (the file, its document given the machine, whether managed settings make
# the sandbox admin-required, the approvals, the status, and the gap said or `None`). The keys are
# the sandboxing reference's.
(_PROJECT,) = CLAUDE.settings
(_LOCAL,) = CLAUDE.local_settings
_USER = f"~/{_PROJECT}"
WIDENING = [
    pytest.param(
        "project",
        lambda m: {"sandbox": {"excludedCommands": ["docker"]}},
        False,
        1,
        RED,
        boundary.EXCLUDED.format(label=_PROJECT),
        id="excluded-commands",
    ),
    pytest.param(
        "project",
        lambda m: {"sandbox": {"excludedCommands": ["docker"]}},
        False,
        0,
        WARN,
        boundary.EXCLUDED.format(label=_PROJECT),
        id="excluded-commands-no-approval",
    ),
    pytest.param(
        "project",
        lambda m: {"sandbox": {"excludedCommands": ["docker"]}},
        True,
        1,
        OK,
        None,
        id="excluded-commands-under-admin",
    ),
    pytest.param(
        "local",
        lambda m: {"sandbox": {"filesystem": {"allowWrite": [_directory(m)]}}},
        False,
        1,
        RED,
        boundary.WIDENED.format(label=_LOCAL, key="sandbox.filesystem.allowWrite"),
        id="local-allow-write",
    ),
    pytest.param(
        "local",
        lambda m: {"sandbox": {"filesystem": {"allowWrite": [_directory(m)]}}},
        True,
        1,
        OK,
        None,
        id="local-allow-write-under-admin",
    ),
    pytest.param(
        "project",
        lambda m: {"permissions": {"allow": [f"Edit(/{_directory(m)})"]}},
        False,
        1,
        RED,
        boundary.WIDENED.format(label=_PROJECT, key="permissions.allow"),
        id="project-edit-allow",
    ),
    pytest.param(
        "project",
        lambda m: {"permissions": {"additionalDirectories": [str(m.tmp)]}},
        False,
        1,
        RED,
        boundary.WIDENED.format(label=_PROJECT, key="permissions.additionalDirectories"),
        id="project-additional-directory-above",
    ),
    pytest.param(
        "user",
        lambda m: {"sandbox": {"filesystem": {"allowWrite": [_directory(m)]}}},
        True,
        1,
        RED,
        boundary.WIDENED.format(label=_USER, key="sandbox.filesystem.allowWrite"),
        id="user-allow-write-under-admin",
    ),
    pytest.param(
        "user",
        lambda m: {"permissions": {"allow": ["Edit"]}},
        True,
        1,
        RED,
        boundary.WIDENED.format(label=_USER, key="permissions.allow"),
        id="user-bare-edit",
    ),
    pytest.param(
        "user",
        lambda m: {"permissions": {"allow": [f"Edit(/{m.tmp}/**)"]}},
        True,
        1,
        RED,
        boundary.UNJUDGED.format(label=_USER, key="permissions.allow"),
        id="user-edit-glob",
    ),
    pytest.param(
        "user",
        lambda m: {"permissions": {"additionalDirectories": [_directory(m)]}},
        True,
        1,
        RED,
        boundary.WIDENED.format(label=_USER, key="permissions.additionalDirectories"),
        id="user-additional-directory",
    ),
    pytest.param(
        "project",
        lambda m: {"sandbox": {"filesystem": {"allowWrite": ["/elsewhere"]}}},
        False,
        1,
        WARN,
        None,
        id="allow-write-elsewhere",
    ),
    pytest.param(
        "project",
        lambda m: {"permissions": {"allow": ["Edit(src)"]}},
        False,
        1,
        WARN,
        None,
        id="edit-allow-in-the-project",
    ),
    pytest.param(
        "project",
        lambda m: {"sandbox": {"filesystem": {"allowWrite": ["/" + "*a" * 5000]}}},
        False,
        1,
        RED,
        boundary.UNJUDGED.format(label=_PROJECT, key="sandbox.filesystem.allowWrite"),
        id="ten-thousand-wildcards",
    ),
    pytest.param(
        "project",
        lambda m: {"sandbox": {"filesystem": {"allowWrite": ["/x/[ab]"]}}},
        False,
        1,
        RED,
        boundary.UNJUDGED.format(label=_PROJECT, key="sandbox.filesystem.allowWrite"),
        id="could-not-tell",
    ),
]


@pytest.mark.parametrize(("where", "document", "admin", "approvals", "expected", "said"), WIDENING)
def test_a_setting_that_widens_confinement_is_a_gap(
    m: Machine,
    where: str,
    document: Any,
    admin: bool,
    approvals: int,
    expected: str,
    said: str | None,
) -> None:
    # The sandbox on and the deny rule in place, and one setting that widens them: a repository's
    # `excludedCommands`, or an entry that reaches the record's directory, counts while the sandbox
    # is not admin-required (Claude Code ignores those repository entries while it is), and the
    # user's counts always, since it undoes the deny rule. An entry this row cannot judge is a gap
    # said as such. Mutations (`mutations/`'s "the boundary row reads no excludedCommands" -> the
    # two `excluded-commands` gaps go; "the boundary row reads no repository entry that widens" ->
    # `local-allow-write`, `project-edit-allow` and `project-additional-directory-above` go; "the
    # boundary row reads no user entry that widens" -> the four `user-` cases go; "the boundary row
    # reads widening repository entries while admin-required" -> the two `-under-admin` cases are
    # red; "the boundary row takes an entry it cannot judge for one that reaches nothing" ->
    # `could-not-tell`, `ten-thousand-wildcards` and `user-edit-glob` warn or name no gap; "the
    # boundary row reads a pattern as a literal path" -> `could-not-tell` and `user-edit-glob` name
    # no gap; "the boundary row takes every literal entry for one that reaches the record" ->
    # `allow-write-elsewhere` and `edit-allow-in-the-project` are red; "the boundary row takes an
    # entry that holds the record for one that misses it" -> `project-additional-directory-above`
    # names no gap).
    base = _merged(SANDBOX_ON, _deny(_rule(m.record_directory)))
    if admin:
        m.managed(ADMIN_REQUIRED)
    written = document(m)
    if where == "user":
        m.user(_merged(base, written))
    else:
        m.user(base)
        getattr(m, where)(written)
    m.approvals(approvals)
    row = m.row()
    assert row.status == expected, row
    if said is not None:
        assert said in row.detail.split("; "), row.detail
    else:
        assert not any(
            part.startswith((_PROJECT, _LOCAL, _USER)) for part in row.detail.split("; ")
        ), row.detail


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


def _linked_beside(m: Machine, name: str, to: Path) -> Path:
    """A symbolic link outside every directory above the record's, leading to `to`."""
    other = m.tmp / "other"
    other.mkdir(exist_ok=True)
    link = other / name
    link.symlink_to(to)
    return link


def _widening_gap(m: Machine, entry: str) -> Check:
    m.user(_merged(SANDBOX_ON, _deny(_rule(m.record_directory))))
    m.project({"sandbox": {"filesystem": {"allowWrite": [entry]}}})
    m.approvals(1)
    return m.row()


@pytest.fixture
def deep(tmp_path: Path) -> Machine:
    """A machine whose record lies two directories down, so a sibling tree holds no ancestor of
    it."""
    machine = Machine(tmp_path)
    machine.machine = tmp_path / "m" / "machine" / "config.toml"
    machine.machine.parent.mkdir(parents=True)
    return machine


def test_a_parent_component_is_a_gap_it_could_not_tell_about(deep: Machine) -> None:
    # `link/..` normalises, as text, to the directory the link sits in, which holds nothing of the
    # record's; the harness, following the link first, reaches the record. So an entry with a `..`
    # component is never judged. Mutation (`mutations/`'s "the boundary row lets a parent
    # component through"): the entry reads as missing the record and the row names no gap.
    inner = deep.record_directory / "inner"
    inner.mkdir()
    link = _linked_beside(deep, "l", inner)
    row = _widening_gap(deep, f"{link}/..")
    assert row.status == RED, row
    assert boundary.UNJUDGED.format(label=_PROJECT, key="sandbox.filesystem.allowWrite") in (
        row.detail.split("; ")
    )


def test_a_literal_path_through_a_link_is_judged_where_it_leads(deep: Machine) -> None:
    # A literal entry whose prefix is a link to a directory above the record reaches it, which the
    # entry's own spelling does not say. Mutation (`mutations/`'s "the boundary row judges an entry
    # by its spelling and not where it leads"): the row names no gap.
    link = _linked_beside(deep, "l2", deep.record_directory.parent)
    row = _widening_gap(deep, str(link))
    assert row.status == RED, row
    assert boundary.WIDENED.format(label=_PROJECT, key="sandbox.filesystem.allowWrite") in (
        row.detail.split("; ")
    )


def test_a_case_variant_names_the_record_on_a_volume_that_folds_case(
    m: Machine, monkeypatch: pytest.MonkeyPatch
) -> None:
    # On macOS's default volume two spellings that differ in case are one directory, so a variant
    # of the record's directory reaches it. Mutation (`mutations/`'s "the boundary row compares
    # paths by their case where the volume folds it"): the row names no gap.
    monkeypatch.setattr(boundary, "CASE_FOLDS", True)
    row = _widening_gap(m, str(m.record_directory).swapcase())
    assert row.status == RED, row
    assert boundary.WIDENED.format(label=_PROJECT, key="sandbox.filesystem.allowWrite") in (
        row.detail.split("; ")
    )


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
