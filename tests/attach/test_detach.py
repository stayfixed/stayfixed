"""`stayfixed detach` removes exactly what `attach` added, and nothing else.

The ledger is the authority on what was ours. Guessing it back from the content of a settings
file is the heuristic the ledger exists to replace, and a detach built on a guess removes a rule
the owner wrote by hand — which is worse than removing none.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path, PurePosixPath
from typing import Any

import pytest

from stayfixed import fsops, jsonobject
from stayfixed.attach.write import GROUP_UNASKED_IN_TREE, Detached, detach
from stayfixed.config.layout import ATTACH_LEDGER as LEDGER
from stayfixed.errors import Failure, Refusal
from stayfixed.memory.api import harness_memory_path, resolve
from stayfixed.printed import quoted
from stayfixed.project.init import init
from stayfixed.project.uninstall import uninstall
from stayfixed.scaffold import MANIFEST_PATH
from stayfixed.scaffold.regions import Style, extract
from tests.approved import record
from tests.attach.test_binding import DEFAULT_MEMORY
from tests.attach.test_links import _attach, _bound, _config, _trusted
from tests.attach.test_write import SETTINGS
from tests.gitfixture import git
from tests.parserlimits import LONG_NUMBER, NESTED, PAST_ENCODING, overflowing_indent
from tests.pathfaults import (
    ROOT_SEARCHES_EVERYTHING,
    symlink_loop_at,
    unsearchable,
)
from tests.runners import LsRemote, git_that_cannot_run
from tests.snapshot import (
    assert_snapshot_changed,
    assert_snapshot_unchanged,
    snapshot,
    tree_entries,
)

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")

RULE = "Bash(uv run pytest:*)"
ENTRY = {"type": "command", "command": "echo hello"}


def _grant(overlay: Path, *, allow: tuple[str, ...] = (), hooks: bool = False) -> None:
    claude = overlay / "common" / "claude"
    claude.mkdir(parents=True, exist_ok=True)
    (claude / "permissions.json").write_text(
        json.dumps({"permissions": {"allow": list(allow), "deny": []}}), encoding="utf-8"
    )
    (claude / "hooks.json").write_text(
        json.dumps({"hooks": {"SessionStart": [{"hooks": [ENTRY]}]} if hooks else {}}),
        encoding="utf-8",
    )
    (overlay / "common" / "codex").mkdir(parents=True, exist_ok=True)
    (overlay / "common" / "codex" / "common.rules").write_text("# rule\n", encoding="utf-8")


def _detach(root: Path, machine: Path, home: Path) -> Detached:
    return detach(root, machine=machine, home=home)


def test_detach_removes_exactly_what_attach_added(tmp_path: Path) -> None:
    # The round trip is the assertion: snapshot every file under the root, attach with
    # `confirmed=True`, detach, and compare against the snapshot. A detach that removes a rule
    # the owner wrote by hand is worse than one that removes none.
    root, store, machine = _bound(tmp_path)
    _grant(store.parents[2], allow=(RULE,), hooks=True)
    home = tmp_path / "home"
    before = snapshot(root)
    _attach(root, store, machine, home)
    assert_snapshot_changed(root, before)
    _detach(root, machine, home)
    assert_snapshot_unchanged(root, before)


def test_uninstall_after_a_real_detach_takes_the_footprint_back(tmp_path: Path) -> None:
    # The lifecycle's "uninstalled after a detach": `stayfixed uninstall` refuses an attached
    # repository, so what a detach leaves behind decides whether it runs at all. An `init`
    # footprint, a real attach that merged a rule and a hook entry, a detach, and the tree is the
    # one `init` left; `uninstall` then runs and takes the footprint back, and a second one finds
    # nothing to take. Mutation: `mutations/`'s "detach leaves its ledger behind".
    root, store, machine = _bound(tmp_path)
    init(root, machine=machine, runner=LsRemote(), yes=True, dry_run=False, ci=False)
    git(root, "add", "-A")
    git(root, "-c", "user.email=a@b.c", "-c", "user.name=a", "commit", "-qm", "footprint")
    initialised = snapshot(root)
    _grant(store.parents[2], allow=(RULE,), hooks=True)
    home = tmp_path / "home"
    _attach(root, store, machine, home)
    assert_snapshot_changed(root, initialised)
    _detach(root, machine, home)
    assert_snapshot_unchanged(root, initialised)
    uninstall(root, machine=machine, dry_run=False, force=())
    assert not (root / MANIFEST_PATH).exists() and not (root / LEDGER).exists()
    with pytest.raises(Refusal):
        uninstall(root, machine=machine, dry_run=False, force=())


def test_detach_leaves_a_rule_the_ledger_does_not_claim(tmp_path: Path) -> None:
    # Write an allow rule into settings.local.json by hand before attaching, attach, detach,
    # and assert that rule survives. The ledger is the authority on what was ours; content
    # heuristics are exactly what it exists to replace.
    root, store, machine = _bound(tmp_path)
    _grant(store.parents[2], allow=(RULE,))
    (root / ".claude").mkdir(exist_ok=True)
    (root / SETTINGS).write_text(
        json.dumps({"permissions": {"allow": ["Bash(rm:*)"]}}), encoding="utf-8"
    )
    home = tmp_path / "home"
    _attach(root, store, machine, home)
    _detach(root, machine, home)
    document = json.loads((root / SETTINGS).read_text(encoding="utf-8"))
    assert document["permissions"]["allow"] == ["Bash(rm:*)"]


def test_detach_leaves_a_hook_entry_that_was_never_marked(tmp_path: Path) -> None:
    # The same rule for the other half of the file. `scaffold.apply_entries` splits a group
    # rather than replacing it, so a developer's own entry beside stayfixed's survives — and
    # this is the command whose mistake would delete it.
    root, store, machine = _bound(tmp_path)
    _grant(store.parents[2], hooks=True)
    (root / ".claude").mkdir(exist_ok=True)
    (root / SETTINGS).write_text(
        json.dumps({"hooks": {"SessionStart": [{"hooks": [{"command": "mine.sh"}]}]}}),
        encoding="utf-8",
    )
    home = tmp_path / "home"
    _attach(root, store, machine, home)
    _detach(root, machine, home)
    document = json.loads((root / SETTINGS).read_text(encoding="utf-8"))
    commands = [e["command"] for g in document["hooks"]["SessionStart"] for e in g["hooks"]]
    assert commands == ["mine.sh"]


def test_detach_without_a_ledger_says_so_and_changes_nothing(tmp_path: Path) -> None:
    # A repository attached by an older version, or by hand. Guessing which rules were ours
    # from their content is the heuristic this ledger exists to avoid, so the answer is a
    # `Failure` naming the missing ledger, not a best effort.
    root, store, machine = _bound(tmp_path)
    _grant(store.parents[2], allow=(RULE,))
    home = tmp_path / "home"
    _attach(root, store, machine, home)
    (root / LEDGER).unlink()
    before = snapshot(root)
    # As in `test_a_mismatched_remote_refuses_and_writes_nothing`: `snapshot` is a walk and an
    # empty one satisfies the comparison below on its own.
    assert before
    with pytest.raises(Failure) as failed:
        _detach(root, machine, home)
    assert LEDGER in str(failed.value)
    assert_snapshot_unchanged(root, before)


def test_detach_withdraws_the_harness_link(tmp_path: Path) -> None:
    # The link that leaves stayfixed's gate is the one that must not outlive the binding — the
    # same asymmetry `worktree._unlink` already enforces in the other direction.
    root, store, machine = _bound(tmp_path)
    _grant(store.parents[2])
    home = tmp_path / "home"
    _attach(root, store, machine, home)
    resolved = resolve(root, _config(root, machine), machine=machine)
    assert resolved is not None
    record(resolved, _config(root, machine))
    _attach(root, store, machine, home)
    harness = harness_memory_path(root, home)
    assert harness.is_symlink()
    _detach(root, machine, home)
    assert not harness.is_symlink()
    assert not (root / "docs" / "memory" / "developer").is_symlink()


def test_detach_withdraws_the_link_tree_from_every_worktree(tmp_path: Path) -> None:
    # `attach` links into every existing worktree, so a detach that only cleaned the owning
    # checkout would leave every other one reading an overlay it is no longer bound to.
    root, store, machine = _bound(tmp_path)
    _grant(store.parents[2])
    side = tmp_path / "side"
    git(root, "worktree", "add", "-q", str(side), "-b", "side")
    home = tmp_path / "home"
    _attach(root, store, machine, home)
    assert (side / "docs" / "memory" / "developer").is_symlink()
    _detach(root, machine, home)
    assert not (side / "docs" / "memory" / "developer").is_symlink()


# --- a checkout another ledger still serves stays attached -----------------------------------


def _both_attached(tmp_path: Path) -> tuple[Path, Path, Path, Path, Path]:
    """The main checkout attached, its store approved, and a linked worktree attached after it,
    each with its harness memory link made by `attach` itself: the main checkout's to its own
    `paths.memory`, the worktree's to the main checkout's, which is where `attach` points every
    checkout's link. Asserted here, so no case below asserts about links that were never made.
    Returns `(root, side, store, machine, home)`."""
    root, store, machine = _bound(tmp_path)
    _grant(store.parents[2])
    side = tmp_path / "side"
    git(root, "worktree", "add", "-q", str(side), "-b", "side")
    home = tmp_path / "home"
    _attach(root, store, machine, home)
    _trusted(root, machine)
    _attach(root, store, machine, home)
    _attach(side, store, machine, home)
    assert (root / LEDGER).is_file() and (side / LEDGER).is_file()
    for checkout in (root, side):
        harness = harness_memory_path(checkout, home)
        assert harness.is_symlink() and harness.exists(), checkout
        assert harness.resolve() == (root / DEFAULT_MEMORY).resolve()
        assert (checkout / DEFAULT_MEMORY / "developer").is_symlink()
    return root, side, store, machine, home


def _dangling_under(home: Path) -> list[Path]:
    """Every link under the home's `.claude/projects/` that resolves to nothing."""
    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(home / ".claude" / "projects"):
        for name in (*dirnames, *filenames):
            path = Path(dirpath) / name
            if path.is_symlink() and not path.exists():
                found.append(path)
    return found


