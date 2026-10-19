# tests/setup/test_setup.py
from __future__ import annotations

import contextlib
import errno
import json
import os
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from stayfixed import gitenv
from stayfixed.attach.api import read_binding
from stayfixed.config.overlay import overlay_root
from stayfixed.errors import Failure, Refusal
from stayfixed.jsonobject import LONG_NUMBER, NESTED
from stayfixed.overlay.api import MARKETPLACE_MANIFEST, PLUGIN_MANIFEST
from stayfixed.presets import load_preset
from stayfixed.printed import quoted
from stayfixed.runner import Completed
from stayfixed.setup.api import USER_SETTINGS, setup
from stayfixed.setup.machine import read_machine, write_machine
from tests import parserlimits
from tests.gitfixture import git as _git
from tests.gitfixture import needs_git, stand_in_git
from tests.parserlimits import overflowing
from tests.pathfaults import (
    ROOT_SEARCHES_EVERYTHING,
    at_mode,
    read_only,
    unsearchable,
    write_only,
)
from tests.runners import Recorder

# The minimal `stayfixed.toml` `attach.read_binding` needs (a project name and nothing else),
# the same shape `tests/setup/test_machine.py::_initialised_project` uses for `load()`.
CONFIG = """
[stayfixed]
version = "0.1.0"
state = "installed"
preset = "recommended"
profile = ""
agents = ["claude"]

[project]
name = "widget"
base_branch = "main"
release_branch = "main"
"""


