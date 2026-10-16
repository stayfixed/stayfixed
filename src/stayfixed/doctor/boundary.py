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
  here: a non-empty `sandbox.excludedCommands`, whose commands the reference says run outside the
  sandbox, with no filesystem restriction, and any entry of `sandbox.filesystem.allowWrite`, an
  `Edit` rule in `permissions.allow` or `permissions.additionalDirectories` not shown safe — each
  in the project's or the local file while the sandbox is not admin-required (`WIDENING_KEYS` says
  what Claude Code ignores while it is, and why skipping those files then is still right), and in
  the user's file always, since there one undoes the deny rule and the reference gives neither key
  a managed-only lock. Managed settings' `excludedCommands` is an administrator's choice, and still
  runs those commands where the deny rule does not reach the shell, so it is named and the row is
  at best a warning beside it. **An entry is read as text and nothing else**: no filesystem call
  and no pattern engine touches it. It is safe only when every condition `_safe` asks holds: a
  literal path of letters, digits, `.`, `_`, `-`, `~` and `/` with no `.`, `..` or empty
  component; anchored outside the working directory as the documentation anchors it for its key (a
  sandbox path list's or `additionalDirectories`' `/x` is absolute, an `Edit` rule's `//x` is, and
  `~/x` is under the home for both — under every home it may mean: the password database's, the
  `--home` given, and `HOME`, which Claude Code expands `~` from — while an `Edit` rule's `/x` is
  the project's and a relative path is the working directory's for both); outside the project, its
  root neither held nor holding it; neither either spelling of the record's directory (as named,
  and resolved by stayfixed from its own machine path), nor above it, nor inside it — compared
  `trust.boundary.folded`; and not below a `claude-<digits>` component (`SANDBOX_TEMP`), the
  per-user directory the reference says sandboxed commands write as their temporary directory,
  under whatever base `CLAUDE_CODE_TMPDIR` gives it. Nor may the entry lie strictly inside another
  widening entry the row reads, or one of managed settings' (`_nested`): an agent's shell writes
  inside the outer one, so it can put a link to the record's directory where this one names before
  a later session resolves it, and whether a deny rule holds inside a wider entry was not measured.
  The same place named twice opens nothing, since replacing it needs write access to its parent.
  Every other entry is a gap: there is no class of entry the row could not tell about.

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
be read is taken to hold approvals, since it holds every project's on the machine.

**What the row cannot read is not read as absent.** The project's two files and the user's are read
as Claude Code reads them, past a leading byte-order mark (`harnesses.lenient_settings`); managed
settings, whose reading was not measured, are read strictly. A key of the boundary's own that is
there with a value of the wrong shape is a gap, named with its file and key: a sandbox switch
(`sandbox.enabled` in any layer, `allowUnsandboxedCommands` and `failIfUnavailable` in managed
settings) that is not true or false, a `sandbox` or `sandbox.filesystem` that is not an object, a
`permissions` that is not an object where the row reads its allow rules, and any widening key that
is not a list of strings, `excludedCommands` among them (in managed settings, one that is not such
a list keeps the row from green as a non-empty one does). Read as absent, each made the answer
better than the bytes allow; how Claude Code reads such a value was not measured. A settings file
that cannot be read as one JSON object at all (unreadable, not UTF-8, or not JSON) is read as
absent for its layer and named; the row is never red for that alone, and never green beside it,
since what the harness makes of the file is not known here.

**`CLAUDE_CONFIG_DIR` may only make the answer worse**, since nothing tells whether a person or a
repository set it (`trust.boundary.user_settings`). Where it names a directory not spelled byte for
byte as the home's `.claude`, that directory is judged too, and its gaps are added, said with its
file, raising the status and never lowering it. Where the home has no `.claude`, the variable's
directory is judged alone and the row is at best a warning, naming it. A directory inside the
project or another checkout of its repository is never judged, and nor is one under neither a
home nor the project, which the row never asks the filesystem about (`trust.boundary.placement`):
each is named, and the row is at best a warning for it. The value is printed through
`printed.clipped`, since a repository may have chosen it and a model reads the row.

