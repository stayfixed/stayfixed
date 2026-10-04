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
# for both entries.
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


def _claiming(recorded: Mapping[str, str] | None, granted: frozenset[str] | None) -> Contribution:
    """An area that contributes no row and answers `Claims(recorded, granted)` when asked."""
    return Contribution(checks=(), claims=lambda context: Claims(recorded, granted))


ALPHA_CLAIMS = _claiming({"alpha-1": "PreToolUse"}, frozenset({ALPHA}))
OMEGA_CLAIMS = _claiming({"omega-1": "PreToolUse"}, frozenset({OMEGA}))


def _hook_entries(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *areas: ModuleType) -> Check:
    _contribute(monkeypatch, *areas)
    return next(
        row for row in _checks(tmp_path, tmp_path / "project") if row.name == "hook-entries"
    )


def test_hook_entries_pools_what_every_area_claims(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Each area answers for the entries it put there, so the row reads the union of the answers:
    # alpha's entry is vouched for by alpha's record and grant, omega's by omega's, and an area
    # that contributes a row and no claims takes no part. Mutations (oracle): `mutations/`'s
    # "hook-entries keeps only the last area's recorded ids" and "hook-entries keeps only the
    # last area's granted commands" -> alpha's entry is no longer vouched for and the row is red;
    # "hook-entries ignores what the areas claim" -> neither is.
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
    # names ids no other record knows, an overlay it could not ask grants commands no other grant
    # covers. So the pool is unknown, whichever side of a good answer the `None` falls on, and
    # the row withholds what that answer decides and says which answer is missing. The probe is
    # the entry that answer would make red: `NOBODYS`, which no area records, for a record; and
    # `STRAY`, which alpha records and does not grant, for a grant. Mutations (oracle):
    # `mutations/`'s "a later area's record overwrites one an earlier area could not read" and "a
    # later area's grants overwrite an overlay an earlier area could not ask" -> the `-first`
    # cases compute the column and are red; "hook-entries judges provenance against an overlay
    # that could not be asked" -> the `granted` cases are.
    probe = NOBODYS if unknown == "recorded" else STRAY
    _hooked(_initialised(tmp_path), ALPHA, probe)
    known = _claiming({"alpha-1": "PreToolUse"}, frozenset({ALPHA}))
    if unknown == "recorded":
        missing = _claiming(None, frozenset({ALPHA}))
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
        assert row.remedy == (
            f"check that {ATTACH_LEDGER} is readable and is the file your last attach wrote"
        )
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
