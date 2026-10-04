from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from stayfixed.config.loader import CONFIG_FILE, load
from stayfixed.guards import bgcleanup
from stayfixed.guards.hooks import register
from stayfixed.hooks.api import EVENTS, Decision, Handler, HookEvent, Policy
from stayfixed.hooks.dispatch import Recorder, dispatch
from tests.floor import floor_env
from tests.gitfixture import git

ROOT = Path(__file__).resolve().parents[2]
CONFIG = """
[stayfixed]
version = "0.1.0"
state = "installed"
preset = "recommended"
profile = ""
agents = ["claude"]

[project]
name = "widget"
base_branch = "main"
release_branch = "main"
"""

LIST_IMPORTS = (
    "import sys\n"
    "from stayfixed.hooks.registry import discover\n"
    "names = [h.name for h in discover()]\n"
    "assert 'bg-cleanup' in names, names\n"
    "print(' '.join(sorted(m for m in sys.modules if m.startswith('stayfixed'))))\n"
)


def a_project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    root.mkdir()
    (root / CONFIG_FILE).write_text(CONFIG, encoding="utf-8")
    return root


def bash_event(
    root: Path, command: str, *, background: bool = True, tool: str = "Bash"
) -> HookEvent:
    tool_input: dict[str, object] = {"command": command}
    if background:
        tool_input["run_in_background"] = True
    return HookEvent(
        name="PreToolUse",
        session_id="s1",
        agent_id=None,
        tool_name=tool,
        tool_input=tool_input,
        cwd=root,
        project_root=root,
        harness="claude",
        raw={"tool_name": tool, "tool_input": tool_input},
    )


def guard() -> Handler:
    return next(h for h in register() if h.name == "bg-cleanup")


def test_every_handler_declares_a_known_event() -> None:
    handlers = register()
    assert handlers != []
    for handler in handlers:
        assert handler.event in EVENTS


def test_the_background_guard_is_the_closed_pre_tool_use_handler() -> None:
    # A guard for an action with a high cost of error fails closed. This is the only
    # CLOSED handler in the plugin, and the policy is the whole difference between "could not
    # judge" and "permitted".
    handler = guard()
    assert handler.event == "PreToolUse"
    assert handler.policy is Policy.CLOSED


def test_no_config_is_silence_for_every_handler(tmp_path: Path) -> None:
    # With no stayfixed.toml, no hook handler says anything. The guard included, by design.
    for handler in register():
        result = handler.run(bash_event(tmp_path, "sleep 300 &"), None)
        assert result.decision is None and result.context is None


def test_a_leaking_background_call_is_denied(tmp_path: Path) -> None:
    root = a_project(tmp_path)
    config = load(root, machine=tmp_path / "absent.toml")
    result = guard().run(bash_event(root, "python -m http.server 8000 &"), config)
    assert result.decision is Decision.DENY
    assert result.reason == bgcleanup.LEAK_REASON


def test_a_non_bash_tool_is_ignored(tmp_path: Path) -> None:
    # Carries `run_in_background: true` deliberately: without it the flag check would be what
    # stops this event, and the assertion would say nothing about `tool_name`.
    root = a_project(tmp_path)
    config = load(root, machine=tmp_path / "absent.toml")
    result = guard().run(bash_event(root, "sleep 300 &", tool="Edit"), config)
    assert result.decision is None


def test_a_trailing_restore_arrives_as_context_not_a_decision(tmp_path: Path) -> None:
    root = a_project(tmp_path)
    config = load(root, machine=tmp_path / "absent.toml")
    command = "cp a a.bak; sed -i '' 's/x/y/' a; pytest; cp a.bak a"
    result = guard().run(bash_event(root, command, background=False), config)
    assert result.decision is None
    assert result.context is not None and "trap" in result.context


def test_a_masking_echo_arrives_as_context_not_a_decision(tmp_path: Path) -> None:
    root = a_project(tmp_path)
    config = load(root, machine=tmp_path / "absent.toml")
    command = 'pytest -q > out.log 2>&1; echo "EXIT=$?" >> out.log'
    result = guard().run(bash_event(root, command, background=True), config)
    assert result.decision is None
    assert result.context is not None and "notification" in result.context


