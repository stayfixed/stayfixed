"""`stayfixed trust list | approve | revoke`: every approval on this machine, one command family.

`approve` is asked of a person: it refuses with `NOT_A_TERMINAL` when standard input is not a
terminal (`kinds.interactive`), before it reads anything a kind describes, and nothing takes
`--yes`. That check slows an agent's bare call and guarantees nothing (`kinds`' docstring says
why). `revoke` needs no terminal: withdrawing an approval is the direction that fails safe.
`list` reads the record and writes nothing.
"""

from __future__ import annotations

import argparse
import shlex
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from stayfixed.areas import SubParsers
from stayfixed.command import STORE_HELP, common_flags
from stayfixed.config.machine import homes_agree, passwd_home
from stayfixed.errors import Failure, Refusal
from stayfixed.printed import clipped, printable
from stayfixed.result import Result
from stayfixed.trust import kinds as discovered
from stayfixed.trust import record
from stayfixed.trust.kinds import ApprovalKind, KindContext

# The refusal of an approval asked with no terminal on standard input. `command` is the exact
# command for a person to run, built by `_command` from the flags as they were given. Its likely
# reader is an agent's shell tool, so it speaks of the person rather than to its reader, tells an
# agent to stop, and says nothing of how a terminal could be had: what the check does not
# guarantee is stated in `kinds`' docstring, `docs/cli.md` and `SECURITY.md`, not at the moment an
# agent decides what to do next.
NOT_A_TERMINAL = (
    "an approval is a person's decision, and standard input is not a terminal, so nothing was "
    "approved; ask the person at this machine to run `{command}` in their own terminal — an "
    "agent must not run it for them"
)
# A kind no area contributes. The name typed is not repeated: it is whatever was typed.
UNKNOWN_KIND = "there is no approval kind of that name; the kinds are: {known}"
# A revoke that matched nothing: exit 1, and what the kind has recorded.
NOTHING_TO_REVOKE = "nothing recorded for {kind} matches, so nothing was revoked"
# What a flag a kind takes says in `--help`: the shared sentence where the frame has one.
FLAG_HELP = {"--store": STORE_HELP}
OTHER_FLAG_HELP = "passed to the approval kind that takes it"
# Said after an approval where `HOME` is not the database's home, because a person who looks under
# `HOME` for the record finds an older one or none (`config.machine`'s docstring says why).
ELSEWHERE = (
    "in {path}: under the home the password database records for this user, not under HOME, "
    "because that is where a hook reads it"
)


def approve_kind(name: str, context: KindContext, given: Sequence[str]) -> Result:
    """The approve path both spellings run: the terminal check, then every subject of the kind
    `name` describes for this checkout, each recorded at its digest now.

    `given` is the flags as they were typed after the kind, for the command `NOT_A_TERMINAL`
    names."""
    kind = _kind(name)
    # Through the module, so the one seam a test replaces is the one asked here.
    if not discovered.interactive():
        raise Refusal(NOT_A_TERMINAL.format(command=_command(name, given)))
    subjects = kind.describe(context)
    now = datetime.now(UTC)
    lines: list[str] = []
    approved: list[dict[str, str]] = []
    for subject in subjects:
        was = record.state(context.machine, name, subject.key, subject.digest)
        record.approve(context.machine, name, subject.key, subject.digest, now=now)
        lines.append(f"approved {name} {printable(subject.label)} at digest {subject.digest}")
        approved.append(
            {"subject": subject.key, "label": subject.label, "digest": subject.digest, "was": was}
        )
    written = record.record_path(context.machine)
    summary = "\n".join(lines) or f"{name} has nothing to approve in this checkout"
    if approved and context.machine is None and written is not None and not homes_agree():
        summary = f"{summary}\n{ELSEWHERE.format(path=written)}"
    return Result(summary, {"kind": name, "approved": approved})


def run_approve(args: argparse.Namespace) -> Result:
    context, given = kind_context(args)
    return approve_kind(args.kind, context, given)


def run_list(args: argparse.Namespace) -> Result:
    context, _ = kind_context(args)
    if args.all:
        return _everything(context.machine)
    lines: list[str] = []
    rows: list[dict[str, str]] = []
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
            state = record.state(context.machine, name, subject.key, subject.digest)
            line = f"{name} {printable(subject.label)}: {state}"
            if state is not record.State.APPROVED:
                command = _command(name, _given(args, kind))
                line = f"{line} — run `{command}` in a terminal to approve it"
            lines.append(line)
            rows.append({"kind": name, "subject": subject.key, "state": str(state)})
    return Result("\n".join(lines), {"subjects": rows})


