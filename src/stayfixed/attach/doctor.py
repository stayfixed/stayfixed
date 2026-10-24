"""The binding's row in `stayfixed doctor`: the delivery and the harness memory path.

`attached` is this area's: it reads the attach ledger this area writes, asks this machine, through
this area's own `read_binding`, whether a binding stands behind it, and then reads what the binding
delivers: the render `attach` left under the machine's data directory and the paths it placed in
the checkout. `doctor`'s core discovers this module by name (CONTRIBUTING.md, "Areas") and imports
nothing of this area.

The overlay root is the core's answer, `Context.overlay_root`, resolved at most once per report
for every row that reads it. The note store comes from the `Answers` this module's `register()`
creates, one per report, so the row resolves it once. The attach ledger comes from the `_Ledger`
created beside it, so every question the row asks of the file gets one answer.

Every import sits inside a function body, as in a `hooks.py`: this module is imported by
discovery, and a module-level import here would be one more thing every `doctor` run loads
before it has asked anything.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final, NamedTuple

if TYPE_CHECKING:
    from pathlib import Path

    from stayfixed.attach.binding import Binding
    from stayfixed.attach.write import AttachLedger
    from stayfixed.config.schema import Config
    from stayfixed.doctor.api import Context, Contribution, Row, Status
    from stayfixed.memory.api import Answers, Store


# What `_ledger_state` answers beside a ledger: no file at the ledger's path, and a file there that
# cannot be read as one. Not statuses and not sentences: each reader decides both.
NO_LEDGER: Final = "no-ledger"
# Also the fourth of `_binding_answer`'s reasons, below: the same fact, and it is about the
# repository rather than about this machine.
UNREADABLE_LEDGER: Final = "unreadable-ledger"


def _ledger_state(root: Path) -> AttachLedger | str:
    """This repository's attach ledger, `NO_LEDGER` when the path names no file, or
    `UNREADABLE_LEDGER` when the file is there and cannot be read as a ledger.

    Three answers and not two. `ledger()` raises on a file that is not JSON, is not an object,
    or names something `attach` could not have written — and `.stayfixed/local/attach.json` is a
    path a clone can commit, because `.gitignore` does not untrack a committed file. Let through to
    the report's guard, that would let a repository force a row red with the detail "this check
    could not run: Failure" and a remedy that cannot help, on an installation with nothing wrong
    with it. The rows report the file instead.

    **Whether it is there is `fsops.names_regular_file`'s answer, and a path it cannot answer
    about is unreadable.** A clone can commit the ledger, or a directory above it, as a symbolic
    link to a name longer than a file name may be. Raised past this function to `_guarded`, the
    error's warning would stand in for the whole row, so a forged entry beside the link would lose
    its red in `hook-entries` and a real directory at the harness memory path its red in
    `attached`; read as no ledger, a file that is there would be skipped. A path that names no file
    — nothing there, a dangling link or a loop, or something other than a regular file — is no
    ledger.
    """
    from stayfixed.attach.write import ledger
    from stayfixed.config.layout import ATTACH_LEDGER
    from stayfixed.errors import Failure, Refusal
    from stayfixed.fsops import names_regular_file

    try:
        if not names_regular_file(root / ATTACH_LEDGER):
            return NO_LEDGER
    except OSError:
        return UNREADABLE_LEDGER
    try:
        return ledger(root)
    except (Failure, Refusal):
        return UNREADABLE_LEDGER


class _Ledger:
    """`_ledger_state` for one report, read on first use and never again.

    Created once per report by `register()`, so every question `attached` asks of the file gets
    one answer: no arm can read the ledger as there while another reads it as absent or
    unreadable.
    """

    def __init__(self) -> None:
        self._state: tuple[AttachLedger | str] | None = None

    def state(self, root: Path) -> AttachLedger | str:
        if self._state is None:
            self._state = (_ledger_state(root),)
        return self._state[0]


# The remedy for an overlay project record that cannot be read: it binds nothing, so the binding
# is read all the same, and the owner repairs the file, often a merge's conflict markers.
RECORD_REPAIR: Final = "repair that file in the overlay, often a merge's conflict markers"

# What the delivery is, as `_delivery` reads it: each clause is said in the row's detail beside the
# binding, formatted only with stayfixed's own words and paths this machine chose, through
# `printed.quoted`, and never with the whole binding id (`binding.short`). Red where nothing loads,
# or where git shows what `attach` keeps for this machine alone; a warning where what loads is not
# what the overlay holds now.
DELIVERY_IN_PLACE: Final = "the delivery is in place"
OVERLAY_GONE: Final = (
    "the overlay this machine records, {path}, is not there, so the delivered hooks that run its "
    "scripts have nothing to run"
)
PLACED_TRACKED: Final = "this repository tracks {paths}, which attach placed for this machine alone"
PLACED_SHOWN: Final = (
    "git would not ignore {paths}, which attach placed for this machine alone: a `.gitignore` line "
    "starting with `!` re-includes it"
)
PLACED_UNASKED: Final = (
    "git could not say whether the paths attach placed are tracked or ignored, or whether a "
    "tracked file names the delivery"
)
ID_COMMITTED: Final = (
    "a tracked file names this checkout's delivery, and with it the binding id, which never leaves "
    "this machine: {paths}"
)
UNINSTALLED: Final = (
    "the ledger records no install of the overlay's plugin, so none of the overlay's hooks, skills "
    "or agents is delivered"
)
RENDER_GONE: Final = (
    "the render directory of binding {short} under {parent} is gone, so none of the overlay's "
    "hooks, skills or agents loads, and nothing else says so"
)
MARKETPLACE_GONE: Final = (
    "the render of binding {short} has no {file}, so its plugin does not load, and nothing else "
    "says so"
)
LAUNCHER_GONE: Final = (
    "the launcher the overlay's path-scoped rules run through, {path}, is not there, so those "
    "rules are not delivered"
)
DRIFTED: Final = (
    "the overlay's hooks, skills or agents changed since the last attach, so what runs is the "
    "render that attach left"
)
OVERLAY_UNREAD: Final = (
    "the overlay's hooks, skills or agents could not be read, so whether they changed since the "
    "last attach is not known"
)


class _Finding(NamedTuple):
    """One thing `_delivery` found: its status, the clause the row says it in, and its remedy."""

    status: Status
    clause: str
    remedy: str


def _worst(findings: list[_Finding]) -> _Finding | None:
    """The first red finding, else the first warning, else `None`."""
    from stayfixed.doctor.api import RED

    return next((each for each in findings if each.status == RED), None) or next(
        iter(findings), None
    )


def _delivery(
    context: Context, config: Config, recorded: AttachLedger, bound: Binding, id: str
) -> _Finding:
    """What the binding delivers, read where `attach` left it.

    **Red where nothing loads, or where git would show what is this machine's alone.** Claude Code
    runs the plugin from the render directory in place, and with that directory or its marketplace
    file gone it loads nothing and says nothing, so this row is the one place that says so; the
    overlay gone is the same for the hooks that run its scripts. A placed path that is tracked, or
    that a `.gitignore` re-includes, is one a collaborator gets, and a tracked file naming the
    delivery carries the binding id, the name a clone would need (`stayfixed.binding`).

    **A warning where what loads is not what the overlay holds now**: no install recorded, the
    launcher the path-scoped rules run through gone, the overlay's parts changed since the render
    (its digest against the ledger's, computed with the launcher the render holds, so a report run
    through another launcher reads no drift for that alone), and the `origin` note. The digest is
    a convenience and refuses nothing (`attach.render`).

    Every finding is read, and the first red one answers, else the first warning: no order of the
    reads lets a warning stand in front of a red."""
    from pathlib import Path

    from stayfixed import fsops
    from stayfixed.attach import ATTACH_STORE, exclude
    from stayfixed.attach.permissions import LOCAL_SETTINGS
    from stayfixed.attach.render import (
        MARKETPLACE_FILE,
        delivery_directory,
        digest,
        launcher,
        marketplace_name,
        read_parts,
        recorded_command,
    )
    from stayfixed.attach.write import named_placed, placed_paths
    from stayfixed.binding import short
    from stayfixed.config.schema import OVERLAY_MODE
    from stayfixed.doctor.api import OK, RED, WARN
    from stayfixed.errors import Failure, Refusal
    from stayfixed.gitenv import git_run
    from stayfixed.printed import quoted

    rerun = f"run `{ATTACH_STORE}`"
    found: list[_Finding] = []
    if not fsops.is_dir(bound.overlay):
        found.append(
            _Finding(
                RED,
                OVERLAY_GONE.format(path=quoted(str(bound.overlay))),
                "move the overlay back, or run `stayfixed setup --overlay <path>` to record where "
                f"it is now; then {rerun}",
            )
        )
    # The link tree only where `paths.memory` is a directory: git tracks and ignores a symlink
    # there as one path, answers nothing for a path beyond it, and the harness memory path's
    # reading already says what that tree is.
    linked = config.memory.mode == OVERLAY_MODE
    tree = context.root / config.paths.memory
    placed = placed_paths(config, recorded.rules, memory=linked and not fsops.is_symlink(tree))
    owner = _owner(context)
    # The main checkout's settings file, from a linked worktree: Claude Code writes the plugin's
    # entry, which names the id, into that file whichever worktree `attach` ran from.
    main = () if owner.resolve() == context.root.resolve() else (LOCAL_SETTINGS,)
    main_named = f"the main checkout's {LOCAL_SETTINGS}"
    try:
        tracked = (
            [named_placed(config, held)] if (held := exclude.tracked(context.root, placed)) else []
        )
        tracked += [main_named] if exclude.tracked(owner, main) else []
        shown = (
            [named_placed(config, held)]
            if (held := exclude.unignored(context.root, placed))
            else []
        )
        shown += [main_named] if exclude.unignored(owner, main) else []
    except Refusal:
        tracked, shown, unasked = [], [], True
    else:
        unasked = False
    if tracked:
        found.append(
            _Finding(
                RED,
                PLACED_TRACKED.format(paths=", ".join(tracked)),
                f"take each out of the index with `git rm --cached`, then {rerun}",
            )
        )
    if shown:
        found.append(
            _Finding(
                RED,
                PLACED_SHOWN.format(paths=", ".join(shown)),
                f"take that line out of the `.gitignore`, then {rerun}",
            )
        )
    # Every tracked file, in the work tree's copy, asked for the whole name and never the prefix,
    # which this repository's own sources spell: only this binding's id is the secret.
    delivered = marketplace_name(id)
    code, out = git_run(context.root, "grep", "-l", "-z", "-I", "-F", "-e", delivered)
    # Exit 1 is "no file names it", an answer; anything but 0 and 1 is git not answering, which is
    # never read as "none".
    if unasked or code not in (0, 1):
        found.append(
            _Finding(
                WARN,
                PLACED_UNASKED,
                "run `stayfixed doctor` again where `git ls-files`, `git check-ignore` and `git "
                "grep` work",
            )
        )
    if code == 0:
        named = [quoted(name) for name in out.split("\0") if name]
        found.append(
            _Finding(
                RED,
                ID_COMMITTED.format(paths=", ".join(named)),
                "take the name out of each file named above before it is pushed: a clone that "
                "carries it can name this machine's delivery",
            )
        )
    directory = delivery_directory(id)
    render = recorded.render
    if render is None:
        found.append(_Finding(WARN, UNINSTALLED, f"{rerun}, which installs it"))
    elif not fsops.is_dir(directory):
        found.append(
            _Finding(
                RED,
                RENDER_GONE.format(short=short(id), parent=quoted(str(directory.parent))),
                f"{rerun}, which renders it again",
            )
        )
    elif not fsops.is_file(directory / MARKETPLACE_FILE):
        found.append(
            _Finding(
                RED,
                MARKETPLACE_GONE.format(short=short(id), file=MARKETPLACE_FILE),
                f"{rerun}, which renders it again",
            )
        )
    command = recorded_command(directory)
    executable = None if command is None else launcher(command)
    if executable is not None and not fsops.exists(Path(executable)):
        found.append(
            _Finding(
                WARN,
                LAUNCHER_GONE.format(path=quoted(executable)),
                f"{rerun} from the stayfixed you run now, which renders the entry through it",
            )
        )
    if render is not None:
        try:
            now = digest(id, read_parts(bound.overlay, bound.project, command=command))
        except (Failure, Refusal, OSError):
            found.append(
                _Finding(WARN, OVERLAY_UNREAD, f"run `{ATTACH_STORE} --check`, which says why")
            )
        else:
            if now != render.digest:
                found.append(
                    _Finding(WARN, DRIFTED, f"{rerun}, which renders the overlay as it is now")
                )
    if bound.note is not None:
        found.append(_Finding(WARN, bound.note, rerun))
    if bound.fault is not None:
        found.append(_Finding(WARN, bound.fault, RECORD_REPAIR))
    return _worst(found) or _Finding(OK, DELIVERY_IN_PLACE, "")


def _attached(context: Context, config: Config, answers: Answers, ledger: _Ledger) -> Row:
    """The binding, what it delivers, and, where the notes are linked, the harness memory path.

    **Delivery does not depend on the memory mode** (`attach.write`), so the delivery is read for
    every repository whose ledger this machine's binding confirms; the harness memory path only
    where `memory.mode` is `overlay`. With no ledger, a repository whose notes are not linked is
    simply not attached, which is green.

    `attach` prefers a symlink at `~/.claude/projects/<slug>/memory`, because a settings-file
    value is subject to workspace trust and a link is not. A **real directory** there is a
    failure of its own and the reason this check exists rather than a general "not attached":
    the harness's native reader finds a directory, reads nothing out of it, and reports no fault
    — it looks attached and behaves like nothing. Unless `attach` took its settings-file fallback
    beside it, which points the harness at the store instead (`_harness_verdict`'s
    `real-directory-no-fallback`, `fallback-elsewhere` and `fallback-approved` rows).

    A path that is simply absent is not that. `worktree.harness_link_needed` gates the link on
    the same trust record every other channel is gated on, so an unapproved store correctly has
    no link, and calling that red would make `doctor` red on a correct fresh install. So this
    check *asks that function* rather than assuming: absent-and-not-wanted is green and says
    which of the two it is, absent-and-wanted is a warning, because a store the record approves
    and a harness that cannot see it is an attach that did not finish.

    **The link's target is compared, and the sentence about it is only ever printed when it is
    true.** "The harness memory path is a link to the store" printed for *any* symlink — a
    dangling one, or one pointing at an unrelated directory — with the row green underneath it
    would be, on the one channel `attach` uses to reach the model, a false statement about where
    the model's memory comes from, and the two states it would hide are the same failure the real
    directory is flagged for: one reads nothing, the other reads somebody else's notes.

    The delivery and the harness memory path are said side by side, and the row takes the worse
    status of the two and the worse one's remedy first.
    """
    from stayfixed.attach import ATTACH_STORE
    from stayfixed.config.layout import ATTACH_LEDGER
    from stayfixed.config.schema import OVERLAY_MODE
    from stayfixed.doctor.api import OK, RED, WARN, Row
    from stayfixed.errors import Refusal
    from stayfixed.memory.api import UNBOUND, harness_memory_path

    linked = config.memory.mode == OVERLAY_MODE
    if not linked and ledger.state(context.root) == NO_LEDGER:
        return Row(OK, f"{ATTACH_LEDGER} does not exist, so nothing records an attach")
    verdict: _Verdict | None = None
    harness: Path | None = None
    fallback = _Fallback()
    if linked:
        try:
            harness = harness_memory_path(context.root, context.home)
        except Refusal:
            # Refused only for a home it cannot name, which is this machine's state and not a
            # broken check, so it is a warning that says what it costs.
            return Row(
                WARN,
                "HOME names no home directory, so there is no harness memory path to check",
                "set HOME to your home directory, or pass --home <path> to check the harness "
                "memory path under that directory",
            )
        # A real directory there is red unless `attach` took the settings-file fallback beside it,
        # and a fallback naming anything but the store `attach` writes there is red beside any
        # shape: either is where the harness then reads its memory whatever the ledger says, so
        # both are read before the ledger is. The verdict is the one the row ends with, read once.
        fallback = _settings_fallback(context.root)
        if fallback.held or _shape_of(harness) == _REAL_DIRECTORY:
            verdict = _harness_verdict(context, config, answers, harness, fallback)
            if verdict.whole:
                return Row(verdict.status, verdict.shape, verdict.remedy)
        if ledger.state(context.root) == NO_LEDGER:
            return Row(
                WARN,
                f"memory.mode is overlay and {ATTACH_LEDGER} does not exist, so nothing records an "
                f"attach",
                f"run `{ATTACH_STORE} --check`",
            )
    answer = _binding_answer(context, config, ledger)
    # The ledger exists, so from here on this row's job is to say what **this machine** makes of
    # it (principle 5): the ledger is a path a clone can commit, and the binding is the one record
    # a repository cannot choose. Every arm below but the last refuses to print the word
    # "attached".
    if isinstance(answer, str):
        return _uncorroborated(answer)
    state = answer.state
    from stayfixed.attach.binding import OVERLAY_REPAIR, damaged_overlay
    from stayfixed.binding import read_id
    from stayfixed.errors import Failure

    # An overlay whose root or `projects/` is a file holds none of this checkout's notes or grants,
    # bound or not; the remedy for that is the overlay's repair, and never removing the ledger,
    # which is this checkout's record of a real attach.
    damaged = damaged_overlay(answer.overlay)
    if damaged is not None:
        return Row(
            WARN,
            f"{ATTACH_LEDGER} records an attach, but {damaged} is not a directory, so the overlay "
            f"this machine records is damaged and holds none of this checkout's notes or grants",
            OVERLAY_REPAIR.format(path=damaged, command="`stayfixed doctor`"),
        )
    # The id `bound_project` read to answer `bound`; read again for the render it names, and none
    # (git gone since, or the id removed in between) is no binding, as `unbound` is.
    try:
        id = read_id(context.root)
    except Failure:
        id = None
    if state == UNBOUND or id is None:
        return Row(
            WARN,
            f"{ATTACH_LEDGER} records an attach, but this machine records no binding of this "
            f"checkout to this project — a clone can commit that file, so it is not evidence of "
            f"an attach",
            _re_attach(),
        )
    recorded = ledger.state(context.root)
    if isinstance(recorded, str):  # `_binding_answer` answered a binding, so never
        return _uncorroborated(recorded)
    delivery = _delivery(context, config, recorded, answer, id)
    if harness is None:
        return Row(
            delivery.status, f"attached; {delivery.clause}; the binding is {state}", delivery.remedy
        )
    if verdict is None:
        verdict = _harness_verdict(context, config, answers, harness, fallback)
    rank = {OK: 0, WARN: 1, RED: 2}
    pair = (delivery.status, delivery.remedy), (verdict.status, verdict.remedy)
    (status, worse), (_, other) = sorted(pair, key=lambda each: -rank[each[0]])
    return Row(
        status,
        f"attached; {delivery.clause}; the harness memory path is {verdict.shape}; the binding is "
        f"{state}",
        "; ".join(dict.fromkeys(remedy for remedy in (worse, other) if remedy)),
    )


# Why the overlay could not corroborate the ledger, as `_binding_answer`'s three answers. Not
# statuses and not sentences: the row below decides both, and these are the question's own
# vocabulary. `UNRESOLVED` is about the repository, the other two about this machine.
UNRESOLVED: Final = "unresolved"
NO_OVERLAY: Final = "no-overlay"
UNASKABLE: Final = "unaskable"
# About this machine too: its machine file could not be read (`Context.overlay_root`'s
# `MachineUnread`), so whether it records an overlay is not known. Read as `NO_OVERLAY` it told the
# owner the machine records none, and as `UNASKABLE` that `git` or the overlay was at fault.
MACHINE_UNREAD: Final = "machine-unread"
# The fourth is `UNREADABLE_LEDGER`, above, and it is about the repository rather than about this
# machine: a ledger that is there and will not parse is a file in the checkout the reader is
# standing in. Told with the other two, the row would blame `git` or an unreadable record and send
# the reader to run `stayfixed doctor` where `git` runs, which cannot fix it, and its `skip` never
# reaches the exit code, so a repository's own committed, malformed ledger would go unreported.


def _re_attach() -> str:
    """The remedy for a ledger the overlay does not corroborate. A function only because the
    command it names is imported, and an import here sits inside a function body."""
    from stayfixed.attach import ATTACH_STORE

    return (
        f"run `{ATTACH_STORE} --check`; if this checkout was never attached on this machine, "
        "remove the ledger"
    )


def _uncorroborated(reason: str) -> Row:
    """The row for a ledger the overlay did not confirm, split by what the reason is *about*.

    `warn` accuses the repository and `skip` does not, and the split is the point: `skip` never
    reaches the exit code, so using it for the repository's own doing would silence it, and using
    `warn` for a machine where `setup` has never run would make `doctor` warn on every correct
    fresh install. Neither row ever says "attached".

    **Four reasons and not three.** A ledger that is there and will not parse is the
    repository's doing, so by this function's own rule it warns. Answered with the machine-side
    two, its row would blame `git` for a malformed file in the reader's own checkout and offer a
    remedy — run this somewhere `git` works — that could not fix it.
    """
    from stayfixed.attach import ATTACH_STORE
    from stayfixed.config.layout import ATTACH_LEDGER
    from stayfixed.doctor.api import SKIP, WARN, Row

    # Said by every row that meets a ledger the overlay has not confirmed, because it is the whole
    # reason those rows exist: the binding lives in the git common directory and this machine's
    # record of it, and this file does not.
    not_evidence = (
        f"a clone can commit {ATTACH_LEDGER}, so on its own it is not evidence of an attach"
    )
    if reason == UNRESOLVED:
        return Row(
            WARN,
            f"{ATTACH_LEDGER} records an attach, and the store it names is not this project's "
            f"directory inside the overlay this machine records — {not_evidence}",
            _re_attach(),
        )
    if reason == UNREADABLE_LEDGER:
        return Row(
            WARN,
            f"{ATTACH_LEDGER} is here and cannot be read as a ledger, so nothing in it can be "
            f"corroborated and this checkout's attach state is unknown — {not_evidence}",
            f"remove {ATTACH_LEDGER}, then run `{ATTACH_STORE} --check`",
        )
    if reason == MACHINE_UNREAD:
        # No remedy of its own: the `preferences` row is red on the same file, and names it and
        # what to do.
        return Row(
            SKIP,
            f"{ATTACH_LEDGER} records an attach and the machine configuration file could not be "
            f"read, so whether this checkout is attached could not be answered here; the "
            f"`preferences` row says why — {not_evidence}",
            "",
        )
    if reason == NO_OVERLAY:
        return Row(
            SKIP,
            f"{ATTACH_LEDGER} records an attach and this machine records no overlay to check it "
            f"against, so whether this checkout is attached could not be answered here — "
            f"{not_evidence}",
            "run `stayfixed setup --overlay <path>` to record the overlay, then `stayfixed "
            "doctor` again",
        )
    return Row(
        SKIP,
        f"{ATTACH_LEDGER} records an attach and the overlay could not be asked about it here — no "
        f"`git`, or an overlay record this process could not read — so whether this checkout "
        f"is attached could not be answered; {not_evidence}",
        "run `stayfixed doctor` again where `git` runs and the overlay is readable",
    )


# The shapes the harness memory path can have, as `_harness_verdict` reads them. Not statuses and
# not sentences: the table below gives each its status and its words.
_ABSENT: Final = "absent"
_DANGLING: Final = "dangling"
_LINK: Final = "link"
_REAL_DIRECTORY: Final = "real-directory"
_OTHER: Final = "other"


class _Verdict(NamedTuple):
    """`_harness_verdict`'s answer: the status, what the harness memory path is, and the remedy.

    `whole` is the real directory's red, whose sentence is the row's whole detail rather than the
    shape the attached row frames ("attached; the harness memory path is …; the binding is …"):
    it is answered before the ledger is read, so it never says "attached"."""

    status: Status
    shape: str
    remedy: str
    whole: bool = False


def _shape_of(harness: Path) -> str:
    """What stands at the harness memory path, by `fsops`' answers, which every interpreter gives
    alike. A link that reaches nothing — gone, or a loop — is dangling."""
    from stayfixed import fsops

    if fsops.is_symlink(harness):
        return _LINK if fsops.exists(harness) else _DANGLING
    if fsops.is_dir(harness):
        return _REAL_DIRECTORY
    return _OTHER if fsops.exists(harness) else _ABSENT


class _Fallback(NamedTuple):
    """What the two settings files a repository controls say about `autoMemoryDirectory`, as
    `_settings_fallback` reads them: one of none, a value, or cannot tell.

    `held` is whether a key is in effect, `value` its value, of any type and never printed, and
    `where` the file it is in effect from. `unread` names a file that could not be read as
    settings, where no value is in effect: what the harness makes of that file is unknown."""

    held: bool = False
    value: object = None
    where: str = ""
    unread: str = ""


# `_settings_key`'s two answers about one file besides a key's value: no key, and a file that
# cannot be read as settings. Objects and not strings, since a value may be any string.
_NO_KEY: Final = object()
_CANNOT_TELL: Final = object()


def _settings_fallback(root: Path) -> _Fallback:
    """`autoMemoryDirectory` as a whitelist over the two settings files a repository controls,
    `.claude/settings.local.json` and the shared `.claude/settings.json`, the local file's key in
    effect over the shared one's, as the harness takes them.

    **A whitelist, and not a model of the harness's reader.** Every file the harness may read the
    key from is answered as one of: no file, or a JSON object (`jsonobject.json_object`) with no
    such key; a key, of any value; or a file that cannot be read as settings — unreadable, not a
    regular file, not UTF-8, a byte-order mark, a comment, a trailing comma, or anything but one
    object. The verdict then admits one value, the
    one `attach` writes (`_written_fallback`), and nothing else: a `~/…` value, a relative one,
    an empty one, another spelling of the store, a number. The harness reads more than strict
    JSON and expands more than absolute paths, so modelling it one spelling at a time read each
    new spelling as no key, and green. A file this cannot read is never read as no key: where
    the row would be green beside it, it warns that what the harness makes of it is unknown.

    The user's own `~/.claude/settings.json`, policy settings and `--settings` are not the
    repository's, and this row does not read them."""
    from stayfixed.harnesses import CLAUDE

    effective = _Fallback()
    unread = ""
    for relative in (*CLAUDE.local_settings, *CLAUDE.settings):
        found = _settings_key(root / relative)
        if found is _CANNOT_TELL:
            unread = unread or relative
        elif found is not _NO_KEY and not effective.held:
            effective = _Fallback(True, found, relative)
    if effective.held and effective.where in CLAUDE.local_settings:
        # The local key is in effect whatever the shared file holds.
        return effective
    # The shared file's key, or none, beside a file that may not have been read: a value that is
    # not the written one is still red, and nothing beside an unread file is green.
    return effective._replace(unread=unread)


