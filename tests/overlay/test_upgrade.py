from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from stayfixed.cli import build_parser, discover_registrars, run
from stayfixed.errors import Failure, Refusal
from stayfixed.overlay.api import create, init_instance
from stayfixed.overlay.upgrade import upgrade
from stayfixed.scaffold import MANIFEST_PATH, Verb, digest
from tests.runners import Recorder


def _an_overlay(tmp_path: Path) -> Path:
    return create("octo", "ov", source="local", root=tmp_path, runner=Recorder()).root


def _restamp(root: Path, artifact_id: str) -> None:
    """Record the artifact's *current* bytes, the state a release leaves behind when the
    template has moved on and the instance has not."""
    path = root / MANIFEST_PATH
    document = json.loads(path.read_text(encoding="utf-8"))
    body = (root / artifact_id).read_text(encoding="utf-8")
    document["artifacts"][artifact_id]["sha256"] = digest(body)
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")


def test_an_untouched_skeleton_file_is_refreshed(tmp_path: Path) -> None:
    # `overlay upgrade` refreshes untouched skeleton files after a release by the same rule a
    # project's files follow, which is the scaffold engine's hash comparison; this asserts the
    # overlay really goes through it rather than reimplementing it.
    root = _an_overlay(tmp_path)
    (root / "README.md").write_text("stale", encoding="utf-8")
    _restamp(root, "README.md")  # record the hash of the stale text, as a release would
    verbs = {a.artifact_id: a.verb for a in upgrade(root, dry_run=True).plan.actions}
    assert verbs["README.md"] is Verb.UPDATE


def test_a_hand_edited_file_is_skipped_and_named(tmp_path: Path) -> None:
    # The same rule's other half. An overlay is where the owner's own rules live, so a silent
    # overwrite here destroys the only copy of something.
    root = _an_overlay(tmp_path)
    (root / "common" / "codex" / "common.rules").write_text("my own rules\n", encoding="utf-8")
    verbs = {a.artifact_id: a.verb for a in upgrade(root, dry_run=True).plan.actions}
    assert verbs["common/codex/common.rules"] is Verb.SKIP_MODIFIED


def test_the_two_permission_files_are_asked_about_even_when_unchanged(tmp_path: Path) -> None:
    # Exactly two files are exceptions to the hash rule, and `overlay upgrade` diffs and asks
    # about them regardless of hash — they are the two files that can grant capability, and a
    # hash match is not consent for those. The scaffold engine every area shares has no verb for
    # it, so the decision list lives beside the plan rather than inside it.
    root = _an_overlay(tmp_path)
    decisions = upgrade(root, dry_run=True).decisions
    assert set(decisions) == {"common/claude/permissions.json", "common/claude/hooks.json"}


def test_a_dry_run_writes_nothing_where_a_real_run_would(tmp_path: Path) -> None:
    # Non-vacuous on purpose: on a freshly created overlay the plan carries no action, so a dry
    # run and a real run both write nothing and `if not dry_run:` could be deleted unnoticed.
    # A stale, re-stamped file gives the plan an UPDATE; the dry run must leave the stale bytes
    # and the real run must replace them. Mutation: `if not dry_run:` → `if True:` reddens the
    # first assertion; `apply(...)` removed reddens the second.
    root = _an_overlay(tmp_path)
    (root / "README.md").write_text("stale", encoding="utf-8")
    _restamp(root, "README.md")
    before = {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}
    assert upgrade(root, dry_run=True).plan.actions
    assert {p: p.read_bytes() for p in root.rglob("*") if p.is_file()} == before
    upgrade(root, dry_run=False)
    assert (root / "README.md").read_text(encoding="utf-8") != "stale"


def test_a_directory_that_is_not_an_overlay_is_refused_before_anything_is_written(
    tmp_path: Path,
) -> None:
    # `--root` defaults to `.` and was checked nowhere: in a directory
    # holding a `README.md` and a `src/main.py`, `stayfixed overlay upgrade --root .` created
    # the whole overlay — both plugin manifests, `hooks/hooks.json`, `common/**`, `.gitignore`
    # and `.github/workflows/scan.yml` — reported them as work done and exited 0. (Fourteen
    # files when the defect was found; the count has moved since, which is why it is not
    # restated here.) Writing a workflow file into a repository the owner may then
    # commit is the concrete harm.
    #
    # Mutation (`mutations/`, "overlay upgrade stops asking whether --root is an overlay"):
    # the `require_overlay` call is removed → the overlay's files appear and this reddens on
    # both the refusal and the tree.
    project = tmp_path / "project"
    (project / "src").mkdir(parents=True)
    (project / "README.md").write_text("# a project, not an overlay\n", encoding="utf-8")
    (project / "src" / "main.py").write_text("print('hi')\n", encoding="utf-8")
    before = sorted(p.relative_to(project) for p in project.rglob("*"))
    assert before, "the fixture writes nothing, so the comparison below would prove nothing"
    with pytest.raises(Refusal, match="must name an overlay"):
        upgrade(project, dry_run=False)
    assert sorted(p.relative_to(project) for p in project.rglob("*")) == before


