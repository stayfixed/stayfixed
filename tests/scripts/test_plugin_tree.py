"""`scripts/plugin_tree.py`: the plugin's paths read from a commit, as members, manifest and tree.

Every case builds a scratch repository and commits into it, because the subject is what a commit
holds and not what a disk does. The nine paths are spelled out in `tests/plugintree.py`, which
builds every source here, and never read from the script's `PLUGIN_PATHS`; the manifest's first
line and every commit text are spelled here and never read from the script: an expectation read
from the subject is the subject compared with itself.
"""

from __future__ import annotations

import errno
import hashlib
import json
import os
import stat
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest

from stayfixed import gitenv
from stayfixed.errors import Refusal
from tests.gitfixture import git, git_bytes, needs_git, plant_path
from tests.plugintree import NINE, PLUGIN_FILES, commit, hashed, literal, plugin_source, write
from tests.scriptload import plugin_tree as _script

plugin_tree = _script()
Member = plugin_tree.Member

pytestmark = needs_git

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


def listed(root: Path, rev: str = "HEAD", **kwargs: bool) -> dict[str, tuple[bytes, str]]:
    return {m.path: (m.content, m.mode) for m in plugin_tree.members(root, rev, **kwargs)}


def test_members_lists_every_plugin_path_with_its_mode_and_nothing_else(tmp_path: Path) -> None:
    # Mutation (declared): `"agents"` dropped from `PLUGIN_PATHS` -> its file is missing here. The
    # neighbours are kept out by git's pathspec in this listing; the prefix rule's own mutation
    # reddens `test_exact_refuses_a_path_outside_the_plugin`, which reads the whole tree.
    root = plugin_source(
        tmp_path, {**PLUGIN_FILES, **{path: (b"x\n", "100644") for path in NEIGHBOURS}}
    )
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
    root = plugin_source(tmp_path)
    (root / "README.md").write_bytes(b"edited on disk\n")
    (root / "LICENSE").unlink()
    write(root, {"skills/staged/SKILL.md": (b"staged only\n", "100644")})
    git(root, "add", "skills/staged/SKILL.md")
    assert listed(root) == PLUGIN_FILES


def test_a_replace_ref_does_not_change_what_is_read(tmp_path: Path) -> None:
    # Mutation (declared): `--no-replace-objects` dropped from the script's git options -> the
    # README's blob is read as the one `refs/replace/` names in its place.
    root = plugin_source(tmp_path)
    readme = git(root, "rev-parse", "HEAD:README.md").strip()
    write(root, {"elsewhere.md": (b"# a replacement\n", "100644")})
    replacement = git(root, "hash-object", "-w", "elsewhere.md").strip()
    git(root, "replace", readme, replacement)
    assert listed(root) == PLUGIN_FILES


def test_a_bare_repository_is_read_under_an_explicit_safe_bare_repository(tmp_path: Path) -> None:
    # Mutation (declared): `safe.bareRepository=all` dropped from the script's git options -> the
    # owner's `explicit` refuses the bare repository `--root` names, as `publish_plugin.py`'s
    # read-back names its scratch one, and the commit is reported as unresolvable.
    bare = tmp_path / "bare.git"
    git(tmp_path, "clone", "-q", "--bare", str(plugin_source(tmp_path)), str(bare))
    config = Path(os.environ["HOME"]) / ".gitconfig"
    config.write_text(
        config.read_text(encoding="utf-8") + "[safe]\n\tbareRepository = explicit\n",
        encoding="utf-8",
    )
    assert listed(bare) == PLUGIN_FILES


def test_members_at_an_older_commit_are_that_commits(tmp_path: Path) -> None:
    # Mutation (declared): the listing asked of `HEAD` instead of the resolved commit -> the second
    # commit's README is read at the first.
    root = plugin_source(tmp_path)
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
    root = plugin_source(tmp_path)
    plant(root)
    git(root, "commit", "-q", "-m", "plant")
    with pytest.raises(Refusal) as refused:
        plugin_tree.members(root, "HEAD")
    assert path in str(refused.value)
    assert mode in str(refused.value)


def test_a_path_with_a_control_character_is_refused(tmp_path: Path) -> None:
    # Mutation (declared): the control-character rule dropped -> the name is a member, and a
    # manifest line could be forged by it.
    root = plugin_source(tmp_path)
    plant_path(root, b"skills/a\nb")
    git(root, "commit", "-q", "-m", "a name holding a newline")
    with pytest.raises(Refusal) as refused:
        plugin_tree.members(root, "HEAD")
    assert "'skills/a\\nb'" in str(refused.value)