def _initialised_project(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    project.mkdir()
    (project / "stayfixed.toml").write_text(CONFIG, encoding="utf-8")
    return project


# What `gh repo view <slug> --json isTemplate` answers (measured against gh 2.101.0): a template
# exits 0 with `{"isTemplate":true}`, and a repository that does not exist exits 1 with GraphQL's
# "Could not resolve to a Repository". `overlay create` asks it once to choose whose template to
# generate from, so a `create:` run has to have the probe answered.
_OCTOS_PROBE = "gh repo view octo/stayfixed-overlay-template"
_A_TEMPLATE = Completed(0, '{"isTemplate":true}\n', "")
_NO_SUCH_REPOSITORY = Completed(
    1,
    "",
    "GraphQL: Could not resolve to a Repository with the name 'octo/stayfixed-overlay-template'."
    " (repository)\n",
)


def _populate_overlay(argv: list[str], cwd: Path) -> None:
    """Stand in for a successful template generation, the same probe `overlay.create` reads."""
    if argv[:3] != ["gh", "repo", "create"]:
        return
    target = cwd / argv[3].split("/")[-1] / ".claude-plugin"
    target.mkdir(parents=True, exist_ok=True)
    (target / "plugin.json").write_text(json.dumps({"name": "stayfixed-overlay"}), encoding="utf-8")
    (target / "marketplace.json").write_text(
        json.dumps({"name": "stayfixed-overlay-marketplace", "plugins": []}), encoding="utf-8"
    )


def _seed_overlay(path: Path) -> None:
    """Give `path` the two manifests `overlay.identity.overlay_fault` checks, named the way the
    shipped template names them, without rendering the whole template — enough for a fixture to
    read as a real overlay's root."""
    (path / ".claude-plugin").mkdir(parents=True, exist_ok=True)
    (path / PLUGIN_MANIFEST).write_text(json.dumps({"name": "stayfixed-overlay"}), encoding="utf-8")
    (path / MARKETPLACE_MANIFEST).write_text(
        json.dumps({"name": "stayfixed-overlay-marketplace", "plugins": []}), encoding="utf-8"
    )


def test_setup_writes_the_machine_file_and_the_deny_rules(tmp_path: Path) -> None:
    # Two machine-level writes, both on the enumerated list of what `setup` writes. Assert the
    # machine file round-trips through `read_machine`, and that `<home>/.claude/settings.json` —
    # `setup.api.USER_SETTINGS`, the one machine-scope settings file `setup` writes — carries every
    # rule from the preset's `[deny] global` and no `allow` key at all.
    #
    # Mutation: `_write_user_settings`'s `permissions["deny"] = ...` line changed to write
    # `permissions["allow"]` instead → reddens both assertions below (the deny list goes missing
    # and an allow key appears) — the exact typo the deny-only invariant exists to catch.
    home = tmp_path / "home"
    machine = tmp_path / "config.toml"
    setup(
        "recommended",
        home=home,
        machine=machine,
        runner=Recorder(),
        yes=True,
        overlay=None,
        project_root=tmp_path / "project",
    )
    written = read_machine(machine)
    assert written["personal"]["preset"] == "recommended"
    settings = json.loads((home / USER_SETTINGS).read_text(encoding="utf-8"))
    preset = load_preset("recommended")
    for rule in preset["deny"]["global"]:
        assert rule in settings["permissions"]["deny"]
    assert "allow" not in settings.get("permissions", {})


def test_setup_takes_the_retired_env_masks_back_out_and_keeps_the_owners_rules(
    tmp_path: Path,
) -> None:
    # A machine an older `setup` configured holds `Read(.env*)` and `Read(**/.env*)`, which refuse
    # `.env.example` too, and no allow rule can let it through: the masks have to leave the file,
    # or an upgrade fixes nothing. Removed by their exact strings and nothing else, so the owner's
    # own rules, a near miss among them, stay where they stood.
    # Mutation: `mutations/`'s "setup leaves the retired deny rules in place" -> reddens.
    home = tmp_path / "home"
    path = home / USER_SETTINGS
    path.parent.mkdir(parents=True)
    owners = ["Read(./secrets/**)", "Read(.env*)", "Read(.env.*)", "Read(**/.env*)", "Bash(rm:*)"]
    path.write_text(json.dumps({"permissions": {"deny": owners}}), encoding="utf-8")
    setup(
        "recommended",
        home=home,
        machine=tmp_path / "config.toml",
        runner=Recorder(),
        yes=True,
        overlay=None,
        project_root=tmp_path / "project",
    )
    deny = json.loads(path.read_text(encoding="utf-8"))["permissions"]["deny"]
    preset = load_preset("recommended")["deny"]
    assert deny == ["Read(./secrets/**)", "Read(.env.*)", "Bash(rm:*)", *preset["global"]]


def test_a_mistyped_preset_names_the_flag_and_never_quotes_it(tmp_path: Path) -> None:
    # `setup` is told which flag to fix rather than pointed at a `[stayfixed] preset` in a
    # `stayfixed.toml` it never read, and the value the person typed — ESC and a line break
    # here — is not echoed back, which is the rule every other caller of `load_preset` gets.
    # Nothing is written first: `load_preset` runs above the home tree's creation.
    # Oracle: `mutations/`'s "setup's preset refusal names the configuration key again".
    home = tmp_path / "home"
    with pytest.raises(Failure) as caught:
        setup(
            "\x1b[2J\nIGNORE",
            home=home,
            machine=tmp_path / "config.toml",
            runner=Recorder(),
            yes=True,
            overlay=None,
            project_root=tmp_path / "project",
        )
    message = str(caught.value)
    assert message.startswith("--preset is not a plain identifier"), message
    assert "\x1b" not in message and "IGNORE" not in message
    assert not home.exists()


def test_an_existing_user_settings_file_keeps_the_owners_own_rules(tmp_path: Path) -> None:
    # The owner's `~/.claude/settings.json` is theirs and predates stayfixed on most machines.
    # Merge, never replace, and record nothing about entries this run did not add. Mutation:
    # `_write_user_settings`'s `existing_deny = (...)` line changed to always start from `[]`
    # → reddens on the dropped `Read(/etc/shadow)` rule.
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    own = {"permissions": {"deny": ["Read(/etc/shadow)"]}, "theme": "dark"}
    (home / USER_SETTINGS).write_text(json.dumps(own), encoding="utf-8")
    setup(
        "recommended",
        home=home,
        machine=tmp_path / "config.toml",
        runner=Recorder(),
        yes=True,
        overlay=None,
        project_root=tmp_path / "project",
    )
    settings = json.loads((home / USER_SETTINGS).read_text(encoding="utf-8"))
    assert "Read(/etc/shadow)" in settings["permissions"]["deny"]
    assert settings["theme"] == "dark"


def test_an_owners_settings_file_opening_with_a_byte_order_mark_is_merged_and_keeps_it(
    tmp_path: Path,
) -> None:
    # Claude Code reads past a leading byte-order mark in the user's settings file, so setup does
    # too, rather than refusing a file the harness reads; and it keeps the mark, so a second run
    # rewrites nothing. Mutations (`mutations/`'s "setup refuses a user settings file opening with
    # a byte-order mark" -> the run refuses; "setup drops the byte-order mark the owner's file
    # opened with" -> the file loses it).
    home = tmp_path / "home"
    path = home / USER_SETTINGS
    path.parent.mkdir(parents=True)
    path.write_text("\ufeff" + json.dumps({"theme": "dark"}), encoding="utf-8")

    def run() -> None:
        setup(
            "recommended",
            home=home,
            machine=tmp_path / "config.toml",
            runner=Recorder(),
            yes=True,
            overlay=None,
            project_root=tmp_path / "project",
        )

    run()
    text = path.read_text(encoding="utf-8")
    assert text.startswith("\ufeff")
    assert json.loads(text.removeprefix("\ufeff"))["theme"] == "dark"
    before = path.read_bytes()
    run()
    assert path.read_bytes() == before


@pytest.mark.parametrize(
    ("document", "clause"),
    [(parserlimits.NESTED, NESTED), ('{"n": ' + parserlimits.LONG_NUMBER + "}", LONG_NUMBER)],
    ids=["nested", "long-number"],
)
def test_a_user_settings_file_past_the_parsers_reach_is_a_failure_naming_it(
    tmp_path: Path, document: str, clause: str
) -> None:
    # Both documents are valid JSON, and `json.loads` meets neither with the `JSONDecodeError` the
    # reader caught: nesting past what it follows raises `RecursionError`, and an integer longer
    # than the interpreter converts (4,300 digits by default) a plain `ValueError`. Either ended
    # `stayfixed setup` in an internal error. The file is the owner's, and setup rewrites it, so it
    # is refused rather than read. Mutation (advisory): `_read_document` parses with `json.loads`
    # again -> the `Failure` is never raised and this reddens.
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    (home / USER_SETTINGS).write_text(document, encoding="utf-8")
    with pytest.raises(Failure) as caught:
        setup(
            "recommended",
            home=home,
            machine=tmp_path / "config.toml",
            runner=Recorder(),
            yes=True,
            overlay=None,
            project_root=tmp_path / "project",
        )
    assert str(caught.value) == f"{home / USER_SETTINGS} {clause}"
    assert (home / USER_SETTINGS).read_text(encoding="utf-8") == document


@pytest.mark.skipif(os.geteuid() == 0, reason="root reads every file")
def test_a_user_settings_file_that_cannot_be_read_is_a_failure_saying_why_in_words(
    tmp_path: Path,
) -> None:
    # The failure quoted the error whole, `[Errno 13] Permission denied: '<the path again>'`,
    # where every other reader of a file says its reason in words, in parentheses (`fsops.said`).
    # A file at mode 000: a directory at that path is refused before the first write now. Mutation
    # (oracle): `mutations/`'s "a read refusal says an unreadable file in its error's own text".
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    (home / USER_SETTINGS).write_text("{}\n", encoding="utf-8")
    with at_mode(home / USER_SETTINGS, 0, after=0o644), pytest.raises(Failure) as caught:
        setup(
            "recommended",
            home=home,
            machine=tmp_path / "config.toml",
            runner=Recorder(),
            yes=True,
            overlay=None,
            project_root=tmp_path / "project",
        )
    assert (
        str(caught.value) == f"{home / USER_SETTINGS} cannot be read ({os.strerror(errno.EACCES)})"
    )


def test_every_plugin_install_is_one_recorded_argv(tmp_path: Path) -> None:
    # The Runner seam again. Two things could be wrong here that only an argv assertion can see: the
    # marketplace must be registered *before* anything is installed from it (a fresh machine cannot
    # install a plugin from a marketplace it never added), and the install call itself must carry
    # none of the unmeasured `--scope`/`-y` flags the first draft guessed.
    runner = Recorder()
    setup(
        "recommended",
        home=tmp_path / "home",
        machine=tmp_path / "config.toml",
        runner=runner,
        yes=True,
        overlay=None,
        project_root=tmp_path / "project",
    )
    preset = load_preset("recommended")
    claude = preset["plugins"]["claude"]
    add = ["claude", "plugin", "marketplace", "add", claude["source"]]
    installs = [
        ["claude", "plugin", "install", f"{selector}@{claude['marketplace']}"]
        for selector in preset["plugins"]["install"]
    ]
    # **Order, not membership.** `… in runner.calls` is a set question, and the thing this test is
    # named for is a sequence: the reviewer swapped the two loops in `_install_plugins` so every
    # install ran before its marketplace was registered -- the exact defect the first draft shipped
    # -- and both assertions still passed, because both calls were still made. `mutations/`'s
    # "a plugin is installed before its marketplace is registered" carries the swap.
    assert installs, "the preset installs nothing, so the ordering below measures nothing"
    assert add in runner.calls
    for install in installs:
        assert install in runner.calls
        assert runner.calls.index(add) < runner.calls.index(install), runner.calls
    # Codex has no verified marketplace for these two plugins: nothing is attempted.
    assert not any(argv and argv[0] == "codex" for argv in runner.calls)


def test_a_selector_the_marketplace_does_not_carry_is_a_note_naming_the_argv(
    tmp_path: Path,
) -> None:
    # `_install_plugins`' install-failure branch, which no test in this file could reach: with
    # `answers` keyed on `argv[0]`, `"claude"` answered the `marketplace add` too, so the run
    # `continue`d and never attempted an install at all. This is the likelier of the two real
    # failures -- the marketplace is registered and simply does not carry the selector the
    # preset names -- and `setup` must report it and finish, not raise and not claim it
    # installed.
    #
    # Mutation: `_install_plugins`' `notes.append(f"{agent}: `{' '.join(argv)}` did not
    # succeed ({detail})")` replaced by `pass` -> reddens on the missing note, while
    # `plugins_installed` stays empty, which is what makes the two assertions different
    # questions rather than one asked twice.
    preset = load_preset("recommended")
    claude = preset["plugins"]["claude"]
    selector = preset["plugins"]["install"][0]
    full = f"{selector}@{claude['marketplace']}"
    runner = Recorder(
        answers={
            f"claude plugin install {full}": Completed(1, "", f"no plugin named {selector} here")
        }
    )
    report = setup(
        "recommended",
        home=tmp_path / "home",
        machine=tmp_path / "config.toml",
        runner=runner,
        yes=True,
        overlay=None,
        project_root=tmp_path / "project",
    )
    assert ["claude", "plugin", "marketplace", "add", claude["source"]] in runner.calls
    assert ["claude", "plugin", "install", full] in runner.calls
    assert selector not in report.plugins_installed
    # The other selector still installs: one failure is one note, never an abandoned run.
    assert preset["plugins"]["install"][1] in report.plugins_installed
    assert any(f"claude plugin install {full}" in note for note in report.notes), report.notes
    assert any("no plugin named" in note for note in report.notes), report.notes


@pytest.mark.parametrize("step", ["marketplace add", "install"])
def test_what_a_plugin_command_prints_cannot_drive_a_terminal(tmp_path: Path, step: str) -> None:
    # A plugin command's answer was quoted raw in the note: a line break followed by `::error::`
    # is a workflow command in a CI log, and an escape sequence drives a terminal.
    #
    # Mutation: `mutations/`'s "a subprocess's answer is quoted raw".
    runner = Recorder(
        answers={f"claude plugin {step}": Completed(1, "", "boom\n::error::forged\x1b[2J")}
    )
    report = setup(
        "recommended",
        home=tmp_path / "home",
        machine=tmp_path / "config.toml",
        runner=runner,
        yes=True,
        overlay=None,
        project_root=tmp_path / "project",
    )
    said = " ".join(report.notes)
    assert "forged" in said
    assert "\n::error::" not in said and "\x1b" not in said


def test_codex_gets_a_note_naming_the_unverified_plugins_rather_than_silence(
    tmp_path: Path,
) -> None:
    # A harness this preset cannot install for on a verified path is a reported note, never silence
    # and never a failure. `agents = ["claude", "codex"]` is the preset's own default, so an
    # ordinary run reaches this for every machine that has Codex configured.
    preset = load_preset("recommended")
    report = setup(
        "recommended",
        home=tmp_path / "home",
        machine=tmp_path / "config.toml",
        runner=Recorder(),
        yes=True,
        overlay=None,
        project_root=tmp_path / "project",
    )
    expected = (
        f"codex: no verified marketplace for {', '.join(preset['plugins']['install'])}; "
        f"install manually if this harness supports it (see README)"
    )
    assert expected in report.notes


def test_a_harness_that_is_not_installed_is_a_note_not_a_failure(tmp_path: Path) -> None:
    # A missing `claude` binary must never turn a fresh-machine `setup` into a traceback — the
    # marketplace-add call is the first one this harness makes, and it is where a missing
    # binary would surface (`Runner` turns it into `Completed(127, ...)`).
    #
    # No mutation: this is `Runner`'s own fail-soft convention (a non-zero result is a note,
    # per `stayfixed.runner.Runner`'s own docstring), exercised here through the `Recorder`'s
    # script rather than guarding one line of this module's own whose removal would look like
    # a plausible bug — the "non-zero becomes a note" shape is `_install_plugins`' whole
    # structure, not a single guardable line.
    runner = Recorder(answers={"claude": Completed(127, "", "claude: command not found")})
    report = setup(
        "recommended",
        home=tmp_path / "home",
        machine=tmp_path / "config.toml",
        runner=runner,
        yes=True,
        overlay=None,
        project_root=tmp_path / "project",
    )
    assert any("claude" in note for note in report.notes)
    assert report.plugins_installed == ()


def test_the_overlay_offer_is_never_taken_without_being_asked(tmp_path: Path) -> None:
    # `overlay create` runs `gh repo create` only after explicit confirmation. A default that
    # creates a GitHub repository is the one default this command may not have — and `--yes`, which
    # confirms creating one, must not stand in for naming one.
    #
    # Mutation: `setup`'s `if overlay is not None:` changed to `if True:` → reddens (the call
    # then reaches `_apply_overlay(None, ...)`, which is exactly the "taken without being
    # asked" shape this test exists to catch — `overlay=None` runs anyway).
    runner = Recorder()
    report = setup(
        "recommended",
        home=tmp_path / "home",
        machine=tmp_path / "config.toml",
        runner=runner,
        yes=True,
        overlay=None,
        project_root=tmp_path / "project",
    )
    assert report.overlay is None
    assert not any(argv[:2] == ["gh", "repo"] for argv in runner.calls)


# Asks `_requested_overlay` the question a `setup` with no `--overlay` asks, in a clean interpreter,
# and prints every module of the overlay area that loaded.
_ASK_WITH_NO_OVERLAY = (
    "import sys\n"
    "from pathlib import Path\n"
    "from stayfixed.setup.run import _requested_overlay\n"
    "here = Path(sys.argv[1])\n"
    "assert _requested_overlay(None, home=here, yes=True) is None\n"
    "print(' '.join(m for m in sorted(sys.modules) if m.startswith('stayfixed.overlay')))\n"
)


def test_setup_with_no_overlay_never_loads_the_overlay_area(tmp_path: Path) -> None:
    # `setup --overlay` is the one crossing from the core into delivery, and the core loads the
    # private layer only when that flag asks for it (CONTRIBUTING.md, "Areas"). The import stood
    # above the early return for a run with no `--overlay`, so every such `setup` loaded the
    # overlay area anyway. A clean interpreter, because this suite has long since imported it.
    # Mutation (oracle): `mutations/`'s "setup loads the overlay area with no --overlay again" ->
    # `stayfixed.overlay.api` is printed.
    source = Path(__file__).resolve().parents[2] / "src"
    completed = subprocess.run(
        [sys.executable, "-c", _ASK_WITH_NO_OVERLAY, str(tmp_path)],
        capture_output=True,
        text=True,
        check=False,
        env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(source)},
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.split() == []


def test_pointing_at_an_existing_overlay_records_its_root_and_creates_nothing(
    tmp_path: Path,
) -> None:
    # The second of the three answers to where the overlay is — create one, record an existing one,
    # or pass no `--overlay` — and the answer a second machine gives: the overlay already exists
    # and is cloned, and `setup` only records it.
    existing = tmp_path / "overlay"
    existing.mkdir()
    _seed_overlay(existing)
    machine = tmp_path / "config.toml"
    runner = Recorder()
    report = setup(
        "recommended",
        home=tmp_path / "home",
        machine=machine,
        runner=runner,
        yes=True,
        overlay=str(existing),
        project_root=tmp_path / "project",
    )
    assert report.overlay == existing
    assert not any(argv[:2] == ["gh", "repo"] for argv in runner.calls)
    assert overlay_root(machine) == existing


def test_an_overlay_missing_the_layout_is_refused(tmp_path: Path) -> None:
    # The overlay root is the machine's trust anchor, so an arbitrary directory that merely happens
    # to exist must not become one. `existing` here is empty — no `.claude-plugin/plugin.json`, no
    # `marketplace.json` — which is exactly the shape a careless `--overlay /tmp/whatever` would
    # have.
    #
    # Mutation (`mutations/`'s "the overlay probe stops looking for the manifests at all"):
    # `overlay.identity.overlay_fault` stops iterating the manifests → an empty directory is
    # accepted as an overlay root and this reddens.
    empty = tmp_path / "not-an-overlay"
    empty.mkdir()
    with pytest.raises(Refusal, match="does not carry the overlay layout"):
        setup(
            "recommended",
            home=tmp_path / "home",
            machine=tmp_path / "config.toml",
            runner=Recorder(),
            yes=True,
            overlay=str(empty),
            project_root=tmp_path / "project",
        )


@needs_git
def test_an_overlay_inside_the_project_root_is_refused(tmp_path: Path) -> None:
    # The other half, and the control that actually binds: a path outside the repository that
    # already carries a real overlay layout is not something a hostile clone can create, but a path
    # *inside* the repository is exactly the shape of tree a clone can ship — so recording one there
    # is refused regardless of how convincing its layout is. A repository, because containment is
    # judged against the repository `--root` is in: a directory in none ships nothing.
    #
    # Mutation (`mutations/`'s "setup stops refusing an overlay root inside the project"):
    # `_overlaps` stops looking above the candidate -> the path arm and the checkout listing both
    # pass it, and the refusal that is left, the candidate-side walk's, does not name `--root`, so
    # this reddens on the match.
    project = tmp_path / "project"
    project.mkdir()
    _git(project, "init", "-q", "-b", "main")
    nested = project / "vendored-overlay"
    nested.mkdir()
    _seed_overlay(nested)
    with pytest.raises(Refusal, match="holds it, or is it"):
        setup(
            "recommended",
            home=tmp_path / "home",
            machine=tmp_path / "config.toml",
            runner=Recorder(),
            yes=True,
            overlay=str(nested),
            project_root=project,
        )


def test_overlay_create_asks_github_and_records_the_new_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The first of `--overlay`'s three answers: nothing exists yet, so `setup` both creates the
    # repository and records what it created — the same probe `overlay.create` uses
    # (`.claude-plugin`) is what tells this test the create branch, and not a no-op, ran.
    #
    # `home`, and not `Path.cwd()`, is asserted here rather than merely the leaf name: measured
    # while writing this module, `root=Path.cwd()` created a real `stayfixed-private/` inside
    # this checkout the first time this branch ran under a test, because `tmp_path` was never
    # in that call at all. Mutation: change `_apply_overlay`'s `root=home` back to
    # `root=Path.cwd()` → reddens on this line without touching the `.name` check alone.
    #
    # `monkeypatch.chdir(tmp_path)` is not decoration: it is what keeps that exact mutation's
    # own oracle run from recreating the real directory a second time — under the mutation,
    # the create call falls back to `Path.cwd()`, and this way that lands inside `tmp_path`
    # instead of wherever the process happened to be running from.
    monkeypatch.chdir(tmp_path)
    home = tmp_path / "home"
    machine = tmp_path / "config.toml"
    runner = Recorder(answers={_OCTOS_PROBE: _A_TEMPLATE}, on_call=_populate_overlay)
    report = setup(
        "recommended",
        home=home,
        machine=machine,
        runner=runner,
        yes=True,
        overlay="create:octo/stayfixed-private",
        project_root=tmp_path / "project",
    )
    assert any(argv[:3] == ["gh", "repo", "create"] for argv in runner.calls)
    assert report.overlay == home / "stayfixed-private"
    assert overlay_root(machine) == report.overlay


@pytest.mark.parametrize(
    ("probe", "template"),
    [
        pytest.param(_A_TEMPLATE, "octo/stayfixed-overlay-template", id="the-owners-own"),
        pytest.param(
            _NO_SUCH_REPOSITORY,
            "github.com/stayfixed/stayfixed-overlay-template",
            id="the-publishers",
        ),
    ],
)
def test_overlay_create_generates_from_the_template_overlay_create_would_choose(
    tmp_path: Path, probe: Completed, template: str
) -> None:
    # `--overlay create:` calls `overlay.create`, so a user with no template of their own reaches
    # the publisher's the same way `overlay create --template` does. One resolution, two commands:
    # a second copy of it here would be the place they drift. Mutation: the `setup` call passes a
    # template of its own → one of the two cases reddens.
    home = tmp_path / "home"
    runner = Recorder(answers={_OCTOS_PROBE: probe}, on_call=_populate_overlay)
    setup(
        "recommended",
        home=home,
        machine=tmp_path / "config.toml",
        runner=runner,
        yes=True,
        overlay="create:octo/stayfixed-private",
        project_root=tmp_path / "project",
    )
    creating = next(argv for argv in runner.calls if argv[:3] == ["gh", "repo", "create"])
    assert creating[creating.index("--template") + 1] == template


def test_overlay_create_that_cannot_ask_gh_whose_template_creates_nothing(
    tmp_path: Path,
) -> None:
    # A probe that failed for a reason other than "not found" never becomes a repository on the
    # publisher's template: `gh repo create` is the one irreversible act `setup` performs.
    home = tmp_path / "home"
    runner = Recorder(
        answers={_OCTOS_PROBE: Completed(1, "", "HTTP 401: Bad credentials")},
        on_call=_populate_overlay,
    )
    with pytest.raises(Failure, match="Bad credentials"):
        setup(
            "recommended",
            home=home,
            machine=tmp_path / "config.toml",
            runner=runner,
            yes=True,
            overlay="create:octo/stayfixed-private",
            project_root=tmp_path / "project",
        )
    assert not any(argv[:3] == ["gh", "repo", "create"] for argv in runner.calls)


def test_rerunning_overlay_create_over_an_existing_overlay_creates_nothing_and_names_no_template(
    tmp_path: Path,
) -> None:
    # Re-running `setup --overlay create:` after the first run is the ordinary case, and `create`
    # answers a populated destination with no `gh` call and no template. The report used to say
    # "generated from None". Mutation: drop the `created.template is None` branch in
    # `_apply_overlay` and the report reads "created the overlay ... generated from None".
    home = tmp_path / "home"
    machine = tmp_path / "config.toml"
    destination = home / "stayfixed-private"
    _seed_overlay(destination)
    runner = Recorder(answers={_OCTOS_PROBE: _A_TEMPLATE}, on_call=_populate_overlay)
    report = setup(
        "recommended",
        home=home,
        machine=machine,
        runner=runner,
        yes=True,
        overlay="create:octo/stayfixed-private",
        project_root=tmp_path / "project",
    )
    assert not any(argv[:3] == ["gh", "repo", "create"] for argv in runner.calls)
    assert not any(argv[:3] == ["gh", "repo", "view"] for argv in runner.calls)
    text = " ".join(str(value) for value in vars(report).values() if value is not None)
    assert "None" not in text
    assert "already" in " ".join(report.notes)
    assert overlay_root(machine) == destination


def test_rerunning_overlay_create_says_what_init_changed_in_the_overlay_it_found(
    tmp_path: Path,
) -> None:
    # The re-run runs `overlay init` on the overlay it found, and `init` may rename its manifests
    # (an overlay named at 0.1.x has no account in them yet) or remove the old memory README. The
    # report said "found the overlay ... and left it alone" all the same. It names what `init`
    # changed now, and says nothing was changed only when nothing was.
    #
    # Mutation: `mutations/`'s "setup says it left alone an overlay init changed".
    home = tmp_path / "home"
    machine = tmp_path / "config.toml"
    _seed_overlay(home / "stayfixed-private")

    def overlay_note() -> str:
        runner = Recorder(answers={_OCTOS_PROBE: _A_TEMPLATE}, on_call=_populate_overlay)
        report = setup(
            "recommended",
            home=home,
            machine=machine,
            runner=runner,
            yes=True,
            overlay="create:octo/stayfixed-private",
            project_root=tmp_path / "project",
        )
        return next(note for note in report.notes if "found the overlay" in note)

    first = overlay_note()
    assert "left it alone" not in first
    assert PLUGIN_MANIFEST in first and MARKETPLACE_MANIFEST in first
    second = overlay_note()
    assert PLUGIN_MANIFEST not in second
    assert "changed none of the overlay's tracked files" in second


def test_creating_an_overlay_without_yes_is_refused(tmp_path: Path) -> None:
    # Creating a repository on GitHub is the one irreversible, outward-facing act `setup` performs,
    # and `gh repo create` runs only after explicit confirmation. Naming `create:<owner>/<name>` is
    # not that confirmation by itself — `--yes` is.
    #
    # Mutation: `_apply_overlay`'s `if not yes:` line changed to `if False:` → reddens (the
    # repository would then be created without `--yes`).
    runner = Recorder(on_call=_populate_overlay)
    with pytest.raises(Refusal, match="explicit confirmation"):
        setup(
            "recommended",
            home=tmp_path / "home",
            machine=tmp_path / "config.toml",
            runner=runner,
            yes=False,
            overlay="create:octo/stayfixed-private",
            project_root=tmp_path / "project",
        )
    assert not any(argv[:3] == ["gh", "repo", "create"] for argv in runner.calls)


def test_the_recorded_overlay_root_is_accepted_inside_and_refused_outside_by_attach(
    tmp_path: Path,
) -> None:
    # The seam between `setup` and `attach`, asserted rather than assumed — and asserted through
    # both halves, which is what makes it the seam and not a guess: `setup --overlay <path>` records
    # a root, and `attach.read_binding` must accept a `--store` that is that root's own share for
    # this project and refuse, by the specific "own directory inside the overlay" guard, one that is
    # not. A bare `pytest.raises(Refusal)` with no message match could not tell that guard apart
    # from any other refusal `read_binding` might raise for an unrelated reason.
    #
    # No new entry in `mutations/`: the guard both arms exercise is `binding.py`'s own
    # store-must-match-`permitted_roots` check, already load-bearing as `mutations/`'s "attach takes
    # the overlay root from its argument instead of the machine file" — this test proves the two
    # ends of the seam agree, not a new line to mutate.
    existing = tmp_path / "overlay"
    existing.mkdir()
    _seed_overlay(existing)
    machine = tmp_path / "config.toml"
    setup(
        "recommended",
        home=tmp_path / "home",
        machine=machine,
        runner=Recorder(),
        yes=True,
        overlay=str(existing),
        project_root=tmp_path / "project",
    )
    project = _initialised_project(tmp_path)

    good_store = existing / "projects" / "widget" / "memory"
    binding = read_binding(project, store=good_store, machine=machine)
    assert binding.overlay == existing

    wrong_store = tmp_path / "elsewhere" / "memory"
    with pytest.raises(Refusal, match="own directory inside the overlay"):
        read_binding(project, store=wrong_store, machine=machine)


def test_a_second_run_is_idempotent(tmp_path: Path) -> None:
    # Two runs, one report each; the second installs no plugin twice and leaves the deny list
    # the same length.
    #
    # No mutation: idempotence here is an emergent property of guards this file already tests on
    # their own (the deny merge's `existing_deny`, and `write_machine`'s overlay-preserving
    # read-back) run twice, not a separate line of its own.
    home = tmp_path / "home"
    machine = tmp_path / "config.toml"
    runner = Recorder()
    first = setup(
        "recommended",
        home=home,
        machine=machine,
        runner=runner,
        yes=True,
        overlay=None,
        project_root=tmp_path / "project",
    )
    second = setup(
        "recommended",
        home=home,
        machine=machine,
        runner=runner,
        yes=True,
        overlay=None,
        project_root=tmp_path / "project",
    )
    assert sorted(first.plugins_installed) == sorted(second.plugins_installed)
    settings = json.loads((home / USER_SETTINGS).read_text(encoding="utf-8"))
    preset = load_preset("recommended")
    assert len(settings["permissions"]["deny"]) == len(preset["deny"]["global"])


def test_a_second_run_does_not_reset_a_personal_value_the_owner_set(tmp_path: Path) -> None:
    # `[personal]` is the preset's `[defaults.personal]` overlaid by anything the caller passed — a
    # preset default must never win over a value already recorded, whether that value came from the
    # owner's own hand or from an earlier `setup` run.
    #
    # Mutation: `_new_personal_values`'s `return {k: v for k, v in ... if k not in existing}`
    # changed to `return _personal_defaults(preset)` → reddens (the owner's "ru" is overwritten
    # back to the preset's own "").
    home = tmp_path / "home"
    machine = tmp_path / "config.toml"
    runner = Recorder()
    setup(
        "recommended",
        home=home,
        machine=machine,
        runner=runner,
        yes=True,
        overlay=None,
        project_root=tmp_path / "project",
    )
    # The owner sets a personal value by hand between two runs.
    write_machine(machine, personal={"preset": "mine"}, overlay_root=None, machine={})
    setup(
        "recommended",
        home=home,
        machine=machine,
        runner=runner,
        yes=True,
        overlay=None,
        project_root=tmp_path / "project",
    )
    assert read_machine(machine)["personal"]["preset"] == "mine"


def test_a_malformed_overlay_spec_is_refused(tmp_path: Path) -> None:
    # `--overlay create:` with no slash, or a missing owner or name, is a typo — not a path to
    # try to interpret and not a repository to create somewhere unexpected.
    #
    # No mutation: this is ordinary input validation on a value only the operator types
    # (`owner, sep, name = spec.partition("/")`), not a trust-boundary guard something
    # downstream reads as permission — the guards the oracle curates for are the overlay-layout
    # and containment checks above, which this same branch also runs.
    with pytest.raises(Refusal):
        setup(
            "recommended",
            home=tmp_path / "home",
            machine=tmp_path / "config.toml",
            runner=Recorder(),
            yes=True,
            overlay="create:no-slash-here",
            project_root=tmp_path / "project",
        )


def test_a_missing_stayfixed_on_path_is_a_note(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # `uv tool install` has no `--from`, so the positional git URL form pinned to a release tag
    # (principle 9: the CLI installs from a git tag) is what the note must name; asserted here
    # rather than left to eyeballing, since it is the one line a typo in the URL or the tag would
    # hide from every other test in this module.
    monkeypatch.setattr("shutil.which", lambda name: None)
    report = setup(
        "recommended",
        home=tmp_path / "home",
        machine=tmp_path / "config.toml",
        runner=Recorder(),
        yes=True,
        overlay=None,
        project_root=tmp_path / "project",
    )
    assert report.cli_on_path is False
    assert any(
        "uv tool install git+https://github.com/stayfixed/stayfixed@v" in n for n in report.notes
    )


# --- everything structural, above the first write ---


def _wrote_anything(home: Path, machine: Path) -> list[str]:
    """What a run left behind on this machine: the two files `setup` writes, by name.

    A list rather than a boolean so a failing assertion says *which* file survived a refusal,
    and asserted non-empty by a companion test below — a check that a refused run wrote nothing
    proves nothing unless the same fixture, unrefused, writes something.
    """
    return [str(path) for path in (machine, home / USER_SETTINGS) if path.is_file()]


def test_a_refused_overlay_path_is_refused_before_the_first_write(tmp_path: Path) -> None:
    # `--overlay /typo` used to be validated at the very bottom of `setup`: a stub runner recorded
    # the marketplace add and both plugin installs, the machine file and `~/.claude/settings.json`
    # were both on disk, and only then did `Refusal: /typo is not a directory` propagate — with the
    # `SetupReport` discarded, so the caller saw only the refusal and never a word about what had
    # already happened. A purely structural check on a caller-supplied path belongs above the first
    # write.
    #
    # Mutation (`mutations/`'s "setup asks whether --overlay is an overlay after it has
    # already written"): the hoisted `_requested_overlay` call is replaced by one that trusts
    # the path, leaving only `_apply_overlay`'s floor → the refusal still arrives, and this
    # reddens on the two files and the argv.
    home = tmp_path / "home"
    machine = tmp_path / "config.toml"
    runner = Recorder()
    with pytest.raises(Refusal, match="is not a directory"):
        setup(
            "recommended",
            home=home,
            machine=machine,
            runner=runner,
            yes=True,
            overlay=str(tmp_path / "typo"),
            project_root=tmp_path / "project",
        )
    assert _wrote_anything(home, machine) == []
    assert runner.calls == [], "no plugin was installed for a run that refuses its own arguments"


@pytest.mark.parametrize(
    "overlay",
    [
        pytest.param(os.fsdecode(b"/overlays/caf\xe9"), id="path"),
        pytest.param("create:octo/stayfixed-private", id="create"),
    ],
)
def test_an_overlay_root_a_utf_8_file_cannot_record_is_refused_before_the_first_write(
    tmp_path: Path, overlay: str
) -> None:
    # The machine file is UTF-8 TOML, and the overlay root is written into it last: on Linux an
    # overlay under a directory named in latin-1 bytes ended `setup --overlay` as `internal
    # error: UnicodeEncodeError`, after the machine file's other tables and the settings file
    # were already written (reproduced in a Linux container). Refused with the tree checks,
    # above every write, and before `gh repo create` for a created one, whose root lies under
    # `home`. Built from the path alone, because APFS refuses such a name. Mutation (declared):
    # drop the check -> the other refusals answer, or the write crashes, and this reddens.
    home = Path(os.fsdecode(os.fsencode(tmp_path) + b"/home-caf\xe9"))
    machine = tmp_path / "config.toml"
    runner = Recorder()
    with pytest.raises(Refusal, match="not UTF-8"):
        setup(
            "recommended",
            home=home,
            machine=machine,
            runner=runner,
            yes=True,
            overlay=overlay,
            project_root=tmp_path / "project",
        )
    assert _wrote_anything(home, machine) == []
    assert runner.calls == []


def test_the_same_fixture_without_the_typo_writes_both_files(tmp_path: Path) -> None:
    # The non-vacuity guard under the test above: the assertions there are about a *refused*
    # run, and they would pass just as well if `setup` wrote nothing under any circumstances.
    home = tmp_path / "home"
    machine = tmp_path / "config.toml"
    existing = tmp_path / "overlay"
    existing.mkdir()
    _seed_overlay(existing)
    runner = Recorder()
    setup(
        "recommended",
        home=home,
        machine=machine,
        runner=runner,
        yes=True,
        overlay=str(existing),
        project_root=tmp_path / "project",
    )
    assert _wrote_anything(home, machine) == [str(machine), str(home / USER_SETTINGS)]
    assert runner.calls != []


@needs_git
def test_a_created_overlay_is_refused_before_the_repository_exists(tmp_path: Path) -> None:
    # The most serious of the structural checks that used to run too late: the documented command
    # run from `$HOME` — `--root` defaulting to `.` — created the private repository on GitHub,
    # cloned it, renamed both manifests and installed the secret scan, and *then* refused, because
    # `home/<name>` lies inside the "project root" that `--root` had defaulted to. The machine file
    # was left with no `[overlay]` table and nothing told the owner the repository now existed.
    # `home/<name>` needs no created tree: it is `overlay.api.target_root`'s answer, known from the
    # arguments alone.
    #
    # The refusal is for a home that is a repository — a dotfiles work tree, which could ship the
    # tree `create:` would clone into it. A home in no repository is not refused at all:
    # `test_an_overlay_created_from_a_directory_in_no_repository_passes_containment`.
    #
    # Mutation (`mutations/`'s "setup computes where a created overlay lands only after creating
    # it"): `_before_the_first_write` asks where the overlay lies only for `--overlay <path>`,
    # leaving `_apply_overlay`'s floor → `gh repo create` runs, and this reddens on the argv
    # assertion.
    home = tmp_path / "home"
    home.mkdir()
    _git(home, "init", "-q", "-b", "main")
    machine = tmp_path / "config.toml"
    # The template probe answered, so under the mutation `gh repo create` really runs and the
    # floor's refusal follows it, as it did on the owner's machine.
    runner = Recorder(answers={_OCTOS_PROBE: _A_TEMPLATE}, on_call=_populate_overlay)
    with pytest.raises(Refusal, match="is inside"):
        setup(
            "recommended",
            home=home,
            machine=machine,
            runner=runner,
            yes=True,
            overlay="create:octo/stayfixed-private",
            project_root=home,
        )
    assert not any(argv[:3] == ["gh", "repo", "create"] for argv in runner.calls)
    assert not (home / "stayfixed-private").exists()
    assert _wrote_anything(home, machine) == []


@needs_git
def test_an_overlay_created_from_a_directory_in_no_repository_passes_containment(
    tmp_path: Path,
) -> None:
    # The owner's own documented command, `stayfixed setup --overlay create:<owner>/<name> --yes`
    # run in `~`: `--root` defaults to `.`, the home directory, and `home/<name>` lies inside it, so
    # the path comparison refused it — although `~` is in no repository and the destination is
    # one this run makes, which nothing can have shipped. With `--root` in no repository a
    # `create:` destination that is not there yet is not compared with it. Mutation
    # (`mutations/`'s "setup compares a created overlay's place with --root outside any
    # repository"): the path arm compares every overlay, as it did before -> refused, and this
    # reddens.
    #
    # Run again, the clone it made is a checkout of its own, as `gh repo create --clone` leaves
    # it, and the overlay root the machine file records: that checkout is not a repository
    # holding the overlay, and the recorded root is not compared with `--root` either, so the
    # second run creates nothing and records the same root. Mutations (`mutations/`'s "setup asks
    # whether an overlay lies in another repository from the overlay itself" -> the clone
    # answers for itself and the second run is refused; "setup stops exempting the overlay root
    # the machine file records" -> the second run is refused by the path arm).
    home = tmp_path / "home"
    home.mkdir()
    machine = tmp_path / "config.toml"
    runner = Recorder(answers={_OCTOS_PROBE: _A_TEMPLATE}, on_call=_populate_overlay)
    setup(
        "recommended",
        home=home,
        machine=machine,
        runner=runner,
        yes=True,
        overlay="create:octo/stayfixed-private",
        project_root=home,
    )
    assert any(argv[:3] == ["gh", "repo", "create"] for argv in runner.calls)
    clone = home / "stayfixed-private"
    _git(clone, "init", "-q", "-b", "main")
    again = Recorder(answers={_OCTOS_PROBE: _A_TEMPLATE}, on_call=_populate_overlay)
    setup(
        "recommended",
        home=home,
        machine=machine,
        runner=again,
        yes=True,
        overlay="create:octo/stayfixed-private",
        project_root=home,
    )
    assert not any(argv[:3] == ["gh", "repo", "create"] for argv in again.calls)
    assert overlay_root(machine) == clone


@needs_git
@pytest.mark.parametrize("planted", ["plain", "own-checkout", "root-inside-it"])
def test_a_created_overlays_destination_already_there_and_not_recorded_is_compared_with_the_root(
    tmp_path: Path, planted: str
) -> None:
    # `create:` leaves a populated destination alone and records it, so a tree someone else put at
    # `<home>/<name>` — an archive's, a checkout of its own — was recorded with no comparison when
    # `--root` is in no repository, and `overlay init` ran in it. The destination is exempt only
    # when this run makes it (it is not there when the phase asks) or when it is the overlay root
    # the machine file already records; anything else is compared as `--overlay <path>` is.
    # Mutation (`mutations/`'s "setup exempts a created overlay's destination that is already
    # there") -> each is recorded and reddens.
    home = tmp_path / "home"
    destination = home / "stayfixed-private"
    _seed_overlay(destination)
    if planted == "own-checkout":
        _git(destination, "init", "-q", "-b", "main")
    root = destination / "sub" if planted == "root-inside-it" else home
    root.mkdir(exist_ok=True)
    machine = tmp_path / "config.toml"
    runner = Recorder(answers={_OCTOS_PROBE: _A_TEMPLATE}, on_call=_populate_overlay)
    with pytest.raises(Refusal, match="holds it, or is it"):
        setup(
            "recommended",
            home=home,
            machine=machine,
            runner=runner,
            yes=True,
            overlay="create:octo/stayfixed-private",
            project_root=root,
        )
    assert runner.calls == [] and not machine.exists()
    manifest = json.loads((destination / PLUGIN_MANIFEST).read_text(encoding="utf-8"))
    assert manifest["name"] == "stayfixed-overlay", "overlay init ran in the planted tree"


def test_a_created_overlays_destination_that_appears_after_the_phase_is_compared_before_init(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The phase found nothing at `<home>/<name>`, and a tree arrived before `create:` reached it:
    # `create` leaves it alone, so this run did not make it, and the exemption the phase gave an
    # absent destination does not carry over to it. It is compared where the overlay is first
    # touched, before `overlay init` writes in it or runs `pre-commit` there. Mutations
    # (`mutations/`'s "setup exempts a destination create left alone" -> recorded; "setup
    # initialises a created overlay before asking where it lies" -> `init` renames its manifest).
    home = tmp_path / "home"
    home.mkdir()
    destination = home / "stayfixed-private"
    real = write_machine

    def planting(*args: Any, **kwargs: Any) -> None:
        if not destination.exists():
            _seed_overlay(destination)
        real(*args, **kwargs)

    monkeypatch.setattr("stayfixed.setup.run.write_machine", planting)
    runner = Recorder(answers={_OCTOS_PROBE: _A_TEMPLATE}, on_call=_populate_overlay)
    with pytest.raises(Refusal, match="holds it, or is it"):
        setup(
            "recommended",
            home=home,
            machine=tmp_path / "config.toml",
            runner=runner,
            yes=True,
            overlay="create:octo/stayfixed-private",
            project_root=home,
        )
    assert not any(argv[:3] == ["gh", "repo", "create"] for argv in runner.calls)
    manifest = json.loads((destination / PLUGIN_MANIFEST).read_text(encoding="utf-8"))
    assert manifest["name"] == "stayfixed-overlay", "overlay init ran in the planted tree"


@needs_git
def test_a_created_overlays_destination_that_is_a_link_is_recorded_where_it_leads(
    tmp_path: Path,
) -> None:
    # A repository can commit `<home>/<name>` as a link: `create:` was judged at the link's
    # target, which lay outside every checkout, and recorded the link, which the repository can
    # later point into its own tree. `create:` records what `--overlay <path>` records, the
    # destination resolved, and judges and compares that one value. Mutation (`mutations/`'s
    # "setup records a created overlay at its link and not where it leads") -> the link is
    # recorded and this reddens.
    outside = tmp_path / "outside-ov"
    outside.mkdir()
    _git(outside, "init", "-q", "-b", "main")
    _seed_overlay(outside)
    repository = tmp_path / "A"
    repository.mkdir()
    _git(repository, "init", "-q", "-b", "main")
    link = repository / "stayfixed-private"
    link.symlink_to(outside)
    _git(repository, "add", "-A")
    _git(repository, "commit", "-qm", "the link")
    machine = tmp_path / "config.toml"
    runner = Recorder(answers={_OCTOS_PROBE: _A_TEMPLATE}, on_call=_populate_overlay)
    setup(
        "recommended",
        home=repository,
        machine=machine,
        runner=runner,
        yes=True,
        overlay="create:octo/stayfixed-private",
        project_root=repository,
    )
    assert overlay_root(machine) == outside.resolve()
    # The repository points the link into its own tree; the record does not move with it.
    (repository / "evil").mkdir()
    link.unlink()
    link.symlink_to(repository / "evil")
    assert overlay_root(machine) == outside.resolve()


@pytest.mark.parametrize("leads", ["inside-the-root", "outside-the-root"])
def test_a_created_overlays_destination_that_is_a_dangling_link_is_refused_before_anything(
    tmp_path: Path, leads: str
) -> None:
    # A link at `<home>/<name>` whose target is not there: read as absent, the destination was
    # exempt from the comparison and `gh repo create` cloned through the link to wherever it
    # pointed; compared at its target, a target outside `--root` still passed and `gh` created a
    # repository before the clone failed on the link. It is refused where the overlay's place is
    # asked, before anything is written or run. Mutation (`mutations/`'s "setup plans a created
    # overlay through a link that leads nowhere") -> `gh` runs and each reddens.
    home = tmp_path / "home"
    home.mkdir()
    target = home / "later" / "ov" if leads == "inside-the-root" else tmp_path / "later" / "ov"
    (home / "stayfixed-private").symlink_to(target)
    machine = tmp_path / "config.toml"
    runner = Recorder(answers={_OCTOS_PROBE: _A_TEMPLATE}, on_call=_populate_overlay)
    with pytest.raises(Refusal, match="which is not there"):
        setup(
            "recommended",
            home=home,
            machine=machine,
            runner=runner,
            yes=True,
            overlay="create:octo/stayfixed-private",
            project_root=home,
        )
    assert runner.calls == [] and _wrote_anything(home, machine) == []


@pytest.mark.parametrize("swap", ["recorded-link-repointed", "absent-then-a-link"])
def test_a_created_overlays_destination_swapped_after_the_phase_is_compared(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, swap: str
) -> None:
    # The phase exempted the destination — the overlay root the machine file records, reached
    # through a link, or nothing there yet — and between the phase and `create` something put a
    # link there into `--root`. The exemption holds only for the directory the phase judged, and
    # an absent destination only when `create` made a directory there and not a link to one, so
    # the swapped destination is compared and refused before `overlay init`. Out of the threat
    # model `setup` defends (a party writing `<home>/<name>` mid-run can write the machine file
    # too); defence in depth. Mutations (`mutations/`'s "setup honours an exemption for a
    # directory the phase did not judge" -> `recorded-link-repointed`; "setup honours an absent
    # destination's exemption for a link create cloned through" -> `absent-then-a-link`).
    home = tmp_path / "home"
    home.mkdir()
    destination = home / "stayfixed-private"
    evil = home / "evil"
    evil.mkdir()
    machine = tmp_path / "config.toml"
    if swap == "recorded-link-repointed":
        recorded = tmp_path / "outside-ov"
        _seed_overlay(recorded)
        _seed_overlay(evil)
        destination.symlink_to(recorded)
        write_machine(machine, personal={}, overlay_root=recorded.resolve(), machine={})
    real = write_machine
    swapped: list[bool] = []

    def swapping(*args: Any, **kwargs: Any) -> None:
        if not swapped:
            swapped.append(True)
            if destination.is_symlink():
                destination.unlink()
            destination.symlink_to(evil)
        real(*args, **kwargs)

    monkeypatch.setattr("stayfixed.setup.run.write_machine", swapping)
    runner = Recorder(answers={_OCTOS_PROBE: _A_TEMPLATE}, on_call=_populate_overlay)
    with pytest.raises(Refusal, match="holds it, or is it"):
        setup(
            "recommended",
            home=home,
            machine=machine,
            runner=runner,
            yes=True,
            overlay="create:octo/stayfixed-private",
            project_root=home,
        )
    assert swapped
    manifest = json.loads((evil / PLUGIN_MANIFEST).read_text(encoding="utf-8"))
    assert manifest["name"] == "stayfixed-overlay", "overlay init ran in the swapped tree"


@needs_git
def test_an_overlay_inside_another_repository_is_refused_from_a_directory_in_no_repository(
    tmp_path: Path,
) -> None:
    # The other half of judging only against a repository: with `--root` in none, the overlay's own
    # side is still asked. A directory inside some other repository's work tree is a tree that
    # repository can ship, whichever repository `--root` is in. Mutation (`mutations/`'s "setup
    # stops refusing an overlay inside another repository's checkout"): the arm's condition
    # becomes `False` -> this overlay is recorded and this reddens.
    repository = tmp_path / "code" / "R"
    repository.mkdir(parents=True)
    _git(repository, "init", "-q", "-b", "main")
    candidate = repository / "ov"
    candidate.mkdir()
    _seed_overlay(candidate)
    # `--root` beside the overlay, in no repository: one that held it would refuse it first, in
    # the path arm's words.
    with pytest.raises(Refusal, match="inside a checkout of another repository"):
        setup(
            "recommended",
            home=tmp_path / "home",
            machine=tmp_path / "config.toml",
            runner=Recorder(),
            yes=True,
            overlay=str(candidate),
            project_root=tmp_path / "elsewhere",
        )


@pytest.mark.parametrize("place", ["inside", "holding", "equal"])
def test_an_existing_overlay_placed_against_a_root_in_no_repository_is_refused(
    tmp_path: Path, place: str
) -> None:
    # A `--root` git finds no repository for can still hold a tree someone else made: a project
    # downloaded as an archive, a checkout of another version control system, a `vendor/ov`
    # shipped inside either. Only a `create:` destination, which the run itself makes, is
    # exempt from the comparison with `--root` there; an overlay that is already on disk is
    # compared as it is inside a repository.
    #
    # Mutation (`mutations/`'s "setup exempts an existing overlay from the comparison with a
    # --root in no repository"): the exemption covers every overlay -> each place is recorded
    # and reddens.
    if place == "inside":
        root, candidate = tmp_path / "project", tmp_path / "project" / "vendor" / "ov"
    elif place == "holding":
        root, candidate = tmp_path / "ov" / "sub", tmp_path / "ov"
    else:
        root = candidate = tmp_path / "ov"
    candidate.mkdir(parents=True)
    root.mkdir(parents=True, exist_ok=True)
    _seed_overlay(candidate)
    home, machine = tmp_path / "home", tmp_path / "config.toml"
    with pytest.raises(Refusal, match="holds it, or is it") as refused:
        setup(
            "recommended",
            home=home,
            machine=machine,
            runner=Recorder(),
            yes=True,
            overlay=str(candidate),
            project_root=root,
        )
    assert "in no git repository" in str(refused.value)
    assert _wrote_anything(home, machine) == []


@needs_git
def test_an_overlay_that_is_a_checkout_of_its_own_inside_another_repository_is_refused(
    tmp_path: Path,
) -> None:
    # Its own `.git` does not take it out of the outer work tree: measured on git 2.54, a merge in
    # the outer repository of a commit that tracks `ov/extra` writes that file into the nested
    # checkout's directory. So the question is asked from above the candidate, where the
    # candidate's own repository cannot be the answer. Mutation (`mutations/`'s "setup stops
    # refusing an overlay inside another repository's checkout"): the arm's condition becomes
    # `False` -> this overlay is recorded and this reddens.
    repository = tmp_path / "code" / "R"
    repository.mkdir(parents=True)
    _git(repository, "init", "-q", "-b", "main")
    candidate = repository / "ov"
    candidate.mkdir()
    _git(candidate, "init", "-q", "-b", "main")
    _seed_overlay(candidate)
    # `--root` beside the overlay, in no repository: one that held it would refuse it first, in
    # the path arm's words.
    with pytest.raises(Refusal, match="inside a checkout of another repository"):
        setup(
            "recommended",
            home=tmp_path / "home",
            machine=tmp_path / "config.toml",
            runner=Recorder(),
            yes=True,
            overlay=str(candidate),
            project_root=tmp_path / "elsewhere",
        )


@needs_git
@pytest.mark.parametrize("whose", ["the-projects", "another-repositorys"])
def test_a_git_directory_git_names_reaches_a_containment_refusal_quoted(
    tmp_path: Path, whose: str
) -> None:
    # Both refusals name a git directory as git answers it, and a submodule's lies at
    # `.git/modules/<name>`, the name `.gitmodules` chose: an escape sequence and a bell in it
    # reached the terminal. Here a separate git directory carries them. Each is printed through
    # `printed.quoted` now. Mutations (`mutations/`'s "setup prints the project's git directory
    # raw in a containment refusal" -> `the-projects` reddens; "setup prints another
    # repository's git directory raw in a containment refusal" -> `another-repositorys`).
    gitdir = tmp_path / "git\x1b]0;owned\x07"
    checkout = tmp_path / "checkout"
    _git(tmp_path, "init", "-q", "-b", "main", "--separate-git-dir", str(gitdir), str(checkout))
    candidate = checkout / "ov"
    candidate.mkdir()
    _seed_overlay(candidate)
    root = checkout if whose == "the-projects" else tmp_path / "elsewhere"
    with pytest.raises(Refusal) as refused:
        _record(tmp_path, candidate, root)
    said = str(refused.value)
    assert "\x1b" not in said and "\x07" not in said, said
    assert "\\x1b]0;owned\\x07" in said, said


_DRIVES_A_TERMINAL = "x\x1b]0;owned\x07"


@needs_git
@pytest.mark.parametrize("printed", ["the-overlay", "where-git-was-asked", "the-floor"])
def test_a_path_a_repository_spells_reaches_every_containment_refusal_quoted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, printed: str
) -> None:
    # A path resolved through a link a repository commits is spelled in bytes the repository
    # chose, and the overlay, `--root`, the directory git was asked from and the path the floor
    # could not ask about each reached a refusal raw: an escape sequence and a bell in a name drove
    # the terminal that read it. Each is printed through `printed.quoted`. Mutations
    # (`mutations/`'s "setup prints the overlay root raw in a containment refusal" ->
    # `the-overlay`; "setup prints the directory git was asked from raw" ->
    # `where-git-was-asked`; "the floor prints the path it could not ask about raw" ->
    # `the-floor`).
    if printed == "the-floor" and os.geteuid() == 0:
        pytest.skip("root searches every directory")
    root = tmp_path / "project"
    root.mkdir()
    overlay = tmp_path / "overlay"
    _seed_overlay(overlay)
    if printed == "the-overlay":
        shipped = root / _DRIVES_A_TERMINAL
        _seed_overlay(shipped)
        (root / "link").symlink_to(shipped)
        overlay = root / "link"
    elif printed == "where-git-was-asked":
        checkout = tmp_path / _DRIVES_A_TERMINAL
        checkout.mkdir()
        _git(checkout, "init", "-q", "-b", "main")
        (tmp_path / "link").symlink_to(checkout)
        root = tmp_path / "link"
        _quiet_git(tmp_path, monkeypatch, "exit 1")
    else:
        locked = tmp_path / _DRIVES_A_TERMINAL
        _seed_overlay(locked / "overlay")
        overlay = locked / "overlay"
    with (
        unsearchable(tmp_path / _DRIVES_A_TERMINAL)
        if printed == "the-floor"
        else (contextlib.nullcontext()),
        pytest.raises(Refusal) as refused,
    ):
        _record(tmp_path, overlay, root)
    said = str(refused.value)
    assert "\x1b" not in said and "\x07" not in said, said
    assert "\\x1b]0;owned\\x07" in said, said


@pytest.mark.parametrize("printed", ["not-an-overlay", "the-note", "the-summary"])
def test_an_overlay_path_a_repository_spells_is_printed_quoted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    printed: str,
) -> None:
    # `--overlay`'s path, resolved through a link a repository commits, is spelled in the
    # repository's bytes, and the refusal that it is not an overlay, the note that it was
    # recorded and `setup`'s own report line printed it raw. Mutations (`mutations/`'s "the
    # overlay probe prints the path it judged raw" -> `not-an-overlay`; "setup notes a recorded
    # overlay's path raw" -> `the-note`; "setup reports the recorded overlay's path raw" ->
    # `the-summary`).
    from stayfixed.cli import build_parser, discover_registrars, run

    overlay = tmp_path / _DRIVES_A_TERMINAL
    overlay.mkdir()
    if printed != "not-an-overlay":
        _seed_overlay(overlay)
    runner = Recorder()
    monkeypatch.setattr("stayfixed.setup.commands.subprocess_runner", lambda: runner)
    argv = ["setup", "--preset", "recommended", "--home", str(tmp_path / "home")]
    argv += ["--machine", str(tmp_path / "config.toml"), "--root", str(tmp_path / "project")]
    argv += ["--overlay", str(overlay)]
    if printed == "the-note":
        argv.append("--json")
    code = run(argv, parser=build_parser(discover_registrars()))
    captured = capsys.readouterr()
    said = captured.err if printed == "not-an-overlay" else captured.out
    if printed == "the-note":
        said = "\n".join(json.loads(captured.out)["notes"])
    assert code == (2 if printed == "not-an-overlay" else 0), captured
    assert "\x1b" not in said and "\x07" not in said, said
    assert "\\x1b]0;owned\\x07" in said, said


@needs_git
def test_an_overlay_that_is_a_worktree_nested_in_its_own_checkout_is_refused_as_its_own(
    tmp_path: Path,
) -> None:
    # A linked worktree of the overlay's own repository, nested in that repository's main
    # checkout, lies where the main checkout can write: a branch there that tracks `.wt/ov/x`
    # writes it into the worktree's directory. It stays refused, and the refusal says it is the
    # overlay's own repository, where it said "another repository" of the one it belongs to.
    # Mutation (`mutations/`'s "setup calls the overlay's own repository another one") -> the
    # refusal says "another repository" and this reddens.
    main = tmp_path / "overlay"
    main.mkdir()
    _git(main, "init", "-q", "-b", "main")
    (main / "README.md").write_text("x", encoding="utf-8")
    _git(main, "add", "-A")
    _git(main, "commit", "-qm", "init")
    candidate = main / ".wt" / "ov"
    _git(main, "worktree", "add", "-q", str(candidate), "-b", "ov")
    _seed_overlay(candidate)
    with pytest.raises(Refusal, match="inside another checkout of its own repository"):
        _record(tmp_path, candidate, tmp_path / "elsewhere")
    assert overlay_root(tmp_path / "config.toml") is None


@needs_git
def test_an_overlay_that_is_a_checkout_of_its_own_is_recorded(tmp_path: Path) -> None:
    # The owner's own layout: the overlay is a clone of a private repository, in a directory no
    # other repository holds. That it is a checkout is not what refuses an overlay; where it lies
    # is. Mutation (`mutations/`'s "setup asks whether an overlay lies in another repository from
    # the overlay itself"): the walk starts at the candidate -> it answers for itself and is
    # refused, and this reddens.
    candidate = tmp_path / "overlay"
    candidate.mkdir()
    _git(candidate, "init", "-q", "-b", "main")
    _seed_overlay(candidate)
    machine = tmp_path / "config.toml"
    setup(
        "recommended",
        home=tmp_path / "home",
        machine=machine,
        runner=Recorder(),
        yes=True,
        overlay=str(candidate),
        project_root=tmp_path / "project",
    )
    assert overlay_root(machine) == candidate


@pytest.mark.parametrize("document", ["[]", '"stayfixed-overlay"', "null"])
def test_a_manifest_that_parses_and_is_not_an_object_names_no_overlay(
    tmp_path: Path, document: str
) -> None:
    # The probe reads its manifests through `jsonobject`, which calls a document that parses and
    # is not an object "not a JSON object". This probe's own sentence for one is that it does not
    # name a stayfixed overlay, which says what to write there; "cannot be read as JSON" would be
    # false about `[]`. Mutation: `identity`'s `shape=_NotAnObject` dropped from the `json_object`
    # call -> the sentence is the unreadable one and this reddens.
    from stayfixed.overlay.api import overlay_fault

    _seed_overlay(tmp_path)
    (tmp_path / PLUGIN_MANIFEST).write_text(document, encoding="utf-8")
    fault = overlay_fault(tmp_path)
    assert fault == (
        f"{quoted(str(tmp_path))} carries a {PLUGIN_MANIFEST} that does not name a stayfixed "
        f"overlay; its "
        f"`name` has to be stayfixed-overlay, or stayfixed-overlay-<owner> after `stayfixed "
        f"overlay init`"
    )


def test_a_directory_whose_manifests_name_another_plugin_is_not_an_overlay(tmp_path: Path) -> None:
    # The probe was the two manifest *files* existing, which the stayfixed checkout itself satisfies
    # and any Claude Code plugin repository satisfies — so "carries the overlay's own layout"
    # excluded almost nothing. The manifests are now read, and have to name the tree
    # `stayfixed-overlay[-<owner>]`.
    #
    # Mutation (`mutations/`'s "the overlay probe stops reading what the manifests name"):
    # `identity`'s `_claims` arm is dropped → this directory is accepted and the refusal never
    # fires.
    impostor = tmp_path / "some-plugin"
    (impostor / ".claude-plugin").mkdir(parents=True)
    (impostor / PLUGIN_MANIFEST).write_text(
        json.dumps({"name": "somebody-elses-plugin"}), encoding="utf-8"
    )
    (impostor / MARKETPLACE_MANIFEST).write_text(
        json.dumps({"name": "somebody-elses-marketplace", "plugins": []}), encoding="utf-8"
    )
    with pytest.raises(Refusal, match="does not name a stayfixed overlay"):
        setup(
            "recommended",
            home=tmp_path / "home",
            machine=tmp_path / "config.toml",
            runner=Recorder(),
            yes=True,
            overlay=str(impostor),
            project_root=tmp_path / "project",
        )


@needs_git
def test_an_overlay_that_holds_the_project_root_is_refused(tmp_path: Path) -> None:
    # The containment refused `candidate == project` or `project in candidate.parents` and nothing
    # else, so a *parent* passed — and `git worktree add .worktrees/x`, which is how feature work is
    # ordinarily started, puts `--root` exactly there. A
    # clone shipping its two manifests at its own root was then accepted as the machine's trust
    # anchor. `--root` is a repository of its own here, so the path arm is the only one that can
    # see the clone above it: a real worktree of the clone is refused by the checkout listing too.
    #
    # Mutation (`mutations/`'s "setup stops refusing an overlay root that holds the project"):
    # `_overlaps` stops asking whether `a` holds `b` -> the clone's own root is recorded and this
    # reddens.
    clone = tmp_path / "clone"
    clone.mkdir()
    _seed_overlay(clone)
    worktree = clone / ".worktrees" / "feature"
    worktree.mkdir(parents=True)
    _git(worktree, "init", "-q", "-b", "main")
    with pytest.raises(Refusal, match="holds it, or is it"):
        setup(
            "recommended",
            home=tmp_path / "home",
            machine=tmp_path / "config.toml",
            runner=Recorder(),
            yes=True,
            overlay=str(clone),
            project_root=worktree,
        )


def test_a_sibling_checkout_of_the_project_is_never_the_trust_anchor(tmp_path: Path) -> None:
    # The case no path comparison can see: `git worktree add ../side` is git's own documented layout
    # and this repository's own convention, and a worktree beside the checkout is neither inside it
    # nor above it. The clone's manifests sit in the *other* checkout of the same repository, so
    # both path arms passed and the tree a clone ships was recorded. `git worktree list`, asked from
    # the project, is what tells two checkouts of one repository apart from two repositories.
    #
    # No mutation reddens this alone: the project's listing and the candidate-side walk both
    # refuse it. Each is proven by a test only it catches — the bare-shaped directory that
    # claims to be a checkout, and the separate-git-dir checkout.
    clone = tmp_path / "clone"
    clone.mkdir()
    _git(clone, "init", "-q", "-b", "main")
    _seed_overlay(clone)
    (clone / "README.md").write_text("x", encoding="utf-8")
    _git(clone, "add", "-A")
    _git(clone, "-c", "user.email=a@b.c", "-c", "user.name=a", "commit", "-qm", "init")
    worktree = tmp_path / "clone.worktrees" / "feature"
    _git(clone, "worktree", "add", "-q", str(worktree), "-b", "feature")
    assert clone.resolve() not in worktree.resolve().parents, "beside the checkout, not under it"
    with pytest.raises(Refusal, match="same repository"):
        setup(
            "recommended",
            home=tmp_path / "home",
            machine=tmp_path / "config.toml",
            runner=Recorder(),
            yes=True,
            overlay=str(clone),
            project_root=worktree,
        )


def test_a_sibling_checkout_git_names_in_bytes_that_are_not_utf_8_is_still_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The case above with a common directory whose path is not UTF-8, an ordinary latin-1
    # directory name on Linux. Decoded strictly, git's answer was a traceback; read as no answer,
    # `_repository` answered `None`, the `git` arms went silent, and the sibling checkout of the
    # project was recorded as the machine's trust anchor. Decoded losslessly, the answer is read
    # and the checkout is refused.
    #
    # APFS refuses to create such a directory, so a stand-in `git` on `PATH` runs the real one
    # and appends one latin-1 byte to the first line of what `--git-common-dir` prints — the
    # common directory, not the `--is-inside-work-tree` answer after it — for every directory
    # alike, exactly as a common directory really named so would read. Every other `git` call
    # passes through untouched.
    #
    # Mutation (declared, on `gitenv`): the answer read as no answer again -> the guard, which
    # refuses git's silence inside a checkout, refuses for that silence rather than naming the
    # sibling checkout, and this reddens on the `same repository` match alone.
    clone = tmp_path / "clone"
    clone.mkdir()
    _git(clone, "init", "-q", "-b", "main")
    _seed_overlay(clone)
    (clone / "README.md").write_text("x", encoding="utf-8")
    _git(clone, "add", "-A")
    _git(clone, "-c", "user.email=a@b.c", "-c", "user.name=a", "commit", "-qm", "init")
    worktree = tmp_path / "clone.worktrees" / "feature"
    _git(clone, "worktree", "add", "-q", str(worktree), "-b", "feature")
    real_git = shutil.which("git")
    assert real_git is not None
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "git").write_text(
        "#!/bin/sh\n"
        'case "$*" in\n'
        f'  *--git-common-dir*) out=$("{real_git}" "$@") || exit $?\n'
        '    printf "%s\\351\\n" "$(printf "%s\\n" "$out" | head -n 1)"\n'
        '    printf "%s\\n" "$out" | tail -n +2 ;;\n'
        f'  *) exec "{real_git}" "$@" ;;\n'
        "esac\n",
        encoding="utf-8",
    )
    (bin_dir / "git").chmod(0o755)
    stand_in_git(monkeypatch, bin_dir / "git")
    with pytest.raises(Refusal, match="same repository"):
        setup(
            "recommended",
            home=tmp_path / "home",
            machine=tmp_path / "config.toml",
            runner=Recorder(),
            yes=True,
            overlay=str(clone),
            project_root=worktree,
        )


