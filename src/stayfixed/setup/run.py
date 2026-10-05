"""`setup(preset, ...)`: machine setup, once — after stayfixed is installed, before any attach.

Five things, each reported and each independently skippable, in this order: write the machine
file (the personal defaults the preset names, for whichever of them nothing has recorded yet);
merge the preset's deny rules and the personal values into the machine-scope settings file;
register each preset plugin's marketplace and install from it, per configured harness; report
whether `stayfixed` itself resolves on `PATH`; and, only when the caller named an answer, create
or record the private overlay.

**A preset default never overwrites a value already recorded.** The first draft of this module
rebuilt `[personal]` from the preset's own defaults on every run, which meant a second
`setup --preset recommended` reset `reply_language` back to `""` even after the owner had set it by
hand — exactly the value `skills/setup/SKILL.md` calls "the user's to set" and `setup.machine`'s own
docstring promises survives a rewrite that "only set one of them". `_new_personal_values` computes
only the keys the machine file does not already carry, and that is what both `write_machine` and the
settings file's `pluginConfigs` receive — an empty dict on every run after the first, once every key
has a recorded value.

**Marketplaces are registered before anything is installed from them, and per-plugin sources are
never guessed.** The first draft attempted `claude plugin install superpowers@obra` on a fresh
machine and always failed there — `obra` and `upstash` are GitHub accounts, not marketplace names,
and every measured successful install in this tree's own spike record
(`docs/plans/2026-09-05-agent-harness-p0-spikes.md`) is preceded by a `marketplace add`. Checked
before writing this fix (`gh api repos/...`, `claude plugin marketplace list` on the machine this
was written on): `superpowers` and `context7` both ship in Anthropic's own official marketplace,
`anthropics/claude-plugins-official`, which a Claude Code install already carries — the
`marketplace add` this module still issues is idempotent defence in depth, not a first registration,
and its own real output confirms that (`✔ Marketplace 'claude-plugins-official' already on disk`).
No non-interactive, non-guessed source could be established for Codex, so nothing is attempted there
for these two plugins; the recommended preset's own `[plugins.claude]` table and the README carry
the reasoning and the recommendation respectively.

**Two harnesses, two verbs, and no unmeasured flags.** Claude Code installs a plugin with `claude
plugin install <name>@<marketplace>`, bare — the spike record's own transcript reports
`(scope: user)` as the *default* a bare install already gets, not something a flag adds, and `-y`
appears in that record only on `plugin uninstall`, never `install`. Codex adds one with
`codex plugin add <name>@<marketplace>` when a marketplace is declared for it — measured, not
assumed, in that same spike record. A harness or a plugin with no declared marketplace gets a note,
never a guessed argv.

**`pluginConfigs` and not a flat top-level key.** Claude Code's own settings reference files a
plugin's non-sensitive `userConfig` answers under `pluginConfigs[<plugin-id>].options`, keyed by
`<plugin-name>@<marketplace-name>` and not by the plugin name alone — confirmed against
`code.claude.com/docs/en/settings-reference` before this was written, because a flatter shape
would round-trip through nothing Claude Code itself reads. `PLUGIN_ID` matches this repository's
own shipped manifest and marketplace names (`tests/test_manifests.py`), which is the pair this
plugin is actually installed under everywhere the preset's own `setup` runs.

**The overlay root is validated before anything is written, and the create branch is gated on
`--yes`.** `--yes` on `--overlay <path>` would be theatre in a harness where the command line
is written by a model, so it is not added there. What bounds the exposure instead is
`_requested_overlay`, and it runs **above the first write** — above the machine file, the
settings merge and the plugin installs, and for `create:` above `gh repo create` itself. Two
controls:

* **it must be an overlay**, which is `overlay.api.require_overlay` and not a pair of `is_file`
  calls. The old probe was the two manifests *existing*, which the stayfixed checkout satisfies
  and any Claude Code plugin repository satisfies; the probe now reads them and requires them to
  name the tree `stayfixed-overlay[-<owner>]` and `stayfixed-overlay-marketplace[-<owner>]`, the
  names `overlay init` writes and a harness installs an overlay by. `identity`'s own docstring
  is honest that a repository can still *claim* those names: it stops the accidents, and it
  stops this half from standing for nothing.
* **it must lie outside the repository the agent works in**, which now means outside *every*
  checkout of it. The old check refused `candidate == project` or `project in candidate.parents`
  and nothing else, so a parent directory and a sibling worktree both passed — and working
  in a worktree, which is ordinary, makes `--root` one, which is exactly the shape that passed.
  It now also refuses a candidate that *holds* the project root, and a candidate inside, holding
  or equal to any checkout of the project root's repository that `git` can name: what a
  repository ships reaches its own checkouts and nowhere else, so refusing every checkout of it
  removes the tree a clone can stage.
  `_outside_the_project` says how `git` is asked and from which side, and why. It is not a claim
  that the same bytes cannot be somewhere else on the machine — a separate clone of the same
  remote passes — only that the owner put them there. When `git` gives no answer for the project
  root only the path arms stand, and that is stated rather than assumed; once `git` has said
  there is a repository, a listing it cannot give is a refusal and not a pass.

For `create:`, the destination is `home/<name>` and is knowable from the arguments
(`overlay.api.target_root`), so it is checked before the call rather than after it: the first
draft ran `gh repo create`, cloned, renamed both manifests and installed the secret scan, and
*then* refused — leaving a private repository on somebody's GitHub account that nothing in the
report mentioned. `--yes` gets the one control it can really carry: `setup` refuses
`--overlay create:<owner>/<name>` without it, because `gh repo create` runs only after explicit
confirmation, and creating a repository on GitHub is the one irreversible, outward-facing act
this command performs.

**A symlinked settings file is a refusal with a remedy that works, not an internal error.**
`home` is the machine owner's own directory and a home managed by stow, chezmoi or a synced
directory is the
most common non-default layout there is, but the settings file still goes through the
`O_NOFOLLOW` walk — so the containment rule's two stages both apply here: `config.paths
.contained` gives the user-facing refusal above the first write, and `fsops.write_within` is the
floor under it for a component that becomes a symlink afterwards. Before, only the second stage
existed, and it surfaced as `stayfixed: internal error: UnsafePath` after the machine file had
already been written. What the refusal prints is held to the same standard as the refusal
itself: `_home_that_leads_there` offers a `--home` only when that `--home` really writes the file
the link leads to, and says plainly that no such value exists when none does — a remedy that
exits 0 into a file no reader reads is the defect one door over.
"""

