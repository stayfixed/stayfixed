"""`stayfixed trust list | revoke`: every approval recorded on this machine, one command family.

`list` reads the record and writes nothing. `revoke` withdraws one recorded approval, named by its
kind and subject as `list --json` prints them, and needs no terminal: withdrawing is the direction
that fails safe.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from stayfixed.areas import SubParsers
from stayfixed.command import common_flags
from stayfixed.config.machine import owner_home
from stayfixed.printed import clipped
from stayfixed.result import Result
from stayfixed.trust import record

# A revoke that matched nothing: exit 1, and what the kind has recorded.
NOTHING_TO_REVOKE = "nothing recorded for {kind} matches, so nothing was revoked"


def _machine(args: argparse.Namespace) -> Path | None:
    return Path(args.machine) if args.machine else None


def run_list(args: argparse.Namespace) -> Result:
    approvals = record.recorded(_machine(args))
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


def run_revoke(args: argparse.Namespace) -> Result:
    machine = _machine(args)
    # The kind is whatever was typed, so a line names it through `clipped`, as it does a subject.
    kind = clipped(args.kind)
    revoked = record.revoke_all(machine, args.kind, [_unshown(args.subject)])
    if revoked:
        return Result(
            f"revoked {len(revoked)} {kind} approval(s)",
            {"kind": args.kind, "revoked": revoked},
        )
    recorded = sorted(subject for (name, subject) in record.recorded(machine) if name == args.kind)
    shown = ", ".join(_shown(subject) for subject in recorded) or "none"
    return Result(
        f"{NOTHING_TO_REVOKE.format(kind=kind)}; recorded: {shown}",
        {"kind": args.kind, "revoked": [], "recorded": recorded},
        exit_code=1,
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


def _unshown(subject: str) -> str:
    """A subject as typed, read back from the `~/` form `_shown` prints a subject under the owner's
    home in, so the spelling `trust list` gives is one `revoke` takes."""
    home = owner_home()
    if home is None or (subject != "~" and not subject.startswith("~/")):
        return subject
    return str(home.resolve() / subject[2:])


def register(groups: SubParsers) -> None:
    group = groups.add_parser("trust", help="every approval on this machine")
    sub = group.add_subparsers(dest="command", metavar="<command>")

    listing = common_flags(sub.add_parser("list", help="every approval on this machine"))
    listing.set_defaults(func=run_list)

    revoking = common_flags(sub.add_parser("revoke", help="withdraw a recorded approval"))
    revoking.add_argument("kind", help="the kind of the approval, as `trust list` names it")
    revoking.add_argument(
        "--subject", required=True, help="the recorded subject, as `trust list` prints it"
    )
    revoking.set_defaults(func=run_revoke)
