"""`setup(preset, ...)`: machine setup, once — after stayfixed is installed, before any attach.

Five things, each reported and each independently skippable, in this order: write the machine
file (the personal defaults the preset names, for whichever of them nothing has recorded yet);
merge the preset's deny rules and the personal values into the machine-scope settings file;
register each preset plugin's marketplace and install from it, per configured harness; report
whether `stayfixed` itself resolves on `PATH`; and, only when the caller named an answer, create
or record the private overlay.

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

**The overlay root is validated before anything is written, and the create branch is gated on
`--yes`.** `--yes` on `--overlay <path>` would be theatre in a harness where the command line
is written by a model, so it is not added there. What bounds the exposure instead is
`_requested_overlay` and `_outside_the_project`, asked in `_before_the_first_write` — above the
machine file, the settings merge and the plugin installs, and for `create:` above
`gh repo create` itself. Two controls:

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
  removes the tree a clone can stage. Nor may it lie inside a checkout of any other repository,
  its own nested checkout included. With no `.git` at or above `--root` there are no other
  checkouts to list, and the only candidates not compared with `--root` itself are a `create:`
  destination that is not there yet, which this run makes, and one that is the overlay root the
  machine file already records (`_exemption`); any other overlay already on disk inside, around
  or equal to a `--root` in no repository is refused, because an archive or another version
  control system's checkout can hold one (`_outside_the_project` names what is left uncompared).
  `_outside_the_project` says how `git` is asked and from which side, and why. It is not a claim
  that the same bytes cannot be somewhere else on the machine — a separate clone of the same
  remote passes — only that the owner put them there. Where a `.git` is, a `git` that gives no
  answer, exits non-zero, is ended by a signal or cannot list the checkouts is a refusal and not
  a pass (`_ask`).

For `create:`, the destination is `home/<name>` and is knowable from the arguments
(`overlay.api.target_root`), so it is checked before the call rather than after it: the first
draft ran `gh repo create`, cloned, renamed both manifests and installed the secret scan, and
*then* refused — leaving a private repository on somebody's GitHub account that nothing in the
report mentioned. `--yes` gets the one control it can really carry: `setup` refuses
`--overlay create:<owner>/<name>` without it, because `gh repo create` runs only after explicit
confirmation, and creating a repository on GitHub is the one irreversible, outward-facing act
this command performs.

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
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from stayfixed import REPOSITORY_URL, __version__, fsops
from stayfixed.config.overlay import overlay_root
from stayfixed.errors import Failure, Refusal
from stayfixed.fsops import utf_8_name
from stayfixed.gitenv import NO_ANSWER, answer_lines, git_run, in_work_tree
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
    "--overlay must name a real overlay's root — the tree `stayfixed overlay create` renders "
    "and `stayfixed overlay init` names after you — because this path becomes the machine's "
    "trust anchor: every `stayfixed attach` on this machine reads rules and notes out of it"
)
_CREATED = (
    "the repository was created and cloned, and nothing was recorded in the machine "
    "configuration; look at what arrived, then record it with `stayfixed setup --overlay <path>`"
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
      made a repository on somebody's account. While it is there, whether it can be searched:
      `overlay.create` looks inside it for an overlay before anything else, and a destination
      nobody may search raised `PermissionError` there as `internal error`, after the machine
      file and the plugin installs.

    The refusal names the directory `creatable` stopped at. `os.access` answers for the real uid
    and says yes to root whatever the mode, so the `mkdir` in `setup` keeps a refusal of its own
    under this one. A directory above `home` that cannot be searched leaves the question open,
    and the `fsops` predicates raise for that rather than guess: the floor of
    `_before_the_first_write` names the path they were asked about, as it does for every step.
    """
    landing = [fsops.resolved(home / USER_SETTINGS)]
    if created is not None and not fsops.exists(created):
        landing.append(created)
    elif created is not None and fsops.is_dir(created) and not os.access(created, os.X_OK):
        raise Refusal(f"--home {home} cannot be used: {created} cannot be searched")
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
    while not fsops.is_dir(path) and path != path.parent:
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