from __future__ import annotations

import datetime
import json
import os
import shutil
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from stayfixed import REPOSITORY_URL, __version__, fsops
from stayfixed.config.paths import PathEscape, contained
from stayfixed.errors import Failure, Refusal
from stayfixed.fsops import UnsafePath, utf_8_name
from stayfixed.gitenv import NO_ANSWER, answer_lines, git_run, in_work_tree
from stayfixed.jsonobject import json_object
from stayfixed.presets import load_preset
from stayfixed.printed import answered
from stayfixed.runner import Runner
from stayfixed.setup.machine import USER_SETTINGS, read_personal, write_machine

# `<plugin-name>@<marketplace-name>`, matching `.claude-plugin/plugin.json`'s `name` and
# `.claude-plugin/marketplace.json`'s `name` (`tests/test_manifests.py` holds both). Claude
# Code keys `pluginConfigs` by this pair, not by the plugin name alone.
PLUGIN_ID = "stayfixed@stayfixed-marketplace"
# The release tag scheme (`vX.Y.Z`); `uv tool install` has no `--from`, so the positional git URL
# form pinned to a release tag is the install form (`git+https://…@<tag>`; principle 9: the CLI
# installs from a git tag). An f-string with a doubled brace, because the concatenation it replaces
# read as somebody having forgotten one: `{version}` is meant to survive into the template and be
# filled by the caller, and `{{version}}` says so.
INSTALL_COMMAND = f"uv tool install git+{REPOSITORY_URL}@v{{version}}"
# One verb pair per harness, fixed here rather than in the preset: which CLI verb installs a
# plugin is a property of the harness, never of any one plugin, and the two differ (measured;
# the module docstring's "Two harnesses, two verbs" paragraph).
_MARKETPLACE_ADD = {
    "claude": lambda source: ["claude", "plugin", "marketplace", "add", source],
    "codex": lambda source: ["codex", "plugin", "marketplace", "add", source],
}
_PLUGIN_INSTALL = {
    "claude": lambda full: ["claude", "plugin", "install", full],
    "codex": lambda full: ["codex", "plugin", "add", full],
}
# What `--overlay <path>` and `--overlay create:` are each about to do, for the refusal the
# overlay probe raises. One sentence each, so the two commands that ask "is this an overlay"
# differ in what they were doing and not in what the answer means.
_RECORDING = (
    "--overlay must name a real overlay's root — the tree `stayfixed overlay create` renders "
    "and `stayfixed overlay init` names after you — because this path becomes the machine's "
    "trust anchor: every `stayfixed attach` on this machine reads rules and notes out of it"
)
_CREATED = (
    "the repository was created and cloned, and nothing was recorded in the machine "
    "configuration; look at what arrived, then record it with `stayfixed setup --overlay <path>`"
)
# Both halves of the containment rule for the settings file, said once. The refusal above the
# first write names the link and the way out; the walk at write time is the floor under it.
_SYMLINKED_SETTINGS = (
    f"stayfixed writes {USER_SETTINGS} through a walk that never follows a symlink, so it will "
    f"not write through this one"
)


@dataclass(frozen=True)
class SetupReport:
    """What one `setup` run did. Every field here is this run's own computation, printable."""

    machine_written: bool
    plugins_installed: tuple[str, ...]
    deny_written: bool
    cli_on_path: bool
    overlay: Path | None
    notes: tuple[str, ...]


def _personal_defaults(preset: dict[str, Any]) -> dict[str, Any]:
    return dict(preset.get("defaults", {}).get("personal", {}))


def _new_personal_values(preset: dict[str, Any], machine: Path) -> dict[str, Any]:
    """The preset's personal defaults, minus every key the machine file already carries.

    A key present in the file — set by an earlier `setup`, or by the owner's own hand — is the
    owner's, and a preset default may not win over it on a later run. An absent key gets the
    preset's default, which is what makes a *first* run write all three.
    """
    existing = read_personal(machine)
    return {k: v for k, v in _personal_defaults(preset).items() if k not in existing}


def _agents(preset: dict[str, Any]) -> tuple[str, ...]:
    agents = preset.get("defaults", {}).get("stayfixed", {}).get("agents", [])
    return tuple(agent for agent in agents if isinstance(agent, str))


def _marketplace(preset: dict[str, Any], agent: str) -> tuple[str, str] | None:
    """`(source, marketplace name)` for `agent`, or `None` when the preset declares none.

    `None` is not a fault: nothing is vendored for a harness on a guess, and the caller reports
    it as a note rather than attempting an argv nobody measured.
    """
    table = preset.get("plugins", {}).get(agent)
    if not isinstance(table, dict):
        return None
    source, marketplace = table.get("source"), table.get("marketplace")
    if not isinstance(source, str) or not isinstance(marketplace, str):
        return None
    return source, marketplace


