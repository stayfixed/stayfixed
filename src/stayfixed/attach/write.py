"""What `stayfixed attach` actually writes, in the order the refusals have to happen in.

**No hook entry goes into `settings.local.json`.** Claude Code rewrites that file whole and adds
allow rules of its own to it, so no in-band marker survives there. The overlay's hook entries,
skills and agents are rendered into a local plugin named by the binding id (`attach.render`),
re-rendered in place and installed on every run, both `claude plugin` calls being idempotent; the
file keeps only the allow rules the ledger names, and the plugin's `enabledPlugins` and
`extraKnownMarketplaces` entries, which Claude Code writes. A checkout an earlier release attached
holds the entries that release merged, named by its ledger's `entries`: `attach` takes back
exactly those, through `scaffold.withdraw_entries`, and records none.

*Not the scaffold engine's `plan`/`apply` for the settings file.* The engine stamps a digest of
the document into the **committed** `.stayfixed/manifest.json`, which would publish a digest of
the owner's personal allow rules to every collaborator. The pure functions are called
instead — document string in, document string out, no manifest — and the ledger below takes
the manifest's place. This is the one place where refusing an existing mechanism is right.

An allow rule cannot carry a marker — `scaffold.mark` appends to a *command* — so it has exactly
**one** witness, the ledger at `.stayfixed/local/attach.json`, and `detach` is only ever as good
as that file.

**Delivery does not depend on the memory mode.** Every repository is rendered and installed; the
note half — the overlay's group directories, the link tree and the harness memory link — is made
only for a repository whose `memory.mode` is `overlay`, and every check that is about it is asked
only there.

**Nothing goes into `.gitignore`, and every placed path is ignored before the first write after
the exclude block.** `.gitignore` is tracked, so a line `attach` wrote there was a change every
collaborator got. Everything `attach` places in the checkout, the ledger with the owner's personal
allow rules included, is listed in the `info/exclude` block (`attach.exclude`), which no clone
carries; the block is written first, and git is then asked whether each placed path is ignored,
so a `.gitignore` that re-includes one (a `!` line outranks the exclude file) stops the run
before that path is written. The binding id is placed too, but in the git common directory, which
git never tracks, so it is neither listed nor asked about. `init`'s own `stayfixed:ignore` region
is `init`'s, and this module neither writes nor withdraws it.

**Every write goes through a primitive that already exists.** `fsops.write_within(root, …)` for
everything inside the project, `fsops.write_within(overlay, …)` for the overlay's project record,
and `stayfixed.binding` and `attach.render` for this machine's binding record and render.
"""

from __future__ import annotations

import datetime
import json
import os
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from stayfixed import fsops, tomlout
from stayfixed.attach import exclude
from stayfixed.attach.binding import (
    Binding,
    read_binding,
    refuse_unless_share_can_exist,
    unlinked_groups,
)
from stayfixed.attach.permissions import (
    CODEX_RULES,
    LOCAL_SETTINGS,
    PermissionDiff,
    allow_list,
    codex_rules,
    diff_permissions,
    local_document,
    settings_document,
)
from stayfixed.attach.render import (
    COPIED,
    HOOK_FILE,
    MARKETPLACE_PREFIX,
    PLUGIN_DIRECTORY,
    PLUGIN_INSTALL_LOCAL,
    PLUGIN_MARKETPLACE_ADD_LOCAL,
    PLUGIN_MARKETPLACE_REMOVE,
    PLUGIN_UNINSTALL_LOCAL,
    Part,
    Rendered,
    delivery_directory,
    filled,
    marketplace_name,
    plugin_name,
    read_parts,
    remove_tree,
)
from stayfixed.attach.render import write as write_render
from stayfixed.binding import bound_project, ensure_id, read_id, record, short
from stayfixed.config.layout import ATTACH_LEDGER
from stayfixed.config.owner import Owner
from stayfixed.config.paths import PathEscape, PathUnasked, contained
from stayfixed.config.reading import UNPARSEABLE
from stayfixed.config.schema import OVERLAY_MODE, Config
from stayfixed.config.session import command_config
from stayfixed.errors import Failure, Refusal
from stayfixed.fsops import UnsafePath
from stayfixed.gitenv import GitUnavailable, Unasked, answer_lines, git_run, without_userinfo
from stayfixed.guards.api import hooks_dir
from stayfixed.jsonobject import NESTED, json_object
from stayfixed.memory.api import (
    BOUND,
    COMMON_GROUP,
    GATE_LAPSED,
    GATE_OPEN,
    PROJECT_RECORD,
    PROJECTS,
    STORE_DIR,
    Links,
    PartialLink,
    attach_main,
    build_composed,
    detach_main,
    harness_anchor,
    harness_gate,
    harness_targets,
    link,
    linked_names,
    main_checkout,
    read_binding_record,
    require_readable_record,
    resolve,
    withdraw_composed,
)
from stayfixed.overlay.api import PRE_COMMIT_CONFIG, PRE_COMMIT_HOOK
from stayfixed.printed import answered, quoted
from stayfixed.runner import Runner
from stayfixed.scaffold import (
    ParserLimitError,
    mark,
    marker_id,
    owned_ids,
    settings_text,
    withdraw_entries,
)
from stayfixed.trust.api import ONLY_OUTSIDE, PERSON_RUNS, SANDBOX_REFUSED

LEDGER_FORMAT = 1
# The one settings key `attach` writes: the harness's memory directory, which in overlay mode names
# the composed store (`memory.composed`), absolute, in the main checkout's `settings.local.json`,
# which Claude Code reads from every worktree.
POINTER_KEY = "autoMemoryDirectory"
# What `attach` says of a checkout with no `origin`, which binds as any other: the binding is the
# id in the git common directory, and the remote is only what the records note beside it.
NO_ORIGIN_NOTE = "this checkout has no `origin` remote, so the binding records none"
# Said where this machine's record bound the checkout to another project than the one it is bound
# to now: a renamed `[project] name` moves every worktree's binding. Both names print quoted.
REBOUND = "this checkout's binding moves from project {earlier} to project {project}"
# The third, and the first of the two whose trigger is repository-authored
# (`memory.groups` reaches no guard of its own). One constant for the check above every write
# and for the `O_NOFOLLOW` walk that is the floor under it, because two spellings of one
# refusal are two refusals to keep in step. The entry is never quoted back into it.
GROUP_ESCAPES = (
    "a memory.groups entry does not stay inside this project's share of the overlay, so it is "
    "refused rather than created"
)
# Said instead when no symlink is on the way and a directory on it cannot be asked whether it is
# one, which the sentence above would misname; `{fault}` is the system's words, never a path.
GROUP_UNASKED = (
    "a memory.groups entry's place in this project's share of the overlay cannot be checked for "
    "a symlink ({fault}), so it is refused rather than created"
)
# The fifth, and the second of the two whose trigger is repository-authored. Its anchor is
# `root` -- the checkout the command was pointed at, never a value the repository chose -- so a
# repository cannot move the directory this count is taken under: `unlinked_groups` contains
# every `<paths.memory>/<group>` against that root and refuses the ones that leave it. The
# count prints and the entries do not, for the reason `GROUP_ESCAPES` gives; the remedy names
# the shape of the destination rather than any group's name.
REAL_DIRECTORIES = (
    "{count} of this project's memory groups are real directories under paths.memory, and "
    "`attach` links rather than moves; move each into "
    "`<overlay>/projects/<the name in stayfixed.toml>/memory/<group>` (`common/memory` for the "
    "shared group) and run again -- `stayfixed attach --check` reports the count"
)
# `fsops.mkdirs_within` creates a target's *parents*, so a directory is asked for as the parent
# of a name inside it. Nothing is ever written at this name; `overlay.create` asks the same way.
_INSIDE = ".keep"
# Every directory `attach` can bring into existence in the project root, as a *closed* list,
# deepest first — which is also the order `detach` has to remove them in.
#
# There are exactly three writes that create a directory here, and each one's parents are on
# this list: `ATTACH_LEDGER` under `.stayfixed/local/`, the rule copies under `.codex/rules/`, and
# `LOCAL_SETTINGS` under `.claude/`. The link tree's directory (`paths.memory`, wherever the
# project configures it) is deliberately **not** here: it is repository-configured, so it cannot
# be a member of a closed list. The ledger's `memory_parents` records the directories above it
# instead, and `detach` bounds that record by the configuration it loads
# (`_withdraw_memory_directories`); `paths.memory` itself goes when it is empty.
#
# Closed because a ledger is a file a clone can commit. `detach` iterates this tuple and keeps
# only the members the ledger names, so the ledger can shorten the list and never extend it,
# and a committed `["src"]` names nothing this loop will act on. `ledger()` refuses one anyway,
# on the same standard `rules` and `settings_keys` are held to.
CREATED_DIRS = (".stayfixed/local", ".stayfixed", ".codex/rules", ".codex", ".claude")


@dataclass(frozen=True)
class Carried:
    """What a render of the plugin carries, as `attach` names it on its screen: each hook entry by
    its event and command, and each skill and agent by its name under `skills/` or `agents/`.

    Every name is the overlay's, the owner's own, read either out of the parts this run renders or
    out of the render directory the last run left, which is this machine's; each prints through
    `printed`."""

    hooks: tuple[tuple[str, str], ...] = ()
    skills: tuple[str, ...] = ()
    agents: tuple[str, ...] = ()

    def without(self, other: Carried) -> Carried:
        """What this carries that `other` does not."""
        return Carried(
            tuple(entry for entry in self.hooks if entry not in other.hooks),
            tuple(name for name in self.skills if name not in other.skills),
            tuple(name for name in self.agents if name not in other.agents),
        )


@dataclass(frozen=True)
class Attached:
    """What one `attach` changed, and the screen it is said on: the binding, then what will run
    that did not before and what no longer will, then the allow rules added.

    Nothing here is repository-authored but `origin`, this checkout's remote, and `project`, the
    name the binding is recorded under, both of which a caller prints through `printed`, and two
    notes: what `pre-commit install` printed, which is this
    machine's tool answering in the overlay, and `memory.store.origin_note`'s, which names the
    remotes through `printed.quoted`. `binding` is the binding id as `binding.short` prints it,
    never the whole id; `binding_recorded` says whether this run bound a checkout this machine did
    not bind before. `added` and `removed` are the executable diff against the render the last
    run left, and `allow_added` the allow rules this run merged; all three are the overlay's.
    """

    settings_written: bool
    rules_written: tuple[str, ...]
    binding_recorded: bool
    notes: tuple[str, ...]
    links: Links
    binding: str
    origin: str | None = None
    project: str = ""
    added: Carried = Carried()
    removed: Carried = Carried()
    allow_added: tuple[str, ...] = ()


