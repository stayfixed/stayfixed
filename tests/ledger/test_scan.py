"""One traversal for three readers, and the two readers that use it.

stayfixed:ledger:fixtures — the identifiers below are sample data, not claims about a ledger.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path, PurePosixPath
from typing import Any

import pytest

from stayfixed.config.loader import load
from stayfixed.config.schema import Config
from stayfixed.gitenv import git_run
from stayfixed.ledger.register import bug_register
from stayfixed.ledger.scan import (
    FIXTURE_MARKER,
    FIXTURE_MARKER_WINDOW,
    citation_pattern,
    citation_roots,
    code_mentions,
    entry_citations,
    mention_roots,
    scannable,
)
from tests.gitfixture import git, plant_path

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


def project(tmp_path: Path, extra: str = "") -> tuple[Path, Config]:
    root = tmp_path / "widget"
    root.mkdir()
    (root / "stayfixed.toml").write_text(CONFIG + extra, encoding="utf-8")
    for name in ("src", "tests", "scripts", "docs"):
        (root / name).mkdir()
    return root, load(root, machine=tmp_path / "m.toml")


def write(root: Path, relative: str, text: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_mention_roots_are_the_top_level_plus_the_contained_code_roots(tmp_path: Path) -> None:
    root, config = project(tmp_path)
    assert mention_roots(root, config) == (".", "src", "tests", "scripts")


def test_citation_roots_add_the_first_component_of_every_document_path(tmp_path: Path) -> None:
    # The defaults put every document under `docs/`; a citation names a path, so the reader
    # that reports a dangling one may read documents, while the bare-mention reader may not
    # (plan documents spell invented identifiers as worked examples).
    root, config = project(tmp_path)
    assert citation_roots(root, config) == (".", "src", "tests", "scripts", "docs")


def test_a_code_root_outside_the_project_is_skipped_not_scanned(tmp_path: Path) -> None:
    root, config = project(tmp_path, '\n[ledger]\ncode_roots = ["src", "../elsewhere"]\n')
    (tmp_path / "elsewhere").mkdir()
    assert mention_roots(root, config) == (".", "src")


def test_the_top_level_files_are_scanned(tmp_path: Path) -> None:
    # `pyproject.toml` and `.gitignore` each carried a live identifier once, invisible to a scan
    # that only knew directories.
    root, config = project(tmp_path)
    write(root, "pyproject.toml", "# see BR-404\n")
    assert list(code_mentions(root, config, bug_register(config))) == ["BR-404"]


@pytest.mark.parametrize(
    "location",
    [
        "node_modules/pkg/index.js",
        "src/build/generated.py",
        "tests/dist/bundle.js",
        "scripts/__pycache__/x.py",
    ],
)
def test_the_walk_enters_no_vendored_or_generated_directory(tmp_path: Path, location: str) -> None:
    root, config = project(tmp_path)
    write(root, location, "// see BR-404\n")
    assert code_mentions(root, config, bug_register(config)) == {}


def test_a_directory_name_is_excluded_only_inside_the_repository(tmp_path: Path) -> None:
    # A repository kept under a directory called `build` is an ordinary thing.
    root = tmp_path / "build"
    root.mkdir()
    (root / "stayfixed.toml").write_text(CONFIG, encoding="utf-8")
    (root / "src").mkdir()
    config = load(root, machine=tmp_path / "m.toml")
    write(root, "src/a.py", "# BR-404\n")
    assert list(code_mentions(root, config, bug_register(config))) == ["BR-404"]


def test_a_binary_suffix_and_a_symlink_are_skipped_whole(tmp_path: Path) -> None:
    root, config = project(tmp_path)
    (root / "src" / "img.png").write_bytes(b"BR-404")
    outside = tmp_path / "outside.py"
    outside.write_text("# BR-405\n", encoding="utf-8")
    os.symlink(outside, root / "src" / "linked.py")
    assert code_mentions(root, config, bug_register(config)) == {}


def test_a_fixture_holder_is_excluded_from_the_scan(tmp_path: Path) -> None:
    # The marker replaces the source's hard-coded exclusion list. Mutation: make
    # `is_fixture_holder` return False — this reddens.
    root, config = project(tmp_path)
    write(root, "tests/test_x.py", f'"""{FIXTURE_MARKER} — sample data"""\nENTRY = "BR-404"\n')
    write(root, "tests/test_y.py", "ENTRY = 'BR-405'\n")
    assert list(code_mentions(root, config, bug_register(config))) == ["BR-405"]


def test_the_marker_is_read_only_from_the_head_of_a_file(tmp_path: Path) -> None:
    # A marker buried past the window is prose about the marker, not the marker.
    root, config = project(tmp_path)
    write(
        root,
        "tests/test_x.py",
        "x = 1\n" * (FIXTURE_MARKER_WINDOW // 6 + 1) + f"# {FIXTURE_MARKER}\nENTRY = 'BR-404'\n",
    )
    assert list(code_mentions(root, config, bug_register(config))) == ["BR-404"]


def test_an_undecodable_file_is_not_text_and_an_unreadable_one_carries_its_error(
    tmp_path: Path,
) -> None:
    root, _config = project(tmp_path)
    (root / "src" / "latin.py").write_bytes(b"# \xff BR-404\n")
    write(root, "src/ok.py", "# BR-405\n")
    items = {item.relative.as_posix(): item for item in scannable(root, ("src",))}
    assert items["src/latin.py"].text is None and items["src/latin.py"].error is None
    assert items["src/ok.py"].text == "# BR-405\n"
    if os.geteuid() == 0:
        pytest.skip("root reads everything")
    (root / "src" / "ok.py").chmod(0)
    try:
        items = {item.relative.as_posix(): item for item in scannable(root, ("src",))}
        assert items["src/ok.py"].text is None and items["src/ok.py"].error
    finally:
        (root / "src" / "ok.py").chmod(0o644)


@needs_git
def test_git_enumerates_the_candidates_and_an_ignored_file_is_not_one(tmp_path: Path) -> None:
    # The question is "what is in the commit under review"; a walk answers a different one.
    # Mutation: make `_committed_files` return None — this reddens.
    root, config = project(tmp_path)
    git(root, "init", "-q")
    write(root, ".gitignore", "src/generated/\n")
    write(root, "src/generated/out.py", "# BR-404\n")
    write(root, "src/a.py", "# BR-405\n")
    assert list(code_mentions(root, config, bug_register(config))) == ["BR-405"]


@needs_git
def test_a_listing_git_gave_no_answer_for_falls_back_to_the_walk_and_not_to_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # `git_run`'s `(-1, "")` — git could not be run or ran past its bound — read as an empty
    # listing scanned no file at all and reported every reference as absent: the guard that
    # says OK because it looked at nothing, which this module's walk fallback exists to
    # prevent. Only the listing is diverted, so the top-level probe still answers and the case
    # reaches the listing's own arm. Mutation (declared): answer the failed listing with the
    # empty string again — the scan finds nothing and this reddens.
    from stayfixed.ledger import scan as module

    root, config = project(tmp_path)
    git(root, "init", "-q")
    write(root, "src/a.py", "# BR-405\n")
    real = git_run

    def unanswered(where: Path, *args: str, **kwargs: Any) -> tuple[int, str]:
        return (-1, "") if args[0] == "ls-files" else real(where, *args, **kwargs)

    monkeypatch.setattr(module, "git_run", unanswered)
    assert list(code_mentions(root, config, bug_register(config))) == ["BR-405"]


@needs_git
def test_a_listed_name_that_is_not_utf_8_hides_no_other_file(tmp_path: Path) -> None:
    # `ls-files -z` prints a tracked name raw; decoded losslessly it is one more name in the
    # listing, and the files beside it are still scanned. The planted name has no file on this
    # disk (APFS refuses one), so this also holds that a listed name the scan cannot open costs
    # that name and not the scan.
    root, config = project(tmp_path)
    git(root, "init", "-q")
    write(root, "src/a.py", "# BR-405\n")
    plant_path(root, b"src/caf\xe9.py")
    assert list(code_mentions(root, config, bug_register(config))) == ["BR-405"]


@needs_git
def test_a_root_that_is_not_the_top_of_a_checkout_falls_back_to_the_walk(tmp_path: Path) -> None:
    git(tmp_path, "init", "-q")
    root, config = project(tmp_path)
    write(root, "src/a.py", "# BR-404\n")
    assert list(code_mentions(root, config, bug_register(config))) == ["BR-404"]


def test_a_citation_of_an_entry_file_is_resolved_two_ways(tmp_path: Path) -> None:
    root, config = project(tmp_path)
    write(root, "src/a.py", "# see docs/bugs/BR-404.md\n")
    write(root, "docs/roadmap.md", "see [x](bugs/BR-405.md)\n")
    write(root, "docs/deeper/note.md", "see [x](../bugs/BR-406.md)\n")
    # resolves to docs/deeper/bugs/: not a citation
    write(root, "docs/deeper/other.md", "see [x](bugs/BR-407.md)\n")
    found = entry_citations(root, config, bug_register(config))
    assert set(found) == {"BR-404", "BR-405", "BR-406"}
    assert found["BR-404"] == [(PurePosixPath("src/a.py"), 1)]


def test_an_absolute_path_that_merely_contains_the_entry_path_is_not_a_citation(
    tmp_path: Path,
) -> None:
    root, config = project(tmp_path)
    write(root, "src/a.py", "# /tmp/x/docs/bugs/BR-404.md\n")
    assert entry_citations(root, config, bug_register(config)) == {}


def test_the_index_and_the_entries_are_not_read_as_citers(tmp_path: Path) -> None:
    root, config = project(tmp_path)
    write(root, "docs/bug-reports.md", "| [BR-404](bugs/BR-404.md) |\n")
    write(root, "docs/bugs/BR-001.md", "see [BR-404](BR-404.md)\n")
    assert entry_citations(root, config, bug_register(config)) == {}


def test_the_citation_pattern_follows_the_configured_ledger_directory(tmp_path: Path) -> None:
    _root, config = project(tmp_path, '\n[paths]\nbugs = "docs/defects"\n')
    assert citation_pattern(bug_register(config)).search("docs/defects/BR-001.md")
    assert not citation_pattern(bug_register(config)).search("docs/bugs/BR-001.md")