def _install_plugins(
    preset: dict[str, Any], agents: Sequence[str], *, home: Path, runner: Runner
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    selectors = [s for s in preset.get("plugins", {}).get("install", []) if isinstance(s, str)]
    installed: list[str] = []
    notes: list[str] = []
    for agent in agents:
        market = _marketplace(preset, agent)
        if market is None:
            if selectors:
                notes.append(
                    f"{agent}: no verified marketplace for {', '.join(selectors)}; "
                    f"install manually if this harness supports it (see README)"
                )
            continue
        source, marketplace = market
        add_argv_of, install_argv_of = _MARKETPLACE_ADD.get(agent), _PLUGIN_INSTALL.get(agent)
        if add_argv_of is None or install_argv_of is None:
            notes.append(f"{agent}: no known plugin command for this harness")
            continue
        # Idempotent by construction: an already-registered source is a note from `claude`/
        # `codex` themselves ("already on disk"), read here through the same non-zero-is-a-note
        # path as everything else — a missing binary is `Completed(127, ...)` from `Runner`
        # itself (its own docstring: "a missing binary is a finding, never a traceback").
        added = runner.launch(add_argv_of(source), home)
        if added.code != 0:
            detail = answered(added)
            notes.append(f"{agent}: could not register marketplace {source} ({detail})")
            continue
        for selector in selectors:
            argv = install_argv_of(f"{selector}@{marketplace}")
            done = runner.launch(argv, home)
            if done.code == 0:
                if selector not in installed:
                    installed.append(selector)
            else:
                detail = answered(done)
                notes.append(f"{agent}: `{' '.join(argv)}` did not succeed ({detail})")
    return tuple(installed), tuple(notes)


def _read_document(path: Path) -> tuple[dict[str, Any], str]:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}, ""
    except OSError as exc:
        raise Failure(f"{path} cannot be read: {exc}") from exc
    except UnicodeDecodeError:
        raise Failure(f"{path} is not UTF-8 text") from None
    if not text.strip():
        return {}, text
    # The file is the owner's and this run rewrites it, so valid JSON past the parser's reach is
    # refused as a `Failure` naming it rather than read, and rather than ending setup in an
    # internal error.
    return json_object(text, str(path), error=Failure), text


def _write_user_settings(
    home: Path,
    deny_rules: Sequence[str],
    personal: Mapping[str, Any],
    *,
    settings: Path | None = None,
) -> bool:
    """Merge the preset's deny rules and the personal values into `<home>/<USER_SETTINGS>`.

    Merge, never replace: the owner's own file predates stayfixed on most machines, and nothing
    this run did not add may be recorded as if it had. Deny only — this never reads or writes
    `permissions.allow` — and `pluginConfigs` gets the same treatment, key by key inside its own
    `options`, so a value this run did not set survives a second one same as `write_machine`'s.

    `settings` names the file itself, for the layout no `--home` can express: `stow` folds
    a package as far as it can, so with `~/.claude` already there it links
    `~/.claude/settings.json` into a dotfiles tree, and `--home <dotfiles>/claude` writes
    `<dotfiles>/claude/.claude/settings.json` — a file no reader reads. When it is given, the
    root of the write is the named file's own directory and the walk is one component deep.
    """
    path = settings if settings is not None else home / USER_SETTINGS
    document, text = _read_document(path)

    permissions = document.get("permissions")
    permissions = dict(permissions) if isinstance(permissions, dict) else {}
    raw_deny = permissions.get("deny")
    existing_deny = (
        [r for r in raw_deny if isinstance(r, str)] if isinstance(raw_deny, list) else []
    )
    permissions["deny"] = existing_deny + [r for r in deny_rules if r not in existing_deny]
    document["permissions"] = permissions

    plugin_configs = document.get("pluginConfigs")
    plugin_configs = dict(plugin_configs) if isinstance(plugin_configs, dict) else {}
    entry = plugin_configs.get(PLUGIN_ID)
    entry = dict(entry) if isinstance(entry, dict) else {}
    options = entry.get("options")
    options = dict(options) if isinstance(options, dict) else {}
    options.update(personal)
    entry["options"] = options
    plugin_configs[PLUGIN_ID] = entry
    document["pluginConfigs"] = plugin_configs

    new_text = json.dumps(document, indent=2, sort_keys=True) + "\n"
    if new_text == text:
        return False
    root, relative = (
        (settings.parent, settings.name) if settings is not None else (home, USER_SETTINGS)
    )
    try:
        # One write, through whichever root `path` named. With `--settings` the root is the
        # owner's own directory and the walk is one component deep — and that walk does NOT
        # refuse a symlink at the file itself: `open_within` never opens the final name, and
        # `os.replace` replaces a link entry rather than following it. This comment claimed it
        # did; the measurement was a destroyed link and exit 0. `_check_settings_parent` is
        # what refuses that link, above every write, and it asks `contained()` — the identical
        # question `_check_settings_path` asks of `<home>/.claude/settings.json`.
        #
        # Without it this is the floor under `_check_settings_path`, and not dead: a component
        # that became a symlink, or stopped being a directory, between that check and this
        # write can only be refused here. `UnsafePath` is an `OSError`, and reaching `cli.run`'s
        # final handler is what made the ordinary symlinked `~/.claude` an `internal error`.
        fsops.write_within(root, relative, new_text)
    except UnsafePath as exc:
        raise Refusal(f"{path} cannot be written: {exc}; {_SYMLINKED_SETTINGS}") from exc
    except OSError as exc:
        # `UnsafePath` is not the only `OSError` reachable here, and the two that are not it
        # used to leave this library and land on `cli.run`'s final handler as `stayfixed:
        # internal error: FileNotFoundError`, exit 2, no remedy -- the exact rendering the
        # paragraph above and `_check_settings_path` were written to remove. `write_within`
        # opens the root itself before the loop that wraps `ELOOP`/`ENOTDIR` into `UnsafePath`,
        # so a root that is not there and a root that is a symlink to a directory both arrive
        # raw. `--settings` is what makes both ordinary: a typo in the directory component, and
        # the whole-directory stow layout (`--settings ~/.claude/settings.json`) that the
        # refusal below now advertises. One refusal, naming the path and both causes.
        raise Refusal(
            f"{path} cannot be written ({type(exc).__name__}: {exc}); its directory has to "
            f"exist and be a real directory, because {_SYMLINKED_SETTINGS}"
        ) from exc
    return True


