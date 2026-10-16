"""`doctor`'s `approval-boundary` row: whether a session of this project keeps an agent out of the
trust record.

An approval holds against what a repository commits; against an agent that writes `trust.json`
itself it holds only while the harness stops that write (`trust.boundary` says what stops it, and
how that was measured). So the row reads this project's effective Claude Code settings, in the
harness's own precedence — managed settings with their drop-ins, then the project's
`.claude/settings.local.json`, then its `.claude/settings.json`, then the user's file in `.claude`
under the home — and answers four questions: is the sandbox on for this project, confining the
filesystem; do the `permissions.deny` rules `setup` writes over the record's directory stand, byte
for byte; does any setting widen what those confine; and does any of it rest on a file the
repository can change.

- **Whether the sandbox is on** is the highest layer's `sandbox.enabled`. While the sandbox is
  admin-required, which only managed settings make it (`sandbox.allowUnsandboxedCommands = false`
  there; a user's own does not stop a repository turning the sandbox off), a repository's `false` is
  passed over when managed settings or the user's file set `true`, as Claude Code's sandboxing
  reference says, and stands otherwise. A `sandbox.filesystem.disabled` that is there and is not
  `false` turns the sandbox's filesystem confinement off, and is a gap as the sandbox being off is:
  in managed settings and the user's file always, and in a repository's file while the sandbox is
  not admin-required (the reference says a repository's file cannot set it; the row does not lean
  on that).
- **The deny rules** from any layer count, as the harness adds them up, and only `setup`'s own
  spellings count: `Edit(//<directory>/**)` over the directory where it leads, and over the
  directory as named where a symbolic link makes the two differ (`trust.boundary.deny_rules`), each
  compared byte for byte. Another spelling of the same directory is not read as covering it.
- **What widens them**, by the key names the sandboxing reference gives, which were not measured
  here: a repository's non-empty `sandbox.excludedCommands`, which runs commands outside the
  sandbox, and any entry of `sandbox.filesystem.allowWrite`, an `Edit` rule in `permissions.allow`
  or `permissions.additionalDirectories` not shown safe, in the project's or the local file while
  the sandbox is not admin-required (`WIDENING_KEYS` says what Claude Code ignores while it is, and
  why skipping those files then is still right), and in the user's file always, since there one
  undoes the deny rule. **An entry is read as text and nothing else**: no filesystem call and no
  pattern engine touches it. It is safe only when every condition `_safe` asks holds: a literal
  path of letters, digits, `.`, `_`, `-`, `~` and `/` with no `.`, `..` or empty component;
  anchored outside the working directory as the documentation anchors it for its key (a sandbox
  path list's or `additionalDirectories`' `/x` is absolute, an `Edit` rule's `//x` is, and `~/x` is
  under the home for both — under every home it may mean: the password database's, the `--home`
  given, and `HOME`, which Claude Code expands `~` from — while an `Edit` rule's `/x` is the
  project's and a relative path is the working directory's for both); outside the project, its
  root neither held nor holding it; and neither either spelling of the record's directory (as
  named, and resolved by stayfixed from its own machine path), nor above it, nor inside it —
  compared `trust.boundary.folded`. Nor may another widening entry the row reads be the same place
  or lie above it (`_nested`): an agent's shell writes inside the other, so it can put a link to
  the record's directory where this one names before a later session resolves it, and whether a
  deny rule holds inside a wider entry was not measured. Every other entry is a gap: there is no
  class of entry the row could not tell about.

**Only the owner's files make it green.** Managed settings and the user's file are the owner's; a
repository's two files change with its next commit, which a pull delivers with no person acting.
So the sandbox's `true` and the deny rules decide red from every layer, and green only from managed
settings and the user's file: where the only `true`, or the only copy of a rule, is a repository's,
the row is at best a warning naming that file. A repository's bytes may make the answer worse,
never better.

**Red only once the machine holds an approval.** With one, a gap is red; with none, it is a
warning, so a default install is never red here. With every setting in force the row still warns
until managed settings make the sandbox admin-required and set `sandbox.failIfUnavailable = true`,
the sandboxing reference's own recipe for enforcing it — without the second, Claude Code runs
commands outside a sandbox that cannot start — and is green only then. A trust record that cannot
be read is taken to hold approvals, since it holds every project's on the machine. A settings file
that cannot be read as one JSON object (unreadable, not UTF-8, or not JSON) is read as absent for
its layer and named; the row is never red for that alone, and never green beside it, since what
the harness makes of the file is not known here.

**`CLAUDE_CONFIG_DIR` may only make the answer worse**, since nothing tells whether a person or a
repository set it (`trust.boundary.user_settings`). Where it names a directory not spelled byte for
byte as the home's `.claude`, that directory is judged too, and its gaps are added, said with its
file, raising the status and never lowering it. Where the home has no `.claude`, the variable's
directory is judged alone and the row is at best a warning, naming it. A directory inside the
project is never judged: it is named, and the row is at best a warning for it.

**Skipped** on a machine with no Claude Code user settings directory, and for a project whose
`[stayfixed] agents` does not list `claude` and which carries neither `.claude/settings.json` nor
`.claude/settings.local.json`: the agents list is the repository's to write, so a project that ships
Claude Code settings is read whatever it lists. With no `stayfixed.toml`, the preset's agents apply.

Nothing a repository wrote is printed: the files are named by the labels a reader types, the deny
rule and the managed path are stayfixed's own and the machine's, and no value is quoted.
"""

