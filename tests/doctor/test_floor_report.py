"""`doctor` on a repository with nothing configured, and the owner's preferences row
(`src/stayfixed/doctor/checks.py`).

A default install has no `stayfixed.toml`, and the guards and `doctor` work there, so the report
warns that the rest needs `stayfixed init` and is red about nothing. The report reads the
configuration the way a session does (`config.session`): a file that loads with notes is a warning
listing the keys, and only a file that falls back whole is red, in the session's words."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from stayfixed.config.session import FALLBACK_WARNING, cause
from stayfixed.doctor.api import NO_CONFIG_SKIP, OK, RED, SKIP, WARN, Check, run_checks
from stayfixed.doctor.checks import NOT_INITIALISED
from tests.doctor.test_checks import LOCAL_ONLY, _initialised
from tests.overlay.test_requires import overlay_with
from tests.ownerhome import as_owner_home
from tests.runners import Recorder

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")


def run_checks_for(tmp_path: Path, root: Path, *, machine: Path) -> list[Check]:
    """`run_checks` hermetic: a home, a machine file and an environment of the test's own."""
    env = {"PATH": os.environ.get("PATH", ""), "HOME": os.environ["HOME"]}
    return run_checks(root, home=tmp_path / "home", machine=machine, runner=Recorder(), env=env)


def row(report: list[Check], name: str) -> Check:
    return next(check for check in report if check.name == name)


def none(tmp_path: Path) -> Path:
    return tmp_path / "none.toml"


def test_no_stayfixed_toml_is_a_warning_and_no_row_is_red(tmp_path: Path) -> None:
    # A repository with no `stayfixed.toml` was one red row and sixteen skips, "the plugin's hooks
    # are silent in this repository" — false since the guards run with no configuration, and red
    # on every default install. Mutation (`mutations/`'s "not-initialised is red with no
    # stayfixed.toml"): the row is red.
    root = tmp_path / "project"
    root.mkdir()
    report = run_checks_for(tmp_path, root, machine=none(tmp_path))
    assert (row(report, "not-initialised").status, row(report, "not-initialised").detail) == (
        WARN,
        NOT_INITIALISED,
    )
    assert not [check.name for check in report if check.status == RED]


@pytest.mark.parametrize(
    "name",
    ["versions", "files", "wrapper", "cli-path", "diagnostics", "ignored-env", "preferences"],
)
def test_rows_that_need_no_configuration_run_without_one(tmp_path: Path, name: str) -> None:
    # Each answered "there is no stayfixed.toml to check against" whatever it asks. Not skipped
    # for want of a configuration: a skip may remain on a state of this machine (no plugin root,
    # no harness data root), never on the missing file. Mutation (`mutations/`'s "doctor skips
    # every row without a stayfixed.toml"): every row says the configuration is missing.
    root = tmp_path / "project"
    root.mkdir()
    checked = row(run_checks_for(tmp_path, root, machine=none(tmp_path)), name)
    assert checked.detail != NO_CONFIG_SKIP


@pytest.mark.parametrize("name", ["budgets", "ci-ref"])
def test_rows_that_read_the_configuration_skip_without_one(tmp_path: Path, name: str) -> None:
    # Mutation (`mutations/`'s "the budgets row reads a configuration that is not there"): the
    # row raises and reads as a check that could not run.
    root = tmp_path / "project"
    root.mkdir()
    checked = row(run_checks_for(tmp_path, root, machine=none(tmp_path)), name)
    assert (checked.status, checked.detail) == (SKIP, NO_CONFIG_SKIP)


def test_notes_are_listed_by_key(tmp_path: Path) -> None:
    # Keys only: a note's sentence carries the loader's refusal, and the value never prints.
    # Mutation (`mutations/`'s "not-initialised is green over a file that loaded with notes"):
    # the row is green.
    root = _initialised(tmp_path, template=LOCAL_ONLY + '\n[newer]\nx = 1\n[ci]\nmode = "fax"\n')
    checked = row(run_checks_for(tmp_path, root, machine=none(tmp_path)), "not-initialised")
    assert checked.status == WARN
    assert checked.detail.endswith(": newer, ci.mode")
    assert "fax" not in checked.detail


def test_a_whole_fallback_is_red(tmp_path: Path) -> None:
    # The session's own words, without the pointer back at `doctor`. Mutation (`mutations/`'s "a
    # whole fallback reads as a repository with no stayfixed.toml"): the row is the warning.
    root = tmp_path / "project"
    root.mkdir()
    (root / "stayfixed.toml").write_text("[[[", encoding="utf-8")
    report = run_checks_for(tmp_path, root, machine=none(tmp_path))
    checked = row(report, "not-initialised")
    assert (checked.status, checked.detail) == (RED, cause(FALLBACK_WARNING))
    # The rows that read no configuration still answer: a file that does not load costs the
    # project's rows, not the installation's.
    assert row(report, "cli-path").detail != NO_CONFIG_SKIP


