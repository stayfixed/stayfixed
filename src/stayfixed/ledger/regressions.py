"""`stayfixed bugs regressions`: run each fixed entry's `regression` through `prove`.

A closed entry is `status: fixed`. A `rejected` one has no fix to regress, a `partial` one is still
open and a `void` one is a renumber's pointer: each may carry a `regression`, and none is run.

Each argv runs as `prove` runs a command, from the project root, under the caller's environment,
with `[gates] custom_timeout_seconds` as its bound, the bound a project already sets for its own
gates; and every receipt is judged as `prove` judges it, so an argv no runner adapter recognises is
`not proven` and nothing is started for it.

**A convenience, not a control.** The argv is read from the tree a pull request wrote, so a hostile
pull request can rewrite it as easily as it can rewrite the test it runs: the run catches an honest
regression and never a hostile edit. Who runs it is decided where every custom gate's command is,
by the base branch's `run` and by the person's yes before a clone's commands run.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING, TextIO

from stayfixed.ledger.entries import Entry, load_entries
from stayfixed.ledger.register import bug_register
from stayfixed.prove.api import INTERRUPTED, Receipt, prove

if TYPE_CHECKING:
    from stayfixed.config.schema import Config


def regressions(root: Path, config: Config, *, echo: TextIO) -> list[tuple[Entry, Receipt]]:
    """Every fixed entry that carries a `regression`, in identifier order, with the receipt of its
    run; the runner's standard output goes to `echo`. A run an interrupt ended (a Ctrl-C, or the
    SIGTERM a custom gate's bound sends) is the last: `prove` returns its receipt rather than
    raising, so going on would start the next runner after the signal."""
    ran: list[tuple[Entry, Receipt]] = []
    for entry in load_entries(root, bug_register(config)):
        argv = entry.lists["regression"]
        if entry.status != "fixed" or not argv:
            continue
        timeout = config.gates.custom_timeout_seconds
        receipt = prove(argv, cwd=root, environ=os.environ, timeout=timeout, echo=echo)
        ran.append((entry, receipt))
        if receipt.reason == INTERRUPTED:
            break
    return ran