def test_a_guard_that_cannot_judge_refuses_rather_than_permits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The CLOSED policy, exercised through the real dispatcher: an exception inside the judge
    # is exit 2 with a reason, not an allow. Under Policy.OPEN this same call exits 0.
    def broken(command: str, *, background: bool) -> bgcleanup.Verdict:
        raise RuntimeError("boom")

    monkeypatch.setattr(bgcleanup, "judge", broken)
    root = a_project(tmp_path)
    config = load(root, machine=tmp_path / "absent.toml")
    recorder = Recorder()
    outcome = dispatch(bash_event(root, "ls"), register(), config, sink=recorder)
    assert outcome.exit_code == 2
    assert "bg-cleanup: RuntimeError: boom" in outcome.stderr
    assert recorder.records[0]["handler"] == "bg-cleanup"


def test_discovery_imports_no_guards_module_but_hooks(tmp_path: Path) -> None:
    # Every real import lives inside a handler body, so registering costs discovery nothing.
    completed = subprocess.run(
        [sys.executable, "-c", LIST_IMPORTS],
        capture_output=True,
        text=True,
        check=False,
        env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(ROOT / "src")},
    )
    assert completed.returncode == 0, completed.stderr
    imported = set(completed.stdout.split())
    assert "stayfixed.guards.hooks" in imported
    assert "stayfixed.guards.bgcleanup" not in imported
    assert "stayfixed.guards.bashscan" not in imported
    # The test-hygiene notice's modules, named explicitly: `hygiene` imports `bashscan` and
    # `gitenv` at module scope, so a module-level import of it in `hooks.py` would be caught by
    # the line above too — but only by accident of what it happens to import. The hints it asks
    # live in the profiles, which read configuration and data files.
    assert "stayfixed.guards.hygiene" not in imported
    assert "stayfixed.guards.roots" not in imported
    assert "stayfixed.profiles" not in imported
    assert "stayfixed.config" not in imported


def hook(event: str, stdin: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "stayfixed", "hook", event],
        input=stdin,
        capture_output=True,
        text=True,
        check=False,
        cwd=cwd,
        env={
            "PATH": "/usr/bin:/bin",
            "PYTHONPATH": str(ROOT / "src"),
            "CLAUDE_PROJECT_DIR": str(cwd),
            **floor_env(),
        },
    )


def test_a_leaking_background_call_is_denied_through_the_real_dispatcher(tmp_path: Path) -> None:
    # The production path end to end: stdin in, exit code out. This is what the wrapper runs.
    root = a_project(tmp_path)
    payload = {
        "hook_event_name": "PreToolUse",
        "session_id": "s",
        "cwd": str(root),
        "tool_name": "Bash",
        "tool_input": {"command": "sleep 300 & wait", "run_in_background": True},
    }
    completed = hook("PreToolUse", json.dumps(payload), root)
    assert completed.returncode == 2
    assert "refused: bg-cleanup:" in completed.stderr
    allowed = dict(payload, tool_input={"command": "make && make test", "run_in_background": True})
    completed = hook("PreToolUse", json.dumps(allowed), root)
    assert completed.returncode == 0, completed.stderr


needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")


def post_event(root: Path, command: str, raw_extra: dict[str, object]) -> HookEvent:
    tool_input: dict[str, object] = {"command": command}
    raw: dict[str, object] = {"tool_name": "Bash", "tool_input": tool_input, **raw_extra}
    return HookEvent(
        name="PostToolUse",
        session_id="s1",
        agent_id=None,
        tool_name="Bash",
        tool_input=tool_input,
        cwd=root,
        project_root=root,
        harness="claude",
        raw=raw,
    )


def dirty_project(tmp_path: Path) -> Path:
    # A tracked file modified after its commit, not merely an untracked one: the dirty count
    # comes from `git status --porcelain` under the owner's own git, and
    # `status.showUntrackedFiles = no` or a broad excludes file would hide an untracked file.
    root = a_project(tmp_path)
    (root / "src").mkdir()
    (root / "src" / "m.py").write_text("x = 1\n", encoding="utf-8")
    for args in (["init", "-q"], ["add", "-A"], ["commit", "-q", "-m", "chore: seed"]):
        git(root, *args, home=tmp_path)
    (root / "src" / "m.py").write_text("x = 2\n", encoding="utf-8")
    return root


def hygiene() -> Handler:
    return next(h for h in register() if h.name == "test-hygiene")


