"""`test attribute`: one failing command, run three times, and a verdict the three exit codes
determine.

This module never writes the working tree and never moves the checkout between commits: HEAD
and the merge-base are extracted with `git archive` into a scratch directory. Run 1 does
execute the caller's command in the working tree, so whatever that command writes there it
writes. The command itself is the caller's — `uv sync --locked && uv run pytest …` is what
makes run 2 and run 3 "synced" — so the tool is the same for every stack.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from stayfixed import gitenv
from stayfixed.errors import Failure
from stayfixed.findings import LISTED_LIMIT
from stayfixed.gitenv import GIT_TIMEOUT_SECONDS, NO_ANSWER, SHALLOW, git_run
from stayfixed.guards.attribute import VERDICTS, attribute
from stayfixed.runner import NOT_FOUND, TIMED_OUT, Completed
from tests import gitfixture

needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")


@dataclass
class _Coded:
    """A runner that answers by the directory it is run in: the tree decides the exit code.

    Not `tests.runners.Recorder`, because it answers a different question. That one answers by
    the argv, and every run here launches the same argv: what tells the three runs apart is the
    tree each one is launched in (the working tree, HEAD's extraction, the merge base's), so the
    exit code is keyed on `cwd.name`. And it snapshots that tree at the moment of the call,
    because `attribute` removes its scratch extractions before it returns and the snapshot is
    the only evidence of what each run actually ran over.
    """

    codes: dict[str, int]
    calls: list[tuple[list[str], Path]] = field(default_factory=list)
    trees: dict[str, dict[str, str]] = field(default_factory=dict)

    def launch(self, argv: list[str], cwd: Path) -> Completed:
        self.calls.append((argv, cwd))
        self.trees[cwd.name] = {
            str(p.relative_to(cwd)): p.read_text(encoding="utf-8")
            for p in cwd.rglob("*")
            if p.is_file() and ".git" not in p.parts
        }
        return Completed(self.codes.get(cwd.name, 0), "", "")


def _git(root: Path, *args: str) -> str:
    """The shared fixture `git`, stripped: every call site here compares a single ref or sha."""
    return gitfixture.git(root, *args).strip()


def _repo(tmp_path: Path) -> Path:
    """`main` with one commit, then `feature` with one more, then `main` advanced past the fork."""
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    (root / "a.txt").write_text("base\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "-c", "user.email=a@b.c", "-c", "user.name=a", "commit", "-qm", "base")
    _git(root, "switch", "-qc", "feature")
    (root / "a.txt").write_text("feature\n", encoding="utf-8")
    _git(root, "-c", "user.email=a@b.c", "-c", "user.name=a", "commit", "-qam", "feature")
    _git(root, "switch", "-q", "main")
    (root / "later.txt").write_text("later\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "-c", "user.email=a@b.c", "-c", "user.name=a", "commit", "-qm", "later")
    _git(root, "switch", "-q", "feature")
    return root


@needs_git
def test_the_three_runs_land_in_the_working_tree_head_and_the_merge_base(tmp_path: Path) -> None:
    # Run 1 is the working tree as it is; run 2 is HEAD's committed tree; run 3 is the
    # merge-base with `--base`, NOT the base's tip — a base that advanced after the fork would
    # otherwise leak later commits into the "before" side. Proved from the files the archives
    # left: the head copy carries the feature edit, the base copy carries neither the feature
    # edit nor `later.txt`.
    #
    # Mutation (declared): archive `base` instead of `merge_base` -> the base copy carries
    # `later.txt` and the last assertion reddens.
    root = _repo(tmp_path)
    (root / "a.txt").write_text("uncommitted\n", encoding="utf-8")
    runner = _Coded({})
    result = attribute(root, command="true", base="main", runner=runner)
    assert [cwd.name for _, cwd in runner.calls] == ["repo", "head", "base"]
    assert all(argv == ["sh", "-c", "true"] for argv, _ in runner.calls)
    # The scratch directory is gone when `attribute` returns, so the stub snapshots each
    # tree at call time (`_Coded.trees`) and the assertions are over the snapshots.
    head, base = runner.trees["head"], runner.trees["base"]
    assert head["a.txt"] == "feature\n"
    assert base["a.txt"] == "base\n"
    assert "later.txt" not in base
    assert (root / "a.txt").read_text(encoding="utf-8") == "uncommitted\n"
    assert result.merge_base == _git(root, "merge-base", "HEAD", "main")


@needs_git
def test_several_merge_bases_leave_the_attribution_undetermined(tmp_path: Path) -> None:
    # A criss-cross: `main` fixes a failure and then merges a colleague's side branch, forked
    # before the fix and committed after it; the change merges the fixing commit and the side
    # branch itself, then breaks it again. `git merge-base` answers the side branch, which fails
    # too: run 3 failed there and the failure the change brought back was filed as
    # pre-existing. Each merge base is as much "before this change" as the other and they
    # disagree, so no verdict is given, nothing is run, and both are named. Mutations
    # (declared): `--all` dropped, or several merge bases accepted -> a verdict comes back.
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    (root / "state.txt").write_text("broken\n", encoding="utf-8")
    _git(root, "add", "-A")
    gitfixture.dated(root, 1, "commit", "-q", "-m", "broken")
    shape = gitfixture.criss_cross(
        root, lambda: (root / "state.txt").write_text("fixed\n", encoding="utf-8")
    )
    (root / "state.txt").write_text("broken\n", encoding="utf-8")
    gitfixture.dated(root, 6, "commit", "-q", "-am", "break it again")
    runner = _Coded({})
    with pytest.raises(Failure, match="undetermined") as caught:
        attribute(root, command="grep -q fixed state.txt", base="main", runner=runner)
    assert shape.fixed in str(caught.value) and shape.side in str(caught.value)
    assert runner.calls == []


@needs_git
def test_a_shallow_clone_leaves_the_attribution_undetermined(tmp_path: Path) -> None:
    # In a shallow clone the commit HEAD forked from can be cut off and the merge base git sees
    # be an older one, so run 3 can be a tree from before the fix a failure broke. No verdict,
    # nothing run, and the remedy named. Mutation (declared, on `gitenv`): the shallow answer
    # ignored -> the clone below, whose tip is its own merge base, gets a verdict.
    root = _repo(tmp_path)
    shallow = tmp_path / "shallow"
    _git(tmp_path, "clone", "-q", "--depth", "1", "--branch", "main", root.as_uri(), str(shallow))
    assert _git(shallow, "rev-parse", "--is-shallow-repository") == "true"
    runner = _Coded({})
    with pytest.raises(Failure, match="undetermined") as caught:
        attribute(shallow, command="true", base="origin/main", runner=runner)
    assert SHALLOW in str(caught.value) and "--unshallow" in str(caught.value)
    assert runner.calls == []


@needs_git
@pytest.mark.parametrize(
    ("answer", "cause"),
    [(-1, NO_ANSWER), (128, "git exited 128")],
    ids=["no-answer", "refused"],
)
def test_a_shallow_check_git_does_not_answer_leaves_the_attribution_undetermined(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, answer: int, cause: str
) -> None:
    # Whether the clone is shallow is a question too: read as "not shallow" when git gave no
    # answer or refused, a shallow clone went on to the merge base it could see. Mutation
    # (declared, on `gitenv`): the shallow check's failure ignored -> a verdict comes back.
    root = _repo(tmp_path)
    gitfixture.answer_shallow_check(monkeypatch, answer)
    runner = _Coded({})
    with pytest.raises(Failure, match="undetermined") as caught:
        attribute(root, command="true", base="main", runner=runner)
    assert f"({cause})" in str(caught.value)
    assert runner.calls == []


@needs_git
@pytest.mark.parametrize(
    ("codes", "verdict"),
    [
        ({"head": 1, "base": 1}, VERDICTS[0]),  # pre-existing: not this change
        ({"head": 1, "base": 0}, VERDICTS[1]),  # this change
        ({"head": 0, "base": 1}, VERDICTS[2]),  # this change fixed a pre-existing failure
        ({"repo": 1, "head": 0, "base": 0}, VERDICTS[3]),  # environmental
        ({}, VERDICTS[4]),  # not reproduced
    ],
)
def test_each_verdict_follows_from_its_exit_codes(
    tmp_path: Path, codes: dict[str, int], verdict: str
) -> None:
    # The verdict table, one row per assertion. Mutation (declared): swap the "this change"
    # and "pre-existing" arms -> two rows redden.
    root = _repo(tmp_path)
    result = attribute(root, command="true", base="main", runner=_Coded(codes))
    assert result.verdict == verdict


@needs_git
@pytest.mark.parametrize("code", [TIMED_OUT, NOT_FOUND])
def test_a_run_that_did_not_execute_is_a_failure_never_a_verdict(tmp_path: Path, code: int) -> None:
    # Runs 2 and 3 execute in fresh extractions with no environment, so a cold sync is the
    # likeliest thing to hit the seam's wall-clock cap — and two timeouts read as "fails on
    # both", the worst wrong answer a tool feeding a ledger entry can give. A timed-out or
    # unlaunchable run is a `Failure` naming which run; no verdict is computed.
    # Mutation (declared): drop the short-circuit -> the timeout is scored as a failure and
    # `pytest.raises` reddens.
    root = _repo(tmp_path)
    with pytest.raises(Failure, match="head"):
        attribute(root, command="true", base="main", runner=_Coded({"head": code}))


@needs_git
def test_an_archive_an_export_rule_shrank_is_a_failure_and_not_a_smaller_tree(
    tmp_path: Path,
) -> None:
    # `git archive` honours the ARCHIVED tree's own `.gitattributes`, and `export-ignore` is
    # versioned like everything else in it — so runs 2 and 3 can quietly execute against trees
    # that are missing files the working tree has, and the verdict then answers a question
    # nobody asked. The guard compares each extraction against `git ls-tree -r --name-only REF`
    # and fails naming how many files are missing; the count is asserted, not merely that
    # something was raised, because a wrong count means the comparison is measuring the wrong
    # two sets.
    #
    # Mutation (declared): drop the comparison -> the extraction is one file short, all three
    # runs complete, a verdict is returned and `pytest.raises` reddens.
    root = _repo(tmp_path)
    (root / "secret.txt").write_text("kept out of the archive\n", encoding="utf-8")
    (root / ".gitattributes").write_text("secret.txt export-ignore\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "-c", "user.email=a@b.c", "-c", "user.name=a", "commit", "-qm", "exported")
    with pytest.raises(Failure, match=r"missing 1 tracked file"):
        attribute(root, command="true", base="main", runner=_Coded({}))


@needs_git
def test_a_spaced_path_a_quoted_one_and_a_dangling_symlink_are_not_missing_files(
    tmp_path: Path,
) -> None:
    # The export-rule guard once fired on ordinary repositories and blamed a `.gitattributes`
    # rule that was not there. Three independent sources, one fixture:
    #
    #   * `set(listing.split())` broke `sub dir/a b.txt` into `sub`, `dir/a` and `b.txt` —
    #     three phantom entries, none of them on disk;
    #   * without `-z`, `ls-tree` renders `quo"te.txt` as `"quo\"te.txt"` and a non-ASCII name
    #     in octal escapes, so `splitlines()` alone would still have missed two of these;
    #   * `found` built with `p.is_file()` alone drops a tracked DANGLING symlink, because
    #     `is_file()` follows the link.
    #
    # Each was measured against the real `git` before the fix. The assertion is that the call
    # returns a verdict at all: this guard's failure mode is a `Failure` on a healthy tree, so
    # "it did not raise" is the whole claim, and the runner's tree snapshot pins that the
    # awkward names really were in the extraction rather than quietly absent from both sides.
    #
    # Mutation (declared): `-z` and the NUL split back to `split()` -> this reddens.
    root = _repo(tmp_path)
    (root / "sub dir").mkdir()
    (root / "sub dir" / "a b.txt").write_text("spaced\n", encoding="utf-8")
    (root / 'quo"te.txt').write_text("quoted\n", encoding="utf-8")
    (root / "ünïcode.txt").write_text("wide\n", encoding="utf-8")
    (root / "dangling.txt").symlink_to("nowhere-at-all")
    _git(root, "add", "-A")
    _git(root, "-c", "user.email=a@b.c", "-c", "user.name=a", "commit", "-qm", "awkward names")
    runner = _Coded({})
    result = attribute(root, command="true", base="main", runner=runner)
    assert result.verdict == VERDICTS[4]
    head = runner.trees["head"]
    assert head["sub dir/a b.txt"] == "spaced\n"
    assert head['quo"te.txt'] == "quoted\n"


@needs_git
def test_a_tar_that_cannot_be_launched_is_a_finding_and_not_a_traceback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Every external program is optional at runtime and a missing binary is a reported finding:
    # `gitenv.git_run` answers `(-1, "")` and `runner` answers `Completed(NOT_FOUND, ...)`. The
    # `tar` call was the one launch in this module with nothing around it, so a machine without
    # `tar` got `FileNotFoundError` out of a library function, which only `cli.py`'s mapping
    # caught — as an internal error, exit 2.
    #
    # A PATH holding `git` and nothing else, rather than an empty one: an empty PATH breaks
    # the merge-base first and the test would pass for the wrong reason, never reaching `tar`.
    # The assertion names `tar`, so a `Failure` raised anywhere else on the path does not
    # satisfy it. Mutation (declared): drop the `except OSError` -> `FileNotFoundError`
    # escapes and `pytest.raises(Failure)` reddens.
    git_binary = shutil.which("git")
    assert git_binary is not None
    root = _repo(tmp_path)
    only_git = tmp_path / "bin"
    only_git.mkdir()
    (only_git / "git").symlink_to(git_binary)
    monkeypatch.setenv("PATH", str(only_git))
    with pytest.raises(Failure, match="tar could not be run"):
        attribute(root, command="true", base="main", runner=_Coded({}))


@needs_git
def test_a_git_that_could_not_be_launched_is_not_reported_as_an_exit_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # `git_run` answers `(-1, "")` when the binary could not be launched, and `-1` is a
    # sentinel and not an exit status — rendered as one, the message read "`git merge-base
    # HEAD origin/main` exited -1; is origin/main fetched?", which sends a reader to fetch a ref
    # when the answer is that there is no git on this machine. The assertion is on the cause,
    # not on the exception type. The first question asked is whether the clone is shallow, so
    # the cause surfaces there; the merge-base's own arm has the test below.
    root = _repo(tmp_path)
    gitfixture.no_git(monkeypatch, tmp_path / "empty")
    with pytest.raises(Failure, match="git could not be run"):
        attribute(root, command="true", base="main", runner=_Coded({}))


@needs_git
def test_a_merge_base_git_gave_no_answer_for_is_not_reported_as_an_exit_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The same sentinel one question later: the shallow check answered and the merge base did
    # not. Rendered as an exit code it read "exited -1; is main fetched?", sending a reader to
    # fetch a ref that is already here. Mutation (declared, on `gitenv`): `answered` ignored ->
    # the message asks whether the base is fetched and this reddens.
    root = _repo(tmp_path)
    real = git_run

    def unanswered(where: Path, *args: str, **kwargs: Any) -> tuple[int, str]:
        return (-1, "") if args[0] == "merge-base" else real(where, *args, **kwargs)

    monkeypatch.setattr(gitenv, "git_run", unanswered)
    with pytest.raises(Failure, match=re.escape(NO_ANSWER)) as caught:
        attribute(root, command="true", base="main", runner=_Coded({}))
    assert "fetched" not in str(caught.value)


@needs_git
def test_a_submodule_gitlink_is_present_and_not_a_missing_file(tmp_path: Path) -> None:
    # `git archive` materialises a gitlink as an EMPTY DIRECTORY, which is neither a file nor a
    # symlink — so the previous walk-and-subtract answered "missing 1 tracked file(s)" and
    # blamed a `.gitattributes` rule on every submodule-bearing repository. Measured before the
    # fix: `expected - found == {'mod'}`.
    #
    # The gitlink is written with `update-index --cacheinfo` rather than `git submodule add`:
    # the tree entry is the same `160000 commit <sha>` either way, and this form needs no
    # clone, no network and no `protocol.file.allow` relaxation.
    #
    # Mutation (declared): ask `is_file()` instead of `exists()` — the old semantics exactly —
    # and this reddens while the dangling-symlink case stays green.
    root = _repo(tmp_path)
    head = _git(root, "rev-parse", "HEAD")
    _git(root, "update-index", "--add", "--cacheinfo", f"160000,{head},mod")
    _git(root, "-c", "user.email=a@b.c", "-c", "user.name=a", "commit", "-qm", "a submodule")
    result = attribute(root, command="true", base="main", runner=_Coded({}))
    assert result.verdict == VERDICTS[4]


@needs_git
def test_the_tree_listing_is_not_bounded_by_the_argument_free_cap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`ls-tree -r` grows with the repository, so it does not run on the cap for queries that
    do not.

    `gitenv.GIT_TIMEOUT_SECONDS` is documented in its own file as the bound for "a local,
    argument-free, read-only query … which neither touches the network nor grows with the
    repository", and it instructs a caller whose query is not that shape to pass its own. This
    call was the one in the module whose cost *is* the repository's size, and it ran on the
    default five seconds — while the `git archive` twenty lines above it, over the same tree,
    was given 120.

    What the timeout costs is not an error. `git_run` answers `(-1, "")` on `TimeoutExpired`,
    so `code == 0 and missing` goes False and the export-rule comparison is **skipped with no
    note**: the verdict is then computed from a tree that really is missing files, which is the
    one outcome this comparison exists to prevent. A large monorepo, or any repository on a
    slow or network volume, is the trigger.

    Mutation (declared): the explicit bound is removed -> this reddens naming the five.
    """
    root = _repo(tmp_path)
    real = git_run
    bounds: dict[str, float] = {}

    def recorded(
        where: Path, *args: str, timeout: float = GIT_TIMEOUT_SECONDS, stdin: str | None = None
    ) -> tuple[int, str]:
        bounds[args[0]] = timeout
        return real(where, *args, timeout=timeout, stdin=stdin)

    monkeypatch.setattr("stayfixed.guards.attribute.git_run", recorded)
    attribute(root, command="true", base="main", runner=_Coded({}))
    # The walk's floor before the bound is read: a run that never reached `ls-tree` would make
    # a `.get` comparison vacuously true, and the archive is here to show the two agree.
    assert "ls-tree" in bounds, bounds
    assert "archive" in bounds, bounds
    assert bounds["ls-tree"] > GIT_TIMEOUT_SECONDS, bounds
    assert bounds["ls-tree"] == bounds["archive"], bounds


