"""`scripts/plugin_tree.py`: the plugin's paths read from a commit, as members, manifest and tree.

Every case builds a scratch repository and commits into it, because the subject is what a commit
holds and not what a disk does. The nine paths are spelled out here and never read from the
script's `PLUGIN_PATHS`, and the manifest's first line is spelled here and never read from its
`FORMAT`: an expectation read from the subject is the subject compared with itself.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

from stayfixed.errors import Refusal
from tests.gitfixture import git, needs_git, plant_path
from tests.scriptload import plugin_tree as _script

plugin_tree = _script()
Member = plugin_tree.Member

pytestmark = needs_git

# The nine paths the runtime reads, as the plugin's tree must hold them, spelled out.
NINE = (
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
# One file under each of the nine, with its git mode: the wrapper and the launcher are executable.
PLUGIN_FILES: dict[str, tuple[bytes, str]] = {
    ".claude-plugin/plugin.json": (b'{"name": "stayfixed"}\n', "100644"),
    ".codex-plugin/plugin.json": (b'{"name": "stayfixed"}\n', "100644"),
    "hooks/hooks.json": (b"{}\n", "100644"),
    "hooks/run-hook.sh": (b"#!/bin/sh\nexit 0\n", "100755"),
    "scripts/stayfixed": (b"#!/usr/bin/env python3\n", "100755"),
    "src/stayfixed/__init__.py": (b'__version__ = "1.2.3"\n', "100644"),
    "skills/close-bug/SKILL.md": (b"# close a bug\n", "100644"),
    "agents/navigator.md": (b"# navigator\n", "100644"),
    "README.md": (b"# stayfixed\n", "100644"),
    "LICENSE": (b"MIT\n", "100644"),
}
# Paths beside the plugin's that a prefix test without its `/` would take for its own, and
# paths of the repository that are no part of the plugin.
NEIGHBOURS = (
    ".claude-plugin/marketplace.json",
    "src/stayfixed_extra/__init__.py",
    "scripts/release.py",
    "README.md.bak",
    "hooksx/hooks.json",
    "docs/guide.md",
    "tests/test_it.py",
)


def write(root: Path, files: dict[str, tuple[bytes, str]]) -> None:
    for path, (content, mode) in files.items():
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        target.chmod(0o755 if mode == "100755" else 0o644)


def commit(root: Path, message: str = "a commit") -> str:
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", message)
    return git(root, "rev-parse", "HEAD").strip()


def plugin_repository(
    tmp_path: Path, extra: dict[str, tuple[bytes, str]] | None = None, *, without: str = ""
) -> Path:
    """A repository whose one commit holds a file under each of the nine paths, `extra` beside
    them, and not `without`."""
    root = tmp_path / "repository"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    files = {path: file for path, file in PLUGIN_FILES.items() if path != without}
    write(root, {**files, **(extra or {})})
    commit(root)
    return root


def listed(root: Path, rev: str = "HEAD", **kwargs: bool) -> dict[str, tuple[bytes, str]]:
    return {m.path: (m.content, m.mode) for m in plugin_tree.members(root, rev, **kwargs)}


def test_members_lists_every_plugin_path_with_its_mode_and_nothing_else(tmp_path: Path) -> None:
    # Mutation (declared): `"agents"` dropped from `PLUGIN_PATHS` -> its file is missing here. The
    # neighbours are kept out by git's pathspec in this listing; the prefix rule's own mutation
    # reddens `test_exact_refuses_a_path_outside_the_plugin`, which reads the whole tree.
    root = plugin_repository(tmp_path, {path: (b"x\n", "100644") for path in NEIGHBOURS})
    members = plugin_tree.members(root, "HEAD")
    assert [(m.path, m.mode) for m in members] == [
        (".claude-plugin/plugin.json", "100644"),
        (".codex-plugin/plugin.json", "100644"),
        ("LICENSE", "100644"),
        ("README.md", "100644"),
        ("agents/navigator.md", "100644"),
        ("hooks/hooks.json", "100644"),
        ("hooks/run-hook.sh", "100755"),
        ("scripts/stayfixed", "100755"),
        ("skills/close-bug/SKILL.md", "100644"),
        ("src/stayfixed/__init__.py", "100644"),
    ]
    assert {m.path: m.content for m in members} == {p: c for p, (c, _) in PLUGIN_FILES.items()}
    # Every path named is one of the nine or under one, and the nine are the script's.
    assert all(any(m.path == p or m.path.startswith(p + "/") for p in NINE) for m in members)
    assert plugin_tree.PLUGIN_PATHS == NINE


def test_members_read_the_commit_and_not_the_disk(tmp_path: Path) -> None:
    # Mutation (declared): the content read from `root / path` -> the edited README and the
    # deleted LICENSE are read off the disk.
    root = plugin_repository(tmp_path)
    (root / "README.md").write_bytes(b"edited on disk\n")
    (root / "LICENSE").unlink()
    write(root, {"skills/staged/SKILL.md": (b"staged only\n", "100644")})
    git(root, "add", "skills/staged/SKILL.md")
    assert listed(root) == PLUGIN_FILES


def test_members_at_an_older_commit_are_that_commits(tmp_path: Path) -> None:
    root = plugin_repository(tmp_path)
    first = git(root, "rev-parse", "HEAD").strip()
    write(root, {"README.md": (b"# second\n", "100644"), "skills/new/SKILL.md": (b"n\n", "100644")})
    commit(root, "the second")
    assert listed(root, first) == PLUGIN_FILES
    assert listed(root)["README.md"] == (b"# second\n", "100644")
    assert "skills/new/SKILL.md" in listed(root)


def _symlink(root: Path) -> None:
    os.symlink("../README.md", root / "skills" / "link")
    git(root, "add", "-A")


def _gitlink(root: Path) -> None:
    head = git(root, "rev-parse", "HEAD").strip()
    git(root, "update-index", "--add", "--cacheinfo", f"160000,{head},src/stayfixed/vendored")


@pytest.mark.parametrize(
    ("plant", "path", "mode"),
    [
        pytest.param(_symlink, "skills/link", "120000", id="symlink"),
        pytest.param(_gitlink, "src/stayfixed/vendored", "160000", id="submodule"),
    ],
)
def test_a_symlink_or_submodule_among_the_members_is_refused(
    tmp_path: Path, plant: Callable[[Path], None], path: str, mode: str
) -> None:
    root = plugin_repository(tmp_path)
    plant(root)
    git(root, "commit", "-q", "-m", "plant")
    with pytest.raises(Refusal) as refused:
        plugin_tree.members(root, "HEAD")
    assert path in str(refused.value)
    assert mode in str(refused.value)


def test_a_path_with_a_control_character_is_refused(tmp_path: Path) -> None:
    # Mutation (declared): the control-character rule dropped -> the name is a member, and a
    # manifest line could be forged by it.
    root = plugin_repository(tmp_path)
    plant_path(root, b"skills/a\nb")
    git(root, "commit", "-q", "-m", "a name holding a newline")
    with pytest.raises(Refusal) as refused:
        plugin_tree.members(root, "HEAD")
    assert "'skills/a\\nb'" in str(refused.value)


def test_a_path_that_is_not_utf_8_is_refused(tmp_path: Path) -> None:
    # Mutation (declared): the UTF-8 rule dropped -> the name's decoding raises out of `members`
    # as a `UnicodeDecodeError`, not a refusal naming it.
    root = plugin_repository(tmp_path)
    plant_path(root, b"skills/caf\xe9")
    git(root, "commit", "-q", "-m", "a latin-1 name")
    with pytest.raises(Refusal) as refused:
        plugin_tree.members(root, "HEAD")
    assert "skills/caf" in str(refused.value)
    assert "UTF-8" in str(refused.value)


@pytest.mark.parametrize(
    "outside",
    [
        pytest.param(".mcp.json", id="mcp-json"),
        pytest.param("README.md.bak", id="a-file-beside"),
        pytest.param("hooksx/hooks.json", id="a-directory-beside"),
        pytest.param("src/stayfixed_extra/__init__.py", id="a-package-beside"),
        pytest.param("scripts/release.py", id="a-script-beside"),
    ],
)
def test_exact_refuses_a_path_outside_the_plugin(tmp_path: Path, outside: str) -> None:
    # Mutation (declared): `exact` ignored -> every case reddens. Mutation (declared): the prefix
    # rule's `/` dropped -> the look-alike neighbours (all but `.mcp.json`) pass as the plugin's.
    root = plugin_repository(tmp_path, {outside: (b"{}\n", "100644")})
    assert listed(root, exact=False) == PLUGIN_FILES
    with pytest.raises(Refusal) as refused:
        plugin_tree.members(root, "HEAD", exact=True)
    assert outside in str(refused.value)


def test_exact_lists_a_tree_that_is_only_the_plugin(tmp_path: Path) -> None:
    root = plugin_repository(tmp_path)
    assert listed(root, exact=True) == PLUGIN_FILES


def test_a_missing_plugin_path_is_refused_by_name(tmp_path: Path) -> None:
    # Mutation (declared): the absence check dropped -> a tree without its LICENSE is listed.
    root = plugin_repository(tmp_path, without="LICENSE")
    with pytest.raises(Refusal) as refused:
        plugin_tree.members(root, "HEAD")
    assert "LICENSE" in str(refused.value)


@pytest.mark.parametrize("rev", ["no-such-rev", "HEAD^{tree}", "--all"])
def test_an_unresolvable_rev_is_refused_by_name(tmp_path: Path, rev: str) -> None:
    # A tree is not a commit, and an option is not a rev: `--end-of-options` keeps `--all` a name.
    root = plugin_repository(tmp_path)
    with pytest.raises(Refusal) as refused:
        plugin_tree.members(root, rev)
    assert rev in str(refused.value)


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def test_the_manifest_is_one_line_per_member_in_order() -> None:
    entries = [
        Member("skills/b.md", "100644", b"two"),
        Member("hooks/run-hook.sh", "100755", b"one"),
        Member("LICENSE", "100644", b""),
    ]
    assert plugin_tree.manifest(entries) == (
        "stayfixed-plugin-tree 1\n"
        f"100644 {_sha256(b'')} LICENSE\n"
        f"100755 {_sha256(b'one')} hooks/run-hook.sh\n"
        f"100644 {_sha256(b'two')} skills/b.md\n"
    )


@pytest.mark.parametrize(
    "other",
    [
        pytest.param(Member("a", "100644", b"y"), id="one-byte"),
        pytest.param(Member("a", "100755", b"x"), id="one-mode"),
    ],
)
def test_the_manifest_changes_with_one_byte_and_with_one_mode(other: object) -> None:
    # Mutation (declared): the mode dropped from the line -> `one-mode` reddens. Mutation
    # (declared): the path hashed instead of the content -> `one-byte` reddens.
    assert plugin_tree.manifest([Member("a", "100644", b"x")]) != plugin_tree.manifest([other])


@contextmanager
def umask(mask: int) -> Iterator[None]:
    previous = os.umask(mask)
    try:
        yield
    finally:
        os.umask(previous)


def tree_on_disk(out: Path) -> dict[str, tuple[bytes, int]]:
    return {
        path.relative_to(out).as_posix(): (path.read_bytes(), stat.S_IMODE(path.stat().st_mode))
        for path in sorted(out.rglob("*"))
        if path.is_file()
    }


@pytest.mark.parametrize("mask", [0o022, 0o077], ids=["umask-022", "umask-077"])
def test_render_writes_bytes_and_the_executable_bit(tmp_path: Path, mask: int) -> None:
    # Mutation (declared): written as `content.decode(errors="replace")` text -> `\xff` is
    # replaced. Mutation (declared): the `fchmod` dropped -> under 077 the umask decides.
    awkward = b"line\r\n\x00nul\xff\n"
    # Not the hook wrapper's path: `tests/test_owner_home_seam.py` reads a list headed by it as a
    # launch of stayfixed.
    entries = [
        Member("bin/run", "100755", b"#!/bin/sh\r\n" + awkward),
        Member("skills/data/blob", "100644", awkward),
    ]
    out = tmp_path / "out"
    with umask(mask):
        plugin_tree.render(entries, out)
    assert tree_on_disk(out) == {
        "bin/run": (b"#!/bin/sh\r\n" + awkward, 0o755),
        "skills/data/blob": (awkward, 0o644),
    }


@pytest.mark.parametrize("occupied", ["a-file-inside", "a-file-instead"])
def test_render_refuses_a_destination_that_is_not_empty(tmp_path: Path, occupied: str) -> None:
    # A render killed part-way leaves a directory that is not empty, and the next one refuses it
    # rather than writing over half a tree.
    out = tmp_path / "out"
    if occupied == "a-file-inside":
        out.mkdir()
        (out / "left-over").write_bytes(b"half\n")
    else:
        out.write_bytes(b"a file\n")
    before = out.read_bytes() if out.is_file() else tree_on_disk(out)
    with pytest.raises(Refusal) as refused:
        plugin_tree.render([Member("LICENSE", "100644", b"MIT\n")], out)
    assert str(out) in str(refused.value)
    assert (out.read_bytes() if out.is_file() else tree_on_disk(out)) == before


def test_render_writes_into_an_empty_directory(tmp_path: Path) -> None:
    out = tmp_path / "out"
    out.mkdir()
    plugin_tree.render([Member("LICENSE", "100644", b"MIT\n")], out)
    assert tree_on_disk(out) == {"LICENSE": (b"MIT\n", 0o644)}


def test_render_twice_writes_the_same_tree_and_manifest(tmp_path: Path) -> None:
    # No mutation exists: `members`, `manifest` and `render` keep no state between calls. This
    # pins determinism against a cache added later.
    root = plugin_repository(tmp_path)
    plugin_tree.render(plugin_tree.members(root, "HEAD"), tmp_path / "one")
    plugin_tree.render(plugin_tree.members(root, "HEAD"), tmp_path / "two")
    assert tree_on_disk(tmp_path / "one") == tree_on_disk(tmp_path / "two")
    assert len(tree_on_disk(tmp_path / "one")) == len(PLUGIN_FILES)
    first = plugin_tree.manifest(plugin_tree.members(root, "HEAD"))
    assert plugin_tree.manifest(plugin_tree.members(root, "HEAD")) == first


def test_the_cli_writes_the_manifest_file_and_renders(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = plugin_repository(tmp_path)
    head = git(root, "rev-parse", "HEAD").strip()
    out, written = tmp_path / "out", tmp_path / "manifest.txt"
    argv = ["render", "--root", str(root), "--rev", "HEAD", "--out", str(out)]
    assert plugin_tree.main([*argv, "--manifest-file", str(written)]) == 0
    expected = plugin_tree.manifest(plugin_tree.members(root, "HEAD")).encode("utf-8")
    assert written.read_bytes() == expected
    assert written.read_bytes().startswith(b"stayfixed-plugin-tree 1\n")
    assert set(tree_on_disk(out)) == set(PLUGIN_FILES)
    capsys.readouterr()

    assert plugin_tree.main(["manifest", "--root", str(root), "--rev", "HEAD", "--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert (report["rev"], report["files"]) == (head, len(PLUGIN_FILES))
    assert len(report["rev"]) == 40

    assert plugin_tree.main(["manifest", "--root", str(root), "--rev", "no-such-rev"]) == 2
    assert "no-such-rev" in capsys.readouterr().err


def test_the_cli_manifest_writes_its_file_and_honours_exact(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = plugin_repository(tmp_path, {".mcp.json": (b"{}\n", "100644")})
    written = tmp_path / "manifest.txt"
    argv = ["manifest", "--root", str(root), "--rev", "HEAD", "--manifest-file", str(written)]
    assert plugin_tree.main(argv) == 0
    assert written.read_bytes() == plugin_tree.manifest(plugin_tree.members(root, "HEAD")).encode()
    written.unlink()
    capsys.readouterr()
    assert plugin_tree.main([*argv, "--exact"]) == 2
    assert ".mcp.json" in capsys.readouterr().err
    assert not written.exists()


def test_the_cli_refuses_a_manifest_file_inside_the_tree(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # The manifest describes the tree and is no member of it: written inside `--out`, it would be
    # a file the rendered tree holds and its own manifest does not name.
    root = plugin_repository(tmp_path)
    out = tmp_path / "out"
    argv = ["render", "--root", str(root), "--rev", "HEAD", "--out", str(out)]
    assert plugin_tree.main([*argv, "--manifest-file", str(out / "MANIFEST")]) == 2
    assert "--manifest-file" in capsys.readouterr().err
    assert not out.exists()
