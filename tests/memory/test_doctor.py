"""What the `bundles`, `store-debris` and `harness-link` rows in `stayfixed doctor` answer, now
that `memory` contributes them.

Every case runs the whole report through `run_checks`, so the rows are asked the way a user's
`stayfixed doctor` asks them: discovered in this area's `doctor.py`, with the note store resolved
by the lazy value its `register()` creates. The fixtures are the doctor area's own
(`tests/doctor/test_checks.py`), shared rather than respelled.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

import stayfixed.memory.answers as answers_module
from stayfixed.config.loader import load
from stayfixed.doctor.api import OK, RED, SKIP, WARN, Check
from stayfixed.errors import Refusal
from stayfixed.memory.api import PROJECTS
from stayfixed.memory.doctor import NEARLY_FULL
from stayfixed.memory.hooks import (
    NO_HARNESS_LINK,
    NO_HARNESS_LINK_NO_HOME,
    NO_HARNESS_LINK_OVERLAY,
    Withheld,
)
from tests.doctor.test_checks import (
    LOCAL_ONLY,
    OVERLAY,
    _attached,
    _by_name,
    _checks,
    _env,
    _initialised,
    _machine,
)
from tests.ownerhome import as_owner_home

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")

# A local-only project whose one group leaves the store, with the store's directory in place so
# the resolver reaches the group rather than stopping at a missing directory, and answers no store
# for it.
OUTSIDE = """
[stayfixed]
version = "{version}"
state = "installed"

[project]
name = "p"