@needs_git
def test_a_listing_git_gave_no_answer_for_skips_the_comparison(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # `git_run`'s `(-1, "")` for the listing is a `git` that ran past its bound — it has just
    # produced the archive, so it runs. A listing git gave no answer for is no listing at all:
    # the export-rule comparison is skipped, and a verdict still comes back. Only the `ls-tree`
    # call is diverted, so the archive and the merge-base are still the real thing.
    #
    # Mutation (declared): a listing git gave no answer for raises the missing-files `Failure`
    # instead of skipping (`code == 0 and missing` becomes `code != 0 or missing`) — this
    # reddens.
    root = _repo(tmp_path)
    real = git_run

    def unanswered(
        where: Path, *args: str, timeout: float = GIT_TIMEOUT_SECONDS, stdin: str | None = None
    ) -> tuple[int, str]:
        if args[0] == "ls-tree":
            return -1, ""
        return real(where, *args, timeout=timeout, stdin=stdin)

    monkeypatch.setattr("stayfixed.guards.attribute.git_run", unanswered)
    result = attribute(root, command="true", base="main", runner=_Coded({}))
    assert result.verdict == VERDICTS[4]


@needs_git
def test_a_base_git_names_in_bytes_that_are_not_text_keeps_git_s_own_exit_code(
    tmp_path: Path,
) -> None:
    # The real thing, on every platform: git's error for a base it cannot resolve quotes the
    # base, raw, on stderr. Decoded strictly that stderr was a traceback; read as no answer it
    # became `-1`, and git's own exit status — the answer, "this ref is not here" — was lost for
    # a sentence about git not running. Never decoded, the exit code reaches the message.
    # Mutation (declared, on `gitenv`): decode git's stderr again -> the byte raises out of
    # `attribute` and this reddens.
    root = _repo(tmp_path)
    with pytest.raises(Failure, match="exited 128") as caught:
        attribute(root, command="true", base=os.fsdecode(b"caf\xe9"), runner=_Coded({}))
    assert "could not be run" not in str(caught.value)


@needs_git
@pytest.mark.parametrize("diverted", ["merge-base", "archive", "ls-tree"])
def test_git_diagnostics_this_process_cannot_decode_still_reach_a_verdict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, diverted: str
) -> None:
    # `git_run` used to decode stderr strictly as well as stdout, so git's own error text
    # carrying one non-UTF-8 byte raised out of `attribute`, or turned an answered call into
    # no answer. What is left to prove is that a diagnostic nobody reads changes nothing.
    #
    # Diverted at the `subprocess` seam and not at `git_run`, so the runner under test is the
    # real one: the real `git` still answers, with one latin-1 byte on stderr ahead of it.
    # Only `git` argv is diverted, so `tar` runs as it is.
    #
    # Mutation (declared, on `gitenv`): decode git's stderr again -> the byte raises out of
    # `attribute` and every case reddens.
    root = _repo(tmp_path)
    real = subprocess.run

    def noisy(argv: list[str], **kwargs: Any) -> Any:
        if argv[:1] == ["git"] and argv[3:4] == [diverted]:
            argv = ["sh", "-c", 'printf "caf\\351\\n" >&2; exec "$@"', "sh", *argv]
        return real(argv, **kwargs)

    monkeypatch.setattr(subprocess, "run", noisy)
    result = attribute(root, command="true", base="main", runner=_Coded({}))
    assert result.verdict == VERDICTS[4]


