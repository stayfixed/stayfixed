"""What `stayfixed attach` writes, and the three refusals it owes before it writes anything.

The third of the rules that keep the overlay trusted is here: a write that would widen a permission
refuses without an explicit confirmation. It is a parameter and a `Refusal` rather than a step in a
document, because in this harness the CLI is driven by a model that has read the repository, and a
gate enforced by model compliance is not a gate.
"""

from __future__ import annotations

import json
import os
import shutil
from collections.abc import Mapping
from pathlib import Path

import pytest

from stayfixed import fsops
from stayfixed.attach.api import ledger
from stayfixed.attach.permissions import settings_document
from stayfixed.attach.write import (
    GROUP_ESCAPES,
    HARNESS_WAITS,
    REAL_DIRECTORIES,
    Attached,
    attach,
)
from stayfixed.errors import Failure, Refusal
from stayfixed.memory.api import PROJECT_RECORD
from stayfixed.overlay.api import COMMON_CLAUDE, COMMON_CODEX
from stayfixed.scaffold import EntriesError, Style, drop, extract, owned_ids

# The fixture the binding tests already build, reused rather than copied: one spelling of the
# overlay layout keeps the two modules from drifting apart about what `--store` names.
from tests.attach.test_binding import DEFAULT_MEMORY, _machine, _project_and_store
from tests.gitfixture import git as _git
from tests.gitfixture import run_git
from tests.runners import Recorder

# The walk-based snapshot guard, owned at the top level rather than duplicated here and in
# tests/test_install_path.py: it used to exist twice, verbatim including its docstring, and the
# two copies drifted apart on the one thing that mattered — how much of `.git` to trust.
from tests.snapshot import assert_snapshot_unchanged, snapshot

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")

LEDGER = ".stayfixed/local/attach.json"
SETTINGS = ".claude/settings.local.json"
RULE = "Bash(uv run pytest:*)"
ENTRY = {"type": "command", "command": "echo hello"}


def _overlay_repository(overlay: Path, *, hooks_path: Path | None = None) -> Path:
    """The overlay as what it actually is — a git repository — and where its hooks live.

    `attach` asks `guards.hooks_dir` rather than assuming `.git/hooks`, so the fixture has to
    be a repository for the question to have an answer. `hooks_path` sets `core.hooksPath`,
    which is an ordinary global dotfiles setting and the arrangement the hardcoded path got
    wrong: the scan reads as missing on every attach and `pre-commit install` is shelled out to
    every time.
    """
    _git(overlay, "init", "-q", "-b", "main")
    if hooks_path is None:
        # Pinned LOCALLY, and this is not belt-and-braces. `hooks_dir` runs `git` under
        # `gitenv.scrubbed_env()`, which keeps `HOME` deliberately — honouring the machine
        # owner's global `core.hooksPath` is exactly what `attach` asks for — so a
        # developer whose own `~/.gitconfig` sets one would have this fixture answer *their*
        # directory and the case fail for a reason that is nothing to do with the code. `_git`
        # pins only `GIT_CONFIG_GLOBAL`, which the separate `hooks_dir` subprocess never sees.
        # Local config outranks global, so the fixture says what it means and production is
        # untouched.
        own = overlay / ".git" / "hooks"
        _git(overlay, "config", "core.hooksPath", str(own))
        return own
    hooks_path.mkdir(parents=True, exist_ok=True)
    _git(overlay, "config", "core.hooksPath", str(hooks_path))
    return hooks_path


def _overlay_grants(
    store: Path,
    *,
    allow: tuple[str, ...] = (),
    hooks: Mapping[str, object] | None = None,
    codex: str | None = None,
) -> Path:
    overlay = store.parents[2]
    (overlay / COMMON_CLAUDE / "permissions.json").write_text(
        json.dumps({"permissions": {"allow": list(allow), "deny": []}}), encoding="utf-8"
    )
    (overlay / COMMON_CLAUDE / "hooks.json").write_text(
        json.dumps({"hooks": dict(hooks or {})}), encoding="utf-8"
    )
    if codex is not None:
        (overlay / COMMON_CODEX / "common.rules").write_text(codex, encoding="utf-8")
    return overlay


def _attachable(
    tmp_path: Path,
    *,
    recorded: str | None = None,
    origin: str = "git@example.com:o/p.git",
    allow: tuple[str, ...] = (),
    hooks: Mapping[str, object] | None = None,
    codex: str | None = None,
) -> tuple[Path, Path, Path]:
    root, store = _project_and_store(tmp_path, recorded=recorded, origin=origin)
    _overlay_grants(store, allow=allow, hooks=hooks, codex=codex)
    return root, store, _machine(tmp_path, overlay=store.parents[2])


def _check_ignore(root: Path, relative: str) -> bool:
    # `run_git` and not `git`: `check-ignore` answers 1 for "nothing matched", which is an
    # answer and not a failure — the same distinction `stayfixed.gitenv.git_run` makes.
    return run_git(root, "check-ignore", "-q", "--", relative).returncode == 0


def test_a_mismatched_remote_refuses_and_writes_nothing(tmp_path: Path) -> None:
    # On a mismatch `attach` refuses unless --trust-remote is given interactively. The assertion
    # that matters is the second half: snapshot every file under the root before, expect `Refusal`,
    # and compare the snapshot after. Not one byte changed.
    root, store, machine = _attachable(tmp_path, recorded="git@example.com:o/real.git")
    before = snapshot(root)
    # The mutation guard for the assertion below, and the rule that asks for it — an assertion
    # nobody has watched fail advertises coverage it may not have (principle 2): `snapshot` is a
    # walk, so `snapshot(root) == before` passes vacuously the day the walk stops finding files —
    # and this is a test standing behind a refusal.
    assert before
    with pytest.raises(Refusal):
        attach(
            root,
            store=store,
            machine=machine,
            confirmed=True,
            trust_remote=False,
            runner=Recorder(),
            home=tmp_path / "home",
        )
    assert_snapshot_unchanged(root, before)


def test_the_same_repository_under_another_url_form_is_refused_in_words_true_of_it(
    tmp_path: Path,
) -> None:
    # URLs are compared exactly, so an owner who re-cloned over https a repository the overlay
    # recorded over ssh is refused as a mismatch -- and was told "this is not the repository it
    # was bound to", which is false for the same repository. The sentence now says what the check
    # knows: a different remote URL, which the same repository in another form also is. The way
    # out is unchanged: `--trust-remote` rebinds it.
    #
    # Mutation: none; the refusal's wording is the assertion, and the rebind is the existing
    # `--trust-remote` path. The old sentence reddens it.
    root, store, machine = _attachable(
        tmp_path,
        recorded="https://example.com/o/p.git",
        origin="git@example.com:o/p.git",
    )
    before = snapshot(root)
    assert before
    with pytest.raises(Refusal) as refused:
        attach(
            root,
            store=store,
            machine=machine,
            confirmed=True,
            trust_remote=False,
            runner=Recorder(),
            home=tmp_path / "home",
        )
    said = str(refused.value)
    assert "not the repository" not in said
    assert "different remote URL" in said and "another URL form" in said
    assert "--trust-remote" in said
    assert_snapshot_unchanged(root, before)
    attached = attach(
        root,
        store=store,
        machine=machine,
        confirmed=True,
        trust_remote=True,
        runner=Recorder(),
        home=tmp_path / "home",
    )
    assert attached.binding_recorded


def test_an_unconfirmed_attach_that_would_widen_a_permission_refuses(tmp_path: Path) -> None:
    # The write gate, and the defect that produced it. `attach` writes `settings.local.json` only
    # after a printed diff and an explicit confirmation, and an earlier revision implemented that
    # rule with nothing at all: the only mechanism was a Markdown step telling a model to run
    # `--check` first. A repository that says "setup requires
    # `stayfixed attach --store <path it names>`" gets a compliant agent to grant it tool
    # permissions, and no human sees the diff.
    root, store, machine = _attachable(tmp_path, allow=(RULE,))
    with pytest.raises(Refusal):
        attach(
            root,
            store=store,
            machine=machine,
            confirmed=False,
            trust_remote=False,
            runner=Recorder(),
            home=tmp_path / "home",
        )
    assert not (root / SETTINGS).exists()


def test_an_attach_that_widens_nothing_needs_no_confirmation(tmp_path: Path) -> None:
    # The gate is on the capability, not on the command. An overlay with no allow rules and no
    # hooks — the state of a freshly created one — must still attach without a flag, or the
    # flag becomes something people pass reflexively.
    root, store, machine = _attachable(tmp_path)
    attached = attach(
        root,
        store=store,
        machine=machine,
        confirmed=False,
        trust_remote=False,
        runner=Recorder(),
        home=tmp_path / "home",
    )
    assert attached.binding_recorded
    assert not attached.settings_written
    assert (root / LEDGER).is_file()


def test_confirmed_merges_the_rules_and_records_each_entry_under_its_own_id(
    tmp_path: Path,
) -> None:
    # `owned_ids` is keyed by id, so one shared id for N entries yields one provenance row and
    # the same id under two events silently keeps the last. Assert `owned_ids(document)` has
    # one entry per merged hook.
    hooks = {
        "SessionStart": [{"hooks": [ENTRY, {"type": "command", "command": "echo two"}]}],
        "PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "echo t"}]}],
    }
    root, store, machine = _attachable(tmp_path, allow=(RULE,), hooks=hooks)
    attach(
        root,
        store=store,
        machine=machine,
        confirmed=True,
        trust_remote=False,
        runner=Recorder(),
        home=tmp_path / "home",
    )
    document = (root / SETTINGS).read_text(encoding="utf-8")
    claimed = owned_ids(document)
    assert len(claimed) == 3, claimed
    assert set(claimed.values()) == {"SessionStart", "PreToolUse"}
    assert json.loads(document)["permissions"]["allow"] == [RULE]


def test_an_entry_the_overlay_stopped_granting_is_taken_back_out(tmp_path: Path) -> None:
    # Walked end to end: the overlay grants a hook entry, `attach` installs it, the owner
    # deletes it from the overlay, `attach` runs again. The second run adds nothing — no allow
    # rule, no wanted entry — so it used to return the document untouched, leaving a marked
    # entry that still FIRES while the ledger (rebuilt from the overlay) forgot it. `doctor`
    # then reads an entry claiming the marker and named in no ledger, goes red, and tells the
    # owner to remove an entry stayfixed installed: a false red with actively wrong advice.
    #
    # `apply_entries(document, {})` is the engine's removal path and is what now runs.
    hooks = {"SessionStart": [{"hooks": [ENTRY]}]}
    root, store, machine = _attachable(tmp_path, hooks=hooks)
    home = tmp_path / "home"
    attach(
        root,
        store=store,
        machine=machine,
        confirmed=True,
        trust_remote=False,
        runner=Recorder(),
        home=home,
    )
    installed = owned_ids((root / SETTINGS).read_text(encoding="utf-8"))
    # Non-vacuous: the sequence is only about a second run if the first one installed something.
    assert installed
    assert set(ledger(root).entries) == set(installed)

    _overlay_grants(store)  # the owner takes the entry out of the overlay
    attached = attach(
        root,
        store=store,
        machine=machine,
        confirmed=True,
        trust_remote=False,
        runner=Recorder(),
        home=home,
    )
    assert attached.settings_written
    assert owned_ids((root / SETTINGS).read_text(encoding="utf-8")) == {}
    assert ledger(root).entries == {}