def test_the_cli_exits_two_rather_than_zero_on_a_directory_that_is_not_an_overlay(
    tmp_path: Path,
) -> None:
    # The same finding through the command surface, which is where it was reproduced: the run
    # that created the overlay's files reported them as work done and exited 0, so nothing
    # about the outcome said anything had gone wrong.
    (tmp_path / "README.md").write_text("# not an overlay\n", encoding="utf-8")
    parser = build_parser(discover_registrars())
    assert run(["overlay", "upgrade", "--root", str(tmp_path)], parser=parser) == 2
    assert [p.name for p in tmp_path.iterdir()] == ["README.md"]


def test_a_manifest_init_renamed_is_still_refreshed_by_a_later_release(tmp_path: Path) -> None:
    # `overlay init` rewrote both manifests behind the scaffold ledger, so
    # every later `upgrade` reported `skip_modified .claude-plugin/plugin.json (hand-edited)` —
    # for the one file carrying `stayfixed.requires`, the version-compatibility declaration the
    # README advertises, and attributing to the owner an edit stayfixed itself made. `init` now
    # re-stamps each record with the bytes it wrote.
    #
    # Mutation (`mutations/`, "overlay init writes the manifests behind the scaffold
    # ledger"): the `with_record(replace(...))` line stops updating the digest → both manifests
    # read as hand-edited and this reddens.
    root = _an_overlay(tmp_path)
    init_instance(root, "OctoCat", runner=Recorder())
    verbs = {a.artifact_id: a.verb for a in upgrade(root, dry_run=True).plan.actions}
    for manifest in (".claude-plugin/plugin.json", ".claude-plugin/marketplace.json"):
        assert verbs[manifest] is not Verb.SKIP_MODIFIED
    # What the record now vouches for is the file `init` left: the owner's name and account, not
    # the template's. A re-stamp of anything else would make those bytes read as hand-edited.
    plugin = root / ".claude-plugin" / "plugin.json"
    document = json.loads(plugin.read_text(encoding="utf-8"))
    assert document["name"] == "stayfixed-overlay-octocat"
    assert document["author"] == {"name": "octocat"}
    recorded = json.loads((root / MANIFEST_PATH).read_text(encoding="utf-8"))["artifacts"]
    assert recorded[".claude-plugin/plugin.json"]["sha256"] == digest(
        plugin.read_text(encoding="utf-8")
    )
    # And the refresh really is live: a release that moves the template updates the file rather
    # than leaving the owner on a manifest nothing can reach.
    # Still a manifest that names this overlay — a release moving the file is what is being
    # modelled, not an owner breaking it — but with the older body a release has left behind.
    (root / ".claude-plugin" / "plugin.json").write_text(
        json.dumps({"name": "stayfixed-overlay-octocat", "version": "0.0.0"}) + "\n",
        encoding="utf-8",
    )
    _restamp(root, ".claude-plugin/plugin.json")
    moved = {a.artifact_id: a.verb for a in upgrade(root, dry_run=True).plan.actions}
    assert moved[".claude-plugin/plugin.json"] is Verb.UPDATE


def test_init_does_not_vouch_for_a_manifest_the_owner_edited(tmp_path: Path) -> None:
    # `init` re-stamped the ledger with whatever it wrote, without asking whether the file it
    # rewrote was stayfixed's to begin with. An owner who had edited `plugin.json` (a description
    # of their own) and then ran `init` had their edit recorded as stayfixed's bytes, and the next
    # `overlay upgrade` refreshed the file: the description, the suffix and the account were gone.
    # `init` rewrites the name and account either way; the record moves only when the bytes it
    # replaced were the ones recorded, so `upgrade` goes on naming the file as hand-edited.
    #
    # Mutation: `mutations/`'s "overlay init vouches for a manifest the owner edited".
    root = _an_overlay(tmp_path)
    plugin = root / ".claude-plugin" / "plugin.json"
    document = json.loads(plugin.read_text(encoding="utf-8"))
    document["description"] = "My own overlay."
    plugin.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    before = {a.artifact_id: a.verb for a in upgrade(root, dry_run=True).plan.actions}
    assert before[".claude-plugin/plugin.json"] is Verb.SKIP_MODIFIED
    init_instance(root, "acme", runner=Recorder())
    after = {a.artifact_id: a.verb for a in upgrade(root, dry_run=True).plan.actions}
    assert after[".claude-plugin/plugin.json"] is Verb.SKIP_MODIFIED
    upgrade(root, dry_run=False)
    kept = json.loads(plugin.read_text(encoding="utf-8"))
    assert kept["description"] == "My own overlay."
    assert kept["name"] == "stayfixed-overlay-acme"
    assert kept["author"] == {"name": "acme"}


def test_init_reads_every_manifest_before_it_rewrites_any(tmp_path: Path) -> None:
    # A manifest that cannot be read stops `init`, and it used to stop it after the ones before it
    # were rewritten and before their records were re-stamped: those files then read as
    # hand-edited to every later `upgrade`. Every manifest is read and decided first now, so the
    # failure leaves the tree as it was.
    #
    # Mutation: `mutations/`'s "overlay init rewrites a manifest before reading the next".
    root = _an_overlay(tmp_path)
    (root / ".codex-plugin" / "plugin.json").write_text("{not json", encoding="utf-8")
    before = {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}
    with pytest.raises(Failure, match="not valid JSON"):
        init_instance(root, "acme", runner=Recorder())
    assert {p: p.read_bytes() for p in root.rglob("*") if p.is_file()} == before


