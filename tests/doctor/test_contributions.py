"""An area adds rows to `stayfixed doctor` through its own `doctor.py`, discovered by name, and
tells `hook-entries` what it put into settings files through its `Claims`.

The fake areas below are modules injected through `checks.discover_contributors`, the seam the
discovery reads, the way `tests/test_cli.py` replaces `cli.discover_registrars`: a test that
shipped a real `doctor.py` to prove the convention would be a check in every user's report. With
the fakes in place no real area is discovered, so what these cases prove is the core's reading of
a contribution; what a real area answers is proven in that area's own tests.
"""

from __future__ import annotations

import json
import shutil
from collections.abc import Mapping
from pathlib import Path
from types import ModuleType

import pytest

from stayfixed.config.layout import ATTACH_LEDGER
from stayfixed.doctor import checks
from stayfixed.doctor.api import OK, RED, SKIP, WARN, Check, Claims, Context, Contribution, Row
from tests.doctor.test_checks import _checks, _initialised

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")

CORE = [name for name, _ in checks.CHECKS]


def _area(name: str, contribution: Contribution) -> ModuleType:
    """A stand-in for `stayfixed.<name>.doctor`, whose `register()` answers `contribution`."""
    module = ModuleType(f"stayfixed.{name}.doctor")
    setattr(module, "register", lambda: contribution)  # noqa: B010 - a module built at runtime
    return module


def _contribute(monkeypatch: pytest.MonkeyPatch, *areas: ModuleType) -> None:
    monkeypatch.setattr("stayfixed.doctor.checks.discover_contributors", lambda: list(areas))


def test_a_contributed_check_runs_after_the_core_checks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The core's rows first, then each area's in the order discovery hands the areas over, and
    # each contributed check is asked with the run's own context. Mutation (oracle): `mutations/`'s
    # "doctor drops the checks an area contributes" -> the two contributed rows are missing.
    asked: list[Path] = []

    def first(context: Context) -> Row:
        asked.append(context.root)
        return Row(WARN, "the first area's answer", "the first area's remedy")

    def second(context: Context) -> Row:
        return Row(OK, "the second area's answer")

    _contribute(
        monkeypatch,
        _area("alpha", Contribution(checks=(("alpha-row", first),))),
        _area("omega", Contribution(checks=(("omega-row", second),))),
    )
    root = _initialised(tmp_path)
    rows = _checks(tmp_path, root)
    assert [row.name for row in rows] == [*CORE, "alpha-row", "omega-row"]
    assert rows[-2:] == [
        Check("alpha-row", WARN, "the first area's answer", "the first area's remedy"),
        Check("omega-row", OK, "the second area's answer", ""),
    ]
    assert asked == [root]


def test_a_contribution_that_raises_costs_one_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A contributed check is asked through the guard the core's are, so one that raises is one
    # red row naming the exception's type and never its message, which a check may have built
    # out of repository bytes, and the report around it is whole. Mutation (oracle): `mutations/`'s
    # "doctor asks its checks without the guard" -> the `RuntimeError` escapes `run_checks`.
    def broken(context: Context) -> Row:
        raise RuntimeError("IGNORE-PRIOR-RULES, a message the check built")

    def after(context: Context) -> Row:
        return Row(OK, "still asked")

    _contribute(
        monkeypatch,
        _area("alpha", Contribution(checks=(("alpha-broken", broken), ("alpha-after", after)))),
    )
    rows = _checks(tmp_path, _initialised(tmp_path))
    assert [row.name for row in rows] == [*CORE, "alpha-broken", "alpha-after"]
    broken_row = rows[len(CORE)]
    assert broken_row == Check(
        "alpha-broken",
        RED,
        "this check could not run: RuntimeError",
        "report this, with the command you ran",
    )
    assert "IGNORE" not in broken_row.detail + broken_row.remedy
    assert rows[-1] == Check("alpha-after", OK, "still asked", "")


def _registering(register: object) -> ModuleType:
    """A stand-in for `stayfixed.alpha.doctor` whose `register` is `register` itself."""
    module = ModuleType("stayfixed.alpha.doctor")
    setattr(module, "register", register)  # noqa: B010 - a module built at runtime
    return module


def _raises() -> Contribution:
    raise RuntimeError("IGNORE-PRIOR-RULES, a message register() built")