def test_an_overlay_outside_every_checkout_is_still_recorded(tmp_path: Path) -> None:
    # The other side of the two tests above, and the reason they are not simply "refuse
    # everything": a real overlay is a repository of its own, beside the project and unrelated
    # to it, and `git` answering for both must not make them the same tree.
    project = tmp_path / "project"
    project.mkdir()
    _git(project, "init", "-q", "-b", "main")
    overlay = tmp_path / "stayfixed-private"
    overlay.mkdir()
    _git(overlay, "init", "-q", "-b", "main")
    _seed_overlay(overlay)
    machine = tmp_path / "config.toml"
    report = setup(
        "recommended",
        home=tmp_path / "home",
        machine=machine,
        runner=Recorder(),
        yes=True,
        overlay=str(overlay),
        project_root=project,
    )
    assert report.overlay == overlay
    assert overlay_root(machine) == overlay


def _commit_a_bare_shaped_directory(checkout: Path) -> Path:
    """Commit `ov/` into `checkout`, shaped like a bare repository and carrying the overlay's
    two manifests; `ov/`.

    `HEAD`, `objects/` and `refs/` are three paths any repository can commit, and `git`'s
    discovery reads a directory holding all three as a bare repository of its own when
    `safe.bareRepository` is unset. With the manifests beside them, `ov/` in every checkout is a
    tree the clone shipped and that reads as an overlay.
    """
    shaped = checkout / "ov"
    (shaped / "objects").mkdir(parents=True)
    (shaped / "refs").mkdir()
    (shaped / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    (shaped / "objects" / ".keep").write_text("", encoding="utf-8")
    (shaped / "refs" / ".keep").write_text("", encoding="utf-8")
    _seed_overlay(shaped)
    _git(checkout, "add", "-A")
    _git(checkout, "commit", "-qm", "init")
    return shaped


def _clone_with_a_bare_shaped_directory(tmp_path: Path, ov_config: str = "") -> tuple[Path, Path]:
    """A project repository that commits a bare-shaped `ov/` (and `ov_config` as its `config`,
    when given), plus two sibling worktrees of it; `(main checkout, the worktrees' parent)`."""
    project = tmp_path / "proj"
    project.mkdir()
    _git(project, "init", "-q", "-b", "main")
    if ov_config:
        (project / "ov").mkdir()
        (project / "ov" / "config").write_text(ov_config, encoding="utf-8")
    _commit_a_bare_shaped_directory(project)
    worktrees = tmp_path / "proj.wt"
    _git(project, "worktree", "add", "-q", str(worktrees / "feature"), "-b", "feature")
    _git(project, "worktree", "add", "-q", str(worktrees / "bugfix"), "-b", "bugfix")
    return project, worktrees


# `safe.bareRepository` arrived in git 2.38, and an older git ignores a `-c` key it does not
# know. "ignores-safe-bare" stands that git in by emptying the pair, so the refusals that must not
# depend on it are proven on the git CI has.
GITS = ["current", "ignores-safe-bare"]


def _as(git_version: str, monkeypatch: pytest.MonkeyPatch) -> None:
    if git_version == "ignores-safe-bare":
        monkeypatch.setattr("stayfixed.setup.run._EXPLICIT_BARE", ())


def _record(tmp_path: Path, overlay: Path, project_root: Path) -> None:
    setup(
        "recommended",
        home=tmp_path / "home",
        machine=tmp_path / "config.toml",
        runner=Recorder(),
        yes=True,
        overlay=str(overlay),
        project_root=project_root,
    )


@pytest.mark.parametrize("git_version", GITS)
@pytest.mark.parametrize("root", ["proj", "proj.wt/bugfix", "proj.wt/bugfix/no/such/dir"])
def test_a_bare_shaped_directory_in_a_sibling_checkout_is_never_the_trust_anchor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, root: str, git_version: str
) -> None:
    # The sibling-checkout arm asked `git rev-parse --git-common-dir` *from inside the
    # candidate*, and git answered for the committed `ov/` rather than for the checkout it sits
    # in: `proj.wt/feature/ov` reported itself as its own common directory, so it was "not the
    # same repository" and was recorded — while `proj.wt/feature` itself was refused. The
    # checkouts are now listed from the project's side, which the candidate's bytes cannot reach.
    #
    # The listing and the candidate-side arm each refuse this layout, so breaking either one
    # leaves it refused: the test below proves the listing alone, and the separate-git-dir test
    # the candidate side alone. A `--root` that does not exist is asked about from its nearest
    # directory that does, where it used to be asked from its parent and nothing else.
    #
    # Mutation (`mutations/`'s "setup asks git about --root from a directory that does not exist"):
    # the walk up becomes one step → `no/such` does not exist, git gives no answer, only the path
    # arm stands and the third root reddens.
    _as(git_version, monkeypatch)
    _clone_with_a_bare_shaped_directory(tmp_path)
    with pytest.raises(Refusal, match="same repository"):
        _record(tmp_path, tmp_path / "proj.wt" / "feature" / "ov", tmp_path / root)
    assert not (tmp_path / "config.toml").exists(), "refused above the first write"


