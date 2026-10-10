"""`scripts/publish_plugin.py`: the attested plugin tree pushed to its own repository, and nothing
else.

Every case builds a scratch source repository holding a file under each of the plugin's nine paths
and a tag `v1.2.3` whose `plugin.json` says `1.2.3`, and a bare repository in `tmp_path` stands for
the plugin repository. `gh` is never run: the runner is a composite that records every argv it is
handed, answers `gh` from a `Recorder` and runs the rest — `git`'s network half and
`plugin_tree.py` — for real. The plumbing `publish` runs through `gitenv.git_run` reaches no runner,
so a case that wants "nothing ran" reads the composite's `calls`, and one that wants "nothing was
written" reads the scratch directory and the remote.

`git_run` hands git only `PATH`, `HOME`, `LANG`, `LC_ALL` and `SYSTEMROOT`, so the commit's author
comes from the test `HOME`'s `.gitconfig`, which `_an_owner_identity` writes for every case.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from stayfixed.errors import Refusal
from stayfixed.runner import Completed, subprocess_runner
from tests.gitfixture import MAINTENANCE_OFF, git, gitconfig, needs_git
from tests.runners import Recorder
from tests.scriptload import plugin_tree as _tree_script
from tests.scriptload import publish_plugin as _script

publish_plugin = _script()
plugin_tree = _tree_script()

pytestmark = needs_git

TAG = "v1.2.3"
# One file under each of the nine paths, with its git mode: the wrapper and the launcher are
# executable. Spelled here rather than read from `plugin_tree.PLUGIN_PATHS`.
PLUGIN_FILES: dict[str, tuple[bytes, str]] = {
    ".claude-plugin/plugin.json": (b'{"name": "stayfixed", "version": "1.2.3"}\n', "100644"),
    ".codex-plugin/plugin.json": (b'{"name": "stayfixed", "version": "1.2.3"}\n', "100644"),
    "hooks/hooks.json": (b"{}\n", "100644"),
    "hooks/run-hook.sh": (b"#!/bin/sh\nexit 0\n", "100755"),
    "scripts/stayfixed": (b"#!/usr/bin/env python3\n", "100755"),
    "src/stayfixed/__init__.py": (b'__version__ = "1.2.3"\n', "100644"),
    "skills/close-bug/SKILL.md": (b"# close a bug\n", "100644"),
    "agents/navigator.md": (b"# navigator\n", "100644"),
    "README.md": (b"# stayfixed\n", "100644"),
    "LICENSE": (b"MIT\n", "100644"),
}
# What the source repository holds beside the plugin, and the plugin repository must not.
NOT_PLUGIN: dict[str, tuple[bytes, str]] = {
    "docs/guide.md": (b"# guide\n", "100644"),
    "tests/test_it.py": (b"def test_it(): pass\n", "100644"),
    ".claude-plugin/marketplace.json": (b"{}\n", "100644"),
}
OWNER = "Owner <owner@example.com>"


@dataclass
class Composite:
    """The runner `publish` is handed: every argv recorded in `calls` before it is dispatched,
    `gh` answered by `gh`, and every other program run for real."""

    gh: Recorder = field(default_factory=Recorder)
    calls: list[list[str]] = field(default_factory=list)

    def launch(self, argv: list[str], cwd: Path) -> Completed:
        self.calls.append(argv)
        if argv[:1] == ["gh"]:
            return self.gh.launch(argv, cwd)
        return subprocess_runner().launch(argv, cwd)


def _home() -> Path:
    return Path(os.environ["HOME"])


def _global_config(text: str) -> None:
    """Append `text` to the test `HOME`'s `.gitconfig`, which the product's `git` reads."""
    config = _home() / ".gitconfig"
    config.write_text(config.read_text(encoding="utf-8") + text, encoding="utf-8")


@pytest.fixture(autouse=True)
def _an_owner_identity() -> None:
    _global_config("[user]\n\tname = Owner\n\temail = owner@example.com\n")


def write(root: Path, files: dict[str, tuple[bytes, str]]) -> None:
    for path, (content, mode) in files.items():
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        target.chmod(0o755 if mode == "100755" else 0o644)


def commit(root: Path, message: str = "a commit") -> str:
    git(root, "add", "-A")
    git(root, "commit", "-q", "--allow-empty", "-m", message)
    return git(root, "rev-parse", "HEAD").strip()


def source_repository(tmp_path: Path, files: dict[str, tuple[bytes, str]] | None = None) -> Path:
    """A repository whose one commit holds the plugin's files and its neighbours, tagged `v1.2.3`
    by an annotated tag, so the tag's commit is reached through a peel."""
    root = tmp_path / "source"
    root.mkdir()
    git(root, "init", "-q", "-b", "dev")
    write(root, {**PLUGIN_FILES, **NOT_PLUGIN, **(files or {})})
    commit(root)
    git(root, "tag", "-a", TAG, "-m", TAG)
    return root