def _settings_key(path: Path) -> object:
    """`autoMemoryDirectory`'s value in one settings file, `_NO_KEY`, or `_CANNOT_TELL`."""
    from stayfixed import fsops
    from stayfixed.attach.write import FALLBACK_KEY
    from stayfixed.jsonobject import json_object

    try:
        text = fsops.read_regular_text(path, newline="")
    except (FileNotFoundError, NotADirectoryError):
        return _NO_KEY
    except (OSError, UnicodeDecodeError):
        return _CANNOT_TELL
    if not text.strip():
        return _NO_KEY
    try:
        document = json_object(text, str(path), error=ValueError)
    except ValueError:
        return _CANNOT_TELL
    return document.get(FALLBACK_KEY, _NO_KEY)


def _owner(context: Context) -> Path:
    """The checkout that owns this one's store: the one `attach` points every checkout's harness
    link at and asks the gate of. A `git` that cannot say leaves this checkout, the one answer that
    needs no `git`; the binding row above has already asked `git` by then, so this is the race and
    not the layout."""
    from stayfixed.errors import Failure
    from stayfixed.memory.api import main_checkout

    try:
        return main_checkout(context.root)
    except Failure:
        return context.root


def _store_of(context: Context, config: Config, answers: Answers, checkout: Path) -> Store | None:
    """`checkout`'s note store, or `None` where it does not resolve: `answers`' own for this
    checkout, resolved the same way (`errors.resolved_or_none`) for another.

    `checkout` is the owning checkout for every shape but a link that reaches this checkout's own
    tree, because the owner's is the store `attach` links every checkout's harness link to and
    asks the gate of (`attach.write._fallback_store`). Asked of a worktree's own store, one
    machine state read two ways: with the main checkout's store approved and no link anywhere,
    the main checkout warned that the link is missing and the worktree read green, since `attach`
    never approves a worktree's own store. A link to the worktree's own tree is the `SessionStart`
    re-link's, made by the gate of that tree's store, so that store is the one it is judged by.

    Compared resolved: `git` names the owner by its resolved path, and `--root` may spell the
    same checkout through a link."""
    from stayfixed.errors import resolved_or_none
    from stayfixed.memory.api import resolve

    if checkout.resolve() == context.root.resolve():
        return answers.store(context)
    return resolved_or_none(lambda: resolve(checkout, config, machine=context.machine))


