"""`stayfixed adopt promote`: the state machine that moves one gate at a time from advisory to
enforcing, over a repository `init --yes` wrote and two commits made.

Every promotion is judged against the first commit, named by its full id: the fixture has an
origin but no remote-tracking ref, so the default base does not exist and `plan` and `commit`
would have no range. From that commit, `plan` lints the one adoption plan and `commit` checks one
message, and all five built-in gates pass on the tree as `_project` leaves it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from stayfixed.assess.commands import BASE_NOT_THERE, NOT_RUN, WAITING
from stayfixed.assess.report import BUILTIN_FINDINGS_ELSEWHERE, FINDINGS_ELSEWHERE
from stayfixed.assess.state import Transition, promote
from stayfixed.config.loader import CONFIG_FILE, load, preset_defaults
from stayfixed.config.owned import OwnedKeyError
from stayfixed.config.schema import BUILTIN_GATES, Config
from stayfixed.errors import Refusal
from stayfixed.findings import LISTED_LIMIT
from stayfixed.project.api import rewrite_owned
from stayfixed.project.templates import CONFIG_ARTIFACT
from stayfixed.project.upgrade import upgrade
from stayfixed.scaffold import Manifest, ManifestError, digest
from tests.cli import cli, custom_gate
from tests.gitfixture import git, needs_git
from tests.project.repos import repository
from tests.runners import LsRemote

pytestmark = needs_git

PLAN = "# Adoption\n\n**Scope:** adoption.\n\n**Premise:** none.\n"
PLANS = preset_defaults("widget").paths.plans
ADOPTION = f"{PLANS}/2026-09-23-stayfixed-adoption.md"
# Well past the preset's `AGENTS.md` budget, so the `docs` gate has a finding.
OVER_BUDGET = "".join("word\n" for _ in range(400))
MARKER = "marker"


def _project(tmp_path: Path, *, branch: str = "main") -> tuple[Path, str]:
    """A repository on `branch` that `init --yes --no-ci` wrote, committed, then an adoption plan
    committed with the trail that lists it; the root, and the first commit's full id.

    The plan is staged before `docs trail` runs, because the trail lists tracked files only:
    regenerated first, it would be stale once the plan is committed.
    """
    root = repository(tmp_path)
    git(root, "symbolic-ref", "HEAD", f"refs/heads/{branch}")
    # Answered rather than detected: the fixture has an origin and no `origin/HEAD`, where `init`
    # keeps `main` whatever is checked out.
    code, _, err = cli(root, tmp_path, "init", "--yes", "--no-ci", "--base-branch", branch)
    assert code == 0, err
    git(root, "add", "-A")
    git(root, "commit", "-qm", "chore: adopt stayfixed")
    (root / ADOPTION).write_text(PLAN, encoding="utf-8")
    git(root, "add", "-A")
    code, _, err = cli(root, tmp_path, "docs", "trail")
    assert code == 0, err
    git(root, "add", "-A")
    git(root, "commit", "-qm", "docs: the stayfixed adoption plan")
    return root, git(root, "rev-parse", "HEAD~1").strip()


def _config(root: Path, tmp_path: Path) -> Config:
    return load(root, machine=tmp_path / "m.toml")


def _document(root: Path) -> str:
    return (root / CONFIG_FILE).read_text(encoding="utf-8")


def _set(root: Path, old: str, new: str) -> None:
    """Replace `old` in `stayfixed.toml`, once, by `new`."""
    text = _document(root)
    assert text.count(old) == 1, old
    (root / CONFIG_FILE).write_text(text.replace(old, new), encoding="utf-8")


# Where a promotion may start: a project `init` left, and one an `adopt begin` left in 0.2.0, the
# release before promotion moved a project out of `initialised` itself. That command wrote
# `state = "adopting"` and no `enforced` line, through the owned-key rewrite, and an upgrade
# leaves such a document as it is.
STARTS = pytest.mark.parametrize("start", ["initialised", "adopting"])


def _start(root: Path, start: str) -> None:
    """Leave the project at `start`; `adopting` is written as 0.2.0's `adopt begin` wrote it, the
    manifest's record re-stamped with it, so `uninstall` still knows the document as its own."""
    if start == "initialised":
        return
    before = _document(root)
    rewrite_owned(root, {("stayfixed", "state"): "adopting"})
    assert _document(root) == before.replace('state = "initialised"\n', 'state = "adopting"\n')
    assert "\nenforced =" not in _document(root)


def _land(root: Path, subject: str = "chore: a custom gate") -> str:
    """Commit the tree as it is and name the commit: a base that has the tree's custom gates,
    which is the only base a custom gate is promoted against."""
    git(root, "add", "-A")
    git(root, "commit", "-qm", subject)
    return git(root, "rev-parse", "HEAD").strip()


