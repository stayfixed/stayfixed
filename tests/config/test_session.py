"""What a session runs on (`src/stayfixed/config/session.py`): the project's configuration read the
way a session must, the owner's layer, and one warning about each file it could not use whole.

`session_config` never raises for anything a repository or a machine file holds, so every case
below is a document a command refuses and a session reads anyway, or drops with a warning."""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path

import pytest

from stayfixed import __version__
from stayfixed.config.loader import NOTE_REMOVAL_LIMIT
from stayfixed.config.owner import resolve_owner
from stayfixed.config.session import (
    FALLBACK_WARNING,
    MACHINE_FILE_WARNING,
    NEWER_RELEASE_WARNING,
    NOTED_WARNING,
    TOO_MANY_WARNING,
    UNUSABLE_WARNING,
    session_config,
)
from stayfixed.doctor.checks import VERSION_AHEAD
from tests.config.test_loader import HEAD, MINIMAL

_MAJOR, _MINOR, _ = (int(part) for part in __version__.split(".")[:3])
# `HEAD` with a `version` one minor above the running one.
HEAD_LATER = HEAD.replace('version = "0.1.0"', f'version = "{_MAJOR}.{_MINOR + 1}.0"')


def write(root: Path, text: str) -> None:
    (root / "stayfixed.toml").write_text(text, encoding="utf-8")


def none(root: Path) -> Path:
    """A machine file that is not there: no owner's values but the preset's."""
    return root / "none.toml"


def broken_machine(root: Path) -> Path:
    path = root / "machine.toml"
    path.write_text("[personal\n", encoding="utf-8")
    return path


def unparseable(root: Path) -> None:
    write(root, "[[[")


def not_utf8(root: Path) -> None:
    (root / "stayfixed.toml").write_bytes(MINIMAL.encode("utf-8") + b"\xff\n")


def symlink_to_loadable(root: Path) -> None:
    (root / "real.toml").write_text(MINIMAL, encoding="utf-8")
    os.symlink(root / "real.toml", root / "stayfixed.toml")


def symlink_to_dev_zero(root: Path) -> None:
    os.symlink("/dev/zero", root / "stayfixed.toml")


def test_no_file_is_no_config_and_no_warning(tmp_path: Path) -> None:
    # No mutation of its own: nothing here is decided, the file is simply absent; the cases below
    # are what each arm reddens.
    got = session_config(tmp_path, machine=none(tmp_path))
    assert got.config is None and got.warnings == ()


def test_no_project_root_still_has_the_owners_layer(tmp_path: Path) -> None:
    # A hook with no project root runs the guards on the owner's layer all the same. Mutation
    # (`mutations/`'s "a session with no project root reads no machine file"): the guard is on.
    machine = tmp_path / "machine.toml"
    machine.write_text("[guards]\nbg_cleanup = false\n", encoding="utf-8")
    got = session_config(None, machine=machine)
    assert got.config is None and got.warnings == ()
    assert got.owner.guards.bg_cleanup is False


@pytest.mark.parametrize(
    "make",
    [unparseable, not_utf8, symlink_to_loadable, symlink_to_dev_zero],
    ids=lambda f: f.__name__,
)
def test_a_file_that_cannot_be_read_as_toml_falls_back_whole(
    tmp_path: Path, make: Callable[[Path], None]
) -> None:
    # A link meets the rule before anything follows it, so one to a loadable file and one to
    # `/dev/zero` get the same answer. Mutations (`mutations/`'s "a session lets a symlinked
    # stayfixed.toml raise" -> both links raise; "a session lets a file that is not TOML raise"
    # -> `unparseable` raises).
    make(tmp_path)
    got = session_config(tmp_path, machine=none(tmp_path))
    assert got.config is None and got.warnings == (FALLBACK_WARNING,)