@pytest.mark.parametrize("git_version", GITS)
def test_a_bare_shaped_directory_that_claims_to_be_a_checkout_is_still_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, git_version: str
) -> None:
    # A committed `ov/config` saying `core.bare = false` makes a git that ignores
    # `safe.bareRepository` answer from inside `ov/` with `ov/` as a repository that is *not*
    # bare. The listing refuses the sibling regardless, and the candidate-side walk takes only
    # an answer from inside a work tree, which `ov/` never gives, so both arms refuse it; the
    # test below proves the listing alone, and the separate-git-dir test's `claims-a-checkout`
    # case proves the walk alone.
    _as(git_version, monkeypatch)
    project = tmp_path / "proj"
    project.mkdir()
    _git(project, "init", "-q", "-b", "main")
    (project / "ov").mkdir()
    (project / "ov" / "config").write_text("[core]\n\tbare = false\n", encoding="utf-8")
    _commit_a_bare_shaped_directory(project)
    linked = tmp_path / "proj.wt" / "feature"
    _git(project, "worktree", "add", "-q", str(linked), "-b", "feature")
    with pytest.raises(Refusal, match="same repository"):
        _record(tmp_path, linked / "ov", project)


@pytest.mark.parametrize("ov_config", ["none", "claims-a-checkout"])
@pytest.mark.parametrize("git_version", GITS)
def test_a_root_inside_a_bare_shaped_directory_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, git_version: str, ov_config: str
) -> None:
    # The same shape from the project's side: run from `proj/ov`, git's own discovery stops at
    # `ov/` and names *it* as the repository, whose only "checkout" is itself — so the sibling
    # `proj.wt/feature/ov` lies outside every listed checkout and every path arm. git's answer
    # says `ov/` is not inside a work tree — even when a committed `ov/config` says
    # `core.bare = false` (`claims-a-checkout`) — and on every git version that is what refuses:
    # a project root with no checkout of its own to compare against is not one.
    #
    # Mutation (`mutations/`'s "setup stops refusing a root git does not read as inside a
    # checkout"): the `--is-inside-work-tree` refusal becomes `if False:` → the current-git cases
    # fall to the retry's refusal, which does not say "bare repository", and the other cases are
    # recorded.
    _as(git_version, monkeypatch)
    config = "[core]\n\tbare = false\n" if ov_config == "claims-a-checkout" else ""
    project, _ = _clone_with_a_bare_shaped_directory(tmp_path, config)
    with pytest.raises(Refusal, match="bare repository"):
        _record(tmp_path, tmp_path / "proj.wt" / "feature" / "ov", project / "ov")
    assert not (tmp_path / "config.toml").exists(), "refused above the first write"