def tag_commit(root: Path, tag: str = TAG) -> str:
    return git(root, "rev-parse", f"{tag}^{{commit}}").strip()


def bare_remote(tmp_path: Path) -> Path:
    remote = tmp_path / "remote.git"
    git(tmp_path, "init", "-q", "--bare", str(remote))
    return remote


def refs(remote: Path) -> dict[str, str]:
    listing = git(remote, "for-each-ref", "--format=%(refname) %(objectname)")
    return dict(line.split(" ", 1) for line in listing.splitlines())


def seed(
    tmp_path: Path,
    remote: Path,
    files: dict[str, tuple[bytes, str]],
    *,
    tag: str | None = TAG,
    main: str = "same",
) -> dict[str, str]:
    """Put a commit holding `files` on the remote: under `tag`, and under `main` too when `main` is
    "same", or a later commit there when it is "elsewhere". Returns the remote's refs."""
    work = tmp_path / "seed"
    work.mkdir()
    git(work, "init", "-q", "-b", "main")
    write(work, files)
    first = commit(work, "an earlier publish")
    pushed = [f"{first}:refs/tags/{tag}"] if tag is not None else []
    if main == "same":
        pushed.append(f"{first}:refs/heads/main")
    else:
        pushed.append(f"{commit(work, 'a later commit on main')}:refs/heads/main")
    git(work, "push", "-q", str(remote), *pushed)
    return refs(remote)


def publish(
    source: Path,
    remote: Path,
    scratch: Path,
    *,
    yes: bool = True,
    tag: str = TAG,
    runner: Composite | None = None,
) -> tuple[Any, Composite]:
    runner = runner if runner is not None else Composite()
    scratch.mkdir(parents=True, exist_ok=True)
    done = publish_plugin.publish(
        source, tag, remote=str(remote), yes=yes, runner=runner, scratch=scratch
    )
    return done, runner


def listed(root: Path, rev: str, **kwargs: bool) -> dict[str, tuple[bytes, str]]:
    return {m.path: (m.content, m.mode) for m in plugin_tree.members(root, rev, **kwargs)}


def ran(runner: Composite, word: str) -> list[list[str]]:
    """The recorded argvs that ran `git <word>`, wherever the global options put it."""
    return [argv for argv in runner.calls if argv[:1] == ["git"] and word in argv]


# --- A publish that goes through ---------------------------------------------------------------