[memory]
mode = "local-only"
groups = ["../outside"]
"""


@pytest.mark.parametrize("how", ["group-outside-the-store", "resolver-raises"])
def test_a_store_that_refuses_skips_the_store_checks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, how: str
) -> None:
    # A `stayfixed.toml` is repository-authored, so a `memory.groups` that makes the store refuse
    # is the repository's to write. The two rows that read the store skip on it, as they did
    # when the core resolved the store for them; neither may turn red, because red gates the exit
    # code and a check that "could not run" is not something the repository did wrong.
    #
    # Two cases, because the resolver has two ways of not handing a store over. Asked about a
    # group that leaves the store, it answers no store at all rather than refusing, which is what
    # every `memory.groups` value measured here gets from it. The second case is the resolver
    # raising `Refusal` instead, which is what the lazy value's `except` exists for and what no
    # `memory.groups` reaches today, so it is stood in for by replacing the resolver where the lazy
    # value calls it, in `memory.answers`.
    #
    # Mutation (oracle): `mutations/`'s "the delivery rows let a refusing store escape" -> the
    # `Refusal` reaches the guard and both rows are red, "this check could not run: Refusal".
    root = _initialised(tmp_path, template=OUTSIDE)
    (root / ".stayfixed" / "local" / "memory").mkdir(parents=True)
    if how == "resolver-raises":

        def refuses(*args: object, **kwargs: object) -> None:
            raise Refusal("the store refused")

        monkeypatch.setattr(answers_module, "resolve", refuses)
    rows = {row.name: row for row in _checks(tmp_path, root)}
    for name in ("bundles", "store-debris"):
        assert rows[name].status == SKIP, rows[name]
    assert not any(row.status == RED for row in rows.values()), [
        (row.name, row.detail) for row in rows.values() if row.status == RED
    ]


def _note(body: str, *, name: str, startup: int) -> str:
    return (
        f"---\nname: {name}\ndescription: a standing rule\nmetadata:\n"
        f"  type: rule\n  startup: {startup}\n---\n\n{body}"
    )


def test_a_bundle_that_does_not_fit_its_slots_is_reported(tmp_path: Path) -> None:
    # A bundle whose notes do not fit its slots is the condition that needs a human — raising N
    # edits a shipped file — so doctor reports it. Four standing notes of a whole slot each,
    # against the three `standing-rules` entries `hooks/hooks.json` declares.
    #
    # In the overlay, not in a local-only store: `trust.may_inject` gates a store that lives in
    # the repository, so an untrusted local store renders every bundle empty and this assertion
    # would pass for having measured nothing.
    root = _attached(tmp_path)
    store = tmp_path / "overlay" / PROJECTS / "p" / "memory" / "developer"
    for index in range(4):
        (store / f"note-{index}.md").write_text(
            _note("word " * 2_000, name=f"note-{index}", startup=index + 1), encoding="utf-8"
        )
    check = _by_name(
        _checks(tmp_path, root, machine=_machine(tmp_path)),
        "bundles",
    )
    assert check.status == "red"
    assert "standing-rules" in check.detail


def test_a_bundle_that_fits_is_not_reported(tmp_path: Path) -> None:
    # The vacuity guard for the test above: one short standing rule fits its slots and is
    # nowhere near the platform cap, which is the ordinary installation, and the row stays green.
    root = _attached(tmp_path)
    store = tmp_path / "overlay" / PROJECTS / "p" / "memory" / "developer"
    (store / "short.md").write_text(_note("a short rule", name="short", startup=1), "utf-8")
    check = _by_name(
        _checks(tmp_path, root, machine=_machine(tmp_path)),
        "bundles",
    )
    assert check.status == "ok"


def test_a_bundle_whose_largest_part_is_at_the_platform_cap_is_a_warning(tmp_path: Path) -> None:
    # `NEARLY_FULL` appeared in no test at all: the constant, the fraction and the whole `full`
    # arm were dead. It is the warning *before* the red row above — one more sentence in one
    # note and the bundle needs a slot that does not exist, and raising a slot count edits
    # `hooks/hooks.json`, which is a shipped file and a change somebody has to make deliberately.
    #
    # One standing note sized into the band between the threshold and the cap, so this is
    # neither the `over` arm (which would be red) nor the green one. Both are asserted, because
    # "warn" alone would also be produced by a `full` list built from the wrong predicate.
    root = _attached(tmp_path)
    store = tmp_path / "overlay" / PROJECTS / "p" / "memory" / "developer"
    cap = load(root, machine=_machine(tmp_path)).native_caps.hook_output_chars
    body = "word " * ((int(cap * NEARLY_FULL) + 600) // 5)
    (store / "big.md").write_text(_note(body, name="big", startup=1), encoding="utf-8")
    check = _by_name(_checks(tmp_path, root, machine=_machine(tmp_path)), "bundles")
    assert check.status == "warn", check.detail
    assert "standing-rules" in check.detail
    assert "at the platform cap" in check.detail


def test_a_note_store_holding_something_that_is_not_a_note_is_reported(tmp_path: Path) -> None:
    # `store-debris`. The count is stayfixed's own; the file names are not, so they are
    # counted rather than printed and the remedy names the command that lists them.
    root = _initialised(tmp_path)
    store = root / ".stayfixed" / "local" / "memory" / "developer"
    store.mkdir(parents=True)
    (store / "kept.md").write_text("---\nname: kept\ndescription: d\n---\n\nbody\n")
    (store / "scratch.txt").write_text("not a note\n", encoding="utf-8")
    check = _by_name(_checks(tmp_path, root), "store-debris")
    assert check.status == "warn"
    assert "1" in check.detail
    assert "scratch.txt" not in check.detail


@pytest.mark.parametrize(
    ("mode", "withheld"),
    [("overlay", NO_HARNESS_LINK_OVERLAY), ("local-only", NO_HARNESS_LINK)],
    ids=["overlay", "local-only"],
)
def test_a_home_the_database_does_not_record_is_told_what_it_costs_the_harness_link(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str, withheld: Withheld
) -> None:
    # A hook trusts only the password database's home and the harness finds its memory directory
    # through `HOME`, so where the two differ the hook makes no harness link. The session is told
    # once, at its start; this row is where the owner reads it again, in the hook's own words, so
    # the two never disagree: `attach` from a terminal for an overlay store, which `attach` binds,
    # and for the other modes, which it refuses, nothing but the hook. Mutations (oracle):
    # `mutations/`'s "the harness-link row reads HOME as the database's home whatever it names"
    # -> ok; "the withheld link line names attach for every store" -> the local-only case.
    as_owner_home(monkeypatch, tmp_path / "owner")
    root = _initialised(tmp_path, template=OVERLAY if mode == "overlay" else LOCAL_ONLY)
    check = _by_name(_checks(tmp_path, root, env=_env(tmp_path, HOME="fakehome")), "harness-link")
    assert check == Check("harness-link", WARN, withheld.cause, withheld.remedy)


def test_a_user_the_database_lists_no_home_for_is_told_the_hook_makes_no_link(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # No entry and no `HOME` agree with nothing, so no hook makes the link, and for a store
    # `attach` does not bind nothing else does either. Mutation (oracle): `mutations/`'s "the
    # withheld link line points a user with no home at a home" -> the other words.
    as_owner_home(monkeypatch, None)
    check = _by_name(_checks(tmp_path, _initialised(tmp_path)), "harness-link")
    assert check == Check(
        "harness-link", WARN, NO_HARNESS_LINK_NO_HOME.cause, NO_HARNESS_LINK_NO_HOME.remedy
    )


def test_a_home_the_database_records_leaves_the_harness_link_to_the_hook(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The vacuity guard for the two above, and it is asked of the report's environment, never of
    # this process's, whose `HOME` is the suite's and not the owner's. Mutation (oracle):
    # `mutations/`'s "the harness-link row asks this process's HOME rather than the report's" ->
    # a warning.
    owner = tmp_path / "owner"
    owner.mkdir()
    as_owner_home(monkeypatch, owner)
    assert os.environ["HOME"] != str(owner)
    check = _by_name(
        _checks(tmp_path, _initialised(tmp_path), env=_env(tmp_path, HOME=str(owner))),
        "harness-link",
    )
    assert check.status == OK, check