def _add_marker_gate(root: Path) -> None:
    with (root / CONFIG_FILE).open("a", encoding="utf-8") as stream:
        stream.write(custom_gate(MARKER, f"open({MARKER!r}, 'w').close()"))


def _with_marker_gate(root: Path) -> str:
    """The marker gate, landed: the base the promotion is judged against from here on."""
    _add_marker_gate(root)
    return _land(root)


def test_a_promotion_keeps_every_other_byte_and_the_record(tmp_path: Path) -> None:
    # The state machine's one write is `state` and `enforced`, through `rewrite_owned`, so the
    # manifest's record of the untouched document is re-stamped with it. Mutation: `_write`
    # passing `"installed"` -> the byte equality reddens; skipping the manifest's re-stamp in
    # `rewrite_owned` -> the digest equality reddens.
    root, base = _project(tmp_path)
    before = _document(root)
    promote(root, _config(root, tmp_path), ["docs"], base=base, machine=tmp_path / "m.toml")
    after = _document(root)
    assert before.count('state = "initialised"') == 1
    assert before.count("[stayfixed]\n") == 1
    expected = before.replace('state = "initialised"', 'state = "adopting"')
    assert after == expected.replace("[stayfixed]\n", '[stayfixed]\nenforced = ["docs"]\n')
    record = Manifest.read(root).get(CONFIG_ARTIFACT)
    assert record is not None
    assert record.sha256 == digest(after)


@STARTS
def test_a_named_gate_that_passes_moves_an_initialised_project_to_adopting(
    tmp_path: Path, start: str
) -> None:
    # Promotion is the one adoption step: the first promotion moves an initialised project to
    # adopting, since the loader refuses a list under `initialised`, and a project an earlier
    # release's `adopt begin` left adopting with no list is promoted from there the same way.
    # Mutation: `after` kept at the current state when not installing -> `enforced` is written
    # under `initialised`, and reloading the document refuses it. Mutation (declared): `promote`
    # refusing an adopting project that enforces nothing yet -> the `adopting` case reddens.
    root, base = _project(tmp_path)
    _start(root, start)
    transition = promote(
        root, _config(root, tmp_path), ["docs"], base=base, machine=tmp_path / "m.toml"
    )
    assert (transition.before, transition.after, transition.promoted) == (
        start,
        "adopting",
        ("docs",),
    )
    assert _config(root, tmp_path).stayfixed.enforced == ("docs",)


def test_named_gates_are_promoted_all_together_or_not_at_all(tmp_path: Path) -> None:
    # Mutation (declared): the write condition made `if not promoted:` -> `bugs` is written
    # although `docs`, named beside it, failed.
    root, base = _project(tmp_path)
    (root / "AGENTS.md").write_text(OVER_BUDGET, encoding="utf-8")
    before = _document(root)
    transition = promote(
        root, _config(root, tmp_path), ["docs", "bugs"], base=base, machine=tmp_path / "m.toml"
    )
    assert transition.promoted == ()
    assert set(transition.failing) == {"docs"}
    assert (transition.before, transition.after) == ("initialised", "initialised")
    assert _document(root) == before


def test_with_no_names_every_passing_gate_is_enforced_and_the_rest_are_named(
    tmp_path: Path,
) -> None:
    # Mutation (declared): the write condition made `if failing or unanswered or not promoted:`
    # -> nothing is written once `docs` fails, and the four that passed stay advisory.
    root, base = _project(tmp_path)
    (root / "AGENTS.md").write_text(OVER_BUDGET, encoding="utf-8")
    transition = promote(root, _config(root, tmp_path), [], base=base, machine=tmp_path / "m.toml")
    passing = tuple(name for name in BUILTIN_GATES if name != "docs")
    assert transition.promoted == passing
    assert list(transition.failing) == ["docs"]
    assert transition.failing["docs"] > 0
    assert transition.unanswered == ()
    loaded = _config(root, tmp_path).stayfixed
    assert (loaded.state, loaded.enforced) == ("adopting", passing)


def test_promoting_every_configured_gate_installs_the_project(tmp_path: Path) -> None:
    # Mutation (declared): `after = "adopting"` always -> the state stays adopting with every
    # gate listed.
    root, base = _project(tmp_path)
    transition = promote(root, _config(root, tmp_path), [], base=base, machine=tmp_path / "m.toml")
    assert (transition.after, transition.promoted, transition.failing) == (
        "installed",
        BUILTIN_GATES,
        {},
    )
    assert "enforced = []" in _document(root)
    loaded = _config(root, tmp_path).stayfixed
    assert loaded.state == "installed"
    assert loaded.enforcing == frozenset(BUILTIN_GATES)