def test_detach_in_a_worktree_leaves_the_attached_main_checkout_whole(tmp_path: Path) -> None:
    # The main checkout attached, a worktree attached after it, and `detach` run in the worktree:
    # the main checkout still holds its ledger, and `detach` took its link tree and its harness
    # link anyway, leaving it half attached; and the worktree's own harness link, which points at
    # the main checkout's tree, was compared with the worktree's tree, never matched, and stayed
    # behind dangling. Mutation (oracle): `mutations/`'s "detach withdraws every checkout's tree
    # while another ledger still serves one" -> the main checkout's tree goes.
    root, side, _, machine, home = _both_attached(tmp_path)
    _detach(side, machine, home)
    assert (root / DEFAULT_MEMORY / "developer").is_symlink()
    assert harness_memory_path(root, home).exists()
    assert (root / LEDGER).is_file()
    assert not os.path.lexists(harness_memory_path(side, home))
    assert not (side / LEDGER).exists()
    assert not (side / DEFAULT_MEMORY / "developer").is_symlink()
    assert _dangling_under(home) == []


def test_detach_in_the_main_checkout_leaves_an_attached_worktree_whole(tmp_path: Path) -> None:
    # The other direction. The main checkout's tree is what the worktree's harness link points
    # at, so while the worktree's ledger stands it stays; only the main checkout's own harness
    # link, ledger, settings and rule copies go. A later `attach` anywhere rebuilds that tree
    # first, so keeping it loses nothing. Mutation (oracle): `mutations/`'s "detach takes the
    # owning checkout's tree while another ledger still serves it" -> the main checkout's tree
    # goes.
    root, side, _, machine, home = _both_attached(tmp_path)
    _detach(root, machine, home)
    assert (root / DEFAULT_MEMORY / "developer").is_symlink()
    assert not os.path.lexists(harness_memory_path(root, home))
    assert not (root / LEDGER).exists()
    assert (side / DEFAULT_MEMORY / "developer").is_symlink()
    assert harness_memory_path(side, home).exists()
    assert (side / LEDGER).is_file()
    assert _dangling_under(home) == []


def _relinked_to_its_own_tree(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    """`_both_attached`, with the worktree's harness memory link then made the way the
    `SessionStart` re-link makes it: `memory.worktree.link` handed the worktree's own store, which
    points the link at the worktree's own `paths.memory` rather than at the main checkout's. The
    gate that link asks is the worktree's own store's, so that store is approved first. Returns
    `(root, side, machine, home)`."""
    from stayfixed.memory.api import link

    root, side, _, machine, home = _both_attached(tmp_path)
    config = _config(side, machine)
    own = resolve(side, config, machine=machine)
    assert own is not None
    record(own, config)
    link(side, own, config, home=home)
    harness = harness_memory_path(side, home)
    # Non-vacuous: the link is the worktree's own tree now, the second directory a harness link
    # may point at and be stayfixed's.
    assert harness.is_symlink() and harness.exists()
    assert harness.resolve() == (side / DEFAULT_MEMORY).resolve()
    assert harness.resolve() != (root / DEFAULT_MEMORY).resolve()
    return root, side, machine, home


def test_detach_withdraws_a_worktree_harness_link_the_session_start_relink_made(
    tmp_path: Path,
) -> None:
    # A worktree's harness link is `attach`'s when it points at the main checkout's tree or at the
    # worktree's own, which is where the `SessionStart` re-link points it. Compared with the main
    # checkout's alone, the re-linked one was left standing and, once the worktree's tree went,
    # dangling. Mutation (oracle): `mutations/`'s "harness_targets names the owning checkout's
    # tree alone" -> the link stays and dangles.
    root, side, machine, home = _relinked_to_its_own_tree(tmp_path)
    _detach(side, machine, home)
    assert not os.path.lexists(harness_memory_path(side, home))
    assert _dangling_under(home) == []
    assert harness_memory_path(root, home).exists()


@pytest.mark.parametrize("run_in", ["main", "worktree", "lone"])
def test_a_second_detach_exits_one_and_writes_nothing(tmp_path: Path, run_in: str) -> None:
    # Run twice in one checkout: the first takes that checkout's ledger, so the second has nothing
    # to reverse and fails (exit 1) naming the missing ledger, with every checkout and every
    # harness link exactly as the first left them. From the main checkout and from the worktree
    # while the other is attached, and from a lone checkout, where the first takes everything.
    if run_in == "lone":
        root, store, machine = _bound(tmp_path)
        _grant(store.parents[2])
        home = tmp_path / "home"
        _attach(root, store, machine, home)
        _trusted(root, machine)
        _attach(root, store, machine, home)
        assert harness_memory_path(root, home).exists()
        checkouts: tuple[Path, ...] = (root,)
        target = root
    else:
        root, side, _, machine, home = _both_attached(tmp_path)
        checkouts = (root, side)
        target = root if run_in == "main" else side
    _detach(target, machine, home)
    before = tree_entries(*checkouts, home)
    # Non-vacuous: the walk sees what the first left — the other checkout's tree and harness
    # link, and its own tree's directory where it was the main checkout's.
    if run_in != "lone":
        other = side if run_in == "main" else root
        assert str(harness_memory_path(other, home)) in before
        assert any(path.endswith("developer") for path in before)
    else:
        assert str(root / "stayfixed.toml") in before
        assert not os.path.lexists(harness_memory_path(root, home))
    with pytest.raises(Failure) as failed:
        _detach(target, machine, home)
    assert LEDGER in str(failed.value)
    assert tree_entries(*checkouts, home) == before


@pytest.mark.parametrize("detached", ["worktree", "main"])
def test_a_main_checkout_tree_reached_through_a_symlink_refuses_before_anything_is_withdrawn(
    tmp_path: Path, detached: str
) -> None:
    # While another checkout's ledger stands, `detach` withdraws no tree but `--root`'s, so the
    # walk before the first withdrawal no longer reaches the main checkout's; but each harness
    # link is still compared with the main checkout's `paths.memory`, and that question was asked
    # from inside the withdrawal. With the main checkout's `docs` moved away and linked back, it
    # refused there, after the rule copies were gone: a refused `detach` that had removed some of
    # what it promises to remove all of or none of. Both directions: run in the worktree, and in
    # the main checkout, which keeps its own tree and whose configuration already refuses the
    # link when it is loaded, the twin that holds the refusal's place. From the worktree the
    # refusal names whose `paths.memory` it could not ask, which the raw `PathEscape` did not: it
    # read as the worktree's own. Mutation (oracle): `mutations/`'s "detach asks where a harness
    # link may point only once it has begun withdrawing".
    root, side, _, machine, home = _both_attached(tmp_path)
    moved = tmp_path / "moved-docs"
    shutil.move(root / "docs", moved)
    (root / "docs").symlink_to(moved, target_is_directory=True)
    run_in = side if detached == "worktree" else root
    # Non-vacuous: there is a rule copy to withdraw before the harness links are reached.
    assert (run_in / ".codex" / "rules").is_dir()
    assert any((run_in / ".codex" / "rules").iterdir())
    before = tree_entries(root, side, home)
    with pytest.raises(Refusal) as refused:
        _detach(run_in, machine, home)
    assert "symlink" in str(refused.value)
    if detached == "worktree":
        assert "the main checkout's paths.memory" in str(refused.value)
    assert str(tmp_path) not in str(refused.value)
    assert tree_entries(root, side, home) == before


def test_a_main_checkout_tree_that_is_a_symlink_loop_refuses_before_anything_is_withdrawn(
    tmp_path: Path,
) -> None:
    # Up to Python 3.12 `.resolve()` raised `RuntimeError` on a loop, and asking where the
    # worktree's harness link may point resolves the main checkout's `paths.memory`: `detach` from
    # the worktree ended in an internal error. It is the refusal above now, before the first
    # withdrawal, on every interpreter (`fsops.resolved`).
    root, side, _, machine, home = _both_attached(tmp_path)
    shutil.rmtree(root / DEFAULT_MEMORY)
    (root / DEFAULT_MEMORY).symlink_to(PurePosixPath(DEFAULT_MEMORY).name)
    before = tree_entries(root, side, home)
    with pytest.raises(Refusal) as refused:
        _detach(side, machine, home)
    assert "the main checkout's paths.memory" in str(refused.value)
    assert "symlink loop" in str(refused.value)
    assert tree_entries(root, side, home) == before


@pytest.mark.parametrize("loop", ["real", "stood-in"])
@pytest.mark.parametrize("checkout", ["lone-main", "worktree"])
def test_a_checkouts_own_paths_memory_that_is_a_symlink_loop_refuses_before_anything_is_withdrawn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, checkout: str, loop: str
) -> None:
    # The checkout `detach` runs in, with its own `paths.memory` a symlink loop: a lone main
    # checkout, and a linked worktree detached while the main checkout stays attached. The walk to
    # every path the withdrawal removes resolved that loop before anything asked where a harness
    # link may point, and up to Python 3.12 `.resolve()` raises `RuntimeError` there: `internal
    # error`, where the refusal that names the loop was documented. Nothing was removed, but the
    # run ended in a traceback. `stood-in` makes `.resolve()` of the loop raise as 3.11 does, so
    # every interpreter meets it. Mutation (oracle): `mutations/`'s "detach walks the trees it
    # withdraws before asking where a harness link may point" -> RuntimeError.
    if checkout == "lone-main":
        root, store, machine = _bound(tmp_path)
        _grant(store.parents[2])
        home = tmp_path / "home"
        _attach(root, store, machine, home)
        _trusted(root, machine)
        _attach(root, store, machine, home)
        checkouts: tuple[Path, ...] = (root,)
        run_in, whose = root, "the main checkout's"
    else:
        root, side, _, machine, home = _both_attached(tmp_path)
        checkouts = (root, side)
        run_in, whose = side, "the linked worktree's"
    shutil.rmtree(run_in / DEFAULT_MEMORY)
    if loop == "real":
        (run_in / DEFAULT_MEMORY).symlink_to(PurePosixPath(DEFAULT_MEMORY).name)
    else:
        symlink_loop_at(monkeypatch, run_in / DEFAULT_MEMORY)
    # Non-vacuous: there is a rule copy and a harness link to withdraw.
    assert any((run_in / ".codex" / "rules").iterdir())
    assert os.path.lexists(harness_memory_path(run_in, home))
    before = tree_entries(*checkouts, home)
    with pytest.raises(Refusal) as refused:
        _detach(run_in, machine, home)
    assert str(refused.value) == (
        f"where a harness memory link may point cannot be asked of {whose} paths.memory: "
        f"{DEFAULT_MEMORY!r} is a symlink loop"
    )
    assert tree_entries(*checkouts, home) == before


