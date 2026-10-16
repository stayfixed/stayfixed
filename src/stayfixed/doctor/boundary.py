"""`doctor`'s `approval-boundary` row: whether a session of this project keeps an agent out of the
trust record.

An approval holds against what a repository commits; against an agent that writes `trust.json`
itself it holds only while the harness stops that write (`trust.boundary` says what stops it, and
how that was measured). So the row reads this project's effective Claude Code settings, in the
harness's own precedence — managed settings with their drop-ins, then the project's
`.claude/settings.local.json`, then its `.claude/settings.json`, then the user's file under
`CLAUDE_CONFIG_DIR` or `~/.claude` — and answers two questions: is the sandbox on for this project,
and does a `permissions.deny` rule in the measured spelling cover the record's directory. A deny
rule from any layer counts, as the harness adds them up. Whether the sandbox is on is the highest
layer's `sandbox.enabled`, except that a repository's `false` is passed over while the sandbox is
admin-required, which only managed settings make it (`sandbox.allowUnsandboxedCommands = false`
there; a user's own does not stop a repository turning the sandbox off).

**Red only once the machine holds an approval.** With one, a gap is red; with none, it is a
warning, so a default install is never red here. With both settings in force the row still warns
until the sandbox is admin-required, and is green only then. A trust record that cannot be read is
taken to hold approvals, since it holds every project's on the machine. A settings file that is not
JSON is read as absent for its layer and named; the row is never red for that alone, and never green
beside it, since what the harness makes of the file is not known here.

**Skipped** on a machine with no Claude Code user settings directory, and for a project whose
`[stayfixed] agents` does not list `claude`; with no `stayfixed.toml`, the preset's agents apply.

Nothing a repository wrote is printed: the files are named by the labels a reader types, the deny
rule and the managed path are stayfixed's own and the machine's, and no value is quoted.
"""

from __future__ import annotations

import os
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
    "[stayfixed] agents does not list claude, so no session of this project runs where the sandbox "
    "and the deny rule apply"
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
    if not _lists_claude(context):
        return Row(SKIP, NOT_LISTED)
    directory, user_label = _user_directory(context)
    if directory is None or not fsops.is_dir(directory):
        return Row(SKIP, NO_CLAUDE_CODE)
    managed, managed_unread = _managed()
    local = _read(context.root / LOCAL_SETTINGS, LOCAL_SETTINGS)
    project = _read(context.root / PROJECT_SETTINGS, PROJECT_SETTINGS)
    user = _read(directory / USER_FILE, user_label)
    admin = _sandbox(managed, UNSANDBOXED_ALLOWED) is False

    enabled: object = None
    source: _Layer | None = None
    # Highest first, each with whether the repository wrote it.
    for layer, repository in ((managed, False), (local, True), (project, True), (user, False)):
        value = _sandbox(layer, ENABLED)
        if not isinstance(value, bool):
            continue
        if value is False and admin and repository:
            # Admin-required: a repository's `false` is ignored (measured).
            continue
        enabled, source = value, layer
        break

    try:
        held = len(recorded(context.machine))
        lead = HELD.format(count=held) if held else NONE_HELD
    except UnreadableTrust:
        held, lead = 1, RECORD_UNREAD

    path = record_path(context.machine)
    # The directory as the record's path names it, and where it leads: a rule over either covers it.
    rules = (
        {deny_rule(path.parent), deny_rule(path.parent.resolve())} if path is not None else set()
    )
    rule = deny_rule(path.parent) if path is not None else NO_RECORD_RULE
    covered = bool(rules & _deny_rules((managed, local, project, user)))

    gaps: list[str] = []
    if enabled is not True:
        gaps.append(
            TURNED_OFF.format(label=source.label)
            if enabled is False and source is not None
            else NO_SANDBOX
        )
    if not covered:
        gaps.append(NO_DENY.format(rule=rule))
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
