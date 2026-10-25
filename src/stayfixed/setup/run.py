"""`setup(preset, ...)`: machine setup, once — after stayfixed is installed, before any attach.

Five things, each reported and each independently skippable, in this order: write the machine
file (the personal defaults the preset names, for whichever of them nothing has recorded yet);
merge the preset's deny rules and the personal values into the machine-scope settings file;
register each preset plugin's marketplace and install from it, per configured harness; report
whether `stayfixed` itself resolves on `PATH`; and, only when the caller named an answer, create,
render or record the private overlay.

**A preset default never overwrites a value already recorded.** The first draft of this module
rebuilt `[personal]` from the preset's own defaults on every run, which meant a second
`setup --preset recommended` reset a personal value back to the preset's after the owner set it by
hand — exactly the value `setup.machine`'s own docstring promises survives a rewrite that "only
set one of them". `_new_personal_values` computes only the keys the machine file does not already
carry, and that is what both `write_machine` and the settings file's `pluginConfigs` receive — an
empty dict on every run after the first, once every key has a recorded value.

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

**The overlay is validated before anything is written**, in `_requested_overlay`, asked in
`_before_the_first_write` — above the machine file, the settings merge and the plugin installs,
and for `create:` above `gh repo create` itself:

* **an existing path must be an overlay**, which is `overlay.api.require_overlay`: a tree whose
  identity record names layout 1. `identity`'s own docstring is honest that a repository can still
  commit such a record: it stops the accidents, a mistyped path or somebody else's tree.
* **a `create:` destination must be one `gh` can clone into**: not there, or the overlay an
  earlier run made. Its place is `home/<name>`, knowable from the arguments
  (`overlay.api.target_root`), so a file there, or a directory holding anything but an overlay, is
  refused before `gh repo create` makes a repository on the owner's account that nothing would
  then record. Naming `create:` is the request, and no flag stands in front of it: a flag a
  model-written command line types as easily as the command consents to nothing.

Where the overlay lives is the owner's choice, and `setup` refuses no place for it: `doctor`'s
`overlay-requires` row warns when another repository's work tree holds it.

**The settings file is written through the home's own symlinks**, so a home managed by stow,
chezmoi or a synced directory gets the file its links lead to: nothing a repository writes is on
that path.
"""

from __future__ import annotations