def run_revoke(args: argparse.Namespace) -> Result:
    context, _ = kind_context(args)
    kind = _kind(args.kind)
    if args.subject is not None:
        keys = [args.subject]
    else:
        keys = [subject.key for subject in kind.describe(context)]
    revoked = [key for key in keys if record.revoke(context.machine, kind.name, key)]
    if revoked:
        return Result(
            f"revoked {len(revoked)} {kind.name} approval(s)",
            {"kind": kind.name, "revoked": revoked},
        )
    recorded = sorted(
        subject for (name, subject) in record.recorded(context.machine) if name == kind.name
    )
    shown = ", ".join(_shown(subject) for subject in recorded) or "none"
    return Result(
        f"{NOTHING_TO_REVOKE.format(kind=kind.name)}; recorded: {shown}",
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
    """A recorded subject as a line prints it: under the home the password database records, as
    `~/` and the rest; anywhere else, whole. Either way through `printed.clipped`, escaped and
    bounded: a subject is the absolute path of something in a checkout, chosen by whoever named
    its directories, and `printable` withheld every one of them, since the path grammar admits no
    leading `/`, so the listing a person reads to see what they approved named nothing."""
    home = passwd_home()
    if home is not None:
        try:
            inside = Path(subject).relative_to(home.resolve())
        except ValueError:
            pass
        else:
            return "~" if inside == Path() else f"~/{clipped(inside.as_posix())}"
    return clipped(subject)


def _kind(name: str) -> ApprovalKind:
    found = discovered.kinds()
    if name not in found:
        raise Refusal(UNKNOWN_KIND.format(known=", ".join(sorted(found))))
    return found[name]


def _flags() -> list[str]:
    """Every flag a kind takes, once each, in the order the kinds name them."""
    return list(dict.fromkeys(flag for kind in discovered.kinds().values() for flag in kind.flags))


def _dest(flag: str) -> str:
    return flag.removeprefix("--").replace("-", "_")


def kind_context(args: argparse.Namespace) -> tuple[KindContext, list[str]]:
    """The checkout, the machine file and the kind flags given, and the flags as typed: what
    `approve_kind` takes, read off any parsed command line that carries `--root`, `--machine`
    and the kinds' flags (`memory trust`'s among them)."""
    options = {
        flag: value for flag in _flags() if (value := getattr(args, _dest(flag), None)) is not None
    }
    given: list[str] = []
    if args.root != ".":
        given += ["--root", args.root]
    if args.machine is not None:
        given += ["--machine", args.machine]
    for flag, value in options.items():
        given += [flag, value]
    machine = Path(args.machine) if args.machine else None
    return KindContext(Path(args.root).resolve(), machine, options), given


def _given(args: argparse.Namespace, kind: ApprovalKind) -> list[str]:
    """The flags as given, keeping only the kind's own beside `--root` and `--machine`."""
    _, given = kind_context(args)
    kept: list[str] = []
    for flag, value in zip(given[::2], given[1::2], strict=True):
        if flag in ("--root", "--machine") or flag in kind.flags:
            kept += [flag, value]
    return kept


def _command(name: str, given: Sequence[str]) -> str:
    """`stayfixed trust approve <name>` with the flags as given, each value quoted for a shell.

    A value holding a character that is not printable — a line break, an escape — would drive the
    terminal that shows the refusal, so its flag is left out and the command still names the kind.
    """
    words = ["stayfixed", "trust", "approve", name]
    for flag, value in zip(given[::2], given[1::2], strict=True):
        if value.isprintable():
            words += [flag, value]
    return shlex.join(words)


def register(groups: SubParsers) -> None:
    group = groups.add_parser("trust", help="every approval on this machine")
    sub = group.add_subparsers(dest="command", metavar="<command>")
    flags = _flags()

    listing = common_flags(sub.add_parser("list", help="each kind's state in this checkout"))
    listing.add_argument("--all", action="store_true", help="every approval on this machine")
    for flag in flags:
        listing.add_argument(flag, default=None, help=FLAG_HELP.get(flag, OTHER_FLAG_HELP))
    listing.set_defaults(func=run_list)

    approving = common_flags(sub.add_parser("approve", help="approve a kind, at a terminal"))
    approving.add_argument("kind", help="the kind to approve, as `trust list` names it")
    for flag in flags:
        approving.add_argument(flag, default=None, help=FLAG_HELP.get(flag, OTHER_FLAG_HELP))
    approving.set_defaults(func=run_approve)

    revoking = common_flags(sub.add_parser("revoke", help="withdraw a kind's approval"))
    revoking.add_argument("kind", help="the kind to revoke, as `trust list` names it")
    revoking.add_argument("--subject", default=None, help="the recorded subject to revoke")
    for flag in flags:
        revoking.add_argument(flag, default=None, help=FLAG_HELP.get(flag, OTHER_FLAG_HELP))
    revoking.set_defaults(func=run_revoke)
