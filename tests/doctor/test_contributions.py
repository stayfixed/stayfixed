"""An area adds rows to `stayfixed doctor` through its own `doctor.py`, discovered by name, and
tells `hook-entries` what it put into settings files through its `Claims`.

The fake areas below are modules, or an import's exception in an area's place, injected through
`registry.discover_contributors`, the seam the discovery reads, the way `tests/test_cli.py`
replaces `cli.discover_registrars`: a test that shipped a real `doctor.py` to prove the
convention would be a check in every user's report. With the fakes in place no real area is
discovered, so what these cases prove is the core's reading of a contribution; what a real area
answers is proven in that area's own tests.
"""

from __future__ import annotations

import json
import shutil
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from types import ModuleType

import pytest

from stayfixed.doctor import checks, registry
from stayfixed.doctor.api import (
    OK,
    RED,
    SKIP,
    WARN,
    Check,
    Claims,
    Context,
    Contribution,
    Row,
    Wording,
)
from stayfixed.doctor.entries import SETTINGS_FILES
from tests.doctor.test_checks import _checks, _initialised

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")

CORE = [name for name, _ in checks.CHECKS]


def _area(name: str, contribution: Contribution) -> ModuleType:
    """A stand-in for `stayfixed.<name>.doctor`, whose `register()` answers `contribution`."""
    module = ModuleType(f"stayfixed.{name}.doctor")
    setattr(module, "register", lambda: contribution)  # noqa: B010 - a module built at runtime
    return module