def test_a_verified_tree_is_pushed_with_its_tag_and_reads_back_whole(tmp_path: Path) -> None:
    # Mutation (declared): every mode taken as `100644` when the tree is built -> the read-back's
    # refusal fires first, and its sentence names the line whose mode is lost
    # ("100755 … hooks/run-hook.sh"), so the run that reddens says why.
    source, remote = source_repository(tmp_path), bare_remote(tmp_path)
    done, _ = publish(source, remote, tmp_path / "scratch")
    pushed = refs(remote)
    assert pushed == {"refs/heads/main": done.commit, f"refs/tags/{TAG}": done.commit}
    assert (done.tag, done.files, done.pushed, done.already) == (TAG, 10, True, False)
    assert listed(remote, TAG, exact=True) == listed(source, TAG) == PLUGIN_FILES
    assert listed(remote, TAG)["hooks/run-hook.sh"][1] == "100755"
    assert listed(remote, TAG)["scripts/stayfixed"][1] == "100755"
    # The plugin repository's first commit has no parent; its message and author say where it
    # came from and who pushed it.
    assert git(remote, "rev-list", "--parents", "-n", "1", done.commit).split() == [done.commit]
    sha = tag_commit(source)
    assert git(remote, "log", "-1", "--format=%B", done.commit) == (
        "stayfixed 1.2.3\n\n"
        f"Generated from stayfixed/stayfixed at {sha} ({TAG}) by scripts/publish_plugin.py.\n\n"
    )
    assert git(remote, "log", "-1", "--format=%an <%ae>", done.commit).strip() == OWNER


def test_without_yes_the_remote_is_unchanged(tmp_path: Path) -> None:
    # Mutation (declared): the push's `if yes:` -> `if True:` -> the remote gains both refs.
    source, remote = source_repository(tmp_path), bare_remote(tmp_path)
    scratch = tmp_path / "scratch"
    done, runner = publish(source, remote, scratch, yes=False)
    assert refs(remote) == {}
    assert ran(runner, "push") == []
    assert (done.pushed, done.already, done.files) == (False, False, 10)
    # The commit the dry run reports is the one it built, and would push.
    built = scratch / "plugin.git"
    assert git(built, "rev-parse", "--verify", f"{done.commit}^{{commit}}").strip() == done.commit
    assert listed(built, done.commit, exact=True) == PLUGIN_FILES


def test_the_tree_is_rendered_from_the_tag_and_not_the_disk(tmp_path: Path) -> None:
    # Mutation: the render asked for `HEAD` of the checkout's disk is not one this script can
    # make — `plugin_tree.py` reads a commit and nothing else (its own tests hold that); what this
    # holds is that `publish` hands it the tag's commit, as the next case does against a branch.
    source, remote = source_repository(tmp_path), bare_remote(tmp_path)
    (source / "README.md").write_bytes(b"edited on disk\n")
    write(source, {"skills/staged/SKILL.md": (b"staged only\n", "100644")})
    git(source, "add", "skills/staged/SKILL.md")
    publish(source, remote, tmp_path / "scratch")
    assert listed(remote, TAG, exact=True) == PLUGIN_FILES


def test_a_branch_named_like_the_tag_does_not_stand_in_for_it(tmp_path: Path) -> None:
    # git's own order reads a tag before a branch of one name, so resolving the bare name would
    # pass this too; the mutation that a branch standing in for an absent tag reddens is in
    # `test_an_unknown_tag_is_refused_before_anything_runs`.
    source, remote = source_repository(tmp_path), bare_remote(tmp_path)
    write(source, {"README.md": (b"# on the branch\n", "100644")})
    git(source, "branch", "-q", "elsewhere")
    git(source, "checkout", "-q", "elsewhere")
    branch_commit = commit(source, "the branch's commit")
    git(source, "branch", "-q", TAG, branch_commit)
    publish(source, remote, tmp_path / "scratch")
    assert listed(remote, TAG, exact=True)["README.md"] == PLUGIN_FILES["README.md"]


