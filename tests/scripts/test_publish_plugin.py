"""`scripts/publish_plugin.py`: the plugin commit a release pins, built with the tag's own code and
pushed to the plugin's own repository, and nothing else.

Every case starts from `tests/plugintree.py`'s `tool_source`: one commit holding a file under each
of the plugin's nine paths, this branch's `scripts/plugin_tree.py` and `src/stayfixed`, and a
marketplace pinning the plugin commit its tree makes, tagged `v1.2.3` (annotated). The default one
is built once per session and cloned per case; a case that changes the tag's own code patches its
clone, or builds its own when the pin has to change with it. A bare repository in `tmp_path` stands
for the plugin repository.

`gh` is never run. The runner is a composite that records every argv it is handed, answers `gh`
from `GitHub` — `gh api` read from the local repositories standing for GitHub's, everything else
from a script — and runs the rest for real: `git`'s network half and the tag's `plugin_tree.py`.
Every commit id a case expects is computed by git from a literal text (`tests/plugintree.py`), never
by the script. Which exit each outcome is — `1` to reject the release's approval, `2` to fix
something and run again — is held in one place, the table at the end, through the command's `main`.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from stayfixed.errors import Failure, Refusal
from stayfixed.runner import Completed, subprocess_runner
from tests.gitfixture import git, git_bytes, needs_git, run_git
from tests.plugintree import (
    MARKETPLACE,
    NINE,
    PLUGIN_FILES,
    REPOSITORY,
    commit,
    hashed,
    literal,
    pinned_at,
    pinned_marketplace,
    plugin_source,
    plugin_tree_id,
    released,
    tool_source,
    write,
)
from tests.runners import Recorder
from tests.scriptload import plugin_tree as _tree_script
from tests.scriptload import publish_plugin as _script
from tests.scriptload import release as _release_script

publish_plugin = _script()
plugin_tree = _tree_script()
release_script = _release_script()
Rejected = publish_plugin.Rejected

pytestmark = needs_git

TAG = "v1.2.3"
SOURCE_REPOSITORY = "stayfixed/stayfixed"
PLUGIN_REPOSITORY = "stayfixed/stayfixed-plugin"
# GitHub's answers to a ref it does not hold and to any ref of an empty repository, as `gh api`
# gives them (measured for a 404: exit 1, the body on stdout, the status on stderr).
NOT_FOUND = Completed(
    1,
    '{"message":"Not Found","documentation_url":"https://docs.github.com/rest","status":"404"}',
    "gh: Not Found (HTTP 404)\n",
)
EMPTY = Completed(
    1,
    '{"message":"Git Repository is empty.","documentation_url":"https://docs.github.com/rest",'
    '"status":"409"}',
    "gh: Git Repository is empty. (HTTP 409)\n",
)


@dataclass(kw_only=True)
class GitHub(Recorder):
    """`gh`: `gh api … git/ref/<ref>` and `… git/tags/<id>` answered from the repository that
    `repositories` names for the API's, as GitHub answers them, and any other call, or one
    `answers` scripts, as the `Recorder` answers it. Read with `--no-replace-objects`: GitHub
    holds no replace refs. A private double rather than a `Recorder` alone because what it
    answers is a repository's state, which a case changes as it runs."""

    repositories: dict[str, Path] = field(default_factory=dict)

    def launch(self, argv: list[str], cwd: Path) -> Completed:
        answer = super().launch(argv, cwd)
        scripted = any(argv[: len(key.split(" "))] == key.split(" ") for key in self.answers)
        if scripted or argv[:2] != ["gh", "api"]:
            return answer
        return self._api(argv)

    def _api(self, argv: list[str]) -> Completed:
        assert argv[2:4] == ["--hostname", "github.com"], argv
        found = re.fullmatch(r"repos/([^/]+/[^/]+)/git/(ref|tags)/(.+)", argv[4])
        assert found is not None and len(argv) == 5, argv
        name, kind, rest = found.groups()
        repository = self.repositories.get(name)
        if repository is None:
            return NOT_FOUND
        if kind == "tags":
            done = run_git(repository, "--no-replace-objects", "cat-file", "tag", rest)
            if done.returncode != 0:
                return NOT_FOUND
            header = dict(line.split(" ", 1) for line in done.stdout.split("\n\n")[0].split("\n"))
            target = {"sha": header["object"], "type": header["type"]}
            return Completed(0, json.dumps({"sha": rest, "object": target}), "")
        listing = "%(refname) %(objectname) %(objecttype)"
        rows = git(repository, "--no-replace-objects", "for-each-ref", f"--format={listing}")
        if not rows:
            return EMPTY
        for row in rows.splitlines():
            ref, obj, obj_type = row.split(" ")
            if ref == f"refs/{rest}":
                body = {"ref": ref, "object": {"sha": obj, "type": obj_type}}
                return Completed(0, json.dumps(body), "")
        return NOT_FOUND


@dataclass
class Composite:
    """The runner `publish` is handed: every argv recorded in `calls` before it is dispatched,
    `gh` answered by `gh`, every other program run for real, and `before` and `after` run on
    either side of each launch."""

    gh: Recorder = field(default_factory=GitHub)
    calls: list[list[str]] = field(default_factory=list)
    before: Callable[[list[str]], None] = lambda argv: None
    after: Callable[[list[str]], None] = lambda argv: None

    def launch(self, argv: list[str], cwd: Path) -> Completed:
        self.calls.append(argv)
        self.before(argv)
        if argv[:1] == ["gh"]:
            done = self.gh.launch(argv, cwd)
        else:
            done = subprocess_runner().launch(argv, cwd)
        self.after(argv)
        return done


def runner_for(
    source: Path,
    plugin: Path | None = None,
    *,
    answers: dict[str, Completed] | None = None,
    before: Callable[[list[str]], None] = lambda argv: None,
    after: Callable[[list[str]], None] = lambda argv: None,
) -> Composite:
    """A composite whose GitHub holds `source` as `stayfixed/stayfixed` and, when given, `plugin`
    as the plugin repository."""
    repositories = {SOURCE_REPOSITORY: source}
    if plugin is not None:
        repositories[PLUGIN_REPOSITORY] = plugin
    gh = GitHub(repositories=repositories, answers=dict(answers or {}))
    return Composite(gh=gh, before=before, after=after)


@pytest.fixture(scope="session")
def _template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tool_source(tmp_path_factory.mktemp("tool-source"))


@pytest.fixture
def source(_template: Path, tmp_path: Path) -> Path:
    """The default tool source, cloned for this case."""
    root = tmp_path / "source"
    git(tmp_path, "clone", "-q", str(_template), str(root))
    return root


def _home() -> Path:
    return Path(os.environ["HOME"])


def _global_config(text: str) -> None:
    """Append `text` to the test `HOME`'s `.gitconfig`, which the product's `git` reads."""
    config = _home() / ".gitconfig"
    config.write_text(config.read_text(encoding="utf-8") + text, encoding="utf-8")


def tag_commit(root: Path, tag: str = TAG) -> str:
    return git(root, "rev-parse", f"{tag}^{{commit}}").strip()