def _settings_symlink(home: Path) -> Path | None:
    """The first symlink between `home` and the settings file, or `None`."""
    target = home / USER_SETTINGS
    for ancestor in [target, *target.parents]:
        if ancestor == home:
            return None
        if ancestor.is_symlink():
            return ancestor
    return None


def _home_that_leads_there(home: Path, link: Path) -> Path | None:
    """The `--home` whose own walk writes the file this link leads to, or `None` for a layout no
    `--home` can express.

    One computation for both shapes of the same accident, because the first draft had one arm
    written for the directory shape and it misfired on the other. `stow` folds a package as far
    as it can: with `~/.claude` already created by Claude Code it links the *file*, so the link
    is `~/.claude/settings.json -> <dotfiles>/claude/settings.json`. The old remedy compared the
    link's basename to its target's, which is trivially true for a per-file link, and printed
    `--home <dotfiles>/claude` — under which this command writes
    `<dotfiles>/claude/.claude/settings.json`, exits 0, and leaves the file the link leads to
    untouched and every reader reading nothing. That is the wrong-file write `--machine`'s old
    default made, arriving through the remedy instead of through the default.

    What `--home H` actually writes is `H/<USER_SETTINGS>` and nothing else, so a remedy exists
    exactly when what the link leads to *is* a `<USER_SETTINGS>` inside some directory — and
    that directory is the answer. Whatever of `USER_SETTINGS` lies below the link still follows
    it, which is what puts the directory and the file shapes into one expression.
    """
    wanted = Path(USER_SETTINGS).parts
    leads_to = link.resolve() / (home / USER_SETTINGS).relative_to(link)
    if leads_to.parts[-len(wanted) :] != wanted:
        return None
    return leads_to.parents[len(wanted) - 1]


def _check_settings_path(home: Path) -> None:
    """Refuse a `~/.claude` this command cannot write through — above the first write.

    `home` is the machine owner's own directory rather than an untrusted root, but the write
    goes through the `O_NOFOLLOW` walk all the same, and the walk had no user-facing half: a
    home managed by stow, chezmoi or a synced directory raised `UnsafePath` out of
    `fsops.write_within`, which `cli.run` rendered as `stayfixed: internal error: UnsafePath:
    '.claude/settings.json': '.claude' is a symlink or not a directory`, exit 2 — after the
    machine file had been written. `config.paths.contained` is the missing half, and this
    translates its verdict into a refusal that names the link and the way out.
    """
    try:
        contained(home, USER_SETTINGS)
    except PathEscape as exc:
        link = _settings_symlink(home)
        if link is None:
            raise
        real = link.resolve()
        instead = _home_that_leads_there(home, link)
        kind = "file" if link == home / USER_SETTINGS else "directory"
        if instead is not None:
            remedy = (
                f"run `stayfixed setup --home {instead}`, which writes the file this link leads "
                f"to, or replace the link with a real {kind}"
            )
        else:
            # An honest "this cannot be expressed" beats a command that writes somewhere else
            # and exits 0. The two ways out are named because both are ordinary dotfiles work:
            # `stow` can package the directory as `.claude`, and `stow --adopt` (and its
            # equivalents) take a real file back afterwards.
            remedy = (
                f"no --home can name it: this command writes <home>/{USER_SETTINGS} and nothing "
                f"else, and {real} is not a {USER_SETTINGS} inside any directory. "
                f"`--settings {real}` writes that file directly. Otherwise point "
                f"the link at a path ending in {USER_SETTINGS}, or take the link away, let this "
                f"command write a real {kind}, and have your dotfiles manager adopt it"
            )
        raise Refusal(
            f"{link} is a symlink to {real}; {_SYMLINKED_SETTINGS}. A dotfiles manager or a "
            f"synced home is the usual reason — {remedy}"
        ) from exc


def _check_settings_parent(settings: Path) -> None:
    """Refuse a `--settings` whose directory cannot be written through — above the first write.

    The other half of `_check_settings_path`, for the layout the flag exists for. `--settings`
    names the file, so the root of the write is the file's own directory; `fsops.open_within`
    opens that root with `O_NOFOLLOW` before the loop that wraps `ELOOP`/`ENOTDIR` into
    `UnsafePath`, so a directory that is not there and a directory that is a symlink are both
    refused there. Both were refused *late*: `_write_user_settings` runs after
    `home.mkdir(parents=True)` and after `write_machine`, so
    `stayfixed setup --settings /typo/settings.json` created the home tree, wrote the machine
    configuration, and then exited 2. The same two conditions, asked here while nothing is on
    disk — which is what the docstring above claims for every structural question.

    `is_dir() and not is_symlink()` and not `exists()`: it is exactly the pair the write refuses
    one frame down, so this check adds no rule of its own. It moves the existing one earlier.
    A symlinked *home* stays fine, and is a different question — `_check_settings_path` answers
    that one, and `open_within` never applies `O_NOFOLLOW` to the root it is handed.

    **And the file itself, which the write does not refuse.** With `--settings` the root is the
    file's own directory and the walk is one component deep, so `open_within` never opens the
    final name at all and `write_atomically_at` reaches `os.replace` — which *replaces* a
    symlink entry rather than following it or refusing it. The link became a regular file and
    the dotfiles copy kept its old bytes, with exit 0, while the comment beside that write, this
    document's own `--settings` paragraph and the shipped changelog all said a link at the file
    was refused. `contained(parent, settings.name)` is the identical question
    `_check_settings_path` asks of `<home>/.claude/settings.json`, asked of the path this flag
    names, and it is the only reason that sentence is true.

    A directory at the file's own name is refused in the same breath: it passed both checks
    above, and `_write_user_settings` then failed from `_read_document` with `Is a directory` —
    a `Failure`, the findings exit code 1, for a structural precondition — after
    `home.mkdir(parents=True)` and after the machine configuration had been written.
    """
    parent = settings.parent
    if not (parent.is_dir() and not parent.is_symlink()):
        raise Refusal(
            f"{settings} cannot be written: its directory has to exist and be a real directory, "
            f"because {_SYMLINKED_SETTINGS}"
        )
    try:
        contained(parent, settings.name)
    except PathEscape as exc:
        raise Refusal(
            f"{settings} is a symlink to {settings.resolve()}; {_SYMLINKED_SETTINGS}. A dotfiles "
            f"manager is the usual reason — run `stayfixed setup --settings {settings.resolve()}`, "
            f"which writes the file this link leads to, or replace the link with a real file"
        ) from exc
    # After the symlink refusal, so no link can be behind this answer.
    if settings.is_dir():
        raise Refusal(
            f"{settings} is a directory; --settings names the settings file to write, not the "
            f"directory to write it in"
        )


