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
  rule. An entry this row cannot judge — a pattern holding anything but `*` and `**` — is taken to
  reach it, and said so. A path entry's leading `/` is read both as absolute and as the project's,
  since the reference was not measured on it; an `Edit` rule's is the project's, as measured.

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
import re
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
UNJUDGED = (
    "{label}'s {key} holds an entry this row could not tell about (a pattern holding more than * "
    "and **), so it is taken to reach the trust record's directory"
)
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
NO_MANAGED_PATH = "the managed settings file"
# The rule's place in a sentence on a machine with no home for a trust record: the password
# database lists none for this user, and `--machine` was not given.
NO_RECORD_RULE = "Edit(//<the trust record's directory>/**)"
# The machine file's name beside the record, which the deny rule covers too.
_MACHINE_FILE = "config.toml"


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


# The keys that widen confinement, as Claude Code's sandboxing reference names them.
EXCLUDED_COMMANDS = "excludedCommands"
FILESYSTEM = "filesystem"
ALLOW_WRITE = "allowWrite"
ADDITIONAL_DIRECTORIES = "additionalDirectories"
WIDENING_KEYS = (
    f"{SANDBOX}.{FILESYSTEM}.{ALLOW_WRITE}",
    "permissions.allow",
    f"permissions.{ADDITIONAL_DIRECTORIES}",
)
# A pattern character this row does not evaluate: anything but `*` and `**` is "could not tell".
_UNJUDGEABLE = re.compile(r"[?\[\]{}!\\]")
# An `Edit` rule, bare (every edit) or with its path in parentheses.
_EDIT_RULE = re.compile(r"\AEdit(?:\((.*)\))?\Z", re.DOTALL)


def _table(document: Mapping[str, Any] | None, *keys: str) -> object:
    value: object = document or {}
    for key in keys:
        value = value.get(key) if isinstance(value, dict) else None
    return value


def _strings(value: object) -> list[str]:
    return [item for item in value if isinstance(item, str)] if isinstance(value, list) else []


def _glob(pattern: str) -> re.Pattern[str]:
    """`pattern`, an absolute path that may hold `*` and `**`, as a regular expression."""
    parts = re.split(r"(\*\*|\*)", pattern)
    body = "".join(
        ".*" if part == "**" else "[^/]*" if part == "*" else re.escape(part) for part in parts
    )
    return re.compile(body)


def _matches(pattern: str, targets: Sequence[Path]) -> bool:
    """Whether the absolute `pattern` names one of `targets` or a directory above one, which is
    every path under it."""
    compiled = _glob(pattern.rstrip("/") or "/")
    return any(
        compiled.fullmatch(str(candidate))
        for target in targets
        for candidate in (target, *target.parents)
    )


def _anchored(entry: str, root: Path, home: Path | None, *, rule: bool) -> list[str] | None:
    """Every absolute pattern `entry` may stand for, or `None` for one with no home to read `~` by.

    `//x` is absolute and `~/x` under the home; a rule's `/x` is the project's, as measured, and a
    path entry's is read both ways; anything else is the project's."""
    if entry.startswith("//"):
        return [entry[1:]]
    if entry == "~" or entry.startswith("~/"):
        return None if home is None else [f"{home}/{entry[2:]}"]
    if entry.startswith("/"):
        project = f"{root}{entry}"
        return [project] if rule else [entry, project]
    return [f"{root}/{entry.removeprefix('./')}"]


def _reaches(
    entry: str, root: Path, home: Path | None, targets: Sequence[Path], *, rule: bool
) -> bool | None:
    """Whether `entry` reaches one of `targets`; `None` when this row cannot tell."""
    if _UNJUDGEABLE.search(entry):
        return None
    patterns = _anchored(entry, root, home, rule=rule)
    if patterns is None:
        return None
    return any(_matches(pattern, targets) for pattern in patterns)


def _widened(layer: _Layer, root: Path, home: Path | None, targets: Sequence[Path]) -> list[str]:
    """The gaps `layer` opens towards `targets`: each widening key that reaches one, or that holds
    an entry this row cannot judge."""
    found: list[str] = []
    entries = {
        WIDENING_KEYS[0]: [
            (entry, False)
            for entry in _strings(_table(layer.document, SANDBOX, FILESYSTEM, ALLOW_WRITE))
        ],
        WIDENING_KEYS[1]: [
            (match.group(1), True)
            for entry in _strings(_table(layer.document, "permissions", "allow"))
            if (match := _EDIT_RULE.match(entry))
        ],
        WIDENING_KEYS[2]: [
            (entry, False)
            for entry in _strings(_table(layer.document, "permissions", ADDITIONAL_DIRECTORIES))
        ],
    }
    for key, listed in entries.items():
        # A bare `Edit` allows every edit, and reaches everything.
        answers = [
            True if path is None else _reaches(path, root, home, targets, rule=rule)
            for path, rule in listed
        ]
        if any(answer is True for answer in answers):
            found.append(WIDENED.format(label=layer.label, key=key))
        elif any(answer is None for answer in answers):
            found.append(UNJUDGED.format(label=layer.label, key=key))
    return found


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
    covered = real is not None and deny_rule(real) in _deny_rules((managed, local, project, user))
    # The record and the machine file beside it, in both spellings, for what widens.
    machine_name = context.machine.name if context.machine is not None else _MACHINE_FILE
    targets = (
        [where / name for where in {path.parent, real} for name in (path.name, machine_name)]
        if path is not None and real is not None
        else []
    )
    home = context.home if context.home is not None else passwd_home()

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
            gaps.extend(_widened(layer, context.root, home, targets))
    gaps.extend(_widened(user, context.root, home, targets))
    unread = [
        NOT_READ.format(label=layer.label)
        for layer in (*managed_unread, local, project, user)
        if layer.unread
    ]

    managed_path = managed_settings()
    if gaps:
        status: Status = RED if held else WARN
        return Row(status, "; ".join((lead, *gaps, *unread)), ADD_THE_BOUNDARY)
    if not admin:
        remedy = MAKE_IT_ADMIN.format(managed=managed_path or NO_MANAGED_PATH)
        return Row(WARN, "; ".join((lead, NOT_ADMIN, *unread)), remedy)
    detail = "; ".join((lead, GUARDED.format(rule=rule), *unread))
    return Row(WARN, detail, MAKE_IT_JSON) if unread else Row(OK, detail)
