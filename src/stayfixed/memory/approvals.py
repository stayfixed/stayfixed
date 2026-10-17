"""The approval kind this area contributes to `stayfixed trust` (`trust.kinds`): `memory`, a store
of notes committed to the repository, found as `memory trust` always found it and hashed by
`trust.store_digest`.

Every import of this area's own modules and of the loader sits inside `_describe`: `stayfixed trust`
reads `KINDS` when it builds its parser, and a store is resolved only when a command asks about one.
`stayfixed.trust.api`, which `KINDS` is built from, is the one import at module level.
"""

from __future__ import annotations

from stayfixed.trust.api import ApprovalKind, KindContext, Subject

# What a person reads for a store outside the path grammar, where `--json` carries its key.
UNNAMED_STORE = "the memory store"
# What `--help` says of `--store`, the words every command that takes it says
# (`stayfixed.command.STORE_HELP`, which this module cannot import when the parser is built, and
# `tests/test_command.py` holds every occurrence equal to).
STORE_HELP = "resolve the memory store at this path"
# A checkout a session reads no project configuration in, described as a session reads it: no
# store to describe. Fixed text: the session's own warning names what is wrong with the file.
NO_CONFIGURATION = (
    "a session reads no project configuration here — stayfixed.toml is missing or does not load "
    "for it — so it uses no store"
)


def _describe(context: KindContext) -> tuple[Subject, ...]:
    """This checkout's one store: keyed by its resolved path, labelled by its path in the
    repository, at its digest now. Read as a session reads the configuration when the context is
    `noting`, and as a command reads it, refusing, otherwise (`KindContext.noting`)."""
    from stayfixed.command import command_owner
    from stayfixed.config.loader import load
    from stayfixed.config.session import session_config
    from stayfixed.errors import Refusal
    from stayfixed.memory import trust
    from stayfixed.memory.commands import store_at

    if context.noting:
        session = session_config(context.root, machine=context.machine).config
        if session is None:
            raise Refusal(NO_CONFIGURATION)
        config = session
    else:
        config = load(context.root, machine=context.machine, owner=command_owner(context.machine))
    store = store_at(context.root, config, context.machine, context.options.get("--store"))
    try:
        label = store.path.relative_to(context.root).as_posix()
    except ValueError:
        label = UNNAMED_STORE
    return (Subject(trust.store_key(store), label, trust.store_digest(store, config)),)


KINDS = (ApprovalKind("memory", _describe, flags={"--store": STORE_HELP}),)
