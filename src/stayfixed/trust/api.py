"""The trust package's import surface: the machine's one record of approvals.

The `memory` area keeps its store approvals in the record under kind `memory`, and reads `recorded`,
`approve`, `record_path` and `UnreadableTrust`; `refresh` is how it carries an approval across a
write stayfixed itself made without undoing a revoke made before its final re-read of the record.
`Approval` is what `recorded` and `approve` return, which a consumer holding the value has to be
able to declare. `state` and `revoke`, with the `State` the first answers in, complete the record's
answers: a consumer handed half of it could approve and could not withdraw, or could read an
approval and not tell one that lapsed from one never given. `ApprovalKind`, `KindContext` and
`Subject` are what an area's `approvals.py` builds its `KINDS` from (`memory.approvals`), and
`approve_kind` is the approve path the `memory trust` alias runs, terminal check included, on what
`kind_context` reads off its command line, so the old spelling cannot read its flags another way
than the new one. `PERSON_RUNS` is the sentence `memory` and `attach` tell their reader in to have
an approval made: the person at the machine runs it, and an agent does not, in the words `trust
approve`'s own refusal uses.

The approval boundary's spellings (`boundary`) are read by two consumers that must not drift apart:
`setup`, which writes `deny_rule` over the record's directory and names `managed_settings` in what
it prints, and `doctor`'s `approval-boundary` row, which reads the settings layers through
`managed_settings`, `MANAGED_DROP_INS` and `CONFIG_DIR_VARIABLE`, judges the sandbox by `SANDBOX`,
`ENABLED` and `UNSANDBOXED_ALLOWED`, and looks for that same `deny_rule`.
"""

from __future__ import annotations

from stayfixed.trust.boundary import (
    CONFIG_DIR_VARIABLE,
    ENABLED,
    MANAGED_DROP_INS,
    SANDBOX,
    UNSANDBOXED_ALLOWED,
    deny_rule,
    managed_settings,
)
from stayfixed.trust.commands import PERSON_RUNS, approve_kind, kind_context
from stayfixed.trust.kinds import ApprovalKind, KindContext, Subject
from stayfixed.trust.record import (
    Approval,
    State,
    UnreadableTrust,
    approve,
    record_path,
    recorded,
    refresh,
    revoke,
    state,
)

__all__ = [
    "CONFIG_DIR_VARIABLE",
    "ENABLED",
    "MANAGED_DROP_INS",
    "PERSON_RUNS",
    "SANDBOX",
    "UNSANDBOXED_ALLOWED",
    "Approval",
    "ApprovalKind",
    "KindContext",
    "State",
    "Subject",
    "UnreadableTrust",
    "approve",
    "approve_kind",
    "deny_rule",
    "kind_context",
    "managed_settings",
    "record_path",
    "recorded",
    "refresh",
    "revoke",
    "state",
]
