#!/usr/bin/env python3
"""The plugin's tree: the nine paths the runtime reads, read from a commit of this repository.

    uv run python scripts/plugin_tree.py manifest --root DIR --rev REV [--exact]
                                         [--manifest-file FILE]
    uv run python scripts/plugin_tree.py render --root DIR --rev REV --out DIR
                                       [--manifest-file FILE]

This repository is more than the plugin: its tests, documents, plans and tooling ship nowhere. The
plugin is published from a repository of its own whose root is the tree this script generates, and
`PLUGIN_PATHS` is the one place its paths are named: the release check, the payload test and the
workflows that build, install and attest the plugin all run this script, or, in a test, import it.

**Read from a commit, never from the disk.** The directory, the attestation and the plugin
repository each see a commit, so a file edited, deleted or only staged here is not in what they
see, and must not be in what this script reports either. Every byte comes from `git ls-tree` and
`git cat-file` at one commit, resolved once; no filter, attribute or line-ending conversion of a
working tree touches it.

**The manifest is the text a release attests.** One line naming its format, then one line per
file: its git mode, the sha256 of its bytes and its path. `publish_plugin.py` compares two of them
and nothing else, which is why a path holding a control character, or one that is not UTF-8, is
refused rather than written: a `\\n` in a name would forge a line, and a C1 control or a Unicode
line separator breaks the line a terminal or an editor shows.

The commands go through the CLI frame's `run`, as `scripts/release.py`'s do: `--json` anywhere on
the line, exit `0`, and `2` for a refusal.
"""

from __future__ import annotations

import argparse
import hashlib
import operator
import os
import re
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from stayfixed import fsops
from stayfixed.cli import JSON_EPILOG, run
from stayfixed.errors import Refusal
from stayfixed.gitenv import QUERY_TIMEOUT_SECONDS, answer_bytes, git_run
from stayfixed.printed import quoted
from stayfixed.result import Result

# What the plugin's runtime reads, and nothing else: the two manifests, the hooks and their
# wrapper, the launcher and the package it puts on `sys.path`, the skills and agents the harness
# loads, and the two files every published repository carries.
PLUGIN_PATHS: tuple[str, ...] = (
    ".claude-plugin/plugin.json",
    ".codex-plugin/plugin.json",
    "hooks",
    "scripts/stayfixed",
    "src/stayfixed",
    "skills",
    "agents",
    "README.md",
    "LICENSE",
)
# The manifest's first line: a reader that meets another refuses to compare.
FORMAT = "stayfixed-plugin-tree 1"
# The only modes a member may have. A symlink (`120000`) and a submodule (`160000`) are what the
# plugin directory blocks where the plugin loads them, and every path here is one it loads.
REGULAR_MODES = frozenset({"100644", "100755"})
# The permission bits a rendered file gets for its git mode, whatever the umask says.
PERMISSIONS = {"100644": 0o644, "100755": 0o755}
_CREATE = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0) | os.O_CLOEXEC
# Before the subcommand on every git this script runs. `--no-replace-objects`: a `refs/replace/`
# ref makes git read one object as another, and the tree read here is the commit's own, not what
# a replacement says it is. `safe.bareRepository=all`: `--root` is the repository the caller
# names, and `publish_plugin.py` names its scratch bare repository, which an owner's
# `safe.bareRepository=explicit` would otherwise refuse, since `git -C` finds it rather than is
# given it.
GIT_OPTIONS = ("--no-replace-objects", "-c", "safe.bareRepository=all")
# A full object name as git prints one: SHA-1's 40 hex characters or SHA-256's 64, lower case.
OBJECT_NAME = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")
# The two Unicode line breaks that are neither a C0 nor a C1 control: an editor or a terminal
# ends a line at each.
_LINE_SEPARATORS = frozenset({"\u2028", "\u2029"})


@dataclass(frozen=True)
class Member:
    path: str  # POSIX, relative to the plugin root, as git lists it
    mode: str  # "100644" or "100755"
    content: bytes


@dataclass(frozen=True)
class Tree:
    commit: str  # the full object name of the commit the tree was read at
    members: tuple[Member, ...]  # sorted by path


def _under(path: str, entry: str) -> bool:
    """Whether `path` is the plugin path `entry` or inside it: `hooksx` is not under `hooks`."""
    return path == entry or path.startswith(entry + "/")


def is_plugin_path(path: str) -> bool:
    """Whether `path` is one of `PLUGIN_PATHS` or inside one."""
    return any(_under(path, entry) for entry in PLUGIN_PATHS)


def _control(path: str) -> bool:
    """Whether `path` holds a C0 control, DEL, a C1 control or a Unicode line separator."""
    return any(
        ord(char) < 0x20 or 0x7F <= ord(char) <= 0x9F or char in _LINE_SEPARATORS for char in path
    )