# --- a file an earlier release shipped and this one does not --------------------------------

# The bytes 0.1.0 and 0.1.1 shipped at `common/memory/README.md`, whole: the note reader read the
# file as a note with no frontmatter, so `memory index --check` failed in every project attached to
# the overlay. Held here in full so the digest `overlay upgrade` removes the file by is checked
# against the file it names rather than against itself.
SHIPPED_MEMORY_README = (
    "# Cross-project notes\n"
    "\n"
    "Notes that are true across your projects: how you like to work, what you have learned "
    "about a\n"
    "tool you use everywhere, standing preferences that are not rules.\n"
    "\n"
    "This directory is the store a bound repository links to as its `developer` group, alongside\n"
    "that project's own notes under `projects/<name>/memory/`. The routing index a session "
    "reads is\n"
    "rendered from both; it is generated, so write the notes and let the index follow.\n"
    "\n"
    "A note about one project goes under `projects/<name>/memory/` instead. Keeping the two apart\n"
    "is what stops one client's work reaching another client's session.\n"
)
MEMORY_README = "common/memory/README.md"


def _with_a_retired_file(
    root: Path, relative: str, *, ledger: bool, text: str, shipped: str, version: str
) -> Path:
    """An overlay carrying a retired file that holds `text`, with the ledger an earlier `--local`
    render leaves, recording the bytes release `version` `shipped` there, or with none, as an
    overlay generated from a template has (`publish-template` strips it)."""
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    manifest = root / MANIFEST_PATH
    if not ledger:
        if manifest.exists():
            manifest.unlink()
        return path
    document = json.loads(manifest.read_text(encoding="utf-8"))
    document["artifacts"][relative] = {
        "id": relative,
        "kind": "template",
        "location": "repo",
        "target": relative,
        "template": f"overlay/{relative}",
        "version": version,
        "sha256": digest(shipped),
    }
    manifest.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    return path


def _with_the_shipped_memory_readme(root: Path, *, ledger: bool, text: str) -> Path:
    return _with_a_retired_file(
        root,
        MEMORY_README,
        ledger=ledger,
        text=text,
        shipped=SHIPPED_MEMORY_README,
        version="0.1.1",
    )


@pytest.mark.parametrize("ledger", [True, False], ids=["recorded", "no-ledger"])
def test_the_memory_readme_a_release_shipped_is_removed(tmp_path: Path, ledger: bool) -> None:
    # `common/memory/README.md` became `_README.md`, which the note reader skips, and `upgrade`
    # created the new name beside the old one: the old one stayed, and `memory index --check`
    # went on reporting it unreadable. An overlay `--local` rendered carries a ledger that
    # records the file; one generated from a template carries none, and there the bytes a
    # release shipped are the only evidence the file is stayfixed's.
    #
    # Mutations: `mutations/`'s "a retired overlay file the ledger records is kept" and "a
    # retired overlay file holding the shipped bytes is kept".
    root = _an_overlay(tmp_path)
    path = _with_the_shipped_memory_readme(root, ledger=ledger, text=SHIPPED_MEMORY_README)
    planned = upgrade(root, dry_run=True).plan
    removed = [a for a in planned.actions if a.verb is Verb.REMOVE]
    assert [a.target for a in removed] == [MEMORY_README]
    # Non-vacuous: the dry run left it, and the real run takes it and keeps the new name.
    assert path.is_file()
    upgrade(root, dry_run=False)
    assert not path.exists()
    assert (root / "common" / "memory" / "_README.md").is_file()


@pytest.mark.parametrize("ledger", [True, False], ids=["recorded", "no-ledger"])
def test_an_edited_memory_readme_is_kept_and_the_report_says_what_to_do(
    tmp_path: Path, ledger: bool
) -> None:
    # A copy that is not the shipped bytes may hold the owner's own words, and nothing else holds
    # them, so it is never removed: the report names it and the way out, since the note reader
    # still reads it as a note.
    #
    # Mutations: `mutations/`'s "a retired overlay file with no ledger is removed whatever it
    # holds" and "a kept retired overlay file is named without its way out".
    root = _an_overlay(tmp_path)
    edited = SHIPPED_MEMORY_README + "\nMy own line.\n"
    path = _with_the_shipped_memory_readme(root, ledger=ledger, text=edited)
    planned = upgrade(root, dry_run=True).plan
    kept = {a.target: a for a in planned.actions}[MEMORY_README]
    assert kept.verb is Verb.SKIP_MODIFIED
    assert "_README.md" in kept.reason
    upgrade(root, dry_run=False)
    assert path.read_text(encoding="utf-8") == edited


def test_the_digest_held_for_the_retired_readme_is_the_shipped_files() -> None:
    # The constant and the bytes it names, checked against each other. No mutation: a changed
    # digest reddens the removal test above through the no-ledger case.
    from stayfixed.overlay.template import SHIPPED_MEMORY_README as held

    assert digest(SHIPPED_MEMORY_README) == held


