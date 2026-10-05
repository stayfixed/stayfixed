"""One writer for every file stayfixed replaces in place, and one way to reach it safely.

Two problems, one module.

*Atomicity, and durability.* A note, an index and a scaffolded artifact are each a file a
person may be editing, and a bare `write_text` truncates before it writes: a crash in between
leaves an empty file where the only copy of a note was. `mkstemp` plus `os.replace` makes the
replacement atomic, and the mode of the replaced file is carried over, because a fresh
temporary is 0600 and silently tightening `.gitignore`, `AGENTS.md` or a workflow file is a
defect of its own. Atomicity is not durability, and the crash argument above asks for both:
`os.replace` guarantees that a reader sees the old file or the new one and never a half-written
one, and guarantees nothing about what survives power loss. So the bytes are `fsync`ed before
the rename and the directory is `fsync`ed after it — without the first, the rename can be
durable while the data is not, which is the zero-length note this module exists to prevent.

*Containment that survives the write.* Validating a path string and then writing to it leaves
a window in which a component can become a symlink, and the clone may be running a process of
its own. `open_within` walks the path one component at a time with `O_NOFOLLOW`, so a symlink
anywhere along it fails the open rather than redirecting it, and returns a directory
descriptor the write then happens relative to. The string is never resolved again.

**`open_within` contains, and the name is the contract.** The walk refuses symlinks; for a
while it refused nothing else, so `..` walked out of the root one component at a time and an
absolute `relative` restarted the walk at `/` — `openat` ignores its `dir_fd` for an absolute
path. On Linux, where `/etc` and `/var` are real directories, that completed and yielded a
descriptor outside the root; macOS refused it only incidentally, because those two happen to
be symlinks there. No caller reached it — `scaffold.engine` calls `contained()` first — but
the seam is the point: every area that puts a file into a repository calls it instead of writing
files of its own, and the name of this function is what those callers read as the guarantee. It
is the guarantee now.

`contained()` in `config.paths` is still the right first call for a *configured* string: it
answers about the project root, reports a `Refusal` a user can act on, and catches a committed
symlink before any descriptor is opened. This is the floor under it, not a replacement for it.

A leaf module: it imports nothing from `stayfixed`, so the hook path pays no area import to
reach it. That is also why the write helpers below raise `OSError` and `UnsafePath` rather
than `stayfixed.errors.Refusal` — the area that owns a user-facing verdict translates them.
"""

from __future__ import annotations

import contextlib
import errno
import os
import stat
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

# The mode a file stayfixed creates asks for. It is a request, not a decision: the temporary is
# created with it and the kernel subtracts the process umask, exactly as `open()` does for any
# other program. Forcing it with `fchmod` — which this module did — wrote a world-readable
# `trust.json` into `~/.config` under `umask 077`, overriding a choice the machine owner had
# made deliberately. A file that already exists keeps its own mode instead; see `_mode_of`.
NEW_FILE_MODE = 0o644
_DIR_FLAGS = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
_PARENT = ".."
_HERE = "."
# Git's control directory, reserved at every depth and in any case.
#
# **Where the anchor comes from.** The rule is "no component of a path *relative to a root* may
# be git's control directory", and the root is the checkout a person handed the CLI — resolved
# by `project.detect`, or passed on the command line. `.git` is git's own name inside that
# root. So the party being contained is the clone, which authors the path string and can author
# nothing else here: it cannot move `.git`, cannot choose the root, and cannot rename the
# directory out from under this check.
#
# **Case-insensitively**, because the default filesystem on macOS is case-insensitive and
# `.GIT/hooks/pre-commit` reaches the same file there; **at every depth**, because a `.git`
# below the top is a submodule's control directory and is exactly as off-limits.
#
# **`.git` and not "a leading dot".** `.github/workflows/stayfixed.yml` is an artifact this
# project ships and `.stayfixed/manifest.json` is its own ledger, so a leading-dot rule would
# refuse stayfixed's own footprint. `.gitignore`, `.gitattributes` and `.gitkeep` are ordinary
# files and are untouched by an equality test on the whole component.
#
# The one place stayfixed does write inside `.git` is `guards.githooks.install`, and it does not
# come through here: git itself names the directory (`rev-parse --git-path hooks`), the result
# is an absolute path this process computed, and the write is `write_atomically`, the plain-path
# form for a caller that already holds a trusted path. No repository-authored string reaches it.
CONTROL_DIRECTORY = ".git"


