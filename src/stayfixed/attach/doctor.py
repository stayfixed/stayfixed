"""The binding's row in `stayfixed doctor`, and what this area put into settings files.

`attached` is this area's: it reads the attach ledger this area writes and asks the overlay, through
this area's own `read_binding`, whether a binding stands behind it. The `claims` are this area's
too: `hook-entries`, which stays in the core because every settings file is the core's to walk,
lists each hook entry with its provenance, and only this area can say which entries `attach`
recorded and which of them the overlay still grants. `doctor`'s core discovers this module by
name (CONTRIBUTING.md, "Areas") and imports nothing of this area.

The overlay root is the core's answer, `Context.overlay_root`, resolved at most once per report
for every row that reads it. The note store comes from the `Answers` this module's `register()`
creates, one per report, so the row resolves it once. The attach ledger comes from the `_Ledger`
created beside it, so the binding the row reads and the claims `hook-entries` reads read the file
once between them, and both read it the same way.

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
    from stayfixed.doctor.api import Claims, Context, Contribution, Row, Status, Wording
    from stayfixed.memory.api import Answers, Store
    from stayfixed.scaffold import Placed


# What `_ledger_state` answers beside a ledger: no file at the ledger's path, and a file there that
# cannot be read as one. Not statuses and not sentences: each reader decides both.
NO_LEDGER: Final = "no-ledger"
# Also the fourth of `_binding_answer`'s reasons, below: the same fact, and it is about the
# repository rather than about this machine.
UNREADABLE_LEDGER: Final = "unreadable-ledger"
# Why the overlay grants this checkout only what `common/` grants, where saying it refused would be
# false: the record under `projects/<name>/` binds another remote, or cannot be read. Not a state
# of `memory.store`'s: the record's own failure is this area's question, asked only here.
UNREADABLE_RECORD: Final = "unreadable-record"
# The `attached` row's remedy for a record that binds another remote, which `hook-entries` hands on
# for the entries that mismatch leaves red: one spelling, so the two rows cannot disagree.
_REBIND = "run `stayfixed attach --check`, and `--trust-remote` only if it should be"


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

    Created once per report by `register()`, so `attached` and the claims
    `hook-entries` reads ask one question of the file and get one answer: no row can read the
    ledger as there while another reads it as absent or unreadable.
    """

    def __init__(self) -> None:
        self._state: tuple[AttachLedger | str] | None = None

    def state(self, root: Path) -> AttachLedger | str:
        if self._state is None:
            self._state = (_ledger_state(root),)
        return self._state[0]


def _attach_ledger_entries(state: AttachLedger | str) -> dict[str, str] | None:
    """The marker ids this repository's last `attach` claims, `{}` when it never ran, `None`
    when the file is there and cannot be read as a ledger."""
    if isinstance(state, str):
        return None if state == UNREADABLE_LEDGER else {}
    return dict(state.entries)


