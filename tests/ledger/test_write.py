"""`new` and `renumber`: every rejection leaves the tree untouched; every write is enumerated.

stayfixed:ledger:fixtures — the identifiers below are sample data, not claims about a ledger.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from stayfixed.config.loader import load
from stayfixed.config.schema import Config
from stayfixed.errors import Refusal
from stayfixed.gitenv import NO_ANSWER, git_run
from stayfixed.ledger.check import problems
from stayfixed.ledger.entries import LedgerError, load_entries
from stayfixed.ledger.index import render_index
from stayfixed.ledger.register import EVIDENCE_LABEL, bug_register
from stayfixed.ledger.scan import FIXTURE_MARKER
from stayfixed.ledger.write import file_entry, next_identifier, renumber
from tests.gitfixture import git, plant_path, run_git

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

# The values every filing below that is not about them passes.
LOW = {"severity": "low", "area": "a"}

needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")


def project(tmp_path: Path) -> tuple[Path, Config]:
    root = tmp_path / "widget"
    root.mkdir()
    (root / "stayfixed.toml").write_text(CONFIG, encoding="utf-8")
    for name in ("src", "tests", "scripts", "docs", "docs/bugs"):
        (root / name).mkdir()
    return root, load(root, machine=tmp_path / "m.toml")


def entry(number: int, related: str = "") -> str:
    return (
        f"---\nid: BR-{number:03d}\ntitle: a title\nstatus: open\nseverity: low\n"
        f"area: an area\nfound: 2026-01-01\nsource:\nfixed_in:\nrelated: {related}\n---\n\n"
        f"body mentioning BR-{number:03d}\n"
    )


def seed(root: Path, config: Config, *numbers: int) -> None:
    for number in numbers:
        path = root / "docs" / "bugs" / f"BR-{number:03d}.md"
        path.write_text(entry(number), encoding="utf-8")
    register = bug_register(config)
    (root / "docs" / "bug-reports.md").write_text(
        render_index(load_entries(root, register), register), encoding="utf-8"
    )


def commit_all(root: Path, message: str = "seed") -> None:
    git(root, "add", "-A")
    git(root, "-c", "user.email=t@example.com", "-c", "user.name=t", "commit", "-qm", message)


def test_new_writes_a_scaffolded_entry_and_refreshes_the_index(tmp_path: Path) -> None:
    root, config = project(tmp_path)
    filed = file_entry(
        root,
        bug_register(config),
        title="the reconciler collides with its own id",
        values={"severity": "high", "area": "delivery", "source": "audit-2026-08-16"},
        today="2026-08-16",
        fetch=False,
    )
    assert filed.identifier == "BR-001" and filed.warning is None
    written = (root / "docs" / "bugs" / "BR-001.md").read_text(encoding="utf-8")
    assert 'title: "the reconciler collides with its own id"' not in written  # no quoting needed
    assert "title: the reconciler collides with its own id\n" in written
    assert (
        "status: open\nseverity: high\narea: delivery\nfound: 2026-08-16\n"
        "source: audit-2026-08-16\nfixed_in:\nrelated:\n"
    ) in written
    assert EVIDENCE_LABEL in written
    assert "BR-001" in (root / "docs" / "bug-reports.md").read_text(encoding="utf-8")
    found = problems(root, config, bug_register(config))
    assert [p.rule for p in found] == ["evidence-boundary"]  # scaffolded


def test_new_quotes_a_source_value_that_needs_it(tmp_path: Path) -> None:
    root, config = project(tmp_path)
    file_entry(
        root,
        bug_register(config),
        title="t",
        values={"severity": "low", "area": "a", "source": "#412 in the tracker"},
        fetch=False,
    )
    written = (root / "docs" / "bugs" / "BR-001.md").read_text(encoding="utf-8")
    assert 'source: "#412 in the tracker"' in written
    assert load_entries(root, bug_register(config))[0].fields["source"] == "#412 in the tracker"


@pytest.mark.parametrize("key", ["found", "fixed_in", "sevrity"])
def test_a_value_the_template_has_no_line_for_is_refused_not_dropped(
    tmp_path: Path, key: str
) -> None:
    # `found` and `fixed_in` are literal lines of the bug ledger's template and a misspelt key
    # names no line at all; `str.format` ignores a keyword it has no field for, so each value was
    # dropped in silence and the entry filed without it. Mutation (oracle): the refusal skipped ->
    # every case files an entry.
    root, config = project(tmp_path)
    with pytest.raises(ValueError, match=f"the bugs register's template has no line for {key}$"):
        file_entry(root, bug_register(config), title="t", values={**LOW, key: "x"}, fetch=False)
    assert list((root / "docs" / "bugs").iterdir()) == []
    assert not (root / "docs" / "bug-reports.md").exists()


def test_new_rejects_a_malformed_related_identifier_before_writing_anything(
    tmp_path: Path,
) -> None:
    root, config = project(tmp_path)
    with pytest.raises(LedgerError):
        file_entry(
            root,
            bug_register(config),
            title="t",
            values={"severity": "low", "area": "a"},
            related=("BR-2",),
            fetch=False,
        )
    assert list((root / "docs" / "bugs").iterdir()) == []
    assert not (root / "docs" / "bug-reports.md").exists()


def test_new_refuses_over_foreign_index_content_without_writing(tmp_path: Path) -> None:
    root, config = project(tmp_path)
    index = root / "docs" / "bug-reports.md"
    foreign = "# Bug reports\n\n## BR-009 — hand-written\n"
    index.write_text(foreign, encoding="utf-8")
    with pytest.raises(Refusal):
        file_entry(root, bug_register(config), title="t", values=LOW, fetch=False)
    assert list((root / "docs" / "bugs").iterdir()) == []
    # The refusal exists to stop the regeneration deleting the operator's own lines, so the
    # bytes are the assertion: an exception raised over a file already rewritten proves nothing.
    assert index.read_text(encoding="utf-8") == foreign


def test_new_never_writes_over_an_entry_file_whatever_the_allocator_returns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The allocator cannot see a branch this checkout never fetched; the file's existence
    # decides. Mutation: drop the `path.exists()` refusal — this reddens.
    root, config = project(tmp_path)
    seed(root, config, 1)
    from stayfixed.ledger import write as module

    monkeypatch.setattr(
        module, "next_identifier", lambda *a, **k: module.Allocation("BR-001", None)
    )
    before = (root / "docs" / "bugs" / "BR-001.md").read_text(encoding="utf-8")
    with pytest.raises(LedgerError, match="already exists"):
        file_entry(root, bug_register(config), title="t", values=LOW, fetch=False)
    assert (root / "docs" / "bugs" / "BR-001.md").read_text(encoding="utf-8") == before


def test_next_identifier_counts_void_numbers_and_a_filename_whose_id_disagrees(
    tmp_path: Path,
) -> None:
    root, config = project(tmp_path)
    (root / "docs" / "bugs" / "BR-003.md").write_text(
        "---\nid: BR-003\ntitle: v\nstatus: void\nfound: 2026-01-01\n---\n", encoding="utf-8"
    )
    # id BR-002 under filename BR-007
    (root / "docs" / "bugs" / "BR-007.md").write_text(entry(2), encoding="utf-8")
    assert next_identifier(root, bug_register(config), fetch=False).identifier == "BR-008"


@needs_git
def test_next_identifier_sees_entries_on_other_branches(tmp_path: Path) -> None:
    # Mutation: drop the `git log --all` source — this reddens.
    root, config = project(tmp_path)
    git(root, "init", "-q", "-b", "main")
    seed(root, config, 1)
    commit_all(root)
    git(root, "checkout", "-qb", "other")
    (root / "docs" / "bugs" / "BR-005.md").write_text(entry(5), encoding="utf-8")
    commit_all(root, "five")
    git(root, "checkout", "-q", "main")
    assert next_identifier(root, bug_register(config), fetch=False).identifier == "BR-006"


@needs_git
def test_a_name_that_is_not_utf_8_in_history_does_not_hide_every_other_ref(tmp_path: Path) -> None:
    # Reproduced in review: with `core.quotePath=false`, `git log --name-only` prints a name in
    # the ledger's history raw, and when `git_run` read an answer that was not UTF-8 as no
    # answer, the allocator took that for an empty history — handing out BR-002, which `other`
    # holds, with no word. Two things now hold it, each on its own: the log is asked with
    # quoting forced on, so such a name comes back escaped, and `git_run` decodes raw bytes
    # losslessly anyway. Measured: either one removed alone leaves this green, so neither has an
    # oracle entry of its own; removing both reddens it on the identifier.
    root, config = project(tmp_path)
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "core.quotePath", "false")
    seed(root, config, 1)
    commit_all(root)
    git(root, "checkout", "-qb", "other")
    (root / config.paths.bugs / "BR-005.md").write_text(entry(5), encoding="utf-8")
    commit_all(root, "five")
    git(root, "checkout", "-q", "main")
    plant_path(root, f"{config.paths.bugs}/caf".encode() + b"\xe9.txt")
    # Not `commit_all`: `add -A` would stage the planted name's removal, as no such file exists.
    git(root, "-c", "user.email=t@example.com", "-c", "user.name=t", "commit", "-qm", "planted")
    allocation = next_identifier(root, bug_register(config), fetch=False)
    assert allocation.identifier == "BR-006"
    assert allocation.warning is None


@needs_git
@pytest.mark.parametrize("code", [-1, 128])
def test_a_history_git_gave_no_answer_for_is_named_and_not_read_as_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, code: int
) -> None:
    # A timeout (30 s over `log --all`) or a `git` that cannot run left every other ref's
    # entries uncounted with no word, and so did a log that failed inside a repository. The
    # working tree still counts; the warning says what did not. Outside a repository there is
    # no history to miss, which the next case pins. Mutation (declared): the warning arm never
    # taken — the warning is `None` and this reddens.
    root, config = project(tmp_path)
    git(root, "init", "-q", "-b", "main")
    seed(root, config, 1)
    from stayfixed.ledger import write as module

    real = git_run

    def failing(where: Path, *args: str, **kwargs: Any) -> tuple[int, str]:
        if "log" in args:
            return code, ""
        return real(where, *args, **kwargs)

    monkeypatch.setattr(module, "git_run", failing)
    allocation = next_identifier(root, bug_register(config), fetch=False)
    assert allocation.identifier == "BR-002"
    assert allocation.warning is not None
    assert "history" in allocation.warning and "collide" in allocation.warning
    if code == -1:
        assert NO_ANSWER in allocation.warning


@needs_git
@pytest.mark.parametrize("git_runs", [True, False], ids=["git", "no-git"])
def test_outside_a_repository_there_is_no_history_to_warn_about(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, git_runs: bool
) -> None:
    # `git log` exits 128 outside a work tree, and a `git` that cannot run answers `-1`; neither
    # is a missed history where no `.git` exists: `bugs new` in a directory git does not know
    # stays one line. Mutation (advisory): warn on every failed log without reading the disk —
    # both cases redden.
    root, config = project(tmp_path)
    if not git_runs:
        monkeypatch.setenv("PATH", str(tmp_path / "no-git-here"))
    assert next_identifier(root, bug_register(config), fetch=False).warning is None


@needs_git
def test_a_repository_git_refuses_to_read_is_not_mistaken_for_no_repository(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Found in review: the allocator asked `rev-parse --is-inside-work-tree` whether a failed log
    # meant "no repository", and git refuses that question the same way it refused the log — a
    # checkout it judges of dubious ownership (a bind mount under another uid in a container or
    # CI), a linked worktree whose gitdir is gone. BR-005 on `other` went uncounted with no word.
    # "No repository" is read off the disk now, where a `.git` entry is. The wrapper makes git
    # judge the checkout foreign, as `safe.directory` would. It reads neither the system nor the
    # global configuration: a machine whose either file sets `safe.directory = *` trusts every
    # checkout, and git then answers the log this case needs refused. Mutation (declared): the
    # disk check replaced by the `rev-parse` question again — the warning is `None` and this
    # reddens.
    root, config = project(tmp_path)
    git(root, "init", "-q", "-b", "main")
    seed(root, config, 1)
    commit_all(root)
    git(root, "checkout", "-qb", "other")
    (root / config.paths.bugs / "BR-005.md").write_text(entry(5), encoding="utf-8")
    commit_all(root, "five")
    git(root, "checkout", "-q", "main")
    real = shutil.which("git")
    assert real is not None
    wrappers = tmp_path / "bin"
    wrappers.mkdir()
    wrapper = wrappers / "git"
    wrapper.write_text(
        "#!/bin/sh\n"
        f"GIT_TEST_ASSUME_DIFFERENT_OWNER=1 GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL={os.devnull} "
        f'exec "{real}" "$@"\n',
        encoding="utf-8",
    )
    wrapper.chmod(0o755)
    monkeypatch.setenv("PATH", f"{wrappers}{os.pathsep}{os.environ['PATH']}")
    allocation = next_identifier(root, bug_register(config), fetch=False)
    assert allocation.identifier == "BR-002"
    assert allocation.warning is not None
    assert "git log exited 128" in allocation.warning


@needs_git
def test_the_allocator_reads_the_git_source_with_the_shared_digit_rule(tmp_path: Path) -> None:
    # The `git log` reader used to respell the digit rule inline as `(\d{3,})` instead of
    # taking `DIGITS` from `stayfixed.identifiers`, which owns it. A third spelling is one
    # `mutations/`'s "the identifier digit rule widens and the allocator keeps the old one" cannot
    # reach, so widening the rule would have left the allocator counting by the old one and
    # handing out a number some ref already holds. Mutation: `DIGITS = r"\d+"` — `BR-42.md`
    # becomes an identifier the reader counts and this reddens (that same entry).
    root, config = project(tmp_path)
    git(root, "init", "-q", "-b", "main")
    seed(root, config, 1)
    commit_all(root)
    git(root, "checkout", "-qb", "other")
    (root / "docs" / "bugs" / "BR-005.md").write_text(entry(5), encoding="utf-8")
    (root / "docs" / "bugs" / "BR-42.md").write_text("a two-digit name\n", encoding="utf-8")
    commit_all(root, "five, and a name too short to be an identifier")
    git(root, "checkout", "-q", "main")
    assert next_identifier(root, bug_register(config), fetch=False).identifier == "BR-006"


def test_a_failed_fetch_is_reported_not_raised(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, config = project(tmp_path)
    from stayfixed.ledger import write as module

    real = git_run

    def failing(where: Path, *args: str, **kwargs: Any) -> tuple[int, str]:
        # Only the fetch fails; the history the allocator reads next is the real one.
        if args[0] == "fetch":
            return 128, ""
        return real(where, *args, **kwargs)

    monkeypatch.setattr(module, "git_run", failing)
    allocation = next_identifier(root, bug_register(config), fetch=True)
    assert allocation.identifier == "BR-001"
    assert allocation.warning is not None and "fetch" in allocation.warning


def test_a_fetch_that_gave_no_answer_names_every_cause_and_not_only_two(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # `-1` is every cause `NO_ANSWER` names, and the warning words it with that clause rather
    # than with one cause of its own choosing. Mutation (advisory): word `-1` as "could not run
    # or timed out" again — this reddens.
    root, config = project(tmp_path)
    from stayfixed.ledger import write as module

    monkeypatch.setattr(module, "git_run", lambda *a, **k: (-1, ""))
    warning = next_identifier(root, bug_register(config), fetch=True).warning
    assert warning is not None and NO_ANSWER in warning


def test_renumber_moves_the_entry_rewrites_every_reference_and_leaves_a_void_pointer(
    tmp_path: Path,
) -> None:
    root, config = project(tmp_path)
    seed(root, config, 1, 2)
    (root / "docs" / "bugs" / "BR-002.md").write_text(
        entry(2, related="[BR-001]"), encoding="utf-8"
    )
    (root / "src" / "a.py").write_text("# BR-001 and XBR-001 stays\n", encoding="utf-8")
    (root / "docs" / "note.md").write_text("see [BR-001](bugs/BR-001.md)\n", encoding="utf-8")
    result = renumber(root, config, bug_register(config), "BR-001", "BR-009", today="2026-01-02")
    # A frozen record, and a value: a list among its fields made `hash(result)` raise.
    # Mutation (oracle): the unswept files handed back as the list they were collected in.
    assert result.unswept == ()
    assert hash(result) == hash(replace(result))
    assert result.void == root / "docs" / "bugs" / "BR-001.md"
    assert (root / "src" / "a.py").read_text(encoding="utf-8") == "# BR-009 and XBR-001 stays\n"
    assert (root / "docs" / "note.md").read_text(encoding="utf-8") == (
        "see [BR-009](bugs/BR-009.md)\n"
    )
    assert "related: [BR-009]" in (root / "docs" / "bugs" / "BR-002.md").read_text(encoding="utf-8")
    moved = (root / "docs" / "bugs" / "BR-009.md").read_text(encoding="utf-8")
    # The body is the operator's: the sweep never rewrites the moved entry itself.
    assert moved.startswith("---\nid: BR-009\n") and "body mentioning BR-001" in moved
    void = (root / "docs" / "bugs" / "BR-001.md").read_text(encoding="utf-8")
    assert "status: void" in void and "related: [BR-009]" in void
    assert "[BR-009](BR-009.md)" in void
    assert problems(root, config, bug_register(config)) == []


def test_renumber_refuses_an_occupied_target_and_a_missing_source(tmp_path: Path) -> None:
    root, config = project(tmp_path)
    seed(root, config, 1, 2)
    entries = {path: path.stat().st_mtime_ns for path in (root / "docs" / "bugs").iterdir()}
    with pytest.raises(LedgerError, match="pick a free identifier"):
        renumber(root, config, bug_register(config), "BR-001", "BR-002")
    with pytest.raises(LedgerError, match="does not exist"):
        renumber(root, config, bug_register(config), "BR-005", "BR-006")
    # Neither rejection wrote: same files, none of them replaced. `renumber` overwrites its
    # source in place, so a half-run would leave BR-001.md rewritten with its name unchanged.
    assert {path: path.stat().st_mtime_ns for path in (root / "docs" / "bugs").iterdir()} == entries


def test_renumber_refuses_over_foreign_index_content_without_moving_anything(
    tmp_path: Path,
) -> None:
    # `renumber` regenerates the index at the end, so it makes `new`'s refusal before its first
    # write — and it is the destructive one: both endpoints and the whole sweep are already on
    # disk by the time the regeneration runs.
    # Oracle: `mutations/`, "renumber regenerates over an index carrying content this tool
    # did not generate" — measured, and the only test in the suite that reddens under it.
    root, config = project(tmp_path)
    seed(root, config, 1)
    index = root / "docs" / "bug-reports.md"
    foreign = index.read_text(encoding="utf-8") + "\n## Notes an operator keeps here\n"
    index.write_text(foreign, encoding="utf-8")
    entry_file = root / "docs" / "bugs" / "BR-001.md"
    before = entry_file.read_text(encoding="utf-8")
    with pytest.raises(Refusal):
        renumber(root, config, bug_register(config), "BR-001", "BR-009")
    assert index.read_text(encoding="utf-8") == foreign
    assert not (root / "docs" / "bugs" / "BR-009.md").exists()
    assert entry_file.read_text(encoding="utf-8") == before


def test_renumber_rejects_a_malformed_sibling_before_it_moves_anything(tmp_path: Path) -> None:
    # The reproduction, from repository-authored input: `_write_index` runs last and parses
    # every entry file in the directory, so one malformed sibling the operator never touched
    # failed the command with both endpoints and the whole sweep already on disk — exit 1 naming
    # someone else's file, a half-completed rename, and a retry refused with "already has an
    # entry file", so the move could not be finished at all. The docstring promises "every check
    # that can reject the call runs before any file is touched". Mutation: drop the
    # `load_entries` call before the first write — the three tree assertions redden.
    root, config = project(tmp_path)
    seed(root, config, 1, 2)
    bugs = root / "docs" / "bugs"
    sibling = bugs / "BR-002.md"
    sibling.write_text(entry(2).replace("status: open", "status: nonsense"), encoding="utf-8")
    before = {path: path.read_text(encoding="utf-8") for path in bugs.iterdir()}
    with pytest.raises(LedgerError, match=r"BR-002\.md"):
        renumber(root, config, bug_register(config), "BR-001", "BR-009")
    assert not (bugs / "BR-009.md").exists()
    assert {path: path.read_text(encoding="utf-8") for path in bugs.iterdir()} == before
    # And the retry, once the sibling is repaired, completes — rather than being refused for a
    # target the failed run created on its way out.
    sibling.write_text(entry(2), encoding="utf-8")
    renumber(root, config, bug_register(config), "BR-001", "BR-009")
    assert (bugs / "BR-009.md").is_file()


def test_renumber_normalises_an_id_line_with_nonstandard_spacing(tmp_path: Path) -> None:
    root, config = project(tmp_path)
    seed(root, config, 1)
    path = root / "docs" / "bugs" / "BR-001.md"
    path.write_text(
        path.read_text(encoding="utf-8").replace("id: BR-001", "id:   BR-001"), encoding="utf-8"
    )
    renumber(root, config, bug_register(config), "BR-001", "BR-009")
    moved = (root / "docs" / "bugs" / "BR-009.md").read_text(encoding="utf-8")
    assert moved.startswith("---\nid: BR-009\n")


def test_renumber_leaves_a_fixture_holder_and_a_binary_alone(tmp_path: Path) -> None:
    root, config = project(tmp_path)
    seed(root, config, 1)
    fixture = root / "tests" / "test_x.py"
    fixture.write_text(f"# {FIXTURE_MARKER}\nENTRY = 'BR-001'\n", encoding="utf-8")
    (root / "src" / "img.png").write_bytes(b"BR-001")
    assert renumber(root, config, bug_register(config), "BR-001", "BR-009").unswept == ()
    assert "BR-001" in fixture.read_text(encoding="utf-8")
    assert (root / "src" / "img.png").read_bytes() == b"BR-001"


def test_renumber_does_not_follow_a_symlink_out_of_the_tree(tmp_path: Path) -> None:
    # Passes by construction of `scannable`, which skips anything that is not `S_ISREG`, and
    # again by `fsops.write_within`, which refuses to write through a symlinked component.
    root, config = project(tmp_path)
    seed(root, config, 1)
    outside = tmp_path / "outside.py"
    outside.write_text("# BR-001\n", encoding="utf-8")
    os.symlink(outside, root / "src" / "linked.py")
    renumber(root, config, bug_register(config), "BR-001", "BR-009")
    assert outside.read_text(encoding="utf-8") == "# BR-001\n"


def test_renumber_reports_a_file_it_could_not_sweep_and_keeps_both_endpoints(
    tmp_path: Path,
) -> None:
    # Once the void pointer exists, `known` makes a stale mention look intentional forever, so
    # an unreadable file is reported and the command fails rather than claiming a rewrite it
    # did not deliver. Mutation: `continue` silently on `item.error` — this reddens.
    if os.geteuid() == 0:
        pytest.skip("root reads everything")
    root, config = project(tmp_path)
    seed(root, config, 1)
    locked = root / "src" / "locked.py"
    locked.write_text("# BR-001\n", encoding="utf-8")
    locked.chmod(0)
    try:
        result = renumber(root, config, bug_register(config), "BR-001", "BR-009")
    finally:
        locked.chmod(0o644)
    assert [u.path for u in result.unswept] == ["src/locked.py"]
    assert result.unswept[0].reason.startswith("could not be read to check for BR-001")
    assert (root / "docs" / "bugs" / "BR-009.md").is_file()
    void = (root / "docs" / "bugs" / "BR-001.md").read_text(encoding="utf-8")
    assert "status: void" in void


def test_renumber_reports_a_file_it_could_not_write_back(tmp_path: Path) -> None:
    # The other half of `unswept`: the file reads fine and carries the identifier, and the
    # write through `fsops` is what fails. Reported for the same reason an unreadable file is —
    # once the void pointer exists the stale mention looks intentional to `check` forever.
    if os.geteuid() == 0:
        pytest.skip("root writes everywhere")
    root, config = project(tmp_path)
    seed(root, config, 1)
    sealed = root / "src" / "sealed"
    sealed.mkdir()
    (sealed / "a.py").write_text("# BR-001\n", encoding="utf-8")
    sealed.chmod(0o555)
    try:
        result = renumber(root, config, bug_register(config), "BR-001", "BR-009")
    finally:
        sealed.chmod(0o755)
    assert [u.path for u in result.unswept] == ["src/sealed/a.py"]
    assert result.unswept[0].reason.startswith("could not be written")
    assert (sealed / "a.py").read_text(encoding="utf-8") == "# BR-001\n"


def test_a_successful_fetch_leaves_no_warning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The other side of `test_a_failed_fetch_is_reported_not_raised`: a fetch that worked says
    # nothing, so the command line carries a warning only when one is true.
    root, config = project(tmp_path)
    from stayfixed.ledger import write as module

    monkeypatch.setattr(module, "git_run", lambda *a, **k: (0, ""))
    assert next_identifier(root, bug_register(config), fetch=True).warning is None


@needs_git
@pytest.mark.parametrize("gone", [False, True], ids=["reachable", "gone"])
def test_the_fetch_asks_origin_alone_and_never_a_submodules_remote(
    tmp_path: Path, gone: bool
) -> None:
    # The fetch is for refs, to see the identifiers on branches this checkout has not fetched.
    # Under git's default `fetch.recurseSubmodules=on-demand` it also fetched from the remote of
    # each populated submodule whose recorded commit it brought in: a destination the README had
    # to disclose. Reachable, that remote's new commit arrives in the checkout's submodule, which
    # is the destination asked, observed directly; gone, it failed the whole fetch and warned of a
    # collision nothing caused. Mutation (declared): the fetch recurses again -> the reachable
    # case finds the commit fetched, and the gone case's fetch exits 1 ("Errors during submodule
    # fetch") with a warning.
    upstream, _ = project(tmp_path)
    git(upstream, "init", "-q", "-b", "main")
    sub = tmp_path / "sub"
    git(tmp_path, "init", "-q", "-b", "main", str(sub))
    git(sub, "commit", "-q", "--allow-empty", "-m", "one")
    file_protocol = ("-c", "protocol.file.allow=always")
    git(upstream, *file_protocol, "submodule", "add", "-q", str(sub), "sub")
    commit_all(upstream)
    root = tmp_path / "checkout"
    git(tmp_path, *file_protocol, "clone", "-q", "--recurse-submodules", str(upstream), str(root))
    git(sub, "commit", "-q", "--allow-empty", "-m", "two")
    two = git(sub, "rev-parse", "HEAD").strip()
    git(upstream / "sub", *file_protocol, "pull", "-q", "origin", "main")
    commit_all(upstream, "move the submodule")
    if gone:
        shutil.rmtree(sub)
    allocation = next_identifier(
        root, bug_register(load(root, machine=tmp_path / "m.toml")), fetch=True
    )
    assert allocation.identifier == "BR-001"
    assert allocation.warning is None
    assert run_git(root / "sub", "cat-file", "-e", two).returncode != 0


def test_the_allocator_starts_at_one_before_the_ledger_directory_exists(tmp_path: Path) -> None:
    root, config = project(tmp_path)
    (root / "docs" / "bugs").rmdir()
    assert next_identifier(root, bug_register(config), fetch=False).identifier == "BR-001"


def test_a_severity_outside_the_vocabulary_is_rejected_before_anything_is_allocated(
    tmp_path: Path,
) -> None:
    # `argparse` rejects it at the command line; the library says so too, because `file_entry`
    # is on the import surface and a consumer calling it directly gets no `choices=`.
    root, config = project(tmp_path)
    with pytest.raises(LedgerError, match="--severity must be one of"):
        file_entry(
            root,
            bug_register(config),
            title="t",
            values={"severity": "huge", "area": "a"},
            fetch=False,
        )
    assert list((root / "docs" / "bugs").iterdir()) == []


def test_renumber_rejects_an_endpoint_that_is_not_an_identifier(tmp_path: Path) -> None:
    root, config = project(tmp_path)
    seed(root, config, 1)
    entry_file = root / "docs" / "bugs" / "BR-001.md"
    before = entry_file.stat().st_mtime_ns
    with pytest.raises(LedgerError, match="must look like BR-nnn"):
        renumber(root, config, bug_register(config), "BR-42", "BR-009")
    # Refused before the shape was ever resolved to a path, so nothing under the ledger moved.
    assert [p.name for p in (root / "docs" / "bugs").iterdir()] == ["BR-001.md"]
    assert entry_file.stat().st_mtime_ns == before


def test_the_sweep_leaves_a_file_that_only_looks_like_it_carries_the_identifier(
    tmp_path: Path,
) -> None:
    # The substring test finds the file and the word-bounded substitution changes nothing in
    # it, so it is never written back: rewriting it would bump a file the move did not touch.
    root, config = project(tmp_path)
    seed(root, config, 1)
    near = root / "src" / "near.py"
    near.write_text("# XBR-001 is a different thing\n", encoding="utf-8")
    before = near.stat().st_mtime_ns
    assert renumber(root, config, bug_register(config), "BR-001", "BR-009").unswept == ()
    assert near.read_text(encoding="utf-8") == "# XBR-001 is a different thing\n"
    assert near.stat().st_mtime_ns == before
