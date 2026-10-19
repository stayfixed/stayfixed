from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import NamedTuple

import pytest

from stayfixed import __version__
from tests.gitfixture import git
from tests.ownerhome import plugin_root_with_owner_home, stayfixed_argv
from tests.scriptload import SCRIPTS, load
from tests.test_launcher import _old_python

ROOT = Path(__file__).resolve().parents[2]
WRAPPER = ROOT / "hooks" / "run-hook.sh"


def _plugin_root(
    base: Path, exit_code: int, *, echo_cwd: bool = False, with_launcher: bool = True
) -> Path:
    """A plugin root: a copy of the shipped wrapper, and a fake launcher beside it.

    The wrapper finds its launcher relative to its own path, so a plugin root is a real directory
    pair — `hooks/run-hook.sh` and `scripts/stayfixed` — which is what an installed plugin is. A
    fake launcher, because these cases are about the wrapper's exit mapping and its argv, and a
    real `stayfixed` run would couple them to every command in the package. With `echo_cwd` it
    prints the physical directory it runs in, which is what `Path.resolve()` names.
    """
    root = base / "plugin"
    (root / "scripts").mkdir(parents=True)
    (root / "hooks").mkdir(parents=True)
    shutil.copy(WRAPPER, root / "hooks" / WRAPPER.name)
    (root / "hooks" / WRAPPER.name).chmod(0o755)
    if not with_launcher:
        return root
    launcher = root / "scripts" / "stayfixed"
    body = "import os\n\nprint(os.getcwd())\n" if echo_cwd else ""
    launcher.write_text(
        f"#!/usr/bin/env python3\n{body}raise SystemExit({exit_code})\n", encoding="utf-8"
    )
    launcher.chmod(0o755)
    return root


def _python_on_path(base: Path, interpreter: str = sys.executable) -> str:
    """A `PATH` whose first `python3` runs `interpreter`, then this process's own `PATH`."""
    directory = base / "python-on-path"
    directory.mkdir(parents=True, exist_ok=True)
    shim = directory / "python3"
    shim.write_text(f'#!/bin/sh\nexec "{interpreter}" "$@"\n', encoding="utf-8")
    shim.chmod(0o755)
    return f"{directory}{os.pathsep}{os.environ.get('PATH', '')}"