def test_the_hygiene_notice_is_an_open_post_tool_use_handler_with_a_once_key() -> None:
    # The policy is the whole of `test-hygiene`'s safety story: a notice that could refuse a
    # tool call would be worse than no notice. Reddened by flipping `Policy.OPEN` to
    # `Policy.CLOSED` in `register()`; measured. `once_key` is asserted against the literal
    # "test-hygiene" rather than against `ONCE_TEST_HYGIENE`, so the expected value is a fixed
    # one and not one read from the subject.
    handler = hygiene()
    assert handler.event == "PostToolUse"
    assert handler.policy is Policy.OPEN
    assert handler.once_key == "test-hygiene"


@needs_git
@pytest.mark.parametrize(
    "extra", [{"tool_response": {"exit_code": 1}}, {"error": "Exit code 1\nFAILED"}]
)
def test_a_red_pytest_over_a_dirty_tree_is_noticed(
    tmp_path: Path, extra: dict[str, object]
) -> None:
    # Both payload shapes through the handler, not only through `red_exit`: which field says a
    # run was red depends on what the harness actually sends, so the parametrisation has to
    # reach `event.raw`.
    # Reddened by mutating `_test_hygiene`'s last line to `return HookResult()`; measured.
    root = dirty_project(tmp_path)
    config = load(root, machine=tmp_path / "absent.toml")
    result = hygiene().run(post_event(root, "pytest -q", extra), config)
    assert result.decision is None
    assert result.context is not None and "uncommitted" in result.context


@needs_git
def test_a_green_run_or_a_non_pytest_command_is_silence(tmp_path: Path) -> None:
    # Reddened by dropping `_test_hygiene`'s `if red_exit(event.raw) is None: return
    # HookResult()` (the first assertion) and by dropping `context_for`'s `if not speaking:
    # return None` (the second); both measured.
    root = dirty_project(tmp_path)
    config = load(root, machine=tmp_path / "absent.toml")
    assert (
        hygiene()
        .run(post_event(root, "pytest -q", {"tool_response": {"stdout": "ok"}}), config)
        .context
        is None
    )
    assert (
        hygiene().run(post_event(root, "ls", {"tool_response": {"exit_code": 1}}), config).context
        is None
    )


@needs_git
def test_a_hygiene_failure_is_recorded_and_never_costs_the_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # OPEN: the dispatcher swallows and records. The handler does not need its own try/except,
    # and must not have one — a silent swallow is how a broken notice goes unnoticed. The
    # guards inside `context_for` are narrower: each costs one stack's line and nothing else,
    # and `tests/profiles/test_hints.py` pins them. Reddened by flipping the handler's policy
    # to `Policy.CLOSED` (exit 2, not 0); the stderr assertion is reddened by giving
    # `_test_hygiene` its own try/except around `context_for`.
    from stayfixed.guards import hygiene as module

    def broken(command: str, root: Path, config: object, hints: object) -> str | None:
        raise RuntimeError("boom")

    monkeypatch.setattr(module, "context_for", broken)
    root = dirty_project(tmp_path)
    config = load(root, machine=tmp_path / "absent.toml")
    recorder = Recorder()
    outcome = dispatch(
        post_event(root, "pytest", {"tool_response": {"exit_code": 1}}),
        register(),
        config,
        sink=recorder,
    )
    assert outcome.exit_code == 0
    assert "test-hygiene: RuntimeError: boom" in outcome.stderr


@needs_git
def test_an_unrelated_call_does_not_consume_the_one_delivery(tmp_path: Path) -> None:
    # The defect this pins: `dispatch` used to call `sink.mark(handler.once_key)` after EVERY
    # successful run, including one that returned an empty `HookResult`, so once a durable
    # sink exists the first unrelated Bash call of a session silently spends this handler's
    # single delivery.
    root = dirty_project(tmp_path)
    config = load(root, machine=tmp_path / "absent.toml")
    recorder = Recorder()
    dispatch(
        post_event(root, "ls", {"tool_response": {"stdout": ""}}), register(), config, sink=recorder
    )
    outcome = dispatch(
        post_event(root, "pytest", {"tool_response": {"exit_code": 1}}),
        register(),
        config,
        sink=recorder,
    )
    assert "uncommitted" in json.loads(outcome.stdout)["hookSpecificOutput"].get(
        "additionalContext", ""
    )