def _harness_verdict(
    context: Context, config: Config, answers: Answers, harness: Path, fallback: _Fallback
) -> _Verdict:
    """The one reading of the harness memory path; `_read_harness` is the reading, and this is
    it with a settings file that cannot be read said beside every green answer: what the harness
    makes of that file is unknown, so nothing beside it is green."""
    from stayfixed.doctor.api import OK, WARN

    verdict = _read_harness(context, config, answers, harness, fallback)
    if verdict.status != OK or not fallback.unread:
        return verdict
    return _Verdict(  # settings-unreadable
        WARN,
        f"{verdict.shape}, but {fallback.unread} could not be read as settings, so whether it "
        "points the harness elsewhere is unknown",
        f"make {fallback.unread} one JSON object, as the harness reads it, then run `stayfixed "
        "doctor` again",
    )


def _read_harness(
    context: Context, config: Config, answers: Answers, harness: Path, fallback: _Fallback
) -> _Verdict:
    """The one reading of the harness memory path: each machine state one status, sentence and
    remedy, answered alike from the main checkout and from a linked worktree.

    One ordered reading, and the first row that matches answers. Each row is named as the state
    it answers is named in `tests/attach/test_doctor.py`'s `ONE_MACHINE_STATE`, and the name is
    the comment on the line that answers it:

    - `dangling`: a link that reaches nothing. Red; `attach`.
    - `real-directory-no-fallback`: a real directory, and no `autoMemoryDirectory` in effect in
      either settings file the repository controls (`_settings_fallback`). Red, the row's whole
      detail; move it aside, then `attach`.
    - `targets-unaskable`: where a harness link may point cannot be asked (`harness_targets`
      refuses). Warn, naming whose `paths.memory` and why; replace the symlink, or make the
      directory readable.
    - `links-elsewhere`: a link to a directory a harness link may not point at. Red; `attach`.
    - `tree-gone`: the store does not resolve, and its link tree is gone. Warn; `attach`
      (`_unresolved`).
    - `tree-there-not-resolving`: the store does not resolve, and its link tree is there. Warn;
      `memory index --check` (`_unresolved`).
    - `fallback-elsewhere`: whatever stands there, `autoMemoryDirectory` in effect and set to
      anything but the owning checkout's store, resolved, the one value `attach` writes there
      (`_written_fallback`), compared as a string. Red, the row's whole detail, naming the file;
      remove the key, then `attach`.
    - `trust-record-unreadable`: this machine's trust record cannot be read. Warn; `trust list
      --all`, which says why and needs no terminal.
    - `attached`: a link to the store, the gate open. Ok.
    - `link-lapsed`: a link to the store, the gate closed, the approval lapsed. Warn;
      `HARNESS_LAPSED`'s remedy (read what changed, approve, `attach`).
    - `link-never-approved`: a link to the store, the gate closed, never approved. Warn;
      `attach`, which withdraws a link to the main checkout's tree in exactly this state, or, for
      a link to this checkout's own tree, which `attach` does not withdraw, remove it.
    - `fallback-unapproved`: anything but a link beside the fallback `attach` writes, the gate
      closed, lapsed or never approved. Warn, naming which; `attach`, which withdraws the
      fallback in exactly this state.
    - `fallback-approved`: a real directory beside the fallback, the gate open. Ok.
    - `fallback-instead-of-a-link`: nothing in place beside the fallback, the gate open. Warn;
      `attach`, which makes the link the gate allows.
    - `no-links-approved`: nothing in place, the gate open. Warn; `attach`.
    - `lapsed-links-withdrawn`: nothing in place, the gate closed, the approval lapsed. Warn;
      `HARNESS_LAPSED`'s remedy (read what changed, approve, `attach`).
    - `never-approved`: nothing in place, the gate closed, never approved. Ok.

    **`dangling` comes first**, before the store is asked anything: with the owning checkout's
    tree gone every checkout's link dangles, and the store-resolution rows read first made the
    main checkout warn while a linked worktree said red. `doctor` exits non-zero only on red, and
    a link that reaches nothing is red from every checkout.

    **The store is the one the harness reads** (`_store_of`): the owning checkout's, which
    `attach` links every checkout to and asks the gate of, but for a link that reaches this
    checkout's own tree, which the `SessionStart` re-link makes by the gate of that tree's store.
    Judged at the owner's instead, a worktree linked to its own emptied tree read green while the
    harness read nothing, and with the owner's tree gone a worktree reading its own tree was told
    the harness read nothing through it.

    **The gate is asked of every shape but the red ones and the unresolved ones**, a link to the
    store included: after one changed note the harness reads notes nobody approved through a link
    that still resolves as surely as through the fallback, and the row read that link green while
    it warned for the fallback, one exposure, two verdicts, until the next `attach` withdrew it.

    **`harness_targets` is asked once, and its one refusal is one answer** (`targets-unaskable`),
    whatever the shape: it says whose `paths.memory` and why, in stayfixed's words, and the value
    it quotes is held to `PATH_VALUE`, the grammar a report may print. `dangling` and
    `real-directory-no-fallback` are red without asking it, since nothing it could answer would
    change that.

    **The fallback is read for every shape** (`fallback`, `_settings_fallback`'s answer, which
    the caller reads once): both settings files are ones a branch can commit, and the harness
    reads `autoMemoryDirectory` whatever stands at the harness memory path, a link to the store
    included. Read only beside a real directory, a committed key read green beside a link or
    beside nothing. Where a settings file cannot be read as settings, `_harness_verdict` turns
    every green answer of this reading into the `settings-unreadable` warning.

    A file or anything else that is no link and no directory reads as nothing in place
    (`tree-gone`, `tree-there-not-resolving`, `no-links-approved`, `lapsed-links-withdrawn`,
    `never-approved`), as it did.
    """
    from stayfixed.attach import ATTACH_STORE
    from stayfixed.attach.write import APPROVAL_LAPSED, FALLBACK_KEY, REAPPROVE
    from stayfixed.doctor.api import OK, RED, WARN
    from stayfixed.errors import Refusal
    from stayfixed.memory.api import GATE_LAPSED, GATE_OPEN, harness_gate, harness_targets

    # The remedy every arm but the green ones and the named ones carries: one command puts the link
    # back where `attach` puts it, whatever the wrong shape was.
    relink = f"run `{ATTACH_STORE}`"
    shape = _shape_of(harness)
    if shape == _DANGLING:  # dangling
        return _Verdict(RED, "a dangling link, so the harness reads nothing through it", relink)
    if shape == _REAL_DIRECTORY and not fallback.held:  # real-directory-no-fallback
        return _real_directory(harness)
    words = {
        _LINK: "a link",
        _REAL_DIRECTORY: f"a real directory beside the {FALLBACK_KEY} fallback",
        _OTHER: "something other than a link",
        _ABSENT: "not in place",
    }[shape]
    owner = _owner(context)
    try:
        targets = harness_targets(context.root, owner, config)
    except Refusal as refused:  # targets-unaskable
        unchecked = {
            _LINK: "what the link points at",
            _REAL_DIRECTORY: f"whether {FALLBACK_KEY} names the store",
        }.get(shape, "whether the harness should see it")
        return _Verdict(
            WARN,
            f"{words}, and {refused}, so {unchecked} could not be checked",
            "replace that symlink with the directory it points at, or make the directory "
            "readable, then run `stayfixed doctor` again",
        )
    # What stands there in plain words, for the rows the fallback answers.
    plain = {
        _LINK: "a link",
        _REAL_DIRECTORY: "a real directory",
        _OTHER: "something other than a link",
        _ABSENT: "not in place",
    }[shape]
    written = str(_written_fallback(owner, config))
    if fallback.held and fallback.value != written:
        return _fallback_elsewhere(plain, fallback.where)  # fallback-elsewhere
    reached = harness.resolve() if shape == _LINK else None
    if reached is not None and reached not in targets:  # links-elsewhere
        return _Verdict(
            RED,
            "a link to a directory that is not this project's note store, so the harness "
            "reads notes this repository is not bound to",
            relink,
        )
    # `harness_targets` answers the owning checkout's tree first: a link that reaches the other
    # one reaches this checkout's own.
    own = reached is not None and reached != targets[0]
    checkout = context.root if own else owner
    store = _store_of(context, config, answers, checkout)
    if store is not None and reached is not None and store.path.resolve() != reached:
        # A linked worktree whose own tree does not resolve resolves through the main checkout
        # (`memory.store.resolved`), and that store is not the one the harness reads through a
        # link to the worktree's own tree.
        store = None
    if store is None:  # tree-gone, tree-there-not-resolving
        return _unresolved(context, config, checkout, shape, words, relink)
    try:
        gate = harness_gate(store, config)
    except Refusal:  # trust-record-unreadable
        return _Verdict(
            WARN,
            f"{words}, and this machine's trust record cannot be read, so whether the harness "
            "should see this store could not be checked",
            "run `stayfixed trust list --all`, which says why the trust record cannot be read, "
            "then `stayfixed doctor` again",
        )
    if shape == _LINK:
        if gate == GATE_OPEN:  # attached
            return _Verdict(OK, "a link to the store", "")
        if gate == GATE_LAPSED:  # link-lapsed
            return _Verdict(
                WARN,
                f"a link to the store, although {APPROVAL_LAPSED} — the harness reads notes "
                "nobody approved",
                REAPPROVE,
            )
        # `attach` withdraws a link to the main checkout's tree in this state, and leaves one
        # to this checkout's own, which only the `SessionStart` re-link makes.
        return _Verdict(  # link-never-approved
            WARN,
            "a link to the store, although no approval is recorded for the store — the harness "
            "reads notes nobody approved",
            f"remove {harness}, a link to this checkout's own tree, which `{ATTACH_STORE}` does "
            "not withdraw"
            if own
            else relink,
        )
    # The file named through the harness registry (`CLAUDE.local_settings`), as `attach`'s own
    # fallback line names it: a harness fact spelled here is one more place a new harness would
    # have to be found.
    points = f"{plain}, and {FALLBACK_KEY} in {fallback.where} points the harness"
    if fallback.held and gate != GATE_OPEN:  # fallback-unapproved
        why = APPROVAL_LAPSED if gate == GATE_LAPSED else "no approval is recorded for the store"
        return _Verdict(
            WARN,
            f"{points} at the store, although {why} — the harness reads notes nobody approved",
            relink,
        )
    if shape == _REAL_DIRECTORY:  # fallback-approved
        return _Verdict(OK, f"{points} at the store instead", "")
    if fallback.held:  # fallback-instead-of-a-link
        return _Verdict(
            WARN,
            f"{points} at the store instead, where this store's trust record allows the link "
            "`attach` makes",
            relink,
        )
    if gate == GATE_OPEN:  # no-links-approved
        return _Verdict(
            WARN,
            "not in place, although this store's trust record allows it, so the harness sees "
            "no memory here",
            relink,
        )
    if gate == GATE_LAPSED:  # lapsed-links-withdrawn
        return _Verdict(
            WARN,
            f"not in place, because {APPROVAL_LAPSED} — the harness sees no memory here",
            REAPPROVE,
        )
    # never-approved
    return _Verdict(OK, "not in place, which is what this store's trust record asks for", "")