@pytest.mark.parametrize("ledger", [True, False], ids=["recorded", "no-ledger"])
def test_init_removes_the_memory_readme_a_release_shipped(tmp_path: Path, ledger: bool) -> None:
    # An overlay generated from a template published at an earlier release arrives with the old
    # README and no ledger, and nobody is told to run `overlay upgrade` on an overlay just made.
    # `init`, which every such overlay runs, removes it, and drops a record the ledger holds.
    #
    # Mutation: `mutations/`'s "overlay init leaves the memory README a release shipped".
    root = _an_overlay(tmp_path)
    path = _with_the_shipped_memory_readme(root, ledger=ledger, text=SHIPPED_MEMORY_README)
    done = init_instance(root, "octo", runner=Recorder())
    assert not path.exists()
    assert any(MEMORY_README in note for note in done.notes)
    if ledger:
        recorded = json.loads((root / MANIFEST_PATH).read_text(encoding="utf-8"))["artifacts"]
        assert MEMORY_README not in recorded
    else:
        # A tree that arrived without a ledger is not given one.
        assert not (root / MANIFEST_PATH).exists()


@pytest.mark.parametrize("ledger", [True, False], ids=["recorded", "no-ledger"])
def test_init_leaves_the_memory_directory_its_readme_under_the_new_name(
    tmp_path: Path, ledger: bool
) -> None:
    # An overlay from a 0.1.x template has `common/memory/README.md` and no `_README.md`. Removing
    # the one left the directory empty, git keeps no empty directory, and a clone of the overlay
    # elsewhere had no `common/memory/` at all, so the `developer` link attach makes there
    # dangled. `init` writes the shipped `_README.md` in its place, and records it where the tree
    # has a ledger.
    #
    # Mutation: `mutations/`'s "overlay init leaves the memory directory empty".
    root = _an_overlay(tmp_path)
    successor = root / "common" / "memory" / "_README.md"
    shipped = successor.read_text(encoding="utf-8")
    successor.unlink()
    manifest = root / MANIFEST_PATH
    document = json.loads(manifest.read_text(encoding="utf-8"))
    del document["artifacts"]["common/memory/_README.md"]
    manifest.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    path = _with_the_shipped_memory_readme(root, ledger=ledger, text=SHIPPED_MEMORY_README)
    done = init_instance(root, "octo", runner=Recorder())
    assert not path.exists()
    assert successor.read_text(encoding="utf-8") == shipped
    assert any("common/memory/_README.md" in note for note in done.notes)
    if ledger:
        recorded = json.loads(manifest.read_text(encoding="utf-8"))["artifacts"]
        assert recorded["common/memory/_README.md"]["sha256"] == digest(shipped)
    else:
        assert not manifest.exists()


def test_init_that_stops_part_way_keeps_the_manifests_it_renamed_recorded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # `init` renamed the manifests, then stopped while retiring the old README, and exited with
    # the new records only in memory: the renamed manifests then read as hand-edited to every
    # `upgrade`. The records are written before anything is retired, so a stop there leaves them
    # true. What stops it here is an install whose template tree cannot be read, the one failure
    # left between the renames and the end of `init`: a removal or a write that fails is named
    # and passed over instead.
    #
    # Mutation: `mutations/`'s "overlay init records its renames only after the removal".
    from stayfixed.overlay import create as module

    def unreadable() -> list[object]:
        raise Failure("the overlay template tree is not readable")

    root = _an_overlay(tmp_path)
    path = _with_the_shipped_memory_readme(root, ledger=True, text=SHIPPED_MEMORY_README)
    monkeypatch.setattr(module, "templates", unreadable)
    with pytest.raises(Failure, match="not readable"):
        init_instance(root, "acme", runner=Recorder())
    monkeypatch.undo()
    assert not path.exists()
    verbs = {a.artifact_id: a.verb for a in upgrade(root, dry_run=True).plan.actions}
    for manifest in (
        ".claude-plugin/plugin.json",
        ".claude-plugin/marketplace.json",
        ".codex-plugin/plugin.json",
    ):
        assert verbs[manifest] is not Verb.SKIP_MODIFIED, manifest
        assert json.loads((root / manifest).read_text(encoding="utf-8"))["name"].endswith("-acme")