def test_nothing_left_to_promote_on_an_installed_project_is_refused_rather_than_rewritten(
    tmp_path: Path,
) -> None:
    # In-comment, not declared: the bare call's refusal guards no write, since without it an
    # installed project is "completed" to the bytes it already holds. Mutation: `raise
    # Refusal(ALL_ENFORCE)` made `return Transition(state, state)` -> the second bare call
    # returns, and the `pytest.raises` reddens.
    root, base = _project(tmp_path)
    promote(root, _config(root, tmp_path), ["docs"], base=base, machine=tmp_path / "m.toml")
    with pytest.raises(Refusal, match="already enforces"):
        promote(root, _config(root, tmp_path), ["docs"], base=base, machine=tmp_path / "m.toml")
    promote(root, _config(root, tmp_path), [], base=base, machine=tmp_path / "m.toml")
    before = _document(root)
    with pytest.raises(Refusal, match="already enforces"):
        promote(root, _config(root, tmp_path), [], base=base, machine=tmp_path / "m.toml")
    assert _document(root) == before


def test_an_adopting_project_whose_every_gate_enforces_is_completed_to_installed(
    tmp_path: Path,
) -> None:
    # A project that removed the one gate it had not promoted: every configured gate enforces
    # and the state still says adopting, so a bare `promote` completes it without running one.
    # Mutation (declared): the completion's branch made to refuse as under `installed` -> the
    # bare call raises the "nothing left" refusal, and this case alone reddens.
    root, _ = _project(tmp_path)
    kept = [name for name in BUILTIN_GATES if name != "trail"]
    listed = ", ".join(f'"{name}"' for name in (*kept, MARKER))
    _set(
        root,
        'state = "initialised"\n',
        f'state = "adopting"\nenforced = [{listed}]\n',
    )
    with (root / CONFIG_FILE).open("a", encoding="utf-8") as stream:
        stream.write("\n[gates]\nbuiltin = [" + ", ".join(f'"{n}"' for n in kept) + "]\n")
    base = _with_marker_gate(root)
    transition = promote(root, _config(root, tmp_path), [], base=base, machine=tmp_path / "m.toml")
    assert (transition.before, transition.after, transition.promoted) == (
        "adopting",
        "installed",
        (),
    )
    assert not (root / MARKER).exists()
    loaded = _config(root, tmp_path).stayfixed
    assert loaded.state == "installed"
    assert "enforced = []" in _document(root)


@pytest.mark.parametrize("begun", [False, True], ids=["initialised", "adopting"])
def test_a_project_with_no_gate_is_refused_rather_than_installed(
    tmp_path: Path, begun: bool
) -> None:
    # With nothing configured nothing is wanted, and the completion that is right for an
    # adopting project whose every gate enforces would install one that never earned a gate,
    # adopting or not. `adopting` with an empty `enforced` is written by hand here, as a person
    # or an earlier release left it. Mutation (declared): the refusal's condition made
    # `if False:` -> the project is written `installed`.
    root, base = _project(tmp_path)
    with (root / CONFIG_FILE).open("a", encoding="utf-8") as stream:
        stream.write("\n[gates]\nbuiltin = []\n")
    if begun:
        _set(root, 'state = "initialised"\n', 'state = "adopting"\n')
        assert _config(root, tmp_path).stayfixed.state == "adopting"
    before = _document(root)
    with pytest.raises(Refusal, match="configures no gate"):
        promote(root, _config(root, tmp_path), [], base=base, machine=tmp_path / "m.toml")
    assert _document(root) == before


def test_a_completion_the_editor_cannot_write_names_both_keys_as_they_will_be(
    tmp_path: Path,
) -> None:
    # An adopting project whose every gate enforces, listed over several lines. The editor
    # sets `enforced` first and refused it naming `enforced = []` alone; followed beside
    # `state = "adopting"`, that loads with nothing enforcing, every earned gate demoted. The
    # remedy names both keys as the completion writes them, and following it installs.
    # Mutation (declared): the editor's own refusal re-raised -> the message lacks the state.
    root, base = _project(tmp_path)
    multiline = "".join(f'  "{name}",\n' for name in BUILTIN_GATES)
    _set(root, 'state = "initialised"\n', f'state = "adopting"\nenforced = [\n{multiline}]\n')
    before = _document(root)
    with pytest.raises(OwnedKeyError) as refused:
        promote(root, _config(root, tmp_path), [], base=base, machine=tmp_path / "m.toml")
    message = str(refused.value)
    assert '`state = "installed"`' in message
    assert "`enforced = []`" in message
    assert _document(root) == before
    (root / CONFIG_FILE).write_text(
        before.replace(
            f'state = "adopting"\nenforced = [\n{multiline}]\n',
            'state = "installed"\nenforced = []\n',
        ),
        encoding="utf-8",
    )
    loaded = _config(root, tmp_path).stayfixed
    assert loaded.state == "installed"
    assert loaded.enforcing == frozenset(BUILTIN_GATES)