def test_detach_withdraws_the_settings_fallback_it_recorded(tmp_path: Path) -> None:
    # The fallback is a setting, not a link, so nothing expires it: if `detach` left it behind
    # the harness would keep reading the store of a repository that is no longer bound.
    root, store, machine = _bound(tmp_path)
    _grant(store.parents[2])
    home = tmp_path / "home"
    _attach(root, store, machine, home)
    resolved = resolve(root, _config(root, machine), machine=machine)
    assert resolved is not None
    record(resolved, _config(root, machine))
    harness_memory_path(root, home).mkdir(parents=True)
    _attach(root, store, machine, home)
    assert "autoMemoryDirectory" in (root / SETTINGS).read_text(encoding="utf-8")
    _detach(root, machine, home)
    assert not (root / SETTINGS).exists()


def test_detach_leaves_the_binding_record_in_place(tmp_path: Path) -> None:
    # `projects/<name>/project.toml` is a record of the owner's consent, not a piece of local
    # state. Re-attaching later must not re-ask for it, and a detach that deleted it would
    # turn every re-attach into a first attach.
    root, store, machine = _bound(tmp_path)
    _grant(store.parents[2])
    home = tmp_path / "home"
    _attach(root, store, machine, home)
    _detach(root, machine, home)
    assert (store.parent / "project.toml").is_file()
    assert (store.parents[2] / "common" / "memory" / "shared.md").is_file()


def test_detach_removes_a_rule_file_the_overlay_has_since_deleted(tmp_path: Path) -> None:
    # `attach` stays idempotent and reversible by `detach`, and the ledger is the only record
    # of what was placed. A rule file deleted from the overlay between two attaches is not
    # written by the second one and so drops out of a ledger built from that run alone — while
    # the copy the first attach made is still in `.codex/rules/`, where Codex reads it as a
    # standing instruction. Without the union, `detach` leaves it there for good.
    root, store, machine = _bound(tmp_path)
    _grant(store.parents[2])
    home = tmp_path / "home"
    _attach(root, store, machine, home)
    landed = root / ".codex" / "rules" / "common.rules"
    assert landed.is_file()
    (store.parents[2] / "common" / "codex" / "common.rules").unlink()
    _attach(root, store, machine, home)
    assert landed.is_file(), "the copy the first attach made is still here"
    _detach(root, machine, home)
    assert not landed.exists()


def _rewrite_ledger(root: Path, **fields: object) -> None:
    """The ledger a clone committed: `attach`'s own, with fields replaced.

    Built from a real one rather than by hand so that the case differs from a working detach in
    exactly the field under test. `.gitignore` does not untrack a file a clone committed, which
    is what makes this a state a fresh checkout can be in rather than a contrivance.
    """
    document = json.loads((root / LEDGER).read_text(encoding="utf-8"))
    document.update(fields)
    (root / LEDGER).write_text(json.dumps(document), encoding="utf-8")


def test_a_ledger_naming_a_file_attach_could_not_have_written_removes_nothing(
    tmp_path: Path,
) -> None:
    # The ledger is a record, not an authority. `fsops.remove_within` contains the removal to
    # the root — and `.github/workflows/`, `.pre-commit-config.yaml` and every source file are
    # inside it, so containment is not the guard that matters. The guard is that `attach` only
    # ever writes `.codex/rules/<file>`, so anything else in `rules` is a repository asking for
    # a deletion no attach could have earned.
    #
    # Mutation: `mutations/`'s "detach deletes whatever file the ledger names" — make
    # `_rule_is_writable` answer True unconditionally and the workflow file goes.
    root, store, machine = _bound(tmp_path)
    _grant(store.parents[2])
    home = tmp_path / "home"
    _attach(root, store, machine, home)
    workflow = root / ".github" / "workflows" / "ci.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text("on: push\n", encoding="utf-8")
    _rewrite_ledger(root, rules=[".github/workflows/ci.yml", ".codex/rules/common.rules"])
    before = snapshot(root)
    # `snapshot` is a walk, and an empty one satisfies the comparison below on its own.
    assert before
    with pytest.raises(Refusal):
        _detach(root, machine, home)
    assert_snapshot_unchanged(root, before)
    assert workflow.is_file()


def test_a_ledger_nested_past_the_parsers_reach_removes_nothing(tmp_path: Path) -> None:
    # A committed ledger nested deeper than `json.loads` follows ended `detach` in an internal
    # error. It is a ledger that cannot be read, so the run fails before it withdraws anything.
    # Mutation (oracle): `mutations/`'s "the JSON object reader lets a document nested past the
    # parser raise" -> `RecursionError`.
    root, store, machine = _bound(tmp_path)
    _grant(store.parents[2])
    home = tmp_path / "home"
    _attach(root, store, machine, home)
    (root / LEDGER).write_text('{"entries": ' + NESTED + "}", encoding="utf-8")
    before = snapshot(root)
    assert before
    with pytest.raises(Failure, match="nested deeper"):
        _detach(root, machine, home)
    assert_snapshot_unchanged(root, before)


def test_a_ledger_holding_a_number_past_the_parsers_reach_removes_nothing(tmp_path: Path) -> None:
    # A committed ledger holding an integer literal longer than the interpreter converts ended
    # `detach` in an internal error, `ValueError`. It is a ledger that cannot be read, so the run
    # fails before it withdraws anything. Mutation (oracle): `mutations/`'s "the JSON object
    # reader lets a number past the parser's reach raise" -> `ValueError`.
    root, store, machine = _bound(tmp_path)
    _grant(store.parents[2])
    home = tmp_path / "home"
    _attach(root, store, machine, home)
    (root / LEDGER).write_text('{"entries": {"x": ' + LONG_NUMBER + "}}", encoding="utf-8")
    before = snapshot(root)
    assert before
    with pytest.raises(Failure, match="number longer"):
        _detach(root, machine, home)
    assert_snapshot_unchanged(root, before)


@pytest.mark.parametrize("bound", ["real-depth", "cap-forced"])
def test_a_local_settings_file_past_the_encoder_is_refused_and_removes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, bound: str
) -> None:
    # On Python 3.14 the parser follows about 57,800 levels and `json.dumps` overflows near
    # 50,000, so a `settings.local.json` nested between the two parsed and then ended `detach` in
    # `internal error: RecursionError … while encoding a JSON object`, where 3.11 to 3.13 refuse
    # it as nested deeper than the reader follows. The reader now bounds the depth it follows, so
    # every interpreter refuses it in those words. `real-depth` is that file, and exercises the
    # bound only where the parser reaches it (3.14); `cap-forced` lowers the bound so the same
    # refusal is reached on every interpreter. Mutation (declared): the depth bound never refuses
    # -> `cap-forced` detaches.
    root, store, machine = _bound(tmp_path)
    _grant(store.parents[2])
    home = tmp_path / "home"
    _attach(root, store, machine, home)
    if bound == "cap-forced":
        monkeypatch.setattr(jsonobject, "DEPTH_CAP", 4)
        deep = "[" * 5 + "]" * 5
    else:
        deep = PAST_ENCODING
    (root / SETTINGS).parent.mkdir(exist_ok=True)
    (root / SETTINGS).write_text('{"x": ' + deep + "}", encoding="utf-8")
    before = snapshot(root)
    assert before
    with pytest.raises((Failure, Refusal), match="nested deeper than this reader follows"):
        _detach(root, machine, home)
    assert_snapshot_unchanged(root, before)


