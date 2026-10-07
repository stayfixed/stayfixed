"""What attaching would add to this project's local settings, and where it may read it from.

**Two sources, and the third one is the defect.** The inputs are `<overlay>/common/claude/` and
`<overlay>/projects/<name>/claude/` — the machine owner's own files, in the repository the
machine file anchors. `.claude/settings.json` is read for *nothing*: it is committed, so it is
repository-controlled, and committed settings that would widen a permission are never merged.
`.claude/settings.local.json` is read, and only to subtract: a rule the project already carries
is not something this attach would add.

**The two halves of the diff are not symmetric.** A hook entry carries `# stayfixed:<id>`
inside its command string, so it has an in-band witness that survives the file being edited by
hand — `scaffold.owned_ids` reads them back. A `permissions.allow` string cannot carry one:
`scaffold.mark` appends to a *command*, and `scaffold.entries.unmarked` walks
`groups → hooks → command`. So an allow rule has exactly one witness, the ledger `write.py`
keeps, and this module numbers hook ids per entry rather than sharing one — `owned_ids` is a
`dict[str, str]`, so one id for N entries yields one provenance row and the same id under two
events keeps only the last.

**What may be printed.** `added_allow` and `added_hooks` are built out of the overlay, which is
the owner's own repository, so a command may show them — and must, since a diff nobody reads is
not a gate. `already_present` comes out of `.claude/settings.local.json`, which a hostile clone
*can* commit, so it is repository-authored: this module carries the strings so a caller can
subtract with them, and `attach.check` reports only how many there were.
"""

from __future__ import annotations

import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from stayfixed import fsops
from stayfixed.attach.binding import Binding, cannot_exist
from stayfixed.errors import Failure
from stayfixed.fsops import read_regular_text, said
from stayfixed.harnesses import CLAUDE
from stayfixed.jsonobject import WRITTEN_PAST
from stayfixed.memory.api import PROJECTS
from stayfixed.overlay.api import COMMON_CLAUDE, COMMON_CODEX
from stayfixed.scaffold import (
    EntriesError,
    ParserLimitError,
    judged_entries,
    mark,
    settings_object,
    settings_text,
)

# The project-local file `attach` owns outright, as the harness registry names it: the one file
# Claude Code reads that a repository keeps out of git. `.claude/settings.json` beside it is the
# committed one and is never read.
(LOCAL_SETTINGS,) = CLAUDE.local_settings
PERMISSIONS_FILE = "permissions.json"
HOOKS_FILE = "hooks.json"
# The per-harness subdirectory of a project's own share of the overlay.
PROJECT_CLAUDE = "claude"
PROJECT_CODEX = "codex"
# `stayfixed:overlay-<event>-<n>`: one id per entry, for the reason in the module docstring.
ENTRY_PREFIX = "overlay"
# Where Codex reads standing instructions.
CODEX_RULES = ".codex/rules"


@dataclass(frozen=True)
class PermissionDiff:
    """What `attach` would add, and what is already there.

    `added_hooks` holds the *marked* command strings, which is what a reader has to see: the
    marker is the key the merge is done on, and an entry whose marker changed is a different
    entry however familiar its command looks.
    """

    added_allow: tuple[str, ...]
    added_hooks: tuple[str, ...]
    already_present: tuple[str, ...]

    @property
    def widens(self) -> bool:
        """Whether applying this diff would grant a capability the project does not have.

        The `--yes` gate on the write is on *this*, not on the command: an overlay with no
        allow rules and no hook entries — the state of a freshly created one — must still link
        memory with no flag, or the flag becomes something people pass reflexively.
        """
        return bool(self.added_allow or self.added_hooks)


def settings_document(text: str) -> dict[str, Any]:
    """The local settings file as an object, refusing a shape the merge could not read back.

    `write.py` adds allow rules to this document and `scaffold.apply_entries` rewrites the hook
    table in it, so both halves have to agree about what a readable document is — and a shape
    this cannot read is refused rather than filtered, because what a filter drops here is
    somebody's own setting and nothing would say it went.
    """
    return settings_object(text, LOCAL_SETTINGS)


