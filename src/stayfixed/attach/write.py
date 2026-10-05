"""What `stayfixed attach` actually writes, in the order the refusals have to happen in.

**Four things this module does not build.**

*Not a hook-entry merger.* `stayfixed.scaffold` already exports `apply_entries`, `mark` and
`owned_ids`, and it inherits the two rules a hand-rolled merge gets wrong: a group mixing a
marked entry with a foreign one is **split, not replaced**, and a shape it cannot read is
**refused, not filtered**, because "dropping a group it did not recognise deletes somebody
else's hook and says nothing".

*Not the scaffold engine's `plan`/`apply` for the settings file.* The engine stamps a digest of
the document into the **committed** `.stayfixed/manifest.json`, which would publish a digest of
the owner's personal allow rules to every collaborator. The pure functions are called
instead — document string in, document string out, no manifest — and the ledger below takes
the manifest's place. This is the one place where refusing an existing mechanism is right.

*Not one id for every entry.* `owned_ids` returns `dict[str, str]`, so one shared
`stayfixed:overlay` id yields exactly one provenance row however many entries there are, and the
same id under two events keeps only the last. `permissions.overlay_entries` numbers them
`overlay-<event>-<n>`, one per entry.

*Not a pretence that the two halves are symmetric.* A hook entry's `# stayfixed:<id>` lives
inside its command string, so it has an in-band witness that survives the file being edited by
hand. A `permissions.allow` string cannot carry one — `scaffold.mark` appends to a *command* —
so an allow rule has exactly **one** witness, the ledger at `.stayfixed/local/attach.json`, and
`detach` is only ever as good as that file.

**The ledger is written under `.stayfixed/local/`, and the `.gitignore` region goes first.** The
repository has no `.stayfixed` line today and nothing in this area ships one, so without that
region `attach` drops the owner's personal allow rules into a tracked-by-default path. It is
written before the ledger rather than beside it, so the ledger is never in a tracked path even
for an instant — and if the region cannot be written, writing the ledger would be a leak, so the
answer is a refusal rather than a warning. It is written only when git does not already ignore
both paths it lists, so a checkout that hides them another way reaches no tracked file here; the
rest of what `attach` places is hidden through `info/exclude` instead (`attach.exclude`).

**Every write goes through a primitive that already exists.** `fsops.write_within(root, …)` for
everything inside the project and `fsops.write_within(overlay, …)` for the binding record — the
overlay root is a root, so there is no carve-out to take anywhere here.
"""

from __future__ import annotations

import datetime
import json
import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from stayfixed import fsops, tomlout
from stayfixed.attach import exclude
from stayfixed.attach.binding import (
    Binding,
    read_binding,
    refuse_unless_overlay,
    refuse_unless_share_can_exist,
    unlinked_groups,
)
from stayfixed.attach.permissions import (
    CODEX_RULES,
    LOCAL_SETTINGS,
    PermissionDiff,
    codex_rules,
    diff_permissions,
    local_document,
    marked_commands,
    overlay_entries,
    settings_document,
)
from stayfixed.config.layout import (
    ATTACH_LEDGER,
    IGNORE_BODY,
    IGNORE_REGION,
    LOCAL_STATE_PATHS,
)
from stayfixed.config.loader import UNPARSEABLE, load
from stayfixed.config.paths import PathEscape, contained
from stayfixed.config.schema import Config
from stayfixed.errors import Failure, Refusal
from stayfixed.fsops import UnsafePath
from stayfixed.gitenv import answer_lines, git_run
from stayfixed.guards.api import hooks_dir
from stayfixed.jsonobject import json_object
from stayfixed.memory.api import (
    COMMON_GROUP,
    DIFFERENT_REMOTE,
    MISMATCH,
    NO_ORIGIN,
    NO_REMOTE,
    PROJECT_RECORD,
    PROJECTS,
    STORE_DIR,
    Links,
    PartialLink,
    approval_recorded,
    attach_main,
    detach_main,
    harness_anchor,
    harness_link_needed,
    harness_memory_path,
    link,
    linked_names,
    main_checkout,
    read_binding_record,
    require_readable_record,
    resolve,
)
from stayfixed.overlay.api import PRE_COMMIT_CONFIG, PRE_COMMIT_HOOK
from stayfixed.printed import answered
from stayfixed.runner import Runner
from stayfixed.scaffold import (
    EntriesError,
    Manifest,
    RegionError,
    Style,
    apply_entries,
    drop,
    mark,
    marker_id,
    owned_ids,
    upsert,
)