# `git` reads any directory holding `HEAD`, `objects/` and `refs/` as a bare repository of its
# own when its discovery reaches one (`safe.bareRepository` unset means "all"), and those are
# three paths any repository can commit — see `_repository` for what that did to this check.
# With `explicit`, git refuses to answer from inside one and so never reads the committed
# `config` there. git 2.38 is the first to know the key and an older one ignores it silently,
# so no refusal below rests on it alone. `--is-inside-work-tree`, in the same answer, is what
# does: git answers `true` only for a directory it reached through a checkout's `.git`, and
# `false` for one it read as a git directory by its shape, whatever that directory's committed
# `config` or `commondir` says (`core.bare`, `core.worktree` and a `commondir` pointing elsewhere
# were each tried). `--path-format` already needs 2.31.
_EXPLICIT_BARE: tuple[str, ...] = ("-c", "safe.bareRepository=explicit")
_COMMON_AND_CHECKOUT = (
    "rev-parse",
    "--path-format=absolute",
    "--git-common-dir",
    "--is-inside-work-tree",
)

_UNLISTED = (
    "`git` could not list the checkouts of the repository {root} is in, so no overlay root can be "
    "shown to lie outside all of them. The overlay root is the machine's trust anchor, and a "
    "question git did not answer is not taken as a yes; check that `git` runs here and is 2.31 "
    "or later, the first to answer `rev-parse --path-format`"
)


@dataclass(frozen=True)
class _Repository:
    """The repository `--root` is in: its common directory, and every checkout git lists."""

    common: Path
    checkouts: tuple[Path, ...]


def _nearest_directory(path: Path) -> Path:
    """`path`, or its nearest ancestor that is a directory: `--root` and a `create:`
    destination may name one that does not exist."""
    while not path.is_dir() and path != path.parent:
        path = path.parent
    return path


_SILENT_IN_A_CHECKOUT = (
    "`git` gave no answer asked from {start}, which is inside a checkout — {no_answer} — so no "
    "overlay root can be shown to lie outside every checkout of the project. The overlay root is "
    "the machine's trust anchor, and a question git did not answer is not taken as a yes; check "
    "that `git` runs here and answers `git status` within a few seconds, then run this again"
)
_REFUSED_IN_A_CHECKOUT = (
    "`git` refused to describe the repository {start} is in, which is inside a checkout — one "
    "another user owns that `safe.directory` does not admit, or a `.git` it cannot read — so no "
    "overlay root can be shown to lie outside every checkout of the project. The overlay root is "
    "the machine's trust anchor, and a question git did not answer is not taken as a yes; check "
    "that `git status` runs there, then run this again"
)
# git's exit when it will not describe the repository it found: a checkout of dubious ownership,
# an unreadable `.git`, a worktree whose git directory is gone, and, asked with `_EXPLICIT_BARE`,
# a bare-shaped directory. Only the last is an answer, which is why a keyed question is asked
# again without the key before its 128 counts.
_GIT_REFUSED = 128


def _ask(start: Path, *args: str, keyed: bool = False) -> list[str] | None:
    """git's answer to `args` asked from `start`, one line per entry, or `None` when it gave
    none. `gitenv.git_run` decodes losslessly, so a path in bytes that are not UTF-8 is part of
    the answer and compares equal to itself.

    **A git that said nothing is not a git that said "no repository" where a checkout could
    be.** `git_run`'s `-1` — git could not be run or ran past its time limit — read as `None`
    here, and every caller reads `None` as a directory git does not count as a checkout: a git
    that timed out on `rev-parse` let the main checkout of the project be recorded from one of
    its worktrees. Whether `start` could be inside a checkout is read off the disk
    (`gitenv.in_work_tree`), because the question cannot go to the git that just failed to
    answer it. Where it could, the silence refuses; where no `.git` is at or above `start`,
    there is no checkout for git to have named, and it is `None` as before.

    **Nor is a git that refused the repository it found.** Exit 128 inside a checkout is git
    saying there is a repository it will not describe — another user's, under `safe.directory`,
    or one whose `.git` it cannot read — and read as `None` it let the path arm stand alone, as
    `-1` did. It refuses too, except for a `keyed` question, asked with `_EXPLICIT_BARE`, whose
    128 can be git declining a bare-shaped directory: its caller asks again without the key.
    """
    code, out = git_run(start, *args)
    if code == -1 and in_work_tree(start):
        raise Refusal(_SILENT_IN_A_CHECKOUT.format(start=start, no_answer=NO_ANSWER))
    if code == _GIT_REFUSED and not keyed and in_work_tree(start):
        raise Refusal(_REFUSED_IN_A_CHECKOUT.format(start=start))
    # Split where git ended each line: `splitlines()` also broke a path at a `\r` it holds, and
    # recorded `…/wt` among the checkouts for a worktree at `…/wt\rx` (`gitenv.answer_lines`).
    lines = answer_lines(out)
    return lines if code == 0 and lines else None


