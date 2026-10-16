"""`doctor`'s `approval-boundary` row: whether a session of this project keeps an agent out of the
trust record.

An approval holds against what a repository commits; against an agent that writes `trust.json`
itself it holds only while the harness stops that write (`trust.boundary` says what stops it, and
how that was measured). So the row reads this project's effective Claude Code settings, in the
harness's own precedence — managed settings with their drop-ins, then the project's
`.claude/settings.local.json`, then its `.claude/settings.json`, then the user's file under
`CLAUDE_CONFIG_DIR` or `~/.claude` — and answers three questions: is the sandbox on for this
project; does a `permissions.deny` rule in the measured spelling cover the record's directory where
it leads, its symbolic links resolved (a rule over the directory as named is accepted beside it and
is not enough alone); and does any setting widen what those two confine to reach the record.

- **Whether the sandbox is on** is the highest layer's `sandbox.enabled`. While the sandbox is
  admin-required, which only managed settings make it (`sandbox.allowUnsandboxedCommands = false`
  there; a user's own does not stop a repository turning the sandbox off), a repository's `false` is
  passed over when managed settings or the user's file set `true`, as Claude Code's sandboxing
  reference says, and stands otherwise.
- **A deny rule** from any layer counts, as the harness adds them up.
- **What widens them**, by the key names the sandboxing reference gives, which were not measured
  here: a repository's non-empty `sandbox.excludedCommands`, which runs commands outside the
  sandbox, and a `sandbox.filesystem.allowWrite` entry, an `Edit(...)` rule in `permissions.allow`
  or a `permissions.additionalDirectories` entry that reaches the record's directory, in the
  project's or the local file while the sandbox is not admin-required (the reference says Claude
  Code ignores them while it is), and in the user's file always, since there one undoes the deny
  rule. **An entry is read as text and nothing else**: no filesystem call and no pattern engine
  touches it. One holding only letters, digits, `.`, `_`, `-`, `~` and `/`, with no `..`
  component, is anchored as the harness anchors it and normalised; it is a gap when it is either
  spelling of the record's directory (as named, and resolved by stayfixed from its own machine
  path), holds it, or lies inside it, compared in NFC and case-folded on macOS. Every other entry
  is not shown either way, and the row warns that it could not tell whether it covers the record:
  there is no class of entry proven safe. A deny rule covers the record only when it is the
  spelling `setup` writes over the resolved directory, compared as text the same way.

**Red only once the machine holds an approval.** With one, a gap is red; with none, it is a
warning, so a default install is never red here. With both settings in force the row still warns
until the sandbox is admin-required, and is green only then. A trust record that cannot be read is
taken to hold approvals, since it holds every project's on the machine. A settings file that is not
JSON is read as absent for its layer and named; the row is never red for that alone, and never green
beside it, since what the harness makes of the file is not known here.

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
import sys
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from stayfixed import fsops
from stayfixed.config.machine import passwd_home
from stayfixed.doctor.model import OK, RED, SKIP, WARN, Context, Row, Status
from stayfixed.errors import Failure
from stayfixed.harnesses import CLAUDE, CLAUDE_DIR
from stayfixed.jsonobject import json_object
from stayfixed.presets import load_preset
from stayfixed.trust.api import (
    CONFIG_DIR_VARIABLE,
    ENABLED,
    MANAGED_DROP_INS,
    SANDBOX,
    UNSANDBOXED_ALLOWED,
    UnreadableTrust,
    deny_rule,
    managed_settings,
    record_path,
    recorded,
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
NO_DENY = (
    "no permissions.deny rule {rule} covers the trust record's directory, so the shell and the "
    "file tools may write the approvals in it"
)
# A setting that widens what the sandbox or the deny rule confines. `label` names the file and
# `key` the setting; the entry itself is not printed, since a repository wrote it.
EXCLUDED = (
    "{label} sets sandbox.excludedCommands, so the commands it names run outside the sandbox, "
    "where nothing stops one writing the trust record"
)
WIDENED = (
    "{label}'s {key} reaches the trust record's directory, so the shell or the file tools may "
    "write the approvals in it past the deny rule"
)
# An entry the row reads only as text and cannot show to reach the record or not: a warning.
UNKNOWN = "could not tell whether {key} in {label} covers the trust record"
# Both in force, and not admin-required: what a repository can still do.
NOT_ADMIN = (
    f"the sandbox is on and the deny rule covers the trust record's directory, but managed "
    f"settings do not make the sandbox admin-required, so a repository's {PROJECT_SETTINGS} or "
    f"{LOCAL_SETTINGS} can turn it off, and an agent can retry a command outside it"
)
GUARDED = (
    "the sandbox is on and admin-required, and {rule} denies writes to the trust record's directory"
)
NOT_READ = "{label} is not JSON and was read as absent"
# The remedies.
ADD_THE_BOUNDARY = (
    "run `stayfixed setup --approval-boundary`, which adds the deny rule and prints the sandbox "
    "settings to set"
)
MAKE_IT_ADMIN = (
    "set sandbox.enabled = true and sandbox.allowUnsandboxedCommands = false in {managed}, a file "
    "only an administrator writes: then no repository's settings turn the sandbox off and no "
    "command runs outside it"
)
MAKE_IT_JSON = "make each file the detail names one JSON object, then run `stayfixed doctor` again"
CHECK_THE_ENTRIES = (
    "check that no entry of a key the detail names reaches the trust record's directory, or spell "
    "each as a literal path of letters, digits, `.`, `_`, `-`, `~` and `/`"
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


def _deny_rules(layers: Sequence[_Layer]) -> set[str]:
    found: set[str] = set()
    for layer in layers:
        permissions = (layer.document or {}).get("permissions")
        rules = permissions.get("deny") if isinstance(permissions, dict) else None
        if isinstance(rules, list):
            found.update(rule for rule in rules if isinstance(rule, str))
    return found


# The keys that widen confinement, as Claude Code's sandboxing reference names them (not measured
# here). While the sandbox is admin-required, the reference says Claude Code ignores these keys in
# a repository's project and local files, from Claude Code 2.1.285 on, which is why the row reads
# them in those files only while it is not; the user's file is read in every case.
EXCLUDED_COMMANDS = "excludedCommands"
FILESYSTEM = "filesystem"
ALLOW_WRITE = "allowWrite"
ADDITIONAL_DIRECTORIES = "additionalDirectories"
WIDENING_KEYS = (
    f"{SANDBOX}.{FILESYSTEM}.{ALLOW_WRITE}",
    "permissions.allow",
    f"permissions.{ADDITIONAL_DIRECTORIES}",
)
# The only characters an entry this row judges may hold. Anything else -- a pattern character, a
# backslash, a NUL, a space, a letter outside ASCII -- makes the entry one it could not tell about:
# the row reads an entry as text and never asks the filesystem or a pattern engine about it, since
# proving what someone else's matcher, or an automounted root, makes of it is not this row's to do.
ALLOWED = frozenset(string.ascii_letters + string.digits + "._/~-")
PARENT = ".."
# The macOS default volume folds case, and its names may arrive composed or decomposed, so a
# spelling is compared there in NFC, case-folded.
CASE_FOLDS = sys.platform == "darwin"
# An `Edit` rule in `permissions.allow`: bare, which allows every edit, or with its path.
EDIT = "Edit"


def _table(document: Mapping[str, Any] | None, *keys: str) -> object:
    value: object = document or {}
    for key in keys:
        value = value.get(key) if isinstance(value, dict) else None
    return value


def _strings(value: object) -> list[str]:
    return [item for item in value if isinstance(item, str)] if isinstance(value, list) else []


def _folded(text: str) -> str:
    """`text` as the row compares it: as it is, or in NFC and case-folded where names fold."""
    return unicodedata.normalize("NFC", text).casefold() if CASE_FOLDS else text


def _normalised(entry: str, root: Path, home: Path | None) -> str | None:
    """`entry` anchored and normalised as text, or `None` for one the row does not judge.

    `//x` is `/x`; `~/x` is under the home; `/x` is under the session's working directory, the
    project root; `./x` and `x` are under the project root. No filesystem call is made."""
    if not entry or not set(entry) <= ALLOWED or PARENT in entry.split("/"):
        return None
    if entry.startswith("//"):
        anchored = entry[1:]
    elif entry == "~" or entry.startswith("~/"):
        if home is None:
            return None
        anchored = f"{home}/{entry[2:]}"
    elif entry.startswith("~"):
        return None
    elif entry.startswith("/"):
        anchored = f"{root}{entry}"
    else:
        anchored = f"{root}/{entry.removeprefix('./')}"
    return _folded(posixpath.normpath(anchored))


def _proven(entry: str | None, root: Path, home: Path | None, spellings: Sequence[str]) -> bool:
    """Whether `entry` is shown, as text, to be one of the record directory's `spellings`, to hold
    it, or to lie inside it; a bare `Edit` (`None`) allows every edit and always is."""
    if entry is None:
        return True
    place = _normalised(entry, root, home)
    if place is None:
        return False
    above = place.rstrip("/") + "/"
    return any(
        place == held or held.startswith(above) or place.startswith(held + "/")
        for held in spellings
    )


def _widened(
    layer: _Layer, root: Path, home: Path | None, spellings: Sequence[str]
) -> tuple[list[str], list[str]]:
    """What `layer`'s widening keys do to the record directory, named by its `spellings` (folded,
    as stayfixed computed them from its own machine path): the keys with an entry shown to reach
    it, and the keys with an entry the row could not tell about."""
    allowed = _strings(_table(layer.document, "permissions", "allow"))
    entries: dict[str, list[str | None]] = {
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
    proven: list[str] = []
    unknown: list[str] = []
    for key, listed in entries.items():
        if any(_proven(entry, root, home, spellings) for entry in listed):
            proven.append(WIDENED.format(label=layer.label, key=key))
        elif listed:
            unknown.append(UNKNOWN.format(label=layer.label, key=key))
    return proven, unknown


def _deny_covers(rules: set[str], resolved: str) -> bool:
    """Whether a deny rule is the spelling `setup` writes over the resolved record directory,
    compared as text after the same normalisation; no other rule is read as covering it."""
    head, tail = "Edit(/", "/**)"
    return any(
        rule.startswith(head + "/")
        and rule.endswith(tail)
        and "\0" not in rule
        and _folded(posixpath.normpath(rule[len(head) : -len(tail)])) == resolved
        for rule in rules
    )


def _carries_settings(root: Path) -> bool:
    """Whether the project carries a Claude Code settings file, a link to one included."""
    return any(
        fsops.exists(root / relative) or fsops.is_symlink(root / relative)
        for relative in (PROJECT_SETTINGS, LOCAL_SETTINGS)
    )


def _user_directory(context: Context) -> tuple[Path | None, str]:
    """Where the user's settings live, and how the row names the file, or `None` for no home."""
    chosen = context.env.get(CONFIG_DIR_VARIABLE)
    if chosen:
        return Path(chosen), f"${CONFIG_DIR_VARIABLE}/{USER_FILE}"
    home = context.home if context.home is not None else passwd_home()
    if home is None:
        return None, f"~/{PROJECT_SETTINGS}"
    return home / CLAUDE_DIR, f"~/{PROJECT_SETTINGS}"


