"""`stayfixed assess` through the real parser: its exit codes, its `--json`, and the one write it
makes, at a constant place a clone can shape only by committing something there."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from stayfixed.assess.assessment import SKIPPED
from stayfixed.assess.commands import BASE_NOT_THERE
from stayfixed.config.loader import CONFIG_FILE
from stayfixed.config.paths import STAYFIXED_DIRECTORY
from stayfixed.project.api import ASSESSMENT
from stayfixed.project.init import init
from tests.assess.smoke import BASE, smoke_repo
from tests.cli import cli, custom_gate
from tests.gitfixture import git, needs_git
from tests.parserlimits import LONG_HEX, PAST_FLOAT
from tests.project.repos import DOCUMENT as BASE_DOCUMENT
from tests.project.repos import repository
from tests.runners import LsRemote

CUSTOM_GATE = '\n[gates.custom.tests]\nrun = ["git", "--version"]\n'


@needs_git
def test_assess_exits_zero_and_its_json_is_the_inventory(tmp_path: Path) -> None:
    # Mutation: `--json` printing a document whose `items` is emptied (`run_assess` passing
    # `{**document(assessment), "items": []}` to `Result`) -> the equality below reddens, as long
    # as the smoke copy has an item at all, which the first assertion pins.
    root = smoke_repo(tmp_path)
    code, out, _ = cli(root, tmp_path, "assess", "--base", BASE, "--json")
    assert code == 0
    printed = json.loads(out)
    written = json.loads((root / ASSESSMENT).read_text(encoding="utf-8"))
    assert written["items"] != []
    assert {k: v for k, v in printed.items() if k != "summary"} == written


@needs_git
def test_a_base_the_checkout_lacks_is_named_as_why_the_gates_that_read_it_fail(
    tmp_path: Path,
) -> None:
    # The path the `init` skill sends a new user down: a repository with no origin, where `plan`
    # and `commit` could not run, each with a remedy about plans and commit messages. `adopt
    # promote` explained the missing base in a note, `assess` did not. Mutation (oracle):
    # "assess never explains a base the checkout lacks" -> the note is gone.
    root = repository(tmp_path, origin=None)
    git(root, "symbolic-ref", "HEAD", "refs/heads/develop")
    answered = init(
        root, machine=tmp_path / "m.toml", runner=LsRemote(), yes=True, dry_run=False, ci=False
    )
    assert not answered.refused
    git(root, "add", "-A")
    git(root, "commit", "-qm", "chore: adopt stayfixed")
    code, summary, _ = cli(root, tmp_path, "assess")
    assert code == 1
    assert summary.rstrip().endswith(BASE_NOT_THERE.format(branch="develop")), summary
    # A base that is there leaves the note out: the failures are then the tree's own.
    head = git(root, "rev-parse", "HEAD").strip()
    _, out, _ = cli(root, tmp_path, "assess", "--base", head)
    assert "note: the base" not in out


@needs_git
def test_assess_exits_one_when_a_gate_would_fail(tmp_path: Path) -> None:
    # Mutation: `exit_code=1 if assessment.would_fail else 0` becomes `exit_code=0` -> reddens.
    root = smoke_repo(tmp_path)
    (root / "AGENTS.md").write_text("".join("word\n" for _ in range(400)), encoding="utf-8")
    assert cli(root, tmp_path, "assess", "--base", BASE)[0] == 1


@needs_git
def test_a_symlinked_stayfixed_toml_is_refused_and_never_followed(tmp_path: Path) -> None:
    # `stayfixed gate` refuses a committed symlink at `stayfixed.toml`, and `assess` read through
    # it: a link to `/dev/zero` ended the run by exhausting memory. Both read the file through
    # the one reader that refuses a link. Mutation (declared): `load` reading the file by
    # following the link -> the run exits 0 and writes the inventory.
    root = smoke_repo(tmp_path)
    elsewhere = tmp_path / "elsewhere.toml"
    elsewhere.write_bytes((root / CONFIG_FILE).read_bytes())
    (root / CONFIG_FILE).unlink()
    (root / CONFIG_FILE).symlink_to(elsewhere)
    code, _, err = cli(root, tmp_path, "assess", "--base", BASE)
    assert code == 2
    assert CONFIG_FILE in err
    assert not (root / ASSESSMENT).exists()


@needs_git
def test_a_symlinked_stayfixed_directory_is_a_refusal_and_nothing_is_written_through_it(
    tmp_path: Path,
) -> None:
    # Mutation: drop the `except UnsafePath` in `write` -> the frame reports an internal error,
    # still exit 2, and the message assertion reddens.
    root = smoke_repo(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    stayfixed_directory = root / STAYFIXED_DIRECTORY
    for child in stayfixed_directory.iterdir():
        child.unlink()
    stayfixed_directory.rmdir()
    stayfixed_directory.symlink_to(outside, target_is_directory=True)
    code, _, err = cli(root, tmp_path, "assess", "--base", BASE)
    assert code == 2
    assert f"refusing to write {ASSESSMENT}" in err
    assert list(outside.iterdir()) == []


@needs_git
def test_a_file_where_stayfixed_s_directory_goes_is_a_refusal_and_is_left_as_it_was(
    tmp_path: Path,
) -> None:
    # The other half of the same refusal: `.stayfixed` is a regular file, so the walk cannot open
    # it as a directory. No entry in `mutations/` and no line of its own: the `except
    # UnsafePath` that turns it into the refusal also holds the symlink case above, and the
    # walk's `O_DIRECTORY` is `fsops`'s, held by its own tests. Mutation: drop that `except`
    # -> the frame reports an internal error, still exit 2, and the message assertion reddens.
    root = smoke_repo(tmp_path)
    stayfixed_directory = root / STAYFIXED_DIRECTORY
    for child in stayfixed_directory.iterdir():
        child.unlink()
    stayfixed_directory.rmdir()
    stayfixed_directory.write_text("a person's file\n", encoding="utf-8")
    before = sorted(p.name for p in root.iterdir())
    code, _, err = cli(root, tmp_path, "assess", "--base", BASE)
    assert code == 2
    assert f"refusing to write {ASSESSMENT}: a directory on its path" in err
    assert stayfixed_directory.read_text(encoding="utf-8") == "a person's file\n"
    assert sorted(p.name for p in root.iterdir()) == before


@needs_git
def test_a_directory_where_the_inventory_goes_is_a_refusal(tmp_path: Path) -> None:
    # Mutation: drop the `except IsADirectoryError` in `write` -> an internal error, exit 2, and
    # the message assertion reddens.
    root = smoke_repo(tmp_path)
    held = root / ASSESSMENT / "held.txt"
    held.parent.mkdir()
    held.write_text("a person's file\n", encoding="utf-8")
    code, _, err = cli(root, tmp_path, "assess", "--base", BASE)
    assert code == 2
    assert "something that is not a file is there" in err
    assert held.read_text(encoding="utf-8") == "a person's file\n"


@needs_git
def test_a_link_where_the_inventory_goes_is_replaced_and_its_target_is_untouched(
    tmp_path: Path,
) -> None:
    # No single line reddens this: what holds it is `os.replace` never following a link at its
    # destination, together with `fsops._mode_of` asking `lstat`, so the replacement neither
    # writes through the link nor takes the link's mode.
    root = smoke_repo(tmp_path)
    outside = tmp_path / "outside.txt"
    outside.write_text("a file outside the root\n", encoding="utf-8")
    (root / ASSESSMENT).symlink_to(outside)
    assert cli(root, tmp_path, "assess", "--base", BASE)[0] == 0
    assert not (root / ASSESSMENT).is_symlink()
    assert (root / ASSESSMENT).is_file()
    assert outside.read_text(encoding="utf-8") == "a file outside the root\n"


@needs_git
def test_a_custom_gate_runs_beside_the_built_ins(tmp_path: Path) -> None:
    # The fixture is `installed`, so the custom gate enforces from the commit that adds it.
    # Mutation: `config.gates.builtin` passed to `run_gates` in place of `config.gate_names` ->
    # the custom gate never runs and the last gate is `trail`.
    root = smoke_repo(tmp_path)
    with (root / CONFIG_FILE).open("a", encoding="utf-8") as document:
        document.write(CUSTOM_GATE)
    git(root, "commit", "-qam", "chore: a gate of our own")
    code, out, _ = cli(root, tmp_path, "assess", "--base", "HEAD~1", "--json")
    assert code == 0
    gates = json.loads(out)["gates"]
    assert gates[-1]["name"] == "tests"
    assert gates[-1]["enforcing"] is True


@needs_git
def test_builtin_runs_no_custom_gate_and_says_which_it_left_out(tmp_path: Path) -> None:
    # `stayfixed assess` in a clone runs the commands the clone configured; a person who has not
    # agreed to that still gets an assessment. The gate that writes the marker must not run, and
    # the summary names what was left out rather than counting it as passing. Mutation
    # (declared): `builtin` ignored -> the marker appears.
    root = smoke_repo(tmp_path)
    marker = tmp_path / "marker"
    with (root / CONFIG_FILE).open("a", encoding="utf-8") as document:
        document.write(custom_gate("tests", f"open({str(marker)!r}, 'w')"))
    git(root, "commit", "-qam", "chore: a gate of our own")
    code, out, _ = cli(root, tmp_path, "assess", "--base", "HEAD~1", "--builtin")
    assert code == 0
    assert not marker.exists()
    assert SKIPPED.format(names="tests") in out
    written = json.loads((root / ASSESSMENT).read_text(encoding="utf-8"))
    assert written["skipped"] == ["tests"]
    assert "tests" not in [gate["name"] for gate in written["gates"]]
    assert cli(root, tmp_path, "assess", "--base", "HEAD~1")[0] == 0
    assert marker.exists()


@needs_git
def test_assess_after_init_with_no_origin_fetched_names_the_gates_that_cannot_judge(
    tmp_path: Path,
) -> None:
    # The first thing a person runs after `init`: `origin` is configured and never fetched, so
    # the default base does not exist. `plan`, `commit` and `bugs`, which compares the ledger's
    # entries with the base's, could not run, one gate contract for one cause: `plan` reported a
    # `base-unresolvable` finding here, a second outcome for the same missing base. All three
    # are failing, so the command exits 1, and the inventory is still written where git
    # ignores it. Mutation (advisory): the default base spelled as `HEAD` -> the gates read an
    # empty range and the base's own ledger, nothing fails, and the exit code reddens.
    root = repository(tmp_path)
    init(root, machine=tmp_path / "m.toml", runner=LsRemote(), yes=True, dry_run=False, ci=False)
    git(root, "add", "-A")
    git(root, "commit", "-qm", "chore: stayfixed init")
    code, out, _ = cli(root, tmp_path, "assess", "--json")
    assert code == 1
    printed = json.loads(out)
    failing = {g["name"]: g["answered"] for g in printed["gates"] if g["failing"]}
    assert failing == {"bugs": False, "plan": False, "commit": False}
    assert printed["base"] == "refs/remotes/origin/main"
    assert git(root, "check-ignore", "--", ASSESSMENT).strip() == ASSESSMENT


@needs_git
def test_a_roadmap_and_agents_md_kept_out_of_git_fail_trail_and_docs_and_say_what_to_drop(
    tmp_path: Path,
) -> None:
    # Both gates read the committed place, where a file kept out of git is not, so both fail on
    # every run; the remedy that told the person to commit the roadmap was the wrong one, and the
    # configuration reference's answer is to drop the gate. The file's own `[artifacts] local`
    # is the adopted document's to write: `--local` does not offer these two.
    root = repository(tmp_path)
    (root / CONFIG_FILE).write_text(
        BASE_DOCUMENT + '\n[artifacts]\nlocal = ["roadmap", "agents-skeleton"]\n', encoding="utf-8"
    )
    init(root, machine=tmp_path / "m.toml", runner=LsRemote(), yes=True, dry_run=False, ci=False)
    git(root, "add", "-A")
    git(root, "commit", "-qm", "chore: stayfixed init")
    head = git(root, "rev-parse", "HEAD").strip()
    code, out, _ = cli(root, tmp_path, "assess", "--base", head, "--json")
    assert code == 1
    printed = json.loads(out)
    failing = {g["name"] for g in printed["gates"] if g["failing"]}
    assert {"trail", "docs"} <= failing
    remedies = {i["probe"]: i["remedy"] for i in printed["items"] if i["probe"] in failing}
    for gate in ("trail", "docs"):
        assert f"drops {gate} from [gates] builtin" in remedies[gate]


@needs_git
def test_a_probe_that_raises_exits_2_and_leaves_the_last_inventory_as_it_was(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # "Compute everything, then write once": an error the command has no answer for is the
    # frame's internal error, and the inventory the last finished run wrote stays. Mutation (by
    # hand): `write` moved above the probes -> a half-built inventory replaces it.
    root = smoke_repo(tmp_path)
    assert cli(root, tmp_path, "assess", "--base", BASE)[0] == 0
    before = (root / ASSESSMENT).read_bytes()

    def boom(context: object) -> list[object]:
        raise RuntimeError("a probe the command has no answer for")

    monkeypatch.setattr("stayfixed.assess.assessment.run_probes", boom)
    assert cli(root, tmp_path, "assess", "--base", BASE)[0] == 2
    assert (root / ASSESSMENT).read_bytes() == before


# Integers `tomllib` converts whatever their length, each too large for what reads the key: a hex
# literal (a power-of-two base is exempt from the 4,300-digit limit) that no `str` can print, and
# a decimal of 401 digits, inside the limit, that no `float` can hold.
TOO_LARGE = {"hex": LONG_HEX, "decimal": PAST_FLOAT}


@needs_git
@pytest.mark.parametrize("shape", sorted(TOO_LARGE))
def test_a_timeout_too_large_for_its_reader_is_the_configurations_own_error(
    tmp_path: Path, shape: str
) -> None:
    # `[gates] custom_timeout_seconds` was checked only for `<= 0`, so either literal reached the
    # custom gate: `str` raised `ValueError` with the interpreter's advice to raise a limit, or
    # `float` raised `OverflowError`, and `assess` ended in an internal error, exit 2. The loader
    # bounds every integer key, so it is the configuration's refusal, exit 1. Mutation
    # (declared): the bound on a schema integer dropped -> exit 2 again.
    root = smoke_repo(tmp_path)
    config = root / CONFIG_FILE
    config.write_text(
        config.read_text(encoding="utf-8")
        + f"\n[gates]\ncustom_timeout_seconds = {TOO_LARGE[shape]}\n"
        + CUSTOM_GATE,
        encoding="utf-8",
    )
    code, out, err = cli(root, tmp_path, "assess", "--base", BASE)
    assert code == 1, err
    assert "gates.custom_timeout_seconds must be a positive integer below" in out + err
    assert "internal error" not in out + err


@needs_git
def test_a_pyproject_number_past_the_conversion_limit_is_one_the_profile_cannot_read(
    tmp_path: Path,
) -> None:
    # A hex literal of any length parses, and the Python profile's locator read its text with
    # `str()`, which raises past 4,300 digits: `stayfixed assess` ended in an internal error, exit
    # 2. The value resolves to nothing, as a `pyproject.toml` that does not parse does, and
    # `requires-python` reads as absent. Mutation (declared): "a profile locator stringifies a
    # number past the conversion limit".
    root = smoke_repo(tmp_path)
    config = root / CONFIG_FILE
    config.write_text(
        config.read_text(encoding="utf-8").replace(
            "[stayfixed]\n", '[stayfixed]\nprofile = "python"\n', 1
        ),
        encoding="utf-8",
    )
    assert 'profile = "python"' in config.read_text(encoding="utf-8")
    (root / "pyproject.toml").write_text(
        '[project]\nname = "smoke"\nrequires-python = 0x' + "f" * 5_000 + "\n", encoding="utf-8"
    )
    code, out, err = cli(root, tmp_path, "assess", "--base", BASE, "--json")
    assert code in (0, 1), err
    assert "internal error" not in out + err
    ids = [item["rule"] for item in json.loads(out)["items"]]
    assert "requires-python" in ids
