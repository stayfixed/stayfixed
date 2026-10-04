from __future__ import annotations

import io
import json
import shutil
import sys
import types
from pathlib import Path

import pytest

from stayfixed.cli import build_parser, discover_registrars, run
from stayfixed.findings import LISTED_LIMIT
from tests.gitfixture import git
from tests.profiles import redrun
from tests.profiles.python.bytecode import compile_module, make_stale


def invoke(argv: list[str]) -> int:
    return run(argv, parser=build_parser(discover_registrars()))


def feed(monkeypatch: pytest.MonkeyPatch, text: str) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO(text))


def test_guard_bg_cleanup_refuses_a_leaking_payload(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    payload = {"tool_input": {"command": "sleep 300 & wait", "run_in_background": True}}
    feed(monkeypatch, json.dumps(payload))
    assert invoke(["guard", "bg-cleanup"]) == 2
    assert "refused:" in capsys.readouterr().err


def test_guard_bg_cleanup_accepts_a_bare_tool_input(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    feed(monkeypatch, json.dumps({"command": "make && make test", "run_in_background": True}))
    assert invoke(["guard", "bg-cleanup"]) == 0
    assert "no background leak" in capsys.readouterr().out


def test_guard_bg_cleanup_reports_a_restore_hint_as_a_finding(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    feed(monkeypatch, json.dumps({"command": "cp a a.bak; pytest; cp a.bak a"}))
    assert invoke(["guard", "bg-cleanup", "--json"]) == 1
    assert "trap" in json.loads(capsys.readouterr().out)["hint"]


def test_guard_bg_cleanup_passes_a_payload_for_another_tool_like_the_handler_does(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    payload = {"tool_name": "Edit", "tool_input": {"file_path": "x", "run_in_background": True}}
    feed(monkeypatch, json.dumps(payload))
    assert invoke(["guard", "bg-cleanup"]) == 0
    assert "not a Bash call" in capsys.readouterr().out


@pytest.mark.parametrize("stdin", ["not json at all", "[1, 2]", '{"tool_input": "x"}', "{}"])
def test_guard_bg_cleanup_refuses_what_it_cannot_read(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], stdin: str
) -> None:
    # Fail-closed: a guard that cannot read its input must not answer "allowed".
    feed(monkeypatch, stdin)
    assert invoke(["guard", "bg-cleanup"]) == 2
    assert "refused" in capsys.readouterr().err


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

needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")


def repo(tmp_path: Path, *messages: str) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    (root / "stayfixed.toml").write_text(CONFIG, encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "chore: seed")
    git(root, "tag", "base")
    for index, message in enumerate(messages):
        (root / f"f{index}.txt").write_text("x\n", encoding="utf-8")
        git(root, "add", "-A")
        git(root, "commit", "-q", "-m", message)
    return root


@needs_git
def test_commit_check_passes_a_clean_range(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = repo(tmp_path, "feat: one", "fix(x): two")
    argv = [
        "commit",
        "check",
        "--range",
        "base..HEAD",
        "--root",
        str(root),
        "--machine",
        str(tmp_path / "m.toml"),
    ]
    assert invoke(argv) == 0
    assert "OK: 2 commit message(s) checked" in capsys.readouterr().out


@needs_git
def test_commit_check_names_the_offence_not_the_text(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = repo(tmp_path, "fix: dirty\n\nCo-Authored-By: Claude <noreply@anthropic.com>\n")
    argv = [
        "commit",
        "check",
        "--range",
        "base..HEAD",
        "--root",
        str(root),
        "--machine",
        str(tmp_path / "m.toml"),
        "--json",
    ]
    assert invoke(argv) == 1
    out = json.loads(capsys.readouterr().out)
    assert out["violations"][0]["offences"] == [
        {"line": 3, "label": "attribution trailer naming an AI tool"}
    ]
    assert "noreply@anthropic.com" not in json.dumps(out)


@needs_git
def test_commit_check_refuses_a_range_git_cannot_read(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = repo(tmp_path)
    argv = [
        "commit",
        "check",
        "--range",
        "nope..HEAD",
        "--root",
        str(root),
        "--machine",
        str(tmp_path / "m.toml"),
    ]
    assert invoke(argv) == 2
    assert "refused" in capsys.readouterr().err


def test_commit_strip_rewrites_the_file_in_place(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    message = tmp_path / "COMMIT_EDITMSG"
    message.write_text(
        "fix: thing\n\nCo-Authored-By: Claude <noreply@anthropic.com>\n", encoding="utf-8"
    )
    assert invoke(["commit", "strip", str(message)]) == 0
    assert message.read_text(encoding="utf-8") == "fix: thing\n"
    assert "stripped 1" in capsys.readouterr().out


def test_commit_strip_leaves_a_message_that_is_only_attribution(tmp_path: Path) -> None:
    # Emptying it would abort the commit with a confusing "empty message"; CI explains instead.
    message = tmp_path / "COMMIT_EDITMSG"
    original = "Co-Authored-By: Claude <noreply@anthropic.com>\n"
    message.write_text(original, encoding="utf-8")
    assert invoke(["commit", "strip", str(message)]) == 0
    assert message.read_text(encoding="utf-8") == original


def test_commit_strip_keeps_the_files_mode(tmp_path: Path) -> None:
    message = tmp_path / "COMMIT_EDITMSG"
    message.write_text("fix: t\n\nGenerated with Codex\n", encoding="utf-8")
    message.chmod(0o640)
    assert invoke(["commit", "strip", str(message)]) == 0
    assert (message.stat().st_mode & 0o777) == 0o640


def test_commit_strip_never_writes_through_a_symlink(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    real = tmp_path / "real.txt"
    real.write_text("fix: t\n\nGenerated with Codex\n", encoding="utf-8")
    link = tmp_path / "COMMIT_EDITMSG"
    link.symlink_to(real)
    assert invoke(["commit", "strip", str(link)]) == 2
    # `write_atomically` replaces the *link* with a regular file rather than following it, so
    # the target is untouched with or without the guard; what the guard preserves is the link.
    assert link.is_symlink()


def test_commit_strip_reports_a_message_file_that_is_not_utf_8_as_a_failure(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # `except OSError` does not catch `UnicodeDecodeError`, so a legitimately non-UTF-8 message
    # file (git has `i18n.commitEncoding` for exactly this) reached the CLI frame as
    # `internal error: UnicodeDecodeError` and exit 2 — the code this project's callers are told
    # never to read as permission. It is a file the command cannot read, like the `OSError`
    # beside it, so it is exit 1. Both assertions matter: the exit code, and that the offending
    # byte the exception names does not travel into the message.
    message = tmp_path / "COMMIT_EDITMSG"
    message.write_bytes("fix: thing\n\nCo-Authored-By: Claude\n".encode("cp1251") + b"\xff\xfe")
    assert invoke(["commit", "strip", str(message)]) == 1
    err = capsys.readouterr().err
    assert "UnicodeDecodeError" not in err
    assert "0xff" not in err


def test_commit_strip_refuses_an_option_shaped_path() -> None:
    assert invoke(["commit", "strip", "--", "-weird"]) == 2


def test_commit_strip_keeps_gits_trailing_comment_block_intact(tmp_path: Path) -> None:
    # A realistic `prepare-commit-msg` file — subject, blank, an attribution trailer,
    # then git's own comment block (`core.commentChar` default `#`). `offending_lines` judges
    # only the message's *trailing attribution block* (commit.py's docstring), and in this file
    # the last paragraph is git's comment block, which is not attribution and therefore ends
    # that block where it starts — so a strip that does not split the comment block off first
    # would no-op here, on exactly the path the hook exists for.
    message = tmp_path / "COMMIT_EDITMSG"
    message.write_text(
        "fix: thing\n"
        "\n"
        "Co-Authored-By: Claude <noreply@anthropic.com>\n"
        "\n"
        "# Please enter the commit message for your changes. Lines starting\n"
        "# with '#' will be ignored, and an empty message aborts the commit.\n"
        "#\n"
        "# On branch main\n"
        "# Changes to be committed:\n"
        "#\tnew file:   widget.py\n"
        "#\n",
        encoding="utf-8",
    )
    assert invoke(["commit", "strip", str(message)]) == 0
    result = message.read_text(encoding="utf-8")
    assert result == (
        "fix: thing\n"
        "\n"
        "# Please enter the commit message for your changes. Lines starting\n"
        "# with '#' will be ignored, and an empty message aborts the commit.\n"
        "#\n"
        "# On branch main\n"
        "# Changes to be committed:\n"
        "#\tnew file:   widget.py\n"
        "#\n"
    )
    assert "Co-Authored-By" not in result


# Everything git appends below the message under `commit.verbose = true`, captured from a real
# `prepare-commit-msg` hook in a repository with the key set, and retyped. Kept separate from the
# message above it so the assertion that it comes back byte for byte is against a fixed literal.
VERBOSE_TAIL = (
    "\n"
    "# Please enter the commit message for your changes. Lines starting\n"
    "# with '#' will be ignored, and an empty message aborts the commit.\n"
    "#\n"
    "# On branch main\n"
    "# Changes to be committed:\n"
    "#\tmodified:   a.txt\n"
    "#\n"
    "# ------------------------ >8 ------------------------\n"
    "# Do not modify or remove the line above.\n"
    "# Everything below it will be ignored.\n"
    "diff --git a/a.txt b/a.txt\n"
    "index 4cb29ea..6addb9b 100644\n"
    "--- a/a.txt\n"
    "+++ b/a.txt\n"
    "@@ -1,3 +1,4 @@\n"
    " one\n"
    "-two\n"
    "+TWO\n"
    " three\n"
    "+four\n"
)
VERBOSE_EDITMSG = "fix: thing\n\nCo-Authored-By: Claude <noreply@anthropic.com>\n" + VERBOSE_TAIL


def test_commit_strip_still_strips_when_commit_verbose_appends_the_diff(tmp_path: Path) -> None:
    """One config key turned the whole local layer into a silent no-op. Measured, not foreseen.

    `commit.verbose = true` makes git append the staged diff below a scissors line, and a diff's
    lines begin with `diff`, `+`, `-`, `@@` or a space — none of which is a comment or a blank.
    The walk back from the end of the file stopped at the first of them, the whole file read as
    "message", the attribution block was no longer trailing, and nothing was stripped:

        A) CONTROL, no verbose      : stripped 2 attribution line(s); trailer stored: 0
        B) SAME, commit.verbose=true: trailer in the stored message: 1   (DEFECT)

    The fixture is git's own output, captured from a `prepare-commit-msg` hook in a real
    repository with `commit.verbose` set, and retyped here.

    Both assertions are needed. "The trailer is gone" alone is satisfied by a split that threw
    the diff away, which would be a corruption rather than a no-op; the second is against a fixed
    literal and says every byte git appended comes back. The diff is what the earlier
    comment-block test cannot pin, because without `verbose` there is none.
    """
    message = tmp_path / "COMMIT_EDITMSG"
    message.write_text(VERBOSE_EDITMSG, encoding="utf-8")
    assert invoke(["commit", "strip", str(message)]) == 0
    result = message.read_text(encoding="utf-8")
    assert "Co-Authored-By" not in result
    assert result == "fix: thing\n" + VERBOSE_TAIL


def test_a_scissors_line_is_found_by_its_marker_not_by_gits_english_sentence(
    tmp_path: Path,
) -> None:
    # The two lines under the scissors ("Do not modify or remove the line above.") go through
    # gettext, so a rule keyed on that wording stops splitting in a translated checkout and the
    # hook silently no-ops there. The ruler and its `>8` are not translated. This fixture is the
    # same file with those two lines in another language; the answer must not move.
    message = tmp_path / "COMMIT_EDITMSG"
    message.write_text(
        VERBOSE_EDITMSG.replace(
            "# Do not modify or remove the line above.\n# Everything below it will be ignored.\n",
            "# Ne modifiez pas et ne supprimez pas la ligne ci-dessus.\n"
            "# Tout ce qui suit sera ignore.\n",
        ),
        encoding="utf-8",
    )
    assert invoke(["commit", "strip", str(message)]) == 0
    result = message.read_text(encoding="utf-8")
    assert result.startswith("fix: thing\n\n# Please enter")
    assert "Co-Authored-By" not in result


@needs_git
def test_test_hygiene_reports_the_two_faults(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # Exit 1 is "findings", which is what makes this a command and not only a hook notice.
    # Reddened by mutating `run_test_hygiene`'s `exit_code=1 if findings else 0` to `0`;
    # measured. The `roots == 1` assertion has no mutation of its own here — `code_roots` is
    # overridden to the single entry `src`, which exists, so neither the `is_dir()` filter nor
    # the containment call changes this number (both were applied and this test stayed green).
    # It is the wiring assertion: it pins that `--json` reports the profile's own counts, under
    # the profile's name, and the filter and the containment check are pinned in
    # `tests/profiles/python/test_hygiene.py`.
    root = repo(tmp_path)
    (root / "pyproject.toml").write_text('[project]\nname = "widget"\n', encoding="utf-8")
    (root / "src").mkdir()
    (root / "src" / "m.py").write_text("x = 1\n", encoding="utf-8")
    (root / "stayfixed.toml").write_text(
        CONFIG + '\n[ledger]\ncode_roots = ["src"]\n', encoding="utf-8"
    )
    argv = ["test", "hygiene", "--root", str(root), "--machine", str(tmp_path / "m.toml"), "--json"]
    assert invoke(argv) == 1
    out = json.loads(capsys.readouterr().out)
    assert out["dirty"] >= 1 and out["profiles"] == {"python": {"stale": 0, "roots": 1}}


@needs_git
def test_test_hygiene_reports_every_stack_by_its_markers_and_not_by_configuration(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # `[stayfixed] profile` names one stack, and a repository may be written in several: the
    # report goes to every profile whose markers sit at the root. `CONFIG` names no profile, so
    # the Python entry here comes from `pyproject.toml` alone, and a repository with no marker
    # gets no entry while it has nothing to say. Reddened by mutating `run_test_hygiene`'s
    # `if note is None and not detects(load_profile(name), root):` to `if False:` (the second
    # assertion); measured.
    root = repo(tmp_path)
    argv = ["test", "hygiene", "--root", str(root), "--machine", str(tmp_path / "m.toml"), "--json"]
    (root / "pyproject.toml").write_text('[project]\nname = "widget"\n', encoding="utf-8")
    invoke(argv)
    assert set(json.loads(capsys.readouterr().out)["profiles"]) == {"python"}
    (root / "pyproject.toml").unlink()
    invoke(argv)
    assert json.loads(capsys.readouterr().out)["profiles"] == {}


@needs_git
def test_test_hygiene_is_clean_on_a_committed_tree(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # `repo()` leaves no `[ledger]` and no stack's marker, so no profile reports: this pins the
    # clean-tree path, not the walk. The walk is pinned in
    # `tests/profiles/python/test_hygiene.py`. Reddened by mutating `run_test_hygiene`'s
    # `exit_code=1 if findings else 0` to `1`; measured. Then a committed `pyproject.toml`, so
    # Python is detected with nothing to report, and the summary says so in the words a person
    # reads. Oracle: `mutations/`, "test hygiene's clean summary names no stack".
    root = repo(tmp_path)
    argv = ["test", "hygiene", "--root", str(root), "--machine", str(tmp_path / "m.toml")]
    assert invoke(argv) == 0
    assert capsys.readouterr().out == "tree is clean\n"
    (root / "pyproject.toml").write_text('[project]\nname = "widget"\n', encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "chore: python")
    assert invoke(argv) == 0
    assert capsys.readouterr().out == "tree is clean; the python profile has nothing to report\n"


@needs_git
def test_test_hygiene_refuses_a_tree_git_cannot_report_on(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # Not in the ported plan: exit 2 is the third of the three exit codes the CLI row
    # promises, and without this the `Refusal` branch of `run_test_hygiene` is unexercised —
    # deleting it would report an unjudgeable tree as clean and exit 0. Reddened by replacing
    # `raise Refusal(_NO_GIT)` with `dirty = 0`; measured.
    root = tmp_path / "bare"
    root.mkdir()
    (root / "stayfixed.toml").write_text(CONFIG, encoding="utf-8")
    argv = ["test", "hygiene", "--root", str(root), "--machine", str(tmp_path / "m.toml")]
    assert invoke(argv) == 2
    assert "refused:" in capsys.readouterr().err


@needs_git
def test_test_hygiene_names_the_stale_count_in_its_summary(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # The summary's profile branch, which nothing else at the CLI level renders: the tests
    # above report `stale == 0`, so the profile's line could be dropped from the summary with
    # them still green. The walk itself is pinned in `tests/profiles/python/test_hygiene.py`;
    # this is the string a person reads, the profile's name and then its own note. Reddened by
    # mutating `run_test_hygiene`'s `if note:` to `if False:`; measured.
    root = repo(tmp_path)
    (root / "pyproject.toml").write_text('[project]\nname = "widget"\n', encoding="utf-8")
    (root / "src").mkdir()
    module = root / "src" / "m.py"
    module.write_text("x = 1\n", encoding="utf-8")
    compile_module(module)
    make_stale(module)
    (root / "stayfixed.toml").write_text(
        CONFIG + '\n[ledger]\ncode_roots = ["src"]\n', encoding="utf-8"
    )
    argv = ["test", "hygiene", "--root", str(root), "--machine", str(tmp_path / "m.toml")]
    assert invoke(argv) == 1
    assert "python: 1 .pyc file(s) whose recorded source mtime" in capsys.readouterr().out


@needs_git
def test_test_hygiene_reports_a_profile_with_something_to_say_wherever_its_markers_sit(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # A monorepo whose Python project lives in a subdirectory has no Python marker at its root,
    # and the hook, which asks every hint and detects nothing, still reports its stale bytecode
    # after a failed pytest run. Listing only the profiles detected at the root answered "tree is
    # clean", exit 0, for the same tree: the command contradicted the notice it documents. A
    # profile whose note is not `None` is listed whether or not its markers sit at the root, and
    # the exit code follows. The tree is committed, with the bytecode ignored, so the only
    # finding is the stale `.pyc`. Oracle: `mutations/`, "test hygiene hides a profile its
    # markers do not detect at the root".
    root = repo(tmp_path)
    (root / ".gitignore").write_text("__pycache__/\n", encoding="utf-8")
    (root / "src").mkdir()
    module = root / "src" / "m.py"
    module.write_text("x = 1\n", encoding="utf-8")
    (root / "stayfixed.toml").write_text(
        CONFIG + '\n[ledger]\ncode_roots = ["src"]\n', encoding="utf-8"
    )
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "chore: code")
    compile_module(module)
    make_stale(module)
    assert not (root / "pyproject.toml").exists()
    argv = ["test", "hygiene", "--root", str(root), "--machine", str(tmp_path / "m.toml"), "--json"]
    assert invoke(argv) == 1
    out = json.loads(capsys.readouterr().out)
    assert out["dirty"] == 0 and out["profiles"] == {"python": {"stale": 1, "roots": 1}}


@needs_git
@pytest.mark.parametrize("as_json", [False, True])
def test_test_hygiene_refuses_a_failing_hint_without_printing_its_message(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    as_json: bool,
) -> None:
    # An exception's message can carry what the hint walked: on Python 3.11 `rglob` lets an
    # `OSError` for a name too long to open escape with the full path, and a repository chooses
    # its directories' names. Printed as an internal error, that text reached whoever ran this
    # command, the agent the shipped skills send here included. The refusal names the profile
    # and the exception's type and nothing the exception carried, in either output. Oracle:
    # `mutations/`, "test hygiene prints a failing hint's own message".
    root = repo(tmp_path)
    (root / "src").mkdir()
    (root / "src" / "m.py").write_text("x = 1\n", encoding="utf-8")
    (root / "stayfixed.toml").write_text(
        CONFIG + '\n[ledger]\ncode_roots = ["src"]\n', encoding="utf-8"
    )
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "chore: code")

    def broken(self: Path, pattern: str) -> object:
        raise OSError("<injected text>")

    monkeypatch.setattr(Path, "rglob", broken)
    json_flag = ["--json"] if as_json else []
    argv = ["test", "hygiene", "--root", str(root), "--machine", str(tmp_path / "m.toml")]
    assert invoke([*argv, *json_flag]) == 2
    captured = capsys.readouterr()
    assert "<injected text>" not in captured.out + captured.err
    assert "the python profile's red-run hint failed: OSError" in captured.out + captured.err


def detected_everywhere(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every shipped profile's markers sit at the root, whatever the tree holds."""
    monkeypatch.setattr("stayfixed.profiles.load_profile", lambda name: name)
    monkeypatch.setattr("stayfixed.profiles.detects", lambda profile, root: True)


def committed_project(tmp_path: Path) -> Path:
    """A repository whose one file, its configuration, is committed: a clean tree."""
    root = tmp_path / "repo"
    root.mkdir()
    (root / "stayfixed.toml").write_text(redrun.CONFIG, encoding="utf-8")
    git(root, "init", "-q", "-b", "main")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "chore: seed")
    return root


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
    loud, quiet = redrun.LoudHint("x", "alpha says"), redrun.FakeHint("y", None)
    redrun.ship(monkeypatch, {"alpha": loud, "beta": quiet})
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
    redrun.ship(
        monkeypatch, {"alpha": redrun.FakeHint("x", None), "beta": redrun.FakeHint("y", None)}
    )
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
    redrun.ship(monkeypatch, {"gamma": redrun.FakeHint("x", None)})
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
    redrun.ship(monkeypatch, {"alpha": redrun.WordlessHint("x", "alpha says")})
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
    redrun.ship(monkeypatch, {"alpha": redrun.EmptyHint("x", "alpha says")})
    monkeypatch.setattr("stayfixed.profiles.load_profile", lambda name: name)
    monkeypatch.setattr("stayfixed.profiles.detects", lambda profile, root: False)
    root = committed_project(tmp_path)
    argv = ["test", "hygiene", "--root", str(root), "--machine", str(tmp_path / "m.toml"), "--json"]
    assert invoke(argv) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["profiles"] == {}
    assert out["summary"] == "tree is clean"


@needs_git
def test_test_attribute_runs_the_three_trees_and_reports_the_verdict(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # The argv wiring end to end: the real launcher, the real `git archive`, the real `sh`.
    # `repo()` leaves HEAD on `main`, so the merge-base with `main` is HEAD itself and a
    # command that always passes gives the "not reproduced" sentence — the one verdict of the
    # five that a green command can produce, so the assertion names it rather than asserting
    # that some sentence came back. The `--json` keys are the documented contract
    # (`docs/cli.md`), stated as fixed literals and not read off the dataclass.
    #
    # The summary is asserted beside the `verdict` key and not only through it: the first
    # draft of this test checked `out["verdict"]` alone, and mutating `run_test_attribute`'s
    # `Result(result.verdict, data)` to `Result("done", data)` left the whole suite green —
    # `verdict` comes out of `data`, so the line a person reads was covered by nothing.
    # Re-measured with both: that mutation now reddens this test, and this test alone.
    from stayfixed.guards.attribute import VERDICTS

    root = repo(tmp_path)
    argv = [
        "test",
        "attribute",
        "--command",
        "true",
        "--base",
        "main",
        "--root",
        str(root),
        "--machine",
        str(tmp_path / "m.toml"),
        "--json",
    ]
    assert invoke(argv) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["verdict"] == VERDICTS[4]
    assert out["summary"] == VERDICTS[4]
    assert sorted(out) == ["base", "merge_base", "runs", "summary", "verdict"]
    assert out["runs"] == {"head_ambient": 0, "head_clean": 0, "base_clean": 0}
    assert out["base"] == "main"
    assert out["merge_base"] == git(root, "rev-parse", "HEAD").strip()


@needs_git
def test_test_attribute_defaults_the_base_to_the_configured_branch_on_the_remote(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # `--base` omitted means `origin/<project.base_branch>` and not the bare branch name: a
    # local `main` that has not been fetched is not the base a pull request is measured
    # against. The fixture has no remote, so the default is proved by the ref the failure
    # names — `origin/main`, which only the default produces. Exit 1, because a merge-base
    # that cannot be resolved is a failed operation and not a refusal.
    # Reddened by mutating the default to `config.project.base_branch`; measured, and the
    # failure then names `main`, so the assertion is on the string and not on the exit code.
    root = repo(tmp_path)
    argv = [
        "test",
        "attribute",
        "--command",
        "true",
        "--root",
        str(root),
        "--machine",
        str(tmp_path / "m.toml"),
    ]
    assert invoke(argv) == 1
    assert "origin/main" in capsys.readouterr().err


@needs_git
def test_test_attribute_refuses_a_base_shaped_like_an_option(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # Exit 2, the third code the CLI row promises: `--base` reaches `git merge-base` as an
    # argument, so a `-`-shaped value is refused above the first subprocess rather than
    # becoming an option to it. Reddened by deleting the `base.startswith("-")`
    # raise in `attribute`; measured — the command then exits 1 with git's own complaint.
    #
    # The assertion was once `== 2` plus the word "refused:", which ANY refusal on this path
    # satisfies — `_root_and_config`'s missing-configuration refusal reaches the same two
    # lines, and only the hand-measured mutation ruled that reading out. The refusal's own
    # sentence is matched instead, so the test names the arm it is about.
    root = repo(tmp_path)
    argv = [
        "test",
        "attribute",
        "--command",
        "true",
        "--base=--upload-pack=touch /tmp/x",
        "--root",
        str(root),
        "--machine",
        str(tmp_path / "m.toml"),
    ]
    assert invoke(argv) == 2
    assert "--base must name a ref" in capsys.readouterr().err


@needs_git
def test_commit_check_names_at_most_the_listed_limit_of_offences(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # A range holds any number of commits, so the offences on the line are bounded in number by
    # nothing: it counts every commit, names the first `LISTED_LIMIT` offences, and says how many
    # more, and `--json`'s `violations` carries every one. Mutation (oracle): "commit check names
    # every offence" -> this reddens.
    dirty = "fix: dirty\n\nCo-Authored-By: Claude <noreply@anthropic.com>\n"
    root = repo(tmp_path, *[dirty] * (LISTED_LIMIT + 2))
    argv = ["commit", "check", "--range", "base..HEAD", "--root", str(root)]
    assert invoke([*argv, "--machine", str(tmp_path / "m.toml")]) == 1
    line = capsys.readouterr().out.strip()
    assert line.startswith(f"FAIL: {LISTED_LIMIT + 2} of {LISTED_LIMIT + 2} commit message(s)")
    assert line.count("[attribution trailer naming an AI tool]") == LISTED_LIMIT
    assert "[attribution trailer naming an AI tool], and 2 more. " in line