def _git(
    root: Path, *args: str, stdin: str | None = None, timeout: float = QUERY_TIMEOUT_SECONDS
) -> tuple[int, str]:
    return git_run(root, *GIT_OPTIONS, *args, stdin=stdin, timeout=timeout)


def peel(root: Path, rev: str, kind: str) -> str:
    """The `kind` (`commit` or `tree`) `rev` peels to in `root`, as git's full object name, or a
    refusal naming `rev`: the one place this script resolves a rev."""
    code, answer = _git(root, "rev-parse", "--verify", "--end-of-options", f"{rev}^{{{kind}}}")
    name = answer.removesuffix("\n")
    if code != 0:
        raise Refusal(f"{quoted(rev)} names no {kind} in {root} (git rev-parse exited {code})")
    if not OBJECT_NAME.fullmatch(name):
        raise Refusal(f"git rev-parse answered {quoted(name)} for {quoted(rev)} in {root}")
    return name


def _listing(root: Path, sha: str, *, exact: bool) -> list[tuple[str, str, str]]:
    """`(mode, object, path)` for every path git lists at `sha`: under the plugin's paths, or, when
    `exact`, the whole tree."""
    pathspec = () if exact else ("--", *PLUGIN_PATHS)
    code, answer = _git(root, "ls-tree", "-r", "-z", "--full-tree", sha, *pathspec)
    if code != 0:
        raise Refusal(f"git ls-tree of {sha} exited {code} in {root}")
    rows = []
    for record in answer.split("\0"):
        if not record:
            continue
        # `<mode> <type> <object>\t<path>`: the path is everything after the tab, unquoted under -z.
        meta, path = record.split("\t", 1)
        mode, _kind, obj = meta.split()
        rows.append((mode, obj, path))
    return rows


def _blobs(root: Path, objects: list[str]) -> dict[str, bytes]:
    """Each object's bytes, from one `git cat-file --batch`."""
    if not objects:
        return {}
    code, answer = _git(root, "cat-file", "--batch", stdin="".join(obj + "\n" for obj in objects))
    if code != 0:
        raise Refusal(f"git cat-file --batch exited {code} in {root}")
    out, at, blobs = answer_bytes(answer), 0, {}
    for obj in objects:
        # `<object> <type> <size>\n<content>\n`, once per object asked, in the order asked.
        header_end = out.find(b"\n", at)
        header = out[at:header_end].split() if header_end != -1 else []
        if len(header) != 3 or header[1] != b"blob" or not header[2].isdigit():
            raise Refusal(f"git cat-file did not answer {obj} as a blob in {root}")
        size = int(header[2])
        content = out[header_end + 1 : header_end + 1 + size]
        # A slice past the end is short, not an error: an answer cut off inside a blob would
        # otherwise be read as that blob's bytes.
        if len(content) != size:
            raise Refusal(f"git cat-file's answer in {root} ended inside {obj}")
        blobs[obj] = content
        at = header_end + 1 + size + 1
    return blobs


def read(root: Path, rev: str, *, exact: bool = False) -> Tree:
    """The commit `rev` names, resolved once, and every file under the plugin's paths at it,
    sorted by path.

    Refused: a rev that names no commit; a plugin path the commit does not hold; a member that is
    not a regular file, by its path and mode; a path that is not UTF-8 or that holds a control
    character; and, with `exact`, any path at the commit outside every plugin path.
    """
    sha = peel(root, rev, "commit")
    rows = []
    for mode, obj, raw in _listing(root, sha, exact=exact):
        if not fsops.utf_8_name(raw):
            raise Refusal(f"{quoted(raw)} at {sha} is not UTF-8; a plugin path must be")
        # The bytes git printed, read as the UTF-8 they were just shown to be, whatever the
        # filesystem's codec decoded them as.
        path = os.fsencode(raw).decode("utf-8")
        if _control(path):
            raise Refusal(f"{quoted(path)} at {sha} holds a control character")
        if not is_plugin_path(path):
            raise Refusal(f"{quoted(path)} at {sha} is outside every plugin path")
        if mode not in REGULAR_MODES:
            raise Refusal(f"{quoted(path)} at {sha} has mode {mode}, not a regular file's")
        rows.append((path, mode, obj))
    for entry in PLUGIN_PATHS:
        if not any(_under(path, entry) for path, _, _ in rows):
            raise Refusal(f"{entry} is missing at {sha}; the plugin cannot be built without it")
    blobs = _blobs(root, sorted({obj for _, _, obj in rows}))
    found = (Member(path, mode, blobs[obj]) for path, mode, obj in rows)
    return Tree(sha, tuple(sorted(found, key=operator.attrgetter("path"))))


