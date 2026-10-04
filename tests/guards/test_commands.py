from __future__ import annotations

import io
import json
import os
import py_compile
import shutil
import sys
import time
from pathlib import Path

import pytest

from stayfixed.cli import build_parser, discover_registrars, run
from stayfixed.findings import LISTED_LIMIT
from tests.gitfixture import git


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
    # It is the wiring assertion: it pins that `--json` reports the walk's own count, and the
    # filter and the containment check are pinned in `tests/guards/test_hygiene.py`.
    root = repo(tmp_path)
    (root / "src").mkdir()
    (root / "src" / "m.py").write_text("x = 1\n", encoding="utf-8")
    (root / "stayfixed.toml").write_text(
        CONFIG + '\n[ledger]\ncode_roots = ["src"]\n', encoding="utf-8"
    )
    argv = ["test", "hygiene", "--root", str(root), "--machine", str(tmp_path / "m.toml"), "--json"]
    assert invoke(argv) == 1
    out = json.loads(capsys.readouterr().out)
    assert out["dirty"] >= 1 and out["stale"] == 0 and out["roots"] == 1


@needs_git
def test_test_hygiene_is_clean_on_a_committed_tree(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # `repo()` leaves no `[ledger]`, so the roots are the preset's (`src`, `tests`, `scripts`)
    # and none of them exists here: this pins the clean-tree path, not the walk. The walk is
    # pinned in `tests/guards/test_hygiene.py`. Reddened by mutating `run_test_hygiene`'s
    # `exit_code=1 if findings else 0` to `1`; measured.
    root = repo(tmp_path)
    argv = ["test", "hygiene", "--root", str(root), "--machine", str(tmp_path / "m.toml")]
    assert invoke(argv) == 0
    assert "clean" in capsys.readouterr().out


@needs_git
def test_test_hygiene_refuses_a_tree_git_cannot_report_on(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # Not in the ported plan: exit 2 is the third of the three exit codes the CLI row
    # promises, and without this the `Refusal` branch of `run_test_hygiene` is unexercised —
    # deleting it would report an unjudgeable tree as clean and exit 0. Reddened by replacing
    # `raise Refusal(_NO_GIT)` with `found = found._replace(dirty=0)`; measured.
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
    # The summary's stale branch, which nothing else at the CLI level renders: the two tests
    # above report `stale == 0` (and the clean one runs with `roots == 0`), so
    # `f"{found.stale} stale .pyc file(s) under {found.roots} code root(s)"` could be deleted
    # with both still green. The walk itself is pinned in `tests/guards/test_hygiene.py`; this
    # is the string a person reads. Reddened by mutating `run_test_hygiene`'s `if found.stale:`
    # to `if False:`; measured.
    root = repo(tmp_path)
    (root / "src").mkdir()
    module = root / "src" / "m.py"
    module.write_text("x = 1\n", encoding="utf-8")
    # Explicit `cfile` and `TIMESTAMP`, for the reasons `tests/guards/test_hygiene.py`'s
    # `compile_module` gives: `cfile=None` follows `PYTHONPYCACHEPREFIX` out of the fixture,
    # and `SOURCE_DATE_EPOCH` in the environment would make the header hash-based.
    py_compile.compile(
        str(module),
        cfile=str(root / "src" / "__pycache__" / f"m.{sys.implementation.cache_tag}.pyc"),
        doraise=True,
        invalidation_mode=py_compile.PycInvalidationMode.TIMESTAMP,
    )
    future = time.time() + 60
    os.utime(module, (future, future))
    (root / "stayfixed.toml").write_text(
        CONFIG + '\n[ledger]\ncode_roots = ["src"]\n', encoding="utf-8"
    )
    argv = ["test", "hygiene", "--root", str(root), "--machine", str(tmp_path / "m.toml")]
    assert invoke(argv) == 1
    assert "1 stale .pyc file(s) under 1 code root(s)" in capsys.readouterr().out


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
