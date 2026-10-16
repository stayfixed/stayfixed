"""A `SessionConfig` for a handler or `dispatch` called in this process, the way `stayfixed hook`
hands one over (`src/stayfixed/config/session.py`): the project's configuration, or none, over the
preset's owner's layer, with no warnings. A test about the session itself builds one with
`session_config`."""

from __future__ import annotations

from stayfixed.config.owner import resolve_owner
from stayfixed.config.schema import Config
from stayfixed.config.session import SessionConfig

# The owner's layer with no machine file: the preset's personal values, every guard on.
OWNER = resolve_owner(None)
# A session with no project configuration.
NO_CONFIG = SessionConfig(None, OWNER, ())


def session_of(config: Config | None) -> SessionConfig:
    """`config` as a session hands it to a handler."""
    return SessionConfig(config, OWNER, ())