def test_the_listing_refuses_a_sibling_checkout_when_git_answers_nothing_from_the_candidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Why the listing stays the arm that decides: it does not depend on git answering from the
    # candidate's side at all. Here every question asked from anywhere but the project root
    # times out, so the candidate-side walk finds nothing, and the sibling's `ov/` is refused by
    # the project's own record of its checkouts alone.
    #
    # Mutation (`mutations/`'s "setup stops asking git whether the overlay is a checkout of the
    # project"): the per-checkout comparison becomes `if False:` → the sibling is recorded.
    project, worktrees = _clone_with_a_bare_shaped_directory(tmp_path)
    real = gitenv.git_run

    def silent_off_the_project(root: Path, *args: str, **kwargs: Any) -> tuple[int, str]:
        if "rev-parse" in args and root.resolve() != project.resolve():
            return -1, ""
        return real(root, *args, **kwargs)

    monkeypatch.setattr("stayfixed.setup.run.git_run", silent_off_the_project)
    with pytest.raises(Refusal, match="same repository"):
        _record(tmp_path, worktrees / "feature" / "ov", project)


@pytest.mark.parametrize("ov_config", ["none", "claims-a-checkout", "points-elsewhere"])
@pytest.mark.parametrize("git_version", GITS)
def test_a_checkout_the_listing_names_by_its_git_directory_is_still_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, git_version: str, ov_config: str
) -> None:
    # `git worktree list` does not name every checkout. With `--separate-git-dir` the main
    # worktree is listed as the git directory (`sep.git`), which does not record where its work
    # tree is, so from the linked worktree `s.wt/w` the main checkout `s` is on no list and its
    # `ov/` passed every listed arm. The candidate-side arm walks up from the candidate to the
    # first repository git answers for that is not bare — `s`, through its `.git` file — and
    # refuses when that is the project's. It can only add a refusal: whatever the candidate's
    # bytes make git answer, the listing's refusals still stand.
    #
    # Mutation (`mutations/`'s "setup stops asking git from the candidate's side"): the
    # candidate-side refusal becomes `if False:` → `s/ov` is recorded and both cases redden.
    # Mutation (`mutations/`'s "the candidate-side walk stops at the first directory git will not
    # answer for"): the step to the parent becomes `return None` → git refuses `ov/` as a bare
    # repository, the walk never reaches `s`, and the current-git case reddens.
    #
    # On a git that ignores the key, `ov/` answers for itself, and what it commits can shape
    # that answer: `claims-a-checkout` commits `ov/config` saying `core.bare = false`, and
    # `points-elsewhere` commits `ov/commondir` naming a second bare-shaped `ov2/` whose config
    # says the same, so the answer is "not bare" with a common directory off the walk. Neither
    # can make git say `ov/` is inside a work tree, and the walk goes on past it.
    # Mutation (`mutations/`'s "the candidate-side walk takes an answer from outside a work tree as
    # the candidate's"): the `answer[1] == "true"` condition is dropped → the walk stops at `ov/`
    # and every `ignores-safe-bare` case reddens.
    _as(git_version, monkeypatch)
    main, sep = tmp_path / "s", tmp_path / "sep.git"
    _git(tmp_path, "init", "-q", "-b", "main", "--separate-git-dir", str(sep), str(main))
    not_bare = "[core]\n\tbare = false\n"
    if ov_config == "claims-a-checkout":
        (main / "ov").mkdir()
        (main / "ov" / "config").write_text(not_bare, encoding="utf-8")
    if ov_config == "points-elsewhere":
        other = main / "ov2"
        (other / "objects").mkdir(parents=True)
        (other / "refs").mkdir()
        (other / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
        (other / "objects" / ".keep").write_text("", encoding="utf-8")
        (other / "refs" / ".keep").write_text("", encoding="utf-8")
        (other / "config").write_text(not_bare, encoding="utf-8")
        (main / "ov").mkdir()
        (main / "ov" / "commondir").write_text("../ov2\n", encoding="utf-8")
    _commit_a_bare_shaped_directory(main)
    linked = tmp_path / "s.wt" / "w"
    _git(main, "worktree", "add", "-q", str(linked), "-b", "w")
    with pytest.raises(Refusal, match="same repository"):
        _record(tmp_path, main / "ov", linked)


@pytest.mark.parametrize("git_version", GITS)
def test_a_submodule_checkout_is_refused_from_a_worktree_of_the_submodule(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, git_version: str
) -> None:
    # The second layout the listing names by its git directory: a submodule's own checkout is
    # listed as `sup/.git/modules/sub`, so from a linked worktree of the submodule `sup/sub` is
    # on no list. The candidate-side walk reaches it through `sup/sub/.git`.
    #
    # Mutation (`mutations/`'s "setup stops asking git from the candidate's side"): as above, both
    # cases.
    _as(git_version, monkeypatch)
    sub = tmp_path / "sub"
    sub.mkdir()
    _git(sub, "init", "-q", "-b", "main")
    _commit_a_bare_shaped_directory(sub)
    sup = tmp_path / "sup"
    sup.mkdir()
    _git(sup, "init", "-q", "-b", "main")
    _git(sup, "-c", "protocol.file.allow=always", "submodule", "add", "-q", str(sub), "sub")
    _git(sup, "commit", "-qm", "add the submodule")
    linked = tmp_path / "sup.wt"
    _git(sup / "sub", "worktree", "add", "-q", str(linked), "-b", "w")
    with pytest.raises(Refusal, match="same repository"):
        _record(tmp_path, sup / "sub" / "ov", linked)


def test_a_sibling_checkout_spelled_in_another_case_is_still_refused(tmp_path: Path) -> None:
    # On a volume that folds case — macOS's default — `PROJ.WT/feature/ov` is the sibling
    # checkout's `ov/`, and `Path.resolve()` keeps the case it was given, so a string comparison
    # against the listed `proj.wt/feature` said "outside". Directories are now compared as the
    # filesystem sees them.
    #
    # No mutation entry: the oracle runs on Linux, where this layout cannot exist and the test
    # skips, so an entry would be reported as proving nothing. `_overlaps`' own arms are pinned
    # by the entries on the inside and holds tests.
    project, _ = _clone_with_a_bare_shaped_directory(tmp_path)
    candidate = tmp_path / "PROJ.WT" / "feature" / "ov"
    if not candidate.is_dir():
        pytest.skip("this filesystem is case-sensitive")
    with pytest.raises(Refusal, match="same repository"):
        _record(tmp_path, candidate, project)


FAILURES: dict[str, Callable[[tuple[str, ...]], tuple[int, str] | None]] = {
    # What the listing call answers.
    "listing-exit": lambda args: (128, "") if "worktree" in args else None,
    "listing-empty": lambda args: (0, "") if "worktree" in args else None,
    # What the project-side `rev-parse` answers.
    "answers-only-without-the-key": (
        lambda args: (128, "") if "rev-parse" in args and "-c" in args else None
    ),
}


@pytest.mark.parametrize("failure", sorted(FAILURES))
def test_checkouts_git_cannot_list_refuse_the_overlay_rather_than_pass_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    # Once git has said the project is a repository, "no answer" about its checkouts is not
    # "none of them holds the candidate". It used to be: a `git` that gave no answer for the
    # candidate returned `None`, `None` differed from the project's common directory, and the
    # candidate was recorded. (A path git prints in bytes that are not UTF-8 is not among these:
    # `gitenv.git_run` decodes it losslessly, so it is an answer, and the test of a non-UTF-8
    # common directory above holds that.)
    #
    # Mutation (`mutations/`'s "setup stops refusing an overlay when git cannot list the project's
    # checkouts"): the listing's refusal becomes `return _Repository(common, [])` → the
    # legitimate-looking overlay below is recorded and `listing-exit` reddens. An empty listing
    # with exit 0 is refused before it is read, as a git that printed nothing inside a checkout
    # (`_ask`), so it says that instead.
    # Mutation (`mutations/`'s "setup takes an answer git gave only without the key"): the refusal
    # after the retry becomes `pass` → `answers-only-without-the-key` is recorded and reddens.
    project = tmp_path / "project"
    project.mkdir()
    _git(project, "init", "-q", "-b", "main")
    overlay = tmp_path / "stayfixed-private"
    overlay.mkdir()
    _git(overlay, "init", "-q", "-b", "main")
    _seed_overlay(overlay)
    real = gitenv.git_run

    def failing(root: Path, *args: str, **kwargs: Any) -> tuple[int, str]:
        answer = FAILURES[failure](args)
        if answer is None:
            return real(root, *args, **kwargs)
        return answer

    monkeypatch.setattr("stayfixed.setup.run.git_run", failing)
    said = "git exited 0 and printed nothing" if failure == "listing-empty" else "could not list"
    with pytest.raises(Refusal, match=said):
        _record(tmp_path, overlay, project)


# Which `git` calls give no answer — `gitenv.git_run`'s `(-1, "")`, for a git that could not be
# run or ran past its time limit — keyed by what was asked and from where.
SILENT: dict[str, Callable[[Path, Path, tuple[str, ...]], bool]] = {
    "every-call": lambda main, root, args: True,
    "the-listing": lambda main, root, args: "worktree" in args,
    # Only the walk up from the candidate: `main` is the checkout the listing names by its git
    # directory, so this arm alone can refuse it.
    "the-candidate-side": lambda main, root, args: main in (root, *root.parents),
}


@pytest.mark.parametrize("silent", sorted(SILENT))
def test_git_giving_no_answer_inside_a_checkout_refuses_the_overlay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, silent: str
) -> None:
    # `git_run` answers `(-1, "")` when git could not be run or ran past its time limit, and the
    # guard read that as it reads git's own "no repository": `_repository` answered `None` and
    # only the path arm stood, and the candidate-side walk went on past it and found nothing. A
    # git that timed out on `rev-parse` let the main checkout of the project be recorded as the
    # trust anchor from one of its worktrees. Inside a checkout, which the disk says without
    # asking git, that silence is now a refusal.
    #
    # The layout is the separate-git-dir one, whose main checkout `s` only the candidate-side
    # walk can refuse, so each of the three places git is asked is the one that decides.
    #
    # Mutation (`mutations/`'s "setup reads git giving no answer inside a checkout as no repository
    # again"): the refusal in `_ask` becomes `if False:` → `every-call` and `the-candidate-side`
    # record `s/ov`, and `the-listing` is refused for an empty listing, a message that names the
    # wrong cause; all three redden.
    main, sep = tmp_path / "s", tmp_path / "sep.git"
    _git(tmp_path, "init", "-q", "-b", "main", "--separate-git-dir", str(sep), str(main))
    (main / "README.md").write_text("x", encoding="utf-8")
    _git(main, "add", "-A")
    _git(main, "commit", "-qm", "init")
    linked = tmp_path / "s.wt" / "w"
    _git(main, "worktree", "add", "-q", str(linked), "-b", "w")
    candidate = main / "ov"
    candidate.mkdir()
    _seed_overlay(candidate)
    real = gitenv.git_run
    resolved_main = main.resolve()

    def silent_git(root: Path, *args: str, **kwargs: Any) -> tuple[int, str]:
        if SILENT[silent](resolved_main, root.resolve(), args):
            return -1, ""
        return real(root, *args, **kwargs)

    monkeypatch.setattr("stayfixed.setup.run.git_run", silent_git)
    with pytest.raises(Refusal, match="gave no answer") as refused:
        _record(tmp_path, candidate, linked)
    assert gitenv.NO_ANSWER in str(refused.value)


