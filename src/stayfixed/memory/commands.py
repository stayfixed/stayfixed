"""The `memory` group. Every command takes `--store PATH`.

`--store` is an override of *where the notes are*, not of the rules about them: it is held to
the same target rule as a link the resolver found, so passing a path is not a way around the
overlay binding. `--machine` exists for the same reason the resolver takes one — a test that
did not thread it would read the developer's real configuration and, worse, write a trust
record into their home directory.

It is threaded exactly twice, into `load` and into `resolve`, and never again: `resolve` puts
it on the `Store` it builds, so every later call takes it from there. It used to be an optional
keyword on about twenty functions, and the only thing keeping a command's overlay, its index
destination and its trust record in agreement was that each of those call sites remembered to
pass it.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from stayfixed.areas import SubParsers
from stayfixed.command import CHECK_HELP, common_flags
from stayfixed.config.loader import load
from stayfixed.config.schema import Config
from stayfixed.errors import Failure, Refusal
from stayfixed.findings import labels, listed
from stayfixed.memory import trust
from stayfixed.memory.bundles import Bundle, fit, render
from stayfixed.memory.index import (
    INDEX_NAME,
    IndexCheck,
    Reconciliation,
    check_index,
    index_source,
    reconcile,
    render_index,
    write_index,
)
from stayfixed.memory.inventory import inventory, totals
from stayfixed.memory.store import Store, Unresolved, in_repository, resolved
from stayfixed.memory.worktree import harness_link_needed
from stayfixed.printed import printable, quoted
from stayfixed.result import Result


def _machine(args: argparse.Namespace) -> Path | None:
    value = getattr(args, "machine", None)
    return Path(value) if value else None


# `refusal_reason`'s own docstring: the string "must never reach model context unwrapped". Its
# only caller put it verbatim into a `Failure` message, and `cli._report` prints that message on
# **stdout** under `--json` — twice, in one object, since the envelope carries it as both
# `summary` and the message. `memory session-context` is a `hooks.json` entry, so the invariant
# was holding only on the expectation that those entries never pass `--json`: an expectation
# owned by a different area, asserted by no test here, and contradicted by `hooks.py` going to
# real lengths to keep this same string out of `HookResult.context`.
#
# So the detail is kept and wrapped, rather than dropped. A person running `memory index` by
# hand needs to know *which* group entry was refused; a model reading the same bytes needs the
# region markers that say the text is data. `trust.wrap` is what `refusal_reason` names as the
# way to have both, and `UnsafeNote` — a `Refusal`, exit 2 — is the right answer to a value
# that tries to forge the markers.
#
# A reason that has words of stayfixed's own — which cause, and the way out — says them *before*
# the region: inside it they are data a model is told not to act on, and the way out is the one
# thing a reader has to act on.
_SAID = "no memory store: {said}; the detail below is repository-authored text, shown as data"


def _no_store(reason: Unresolved) -> Failure:
    if reason.detail is None:
        return Failure(f"no memory store: {reason.said}")
    lead = _SAID.format(said=reason.said)
    return Failure(f"{lead}\n{trust.wrap(reason.detail, trust.new_nonce())}")


def _store(args: argparse.Namespace) -> tuple[Store, Config]:
    root = Path(args.root).resolve()
    machine = _machine(args)
    config = load(root, machine=machine)
    # `resolved` and not `resolve` + `refusal_reason`: the pair walked the whole resolution
    # twice, four `git` queries with a five-second timeout apiece each time, so a hanging `git`
    # cost a refused `memory session-context` up to forty seconds — once per `SessionStart`
    # bundle entry.
    found = resolved(root, config, override=args.store, machine=machine)
    if found[0] is None:
        raise _no_store(found[1])
    return found[0], config


# What the trust gate withholds until there is a record, said where a person will read it:
# `bundles.blocks` returns `[]` for repository-data notes, and `worktree.harness_link_needed`
# withholds the harness memory link from a store whose directory is inside the repository.
# `harness_link_needed` decides when one of these is said — the link's question, which is the
# wider one: whenever the notes or a committed index are withheld, so is the link — and
# `_holds_repository_data` which. The failure
# this closes was silent in both directions: `memory index` rewrites every note and `MEMORY.md`,
# so it used to revoke the very record it depends on, and nothing in any summary said why the
# model had stopped receiving standing rules.
_UNTRUSTED = (
    "this store holds repository data with no trust record, so none of it reaches a session — "
    "not through the standing-rules and volatile-notes bundles, nor through the harness memory "
    "link — run `stayfixed memory trust --in-repo-memory`"
)
# The overlay store whose notes are all the machine owner's: the bundles deliver them with no
# record, and only the link to the store's directory, which is inside the repository, waits.
# Said in its own words because `_UNTRUSTED`'s "none of it reaches a session" is false here.
_LINK_WAITS = (
    "the harness memory link to this store waits for a trust record, because the store's "
    "directory is inside the repository; its notes still reach a session through the "
    "standing-rules and volatile-notes bundles — run `stayfixed memory trust --in-repo-memory` "
    "to link it"
)
# The narrow case where a stayfixed-authored write cannot carry trust forward: the store changed
# under it, so re-recording would bless bytes the owner has never looked at. `refresh_if_trusted`
# refuses rather than guess, which is right, and the human has to be told which it was.
_DROPPED = (
    "the store changed while this command ran, so its trust record was not carried over — "
    "review the change and re-run `stayfixed memory trust --in-repo-memory`"
)
# `index._harvestable` refused to persist repository-authored titles into notes that are not
# themselves repository data. Said out loud because the alternative is a silent drop: the notes
# keep their own descriptions and nothing else in the output would differ.
_NOT_HARVESTED = (
    "{names} took no index line from {index}: it is committed to this repository and they are "
    "not, so its text was not written into memory the machine owns"
)
# `index._publishable` refused to write a repository-authored line into {index} because this
# run's destination reaches outside this project's own repository — the write-side mirror of
# `_NOT_HARVESTED`, said out loud for the same reason: a drop `render_index` makes on its own
# has no channel back to a person running the command, and a silent one is how repository text
# reaches every other project sharing that destination.
_NOT_PUBLISHED = (
    "{names} took no line in {index}: committed to this repository, while this run's "
    "destination reaches outside it, so none of it was published into memory the machine shares"
)
# The same gate, the other kind of thing. `memory.index_extra` entries are pointers in
# `stayfixed.toml`, not notes, and they used to be appended to the same list the notes above are
# named from — so one sentence called a note name and a document path both notes.
_EXTRA_NOT_PUBLISHED = (
    "{names} took no pointer in {index}: `memory.index_extra` lives in this repository's "
    "stayfixed.toml, while this run's destination reaches outside it"
)


def _holds_repository_data(store: Store, config: Config) -> bool:
    """Whether the notes or a committed index are repository data, which the bundles withhold
    too, rather than only the directory the harness link exposes.

    `trust.is_repository_data` answers about the store's *notes*, through `inside_project`,
    which in overlay mode is False by design — every group resolves out into the overlay —
    while `store.path` is a real directory inside the repository, so a committed `MEMORY.md`
    there is repository data that answer cannot see. So the index is asked about by file,
    through its own `in_repository`, beside the notes.
    """
    index = index_source(store, config)
    return trust.is_repository_data(store) or (index is not None and in_repository(store, index))


def _gate(store: Store, config: Config, trusted: bool) -> str | None:
    """Whether the trust gate is what a person should be told about, after a command ran;
    `trusted` is the caller's own answer to `harness_link_needed`, asked once per command.

    Deliberately not wired into `session-context`: that command's `Result.summary` *is* the
    text the `SessionStart` entry emits, so a diagnostic there would be injected into the model
    rather than read by anyone. Nor into the handler, which stays `Policy.OPEN` and quiet. The
    commands a person runs by hand are where this belongs.
    """
    if trusted:
        return None
    return _UNTRUSTED if _holds_repository_data(store, config) else _LINK_WAITS


def _with(summary: str, note: str | None) -> str:
    return summary if note is None else f"{summary}; {note}"


def _printed(names: list[str]) -> str:
    """Names the store or `stayfixed.toml` supplied, joined for a summary line. Each is a file
    name or a `name:` a repository can commit, escape sequences included, so each goes through
    `printable`, and the list through `findings.listed`'s one cap, since a store can hold notes
    by the hundred: the line says how many it left off, and `--json` carries every name,
    whole."""
    return listed([printable(name) for name in names])


def _harvest(reconciled: Reconciliation, store: Store) -> str | None:
    """What `index._harvestable` declined to persist, named where a person will read it."""
    if not reconciled.refused_harvest:
        return None
    names = _printed(reconciled.refused_harvest)
    return _NOT_HARVESTED.format(names=names, index=store.path / INDEX_NAME)


def _publish(reconciled: Reconciliation, store: Store) -> str | None:
    """What `index._publishable` declined to write, named where a person will read it."""
    index = store.path / INDEX_NAME
    said = []
    if reconciled.refused_publish:
        said.append(_NOT_PUBLISHED.format(names=_printed(reconciled.refused_publish), index=index))
    if reconciled.refused_extra:
        said.append(
            _EXTRA_NOT_PUBLISHED.format(names=_printed(reconciled.refused_extra), index=index)
        )
    return "; ".join(said) or None


# A note the store holds and cannot parse is the one failure this store cannot recover from by
# itself: `walk` quarantines it so one bad file does not cost the whole store, and from there
# it is invisible to routing, to the standing rules and to volatile injection. It reached
# `Result.data` and nothing a person reads.
_UNREADABLE_NOTES = (
    "{count} file(s) in the store cannot be read as a note, so they reach neither the index "
    "nor any injection bundle: {paths}"
)


def _findings(report: IndexCheck, config: Config) -> list[str]:
    """Everything `memory index` must both say out loud and exit non-zero for.

    One list, read by the summary and by the exit code, because the two disagreed: the summary
    branched on `drifted` alone while the exit code was `drifted or over_budget`, so a run
    printed "index is current: N words, M lines" and exited 1 in the same breath. `over_caps` —
    the two limits at which the harness truncates `MEMORY.md` — was computed by `check_index`
    and then dropped entirely, absent from the data, the summary and the exit code alike.

    Drift is deliberately not here. It is the one finding whose meaning differs between the two
    callers: `--check` reports it, and the write path has just removed it.
    """
    found: list[str] = []
    if report.over_budget:
        budget = config.budgets.effective("memory_index_words")
        found.append(f"the index is {report.words} words, over its {budget}-word budget")
    if report.over_caps:
        found.append(
            f"the index is past the harness caps it is truncated at "
            f"({', '.join(report.over_caps)}): {report.lines} lines, {report.bytes_} bytes"
        )
    if report.unreadable:
        found.append(
            _UNREADABLE_NOTES.format(
                count=len(report.unreadable),
                paths=_printed(report.unreadable),
            )
        )
    return found


def run_index(args: argparse.Namespace) -> Result:
    store, config = _store(args)
    # Taken before anything is written, so it records the bytes the owner actually approved.
    before = trust.snapshot(store, config)
    reconciled = reconcile(store, config, write=not args.check)
    report = check_index(store, config, reconciled)
    findings = _findings(report, config)
    if args.check:
        if report.drifted:
            findings.insert(0, "the index is out of date; run `stayfixed memory index`")
        summary = (
            "; ".join(findings)
            if findings
            else f"index is current: {report.words} words, {report.lines} lines"
        )
        summary = _with(_with(summary, _harvest(reconciled, store)), _publish(reconciled, store))
        trusted = harness_link_needed(store, config)
        return Result(
            _with(summary, _gate(store, config, trusted)),
            {
                "drifted": report.drifted,
                "words": report.words,
                "lines": report.lines,
                "bytes": report.bytes_,
                "over_budget": report.over_budget,
                "over_caps": report.over_caps,
                "provisional": report.provisional,
                "refused_harvest": reconciled.refused_harvest,
                "refused_publish": reconciled.refused_publish,
                "refused_extra": reconciled.refused_extra,
                "unreadable": report.unreadable,
                "trusted": trusted,
            },
            # The same list the summary is built from, so the two can no longer disagree.
            exit_code=1 if findings else 0,
        )
    text = render_index(reconciled, config, store)
    path = write_index(store, config, text)
    carried = trust.refresh_if_trusted(store, config, before, [*reconciled.written, path])
    # Asked after the write and its refresh, which is the state the next session meets.
    trusted = harness_link_needed(store, config)
    note = _DROPPED if before.trusted and not carried else _gate(store, config, trusted)
    # Exit 0: the write succeeded, and `--check` is the mode that fails a build. The findings
    # are still said, because a person running this by hand is who can act on them.
    wrote = "; ".join(
        [f"wrote {path} ({report.words} words, {len(reconciled.notes)} notes)", *findings]
    )
    wrote = _with(_with(wrote, _harvest(reconciled, store)), _publish(reconciled, store))
    return Result(
        _with(wrote, note),
        {
            "path": str(path),
            "words": report.words,
            "lines": report.lines,
            "harvested": reconciled.harvested,
            "provisional": reconciled.provisional,
            "refused_harvest": reconciled.refused_harvest,
            "refused_publish": reconciled.refused_publish,
            "refused_extra": reconciled.refused_extra,
            "unreadable": report.unreadable,
            "over_budget": report.over_budget,
            "over_caps": report.over_caps,
            "trusted": trusted,
        },
    )


def run_session_context(args: argparse.Namespace) -> Result:
    try:
        bundle = Bundle(args.bundle)
    except ValueError as exc:
        known = ", ".join(b.value for b in Bundle)
        raise Refusal(f"unknown bundle {args.bundle!r}; known: {known}") from exc
    store, config = _store(args)
    text = render(bundle, store, config, part=args.part)
    return Result(text if text is not None else "")


def run_trust(args: argparse.Namespace) -> Result:
    store, config = _store(args)
    before = trust.state(store, config)
    after = trust.record(store, config)
    return Result(
        f"recorded the store hash for {store.path}",
        {"was_trusted": before.trusted, "trusted": after.trusted, "digest": after.current},
    )


def run_inventory(args: argparse.Namespace) -> Result:
    store, config = _store(args)
    reconciled = reconcile(store, config, write=False)
    entries = inventory(reconciled, config)
    counts = totals(entries)
    return Result(
        f"{counts['notes']} notes, {counts['words']} words, "
        f"{counts['provisional']} provisional, {counts['stale']} stale",
        {"entries": [entry.as_dict() for entry in entries], **counts},
    )


def run_doctor_bundles(args: argparse.Namespace) -> Result:
    """What `doctor` reads: whether each bundle fits the slots `hooks.json` declares."""
    store, config = _store(args)
    report = {
        bundle.value: {
            "parts": (found := fit(bundle, store, config)).parts,
            "slots": found.slots,
            "overflow": found.overflow,
            "oversized": found.oversized,
        }
        for bundle in Bundle
    }
    bad = [name for name, row in report.items() if row["overflow"] or row["oversized"]]
    summary = "every bundle fits its slots" if not bad else f"does not fit: {', '.join(bad)}"
    # A bundle that fits because it is empty is not a bundle that fits. `doctor` reads this.
    trusted = harness_link_needed(store, config)
    return Result(
        _with(summary, _gate(store, config, trusted)),
        {"bundles": report, "trusted": trusted},
        exit_code=1 if bad else 0,
    )


# The refusal carries the resolver's reasons rather than naming a command that would report
# them, because no command does: `run_index` builds its findings from `_findings` and drift and
# reads `store.unavailable` nowhere, in either `--json` object or on the summary. The one case a
# resolver reason does surface elsewhere is total failure — `resolve` returns `None` and
# `_no_store` raises — and that never reaches here, so a pointer would have been false in
# precisely and only the case that produces it: partial group resolution. `ledger/index.py` says
# at length why a refusal pointing away from the fix is worth rewriting a guard to avoid.
#
# The reasons are built out of `memory.groups` entries and name paths, so they are
# repository-authored text and reach a reader the way `_no_store`'s reason does: inside
# `trust.wrap`, with the region markers that say the text is data. So the line above the region
# counts and names no group: escaping bounds a name's bytes, not its meaning, and a group named as
# a sentence would otherwise reach an agent as prose outside the markers.
_UNAVAILABLE_GROUPS = (
    "{count} configured group(s) could not be resolved, so the walk read a subset and "
    "no answer from it means anything; the reasons below are repository-authored text, shown as "
    "data"
)


def _unavailable(unavailable: dict[str, str]) -> Refusal:
    # Each name through `quoted`: `memory.groups` is repository-written and bounded by no
    # grammar, and `trust.wrap` delimits text for the model without escaping a byte for the
    # terminal. The store's own reasons quote the group the same way.
    #
    # Not capped, unlike the resolver's one-line reason: this is the data region, one reason per
    # line, and the line above it counts them. What bounds it on the path a model reads is the
    # harness, which keeps at most `[native_caps] hook_output_chars` of a hook's output.
    reasons = "\n".join(f"{quoted(group)}: {unavailable[group]}" for group in sorted(unavailable))
    head = _UNAVAILABLE_GROUPS.format(count=len(unavailable))
    return Refusal(f"{head}\n{trust.wrap(reasons, trust.new_nonce())}")


def run_refs(args: argparse.Namespace) -> Result:
    from dataclasses import asdict

    from stayfixed.memory.refs import check_refs

    store, config = _store(args)
    report = check_refs(Path(args.root).resolve(), config, store)
    if report.unavailable:
        raise _unavailable(report.unavailable)
    data = {
        "findings": [asdict(f) for f in report.findings],
        "unreadable": [str(path.relative_to(store.path)) for path, _ in report.unreadable],
        "notices": [asdict(n) for n in report.notices],
    }
    # The link graph is advice: counted on the line and listed in `--json`, never in the exit
    # code, because the store is shared by every session on the machine and a sibling's
    # half-finished sweep is not this tree's fault to fail on.
    advice = (
        [f"{len(report.notices)} advisory link-graph notice(s), which do not gate"]
        if report.notices
        else []
    )
    parts: list[str] = []
    if report.findings:
        parts.append(f"{len(report.findings)} stale reference(s): {labels(report.findings)}")
    if report.unreadable:
        parts.append(f"{len(report.unreadable)} note(s) could not be parsed and were not read")
    if not parts:
        return Result("; ".join(["every backticked path in the store resolves", *advice]), data)
    return Result("; ".join([*parts, *advice]), data, exit_code=1)


def register(groups: SubParsers) -> None:
    group = groups.add_parser("memory", help="the working-memory store")
    sub = group.add_subparsers(dest="command", metavar="<command>")

    index = common_flags(
        sub.add_parser("index", help="render MEMORY.md from the notes"), store=True
    )
    index.add_argument("--check", action="store_true", help=CHECK_HELP)
    index.set_defaults(func=run_index)

    context = common_flags(
        sub.add_parser("session-context", help="render one injection bundle"), store=True
    )
    context.add_argument("--bundle", required=True, help=", ".join(b.value for b in Bundle))
    context.add_argument("--part", type=int, default=1, help="which numbered slot to render")
    context.set_defaults(func=run_session_context)

    trusted = common_flags(
        sub.add_parser("trust", help="trust notes committed to this repository"), store=True
    )
    trusted.add_argument(
        "--in-repo-memory",
        action="store_true",
        required=True,
        # Required and never read by `run_trust` — that is not a missing guard, it is the whole
        # point. This is an explicit-confirmation gesture, not a switch between two behaviours:
        # its presence is what stops `memory trust` from being a bare, trivially scripted
        # command. It is not a safety check either, so there is nothing here to branch on: trust
        # is only ever *consulted* for content that lives in the repository — the notes, when
        # `inside_project(store)`, and `MEMORY.md` whenever it resolves inside the repository,
        # which it does in overlay mode too, since `store.path` is a real directory there. For
        # a store holding neither, `trust.may_inject` short-circuits to `True`, so recording a
        # hash for it is inert rather than dangerous.
        help="the only kind of store trust applies to",
    )
    trusted.set_defaults(func=run_trust)

    listing = common_flags(
        sub.add_parser("inventory", help="what a memory sweep reads"), store=True
    )
    listing.set_defaults(func=run_inventory)

    fitting = common_flags(
        sub.add_parser("fit", help="whether each bundle fits its hook slots"), store=True
    )
    fitting.set_defaults(func=run_doctor_bundles)

    refs = common_flags(
        sub.add_parser(
            "refs",
            help="backticked paths in notes that no longer resolve, and the link graph as advice",
        ),
        store=True,
    )
    refs.set_defaults(func=run_refs)