from __future__ import annotations

import os
import posixpath
import string
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from stayfixed import fsops
from stayfixed.config.machine import passwd_home
from stayfixed.doctor.model import OK, RED, SKIP, WARN, Context, Row, Status
from stayfixed.errors import Failure
from stayfixed.harnesses import CLAUDE
from stayfixed.jsonobject import json_object
from stayfixed.presets import load_preset
from stayfixed.printed import quoted
from stayfixed.trust.api import (
    CONFIG_DIR_VARIABLE,
    ENABLED,
    FAIL_IF_UNAVAILABLE,
    MANAGED_DROP_INS,
    SANDBOX,
    UNSANDBOXED_ALLOWED,
    UnreadableTrust,
    deny_rules,
    folded,
    in_project,
    managed_settings,
    record_path,
    recorded,
    user_settings,
)

(PROJECT_SETTINGS,) = CLAUDE.settings
(LOCAL_SETTINGS,) = CLAUDE.local_settings
USER_FILE = Path(PROJECT_SETTINGS).name

# The two skips: a measurement that is simply unavailable, so neither carries a remedy.
NO_CLAUDE_CODE = (
    "this machine has no Claude Code user settings directory, so there is no sandbox or deny rule "
    "to read"
)
NOT_LISTED = (
    "[stayfixed] agents does not list claude and the project carries no Claude Code settings file, "
    "so no session of this project runs where the sandbox and the deny rule apply"
)
# The approvals the row is judged against, the first part of every answered detail.
HELD = "{count} approval(s) recorded on this machine"
NONE_HELD = "no approval is recorded on this machine yet, so a gap is a warning"
RECORD_UNREAD = "the trust record cannot be read, so it is taken to hold approvals"
# The gaps, each naming the setting and what it stops.
NO_SANDBOX = (
    "no settings file turns the sandbox on (sandbox.enabled = true), so an agent's shell commands "
    "run outside it, where nothing stops one writing the trust record"
)
TURNED_OFF = (
    "{label} sets sandbox.enabled = false, which turns the sandbox off for this project, so an "
    "agent's shell commands run outside it, where nothing stops one writing the trust record"
)
FILESYSTEM_OFF = (
    "{label} sets sandbox.filesystem.disabled = true, which turns the sandbox's filesystem "
    "confinement off, so an agent's shell writes anywhere, the trust record included"
)
NO_DENY = (
    "permissions.deny lacks {rule}, as setup writes it over the trust record's directory, so the "
    "shell and the file tools may write the approvals in it"
)
# A setting that widens what the sandbox or the deny rule confines. `label` names the file and
# `key` the setting; the entry itself is not printed, since a repository wrote it.
EXCLUDED = (
    "{label} sets sandbox.excludedCommands, so the commands it names run outside the sandbox, "
    "where nothing stops one writing the trust record"
)
WIDENED = (
    "{label}'s {key} holds an entry not shown to stay clear of the trust record's directory, so "
    "the shell or the file tools may write the approvals in it past the deny rule"
)
NESTED = (
    "{label}'s {key} holds an entry that another widening entry names or lies above, so an agent's "
    "shell may put a link to the trust record's directory in its place before a later session "
    "reads it"
)
# Protection that rests on a repository's file alone: in force today, and gone with the commit that
# removes it.
SANDBOX_FROM_REPOSITORY = (
    "the sandbox is on only because {label} sets sandbox.enabled = true, a file in the project's "
    "tree, so a later commit can remove it"
)
DENY_FROM_REPOSITORY = (
    "{rule} stands only in {label}, in the project's tree, so a later commit can remove it"
)
# Both in force, and not admin-required: what a repository can still do.
NOT_ADMIN = (
    f"the sandbox is on and the deny rule covers the trust record's directory, but managed "
    f"settings do not make the sandbox admin-required, so a repository's {PROJECT_SETTINGS} or "
    f"{LOCAL_SETTINGS} can turn it off, and an agent can retry a command outside it"
)
# Admin-required, and yet a machine where the sandbox cannot start runs commands outside it.
NO_FAIL_CLOSED = (
    "{managed} does not set sandbox.failIfUnavailable = true, nor does a drop-in beside it, so "
    "where the sandbox cannot start, Claude Code runs an agent's shell commands outside it"
)
GUARDED = (
    "the sandbox is on, admin-required and required to start, and {rule} denies writes to the "
    "trust record's directory"
)
NOT_READ = (
    "{label} could not be read as one JSON object (it is unreadable, not UTF-8, or not JSON) and "
    "was read as absent"
)
# Where `CLAUDE_CONFIG_DIR` names a user settings directory besides the home's, that one may only
# make the answer worse (`trust.boundary.user_settings` says why): its gaps are added, said with its
# file. `path` is the variable's value, which a repository may have chosen, so it is printed
# through `printed.quoted`.
JUDGED_WITH = "judged with {label}: {detail}"
USER_LABEL = f"~/{PROJECT_SETTINGS}"
CHOSEN_LABEL = f"${CONFIG_DIR_VARIABLE}/{USER_FILE}"
CHOSEN_ALONE = (
    f"the home has no .claude, so the user settings were read from {{path}}, the directory "
    f"{CONFIG_DIR_VARIABLE} names, which a repository's env block, direnv or mise may have chosen, "
    f"so the row is at best a warning"
)
CONFIG_DIR_IN_PROJECT = (
    f"{CONFIG_DIR_VARIABLE} names {{path}}, inside the project, whose contents the repository "
    f"chooses, so it was not read and the row is at best a warning"
)
# How bad each answer is, for letting the variable's directory make one worse and never better.
SEVERITY = {SKIP: 0, OK: 1, WARN: 2, RED: 3}
# The remedies.
ADD_THE_BOUNDARY = (
    "run `stayfixed setup --approval-boundary`, which adds the deny rule and prints the sandbox "
    "settings to set"
)
MAKE_IT_ADMIN = (
    "set sandbox.enabled = true, sandbox.failIfUnavailable = true and "
    "sandbox.allowUnsandboxedCommands = false in {managed}, a file only an administrator writes: "
    "then no repository's settings turn the sandbox off, no command runs outside it, and Claude "
    "Code does not start where it cannot"
)
MAKE_IT_JSON = (
    "make each file the detail names a readable UTF-8 file holding one JSON object, then run "
    "`stayfixed doctor` again"
)
KEEP_THE_FILESYSTEM = (
    "take sandbox.filesystem.disabled out of each file the detail names, or set it to false"
)
NARROW_THE_SETTINGS = (
    "take sandbox.excludedCommands out of each repository file the detail names, and take out each "
    "entry of a key it names or spell it as a literal path outside the project and the trust "
    "record's directory, of letters, digits, `.`, `_`, `-` and `/`: `/…` or `~/…` in a sandbox "
    "path list and permissions.additionalDirectories, `//…` or `~/…` in an Edit rule, none of them "
    "inside another"
)
NO_MANAGED_PATH = "the managed settings file"
# The rule's place in a sentence on a machine with no home for a trust record: the password
# database lists none for this user, and `--machine` was not given.
NO_RECORD_RULE = "Edit(//<the trust record's directory>/**)"