def test_a_second_attach_that_changes_nothing_leaves_the_settings_file_alone(
    tmp_path: Path,
) -> None:
    # The guard for the clause above: `owned_ids` widened the early return, and a widening that
    # went too far would reformat a file the owner owns on every run and report itself as a
    # write. An overlay that grants nothing and a project that was never attached still touch
    # nothing.
    root, store, machine = _attachable(tmp_path)
    attached = attach(
        root,
        store=store,
        machine=machine,
        confirmed=False,
        trust_remote=False,
        runner=Recorder(),
        home=tmp_path / "home",
    )
    assert not attached.settings_written
    assert not (root / SETTINGS).exists()


def test_a_group_mixing_a_marked_entry_with_a_foreign_one_is_split_not_replaced(
    tmp_path: Path,
) -> None:
    # Inherited from `scaffold.apply_entries` rather than re-implemented, and asserted here
    # because this is the command whose mistake would delete a developer's own hook.
    hooks = {"SessionStart": [{"hooks": [ENTRY]}]}
    root, store, machine = _attachable(tmp_path, hooks=hooks)
    (root / ".claude").mkdir()
    (root / SETTINGS).write_text(
        json.dumps(
            {
                "hooks": {
                    "SessionStart": [
                        {
                            "hooks": [
                                {"type": "command", "command": "mine.sh"},
                                {
                                    "type": "command",
                                    "command": "stale.sh  # stayfixed:overlay-SessionStart-1",
                                },
                            ]
                        }
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    attach(
        root,
        store=store,
        machine=machine,
        confirmed=True,
        trust_remote=False,
        runner=Recorder(),
        home=tmp_path / "home",
    )
    document = (root / SETTINGS).read_text(encoding="utf-8")
    commands = [
        entry["command"]
        for group in json.loads(document)["hooks"]["SessionStart"]
        for entry in group["hooks"]
    ]
    assert "mine.sh" in commands
    assert "stale.sh  # stayfixed:overlay-SessionStart-1" not in commands
    assert "echo hello  # stayfixed:overlay-SessionStart-1" in commands


def test_a_first_attach_records_the_remote_and_the_date(tmp_path: Path) -> None:
    # projects/<name>/project.toml holds the bound remote URL and the first-attach date.
    import datetime
    import tomllib

    root, store, machine = _attachable(tmp_path)
    attach(
        root,
        store=store,
        machine=machine,
        confirmed=False,
        trust_remote=False,
        runner=Recorder(),
        home=tmp_path / "home",
    )
    record = tomllib.loads((store.parent / "project.toml").read_text(encoding="utf-8"))
    assert record["remote"] == "git@example.com:o/p.git"
    assert datetime.date.fromisoformat(str(record["first_attach"]))


def test_a_record_that_already_binds_this_repository_is_left_alone(tmp_path: Path) -> None:
    # The record is the owner's consent, and its date is when they gave it. Rewriting it on
    # every attach turns a fact into a timestamp of the last run — so a repository the overlay
    # already records correctly is not written at all.
    import tomllib

    root, store, machine = _attachable(tmp_path)
    runner = Recorder()
    attach(
        root,
        store=store,
        machine=machine,
        confirmed=False,
        trust_remote=False,
        runner=runner,
        home=tmp_path / "home",
    )
    record = store.parent / "project.toml"
    first = tomllib.loads(record.read_text(encoding="utf-8"))["first_attach"]
    record.write_text(
        record.read_text(encoding="utf-8").replace(str(first), "2000-01-01"), encoding="utf-8"
    )
    attach(
        root,
        store=store,
        machine=machine,
        confirmed=False,
        trust_remote=False,
        runner=runner,
        home=tmp_path / "home",
    )
    assert tomllib.loads(record.read_text(encoding="utf-8"))["first_attach"] == "2000-01-01"


def test_the_merged_rules_are_recorded_where_they_can_be_removed_again(tmp_path: Path) -> None:
    # The ledger lives under .stayfixed/local/, because the committed manifest would
    # publish a digest of the owner's personal allow rules to collaborators.
    hooks = {"SessionStart": [{"hooks": [ENTRY]}]}
    root, store, machine = _attachable(tmp_path, allow=(RULE,), hooks=hooks)
    attach(
        root,
        store=store,
        machine=machine,
        confirmed=True,
        trust_remote=False,
        runner=Recorder(),
        home=tmp_path / "home",
    )
    recorded = ledger(root)
    assert recorded.allow == (RULE,)
    assert recorded.entries == {"overlay-SessionStart-1": "SessionStart"}
    assert (root / LEDGER).is_file()


def test_attach_writes_the_ignore_region_that_keeps_the_ledger_untracked(tmp_path: Path) -> None:
    # The repository has no `.stayfixed` line today and nothing under `templates/project/` ships
    # one, so an earlier revision's confidentiality argument rested on a file that does not exist.
    # Assert the region exists after attach, and assert
    # `git check-ignore -q .stayfixed/local/attach.json` succeeds — not that nothing is tracked,
    # which passes on a fixture that has committed nothing.
    root, store, machine = _attachable(tmp_path)
    assert not _check_ignore(root, LEDGER)
    attach(
        root,
        store=store,
        machine=machine,
        confirmed=False,
        trust_remote=False,
        runner=Recorder(),
        home=tmp_path / "home",
    )
    body = extract((root / ".gitignore").read_text(encoding="utf-8"), "ignore", Style.HASH)
    assert body is not None and ".stayfixed/local/" in body
    assert _check_ignore(root, LEDGER)


def test_the_ignore_region_is_written_before_the_ledger_and_not_merely_written(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The two tests around this one assert the region *exists* afterwards, which is a different
    # question from the one `attach`'s own comment states: the ledger holds the owner's personal
    # allow rules and lives under a path the repository has no `.gitignore` line for, so a ledger
    # written first is a ledger `git add -A` publishes to every collaborator in the window before
    # the region lands. The one entry it had replaced the call with `pass`, which is what
    # `mutations/`'s "the ignore region is never written at all" still does, so both named tests
    # reddened against absence and nothing anywhere reddened against order.
    #
    # The order of the writes themselves, recorded at `fsops.write_within` — the one primitive
    # every write in this module goes through — rather than inferred from the tree afterwards,
    # because the tree afterwards is identical either way.
    #
    # Mutation: `mutations/`'s "the ignore region is written after the ledger it untracks".
    root, store, machine = _attachable(tmp_path)
    written: list[str] = []
    real = fsops.write_within

    def record(base: Path, relative: str, text: str, *, encoding: str = "utf-8") -> None:
        if base == root:
            written.append(relative)
        real(base, relative, text, encoding=encoding)

    monkeypatch.setattr(fsops, "write_within", record)
    attach(
        root,
        store=store,
        machine=machine,
        confirmed=False,
        trust_remote=False,
        runner=Recorder(),
        home=tmp_path / "home",
    )
    assert ".gitignore" in written and LEDGER in written, written
    assert written.index(".gitignore") < written.index(LEDGER), written


def test_attach_leaves_every_other_line_of_an_existing_gitignore_alone(tmp_path: Path) -> None:
    # The whole point of a managed region, and the reason this does not need the scaffold engine's
    # manifest: everything outside the two markers comes back out as it went in.
    root, store, machine = _attachable(tmp_path)
    (root / ".gitignore").write_text("node_modules/\n", encoding="utf-8")
    attach(
        root,
        store=store,
        machine=machine,
        confirmed=False,
        trust_remote=False,
        runner=Recorder(),
        home=tmp_path / "home",
    )
    assert "node_modules/\n" in (root / ".gitignore").read_text(encoding="utf-8")


def test_attach_refuses_when_the_ignore_region_cannot_be_written(tmp_path: Path) -> None:
    # The other half: if the ledger cannot be made untracked, writing it is a leak, and the
    # right answer is to refuse rather than to warn.
    root, store, machine = _attachable(tmp_path)
    (root / ".gitignore").mkdir()
    with pytest.raises(Refusal):
        attach(
            root,
            store=store,
            machine=machine,
            confirmed=False,
            trust_remote=False,
            runner=Recorder(),
            home=tmp_path / "home",
        )
    assert not (root / LEDGER).exists()


def _with_groups(root: Path, listed: str) -> None:
    text = (root / "stayfixed.toml").read_text(encoding="utf-8")
    (root / "stayfixed.toml").write_text(
        text.replace('groups = ["developer", "project-stable"]', f"groups = {listed}"),
        encoding="utf-8",
    )


def test_a_memory_group_that_leaves_the_projects_share_is_refused_not_created(
    tmp_path: Path,
) -> None:
    # `memory.groups` is repository-authored (principle 5) and reaches no guard of its own —
    # `config/paths.py` says so in as many words, and leaves the containment to the module that
    # consumes the field. The entry decides a directory created inside the OVERLAY, which is the
    # one tree `attach` trusts, so a `..` in it is refused rather than created, and refused rather
    # than crashing out as a raw `OSError`.
    #
    # **And refused before the first write**, which is the half this case was missing. The
    # containment was called from `_prepare_store`, which runs after the ignore region, the
    # `.codex/rules/` copies, the settings merge, the ledger *and* the overlay's binding record
    # — so a clone committing the entry below got five artifacts written and exit 2, and
    # `doctor._attached` then reported the repository attached and the binding **bound**,
    # because the record had been written too. The overlay is left out of the snapshot on
    # purpose: the binding record lives there, and asserting on the repository is what the
    # separate assertion below the snapshot is for.
    #
    # Mutation: `mutations/`'s "the memory.groups containment is asked at write time only".
    root, store, machine = _attachable(tmp_path, allow=(RULE,), codex="# a standing rule\n")
    _with_groups(root, '["../../escape"]')
    before = snapshot(root)
    # `snapshot` is a walk, and an empty one satisfies the comparison below on its own.
    assert before
    with pytest.raises(Refusal) as refusal:
        attach(
            root,
            store=store,
            machine=machine,
            confirmed=True,
            trust_remote=True,
            runner=Recorder(),
            home=tmp_path / "home",
        )
    # Non-vacuous: this refusal and not one of the five `attach` can raise before it, nor the
    # one below it. `unlinked_groups` refuses the same entry with `MEMORY_GROUP_ESCAPES` --
    # deliberately a different sentence, because it contains the group against `root` rather
    # than against the overlay -- so "memory.groups is in the message" no longer says which of
    # the two fired. The identity does, and it is what keeps the hoisted call proven: without
    # it this case passed with `_check_groups` deleted, on the never-moved check's refusal.
    # (`GROUP_ESCAPES` names `memory.groups`, which is what a reader needs from it; asserting
    # that here would be an assertion about a literal that no behaviour change can redden.)
    assert str(refusal.value) == GROUP_ESCAPES
    # The entry itself is repository-authored, so it is not quoted back.
    assert "../../escape" not in str(refusal.value)
    assert not (store.parents[2].parent / "escape").exists()
    assert_snapshot_unchanged(root, before)
    # The one write that is not under the root, and the one that made `doctor` say `bound`.
    assert not (store.parent / PROJECT_RECORD).exists()


def test_the_memory_group_refusal_is_reached_on_a_run_that_would_have_written(
    tmp_path: Path,
) -> None:
    # The vacuity guard for the snapshot above, and the same one the no-origin refusal and the
    # ledger refusal carry: a refusal that writes nothing proves nothing if the run had nothing to
    # write. The identical fixture with a group name that stays inside this project's share
    # attaches, and leaves behind every artifact the case above has to prevent.
    root, store, machine = _attachable(tmp_path, allow=(RULE,), codex="# a standing rule\n")
    _with_groups(root, '["developer", "project-stable"]')
    before = snapshot(root)
    assert before
    attached = attach(
        root,
        store=store,
        machine=machine,
        confirmed=True,
        trust_remote=True,
        runner=Recorder(),
        home=tmp_path / "home",
    )
    after = snapshot(root)
    added = set(after) - set(before)
    assert attached.settings_written and attached.binding_recorded
    assert {LEDGER, SETTINGS, ".codex/rules/common.rules"} <= added
    assert before.get(".gitignore") != after.get(".gitignore")
    assert (store.parent / PROJECT_RECORD).is_file()
    assert (store / "project-stable").is_dir()


def test_a_second_attach_adds_nothing_twice(tmp_path: Path) -> None:
    # `attach` is idempotent and reversible by `detach`. A permission list that grows by one copy of
    # every rule per attach is the shape this catches.
    hooks = {"SessionStart": [{"hooks": [ENTRY]}]}
    root, store, machine = _attachable(tmp_path, allow=(RULE,), hooks=hooks)
    runner = Recorder()
    attach(
        root,
        store=store,
        machine=machine,
        confirmed=True,
        trust_remote=False,
        runner=runner,
        home=tmp_path / "home",
    )
    attach(
        root,
        store=store,
        machine=machine,
        confirmed=True,
        trust_remote=False,
        runner=runner,
        home=tmp_path / "home",
    )
    document = json.loads((root / SETTINGS).read_text(encoding="utf-8"))
    assert document["permissions"]["allow"] == [RULE]
    assert len(document["hooks"]["SessionStart"]) == 1
    assert ledger(root).allow == (RULE,)


def test_a_second_attach_still_claims_what_the_first_one_added(tmp_path: Path) -> None:
    # The idempotence above is what makes this possible to get wrong: on the second run the
    # rule is already present, so the *diff* is empty — and a ledger written from the diff
    # alone would forget it, leaving `detach` nothing to remove.
    root, store, machine = _attachable(tmp_path, allow=(RULE,))
    runner = Recorder()
    attach(
        root,
        store=store,
        machine=machine,
        confirmed=True,
        trust_remote=False,
        runner=runner,
        home=tmp_path / "home",
    )
    attach(
        root,
        store=store,
        machine=machine,
        confirmed=True,
        trust_remote=False,
        runner=runner,
        home=tmp_path / "home",
    )
    assert ledger(root).allow == (RULE,)


def test_codex_rules_land_under_the_directory_codex_reads(tmp_path: Path) -> None:
    # `attach` places Codex rules under .codex/rules/. Kept separate from the Claude settings merge
    # because the two harnesses fail differently and a shared path would hide which.
    root, store, machine = _attachable(tmp_path, codex="# standing rule\n")
    attached = attach(
        root,
        store=store,
        machine=machine,
        confirmed=False,
        trust_remote=False,
        runner=Recorder(),
        home=tmp_path / "home",
    )
    landed = root / ".codex" / "rules" / "common.rules"
    assert landed.read_text(encoding="utf-8") == "# standing rule\n"
    assert ".codex/rules/common.rules" in attached.rules_written
    assert ledger(root).rules == (".codex/rules/common.rules",)


def test_a_rule_the_overlay_never_granted_is_left_alone(tmp_path: Path) -> None:
    # `doctor` lists every rule with its provenance, so one no overlay granted is visible. attach's
    # own contribution to that is narrower and stricter: it does not touch one.
    root, store, machine = _attachable(tmp_path, allow=(RULE,))
    (root / ".claude").mkdir()
    (root / SETTINGS).write_text(
        json.dumps({"permissions": {"allow": ["Bash(rm:*)"]}}), encoding="utf-8"
    )
    attach(
        root,
        store=store,
        machine=machine,
        confirmed=True,
        trust_remote=False,
        runner=Recorder(),
        home=tmp_path / "home",
    )
    allow = json.loads((root / SETTINGS).read_text(encoding="utf-8"))["permissions"]["allow"]
    assert allow == ["Bash(rm:*)", RULE]
    assert ledger(root).allow == (RULE,)


def test_the_secret_scan_is_installed_on_the_machine_that_never_ran_overlay_init(
    tmp_path: Path,
) -> None:
    # `attach` runs `pre-commit install` in the overlay if it is missing, and `overlay init` only
    # covers the first machine: a second one clones an overlay initialised elsewhere and never runs
    # `overlay init` again. Doing it twice is free; not doing it at all leaves the commit-time
    # secret scan unarmed on exactly the machine that thinks it is set up.
    root, store, machine = _attachable(tmp_path)
    _overlay_repository(store.parents[2])
    (store.parents[2] / ".pre-commit-config.yaml").write_text("repos: []\n", encoding="utf-8")
    runner = Recorder()
    attached = attach(
        root,
        store=store,
        machine=machine,
        confirmed=False,
        trust_remote=False,
        runner=runner,
        home=tmp_path / "home",
    )
    assert ["pre-commit", "install"] in runner.calls
    assert any("pre-commit" in note for note in attached.notes)


def test_trust_remote_rebinds_and_keeps_the_original_first_attach_date(tmp_path: Path) -> None:
    # The only path that rewrites an existing record, and the reason the date is read back
    # rather than re-stamped: `first_attach` is when the owner first consented, not when they
    # last ran the command.
    import tomllib

    root, store, machine = _attachable(tmp_path, recorded="git@example.com:o/real.git")
    (store.parent / "project.toml").write_text(
        'remote = "git@example.com:o/real.git"\nfirst_attach = "2020-02-02"\n', encoding="utf-8"
    )
    attached = attach(
        root,
        store=store,
        machine=machine,
        confirmed=False,
        trust_remote=True,
        runner=Recorder(),
        home=tmp_path / "home",
    )
    assert attached.binding_recorded
    record = tomllib.loads((store.parent / "project.toml").read_text(encoding="utf-8"))
    assert record["remote"] == "git@example.com:o/p.git"
    assert record["first_attach"] == "2020-02-02"


def test_a_repository_with_no_origin_remote_has_nothing_to_record(tmp_path: Path) -> None:
    # An empty `remote` in the overlay's record would read as bound to nothing, and
    # `memory.store._bound` would then refuse every session with advice to run this command.
    #
    # **The snapshot is the half that was missing**, and it is the same snapshot
    # `test_a_mismatched_remote_refuses_and_writes_nothing` takes for the same reason. Asserting
    # only that `Refusal` is raised passed while the refusal lived in `_record_binding` — after
    # the ignore region, the `.codex/rules/` copies, the settings merge and the ledger. So a
    # checkout with no `origin` exited 2 having written four artifacts, and `doctor._attached`,
    # which keys on the ledger existing, then reported it attached. A refusal that leaves a
    # repository looking attached is not a refusal, and only a snapshot says so.
    #
    # Mutation: move the `if binding.remote is None` guard in `attach` back below
    # `_write_ignore_region`, and this reddens on the snapshot while `pytest.raises` stays green.
    root, store, machine = _attachable(tmp_path, codex="# a standing rule\n")
    run_git(root, "remote", "remove", "origin")
    before = snapshot(root)
    # `snapshot` is a walk, and an empty one satisfies the comparison below on its own.
    assert before
    with pytest.raises(Refusal):
        attach(
            root,
            store=store,
            machine=machine,
            confirmed=False,
            trust_remote=True,
            runner=Recorder(),
            home=tmp_path / "home",
        )
    assert_snapshot_unchanged(root, before)


def test_the_no_origin_refusal_is_reached_with_a_diff_that_would_have_written(
    tmp_path: Path,
) -> None:
    # The vacuity guard for the case above: a refusal that writes nothing proves nothing if the
    # run had nothing to write. The same overlay, with an allow rule, a hook entry and a Codex
    # rule file, attaches and writes all of them when `origin` is there — so the snapshot above
    # is measuring a run that would otherwise have left four artifacts behind.
    hooks = {"SessionStart": [{"hooks": [ENTRY]}]}
    root, store, machine = _attachable(
        tmp_path, allow=(RULE,), hooks=hooks, codex="# a standing rule\n"
    )
    attached = attach(
        root,
        store=store,
        machine=machine,
        confirmed=True,
        trust_remote=True,
        runner=Recorder(),
        home=tmp_path / "home",
    )
    assert attached.settings_written
    assert attached.rules_written == (".codex/rules/common.rules",)
    assert (root / LEDGER).is_file()
    assert (root / ".gitignore").is_file()


def test_a_settings_file_the_merge_cannot_read_is_refused_and_never_filtered(
    tmp_path: Path,
) -> None:
    # `scaffold.entries`' rule, one file over: what a filter drops here is somebody's own
    # setting, and nothing would say it went.
    root, store, machine = _attachable(tmp_path, allow=(RULE,))
    (root / ".claude").mkdir()
    (root / SETTINGS).write_text(json.dumps({"permissions": {"allow": "all"}}), encoding="utf-8")
    with pytest.raises(Refusal):
        attach(
            root,
            store=store,
            machine=machine,
            confirmed=True,
            trust_remote=False,
            runner=Recorder(),
            home=tmp_path / "home",
        )


def test_an_overlay_hooks_file_with_an_unreadable_shape_is_refused(tmp_path: Path) -> None:
    # The same rule on the other side. An overlay entry this cannot key is one the owner put
    # there on purpose, and installing the rest of the file while dropping it silently is how
    # a hook goes missing with nothing to say so.
    root, store, machine = _attachable(tmp_path)
    (store.parents[2] / COMMON_CLAUDE / "hooks.json").write_text(
        json.dumps({"hooks": {"SessionStart": "not a list"}}), encoding="utf-8"
    )
    with pytest.raises(Refusal):
        attach(
            root,
            store=store,
            machine=machine,
            confirmed=True,
            trust_remote=False,
            runner=Recorder(),
            home=tmp_path / "home",
        )


def test_a_ledger_that_is_not_json_is_a_failure_and_not_an_empty_one(tmp_path: Path) -> None:
    # An empty ledger reads as "attach added nothing", which makes `detach` a no-op on a
    # repository that has stayfixed's rules in it — the quiet half of the failure this file is
    # the only witness to.
    root, store, machine = _attachable(tmp_path)
    attach(
        root,
        store=store,
        machine=machine,
        confirmed=False,
        trust_remote=False,
        runner=Recorder(),
        home=tmp_path / "home",
    )
    (root / LEDGER).write_text("{", encoding="utf-8")
    with pytest.raises(Failure):
        ledger(root)


# Valid JSON nested past what `json.loads` follows: it raises `RecursionError` on every supported
# Python, which no reader caught, and both files below are ones a clone can commit.
NESTED = "[" * 200_000 + "]" * 200_000


def test_a_ledger_nested_past_the_parsers_reach_is_a_failure_and_never_an_internal_error(
    tmp_path: Path,
) -> None:
    # The ledger is the unreadable ledger it is, and the attach that reads it back answers so
    # rather than ending in an internal error. Mutation (oracle): `mutations/`'s "the attach
    # ledger's reader lets a nested ledger raise" -> both raise `RecursionError`.
    root, store, machine = _attachable(tmp_path)
    attach(
        root,
        store=store,
        machine=machine,
        confirmed=False,
        trust_remote=False,
        runner=Recorder(),
        home=tmp_path / "home",
    )
    (root / LEDGER).write_text('{"entries": ' + NESTED + "}", encoding="utf-8")
    with pytest.raises(Failure, match="nested deeper"):
        ledger(root)
    with pytest.raises(Failure, match="nested deeper"):
        attach(
            root,
            store=store,
            machine=machine,
            confirmed=True,
            trust_remote=False,
            runner=Recorder(),
            home=tmp_path / "home",
        )


def test_a_settings_file_nested_past_the_parsers_reach_is_refused(tmp_path: Path) -> None:
    # The settings file `attach` merges into, read first by `permissions.settings_document`.
    # Mutation (oracle): `mutations/`'s "attach's settings reader lets a nested document raise"
    # -> both raise `RecursionError`.
    root, store, machine = _attachable(tmp_path, allow=(RULE,))
    (root / ".claude").mkdir()
    (root / SETTINGS).write_text('{"hooks": ' + NESTED + "}", encoding="utf-8")
    with pytest.raises(EntriesError, match="nested deeper"):
        settings_document((root / SETTINGS).read_text(encoding="utf-8"))
    with pytest.raises(Refusal, match="nested deeper"):
        attach(
            root,
            store=store,
            machine=machine,
            confirmed=True,
            trust_remote=False,
            runner=Recorder(),
            home=tmp_path / "home",
        )


def test_a_pre_commit_that_is_already_installed_is_not_run_again(tmp_path: Path) -> None:
    root, store, machine = _attachable(tmp_path)
    overlay = store.parents[2]
    hooks = _overlay_repository(overlay)
    (overlay / ".pre-commit-config.yaml").write_text("repos: []\n", encoding="utf-8")
    (hooks / "pre-commit").write_text("#!/bin/sh\n", encoding="utf-8")
    runner = Recorder()
    attached = attach(
        root,
        store=store,
        machine=machine,
        confirmed=False,
        trust_remote=False,
        runner=runner,
        home=tmp_path / "home",
    )
    assert runner.calls == []
    # The one note left is the harness link waiting for approval, which this fixture never
    # gives; nothing about the secret scan is said.
    assert attached.notes == (HARNESS_WAITS,)


def test_a_hook_outside_dot_git_still_counts_as_installed(tmp_path: Path) -> None:
    # The hook's directory is `git rev-parse --git-path hooks`, never `.git/hooks` and
    # never `core.hooksPath` read by hand — the rule `docs/cli.md` states for `setup
    # --git-hooks` and `guards.githooks.hooks_dir` implements. With `core.hooksPath` set, a
    # hardcoded path finds the scan missing on EVERY attach and shells out to `pre-commit
    # install` each time, on a machine where it is already armed.
    root, store, machine = _attachable(tmp_path)
    overlay = store.parents[2]
    hooks = _overlay_repository(overlay, hooks_path=tmp_path / "dotfiles" / "hooks")
    (overlay / ".pre-commit-config.yaml").write_text("repos: []\n", encoding="utf-8")
    (hooks / "pre-commit").write_text("#!/bin/sh\n", encoding="utf-8")
    runner = Recorder()
    attached = attach(
        root,
        store=store,
        machine=machine,
        confirmed=False,
        trust_remote=False,
        runner=runner,
        home=tmp_path / "home",
    )
    assert runner.calls == []
    # The one note left is the harness link waiting for approval, which this fixture never
    # gives; nothing about the secret scan is said.
    assert attached.notes == (HARNESS_WAITS,)


def test_an_overlay_git_cannot_answer_about_is_a_note_and_never_a_traceback(
    tmp_path: Path,
) -> None:
    # `hooks_dir` refuses when `git` cannot name the directory — an overlay that is not a
    # repository at all is the cheapest such state. Every external binary is optional, so this
    # is a note; and `pre-commit install` is NOT fired blind at a directory nobody could place
    # a hook in.
    root, store, machine = _attachable(tmp_path)
    (store.parents[2] / ".pre-commit-config.yaml").write_text("repos: []\n", encoding="utf-8")
    runner = Recorder()
    attached = attach(
        root,
        store=store,
        machine=machine,
        confirmed=False,
        trust_remote=False,
        runner=runner,
        home=tmp_path / "home",
    )
    assert runner.calls == []
    assert any("hooks directory" in note for note in attached.notes)


def test_a_pre_commit_that_cannot_run_is_a_note_and_never_a_traceback(tmp_path: Path) -> None:
    # Every external binary is optional: a missing `pre-commit` is a reported finding, and the
    # push-time scan the template ships still runs.
    root, store, machine = _attachable(tmp_path)
    _overlay_repository(store.parents[2])
    (store.parents[2] / ".pre-commit-config.yaml").write_text("repos: []\n", encoding="utf-8")
    runner = Recorder(code=127, stderr="pre-commit could not be run")
    attached = attach(
        root,
        store=store,
        machine=machine,
        confirmed=False,
        trust_remote=False,
        runner=runner,
        home=tmp_path / "home",
    )
    assert any("did not run" in note for note in attached.notes)


def _committed_ledger(root: Path, store: Path, **fields: object) -> None:
    """The ledger a clone committed, as a fresh checkout can genuinely hold one.

    `.gitignore` does not untrack a file a clone committed, and the `stayfixed:ignore` region
    `attach` writes does not either — so this path can be populated before `attach` has ever run
    here, which is the state both cases below are about.
    """
    document: dict[str, object] = {
        "format": 1,
        "store": str(store),
        "allow": [],
        "entries": {},
        "rules": [],
        "settings_keys": [],
    }
    document.update(fields)
    (root / LEDGER).parent.mkdir(parents=True, exist_ok=True)
    (root / LEDGER).write_text(json.dumps(document), encoding="utf-8")


def test_a_ledger_no_attach_could_have_written_is_refused_before_the_first_write(
    tmp_path: Path,
) -> None:
    # The same shape as `test_a_repository_with_no_origin_remote_has_nothing_to_record`, one
    # door over, and introduced by the commit that wrote that rule down. `ledger()` refuses a
    # ledger naming files or settings keys `attach` could not have written, and `_write_ledger`
    # used to be the thing that asked for it — from the fourth write of the run. So a clone
    # committing such a ledger got `attach` to write the `stayfixed:ignore` region, copy
    # `.codex/rules/*` and merge `.claude/settings.local.json`, and only then exit 2 — with the
    # committed ledger still on disk, which `doctor._attached` keys on. `attach --check` reports
    # clean beforehand, because it does not read the ledger at all.
    #
    # Nothing the repository gains here differs from a successful attach, so this is not a trust
    # boundary being crossed. What it is, is `docs/cli.md` asserting that every cause of exit 2
    # happens before the first write while one of them did not.
    #
    # Mutation: `mutations/`'s "the ledger is read after attach has already written".
    root, store, machine = _attachable(tmp_path, allow=(RULE,), codex="# a standing rule\n")
    _committed_ledger(root, store, rules=[".github/workflows/ci.yml"])
    before = snapshot(root)
    # `snapshot` is a walk, and an empty one satisfies the comparison below on its own.
    assert before
    with pytest.raises(Refusal):
        attach(
            root,
            store=store,
            machine=machine,
            confirmed=True,
            trust_remote=True,
            runner=Recorder(),
            home=tmp_path / "home",
        )
    assert_snapshot_unchanged(root, before)


def test_the_refused_ledger_is_reached_on_a_run_that_would_have_written_three_files(
    tmp_path: Path,
) -> None:
    # The vacuity guard for the case above, and the same one the no-origin refusal's snapshot has: a
    # refusal that writes nothing proves nothing if the run had nothing to write. The identical
    # fixture, with a ledger `attach` really could have written, attaches and leaves all three
    # artifacts the refusal above has to prevent.
    root, store, machine = _attachable(tmp_path, allow=(RULE,), codex="# a standing rule\n")
    _committed_ledger(root, store, rules=[".codex/rules/common.rules"])
    before = snapshot(root)
    assert before
    attached = attach(
        root,
        store=store,
        machine=machine,
        confirmed=True,
        trust_remote=True,
        runner=Recorder(),
        home=tmp_path / "home",
    )
    after = snapshot(root)
    assert attached.settings_written
    assert ".codex/rules/common.rules" in set(after) - set(before)
    assert SETTINGS in set(after) - set(before)
    assert before.get(".gitignore") != after.get(".gitignore")
    # And the union the ledger exists for survived the refusal being hoisted out of the writer:
    # `_write_ledger` is handed the ledger the caller read once, above every write.
    assert ledger(root).rules == (".codex/rules/common.rules",)


def test_an_overlay_store_the_walk_cannot_enter_is_refused_at_write_time(tmp_path: Path) -> None:
    # The floor under the containment hoisted above every write, and the proof it is not dead.
    # `config.paths.contained` answers about a *spelling* and about the symlinks it can see when
    # it looks; `fsops.mkdirs_within` asks the filesystem again at the moment of writing, through
    # the `O_NOFOLLOW` walk, which is the only thing that can catch a component that is not a
    # directory — or became a symlink in between. Here the overlay holds a regular file where
    # this project's memory directory belongs, which `contained` passes and the walk refuses.
    #
    # This is the one remaining way this refusal can arrive after a write, and it is a fact
    # about the overlay — the owner's own tree — rather than about a repository-authored entry.
    #
    # Mutation: `mutations/`'s "the write-time containment on the overlay's store directory
    # is swallowed".
    root, store, machine = _attachable(tmp_path)
    shutil.rmtree(store)
    store.write_text("not a directory\n", encoding="utf-8")
    with pytest.raises(Refusal) as refusal:
        attach(
            root,
            store=store,
            machine=machine,
            confirmed=True,
            trust_remote=True,
            runner=Recorder(),
            home=tmp_path / "home",
        )
    assert "memory.groups" in str(refusal.value)


def test_a_group_that_never_moved_refuses_the_attach_above_every_write(tmp_path: Path) -> None:
    """The ninth refusal, and the only one whose remedy is an act nothing here can perform.

    `attach` **links**; it never moves a note. So a `memory.groups` entry that is still a real
    directory under `paths.memory` is a group whose notes are in the repository and whose share
    of the overlay is empty — and linking over it would leave the session reading the
    repository's copy with the binding record, the settings merge and the ledger already
    written. The anchor is `root`, the checkout the command was pointed at, and not a value the
    repository chose: `unlinked_groups` contains every `<paths.memory>/<group>` against it, so a
    repository cannot move the directory the count is taken under.

    Both snapshots, because a refusal that leaves the *overlay* carrying a binding record is
    just as much "looking attached" as one that leaves the repository carrying a ledger.

    Mutation: `mutations/`'s "attach links over notes that never moved again".
    """
    root, store, machine = _attachable(tmp_path)
    note = root / DEFAULT_MEMORY / "project-stable" / "kept.md"
    note.parent.mkdir(parents=True)
    note.write_text("---\nname: kept\ndescription: a note\n---\n\nbody\n", encoding="utf-8")
    before, overlay_before = snapshot(root), snapshot(store.parents[2])
    # The walks' own floor, for the reason the mismatch case above states: `snapshot` is a walk,
    # and two empty dictionaries compare equal however much was written between them.
    assert before and overlay_before
    # The identity and not a substring, for the reason the escaping-group case above now gives:
    # a refusal added beside this one makes a substring match stop saying which fired, and this
    # one already sits one line from a containment whose message shares most of its words.
    with pytest.raises(Refusal) as refusal:
        attach(
            root,
            store=store,
            machine=machine,
            confirmed=True,
            trust_remote=False,
            runner=Recorder(),
            home=tmp_path / "home",
        )
    assert str(refusal.value) == REAL_DIRECTORIES.format(count=1)
    assert_snapshot_unchanged(root, before)
    assert_snapshot_unchanged(store.parents[2], overlay_before)
    # The owner's act, and the only one that clears the refusal: the notes move into this
    # project's share of the overlay, and the same attach then links over nothing.
    shutil.move(str(note.parent), str(store / "project-stable"))
    attach(
        root,
        store=store,
        machine=machine,
        confirmed=True,
        trust_remote=False,
        runner=Recorder(),
        home=tmp_path / "home",
    )
    assert (root / DEFAULT_MEMORY / "project-stable").is_symlink()
    assert (root / DEFAULT_MEMORY / "project-stable" / "kept.md").is_file()


def test_the_refusal_counts_the_groups_and_never_names_one(tmp_path: Path) -> None:
    """`memory.groups` is repository-authored, so the message carries a count and no entry.

    The same rule `GROUP_ESCAPES` and the `--store` refusal are written to, and worth its own
    case here because this refusal's *remedy* invites a name — "move this group" reads better
    than "move each of them" — and `skills/attach/SKILL.md` relays these messages to a model.
    """
    root, store, machine = _attachable(tmp_path)
    (root / DEFAULT_MEMORY / "developer").mkdir(parents=True)
    with pytest.raises(Refusal) as refusal:
        attach(
            root,
            store=store,
            machine=machine,
            confirmed=True,
            trust_remote=False,
            runner=Recorder(),
            home=tmp_path / "home",
        )
    message = str(refusal.value)
    assert "developer" not in message
    # Non-vacuous: the message did report, and what it reported is the count `attach` took.
    assert "1 of this project's memory groups" in message


def test_a_worktree_listing_git_gave_no_answer_for_is_a_failure_about_this_machine(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # `-1` from `git_run` is a `git` that could not be run or ran past its bound: a fault on
    # this machine, and never a listing of no worktrees, which would link memory into none of
    # them. A worktree path that is not UTF-8 is no longer a cause — the listing is decoded
    # losslessly — so the message does not send the owner looking for one. Mutation
    # (advisory): put the UTF-8 clause back — the last assertion reddens.
    from stayfixed.attach import write as module

    monkeypatch.setattr(module, "git_run", lambda *a, **k: (-1, ""))
    with pytest.raises(Failure, match="check that `git` runs here") as caught:
        module._worktrees(tmp_path)
    assert "UTF-8" not in str(caught.value)


# --- what `attach` leaves for `git status` to show -------------------------------------------

EXCLUDE_REGION = "attach"


def _exclude(root: Path) -> Path:
    return root / ".git" / "info" / "exclude"


def _committed(root: Path) -> None:
    """Commit what the fixture wrote, so `git status` afterwards shows only what `attach` added."""
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "the project as it was")


def _status(root: Path) -> list[str]:
    return _git(root, "status", "--porcelain", "--untracked-files=all").splitlines()


def _placed() -> list[str]:
    """Every path `attach` puts into the project for this fixture, the ledger aside: the link
    tree (the index and one link per group), the Codex rule it copies and the settings file."""
    return [
        f"{DEFAULT_MEMORY}/MEMORY.md",
        f"{DEFAULT_MEMORY}/developer",
        f"{DEFAULT_MEMORY}/project-stable",
        ".codex/rules/common.rules",
        SETTINGS,
    ]


def _attach_confirmed(root: Path, store: Path, machine: Path, home: Path) -> None:
    attach(
        root,
        store=store,
        machine=machine,
        confirmed=True,
        trust_remote=False,
        runner=Recorder(),
        home=home,
    )


def test_attach_leaves_nothing_for_git_status_but_the_ignore_region(tmp_path: Path) -> None:
    # The link tree, `.codex/rules/` and `.claude/settings.local.json` were all untracked and
    # unignored after an attach, so every `git status` in the project listed the owner's personal
    # links and rules, and a `git add -A` committed them. They are machine-local by construction,
    # so `attach` hides them in `info/exclude`, which no clone shares, and leaves `.gitignore`
    # to the one region `init` already owns.
    root, store, machine = _attachable(tmp_path, allow=(RULE,), codex="# standing rule\n")
    _committed(root)
    _attach_confirmed(root, store, machine, tmp_path / "home")
    for placed in _placed():
        # Non-vacuous: each one is really there, so `check-ignore` answers about a real path.
        assert (root / placed).is_symlink() or (root / placed).is_file(), placed
        assert _check_ignore(root, placed), placed
    assert _status(root) == ["?? .gitignore"]
    body = extract(_exclude(root).read_text(encoding="utf-8"), EXCLUDE_REGION, Style.HASH)
    assert body is not None and SETTINGS in body


def test_a_checkout_that_already_hides_everything_is_not_touched(tmp_path: Path) -> None:
    # The legitimate user the exclude block must not disturb: someone who keeps the whole
    # footprint out of git through `info/exclude` already. `attach` asks git which of its paths
    # are ignored before it writes, so neither file changes and `git status` stays empty.
    #
    # Mutation: `mutations/`'s "attach treats an ignored path as not ignored".
    root, store, machine = _attachable(tmp_path, allow=(RULE,), codex="# standing rule\n")
    _committed(root)
    exclude = _exclude(root)
    exclude.parent.mkdir(exist_ok=True)
    held = exclude.read_text(encoding="utf-8") if exclude.is_file() else ""
    lines = [f"/{placed}" for placed in _placed()] + [
        ".stayfixed/local/",
        ".stayfixed/assessment.json",
    ]
    exclude.write_text(held + "\n".join(lines) + "\n", encoding="utf-8")
    before = exclude.read_bytes()
    _attach_confirmed(root, store, machine, tmp_path / "home")
    # Non-vacuous: the attach did place its files, so there was something to hide.
    assert (root / SETTINGS).is_file()
    assert not (root / ".gitignore").exists()
    assert exclude.read_bytes() == before
    assert _status(root) == []


def test_a_checkout_whose_global_excludes_file_hides_everything_is_not_touched(
    tmp_path: Path,
) -> None:
    # The other owner-held source: a global excludes file (`core.excludesFile`) that already
    # hides the whole footprint. Its lines count as hidden, so neither ignore file changes.
    root, store, machine = _attachable(tmp_path, allow=(RULE,), codex="# standing rule\n")
    _committed(root)
    owner = tmp_path / "owner-excludes"
    lines = [f"/{placed}" for placed in _placed()] + [
        ".stayfixed/local/",
        ".stayfixed/assessment.json",
    ]
    owner.write_text("\n".join(lines) + "\n", encoding="utf-8")
    _git(root, "config", "core.excludesFile", str(owner))
    exclude = _exclude(root)
    before = exclude.read_bytes() if exclude.is_file() else None
    _attach_confirmed(root, store, machine, tmp_path / "home")
    # Non-vacuous: the attach did place its files, so there was something to hide.
    assert (root / SETTINGS).is_file()
    assert not (root / ".gitignore").exists()
    assert (exclude.read_bytes() if exclude.is_file() else None) == before
    assert _status(root) == []


def test_a_global_excludes_file_named_by_a_relative_path_still_stands_in_for_the_block(
    tmp_path: Path,
) -> None:
    # git opens a relative `core.excludesFile` from the top of the work tree. The question about
    # the owner's own excludes is asked over an empty work tree, where that path names no file,
    # so the owner's lines stood in for nothing and every path they hide got a line of its own.
    #
    # Mutation: `mutations/`'s "the owner's relative excludes file is read from the empty work
    # tree".
    root, store, machine = _attachable(tmp_path, allow=(RULE,), codex="# standing rule\n")
    _committed(root)
    owner = tmp_path / "owner-excludes"
    lines = [f"/{placed}" for placed in _placed()] + [
        ".stayfixed/local/",
        ".stayfixed/assessment.json",
    ]
    owner.write_text("\n".join(lines) + "\n", encoding="utf-8")
    relative = os.path.relpath(owner, root)
    _git(root, "config", "core.excludesFile", relative)
    # Non-vacuous: the path is relative, and git reads it from the checkout's top.
    assert not Path(relative).is_absolute()
    assert _check_ignore(root, SETTINGS)
    exclude = _exclude(root)
    before = exclude.read_bytes() if exclude.is_file() else None
    _attach_confirmed(root, store, machine, tmp_path / "home")
    assert (root / SETTINGS).is_file()
    assert (exclude.read_bytes() if exclude.is_file() else None) == before
    assert _status(root) == []


def test_a_committed_gitignore_does_not_stand_in_for_the_exclude_block(tmp_path: Path) -> None:
    # A committed `.gitignore` is the repository's, and a pull can take a line out of it. Counted
    # as hiding the owner's links, it left them out of the block, and an upstream commit that
    # dropped the link tree's line from `.gitignore` showed the links and the settings file in every
    # `git status` until the next attach. Only the owner's own excludes -- `info/exclude` and the
    # global excludes file -- stand in for the block.
    #
    # Mutation: `mutations/`'s "the owner's exclude question reads the checkout's .gitignore".
    root, store, machine = _attachable(tmp_path, allow=(RULE,), codex="# standing rule\n")
    (root / ".gitignore").write_text(f"{DEFAULT_MEMORY}/\n.claude/\n.codex/\n", encoding="utf-8")
    _committed(root)
    _attach_confirmed(root, store, machine, tmp_path / "home")
    body = extract(_exclude(root).read_text(encoding="utf-8"), EXCLUDE_REGION, Style.HASH)
    assert body is not None
    for placed in _placed():
        assert f"/{placed}" in body.split("\n"), placed
    # Upstream drops the lines; the owner's files stay hidden.
    (root / ".gitignore").write_text(
        (root / ".gitignore")
        .read_text(encoding="utf-8")
        .split("# stayfixed:ignore:begin")[0]
        .replace(f"{DEFAULT_MEMORY}/\n", "")
        .replace(".claude/\n", "")
        .replace(".codex/\n", "")
        + "# stayfixed:ignore:begin"
        + (root / ".gitignore").read_text(encoding="utf-8").split("# stayfixed:ignore:begin")[1],
        encoding="utf-8",
    )
    assert _status(root) == [" M .gitignore"]


def test_a_path_the_owners_global_excludes_hide_gets_no_line_whatever_the_gitignore_says(
    tmp_path: Path,
) -> None:
    # The common dotfiles layout: the owner's global excludes file (`~/.config/git/ignore`, read
    # with no `core.excludesFile` set) hides the settings file, and the repository's committed
    # `.gitignore` names it too. Asked which pattern decides, git names the `.gitignore`, which
    # outranks the owner's file, and that answer gave the settings file a redundant line of its
    # own: the owner's line keeps it hidden whatever a pull does to the `.gitignore`.
    #
    # Mutation: `mutations/`'s "the exclude block ignores what the owner's excludes hide".
    root, store, machine = _attachable(tmp_path, allow=(RULE,), codex="# standing rule\n")
    (root / ".gitignore").write_text(f"{SETTINGS}\n", encoding="utf-8")
    _committed(root)
    ignore = Path.home() / ".config" / "git" / "ignore"
    ignore.parent.mkdir(parents=True)
    ignore.write_text(f"{SETTINGS}\n", encoding="utf-8")
    _attach_confirmed(root, store, machine, tmp_path / "home")
    body = extract(_exclude(root).read_text(encoding="utf-8"), EXCLUDE_REGION, Style.HASH)
    # Non-vacuous: the run wrote the settings file, and a block for what nobody else hides.
    assert (root / SETTINGS).is_file()
    assert body is not None and f"/{DEFAULT_MEMORY}/developer" in body.split("\n")
    assert f"/{SETTINGS}" not in body.split("\n")
    assert _status(root) == [" M .gitignore"]


def test_a_gitignore_a_sparse_checkout_leaves_out_does_not_stand_in_for_the_block(
    tmp_path: Path,
) -> None:
    # A sparse checkout keeps a `.gitignore` it leaves out of the work tree in the index only,
    # marked skip-worktree, and git reads such a file from the index when it is not on disk. The
    # question about the owner's own excludes is asked against an empty work tree, where no
    # `.gitignore` is on disk: read with the index, it took the repository's line for the
    # owner's again and left the link tree out of the block.
    #
    # Mutation: `mutations/`'s "the owner's exclude question reads the index".
    root, store, machine = _attachable(tmp_path)
    (root / ".gitignore").write_text(f"{DEFAULT_MEMORY}/\n", encoding="utf-8")
    _committed(root)
    _git(root, "update-index", "--skip-worktree", ".gitignore")
    (root / ".gitignore").unlink()
    # Non-vacuous: git still reads the left-out file, so the link tree's directory is ignored.
    assert _check_ignore(root, f"{DEFAULT_MEMORY}/developer")
    _attach_confirmed(root, store, machine, tmp_path / "home")
    body = extract(_exclude(root).read_text(encoding="utf-8"), EXCLUDE_REGION, Style.HASH)
    assert body is not None
    for placed in (f"{DEFAULT_MEMORY}/MEMORY.md", f"{DEFAULT_MEMORY}/developer"):
        assert f"/{placed}" in body.split("\n"), placed


def test_a_path_the_owners_excludes_re_include_is_still_hidden(tmp_path: Path) -> None:
    # `check-ignore -v` reports a path whose last matching pattern is a negation, and exits 0 for
    # it. Read as "hidden", a link the owner's excludes file re-includes got no line and showed
    # in `git status`. No mutation: the question is asked without `-v`, so git applies the
    # negation itself and no line of stayfixed's reads it; the test holds the behaviour.
    root, store, machine = _attachable(tmp_path)
    _committed(root)
    owner = tmp_path / "owner-excludes"
    owner.write_text(f"{DEFAULT_MEMORY}/*\n!{DEFAULT_MEMORY}/developer\n", encoding="utf-8")
    _git(root, "config", "core.excludesFile", str(owner))
    _attach_confirmed(root, store, machine, tmp_path / "home")
    body = extract(_exclude(root).read_text(encoding="utf-8"), EXCLUDE_REGION, Style.HASH)
    assert body is not None and f"/{DEFAULT_MEMORY}/developer" in body.split("\n")
    # The other links the owner's file hides get no line of their own.
    assert f"/{DEFAULT_MEMORY}/project-stable" not in body.split("\n")
    assert _status(root) == ["?? .gitignore"]


def test_the_block_keeps_what_an_earlier_attach_hid_when_the_grant_changes(
    tmp_path: Path,
) -> None:
    # A path an earlier block hides reads as ignored now. Rebuilt from one run's answer alone, the
    # block dropped it: attach with an overlay granting nothing, grant a rule, attach again, and
    # the block held only the settings file while `git status` listed the whole link tree.
    #
    # Mutation: `mutations/`'s "the exclude block forgets what an earlier attach hid".
    root, store, machine = _attachable(tmp_path)
    _committed(root)
    home = tmp_path / "home"
    _attach_confirmed(root, store, machine, home)
    first = extract(_exclude(root).read_text(encoding="utf-8"), EXCLUDE_REGION, Style.HASH)
    # Non-vacuous: the first block names the link tree and not the settings file.
    assert first is not None and f"/{DEFAULT_MEMORY}/developer" in first
    assert SETTINGS not in first
    _overlay_grants(store, allow=(RULE,))
    _attach_confirmed(root, store, machine, home)
    second = extract(_exclude(root).read_text(encoding="utf-8"), EXCLUDE_REGION, Style.HASH)
    assert second is not None and f"/{SETTINGS}" in second.split("\n")
    assert _status(root) == ["?? .gitignore"]


def test_a_second_attach_changes_neither_ignore_file(tmp_path: Path) -> None:
    root, store, machine = _attachable(tmp_path, allow=(RULE,), codex="# standing rule\n")
    _committed(root)
    home = tmp_path / "home"
    _attach_confirmed(root, store, machine, home)
    # Non-vacuous: the first attach did write both, so "unchanged" is about a block and a region
    # and not about two files that were never there.
    body = extract(_exclude(root).read_text(encoding="utf-8"), EXCLUDE_REGION, Style.HASH)
    assert body is not None and SETTINGS in body
    assert extract((root / ".gitignore").read_text(encoding="utf-8"), "ignore", Style.HASH)
    gitignore, exclude = (root / ".gitignore").read_bytes(), _exclude(root).read_bytes()
    _attach_confirmed(root, store, machine, home)
    assert (root / ".gitignore").read_bytes() == gitignore
    assert _exclude(root).read_bytes() == exclude


def test_a_linked_worktree_shares_the_block_and_its_links_stay_hidden(tmp_path: Path) -> None:
    # `info/exclude` resolves through the common directory every worktree shares, so the one
    # block the attach wrote covers the links `worktree-link` builds in a worktree made later,
    # and that handler never writes the block itself.
    from stayfixed.config.loader import load
    from stayfixed.memory.api import link, resolve

    root, store, machine = _attachable(tmp_path)
    _committed(root)
    home = tmp_path / "home"
    _attach_confirmed(root, store, machine, home)
    side = tmp_path / "side"
    _git(root, "worktree", "add", "-q", str(side), "-b", "side")
    shared = _git(side, "rev-parse", "--path-format=absolute", "--git-path", "info/exclude")
    assert Path(shared.strip()).resolve() == _exclude(root).resolve()
    before = _exclude(root).read_bytes()
    config = load(root, machine=machine)
    resolved = resolve(root, config, machine=machine)
    assert resolved is not None
    made = link(side, resolved, config, home=home)
    # Non-vacuous: the handler's call did build a tree in the worktree.
    assert made.created
    assert _exclude(root).read_bytes() == before
    assert _status(side) == []


def test_a_symlinked_exclude_file_is_refused_before_anything_is_written(tmp_path: Path) -> None:
    # `info/exclude` is resolved by git, and written by `attach` only after it refuses a
    # symlink there, as `setup --git-hooks` refuses a symlinked hook: a write through the link
    # would land wherever it points. Refused above the first write, like every other refusal.
    root, store, machine = _attachable(tmp_path, allow=(RULE,))
    exclude = _exclude(root)
    elsewhere = tmp_path / "somebody-elses-file"
    elsewhere.write_text("# not the repository's\n", encoding="utf-8")
    if exclude.exists():
        exclude.unlink()
    exclude.parent.mkdir(exist_ok=True)
    exclude.symlink_to(elsewhere)
    before = snapshot(root)
    assert before
    with pytest.raises(Refusal) as refused:
        _attach_confirmed(root, store, machine, tmp_path / "home")
    assert "symlink" in str(refused.value)
    assert_snapshot_unchanged(root, before)
    assert elsewhere.read_text(encoding="utf-8") == "# not the repository's\n"


def test_the_first_attach_leaves_an_index_behind_its_link(tmp_path: Path) -> None:
    # `attach` linked `<paths.memory>/MEMORY.md` to the overlay's copy before any copy existed,
    # so every session saw a dangling link and `memory index --check` failed until someone ran
    # `memory index` by hand. The memory area's own renderer writes it in the same run.
    from tests.cli import cli

    root, store, machine = _attachable(tmp_path)
    _attach_confirmed(root, store, machine, tmp_path / "home")
    index = root / DEFAULT_MEMORY / "MEMORY.md"
    assert index.is_symlink()
    assert index.is_file(), "the index link dangles"
    code, out, err = cli(root, tmp_path, "memory", "index", "--check", machine=machine)
    assert code == 0, out + err


def test_a_symlinked_claude_directory_the_run_never_writes_into_is_not_refused(
    tmp_path: Path,
) -> None:
    # A `.claude` kept elsewhere and linked in is an ordinary layout, and an overlay that grants
    # nothing gives `attach` nothing to write there. The exclude block's candidates are what this
    # run writes, so the settings file is neither a reason to refuse nor a line in the block.
    #
    # Mutation: `mutations/`'s "attach hides the settings file on a run that never writes it".
    root, store, machine = _attachable(tmp_path)
    _committed(root)
    (tmp_path / "dotfiles-claude").mkdir()
    (root / ".claude").symlink_to(tmp_path / "dotfiles-claude", target_is_directory=True)
    _attach_confirmed(root, store, machine, tmp_path / "home")
    # Non-vacuous: the attach did run to the end and wrote a block for what it did place.
    body = extract(_exclude(root).read_text(encoding="utf-8"), EXCLUDE_REGION, Style.HASH)
    assert body is not None and f"/{DEFAULT_MEMORY}/developer" in body
    assert SETTINGS not in body
    assert not (tmp_path / "dotfiles-claude" / "settings.local.json").exists()


def test_a_run_that_would_write_through_a_symlinked_claude_directory_still_refuses(
    tmp_path: Path,
) -> None:
    # The other half: when the overlay grants a rule, the settings file is written, and a
    # `.claude` that is a link is refused before anything is written, as before.
    root, store, machine = _attachable(tmp_path, allow=(RULE,))
    (tmp_path / "dotfiles-claude").mkdir()
    (root / ".claude").symlink_to(tmp_path / "dotfiles-claude", target_is_directory=True)
    before = snapshot(root)
    assert before
    with pytest.raises(Refusal) as refused:
        _attach_confirmed(root, store, machine, tmp_path / "home")
    # Refused for the reason it has: the containment asked of each placed path names the link.
    # Mutation: `mutations/`'s "the exclude block stops holding placed paths to the project".
    assert "symlink" in str(refused.value)
    assert_snapshot_unchanged(root, before)


def test_a_symlinked_stayfixed_directory_is_refused_before_anything_is_written(
    tmp_path: Path,
) -> None:
    # The ledger is written under `.stayfixed/local/`, and nothing above the first write held
    # that path to the project by name: a clone committing `.stayfixed` as a link was refused
    # only because `git check-ignore` will not answer about a path beyond a symlink, with a
    # message blaming git. Held to the project first, so the refusal says what is wrong.
    #
    # Mutation: `mutations/`'s "attach stops holding the ledger's path to the project".
    root, store, machine = _attachable(tmp_path, allow=(RULE,), codex="# standing rule\n")
    (tmp_path / "elsewhere").mkdir()
    (root / ".stayfixed").symlink_to(tmp_path / "elsewhere", target_is_directory=True)
    before = snapshot(root)
    assert before
    with pytest.raises(Refusal) as refused:
        _attach_confirmed(root, store, machine, tmp_path / "home")
    # Named for what it is. Before, the refusal came by accident from `git check-ignore`, which
    # will not answer about a path beyond a symlink, and blamed git.
    assert "symlink" in str(refused.value)
    assert_snapshot_unchanged(root, before)
    assert list((tmp_path / "elsewhere").iterdir()) == []


def test_a_first_attach_beside_the_harnesss_own_memory_and_a_linked_claude_attaches(
    tmp_path: Path,
) -> None:
    # The harness makes `~/.claude/projects/<slug>/memory` a real directory of its own, a
    # `.claude` linked in from elsewhere is an ordinary layout, and an overlay that grants
    # nothing gives `attach` nothing to merge. On a first attach the store has no approval, so
    # the harness link is withheld and no settings-file fallback is ever wanted: the attach goes
    # through, says the link waits, writes no settings file and leaves `git status` clean but for
    # the region `init` owns.
    from stayfixed.memory.api import harness_memory_path

    root, store, machine = _attachable(tmp_path)
    home = tmp_path / "home"
    harness_memory_path(root, home).mkdir(parents=True)
    (tmp_path / "dotfiles-claude").mkdir()
    (root / ".claude").symlink_to(tmp_path / "dotfiles-claude", target_is_directory=True)
    _committed(root)  # the link is the project's own, committed like the rest of it
    attached = attach(
        root,
        store=store,
        machine=machine,
        confirmed=True,
        trust_remote=False,
        runner=Recorder(),
        home=home,
    )
    assert attached.notes == (HARNESS_WAITS,)
    assert not attached.settings_written
    assert list((tmp_path / "dotfiles-claude").iterdir()) == []
    assert _status(root) == ["?? .gitignore"]


# --- a `memory.groups` entry git would read as more than one exclude line -------------------

# Every character `str.splitlines` breaks a line at besides `\n` and `\r`, and the NUL git's C
# reader stops a line at: git reads an exclude file by `\n` alone, so a name holding one of these
# is one line to git and several to anything that re-reads the block with `splitlines`.
_LINE_BREAKERS = ("\v", "\f", "\x1c", "\x1d", "\x1e", "\x85", "\u2028", "\u2029", "\x00")
# A group name the repository authors, spelled as TOML escapes so the file stays text.
_INJECTED = r"g\u2028!.env\u2028b"


def _owner_hides_dotenv(root: Path, tmp_path: Path) -> None:
    """The owner's own excludes file hides `.env`; the project's `.env` and a file `b` sit
    untracked beside it, so `git status` shows `b` and never `.env`."""
    owner = tmp_path / "owner-excludes"
    owner.write_text(".env\n", encoding="utf-8")
    _git(root, "config", "core.excludesFile", str(owner))
    (root / ".env").write_text("SECRET=1\n", encoding="utf-8")
    (root / "b").write_text("b\n", encoding="utf-8")


def test_a_group_name_with_a_line_separator_unhides_nothing_on_a_later_attach(
    tmp_path: Path,
) -> None:
    # A repository-authored group name holding U+2028 was written as one exclude line, which git
    # reads as one line. The next attach re-read the block with `str.splitlines`, which breaks at
    # U+2028, and wrote the pieces back as three lines: the link's path up to `g`, `!.env` and
    # `b` -- so the owner's `.env` showed in `git status` and every file named `b` stopped
    # showing. The repository adding a group is the ordinary reason for a second attach.
    #
    # Mutation: `mutations/`'s "the exclude line refuses only a newline".
    root, store, machine = _attachable(tmp_path)
    _with_groups(root, f'["developer", "project-stable", "{_INJECTED}"]')
    _committed(root)
    _owner_hides_dotenv(root, tmp_path)
    home = tmp_path / "home"
    _attach_confirmed(root, store, machine, home)
    config = root / "stayfixed.toml"
    text = config.read_text(encoding="utf-8")
    config.write_text(text.replace(f'"{_INJECTED}"]', f'"{_INJECTED}", "later"]'), encoding="utf-8")
    _git(root, "commit", "-qam", "a group is added")
    _attach_confirmed(root, store, machine, home)
    body = extract(_exclude(root).read_text(encoding="utf-8"), EXCLUDE_REGION, Style.HASH)
    # Non-vacuous: the second attach did rewrite the block, with the group it added.
    assert body is not None and f"/{DEFAULT_MEMORY}/later" in body
    assert "!.env" not in body.split("\n")
    status = _status(root)
    assert "?? .env" not in status
    assert "?? b" in status


def test_an_earlier_blocks_line_is_kept_whole_whatever_it_holds(tmp_path: Path) -> None:
    # The union reads back the lines an earlier attach wrote. Read by `str.splitlines`, one line
    # holding U+2028 came back as three, and a `!.env` among them un-hid the owner's `.env`. git
    # ends a line at `\n` alone, so the block is read the same way.
    #
    # Mutation: `mutations/`'s "the exclude block is re-read at every line separator".
    root, store, machine = _attachable(tmp_path)
    _committed(root)
    _owner_hides_dotenv(root, tmp_path)
    exclude = _exclude(root)
    exclude.parent.mkdir(exist_ok=True)
    earlier = f"/{DEFAULT_MEMORY}/g\u2028!.env\u2028b"
    exclude.write_text(
        f"# stayfixed:attach:begin\n{earlier}\n# stayfixed:attach:end\n", encoding="utf-8"
    )
    _attach_confirmed(root, store, machine, tmp_path / "home")
    body = extract(exclude.read_text(encoding="utf-8"), EXCLUDE_REGION, Style.HASH)
    # Non-vacuous: this attach did rewrite the block, adding the links it placed.
    assert body is not None and f"/{DEFAULT_MEMORY}/developer" in body
    assert earlier in body.split("\n")
    status = _status(root)
    assert "?? .env" not in status
    assert "?? b" in status


@pytest.mark.parametrize("breaker", _LINE_BREAKERS, ids=lambda c: f"U+{ord(c):04X}")
def test_a_name_git_would_read_differently_gets_no_exclude_line(breaker: str) -> None:
    # A name holding one of these is left visible, as a name holding a line break already was:
    # no exclude line spells it, and one that tried would be read back as other lines, or, for a
    # NUL, cut short by git into a pattern for a different path.
    from stayfixed.attach.exclude import pattern

    assert pattern(f"notes/z{breaker}*") is None


def test_a_group_with_a_space_or_a_non_ascii_name_is_still_hidden() -> None:
    # The legitimate user the rule above must not refuse: an ordinary name that happens to hold a
    # space or a letter outside ASCII still gets its one anchored, escaped line.
    from stayfixed.attach.exclude import pattern

    assert pattern("notes/my notes") == "/notes/my\\ notes"
    assert pattern("notes/заметки") == "/notes/заметки"


@pytest.mark.parametrize(
    ("name", "line"),
    [
        ("notes/a*b", "/notes/a\\*b"),
        ("notes/a?b", "/notes/a\\?b"),
        ("notes/a[b", "/notes/a\\[b"),
        ("notes/a\\b", "/notes/a\\\\b"),
    ],
    ids=["star", "question", "bracket", "backslash"],
)
def test_each_pattern_character_in_a_group_name_is_escaped(name: str, line: str) -> None:
    # A `memory.groups` entry is the repository's, and git reads `*`, `?`, `[` and `\` in an
    # exclude line as pattern syntax: a group named `*` unescaped would hide every untracked note
    # under `paths.memory`, and `\` would escape whatever follows it. Only the space escape was
    # asserted, so any one of these could leave `_SPECIAL` unnoticed.
    #
    # Mutations: `mutations/`'s "the exclude line leaves a star unescaped", "the exclude line
    # leaves a question mark unescaped", "the exclude line leaves a bracket unescaped" and "the
    # exclude line leaves a backslash unescaped".
    from stayfixed.attach.exclude import pattern

    assert pattern(name) == line


# --- every refusal is made before the first write ---------------------------------------------


def _everything(tmp_path: Path) -> dict[str, dict[str, bytes]]:
    """What an attach could write: the project, the overlay, the home and the machine's trust
    record beside the machine file."""
    trust = tmp_path / "trust.json"
    return {
        "project": snapshot(tmp_path / "project"),
        "overlay": snapshot(tmp_path / "overlay"),
        "home": snapshot(tmp_path / "home"),
        "trust": {"trust.json": trust.read_bytes()} if trust.is_file() else {},
    }


def _attach_it(root: Path, store: Path, machine: Path, home: Path) -> Attached:
    return attach(
        root,
        store=store,
        machine=machine,
        confirmed=True,
        trust_remote=False,
        runner=Recorder(),
        home=home,
    )


def test_an_overlay_rule_that_is_not_utf8_stops_attach_before_it_writes(tmp_path: Path) -> None:
    # The overlay's rule sources were read and decoded while they were copied, after `.gitignore`
    # and the exclude block were written and after the rules before the bad one were copied: a
    # rule file that was not UTF-8 exited 1 with `.codex/rules/common.rules` on disk, listed in
    # the exclude block so `git status` no longer showed it, and no ledger for `detach` to
    # remove it by. Every source is read while the run is planned now.
    #
    # Mutations: `mutations/`'s "attach copies past an overlay rule that is not UTF-8", which
    # drops the refusal, and "attach reads the overlay's rule sources after its first write",
    # which keeps it and moves it below a write, so the snapshot is what reddens.
    root, store, machine = _attachable(tmp_path, allow=(RULE,), codex="# a standing rule\n")
    (store.parents[2] / COMMON_CODEX / "z.rules").write_bytes(b"\xff\xfe not text\n")
    before = _everything(tmp_path)
    assert before["project"] and before["overlay"]
    with pytest.raises(Failure, match="not UTF-8"):
        _attach_it(root, store, machine, tmp_path / "home")
    assert _everything(tmp_path) == before


def test_a_trust_record_that_does_not_parse_stops_attach_before_it_writes(tmp_path: Path) -> None:
    # The trust record was first read by the index render and the harness link, after the settings,
    # the rule copies, the ledger, the overlay's binding record and the link tree were written: a
    # `trust.json` that did not parse exited 2 there, with the index link dangling. It is read
    # while the run is planned now, so the refusal leaves everything as it was.
    #
    # Mutation: `mutations/`'s "attach reads the trust record only after it has written".
    root, store, machine = _attachable(tmp_path, allow=(RULE,), codex="# a standing rule\n")
    (machine.parent / "trust.json").write_text("{not json", encoding="utf-8")
    before = _everything(tmp_path)
    with pytest.raises(Refusal, match=r"trust\.json"):
        _attach_it(root, store, machine, tmp_path / "home")
    assert _everything(tmp_path) == before


@pytest.mark.skipif(os.geteuid() == 0, reason="root writes into a directory it cannot write")
def test_an_exclude_file_that_cannot_be_written_is_refused_by_name_before_the_first_write(
    tmp_path: Path,
) -> None:
    # A `.git/info` attach could not write into ended as `internal error: PermissionError`, after
    # `.gitignore` had its region. The directory is asked whether it can be written while the run
    # is planned, and the refusal names the file.
    #
    # Mutation: `mutations/`'s "attach finds out the exclude file cannot be written by
    # writing it".
    root, store, machine = _attachable(tmp_path, allow=(RULE,), codex="# a standing rule\n")
    info = root / ".git" / "info"
    info.mkdir(exist_ok=True)
    before = _everything(tmp_path)
    info.chmod(0o555)
    try:
        with pytest.raises(Refusal) as refused:
            _attach_it(root, store, machine, tmp_path / "home")
    finally:
        info.chmod(0o755)
    assert "info/exclude" in str(refused.value)
    assert "internal error" not in str(refused.value)
    assert _everything(tmp_path) == before


def test_a_doubled_exclude_block_is_refused_naming_the_exclude_file(tmp_path: Path) -> None:
    # "region 'attach' is opened or closed twice" said which region and never which file, and the
    # file is not one a person opens often: `.git/info/exclude`.
    #
    # Mutation: `mutations/`'s "a doubled exclude block is refused without its file".
    root, store, machine = _attachable(tmp_path, allow=(RULE,), codex="# a standing rule\n")
    begin = "# stayfixed:attach:begin\n"
    _exclude(root).parent.mkdir(exist_ok=True)
    _exclude(root).write_text(begin + begin + "# stayfixed:attach:end\n", encoding="utf-8")
    before = _everything(tmp_path)
    with pytest.raises(Refusal) as refused:
        _attach_it(root, store, machine, tmp_path / "home")
    assert "info/exclude" in str(refused.value)
    assert _everything(tmp_path) == before


@pytest.mark.skipif(os.geteuid() == 0, reason="root writes into a directory it cannot write")
def test_an_exclude_file_whose_write_fails_is_a_refusal_naming_it(tmp_path: Path) -> None:
    # The check made while planning cannot rule out a write that fails anyway, and that write used
    # to end as `internal error: PermissionError`. It is a refusal naming the file.
    #
    # Mutation: `mutations/`'s "a failed exclude write is an internal error".
    from stayfixed.attach.exclude import ExcludeWrite, write

    shut = tmp_path / "info"
    shut.mkdir()
    shut.chmod(0o555)
    try:
        with pytest.raises(Refusal) as refused:
            write(ExcludeWrite(shut / "exclude", "/x\n"))
    finally:
        shut.chmod(0o755)
    assert "info/exclude" in str(refused.value)


def test_a_trusted_store_keeps_its_approval_when_attach_renders_its_missing_index(
    tmp_path: Path,
) -> None:
    # A store approved while it had no `MEMORY.md`, which is how a 0.1.x first attach left it,
    # gets its index rendered by the next attach. The render rewrites a file the approval covers,
    # so it carries the approval across its own write, as `memory index` does; without that the
    # re-attach revoked the owner's approval and withheld the harness link with "has no approval
    # yet".
    #
    # Mutation: `mutations/`'s "attach's index render drops the store's approval".
    from stayfixed.config.loader import load
    from stayfixed.memory.api import harness_memory_path, resolve
    from stayfixed.memory.trust import record

    root, store, machine = _attachable(tmp_path, allow=(RULE,))
    home = tmp_path / "home"
    _attach_it(root, store, machine, home)
    (store / "MEMORY.md").unlink()
    config = load(root, machine=machine)
    resolved = resolve(root, config, machine=machine)
    assert resolved is not None
    assert record(resolved, config).trusted
    attached = _attach_it(root, store, machine, home)
    assert (store / "MEMORY.md").is_file()
    assert HARNESS_WAITS not in attached.notes
    assert harness_memory_path(root, home).is_symlink()


def test_a_settings_file_an_earlier_attach_wrote_is_hidden_by_the_next_one(
    tmp_path: Path,
) -> None:
    # The upgrade path: a 0.1.x attach merged the overlay's rules into the settings file and
    # recorded them in its ledger, and kept no exclude block. The next attach, with nothing new
    # to merge, writes no settings, and it is the earlier ledger that says the file is
    # stayfixed's to hide; asked only of this run's writes, the file stayed in `git status`.
    #
    # Mutation: `mutations/`'s "attach forgets the settings file an earlier attach wrote".
    root, store, machine = _attachable(tmp_path, allow=(RULE,))
    _committed(root)
    home = tmp_path / "home"
    _attach_confirmed(root, store, machine, home)
    exclude = _exclude(root)
    exclude.write_text(
        drop(exclude.read_text(encoding="utf-8"), EXCLUDE_REGION, Style.HASH), encoding="utf-8"
    )
    assert not _check_ignore(root, SETTINGS)
    _attach_confirmed(root, store, machine, home)
    assert _check_ignore(root, SETTINGS)


def _exclude_files() -> list[bytes | None]:
    """Every exclude file of up to two pattern lines, each ended by `\\n`, `\\r\\n`, a lone `\\r`
    or `\\r\\r\\n`, with the last one also left unended, plus an absent and an empty file."""
    endings = [b"\n", b"\r\n", b"\r", b"\r\r\n"]
    files: list[bytes | None] = [None, b""]
    for first in endings:
        files += [b"/a0" + first, b"/a0"]
        for second in endings:
            files += [b"/a0" + first + b"/a1" + second, b"/a0" + first + b"/a1"]
    return list(dict.fromkeys(files))


def test_the_exclude_block_hides_what_git_hid_and_gives_every_file_back(tmp_path: Path) -> None:
    # Checked against git itself, not against a model of it: for each exclude file, what git hides
    # with the block is what it hid without it plus the placed path, and taking the block out
    # gives the bytes back. git ends a line at `\n` and then drops one `\r` before it, so a file
    # holding `\r\n` whose last line ended `/a1\r` used to get `\r\n` appended, and git read
    # `/a1\r`, a pattern for another name.
    #
    # Mutations: `mutations/`'s "a hash region ends a line after a lone carriage return with
    # the file's own ending", "detach leaves the newline it added after a lone carriage return"
    # and "detach takes back half the CRLF attach added".
    from stayfixed.attach import exclude

    repo = tmp_path / "r"
    repo.mkdir()
    _git(repo, "init", "-q")
    for name in ("a0", "a1", "linked"):
        (repo / name).write_text("x", encoding="utf-8")
    path = repo / ".git" / "info" / "exclude"

    def hidden() -> set[str]:
        return set(run_git(repo, "check-ignore", "--", "a0", "a1", "linked").stdout.split())

    wrong = []
    for held in _exclude_files():
        if held is None:
            path.unlink(missing_ok=True)
        else:
            path.write_bytes(held)
        before = hidden()
        planned = exclude.planned_block(repo, ["linked"])
        assert planned is not None
        exclude.write(planned)
        with_block = hidden()
        withdrawn = exclude.withdrawn_block(repo)
        assert withdrawn is not None
        exclude.write(withdrawn)
        after = path.read_bytes() if path.exists() else None
        if with_block != before | {"linked"} or after != held:
            wrong.append((held, sorted(before), sorted(with_block), after))
    assert wrong == []


def test_a_doubled_gitignore_region_is_refused_naming_the_file(tmp_path: Path) -> None:
    # "region 'ignore' is opened or closed twice" named the region and not the file it is in.
    #
    # Mutation: `mutations/`'s "a doubled .gitignore region is refused without its file".
    root, store, machine = _attachable(tmp_path, allow=(RULE,))
    begin = "# stayfixed:ignore:begin\n"
    (root / ".gitignore").write_text(begin + begin + "# stayfixed:ignore:end\n", encoding="utf-8")
    before = _everything(tmp_path)
    with pytest.raises(Refusal) as refused:
        _attach_it(root, store, machine, tmp_path / "home")
    assert ".gitignore" in str(refused.value)
    assert _everything(tmp_path) == before


def test_what_pre_commit_prints_cannot_drive_a_terminal(tmp_path: Path) -> None:
    # `pre-commit install`'s answer was quoted raw in the note.
    #
    # Mutation: `mutations/`'s "a subprocess's answer is quoted raw".
    root, store, machine = _attachable(tmp_path)
    _overlay_repository(store.parents[2])
    (store.parents[2] / ".pre-commit-config.yaml").write_text("repos: []\n", encoding="utf-8")
    runner = Recorder(code=1, stderr="boom\n::error::forged\x1b[2J")
    attached = attach(
        root,
        store=store,
        machine=machine,
        confirmed=False,
        trust_remote=False,
        runner=runner,
        home=tmp_path / "home",
    )
    said = " ".join(attached.notes)
    assert "forged" in said
    assert "\n::error::" not in said and "\x1b" not in said
