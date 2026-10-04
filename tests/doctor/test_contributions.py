"""An area adds rows to `stayfixed doctor` through its own `doctor.py`, discovered by name.

The fake areas below are modules injected through `checks.discover_contributors`, the seam the
discovery reads, the way `tests/test_cli.py` replaces `cli.discover_registrars`: a test that
shipped a real `doctor.py` to prove the convention would be a check in every user's report.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from types import ModuleType

import pytest

from stayfixed.doctor import checks
from stayfixed.doctor.api import OK, RED, SKIP, WARN, Check, Context, Contribution, Row
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
    # and is never asked: it would be asked with no configuration to read. No oracle entry:
    # measured by hand — taking the early report's names from `CHECKS` alone drops the row and
    # this reddens.
    def unreachable(context: Context) -> Row:
        raise AssertionError("asked with no configuration")

    _contribute(monkeypatch, _area("alpha", Contribution(checks=(("alpha-row", unreachable),))))
    rows = _checks(tmp_path, tmp_path)
    assert [row.name for row in rows] == [*CORE, "alpha-row"]
    assert rows[-1].status == SKIP