def test_a_named_gate_already_enforcing_is_refused_and_nothing_is_written(tmp_path: Path) -> None:
    # In-comment, not declared: this refusal guards no write the all-or-nothing rule does not
    # already hold; dropping it re-runs `docs` and writes the same list plus `bugs`.
    root, base = _project(tmp_path)
    promote(root, _config(root, tmp_path), ["docs"], base=base, machine=tmp_path / "m.toml")
    before = _document(root)
    with pytest.raises(Refusal, match="already enforces"):
        promote(
            root, _config(root, tmp_path), ["docs", "bugs"], base=base, machine=tmp_path / "m.toml"
        )
    assert _document(root) == before


def test_a_name_that_is_not_a_configured_gate_is_refused(tmp_path: Path) -> None:
    # In-comment, not declared: without it `run_gates` raises `KeyError` on the name, which the
    # frame reports as an internal error; nothing is written either way.
    root, base = _project(tmp_path)
    for name in ("config", "lint"):
        with pytest.raises(Refusal, match="configured gate"):
            promote(root, _config(root, tmp_path), [name], base=base, machine=tmp_path / "m.toml")


@pytest.mark.parametrize(
    ("old", "new"),
    [
        pytest.param(
            'state = "initialised"\n',
            'state = "initialised"\nenforced = [\n]\n',
            id="a-two-line-enforced",
        ),
        pytest.param('state = "initialised"\n', '"state" = "initialised"\n', id="a-quoted-state"),
    ],
)
def test_an_enforced_list_the_editor_cannot_rewrite_is_refused_before_any_gate_runs(
    tmp_path: Path, old: str, new: str
) -> None:
    # Mutation (declared): the trial rewrite made `pass` -> the marker gate runs before the
    # write refuses, so the marker appears.
    #
    # The remedy names what the document holds now. The trial sets made-up values, and passing
    # the editor's own refusal on told the person to write them: `state = "installed"`, which
    # enforces every gate with none of them earned, or `enforced = ["config"]`, which does not
    # load. Mutation: re-raising the editor's refusal unchanged -> the message assertions redden.
    root, _ = _project(tmp_path)
    _set(root, old, new)
    base = _with_marker_gate(root)
    before = _document(root)
    with pytest.raises(OwnedKeyError) as refused:
        promote(root, _config(root, tmp_path), [], base=base, machine=tmp_path / "m.toml")
    message = str(refused.value)
    assert '`state = "initialised"`' in message
    assert "`enforced = []`" in message
    assert "installed" not in message
    assert "config" not in message
    assert not (root / MARKER).exists()
    assert _document(root) == before


def test_an_uneditable_document_s_remedy_names_the_list_as_it_stands(tmp_path: Path) -> None:
    # An adopting project whose list is written over two lines: the remedy gives the list it
    # holds, one line, and not the trial's.
    root, base = _project(tmp_path)
    _set(root, 'state = "initialised"\n', 'state = "adopting"\nenforced = [\n  "docs",\n]\n')
    with pytest.raises(OwnedKeyError) as refused:
        promote(root, _config(root, tmp_path), [], base=base, machine=tmp_path / "m.toml")
    message = str(refused.value)
    assert '`state = "adopting"`' in message
    assert '`enforced = ["docs"]`' in message
    assert "config" not in message


def test_a_document_a_custom_gate_left_invalid_is_refused_as_invalid_toml(tmp_path: Path) -> None:
    # A custom gate is a command, and one that appends `[[broken` to `stayfixed.toml` while it
    # runs leaves a document that does not parse by the time the promotion writes. The editor
    # says so with the parser's position; relabelled as "a shape stayfixed does not rewrite", the
    # remedy sent the person to edit two keys in a file that does not load. Mutation (declared):
    # the parse refusal relabelled again -> the shape sentence comes back.
    root, _ = _project(tmp_path)
    corrupt = f"open({CONFIG_FILE!r}, 'a').write('[[broken')"
    with (root / CONFIG_FILE).open("a", encoding="utf-8") as stream:
        stream.write(custom_gate("corrupt", corrupt))
    base = _land(root)
    with pytest.raises(OwnedKeyError) as refused:
        promote(root, _config(root, tmp_path), ["corrupt"], base=base, machine=tmp_path / "m.toml")
    message = str(refused.value)
    assert "is not valid TOML" in message
    assert "shape" not in message