def _lists_claude(context: Context) -> bool:
    if context.config is not None:
        return CLAUDE.name in context.config.stayfixed.agents
    agents = load_preset("recommended").get("defaults", {}).get("stayfixed", {}).get("agents", [])
    return CLAUDE.name in agents


def approval_boundary(context: Context) -> Row:
    """The row (the module docstring says what it reads and how it answers)."""
    if not _lists_claude(context) and not _carries_settings(context.root):
        return Row(SKIP, NOT_LISTED)
    directory, user_label = _user_directory(context)
    if directory is None or not fsops.is_dir(directory):
        return Row(SKIP, NO_CLAUDE_CODE)
    managed, managed_unread = _managed()
    local = _read(context.root / LOCAL_SETTINGS, LOCAL_SETTINGS)
    project = _read(context.root / PROJECT_SETTINGS, PROJECT_SETTINGS)
    user = _read(directory / USER_FILE, user_label)
    admin = _sandbox(managed, UNSANDBOXED_ALLOWED) is False
    # While admin-required, a repository's `false` gives way to an owner's `true` and to nothing
    # else (Claude Code's sandboxing reference).
    owners_true = _sandbox(managed, ENABLED) is True or _sandbox(user, ENABLED) is True

    enabled: object = None
    source: _Layer | None = None
    # Highest first, each with whether the repository wrote it.
    for layer, repository in ((managed, False), (local, True), (project, True), (user, False)):
        value = _sandbox(layer, ENABLED)
        if not isinstance(value, bool):
            continue
        if value is False and admin and repository and owners_true:
            continue
        enabled, source = value, layer
        break

    try:
        held = len(recorded(context.machine))
        lead = HELD.format(count=held) if held else NONE_HELD
    except UnreadableTrust:
        held, lead = 1, RECORD_UNREAD

    path = record_path(context.machine)
    # Where the directory leads is what the harness compares a write against, so only a rule over
    # that covers it; a rule over the directory as named may stand beside it.
    real = fsops.resolved(path.parent) if path is not None else None
    rule = deny_rule(real) if real is not None else NO_RECORD_RULE
    rules = _deny_rules((managed, local, project, user))
    covered = real is not None and _deny_covers(rules, _folded(posixpath.normpath(str(real))))
    home = context.home if context.home is not None else passwd_home()
    # Both spellings of the record directory, computed from stayfixed's own machine path.
    spellings = (
        [_folded(posixpath.normpath(str(where))) for where in (path.parent, real)]
        if path is not None and real is not None
        else []
    )
    unknown: list[str] = []

    gaps: list[str] = []
    if enabled is not True:
        gaps.append(
            TURNED_OFF.format(label=source.label)
            if enabled is False and source is not None
            else NO_SANDBOX
        )
    if not covered:
        gaps.append(NO_DENY.format(rule=rule))
    if not admin:
        for layer in (local, project):
            if _strings(_sandbox(layer, EXCLUDED_COMMANDS)):
                gaps.append(EXCLUDED.format(label=layer.label))
            shown, untold = _widened(layer, context.root, home, spellings)
            gaps.extend(shown)
            unknown.extend(untold)
    shown, untold = _widened(user, context.root, home, spellings)
    gaps.extend(shown)
    unknown.extend(untold)
    unread = [
        NOT_READ.format(label=layer.label)
        for layer in (*managed_unread, local, project, user)
        if layer.unread
    ]

    managed_path = managed_settings()
    if gaps:
        status: Status = RED if held else WARN
        return Row(status, "; ".join((lead, *gaps, *unknown, *unread)), ADD_THE_BOUNDARY)
    if not admin:
        remedy = MAKE_IT_ADMIN.format(managed=managed_path or NO_MANAGED_PATH)
        return Row(WARN, "; ".join((lead, NOT_ADMIN, *unknown, *unread)), remedy)
    detail = "; ".join((lead, GUARDED.format(rule=rule), *unknown, *unread))
    remedies = [*([CHECK_THE_ENTRIES] if unknown else []), *([MAKE_IT_JSON] if unread else [])]
    return Row(WARN, detail, "; ".join(remedies)) if remedies else Row(OK, detail)
