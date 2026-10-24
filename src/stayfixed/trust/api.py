"""The trust package's import surface: the machine's one record of approvals.

The `memory` area keeps its store approvals in the record under kind `memory`, and reads `recorded`,
with the `Approval` it answers in, and `UnreadableTrust`, and `state` with the `State` it answers
in; `refresh` is how it carries an approval across a write stayfixed itself made without undoing a
revoke made before its final re-read of the record. A person approves and revokes through
`stayfixed trust`, whose commands are this package's own, so the record's writers are not
published: a consumer that needs one grows this list in a commit that names it.

`ApprovalKind`, `KindContext` and `Subject` are what an area's `approvals.py` builds its `KINDS`
from (`memory.approvals`), and `approve_kind` is the approve path the `memory trust` alias runs,
on what `kind_context` reads off its command line, so the old spelling
cannot read its flags another way than the new one; both come from `approving`, not from the command
module, so importing the record loads no CLI. `PERSON_RUNS` is the sentence `memory` and `attach`
tell their reader in to have an approval made: the person at the machine runs it, and an agent does
not, in the words `trust list` uses.

`setup --approval-boundary` prints what keeps an agent's shell out of the record, and writes none
of it (`boundary`): `record_deny_rules` over the directory `record_path` names, `SANDBOX_ON` for
the user settings, and `ENFORCING_SETTINGS` for `managed_named`'s file. `sandbox_refused` is how
`setup` tells a write an agent's sandbox refused, `SandboxedWrite` is the record's own refusal of
one, which `memory` catches. `SANDBOX_REFUSED` is the one sentence every writer gives such a write,
`setup`'s, `memory`'s and `attach`'s as the record's; `RUN_OUTSIDE` is the remedy `setup` gives in
it as the record does, and `ONLY_OUTSIDE` the one `memory` and `attach` give.
"""

from __future__ import annotations

from stayfixed.trust.approving import PERSON_RUNS, approve_kind, kind_context
from stayfixed.trust.boundary import (
    ENFORCING_SETTINGS,
    ONLY_OUTSIDE,
    RUN_OUTSIDE,
    SANDBOX_ON,
    SANDBOX_REFUSED,
    managed_named,
    record_deny_rules,
    sandbox_refused,
)
from stayfixed.trust.kinds import ApprovalKind, KindContext, Subject
from stayfixed.trust.record import (
    Approval,
    SandboxedWrite,
    State,
    UnreadableTrust,
    record_path,
    recorded,
    refresh,
    state,
)

__all__ = [
    "ENFORCING_SETTINGS",
    "ONLY_OUTSIDE",
    "PERSON_RUNS",
    "RUN_OUTSIDE",
    "SANDBOX_ON",
    "SANDBOX_REFUSED",
    "Approval",
    "ApprovalKind",
    "KindContext",
    "SandboxedWrite",
    "State",
    "Subject",
    "UnreadableTrust",
    "approve_kind",
    "kind_context",
    "managed_named",
    "record_deny_rules",
    "record_path",
    "recorded",
    "refresh",
    "sandbox_refused",
    "state",
]