def _attached(context: Context, answers: Answers, ledger: _Ledger) -> Row:
    """Attach state, and the shape of the harness memory path.

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
    """
    from stayfixed.attach import ATTACH_STORE
    from stayfixed.attach.write import HOME_DIFFERS, UnreadHome, unread_home
    from stayfixed.config.layout import ATTACH_LEDGER
    from stayfixed.config.machine import home_is_empty, override_is_honoured
    from stayfixed.config.schema import OVERLAY_MODE
    from stayfixed.doctor.api import OK, RED, WARN, Row
    from stayfixed.errors import Refusal
    from stayfixed.memory.api import (
        DIFFERENT_REMOTE,
        MISMATCH,
        NO_ORIGIN,
        NO_ORIGIN_CAUSE,
        NO_ORIGIN_WAY_OUT,
        UNBOUND,
        harness_memory_path,
    )

    config = context.config
    if config.memory.mode != OVERLAY_MODE:
        # `memory.mode` is repository-authored and is safe to print for one reason only: the
        # loader holds it to a fixed set of three words, so what reaches this line is one of
        # stayfixed's own labels rather than a string a clone chose.
        return Row(OK, f"memory.mode is {config.memory.mode}; there is no overlay to bind to")
    # Asked as `attach` asks it, with no `--home`: off a terminal, where `HOME` is not the home the
    # link goes under, the path under that home is not the one a harness started with this `HOME`
    # reads, and the one under `HOME` is not judged, since a `HOME` the clone chose could hold a
    # link that reads green. The row says so in `attach`'s words instead of judging either.
    unread = unread_home() if context.home is None else None
    harness: Path | UnreadHome
    verdict: _Verdict | None = None
    if unread is not None:
        harness = unread
    else:
        try:
            harness = harness_memory_path(context.root, context.home)
        except Refusal:
            # Refused only for a home it cannot name: a user the password database lists no home
            # for, off a terminal or at one where `HOME` is unset, or a terminal whose `HOME` is
            # empty, which names none (`config.machine.owner_home`). That is this machine's state
            # and not a broken check, so it is a warning that says what it costs; `ignored-env`
            # says why.
            if override_is_honoured() and home_is_empty():
                return Row(
                    WARN,
                    "HOME is empty, so it names no home directory and there is no harness memory "
                    "path to check",
                    "set HOME to your home directory, or pass --home <path> to check the harness "
                    "memory path under that directory",
                )
            return Row(
                WARN,
                "the password database lists no home directory for this user, so there is no "
                "harness memory path to check and no hook makes one",
                "pass --home <path> to check the harness memory path under that directory",
            )
        # A real directory there is red unless `attach` took the settings-file fallback beside it,
        # which is where the harness then reads its memory — red whatever the ledger says, so it is
        # read before the ledger is. The verdict is the one the row ends with, read once.
        if _shape_of(harness) == _REAL_DIRECTORY:
            verdict = _harness_verdict(context, answers, harness)
            if verdict.whole:
                return Row(verdict.status, verdict.shape, verdict.remedy)
    if ledger.state(context.root) == NO_LEDGER:
        return Row(
            WARN,
            f"memory.mode is overlay and {ATTACH_LEDGER} does not exist, so nothing records an "
            f"attach",
            f"run `{ATTACH_STORE} --check`",
        )
    answer = _binding_answer(context, ledger)
    # The ledger exists, so from here on this row's job is to say what the **overlay** makes of it
    # (principle 5), for the reason `_granted_commands` gives: the ledger is a path a clone can
    # commit, and the overlay is the one source a repository cannot choose. Every arm below but the
    # last refuses to print the word "attached".
    if isinstance(answer, str):
        return _uncorroborated(answer)
    state = answer.state
    if state == UNBOUND:
        from stayfixed.attach.binding import OVERLAY_REPAIR, damaged_overlay

        # An overlay whose root or `projects/` is a file holds no record of any binding, so a
        # bound project reads as unbound there; the remedy for that is the overlay's repair, and
        # never removing the ledger, which is this checkout's record of a real attach.
        damaged = damaged_overlay(answer.overlay)
        if damaged is not None:
            return Row(
                WARN,
                f"{ATTACH_LEDGER} records an attach, but {damaged} is not a directory, so the "
                f"overlay this machine records is damaged and cannot say whether this checkout is "
                f"bound",
                OVERLAY_REPAIR.format(path=damaged, command="`stayfixed doctor`"),
            )
        return Row(
            WARN,
            f"{ATTACH_LEDGER} records an attach, but the overlay this machine records has no "
            f"binding for this project — a clone can commit that file, so it is not evidence of "
            f"an attach",
            _re_attach(),
        )
    if state == NO_ORIGIN:
        return Row(RED, NO_ORIGIN_CAUSE, NO_ORIGIN_WAY_OUT)
    if state == MISMATCH:
        return Row(RED, DIFFERENT_REMOTE, _REBIND)
    if isinstance(harness, UnreadHome):
        remedy = harness.remedy
        if harness == HOME_DIFFERS:
            remedy += f"; {_CHECKED_AT_A_TERMINAL}"
        return Row(WARN, f"attached; {harness.cause}; the binding is {state}", remedy)
    if verdict is None:
        verdict = _harness_verdict(context, answers, harness)
    return Row(
        verdict.status,
        f"attached; the harness memory path is {verdict.shape}; the binding is {state}",
        verdict.remedy,
    )