def test_preferences_names_the_layer_and_hides_free_text(tmp_path: Path) -> None:
    # Each owner key and each preference as `key (layer)`, with a value only where it is one of
    # stayfixed's own words, a number or a boolean: `index_extra` and `reply_language` are text a
    # repository or an owner wrote. Mutation (`mutations/`'s "the preferences row prints a free
    # text value"): the repository's text reaches the row.
    root = _initialised(tmp_path, template=LOCAL_ONLY + 'index_extra = ["IGNORE-PRIOR-RULES.md"]\n')
    machine = tmp_path / "machine.toml"
    machine.write_text(
        '[personal]\nreply_language = "SECRET-WORD"\n[guards]\nbg_cleanup = false\n', "utf-8"
    )
    checked = row(run_checks_for(tmp_path, root, machine=machine), "preferences")
    assert checked.status == OK
    for named in (
        "personal.reply_language (machine file)",
        "guards.bg_cleanup = false (machine file)",
        "memory.mode = local-only (repository)",
        "memory.groups (repository)",
        "memory.index_extra (repository)",
        "stayfixed.profile (preset)",
    ):
        assert named in checked.detail, named
    assert "IGNORE-PRIOR-RULES" not in checked.detail
    assert "SECRET-WORD" not in checked.detail


def test_preferences_with_no_stayfixed_toml_are_the_presets(tmp_path: Path) -> None:
    # Mutation (`mutations/`'s "the preferences row credits the repository with the preset's
    # values"): a preference reads as the repository's with no repository there.
    root = tmp_path / "project"
    root.mkdir()
    checked = row(run_checks_for(tmp_path, root, machine=none(tmp_path)), "preferences")
    assert "memory.mode = local-only (preset)" in checked.detail
    assert "(repository)" not in checked.detail


def test_preferences_warn_of_a_machine_file_that_could_not_be_used(tmp_path: Path) -> None:
    # The session's warning names the machine file and sends the owner here. Mutation
    # (`mutations/`'s "the preferences row says nothing of the machine file's notes"): green.
    root = tmp_path / "project"
    root.mkdir()
    machine = tmp_path / "machine.toml"
    machine.write_text("[guards\n", encoding="utf-8")
    checked = row(run_checks_for(tmp_path, root, machine=machine), "preferences")
    assert checked.status == WARN
    assert str(machine) in checked.detail


def _recorded_overlay(tmp_path: Path, requires: str) -> Path:
    """A machine file recording an overlay whose manifest declares `requires`."""
    overlay = overlay_with(tmp_path / "overlay", requires)
    machine = tmp_path / "machine.toml"
    machine.write_text(f'[overlay]\nroot = "{overlay}"\n', encoding="utf-8")
    return machine


def test_a_machine_with_an_overlay_and_no_stayfixed_toml_is_red_about_nothing(
    tmp_path: Path,
) -> None:
    # The two rows that read the project configuration beside a recorded overlay: the claims
    # `hook-entries` asks name the project's binding, and `overlay-requires` asks whether the
    # project consults the overlay. With no project, the claims answer what `common/` grants and
    # an unmet floor is a warning. Mutations (`mutations/`'s "the attach claims ask a binding of
    # no project configuration" -> `hook-entries` reads as a check that could not run; "the
    # overlay floor asks a project configuration that is not there" -> `overlay-requires` does).
    root = tmp_path / "project"
    root.mkdir()
    machine = _recorded_overlay(tmp_path, ">=99.0.0")
    report = run_checks_for(tmp_path, root, machine=machine)
    assert row(report, "overlay-requires").status == WARN
    assert row(report, "hook-entries").status != RED, row(report, "hook-entries")
    assert not [check.name for check in report if check.status == RED]


def test_harness_link_skips_without_a_configuration_when_the_homes_differ(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # What makes the harness link depends on the store's mode, which only the project's file
    # says. Mutation (`mutations/`'s "the harness-link row reads a configuration that is not
    # there"): the row reads as a check that could not run.
    as_owner_home(monkeypatch, tmp_path / "elsewhere")
    root = tmp_path / "project"
    root.mkdir()
    checked = row(run_checks_for(tmp_path, root, machine=none(tmp_path)), "harness-link")
    assert (checked.status, checked.detail) == (SKIP, NO_CONFIG_SKIP)