def _repository(project_root: Path) -> _Repository | None:
    """The repository `project_root` is in, or `None` when `git` gives no answer for it at all.

    **Its checkouts are asked from the project's side.** The first version asked
    `rev-parse --git-common-dir` from inside the *candidate* and compared the answers, which let
    the candidate's own bytes choose the answer: a committed bare-shaped `ov/` reported itself as
    its own common directory, so a clone's `ov/` in a sibling worktree was "another repository"
    and was recorded. `git worktree list` is the repository's own record of its checkouts, which
    a clone cannot commit into.

    **`None` means git gave no answer where no `.git` is at or above `--root`**: it is in no
    repository, or git could not be run or timed out there. Only the path arm stands, and
    neither is something a repository can commit. Every other way of not answering refuses:
    git that could not be run, timed out, or refused the repository it found (`safe.directory`,
    an unreadable `.git`) inside a checkout (`_ask`), an answer that says `--root`
    is not inside a work tree (a root inside a bare-shaped directory has no checkout of its own
    to compare against), an answer git gives only without the key, and a listing that fails or
    is empty.
    """
    start = _nearest_directory(project_root)
    unlisted = _UNLISTED.format(root=project_root)
    answer = _ask(start, *_EXPLICIT_BARE, *_COMMON_AND_CHECKOUT, keyed=True)
    retried = False
    if answer is None:
        # git 2.38 and later refuse an implicit bare repository outright. Asked again without
        # the key only to tell that apart from "no repository at all".
        retried = True
        answer = _ask(start, *_COMMON_AND_CHECKOUT)
        if answer is None:
            return None
    if len(answer) != 2:
        raise Refusal(unlisted)
    if answer[1] != "true":
        raise Refusal(
            f"git does not read {project_root} as inside a checkout: it is inside a bare "
            f"repository, a git directory, or a directory holding `HEAD`, `objects/` and "
            f"`refs/`, which any repository can commit — so it has no checkout of its own for an "
            f"overlay root to be compared against. Run this command from the checkout itself"
        )
    if retried:
        raise Refusal(unlisted)
    listing = _ask(start, *_EXPLICIT_BARE, "worktree", "list", "--porcelain", keyed=True)
    # Prunable entries included: a checkout whose directory is gone costs nothing to refuse.
    checkouts = tuple(
        Path(line[len("worktree ") :]) for line in listing or () if line.startswith("worktree ")
    )
    # git always lists at least the main worktree, so an empty listing is not an answer either.
    if not checkouts:
        raise Refusal(unlisted)
    return _Repository(Path(answer[0]), checkouts)


def _candidate_repository(candidate: Path) -> Path | None:
    """The common directory of the nearest checkout at or above `candidate` that git answers
    for, or `None`.

    **This arm can only add a refusal.** `git worktree list` does not name every checkout: with
    `--separate-git-dir`, and for a submodule, the main checkout is listed by its git directory,
    which does not record where the checkout is — so from a linked worktree the main checkout
    was on no list. Asked from the candidate's side, git finds it through the checkout's `.git`.
    The candidate's bytes can try to make this answer wrong, and whatever they make it say they
    cannot remove a refusal the listing makes. Nor can a git that says nothing: on the walk, as
    everywhere `_ask` is used, that is a refusal inside a checkout and not a step past it.

    **Only an answer from inside a work tree is the candidate's.** On a git that ignores
    `safe.bareRepository`, a bare-shaped `ov/` answers for itself, and its committed `config` or
    `commondir` can make that answer say "not bare" with a common directory anywhere. It cannot
    make git say `ov/` is inside a work tree: that answer comes only through a checkout's `.git`,
    which a repository cannot commit. So the walk goes on past every other answer.

    Walked up rather than asked once, because git refuses to answer from inside a bare-shaped
    directory — which is exactly where a clone puts the candidate — and a git directory's answer
    is not the candidate's. Asked from the nearest directory that exists, because a
    `create:` destination does not yet.
    """
    start = _nearest_directory(candidate)
    while True:
        answer = _ask(start, *_EXPLICIT_BARE, *_COMMON_AND_CHECKOUT, keyed=True)
        if answer is None and in_work_tree(start):
            # A bare-shaped directory, which git declines under the key and describes without
            # it, or a repository git refuses either way, which `_ask` refuses.
            _ask(start, *_COMMON_AND_CHECKOUT)
        if answer is not None and len(answer) == 2 and answer[1] == "true":
            return Path(answer[0])
        if start == start.parent:
            return None
        start = start.parent


def _same(a: Path, b: Path) -> bool:
    """Whether `a` and `b` are one directory, asked of the filesystem where both exist.

    `Path.resolve()` keeps the case it was given, so on a volume that folds case — macOS's
    default — `PROJ.WT/a` and `proj.wt/a` are one directory and two strings. Exact comparison
    stands only where one of them does not exist.
    """
    try:
        return os.path.samefile(a, b)
    except OSError:
        return a == b


def _overlaps(a: Path, b: Path) -> bool:
    """Whether `a` is `b`, lies inside it, or holds it. Both are resolved."""
    if any(_same(part, b) for part in (a, *a.parents)):
        return True
    return any(_same(part, a) for part in b.parents)