LEDGER_FORMAT = 1
GITIGNORE = ".gitignore"
# `attach`'s fallback for the one link that leaves stayfixed's own channel: a settings-file value
# is subject to workspace trust and a link is not, so the symlink is preferred and this is taken
# only when it cannot be made.
FALLBACK_KEY = "autoMemoryDirectory"
# The fourth, asked just after the fifth (a checkout with no `origin`, `memory.api.NO_REMOTE`),
# and above every write for the same reason. The binding record is UTF-8 TOML, and an `origin`
# URL git prints in other bytes cannot be written into it: `_record_binding`, the last write,
# would raise `UnicodeEncodeError` after the ignore region, the Codex rules, the settings merge
# and the ledger. `fsops.utf_8_name` asks it. The URL is not quoted: a remote URL is
# repository-authored.
ORIGIN_NOT_TEXT = (
    "this repository's `origin` URL is not UTF-8 text, so the overlay cannot record it; set it "
    "again with `git remote set-url origin URL`"
)
# The seventh, and the first of the two whose trigger is repository-authored
# (`memory.groups` reaches no guard of its own). One constant for the check above every write
# and for the `O_NOFOLLOW` walk that is the floor under it, because two spellings of one
# refusal are two refusals to keep in step. The entry is never quoted back into it.
GROUP_ESCAPES = (
    "a memory.groups entry does not stay inside this project's share of the overlay, so it is "
    "refused rather than created"
)
# The ninth, and the second of the two whose trigger is repository-authored. Its anchor is
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
class Attached:
    """What one `attach` changed.

    Nothing here is repository-authored. `notes` is the one field that carries text from
    outside this process -- what `pre-commit install` printed -- and that is this machine's
    tool answering in the overlay, not the clone's bytes.
    """

    settings_written: bool
    rules_written: tuple[str, ...]
    binding_recorded: bool
    notes: tuple[str, ...]
    links: Links


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
    - `settings_keys` may only be `autoMemoryDirectory`, the one key `_harness_fallback` writes.

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
    in, so `doctor` can compare the two without a translation in between.
    """

    store: str
    allow: tuple[str, ...]
    entries: dict[str, str]
    rules: tuple[str, ...]
    settings_keys: tuple[str, ...]
    directories: tuple[str, ...] = ()
    memory_parents: tuple[str, ...] = ()
    memory_created: bool = False


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
    foreign += sum(1 for key in keys if key != FALLBACK_KEY)
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
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise Failure(
            f"{ATTACH_LEDGER} is not there, so nothing records what `stayfixed attach` added to "
            f"this repository; there is no safe way to guess it from the settings file"
        ) from exc
    except OSError as exc:
        raise Failure(f"{path} cannot be read: {exc}") from exc
    except UnicodeDecodeError:
        raise Failure(f"{path} is not UTF-8 text") from None
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
    )


def _existing_ledger(root: Path) -> AttachLedger | None:
    """The ledger, or `None` when there is none — the one caller that may carry on without it."""
    if not (root / ATTACH_LEDGER).is_file():
        return None
    return ledger(root)


def _planned_ignore_region(root: Path) -> str | None:
    """`.gitignore` with the region that makes `.stayfixed/local/` untracked, or `None` when it
    holds the region already; a refusal when the file cannot be read.

    One `scaffold.upsert` with the `stayfixed:ignore` marker: everything outside the region comes
    back out as it went in, which is the whole point of a managed region and the reason this
    does not need the scaffold engine's manifest. Asked while the run is planned, and only when
    git does not already ignore both `LOCAL_STATE_PATHS`; `_write_ignore_region` writes the
    answer.
    """
    path = root / GITIGNORE
    try:
        text = path.read_text(encoding="utf-8") if path.exists() else ""
    except UnicodeDecodeError:
        raise Refusal(
            f"{GITIGNORE} is not UTF-8 text, so `.stayfixed/local/` cannot be made untracked — and "
            f"writing the attach ledger into a tracked path would publish your personal allow "
            f"rules to every collaborator"
        ) from None
    except OSError as exc:
        raise Refusal(
            f"{GITIGNORE} cannot be read ({exc}), so `.stayfixed/local/` cannot be made "
            f"untracked — and writing the attach ledger into a tracked path would publish "
            f"your personal allow rules to every collaborator"
        ) from exc
    updated = _in_gitignore(upsert, text, IGNORE_REGION, IGNORE_BODY, Style.HASH)
    return None if updated == text else updated


def _in_gitignore(region: Callable[..., str], *args: object) -> str:
    """`upsert` or `drop` over `.gitignore`, with the file named in a refusal: "region 'ignore' is
    opened or closed twice" said which region and never which file."""
    try:
        return region(*args)
    except RegionError as exc:
        raise RegionError(f"`{GITIGNORE}`: {exc}") from exc


def _write_ignore_region(root: Path, updated: str) -> None:
    """Write the `.gitignore` `_planned_ignore_region` decided on, or refuse: writing the ledger
    into a tracked path would be a leak, so a failure here is never a warning."""
    try:
        fsops.write_within(root, GITIGNORE, updated)
    except OSError as exc:
        raise Refusal(
            f"{GITIGNORE} cannot be written ({exc}), so `.stayfixed/local/` cannot be made "
            f"untracked — refusing rather than leaving the attach ledger in a tracked path"
        ) from exc