def test_a_manifest_the_write_cannot_read_is_refused_before_any_gate_runs(tmp_path: Path) -> None:
    # The write re-stamps the manifest's record of `stayfixed.toml`, so a manifest that does not
    # parse refuses the write; found only there, it was found after every gate, a custom
    # command included, had run. Mutation (declared): the pre-check's `Manifest.read` made
    # `pass` -> the marker gate runs and the marker appears.
    root, _ = _project(tmp_path)
    base = _with_marker_gate(root)
    manifest = root / ".stayfixed" / "manifest.json"
    manifest.write_text("{not json", encoding="utf-8")
    before = _document(root)
    with pytest.raises(ManifestError):
        promote(root, _config(root, tmp_path), [], base=base, machine=tmp_path / "m.toml")
    assert not (root / MARKER).exists()
    assert _document(root) == before


def test_a_custom_gate_runs_its_command_when_promoted(tmp_path: Path) -> None:
    # A custom gate is promoted as a built-in is: its command runs, and its name joins the list.
    # Mutation: `run_gates` handed only the built-in names of `wanted` -> nothing runs, nothing
    # is promoted, and the marker is absent.
    root, _ = _project(tmp_path)
    base = _with_marker_gate(root)
    transition = promote(
        root, _config(root, tmp_path), [MARKER], base=base, machine=tmp_path / "m.toml"
    )
    assert (root / MARKER).exists()
    assert transition.promoted == (MARKER,)
    assert _config(root, tmp_path).stayfixed.enforced == (MARKER,)


def test_a_custom_gate_the_base_does_not_have_is_neither_run_nor_promoted(tmp_path: Path) -> None:
    # `stayfixed gate` runs a custom gate only with the base's own command, so a promotion of
    # one the base lacks would enforce a command the pull request carrying it never ran. It is
    # not run here either, and waits: named beside a gate that passes it stops the whole
    # promotion, and with no names every other gate is promoted. Mutations (declared): nothing
    # waits -> the marker gate runs and is promoted; a waiting gate left out of the named rule
    # -> `docs` is written alone.
    root, base = _project(tmp_path)
    _add_marker_gate(root)
    before = _document(root)
    transition = promote(
        root, _config(root, tmp_path), ["docs", MARKER], base=base, machine=tmp_path / "m.toml"
    )
    assert (transition.promoted, transition.waiting) == ((), (MARKER,))
    assert not (root / MARKER).exists()
    assert _document(root) == before
    transition = promote(root, _config(root, tmp_path), [], base=base, machine=tmp_path / "m.toml")
    assert not (root / MARKER).exists()
    assert (transition.promoted, transition.waiting) == (BUILTIN_GATES, (MARKER,))
    assert MARKER not in _config(root, tmp_path).stayfixed.enforcing


def test_a_custom_gate_waits_when_the_base_cannot_be_read(tmp_path: Path) -> None:
    # The fixture's default base does not exist: git cannot answer what the base's command is,
    # so the gate waits as for a base without it, and the built-ins still run. Mutation
    # (declared): the unreadable base raised -> the whole promotion fails.
    root, _ = _project(tmp_path)
    _with_marker_gate(root)
    missing = "refs/remotes/origin/no-such-branch"
    transition = promote(
        root, _config(root, tmp_path), [], base=missing, machine=tmp_path / "m.toml"
    )
    assert transition.waiting == (MARKER,)
    assert "docs" in transition.promoted
    assert not (root / MARKER).exists()


def test_a_custom_gate_the_base_runs_another_command_for_waits_and_the_command_says_why(
    tmp_path: Path,
) -> None:
    # Re-commanded on this branch, the gate's command is not the base's either. The summary
    # names it and says what to do, and `--json` lists it apart from the gates that ran.
    root, _ = _project(tmp_path)
    with (root / CONFIG_FILE).open("a", encoding="utf-8") as stream:
        stream.write(custom_gate(MARKER, "pass"))
    base = _land(root)
    text = _document(root).replace(custom_gate(MARKER, "pass"), "")
    (root / CONFIG_FILE).write_text(text, encoding="utf-8")
    _add_marker_gate(root)
    code, out, err = cli(root, tmp_path, "adopt", "promote", MARKER, "--base", base)
    assert code == 1, err
    assert out.splitlines() == [
        f"promoted: nothing; still advisory: {MARKER} (not on the base); state initialised",
        WAITING,
        FINDINGS_ELSEWHERE,
    ]
    assert not (root / MARKER).exists()
    code, out, _ = cli(root, tmp_path, "adopt", "promote", MARKER, "--base", base, "--json")
    assert json.loads(out)["not_on_base"] == [MARKER]