def _contribute(
    monkeypatch: pytest.MonkeyPatch, *areas: ModuleType | tuple[str, Exception]
) -> None:
    """Discovery answering `areas` in order: each a module that imported, or the qualified name of
    one that did not with the exception its import raised."""
    found = [area if isinstance(area, tuple) else (area.__name__, area) for area in areas]
    monkeypatch.setattr("stayfixed.doctor.registry.discover_contributors", lambda: found)


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
# way an area's own code could get it wrong: no value at all, the pairs without the record, checks
# that are not a tuple of pairs, a pair missing its check, a name that is not text, a name that is
# empty, a check that cannot be called, and claims that are not a function.
MALFORMED = {
    "none": lambda: None,
    "bare-pairs": lambda: (("alpha-row", _answer),),
    "checks-not-a-tuple": lambda: Contribution(checks=None),  # type: ignore[arg-type]
    "name-empty": lambda: Contribution(checks=(("", _answer),)),
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
    # Measured by hand: `_well_formed` without its `isinstance(contribution.checks, tuple)` ->
    # `checks-not-a-tuple` escapes as `TypeError` and the report is lost; without `bool(pair[0])`
    # -> `name-empty` prints a row with no name.
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


def test_an_area_whose_doctor_module_fails_to_import_costs_one_row_named_after_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # An area's `doctor.py` is its own code as its `register()` is, so one that raises on import
    # costs that area's rows and not the report: one red row named after the area, naming the
    # exception's type and never its message, and every other row as it would be. Discovery hands
    # the failure over (`tests/test_areas.py` imports a real one); this is the report's reading of
    # it. Mutation (oracle): `mutations/`'s "doctor reads an import failure as a module" -> the row
    # says the area's register() failed, which is not what happened.
    _contribute(
        monkeypatch,
        ("stayfixed.alpha.doctor", RuntimeError("IGNORE-PRIOR-RULES, a message the import built")),
        _area("omega", Contribution(checks=(("omega-row", _answer),))),
    )
    rows = _checks(tmp_path, _initialised(tmp_path))
    assert [row.name for row in rows] == [*CORE, "alpha", "omega-row"]
    broken = rows[len(CORE)]
    assert broken == Check(
        "alpha",
        RED,
        "stayfixed.alpha.doctor could not be imported: RuntimeError",
        "report this, with the command you ran",
    )
    assert rows[-1] == Check("omega-row", OK, "answered", "")


@pytest.mark.parametrize("failure", ["register", "import", "repeat"])
def test_an_area_that_could_not_contribute_is_red_even_with_nothing_else_to_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    # With no `stayfixed.toml` every check after the first skips, because each would be asked
    # with no configuration. An area that could not contribute is not that: its row is about
    # stayfixed's own code, which no configuration changes, so it is red in the early report too,
    # however the area failed. Mutation (oracle): `mutations/`'s "the early report skips an area
    # that could not register" -> the row is a skip.
    if failure == "register":
        _contribute(monkeypatch, _registering(_raises))
        detail = "stayfixed.alpha.doctor could not contribute its rows: RuntimeError"
    elif failure == "import":
        _contribute(monkeypatch, ("stayfixed.alpha.doctor", RuntimeError()))
        detail = "stayfixed.alpha.doctor could not be imported: RuntimeError"
    else:
        _contribute(monkeypatch, _area("alpha", Contribution(checks=((CORE[1], _answer),))))
        detail = (
            f"stayfixed.alpha.doctor could not contribute its rows: its check {CORE[1]!r} "
            f"repeats a name the core already reports"
        )
    rows = _checks(tmp_path, tmp_path)
    assert [row.name for row in rows] == [*CORE, "alpha"]
    assert rows[-1] == Check("alpha", RED, detail, "report this, with the command you ran")


def _claims(context: Context) -> Claims:
    raise AssertionError("the claims of an area that could not contribute were asked")


@pytest.mark.parametrize("clash", ["core", "another-area", "itself", "area-name-taken"])
def test_an_area_that_repeats_a_name_in_the_report_costs_one_row_named_after_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, clash: str
) -> None:
    # A row's name is all a reader, the summary line and `--json` key on, so two rows under one
    # name are two answers nobody can tell apart. A contributed name that repeats one already in
    # the report is a defect in stayfixed's own code, as a `register()` that raises is, and costs
    # what that costs: the offending area's rows and its claims become one red row named after
    # it, and the rest of the report stands. It used to raise out of `run_checks`, and the CLI
    # turned that into an internal error with no report at all. The row's name is itself a name
    # in the report, so when the area's name is taken it is numbered, never repeated. Mutations
    # (oracle): `mutations/`'s "doctor lets an area repeat a name the report already has" -> the
    # `core` and `another-area` cases print two rows under one name; "doctor lets an area name
    # two of its checks alike" -> `itself` does; "an area's failure row takes a name the report
    # already has" -> `area-name-taken` prints two rows named `omega`.
    if clash == "core":
        repeated, owner = CORE[1], "the core"
        omega = Contribution(checks=((CORE[1], _answer),), claims=_claims)
        alpha = Contribution(checks=(("alpha-row", _answer),))
    elif clash == "another-area":
        repeated, owner = "alpha-row", "stayfixed.alpha.doctor"
        omega = Contribution(
            checks=(("omega-row", _answer), ("alpha-row", _answer)), claims=_claims
        )
        alpha = Contribution(checks=(("alpha-row", _answer),))
    elif clash == "itself":
        repeated, owner = "omega-row", "it"
        omega = Contribution(
            checks=(("omega-row", _answer), ("omega-row", _answer)), claims=_claims
        )
        alpha = Contribution(checks=(("alpha-row", _answer),))
    else:
        # `alpha` contributes the names `omega`'s row would take first and second, so the row
        # is numbered past both.
        repeated, owner = CORE[1], "the core"
        omega = Contribution(checks=((CORE[1], _answer),), claims=_claims)
        alpha = Contribution(checks=(("omega", _answer), ("omega (2)", _answer)))
    _contribute(monkeypatch, _area("alpha", alpha), _area("omega", omega))
    rows = _checks(tmp_path, _initialised(tmp_path))
    alphas = [name for name, _ in alpha.checks]
    failed = "omega (3)" if clash == "area-name-taken" else "omega"
    assert [row.name for row in rows] == [*CORE, *alphas, failed]
    assert [each.status for each in rows[len(CORE) : -1]] == [OK] * len(alphas)
    assert rows[-1] == Check(
        failed,
        RED,
        f"stayfixed.omega.doctor could not contribute its rows: its check {repeated!r} repeats "
        f"a name {owner} already reports",
        "report this, with the command you ran",
    )
    assert [each.claims for each in registry.contributions(checks.CHECKS)] == [None, None]


def test_a_later_area_never_takes_the_name_of_an_earlier_areas_failure_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The red row an area that could not contribute gets is a name in the report like any other, so
    # a later area that contributes a check under that name repeats it. Recorded only in the row
    # and not among the names the report already has, the later area's check joined, and the
    # report printed two rows named `alpha`: one red, one green, which nothing keyed on the name
    # can tell apart. Mutation (oracle): `mutations/`'s "an area's failure row is not counted among
    # the report's names" -> two rows named `alpha`.
    _contribute(
        monkeypatch,
        _registering(_raises),
        _area("omega", Contribution(checks=(("alpha", _answer),), claims=_claims)),
    )
    rows = _checks(tmp_path, _initialised(tmp_path))
    assert [row.name for row in rows] == [*CORE, "alpha", "omega"]
    assert rows[-1] == Check(
        "omega",
        RED,
        "stayfixed.omega.doctor could not contribute its rows: its check 'alpha' repeats a name "
        "stayfixed.alpha.doctor already reports",
        "report this, with the command you ran",
    )


