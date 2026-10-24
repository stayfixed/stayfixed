"""The trust package's import surface: the machine's one record of approvals.

A person lists and revokes approvals through `stayfixed trust`, whose commands are this package's
own, so the record's readers and writers are not published: a consumer that needs one grows this
list in a commit that names it.

`setup --approval-boundary` prints what keeps an agent's shell out of the record, and writes none
of it (`boundary`): `record_deny_rules` over the directory `record_path` names, `SANDBOX_ON` for
the user settings, and `ENFORCING_SETTINGS` for `managed_named`'s file. `sandbox_refused` is how
`setup` tells a write an agent's sandbox refused; `SANDBOX_REFUSED` is the one sentence every
writer gives such a write, `setup`'s as the record's, and `RUN_OUTSIDE` the remedy it gives in it.
"""

from __future__ import annotations

from stayfixed.trust.boundary import (
    ENFORCING_SETTINGS,
    RUN_OUTSIDE,
    SANDBOX_ON,
    SANDBOX_REFUSED,
    managed_named,
    record_deny_rules,
    sandbox_refused,
)
from stayfixed.trust.record import record_path

__all__ = [
    "ENFORCING_SETTINGS",
    "RUN_OUTSIDE",
    "SANDBOX_ON",
    "SANDBOX_REFUSED",
    "managed_named",
    "record_deny_rules",
    "record_path",
    "sandbox_refused",
]
