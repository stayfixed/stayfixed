"""The red-run hint: the core names the dirty tree, and the profile whose runner failed adds its own
advice, chosen by the command and never by `[stayfixed] profile`."""

from __future__ import annotations

import json
import os
import py_compile
import shutil
import sys
import time
import types
from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest

from stayfixed.config.loader import CONFIG_FILE, load
from stayfixed.config.schema import Config
from stayfixed.guards.hooks import register
from stayfixed.hooks.api import Handler, HookEvent
from stayfixed.hooks.dispatch import Recorder, dispatch
from stayfixed.profiles.python.hygiene import HINT
from tests.gitfixture import git
from tests.guards.test_commands import invoke

needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")

# `profile = ""` on purpose: the note is chosen by the command that failed, so a repository that
# names no profile, or names one stack while running another's tests, still gets the right advice.
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

[ledger]
code_roots = ["src"]
"""

RED = {"tool_response": {"exit_code": 1}}

# The notice as the code before the move rendered it, captured from that code with one
# uncommitted change and one stale `.pyc` and pasted here, never derived from the code under test.
# A repository in Python must read exactly what it read before its advice moved into the profile.
LEAD = "Before calling this red a flake, pre-existing, or caused by the branch:"
DIRTY_ONE = (
    "1 uncommitted change(s) in the tree -- this run measured a tree nobody is merging. "
    "A stashed-baseline A/B cannot see this: both halves run in it."
)
STALE_TWO = (
    "2 .pyc file(s) whose recorded source mtime no longer matches their source, under the "
    "configured code roots -- the interpreter may be importing a build that predates a fix on "
    "disk, which fails DETERMINISTICALLY in the shape of the defect the test pins. Delete the "
    "`__pycache__` directories under those roots, then re-run before attributing anything."
)
STALE_ONE = STALE_TWO.replace("2 .pyc", "1 .pyc", 1)


def hygiene() -> Handler:
    return next(h for h in register() if h.name == "test-hygiene")


def red_event(root: Path, command: str) -> HookEvent:
    tool_input: dict[str, object] = {"command": command}
    return HookEvent(
        name="PostToolUse",
        session_id="s1",
        agent_id=None,
        tool_name="Bash",
        tool_input=tool_input,
        cwd=root,
        project_root=root,
        harness="claude",
        raw={"tool_name": "Bash", "tool_input": tool_input, **RED},
    )


def config_of(root: Path) -> Config:
    return load(root, machine=root.parent / "absent.toml")


def faulty_python_tree(tmp_path: Path) -> Path:
    """A committed tree with one uncommitted change and one stale `.pyc`.

    The bytecode directory is ignored by a committed `.gitignore`, so it is never itself counted
    as uncommitted, and the one change is a tracked file modified after its commit: the dirty
    count runs under the owner's own git, whose `status.showUntrackedFiles` could hide an
    untracked file and make the count depend on the machine.
    """
    root = tmp_path / "repo"
    (root / "src").mkdir(parents=True)
    module = root / "src" / "mod.py"
    module.write_text("x = 1\n", encoding="utf-8")
    (root / "notes.txt").write_text("a\n", encoding="utf-8")
    (root / ".gitignore").write_text("__pycache__/\n", encoding="utf-8")
    (root / CONFIG_FILE).write_text(CONFIG, encoding="utf-8")
    git(root, "init", "-q", "-b", "main")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "chore: seed")
    # Explicit `cfile` and `TIMESTAMP`: `cfile=None` follows `PYTHONPYCACHEPREFIX` out of the
    # fixture, and `SOURCE_DATE_EPOCH` would make the header hash-based, which is never judged.
    py_compile.compile(
        str(module),
        cfile=str(module.parent / "__pycache__" / f"mod.{sys.implementation.cache_tag}.pyc"),
        doraise=True,
        invalidation_mode=py_compile.PycInvalidationMode.TIMESTAMP,
    )
    future = time.time() + 60
    os.utime(module, (future, future))
    (root / "notes.txt").write_text("b\n", encoding="utf-8")
    return root


@needs_git
def test_a_red_pytest_run_gets_the_python_profiles_note(tmp_path: Path) -> None:
    # The everyday case end to end through the handler: a failed pytest over a dirty tree with
    # stale bytecode gets the core's dirty-tree line and then the Python profile's line, in the
    # words the notice carried before the move. Reddened by handing `context_for` no hints in
    # `_test_hygiene` (`shipped_hints()` replaced by `()`, so no profile speaks); measured.
    root = faulty_python_tree(tmp_path)
    result = hygiene().run(red_event(root, "uv run pytest -q"), config_of(root))
    assert result.decision is None
    assert result.context == f"{LEAD}\n- {DIRTY_ONE}\n- {STALE_ONE}"


@needs_git
def test_no_recognising_profile_means_no_notice(tmp_path: Path) -> None:
    # A red `cargo test` over the same faulty tree: no shipped profile recognises the runner, so
    # nothing is said -- not even the dirty-tree line. The core cannot tell a failed test run
    # from any other failed command, and the notice is once per context: a dirty-tree line after
    # a failed `grep` would spend the one delivery the next failed test run needed. The Python
    # tree's stale `.pyc` is what makes this non-vacuous: a Python hint that answered for every
    # command would put both lines here. Oracle: `mutations/`, "the Python hint recognises every
    # command".
    root = faulty_python_tree(tmp_path)
    config = config_of(root)
    assert hygiene().run(red_event(root, "cargo test"), config).context is None
    assert hygiene().run(red_event(root, "pytest"), config).context is not None


class FakeHint:
    """A hint for one runner, whose report and note are fixed, and which can be told to raise.
    A `note` of `None` is a hint with nothing to say."""

    def __init__(self, runner: str, note: str | None, *, raises_in: str = "") -> None:
        self.runner = runner
        self.said = note
        self.raises_in = raises_in

    def _maybe_raise(self, where: str) -> None:
        if self.raises_in == where:
            raise RuntimeError(f"{self.runner} broke in {where}")

    def recognises(self, argv: Sequence[str]) -> bool:
        self._maybe_raise("recognises")
        return argv[0] == self.runner

    def report(self, root: Path, config: Config) -> Mapping[str, int]:
        self._maybe_raise("report")
        return {"found": 1}

    def note(self, counts: Mapping[str, int]) -> str | None:
        self._maybe_raise("note")
        if self.said is None:
            return None
        return f"{self.said} ({counts['found']})"


def ship(monkeypatch: pytest.MonkeyPatch, hints: dict[str, FakeHint]) -> None:
    """Replace the shipped hints with `hints`, through the seam `shipped_hints` reads from.

    The modules go into `sys.modules` under the names `shipped_hints` imports, so the import
    path the handler takes in production is the one this exercises.
    """
    for name, hint in hints.items():
        module = types.ModuleType(f"stayfixed.profiles.{name}.hygiene")
        module.HINT = hint  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, module.__name__, module)
    monkeypatch.setattr("stayfixed.profiles.hints.hint_modules", lambda: tuple(sorted(hints)))


def a_project(tmp_path: Path) -> Path:
    # Not a git repository, so the dirty count is "could not answer" and adds no line: what is
    # left is exactly what the hints said.
    root = tmp_path / "project"
    root.mkdir()
    (root / CONFIG_FILE).write_text(CONFIG, encoding="utf-8")
    return root


def test_two_recognising_hints_both_speak(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # A repository in two stacks runs both suites in one command; each stack whose runner
    # failed gets its own line, in name order, and a third whose runner did not run says
    # nothing. Oracle: `mutations/`, "only the first recognising hint speaks".
    ship(
        monkeypatch,
        {
            "alpha": FakeHint("alpha-test", "alpha says"),
            "beta": FakeHint("beta-test", "beta says"),
            "gamma": FakeHint("gamma-test", "gamma says"),
        },
    )
    root = a_project(tmp_path)
    result = hygiene().run(red_event(root, "alpha-test && beta-test"), config_of(root))
    assert result.context == f"{LEAD}\n- alpha says (1)\n- beta says (1)"


def test_a_hint_that_raises_costs_its_note_not_the_dispatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # One stack's broken hint must cost that stack's line and nothing else: not the other
    # stacks' lines, and not the handler, whose failure under `Policy.OPEN` the dispatcher would
    # record and swallow whole. Through the real dispatcher, so "nothing else" includes stderr.
    # Oracle: `mutations/`, "a hint's note is computed outside its guard" and "a hint's
    # recognition is asked outside its guard".
    ship(
        monkeypatch,
        {
            "alpha": FakeHint("x", "alpha says", raises_in="recognises"),
            "beta": FakeHint("x", "beta says", raises_in="report"),
            "delta": FakeHint("x", "delta says", raises_in="note"),
            "gamma": FakeHint("x", "gamma says"),
        },
    )
    root = a_project(tmp_path)
    outcome = dispatch(red_event(root, "x"), register(), config_of(root), sink=Recorder())
    assert outcome.exit_code == 0
    assert outcome.stderr == ""
    answer = json.loads(outcome.stdout)["hookSpecificOutput"]
    assert answer["additionalContext"] == f"{LEAD}\n- gamma says (1)"


class WordlessHint(FakeHint):
    """A hint whose note is something other than text, which the protocol does not allow."""

    def note(self, counts: Mapping[str, int]) -> str | None:
        return ["a", "list"]  # type: ignore[return-value]


@needs_git
def test_a_hint_that_cannot_load_or_gives_no_text_costs_only_its_own_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The per-hint guards cover recognising, reporting and noting; a profile's module that does
    # not import, one that has no `HINT`, and a note that is not text sit outside them unless
    # they are handled on their own. Each must cost that profile's line and nothing else: the
    # dirty-tree line and every other stack's line stay. Through the real dispatcher, so
    # "nothing else" includes stderr. Oracle: `mutations/`, "a hint module is imported outside
    # its guard" and "a note that is not text passes as one".
    ship(
        monkeypatch,
        {"delta": WordlessHint("x", "delta says"), "gamma": FakeHint("x", "gamma says")},
    )
    # `alpha` has no module at all, and `beta`'s module defines no `HINT`.
    beta = types.ModuleType("stayfixed.profiles.beta.hygiene")
    monkeypatch.setitem(sys.modules, beta.__name__, beta)
    monkeypatch.setattr(
        "stayfixed.profiles.hints.hint_modules", lambda: ("alpha", "beta", "delta", "gamma")
    )
    root = faulty_python_tree(tmp_path)
    outcome = dispatch(red_event(root, "x"), register(), config_of(root), sink=Recorder())
    assert outcome.exit_code == 0
    assert outcome.stderr == ""
    answer = json.loads(outcome.stdout)["hookSpecificOutput"]
    assert answer["additionalContext"] == f"{LEAD}\n- {DIRTY_ONE}\n- gamma says (1)"


class EmptyHint(FakeHint):
    """A hint whose note is the empty string: text, with nothing in it."""

    def note(self, counts: Mapping[str, int]) -> str | None:
        return ""


class LoudHint(FakeHint):
    """A hint whose report carries more than counts, and which keeps what its note was given."""

    def __init__(self, runner: str, note: str) -> None:
        super().__init__(runner, note)
        self.returned: dict[object, object] = {}
        self.given: object = None

    def report(self, root: Path, config: Config) -> Mapping[str, int]:
        self.returned = {
            "found": 1,
            "path": str(root),
            "flag": True,
            "ratio": 0.5,
            7: 3,
            str(root / "notes.txt"): 2,
        }
        return self.returned  # type: ignore[return-value]

    def note(self, counts: Mapping[str, int]) -> str | None:
        self.given = counts
        return super().note(counts)


def test_a_note_is_handed_counts_and_nothing_else(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The trust rule for a hint's line holds because `note` is handed counts and nothing else,
    # so the core hands it a fresh mapping of count names to plain integers, whatever `report`
    # returned: a path, a boolean (an `int` to Python), a float, a non-string key and a key shaped
    # like a path are dropped before the hint renders anything, and the hint never sees the very
    # object it returned. A key is text too, and one a hint built from the tree it walked would
    # carry that tree's names into `note` and into `stayfixed test hygiene --json`. Oracle:
    # `mutations/`, "a hint's note is handed its report as returned" and "a count keeps any
    # string for its name".
    loud = LoudHint("x", "loud says")
    ship(monkeypatch, {"alpha": loud})
    root = a_project(tmp_path)
    result = hygiene().run(red_event(root, "x"), config_of(root))
    assert result.context == f"{LEAD}\n- loud says (1)"
    assert loud.given == {"found": 1}
    assert loud.given is not loud.returned


@needs_git
def test_test_hygiene_reports_a_repository_in_two_stacks_as_two_entries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # `[stayfixed] profile` names one stack; a repository written in two gets both stacks'
    # counts, each under its profile's name, and only counts: the report that carried a path
    # reaches `--json` as its integers alone. `beta` has nothing to say, so it is listed only
    # because detection, replaced here, puts its markers at the root: its entry is the proof that
    # detection was asked. Oracle: `mutations/`, "test hygiene reports the first stack and
    # stops", "test hygiene prints a report as the hint returned it" and "test hygiene lists
    # only the profiles with something to say".
    ship(monkeypatch, {"alpha": LoudHint("x", "alpha says"), "beta": FakeHint("y", None)})
    detected_everywhere(monkeypatch)
    root = committed_project(tmp_path)
    argv = ["test", "hygiene", "--root", str(root), "--machine", str(tmp_path / "m.toml"), "--json"]
    assert invoke(argv) == 1
    out = json.loads(capsys.readouterr().out)
    assert out["dirty"] == 0
    assert out["profiles"] == {"alpha": {"found": 1}, "beta": {"found": 1}}
    assert out["summary"] == "alpha: alpha says (1)"


@needs_git
def test_test_hygiene_names_every_detected_stack_that_has_nothing_to_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # A clean tree in two stacks says so for each of them, in name order, and exits 0: the
    # summary is what tells a person which stacks were looked at. Oracle: `mutations/`, "test
    # hygiene's clean summary names only the first stack".
    ship(monkeypatch, {"alpha": FakeHint("x", None), "beta": FakeHint("y", None)})
    detected_everywhere(monkeypatch)
    root = committed_project(tmp_path)
    argv = ["test", "hygiene", "--root", str(root), "--machine", str(tmp_path / "m.toml"), "--json"]
    assert invoke(argv) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["profiles"] == {"alpha": {"found": 1}, "beta": {"found": 1}}
    assert out["summary"] == (
        "tree is clean; the alpha profile has nothing to report; "
        "the beta profile has nothing to report"
    )


@needs_git
@pytest.mark.parametrize("broken", ["absent", "no-hint"])
def test_test_hygiene_refuses_when_a_shipped_hint_cannot_load(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    broken: str,
) -> None:
    # The hook leaves out a profile whose `hygiene.py` does not import or has no `HINT`, so one
    # stack's broken module costs only its own line. This command answers whether a red run can
    # be trusted, and a profile it could not ask is "I do not know", never "tree is clean": it
    # refuses (exit 2) and names the profile, a shipped name. `gamma` loads and has nothing to
    # say, so without the refusal the answer would be clean. Oracle: `mutations/`, "test hygiene
    # calls a tree clean without a hint it could not load".
    ship(monkeypatch, {"gamma": FakeHint("x", None)})
    if broken == "no-hint":
        alpha = types.ModuleType("stayfixed.profiles.alpha.hygiene")
        monkeypatch.setitem(sys.modules, alpha.__name__, alpha)
    monkeypatch.setattr("stayfixed.profiles.hints.hint_modules", lambda: ("alpha", "gamma"))
    detected_everywhere(monkeypatch)
    root = committed_project(tmp_path)
    argv = ["test", "hygiene", "--root", str(root), "--machine", str(tmp_path / "m.toml")]
    assert invoke(argv) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "the alpha profile's red-run hint could not be loaded" in captured.err


@needs_git
def test_test_hygiene_refuses_a_note_that_is_not_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # The hook drops a note that is not text and keeps the rest of its notice. This command
    # answers whether a red run can be trusted, and a hint that answered outside its protocol is
    # "I do not know", never "tree is clean" and never a finding printed as whatever the object
    # renders to: it refuses (exit 2) and names the profile, as for a hint that did not load.
    # Oracle: `mutations/`, "a note that is not text passes as one".
    ship(monkeypatch, {"alpha": WordlessHint("x", "alpha says")})
    monkeypatch.setattr("stayfixed.profiles.load_profile", lambda name: name)
    monkeypatch.setattr("stayfixed.profiles.detects", lambda profile, root: False)
    root = committed_project(tmp_path)
    argv = ["test", "hygiene", "--root", str(root), "--machine", str(tmp_path / "m.toml")]
    assert invoke(argv) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "the alpha profile's red-run hint answered in something other than text" in captured.err


@needs_git
def test_test_hygiene_does_not_list_an_undetected_stack_whose_note_is_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # An empty note is text with nothing in it: nothing to report, the same answer the hook
    # gives by leaving the line out. So a stack whose markers are not at the root and whose note
    # is "" is not listed, and the tree reads clean. Oracle: `mutations/`, "an empty note is
    # something to report".
    ship(monkeypatch, {"alpha": EmptyHint("x", "alpha says")})
    monkeypatch.setattr("stayfixed.profiles.load_profile", lambda name: name)
    monkeypatch.setattr("stayfixed.profiles.detects", lambda profile, root: False)
    root = committed_project(tmp_path)
    argv = ["test", "hygiene", "--root", str(root), "--machine", str(tmp_path / "m.toml"), "--json"]
    assert invoke(argv) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["profiles"] == {}
    assert out["summary"] == "tree is clean"


def detected_everywhere(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every shipped profile's markers sit at the root, whatever the tree holds."""
    monkeypatch.setattr("stayfixed.profiles.load_profile", lambda name: name)
    monkeypatch.setattr("stayfixed.profiles.detects", lambda profile, root: True)


def committed_project(tmp_path: Path) -> Path:
    """A repository whose one file, its configuration, is committed: a clean tree."""
    root = tmp_path / "repo"
    root.mkdir()
    (root / CONFIG_FILE).write_text(CONFIG, encoding="utf-8")
    git(root, "init", "-q", "-b", "main")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "chore: seed")
    return root


def test_the_note_is_a_function_of_the_report() -> None:
    # `note` sees counts and nothing else, so no path, file name or command text a repository
    # authored can reach the line it renders. Pinned against the literal captured from the code
    # before the move. Reddened by changing `STALE`'s wording in
    # `src/stayfixed/profiles/python/hygiene.py`; measured. The second assertion is the silence:
    # a tree with nothing stale gets no Python line at all. Reddened by dropping `note`'s
    # `if not stale: return None`; measured.
    assert HINT.note({"stale": 2, "roots": 1}) == STALE_TWO
    assert HINT.note({"stale": 0, "roots": 3}) is None