def test_a_newer_release_keeps_every_other_setting(tmp_path: Path) -> None:
    # A `stayfixed.toml` a newer release wrote: an unknown section and an unknown enum value
    # together, and the raised budget beside them stands. Mutation (`mutations/`'s "session_config
    # answers no configuration for a file that loads with notes"): the budget goes with the file.
    write(
        tmp_path,
        HEAD_LATER + '[project]\nname = "p"\n[newer]\n[memory]\nmode = "harness"\n'
        "[budgets]\nagents_md_lines = 900\n",
    )
    got = session_config(tmp_path, machine=none(tmp_path))
    assert got.config is not None
    assert got.config.budgets.configured["agents_md_lines"] == 900
    assert got.warnings == (NEWER_RELEASE_WARNING.format(count=2),)
    # Mutation (`mutations/`'s "a session lists no key it noted"): `noted` is empty.
    assert got.noted == ("newer", "memory.mode")


def test_a_file_from_this_release_with_notes_is_not_called_newer(tmp_path: Path) -> None:
    # Mutation (`mutations/`'s "the session warns of a newer release for every file with notes"):
    # this one is called newer too.
    write(tmp_path, MINIMAL + '[memory]\nmode = "harness"\n')
    got = session_config(tmp_path, machine=none(tmp_path))
    assert got.config is not None
    assert got.warnings == (NOTED_WARNING.format(count=1),)


def test_the_newer_release_warning_gives_doctors_remedy() -> None:
    # One way out of a file a later release wrote, in both places that name it. No mutation: a
    # wording held equal across two constants.
    assert VERSION_AHEAD.split(":")[0] in NEWER_RELEASE_WARNING


def test_a_broken_machine_file_keeps_the_project(tmp_path: Path) -> None:
    # A machine file that is not TOML costs the session nothing of the project's, and is named.
    # Mutation (`mutations/`'s "a session says nothing of a machine file it could not use"): the
    # warning goes.
    write(tmp_path, MINIMAL)
    machine = broken_machine(tmp_path)
    got = session_config(tmp_path, machine=machine)
    assert got.config is not None
    assert got.warnings == (MACHINE_FILE_WARNING.format(path=machine),)


@pytest.mark.parametrize("root", ["no-file", "no-root"])
def test_a_broken_machine_file_is_named_with_no_project_configuration(
    tmp_path: Path, root: str
) -> None:
    # A machine file that is not TOML, with nothing of the project's to read: no `stayfixed.toml`,
    # or a hook with no project root. The guards still run on the preset's owner values, and the
    # warning still names the machine file. Mutation (`mutations/`'s "a session with no project
    # configuration says nothing of a machine file it could not use"): the warning goes.
    machine = broken_machine(tmp_path)
    got = session_config(tmp_path if root == "no-file" else None, machine=machine)
    assert got.config is None
    assert got.owner.guards.bg_cleanup is True
    assert got.owner.personal == resolve_owner(None).personal
    assert got.warnings == (MACHINE_FILE_WARNING.format(path=machine),)
    assert got.project_warnings == ()


@pytest.mark.parametrize("root", ["no-file", "no-root"])
def test_a_usable_machine_file_with_no_project_configuration_says_nothing(
    tmp_path: Path, root: str
) -> None:
    # The control for the case above: a machine file that loads whole is no warning. No mutation
    # of its own: the warning appearing here would be the case above's arm firing on every file.
    machine = tmp_path / "machine.toml"
    machine.write_text('[personal]\nreply_language = "fr"\n', encoding="utf-8")
    got = session_config(tmp_path if root == "no-file" else None, machine=machine)
    assert got.config is None and got.warnings == ()
    assert got.owner.personal.reply_language == "fr"


def test_both_broken(tmp_path: Path) -> None:
    # One warning about each file, the project's first. Mutation: as above, the machine file's
    # warning goes.
    unparseable(tmp_path)
    machine = broken_machine(tmp_path)
    got = session_config(tmp_path, machine=machine)
    assert got.config is None
    assert got.warnings == (FALLBACK_WARNING, MACHINE_FILE_WARNING.format(path=machine))
    assert got.project_warnings == (FALLBACK_WARNING,)