@dataclass(frozen=True)
class _Layer:
    """One settings layer: what the reader names it, and its document, `None` when absent or
    unreadable."""

    label: str
    document: Mapping[str, Any] | None
    unread: bool = False


def _read(path: Path, label: str) -> _Layer:
    """The settings file at `path` as one JSON object, absent when it names no regular file, and
    unreadable when it is there and is not one."""
    try:
        if not fsops.names_regular_file(path):
            return _Layer(label, None)
        text = fsops.read_regular_bytes(path).decode("utf-8")
    except (OSError, UnicodeDecodeError):
        return _Layer(label, None, unread=True)
    if not text.strip():
        return _Layer(label, {})
    try:
        return _Layer(label, json_object(text, label, error=Failure))
    except Failure:
        return _Layer(label, None, unread=True)


def _merged(base: Mapping[str, Any], over: Mapping[str, Any]) -> dict[str, Any]:
    """`over` merged into `base`: objects key by key, lists added up, anything else replaced."""
    out = dict(base)
    for key, value in over.items():
        held = out.get(key)
        if isinstance(held, dict) and isinstance(value, dict):
            out[key] = _merged(held, value)
        elif isinstance(held, list) and isinstance(value, list):
            out[key] = [*held, *value]
        else:
            out[key] = value
    return out