def test_an_area_turned_away_for_a_repeated_name_leaves_its_other_names_free(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # An area whose second check repeats a core name contributes none of its rows, so its first
    # name is not in the report, and a later area may use it. Asking whether the area repeats a
    # name must not write the area's names among the report's: written there, the turned-away
    # area's first name was taken by nobody's row, and the later area was turned away too, for
    # repeating a name "it" already reports. Mutation (oracle): `mutations/`'s "asking whether an
    # area repeats a name records its names in the report" -> omega's row is red.
    _contribute(
        monkeypatch,
        _area("alpha", Contribution(checks=(("shared", _answer), (CORE[1], _answer)))),
        _area("omega", Contribution(checks=(("shared", _answer),))),
    )
    rows = _checks(tmp_path, _initialised(tmp_path))
    assert [row.name for row in rows] == [*CORE, "alpha", "shared"]
    assert rows[-1] == Check("shared", OK, "answered", "")


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


def _wording(area: str) -> Wording:
    """A fake area's own words for its record, its source and the commands that repair them.

    None of them is `attach`'s, so a sentence that reaches for `attach`'s ledger or commands
    instead of the claimant's own words reads wrong here, which is what `_speaks_no_attach`
    asks."""
    return Wording(
        record=f".{area}/record.json",
        unreadable=(
            f"cannot be read as {area}'s record, so which of those entries {area} wrote could "
            f"not be established"
        ),
        inspect=f"check that .{area}/record.json is readable",
        source=f"{area}'s source",
        unsourced=f"this machine records no {area} source",
        unaskable=f"{area}'s source could not be asked which entries it grants",
        diagnose=f"run `{area} diagnose`",
        setup=f"run `{area} setup` to record {area}'s source",
        vouch=f"`{area} vouch`",
    )


ALPHA_WORDING = _wording("alpha")
OMEGA_WORDING = _wording("omega")
WORDING = {"alpha": ALPHA_WORDING, "omega": OMEGA_WORDING}

# What `attach` names in this row, none of which a fake area says: the core used to print these
# whoever the claimant was, and with no claimant at all.
ATTACH_WORDS = (".stayfixed/local/attach.json", "stayfixed attach", "stayfixed setup", "overlay")


def _speaks_no_attach(row: Check) -> None:
    for word in ATTACH_WORDS:
        assert word not in row.detail + row.remedy, (word, row)


def _hooked(root: Path, *commands: str) -> None:
    """`root`'s `SETTINGS`, holding one `PreToolUse` hook entry per command, in order."""
    assert SETTINGS in SETTINGS_FILES, "the walk would never open this file"
    entries = [{"type": "command", "command": command} for command in commands]
    (root / SETTINGS).parent.mkdir(parents=True, exist_ok=True)
    (root / SETTINGS).write_text(
        json.dumps({"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": entries}]}}),
        encoding="utf-8",
    )


def _claiming(
    recorded: Mapping[str, str] | None,
    granted: frozenset[str] | None,
    *,
    sourced: bool = True,
    wording: Wording = ALPHA_WORDING,
) -> Contribution:
    """An area that contributes no row and answers `Claims(recorded, granted, sourced)`, in
    `wording`, when asked."""
    return Contribution(
        checks=(),
        claims=lambda context: Claims(recorded, granted, sourced, wording=wording),
    )


ALPHA_CLAIMS = _claiming({"alpha-1": "PreToolUse"}, frozenset({ALPHA}))
OMEGA_CLAIMS = _claiming({"omega-1": "PreToolUse"}, frozenset({OMEGA}), wording=OMEGA_WORDING)


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
        _area("omega", _claiming({}, frozenset({ALPHA}), wording=OMEGA_WORDING)),
    )
    assert row.status == RED, row
    assert (
        f"1 entr(ies) claim the stayfixed marker and are recorded in .alpha/record.json, and "
        f"alpha's source does not grant them: {SETTINGS} entry 1 of 1"
    ) in row.detail
    _speaks_no_attach(row)


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
        f"1 entr(ies) claim the stayfixed marker and are recorded in .alpha/record.json, and "
        f"alpha's source does not grant them: {SETTINGS} entry 2 of 2"
    ) in row.detail
    _speaks_no_attach(row)


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
    assert "alpha's source does not grant" in row.detail
    assert f"{SETTINGS} entry 1 of 1" in row.detail


