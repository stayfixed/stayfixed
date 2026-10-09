"""The chained `prepare-commit-msg` hook and its installer, end to end through git."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from stayfixed.errors import Refusal
from stayfixed.guards.commit import offending_lines
from stayfixed.guards.githooks import (
    HOOK_MARKER,
    HOOK_NAME,
    Found,
    hooks_dir,
    install,
    uninstall,
)
from tests import gitfixture
from tests.floor import floor_env

ROOT = Path(__file__).resolve().parents[2]
# The hook exactly as stayfixed 0.2.0 wrote it into a repository, generated once from the tag.
RELEASED_0_2_0 = ROOT / "tests" / "fixtures" / "prepare-commit-msg-0.2.0"
pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")


@pytest.fixture(autouse=True)
def _scrubbed_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # `hooks_dir` runs git with `gitenv.scrubbed_env()`, which keeps `HOME` and cannot carry
    # `GIT_CONFIG_GLOBAL`. Without this the developer's own `core.hooksPath` would decide where
    # these tests install a hook — outside `tmp_path`, in a directory they actually use.
    monkeypatch.setenv("HOME", str(tmp_path))
    # And `HOME` is not enough: the keep-list cannot carry `GIT_CONFIG_SYSTEM` either, so a
    # `core.hooksPath` in `/etc/gitconfig` still points every `install`/`uninstall` below at a
    # real directory, where a mid-test failure leaves the developer's own hook renamed. Skip
    # rather than install: this module's writes are the only ones on this branch that could
    # reach outside `tmp_path`.
    probe = tmp_path / "probe"
    probe.mkdir()
    git(tmp_path, probe, "init", "-q")
    if tmp_path not in hooks_dir(probe).parents:
        pytest.skip("a system-wide core.hooksPath points these tests outside tmp_path")


def launching(tmp_path: Path) -> dict[str, str]:
    """What this module layers on `tests/gitfixture.py`'s sealed environment.

    A `stayfixed` shim leading `PATH`, so the hook's first branch is the one exercised — the same
    branch a `uv tool install` user takes. The shim runs this checkout's package, and it has to
    be first because the `git commit` below runs the commit-msg hook this test just installed,
    and that hook is what invokes `stayfixed`. The suite's floor under the product's own `git`
    (`tests/floor.py`) is layered on too: git hands it on to the hook, and the hook to that
    `stayfixed`.
    """
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    shim = bin_dir / "stayfixed"
    if not shim.exists():
        shim.write_text(
            f'#!/bin/sh\nPYTHONPATH="{ROOT / "src"}" exec "{sys.executable}" -m stayfixed "$@"\n',
            encoding="utf-8",
        )
        shim.chmod(0o755)
    return {"PATH": f"{bin_dir}:{os.environ.get('PATH', '')}", **floor_env()}


def git(tmp_path: Path, root: Path, *args: str) -> str:
    """The shared fixture `git`, given this module's shim `PATH` and its `tmp_path` as `HOME`."""
    return gitfixture.git(root, *args, home=tmp_path, **launching(tmp_path))


def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    git(tmp_path, root, "init", "-q", "-b", "main")
    (root / "a.txt").write_text("a\n", encoding="utf-8")
    git(tmp_path, root, "add", "-A")
    git(tmp_path, root, "commit", "-q", "-m", "chore: seed")
    return root


def commit(tmp_path: Path, root: Path, message: str, *flags: str) -> str:
    (root / "a.txt").write_text(message + "\n", encoding="utf-8")
    git(tmp_path, root, "add", "-A")
    git(tmp_path, root, "commit", "-q", *flags, "-m", message)
    return git(tmp_path, root, "log", "-1", "--format=%B")


def committing(tmp_path: Path, root: Path, message: str) -> subprocess.CompletedProcess[str]:
    """Stage a change and commit it, returning the whole run so its streams can be read."""
    (root / "a.txt").write_text(message + "\n", encoding="utf-8")
    git(tmp_path, root, "add", "-A")
    # `run_git`: the hook under test is what rejects this commit, so the exit code is the
    # subject and not a failure.
    return gitfixture.run_git(
        root, "commit", "-q", "-m", message, home=tmp_path, **launching(tmp_path)
    )