@dataclass(frozen=True)
class AttachLedger:
    """The only witness an allow rule has, and the record `detach` acts from.

    Not *authority*, and the difference is the whole of this docstring. `.gitignore` does not
    untrack a file a clone committed, so this path can arrive in a fresh checkout with contents
    nobody on this machine wrote — and `detach` then deletes files by the strings in `rules` and
    drops settings keys by the strings in `settings_keys`. Obeyed, a ledger claiming
    `settings_keys = ["permissions"]` would delete the owner's whole `permissions` block, **deny
    rules included**: a widening driven by repository-authored bytes, out of a file that is no
    authority.

    So `ledger()` answers one question about every field before `detach` sees it — *what could
    `attach` possibly have written here?* — and refuses anything outside that answer rather than
    obeying it. The two fields that name things to destroy are bounded exactly:

    - `rules` may only be `.codex/rules/<file>`, the one place `permissions.codex_rules`
      enumerates, one path segment deep and never a dotfile; and
    - `settings_keys` may only be `autoMemoryDirectory`, the pointer at the composed store and the
      one key `_point` writes.

    `directories` is the third, and is bounded by membership in `CREATED_DIRS`. It records which
    of those directories this repository did **not** have before the attach, so `detach` can put
    the tree back as it found it; `rmdir` is the only removal it drives, so a directory holding
    anything at all survives regardless of what the ledger claims.

    `memory_parents` is the same record for the directories above `paths.memory` — `docs/`, for
    the preset's place — which only the configuration can name, so it is bounded where the
    configuration is in hand: `detach` keeps only the members that are ancestors of the
    `paths.memory` it loaded, and removes those with `rmdir` too. `memory_created` says whether
    this checkout had no `paths.memory` directory before the attach; a committed `true` costs at
    most an empty directory, because `rmdir` is the only removal it drives.

    `entries` keys must parse as marker ids, because `_write_ledger` builds them with
    `scaffold.marker_id` and nothing else can appear there.

    `allow` and `store` are not bounded here, and saying why is part of the rule rather than an
    omission. An allow rule has no grammar this area owns — the ledger exists *because* a rule
    cannot be told from the owner's own by its content — and `_withdraw_settings` only ever
    removes a rule the settings file already holds, so the worst a committed `allow` achieves is
    taking a permission away. `store` is read by nothing: `detach` derives every path it
    withdraws from the configuration and the overlay root, never from this field, so it is a
    record for a human reading the file and for `doctor`, and a committed value costs nothing —
    except one holding a NUL, which no path holds and `doctor`'s `Path.resolve` meets with
    `ValueError`, so that one is a ledger no attach wrote. So is any list field holding something
    other than a list, which reading it would meet with `TypeError`.

    `entries` maps each marker id to its event, which is the shape `scaffold.owned_ids` answers
    in, so `doctor` can compare the two without a translation in between. Only a ledger an earlier
    release wrote holds any: `attach` merges no hook entry now, takes back the ones recorded here,
    and records none.

    `render` is the digest and the parts of the render the last run installed, `None` before the
    first. It decides one thing, whether `attach` runs `claude plugin` again, and names nothing to
    destroy: each part is held to a path the contained walk accepts, and it is removed only from
    under `delivery_directory(id)`, which is derived from the id and never from this file.
    """

    store: str
    allow: tuple[str, ...]
    entries: dict[str, str]
    rules: tuple[str, ...]
    settings_keys: tuple[str, ...]
    directories: tuple[str, ...] = ()
    memory_parents: tuple[str, ...] = ()
    memory_created: bool = False
    render: Rendered | None = None


def _rule_is_writable(rule: str) -> bool:
    """Whether `attach` could have written this path: `.codex/rules/<file>` and nothing else.

    `permissions.codex_rules` composes every target as `f"{CODEX_RULES}/{rule.name}"` over a
    directory listing, so the answer is one path segment under that prefix, never a dotfile and
    never a nested path. `.github/workflows/ci.yml` and `src/stayfixed/__init__.py` are all
    inside the root `fsops.remove_within` contains the removal to, which is why containment is
    not the guard that matters here.
    """
    prefix = f"{CODEX_RULES}/"
    if not rule.startswith(prefix):
        return False
    name = rule[len(prefix) :]
    return bool(name) and "/" not in name and not name.startswith(".")


def _listed(raw: dict[str, Any], key: str, path: Path) -> list[Any]:
    """The ledger's `key`, which `attach` always writes as a list: absent reads as empty, and
    anything else is a ledger no attach wrote — a `Failure`, the answer every reader of this file
    already handles, and not the `TypeError` iterating a number would raise past them."""
    value = raw.get(key, [])
    if not isinstance(value, list):
        raise Failure(f"{path} is not a ledger `stayfixed attach` wrote: its {key!r} is not a list")
    return value


