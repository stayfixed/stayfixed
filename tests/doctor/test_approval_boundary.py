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
from stayfixed import fsops
from stayfixed.config.loader import CONFIG_FILE
from stayfixed.doctor import boundary
from stayfixed.doctor.api import OK, RED, SKIP, WARN, Check
from stayfixed.doctor.checks import run_checks
from stayfixed.harnesses import CLAUDE
from stayfixed.printed import clipped
from stayfixed.trust import boundary as trust_boundary
from stayfixed.trust.api import approve, managed_settings
from tests.gitfixture import git
from tests.runners import Recorder

T0 = datetime(2026, 10, 16, 9, 30, tzinfo=UTC)

# The settings, as measured on Claude Code 2.1.296.
SANDBOX_ON: dict[str, Any] = {"sandbox": {"enabled": True}}
SANDBOX_OFF: dict[str, Any] = {"sandbox": {"enabled": False}}
ADMIN_REQUIRED: dict[str, Any] = {"sandbox": {"enabled": True, "allowUnsandboxedCommands": False}}
USER_NO_RETRY: dict[str, Any] = {"sandbox": {"enabled": True, "allowUnsandboxedCommands": False}}
MANAGED_NO_RETRY: dict[str, Any] = {"sandbox": {"allowUnsandboxedCommands": False}}
# Claude Code's sandboxing reference's recipe for enforcing the sandbox from managed settings (not
# measured here): admin-required, and refusing to start where the sandbox cannot. Only with
# `failIfUnavailable` there may the row be green.
ENFORCED: dict[str, Any] = {
    "sandbox": {"enabled": True, "failIfUnavailable": True, "allowUnsandboxedCommands": False}
}
MANAGED_NO_RETRY_ENFORCED: dict[str, Any] = {
    "sandbox": {"allowUnsandboxedCommands": False, "failIfUnavailable": True}
}


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
    m.managed(ENFORCED)


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
    m.managed(MANAGED_NO_RETRY_ENFORCED)
    m.project(SANDBOX_OFF)


def _admin_by_drop_in(m: Machine) -> None:
    m.user(_merged(SANDBOX_ON, _deny(_rule(m.record_directory))))
    path = managed_settings()
    assert path is not None
    _write(path.parent / "managed-settings.d" / "10-sandbox.json", ENFORCED)


def _deny_in_the_local_file(m: Machine) -> None:
    m.user(SANDBOX_ON)
    m.managed(ENFORCED)
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
        pytest.param(_deny_in_the_local_file, 1, WARN, id="deny-in-the-local-file"),
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
    # The warning names the managed-settings file and the three keys of the reference's recipe,
    # and says what they stop. Mutation (`mutations/`'s "the boundary row takes a user's
    # allowUnsandboxedCommands for admin-required"): the row says nothing of admin-required.
    _user_forbids_retry(m)
    m.approvals(1)
    row = m.row()
    managed = managed_settings()
    assert row.status == WARN, row
    assert row.detail == "; ".join(
        (
            boundary.HELD.format(count=1),
            boundary.NOT_ADMIN,
            boundary.NO_FAIL_CLOSED.format(managed=managed),
        )
    )
    assert row.remedy == boundary.MAKE_IT_ADMIN.format(managed=managed)
    for said in (
        "sandbox.enabled = true",
        "sandbox.failIfUnavailable = true",
        "sandbox.allowUnsandboxedCommands = false",
        str(managed),
    ):
        assert said in row.remedy


@pytest.mark.parametrize(
    ("managed", "expected"),
    [
        pytest.param(ADMIN_REQUIRED, WARN, id="admin-required-only"),
        pytest.param(
            _merged(ADMIN_REQUIRED, {"sandbox": {"failIfUnavailable": False}}),
            WARN,
            id="fail-if-unavailable-false",
        ),
        pytest.param(ENFORCED, OK, id="enforced"),
    ],
)
def test_green_needs_managed_settings_to_refuse_a_sandbox_that_cannot_start(
    m: Machine, managed: dict[str, Any], expected: str
) -> None:
    # Admin-required is not yet enforced: where the sandbox cannot start, Claude Code runs commands
    # outside it unless managed settings set `sandbox.failIfUnavailable = true`, the sandboxing
    # reference's recipe. The warning names the key and the managed file; the user's own `true`
    # does not count. Mutations (`mutations/`'s "the boundary row is green without
    # failIfUnavailable" -> `admin-required-only` and `fail-if-unavailable-false` are ok; "the
    # boundary row takes the user's failIfUnavailable for the managed one" -> the same two are ok).
    fail_closed = {"sandbox": {"enabled": True, "failIfUnavailable": True}}
    m.user(_merged(fail_closed, _deny(_rule(m.record_directory))))
    m.managed(managed)
    m.approvals(1)
    row = m.row()
    assert row.status == expected, row
    path = managed_settings()
    if expected == WARN:
        assert row.detail == "; ".join(
            (boundary.HELD.format(count=1), boundary.NO_FAIL_CLOSED.format(managed=path))
        )
        assert row.remedy == boundary.MAKE_IT_ADMIN.format(managed=path)
    else:
        guarded = boundary.GUARDED.format(rule=_rule(m.record_directory))
        assert row.detail == "; ".join((boundary.HELD.format(count=1), guarded))


@pytest.mark.parametrize("fault", ["not-json", "not-utf-8", "unreadable"])
def test_a_settings_file_that_is_not_json_is_read_as_absent_and_named(
    m: Machine, fault: str
) -> None:
    # Never a crash, and never red because of it alone: the file is read as absent for its layer,
    # named in the detail with each cause it may have, and the row cannot be green beside it, since
    # what Claude Code makes of the file is not known here. Mutations (`mutations/`'s "a settings
    # file that is not JSON ends the boundary row" -> `not-json` is red, its check unable to run;
    # "the boundary row is green beside a settings file it could not read" -> every case is ok).
    _admin_required(m)
    (project,) = CLAUDE.settings
    m.project("{ not json")
    if fault == "not-utf-8":
        (m.root / project).write_bytes(b'{"sandbox": "\xff"}')
    elif fault == "unreadable":
        (m.root / project).chmod(0)
    m.approvals(1)
    try:
        row = m.row()
    finally:
        (m.root / project).chmod(0o644)
    assert row.status == WARN, row
    assert row.detail == "; ".join(
        (
            boundary.HELD.format(count=1),
            boundary.GUARDED.format(rule=_rule(m.record_directory)),
            boundary.NOT_READ.format(label=project),
        )
    )
    assert row.remedy == boundary.MAKE_IT_JSON


def test_the_row_skips_without_claude_code(m: Machine) -> None:
    # No user settings directory: Claude Code has never run here under this home, and there is
    # no sandbox or deny rule to read. Mutation (`mutations/`'s "the boundary row asks a machine
    # with no Claude Code"): the row warns instead.
    (m.home / ".claude").rmdir()
    m.approvals(1)
    row = m.row()
    assert (row.status, row.detail, row.remedy) == (SKIP, boundary.NO_CLAUDE_CODE, "")