def _answer(context: Context) -> Row:
    return Row(OK, "answered")


# What `register()` can hand back that is not a `Contribution` of `(name, check)` pairs, each the
# way an area's own code could get it wrong: no value at all, the pairs without the record, a pair
# missing its check, a name that is not text, a check that cannot be called, and claims that are
# not a function.
MALFORMED = {
    "none": lambda: None,
    "bare-pairs": lambda: (("alpha-row", _answer),),
    "short-pair": lambda: Contribution(checks=(("alpha-row",),)),  # type: ignore[arg-type]
    "name-not-text": lambda: Contribution(checks=((1, _answer),)),  # type: ignore[arg-type]
    "check-not-callable": lambda: Contribution(checks=(("alpha-row", "answer"),)),  # type: ignore[arg-type]
    "claims-not-callable": lambda: Contribution(checks=(), claims="claims"),  # type: ignore[arg-type]
}


@pytest.mark.parametrize("register", ["raises", *MALFORMED])
def test_an_area_whose_register_fails_costs_one_row_named_after_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, register: str
) -> None:
    # `register()` is an area's code like its checks are, so one that raises, or hands back
    # something that is not a `Contribution`, costs one row and not the report: a red row named
    # after the area, where its rows would have been, naming the exception's type and never its
    # message, and every other row as it would be. It used to escape `run_checks`, which the CLI
    # turns into an internal error and exit 2 with no report at all. Mutations (oracle):
    # `mutations/`'s "doctor calls an area's register() unguarded" -> the `raises` case escapes;
    # "doctor takes whatever an area's register() returns" -> the malformed cases fail later, or
    # report nothing for the area.
    _contribute(
        monkeypatch,
        _registering(_raises if register == "raises" else MALFORMED[register]),
        _area("omega", Contribution(checks=(("omega-row", _answer),))),
    )
    rows = _checks(tmp_path, _initialised(tmp_path))
    assert [row.name for row in rows] == [*CORE, "alpha", "omega-row"]
    broken = rows[len(CORE)]
    if register == "raises":
        detail = "stayfixed.alpha.doctor could not contribute its rows: RuntimeError"
    else:
        detail = (
            "stayfixed.alpha.doctor could not contribute its rows: its register() did not "
            "return a Contribution of (name, check) pairs"
        )
    assert broken == Check("alpha", RED, detail, "report this, with the command you ran")
    assert "IGNORE" not in broken.detail + broken.remedy
    assert rows[-1] == Check("omega-row", OK, "answered", "")


def test_an_area_whose_register_fails_is_red_even_with_nothing_else_to_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # With no `stayfixed.toml` every check after the first skips, because each would be asked
    # with no configuration. An area that could not contribute is not that: its row is about
    # stayfixed's own code, which no configuration changes, so it is red in the early report too.
    # Mutation (oracle): `mutations/`'s "the early report skips an area that could not register"
    # -> the row is a skip.
    _contribute(monkeypatch, _registering(_raises))
    rows = _checks(tmp_path, tmp_path)
    assert [row.name for row in rows] == [*CORE, "alpha"]
    assert rows[-1].status == RED
    assert rows[-1].detail == "stayfixed.alpha.doctor could not contribute its rows: RuntimeError"


@pytest.mark.parametrize("clash", ["core", "another-area"])
def test_a_contributed_name_may_not_repeat_a_core_or_another_areas_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, clash: str
) -> None:
    # A row's name is all a reader, the summary line and `--json` key on, so two rows under one
    # name are two answers nobody can tell apart. Refused at discovery, before any check is asked
    # and whatever the repository holds — here, not even a `stayfixed.toml`. Mutation (oracle):
    # `mutations/`'s "doctor lets two checks share one name" -> both cases report instead.
    def answer(context: Context) -> Row:
        return Row(OK, "answered")

    if clash == "core":
        _contribute(monkeypatch, _area("alpha", Contribution(checks=((CORE[1], answer),))))
        owner = "the core"
    else:
        _contribute(
            monkeypatch,
            _area("alpha", Contribution(checks=(("shared-row", answer),))),
            _area("omega", Contribution(checks=(("shared-row", answer),))),
        )
        owner = "stayfixed.alpha.doctor"
    with pytest.raises(checks.DuplicateCheck) as refused:
        _checks(tmp_path, tmp_path)
    assert owner in str(refused.value)


