"""The binding's row in `stayfixed doctor`, and what this area put into settings files.

`attached` is this area's: it reads the attach ledger this area writes and asks the overlay, through
this area's own `read_binding`, whether a binding stands behind it. The `claims` are this area's
too: `hook-entries`, which stays in the core because every settings file is the core's to walk,
lists each hook entry with its provenance, and only this area can say which entries `attach`
recorded and which of them the overlay still grants. `doctor`'s core discovers this module by
name (CONTRIBUTING.md, "Areas") and imports nothing of this area.

The overlay root and the note store come from the `Answers` this module's `register()` creates,
one per report, so the binding the row reads and the claims `hook-entries` reads ask the overlay
root once between them.

Every import sits inside a function body, as in a `hooks.py`: this module is imported by
discovery, and a module-level import here would be one more thing every `doctor` run loads
before it has asked anything.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from pathlib import Path

    from stayfixed.attach.binding import Binding
    from stayfixed.doctor.api import Claims, Context, Contribution, Row, Status
    from stayfixed.memory.api import Answers


def _attach_ledger_entries(root: Path) -> dict[str, str] | None:
    """The marker ids this repository's last `attach` claims, `{}` when it never ran, `None`
    when the file is there and cannot be read as a ledger.

    Three answers and not two. `ledger()` raises on a file that is not JSON, is not an object,
    or names something `attach` could not have written — and `.stayfixed/local/attach.json` is a
    path a clone can commit, because `.gitignore` does not untrack a committed file. Letting
    that reach the report's guard made a repository able to force `hook-entries` red with the
    detail "this check could not run: Failure" and a remedy that cannot help, on an installation
    with nothing wrong with it. The row reports the file instead.
    """
    from stayfixed.attach.write import ledger
    from stayfixed.config.layout import ATTACH_LEDGER
    from stayfixed.errors import Failure, Refusal

    if not (root / ATTACH_LEDGER).is_file():
        return {}
    try:
        return dict(ledger(root).entries)
    except (Failure, Refusal):
        return None


def _attached(context: Context, answers: Answers) -> Row:
    """Attach state, and the shape of the harness memory path.

    `attach` prefers a symlink at `~/.claude/projects/<slug>/memory`, because a settings-file
    value is subject to workspace trust and a link is not. A **real directory** there is a
    failure of its own and the reason this check exists rather than a general "not attached":
    the harness's native reader finds a directory, reads nothing out of it, and reports no fault
    — it looks attached and behaves like nothing.

    A path that is simply absent is not that. `worktree.harness_link_needed` gates the link on
    the same trust record every other channel is gated on, so an unapproved store correctly has
    no link, and calling that red would make `doctor` red on a correct fresh install. So this
    check *asks that function* rather than assuming: absent-and-not-wanted is green and says
    which of the two it is, absent-and-wanted is a warning, because a store the record approves
    and a harness that cannot see it is an attach that did not finish.

    **The link's target is compared, and the sentence about it is only ever printed when it is
    true.** The shape used to be computed into `detail` and then dropped for the status, and
    "the harness memory path is a link to the store" was printed for *any* symlink — a dangling
    one, or one pointing at an unrelated directory — with the row green underneath it. On the
    one channel `attach` uses to reach the model, that is a false statement about where the
    model's memory comes from, and the two states it hid are the same failure the real
    directory is flagged for: one reads nothing, the other reads somebody else's notes.
    """
    from stayfixed.config.layout import ATTACH_LEDGER
    from stayfixed.doctor.api import OK, RED, WARN, Row
    from stayfixed.memory.api import (
        DIFFERENT_REMOTE,
        MISMATCH,
        NO_ORIGIN,
        NO_ORIGIN_CAUSE,
        NO_ORIGIN_WAY_OUT,
        PROJECTS,
        UNBOUND,
        harness_memory_path,
    )

    config = context.config
    if config.memory.mode != "overlay":
        # `memory.mode` is repository-authored and is safe to print for one reason only: the
        # loader holds it to a fixed set of three words, so what reaches this line is one of
        # stayfixed's own labels rather than a string a clone chose.
        return Row(OK, f"memory.mode is {config.memory.mode}; there is no overlay to bind to")
    recorded = (context.root / ATTACH_LEDGER).is_file()
    harness = harness_memory_path(context.root, context.home)
    if harness.is_dir() and not harness.is_symlink():
        return Row(
            RED,
            "the harness memory path is a real directory rather than a link to the store, so "
            "this checkout looks attached and behaves like nothing",
            # `<project>` and not `config.project.name`: the name is repository-authored, and a
            # remedy is as much output as a detail is.
            f"remove {harness} and run "
            f"`stayfixed attach --store <overlay>/{PROJECTS}/<project>/memory`",
        )
    if not recorded:
        return Row(
            WARN,
            f"memory.mode is overlay and {ATTACH_LEDGER} does not exist, so nothing records an "
            f"attach",
            "run `stayfixed attach --store <overlay>/projects/<project>/memory --check`",
        )
    answer = _binding_answer(context, answers)
    # The ledger exists, so from here on this row's job is to say what the **overlay** makes of it
    # (principle 5), for the reason `_granted_commands` gives: the ledger is a path a clone can
    # commit, and the overlay is the one source a repository cannot choose. Every arm below but the
    # last refuses to print the word "attached".
    if isinstance(answer, str):
        return _uncorroborated(answer)
    state = answer.state
    if state == UNBOUND:
        return Row(
            WARN,
            f"{ATTACH_LEDGER} records an attach, but the overlay this machine records has no "
            f"binding for this project — a clone can commit that file, so it is not evidence of "
            f"an attach",
            "run `stayfixed attach --store <overlay>/projects/<project>/memory --check`; if this "
            "checkout was never attached on this machine, remove the ledger",
        )
    if state == NO_ORIGIN:
        return Row(RED, NO_ORIGIN_CAUSE, NO_ORIGIN_WAY_OUT)
    if state == MISMATCH:
        return Row(
            RED,
            DIFFERENT_REMOTE,
            "run `stayfixed attach --check`, and `--trust-remote` only if it should be",
        )
    status, shape, remedy = _harness_shape(context, answers, harness)
    return Row(
        status, f"attached; the harness memory path is {shape}; the binding is {state}", remedy
    )


# Why the overlay could not corroborate the ledger, as `_binding_answer`'s three answers. Not
# statuses and not sentences: the row below decides both, and these are the question's own
# vocabulary. `UNRESOLVED` is about the repository, the other two about this machine.
UNRESOLVED: Final = "unresolved"
NO_OVERLAY: Final = "no-overlay"
UNASKABLE: Final = "unaskable"
# The fourth, and it is about the repository rather than about this machine. A ledger that is
# there and will not parse used to answer `UNASKABLE` with the other two, so the row said
# "no `git`, or a record this process could not read" and the remedy said "run `stayfixed doctor`
# again where `git` runs" — about a file in the checkout the reader is standing in. `skip` never
# reaches the exit code, so a repository's own committed, malformed ledger was also silent.
UNREADABLE_LEDGER: Final = "unreadable-ledger"
_RE_ATTACH = (
    "run `stayfixed attach --store <overlay>/projects/<project>/memory --check`; if this "
    "checkout was never attached on this machine, remove the ledger"
)


def _uncorroborated(reason: str) -> Row:
    """The row for a ledger the overlay did not confirm, split by what the reason is *about*.

    `warn` accuses the repository and `skip` does not, and the split is the point: `skip` never
    reaches the exit code, so using it for the repository's own doing would be the defect this
    function was written to remove, and using `warn` for a machine where `setup` has never run
    would make `doctor` warn on every correct fresh install. Neither row ever says "attached".

    **Four reasons and not three.** A ledger that is there and will not parse was answering
    with the machine-side two, so the row it got blamed `git` for a malformed file in the
    reader's own checkout and offered a remedy — run this somewhere `git` works — that could
    not fix it. By this function's own rule it is the repository's doing and warns.
    """
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
            _RE_ATTACH,
        )
    if reason == UNREADABLE_LEDGER:
        return Row(
            WARN,
            f"{ATTACH_LEDGER} is here and cannot be read as a ledger, so nothing in it can be "
            f"corroborated and this checkout's attach state is unknown — {not_evidence}",
            f"remove {ATTACH_LEDGER}, then run `stayfixed attach --store "
            f"<overlay>/projects/<project>/memory --check`",
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


def _harness_shape(context: Context, answers: Answers, harness: Path) -> tuple[Status, str, str]:
    """The status, the sentence and the remedy for the harness memory path, as one answer.

    One function because the status and the sentence must not be able to disagree — computing
    the shape and then discarding it for the status is the defect this replaces.

    The comparison is against the resolved store's path, which is what
    `worktree._apply_harness_link` links to, resolved on both sides so that two spellings of one
    directory are one answer. A store that does not resolve means the comparison cannot be made
    at all, which is a warning naming what could not be asked rather than a green sentence
    asserting what was not checked.
    """
    from stayfixed.doctor.api import OK, RED, WARN
    from stayfixed.memory.api import PROJECTS, harness_link_needed

    # The remedy every arm but the green ones carries: one command puts the link back where
    # `attach` puts it, whatever the wrong shape was. `<overlay>` and `<project>` and never
    # `config.project.name`, for the reason `_attached`'s real-directory row gives.
    relink = f"run `stayfixed attach --store <overlay>/{PROJECTS}/<project>/memory`"
    store = answers.store(context)
    if harness.is_symlink():
        if store is None:
            return (
                WARN,
                "a link, and the note store does not resolve, so what it points at could not "
                "be checked",
                "run `stayfixed memory index --check`, then `stayfixed doctor` again",
            )
        if harness.resolve() == store.path.resolve():
            return OK, "a link to the store", ""
        if not harness.exists():
            return RED, "a dangling link, so the harness reads nothing through it", relink
        return (
            RED,
            "a link to a directory that is not this project's note store, so the harness "
            "reads notes this repository is not bound to",
            relink,
        )
    if store is not None and harness_link_needed(store, context.config):
        return (
            WARN,
            "not in place, although this store's trust record allows it, so the harness sees "
            "no memory here",
            relink,
        )
    return OK, "not in place, which is what this store's trust record asks for", ""


def _binding_answer(context: Context, answers: Answers) -> Binding | str:
    """The overlay binding this repository would attach under, or the label of why there is none.

    Three different situations used to collapse into one `None` — a ledger naming a store the
    overlay does not permit, a machine that records no overlay at all, and a machine with no
    usable `git` — and the `attached` row then treated the last two as *attached*. They are not
    one finding. A ledger whose store is not this project's share of the recorded overlay is a
    fact about **this repository**, and `.stayfixed/local/attach.json` is a path a clone can
    commit, so it earns a warning. A missing overlay or a missing `git` is a fact about **our
    own inputs**, and a row that accused the repository on it would be reporting on itself.

    The three are told apart without restructuring `read_binding`, which raises `Refusal` for
    two of them: `answers.overlay` is the answer of the same `overlay_root(machine)` that
    function calls with the same argument, so asking it first takes the overlay-is-missing arm
    off the table, and what is left of `Refusal` is the store that is not this project's
    permitted root. Anything else that goes wrong — a `Failure` out of the overlay's own record,
    a ledger this process may not read — answers `UNASKABLE`, which is the conservative
    direction: it never accuses the repository for something it may not have done.
    """
    from pathlib import Path

    from stayfixed.attach.binding import read_binding
    from stayfixed.attach.write import ledger
    from stayfixed.errors import Failure, Refusal
    from stayfixed.gitenv import GitUnavailable

    if answers.overlay(context) is None:
        return NO_OVERLAY
    try:
        store = Path(ledger(context.root).store)
    except (Failure, Refusal):
        # This one is the repository's file and not our inputs, so it does not join the other
        # two: a clone can commit `.stayfixed/local/attach.json`, and a file that will not parse
        # is a fact about the checkout the reader is standing in.
        return UNREADABLE_LEDGER
    try:
        return read_binding(context.root, store=store, machine=context.machine)
    except Refusal:
        return UNRESOLVED
    except (Failure, GitUnavailable):
        return UNASKABLE


def _granted_commands(context: Context, answers: Answers) -> set[str] | None:
    """Every marked command the overlay grants this repository **right now**, or `None`.

    The overlay is what `attach` merges from, and it is trusted by construction: its root comes
    from the machine configuration, which `config/machine.py` keeps unselectable by a repository.
    So it is the one source that can answer whether an entry claiming the stayfixed marker is
    really stayfixed's — and it is the answer the ledger cannot give, because
    `.stayfixed/local/attach.json` is a path a clone can commit.

    `overlay_entries` is the same enumeration `attach` installs from, so the strings compared are
    the strings `attach` would write: the *marked command*, not the id. Comparing ids alone would
    still let a repository take an id the overlay does grant and hang a different command on it.

    **The ledger is not read here.** The binding is the one `binding_for` derives from the overlay
    this machine records and the project's name, the same one `attach` would install from, and
    not the one the ledger's `store` names. Asked through the ledger's store, a store that is not
    this project's answered "could not be asked", and that is a warning: a clone that committed a
    ledger recording its own entry, under any store it liked, turned `hook-entries`' red into an
    exit of 0. Whether that store is right is the `attached` row's question, and it warns there.

    `None` means the overlay this machine records could not be asked — no `git`, an overlay
    record that will not read, or an overlay whose own hook file will not parse — and is decided
    by this machine's state alone. A machine that records no overlay is not that: nothing on it
    can grant, which is the empty set, and `_claims` says why it is empty. An empty set is "the
    overlay grants nothing", which is an answer.

    **Nor is a `project.name` no directory under the overlay can carry.** The name is committed,
    and it picks `projects/<name>/` out of the overlay; one that a file there already holds, or
    one longer than the filesystem allows, used to make the read fail and so answer `None`, which
    let a clone turn this row's red into a warning with nothing on the machine broken.
    `binding.cannot_exist` reads such a path as one the overlay has no file at, so the answer is
    what `common/` grants, the same as for a name the overlay has no project for.
    """
    from stayfixed.attach.binding import binding_for
    from stayfixed.attach.permissions import overlay_entries
    from stayfixed.errors import Failure, Refusal

    if answers.overlay(context) is None:
        return set()
    try:
        binding = binding_for(context.root, context.config, machine=context.machine)
        wanted = overlay_entries(binding)
    except (Failure, Refusal, OSError):
        return None
    return {
        entry["command"]
        for groups in wanted.values()
        for group in groups
        for entry in group["hooks"]
        if isinstance(entry.get("command"), str)
    }


def _claims(context: Context, answers: Answers) -> Claims:
    """What `attach` put into settings files, for `hook-entries`' provenance column.

    The ledger says which marker ids the last `attach` recorded, and the overlay says which
    marked commands it grants right now; the row needs both, because the ledger is a file a clone
    can commit. The overlay is asked unless the ledger is readable and records nothing, because
    then nothing can be absolved and asking it costs a `git` call: an empty ledger keeps its old
    answer, every entry claiming the marker is one no attach recorded. A ledger that cannot be read
    is not that: the grant is what decides whether an entry beside it may be the owner's (a warning)
    or is one nothing on this machine vouches for (red), so the overlay is asked for it too.

    `sourced` is whether this machine records an overlay at all, read from the machine file and
    nothing else: without one the grant is empty because nothing could grant, and the row says
    so and how to record one rather than that the overlay refused.
    """
    from stayfixed.doctor.api import Claims

    found = _attach_ledger_entries(context.root)
    granted = _granted_commands(context, answers) if found is None or found else set()
    return Claims(
        found,
        None if granted is None else frozenset(granted),
        sourced=answers.overlay(context) is not None,
    )


def register() -> Contribution:
    """The `attached` row and this area's claims, sharing one `Answers` for the report."""
    from stayfixed.doctor.api import Contribution
    from stayfixed.memory.api import Answers

    answers = Answers()
    return Contribution(
        checks=(("attached", lambda context: _attached(context, answers)),),
        claims=lambda context: _claims(context, answers),
    )