def bare_remote(tmp_path: Path) -> Path:
    remote = tmp_path / "remote.git"
    git(tmp_path, "init", "-q", "--bare", str(remote))
    return remote


def refs(remote: Path) -> dict[str, str]:
    listing = git(remote, "for-each-ref", "--format=%(refname) %(objectname)")
    return dict(line.split(" ", 1) for line in listing.splitlines())


def remote_commit(remote: Path, message: str, parent: str | None = None) -> str:
    """A commit of the empty tree in `remote`, written there and named by no ref."""
    tree = git_bytes(remote, "mktree", stdin=b"").decode().strip()
    lineage = ("-p", parent) if parent is not None else ()
    return git(remote, "commit-tree", tree, *lineage, "-m", message).strip()


def advance(remote: Path) -> str:
    """`remote`'s `main` moved on by one commit, as someone else's push would move it."""
    main = git(remote, "rev-parse", "refs/heads/main").strip()
    later = remote_commit(remote, "pushed by someone else in the meantime", main)
    git(remote, "update-ref", "refs/heads/main", later, main)
    return later


def with_tool(root: Path, script: bytes, tag: str = TAG) -> None:
    """The tag's commit amended to carry `script` as its `scripts/plugin_tree.py`, and the tag
    moved onto it. No plugin path changes, so the marketplace's pin still holds."""
    write(root, {"scripts/plugin_tree.py": (script, "100755")})
    git(root, "commit", "-q", "-a", "--amend", "--no-edit")
    git(root, "tag", "-f", "-a", tag, "-m", tag)


def repinned(root: Path, sha: str, tag: str = TAG) -> None:
    """The tag's commit amended so its marketplace pins `sha`, and the tag moved onto it."""
    write(root, {MARKETPLACE: pinned_marketplace(sha)})
    git(root, "commit", "-q", "-a", "--amend", "--no-edit")
    git(root, "tag", "-f", "-a", tag, "-m", tag)


SCRIPT = (REPOSITORY / "scripts" / "plugin_tree.py").read_bytes()


def patched(old: bytes, new: bytes) -> bytes:
    """This branch's `scripts/plugin_tree.py` with `old`, which it holds once, made `new`."""
    assert SCRIPT.count(old) == 1, old
    return SCRIPT.replace(old, new)


def publish(
    source: Path,
    remote: Path | str,
    scratch: Path,
    *,
    yes: bool = True,
    tag: str = TAG,
    runner: Composite | None = None,
) -> tuple[Any, Composite]:
    runner = runner if runner is not None else runner_for(source)
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


def tool_command(argv: list[str]) -> str | None:
    """The `plugin_tree.py` command an argv runs the tag's copy for, or `None`."""
    return argv[6] if argv[1:3] == ["-I", "-c"] and len(argv) > 6 else None


def tool_runs(runner: Composite) -> list[list[str]]:
    return [argv for argv in runner.calls if tool_command(argv) is not None]


def gh_asked(runner: Composite, *words: str) -> list[list[str]]:
    return [argv for argv in runner.gh.calls if argv[: len(words)] == list(words)]


def plugin_api(runner: Composite) -> list[list[str]]:
    """The `gh api` calls about the plugin repository."""
    return [
        argv
        for argv in gh_asked(runner, "gh", "api")
        if argv[-1].startswith(f"repos/{PLUGIN_REPOSITORY}/")
    ]


# --- A publish that goes through ---------------------------------------------------------------


def test_the_commit_pushed_is_the_pinned_one(source: Path, tmp_path: Path) -> None:
    # Mutation (declared): `mutations/`'s "the plugin commit builds every file without its
    # executable bit" -> the tag's own `plugin_tree.py`, this branch's, makes another commit than
    # the pin and the run is rejected before anything is pushed.
    remote = bare_remote(tmp_path)
    done, _ = publish(source, remote, tmp_path / "scratch")
    expected = hashed(source, literal(plugin_tree_id(source, TAG), None))
    assert pinned_at(source, TAG) == expected
    assert refs(remote) == {"refs/heads/main": expected, f"refs/tags/{TAG}": expected}
    assert (done.tag, done.commit, done.outcome, done.confirmed) == (TAG, expected, "pushed", False)
    assert git(remote, "cat-file", "commit", expected) == literal(done.tree, None)
    assert listed(remote, TAG, exact=True) == listed(source, TAG)
    assert done.files == len(listed(source, TAG))
    assert listed(remote, TAG)["hooks/run-hook.sh"][1] == "100755"
    assert listed(remote, TAG)["scripts/stayfixed"][1] == "100755"


def test_without_yes_the_remote_is_unchanged(source: Path, tmp_path: Path) -> None:
    # Mutations (declared): `mutations/`'s "the publisher pushes without --yes" -> the remote
    # gains both refs; "the publisher reports its commit's id as the tree it pushes" -> the tree
    # reported is not the commit's.
    remote, scratch = bare_remote(tmp_path), tmp_path / "scratch"
    done, runner = publish(source, remote, scratch, yes=False)
    assert refs(remote) == {}
    assert ran(runner, "push") == []
    assert (done.outcome, done.commit) == ("would-push", pinned_at(source, TAG))
    # The commit the dry run reports is the one the tag's code built, and the tree is its own.
    built = scratch / "plugin.git"
    assert git(built, "rev-parse", "--verify", f"{done.commit}^{{commit}}").strip() == done.commit
    assert git(built, "rev-parse", f"{done.commit}^{{tree}}").strip() == done.tree


def test_the_tree_a_dry_run_names_is_the_one_a_later_run_pushes(
    source: Path, tmp_path: Path
) -> None:
    # No mutation of its own: the commit is a function of the source commit, which
    # `test_the_commit_pushed_is_the_pinned_one` holds; this pins a dry run's answer to be the one
    # a later run pushes, the commit as well as the tree.
    remote = bare_remote(tmp_path)
    dry, _ = publish(source, remote, tmp_path / "dry", yes=False)
    pushed, _ = publish(source, remote, tmp_path / "pushed")
    assert (pushed.tree, pushed.commit) == (dry.tree, dry.commit)
    assert git(remote, "rev-parse", "refs/heads/main").strip() == dry.commit


def test_the_tree_is_rendered_from_the_tag_and_not_the_disk(source: Path, tmp_path: Path) -> None:
    # No mutation of its own: the commit is the tag's `plugin_tree.py`'s, which reads a commit and
    # nothing else (its own tests hold that); what this holds is that `publish` hands it the tag's
    # commit, as the next case does against a branch.
    remote = bare_remote(tmp_path)
    (source / "README.md").write_bytes(b"edited on disk\n")
    write(source, {"skills/staged/SKILL.md": (b"staged only\n", "100644")})
    git(source, "add", "skills/staged/SKILL.md")
    publish(source, remote, tmp_path / "scratch")
    pushed = listed(remote, TAG, exact=True)
    assert pushed["README.md"] == PLUGIN_FILES["README.md"]
    assert "skills/staged/SKILL.md" not in pushed


