"""The approve path every spelling of an approval runs, apart from the command line that asks it.

`approve_kind` is what `stayfixed trust approve` and the `memory trust` alias both run: the terminal
check first, before anything a kind describes is read, then every subject of the kind recorded at
its digest now, in one write of the record. `kind_context` reads the checkout, the machine file and
the kinds' own flags off a parsed command line, so the old spelling cannot read its flags another
way than the new one. Here and not in `commands`, so a consumer of the record (`trust.api`, which
the hook path imports through `memory`) loads no command module and no CLI frame.
"""

from __future__ import annotations

import argparse
import shlex
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path

from stayfixed.errors import Refusal
from stayfixed.printed import printable
from stayfixed.result import Result
from stayfixed.trust import kinds as discovered
from stayfixed.trust import record
from stayfixed.trust.kinds import ApprovalKind, KindContext

# How every sentence that names an approval command tells its reader to have it run, here and in
# the areas that name one (`memory`, `attach`): any of them may be read by an agent's shell tool or
# reach the model, so each speaks of the person at the machine and tells an agent to stop, in these
# words, rather than telling its reader to run the command "in a terminal", which an agent able to
# open a pseudo-terminal reads as an instruction. `command` is the exact command.
PERSON_RUNS = (
    "ask the person at this machine to run `{command}` in their own terminal — an agent must not "
    "run it for them"
)
# The refusal of an approval asked with no terminal on standard input. `command` is the exact
# command for a person to run, built by `command_for` from the flags as they were given. Its likely
# reader is an agent's shell tool, so it speaks of the person rather than to its reader, tells an
# agent to stop, and says nothing of how a terminal could be had: what the check does not
# guarantee is stated in `kinds`' docstring, `docs/cli.md` and `SECURITY.md`, not at the moment an
# agent decides what to do next.
NOT_A_TERMINAL = (
    "an approval is a person's decision, and standard input is not a terminal, so nothing was "
    "approved; " + PERSON_RUNS
)
# A kind no area contributes. The name typed is not repeated: it is whatever was typed.
UNKNOWN_KIND = "there is no approval kind of that name; the kinds are: {known}"


def approve_kind(name: str, context: KindContext, given: Sequence[str]) -> Result:
    """The approve path both spellings run: the terminal check, then every subject of the kind
    `name` describes for this checkout, recorded at its digest now in one write of the record.

    `given` is the flags as they were typed after the kind, for the command `NOT_A_TERMINAL`
    names."""
    kind = known_kind(name)
    # Through the module, so the one seam a test replaces is the one asked here.
    if not discovered.interactive():
        raise Refusal(NOT_A_TERMINAL.format(command=command_for(name, given)))
    subjects = kind.describe(context)
    # One write for every subject (`record.approve_all`): a failure part-way leaves the record as it
    # was, never a kind half approved.
    was = record.approve_all(
        context.machine,
        name,
        {subject.key: subject.digest for subject in subjects},
        now=datetime.now(UTC),
    )
    lines = [
        f"approved {name} {printable(subject.label)} at digest {subject.digest}"
        for subject in subjects
    ]
    approved = [
        {
            "subject": subject.key,
            "label": subject.label,
            "digest": subject.digest,
            "was": was[subject.key],
        }
        for subject in subjects
    ]
    summary = "\n".join(lines) or f"{name} has nothing to approve in this checkout"
    return Result(summary, {"kind": name, "approved": approved})


def known_kind(name: str) -> ApprovalKind:
    """The kind of approval named `name`, or `UNKNOWN_KIND` naming the kinds there are."""
    found = discovered.kinds()
    if name not in found:
        raise Refusal(UNKNOWN_KIND.format(known=", ".join(sorted(found))))
    return found[name]


def kind_flags() -> dict[str, str]:
    """Every flag a kind takes and what `--help` says of it, once each, in the order the kinds name
    them; where two kinds take one flag, the first kind's words."""
    flags: dict[str, str] = {}
    for kind in discovered.kinds().values():
        for flag, help_text in kind.flags.items():
            flags.setdefault(flag, help_text)
    return flags


def _dest(flag: str) -> str:
    return flag.removeprefix("--").replace("-", "_")


def kind_context(
    args: argparse.Namespace, *, noting: bool = False
) -> tuple[KindContext, list[str]]:
    """The checkout, the machine file and the kind flags given, and the flags as typed: what
    `approve_kind` takes, read off any parsed command line that carries `--root`, `--machine`
    and the kinds' flags (`memory trust`'s among them). `noting` is `KindContext.noting`."""
    options: Mapping[str, str] = {
        flag: value
        for flag in kind_flags()
        if (value := getattr(args, _dest(flag), None)) is not None
    }
    given: list[str] = []
    if args.root != ".":
        given += ["--root", args.root]
    if args.machine is not None:
        given += ["--machine", args.machine]
    for flag, value in options.items():
        given += [flag, value]
    machine = Path(args.machine) if args.machine else None
    return KindContext(Path(args.root).resolve(), machine, options, noting=noting), given


def command_for(name: str, given: Sequence[str]) -> str:
    """`stayfixed trust approve <name>` with the flags as given, each value quoted for a shell.

    A value holding a character that is not printable — a line break, an escape — would drive the
    terminal that shows the refusal, so its flag is left out and the command still names the kind.
    """
    words = ["stayfixed", "trust", "approve", name]
    for flag, value in zip(given[::2], given[1::2], strict=True):
        if value.isprintable():
            words += [flag, value]
    return shlex.join(words)