def _managed() -> tuple[_Layer, list[_Layer]]:
    """The managed layer, its drop-ins merged over it in name order, and every file of it that was
    there and could not be read."""
    path = managed_settings()
    if path is None:
        return _Layer(NO_MANAGED_PATH, None), []
    base = _read(path, str(path))
    unread = [base] if base.unread else []
    document: dict[str, Any] | None = None if base.document is None else dict(base.document)
    drop_ins = path.parent / MANAGED_DROP_INS
    if fsops.is_dir(drop_ins):
        names = sorted(
            entry.name
            for entry in os.scandir(drop_ins)
            if entry.name.endswith(".json") and not entry.name.startswith(".")
        )
        for name in names:
            layer = _read(drop_ins / name, str(drop_ins / name))
            if layer.unread:
                unread.append(layer)
            elif layer.document is not None:
                document = _merged(document or {}, layer.document)
    return _Layer(str(path), document), unread


def _sandbox(layer: _Layer, key: str) -> object:
    table = (layer.document or {}).get(SANDBOX)
    return table.get(key) if isinstance(table, dict) else None


def _filesystem_off(layer: _Layer) -> bool:
    """Whether `layer` sets `sandbox.filesystem.disabled`, to anything but `false`."""
    table = _table(layer.document, SANDBOX, FILESYSTEM)
    return isinstance(table, dict) and DISABLED in table and table[DISABLED] is not False


def _deny_rules(layers: Sequence[_Layer]) -> set[str]:
    found: set[str] = set()
    for layer in layers:
        permissions = (layer.document or {}).get("permissions")
        rules = permissions.get("deny") if isinstance(permissions, dict) else None
        if isinstance(rules, list):
            found.update(rule for rule in rules if isinstance(rule, str))
    return found