def test_the_attestation_is_asked_for_this_workflow_this_tag_and_this_commit(
    tmp_path: Path,
) -> None:
    # Mutations (declared), one entry each: `--source-ref` dropped; `--source-digest` dropped;
    # `--deny-self-hosted-runners` dropped; `--signer-workflow` dropped.
    source, remote = source_repository(tmp_path), bare_remote(tmp_path)
    _, runner = publish(source, remote, tmp_path / "scratch", yes=False)
    asked = [argv for argv in runner.gh.calls if argv[:3] == ["gh", "attestation", "verify"]]
    assert len(asked) == 1, runner.gh.calls
    argv = asked[0]

    def value(option: str) -> str:
        assert argv.count(option) == 1, argv
        return argv[argv.index(option) + 1]

    sha = tag_commit(source)
    assert len(sha) == 40
    assert value("--repo") == "stayfixed/stayfixed"
    assert value("--signer-workflow") == "stayfixed/stayfixed/.github/workflows/release.yml"
    assert value("--source-ref") == f"refs/tags/{TAG}"
    assert value("--source-digest") == sha
    assert "--deny-self-hosted-runners" in argv
    # The file it is asked about is the render's manifest: the plugin's files at the tag.
    expected = plugin_tree.manifest(plugin_tree.members(source, sha)).encode("utf-8")
    assert Path(argv[3]).read_bytes() == expected
    assert expected.startswith(b"stayfixed-plugin-tree 1\n")


def test_a_second_publish_of_the_same_tag_pushes_nothing(tmp_path: Path) -> None:
    # Mutations (declared): a tag already on the remote treated as absent -> the second run builds
    # again and its push is refused by the remote, whose tag exists; the attestation asked after
    # the remote is listed -> the ordering below.
    source, remote = source_repository(tmp_path), bare_remote(tmp_path)
    first, _ = publish(source, remote, tmp_path / "first")
    before = refs(remote)
    second, runner = publish(source, remote, tmp_path / "second")
    assert (second.already, second.pushed, second.commit) == (True, False, first.commit)
    assert refs(remote) == before
    assert ran(runner, "push") == []
    # The attestation is asked again before the remote is: a re-run trusts nothing it found.
    verify = next(
        i for i, argv in enumerate(runner.calls) if argv[:3] == ["gh", "attestation", "verify"]
    )
    listing = next(i for i, argv in enumerate(runner.calls) if "ls-remote" in argv)
    assert verify < listing


def test_the_previous_release_is_replaced_whole(tmp_path: Path) -> None:
    # Mutation: the parent left off the commit -> the remote refuses a push that is not a fast
    # forward, and the refusal reddens this before its parent assertion is reached.
    source, remote = source_repository(tmp_path), bare_remote(tmp_path)
    earlier = {**PLUGIN_FILES, "skills/old/SKILL.md": (b"# gone in 1.2.3\n", "100644")}
    before = seed(tmp_path, remote, earlier, tag="v1.2.2")
    done, _ = publish(source, remote, tmp_path / "scratch")
    assert listed(remote, TAG, exact=True) == PLUGIN_FILES
    assert git(remote, "rev-parse", f"{done.commit}^").strip() == before["refs/heads/main"]
    assert refs(remote)["refs/tags/v1.2.2"] == before["refs/tags/v1.2.2"]


# --- What the owner's own git configuration cannot change -----------------------------------------


def test_the_commit_ignores_the_owners_line_ending_and_hook_configuration(tmp_path: Path) -> None:
    # Mutations (declared): `--no-filters` dropped -> `core.autocrlf` turns each CRLF into LF as
    # the blob is written, and the read-back refuses; `-c core.hooksPath=/dev/null` dropped ->
    # the owner's `pre-push` runs and refuses the push.
    crlf = {
        "README.md": (b"# stayfixed\r\nline two\r\n", "100644"),
        "skills/close-bug/SKILL.md": (b"# close a bug\r\n", "100644"),
    }
    source, remote = source_repository(tmp_path, crlf), bare_remote(tmp_path)
    hooks = _home() / "hooks"
    hooks.mkdir()
    (hooks / "pre-push").write_text("#!/bin/sh\necho refused by pre-push >&2\nexit 1\n")
    (hooks / "pre-push").chmod(0o755)
    (_home() / "ignore").write_text("*.md\n", encoding="utf-8")
    _global_config(
        f"[core]\n\tautocrlf = true\n\thooksPath = {hooks}\n\texcludesFile = {_home() / 'ignore'}\n"
    )
    done, _ = publish(source, remote, tmp_path / "scratch")
    assert done.pushed
    assert listed(remote, TAG, exact=True) == {**PLUGIN_FILES, **crlf}