class UnsafePath(OSError):
    """A component of the path is a symlink, is not a directory, or leaves the root."""


def said(error: OSError) -> str:
    """What an `OSError` says about a file without naming it: `str(error)` carries the path as it
    was opened — the absolute one, under this machine's own layout — so a report that names the
    file relative to the root says the error beside it as its `strerror`, or its class's name.

    `UnsafePath` alone is said whole, decided by its type: it is stayfixed's own refusal, raised
    with a message and no errno, and the message names the path relative to the root. Any other
    error's message may carry a path, whether or not it has a file name."""
    if isinstance(error, UnsafePath):
        return str(error)
    return error.strerror or type(error).__name__


def path_key(relative: str) -> str:
    """The form in which two root-relative paths are compared for identity: case-folded.

    The default filesystems on macOS and Windows fold case, so `claude.md` and `CLAUDE.md` are
    one file there, and a rule that asks "is this the same file" by exact string equality answers
    no for a pair the disk answers yes for. It is a pure string rule, the same on every
    filesystem, so a case-sensitive machine refuses and withholds exactly what a folding one
    must, and the tests that hold it redden on Linux too. Where a comparison must stay exact (a
    `--force` path, an exemption that only relaxes a guard), its caller says why.
    """
    return relative.casefold()


def names_component(relative: str, name: str) -> bool:
    """Whether any component of `relative` is `name`, spelled in any case.

    The one test behind `names_control_directory` and `config.paths.names_stayfixed_directory`:
    at any depth, and in any case, because the default filesystems on macOS and Windows fold
    case and `.GIT` or `.stayfixed` reaches the same directory there. `name` is lower-case.
    """
    return any(part.lower() == name for part in relative.split("/"))


def names_control_directory(relative: str) -> bool:
    """Whether any component of `relative` is git's control directory, spelled in any case.

    Public and separate from the walk, because two callers need the same answer and must not
    each write their own version of it: `checked_components` refuses on it, and
    `config.paths.validate_paths` asks it a key at a time so its refusal can name the key
    without printing the repository-authored value. See `CONTROL_DIRECTORY` for the rule and
    for where its anchor comes from.
    """
    return names_component(relative, CONTROL_DIRECTORY)


def utf_8_name(name: str) -> bool:
    """Whether a name the filesystem gave is UTF-8 on disk, so a UTF-8 file can hold it.

    A name held in other bytes — latin-1, on Linux — reaches Python with surrogate escapes, and
    writing it into a UTF-8 file raises `UnicodeEncodeError`, which would end `docs trail`,
    `memory index` or `attach` as an internal error. The bytes are asked and not the `str`,
    because under a latin-1 filesystem codec every byte decodes and the escapes that would show
    it never appear.
    """
    try:
        os.fsencode(name).decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


# The faults of a `stat` that say its path names no file: nothing there, a component that is not
# a directory, a symbolic link loop. `Path.is_file()` answers `False` for these, raises most other
# faults up to Python 3.13 and answers `False` for any from 3.14, and neither will do for a path a
# clone can commit. A symbolic link to a name longer than a file name may be raises `ENAMETOOLONG`:
# raised past a caller's catch, it costs a `doctor` row its verdict, so an entry nothing vouches for
# loses its red beside it; answered `False`, it skips a file that is there. So `stat` is asked,
# these three are no file, and any other fault is a file the caller cannot read.
NAMES_NO_FILE = frozenset({errno.ENOENT, errno.ENOTDIR, errno.ELOOP})