def _written_fallback(owner: Path, config: Config) -> Path:
    """The one value `attach` writes into `autoMemoryDirectory`: the owning checkout's store,
    resolved (`write._fallback_wanted`'s `str(store.path.resolve())`).

    Computed without the store, so a fallback is judged whether or not the store resolves: a
    store that resolves is `paths.memory` under the owner, a real directory, so its resolution is
    its parent's and its own name. And computed without following `paths.memory` itself, which a
    branch can commit as a link to a directory of its choosing beside a key naming that
    directory. Asked after `harness_targets` answered, which walked the same path."""
    from stayfixed.config.paths import contained

    tree = contained(owner, config.paths.memory, allow_final_symlink=True)
    return tree.parent.resolve() / tree.name


def _fallback_elsewhere(plain: str, where: str) -> _Verdict:
    """The `fallback-elsewhere` row of `_read_harness`: `autoMemoryDirectory` in `where` is set
    to anything but the one value `attach` writes there, beside whatever stands at the harness
    memory path, which the harness then does not read. The value is a committed file's and is
    never printed; another spelling of the store is this row too, since only the written one is
    admitted. Read before the ledger, so it is the row's whole detail."""
    from stayfixed.attach import ATTACH_STORE
    from stayfixed.attach.write import FALLBACK_KEY
    from stayfixed.doctor.api import RED

    return _Verdict(
        RED,
        f"the harness memory path is {plain}, and {FALLBACK_KEY} in {where} is set to something "
        "other than the store `attach` writes there, so the harness may read notes this "
        "repository is not bound to",
        f"remove {FALLBACK_KEY} from {where}, then run `{ATTACH_STORE}`",
        whole=True,
    )