def test_a_contributed_check_skips_with_the_core_when_there_is_nothing_to_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The report has one row per check whatever state the repository is in, so with no
    # `stayfixed.toml` a contributed check gets the skip every core check after the first gets,
    # and is never asked: it would be asked with no configuration to read. Mutation (oracle):
    # `mutations/`'s "the early report names the core's checks alone" -> the row is missing.
    def unreachable(context: Context) -> Row:
        raise AssertionError("asked with no configuration")

    _contribute(monkeypatch, _area("alpha", Contribution(checks=(("alpha-row", unreachable),))))
    rows = _checks(tmp_path, tmp_path)
    assert [row.name for row in rows] == [*CORE, "alpha-row"]
    assert rows[-1].status == SKIP


# --- `Claims`: what each area says it put into settings files ----------------------------------

# Two entries claiming the marker, one for each of two areas, in a settings file `hook-entries`
# walks. Each area records its own id and grants its own command, so neither answer alone vouches
# for both entries, and an entry is absolved only by the one area that both records and grants it.
ALPHA = "echo alpha  # stayfixed:alpha-1"
OMEGA = "echo omega  # stayfixed:omega-1"
# An entry claiming the marker that no area records: red whenever the records can be read, so a
# row that is not red with it in the file is a row that withheld the column.
NOBODYS = "echo nobody  # stayfixed:nobody-1"
# An entry claiming an id alpha records, with a command alpha does not grant: red whenever the
# grants can be read, so a row that is not red with it in the file withheld the grant comparison.
STRAY = "echo stray  # stayfixed:alpha-1"
SETTINGS = ".claude/settings.json"


def _hooked(root: Path, *commands: str) -> None:
    """`root`'s `SETTINGS`, holding one `PreToolUse` hook entry per command, in order."""
    assert SETTINGS in checks.SETTINGS_FILES, "the walk would never open this file"
    entries = [{"type": "command", "command": command} for command in commands]
    (root / SETTINGS).parent.mkdir(parents=True, exist_ok=True)
    (root / SETTINGS).write_text(
        json.dumps({"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": entries}]}}),
        encoding="utf-8",
    )


def _claiming(
    recorded: Mapping[str, str] | None, granted: frozenset[str] | None, *, sourced: bool = True
) -> Contribution:
    """An area that contributes no row and answers `Claims(recorded, granted, sourced)` when
    asked."""
    return Contribution(checks=(), claims=lambda context: Claims(recorded, granted, sourced))


ALPHA_CLAIMS = _claiming({"alpha-1": "PreToolUse"}, frozenset({ALPHA}))
OMEGA_CLAIMS = _claiming({"omega-1": "PreToolUse"}, frozenset({OMEGA}))


def _hook_entries(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *areas: ModuleType) -> Check:
    _contribute(monkeypatch, *areas)
    return next(
        row for row in _checks(tmp_path, tmp_path / "project") if row.name == "hook-entries"
    )