def names_regular_file(path: Path) -> bool:
    """Whether `path`, followed through symbolic links, names a regular file.

    `False` when it names no file — one of `NAMES_NO_FILE`, or something other than a regular
    file, such as a directory — and any other `OSError` raised, because what a path that cannot
    be asked about means is the caller's to say: a reader that must account for every file calls
    it one it is blind to, and one reading a record a clone can commit calls the record unreadable.
    """
    try:
        mode = path.stat().st_mode
    except OSError as exc:
        if exc.errno in NAMES_NO_FILE:
            return False
        raise
    return stat.S_ISREG(mode)


def checked_components(relative: str) -> tuple[str, ...]:
    """The path's components, or `UnsafePath` for any spelling that could leave the root.

    **Public, and the one place this rule lives.** `config.paths.contained()` used to carry a
    second copy of it, written against `Path(relative).parts` — and the two agreed only about
    the values nobody had to think about. Those parts are normalised, so `docs//x.md`,
    `docs/x/` and `./docs` reached `contained()` as `('docs', 'x.md')`, `('docs', 'x')` and
    `('docs',)`: a configured path that `plan()` reported no refusal for and that the walk below
    then refused at the write, part-way through a pass, with earlier artifacts already on disk.
    Two spellings of one rule is the defect; there is one spelling now, and `contained()` calls
    it. That is also why this is not private: `contained()` is in a subpackage and this is a
    leaf module, so the call goes this way and the leaf stays a leaf.

    The split is on the **raw string**, not on `PurePosixPath(relative).parts`. Those parts are
    already normalised — `.` and empty segments are dropped, a trailing slash disappears — so a
    guard written against them can only ever see what pathlib chose to keep, and the one
    component it does keep is the one that escapes. Reading the caller's own spelling means
    every refusal below is a refusal of something a caller can actually write:

    * the empty path, and any path that is only separators;
    * an absolute path — `openat` ignores its `dir_fd` for one, so the walk would restart at
      the filesystem root;
    * `..`, which walks out one component at a time; and `.`, and an empty segment (`a//b`, a
      trailing slash), which are merely odd rather than dangerous — refused because this
      function's answer is what every caller reads as "contained", and a surface that quietly
      rewrites its argument is a surface whose guarantee has to be restated per caller;
    * and git's control directory, at any depth and in any case — see `CONTROL_DIRECTORY`.
      Staying inside the root is not the whole of containment for a repository-scoped tool:
      `.git/hooks/pre-commit` is inside every root stayfixed is ever handed, and a clone that
      pointed a `MANAGED_REGION` artifact at it had the developer's executable hook rewritten
      in place, because `_mode_of` carries an existing file's 0755 onto the replacement. This
      is the last line before the write, under `contained()` rather than instead of it, and it
      covers the callers that never had a configured string to check — `attach`, `overlay` and
      `hooks` all pass paths that `contained()` never sees.
    """
    if relative.startswith("/"):
        raise UnsafePath(f"{relative!r} is absolute; a path here must stay inside the root")
    if not relative:
        raise UnsafePath(f"{relative!r} names no file")
    parts = tuple(relative.split("/"))
    for part in parts:
        if part == "":
            raise UnsafePath(f"{relative!r} has an empty path component")
        if part in (_PARENT, _HERE):
            raise UnsafePath(
                f"{relative!r} contains {part!r}; a path here must stay inside the root"
            )
    if names_control_directory(relative):
        raise UnsafePath(
            f"{relative!r} names {CONTROL_DIRECTORY!r}; git's control directory is not a "
            "repository-scoped tool's to write into"
        )
    return parts


