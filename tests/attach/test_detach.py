"""`stayfixed detach` removes exactly what `attach` added, and nothing else.

The ledger is the authority on what was ours. Guessing it back from the content of a settings
file is the heuristic the ledger exists to replace, and a detach built on a guess removes a rule
the owner wrote by hand — which is worse than removing none.
"""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable
from pathlib import Path, PurePosixPath

import pytest

from stayfixed import jsonobject
from stayfixed.attach.write import GITIGNORE, Detached, detach
from stayfixed.config.layout import ATTACH_LEDGER as LEDGER
from stayfixed.config.layout import IGNORE_BODY, IGNORE_REGION
from stayfixed.errors import Failure, Refusal
from stayfixed.memory.api import harness_memory_path, resolve
from stayfixed.memory.trust import record
from stayfixed.scaffold import MANIFEST_PATH, Kind, Location, Manifest, Record, digest
from stayfixed.scaffold.regions import RegionError, Style, extract, markers, upsert
from tests.attach.test_binding import DEFAULT_MEMORY
from tests.attach.test_links import _attach, _bound, _config
from tests.attach.test_write import SETTINGS
from tests.gitfixture import git
from tests.parserlimits import LONG_NUMBER, NESTED, PAST_ENCODING, overflowing_indent
from tests.runners import git_that_cannot_run
from tests.snapshot import assert_snapshot_changed, assert_snapshot_unchanged, snapshot

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
    _attach(root, store, machine, home, confirmed=True)
    assert_snapshot_changed(root, before)
    _detach(root, machine, home)
    assert_snapshot_unchanged(root, before)


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
    _attach(root, store, machine, home, confirmed=True)
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
    _attach(root, store, machine, home, confirmed=True)
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
    _attach(root, store, machine, home, confirmed=True)
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
    _attach(root, store, machine, home, confirmed=True)
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
    _attach(root, store, machine, home, confirmed=True)
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
    _attach(root, store, machine, home, confirmed=True)
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
    _attach(root, store, machine, home, confirmed=True)
    return _detach(root, machine, home)


def test_detach_keeps_a_directory_that_still_holds_something(tmp_path: Path) -> None:
    # The floor under the ledger: the removal is `rmdir`, so a directory holding anything the
    # attach did not put there survives — and its parent survives with it, because a parent that
    # still holds a child is not empty either. A `shutil.rmtree` here would delete the owner's
    # own `.codex/rules/` file on a detach that promised to remove only what it added.
    root, store, machine = _bound(tmp_path)
    _grant(store.parents[2], allow=(RULE,), hooks=True)
    home = tmp_path / "home"
    _attach(root, store, machine, home, confirmed=True)
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
    _attach(root, store, machine, home, confirmed=True)
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


def test_a_home_whose_claude_became_a_symlink_refuses_above_every_withdrawal(
    tmp_path: Path,
) -> None:
    # The mirror of the `attach` case, and the half that had no answer at all: the walk's
    # `UnsafePath` left `detach` uncaught, `cli.run` rendered it as `internal error` and exit
    # 2, and every later `detach` failed at the same line — with `.codex/rules/` already
    # deleted and the ledger, the ignore region and every link still on disk. A repository no
    # shipped command could return to its pre-attach state.
    #
    # The layout is reached the way a person reaches it: attach first, then let the dotfiles
    # manager adopt `~/.claude`. That is also why this is `detach`'s case and not a repeat of
    # `attach`'s — the home directory was fine when the repository was attached.
    #
    # Mutation (declared, "detach discovers the harness anchor from inside the withdrawal"):
    # the hoisted loop goes -> the refusal still arrives, from `detach_main`, and
    # `assert_snapshot_unchanged` reddens with the rule files already removed.
    root, store, machine = _bound(tmp_path)
    _grant(store.parents[2], allow=(RULE,), hooks=True)
    home = tmp_path / "home"
    _attach(root, store, machine, home, confirmed=True)
    resolved = resolve(root, _config(root, machine), machine=machine)
    assert resolved is not None
    record(resolved, _config(root, machine))
    _attach(root, store, machine, home, confirmed=True)
    harness = harness_memory_path(root, home)
    assert harness.is_symlink(), "there is no harness link for this case to be about"
    adopted = tmp_path / "dotfiles" / "claude"
    adopted.parent.mkdir(parents=True)
    shutil.move(str(home / ".claude"), str(adopted))
    (home / ".claude").symlink_to(adopted, target_is_directory=True)
    before = snapshot(root)
    assert before
    with pytest.raises(Refusal) as refused:
        _detach(root, machine, home)
    # The symlink is named by its place under the home directory, `contained`'s root.
    assert "passes through a symlink at '.claude'" in str(refused.value)
    # Nothing was withdrawn, so the repository is still the one the attach left and a second
    # `detach` — against a home whose `.claude` is a real directory — still has everything to
    # withdraw.
    assert_snapshot_unchanged(root, before)
    assert (root / LEDGER).is_file()
    assert (root / ".codex" / "rules").is_dir()
    assert harness.is_symlink()