# The keys that widen confinement, as Claude Code's sandboxing reference names them (not measured
# here). While the sandbox is admin-required, the reference says that from Claude Code 2.1.285 on,
# in a repository's project and local files, Claude Code ignores every `excludedCommands` entry and
# the write access each of these entries gives sandboxed commands -- and only that: Claude's file
# tools still follow a repository's `Edit(...)` allow rules and `additionalDirectories`. The row
# reads those files only while the sandbox is not admin-required all the same, because what keeps
# the file tools out of the record's directory is the deny rule, and a deny rule outranks every
# allow rule for them (the reference: deny entries still apply, and an explicit deny is always
# respected), so no repository allow entry lets them past it. The user's file is read in every case.
EXCLUDED_COMMANDS = "excludedCommands"
FILESYSTEM = "filesystem"
ALLOW_WRITE = "allowWrite"
# `sandbox.filesystem.disabled`, which turns the filesystem confinement off (the module docstring).
DISABLED = "disabled"
ADDITIONAL_DIRECTORIES = "additionalDirectories"
WIDENING_KEYS = (
    f"{SANDBOX}.{FILESYSTEM}.{ALLOW_WRITE}",
    "permissions.allow",
    f"permissions.{ADDITIONAL_DIRECTORIES}",
)
# The only characters a safe entry may hold. Anything else -- a pattern character, a backslash, a
# NUL, a space, a letter outside ASCII -- makes the entry a gap: the row reads an entry as text and
# never asks the filesystem or a pattern engine about it, since proving what someone else's
# matcher, or an automounted root, makes of it is not this row's to do.
ALLOWED = frozenset(string.ascii_letters + string.digits + "._/~-")
# The components a safe entry may not hold: the empty one (`a//b`, a trailing `/`), `.` and `..`.
NOT_A_NAME = frozenset({"", ".", ".."})
# An `Edit` rule in `permissions.allow`: bare, which allows every edit, or with its path.
EDIT = "Edit"
# The prefix that makes an entry of each key absolute, as Claude Code's documentation states (not
# measured here): one slash in a sandbox path list and in `additionalDirectories`, two in a
# permission rule, whose single slash is the project's. `~/` is the home for every key, and a
# relative path the working directory's. Only these anchors lie outside the working directory;
# every other spelling lies in the project, or where the row cannot show, and is a gap.
ABSOLUTE = {WIDENING_KEYS[0]: "/", WIDENING_KEYS[1]: "//", WIDENING_KEYS[2]: "/"}
HOME = "~/"


def _table(document: Mapping[str, Any] | None, *keys: str) -> object:
    value: object = document or {}
    for key in keys:
        value = value.get(key) if isinstance(value, dict) else None
    return value


def _strings(value: object) -> list[str]:
    return [item for item in value if isinstance(item, str)] if isinstance(value, list) else []


def _related(place: str, held: str) -> bool:
    """Whether the paths `place` and `held`, as text, are one, or either holds the other."""
    return place == held or place.startswith(held + "/") or held.startswith(place + "/")


def _homes(context: Context) -> list[Path | None]:
    """Every home a `~/` entry may be read under: the password database's, the `--home` given, and
    `HOME`, which Claude Code expands `~` from, where it is set; `None` stands for a `HOME` that
    names no absolute directory, under which no `~/` entry can be placed."""
    homes: list[Path | None] = [home for home in (passwd_home(), context.home) if home is not None]
    named = context.env.get("HOME")
    if named is not None:
        homes.append(Path(named) if os.path.isabs(named) else None)
    return list(dict.fromkeys(homes)) or [None]


def _anchored(entry: str, key: str, homes: Sequence[Path | None]) -> list[str] | None:
    """Every absolute path `entry` may name under `key`'s anchoring, as text — one, or one per home
    for a `~/` entry — when it is a literal anchored outside the working directory; `None` for
    every other entry. No filesystem call."""
    if not set(entry) <= ALLOWED:
        return None
    if entry.startswith(ABSOLUTE[key]):
        bases, rest = [""], entry[len(ABSOLUTE[key]) :]
    elif entry.startswith(HOME) and None not in homes:
        bases = [home.as_posix().rstrip("/") for home in homes if home is not None]
        rest = entry[len(HOME) :]
    else:
        return None
    if any(part in NOT_A_NAME for part in rest.split("/")):
        return None
    return [f"{base}/{rest}" for base in bases]


