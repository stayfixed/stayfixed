from __future__ import annotations

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
    # is blind to a settings path that names no file" raises for the first four, and "hook-entries
    # reads a settings path that is no regular file" answers `True` for the directory.
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
    with fsops.open_regular(regular, "r", encoding="utf-8", newline="") as stream:
        assert stream.read() == "a\r\nb\n"
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