def test_a_gitignore_region_that_cannot_be_withdrawn_is_answered_before_anything_is(
    tmp_path: Path,
) -> None:
    # The same shape as the `git` case above, one precondition over. `drop()` refuses a region
    # opened twice — what a merge that kept both sides leaves — and it was asked *after* the
    # settings withdrawal, the rule files and every link tree: rules gone, links gone, ledger
    # still there, `doctor` still reporting the repository attached, and a second `detach`
    # failing at the same line. The region is now read beside the ledger and `_checkouts`, so a
    # broken one refuses above the first withdrawal.
    #
    # Mutation (`mutations/`, "detach reads the ignore region after it has already
    # withdrawn"): the remainder computed where the write happens → the snapshot below changes.
    root, store, machine = _bound(tmp_path)
    _grant(store.parents[2], allow=(RULE,), hooks=True)
    home = tmp_path / "home"
    _attach(root, store, machine, home, confirmed=True)
    begin, _end = markers(IGNORE_REGION, Style.HASH)
    ignore = root / GITIGNORE
    ignore.write_text(f"{begin}\n" + ignore.read_text(encoding="utf-8"), encoding="utf-8")
    before = snapshot(root)
    with pytest.raises(RegionError) as refused:
        _detach(root, machine, home)
    # The refusal names the file, as the exclude block's does. Mutation: `mutations/`'s "a
    # doubled .gitignore region is refused without its file".
    assert GITIGNORE in str(refused.value)
    assert_snapshot_unchanged(root, before)
    assert (root / LEDGER).is_file()
    assert (root / "docs" / "memory" / "developer").is_symlink()


def test_a_whitespace_only_gitignore_survives_the_round_trip(tmp_path: Path) -> None:
    # `docs/cli.md` promises the round trip is byte-for-byte, and the withdrawal removed the
    # file whenever what remained was blank — so a `.gitignore` holding one newline before the
    # attach was gone after the detach. Only a file the attach created is taken away.
    root, store, machine = _bound(tmp_path)
    home = tmp_path / "home"
    (root / GITIGNORE).write_text("\n", encoding="utf-8")
    before = snapshot(root)
    _attach(root, store, machine, home)
    _detach(root, machine, home)
    assert_snapshot_unchanged(root, before)
    assert (root / GITIGNORE).read_bytes() == b"\n"


def test_a_region_init_recorded_survives_a_detach(tmp_path: Path) -> None:
    """A region `init`'s footprint records is `init`'s: ownership decides, not last writer.

    `stayfixed init` records the `stayfixed:ignore` region as a footprint artifact with exactly
    the body `attach` writes — one spelling, imported rather than respelled, so neither command
    can report the other's region as hand-edited. `attach`'s own write stays and is idempotent;
    what changes is the withdrawal. A `detach` that dropped a region the manifest records would
    take a line out of a *committed* file that `init` put there, and `upgrade` would then read
    the footprint as hand-edited on a repository nobody edited.

    The manifest is the authority because it is the only record of who wrote the region that
    survives the region being written twice. There is no new ledger field: the attach ledger is
    per-checkout and untracked, and the question "whose region is this" is answered for every
    clone by the committed manifest.

    Mutation: `mutations/`'s "detach withdraws a region the footprint owns".
    """
    root, store, machine = _bound(tmp_path)
    _grant(store.parents[2])
    (root / GITIGNORE).write_text(
        "node_modules/\n" + upsert("", IGNORE_REGION, IGNORE_BODY, Style.HASH), encoding="utf-8"
    )
    Manifest(
        {
            "gitignore": Record(
                "gitignore",
                Kind.MANAGED_REGION,
                Location.REPO,
                GITIGNORE,
                "gitignore",
                "0.1.0",
                digest(IGNORE_BODY),
            )
        }
    ).write(root)
    _attach(root, store, machine, tmp_path / "home", confirmed=True)
    removed = _detach(root, machine, tmp_path / "home")
    text = (root / GITIGNORE).read_text(encoding="utf-8")
    assert removed.ignore_region_removed is False
    assert text.startswith("node_modules/\n")
    assert extract(text, IGNORE_REGION, Style.HASH) == IGNORE_BODY