def _clear(place: str, project: Sequence[str], record: Sequence[str]) -> bool:
    """Whether `place`, folded, is related to none of the project root's spellings and none of the
    record directory's."""
    return not any(_related(place, held) for held in (*project, *record))


def _safe(
    entry: str | None,
    key: str,
    homes: Sequence[Path | None],
    project: Sequence[str],
    record: Sequence[str],
) -> bool:
    """Whether `entry` of `key` is shown, as text, to lie outside the project and clear of the
    record's directory: a literal anchored outside the working directory, clear under every home
    a `~/` may mean. A bare `Edit` (`None`) allows every edit and never is, and with no record
    directory to compare nothing is."""
    if entry is None or not record:
        return False
    places = _anchored(entry, key, homes)
    if places is None:
        return False
    return all(_clear(folded(place), project, record) for place in places)


def _entries(layer: _Layer) -> dict[str, list[str | None]]:
    """`layer`'s entries of each widening key, an `Edit` rule's by its path and a bare `Edit` as
    `None`."""
    allowed = _strings(_table(layer.document, "permissions", "allow"))
    return {
        WIDENING_KEYS[0]: [*_strings(_table(layer.document, SANDBOX, FILESYSTEM, ALLOW_WRITE))],
        WIDENING_KEYS[1]: [
            None if entry == EDIT else entry[len(EDIT) + 1 : -1]
            for entry in allowed
            if entry == EDIT or (entry.startswith(f"{EDIT}(") and entry.endswith(")"))
        ],
        WIDENING_KEYS[2]: [
            *_strings(_table(layer.document, "permissions", ADDITIONAL_DIRECTORIES))
        ],
    }


def _widened(
    layer: _Layer, homes: Sequence[Path | None], project: Sequence[str], record: Sequence[str]
) -> list[str]:
    """The gaps `layer`'s widening keys open: one for each key holding an entry not shown safe."""
    return [
        WIDENED.format(label=layer.label, key=key)
        for key, listed in _entries(layer).items()
        if not all(_safe(entry, key, homes, project, record) for entry in listed)
    ]


def _nested(layers: Sequence[_Layer], homes: Sequence[Path | None]) -> list[str]:
    """The gaps of the entries in `layers` that another entry names or lies above, compared as
    `_safe` compares, one for each key holding one: an agent's shell writes inside the other, so
    what this one names may be a link to the record's directory by the time a session reads it.
    Only entries `_anchored` places are compared; every other one is a gap of its own already."""
    placed: list[tuple[str, list[str]]] = []
    for layer in layers:
        for key, listed in _entries(layer).items():
            for entry in listed:
                places = None if entry is None else _anchored(entry, key, homes)
                if places is not None:
                    said = NESTED.format(label=layer.label, key=key)
                    placed.append((said, [folded(place) for place in places]))
    return list(
        dict.fromkeys(
            said
            for n, (said, places) in enumerate(placed)
            if any(
                place == other or place.startswith(other + "/")
                for m, (_, others) in enumerate(placed)
                if m != n
                for other in others
                for place in places
            )
        )
    )


def _carries_settings(root: Path) -> bool:
    """Whether the project carries a Claude Code settings file, a link to one included."""
    return any(
        fsops.exists(root / relative) or fsops.is_symlink(root / relative)
        for relative in (PROJECT_SETTINGS, LOCAL_SETTINGS)
    )


def _lists_claude(context: Context) -> bool:
    if context.config is not None:
        return CLAUDE.name in context.config.stayfixed.agents
    agents = load_preset("recommended").get("defaults", {}).get("stayfixed", {}).get("agents", [])
    return CLAUDE.name in agents


def _spellings(*paths: Path) -> list[str]:
    """Each of stayfixed's own `paths` as the row compares an entry with it."""
    return [folded(posixpath.normpath(str(path))) for path in paths]