def test_git_giving_no_answer_where_no_checkout_is_still_records_the_overlay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The other side of the test above: where no `.git` is at or above the directory git was
    # asked from, there is no checkout for it to have named, so a git that cannot run at all
    # costs nothing and the path arm stands, as it did before.
    #
    # Mutation (`mutations/`'s "setup refuses an overlay whenever git gives no answer, checkout or
    # not"): the `in_work_tree` condition is dropped → this overlay is refused and this reddens.
    project = tmp_path / "project"
    project.mkdir()
    overlay = tmp_path / "stayfixed-private"
    overlay.mkdir()
    _seed_overlay(overlay)
    monkeypatch.setattr("stayfixed.setup.run.git_run", lambda root, *args, **kwargs: (-1, ""))
    machine = tmp_path / "config.toml"
    report = setup(
        "recommended",
        home=tmp_path / "home",
        machine=machine,
        runner=Recorder(),
        yes=True,
        overlay=str(overlay),
        project_root=project,
    )
    assert report.overlay == overlay
    assert overlay_root(machine) == overlay


# A `git` that runs the real one as though another user owned every repository it opens, which
# is how git's own suite drives `safe.directory`: git then refuses the repository with exit 128.
# `where` limits it to the directories one arm of the guard asks from. Where it applies it reads
# neither the system nor the global configuration, as `tests/ledger/test_write.py`'s wrapper does:
# a machine whose either file sets `safe.directory = *` — GitHub's Ubuntu images write it into
# `/etc/gitconfig`, which the product's `git` reads — trusts every repository, so git described
# the one this wrapper exists to have refused and only the path arm was left to be tested.
DUBIOUS: dict[str, Callable[[Path], str]] = {
    "every-call": lambda main: "true",
    # Only the walk up from the candidate: `main` is the checkout the listing names by its git
    # directory, so this arm alone can refuse it.
    "the-candidate-side": lambda main: (
        f'case "$2" in "{main}"|"{main}"/*) true ;; *) false ;; esac'
    ),
}


def _dubious_git(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, where: str) -> None:
    real_git = shutil.which("git")
    assert real_git is not None
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "git").write_text(
        "#!/bin/sh\n"
        f"if {where}; then\n"
        "  GIT_TEST_ASSUME_DIFFERENT_OWNER=1\n"
        "  GIT_CONFIG_NOSYSTEM=1\n"
        f"  GIT_CONFIG_GLOBAL={os.devnull}\n"
        "  export GIT_TEST_ASSUME_DIFFERENT_OWNER GIT_CONFIG_NOSYSTEM GIT_CONFIG_GLOBAL\n"
        "fi\n"
        f'exec "{real_git}" "$@"\n',
        encoding="utf-8",
    )
    (bin_dir / "git").chmod(0o755)
    stand_in_git(monkeypatch, bin_dir / "git")


@pytest.mark.parametrize("dubious", sorted(DUBIOUS))
def test_git_refusing_the_repository_inside_a_checkout_refuses_the_overlay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, dubious: str
) -> None:
    # Exit 128 inside a checkout is git saying there is a repository it will not describe —
    # another user's under `safe.directory`, or one whose `.git` it cannot read — and the guard
    # read it as git's "no repository": on every call only the path arm stood and the main
    # checkout's `ov/` was recorded from a linked worktree; on the candidate side the walk went
    # past it. The layout is the separate-git-dir one of the silent-git case above.
    #
    # Mutations (declared): the 128 refusal in `_ask` made `if False:` -> both cases record
    # `s/ov`; the walk's question without the key dropped -> the candidate-side case records it.
    main, sep = tmp_path / "s", tmp_path / "sep.git"
    _git(tmp_path, "init", "-q", "-b", "main", "--separate-git-dir", str(sep), str(main))
    (main / "README.md").write_text("x", encoding="utf-8")
    _git(main, "add", "-A")
    _git(main, "commit", "-qm", "init")
    linked = tmp_path / "s.wt" / "w"
    _git(main, "worktree", "add", "-q", str(linked), "-b", "w")
    candidate = main / "ov"
    candidate.mkdir()
    _seed_overlay(candidate)
    _dubious_git(tmp_path, monkeypatch, DUBIOUS[dubious](main.resolve()))
    # The premise, asked of the `git` the product runs: it refuses the main checkout. A runner
    # whose configuration defeats the fake owner fails here, at the setup, and not at the
    # verdict below, where the path arm's refusal reads as a different message.
    assert gitenv.git_run(main.resolve(), "rev-parse", "--git-dir")[0] == 128
    with pytest.raises(Refusal, match="refused to describe the repository"):
        _record(tmp_path, candidate, linked)
    assert overlay_root(tmp_path / "config.toml") is None


def test_git_refusing_every_repository_where_no_checkout_is_still_records_the_overlay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The other side: outside every checkout git's 128 is its ordinary "not a git repository",
    # and no `.git` at or above the directory says there was nothing for it to describe.
    # Mutation (declared): the `in_work_tree` condition dropped from the 128 arm -> refused.
    project = tmp_path / "project"
    project.mkdir()
    overlay = tmp_path / "stayfixed-private"
    overlay.mkdir()
    _seed_overlay(overlay)
    _dubious_git(tmp_path, monkeypatch, "true")
    _record(tmp_path, overlay, project)
    assert overlay_root(tmp_path / "config.toml") == overlay


# How a `git` that runs can still say nothing about a repository, each a line of shell run in
# place of `rev-parse`: a wrapper that exits 1 (asdf or mise with no version chosen), one the
# kernel ends with a signal, and one that exits 0 having printed nothing.
QUIET = {
    "exits-1": "exit 1",
    "killed-by-a-signal": "kill -KILL $$",
    "answers-nothing": "exit 0",
}
# Where the overlay lies, in a checkout git is asked about: inside `--root`, which the path arm
# would still see with no repository, and in a sibling checkout of `--root`'s repository, which
# only git's answers can show.
QUIET_LAYOUTS = ["inside-the-root", "in-a-sibling-checkout"]