def _read(path: Path, *, share: Path | None = None, label: str | None = None) -> str:
    """A file's text, or an empty string when there is no such file.

    `label` is how a refusal names the file, for one the project names: the project's own
    `.claude/settings.local.json` is named as such and never by the machine's absolute path,
    as `attach.write` names `.gitignore` and the ledger. An overlay source keeps its path.

    `share` is for the overlay's sources under `projects/<name>/` and nothing else, and names that
    directory: a path its spelling rules out (`binding.cannot_exist`) is a file the overlay does not
    have when `project.name` picks out no directory there (`_names_no_directory`), because the one
    free part of that spelling is the name and a repository chooses it. Every other fault is the
    overlay failing to answer and stays a `Failure`, which `doctor` reports as a warning: no
    permission, a directory where the file goes, and a path ruled out *below* a directory the name
    does pick out -- the name holds no `/`, so a file where `claude/` goes is the owner's own
    state, and read as absent it granted nothing: the owner's entries read red and `attach`
    stripped them. So is any fault under `common/`, whose spelling the overlay alone chooses. The
    project's own `.claude/` is never read this way: a `.claude` that is a file has to stop
    `attach` before it writes, and read as an empty settings file it would stop only at the write
    of that file.
    """
    try:
        # A regular file only (`fsops.read_regular_text`): `.claude/settings.local.json` is a path
        # a clone can commit, and a link there to `/dev/zero` read until memory ran out, one to a
        # FIFO waited for a writer. Anything else is a file that cannot be read.
        return read_regular_text(path)
    except FileNotFoundError:
        return ""
    except OSError as exc:
        if share is not None and cannot_exist(exc) and _names_no_directory(share):
            return ""
        raise Failure(f"{label or path} cannot be read: {said(exc)}") from exc
    except UnicodeDecodeError:
        raise Failure(f"{label or path} is not UTF-8 text") from None


def _names_no_directory(share: Path) -> bool:
    """Whether `share`, the overlay's `projects/<name>`, is no directory, so nothing below it is
    the owner's and a path through it that cannot exist is one the overlay has no file at.

    Asked of the share itself because `cannot_exist` says only that *some* component of a path is
    not a directory or is too long, never which. Only the share's own answer is about the name,
    and any component below a share that is a directory is the owner's own state. Whatever is
    absent counts, `projects/` or the share: nothing is below a directory that is not there, so
    nothing there is the owner's. An overlay need not keep `projects/` at all, and a long name
    under a long overlay root can put a file under an absent share past the longest path while
    the share itself is not.

    Every caller reaches this past a share that is absent or a directory, so those are the two
    answers that decide anything: `attach` and `--check` refuse any other share above their reads
    (`binding.refuse_unless_share_can_exist`), and `doctor` opens `projects/<name>/` only for a
    binding whose record it has just read there. So a `projects/` that is a file is not told apart
    from a share a file holds: no caller can reach either.
    """
    try:
        mode = share.stat().st_mode
    except FileNotFoundError:
        # No share, or no `projects/` above it: the overlay has no directory for this project.
        return True
    except OSError as exc:
        return cannot_exist(exc)
    return not stat.S_ISDIR(mode)


def allow_list(raw: dict[str, Any], label: str) -> list[str]:
    """The `permissions.allow` list of a settings document `settings_object` read, or a refusal.

    **The one reader of that list**, for `--check` and for the real run alike: `diff_permissions`
    reads every source and the project's own file through it, and `write.py` reads the file it
    merges into and withdraws from through it, so `--check` refuses exactly the documents the real
    run refuses. Two copies of it disagreed about `null`: one read a `null` `permissions` or
    `allow` as no rules, the other refused it, so `--check` exited 0 promising a rule for a file
    the real run then refused. A key that is absent is no rules; a key that is there must hold an
    object, and then a list of strings, and `null` is a value that is neither. A shape this cannot
    read is a refusal and never a filter, for the reason `_hook_groups` gives. `label` names the
    file in the refusal.
    """
    if "permissions" not in raw:
        return []
    permissions = raw["permissions"]
    if not isinstance(permissions, dict):
        raise EntriesError(f"{label}: 'permissions' is not an object")
    if "allow" not in permissions:
        return []
    allow = permissions["allow"]
    if not isinstance(allow, list) or not all(isinstance(rule, str) for rule in allow):
        raise EntriesError(f"{label}: 'permissions.allow' is not a list of strings")
    return list(allow)


def _allow_rules(document: str, path: Path) -> tuple[str, ...]:
    """The `permissions.allow` list of one settings-shaped document, read by `allow_list`."""
    label = str(path)
    return tuple(allow_list(settings_object(document, label), label))


