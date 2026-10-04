"""Every site that asks git a question reads the answer through `gitenv.git_run`, exactly.

Six sites ran `git` through a `subprocess.run(text=True)` of their own and decoded its answer
strictly in the locale's codec: one byte that was not UTF-8 in the answer — a checkout path, an
`origin` URL, a hooks path, a dirty file's name — raised `UnicodeDecodeError` out of the command,
and every hook, as an internal error. `git_run` decodes losslessly in the filesystem's codec, and
each site now decides what an answer it cannot use as text means: a path is compared with and
opened on the disk as it is, a count counts it, and a value that must be written into a UTF-8
file is refused by name before anything is written.

The bytes are planted in `.git/config` or the index, or printed by a stand-in `git`, so every case
runs where the disk cannot hold such a name (APFS refuses one).
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from stayfixed.attach.write import _worktrees, attach
from stayfixed.errors import Refusal
from stayfixed.gitenv import GitUnavailable, origin_remote
from stayfixed.guards.commit import commits_in
from stayfixed.guards.githooks import hooks_dir
from stayfixed.guards.hygiene import inspect
from stayfixed.hooks.dispatch import _git_toplevel
from stayfixed.ledger.scan import TOP_LEVEL, _committed_files
from stayfixed.overlay.sync import overlay_sync
from stayfixed.project.detect import NOT_DERIVABLE, detect
from stayfixed.setup.run import _repository
from tests.attach.test_write import RULE, _attachable
from tests.cli import cli
from tests.gitfixture import git, needs_git, plant_path
from tests.guards.test_hygiene import config, repo
from tests.project.repos import repository
from tests.runners import Recorder
from tests.snapshot import assert_snapshot_unchanged, snapshot

# An `origin` URL whose last byte is latin-1, and the `str` the filesystem's codec spells it as.
LATIN1_URL = b"https://example.com/caf\xe9"
DECODED_URL = os.fsdecode(LATIN1_URL)


def _append(path: Path, raw: bytes) -> None:
    with path.open("ab") as handle:
        handle.write(raw)


def _stand_in_git(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, printed: bytes) -> None:
    """A `git` first on `PATH` that prints `printed` for any question; `scrubbed_env` keeps
    `PATH`, so it is the one `git_run` launches."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    octal = "".join(f"\\{byte:03o}" for byte in printed)
    (bin_dir / "git").write_text(f"#!/bin/sh\nprintf '{octal}'\n", encoding="utf-8")
    (bin_dir / "git").chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")


def test_the_hook_path_reads_a_checkout_path_that_is_not_utf_8_as_that_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # `project_root()` feeds every hook decision, and its git fallback decoded strictly: on
    # Linux a checkout under a latin-1 directory made every hook an internal error, which
    # PreToolUse turns into a refusal of every tool call (reproduced in a Linux container with
    # a payload that names no `cwd`). The answer is the path on disk, byte for byte — a trailing
    # space included, which the old `strip()` took off. Mutation (declared, on `gitenv`): the
    # decode made strict again -> this reddens.
    _stand_in_git(tmp_path, monkeypatch, b"/checkouts/caf\xe9 \n")
    assert _git_toplevel(tmp_path) == Path(os.fsdecode(b"/checkouts/caf\xe9 "))


@needs_git
def test_an_origin_url_that_is_not_utf_8_is_answered_as_itself(tmp_path: Path) -> None:
    # Reproduced: `printf '[remote "origin"]\n\turl = https://x/caf\xe9\n' >> .git/config`, then
    # `stayfixed init --questions` and `init --yes` both ended as `internal error:
    # UnicodeDecodeError`. The answer is the URL as the filesystem's codec spells it, so it can
    # still be compared with a recorded one; it never equals one read out of a TOML file.
    # Mutation (declared, on `gitenv`): the decode made strict again -> this reddens.
    root = tmp_path / "project"
    root.mkdir()
    git(root, "init", "-q")
    _append(root / ".git" / "config", b'[remote "origin"]\n\turl = ' + LATIN1_URL + b"\n")
    assert origin_remote(root) == DECODED_URL
    # The name `init` suggests from it is outside the name grammar, so it is asked for rather
    # than suggested, and refused by the grammar under `--yes`, never with the URL's bytes.
    assert (detect(root, lenient=True).name, detect(root, lenient=True).sources["name"]) == (
        "",
        NOT_DERIVABLE,
    )
    with pytest.raises(Refusal) as refused:
        detect(root)
    assert "caf" not in str(refused.value)