TRAILER = "fix: thing\n\nCo-Authored-By: Claude <noreply@anthropic.com>"
# What the harness actually appends: a footer, a blank line, and a trailer. Two paragraphs.
CANONICAL_BLOCK = (
    "fix: thing\n"
    "\n"
    "\U0001f916 Generated with [Claude Code](https://claude.com/claude-code)\n"
    "\n"
    "Co-Authored-By: Claude <noreply@anthropic.com>"
)
CLEAN = "fix: thing"
FAILED_LINE = "stayfixed: commit strip failed"


def test_install_writes_an_executable_hook_carrying_the_marker(tmp_path: Path) -> None:
    root = repo(tmp_path)
    installed = install(root)
    assert installed.path == hooks_dir(root) / HOOK_NAME
    assert installed.preserved is None and installed.replaced is False
    assert os.access(installed.path, os.X_OK)
    assert HOOK_MARKER in installed.path.read_text(encoding="utf-8")


def test_the_hook_strips_a_trailer_before_the_commit_is_written(tmp_path: Path) -> None:
    root = repo(tmp_path)
    install(root)
    assert commit(tmp_path, root, TRAILER).strip() == "fix: thing"


def test_the_hook_leaves_nothing_for_the_range_check_to_find(tmp_path: Path) -> None:
    # The end-to-end half of the two-paragraph fix, across the seam the unit tests cannot see:
    # real repository, real installed hook, the canonical block, then the committed message
    # judged by the same function CI runs. This is the failure as it was reported — the hook
    # said `stripped 1 attribution line(s)` and `commit check` rejected the commit anyway — so
    # the two assertions are the hook's own claim and the gate's verdict, not one twice.
    root = repo(tmp_path)
    install(root)
    completed = committing(tmp_path, root, CANONICAL_BLOCK)
    assert completed.returncode == 0
    assert "stripped 2 attribution line(s)" in completed.stderr
    written = git(tmp_path, root, "log", "-1", "--format=%B")
    assert offending_lines(written) == []
    assert written.strip() == "fix: thing"


def test_the_hook_survives_no_verify(tmp_path: Path) -> None:
    # The reason it is prepare-commit-msg and not commit-msg.
    root = repo(tmp_path)
    install(root)
    assert commit(tmp_path, root, TRAILER, "--no-verify").strip() == "fix: thing"


def test_a_pre_existing_hook_is_preserved_and_still_runs(tmp_path: Path) -> None:
    root = repo(tmp_path)
    foreign = hooks_dir(root) / HOOK_NAME
    foreign.parent.mkdir(parents=True, exist_ok=True)
    foreign.write_text('#!/bin/sh\necho ran > "$(dirname "$0")/../foreign-ran"\n', encoding="utf-8")
    foreign.chmod(0o755)
    installed = install(root)
    assert installed.preserved == foreign.with_name(HOOK_NAME + ".local")
    commit(tmp_path, root, TRAILER)
    assert (hooks_dir(root).parent / "foreign-ran").read_text(encoding="utf-8").strip() == "ran"


def test_a_hook_the_developer_switched_off_stays_off(tmp_path: Path) -> None:
    # `chmod -x` is the standard way to disable a hook; preserving it must not re-enable it.
    root = repo(tmp_path)
    foreign = hooks_dir(root) / HOOK_NAME
    foreign.parent.mkdir(parents=True, exist_ok=True)
    foreign.write_text('#!/bin/sh\necho ran > "$(dirname "$0")/../foreign-ran"\n', encoding="utf-8")
    foreign.chmod(0o644)
    install(root)
    commit(tmp_path, root, TRAILER)
    assert not (hooks_dir(root).parent / "foreign-ran").exists()


def test_a_stray_local_hook_is_refused_even_with_no_hook_at_the_name(tmp_path: Path) -> None:
    # The chain `exec`s `$0.local`; a file this installer never preserved must not be run
    # under stayfixed's name, so the refusal cannot live inside the preserve branch alone.
    root = repo(tmp_path)
    directory = hooks_dir(root)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / (HOOK_NAME + ".local")).write_text("#!/bin/sh\n", encoding="utf-8")
    with pytest.raises(Refusal):
        install(root)


def test_the_hook_says_what_it_stripped(tmp_path: Path) -> None:
    # The source hook sent the count to `/dev/null`; a rewritten message nobody is told about
    # is a silent edit of the author's text, which the strip must never be. Behaviour 1 of the
    # four the hook body owes.
    root = repo(tmp_path)
    install(root)
    completed = committing(tmp_path, root, TRAILER)
    assert completed.returncode == 0
    assert "stripped 1 attribution line(s)" in completed.stderr