def test_a_branch_named_like_the_tag_does_not_stand_in_for_it(source: Path, tmp_path: Path) -> None:
    # git's own order reads a tag before a branch of one name, so resolving the bare name would
    # pass this too; the mutation that a branch standing in for an absent tag reddens is in
    # `test_an_unknown_tag_is_refused_before_anything_runs`.
    remote = bare_remote(tmp_path)
    write(source, {"README.md": (b"# on the branch\n", "100644")})
    git(source, "checkout", "-q", "-b", "elsewhere")
    branch_commit = commit(source, "the branch's commit")
    git(source, "branch", "-q", TAG, branch_commit)
    publish(source, remote, tmp_path / "scratch")
    assert listed(remote, TAG, exact=True)["README.md"] == PLUGIN_FILES["README.md"]


def test_the_attestation_is_asked_for_this_workflow_this_tag_and_this_commit(
    source: Path, tmp_path: Path
) -> None:
    # Mutations (declared), one entry each: `--source-ref` dropped; `--source-digest` dropped;
    # `--deny-self-hosted-runners` dropped; `--signer-workflow` dropped.
    _, runner = publish(source, bare_remote(tmp_path), tmp_path / "scratch", yes=False)
    asked = gh_asked(runner, "gh", "attestation", "verify")
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
    # The file it is asked about is the manifest of the plugin's files at the tag.
    expected = plugin_tree.manifest(plugin_tree.members(source, sha)).encode("utf-8")
    assert Path(argv[3]).read_bytes() == expected
    assert expected.startswith(b"stayfixed-plugin-tree 1\n")


def test_a_second_publish_of_the_same_tag_pushes_nothing(source: Path, tmp_path: Path) -> None:
    # Mutations (declared): `mutations/`'s "the publisher treats a tag already on the remote as
    # absent" -> the second run finds `main` at the commit, which is not its parent, and is
    # rejected; "the publisher asks for the attestation after listing the remote" -> the ordering
    # below.
    remote = bare_remote(tmp_path)
    first, _ = publish(source, remote, tmp_path / "first")
    before = refs(remote)
    second, runner = publish(source, remote, tmp_path / "second")
    assert (second.outcome, second.commit, second.tree) == ("already", first.commit, first.tree)
    assert refs(remote) == before
    assert ran(runner, "push") == ran(runner, "fetch") == []
    # The attestation is asked again before the remote is: a re-run trusts nothing it found.
    verify = next(i for i, argv in enumerate(runner.calls) if argv[:2] == ["gh", "attestation"])
    listing = next(i for i, argv in enumerate(runner.calls) if "ls-remote" in argv)
    assert verify < listing


def test_the_previous_release_is_replaced_whole(source: Path, tmp_path: Path) -> None:
    # No mutation of its own: the parent is the tag's `plugin_tree.py`'s, held by
    # `test_the_parent_is_the_sha_the_first_parent_pins` in its own tests, and `main` moving only
    # to a commit whose parent it is by `test_a_main_that_is_not_the_parent_is_rejected`. This
    # holds the fast-forward end to end: the earlier release's file is gone from the new tree.
    remote = bare_remote(tmp_path)
    first, _ = publish(source, remote, tmp_path / "first")
    (source / "agents" / "navigator.md").unlink()
    pin = released(source, "1.2.4", files={"agents/other.md": (b"# other\n", "100644")})
    done, _ = publish(source, remote, tmp_path / "second", tag="v1.2.4")
    assert done.commit == pin
    assert git(remote, "rev-parse", f"{pin}^").strip() == first.commit
    assert listed(remote, "v1.2.4", exact=True) == listed(source, "v1.2.4")
    assert "agents/navigator.md" not in listed(remote, "v1.2.4", exact=True)
    assert refs(remote) == {
        "refs/heads/main": pin,
        f"refs/tags/{TAG}": first.commit,
        "refs/tags/v1.2.4": pin,
    }


# --- What the owner's own git configuration cannot change -----------------------------------------


def test_the_owners_hooks_do_not_run_in_the_scratch_repository(
    source: Path, tmp_path: Path
) -> None:
    # Mutation (declared): `mutations/`'s "the publisher lets the owner's hooks run on its push"
    # -> the owner's `pre-push` runs and refuses the push. The git dir's own gits are
    # `plugin_tree.py`'s, held by `test_the_owners_hooks_do_not_run_in_the_git_dir`.
    remote = bare_remote(tmp_path)
    hooks = _home() / "hooks"
    hooks.mkdir()
    (hooks / "pre-push").write_text("#!/bin/sh\necho refused by pre-push >&2\nexit 1\n")
    (hooks / "pre-push").chmod(0o755)
    _global_config(f"[core]\n\thooksPath = {hooks}\n")
    done, _ = publish(source, remote, tmp_path / "scratch")
    assert done.outcome == "pushed"
    assert refs(remote) == {"refs/heads/main": done.commit, f"refs/tags/{TAG}": done.commit}


def test_an_explicit_safe_bare_repository_does_not_refuse_the_scratch_repository(
    source: Path, tmp_path: Path
) -> None:
    # Mutations (declared): `mutations/`'s "the publisher finds its scratch repository from -C in
    # its network git" and "the publisher finds its scratch repository from -C in its local git"
    # -> `safe.bareRepository=explicit` refuses the bare repository `git -C` finds, at the listing
    # or at the read of the fetched `main`. The git dir's own gits are `plugin_tree.py`'s, held
    # by `test_an_explicit_safe_bare_repository_does_not_refuse_the_git_dir`.
    remote = bare_remote(tmp_path)
    first, _ = publish(source, remote, tmp_path / "first")
    pin = released(source, "1.2.4")
    _global_config("[safe]\n\tbareRepository = explicit\n")
    done, _ = publish(source, remote, tmp_path / "second", tag="v1.2.4")
    assert done.outcome == "pushed"
    assert refs(remote)["refs/heads/main"] == pin
    assert git(remote, "rev-parse", f"{pin}^").strip() == first.commit


def test_a_replace_ref_does_not_stand_in_for_the_tags_version(source: Path, tmp_path: Path) -> None:
    # Mutation (declared): `mutations/`'s "the plugin tree reads an object through a replace ref"
    # -> the tag's own `plugin_tree.py` reads the replaced `plugin.json`, whose tree is not the one
    # the marketplace pinned, and the run is rejected for the pin rather than for the version.
    git(source, "tag", "v1.2.4")
    plugin_json = git(source, "rev-parse", "HEAD:.claude-plugin/plugin.json").strip()
    write(source, {"replacement.json": (b'{"version": "1.2.4"}\n', "100644")})
    replacement = git(source, "hash-object", "-w", "replacement.json").strip()
    git(source, "replace", plugin_json, replacement)
    remote = bare_remote(tmp_path)
    with pytest.raises(Rejected, match=r"plugin\.json says 1\.2\.3") as rejected:
        publish(source, remote, tmp_path / "scratch", tag="v1.2.4")
    assert "v1.2.4" in str(rejected.value)
    assert refs(remote) == {}