def _quiet_git(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, rev_parse: str) -> None:
    real_git = shutil.which("git")
    assert real_git is not None
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "git").write_text(
        "#!/bin/sh\n"
        'for arg in "$@"; do\n'
        f'  if [ "$arg" = rev-parse ]; then {rev_parse}; fi\n'
        "done\n"
        f'exec "{real_git}" "$@"\n',
        encoding="utf-8",
    )
    (bin_dir / "git").chmod(0o755)
    stand_in_git(monkeypatch, bin_dir / "git")


# Two ways a `git` that runs answers `rev-parse` in a shape git does not give, each a stand-in's
# body: git 2.30 and older echo the `--path-format=absolute` they do not know as an extra line
# (stood in for by renaming the flag, which a current git echoes the same way), and a wrapper
# prints a banner of its own on standard output before git's answer.
MISSHAPEN = {
    "an-extra-line": (
        'for a in "$@"; do shift; '
        'if [ "$a" = --path-format=absolute ]; then set -- "$@" --path-formatx=absolute; '
        'else set -- "$@" "$a"; fi; done\n'
    ),
    "a-banner": "echo 'welcome to the managed toolchain'\n",
}


@needs_git
@pytest.mark.parametrize("form", ["path", "create", "root"])
@pytest.mark.parametrize("shape", sorted(MISSHAPEN))
def test_git_answering_in_another_shape_inside_a_checkout_refuses_the_overlay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, shape: str, form: str
) -> None:
    # The walk up from the overlay took only `<path>`, `true` as an answer and stepped past every
    # other exit-0 answer, inside a work tree too, so with `--root` in no repository — where the
    # walk is the only arm — an overlay, or a `create:` destination, inside another repository's
    # work tree was recorded. Inside a work tree an answer that is not a path and `true` or
    # `false` refuses; `root` is the same rule asked of `--root`'s own repository, which refused
    # such an answer as an unlisted one. Mutations (`mutations/`'s "the candidate walk steps past
    # an answer of the wrong shape inside a work tree" -> `path` and `create` are recorded;
    # "setup reads --root's repository from an answer of the wrong shape" -> `root` is refused in
    # other words).
    repository = tmp_path / "code" / "R"
    repository.mkdir(parents=True)
    _git(repository, "init", "-q", "-b", "main")
    root = tmp_path / "project"
    root.mkdir()
    real_git = shutil.which("git")
    assert real_git is not None
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "git").write_text(
        f'#!/bin/sh\n{MISSHAPEN[shape]}exec "{real_git}" "$@"\n', encoding="utf-8"
    )
    (bin_dir / "git").chmod(0o755)
    stand_in_git(monkeypatch, bin_dir / "git")
    if form == "root":
        root, overlay, home = repository, tmp_path / "ov", tmp_path / "home"
        _seed_overlay(overlay)
        spelled = str(overlay)
    elif form == "path":
        overlay, home = repository / "ov", tmp_path / "home"
        _seed_overlay(overlay)
        spelled = str(overlay)
    else:
        overlay, home, spelled = (
            repository / "stayfixed-private",
            repository,
            "create:octo/stayfixed-private",
        )
    runner = Recorder(answers={_OCTOS_PROBE: _A_TEMPLATE}, on_call=_populate_overlay)
    with pytest.raises(Refusal, match="in a shape it does not give"):
        setup(
            "recommended",
            home=home,
            machine=tmp_path / "config.toml",
            runner=runner,
            yes=True,
            overlay=spelled,
            project_root=root,
        )
    assert runner.calls == [] and overlay_root(tmp_path / "config.toml") is None


@needs_git
@pytest.mark.parametrize("layout", QUIET_LAYOUTS)
@pytest.mark.parametrize("quiet", sorted(QUIET))
def test_git_that_runs_and_answers_nothing_inside_a_checkout_refuses_the_overlay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, quiet: str, layout: str
) -> None:
    # Only a `git` that could not be run or ran out of time refused; every other way of saying
    # nothing — an exit of 1, 126 or 127, a signal, an empty answer — read as "no repository",
    # so the comparisons with `--root` were skipped and the walk up from the candidate stepped
    # past every directory: the clone's own `ov/` was recorded as the machine's trust anchor,
    # exit 0. Inside a checkout, which the disk says without asking git, any of them refuses.
    #
    # Mutation (`mutations/`'s "setup reads git giving no answer inside a checkout as no
    # repository again"): the silent arm of `_ask` answers `None` -> `in-a-sibling-checkout` is
    # recorded and `inside-the-root` is refused by the path arm in other words; all redden.
    project = tmp_path / "proj"
    project.mkdir()
    _git(project, "init", "-q", "-b", "main")
    (project / "README.md").write_text("x", encoding="utf-8")
    _git(project, "add", "-A")
    _git(project, "commit", "-qm", "init")
    candidate = project / "ov"
    candidate.mkdir()
    _seed_overlay(candidate)
    root = project
    if layout == "in-a-sibling-checkout":
        root = tmp_path / "proj.wt" / "feature"
        _git(project, "worktree", "add", "-q", str(root), "-b", "feature")
    _quiet_git(tmp_path, monkeypatch, QUIET[quiet])
    with pytest.raises(Refusal, match="gave no answer"):
        _record(tmp_path, candidate, root)
    assert overlay_root(tmp_path / "config.toml") is None


@pytest.mark.parametrize("git_version", GITS)
def test_an_overlay_beside_a_project_with_worktrees_is_still_recorded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, git_version: str
) -> None:
    # The legitimate user the tests above must not lose: a project with a main checkout and a
    # sibling worktree, as this project's own preset lays it out, and an overlay that is a
    # repository of its own beside both. Its root is under no checkout and holds none, and git
    # asked from inside it answers with its own repository, so it is recorded — from either
    # checkout, and on either git.
    _as(git_version, monkeypatch)
    project, worktrees = _clone_with_a_bare_shaped_directory(tmp_path)
    overlay = tmp_path / "stayfixed-private"
    overlay.mkdir()
    _git(overlay, "init", "-q", "-b", "main")
    _seed_overlay(overlay)
    for root in (project, worktrees / "feature"):
        machine = tmp_path / f"{root.name}.toml"
        report = setup(
            "recommended",
            home=tmp_path / "home",
            machine=machine,
            runner=Recorder(),
            yes=True,
            overlay=str(overlay),
            project_root=root,
        )
        assert report.overlay == overlay
        assert overlay_root(machine) == overlay


def test_a_home_that_is_a_link_to_a_directory_is_followed_once_and_written_where_it_leads(
    tmp_path: Path,
) -> None:
    # `--home` is the machine owner's own directory, and one that is a link — a home on another
    # volume — is that owner's layout: every write under it lands where it leads.
    real = tmp_path / "volume" / "me"
    real.mkdir(parents=True)
    home = tmp_path / "home"
    home.symlink_to(real)
    machine = tmp_path / "config.toml"
    setup(
        "recommended",
        home=home,
        machine=machine,
        runner=Recorder(),
        yes=False,
        overlay=None,
        project_root=tmp_path / "project",
    )
    assert machine.is_file()
    assert (real / USER_SETTINGS).is_file()
    assert home.is_symlink()


# For a test that needs a directory its owner may not write into: root writes into every one,
# and `os.access` answers yes for root whatever the mode says.
_ROOT_WRITES_EVERYWHERE = pytest.mark.skipif(
    os.geteuid() == 0, reason="root writes into every directory"
)


def _setup_through_the_cli(
    monkeypatch: pytest.MonkeyPatch, home: Path, machine: Path
) -> tuple[int, Recorder]:
    """`stayfixed setup --preset recommended --yes --home H --machine M`, through `cli.run`, with
    the runner a recorder: the frame is what turns an `OSError` into `internal error`, so a test
    about what the owner reads has to go through it."""
    from stayfixed.cli import build_parser, discover_registrars, run

    runner = Recorder()
    monkeypatch.setattr("stayfixed.setup.commands.subprocess_runner", lambda: runner)
    argv = ["setup", "--preset", "recommended", "--yes", "--home", str(home)]
    code = run([*argv, "--machine", str(machine)], parser=build_parser(discover_registrars()))
    return code, runner


@_ROOT_WRITES_EVERYWHERE
@pytest.mark.parametrize("locked", ["above-home", "home", "claude"])
def test_a_home_that_cannot_take_the_write_is_refused_before_any_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    locked: str,
) -> None:
    # Where the settings file lands, at mode 555: the directory a home that is not there yet
    # would be made in, the home, or the `.claude` already in it. Under a read-only parent
    # `home.mkdir(parents=True)` raised `PermissionError` into the frame as `internal error`; a
    # read-only home or `.claude` had the machine file written, and only then did the settings
    # write refuse, in words about a symlink that was not there. Each is refused naming the
    # directory, with nothing written and nothing run. Mutations (`mutations/`'s "setup stops
    # asking whether --home can be used before its first write" -> `above-home` and `home`;
    # "setup stops asking whether an existing .claude can be written" -> `claude`, asked of the
    # writable home instead).
    home = tmp_path / "home"
    directory = {"above-home": tmp_path / "locked", "home": home, "claude": home / ".claude"}[
        locked
    ]
    directory.mkdir(parents=True)
    if locked == "above-home":
        home = directory / "home"
    machine = tmp_path / "config.toml"
    with read_only(directory):
        code, runner = _setup_through_the_cli(monkeypatch, home, machine)
    out = capsys.readouterr().err
    assert code == 2 and out.startswith("stayfixed: refused:"), out
    assert f"--home {home} cannot be used: {directory} is not writable" in out
    assert "symlink" not in out
    assert not machine.exists()
    assert runner.calls == []


@_ROOT_WRITES_EVERYWHERE
def test_a_directory_the_settings_write_opens_to_read_and_cannot_is_refused_before_any_write(
    tmp_path: Path,
) -> None:
    # The settings write opens its file's directory `O_RDONLY`, and a directory at mode 300 takes
    # a new name and refuses that open: the question whether a name can be made there passed it,
    # the machine file was written, and the settings write then refused. Mutation (`mutations/`'s
    # "setup stops asking whether the settings write can read its directory").
    home, machine = tmp_path / "home", tmp_path / "config.toml"
    directory = home / ".claude"
    directory.mkdir(parents=True)
    runner = Recorder()
    with write_only(directory), pytest.raises(Refusal) as refused:
        setup(
            "recommended",
            home=home,
            machine=machine,
            runner=runner,
            yes=False,
            overlay=None,
            project_root=tmp_path / "project",
        )
    said = str(refused.value)
    assert f"{directory} is not readable, and the settings write opens it to read" in said, said
    assert not machine.exists() and runner.calls == []


@ROOT_SEARCHES_EVERYTHING
def test_a_home_mkdir_that_fails_is_a_refusal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The floor under the check above, and not dead: `os.access` answers for the real uid and
    # says yes to root whatever the mode, and a directory can change between the question and
    # the `mkdir`. Patching `mkdir` is how that interval is reached without a race. Mutation
    # (`mutations/`'s "setup lets a failed --home mkdir reach the frame"): the `except OSError`
    # around `home.mkdir` dropped -> `PermissionError` leaves `setup` and this reddens.
    home = tmp_path / "home"
    machine = tmp_path / "config.toml"

    def refused_mkdir(self: Path, *args: object, **kwargs: object) -> None:
        raise PermissionError(errno.EACCES, "Permission denied", str(self))

    monkeypatch.setattr(Path, "mkdir", refused_mkdir)
    with pytest.raises(Refusal) as refused:
        setup(
            "recommended",
            home=home,
            machine=machine,
            runner=Recorder(),
            yes=True,
            overlay=None,
            project_root=tmp_path / "project",
        )
    assert str(refused.value) == f"--home {home} could not be created (Permission denied)"
    assert not machine.exists()


@_ROOT_WRITES_EVERYWHERE
def test_a_read_only_home_whose_claude_directory_is_writable_is_set_up(tmp_path: Path) -> None:
    # Nothing is written into a home that holds a writable `.claude` already: the settings file
    # lands in `.claude`, and the `mkdir` of a home that is there is a no-op. Asking whether
    # `home` itself could be written refused this layout, which worked before the question was
    # asked, saying "<home> is not writable" about a directory no write touches. Mutation
    # (`mutations/`'s "setup stops asking whether an existing .claude can be written"): the
    # question asked of `home` instead of where the settings file lands -> refused, and this
    # reddens.
    home = tmp_path / "home"
    claude = home / ".claude"
    claude.mkdir(parents=True)
    machine = tmp_path / "config.toml"
    with read_only(home):
        setup(
            "recommended",
            home=home,
            machine=machine,
            runner=Recorder(),
            yes=False,
            overlay=None,
            project_root=tmp_path / "project",
        )
    assert machine.is_file()
    assert (home / USER_SETTINGS).is_file()


@_ROOT_WRITES_EVERYWHERE
def test_a_created_overlay_already_in_a_read_only_home_is_set_up(tmp_path: Path) -> None:
    # Run again over the overlay it made, `create:` clones nothing, so `<home>/<name>` being there
    # is the end of what the home has to take. Mutation (`mutations/`'s "setup asks whether --home
    # can take a created overlay that is already there"): asked whether or not it is there ->
    # refused, and this reddens.
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    _seed_overlay(home / "stayfixed-private")
    machine = tmp_path / "config.toml"
    runner = Recorder(answers={_OCTOS_PROBE: _A_TEMPLATE}, on_call=_populate_overlay)
    with read_only(home):
        setup(
            "recommended",
            home=home,
            machine=machine,
            runner=runner,
            yes=True,
            overlay="create:octo/stayfixed-private",
            project_root=tmp_path / "project",
        )
    assert not any(argv[:3] == ["gh", "repo", "create"] for argv in runner.calls)
    assert machine.is_file()


@pytest.mark.parametrize("below", [False, True], ids=["home", "above-home"])
def test_a_home_that_is_a_regular_file_is_refused_as_one(tmp_path: Path, below: bool) -> None:
    # A regular file where `--home`, or a directory above it, has to be: the `mkdir` names it
    # ("File exists", "Not a directory"). The question about where the settings file lands walks
    # up to that file, and asking it whether a name can be made in it answered "is not writable",
    # a cause the path does not have. Mutation (`mutations/`'s "setup calls a regular file in
    # --home's place not writable"): the directory test dropped -> this reddens.
    blocker = tmp_path / "file"
    blocker.write_text("not a directory\n")
    home = blocker / "home" if below else blocker
    machine = tmp_path / "config.toml"
    with pytest.raises(Refusal) as refused:
        setup(
            "recommended",
            home=home,
            machine=machine,
            runner=Recorder(),
            yes=False,
            overlay=None,
            project_root=tmp_path / "project",
        )
    reason = "Not a directory" if below else "File exists"
    assert str(refused.value) == f"--home {home} could not be created ({reason})"
    assert not machine.exists()


@_ROOT_WRITES_EVERYWHERE
def test_a_created_overlay_in_a_read_only_home_is_refused_before_gh_runs(tmp_path: Path) -> None:
    # `--overlay create:<owner>/<name>` clones into `<home>/<name>`, so a home with a writable
    # `.claude` still has to take that one directory — and finding out from the clone is finding
    # out after `gh repo create` made a repository on somebody's account. Mutation
    # (`mutations/`'s "setup stops asking whether --home can take a created overlay"): the question
    # dropped -> `gh repo create` runs, and this reddens.
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    machine = tmp_path / "config.toml"
    runner = Recorder(answers={_OCTOS_PROBE: _A_TEMPLATE}, on_call=_populate_overlay)
    with read_only(home), pytest.raises(Refusal) as refused:
        setup(
            "recommended",
            home=home,
            machine=machine,
            runner=runner,
            yes=True,
            overlay="create:octo/stayfixed-private",
            project_root=tmp_path / "project",
        )
    assert str(refused.value) == f"--home {home} cannot be used: {home} is not writable"
    assert runner.calls == []
    assert not machine.exists()


