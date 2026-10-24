"""`attach` links the store into the owning checkout and into every worktree that already exists.

The main checkout is `worktree.attach_main`'s (the case `link` excludes); every other checkout
is `worktree.link`'s, unchanged. This module asserts that `attach` reaches both.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import pytest

from stayfixed import fsops
from stayfixed.attach.write import Attached, _worktrees, attach
from stayfixed.config.layout import ATTACH_LEDGER as LEDGER
from stayfixed.config.loader import load
from stayfixed.config.schema import Config
from stayfixed.errors import Refusal
from stayfixed.memory.api import PartialLink, harness_memory_path, main_checkout
from tests.attach.test_binding import CONFIG, DEFAULT_MEMORY, _machine
from tests.gitfixture import git as _git
from tests.runners import Recorder
from tests.snapshot import assert_snapshot_unchanged, snapshot

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")


def _config(root: Path, machine: Path) -> Config:
    return load(root, machine=machine)


def _bound(tmp_path: Path) -> tuple[Path, Path, Path]:
    """A committed repository in overlay mode, and the overlay that already records it."""
    root = tmp_path / "project"
    root.mkdir(parents=True)
    # A home directory that is already there: stayfixed never creates one, and a home that is not
    # there is a refusal (`tests/memory/test_worktree.py`). Every test below spells its home as
    # `tmp_path / "home"`; it is created here so none of them has to say so.
    (tmp_path / "home").mkdir(exist_ok=True)
    overlay = tmp_path / "overlay"
    (overlay / "common" / "memory").mkdir(parents=True)
    (overlay / "common" / "memory" / "shared.md").write_text("x", encoding="utf-8")
    own = overlay / "projects" / "p" / "memory"
    own.mkdir(parents=True)
    (own.parent / "project.toml").write_text(
        'remote = "git@example.com:o/p.git"\n', encoding="utf-8"
    )
    (overlay / "common" / "claude").mkdir(parents=True)
    (overlay / "common" / "codex").mkdir(parents=True)
    (root / "stayfixed.toml").write_text(CONFIG.format(name="p"), encoding="utf-8")
    (root / ".gitignore").write_text(f"{DEFAULT_MEMORY}/\n", encoding="utf-8")
    _git(root, "init", "-q", "-b", "main")
    _git(root, "remote", "add", "origin", "git@example.com:o/p.git")
    _git(root, "add", "-A")
    _git(root, "-c", "user.email=a@b.c", "-c", "user.name=a", "commit", "-qm", "init")
    return root, own, _machine(tmp_path, overlay=overlay)


def _attach(root: Path, store: Path, machine: Path, home: Path) -> Attached:
    """`attach`, then the main checkout's settings file as an attach left it before the composed
    store: without `autoMemoryDirectory`. The harness reads the directory that key names whatever
    stands at the harness memory path, so with it in place no state of the link tree or the harness
    link that the cases built on this read is reachable; the pointer itself is held by
    `tests/attach/test_write.py` and `tests/attach/test_detach.py`."""
    attached = attach(
        root,
        store=store,
        machine=machine,
        runner=Recorder(),
        home=home,
    )
    settings = main_checkout(root) / ".claude" / "settings.local.json"
    if settings.is_file():
        document = json.loads(settings.read_text(encoding="utf-8"))
        document.pop("autoMemoryDirectory", None)
        if document:
            settings.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
        else:
            settings.unlink()
    return attached


def test_every_existing_worktree_is_linked(tmp_path: Path) -> None:
    # `attach` links memory into every existing worktree. A worktree created before the attach
    # is the common case — this repository has four of them. The main checkout is skipped here
    # because `attach_main` has already handled it, and `link` is a no-op there anyway.
    root, store, machine = _bound(tmp_path)
    side = tmp_path / "side"
    _git(root, "worktree", "add", "-q", str(side), "-b", "side")
    _attach(root, store, machine, tmp_path / "home")
    assert (root / "docs" / "memory" / "developer").is_symlink()
    assert (side / "docs" / "memory" / "developer").is_symlink()
    assert (side / "docs" / "memory" / "project-stable").is_symlink()


def test_a_partial_link_failure_carries_every_link_the_run_already_made(
    tmp_path: Path,
) -> None:
    # **The defect this test used to pin.** `PartialLink` carries `.created` precisely so a
    # half-built tree is repairable rather than mysterious. `_link_everywhere` accumulates
    # `created` in a *local* list across `attach_main` and one `link` per further checkout, and
    # used to let the exception out untouched — so what the caller received was the failing
    # call's own list and nothing before it. Here that list was empty while the owning
    # checkout's link tree was on disk, which is precisely the state `.created` exists to
    # describe, and the docstring claiming "`.created` intact" was false.
    #
    # The coupling is mechanical rather than a sentence: the assertion below reads the symlinks
    # the owning checkout actually holds and requires every one of them to be in `.created`.
    # Nothing has to be restated when the tree grows a group. Mutation: restoring the bare
    # `more = link(tree, store, config, home=home)` in `_link_everywhere` reddens it —
    # `mutations/`'s "attach's PartialLink forgets the links made before the failing call".
    root, store, machine = _bound(tmp_path)
    side = tmp_path / "side"
    _git(root, "worktree", "add", "-q", str(side), "-b", "side")
    # Patched at `fsops.symlink_within` and no longer at `Path.symlink_to`: the link tree
    # creates every link through the contained walk, so the `Path` method it used to call is
    # not on the path any more and patching it would simulate nothing. The root is what says
    # which checkout the link is going into — it is the containment anchor `worktree._link`
    # takes, and for a worktree's own links it is that worktree.
    real = fsops.symlink_within

    def refuse_inside_the_worktree(root_of_the_link: Path, target: str, source: Path) -> None:
        if str(root_of_the_link).startswith(str(side)):
            raise OSError("this filesystem refuses symlinks")
        real(root_of_the_link, target, source)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(fsops, "symlink_within", refuse_inside_the_worktree)
        with pytest.raises(PartialLink) as failed:
            _attach(root, store, machine, tmp_path / "home")
    # The owning checkout's tree exists — `attach_main` made it before the failing call — and
    # the walk over it is asserted non-empty before anything is asserted about the list, so a
    # run that made no links at all could not pass this as "nothing missing".
    made_by_attach_main = root / "docs" / "memory" / "developer"
    assert made_by_attach_main.is_symlink()
    on_disk = {path for path in (root / "docs" / "memory").resolve().iterdir() if path.is_symlink()}
    assert on_disk, "the owning checkout holds no links, so this would assert nothing"
    carried = {path.parent.resolve() / path.name for path in failed.value.created}
    assert on_disk <= carried, f"made on disk and absent from .created: {on_disk - carried}"


def _trusted(root: Path, machine: Path) -> None:
    from stayfixed.memory.api import resolve
    from tests.approved import record

    config = _config(root, machine)
    store = resolve(root, config, machine=machine)
    assert store is not None
    record(store, config)


def test_attaching_from_a_linked_worktree_links_the_main_checkout_too(tmp_path: Path) -> None:
    # `attach` links every checkout, and `--root` is allowed to name any of them. `attach_main`
    # used to be applied to whatever `--root` named and the loop then skipped
    # `main_checkout(root)` unconditionally — and `worktree.link` is documented as a no-op for
    # the main checkout, so nothing downstream caught it. Attaching from a worktree built that
    # worktree's tree and left the owning checkout with none: every session there saw no
    # memory, silently, and the command exited 0.
    #
    # Mutation: `mutations/`'s "attach applies the owning-checkout entry point to --root".
    root, store, machine = _bound(tmp_path)
    side = tmp_path / "side"
    _git(root, "worktree", "add", "-q", str(side), "-b", "side")
    _attach(side, store, machine, tmp_path / "home")
    assert (root / "docs" / "memory" / "developer").is_symlink()
    assert (root / "docs" / "memory" / "project-stable").is_symlink()
    assert (side / "docs" / "memory" / "developer").is_symlink()


def test_attaching_from_a_linked_worktree_says_the_link_waits_only_when_it_does(
    tmp_path: Path,
) -> None:
    # The same store, asked the same way: with the owning checkout's store approved and the
    # worktree's own not, the link is made to the approved one, and the line said it waited for
    # an approval because it asked the worktree's. Mutation: `mutations/`'s "attach says the
    # harness link waits by a worktree's own store".
    from stayfixed.attach.write import HARNESS_WAITS

    root, store, machine = _bound(tmp_path)
    side = tmp_path / "side"
    _git(root, "worktree", "add", "-q", str(side), "-b", "side")
    home = tmp_path / "home"
    _attach(side, store, machine, home)
    _trusted(root, machine)
    attached = _attach(side, store, machine, home)
    assert harness_memory_path(side, home).is_symlink()
    assert HARNESS_WAITS not in attached.notes


def test_detaching_from_a_linked_worktree_withdraws_the_main_checkouts_tree_too(
    tmp_path: Path,
) -> None:
    # The mirror shape, and it had the mirror defect: `detach_main` was applied to `--root` and
    # the loop skipped the owner, so a detach run from a worktree withdrew that worktree's tree
    # twice and left the owning checkout's — and its harness link — in place.
    from stayfixed.attach.write import detach

    root, store, machine = _bound(tmp_path)
    side = tmp_path / "side"
    _git(root, "worktree", "add", "-q", str(side), "-b", "side")
    home = tmp_path / "home"
    # Attached from the worktree as well, because the ledger `detach` reads lives under
    # `.stayfixed/local/` in the checkout the attach was run from, and that directory is
    # untracked — a sibling worktree does not have one.
    _attach(side, store, machine, home)
    # Approved and attached again, so each checkout holds a harness link as `attach` makes it:
    # both point at the owning checkout's `paths.memory`. The worktree's was compared with the
    # worktree's own tree, never matched, and outlived the detach dangling. Mutation (oracle):
    # `mutations/`'s "detach compares a checkout's harness link with that checkout's own tree"
    # -> the worktree's link stays.
    _trusted(root, machine)
    _attach(side, store, machine, home)
    # Non-vacuous: there is nothing to withdraw unless both trees and both links were built.
    assert (root / "docs" / "memory" / "developer").is_symlink()
    assert (side / "docs" / "memory" / "developer").is_symlink()
    for checkout in (root, side):
        assert harness_memory_path(checkout, home).exists(), checkout
    detach(side, machine=machine, runner=Recorder(), home=home)
    assert not (root / "docs" / "memory" / "developer").is_symlink()
    assert not (side / "docs" / "memory" / "developer").is_symlink()
    for checkout in (root, side):
        assert not os.path.lexists(harness_memory_path(checkout, home)), checkout
    projects = home / ".claude" / "projects"
    assert [path for path in projects.rglob("*") if path.is_symlink()] == []


def test_a_worktree_whose_directory_is_gone_is_skipped_rather_than_blamed_on_git(
    tmp_path: Path,
) -> None:
    # `rm -rf` on a worktree without `git worktree prune` is the ordinary way one goes away, and
    # `git worktree list --porcelain` keeps listing it with a `prunable` line. `_worktrees` kept
    # every `worktree ` line, `link()` ran with `cwd=<gone>`, and `GitUnavailable` said "check
    # that `git` runs here" — after the ledger, the region, the binding record and the owner's
    # links were written, on a machine whose `git` was fine. `detach` in the same state
    # completed, so the two halves disagreed about it.
    #
    # Two guards hold this, and neither alone reddens it: the `prunable` skip in `_worktrees`
    # and the gone-directory skip in `_link_everywhere`. Each is pinned by a test of its own, the
    # next one here and `test_write`'s race: `mutations/`'s "attach links into a worktree git
    # reports as prunable" and "a worktree removed mid-walk fails the whole attach".
    root, store, machine = _bound(tmp_path)
    side = tmp_path / "side"
    _git(root, "worktree", "add", "-q", str(side), "-b", "side")
    shutil.rmtree(side)
    attached = _attach(root, store, machine, tmp_path / "home")
    assert (root / "docs" / "memory" / "developer").is_symlink()
    assert not any(str(side) in str(path) for path in attached.links.created)


def test_a_worktree_git_reports_as_prunable_is_not_a_checkout_attach_or_detach_walks(
    tmp_path: Path,
) -> None:
    # `git worktree list` keeps a worktree deleted without `git worktree prune`, marked
    # `prunable`, and git's own word on it is that it is gone. `attach` would also skip it for its
    # gone directory when it asks there, so the test above passes without this guard; `_worktrees`
    # is what `detach` walks too, and it lists no checkout git calls prunable. Mutation (declared):
    # `mutations/`'s "attach links into a worktree git reports as prunable".
    root, _store, _machine = _bound(tmp_path)
    side = tmp_path / "side"
    _git(root, "worktree", "add", "-q", str(side), "-b", "side")
    listed = {path.resolve() for path in _worktrees(root)}
    # Non-vacuous: listed while it exists.
    assert side.resolve() in listed
    shutil.rmtree(side)
    assert all(path.name != "side" for path in _worktrees(root))


def test_a_side_worktree_whose_slug_is_a_link_refuses_attach_and_detach_before_any_write(
    tmp_path: Path,
) -> None:
    # The walk differs per checkout at `projects/<slug>`, so the anchor is asked for every
    # checkout, above the first write. Mutations (oracle): `mutations/`'s "attach asks the harness
    # anchor of --root alone" and "detach asks the harness anchor of --root alone".
    from stayfixed.attach.write import detach

    root, store, machine = _bound(tmp_path)
    side = tmp_path / "side"
    _git(root, "worktree", "add", "-q", str(side), "-b", "side")
    home = tmp_path / "home"
    slug = harness_memory_path(side, home).parent
    slug.parent.mkdir(parents=True)
    (tmp_path / "elsewhere").mkdir()
    before = snapshot(root)
    assert before
    for attached in (False, True):
        if attached:
            _attach(root, store, machine, home)
            before = snapshot(root)
        slug.symlink_to(tmp_path / "elsewhere", target_is_directory=True)
        with pytest.raises(Refusal, match="none below it"):
            if attached:
                detach(root, machine=machine, runner=Recorder(), home=home)
            else:
                _attach(root, store, machine, home)
        assert_snapshot_unchanged(root, before)
        slug.unlink()


def test_a_home_that_is_not_there_refuses_above_every_write(tmp_path: Path) -> None:
    # A mistyped `--home` used to be discovered from inside the link step, after the ignore
    # region, the Codex rule files, the settings merge, the ledger and the overlay's binding
    # record. Mutation (declared, `mutations/`'s "attach discovers the harness anchor from inside
    # the link step"): the hoisted call goes -> `assert_snapshot_unchanged` reddens with the
    # ledger and the region already written.
    root, store, machine = _bound(tmp_path)
    before = snapshot(root)
    # `snapshot` is a walk, and an empty one satisfies the comparison below on its own.
    assert before
    with pytest.raises(Refusal, match="never creates the home directory itself"):
        _attach(root, store, machine, tmp_path / "no-such-home")
    assert_snapshot_unchanged(root, before)
    assert not (root / LEDGER).exists()


def test_a_memory_mode_the_overlays_common_file_sets_reaches_attach(tmp_path: Path) -> None:
    # The overlay's layers are resolved for a session; `attach` read the repository and the
    # machine file alone, so an overlay that set `memory.mode = "overlay"` had the session ask for
    # a store `attach` never built, and the remedy the session named changed nothing for ever.
    root, store, machine = _bound(tmp_path)
    text = (root / "stayfixed.toml").read_text(encoding="utf-8")
    (root / "stayfixed.toml").write_text(text.replace('mode = "overlay"\n', ""), encoding="utf-8")
    _git(root, "commit", "-qam", "no mode of its own")
    (store.parents[2] / "common" / "stayfixed.toml").write_text(
        '[memory]\nmode = "overlay"\n', encoding="utf-8"
    )
    _attach(root, store, machine, tmp_path / "home")
    assert (root / DEFAULT_MEMORY / "developer").is_symlink()


def test_memory_groups_the_overlay_sets_are_placed_by_attach_and_doctor_stays_green(
    tmp_path: Path,
) -> None:
    # `doctor` reads the session's preferences, the overlay's `memory.groups` among them; `attach`
    # read the repository's, so a group the overlay added was never placed or hidden, and the
    # `attached` row turned red blaming a `.gitignore` line that did not exist.
    import json

    from stayfixed.doctor import checks as doctor_checks

    root, store, machine = _bound(tmp_path)
    (root / ".gitignore").write_text("", encoding="utf-8")
    _git(root, "commit", "-qam", "nothing ignored by the repository")
    groups = [*load(root, machine=machine).memory.groups, "extra"]
    (store.parents[2] / "common" / "stayfixed.toml").write_text(
        f"[memory]\ngroups = {json.dumps(groups)}\n", encoding="utf-8"
    )
    home = tmp_path / "home"
    _attach(root, store, machine, home)
    env = {"PATH": os.environ.get("PATH", ""), "HOME": os.environ["HOME"]}
    rows = doctor_checks.run_checks(root, home=home, machine=machine, runner=Recorder(), env=env)
    row = next(row for row in rows if row.name == "attached")
    assert row.status != "red", row.detail
    assert (root / DEFAULT_MEMORY / "extra").is_symlink()