@pytest.mark.skipif(os.geteuid() == 0, reason="root removes from a directory it cannot write")
def test_a_retired_file_init_cannot_remove_is_named_and_the_rest_goes_on(tmp_path: Path) -> None:
    # `init` stopped at the first retired file it could not remove: the ones it had already
    # removed were gone, their `removed` lines never printed, and their records never dropped
    # from the ledger, so every later run read the absent file as unchanged and kept the record
    # for good. A file `init` cannot remove is named and left, as one it cannot read is, and the
    # ledger it writes drops the records of the files it did remove and only those.
    #
    # Mutation: `mutations/`'s "overlay init stops at a retired file it cannot remove".
    root = _an_overlay(tmp_path)
    for relative, text in (
        (ATTACH_SKILL, SHIPPED_ATTACH_SKILL),
        (RULES_README, SHIPPED_RULES_README_0_2),
    ):
        _with_a_retired_file(root, relative, ledger=True, text=text, shipped=text, version="0.2.0")
    rules = root / "common" / "rules"
    rules.chmod(0o555)
    try:
        done = init_instance(root, "acme", runner=Recorder())
    finally:
        rules.chmod(0o755)
    assert f"removed {ATTACH_SKILL}, which this release no longer ships" in done.notes
    left = [note for note in done.notes if note.startswith(f"left {RULES_README}: ")]
    assert left == [f"left {RULES_README}: cannot be removed: Permission denied"], done.notes
    # `init` went on to its last step, the secret scan.
    assert any("pre-commit" in note for note in done.notes), done.notes
    assert not (root / ATTACH_SKILL).exists()
    assert (root / RULES_README).is_file()
    assert ATTACH_SKILL in done.changed and RULES_README not in done.changed
    recorded = json.loads((root / MANIFEST_PATH).read_text(encoding="utf-8"))["artifacts"]
    assert ATTACH_SKILL not in recorded
    assert RULES_README in recorded
    # And the next run finishes the job.
    again = init_instance(root, "acme", runner=Recorder())
    assert f"removed {RULES_README}, which this release no longer ships" in again.notes
    assert (
        RULES_README
        not in json.loads((root / MANIFEST_PATH).read_text(encoding="utf-8"))["artifacts"]
    )