def test_builtin_runs_no_custom_gate_and_promotes_the_built_ins_alone(tmp_path: Path) -> None:
    # In a clone, `origin/<base>` is the clone author's, so a base that has a custom gate's
    # command is no brake: without `builtin`, `adopt promote` runs the clone's commands whatever
    # the person answered. `builtin` runs none, and a custom gate it did not run is never
    # promoted: named beside a built-in it holds the whole promotion back, and with no names
    # every built-in that passes is promoted and the custom gate stays advisory. Mutations
    # (oracle): "adopt promote --builtin still runs the custom gates" -> the marker is written
    # and the gate promoted; "a named custom gate --builtin did not run holds nothing back" ->
    # `docs` is written alone.
    root, _ = _project(tmp_path)
    base = _with_marker_gate(root)
    before = _document(root)
    transition = promote(
        root,
        _config(root, tmp_path),
        ["docs", MARKER],
        base=base,
        machine=tmp_path / "m.toml",
        builtin=True,
    )
    assert (transition.promoted, transition.skipped, transition.waiting) == ((), (MARKER,), ())
    assert not (root / MARKER).exists()
    assert _document(root) == before
    transition = promote(
        root, _config(root, tmp_path), [], base=base, machine=tmp_path / "m.toml", builtin=True
    )
    assert not (root / MARKER).exists()
    assert (transition.promoted, transition.skipped) == (BUILTIN_GATES, (MARKER,))
    assert [r.name for r in transition.results] == list(BUILTIN_GATES)
    loaded = _config(root, tmp_path).stayfixed
    assert (loaded.state, loaded.enforced) == ("adopting", BUILTIN_GATES)


def test_adopt_promote_builtin_names_the_custom_gates_it_did_not_run(tmp_path: Path) -> None:
    # The command says which gates it left out and why, lists them apart in `--json`, and exits
    # 1, since they stay advisory; the note says what running them takes, so the person who
    # declined decides again rather than the command. The closing line names `assess --builtin
    # --json`: it is relayed as what to run next, and a plain `assess` would run the commands the
    # person declined. Mutation (advisory): the `skipped` names left out of the advisory list ->
    # the command exits 0 and reddens. Mutation (oracle): "adopt promote --builtin hands on a
    # command that runs the custom gates" -> the closing line is the plain one and this reddens.
    root, _ = _project(tmp_path)
    base = _with_marker_gate(root)
    code, out, err = cli(root, tmp_path, "adopt", "promote", "--builtin", "--base", base)
    assert code == 1, err
    assert out.splitlines() == [
        f"promoted: {', '.join(BUILTIN_GATES)}; still advisory: {MARKER} (not run, as --builtin "
        "asked); state adopting",
        NOT_RUN,
        BUILTIN_FINDINGS_ELSEWHERE,
    ]
    assert not (root / MARKER).exists()
    code, out, _ = cli(root, tmp_path, "adopt", "promote", "--builtin", "--base", base, "--json")
    assert code == 1
    printed = json.loads(out)
    assert (printed["skipped"], printed["not_on_base"], printed["promoted"]) == ([MARKER], [], [])
    assert not (root / MARKER).exists()


def test_a_promotion_is_what_the_gate_enforces_next(tmp_path: Path) -> None:
    # Mutation (declared): the write made to carry `state` alone -> `enforced` stays empty, so
    # the second `gate` still prints `docs: advisory`.
    root, _ = _project(tmp_path)
    head = git(root, "rev-parse", "HEAD").strip()
    code, out, err = cli(root, tmp_path, "gate", "--only", "docs", "--base", head)
    assert (code, out.splitlines()) == (0, ["docs: advisory, 0 finding(s)"]), err
    code, out, err = cli(root, tmp_path, "adopt", "promote", "docs", "--base", head, "--json")
    assert code == 0, err
    printed = json.loads(out)
    assert (printed["promoted"], printed["failing"]) == (["docs"], {})
    code, out, err = cli(root, tmp_path, "gate", "--only", "docs", "--base", head)
    assert (code, out.splitlines()) == (0, ["docs: enforcing, 0 finding(s)"]), err