def approval_boundary(context: Context) -> Row:
    """The row (the module docstring says what it reads and how it answers). The home's user
    settings directory is the subject; the one `CLAUDE_CONFIG_DIR` names may only make the answer
    worse (`trust.boundary.user_settings` says why)."""
    if not _lists_claude(context) and not _carries_settings(context.root):
        return Row(SKIP, NOT_LISTED)
    found = user_settings(context.env, context.home)
    chosen = found.chosen
    inside = chosen is not None and in_project(chosen, context.root)
    ignored = (CONFIG_DIR_IN_PROJECT.format(path=quoted(str(chosen))),) if inside else ()
    other = (
        _judged(context, chosen, CHOSEN_LABEL)
        if chosen is not None and not inside and fsops.is_dir(chosen)
        else None
    )
    if found.directory is not None and fsops.is_dir(found.directory):
        row = _judged(context, found.directory, USER_LABEL)
        if other is not None and other.status != OK and other.detail != row.detail:
            row = _worsened(
                row,
                other.status,
                JUDGED_WITH.format(label=CHOSEN_LABEL, detail=other.detail),
                other.remedy,
            )
    elif other is not None and chosen is not None:
        row = _worsened(other, WARN, CHOSEN_ALONE.format(path=quoted(str(chosen))), "")
    elif inside:
        return Row(WARN, "; ".join((NO_CLAUDE_CODE, *ignored)))
    else:
        return Row(SKIP, NO_CLAUDE_CODE)
    return _worsened(row, WARN, *ignored, "") if ignored else row


def _worsened(row: Row, status: Status, said: str, remedy: str) -> Row:
    """`row`, its status made `status` where that is worse and never better, with `said` added to
    its detail and `remedy` to its remedies."""
    worse = status if SEVERITY[status] > SEVERITY[row.status] else row.status
    remedies = "; ".join(dict.fromkeys(part for part in (row.remedy, remedy) if part))
    return Row(worse, "; ".join((row.detail, said)), remedies)