@contextmanager
def open_within(root: Path, relative: str) -> Iterator[tuple[int, str]]:
    """Yield `(directory descriptor, final name)` for `root/relative`, following no symlink.

    The caller writes through the descriptor, so nothing between this walk and the write can
    redirect it: `os.replace(..., src_dir_fd=fd, dst_dir_fd=fd)` never re-resolves the parent.

    `relative` must stay inside `root` by its own spelling — see `checked_components`.
    """
    parts = checked_components(relative)
    fd = os.open(root, _DIR_FLAGS)
    opened = [fd]
    try:
        for part in parts[:-1]:
            try:
                nxt = os.open(part, _DIR_FLAGS, dir_fd=fd)
            except OSError as exc:
                # O_NOFOLLOW on a symlink reports ELOOP on Linux and ENOTDIR on macOS when the
                # link points at a directory; both mean the same thing here.
                if exc.errno in (errno.ELOOP, errno.ENOTDIR):
                    raise UnsafePath(
                        f"{relative!r}: {part!r} is a symlink or not a directory"
                    ) from exc
                raise
            opened.append(nxt)
            fd = nxt
        yield fd, parts[-1]
    finally:
        for handle in reversed(opened):
            os.close(handle)


def check_within(root: Path, relative: str) -> None:
    """Walk to `root/relative` as every write and removal here does, and touch nothing.

    For a caller that must know before its first write whether a later one would be refused: it
    raises the same `UnsafePath` the write or removal would, from the same walk, so the two cannot
    disagree about which components count. A component that is not there is not an error, since
    a removal through it has nothing to remove.
    """
    with contextlib.suppress(FileNotFoundError), open_within(root, relative):
        pass


def _mode_of(dir_fd: int, name: str) -> int | None:
    """The mode to carry over, and `None` for a file that is not there to carry one.

    `None` rather than `NEW_FILE_MODE` so the caller can tell "keep this file's mode" from
    "this is a new file": the second is the case the umask gets to decide, and answering it
    with a number made the two indistinguishable.

    `lstat` on a symlink reports `0o777`, and carrying that onto the replacement would make it
    world-writable. `contained()` refuses a symlink at the final component before any caller
    here runs, so this is a floor under a guard that lives in another module — one caller
    away, and not one this module can see.
    """
    try:
        info = os.stat(name, dir_fd=dir_fd, follow_symlinks=False)
    except FileNotFoundError:
        return None
    return stat.S_IMODE(info.st_mode) if stat.S_ISREG(info.st_mode) else None


def _sync_directory(dir_fd: int) -> None:
    """Make the rename itself durable, and never fail a completed write because it was not.

    The data is already on disk by the time this runs and the rename has already happened, so
    a filesystem that refuses `fsync` on a directory (some do, with EINVAL) has cost this call
    its durability guarantee and nothing else. Raising here would turn a successful write into
    an exception the caller would report as a failed one.
    """
    with contextlib.suppress(OSError):
        os.fsync(dir_fd)


def write_atomically_at(
    dir_fd: int, name: str, text: str, *, encoding: str = "utf-8", errors: str = "strict"
) -> None:
    """Replace `name` inside the already-opened directory, keeping the mode it had.

    `errors` is the codec's: `surrogateescape` writes back the bytes a file was read with under
    the same handler, for a caller that must keep bytes that are not UTF-8 exactly."""
    mode = _mode_of(dir_fd, name)
    temporary = f".stayfixed-{os.getpid()}-{name}.tmp"
    create = NEW_FILE_MODE if mode is None else 0o600
    handle = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, create, dir_fd=dir_fd)
    try:
        with os.fdopen(handle, "w", encoding=encoding, errors=errors) as stream:
            stream.write(text)
            if mode is not None:
                # `os.fchmod` on the descriptor rather than
                # `os.chmod(..., follow_symlinks=False)`. The temporary was just created
                # O_CREAT|O_EXCL, so it cannot be a symlink and the flag bought nothing; and
                # that form is accepted only where `os.chmod in os.supports_follow_symlinks`,
                # which is a runtime property of the platform rather than a guarantee. Setting
                # the mode on the open descriptor needs no such support and closes the
                # create-to-chmod window. A *new* file is not chmod-ed at all: it was created
                # with `NEW_FILE_MODE` and the kernel has already applied the umask to it.
                os.fchmod(stream.fileno(), mode)
            # Userspace to kernel, then kernel to disk. `flush` alone was the whole of the
            # durability story here, and it is only the first half: it moves the bytes out of
            # Python's buffer into the page cache, where a power loss still loses them.
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, name, src_dir_fd=dir_fd, dst_dir_fd=dir_fd)
        _sync_directory(dir_fd)
    except BaseException:
        _unlink_quietly(dir_fd, temporary)
        raise