def _checked(
    raw: dict[str, Any], path: Path
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    """`rules`, `settings_keys` and `directories`, or a `Refusal` counting what was never written.

    Counted and never quoted: these strings are repository-authored (principle 5), and a
    refusal built out of one is still one.
    """
    rules = tuple(r for r in _listed(raw, "rules", path) if isinstance(r, str))
    keys = tuple(k for k in _listed(raw, "settings_keys", path) if isinstance(k, str))
    # Held to the same standard as the two above rather than merely filtered at the removal
    # site, so the answer to "is this a record of an attach on this machine?" is one answer.
    # `detach` also intersects with `CREATED_DIRS` when it walks them, which is the floor under
    # this; a name outside the list is a ledger no attach wrote, and that is a refusal.
    directories = tuple(d for d in _listed(raw, "directories", path) if isinstance(d, str))
    foreign = sum(1 for rule in rules if not _rule_is_writable(rule))
    foreign += sum(1 for key in keys if key != POINTER_KEY)
    foreign += sum(1 for name in directories if name not in CREATED_DIRS)
    if foreign:
        raise Refusal(
            f"{path} names {foreign} file(s), settings key(s) or directory(ies) that "
            f"`stayfixed attach` could never have written, so it is not a record of an attach on "
            f"this machine; nothing "
            f"was removed. Delete it, or take it out of the clone that committed it"
        )
    return rules, keys, directories


def ledger(root: Path) -> AttachLedger:
    """The ledger this repository's last `attach` wrote, or a `Failure` naming the missing file.

    Never a best effort. Guessing which allow rules were stayfixed's from their content is the
    heuristic this file exists to replace, and a `detach` built on a guess removes a rule the
    owner wrote by hand — which is worse than removing none.

    A ledger whose `rules` or `settings_keys` name something `attach` could not have written is
    a `Refusal` rather than a filtered list: see `AttachLedger`. Filtering would let a committed
    ledger keep the members it is entitled to and lose only the hostile ones, which is a partial
    defence reported as a success.
    """
    path = root / ATTACH_LEDGER
    with fsops.reading(ATTACH_LEDGER, Failure):
        try:
            # A regular file only (`fsops.read_regular_text`): a clone can commit the ledger, and
            # `detach` read it with no other check first, so a link to `/dev/zero` read until
            # memory ran out.
            text = fsops.read_regular_text(path)
        except FileNotFoundError as exc:
            raise Failure(
                f"{ATTACH_LEDGER} is not there, so nothing records what `stayfixed attach` added "
                f"to this repository; there is no safe way to guess it from the settings file"
            ) from exc
    # Empty text fails as JSON: `attach` never writes an empty ledger, so one is no record. Valid
    # JSON past the parser's reach, which a clone can commit, is unreadable like the arms above,
    # and said in the words every other refusal of a ledger here uses: not one `attach` wrote.
    raw = json_object(
        text,
        str(path),
        error=Failure,
        limit=lambda clause: Failure(
            f"{path} is not a ledger `stayfixed attach` wrote: it {clause}"
        ),
    )
    rules, keys, directories = _checked(raw, path)
    store = raw.get("store", "")
    if not isinstance(store, str):
        # `attach` writes the store as a string. Anything else is refused rather than passed
        # through `str()`: `{"store": 5}` would read as the store `5`, and from Python 3.14, whose
        # parser follows deeper nesting than `str()` does, a deeply nested value raised
        # `RecursionError` past every reader's catch.
        raise Failure(f"{path} is not a ledger `stayfixed attach` wrote: its 'store' is not text")
    if "\0" in store:
        # `attach` records the store it was handed as a path, and no path holds a NUL; `doctor`
        # hands this field to `Path.resolve`, which meets one with `ValueError`.
        raise Failure(f"{path} is not a ledger `stayfixed attach` wrote: its 'store' holds a NUL")
    try:
        os.fsencode(store)
    except UnicodeEncodeError:
        # The same reason as the NUL: a lone surrogate (`"\ud800"` in the JSON) is no path this
        # system can name, and `Path.resolve` meets one with `UnicodeEncodeError`.
        raise Failure(
            f"{path} is not a ledger `stayfixed attach` wrote: its 'store' is not a path this "
            f"system can encode"
        ) from None
    render = _render(raw.get("render"), path)
    entries = raw.get("entries")
    if isinstance(entries, dict) and not all(isinstance(v, str) for v in entries.values()):
        # `attach` records each entry's event as a string; refused for the reason `store` is.
        raise Failure(
            f"{path} is not a ledger `stayfixed attach` wrote: its 'entries' hold a value that "
            f"is not text"
        )
    return AttachLedger(
        store=store,
        allow=tuple(r for r in _listed(raw, "allow", path) if isinstance(r, str)),
        entries=(
            # `mark`/`marker_id` and not a second copy of the marker grammar: `_write_ledger`
            # builds these keys with `marker_id`, so a key that does not round-trip through the
            # engine's own pair is one no attach could have recorded. Dropped rather than
            # refused, because a key names nothing to destroy: what it costs is a provenance
            # row, and `doctor` reporting an entry as unrecorded is the conservative answer.
            {k: v for k, v in entries.items() if marker_id(mark("", k)) == k}
            if isinstance(entries, dict)
            else {}
        ),
        rules=rules,
        settings_keys=keys,
        directories=directories,
        memory_parents=tuple(d for d in _listed(raw, "memory_parents", path) if isinstance(d, str)),
        memory_created=raw.get("memory_created") is True,
        render=render,
    )


def _render(value: object, path: Path) -> Rendered | None:
    """The ledger's `render`, or `None` where it records none, or a `Failure` for one no attach
    wrote: `attach` writes a digest."""
    if value is None:
        return None
    digest = value.get("digest") if isinstance(value, dict) else None
    if not isinstance(digest, str):
        raise Failure(f"{path} is not a ledger `stayfixed attach` wrote: its 'render' is not one")
    return Rendered(digest)


def existing_ledger(root: Path) -> AttachLedger | None:
    """The ledger, or `None` when there is none: `attach` and `attach --check`, the two callers
    that may carry on without it, read it here, so the two end with one code on a ledger the run
    cannot take.

    Its path is held to the project before anything reads it: it is the one path `attach` writes
    inside the project that no other candidate names, so a `.stayfixed` committed as a link is
    refused here by name rather than by the walk that writes the ledger, after every write before
    it."""
    contained(root, ATTACH_LEDGER)
    if not fsops.is_file(root / ATTACH_LEDGER):
        return None
    return ledger(root)


def _allow_list(raw: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """The local settings document's `permissions` object, copied, and its allow list, read by
    `permissions.allow_list`: the reader `--check` reads the same file with, so the two refuse
    the same documents."""
    allow = allow_list(raw, LOCAL_SETTINGS)
    return dict(raw.get("permissions", {})), allow


def _merged_settings(document: str, diff: PermissionDiff, previous: AttachLedger | None) -> str:
    """The local settings document with the overlay's allow rules appended in order and the hook
    entries an earlier attach recorded taken back out (`scaffold.withdraw_entries`).

    Only the entries the earlier ledger names, under the event it names, and only where the file
    still holds them: the ledger and never the marker alone says which entries are stayfixed's.
    """
    recorded = previous.entries if previous is not None else {}
    held = owned_ids(document) if recorded else {}
    withdrawn = {id: event for id, event in recorded.items() if held.get(id) == event}
    if not diff.added_allow and not withdrawn:
        # Nothing to add or take back, so nothing is touched. A rewrite here would reformat a file
        # the owner owns, on a run that changed nothing, and report itself as a write.
        return document
    raw = settings_document(document)
    permissions, allow = _allow_list(raw)
    allow += [rule for rule in diff.added_allow if rule not in allow]
    if allow or permissions:
        permissions["allow"] = allow
        raw["permissions"] = permissions
    text = settings_text(raw, LOCAL_SETTINGS) + "\n"
    return withdraw_entries(text, withdrawn) if withdrawn else text


def _codex_rule_texts(binding: Binding) -> tuple[tuple[str, str], ...]:
    """Each overlay standing rule's target under `.codex/rules/` and its text, read while the run
    is planned.

    Kept apart from the Claude settings merge because the two harnesses fail differently and a
    shared path would hide which. The list itself is `permissions.codex_rules`, so that
    `attach --check` reports exactly the files `attach` then writes rather than a second
    enumeration that could disagree with this one. Every source is read and decoded here and none
    while copying: a source that is not UTF-8, met while copying, would stop the copy after
    the exclude block and the rules before it were written, with the partial copies
    hidden by the block and no ledger for `detach` to remove them by.
    """
    texts: list[tuple[str, str]] = []
    for target, source in codex_rules(binding):
        # The overlay is the owner's, so its path may print, and through `quoted`, as the
        # directory holding it is printed when it cannot be listed (`permissions.codex_rules`): the
        # project's `codex/` carries `project.name`, which the repository chooses.
        with fsops.reading(quoted(str(source)), _nothing_written):
            texts.append((target, source.read_text(encoding="utf-8")))
    return tuple(texts)


def _nothing_written(sentence: str) -> Failure:
    """`fsops.reading`'s sentence about an overlay rule file, as the failure it ends a run in."""
    return Failure(f"{sentence}, so nothing was written")


def _record_project(binding: Binding, remote: str | None) -> None:
    """Write `projects/<name>/project.toml` where it records no remote yet, keeping the
    first-attach date it already carries.

    The record is what the overlay keeps for the owner to read — the remote the project was first
    bound with and the first attach's date — and binds nothing: the binding is this machine's
    (`stayfixed.binding`). So a record that names a remote is left alone, whatever this checkout's
    `origin` says, and two machines attaching one project each keep their own binding without
    rewriting it. Re-stamping the date on every attach would turn a fact into a timestamp of the
    last run. `remote` is the `origin` as the machine's record kept it: none where a UTF-8 file
    cannot hold it.
    """
    if binding.recorded is not None or binding.fault is not None:
        return
    relative = f"{PROJECTS}/{binding.project}/{PROJECT_RECORD}"
    first = _first_attach(binding.overlay / relative) or datetime.date.today().isoformat()
    fields: dict[str, object] = {"first_attach": first}
    if remote is not None:
        fields = {"remote": remote, **fields}
    # `tomlout` and not an f-string: the value is a git remote URL, which is repository-authored
    # (principle 5), and one carrying a quote and a newline would write further keys into it.
    fsops.write_within(binding.overlay, relative, tomlout.dumps({"": fields}))


def _first_attach(record: Path) -> str | None:
    if not fsops.is_file(record):
        return None
    try:
        return read_binding_record(record).get("first_attach")
    except (OSError, UnicodeDecodeError, *UNPARSEABLE):
        return None


def _secret_scan(binding: Binding, runner: Runner) -> str | None:
    """Run `pre-commit install` in the overlay if it is missing.

    `overlay init` runs it on the machine that created the overlay, which is the first attach's
    happy path — but a second machine clones an overlay initialised elsewhere and never runs
    `init` again. Doing it twice is free; not doing it at all leaves the commit-time secret scan
    unarmed on exactly the machine that thinks it is set up. A missing `pre-commit` is a note,
    never a traceback.
    """
    if not fsops.is_file(binding.overlay / PRE_COMMIT_CONFIG):
        return None
    try:
        installed = fsops.exists(hooks_dir(binding.overlay) / PRE_COMMIT_HOOK)
    except Refusal:
        # `hooks_dir` shells out to `git`, and a `git` that cannot answer is this area's own
        # kind of missing optional binary: a note, never a traceback, and never a `pre-commit
        # install` fired blind at an overlay whose hooks directory nobody could name.
        return (
            "`git` could not name the overlay's hooks directory, so whether its commit-time "
            "secret scan is installed was not checked; the push-time scan still runs"
        )
    if installed:
        return None
    done = runner.launch(["pre-commit", "install"], binding.overlay)
    if done.code == 0:
        return "installed the overlay's commit-time secret scan with `pre-commit install`"
    detail = answered(done)
    return (
        f"`pre-commit install` did not run in the overlay ({detail}), so its commit-time secret "
        f"scan is not installed; the push-time scan still runs"
    )


def _absent_directories(root: Path) -> tuple[str, ...]:
    """Which of `CREATED_DIRS` this repository does not have, asked before the first write.

    Asked *before*, because after the ledger is written `.stayfixed/local/` exists and the answer
    is not the one `detach` needs. `attach` therefore takes it at the top of the run and
    hands it down, the same way it hands down `previous`.

    `is_dir()` and not `exists()`: a path of this name that is a file, or a symlink to one, is
    not a directory this run created and `rmdir` would refuse it anyway — recording it would
    only put a name in the ledger that nothing can act on.

    A path the question cannot reach, below a committed `.codex` that links into a directory
    nobody may search, is not one either: every write of this run goes through the `O_NOFOLLOW`
    walk, which never reaches it, so this run cannot create it. Raised, the fault ended `attach`
    and `--check` in an internal error before the containment refusal that names the link.
    """
    return tuple(name for name in CREATED_DIRS if not _reached_directory(root / name))


def _reached_directory(path: Path) -> bool:
    """`fsops.is_dir`, and `True` for a path no write of this run can reach; see above."""
    try:
        return fsops.is_dir(path)
    except OSError:
        return True


def _memory_parents(config: Config) -> tuple[str, ...]:
    """Every directory above `paths.memory` inside the project, deepest first.

    Read off the loaded value, which the loader has already held to one component per segment
    (`config.paths.validate_paths`), so this is a split and not a second parser.
    """
    parts = config.paths.memory.split("/")
    return tuple("/".join(parts[:depth]) for depth in range(len(parts) - 1, 0, -1))


def _absent_memory_parents(root: Path, config: Config) -> tuple[str, ...]:
    """Which directories above `paths.memory` this repository does not have, asked before the
    first write for the reason `_absent_directories` is."""
    return tuple(name for name in _memory_parents(config) if not fsops.is_dir(root / name))


def _memory_absent(root: Path, config: Config) -> bool:
    """Whether this checkout has no `paths.memory` directory, asked before the first write for the
    reason `_absent_directories` is: an empty one the owner made is theirs, and survives."""
    return not fsops.is_dir(root / config.paths.memory)


def placed_paths(config: Config, rules: Iterable[str], *, memory: bool) -> tuple[str, ...]:
    """Every path an attach puts into the checkout's work tree: the ledger, the link tree
    (`linked_names`, the same list `attach_main` walks) where `memory` says the notes are linked,
    each rule copy in `rules` (`codex_rules`' targets for a run, the ledger's for `doctor`), and
    the settings file. These are what
    `attach.exclude` hides and holds inside the project, and what one rule holds: none tracked,
    each ignored once the block stands. The binding id is placed too, but under the git common
    directory, which git never tracks, so it is no path of the work tree.

    **The settings file always, because it names the id.** `claude plugin install --scope local`
    writes the plugin's `enabledPlugins` entry, `overlay-<id>@stayfixed-delivery-<id>`, into it on
    the first attach, and it holds that entry on every run after; a name a clone could read there is
    a name it could commit."""
    return (
        ATTACH_LEDGER,
        *(f"{config.paths.memory}/{name}" for name in linked_names(config) if memory),
        *rules,
        LOCAL_SETTINGS,
    )


def main_settings(root: Path, checkouts: tuple[Path, ...]) -> tuple[str, ...]:
    """The main checkout's settings file as a placed path of its own, where `root` is a linked
    worktree: Claude Code writes the plugin's entry, which names the binding id, into the main
    checkout's file whichever worktree `attach` runs from, so that file is held to the rule every
    placed path is. Nothing where `root` is the main checkout, whose own placed paths include it."""
    return () if checkouts[0] == root.resolve() else (LOCAL_SETTINGS,)


def named_placed(config: Config, paths: tuple[str, ...]) -> str:
    """Placed paths as a refusal names them: those the checkout or the overlay names through
    `printed.quoted`, and the link tree's counted, because each carries a `memory.groups` entry,
    which the repository chose."""
    tree = f"{config.paths.memory}/"
    named = [quoted(path) for path in paths if not path.startswith(tree)]
    if linked := sum(1 for path in paths if path.startswith(tree)):
        named.append(f"{linked} link(s) of the link tree under paths.memory")
    return ", ".join(named)


def _write_ledger(
    root: Path, planned: AttachPlan, settings_keys: tuple[str, ...], render: Rendered | None
) -> None:
    """Record what this attach may remove again — the union with what an earlier one claimed.

    The union is not a nicety. A second attach against an unchanged overlay has an *empty*
    diff, because every rule is already present, so a ledger written from the diff alone would
    forget what the first one added and leave `detach` nothing to remove.

    **The earlier ledger arrives in the plan and is not read here**, which is a refusal's
    position and not a refactor. `ledger()` refuses a ledger naming files or settings keys
    `attach` could not have written, and read here that refusal would fire from the fourth write
    of the run, with the ignore region, the `.codex/rules/` copies and the settings merge already
    on disk and the committed ledger still there for `doctor._attached` to read as "attached".
    That is the shape `attach`'s own docstring says all its refusals must not have. `_plan` reads
    it once, above every write.

    Reading it once is also the more correct union: `attach` writes the ledger twice in a run,
    and the second call would otherwise union against the file the first call just wrote.
    """
    previous, binding = planned.previous, planned.binding
    rules = tuple(target for target, _ in planned.rules)
    allow = list(previous.allow) if previous is not None else []
    allow += [rule for rule in planned.diff.added_allow if rule not in allow]
    # The same union for the rule files, and for a sharper reason than the one above. A file
    # deleted from the overlay between two attaches is not written this time and so drops out of
    # a ledger built from this run alone — while the copy from the first attach is still sitting
    # in `.codex/rules/`, where Codex reads it as a standing instruction. `detach` would then
    # leave an agent-steering file behind, and `attach` must stay idempotent and reversible by
    # `detach`.
    placed = list(previous.rules) if previous is not None else []
    placed += [rule for rule in rules if rule not in placed]
    # The same union as `allow` and `rules`, for the same reason sharpened once more: the second
    # attach in a repository finds every one of these directories already there and would record
    # none, so a ledger built from this run alone would leave `detach` unable to remove what the
    # first attach created. Ordered by `CREATED_DIRS` rather than by either input, so the written
    # list is deepest-first whatever order it was unioned in.
    made = set(previous.directories if previous is not None else ()) | set(planned.absent)
    # The same union for the directories above `paths.memory`, deepest first, for the same reason.
    above = set(previous.memory_parents if previous is not None else ()) | set(planned.parents)
    document = {
        "format": LEDGER_FORMAT,
        "store": str(binding.store),
        "allow": allow,
        # No hook entry is merged any more, and the settings file this run writes has taken back
        # every one the earlier ledger recorded.
        "entries": {},
        "rules": placed,
        "settings_keys": list(settings_keys),
        "directories": [name for name in CREATED_DIRS if name in made],
        "memory_parents": sorted(above, key=lambda name: (-name.count("/"), name)),
        # The same union once more: a second attach finds the directory the first one made.
        "memory_created": planned.memory_created
        or (previous is not None and previous.memory_created),
        # The digest, never the id and never a path on this machine (`render.Rendered`).
        "render": None if render is None else {"digest": render.digest},
    }
    fsops.write_within(root, ATTACH_LEDGER, json.dumps(document, indent=2, sort_keys=True) + "\n")


def _group_directories(binding: Binding, config: Config) -> list[str]:
    """Every directory this project's groups need inside the overlay, as one spelling.

    One list for the check and for the write both, so the refusal above every write and the
    `O_NOFOLLOW` walk that does the writing cannot come to disagree about which paths they are
    talking about. `common/memory` is not here — it is shared across projects and `overlay
    create` ships it — and skipping it in one of the two would be the first way they drift.
    """
    return [
        f"{PROJECTS}/{binding.project}/{STORE_DIR}/{group}/{_INSIDE}"
        for group in config.memory.groups
        if group != COMMON_GROUP
    ]


def _check_groups(binding: Binding, config: Config) -> None:
    """Refuse a `memory.groups` entry that leaves this project's share of the overlay — first.

    `memory.groups` is repository-authored (principle 5) and reaches no guard of its own —
    `config/paths.py` says so in as many words, and leaves the containment to the module that
    consumes the field. This module was calling it, and calling it too late: the refusal came
    out of `_prepare_store`, which runs after the ignore region, the `.codex/rules/` copies, the
    settings merge, the ledger **and** the overlay's binding record. So a clone committing
    `groups = ["../../escape"]` got `attach` to write five artifacts and exit 2, with
    `doctor._attached` — which keys on the ledger existing — then reporting the repository
    attached and the binding *bound*, because the record had been written too.

    Hoisting it here is not only a reordering: it is this project's own two-stage rule, which
    `attach` was skipping for this one path. `config.paths.contained` "decides whether a
    configured path *may* be written — it gives a user-facing refusal and catches a committed
    symlink", and `fsops.mkdirs_within` then does the write through an `O_NOFOLLOW` walk so a
    component that becomes a symlink *after* the check cannot redirect it. `attach` had only the
    second half, which is why its user-facing refusal arrived at write time.

    `resolved_root` is passed because this validates many paths against one root, which is the
    parameter's documented reason for existing.
    """
    resolved = binding.overlay.resolve()
    for relative in _group_directories(binding, config):
        try:
            contained(binding.overlay, relative, resolved_root=resolved)
        except PathUnasked as exc:
            raise Refusal(GROUP_UNASKED.format(fault=exc.fault)) from exc
        except PathEscape as exc:
            # The entry itself is repository-authored, so it is refused rather than quoted back.
            raise Refusal(GROUP_ESCAPES) from exc


def _prepare_store(binding: Binding, config: Config) -> None:
    """Create this project's own group directories in the overlay.

    The link tree has to land on something: `memory.store` drops a group whose target does not
    exist, and a store with no groups does not resolve at all.

    **The `UnsafePath` arm is the floor under `_check_groups` and is not dead.** A spelling that
    escapes was already refused above every write, so that half reaching here means the hoist
    drifted. The other half cannot be hoisted and should not be: `contained` asks the filesystem
    a question and this walk asks it again at the moment of writing, so a component of the
    overlay that became a symlink in between refuses here and nowhere earlier. That is the
    interval the `O_NOFOLLOW` walk exists for, and it is the one remaining way this refusal can
    arrive after a write.
    """
    for relative in _group_directories(binding, config):
        try:
            fsops.mkdirs_within(binding.overlay, relative)
        except UnsafePath as exc:
            raise Refusal(GROUP_ESCAPES) from exc


# Said where the repository is bare: git names no main checkout, the one whose
# `settings.local.json` Claude Code reads from every worktree and the overlay's plugin is installed
# from, and the common directory's parent is no checkout at all.
NO_MAIN_CHECKOUT = (
    "cannot tell which checkout is this repository's main one: the repository is bare, so git "
    "names none, and the overlay's plugin is installed from the main checkout; nothing was "
    "changed. Attach from a clone with a working tree of its own"
)


def _worktrees(root: Path, *, bare: bool = False) -> list[Path]:
    """Every checkout of this repository, from `git worktree list --porcelain`; in a bare
    repository `NO_MAIN_CHECKOUT`, or nothing where `bare` says the caller can do without a main
    checkout.

    Through `gitenv.git_run`, which scrubs `GIT_DIR` and `GIT_WORK_TREE`: an inherited one would
    list the worktrees of a different repository altogether, and this module then writes into
    each one of them.
    """
    code, out = git_run(root, "worktree", "list", "--porcelain")
    if code != 0:
        raise Failure(
            "`git` could not list this repository's worktrees, so memory cannot be linked into "
            "them; the fault is on this machine — check that `git` runs here"
        )
    # One record per blank-line-separated block. A block carrying `prunable` names a worktree
    # whose directory is gone and which nobody has `git worktree prune`d yet -- the state a
    # deleted worktree is left in by the ordinary `rm -rf`. `link()` run with `cwd=<gone>`
    # raised `GitUnavailable` ("check that `git` runs here") after the ledger, the region and
    # the owner's links were written, on a machine whose `git` was fine; and `detach` in the
    # same state completed. Skipped here, so both halves read the same set.
    found: list[Path] = []
    # Lines split where git ended them: `splitlines()` also broke a path at a `\r` it holds, and
    # listed `…/wt` — a directory that is not the worktree, and one this module links into — for
    # the worktree at `…/wt\rx` (`gitenv.answer_lines`).
    for block in out.split("\n\n"):
        lines = answer_lines(block)
        # The first block is the main worktree, and in a bare repository it is the repository
        # itself, marked `bare`: there is no main checkout to install the plugin from or to own
        # the store, and the common directory's parent is no checkout.
        if "bare" in lines:
            if not bare:
                raise Refusal(NO_MAIN_CHECKOUT)
            return []
        if any(line == "prunable" or line.startswith("prunable ") for line in lines):
            continue
        found.extend(
            Path(line[len("worktree ") :]) for line in lines if line.startswith("worktree ")
        )
    return found


def _checkouts(root: Path, *, bare: bool = False) -> list[Path]:
    """Every checkout of this repository, the one that owns the store first, each exactly once;
    nothing in a bare repository where `bare` asks for that rather than for `NO_MAIN_CHECKOUT`.

    Both halves need `git` — `main_checkout` asks it which checkout owns this worktree, and
    `_worktrees` asks it for the rest — which is the whole reason this is a function rather than
    four lines in each caller. `detach` calls it **before its first withdrawal** for that reason:
    a `git` that cannot run is a fact about the machine, knowable at the start, and asking it
    after the settings file and the `.codex/rules/` copies were already taken away left the
    repository half-detached over something nothing had yet touched.

    Owner first because `attach` has to build the owning checkout's tree before `resolve()` can
    answer, and `detach` mirrors the order so the two read the same way. Deduplicated by resolved
    path, so `--root` is visited exactly once whether or not it is the owner.
    """
    owner = main_checkout(root).resolve()
    trees = _worktrees(root, bare=bare)
    if not trees:
        return []
    found = [owner]
    seen = {owner}
    for tree in trees:
        resolved = tree.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        found.append(resolved)
    return found


def _link_everywhere(
    checkouts: tuple[Path, ...],
    binding: Binding,
    config: Config,
    *,
    machine: Path | None,
    home: Path | None,
) -> Links:
    """The owning checkout first, then every other worktree.

    `attach_main` handles the checkout that holds the store — the case `worktree.link` excludes
    — and `link` handles the rest unchanged. A `PartialLink` propagates carrying **everything
    this run made**, across every call: a half-built tree is repairable, and swallowing it into
    a generic failure is what made one mysterious.

    That accumulation is the whole of the re-raise below. `link` builds its own `.created` per
    call, so an exception let out untouched carries the failing checkout's links and not the
    owning checkout's — which are on disk, made by `attach_main` one call earlier — and a list
    missing the links that were actually made defeats the type: a caller repairing from it is told
    nothing was made. `attach_main` itself is the first call, so its own `.created` is already the
    whole of what this run made and needs no wrapping.

    **`attach_main` is applied to the owning checkout and never to `--root`.** The loop below
    skips `main_checkout(root)` unconditionally, so applied to whatever `--root` names, `stayfixed
    attach` run from a linked worktree would build that worktree's tree twice and the main
    checkout's not at all. `worktree.link` is documented as a no-op for the main checkout, so
    nothing downstream would catch it: every session in the owning checkout would see no memory,
    silently, and the command would exit 0.

    The skip is by resolved path and accumulates, so `root` — which `_worktrees` lists like any
    other — is linked exactly once whether or not it is the owner. `checkouts` is `_checkouts`'
    answer, taken while the run is planned: it needs `git`, and a `git` that cannot list the
    worktrees is knowable before anything is written.
    """
    owner = checkouts[0]
    links = attach_main(owner, binding.store, config, machine=machine, home=home)
    created, revoked = list(links.created), list(links.revoked)
    # Resolved against the owner and not against `root`: in overlay mode `resolve` reads the
    # link tree, and the tree that exists at this point is the one `attach_main` just built.
    store = resolve(owner, config, machine=machine)
    if store is None:
        raise Failure(
            "the link tree was created and the store still does not resolve; "
            "`stayfixed memory index --check` reports why"
        )
    for tree in checkouts[1:]:
        try:
            more = link(tree, store, config, home=home)
        except PartialLink as partial:
            raise PartialLink([*created, *partial.created], partial) from partial
        except GitUnavailable as unasked:
            # Removed after `git worktree list` named it, and before `link` asked in it: no
            # checkout to link any more, as a `prunable` one is not (`_worktrees`). Asked first
            # thing in `link`, so nothing was written there. Any other cause is reported.
            if unasked.cause is not Unasked.GONE:
                raise
            continue
        created += more.created
        revoked += more.revoked
    return Links(created, revoked, refresh_refused=links.refresh_refused)


def _keys_in(document: str) -> tuple[str, ...]:
    """The settings keys `attach` owns that a settings document holds."""
    return (POINTER_KEY,) if POINTER_KEY in settings_document(document) else ()


def _point(main: Path, store: Path) -> bool:
    """Write `POINTER_KEY` naming `store` into the main checkout's settings file, whether it was
    written: the file is left alone where it already names `store`. Asked after the placed-path rule
    has passed for that file (`_carry_out`), since the path names the whole binding id."""
    document = settings_document(local_document(main))
    if document.get(POINTER_KEY) == str(store):
        return False
    document[POINTER_KEY] = str(store)
    fsops.write_within(main, LOCAL_SETTINGS, settings_text(document, LOCAL_SETTINGS) + "\n")
    return True


# How the sentences below ask for the store's approval: of the person at the machine, never of an
# agent (`trust.api.PERSON_RUNS`).
_APPROVE = PERSON_RUNS.format(command="stayfixed trust approve memory")
# Said when the harness memory link was left out because the gate withheld it, which in overlay
# mode it does until the owner approves the store: the link tree sits inside the repository.
# Nothing in it is repository-authored, so it prints.
HARNESS_WAITS = (
    "the harness memory link was not created, because the link tree it would expose sits inside "
    f"this repository and has no approval yet; {_APPROVE}; then run `stayfixed attach` again"
)


# Why an approval no longer holds, and what to do about it: said by `attach` (`HARNESS_LAPSED`)
# and by `doctor`'s `attached` row, which reads the same state after the run, so the two say it
# alike. Nothing in either is repository-authored, so both print.
APPROVAL_LAPSED = (
    "the store or its memory.index_extra changed since its approval was recorded, so that "
    "approval no longer holds"
)
REAPPROVE = f"read what changed, then {_APPROVE}; then run `stayfixed attach` again"
# Said instead of `HARNESS_WAITS` where the machine records an approval and the store changed
# since, which closes the gate as surely as no approval and also withdraws the links an earlier run
# made: one line appended to one note is enough.
HARNESS_LAPSED = f"the harness memory link was not created, because {APPROVAL_LAPSED}; {REAPPROVE}"
# Said where the index this run rendered for the store could not carry its approval, because the
# trust record's directory refused the write as an agent's sandbox refuses one: the approval stays
# at the person's digest, which the store no longer matches, so `HARNESS_LAPSED` follows it, and
# this says why it lapsed.
REFRESH_REFUSED = SANDBOX_REFUSED.format(
    outcome="the store's approval was not carried across the index this run wrote and was left "
    "as it was",
    directory="the trust record's directory",
    remedy=ONLY_OUTSIDE,
)
# Said whenever the run withdrew harness memory links, which only the gate does, so the line
# never leaves a withdrawal unsaid; the count is the one `--json` gives as `links_revoked`.
HARNESS_WITHDREW = "withdrew {count} harness memory link(s)"


def _harness_waits(owner: Path, config: Config, *, machine: Path | None) -> str | None:
    """Why the gate kept the harness link from being made, or `None` where it did not:
    `harness_link_needed`, asked exactly as `_apply_harness_link` asks it, of the store the run
    just linked, which is the owning checkout's, `owner`. `HARNESS_LAPSED` where an
    approval is recorded and the store changed since it (`harness_gate`), and `HARNESS_WAITS`
    where none is."""
    store = resolve(owner, config, machine=machine)
    gate = GATE_OPEN if store is None else harness_gate(store, config)
    if gate == GATE_OPEN:
        return None
    return HARNESS_LAPSED if gate == GATE_LAPSED else HARNESS_WAITS


@dataclass(frozen=True)
class AttachPlan:
    """What `attach` decided before its first write, and all its writes are made from.

    `_plan` reads, decodes and refuses; `_carry_out` takes this value and writes. So a refusal
    after the first write is not something a later edit can bring back by moving a line: a read
    the writes need is a field here, and filling it is `_plan`'s job.
    """

    config: Config
    binding: Binding
    diff: PermissionDiff
    previous: AttachLedger | None
    # Whether the notes are linked: `memory.mode` is `overlay`. Delivery does not ask.
    memory: bool
    absent: tuple[str, ...]
    parents: tuple[str, ...]
    memory_created: bool
    # The settings document to write, or `None` when the merge leaves it as it is.
    settings: str | None
    carried: tuple[str, ...]
    # Every path this run places in the work tree (`placed_paths`), and the exclude block that hides
    # them, or `None` when the owner's own excludes hide them all.
    placed: tuple[str, ...]
    hidden: exclude.ExcludeWrite | None
    # Each `.codex/rules/` target and the text to copy there.
    rules: tuple[tuple[str, str], ...]
    # What the rendered plugin carries, read from the overlay (`render.read_parts`).
    parts: dict[str, Part]
    checkouts: tuple[Path, ...]


def attach(
    root: Path,
    *,
    store: Path | None,
    machine: Path | None,
    runner: Runner,
    home: Path | None,
    owner: Owner | None = None,
) -> Attached:
    """Bind this repository to the overlay, merge the allow rules it grants, render and install
    its executable parts, and link the notes in.

    The order below is the order they are enumerated in: read the binding, which already
    refuses a store outside the machine-recorded overlay; compute the diff, which gates nothing,
    since the overlay is the owner's and what it grants is shown rather than refused; read the
    existing ledger, which refuses one no attach could have written; refuse a `memory.groups`
    entry that leaves this project's share of the overlay; refuse a harness anchor this machine
    cannot vouch for; refuse a group that never moved into the overlay; ask git what it already
    hides, which refuses a `check-ignore` with no answer, a placed path that leaves the project
    and a symlinked or unwritable exclude file; read the overlay's rule sources and the parts the
    plugin carries, the checkouts and the machine's trust record, which the writes below would
    otherwise read for themselves; then write the exclude block, refuse a placed path git would
    still not ignore (`exclude.NOT_IGNORED`), and only then write any file the block hides. The
    checks about the notes — the `memory.groups` containment, the harness anchor and the groups
    that never moved — are asked only of a repository whose `memory.mode` is `overlay`, whose
    notes are linked; delivery does not depend on the mode.

    **The split is what holds that order.** `_plan` reads and refuses and returns an
    `AttachPlan`; `_carry_out` takes only that value and writes. A read the writes need is a
    field of the plan, so it cannot drift below the first write the way the rule sources, the
    worktree listing and the trust record each once did.

    The ordinals in the body number that enumeration and not the line order, and two of them
    fire out of it: the ledger's refusal is read a few lines below the two that need the
    `Config`, and the never-moved check is asked **before** the harness anchor rather than
    after it. The reason is the `Config`: `_check_groups` has just loaded it, and the
    never-moved check reads the same `memory.groups` and the same `paths.memory` — so the two
    containments over one repository-authored list stay in one place, and the anchor, which
    needs neither, follows. Nothing writes between them; every one of the five is above the
    first write, which is the property that matters and the one the tests assert.

    **A sixth refusal is above every write and is not one of the five**, because it is not a
    check this function makes: `unlinked_groups` contains each `<paths.memory>/<group>` against
    `root` before it counts, and a `PathEscape` out of it propagates as the refusal it already
    is — `paths.memory` may itself be a symlink, and then every group escapes at once. It is
    enumerated nowhere because it has no ordinal of its own; it is named here so that the count
    above reads as "five checks" rather than as "five ways this can refuse".

    **Neither a missing `origin` nor one the records do not name refuses.** The binding is the id
    `stayfixed.binding` writes into the git common directory, which no clone carries, and the
    machine's record of it; the remote decides nothing, so it is a note (`NO_ORIGIN_NOTE`,
    `memory.store.origin_note`).

    The binding is written before the links, the id and the machine's record first, because
    `memory.store` checks it and a store whose checkout is unbound does not resolve — and
    `attach_main` resolves as its last step. The ledger is written before the links too, so a
    `PartialLink` half way through leaves behind a repository `detach` can still clean up. The
    render follows the binding, since it is named by the id, and is installed with two idempotent
    `claude plugin` calls on every run; the ledger records it once they succeed, and a call that
    fails exits 1 with the exclude block standing, so a re-run completes.

    `runner` and `home` are keyword-**required** rather than defaulted so that no test can reach
    a real `pre-commit` or the developer's own `~/.claude/`. A default here would leave that as
    a convention, which is the thing the rule exists to replace: while this module was being
    written, every call that omitted `home` computed a path under the real home directory.
    `owner` is the owner's layer the command resolved, which the one load takes
    (`config.loader.loads`' own).
    """
    planned = _plan(
        root,
        store=store,
        machine=machine,
        home=home,
        owner=owner,
    )
    return _carry_out(root, planned, machine=machine, runner=runner, home=home)


class Gates:
    """The gates `attach` meets past the binding, in the order it meets them.

    Iterated, it yields the refusal of each stop and makes the reads that lie between them, so
    `_plan` and `attach --check` take one order and cannot come to disagree about it. `_plan`
    refuses at the first stop and reads nothing past it; `--check` takes the stop and reports it,
    and plans the writes only where there was none. `diff` and `real` are what the reads found,
    for the plan and the report.

    **No stop is about what the overlay grants.** The allow rules and the executable parts are the
    owner's, written by the owner and the owner's agents, neither of them this delivery's
    adversary, so `attach` shows them and proceeds (`Attached`) rather than asking for a flag.
    """

    # What the overlay grants and the local settings lack, read past the share once iterated.
    diff: PermissionDiff

    def __init__(self, root: Path, config: Config, binding: Binding) -> None:
        self.root = root
        self.config = config
        self.binding = binding
        self.real = 0

    def __iter__(self) -> Iterator[str]:
        binding, config = self.binding, self.config
        # Beside the binding's own refusals: a `project.name` no directory under the overlay can
        # carry leaves the binding record and the group directories nowhere to go, and the
        # overlay's sources read under it answer "none" rather than refusing, so nothing below
        # would ask before writing.
        refuse_unless_share_can_exist(binding, config)
        # The diff, read in the run's order: it refuses a settings file the merge could not read,
        # and `--check` reads it past a stop where the run reads nothing, so it is read before it.
        self.diff = diff_permissions(self.root, binding)
        # The two checks about the notes, asked only where they are linked.
        if config.memory.mode != OVERLAY_MODE:
            return
        refuse_unless_share_holds(binding, config)
        # The fifth, and the one whose remedy is an act no command performs: `attach` **links**,
        # so a group that is still a real directory under `paths.memory` has its notes in the
        # repository and its share of the overlay empty, and linking over it would leave every
        # session reading the repository's copy with the binding record, the settings merge and
        # the ledger already written. Above every write for that reason, and beside the
        # `memory.groups` containment because it reads the same repository-authored list -- the
        # anchor it is contained against is `root`, the checkout this command was pointed at,
        # which is why a repository cannot move the directory the count is taken under. A
        # `PathEscape` out of `unlinked_groups` propagates as the refusal it already is.
        self.real = len(unlinked_groups(self.root, config))
        if self.real:
            yield REAL_DIRECTORIES.format(count=self.real)


def _plan(
    root: Path,
    *,
    store: Path | None,
    machine: Path | None,
    home: Path | None,
    owner: Owner | None,
) -> AttachPlan:
    """Every read, decode and check `attach` makes, in the order `attach` enumerates them, and
    nothing written: what it returns is all `_carry_out` may act on.

    The gate -- the groups that never moved -- is `Gates`', which `attach --check` iterates too,
    and the run refuses at it.
    What lies between and after them is `refuse_unless_share_holds` and `plan_writes`, which
    `--check` asks where the run would, so the preview stops on every refusal the run makes past
    those gates, with the same code and line, by calling what the run calls."""
    # One load for the whole run, handed to `read_binding` rather than left for it to make a
    # second of. `attach.check` took this ruling for `--check` -- "two loads could
    # disagree, and a `--check` whose two halves read different documents is exactly what it
    # exists to rule out" -- and the writing command has the stronger version of that argument:
    # a `--check` that read two documents reports the wrong thing, while an `attach` that reads
    # two writes under the wrong one. `read_binding` loads on the line it is called from, so
    # nothing moves in the order the refusals happen in; what changes is that `project.name`,
    # `memory.groups` and `paths.memory` are read once and the refusals below are about the
    # same document the binding was read under.
    config = command_config(root, machine=machine, owner=owner)
    binding = read_binding(root, store=store, machine=machine, config=config)
    gates = Gates(root, config, binding)
    for refusal in gates:
        raise Refusal(refusal)
    return plan_writes(root, config, binding, gates.diff, machine=machine, home=home)


def refuse_unless_share_holds(binding: Binding, config: Config) -> None:
    """Refuse a binding this project's share of the overlay cannot hold: a `memory.groups` entry
    that leaves the share.

    Asked between the run's gates (`Gates`), above every write, by `attach` and by
    `attach --check` alike where the run would reach it, so the two end alike on either.
    """
    # The third refusal, and it belongs here for the reason the two above it do; the second,
    # the ledger's, is read in `plan_writes` and is above every write too. `ledger()` refuses
    # a ledger naming files or settings keys `attach` could not have written, and asked for by
    # `_write_ledger`, the fourth write of the run, it would let a clone that commits such a
    # ledger make `attach` write the ignore region, copy `.codex/rules/*` and merge
    # `.claude/settings.local.json` before exiting 2, with the committed ledger still on disk for
    # `doctor._attached` to read as "attached"; `attach --check` reads it through the same
    # `existing_ledger`, so it no longer reports clean beforehand. The `Config` this and the
    # never-moved check read is loaded at the top of `_plan`, which is where the binding needs it
    # anyway: a check cannot happen above the writes while what it reads is loaded below them.
    _check_groups(binding, config)


def plan_writes(
    root: Path,
    config: Config,
    binding: Binding,
    diff: PermissionDiff,
    *,
    machine: Path | None,
    home: Path | None,
) -> AttachPlan:
    """The rest of `_plan`: every read and refusal `attach` makes once the groups have all moved,
    and nothing written. The ledger, the settings merge, the checkouts and the anchor for the
    harness memory link, what git already hides and the exclude block, the overlay's rule sources
    and the parts the rendered plugin carries, and the machine's trust record, in that order.

    `attach --check` calls it too and drops the plan, which is how the preview meets every one of
    these refusals with the run's code and line: each read here was once left out of the preview,
    and `--check` answered clean over a checkout the run then stopped on.
    """
    previous = existing_ledger(root)
    memory = config.memory.mode == OVERLAY_MODE
    # Above every write, because the first of them creates `.stayfixed/local/` and the answer
    # would then be wrong by exactly the directory this run brought into existence.
    absent = _absent_directories(root)
    parents = _absent_memory_parents(root, config) if memory else ()
    memory_created = memory and _memory_absent(root, config)
    # What git already hides is asked here, above the first write, and decides the `info/exclude`
    # block: a line for each path `attach` places that the owner's own excludes do not hide
    # (`exclude.unhidden_by_owner`). It can refuse — git cannot answer, a path leaves the project,
    # the exclude file is a symlink — and each refusal is made while nothing has been written.
    # The settings merge is computed here, before any write, so a file it cannot read stops the
    # run while nothing is written.
    document = local_document(root)
    merged = _merged_settings(document, diff, previous)
    written = merged != document
    # The checkouts, read here: the first is the main checkout, which the plugin is installed
    # from, and the rest are where the link tree goes. Their refusal is a `git` that cannot name
    # or list them, knowable before anything is written. The harness memory link's walk
    # differs per checkout at `projects/<slug>`, so it is asked of each here where it is made.
    checkouts = tuple(_checkouts(root))
    if memory:
        for tree in checkouts:
            harness_anchor(tree, home)
        # The main checkout's settings file, which `_point` reads after the writes: read now as it
        # reads it, so a file it cannot read refuses while nothing is written.
        settings_document(local_document(checkouts[0]))
    placed = placed_paths(config, (target for target, _ in codex_rules(binding)), memory=memory)
    # One rule for every placed path: none tracked, asked here above every write, and each ignored,
    # asked once the block stands (`_carry_out`).
    if found := exclude.tracked(root, placed):
        raise Refusal(exclude.TRACKED.format(paths=named_placed(config, found)))
    # And the main checkout's settings file, the one `claude plugin install --scope local` writes
    # the plugin's entry into from any worktree, asked of the main checkout's own index.
    if found := exclude.tracked(checkouts[0], main_settings(root, checkouts)):
        raise Refusal(exclude.TRACKED.format(paths=named_placed(config, found)))
    hidden = exclude.planned_block(root, placed)
    # The reads the writes below would otherwise make for themselves, each of which can refuse
    # after the first write: the overlay's rule sources (a file that is not UTF-8), what the
    # rendered plugin carries (a hook file of a shape it cannot read, a skill that cannot be read)
    # and, where the notes are linked, the machine's trust record, which the index render and the
    # harness link both read (a `trust.json` that does not parse).
    rules = _codex_rule_texts(binding)
    parts = read_parts(binding.overlay, binding.project)
    if memory:
        require_readable_record(machine)
    return AttachPlan(
        config=config,
        binding=binding,
        diff=diff,
        previous=previous,
        memory=memory,
        absent=absent,
        parents=parents,
        memory_created=memory_created,
        settings=merged if written else None,
        # What an earlier attach left in the settings file, carried into the ledger written
        # before the links so that a `PartialLink` half way through still leaves `detach` able to
        # remove it. Read off the document this run leaves there; the real answer is taken again
        # after the links, by the only function that can change it.
        carried=_keys_in(merged),
        placed=placed,
        hidden=hidden,
        rules=rules,
        parts=parts,
        checkouts=checkouts,
    )


def _carry_out(
    root: Path, planned: AttachPlan, *, machine: Path | None, runner: Runner, home: Path | None
) -> Attached:
    """Write what `_plan` decided: the exclude block first, then ask git whether every placed path
    is ignored, and only then any file the block hides, so none is ever where git would show it —
    the settings file Claude Code writes the plugin's `enabledPlugins` entry into among them,
    before the first `claude plugin` call.

    What is still asked here is asked of what this run has just written, and cannot be asked
    before it: whether git ignores each placed path once the block stands, whether the store
    resolves once the link tree stands, and whether the harness link is wanted once it does; the
    composed store and its pointer follow the links. A write that itself fails is the other way
    this can stop after the first write.
    """
    config, binding, previous = planned.config, planned.binding, planned.previous
    if planned.hidden is not None:
        exclude.write(planned.hidden)
    # The rule's second half: a `.gitignore` re-including a placed path (`!`) outranks the block.
    if shown := exclude.unignored(root, planned.placed):
        raise Refusal(exclude.NOT_IGNORED.format(paths=named_placed(config, shown)))
    # The main checkout's settings file too, asked of its own `.gitignore`: a worktree's branch can
    # ignore it while the main checkout's re-includes it. The block is shared, so it is in place.
    main = planned.checkouts[0]
    if shown := exclude.unignored(main, main_settings(root, planned.checkouts)):
        raise Refusal(exclude.NOT_IGNORED.format(paths=named_placed(config, shown)))
    for target, text in planned.rules:
        fsops.write_within(root, target, text)
    rules = tuple(target for target, _ in planned.rules)
    written = planned.settings is not None
    if planned.settings is not None:
        fsops.write_within(root, LOCAL_SETTINGS, planned.settings)
    # The pointer is recorded before it is written, so a run that stops on the way leaves `detach`
    # a record of it; with no notes linked, what an earlier attach left in the file stays recorded.
    carried = (POINTER_KEY,) if planned.memory else planned.carried
    recorded = previous.render if previous is not None else None
    _write_ledger(root, planned, carried, recorded)
    # The binding: the id in the git common directory and the machine's record of it, then the
    # overlay's record where it has none. Before the links, since the store resolves only for a
    # bound checkout, and before the render, which the id names.
    id = ensure_id(root)
    bound = record(root, binding.project, binding.remote)
    _record_project(binding, bound.origin)
    # What ran before this render, read out of the render directory before it is rewritten, and
    # what will run after it, read out of the parts: the screen's executable diff.
    before, after = _carried_in(delivery_directory(id)), _carried(planned.parts)
    rendered = write_render(id, planned.parts)
    # Installed on every run, since both calls are idempotent: what Claude Code knows is its own
    # state, which a copy's detach or a lost id can take away whatever this ledger says. A call
    # that fails exits 1 with no render recorded and the exclude block standing, so a re-run
    # completes.
    if (failed := _install(id, planned.checkouts[0], runner)) is not None:
        _write_ledger(root, planned, carried, None)
        raise Failure(failed)
    recorded = rendered.rendered
    _write_ledger(root, planned, carried, recorded)
    notes: list[str] = []
    links = Links([], [])
    if planned.memory:
        _prepare_store(binding, config)
        links = _link_everywhere(planned.checkouts, binding, config, machine=machine, home=home)
    if (note := _secret_scan(binding, runner)) is not None:
        notes.append(note)
    if binding.fault is not None:
        notes.append(binding.fault)
    if binding.bound is not None and binding.bound != binding.project:
        notes.append(REBOUND.format(earlier=quoted(binding.bound), project=quoted(binding.project)))
    if binding.remote is None:
        notes.append(NO_ORIGIN_NOTE)
    elif binding.note is not None:
        notes.append(binding.note)

    def said(written: bool) -> Attached:
        """What this run did, with the screen it is said on."""
        return Attached(
            written,
            rules,
            binding.state != BOUND,
            tuple(notes),
            links,
            short(id),
            origin=None if binding.remote is None else without_userinfo(binding.remote),
            project=binding.project,
            added=after.without(before),
            removed=before.without(after),
            allow_added=planned.diff.added_allow,
        )

    if not planned.memory:
        return said(written)
    owner = planned.checkouts[0]
    # The composed store, rebuilt, and the one key that points the harness at it, in the main
    # checkout's settings file, whose placed-path rule passed above; the ledger already records the
    # key (`carried`), so a run that stops here leaves `detach` able to take it back.
    # The project is the one this machine's binding record names, read back after `record` above
    # wrote it, never `[project] name` on its own.
    project = (bound_project(root) or bound).project
    written = _point(owner, build_composed(binding.overlay, project, id)) or written
    if links.revoked:
        notes.append(HARNESS_WITHDREW.format(count=len(links.revoked)))
    if links.refresh_refused:
        notes.append(REFRESH_REFUSED)
    # Asked only here, where its answer is said: it reads the store's trust record and digests
    # its notes, and a run that says something else above has no use for that.
    if (waits := _harness_waits(owner, config, machine=machine)) is not None:
        notes.append(waits)
    return said(written)


def _named_under(files: Iterable[str], directory: str) -> tuple[str, ...]:
    """The first name below `directory/` of each of `files`, paths relative to the plugin, sorted
    and each once: a skill is its directory, an agent its file."""
    prefix = f"{directory}/"
    return tuple(
        sorted({path[len(prefix) :].split("/")[0] for path in files if path.startswith(prefix)})
    )


def _hook_entries(text: str) -> tuple[tuple[str, str], ...]:
    """Each entry of a rendered hook file as `(event, command)`, in its order; nothing for a file
    of any other shape, since the screen is a convenience and refuses nothing."""
    try:
        hooks = json.loads(text).get("hooks", {})
    except (ValueError, AttributeError, RecursionError):
        return ()
    found: list[tuple[str, str]] = []
    for event, groups in hooks.items() if isinstance(hooks, dict) else ():
        for group in groups if isinstance(groups, list) else ():
            entries = group.get("hooks", []) if isinstance(group, dict) else []
            for entry in entries if isinstance(entries, list) else ():
                if isinstance(entry, dict) and isinstance(entry.get("command"), str):
                    found.append((str(event), entry["command"]))
    return tuple(dict.fromkeys(found))


def _carried(parts: Mapping[str, Part]) -> Carried:
    """What the parts `render.read_parts` read carry."""
    hooks = parts[HOOK_FILE].text if HOOK_FILE in parts else ""
    return Carried(_hook_entries(hooks), *(_named_under(parts, name) for name in COPIED))


def _carried_in(directory: Path) -> Carried:
    """What the render directory the last run left carries, or nothing where it holds no render
    or cannot be read: asked after the first write, so it answers rather than refusing, and a
    directory it cannot read shows every part as added."""
    plugin = directory / PLUGIN_DIRECTORY
    try:
        hooks = fsops.read_regular_text(plugin / HOOK_FILE)
    except (OSError, UnicodeDecodeError):
        hooks = ""
    files: list[str] = []
    for name in COPIED:
        try:
            files += [f"{name}/{child}" for child in os.listdir(plugin / name)]
        except OSError:
            continue
    return Carried(_hook_entries(hooks), *(_named_under(files, name) for name in COPIED))


# Said where a `claude plugin` call did not succeed. Its code and nothing it printed: what Claude
# Code prints names the plugin, and the plugin's name carries the whole binding id.
NOT_INSTALLED = (
    "`claude plugin {verb}` did not succeed (exit {code}), so the overlay's hooks, skills and "
    "agents are rendered but not installed; run `stayfixed attach` again"
)


def _install(id: str, main: Path, runner: Runner) -> str | None:
    """Register the render as a marketplace of the main checkout and install its plugin there, or
    say which call failed. Run from the main checkout, whose `settings.local.json` Claude Code reads
    from every worktree and writes the plugin's entry into."""
    added = runner.launch(filled(PLUGIN_MARKETPLACE_ADD_LOCAL, str(delivery_directory(id))), main)
    if added.code != 0:
        return NOT_INSTALLED.format(verb="marketplace add", code=added.code)
    done = runner.launch(
        filled(PLUGIN_INSTALL_LOCAL, f"{plugin_name(id)}@{marketplace_name(id)}"), main
    )
    if done.code != 0:
        return NOT_INSTALLED.format(verb="install", code=done.code)
    return None


# Said where the main checkout's settings file still names the plugin once `detach` asked Claude
# Code to forget it: the keys left, never their names, which carry the whole binding id.
STILL_NAMED = (
    "the main checkout's `.claude/settings.local.json` still names the overlay's plugin under "
    "{keys}, so the exclude block, the ledger and the render were kept; run `stayfixed detach` "
    "again once `claude plugin` runs here"
)
# Said where the render directory could not be removed once Claude Code was told to forget it.
RENDER_STAYED = (
    "the overlay's rendered plugin under this machine's data directory could not be removed "
    "({fault}); the ledger was kept, so `stayfixed detach` can be run again"
)
# The two keys of the settings file Claude Code writes the plugin's entries under: `install` the
# plugin's, `marketplace add` its marketplace's, each named by the whole binding id.
ENABLED_PLUGINS = "enabledPlugins"
KNOWN_MARKETPLACES = "extraKnownMarketplaces"


def _plugin_keys(main: Path) -> dict[str, tuple[str, ...]]:
    """The names under each of the two keys in the main checkout's settings file."""
    document = settings_document(local_document(main))
    return {
        key: tuple(document[key]) if isinstance(document.get(key), dict) else ()
        for key in (ENABLED_PLUGINS, KNOWN_MARKETPLACES)
    }


def _withdraw_plugin(
    id: str | None, main: Path, held: dict[str, tuple[str, ...]], runner: Runner
) -> None:
    """Ask Claude Code, from the main checkout, to forget the plugin `id` names and its marketplace,
    each where `held` says that checkout's settings file names it; then read the file again and
    stop with `STILL_NAMED` while a name under either key names a `stayfixed-delivery-`
    marketplace, which needs no id. The file decides, never the exit codes: what must hold before
    the exclude block goes is that the file names no delivery."""
    if id is not None:
        plugin = f"{plugin_name(id)}@{marketplace_name(id)}"
        if plugin in held[ENABLED_PLUGINS]:
            runner.launch(filled(PLUGIN_UNINSTALL_LOCAL, plugin), main)
        if marketplace_name(id) in held[KNOWN_MARKETPLACES]:
            runner.launch(filled(PLUGIN_MARKETPLACE_REMOVE, marketplace_name(id)), main)
    named = _plugin_keys(main).items()
    left = [key for key, names in named if any(MARKETPLACE_PREFIX in name for name in names)]
    if left:
        raise Failure(STILL_NAMED.format(keys=", ".join(f"`{key}`" for key in left)))


def _remove_render(directory: Path) -> None:
    """Remove the render directory whole (`render.remove_tree`), or say why it stayed."""
    try:
        remove_tree(directory)
    except OSError as exc:
        raise Failure(RENDER_STAYED.format(fault=fsops.said(exc))) from exc


@dataclass(frozen=True)
class Detached:
    """What one `detach` withdrew. The binding record is not on this list, on purpose."""

    allow_removed: tuple[str, ...]
    entries_removed: tuple[str, ...]
    rules_removed: tuple[str, ...]
    settings_keys_removed: tuple[str, ...]
    links: Links
    directories_removed: tuple[str, ...] = ()
    exclude_block_removed: bool = False
    # The block was left in place because another checkout of this repository still holds a
    # ledger: the exclude file is shared, and that checkout's files still need hiding.
    exclude_block_kept: bool = False
    # This checkout's link tree was left in place because it owns the store and another checkout
    # of this repository still holds a ledger: that checkout's harness memory link points at it.
    link_tree_kept: bool = False
    # The rendered plugin's render directory was removed, Claude Code having been told to forget
    # whatever of it the main checkout's settings file named.
    delivery_removed: bool = False
    # The composed store was kept, its links taken, because it holds a file that is not a link: a
    # note the harness wrote there, which nothing of stayfixed's placed.
    store_kept: bool = False


def _emptied(raw: dict[str, Any]) -> dict[str, Any]:
    """The settings document with the containers `detach` just emptied taken out again.

    An empty `permissions.allow` is not what the file looked like before `attach`, and the round
    trip this command promises is measured in bytes: `tests/attach/test_detach.py` snapshots
    every file under the root and compares. `apply_entries` already does the same for `hooks`.
    """
    permissions = raw.get("permissions")
    if isinstance(permissions, dict):
        if permissions.get("allow") == []:
            permissions.pop("allow")
        if not permissions:
            raw.pop("permissions")
    return raw


@dataclass(frozen=True)
class SettingsWithdrawal:
    """What `detach` takes out of the settings file, decided before its first withdrawal.

    `text` is the file's new content, `""` when nothing is left and the file goes, and `None`
    when nothing of stayfixed's is in it and it is not written at all: a rewrite of a file the
    withdrawal leaves as it was reformats somebody's file, and through a `.claude` linked in from
    elsewhere it is a write `detach` has no business making.
    """

    removed: tuple[str, ...]
    text: str | None


def _planned_settings(root: Path, recorded: AttachLedger) -> SettingsWithdrawal:
    """Take exactly the recorded rules, the recorded entries and the pointer key back out.

    The allow rules come from the ledger and never from a guess at their content: that is the
    whole reason the ledger exists. So do the hook entries an earlier release merged, through
    `scaffold.withdraw_entries`, which takes the ones the ledger names and never one by its marker
    alone — foreign entries keep their matcher and their position, and a group that mixes the two
    is split rather than dropped.
    """
    document = local_document(root)
    if not document.strip():
        return SettingsWithdrawal((), None)
    raw = settings_document(document)
    try:
        # The copy and the comparison recurse as the encoder does, and on Python 3.14 under a
        # reduced stack either overflows for a document the parser read: the reader's refusal of
        # one nested too deep, never an internal error.
        held = json.loads(json.dumps(raw))
        permissions, allow = _allow_list(raw)
        removed = tuple(rule for rule in recorded.allow if rule in allow)
        if permissions:
            permissions["allow"] = [rule for rule in allow if rule not in recorded.allow]
            raw["permissions"] = permissions
        for key in recorded.settings_keys:
            raw.pop(key, None)
        # Through `settings_text`, as every write-back of a parsed settings document: on Python
        # 3.12 an indented encode stops near 994 levels, under what the parser read.
        emptied = settings_text(_emptied(raw), LOCAL_SETTINGS) + "\n"
        remaining = json.loads(withdraw_entries(emptied, recorded.entries))
        unchanged = remaining == held
    except RecursionError:
        raise ParserLimitError(f"{LOCAL_SETTINGS} {NESTED}") from None
    if unchanged:
        return SettingsWithdrawal(removed, None)
    # `{}` is not what the file looked like before `attach`; a file holding nothing is one this
    # command created and is the last thing it takes away.
    text = settings_text(remaining, LOCAL_SETTINGS) + "\n" if remaining else ""
    return SettingsWithdrawal(removed, text)


def _withdraw_settings(root: Path, planned: SettingsWithdrawal) -> tuple[str, ...]:
    """Write what `_planned_settings` decided."""
    if planned.text:
        fsops.write_within(root, LOCAL_SETTINGS, planned.text)
    elif planned.text is not None:
        fsops.remove_within(root, LOCAL_SETTINGS)
    return planned.removed


def _withdraw_directories(root: Path, recorded: AttachLedger) -> tuple[str, ...]:
    """Remove the directories this repository did not have before the attach, and only those.

    The last step of a detach, after the ledger itself is gone, because `.stayfixed/local/` holds
    it. `docs/cli.md` promises "an attach and a detach leave the tree byte-for-byte as it was",
    and directories are part of the tree, though a snapshot that filters on `is_file()` cannot
    see them.

    **Three things keep this from deleting somebody's directory.** It walks `CREATED_DIRS`, a
    closed list, and keeps only what the ledger named — so a committed ledger can shorten the
    list, never extend it. The ledger names only what `_absent_directories` found missing before
    the first write, so a directory that was already there is never on it. And the removal is
    `rmdir`: a directory holding anything else at all — the owner's own `.claude/settings.json`,
    a `.codex/rules/` file they wrote by hand, a file some other tool left — survives, and its
    parents then survive with it because they are not empty either.

    `ENOTEMPTY` is therefore an ordinary outcome and not a failure, and it is the one this
    `except OSError` is written for: `fsops.rmdir_within` already contains the walk to `root` and
    tolerates an absent target, so what is left is "not empty" and "not permitted", and neither
    is a reason to fail a detach that has already put everything it recorded back.

    Two other things land in the same arm and are meant to. `fsops.UnsafePath` subclasses
    `OSError`, so a component of one of these paths that became a symlink between the check and
    the call is caught here too — the walk refuses it, the directory stays, and the detach
    finishes; that is the same answer "not empty" gets, and the right one for a path this
    function was never going to be able to remove safely. A `PermissionError` is the third, and
    is a fact about the filesystem rather than about the detach.
    """
    removed: list[str] = []
    for name in CREATED_DIRS:
        # `is_dir()` before the call and not only the ledger's say-so: `rmdir_within` tolerates
        # an absent target, so without this a directory the run never created — `.claude/`, when
        # the overlay grants nothing to merge — would be reported as one this detach removed.
        if name not in recorded.directories or not fsops.is_dir(root / name):
            continue
        try:
            fsops.rmdir_within(root, name)
        except OSError:
            continue
        removed.append(name)
    return tuple(removed)


def _rmdir_if_empty(base: Path, name: str) -> bool:
    """`rmdir` one directory a name this run computed, through the walk; whether it went.

    `ENOTEMPTY` is the ordinary answer and not a failure, for the reason
    `_withdraw_directories` gives, and so is a component the walk refuses.
    """
    target = base / name
    if fsops.is_symlink(target) or not fsops.is_dir(target):
        return False
    try:
        fsops.rmdir_within(base, name)
    except OSError:
        return False
    return True


def _withdraw_memory_directories(
    root: Path, trees: list[Path], config: Config, recorded: AttachLedger
) -> tuple[str, ...]:
    """The empty `paths.memory` directory, then the directories above it that the ledger records
    the attach as having created, in `root` alone; and the empty `paths.memory` in every other
    checkout this run withdrew a tree from. `trees` is `_reach`'s second answer, so a checkout
    whose tree was kept keeps its directories too, `root` among them: its `paths.memory` still
    stands inside every parent the ledger names, so `rmdir` takes none of them.

    In `root`, `paths.memory` goes only when the ledger says the attach created it — an empty
    one the owner made before is theirs — and the directories above it only when the ledger says
    this repository did not have them before, and only the names that are ancestors of the
    `paths.memory` this run loaded, so a ledger a clone committed can shorten that list and never
    extend it. In every other checkout no ledger of this run's records what was there, and the
    tree was built by `attach` or by the worktree-link handler, so `paths.memory` goes wherever it
    is empty. `rmdir` cannot take a directory holding a note, a group that never moved or
    anything else of the project's. Only `root`'s names are returned, so the count `run_detach`
    prints is this checkout's.
    """
    removed: list[str] = []
    own = root.resolve()
    for tree in trees:
        if tree.resolve() == own:
            if recorded.memory_created and _rmdir_if_empty(tree, config.paths.memory):
                removed.append(config.paths.memory)
        else:
            _rmdir_if_empty(tree, config.paths.memory)
    for name in _memory_parents(config):
        if name in recorded.memory_parents and _rmdir_if_empty(root, name):
            removed.append(name)
    return tuple(removed)


# Said when a path `detach` removes or rewrites is reached through a symlink: a directory on the
# way to it became one after the attach. Asked before the first withdrawal, because its removal
# would find that out after the settings file was withdrawn, as `internal error: UnsafePath`. The
# path is named by what it is, never by its spelling: a recorded rule copy's name is a ledger's,
# which a clone can commit, and `paths.memory` and the group names are the repository's.
LINKED_ON_THE_WAY = (
    "{what} is reached through a symlink ({where} is one now), and `detach` removes nothing "
    "through one, so nothing was withdrawn; replace the link with the directory it points at and "
    "run `stayfixed detach` again"
)
# Said when a `memory.groups` entry added since the attach is not one name inside `paths.memory`.
# Asked before the first withdrawal, because the link tree's withdrawal would find that out after
# the settings, the rule copies and the earlier links were withdrawn, and would print the entry,
# which the repository wrote.
GROUP_LEAVES_TREE = (
    "a memory.groups entry is not one directory name inside paths.memory, so its link cannot be "
    "withdrawn, and nothing was; take it out of stayfixed.toml, or put back the list the attach "
    "ran with, and run `stayfixed detach` again"
)
# Said instead when the entry is one name and a directory on the way cannot be asked whether it
# is a symlink: taking the entry out would not be the remedy. `{fault}` is the system's words.
GROUP_UNASKED_IN_TREE = (
    "a memory.groups entry's place inside paths.memory cannot be checked for a symlink "
    "({fault}), so its link cannot be withdrawn, and nothing was; run `stayfixed detach` again "
    "once that directory can be read"
)


def _walked(root: Path, relative: str, *, what: str, where: str) -> None:
    """`fsops.check_within`, the removal's own walk, with its refusal said by name."""
    try:
        fsops.check_within(root, relative)
    except UnsafePath as exc:
        raise Refusal(LINKED_ON_THE_WAY.format(what=what, where=where)) from exc


def _refuse_unwithdrawable(
    root: Path,
    recorded: AttachLedger,
    trees: list[Path],
    config: Config,
    settings: SettingsWithdrawal,
) -> None:
    """Walk to every path the withdrawal writes or removes, before the first withdrawal: the
    settings file when it is rewritten, each recorded rule copy, each name that is a link in the
    link tree of every checkout in `trees` — `_reach`'s answer, the checkouts whose tree this run
    withdraws, and no other — and the ledger.

    The writes and removals are `fsops` walks that refuse a symlinked component, and asked first
    by them, the question would come after the settings file was already withdrawn. `contained`
    is not the walk's question: it lets `paths.memory`'s own last component be a link, which the
    walk refuses, and refuses a rule copy that is itself a link, which the walk unlinks.
    `fsops.check_within` is the walk, so the two cannot disagree; it stays the floor for a
    component that changes in between.
    """
    if settings.text is not None:
        _walked(root, LOCAL_SETTINGS, what=f"`{LOCAL_SETTINGS}`", where="`.claude`")
    for rule in recorded.rules:
        _walked(
            root,
            rule,
            what="a `.codex/rules/` copy this checkout's attach recorded",
            where="`.codex` or `.codex/rules`",
        )
    for tree in trees:
        base = contained(tree, config.paths.memory, allow_final_symlink=True)
        for name in linked_names(config):
            try:
                target = contained(base, name, allow_final_symlink=True)
            except PathUnasked as exc:
                raise Refusal(GROUP_UNASKED_IN_TREE.format(fault=exc.fault)) from exc
            except PathEscape as exc:
                raise Refusal(GROUP_LEAVES_TREE) from exc
            if fsops.is_symlink(target):
                _walked(
                    tree,
                    f"{config.paths.memory}/{name}",
                    what="a link in a checkout's link tree",
                    where="`paths.memory` or a directory above it",
                )
    _walked(
        root,
        ATTACH_LEDGER,
        what=f"the ledger, `{ATTACH_LEDGER}`",
        where="`.stayfixed` or `.stayfixed/local`",
    )


def _another_attached(root: Path, checkouts: list[Path]) -> bool:
    """Whether a checkout of this repository other than `root` holds an attach ledger.

    Only a ledger an attach in that checkout wrote counts: one git does not track, since
    `attach` never commits it and a clone that did puts the file in every worktree, and one that
    reads as a ledger, since a file that does not records no attach. Counted, either kind would
    keep the shared exclude block for good. A `git` that cannot say whether the file is tracked
    counts it, which keeps the block: the answer that hides too much rather than too little.
    """
    own = root.resolve()
    for tree in checkouts:
        if tree == own or not fsops.is_file(tree / ATTACH_LEDGER):
            continue
        code, tracked = git_run(tree, "ls-files", "-z", "--", ATTACH_LEDGER)
        if code == 0 and tracked:
            continue
        try:
            ledger(tree)
        except (Failure, Refusal):
            continue
        return True
    return False


def _reach(root: Path, checkouts: list[Path], *, kept: bool) -> tuple[list[Path], list[Path]]:
    """The checkouts whose harness memory link this detach withdraws, and those whose link tree
    it withdraws.

    With no other checkout attached, every checkout's of both, as `attach` made them. While
    another checkout still holds a ledger (`kept`, `_another_attached`), only `--root`'s harness
    link, and `--root`'s tree unless `--root` owns the store: every checkout's harness link points
    at the owning checkout's tree (`_link_everywhere`), so taking that tree, or another
    checkout's, left a checkout whose ledger still stands half attached and its harness link
    dangling. A later `attach` anywhere builds the owner's tree first, so keeping it loses
    nothing. `checkouts` is `_checkouts`' answer, owner first and resolved.
    """
    if not kept:
        return checkouts, checkouts
    own = root.resolve()
    return [own], [] if own == checkouts[0] else [own]


def detach(
    root: Path,
    *,
    machine: Path | None,
    runner: Runner,
    home: Path | None,
    owner: Owner | None = None,
) -> Detached:
    """Remove exactly what `attach` added, reading the ledger for what that was, and withdraw the
    rendered plugin, whose directory is derived from the binding id and never read from the ledger.

    The plugin is installed in the main checkout, which every worktree shares, so it is withdrawn
    only where no other checkout is still attached: `claude plugin uninstall` where the main
    checkout's settings file names the plugin and `marketplace remove` where it names the
    marketplace, through `runner`, after this run's own withdrawal from the settings file and before
    the exclude block goes, then the render directory where there is one. While the file still names
    the id once they ran, whatever they exited with, it is a `Failure` there (`STILL_NAMED`), with
    the exclude block, the ledger and the render kept, and a second `detach` finishes from the
    ledger. In a bare repository's worktree git names no main checkout, `attach` installed nothing
    there, and this checkout's own parts are withdrawn. The id and this machine's record of it are
    kept, as the overlay's record is.

    It does **not** touch `projects/<name>/project.toml`. That record is the overlay's note of
    the project's first remote and first attach, for the owner to read, and binds nothing: the
    overlay's, not this checkout's.

    `machine` and `home` are keyword-required, as they are on `attach` and on every helper here
    that takes them, and required rather than defaulted for the reason `attach` gives: a resolver
    without a machine file reads the developer's real `~/.config/stayfixed/`, and the harness link
    is under their real home. A caller that means "the machine owner's own" says `None` out loud.

    **What it may refuse on, and when.** `detach` cannot refuse the way `attach` does once it has
    begun: by the time it reaches the link tree the recorded allow rules, the recorded hook entries
    and the `.codex/rules/` copies are already withdrawn, so a refusal there strands a
    half-detached repository. That is why `worktree.detach_main` makes `memory.mode` load-bearing
    through the target it derives rather than refusing on it.

    That is not licence to *discover* a precondition late. Everything structural this function
    can know before its first withdrawal is asked before it: the ledger (which refuses one no
    attach could have written), the configuration (whose loader validates `paths.*`), the
    settings document's own shape through `owned_ids`, `_checkouts`, which is the only thing here
    that needs `git`, the exclude block, what
    the settings file becomes (`_planned_settings`), and every path the withdrawal writes or
    removes, walked the way the write or removal walks it (`_refuse_unwithdrawable`). What is
    left after the first withdrawal is exactly what cannot precede it — a write that fails, and a
    component of the tree that changed between the check and the removal.

    **It needs the ledger in the checkout it is run from, and that is a limitation rather than a
    defect.** `.stayfixed/local/` is untracked and per-checkout, so a sibling worktree does not
    carry the ledger of the checkout an attach was run from and `detach --root <that worktree>`
    answers "no ledger". Without one there is nothing to reverse — guessing which allow rules
    were stayfixed's from their content is the heuristic the ledger exists to replace. So the
    place it may be started from is the one that holds the record, and the reach it has *once it
    starts* is `_reach`'s: every checkout (`_worktrees` below) when no other holds a ledger, and
    `--root` alone while one does, keeping the owning checkout's tree that other checkout's
    harness link points at.
    """
    recorded = ledger(root)
    config = command_config(root, machine=machine, owner=owner)
    held = owned_ids(local_document(root))
    entries = tuple(sorted(id for id, event in recorded.entries.items() if held.get(id) == event))
    # Asked before the first withdrawal, because these are the things here that need `git` and a
    # `git` that cannot run is knowable at the start. Asked between the settings withdrawal and
    # the link trees, a machine whose `git` is gone would get exit 1 with the settings file and the
    # `.codex/rules/` copies already removed and every link still in place. The home the harness
    # links are under is asked in the same breath: a mistyped `--home` withdrew nothing, exit 0.
    # The rendered plugin, named by the id and installed in the main checkout, which every
    # worktree shares: withdrawn where no other checkout is still attached (`kept`, below). Its
    # render directory is derived from the id and never read from the ledger, whose `store` and
    # `render` a clone can commit; asked here, before the first withdrawal, since the id is read
    # through `git`.
    id = read_id(root)
    try:
        delivery = delivery_directory(id) if id is not None else None
    except Failure:
        # A `HOME` that names no home holds no render; the home the harness links are under is
        # refused below in its own words.
        delivery = None
    # Nothing in a bare repository's worktree: git names no main checkout there, so `attach`
    # installed nothing, and this checkout's own parts are withdrawn alone.
    listed = _checkouts(root, bare=True)
    main = listed[0] if listed else None
    checkouts = listed or [root.resolve()]
    for tree in checkouts:
        harness_anchor(tree, home)
    # The `info/exclude` block is found above the first withdrawal for the same reason: `git`
    # names the file and a region opened twice refuses, and both are knowable now. It is shared
    # by every checkout while the ledger, the settings file and the `.codex/rules/` copies are
    # each checkout's own, so it stays while another checkout still holds a ledger: taking it
    # would show that checkout's settings file and rule copies in its `git status`.
    kept = _another_attached(root, checkouts)
    hidden = None if kept else exclude.withdrawn_block(root)
    harnessed, trees = _reach(root, checkouts, kept=kept)
    settings = _planned_settings(root, recorded)
    # What the main checkout's settings file names, which decides each `claude plugin` call: read
    # here, so a file that cannot be read refuses while nothing is withdrawn.
    plugin = None if kept or main is None else (id, main, _plugin_keys(main))
    # Where each checkout's harness link may point and be ours, asked here because it walks the
    # owning checkout's `paths.memory` as well as the checkout's own, and while another ledger
    # stands `_refuse_unwithdrawable` walks no tree but `--root`'s. Asked from inside the
    # withdrawal, a main checkout whose `paths.memory` came to be reached through a symlink
    # refused after the rule copies were gone. And asked before `_refuse_unwithdrawable`, which
    # walks only checkouts asked here: it resolves each tree's `paths.memory` with no answer for
    # a symlink loop, where `.resolve()` raises `RuntimeError` up to Python 3.12, and this
    # question's one refusal names the loop.
    targets = {tree: harness_targets(tree, checkouts[0], config) for tree in harnessed}
    _refuse_unwithdrawable(root, recorded, trees, config, settings)
    allow_removed = _withdraw_settings(root, settings)
    rules_removed: list[str] = []
    for rule in recorded.rules:
        if fsops.is_file(root / rule):
            fsops.remove_within(root, rule)
            rules_removed.append(rule)
    # The pointer, which `attach` writes into the main checkout's settings file from any worktree:
    # taken out of that file too where it is not this checkout's own and no other checkout is still
    # attached, the rest of it as it is. That file was read as `_plugin_keys` reads it, above.
    if plugin is not None and plugin[1] != root.resolve() and POINTER_KEY in recorded.settings_keys:
        only = replace(recorded, allow=(), entries={}, settings_keys=(POINTER_KEY,))
        _withdraw_settings(plugin[1], _planned_settings(plugin[1], only))
    # The mirror of `_link_everywhere`, and it had the mirror defect: `detach_main` was applied
    # to `--root` and the loop then skipped the owning checkout unconditionally, so a detach run
    # from a linked worktree withdrew that worktree's tree twice and left the main checkout's
    # link tree — and its harness link — in place. `_checkouts` is the one spelling of "every
    # checkout, owner first, each exactly once" that both halves now read, and `_reach` says
    # which of them this run withdraws from.
    revoked: list[Path] = []
    for tree in harnessed:
        revoked += detach_main(
            tree,
            config,
            machine=machine,
            home=home,
            targets=targets[tree],
            keep_tree=tree not in trees,
        ).revoked
    # Before the exclude block goes: Claude Code takes the plugin's entries, which name the id, out
    # of the settings file the block hides, and it does so after this run's own withdrawal from
    # that file, which would otherwise write them back. A file that still names the id stops the
    # run here, with the exclude block, the ledger and the render kept.
    if plugin is not None:
        _withdraw_plugin(*plugin, runner)
    removed = False
    if not kept and delivery is not None and (fsops.is_dir(delivery) or fsops.is_symlink(delivery)):
        _remove_render(delivery)
        removed = True
    # The composed store the pointer named, derived from the id as the render is: its links, then
    # the directory where nothing else is left.
    store_kept = False
    if not kept and id is not None and delivery is not None:
        store_kept = not withdraw_composed(id)
    if hidden is not None:
        exclude.write(hidden)
    memory = _withdraw_memory_directories(root, trees, config, recorded)
    fsops.remove_within(root, ATTACH_LEDGER)
    # Last, because the ledger lives in one of them.
    directories = _withdraw_directories(root, recorded)
    return Detached(
        allow_removed,
        entries,
        tuple(rules_removed),
        recorded.settings_keys,
        Links([], revoked),
        directories + memory,
        hidden is not None,
        kept,
        root.resolve() not in trees,
        removed,
        store_kept,
    )