def test_the_hook_says_nothing_when_there_was_nothing_to_strip(tmp_path: Path) -> None:
    # Behaviour 2, and the one the ported body got wrong: `grep -v` exits 1 when it selects no
    # lines, which is exactly the quiet case, so a `|| echo "$failed"` after it printed a
    # failure line on every clean commit. The quiet outcome is worth no line at all.
    root = repo(tmp_path)
    install(root)
    completed = committing(tmp_path, root, CLEAN)
    assert completed.returncode == 0
    assert completed.stderr == ""
    assert git(tmp_path, root, "log", "-1", "--format=%B").strip() == CLEAN


def test_the_hook_reports_a_failed_strip_and_still_lets_the_commit_through(
    tmp_path: Path,
) -> None:
    # Behaviours 3 and 4: the failure line belongs to `commit strip` exiting non-zero and to
    # nothing else, and no outcome of it may cost the developer their commit. The shim `env`
    # would write is pre-empted here by one that fails, which is the only way to reach that
    # branch without a genuinely broken `stayfixed`.
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    shim = bin_dir / "stayfixed"
    shim.write_text("#!/bin/sh\necho 'stayfixed: refused' >&2\nexit 2\n", encoding="utf-8")
    shim.chmod(0o755)
    root = repo(tmp_path)
    install(root)
    completed = committing(tmp_path, root, TRAILER)
    assert completed.returncode == 0
    assert FAILED_LINE in completed.stderr
    assert git(tmp_path, root, "log", "-1", "--format=%B").strip() == TRAILER


def test_a_directory_at_the_hook_name_is_refused(tmp_path: Path) -> None:
    root = repo(tmp_path)
    (hooks_dir(root) / HOOK_NAME).mkdir(parents=True)
    with pytest.raises(Refusal):
        install(root)


def test_install_is_idempotent_over_its_own_hook(tmp_path: Path) -> None:
    root = repo(tmp_path)
    install(root)
    again = install(root)
    assert again.replaced is True and again.preserved is None
    assert not again.path.with_name(HOOK_NAME + ".local").exists()


def test_a_hook_an_earlier_release_wrote_is_still_ours(tmp_path: Path) -> None:
    # The hook's text changes between releases, and every repository keeps the bytes the release
    # that installed it wrote. The marker line, not the text, is what makes a hook stayfixed's:
    # an install over an earlier text rewrites it in place rather than preserving it as a
    # stranger's `.local` and chaining to it, and an uninstall removes it rather than leaving it
    # orphaned. The earlier text is frozen in a file, `HOOK_TEXT` as the v0.2.0 tag evaluates it,
    # and never rebuilt from today's module: a hook built from today's text carries today's marker,
    # so a changed marker, which would orphan every hook 0.2.0 installed, would pass unseen.
    # Mutation (declared): a hook is ours only when its bytes equal today's text -> this reddens.
    # Mutation (declared): the marker line changes -> this reddens.
    from stayfixed.guards.githooks import HOOK_TEXT

    old_text = RELEASED_0_2_0.read_text(encoding="utf-8")
    assert old_text != HOOK_TEXT
    root = repo(tmp_path)
    hook = hooks_dir(root) / HOOK_NAME
    hook.parent.mkdir(parents=True, exist_ok=True)
    hook.write_text(old_text, encoding="utf-8")
    hook.chmod(0o755)

    again = install(root)
    assert again.replaced is True and again.preserved is None
    assert hook.read_text(encoding="utf-8") == HOOK_TEXT
    assert not hook.with_name(HOOK_NAME + ".local").exists()

    hook.write_text(old_text, encoding="utf-8")
    removed = uninstall(root)
    assert removed.restored is None
    assert not hook.exists()


def test_install_refuses_to_overwrite_a_stale_local_hook(tmp_path: Path) -> None:
    # Two foreign hooks cannot both be preserved under one name; refusing beats losing one.
    root = repo(tmp_path)
    directory = hooks_dir(root)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / (HOOK_NAME + ".local")).write_text("#!/bin/sh\n", encoding="utf-8")
    (directory / HOOK_NAME).write_text("#!/bin/sh\n", encoding="utf-8")
    with pytest.raises(Refusal):
        install(root)


def test_install_refuses_a_symlinked_destination(tmp_path: Path) -> None:
    root = repo(tmp_path)
    directory = hooks_dir(root)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / HOOK_NAME).symlink_to(tmp_path / "elsewhere")
    with pytest.raises(Refusal):
        install(root)


