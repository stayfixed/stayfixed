"""The `docs` and `trail` gates judge tracked files: `assess` says when a file one of them reads
is not, and `adopt promote` never enforces such a gate.

CI checks out what git tracks and nothing else, so a file those gates read here and git does not
track is one they read here and CI never sees; there the gate's own finding for an absent file
fails every pull request. Each case starts from the smoke fixture, where every file is tracked
and every gate passes, and takes one file out of git's index while leaving it on disk.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import pytest

from stayfixed import gitenv
from stayfixed.assess import tracked
from stayfixed.assess.assessment import UNNAMED, Assessment, assess, document, render
from stayfixed.assess.gates import COULD_NOT_RUN, GateResult, configured
from stayfixed.assess.state import promote
from stayfixed.assess.tracked import (
    CASE_DIFFERS,
    CASE_REMEDY,
    UNASKED,
    UNASKED_REASON,
    UNASKED_REMEDY,
    UNSEEN_REASON,
    UNTRACKED,
)
from stayfixed.config.loader import load
from stayfixed.printed import UNPRINTABLE
from tests.assess.smoke import BASE, FIXTURE, PLAN, smoke_repo
from tests.cli import cli
from tests.gitfixture import git, needs_git

pytestmark = needs_git

AGENTS = "AGENTS.md"
ROADMAP = "docs/roadmap.md"
TRAIL = "docs/trail.toml"


def _untrack(root: Path, path: str) -> None:
    """Take `path` out of git's index and commit that, leaving the file on disk."""
    git(root, "rm", "-q", "--cached", "--", path)
    git(root, "commit", "-qm", "chore: keep a file out of git")


def _unlink_roadmap(root: Path) -> None:
    """The fixture's `AGENTS.md` with its link to the roadmap turned into plain text, so the
    roadmap is read by the gates that read it by path and by no link."""
    agents = root / AGENTS
    text = agents.read_text(encoding="utf-8")
    link = f"[{ROADMAP}]({ROADMAP})"
    assert link in text, text
    agents.write_text(text.replace(link, ROADMAP), encoding="utf-8")
    git(root, "commit", "-qam", "docs: name the roadmap without a link")


def _assess(root: Path, tmp_path: Path) -> Assessment:
    return assess(root, machine=tmp_path / "m.toml", base=BASE)


def _row(assessment: Assessment, name: str) -> GateResult:
    return next(g for g in assessment.gates if g.name == name)


def _items(assessment: Assessment, rule: str) -> dict[str, tuple[str, ...]]:
    return {i.probe: i.where for i in assessment.items if i.rule == rule}


def _sha(root: Path, rev: str) -> str:
    return git(root, "rev-parse", rev).strip()


def _unenforced(root: Path) -> None:
    """The fixture with its `enforced` list dropped, so its gates have something to be promoted
    to."""
    config = root / "stayfixed.toml"
    text = config.read_text(encoding="utf-8")
    listed = 'enforced = ["docs", "bugs", "plan", "commit", "trail"]\n'
    assert text.count(listed) == 1
    config.write_text(text.replace(listed, ""), encoding="utf-8")
    git(root, "commit", "-qam", "chore: begin again")


def test_a_tree_whose_every_read_file_is_tracked_is_judged_as_it_is(tmp_path: Path) -> None:
    # The fixture as it is: nothing untracked, so both gates answer and nothing is reported.
    # Without this the cases below could pass on a check that reports every file. Mutations
    # (declared): a directory with a tracked file under it reads as untracked; a walk that
    # reaches a tracked file names it all the same.
    assessment = _assess(smoke_repo(tmp_path), tmp_path)
    assert assessment.would_fail == ()
    assert _items(assessment, UNTRACKED) == {}


@pytest.mark.parametrize(
    ("path", "gate"),
    [(AGENTS, "docs"), (ROADMAP, "trail"), (TRAIL, "trail")],
    ids=["agents-md", "roadmap", "trail-toml"],
)
def test_assess_reports_a_gate_that_reads_an_untracked_file_as_unable_to_judge_it(
    tmp_path: Path, path: str, gate: str
) -> None:
    # The file is there, so the gate passes here; CI would not have it. The gate's row says it
    # could not judge the tree as CI will, it would fail if enforced, and an item names the file.
    # `trail.toml` is the trail gate's too: CI would rebuild the listing without its states.
    # Mutations (declared): the tracked check answers "tracked" for everything; the trail
    # gate's `trail.toml` is not asked about; either gate's record declares no files it reads.
    root = smoke_repo(tmp_path)
    _unlink_roadmap(root)
    _untrack(root, path)
    assessment = _assess(root, tmp_path)
    row = _row(assessment, gate)
    assert (row.answered, row.reason) == (False, UNSEEN_REASON)
    assert gate in assessment.would_fail
    assert _items(assessment, UNTRACKED) == {gate: (path,)}
    # And every other gate is judged as before.
    assert assessment.would_fail == (gate,)
    # The summary counts and names the gate and the rule; the file stays in the document.
    summary = render(assessment)
    assert f"| {gate} | yes | could not run | yes |" in summary, summary
    assert f"| {gate} | {UNTRACKED} | warning | 1 |" in summary, summary
    assert path not in summary, summary
    rows = {r["name"]: r for r in document(assessment)["gates"]}
    assert rows[gate]["answered"] is False and rows[gate]["failing"] is True, rows[gate]


