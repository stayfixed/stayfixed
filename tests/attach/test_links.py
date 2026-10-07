"""`attach` links the store into the owning checkout and into every worktree that already exists.

The main checkout is `worktree.attach_main`'s (the case `link` excludes); every other checkout
is `worktree.link`'s, unchanged. This module asserts that `attach` reaches both.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from stayfixed import fsops
from stayfixed.attach.write import Attached, attach
from stayfixed.config.layout import ATTACH_LEDGER as LEDGER
from stayfixed.config.loader import load
from stayfixed.config.schema import Config
from stayfixed.errors import Refusal
from stayfixed.memory.api import PartialLink, harness_memory_path
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
    # A home directory that is already there. stayfixed finds the machine owner's home and
    # never creates it — `worktree.harness_link_parts` makes it the containment anchor, and
    # the `O_NOFOLLOW` walk vouches for every component below an anchor and never for the
    # anchor itself — so a home that is not there is a refusal, which
    # `tests/memory/test_worktree.py` asserts in both directions. Every test below spells its
    # home as `tmp_path / "home"`; it is created here so none of them has to say so.
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


def _attach(
    root: Path, store: Path, machine: Path, home: Path, *, confirmed: bool = False
) -> Attached:
    return attach(
        root,
        store=store,
        machine=machine,
        confirmed=confirmed,
        trust_remote=False,
        runner=Recorder(),
        home=home,
    )


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
    # `mutations/`, "attach's PartialLink forgets the links made before the failing call".
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


def test_the_harness_fallback_is_recorded_so_it_can_be_withdrawn(tmp_path: Path) -> None:
    # `~/.claude/projects/<slug>/memory` has a fallback — `autoMemoryDirectory` in
    # settings.local.json. The symlink is preferred, because a settings-file value is subject to
    # workspace trust and a link is not, and the fallback is taken only when the link cannot be
    # made; when it is, it goes into the same ledger as everything else, because a fallback nothing
    # records is a setting that outlives its reason.
    import json

    from stayfixed.attach.api import ledger
    from stayfixed.memory.api import resolve
    from stayfixed.memory.trust import record

    root, store, machine = _bound(tmp_path)
    home = tmp_path / "home"
    _attach(root, store, machine, home)
    resolved = resolve(root, _config(root, machine), machine=machine)
    assert resolved is not None
    record(resolved, _config(root, machine))
    # A real directory where the link belongs: the case `_link` refuses to clobber, and the one
    # that takes the fallback alongside a filesystem that has no symlinks.
    harness = harness_memory_path(root, home)
    harness.mkdir(parents=True)
    attached = _attach(root, store, machine, home)
    settings = json.loads((root / ".claude" / "settings.local.json").read_text(encoding="utf-8"))
    assert settings["autoMemoryDirectory"] == str(resolved.path.resolve())
    assert ledger(root).settings_keys == ("autoMemoryDirectory",)
    assert any("autoMemoryDirectory" in note for note in attached.notes)


def _settings(root: Path) -> dict[str, object]:
    import json

    path = root / ".claude" / "settings.local.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def _trusted(root: Path, machine: Path) -> None:
    from stayfixed.memory.api import resolve
    from stayfixed.memory.trust import record

    config = _config(root, machine)
    store = resolve(root, config, machine=machine)
    assert store is not None
    record(store, config)


def test_a_second_attach_neither_forgets_the_fallback_nor_lets_it_outlive_its_reason(
    tmp_path: Path,
) -> None:
    # `memory/worktree.py`'s own rule, one function over: "a gate evaluated once, at creation,
    # over state that persists is not a gate". A settings value is exactly such state, and this
    # is the channel that module calls the one hop that leaves its gate — read by the harness's
    # native reader, outside every delimiter and trust record stayfixed controls.
    #
    # The sequence measured: attach with a real directory where the link belongs, so the
    # fallback is taken and recorded; then a `git pull` adds a note, which lapses the trust
    # record. `_apply_harness_link` correctly revokes the *symlink* channel — and the key used
    # to survive, with `_write_ledger` handed `()` on every run so the ledger forgot it too. The
    # harness went on reading the new bytes through a setting nothing recorded and `detach`
    # could no longer remove.
    #
    # Mutation: `mutations/`'s "the settings fallback outlives the gate that allowed it" —
    # make `_harness_fallback` return early when the link is no longer needed.
    from stayfixed.attach.api import ledger

    root, store, machine = _bound(tmp_path)
    home = tmp_path / "home"
    _attach(root, store, machine, home)
    _trusted(root, machine)
    harness_memory_path(root, home).mkdir(parents=True)
    _attach(root, store, machine, home)
    # Non-vacuous: the rest of this is only about a lapse if the fallback was taken at all.
    assert "autoMemoryDirectory" in _settings(root)
    assert ledger(root).settings_keys == ("autoMemoryDirectory",)

    (tmp_path / "overlay" / "common" / "memory" / "pulled.md").write_text("# n\n", "utf-8")
    _attach(root, store, machine, home)
    assert "autoMemoryDirectory" not in _settings(root)
    assert ledger(root).settings_keys == ()


def test_the_fallback_goes_when_the_symlink_it_stood_in_for_can_be_made(tmp_path: Path) -> None:
    # The other arm of the same gate, and the one that needs no trust record to lapse. The
    # fallback exists only "when the link cannot be made"; once the real directory in the way is
    # gone the link is made and the setting has no reason left. It used to be left in the file
    # while the ledger was reset to `[]` around it, so `detach` left it behind for good — two
    # readers pointed at the store, one of them recorded nowhere.
    from stayfixed.attach.api import ledger

    root, store, machine = _bound(tmp_path)
    home = tmp_path / "home"
    _attach(root, store, machine, home)
    _trusted(root, machine)
    harness = harness_memory_path(root, home)
    harness.mkdir(parents=True)
    _attach(root, store, machine, home)
    assert "autoMemoryDirectory" in _settings(root)

    harness.rmdir()
    _attach(root, store, machine, home)
    assert harness.is_symlink()
    assert "autoMemoryDirectory" not in _settings(root)
    assert ledger(root).settings_keys == ()


def test_a_second_attach_that_changes_nothing_still_records_the_standing_fallback(
    tmp_path: Path,
) -> None:
    # The vacuity guard for the two cases above: a `_harness_fallback` that simply never
    # recorded the key would pass both. While the real directory is still in the way, every
    # later attach must go on recording the key that is still in the file — which is the defect
    # in its original direction, since the ledger is what `detach` reads.
    from stayfixed.attach.api import ledger

    root, store, machine = _bound(tmp_path)
    home = tmp_path / "home"
    _attach(root, store, machine, home)
    _trusted(root, machine)
    harness_memory_path(root, home).mkdir(parents=True)
    _attach(root, store, machine, home)
    _attach(root, store, machine, home)
    assert "autoMemoryDirectory" in _settings(root)
    assert ledger(root).settings_keys == ("autoMemoryDirectory",)


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


def test_attaching_from_a_linked_worktree_takes_no_fallback_for_the_link_it_made(
    tmp_path: Path,
) -> None:
    # The worktree's harness link points at the store the owning checkout holds, which is what
    # `link` hands every worktree; the fallback compared it with the worktree's own resolved
    # store instead, a different directory, so a run that made the link still said "the harness
    # memory link could not be created" and recorded `autoMemoryDirectory`. Asked of the store
    # the link was made to, it takes none. Where a real directory does stand in the way, the
    # fallback names that same store. Mutation: `mutations/`, "the settings fallback compares a
    # worktree's link with that worktree's own store".
    from stayfixed.attach.api import ledger
    from stayfixed.memory.api import resolve

    root, store, machine = _bound(tmp_path)
    side = tmp_path / "side"
    _git(root, "worktree", "add", "-q", str(side), "-b", "side")
    home = tmp_path / "home"
    _attach(side, store, machine, home)
    _trusted(root, machine)
    _trusted(side, machine)
    attached = _attach(side, store, machine, home)
    assert harness_memory_path(side, home).is_symlink()
    assert "autoMemoryDirectory" not in _settings(side)
    assert ledger(side).settings_keys == ()
    assert not [note for note in attached.notes if "could not be created" in note]

    owner = resolve(root, _config(root, machine), machine=machine)
    assert owner is not None
    harness_memory_path(side, home).unlink()
    harness_memory_path(side, home).mkdir()
    _attach(side, store, machine, home)
    assert _settings(side)["autoMemoryDirectory"] == str(owner.path.resolve())


def test_a_worktree_whose_claude_is_linked_in_says_the_fallback_is_unavailable_only_when_wanted(
    tmp_path: Path,
) -> None:
    # The other branch of the same question: a worktree whose `.claude` is linked in from
    # elsewhere takes no fallback and says so when one is wanted. Asked of the worktree's own store,
    # it said so beside the link it had just made. Mutation: `mutations/`, "the unavailable
    # fallback is asked of a worktree's own store".
    from stayfixed.attach.write import FALLBACK_UNAVAILABLE

    root, store, machine = _bound(tmp_path)
    side = tmp_path / "side"
    _git(root, "worktree", "add", "-q", str(side), "-b", "side")
    home = tmp_path / "home"
    _attach(side, store, machine, home)
    _trusted(root, machine)
    _trusted(side, machine)
    (tmp_path / "dotfiles-claude").mkdir()
    (side / ".claude").symlink_to(tmp_path / "dotfiles-claude", target_is_directory=True)
    attached = _attach(side, store, machine, home)
    assert harness_memory_path(side, home).is_symlink()
    assert FALLBACK_UNAVAILABLE not in attached.notes
    harness_memory_path(side, home).unlink()
    harness_memory_path(side, home).mkdir()
    assert FALLBACK_UNAVAILABLE in _attach(side, store, machine, home).notes
    assert list((tmp_path / "dotfiles-claude").iterdir()) == []


def test_attaching_from_a_linked_worktree_says_the_link_waits_only_when_it_does(
    tmp_path: Path,
) -> None:
    # The same store, asked the same way: with the owning checkout's store approved and the
    # worktree's own not, the link is made to the approved one, and the line said it waited for
    # an approval because it asked the worktree's. Mutation: `mutations/`, "attach says the
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
    # Non-vacuous: there is nothing to withdraw unless both trees were built.
    assert (root / "docs" / "memory" / "developer").is_symlink()
    assert (side / "docs" / "memory" / "developer").is_symlink()
    detach(side, machine=machine, home=home)
    assert not (root / "docs" / "memory" / "developer").is_symlink()
    assert not (side / "docs" / "memory" / "developer").is_symlink()


def test_withdrawing_the_fallback_takes_the_settings_file_with_it_when_nothing_is_left(
    tmp_path: Path,
) -> None:
    # The one case in which `attach` removes a file, pinned rather than left to be discovered.
    # `{}` is not what `.claude/settings.local.json` looked like before the fallback was taken —
    # it is a file `attach` itself created — so the last thing withdrawn takes it away, which is
    # the rule `detach`'s own `_withdraw_settings` already applies and what keeps the round trip
    # byte-for-byte.
    root, store, machine = _bound(tmp_path)
    home = tmp_path / "home"
    _attach(root, store, machine, home)
    _trusted(root, machine)
    harness = harness_memory_path(root, home)
    harness.mkdir(parents=True)
    _attach(root, store, machine, home)
    # Non-vacuous: the file exists, and the key is the only thing in it.
    assert list(_settings(root)) == ["autoMemoryDirectory"]

    harness.rmdir()
    _attach(root, store, machine, home)
    assert not (root / ".claude" / "settings.local.json").exists()


def test_withdrawing_the_fallback_never_takes_anything_else_out_of_that_file(
    tmp_path: Path,
) -> None:
    # The guard on the case above, and the one that matters: the removal may only ever fire when
    # stayfixed's own key was the file's entire contents. An owner's own setting beside it keeps
    # the file, and keeps itself.
    root, store, machine = _bound(tmp_path)
    home = tmp_path / "home"
    (root / ".claude").mkdir(exist_ok=True)
    (root / ".claude" / "settings.local.json").write_text(
        '{\n  "permissions": {\n    "deny": [\n      "Bash(curl:*)"\n    ]\n  }\n}\n', "utf-8"
    )
    _attach(root, store, machine, home)
    _trusted(root, machine)
    harness = harness_memory_path(root, home)
    harness.mkdir(parents=True)
    _attach(root, store, machine, home)
    assert "autoMemoryDirectory" in _settings(root)

    harness.rmdir()
    _attach(root, store, machine, home)
    document = _settings(root)
    assert "autoMemoryDirectory" not in document
    permissions = document["permissions"]
    assert isinstance(permissions, dict)
    assert permissions["deny"] == ["Bash(curl:*)"]


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
    # Mutation (`mutations/`, "attach links into a worktree git reports as prunable"): the
    # `prunable` skip removed → this raises.
    root, store, machine = _bound(tmp_path)
    side = tmp_path / "side"
    _git(root, "worktree", "add", "-q", str(side), "-b", "side")
    shutil.rmtree(side)
    attached = _attach(root, store, machine, tmp_path / "home")
    assert (root / "docs" / "memory" / "developer").is_symlink()
    assert not any(str(side) in str(path) for path in attached.links.created)


def test_a_home_whose_claude_is_a_symlink_refuses_above_every_write(tmp_path: Path) -> None:
    # The layout is stow's, chezmoi's, or any synced home: `~/.claude` is a link into a
    # dotfiles tree. The walk under the home directory refuses to follow it — deliberately,
    # and `worktree.harness_link_parts` cites `setup --settings` as the precedent — but the
    # refusal used to be discovered from inside the link step, which runs after the ignore
    # region, the Codex rule files, the settings merge, the ledger and the overlay's binding
    # record. Measured then: `PartialLink` with three links already made, `detach` afterwards
    # raising a raw `UnsafePath` as `internal error`, and no shipped command able to put the
    # repository back.
    #
    # `attach`'s own docstring is the standard this holds it to: "All six refusals are above
    # every write… A refusal that leaves a repository looking attached is not a refusal."
    #
    # Mutation (declared, "attach discovers the harness anchor from inside the link step"):
    # the hoisted call goes -> the refusal still arrives, from `_apply_harness_link`, and
    # `assert_snapshot_unchanged` reddens with the ledger and the region already written.
    root, store, machine = _bound(tmp_path)
    home = tmp_path / "home"
    elsewhere = tmp_path / "dotfiles" / "claude"
    elsewhere.mkdir(parents=True)
    (home / ".claude").symlink_to(elsewhere, target_is_directory=True)
    before = snapshot(root)
    # `snapshot` is a walk, and an empty one satisfies the comparison below on its own.
    assert before
    with pytest.raises(Refusal) as refused:
        _attach(root, store, machine, home, confirmed=True)
    # The symlink is named by its place under the home directory, `contained`'s root.
    assert "passes through a symlink at '.claude'" in str(refused.value)
    assert_snapshot_unchanged(root, before)
    assert not (root / LEDGER).exists()
    # Nothing reached the dotfiles tree either: the refusal is in front of the link, not a
    # write that followed it.
    assert list(elsewhere.iterdir()) == []