def test_uninstall_restores_the_preserved_hook(tmp_path: Path) -> None:
    root = repo(tmp_path)
    foreign = hooks_dir(root) / HOOK_NAME
    foreign.parent.mkdir(parents=True, exist_ok=True)
    foreign.write_text("#!/bin/sh\necho foreign\n", encoding="utf-8")
    install(root)
    removed = uninstall(root)
    assert removed.restored == foreign
    assert "foreign" in foreign.read_text(encoding="utf-8")
    assert not foreign.with_name(HOOK_NAME + ".local").exists()


def test_uninstall_promotes_whatever_sits_at_local_even_a_stranger(tmp_path: Path) -> None:
    # The recorded decision, not an accident. `install` refuses a stray `.local` only while our
    # hook is absent, so one dropped beside an installed hook is checked by nothing — and the
    # installed hook has been `exec`ing it on every commit since, which is the larger fact.
    # `uninstall` restores it rather than pretending it can tell it from one install preserved.
    # Changing that is `setup`'s call, not this module's; this pins today's answer so
    # a change to it is a decision somebody makes rather than a diff nobody notices.
    root = repo(tmp_path)
    installed = install(root)
    stranger = installed.path.with_name(HOOK_NAME + ".local")
    stranger.write_text("#!/bin/sh\necho stranger\n", encoding="utf-8")
    removed = uninstall(root)
    assert removed.restored == installed.path
    assert "stranger" in installed.path.read_text(encoding="utf-8")
    assert not stranger.exists()


def test_reinstalling_over_a_chained_setup_keeps_the_preserved_hook(tmp_path: Path) -> None:
    # The ordinary upgrade path for anyone who had a hook before: our hook plus the `.local` we
    # made. A regression that moved the `replaced` test below the stray-`.local` guard would
    # refuse every re-install for exactly those users, and no other test here has both files
    # present at once.
    root = repo(tmp_path)
    foreign = hooks_dir(root) / HOOK_NAME
    foreign.parent.mkdir(parents=True, exist_ok=True)
    foreign.write_text("#!/bin/sh\necho foreign\n", encoding="utf-8")
    foreign.chmod(0o755)
    install(root)
    again = install(root)
    assert again.replaced is True and again.preserved is None
    local = foreign.with_name(HOOK_NAME + ".local")
    assert "foreign" in local.read_text(encoding="utf-8")
    removed = uninstall(root)
    assert removed.restored == foreign
    assert "foreign" in foreign.read_text(encoding="utf-8")


def test_uninstall_leaves_a_hook_it_did_not_write(tmp_path: Path) -> None:
    # And says so, `Found.FOREIGN`, where the answer was the one an uninstall of stayfixed's own
    # hook with nothing chained gave; with no hook at all, `Found.ABSENT`. Mutations:
    # `mutations/`'s "uninstall says it removed a hook when the hook there is not stayfixed's" and
    # "uninstall says it removed a hook when there was none".
    root = repo(tmp_path)
    foreign = hooks_dir(root) / HOOK_NAME
    foreign.parent.mkdir(parents=True, exist_ok=True)
    assert uninstall(root) == (foreign, None, Found.ABSENT)
    foreign.write_text("#!/bin/sh\necho foreign\n", encoding="utf-8")
    removed = uninstall(root)
    assert removed == (foreign, None, Found.FOREIGN)
    assert "foreign" in foreign.read_text(encoding="utf-8")