def _docs_symlink(root: Path) -> str:
    (root.parent / "outside").mkdir()
    os.symlink(root.parent / "outside", root / "docs")
    return MINIMAL


UNUSABLE = [
    pytest.param(
        lambda root: MINIMAL.replace('name = "sample"', 'name = "has space"'),
        "project.name",
        id="project-name",
    ),
    pytest.param(
        lambda root: MINIMAL.replace('version = "0.1.0"', "version = 1"),
        "stayfixed.version",
        id="version",
    ),
    pytest.param(_docs_symlink, "paths.architecture", id="docs-symlink"),
    pytest.param(lambda root: "project = 1\n" + HEAD, "project", id="project-not-a-table"),
]


def test_more_unusable_keys_than_the_note_path_reads_drop_the_project(tmp_path: Path) -> None:
    # One past `NOTE_REMOVAL_LIMIT`: the floor, with a warning in stayfixed's own words, and the
    # owner's layer still read. Mutation (`mutations/`'s "the NOTE path removes every key it cannot
    # use, however many"): the project loads with 65 notes.
    gates = "".join(f"g{n} = {{ run = [] }}\n" for n in range(NOTE_REMOVAL_LIMIT + 1))
    write(tmp_path, MINIMAL + "[gates.custom]\n" + gates)
    got = session_config(tmp_path, machine=none(tmp_path))
    assert got.config is None and got.warnings == (TOO_MANY_WARNING,)
    assert got.project_warnings == (TOO_MANY_WARNING,) and got.machine_warnings == ()


@pytest.mark.parametrize(("make", "key"), UNUSABLE)
def test_a_key_nothing_can_stand_in_for_drops_the_project_and_names_it(
    tmp_path: Path, make: Callable[[Path], str], key: str
) -> None:
    # A key nothing can stand in for drops the project configuration whole, and the warning
    # names the key the document got wrong, never one it calls missing. The owner's layer still
    # stands, so the guards run. Mutation (`mutations/`'s "a session names no key it could not
    # use"): the warning says "a setting".
    root = tmp_path / "root"
    root.mkdir()
    write(root, make(root))
    machine = root / "machine.toml"
    machine.write_text("[guards]\nbg_cleanup = false\n", encoding="utf-8")
    got = session_config(root, machine=machine)
    assert got.config is None
    assert got.warnings == (UNUSABLE_WARNING.format(key=key),)
    assert got.owner.guards.bg_cleanup is False


def test_a_required_key_the_document_never_wrote_drops_the_project_and_names_it(
    tmp_path: Path,
) -> None:
    # No `[project] name` at all: a command refuses the document whole, and a session still
    # goes on. Mutation (`mutations/`'s "a session names no key a document is missing"): the
    # warning says "a setting".
    write(tmp_path, HEAD)
    got = session_config(tmp_path, machine=none(tmp_path))
    assert got.config is None
    assert got.warnings == (UNUSABLE_WARNING.format(key="project.name"),)


@pytest.mark.parametrize("value", ['"future"', "1"], ids=["unshipped", "not-a-string"])
def test_a_preset_this_build_cannot_use_is_one_note(tmp_path: Path, value: str) -> None:
    # The loader resets the key with its note, and the owner's layer stands on the fallback
    # preset without a note of its own, which would have read as the machine file's fault.
    # Mutation (`mutations/`'s "the owner's layer is handed a preset the loader resets"): the
    # owner notes it too, and the machine file is blamed.
    write(tmp_path, MINIMAL.replace('preset = "recommended"', f"preset = {value}"))
    got = session_config(tmp_path, machine=none(tmp_path))
    assert got.config is not None and got.config.stayfixed.preset == "recommended"
    assert got.owner.notes == ()
    assert got.warnings == (NOTED_WARNING.format(count=1),)