def test_a_replace_ref_on_the_tag_object_does_not_move_the_tags_commit(
    source: Path, tmp_path: Path
) -> None:
    # Mutation (declared): `mutations/`'s "the publisher peels the tag through a replace ref" ->
    # the annotated tag's object is read as its replacement, which points at another commit, and
    # GitHub's tag, which no replacement moves, is not that commit.
    remote = bare_remote(tmp_path)
    tagged = tag_commit(source)
    write(source, {"README.md": (b"# another tree under the same version\n", "100644")})
    other = commit(source, "another commit")
    git(source, "tag", "-a", "elsewhere", "-m", "elsewhere", other)
    tag_object = git(source, "rev-parse", f"refs/tags/{TAG}").strip()
    elsewhere = git(source, "rev-parse", "refs/tags/elsewhere").strip()
    git(source, "replace", "-f", tag_object, elsewhere)
    # The premise: through the replacement, the tag peels to the other commit.
    assert git(source, "rev-parse", f"refs/tags/{TAG}^{{commit}}").strip() == other
    done, runner = publish(source, remote, tmp_path / "scratch")
    asked = gh_asked(runner, "gh", "attestation", "verify")
    assert len(asked) == 1, runner.gh.calls
    assert asked[0][asked[0].index("--source-digest") + 1] == tagged
    assert done.outcome == "pushed"
    assert listed(remote, TAG, exact=True)["README.md"] == PLUGIN_FILES["README.md"]


# --- Refusals before anything runs ------------------------------------------------------------


def test_an_unknown_tag_is_refused_before_anything_runs(source: Path, tmp_path: Path) -> None:
    # Mutation (declared): `mutations/`'s "the publisher lets a branch stand in for an absent tag"
    # -> the branch `v2.0.0` stands in for the tag that does not exist.
    write(source, {".claude-plugin/plugin.json": (b'{"version": "2.0.0"}\n', "100644")})
    git(source, "branch", "-q", "v2.0.0", commit(source, "two"))
    runner, scratch = runner_for(source), tmp_path / "scratch"
    with pytest.raises(Refusal, match=r"v2\.0\.0"):
        publish(source, bare_remote(tmp_path), scratch, tag="v2.0.0", runner=runner)
    assert runner.calls == []
    assert list(scratch.iterdir()) == []


@pytest.mark.parametrize("tag", ["v1.2.3\n", "v1.2.3-rc1", "v\N{ARABIC-INDIC DIGIT ONE}.2.3"])
def test_a_tag_that_is_not_a_plain_version_is_refused(
    source: Path, tmp_path: Path, tag: str
) -> None:
    # Mutations (declared): `re.fullmatch` -> `re.match` admits `v1.2.3-rc1`; `[0-9]` -> `\d`
    # admits the Arabic-Indic digit. Each tag git can name is made to exist, with a `plugin.json`
    # whose version spells it, so only the pattern stands between it and the run.
    if "\n" not in tag:
        version = tag.removeprefix("v")
        body = f'{{"version": "{version}"}}\n'.encode()
        write(source, {".claude-plugin/plugin.json": (body, "100644")})
        git(source, "tag", tag, commit(source, "a version that is not plain"))
    runner = runner_for(source)
    with pytest.raises(Refusal, match="plain version"):
        publish(source, bare_remote(tmp_path), tmp_path / "scratch", tag=tag, runner=runner)
    assert runner.calls == []


OTHER = "e" * 40
ANOTHER_ID = Completed(
    0, json.dumps({"ref": f"refs/tags/{TAG}", "object": {"sha": OTHER, "type": "commit"}}), ""
)


@pytest.mark.parametrize(
    ("answer", "named"),
    [
        pytest.param(ANOTHER_ID, f"names {OTHER}", id="another-id"),
        pytest.param(NOT_FOUND, "holds no such tag", id="no-such-tag"),
    ],
)
def test_a_local_tag_github_does_not_hold_is_refused(
    source: Path, tmp_path: Path, answer: Completed, named: str
) -> None:
    # Mutation (declared): `mutations/`'s "the publisher runs a tag GitHub does not hold" -> the
    # tag's code is extracted and run, and the publish goes on.
    asked = f"gh api --hostname github.com repos/{SOURCE_REPOSITORY}/git/ref/tags/{TAG}"
    runner, scratch = runner_for(source, answers={asked: answer}), tmp_path / "scratch"
    with pytest.raises(Refusal, match="is not GitHub's") as refused:
        publish(source, bare_remote(tmp_path), scratch, runner=runner)
    assert tag_commit(source) in str(refused.value)
    assert named in str(refused.value)
    assert not (scratch / "tool").exists()
    assert tool_runs(runner) == gh_asked(runner, "gh", "attestation") == []


SERVER_ERROR = Completed(
    1, '{"message":"Server Error","status":"500"}', "gh: Server Error (HTTP 500)\n"
)
NOT_JSON = Completed(0, "<html>a proxy's page</html>\n", "")
NO_OBJECT_NAME = Completed(
    0, json.dumps({"ref": f"refs/tags/{TAG}", "object": {"sha": "+main", "type": "commit"}}), ""
)


@pytest.mark.parametrize(
    ("answer", "said"),
    [
        pytest.param(SERVER_ERROR, "exited 1: 'gh: Server Error (HTTP 500)'", id="a-server-error"),
        pytest.param(NOT_JSON, "answered no JSON object", id="not-json"),
        pytest.param(NO_OBJECT_NAME, "GitHub answered '+main' for", id="no-object-name"),
    ],
)
def test_an_api_answer_that_is_neither_a_ref_nor_its_absence_is_refused(
    source: Path, tmp_path: Path, answer: Completed, said: str
) -> None:
    # Mutations (declared): `mutations/`'s "the publisher reads any failed API call as absent" ->
    # the server error reads as GitHub holding no such tag; "the publisher takes GitHub's answer
    # that is no object name" -> `+main` is compared with the tag's commit. Either way the
    # refusal says the local tag is not GitHub's, which is not what happened.
    asked = f"gh api --hostname github.com repos/{SOURCE_REPOSITORY}/git/ref/tags/{TAG}"
    runner = runner_for(source, answers={asked: answer})
    with pytest.raises(Refusal) as refused:
        publish(source, bare_remote(tmp_path), tmp_path / "scratch", runner=runner)
    assert said in str(refused.value), str(refused.value)
    assert "is not GitHub's" not in str(refused.value)
    assert tool_runs(runner) == []


def test_a_tag_without_the_plugin_tree_script_is_refused(tmp_path: Path) -> None:
    # Mutation (declared): `mutations/`'s "the publisher runs a tag that predates it" -> the tag's
    # `src/stayfixed` is extracted without a script to run, and the run fails in Python's words.
    source = plugin_source(tmp_path)
    git(source, "tag", "-a", TAG, "-m", TAG)
    runner, scratch = runner_for(source), tmp_path / "scratch"
    with pytest.raises(Refusal, match="predates") as refused:
        publish(source, bare_remote(tmp_path), scratch, runner=runner)
    assert "scripts/plugin_tree.py" in str(refused.value)
    assert tool_runs(runner) == []
    assert not (scratch / "tool").exists()