def _hook_groups(path: Path, *, share: Path | None) -> dict[str, list[dict[str, Any]]]:
    """`event -> groups` out of a `hooks.json`-shaped document, refusing a shape it cannot read.

    A shape this cannot read is a refusal and never a filter, for `scaffold.entries`' own
    reason: what is dropped silently here is an entry the owner put in their overlay on
    purpose, and nothing would say it never arrived. `share` is `_read`'s.
    """
    hooks = settings_object(_read(path, share=share), str(path)).get("hooks", {})
    if not isinstance(hooks, dict):
        raise EntriesError(f"{path}: 'hooks' is not an object")
    found: dict[str, list[dict[str, Any]]] = {}
    for event, groups in hooks.items():
        if not isinstance(groups, list) or not all(isinstance(g, dict) for g in groups):
            raise EntriesError(f"{path}: 'hooks.{event}' is not a list of entry groups")
        found[str(event)] = [dict(g) for g in groups]
    return found


def codex_rules(binding: Binding) -> tuple[tuple[str, Path], ...]:
    """Every standing-rule file `attach` would place under `.codex/rules/`, as (target, source).

    Enumeration here, copying in `write.py`, because `--check`'s whole promise is "read it
    before the real run" and `docs/cli.md` lists `.codex/rules/` under **Writes**: half a write
    that never appears in the report makes that promise false. A file Codex reads as standing
    instruction is exactly the kind of thing an owner wants named before it lands.

    This is **reporting and not gating**, and the distinction is deliberate. The `--yes` gate is
    about widening a *permission*, which only the overlay may grant and never a file the repository
    commits; adding standing rules is the machine owner's to do, and the overlay is the machine
    owner's own artifact — so a rule file does not make `widens` true, and `widens` keeps meaning
    what its name says.

    This project's own `codex/` is read second, so a file it shares a name with in `common/` is
    the one that lands; the pair is returned rather than two lists so the caller cannot pair
    them up differently from the way the write does.
    """
    found: dict[str, Path] = {}
    for source in (
        binding.overlay / COMMON_CODEX,
        binding.overlay / PROJECTS / binding.project / PROJECT_CODEX,
    ):
        if not source.is_dir():
            continue
        for rule in sorted(source.iterdir()):
            if rule.is_file() and not rule.name.startswith("."):
                found[f"{CODEX_RULES}/{rule.name}"] = rule
    return tuple(found.items())


def _claude_sources(
    binding: Binding, name: str
) -> tuple[tuple[Path, Path | None], tuple[Path, Path | None]]:
    """The two per-harness files this diff reads, common first, this project's second, each with
    the directory `project.name` picks for it, when it has one (`_read`'s `share`)."""
    share = binding.overlay / PROJECTS / binding.project
    return (
        (binding.overlay / COMMON_CLAUDE / name, None),
        (share / PROJECT_CLAUDE / name, share),
    )


def overlay_entries(binding: Binding) -> dict[str, list[dict[str, Any]]]:
    """The hook entries the overlay would install, each command carrying its own marker id.

    Shaped exactly as `scaffold.apply_entries` wants its `wanted` argument, because that is the
    merge — this area does not own one. Numbering runs per event across both sources in read
    order, so a second attach against an unchanged overlay produces the identical ids and the
    merge is a no-op.
    """
    return _numbered(_claude_sources(binding, HOOKS_FILE))


def common_entries(overlay: Path) -> dict[str, list[dict[str, Any]]]:
    """`overlay_entries` for `common/` alone, which never opens anything under `projects/`.

    For a caller that may not take any project's grants (`doctor`, for a checkout the overlay's
    record does not bind, or whose record it cannot read), and asked of the overlay root rather
    than of a `Binding`, because deciding a binding opens the record such a caller may not lean
    on. `common/` is read first by `overlay_entries` too, so this is exactly the leading part of
    its answer, with the same ids.
    """
    return _numbered(((overlay / COMMON_CLAUDE / HOOKS_FILE, None),))


