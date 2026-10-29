"""Which commit a change is judged against, and where in it the base's `stayfixed.toml` is.

Every case reads a real clone, because each defect here is git resolving a name or a path to
something other than what the caller meant: a tag answering for a remote-tracking ref, a
symlinked root answering for a directory the base never had. "No copy on the base" is the
bootstrap, which lets a change decide its own configuration, so every way of reaching it by
accident is a case.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

import stayfixed
from stayfixed import committed, gitenv
from stayfixed.assess.base import (
    BASE_NOT_A_BRANCH,
    BASE_NOT_UTF8,
    NO_BASE,
    PATH_LEAVES,
    platform_base,
    platform_root,
    read_base,
)
from stayfixed.assess.report import UNCHANGED
from stayfixed.committed import NOT_A_REPOSITORY, ROOT_UNANSWERED, repository_prefix
from stayfixed.config.layout import local_base
from stayfixed.config.loader import load
from stayfixed.errors import Failure, Refusal
from tests.assess.baserepo import clone, commit, shadow
from tests.cli import cli
from tests.gitfixture import git, needs_git

pytestmark = needs_git

BASE = f"""[stayfixed]
version = "{stayfixed.__version__}"

[project]
name = "widget"
"""
REMOTE_MAIN = "refs/remotes/origin/main"


def default_base(root: Path) -> str:
    return local_base(load(root, machine=root.parent / "absent.toml"))


def test_the_default_base_is_the_remote_tracking_ref_whatever_a_tag_is_called(
    tmp_path: Path,
) -> None:
    # A tag spelled `origin/main` wins git's lookup of the short name over the remote-tracking
    # ref, and it carries no `stayfixed.toml`: read by the short name, the base would be the
    # bootstrap. The default names the ref in full, so no tag can stand in for it.
    project = clone(tmp_path, BASE)
    shadow(project, "origin/main")
    assert read_base(project, default_base(project), branch="main") == BASE


def test_a_short_name_is_refused_because_a_tag_can_take_its_place(tmp_path: Path) -> None:
    project = clone(tmp_path, BASE)
    shadow(project, "origin/main")
    with pytest.raises(Refusal, match="refs/"):
        read_base(project, "origin/main", branch="main")


def test_a_full_ref_name_must_exist_as_itself(tmp_path: Path) -> None:
    # With no `refs/remotes/origin/gone`, git would resolve the name to the tag
    # `refs/tags/refs/remotes/origin/gone`, whose commit has no `stayfixed.toml`.
    project = clone(tmp_path, BASE)
    shadow(project, "refs/remotes/origin/gone")
    with pytest.raises(Failure, match=re.escape("fetch-depth: 0")):
        read_base(project, "refs/remotes/origin/gone", branch="main")


def test_a_commit_id_is_read_as_given(tmp_path: Path) -> None:
    # What CI passes: the id the workflow resolved once from the remote-tracking ref. Removing
    # the 40-hex alternative from the shape refuses more, so it is not declared as a mutation.
    project = clone(tmp_path, BASE)
    sha = git(project, "rev-parse", REMOTE_MAIN).strip()
    assert read_base(project, sha, branch="main") == BASE


def test_a_base_id_that_names_no_commit_is_a_failure_and_never_the_bootstrap(
    tmp_path: Path,
) -> None:
    # A 40-hex id is taken as given, so it must name a commit: read as a tree, the empty tree
    # lists no `stayfixed.toml`, and the change would govern itself.
    project = clone(tmp_path, BASE)
    empty = git(project, "hash-object", "-t", "tree", "-w", os.devnull).strip()
    with pytest.raises(Failure, match=re.escape("fetch-depth: 0")):
        read_base(project, empty, branch="main")


def test_a_project_in_a_subdirectory_reads_the_base_s_copy_at_its_own_path(
    tmp_path: Path,
) -> None:
    project = clone(tmp_path, BASE, under="sub")
    assert repository_prefix(project / "sub") == "sub/"
    assert read_base(project / "sub", REMOTE_MAIN, branch="main") == BASE
    assert read_base(project, REMOTE_MAIN, branch="main") is None


def test_a_project_under_a_directory_named_like_pathspec_magic_reads_its_own_copy(
    tmp_path: Path,
) -> None:
    # git reads a pathspec starting `:/` as "from the top": without `--literal-pathspecs`,
    # `ls-tree -- :/x/stayfixed.toml` looks for `x/stayfixed.toml`, exits 0 and lists nothing, so a
    # project kept under `:/x` would be the bootstrap and govern its own change.
    project = clone(tmp_path, BASE, under=":/x")
    assert repository_prefix(project / ":" / "x") == ":/x/"
    assert read_base(project / ":" / "x", REMOTE_MAIN, branch="main") == BASE


def test_a_file_named_like_the_separator_is_not_listed_as_the_base_s_copy(tmp_path: Path) -> None:
    # After `--end-of-options` every argument is literal, a `--` included: `ls-tree` also listed a
    # top-level file named `--`, so a project with no copy on its base failed as unreadable. A
    # separator put back refuses more (a false failure), so it is not declared as a mutation.
    project = clone(tmp_path, BASE, under="sub", also={"--": "not a separator\n"})
    assert read_base(project, REMOTE_MAIN, branch="main") is None
    assert read_base(project / "sub", REMOTE_MAIN, branch="main") == BASE


def test_a_project_under_a_directory_named_like_an_option_reads_its_own_copy(
    tmp_path: Path,
) -> None:
    # With no `--`, `--end-of-options` is what keeps `-x/stayfixed.toml` a path: dropping it makes
    # `ls-tree` refuse the argument as an option, a false failure that refuses more, so it is
    # not declared as a mutation.
    project = clone(tmp_path, BASE, under="-x")
    assert read_base(project / "-x", REMOTE_MAIN, branch="main") == BASE


def test_a_project_root_moved_behind_a_symlink_is_refused(tmp_path: Path) -> None:
    # The change moves the project and leaves a link where it was: git resolves the link and
    # looks for `newdir/stayfixed.toml` on the base, which has none, so the change would be the
    # bootstrap and decide its own configuration.
    project = clone(tmp_path, BASE, under="sub")
    git(project, "mv", "sub", "newdir")
    os.symlink("newdir", project / "sub")
    commit(project, "chore: move the project")
    with pytest.raises(Refusal, match="symlink"):
        read_base(project / "sub", REMOTE_MAIN, branch="main")


def test_a_component_linked_back_to_the_repository_s_top_is_refused(tmp_path: Path) -> None:
    # `app -> .` resolves to the top as well, so an ancestor search from the nearest end would
    # stop at `app` and read `sub/` as the prefix, where the base keeps `app/sub/`.
    project = clone(tmp_path, BASE, under="app/sub")
    git(project, "mv", "app/sub", "sub")
    if (project / "app").exists():
        (project / "app").rmdir()
    os.symlink(".", project / "app")
    commit(project, "chore: link the old place back to the top")
    with pytest.raises(Refusal, match="symlink"):
        read_base(project / "app" / "sub", REMOTE_MAIN, branch="main")


def test_a_link_above_the_repository_is_the_machine_s_and_is_admitted(tmp_path: Path) -> None:
    # `/tmp` on macOS, a symlinked home, a logical `$PWD`: a link above the repository is not
    # the repository's to author. A first draft refused any root that did not equal its own
    # resolution, which refuses more, so it is not declared as a mutation.
    real = tmp_path / "real"
    real.mkdir()
    project = clone(real, BASE)
    os.symlink(real, tmp_path / "link")
    through = tmp_path / "link" / project.name
    assert repository_prefix(through) == ""
    assert read_base(through, REMOTE_MAIN, branch="main") == BASE


def test_a_root_that_is_itself_a_link_into_the_repository_is_refused(tmp_path: Path) -> None:
    # No ancestor of the root resolves to git's top: the link names the project's directory, not
    # the repository, so the root's own spelling says nothing about where the base keeps it.
    # Removing that refusal crashes on the missing ancestor (an internal error, exit 2: it fails
    # closed), and falling back to the root or to git's top is still refused by the spelling
    # check, so no mutation of it reaches the bootstrap and it has no oracle entry.
    project = clone(tmp_path, BASE, under="sub")
    os.symlink(project / "sub", tmp_path / "link")
    with pytest.raises(Refusal, match="symlink"):
        read_base(tmp_path / "link", REMOTE_MAIN, branch="main")


def test_a_prefix_git_spells_otherwise_than_the_caller_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # What a case-folding disk does, held on every platform: git answers `SUB/` for the root the
    # caller spells `sub`. The base keeps one of the two, and nothing here can tell which.
    project = clone(tmp_path, BASE, under="sub")
    real = gitenv.git_run

    def upper_prefix(root: Path, *args: str, **kwargs: Any) -> tuple[int, str]:
        code, out = real(root, *args, **kwargs)
        if "--show-prefix" in args:
            top, _, prefix = out.partition("\n")
            out = f"{top}\n{prefix.upper()}"
        return code, out

    monkeypatch.setattr(committed, "git_run", upper_prefix)
    with pytest.raises(Refusal, match="symlink"):
        read_base(project / "sub", REMOTE_MAIN, branch="main")


@pytest.mark.parametrize(
    "spelling", ["project/SUB", "PROJECT/sub"], ids=["below-the-top", "the-top"]
)
def test_a_root_spelled_otherwise_than_git_spells_it_is_refused(
    spelling: str, tmp_path: Path
) -> None:
    project = clone(tmp_path, BASE, under="sub")
    if not (project / "SUB").exists():
        pytest.skip("this file system tells `SUB` from `sub`")
    # On a case-folding disk `SUB` is `sub`, but the base has no `SUB/stayfixed.toml`. Spelled
    # otherwise at the top itself, no ancestor of the root resolves to git's top at all. Both
    # skip on Linux; the two cases above hold the same refusals there.
    with pytest.raises(Refusal, match="symlink"):
        read_base(tmp_path / spelling, REMOTE_MAIN, branch="main")


def test_git_failing_to_list_the_base_is_a_failure_and_never_the_bootstrap(
    tmp_path: Path,
) -> None:
    project = clone(tmp_path, BASE)
    tree = git(project, "rev-parse", f"{REMOTE_MAIN}^{{tree}}").strip()
    loose = project / ".git" / "objects" / tree[:2] / tree[2:]
    assert loose.is_file(), "the case needs the base's tree as a loose object"
    loose.unlink()
    with pytest.raises(Failure, match=re.escape("fetch-depth: 0")):
        read_base(project, REMOTE_MAIN, branch="main")


def test_a_base_copy_that_is_not_utf8_is_a_failure_and_never_the_bootstrap(
    tmp_path: Path,
) -> None:
    # `git_run` decodes git's answer losslessly, so a blob that is not UTF-8 comes back as text
    # carrying surrogate escapes, and `tomllib` accepts them: the base's bytes, which the
    # loader refuses in the tree's own copy, would govern the run. Read as "listed nothing" or
    # as an empty document instead, the change would govern itself, or be judged against no
    # configuration. It is refused in the loader's words, and without the shallow-checkout
    # remedy, which would send the owner to fetch history they already have. Mutation
    # (declared): drop the refusal -> the base is returned and this reddens.
    project = clone(tmp_path, b'[stayfixed]\nversion = "\xff"\n')
    (project / "stayfixed.toml").write_text(BASE, encoding="utf-8")
    with pytest.raises(Failure, match=re.escape(BASE_NOT_UTF8)) as caught:
        read_base(project, default_base(project), branch="main")
    assert "fetch-depth" not in str(caught.value)


# A base copy whose one non-ASCII character is valid UTF-8, and the same copy with a byte that
# is not: the one stayfixed reads as the tree's own copy reads it, and the one it refuses.
NON_ASCII_BASE = BASE.replace('name = "widget"', 'name = "widget"\n# caf\u00e9')
NOT_UTF8_BASE = b'[stayfixed]\nversion = "\xff"\n'


@pytest.mark.parametrize("base", [NON_ASCII_BASE, NOT_UTF8_BASE], ids=["utf-8", "not-utf-8"])
def test_the_base_copy_is_read_as_utf_8_whatever_the_locale_decodes_git_s_answers_with(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, base: str | bytes
) -> None:
    # `git_run` decodes with the filesystem's codec, which on Linux follows the locale. Where it
    # is latin-1 every byte decodes, so a copy that is not UTF-8 came back with no surrogate for
    # the refusal to find and was parsed, `0xff` read as `y` with a diaeresis; and a valid UTF-8
    # copy came back as mojibake, a different document from the one the tree's loader reads as
    # UTF-8. The bytes git printed
    # are recovered and decoded as UTF-8, so both answers are the same under every locale. The
    # codec is simulated at the runner's one seam, `pipe_encoding`, so this holds on a machine
    # with no latin-1 locale installed. Mutation (declared): check the decoded text for
    # surrogates again instead of decoding the bytes -> both cases redden.
    monkeypatch.setattr(gitenv, "pipe_encoding", lambda: "latin-1")
    project = clone(tmp_path, base)
    (project / "stayfixed.toml").write_text(BASE, encoding="utf-8")
    if isinstance(base, bytes):
        with pytest.raises(Failure, match=re.escape(BASE_NOT_UTF8)):
            read_base(project, default_base(project), branch="main")
    else:
        assert read_base(project, default_base(project), branch="main") == base


def test_a_real_latin_1_locale_reads_the_base_copy_as_utf_8(
    tmp_path: Path, latin1_locale: str
) -> None:
    # The case above without the seam: a child process under a real latin-1 locale, where the
    # machine has one. On Linux the pipe's codec is then latin-1; on macOS it stays UTF-8, and
    # the case holds that the locale changes neither answer. A stock Linux runner has no such
    # locale, which is why the seam case carries the oracle entry.
    project = clone(tmp_path / "ok", NON_ASCII_BASE)
    broken = clone(tmp_path / "broken", NOT_UTF8_BASE)
    script = (
        "import sys\n"
        "from pathlib import Path\n"
        "from stayfixed.assess.base import read_base\n"
        "from stayfixed.errors import Failure\n"
        "for root in sys.argv[1:]:\n"
        "    try:\n"
        "        print(ascii(read_base(Path(root), 'refs/remotes/origin/main', branch='main')))\n"
        "    except Failure as exc:\n"
        "        print(ascii(str(exc)))\n"
    )
    done = subprocess.run(
        [sys.executable, "-c", script, str(project), str(broken)],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "LC_ALL": latin1_locale, "PYTHONUTF8": "0"},
    )
    assert done.returncode == 0, done.stderr
    assert done.stdout.splitlines() == [ascii(NON_ASCII_BASE), ascii(BASE_NOT_UTF8)]


def test_a_root_outside_any_repository_is_a_failure(tmp_path: Path) -> None:
    nowhere = tmp_path / "nowhere"
    nowhere.mkdir()
    with pytest.raises(Failure, match=re.escape(NOT_A_REPOSITORY)):
        read_base(nowhere, REMOTE_MAIN, branch="main")


def test_a_repository_git_will_not_answer_for_is_not_called_no_repository(
    tmp_path: Path,
) -> None:
    # A worktree whose git directory is gone: git exits 128 exactly as outside a repository, and
    # a CI checkout of dubious ownership does the same. Both fail; the message must not send the
    # owner looking for a repository that is there. Raising `NOT_A_REPOSITORY` whatever the disk
    # says reddens this; it is wording, not permission, so it has no oracle entry.
    broken = tmp_path / "broken"
    broken.mkdir()
    (broken / ".git").write_text(f"gitdir: {tmp_path / 'gone'}\n", encoding="utf-8")
    with pytest.raises(Failure, match=re.escape(ROOT_UNANSWERED)):
        read_base(broken, REMOTE_MAIN, branch="main")


# The platform's base and root: what `stayfixed gate` is handed raw by the reusable workflow, and
# what the workflow's shell step checked before Python did. Each case is the successor of one of
# that step's cases, against a real clone whose upstream also has a branch the author pushed, so
# a `base:` naming it meets a ref that exists, which is the attack, and not a missing one that
# fails for another reason.
PUSHED = "a-branch-the-author-pushed"


def _platform_clone(tmp_path: Path, *, under: str = "") -> Path:
    project = clone(tmp_path, BASE, under=under)
    git(tmp_path / "upstream", "branch", PUSHED)
    git(project, "fetch", "-q")
    assert git(project, "rev-parse", f"refs/remotes/origin/{PUSHED}").strip()
    return project


def _platform(project: Path, **values: str) -> str:
    given = {"pr_base": "", "base_input": "", "default_branch": "", **values}
    return platform_base(project, **given)


def _gate(project: Path, tmp_path: Path, *argv: str) -> tuple[int, str]:
    """`stayfixed gate` with `argv`, its exit code and both streams together."""
    code, out, err = cli(project, tmp_path, "gate", *argv)
    return code, out + err


def test_a_tag_named_like_the_tracking_branch_does_not_choose_the_platform_base(
    tmp_path: Path,
) -> None:
    """git resolves a short `origin/main` through `refs/tags/` before `refs/remotes/`, and
    `fetch-depth: 0` fetches every tag, so whoever may push a tag of that name would choose the
    configuration every pull request is judged against. The base resolves the fully qualified
    tracking ref. Mutation (declared): `mutations/`'s "the base resolves through a short name".
    """
    project = _platform_clone(tmp_path)
    shadow(project, "origin/main")
    resolved = _platform(project, pr_base="main")
    assert resolved == git(project, "rev-parse", REMOTE_MAIN).strip()
    assert resolved != git(project, "rev-parse", "refs/tags/origin/main").strip()


def test_a_base_input_that_disagrees_with_the_pr_base_is_refused_unechoed(tmp_path: Path) -> None:
    """On a `pull_request` the caller file runs from the merge commit, the author's copy, so a
    `base:` naming a branch the author pushed would choose the configuration the change is
    judged against. `github.base_ref` cannot be written from the branch, so where both are given
    and differ the base is refused, naming the platform's value and never the author's.
    Mutation (declared): `mutations/`'s "a disagreeing base input is admitted".
    """
    project = _platform_clone(tmp_path)
    with pytest.raises(Refusal) as refused:
        _platform(project, pr_base="main", base_input=PUSHED)
    assert "this pull request's base is main" in str(refused.value)
    assert PUSHED not in str(refused.value)
    # Through the command too: a refusal, exit 2, where the shell step exited 1.
    code, said = _gate(
        project, tmp_path, "--pr-base=main", f"--base-input={PUSHED}", "--default-branch="
    )
    assert code == 2, said
    assert PUSHED not in said, said
    # Agreeing is not refused, and `base:` still decides on every event that reports no base,
    # which is what makes the refusal free.
    main = git(project, "rev-parse", REMOTE_MAIN).strip()
    assert _platform(project, pr_base="main", base_input="main") == main
    assert (
        _platform(project, base_input=PUSHED)
        == git(project, "rev-parse", f"refs/remotes/origin/{PUSHED}").strip()
    )


def test_the_platform_base_falls_back_to_the_pr_base_then_the_default_branch(
    tmp_path: Path,
) -> None:
    # The three in the workflow's order, none of them the tree under review: the caller's
    # `base:`, the pull request's base as the platform reports it, and the repository's default
    # branch. The pull request's base comes before the default branch, so a pull request into
    # another branch is judged against that branch. Mutation (declared): `mutations/`'s "the
    # fallback skips the pull request's base".
    project = _platform_clone(tmp_path)
    pushed = git(project, "rev-parse", f"refs/remotes/origin/{PUSHED}").strip()
    git(tmp_path / "upstream", "commit", "-q", "--allow-empty", "-m", "chore: move main")
    git(project, "fetch", "-q")
    main = git(project, "rev-parse", REMOTE_MAIN).strip()
    assert main != pushed
    assert _platform(project, pr_base="main") == main
    assert _platform(project, default_branch="main") == main
    assert _platform(project, pr_base=PUSHED, default_branch="main") == pushed
    # With none of the three the base is refused rather than guessed.
    with pytest.raises(Refusal, match=re.escape(NO_BASE)):
        _platform(project)


def test_a_dotdot_path_is_refused_unechoed(tmp_path: Path) -> None:
    """The adversary is a caller file whose `path:` points the gates at another checkout's
    configuration: `../upstream` here is a repository beside the checkout, as `../stayfixed`, the
    workflow's own, is beside CI's.

    Mutation (declared): `mutations/`'s "a root spelled with '..' is refused as a symlink".
    """
    project = _platform_clone(tmp_path)
    platform = ("--pr-base=main", "--base-input=", "--default-branch=")
    code, said = _gate(project, tmp_path, *platform, "--path=../upstream", "--only=config")
    assert code == 2, said
    assert "../upstream" not in said, said


@pytest.mark.parametrize("path", ["/the-other-checkout", "/", ".//", ".//the-other-checkout"])
def test_an_absolute_path_is_refused_unechoed(tmp_path: Path, path: str) -> None:
    # An absolute `path:` leaves the checkout without a `..`, and so does one that is absolute
    # once its leading `./` is dropped. Mutation (declared): `mutations/`'s "an absolute path is
    # admitted".
    with pytest.raises(Refusal, match=re.escape(PATH_LEAVES)) as refused:
        platform_root(tmp_path / "project", path)
    assert "the-other-checkout" not in str(refused.value)


@pytest.mark.parametrize(
    ("path", "below"),
    [
        ("", ""),
        (".", ""),
        ("./", ""),
        ("./sub/project/", "sub/project"),
        ("sub/project", "sub/project"),
        ("a dir with a space", "a dir with a space"),
        ("проект", "проект"),
    ],
)
def test_a_project_root_below_the_checkout_is_the_root(
    tmp_path: Path, path: str, below: str
) -> None:
    # The `path:` input a monorepo and the smoke fixture use. No character is refused: nothing it
    # is written into reads a line break as a key, so a root with a space or a name outside ASCII
    # is a root like any other.
    checkout = tmp_path / "checkout"
    assert platform_root(checkout, path) == (checkout / below if below else checkout)
    # And through the command, where the gates run at that root and read the base's copy there.
    project = _platform_clone(tmp_path, under=below)
    code, said = _gate(
        project,
        tmp_path,
        "--pr-base=main",
        "--base-input=",
        "--default-branch=",
        f"--path={path}",
        "--only=config",
    )
    assert code == 0, said
    # Unchanged, and not the bootstrap: the base's copy was read at the same root the tree's was.
    assert f"config: {UNCHANGED}" in said, said


PLATFORM = ("--pr-base=main", "--base-input=", "--default-branch=")


def test_a_root_git_would_take_for_a_repository_of_its_own_is_read_as_the_checkout_s_subdirectory(
    tmp_path: Path,
) -> None:
    """`HEAD`, `refs/` and `objects/` are names a tree may commit, and git asked in a directory
    holding them takes it for a repository of its own. With the platform's base `--root` is the
    checkout, whose repository the run names to git, so `app` is still the checkout's `app/` and
    the base's copy is read there. Mutation (declared): `mutations/`'s "the gate's git discovers
    the repository again".
    """
    project = _platform_clone(tmp_path, under="app")
    app = project / "app"
    (app / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    (app / "refs" / "heads").mkdir(parents=True)
    (app / "refs" / "heads" / "main").write_text(git(project, "rev-parse", REMOTE_MAIN))
    (app / "objects").mkdir()
    (app / "objects" / "kept").write_text("", encoding="utf-8")
    commit(project, "chore: files named like a repository's")
    # The premise: asked in `app`, git answers for `app` itself.
    assert git(app, "rev-parse", "--git-dir").strip() == "."
    code, said = _gate(project, tmp_path, *PLATFORM, "--path=app", "--only=config")
    assert code == 0, said
    assert f"config: {UNCHANGED}" in said, said


def test_a_path_through_a_committed_link_into_another_repository_is_refused(
    tmp_path: Path,
) -> None:
    # `link -> ../upstream` leads into a repository that holds the base commit and a
    # `stayfixed.toml` at its top, so both copies would be read there, and neither is the
    # checkout's. The link is below the checkout, the tree's to write, so it is refused as a link
    # would be anywhere below the repository's top.
    project = _platform_clone(tmp_path)
    os.symlink(os.path.join("..", "upstream"), project / "link")
    commit(project, "chore: a link out of the checkout")
    code, said = _gate(project, tmp_path, *PLATFORM, "--path=link", "--only=config")
    assert code == 2, said
    assert "symlink" in said, said


def test_a_checkout_reached_through_a_linked_parent_is_read_as_the_checkout(
    tmp_path: Path,
) -> None:
    # `/tmp` on macOS, a symlinked home: a link above the checkout is the machine's, and the
    # repository named to git is the checkout's own however `--root` is spelled.
    real = tmp_path / "real"
    real.mkdir()
    project = _platform_clone(real, under="app")
    os.symlink(real, tmp_path / "link")
    through = tmp_path / "link" / project.name
    code, said = _gate(through, tmp_path, *PLATFORM, "--path=app", "--only=config")
    assert code == 0, said
    assert f"config: {UNCHANGED}" in said, said


def test_a_root_below_the_checkout_s_top_is_read_in_the_checkout(tmp_path: Path) -> None:
    # The platform's run reproduced from the project's own directory: `--root` is that directory,
    # and the repository named to git is the checkout's, whose top git finds from there.
    project = _platform_clone(tmp_path, under="app")
    code, said = _gate(project / "app", tmp_path, *PLATFORM, "--only=config")
    assert code == 0, said
    assert f"config: {UNCHANGED}" in said, said


@pytest.mark.parametrize(
    ("name", "document"),
    [
        ("x\n::error file=README.md,line=1::forged", "not toml = ["),
        ("y\n::warning::forged", "[bogus]\n"),
    ],
    ids=["not-toml", "unknown-section"],
)
def test_a_path_holding_a_line_break_prints_no_workflow_command(
    tmp_path: Path, name: str, document: str
) -> None:
    # `path:` is admitted whatever its characters, so a root whose name holds a line break
    # reaches every message that names the tree's `stayfixed.toml`, and a runner reads a workflow
    # command from any line of the step's output. Printed through `printed.quoted`, the name
    # stays on its line.
    project = _platform_clone(tmp_path)
    (project / name).mkdir()
    (project / name / "stayfixed.toml").write_text(document, encoding="utf-8")
    commit(project, "chore: a root named by the pull request")
    code, said = _gate(
        project,
        tmp_path,
        "--pr-base=main",
        "--base-input=",
        "--default-branch=",
        f"--path={name}",
        "--annotate",
    )
    assert code == 1, said
    assert [line for line in said.splitlines() if line.startswith("::")] == [], said


@pytest.mark.parametrize("branch", ["a..b", "-x"])
def test_a_branch_check_ref_format_refuses_is_refused(tmp_path: Path, branch: str) -> None:
    # A plain call with no mutation entry: it refuses no legitimate branch, and the qualified
    # ref already decides which commit is read. Never echoed, since `base:` may be what it
    # refuses; and a refusal, where a range or an option-shaped name would otherwise reach
    # `rev-parse` and fail as a base missing from the checkout.
    project = _platform_clone(tmp_path)
    with pytest.raises(Refusal, match=re.escape(BASE_NOT_A_BRANCH)) as refused:
        _platform(project, base_input=branch)
    assert branch not in str(refused.value)
    code, said = _gate(
        project, tmp_path, "--pr-base=", f"--base-input={branch}", "--default-branch="
    )
    assert code == 2, said
    assert BASE_NOT_A_BRANCH in said, said


def test_a_subset_of_the_platform_base_flags_is_refused(tmp_path: Path) -> None:
    # The three flags are one form: a subset would read the flags left out as empty, and
    # beside `--base` one of two forms would be ignored. Each is a refusal before any base is read.
    project = _platform_clone(tmp_path)
    code, said = _gate(project, tmp_path, "--pr-base=main")
    assert code == 2, said
    assert "missing: --base-input, --default-branch" in said, said
    code, said = _gate(project, tmp_path, "--base-input=", "--default-branch=main")
    assert code == 2, said
    assert "missing: --pr-base" in said, said
    sha = git(project, "rev-parse", REMOTE_MAIN).strip()
    code, said = _gate(
        project, tmp_path, "--base", sha, "--pr-base=main", "--base-input=", "--default-branch="
    )
    assert code == 2, said
    assert "two forms of one input" in said, said
    # `--path` is admitted with either form, and with neither.
    code, said = _gate(project, tmp_path, "--base", sha, "--path=.", "--only=config")
    assert code == 0, said
    code, said = _gate(project, tmp_path, "--path=.", "--only=config")
    assert code == 0, said