def test_a_tool_file_that_is_not_regular_is_refused(source: Path, tmp_path: Path) -> None:
    # Mutation (declared): `mutations/`'s "the publisher runs the tag's code from a file that is
    # not regular" -> the symlink is written as a file holding its target's name, and the tag's
    # code runs.
    os.symlink("__init__.py", source / "src" / "stayfixed" / "linked.py")
    commit(source, "a symlink among the tag's code")
    git(source, "tag", "-f", "-a", TAG, "-m", TAG)
    runner, scratch = runner_for(source), tmp_path / "scratch"
    with pytest.raises(Refusal, match=r"src/stayfixed/linked\.py") as refused:
        publish(source, bare_remote(tmp_path), scratch, runner=runner)
    assert "120000" in str(refused.value)
    assert tool_runs(runner) == []
    assert not (scratch / "tool").exists()


# --- The tag's own code ---------------------------------------------------------------------------


def test_the_tag_s_own_plugin_tree_builds_the_commit(tmp_path: Path) -> None:
    # Mutation (declared): `mutations/`'s "the publisher runs the checkout's plugin_tree.py" ->
    # the checkout's copy reads nine paths, so its commit is not the pin and the run is rejected
    # when the commit is built, before any manifest is compared.
    ten = (*NINE, "commands")
    script = patched(b'    "LICENSE",\n)', b'    "LICENSE",\n    "commands",\n)')
    extra = {"commands/a.md": (b"# a command\n", "100644")}
    source = tool_source(tmp_path, plugin_tree=script, extra=extra, paths=ten)
    scratch = tmp_path / "scratch"
    done, _ = publish(source, bare_remote(tmp_path), scratch, yes=False)
    assert (done.outcome, done.commit) == ("would-push", pinned_at(source, TAG))
    rows = []
    for record in git(source, "ls-tree", "-r", "-z", "--full-tree", TAG, "--", *ten).split("\0"):
        if record:
            meta, path = record.split("\t", 1)
            mode, _kind, obj = meta.split()
            digest = hashlib.sha256(git_bytes(source, "cat-file", "blob", obj)).hexdigest()
            rows.append((path, f"{mode} {digest} {path}\n"))
    expected = "stayfixed-plugin-tree 1\n" + "".join(line for _, line in sorted(rows))
    assert (scratch / "plugin-tree.txt").read_text(encoding="utf-8") == expected
    line = "100644 dcf4a2ae11e48a937801393a5a5521068b50366476f099740f5576f081a659a2 commands/a.md\n"
    assert line in expected
    assert done.files == len(rows)


def test_the_tag_s_tool_imports_the_tag_s_stayfixed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Mutation (declared): `mutations/`'s "the publisher puts the tag's src after the checkout's"
    # -> the venv's path to this checkout's `src` is read first, and the tag's code runs on this
    # checkout's `stayfixed`.
    marker = b"from __future__ import annotations\n"
    line = (
        b"import os, stayfixed; "
        b'open(os.environ["PUBLISH_TEST_IMPORTED"], "w").write(stayfixed.__file__)\n'
    )
    imported = tmp_path / "imported.txt"
    monkeypatch.setenv("PUBLISH_TEST_IMPORTED", str(imported))
    source = tool_source(tmp_path, plugin_tree=patched(marker, marker + line))
    scratch = tmp_path / "scratch"
    publish(source, bare_remote(tmp_path), scratch, yes=False)
    written = Path(imported.read_text(encoding="utf-8")).resolve()
    assert written == (scratch / "tool" / "src" / "stayfixed" / "__init__.py").resolve()


@pytest.mark.parametrize(
    ("name", "value", "shown"),
    [
        pytest.param("commit", "+main", "'+main'", id="commit"),
        pytest.param("tree", "+main", "'+main'", id="tree"),
        pytest.param("parent", "+main", "'+main'", id="parent"),
        pytest.param("files", "10", "a str", id="files"),
    ],
)
def test_a_tool_answer_that_is_not_an_object_name_is_refused(
    source: Path, tmp_path: Path, name: str, value: str, shown: str
) -> None:
    # Mutations (declared), one per field: `mutations/`'s "the publisher takes a tool's commit
    # that is no object name" -> `+main` reaches the read-back, which refuses it in the tool's
    # words; "the publisher takes a tool's tree that is no object name" and "the publisher takes
    # a tool's file count that is no integer" -> the run goes through; "the publisher takes a
    # tool's parent that is no object name" -> `+main` is compared with `main` and rejected.
    data = b'{"format": FORMAT, **asdict(found)}'
    with_tool(source, patched(data, data[:-1] + f', "{name}": "{value}"}}'.encode()))
    remote = bare_remote(tmp_path)
    runner = runner_for(source)
    with pytest.raises(Refusal) as refused:
        publish(source, remote, tmp_path / "scratch", runner=runner)
    assert not isinstance(refused.value, Failure)
    assert f"commit answered {shown} for {name}," in str(refused.value), str(refused.value)
    assert ran(runner, "push") == []
    assert refs(remote) == {}


def test_a_tool_answering_in_another_format_is_refused(source: Path, tmp_path: Path) -> None:
    # Mutation (declared): `mutations/`'s "the publisher reads a tool answer in another format" ->
    # both manifests are in the other format, they agree, and the run pushes.
    old = b'FORMAT = "stayfixed-plugin-tree 1"'
    with_tool(source, patched(old, b'FORMAT = "stayfixed-plugin-tree 2"'))
    remote = bare_remote(tmp_path)
    runner = runner_for(source)
    with pytest.raises(Refusal, match="stayfixed-plugin-tree 2"):
        publish(source, remote, tmp_path / "scratch", runner=runner)
    assert gh_asked(runner, "gh", "attestation") == []
    assert refs(remote) == {}


# --- Rejections: facts of the release no re-run changes -------------------------------------------


def test_a_pin_other_than_the_commit_is_rejected(source: Path, tmp_path: Path) -> None:
    # Mutation (declared): `mutations/`'s "the publisher refuses a pin it should reject" -> the
    # pin's difference is a refusal, exit 2, which says to run again.
    made = pinned_at(source, TAG)
    repinned(source, "c" * 40)
    remote = bare_remote(tmp_path)
    runner = runner_for(source)
    with pytest.raises(Rejected) as rejected:
        publish(source, remote, tmp_path / "scratch", runner=runner)
    assert "c" * 40 in str(rejected.value)
    assert str(made) in str(rejected.value)
    assert gh_asked(runner, "gh", "attestation") == []
    assert refs(remote) == {}