@pytest.mark.parametrize("branch", ["main", "develop"])
def test_a_base_that_is_not_there_is_named_as_the_reason_the_gates_reading_it_did_not_pass(
    tmp_path: Path, branch: str
) -> None:
    # The fixture has an origin and no remote-tracking ref, so the default base is not there:
    # `bugs`, `plan` and `commit` could not run, which read as a defect in the tree. The note
    # says why and names `--base`, and the last line where the findings are. Mutation (by hand):
    # the note dropped -> the `--base` assertion reddens. The `--base` it suggests is the
    # project's own base branch: a fixed `refs/heads/main` sent a `develop` project to a branch
    # it does not have. Mutation (oracle): "the missing-base note suggests main whatever the base
    # branch" -> `develop` reddens.
    root, _ = _project(tmp_path, branch=branch)
    code, out, err = cli(root, tmp_path, "adopt", "promote")
    assert code == 1, err
    lines = out.splitlines()
    assert (
        "still advisory: bugs (could not run), plan (could not run), commit (could not run)"
        in lines[0]
    )
    assert lines[1:] == [BASE_NOT_THERE.format(branch=branch), FINDINGS_ELSEWHERE]
    assert lines[1].endswith(f"such as refs/heads/{branch}")


def test_every_command_that_runs_gates_gives_a_gate_the_same_json_row(tmp_path: Path) -> None:
    # One gate result had three `--json` shapes: `assess` wrote `name`, `enforcing`, `answered`,
    # `reason`, `count` and `failing`; `gate` dropped `reason` and `failing`; `adopt promote`
    # gave no row, only lists of names. Now each is `report.gate_row`, so the rows agree key for
    # key and value for value, and `adopt promote` marks enforcing the gates it promoted.
    # Mutations (oracle): "adopt promote --json marks no gate it promoted enforcing" and "every
    # command's gate --json row drops failing".
    root, base = _project(tmp_path)
    (root / "AGENTS.md").write_text(OVER_BUDGET, encoding="utf-8")
    code, out, err = cli(root, tmp_path, "assess", "--base", base, "--json")
    assert code == 1, err
    assessed = {row["name"]: row for row in json.loads(out)["gates"]}
    code, out, err = cli(root, tmp_path, "gate", "--base", base, "--json")
    assert code == 0, err
    assert {row["name"]: row for row in json.loads(out)["gates"]} == assessed
    code, out, err = cli(root, tmp_path, "adopt", "promote", "--base", base, "--json")
    assert code == 1, err
    printed = json.loads(out)
    promoted = set(printed["promoted"])
    assert promoted == set(BUILTIN_GATES) - {"docs"}
    expected = {name: {**row, "enforcing": name in promoted} for name, row in assessed.items()}
    assert {row["name"]: row for row in printed["gates"]} == expected
    assert (expected["docs"]["failing"], expected["docs"]["answered"]) == (True, True)
    assert printed["failing"] == {"docs": expected["docs"]["count"]}


def test_the_command_exits_1_when_a_gate_failed_and_reports_both_lists(tmp_path: Path) -> None:
    # Mutation (declared): `exit_code=1 if advisory else 0` dropped -> exits 0 with `docs` still
    # advisory.
    root, base = _project(tmp_path)
    (root / "AGENTS.md").write_text(OVER_BUDGET, encoding="utf-8")
    code, out, err = cli(root, tmp_path, "adopt", "promote", "--base", base, "--json")
    assert code == 1, err
    printed = json.loads(out)
    assert printed["promoted"] == [name for name in BUILTIN_GATES if name != "docs"]
    assert list(printed["failing"]) == ["docs"]
    assert (printed["before"], printed["after"]) == ("initialised", "adopting")


def test_adopt_promote_with_no_base_judges_against_the_base_branch(tmp_path: Path) -> None:
    # A local promotion is judged against `refs/remotes/origin/<project.base_branch>`. The
    # fixture has no remote-tracking ref, so `plan` cannot resolve that base and stays advisory;
    # once the ref exists at the first commit, the same call promotes it. Mutation: defaulting
    # to a ref other than the base branch's -> the second call exits 1.
    root, base = _project(tmp_path)
    code, out, _ = cli(root, tmp_path, "adopt", "promote", "plan", "--json")
    assert code == 1
    assert json.loads(out)["promoted"] == []
    branch = _config(root, tmp_path).project.base_branch
    git(root, "update-ref", f"refs/remotes/origin/{branch}", base)
    code, out, err = cli(root, tmp_path, "adopt", "promote", "plan", "--json")
    assert code == 0, err
    assert json.loads(out)["promoted"] == ["plan"]


