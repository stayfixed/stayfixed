"""Evidence records: one JSON line on the machine per `stayfixed prove` and `stayfixed gate` run,
under the password database's home and never under a repository, and a warning in place of one
that cannot be written, the verdict and the exit code unchanged.

Every test has a `HOME` of its own, and the password database answers it (`tests/conftest.py`), so
a record lands under the test's own directory; a test about the two disagreeing pins the
database's answer with `as_owner_home`.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import re
import subprocess
import sys
import types
from pathlib import Path
from typing import cast

import pytest

import stayfixed
from stayfixed import gitenv, processes
from stayfixed.assess.commands import NO_TREE_CONFIG, ONLY_UNKNOWN, _verdict_words
from stayfixed.assess.report import GateRun
from stayfixed.gitenv import GitUnavailable
from stayfixed.prove import evidence, tree
from stayfixed.prove.evidence import (
    EVIDENCE,
    INSIDE_REPOSITORY,
    NO_HOME,
    NOT_RECORDED,
    STATE_DIR,
    VERSION,
    normalised_origin,
    project_key,
    record_path,
)
from stayfixed.prove.run import INTERRUPTED, TIMED_OUT, Receipt, Verdict
from tests.assess.baserepo import clone, commit
from tests.cli import cli, custom_gate
from tests.gitfixture import git, needs_git
from tests.ownerhome import as_owner_home
from tests.prove.stand_in import NAME
from tests.prove.test_command import prove_cli
from tests.prove.test_junit_flag import REPORT, writer

GATE_BASE = f"""[stayfixed]
version = "{stayfixed.__version__}"
state = "adopting"
enforced = ["docs"]