# Alpha's words for a checkout its source does not grant what it grants the one it is for, where
# "alpha's source does not grant them" would be false and `alpha vouch` refused.
NARROWED_WORDING = replace(
    ALPHA_WORDING,
    ungranted="alpha's source grants this checkout less than the one it is for",
    regrant="settle the checkout with `alpha rebind`",
)
# The row for one entry alpha's source left red, by whether alpha's record could be read: the
# sentence and remedy are alpha's own clause and remedy, in each of the two arms that tell it.
NARROWED_ROWS = {
    "readable": Check(
        "hook-entries",
        RED,
        f"1 stayfixed entr(ies), 0 foreign; 1 entr(ies) claim the stayfixed marker and are "
        f"recorded in .alpha/record.json, and alpha's source grants this checkout less than the "
        f"one it is for: {SETTINGS} entry 1 of 1",
        "settle the checkout with `alpha rebind`",
    ),
    "unreadable": Check(
        "hook-entries",
        RED,
        f"1 stayfixed entr(ies), 0 foreign; .alpha/record.json is there and cannot be read as "
        f"alpha's record, so which of those entries alpha wrote could not be established; 1 "
        f"entr(ies) claim the stayfixed marker and alpha's source grants this checkout less than "
        f"the one it is for, so whatever .alpha/record.json records, nothing on this machine "
        f"vouches for them: {SETTINGS} entry 1 of 1",
        "open each entry named above and remove the ones you did not install; then settle the "
        "checkout with `alpha rebind`",
    ),
}


@pytest.mark.parametrize("record", sorted(NARROWED_ROWS))
def test_an_area_that_says_why_its_source_grants_less_is_told_in_its_words(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, record: str
) -> None:
    # An area whose source answered and does not grant *this checkout* what it grants the one it
    # is for — `attach`'s overlay, for a checkout its record binds to another remote — knows that
    # "its source does not grant them" is false and its `vouch` may be refused. Its `ungranted`
    # and `regrant` stand in for both, the verdict unchanged, beside a readable record and an
    # unreadable one. Mutations (oracle): `mutations/`'s "hook-entries says a source refused what
    # its area says it grants elsewhere" -> the old clause; "hook-entries offers the vouch an area
    # says may be refused" and "hook-entries offers the rebuild an area says may be refused,
    # beside an unreadable record" -> the old remedies.
    _hooked(_initialised(tmp_path), ALPHA)
    recorded = {"alpha-1": "PreToolUse"} if record == "readable" else None
    row = _hook_entries(
        tmp_path,
        monkeypatch,
        _area("alpha", _claiming(recorded, frozenset(), wording=NARROWED_WORDING)),
    )
    assert row == NARROWED_ROWS[record]


# How the row tells an owner to get an unreadable record back, in each fake area's words.
REBUILD = {
    "alpha": "remove .alpha/record.json and run `alpha vouch` to write a new one",
    "omega": "remove .omega/record.json and run `omega vouch` to write a new one",
}


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
    # the row withholds what that answer decides and says which answer is missing — in the words
    # of the area whose answer it is, never the other's. The probe is the entry that answer would
    # make red: `NOBODYS`, which no readable record holds and the area whose record is unreadable
    # grants, for a record; and `STRAY`, which alpha records and does not grant, for a grant.
    # Mutations (oracle): `mutations/`'s "a later area's record overwrites one an earlier area
    # could not read" and "a later area's grants overwrite an overlay an earlier area could not
    # ask" -> the `-first` cases compute the column and are red; "hook-entries judges provenance
    # against an overlay that could not be asked" -> the `granted` cases are; "hook-entries names
    # the first area's record wherever a record could not be read" -> `recorded-last` names
    # alpha's record.
    probe = NOBODYS if unknown == "recorded" else STRAY
    _hooked(_initialised(tmp_path), ALPHA, probe)
    missing, known = ("alpha", "omega") if where == "first" else ("omega", "alpha")

    def claims(area: str) -> Contribution:
        wording = WORDING[area]
        if area == known:
            return _claiming({"alpha-1": "PreToolUse"}, frozenset({ALPHA}), wording=wording)
        if unknown == "recorded":
            return _claiming(None, frozenset({ALPHA, NOBODYS}), wording=wording)
        return _claiming({"alpha-1": "PreToolUse"}, None, wording=wording)

    row = _hook_entries(
        tmp_path, monkeypatch, _area("alpha", claims("alpha")), _area("omega", claims("omega"))
    )
    assert row.status == WARN, row
    assert "all accounted for" not in row.detail
    assert "are not recorded in" not in row.detail
    assert "does not grant" not in row.detail
    if unknown == "recorded":
        assert row.detail == (
            f"2 stayfixed entr(ies), 0 foreign; .{missing}/record.json is there and cannot be "
            f"read as {missing}'s record, so which of those entries {missing} wrote could not be "
            f"established"
        )
        assert row.remedy == REBUILD[missing]
    else:
        assert row.detail == (
            f"2 stayfixed entr(ies), 0 foreign; {missing}'s source could not be asked which "
            f"entries it grants, so nothing here vouches for the ones claiming the marker"
        )
        assert row.remedy == f"run `{missing} diagnose`"
    _speaks_no_attach(row)


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
    assert row == Check(
        "hook-entries",
        RED,
        "2 stayfixed entr(ies), 0 foreign; alpha's source could not be asked which entries it "
        "grants, so nothing here vouches for the ones claiming the marker; 1 entr(ies) claim the "
        f"stayfixed marker and are not recorded in .alpha/record.json: {SETTINGS} entry 2 of 2",
        "open each entry named above and remove the ones you did not install",
    )
    _speaks_no_attach(row)


