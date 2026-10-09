from __future__ import annotations

import ast
import errno
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from stayfixed import fsops
from stayfixed.fsops import (
    NEW_FILE_MODE,
    NotASymlink,
    NotRegularFile,
    UnsafePath,
    _mode_of,
    checked_components,
    mkdirs_within,
    names_control_directory,
    open_within,
    readlink_within,
    remove_within,
    rmdir_parents_within,
    rmdir_within,
    symlink_within,
    unlink_within,
    write_atomically,
    write_atomically_at,
    write_within,
)
from tests.pathfaults import LSTAT_FAULT, lstat_fault, shaped, unlock, unmet_here


def _umasked(mode: int = NEW_FILE_MODE) -> int:
    """`mode` as the kernel will actually create it under this process's umask.

    The suite must not assert `0o644` outright: forcing that mode is a defect of its own, and a
    test that pins the forced value passes only because the machine running it happens to use
    `umask 022`. Read once and restored immediately — `os.umask` is a set-and-return.
    """
    current = os.umask(0o077)
    os.umask(current)
    return mode & ~current


def test_a_new_file_is_written_with_the_default_mode(tmp_path: Path) -> None:
    target = tmp_path / "a" / "b.txt"
    write_atomically(target, "body\n")
    assert target.read_text(encoding="utf-8") == "body\n"
    assert stat.S_IMODE(target.stat().st_mode) == _umasked()


def test_a_new_file_does_not_override_the_umask(tmp_path: Path) -> None:
    # A trust record written under `umask 077` landed 0o644 — a world-readable security record
    # in `~/.config`, because the mode was forced onto the descriptor rather than requested of
    # the kernel. The machine owner's umask is a decision, not a default to be overridden.
    previous = os.umask(0o077)
    try:
        target = tmp_path / "private.json"
        write_atomically(target, "{}\n")
        assert stat.S_IMODE(target.stat().st_mode) == 0o600
    finally:
        os.umask(previous)


def test_an_existing_file_keeps_its_mode(tmp_path: Path) -> None:
    target = tmp_path / "b.txt"
    target.write_text("old\n", encoding="utf-8")
    os.chmod(target, 0o640)
    write_atomically(target, "new\n")
    assert target.read_text(encoding="utf-8") == "new\n"
    assert stat.S_IMODE(target.stat().st_mode) == 0o640


def test_no_temporary_file_survives(tmp_path: Path) -> None:
    write_atomically(tmp_path / "b.txt", "body\n")
    assert sorted(p.name for p in tmp_path.iterdir()) == ["b.txt"]


def test_a_failed_write_leaves_the_original_and_no_temporary(tmp_path: Path) -> None:
    target = tmp_path / "b.txt"
    target.write_text("original\n", encoding="utf-8")

    with pytest.raises(UnicodeEncodeError):
        write_atomically(target, "\udcff")
    assert target.read_text(encoding="utf-8") == "original\n"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["b.txt"]


# --- the descriptor walk, which had no coverage at all ---------------------------------------
#
# `open_within` is what the module leads with, and `write_atomically_at` is the sole write path
# of the scaffold engine. Neither was exercised by any test, which is how a call that raises
# NotImplementedError on Linux passed a green suite on macOS: the platform difference only
# shows where the code actually runs.


def test_a_symlinked_component_fails_the_open(tmp_path: Path) -> None:
    (tmp_path / "outside").mkdir()
    root = tmp_path / "root"
    root.mkdir()
    (root / "docs").symlink_to(tmp_path / "outside", target_is_directory=True)
    with pytest.raises(UnsafePath), open_within(root, "docs/a.md"):
        pass


def test_a_component_that_is_not_a_directory_fails_the_open(tmp_path: Path) -> None:
    (tmp_path / "docs").write_text("a file, not a directory\n", encoding="utf-8")
    with pytest.raises(UnsafePath), open_within(tmp_path, "docs/a.md"):
        pass


def test_a_path_that_names_nothing_fails_the_open(tmp_path: Path) -> None:
    with pytest.raises(UnsafePath), open_within(tmp_path, ""):
        pass