def test_a_tag_whose_version_is_another_is_rejected(source: Path, tmp_path: Path) -> None:
    # Mutation (declared): `mutations/`'s "the publisher stops holding the tag to the version it
    # releases" -> the run goes on and pushes `v1.2.4` holding 1.2.3.
    git(source, "tag", "v1.2.4")
    remote = bare_remote(tmp_path)
    runner = runner_for(source)
    with pytest.raises(Rejected, match=r"1\.2\.3") as rejected:
        publish(source, remote, tmp_path / "scratch", tag="v1.2.4", runner=runner)
    assert "v1.2.4" in str(rejected.value)
    assert gh_asked(runner, "gh", "attestation") == []
    assert refs(remote) == {}


@pytest.mark.parametrize("annotated", [False, True], ids=["lightweight", "annotated"])
def test_another_commit_under_the_tag_is_rejected(
    source: Path, tmp_path: Path, annotated: bool
) -> None:
    # Mutation (declared): `mutations/`'s "the publisher treats a tag already on the remote as
    # absent" -> the run goes on to push, and the remote refuses the tag that exists, with git's
    # sentence and exit 2.
    remote = bare_remote(tmp_path)
    some = remote_commit(remote, "another commit under the tag")
    if annotated:
        git(remote, "tag", "-a", TAG, "-m", TAG, some)
    else:
        git(remote, "update-ref", f"refs/tags/{TAG}", some)
    before = refs(remote)
    runner = runner_for(source)
    with pytest.raises(Rejected) as rejected:
        publish(source, remote, tmp_path / "scratch", runner=runner)
    assert some in str(rejected.value)
    assert str(pinned_at(source, TAG)) in str(rejected.value)
    assert ran(runner, "fetch") == ran(runner, "push") == []
    assert refs(remote) == before


def test_an_annotated_tag_peeling_to_the_pin_is_already_published(
    source: Path, tmp_path: Path
) -> None:
    # Mutation (declared): `mutations/`'s "the publisher compares the tag object where the remote
    # lists its peel" -> the tag object's id is not the commit, and the run is rejected.
    remote = bare_remote(tmp_path)
    first, _ = publish(source, remote, tmp_path / "first")
    git(remote, "tag", "-f", "-a", TAG, "-m", "annotated on the remote", first.commit)
    assert refs(remote)[f"refs/tags/{TAG}"] != first.commit
    before = refs(remote)
    done, runner = publish(source, remote, tmp_path / "second")
    assert (done.outcome, done.commit) == ("already", first.commit)
    assert ran(runner, "fetch") == ran(runner, "push") == []
    assert refs(remote) == before


def test_a_published_tag_with_main_moved_on_is_already_published(
    source: Path, tmp_path: Path
) -> None:
    # No mutation exists: no line compares `main` once the tag names the commit. This pins a
    # re-run after the plugin repository moved on against such a comparison coming back, which
    # would refuse a release that was published.
    remote = bare_remote(tmp_path)
    first, _ = publish(source, remote, tmp_path / "first")
    later = advance(remote)
    done, runner = publish(source, remote, tmp_path / "second")
    assert (done.outcome, done.commit) == ("already", first.commit)
    assert refs(remote) == {"refs/heads/main": later, f"refs/tags/{TAG}": first.commit}
    assert ran(runner, "push") == []


@pytest.mark.parametrize(
    ("main", "previous"),
    [
        pytest.param(False, "c" * 40, id="no-main"),
        pytest.param(True, None, id="no-parent"),
        pytest.param(True, "c" * 40, id="another-main"),
    ],
)
def test_a_main_that_is_not_the_parent_is_rejected(
    source: Path, tmp_path: Path, main: bool, previous: str | None
) -> None:
    # The plugin repository's `main` moves only by fast-forward, so the commit this release pins
    # must follow it: rejected, naming both, before anything is fetched or pushed. Mutation
    # (declared): `mutations/`'s "the publisher builds on a main that is not the parent" -> each
    # case goes on, to a fetch of a `main` the remote lacks or a push the remote refuses, exit 2.
    remote = bare_remote(tmp_path)
    if main:
        git(remote, "update-ref", "refs/heads/main", remote_commit(remote, "some"))
    before = refs(remote)
    pin = released(source, "1.2.4", before=previous)
    runner = runner_for(source)
    with pytest.raises(Rejected) as rejected:
        publish(source, remote, tmp_path / "scratch", tag="v1.2.4", runner=runner)
    said = str(rejected.value)
    assert pin in said
    assert (f"parent {previous}" if previous else "no parent") in said, said
    assert (f"main at {before['refs/heads/main']}" if main else "no main") in said, said
    assert ran(runner, "fetch") == ran(runner, "push") == []
    assert refs(remote) == before


def test_publishing_an_older_line_never_rewinds_main(source: Path, tmp_path: Path) -> None:
    # No mutation of its own: the rejection is `main`'s comparison with the parent, whose entry
    # reddens `test_a_main_that_is_not_the_parent_is_rejected`. This holds the case a patch
    # release of an older line makes.
    remote = bare_remote(tmp_path)
    publish(source, remote, tmp_path / "first")
    newer = released(source, "1.3.0")
    publish(source, remote, tmp_path / "second", tag="v1.3.0")
    assert refs(remote)["refs/heads/main"] == newer
    git(source, "checkout", "-q", "-b", "line-1.2", TAG)
    released(source, "1.2.4", before=None)
    with pytest.raises(Rejected, match="no parent"):
        publish(source, remote, tmp_path / "third", tag="v1.2.4")
    assert refs(remote)["refs/heads/main"] == newer
    assert "refs/tags/v1.2.4" not in refs(remote)


def test_a_manifest_changed_after_the_commit_is_rejected_by_the_read_back(
    source: Path, tmp_path: Path
) -> None:
    # Mutation (declared): `mutations/`'s "the publisher pushes without reading its commit back"
    # -> the commit is pushed under a manifest it does not hold. The edit lands just after the
    # tag's code wrote the commit and its manifest: the one window in which the two can part.
    def edit(argv: list[str]) -> None:
        if tool_command(argv) == "commit":
            manifest = Path(argv[argv.index("--manifest-file") + 1])
            manifest.write_bytes(manifest.read_bytes().replace(b"\n100644 ", b"\n100755 ", 1))

    remote = bare_remote(tmp_path)
    runner = runner_for(source, after=edit)
    with pytest.raises(Rejected, match=r"\.claude-plugin/plugin\.json") as rejected:
        publish(source, remote, tmp_path / "scratch", runner=runner)
    assert "nothing was pushed" in str(rejected.value)
    assert refs(remote) == {}
    assert ran(runner, "push") == []


def test_a_refused_attestation_stops_before_anything_is_fetched(
    source: Path, tmp_path: Path
) -> None:
    # Mutation (declared): `mutations/`'s "the publisher goes on past a refused attestation" ->
    # the remote is listed, and pushed to.
    remote = bare_remote(tmp_path)
    said = "no attestations found for the subject"
    verify = Completed(1, "", f"{said}\nsecond line\n")
    runner = runner_for(source, answers={"gh attestation verify": verify})
    with pytest.raises(Rejected) as rejected:
        publish(source, remote, tmp_path / "scratch", runner=runner)
    assert said in str(rejected.value)
    assert "could not check" in str(rejected.value)
    for word in ("ls-remote", "fetch", "push"):
        assert ran(runner, word) == [], word
    assert refs(remote) == {}


