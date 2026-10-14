"""The adoption state machine: a project's gates move from advisory to enforcing one at a time,
each once it passes.

`[stayfixed] state` is the lifecycle (`initialised`, `adopting`, `installed`) and `enforced` the
gates promoted while adopting. `promote` runs gates strictly on the tree as it is and adds those
that pass to `enforced`, moving an `initialised` project to `adopting` with the first gate it
promotes. An `adopting` project with an empty `enforced` is a valid shape too, written by hand or
left by an earlier release, and `promote` takes it from there the same way. A custom gate is
promoted only once the base has its command, since `stayfixed gate` runs it only then: until it
lands there it is not run, and waits. Promoting the last configured gate writes `installed` and
empties the list, which under `installed` means every configured gate, so a gate added later
enforces from its first run — for a custom gate, the first run after it lands on the base, since
`stayfixed gate` runs none before. The state never moves back: there is no demotion, and loosening
is an owner's edit of `stayfixed.toml`, which `stayfixed gate` refuses to a pull request while
anything enforces.

**A gate that reads a file git does not track is never promoted.** The `docs` and `trail` gates
judge tracked files: CI checks out nothing else, so one that passes here over a file git does not
track would fail every pull request there. `stayfixed.assess.tracked` turns such a gate's result
into one that could not judge the tree, and a gate that could not judge is not promoted.

**One write, at one place.** `promote` changes `stayfixed.toml`'s `state` and `enforced` through
`rewrite_owned` and nothing else, so the manifest's record of an untouched document is
re-stamped with it and `uninstall` still takes the file back. It does not ask the ignore guard:
`stayfixed.toml` is a fixed name, which that guard exempts so that a person may keep it out of
git. Every refusal of the write that can be known in advance — a name, a gate already
enforcing, nothing left to promote, a document the editor cannot rewrite, a manifest the
re-stamp cannot read — comes before the first gate runs, because a custom gate is a command and
running it is not free. What is left is the disk refusing the write itself.

**What prints.** Gate names, which the loader holds to a grammar, counts and fixed text.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from stayfixed.assess.gates import GateContext, GateResult, run_gates
from stayfixed.assess.rule import read_base_gates
from stayfixed.assess.tracked import Unseen, as_ci_sees
from stayfixed.config.loader import read_document
from stayfixed.config.owned import OwnedKeyError, UnparsedDocument, rewrite
from stayfixed.config.schema import CONFIG_CHECK, Config
from stayfixed.errors import Refusal, StayfixedError
from stayfixed.project.api import rewrite_owned
from stayfixed.scaffold import Manifest

NOT_A_GATE = "every name must be a configured gate, and config is the configuration check"
NAMED_ENFORCES = (
    "one of the gates named already enforces; name only gates that do not yet, or none for "
    "every gate left"
)
ALL_ENFORCE = "every configured gate already enforces; there is nothing left to promote"
NO_GATE = "this project configures no gate, so there is nothing to promote"
UNEDITABLE = (
    "[stayfixed] state or enforced is written in a shape stayfixed does not rewrite in place, so "
    "no gate ran and nothing was written; write each on one line as it stands now, "
    "`state = {state}` and `enforced = {enforced}`, and run the command again"
)
UNWRITTEN = (
    "[stayfixed] state or enforced is written in a shape stayfixed does not rewrite in place, so "
    "nothing was written; set both by hand, in one edit, to `state = {state}` and "
    "`enforced = {enforced}`"
)


def _literals(state: str, enforced: Sequence[str]) -> dict[str, str]:
    """`state` and `enforced` as the one-line values a remedy names.

    Plain basic strings: a member of the lifecycle and gate names the loader has held to a
    grammar, so no character in them needs escaping.
    """
    listed = ", ".join(f'"{name}"' for name in enforced)
    return {"state": f'"{state}"', "enforced": f"[{listed}]"}


@dataclass(frozen=True)
class Transition:
    before: str
    after: str
    promoted: tuple[str, ...] = ()
    results: tuple[GateResult, ...] = ()  # every gate this run ran, in the order it ran them
    waiting: tuple[str, ...] = ()  # custom gates not run: the base does not have their command
    skipped: tuple[str, ...] = ()  # custom gates not run: `--builtin` asked for none
    unseen: tuple[Unseen, ...] = ()  # gates not promoted: they read files CI cannot see

    @property
    def failing(self) -> dict[str, int]:
        """Each gate that ran and did not pass, with its finding count."""
        return {r.name: len(r.findings) for r in self.results if r.answered and r.failing}

    @property
    def unanswered(self) -> tuple[str, ...]:
        """Each gate that could not run."""
        return tuple(r.name for r in self.results if not r.answered)


def _refuse_an_uneditable_document(root: Path, config: Config) -> None:
    """Refuse, before any gate runs, a document whose `state` or `enforced` the editor cannot
    rewrite in place.

    A trial edit of both keys, discarded. The values differ from any the document can hold, so
    the editor meets both lines rather than skipping one already at its value: `config` is never
    a gate's name, and the loader refuses it in `enforced`. Those values are made up, so the
    editor's own refusal, which tells the person to write the value it was setting, is not
    passed on: following it would enforce what no gate earned, or write a list that does not
    load. The remedy names the values the document holds now, in the one-line shape the editor
    rewrites. Both are bounded: a member of the lifecycle and gate names the loader has held to
    a grammar, each written as a plain basic string.
    """
    text = read_document(root)
    if text is None:
        return  # the configuration was loaded from it a moment ago; the write refuses its absence
    state = config.stayfixed.state
    other = "installed" if state != "installed" else "adopting"
    try:
        rewrite(text, {("stayfixed", "state"): other, ("stayfixed", "enforced"): (CONFIG_CHECK,)})
    except OwnedKeyError:
        values = _literals(state, config.stayfixed.enforced)
        raise OwnedKeyError(UNEDITABLE.format(**values)) from None


def _write(root: Path, state: str, enforced: tuple[str, ...]) -> None:
    """The state machine's two-key write, whose refusal names both keys at once.

    The two keys state one fact, and the editor edits them one at a time, so its own refusal
    names only the key it failed on: `enforced = []` alone, which is right only beside
    `installed`, and beside `adopting` enforces nothing. The values named are the ones this
    write earned, so following the remedy is the transition itself. A document that does not
    parse at all is refused in the editor's own words, with the parser's position.
    """
    try:
        rewrite_owned(root, {("stayfixed", "state"): state, ("stayfixed", "enforced"): enforced})
    except UnparsedDocument:
        # Not a shape: the file does not parse, a custom gate having written into it, say, and
        # the parser's position is the remedy.
        raise
    except OwnedKeyError:
        raise OwnedKeyError(UNWRITTEN.format(**_literals(state, enforced))) from None


def _not_on_base(
    root: Path, config: Config, wanted: Sequence[str], *, base: str, machine: Path | None
) -> tuple[str, ...]:
    """The custom gates in `wanted` whose command the base's `stayfixed.toml` does not have.

    `stayfixed gate` runs a custom gate only with the base's own command, so a promotion of one
    the base lacks would enforce a command the pull request carrying it never runs. The base is
    read only when a custom gate is wanted; a base that cannot be read, or has no copy, has no
    command, so every such gate waits.
    """
    custom = config.gates.custom
    asked = [name for name in wanted if name in custom]
    if not asked:
        return ()
    try:
        landed = read_base_gates(root, base, branch=config.project.base_branch, machine=machine)
    except StayfixedError:
        landed = {}
    return tuple(name for name in asked if landed.get(name) != custom[name])


def promote(
    root: Path,
    config: Config,
    names: Sequence[str],
    *,
    base: str,
    machine: Path | None,
    builtin: bool = False,
) -> Transition:
    """Enforce the named gates if every one of them passes now, or, with none named, each
    configured gate not yet enforcing that passes; `base` is what `plan` and `commit` judge a
    range against, what `bugs` compares the ledger with (where HEAD forked from it), and what a
    custom gate's command must already be on (`machine` loads the base's copy, as the tree's
    was loaded).

    `builtin` runs no custom gate, for a clone whose commands the person has not agreed to run:
    in a clone the base is the clone author's, so its having the command is no brake. A custom
    gate is promoted only by a run that ran it, so each one wanted is `skipped` and stays
    advisory, and a named one holds the rest back as a gate that waits does."""
    configured = config.gate_names
    if any(name not in configured for name in names):
        raise Refusal(NOT_A_GATE)
    enforcing = config.stayfixed.enforcing
    if any(name in enforcing for name in names):
        raise Refusal(NAMED_ENFORCES)
    state = config.stayfixed.state
    wanted = [n for n in configured if n in (names or configured) and n not in enforcing]
    if not wanted:
        if not configured:
            # Nothing configured is nothing wanted too, and completing the state would install
            # a project that never earned a gate, whether it had begun adopting or not.
            raise Refusal(NO_GATE)
        if state == "installed":
            raise Refusal(ALL_ENFORCE)
        # Every configured gate enforces and the state never said so: complete it.
        _write(root, "installed", ())
        return Transition(state, "installed")
    _refuse_an_uneditable_document(root, config)  # trial rewrite; before any gate runs
    Manifest.read(root)  # the write re-stamps its record, so one it cannot read refuses here
    skipped = tuple(n for n in wanted if builtin and n in config.gates.custom)
    asked = [n for n in wanted if n not in skipped]
    waiting = _not_on_base(root, config, asked, base=base, machine=machine)
    ran = run_gates(GateContext(root, config, base), [n for n in asked if n not in waiting])
    # A gate that reads a file git does not track passes here and fails every pull request in
    # CI, which never checks that file out: it could not judge the tree as CI will, so it is
    # not promoted (`stayfixed.assess.tracked`).
    results, unseen = as_ci_sees(root, config, ran)
    promoted = tuple(r.name for r in results if not r.failing)
    # With names, every one passes or nothing is written: one that failed, could not run, waits
    # or was not run holds the rest back.
    if (names and (len(promoted) < len(results) or waiting or skipped)) or not promoted:
        return Transition(state, state, (), results, waiting, skipped, unseen)
    enforced = enforcing | set(promoted)
    installed = enforced >= set(configured)
    after = "installed" if installed else "adopting"
    listed = () if installed else tuple(n for n in configured if n in enforced)
    _write(root, after, listed)
    return Transition(state, after, promoted, results, waiting, skipped, unseen)