# Where `HOME` differs, the way to have this row judge the link under it: at a terminal `HOME` is
# the home the link goes under, and this row checks it there.
_CHECKED_AT_A_TERMINAL = "`stayfixed doctor` run from a terminal checks the link under HOME"


# Why the overlay could not corroborate the ledger, as `_binding_answer`'s three answers. Not
# statuses and not sentences: the row below decides both, and these are the question's own
# vocabulary. `UNRESOLVED` is about the repository, the other two about this machine.
UNRESOLVED: Final = "unresolved"
NO_OVERLAY: Final = "no-overlay"
UNASKABLE: Final = "unaskable"
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
    # reason those rows exist: the consent record lives in the overlay, and this file does not.
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


def _recorded_fallback(context: Context) -> Path | None:
    """The directory `autoMemoryDirectory` in `.claude/settings.local.json` names, as written, or
    `None` where the file holds no such absolute path or cannot be read as a settings document.

    The file is one a clone can commit, so the value is never resolved and never printed: it is
    compared exactly with the one value `attach` writes there, the owning checkout's store,
    resolved (`str(store.path.resolve())`), and so only once that store has resolved. Resolved, a
    committed value naming a link the clone also committed would be read as the store. Nor is it
    compared with every directory a harness link may point at (`harness_targets`): that set holds
    this checkout's own `paths.memory`, followed through a final link, and a branch that commits
    that link and this file beside it names any directory it likes."""
    from pathlib import Path

    from stayfixed.attach.permissions import local_document, settings_document
    from stayfixed.attach.write import FALLBACK_KEY
    from stayfixed.errors import Failure, Refusal

    try:
        value = settings_document(local_document(context.root)).get(FALLBACK_KEY)
    except (Failure, Refusal, OSError, ValueError):
        return None
    if not isinstance(value, str) or not Path(value).is_absolute():
        return None
    return Path(value)


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


def _store_of(context: Context, answers: Answers, checkout: Path) -> Store | None:
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
    return resolved_or_none(lambda: resolve(checkout, context.config, machine=context.machine))