# --- Refusals: run again once the cause is fixed --------------------------------------------------


@dataclass
class _Listing(Composite):
    """The composite, with `ls-remote` answered from `listing` rather than by a remote."""

    listing: str = ""

    def launch(self, argv: list[str], cwd: Path) -> Completed:
        if "ls-remote" in argv:
            self.calls.append(argv)
            return Completed(0, self.listing, "")
        return super().launch(argv, cwd)


def test_a_listing_that_names_no_object_is_refused(source: Path, tmp_path: Path) -> None:
    # Mutation: the object-name check dropped -> the listing is taken for a `main`, compared with
    # the parent and rejected rather than refused. No entry: what the check keeps out is a name the
    # remote chose reaching `fetch`, and a remote that lies about `main` is refused by the fetch's
    # check or by the atomic push as well.
    gh = runner_for(source).gh
    runner = _Listing(gh=gh, listing="--upload-pack=x\trefs/heads/main\n")
    with pytest.raises(Refusal, match="answered '--upload-pack=x' for refs/heads/main"):
        publish(source, bare_remote(tmp_path), tmp_path / "scratch", runner=runner)
    assert ran(runner, "fetch") == []


def test_a_main_that_moves_between_list_and_fetch_is_refused(source: Path, tmp_path: Path) -> None:
    # Mutation (declared): `mutations/`'s "the publisher builds on a main the fetch did not bring"
    # -> the run goes on past the fetch and says what it would push onto a `main` that moved.
    remote = bare_remote(tmp_path)
    first, _ = publish(source, remote, tmp_path / "first")
    released(source, "1.2.4")
    moved: list[str] = []

    def race(argv: list[str]) -> None:
        if argv[:1] == ["git"] and "ls-remote" in argv and not moved:
            moved.append(advance(remote))

    runner = runner_for(source, after=race)
    with pytest.raises(Refusal, match="main moved while this ran") as refused:
        publish(source, remote, tmp_path / "second", yes=False, tag="v1.2.4", runner=runner)
    assert "run again" in str(refused.value)
    assert refs(remote) == {"refs/heads/main": moved[0], f"refs/tags/{TAG}": first.commit}


def test_a_rejected_push_moves_no_ref(source: Path, tmp_path: Path) -> None:
    # Mutation (declared): `mutations/`'s "the publisher's push is not atomic" -> the remote takes
    # `main` and refuses only the tag.
    remote = bare_remote(tmp_path)
    hook = remote / "hooks" / "update"
    hook.write_text(
        '#!/bin/sh\ncase "$1" in refs/tags/*) echo "tags are refused here" >&2; exit 1;; esac\n'
    )
    hook.chmod(0o755)
    with pytest.raises(Refusal, match="git push") as refused:
        publish(source, remote, tmp_path / "scratch")
    assert not isinstance(refused.value, Failure)
    assert "tags are refused here" in str(refused.value)
    assert refs(remote) == {}


def test_a_main_that_moved_before_the_push_is_not_overwritten(source: Path, tmp_path: Path) -> None:
    # Mutation (declared): `mutations/`'s "the publisher forces main over a commit pushed after its
    # fetch" -> the commit built on the fetched `main` replaces the one pushed in between, and the
    # tag lands with it.
    remote = bare_remote(tmp_path)
    first, _ = publish(source, remote, tmp_path / "first")
    released(source, "1.2.4")
    moved: list[str] = []

    def race(argv: list[str]) -> None:
        if argv[:1] == ["git"] and "push" in argv:
            moved.append(advance(remote))

    runner = runner_for(source, before=race)
    with pytest.raises(Refusal, match="git push"):
        publish(source, remote, tmp_path / "second", tag="v1.2.4", runner=runner)
    assert refs(remote) == {"refs/heads/main": moved[0], f"refs/tags/{TAG}": first.commit}


# --- GitHub's API, the remote's anchor on the default remote --------------------------------------


