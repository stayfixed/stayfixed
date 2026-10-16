"""The approval kind this area contributes to `stayfixed trust` (`trust.kinds`): `memory`, a store
of notes committed to the repository, found as `memory trust` always found it and hashed by
`trust.store_digest`.

Every import sits inside `_describe`: `stayfixed trust` reads `KINDS` when it builds its parser, and
a store is resolved only when a command asks about one.
"""

from __future__ import annotations

from stayfixed.trust.api import ApprovalKind, KindContext, Subject

# What a person reads for a store outside the path grammar, where `--json` carries its key.
UNNAMED_STORE = "the memory store"


def _describe(context: KindContext) -> tuple[Subject, ...]:
    """This checkout's one store: keyed by its resolved path, labelled by its path in the
    repository, at its digest now."""
    from stayfixed.config.loader import load
    from stayfixed.memory import trust
    from stayfixed.memory.commands import store_at

    config = load(context.root, machine=context.machine)
    store = store_at(context.root, config, context.machine, context.options.get("--store"))
    try:
        label = store.path.relative_to(context.root).as_posix()
    except ValueError:
        label = UNNAMED_STORE
    return (Subject(trust.store_key(store), label, trust.store_digest(store, config)),)


KINDS = (ApprovalKind("memory", _describe, flags=("--store",)),)