def _real_directory(harness: Path) -> _Verdict:
    """The `real-directory-no-fallback` row of `_harness_verdict`: a real directory at the
    harness memory path with no fallback recorded beside it. The remedy is `attach`'s own
    (`write.FALLBACK_UNAVAILABLE`): the directory can hold notes the harness wrote, so it is moved
    aside and never removed."""
    from stayfixed.attach import ATTACH_STORE
    from stayfixed.doctor.api import RED

    return _Verdict(
        RED,
        "the harness memory path is a real directory rather than a link to the store, so this "
        "checkout looks attached and behaves like nothing",
        f"move {harness} aside, then run `{ATTACH_STORE}` again",
        whole=True,
    )


def _unresolved(
    context: Context, config: Config, checkout: Path, shape: str, words: str, relink: str
) -> _Verdict:
    """The `tree-gone` and `tree-there-not-resolving` rows of `_harness_verdict`: the note store
    of `checkout`, the one `_store_of` was asked of, does not resolve, by what its tree is.

    A `paths.memory` that is not there is the tree `attach` builds, gone: `attach` puts it back,
    so the row names it. Anything else that keeps the store from resolving — `paths.memory` a
    symlink, the overlay's group directories gone, an empty tree — is not one `attach` is known to
    mend, so the row sends the reader to `memory index --check`, which says which it is. Either
    way the row warns: with no store there is no trust record to ask, and "what this store's trust
    record asks for", green, was said about a checkout whose sessions see no memory at all. A
    `paths.memory` that cannot be asked about is read as there, so the remedy is the one that
    reports why.
    """
    from stayfixed import fsops
    from stayfixed.doctor.api import WARN

    tree = checkout / config.paths.memory
    try:
        gone = not fsops.is_symlink(tree) and not fsops.exists(tree)
    except OSError:
        gone = False
    if gone:  # tree-gone
        return _Verdict(
            WARN,
            f"{words}, and the link tree at paths.memory is not there, so the note store does not "
            f"resolve and the harness reads nothing through it",
            relink,
        )
    unchecked = "what it points at" if shape == _LINK else "whether the harness should see it"
    return _Verdict(  # tree-there-not-resolving
        WARN,
        f"{words}, and the note store does not resolve, so {unchecked} could not be checked",
        "run `stayfixed memory index --check`, then `stayfixed doctor` again",
    )


