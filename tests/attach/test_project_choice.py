"""Which overlay project `attach` binds a repository with no `stayfixed.toml` to.

A public clone the owner cannot commit to carries no `[project] name`, so the project comes, in
this order, from `--project`, from this machine's binding record, from the one overlay project
whose `project.toml` records this checkout's `origin`, and from the last segment of `origin`'s
path. Each step is a convenience and not a gate: the anchor is `origin`, which whoever cloned set,
and the screen names the project and the origin for the owner who ran the command to read.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from stayfixed import binding
from stayfixed.attach.binding import BOUND_HERE, BY_REMOTE, FROM_REMOTE, NAMED
from stayfixed.cli import build_parser, discover_registrars, run
from stayfixed.memory.api import PROJECT_RECORD, PROJECTS
from stayfixed.overlay.api import COMMON_CLAUDE, COMMON_CODEX, COMMON_MEMORY
from stayfixed.printed import quoted
from tests.attach.test_binding import _machine, _project_and_store
from tests.attach.test_write import SETTINGS
from tests.gitfixture import git
from tests.runners import Recorder, claude_code
from tests.snapshot import assert_snapshot_changed, assert_snapshot_unchanged, snapshot

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")


@pytest.fixture(autouse=True)
def _claude_code(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """No case reaches the developer's real `claude`: the CLI's `subprocess_runner()` is a
    recorder that writes what Claude Code's local-scope plugin calls write."""
    runner = Recorder(on_call=claude_code(tmp_path / "project"))
    monkeypatch.setattr("stayfixed.runner.subprocess_runner", lambda **_: runner)


def invoke(argv: list[str]) -> int:
    return run(argv, parser=build_parser(discover_registrars()))


def _clone(tmp_path: Path, *, origin: str | None) -> tuple[Path, Path, Path]:
    """A committed repository with no `stayfixed.toml`, the overlay the machine records, and the
    machine file. Returns `(root, overlay, machine)`."""
    root = tmp_path / "project"
    root.mkdir()
    (root / "README.md").write_text("a public clone\n", encoding="utf-8")
    git(root, "init", "-q", "-b", "main")
    if origin is not None:
        git(root, "remote", "add", "origin", origin)
    git(root, "add", "-A")
    git(root, "commit", "-qm", "init")
    overlay = tmp_path / "overlay"
    for relative in (COMMON_CLAUDE, COMMON_CODEX, COMMON_MEMORY):
        (overlay / relative).mkdir(parents=True)
    return root, overlay, _machine(tmp_path, overlay=overlay)


def _recorded(overlay: Path, name: str, remote: str) -> Path:
    """An overlay project whose binding record names `remote`; its directory."""
    home = overlay / PROJECTS / name
    home.mkdir(parents=True)
    (home / PROJECT_RECORD).write_text(f'remote = "{remote}"\n', encoding="utf-8")
    return home


def _flags(root: Path, machine: Path) -> list[str]:
    return ["--root", str(root), "--machine", str(machine)]


def _screen(root: Path, project: str, chosen: str, origin: str) -> str:
    made = binding.read_id(root)
    assert made is not None
    return (
        f"binding {binding.short(made)}: project {quoted(project)}, {chosen}, "
        f"origin {quoted(origin)}"
    )


def _bound_to(root: Path) -> str | None:
    found = binding.bound_project(root)
    return None if found is None else found.project