@needs_git
def test_a_tracked_name_that_is_not_utf_8_does_not_switch_off_the_export_rule_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # `ls-tree -z` prints a tracked name raw. Read as no answer, one planted latin-1 name made
    # the listing `-1`, the comparison was skipped, and an archive an `export-ignore` rule had
    # shrunk was judged as if it were the whole tree — the outcome the comparison exists to
    # prevent, reached by a filename. Decoded losslessly, the listing names every file and the
    # shrunk archive is refused.
    #
    # `tar` is a stand-in on `PATH` that extracts what it can and exits 0, as GNU tar does on
    # Linux, where CI's oracle runs: APFS refuses to create the latin-1 name (`Can't create:
    # Illegal byte sequence`, exit 1), which would fail `_extract` before the comparison. So the
    # count is 1 where the disk holds the name and 2 where it does not; either is a refusal.
    #
    # Mutation (declared, on `gitenv`): the answer read as no answer again -> the listing is
    # skipped, a verdict comes back and `pytest.raises` reddens.
    root = _repo(tmp_path)
    (root / "secret.txt").write_text("kept out of the archive\n", encoding="utf-8")
    (root / ".gitattributes").write_text("secret.txt export-ignore\n", encoding="utf-8")
    _git(root, "add", "-A")
    gitfixture.plant_path(root, b"caf\xe9.txt")
    _git(root, "-c", "user.email=a@b.c", "-c", "user.name=a", "commit", "-qm", "exported")
    real_tar = shutil.which("tar")
    assert real_tar is not None
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "tar").write_text(f'#!/bin/sh\n"{real_tar}" "$@"\nexit 0\n', encoding="utf-8")
    (bin_dir / "tar").chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")
    with pytest.raises(Failure, match=r"missing [12] tracked file"):
        attribute(root, command="true", base="main", runner=_Coded({}))