def _binding_answer(context: Context, config: Config, ledger: _Ledger) -> Binding | str:
    """The overlay binding this repository would attach under, or the label of why there is none.

    Three different situations are three answers and never one `None` — a ledger naming a store
    the overlay does not permit, a machine that records no overlay at all, and a machine with no
    usable `git` — because collapsed, the `attached` row would read the last two as *attached*.
    They are not one finding. A ledger whose store is not this project's share of the recorded
    overlay is a fact about **this repository**, and `.stayfixed/local/attach.json` is a path a
    clone can commit, so it earns a warning. A missing overlay or a missing `git` is a fact about
    **our own inputs**, and a row that accused the repository on it would be reporting on itself.
    So is a machine file that could not be read (`MACHINE_UNREAD`), asked first as `NO_OVERLAY` is:
    `read_binding` would raise its refusal as a `Failure`, read as `UNASKABLE`, which blames `git`.

    The three are told apart without restructuring `read_binding`, which raises `Refusal` for
    two of them: `context.overlay_root` is the answer of the same `overlay_root(machine)` that
    function calls with the same argument, so asking it first takes the overlay-is-missing arm
    off the table, and what is left of `Refusal` is the store that is not this project's
    permitted root. Anything else that goes wrong — a `git` that cannot be asked, a ledger this
    process may not read — answers `UNASKABLE`, which is the conservative
    direction: it never accuses the repository for something it may not have done.
    """
    from pathlib import Path

    from stayfixed.attach.binding import read_binding
    from stayfixed.doctor.api import MachineUnread
    from stayfixed.errors import Failure, Refusal
    from stayfixed.gitenv import GitUnavailable

    if context.overlay_root is None:
        return NO_OVERLAY
    if isinstance(context.overlay_root, MachineUnread):
        return MACHINE_UNREAD
    recorded = ledger.state(context.root)
    # This one is the repository's file and not our inputs, so it does not join the other two: a
    # clone can commit `.stayfixed/local/attach.json`, and a file that will not parse is a fact
    # about the checkout the reader is standing in. `NO_LEDGER` never reaches here: `_attached`
    # answers it before asking.
    if isinstance(recorded, str):
        return UNREADABLE_LEDGER
    try:
        # The report's own `Config`, which `read_binding` would otherwise load a second time.
        return read_binding(
            context.root, store=Path(recorded.store), machine=context.machine, config=config
        )
    except Refusal:
        return UNRESOLVED
    except (Failure, GitUnavailable):
        return UNASKABLE


def register() -> Contribution:
    """The `attached` row, with one `_Ledger` and one `Answers` for the note store, per report."""
    from stayfixed.doctor.api import Contribution, configured
    from stayfixed.memory.api import Answers

    answers = Answers()
    ledger = _Ledger()
    # `configured`: which store, which tree and whether the overlay is consulted at all are the
    # project's file's to say, so with none the row skips.
    attached = configured(lambda context, config: _attached(context, config, answers, ledger))
    return Contribution(checks=(("attached", attached),))