def test_a_missing_git_identity_is_refused_before_anything_is_pushed(tmp_path: Path) -> None:
    # Mutation: none of its own. Without an identity `git commit-tree` writes no commit and exits
    # non-zero, so there is nothing later to push; what this holds is the sentence, and that the
    # remote is untouched.
    source, remote = source_repository(tmp_path), bare_remote(tmp_path)
    # The maintenance keys `tests/conftest.py` writes stay; the identity the fixture added goes.
    config = gitconfig(MAINTENANCE_OFF) + "[user]\n\tuseConfigOnly = true\n"
    (_home() / ".gitconfig").write_text(config, encoding="utf-8")
    with pytest.raises(Refusal, match="git commit-tree exited") as refused:
        publish(source, remote, tmp_path / "scratch")
    assert "user.name" in str(refused.value)
    assert "global git configuration" in str(refused.value)
    assert refs(remote) == {}


def test_a_main_that_moved_before_the_fetch_is_refused_as_a_race(tmp_path: Path) -> None:
    # Mutation (declared): the parent's presence not checked after the fetch -> `commit-tree -p`
    # names an object the scratch repository lacks, exits non-zero, and the refusal blames the
    # identity instead. The listing names a `main` the remote no longer has, which is what a
    # `main` force-moved between `ls-remote` and the fetch leaves behind.
    source, remote = source_repository(tmp_path), bare_remote(tmp_path)
    before = seed(tmp_path, remote, PLUGIN_FILES, tag=None)
    gone = "1" * 40
    runner = _Listing(listing=f"{gone}\trefs/heads/main\n")
    with pytest.raises(Refusal, match="main moved on the remote") as refused:
        publish(source, remote, tmp_path / "scratch", runner=runner)
    assert gone in str(refused.value)
    assert "run the command again" in str(refused.value)
    assert refs(remote) == before


# --- Refusals before anything runs ------------------------------------------------------------


def test_an_unknown_tag_is_refused_before_anything_runs(tmp_path: Path) -> None:
    # Mutation (declared): the tag resolved by its bare name rather than under `refs/tags/` -> the
    # branch `v2.0.0`, whose `plugin.json` says 2.0.0, stands in for the tag that does not exist.
    source, remote = source_repository(tmp_path), bare_remote(tmp_path)
    write(source, {".claude-plugin/plugin.json": (b'{"version": "2.0.0"}\n', "100644")})
    git(source, "branch", "-q", "v2.0.0", commit(source, "two"))
    runner = Composite()
    with pytest.raises(Refusal, match=r"v2\.0\.0"):
        publish(source, remote, tmp_path / "scratch", tag="v2.0.0", runner=runner)
    assert runner.calls == []
    assert list((tmp_path / "scratch").iterdir()) == []


def test_a_tag_whose_version_is_another_is_refused(tmp_path: Path) -> None:
    # Mutation (declared): the version comparison skipped -> the render runs.
    source, remote = source_repository(tmp_path), bare_remote(tmp_path)
    git(source, "tag", "v1.2.4")
    runner = Composite()
    with pytest.raises(Refusal, match=r"1\.2\.3") as refused:
        publish(source, remote, tmp_path / "scratch", tag="v1.2.4", runner=runner)
    assert "v1.2.4" in str(refused.value)
    assert runner.calls == []