def _outside_the_project(candidate: Path, *, project_root: Path) -> None:
    """Refuse an overlay root that sits where the repository an agent works in could reach it.

    A path arm and two `git` arms. The path arm is equality or nesting either way round — a
    candidate *under* the project, and a candidate that *holds* it, which is the shape
    `git worktree add .worktrees/x` produces and which the first draft accepted. The `git` arms
    are the sibling case the paths cannot see: `stayfixed.worktrees/feature` is not under
    `stayfixed/`, so a clone committing its own manifests at its own root passed the path arm
    whenever `--root` was one of its worktrees — and working in a worktree makes `--root` one.
    The first applies the path arm to every checkout `_repository` lists; the second,
    `_candidate_repository`, catches the checkouts that list names by their git directory. See
    each for why it is asked from the side it is.

    **What it does not cover, stated rather than implied.** When `git` gives no answer for the
    project root, the `git` arms are silent and only the path arm stands — `_repository` says
    which answers those are. A common directory whose path is not UTF-8 is an answer like any
    other: `git_run` decodes it losslessly, so two checkouts of one repository still compare
    equal. And what the whole check bounds is a repository *shipping* a tree: committed contents
    reach that repository's own checkouts and nowhere else, so refusing all of them removes the
    case a clone can stage. It is not a claim that no other directory on the machine can hold the
    same bytes — a separate `git clone` of the same remote has its own common directory and
    passes — only that the owner, and not the clone, put it there.
    """
    resolved_candidate = candidate.resolve()
    resolved_project = project_root.resolve()
    if _overlaps(resolved_candidate, resolved_project):
        raise Refusal(
            f"{candidate} is inside {project_root}, holds it, or is it — and {project_root} is "
            f"the project this command was run from. The overlay root is the machine's trust "
            f"anchor and must live outside any repository an agent works in: a repository could "
            f"otherwise ship its own tree and have this command record it"
        )
    repository = _repository(resolved_project)
    if repository is None:
        return
    same_repository = (
        f"{candidate} is inside a checkout of the same repository as {project_root}, the "
        f"project this command was run from, holds one, or is one. The overlay root is the "
        f"machine's trust anchor and must live outside every checkout of a repository an agent "
        f"works in — a worktree is not a different repository, and a clone ships its own tree "
        f"into all of them"
    )
    for checkout in repository.checkouts:
        if _overlaps(resolved_candidate, checkout.resolve()):
            raise Refusal(same_repository)
    found = _candidate_repository(resolved_candidate)
    if found is not None and _same(found.resolve(), repository.common.resolve()):
        raise Refusal(same_repository)


@dataclass(frozen=True)
class _Overlay:
    """What `--overlay` asked for, once everything knowable before the first write is known.

    `create` is `(owner, name)` when this run has to create the repository, and `None` when the
    root already exists and is only being recorded. `root` is where the overlay is or will be:
    for the create branch it is `overlay.api.target_root`'s answer, computed from the arguments
    alone so the destination can be refused before `gh repo create` runs.
    """

    root: Path
    create: tuple[str, str] | None


def _recordable(root: Path) -> None:
    """Refuse an overlay root the machine file cannot hold: it is UTF-8 TOML, and a path the
    disk holds in other bytes — a directory named in latin-1, on Linux — reaches Python with
    surrogate escapes and raised `UnicodeEncodeError` at the last write, after the machine
    file's other tables and the settings file were written. Asked with the tree checks, above
    every write."""
    if not utf_8_name(str(root)):
        raise Refusal(
            f"{root} is not UTF-8 text, so the machine configuration, a UTF-8 file, cannot record "
            f"it as the overlay root; keep the overlay under a path that is"
        )


def _requested_overlay(
    overlay: str | None, *, home: Path, project_root: Path, yes: bool
) -> _Overlay | None:
    """Every refusal `--overlay` can raise that does not need a tree to exist first.

    Called above the first write. The first draft called the equivalent of this from the bottom
    of `setup`, so `--overlay /typo` had already written the machine file, merged the settings
    file and installed two plugins before it refused, and `--overlay create:` had already
    created a private repository on GitHub.

    `home`, never `Path.cwd()`, is what a *created* overlay is created in: this is a machine
    command, run from wherever the owner happened to be sitting, and a created overlay must not
    depend on that. Measured while that was written: `root=Path.cwd()` created a real
    `stayfixed-private/` inside this very checkout the first time a test exercised the branch.

    The overlay area is imported here and in `_apply_overlay`, never at module level: this module
    is behind `setup.api`, which `doctor` imports, and the core loads the private layer only when
    `--overlay` asks for it (CONTRIBUTING.md, "Areas").
    """
    if overlay is None:
        # Nothing was asked for, so nothing is touched. The creation gate is that `--overlay` is
        # the only way to reach the overlay at all, and `--yes` does not imply one: a default here
        # would turn an omitted flag into a repository created on somebody's account.
        return None
    from stayfixed.overlay.api import require_overlay, target_root

    if overlay.startswith("create:"):
        if not yes:
            raise Refusal(
                "creating a private overlay runs `gh repo create ... --private --template ...` "
                "on GitHub, which is irreversible and outward-facing, so it needs explicit "
                "confirmation; pass --yes to confirm it, or use --overlay <path> to record one "
                "that already exists"
            )
        spec = overlay[len("create:") :]
        owner, sep, name = spec.partition("/")
        if not sep or not owner or not name:
            raise Refusal(
                f"--overlay create:<owner>/<name> needs both a GitHub owner and a repository "
                f"name; got {overlay!r}"
            )
        # Refuses a name that is not one path segment, and answers where the tree would land —
        # both without creating anything, which is the whole point of asking here.
        destination, account = target_root(home, owner, name)
        _outside_the_project(destination, project_root=project_root)
        _recordable(destination)
        return _Overlay(root=destination, create=(account, name))
    candidate = Path(overlay).expanduser().resolve()
    _recordable(candidate)
    require_overlay(candidate, because=_RECORDING)
    _outside_the_project(candidate, project_root=project_root)
    return _Overlay(root=candidate, create=None)


