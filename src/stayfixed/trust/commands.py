"""`stayfixed trust list | approve | revoke`: every approval on this machine, one command family.

`approve` is asked of a person: it refuses with `NOT_A_TERMINAL` when standard input is not a
terminal (`kinds.interactive`), before it reads anything a kind describes, and nothing takes
`--yes`. That check slows an agent's bare call and guarantees nothing (`kinds`' docstring says
why). `revoke` needs no terminal: withdrawing an approval is the direction that fails safe.
`list` reads the record and writes nothing.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from stayfixed.areas import SubParsers
from stayfixed.command import common_flags
from stayfixed.config.machine import owner_home
from stayfixed.errors import Failure, Refusal
from stayfixed.printed import clipped, printable
from stayfixed.result import Result
from stayfixed.trust import kinds as discovered
from stayfixed.trust import record
from stayfixed.trust.approving import (
    PERSON_RUNS,
    approve_kind,
    command_for,
    kind_context,
    kind_flags,
    known_kind,
)
from stayfixed.trust.kinds import ApprovalKind

# A revoke that matched nothing: exit 1, and what the kind has recorded.
NOTHING_TO_REVOKE = "nothing recorded for {kind} matches, so nothing was revoked"
# A revoke whose kind could not describe this checkout's subjects: exit 1, the kind's reason, and
# the spelling that revokes a recorded subject by its key, which needs no description. The reason
# is the kind's refusal, a sentence built for the frame to print, any name the repository chose in
# it already bounded, as `trust list` prints it.
UNDESCRIBED = (
    "{kind} cannot be described in this checkout ({reason}), so nothing was revoked; to revoke a "
    "recorded approval by its key, run `stayfixed trust revoke {kind} --subject KEY` with a "
    "subject `stayfixed trust list --all --json` prints"
)


def run_approve(args: argparse.Namespace) -> Result:
    context, given = kind_context(args)
    return approve_kind(args.kind, context, given)


def run_list(args: argparse.Namespace) -> Result:
    # Described as a session reads the checkout (`KindContext.noting`): what is approved is what a
    # session would use, and a file only a session reads past cannot hide a live approval.
    context, _ = kind_context(args, noting=True)
    if args.all:
        return _everything(context.machine)
    lines: list[str] = []
    rows: list[dict[str, str]] = []
    # Read once, when the first subject is asked of, and not once per subject: a kind with no
    # subject to describe asks nothing of the record.
    approvals: dict[tuple[str, str], record.Approval] | None = None
    for name, kind in discovered.kinds().items():
        try:
            subjects = kind.describe(context)
        except (Failure, Refusal) as refused:
            # Said here rather than pointed at: `trust approve` refuses with no terminal before it
            # asks the kind anything, so from where an agent runs this it would never say why. The
            # kind's refusal is a sentence built for the frame to print, any name the repository
            # chose in it already bounded, so it prints here as it would there.
            lines.append(f"{name}: nothing to approve in this checkout: {refused}")
            rows.append({"kind": name, "state": "undescribed", "reason": str(refused)})
            continue
        for subject in subjects:
            if approvals is None:
                approvals = record.recorded(context.machine)
            state = record.state_in(approvals, name, subject.key, subject.digest)
            line = f"{name} {printable(subject.label)}: {state}"
            if state is not record.State.APPROVED:
                command = command_for(name, _given(args, kind))
                line = f"{line} — to approve it, {PERSON_RUNS.format(command=command)}"
            lines.append(line)
            rows.append({"kind": name, "subject": subject.key, "state": str(state)})
    return Result("\n".join(lines), {"subjects": rows})


def run_revoke(args: argparse.Namespace) -> Result:
    # Described as a session reads the checkout (`KindContext.noting`), as `trust list` describes
    # it: the fail-safe direction withdraws what a session would use, whatever a command would
    # refuse in the file.
    context, _ = kind_context(args, noting=True)
    kind = known_kind(args.kind)
    if args.subject is not None:
        keys = [args.subject]
    else:
        try:
            keys = [subject.key for subject in kind.describe(context)]
        except (Failure, Refusal) as refused:
            return _not_revoked(
                kind, context.machine, UNDESCRIBED.format(kind=kind.name, reason=refused)
            )
    revoked = record.revoke_all(context.machine, kind.name, keys)
    if revoked:
        return Result(
            f"revoked {len(revoked)} {kind.name} approval(s)",
            {"kind": kind.name, "revoked": revoked},
        )
    return _not_revoked(kind, context.machine, NOTHING_TO_REVOKE.format(kind=kind.name))


def _not_revoked(kind: ApprovalKind, machine: Path | None, said: str) -> Result:
    """A revoke that withdrew nothing: `said`, what the kind has recorded, and exit 1."""
    recorded = sorted(subject for (name, subject) in record.recorded(machine) if name == kind.name)
    shown = ", ".join(_shown(subject) for subject in recorded) or "none"
    return Result(
        f"{said}; recorded: {shown}",
        {"kind": kind.name, "revoked": [], "recorded": recorded},
        exit_code=1,
    )


def _everything(machine: Path | None) -> Result:
    approvals = record.recorded(machine)
    lines = [
        f"{kind} {_shown(subject)}: approved {approval.approved_at or 'before 0.4.0'}"
        for (kind, subject), approval in sorted(approvals.items())
    ]
    rows = [
        {
            "kind": approval.kind,
            "subject": approval.subject,
            "digest": approval.digest,
            "approved_at": approval.approved_at,
        }
        for _, approval in sorted(approvals.items())
    ]
    return Result(
        "\n".join(lines) or "no approval is recorded on this machine", {"approvals": rows}
    )


def _shown(subject: str) -> str:
    """A recorded subject as a line prints it: under the owner's home, as
    `~/` and the rest; anywhere else, whole. Either way through `printed.clipped`, escaped and
    bounded: a subject is the absolute path of something in a checkout, chosen by whoever named
    its directories, and `printable` withheld every one of them, since the path grammar admits no
    leading `/`, so the listing a person reads to see what they approved named nothing."""
    home = owner_home()
    if home is not None:
        try:
            inside = Path(subject).relative_to(home.resolve())
        except ValueError:
            pass
        else:
            return "~" if inside == Path() else f"~/{clipped(inside.as_posix())}"
    return clipped(subject)


def _given(args: argparse.Namespace, kind: ApprovalKind) -> list[str]:
    """The flags as given, keeping only the kind's own beside `--root` and `--machine`."""
    _, given = kind_context(args)
    kept: list[str] = []
    for flag, value in zip(given[::2], given[1::2], strict=True):
        if flag in ("--root", "--machine") or flag in kind.flags:
            kept += [flag, value]
    return kept