def test_hook_entries_reads_what_every_area_claims(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Each area answers for the entries it put there, so the row asks every area: alpha's entry
    # is vouched for by alpha's record and grant, omega's by omega's, and an area that contributes
    # a row and no claims takes no part. Mutations (oracle): `mutations/`'s "hook-entries keeps
    # only the last area's recorded ids" and "hook-entries keeps only the last area's granted
    # commands" -> alpha's entry is no longer vouched for and the row is red; "hook-entries
    # ignores what the areas claim" -> neither is.
    def answer(context: Context) -> Row:
        return Row(OK, "answered")

    _hooked(_initialised(tmp_path), ALPHA, OMEGA)
    row = _hook_entries(
        tmp_path,
        monkeypatch,
        _area("alpha", ALPHA_CLAIMS),
        _area("beta", Contribution(checks=(("beta-row", answer),))),
        _area("omega", OMEGA_CLAIMS),
    )
    assert row == Check("hook-entries", OK, "2 stayfixed entr(ies), 0 foreign; all accounted for")


def test_one_areas_record_and_another_areas_grant_never_absolve_an_entry_together(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A record and a grant vouch for an entry only when they are one area's: that area wrote the
    # entry and its overlay still grants it. Pooled, alpha's record of the id and omega's grant of
    # the command absolved an entry neither area put there whole — and a record is a file a
    # repository can write, so the pool let one area's committable file borrow another's grant.
    # Mutation (oracle): `mutations/`'s "hook-entries absolves an entry on one area's record and
    # another area's grant" -> the entry is absolved and the row is green.
    _hooked(_initialised(tmp_path), ALPHA)
    row = _hook_entries(
        tmp_path,
        monkeypatch,
        _area("alpha", _claiming({"alpha-1": "PreToolUse"}, frozenset())),
        _area("omega", _claiming({}, frozenset({ALPHA}))),
    )
    assert row.status == RED, row
    assert (
        f"1 entr(ies) claim the stayfixed marker and are recorded in {ATTACH_LEDGER}, and the "
        f"overlay does not grant them: {SETTINGS} entry 1 of 1"
    ) in row.detail


def test_an_id_an_area_records_and_grants_for_another_command_is_never_absolved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The grant is compared by the marked command and not by its id: an id the area does record
    # and grant, hung on a command it does not grant, is a repository borrowing a real id. Alpha
    # vouches for `ALPHA`, and `STRAY` claims alpha's id with a command of its own. Mutation
    # (oracle): `mutations/`'s "hook-entries compares a grant by its id rather than its command"
    # -> `STRAY` is absolved with `ALPHA` and the row is green.
    _hooked(_initialised(tmp_path), ALPHA, STRAY)
    row = _hook_entries(tmp_path, monkeypatch, _area("alpha", ALPHA_CLAIMS))
    assert row.status == RED, row
    assert (
        f"1 entr(ies) claim the stayfixed marker and are recorded in {ATTACH_LEDGER}, and the "
        f"overlay does not grant them: {SETTINGS} entry 2 of 2"
    ) in row.detail


def test_an_id_an_area_records_and_nothing_grants_is_never_absolved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A record is a file a repository can write, so an id in it vouches for nothing until a grant
    # stands behind the entry's command. Mutation (oracle): `mutations/`'s "the attach ledger
    # vouches for a hook entry on its own" -> the entry is absolved and the row is green.
    _hooked(_initialised(tmp_path), ALPHA)
    row = _hook_entries(
        tmp_path, monkeypatch, _area("alpha", _claiming({"alpha-1": "PreToolUse"}, frozenset()))
    )
    assert row.status == RED
    assert "the overlay does not grant" in row.detail
    assert f"{SETTINGS} entry 1 of 1" in row.detail


# How the row tells an owner to get an unreadable record back.
REBUILD = (
    f"remove {ATTACH_LEDGER} and run `stayfixed attach --store "
    f"<overlay>/projects/<project>/memory` to write a new one"
)


@pytest.mark.parametrize(
    ("unknown", "where"),
    [
        ("recorded", "first"),
        ("recorded", "last"),
        ("granted", "first"),
        ("granted", "last"),
    ],
    ids=["recorded-first", "recorded-last", "granted-first", "granted-last"],
)
def test_a_none_from_any_area_is_none_for_the_pool(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, unknown: str, where: str
) -> None:
    # One area's `None` is an answer nobody else can stand in for: a record it could not read
    # may name ids no other record knows, an overlay it could not ask grants commands no other grant
    # covers. So the pool is unknown, whichever side of a good answer the `None` falls on, and
    # the row withholds what that answer decides and says which answer is missing. The probe is
    # the entry that answer would make red: `NOBODYS`, which no readable record holds and the area
    # whose record is unreadable grants, for a record; and `STRAY`, which alpha records and does
    # not grant, for a grant. Mutations (oracle):
    # `mutations/`'s "a later area's record overwrites one an earlier area could not read" and "a
    # later area's grants overwrite an overlay an earlier area could not ask" -> the `-first`
    # cases compute the column and are red; "hook-entries judges provenance against an overlay
    # that could not be asked" -> the `granted` cases are.
    probe = NOBODYS if unknown == "recorded" else STRAY
    _hooked(_initialised(tmp_path), ALPHA, probe)
    known = _claiming({"alpha-1": "PreToolUse"}, frozenset({ALPHA}))
    if unknown == "recorded":
        missing = _claiming(None, frozenset({ALPHA, NOBODYS}))
    else:
        missing = _claiming({"alpha-1": "PreToolUse"}, None)
    first, last = (missing, known) if where == "first" else (known, missing)
    row = _hook_entries(tmp_path, monkeypatch, _area("alpha", first), _area("omega", last))
    assert row.status == WARN, row
    assert "all accounted for" not in row.detail
    assert "are not recorded in" not in row.detail
    assert "the overlay does not grant" not in row.detail
    if unknown == "recorded":
        assert f"{ATTACH_LEDGER} is there and cannot be read as a ledger" in row.detail
        assert row.remedy == REBUILD
    else:
        assert "could not be asked which entries it grants" in row.detail
        assert row.remedy == (
            "run `stayfixed attach --check`, which reports why the overlay cannot be read"
        )


def test_an_id_no_area_records_is_red_even_where_no_overlay_can_be_asked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Whether any record holds an entry's id needs only the records, so an overlay nobody could
    # ask withholds the grant comparison and nothing else: a committed ledger beside a committed
    # entry it does not record is red on a machine with no overlay, where it used to be a
    # warning and an exit of 0. The entry alpha does record is not judged, and the row says why.
    # Mutation (oracle): `mutations/`'s "an overlay that cannot be asked silences an entry no
    # record holds" -> the row is a warning again.
    _hooked(_initialised(tmp_path), ALPHA, NOBODYS)
    row = _hook_entries(
        tmp_path, monkeypatch, _area("alpha", _claiming({"alpha-1": "PreToolUse"}, None))
    )
    assert row.status == RED, row
    assert (
        f"1 entr(ies) claim the stayfixed marker and are not recorded in {ATTACH_LEDGER}: "
        f"{SETTINGS} entry 2 of 2"
    ) in row.detail
    assert "could not be asked which entries it grants" in row.detail
    assert "the overlay does not grant" not in row.detail
    assert row.remedy == "open each entry named above and remove the ones you did not install"


UNREADABLE = (
    f"{ATTACH_LEDGER} is there and cannot be read as a ledger, so which of those entries "
    f"`stayfixed attach` installed could not be established"
)


@pytest.mark.parametrize("sourced", [True, False], ids=["sourced", "unsourced"])
def test_an_entry_no_grant_covers_is_red_whatever_an_unreadable_record_would_say(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, sourced: bool
) -> None:
    # An unreadable record may hold any id, so it withholds judgement of an entry only where its
    # area's grant covers the command: that entry may be the area's, and the row warns. An entry no
    # grant covers is red whatever the record would have said, because a record is a file a clone
    # can commit, and an unreadable one used to turn a forged entry's red into a warning and an
    # exit of 0. The row cannot say whether the record holds it, and does not. Mutations (oracle):
    # `mutations/`'s "an unreadable record withholds judgement of every entry" -> the row is a
    # warning; "an unreadable record reads as one recording nothing" -> `ALPHA` reads as not
    # recorded; "hook-entries says the overlay does not grant what no overlay was recorded to grant,
    # beside an unreadable record" -> `unsourced` reads the sentence for a recorded overlay.
    _hooked(_initialised(tmp_path), ALPHA, NOBODYS)
    granted = frozenset({ALPHA}) if sourced else frozenset()
    row = _hook_entries(
        tmp_path, monkeypatch, _area("alpha", _claiming(None, granted, sourced=sourced))
    )
    if sourced:
        why, where, remedy = (
            "the overlay does not grant them",
            f"{SETTINGS} entry 2 of 2",
            f"open each entry named above and remove the ones you did not install; then {REBUILD}",
        )
    else:
        why, where, remedy = (
            "this machine records no overlay",
            f"{SETTINGS} entry 1 of 2, {SETTINGS} entry 2 of 2",
            "open each entry named above and remove the ones you did not install; if you did "
            "install them, run `stayfixed setup --overlay <path>` to record the overlay that "
            f"grants them; then {REBUILD}",
        )
    count = 1 if sourced else 2
    assert row == Check(
        "hook-entries",
        RED,
        f"2 stayfixed entr(ies), 0 foreign; {UNREADABLE}; {count} entr(ies) claim the stayfixed "
        f"marker and {why}, so whatever {ATTACH_LEDGER} records, nothing on this machine vouches "
        f"for them: {where}",
        remedy,
    )


# What the row says of an entry a record holds where nothing could grant it, and how it ends.
UNSOURCED = (
    f"1 entr(ies) claim the stayfixed marker and are recorded in {ATTACH_LEDGER}, and this "
    f"machine records no overlay, so nothing on this machine vouches for them: "
    f"{SETTINGS} entry 1 of 1"
)
RECORD_A_SOURCE = (
    "open each entry named above and remove the ones you did not install; if you did install "
    "them, run `stayfixed setup --overlay <path>` to record the overlay that grants them, then "
    "`stayfixed attach --store <overlay>/projects/<project>/memory`"
)


def test_an_id_an_area_records_where_no_source_is_recorded_is_red_and_says_so(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # An area whose machine records no source to grant from answers an empty grant with
    # `sourced=False`, and the row reads that as what it is: nothing could vouch, so the entry is
    # red, and the sentence and remedy say to record a source rather than that one refused.
    # Mutation (oracle): `mutations/`'s "hook-entries says the overlay does not grant what no
    # overlay was recorded to grant" -> the row reads the recorded overlay's sentence.
    _hooked(_initialised(tmp_path), ALPHA)
    row = _hook_entries(
        tmp_path,
        monkeypatch,
        _area("alpha", _claiming({"alpha-1": "PreToolUse"}, frozenset(), sourced=False)),
    )
    assert row == Check(
        "hook-entries", RED, f"1 stayfixed entr(ies), 0 foreign; {UNSOURCED}", RECORD_A_SOURCE
    )


@pytest.mark.parametrize("record", ["readable", "unreadable"])
def test_a_file_this_walk_cannot_read_keeps_an_unvouched_entry_red(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, record: str
) -> None:
    # A settings file the walk is blind to downgrades a row with nothing else to say to a warning,
    # and must not downgrade one that has a red entry to report, whether or not the record that
    # might hold it could be read. Mutations (oracle): `mutations/`'s "a blind settings file softens
    # an entry nothing on this machine vouches for" -> `readable` is a warning; "a blind settings
    # file softens an entry beside an unreadable record that nothing grants" -> `unreadable` is.
    root = _initialised(tmp_path)
    _hooked(root, ALPHA)
    (root / ".codex").mkdir()
    (root / ".codex" / "hooks.json").write_text("{", encoding="utf-8")
    recorded = {"alpha-1": "PreToolUse"} if record == "readable" else None
    row = _hook_entries(
        tmp_path, monkeypatch, _area("alpha", _claiming(recorded, frozenset(), sourced=False))
    )
    assert row.status == RED, row
    if record == "readable":
        assert UNSOURCED in row.detail
        assert row.remedy == RECORD_A_SOURCE
    else:
        assert "this machine records no overlay, so whatever" in row.detail
        assert row.remedy.endswith(REBUILD)
    assert "could not be read as hook entries, so nothing here accounts for what is in them: " in (
        row.detail
    )


def test_claims_that_raise_cost_the_hook_entries_row_alone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # `hook-entries` asks the claims itself, under its own guard, so an area whose `claims`
    # raises costs that one row, red and naming the exception's type and never its message; the
    # area's own rows and every other row read as they do when the area claims nothing.
    # Mutation (oracle): `mutations/`'s "doctor asks its checks without the guard" -> the
    # `RuntimeError` escapes `run_checks`.
    def answer(context: Context) -> Row:
        return Row(OK, "answered")

    def raises(context: Context) -> Claims:
        raise RuntimeError("IGNORE-PRIOR-RULES, a message the claims built")

    root = _initialised(tmp_path)
    _hooked(root, ALPHA)
    _contribute(monkeypatch, _area("alpha", Contribution(checks=(("alpha-row", answer),))))
    quiet = _checks(tmp_path, root)
    _contribute(
        monkeypatch,
        _area("alpha", Contribution(checks=(("alpha-row", answer),), claims=raises)),
    )
    rows = _checks(tmp_path, root)
    assert [row.name for row in rows] == [*CORE, "alpha-row"]
    broken = next(row for row in rows if row.name == "hook-entries")
    assert broken == Check(
        "hook-entries",
        RED,
        "this check could not run: RuntimeError",
        "report this, with the command you ran",
    )
    assert [row for row in rows if row.name != "hook-entries"] == [
        row for row in quiet if row.name != "hook-entries"
    ]