def _apply_overlay(planned: _Overlay, *, project_root: Path, runner: Runner) -> tuple[Path, str]:
    """Create the overlay if this run has to, record what there is, and say what happened.

    Everything here that can refuse is a **floor** under `_requested_overlay` rather than a
    second copy of it, in the sense the `attach` area settled the same shape: the checks above
    the first write are what a person acts on, and these are what catches a tree that changed in
    between — or, for the create branch, one that did not exist to be checked at all. What this
    function returns is written into the machine file, and every later `attach` on this machine
    derives `permitted_roots` from that record, so the last thing to touch the tree before it
    becomes the trust anchor asks again.

    The created branch's refusal says the repository exists. It has to: the owner now has a
    private repository on GitHub that this run made, and the report is discarded on a refusal,
    so nothing else would ever tell them.
    """
    from stayfixed.overlay.api import create, init_instance, overlay_fault, require_overlay

    if planned.create is None:
        require_overlay(planned.root, because=_RECORDING)
        _outside_the_project(planned.root, project_root=project_root)
        return planned.root, f"recorded the existing overlay at {planned.root}"
    owner, name = planned.create
    created = create(owner, name, source="template", root=planned.root.parent, runner=runner)
    # Before `init_instance`, which now asks the same question and refuses with an answer that
    # does not say the repository exists; this one has to, and so it goes first.
    fault = overlay_fault(created.root)
    if fault is not None:
        raise Refusal(
            f"{fault}. {owner}/{name} was created and cloned to {created.root}, but {_CREATED}"
        )
    initialised = init_instance(created.root, owner, runner=runner)
    _outside_the_project(created.root, project_root=project_root)
    if created.template is None:
        # `create` found a populated destination and generated nothing (no `gh` call at all),
        # which is what re-running `setup --overlay create:` does after the first run, so there is
        # no template to name. `init` still ran on it, and an overlay named by an earlier release
        # has its manifests completed or its old memory README removed, so the note says what
        # `init` changed rather than that the overlay was left alone.
        changed = initialised.changed
        return created.root, (
            f"found the overlay already at {created.root}, so nothing was generated; "
            + (
                f"`overlay init` changed {', '.join(changed)}"
                if changed
                # Not "nothing": `init` also runs `pre-commit install`, which may write the
                # overlay's untracked git hook on this run.
                else "`overlay init` changed none of the overlay's tracked files"
            )
        )
    return created.root, f"created the overlay at {created.root}, generated from {created.template}"


def setup(
    preset: str,
    *,
    home: Path,
    machine: Path,
    runner: Runner,
    yes: bool,
    overlay: str | None,
    project_root: Path,
    settings: Path | None = None,
) -> SetupReport:
    """Configure this machine from `preset`.

    `project_root` is the repository this invocation was run from (the CLI's `--root`, default
    `.`), and it exists for exactly one reason: `_outside_the_project` refuses an `--overlay`
    that any checkout of it could reach. `yes` confirms creating an overlay on GitHub and
    nothing else: there is no other prompt here for it to answer (see the module docstring).

    **Everything structural is asked before the first write**, and the order below is
    load-bearing rather than tidy: `--overlay` is parsed, probed and contained, and the settings
    path is checked — **both spellings of it**, the `<home>/.claude` walk and the directory
    `--settings` names — while nothing is on disk and no repository exists on anyone's GitHub
    account. What is left after that is the work, and the one refusal that follows a write is
    the post-condition on a tree this run created.
    """
    planned_overlay = _requested_overlay(overlay, home=home, project_root=project_root, yes=yes)
    # `--settings` names the file, so the `<home>/.claude` walk `_check_settings_path` is about
    # is not the walk that will run: asking it anyway would refuse the one layout the flag exists
    # for. So the question is asked of whichever root the write will actually use. Both arms and
    # not one: with only the first, `--settings` reached its refusal from `_write_user_settings`,
    # after `home.mkdir` and after the machine file had been written, and a typo in the directory
    # component left both of those behind on the way to exit 2.
    if settings is None:
        _check_settings_path(home)
    else:
        _check_settings_parent(settings)

    # `home` is the root every write in this function lands under **except the one `--settings`
    # redirects** — the settings file through `fsops.write_within` below, whose root is the named
    # file's own directory when the flag is given and `home` when it is not, and a created overlay
    # through `overlay.create` further down. `home` is not a root this process was handed already
    # existing, the way a project root or the overlay itself is. Created directly for the same
    # reason `setup.machine`'s module docstring gives for `fsops.write_atomically` on the
    # machine file: there is nothing for a contained walk to be relative to until this
    # directory exists.
    # `load_preset` first: a mistyped `--preset` is a refusal, and it used to come one line
    # after the home tree had been created for it.
    data = load_preset(preset, key="--preset")
    home.mkdir(parents=True, exist_ok=True)
    personal = _new_personal_values(data, machine)
    machine_table = {"version": __version__, "installed": datetime.date.today().isoformat()}
    write_machine(machine, personal=personal, overlay_root=None, machine=machine_table)

    deny_rules = [r for r in data.get("deny", {}).get("global", []) if isinstance(r, str)]
    # **The `pluginConfigs` mirror is recomputed from the machine file, not from this run's own
    # new keys.** `personal` above is empty on every run after the first, so the mirror was
    # write-once: an owner who edited `reply_language` in the machine file — the documented way,
    # `README.md`'s own "Written by: you, or `stayfixed setup`" — kept `""` in
    # `~/.claude/settings.json` for ever. The other answer the review offered was to stop
    # writing the mirror at all; it is rejected because `pluginConfigs` is where Claude Code
    # itself reads a plugin's `userConfig` answers, and this plugin's own manifest declares
    # them, so dropping it would leave the harness reading nothing. The cost of this direction
    # is stated where a reader will meet it: a value set in Claude Code's plugin-config UI is
    # overwritten by the machine file on the next `setup`, because one file has to win and the
    # machine file is the one every stayfixed reader reads.
    deny_written = _write_user_settings(home, deny_rules, read_personal(machine), settings=settings)

    installed, install_notes = _install_plugins(data, _agents(data), home=home, runner=runner)
    notes = list(install_notes)

    cli_on_path = shutil.which("stayfixed") is not None
    if not cli_on_path:
        notes.append(
            f"`stayfixed` is not on PATH; install it with "
            f"`{INSTALL_COMMAND.format(version=__version__)}`"
        )

    overlay_root: Path | None = None
    if planned_overlay is not None:
        overlay_root, note = _apply_overlay(
            planned_overlay, project_root=project_root, runner=runner
        )
        notes.append(note)
        write_machine(machine, personal={}, overlay_root=overlay_root, machine={})

    return SetupReport(
        machine_written=True,
        plugins_installed=installed,
        deny_written=deny_written,
        cli_on_path=cli_on_path,
        overlay=overlay_root,
        notes=tuple(notes),
    )