def register(groups: SubParsers) -> None:
    group = groups.add_parser("trust", help="every approval on this machine")
    sub = group.add_subparsers(dest="command", metavar="<command>")
    # Each kind's flags with the words its kind gives them (`ApprovalKind.flags`), so a kind's new
    # flag edits that kind's `approvals.py` and nothing here.
    flags = kind_flags()

    listing = common_flags(sub.add_parser("list", help="each kind's state in this checkout"))
    listing.add_argument("--all", action="store_true", help="every approval on this machine")
    for flag, help_text in flags.items():
        listing.add_argument(flag, default=None, help=help_text)
    listing.set_defaults(func=run_list)

    approving = common_flags(sub.add_parser("approve", help="approve a kind, at a terminal"))
    approving.add_argument("kind", help="the kind to approve, as `trust list` names it")
    for flag, help_text in flags.items():
        approving.add_argument(flag, default=None, help=help_text)
    approving.set_defaults(func=run_approve)

    revoking = common_flags(sub.add_parser("revoke", help="withdraw a kind's approval"))
    revoking.add_argument("kind", help="the kind to revoke, as `trust list` names it")
    revoking.add_argument("--subject", default=None, help="the recorded subject to revoke")
    for flag, help_text in flags.items():
        revoking.add_argument(flag, default=None, help=help_text)
    revoking.set_defaults(func=run_revoke)
