"""The `doctor` command: one line, the right exit code, and a remedy the skill can relay.

The report itself is `tests/doctor/test_checks.py`'s. What is untested until this file is the
argparse wiring, the two exit codes — 0 for a report with no red row, and 1, the findings exit
code, for one with any — and the one property of the output that decides whether the skill is
any use: a remedy missing from `--json` is a remedy the user never sees.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from types import ModuleType

import pytest

from stayfixed.cli import build_parser, discover_registrars, run
from stayfixed.doctor import checks
from stayfixed.doctor.api import OK, RED, SKIP, WARN, Check, Claims, Context, Contribution
from stayfixed.doctor.commands import summarise
from stayfixed.findings import LISTED_LIMIT
from tests.doctor.test_checks import _initialised
from tests.floor import is_developers
from tests.test_areas import UNIMPORTABLE, plant_area


@pytest.fixture(autouse=True)
def _nothing_of_the_developers_own(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The seam `tests/doctor/test_checks.py` closes with `_env`, closed here instead.

    `run_doctor` passes no `env=`, so `run_checks` falls back to `os.environ` — and that is the
    real environment, which no test in this suite may read: `ignored-env` reports whichever of
    two real variables is set, `diagnostics` finds the harness data root in it and this suite is
    plausibly run inside a session where that points at a real log, and
    `load(root, machine=None)` resolves the developer's own `~/.config/stayfixed/config.toml`.
    The flag cases below cannot pass an environment through argparse, so the environment is made
    hermetic instead of passed.

    `_own_root` is stood down for the same reason and one more: `plugin_root` would otherwise
    answer with this checkout, and the `wrapper` check **executes** what it answers. Every case
    here would then spawn a real `hooks/run-hook.sh`, and `test_a_clean_installation_exits_zero`
    would become false the day that run goes red on somebody's machine — which is a fact about
    their interpreters, not about the argparse wiring this file is for. What the two checks do
    with a plugin root is `tests/doctor/test_checks.py`'s.
    """
    # `is_developers` keeps the suite's floor under the product's `git` bounds, which is the test
    # runner's rather than the developer's: `doctor` runs its `git` in this process, and without
    # the floor a loaded machine could run a five-second `rev-parse` out.
    for name in list(os.environ):
        if is_developers(name):
            monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setattr(checks, "_own_root", lambda: None)


def invoke(argv: list[str]) -> int:
    return run(argv, parser=build_parser(discover_registrars()))


def test_the_command_is_discovered() -> None:
    assert "doctor" in build_parser(discover_registrars()).format_help()