@pytest.mark.parametrize("tag", ["v1.2.3\n", "v1.2.3-rc1", "v\N{ARABIC-INDIC DIGIT ONE}.2.3"])
def test_a_tag_that_is_not_a_plain_version_is_refused(tmp_path: Path, tag: str) -> None:
    # Mutations (declared): `re.fullmatch` -> `re.match` admits `v1.2.3-rc1`; `[0-9]` -> `\d`
    # admits the Arabic-Indic digit. Each tag git can name is made to exist, with a `plugin.json`
    # whose version spells it, so only the pattern stands between it and the render.
    source, remote = source_repository(tmp_path), bare_remote(tmp_path)
    if "\n" not in tag:
        version = tag.removeprefix("v")
        body = f'{{"version": "{version}"}}\n'.encode()
        write(source, {".claude-plugin/plugin.json": (body, "100644")})
        git(source, "tag", tag, commit(source, "a version that is not plain"))
    runner = Composite()
    with pytest.raises(Refusal, match="plain version"):
        publish(source, remote, tmp_path / "scratch", tag=tag, runner=runner)
    assert runner.calls == []


# --- Refusals at the attestation and the read-back ------------------------------------------------


def test_a_refused_attestation_stops_before_anything_is_fetched(tmp_path: Path) -> None:
    # Mutation (declared): the verify's exit code ignored -> the remote is listed, and pushed to.
    source, remote = source_repository(tmp_path), bare_remote(tmp_path)
    scratch = tmp_path / "scratch"
    said = "no attestations found for the subject"
    gh = Recorder(answers={"gh attestation verify": Completed(1, "", f"{said}\nsecond line\n")})
    runner = Composite(gh=gh)
    with pytest.raises(Refusal) as refused:
        publish(source, remote, scratch, runner=runner)
    assert said in str(refused.value)
    assert "could not check" in str(refused.value)
    for word in ("ls-remote", "fetch", "push"):
        assert ran(runner, word) == [], word
    assert not (scratch / "plugin.git").exists()
    assert refs(remote) == {}


@pytest.mark.parametrize(
    "written",
    [b"stayfixed-plugin-tree 1\ngarbage\n", b"stayfixed-plugin-tree 1\n100644 ab \xff\n"],
    ids=["a-line-of-one-field", "not-utf-8"],
)
def test_a_manifest_that_cannot_be_read_is_refused(tmp_path: Path, written: bytes) -> None:
    # Mutation: the two catches removed -> a `ValueError` or `UnicodeDecodeError` leaves
    # `publish` instead of a `Refusal`, which the CLI frame reports as an internal error. No
    # entry: the manifest is `plugin_tree.py`'s own output, so only an edit after the render
    # reaches either, and the exit code is 2 both ways.
    source, remote = source_repository(tmp_path), bare_remote(tmp_path)
    scratch = tmp_path / "scratch"

    def rewrite(argv: list[str], cwd: Path) -> None:
        (scratch / "plugin-tree.txt").write_bytes(written)

    runner = Composite(gh=Recorder(on_call=rewrite))
    with pytest.raises(Refusal, match="stayfixed-plugin-tree 1"):
        publish(source, remote, scratch, runner=runner)
    assert ran(runner, "ls-remote") == []


def test_a_rendered_file_changed_after_the_attestation_is_refused_by_the_read_back(
    tmp_path: Path,
) -> None:
    # Mutation (declared): the read-back's comparison skipped -> the edited file is pushed. The
    # edit lands while `gh` is being asked, after the render and before the commit is built: the
    # one window in which the attested manifest and the files on disk can part.
    source, remote = source_repository(tmp_path), bare_remote(tmp_path)
    scratch = tmp_path / "scratch"

    def edit(argv: list[str], cwd: Path) -> None:
        (scratch / "tree" / "README.md").write_bytes(b"changed after the attestation\n")

    runner = Composite(gh=Recorder(on_call=edit))
    with pytest.raises(Refusal, match=r"README\.md") as refused:
        publish(source, remote, scratch, runner=runner)
    assert "nothing was pushed" in str(refused.value)
    assert refs(remote) == {}
    assert ran(runner, "push") == []