def _silence(code: int) -> str:
    """How a `git` that gave no answer gave none, from `git_run`'s exit code: in words for
    `_SILENT_IN_A_CHECKOUT`, which a person reads to know where to look."""
    if code == -1:
        return NO_ANSWER
    if code < 0:
        # `subprocess` reports a process a signal ended as the signal's negative.
        return f"git was ended by signal {-code}"
    if code == 0:
        return "git exited 0 and printed nothing"
    return f"git exited {code}"


def _ask(start: Path, *args: str, keyed: bool = False) -> list[str] | None:
    """git's answer to `args` asked from `start`, one line per entry; `None` where no `.git` is
    at or above `start`, which is "no repository"; or a refusal. `gitenv.git_run` decodes
    losslessly, so a path in bytes that are not UTF-8 is part of the answer and compares equal
    to itself.

    **Three answers, and the third fails closed.** Whether `start` could be inside a checkout is
    read off the disk (`gitenv.in_work_tree`), because the question cannot go to the git that
    just failed to answer it.

    - Lines, when git exits 0 and prints some.
    - `None`, for anything else where no `.git` is at or above `start`: git finds a work tree
      only through a `.git`, and `gitenv` scrubs `GIT_DIR`, so there is no checkout for git to
      have named, whatever it said — its own "not a git repository", or nothing at all.
    - A refusal, for anything else where a `.git` is: any exit but 0, a signal, `git_run`'s
      `-1` (git could not be run or ran past its time limit), and an exit 0 with nothing
      printed. Each of them used to read as `None`, and every caller reads `None` as a directory
      git does not count as a checkout: a git that timed out on `rev-parse` let the main checkout
      of the project be recorded from one of its worktrees, and a git wrapper that exits 1 — asdf
      or mise with no version chosen — or a git the kernel killed let a clone's own `ov/` be
      recorded from inside it.

    Exit 128 inside a checkout is git saying there is a repository it will not describe —
    another user's, under `safe.directory`, or one whose `.git` it cannot read — and it refuses
    in words of its own, except for a `keyed` question, asked with `_EXPLICIT_BARE`, whose 128
    can be git declining a bare-shaped directory: that is `None`, and its caller asks again
    without the key.
    """
    code, out = git_run(start, *args)
    # Split where git ended each line: `splitlines()` also broke a path at a `\r` it holds, and
    # recorded `…/wt` among the checkouts for a worktree at `…/wt\rx` (`gitenv.answer_lines`).
    lines = answer_lines(out)
    if code == 0 and lines:
        return lines
    if not in_work_tree(start):
        return None
    if code == _GIT_REFUSED and keyed:
        return None
    if code == _GIT_REFUSED:
        raise Refusal(_REFUSED_IN_A_CHECKOUT.format(start=quoted(str(start))))
    raise Refusal(_SILENT_IN_A_CHECKOUT.format(start=quoted(str(start)), no_answer=_silence(code)))


_MISSHAPEN = (
    "`git` answered a question asked from {start} in a shape it does not give — not a path and "
    "`true` or `false` — so no overlay root can be shown to lie outside every checkout of the "
    "project. The overlay root is the machine's trust anchor, and an answer that cannot be read "
    "is not taken as a yes; check that the `git` on `PATH` is git itself, printing nothing of its "
    "own, and is 2.31 or later, the first to answer `rev-parse --path-format`"
)


def _well_shaped(lines: list[str]) -> bool:
    """Whether `lines` is the answer `_COMMON_AND_CHECKOUT` asks for: an absolute path, then
    `true` or `false`. git 2.30 and older echo the `--path-format=absolute` they do not know as a
    line of its own, and a wrapper can print a banner on standard output before git's answer."""
    return len(lines) == 2 and Path(lines[0]).is_absolute() and lines[1] in ("true", "false")