def _in_a_child(probe: str, root: Path, verb: str) -> str:
    """What `probe` prints, run over `root` in a child under a timeout: a hook path that is a FIFO
    hangs a reader that opens it, and a hang here fails the case rather than the worker."""
    try:
        done = subprocess.run(
            [sys.executable, "-c", probe, str(root)],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except subprocess.TimeoutExpired:
        pytest.fail(f"{verb} waited on the hook path")
    assert done.returncode == 0, done.stderr
    return done.stdout


def test_a_fifo_at_the_hook_path_is_refused_by_install_and_never_waited_on(tmp_path: Path) -> None:
    # Whether a hook is stayfixed's is read off its bytes, and the read waited on a FIFO for a
    # writer that never came: `setup --git-hooks` and `--uninstall` both hung. It is read as a
    # regular file only, to the read cap, so a FIFO is a hook `install` cannot read, and it can
    # neither chain one nor write over it: refused. (`uninstall` leaves it as foreign, below.)
    # Mutation: `mutations/`'s "the hook installer reads a hook with no bound".
    root = repo(tmp_path)
    hook = hooks_dir(root) / HOOK_NAME
    hook.parent.mkdir(parents=True, exist_ok=True)
    os.mkfifo(hook)
    probe = (
        "import sys\n"
        "from pathlib import Path\n"
        "from stayfixed.errors import Refusal\n"
        "from stayfixed.guards.githooks import install\n"
        "try:\n"
        "    install(Path(sys.argv[1]))\n"
        "except Refusal as refused:\n"
        "    print(refused)\n"
    )
    said = _in_a_child(probe, root, "install")
    assert said.startswith(f"{hook} could not be read (not a regular file); "), said
    assert hook.is_fifo()


@pytest.mark.parametrize("shape", ["fifo", "directory"])
def test_uninstall_leaves_a_fifo_or_a_directory_at_the_hook_path_as_a_foreign_hook(
    tmp_path: Path, shape: str
) -> None:
    # stayfixed writes only a regular file at the hook path, so anything else there is as surely
    # not its own as a regular file past the read cap: `--uninstall` leaves it in place and says
    # it is not stayfixed's, where it refused it as a hook it could not read. A FIFO is never
    # opened, and so never waited on; a regression to a plain open would wait for a writer, so
    # this runs in a child under a timeout as its `install` sibling does. Mutation:
    # `mutations/`'s "uninstall reads a hook that is not a regular file".
    root = repo(tmp_path)
    hook = hooks_dir(root) / HOOK_NAME
    hook.parent.mkdir(parents=True, exist_ok=True)
    if shape == "fifo":
        os.mkfifo(hook)
    else:
        hook.mkdir()
    probe = (
        "import sys\n"
        "from pathlib import Path\n"
        "from stayfixed.guards.githooks import uninstall\n"
        "path, restored, found = uninstall(Path(sys.argv[1]))\n"
        "print(path, restored, found.name, sep='\\n')\n"
    )
    said = _in_a_child(probe, root, "uninstall")
    assert said.splitlines() == [str(hook), "None", Found.FOREIGN.name]
    assert hook.is_fifo() if shape == "fifo" else hook.is_dir()


@pytest.mark.parametrize("verb", ["install", "uninstall"])
def test_a_hook_that_cannot_be_read_is_neither_ours_nor_foreign(tmp_path: Path, verb: str) -> None:
    # Whether it is stayfixed's cannot be told, so it is neither: read as foreign, `--uninstall`
    # said "it is not stayfixed's hook" of stayfixed's own hook at mode 000, and `install`
    # renamed that hook to `.local` and chained it. Each refuses, naming the reason, and leaves it
    # where it is. Mutation: `mutations/`'s "a hook that cannot be read is read as a foreign one".
    if os.geteuid() == 0:
        pytest.skip("root reads everything")
    root = repo(tmp_path)
    hook = install(root).path
    hook.chmod(0o000)
    try:
        with pytest.raises(Refusal) as refused:
            install(root) if verb == "install" else uninstall(root)
    finally:
        hook.chmod(0o755)
    assert str(refused.value).startswith(f"{hook} could not be read (Permission denied); ")
    assert HOOK_MARKER in hook.read_text(encoding="utf-8")
    assert not hook.with_name(HOOK_NAME + ".local").exists()


def test_a_hook_past_the_read_cap_is_a_foreign_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # stayfixed's own hook is a couple of kilobytes, so a regular file longer than the read cap
    # is certainly not it: it is foreign, chained by `install` and left alone by `--uninstall`,
    # as 0.2.0 did, rather than refused as a hook that cannot be read. The cap is lowered to
    # just past stayfixed's own hook, which is still read whole. Mutation: `mutations/`'s "a hook
    # past the read cap is refused as one that cannot be read".
    from stayfixed import fsops
    from stayfixed.guards.githooks import HOOK_TEXT

    limit = len(HOOK_TEXT.encode("utf-8")) + 16
    monkeypatch.setattr(fsops, "REGULAR_READ_LIMIT", limit)
    root = repo(tmp_path)
    hook = hooks_dir(root) / HOOK_NAME
    hook.parent.mkdir(parents=True, exist_ok=True)
    foreign = "#!/bin/sh\necho foreign\n" + "#" * limit + "\n"
    hook.write_text(foreign, encoding="utf-8")
    assert uninstall(root) == (hook, None, Found.FOREIGN)
    installed = install(root)
    local = hook.with_name(HOOK_NAME + ".local")
    assert (installed.replaced, installed.preserved) == (False, local)
    assert local.read_text(encoding="utf-8") == foreign
    assert uninstall(root) == (hook, hook, Found.REMOVED)
    assert hook.read_text(encoding="utf-8") == foreign


def test_hooks_dir_honours_core_hooks_path(tmp_path: Path) -> None:
    # `git rev-parse --git-path hooks` rather than `<common-dir>/hooks` computed by hand,
    # which is a directory git never reads when husky has pointed core.hooksPath elsewhere.
    root = repo(tmp_path)
    git(tmp_path, root, "config", "core.hooksPath", ".husky")
    assert hooks_dir(root) == root / ".husky"


def test_install_creates_a_hooks_directory_core_hooks_path_only_names(tmp_path: Path) -> None:
    # The enumerated write that is easy to miss: `core.hooksPath` may name a directory
    # nobody has made yet — husky's `.husky/` before `husky install` — and `write_atomically`'s
    # `parent.mkdir(parents=True)` is what makes the hook land there rather than raise.
    root = repo(tmp_path)
    git(tmp_path, root, "config", "core.hooksPath", ".husky")
    assert not (root / ".husky").exists()
    installed = install(root)
    assert installed.path == root / ".husky" / HOOK_NAME
    assert os.access(installed.path, os.X_OK)
    assert commit(tmp_path, root, TRAILER).strip() == "fix: thing"


def test_hooks_dir_refuses_where_git_cannot_answer(tmp_path: Path) -> None:
    # The `Refusal` arm: outside a repository `rev-parse` exits non-zero, and a caller that
    # read the empty answer as a path would install a hook into a directory of its own making.
    with pytest.raises(Refusal) as raised:
        hooks_dir(tmp_path / "not-a-repo")
    # And the refusal says so in this module's own words. `rev-parse`'s stderr is
    # repository-authored — here `fatal: not a git repository …`, and for a `core.hooksPath` git
    # dislikes it quotes the config VALUE — so piping it into the message puts bytes a repository
    # chose in front of a person. `commit.commits_in` carries the same reasoning and was fixed
    # first; this one was not, and the assertion is what makes that visible.
    message = str(raised.value)
    assert "not a git repository" not in message
    assert "fatal" not in message
    assert str(tmp_path / "not-a-repo") in message


def test_a_hooks_dir_that_times_out_refuses_without_rendering_the_argv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The other arm, and the one no repository fixture can reach. `TimeoutExpired.__str__`
    # renders the whole command — `Command '['git', '-C', '/…', 'rev-parse', …]' timed out` —
    # so `f"…: {exc}"` published the argv, which carries `root` twice over and whatever a later
    # caller puts in it. The same is true of `OSError`.
    import subprocess as sp

    def explode(*args: object, **kwargs: object) -> object:
        raise sp.TimeoutExpired(["git", "-C", "/SECRET", "rev-parse"], 5)

    monkeypatch.setattr(sp, "run", explode)
    with pytest.raises(Refusal) as raised:
        hooks_dir(tmp_path)
    assert "SECRET" not in str(raised.value)
    assert "rev-parse" not in str(raised.value)


def test_a_worktree_shares_the_main_checkouts_hook(tmp_path: Path) -> None:
    # And its chain. `$0.local` is a sibling of the path git ran, which in a linked worktree is
    # the common directory's — the reason the chain is spelled that way rather than computed
    # from `--git-common-dir`, and the half a strip-only assertion would leave unmeasured.
    root = repo(tmp_path)
    foreign = hooks_dir(root) / HOOK_NAME
    foreign.parent.mkdir(parents=True, exist_ok=True)
    foreign.write_text('#!/bin/sh\necho ran > "$(dirname "$0")/../foreign-ran"\n', encoding="utf-8")
    foreign.chmod(0o755)
    install(root)
    worktree = tmp_path / "wt"
    git(tmp_path, root, "worktree", "add", "-q", str(worktree), "-b", "wp")
    assert commit(tmp_path, worktree, TRAILER).strip() == "fix: thing"
    assert (hooks_dir(root).parent / "foreign-ran").read_text(encoding="utf-8").strip() == "ran"


def test_the_hook_text_carries_the_marker_the_installer_looks_for() -> None:
    # No mutation of its own: this reads its expectation from the module it tests, so it
    # survives any edit to the marker by construction. It is here as the mutation guard for
    # `install`'s `_ours` check — the marker the installer greps for and the one the hook
    # carries are the same string, and this is what says so.
    from stayfixed.guards.githooks import HOOK_TEXT

    assert HOOK_TEXT.splitlines()[1] == HOOK_MARKER