def test_a_successor_init_cannot_write_is_named_and_the_rest_goes_on(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The same stop one step later: the old README was removed, `_README.md` could not be written
    # in its place, and `init` refused with the README's record still in the ledger and its
    # `removed` line never printed. The write that fails is named with the command that writes
    # the file, and the ledger drops the record of the file that is gone.
    #
    # Mutation: `mutations/`'s "overlay init stops at a successor it cannot write".
    from stayfixed import fsops

    write = fsops.write_within

    def refused(root: Path, relative: str, body: str) -> None:
        if relative == "common/memory/_README.md":
            raise PermissionError(13, "Permission denied")
        write(root, relative, body)

    root = _an_overlay(tmp_path)
    (root / "common" / "memory" / "_README.md").unlink()
    path = _with_the_shipped_memory_readme(root, ledger=True, text=SHIPPED_MEMORY_README)
    monkeypatch.setattr(fsops, "write_within", refused)
    done = init_instance(root, "acme", runner=Recorder())
    monkeypatch.undo()
    assert f"removed {MEMORY_README}, which this release no longer ships" in done.notes
    assert (
        "common/memory/_README.md cannot be written: Permission denied; "
        "`stayfixed overlay upgrade` writes it"
    ) in done.notes
    assert any("pre-commit" in note for note in done.notes), done.notes
    assert not path.exists()
    recorded = json.loads((root / MANIFEST_PATH).read_text(encoding="utf-8"))["artifacts"]
    assert MEMORY_README not in recorded


def test_init_keeps_an_edited_memory_readme_and_says_what_to_do(tmp_path: Path) -> None:
    # Bytes that are not the shipped ones may be the owner's own words, so `init` leaves the file
    # and its note carries the way out. Mutation: `mutations/`'s "overlay init leaves the
    # memory README a release shipped", which drops the note with the removal; the engine's
    # verdict itself is "a retired overlay file with no ledger is removed whatever it holds",
    # proven through `upgrade`.
    root = _an_overlay(tmp_path)
    edited = SHIPPED_MEMORY_README + "\nMy own line.\n"
    path = _with_the_shipped_memory_readme(root, ledger=False, text=edited)
    done = init_instance(root, "octo", runner=Recorder())
    assert path.read_text(encoding="utf-8") == edited
    assert any(MEMORY_README in note and "_README.md" in note for note in done.notes)


# --- the template's own `attach` skill, and the README of a directory nothing read --------------

# Every copy a release shipped of the two files, whole, taken from `git show <tag>:<path>` under
# `src/stayfixed/templates/overlay/` and held here for the reason `SHIPPED_MEMORY_README` is: the
# digests `overlay upgrade` removes these files by are checked against the files they name rather
# than against themselves. The skill is the same bytes in 0.1.0, 0.1.1 and 0.2.0; the README
# changed once, in 0.2.0, to say that nothing read its directory.
SHIPPED_ATTACH_SKILL = (
    "---\n"
    "name: attach\n"
    "description: Bind a repository to this private overlay and link its note store in. Use when a "
    "session reports that a repository is not attached, or when the user asks to attach a clone to "
    "their overlay.\n"
    "---\n"
    "\n"
    "# Attaching a repository to this overlay\n"
    "\n"
    "1. Find the project's name — the `[project] name` in its `stayfixed.toml` — and check that\n"
    "   `projects/<name>/` exists here. If it does not, this repository has not been bound yet "
    "and\n"
    "   the directory is created by the command below.\n"
    "2. Run `stayfixed attach --store PATH --check` first, where `PATH` is this overlay's own\n"
    "   `projects/<name>/memory`. It reports whether the record binds this repository's remote "
    "and\n"
    "   what permissions would change, and writes nothing. That path is the only one accepted;\n"
    "   anything else is refused.\n"
    "3. Relay that diff and wait for an answer. The command refuses to widen a permission without\n"
    "   `--yes`, so this step is how a person comes to give it rather than what stands in for it.\n"
    "   Once they agree, run the same command with `--yes` instead of `--check`, and relay what "
    "it\n"
    "   wrote.\n"
    "4. Personal rules, notes and permissions live here and nowhere else. Never copy one into the\n"
    "   project repository, and never widen a permission on the user's behalf.\n"
)

SHIPPED_RULES_README_0_1 = (
    "# Personal standing rules\n"
    "\n"
    "One Markdown file per rule. These are yours: they hold across every project you work on, and\n"
    "they reach a session at its start rather than being looked up, because by the time a rule\n"
    "would be looked up the decision it governs has already been made.\n"
    "\n"
    "Rank a rule by giving it `startup` in its metadata. Ranked rules are injected first and are\n"
    "the ones worth a session's attention budget; everything else waits to be asked for.\n"
    "\n"
    'Write a rule as an instruction, not as the story of the day you learned it. "Ask before\n'
    'rewriting a migration" is a rule; "remember the incident in March" is a memory. If a rule '
    "is\n"
    "about one project only, it belongs in that project's directory under `projects/`, not here.\n"
)

SHIPPED_RULES_README_0_2 = (
    "# Personal standing rules\n"
    "\n"
    "Nothing reads this directory yet. It is here because the layout reserves it, and a file you "
    "put\n"
    "here reaches no session.\n"
    "\n"
    "A personal standing rule is a note in `common/memory/` that carries `metadata.startup`, the\n"
    "rank it is injected at:\n"
    "\n"
    "```\n"
    "---\n"
    "name: ask-before-rewriting-a-migration\n"
    "description: one line saying what the rule is for\n"
    "metadata:\n"
    "  type: feedback\n"
    "  startup: 1\n"
    "---\n"
    "\n"
    "Ask before rewriting a migration.\n"
    "```\n"
    "\n"
    "`stayfixed memory session-context --bundle standing-rules` injects every such note in full at "
    "the\n"
    "start of a session, lowest `startup` first, ahead of everything that is only looked up. The "
    "rank\n"
    "is what makes a rule worth a session's attention budget.\n"
    "\n"
    'Write a rule as an instruction, not as the story of the day you learned it. "Ask before\n'
    'rewriting a migration" is a rule; "remember the incident in March" is a memory. If a rule '
    "is\n"
    "about one project only, it belongs in that project's `projects/<name>/memory/`, not here.\n"
)
ATTACH_SKILL = "skills/attach/SKILL.md"
RULES_README = "common/rules/README.md"
RELEASED_COPIES = [
    pytest.param(ATTACH_SKILL, SHIPPED_ATTACH_SKILL, "0.2.0", id="attach-skill"),
    pytest.param(RULES_README, SHIPPED_RULES_README_0_1, "0.1.1", id="rules-readme-v0.1"),
    pytest.param(RULES_README, SHIPPED_RULES_README_0_2, "0.2.0", id="rules-readme-v0.2.0"),
]


@pytest.mark.parametrize("ledger", [True, False], ids=["recorded", "no-ledger"])
@pytest.mark.parametrize(("relative", "shipped", "version"), RELEASED_COPIES)
@pytest.mark.parametrize("command", ["upgrade", "init"])
def test_each_released_copy_of_a_retired_file_is_removed(
    tmp_path: Path, command: str, relative: str, shipped: str, version: str, ledger: bool
) -> None:
    # The template shipped its own copy of the `attach` skill, a subset of the plugin's, which
    # also covers detaching and a moved remote; and a README for `common/rules/`, a directory
    # nothing read. Every overlay up to 0.2.0 carries both: recorded in the ledger where `--local`
    # rendered it, unrecorded where a template generated it, and there the bytes a release
    # shipped are the only evidence that a copy is stayfixed's. `overlay upgrade` removes them,
    # and so does `overlay init`, the step a generated overlay runs.
    #
    # Mutation: `mutations/`'s "the rules README 0.2.0 shipped is kept where no ledger records
    # it", which drops that digest from the ones held for the file. A recorded copy is removed
    # by its record, so only the unrecorded 0.2.0 case reddens.
    root = _an_overlay(tmp_path)
    path = _with_a_retired_file(
        root, relative, ledger=ledger, text=shipped, shipped=shipped, version=version
    )
    if command == "upgrade":
        planned = upgrade(root, dry_run=True).plan
        assert [a.target for a in planned.actions if a.verb is Verb.REMOVE] == [relative]
        # Non-vacuous: the dry run left it, and the real run takes it.
        assert path.is_file()
        upgrade(root, dry_run=False)
    else:
        done = init_instance(root, "octo", runner=Recorder())
        assert f"removed {relative}, which this release no longer ships" in done.notes
    assert not path.exists()
    manifest = root / MANIFEST_PATH
    if ledger:
        assert relative not in json.loads(manifest.read_text(encoding="utf-8"))["artifacts"]


@pytest.mark.parametrize("ledger", [True, False], ids=["recorded", "no-ledger"])
@pytest.mark.parametrize(
    ("relative", "shipped", "remedy"),
    [
        pytest.param(
            ATTACH_SKILL,
            SHIPPED_ATTACH_SKILL,
            "the plugin's own `attach` skill replaces it; delete this copy once you no longer "
            "need your edits",
            id="attach-skill",
        ),
        pytest.param(
            RULES_README,
            SHIPPED_RULES_README_0_2,
            "a standing rule is a note with `metadata.startup`, so move your rules into such "
            "notes and delete this copy",
            id="rules-readme",
        ),
    ],
)
def test_an_edited_retired_file_is_kept_and_named(
    tmp_path: Path, relative: str, shipped: str, remedy: str, ledger: bool
) -> None:
    # An owner may have written a skill of their own over the template's, or rules into the
    # README, and nothing else holds those words: a copy that is not the bytes stayfixed wrote is
    # left, by `upgrade` and by `init`, and both name it with the way out. The verdict and the
    # way out are the scaffold engine's, held by `mutations/`'s "a retired overlay file with no
    # ledger is removed whatever it holds" and "a kept retired overlay file is named without its
    # way out"; this holds that the two files reach them with a way out of their own.
    root = _an_overlay(tmp_path)
    edited = shipped + "\nMy own line.\n"
    path = _with_a_retired_file(
        root, relative, ledger=ledger, text=edited, shipped=shipped, version="0.2.0"
    )
    kept = {a.target: a for a in upgrade(root, dry_run=True).plan.actions}[relative]
    assert kept.verb is Verb.SKIP_MODIFIED
    assert remedy in kept.reason
    upgrade(root, dry_run=False)
    assert path.read_text(encoding="utf-8") == edited
    done = init_instance(root, "octo", runner=Recorder())
    assert any(note.startswith(f"left {relative}") and remedy in note for note in done.notes)
    assert path.read_text(encoding="utf-8") == edited


def test_init_prints_a_retired_file_s_recorded_path_escaped(tmp_path: Path) -> None:
    # The ledger is committed with the overlay, so the path a record names is repository-chosen:
    # one this release's retired file cannot produce is left where it is and named, and `init`
    # printed it as it stood, where a line break and an escape sequence reach the terminal and a
    # CI runner verbatim. It prints through `printed.quoted`, as a refusal names such a path.
    # Mutation (declared): the left line prints the target unescaped -> the escaped spelling is
    # missing, and the raw bytes reach the line.
    root = _an_overlay(tmp_path)
    hostile = "x\x1b[31mRED\n::error::IGNORE\x07.md"
    _with_a_retired_file(
        root,
        ATTACH_SKILL,
        ledger=True,
        text=SHIPPED_ATTACH_SKILL,
        shipped=SHIPPED_ATTACH_SKILL,
        version="0.2.0",
    )
    manifest = root / MANIFEST_PATH
    document = json.loads(manifest.read_text(encoding="utf-8"))
    document["artifacts"][ATTACH_SKILL]["target"] = hostile
    manifest.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    done = init_instance(root, "octo", runner=Recorder())
    left = [note for note in done.notes if note.startswith(f"left {hostile!r} (")]
    assert len(left) == 1, done.notes
    for note in done.notes:
        assert not any(c in note for c in "\x1b\x07\n"), note


@pytest.mark.skipif(os.geteuid() == 0, reason="root removes from a directory it cannot write")
@pytest.mark.parametrize("removable", [True, False], ids=["removed", "cannot-remove"])
def test_init_prints_a_recorded_case_variant_it_removes_or_leaves_escaped(
    tmp_path: Path, removable: bool
) -> None:
    # A record whose target case-folds to a place this release's retired file can be is acted on
    # at the target the record names, so the path `init` prints on its `removed` line, and on the
    # line naming a file it could not remove, is the ledger's own spelling. Case folding admits
    # letters outside the path grammar (`\u017f` folds to `s`), and such a path prints through
    # `printed.quoted` like any other the ledger chose.
    # Mutation (declared): each line prints the target unescaped -> its escaped spelling is
    # missing.
    root = _an_overlay(tmp_path)
    variant = ".stayfixed/local/artifacts/\u017fkills/attach/SKILL.md"
    _with_a_retired_file(
        root,
        ATTACH_SKILL,
        ledger=True,
        text=SHIPPED_ATTACH_SKILL,
        shipped=SHIPPED_ATTACH_SKILL,
        version="0.2.0",
    )
    (root / ATTACH_SKILL).unlink()
    copy = root / variant
    copy.parent.mkdir(parents=True)
    copy.write_text(SHIPPED_ATTACH_SKILL, encoding="utf-8")
    manifest = root / MANIFEST_PATH
    document = json.loads(manifest.read_text(encoding="utf-8"))
    document["artifacts"][ATTACH_SKILL]["target"] = variant
    manifest.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    if not removable:
        copy.parent.chmod(0o555)
    try:
        done = init_instance(root, "octo", runner=Recorder())
    finally:
        if not removable:
            copy.parent.chmod(0o755)
    if removable:
        assert f"removed {variant!r}, which this release no longer ships" in done.notes
        assert not copy.exists()
    else:
        assert f"left {variant!r}: cannot be removed: Permission denied" in done.notes
        assert copy.is_file()


def _retire_by(command: str, root: Path) -> None:
    if command == "upgrade":
        upgrade(root, dry_run=False)
    else:
        init_instance(root, "octo", runner=Recorder())


@pytest.mark.parametrize("command", ["upgrade", "init"])
def test_retiring_a_file_removes_the_directories_it_leaves_empty(
    tmp_path: Path, command: str
) -> None:
    # Removing the template's `attach` skill and the rules README left `skills/attach/`,
    # `skills/` and `common/rules/` behind, empty: git keeps no empty directory, so a clone never
    # saw them, but a plugin added from the overlay's own path did. Each directory above a file the
    # run removed goes once it is empty, up to the first that is not, which here is `common/`.
    # Mutation (declared): `mutations/`'s "overlay upgrade leaves the directories a retirement
    # empties" and "overlay init leaves the directories a retirement empties".
    root = _an_overlay(tmp_path)
    for relative, text in (
        (ATTACH_SKILL, SHIPPED_ATTACH_SKILL),
        (RULES_README, SHIPPED_RULES_README_0_2),
    ):
        _with_a_retired_file(root, relative, ledger=True, text=text, shipped=text, version="0.2.0")
    _retire_by(command, root)
    assert not (root / ATTACH_SKILL).exists() and not (root / RULES_README).exists()
    assert not (root / "skills").exists()
    assert not (root / "common" / "rules").exists()
    assert (root / "common" / "memory" / "_README.md").is_file()
    assert root.is_dir()


@pytest.mark.parametrize("command", ["upgrade", "init"])
def test_a_directory_holding_the_owner_s_own_file_is_left(tmp_path: Path, command: str) -> None:
    # `rmdir` refuses a directory with anything in it, which is the whole safety of the walk: a
    # file of the owner's beside the retired one keeps its directory and every one above it.
    # No mutation: what holds this is the kernel's refusal, not a line of the walk.
    root = _an_overlay(tmp_path)
    _with_a_retired_file(
        root,
        ATTACH_SKILL,
        ledger=True,
        text=SHIPPED_ATTACH_SKILL,
        shipped=SHIPPED_ATTACH_SKILL,
        version="0.2.0",
    )
    mine = root / "skills" / "attach" / "notes.md"
    mine.write_text("mine\n", encoding="utf-8")
    _retire_by(command, root)
    assert not (root / ATTACH_SKILL).exists()
    assert mine.read_text(encoding="utf-8") == "mine\n"


@pytest.mark.parametrize("command", ["upgrade", "init"])
def test_an_empty_directory_no_file_was_removed_from_is_left(tmp_path: Path, command: str) -> None:
    # A record whose file is already gone is still a removal the engine plans, one that unlinks
    # nothing. The directories above it held no file of stayfixed's when the run began, so
    # emptying them is not this run's doing: a person may have made them, and they stay.
    # Mutation (declared): `mutations/`'s "overlay upgrade prunes above a file that was not there"
    # and "overlay init prunes above a file that was not there".
    root = _an_overlay(tmp_path)
    old = ".stayfixed/local/artifacts/skills/attach/SKILL.md"
    _with_a_retired_file(
        root,
        ATTACH_SKILL,
        ledger=True,
        text=SHIPPED_ATTACH_SKILL,
        shipped=SHIPPED_ATTACH_SKILL,
        version="0.2.0",
    )
    (root / ATTACH_SKILL).unlink()
    manifest = root / MANIFEST_PATH
    document = json.loads(manifest.read_text(encoding="utf-8"))
    document["artifacts"][ATTACH_SKILL]["target"] = old
    manifest.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    made = (root / old).parent
    made.mkdir(parents=True)
    planned = upgrade(root, dry_run=True).plan
    assert [a.target for a in planned.actions if a.verb is Verb.REMOVE] == [old]
    _retire_by(command, root)
    assert made.is_dir()


def test_an_overlay_without_the_retired_files_plans_nothing(tmp_path: Path) -> None:
    # A fresh overlay carries neither file, and an overlay an upgrade has cleared of them has
    # nothing left to remove: run again, `overlay upgrade` plans no action and `overlay init`
    # names no file it removed or left. Mutation (declared): `mutations/`'s "a retired overlay
    # file that is absent is planned for removal" -> the first plan's assertion reddens. The
    # engine's removal and record-dropping paths are the set's other retirement entries.
    root = _an_overlay(tmp_path)
    for relative in (ATTACH_SKILL, RULES_README):
        assert not (root / relative).exists(), relative
    assert upgrade(root, dry_run=True).plan.actions == ()
    _with_a_retired_file(
        root,
        ATTACH_SKILL,
        ledger=True,
        text=SHIPPED_ATTACH_SKILL,
        shipped=SHIPPED_ATTACH_SKILL,
        version="0.2.0",
    )
    _with_a_retired_file(
        root,
        RULES_README,
        ledger=True,
        text=SHIPPED_RULES_README_0_2,
        shipped=SHIPPED_RULES_README_0_2,
        version="0.2.0",
    )
    upgrade(root, dry_run=False)
    assert upgrade(root, dry_run=True).plan.actions == ()
    done = init_instance(root, "octo", runner=Recorder())
    assert not [note for note in done.notes if note.startswith(("removed ", "left "))], done.notes