def test_project_names_the_project_of_a_repository_with_no_stayfixed_toml(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # The first way, and the one every refusal below names: the owner says which project. It wins
    # over the remote's own name, `widget` here. Mutation: `mutations/`'s "attach ignores
    # --project".
    origin = "git@example.com:o/widget.git"
    root, _, machine = _clone(tmp_path, origin=origin)
    assert invoke(["attach", "--project", "mine", *_flags(root, machine)]) == 0
    assert _bound_to(root) == "mine"
    assert _screen(root, "mine", NAMED, origin) in capsys.readouterr().out.splitlines()


def test_a_later_attach_takes_the_project_this_machines_binding_records(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # The second way: once bound, a routine re-attach needs no `--project`, and does not drift to
    # the remote's name. Mutation: `mutations/`'s "attach forgets this machine's binding".
    origin = "git@example.com:o/widget.git"
    root, _, machine = _clone(tmp_path, origin=origin)
    assert invoke(["attach", "--project", "mine", *_flags(root, machine)]) == 0
    capsys.readouterr()
    assert invoke(["attach", *_flags(root, machine)]) == 0
    assert _bound_to(root) == "mine"
    assert _screen(root, "mine", BOUND_HERE, origin) in capsys.readouterr().out.splitlines()


def test_the_one_overlay_project_recording_this_origin_is_the_project(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # The third way, the one a second machine meets: the overlay's record names the remote in
    # another spelling, which is the same repository as the binding note compares them. Mutation:
    # `mutations/`'s "attach finds no overlay project by its remote".
    origin = "https://github.com/o/widget"
    root, overlay, machine = _clone(tmp_path, origin=origin)
    _recorded(overlay, "alpha", "git@github.com:O/Widget.git")
    _recorded(overlay, "beta", "git@github.com:o/other.git")
    assert invoke(["attach", *_flags(root, machine)]) == 0
    assert _bound_to(root) == "alpha"
    assert _screen(root, "alpha", BY_REMOTE, origin) in capsys.readouterr().out.splitlines()


def test_two_overlay_projects_recording_this_origin_are_refused_and_nothing_is_written(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # Two of the owner's projects claim this repository, so which one is meant is the owner's to
    # say. Mutation: `mutations/`'s "attach takes the first of several projects recording its
    # remote".
    root, overlay, machine = _clone(tmp_path, origin="git@example.com:o/widget.git")
    _recorded(overlay, "alpha", "git@example.com:o/widget.git")
    _recorded(overlay, "beta", "https://example.com/o/widget.git")
    before = snapshot(root)
    assert invoke(["attach", *_flags(root, machine)]) == 2
    assert "--project" in capsys.readouterr().err
    assert invoke(["attach", "--check", *_flags(root, machine)]) == 2
    assert_snapshot_unchanged(root, before)
    assert binding.read_id(root) is None


def test_with_nothing_recorded_the_project_is_the_last_segment_of_origin_lower_cased(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # The fourth way, a first attach anywhere: the repository's own name, `.git` taken off and
    # lower-cased, which the overlay's record then keeps beside this remote for the next machine.
    # Mutation: `mutations/`'s "attach derives the project's name with its case".
    origin = "https://example.com/Owner/Widget-Kit.git"
    root, overlay, machine = _clone(tmp_path, origin=origin)
    assert invoke(["attach", *_flags(root, machine)]) == 0
    assert _bound_to(root) == "widget-kit"
    assert _screen(root, "widget-kit", FROM_REMOTE, origin) in capsys.readouterr().out.splitlines()
    record = overlay / PROJECTS / "widget-kit" / PROJECT_RECORD
    assert origin in record.read_text(encoding="utf-8")


def test_a_derived_name_the_overlay_records_with_another_remote_is_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # `widget` in the overlay is another repository of that name, and binding this clone to it
    # would deliver that project's grants and notes here. Mutation: `mutations/`'s "attach takes a
    # derived name the overlay records for another remote".
    root, overlay, machine = _clone(tmp_path, origin="git@example.com:o/widget.git")
    _recorded(overlay, "widget", "git@example.com:other/widget.git")
    before = snapshot(root)
    assert invoke(["attach", *_flags(root, machine)]) == 2
    assert "--project" in capsys.readouterr().err
    assert_snapshot_unchanged(root, before)
    assert invoke(["attach", "--project", "widget-fork", *_flags(root, machine)]) == 0


def test_a_derived_name_that_is_no_project_name_is_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # The derived name becomes a directory under the overlay's `projects/`, so it is held to the
    # rule `[project] name` is. Mutation: `mutations/`'s "attach takes a derived name the name
    # rule refuses".
    root, _, machine = _clone(tmp_path, origin="git@example.com:o/_tools.git")
    assert invoke(["attach", *_flags(root, machine)]) == 2
    assert "--project" in capsys.readouterr().err
    assert binding.read_id(root) is None


def test_no_origin_and_no_binding_is_refused_naming_project(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # Nothing names the project at all. Mutation: `mutations/`'s "attach takes the directory's
    # name where nothing names the project".
    root, _, machine = _clone(tmp_path, origin=None)
    assert invoke(["attach", *_flags(root, machine)]) == 2
    assert "--project" in capsys.readouterr().err
    assert invoke(["attach", "--check", *_flags(root, machine)]) == 2
    assert binding.read_id(root) is None
    assert invoke(["attach", "--project", "mine", *_flags(root, machine)]) == 0
    assert _bound_to(root) == "mine"


def test_project_beside_a_stayfixed_toml_is_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # The file names the project, and a second name beside it would bind the checkout to a
    # project the file does not name. Mutation: `mutations/`'s "attach takes --project beside a
    # stayfixed.toml".
    root, store = _project_and_store(tmp_path, recorded=None, origin="git@example.com:o/p.git")
    machine = _machine(tmp_path, overlay=store.parents[2])
    before = snapshot(root)
    assert invoke(["attach", "--project", "q", *_flags(root, machine)]) == 2
    assert "stayfixed.toml" in capsys.readouterr().err
    assert invoke(["attach", "--check", "--project", "q", *_flags(root, machine)]) == 2
    assert_snapshot_unchanged(root, before)
    assert binding.read_id(root) is None


def test_a_project_no_directory_name_can_be_is_refused_before_anything_runs(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # `--project` becomes a directory under the overlay's `projects/`, so `../common` is the value
    # the rule exists for; the refusal states the rule and never echoes the value.
    root, _, machine = _clone(tmp_path, origin="git@example.com:o/widget.git")
    with pytest.raises(SystemExit) as raised:
        invoke(["attach", "--project", "../common", *_flags(root, machine)])
    assert raised.value.code == 2
    assert "../common" not in capsys.readouterr().err
    assert binding.read_id(root) is None


def test_check_reads_the_overlay_project_layer_for_the_chosen_project_before_any_binding(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # No binding record names the project yet, so the overlay's project layer is read for the
    # project chosen here, or a `memory.mode` it sets would go unseen until a second attach. Its
    # `memory.groups` leaves the share, which only overlay mode asks about: `--check` refuses it as
    # the run would. Mutation: `mutations/`'s "attach reads no overlay project layer for the
    # project it chose".
    root, overlay, machine = _clone(tmp_path, origin="git@example.com:o/widget.git")
    (overlay / PROJECTS / "widget").mkdir(parents=True)
    (overlay / PROJECTS / "widget" / "stayfixed.toml").write_text(
        '[memory]\nmode = "overlay"\ngroups = ["../../escape"]\n', encoding="utf-8"
    )
    assert invoke(["attach", "--check", *_flags(root, machine)]) == 2
    assert "memory.groups" in capsys.readouterr().err
    (overlay / PROJECTS / "widget" / "stayfixed.toml").write_text(
        '[memory]\nmode = "overlay"\n', encoding="utf-8"
    )
    before = snapshot(root)
    assert invoke(["attach", "--check", *_flags(root, machine)]) == 0
    assert_snapshot_unchanged(root, before)
    assert invoke(["attach", *_flags(root, machine)]) == 0
    document = json.loads((root / SETTINGS).read_text(encoding="utf-8"))
    assert "autoMemoryDirectory" in document


def test_without_an_overlay_layer_the_mode_is_the_presets_and_no_pointer_is_written(
    tmp_path: Path,
) -> None:
    # The preset's `memory.mode` is `harness`: the plugin is delivered, and no note store is
    # composed or pointed at.
    root, _, machine = _clone(tmp_path, origin="git@example.com:o/widget.git")
    assert invoke(["attach", *_flags(root, machine)]) == 0
    document = json.loads((root / SETTINGS).read_text(encoding="utf-8"))
    assert "autoMemoryDirectory" not in document
    assert document["enabledPlugins"]


def test_attach_then_detach_leaves_a_repository_with_no_stayfixed_toml_as_it_was(
    tmp_path: Path,
) -> None:
    # The round trip through Claude Code's calls: `detach` reads no configuration, so a checkout
    # attached with no `stayfixed.toml` comes back byte for byte, and `git status` shows nothing at
    # either end.
    root, _, machine = _clone(tmp_path, origin="git@example.com:o/widget.git")
    before = snapshot(root)
    assert invoke(["attach", *_flags(root, machine)]) == 0
    assert_snapshot_changed(root, before)
    assert git(root, "status", "--porcelain", "-uall").strip() == ""
    assert invoke(["detach", *_flags(root, machine)]) == 0
    assert_snapshot_unchanged(root, before)
    assert git(root, "status", "--porcelain", "-uall").strip() == ""
