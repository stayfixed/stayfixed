from __future__ import annotations

import json
import os
import pty
import re
import shutil
import stat
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import NamedTuple

import pytest

from stayfixed import __version__
from stayfixed.gitenv import GIT_CANDIDATES, HOOK_WRAPPER_LAUNCHED, HOOK_WRAPPER_VARIABLE
from tests.gitfixture import git
from tests.ownerhome import pin_git_home, plugin_root_with_owner_home, stayfixed_argv
from tests.test_launcher import _old_python

ROOT = Path(__file__).resolve().parents[2]
WRAPPER = ROOT / "hooks" / "run-hook.sh"


def _plugin_root(
    base: Path,
    exit_code: int,
    *,
    echo_cwd: bool = False,
    with_launcher: bool = True,
    git_candidates: str | None = None,
    id_candidates: str | None = None,
    prints: str | None = None,
    looks_up_git_home: bool = False,
) -> Path:
    """A plugin root: a copy of the shipped wrapper, and a launcher beside it.

    The wrapper is **copied in** rather than invoked out of the checkout, because it now finds
    its launcher relative to its own path. A plugin root is therefore a real directory pair —
    `hooks/run-hook.sh` and `scripts/stayfixed` — which is what an installed plugin is, and what
    the harness substitutes into the command string of `hooks/hooks.json`.

    A fake launcher, not the real one: this test is about the wrapper's own exit-code mapping
    and its argv contract, and a real `stayfixed` run would couple it to every command in the
    package.

    Python and not `#!/bin/sh`, because the wrapper hands the launcher to the interpreter it
    probed — `"$p" "$launcher"` — rather than executing it by its shebang, which is the whole
    reason the probe exists: a launcher run by its own `#!/usr/bin/env python3` would be given
    whatever `python3` the session's PATH resolves to, which on macOS is 3.9. A shell script
    here therefore reaches Python as a `SyntaxError` and every exit code below arrives as 1.

    The wrapper's own `git` reads this test's `HOME` (`tests/ownerhome.py`, `pin_git_home`) unless
    `looks_up_git_home` keeps the lookup it ships, for a test of that lookup.
    """
    root = base / "plugin"
    (root / "scripts").mkdir(parents=True)
    (root / "hooks").mkdir(parents=True)
    shutil.copy(WRAPPER, root / "hooks" / WRAPPER.name)
    if not looks_up_git_home:
        pin_git_home(root / "hooks" / WRAPPER.name, Path(os.environ["HOME"]))
    if git_candidates is not None:
        # The one thing a test may rewrite, and only because it cannot be reached any other way:
        # the git candidate list is deliberately not environment-settable — that is the whole of
        # the change it belongs to — so the "no git at any absolute path" arm has no seam but
        # this. Only the list is rewritten; every guard around it is the shipped one.
        copied = root / "hooks" / WRAPPER.name
        lines = copied.read_text(encoding="utf-8").splitlines(keepends=True)
        first = next(i for i, line in enumerate(lines) if line.startswith("for g in /"))
        # The list is spelled across two physical lines with a trailing backslash, so the
        # continuation goes with it; anything else would leave half a list behind.
        last = first
        while lines[last].rstrip("\n").endswith("\\"):
            last += 1
        lines[first : last + 1] = [f"for g in {git_candidates}; do\n"]
        copied.write_text("".join(lines), encoding="utf-8")
    if id_candidates is not None:
        # The `id` list has the git list's reason: it is not environment-settable either, and no
        # test can put a program at `/usr/bin/id` or take one away.
        copied = root / "hooks" / WRAPPER.name
        text = copied.read_text(encoding="utf-8")
        shipped = "for i in /usr/bin/id /bin/id /run/current-system/sw/bin/id; do\n"
        assert text.count(shipped) == 1, (
            "the wrapper's id list is no longer spelled as this expects"
        )
        copied.write_text(
            text.replace(shipped, f"for i in {id_candidates}; do\n"), encoding="utf-8"
        )
    (root / "hooks" / WRAPPER.name).chmod(0o755)
    if not with_launcher:
        return root
    launcher = root / "scripts" / "stayfixed"
    # `os.getcwd()` rather than the shell's `pwd`: it reports the physical directory, which is
    # what `Path.resolve()` names, so the assertion is about the directory and not about which
    # of its spellings the shell kept.
    body = "import os\n\nprint(os.getcwd())\n" if echo_cwd else ""
    # `prints` is an expression the launcher prints instead, with `os` imported.
    if prints is not None:
        body = f"import os\n\nprint({prints})\n"
    launcher.write_text(
        f"#!/usr/bin/env python3\n{body}raise SystemExit({exit_code})\n", encoding="utf-8"
    )
    launcher.chmod(0o755)
    return root


def _env(plugin_root: Path, env_root: Path | None, candidates: str | None) -> dict[str, str]:
    env = dict(os.environ)
    env.pop("CLAUDE_PLUGIN_ROOT", None)
    env.pop("CLAUDE_PROJECT_DIR", None)
    env.pop("STAYFIXED_PYTHON_CANDIDATES", None)
    env.pop(HOOK_WRAPPER_VARIABLE, None)
    if env_root is not None:
        env["CLAUDE_PLUGIN_ROOT"] = str(env_root)
    if candidates is not None:
        env["STAYFIXED_PYTHON_CANDIDATES"] = candidates
    return env