def test_a_ledger_claiming_the_permissions_key_never_drops_the_owners_deny_rules(
    tmp_path: Path,
) -> None:
    # The measured widening, and the reason this refusal is not a nicety. `_withdraw_settings`
    # assigns `raw["permissions"] = permissions` and *then* pops every string in
    # `settings_keys`, so a committed `settings_keys = ["permissions"]` took the owner's whole
    # permissions block out — deny rules included. A repository cannot be allowed to remove a
    # deny rule by committing a JSON file, whatever it calls that file.
    #
    # Mutation: the same entry as above, on the `settings_keys` half — let `_checked` accept a
    # key other than `autoMemoryDirectory` and the deny rule below is gone.
    root, store, machine = _bound(tmp_path)
    _grant(store.parents[2])
    home = tmp_path / "home"
    _attach(root, store, machine, home)
    (root / ".claude").mkdir(exist_ok=True)
    (root / SETTINGS).write_text(
        json.dumps({"permissions": {"allow": ["Bash(ls:*)"], "deny": ["Bash(curl:*)"]}}),
        encoding="utf-8",
    )
    _rewrite_ledger(root, settings_keys=["permissions"])
    with pytest.raises(Refusal):
        _detach(root, machine, home)
    document = json.loads((root / SETTINGS).read_text(encoding="utf-8"))
    assert document["permissions"]["deny"] == ["Bash(curl:*)"]
    assert document["permissions"]["allow"] == ["Bash(ls:*)"]


def test_the_two_values_attach_really_writes_are_still_acted_on(tmp_path: Path) -> None:
    # The vacuity guard for both refusals above: a validator that refused everything would pass
    # them and break the command. A ledger holding exactly what `attach` wrote — one
    # `.codex/rules/` file and the one fallback key — detaches, and both are withdrawn.
    root, store, machine = _bound(tmp_path)
    _grant(store.parents[2])
    home = tmp_path / "home"
    _attach(root, store, machine, home)
    resolved = resolve(root, _config(root, machine), machine=machine)
    assert resolved is not None
    record(resolved, _config(root, machine))
    harness_memory_path(root, home).mkdir(parents=True)
    _attach(root, store, machine, home)
    from stayfixed.attach.api import ledger as read_ledger

    recorded = read_ledger(root)
    assert recorded.rules == (".codex/rules/common.rules",)
    assert recorded.settings_keys == ("autoMemoryDirectory",)
    _detach(root, machine, home)
    assert not (root / ".codex" / "rules" / "common.rules").exists()
    assert not (root / SETTINGS).exists()


def test_a_git_that_cannot_run_is_answered_before_anything_is_withdrawn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # `detach` cannot refuse the way `attach` does once it has started — by the time it reaches
    # the link tree the settings and the rule files are gone, and refusing there strands a
    # half-detached repository. That is why `detach_main` checks `memory.mode` through the
    # target it derives rather than by refusing. It is not licence to *discover* a precondition
    # late: this one is a fact about the machine, true before the run began.
    #
    # `main_checkout` and `_worktrees` are the only things here that need `git`, and they sat
    # between the settings withdrawal and the link trees — so a machine whose `git` was gone got
    # exit 1 with `.claude/settings.local.json` and `.codex/rules/common.rules` already removed
    # and every link, the ignore region and the ledger still in place. Both are pure reads.
    #
    # Mutation: `mutations/`'s "detach asks git where the checkouts are after it has already
    # withdrawn".
    root, store, machine = _bound(tmp_path)
    _grant(store.parents[2], allow=(RULE,), hooks=True)
    home = tmp_path / "home"
    _attach(root, store, machine, home)
    before = snapshot(root)
    # `snapshot` is a walk, and an empty one satisfies the comparison below on its own.
    assert before
    git_that_cannot_run(monkeypatch)
    with pytest.raises(Failure):
        _detach(root, machine, home)
    assert_snapshot_unchanged(root, before)
    assert (root / "docs" / "memory" / "developer").is_symlink()


def test_the_git_failure_is_reached_on_a_run_that_would_have_withdrawn(tmp_path: Path) -> None:
    # The vacuity guard for the snapshot above: a refusal that withdraws nothing proves nothing
    # if the run had nothing to withdraw. The identical fixture, with a `git` that works,
    # withdraws every artifact the case above has to leave standing.
    root, store, machine = _bound(tmp_path)
    _grant(store.parents[2], allow=(RULE,), hooks=True)
    home = tmp_path / "home"
    _attach(root, store, machine, home)
    before = snapshot(root)
    assert before
    removed = _detach(root, machine, home)
    after = snapshot(root)
    gone = set(before) - set(after)
    assert {SETTINGS, ".codex/rules/common.rules", LEDGER} <= gone
    assert removed.allow_removed == (RULE,)
    assert not (root / "docs" / "memory" / "developer").is_symlink()


# --- the directories, which the file snapshot could not see -----------------------------------


def _directories(root: Path) -> set[str]:
    """Every directory under the root but `.git`, as `snapshot` would if it saw directories."""
    found: set[str] = set()
    for path in root.rglob("*"):
        if path.is_dir() and not path.is_symlink() and ".git" not in path.relative_to(root).parts:
            found.add(str(path.relative_to(root)))
    return found


def test_detach_removes_the_directories_the_attach_created(tmp_path: Path) -> None:
    # `docs/cli.md` promised "an attach and a detach leave the tree byte-for-byte as it was" and
    # it was false for directories: `.stayfixed/local/`, `.stayfixed/`, `.codex/rules/` and
    # `.codex/` survived every round trip. `snapshot` filters on `is_file()`, so the round-trip
    # test above passed while four directories accumulated.
    #
    # The set is asserted by value and not by `not any(...)`: a `_withdraw_directories` that
    # removed only the leaves, or only `.stayfixed/`, satisfies "something was removed" and
    # leaves the tree changed. `.claude/` is on the list too — the overlay here grants a rule,
    # so the attach creates it.
    #
    # Mutation: `mutations/`'s "detach leaves behind the directories the attach created".
    root, store, machine = _bound(tmp_path)
    _grant(store.parents[2], allow=(RULE,), hooks=True)
    home = tmp_path / "home"
    before = _directories(root)
    _attach(root, store, machine, home)
    # The walk the comparison below rests on, asserted non-empty before it is trusted: an
    # `rglob` that finds nothing would satisfy every equality in this case on its own.
    assert _directories(root) > before
    removed = _detach(root, machine, home)
    # `paths.memory` and the `docs/` above it are on the list too: the fixture had no `docs/`, so
    # the attach created both, and the detach takes back what it created once it is empty.
    memory = PurePosixPath(DEFAULT_MEMORY)
    assert set(removed.directories_removed) == {
        ".stayfixed/local",
        ".stayfixed",
        ".codex/rules",
        ".codex",
        ".claude",
        str(memory),
        str(memory.parent),
    }
    assert _directories(root) == before


def _detach_after_attach(root: Path, store: Path, machine: Path, home: Path) -> Detached:
    _attach(root, store, machine, home)
    return _detach(root, machine, home)


def test_detach_keeps_a_directory_that_still_holds_something(tmp_path: Path) -> None:
    # The floor under the ledger: the removal is `rmdir`, so a directory holding anything the
    # attach did not put there survives — and its parent survives with it, because a parent that
    # still holds a child is not empty either. A `shutil.rmtree` here would delete the owner's
    # own `.codex/rules/` file on a detach that promised to remove only what it added.
    root, store, machine = _bound(tmp_path)
    _grant(store.parents[2], allow=(RULE,), hooks=True)
    home = tmp_path / "home"
    _attach(root, store, machine, home)
    mine = root / ".codex" / "rules" / "zz-my-own.md"
    mine.write_text("# mine\n", encoding="utf-8")
    removed = _detach(root, machine, home)
    assert mine.is_file(), "a detach deleted a rule file the owner wrote by hand"
    assert ".codex/rules" not in removed.directories_removed
    assert ".codex" not in removed.directories_removed
    # And the ones that had nothing of the owner's in them still went.
    assert ".stayfixed" in removed.directories_removed


def test_detach_leaves_a_directory_that_was_there_before_the_attach(tmp_path: Path) -> None:
    # The other half, and the one the ledger answers rather than `rmdir`: an **empty** `.codex/`
    # the owner made themselves is indistinguishable from one this attach created, once the run
    # is over. `_absent_directories` is asked above the first write, so it is not on the ledger
    # and `detach` does not touch it — a detach must not remove a directory it did not create.
    root, store, machine = _bound(tmp_path)
    _grant(store.parents[2], allow=(RULE,), hooks=True)
    home = tmp_path / "home"
    (root / ".codex").mkdir()
    removed = _detach_after_attach(root, store, machine, home)
    assert (root / ".codex").is_dir(), "a detach removed a directory that predated the attach"
    assert ".codex" not in removed.directories_removed
    # `.codex/rules/` inside it was this attach's, and still goes.
    assert ".codex/rules" in removed.directories_removed
    assert not (root / ".codex" / "rules").exists()