def test_an_ignored_file_is_untracked_too(tmp_path: Path) -> None:
    # A file kept out of git by an ignore rule is the commonest way this happens, and CI sees it
    # no more than an untracked one.
    root = smoke_repo(tmp_path)
    (root / ".gitignore").write_text(f"/{AGENTS}\n", encoding="utf-8")
    git(root, "add", ".gitignore")
    _untrack(root, AGENTS)
    assessment = _assess(root, tmp_path)
    assert _row(assessment, "docs").reason == UNSEEN_REASON
    assert _items(assessment, UNTRACKED) == {"docs": (AGENTS,)}


def test_a_file_the_always_loaded_document_links_to_is_read_by_the_docs_gate(
    tmp_path: Path,
) -> None:
    # `check_links` asks whether each target exists, and CI answers for the tracked tree: a link
    # to a file git does not track passes here and is `missing-link` there. A link to a tracked
    # directory is tracked through the files under it. Mutation (declared): the docs gate's
    # link targets are not asked about.
    root = smoke_repo(tmp_path)
    (root / "local-notes.md").write_text("# mine\n", encoding="utf-8")
    agents = root / AGENTS
    agents.write_text(
        agents.read_text(encoding="utf-8") + "\n[notes](local-notes.md) and [docs](docs/specs)\n",
        encoding="utf-8",
    )
    git(root, "add", AGENTS)
    git(root, "commit", "-qm", "docs: link a local file")
    assessment = _assess(root, tmp_path)
    assert _row(assessment, "docs").reason == UNSEEN_REASON
    assert _items(assessment, UNTRACKED) == {"docs": ("local-notes.md",)}