def _judged(context: Context, directory: Path, user_label: str) -> Row:
    """The row's answer with the user's settings read from `directory`, named `user_label`."""
    managed, managed_unread = _managed()
    local = _read(context.root / LOCAL_SETTINGS, LOCAL_SETTINGS)
    project = _read(context.root / PROJECT_SETTINGS, PROJECT_SETTINGS)
    user = _read(directory / USER_FILE, user_label)
    admin = _sandbox(managed, UNSANDBOXED_ALLOWED) is False
    enabled, source = _enabled(managed, local, project, user, admin=admin)

    try:
        held = len(recorded(context.machine))
        lead = HELD.format(count=held) if held else NONE_HELD
    except UnreadableTrust:
        held, lead = 1, RECORD_UNREAD

    path = record_path(context.machine)
    # Where the directory leads is what the harness compares a write against, and the spelling as
    # named is what a tool call may carry, so `setup` writes a rule over each and only those count.
    real = fsops.resolved(path.parent) if path is not None else None
    wanted = deny_rules(path.parent, real) if path is not None and real is not None else ()
    rules = _deny_rules((managed, local, project, user))
    missing = [rule for rule in wanted if rule not in rules] if wanted else [NO_RECORD_RULE]
    homes = _homes(context)
    # Both spellings of the record's directory and of the project root, each computed from
    # stayfixed's own paths, never from an entry.
    record = _spellings(path.parent, real) if path is not None and real is not None else []
    project_root = _spellings(context.root, fsops.resolved(context.root))

    gaps: list[str] = []
    if enabled is not True:
        gaps.append(
            TURNED_OFF.format(label=source.label)
            if enabled is False and source is not None
            else NO_SANDBOX
        )
    if missing:
        gaps.append(NO_DENY.format(rule=" and ".join(missing)))
    # A repository's file is read for what loosens the sandbox only while it is not admin-required
    # (`WIDENING_KEYS` says why).
    repository = () if admin else (local, project)
    off = [
        FILESYSTEM_OFF.format(label=layer.label)
        for layer in (managed, *repository, user)
        if _filesystem_off(layer)
    ]
    widened: list[str] = []
    if not admin:
        for layer in (local, project):
            if _strings(_sandbox(layer, EXCLUDED_COMMANDS)):
                widened.append(EXCLUDED.format(label=layer.label))
            widened.extend(_widened(layer, homes, project_root, record))
    widened.extend(_widened(user, homes, project_root, record))
    widened.extend(_nested((*repository, user), homes))
    resting = _resting(enabled, source, (managed, user), (local, project), wanted, missing)
    unread = [
        NOT_READ.format(label=layer.label)
        for layer in (*managed_unread, local, project, user)
        if layer.unread
    ]

    managed_path = managed_settings() or NO_MANAGED_PATH
    if gaps or off or widened:
        status: Status = RED if held else WARN
        remedies = [
            *([ADD_THE_BOUNDARY] if gaps or resting else []),
            *([KEEP_THE_FILESYSTEM] if off else []),
            *([NARROW_THE_SETTINGS] if widened else []),
        ]
        detail = "; ".join((lead, *gaps, *off, *widened, *resting, *unread))
        return Row(status, detail, "; ".join(remedies))
    enforced = _sandbox(managed, FAIL_IF_UNAVAILABLE) is True
    short = [
        *resting,
        *([] if admin else [NOT_ADMIN]),
        *([] if enforced else [NO_FAIL_CLOSED.format(managed=managed_path)]),
    ]
    if short:
        remedies = [
            *([ADD_THE_BOUNDARY] if resting else []),
            *([] if admin and enforced else [MAKE_IT_ADMIN.format(managed=managed_path)]),
            *([MAKE_IT_JSON] if unread else []),
        ]
        return Row(WARN, "; ".join((lead, *short, *unread)), "; ".join(remedies))
    rule = " and ".join(wanted)
    detail = "; ".join((lead, GUARDED.format(rule=rule), *unread))
    return Row(WARN, detail, MAKE_IT_JSON) if unread else Row(OK, detail)


def _enabled(
    managed: _Layer, local: _Layer, project: _Layer, user: _Layer, *, admin: bool
) -> tuple[object, _Layer | None]:
    """The effective `sandbox.enabled`, and the layer it comes from: the highest layer's, where a
    repository's `false` gives way, while admin-required, to an owner's `true` and to nothing else
    (Claude Code's sandboxing reference)."""
    owners_true = _sandbox(managed, ENABLED) is True or _sandbox(user, ENABLED) is True
    # Highest first, each with whether the repository wrote it.
    for layer, repository in ((managed, False), (local, True), (project, True), (user, False)):
        value = _sandbox(layer, ENABLED)
        if not isinstance(value, bool):
            continue
        if value is False and admin and repository and owners_true:
            continue
        return value, layer
    return None, None


def _resting(
    enabled: object,
    source: _Layer | None,
    owners: Sequence[_Layer],
    repository: Sequence[_Layer],
    wanted: Sequence[str],
    missing: Sequence[str],
) -> list[str]:
    """What is in force only through a repository's file (the module docstring says why that is
    never green): the sandbox's `true`, where no owner's layer sets it, and each deny rule no
    owner's layer holds, naming the files that do."""
    resting: list[str] = []
    owner_says = [_sandbox(layer, ENABLED) for layer in owners]
    owners_on = next((value for value in owner_says if isinstance(value, bool)), None) is True
    if enabled is True and not owners_on and source is not None:
        resting.append(SANDBOX_FROM_REPOSITORY.format(label=source.label))
    held = _deny_rules(owners)
    lacking = [rule for rule in wanted if rule not in held]
    if lacking and not missing:
        holders = [layer.label for layer in repository if set(lacking) & _deny_rules((layer,))]
        resting.append(
            DENY_FROM_REPOSITORY.format(rule=" and ".join(lacking), label=" and ".join(holders))
        )
    return resting