def _run(
    *argv: str,
    plugin_root: Path,
    cwd: Path | None = None,
    project: Path | None = None,
    path: str | None = None,
    extra: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run the wrapper inside `plugin_root`, the way an installed plugin's entry does.

    `cwd` defaults to `plugin_root`, which is under `tmp_path` and is not a repository, so the
    wrapper's `git` names no project root unless a case gives it one. `path` defaults to this
    process's own, whose first `python3` under `uv run` is the suite's interpreter.
    """
    env = dict(os.environ)
    env.pop("CLAUDE_PLUGIN_ROOT", None)
    env.pop("CLAUDE_PROJECT_DIR", None)
    if project is not None:
        env["CLAUDE_PROJECT_DIR"] = str(project)
    if path is not None:
        env["PATH"] = path
    env.update(extra or {})
    return subprocess.run(
        [str(plugin_root / "hooks" / WRAPPER.name), *argv],
        capture_output=True,
        text=True,
        check=False,
        env=env,
        cwd=str(cwd if cwd is not None else plugin_root),
        stdin=subprocess.DEVNULL,
    )


def test_no_python3_on_path_degrades_open(tmp_path: Path) -> None:
    # A session never dies of its configuration: a machine with no `python3` gets one line on
    # stderr and an exit Claude Code reads as no objection.
    empty = tmp_path / "empty"
    empty.mkdir()
    result = _run("hook", "PreToolUse", plugin_root=_plugin_root(tmp_path, 0), path=str(empty))
    assert result.returncode == 0
    assert "no python3 on PATH" in result.stderr


def test_an_interpreter_below_the_floor_degrades_open(tmp_path: Path) -> None:
    # A real sub-floor interpreter rather than a fake that exits non-zero for every argument,
    # which could not exercise `sys.version_info` at all. Without the probe the launcher's own
    # floor check exits 2, which blocks every Bash call. `_old_python` is the tree's own seam,
    # and CI pins it through STAYFIXED_OLD_PYTHON so this runs there rather than skipping.
    old = _old_python()
    if old is None:
        pytest.skip("no interpreter below 3.11 on this machine; set STAYFIXED_OLD_PYTHON")
    result = _run(
        "hook",
        "PreToolUse",
        plugin_root=_plugin_root(tmp_path, 2),
        path=_python_on_path(tmp_path, old),
    )
    assert result.returncode == 0
    assert "is not python 3.11 or newer" in result.stderr


def test_an_interpreter_at_the_floor_is_accepted(tmp_path: Path) -> None:
    # The positive row: without it a probe that rejected everything would pass every case above.
    result = _run("hook", "PreToolUse", plugin_root=_plugin_root(tmp_path, 0))
    assert (result.returncode, result.stderr) == (0, "")


def test_a_missing_launcher_degrades_open(tmp_path: Path) -> None:
    # Without the check a missing launcher reaches Python as a missing script, which exits 2 by
    # CPython accident and blocks the call.
    result = _run("hook", "PreToolUse", plugin_root=_plugin_root(tmp_path, 0, with_launcher=False))
    assert result.returncode == 0
    assert "no readable launcher" in result.stderr


@pytest.mark.skipif(os.geteuid() == 0, reason="root reads a file at mode 000")
def test_a_launcher_that_cannot_be_read_degrades_open(tmp_path: Path) -> None:
    # `test -f` tests existence, not readability: a launcher at mode 000 reached CPython, which
    # printed its own "Permission denied" and exited 2.
    root = _plugin_root(tmp_path, 0)
    (root / "scripts" / "stayfixed").chmod(0o000)
    try:
        result = _run("hook", "PreToolUse", plugin_root=root)
    finally:
        (root / "scripts" / "stayfixed").chmod(0o755)
    assert result.returncode == 0
    assert "no readable launcher" in result.stderr


@pytest.mark.parametrize("rc", [1, 3, 126, 127])
def test_any_other_exit_code_degrades_open_and_says_so(tmp_path: Path, rc: int) -> None:
    result = _run("hook", "PreToolUse", plugin_root=_plugin_root(tmp_path, rc))
    assert result.returncode == 0
    assert f"stayfixed exited {rc}" in result.stderr


@pytest.mark.parametrize("rc", [0, 2])
def test_the_two_platform_codes_pass_through_untouched(tmp_path: Path, rc: int) -> None:
    result = _run("hook", "PreToolUse", plugin_root=_plugin_root(tmp_path, rc))
    assert result.returncode == rc
    assert "stayfixed:" not in result.stderr


def test_stayfixed_runs_from_the_project_root(tmp_path: Path) -> None:
    # Every hooks.json entry but the dispatcher's relies on `--root` defaulting to `.`, and the
    # harness does not promise to launch a hook in the project. The wrapper changes into
    # CLAUDE_PROJECT_DIR, else git's toplevel, so one rule serves every entry.
    project = tmp_path / "project"
    (project / ".git").mkdir(parents=True)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    result = _run(
        "memory",
        "session-context",
        "--bundle",
        "standing-rules",
        plugin_root=_plugin_root(tmp_path, 0, echo_cwd=True),
        cwd=elsewhere,
        project=project,
    )
    assert result.stdout.strip() == str(project.resolve())


def test_the_project_root_is_never_taken_from_an_inherited_git_environment(tmp_path: Path) -> None:
    # `cd repoA` with GIT_DIR/GIT_WORK_TREE naming repoB put the launcher in repoB, so the whole
    # hook read another repository's stayfixed.toml, budgets and note store. The Codex path,
    # where CLAUDE_PROJECT_DIR is unset.
    here, there = tmp_path / "here", tmp_path / "there"
    for repository in (here, there):
        repository.mkdir()
        git(repository, "init", "-q")
    result = _run(
        "hook",
        "PreToolUse",
        plugin_root=_plugin_root(tmp_path, 0, echo_cwd=True),
        cwd=here,
        extra={"GIT_DIR": str(there / ".git"), "GIT_WORK_TREE": str(there)},
    )
    assert result.stdout.strip() == str(here.resolve())


def test_a_project_root_that_cannot_be_entered_says_so(tmp_path: Path) -> None:
    # A root that was named and cannot be entered left the process in the harness's directory,
    # and if that was another stayfixed project every `--root`-defaulting entry read its
    # configuration, with nothing said.
    result = _run(
        "hook",
        "PreToolUse",
        plugin_root=_plugin_root(tmp_path, 0, echo_cwd=True),
        cwd=tmp_path,
        project=tmp_path / "not-on-disk",
    )
    assert result.returncode == 0
    assert "cannot enter the project root" in result.stderr
    # Non-vacuous: the launcher was not reached at all, which would have printed a directory.
    assert result.stdout == ""


def test_a_cdpath_never_chooses_the_directory_the_hook_runs_in(tmp_path: Path) -> None:
    # With `CDPATH` set and a relative root, `cd` writes the destination it chose to stdout, ahead
    # of anything the launcher prints, and a hook's stdout is a contract the harness parses.
    decoy = tmp_path / "decoy-parent" / "target"
    decoy.mkdir(parents=True)
    real = tmp_path / "real-parent" / "target"
    real.mkdir(parents=True)
    result = _run(
        "hook",
        "PreToolUse",
        plugin_root=_plugin_root(tmp_path, 0, echo_cwd=True),
        project=Path("target"),
        cwd=real.parent,
        extra={"CDPATH": str(decoy.parent)},
    )
    # Exactly one line, so nothing was written ahead of the launcher, and the real tree.
    assert result.stdout.splitlines() == [str(real.resolve())]


def test_a_project_root_whose_name_begins_with_a_dash_is_a_destination_and_not_an_option(
    tmp_path: Path,
) -> None:
    dashed = tmp_path / "parent" / "-dashed"
    dashed.mkdir(parents=True)
    result = _run(
        "hook",
        "PreToolUse",
        plugin_root=_plugin_root(tmp_path, 0, echo_cwd=True),
        project=Path("-dashed"),
        cwd=dashed.parent,
    )
    assert result.stdout.splitlines() == [str(dashed.resolve())]


def test_the_wrapper_is_committed_executable() -> None:
    # A 0644 wrapper is never executed, so no code of ours runs; this assertion and `doctor`'s
    # wrapper probe are the whole defence.
    assert stat.S_IMODE(WRAPPER.stat().st_mode) & 0o111, "run-hook.sh must ship executable"


class Planting(NamedTuple):
    """A module planted where an interpreter started without `-I` imports it at startup, the
    variables that make it so, and the file it appends to each time it runs."""

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
    was made from. Outside a venv it is `sys.executable`, as is the fallback.
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
    # A developer's `PYTHONPATH` or user site would otherwise be imported before the launcher's
    # first line, once for the version probe and once for the launcher. Reddens on either `-I`
    # removed, which is two entries in `mutations/`. The shipped wrapper and launcher, run in
    # place: the other half of this case is that the real launcher still finds its own `src`
    # under `-I`. Run from `tmp_path`, outside every repository.
    planting = case(tmp_path)
    # Non-vacuous: the planting does run in an interpreter started without `-I`.
    subprocess.run(
        [planting.interpreter, "-c", "pass"],
        check=True,
        env=dict(os.environ, **planting.env),
        cwd=tmp_path,
    )
    assert planting.record.read_text(encoding="utf-8") == "['-c']\n"
    planting.record.unlink()
    result = _run(
        "--version",
        plugin_root=ROOT,
        cwd=tmp_path,
        path=_python_on_path(tmp_path, planting.interpreter),
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
    # The approval is a person's, at a terminal (`scripts/ptyrun.py`).
    code, said = load(SCRIPTS / "ptyrun.py", "ptyrun_for_wrapper_tests").run_in_pty(
        [*stayfixed_argv(owner), "trust", "approve", "memory", "--root", str(project)],
        env=dict(os.environ, HOME=str(owner)),
    )
    assert code == 0, said
    owners = owner / ".config" / "stayfixed" / "trust.json"
    planted = project / "fakehome" / ".config" / "stayfixed" / "trust.json"
    planted.parent.mkdir(parents=True)
    owners.rename(planted)
    home = "fakehome" if spelling == "relative" else str(project / "fakehome")
    argv = ["memory", "session-context", "--bundle", "standing-rules", "--part", "1"]

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