def _unlink_quietly(dir_fd: int, name: str) -> None:
    with contextlib.suppress(OSError):
        os.unlink(name, dir_fd=dir_fd)


def write_atomically(
    path: Path, text: str, *, encoding: str = "utf-8", errors: str = "strict"
) -> None:
    """Replace `path` with `text` in one step, keeping the mode it already had.

    The plain-path form, for callers that already hold a trusted absolute path: the memory
    store's own notes and index, whose directory the resolver has already validated. It is the
    same write as `write_atomically_at` — the mode rule, the `fsync` pair and the temporary's
    lifetime are one implementation, reached through a descriptor opened on `path.parent`,
    rather than a second copy that can drift from it. It drifted once: this half used
    path-based `os.chmod`, reopening by name exactly the create-to-chmod window its sibling
    carries seven lines of comment about closing.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    dir_fd = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        write_atomically_at(dir_fd, path.name, text, encoding=encoding, errors=errors)
    finally:
        os.close(dir_fd)


def mkdirs_within(root: Path, target: str) -> None:
    """Create `target`'s parent directories without ever leaving the root.

    `Path.mkdir(parents=True)` cannot do this job: it takes a string and it follows symlinks,
    so a component that became a link after `contained()` passed makes it create directories
    outside the root — and it creates them before the `O_NOFOLLOW` walk gets a chance to
    refuse. Each component here is created relative to a descriptor the walk just opened, so a
    symlink anywhere along the path refuses with nothing created.

    Public, and here rather than in `scaffold.engine` where it was written, because it is the
    subtle half of the surface rule that every area putting a file into a repository calls it
    instead of writing files of its own. `attach`, `setup`, `overlay` and `hooks` all write
    files that are not `Template`s; a private helper leaves each of them to re-derive this, and
    the failure mode of getting it wrong is silent.
    """
    # `checked_components` and not `PurePosixPath(target).parts`, so the whole target is
    # refused by
    # its own spelling before any directory is created, rather than one branch at a time.
    parts = checked_components(target)[:-1]
    for depth in range(len(parts)):
        branch = "/".join(parts[: depth + 1])
        with open_within(root, branch) as (dir_fd, name), contextlib.suppress(FileExistsError):
            os.mkdir(name, dir_fd=dir_fd)


def write_within(root: Path, target: str, text: str, *, encoding: str = "utf-8") -> None:
    """Create the parents and replace `root/target`, reaching it through the `O_NOFOLLOW` walk."""
    mkdirs_within(root, target)
    with open_within(root, target) as (dir_fd, name):
        write_atomically_at(dir_fd, name, text, encoding=encoding)


def remove_within(root: Path, target: str) -> None:
    """Unlink `root/target` through the same walk; an absent file is not an error.

    `contextlib.suppress` is entered after `open_within` has yielded, so it covers the unlink
    and not the walk — a refused walk must still raise.
    """
    with open_within(root, target) as (dir_fd, name), contextlib.suppress(FileNotFoundError):
        os.unlink(name, dir_fd=dir_fd)


def rmdir_within(root: Path, target: str) -> None:
    """Remove the empty directory `root/target` through the same walk; an absent one is not
    an error.

    `remove_within` cannot do this job and cannot be made to: `unlink` on a directory is EPERM
    on macOS and EISDIR on Linux, so a caller that reached for it got an `OSError` it was most
    likely already swallowing, and a tree that quietly never shrank.

    Public, and here rather than private to its caller, for the reason `mkdirs_within` gives one
    function above: "a private helper leaves each of them to re-derive this, and the failure mode of
    getting it wrong is silent". The hook sink asked for it — its marker tree is keyed by session
    and must be pruned, one of the two removals driven by a directory listing that the
    enumerated-writes rule (CONTRIBUTING.md#enumerated-writes) permits — and it is the whole of the
    difference from `remove_within`, so a later hardening of that walk reaches this too instead of
    leaving a copy behind.
    """
    with open_within(root, target) as (dir_fd, name), contextlib.suppress(FileNotFoundError):
        os.rmdir(name, dir_fd=dir_fd)


def rmdir_parents_within(root: Path, target: str) -> None:
    """After `root/target` was removed, remove each directory above it that is now empty, deepest
    first, and stop at the first that is not.

    Only `target`'s own directories, named by its spelling and never found by listing one, so
    this is the "directory above a file the same run removed" of the enumerated-writes rule
    (CONTRIBUTING.md#enumerated-writes), and never `root` or anything above it. Each is one
    `rmdir_within`: the same contained walk, `rmdir`'s own refusal of a directory with anything in
    it, and no symlink followed — one at the end of the walk is refused as not a directory, one
    inside it by the walk — so whatever stops one stops the rest, which hold it. `UnsafePath` for
    a spelling that could leave the root, before anything is asked.
    """
    parts = checked_components(target)
    for depth in range(len(parts) - 1, 0, -1):
        try:
            rmdir_within(root, "/".join(parts[:depth]))
        except OSError:
            return


class NotASymlink(OSError):
    """A real file or directory was found where a symlink was asked about; it is left alone."""


def _type_of(dir_fd: int, name: str) -> int | None:
    """`S_IFMT` of the entry, or `None` when nothing is there — the link questions' `lstat`.

    Separate from `_mode_of`, which answers "what permission bits does the replacement carry
    over" and deliberately returns `None` for anything that is not a regular file, with the
    type bits stripped: `stat.S_ISLNK(_mode_of(...))` is False for every value it can return.
    """
    try:
        return stat.S_IFMT(os.stat(name, dir_fd=dir_fd, follow_symlinks=False).st_mode)
    except FileNotFoundError:
        return None


def readlink_within(root: Path, target: str) -> Path | None:
    """The target of the symlink at `root/target`; `None` when nothing is there.

    Through the same walk as every other primitive, so the question is asked of the entry
    the descriptor names and not of whatever a re-resolved path would reach. A real entry
    raises `NotASymlink`: the callers treat it as somebody else's and never remove it.
    """
    with open_within(root, target) as (dir_fd, name):
        kind = _type_of(dir_fd, name)
        if kind is None:
            return None
        if kind != stat.S_IFLNK:
            raise NotASymlink(f"{target!r} is not a symlink")
        return Path(os.readlink(name, dir_fd=dir_fd))


def symlink_within(root: Path, target: str, source: Path) -> None:
    """Create `root/target -> source` through the walk; parents are created the same way.

    `FileExistsError` when anything is already there — the caller reads first
    (`readlink_within`) and removes first (`unlink_within`); this never replaces.
    """
    mkdirs_within(root, target)
    with open_within(root, target) as (dir_fd, name):
        os.symlink(str(source), name, dir_fd=dir_fd)


def unlink_within(root: Path, target: str, *, pointing_at: Path | None = None) -> bool:
    """Remove the symlink at `root/target`; report whether anything was removed.

    A real entry raises `NotASymlink`. With `pointing_at`, only a link to exactly that path
    is removed — the mirror of `_link`'s "a symlink pointing anywhere else belongs to
    somebody else".
    """
    with open_within(root, target) as (dir_fd, name):
        kind = _type_of(dir_fd, name)
        if kind is None:
            return False
        if kind != stat.S_IFLNK:
            raise NotASymlink(f"{target!r} is not a symlink")
        if pointing_at is not None and Path(os.readlink(name, dir_fd=dir_fd)) != pointing_at:
            return False
        os.unlink(name, dir_fd=dir_fd)
        return True