def test_a_write_through_the_descriptor_lands_where_the_walk_ended(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    with open_within(tmp_path, "docs/a.md") as (dir_fd, name):
        write_atomically_at(dir_fd, name, "body\n")
    assert (tmp_path / "docs" / "a.md").read_text(encoding="utf-8") == "body\n"
    assert stat.S_IMODE((tmp_path / "docs" / "a.md").stat().st_mode) == _umasked()


def test_a_descriptor_write_keeps_the_mode_of_the_file_it_replaced(tmp_path: Path) -> None:
    target = tmp_path / "a.md"
    target.write_text("old\n", encoding="utf-8")
    os.chmod(target, 0o640)
    with open_within(tmp_path, "a.md") as (dir_fd, name):
        write_atomically_at(dir_fd, name, "new\n")
    assert target.read_text(encoding="utf-8") == "new\n"
    assert stat.S_IMODE(target.stat().st_mode) == 0o640


def test_no_temporary_survives_a_descriptor_write(tmp_path: Path) -> None:
    with open_within(tmp_path, "a.md") as (dir_fd, name):
        write_atomically_at(dir_fd, name, "body\n")
    assert sorted(p.name for p in tmp_path.iterdir()) == ["a.md"]


def test_a_failed_descriptor_write_leaves_the_original_and_no_temporary(tmp_path: Path) -> None:
    target = tmp_path / "a.md"
    target.write_text("original\n", encoding="utf-8")
    with pytest.raises(UnicodeEncodeError), open_within(tmp_path, "a.md") as (dir_fd, name):
        write_atomically_at(dir_fd, name, "\udcff")
    assert target.read_text(encoding="utf-8") == "original\n"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["a.md"]


def test_a_symlinked_target_does_not_propagate_its_mode(tmp_path: Path) -> None:
    # `lstat` on a symlink reports 0o777. `contained()` refuses a symlink at the final
    # component before any caller reaches here, so this is a floor under a guard one caller
    # away — asserted because the guard and the floor live in different modules. `None` is
    # "carry nothing over", which is what sends the write down the umask path.
    (tmp_path / "elsewhere").write_text("x\n", encoding="utf-8")
    (tmp_path / "a.md").symlink_to(tmp_path / "elsewhere")
    fd = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        assert _mode_of(fd, "a.md") is None
    finally:
        os.close(fd)


def test_an_absent_file_carries_no_mode(tmp_path: Path) -> None:
    fd = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        assert _mode_of(fd, "missing.md") is None
    finally:
        os.close(fd)


# --- containment, which the twelve tests above did not test -----------------------------------
#
# The walk refused symlinks and nothing else. `PurePosixPath(relative).parts` keeps `..` and
# reports a leading `/` as its own first part, and `openat` ignores its `dir_fd` for an absolute
# path — so `open_within(root, "../outside/victim.txt")` handed back a descriptor outside the
# root, and an absolute argument restarted the walk at `/`. On Linux, where `/etc` and `/var` are
# real directories, the absolute case completed; macOS refused it only because those two happen
# to be symlinks there. Grepping this file for `..` or `absolute` used to return nothing, and
# that absence is why it survived.


def test_a_parent_component_never_leaves_the_root(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "victim.txt").write_text("mine\n", encoding="utf-8")
    root = tmp_path / "root"
    root.mkdir()
    with pytest.raises(UnsafePath), open_within(root, "../outside/victim.txt"):
        pass
    assert (outside / "victim.txt").read_text(encoding="utf-8") == "mine\n"


def test_a_parent_component_anywhere_along_the_path_is_refused(tmp_path: Path) -> None:
    # Not only as the first component: `docs/../../outside` is the same escape spelled longer,
    # and the loop that refuses it has to look at every part rather than at `parts[0]`.
    (tmp_path / "docs").mkdir()
    with pytest.raises(UnsafePath), open_within(tmp_path, "docs/../../outside/victim.txt"):
        pass


def test_a_component_holding_a_nul_is_refused(tmp_path: Path) -> None:
    # A NUL names no file on any system, and a path call meets it with `ValueError`, which no
    # caller of this rule catches: refused here, it is the `UnsafePath` every caller already turns
    # into its own refusal. Mutation (oracle): `mutations/`'s "a path component holding a NUL
    # passes the containment rule".
    with pytest.raises(UnsafePath):
        checked_components("memory/a\x00b")
    assert not (tmp_path / "memory").exists()


def test_an_absolute_path_is_refused(tmp_path: Path) -> None:
    # `os.open` ignores `dir_fd` for an absolute path, so without this the walk restarts at the
    # filesystem root. This is the case that succeeds on Linux, where CI runs.
    #
    # `match=` and not a bare `raises`: with the explicit check deleted an absolute path is
    # still refused, by the empty-first-component rule — `"/etc".split("/")` starts with `""`.
    # So the assertion has to be about the *reason*, or a later edit to that other rule takes
    # the absolute case with it silently. `mutations/`'s "the containment walk stops refusing an
    # absolute path by name" records this; the oracle found it.
    with pytest.raises(UnsafePath, match="absolute"), open_within(tmp_path, "/etc/passwd"):
        pass


def test_a_current_directory_component_is_refused(tmp_path: Path) -> None:
    # `PurePosixPath` normalises `.` away today, so this asserts the guard rather than the
    # parse: the normalisation is pathlib's implementation detail and this is the single place
    # every caller's containment rests on.
    with pytest.raises(UnsafePath):
        checked_components("docs/./a.md")


def test_gits_control_directory_is_reserved_at_every_depth_and_in_any_case() -> None:
    # Nothing reserved `.git`: the walk refused a symlink, `..`, an absolute path and an
    # empty component, and a control directory is none of those. Both halves of the rule are
    # asserted, because either alone is a rule a clone can spell its way past — the default
    # filesystem on macOS is case-insensitive, so `.GIT/hooks/pre-commit` reaches the same file,
    # and a `.git` below the top component is a submodule's control directory.
    #
    # Mutation (oracle): drop the `names_control_directory` check from `checked_components`.
    for target in (
        ".git",
        ".git/hooks/pre-commit",
        ".git/config",
        ".GIT/hooks/pre-commit",
        ".Git/config",
        "vendor/lib/.git/hooks/pre-commit",
        "a/b/.GIT",
    ):
        assert names_control_directory(target), target
        with pytest.raises(UnsafePath, match="control directory"):
            checked_components(target)


def test_the_reserved_name_is_the_component_and_not_a_leading_dot() -> None:
    # The rule this branch cannot have: `.github/workflows/` is an artifact it ships and
    # `.stayfixed/` holds the manifest, so refusing a leading dot would refuse stayfixed's own
    # footprint. And `.gitignore`, `.gitattributes` and `.gitkeep` are ordinary files that
    # merely start the same way, which an equality test on the whole component leaves alone.
    for target in (
        ".github/workflows/stayfixed.yml",
        ".stayfixed/manifest.json",
        ".gitignore",
        ".gitattributes",
        "docs/.gitkeep",
        "gitignore/x.md",
    ):
        assert not names_control_directory(target), target
        assert checked_components(target), target


def test_an_existing_git_hook_is_never_rewritten_in_place(tmp_path: Path) -> None:
    # The impact, end to end and at the primitive. The developer's own `pre-commit` is a real
    # executable file, and `_mode_of` carries an existing file's mode onto the replacement — so
    # before this rule, a write through here left a 0755 file with stayfixed's bytes appended to
    # somebody else's hook. Mode and body are both asserted, and both after the refusal.
    hooks = tmp_path / ".git" / "hooks"
    hooks.mkdir(parents=True)
    hook = hooks / "pre-commit"
    hook.write_text("#!/bin/sh\necho real hook\n", encoding="utf-8")
    hook.chmod(0o755)

    with pytest.raises(UnsafePath, match="control directory"):
        write_within(tmp_path, ".git/hooks/pre-commit", "#!/bin/sh\n<!-- stayfixed -->\n")
    assert hook.read_text(encoding="utf-8") == "#!/bin/sh\necho real hook\n"
    assert stat.S_IMODE(hook.stat().st_mode) == 0o755

    # And nothing new is created inside it either, which is the other half of what a clone got
    # to choose: an arbitrary file at an arbitrary name in git's own directory.
    with pytest.raises(UnsafePath, match="control directory"):
        write_within(tmp_path, ".git/stayfixed-roadmap.md", "# roadmap\n")
    assert sorted(p.name for p in (tmp_path / ".git").iterdir()) == ["hooks"]


# --- the reusable write surface ---------------------------------------------------------------


def test_write_within_creates_the_parents_and_lands_inside_the_root(tmp_path: Path) -> None:
    write_within(tmp_path, "a/b/c.txt", "body\n")
    assert (tmp_path / "a" / "b" / "c.txt").read_text(encoding="utf-8") == "body\n"


def test_write_within_refuses_an_escaping_target(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    with pytest.raises(UnsafePath):
        write_within(tmp_path / "root", "../outside/victim.txt", "PWNED\n")
    assert not (outside / "victim.txt").exists()


def test_mkdirs_within_refuses_a_symlinked_component_with_nothing_created(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    root = tmp_path / "root"
    root.mkdir()
    (root / "docs").symlink_to(outside, target_is_directory=True)
    with pytest.raises(UnsafePath):
        mkdirs_within(root, "docs/deep/a.md")
    assert list(outside.iterdir()) == []


def test_remove_within_unlinks_and_tolerates_an_absent_file(tmp_path: Path) -> None:
    (tmp_path / "a.md").write_text("body\n", encoding="utf-8")
    remove_within(tmp_path, "a.md")
    assert not (tmp_path / "a.md").exists()
    remove_within(tmp_path, "a.md")


def test_remove_within_refuses_an_escaping_target(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "victim.txt").write_text("mine\n", encoding="utf-8")
    with pytest.raises(UnsafePath):
        remove_within(tmp_path / "root", "../outside/victim.txt")
    assert (outside / "victim.txt").exists()


def test_rmdir_within_removes_an_empty_directory_and_tolerates_an_absent_one(
    tmp_path: Path,
) -> None:
    # The half `remove_within` cannot do: `unlink` on a directory is EPERM on macOS and EISDIR
    # on Linux, so a caller reaching for it got an OSError it was most likely already swallowing
    # and a tree that quietly never shrank.
    (tmp_path / "stale").mkdir()
    rmdir_within(tmp_path, "stale")
    assert not (tmp_path / "stale").exists()
    rmdir_within(tmp_path, "stale")


def test_rmdir_within_refuses_an_escaping_target(tmp_path: Path) -> None:
    # The same containment as its sibling, asserted separately: this walk is what stands between a
    # payload-controlled marker segment and an `rmdir` loop outside the hook sink's marker tree,
    # one of the two removals a listing drives (CONTRIBUTING.md#enumerated-writes), and a new
    # public name on this surface is read as that guarantee.
    outside = tmp_path / "outside"
    (outside / "victim").mkdir(parents=True)
    with pytest.raises(UnsafePath):
        rmdir_within(tmp_path / "root", "../outside/victim")
    assert (outside / "victim").is_dir()


def test_rmdir_parents_within_removes_each_empty_parent_and_never_the_root(tmp_path: Path) -> None:
    # A file a run removed can leave the directories above it empty, and git keeps no empty
    # directory, so they are noise in the tree and nothing else. The walk goes up from the file's
    # own directory and stops below the root: an empty root is the caller's, and what is above it
    # is nobody's business here, which no line of the walk could reach: `checked_components`
    # refuses the empty path the root would be.
    # Mutation (declared): the walk never starts -> the empty parents stay.
    outer = tmp_path / "outer"
    root = outer / "root"
    (root / "a" / "b" / "c").mkdir(parents=True)
    rmdir_parents_within(root, "a/b/c/gone.md")
    assert not (root / "a").exists()
    assert root.is_dir() and list(root.iterdir()) == []
    assert outer.is_dir()


def test_rmdir_parents_within_stops_at_the_first_directory_holding_anything(
    tmp_path: Path,
) -> None:
    # `rmdir` refuses a directory with anything in it, which is the whole safety of the walk: the
    # owner's file beside the one removed keeps its directory and every directory above it.
    # No mutation: what holds this is the kernel's refusal, not a line of the walk.
    (tmp_path / "a" / "b" / "c").mkdir(parents=True)
    (tmp_path / "a" / "b" / "mine.md").write_text("mine\n", encoding="utf-8")
    rmdir_parents_within(tmp_path, "a/b/c/gone.md")
    assert not (tmp_path / "a" / "b" / "c").exists()
    assert (tmp_path / "a" / "b" / "mine.md").read_text(encoding="utf-8") == "mine\n"


def test_rmdir_parents_within_leaves_a_symlinked_directory_and_what_it_points_at(
    tmp_path: Path,
) -> None:
    # A component that is a symlink, at the end of the walk or inside it, is never followed: a
    # link swapped in for a directory after its file was removed is left, and so is the empty
    # directory outside the root it points at.
    # Mutation (declared): the walk opens directories without `O_NOFOLLOW` -> the link inside it
    # is followed and the directory outside the root is removed. A link at the end of the walk is
    # refused by `rmdir` itself, which no line here can change.
    outside = tmp_path / "outside"
    (outside / "b").mkdir(parents=True)
    root = tmp_path / "root"
    (root / "a").mkdir(parents=True)
    (root / "a" / "b").symlink_to(outside / "b", target_is_directory=True)
    rmdir_parents_within(root, "a/b/gone.md")
    assert (root / "a" / "b").is_symlink()
    assert (outside / "b").is_dir()
    # And a link inside the walk: the walk to `a/b` refuses at `a`, so nothing past it is asked.
    (root / "a" / "b").unlink()
    (root / "a").rmdir()
    (root / "a").symlink_to(outside, target_is_directory=True)
    rmdir_parents_within(root, "a/b/gone.md")
    assert (root / "a").is_symlink()
    assert (outside / "b").is_dir()


def test_rmdir_parents_within_refuses_an_escaping_target(tmp_path: Path) -> None:
    # The target's own spelling is held to the walk's containment, as every name here is.
    # No mutation: the refusal is `checked_components`', held by that function's own entries.
    outside = tmp_path / "outside"
    (outside / "victim").mkdir(parents=True)
    with pytest.raises(UnsafePath):
        rmdir_parents_within(tmp_path / "root", "../outside/victim/gone.md")
    assert (outside / "victim").is_dir()


# --- durability -------------------------------------------------------------------------------


def test_the_bytes_are_fsynced_before_the_rename(tmp_path: Path) -> None:
    # `os.replace` gives rename atomicity, which is the important property and was already
    # achieved; it does not give durability. After power loss the rename can be durable while
    # the data is not, leaving exactly the zero-length note the module docstring opens by
    # promising to prevent. The order is what the assertion is about: the file descriptor is
    # synced while the temporary still exists, the directory after the name is in place.
    calls: list[str] = []
    real_fsync = os.fsync
    real_replace = os.replace

    def spy_fsync(fd: int) -> None:
        calls.append("fsync")
        real_fsync(fd)

    def spy_replace(*args: object, **kwargs: object) -> None:
        calls.append("replace")
        real_replace(*args, **kwargs)  # type: ignore[arg-type]

    monkey = pytest.MonkeyPatch()
    try:
        monkey.setattr(os, "fsync", spy_fsync)
        monkey.setattr(os, "replace", spy_replace)
        write_atomically(tmp_path / "a.md", "body\n")
    finally:
        monkey.undo()
    assert calls == ["fsync", "replace", "fsync"]


def test_a_directory_that_cannot_be_fsynced_does_not_fail_a_written_file(tmp_path: Path) -> None:
    # The data is on disk and the rename has happened by the time the directory is synced, so a
    # filesystem that answers EINVAL there has cost this call its durability guarantee and
    # nothing else. Raising would report a successful write as a failed one.
    import errno as _errno

    real_fsync = os.fsync
    seen: list[int] = []

    def flaky_fsync(fd: int) -> None:
        seen.append(fd)
        if len(seen) > 1:
            raise OSError(_errno.EINVAL, "fsync on a directory is not supported here")
        real_fsync(fd)

    monkey = pytest.MonkeyPatch()
    try:
        monkey.setattr(os, "fsync", flaky_fsync)
        write_atomically(tmp_path / "a.md", "body\n")
    finally:
        monkey.undo()
    assert (tmp_path / "a.md").read_text(encoding="utf-8") == "body\n"


def test_a_symlink_is_created_through_the_walk_and_never_through_a_symlinked_parent(
    tmp_path: Path,
) -> None:
    # `memory/worktree._link` created links with `Path.symlink_to` after a `Path.exists`
    # check, so a component swapped for a symlink between the two put the link wherever the
    # link pointed. The primitive walks with O_NOFOLLOW and creates through the directory
    # descriptor, so a symlinked parent is refused and nothing lands behind it.
    #
    # Mutation (declared): create with `os.symlink(str(source), root / target)` before the
    # walk -> the link appears under `elsewhere` and the last assertion reddens.
    root = tmp_path / "root"
    elsewhere = tmp_path / "elsewhere"
    (root / "notes").mkdir(parents=True)
    elsewhere.mkdir()
    (root / "notes" / "private").symlink_to(elsewhere)
    source = tmp_path / "store" / "developer"
    source.mkdir(parents=True)
    with pytest.raises(UnsafePath):
        symlink_within(root, "notes/private/developer", source)
    assert list(elsewhere.iterdir()) == []


def test_readlink_within_tells_absent_from_symlink_from_real(tmp_path: Path) -> None:
    # Three answers, because `_link` needs all three: nothing there (create), a link (compare
    # and maybe replace), a real entry (leave alone — "withdrawing a link is not licence to
    # delete a directory"). No mutation: each arm is one `lstat` branch, and the two callers'
    # tests below redden on the wrong answer.
    root = tmp_path / "root"
    root.mkdir()
    assert readlink_within(root, "absent") is None
    (root / "real").mkdir()
    with pytest.raises(NotASymlink):
        readlink_within(root, "real")
    (root / "link").symlink_to(tmp_path / "target")
    assert readlink_within(root, "link") == tmp_path / "target"


def test_unlink_within_removes_only_a_link_that_points_where_it_was_told(tmp_path: Path) -> None:
    # Mutation (declared): drop the `pointing_at` comparison -> the foreign link is removed
    # and the middle assertion reddens.
    root = tmp_path / "root"
    root.mkdir()
    (root / "real").mkdir()
    with pytest.raises(NotASymlink):
        unlink_within(root, "real")
    (root / "foreign").symlink_to(tmp_path / "theirs")
    assert unlink_within(root, "foreign", pointing_at=tmp_path / "ours") is False
    assert (root / "foreign").is_symlink()
    (root / "ours").symlink_to(tmp_path / "ours")
    assert unlink_within(root, "ours", pointing_at=tmp_path / "ours") is True
    assert not (root / "ours").is_symlink()
    assert unlink_within(root, "ours") is False


def test_a_name_is_utf_8_by_its_bytes_on_disk_not_by_its_str() -> None:
    # The predicate `docs trail` and `memory index` ask before writing a file's name into a
    # UTF-8 file: a latin-1 name decodes to surrogate escapes here, and writing one raised
    # `UnicodeEncodeError` in both. Mutation (declared): decode with `surrogateescape` -> the
    # second assertion reddens.
    assert fsops.utf_8_name(os.fsdecode(b"2026-04-04-caf\xc3\xa9.md"))
    assert not fsops.utf_8_name(os.fsdecode(b"2026-04-04-caf\xe9.md"))


def test_an_error_is_said_in_its_words_never_with_the_path_it_was_opened_by() -> None:
    # `str(OSError)` carries the file the call opened, by the path it was given — the absolute
    # one under this machine's layout — so an error is said by its `strerror` alone. stayfixed's
    # own path refusal, `UnsafePath`, carries no errno and names the path relative to the root,
    # so it is said whole rather than as its class's name. Mutation: drop the fall-back to
    # `str(error)` in `said` — the second assertion reddens.
    assert fsops.said(PermissionError(13, "Permission denied", "/machine/checkout/src/a.py")) == (
        "Permission denied"
    )
    refusal = "'src/x/a.py': 'x' is a symlink or not a directory"
    assert fsops.said(UnsafePath(refusal)) == refusal
    # Any other error with no file name is said as its class's name, never by its message, which
    # may carry a path: whole is for `UnsafePath` alone, by its type. Mutation: decide by
    # `error.filename is None` in `said` — this reddens.
    assert fsops.said(OSError("/machine/checkout/src/a.py: refused")) == "OSError"


def test_no_module_but_fsops_says_an_error_by_its_strerror() -> None:
    # One spelling for what an error says about a file, `fsops.said`. Private copies of it drifted
    # from it twice: two spelt it without its `UnsafePath` arm, and two fell back to the error's
    # whole message, the path it was opened by included. Any read of `.strerror` under `src/` is
    # such a copy, so the walk refuses every one but `said`'s own. Mutation (oracle):
    # `mutations/`'s "a reader spells the error's words again rather than saying them".
    source = Path(fsops.__file__).parent
    found = sorted(
        f"{path.relative_to(source).as_posix()}:{number}"
        for path in source.rglob("*.py")
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1)
        if ".strerror" in line
    )
    # The walk finds `said`'s own read, so a walk that stopped finding any cannot pass.
    assert len(found) == 1 and found[0].startswith("fsops.py:"), found


def test_a_path_names_a_regular_file_or_no_file_and_any_other_fault_is_the_callers(
    tmp_path: Path,
) -> None:
    # The probe `doctor`'s `hook-entries` walk and `attach`'s ledger reader share: a path that
    # names no file is `False` for both, and a path neither can ask about is raised, because one
    # calls it a file it is blind to and the other an unreadable ledger.
    regular = tmp_path / "regular"
    regular.write_text("{}", encoding="utf-8")
    assert fsops.names_regular_file(regular) is True
    # Followed through a link, as `Path.is_file()` follows it.
    (tmp_path / "to-regular").symlink_to(regular)
    assert fsops.names_regular_file(tmp_path / "to-regular") is True
    # Names no file: nothing there, a dangling link, a loop, a component that is not a directory,
    # and something that is not a regular file. Mutations (oracle): `mutations/`'s "hook-entries
    # is blind to a settings path that names no file" -> the first four raise; "hook-entries reads
    # a settings path that is no regular file" -> the directory answers `True`.
    (tmp_path / "dangling").symlink_to(tmp_path / "nothing-here")
    (tmp_path / "loop").symlink_to(tmp_path / "loop")
    (tmp_path / "directory").mkdir()
    for path in (
        tmp_path / "absent",
        tmp_path / "dangling",
        tmp_path / "loop",
        regular / "below-a-file",
        tmp_path / "directory",
    ):
        assert fsops.names_regular_file(path) is False, path
    # A link to a name longer than a file name may be is a path a clone can commit, and it is not
    # one that names no file: it is the caller's to classify. Mutation (oracle): `mutations/`'s
    # "the regular-file probe reads a path it cannot ask about as no file" -> `False`.
    (tmp_path / "past-a-name").symlink_to(tmp_path / ("x" * 300))
    with pytest.raises(OSError) as raised:
        fsops.names_regular_file(tmp_path / "past-a-name")
    assert raised.value.errno not in fsops.NAMES_NO_FILE


# What `is_file`, `is_dir`, `exists` and `is_symlink` answer for each shape, in that order, or
# `OSError` where all four raise.
PREDICATE_ANSWERS: dict[str, tuple[bool, bool, bool, bool] | type[OSError]] = {
    "a-regular-file": (True, False, True, False),
    "a-directory": (False, True, True, False),
    "a-link-to-a-file": (True, False, True, True),
    "a-link-to-a-directory": (False, True, True, True),
    "a-dangling-link": (False, False, False, True),
    "a-link-loop": (False, False, False, True),
    "a-link-to-a-name-longer-than-a-name": (False, False, False, True),
    "nothing-there": (False, False, False, False),
    "below-a-file": (False, False, False, False),
    "through-a-link-loop": (False, False, False, False),
    "a-name-longer-than-a-name": (False, False, False, False),
    "past-the-longest-path": (False, False, False, False),
    "through-a-link-to-a-name-longer-than-a-name": (False, False, False, False),
    "below-a-directory-that-cannot-be-searched": OSError,
    "through-a-link-into-a-directory-that-cannot-be-searched": OSError,
    "a-nul": (False, False, False, False),
}


@pytest.mark.parametrize("shape", sorted(LSTAT_FAULT))
def test_the_path_predicates_answer_each_fault_alike_on_every_interpreter(
    tmp_path: Path, shape: str
) -> None:
    # `Path.is_file()`, `is_dir()`, `exists()` and `is_symlink()` raise `ENAMETOOLONG` and
    # `EACCES` up to Python 3.13 and answer `False` for them from 3.14, so a path a clone shapes
    # was an internal error on one interpreter and "nothing there" on the other. `fsops` answers
    # one way on all of them: a name or a path longer than the system takes reaches nothing, as a
    # dangling link and a loop do, and a fault that leaves the question open raises.
    #
    # Mutations (oracle): `mutations/`'s "the path predicates read a name longer than the system
    # takes as a fault" -> the four `ENAMETOOLONG` shapes raise; "the path predicates read a fault
    # they cannot answer as nothing there" -> the unsearchable directory answers; "the path
    # predicates raise on a NUL" -> `a-nul`; and "is_file answers for anything that is there",
    # "is_dir answers for anything that is there", "exists answers for a link it did not follow"
    # and "is_symlink follows the link it is asked about".
    if unmet_here(shape):
        pytest.skip("root searches every directory")
    path = tmp_path / shaped(tmp_path, shape)
    try:
        # The shape meets the fault it is named for, or it proves nothing about that fault.
        assert lstat_fault(path) == LSTAT_FAULT[shape]
        expected = PREDICATE_ANSWERS[shape]
        asks = (fsops.is_file, fsops.is_dir, fsops.exists, fsops.is_symlink)
        if expected is OSError:
            for ask in asks:
                with pytest.raises(OSError) as raised:
                    ask(path)
                assert raised.value.errno == errno.EACCES
        else:
            assert tuple(ask(path) for ask in asks) == expected
    finally:
        unlock(tmp_path)


# The calls of `is_file`, `is_dir`, `exists` and `is_symlink` under `src/` that are not `fsops`'
# own, by file and function, and why each may stay. None asks `pathlib` about a path a repository
# can shape.
OTHER_PREDICATES: dict[tuple[str, str, str], tuple[int, str]] = {
    ("areas.py", "_has_submodule", "is_file"): (2, "the package's own directory"),
    ("overlay/template.py", "templates", "is_dir"): (1, "the wheel's own template tree"),
    ("project/templates.py", "read", "is_dir"): (1, "the wheel's own template tree"),
    ("profiles/__init__.py", "shipped", "is_dir"): (1, "a resource of the package's own"),
    ("profiles/__init__.py", "shipped", "is_file"): (1, "a resource of the package's own"),
    ("profiles/__init__.py", "load_profile", "is_file"): (1, "a resource of the package's own"),
    ("profiles/hints.py", "hint_modules", "is_file"): (1, "a resource of the package's own"),
    # `os.DirEntry`'s, which answers alike on every interpreter.
    ("doctor/hooked.py", "_nested", "is_dir"): (1, "an os.DirEntry"),
    ("doctor/hooked.py", "_nested", "is_symlink"): (1, "an os.DirEntry"),
    ("profiles/python/hygiene.py", "_bytecode", "is_dir"): (1, "an os.DirEntry"),
}


def test_no_module_asks_pathlib_what_is_at_a_path_a_repository_can_shape() -> None:
    # `Path.is_file()`, `is_dir()`, `exists()` and `is_symlink()` raise on a name longer than the
    # system takes, and on a directory that cannot be searched, up to Python 3.13, and answer
    # `False` from 3.14, so the suite passing on one interpreter said nothing about the other:
    # `attach` over a deep checkout was an internal error on 3.11 to 3.13 and attached on 3.14.
    # `fsops` answers one way on all of them, so the walk refuses any other call of the four but
    # the ones `OTHER_PREDICATES` names, each on a path no repository writes. Mutation (oracle):
    # `mutations/`'s "the harness link's check asks pathlib what is there".
    source = Path(fsops.__file__).parent
    found: dict[tuple[str, str, str], int] = {}
    for path in sorted(source.rglob("*.py")):
        relative = path.relative_to(source).as_posix()
        if relative == "fsops.py":
            continue
        # Each call by the definitions around it, `Class.method` for a method, so a call in a
        # class body or at module level is a row too.
        scopes: list[tuple[ast.AST, str]] = [(ast.parse(path.read_text(encoding="utf-8")), "")]
        while scopes:
            scope, name = scopes.pop()
            for node in ast.iter_child_nodes(scope):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    scopes.append((node, f"{name}.{node.name}" if name else node.name))
                    continue
                scopes.append((node, name))
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr in ("is_file", "is_dir", "exists", "is_symlink")
                    and not (
                        isinstance(node.func.value, ast.Name) and node.func.value.id == "fsops"
                    )
                ):
                    key = (relative, name or "<module>", node.func.attr)
                    found[key] = found.get(key, 0) + 1
    assert found == {key: count for key, (count, _) in OTHER_PREDICATES.items()}


def test_a_regular_file_is_read_through_a_link_and_anything_else_is_refused(
    tmp_path: Path,
) -> None:
    # The readers of `*.md` a repository commits followed a committed link to whatever it named:
    # `/dev/zero` grew `bugs check` to 9 GB in 2 s, and `/dev/stdin` or a FIFO waited forever.
    # A link to a regular file is still read, because `attach` links each memory group and
    # `MEMORY.md` into the overlay; a link to `/dev/null` is refused, and it is the case that tells
    # the guard apart without being able to hang: unguarded, it reads as empty. Mutation
    # (declared): the regular-file check before the open dropped -> `/dev/null` reads as b"".
    regular = tmp_path / "regular.md"
    regular.write_bytes(b"a\r\nb\n")
    (tmp_path / "to-regular.md").symlink_to(regular)
    with fsops.open_regular(tmp_path / "to-regular.md") as stream:
        assert stream.read() == b"a\r\nb\n"
    assert fsops.read_regular_text(regular, newline="") == "a\r\nb\n"
    assert fsops.read_regular_text(regular) == "a\nb\n"
    assert fsops.read_regular_bytes(tmp_path / "to-regular.md") == b"a\r\nb\n"
    (tmp_path / "null.md").symlink_to("/dev/null")
    (tmp_path / "directory.md").mkdir()
    for path in (tmp_path / "null.md", tmp_path / "directory.md"):
        with pytest.raises(NotRegularFile) as refused:
            fsops.open_regular(path)
        assert isinstance(refused.value, OSError)
        assert refused.value.strerror == "not a regular file"


def test_a_file_swapped_after_the_check_is_judged_by_what_was_opened(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The check before the open names a path, and a path can be repointed between the two: what
    # is read is judged again by its descriptor, and must be the file that was checked, whatever
    # was put there instead. Mutation (declared): the descriptor's own check dropped -> the
    # swapped-in file is read.
    regular = tmp_path / "regular.md"
    regular.write_bytes(b"x")
    (tmp_path / "other.md").write_bytes(b"y")
    real_open = os.open

    def swapping_open(path: str | Path, flags: int, *args: int) -> int:
        return real_open(tmp_path / "other.md", flags, *args)

    monkeypatch.setattr(os, "open", swapping_open)
    with pytest.raises(NotRegularFile):
        fsops.open_regular(regular)


def test_a_fifo_is_refused_without_waiting_for_a_writer(tmp_path: Path) -> None:
    # A FIFO cannot be committed, but a local process can leave one where a reader globs, and an
    # open for reading waits for a writer that never comes. Run in a child under a timeout, so a
    # regression fails this case rather than hanging the suite.
    fifo = tmp_path / "pipe.md"
    os.mkfifo(fifo)
    probe = (
        "import sys\n"
        "from pathlib import Path\n"
        "from stayfixed import fsops\n"
        "try:\n"
        "    fsops.open_regular(Path(sys.argv[1]))\n"
        "except fsops.NotRegularFile:\n"
        "    print('refused')\n"
    )
    done = subprocess.run(
        [sys.executable, "-c", probe, str(fifo)],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert done.stdout == "refused\n", done.stderr


def test_a_fifo_swapped_in_after_the_check_is_refused_without_waiting(tmp_path: Path) -> None:
    # The check before the open is about a path, which a local process can repoint at a FIFO in
    # between: the open must not wait on a writer that never comes, and the descriptor is then
    # refused as not the file that was checked. In a child under a timeout, so a regression fails
    # this case rather than hanging. Mutation (declared): `O_NONBLOCK` dropped from the open ->
    # the child waits and this times out.
    regular = tmp_path / "regular.md"
    regular.write_bytes(b"x")
    fifo = tmp_path / "pipe.md"
    os.mkfifo(fifo)
    probe = (
        "import os, sys\n"
        "from pathlib import Path\n"
        "from stayfixed import fsops\n"
        "real = os.open\n"
        "os.open = lambda path, flags, *rest: real(sys.argv[2], flags, *rest)\n"
        "try:\n"
        "    fsops.open_regular(Path(sys.argv[1]))\n"
        "except fsops.NotRegularFile:\n"
        "    print('refused')\n"
    )
    try:
        done = subprocess.run(
            [sys.executable, "-c", probe, str(regular), str(fifo)],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except subprocess.TimeoutExpired:
        pytest.fail("the open waited on the FIFO swapped in after the check")
    assert done.stdout == "refused\n", done.stderr


def test_a_regular_file_past_the_read_limit_is_refused_and_one_at_it_is_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A regular file can be endless: on Linux `/proc/self/pagemap` is `S_ISREG` with a size of 0
    # and reads on for as long as anyone asks, so the read stops one byte past the limit and
    # refuses a file that has it. The limit lowered here, so a file at it and one past it are
    # cheap. Mutations (declared): `mutations/`'s "the regular-file reader reads past its limit" ->
    # the longer file is read; "the regular-file reader refuses a file at its limit" -> the shorter
    # is not.
    monkeypatch.setattr(fsops, "REGULAR_READ_LIMIT", 4)
    (tmp_path / "at.md").write_bytes(b"abcd")
    (tmp_path / "past.md").write_bytes(b"abcde")
    assert fsops.read_regular_bytes(tmp_path / "at.md") == b"abcd"
    with pytest.raises(fsops.TooLarge) as refused:
        fsops.read_regular_bytes(tmp_path / "past.md")
    assert isinstance(refused.value, OSError)
    assert refused.value.strerror == "larger than this reader reads"


def test_the_read_limit_sits_far_above_every_file_its_readers_take() -> None:
    # The legitimate readers' files are a few kilobytes -- `MEMORY.md`'s own budget is 25,600
    # bytes -- so the bound must be far above them and still far under a machine's memory.
    assert 1024 * 1024 <= fsops.REGULAR_READ_LIMIT <= 1024 * 1024 * 1024


def test_a_bounded_read_returns_what_fits_and_says_whether_more_is_there(tmp_path: Path) -> None:
    # One reader for every bound: a file at the bound is read whole and is not over, one a byte
    # longer is read to the bound and is, with or without a root. Mutations (declared):
    # `mutations/`'s "the regular-file reader reads past its limit" -> the longer file is not over;
    # "the regular-file reader refuses a file at its limit" -> the file at the bound is.
    (tmp_path / "at.md").write_bytes(b"abcd")
    (tmp_path / "past.md").write_bytes(b"abcde")
    for at, past in (
        (fsops.read_bounded(tmp_path / "at.md", 4), fsops.read_bounded(tmp_path / "past.md", 4)),
        (
            fsops.read_bounded_within(tmp_path, "at.md", 4),
            fsops.read_bounded_within(tmp_path, "past.md", 4),
        ),
    ):
        assert at == (b"abcd", False)
        assert past == (b"abcd", True)


def test_a_bounded_read_under_a_root_follows_no_link_and_reads_only_a_regular_file(
    tmp_path: Path,
) -> None:
    # Under a root the file is reached as a write reaches it: a link at the last component is
    # refused, and so is one above it, where without a root a link to a regular file is read. A
    # directory is refused as not a regular file. Mutation (declared): `mutations/`'s "a symlinked
    # .pyc is followed" -> the linked file is read under the root.
    (tmp_path / "real").mkdir()
    (tmp_path / "real" / "file.md").write_bytes(b"x")
    (tmp_path / "real" / "link.md").symlink_to(tmp_path / "real" / "file.md")
    (tmp_path / "linked").symlink_to(tmp_path / "real", target_is_directory=True)
    assert fsops.read_bounded_within(tmp_path, "real/file.md", 4) == (b"x", False)
    assert fsops.read_bounded(tmp_path / "real" / "link.md", 4) == (b"x", False)
    with pytest.raises(OSError) as refused:
        fsops.read_bounded_within(tmp_path, "real/link.md", 4)
    assert refused.value.errno == errno.ELOOP
    with pytest.raises(UnsafePath):
        fsops.read_bounded_within(tmp_path, "linked/file.md", 4)
    with pytest.raises(NotRegularFile):
        fsops.read_bounded_within(tmp_path, "real", 4)


def test_a_fifo_under_a_root_is_refused_without_waiting_for_a_writer(tmp_path: Path) -> None:
    # The open under a root never waits, and what it opened is asked whether it is a regular file:
    # a FIFO opened without a writer reads as empty, so it must be refused by its descriptor. In a
    # child under a timeout, so a regression fails this case rather than hanging. Mutations
    # (declared): `mutations/`'s "a .pyc that is a named pipe is opened waiting for a writer" -> the
    # child times out; "a .pyc that is not a regular file is read" -> the FIFO reads as empty.
    os.mkfifo(tmp_path / "pipe.md")
    probe = (
        "import sys\n"
        "from pathlib import Path\n"
        "from stayfixed import fsops\n"
        "try:\n"
        "    print(fsops.read_bounded_within(Path(sys.argv[1]), 'pipe.md', 4))\n"
        "except fsops.NotRegularFile:\n"
        "    print('refused')\n"
    )
    try:
        done = subprocess.run(
            [sys.executable, "-c", probe, str(tmp_path)],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except subprocess.TimeoutExpired:
        pytest.fail("the open under a root waited on a FIFO")
    assert done.stdout == "refused\n", done.stderr


def test_a_bounded_read_under_an_open_directory_takes_one_name_and_follows_no_link(
    tmp_path: Path,
) -> None:
    # A reader of many files in one directory opens it once (`open_directory`) and reads each
    # name under it, by the same rules as under a root path: one name and no path below it, no
    # link followed, a regular file only. Mutation (declared): `mutations/`'s "a name under an open
    # directory may be a path" -> the file below a subdirectory is read.
    (tmp_path / "file.md").write_bytes(b"abcde")
    (tmp_path / "link.md").symlink_to(tmp_path / "file.md")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "file.md").write_bytes(b"x")
    with fsops.open_directory(tmp_path) as directory:
        assert fsops.read_bounded_within(directory, "file.md", 4) == (b"abcd", True)
        assert fsops.read_bounded_within(directory, "file.md", 5) == (b"abcde", False)
        with pytest.raises(OSError) as refused:
            fsops.read_bounded_within(directory, "link.md", 4)
        assert refused.value.errno == errno.ELOOP
        with pytest.raises(UnsafePath):
            fsops.read_bounded_within(directory, "sub/file.md", 4)
        with pytest.raises(NotRegularFile):
            fsops.read_bounded_within(directory, "sub", 4)