def members(root: Path, rev: str, *, exact: bool = False) -> list[Member]:
    """`read`'s members: every file under the plugin's paths at the commit `rev` names."""
    return list(read(root, rev, exact=exact).members)


def manifest(entries: Iterable[Member]) -> str:
    """`FORMAT` on the first line, then `<mode> <sha256> <path>` for each member, in the order
    given: `read` gives them sorted by path."""
    lines = [FORMAT]
    for member in entries:
        lines.append(f"{member.mode} {hashlib.sha256(member.content).hexdigest()} {member.path}")
    return "".join(line + "\n" for line in lines)


def _empty_or_absent(out: Path) -> bool:
    if not os.path.lexists(out):
        return True
    return fsops.is_dir(out) and not fsops.is_symlink(out) and not any(out.iterdir())


def render(entries: Iterable[Member], out: Path) -> None:
    """Write each member into `out`, which must be absent or an empty directory: its bytes as
    they are, and exactly the permissions its git mode names. Nothing else is written."""
    if not _empty_or_absent(out):
        raise Refusal(f"{out} is not an empty directory; the plugin tree is rendered into one")
    try:
        out.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise Refusal(f"{out} cannot be made: {exc.strerror or exc}") from None
    for member in entries:
        try:
            fsops.mkdirs_within(out, member.path)
            with fsops.open_within(out, member.path) as (dir_fd, name):
                permissions = PERMISSIONS[member.mode]
                descriptor = os.open(name, _CREATE, permissions, dir_fd=dir_fd)
                with os.fdopen(descriptor, "wb") as handle:
                    handle.write(member.content)
                    # The mode `open` is given passes through the umask; this does not.
                    os.fchmod(handle.fileno(), permissions)
        except fsops.UnsafePath as exc:
            raise Refusal(f"{quoted(member.path)} cannot be rendered: {exc}") from None
        except OSError as exc:
            # A full disk, a quota, a permission: said as the refusal it is, with the path it
            # stopped at, rather than escaping as an internal error.
            raise Refusal(
                f"{quoted(member.path)} could not be written into {out}: {exc.strerror or exc}"
            ) from None


# --- The commands -------------------------------------------------------------------------------


def _write_manifest(path: Path, text: str) -> None:
    path.write_bytes(text.encode("utf-8"))


def run_manifest(args: argparse.Namespace) -> Result:
    tree = read(Path(args.root), args.rev, exact=args.exact)
    if args.manifest_file is not None:
        _write_manifest(Path(args.manifest_file), manifest(tree.members))
    files = len(tree.members)
    return Result(
        f"the plugin tree at {tree.commit} holds {files} files",
        {"rev": tree.commit, "files": files},
    )


def run_render(args: argparse.Namespace) -> Result:
    root, out = Path(args.root), Path(args.out)
    written = None if args.manifest_file is None else Path(args.manifest_file)
    if written is not None and written.resolve().is_relative_to(out.resolve()):
        raise Refusal(f"--manifest-file {written} is inside --out {out}; it describes the tree")
    tree = read(root, args.rev)
    render(tree.members, out)
    # Last, after every member: a manifest on disk says its tree was written whole.
    if written is not None:
        _write_manifest(written, manifest(tree.members))
    files = len(tree.members)
    return Result(
        f"rendered the plugin tree at {tree.commit} into {out}: {files} files",
        {"rev": tree.commit, "files": files},
    )


def parser() -> argparse.ArgumentParser:
    top = argparse.ArgumentParser(
        prog="scripts/plugin_tree.py",
        description="The plugin's tree, read from a commit of this repository.",
        epilog=JSON_EPILOG,
    )
    sub = top.add_subparsers(dest="command", metavar="<command>")

    def command(name: str, sentence: str) -> argparse.ArgumentParser:
        cmd = sub.add_parser(name, help=sentence, description=sentence, epilog=JSON_EPILOG)
        cmd.add_argument("--root", required=True, help="the repository to read")
        cmd.add_argument("--rev", required=True, help="the commit to read the tree from")
        return cmd

    listing = command("manifest", "count the plugin tree at a commit, and write its manifest")
    listing.add_argument(
        "--exact", action="store_true", help="refuse a commit holding any path outside the plugin"
    )
    listing.add_argument("--manifest-file", default=None, help="where to write the manifest")
    listing.set_defaults(func=run_manifest)
    rendering = command("render", "write the plugin tree at a commit into an empty directory")
    rendering.add_argument("--out", required=True, help="an absent or empty directory")
    rendering.add_argument(
        "--manifest-file", default=None, help="where to write the manifest, outside --out"
    )
    rendering.set_defaults(func=run_render)
    return top


def main(argv: list[str] | None = None) -> int:
    return run(sys.argv[1:] if argv is None else argv, parser=parser())


if __name__ == "__main__":
    sys.exit(main())