def _shaped(start: Path, lines: list[str] | None) -> list[str] | None:
    """`lines`, git's answer to `_COMMON_AND_CHECKOUT`, when it has the shape git gives; a
    refusal for any other shape where a `.git` is at or above `start`, as for an answer git did
    not give; and `None` for one where none is, which names no checkout. Read as "step on", an
    answer of another shape inside a work tree let the candidate walk pass every directory of a
    repository holding the overlay."""
    if lines is None or _well_shaped(lines):
        return lines
    if in_work_tree(start):
        raise Refusal(_MISSHAPEN.format(start=quoted(str(start))))
    return None


def _repository(project_root: Path) -> _Repository | None:
    """The repository `project_root` is in; `None`, which is "no repository"; or a refusal.

    **Its checkouts are asked from the project's side.** The first version asked
    `rev-parse --git-common-dir` from inside the *candidate* and compared the answers, which let
    the candidate's own bytes choose the answer: a committed bare-shaped `ov/` reported itself as
    its own common directory, so a clone's `ov/` in a sibling worktree was "another repository"
    and was recorded. `git worktree list` is the repository's own record of its checkouts, which
    a clone cannot commit into.

    **`None` only where no `.git` is at or above `--root`**, which is the one place `_ask`
    answers `None` to an unkeyed question: there is no checkout for git to name, whatever git
    said. `_outside_the_project` says what is still compared then. Every other way of not
    answering refuses: a git inside a checkout that says nothing, exits non-zero, is ended by a
    signal or refuses the repository it found (`safe.directory`, an unreadable `.git`), all in
    `_ask`; an answer that says `--root` is not inside a work tree (a root inside a bare-shaped
    directory has no checkout of its own to compare against); an answer git gives only without
    the key; and a listing that fails or is empty.
    """
    start = _nearest_directory(project_root)
    unlisted = _UNLISTED.format(root=quoted(str(project_root)))
    answer = _ask(start, *_EXPLICIT_BARE, *_COMMON_AND_CHECKOUT, keyed=True)
    retried = False
    if answer is None:
        # git 2.38 and later refuse an implicit bare repository outright. Asked again without
        # the key only to tell that apart from "no repository at all".
        retried = True
        answer = _ask(start, *_COMMON_AND_CHECKOUT)
        if answer is None:
            return None
    # The same shape `_shaped` asks of the walk, asked wherever `--root` is: an answer for `--root`
    # is never stepped past.
    if not _well_shaped(answer):
        raise Refusal(_MISSHAPEN.format(start=quoted(str(start))))
    if answer[1] != "true":
        raise Refusal(
            f"git does not read {quoted(str(project_root))} as inside a checkout: it is inside a "
            f"bare repository, a git directory, or a directory holding `HEAD`, `objects/` and "
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
    cannot remove a refusal the listing makes. Nor can a git that says nothing, exits non-zero
    or is ended by a signal: on the walk, as everywhere `_ask` is used, that is a refusal inside
    a checkout and not a step past it.

    **Only an answer from inside a work tree is the candidate's.** On a git that ignores
    `safe.bareRepository`, a bare-shaped `ov/` answers for itself, and its committed `config` or
    `commondir` can make that answer say "not bare" with a common directory anywhere. It cannot
    make git say `ov/` is inside a work tree: that answer comes only through a checkout's `.git`,
    which a repository cannot commit. So the walk goes on past every other answer of the shape git
    gives (`_shaped`); an answer of any other shape inside a work tree refuses.

    Walked up rather than asked once, because git refuses to answer from inside a bare-shaped
    directory — which is exactly where a clone puts the candidate — and a git directory's answer
    is not the candidate's. Asked from the nearest directory that exists, because a
    `create:` destination does not yet.
    """
    start = _nearest_directory(candidate)
    while True:
        answer = _shaped(start, _ask(start, *_EXPLICIT_BARE, *_COMMON_AND_CHECKOUT, keyed=True))
        if answer is None and in_work_tree(start):
            # A bare-shaped directory, which git declines under the key and describes without
            # it, or a repository git refuses either way, which `_ask` refuses.
            _shaped(start, _ask(start, *_COMMON_AND_CHECKOUT))
        if answer is not None and answer[1] == "true":
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


def _outside_the_project(candidate: Path, *, project_root: Path, exempt: bool) -> None:
    """Refuse an overlay root that sits where the repository an agent works in could reach it.

    A path arm and three `git` arms. The path arm is equality or nesting either way round — a
    candidate *under* the project, and a candidate that *holds* it, which is the shape
    `git worktree add .worktrees/x` produces and which the first draft accepted. The `git` arms
    are the sibling case the paths cannot see: `stayfixed.worktrees/feature` is not under
    `stayfixed/`, so a clone committing its own manifests at its own root passed the path arm
    whenever `--root` was one of its worktrees — and working in a worktree makes `--root` one.
    The first applies the path arm to every checkout `_repository` lists; the second,
    `_candidate_repository`, catches the checkouts that list names by their git directory. See
    each for why it is asked from the side it is. The third asks the same walk from above the
    candidate, and refuses any checkout that holds it, of whichever repository: a directory in a
    work tree is a place that repository can ship files into, a nested checkout's included.

    **With `--root` in no repository, only an `exempt` `create:` destination skips the path
    arm** (`_exemption`): one that is not there when the phase asks, which this run makes —
    `gh repo create` clones into it — and the overlay root the machine file already records,
    which is the owner's own run again. Comparing those with `--root` refused the owner's own
    `setup --overlay create:<owner>/<name> --yes` run in `~`, where `--root` defaults to the home
    directory the overlay is created in. A destination that is there and not recorded is not
    the run's making, since `create` leaves a populated destination alone, and any other
    overlay already on disk is compared with `--root` whether or not git finds a repository
    there: a directory in no repository can still hold a tree someone else made — a project
    downloaded as an archive, a work tree of another version control system, a `vendor/ov`
    shipped inside either. What the comparison needs a repository for is the listing of the
    other checkouts, and "no repository" is `_repository`'s `None`, which `_ask` answers only
    where no `.git` is at or above `--root`: a git that is there and says nothing refuses. The
    candidate's own side is asked either way. The anchor is `--root`, which the command line
    chooses: run from a directory git finds no repository for, no other checkout of the project
    an agent works in is compared. Nor is what git cannot find there: a work tree of another
    version control system, and one whose git directory is elsewhere and named only by
    `--git-dir` and `--work-tree` or `GIT_DIR` — a bare-repository dotfiles home is one — has no
    other checkouts compared, since `gitenv` scrubs `GIT_DIR` from every `git` it runs and no
    `.git` leads to them.

    **What it does not cover, stated rather than implied.** A common directory whose path is not
    UTF-8 is an answer like any other: `git_run` decodes it losslessly, so two checkouts of one
    repository still compare equal. And what the whole check bounds is a repository *shipping* a
    tree: committed contents reach that repository's own checkouts and nowhere else, so refusing
    all of them removes the case a clone can stage. It is not a claim that no other directory on
    the machine can hold the same bytes — a separate `git clone` of the same remote has its own
    common directory and passes — only that the owner, and not the clone, put it there.
    """
    resolved_candidate = fsops.resolved(candidate)
    resolved_project = fsops.resolved(project_root)
    # Both are printed through `printed.quoted`: a path resolved through a link a repository
    # commits is spelled in bytes the repository chose.
    shown, project = quoted(str(candidate)), quoted(str(project_root))
    repository = _repository(resolved_project)
    same_repository = (
        f"{shown} is inside a checkout of the same repository as {project}, the "
        f"project this command was run from, holds one, or is one. The overlay root is the "
        f"machine's trust anchor and must live outside every checkout of a repository an agent "
        f"works in — a worktree is not a different repository, and a clone ships its own tree "
        f"into all of them"
    )
    compared = repository is not None or not exempt
    if compared and _overlaps(resolved_candidate, resolved_project):
        where = (
            # git names the directory, and a submodule's carries the name `.gitmodules` chose.
            f"in the repository whose git directory is {quoted(str(repository.common))}"
            if repository is not None
            # Said, because "no repository" reads like "nothing could have shipped it", and an
            # archive or another version control system's checkout can.
            else "which is in no git repository, and a tree there can still have come from "
            "someone else: an archive, or a checkout of another version control system"
        )
        raise Refusal(
            f"{shown} is inside {project}, holds it, or is it — and {project} "
            f"is the project this command was run from, {where}. The overlay root is the "
            f"machine's trust anchor and must live outside the project an agent works in: it "
            f"could otherwise ship its own tree and have this command record it"
        )
    if repository is not None:
        for checkout in repository.checkouts:
            if _overlaps(resolved_candidate, fsops.resolved(checkout)):
                raise Refusal(same_repository)
    found = _candidate_repository(resolved_candidate)
    if found is None:
        return
    if repository is not None and _same(fsops.resolved(found), fsops.resolved(repository.common)):
        raise Refusal(same_repository)
    # Asked from above the candidate, so an overlay that is the top of a checkout of its own is
    # not its own answer: what git finds there is a work tree that holds the candidate, and that
    # repository can put files in it — a merge writes a tracked path into a nested checkout's
    # directory as into any other.
    outer = _candidate_repository(resolved_candidate.parent)
    if outer is None:
        return
    # A linked worktree of the overlay's own repository, nested in another checkout of it, is
    # refused for the same reason — the outer checkout can write into it — and said as what it
    # is: "another repository" sent the owner looking for one that is not there. Its own only
    # when the candidate is a checkout's top, its `.git` there: a plain directory's nearest
    # checkout is the outer one, and that is another repository.
    own = os.path.lexists(resolved_candidate / ".git") and _same(
        fsops.resolved(outer), fsops.resolved(found)
    )
    whose = "another checkout of its own repository" if own else "a checkout of another repository"
    raise Refusal(
        f"{shown} is inside {whose}, whose git directory is {quoted(str(outer))}. The "
        f"overlay root is the machine's trust anchor and must not lie where a repository can "
        f"ship files: put it in a directory no repository's checkout holds"
    )


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
    # Why a `create:` destination is not compared with a `--root` in no repository, or `None`
    # when it is: `ABSENT` when nothing was there when the phase asked, so this run makes it, and
    # `RECORDED` when it is the overlay root the machine file already records, which is the
    # owner's own run again. `_exemption` decides it; nothing else exempts a destination.
    exempt: str | None = None
    # For `create:`, the destination as `overlay.api.target_root` names it, `<home>/<name>`,
    # which is where `create` clones; `root` is that path resolved, which is what is judged,
    # compared with the recorded root and recorded, as `--overlay <path>` records its path
    # resolved. A link there is the repository's to retarget, its target is not.
    destination: Path | None = None


# `_Overlay.exempt`'s two values.
ABSENT = "absent"
RECORDED = "recorded"


def _exemption(planned: _Overlay, *, machine: Path) -> str | None:
    """Whether a `create:` destination is exempt from the comparison with a `--root` in no
    repository, and why; `None` for `--overlay <path>` and for any destination this run neither
    makes nor already records. `create` leaves a populated destination alone and records it, so
    a tree an archive or a clone put at `<home>/<name>` would otherwise be recorded uncompared.
    The machine file is read only for a destination that is there."""
    if planned.create is None or planned.destination is None:
        return None
    # The destination itself, not where it leads: a link there, dangling or not, is not a
    # directory this run makes.
    if not os.path.lexists(planned.destination):
        return ABSENT
    # There and leading nowhere: a link whose target is not there. `gh repo create` would make a
    # repository on the owner's account and then clone through the link, or fail on it.
    if not fsops.exists(planned.destination):
        raise Refusal(
            f"{quoted(str(planned.destination))} is a link to {quoted(str(planned.root))}, which "
            f"is not there, so `create:` would clone through it to wherever it leads; remove the "
            f"link, or point it at the overlay and record that with --overlay <path>"
        )
    recorded = overlay_root(machine)
    if recorded is not None and _same(recorded, planned.root):
        return RECORDED
    return None


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


def _requested_overlay(overlay: str | None, *, home: Path, yes: bool) -> _Overlay | None:
    """What `--overlay` names, and every refusal its arguments and its tree's identity can raise.

    The first step of `_before_the_first_write`; where the overlay lies is asked there too, last
    (`_outside_the_project`). The first draft called the equivalent of this from the bottom
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
        root = fsops.resolved(destination)
        _recordable(root)
        return _Overlay(root=root, create=(account, name), destination=destination)
    candidate = fsops.resolved(Path(overlay).expanduser())
    _recordable(candidate)
    require_overlay(candidate, because=_RECORDING)
    return _Overlay(root=candidate, create=None)


def _apply_overlay(planned: _Overlay, *, project_root: Path, runner: Runner) -> tuple[Path, str]:
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
    from stayfixed.overlay.api import create, init_instance, overlay_fault, require_overlay

    if planned.create is None:
        require_overlay(planned.root, because=_RECORDING)
        _outside_the_project(planned.root, project_root=project_root, exempt=False)
        return planned.root, f"recorded the existing overlay at {quoted(str(planned.root))}"
    owner, name = planned.create
    destination = planned.destination if planned.destination is not None else planned.root
    created = create(owner, name, source="template", root=destination.parent, runner=runner)
    # The one value judged, initialised and recorded, as the phase planned it: what the clone's
    # path resolves to now, so a link that arrived there since is followed and not recorded.
    root = fsops.resolved(created.root)
    # Before `init_instance`, which now asks the same question and refuses with an answer that
    # does not say the repository exists; this one has to, and so it goes first.
    fault = overlay_fault(root)
    if fault is not None:
        raise Refusal(
            f"{fault}. {owner}/{name} was created and cloned to {quoted(str(root))}, but {_CREATED}"
        )
    # Asked before `init_instance`, which writes in the tree and runs `pre-commit` there. An
    # exemption is the phase's verdict on one directory, so it holds only for that directory; and
    # a destination the phase found absent is exempt only if `create` made a directory there: one
    # it left alone, or a link it cloned through, arrived after the phase, from somewhere else.
    judged = _same(root, planned.root)
    exempt = judged and (
        planned.exempt == RECORDED
        or (
            planned.exempt == ABSENT
            and created.template is not None
            and not os.path.islink(created.root)
        )
    )
    _outside_the_project(root, project_root=project_root, exempt=exempt)
    initialised = init_instance(root, owner, runner=runner)
    if created.template is None:
        # `create` found a populated destination and generated nothing (no `gh` call at all),
        # which is what re-running `setup --overlay create:` does after the first run, so there is
        # no template to name. `init` still ran on it, and an overlay named by an earlier release
        # has its manifests completed or its old memory README removed, so the note says what
        # `init` changed rather than that the overlay was left alone.
        changed = initialised.changed
        return root, (
            f"found the overlay already at {quoted(str(root))}, so nothing was generated; "
            + (
                f"`overlay init` changed {', '.join(changed)}"
                if changed
                # Not "nothing": `init` also runs `pre-commit install`, which may write the
                # overlay's untracked git hook on this run.
                else "`overlay init` changed none of the overlay's tracked files"
            )
        )
    return root, f"created the overlay at {quoted(str(root))}, generated from {created.template}"


def _before_the_first_write(
    preset: str,
    *,
    home: Path,
    machine: Path,
    project_root: Path,
    overlay: str | None,
    yes: bool,
) -> tuple[dict[str, Any], _Overlay | None, Path]:
    """Every question `setup` asks before its first write, in one order, under one floor; and
    `home` resolved, which every write under it uses.

    **`--home` is resolved first.** It is the machine owner's own directory, and one that is a
    link — a home kept on another volume — is that owner's layout.

    Nothing is written, and no program is run, until every step has answered; each refuses with
    its own words, and the first refusal ends the run. The steps, in order:

    1. **What `--overlay` names** (`_requested_overlay`): `create:` without `--yes`, a spec
       without both halves, a name that is not one path segment, a root the machine file cannot
       hold; and for `--overlay <path>`, a tree that is not an overlay.
    2. **The preset** (`load_preset`): a mistyped `--preset`. It used to come one line after the
       home tree had been created for it.
    3. **Where a write under `--home` lands** (`_check_home_usable`): the settings file's
       directory, the `mkdir` of a home not there yet, and a `create:` destination.
    4. **Where the overlay lies** (`_outside_the_project`): `git`, asked from the project's side
       and from the overlay's.

    Where the overlay lies comes last: a `create:` destination under a home nobody may search is
    that home's fault, which step 3 names, where `git`'s walk up from the destination can only
    meet the same unsearchable directory. Last also because it is the step that runs programs.

    **The floor.** `fsops`' predicates raise rather than guess when a path cannot be asked
    about, and a step that does not word that itself let the `OSError` reach `cli.run` as
    `stayfixed: internal error`: the walk up from a `create:` destination under a home nobody
    may search, an `--overlay` or a `--root` directory below one. Whatever a step
    raises that way is a refusal here, naming the path that was being asked about — the
    `OSError`'s own file name, the path the predicate was handed — and the fault in
    `fsops.said`'s words. A step whose own words name the cause better keeps them.
    """
    try:
        home = fsops.resolved(home)
        planned = _requested_overlay(overlay, home=home, yes=yes)
        # Where this run clones a `create:` overlay, or `None` when it creates none.
        created = planned.root if planned is not None and planned.create is not None else None
        data = load_preset(preset, key="--preset")
        _check_home_usable(home, created=created)
        if planned is not None:
            planned = replace(planned, exempt=_exemption(planned, machine=machine))
            _outside_the_project(
                planned.root, project_root=project_root, exempt=planned.exempt is not None
            )
    except OSError as exc:
        asked = (
            quoted(str(exc.filename)) if exc.filename is not None else "a path this run was given"
        )
        raise Refusal(
            f"{asked} cannot be checked ({fsops.said(exc)}), so nothing was written"
        ) from exc
    return data, planned, home


def setup(
    preset: str,
    *,
    home: Path,
    machine: Path,
    runner: Runner,
    yes: bool,
    overlay: str | None,
    project_root: Path,
) -> SetupReport:
    """Configure this machine from `preset`.

    `project_root` is the repository this invocation was run from (the CLI's `--root`, default
    `.`), and it exists for exactly one reason: `_outside_the_project` refuses an `--overlay`
    that any checkout of it could reach. `yes` confirms creating an overlay on GitHub and
    nothing else: there is no other prompt here for it to answer (see the module docstring).

    **Everything structural is asked before the first write**, in `_before_the_first_write`:
    `--overlay` is parsed and probed, the preset is loaded, the places a write under `--home`
    lands are asked, and the overlay is contained, while nothing is on disk and no repository
    exists on anyone's GitHub account. What is left after that is the
    work, and the one refusal that follows a write is the post-condition on a tree this run
    created.
    """
    data, planned_overlay, home = _before_the_first_write(
        preset,
        home=home,
        machine=machine,
        project_root=project_root,
        overlay=overlay,
        yes=yes,
    )

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