def test_a_manifest_in_another_format_is_not_read(tmp_path: Path) -> None:
    # Mutation: none of its own: a format line `plugin_tree.py` does not write is reached only by
    # an edit to the file after the render, which is what this case makes; without the check the
    # lines are read as this format's and the read-back refuses the commit built from them.
    source, remote = source_repository(tmp_path), bare_remote(tmp_path)
    scratch = tmp_path / "scratch"

    def reformat(argv: list[str], cwd: Path) -> None:
        manifest = scratch / "plugin-tree.txt"
        manifest.write_bytes(manifest.read_bytes().replace(b" 1\n", b" 2\n", 1))

    runner = Composite(gh=Recorder(on_call=reformat))
    with pytest.raises(Refusal, match="does not open with 'stayfixed-plugin-tree 1'"):
        publish(source, remote, scratch, runner=runner)
    assert ran(runner, "ls-remote") == []


# --- What the remote already holds ----------------------------------------------------------------


def test_a_remote_commit_holding_a_path_outside_the_plugin_is_not_already_published(
    tmp_path: Path,
) -> None:
    # Mutation (declared): `--exact` dropped from the remote's manifest -> the extra path is not
    # read, the manifests agree, and the run reports "already published".
    source, remote = source_repository(tmp_path), bare_remote(tmp_path)
    before = seed(tmp_path, remote, {**PLUGIN_FILES, ".mcp.json": (b"{}\n", "100644")})
    runner = Composite()
    with pytest.raises(Refusal, match=r"\.mcp\.json"):
        publish(source, remote, tmp_path / "scratch", runner=runner)
    assert refs(remote) == before
    assert ran(runner, "push") == []


def test_a_tag_on_the_remote_with_another_tree_is_refused(tmp_path: Path) -> None:
    # Mutation (declared): a tag present on the remote treated as absent -> the run goes on to
    # build and push, and the remote refuses the tag that exists, with git's sentence rather than
    # this one.
    source, remote = source_repository(tmp_path), bare_remote(tmp_path)
    other = {**PLUGIN_FILES, "README.md": (b"# another readme\n", "100644")}
    before = seed(tmp_path, remote, other)
    runner = Composite()
    with pytest.raises(Refusal, match=r"README\.md") as refused:
        publish(source, remote, tmp_path / "scratch", runner=runner)
    assert "another tree" in str(refused.value)
    assert refs(remote) == before
    assert ran(runner, "push") == []


def test_a_tag_on_the_remote_whose_main_is_elsewhere_is_refused(tmp_path: Path) -> None:
    # Mutation (declared): `main`'s commit not compared -> "already published" over a `main` that
    # names another commit.
    source, remote = source_repository(tmp_path), bare_remote(tmp_path)
    before = seed(tmp_path, remote, PLUGIN_FILES, main="elsewhere")
    runner = Composite()
    with pytest.raises(Refusal, match="main is at") as refused:
        publish(source, remote, tmp_path / "scratch", runner=runner)
    assert before["refs/heads/main"] in str(refused.value)
    assert refs(remote) == before
    assert ran(runner, "push") == []


@dataclass
class _Listing(Composite):
    """The composite, with `ls-remote` answered from `listing` rather than by a remote."""

    listing: str = ""

    def launch(self, argv: list[str], cwd: Path) -> Completed:
        if "ls-remote" in argv:
            self.calls.append(argv)
            return Completed(0, self.listing, "")
        return super().launch(argv, cwd)


def test_a_listing_that_names_no_object_is_refused(tmp_path: Path) -> None:
    # Mutation: the object-name check dropped -> the listing is taken for a `main` to build on,
    # the run goes on to fetch it from a remote that has none, and stops there with git's
    # sentence rather than this one. No entry: what the check keeps out is a name the remote
    # chose reaching `commit-tree -p`, and a remote that lies about `main` is refused by the
    # fetch or by the atomic push as well.
    source, remote = source_repository(tmp_path), bare_remote(tmp_path)
    runner = _Listing(listing="--upload-pack=x\trefs/heads/main\n")
    with pytest.raises(Refusal, match="answered '--upload-pack=x' for refs/heads/main"):
        publish(source, remote, tmp_path / "scratch", runner=runner)
    assert ran(runner, "fetch") == []