def _harness_verdict(context: Context, answers: Answers, harness: Path) -> _Verdict:
    """The one reading of the harness memory path: each machine state one status, sentence and
    remedy, answered alike from the main checkout and from a linked worktree.

    One ordered reading, and the first row that matches answers. Each row is named as the state
    it answers is named in `tests/attach/test_doctor.py`'s `ONE_MACHINE_STATE`, and the name is
    the comment on the line that answers it:

    - `dangling`: a link that reaches nothing. Red; `attach`.
    - `real-directory-no-fallback`: a real directory, and no `autoMemoryDirectory` recorded. Red,
      the row's whole detail; move it aside, then `attach`.
    - `targets-unaskable`: where a harness link may point cannot be asked (`harness_targets`
      refuses). Warn, naming whose `paths.memory` and why; replace the symlink, or make the
      directory readable.
    - `links-elsewhere`: a link to a directory a harness link may not point at. Red; `attach`.
    - `tree-gone`: the store does not resolve, and its link tree is gone. Warn; `attach`
      (`_unresolved`).
    - `tree-there-not-resolving`: the store does not resolve, and its link tree is there. Warn;
      `memory index --check` (`_unresolved`).
    - `fallback-elsewhere`: a real directory, and `autoMemoryDirectory` naming anything but the
      owning checkout's store, resolved, the one value `attach` writes there. As
      `real-directory-no-fallback`.
    - `trust-record-unreadable`: this machine's trust record cannot be read. Warn; `memory trust
      --in-repo-memory`, which says why.
    - `attached`: a link to the store, the gate open. Ok.
    - `link-lapsed`: a link to the store, the gate closed, the approval lapsed. Warn;
      `HARNESS_LAPSED`'s remedy (read what changed, approve, `attach`).
    - `link-never-approved`: a link to the store, the gate closed, never approved. Warn;
      `attach`, which withdraws the link in exactly this state.
    - `fallback-approved`: a real directory beside the fallback, the gate open. Ok.
    - `fallback-unapproved`: a real directory beside the fallback, the gate closed, lapsed or
      never approved. Warn, naming which; `attach`, which withdraws the fallback in exactly this
      state.
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
    it quotes is held to `PATH_VALUE`, the grammar a report may print.
    `real-directory-no-fallback` is red without asking it, since nothing it could answer would
    change that.

    A file or anything else that is no link and no directory reads as nothing in place
    (`tree-gone`, `tree-there-not-resolving`, `no-links-approved`, `lapsed-links-withdrawn`,
    `never-approved`), as it did.
    """
    from stayfixed.attach import ATTACH_STORE
    from stayfixed.attach.permissions import LOCAL_SETTINGS
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
    recorded = _recorded_fallback(context) if shape == _REAL_DIRECTORY else None
    if shape == _REAL_DIRECTORY and recorded is None:  # real-directory-no-fallback
        return _real_directory(harness)
    words = {
        _LINK: "a link",
        _REAL_DIRECTORY: f"a real directory beside the {FALLBACK_KEY} fallback",
        _OTHER: "something other than a link",
        _ABSENT: "not in place",
    }[shape]
    owner = _owner(context)
    try:
        targets = harness_targets(context.root, owner, context.config)
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
    checkout = context.root if reached is not None and reached != targets[0] else owner
    store = _store_of(context, answers, checkout)
    if store is not None and reached is not None and store.path.resolve() != reached:
        # A linked worktree whose own tree does not resolve resolves through the main checkout
        # (`memory.store.resolved`), and that store is not the one the harness reads through a
        # link to the worktree's own tree.
        store = None
    if store is None:  # tree-gone, tree-there-not-resolving
        return _unresolved(context, checkout, shape, words, relink)
    if shape == _REAL_DIRECTORY and recorded != store.path.resolve():  # fallback-elsewhere
        return _real_directory(harness)
    try:
        gate = harness_gate(store, context.config)
    except Refusal:  # trust-record-unreadable
        return _Verdict(
            WARN,
            f"{words}, and this machine's trust record cannot be read, so whether the harness "
            "should see this store could not be checked",
            "run `stayfixed memory trust --in-repo-memory`, which says why the trust record "
            "cannot be read, then `stayfixed doctor` again",
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
        return _Verdict(  # link-never-approved
            WARN,
            "a link to the store, although no approval is recorded for the store — the harness "
            "reads notes nobody approved",
            relink,
        )
    if shape == _REAL_DIRECTORY:
        # The file named through the harness registry (`CLAUDE.local_settings`), as `attach`'s own
        # fallback line names it: a harness fact spelled here is one more place a new harness
        # would have to be found.
        fallback = f"a real directory, and {FALLBACK_KEY} in {LOCAL_SETTINGS} points the harness"
        if gate == GATE_OPEN:  # fallback-approved
            return _Verdict(OK, f"{fallback} at the store instead", "")
        why = APPROVAL_LAPSED if gate == GATE_LAPSED else "no approval is recorded for the store"
        return _Verdict(  # fallback-unapproved
            WARN,
            f"{fallback} at the store, although {why} — the harness reads notes nobody approved",
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


def _real_directory(harness: Path) -> _Verdict:
    """The `real-directory-no-fallback` and `fallback-elsewhere` rows of `_harness_verdict`: a
    real directory at the harness memory path with no fallback beside it that points the harness
    at the store. The remedy is `attach`'s own (`write.FALLBACK_UNAVAILABLE`): the directory can
    hold notes the harness wrote, so it is moved aside and never removed."""
    from stayfixed.attach import ATTACH_STORE
    from stayfixed.doctor.api import RED

    return _Verdict(
        RED,
        "the harness memory path is a real directory rather than a link to the store, so this "
        "checkout looks attached and behaves like nothing",
        f"move {harness} aside, then run `{ATTACH_STORE}` again",
        whole=True,
    )


def _unresolved(context: Context, checkout: Path, shape: str, words: str, relink: str) -> _Verdict:
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

    tree = checkout / context.config.paths.memory
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


def _binding_answer(context: Context, ledger: _Ledger) -> Binding | str:
    """The overlay binding this repository would attach under, or the label of why there is none.

    Three different situations are three answers and never one `None` — a ledger naming a store
    the overlay does not permit, a machine that records no overlay at all, and a machine with no
    usable `git` — because collapsed, the `attached` row would read the last two as *attached*.
    They are not one finding. A ledger whose store is not this project's share of the recorded
    overlay is a fact about **this repository**, and `.stayfixed/local/attach.json` is a path a
    clone can commit, so it earns a warning. A missing overlay or a missing `git` is a fact about
    **our own inputs**, and a row that accused the repository on it would be reporting on itself.

    The three are told apart without restructuring `read_binding`, which raises `Refusal` for
    two of them: `context.overlay_root` is the answer of the same `overlay_root(machine)` that
    function calls with the same argument, so asking it first takes the overlay-is-missing arm
    off the table, and what is left of `Refusal` is the store that is not this project's
    permitted root. Anything else that goes wrong — a `Failure` out of the overlay's own record,
    a ledger this process may not read — answers `UNASKABLE`, which is the conservative
    direction: it never accuses the repository for something it may not have done.
    """
    from pathlib import Path

    from stayfixed.attach.binding import read_binding
    from stayfixed.errors import Failure, Refusal
    from stayfixed.gitenv import GitUnavailable

    if context.overlay_root is None:
        return NO_OVERLAY
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
            context.root, store=Path(recorded.store), machine=context.machine, config=context.config
        )
    except Refusal:
        return UNRESOLVED
    except (Failure, GitUnavailable):
        return UNASKABLE


def _granted_commands(context: Context) -> tuple[set[Placed] | None, str | None]:
    """Every marked command the overlay grants this repository **right now**, where it grants it,
    or `None`; and,
    beside it, why that grant stops at `common/` where "the overlay does not grant" an entry would
    be false: `MISMATCH` or `UNREADABLE_RECORD`, else `None` (`_wording` says what each changes).

    The overlay is what `attach` merges from, and it is trusted by construction: its root comes
    from the machine configuration, which `config/machine.py` keeps unselectable by a repository.
    So it is the one source that can answer whether an entry claiming the stayfixed marker is
    really stayfixed's — and it is the answer the ledger cannot give, because
    `.stayfixed/local/attach.json` is a path a clone can commit.

    `overlay_entries` is the same enumeration `attach` installs from, so the strings compared are
    the strings `attach` would write: the *marked command*, not the id. Comparing ids alone would
    still let a repository take an id the overlay does grant and hang a different command on it.
    And each is where `attach` would write it, and as it would write it — its event, its group's
    matcher and the whole entry, read back by `scaffold.wanted_placements` as the `hook-entries`
    walk reads the settings file — because the granted command hung under another event or matcher,
    or inside an entry of another `type` or with fields the overlay did not write, is a hook the
    overlay never granted.

    **The ledger is not read here.** The binding is the one `binding_for` derives from the overlay
    this machine records and the project's name, the same one `attach` would install from, and
    not the one the ledger's `store` names. Asked through the ledger's store, a store that is not
    this project's would answer "could not be asked", and that is a warning: a clone that
    committed a ledger recording its own entry, under any store it liked, would turn
    `hook-entries`' red into an exit of 0. Whether that store is right is the `attached` row's
    question, and it warns there.

    `None` means the overlay this machine records could not be asked — no `git`, an overlay
    record that will not read, or a hook file the overlay grants this checkout from (`common/`'s,
    or that of the project its record binds this checkout to) that will not parse — and is
    decided by this machine's state alone. **Nothing a repository's name picks out may answer
    `None`**: a `None` turns `hook-entries`' red into a warning, and `project.name` is committed,
    so a file the name chooses under the overlay's `projects/` would let a clone choose that
    warning. A machine that records no overlay is not `None` either: nothing on it can grant,
    which is the empty set, and `_claims` says why it is empty. An empty set is "the overlay
    grants nothing", which is an answer.

    **`projects/<name>/` grants only a checkout the overlay's record binds.** The name is
    committed, so it can name another project of this machine's overlay, and what that project's
    directory grants is that project's: a clone naming itself after it, with an entry equal to
    one granted there and a ledger recording its id, would read "all accounted for". So for a
    binding that is not `bound` — no record, a record of another remote, or no `origin` to compare
    — the answer is what `common/` grants, and the project's hook file is not opened: one there
    that will not parse would answer `None`. Whether the binding is right is the `attached` row's
    question, and it says so there.

    **A binding record that cannot be read binds nothing.** Whether the checkout is bound is read
    from `projects/<name>/project.toml`, so deciding it opens a file the name picks out; one that
    cannot be read (`binding.UnreadableRecord`) is answered as no record, and the answer is what
    `common/` grants. The cost falls on an owner whose own record is broken: their per-project
    entries read red rather than warn, because the record that would vouch for them is the one
    that cannot be read, and the `attached` row says the overlay could not be asked.

    **A mismatch and an unreadable record are named beside the grant, and nothing else is.** For
    either, `projects/<name>/` may grant an entry `common/` does not — to the checkout the record
    binds, or would bind if it read — so "the overlay does not grant them" is false, and the
    rebuild it offers is one `attach` refuses. With no record, or no `origin`, nothing in the
    overlay grants this checkout more than `common/` does, and the overlay refusing is what
    happened.

    **Nor does a `project.name` no directory under the overlay can carry make the overlay
    unaskable.** One that a file under `projects/` holds, or one longer than the filesystem
    allows, has no binding record — `binding.cannot_exist`'s paths are records the overlay does
    not have — so it is never bound and the answer is what `common/` grants. Only below a
    directory whose record binds this checkout's `origin` does the name choose nothing, and a
    file there where `claude/` goes is the owner's overlay failing to answer, `None` like any
    other.
    """
    from stayfixed.attach.binding import UnreadableRecord, binding_for
    from stayfixed.attach.permissions import common_entries, overlay_entries
    from stayfixed.errors import Failure, Refusal
    from stayfixed.memory.api import BOUND, MISMATCH
    from stayfixed.scaffold import wanted_placements

    overlay = context.overlay_root
    if overlay is None:
        return set(), None
    narrowed: str | None = None
    try:
        try:
            binding: Binding | None = binding_for(
                context.root, context.config, machine=context.machine
            )
        except UnreadableRecord:
            binding, narrowed = None, UNREADABLE_RECORD
        if binding is not None and binding.state == BOUND:
            wanted = overlay_entries(binding)
        else:
            wanted = common_entries(overlay)
        granted = set(wanted_placements(wanted))
    except (Failure, Refusal, OSError):
        return None, None
    if binding is not None and binding.state == MISMATCH:
        narrowed = MISMATCH
    return granted, narrowed


def _wording(narrowed: str | None = None) -> Wording:
    """How `hook-entries` names this area's ledger, the overlay that grants, and the commands that
    repair them: stayfixed's own fixed strings, as `Wording` requires, none of them read from the
    repository or the machine.

    `narrowed` is `_granted_commands`' reason the grant stops at `common/`. For `MISMATCH` the
    entries it leaves red are told that the binding is what is wrong, not the grant, and handed
    the `attached` row's remedy: the rebuild `vouch` names is one `attach` refuses on a mismatch
    without `--trust-remote`. For `UNREADABLE_RECORD` they are told the record cannot be read, and
    pointed at the command that says why. Both are fixed text: neither names the project or a
    remote, which are the repository's.

    A function and not a module-level constant only because building the value imports the doctor
    area's surface and the ledger's path, and an import in this module sits inside a function body
    (the module docstring says why)."""
    from stayfixed.attach import ATTACH_STORE
    from stayfixed.config.layout import ATTACH_LEDGER
    from stayfixed.doctor.api import Wording
    from stayfixed.memory.api import MISMATCH

    # Said of a checkout whose grant stops at `common/` for a reason other than a refusal.
    only_common = "the overlay grants this checkout only what it grants every project, because its"
    ungranted: str | None = None
    regrant: str | None = None
    if narrowed == MISMATCH:
        ungranted = (
            f"{only_common} record binds this project to a remote other than this checkout's "
            f"`origin`"
        )
        regrant = (
            f"settle the binding, as the `attached` row says: {_REBIND}; then run `stayfixed "
            f"doctor` again"
        )
    elif narrowed == UNREADABLE_RECORD:
        ungranted = f"{only_common} binding record for this project cannot be read"
        regrant = (
            "run `stayfixed attach --check`, which reports why the binding record cannot be "
            "read; repair it, then run `stayfixed doctor` again"
        )
    return Wording(
        record=ATTACH_LEDGER,
        unreadable=(
            "cannot be read as a ledger, so which of those entries `stayfixed attach` installed "
            "could not be established"
        ),
        inspect=f"check that {ATTACH_LEDGER} is readable and is the file your last attach wrote",
        source="the overlay",
        unsourced="this machine records no overlay",
        unaskable=(
            "the overlay this repository is bound to could not be asked which entries it grants"
        ),
        diagnose="run `stayfixed attach --check`, which reports why the overlay cannot be read",
        setup="run `stayfixed setup --overlay <path>` to record the overlay that grants them",
        vouch=f"`{ATTACH_STORE}`",
        ungranted=ungranted,
        regrant=regrant,
    )


def _claims(context: Context, ledger: _Ledger) -> Claims:
    """What `attach` put into settings files, for `hook-entries`' provenance column.

    The ledger says which marker ids the last `attach` recorded, and the overlay says which
    marked commands it grants right now, and where; the row needs both, because the ledger is a
    file a clone can commit. The overlay is asked unless the ledger is readable and records
    nothing, because then nothing can be absolved and asking it costs a `git` call: an empty
    ledger keeps its old answer, every entry claiming the marker is one no attach recorded. A
    ledger that cannot be read is not that: the grant is what decides whether an entry beside it
    may be the owner's (a warning) or is one nothing on this machine vouches for (red), so the
    overlay is asked for it too.

    `sourced` is whether this machine records an overlay at all, read from the machine file and
    nothing else: without one the grant is empty because nothing could grant, and the row says
    so and how to record one rather than that the overlay refused.
    """
    from stayfixed.doctor.api import Claims

    found = _attach_ledger_entries(ledger.state(context.root))
    granted, narrowed = _granted_commands(context) if found is None or found else (set(), None)
    return Claims(
        found,
        None if granted is None else frozenset(granted),
        sourced=context.overlay_root is not None,
        wording=_wording(narrowed),
    )


def register() -> Contribution:
    """The `attached` row and this area's claims, sharing one `_Ledger` for the report, and the
    row's one `Answers` for the note store."""
    from stayfixed.doctor.api import Contribution
    from stayfixed.memory.api import Answers

    answers = Answers()
    ledger = _Ledger()
    return Contribution(
        checks=(("attached", lambda context: _attached(context, answers, ledger)),),
        claims=lambda context: _claims(context, ledger),
    )