[project]
name = "widget"
"""
STAMP = re.compile(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ")


def home() -> Path:
    return Path(os.environ["HOME"])


def evidence_dir(under: Path | None = None) -> Path:
    return (under or home()) / STATE_DIR / EVIDENCE


def records(under: Path | None = None) -> list[dict[str, object]]:
    """Every record under `under`'s evidence directory (the test's home by default), file by
    file in name order, line by line."""
    found: list[dict[str, object]] = []
    directory = evidence_dir(under)
    if not directory.is_dir():
        return found
    for path in sorted(directory.iterdir()):
        for line in path.read_text(encoding="utf-8").splitlines():
            found.append(json.loads(line))
    return found


def files(under: Path | None = None) -> list[str]:
    directory = evidence_dir(under)
    return sorted(path.name for path in directory.iterdir()) if directory.is_dir() else []


# --- The key ------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("git@github.com:o/r.git", "ssh://github.com/o/r"),
        ("https://u:t@GitHub.com/o/r/", "ssh://github.com/o/r"),
        ("ssh://git@github.com/o/r", "ssh://github.com/o/r"),
        ("/srv/r.git", "/srv/r"),
        ("HTTP://github.com/o/r.git/", "ssh://github.com/o/r"),
        ("git://github.com/o/r", "ssh://github.com/o/r"),
        ("ssh://git@github.com:22/o/r.git", "ssh://github.com/o/r"),
        ("github.com:o/r", "ssh://github.com/o/r"),
        ("file:///srv/r.git", "/srv/r"),
        ("../r.git", "../r"),
    ],
)
def test_one_repository_one_origin(url: str, expected: str) -> None:
    # Mutation (declared): the origin's userinfo kept -> the https case keys apart.
    assert normalised_origin(url) == expected


@needs_git
def test_a_checkout_with_an_origin_keys_by_it_wherever_it_lies(tmp_path: Path) -> None:
    # Mutation (declared): the origin keyed as spelled, not normalised -> the two clones key apart.
    one, two = tmp_path / "one", tmp_path / "two"
    for checkout, url in ((one, "git@github.com:o/r.git"), (two, "https://github.com/o/r")):
        checkout.mkdir()
        git(checkout, "init", "-q")
        git(checkout, "remote", "add", "origin", url)
    digest = hashlib.sha256(b"ssh://github.com/o/r").hexdigest()[:32]
    assert project_key(one) == project_key(two) == f"origin-{digest}"


@needs_git
def test_no_origin_keys_by_the_real_path(tmp_path: Path) -> None:
    # Mutation (declared): the path key is the directory typed in -> `sub` keys apart. The link
    # half has no mutation of its own: `gitenv.checkout_root`'s walk resolves the top-level and
    # the key takes its `realpath` too, so dropping either alone leaves the key as it was.
    real = tmp_path / "real"
    real.mkdir()
    git(real, "init", "-q")
    linked = tmp_path / "linked"
    linked.symlink_to(real, target_is_directory=True)
    digest = hashlib.sha256(os.fsencode(os.path.realpath(real))).hexdigest()[:32]
    assert project_key(linked) == project_key(real) == f"path-{digest}"
    (real / "sub").mkdir()
    assert project_key(real / "sub") == project_key(real)


def test_a_git_that_cannot_be_asked_keys_by_the_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # `origin_remote` raises where git cannot run at all; the record falls back to the path key
    # rather than fail the run. Mutation (declared): the fault not caught -> the call raises.
    def unavailable(root: Path) -> str | None:
        raise GitUnavailable("git could not be run")

    monkeypatch.setattr(gitenv, "origin_remote", unavailable)
    digest = hashlib.sha256(os.fsencode(os.path.realpath(tmp_path))).hexdigest()[:32]
    assert project_key(tmp_path) == f"path-{digest}"


# --- prove --------------------------------------------------------------------------------------


@needs_git
def test_prove_appends_one_line_per_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Mutation (declared): the record not appended -> no line.
    project = tmp_path / "project"
    project.mkdir()
    git(project, "init", "-q")
    first, out, _ = prove_cli(project, monkeypatch, "--json", "--", NAME)
    second, _, _ = prove_cli(project, monkeypatch, "--", NAME, "--report", "fail", "--code", "1")
    assert (first, second) == (0, 1)
    assert files() == [f"{project_key(project)}.jsonl"]
    kept = records()
    assert [(r["kind"], r["verdict"]) for r in kept] == [("prove", "proved"), ("prove", "failed")]
    receipt = json.loads(out)
    del receipt["summary"]
    head = {"version": VERSION, "kind": "prove", "stayfixed": stayfixed.__version__}
    fields = {field.name for field in dataclasses.fields(Receipt)}
    assert set(kept[0]) == {*head, "at", *fields}
    assert {key: kept[0][key] for key in head} == head
    assert {key: kept[0][key] for key in fields} == receipt
    assert STAMP.fullmatch(str(kept[0]["at"]))


@needs_git
def test_a_run_from_a_subdirectory_keys_the_repository(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = tmp_path / "project"
    (project / "packages" / "web").mkdir(parents=True)
    git(project, "init", "-q")
    prove_cli(project, monkeypatch, "--", NAME)
    prove_cli(project / "packages" / "web", monkeypatch, "--", NAME)
    assert files() == [f"{project_key(project)}.jsonl"]
    assert len(records()) == 2


def test_the_record_lives_under_the_database_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Neither `HOME` nor `XDG_STATE_HOME` moves the record: the password database's home does.
    # Mutation (declared): the home read from `HOME` -> the record lands under the variable's.
    database = tmp_path / "database-home"
    database.mkdir()
    variable = tmp_path / "variable-home"
    variable.mkdir()
    state = tmp_path / "xdg-state"
    as_owner_home(monkeypatch, database)
    monkeypatch.setenv("HOME", str(variable))
    monkeypatch.setenv("XDG_STATE_HOME", str(state))
    project = tmp_path / "project"
    project.mkdir()
    code, _, err = prove_cli(project, monkeypatch, "--", NAME)
    assert (code, err) == (0, "")
    assert len(records(database)) == 1
    assert records(variable) == []
    assert not state.exists()
    assert record_path(project, home=database) == (
        database / STATE_DIR / EVIDENCE / f"{project_key(project)}.jsonl"
    )


@needs_git
@pytest.mark.parametrize("typed_in", ["", "sub"])
def test_no_record_under_the_repository(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, typed_in: str
) -> None:
    # A repository that holds the database's home, a dotfiles checkout at `~`: the record would
    # lie inside it, so none is written, and the warning names the record that was not.
    # Mutation (declared): the record written wherever the home is -> a line inside the checkout.
    git(home(), "init", "-q")
    (home() / "sub").mkdir()
    code, out, err = prove_cli(home() / typed_in, monkeypatch, "--", NAME)
    assert code == 0
    assert out.startswith("proved: ")
    would = home() / STATE_DIR / EVIDENCE / f"{project_key(home())}.jsonl"
    assert record_path(home(), home=home()) is None
    assert err == NOT_RECORDED.format(record=evidence.shown(would), why=INSIDE_REPOSITORY) + "\n"
    assert not evidence_dir().exists()


@needs_git
def test_no_prove_record_inside_a_home_repository_a_nested_project_does_not_answer_for(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The run answers for its own repository, nested in a dotfiles repository at `~`: the record
    # would be an untracked file of the dotfiles repository, so none is written there either.
    # Mutation (declared): the evidence directory's own checkout not asked -> a line inside the
    # dotfiles repository.
    git(home(), "init", "-q")
    project = home() / "code" / "proj"
    project.mkdir(parents=True)
    git(project, "init", "-q")
    code, out, err = prove_cli(project, monkeypatch, "--", NAME)
    assert code == 0
    assert out.startswith("proved: ")
    would = home() / STATE_DIR / EVIDENCE / f"{project_key(project)}.jsonl"
    assert record_path(project, home=home()) is None
    assert err == NOT_RECORDED.format(record=evidence.shown(would), why=INSIDE_REPOSITORY) + "\n"
    assert not evidence_dir().exists()
    status = git(home(), "status", "--porcelain", "--untracked-files=all")
    assert ".local" not in status


@needs_git
def test_a_checkout_at_the_state_directory_is_asked_from_its_nearest_existing_part(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # No repository at the home, one at `~/.local/state`: the nearest part of the evidence
    # directory that exists lies inside a checkout, so no record is written there.
    # Mutation (declared): the checkout asked from the home alone -> a line inside it.
    state = home() / ".local" / "state"
    state.mkdir(parents=True)
    git(state, "init", "-q")
    project = tmp_path / "project"
    project.mkdir()
    code, _, err = prove_cli(project, monkeypatch, "--", NAME)
    assert code == 0
    would = home() / STATE_DIR / EVIDENCE / f"{project_key(project)}.jsonl"
    assert err == NOT_RECORDED.format(record=evidence.shown(would), why=INSIDE_REPOSITORY) + "\n"
    assert not (home() / STATE_DIR).exists()


@needs_git
def test_no_gate_record_inside_a_home_repository_a_nested_project_does_not_answer_for(
    tmp_path: Path,
) -> None:
    # Mutation (declared): the evidence directory's own checkout not asked -> gate's line lands
    # inside the dotfiles repository.
    git(home(), "init", "-q")
    project = clone(home() / "code", GATE_BASE + custom_gate("tests", "pass"))
    code, _, err = cli(project, tmp_path, "gate", "--custom")
    assert code == 0
    would = home() / STATE_DIR / EVIDENCE / f"{project_key(project)}.jsonl"
    assert err == NOT_RECORDED.format(record=evidence.shown(would), why=INSIDE_REPOSITORY) + "\n"
    assert not evidence_dir().exists()


def test_outside_a_repository_the_home_itself_records(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A run typed in the home outside any repository answers for the home, which is no
    # repository, so its record is written. Mutation (declared): a record refused wherever the
    # run's directory holds the home -> none is written.
    code, _, err = prove_cli(home(), monkeypatch, "--", NAME)
    assert (code, err) == (0, "")
    assert len(records()) == 1


@pytest.mark.parametrize(
    ("verdict", "argv", "code"),
    [
        ("proved", [NAME], 0),
        ("failed", [NAME, "--report", "fail", "--code", "1"], 1),
        ("refused", ["FORGE=x", NAME], 2),
    ],
)
def test_an_unwritable_state_directory_warns_and_keeps_the_verdict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, verdict: str, argv: list[str], code: int
) -> None:
    # A file where the state directory's parent should be: no mode bit is involved, so it holds
    # for root too. Mutation (declared): a failed append turning the exit 1 -> the proved run
    # exits 1.
    (home() / ".local").write_text("", encoding="utf-8")
    project = tmp_path / "project"
    project.mkdir()
    got, out, err = prove_cli(project, monkeypatch, "--", *argv)
    assert got == code
    assert out.startswith(f"{verdict}: ")
    would = record_path(project, home=home())
    assert would is not None
    assert err.startswith(NOT_RECORDED.format(record=evidence.shown(would), why="")[:-1]), err
    assert err.count("\n") == 1


def test_a_state_directory_that_is_a_symlink_is_refused_and_warns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Mutation (declared): the record written by its path, not by the contained walk -> the line
    # lands where the link leads, with no warning.
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (home() / ".local" / "state").mkdir(parents=True)
    (home() / STATE_DIR).symlink_to(elsewhere, target_is_directory=True)
    project = tmp_path / "project"
    project.mkdir()
    code, _, err = prove_cli(project, monkeypatch, "--", NAME)
    assert code == 0
    assert "was not written" in err
    assert list(elsewhere.iterdir()) == []


def test_a_home_that_is_itself_a_link_records_where_it_leads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The database's home is a link (a home moved to another disk and linked back): the link is
    # the machine's, which no session writes, so the walk starts where it leads.
    # Mutation (declared): the home walked as the database spells it -> "Not a directory".
    real = tmp_path / "real-home"
    real.mkdir()
    linked = tmp_path / "linked-home"
    linked.symlink_to(real, target_is_directory=True)
    as_owner_home(monkeypatch, linked)
    project = tmp_path / "project"
    project.mkdir()
    code, _, err = prove_cli(project, monkeypatch, "--", NAME)
    assert (code, err) == (0, "")
    assert len(records(real)) == 1


def test_no_home_plans_no_record(tmp_path: Path) -> None:
    # Mutation (declared): the no-home arm dropped from `record_path` -> it plans under no home.
    assert record_path(tmp_path, home=None) is None


@pytest.mark.parametrize("json_flag", [[], ["--json"]])
def test_no_home_warns_and_keeps_the_verdict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, json_flag: list[str]
) -> None:
    as_owner_home(monkeypatch, None)
    project = tmp_path / "project"
    project.mkdir()
    code, out, err = prove_cli(project, monkeypatch, *json_flag, "--", NAME)
    assert code == 0
    if json_flag:
        assert json.loads(out)["verdict"] == "proved"
    else:
        assert out.startswith("proved: ")
    assert err == NOT_RECORDED.format(record=evidence.UNNAMED, why=NO_HOME) + "\n"


def test_no_value_reaches_the_record(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # An assignment and an option given its value with `=`: the record carries their names.
    # Mutations (declared): the receipt shows an assignment's value, or an option's -> the value
    # is in the record.
    project = tmp_path / "project"
    project.mkdir()
    value = "s3cret-value-for-the-record"
    code, _, _ = prove_cli(
        project, monkeypatch, "--", f"API_TOKEN={value}", NAME, f"--api-key={value}"
    )
    assert code == 0
    text = (evidence_dir() / files()[0]).read_text(encoding="utf-8")
    assert value not in text
    (kept,) = records()
    assert kept["argv"] == ["API_TOKEN=…", NAME, "--api-key=…"]


def test_a_run_interrupted_before_its_command_starts_is_recorded_not_proven(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A Ctrl-C while the tree's state is taken, before the command runs: `not proven`, exit 1, and
    # its record kept, never an internal error (exit 2) with no record.
    def interrupted(*args: object) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(tree, "state", interrupted)
    project = tmp_path / "project"
    project.mkdir()
    try:
        code, _, _ = prove_cli(project, monkeypatch, "--", NAME)
    except KeyboardInterrupt:  # would stop the whole session rather than fail this case
        pytest.fail("the interrupt escaped prove")
    assert code == 1
    (kept,) = records()
    assert (kept["verdict"], kept["reason"]) == (Verdict.NOT_PROVEN, INTERRUPTED)


def test_a_timed_out_run_is_recorded_not_proven(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Mutation (declared): a run past its time limit said to be interrupted -> the reason differs.
    project = tmp_path / "project"
    project.mkdir()
    code, _, _ = prove_cli(project, monkeypatch, "--timeout", "0.5", "--", NAME, "--sleep", "30")
    assert code == 1
    (kept,) = records()
    assert (kept["verdict"], kept["reason"]) == (Verdict.NOT_PROVEN, TIMED_OUT)


def test_an_interrupted_run_is_recorded_not_proven(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Mutation (declared): an interrupted run said to have timed out -> the reason differs.
    def interrupted(process: object, seconds: float) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(processes, "exited", interrupted)
    project = tmp_path / "project"
    project.mkdir()
    code, _, _ = prove_cli(project, monkeypatch, "--", NAME, "--sleep", "30")
    assert code == 1
    (kept,) = records()
    assert (kept["verdict"], kept["reason"]) == (Verdict.NOT_PROVEN, INTERRUPTED)


def test_a_junit_record_marks_its_runner_not_verified(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Mutation (declared): a `--junit` receipt marks its runner verified -> so does the record.
    project = tmp_path / "project"
    project.mkdir()
    code, _, _ = prove_cli(project, monkeypatch, "--junit", REPORT, "--", *writer("pass"))
    assert code == 0
    (kept,) = records()
    assert (kept["verdict"], kept["runner"], kept["verified"]) == ("proved", None, False)


# --- gate ---------------------------------------------------------------------------------------


@needs_git
@pytest.mark.parametrize(
    ("flags", "mode", "gates"),
    [
        (
            [],
            "all",
            {"config": "passes", "docs": "passes", "bugs": "passes", "plan": "passes"}
            | {"commit": "passes", "trail": "would fail", "tests": "passes"},
        ),
        (
            ["--builtin"],
            "builtin",
            {"config": "passes", "docs": "passes", "bugs": "passes", "plan": "passes"}
            | {"commit": "passes", "trail": "would fail"},
        ),
        (["--custom"], "custom", {"tests": "passes"}),
        (["--only", "docs"], "all", {"docs": "passes"}),
    ],
    ids=["neither", "builtin", "custom", "only"],
)
def test_gate_appends_one_line_per_run(
    tmp_path: Path, flags: list[str], mode: str, gates: dict[str, str]
) -> None:
    # Mutations (declared): `run_gate` keeps no record -> no line; the flags drop `--only`'s
    # names -> the `only` case's argv differs.
    project = clone(tmp_path, GATE_BASE + custom_gate("tests", "pass"))
    code, _, err = cli(project, tmp_path, "gate", *flags)
    assert (code, err) == (0, "")
    (kept,) = records()
    assert files() == [f"{project_key(project)}.jsonl"]
    head = git(project, "rev-parse", "HEAD").strip()
    assert {key: kept[key] for key in ("version", "kind", "stayfixed", "mode")} == {
        "version": VERSION,
        "kind": "gate",
        "stayfixed": stayfixed.__version__,
        "mode": mode,
    }
    assert (kept["commit"], kept["dirty"], kept["gates"]) == (head, False, gates)
    assert kept["argv"] == flags
    assert STAMP.fullmatch(str(kept["at"]))


@needs_git
def test_gate_with_nothing_to_run_still_appends_its_line(tmp_path: Path) -> None:
    project = clone(tmp_path, GATE_BASE)
    code, out, _ = cli(project, tmp_path, "gate", "--custom")
    assert (code, out.strip()) == (0, "nothing to run: no configured gate of the kind asked for")
    (kept,) = records()
    assert (kept["mode"], kept["gates"]) == ("custom", {})


@needs_git
def test_a_failing_gate_run_records_each_gate_s_word(tmp_path: Path) -> None:
    # Mutation (declared): an enforcing gate's findings called advisory -> `would fail`.
    failing = custom_gate("tests", "raise SystemExit(3)")
    project = clone(tmp_path, GATE_BASE + failing)
    (project / "stayfixed.toml").write_text(
        GATE_BASE.replace('["docs"]', '["docs", "tests"]') + failing, encoding="utf-8"
    )
    commit(project, "chore: enforce the tests gate")
    code, _, _ = cli(project, tmp_path, "gate", "--custom")
    assert code == 1
    (kept,) = records()
    assert kept["gates"] == {"tests": "fails"}


@needs_git
@pytest.mark.parametrize(
    "refusal", ["no-tree-config", "machine-file", "only-unknown", "loader-refused"]
)
def test_gate_appends_none_on_a_refusal_before_the_configuration_check(
    tmp_path: Path, refusal: str
) -> None:
    # Each refusal stops the run before the configuration check has an answer, so there is no
    # run to record; each says its own words and exits its own code. Mutations (declared):
    # `run_gate` keeping a record before each refusal -> that refusal's run leaves a line.
    project = clone(tmp_path, GATE_BASE)
    argv = ["gate"]
    machine = None
    if refusal == "no-tree-config":
        git(project, "rm", "-q", "stayfixed.toml")
        commit(project, "chore: no configuration")
        exit_code, said = 1, f"stayfixed: failed: {NO_TREE_CONFIG}\n"
    elif refusal == "machine-file":
        machine = tmp_path / "machine.toml"
        machine.write_text("[[[", encoding="utf-8")
        # The machine file's refusal has no constant: `config.reading` builds it from the path
        # and the parser's position.
        exit_code, said = (
            1,
            f"stayfixed: failed: {machine} is not valid TOML (at line 1, column 3)\n",
        )
    elif refusal == "loader-refused":
        # The tree's own `stayfixed.toml`, which the loader refuses: a key it does not know.
        (project / "stayfixed.toml").write_text(
            (project / "stayfixed.toml").read_text(encoding="utf-8") + "\n[nonsense]\nx = 1\n",
            encoding="utf-8",
        )
        commit(project, "chore: a key the loader refuses")
        exit_code, said = 1, None
    else:
        argv += ["--only", "no-such-gate"]
        exit_code, said = 2, f"stayfixed: refused: {ONLY_UNKNOWN.format(count=1)}\n"
    code, out, err = cli(project, tmp_path, *argv, machine=machine)
    if said is None:
        assert (code, out) == (exit_code, ""), err
        assert err.startswith("stayfixed: failed: "), err
    else:
        assert (code, out, err) == (exit_code, "", said)
    assert records() == []


@needs_git
@pytest.mark.parametrize("fault", ["no-home", "unwritable"])
@pytest.mark.parametrize(
    "flags", [[], ["--builtin"], ["--custom"]], ids=["neither", "builtin", "custom"]
)
def test_gate_without_a_record_keeps_its_exit_and_warns_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str, flags: list[str]
) -> None:
    # Mutation (declared): a record that cannot be written turns gate's exit 1 -> every case.
    project = clone(tmp_path, GATE_BASE + custom_gate("tests", "pass"))
    if fault == "no-home":
        as_owner_home(monkeypatch, None)
    else:
        (home() / ".local").write_text("", encoding="utf-8")
    code, out, err = cli(project, tmp_path, "gate", *flags)
    assert code == 0, out
    assert err.count("\n") == 1
    assert "was not written" in err
    assert records() == []


def test_each_line_holds_its_version_s_keys() -> None:
    # A key added to the receipt reaches every record: the format is a new version then, and this
    # frozen set moves with `VERSION`. Mutation (declared): a key dropped from the frozen set ->
    # the record holds one it does not name.
    receipt = Receipt(Verdict.PROVED, "", "", ("pytest",))
    assert evidence.VERSION == 1
    assert set(evidence.prove_line(receipt, at="t", version="v")) == evidence.PROVE_KEYS
    gate = evidence.gate_line(
        {}, mode="builtin", argv=[], commit=None, dirty=None, at="t", version="v"
    )
    assert set(gate) == evidence.GATE_KEYS


def test_a_fifo_at_the_record_is_a_warning_and_never_a_wait(tmp_path: Path) -> None:
    # A FIFO with no reader at the record's path: an open for writing would wait for a reader that
    # never comes, and `prove` and `gate` with it. Opened without blocking it is `ENXIO`, the one
    # warning. Run in a child under a timeout, so a regression fails this case rather than hanging
    # the suite. Mutation (declared): `O_NONBLOCK` left off the append's flags -> the child waits.
    home = tmp_path / "home"
    record = home / evidence.STATE_DIR / evidence.EVIDENCE / "k.jsonl"
    record.parent.mkdir(parents=True)
    os.mkfifo(record)
    probe = (
        "import sys\n"
        "from pathlib import Path\n"
        "from stayfixed.prove import evidence\n"
        "home = Path(sys.argv[2])\n"
        "print(evidence.append(Path(sys.argv[1]), {'a': 1}, home=home))\n"
    )
    done = subprocess.run(
        [sys.executable, "-c", probe, str(record), str(home)],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert done.stdout.startswith("stayfixed: the evidence record "), (done.stdout, done.stderr)
    assert "was not written" in done.stdout


def _gate_run(
    *, judged: bool, refused: bool, results: list[tuple[str, bool, bool, int]], enforcing: set[str]
) -> GateRun:
    """A gate run as `_verdict_words` reads one: each result a name, whether it ran, whether it
    answered, and how many findings it has."""
    verdict = types.SimpleNamespace(refused=refused, enforcing=frozenset(enforcing))
    ran = [
        types.SimpleNamespace(name=name, ran=r, answered=a, findings=["x"] * n)
        for name, r, a, n in results
    ]
    return cast("GateRun", types.SimpleNamespace(judged=judged, verdict=verdict, results=ran))


def test_each_gate_word_the_record_can_carry() -> None:
    # Every word of a gate record's `gates`, each from the state that says it. Mutations
    # (declared): each word spelled otherwise -> its case differs.
    run = _gate_run(
        judged=True,
        refused=True,
        results=[
            ("docs", True, True, 0),
            ("bugs", True, True, 2),
            ("trail", True, True, 1),
            ("plan", True, False, 0),
            ("commit", False, False, 0),
        ],
        enforcing={"bugs"},
    )
    assert _verdict_words(run, ["tests"]) == {
        "config": "refused",
        "docs": "passes",
        "bugs": "fails",
        "trail": "would fail",
        "plan": "could not run",
        "commit": "not run",
        "tests": "waiting",
    }
    unjudged = _gate_run(judged=False, refused=False, results=[], enforcing=set())
    assert _verdict_words(unjudged, []) == {}