@pytest.mark.parametrize(
    "character",
    [
        pytest.param("\x7f", id="delete"),
        pytest.param("\x85", id="next-line"),
        pytest.param("\x9b", id="control-sequence-introducer"),
        pytest.param("\u2028", id="line-separator"),
        pytest.param("\u2029", id="paragraph-separator"),
    ],
)
def test_a_c1_or_line_separator_in_a_path_is_refused(tmp_path: Path, character: str) -> None:
    # A C1 control or a Unicode line separator is valid UTF-8, so the UTF-8 rule passes it, and a
    # terminal or an editor reading the manifest may break the line at it. `delete` holds the rule
    # already standing. Mutations (declared): `mutations/`'s "the plugin tree lists a path holding
    # a C1 control" -> `next-line` and `control-sequence-introducer` redden; "the plugin tree
    # lists a path holding a Unicode line separator" -> the two separators redden.
    root = plugin_source(tmp_path)
    plant_path(root, f"skills/a{character}b".encode())
    git(root, "commit", "-q", "-m", "a name holding a control character")
    with pytest.raises(Refusal, match="holds a control character"):
        plugin_tree.members(root, "HEAD")


def test_is_plugin_path() -> None:
    # Mutation (declared): `mutations/`'s "the plugin tree takes a look-alike neighbour for a
    # plugin path" -> `hooksx/y` is taken for a path under `hooks`.
    assert plugin_tree.is_plugin_path("hooks/x")
    assert not plugin_tree.is_plugin_path("hooksx/y")
    assert plugin_tree.is_plugin_path("README.md")


def test_a_path_that_is_not_utf_8_is_refused(tmp_path: Path) -> None:
    # Mutation (declared): the UTF-8 rule dropped -> the name's decoding raises out of `members`
    # as a `UnicodeDecodeError`, not a refusal naming it.
    root = plugin_source(tmp_path)
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
    root = plugin_source(tmp_path, {**PLUGIN_FILES, outside: (b"{}\n", "100644")})
    assert listed(root, exact=False) == PLUGIN_FILES
    with pytest.raises(Refusal) as refused:
        plugin_tree.members(root, "HEAD", exact=True)
    assert outside in str(refused.value)


def test_exact_lists_a_tree_that_is_only_the_plugin(tmp_path: Path) -> None:
    # Mutation (declared): `exact` refuses every path -> a tree that is only the plugin is refused.
    root = plugin_source(tmp_path)
    assert listed(root, exact=True) == PLUGIN_FILES


def test_a_missing_plugin_path_is_refused_by_name(tmp_path: Path) -> None:
    # Mutation (declared): the absence check dropped -> a tree without its LICENSE is listed.
    root = plugin_source(tmp_path, {p: f for p, f in PLUGIN_FILES.items() if p != "LICENSE"})
    with pytest.raises(Refusal) as refused:
        plugin_tree.members(root, "HEAD")
    assert "LICENSE" in str(refused.value)


@pytest.mark.parametrize("rev", ["no-such-rev", "HEAD^{tree}", "--all"])
def test_an_unresolvable_rev_is_refused_by_name(tmp_path: Path, rev: str) -> None:
    # A tree is not a commit, and an option is not a rev. `--all` is refused because the
    # `^{commit}` suffix makes `--all^{commit}` no option git knows, with or without the
    # `--end-of-options` that stands behind it; no rev shows that flag alone.
    root = plugin_source(tmp_path)
    with pytest.raises(Refusal) as refused:
        plugin_tree.members(root, rev)
    assert rev in str(refused.value)


def test_peel_names_a_sha256_repository_s_commit(tmp_path: Path) -> None:
    # Mutation (declared): `mutations/`'s "the plugin tree takes no 64-character object name for
    # one" -> the sha256 commit is refused as no object name.
    root = tmp_path / "sha256"
    root.mkdir()
    git(root, "init", "-q", "-b", "main", "--object-format=sha256")
    write(root, PLUGIN_FILES)
    head = commit(root)
    assert len(head) == 64
    assert plugin_tree.peel(root, "HEAD", "commit") == head


def test_peel_refuses_an_answer_that_is_not_an_object_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Mutation (declared): `mutations/`'s "the plugin tree takes any answer of rev-parse for an
    # object name" -> `not-a-sha` is returned as the commit.
    def answered(where: Path, *args: str, **options: Any) -> tuple[int, str]:
        return 0, "not-a-sha\n"

    monkeypatch.setattr(plugin_tree, "git_run", answered)
    with pytest.raises(Refusal) as refused:
        plugin_tree.peel(tmp_path, "refs/tags/v9", "commit")
    assert "refs/tags/v9" in str(refused.value)


def test_a_replaced_annotated_tag_peels_to_its_own_commit(tmp_path: Path) -> None:
    # Mutation (declared): `mutations/`'s "the plugin tree reads an object through a replace ref"
    # -> `v1` peels through its replacement to `v2`'s commit.
    root = plugin_source(tmp_path)
    first = git(root, "rev-parse", "HEAD").strip()
    git(root, "tag", "-a", "v1", "-m", "v1")
    write(root, {"README.md": (b"# second\n", "100644")})
    second = commit(root, "the second")
    git(root, "tag", "-a", "v2", "-m", "v2")
    v1, v2 = (git(root, "rev-parse", f"refs/tags/{tag}").strip() for tag in ("v1", "v2"))
    git(root, "replace", "-f", v1, v2)
    # The premise: through the replacement, `v1` peels to the second commit.
    assert git(root, "rev-parse", "refs/tags/v1^{commit}").strip() == second
    assert plugin_tree.peel(root, "refs/tags/v1", "commit") == first