def _numbered(
    sources: tuple[tuple[Path, Path | None], ...],
) -> dict[str, list[dict[str, Any]]]:
    """The hook entries in `sources`, read in order, each command marked with its own id."""
    wanted: dict[str, list[dict[str, Any]]] = {}
    seen: dict[str, int] = {}
    for source, share in sources:
        for event, groups in _hook_groups(source, share=share).items():
            for group in groups:
                # Absent is no entries; `null`, or any other value that is not a list, is
                # refused, as `allow_list` refuses one where its list goes.
                entries = group.get("hooks", [])
                if not isinstance(entries, list):
                    raise EntriesError(f"{source}: an entry group's 'hooks' is not a list")
                marked: list[dict[str, Any]] = []
                for entry in entries:
                    command = entry.get("command") if isinstance(entry, dict) else None
                    if not isinstance(command, str):
                        raise EntriesError(f"{source}: an entry under {event} has no command")
                    seen[event] = seen.get(event, 0) + 1
                    entry_id = f"{ENTRY_PREFIX}-{event}-{seen[event]}"
                    marked.append({**entry, "command": mark(command, entry_id)})
                if marked:
                    wanted.setdefault(event, []).append({**group, "hooks": marked})
    return wanted


def marked_commands(wanted: dict[str, list[dict[str, Any]]]) -> list[tuple[str, str]]:
    """Every marked command in `overlay_entries`' or `common_entries`' answer, with its event, in
    its order: the grants flattened once, for the diff and the ledger, which each ask only for
    commands. Each is a string, because `_numbered` refuses an entry without one. `doctor` asks
    where each one sits too, and reads that through `scaffold.wanted_placements`."""
    return [
        (event, entry["command"])
        for event, groups in wanted.items()
        for group in groups
        for entry in group["hooks"]
    ]


def local_document(root: Path) -> str:
    """The project's own `settings.local.json`, or an empty string when it has none."""
    return _read(root / LOCAL_SETTINGS, label=LOCAL_SETTINGS)


def _commands(document: str, label: str) -> set[str]:
    """Every hook command already in a settings document, whoever wrote it, or a refusal.

    Read by the strict walk (`scaffold.judged_entries`, not lenient), which refuses every shape
    `scaffold.apply_entries` refuses when the real run merges into this document: a `hooks` that
    is not an object, an event that is not a list of objects, a group whose `hooks` is not a list
    of objects, `null` in any of those places included. This filtered them, so `--check` exited 0
    for a file the real run then refused. A refusal names the file by `label`; one past a limit of
    the parser keeps its own kind and words.
    """
    try:
        walked = judged_entries(document, lenient=False)
    except ParserLimitError:
        raise
    except EntriesError as exc:
        raise EntriesError(f"{label}: {exc}") from None
    return {placed.command for _, placed in walked.entries}


# Room for the one key the settings fallback adds to the text `attach` writes back after the merge:
# the key's name and a path, and no path a filesystem resolves passes 4,096 bytes.
_FALLBACK_ROOM = 8 * 1024


def _refuse_unless_written_back(document: str) -> None:
    """Refuse a settings document whose write-back the next read would refuse.

    `attach` writes the file back indented -- the merge, and the settings fallback after the
    links -- and a short document many levels deep grows by its depth on every line: 12 KB six
    thousand lists deep is 72 MB, past `fsops.REGULAR_READ_LIMIT`, so the read after the write
    refused, after every other write of the run, and so did every `detach` after it. Asked where
    `attach` and `--check` both read the file, so the two answer alike and `attach` answers before
    its first write; and of every document, whether or not this run writes it back, since a later
    run that adds one rule would.
    """
    text = settings_text(settings_document(document), LOCAL_SETTINGS)
    if len(text) + _FALLBACK_ROOM > fsops.REGULAR_READ_LIMIT:
        raise ParserLimitError(f"{LOCAL_SETTINGS} {WRITTEN_PAST}")


def diff_permissions(root: Path, binding: Binding) -> PermissionDiff:
    """What attaching `binding` would add to `root`, without writing a byte."""
    # This line is the whole of the committed-settings rule in the module docstring:
    # `.claude/settings.json` sits one name away from both sources and is not on it.
    sources = _claude_sources(binding, PERMISSIONS_FILE)
    granted = [
        rule
        for source, share in sources
        for rule in _allow_rules(_read(source, share=share), source)
    ]
    document = local_document(root)
    _refuse_unless_written_back(document)
    # Named by its project path, as every refusal of the project's own settings file is.
    held = set(_allow_rules(document, Path(LOCAL_SETTINGS)))
    present = _commands(document, LOCAL_SETTINGS)
    added_allow = tuple(dict.fromkeys(rule for rule in granted if rule not in held))
    already = tuple(dict.fromkeys(rule for rule in granted if rule in held))
    added_hooks = tuple(
        command
        for _, command in marked_commands(overlay_entries(binding))
        if command not in present
    )
    return PermissionDiff(added_allow, added_hooks, already)