def _allow_list(raw: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    permissions = raw.get("permissions", {})
    if not isinstance(permissions, dict):
        raise EntriesError(f"{LOCAL_SETTINGS}: 'permissions' is not an object")
    allow = permissions.get("allow", [])
    if not isinstance(allow, list) or not all(isinstance(rule, str) for rule in allow):
        raise EntriesError(f"{LOCAL_SETTINGS}: 'permissions.allow' is not a list of strings")
    return dict(permissions), list(allow)


def _merged_settings(document: str, diff: PermissionDiff, binding: Binding) -> str:
    """The local settings document with the overlay's rules and entries merged in.

    The allow rules are appended in order and the hook entries go through
    `scaffold.apply_entries`, which is what keys them by marker.
    """
    wanted = overlay_entries(binding)
    if not diff.added_allow and not wanted and not owned_ids(document):
        # Nothing to add, so nothing is touched. A rewrite here would reformat a file the owner
        # owns, on a run that changed nothing, and report itself as a write.
        #
        # **`owned_ids` is the third clause and not decoration.** `apply_entries(document, {})`
        # is the engine's *removal* path, and an overlay that has had its last hook entry taken
        # out reaches here with `wanted` empty — so without this the marked entry stays in the
        # file and goes on firing, while the ledger (built from the overlay, not unioned) loses
        # it. `doctor._hook_entries` then reads an entry claiming the marker and named in no
        # ledger, goes RED, and tells the owner to remove an entry stayfixed installed. This is
        # the twin of the case already fixed for `rules`, answered on the settings side rather
        # than in the ledger, because the honest repair is to take the entry back out.
        return document
    raw = settings_document(document)
    permissions, allow = _allow_list(raw)
    allow += [rule for rule in diff.added_allow if rule not in allow]
    if allow or permissions:
        permissions["allow"] = allow
        raw["permissions"] = permissions
    return apply_entries(json.dumps(raw, indent=2) + "\n", wanted)


def _codex_rule_texts(binding: Binding) -> tuple[tuple[str, str], ...]:
    """Each overlay standing rule's target under `.codex/rules/` and its text, read while the run
    is planned.

    Kept apart from the Claude settings merge because the two harnesses fail differently and a
    shared path would hide which. The list itself is `permissions.codex_rules`, so that
    `attach --check` reports exactly the files `attach` then writes rather than a second
    enumeration that could disagree with this one. Every source is read and decoded here and none
    while copying: a source that is not UTF-8, met while copying, would stop the copy after
    `.gitignore`, the exclude block and the rules before it were written, with the partial copies
    hidden by the block and no ledger for `detach` to remove them by.
    """
    texts: list[tuple[str, str]] = []
    for target, source in codex_rules(binding):
        # The overlay is the owner's, so its path may print.
        try:
            texts.append((target, source.read_text(encoding="utf-8")))
        except UnicodeDecodeError:
            raise Failure(f"{source} is not UTF-8 text, so nothing was written") from None
        except OSError as exc:
            raise Failure(
                f"{source} cannot be read ({fsops.said(exc)}), so nothing was written"
            ) from exc
    return tuple(texts)


def _record_binding(binding: Binding) -> bool:
    """Write `projects/<name>/project.toml`, keeping the first-attach date it already carries.

    The record is the owner's consent — the bound remote URL and the first-attach date — so a
    repository the overlay already records correctly is left alone — re-stamping the date on
    every attach would turn a fact into a timestamp of the last run.
    """
    if binding.state != MISMATCH and binding.recorded is not None:
        return False
    if binding.remote is None:
        # The floor under `attach`'s own hoisted copy, never the first place this is asked. A
        # `Refusal` reaching here means the hoist above drifted — and by then the ignore region,
        # `.codex/rules/`, the settings merge and the ledger have all been written, which is
        # exactly the state the hoist exists to prevent.
        raise Refusal(NO_REMOTE)
    relative = f"{PROJECTS}/{binding.project}/{PROJECT_RECORD}"
    first = _first_attach(binding.overlay / relative) or datetime.date.today().isoformat()
    # `tomlout` and not an f-string: the value is a git remote URL, which is repository-authored
    # (principle 5), and one carrying a quote and a newline would write further keys into the
    # record that decides what `attach` trusts.
    fsops.write_within(
        binding.overlay,
        relative,
        tomlout.dumps({"": {"remote": binding.remote, "first_attach": first}}),
    )
    return True


def _first_attach(record: Path) -> str | None:
    if not record.is_file():
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
    if not (binding.overlay / PRE_COMMIT_CONFIG).is_file():
        return None
    try:
        installed = (hooks_dir(binding.overlay) / PRE_COMMIT_HOOK).exists()
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
    """
    return tuple(name for name in CREATED_DIRS if not (root / name).is_dir())


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
    return tuple(name for name in _memory_parents(config) if not (root / name).is_dir())


def _memory_absent(root: Path, config: Config) -> bool:
    """Whether this checkout has no `paths.memory` directory, asked before the first write for the
    reason `_absent_directories` is: an empty one the owner made is theirs, and survives."""
    return not (root / config.paths.memory).is_dir()


def _placed(binding: Binding, config: Config, *, settings: bool) -> tuple[str, ...]:
    """Every path this run puts into the project besides the ledger, which `.gitignore`'s region
    covers: the link tree (`linked_names`, the same list `attach_main` walks), each rule copy
    `codex_rules` enumerates, and the settings file when `settings` says this run writes it or an
    earlier one did. These are what `attach.exclude` hides and holds inside the project.

    **Only what is written, because each candidate is also a containment refusal.** A `.claude`
    the owner keeps elsewhere and links in is an ordinary layout, and an overlay that grants
    nothing gives this run nothing to write there — so the settings file on such a run is neither
    a reason to refuse nor a line in the block for a file `attach` never made."""
    return (
        *(f"{config.paths.memory}/{name}" for name in linked_names(config)),
        *(target for target, _ in codex_rules(binding)),
        *((LOCAL_SETTINGS,) if settings else ()),
    )


def _fallback_possible(
    root: Path, config: Config, *, machine: Path | None, home: Path | None
) -> bool:
    """Whether this run may take the settings-file fallback, answered before its first write.

    `_harness_fallback` writes the settings file when the gate wants the harness link and the
    link is not there to point at the store. `_link` leaves only one thing standing where the link
    goes — a real entry, which is what the harness makes of the path on its own — so a path that
    is absent or already a symlink is a link this run makes, and no fallback. Where a real entry
    sits, the gate is asked of the store as it resolves now, and of a store that does not resolve
    yet as the next paragraph says. The two agree with `_harness_fallback` by construction, so its
    write is never one this run did not hold to the project and hide above its first write.

    **A first attach is answered too, without the link tree.** `resolve` needs the tree this run
    is about to build, so before it exists the gate is asked the one question it can be: does
    this machine record any approval for a store at `paths.memory`? None is a gate that cannot
    open, which is the ordinary first attach; a record, current or stale, is one that might, and
    is answered "possible", because this answer decides a refusal.
    """
    harness = harness_memory_path(root, home)
    if harness.is_symlink() or not harness.exists():
        return False
    store = resolve(root, config, machine=machine)
    if store is None:
        return approval_recorded(root / config.paths.memory, machine)
    return harness_link_needed(store, config)


def _settings_containable(root: Path) -> bool:
    """Whether `.claude/settings.local.json` stays inside the project: `False` for a `.claude`
    linked in from elsewhere, where no write of this run's may land."""
    try:
        contained(root, LOCAL_SETTINGS)
    except PathEscape:
        return False
    return True


def _settings_placed(previous: AttachLedger | None, document: str) -> bool:
    """Whether an earlier attach put something of its own into the settings file: a rule or an
    entry its ledger records, or the fallback key the file still holds."""
    if previous is not None and (previous.allow or previous.entries or previous.settings_keys):
        return True
    return bool(document.strip()) and FALLBACK_KEY in settings_document(document)


def _write_ledger(root: Path, planned: AttachPlan, settings_keys: tuple[str, ...]) -> None:
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
    # `scaffold.marker_id` and not a second parser for the marker: the ledger's keys have to be
    # the keys `owned_ids` answers in, or `doctor`'s provenance row compares two spellings.
    # A named helper and not a walrus in the comprehension: a walrus binds in the *enclosing*
    # scope, so `(claimed := ...)` here quietly overwrote the allow list two lines above and the
    # ledger recorded a marker id as a permission rule.
    entries = {
        found: event
        for event, command in marked_commands(overlay_entries(binding))
        for found in (marker_id(command),)
        if found is not None
    }
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
        "entries": entries,
        "rules": placed,
        "settings_keys": list(settings_keys),
        "directories": [name for name in CREATED_DIRS if name in made],
        "memory_parents": sorted(above, key=lambda name: (-name.count("/"), name)),
        # The same union once more: a second attach finds the directory the first one made.
        "memory_created": planned.memory_created
        or (previous is not None and previous.memory_created),
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


def _worktrees(root: Path) -> list[Path]:
    """Every checkout of this repository, from `git worktree list --porcelain`.

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
        if any(line == "prunable" or line.startswith("prunable ") for line in lines):
            continue
        found.extend(
            Path(line[len("worktree ") :]) for line in lines if line.startswith("worktree ")
        )
    return found


def _checkouts(root: Path) -> list[Path]:
    """Every checkout of this repository, the one that owns the store first, each exactly once.

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
    found = [owner]
    seen = {owner}
    for tree in _worktrees(root):
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
        created += more.created
        revoked += more.revoked
    return Links(created, revoked)


def _keys_in(document: str) -> tuple[str, ...]:
    """The settings keys `attach` owns that a settings document holds."""
    return (FALLBACK_KEY,) if FALLBACK_KEY in settings_document(document) else ()


def _recorded_keys(root: Path) -> tuple[str, ...]:
    """The settings keys `attach` owns that `.claude/settings.local.json` holds *right now*.

    Read back from the file rather than carried out of the run that wrote it, because
    `settings_keys` is a claim about state that persists. Carried out of the run, it would be the
    key only when this run had just written it — so the second attach after a fallback would
    reset the record to `[]` while the key was still in the file, and `detach` would then leave
    it there for good.
    """
    return _keys_in(local_document(root))


def _fallback_wanted(
    root: Path, config: Config, *, machine: Path | None, home: Path | None
) -> str | None:
    """The store directory the fallback would record, or `None` when the gate does not want the
    harness link or the link already points at the store."""
    store = resolve(root, config, machine=machine)
    if store is None or not harness_link_needed(store, config):
        return None
    harness = harness_memory_path(root, home)
    if harness.is_symlink() and harness.readlink() == store.path.resolve():
        return None
    return str(store.path.resolve())


# Said instead of taking the fallback where it would write through a `.claude` linked in from
# elsewhere. Nothing in it is repository-authored, so it prints.
FALLBACK_UNAVAILABLE = (
    "the harness memory link could not be created, because a real directory already sits where "
    "it goes, and the settings-file fallback was not taken, because this checkout's `.claude` is "
    "linked in from elsewhere and stayfixed writes nothing through it; move that directory "
    "aside, or make `.claude` a real directory, then run `stayfixed attach` again"
)


def _harness_fallback(
    root: Path, config: Config, *, machine: Path | None, home: Path | None
) -> tuple[str, ...]:
    """The settings-file fallback, taken only when no symlink could be made — and withdrawn here.

    The link is preferred because a settings-file value is subject to workspace trust and a link
    is not. It cannot be made on a filesystem that refuses symlinks, or where a real directory
    already sits at the path — the case `worktree._link` refuses to clobber. The gate
    is asked with the same predicate `worktree.harness_link_needed` answers for the link itself,
    so a store the owner has not approved gets neither channel.

    **And it is asked in both directions, in the same call**, which is `memory/worktree`'s rule
    one hop over: "a gate evaluated once, at creation, over state that persists is not a gate".
    A settings value is exactly such state, and this is the same channel that module calls "the
    one hop that leaves stayfixed's gate" — the harness's own native reader, outside every
    delimiter and every trust record this area controls. `_apply_harness_link` revokes the
    *symlink* when the record lapses; a key that outlived it would let a `git pull` that added one
    note shut every channel except the one pointing the harness straight at the new bytes.

    The two arms that return without writing are the two that would otherwise leak: the link is
    not needed, and the symlink exists so the fallback is not warranted. Both take the key back
    out. The answer is what the file holds afterwards, so the caller's ledger is the file's own
    state rather than a memory of this run.

    **This is the one place `attach` removes a file**, and it is worth saying out loud rather
    than leaving to be discovered. Withdrawing the key can empty `.claude/settings.local.json`,
    and `{}` is not what that file looked like before the fallback was taken — it is a file
    `attach` created and this is the last thing it takes away, which is the rule
    `_withdraw_settings` already applies on the `detach` side and what keeps the round trip
    byte-for-byte. It can only fire when stayfixed's own key was all the file held, so nothing of
    the owner's is ever what goes.
    """
    wanted = _fallback_wanted(root, config, machine=machine, home=home)
    document = settings_document(local_document(root))
    if document.get(FALLBACK_KEY) == wanted:
        # Includes the ordinary case where the key is absent and is not wanted: nothing to do,
        # and rewriting a file the owner owns on a run that changed nothing is a write.
        return _recorded_keys(root)
    if wanted is None:
        document.pop(FALLBACK_KEY, None)
    else:
        document[FALLBACK_KEY] = wanted
    if document:
        fsops.write_within(root, LOCAL_SETTINGS, json.dumps(document, indent=2) + "\n")
    else:
        # `{}` is not what the file looked like before the fallback was taken, and a document
        # holding only this key is one `attach` created — the same rule `_withdraw_settings`
        # applies when `detach` empties it.
        fsops.remove_within(root, LOCAL_SETTINGS)
    return () if wanted is None else (FALLBACK_KEY,)


# Said when the harness memory link was left out because the gate withheld it, which in overlay
# mode it does until the owner approves the store: the link tree sits inside the repository.
# Nothing in it is repository-authored, so it prints.
HARNESS_WAITS = (
    "the harness memory link was not created, because the link tree it would expose sits inside "
    "this repository and has no approval yet; run `stayfixed memory trust --in-repo-memory`, "
    "then `stayfixed attach` again"
)


def _harness_waits(root: Path, config: Config, *, machine: Path | None) -> bool:
    """Whether the gate kept the harness link from being made: `harness_link_needed`, asked
    exactly as `_apply_harness_link` asks it, of the store the run just linked."""
    store = resolve(root, config, machine=machine)
    return store is not None and not harness_link_needed(store, config)


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
    absent: tuple[str, ...]
    parents: tuple[str, ...]
    memory_created: bool
    # The settings document to write, or `None` when the merge leaves it as it is.
    settings: str | None
    carried: tuple[str, ...]
    # `.gitignore` with its region, or `None` when it needs none.
    ignore: str | None
    hidden: exclude.ExcludeWrite | None
    # Each `.codex/rules/` target and the text to copy there.
    rules: tuple[tuple[str, str], ...]
    checkouts: tuple[Path, ...]


def attach(
    root: Path,
    *,
    store: Path,
    machine: Path | None,
    confirmed: bool,
    trust_remote: bool,
    runner: Runner,
    home: Path | None,
) -> Attached:
    """Bind this repository to the overlay, merge what the overlay grants, and link the notes in.

    The order below is the order they are enumerated in: read the binding, which already
    refuses a store outside the machine-recorded overlay; refuse a repository whose
    `memory.mode` is not `overlay`, which is numbered with none of the nine because it is about
    the configuration and not about this binding; compute the diff; refuse a widening
    without `confirmed`; refuse a checkout with no `origin`; refuse a mismatch without
    `trust_remote`; refuse an `origin` URL that is not UTF-8 text; read the existing ledger, which
    refuses one no attach could have written; refuse a `memory.groups` entry that leaves this
    project's share of the overlay; refuse a harness anchor this machine cannot vouch for;
    refuse a group that never moved into the overlay; ask git what it already hides, which
    refuses a `check-ignore` with no answer, a placed path that leaves the project and a
    symlinked or unwritable exclude file; read the overlay's rule sources, the checkouts and the
    machine's trust record, which the writes below would otherwise read for themselves;
    then write, `.gitignore` first when it needs its region at all, so the ledger is never in a
    tracked path even for an instant, and the exclude block before any file it hides.

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
    needs neither, follows. Nothing writes between them; every one of the nine is above the
    first write, which is the property that matters and the one the tests assert.

    **A tenth refusal is above every write and is not one of the nine**, because it is not a
    check this function makes: `unlinked_groups` contains each `<paths.memory>/<group>` against
    `root` before it counts, and a `PathEscape` out of it propagates as the refusal it already
    is — `paths.memory` may itself be a symlink, and then every group escapes at once. It is
    enumerated nowhere because it has no ordinal of its own; it is named here so that the count
    above reads as "nine checks" rather than as "nine ways this can refuse".

    **All nine checks are above every write, and three of them were not.** The no-`origin` one
    lived in `_record_binding`, the ledger's in `_write_ledger`, and the `memory.groups` one in
    `_prepare_store` — which runs after the ignore region, the Codex rule files, the settings
    merge, the ledger *and* the overlay's binding record. Each could exit 2 having written three,
    four or five artifacts, with `doctor._attached` — which keys on the ledger existing — then
    reporting the repository attached, and in the third case *bound*, because the record had been
    written too. A refusal that leaves a repository looking attached is not a refusal. The second
    of the three arrived in the commit that wrote that sentence down, and the third was found by
    asking whether the shape was dead or only its named instances were.

    The binding record is written before the links, because `memory.store` checks it and a
    store whose record is missing does not resolve — and `attach_main` resolves as its last
    step. The ledger is written before the links too, so a `PartialLink` half way through leaves
    behind a repository `detach` can still clean up.

    `runner` and `home` are keyword-**required** rather than defaulted so that no test can reach
    a real `pre-commit` or the developer's own `~/.claude/`. A default here would leave that as
    a convention, which is the thing the rule exists to replace: while this module was being
    written, every call that omitted `home` computed a path under the real home directory.
    """
    planned = _plan(
        root,
        store=store,
        machine=machine,
        confirmed=confirmed,
        trust_remote=trust_remote,
        home=home,
    )
    return _carry_out(root, planned, machine=machine, runner=runner, home=home)


def _plan(
    root: Path,
    *,
    store: Path,
    machine: Path | None,
    confirmed: bool,
    trust_remote: bool,
    home: Path | None,
) -> AttachPlan:
    """Every read, decode and check `attach` makes, in the order `attach` enumerates them, and
    nothing written: what it returns is all `_carry_out` may act on."""
    # One load for the whole run, handed to `read_binding` rather than left for it to make a
    # second of. `permissions.check` took this ruling for `--check` -- "two loads could
    # disagree, and a `--check` whose two halves read different documents is exactly what it
    # exists to rule out" -- and the writing command has the stronger version of that argument:
    # a `--check` that read two documents reports the wrong thing, while an `attach` that reads
    # two writes under the wrong one. `read_binding` loads on the line it is called from, so
    # nothing moves in the order the refusals happen in; what changes is that `project.name`,
    # `memory.groups` and `paths.memory` are read once and the refusals below are about the
    # same document the binding was read under.
    config = load(root, machine=machine)
    binding = read_binding(root, store=store, machine=machine, config=config)
    # Beside the binding's own refusals and above every write: nothing below applies to a
    # repository whose notes do not live in the overlay, and every write below would be one
    # `attach_main` then refuses after the fact. After `read_binding`, so a `--store` outside
    # the recorded overlay is still refused for that reason first.
    refuse_unless_overlay(config)
    # Beside the binding too: a `project.name` no directory under the overlay can carry leaves the
    # binding record and the group directories nowhere to go, and the overlay's sources read under
    # it answer "none" rather than refusing, so nothing below would ask before writing.
    refuse_unless_share_can_exist(binding)
    diff = diff_permissions(root, binding)
    if diff.widens and not confirmed:
        raise Refusal(
            f"attaching would add {len(diff.added_allow)} allow rule(s) and "
            f"{len(diff.added_hooks)} hook entr(ies) to {LOCAL_SETTINGS}, which grants "
            f"capability. Read the diff with `stayfixed attach --check` and pass --yes to "
            f"confirm it"
        )
    # The fifth refusal, a checkout with no `origin`, is its own state (`memory.store.binding_state`
    # asks it first) and is refused with the sentence every other surface says. Read as a
    # mismatch, its answer would be `--trust-remote`, which then refuses for the missing `origin`.
    # Kept above every write rather than in `_record_binding`, which runs after the ignore region,
    # the Codex rules, the settings merge and the ledger: refused there, it would leave four
    # artifacts behind and `doctor._attached` would report the repository attached.
    if binding.state == NO_ORIGIN:
        raise Refusal(NO_REMOTE)
    if binding.state == MISMATCH and not trust_remote:
        # The name is not quoted back, for the reason `permissions.check` states at length:
        # `project.name` is repository-authored and looser than the marker-id grammar `doctor`
        # already refuses to print, and a refusal built out of one is still one.
        raise Refusal(
            f"{DIFFERENT_REMOTE}; pass --trust-remote only if this checkout should be bound to it"
        )
    if binding.remote is not None and not fsops.utf_8_name(binding.remote):
        raise Refusal(ORIGIN_NOT_TEXT)
    # The seventh refusal, and it belongs here for the reason the six above it do; the sixth,
    # the ledger's, is read a few lines below and is above every write too. `ledger()` refuses
    # a ledger naming files or settings keys `attach` could not have written, and asked for by
    # `_write_ledger`, the fourth write of the run, it would let a clone that commits such a
    # ledger make `attach` write the ignore region, copy `.codex/rules/*` and merge
    # `.claude/settings.local.json` before exiting 2, with the committed ledger still on disk for
    # `doctor._attached` to read as "attached", and with `attach --check` reporting clean
    # beforehand because it does not read the ledger at all. The `Config` the two checks below
    # read is loaded at the top of this function, which is where the binding needs it anyway: a
    # check cannot happen above the writes while what it reads is loaded below them.
    _check_groups(binding, config)
    # The ninth, and the one whose remedy is an act no command performs: `attach` **links**,
    # so a group that is still a real directory under `paths.memory` has its notes in the
    # repository and its share of the overlay empty, and linking over it would leave every
    # session reading the repository's copy with the binding record, the settings merge and
    # the ledger already written. Above every write for that reason, and beside the
    # `memory.groups` containment because it reads the same repository-authored list -- the
    # anchor it is contained against is `root`, the checkout this command was pointed at,
    # which is why a repository cannot move the directory the count is taken under. A
    # `PathEscape` out of `unlinked_groups` propagates as the refusal it already is.
    real = unlinked_groups(root, config)
    if real:
        raise Refusal(REAL_DIRECTORIES.format(count=len(real)))
    # The eighth, and the one that is not about this repository at all: the anchor for the
    # harness memory link. `_apply_harness_link` asks it per checkout, which is one frame
    # below every write here — so a home directory that is not there, and the ordinary
    # dotfiles layout that links `~/.claude` elsewhere, were discovered after the ignore
    # region, the rule files, the settings merge, the ledger and the binding record. Measured:
    # `PartialLink` with three links made, then a `detach` that could not undo it.
    #
    # Asked for `root` and not for every checkout, because `_checkouts` needs `git` and is
    # read below: every checkout shares `.claude/projects` under one home, which is the
    # component a dotfiles manager links, so the layout that reaches production is refused
    # here for all of them. A `<slug>` component that is itself a symlink is left to the
    # per-call floor in `harness_anchor`, which is a `Refusal` either way.
    harness_anchor(root, home)
    # The ledger's own path, held to the project before anything reads or writes under it: it is
    # the one path this run writes inside the project that no candidate below names, so a
    # `.stayfixed` committed as a link is refused here by name rather than by the walk that
    # writes the ledger, after every write before it.
    contained(root, ATTACH_LEDGER)
    previous = _existing_ledger(root)
    # Above every write, because the first of them creates `.stayfixed/local/` and the answer
    # would then be wrong by exactly the directory this run brought into existence.
    absent = _absent_directories(root)
    parents = _absent_memory_parents(root, config)
    memory_created = _memory_absent(root, config)
    # What git already hides is asked here, above the first write, and decides both ignore
    # files: `.gitignore`'s region only when one of its two paths is still visible, and the
    # `info/exclude` block for the paths `attach` places that the owner's own excludes do not
    # hide (`exclude.unhidden_by_owner`). Each can refuse — git cannot answer, a path leaves the
    # project, the exclude file is a symlink — and each refusal is made while nothing has been
    # written.
    # The settings merge is computed here, before any write, because whether it writes decides
    # whether the settings file is a candidate at all (`_placed`).
    document = local_document(root)
    merged = _merged_settings(document, diff, binding)
    written = merged != document
    # The fallback's write is decided here too, for the same reason: it is the one write to the
    # settings file that happens after the links, and a refusal it earned there would come after
    # every write above it.
    possible = _fallback_possible(root, config, machine=machine, home=home)
    # A `.claude` linked in from elsewhere takes the fallback off the table rather than refusing
    # the run: the link is a layout the owner chose, and the note below says what the harness
    # link is missing and how to get it.
    fallback = possible and _settings_containable(root)
    settings = written or fallback or _settings_placed(previous, document)
    ignore = _planned_ignore_region(root) if exclude.unignored(root, LOCAL_STATE_PATHS) else None
    hidden = exclude.planned_block(root, _placed(binding, config, settings=settings))
    # The three reads the writes below would otherwise make for themselves, each of which can
    # refuse after the first write: the overlay's rule sources (a file that is not UTF-8), the
    # checkouts the link tree goes into (a `git` that cannot list them) and the machine's trust
    # record, which the index render and the harness link both read (a `trust.json` that does not
    # parse).
    rules = _codex_rule_texts(binding)
    checkouts = tuple(_checkouts(root))
    require_readable_record(machine)
    return AttachPlan(
        config=config,
        binding=binding,
        diff=diff,
        previous=previous,
        absent=absent,
        parents=parents,
        memory_created=memory_created,
        settings=merged if written else None,
        # What an earlier attach left in the settings file, carried into the ledger written
        # before the links so that a `PartialLink` half way through still leaves `detach` able to
        # remove it. Read off the document this run leaves there; the real answer is taken again
        # after the links, by the only function that can change it.
        carried=_keys_in(merged),
        ignore=ignore,
        hidden=hidden,
        rules=rules,
        checkouts=checkouts,
    )


def _carry_out(
    root: Path, planned: AttachPlan, *, machine: Path | None, runner: Runner, home: Path | None
) -> Attached:
    """Write what `_plan` decided: `.gitignore` first when it needs its region at all, so the
    ledger is never in a tracked path even for an instant, and the exclude block before any file
    it hides.

    What is still asked here is asked of what this run has just written, and cannot be asked
    before it: whether the store resolves once the link tree stands, and whether the harness link
    or the settings fallback is wanted once it does. A write that itself fails is the other way
    this can stop after the first write.
    """
    config, binding = planned.config, planned.binding
    if planned.ignore is not None:
        _write_ignore_region(root, planned.ignore)
    if planned.hidden is not None:
        exclude.write(planned.hidden)
    for target, text in planned.rules:
        fsops.write_within(root, target, text)
    rules = tuple(target for target, _ in planned.rules)
    written = planned.settings is not None
    if planned.settings is not None:
        fsops.write_within(root, LOCAL_SETTINGS, planned.settings)
    carried = planned.carried
    _write_ledger(root, planned, carried)
    recorded = _record_binding(binding)
    _prepare_store(binding, config)
    links = _link_everywhere(planned.checkouts, binding, config, machine=machine, home=home)
    notes = [] if (note := _secret_scan(binding, runner)) is None else [note]
    unavailable = False
    if _settings_containable(root):
        keys = _harness_fallback(root, config, machine=machine, home=home)
    else:
        keys = carried
        unavailable = _fallback_wanted(root, config, machine=machine, home=home) is not None
    if keys != carried:
        _write_ledger(root, planned, keys)
        written = True
    if keys:
        notes.append(
            f"the harness memory link could not be created, so {FALLBACK_KEY} was recorded in "
            f"{LOCAL_SETTINGS} instead; `stayfixed detach` removes it"
        )
    elif unavailable:
        notes.append(FALLBACK_UNAVAILABLE)
    elif _harness_waits(root, config, machine=machine):
        notes.append(HARNESS_WAITS)
    return Attached(written, rules, recorded, tuple(notes), links)


@dataclass(frozen=True)
class Detached:
    """What one `detach` withdrew. The binding record is not on this list, on purpose."""

    allow_removed: tuple[str, ...]
    entries_removed: tuple[str, ...]
    rules_removed: tuple[str, ...]
    settings_keys_removed: tuple[str, ...]
    ignore_region_removed: bool
    links: Links
    directories_removed: tuple[str, ...] = ()
    exclude_block_removed: bool = False
    # The block was left in place because another checkout of this repository still holds a
    # ledger: the exclude file is shared, and that checkout's files still need hiding.
    exclude_block_kept: bool = False


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
    """Take exactly the recorded rules, the marked entries and the fallback key back out.

    The allow rules come from the ledger and never from a guess at their content: that is the
    whole reason the ledger exists. The hook entries come out through `scaffold.apply_entries`
    with nothing wanted, which is the engine's own removal path — foreign entries keep their
    matcher and their position, and a group that mixes the two is split rather than dropped.
    """
    document = local_document(root)
    if not document.strip():
        return SettingsWithdrawal((), None)
    raw = settings_document(document)
    held = json.loads(json.dumps(raw))
    permissions, allow = _allow_list(raw)
    removed = tuple(rule for rule in recorded.allow if rule in allow)
    if permissions:
        permissions["allow"] = [rule for rule in allow if rule not in recorded.allow]
        raw["permissions"] = permissions
    for key in recorded.settings_keys:
        raw.pop(key, None)
    remaining = json.loads(apply_entries(json.dumps(_emptied(raw), indent=2) + "\n", {}))
    if remaining == held:
        return SettingsWithdrawal(removed, None)
    # `{}` is not what the file looked like before `attach`; a file holding nothing is one this
    # command created and is the last thing it takes away.
    return SettingsWithdrawal(removed, json.dumps(remaining, indent=2) + "\n" if remaining else "")


def _withdraw_settings(root: Path, planned: SettingsWithdrawal) -> tuple[str, ...]:
    """Write what `_planned_settings` decided."""
    if planned.text:
        fsops.write_within(root, LOCAL_SETTINGS, planned.text)
    elif planned.text is not None:
        fsops.remove_within(root, LOCAL_SETTINGS)
    return planned.removed


def _ignore_region_remainder(root: Path) -> str | None:
    """What `.gitignore` will hold once the attach region is dropped; `None` when nothing is
    there to drop.

    Asked **before the first withdrawal**, for the reason `_checkouts` is: `drop()` refuses a
    region that is opened or closed twice -- which a merge that kept both sides produces -- and
    asked at the write, that refusal would come after the settings, the rule files and every link
    tree were gone, with the ledger still present: `doctor` would report the repository attached,
    and a second `detach` would fail at the same line. A region that cannot be withdrawn is
    knowable at the start, and so is a file that cannot be read.
    """
    path = root / GITIGNORE
    if not path.is_file():
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise Failure(f"{GITIGNORE} cannot be read: {exc}") from exc
    except UnicodeDecodeError:
        raise Failure(f"{GITIGNORE} is not UTF-8 text") from None
    remaining = _in_gitignore(drop, text, IGNORE_REGION, Style.HASH)
    return None if remaining == text else remaining


def _footprint_owns_region(root: Path) -> bool:
    """Whether `stayfixed init`'s footprint, and not this attach, put the ignore region there.

    A region `init`'s footprint records is `init`'s, whichever command wrote it last: an
    ownership rule rather than a last-writer one. `init` records the same `stayfixed:ignore`
    block as a scaffold artifact, with the body imported from this module rather than respelled
    -- a second spelling would let each command report the other's region as hand-edited -- and
    that block is **committed**. Withdrawing it would take a line out of a tracked file this
    command never wrote, and leave `upgrade` reading the footprint as hand-edited on a
    repository nobody edited. `attach`'s own write stays and is idempotent; only the withdrawal
    asks this.

    The manifest and not a new ledger field: the ledger is untracked and per-checkout, while
    "whose region is this" has to answer the same for every clone of the project. A repository
    with no manifest is one no `init` has set up -- the state every attach before `init` shipped
    leaves behind -- and its region is withdrawn exactly as it always was.

    **A manifest this cannot read answers "not mine", and that is the whole of the ruling.**
    `.stayfixed/manifest.json` is **tracked** -- `IGNORE_BODY` covers `.stayfixed/local/` and
    `.stayfixed/assessment.json` and nothing else -- so a clone commits it, and `Manifest.read`
    raises `ManifestError` for one that is unreadable, is not a JSON object, or declares a
    `format` past this stayfixed's -- and `PathEscape` for one committed as a symlink out of the
    root. `attach` never reads the file, so such a clone attached
    cleanly, merged the owner's allow rules and hook entries, and then made the **withdrawal**
    exit 2 on every run for ever: a repository a clone chose could keep the command that undoes
    an attach from ever completing. Nothing destructive had happened first, because this
    question is asked above every withdrawal -- which is exactly why refusing here is the wrong
    answer. The remedy would be to delete a tracked file out of somebody else's repository, and
    a `detach` that cannot run until you do that is still a `detach` a repository disabled.

    So an unreadable manifest is not a claim of ownership this command will act on, and it is
    not a claim of ownership this command will act *against* either: it leaves the region where
    it is -- the conservative half, since the block may well be the footprint's -- and finishes
    the detach. `Detached.ignore_region_removed` is `False`, which `run_detach` reports, and no
    sentence anywhere says *why* it was left, so nothing here becomes untrue. The remaining
    cost is one block in `.gitignore` that `stayfixed init` or a hand edit clears, against a
    withdrawal that now always completes.
    """
    try:
        return Manifest.read(root).get("gitignore") is not None
    except Refusal:
        # `Refusal` and not `ManifestError`: a manifest committed as a symlink out of the root is
        # refused by `contained()` as a `PathEscape` before any byte is read, and it blocks the
        # withdrawal exactly as an unparseable one did.
        return True


def _withdraw_ignore_region(root: Path, remaining: str | None) -> bool:
    if remaining is None:
        return False
    # `if remaining` and not `if remaining.strip()`: a `.gitignore` that held only whitespace
    # before the attach is a file the owner had, and the round trip `docs/cli.md` promises is
    # byte-for-byte. Only a file the attach created -- nothing left once its region is gone --
    # is taken away.
    if remaining:
        fsops.write_within(root, GITIGNORE, remaining)
    else:
        fsops.remove_within(root, GITIGNORE)
    return True


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
        if name not in recorded.directories or not (root / name).is_dir():
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
    if target.is_symlink() or not target.is_dir():
        return False
    try:
        fsops.rmdir_within(base, name)
    except OSError:
        return False
    return True


def _withdraw_memory_directories(
    root: Path, checkouts: list[Path], config: Config, recorded: AttachLedger
) -> tuple[str, ...]:
    """The empty `paths.memory` directory, then the directories above it that the ledger records
    the attach as having created, in `root` alone; and the empty `paths.memory` in every other
    checkout.

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
    for tree in checkouts:
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


def _walked(root: Path, relative: str, *, what: str, where: str) -> None:
    """`fsops.check_within`, the removal's own walk, with its refusal said by name."""
    try:
        fsops.check_within(root, relative)
    except UnsafePath as exc:
        raise Refusal(LINKED_ON_THE_WAY.format(what=what, where=where)) from exc


def _refuse_unwithdrawable(
    root: Path,
    recorded: AttachLedger,
    checkouts: list[Path],
    config: Config,
    settings: SettingsWithdrawal,
) -> None:
    """Walk to every path the withdrawal writes or removes, before the first withdrawal: the
    settings file when it is rewritten, each recorded rule copy, each name of every checkout's
    link tree that is a link, and the ledger.

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
    for tree in checkouts:
        base = contained(tree, config.paths.memory, allow_final_symlink=True)
        for name in linked_names(config):
            try:
                target = contained(base, name, allow_final_symlink=True)
            except PathEscape as exc:
                raise Refusal(GROUP_LEAVES_TREE) from exc
            if target.is_symlink():
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
        if tree == own or not (tree / ATTACH_LEDGER).is_file():
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


def detach(root: Path, *, machine: Path | None, home: Path | None) -> Detached:
    """Remove exactly what `attach` added, reading the ledger for what that was.

    It does **not** touch `projects/<name>/project.toml`. That record is the owner's consent,
    not a piece of local state: deleting it would turn every later re-attach into a first
    attach, and re-ask a question that was already answered.

    `machine` and `home` are keyword-required, as they are on `attach` and on every helper here
    that takes them, and required rather than defaulted for the reason `attach` gives: a resolver
    without a machine file reads the developer's real `~/.config/stayfixed/`, and the harness link
    is under their real home. A caller that means "the machine owner's own" says `None` out loud.

    **What it may refuse on, and when.** `detach` cannot refuse the way `attach` does once it has
    begun: by the time it reaches the link tree the recorded allow rules, the marked hook entries
    and the `.codex/rules/` copies are already withdrawn, so a refusal there strands a
    half-detached repository. That is why `worktree.detach_main` makes `memory.mode` load-bearing
    through the target it derives rather than refusing on it.

    That is not licence to *discover* a precondition late. Everything structural this function
    can know before its first withdrawal is asked before it: the ledger (which refuses one no
    attach could have written), the configuration (whose loader validates `paths.*`), the
    settings document's own shape through `owned_ids`, whether the footprint owns the ignore
    region, `_checkouts`, which is the only thing here that needs `git`, the exclude block, what
    the settings file becomes (`_planned_settings`), and every path the withdrawal writes or
    removes, walked the way the write or removal walks it (`_refuse_unwithdrawable`). What is
    left after the first withdrawal is exactly what cannot precede it — a write that fails, and a
    component of the tree that changed between the check and the removal.

    **It needs the ledger in the checkout it is run from, and that is a limitation rather than a
    defect.** `.stayfixed/local/` is untracked and per-checkout, so a sibling worktree does not
    carry the ledger of the checkout an attach was run from and `detach --root <that worktree>`
    answers "no ledger". Without one there is nothing to reverse — guessing which allow rules
    were stayfixed's from their content is the heuristic the ledger exists to replace. So the
    reach this function has *once it starts* is every checkout (`_worktrees` below), and the
    place it may be started from is the one that holds the record.
    """
    recorded = ledger(root)
    config = load(root, machine=machine)
    entries = tuple(sorted(owned_ids(local_document(root))))
    # Asked before the first withdrawal, because it is the one thing here that needs `git` and a
    # `git` that cannot run is knowable at the start. Asked between the settings withdrawal and
    # the link trees, a machine whose `git` is gone would get exit 1 with the settings file and the
    # `.codex/rules/` copies already removed and every link still in place.
    #
    # The anchor for each checkout's harness link is the same shape and is asked in the same
    # breath, with this list as its argument: `detach_main` asks it per checkout from inside the
    # withdrawal, so left to it, a home whose `.claude` became a symlink after the attach — a
    # dotfiles manager adopting it is the ordinary way — would let a raw `UnsafePath` out of
    # `detach` as `internal error`, with the rule files already deleted and every later run
    # failing at the same line.
    checkouts = _checkouts(root)
    for tree in checkouts:
        harness_anchor(tree, home)
    ignore_remainder = None if _footprint_owns_region(root) else _ignore_region_remainder(root)
    # The `info/exclude` block is found above the first withdrawal for the same reason: `git`
    # names the file and a region opened twice refuses, and both are knowable now. It is shared
    # by every checkout while the ledger, the settings file and the `.codex/rules/` copies are
    # each checkout's own, so it stays while another checkout still holds a ledger: taking it
    # would show that checkout's settings file and rule copies in its `git status`.
    kept = _another_attached(root, checkouts)
    hidden = None if kept else exclude.withdrawn_block(root)
    settings = _planned_settings(root, recorded)
    _refuse_unwithdrawable(root, recorded, checkouts, config, settings)
    allow_removed = _withdraw_settings(root, settings)
    rules_removed: list[str] = []
    for rule in recorded.rules:
        if (root / rule).is_file():
            fsops.remove_within(root, rule)
            rules_removed.append(rule)
    # The mirror of `_link_everywhere`, and it had the mirror defect: `detach_main` was applied
    # to `--root` and the loop then skipped the owning checkout unconditionally, so a detach run
    # from a linked worktree withdrew that worktree's tree twice and left the main checkout's
    # link tree — and its harness link — in place. `_checkouts` is the one spelling of "every
    # checkout, owner first, each exactly once" that both halves now read.
    revoked: list[Path] = []
    for tree in checkouts:
        revoked += detach_main(tree, config, machine=machine, home=home).revoked
    region = _withdraw_ignore_region(root, ignore_remainder)
    if hidden is not None:
        exclude.write(hidden)
    memory = _withdraw_memory_directories(root, checkouts, config, recorded)
    fsops.remove_within(root, ATTACH_LEDGER)
    # Last, because the ledger lives in one of them.
    directories = _withdraw_directories(root, recorded)
    return Detached(
        allow_removed,
        entries,
        tuple(rules_removed),
        recorded.settings_keys,
        region,
        Links([], revoked),
        directories + memory,
        hidden is not None,
        kept,
    )