def test_a_ledger_naming_a_directory_no_attach_creates_is_refused(tmp_path: Path) -> None:
    # `.stayfixed/local/attach.json` is a path a clone can commit, and `directories` drives
    # `rmdir`. It is held to the same closed list `rules` and `settings_keys` are held to, so a
    # ledger naming `src` is refused with nothing removed rather than obeyed — even though
    # `rmdir` would have spared a non-empty `src/` anyway. A partial defence reported as a
    # success is the shape this refusal exists to avoid.
    root, store, machine = _bound(tmp_path)
    _grant(store.parents[2], allow=(RULE,))
    home = tmp_path / "home"
    _attach(root, store, machine, home)
    recorded = json.loads((root / LEDGER).read_text(encoding="utf-8"))
    recorded["directories"] = ["src"]
    (root / LEDGER).write_text(json.dumps(recorded), encoding="utf-8")
    (root / "src").mkdir()
    before = snapshot(root)
    assert before
    with pytest.raises(Refusal):
        _detach(root, machine, home)
    assert (root / "src").is_dir()
    assert_snapshot_unchanged(root, before)


def test_a_home_that_is_not_there_refuses_above_every_withdrawal(tmp_path: Path) -> None:
    # A mistyped `--home` is asked about before the first withdrawal: asked from inside it, the
    # refusal arrived with `.codex/rules/` already deleted. Mutation (declared, `mutations/`'s
    # "detach discovers the harness anchor from inside the withdrawal"): the hoisted call goes ->
    # `assert_snapshot_unchanged` reddens with the rule files already removed.
    root, store, machine = _bound(tmp_path)
    _grant(store.parents[2], allow=(RULE,), hooks=True)
    _attach(root, store, machine, tmp_path / "home")
    before = snapshot(root)
    assert before
    with pytest.raises(Refusal, match="never creates the home directory itself"):
        _detach(root, machine, tmp_path / "no-such-home")
    assert_snapshot_unchanged(root, before)
    assert (root / LEDGER).is_file()
    assert (root / ".codex" / "rules").is_dir()


def test_detach_takes_back_the_exclude_block_the_empty_directories_and_the_harness_slug(
    tmp_path: Path,
) -> None:
    # Each is a thing `attach` made that a detach left behind: the block in `info/exclude`, the
    # empty `paths.memory` directory with the `docs/` it had to create above it, and the empty
    # `~/.claude/projects/<slug>/` the harness link sat in. Each is a name the run computes, and
    # each goes only when nothing else is in it.
    root, store, machine = _bound(tmp_path)
    _grant(store.parents[2], allow=(RULE,))
    home = tmp_path / "home"
    before = _directories(root)
    assert not (root / "docs").exists()
    _attach(root, store, machine, home)
    resolved = resolve(root, _config(root, machine), machine=machine)
    assert resolved is not None
    record(resolved, _config(root, machine))
    _attach(root, store, machine, home)
    harness = harness_memory_path(root, home)
    exclude = root / ".git" / "info" / "exclude"
    # Non-vacuous: each of the three exists before the detach.
    assert harness.is_symlink()
    assert extract(exclude.read_text(encoding="utf-8"), "attach", Style.HASH) is not None
    assert (root / DEFAULT_MEMORY).is_dir()
    _detach(root, machine, home)
    assert extract(exclude.read_text(encoding="utf-8"), "attach", Style.HASH) is None
    assert not (root / DEFAULT_MEMORY).exists()
    assert not (root / "docs").exists()
    assert not harness.parent.exists()
    assert _directories(root) == before


def test_the_settings_fallback_written_after_the_links_is_hidden_too(tmp_path: Path) -> None:
    # The fallback key is written after the links, into the settings file every run places and
    # hides in its one block above the first write, since Claude Code writes the plugin's entry
    # there too.
    from tests.attach.test_write import _check_ignore

    root, store, machine = _bound(tmp_path)
    _grant(store.parents[2])
    home = tmp_path / "home"
    _attach(root, store, machine, home)
    assert not (root / SETTINGS).exists()
    resolved = resolve(root, _config(root, machine), machine=machine)
    assert resolved is not None
    record(resolved, _config(root, machine))
    harness_memory_path(root, home).mkdir(parents=True)
    _attach(root, store, machine, home)
    # Non-vacuous: the fallback was taken, so the file exists and is this run's.
    assert "autoMemoryDirectory" in (root / SETTINGS).read_text(encoding="utf-8")
    assert _check_ignore(root, SETTINGS)
    # The block hides it, and `attach` wrote nothing into the fixture's tracked `.gitignore`.
    status = git(root, "status", "--porcelain", "--untracked-files=all")
    assert SETTINGS not in status