def _link_through(
    root: Path, links: dict[str, str], ignored: tuple[str, ...] = (), linked: str = "notes.md"
) -> None:
    """`AGENTS.md` gains a link to `linked`; each of `links` is a symlink, its path to its
    target as written; `private/notes.md` is a file; every path in `ignored` is kept out of git
    by an ignore rule; and the rest is committed."""
    (root / "private").mkdir(exist_ok=True)
    (root / "private" / "notes.md").write_text("# mine\n", encoding="utf-8")
    for path, target in links.items():
        (root / path).symlink_to(target)
    (root / ".gitignore").write_text("".join(f"/{p}\n" for p in ignored), encoding="utf-8")
    agents = root / AGENTS
    agents.write_text(agents.read_text(encoding="utf-8") + f"\n[notes]({linked})\n", "utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "docs: link the notes through a symlink")


@pytest.mark.parametrize(
    ("links", "ignored", "named"),
    [
        ({"notes.md": "private/notes.md"}, ("private/",), "private/notes.md"),
        (
            {"notes.md": "mid.md", "mid.md": "private/notes.md"},
            ("mid.md",),
            "mid.md",
        ),
        ({"notes.md": "../outside.md"}, (), "notes.md"),
        ({"notes.md": "/etc/hosts"}, (), "notes.md"),
    ],
    ids=["to-an-ignored-file", "through-an-ignored-link", "out-of-the-project", "absolute"],
)
def test_a_symlinked_link_target_is_judged_by_where_it_leads_in_a_checkout(
    tmp_path: Path, links: dict[str, str], ignored: tuple[str, ...], named: str
) -> None:
    # git tracks a symlink as the link alone, and CI checks it out dangling when what it leads to
    # is not tracked, or is outside the repository, where no checkout of it has anything: there the
    # link is `missing-link`. So the link being tracked says nothing about what CI reads through
    # it. Each link on the way is followed, and the first that a checkout would not have is
    # named: the untracked file or link, or the link that leaves the project. Mutations
    # (declared): a symlinked link target is judged by the link alone; the untracked file a link
    # leads to is not named, only the link; a climb above the work tree's top, or a link to an
    # absolute target, reads as one a checkout has.
    root = smoke_repo(tmp_path)
    if named == "notes.md":
        (root.parent / "outside.md").write_text("# outside\n", encoding="utf-8")
    _link_through(root, links, ignored)
    assert (root / "notes.md").exists()
    assessment = _assess(root, tmp_path)
    assert _row(assessment, "docs").reason == UNSEEN_REASON
    assert _items(assessment, UNTRACKED) == {"docs": (named,)}


@pytest.mark.parametrize("target", ["elsewhere.md", "notes.md"], ids=["elsewhere", "itself"])
def test_a_climb_out_of_a_symlinked_directory_is_walked_as_the_filesystem_walks_it(
    tmp_path: Path, target: str
) -> None:
    # The filesystem resolves a path one component at a time, so `..` climbs out of a symlinked
    # directory from where the directory leads, not from where the link sits. `sub` leads into
    # the ignored `private/deeper`, so `sub/../<target>` is `private/<target>` on disk and in no
    # checkout. Collapsed as text, it would be the tracked `elsewhere.md`, or `notes.md` itself,
    # a link that names itself for as long as the walk has hops to spend. Walked as the
    # filesystem walks it, it reaches the ignored `private` and the link is named. Mutations
    # (declared): a link's target is collapsed as text before it is walked; a step whose path
    # climbs is named by its own path.
    root = smoke_repo(tmp_path)
    (root / "private" / "deeper").mkdir(parents=True)
    (root / "private" / "elsewhere.md").write_text("# mine\n", encoding="utf-8")
    (root / "elsewhere.md").write_text("# ours\n", encoding="utf-8")
    _link_through(root, {"sub": "private/deeper", "notes.md": f"sub/../{target}"}, ("private/",))
    assert (root / "notes.md").resolve() == (root / "private" / target).resolve()
    assessment = _assess(root, tmp_path)
    assert _items(assessment, UNTRACKED) == {"docs": ("notes.md",)}


@pytest.mark.parametrize(
    ("ignored", "named"),
    [((), None), (("private/",), "private/notes.md")],
    ids=["to-a-tracked-directory", "to-an-ignored-directory"],
)
def test_a_committed_symlinked_directory_on_a_link_s_way_is_followed(
    tmp_path: Path, ignored: tuple[str, ...], named: str | None
) -> None:
    # `alias -> private` is committed, and a checkout writes the directory link; the file behind
    # it is tracked at its real path, so CI reads `alias/notes.md` and passes the link. A
    # directory link on the way is followed as the last one is, and judged by where it leads:
    # when that is ignored, the file there is named, which is the file to commit. Mutation
    # (declared): only the last component of a path is asked whether it is a symlink.
    root = smoke_repo(tmp_path)
    _link_through(root, {"alias": "private"}, ignored, linked="alias/notes.md")
    assert (root / "alias" / "notes.md").is_file()
    assessment = _assess(root, tmp_path)
    assert _row(assessment, "docs").answered is (named is None)
    assert _items(assessment, UNTRACKED) == ({"docs": (named,)} if named else {})


@pytest.mark.parametrize("absolute", [False, True], ids=["climbs-out", "absolute"])
def test_a_directory_link_that_leads_out_of_the_repository_is_named_by_the_link(
    tmp_path: Path, absolute: bool
) -> None:
    # A committed `alias -> ../outside`, or to an absolute path, leaves the link dangling in every
    # other checkout. What to fix is the link, so the link is named, and not the path through
    # it, which names a file nobody could commit. Mutation (declared): a link that leads out is
    # named by the path through it.
    root = smoke_repo(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "notes.md").write_text("# outside\n", encoding="utf-8")
    target = str(outside) if absolute else "../outside"
    _link_through(root, {"alias": target}, linked="alias/notes.md")
    assert (root / "alias" / "notes.md").is_file()
    assert _items(_assess(root, tmp_path), UNTRACKED) == {"docs": ("alias",)}


@pytest.mark.parametrize(
    ("links", "linked", "retarget", "named"),
    [
        ({"alias": "private"}, "alias/notes.md", ("alias", "real"), "alias/notes.md"),
        ({"notes.md": "private/notes.md"}, "notes.md", ("notes.md", "real/notes.md"), "notes.md"),
    ],
    ids=["directory-link", "file-link"],
)
def test_a_link_retargeted_on_disk_and_not_staged_is_named(
    tmp_path: Path,
    links: dict[str, str],
    linked: str,
    retarget: tuple[str, str],
    named: str,
) -> None:
    # The link is committed pointing into the ignored `private/`, then pointed on disk at the
    # tracked `real/` and not staged. The disk's link leads to a tracked file, and a checkout
    # writes the committed one, which leads nowhere: `missing-link`. So a link git reports as
    # changed in the work tree is not followed; it is the first step a checkout does not have.
    # Mutation (declared): a link changed on disk is followed as it is on disk.
    root = smoke_repo(tmp_path)
    (root / "real").mkdir()
    (root / "real" / "notes.md").write_text("# ours\n", encoding="utf-8")
    _link_through(root, links, ("private/",), linked=linked)
    path, target = retarget
    (root / path).unlink()
    (root / path).symlink_to(target)
    assert (root / linked).read_text(encoding="utf-8") == "# ours\n"
    assessment = _assess(root, tmp_path)
    assert _row(assessment, "docs").reason == UNSEEN_REASON
    assert _items(assessment, UNTRACKED) == {"docs": (named,)}


def test_a_link_chain_longer_than_the_cap_is_named_where_the_walk_stopped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The walk follows the links the filesystem follows, and it counts them from the work tree's
    # top where the filesystem counts from `/`, so a path that exists never takes it past
    # `LINK_HOPS` (40, Linux's own limit; macOS stops at 32). The cap is the backstop for a walk
    # that ever does, and it must stop without an answer, never with "tracked": so the cap is
    # lowered here under a chain of two tracked links to a tracked file, and the link it did not
    # follow is named. With room for both, the same chain is judged. Mutation (declared): the
    # walk that runs out of hops answers "tracked".
    root = smoke_repo(tmp_path)
    _link_through(root, {"notes.md": "mid.md", "mid.md": "private/notes.md"})
    monkeypatch.setattr(tracked, "LINK_HOPS", 2)
    assert _items(_assess(root, tmp_path), UNTRACKED) == {}
    monkeypatch.setattr(tracked, "LINK_HOPS", 1)
    assessment = _assess(root, tmp_path)
    assert _row(assessment, "docs").reason == UNSEEN_REASON
    assert _items(assessment, UNTRACKED) == {"docs": ("mid.md",)}


def _project_below_the_top(
    tmp_path: Path, target: str, ignored: tuple[str, ...] = (), beside: dict[str, str] | None = None
) -> Path:
    """The smoke fixture as `repo/proj`, a project in a subdirectory of its repository, with
    `repo/shared/notes.md` beside it and `proj/notes.md` a symlink to `target`, linked from the
    project's `AGENTS.md`; each of `beside` is a symlink under `repo/shared/`, its name to its
    target; every path in `ignored` is kept out of git by the top's ignore rules. Two commits, as
    `smoke_repo` makes them, so `BASE` names the first."""
    top = tmp_path / "repo"
    project = top / "proj"
    shutil.copytree(FIXTURE, project)
    (top / "shared").mkdir()
    (top / "shared" / "notes.md").write_text("# ours\n", encoding="utf-8")
    for name, leads in (beside or {}).items():
        (top / "shared" / name).symlink_to(leads)
    (top / ".gitignore").write_text("".join(f"/{p}\n" for p in ignored), encoding="utf-8")
    held = (project / PLAN).read_bytes()
    (project / PLAN).unlink()
    git(top, "init", "-q", "-b", "main")
    git(top, "add", "-A")
    git(top, "commit", "-qm", "chore: the fixture below the top")
    (project / PLAN).write_bytes(held)
    (project / "notes.md").symlink_to(target)
    agents = project / AGENTS
    agents.write_text(agents.read_text(encoding="utf-8") + "\n[notes](notes.md)\n", "utf-8")
    git(top, "add", "-A")
    git(top, "commit", "-qm", "docs: link the notes through a symlink")
    return project


def test_a_symlink_to_a_tracked_file_elsewhere_in_the_repository_is_judged(
    tmp_path: Path,
) -> None:
    # A project in a subdirectory of its repository, the shape `path:` and `[project]` roots
    # exist for. `proj/notes.md -> ../shared/notes.md` climbs out of the project and not out of
    # the repository, and every checkout has `shared/notes.md`: CI passes the link. So what is
    # outside is judged against the work tree's top, not the project's root. Mutations
    # (declared): a climb out of the project reads as a climb out of the repository; a `..` in a
    # link's target does not step back out of the directory reached.
    project = _project_below_the_top(tmp_path, "../shared/notes.md")
    assert (project / "notes.md").read_text(encoding="utf-8") == "# ours\n"
    assessment = _assess(project, tmp_path)
    assert _row(assessment, "docs").answered
    assert _items(assessment, UNTRACKED) == {}


@pytest.mark.parametrize(
    ("target", "ignored", "beside"),
    [
        ("../../outside.md", (), {}),
        ("../shared/notes.md", ("shared/",), {}),
        ("../shared/onward.md", ("shared/notes.md",), {"onward.md": "notes.md"}),
        ("../shared/onward.md", (), {"onward.md": "../../outside.md"}),
    ],
    ids=[
        "out-of-the-repository",
        "to-an-ignored-file-beside-the-project",
        "on-through-a-link-beside-the-project",
        "out-through-a-link-beside-the-project",
    ],
)
def test_a_symlink_below_the_top_that_no_checkout_has_names_the_link(
    tmp_path: Path, target: str, ignored: tuple[str, ...], beside: dict[str, str]
) -> None:
    # The top is where a climb is judged, and nothing else moves: a target above the repository
    # is in no checkout, and one beside the project that git does not track is in none either.
    # Either way the name printed is the link inside the project, never a path outside it, and
    # that holds when a tracked link beside the project leads on to the untracked file, or out of
    # the repository. Mutations (declared): a step outside the project is named by its own path;
    # a link outside the project is named as the link that led out.
    (tmp_path / "outside.md").write_text("# outside\n", encoding="utf-8")
    project = _project_below_the_top(tmp_path, target, ignored, beside)
    assert (project / "notes.md").exists()
    assessment = _assess(project, tmp_path)
    assert _row(assessment, "docs").reason == UNSEEN_REASON
    assert _items(assessment, UNTRACKED) == {"docs": ("notes.md",)}


def test_a_symlinked_link_target_that_leads_to_a_tracked_file_is_judged(tmp_path: Path) -> None:
    # The legitimate shape, which must not be refused: a committed symlink to a committed file,
    # such as a `current.md` naming this quarter's plan. CI checks out both and the link lands.
    # Mutation (declared): a symlink's target is followed from the link, not from its directory.
    root = smoke_repo(tmp_path)
    _link_through(root, {"notes.md": "private/notes.md"})
    assessment = _assess(root, tmp_path)
    assert _row(assessment, "docs").answered
    assert _items(assessment, UNTRACKED) == {}


def test_a_link_target_outside_the_path_grammar_is_withheld_where_it_is_named(
    tmp_path: Path,
) -> None:
    # A link target is any name the document wrote. The item's `where` holds it only inside the
    # path grammar, as a gate finding's does; `adopt promote`'s note does the same.
    root = smoke_repo(tmp_path)
    _unenforced(root)
    (root / "a note.md").write_text("# mine\n", encoding="utf-8")
    agents = root / AGENTS
    agents.write_text(
        agents.read_text(encoding="utf-8") + "\n[a note](a%20note.md)\n", encoding="utf-8"
    )
    git(root, "add", AGENTS)
    git(root, "commit", "-qm", "docs: link a local file with a space")
    assert _items(_assess(root, tmp_path), UNTRACKED) == {"docs": (UNNAMED,)}
    code, out, _ = cli(root, tmp_path, "adopt", "promote", "docs", "--base", _sha(root, BASE))
    assert code == 1, out
    assert "a note.md" not in out and UNPRINTABLE in out, out


def _link_in_another_case(root: Path) -> None:
    """`notes.md` committed, and `AGENTS.md` linking it as `Notes.md`; on a filesystem that keeps
    case apart, `Notes.md` is made a second name for the same file, which is what a filesystem
    that folds case, such as macOS's default, reads the link as."""
    (root / "notes.md").write_text("# ours\n", encoding="utf-8")
    agents = root / AGENTS
    agents.write_text(agents.read_text(encoding="utf-8") + "\n[notes](Notes.md)\n", "utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "docs: link the notes in another case")
    if not (root / "Notes.md").exists():
        os.link(root / "notes.md", root / "Notes.md")


def test_a_link_that_differs_from_the_tracked_file_only_in_case_says_so(tmp_path: Path) -> None:
    # On a filesystem that folds case the link reads the committed `notes.md`, and in a Linux
    # checkout it reads nothing: `missing-link`. So the gate could not judge the tree as CI will,
    # and the file is committed, so the remedy is to spell the link as git does, not to commit
    # it. The same file under both names stands in for a folding filesystem where case is kept
    # apart, so this holds on Linux as on macOS. Mutation (declared): the walk stops at a
    # case-differing component instead of continuing.
    root = smoke_repo(tmp_path)
    _link_in_another_case(root)
    assessment = _assess(root, tmp_path)
    assert _row(assessment, "docs").reason == UNSEEN_REASON
    assert _items(assessment, UNTRACKED) == {}
    assert _items(assessment, CASE_DIFFERS) == {"docs": ("Notes.md",)}
    remedy = next(i.remedy for i in assessment.items if i.rule == CASE_DIFFERS)
    assert remedy == CASE_REMEDY and "only in case" in remedy, remedy


def test_adopt_promote_s_note_on_a_case_difference_says_to_spell_it_as_git_does(
    tmp_path: Path,
) -> None:
    # The note is the item's remedy, and names the file as read; `--json` carries it apart from
    # the untracked files. Mutation (declared): the note is not printed.
    root = smoke_repo(tmp_path)
    _unenforced(root)
    _link_in_another_case(root)
    base = _sha(root, "HEAD~1")
    code, out, _ = cli(root, tmp_path, "adopt", "promote", "docs", "--base", base)
    assert code == 1, out
    note = next(line for line in out.splitlines() if line.startswith("note: docs reads"))
    assert note.startswith("note: docs reads Notes.md, which git tracks only under a name"), note
    assert note.endswith(CASE_REMEDY), note
    code, out, _ = cli(root, tmp_path, "adopt", "promote", "docs", "--base", base, "--json")
    data = json.loads(out)
    assert data["case_differs"] == {"docs": ["Notes.md"]} and data["untracked"] == {}, data


def test_a_different_file_whose_name_differs_only_in_case_is_untracked(tmp_path: Path) -> None:
    # Where case is kept apart, `Notes.md` beside a committed `notes.md` can be a file of its own,
    # and then it is simply untracked: spelling the link as git does would point it at another
    # file. No mutation is declared for this: the case exists only on a filesystem that keeps
    # case apart, and every declared entry must hold on macOS's folding one as on Linux.
    root = smoke_repo(tmp_path)
    (root / "notes.md").write_text("# ours\n", encoding="utf-8")
    if (root / "NOTES.md").exists():
        pytest.skip("this filesystem folds case, so the two names cannot be two files")
    git(root, "add", "notes.md")
    git(root, "commit", "-qm", "docs: the notes")
    (root / "Notes.md").write_text("# mine\n", encoding="utf-8")
    agents = root / AGENTS
    agents.write_text(agents.read_text(encoding="utf-8") + "\n[notes](Notes.md)\n", "utf-8")
    git(root, "add", AGENTS)
    git(root, "commit", "-qm", "docs: link a local file")
    assessment = _assess(root, tmp_path)
    assert _items(assessment, UNTRACKED) == {"docs": ("Notes.md",)}
    assert _items(assessment, CASE_DIFFERS) == {}


def _second_name(path: Path, same: Path) -> None:
    """`path` made a second name for `same` where case is kept apart, which is what a filesystem
    that folds case reads it as already: a hard link for a file, a second symlink to the same
    target for a link, a directory's included."""
    if path.exists():
        return
    if same.is_symlink():
        path.symlink_to(os.readlink(same))
    else:
        os.link(same, path)


def test_a_case_difference_on_a_symlinked_directory_is_case_differs(tmp_path: Path) -> None:
    # `alias -> private` and `private/notes.md` are committed, and the document links
    # `Alias/notes.md`. A filesystem that folds case reads the committed link and the committed
    # file; a Linux checkout has no `Alias`. Everything the link reaches is committed, so the remedy
    # is to spell it as git does, not to commit it. The walk once stopped at `Alias` and asked about
    # the whole path, which git lists under no spelling, and so said "commit it". Mutation
    # (declared): the walk stops at a case-differing component instead of continuing.
    root = smoke_repo(tmp_path)
    _link_through(root, {"alias": "private"}, linked="Alias/notes.md")
    _second_name(root / "Alias", root / "alias")
    assessment = _assess(root, tmp_path)
    assert _row(assessment, "docs").reason == UNSEEN_REASON
    assert _items(assessment, UNTRACKED) == {}
    assert _items(assessment, CASE_DIFFERS) == {"docs": ("Alias/notes.md",)}


def test_git_s_spelling_that_leads_to_an_untracked_file_is_untracked(tmp_path: Path) -> None:
    # git tracks `notes.md -> private/notes.md` and ignores `private/`; the document links
    # `Notes.md`. Spelling the link as git does would still read a file no checkout has, so the
    # remedy is to commit that file, and it is named, as an untracked step always is. Mutation
    # (declared): a case difference whose walk later meets an untracked step is reported as
    # `case-differs`.
    root = smoke_repo(tmp_path)
    _link_through(root, {"notes.md": "private/notes.md"}, ("private/",), linked="Notes.md")
    _second_name(root / "Notes.md", root / "notes.md")
    assessment = _assess(root, tmp_path)
    assert _items(assessment, UNTRACKED) == {"docs": ("private/notes.md",)}
    assert _items(assessment, CASE_DIFFERS) == {}


def test_a_case_difference_is_named_as_the_document_wrote_it(tmp_path: Path) -> None:
    # The document links `alias/Notes.md` through the committed `alias -> private`, and git tracks
    # `private/notes.md`. The name to respell is the one the document wrote: `private/Notes.md`
    # is a path the document never holds.
    root = smoke_repo(tmp_path)
    _link_through(root, {"alias": "private"}, linked="alias/Notes.md")
    _second_name(root / "private" / "Notes.md", root / "private" / "notes.md")
    assessment = _assess(root, tmp_path)
    assert _items(assessment, UNTRACKED) == {}
    assert _items(assessment, CASE_DIFFERS) == {"docs": ("alias/Notes.md",)}


def test_an_untracked_roadmap_leaves_the_docs_gate_judged(tmp_path: Path) -> None:
    # The docs gate reads the roadmap only when it is there, for its prose budget, and an absent
    # roadmap adds no finding: a roadmap CI cannot see makes the verdict here stricter than CI's
    # and never laxer. So only `trail` is reported, once no link names the roadmap: a link to it
    # is read by the docs gate as any link is, which the next case holds.
    root = smoke_repo(tmp_path)
    _unlink_roadmap(root)
    _untrack(root, ROADMAP)
    assessment = _assess(root, tmp_path)
    assert _row(assessment, "docs").answered
    assert set(_items(assessment, UNTRACKED)) == {"trail"}


def test_a_linked_roadmap_git_does_not_track_is_read_by_both_gates(tmp_path: Path) -> None:
    # The fixture as shipped links to its roadmap from `AGENTS.md`: untracked, it is a
    # `missing-link` in CI as well as a roadmap the trail gate cannot read.
    root = smoke_repo(tmp_path)
    _untrack(root, ROADMAP)
    assert _items(_assess(root, tmp_path), UNTRACKED) == {"docs": (ROADMAP,), "trail": (ROADMAP,)}


def test_outside_a_git_work_tree_the_files_are_judged_as_they_are(tmp_path: Path) -> None:
    # No index to ask and no checkout for CI to take: both gates judge the disk, as `docs trail`
    # lists every document there. Mutation (declared): the check is made outside a work tree
    # too, and every file reads as untracked.
    root = smoke_repo(tmp_path)
    shutil.rmtree(root / ".git")
    assessment = _assess(root, tmp_path)
    assert _row(assessment, "docs").answered and _row(assessment, "trail").answered
    # The probes that ask git say they could not look; neither gate is among them.
    assert not {"docs", "trail"} & (
        set(_items(assessment, UNTRACKED)) | set(_items(assessment, UNASKED))
    )


def test_a_git_that_gives_no_answer_is_never_read_as_tracked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Inside a work tree, a listing git did not give — it timed out, could not start, or refused
    # the checkout — says nothing about what CI will see, so the gate is not judged and is not
    # promoted. Mutation (declared): no answer reads as an empty listing's opposite, "tracked".
    root = smoke_repo(tmp_path)
    _unenforced(root)
    monkeypatch.setattr(tracked, "git_run", lambda *_a, **_k: (-1, ""))
    assessment = _assess(root, tmp_path)
    assert _row(assessment, "docs").reason == UNASKED_REASON
    assert _row(assessment, "trail").reason == UNASKED_REASON
    assert set(_items(assessment, UNASKED)) == {"docs", "trail"}
    config = load(root, machine=tmp_path / "m.toml")
    transition = promote(root, config, [], base=BASE, machine=tmp_path / "m.toml")
    assert "docs" not in transition.promoted and "trail" not in transition.promoted


def test_adopt_promote_never_enforces_a_gate_that_reads_an_untracked_file(tmp_path: Path) -> None:
    # Enforced, the gate would fail every pull request in CI, where the file is not. Named, it
    # holds the rest back and nothing is written; unnamed, every other gate that passes is
    # promoted and it stays advisory. Mutation (declared): `promote` judges the gates as they ran
    # here, and `docs` is enforced.
    root = smoke_repo(tmp_path)
    _unenforced(root)
    _untrack(root, AGENTS)
    machine = tmp_path / "m.toml"
    before = (root / "stayfixed.toml").read_text(encoding="utf-8")
    named = promote(root, load(root, machine=machine), ["docs"], base=BASE, machine=machine)
    assert named.promoted == () and named.unanswered == ("docs",)
    assert (root / "stayfixed.toml").read_text(encoding="utf-8") == before
    every = promote(root, load(root, machine=machine), [], base=BASE, machine=machine)
    assert "docs" not in every.promoted and "bugs" in every.promoted
    assert "docs" not in load(root, machine=machine).stayfixed.enforced


def test_adopt_promote_s_refusal_says_to_track_the_file_and_names_it(tmp_path: Path) -> None:
    # The note is the remedy: commit the file, or keep it out of git and stop running the gate.
    # It names the file, bounded, and names no value for `enforced`, which only a gate that
    # passed has earned. `--json` carries the files by gate. Mutation (declared): the note is
    # not printed.
    root = smoke_repo(tmp_path)
    _unenforced(root)
    _untrack(root, AGENTS)
    code, out, _ = cli(root, tmp_path, "adopt", "promote", "docs", "--base", _sha(root, BASE))
    assert code == 1, out
    assert "docs (could not run)" in out, out
    note = next(line for line in out.splitlines() if line.startswith("note: docs reads"))
    assert f"{AGENTS}, which CI's checkout will not have" in note, note
    assert "commit each file named" in note and "[gates] builtin" in note, note
    # An ignored file is the commonest case, and plain `git add` refuses one.
    assert "`git add -f`" in note, note
    assert "enforced =" not in note and "[stayfixed]" not in note, note
    code, out, _ = cli(
        root, tmp_path, "adopt", "promote", "docs", "--base", _sha(root, BASE), "--json"
    )
    data = json.loads(out)
    assert data["untracked"] == {"docs": [AGENTS]}, data
    assert data["unanswered"] == ["docs"], data


def test_stayfixed_gate_judges_the_disk_and_asks_git_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # `stayfixed gate` runs where CI checked out, and there an untracked file is simply absent,
    # which the gate's own finding covers. So it asks nothing about tracking: here, with the
    # file on disk, `docs` passes as it would have, and the tracked-files check asked git
    # nothing, not even whether this is a work tree. No mutation entry: the defect is a call
    # added to `gate_change`, not a line changed. Measured by hand instead: passing
    # `gate_change`'s results through `as_ci_sees` reddens this test.
    root = smoke_repo(tmp_path)
    _untrack(root, AGENTS)
    asked: list[str] = []

    def git_run(*args: object, **_kwargs: object) -> tuple[int, str]:
        asked.append(str(args))
        return -1, ""

    def in_work_tree(root: Path) -> bool:
        asked.append(f"in_work_tree({root})")
        return True

    monkeypatch.setattr(tracked, "git_run", git_run)
    monkeypatch.setattr(tracked, "in_work_tree", in_work_tree)
    code, out, _ = cli(root, tmp_path, "gate", "--builtin", "--base", _sha(root, BASE), "--json")
    rows = {r["name"]: r for r in json.loads(out)["gates"]}
    assert rows["docs"]["answered"] is True and rows["docs"]["failing"] is False, rows
    assert code == 0, out
    assert asked == []


def test_adopt_promote_s_note_on_a_git_that_gives_no_answer_says_how_to_see_why(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The command's own text, and not only the transition: the note is the no-answer item's
    # remedy, so a person learns to ask `git ls-files` here, and `--json` names no file as
    # untracked, since git said nothing either way. Mutation (declared): the note is not printed.
    root = smoke_repo(tmp_path)
    _unenforced(root)
    monkeypatch.setattr(tracked, "git_run", lambda *_a, **_k: (-1, ""))
    base = _sha(root, BASE)
    code, out, _ = cli(root, tmp_path, "adopt", "promote", "docs", "--base", base)
    assert code == 1, out
    note = next(line for line in out.splitlines() if line.startswith("note: git gave no answer"))
    assert note.startswith("note: git gave no answer to whether it tracks the files docs"), note
    assert note.endswith(UNASKED_REMEDY), note
    data = json.loads(cli(root, tmp_path, "adopt", "promote", "docs", "--base", base, "--json")[1])
    assert data["untracked"] == {} and data["unanswered"] == ["docs"], data


@pytest.mark.parametrize("refused", ["--cached", "--modified"])
def test_a_listing_git_refuses_after_naming_the_top_is_no_answer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, refused: str
) -> None:
    # git can name the work tree's top and then refuse the listing, a timeout or a broken index.
    # An empty listing read in its place would make every file untracked, with a reason saying
    # git does not track them, which it never said; an empty list of changed files would follow
    # every link as it is on disk. Mutations (declared): a failed listing, of either kind, is
    # read as an empty one.
    root = smoke_repo(tmp_path)

    def git_run(cwd: Path, *args: str, timeout: float) -> tuple[int, str]:
        return (-1, "") if refused in args else gitenv.git_run(cwd, *args, timeout=timeout)

    monkeypatch.setattr(tracked, "git_run", git_run)
    assessment = _assess(root, tmp_path)
    assert _row(assessment, "docs").reason == UNASKED_REASON
    assert set(_items(assessment, UNASKED)) == {"docs", "trail"}
    assert _items(assessment, UNTRACKED) == {}


def test_a_path_a_gate_answered_without_reaching_is_left_to_its_result(tmp_path: Path) -> None:
    # With no roadmap, the trail gate could not run (#33) and never asks for `trail.toml`, which
    # here is a symlink `contained()` refuses. The assessment asks nothing about a gate that did
    # not answer; asked anyway, the check is refused and leaves the gate to its result, which
    # already fails; the refusal never ends the run. Mutation (declared): the refusal is raised.
    root = smoke_repo(tmp_path)
    _unlink_roadmap(root)
    git(root, "rm", "-q", ROADMAP)
    trail = root / TRAIL
    trail.rename(root / "docs" / "states.toml")
    trail.symlink_to("states.toml")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "docs: no roadmap, and the states behind a link")
    assessment = _assess(root, tmp_path)
    row = _row(assessment, "trail")
    assert not row.answered and row.findings == (), row
    assert row.reason == COULD_NOT_RUN.format(command="docs trail --check"), row
    assert "trail" not in set(_items(assessment, UNTRACKED)) | set(_items(assessment, UNASKED))
    config = load(root, machine=tmp_path / "m.toml")
    assert tracked.unseen(root, config, (configured(config)["trail"],)) == ()


def test_a_name_that_reaches_no_file_is_never_the_same_file_as_another(tmp_path: Path) -> None:
    # The case check asks whether the name read and git's spelling reach one file. A name that
    # reaches nothing, which a race with the tree can leave, is not a case difference: the name
    # stays untracked, the answer that fails closed, and the question never ends the run.
    # Mutation (declared): a name that reaches nothing reads as the same file.
    (tmp_path / "there.md").write_text("# here\n", encoding="utf-8")
    assert not tracked._same_file(tmp_path / "gone.md", tmp_path / "there.md")
    assert tracked._same_file(tmp_path / "there.md", tmp_path / "there.md")