@needs_git
def test_a_git_that_fails_everything_is_not_a_repository_without_an_origin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Both answers off one checkout with no `origin`: git that runs says "no such remote" with a
    # non-zero exit, which is `None`, and a git that exits non-zero for everything — the Xcode
    # shim with an unaccepted licence — must not read the same way, or the user is sent to
    # `stayfixed attach` about their own `git`. Mutation (declared): `mutations/`'s "a broken git
    # reads as a repository with no origin remote".
    root = tmp_path / "project"
    root.mkdir()
    git(root, "init", "-q")
    assert origin_remote(root) is None

    def broken(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        return subprocess.CompletedProcess(args, 69, b"", b"You have not agreed to the licence\n")

    monkeypatch.setattr("stayfixed.gitenv.subprocess.run", broken)
    with pytest.raises(GitUnavailable):
        origin_remote(root)


@needs_git
def test_init_questions_on_an_origin_url_that_is_not_utf_8_asks_and_does_not_crash(
    tmp_path: Path,
) -> None:
    # The command it was reproduced with, through the real parser. Mutation (declared, on
    # `gitenv`): the decode made strict again -> this reddens.
    code, out, err = cli(repository(tmp_path, origin=DECODED_URL), tmp_path, "init", "--questions")
    assert code == 0, err
    assert "internal error" not in err
    assert "caf" not in out


@needs_git
def test_a_hooks_path_that_is_not_utf_8_is_the_directory_git_names(tmp_path: Path) -> None:
    # `core.hooksPath` is the machine owner's to set, in any bytes; decoded strictly, `setup
    # --git-hooks`, `attach` and `doctor`'s pre-commit row all ended as an internal error. The
    # answer is the directory itself, so the hook lands where git will run it. Mutation
    # (declared, on `gitenv`): the decode made strict again -> this reddens.
    root = tmp_path / "project"
    root.mkdir()
    git(root, "init", "-q")
    _append(root / ".git" / "config", b"[core]\n\thooksPath = hooks-caf\xe9\n")
    assert hooks_dir(root) == root / os.fsdecode(b"hooks-caf\xe9")


@needs_git
def test_a_dirty_name_that_is_not_utf_8_is_counted_and_not_raised(tmp_path: Path) -> None:
    # `git status --porcelain` prints a name raw under `core.quotePath=false`, a common setting
    # for anyone whose names are not ASCII; decoded strictly, the red-run hint of `test hygiene`
    # became an internal error. Planted in the index, so the name is both added and missing
    # from the disk: one entry. Mutation (declared, on `gitenv`): the decode made strict again
    # -> this reddens.
    root = repo(tmp_path)
    git(root, "config", "core.quotePath", "false")
    plant_path(root, b"caf\xe9.py")
    assert inspect(root, config(root)).dirty == 1


@needs_git
def test_the_commit_range_is_read_in_utf_8_whatever_git_is_told_to_print(tmp_path: Path) -> None:
    # The range's messages are judged as UTF-8, and git prints a log in whatever
    # `i18n.logOutputEncoding` says — the machine owner's global configuration reaches it
    # through `HOME`. Under latin-1 output a plain `café` in a message arrived in bytes that are
    # not UTF-8 and the range was refused as unjudgeable. The log asks for UTF-8 by name.
    # Mutation (declared): drop `--encoding=UTF-8` from the argv -> this reddens.
    root = repo(tmp_path)
    git(root, "config", "i18n.logOutputEncoding", "ISO-8859-1")
    git(root, "commit", "-q", "--allow-empty", "-m", "fix: café")
    [commit] = commits_in(root, "HEAD~1..HEAD")
    assert commit.message.startswith("fix: café")


def _worktree_with_a_carriage_return(tmp_path: Path) -> tuple[Path, Path]:
    main = tmp_path / "main"
    main.mkdir()
    git(main, "init", "-q", "-b", "main")
    git(main, "commit", "-q", "--allow-empty", "-m", "chore: seed")
    linked = tmp_path / "wt\rx"
    git(main, "worktree", "add", "-q", "-b", "side", str(linked))
    return main, linked


@needs_git
def test_a_worktree_whose_path_holds_a_carriage_return_is_listed_by_its_own_path(
    tmp_path: Path,
) -> None:
    # `worktree list --porcelain` ends each line with `\n` and prints a path's `\r` raw, and
    # `str.splitlines()` breaks at both: measured, `attach` listed `…/wt` for the worktree at
    # `…/wt\rx` — a directory that is not that worktree, and one `attach` then links into — and
    # `setup` recorded it among the project's checkouts in place of the real one. Lines are
    # split where git ends them. Mutation (declared): split with `splitlines()` again -> this
    # reddens.
    main, linked = _worktree_with_a_carriage_return(tmp_path)
    expected = linked.resolve()
    assert expected in [tree.resolve() for tree in _worktrees(main)]
    listed = _repository(main)
    assert listed is not None
    assert expected in [tree.resolve() for tree in listed.checkouts]


@needs_git
def test_attach_refuses_an_origin_it_cannot_record_before_writing_anything(tmp_path: Path) -> None:
    # The overlay's binding record is UTF-8 TOML, and an `origin` URL in other bytes cannot be
    # written into it: read losslessly, it reached `_record_binding` — the last of attach's
    # writes — and raised `UnicodeEncodeError` there, after the ignore region, the Codex rules,
    # the settings merge and the ledger. It is refused above every write instead, like a
    # checkout with no `origin`, and the refusal never quotes the URL. Mutation (declared):
    # drop the refusal -> the snapshot changes and `pytest.raises` reddens.
    hooks = {"SessionStart": [{"hooks": [{"type": "command", "command": "echo hello"}]}]}
    root, store, machine = _attachable(
        tmp_path, allow=(RULE,), hooks=hooks, codex="# a standing rule\n", origin=DECODED_URL
    )
    before = snapshot(root)
    assert before
    with pytest.raises(Refusal, match="not UTF-8") as refused:
        attach(
            root,
            store=store,
            machine=machine,
            confirmed=True,
            trust_remote=True,
            runner=Recorder(),
            home=tmp_path / "home",
        )
    assert "caf" not in str(refused.value)
    assert_snapshot_unchanged(root, before)
    assert not (store.parent / "project.toml").exists()


@needs_git
def test_a_dirty_name_holding_a_line_separator_is_one_entry(tmp_path: Path) -> None:
    # U+2028 is valid UTF-8, `status --porcelain` prints it raw under `core.quotePath=false`,
    # and `str.splitlines()` breaks at it: one planted name counted as two in `test hygiene`'s
    # hint and in the overlay's sync row. Counted by the lines git wrote. Mutation (declared):
    # count with `splitlines()` again -> this reddens.
    root = repo(tmp_path)
    git(root, "config", "core.quotePath", "false")
    plant_path(root, "a\u2028b.py".encode())
    assert inspect(root, config(root)).dirty == 1
    assert overlay_sync(root).dirty == 1


@needs_git
def test_the_ledger_sweep_asks_git_for_a_root_whose_name_ends_in_a_space(tmp_path: Path) -> None:
    # `strip()` took the space off git's toplevel, so the root never equalled itself and the
    # sweep fell back to walking the disk: an ignored build artifact was swept as if it were a
    # file the change would commit. The line ending alone is taken off. Mutation (declared):
    # `strip()` the toplevel again -> the listing is `None` and this reddens.
    root = tmp_path / "project "
    root.mkdir()
    git(root, "init", "-q")
    (root / ".gitignore").write_text("build.md\n", encoding="utf-8")
    (root / "build.md").write_text("x\n", encoding="utf-8")
    (root / "kept.md").write_text("x\n", encoding="utf-8")
    listed = _committed_files(root, (TOP_LEVEL,))
    assert listed is not None
    assert root / "kept.md" in listed
    assert root / "build.md" not in listed