def _fallback_forced(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    """An attached repository whose store is approved and whose harness link cannot be made —
    a real directory already sits where it goes — so the next attach takes the settings-file
    fallback. Returns `(root, store, machine, home)` with no settings file written yet."""
    root, store, machine = _bound(tmp_path)
    _grant(store.parents[2])
    home = tmp_path / "home"
    _attach(root, store, machine, home)
    resolved = resolve(root, _config(root, machine), machine=machine)
    assert resolved is not None
    record(resolved, _config(root, machine))
    harness_memory_path(root, home).mkdir(parents=True)
    assert not (root / SETTINGS).exists()
    return root, store, machine, home


def test_a_symlinked_exclude_file_is_refused_first_when_only_the_fallback_needs_a_line(
    tmp_path: Path,
) -> None:
    # Every other path this run places is ignored already, so the only exclude line the run
    # needs is the settings file, which holds the fallback key. That need is known before the
    # first write, and so is the refusal of a symlinked exclude file.
    root, store, machine, home = _fallback_forced(tmp_path)
    exclude = root / ".git" / "info" / "exclude"
    held = [
        line for line in exclude.read_text(encoding="utf-8").splitlines() if SETTINGS not in line
    ]
    elsewhere = tmp_path / "exclude-elsewhere"
    elsewhere.write_text("\n".join([*held, "/.codex/rules/", ".stayfixed/"]) + "\n", "utf-8")
    exclude.unlink()
    exclude.symlink_to(elsewhere)
    overlay = store.parents[2]
    project_files, overlay_files = snapshot(root), snapshot(overlay)
    outside = elsewhere.read_bytes()
    with pytest.raises(Refusal) as refused:
        _attach(root, store, machine, home)
    assert "symlink" in str(refused.value)
    assert_snapshot_unchanged(root, project_files)
    assert_snapshot_unchanged(overlay, overlay_files)
    assert elsewhere.read_bytes() == outside
    assert not (root / SETTINGS).exists()


# --- the exclude block is shared by every checkout, and is taken back exactly ----------------


def _exclude_file(root: Path) -> Path:
    return root / ".git" / "info" / "exclude"


def test_detaching_one_checkout_keeps_the_block_another_attached_checkout_needs(
    tmp_path: Path,
) -> None:
    # The block lives in the exclude file every worktree shares, while the ledger, the settings
    # file and the `.codex/rules/` copies are per checkout. Detaching the main checkout took the
    # block away while a worktree was still attached, and `git status` there listed that
    # worktree's settings file and rule copy.
    #
    # Mutation: `mutations/`'s "detach takes the shared block while another checkout is
    # attached".
    root, store, machine = _bound(tmp_path)
    _grant(store.parents[2], allow=(RULE,))
    home = tmp_path / "home"
    side = tmp_path / "side"
    git(root, "worktree", "add", "-q", str(side), "-b", "side")
    _attach(root, store, machine, home)
    _attach(side, store, machine, home)
    # Non-vacuous: the worktree is attached, with files of its own for the block to hide.
    assert (side / LEDGER).is_file()
    assert (side / SETTINGS).is_file() and (side / ".codex" / "rules" / "common.rules").is_file()
    removed = _detach(root, machine, home)
    assert removed.exclude_block_kept is True
    assert removed.exclude_block_removed is False
    assert extract(_exclude_file(root).read_text(encoding="utf-8"), "attach", Style.HASH)
    status = git(side, "status", "--porcelain", "--untracked-files=all")
    assert SETTINGS not in status
    assert ".codex/rules/common.rules" not in status
    # The last attached checkout's detach takes the block.
    last = _detach(side, machine, home)
    assert last.exclude_block_removed is True and last.exclude_block_kept is False
    assert extract(_exclude_file(root).read_text(encoding="utf-8"), "attach", Style.HASH) is None


def test_an_exclude_file_attach_created_is_removed_by_detach(tmp_path: Path) -> None:
    # A repository whose `info/exclude` does not exist (`git init` with no templates) got one
    # from `attach`, and `detach` left it behind empty, against "a file left holding nothing is
    # removed rather than left empty".
    #
    # Mutation: `mutations/`'s "detach leaves the exclude file attach created".
    root, store, machine = _bound(tmp_path)
    _grant(store.parents[2], allow=(RULE,))
    home = tmp_path / "home"
    _exclude_file(root).unlink(missing_ok=True)
    _attach(root, store, machine, home)
    # Non-vacuous: the attach did create the file for its block.
    assert extract(_exclude_file(root).read_text(encoding="utf-8"), "attach", Style.HASH)
    _detach(root, machine, home)
    assert not _exclude_file(root).exists()


def test_an_exclude_file_that_was_there_and_empty_stays_there_and_empty(tmp_path: Path) -> None:
    # The other half: an empty file the owner had is the owner's, and survives the round trip.
    root, store, machine = _bound(tmp_path)
    _grant(store.parents[2], allow=(RULE,))
    home = tmp_path / "home"
    _exclude_file(root).write_bytes(b"")
    _attach(root, store, machine, home)
    assert extract(_exclude_file(root).read_text(encoding="utf-8"), "attach", Style.HASH)
    _detach(root, machine, home)
    assert _exclude_file(root).read_bytes() == b""


@pytest.mark.parametrize("ending", ["\n", "\r\n"], ids=["lf", "crlf"])
def test_an_exclude_file_with_no_final_line_ending_comes_back_without_one(
    tmp_path: Path, ending: str
) -> None:
    # The block starts on a line of its own, so `attach` ends the owner's last line first, and
    # `detach` left that line ending behind. The block records that it added one, and `detach`
    # takes it back when nothing follows the block.
    #
    # Mutation: `mutations/`'s "detach keeps the line ending attach added".
    root, store, machine = _bound(tmp_path)
    _grant(store.parents[2], allow=(RULE,))
    home = tmp_path / "home"
    held = f"# the owner's{ending}/owner-only".encode()
    _exclude_file(root).write_bytes(held)
    _attach(root, store, machine, home)
    # Non-vacuous: the attach wrote its block after a line it had to end.
    assert (
        _exclude_file(root)
        .read_bytes()
        .startswith(f"# the owner's{ending}/owner-only{ending}".encode())
    )
    # A second attach that rewrites the block carries the record along.
    _grant(store.parents[2], allow=(RULE, "Bash(ls:*)"))
    _attach(root, store, machine, home)
    _detach(root, machine, home)
    assert _exclude_file(root).read_bytes() == held


def test_a_line_the_owner_added_after_the_block_keeps_its_line_ending(tmp_path: Path) -> None:
    # The line ending `attach` added sits before the block; with the owner's own line after it,
    # taking it back would join two lines, so it stays.
    root, store, machine = _bound(tmp_path)
    _grant(store.parents[2], allow=(RULE,))
    home = tmp_path / "home"
    _exclude_file(root).write_bytes(b"/owner-only")
    _attach(root, store, machine, home)
    with _exclude_file(root).open("a", encoding="utf-8") as stream:
        stream.write("/added-later\n")
    _detach(root, machine, home)
    assert _exclude_file(root).read_bytes() == b"/owner-only\n/added-later\n"


def test_an_exclude_file_that_is_not_utf8_neither_blocks_attach_nor_detach(
    tmp_path: Path,
) -> None:
    # The exclude file is the owner's, and git reads it as bytes. Read as UTF-8 text, a byte
    # outside it -- a comment in Latin-1, say -- refused `attach` and `detach` both. Its bytes are
    # kept exactly, in the attach and in the round trip.
    #
    # Mutation: `mutations/`'s "the exclude file is read as UTF-8 text".
    root, store, machine = _bound(tmp_path)
    _grant(store.parents[2], allow=(RULE,))
    home = tmp_path / "home"
    held = "# propriété de l'équipe\n/owner-only\n".encode("latin-1")
    _exclude_file(root).write_bytes(held)
    _attach(root, store, machine, home)
    written = _exclude_file(root).read_bytes()
    assert written.startswith(held)
    assert b"# stayfixed:attach:begin" in written
    _detach(root, machine, home)
    assert _exclude_file(root).read_bytes() == held


def test_the_exclude_file_refusals_print_the_path_through_the_quoting_rule(
    tmp_path: Path,
) -> None:
    # The checkout's directory name usually comes from the clone URL, so the exclude file's path
    # is printed through `printed.quoted`, which escapes a line break or an escape sequence in
    # it, as the store's refusals already print theirs.
    #
    # Mutation: `mutations/`'s "the exclude file's symlink refusal prints its path raw".
    from stayfixed.attach.exclude import planned_block

    root = tmp_path / "clone\n::error::x"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    exclude = _exclude_file(root)
    exclude.unlink(missing_ok=True)
    exclude.symlink_to(tmp_path / "elsewhere")
    with pytest.raises(Refusal) as refused:
        planned_block(root, ["placed"])
    assert "symlink" in str(refused.value)
    assert "\n" not in str(refused.value)


# --- the directories above and at `paths.memory` come back as they were ----------------------


def test_an_empty_docs_directory_the_owner_had_survives_the_round_trip(tmp_path: Path) -> None:
    # `attach` records which directories above `paths.memory` it created, and `detach` removes
    # only those: an empty `docs/` the owner already had is not the attach's. Nothing tested that
    # half, so dropping the record check left every test green.
    #
    # Mutation: `mutations/`'s "detach removes a directory above paths.memory it never made".
    root, store, machine = _bound(tmp_path)
    _grant(store.parents[2], allow=(RULE,))
    home = tmp_path / "home"
    parent = root / PurePosixPath(DEFAULT_MEMORY).parts[0]
    parent.mkdir()
    _attach(root, store, machine, home)
    # Non-vacuous: the attach built its tree below it, so the detach had an empty `docs/` to take.
    assert (root / DEFAULT_MEMORY).is_dir()
    _detach(root, machine, home)
    assert not (root / DEFAULT_MEMORY).exists()
    assert parent.is_dir()


def test_an_empty_memory_directory_the_owner_had_survives_the_round_trip(tmp_path: Path) -> None:
    # `detach` removed `paths.memory` whenever it was empty, and so took an empty directory the
    # owner had made before the attach, against a round trip documented as byte for byte. The
    # ledger now records whether the attach created it.
    #
    # Mutation: `mutations/`'s "detach removes a paths.memory it never made".
    root, store, machine = _bound(tmp_path)
    _grant(store.parents[2], allow=(RULE,))
    home = tmp_path / "home"
    (root / DEFAULT_MEMORY).mkdir(parents=True)
    _attach(root, store, machine, home)
    # A second attach finds the directory there, and must not forget whose it is.
    _attach(root, store, machine, home)
    assert (root / DEFAULT_MEMORY / "MEMORY.md").is_symlink()
    _detach(root, machine, home)
    assert (root / DEFAULT_MEMORY).is_dir()
    assert list((root / DEFAULT_MEMORY).iterdir()) == []


# --- every refusal is made before the first withdrawal ----------------------------------------


def _withdrawable(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    root, store, machine = _bound(tmp_path)
    _grant(store.parents[2], allow=(RULE,), hooks=True)
    home = tmp_path / "home"
    _attach(root, store, machine, home)
    assert (root / SETTINGS).is_file()
    return root, store, machine, home


def test_a_codex_directory_linked_in_after_attach_refuses_before_anything_is_withdrawn(
    tmp_path: Path,
) -> None:
    # A `.codex` that became a symlink after the attach was found by the removal of the first rule
    # copy, after `.claude/settings.local.json` was withdrawn: `internal error: UnsafePath`, with
    # the settings gone, the links and the ledger in place, and every later run failing at the
    # same line. Each recorded rule copy is held to the project while the run is planned now.
    #
    # Mutation: `mutations/`'s "detach finds a linked .codex by removing through it".
    root, _store, machine, home = _withdrawable(tmp_path)
    elsewhere = tmp_path / "codex-elsewhere"
    shutil.move(root / ".codex", elsewhere)
    (root / ".codex").symlink_to(elsewhere)
    before = snapshot(root)
    with pytest.raises(Refusal) as refused:
        _detach(root, machine, home)
    assert ".codex" in str(refused.value)
    assert_snapshot_unchanged(root, before)


@pytest.mark.parametrize("group", ["a//b", "../../x"])
def test_a_group_added_since_the_attach_refuses_before_anything_is_withdrawn(
    tmp_path: Path, group: str
) -> None:
    # A `memory.groups` entry added after the attach that is not one plain directory name was
    # found by the link tree's withdrawal, after the settings, the rule copies and the earlier
    # links were withdrawn, and the refusal printed the entry through `repr`. It is held to the
    # link tree while the run is planned now, and the refusal counts it rather than quoting it:
    # the entry is the repository's.
    #
    # Mutation: `mutations/`'s "detach finds an escaping group by withdrawing the tree".
    root, _store, machine, home = _withdrawable(tmp_path)
    text = (root / "stayfixed.toml").read_text(encoding="utf-8")
    (root / "stayfixed.toml").write_text(
        text.replace('groups = ["developer", "project-stable"]', f'groups = ["{group}"]'),
        encoding="utf-8",
    )
    before = snapshot(root)
    with pytest.raises(Refusal) as refused:
        _detach(root, machine, home)
    assert group not in str(refused.value)
    assert_snapshot_unchanged(root, before)


@ROOT_SEARCHES_EVERYTHING
def test_a_link_tree_nobody_may_search_refuses_for_that_before_anything_is_withdrawn(
    tmp_path: Path,
) -> None:
    # Every entry is one plain name and no link is on the way: the link tree itself cannot be
    # searched, so whether a group's place is a link cannot be asked. "is not one directory name"
    # and its remedy, taking the entry out, named a cause the entry did not have.
    #
    # Mutation (oracle): `mutations/`'s "detach words a group it cannot ask about as one that
    # leaves the tree".
    root, _store, machine, home = _withdrawable(tmp_path)
    before = snapshot(root)
    with unsearchable(root / DEFAULT_MEMORY), pytest.raises(Refusal) as refused:
        _detach(root, machine, home)
    assert str(refused.value) == GROUP_UNASKED_IN_TREE.format(fault="Permission denied")
    assert_snapshot_unchanged(root, before)


def test_a_doubled_exclude_block_refuses_detach_naming_the_exclude_file(tmp_path: Path) -> None:
    # The same refusal `attach` makes, and the same missing file name.
    #
    # Mutation: `mutations/`'s "a doubled exclude block is refused without its file".
    root, _store, machine, home = _withdrawable(tmp_path)
    path = _exclude_file(root)
    begin = "# stayfixed:attach:begin\n"
    path.write_text(path.read_text(encoding="utf-8") + begin, encoding="utf-8")
    before = snapshot(root)
    with pytest.raises(Refusal) as refused:
        _detach(root, machine, home)
    assert "info/exclude" in str(refused.value)
    assert_snapshot_unchanged(root, before)


@pytest.mark.skipif(os.geteuid() == 0, reason="root writes into a directory it cannot write")
def test_an_exclude_file_detach_cannot_write_is_refused_before_anything_is_withdrawn(
    tmp_path: Path,
) -> None:
    # A `.git/info` this user cannot write: `detach` found out by writing the exclude file, after
    # the settings file, the rule copies and the link tree were withdrawn, and stopped there with
    # the ledger and the block still in place, half detached. It is asked while nothing has been
    # withdrawn now, as `attach` asks it, and refused naming the file. Mutation (oracle):
    # `mutations/`'s "detach finds out the exclude file cannot be written by writing it" -> the
    # settings file and the rule copies go.
    root, _store, machine, home = _withdrawable(tmp_path)
    info = _exclude_file(root).parent
    # Non-vacuous: there is a block to take out, and a settings file and rule copies before it.
    assert "stayfixed:attach:begin" in _exclude_file(root).read_text(encoding="utf-8")
    assert (root / SETTINGS).is_file()
    assert any((root / ".codex" / "rules").iterdir())
    before = tree_entries(root, home)
    info.chmod(0o555)
    try:
        with pytest.raises(Refusal) as refused:
            _detach(root, machine, home)
    finally:
        info.chmod(0o755)
    assert str(refused.value) == (
        f"{quoted(str(_exclude_file(root)))} cannot be written, because this user cannot write "
        "the directory that holds it, so nothing was written"
    )
    assert tree_entries(root, home) == before


def test_detach_writes_nothing_through_an_exclude_file_that_became_a_symlink(
    tmp_path: Path,
) -> None:
    # `attach` never writes through a symlinked exclude file, so a block behind one is not one it
    # put there, and `detach` leaves the link and the file it points at alone rather than reading
    # the block through it and replacing the link with a regular file.
    #
    # Mutation: `mutations/`'s "detach reads the block through a symlinked exclude file".
    root, _store, machine, home = _withdrawable(tmp_path)
    path = _exclude_file(root)
    elsewhere = tmp_path / "dotfiles-exclude"
    shutil.move(path, elsewhere)
    path.symlink_to(elsewhere)
    held = elsewhere.read_bytes()
    assert b"stayfixed:attach:begin" in held
    detached = _detach(root, machine, home)
    assert path.is_symlink()
    assert elsewhere.read_bytes() == held
    assert not detached.exclude_block_removed


def test_an_exclude_file_ending_in_a_lone_carriage_return_keeps_its_last_pattern(
    tmp_path: Path,
) -> None:
    # git ends a line at `\n` alone, so an exclude file ending `/zz\r` holds the pattern `/zz` on
    # an unended last line. The block was read as starting a new line after the `\r`, so its first
    # marker was glued onto that line and `zz` showed in `git status` while the repository was
    # attached. The file comes back byte for byte on detach.
    #
    # Mutations: `mutations/`'s "a hash region reads a lone carriage return as a line end",
    # "the exclude block reads a lone carriage return as a line end" and "detach leaves the
    # newline it added after a lone carriage return".
    root, store, machine = _bound(tmp_path)
    _grant(store.parents[2], allow=(RULE,))
    home = tmp_path / "home"
    held = b"/qq\n/zz\r"
    _exclude_file(root).write_bytes(held)
    (root / "zz").write_text("mine\n", encoding="utf-8")
    assert "zz" not in git(root, "status", "--porcelain")
    _attach(root, store, machine, home)
    assert "zz" not in git(root, "status", "--porcelain")
    _detach(root, machine, home)
    assert _exclude_file(root).read_bytes() == held


@pytest.mark.parametrize("kind", ["committed", "unreadable"])
def test_a_ledger_no_attach_of_that_checkout_wrote_does_not_keep_the_block(
    tmp_path: Path, kind: str
) -> None:
    # The block stays while another checkout still holds a ledger, and any file at the ledger's
    # path counted: a clone that committed `.stayfixed/local/attach.json` has it in every
    # worktree, and one that will not parse records no attach, so the block was kept for good.
    # Only an untracked ledger that reads as one counts now.
    #
    # Mutations: `mutations/`'s "detach counts a committed ledger as another attach" and
    # "detach counts an unreadable ledger as another attach".
    root, store, machine = _bound(tmp_path)
    _grant(store.parents[2], allow=(RULE,))
    home = tmp_path / "home"
    side = tmp_path / "side"
    _attach(root, store, machine, home)
    if kind == "committed":
        git(root, "add", "-f", LEDGER)
        git(root, "commit", "-qm", "a ledger somebody committed")
        git(root, "worktree", "add", "-q", str(side), "-b", "side")
    else:
        git(root, "worktree", "add", "-q", str(side), "-b", "side")
        (side / LEDGER).parent.mkdir(parents=True)
        (side / LEDGER).write_text("{not json", encoding="utf-8")
    # Non-vacuous: the other checkout has a file at the ledger's path.
    assert (side / LEDGER).is_file()
    removed = _detach(root, machine, home)
    assert removed.exclude_block_kept is False
    assert removed.exclude_block_removed is True


def test_an_info_directory_attach_created_is_removed_by_detach(tmp_path: Path) -> None:
    # A repository made without git's templates has no `.git/info/` at all, and the write of the
    # exclude file created it; `detach` removed the file and left the directory behind. The block
    # records that its directory was created for it, and `detach` takes the directory back when
    # it is empty.
    #
    # Mutation: `mutations/`'s "detach leaves the info directory attach created".
    root, store, machine = _bound(tmp_path)
    _grant(store.parents[2], allow=(RULE,))
    home = tmp_path / "home"
    info = _exclude_file(root).parent
    shutil.rmtree(info)
    _attach(root, store, machine, home)
    # Non-vacuous: the attach did create the directory for its block.
    assert _exclude_file(root).is_file()
    _detach(root, machine, home)
    assert not info.exists()


def test_an_info_directory_the_owner_had_survives_detach(tmp_path: Path) -> None:
    # The other half: a directory that was there before the attach, even empty, is not the
    # attach's to take.
    root, store, machine = _bound(tmp_path)
    _grant(store.parents[2], allow=(RULE,))
    home = tmp_path / "home"
    info = _exclude_file(root).parent
    _exclude_file(root).unlink()
    assert info.is_dir() and not any(info.iterdir())
    _attach(root, store, machine, home)
    _detach(root, machine, home)
    assert info.is_dir()


@pytest.mark.parametrize(
    "linked",
    [DEFAULT_MEMORY, ".stayfixed", ".stayfixed/local", ".claude"],
    ids=["paths-memory", "stayfixed", "stayfixed-local", "claude"],
)
def test_a_directory_linked_in_after_attach_refuses_before_anything_is_withdrawn(
    tmp_path: Path, linked: str
) -> None:
    # Each removal `detach` makes is a walk that refuses a symlinked component, and the check made
    # before the first withdrawal was not that walk: it held `paths.memory` with its last
    # component allowed to be a link, and asked nothing of the ledger's or the settings file's
    # path. So `paths.memory`, `.stayfixed` or `.stayfixed/local` moved away and linked back ended
    # as `internal error: UnsafePath` with the settings file already withdrawn. Every removal
    # target is walked first now, and the refusal says which one.
    #
    # Mutations: `mutations/`'s "detach walks to the ledger only when it removes it", "detach
    # walks to the settings file only when it rewrites it" and "detach walks to a link-tree name
    # only when it removes it".
    root, _store, machine, home = _withdrawable(tmp_path)
    elsewhere = tmp_path / ("moved-" + linked.replace("/", "-"))
    shutil.move(root / linked, elsewhere)
    (root / linked).symlink_to(elsewhere, target_is_directory=True)
    before = snapshot(root)
    with pytest.raises(Refusal) as refused:
        _detach(root, machine, home)
    assert "symlink" in str(refused.value)
    assert "internal error" not in str(refused.value)
    assert_snapshot_unchanged(root, before)


def test_a_rule_copy_that_is_itself_a_symlink_is_withdrawn(tmp_path: Path) -> None:
    # The copy's own name being a link is not a link on the way to it: the removal unlinks the
    # name and follows nothing, as it did before the check above existed, which refused this
    # with a sentence that blamed `.codex`.
    #
    # Mutation: `mutations/`'s "detach refuses a rule copy that is itself a symlink".
    root, _store, machine, home = _withdrawable(tmp_path)
    rule = root / ".codex" / "rules" / "common.rules"
    mine = tmp_path / "mine.rules"
    shutil.copy(rule, mine)
    rule.unlink()
    rule.symlink_to(mine)
    detached = _detach(root, machine, home)
    assert ".codex/rules/common.rules" in detached.rules_removed
    assert not rule.is_symlink()
    assert mine.is_file()


def test_a_settings_file_detach_withdraws_nothing_from_is_not_rewritten(tmp_path: Path) -> None:
    # An overlay that grants nothing gives `attach` nothing to write into the settings file, and
    # `detach` then has nothing to take back out of it. Rewritten anyway, the file came back in
    # another layout, a change to somebody's file the round trip promises not to make, and under
    # the plugin's own entry Claude Code keeps there. A file with nothing to withdraw is not
    # written at all.
    #
    # Mutation: `mutations/`'s "detach rewrites a settings file it withdraws nothing from".
    root, store, machine = _bound(tmp_path)
    _grant(store.parents[2])
    home = tmp_path / "home"
    (root / ".claude").mkdir()
    (root / SETTINGS).write_text('{"theme": "dark"}', encoding="utf-8")
    _attach(root, store, machine, home)
    _detach(root, machine, home)
    assert (root / SETTINGS).read_text(encoding="utf-8") == '{"theme": "dark"}'
    assert not (root / LEDGER).exists()


def test_a_local_settings_file_read_but_too_deep_to_write_back_is_refused_or_withdrawn(
    tmp_path: Path,
) -> None:
    # 3,000 levels: read by every supported parser but 3.11's, and past 3.12's indenting encoder,
    # so `detach` read it there and then ended in `RecursionError` writing it back. Every
    # interpreter now either withdraws what `attach` wrote or refuses before removing anything.
    # Real depth, so it reddens on 3.12 in CI;
    # `test_a_local_settings_write_back_the_encoder_cannot_follow_is_refused_and_removes_nothing`
    # proves the arm on every interpreter, for the oracle.
    root, store, machine = _bound(tmp_path)
    _grant(store.parents[2])
    home = tmp_path / "home"
    _attach(root, store, machine, home)
    (root / SETTINGS).parent.mkdir(exist_ok=True)
    (root / SETTINGS).write_text('{"x": ' + "[" * 3_000 + "]" * 3_000 + "}", encoding="utf-8")
    before = snapshot(root)
    try:
        _detach(root, machine, home)
    except (Failure, Refusal) as refused:
        assert "nested deeper than this reader follows" in str(refused)
        assert_snapshot_unchanged(root, before)


def test_a_local_settings_write_back_the_encoder_cannot_follow_is_refused_and_removes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Forced on every interpreter: the encode that writes the withdrawn settings back overflowing,
    # as it does on Python 3.12 near 994 levels. No single mutation reddens it, and that is the
    # point: two layers answer the overflow, `json_text` and the guard around `detach`'s copy and
    # comparison, and each is proven alone -- `mutations/`'s "the JSON writer lets an encode past
    # the interpreter's recursion escape" -> by the engine's forced case; "detach copies and
    # compares the settings document unguarded" -> by
    # `test_a_settings_document_too_deep_to_copy_or_compare_is_refused_and_removes_nothing`.
    root, store, machine = _bound(tmp_path)
    _grant(store.parents[2])
    home = tmp_path / "home"
    _attach(root, store, machine, home)
    (root / SETTINGS).parent.mkdir(exist_ok=True)
    (root / SETTINGS).write_text('{"theme": "dark"}', encoding="utf-8")
    before = snapshot(root)
    assert before
    monkeypatch.setattr(jsonobject, "_encode", overflowing_indent)
    monkeypatch.setattr(json, "dumps", overflowing_indent)
    with pytest.raises(Refusal, match="nested deeper than this reader follows"):
        _detach(root, machine, home)
    assert_snapshot_unchanged(root, before)


def test_a_local_settings_file_linked_to_a_device_stops_detach_before_it_removes_anything(
    tmp_path: Path,
) -> None:
    # `detach` reads `.claude/settings.local.json` to take back what `attach` merged into it, and
    # read a link to a device through: `/dev/null` read as an empty file and the run went on.
    # Only a regular file is read, so it stops before it removes anything. Mutation (declared):
    # `mutations/`'s "the settings reader reads a file through any link".
    root, store, machine = _bound(tmp_path)
    _grant(store.parents[2])
    home = tmp_path / "home"
    _attach(root, store, machine, home)
    settings = root / SETTINGS
    settings.parent.mkdir(exist_ok=True)
    if settings.exists():
        settings.unlink()
    settings.symlink_to("/dev/null")
    before = snapshot(root)
    assert before
    with pytest.raises(Failure, match=r"settings\.local\.json cannot be read"):
        _detach(root, machine, home)
    assert_snapshot_unchanged(root, before)


def test_a_ledger_linked_to_a_device_stops_detach_and_is_never_read(tmp_path: Path) -> None:
    # `detach` reads the ledger with no check before it, and a clone can commit the ledger: a link
    # there to `/dev/zero` read until memory ran out. Only a regular file is read, and the refusal
    # names the ledger as the project names it, never the machine's path. `/dev/null` tells the
    # guard apart without hanging: read, it is an empty ledger, "not valid JSON". Mutation
    # (declared): `mutations/`'s "the attach ledger is read through any link".
    root, store, machine = _bound(tmp_path)
    _grant(store.parents[2])
    home = tmp_path / "home"
    _attach(root, store, machine, home)
    (root / LEDGER).unlink()
    (root / LEDGER).symlink_to("/dev/null")
    before = snapshot(root)
    with pytest.raises(Failure) as refused:
        _detach(root, machine, home)
    assert str(refused.value) == f"{LEDGER} cannot be read (not a regular file)"
    assert_snapshot_unchanged(root, before)


def test_a_ledger_that_is_not_utf8_is_named_as_the_project_names_it(tmp_path: Path) -> None:
    # The ledger's other refusal, held to the rule its first one keeps: the project's own name for
    # the file, never the machine's path. Mutation (oracle): `mutations/`'s "the ledger refusal of
    # a file that is not UTF-8 prints the path it opened".
    root, store, machine = _bound(tmp_path)
    _grant(store.parents[2])
    home = tmp_path / "home"
    _attach(root, store, machine, home)
    (root / LEDGER).write_bytes(b'{"entries": {"\xff": "PreToolUse"}}')
    before = snapshot(root)
    with pytest.raises(Failure) as refused:
        _detach(root, machine, home)
    assert str(refused.value) == f"{LEDGER} is not UTF-8 text"
    assert_snapshot_unchanged(root, before)


class _ComparedTooDeep(dict[str, object]):
    """A parsed settings document whose comparison overflows, as `==` does on Python 3.14 for a
    document a few thousand levels deep under a reduced stack (`ulimit -s 2048`)."""

    def __eq__(self, other: object) -> bool:
        raise RecursionError

    __hash__ = None


@pytest.mark.parametrize("step", ["copy", "compare"])
def test_a_settings_document_too_deep_to_copy_or_compare_is_refused_and_removes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, step: str
) -> None:
    # `detach` copies the parsed settings document through `json.dumps` and compares what is
    # left with it, and neither step was guarded: on Python 3.14 under a reduced stack a document
    # the parser read raised `RecursionError` at either, an internal error. Forced at each step
    # here; both are the reader's refusal of a document nested too deep. Mutation (declared):
    # `mutations/`'s "detach copies and compares the settings document unguarded".
    root, store, machine = _bound(tmp_path)
    _grant(store.parents[2])
    home = tmp_path / "home"
    _attach(root, store, machine, home)
    (root / SETTINGS).parent.mkdir(exist_ok=True)
    (root / SETTINGS).write_text('{"theme": "dark"}', encoding="utf-8")
    before = snapshot(root)
    if step == "copy":
        real_dumps = json.dumps

        def dumps(value: object, *args: Any, **kwargs: Any) -> str:
            if not args and not kwargs:
                raise RecursionError
            return real_dumps(value, *args, **kwargs)

        monkeypatch.setattr(json, "dumps", dumps)
    else:
        real_loads = json.loads

        def loads(text: str, **kwargs: Any) -> object:
            loaded = real_loads(text, **kwargs)
            return _ComparedTooDeep(loaded) if isinstance(loaded, dict) else loaded

        monkeypatch.setattr(json, "loads", loads)
    with pytest.raises(Refusal, match="nested deeper than this reader follows"):
        _detach(root, machine, home)
    assert_snapshot_unchanged(root, before)


def test_a_settings_write_back_past_the_read_cap_is_refused_and_removes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # `detach` writes the withdrawn settings back indented, which can make a file the reader's
    # cap admits one it refuses: written, every later read of it refused. `jsonobject.json_text`
    # refuses such a write-back, so `detach` stops before it removes anything. The cap is lowered
    # so the document is small. Mutation (oracle): `mutations/`'s "the JSON writer writes back a
    # text past the read cap" -> `detach` writes it.
    root, store, machine = _bound(tmp_path)
    _grant(store.parents[2])
    home = tmp_path / "home"
    _attach(root, store, machine, home)
    settings = root / SETTINGS
    settings.parent.mkdir(exist_ok=True)
    document = {"theme": "dark", "a": [[[[[[[[[[[] for _ in range(1_000)]]]]]]]]]]}
    settings.write_text(json.dumps(document, separators=(",", ":")), encoding="utf-8")
    monkeypatch.setattr(fsops, "REGULAR_READ_LIMIT", 16 * 1024)
    before = snapshot(root)
    with pytest.raises(Refusal, match=jsonobject.WRITTEN_PAST):
        _detach(root, machine, home)
    assert_snapshot_unchanged(root, before)