def test_a_clean_installation_exits_zero_with_one_line(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # Every command prints a one-line result. Sixteen rows on stdout would make `doctor`
    # the one command a caller has to parse rather than read, and `--json` is where the rows are.
    root = _initialised(tmp_path)
    code = invoke(["doctor", "--root", str(root), "--home", str(tmp_path / "home")])
    out = capsys.readouterr().out
    assert code == 0
    assert len(out.strip().splitlines()) == 1


def test_the_runner_this_command_builds_is_bounded_for_a_diagnostic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The one call this area makes that leaves the machine is bounded, and here is where it is.

    `runner.NETWORK_TIMEOUT_SECONDS` is five minutes, written for `gh repo create --clone` and
    the clone behind it. `doctor` inherited it for the `ci-ref` row's single `git ls-remote` —
    and `stayfixed init` recording a `[ci] ref` is what made a five-minute block reachable on a
    command whose whole output is one line. The row's own `git` questions go through `gitenv`'s
    five seconds and the wrapper probe through this module's thirty, so the bound here is the
    module's own thirty and `checks.CI_REF_TIMEOUT_SECONDS` carries the argument for it.

    Asserted where the runner is *built*, because that is the only place the choice exists: the
    `Runner` protocol has no timeout and every stub in this suite is bounded at nothing. The
    factory is imported inside `run_doctor`, so patching the module attribute is the seam.

    Mutation (oracle entry "doctor asks the public repository with no bound of its own"):
    `subprocess_runner(timeout=CI_REF_TIMEOUT_SECONDS)` -> `subprocess_runner()` -> this reddens
    on the recorded keyword.
    """
    import stayfixed.runner as runner

    asked: list[float | None] = []
    real = runner.subprocess_runner

    def spy(*, timeout: float | None = None) -> runner.Runner:
        asked.append(timeout)
        return real(timeout=timeout)

    monkeypatch.setattr(runner, "subprocess_runner", spy)
    root = _initialised(tmp_path)
    assert invoke(["doctor", "--root", str(root), "--home", str(tmp_path / "home")]) == 0
    assert asked == [checks.CI_REF_TIMEOUT_SECONDS]
    # And it is narrower than the seam's own default, which is the whole point of asking.
    assert checks.CI_REF_TIMEOUT_SECONDS < runner.NETWORK_TIMEOUT_SECONDS


def test_a_skip_is_not_a_finding(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # One check cannot be answered by this build — the Codex hook-trust hash, which no spike has
    # measured — and `ci-ref` skips on a state this repository is in: it records no `[ci] ref`.
    # (`files` is not among them: the release ships the record it compares against.) If a skip
    # exited 1, `doctor` would be red on every correct installation.
    root = _initialised(tmp_path)
    code = invoke(["doctor", "--root", str(root), "--home", str(tmp_path / "home"), "--json"])
    assert code == 0
    report = json.loads(capsys.readouterr().out)
    assert [check["name"] for check in report["checks"] if check["status"] == "skip"]


def test_any_red_check_exits_one(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # Exit 1 is "findings". A doctor that always exits 0 is a doctor nothing can gate on: a
    # script or a CI step that runs it reads the exit code, since `stayfixed assess` runs no
    # doctor check. A directory with no `stayfixed.toml` is the cheapest red there is, and the
    # report's own first row.
    code = invoke(["doctor", "--root", str(tmp_path), "--home", str(tmp_path / "home")])
    assert code == 1
    assert "not-initialised" in capsys.readouterr().out


def test_claims_that_raise_an_os_error_fail_the_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # An area's claims that raise are red, as `Contribution.claims` promises, and red is what
    # gates the exit code: claims that raised `PermissionError` reached the report's guard as the
    # machine's `OSError`, so `hook-entries` warned and `stayfixed doctor` exited 0 over entries
    # nothing had judged. The one area here is injected through `checks.discover_contributors`,
    # so nothing else in this repository is red. Mutation (oracle): `mutations/`'s "claims that
    # raise an OSError reach the guard as one" -> the row warns and the exit code is 0.
    def raises(context: Context) -> Claims:
        raise PermissionError("IGNORE-PRIOR-RULES, a message the claims built")

    area = ModuleType("stayfixed.alpha.doctor")
    setattr(area, "register", lambda: Contribution(checks=(), claims=raises))  # noqa: B010
    monkeypatch.setattr(checks, "discover_contributors", lambda: [(area.__name__, area)])
    root = _initialised(tmp_path)
    code = invoke(["doctor", "--root", str(root), "--home", str(tmp_path / "home"), "--json"])
    report = json.loads(capsys.readouterr().out)
    red = [check for check in report["checks"] if check["status"] == RED]
    assert red == [
        {
            "name": "hook-entries",
            "status": RED,
            "detail": "this check could not run: UnansweredClaims",
            "remedy": "report this, with the command you ran",
        }
    ]
    assert code == 1


def test_an_area_whose_doctor_module_fails_to_import_costs_one_red_row_and_not_the_report(
    tmp_path: Path,
    request: pytest.FixtureRequest,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # End to end, through a real import: an area whose `doctor.py` raises when imported is one
    # red row named after the area, exit 1 for it, and every other row exactly as a report without
    # the area gives it. Imported unguarded, the exception would leave `run_checks` for the CLI,
    # which turns it into an internal error with no report at all. Mutation (oracle):
    # `mutations/`'s "discovery lets an area's import failure escape" -> the `RuntimeError`
    # escapes and nothing is reported.
    root = _initialised(tmp_path)
    argv = ["doctor", "--root", str(root), "--home", str(tmp_path / "home"), "--json"]
    assert invoke(argv) == 0
    baseline = json.loads(capsys.readouterr().out)["checks"]
    plant_area(request, monkeypatch, tmp_path / "areas", "zzplanted", {"doctor.py": UNIMPORTABLE})
    code = invoke(argv)
    out = capsys.readouterr().out
    assert code == 1
    assert json.loads(out)["checks"] == [
        *baseline,
        {
            "name": "zzplanted",
            "status": "red",
            "detail": "stayfixed.zzplanted.doctor could not be imported: RuntimeError",
            "remedy": "report this, with the command you ran",
        },
    ]
    assert "IGNORE" not in out


def test_the_json_form_carries_every_check_and_its_remedy(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # The skill relays remedies verbatim, so a remedy missing from `--json` is a remedy the
    # user never sees — and the summary line has room for none of them.
    code = invoke(["doctor", "--root", str(tmp_path), "--home", str(tmp_path / "home"), "--json"])
    assert code == 1
    report = json.loads(capsys.readouterr().out)
    assert len(report["checks"]) == 16
    assert all({"name", "status", "detail", "remedy"} <= set(check) for check in report["checks"])
    red = next(check for check in report["checks"] if check["status"] == "red")
    assert red["remedy"]


def test_the_summary_line_is_bounded() -> None:
    # `findings.LISTED_LIMIT` exists because an unbounded summary pushes the repairing command
    # off the end of the line, and sixteen checks is already past eight. Asserted over a
    # synthetic report rather than a fixture, because arranging nine simultaneous real failures
    # would be a test about the fixture.
    checks = [Check(f"check-{n}", RED, "d", "r") for n in range(LISTED_LIMIT + 3)]
    summary = summarise(checks)
    assert len(summary.splitlines()) == 1
    assert "and 3 more" in summary
    assert "check-10" not in summary


def test_the_summary_counts_every_status(tmp_path: Path) -> None:
    # The vacuity guard for the line above: a summary that named only the red rows would pass
    # it while saying nothing about a warning or a skip.
    summary = summarise(
        [
            Check("a", OK, "", ""),
            Check("b", WARN, "", ""),
            Check("c", SKIP, "", ""),
            Check("d", RED, "", ""),
        ]
    )
    assert "1 red" in summary
    assert "1 warn" in summary
    assert "1 skipped" in summary