@pytest.mark.parametrize(
    ("holds", "expected"),
    [pytest.param("everything", WARN, id="guarded"), pytest.param("no-deny", RED, id="gap")],
)
def test_a_claude_config_dir_alone_is_judged_and_never_above_a_warning(
    m: Machine, holds: str, expected: str
) -> None:
    # With no `.claude` under the home, the directory `CLAUDE_CONFIG_DIR` names is judged alone,
    # and named through `printed.quoted`; since a repository may have chosen it, it never makes the
    # row better than a warning, while a gap in it is red as any gap is. Mutation (`mutations/`'s
    # "the boundary row lets the variable's directory alone make the row green"): `guarded` is ok.
    (m.home / ".claude").rmdir()
    config = m.home / "config-dir"
    deny = _deny(_rule(m.record_directory)) if holds == "everything" else {}
    _write(config / "settings.json", _merged(ADMIN_REQUIRED, deny))
    m.env["CLAUDE_CONFIG_DIR"] = str(config)
    m.managed(ENFORCED)
    m.approvals(1)
    row = m.row()
    answer = (
        boundary.GUARDED.format(rule=_rule(m.record_directory))
        if holds == "everything"
        else boundary.NO_DENY.format(rule=_rule(m.record_directory))
    )
    assert row.status == expected, row
    assert row.detail == "; ".join(
        (
            boundary.HELD.format(count=1),
            answer,
            boundary.CHOSEN_ALONE.format(path=clipped(str(config))),
        )
    )


@pytest.mark.parametrize("lacking", ["home", "chosen"])
def test_the_home_s_directory_is_the_subject_and_claude_config_dir_only_worsens_it(
    m: Machine, lacking: str
) -> None:
    # The home's `.claude` is always judged and is the row's subject; the variable's directory may
    # only add its gaps. A decoy holding every setting does not lift the home's gap (`home`), and
    # the variable's gap is added to a home that holds everything (`chosen`), said with its file.
    # Mutations (`mutations/`'s "the boundary row takes the variable's directory for the home's"
    # -> `home` reads ok; "the boundary row passes the variable's directory's gaps over" ->
    # `chosen` reads ok; "the user settings directory ignores CLAUDE_CONFIG_DIR" -> the same).
    config = m.home / "config-dir"
    good = _merged(ADMIN_REQUIRED, _deny(_rule(m.record_directory)))
    m.user(ADMIN_REQUIRED if lacking == "home" else good)
    _write(config / "settings.json", good if lacking == "home" else ADMIN_REQUIRED)
    m.env["CLAUDE_CONFIG_DIR"] = str(config)
    m.managed(ENFORCED)
    m.approvals(1)
    row = m.row()
    held = boundary.HELD.format(count=1)
    gap = "; ".join((held, boundary.NO_DENY.format(rule=_rule(m.record_directory))))
    guarded = "; ".join((held, boundary.GUARDED.format(rule=_rule(m.record_directory))))
    assert row.status == RED, row
    if lacking == "home":
        assert row.detail == gap
    else:
        assert row.detail == "; ".join(
            (guarded, boundary.JUDGED_WITH.format(label=boundary.CHOSEN_LABEL, detail=gap))
        )
    assert row.remedy == boundary.ADD_THE_BOUNDARY


@pytest.mark.parametrize("home_has_one", [True, False], ids=["home-guarded", "home-has-none"])
def test_a_claude_config_dir_inside_the_project_is_never_judged(
    m: Machine, home_has_one: bool
) -> None:
    # A directory inside the project holds what the repository commits, so it is never judged,
    # only named, and the row is at best a warning for it: a guarded home warns, and a home with no
    # `.claude` warns rather than skipping. Mutations (`mutations/`'s "the boundary row judges a
    # CLAUDE_CONFIG_DIR inside the project" -> `home-guarded` is ok and `home-has-none` reads the
    # repository's settings; "the boundary row is green beside a CLAUDE_CONFIG_DIR inside the
    # project" -> `home-guarded` is ok).
    planted = m.root / ".claude-config"
    _write(planted / "settings.json", _merged(ADMIN_REQUIRED, _deny(_rule(m.record_directory))))
    m.env["CLAUDE_CONFIG_DIR"] = str(planted)
    m.managed(ENFORCED)
    m.approvals(1)
    ignored = boundary.CONFIG_DIR_IN_PROJECT.format(path=clipped(str(planted)))
    if home_has_one:
        m.user(_merged(ADMIN_REQUIRED, _deny(_rule(m.record_directory))))
    else:
        (m.home / ".claude").rmdir()
    row = m.row()
    assert row.status == WARN, row
    if home_has_one:
        guarded = boundary.GUARDED.format(rule=_rule(m.record_directory))
        assert row.detail == "; ".join((boundary.HELD.format(count=1), guarded, ignored))
    else:
        assert row.detail == "; ".join((boundary.NO_CLAUDE_CODE, ignored))


def test_a_claude_config_dir_that_leads_into_the_project_is_inside_it(
    m: Machine, tmp_path: Path
) -> None:
    # A link outside the project leading into it names a directory the repository fills. Mutation
    # (`mutations/`'s "a directory is judged inside the project by its spelling alone"): the
    # planted settings are judged and the row is ok.
    planted = m.root / ".claude-config"
    _write(planted / "settings.json", _merged(ADMIN_REQUIRED, _deny(_rule(m.record_directory))))
    link = m.home / "outside-link"
    link.symlink_to(planted)
    (m.home / ".claude").rmdir()
    m.env["CLAUDE_CONFIG_DIR"] = str(link)
    m.managed(ENFORCED)
    m.approvals(1)
    row = m.row()
    assert (row.status, row.detail) == (
        WARN,
        "; ".join(
            (
                boundary.NO_CLAUDE_CODE,
                boundary.CONFIG_DIR_IN_PROJECT.format(path=clipped(str(link))),
            )
        ),
    )


