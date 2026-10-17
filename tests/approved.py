"""A store approved in-process, for a case about what an approval opens, not how one is given.

`stayfixed trust approve memory` is asked of a person at a terminal and runs every subject through
one write of the record (`trust.approving`); these cases need only the record to hold a store's
digest now, so `record` writes exactly that and answers the store's trust state after it.
"""

from __future__ import annotations

from datetime import UTC, datetime

from stayfixed.config.schema import Config
from stayfixed.memory.store import Store
from stayfixed.memory.trust import MEMORY, TrustState, state, store_digest, store_key
from stayfixed.trust.record import approve_all


def record(store: Store, config: Config) -> TrustState:
    """Approve `store` at its digest now, as `trust approve memory` would, and its state after."""
    digest = store_digest(store, config)
    approve_all(store.machine, MEMORY, {store_key(store): digest}, now=datetime.now(UTC))
    return state(store, config)