def _newer_format(manifest: Path, outside: Path) -> None:
    manifest.write_text(json.dumps({"format": 99}), encoding="utf-8")


def _not_utf8(manifest: Path, outside: Path) -> None:
    manifest.write_bytes(b'{"a": "\xff"}')


def _nested_past_the_stack(manifest: Path, outside: Path) -> None:
    manifest.write_text(NESTED, encoding="utf-8")


def _symlinked_out_of_the_root(manifest: Path, outside: Path) -> None:
    outside.write_text("{}", encoding="utf-8")
    manifest.symlink_to(outside)


@pytest.mark.parametrize(
    "commit",
    [_newer_format, _not_utf8, _nested_past_the_stack, _symlinked_out_of_the_root],
    ids=lambda commit: commit.__name__.lstrip("_"),
)
def test_a_manifest_a_clone_committed_cannot_block_the_withdrawal(
    tmp_path: Path, commit: Callable[[Path, Path], None]
) -> None:
    """A repository may not disable the command that undoes an attach.

    `.stayfixed/manifest.json` is **tracked** -- the ignore region covers `.stayfixed/local/` and
    `.stayfixed/assessment.json` and nothing else -- so a clone commits whatever it likes there,
    and `Manifest.read` refuses one that is unreadable, is not an object, or declares a `format`
    past this stayfixed's. `attach` never reads the file, so a clone shipping `{"format": 99}`
    attached cleanly, merged the owner's allow rules and hook entries, and then made `detach`
    exit 2 on every run for ever: the ownership question is asked above every withdrawal, so
    nothing was half-undone and nothing could ever be undone either.

    Refusing with a better sentence is not the answer, because the act it would name is
    "delete a tracked file out of somebody else's repository". An unreadable manifest is read
    as no claim this command will act on and no claim it will act against: the region stays,
    which is the conservative half, and the detach finishes. Everything else comes back, which
    is what the settings file and the ledger assert here.

    The first fix caught `ManifestError` alone, and a clone has three other ways to make the
    read fail: bytes that are not UTF-8 (`UnicodeDecodeError`, a `ValueError` the reader did not
    name), nesting deep enough to exhaust the parser's stack (`RecursionError`), and a manifest
    committed as a symlink out of the root (`PathEscape`, raised before any byte is read). Each
    one made the detach exit 2 exactly as `{"format": 99}` had.

    Mutations: `mutations/`'s "an unreadable manifest blocks the detach again" and "the
    manifest reader lets undecodable bytes out as a crash again".
    """
    root, store, machine = _bound(tmp_path)
    _grant(store.parents[2], allow=(RULE,), hooks=True)
    home = tmp_path / "home"
    _attach(root, store, machine, home, confirmed=True)
    assert (root / LEDGER).is_file()
    # Written after the attach, exactly as a clone's committed one is there before a later
    # `detach` and never read by the run that wrote the ledger.
    manifest = root / MANIFEST_PATH
    manifest.parent.mkdir(parents=True, exist_ok=True)
    commit(manifest, tmp_path / "outside.json")
    removed = _detach(root, machine, home)
    assert not (root / LEDGER).exists()
    assert removed.allow_removed == (RULE,)
    # The conservative half: ownership could not be established, so the block is left alone and
    # the result says so rather than claiming a withdrawal it did not make.
    assert removed.ignore_region_removed is False
    assert extract((root / GITIGNORE).read_text(encoding="utf-8"), IGNORE_REGION, Style.HASH)


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
    _attach(root, store, machine, home, confirmed=True)
    resolved = resolve(root, _config(root, machine), machine=machine)
    assert resolved is not None
    record(resolved, _config(root, machine))
    _attach(root, store, machine, home, confirmed=True)
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
    # The settings file is a candidate for the exclude block only on a run that writes it, and
    # the fallback key is written after the links. Whether it will be is decided before the
    # first write (`write._fallback_possible`), so the run hides the file in its one block.
    #
    # Mutation: `mutations/`'s "attach decides the settings fallback only once it has
    # written" reddens this through `check-ignore`.
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
    # `.gitignore` shows, as it should: the fixture tracks it and the attach added its region.
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