def test_a_gate_that_could_not_run_is_named_and_the_command_exits_1(tmp_path: Path) -> None:
    # A custom gate whose command cannot start stays advisory, is named as one that could not
    # run, and nothing is written. Mutation: the unanswered names left out of `advisory` in
    # `run_adopt_promote` -> the summary loses the name and the command exits 0.
    root, _ = _project(tmp_path)
    with (root / CONFIG_FILE).open("a", encoding="utf-8") as stream:
        stream.write('\n[gates.custom.absent]\nrun = ["stayfixed-test-no-such-command"]\n')
    base = _land(root)
    before = _document(root)
    code, out, err = cli(root, tmp_path, "adopt", "promote", "absent", "--base", base)
    assert code == 1, err
    assert out.splitlines() == [
        "promoted: nothing; still advisory: absent (could not run); state initialised",
        FINDINGS_ELSEWHERE,
    ]
    assert _document(root) == before


def test_upgrade_after_a_promotion_plans_nothing_new(tmp_path: Path) -> None:
    # Promotions move `state` and `enforced` and nothing `upgrade` owns, so `upgrade` moves
    # no key afterwards and plans what it planned before the adoption (the roadmap `docs trail`
    # rewrote is hand-edited to it) and nothing more. Mutation: the promotion's write also
    # setting `[stayfixed] version` to an older release -> `upgrade` plans to move it back.
    # Skipping the record's re-stamp does not redden this case, because `upgrade` never plans
    # `stayfixed.toml` itself; `test_uninstall_after_a_promotion_takes_stayfixed_toml_back` holds
    # the re-stamp.
    root, base = _project(tmp_path)

    def planned() -> list[tuple[str, str, str]]:
        report = upgrade(
            root, machine=tmp_path / "m.toml", runner=LsRemote(), dry_run=True, force=()
        )
        assert report.moved == ()
        assert not report.refused
        return [(a.artifact_id, str(a.verb), a.target) for a in report.footprint.actions]

    before = planned()
    promote(root, _config(root, tmp_path), ["docs"], base=base, machine=tmp_path / "m.toml")
    promote(root, _config(root, tmp_path), [], base=base, machine=tmp_path / "m.toml")
    assert _config(root, tmp_path).stayfixed.state == "installed"
    assert planned() == before


@STARTS
def test_uninstall_after_a_promotion_takes_stayfixed_toml_back(tmp_path: Path, start: str) -> None:
    # The record was re-stamped at each write, so the promoted document is still one stayfixed
    # wrote, from either start: the bare promotion installs the project, and `uninstall` takes
    # the file back. Mutation: skipping `rewrite_owned`'s re-stamp -> `uninstall` keeps the file.
    # Mutation (declared): `promote` refusing an adopting project that enforces nothing yet ->
    # the `adopting` case reddens.
    root, base = _project(tmp_path)
    _start(root, start)
    first = promote(root, _config(root, tmp_path), ["docs"], base=base, machine=tmp_path / "m.toml")
    assert (first.after, first.promoted) == ("adopting", ("docs",))
    last = promote(root, _config(root, tmp_path), [], base=base, machine=tmp_path / "m.toml")
    assert (last.before, last.after) == ("adopting", "installed")
    assert _config(root, tmp_path).stayfixed.state == "installed"
    code, _, err = cli(root, tmp_path, "uninstall")
    assert code == 0, err
    assert not (root / CONFIG_FILE).exists()


@needs_git
def test_adopt_promote_names_at_most_the_listed_limit_in_each_list(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Custom gates are the repository's to add, so both lists on the line are bounded in number
    # by nothing: each names the first `LISTED_LIMIT` and counts the rest, and `--json` carries
    # every name. The transition is given, since only the line is under test. Mutation (oracle):
    # "adopt promote names every gate it promoted" or "... every gate still advisory" -> this
    # reddens.
    root, base = _project(tmp_path)
    promoted = tuple(f"p{n:02}" for n in range(LISTED_LIMIT + 3))
    skipped = tuple(f"s{n:02}" for n in range(LISTED_LIMIT + 2))
    given = Transition("adopting", "adopting", promoted=promoted, skipped=skipped)
    monkeypatch.setattr("stayfixed.assess.state.promote", lambda *_, **__: given)
    code, out, err = cli(root, tmp_path, "adopt", "promote", "--builtin", "--base", base)
    assert code == 1, err
    advisory = ", ".join(f"{name} (not run, as --builtin asked)" for name in skipped[:LISTED_LIMIT])
    assert out.splitlines()[0] == (
        f"promoted: {', '.join(promoted[:LISTED_LIMIT])}, and 3 more; "
        f"still advisory: {advisory}, and 2 more; state adopting"
    )
    code, out, _ = cli(root, tmp_path, "adopt", "promote", "--builtin", "--base", base, "--json")
    printed = json.loads(out)
    assert (printed["promoted"], printed["skipped"]) == (list(promoted), list(skipped))