**Skipped** on a machine with no Claude Code user settings directory, and for a project whose
`[stayfixed] agents` does not list `claude` and which carries neither `.claude/settings.json` nor
`.claude/settings.local.json`, while the trust record can be read and holds no approval: the agents
list is the repository's to write, so a project that ships Claude Code settings is read whatever it
lists, and once the machine holds an approval, or may, a later commit's agents list cannot turn a
red row into a skip. With no `stayfixed.toml`, the preset's agents apply.

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
from stayfixed.harnesses import CLAUDE, lenient_settings
from stayfixed.jsonobject import json_object
from stayfixed.presets import DEFAULT_PRESET, load_preset
from stayfixed.printed import clipped
from stayfixed.trust.api import (
    CONFIG_DIR_VARIABLE,
    ENABLED,
    ENFORCING_SETTINGS,
    FAIL_IF_UNAVAILABLE,
    MANAGED_DROP_INS,
    NO_MANAGED_PATH,
    SANDBOX,
    UNSANDBOXED_ALLOWED,
    Placement,
    UnreadableTrust,
    folded,
    managed_named,
    managed_settings,
    placement,
    record_deny_rules,
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
    "{label}'s {key} holds an entry inside another widening entry, so an agent's shell may put a "
    "link to the trust record's directory in its place before a later session reads it"
)
# A key of the boundary's own whose value has the wrong shape (the module docstring): read as
# absent, each answered better than its bytes allow. `label` names the file and `key` the setting.
NOT_A_SWITCH = (
    "{label}'s {key} is not true or false, so whether it keeps an agent out of the trust record "
    "cannot be read"
)
NOT_AN_OBJECT = (
    "{label}'s {key} is not an object, so the settings it holds, and whether they keep an agent "
    "out of the trust record, cannot be read"
)
NOT_ENTRIES = (
    "{label}'s {key} is not a list of entries, so what it opens cannot be read, and none of it is "
    "shown to stay clear of the trust record's directory"
)
# Managed settings' `excludedCommands`: an administrator's choice, named, and never green beside.
MANAGED_EXCLUDED = (
    "{managed}, or a drop-in beside it, sets sandbox.excludedCommands, so the commands it names "
    "run outside the sandbox, where nothing stops one writing the trust record; an administrator "
    "chose them, so the row is at best a warning"
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
# file. `path` is the variable's value, which a repository may have chosen and no bound limits in
# length, so it is printed through `printed.clipped`.
JUDGED_WITH = "judged with {label}: {detail}"
USER_LABEL = f"~/{PROJECT_SETTINGS}"
CHOSEN_LABEL = f"${CONFIG_DIR_VARIABLE}/{USER_FILE}"
CHOSEN_ALONE = (
    f"the home has no .claude, so the user settings were read from {{path}}, the directory "
    f"{CONFIG_DIR_VARIABLE} names, which a repository's env block, direnv or mise may have chosen, "
    f"so the row is at best a warning"
)
CONFIG_DIR_IN_PROJECT = (
    f"{CONFIG_DIR_VARIABLE} names {{path}}, inside the project or another checkout of its "
    f"repository, whose contents the repository chooses, so it was not read and the row is at "
    f"best a warning"
)
CONFIG_DIR_ELSEWHERE = (
    f"{CONFIG_DIR_VARIABLE} names {{path}}, under neither the home nor the project, which the row "
    f"does not ask the filesystem about, since such a path may lie under a network mount, so it "
    f"was not read and the row is at best a warning"
)
# How bad each answer is, for letting the variable's directory make one worse and never better.
SEVERITY = {SKIP: 0, OK: 1, WARN: 2, RED: 3}
# The remedies.
ADD_THE_BOUNDARY = (
    "run `stayfixed setup --approval-boundary`, which adds the deny rule and prints the sandbox "
    "settings to set"
)
MAKE_IT_ADMIN = (
    f"set {ENFORCING_SETTINGS} in {{managed}}, a file only an administrator writes: then no "
    f"repository's settings turn the sandbox off, no command runs outside it, and Claude Code does "
    f"not start where it cannot"
)
MAKE_IT_JSON = (
    "make each file the detail names a readable UTF-8 file holding one JSON object, then run "
    "`stayfixed doctor` again"
)
KEEP_THE_FILESYSTEM = (
    "take sandbox.filesystem.disabled out of each file the detail names, or set it to false"
)
NARROW_THE_SETTINGS = (
    "take sandbox.excludedCommands out of each project, local or user file the detail names it in, "
    "and take out each entry of a key it names or spell it as a literal path outside the project, "
    "the trust record's directory and the sandbox's own claude-<digits> temporary directory, of "
    "letters, digits, `.`, `_`, `-` and `/`: `/…` or `~/…` in a sandbox path list and "
    "permissions.additionalDirectories, `//…` or `~/…` in an Edit rule, none of them inside another"
)
SPELL_THE_SETTINGS = (
    "spell each setting the detail names as Claude Code's settings reference gives it: true or "
    "false for a sandbox switch, an object for sandbox, sandbox.filesystem and permissions, and a "
    "list of strings for a list of entries"
)
UNEXCLUDE_MANAGED = (
    "take sandbox.excludedCommands out of {managed} and the drop-ins beside it where an "
    "administrator agrees, since no row can show a command it names keeps clear of the trust record"
)
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


def _read(path: Path, label: str, *, lenient: bool = True) -> _Layer:
    """The settings file at `path` as one JSON object, absent when it names no regular file, and
    unreadable when it is there and is not one. `lenient` reads it as Claude Code reads its
    project, local and user files, past a leading byte-order mark (`harnesses.lenient_settings`);
    managed settings are read strictly, since their reading was not measured."""
    try:
        if not fsops.names_regular_file(path):
            return _Layer(label, None)
        text = fsops.read_regular_bytes(path).decode("utf-8")
    except (OSError, UnicodeDecodeError):
        return _Layer(label, None, unread=True)
    if lenient:
        text = lenient_settings(text)
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
    base = _read(path, str(path), lenient=False)
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
            layer = _read(drop_ins / name, str(drop_ins / name), lenient=False)
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
    """The deny rules `layers` hold. Read leniently, and safely so: a rule the row cannot read is
    a rule it does not count, and a missing rule is a gap."""
    found: set[str] = set()
    for layer in layers:
        found.update(_strings(_table(layer.document, PERMISSIONS, "deny")))
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
PERMISSIONS = "permissions"
EXCLUDED_KEY = f"{SANDBOX}.{EXCLUDED_COMMANDS}"
WIDENING_KEYS = (
    f"{SANDBOX}.{FILESYSTEM}.{ALLOW_WRITE}",
    f"{PERMISSIONS}.allow",
    f"{PERMISSIONS}.{ADDITIONAL_DIRECTORIES}",
)
# The only characters a safe entry may hold. Anything else -- a pattern character, a backslash, a
# NUL, a space, a letter outside ASCII -- makes the entry a gap: the row reads an entry as text and
# never asks the filesystem or a pattern engine about it, since proving what someone else's
# matcher, or an automounted root, makes of it is not this row's to do.
ALLOWED = frozenset(string.ascii_letters + string.digits + "._/~-")
# The components a safe entry may not hold: the empty one (`a//b`, a trailing `/`), `.` and `..`.
NOT_A_NAME = frozenset({"", ".", ".."})
# The start of the component naming the sandbox's own per-user temporary directory: `claude-` and
# the user's id in digits, which Claude Code's environment-variable reference says it appends to
# the base `CLAUDE_CODE_TMPDIR` gives (`/tmp` on macOS, the system's temporary directory on Linux,
# where the variable is not set). Sandboxed commands write there, so they can put a link where an
# entry below it names; such an entry is a gap whatever the base, read as text, which spares the
# row reading `CLAUDE_CODE_TMPDIR` from a shell or a settings file's `env` block.
SANDBOX_TEMP = "claude-"
DIGITS = frozenset(string.digits)
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
    """The strings of a list, and nothing for anything else: for `permissions.deny` alone, where
    reading too little fails closed (`_deny_rules`)."""
    return [item for item in value if isinstance(item, str)] if isinstance(value, list) else []


class _Unread:
    """A value `_value` could not reach: a table on the way to it is there and is not an object."""


UNREAD = _Unread()


def _value(document: Mapping[str, Any] | None, *keys: str) -> object:
    """The value at `keys` in `document`; `None` where it is absent; `UNREAD` where a table on the
    way to it is there and is not an object, so whether it is there cannot be read."""
    value: object = document or {}
    for key in keys:
        if not isinstance(value, dict):
            return UNREAD
        value = value.get(key)
        if value is None:
            return None
    return value


def _listed(document: Mapping[str, Any] | None, *keys: str) -> list[str] | None:
    """The entries of the widening key at `keys`: none where it is absent, its strings where it is
    a list of strings, and `None` -- could not be read -- for any other value that is there,
    including one whose table on the way is not an object. Every widening key is read through
    this, never `_strings`, which would read such a value as empty and so as safe."""
    value = _value(document, *keys)
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        return None
    return list(value)


def _there(value: object) -> bool:
    """Whether `_value` found something there: neither absent nor behind a table it could not
    read, which is a gap of its own."""
    return value is not None and value is not UNREAD


# The tables of the boundary's keys whose shape the row reads: `sandbox`, `sandbox.filesystem` and
# `permissions`, each an object or nothing.
_TABLES: tuple[tuple[str, ...], ...] = ((SANDBOX,), (SANDBOX, FILESYSTEM), (PERMISSIONS,))


def _misshapen(
    layer: _Layer, switches: Sequence[str], tables: Sequence[tuple[str, ...]]
) -> list[str]:
    """The gaps of `layer`'s boundary keys whose value has the wrong shape: each of `tables` that
    is there and is not an object, and each of the sandbox `switches` that is there and is not true
    or false (the module docstring)."""
    found = [(keys, _value(layer.document, *keys)) for keys in tables]
    switched = [(key, _value(layer.document, SANDBOX, key)) for key in switches]
    return [
        *(
            NOT_AN_OBJECT.format(label=layer.label, key=".".join(keys))
            for keys, value in found
            if _there(value) and not isinstance(value, dict)
        ),
        *(
            NOT_A_SWITCH.format(label=layer.label, key=f"{SANDBOX}.{key}")
            for key, value in switched
            if _there(value) and not isinstance(value, bool)
        ),
    ]


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


def _sandbox_temp(part: str) -> bool:
    """Whether the component `part`, folded, names the sandbox's per-user temporary directory
    (`SANDBOX_TEMP`)."""
    name = folded(part)
    digits = name[len(SANDBOX_TEMP) :]
    return name.startswith(SANDBOX_TEMP) and bool(digits) and set(digits) <= DIGITS


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
    record's directory: a literal anchored outside the working directory, below no component
    naming the sandbox's temporary directory, clear under every home a `~/` may mean. A bare
    `Edit` (`None`) allows every edit and never is, and with no record directory to compare
    nothing is."""
    if entry is None or not record:
        return False
    if any(_sandbox_temp(part) for part in entry.split("/")[:-1]):
        return False
    places = _anchored(entry, key, homes)
    if places is None:
        return False
    return all(_clear(folded(place), project, record) for place in places)


def _entries(layer: _Layer) -> dict[str, list[str | None] | None]:
    """`layer`'s entries of each widening key, an `Edit` rule's by its path and a bare `Edit` as
    `None`; `None` for a key whose value could not be read as a list of entries (`_listed`)."""
    allowed = _listed(layer.document, PERMISSIONS, "allow")
    edits: list[str | None] | None = (
        None
        if allowed is None
        else [
            None if entry == EDIT else entry[len(EDIT) + 1 : -1]
            for entry in allowed
            if entry == EDIT or (entry.startswith(f"{EDIT}(") and entry.endswith(")"))
        ]
    )
    written = _listed(layer.document, SANDBOX, FILESYSTEM, ALLOW_WRITE)
    added = _listed(layer.document, PERMISSIONS, ADDITIONAL_DIRECTORIES)
    return {
        WIDENING_KEYS[0]: None if written is None else [*written],
        WIDENING_KEYS[1]: edits,
        WIDENING_KEYS[2]: None if added is None else [*added],
    }


def _widened(
    layer: _Layer, homes: Sequence[Path | None], project: Sequence[str], record: Sequence[str]
) -> list[str]:
    """The gaps `layer`'s widening keys open: one for each key holding an entry not shown safe,
    and one for each key whose value is not a list of entries, which shows nothing safe."""
    return [
        NOT_ENTRIES.format(label=layer.label, key=key)
        if listed is None
        else WIDENED.format(label=layer.label, key=key)
        for key, listed in _entries(layer).items()
        if listed is None or not all(_safe(entry, key, homes, project, record) for entry in listed)
    ]


def _nested(
    layers: Sequence[_Layer], outer: Sequence[_Layer], homes: Sequence[Path | None]
) -> list[str]:
    """The gaps of the entries in `layers` that lie strictly inside another entry of `layers` or
    of `outer`, compared as `_safe` compares, one for each key holding one: an agent's shell writes
    inside the outer one, so what this one names may be a link to the record's directory by the
    time a session reads it. `outer`'s entries, managed settings', are compared against and never
    said. An entry naming the same place as another is not inside it: replacing that place needs
    write access to its parent, which neither gives. Only entries `_anchored` places are compared;
    every other one is a gap of its own already."""
    placed: list[tuple[str | None, list[str]]] = []
    for layer, said in [*((layer, True) for layer in layers), *((layer, False) for layer in outer)]:
        for key, listed in _entries(layer).items():
            for entry in listed or ():
                places = None if entry is None else _anchored(entry, key, homes)
                if places is not None:
                    gap = NESTED.format(label=layer.label, key=key) if said else None
                    placed.append((gap, [folded(place) for place in places]))
    return list(
        dict.fromkeys(
            gap
            for n, (gap, places) in enumerate(placed)
            if gap is not None
            and any(
                place.startswith(other + "/")
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
    agents = load_preset(DEFAULT_PRESET).get("defaults", {}).get("stayfixed", {}).get("agents", [])
    return CLAUDE.name in agents


def _spellings(*paths: Path) -> list[str]:
    """Each of stayfixed's own `paths` as the row compares an entry with it."""
    return [folded(posixpath.normpath(str(path))) for path in paths]


def approval_boundary(context: Context) -> Row:
    """The row (the module docstring says what it reads and how it answers). The home's user
    settings directory is the subject; the one `CLAUDE_CONFIG_DIR` names may only make the answer
    worse (`trust.boundary.user_settings` says why)."""
    approvals = _approvals(context.machine)
    if not approvals[0] and not _lists_claude(context) and not _carries_settings(context.root):
        return Row(SKIP, NOT_LISTED)
    found = user_settings(context.env, context.home)
    chosen = found.chosen
    homes = [home for home in (passwd_home(), context.home) if home is not None]
    where = None if chosen is None else placement(chosen, context.root, homes)
    ignored = (
        (CONFIG_DIR_IN_PROJECT.format(path=clipped(str(chosen))),)
        if where is Placement.INSIDE
        else (CONFIG_DIR_ELSEWHERE.format(path=clipped(str(chosen))),)
        if where is Placement.UNJUDGED
        else ()
    )
    other = (
        _judged(context, chosen, CHOSEN_LABEL, approvals)
        if chosen is not None and where is Placement.OUTSIDE and fsops.is_dir(chosen)
        else None
    )
    if found.directory is not None and fsops.is_dir(found.directory):
        row = _judged(context, found.directory, USER_LABEL, approvals)
        if other is not None and other.status != OK and other.detail != row.detail:
            row = _worsened(
                row,
                other.status,
                JUDGED_WITH.format(label=CHOSEN_LABEL, detail=other.detail),
                other.remedy,
            )
    elif other is not None and chosen is not None:
        row = _worsened(other, WARN, CHOSEN_ALONE.format(path=clipped(str(chosen))), "")
    elif ignored:
        return Row(WARN, "; ".join((NO_CLAUDE_CODE, *ignored)))
    else:
        return Row(SKIP, NO_CLAUDE_CODE)
    return _worsened(row, WARN, *ignored, "") if ignored else row


def _approvals(machine: Path | None) -> tuple[int, str]:
    """How many approvals the machine's trust record holds, and the detail's first part saying so;
    a record that cannot be read is taken to hold one, since it holds every project's."""
    try:
        count = len(recorded(machine))
    except UnreadableTrust:
        return 1, RECORD_UNREAD
    return count, HELD.format(count=count) if count else NONE_HELD


def _worsened(row: Row, status: Status, said: str, remedy: str) -> Row:
    """`row`, its status made `status` where that is worse and never better, with `said` added to
    its detail and `remedy` to its remedies."""
    worse = status if SEVERITY[status] > SEVERITY[row.status] else row.status
    remedies = "; ".join(dict.fromkeys(part for part in (row.remedy, remedy) if part))
    return Row(worse, "; ".join((row.detail, said)), remedies)


def _judged(context: Context, directory: Path, user_label: str, approvals: tuple[int, str]) -> Row:
    """The row's answer with the user's settings read from `directory`, named `user_label`, beside
    `approvals`, the record's count and the detail's first part (`_approvals`)."""
    managed, managed_unread = _managed()
    local = _read(context.root / LOCAL_SETTINGS, LOCAL_SETTINGS)
    project = _read(context.root / PROJECT_SETTINGS, PROJECT_SETTINGS)
    user = _read(directory / USER_FILE, user_label)
    admin = _sandbox(managed, UNSANDBOXED_ALLOWED) is False
    enabled, source = _enabled(managed, local, project, user, admin=admin)

    held, lead = approvals
    path = record_path(context.machine)
    # Where the directory leads is what the harness compares a write against, and the spelling as
    # named is what a tool call may carry, so `setup` writes a rule over each and only those count.
    real = fsops.resolved(path.parent) if path is not None else None
    wanted = record_deny_rules(path)
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
    # A key of the boundary's own with a value of the wrong shape, in each layer the row reads it
    # in (the module docstring): never read as absent.
    misshapen = [
        *_misshapen(managed, (ENABLED, UNSANDBOXED_ALLOWED, FAIL_IF_UNAVAILABLE), _TABLES),
        *(
            gap
            for layer in (local, project)
            for gap in _misshapen(layer, (ENABLED,), _TABLES if not admin else ((SANDBOX,),))
        ),
        *_misshapen(user, (ENABLED,), _TABLES),
    ]
    # A repository's file and the user's widen alike; managed settings' entries only hold others,
    # and their excluded commands only keep the row from green (the module docstring).
    widened: list[str] = []
    for layer in (*repository, user):
        excluded = _listed(layer.document, SANDBOX, EXCLUDED_COMMANDS)
        if excluded is None:
            widened.append(NOT_ENTRIES.format(label=layer.label, key=EXCLUDED_KEY))
        elif excluded:
            widened.append(EXCLUDED.format(label=layer.label))
        widened.extend(_widened(layer, homes, project_root, record))
    widened.extend(_nested((*repository, user), (managed,), homes))
    managed_path = managed_named()
    # One that cannot be read as a list keeps the row from green as a non-empty one does.
    managed_listed = _listed(managed.document, SANDBOX, EXCLUDED_COMMANDS)
    managed_excluded = (
        [MANAGED_EXCLUDED.format(managed=managed_path)]
        if managed_listed is None or managed_listed
        else []
    )
    unexclude = [UNEXCLUDE_MANAGED.format(managed=managed_path)] if managed_excluded else []
    resting = _resting(enabled, source, (managed, user), (local, project), wanted, missing)
    unread = [
        NOT_READ.format(label=layer.label)
        for layer in (*managed_unread, local, project, user)
        if layer.unread
    ]

    unspelled = bool(misshapen) or any(
        listed is None
        for layer in (*repository, user)
        for listed in (
            *_entries(layer).values(),
            _listed(layer.document, SANDBOX, EXCLUDED_COMMANDS),
        )
    )
    if gaps or off or widened or misshapen:
        status: Status = RED if held else WARN
        remedies = [
            *([ADD_THE_BOUNDARY] if gaps or resting else []),
            *([KEEP_THE_FILESYSTEM] if off else []),
            *([NARROW_THE_SETTINGS] if widened else []),
            *([SPELL_THE_SETTINGS] if unspelled else []),
            *unexclude,
        ]
        detail = "; ".join(
            (lead, *gaps, *misshapen, *off, *widened, *resting, *managed_excluded, *unread)
        )
        return Row(status, detail, "; ".join(remedies))
    enforced = _sandbox(managed, FAIL_IF_UNAVAILABLE) is True
    short = [
        *resting,
        *managed_excluded,
        *([] if admin else [NOT_ADMIN]),
        *([] if enforced else [NO_FAIL_CLOSED.format(managed=managed_path)]),
    ]
    if short:
        remedies = [
            *([ADD_THE_BOUNDARY] if resting else []),
            *unexclude,
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