def test_a_fallback_that_would_write_through_a_symlinked_claude_is_skipped_with_a_note(
    tmp_path: Path,
) -> None:
    # The fallback writes the settings file, and a `.claude` linked in from elsewhere is a layout
    # the owner chose, not something to write through or refuse. So the fallback is not taken:
    # the run goes through, writes nothing behind the link, and says what the harness link is
    # missing and how to get it. Before, the write failed with an `OSError` after every earlier
    # write; then, a refusal took the whole attach away from an ordinary layout.
    #
    # Mutation: `mutations/`'s "attach takes the fallback through a linked-in .claude".
    from stayfixed.attach.write import FALLBACK_UNAVAILABLE

    root, store, machine, home = _fallback_forced(tmp_path)
    (tmp_path / "dotfiles-claude").mkdir()
    (root / ".claude").symlink_to(tmp_path / "dotfiles-claude", target_is_directory=True)
    attached = _attach(root, store, machine, home)
    assert attached.notes == (FALLBACK_UNAVAILABLE,)
    assert not attached.settings_written
    assert list((tmp_path / "dotfiles-claude").iterdir()) == []
    # Nothing to hide, so the block names no settings file.
    exclude = (root / ".git" / "info" / "exclude").read_text(encoding="utf-8")
    assert SETTINGS not in exclude


def test_a_symlinked_exclude_file_is_refused_first_when_only_the_fallback_needs_a_line(
    tmp_path: Path,
) -> None:
    # Every other path this run places is ignored already, so the only exclude line the run
    # needs is the fallback's settings file. That need is known before the first write, and so
    # is the refusal of a symlinked exclude file.
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


def test_a_first_attach_with_a_symlinked_exclude_that_hides_everything_attaches(
    tmp_path: Path,
) -> None:
    # A real directory at the harness path, the harness's own, does not make a first attach need
    # the fallback: no approval is recorded for a store that does not exist yet, so the gate
    # cannot open and no settings file is written. A symlinked exclude file that already hides
    # every path the run places is therefore never written, and never refused.
    #
    # Mutation: `mutations/`'s "a first attach treats the unapproved gate as possibly open":
    # the settings file becomes a candidate, the exclude file must take a line, and its symlink
    # is refused. (The linked-`.claude` case in `test_write.py` cannot see this guard: the
    # fallback is off the table there for the link alone.)
    root, store, machine = _bound(tmp_path)
    _grant(store.parents[2])
    home = tmp_path / "home"
    harness_memory_path(root, home).mkdir(parents=True)
    exclude = root / ".git" / "info" / "exclude"
    elsewhere = tmp_path / "exclude-elsewhere"
    held = exclude.read_text(encoding="utf-8") if exclude.is_file() else ""
    # Everything the run places, and not the settings file: the run does not write it, so it is
    # not a candidate, and nothing is left for the exclude file to take. The link tree is listed
    # here too, beside the fixture's committed `.gitignore` line for it: the owner's own line
    # hides it whatever that line says, so a path both hide needs no line of the block. (Asked
    # which pattern decides, git names the `.gitignore`, which outranks the owner's file; read
    # that way, the link tree needed a line and the symlinked file was refused.)
    elsewhere.write_text(
        held + f"/{DEFAULT_MEMORY}/\n/.codex/rules/\n.stayfixed/\n", encoding="utf-8"
    )
    exclude.unlink(missing_ok=True)
    exclude.symlink_to(elsewhere)
    outside = elsewhere.read_bytes()
    attached = _attach(root, store, machine, home)
    # Non-vacuous: the attach did run to the end and placed its tree.
    assert attached.links.created
    assert elsewhere.read_bytes() == outside
    assert not (root / SETTINGS).exists()


