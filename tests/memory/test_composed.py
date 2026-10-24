"""The composed store: the one directory under this machine's data directory that the harness
reads its memory from, named by the binding id and holding links into the overlay."""

from __future__ import annotations

import shutil
from pathlib import Path

from stayfixed.config.paths import data_directory
from stayfixed.memory.composed import build, withdraw
from stayfixed.memory.store import composed_directory as store_directory

# A binding id as `secrets.token_hex(16)` draws one; the store is named by it and nothing else.
ID = "0123456789abcdef0123456789abcdef"


def an_overlay(tmp_path: Path) -> tuple[Path, Path]:
    """An overlay with the common notes, two groups of project `p` and its rendered index."""
    overlay = tmp_path / "overlay"
    (overlay / "common" / "memory").mkdir(parents=True)
    share = overlay / "projects" / "p" / "memory"
    (share / "project-stable").mkdir(parents=True)
    (share / "project-volatile").mkdir()
    (share / "MEMORY.md").write_text("# Memory\n", encoding="utf-8")
    return overlay, share


def test_the_store_links_each_group_and_the_index_into_the_overlay(tmp_path: Path) -> None:
    # `developer` is the overlay's `common/memory` itself, as the link tree routes it, and every
    # other group is this project's own directory in the overlay; the index is the one
    # `memory index` renders in the project's share.
    overlay, share = an_overlay(tmp_path)
    store = build(overlay, "p", ID)
    assert store == data_directory() / "stores" / ID == store_directory(ID)
    assert store.is_dir()
    entries = sorted(store.iterdir())
    assert all(entry.is_symlink() for entry in entries)
    assert {entry.name: entry.resolve() for entry in entries} == {
        "developer": (overlay / "common" / "memory").resolve(),
        "project-stable": (share / "project-stable").resolve(),
        "project-volatile": (share / "project-volatile").resolve(),
        "MEMORY.md": (share / "MEMORY.md").resolve(),
    }


def test_a_rebuild_follows_the_overlay_and_keeps_a_note_the_harness_wrote(tmp_path: Path) -> None:
    # The harness writes into the directory it is pointed at, so a file there that is not a link
    # is a note, and a rebuild never removes it; a link to a group the overlay no longer holds goes,
    # and a group it gained is linked.
    overlay, share = an_overlay(tmp_path)
    store = build(overlay, "p", ID)
    assert store.is_dir()
    (store / "topic.md").write_text("the harness's note", encoding="utf-8")
    shutil.rmtree(share / "project-volatile")
    (share / "specs").mkdir()
    build(overlay, "p", ID)
    assert sorted(entry.name for entry in store.iterdir()) == [
        "MEMORY.md",
        "developer",
        "project-stable",
        "specs",
        "topic.md",
    ]
    assert (store / "topic.md").read_text(encoding="utf-8") == "the harness's note"


def test_withdraw_removes_the_links_and_the_store_and_never_a_note(tmp_path: Path) -> None:
    # The links go and the overlay they point into stays; a note the harness wrote keeps the
    # directory, since nothing stayfixed placed it there.
    overlay, share = an_overlay(tmp_path)
    store = build(overlay, "p", ID)
    assert withdraw(ID) is True
    assert not store.exists() and (share / "project-stable").is_dir()
    build(overlay, "p", ID)
    (store / "topic.md").write_text("kept", encoding="utf-8")
    assert withdraw(ID) is False
    assert [entry.name for entry in store.iterdir()] == ["topic.md"]
    # No store at all is no store left.
    assert withdraw("f" * 32) is True