import datetime
import os
import shutil
import stat
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from stayfixed import REPOSITORY_URL, __version__, fsops
from stayfixed.errors import Failure, Refusal
from stayfixed.fsops import utf_8_name
from stayfixed.harnesses import BYTE_ORDER_MARK, lenient_settings
from stayfixed.jsonobject import json_object, json_text
from stayfixed.presets import defaults_of, load_preset
from stayfixed.printed import answered, quoted
from stayfixed.runner import Runner
from stayfixed.setup.machine import SETUP_SANDBOXED, USER_SETTINGS, read_personal, write_machine
from stayfixed.trust.api import sandbox_refused

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
    "--overlay must name a real overlay's root, or a path that names nothing, where one is "
    "rendered, because this path becomes the machine's trust anchor: every `stayfixed attach` on "
    "this machine reads rules and notes out of it"
)
_CREATED = (
    "the repository was created and cloned, and nothing was recorded in the machine "
    "configuration; look at what arrived, then record it with `stayfixed setup --overlay <path>`"
)
# What `create:` says of a destination it cannot clone into, `{destination}` through
# `printed.quoted`: asked before `gh` is, so nothing exists on GitHub when either is said.
DESTINATION_NOT_A_DIRECTORY = (
    "{destination} is there and is not a directory, so `create:` has nowhere to clone the overlay "
    "and nothing was created on GitHub; move it, or name another repository"
)
DESTINATION_NOT_AN_OVERLAY = (
    "{destination} is a directory that is not an overlay, so `create:` would clone the new "
    "repository over what is there, and nothing was created on GitHub; move it, or name another "
    "repository — and if an earlier run's clone was cut short there, delete it and run again"
)
# What `--overlay <path>` says of a path that is not there and cannot be rendered, `{path}` and
# `{parent}` through `printed.quoted`.
NO_PLACE_TO_RENDER = (
    "{path} is not there, so --overlay would render an overlay at it, and {parent} is not a "
    "directory this user can create it in; create that directory, or name an existing overlay"
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
    return dict(defaults_of(preset).get("personal", {}))


def _new_personal_values(preset: dict[str, Any], machine: Path) -> dict[str, Any]:
    """The preset's personal defaults, minus every key the machine file already carries.

    A key present in the file — set by an earlier `setup`, or by the owner's own hand — is the
    owner's, and a preset default may not win over it on a later run. An absent key gets the
    preset's default, which is what makes a *first* run write all three.
    """
    existing = read_personal(machine)
    return {k: v for k, v in _personal_defaults(preset).items() if k not in existing}


def _agents(preset: dict[str, Any]) -> tuple[str, ...]:
    agents = defaults_of(preset).get("stayfixed", {}).get("agents", [])
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
    """The user settings file at `path` as one JSON object, and its text as it is on disk.

    Read as Claude Code reads it (`harnesses.lenient_settings`), past a leading byte-order mark,
    so an owner's file the harness reads is merged into rather than refused."""
    with fsops.reading(path, Failure):
        try:
            text = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return {}, ""
    if not lenient_settings(text).strip():
        return {}, text
    # The file is the owner's and this run rewrites it, so valid JSON past the parser's reach is
    # refused as a `Failure` naming it rather than read, and rather than ending setup in an
    # internal error.
    return json_object(lenient_settings(text), str(path), error=Failure), text


def _write_user_settings(
    home: Path,
    deny_rules: Sequence[str],
    personal: Mapping[str, Any],
    *,
    retired: Sequence[str] = (),
) -> bool:
    """Merge the preset's deny rules and the personal values into `<home>/<USER_SETTINGS>`.

    Merge, never replace: the owner's own file predates stayfixed on most machines, and nothing
    this run did not add may be recorded as if it had. Deny only — this never reads or writes
    `permissions.allow` — and `pluginConfigs` gets the same treatment, key by key inside its own
    `options`, so a value this run did not set survives a second one same as `write_machine`'s.

    `retired` is the one removal: rules an earlier preset wrote under the same table and this one
    took back (the preset's `[deny] retired`), each removed where it stands verbatim. A rule the
    owner wrote is kept unless it is one of those exact strings, which is the rule an earlier
    `setup` would have written in any case. A rule a preset both retires and lists is removed and
    then added back at the end, so a contradictory preset still leaves it denied.
    """
    path = home / USER_SETTINGS
    document, text = _read_document(path)

    permissions = document.get("permissions")
    permissions = dict(permissions) if isinstance(permissions, dict) else {}
    raw_deny = permissions.get("deny")
    existing_deny = (
        [r for r in raw_deny if isinstance(r, str)] if isinstance(raw_deny, list) else []
    )
    existing_deny = [r for r in existing_deny if r not in retired]
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

    # Written back through `json_text`, which answers a document the parser read and the
    # indenting encoder cannot follow (Python 3.12) as the reader answers one nested too deep.
    # A byte-order mark the file opened with is kept, so a run that changes nothing writes nothing.
    mark = BYTE_ORDER_MARK if text.startswith(BYTE_ORDER_MARK) else ""
    new_text = mark + json_text(document, str(path), error=Failure, indent=2, sort_keys=True) + "\n"
    if new_text == text:
        return False
    try:
        fsops.write_atomically(fsops.resolved(path), new_text)
    except OSError as exc:
        if sandbox_refused(exc):
            raise Refusal(SETUP_SANDBOXED) from exc
        raise Refusal(f"{path} cannot be written ({fsops.said(exc)})") from exc
    return True


def _not_writable(directory: Path, said: str) -> Refusal:
    """The refusal of `directory`, which `os.access` says this user may not write: `SETUP_SANDBOXED`
    where its mode lets its owner, this user, write and search it, and `said` otherwise.

    An agent's sandbox answers `os.access` as it answers the write (measured with `sandbox-exec`
    on macOS 27 on 2026-10-16: `os.access(W_OK)` was false for a directory the profile denied and
    whose mode allowed the write), so a directory its mode does not refuse is refused by something
    else -- the sandbox, or a read-only mount, whose answer is the same for a person: run it from
    their own terminal. A mode that refuses the user is not the sandbox, and keeps `said`.
    """
    try:
        found = os.stat(directory)
    except OSError:
        return Refusal(said)
    writable = stat.S_IWUSR | stat.S_IXUSR
    owned = found.st_uid == os.getuid() and found.st_mode & writable == writable
    return Refusal(SETUP_SANDBOXED if owned else said)


def _check_home_usable(home: Path, *, created: Path | None = None) -> None:
    """Refuse a `--home` this command cannot write into — above the first write.

    `home.mkdir(parents=True)` under a read-only parent raised `PermissionError` into the frame,
    `stayfixed: internal error`, exit 2; and a home that was there with mode 555 had the machine
    file written into the machine configuration before `_write_user_settings` refused. The
    question is `fsops.creatable`'s, and it is asked of each place a write under `home` lands —
    never of `home` for its own sake: a home with a writable `.claude` already in it takes no
    write at all.

    - The settings file, `<home>/.claude/settings.json` where its links lead: `creatable` walks
      to its directory when that is there, and to the nearest directory above it while it is not
      — which is also where the `mkdir` starts.
    - `created`, the `<home>/<name>` a `create:` overlay is cloned into, while it is not there yet.
      Asked here because the clone is what would find out otherwise, after `gh repo create` has
      made a repository on somebody's account. What is there already is `_requested_overlay`'s.

    The refusal names the directory `creatable` stopped at. `os.access` answers for the real uid
    and says yes to root whatever the mode, so the `mkdir` in `setup` keeps a refusal of its own
    under this one. A directory above `home` that cannot be searched leaves the question open,
    and the `fsops` predicates raise for that rather than guess: the floor of
    `_before_the_first_write` names the path they were asked about, as it does for every step.
    """
    landing = [fsops.resolved(home / USER_SETTINGS)]
    if created is not None and not fsops.exists(created):
        landing.append(created)
    for path in landing:
        directory = fsops.creation_directory(path)
        # A regular file where a directory has to be (`home` itself, or one above it) is the
        # `mkdir`'s to name, as "File exists" or "Not a directory": "is not writable" said of it
        # would be a cause it does not have.
        if fsops.is_dir(directory) and not fsops.creatable(path):
            raise _not_writable(
                directory, f"--home {home} cannot be used: {directory} is not writable"
            )
    # The settings write opens the file's directory `O_RDONLY`, and a directory at mode 300 takes
    # a new name and refuses that open. `os.access` says yes to root, for whom the write's own
    # refusal stays the floor.
    directory = landing[0].parent
    if fsops.is_dir(directory) and not os.access(directory, os.R_OK):
        raise Refusal(
            f"--home {home} cannot be used: {directory} is not readable, and the settings write "
            "opens it to read"
        )


@dataclass(frozen=True)
class _Overlay:
    """What `--overlay` asked for, once everything knowable before the first write is known.

    `create` is `(owner, name)` when this run has to create the repository, and `None` when the
    root already exists and is only being recorded, or is not there and is rendered (`render`).
    `root` is where the overlay is or will be: for the create branch it is
    `overlay.api.target_root`'s answer, computed from the arguments alone so the destination can be
    refused before `gh repo create` runs.
    """

    root: Path
    create: tuple[str, str] | None
    # `--overlay <path>` naming nothing: the shipped template is rendered there.
    render: bool = False
    # For `create:`, the destination as `overlay.api.target_root` names it, `<home>/<name>`,
    # which is where `generate` clones; `root` is that path resolved, which is what is judged and
    # recorded, as `--overlay <path>` records its path resolved.
    destination: Path | None = None


def _recordable(root: Path) -> None:
    """Refuse an overlay root the machine file cannot hold: it is UTF-8 TOML, and a path the
    disk holds in other bytes — a directory named in latin-1, on Linux — reaches Python with
    surrogate escapes and raised `UnicodeEncodeError` at the last write, after the machine
    file's other tables and the settings file were written. Asked with the tree checks, above
    every write."""
    if not utf_8_name(str(root)):
        raise Refusal(
            f"{quoted(str(root))} is not UTF-8 text, so the machine configuration, a UTF-8 file, "
            f"cannot record it as the overlay root; keep the overlay under a path that is"
        )


def _requested_overlay(overlay: str | None, *, home: Path) -> _Overlay | None:
    """What `--overlay` names, and every refusal its arguments and its tree's identity can raise.

    The first step of `_before_the_first_write`. The first draft called the equivalent of this from
    the bottom
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
        # Nothing was asked for, so nothing is touched: `--overlay` is the only way to reach the
        # overlay at all, and a default here would turn an omitted flag into a repository created
        # on somebody's account.
        return None
    from stayfixed.overlay.api import overlay_fault, require_overlay, target_root

    if overlay.startswith("create:"):
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
        # What is there already, decided before any `gh` call: nothing, which this run makes; the
        # overlay an earlier run made, which `generate` leaves alone; or anything else — a file, a
        # link to nowhere, a directory holding something that is not an overlay — which the clone
        # would meet only after `gh repo create` had made a repository nothing then records.
        if fsops.exists(destination) or fsops.is_symlink(destination):
            shown = quoted(str(destination))
            if not fsops.is_dir(destination):
                raise Refusal(DESTINATION_NOT_A_DIRECTORY.format(destination=shown))
            if not os.access(destination, os.X_OK):
                raise Refusal(f"--home {home} cannot be used: {destination} cannot be searched")
            if overlay_fault(destination) is not None:
                raise Refusal(DESTINATION_NOT_AN_OVERLAY.format(destination=shown))
        root = fsops.resolved(destination)
        _recordable(root)
        return _Overlay(root=root, create=(account, name), destination=destination)
    candidate = fsops.resolved(Path(overlay).expanduser())
    _recordable(candidate)
    # Through `fsops`, which raises for a path it cannot ask about (a directory above it nobody may
    # search), so that is the floor's refusal and never read as "not there".
    if not fsops.exists(candidate) and not fsops.is_symlink(candidate):
        # Not there: the shipped template is rendered at it, so the directory above it has to be
        # one this user can make it in, asked here rather than met by the render after the
        # machine file is written.
        parent = candidate.parent
        if not fsops.is_dir(parent) or not fsops.creatable(candidate):
            raise Refusal(
                NO_PLACE_TO_RENDER.format(path=quoted(str(candidate)), parent=quoted(str(parent)))
            )
        return _Overlay(root=candidate, create=None, render=True)
    require_overlay(candidate, because=_RECORDING)
    return _Overlay(root=candidate, create=None)


def _apply_overlay(planned: _Overlay, *, runner: Runner) -> tuple[Path, str]:
    """Create the overlay if this run has to, record what there is, and say what happened.

    Everything here that can refuse is a **floor** under `_before_the_first_write` rather than a
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
    from stayfixed.overlay.api import finish, generate, overlay_fault, render, require_overlay

    if planned.render:
        try:
            rendered = render(planned.root, runner=runner)
        except OSError as exc:
            # The floor under `_requested_overlay`'s question: a directory that changed in
            # between, or root, for whom `os.access` says yes whatever the mode.
            raise Refusal(
                f"{quoted(str(planned.root))} could not be rendered ({fsops.said(exc)}), and "
                "nothing was recorded in the machine configuration"
            ) from exc
        root = fsops.resolved(rendered.root)
        notes = (*rendered.notes, *finish(root, runner=runner))
        return root, f"rendered the overlay at {quoted(str(root))}: {'; '.join(notes)}"
    if planned.create is None:
        require_overlay(planned.root, because=_RECORDING)
        return planned.root, f"recorded the existing overlay at {quoted(str(planned.root))}"
    owner, name = planned.create
    destination = planned.destination if planned.destination is not None else planned.root
    created = generate(owner, name, root=destination.parent, runner=runner)
    # The one value judged, finished and recorded, as the phase planned it: what the clone's
    # path resolves to now, so a link that arrived there since is followed and not recorded.
    root = fsops.resolved(created.root)
    # Before `finish`, which writes in the tree; this refusal has to say the repository exists.
    fault = overlay_fault(root)
    if fault is not None:
        raise Refusal(
            f"{fault}. {owner}/{name} was created and cloned to {quoted(str(root))}, but {_CREATED}"
        )
    finished = "; ".join(finish(root, runner=runner, owner=owner, name=name))
    if created.template is None:
        # `generate` found a populated destination and generated nothing (no `gh` call at all),
        # which is what re-running `setup --overlay create:` does after the first run, so there is
        # no template to name.
        return root, (
            f"found the overlay already at {quoted(str(root))}, so nothing was generated; "
            f"{finished}"
        )
    return root, (
        f"created the overlay at {quoted(str(root))}, generated from {created.template}; {finished}"
    )


def _before_the_first_write(
    preset: str, *, home: Path, overlay: str | None
) -> tuple[dict[str, Any], _Overlay | None]:
    """Every question `setup` asks before its first write, in one order, under one floor.

    Nothing is written, and no program is run, until every step has answered; each refuses with
    its own words, and the first refusal ends the run. The steps, in order:

    1. **What `--overlay` names** (`_requested_overlay`): a spec without both halves, a name that
       is not one path segment, a root the machine file cannot hold; for an existing path, a tree
       that is not an overlay; for one that names nothing, a directory above it this user cannot
       create it in; and for `create:`, a destination `gh` could not clone into.
    2. **The preset** (`load_preset`): a mistyped `--preset`. It used to come one line after the
       home tree had been created for it.
    3. **Where a write under `--home` lands** (`_check_home_usable`): the settings file's
       directory, the `mkdir` of a home not there yet, and a `create:` destination not there yet.

    **The floor.** `fsops`' predicates raise rather than guess when a path cannot be asked
    about, and a step that does not word that itself let the `OSError` reach `cli.run` as
    `stayfixed: internal error`: a `create:` destination under a home nobody may search, or an
    `--overlay` directory below one. Whatever a step raises that way is a refusal here, naming
    the path that was being asked about — the `OSError`'s own file name, the path the predicate
    was handed — and the fault in `fsops.said`'s words. A step whose own words name the cause
    better keeps them.
    """
    try:
        planned = _requested_overlay(overlay, home=home)
        # Where this run clones a `create:` overlay, or `None` when it creates none.
        created = planned.root if planned is not None and planned.create is not None else None
        data = load_preset(preset, key="--preset")
        _check_home_usable(home, created=created)
    except OSError as exc:
        asked = (
            quoted(str(exc.filename)) if exc.filename is not None else "a path this run was given"
        )
        raise Refusal(
            f"{asked} cannot be checked ({fsops.said(exc)}), so nothing was written"
        ) from exc
    return data, planned


def setup(
    preset: str,
    *,
    home: Path,
    machine: Path,
    runner: Runner,
    overlay: str | None,
) -> SetupReport:
    """Configure this machine from `preset`.

    **Everything structural is asked before the first write**, in `_before_the_first_write`:
    `--overlay` is parsed and probed, the preset is loaded and the places a write under `--home`
    lands are asked, while nothing is on disk and no repository exists on anyone's GitHub
    account. What is left after that is the
    work, and the one refusal that follows a write is the post-condition on a tree this run
    created.
    """
    data, planned_overlay = _before_the_first_write(preset, home=home, overlay=overlay)

    # `home` is the root every write in this function lands under, the settings file and a
    # created overlay included. `home` is not a root this process was handed already
    # existing, the way a project root or the overlay itself is. Created directly for the same
    # reason `setup.machine`'s module docstring gives for `fsops.write_atomically` on the
    # machine file: there is nothing for a contained walk to be relative to until this
    # directory exists.
    try:
        home.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        # The floor under `_check_home_usable`: root, for whom `os.access` says yes whatever the
        # mode, and a directory that changed between that question and this call.
        raise Refusal(f"--home {home} could not be created ({fsops.said(exc)})") from exc
    personal = _new_personal_values(data, machine)
    machine_table = {"version": __version__, "installed": datetime.date.today().isoformat()}
    write_machine(machine, personal=personal, overlay_root=None, machine=machine_table)

    deny_rules = [r for r in data.get("deny", {}).get("global", []) if isinstance(r, str)]
    retired = [r for r in data.get("deny", {}).get("retired", []) if isinstance(r, str)]
    # **The `pluginConfigs` mirror is recomputed from the machine file, not from this run's own
    # new keys.** `personal` above is empty on every run after the first, so the mirror was
    # write-once: an owner who edited a personal value in the machine file — the documented way,
    # `README.md`'s own "Written by: you, or `stayfixed setup`" — kept the preset's in
    # `~/.claude/settings.json` for ever. The other answer the review offered was to stop
    # writing the mirror at all; it is rejected because `pluginConfigs` is where Claude Code
    # itself reads a plugin's `userConfig` answers, and this plugin's own manifest declares
    # them, so dropping it would leave the harness reading nothing. The cost of this direction
    # is stated where a reader will meet it: a value set in Claude Code's plugin-config UI is
    # overwritten by the machine file on the next `setup`, because one file has to win and the
    # machine file is the one every stayfixed reader reads.
    deny_written = _write_user_settings(home, deny_rules, read_personal(machine), retired=retired)

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
        overlay_root, note = _apply_overlay(planned_overlay, runner=runner)
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