@ROOT_SEARCHES_EVERYTHING
@pytest.mark.parametrize(
    "root_in_a_repository",
    [False, pytest.param(True, marks=needs_git)],
    ids=["no-repository", "repository"],
)
def test_a_created_overlay_under_a_home_nobody_may_search_is_refused_before_anything(
    tmp_path: Path, root_in_a_repository: bool
) -> None:
    # `--overlay create:` with `--home` below a directory nobody may search: the walk up from the
    # destination (`_candidate_repository` -> `_nearest_directory`) asked `is_dir` of it first and
    # `PermissionError` reached the frame as `stayfixed: internal error`. The questions about
    # `--home` come before where the overlay lies, and they name the file they could not ask
    # about. Mutation (`mutations/`'s "setup asks where the overlay lies before it asks about
    # --home") reddens this on the wording.
    locked = tmp_path / "locked"
    locked.mkdir()
    home = locked / "home"
    project = tmp_path / "project"
    project.mkdir()
    if root_in_a_repository:
        _git(project, "init", "-q", "-b", "main")
    machine = tmp_path / "config.toml"
    runner = Recorder(answers={_OCTOS_PROBE: _A_TEMPLATE}, on_call=_populate_overlay)
    with unsearchable(locked), pytest.raises(Refusal) as refused:
        setup(
            "recommended",
            home=home,
            machine=machine,
            runner=runner,
            yes=True,
            overlay="create:octo/stayfixed-private",
            project_root=project,
        )
    assert str(refused.value) == (
        f"{quoted(str(home / 'stayfixed-private'))} cannot be checked (Permission denied), so "
        "nothing was written"
    )
    assert runner.calls == []
    assert not machine.exists()


def _below_a_locked_directory(tmp_path: Path, what: str) -> tuple[dict[str, Any], Path]:
    """`setup`'s keyword arguments with `what` — `--overlay` or `--root` —
    below `tmp_path/locked`, and the path below it that cannot be asked about once it is locked."""
    locked = tmp_path / "locked"
    locked.mkdir()
    overlay = tmp_path / "overlay"
    _seed_overlay(overlay)
    arguments: dict[str, Any] = {
        "home": tmp_path / "home",
        "overlay": str(overlay),
        "project_root": tmp_path / "project",
    }
    if what == "overlay":
        asked = locked / "overlay"
        _seed_overlay(asked)
        arguments["overlay"] = str(asked)
    else:
        asked = locked / "project"
        asked.mkdir()
        arguments["project_root"] = asked
    return arguments, asked


@ROOT_SEARCHES_EVERYTHING
@pytest.mark.parametrize("what", ["overlay", "root"])
def test_a_path_setup_cannot_ask_about_before_its_first_write_is_a_refusal_naming_it(
    tmp_path: Path, what: str
) -> None:
    # Each of these ended in `stayfixed: internal error: PermissionError`, with the path in a
    # traceback's words: `--overlay` from the overlay probe's `is_dir`, `--root` from the walk to
    # the nearest directory git is asked from. Neither step words that fault itself, so the phase's
    # floor
    # does, naming the path the predicate was handed. Mutation (`mutations/`'s "setup lets a path
    # it cannot ask about before its first write reach the frame"): the floor's `except` dropped
    # -> `PermissionError` leaves `setup`, and every case reddens.
    arguments, asked = _below_a_locked_directory(tmp_path, what)
    machine = tmp_path / "config.toml"
    runner = Recorder()
    with unsearchable(tmp_path / "locked"), pytest.raises(Refusal) as refused:
        setup("recommended", machine=machine, runner=runner, yes=True, **arguments)
    assert str(refused.value) == (
        f"{quoted(str(asked))} cannot be checked (Permission denied), so nothing was written"
    )
    assert runner.calls == []
    assert not machine.exists()


@ROOT_SEARCHES_EVERYTHING
@pytest.mark.parametrize("mode", [0o000, 0o600], ids=["no-access", "readable-only"])
def test_a_created_overlay_whose_destination_cannot_be_searched_is_refused_before_anything(
    tmp_path: Path, mode: int
) -> None:
    # Over a `<home>/<name>` that is there, `create:` clones nothing and the home takes no new
    # directory, so nothing about `--home` refused it; `overlay.create` then looked inside it for
    # an overlay, and a destination nobody may search raised `PermissionError` there, as
    # `internal error`, after the machine file and both plugin installs. Looking inside asks the
    # search bit alone, so a destination that can be read and not searched is refused too.
    # Mutations (`mutations/`'s "setup stops asking whether a created overlay's destination can be
    # searched" -> the machine file is written and `PermissionError` leaves `setup`; "setup asks
    # whether a created overlay's destination can be read, not searched" -> `readable-only`).
    home = tmp_path / "home"
    destination = home / "stayfixed-private"
    destination.mkdir(parents=True)
    machine = tmp_path / "config.toml"
    runner = Recorder(answers={_OCTOS_PROBE: _A_TEMPLATE}, on_call=_populate_overlay)
    with at_mode(destination, mode, after=0o755), pytest.raises(Refusal) as refused:
        setup(
            "recommended",
            home=home,
            machine=machine,
            runner=runner,
            yes=True,
            overlay="create:octo/stayfixed-private",
            project_root=tmp_path / "project",
        )
    assert str(refused.value) == f"--home {home} cannot be used: {destination} cannot be searched"
    assert runner.calls == []
    assert not machine.exists()


# `_before_the_first_write`'s steps, in its documented order, for a `create:` run.
_THE_PHASE = (
    "_requested_overlay",
    "load_preset",
    "_check_home_usable",
    "_outside_the_project",
)


def test_every_question_before_the_first_write_is_asked_in_the_documented_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The order is what makes "refused before anything was written" true of every step: a step
    # that ran after a write or a program would have that write behind its refusal. Each step,
    # each write and each program run is logged as it happens. Mutation (`mutations/`'s "setup
    # asks where the overlay lies before it asks about --home") -> the order differs, and this
    # reddens.
    from stayfixed.setup import run

    events: list[str] = []

    def logged(name: str) -> None:
        original = getattr(run, name)

        def step(*args: Any, **kwargs: Any) -> Any:
            events.append(name)
            return original(*args, **kwargs)

        monkeypatch.setattr(run, name, step)

    for name in (*_THE_PHASE, "write_machine", "_write_user_settings"):
        logged(name)
    real_mkdir = Path.mkdir

    def mkdir(self: Path, *args: Any, **kwargs: Any) -> None:
        events.append("mkdir")
        real_mkdir(self, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", mkdir)

    def ran(argv: list[str], cwd: Path) -> None:
        events.append("run")
        _populate_overlay(argv, cwd)

    setup(
        "recommended",
        home=tmp_path / "home",
        machine=tmp_path / "config.toml",
        runner=Recorder(answers={_OCTOS_PROBE: _A_TEMPLATE}, on_call=ran),
        yes=True,
        overlay="create:octo/stayfixed-private",
        project_root=tmp_path / "project",
    )
    phase = len(_THE_PHASE)
    assert tuple(events[:phase]) == _THE_PHASE, events
    assert events[phase] == "mkdir", events
    assert {"write_machine", "_write_user_settings", "run"} <= set(events[phase:]), events


@pytest.mark.parametrize("place", ["claude", "home", "root", "overlay"])
def test_a_symlink_loop_at_any_path_setup_is_given_is_a_refusal_naming_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    place: str,
) -> None:
    # Python 3.11 and 3.12 raise `RuntimeError` resolving a path through a symlink loop, which the
    # floor under `setup`'s questions before its first write, an `except OSError`, did not catch:
    # a loop at `~/.claude`, `--home`, `--root` or `--overlay` was
    # `stayfixed: internal error: RuntimeError` there, while 3.13 refused some in other words and
    # recorded the overlay past a looping `--root`. Every resolve in `setup` goes through
    # `fsops.resolved`, so each is the floor's refusal, naming the path, on every interpreter, with
    # nothing written and nothing run. Mutations (`mutations/`'s "setup's command resolves --root
    # past fsops" -> `root`; "setup resolves --overlay past fsops" -> `overlay`; "fsops.resolved
    # answers a loop with a path where the interpreter does" -> `home`).
    from stayfixed.cli import build_parser, discover_registrars, run

    home, machine = tmp_path / "home", tmp_path / "config.toml"
    root, overlay = tmp_path / "project", tmp_path / "overlay"
    home.mkdir()
    root.mkdir()
    _seed_overlay(overlay)
    looped = {
        "claude": home / ".claude",
        "home": home,
        "root": root,
        "overlay": overlay,
    }[place]
    if looped.is_dir():
        shutil.rmtree(looped)
    looped.parent.mkdir(parents=True, exist_ok=True)
    looped.symlink_to(looped)
    argv = ["setup", "--preset", "recommended", "--yes", "--home", str(home)]
    argv += ["--machine", str(machine), "--root", str(root), "--overlay", str(overlay)]
    runner = Recorder()
    monkeypatch.setattr("stayfixed.setup.commands.subprocess_runner", lambda: runner)
    code = run(argv, parser=build_parser(discover_registrars()))
    said = capsys.readouterr().err
    assert code == 2, said
    assert said.startswith("stayfixed: refused: "), said
    # `--root` is resolved by the command before `setup` is called, and named as the flag.
    # A loop at `~/.claude` or `--home` is met resolving the settings file below it, named.
    asked = home / USER_SETTINGS if place in ("claude", "home") else looped
    named = f"--root {quoted(str(looped))}" if place == "root" else quoted(str(asked))
    assert f"{named} cannot be checked (" in said, said
    assert not machine.exists() and runner.calls == []


def test_a_project_root_through_a_symlink_loop_handed_to_setup_is_refused(tmp_path: Path) -> None:
    # The command resolves `--root` before it calls `setup`, and `setup` resolves the root it is
    # handed again where it compares the overlay with it, under the floor: a caller of the
    # library that hands it a loop gets the floor's refusal, on every interpreter. Mutation
    # (`mutations/`'s "setup resolves the project root past fsops") -> 3.13 records the overlay,
    # and 3.11 raises `RuntimeError`.
    root, overlay = tmp_path / "project", tmp_path / "overlay"
    root.symlink_to(root)
    _seed_overlay(overlay)
    with pytest.raises(Refusal, match="cannot be checked"):
        _record(tmp_path, overlay, root)
    assert not (tmp_path / "config.toml").exists()


def test_the_plugin_config_mirror_follows_the_machine_file(tmp_path: Path) -> None:
    # The mirror was written from `_new_personal_values`, which is empty on every run after the
    # first — so an owner who set `preset` in the machine file, the documented way (`README.md`:
    # "Written by: you, or `stayfixed setup`"), kept the preset's in `~/.claude/settings.json` for
    # ever, and Claude Code read that. The mirror is a projection of the machine file and is
    # recomputed from it on every run. The direction is a decision, recorded in `setup.run`: a value
    # set in Claude Code's own plugin-config UI loses to the machine file, because one file has to
    # win and that one is the file every reader reads.
    #
    # Mutation (`mutations/`'s "setup mirrors only the values this run itself added"): the argument
    # goes back to `personal` → the second run leaves the preset's in the settings file and this
    # reddens.
    home = tmp_path / "home"
    machine = tmp_path / "config.toml"
    for _ in range(1):
        setup(
            "recommended",
            home=home,
            machine=machine,
            runner=Recorder(),
            yes=True,
            overlay=None,
            project_root=tmp_path / "project",
        )
    write_machine(machine, personal={"preset": "mine"}, overlay_root=None, machine={})
    setup(
        "recommended",
        home=home,
        machine=machine,
        runner=Recorder(),
        yes=True,
        overlay=None,
        project_root=tmp_path / "project",
    )
    settings = json.loads((home / USER_SETTINGS).read_text(encoding="utf-8"))
    options = settings["pluginConfigs"]["stayfixed@stayfixed-marketplace"]["options"]
    assert options["preset"] == "mine"


def test_a_created_tree_that_is_not_an_overlay_says_the_repository_now_exists(
    tmp_path: Path,
) -> None:
    # The one refusal that cannot precede a write, and what it owes the owner. `--overlay
    # create:` asks GitHub to generate from a template repository this project does not publish,
    # so what arrives is whatever is on that account — and if it is not an overlay, the run has
    # to say so *and* say that a private repository now exists, because the `SetupReport` is
    # discarded on a refusal and nothing else would ever tell them.
    def _wrong_tree(argv: list[str], cwd: Path) -> None:
        if argv[:3] != ["gh", "repo", "create"]:
            return
        target = cwd / argv[3].split("/")[-1] / ".claude-plugin"
        target.mkdir(parents=True, exist_ok=True)
        for name, body in (
            ("plugin.json", {"name": "not-an-overlay"}),
            ("marketplace.json", {"name": "not-a-marketplace", "plugins": []}),
        ):
            (target / name).write_text(json.dumps(body), encoding="utf-8")

    home = tmp_path / "home"
    home.mkdir()
    with pytest.raises(Refusal) as refused:
        setup(
            "recommended",
            home=home,
            machine=tmp_path / "config.toml",
            runner=Recorder(answers={_OCTOS_PROBE: _A_TEMPLATE}, on_call=_wrong_tree),
            yes=True,
            overlay="create:octo/stayfixed-private",
            project_root=tmp_path / "project",
        )
    message = str(refused.value)
    assert "does not name a stayfixed overlay" in message
    assert "octo/stayfixed-private was created and cloned" in message
    assert "nothing was recorded in the machine configuration" in message
    assert overlay_root(tmp_path / "config.toml") is None


@pytest.mark.parametrize("per_file", [False, True])
def test_a_symlinked_settings_file_or_claude_directory_is_written_through(
    tmp_path: Path, per_file: bool
) -> None:
    # `stow` links the file where `~/.claude` is already there, and the directory where it is not:
    # either is the owner's layout, so the file the link leads to gains the rules and the link
    # stays. Mutation (`mutations/`'s "setup writes the settings file without resolving it") ->
    # the link becomes a regular file.
    home = tmp_path / "home"
    home.mkdir()
    leads_to = tmp_path / "dotfiles" / ".claude" / "settings.json"
    leads_to.parent.mkdir(parents=True)
    if per_file:
        leads_to.write_text(json.dumps({"theme": "dark"}), encoding="utf-8")
        (home / ".claude").mkdir()
        (home / USER_SETTINGS).symlink_to(leads_to)
    else:
        (home / ".claude").symlink_to(leads_to.parent)
    setup(
        "recommended",
        home=home,
        machine=tmp_path / "config.toml",
        runner=Recorder(),
        yes=True,
        overlay=None,
        project_root=tmp_path / "project",
    )
    assert "permissions" in json.loads(leads_to.read_text(encoding="utf-8"))
    assert (home / (USER_SETTINGS if per_file else ".claude")).is_symlink()


def test_a_user_settings_file_the_encoder_cannot_write_back_is_a_failure_naming_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Python 3.12's indenting encoder stops near 994 levels, under what its parser reads, so a
    # deep `~/.claude/settings.json` was read and then ended `stayfixed setup` in
    # `RecursionError` while the merge was encoded. Forced on every interpreter: it is the
    # failure a file nested past the parser gets, and the file is left as it was. Mutation
    # (declared): setup encodes the merged settings with a bare `json.dumps` again.
    from stayfixed import jsonobject

    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    (home / USER_SETTINGS).write_text('{"theme": "dark"}', encoding="utf-8")
    monkeypatch.setattr(jsonobject, "_encode", overflowing)
    with pytest.raises(Failure) as caught:
        setup(
            "recommended",
            home=home,
            machine=tmp_path / "config.toml",
            runner=Recorder(),
            yes=True,
            overlay=None,
            project_root=tmp_path / "project",
        )
    assert str(caught.value) == f"{home / USER_SETTINGS} {NESTED}"
    assert (home / USER_SETTINGS).read_text(encoding="utf-8") == '{"theme": "dark"}'
