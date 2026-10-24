"""A note counts as the owner's only once promoted, and only at the bytes that were promoted.

The record is a `reviewed` entry in `trust.json`, beside the machine file and outside every tree,
so a note a repository ships, one the harness's writer or an agent wrote, and one the owner edited
after promoting it all arrive the same way: unreviewed, as data, and never as a standing rule.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from stayfixed.config.loader import CONFIG_FILE, load
from stayfixed.memory.commands import NOT_A_NOTE, NOTHING_NAMED
from stayfixed.memory.hooks import UNREVIEWED_COUNT, register
from stayfixed.memory.notes import walk
from stayfixed.memory.reviewed import REVIEWED, UNREVIEWED, status
from stayfixed.memory.store import Store, resolve
from stayfixed.memory.trust import DELIMITER
from tests.cli import cli
from tests.sessions import session_of

CONFIG = """
[stayfixed]
version = "0.1.0"
state = "installed"

[project]
name = "widget"

[memory]
mode = "local-only"
groups = ["developer", "project-volatile"]
"""


def _note(name: str, *, startup: str = "", body: str = "Body.") -> str:
    meta = "metadata:\n  type: project\n" + (f"  startup: {startup}\n" if startup else "")
    return f'---\nname: {name}\ndescription: "{name} description"\n{meta}---\n\n{body}\n'


def _project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    base = root / ".stayfixed" / "local" / "memory"
    for group in ("developer", "project-volatile"):
        (base / group).mkdir(parents=True)
    (base / "developer" / "rule.md").write_text(
        _note("rule", startup="1", body="RULE-BODY"), "utf-8"
    )
    (base / "developer" / "other.md").write_text(
        _note("other", startup="2", body="OTHER-BODY"), "utf-8"
    )
    (root / CONFIG_FILE).write_text(CONFIG, encoding="utf-8")
    return root


def _store(root: Path, tmp_path: Path) -> Store:
    machine = tmp_path / "absent.toml"
    store = resolve(root, load(root, machine=machine), machine=machine)
    assert store is not None
    return store


def _status_of(root: Path, tmp_path: Path, name: str) -> str:
    store = _store(root, tmp_path)
    notes = {n.name: n for n in walk(store.path, list(store.groups)).notes}
    return status(store, notes[name])


def _bundle(root: Path, tmp_path: Path, bundle: str) -> str:
    code, out, err = cli(root, tmp_path, "memory", "session-context", "--bundle", bundle)
    assert code == 0, err
    return out


def test_a_note_with_no_record_is_unreviewed_and_no_standing_rule_whatever_it_ranks(
    tmp_path: Path,
) -> None:
    # `startup: 1` is the note's own claim, and a claim a note makes about itself is what a clone,
    # the native writer or an agent can write. With no record it reaches the session in the
    # volatile bundle, inside the data region and labelled, and never as a standing rule.
    # Mutation (oracle): `mutations/`'s "the standing rules admit an unreviewed note".
    root = _project(tmp_path)
    assert _status_of(root, tmp_path, "rule") == UNREVIEWED
    assert "RULE-BODY" not in _bundle(root, tmp_path, "standing-rules")
    volatile = _bundle(root, tmp_path, "volatile-notes")
    assert "### rule [unreviewed]" in volatile
    region = volatile[volatile.index(DELIMITER) :]
    assert "RULE-BODY" in region


def test_promote_marks_a_note_reviewed_and_it_enters_the_standing_rules(tmp_path: Path) -> None:
    root = _project(tmp_path)
    code, out, err = cli(root, tmp_path, "memory", "promote", "developer/rule.md", "--json")
    assert code == 0, err
    promoted = json.loads(out)["promoted"]
    assert [entry["path"] for entry in promoted] == ["developer/rule.md"]
    assert len(promoted[0]["digest"]) == 64
    assert _status_of(root, tmp_path, "rule") == REVIEWED
    assert "RULE-BODY" in _bundle(root, tmp_path, "standing-rules")
    assert "RULE-BODY" not in _bundle(root, tmp_path, "volatile-notes")
    # Only the note named: the other is no more reviewed than it was.
    assert _status_of(root, tmp_path, "other") == UNREVIEWED
    # The line says what was recorded, the path and the digest both.
    code, out, _ = cli(root, tmp_path, "memory", "promote", "developer/other.md")
    assert code == 0 and "developer/other.md" in out and len(out.split()[-1]) == 64


def test_an_edit_after_promotion_makes_that_note_unreviewed_and_moves_no_other(
    tmp_path: Path,
) -> None:
    # The record holds the digest of the bytes promoted, so an edit is a new note to review, and
    # the other note's record still holds. Mutation (oracle): `mutations/`'s "a stale digest
    # still reads as reviewed".
    root = _project(tmp_path)
    assert cli(root, tmp_path, "memory", "promote", "--changed")[0] == 0
    assert _status_of(root, tmp_path, "rule") == REVIEWED
    assert _status_of(root, tmp_path, "other") == REVIEWED
    path = root / ".stayfixed" / "local" / "memory" / "developer" / "rule.md"
    path.write_text(_note("rule", startup="1", body="RULE-BODY, edited"), "utf-8")
    assert _status_of(root, tmp_path, "rule") == UNREVIEWED
    assert _status_of(root, tmp_path, "other") == REVIEWED
    standing = _bundle(root, tmp_path, "standing-rules")
    assert "OTHER-BODY" in standing and "RULE-BODY" not in standing


def test_promote_changed_records_only_the_unreviewed_notes(tmp_path: Path) -> None:
    root = _project(tmp_path)
    assert cli(root, tmp_path, "memory", "promote", "developer/rule.md")[0] == 0
    code, out, _ = cli(root, tmp_path, "memory", "promote", "--changed", "--json")
    assert code == 0
    assert [entry["path"] for entry in json.loads(out)["promoted"]] == ["developer/other.md"]
    code, out, _ = cli(root, tmp_path, "memory", "promote", "--changed", "--json")
    assert (code, json.loads(out)["promoted"]) == (0, [])


@pytest.mark.parametrize(
    "argv,refusal",
    [
        (("developer/absent.md",), NOT_A_NOTE),
        (("../stayfixed.toml",), NOT_A_NOTE),
        ((), NOTHING_NAMED),
        (("developer/rule.md", "--changed"), NOTHING_NAMED),
    ],
    ids=["absent", "outside", "nothing", "both"],
)
def test_promote_refuses_what_is_no_note_of_the_store_and_records_nothing(
    tmp_path: Path, argv: tuple[str, ...], refusal: str
) -> None:
    root = _project(tmp_path)
    code, _, err = cli(root, tmp_path, "memory", "promote", *argv)
    assert code == 2
    assert refusal in err
    assert not (tmp_path / "trust.json").exists()


def test_a_revoked_record_makes_the_note_unreviewed_again(tmp_path: Path) -> None:
    # `trust list` and `trust revoke` read the record kind `reviewed` as any other kind.
    root = _project(tmp_path)
    assert cli(root, tmp_path, "memory", "promote", "developer/rule.md")[0] == 0
    code, out, _ = cli(root, tmp_path, "trust", "list", "--json")
    rows = json.loads(out)["approvals"]
    assert code == 0 and [row["kind"] for row in rows] == ["reviewed"]
    subject = rows[0]["subject"]
    assert cli(root, tmp_path, "trust", "revoke", "reviewed", "--subject", subject)[0] == 0
    assert _status_of(root, tmp_path, "rule") == UNREVIEWED


def test_a_trust_record_that_cannot_be_read_leaves_every_note_unreviewed(tmp_path: Path) -> None:
    # Closed: a record nothing can read promotes nothing, so no note becomes a standing rule on
    # it, and the session still gets every note as data.
    root = _project(tmp_path)
    assert cli(root, tmp_path, "memory", "promote", "--changed")[0] == 0
    (tmp_path / "trust.json").write_text("{not json", encoding="utf-8")
    assert _status_of(root, tmp_path, "rule") == UNREVIEWED
    assert "RULE-BODY" not in _bundle(root, tmp_path, "standing-rules")


def test_the_count_line_is_said_once_for_a_new_set_and_not_again_for_the_same_set(
    tmp_path: Path,
) -> None:
    # Said at `SessionStart` only when the set of unreviewed notes differs from the last
    # session's, so a session over an unchanged store hears nothing, and a new note is news.
    from stayfixed.hooks.api import HookEvent

    root = _project(tmp_path)
    config = load(root, machine=tmp_path / "absent.toml")
    (handler,) = [h for h in register() if h.event == "SessionStart"]
    event = HookEvent("SessionStart", "s1", None, None, {}, root, root, {})

    def said() -> str | None:
        return handler.run(event, session_of(config)).context

    assert said() == UNREVIEWED_COUNT.format(count=2)
    assert said() is None
    (root / ".stayfixed" / "local" / "memory" / "developer" / "third.md").write_text(
        _note("third"), "utf-8"
    )
    assert said() == UNREVIEWED_COUNT.format(count=3)
    assert said() is None