def test_a_claude_config_dir_spelled_inside_the_project_is_never_followed(
    m: Machine, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A link the repository commits inside the project may lead under an automount root, where one
    # stat stalls `doctor` until the network answers; spelled inside, the directory is inside
    # wherever it leads, so its links are never followed. Mutation (`mutations/`'s "a directory
    # spelled inside the project is followed"): `fsops.resolved` is asked for the link, which
    # leads to settings under the home, and the row judges them.
    real = m.home / "real-config"
    _write(real / "settings.json", _merged(ADMIN_REQUIRED, _deny(_rule(m.record_directory))))
    link = m.root / "committed-link"
    link.symlink_to(real)
    (m.home / ".claude").rmdir()
    m.env["CLAUDE_CONFIG_DIR"] = str(link)
    m.managed(ENFORCED)
    m.approvals(1)
    asked: list[str] = []
    real_resolved = fsops.resolved

    def recording(path: Path) -> Path:
        if str(path).startswith(str(link)):
            asked.append(str(path))
        return real_resolved(path)

    monkeypatch.setattr(fsops, "resolved", recording)
    row = m.row()
    said = boundary.CONFIG_DIR_IN_PROJECT.format(path=clipped(str(link)))
    assert (row.status, row.detail) == (WARN, "; ".join((boundary.NO_CLAUDE_CODE, said)))
    assert asked == []


def test_a_claude_config_dir_whose_links_loop_is_taken_to_be_inside_the_project(
    m: Machine, tmp_path: Path
) -> None:
    # Where the variable's links cannot be followed, where it leads cannot be shown to lie outside
    # the project, so it is treated as inside: named, never judged, and the row a warning. Mutation
    # (`mutations/`'s "a directory whose links loop is read as outside the project"): the row skips.
    loop = m.home / "loop"
    loop.symlink_to(loop)
    (m.home / ".claude").rmdir()
    m.env["CLAUDE_CONFIG_DIR"] = str(loop)
    m.approvals(1)
    row = m.row()
    assert (row.status, row.detail) == (
        WARN,
        "; ".join(
            (
                boundary.NO_CLAUDE_CODE,
                boundary.CONFIG_DIR_IN_PROJECT.format(path=clipped(str(loop))),
            )
        ),
    )


@pytest.mark.parametrize(
    ("suffix", "twice"),
    [pytest.param("", False, id="byte-for-byte"), pytest.param("/", True, id="trailing-slash")],
)
def test_claude_config_dir_is_the_home_s_own_only_when_spelled_alike_to_the_byte(
    m: Machine, suffix: str, twice: bool
) -> None:
    # The same directory only when the variable is the home's `.claude` spelled alike to the byte;
    # any other spelling, a trailing slash included, is judged on its own. A home settings file
    # that is not JSON shows which: it is named once with each label it was judged under.
    # Mutations (`mutations/`'s "the user settings directory takes CLAUDE_CONFIG_DIR spelling the
    # home's own for another" -> `byte-for-byte` is judged twice; "the user settings directory
    # normalises CLAUDE_CONFIG_DIR" -> `trailing-slash` is judged once).
    m.user("{ not json")
    m.local(_deny(_rule(m.record_directory)))
    m.managed(ENFORCED)
    m.env["CLAUDE_CONFIG_DIR"] = str(m.home / ".claude") + suffix
    m.approvals(1)
    row = m.row()
    assert row.status == WARN, row
    assert (boundary.CHOSEN_LABEL in row.detail) is twice, row.detail


@pytest.mark.parametrize(
    ("record", "lead"),
    [
        pytest.param("none", None, id="none"),
        pytest.param("one", boundary.HELD.format(count=1), id="one"),
        pytest.param("unreadable", boundary.RECORD_UNREAD, id="unreadable"),
    ],
)
def test_the_row_skips_a_project_that_lists_no_claude_only_while_no_approval_is_held(
    m: Machine, record: str, lead: str | None
) -> None:
    # A project whose `[stayfixed] agents` does not list `claude` runs no session the sandbox
    # guards, so with no approval on the machine the row skips; with no `stayfixed.toml` the
    # preset's agents apply, which do. The agents list is the repository's to write, so once the
    # record holds an approval, or cannot be read, a later commit listing `codex` alone must not
    # turn a red row into a skip: the row is judged. Mutations (`mutations/`'s "the boundary row
    # asks a project that lists no claude" -> `none` warns; "the boundary row skips a project that
    # lists no claude beside an approval" -> `one` and `unreadable` skip).
    (m.root / CONFIG_FILE).write_text(
        f'[stayfixed]\nversion = "{stayfixed.__version__}"\nstate = "installed"\n'
        'agents = ["codex"]\n\n[project]\nname = "p"\n',
        encoding="utf-8",
    )
    if record == "one":
        m.approvals(1)
    elif record == "unreadable":
        (m.record_directory / "trust.json").write_text("{ not json", encoding="utf-8")
    row = m.row()
    if lead is None:
        assert (row.status, row.detail, row.remedy) == (SKIP, boundary.NOT_LISTED, "")
        (m.root / CONFIG_FILE).unlink()
        assert m.row().status == WARN
    else:
        assert row.status == RED, row
        assert row.detail.startswith(lead + "; "), row.detail


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
    # would pass the other two. Mutations (`mutations/`'s "the approval boundary covers only the
    # directory as named" -> `named-only` is ok; "the boundary row counts the rule over where the
    # directory leads alone" -> `resolved-only` is ok).
    real = tmp_path / "real-machine"
    real.mkdir()
    linked = tmp_path / "linked-machine"
    linked.symlink_to(real)
    m.machine = linked / "config.toml"
    rules = {"named": _rule(linked), "resolved": _rule(real.resolve())}
    m.user(_deny(*(rules[name] for name in spelled)))
    m.managed(ENFORCED)
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
    monkeypatch.setattr(trust_boundary, "CASE_FOLDS", True)
    m.user(_deny(spelling(m.record_directory)))
    m.managed(ENFORCED)
    m.approvals(1)
    row = m.row()
    assert row.status == RED, row
    assert row.detail == "; ".join(
        (boundary.HELD.format(count=1), boundary.NO_DENY.format(rule=_rule(m.record_directory)))
    )


@pytest.mark.parametrize(
    ("managed", "user_turns_it_on", "expected"),
    [
        pytest.param(MANAGED_NO_RETRY_ENFORCED, True, OK, id="owner-true"),
        pytest.param(MANAGED_NO_RETRY_ENFORCED, False, RED, id="owner-silent"),
        pytest.param(ENFORCED, False, OK, id="managed-true"),
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
    # The sandbox's per-user temporary directory itself, and components that only look like it:
    # an entry is a gap only below a `claude-` component of digits. Under `/srv`, so that no
    # temporary directory the suite runs in can hold the entry.
    pytest.param(
        "user", lambda m: _allow_write("/srv/claude-501"), True, OK, None, id="sandbox-temp-itself"
    ),
    pytest.param(
        "user", lambda m: _allow_write("/srv/claude-code/x"), True, OK, None, id="claude-not-digits"
    ),
    pytest.param(
        "user", lambda m: _allow_write("/srv/claude-/x"), True, OK, None, id="claude-dash-alone"
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
    # Below the sandbox's per-user temporary directory, which sandboxed commands write, whatever
    # base `CLAUDE_CODE_TMPDIR` gives it.
    pytest.param(
        *_gap("user", lambda m: _allow_write("/tmp/claude-501/build"), _WRITE, admin=True),
        id="sandbox-temp",
    ),
    pytest.param(
        *_gap("project", lambda m: _edit("//srv/claude-0/x/y"), _EDIT), id="edit-sandbox-temp"
    ),
    pytest.param(
        *_gap("user", lambda m: _directories("~/claude-501/x"), _DIRECTORIES, admin=True),
        id="home-sandbox-temp",
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
    # The sandboxing reference's own example puts `docker compose *` in the user's file, its
    # commands run with no filesystem restriction, and the user's file applies while the sandbox is
    # admin-required: a gap in either case.
    pytest.param(
        "user",
        lambda m: {"sandbox": {"excludedCommands": ["docker compose *"]}},
        False,
        RED,
        boundary.EXCLUDED.format(label=_USER),
        id="user-excluded-commands",
    ),
    pytest.param(
        "user",
        lambda m: {"sandbox": {"excludedCommands": ["docker compose *"]}},
        True,
        RED,
        boundary.EXCLUDED.format(label=_USER),
        id="user-excluded-commands-under-admin",
    ),
    pytest.param(
        "user",
        lambda m: {"sandbox": {"excludedCommands": []}},
        True,
        OK,
        None,
        id="user-excludes-none",
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
    # `excluded-commands` and `user-excluded-commands`; "the boundary row reads widening
    # repository entries while admin-required" -> `excluded-commands-under-admin` and
    # `local-allow-write-under-admin` are red; "the boundary row reads no repository entry that
    # widens" -> the repository gaps but `excluded-commands` go; "the boundary row reads no user
    # entry that widens" -> the `user-` cases of `GAPS` go; "the boundary row
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
    # under a HOME that names no directory" -> `home-empty` goes; "the boundary row reads no user
    # excludedCommands" -> both `user-excluded-commands` cases go; "the boundary row takes an empty
    # excludedCommands for a gap" -> `user-excludes-none` is red; "the boundary row passes an entry
    # under the sandbox's temporary directory" -> `sandbox-temp`, `edit-sandbox-temp` and
    # `home-sandbox-temp` go; "the boundary row reads the sandbox's temporary directory itself as
    # below it" -> `sandbox-temp-itself` is red; "the boundary row takes any claude- component for
    # the sandbox's temporary directory" -> `claude-not-digits` is red; "the boundary row takes a
    # bare claude- component for the sandbox's temporary directory" -> `claude-dash-alone` is red).
    written = document(m)
    base = _merged(SANDBOX_ON, _deny(_rule(m.record_directory)))
    if admin:
        m.managed(ENFORCED)
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


@pytest.mark.parametrize(
    ("where", "document", "said"),
    [
        pytest.param(
            "project",
            _allow_write("**"),
            boundary.WIDENED.format(label=_PROJECT, key=_WRITE),
            id="project-allow-write",
        ),
        pytest.param(
            "user",
            {"sandbox": {"excludedCommands": ["docker compose *"]}},
            boundary.EXCLUDED.format(label=_USER),
            id="user-excluded-commands",
        ),
    ],
)
def test_a_widening_gap_with_no_approval_is_a_warning(
    m: Machine, where: str, document: dict[str, Any], said: str
) -> None:
    # As every gap: a warning until the machine holds an approval. Mutations (`mutations/`'s "the
    # boundary row is red with no approval" -> red; "the boundary row reads no user
    # excludedCommands" -> `user-excluded-commands` names no gap).
    owner = _merged(SANDBOX_ON, _deny(_rule(m.record_directory)))
    if where == "user":
        m.user(_merged(owner, document))
    else:
        m.user(owner)
        m.project(document)
    row = m.row()
    assert row.status == WARN, row
    assert row.detail == "; ".join((boundary.NONE_HELD, said))
    assert row.remedy == boundary.NARROW_THE_SETTINGS


@pytest.mark.parametrize("where", ["managed-file", "drop-in", "beside-a-gap"])
def test_managed_settings_excluded_commands_keep_the_row_from_green(m: Machine, where: str) -> None:
    # Managed settings' `excludedCommands` is an administrator's choice, and its commands still run
    # outside the sandbox, where the deny rule does not reach the shell: named, with its remedy,
    # and the row at best a warning, from the managed file or a drop-in beside it alike; beside a
    # red gap it is named too. Mutations (`mutations/`'s "the boundary row reads no managed
    # excludedCommands" -> every case loses the sentence, and `managed-file` and `drop-in` are ok;
    # "the boundary row lets managed excludedCommands make the row green" -> `managed-file` is ok).
    managed = managed_settings()
    assert managed is not None
    excluded = {"sandbox": {"excludedCommands": ["docker *"]}}
    if where == "drop-in":
        m.managed(ENFORCED)
        _write(managed.parent / "managed-settings.d" / "20-docker.json", excluded)
    else:
        m.managed(_merged(ENFORCED, excluded))
    gap = _allow_write("**") if where == "beside-a-gap" else {}
    m.user(_merged(SANDBOX_ON, _deny(_rule(m.record_directory)), gap))
    m.approvals(1)
    row = m.row()
    said = boundary.MANAGED_EXCLUDED.format(managed=managed)
    remedy = boundary.UNEXCLUDE_MANAGED.format(managed=managed)
    lead = boundary.HELD.format(count=1)
    if where == "beside-a-gap":
        widened = boundary.WIDENED.format(label=_USER, key=_WRITE)
        assert (row.status, row.detail, row.remedy) == (
            RED,
            "; ".join((lead, widened, said)),
            "; ".join((boundary.NARROW_THE_SETTINGS, remedy)),
        )
    else:
        assert (row.status, row.detail, row.remedy) == (WARN, "; ".join((lead, said)), remedy)


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
    # way to silence the row. With no approval held, since one is judged whatever the project
    # carries. Mutation (`mutations/`'s "the boundary row skips a project that ships Claude Code
    # settings for the agents it lists"): the row skips.
    (m.root / CONFIG_FILE).write_text(
        f'[stayfixed]\nversion = "{stayfixed.__version__}"\nstate = "installed"\n'
        'agents = ["codex"]\n\n[project]\nname = "p"\n',
        encoding="utf-8",
    )
    getattr(m, carried)({})
    row = m.row()
    assert row.status == WARN, row
    assert row.detail.startswith(boundary.NONE_HELD + "; "), row.detail


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
    monkeypatch.setattr(trust_boundary, "CASE_FOLDS", True)
    m.user(_merged(SANDBOX_ON, _deny(_rule(m.record_directory))))
    m.project(_allow_write(str(m.record_directory).swapcase()))
    m.approvals(1)
    row = m.row()
    assert row.status == RED, row
    assert boundary.WIDENED.format(label=_PROJECT, key=_WRITE) in row.detail.split("; ")


def test_a_case_variant_of_the_sandbox_s_temporary_directory_is_it_where_names_fold(
    m: Machine, monkeypatch: pytest.MonkeyPatch
) -> None:
    # On macOS's default volume `CLAUDE-501` is the sandbox's `claude-501`, so an entry below it is
    # below the directory sandboxed commands write. Mutation (`mutations/`'s "the boundary row
    # reads the sandbox's temporary directory by its case"): the entry is shown safe and the row is
    # ok.
    monkeypatch.setattr(trust_boundary, "CASE_FOLDS", True)
    m.managed(ENFORCED)
    m.user(_merged(SANDBOX_ON, _deny(_rule(m.record_directory)), _allow_write("/srv/CLAUDE-501/x")))
    m.approvals(1)
    row = m.row()
    assert row.status == RED, row
    assert boundary.WIDENED.format(label=_USER, key=_WRITE) in row.detail.split("; ")


def test_composed_and_decomposed_spellings_compare_alike_where_names_fold(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # macOS hands back a name decomposed or composed, so the record's two spellings and an entry
    # compare in NFC there. Mutation (`mutations/`'s "the boundary row compares names composed
    # and decomposed as different"): the two spellings differ.
    monkeypatch.setattr(trust_boundary, "CASE_FOLDS", True)
    assert trust_boundary.folded("/Users/José") == trust_boundary.folded("/Users/José")
    monkeypatch.setattr(trust_boundary, "CASE_FOLDS", False)
    assert trust_boundary.folded("/Users/José") != trust_boundary.folded("/Users/José")


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


# Protection a repository's file alone provides: in force for this session, and gone with the next
# commit that removes it, which a pull delivers with no person acting. It decides red as any layer
# does, and is never green.
def _repository_only(m: Machine) -> None:
    # Managed settings make the sandbox admin-required and refuse to start without it,
    # which an MDM commonly does without turning it on; the user's file holds neither the sandbox
    # nor the rule; the repository's committed file holds both.
    m.managed(MANAGED_NO_RETRY_ENFORCED)
    m.project(_merged(SANDBOX_ON, _deny(_rule(m.record_directory))))


def _sandbox_from_local(m: Machine) -> None:
    m.managed(MANAGED_NO_RETRY_ENFORCED)
    m.user(_deny(_rule(m.record_directory)))
    m.local(SANDBOX_ON)


def _local_true_over_user_false(m: Machine) -> None:
    m.managed(MANAGED_NO_RETRY_ENFORCED)
    m.user(_merged(SANDBOX_OFF, _deny(_rule(m.record_directory))))
    m.local(SANDBOX_ON)


def _deny_from_project(m: Machine) -> None:
    m.managed(ENFORCED)
    m.project(_deny(_rule(m.record_directory)))


def _owner_and_repository(m: Machine) -> None:
    m.managed(MANAGED_NO_RETRY_ENFORCED)
    m.user(_merged(SANDBOX_ON, _deny(_rule(m.record_directory))))
    m.project(_merged(SANDBOX_ON, _deny(_rule(m.record_directory))))


def _repository_true_no_deny(m: Machine) -> None:
    m.managed(MANAGED_NO_RETRY_ENFORCED)
    m.project(SANDBOX_ON)


@pytest.mark.parametrize(
    ("settings", "expected", "said"),
    [
        pytest.param(
            _repository_only,
            WARN,
            lambda m: (
                boundary.SANDBOX_FROM_REPOSITORY.format(label=_PROJECT),
                boundary.DENY_FROM_REPOSITORY.format(
                    rule=_rule(m.record_directory), label=_PROJECT
                ),
            ),
            id="repository-only",
        ),
        pytest.param(
            _sandbox_from_local,
            WARN,
            lambda m: (boundary.SANDBOX_FROM_REPOSITORY.format(label=_LOCAL),),
            id="sandbox-from-local",
        ),
        pytest.param(
            _local_true_over_user_false,
            WARN,
            lambda m: (boundary.SANDBOX_FROM_REPOSITORY.format(label=_LOCAL),),
            id="local-true-over-user-false",
        ),
        pytest.param(
            _deny_from_project,
            WARN,
            lambda m: (
                boundary.DENY_FROM_REPOSITORY.format(
                    rule=_rule(m.record_directory), label=_PROJECT
                ),
            ),
            id="deny-from-project",
        ),
        pytest.param(
            _owner_and_repository,
            OK,
            lambda m: (boundary.GUARDED.format(rule=_rule(m.record_directory)),),
            id="owner-and-repository",
        ),
        pytest.param(
            _repository_true_no_deny,
            RED,
            lambda m: (
                boundary.NO_DENY.format(rule=_rule(m.record_directory)),
                boundary.SANDBOX_FROM_REPOSITORY.format(label=_PROJECT),
            ),
            id="repository-true-no-deny",
        ),
    ],
)
def test_protection_only_a_repository_s_file_provides_is_never_green(
    m: Machine, settings: Any, expected: str, said: Any
) -> None:
    # The sandbox's `true` and the deny rule count toward green only from managed settings or the
    # user's file; from a repository's file alone the row is at best a warning naming that file,
    # with the remedy that puts them in the owner's file. Where the owner's file holds them too,
    # the repository's copy changes nothing. Mutations (`mutations/`'s "the boundary row counts a
    # repository's true toward green" -> `repository-only`, `sandbox-from-local` and
    # `local-true-over-user-false` say no such thing, and the first and the last of those are ok
    # or name the deny rule alone; "the boundary row counts a repository's deny rule toward green"
    # -> `repository-only` and `deny-from-project` say nothing of the rule).
    settings(m)
    m.approvals(1)
    row = m.row()
    assert row.status == expected, row
    assert row.detail == "; ".join((boundary.HELD.format(count=1), *said(m)))
    if expected == WARN:
        assert row.remedy == boundary.ADD_THE_BOUNDARY


# `sandbox.filesystem.disabled`, which turns the sandbox's filesystem confinement off while
# `enabled` stays true (the sandboxing reference). Every case below is otherwise enforced and green.
_FILESYSTEM_OFF: dict[str, Any] = {"sandbox": {"filesystem": {"disabled": True}}}


@pytest.mark.parametrize(
    ("where", "value", "admin", "expected"),
    [
        pytest.param("managed", True, True, RED, id="managed"),
        pytest.param("user", True, True, RED, id="user"),
        pytest.param("user", "yes", True, RED, id="user-not-a-bool"),
        pytest.param("project", True, False, RED, id="project"),
        pytest.param("local", True, False, RED, id="local"),
        pytest.param("project", True, True, OK, id="project-under-admin"),
        pytest.param("user", False, True, OK, id="user-false"),
    ],
)
def test_a_sandbox_that_confines_no_file_is_a_gap(
    m: Machine, where: str, value: object, admin: bool, expected: str
) -> None:
    # With the filesystem layer off, an agent's sandboxed shell writes anywhere, the trust record
    # included, so the key is a gap shaped as the sandbox being off: in managed settings and the
    # user's file always, set to anything but `false`; in a repository's file while the sandbox is
    # not admin-required (it is ignored there while it is, as every loosening repository key is).
    # Mutations (`mutations/`'s "the boundary row reads no sandbox.filesystem.disabled" -> every
    # red case is ok or warns; "the boundary row reads filesystem.disabled only when it is true"
    # -> `user-not-a-bool` is ok; "the boundary row reads a repository's filesystem.disabled while
    # admin-required" -> `project-under-admin` is red).
    disabled = {"sandbox": {"filesystem": {"disabled": value}}}
    owner = _merged(SANDBOX_ON, _deny(_rule(m.record_directory)))
    managed = ENFORCED if admin else _merged(SANDBOX_ON, {"sandbox": {"failIfUnavailable": True}})
    if where == "managed":
        m.managed(_merged(managed, disabled))
        m.user(owner)
    elif where == "user":
        m.managed(managed)
        m.user(_merged(owner, disabled))
    else:
        m.managed(managed)
        m.user(owner)
        getattr(m, where)(disabled)
    m.approvals(1)
    row = m.row()
    assert row.status == expected, row
    if expected == RED:
        label = {
            "managed": str(managed_settings()),
            "user": _USER,
            "project": _PROJECT,
            "local": _LOCAL,
        }[where]
        assert row.detail == "; ".join(
            (boundary.HELD.format(count=1), boundary.FILESYSTEM_OFF.format(label=label))
        )
        assert row.remedy == boundary.KEEP_THE_FILESYSTEM


def test_a_sandbox_that_confines_no_file_warns_with_no_approval(m: Machine) -> None:
    # As every gap: a warning until the machine holds an approval. Mutation (`mutations/`'s "the
    # boundary row is red with no approval"): red.
    m.managed(ENFORCED)
    m.user(_merged(SANDBOX_ON, _FILESYSTEM_OFF, _deny(_rule(m.record_directory))))
    row = m.row()
    assert (row.status, row.detail) == (
        WARN,
        "; ".join((boundary.NONE_HELD, boundary.FILESYSTEM_OFF.format(label=_USER))),
    )


# Two widening entries, one strictly inside the other, a managed one included: an agent's shell
# writes in the outer one, so the inner one may be a link to the record's directory by the time a
# session resolves it. Whether a deny rule holds inside a wider write entry was not measured, so the
# inner one is a gap; an entry beside another, or naming the same place, is not.
def _nested_case(
    where: dict[str, dict[str, Any]], admin: bool, expected: str, said: list[tuple[str, str]]
) -> tuple[dict[str, dict[str, Any]], bool, str, list[tuple[str, str]]]:
    return (where, admin, expected, said)


NESTED_CASES = [
    pytest.param(
        *_nested_case({"user": _allow_write("~/a", "~/a/b")}, True, RED, [(_USER, _WRITE)]),
        id="user-inside-user",
    ),
    pytest.param(
        *_nested_case(
            {"user": _directories("~/a"), "project": _allow_write("~/a/b")},
            False,
            RED,
            [(_PROJECT, _WRITE)],
        ),
        id="project-inside-user",
    ),
    # The mirrored pair the sandboxing reference's users write: the same place for the shell and
    # the file tools. Replacing it needs write access to its parent, which neither entry gives.
    pytest.param(
        *_nested_case(
            {"user": _merged(_allow_write("/tmp/build"), _edit("//tmp/build"))}, True, OK, []
        ),
        id="one-place-twice",
    ),
    pytest.param(
        *_nested_case(
            {"managed": _allow_write("/tmp/build"), "user": _allow_write("/tmp/build")},
            True,
            OK,
            [],
        ),
        id="one-place-in-managed-and-user",
    ),
    # An administrator's entry holds the user's as any other would; managed settings' own entries
    # are never said.
    pytest.param(
        *_nested_case(
            {"managed": _allow_write("~/a"), "user": _directories("~/a/b")},
            True,
            RED,
            [(_USER, _DIRECTORIES)],
        ),
        id="user-inside-managed",
    ),
    pytest.param(
        *_nested_case({"managed": _allow_write("~/a", "~/a/b")}, True, OK, []),
        id="managed-inside-managed",
    ),
    pytest.param(
        *_nested_case({"user": _allow_write("~/a", "~/ab")}, True, OK, []),
        id="side-by-side",
    ),
    pytest.param(
        *_nested_case({"user": _allow_write("/tmp/build", "~/.kube")}, True, OK, []),
        id="the-reference-s-two",
    ),
    pytest.param(
        *_nested_case(
            {"user": _allow_write("~/a/b"), "project": _allow_write("~/a")}, True, OK, []
        ),
        id="repository-outer-under-admin",
    ),
]


@pytest.mark.parametrize(("where", "admin", "expected", "said"), NESTED_CASES)
def test_a_widening_entry_inside_another_is_a_gap(
    m: Machine,
    where: dict[str, dict[str, Any]],
    admin: bool,
    expected: str,
    said: list[tuple[str, str]],
) -> None:
    # Each entry alone is a literal outside the project and the record's directory, so only the
    # pair can make it a gap: the inner one, said by file and key. Under admin-required a
    # repository's entries are not read, so they nest nothing. Mutations (`mutations/`'s "the
    # boundary row lets one widening entry lie inside another" -> every red case is ok or warns;
    # "the boundary row reads one entry inside another by its spelling's prefix" -> `side-by-side`
    # is red; "the boundary row takes two entries naming one place for nested" -> `one-place-twice`
    # and `one-place-in-managed-and-user` are red; "the boundary row compares no entry with managed
    # settings' entries" -> `user-inside-managed` is ok; "the boundary row says managed settings'
    # own nested entries" -> `managed-inside-managed` is red).
    base = ENFORCED if admin else _merged(SANDBOX_ON, {"sandbox": {"failIfUnavailable": True}})
    m.managed(_merged(base, where.get("managed", {})))
    owner = _merged(SANDBOX_ON, _deny(_rule(m.record_directory)))
    m.user(_merged(owner, where.get("user", {})))
    if "project" in where:
        m.project(where["project"])
    m.approvals(1)
    row = m.row()
    assert row.status == expected, row
    nested = [boundary.NESTED.format(label=label, key=key) for label, key in said]
    parts = row.detail.split("; ")
    assert [part for part in parts if "another widening entry" in part] == nested
    if nested:
        assert boundary.NARROW_THE_SETTINGS in row.remedy.split("; ")


def test_a_case_variant_of_the_project_is_inside_it(
    m: Machine, monkeypatch: pytest.MonkeyPatch
) -> None:
    # On macOS's default volume a case variant of the project's path is the project, so a
    # `CLAUDE_CONFIG_DIR` spelled so is inside it: named, never judged. Folded as the row folds an
    # entry, on every platform here since the folding is patched on. Mutation (`mutations/`'s "a
    # directory is judged inside the project by its case"): the variant is judged as outside.
    monkeypatch.setattr(trust_boundary, "CASE_FOLDS", True)
    planted = m.root / ".claude-config"
    _write(planted / "settings.json", _merged(ENFORCED, _deny(_rule(m.record_directory))))
    variant = str(m.root).swapcase() + "/.claude-config"
    (m.home / ".claude").rmdir()
    m.env["CLAUDE_CONFIG_DIR"] = variant
    m.approvals(1)
    row = m.row()
    assert (row.status, row.detail) == (
        WARN,
        "; ".join(
            (boundary.NO_CLAUDE_CODE, boundary.CONFIG_DIR_IN_PROJECT.format(path=clipped(variant)))
        ),
    )


# --- what the row cannot read is not read as absent ---------------------------------------------

BOM = "﻿"


@pytest.mark.parametrize("mark", ["", BOM], ids=["plain", "byte-order-mark"])
def test_a_project_file_opening_with_a_byte_order_mark_is_read_as_claude_code_reads_it(
    m: Machine, mark: str
) -> None:
    # Claude Code reads past a leading byte-order mark (`harnesses.LENIENT_SETTINGS`); the row read
    # such a file as absent, so a committed one turning the sandbox off moved red to a warning.
    # Mutation (`mutations/`'s "the boundary row reads a settings file opening with a byte-order
    # mark as absent"): `byte-order-mark` warns and names the file unread.
    _sandbox_and_deny(m)
    m.project(mark + json.dumps(SANDBOX_OFF))
    m.approvals(1)
    row = m.row()
    assert row.status == RED, row
    assert boundary.TURNED_OFF.format(label=boundary.PROJECT_SETTINGS) in row.detail.split("; ")
    assert boundary.NOT_READ.format(label=boundary.PROJECT_SETTINGS) not in row.detail


def test_a_user_file_opening_with_a_byte_order_mark_still_guards(m: Machine) -> None:
    # The owner's own file with the mark judges as it would without one: the legitimate user the
    # reading must not refuse. Mutation: `mutations/`'s "the boundary row reads a settings file
    # opening with a byte-order mark as absent" -- the row warns that the file could not be read.
    m.user(BOM + json.dumps(_deny(_rule(m.record_directory))))
    m.managed(ENFORCED)
    m.approvals(1)
    assert m.row().status == OK


@pytest.mark.parametrize(
    ("document", "key"),
    [
        pytest.param(
            {"sandbox": {"filesystem": {"allowWrite": "~/.config"}}},
            boundary.WIDENING_KEYS[0],
            id="allowWrite-a-string",
        ),
        pytest.param(
            {"sandbox": {"filesystem": {"allowWrite": ["/tmp/build", 3]}}},
            boundary.WIDENING_KEYS[0],
            id="allowWrite-holding-a-number",
        ),
        pytest.param(
            {"permissions": {"additionalDirectories": "~/.config"}},
            boundary.WIDENING_KEYS[2],
            id="additionalDirectories-a-string",
        ),
        pytest.param(
            {"permissions": {"allow": "Edit(~/.config/**)"}},
            boundary.WIDENING_KEYS[1],
            id="allow-a-string",
        ),
        pytest.param(
            {"sandbox": {"excludedCommands": "docker *"}},
            boundary.EXCLUDED_KEY,
            id="excludedCommands-a-string",
        ),
    ],
)
def test_a_widening_key_that_is_not_a_list_of_entries_is_a_gap(
    m: Machine, document: dict[str, Any], key: str
) -> None:
    # A value of the wrong shape shows nothing safe, so it is a gap, named with its key and file;
    # read as no entries it turned the row green. How Claude Code reads one was not measured.
    # Mutation (`mutations/`'s "the boundary row reads a widening key that is not a list as
    # empty"): each case is ok.
    rule = _deny(_rule(m.record_directory))
    merged = {**rule, **document}
    if "permissions" in document:
        merged["permissions"] = {**rule["permissions"], **document["permissions"]}
    m.user(merged)
    m.managed(ENFORCED)
    m.approvals(1)
    row = m.row()
    assert row.status == RED, row
    gap = boundary.NOT_ENTRIES.format(label=boundary.USER_LABEL, key=key)
    assert gap in row.detail.split("; ")
    assert boundary.SPELL_THE_SETTINGS in row.remedy.split("; ")


def test_a_managed_excluded_commands_that_is_not_a_list_keeps_the_row_from_green(
    m: Machine,
) -> None:
    # An administrator's `excludedCommands` keeps the row at a warning; one that cannot be read
    # as a list was read as none, and the row was green. Mutation (`mutations/`'s "the boundary row
    # reads a managed excludedCommands that is not a list as none"): ok.
    m.user(_deny(_rule(m.record_directory)))
    m.managed({"sandbox": {**ENFORCED["sandbox"], "excludedCommands": "docker *"}})
    m.approvals(1)
    row = m.row()
    managed = str(managed_settings())
    assert row.status == WARN, row
    assert boundary.MANAGED_EXCLUDED.format(managed=managed) in row.detail


def _with_sandbox(m: Machine, sandbox: object) -> dict[str, Any]:
    return {**_deny(_rule(m.record_directory)), "sandbox": sandbox}


@pytest.mark.parametrize(
    ("write", "gap"),
    [
        pytest.param(
            lambda m: m.project({"sandbox": {"enabled": "false"}}),
            boundary.NOT_A_SWITCH.format(label=boundary.PROJECT_SETTINGS, key="sandbox.enabled"),
            id="project-enabled-a-string",
        ),
        pytest.param(
            lambda m: m.user(_with_sandbox(m, {"enabled": 1})),
            boundary.NOT_A_SWITCH.format(label=boundary.USER_LABEL, key="sandbox.enabled"),
            id="user-enabled-a-number",
        ),
        pytest.param(
            lambda m: m.managed({"sandbox": {**ENFORCED["sandbox"], "failIfUnavailable": "true"}}),
            "{managed}'s sandbox.failIfUnavailable is not true or false",
            id="managed-fail-if-unavailable-a-string",
        ),
        pytest.param(
            lambda m: m.managed(
                {"sandbox": {**ENFORCED["sandbox"], "allowUnsandboxedCommands": "false"}}
            ),
            "{managed}'s sandbox.allowUnsandboxedCommands is not true or false",
            id="managed-unsandboxed-a-string",
        ),
        pytest.param(
            lambda m: m.project({"sandbox": "off"}),
            boundary.NOT_AN_OBJECT.format(label=boundary.PROJECT_SETTINGS, key="sandbox"),
            id="project-sandbox-not-an-object",
        ),
        pytest.param(
            lambda m: m.user(_with_sandbox(m, {"filesystem": True})),
            boundary.NOT_AN_OBJECT.format(label=boundary.USER_LABEL, key="sandbox.filesystem"),
            id="user-filesystem-not-an-object",
        ),
    ],
)
def test_a_boundary_key_of_the_wrong_shape_is_a_gap(m: Machine, write: Any, gap: str) -> None:
    # Every other setting holds the row green; the one key of the wrong shape is a gap, named, red
    # with an approval held. Read as absent, each left the row as good as its other files.
    # Mutations (`mutations/`'s "the boundary row reads a sandbox switch that is not true or false
    # as absent" -> each switch case is ok, or a warning; "the boundary row reads a settings table
    # that is not an object as absent" -> each `not-an-object` case is ok).
    m.user(_deny(_rule(m.record_directory)))
    m.managed(ENFORCED)
    write(m)
    m.approvals(1)
    row = m.row()
    expected = gap.format(managed=str(managed_settings()))
    assert row.status == RED, row
    assert any(part.startswith(expected) for part in row.detail.split("; ")), row.detail
    assert boundary.SPELL_THE_SETTINGS in row.remedy.split("; ")


def test_a_boundary_key_of_the_wrong_shape_is_a_warning_with_no_approval(m: Machine) -> None:
    # Red only once the machine holds an approval: with none, the same gap warns. No mutation of
    # its own: the status split is `mutations/`'s "the boundary row is red with no approval".
    m.user(_deny(_rule(m.record_directory)))
    m.managed(ENFORCED)
    m.project({"sandbox": {"enabled": "false"}})
    assert m.row().status == WARN


# --- CLAUDE_CONFIG_DIR: bounded in print, never asked about elsewhere, every checkout inside -----

LONG = 40_000


@pytest.mark.parametrize("where", ["inside-the-project", "elsewhere"])
def test_a_claude_config_dir_of_any_length_prints_bounded(m: Machine, where: str) -> None:
    # A committed `env` block can set the variable to anything, and the `doctor` skill relays the
    # row to a model, so the value prints through `printed.clipped`: its first characters and its
    # length, whether it names a place inside the project or one the row never asks the filesystem
    # about. Mutations (`mutations/`'s "the boundary row prints a CLAUDE_CONFIG_DIR inside the
    # project whole" -> `inside-the-project` carries all of it;
    # "the boundary row prints a CLAUDE_CONFIG_DIR elsewhere whole" -> `elsewhere` does).
    base = m.root if where == "inside-the-project" else m.tmp / "elsewhere"
    value = str(base / ("a" * LONG))
    m.env["CLAUDE_CONFIG_DIR"] = value
    m.approvals(1)
    row = m.row()
    said = (
        boundary.CONFIG_DIR_IN_PROJECT
        if where == "inside-the-project"
        else boundary.CONFIG_DIR_ELSEWHERE
    )
    assert said.format(path=clipped(value)) in row.detail.split("; "), row.detail
    assert len(row.detail) < 2_000


def test_a_claude_config_dir_judged_alone_prints_bounded(m: Machine) -> None:
    # The directory the home's absence leaves judged alone exists, so `PATH_MAX` bounds its name;
    # it prints through `printed.clipped` all the same, one rule for every site. Mutation
    # (`mutations/`'s "the boundary row prints a CLAUDE_CONFIG_DIR judged alone whole"): the whole
    # name reaches the row.
    (m.home / ".claude").rmdir()
    config = m.home / ("c" * 100) / ("d" * 100)
    _write(config / "settings.json", _merged(ADMIN_REQUIRED, _deny(_rule(m.record_directory))))
    m.env["CLAUDE_CONFIG_DIR"] = str(config)
    m.managed(ENFORCED)
    m.approvals(1)
    row = m.row()
    assert boundary.CHOSEN_ALONE.format(path=clipped(str(config))) in row.detail.split("; ")
    assert str(config) not in row.detail


def test_a_claude_config_dir_under_neither_the_home_nor_the_project_is_never_asked_about(
    m: Machine, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A path a committed `env` block chose may lie under an automount root, where one stat stalls
    # `doctor` until the network answers; so a directory under neither the home nor the project is
    # named, never asked of the filesystem, and the row is at best a warning; the detail says how a
    # person whose own directory lies there writes the rules into it. Mutations (`mutations/`'s "a
    # CLAUDE_CONFIG_DIR under neither the home nor the project is asked of the filesystem" -> the
    # directory is resolved and judged, and the row reads ok; "the boundary row names no way to
    # write a CLAUDE_CONFIG_DIR elsewhere" -> the detail names no command).
    elsewhere = m.tmp / "elsewhere"
    _write(elsewhere / "settings.json", _merged(ADMIN_REQUIRED, _deny(_rule(m.record_directory))))
    m.user(_deny(_rule(m.record_directory)))
    m.managed(ENFORCED)
    m.env["CLAUDE_CONFIG_DIR"] = str(elsewhere)
    m.approvals(1)
    asked: list[str] = []
    for name in ("resolved", "is_dir", "names_regular_file"):
        real = getattr(fsops, name)

        def recording(path: Path, *args: Any, _real: Any = real, **kwargs: Any) -> Any:
            if str(path).startswith(str(elsewhere)):
                asked.append(str(path))
            return _real(path, *args, **kwargs)

        monkeypatch.setattr(fsops, name, recording)
    row = m.row()
    assert row.status == WARN, row
    assert boundary.CONFIG_DIR_ELSEWHERE.format(path=clipped(str(elsewhere))) in row.detail
    assert "`stayfixed setup --approval-boundary --settings <that directory>/settings.json`" in (
        row.detail
    )
    assert asked == []


def test_a_claude_config_dir_in_another_checkout_of_the_repository_is_inside_it(
    m: Machine,
) -> None:
    # What a repository commits reaches every one of its checkouts, so a directory in a sibling
    # worktree is the repository's to fill as one in the project is: named, never judged. Mutation
    # (`mutations/`'s "a CLAUDE_CONFIG_DIR in another checkout of the repository is outside it"):
    # the sibling's planted settings are judged alone.
    git(m.root, "init", "-q", "-b", "main")
    git(m.root, "commit", "-q", "--allow-empty", "-m", "chore: seed")
    sibling = m.tmp / "sibling"
    git(m.root, "worktree", "add", "-q", "-b", "side", str(sibling))
    planted = sibling / ".claude-config"
    _write(planted / "settings.json", _merged(ADMIN_REQUIRED, _deny(_rule(m.record_directory))))
    (m.home / ".claude").rmdir()
    m.env["CLAUDE_CONFIG_DIR"] = str(planted)
    m.managed(ENFORCED)
    m.approvals(1)
    row = m.row()
    said = boundary.CONFIG_DIR_IN_PROJECT.format(path=clipped(str(planted)))
    assert (row.status, row.detail) == (WARN, "; ".join((boundary.NO_CLAUDE_CODE, said)))


def test_a_repository_whose_checkouts_git_cannot_list_holds_the_directory(
    m: Machine, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Where a `.git` is and git gives no answer, which checkouts the repository has is not known,
    # so the variable's directory is taken to be in one, as a link that cannot be followed is.
    # Mutation (`mutations/`'s "a repository whose checkouts git cannot list is read as having
    # none"): the directory under the home is judged.
    (m.root / ".git").mkdir()
    monkeypatch.setattr(trust_boundary, "git_run", lambda root, *args, **kwargs: (-1, ""))
    config = m.home / "config-dir"
    _write(config / "settings.json", _merged(ADMIN_REQUIRED, _deny(_rule(m.record_directory))))
    m.user(_deny(_rule(m.record_directory)))
    m.managed(ENFORCED)
    m.env["CLAUDE_CONFIG_DIR"] = str(config)
    m.approvals(1)
    row = m.row()
    said = boundary.CONFIG_DIR_IN_PROJECT.format(path=clipped(str(config)))
    assert row.status == WARN, row
    assert said in row.detail.split("; ")
