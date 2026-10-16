"""The trust package's import surface: the machine's one record of approvals.

The `memory` area keeps its store approvals in the record under kind `memory`, and reads
`recorded`, `approve`, `record_path` and `UnreadableTrust`. `Approval` is what `recorded` and
`approve` return, which a consumer holding the value has to be able to declare. `state` and
`revoke`, with the `State` the first answers in, complete the record's answers: a consumer
handed half of it could approve and could not withdraw, or could read an approval and not tell
one that lapsed from one never given. `ApprovalKind`, `KindContext` and `Subject` are what an
area's `approvals.py` builds its `KINDS` from (`memory.approvals`), and `approve_kind` is the
approve path the `memory trust` alias runs, terminal check included.
"""

from __future__ import annotations

from stayfixed.trust.commands import approve_kind
from stayfixed.trust.kinds import ApprovalKind, KindContext, Subject
from stayfixed.trust.record import (
    Approval,
    State,
    UnreadableTrust,
    approve,
    record_path,
    recorded,
    revoke,
    state,
)

__all__ = [
    "Approval",
    "ApprovalKind",
    "KindContext",
    "State",
    "Subject",
    "UnreadableTrust",
    "approve",
    "approve_kind",
    "record_path",
    "recorded",
    "revoke",
    "state",
]