def test_a_rejected_push_moves_no_ref(tmp_path: Path) -> None:
    # Mutation (declared): `--atomic` dropped -> the remote takes `main` and refuses only the tag.
    source, remote = source_repository(tmp_path), bare_remote(tmp_path)
    hook = remote / "hooks" / "update"
    hook.write_text(
        '#!/bin/sh\ncase "$1" in refs/tags/*) echo "tags are refused here" >&2; exit 1;; esac\n'
    )
    hook.chmod(0o755)
    with pytest.raises(Refusal, match="git push") as refused:
        publish(source, remote, tmp_path / "scratch")
    assert "tags are refused here" in str(refused.value)
    assert refs(remote) == {}


# --- The command line -----------------------------------------------------------------------------


def test_the_cli_refuses_a_tag_that_is_not_a_plain_version(
    capsys: pytest.CaptureFixture[str],
) -> None:
    # No mutation: the refusal is the CLI frame's (`stayfixed.cli.run`), whose own tests hold how
    # a `Refusal` prints under `--json`, and the pattern's two entries redden
    # `test_a_tag_that_is_not_a_plain_version_is_refused`. What this holds is that the script's
    # `main` goes through that frame, and no one line of the script can stop it without also
    # breaking the dry-run case below.
    assert publish_plugin.main(["--tag", "v1.2", "--json"]) == 2
    out = capsys.readouterr().out
    assert '"error": "refused"' in out
    assert "plain version" in out


def test_the_cli_says_what_a_dry_run_would_push(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # Mutation (declared): the push's `if yes:` -> `if True:` -> the dry run pushes, and says
    # "pushed" rather than "would push".
    source, remote = source_repository(tmp_path), bare_remote(tmp_path)
    monkeypatch.setattr(publish_plugin, "ROOT", source)
    monkeypatch.setattr(publish_plugin, "subprocess_runner", Composite)
    assert publish_plugin.main(["--tag", TAG, "--remote", str(remote)]) == 0
    said = capsys.readouterr().out
    assert said.startswith("would push 10 files as ")
    assert f"to {remote}: main and {TAG}" in said
    assert "--yes" in said
    assert refs(remote) == {}


def test_a_relative_remote_is_the_one_beside_the_owner_and_not_the_scratch_repository(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # Mutation: `remote_argument` returning its argument unchanged -> git, run with `-C` in the
    # scratch repository, looks for `remote.git` there, and the listing is refused.
    source, remote = source_repository(tmp_path), bare_remote(tmp_path)
    monkeypatch.setattr(publish_plugin, "ROOT", source)
    monkeypatch.setattr(publish_plugin, "subprocess_runner", Composite)
    monkeypatch.chdir(tmp_path)
    assert publish_plugin.main(["--tag", TAG, "--remote", "remote.git"]) == 0
    said = capsys.readouterr().out
    assert f"to {remote.resolve()}: main and {TAG}" in said
    assert refs(remote) == {}


@pytest.mark.parametrize(
    "remote",
    [
        "git@github.com:stayfixed/stayfixed-plugin.git",
        "https://github.com/stayfixed/stayfixed-plugin.git",
        "file:///srv/plugin.git",
        "host:remote.git",
        "absent.git",
    ],
)
def test_a_url_an_scp_like_remote_or_an_absent_path_is_given_as_it_is(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, remote: str
) -> None:
    # Mutation: the scp-like rule dropped -> `host:remote.git`, which exists here as a directory,
    # is made absolute, and git would read a local path where the owner named a host.
    monkeypatch.chdir(tmp_path)
    (tmp_path / "host:remote.git").mkdir()
    assert publish_plugin.remote_argument(remote) == remote