UNREADABLE = {
    area: (
        f".{area}/record.json is there and cannot be read as {area}'s record, so which of those "
        f"entries {area} wrote could not be established"
    )
    for area in ("alpha", "omega")
}


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
            "alpha's source does not grant them",
            f"{SETTINGS} entry 2 of 2",
            "open each entry named above and remove the ones you did not install; then "
            f"{REBUILD['alpha']}",
        )
    else:
        why, where, remedy = (
            "this machine records no alpha source",
            f"{SETTINGS} entry 1 of 2, {SETTINGS} entry 2 of 2",
            "open each entry named above and remove the ones you did not install; if you did "
            f"install them, run `alpha setup` to record alpha's source; then {REBUILD['alpha']}",
        )
    count = 1 if sourced else 2
    assert row == Check(
        "hook-entries",
        RED,
        f"2 stayfixed entr(ies), 0 foreign; {UNREADABLE['alpha']}; {count} entr(ies) claim the "
        f"stayfixed marker and {why}, so whatever .alpha/record.json records, nothing on this "
        f"machine vouches for them: {where}",
        remedy,
    )
    _speaks_no_attach(row)


# What the row says of an entry a record holds where nothing could grant it, and how it ends.
UNSOURCED = (
    "1 entr(ies) claim the stayfixed marker and are recorded in .alpha/record.json, and this "
    "machine records no alpha source, so nothing on this machine vouches for them: "
    f"{SETTINGS} entry 1 of 1"
)
RECORD_A_SOURCE = (
    "open each entry named above and remove the ones you did not install; if you did install "
    "them, run `alpha setup` to record alpha's source, then `alpha vouch`"
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
    _speaks_no_attach(row)


@pytest.mark.parametrize("record", ["readable", "unreadable"])
def test_a_file_this_walk_cannot_read_keeps_an_unvouched_entry_red(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, record: str
) -> None:
    # A settings file the walk is blind to downgrades a row with nothing else to say to a warning,
    # and must not downgrade one that has a red entry to report, whether or not the record that
    # might hold it could be read; nor may its remedy displace the red entry's. Mutations (oracle):
    # `mutations/`'s "a blind settings file softens a red row" -> both cases are a warning; "a
    # blind settings file's remedy displaces a red entry's" -> both are told to check the file.
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
        assert "this machine records no alpha source, so whatever" in row.detail
        assert row.remedy.endswith(REBUILD["alpha"])
    assert "could not be read as hook entries, so nothing here accounts for what is in them: " in (
        row.detail
    )


def test_with_no_area_claiming_anything_an_entry_claiming_the_marker_is_recorded_nowhere(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # With no area claiming anything nothing records any entry, and the row says so in its own
    # words: it used to name `attach`'s ledger as the record the entry is missing from, a file
    # no claimant had named and a reader would go looking for. Mutation (oracle): `mutations/`'s
    # "hook-entries names a record where no area claims one" -> the sentence ends "not recorded
    # in" and nothing.
    _hooked(_initialised(tmp_path), NOBODYS)
    row = _hook_entries(tmp_path, monkeypatch)
    assert row == Check(
        "hook-entries",
        RED,
        "1 stayfixed entr(ies), 0 foreign; 1 entr(ies) claim the stayfixed marker and are "
        f"recorded nowhere: {SETTINGS} entry 1 of 1",
        "open each entry named above and remove the ones you did not install",
    )
    _speaks_no_attach(row)


def test_an_entry_no_record_holds_names_every_record_it_is_missing_from(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Every claimant's record was read and none holds the entry, so the row names each of them:
    # naming one sent a reader to that record alone, as if the other could not have held it.
    # Mutation (oracle): `mutations/`'s "hook-entries names only the first area's record of an
    # entry no record holds" -> omega's record is missing from the sentence.
    _hooked(_initialised(tmp_path), ALPHA, OMEGA, NOBODYS)
    row = _hook_entries(
        tmp_path, monkeypatch, _area("alpha", ALPHA_CLAIMS), _area("omega", OMEGA_CLAIMS)
    )
    assert row == Check(
        "hook-entries",
        RED,
        "3 stayfixed entr(ies), 0 foreign; 1 entr(ies) claim the stayfixed marker and are not "
        f"recorded in .alpha/record.json or .omega/record.json: {SETTINGS} entry 3 of 3",
        "open each entry named above and remove the ones you did not install",
    )
    _speaks_no_attach(row)


@pytest.mark.parametrize("which", ["second", "both"])
def test_an_unreadable_record_is_named_in_its_own_areas_words(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, which: str
) -> None:
    # Each unreadable record is its own area's to name and to repair: the second area's record
    # unreadable is reported as the second's, never as the first's, and with both unreadable each
    # gets its part and its remedy — rebuilt from its source where that source can be asked, looked
    # at where it cannot. The core used to name `attach`'s ledger whichever record it was.
    # Mutation (oracle): `mutations/`'s "hook-entries names the first area's record wherever a
    # record could not be read" -> `second` names alpha's record.
    _hooked(_initialised(tmp_path), ALPHA, OMEGA)
    if which == "second":
        alpha = ALPHA_CLAIMS
        detail, remedy = UNREADABLE["omega"], REBUILD["omega"]
    else:
        alpha = _claiming(None, frozenset({ALPHA}))
        detail = f"{UNREADABLE['alpha']}; {UNREADABLE['omega']}"
        remedy = f"{REBUILD['alpha']}; check that .omega/record.json is readable"
    omega = _claiming(
        None, frozenset({OMEGA}) if which == "second" else None, wording=OMEGA_WORDING
    )
    row = _hook_entries(tmp_path, monkeypatch, _area("alpha", alpha), _area("omega", omega))
    assert row == Check("hook-entries", WARN, f"2 stayfixed entr(ies), 0 foreign; {detail}", remedy)
    _speaks_no_attach(row)


def test_two_unaskable_sources_each_get_their_own_part_and_remedy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Two areas whose sources could not be asked are two things to diagnose, each in its own
    # area's words, in area order; one sentence naming one source sent a reader to the wrong one.
    # Mutation (oracle): `mutations/`'s "hook-entries names only the first source that could not
    # be asked" -> omega's part and `omega diagnose` are missing.
    _hooked(_initialised(tmp_path), ALPHA, OMEGA)
    row = _hook_entries(
        tmp_path,
        monkeypatch,
        _area("alpha", _claiming({"alpha-1": "PreToolUse"}, None)),
        _area("omega", _claiming({"omega-1": "PreToolUse"}, None, wording=OMEGA_WORDING)),
    )
    assert row == Check(
        "hook-entries",
        WARN,
        "2 stayfixed entr(ies), 0 foreign; alpha's source could not be asked which entries it "
        "grants, so nothing here vouches for the ones claiming the marker; omega's source could "
        "not be asked which entries it grants, so nothing here vouches for the ones claiming the "
        "marker",
        "run `alpha diagnose`; run `omega diagnose`",
    )


@pytest.mark.parametrize("unreadable", ["alpha", "omega"])
def test_an_unreadable_record_beside_another_areas_unaskable_source_tells_both(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, unreadable: str
) -> None:
    # One area's record cannot be read and the other's source cannot be asked: two things the row
    # withholds judgement for, each its own area's to repair, so each gets its part and its remedy,
    # whichever area comes first. The row used to tell the unaskable source only where no record
    # was unreadable, so the second fact and its remedy were dropped: nothing said why the other
    # area's entries were never compared against a grant.
    _hooked(_initialised(tmp_path), ALPHA, OMEGA)
    unasked = "omega" if unreadable == "alpha" else "alpha"
    own = {"alpha": ({"alpha-1": "PreToolUse"}, ALPHA), "omega": ({"omega-1": "PreToolUse"}, OMEGA)}

    def claims(area: str) -> Contribution:
        recorded, command = own[area]
        if area == unreadable:
            return _claiming(None, frozenset({command}), wording=WORDING[area])
        return _claiming(recorded, None, wording=WORDING[area])

    row = _hook_entries(
        tmp_path, monkeypatch, _area("alpha", claims("alpha")), _area("omega", claims("omega"))
    )
    assert row == Check(
        "hook-entries",
        WARN,
        f"2 stayfixed entr(ies), 0 foreign; {UNREADABLE[unreadable]}; {unasked}'s source could "
        f"not be asked which entries it grants, so nothing here vouches for the ones claiming the "
        f"marker",
        f"{REBUILD[unreadable]}; run `{unasked} diagnose`",
    )
    _speaks_no_attach(row)


@pytest.mark.parametrize("sourced", [True, False], ids=["sourced", "unsourced"])
def test_two_areas_red_entries_of_one_kind_each_get_their_own_remedy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, sourced: bool
) -> None:
    # Each area's red entries are told in its own part, and the way out of them is that area's
    # command, so the remedy carries every area's, joined as the warnings' are. The row used to
    # keep only the last area's remedy for a red part, so the first area's entries were named with
    # no way out of them: `alpha vouch` never reached the reader of alpha's entry.
    _hooked(_initialised(tmp_path), ALPHA, OMEGA)
    row = _hook_entries(
        tmp_path,
        monkeypatch,
        _area("alpha", _claiming({"alpha-1": "PreToolUse"}, frozenset(), sourced=sourced)),
        _area(
            "omega",
            _claiming(
                {"omega-1": "PreToolUse"}, frozenset(), sourced=sourced, wording=OMEGA_WORDING
            ),
        ),
    )
    if sourced:
        parts = [
            f"1 entr(ies) claim the stayfixed marker and are recorded in .{area}/record.json, and "
            f"{area}'s source does not grant them: {SETTINGS} entry {n} of 2"
            for n, area in enumerate(("alpha", "omega"), start=1)
        ]
        remedies = [
            f"run `{area} vouch`, which takes out every marked entry {area}'s source no longer "
            f"grants; open any that survive it"
            for area in ("alpha", "omega")
        ]
    else:
        parts = [
            f"1 entr(ies) claim the stayfixed marker and are recorded in .{area}/record.json, and "
            f"this machine records no {area} source, so nothing on this machine vouches for them: "
            f"{SETTINGS} entry {n} of 2"
            for n, area in enumerate(("alpha", "omega"), start=1)
        ]
        remedies = [
            "open each entry named above and remove the ones you did not install; if you did "
            f"install them, run `{area} setup` to record {area}'s source, then `{area} vouch`"
            for area in ("alpha", "omega")
        ]
    assert row == Check(
        "hook-entries",
        RED,
        "; ".join(["2 stayfixed entr(ies), 0 foreign", *parts]),
        "; ".join(remedies),
    )
    _speaks_no_attach(row)


@pytest.mark.parametrize("omega", ["sourced", "unsourced"])
def test_each_red_entry_is_told_in_the_words_of_the_area_that_holds_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, omega: str
) -> None:
    # An entry a record holds and nothing vouches for is told in the holding area's words: its
    # record, its source, and the command that rewrites its entries. `STRAY` is alpha's and
    # `OMEGA` is omega's, so each gets a part of its own, kinds in the row's order and areas in
    # area order, and the remedy is every part's of the row's highest step: both areas' where
    # both refused, alpha's alone where omega's entry is of a lower step. Told in one area's words,
    # the other's entry sent a reader to a record that does not hold it and a command that does not
    # touch it.
    # The first area holds neither, so "the first area" and "the area that holds it" differ for
    # both entries. Mutations (oracle): `mutations/`'s "hook-entries tells a refused grant in the
    # first area's words" -> both cases tell an entry in nobody's words; "hook-entries tells an
    # unvouched entry in the first area's words" -> `unsourced` tells `OMEGA` in nobody's.
    _hooked(_initialised(tmp_path), STRAY, OMEGA)
    sourced = omega == "sourced"
    row = _hook_entries(
        tmp_path,
        monkeypatch,
        _area("nobody", _claiming({}, frozenset(), wording=_wording("nobody"))),
        _area("alpha", ALPHA_CLAIMS),
        _area(
            "omega",
            _claiming(
                {"omega-1": "PreToolUse"}, frozenset(), sourced=sourced, wording=OMEGA_WORDING
            ),
        ),
    )
    alpha_part = (
        "1 entr(ies) claim the stayfixed marker and are recorded in .alpha/record.json, and "
        f"alpha's source does not grant them: {SETTINGS} entry 1 of 2"
    )
    alpha_remedy = (
        "run `alpha vouch`, which takes out every marked entry alpha's source no longer grants; "
        "open any that survive it"
    )
    if sourced:
        omega_part = (
            "1 entr(ies) claim the stayfixed marker and are recorded in .omega/record.json, and "
            f"omega's source does not grant them: {SETTINGS} entry 2 of 2"
        )
        parts, remedy = (
            [alpha_part, omega_part],
            (
                f"{alpha_remedy}; run `omega vouch`, which takes out every marked entry omega's "
                "source no longer grants; open any that survive it"
            ),
        )
    else:
        omega_part = (
            "1 entr(ies) claim the stayfixed marker and are recorded in .omega/record.json, and "
            "this machine records no omega source, so nothing on this machine vouches for them: "
            f"{SETTINGS} entry 2 of 2"
        )
        parts, remedy = [omega_part, alpha_part], alpha_remedy
    assert row == Check(
        "hook-entries", RED, "; ".join(["2 stayfixed entr(ies), 0 foreign", *parts]), remedy
    )
    _speaks_no_attach(row)


def test_an_entry_only_an_unreadable_record_could_hold_is_told_in_a_sourced_areas_words(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Both records are unreadable, alpha's machine records no source and omega's does, and no
    # grant covers `NOBODYS`: red, told as omega's refusal, because omega's is the source that was
    # asked and did not grant it. Told in the first unreadable area's words, it read as alpha's
    # missing source, whose remedy records a source this entry's verdict never depended on.
    # Mutation (oracle): `mutations/`'s "hook-entries tells an entry beside unreadable records in
    # the first one's words" -> the part names alpha's record and alpha's missing source.
    _hooked(_initialised(tmp_path), OMEGA, NOBODYS)
    row = _hook_entries(
        tmp_path,
        monkeypatch,
        _area("alpha", _claiming(None, frozenset(), sourced=False)),
        _area("omega", _claiming(None, frozenset({OMEGA}), wording=OMEGA_WORDING)),
    )
    assert row == Check(
        "hook-entries",
        RED,
        f"2 stayfixed entr(ies), 0 foreign; {UNREADABLE['alpha']}; {UNREADABLE['omega']}; "
        "1 entr(ies) claim the stayfixed marker and omega's source does not grant them, so "
        "whatever .omega/record.json records, nothing on this machine vouches for them: "
        f"{SETTINGS} entry 2 of 2",
        "open each entry named above and remove the ones you did not install; then "
        f"{REBUILD['omega']}",
    )
    _speaks_no_attach(row)


def test_claims_that_raise_cost_the_hook_entries_row_alone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # `hook-entries` asks the claims itself, under its own guard, so an area whose `claims`
    # raises costs that one row, red and naming `UnansweredClaims`, the type the row raises it on
    # as, and never its message; the area's own rows and every other row read as they do when the
    # area claims nothing. Mutation (oracle): `mutations/`'s "doctor asks its checks without the
    # guard" -> `UnansweredClaims` escapes `run_checks`.
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
        "this check could not run: UnansweredClaims",
        "report this, with the command you ran",
    )
    assert "IGNORE" not in broken.detail + broken.remedy
    assert [row for row in rows if row.name != "hook-entries"] == [
        row for row in quiet if row.name != "hook-entries"
    ]


def test_claims_that_raise_an_os_error_are_red_and_never_a_warning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # `Contribution.claims` promises red for an answer that raises, and the guard every check goes
    # through reads an `OSError` as the machine's and warns: claims that raised `PermissionError`
    # turned this row, and with it every forged entry it would have listed, into a warning and an
    # exit of 0. The row names the type it raises them on as, never their message. The exit code
    # is `tests/doctor/test_command.py`'s. Mutation (oracle): `mutations/`'s "claims that raise an
    # OSError reach the guard as one" -> the row is a warning.
    def raises(context: Context) -> Claims:
        raise PermissionError("IGNORE-PRIOR-RULES, a message the claims built")

    _hooked(_initialised(tmp_path), ALPHA)
    row = _hook_entries(
        tmp_path, monkeypatch, _area("alpha", Contribution(checks=(), claims=raises))
    )
    assert row == Check(
        "hook-entries",
        RED,
        "this check could not run: UnansweredClaims",
        "report this, with the command you ran",
    )
    assert "IGNORE" not in row.detail + row.remedy