def test_a_tracked_settings_file_the_owners_symlinked_exclude_hides_does_not_refuse(
    tmp_path: Path,
) -> None:
    # The owner's symlinked exclude file hides the whole footprint, and the repository tracks its
    # own `.claude/settings.local.json`. git shows a tracked file whatever an exclude line says, so
    # asking "does git show it?" gave it a line that hides nothing, and that line needed the
    # symlinked file written, which is refused: an attach nothing had to write into the exclude
    # file exited 2. Only what the owner's own two files leave visible gets a line.
    #
    # Mutation: `mutations/`'s "the exclude block also lists what git shows in spite of the
    # owner's excludes".
    root, store, machine = _bound(tmp_path)
    _grant(store.parents[2], allow=(RULE,))
    home = tmp_path / "home"
    (root / ".claude").mkdir()
    (root / SETTINGS).write_text("{}\n", encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "the repository tracks its settings file")
    exclude = root / ".git" / "info" / "exclude"
    elsewhere = tmp_path / "exclude-elsewhere"
    held = exclude.read_text(encoding="utf-8") if exclude.is_file() else ""
    elsewhere.write_text(
        held + f"/{DEFAULT_MEMORY}/\n/.codex/rules/\n/{SETTINGS}\n.stayfixed/\n", encoding="utf-8"
    )
    exclude.unlink(missing_ok=True)
    exclude.symlink_to(elsewhere)
    outside = elsewhere.read_bytes()
    attached = _attach(root, store, machine, home, confirmed=True)
    # Non-vacuous: the run wrote the tracked settings file, so it was a candidate for the block.
    assert attached.settings_written
    assert RULE in (root / SETTINGS).read_text(encoding="utf-8")
    assert elsewhere.read_bytes() == outside


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
    _attach(root, store, machine, home, confirmed=True)
    _attach(side, store, machine, home, confirmed=True)
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
    _attach(root, store, machine, home, confirmed=True)
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
    _attach(root, store, machine, home, confirmed=True)
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
    _attach(root, store, machine, home, confirmed=True)
    # Non-vacuous: the attach wrote its block after a line it had to end.
    assert (
        _exclude_file(root)
        .read_bytes()
        .startswith(f"# the owner's{ending}/owner-only{ending}".encode())
    )
    # A second attach that rewrites the block carries the record along.
    _grant(store.parents[2], allow=(RULE, "Bash(ls:*)"))
    _attach(root, store, machine, home, confirmed=True)
    _detach(root, machine, home)
    assert _exclude_file(root).read_bytes() == held


def test_a_line_the_owner_added_after_the_block_keeps_its_line_ending(tmp_path: Path) -> None:
    # The line ending `attach` added sits before the block; with the owner's own line after it,
    # taking it back would join two lines, so it stays.
    root, store, machine = _bound(tmp_path)
    _grant(store.parents[2], allow=(RULE,))
    home = tmp_path / "home"
    _exclude_file(root).write_bytes(b"/owner-only")
    _attach(root, store, machine, home, confirmed=True)
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
    _attach(root, store, machine, home, confirmed=True)
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
    _attach(root, store, machine, home, confirmed=True)
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
    _attach(root, store, machine, home, confirmed=True)
    # A second attach finds the directory there, and must not forget whose it is.
    _attach(root, store, machine, home, confirmed=True)
    assert (root / DEFAULT_MEMORY / "MEMORY.md").is_symlink()
    _detach(root, machine, home)
    assert (root / DEFAULT_MEMORY).is_dir()
    assert list((root / DEFAULT_MEMORY).iterdir()) == []


# --- every refusal is made before the first withdrawal ----------------------------------------


def _withdrawable(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    root, store, machine = _bound(tmp_path)
    _grant(store.parents[2], allow=(RULE,), hooks=True)
    home = tmp_path / "home"
    _attach(root, store, machine, home, confirmed=True)
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
    _attach(root, store, machine, home, confirmed=True)
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
    _attach(root, store, machine, home, confirmed=True)
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
    _attach(root, store, machine, home, confirmed=True)
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
    _attach(root, store, machine, home, confirmed=True)
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


def test_a_linked_claude_directory_attach_never_wrote_into_does_not_stop_detach(
    tmp_path: Path,
) -> None:
    # A `.claude` kept elsewhere and linked in is an ordinary layout, and an overlay that grants
    # nothing gives `attach` nothing to write there. `detach` rewrote the settings file whether or
    # not it held anything of stayfixed's, so the same layout that attached cleanly could not be
    # detached. A file with nothing to withdraw is not written at all.
    #
    # Mutation: `mutations/`'s "detach rewrites a settings file it withdraws nothing from".
    root, store, machine = _bound(tmp_path)
    _grant(store.parents[2])
    home = tmp_path / "home"
    dotfiles = tmp_path / "dotfiles-claude"
    dotfiles.mkdir()
    (dotfiles / "settings.local.json").write_text('{"theme": "dark"}', encoding="utf-8")
    (root / ".claude").symlink_to(dotfiles, target_is_directory=True)
    _attach(root, store, machine, home, confirmed=True)
    _detach(root, machine, home)
    assert (dotfiles / "settings.local.json").read_text(encoding="utf-8") == '{"theme": "dark"}'
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
    # as it does on Python 3.12 near 994 levels. Mutation (declared): `detach` encodes the
    # withdrawn document with a bare `json.dumps` again -> `RecursionError`.
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