@pytest.mark.parametrize("cut", ["inside-a-header", "inside-a-blob"])
def test_a_cat_file_answer_cut_short_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, cut: str
) -> None:
    # Mutations (declared): the header's search back to `index` with no check -> a header cut off
    # before its newline escapes as a `ValueError`; the blob's length not compared -> a blob cut
    # off is read as the shorter bytes, and the listing goes through.
    root = plugin_source(tmp_path)
    real = plugin_tree.git_run

    def cut_short(where: Path, *args: str, **options: Any) -> tuple[int, str]:
        code, answer = real(where, *args, **options)
        if "cat-file" not in args:
            return code, answer
        if cut == "inside-a-header":
            return code, answer[: answer.index("\n") - 1]
        return code, answer[:-3]

    monkeypatch.setattr(plugin_tree, "git_run", cut_short)
    with pytest.raises(Refusal, match="cat-file"):
        plugin_tree.members(root, "HEAD")


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def test_the_manifest_is_one_line_per_member_in_order() -> None:
    # In the order given, which `read` sorts by path: the sort lives there alone. No mutation
    # reddens on the order of an input that is already sorted; the format of each line is held by
    # `test_the_manifest_changes_with_one_byte_and_with_one_mode`.
    entries = [
        Member("LICENSE", "100644", b""),
        Member("hooks/run-hook.sh", "100755", b"one"),
        Member("skills/b.md", "100644", b"two"),
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
    # Mutation (declared): an existing directory refused even when empty -> this reddens.
    out = tmp_path / "out"
    out.mkdir()
    plugin_tree.render([Member("LICENSE", "100644", b"MIT\n")], out)
    assert tree_on_disk(out) == {"LICENSE": (b"MIT\n", 0o644)}


def test_a_render_that_fails_part_way_leaves_no_manifest_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Mutation (declared): the manifest file written before the tree -> it is on disk beside a
    # tree whose last member was never written, and says that tree is whole.
    root = plugin_source(tmp_path)
    out, written = tmp_path / "tree", tmp_path / "plugin-tree.txt"
    real, calls = os.fchmod, []

    def full_disk(descriptor: int, mode: int) -> None:
        calls.append(descriptor)
        if len(calls) == len(PLUGIN_FILES):
            raise OSError(errno.ENOSPC, os.strerror(errno.ENOSPC))
        real(descriptor, mode)

    monkeypatch.setattr(plugin_tree.os, "fchmod", full_disk)
    argv = ["render", "--root", str(root), "--rev", "HEAD", "--out", str(out)]
    assert plugin_tree.main([*argv, "--manifest-file", str(written)]) == 2
    assert len(calls) == len(PLUGIN_FILES)
    assert not written.exists()


def test_a_member_the_disk_will_not_take_is_refused_by_its_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Mutation (declared): the `OSError` catch dropped -> a full disk escapes `render` as an
    # internal error naming no member, rather than a refusal naming the one it stopped at.
    members = plugin_tree.members(plugin_source(tmp_path), "HEAD")

    def full_disk(descriptor: int, mode: int) -> None:
        raise OSError(errno.ENOSPC, os.strerror(errno.ENOSPC))

    monkeypatch.setattr(plugin_tree.os, "fchmod", full_disk)
    with pytest.raises(Refusal, match="could not be written into") as refused:
        plugin_tree.render(members, tmp_path / "tree")
    assert members[0].path in str(refused.value)
    assert os.strerror(errno.ENOSPC) in str(refused.value)


def test_a_destination_that_cannot_be_made_is_refused(tmp_path: Path) -> None:
    # Mutation (declared): the `OSError` catch around making the destination dropped -> a
    # destination under a regular file escapes as an internal error.
    members = plugin_tree.members(plugin_source(tmp_path), "HEAD")
    (tmp_path / "a-file").write_bytes(b"")
    with pytest.raises(Refusal, match="cannot be made"):
        plugin_tree.render(members, tmp_path / "a-file" / "tree")


def test_render_twice_writes_the_same_tree_and_manifest(tmp_path: Path) -> None:
    # No mutation exists: `members`, `manifest` and `render` keep no state between calls. This
    # pins determinism against a cache added later.
    root = plugin_source(tmp_path)
    plugin_tree.render(plugin_tree.members(root, "HEAD"), tmp_path / "one")
    plugin_tree.render(plugin_tree.members(root, "HEAD"), tmp_path / "two")
    assert tree_on_disk(tmp_path / "one") == tree_on_disk(tmp_path / "two")
    assert len(tree_on_disk(tmp_path / "one")) == len(PLUGIN_FILES)
    first = plugin_tree.manifest(plugin_tree.members(root, "HEAD"))
    assert plugin_tree.manifest(plugin_tree.members(root, "HEAD")) == first


def test_the_cli_writes_the_manifest_file_and_renders(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # Mutation (declared): `render` writes no manifest file -> this reddens.
    root = plugin_source(tmp_path)
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


def test_render_without_a_manifest_file_writes_only_the_tree(tmp_path: Path) -> None:
    # No mutation of its own: `--manifest-file` required again is an argparse refusal, and this
    # reddens on it.
    root = plugin_source(tmp_path)
    out = tmp_path / "out"
    assert (
        plugin_tree.main(["render", "--root", str(root), "--rev", "HEAD", "--out", str(out)]) == 0
    )
    assert set(tree_on_disk(out)) == set(PLUGIN_FILES)
    assert sorted(tmp_path.iterdir()) == sorted([root, out])


def test_read_resolves_the_rev_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # Mutation (declared): `mutations/`'s "the plugin manifest resolves its rev before reading"
    # -> the manifest command asks git twice, and a ref moved in between names two commits.
    root = plugin_source(tmp_path)
    real, asked = plugin_tree.git_run, []

    def counted(where: Path, *args: str, **options: Any) -> tuple[int, str]:
        if "rev-parse" in args:
            asked.append(args)
        code, answer = real(where, *args, **options)
        return code, answer

    monkeypatch.setattr(plugin_tree, "git_run", counted)
    assert plugin_tree.main(["manifest", "--root", str(root), "--rev", "HEAD"]) == 0
    assert len(asked) == 1, asked
    asked.clear()
    argv = ["render", "--root", str(root), "--rev", "HEAD", "--out", str(tmp_path / "out")]
    assert plugin_tree.main(argv) == 0
    assert len(asked) == 1, asked
    capsys.readouterr()


def test_the_cli_manifest_writes_its_file_and_honours_exact(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # Mutation (declared): `manifest` drops `--exact` -> the `.mcp.json` tree is listed, exit 0.
    root = plugin_source(tmp_path, {**PLUGIN_FILES, ".mcp.json": (b"{}\n", "100644")})
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
    root = plugin_source(tmp_path)
    out = tmp_path / "out"
    argv = ["render", "--root", str(root), "--rev", "HEAD", "--out", str(out)]
    assert plugin_tree.main([*argv, "--manifest-file", str(out / "MANIFEST")]) == 2
    assert "--manifest-file" in capsys.readouterr().err
    assert not out.exists()


def test_the_cli_reads_the_rev_it_is_given(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # Both commands render and count the commit `--rev` names, not `HEAD`, and report that
    # commit. Mutations (declared): `members` asked of `HEAD` in `render`, and in `manifest`
    # -> the second commit's README is written and this reddens.
    root = plugin_source(tmp_path)
    first = git(root, "rev-parse", "HEAD").strip()
    write(root, {"README.md": (b"# second\n", "100644")})
    commit(root, "the second")
    out, rendered, counted = tmp_path / "out", tmp_path / "rendered.txt", tmp_path / "counted.txt"
    argv = ["--root", str(root), "--rev", first]
    rendering = ["render", *argv, "--out", str(out), "--manifest-file", str(rendered)]
    assert plugin_tree.main(rendering) == 0
    capsys.readouterr()
    assert plugin_tree.main(["manifest", *argv, "--manifest-file", str(counted), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["rev"] == first
    on_disk = tree_on_disk(out)
    assert {path: content for path, (content, _) in on_disk.items()} == {
        path: content for path, (content, _) in PLUGIN_FILES.items()
    }
    expected = plugin_tree.manifest(plugin_tree.members(root, first)).encode("utf-8")
    assert rendered.read_bytes() == expected
    assert counted.read_bytes() == expected


# --- The plugin commit ----------------------------------------------------------------------------

MARKETPLACE = ".claude-plugin/marketplace.json"
PLUGIN_URL = "https://github.com/stayfixed/stayfixed-plugin.git"


def marketplace(sha: object = None, *, entries: int = 1) -> tuple[bytes, str]:
    """The marketplace's file: `entries` plugin entries named `stayfixed`, each a `url` source
    pinning `sha` beside its `ref`, or no `sha` when it is `None`."""
    source: dict[str, object] = {"source": "url", "url": PLUGIN_URL, "ref": "v1.2.3"}
    if sha is not None:
        source["sha"] = sha
    plugins = [{"name": "stayfixed", "source": source} for _ in range(entries)]
    text = json.dumps({"name": "stayfixed-marketplace", "plugins": plugins}, indent=2) + "\n"
    return text.encode("utf-8"), "100644"


def pinning(root: Path, sha: object, message: str = "pin") -> str:
    """A commit on `root`'s `HEAD` whose marketplace pins `sha`."""
    write(root, {MARKETPLACE: marketplace(sha)})
    return commit(root, message)


def written(git_dir: Path, commit_id: str) -> dict[str, tuple[bytes, str]]:
    """Every file of `commit_id`'s tree in `git_dir`, read by git: its bytes and its mode."""
    files = {}
    for record in git(git_dir, "ls-tree", "-r", "-z", commit_id).split("\0"):
        if record:
            meta, path = record.split("\t", 1)
            mode, _kind, obj = meta.split()
            files[path] = (git_bytes(git_dir, "cat-file", "blob", obj), mode)
    return files


def owner_config(text: str) -> None:
    """`text` appended to the test `HOME`'s `.gitconfig`: the owner's configuration, which only
    the code under test reads."""
    config = Path(os.environ["HOME"]) / ".gitconfig"
    config.write_text(config.read_text(encoding="utf-8") + text, encoding="utf-8")


def test_commit_text_is_exactly_the_documented_bytes() -> None:
    # Mutation (declared): `mutations/`'s "the plugin commit is dated a second after the epoch"
    # -> both texts differ in their author and committer lines.
    assert plugin_tree.commit_text("a" * 40, "b" * 40, "0.3.0") == (
        "tree aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\n"
        "parent bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb\n"
        "author stayfixed <release@stayfixed.invalid> 0 +0000\n"
        "committer stayfixed <release@stayfixed.invalid> 0 +0000\n"
        "\n"
        "stayfixed 0.3.0\n"
        "\n"
        "The plugin tree of stayfixed/stayfixed at v0.3.0.\n"
    )
    assert plugin_tree.commit_text("a" * 40, None, "0.3.0") == (
        "tree aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\n"
        "author stayfixed <release@stayfixed.invalid> 0 +0000\n"
        "committer stayfixed <release@stayfixed.invalid> 0 +0000\n"
        "\n"
        "stayfixed 0.3.0\n"
        "\n"
        "The plugin tree of stayfixed/stayfixed at v0.3.0.\n"
    )


def test_the_plugin_commit_is_what_git_computes(tmp_path: Path) -> None:
    # Mutations (declared): `mutations/`'s "the plugin commit is dated a second after the epoch"
    # -> the object git holds is not the literal text, and its id is not the one git computes;
    # "the plugin commit builds every file without its executable bit" -> the wrapper and the
    # launcher are written `100644`.
    root = plugin_source(tmp_path)
    head = git(root, "rev-parse", "HEAD").strip()
    git_dir = tmp_path / "plugin.git"
    made = plugin_tree.plugin_commit(root, "HEAD", git_dir)
    tree = git(git_dir, "rev-parse", f"{made.commit}^{{tree}}").strip()
    assert git(git_dir, "cat-file", "commit", made.commit) == literal(tree, None)
    assert made.commit == hashed(git_dir, literal(tree, None))
    assert written(git_dir, made.commit) == PLUGIN_FILES
    assert (made.rev, made.version, made.files, made.tree) == (head, "1.2.3", 10, tree)
    assert (made.parent, made.pinned) == (None, None)


def test_the_plugin_commit_is_the_same_on_every_run(tmp_path: Path) -> None:
    # No mutation of its own: nothing in the commit reads a clock, a path or a counter, which
    # `test_the_plugin_commit_is_what_git_computes` holds byte for byte. This pins it against one
    # added later, across two clones and two git dirs.
    root = plugin_source(tmp_path)
    clones = [tmp_path / "one", tmp_path / "two"]
    for clone in clones:
        git(tmp_path, "clone", "-q", str(root), str(clone))
    first, second = (
        plugin_tree.plugin_commit(clone, "HEAD", tmp_path / f"{clone.name}.git") for clone in clones
    )
    assert (first.commit, first.tree) == (second.commit, second.tree)
    assert first.commit != first.tree


def test_the_parent_is_the_sha_the_first_parent_pins(tmp_path: Path) -> None:
    # Mutation (declared): `mutations/`'s "the plugin commit takes its parent from the source
    # commit's own pin" -> the parent is `d`*40.
    root = plugin_source(tmp_path, {**PLUGIN_FILES, MARKETPLACE: marketplace("c" * 40)})
    pinning(root, "d" * 40)
    git_dir = tmp_path / "plugin.git"
    made = plugin_tree.plugin_commit(root, "HEAD", git_dir)
    assert (made.parent, made.pinned) == ("c" * 40, "d" * 40)
    tree = git(git_dir, "rev-parse", f"{made.commit}^{{tree}}").strip()
    assert git(git_dir, "cat-file", "commit", made.commit) == literal(tree, "c" * 40)


def test_a_first_release_has_no_parent(tmp_path: Path) -> None:
    # The first release's first parent pins no sha: its marketplace names the tag by `ref` alone.
    # No mutation of its own: a pin read where there is none is a refusal or a parent, and the
    # parent's mutations redden `test_the_parent_is_the_sha_the_first_parent_pins`.
    root = plugin_source(tmp_path, {**PLUGIN_FILES, MARKETPLACE: marketplace()})
    pinning(root, "d" * 40)
    git_dir = tmp_path / "plugin.git"
    made = plugin_tree.plugin_commit(root, "HEAD", git_dir)
    assert made.parent is None
    assert "\nparent " not in git(git_dir, "cat-file", "commit", made.commit)


def test_no_parent_ignores_the_history(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # Mutations (declared): `mutations/`'s "the plugin commit reads a parent under root_commit"
    # -> the call's parent is `c`*40; "the plugin commit command drops --no-parent" -> the
    # command's is.
    root = plugin_source(tmp_path, {**PLUGIN_FILES, MARKETPLACE: marketplace("c" * 40)})
    pinning(root, "d" * 40)
    made = plugin_tree.plugin_commit(root, "HEAD", tmp_path / "one.git", root_commit=True)
    assert made.parent is None
    argv = ["commit", "--root", str(root), "--rev", "HEAD", "--git-dir", str(tmp_path / "two.git")]
    assert plugin_tree.main([*argv, "--no-parent", "--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert (report["parent"], report["commit"]) == (None, made.commit)


def test_a_source_whose_first_parent_is_not_in_the_clone_is_refused(tmp_path: Path) -> None:
    # Mutation (declared): `mutations/`'s "the plugin commit reads a first parent the clone lacks
    # as none" -> the commit is built with no parent, which is another commit than the release's.
    root = plugin_source(tmp_path, {**PLUGIN_FILES, MARKETPLACE: marketplace("c" * 40)})
    pinning(root, "d" * 40)
    shallow = tmp_path / "shallow"
    git(tmp_path, "clone", "-q", "--depth", "1", f"file://{root}", str(shallow))
    assert git(shallow, "rev-parse", "--is-shallow-repository").strip() == "true"
    with pytest.raises(Refusal, match="fetch-depth: 2"):
        plugin_tree.plugin_commit(shallow, "HEAD", tmp_path / "plugin.git")


def document(plugins: object) -> tuple[bytes, str]:
    """A marketplace file whose `plugins` is `plugins`, as it is given."""
    text = json.dumps({"name": "stayfixed-marketplace", "plugins": plugins}) + "\n"
    return text.encode("utf-8"), "100644"


# A plugin entry whose source is a url pinning `c`*40, which a reader that skips what stands before
# it in `plugins` would read as the pin.
PINNED_ENTRY = {
    "name": "stayfixed",
    "source": {"source": "url", "url": PLUGIN_URL, "ref": "v1.2.3", "sha": "c" * 40},
}
NO_COMMIT_ID = ", which is no commit id of 40 lowercase hex digits"


@pytest.mark.parametrize(
    ("file", "wording", "whole"),
    [
        pytest.param(
            marketplace("C" * 40), f" pins sha {'C' * 40}{NO_COMMIT_ID}", True, id="upper-case"
        ),
        pytest.param(
            marketplace("c" * 39), f" pins sha {'c' * 39}{NO_COMMIT_ID}", True, id="39-characters"
        ),
        pytest.param(
            marketplace("c" * 64), f" pins sha {'c' * 64}{NO_COMMIT_ID}", True, id="64-characters"
        ),
        pytest.param(marketplace(1), f" pins sha a int{NO_COMMIT_ID}", True, id="a-number"),
        pytest.param(
            marketplace("c" * 40, entries=2),
            " has 2 entries named 'stayfixed'; the pin is read from exactly one",
            True,
            id="two-entries",
        ),
        pytest.param(
            document([{"name": "stayfixed", "source": "./"}]),
            " gives the entry 'stayfixed' a source that is no object; the pin is read from a url "
            "source",
            True,
            id="a-string-source",
        ),
        pytest.param(
            document(["another", PINNED_ENTRY]),
            " is valid JSON but its plugins is not a list of objects",
            True,
            id="an-entry-that-is-no-object",
        ),
        pytest.param(
            document("stayfixed"),
            " is valid JSON but its plugins is not a list of objects",
            True,
            id="plugins-a-string",
        ),
        pytest.param((b'{"plugins": [\n', "100644"), " is not valid JSON: ", False, id="not-json"),
    ],
)
def test_a_malformed_pinned_sha_is_refused(
    tmp_path: Path, file: tuple[bytes, str], wording: str, whole: bool
) -> None:
    # At the source commit itself, which has no parent, so no `hash-object` of a commit naming the
    # pin as its parent can refuse it first. Each case is refused in its own words, naming the
    # marketplace at the commit; the shapes refused are the ones `scripts/release.py` refuses of the
    # same entry. `not-json` is held to its start only: the rest is `json`'s own sentence.
    # Mutations (declared): `mutations/`'s "the plugin commit reads a pin that is no SHA-1 commit
    # id" -> the three strings are read as pins; "the plugin commit reads the pin from the first of
    # several entries" -> `two-entries` reads `c`*40; "the plugin commit reads a pin from a source
    # that is no object" -> `a-string-source` reads no pin; "the plugin commit skips plugins
    # entries that are no object" -> `an-entry-that-is-no-object` reads `c`*40.
    root = plugin_source(tmp_path, {**PLUGIN_FILES, MARKETPLACE: file})
    head = git(root, "rev-parse", "HEAD").strip()
    with pytest.raises(Refusal) as refused:
        plugin_tree.plugin_commit(root, "HEAD", tmp_path / "plugin.git")
    said = f"{MARKETPLACE} at {head} in {root}{wording}"
    assert str(refused.value) == said if whole else str(refused.value).startswith(said), str(
        refused.value
    )


def test_the_owner_s_object_format_does_not_reach_the_git_dir(tmp_path: Path) -> None:
    # Mutation (declared): `mutations/`'s "the plugin commit's git dir takes the owner's object
    # format" -> the git dir is SHA-256 and the commit's id is 64 characters.
    root = plugin_source(tmp_path)
    before = plugin_tree.plugin_commit(root, "HEAD", tmp_path / "before.git")
    owner_config("[init]\n\tdefaultObjectFormat = sha256\n")
    after = plugin_tree.plugin_commit(root, "HEAD", tmp_path / "after.git")
    assert len(after.commit) == 40
    assert after.commit == before.commit


def test_the_owner_s_line_endings_do_not_change_the_blobs(tmp_path: Path) -> None:
    # No mutation exists: `fast-import` applies no filter and writes no file, so no line of the
    # script converts a line ending. This guards a return to hashing a render, which
    # `core.autocrlf = input` converts (`hash-object --stdin-paths` in a bare repository).
    crlf = {"skills/crlf/SKILL.md": (b"a\r\nb\r\n", "100644")}
    root = plugin_source(tmp_path, {**PLUGIN_FILES, **crlf})
    owner_config("[core]\n\tautocrlf = input\n")
    git_dir = tmp_path / "plugin.git"
    made = plugin_tree.plugin_commit(root, "HEAD", git_dir)
    assert written(git_dir, made.commit) == {**PLUGIN_FILES, **crlf}


def test_members_differing_only_in_case_are_both_written(tmp_path: Path) -> None:
    # No mutation exists: no member is written to a filesystem, so none can collide with another.
    # This guards a return to hashing a render, which on a filesystem that folds case keeps one.
    root = plugin_source(tmp_path)
    plant_path(root, b"skills/A.md", "upper\n")
    plant_path(root, b"skills/a.md", "lower\n")
    git(root, "commit", "-q", "-m", "two names one case apart")
    git_dir = tmp_path / "plugin.git"
    made = plugin_tree.plugin_commit(root, "HEAD", git_dir)
    found = written(git_dir, made.commit)
    assert (found["skills/A.md"], found["skills/a.md"]) == (
        (b"upper\n", "100644"),
        (b"lower\n", "100644"),
    )


def test_the_owners_init_template_does_not_reach_the_git_dir(tmp_path: Path) -> None:
    # Mutation (declared): `mutations/`'s "the plugin commit's git dir is made from the owner's
    # init template" -> the template's files are copied into the git dir.
    root = plugin_source(tmp_path)
    template = tmp_path / "template"
    (template / "info").mkdir(parents=True)
    (template / "info" / "from-the-template").write_text("copied\n", encoding="utf-8")
    owner_config(f"[init]\n\ttemplateDir = {template}\n")
    git_dir = tmp_path / "plugin.git"
    plugin_tree.plugin_commit(root, "HEAD", git_dir)
    assert not (git_dir / "info" / "from-the-template").exists()


def test_the_owners_hooks_do_not_run_in_the_git_dir(tmp_path: Path) -> None:
    # Mutation (declared): `mutations/`'s "the plugin commit runs the owner's hooks in its git
    # dir" -> the owner's `reference-transaction` hook runs as `init` writes `HEAD`.
    root = plugin_source(tmp_path)
    hooks, fired = tmp_path / "hooks", tmp_path / "fired"
    hooks.mkdir()
    (hooks / "reference-transaction").write_text(f'#!/bin/sh\necho "$1" >> "{fired}"\n')
    (hooks / "reference-transaction").chmod(0o755)
    owner_config(f"[core]\n\thooksPath = {hooks}\n")
    plugin_tree.plugin_commit(root, "HEAD", tmp_path / "plugin.git")
    assert not fired.exists(), fired.read_text(encoding="utf-8")


def test_an_explicit_safe_bare_repository_does_not_refuse_the_git_dir(tmp_path: Path) -> None:
    # Mutation (declared): `mutations/`'s "the plugin commit finds its git dir rather than naming
    # it" -> `safe.bareRepository = explicit` refuses the bare repository `git -C` finds. Twice:
    # the second call meets a git dir that exists.
    root = plugin_source(tmp_path)
    owner_config("[safe]\n\tbareRepository = explicit\n")
    git_dir = tmp_path / "plugin.git"
    first = plugin_tree.plugin_commit(root, "HEAD", git_dir)
    assert plugin_tree.plugin_commit(root, "HEAD", git_dir) == first


def test_a_commit_that_gave_no_answer_is_refused_in_no_answer_s_words(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Mutation (declared): `mutations/`'s "the plugin commit says a git that gave no answer
    # exited" -> the refusal says `-1` and not why.
    root = plugin_source(tmp_path)
    real = plugin_tree.git_run

    def silent(where: Path, *args: str, **options: Any) -> tuple[int, str]:
        if "hash-object" in args:
            return -1, ""
        code, answer = real(where, *args, **options)
        return code, answer

    monkeypatch.setattr(plugin_tree, "git_run", silent)
    with pytest.raises(Refusal) as refused:
        plugin_tree.plugin_commit(root, "HEAD", tmp_path / "plugin.git")
    assert gitenv.NO_ANSWER in str(refused.value)


@pytest.mark.parametrize("state", ["a-file-inside", "a-sha256-repository"])
def test_a_half_made_git_dir_is_refused_and_an_empty_one_is_made(
    tmp_path: Path, state: str
) -> None:
    # Mutation (declared): `mutations/`'s "the plugin commit writes into a git dir of another
    # object format" -> the SHA-256 repository is written into. A directory holding a file that
    # is no repository fails git's own `rev-parse`, so no line of the script holds it alone.
    root = plugin_source(tmp_path)
    empty = tmp_path / "empty.git"
    empty.mkdir()
    plugin_tree.plugin_commit(root, "HEAD", empty)
    assert git(empty, "rev-parse", "--is-bare-repository").strip() == "true"
    git_dir = tmp_path / "plugin.git"
    if state == "a-file-inside":
        git_dir.mkdir()
        (git_dir / "left-over").write_bytes(b"half\n")
    else:
        git(tmp_path, "init", "-q", "--bare", "--object-format=sha256", str(git_dir))
    with pytest.raises(Refusal) as refused:
        plugin_tree.plugin_commit(root, "HEAD", git_dir)
    assert str(git_dir) in str(refused.value)
    # Refused before anything is written, in the words that say what the git dir must be: a later
    # check of an id's length would refuse a SHA-256 repository too, after writing into it.
    assert "nor a bare SHA-1 repository" in str(refused.value)


def test_a_second_commit_into_the_same_git_dir_succeeds(tmp_path: Path) -> None:
    # No mutation of its own: a git dir that exists is read by `rev-parse` and written by the same
    # gits as an empty one, and `test_a_half_made_git_dir_is_refused_and_an_empty_one_is_made`
    # holds the checks it passes.
    root = plugin_source(tmp_path)
    git_dir = tmp_path / "plugin.git"
    first = plugin_tree.plugin_commit(root, "HEAD", git_dir)
    write(root, {"README.md": (b"# second\n", "100644")})
    commit(root, "the second")
    second = plugin_tree.plugin_commit(root, "HEAD", git_dir)
    assert first.commit != second.commit
    for made in (first, second):
        assert git(git_dir, "cat-file", "-t", made.commit).strip() == "commit"


def test_require_pin_exits_1_when_the_pin_is_another_commit(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # Mutation (declared): `mutations/`'s "the plugin commit command holds the pin to the parent"
    # -> a pin left as the previous release's commit, which is the parent, passes. The ids are
    # computed by git over the literal texts.
    root = plugin_source(tmp_path)
    tree = git(root, "rev-parse", "HEAD^{tree}").strip()
    pinned = hashed(root, literal(tree, None))
    pinning(root, pinned)
    git_dir, listing = tmp_path / "plugin.git", tmp_path / "plugin-tree.txt"
    argv = ["commit", "--root", str(root), "--git-dir", str(git_dir)]
    assert plugin_tree.main([*argv, "--rev", "HEAD", "--require-pin", "--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert set(report) == {
        "summary",
        "format",
        "rev",
        "version",
        "files",
        "tree",
        "parent",
        "commit",
        "pinned",
    }
    assert (report["format"], report["commit"], report["pinned"]) == (
        "stayfixed-plugin-tree 1",
        pinned,
        pinned,
    )
    assert (report["tree"], report["files"], report["parent"]) == (tree, 10, None)

    # The release after it, its pin left as it was: the parent and the pin are the same commit.
    git(root, "commit", "-q", "--allow-empty", "-m", "a release that did not pin")
    expected = hashed(root, literal(tree, pinned))
    pinned_again = [*argv, "--rev", "HEAD", "--manifest-file", str(listing)]
    assert plugin_tree.main(pinned_again) == 0
    capsys.readouterr()
    listing.unlink()
    assert plugin_tree.main([*pinned_again, "--require-pin"]) == 1
    said = capsys.readouterr().err
    assert pinned in said and expected in said, said
    # Refused after the objects and the manifest file were written.
    assert git(git_dir, "cat-file", "-t", expected).strip() == "commit"
    assert listing.read_bytes().startswith(b"stayfixed-plugin-tree 1\n")
