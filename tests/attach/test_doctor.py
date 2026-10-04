"""What the `attached` row in `stayfixed doctor` answers, now that `attach` contributes it.

Every case runs the whole report through `run_checks`, so the row is asked the way a user's
`stayfixed doctor` asks it: discovered in this area's `doctor.py`, with the overlay root and the
note store resolved by the lazy value its `register()` creates. The fixtures are the doctor
area's own (`tests/doctor/test_checks.py`), shared rather than respelled, because the
`hook-entries` cases there read the same attached checkout.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from stayfixed.config.layout import ATTACH_LEDGER as LEDGER
from stayfixed.config.loader import load
from stayfixed.doctor.api import OK, SKIP, WARN, Check
from stayfixed.memory.api import PROJECT_RECORD, PROJECTS, resolve
from stayfixed.memory.trust import record
from tests.doctor.test_checks import (
    LOCAL_ONLY,
    OVERLAY,
    _attached,
    _by_name,
    _checks,
    _initialised,
    _machine,
    _no_overlay_machine,
    _overlay,
)
from tests.gitfixture import git as _git

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")


# The row as `stayfixed doctor --json` printed it for a project that was never attached, captured
# from the code before the row moved into this area and pasted here, never derived from the code
# under test: the move is a move only if these bytes are what a detached or never-attached
# checkout still reads.
UNATTACHED = {
    "overlay": Check(
        "attached",
        "warn",
        "memory.mode is overlay and .stayfixed/local/attach.json does not exist, so nothing "
        "records an attach",
        "run `stayfixed attach --store <overlay>/projects/<project>/memory --check`",
    ),
    "local-only": Check(
        "attached", "ok", "memory.mode is local-only; there is no overlay to bind to", ""
    ),
}


@pytest.mark.parametrize("mode", sorted(UNATTACHED))
def test_an_unattached_project_reports_attached_as_it_did(tmp_path: Path, mode: str) -> None:
    # A checkout with a `stayfixed.toml` and a git repository and nothing `attach` wrote: the
    # state `detach` leaves, and the state of a fresh clone. The whole row is compared, status,
    # sentence and remedy, because a move that reworded any of them is a change a reader of the
    # report sees. Mutation (measured by hand): "does not exist" reworded to "is missing" in the
    # row's sentence -> the `overlay` case reddens.
    template = OVERLAY if mode == "overlay" else LOCAL_ONLY
    root = _initialised(tmp_path, template=template)
    _git(root, "init", "-q", "-b", "main")
    rows = _checks(tmp_path, root)
    assert [row for row in rows if row.name == "attached"] == [UNATTACHED[mode]]


def test_an_overlay_recording_another_remote_is_red_and_never_merely_attached(
    tmp_path: Path,
) -> None:
    # The binding mismatch `attach` refuses, seen from `doctor` instead: the ledger says this
    # checkout is attached and the overlay's own project record names a different remote, so
    # the notes on the other side of that binding are another repository's. The arm existed and
    # no case reached it — an installation in this state read as ordinarily attached.
    root = _attached(tmp_path)
    (tmp_path / "overlay" / PROJECTS / "p" / PROJECT_RECORD).write_text(
        'remote = "git@github.com:somebody/else.git"\nfirst_attach = "2026-09-18"\n',
        encoding="utf-8",
    )
    check = _by_name(_checks(tmp_path, root, machine=_machine(tmp_path)), "attached")
    assert check.status == "red"
    assert "a different remote" in check.detail
    # The other repository's remote is overlay-authored, not repository-authored — but it is
    # still somebody's private URL, and this row has no reason to print one.
    assert "somebody/else" not in check.detail and "somebody/else" not in check.remedy


def test_a_project_with_no_overlay_to_bind_to_is_green_and_says_which_mode(tmp_path: Path) -> None:
    # The arm every `local-only` fixture in this file runs through and none of them asserts on.
    # It is the row's one green-without-an-overlay answer, and it is what keeps the three red
    # and warn arms below from being reachable by an ordinary un-attached project.
    check = _by_name(_checks(tmp_path, _initialised(tmp_path)), "attached")
    assert check.status == "ok"
    assert "local-only" in check.detail


def test_an_overlay_project_with_no_ledger_is_a_warning_naming_the_file(tmp_path: Path) -> None:
    # `memory.mode = "overlay"` and nothing recording an attach. Not red: a project may be
    # configured for an overlay before anyone has run `stayfixed attach` in this checkout, which
    # is the ordinary state of a fresh clone. The remedy is the command that ends it.
    root = _attached(tmp_path)
    (root / LEDGER).unlink()
    check = _by_name(_checks(tmp_path, root, machine=_machine(tmp_path)), "attached")
    assert check.status == "warn"
    assert LEDGER in check.detail
    assert "stayfixed attach" in check.remedy


def test_a_memory_path_that_is_a_real_directory_is_red_rather_than_ok(tmp_path: Path) -> None:
    # The shape an existing checkout can already have, and the one this row exists for, because
    # it looks attached and behaves like nothing. `~/.claude/projects/<slug>/memory` is where
    # the harness's own native reader looks, and a real directory there reads as an empty store
    # while the notes sit untouched in the overlay.
    root = _attached(tmp_path)
    home = tmp_path / "home"
    slug = str(root.resolve()).replace("/", "-").replace(".", "-")
    (home / ".claude" / "projects" / slug / "memory").mkdir(parents=True)
    check = _by_name(_checks(tmp_path, root, home=home, machine=_machine(tmp_path)), "attached")
    assert check.status == "red"
    assert "real directory" in check.detail


def _harness(tmp_path: Path, root: Path) -> Path:
    """Where `~/.claude/projects/<slug>/memory` is for this root, with its parent made."""
    slug = str(root.resolve()).replace("/", "-").replace(".", "-")
    harness = tmp_path / "home" / ".claude" / "projects" / slug / "memory"
    harness.parent.mkdir(parents=True)
    return harness


def test_a_harness_link_pointing_at_the_store_is_green(tmp_path: Path) -> None:
    # The vacuity guard for the test above, and for the three below it. The same fixture, with
    # the shape `attach` leaves: a symlink whose target really is the store this checkout
    # resolves, which in overlay mode is the link tree at `paths.memory`.
    #
    # This assertion used to be the *only* one on this row's green path, and the check never
    # compared the link's target — so it passed for a symlink to anything at all and the three
    # cases below were green with it. It is kept because a fix that reddened the correct shape
    # would be worse than the defect.
    root = _attached(tmp_path)
    harness = _harness(tmp_path, root)
    harness.symlink_to(root / "docs" / "memory")
    check = _by_name(
        _checks(tmp_path, root, home=tmp_path / "home", machine=_machine(tmp_path)), "attached"
    )
    assert check.status == "ok"
    assert "a link to the store" in check.detail


def test_a_harness_link_pointing_at_an_unrelated_directory_is_never_green(tmp_path: Path) -> None:
    # The state the row used to print "the harness memory path is a link to the store" for, in
    # green, while the harness's native reader was reading somebody else's notes. This link is
    # the one channel attached notes take to reach the model, so a false sentence about where
    # that memory comes from is the most expensive thing this check could say.
    #
    # Mutation: `mutations/`'s "doctor stops asking what the harness memory path points at".
    root = _attached(tmp_path)
    elsewhere = tmp_path / "somebody-elses-notes"
    elsewhere.mkdir()
    _harness(tmp_path, root).symlink_to(elsewhere)
    check = _by_name(
        _checks(tmp_path, root, home=tmp_path / "home", machine=_machine(tmp_path)), "attached"
    )
    assert check.status == "red"
    assert "a link to the store" not in check.detail
    assert check.remedy


def test_a_dangling_harness_link_is_never_green(tmp_path: Path) -> None:
    # The same defect's quieter half: the harness reads nothing through a link to a directory
    # that is not there, which looks attached and behaves like nothing one shape over from the
    # real directory the row above it already reddens.
    root = _attached(tmp_path)
    _harness(tmp_path, root).symlink_to(tmp_path / "never-existed")
    check = _by_name(
        _checks(tmp_path, root, home=tmp_path / "home", machine=_machine(tmp_path)), "attached"
    )
    assert check.status == "red"
    assert "dangling" in check.detail


def test_an_absent_harness_path_is_green_only_while_the_trust_record_asks_for_that(
    tmp_path: Path,
) -> None:
    # The row's own docstring is right that absent is not a fault by itself: the link is gated
    # on the same trust record every other channel is, so an unapproved store correctly has
    # none and reddening that would redden a correct fresh install. But the check has to *ask*
    # rather than assume — an approved store with no link is an attach that did not finish, and
    # the harness sees no memory at all. Both arms of `harness_link_needed`, one test.
    root = _attached(tmp_path)
    machine = _machine(tmp_path)
    before = _by_name(_checks(tmp_path, root, machine=machine), "attached")
    assert before.status == "ok"
    assert "trust record" in before.detail

    config = load(root, machine=machine)
    store = resolve(root, config, machine=machine)
    assert store is not None
    record(store, config)
    after = _by_name(_checks(tmp_path, root, machine=machine), "attached")
    assert after.status == "warn"
    assert after.remedy


def test_a_ledger_with_no_binding_in_the_overlay_is_a_warning_and_never_an_attach(
    tmp_path: Path,
) -> None:
    # `.stayfixed/local/attach.json` is a path a clone can commit, and `_attached` took its
    # existence as "this checkout was attached". The overlay is the trusted side, so the row
    # now asks it: a ledger with no `projects/<name>/project.toml` behind it is a warning
    # that names the file, and the remedy says what to do in each of the two cases.
    #
    # Mutation (declared): `if state == UNBOUND:` -> `if False:` -> the row falls
    # through to the harness-shape branch and this reddens on the sentence.
    root = _attached(tmp_path)
    overlay = _overlay(tmp_path)
    record = overlay / PROJECTS / "p" / PROJECT_RECORD
    assert record.is_file(), "the fixture must have recorded a binding for this to be a probe"
    record.unlink()
    row = _by_name(_checks(tmp_path, root, machine=_machine(tmp_path)), "attached")
    assert row.status == WARN
    assert "has no binding for this project" in row.detail
    assert "a clone can commit that file" in row.detail
    assert "attach --store" in row.remedy and "remove the ledger" in row.remedy


def test_a_ledger_naming_a_store_the_overlay_does_not_permit_is_a_warning(tmp_path: Path) -> None:
    # `_attached` asked the overlay only for its *state*, and `read_binding` answers with a
    # `Refusal` — not a state — when the store the ledger names is not this project's share of
    # the recorded overlay. That refusal used to collapse into the same `None` as "no overlay
    # recorded", the row skipped both new arms, and a repository that committed
    # `.stayfixed/local/attach.json` with any store it liked was reported `attached: ok` to a
    # model. This is the likeliest hostile shape of the three: an attacker cannot know
    # the victim's overlay root, so the store they commit is one the overlay does not permit.
    #
    # `warn` and not `skip`: this is a fact about the repository, and `skip` never reaches the
    # exit code.
    #
    # Mutation (declared): `except Refusal: return UNRESOLVED` -> `return UNASKABLE` -> the row
    # becomes a skip about this machine and this reddens on the status and the sentence.
    root = _attached(tmp_path)
    recorded = json.loads((root / LEDGER).read_text(encoding="utf-8"))
    recorded["store"] = str(tmp_path / "somewhere-else" / "memory")
    (root / LEDGER).write_text(json.dumps(recorded), encoding="utf-8")
    row = _by_name(_checks(tmp_path, root, machine=_machine(tmp_path)), "attached")
    assert row.status == WARN
    assert "is not this project's directory inside the overlay" in row.detail
    assert "not evidence of an attach" in row.detail
    assert "attached;" not in row.detail, "a ledger the overlay does not confirm is not an attach"
    assert "attach --store" in row.remedy and "remove the ledger" in row.remedy


def test_a_ledger_on_a_machine_that_records_no_overlay_skips_and_never_reads_as_attached(
    tmp_path: Path,
) -> None:
    # The universal case on a machine where `setup` has never run, and the other refusal beside the
    # one the test above covers: `read_binding` refuses for this too, and the row used to print
    # "attached" over it. It is a fact about *our own inputs*, so it is a `skip` that says what
    # could not be asked — never a warning that accuses the repository, and never the word
    # "attached".
    #
    # Mutation (declared): `if context.overlay is None: return NO_OVERLAY` -> `if False:` ->
    # the reason becomes `UNRESOLVED` (the refusal is indistinguishable once the arm is gone)
    # and this reddens on the status and the sentence.
    root = _attached(tmp_path)
    row = _by_name(_checks(tmp_path, root, machine=_no_overlay_machine(tmp_path)), "attached")
    assert row.status == SKIP
    assert "records no overlay to check it against" in row.detail
    assert "attached;" not in row.detail
    assert "stayfixed setup --overlay" in row.remedy


def test_an_overlay_record_this_process_cannot_read_skips_rather_than_reading_as_attached(
    tmp_path: Path,
) -> None:
    # The third of the three, and the one that is about neither side's honesty: the overlay is
    # recorded and its `projects/<name>/project.toml` will not parse, so `read_binding` raises
    # `Failure` and nothing can be said about the binding either way. A `skip` naming the
    # reason, and — the property all three share — not the word "attached".
    #
    # No mutation of its own: the arm it exercises is the `except (Failure, GitUnavailable)`
    # fallback, and the two declared mutations above already prove that `_binding_answer`'s
    # three answers are told apart rather than collapsed. This is the case that pins the
    # fallback's own sentence.
    root = _attached(tmp_path)
    overlay = _overlay(tmp_path)
    (overlay / PROJECTS / "p" / PROJECT_RECORD).write_text("remote = [", encoding="utf-8")
    row = _by_name(_checks(tmp_path, root, machine=_machine(tmp_path)), "attached")
    assert row.status == SKIP
    assert "the overlay could not be asked about it here" in row.detail
    assert "attached;" not in row.detail


def test_an_attached_checkout_the_overlay_confirms_is_still_green_and_says_the_binding(
    tmp_path: Path,
) -> None:
    # The vacuity guard for the three above: refusing to print "attached" whenever the overlay
    # did not answer must not become refusing to print it at all. The fixture is the state a
    # real attach leaves, the overlay's record matches this checkout's remote, and the row says
    # so with the binding's own label on it.
    root = _attached(tmp_path)
    row = _by_name(_checks(tmp_path, root, machine=_machine(tmp_path)), "attached")
    assert row.status == OK
    assert row.detail.startswith("attached;")
    assert "the binding is bound" in row.detail


def test_a_ledger_that_cannot_be_read_is_this_repositorys_doing_and_never_blamed_on_git(
    tmp_path: Path,
) -> None:
    # `_binding_answer` had three answers and needed four. A ledger that is there and will not
    # parse was joining "no overlay" and "no git" under `unaskable`, so the row said "no `git`,
    # or a record this process could not read" and the remedy said "run `stayfixed doctor` again
    # where `git` runs" — about a file in the checkout the reader is standing in. `skip` never
    # reaches the exit code either, so a clone's committed, malformed ledger was silent, which
    # is the split `_uncorroborated`'s own docstring exists to make.
    #
    # Mutation (declared): the unreadable ledger answers `UNASKABLE` again -> the row is `skip`,
    # blames `git`, and every assertion below reddens.
    root = _attached(tmp_path)
    (root / LEDGER).write_text("this is not json", encoding="utf-8")
    row = _by_name(_checks(tmp_path, root, machine=_machine(tmp_path)), "attached")

    assert row.status == WARN
    assert f"{LEDGER} is here and cannot be read as a ledger" in row.detail
    assert "`git`" not in row.detail and "`git`" not in row.remedy
    assert LEDGER in row.remedy