@needs_git
def test_an_archive_git_gave_no_answer_for_is_a_failure_and_not_an_exit_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # `git_run`'s `(-1, "")` for the archive is a `git` that could not be run or ran past its
    # bound. A `Failure` and not the listing's skip, because nothing was extracted — and not
    # "exited -1", which names no cause. Mutation (declared): the archive's `code == -1` arm
    # never taken — the exit-code sentence comes back and this reddens.
    root = _repo(tmp_path)
    real = git_run

    def unanswered(
        where: Path, *args: str, timeout: float = GIT_TIMEOUT_SECONDS, stdin: str | None = None
    ) -> tuple[int, str]:
        if args[0] == "archive":
            return -1, ""
        return real(where, *args, timeout=timeout, stdin=stdin)

    monkeypatch.setattr("stayfixed.guards.attribute.git_run", unanswered)
    with pytest.raises(Failure, match=re.escape(f"{NO_ANSWER}, so `git archive")) as caught:
        attribute(root, command="true", base="main", runner=_Coded({}))
    assert "exited" not in str(caught.value)


def test_many_merge_bases_are_counted_and_named_at_most_to_the_listed_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The merge bases are the history's, bounded in number by nothing: the refusal counts every
    # one and names the first `LISTED_LIMIT`. Git is not asked, since only the message is under
    # test. Mutation (oracle): `mutations/`'s "the attribution names every merge base" -> this
    # reddens.
    forks = [f"{n:040x}" for n in range(LISTED_LIMIT + 3)]
    monkeypatch.setattr("stayfixed.guards.attribute.fork_points", lambda *_: forks)
    runner = _Coded({})
    with pytest.raises(Failure) as caught:
        attribute(tmp_path, command="true", base="main", runner=runner)
    shown = ", ".join(forks[:LISTED_LIMIT])
    assert f"have {len(forks)} merge bases ({shown}, and 3 more), each" in str(caught.value)
    assert runner.calls == []