def _run(
    *argv: str,
    plugin_root: Path,
    env_root: Path | None = None,
    candidates: str | None = None,
    cwd: Path | None = None,
    project: Path | None = None,
    path: str | None = None,
    extra: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run the wrapper **inside** `plugin_root`, the way an installed plugin's entry does.

    `CLAUDE_PLUGIN_ROOT` is removed from the environment unless `env_root` names one, and
    `env_root` is deliberately a *different* root: nothing below may change because of it.

    **`cwd` defaults to `plugin_root`, which is under `tmp_path` and is not a repository.** It
    used to inherit pytest's own, which is this checkout — so the wrapper's `git rev-parse`
    named *stayfixed's own tree* as the project root, and `sys.executable` under `uv run` is
    `<checkout>/.venv/bin/python3`, inside it. Every case passing `candidates=sys.executable`
    was therefore one edit away from being about the interpreter containment instead of what it
    says it is about. The same hermeticity `tests/doctor/test_checks.py::_env` enforces, for the
    same reason: a case must not read the machine it happens to run on.

    **`candidates` arrives over a pty, because the wrapper honours that variable only from an
    interactive terminal.** It names the *program* the wrapper executes, so it is gated as
    `attach` gates `--machine`, to a person at a terminal — and a hook's stdin is the harness's JSON
    payload on a pipe, never a terminal. Every case below that passes one is therefore about
    the probe itself and says nothing about what an `env` block can reach;
    `test_an_interpreter_the_environment_names_is_ignored_off_a_terminal` is that case, and it
    drives both sides of the same gate.
    """
    env = _env(plugin_root, env_root, candidates)
    if project is not None:
        env["CLAUDE_PROJECT_DIR"] = str(project)
    if path is not None:
        env["PATH"] = path
    env.update(extra or {})
    master, slave = pty.openpty() if candidates is not None else (-1, -1)
    try:
        return subprocess.run(
            [str(plugin_root / "hooks" / WRAPPER.name), *argv],
            capture_output=True,
            text=True,
            check=False,
            env=env,
            cwd=str(cwd if cwd is not None else plugin_root),
            stdin=slave if candidates is not None else subprocess.DEVNULL,
        )
    finally:
        for descriptor in (master, slave):
            if descriptor >= 0:
                os.close(descriptor)


def test_no_policy_argument_refuses_with_a_token(tmp_path: Path) -> None:
    # The one failure the wrapper can cause itself. `set -u` alone exits 1 with the shell's own
    # message and no token, which Claude Code reads as a non-blocking error — permission. An
    # entry that loses its first argument must disarm loudly or not at all.
    result = _run(plugin_root=_plugin_root(tmp_path, 0))
    assert result.returncode == 2
    assert "SF_ARGV" in result.stderr


@pytest.mark.parametrize(("policy", "code"), [("closed", 2), ("open", 0)])
def test_no_interpreter_of_the_floor_version_refuses_under_closed_only(
    tmp_path: Path, policy: str, code: int
) -> None:
    # The "no interpreter" row of the fail-closed matrix in the spike record
    # (`docs/plans/2026-09-05-agent-harness-p0-spikes.md`): the wrapper must decide this itself.
    # Every Python-side fallback is unreachable here by construction — there is no interpreter
    # to run it.
    result = _run(
        policy,
        "hook",
        "PreToolUse",
        plugin_root=_plugin_root(tmp_path, 0),
        candidates="/nonexistent/python3",
    )
    assert result.returncode == code
    assert "SF_NO_PY" in result.stderr


def test_an_interpreter_below_the_floor_is_rejected(tmp_path: Path) -> None:
    # The fail-closed matrix's "only 3.9 available" row, with a real sub-floor interpreter rather
    # than a fake that exits non-zero for every argument. A fake cannot exercise
    # `sys.version_info >= (3, 11)` at all: mutate the predicate to `True` and the fake still
    # refuses, so the row would duplicate the one above and prove nothing. `_old_python` is the
    # tree's own seam for this, and CI pins it through STAYFIXED_OLD_PYTHON so the row runs there
    # rather than skipping everywhere.
    old = _old_python()
    if old is None:
        pytest.skip("no interpreter below 3.11 on this machine; set STAYFIXED_OLD_PYTHON")
    result = _run(
        "closed",
        "hook",
        "PreToolUse",
        plugin_root=_plugin_root(tmp_path, 0),
        candidates=old,
    )
    assert result.returncode == 2
    assert "SF_NO_PY" in result.stderr


def test_an_interpreter_at_the_floor_is_accepted(tmp_path: Path) -> None:
    # The positive row the suite lacks. Without it every interpreter assertion is a refusal,
    # and a probe that rejected *everything* would pass all of them.
    result = _run(
        "closed",
        "hook",
        "PreToolUse",
        plugin_root=_plugin_root(tmp_path, 0),
        candidates=sys.executable,
    )
    assert result.returncode == 0
    assert "SF_NO_PY" not in result.stderr


def test_a_plugin_root_in_the_environment_does_not_choose_the_launcher(tmp_path: Path) -> None:
    # Replaces the fail-closed matrix's "`CLAUDE_PLUGIN_ROOT` unset" row, whose premise was that
    # the environment names the launcher. It does not: the harness substitutes the plugin root
    # into the *command string* of `hooks/hooks.json`, so the wrapper that runs is always the
    # plugin's own, and the program it hands to Python is derived from that wrapper's path. A
    # variable of the same name arriving from anywhere else — a committed `.claude/settings.json`
    # `env` block is the case `config/machine.py` reads no `STAYFIXED_CONFIG` for — must change
    # nothing, because this choice is made before any stayfixed guard runs.
    #
    # The two roots are told apart by their exit codes, not by a message: `theirs` exits 3,
    # which under `closed` policy becomes a SF_RC refusal and exit 2.
    ours = _plugin_root(tmp_path / "ours", 0)
    theirs = _plugin_root(tmp_path / "theirs", 3)
    result = _run("closed", "hook", "PreToolUse", plugin_root=ours, env_root=theirs)
    assert result.returncode == 0
    assert "SF_RC" not in result.stderr


def _planted_interpreter(tmp_path: Path) -> tuple[Path, Path]:
    """An `evil-python` of the shape a repository can commit, and the file it writes when run.

    The probe asks a candidate only to exit 0 for a trivial `-I -c`, so this is the whole cost of
    passing it: three lines and an executable bit. It answers the probe's exact spelling, so a
    probe that stopped passing `-I` would find this fake running its payload instead.
    """
    ran = tmp_path / "planted-interpreter-ran"
    planted = tmp_path / "evil-python"
    planted.write_text(
        f'#!/bin/sh\ncase "$1 $2" in\n  "-I -c") exit 0 ;;\nesac\necho "$*" > "{ran}"\nexit 0\n',
        encoding="utf-8",
    )
    planted.chmod(0o755)
    return planted, ran


def test_an_interpreter_the_environment_names_is_ignored_off_a_terminal(tmp_path: Path) -> None:
    # Off a terminal, the environment does not choose the interpreter — the half
    # `test_a_plugin_root_in_the_environment_does_not_choose_the_launcher` left open one line
    # below itself: closing *which file* the wrapper hands Python, while the environment still
    # chose *which Python*, is the same class of hole with a different name.
    # Measured on the shipped wrapper: with the `env`-block equivalent of
    # STAYFIXED_PYTHON_CANDIDATES=<repo>/evil-python, the wrapper ran
    # `<repo>/evil-python <plugin>/scripts/stayfixed hook PreToolUse` and exited 0 — arbitrary
    # code on every PreToolUse, before any stayfixed guard. `config/machine.py`'s ruling is the
    # one followed here: "Gating one of a pair of equivalent inputs is not a partial defence, it
    # is a redirect with a longer name", so the gate is that module's own — an interactive
    # terminal — and a hook's stdin is the harness's payload on a pipe.
    planted, ran = _planted_interpreter(tmp_path)
    root = _plugin_root(tmp_path, 0, echo_cwd=True)
    result = subprocess.run(
        [str(root / "hooks" / WRAPPER.name), "closed", "hook", "PreToolUse"],
        capture_output=True,
        text=True,
        check=False,
        env=_env(root, None, str(planted)),
        stdin=subprocess.DEVNULL,
        cwd=str(tmp_path),
    )
    assert not ran.exists(), "the planted interpreter chose the program the wrapper ran"
    # Non-vacuous twice over: a real interpreter did run the launcher (it printed its cwd), and
    # the same list IS honoured over a terminal, so the gate is a gate and not a deletion — a
    # machine owner debugging the probe by hand keeps their override.
    assert result.returncode == 0 and result.stdout.strip()
    _run("closed", "hook", "PreToolUse", plugin_root=root, candidates=str(planted))
    assert ran.exists()


def _clone_shipping_an_interpreter(tmp_path: Path) -> tuple[Path, Path, Path]:
    """A checkout that commits its own `python3`, and the file it writes if anything runs it.

    This is the whole of what a hostile clone has to stage for the `PATH` arm: one executable in
    its own tree, and a `PATH` entry naming that tree in a committed `env` block.
    """
    clone = tmp_path / "clone"
    clone.mkdir()
    ran = tmp_path / "shipped-interpreter-ran"
    shipped = clone / "python3"
    shipped.write_text(
        f'#!/bin/sh\ncase "$1 $2" in\n  "-I -c") exit 0 ;;\nesac\necho "$*" > "{ran}"\nexit 0\n',
        encoding="utf-8",
    )
    shipped.chmod(0o755)
    return clone, shipped, ran


def test_an_interpreter_inside_the_project_root_is_never_used(tmp_path: Path) -> None:
    # Gating `STAYFIXED_PYTHON_CANDIDATES` on a terminal moved the program chooser from one
    # variable to another: the hook path then always uses the built-in list, whose last entry is
    # a `PATH` lookup, and `PATH` reaches this process from the same committed `env` block. The
    # entry is not droppable -- it is the fall-through the fail-closed matrix's "only 3.9 available"
    # row measured, and a pyenv, nix or asdf machine has no interpreter at any of the four absolute
    # paths -- so what is refused is the narrower thing a clone can actually stage: a candidate
    # resolving inside its own tree.
    #
    # The containment is asked BEFORE the version probe, because that probe is itself an
    # execution: `"$c" -c ...` runs the candidate, and a check made afterwards would be made on
    # a program that had already run.
    clone, shipped, ran = _clone_shipping_an_interpreter(tmp_path)
    root = _plugin_root(tmp_path, 0, echo_cwd=True)
    result = _run(
        "closed",
        "hook",
        "PreToolUse",
        plugin_root=root,
        project=clone,
        candidates=f"{shipped} {sys.executable}",
    )
    assert not ran.exists(), "the tree's own interpreter was executed"
    # Non-vacuous: one candidate is dropped and the probe goes on, so a real interpreter still
    # answers and the launcher still runs in the project.
    assert result.returncode == 0
    assert result.stdout.strip() == str(clone.resolve())
    # With nothing outside the tree to fall back to it is a refusal carrying a token -- the cost
    # the ruling accepts for a genuinely vendored in-tree toolchain, and `doctor`'s wrapper row
    # names it rather than the hook silently running the tree's own program.
    only = _run(
        "closed", "hook", "PreToolUse", plugin_root=root, project=clone, candidates=str(shipped)
    )
    assert only.returncode == 2
    assert "SF_NO_PY" in only.stderr
    assert not ran.exists()


# Every spelling a `PATH` entry can take that `command -v` turns into a path inside the tree.
# The candidate string is `python3` throughout, because the resolution is the subject: on the
# machine this is about, the built-in list has already fallen through to exactly that entry.
_PATH_SPELLINGS = (
    "a PATH entry naming the tree",
    "a . in PATH",
    "a .. spelling of the tree",
    "a symlinked PATH entry",
    "a symlinked project root",
)


@pytest.mark.parametrize("spelling", _PATH_SPELLINGS)
def test_an_interpreter_reached_through_path_is_judged_by_its_resolved_path(
    tmp_path: Path, spelling: str
) -> None:
    # Both sides are resolved before they are compared, and each of these is a way past a
    # comparison that resolved neither or only one. The last two are why `project` is `pwd -P`
    # and not `$CLAUDE_PROJECT_DIR`: one spelling on one side and another on the other reads as
    # "outside" for every candidate in the tree.
    clone, _, ran = _clone_shipping_an_interpreter(tmp_path)
    linked_bin = tmp_path / "linked-bin"
    linked_bin.symlink_to(clone)
    linked_root = tmp_path / "linked-root"
    linked_root.symlink_to(clone)
    rest = "/usr/bin:/bin"
    path, project = {
        _PATH_SPELLINGS[0]: (f"{clone}:{rest}", clone),
        _PATH_SPELLINGS[1]: (f".:{rest}", clone),
        _PATH_SPELLINGS[2]: (f"{clone.parent}/{clone.name}/../{clone.name}:{rest}", clone),
        _PATH_SPELLINGS[3]: (f"{linked_bin}:{rest}", clone),
        _PATH_SPELLINGS[4]: (f"{clone}:{rest}", linked_root),
    }[spelling]
    result = _run(
        "closed",
        "hook",
        "PreToolUse",
        plugin_root=_plugin_root(tmp_path, 0),
        candidates="python3",
        project=project,
        path=path,
        cwd=clone,
    )
    assert not ran.exists(), f"the tree's own interpreter ran, reached through {spelling}"
    assert result.returncode == 2
    assert "SF_NO_PY" in result.stderr


def test_a_candidate_stands_when_there_is_no_project_root_to_compare_it_against(
    tmp_path: Path,
) -> None:
    # The other half of the rule, and the one a blunt containment gets wrong. No
    # `CLAUDE_PROJECT_DIR` and no `git` answer is not a project this process can name, and
    # refusing every candidate on the strength of a question it could not ask would turn an
    # unresolvable root -- the ordinary state outside a repository -- into no hooks at all.
    planted, ran = _planted_interpreter(tmp_path)
    _run(
        "closed",
        "hook",
        "PreToolUse",
        plugin_root=_plugin_root(tmp_path, 0),
        candidates=str(planted),
    )
    assert ran.exists()


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_the_project_root_is_never_taken_from_an_inherited_git_environment(tmp_path: Path) -> None:
    # `gitenv._git_toplevel` scrubs this exact call one layer down and names the failure
    # verbatim; the wrapper did not. Measured: `cd repoA` with GIT_DIR/GIT_WORK_TREE naming
    # repoB put the launcher in repoB, and every entry but the dispatcher's relies on `--root`
    # defaulting to `.` — so the whole hook then read another repository's stayfixed.toml,
    # budgets and note store. This is the Codex hot path, where CLAUDE_PROJECT_DIR is unset.
    here, there = tmp_path / "here", tmp_path / "there"
    for repository in (here, there):
        repository.mkdir()
        git(repository, "init", "-q")
    root = _plugin_root(tmp_path, 0, echo_cwd=True)
    env = _env(root, None, None)
    env["GIT_DIR"] = str(there / ".git")
    env["GIT_WORK_TREE"] = str(there)
    result = subprocess.run(
        [str(root / "hooks" / WRAPPER.name), "open", "hook", "PreToolUse"],
        capture_output=True,
        text=True,
        check=False,
        env=env,
        cwd=str(here),
        stdin=subprocess.DEVNULL,
    )
    assert result.stdout.strip() == str(here.resolve())


@pytest.mark.skipif(not os.access("/usr/bin/id", os.X_OK), reason="no /usr/bin/id on this system")
def test_the_wrapper_hands_its_git_the_database_home_and_never_an_inherited_one(
    tmp_path: Path,
) -> None:
    # The wrapper asks git for the project root and the checkouts before stayfixed starts, and
    # hands it a `HOME` so that the owner's `safe.directory` answers. `HOME` chooses git's global
    # configuration, which names programs git runs, and direnv, mise or a devcontainer can point
    # it into the clone, so it is the password database's home for this user, the one every
    # `git` stayfixed runs in a hook gets, and never the inherited value. A stand-in `git`
    # records the `HOME` each call meets; the database is asked here by name, as the wrapper
    # asks it, since this process's own lookup by uid follows the suite's `HOME`. Mutation
    # (declared): the wrapper hands git the inherited `HOME` again -> this reddens.
    _, database = _user_and_database_home()
    project = tmp_path / "project"
    project.mkdir()
    root, log = _plugin_root_recording_git_homes(tmp_path, project)
    env = _env(root, None, None)
    env["HOME"] = "fakehome"
    result = subprocess.run(
        [str(root / "hooks" / WRAPPER.name), "open", "hook", "PreToolUse"],
        capture_output=True,
        text=True,
        check=False,
        env=env,
        cwd=str(project),
        stdin=subprocess.DEVNULL,
    )
    assert result.returncode == 0, result.stderr
    assert log.read_text(encoding="utf-8").splitlines() == [
        f"rev-parse --show-toplevel|{database}",
        f"-C {project} worktree list --porcelain|{database}",
    ]


def _user_and_database_home() -> tuple[str, str]:
    """This user's name and the home the password database lists for it, asked by name, as the
    wrapper asks: this process's own lookup by uid follows the suite's `HOME`."""
    import pwd

    user = subprocess.run(["/usr/bin/id", "-un"], capture_output=True, text=True, check=True)
    name = user.stdout.strip()
    database = pwd.getpwnam(name).pw_dir
    assert os.path.isabs(database), database
    return name, database


def _plugin_root_recording_git_homes(
    tmp_path: Path,
    project: Path,
    *,
    id_candidates: str | None = None,
    looks_up_git_home: bool = True,
) -> tuple[Path, Path]:
    """A plugin root whose only git is a stand-in that answers `project` for the root and the
    checkouts and records the `HOME` each call meets, one `<argv>|<HOME>` line per call. The
    root, and the record. The wrapper keeps the home lookup it ships, which is what the cases
    that build one are about, unless `looks_up_git_home` says otherwise."""
    log = tmp_path / "git-homes"
    stand_in = tmp_path / "bin" / "git"
    stand_in.parent.mkdir()
    stand_in.write_text(
        f"#!/bin/sh\nprintf '%s|%s\\n' \"$*\" \"${{HOME-no HOME}}\" >> '{log}'\n"
        f"case $1 in rev-parse) echo '{project}' ;; -C) echo 'worktree {project}' ;; esac\n",
        encoding="utf-8",
    )
    stand_in.chmod(0o755)
    root = _plugin_root(
        tmp_path,
        0,
        echo_cwd=True,
        git_candidates=str(stand_in),
        id_candidates=id_candidates,
        looks_up_git_home=looks_up_git_home,
    )
    return root, log


def test_the_suites_copies_of_the_wrapper_hand_their_git_this_tests_home(tmp_path: Path) -> None:
    # The wrapper's two `git` calls start from `env -i` and take the home the shell's `~name` finds
    # for `id -un`'s name, which no variable redirects, so every copy the suite ran read the
    # developer's own git configuration: a `safe.bareRepository` or a `trace2` setting there acted
    # on each run, and a verdict could depend on whose machine ran it. A copy the suite builds
    # hands them this test's `HOME` instead, after the lookup it ships; the lookup's own cases keep
    # it. Mutation (declared): `mutations/`'s "the suite's copies of the wrapper look their git's
    # home up as shipped" -> the record names the database's home.
    project = tmp_path / "project"
    project.mkdir()
    root, log = _plugin_root_recording_git_homes(tmp_path, project, looks_up_git_home=False)
    result = subprocess.run(
        [str(root / "hooks" / WRAPPER.name), "open", "hook", "PreToolUse"],
        capture_output=True,
        text=True,
        check=False,
        env=_env(root, None, None),
        cwd=str(project),
        stdin=subprocess.DEVNULL,
    )
    assert result.returncode == 0, result.stderr
    home = os.environ["HOME"]
    assert log.read_text(encoding="utf-8").splitlines() == [
        f"rev-parse --show-toplevel|{home}",
        f"-C {project} worktree list --porcelain|{home}",
    ]


ZSH = "/bin/zsh" if os.access("/bin/zsh", os.X_OK) else shutil.which("zsh")


@pytest.mark.skipif(ZSH is None, reason="no zsh, the one shell whose ~name reads a variable first")
@pytest.mark.skipif(not os.access("/usr/bin/id", os.X_OK), reason="no /usr/bin/id on this system")
def test_a_variable_named_for_the_user_chooses_no_home_for_the_wrappers_git_under_zsh_as_sh(
    tmp_path: Path,
) -> None:
    # zsh expands `~name` from a string parameter called `name` whose value starts with `/`
    # before it asks the password database, and keeps doing so run as `sh` and under
    # `emulate sh`; macOS lets `/bin/sh` be zsh. So a variable in the hook's environment named
    # for the user chose the `HOME` the wrapper's git reads, whose global configuration names
    # programs git runs. Measured before the lookup unset that variable: both of the wrapper's
    # git calls met the variable's directory, inside the clone. Run as `sh`, the name the kernel
    # hands the shell from `#!/bin/sh`. Mutation (declared): the wrapper looks the home up
    # without unsetting the variable named for the user -> this reddens.
    user, database = _user_and_database_home()
    project = tmp_path / "project"
    (project / "fakehome").mkdir(parents=True)
    root, log = _plugin_root_recording_git_homes(tmp_path, project)
    env = _env(root, None, None)
    env[user] = str(project / "fakehome")
    result = subprocess.run(
        ["sh", str(root / "hooks" / WRAPPER.name), "open", "hook", "PreToolUse"],
        executable=ZSH,
        capture_output=True,
        text=True,
        check=False,
        env=env,
        cwd=str(project),
        stdin=subprocess.DEVNULL,
    )
    assert result.returncode == 0, result.stderr
    # Non-vacuous: the launcher ran, from the root the stand-in named.
    assert result.stdout == f"{project.resolve()}\n"
    assert log.read_text(encoding="utf-8").splitlines() == [
        f"rev-parse --show-toplevel|{database}",
        f"-C {project} worktree list --porcelain|{database}",
    ]


@pytest.mark.skipif(not os.access("/usr/bin/id", os.X_OK), reason="no /usr/bin/id on this system")
@pytest.mark.parametrize("found", [True, False], ids=["an id further down", "no id at all"])
def test_the_wrapper_takes_id_from_any_absolute_candidate_and_never_a_name_the_environment_holds(
    tmp_path: Path, found: bool
) -> None:
    # The wrapper named the user by `/usr/bin/id` alone, and NixOS has none: its git got no
    # `HOME`, so a global `safe.directory` stopped answering, and a checkout another user owns
    # lost git's anchor for the containment. `id` now comes from a list of absolute paths, as git
    # does. A list with an absent path first stands for that system; one with no `id` at all is
    # the arm that hands git no `HOME` and must not reach for the name the environment carries.
    # Mutations (declared): the wrapper runs its first id candidate whether or not it is there ->
    # the first case reddens; the wrapper names the user by the environment's USER where it has
    # no id -> the second.
    user, database = _user_and_database_home()
    project = tmp_path / "project"
    project.mkdir()
    stand_in = tmp_path / "id"
    stand_in.write_text('#!/bin/sh\nexec /usr/bin/id "$@"\n', encoding="utf-8")
    stand_in.chmod(0o755)
    absent = tmp_path / "absent" / "id"
    candidates = f"{absent} {stand_in}" if found else f"{absent} {absent}-too"
    root, log = _plugin_root_recording_git_homes(tmp_path, project, id_candidates=candidates)
    env = _env(root, None, None)
    env.update(HOME="fakehome", USER=user, LOGNAME=user)
    result = subprocess.run(
        [str(root / "hooks" / WRAPPER.name), "open", "hook", "PreToolUse"],
        capture_output=True,
        text=True,
        check=False,
        env=env,
        cwd=str(project),
        stdin=subprocess.DEVNULL,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == f"{project.resolve()}\n"
    home = database if found else "no HOME"
    assert log.read_text(encoding="utf-8").splitlines() == [
        f"rev-parse --show-toplevel|{home}",
        f"-C {project} worktree list --porcelain|{home}",
    ]


def test_a_launcher_that_cannot_be_read_refuses_with_a_token(tmp_path: Path) -> None:
    # `test -f` tests existence, not readability. Measured with `chmod 000`: the wrapper printed
    # CPython's own "Permission denied" and exited 2 with no SF_ token, passed straight through
    # by `case "$rc" in 0|2)` — an unattributed exit 2, which every SF_ token exists to make
    # impossible, and a state `doctor`'s wrapper row reported green for, because it keys on
    # finding a token.
    root = _plugin_root(tmp_path, 0)
    (root / "scripts" / "stayfixed").chmod(0o000)
    try:
        result = _run("closed", "hook", "PreToolUse", plugin_root=root)
    finally:
        (root / "scripts" / "stayfixed").chmod(0o755)
    assert result.returncode == 2
    assert "SF_NO_LAUNCHER" in result.stderr


@pytest.mark.parametrize(("policy", "code"), [("closed", 2), ("open", 0)])
def test_a_project_root_that_cannot_be_entered_says_so(
    tmp_path: Path, policy: str, code: int
) -> None:
    # The silent half of the same line. A root that cannot be *resolved* is a correct open
    # degradation — nothing is configured, nothing is emitted. A root that WAS named and cannot
    # be entered is not: the process stayed in the harness's cwd, and if that happened to be
    # another stayfixed project every `--root`-defaulting entry read *that* project's
    # configuration, with no token and nothing in the sink.
    root = _plugin_root(tmp_path, 0, echo_cwd=True)
    env = _env(root, None, None)
    env["CLAUDE_PROJECT_DIR"] = str(tmp_path / "not-on-disk")
    result = subprocess.run(
        [str(root / "hooks" / WRAPPER.name), policy, "hook", "PreToolUse"],
        capture_output=True,
        text=True,
        check=False,
        env=env,
        cwd=str(tmp_path),
        stdin=subprocess.DEVNULL,
    )
    assert result.returncode == code
    assert "SF_NO_ROOT" in result.stderr
    # Non-vacuous: the launcher was not reached at all, which is what "cannot be entered" has
    # to mean — a run that continued in the harness's cwd would have printed one.
    assert result.stdout == ""


def test_a_missing_launcher_refuses_although_the_environment_names_one(tmp_path: Path) -> None:
    # The refusal the self-derivation still owes: a wrapper with no launcher beside it must
    # say so rather than reach for the one the environment offers. Both arms matter — without
    # the refusal a missing launcher reaches Python as a missing file and exits 2 by CPython
    # accident, with no token to attribute it; without the self-derivation it would run
    # `theirs` and exit 0.
    ours = _plugin_root(tmp_path / "ours", 0, with_launcher=False)
    theirs = _plugin_root(tmp_path / "theirs", 0)
    result = _run("closed", "hook", "PreToolUse", plugin_root=ours, env_root=theirs)
    assert result.returncode == 2
    assert "SF_NO_LAUNCHER" in result.stderr


@pytest.mark.parametrize("rc", [1, 3, 126, 127])
def test_any_other_exit_code_becomes_a_refusal_under_closed(tmp_path: Path, rc: int) -> None:
    # The fail-closed matrix's "ImportError planted" row, generalised. 1 is an ImportError, 126 a
    # lost executable bit on the launcher, 127 a missing interpreter the probe somehow accepted;
    # none of them may read as allow.
    result = _run("closed", "hook", "PreToolUse", plugin_root=_plugin_root(tmp_path, rc))
    assert result.returncode == 2
    assert "SF_RC" in result.stderr and str(rc) in result.stderr


@pytest.mark.parametrize("rc", [0, 2])
def test_the_two_platform_codes_pass_through_untouched(tmp_path: Path, rc: int) -> None:
    # The dispatcher owns these two and nothing else may reinterpret them: a 2 it produced is
    # a handler's deny, and the wrapper must not relabel it as its own failure.
    result = _run("closed", "hook", "PreToolUse", plugin_root=_plugin_root(tmp_path, rc))
    assert result.returncode == rc
    assert "stayfixed:" not in result.stderr


def test_stayfixed_runs_from_the_project_root(tmp_path: Path) -> None:
    # Every hooks.json entry but the dispatcher's relies on `--root` defaulting to `.`, and the
    # harness does not promise to launch a hook in the project. The wrapper resolves the root —
    # CLAUDE_PROJECT_DIR, else git — and changes into it, so one rule serves every entry.
    project = tmp_path / "project"
    (project / ".git").mkdir(parents=True)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    root = _plugin_root(tmp_path, 0, echo_cwd=True)
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(project))
    env.pop("CLAUDE_PLUGIN_ROOT", None)
    result = subprocess.run(
        [
            str(root / "hooks" / WRAPPER.name),
            "open",
            "memory",
            "session-context",
            "--bundle",
            "standing-rules",
        ],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(elsewhere),
        env=env,
    )
    assert result.stdout.strip() == str(project.resolve())


def test_the_wrapper_is_committed_executable() -> None:
    # Measured: a 0644 wrapper does NOT block — the harness never executes it, so no code of
    # ours runs and no policy applies. The wrapper cannot defend its own mode; this assertion
    # and `doctor`'s wrapper probe are the whole defence.
    assert stat.S_IMODE(WRAPPER.stat().st_mode) & 0o111, "run-hook.sh must ship executable"


def _clone_shipping_a_git(tmp_path: Path, answer: Path) -> tuple[Path, Path]:
    """A checkout that commits its own `git`, and the file it appends to when one runs.

    `answer` is what the planted git prints for `rev-parse --show-toplevel`. Its stdout is what
    the wrapper anchors on, so a decoy tree is the visible consequence of having run it — which
    is what makes the assertion below about the rule rather than about a marker file.
    """
    clone = tmp_path / "clone"
    clone.mkdir(exist_ok=True)
    git(clone, "init", "-q")
    ran = tmp_path / "planted-git-ran"
    planted = clone / "git"
    planted.write_text(
        f'#!/bin/sh\necho "$*" >> "{ran}"\necho "{answer}"\nexit 0\n', encoding="utf-8"
    )
    planted.chmod(0o755)
    return clone, ran


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_the_wrapper_never_runs_a_git_the_environment_put_on_path(tmp_path: Path) -> None:
    # `git` is a program this file chooses, and it was chosen by `PATH` — which a committed
    # `.claude/settings.json` `env` block sets. Measured on the shipped wrapper, on the Codex
    # hot path where `CLAUDE_PROJECT_DIR` is unset and `git` is the only anchor: a clone that
    # ships a `git` had that binary EXECUTED on every hook invocation, before any guard of ours,
    # and its stdout became the root every `--root`-defaulting entry then ran against. Gating
    # `STAYFIXED_PYTHON_CANDIDATES` and containing the interpreter while the anchor itself was
    # an environment-chosen program is the "pair of equivalent inputs" defect a third time.
    decoy = tmp_path / "decoy"
    decoy.mkdir()
    clone, ran = _clone_shipping_a_git(tmp_path, decoy)
    result = _run(
        "closed",
        "hook",
        "PreToolUse",
        plugin_root=_plugin_root(tmp_path, 0, echo_cwd=True),
        path=f"{clone}:{os.environ.get('PATH', '/usr/bin:/bin')}",
        cwd=clone,
    )
    assert not ran.exists(), "the clone's own git was executed to resolve the project root"
    # WHICH git answered, not merely that nothing crashed: the real one names the clone and the
    # planted one names the decoy, so the directory the launcher reports says which ran. An arm
    # that broke and fell through to some other refusal cannot satisfy this.
    assert result.returncode == 0
    assert result.stdout.splitlines() == [str(clone.resolve())]


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_an_interpreter_in_the_git_root_is_refused_although_the_environment_names_another_root(
    tmp_path: Path,
) -> None:
    # The containment was anchored on `CLAUDE_PROJECT_DIR`, which reaches this process from the
    # same committed `env` block it exists to defeat. Measured on the shipped wrapper: setting
    # `PATH=<clone>` AND `CLAUDE_PROJECT_DIR=<outside the clone>` made the clone's own `python3`
    # "outside the project root", and it ran the launcher on a machine where no absolute
    # candidate answers — which is the only machine the containment exists for. So the candidate
    # is measured against the UNION of both anchors, and after the pinning above one of them is
    # the answer of a binary the clone does not choose.
    clone, _shipped, ran = _clone_shipping_an_interpreter(tmp_path)
    git(clone, "init", "-q")
    outside = tmp_path / "outside"
    outside.mkdir()
    plugin = _plugin_root(tmp_path, 0, echo_cwd=True)
    path = f"{clone}:{os.environ.get('PATH', '/usr/bin:/bin')}"
    # `python3` and not the shipped path: the candidate list is pinned to its own last entry,
    # which is the `PATH` fall-through a pyenv, nix or asdf machine actually reaches. A run that
    # let an absolute candidate answer first would never reach the planted one and prove nothing.
    result = _run(
        "closed",
        "hook",
        "PreToolUse",
        plugin_root=plugin,
        project=outside,
        candidates="python3",
        path=path,
        cwd=clone,
    )
    assert not ran.exists(), "the tree's own interpreter ran while the environment moved the anchor"
    assert result.returncode == 2
    # WHICH refusal fired. A later `elif` that let this arm fall through to the generic message
    # would still exit 2 with a SF_NO_PY token, so the token alone proves nothing here.
    assert "inside the project root" in result.stderr
    # Non-vacuous, and it names the member doing the work: take the git anchor away — the same
    # tree, from a directory that is not a repository — and the remaining anchor is the variable
    # the clone controls, which is exactly the state this change is about.
    plain = tmp_path / "not-a-repo"
    plain.mkdir()
    _run(
        "closed",
        "hook",
        "PreToolUse",
        plugin_root=plugin,
        project=outside,
        candidates="python3",
        path=path,
        cwd=plain,
    )
    assert ran.exists()


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_an_interpreter_in_another_checkout_of_the_same_repository_is_refused(
    tmp_path: Path,
) -> None:
    # Both anchors named a single checkout, and a clone's committed bytes reach every checkout
    # of it. Measured on the shipped wrapper: launched inside a linked worktree — which this
    # project's own preset makes the default place an agent works — `--show-toplevel` answered
    # the worktree, so the main checkout's committed `python3` was "outside the project root",
    # reachable through a `PATH` entry of `${CLAUDE_PROJECT_DIR}/../../bin` from the same
    # committed `env` block, and it ran the launcher. `setup` already refuses an overlay root in
    # any checkout of the project for exactly this reason; the wrapper now measures against the
    # same set, taken from `git worktree list` through the pinned `git`.
    #
    # Mutation (`mutations/`'s "the wrapper measures a candidate against one checkout only"):
    # the checkout-list arm of `in_project` stops answering → the main checkout's interpreter
    # runs from the worktree and `ran` exists.
    clone, _shipped, ran = _clone_shipping_an_interpreter(tmp_path)
    git = ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", "-C", str(clone)]
    subprocess.run([*git, "init", "-q"], check=True, capture_output=True)
    subprocess.run([*git, "add", "python3"], check=True, capture_output=True)
    subprocess.run([*git, "commit", "-q", "-m", "ship"], check=True, capture_output=True)
    worktree = tmp_path / "worktrees" / "feature"
    subprocess.run(
        [*git, "worktree", "add", "-q", str(worktree), "-b", "feature"],
        check=True,
        capture_output=True,
    )
    plugin = _plugin_root(tmp_path, 0, echo_cwd=True)
    # `PATH` names the MAIN checkout while the hook runs in the worktree: the arrangement a
    # committed `env` block reaches with `${CLAUDE_PROJECT_DIR}/../../<main>`.
    path = f"{clone}:{os.environ.get('PATH', '/usr/bin:/bin')}"
    result = _run(
        "closed",
        "hook",
        "PreToolUse",
        plugin_root=plugin,
        project=worktree,
        candidates="python3",
        path=path,
        cwd=worktree,
    )
    assert not ran.exists(), "the main checkout's interpreter ran from a linked worktree"
    assert result.returncode == 2
    assert "inside the project root" in result.stderr
    # Non-vacuous: the same `PATH` from a directory that is not a checkout of this repository
    # has no such anchor, and the candidate stands — which is what makes the refusal above the
    # checkout list's doing and not some other arm's.
    plain = tmp_path / "not-a-repo"
    plain.mkdir()
    _run(
        "closed",
        "hook",
        "PreToolUse",
        plugin_root=plugin,
        project=plain,
        candidates="python3",
        path=path,
        cwd=plain,
    )
    assert ran.exists()


def test_the_two_states_with_no_interpreter_are_told_apart(tmp_path: Path) -> None:
    # The message was byte-identical for "a candidate was found inside the tree and skipped" and
    # "there was no candidate at all", while the comment beside it claimed it "says what happened
    # rather than only that nothing was found". A developer with an in-tree `.venv` and no system
    # 3.11 therefore read "none among the candidates", which is false, and the one remedy that
    # exists was named only in `docs/cli.md` and the changelog — neither of them where they are
    # standing when the hook refuses.
    clone, shipped, ran = _clone_shipping_an_interpreter(tmp_path)
    plugin = _plugin_root(tmp_path, 0)
    in_tree = _run(
        "closed",
        "hook",
        "PreToolUse",
        plugin_root=plugin,
        project=clone,
        candidates=str(shipped),
    )
    assert in_tree.returncode == 2
    assert "SF_NO_PY" in in_tree.stderr
    assert "inside the project root" in in_tree.stderr
    assert "outside the checkout" in in_tree.stderr, "the remedy is not named where it is needed"
    assert not ran.exists()

    nothing = _run(
        "closed",
        "hook",
        "PreToolUse",
        plugin_root=plugin,
        candidates="/nonexistent/python3",
    )
    assert nothing.returncode == 2
    assert "SF_NO_PY" in nothing.stderr
    # The assertion the old message could not pass: the two states must not print one string.
    assert "inside the project root" not in nothing.stderr


def test_a_cdpath_never_chooses_the_directory_the_hook_runs_in(tmp_path: Path) -> None:
    # The one `cd` in this file that was neither `CDPATH=`-cleared nor `--`-terminated, while
    # the two others took both cares. Measured: with `CDPATH` set and a relative root, `cd`
    # WRITES THE DESTINATION IT CHOSE TO STDOUT — ahead of anything the launcher prints, and a
    # hook's stdout is a contract the harness parses — and lands in a `CDPATH`-chosen directory,
    # so the `pwd -P` that anchors the interpreter containment then measures the wrong tree.
    decoy = tmp_path / "decoy-parent" / "target"
    decoy.mkdir(parents=True)
    real = tmp_path / "real-parent" / "target"
    real.mkdir(parents=True)
    result = _run(
        "open",
        "hook",
        "PreToolUse",
        plugin_root=_plugin_root(tmp_path, 0, echo_cwd=True),
        project=Path("target"),
        cwd=real.parent,
        extra={"CDPATH": str(decoy.parent)},
    )
    # Both halves in one assertion: exactly one line, so nothing was written ahead of the
    # launcher, and it is the real tree, so `CDPATH` did not choose the directory.
    assert result.stdout.splitlines() == [str(real.resolve())]


def test_a_project_root_whose_name_begins_with_a_dash_is_a_destination_and_not_an_option(
    tmp_path: Path,
) -> None:
    # The other half of the same line. Without the `--`, `cd` parses `-dashed` as options and
    # the entry refuses a root that is on disk and perfectly enterable.
    dashed = tmp_path / "parent" / "-dashed"
    dashed.mkdir(parents=True)
    result = _run(
        "open",
        "hook",
        "PreToolUse",
        plugin_root=_plugin_root(tmp_path, 0, echo_cwd=True),
        project=Path("-dashed"),
        cwd=dashed.parent,
    )
    assert "SF_NO_ROOT" not in result.stderr
    assert result.stdout.splitlines() == [str(dashed.resolve())]


@pytest.mark.parametrize(("policy", "code"), [("closed", 2), ("open", 0)])
def test_no_git_at_any_absolute_path_is_a_token_rather_than_a_silent_run(
    tmp_path: Path, policy: str, code: int
) -> None:
    # `git`'s answer is one of the two anchors the interpreter containment is measured against,
    # so a machine with no `git` at any absolute path has no anchor this process can trust — and
    # the honest outcome is the one the code already gives for a root it cannot trust, rather
    # than a silent run that keeps the shape of the guard and none of its strength.
    result = _run(
        policy,
        "hook",
        "PreToolUse",
        plugin_root=_plugin_root(tmp_path, 0, echo_cwd=True, git_candidates="/nonexistent/git"),
    )
    assert result.returncode == code
    assert "SF_NO_GIT" in result.stderr
    # Non-vacuous: the launcher was never reached, so this is the wrapper's own decision and not
    # something that happened further down.
    assert result.stdout == ""


class Planting(NamedTuple):
    """A module the environment plants, as one case of the test below sees it."""

    interpreter: str
    env: dict[str, str]
    record: Path


def _planted_module(directory: Path, name: str, record: Path) -> None:
    """Write `<directory>/<name>.py`, which appends its `sys.argv` to `record` on each run.

    `sitecustomize` and `usercustomize` are the two names CPython's `site` imports at startup
    from whatever `sys.path` holds by then, before the program's first line.
    """
    directory.mkdir(parents=True)
    (directory / f"{name}.py").write_text(
        f"import sys\nwith open({str(record)!r}, 'a') as f:\n    f.write(repr(sys.argv) + '\\n')\n",
        encoding="utf-8",
    )


def _base_interpreter() -> str:
    """The interpreter the suite's venv was made from, which has a user site where the venv has
    none: a venv disables the user site, so a case about it run under `sys.executable` would be
    green with the guard deleted.

    `sys._base_executable` is private to CPython, and nothing public names the interpreter a venv
    was made from: `sys.base_prefix` is a directory, and which binary under it the venv copied or
    linked is not recorded anywhere else. Outside a venv it is `sys.executable`, as is the fallback.
    """
    return getattr(sys, "_base_executable", None) or sys.executable


def _python_path_case(tmp_path: Path) -> Planting:
    planted = tmp_path / "planted-sitecustomize"
    record = tmp_path / "sitecustomize-ran"
    _planted_module(planted, "sitecustomize", record)
    return Planting(sys.executable, {"PYTHONPATH": str(planted)}, record)


def _user_site_case(tmp_path: Path) -> Planting:
    interpreter = _base_interpreter()
    base = tmp_path / "userbase"
    # Asked of the interpreter itself, because the layout differs by build: a macOS framework
    # build puts it under `lib/python/`, every other one under `lib/python3.N/`.
    site_dir = subprocess.run(
        [interpreter, "-c", "import site; print(site.getusersitepackages())"],
        capture_output=True,
        text=True,
        check=True,
        env=dict(os.environ, PYTHONUSERBASE=str(base)),
    ).stdout.strip()
    record = tmp_path / "usercustomize-ran"
    _planted_module(Path(site_dir), "usercustomize", record)
    return Planting(interpreter, {"PYTHONUSERBASE": str(base)}, record)


@pytest.mark.parametrize(
    "case", [_python_path_case, _user_site_case], ids=["pythonpath", "user-site"]
)
def test_a_module_the_environment_plants_never_runs(
    tmp_path: Path, case: Callable[[Path], Planting]
) -> None:
    # Measured on the wrapper before `-I`: `PYTHONPATH=<dir with sitecustomize.py> sh
    # hooks/run-hook.sh open --version` printed the version and the planted module ran twice, for
    # the version probe's `-c` and for the launcher. Reddens on either `-I` removed, which is two
    # entries in `mutations/`. The contract is `docs/cli.md`'s, "The chosen interpreter starts
    # isolated". `PYTHONHOME` has no case of its own: planting one means shipping a whole standard
    # library tree, and `-I` ignores it by the same `-E` that ignores `PYTHONPATH`.
    #
    # The shipped wrapper and the shipped launcher, run in place, and not `_plugin_root`'s fake:
    # the other half of this case is that the real launcher still finds its own `src` under
    # `-I`, which no longer puts the script's directory on `sys.path` and reads no `PYTHON*`
    # variable — so `--version` answering is the launcher's own insertion working. Run from
    # `tmp_path`, outside every repository, so neither anchor names this checkout and the
    # suite's own interpreter is not refused as an in-tree one.
    planting = case(tmp_path)
    # Non-vacuous: the planting does run in an interpreter started without `-I`, so a green
    # assertion below is the wrapper's doing and not a planting the interpreter ignores.
    subprocess.run(
        [planting.interpreter, "-c", "pass"],
        check=True,
        env=dict(os.environ, **planting.env),
        cwd=tmp_path,
    )
    assert planting.record.read_text(encoding="utf-8") == "['-c']\n"
    planting.record.unlink()
    result = _run(
        "closed",
        "--version",
        plugin_root=ROOT,
        candidates=planting.interpreter,
        cwd=tmp_path,
        extra=planting.env,
    )
    assert not planting.record.exists(), planting.record.read_text(encoding="utf-8")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == f"stayfixed {__version__}"


CANARY = "CANARY-IN-REPO-RULE"


@pytest.mark.parametrize("spelling", ["relative", "absolute"])
def test_a_trust_record_under_a_home_the_environment_names_is_never_read(
    tmp_path: Path, spelling: str
) -> None:
    # A direnv, mise or devcontainer setup can set `HOME` from a file the clone commits (Claude
    # Code's `env` block cannot), and the wrapper enters the project root before Python starts,
    # so `HOME=fakehome` is a directory the clone ships. The clone ships the owner's own record
    # there, moved out of the owner's home: a digest the clone can compute from its own content.
    # The shipped wrapper and launcher run it, with only the password database's answer pinned to
    # the owner's home (`tests/ownerhome.py`), since nothing else can choose it.
    owner = tmp_path / "owner"
    owner.mkdir()
    project = tmp_path / "project"
    shutil.copytree(ROOT / "tests" / "fixtures" / "hostile-project", project)
    plugin = plugin_root_with_owner_home(tmp_path, owner)
    trusted = subprocess.run(
        [*stayfixed_argv(owner), "memory", "trust", "--in-repo-memory", "--root", str(project)],
        capture_output=True,
        text=True,
        check=False,
        stdin=subprocess.DEVNULL,
        env=dict(os.environ, HOME=str(owner)),
    )
    assert trusted.returncode == 0, trusted.stderr
    owners = owner / ".config" / "stayfixed" / "trust.json"
    planted = project / "fakehome" / ".config" / "stayfixed" / "trust.json"
    planted.parent.mkdir(parents=True)
    owners.rename(planted)
    home = "fakehome" if spelling == "relative" else str(project / "fakehome")
    argv = ["open", "memory", "session-context", "--bundle", "standing-rules", "--part", "1"]

    def bundle() -> subprocess.CompletedProcess[str]:
        return _run(*argv, plugin_root=plugin, project=project, extra={"HOME": home})

    refused = bundle()
    assert refused.returncode == 0, refused.stderr
    assert CANARY not in refused.stdout
    # The positive control: the same record under the database's home lets the note through
    # under the same `HOME`, so the absence above is the home's doing.
    planted.rename(owners)
    admitted = bundle()
    assert CANARY in admitted.stdout, admitted.stderr


@pytest.mark.parametrize("inherited", [None, "0", ""], ids=["unset", "another value", "empty"])
def test_the_launcher_is_told_the_wrapper_launched_it_whatever_value_was_inherited(
    tmp_path: Path, inherited: str | None
) -> None:
    # stayfixed takes `git` from the fixed list only in a process the wrapper launched, and
    # knows it by `gitenv.HOOK_WRAPPER_VARIABLE` holding `gitenv.HOOK_WRAPPER_LAUNCHED`, one
    # name and value spelled twice; this holds the two equal. A committed `env` block or a parent
    # can preset the variable, and a preset value left standing would hand every hook's `git`
    # back to the `PATH` that block sets. Mutations (declared): the wrapper stops setting it ->
    # every case reddens; it keeps a value it inherited -> "another value" reddens.
    environment = {} if inherited is None else {HOOK_WRAPPER_VARIABLE: inherited}
    root = _plugin_root(tmp_path, 0, prints=f"os.environ.get({HOOK_WRAPPER_VARIABLE!r})")
    result = _run("open", "hook", "PreToolUse", plugin_root=root, extra=environment)
    assert result.returncode == 0, result.stderr
    assert result.stdout == f"{HOOK_WRAPPER_LAUNCHED}\n"


# The absolute paths both the wrapper and `stayfixed.gitenv` take `git` from in a hook.
ABSOLUTE_GIT = [path for path in GIT_CANDIDATES if os.access(path, os.X_OK)]
# What a committed `env` block can put first on `PATH` for every hook, and Claude Code resolves
# the relative entry against the project (measured on 2.1.293): the `git` every stayfixed query
# asked, the `git-lfs` git runs for a `filter.lfs.process`, and the two programs the wrapper itself
# ran by name.
PLANTED = ("git", "git-lfs", "dirname", "env")


def _plant(project: Path, ran: Path) -> None:
    """`<project>/fakebin` holding each of `PLANTED`: each appends its name and argv to `ran`, then
    hands over to the real program where this machine has one, so a run that reached a stub
    goes on as it would have and the next stub can still be reached."""
    fakebin = project / "fakebin"
    fakebin.mkdir()
    for name in PLANTED:
        real = shutil.which(name) if name != "git-lfs" else None
        then = f'exec "{real}" "$@"' if real else "exit 1"
        stub = fakebin / name
        stub.write_text(f'#!/bin/sh\necho "{name} $*" >> "{ran}"\n{then}\n', encoding="utf-8")
        stub.chmod(0o755)


@pytest.mark.skipif(not ABSOLUTE_GIT, reason="no git at any of the absolute candidate paths")
def test_no_program_a_committed_path_plants_runs_on_a_hook_that_asks_git(tmp_path: Path) -> None:
    # End to end, through the shipped wrapper and launcher: PostToolUse after a red `pytest` over
    # a dirty tree, whose notice counts the dirty files with `git status`. The clone ships
    # `fakebin/git` and `fakebin/git-lfs` and a `PATH` of `fakebin:…`, and the owner's global
    # configuration, under the home the password database records, which is the one a hook's
    # `git` reads, names a `git-lfs` clean filter for `* filter=lfs`, which the clone's
    # `.gitattributes` sets: `git status` runs it on the modified file. A `clean` command and not
    # `process`: a process filter that starts and exits in its handshake, as the planted `git-lfs`
    # does, is fatal to `status`, and git then gives no answer to count, while a clean filter that
    # fails is not, so the count below is held whichever program ran. A filter that cannot start
    # at all is fatal only when marked required (measured with `git status --porcelain`).
    # Measured before the fix: every query ran the clone's `git`, the absolute `git` it handed
    # over to ran the clone's `git-lfs`, and the wrapper ran the clone's `dirname` and `env`. The
    # same block also presets the variable that tells stayfixed the wrapper launched it, to a
    # value that would turn the fixed list off. Mutations (declared): `git_run` resolves `git`
    # through `PATH` again, or hands it the inherited `PATH`; the wrapper runs `env` or `dirname`
    # by name again, or stops overwriting that variable — each reddens this.
    owner = tmp_path / "owner"
    owner.mkdir()
    project = tmp_path / "project"
    project.mkdir()
    (project / "stayfixed.toml").write_text(
        '[stayfixed]\nversion = "0.1.0"\nstate = "installed"\npreset = "recommended"\n'
        'profile = ""\nagents = ["claude"]\n\n[project]\nname = "widget"\n'
        'base_branch = "main"\nrelease_branch = "main"\n',
        encoding="utf-8",
    )
    (project / "m.py").write_text("x = 1\n", encoding="utf-8")
    for args in (["init", "-q"], ["add", "-A"], ["commit", "-q", "-m", "chore: seed"]):
        git(project, *args, home=tmp_path)
    (project / "m.py").write_text("x = 2\n", encoding="utf-8")
    (project / ".gitattributes").write_text("* filter=lfs\n", encoding="utf-8")
    (owner / ".gitconfig").write_text(
        '[filter "lfs"]\n\tclean = git-lfs clean -- %f\n', encoding="utf-8"
    )
    ran = tmp_path / "planted-ran"
    _plant(project, ran)
    plugin = plugin_root_with_owner_home(tmp_path, owner)
    payload = {
        "hook_event_name": "PostToolUse",
        "session_id": "s",
        "cwd": str(project),
        "tool_name": "Bash",
        "tool_input": {"command": "pytest -q"},
        "tool_response": {"exit_code": 1},
    }
    env = _env(plugin, None, None)
    env.update(CLAUDE_PROJECT_DIR=str(project), PATH=f"fakebin:{os.environ.get('PATH', '')}")
    env[HOOK_WRAPPER_VARIABLE] = "0"
    result = subprocess.run(
        [str(plugin / "hooks" / WRAPPER.name), "open", "hook", "PostToolUse"],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=False,
        env=env,
        cwd=project,
    )
    assert not ran.exists(), ran.read_text(encoding="utf-8")
    assert result.returncode == 0, result.stderr
    # Non-vacuous: the dirty count is in the notice, so git was asked and answered, by a `git`
    # the clone did not choose.
    assert "uncommitted" in result.stdout, (result.stdout, result.stderr)


@pytest.mark.skipif(not ABSOLUTE_GIT, reason="no git at any of the absolute candidate paths")
@pytest.mark.parametrize("spelling", ["relative", "absolute"])
def test_a_home_inside_the_clone_names_no_program_a_hooks_git_runs(
    tmp_path: Path, spelling: str
) -> None:
    # Claude Code applies no `HOME` from a project's `env` block, but direnv, mise or a
    # devcontainer can set it from a file the clone commits, and the wrapper enters the project
    # before stayfixed starts, so `HOME=fakehome` names a directory the clone ships. Its
    # `.gitconfig` sets `core.fsmonitor` to a program beside it, and git runs that program on
    # the `git status` the red-run notice counts with. The same setting in the owner's own
    # global configuration, under the home the password database records, is the positive
    # control: it runs, so the hook's `git` did read a home, and the clone's did not run because
    # that home was the owner's. Measured before the fix: the clone's program ran twice per hook,
    # with either spelling. Mutation (declared): `git_run` hands git the inherited `HOME` again
    # -> this reddens.
    owner = tmp_path / "owner"
    owner.mkdir()
    owners_ran = tmp_path / "owners-monitor-ran"
    owners_monitor = owner / "monitor.sh"
    owners_monitor.write_text(f"#!/bin/sh\necho \"$*\" >> '{owners_ran}'\nexit 1\n", "utf-8")
    owners_monitor.chmod(0o755)
    (owner / ".gitconfig").write_text(f"[core]\n\tfsmonitor = {owners_monitor}\n", "utf-8")
    project = tmp_path / "project"
    project.mkdir()
    (project / "stayfixed.toml").write_text(
        '[stayfixed]\nversion = "0.1.0"\n\n[project]\nname = "widget"\n', encoding="utf-8"
    )
    clones_ran = tmp_path / "clones-monitor-ran"
    (project / "fakehome").mkdir()
    (project / "fakehome" / ".gitconfig").write_text(
        "[core]\n\tfsmonitor = fakehome/monitor.sh\n", encoding="utf-8"
    )
    clones_monitor = project / "fakehome" / "monitor.sh"
    clones_monitor.write_text(f"#!/bin/sh\necho \"$*\" >> '{clones_ran}'\nexit 1\n", "utf-8")
    clones_monitor.chmod(0o755)
    (project / "m.py").write_text("x = 1\n", encoding="utf-8")
    for args in (["init", "-q"], ["add", "-A"], ["commit", "-q", "-m", "chore: seed"]):
        git(project, *args, home=tmp_path)
    (project / "m.py").write_text("x = 2\n", encoding="utf-8")
    plugin = plugin_root_with_owner_home(tmp_path, owner)
    payload = {
        "hook_event_name": "PostToolUse",
        "session_id": "s",
        "cwd": str(project),
        "tool_name": "Bash",
        "tool_input": {"command": "pytest -q"},
        "tool_response": {"exit_code": 1},
    }
    env = _env(plugin, None, None)
    env.update(
        CLAUDE_PROJECT_DIR=str(project),
        HOME="fakehome" if spelling == "relative" else str(project / "fakehome"),
    )
    result = subprocess.run(
        [str(plugin / "hooks" / WRAPPER.name), "open", "hook", "PostToolUse"],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=False,
        env=env,
        cwd=project,
    )
    assert result.returncode == 0, result.stderr
    assert not clones_ran.exists(), clones_ran.read_text(encoding="utf-8")
    assert owners_ran.exists(), (result.stdout, result.stderr)
    assert "uncommitted" in result.stdout, (result.stdout, result.stderr)


def _bash_as_sh() -> str | None:
    """A bash to run the wrapper under as `sh`, or `None` where this machine has none.

    `/bin/sh` itself where it is bash, as on macOS, Fedora and Arch. Elsewhere a `bash` run under
    the name `sh`, which puts it in the POSIX mode it has as `/bin/sh` on those systems, so the
    cases below run on a machine whose `/bin/sh` is dash too, CI's among them.
    """
    probe = subprocess.run(
        ["/bin/sh", "-c", 'printf %s "${BASH_VERSION-}"'],
        capture_output=True,
        text=True,
        check=False,
    )
    return "/bin/sh" if probe.stdout else shutil.which("bash")


BASH_AS_SH = _bash_as_sh()


def _run_under_bash(
    plugin_root: Path,
    environment: dict[str, str],
    cwd: Path,
    *,
    terminal: bool = False,
    traced: bool = False,
) -> subprocess.CompletedProcess[str]:
    """The shipped wrapper copied into `plugin_root`, run by `BASH_AS_SH` as `sh` with `closed hook
    PreToolUse`: the command line the kernel builds from its `#!/bin/sh` where `/bin/sh` is bash.
    `terminal` hands it a pty for stdin, the one place it reads `STAYFIXED_PYTHON_CANDIDATES`.
    `traced` runs it under `-x`, with the trace's prefix chosen here and no variable that would
    have bash trace or run anything more, so stderr holds every command it ran. Under a timeout
    whatever it runs, so a run that waits fails the case rather than the worker."""
    assert BASH_AS_SH is not None
    if traced:
        environment = {
            name: value
            for name, value in environment.items()
            if name not in {"SHELLOPTS", "BASHOPTS", "BASH_ENV", "ENV"}
        }
        environment["PS4"] = "+ "
    argv = ["sh", str(plugin_root / "hooks" / WRAPPER.name), "closed", "hook", "PreToolUse"]
    if traced:
        argv.insert(1, "-x")
    master, slave = pty.openpty() if terminal else (-1, -1)
    try:
        return subprocess.run(
            argv,
            executable=BASH_AS_SH,
            capture_output=True,
            text=True,
            check=False,
            env=environment,
            cwd=cwd,
            stdin=slave if terminal else subprocess.DEVNULL,
            timeout=60,
        )
    except subprocess.TimeoutExpired:
        pytest.fail("the wrapper run under bash did not end")
    finally:
        for descriptor in (master, slave):
            if descriptor >= 0:
                os.close(descriptor)


@pytest.mark.skipif(BASH_AS_SH is None, reason="no bash, whose ~0 is the directory stack's top")
def test_a_name_of_digits_alone_names_no_directory_as_the_wrappers_git_home(tmp_path: Path) -> None:
    # `~0` is not a user to bash or zsh but the top of the directory stack, the current
    # directory, which is wherever the harness launched the hook and may be the clone. So a user
    # whose name is digits alone handed the wrapper's git that directory as `HOME`, and with it
    # the global configuration the clone commits there. dash asks the database, which lists no
    # such home, so the case runs under bash as `sh`. Mutation (declared): the wrapper looks a
    # name of digits alone up again -> this reddens.
    project = tmp_path / "project"
    project.mkdir()
    named = tmp_path / "id"
    named.write_text("#!/bin/sh\necho 0\n", encoding="utf-8")
    named.chmod(0o755)
    root, log = _plugin_root_recording_git_homes(tmp_path, project, id_candidates=str(named))
    result = _run_under_bash(root, _env(root, None, None), project)
    assert result.returncode == 0, result.stderr
    assert result.stdout == f"{project.resolve()}\n"
    assert log.read_text(encoding="utf-8").splitlines() == [
        "rev-parse --show-toplevel|no HOME",
        f"-C {project} worktree list --porcelain|no HOME",
    ]


@pytest.mark.skipif(BASH_AS_SH is None, reason="no bash, whose ~-0 is the directory stack too")
@pytest.mark.parametrize(
    "named",
    [
        # What `id -un` does under a uid the database does not list, as in a container run
        # with a bare `--user`: it names nobody and exits 1.
        "echo 'id: cannot find name for user ID 12345' >&2; exit 1",
        "printf '%s\\n' -0",
        "printf '%s\\n' 'x;h={fakehome}'",
    ],
    ids=["no name", "a name led by a dash", "a name holding shell syntax"],
)
def test_a_name_that_is_not_a_plain_one_names_no_home_for_the_wrappers_git(
    tmp_path: Path, named: str
) -> None:
    # The wrapper looks the home up by splicing the name `id` gives into an `eval`, so only a
    # plain name may reach it, and each other shape has its own way to the wrong home. An empty
    # name makes the lookup `~` alone, the inherited `HOME`, which direnv, mise or a
    # devcontainer can point at a directory the clone commits. `~-0` is the top of the
    # directory stack to bash and zsh, the directory the hook was launched in. And any byte the
    # shell reads as syntax runs as code inside the `eval`; `;` here sets the home outright.
    # `HOME` is absolute, so the wrapper's later check for an absolute home cannot be what
    # refuses it. Mutations (declared): the wrapper looks an empty name up -> "no name"
    # reddens; the wrapper looks a name led by - up -> "a name led by a dash"; the wrapper
    # looks up a name holding any byte -> "a name holding shell syntax".
    project = tmp_path / "project"
    fakehome = project / "fakehome"
    fakehome.mkdir(parents=True)
    stand_in = tmp_path / "id"
    stand_in.write_text(f"#!/bin/sh\n{named.format(fakehome=fakehome)}\n", encoding="utf-8")
    stand_in.chmod(0o755)
    root, log = _plugin_root_recording_git_homes(tmp_path, project, id_candidates=str(stand_in))
    env = _env(root, None, None)
    env["HOME"] = str(fakehome)
    result = _run_under_bash(root, env, project)
    assert result.returncode == 0, result.stderr
    assert result.stdout == f"{project.resolve()}\n"
    assert log.read_text(encoding="utf-8").splitlines() == [
        "rev-parse --show-toplevel|no HOME",
        f"-C {project} worktree list --porcelain|no HOME",
    ]


def _exported_functions(tmp_path: Path, names: tuple[str, ...]) -> tuple[dict[str, str], Path]:
    """`BASH_FUNC_<name>%%` for each of `names`: a function that runs a marker program, which
    records the name, and then hands over to what the name meant, so a wrapper that ran one
    answers exactly as it would have and only the record shows it. The variables, and the record."""
    ran = tmp_path / "exported-function-ran"
    marker = tmp_path / "marker"
    marker.write_text(
        f"#!{sys.executable} -I\nimport sys\n"
        f"with open({str(ran)!r}, 'a') as f:\n    f.write(' '.join(sys.argv[1:]) + '\\n')\n",
        encoding="utf-8",
    )
    marker.chmod(0o755)
    functions = {}
    for name in names:
        # `python3` is no builtin, and `command` runs the program `PATH` names past the function.
        hand_over = "command" if name == "python3" else "builtin"
        functions[f"BASH_FUNC_{name}%%"] = f'() {{ "{marker}" {name}; {hand_over} {name} "$@"; }}'
    return functions, ran


# What a trace shows the wrapper running that no function can stand in for: the special builtins,
# which bash finds before any function in POSIX mode (a `BASH_FUNC_unset%%`, like one for `set`,
# `export`, `exit` or `shift`, was measured never to run), and the reserved words `-x` writes for
# a `case` or a `for`. A program named by its path is no function's name either.
SPECIAL_BUILTINS = frozenset(
    {".", ":", "break", "continue", "eval", "exec", "exit", "export", "readonly", "return", "set"}
    | {"shift", "times", "trap", "unset"}
)
RESERVED_WORDS = frozenset({"case", "for", "if", "select", "until", "while"})
# bash 4 and later call this function unasked, for a command they cannot find. No run of the
# wrapper looks a missing command up, so no trace shows it, and it is named here.
CALLED_UNASKED = frozenset({"command_not_found_handle"})


def _unset_line() -> list[str]:
    """The names the wrapper's first statement removes the functions of, as written."""
    (line,) = [
        line
        for line in WRAPPER.read_text(encoding="utf-8").splitlines()
        if line.startswith("unset -f ")
    ]
    return line.removeprefix("unset -f ").removesuffix(" 2>/dev/null").split()


def _names_a_trace_runs(trace: str, functions: frozenset[str]) -> set[str]:
    """Every name `trace`, an `sh -x` trace of the wrapper, shows it running that a function the
    environment exports could stand in for: the first word of each traced command, less an
    assignment, a path, a special builtin, a reserved word and a function the wrapper defines
    itself (`functions`); and each bare name `command -v` is asked about, since it answers a
    function's name and the wrapper then runs that name."""
    names: set[str] = set()
    for line in trace.splitlines():
        words = line.lstrip("+").split() if line.startswith("+ ") or line.startswith("++") else []
        if not words:
            continue
        first = words[0].strip("'")
        if words[:2] == ["command", "-v"] and len(words) > 2 and "/" not in words[2]:
            names.add(words[2].strip("'"))
        if "=" in first.split("/", 1)[0] or first.startswith("/"):
            continue
        if first in SPECIAL_BUILTINS | RESERVED_WORDS | functions:
            continue
        names.add(first)
    return names


def _names_the_wrapper_runs(base: Path) -> set[str]:
    """The names an `sh -x` trace shows the shipped wrapper running, over three runs that between
    them reach every line it runs: a hook in a git repository that reaches the launcher; one
    outside any repository with no launcher, under `closed`, where `git` fails and the wrapper
    refuses; and one at a terminal whose interpreter list is bare `python3`."""
    functions = frozenset(
        re.findall(r"^([A-Za-z_][A-Za-z0-9_]*)\(\) \{", WRAPPER.read_text("utf-8"), re.M)
    )
    project = base / "project"
    project.mkdir(parents=True)
    git(project, "init", "-q", home=base)
    reached = _plugin_root(base / "reached", 0, echo_cwd=True)
    environment = _env(reached, None, None)
    found = _run_under_bash(
        reached, {**environment, "CLAUDE_PROJECT_DIR": str(project)}, project, traced=True
    )
    assert found.stdout == f"{project.resolve()}\n", found.stderr
    nowhere = base / "nowhere"
    nowhere.mkdir()
    refused = _plugin_root(base / "refused", 0, with_launcher=False)
    faulted = _run_under_bash(refused, _env(refused, None, None), nowhere, traced=True)
    assert faulted.returncode == 2 and "SF_NO_LAUNCHER" in faulted.stderr, faulted.stderr
    named = _run_under_bash(
        reached, _env(reached, None, "python3"), nowhere, terminal=True, traced=True
    )
    assert "command -v python3" in named.stderr, named.stderr
    return set().union(
        *(_names_a_trace_runs(run.stderr, functions) for run in (found, faulted, named))
    )


@pytest.mark.skipif(BASH_AS_SH is None, reason="no bash, the one shell that imports functions")
@pytest.mark.skipif(not ABSOLUTE_GIT, reason="no git at any of the absolute candidate paths")
def test_the_wrapper_removes_the_function_of_every_name_a_trace_shows_it_running(
    tmp_path: Path,
) -> None:
    # The wrapper's first statement removes the function of every name it runs that is not a
    # special builtin, and its list was kept by hand: `echo`, `true` and
    # `command_not_found_handle` were on it with no case that would notice one leaving, and a
    # name the wrapper began to run could be missed the same way. So the list is read off a trace
    # of the wrapper itself, and the line must remove exactly those names and the one bash calls
    # unasked. Mutations (declared): `mutations/`'s "an exported function stands in for the
    # wrapper's echo again" and "an exported function stands in for the wrapper's true again" ->
    # the name is traced and not removed; "bash's command_not_found_handle is left in place
    # again" -> the line lacks it; "the wrapper spells a test as [ again, which bash 3.2 cannot
    # unset" -> `[` is traced.
    traced = _names_the_wrapper_runs(tmp_path)
    # A trace that read nothing would leave only the name named here, so the walk says what it
    # found first: the commands of the happy run, and the two only a fault reaches.
    assert {"cd", "echo", "printf", "pwd", "read", "test", "true"} <= traced, traced
    assert sorted(_unset_line()) == sorted(traced | CALLED_UNASKED)


def test_a_trace_is_read_for_the_names_a_function_could_stand_in_for() -> None:
    # The reading the case above rests on, on lines it may not meet. Measured by hand: reading a
    # path, a special builtin, a reserved word or a function of the wrapper's own as a name each
    # reddens this. Mutations (declared): `mutations/`'s "the trace reader takes an assignment
    # for a name the wrapper runs" and "the trace reader drops the name command -v is asked
    # about" -> this reddens.
    trace = (
        "+ unset -f cd\n+ set -u\n+ case $0 in\n+ here=/x\n++ CDPATH=\n++ cd -- /x\n"
        "+ for g in /a /b\n+ test -x /a\n++ /usr/bin/id -un\n+ refuse 'x'\n+ echo 'x'\n"
        "++ command -v python3\n++ command -v /bin/python3\n+ '[' -n x ']'\n"
        "+ IFS='\n'\nnot a traced line\n"
    )
    assert _names_a_trace_runs(trace, frozenset({"refuse"})) == {
        "cd",
        "command",
        "echo",
        "python3",
        "test",
        "[",
    }


# The names a hook run in a repository makes the wrapper run that a function could stand in for,
# `[` among them though the wrapper spells it `test`: bash 3.2 in POSIX mode cannot unset a
# function named `[`, so a `[` written back into the wrapper would run an imported one. Read off a
# trace (`_names_the_wrapper_runs`), less the names a case below holds on its own: `python3`, which
# only a terminal can name, and `echo` and `true`, which only a fault reaches.
HELD_ON_THEIR_OWN = frozenset({"echo", "python3", "true"})


@pytest.mark.skipif(BASH_AS_SH is None, reason="no bash, the one shell that imports functions")
@pytest.mark.skipif(not ABSOLUTE_GIT, reason="no git at any of the absolute candidate paths")
def test_no_function_the_environment_exports_runs_in_place_of_a_builtin_of_the_wrappers(
    tmp_path: Path,
) -> None:
    # bash imports a function from every `BASH_FUNC_<name>%%` variable, as `/bin/sh` too, and a
    # function wins over a regular builtin, so an environment naming the clone's program in one
    # ran it inside the wrapper, past every guard, with no `PATH` entry at all. Measured on
    # macOS's `/bin/sh` before the wrapper unset them: `BASH_FUNC_pwd%%` ran the program five times
    # per hook, `BASH_FUNC_[%%` twenty-six, and the hook's answer was unchanged. Run inside a git
    # repository so the checkout listing reads lines, which is where `read` and `printf` run. The
    # names are the ones a trace of the wrapper shows it running.
    # Mutations (declared): `pwd` or `test` leaves the wrapper's unset list; a test is spelled `[`
    # again — each reddens this.
    builtins = (*sorted(_names_the_wrapper_runs(tmp_path / "traced") - HELD_ON_THEIR_OWN), "[")
    project = tmp_path / "project"
    project.mkdir()
    git(project, "init", "-q", home=tmp_path)
    plugin = _plugin_root(tmp_path, 0, echo_cwd=True)
    environment = _env(plugin, None, None)
    environment["CLAUDE_PROJECT_DIR"] = str(project)
    control = _run_under_bash(plugin, environment, project)
    # The walk first: a trace that stopped reading would export nothing but `[`.
    assert {"cd", "command", "printf", "pwd", "read", "test"} <= set(builtins), builtins
    exported, ran = _exported_functions(tmp_path, builtins)
    result = _run_under_bash(plugin, {**environment, **exported}, project)
    assert not ran.exists(), ran.read_text(encoding="utf-8")
    # Non-vacuous: the launcher ran, from the project root the containment entered, and the
    # answer is the one the wrapper gives with no function exported.
    assert control.returncode == 0, control.stderr
    assert control.stdout == f"{project.resolve()}\n"
    assert (result.returncode, result.stdout) == (control.returncode, control.stdout)


@pytest.mark.skipif(BASH_AS_SH is None, reason="no bash, the one shell that imports functions")
def test_no_function_the_environment_exports_stands_in_for_the_interpreter_the_wrapper_probes(
    tmp_path: Path,
) -> None:
    # `command -v python3` answers a function's bare name, and the wrapper then runs that name as
    # the probe and the launcher's interpreter. The containment cannot see it: a bare name is in
    # the current directory, so it is refused only where the wrapper entered a project root, and
    # here there is none. The list `python3` heads is one only a terminal can name, which is why
    # stdin is a pty; the built-in list reaches bare `python3` last, on a machine with no
    # interpreter at an absolute path. Mutation (declared): `python3` leaves the wrapper's unset
    # list — this reddens.
    plugin = _plugin_root(tmp_path, 0, echo_cwd=True)
    environment = _env(plugin, None, "python3")
    control = _run_under_bash(plugin, environment, plugin, terminal=True)
    exported, ran = _exported_functions(tmp_path, ("python3",))
    result = _run_under_bash(plugin, {**environment, **exported}, plugin, terminal=True)
    assert not ran.exists(), ran.read_text(encoding="utf-8")
    assert control.returncode == 0, control.stderr
    assert control.stdout == f"{plugin.resolve()}\n"
    assert (result.returncode, result.stdout) == (control.returncode, control.stdout)


@pytest.mark.skipif(BASH_AS_SH is None, reason="no bash, the one shell that imports functions")
def test_no_function_the_environment_exports_runs_in_place_of_what_the_wrapper_runs_on_a_fault(
    tmp_path: Path,
) -> None:
    # `echo` speaks only when the wrapper refuses or degrades, and `true` runs only when its
    # `git` names no root, so a hook that reaches its launcher never runs either and the case
    # above cannot see an imported one. Here `git` is asked outside any repository and the
    # launcher is missing, under `closed`: both run, and neither may be a function the
    # environment exported. Mutations (declared): `mutations/`'s "an exported function stands in
    # for the wrapper's echo again" and "an exported function stands in for the wrapper's true
    # again" -> the marker records the name.
    nowhere = tmp_path / "nowhere"
    nowhere.mkdir()
    plugin = _plugin_root(tmp_path, 0, with_launcher=False)
    environment = _env(plugin, None, None)
    control = _run_under_bash(plugin, environment, nowhere)
    exported, ran = _exported_functions(tmp_path, ("echo", "true"))
    result = _run_under_bash(plugin, {**environment, **exported}, nowhere)
    assert not ran.exists(), ran.read_text(encoding="utf-8")
    # Non-vacuous: the run refused, naming the fault, which is the `echo` this is about.
    assert control.returncode == 2, control.stderr
    assert "SF_NO_LAUNCHER" in control.stderr, control.stderr
    assert (result.returncode, result.stderr) == (control.returncode, control.stderr)