def test_the_api_decides_on_the_default_remote(
    source: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Mutation (declared): `mutations/`'s "the publisher classifies the default remote from
    # ls-remote alone" -> the redirected listing's tag is taken for GitHub's, and the run says
    # "already published" of a release GitHub does not hold.
    bare = bare_remote(tmp_path)
    _global_config(f'[url "{bare}"]\n\tinsteadOf = {publish_plugin.PLUGIN_REMOTE}\n')
    monkeypatch.setenv("GIT_SSH_COMMAND", "false")
    default = publish_plugin.PLUGIN_REMOTE
    dry, runner = publish(
        source, default, tmp_path / "dry", yes=False, runner=runner_for(source, bare)
    )
    assert (dry.outcome, dry.confirmed) == ("would-push", True)
    assert sorted(argv[-1] for argv in plugin_api(runner)) == [
        f"repos/{PLUGIN_REPOSITORY}/git/ref/heads/main",
        f"repos/{PLUGIN_REPOSITORY}/git/ref/tags/{TAG}",
    ]
    pushed, _ = publish(source, default, tmp_path / "pushed", runner=runner_for(source, bare))
    assert (pushed.outcome, pushed.confirmed) == ("pushed", True)
    assert refs(bare) == {"refs/heads/main": pushed.commit, f"refs/tags/{TAG}": pushed.commit}
    # GitHub holds no such tag, while the repository the owner's git reaches does.
    tag_api = f"gh api --hostname github.com repos/{PLUGIN_REPOSITORY}/git/ref/tags/{TAG}"
    hidden = runner_for(source, bare, answers={tag_api: NOT_FOUND})
    with pytest.raises(Refusal, match="redirect") as refused:
        publish(source, default, tmp_path / "hidden", runner=hidden)
    assert "insteadOf" in str(refused.value)
    assert ran(hidden, "push") == []


def test_another_remote_is_not_confirmed(source: Path, tmp_path: Path) -> None:
    # Mutation (declared): `mutations/`'s "the publisher confirms another remote through GitHub's
    # API" -> the plugin repository's API is asked about a remote it does not stand for.
    done, runner = publish(source, bare_remote(tmp_path), tmp_path / "scratch", yes=False)
    assert (done.outcome, done.confirmed) == ("would-push", False)
    assert plugin_api(runner) == []


# --- The command line -----------------------------------------------------------------------------


def test_the_publisher_pushes_to_the_repository_the_marketplace_fetches_from() -> None:
    # Mutations (declared): `mutations/`'s "the publisher pushes to another repository than the
    # marketplace fetches from", "the publisher confirms through another repository than the
    # marketplace fetches from" and "the publisher asks GitHub about another plugin repository"
    # -> it no longer agrees with `scripts/release.py`'s `PLUGIN_URL` or `PLUGIN_REPOSITORY`,
    # which the marketplace entry is held to. Two spellings of one repository, one for the owner's
    # git to push over SSH and one for the harness to fetch over HTTPS; this keeps them one.
    remote = re.fullmatch(r"git@github\.com:([^/]+/[^/]+)\.git", publish_plugin.PLUGIN_REMOTE)
    url = re.fullmatch(r"https://github\.com/([^/]+/[^/]+)\.git", release_script.PLUGIN_URL)
    assert remote is not None and url is not None
    assert remote.group(1) == url.group(1) == "stayfixed/stayfixed-plugin"
    assert publish_plugin.PLUGIN_URL == release_script.PLUGIN_URL
    assert publish_plugin.PLUGIN_REPOSITORY == release_script.PLUGIN_REPOSITORY
    assert release_script.PLUGIN_REPOSITORY == "stayfixed/stayfixed-plugin"


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
    source: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Mutation (declared): `mutations/`'s "the publisher pushes without --yes" -> the dry run
    # pushes, and says "pushed" rather than "would push".
    remote = bare_remote(tmp_path)
    monkeypatch.setattr(publish_plugin, "ROOT", source)
    monkeypatch.setattr(publish_plugin, "subprocess_runner", lambda: runner_for(source))
    assert publish_plugin.main(["--tag", TAG, "--remote", str(remote)]) == 0
    said = capsys.readouterr().out
    files = len(listed(source, TAG))
    pin = pinned_at(source, TAG)
    assert said.startswith(f"would push {files} files as tree "), said
    assert f", commit {pin}, to {remote}: main and {TAG}" in said
    assert "(not confirmed through GitHub's API)" in said
    assert said.endswith("; run again with --yes to push\n"), said
    assert refs(remote) == {}


def test_a_relative_remote_is_the_one_beside_the_owner_and_not_the_scratch_repository(
    source: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Mutation: `remote_argument` returning its argument unchanged -> git, run with `-C` in the
    # scratch repository, looks for `remote.git` there, and the listing is refused.
    remote = bare_remote(tmp_path)
    monkeypatch.setattr(publish_plugin, "ROOT", source)
    monkeypatch.setattr(publish_plugin, "subprocess_runner", lambda: runner_for(source))
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


# --- The exit classes: 1 rejects the release's approval, 2 says fix and run again ---------------


def _pins_another(source: Path, remote: Path) -> tuple[Composite, str]:
    repinned(source, "c" * 40)
    return runner_for(source), TAG


def _names_another_version(source: Path, remote: Path) -> tuple[Composite, str]:
    git(source, "tag", "v1.2.4")
    return runner_for(source), "v1.2.4"


def _another_commit_under_the_tag(source: Path, remote: Path) -> tuple[Composite, str]:
    git(remote, "update-ref", f"refs/tags/{TAG}", remote_commit(remote, "another"))
    return runner_for(source), TAG


def _main_not_the_parent(source: Path, remote: Path) -> tuple[Composite, str]:
    git(remote, "update-ref", "refs/heads/main", remote_commit(remote, "some"))
    return runner_for(source), TAG


def _attestation_refused(source: Path, remote: Path) -> tuple[Composite, str]:
    verify = Completed(1, "", "no attestations found for the subject\n")
    return runner_for(source, answers={"gh attestation verify": verify}), TAG


def _read_back_differs(source: Path, remote: Path) -> tuple[Composite, str]:
    def edit(argv: list[str]) -> None:
        if tool_command(argv) == "commit":
            manifest = Path(argv[argv.index("--manifest-file") + 1])
            manifest.write_bytes(manifest.read_bytes().replace(b"\n100644 ", b"\n100755 ", 1))

    return runner_for(source, after=edit), TAG


def _not_plain(source: Path, remote: Path) -> tuple[Composite, str]:
    return runner_for(source), "v1.2"


def _not_github_s(source: Path, remote: Path) -> tuple[Composite, str]:
    asked = f"gh api --hostname github.com repos/{SOURCE_REPOSITORY}/git/ref/tags/{TAG}"
    return runner_for(source, answers={asked: NOT_FOUND}), TAG


def _predates(source: Path, remote: Path) -> tuple[Composite, str]:
    git(source, "rm", "-q", "scripts/plugin_tree.py")
    git(source, "commit", "-q", "--amend", "--no-edit")
    git(source, "tag", "-f", "-a", TAG, "-m", TAG)
    return runner_for(source), TAG


def _no_object_name(source: Path, remote: Path) -> tuple[Composite, str]:
    data = b'{"format": FORMAT, **asdict(found)}'
    with_tool(source, patched(data, data[:-1] + b', "commit": "+main"}'))
    return runner_for(source), TAG


def _main_moves(source: Path, remote: Path) -> tuple[Composite, str]:
    publish(source, remote, source.parent / "first")
    released(source, "1.2.4")
    moved: list[str] = []

    def race(argv: list[str]) -> None:
        if argv[:1] == ["git"] and "ls-remote" in argv and not moved:
            moved.append(advance(remote))

    return runner_for(source, after=race), "v1.2.4"


def _push_refused(source: Path, remote: Path) -> tuple[Composite, str]:
    hook = remote / "hooks" / "update"
    hook.write_text("#!/bin/sh\necho refused >&2\nexit 1\n")
    hook.chmod(0o755)
    return runner_for(source), TAG


@pytest.mark.parametrize(
    ("arrange", "code"),
    [
        pytest.param(_pins_another, 1, id="the-pin-is-another-commit"),
        pytest.param(_names_another_version, 1, id="the-tag-names-another-version"),
        pytest.param(_another_commit_under_the_tag, 1, id="another-commit-under-the-tag"),
        pytest.param(_main_not_the_parent, 1, id="main-is-not-the-parent"),
        pytest.param(_attestation_refused, 1, id="the-attestation-does-not-verify"),
        pytest.param(_read_back_differs, 1, id="the-commit-reads-back-as-another-tree"),
        pytest.param(_not_plain, 2, id="a-tag-that-is-not-plain"),
        pytest.param(_not_github_s, 2, id="a-local-tag-github-does-not-hold"),
        pytest.param(_predates, 2, id="a-tag-that-predates-the-publisher"),
        pytest.param(_no_object_name, 2, id="a-tool-answer-that-is-no-object-name"),
        pytest.param(_main_moves, 2, id="main-moves-between-list-and-fetch"),
        pytest.param(_push_refused, 2, id="a-refused-push"),
    ],
)
def test_every_rejection_exits_1_and_every_refusal_exits_2(
    source: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    arrange: Callable[[Path, Path], tuple[Composite, str]],
    code: int,
) -> None:
    # The classification's one home (Mutation: none of its own: each case's entry reddens the
    # case's own test above, and `Rejected` and `Refusal` are the frame's exit 1 and 2).
    remote = bare_remote(tmp_path)
    runner, tag = arrange(source, remote)
    monkeypatch.setattr(publish_plugin, "ROOT", source)
    monkeypatch.setattr(publish_plugin, "subprocess_runner", lambda: runner)
    argv = ["--tag", tag, "--remote", str(remote), "--yes", "--json"]
    assert publish_plugin.main(argv) == code, capsys.readouterr()
    report = json.loads(capsys.readouterr().out)
    assert report["error"] == {1: "failed", 2: "refused"}[code], report
