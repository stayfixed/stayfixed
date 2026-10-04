"""The hooks area's import surface — and the one that **defines** rather than re-exports.

Every other area's `api.py` is a list of re-exports whose `__all__` equals what it imports.
This one cannot be, and the difference is structural rather than a lapse: the handler
vocabulary below is what `stayfixed.hooks.registry`, `stayfixed.hooks.dispatch`,
`stayfixed.hooks.sink` and every area's `hooks.py` import, so a name defined in one of those
modules and re-exported here would be an import cycle — `sink.py` imports `Sink` and
`NullSink` from this module, and this module would import the sink's layout back out of it.

So the rule this area follows is the other half of the same rule: **a name two areas share is
defined here.** The four names of the sink's on-disk layout live here for exactly that reason,
and `sink.py` imports them from here like everybody else. CONTRIBUTING records the exception.
Which harness a hook runs under is not vocabulary of this kind: it is answered once, by
`stayfixed.harnesses.detect` in `stayfixed hook`, and a handler reads the answer's name off
`HookEvent.harness`.

**Four names below have no importer outside this area**, and each stays for the reason beside it:

- `EVENTS` is the list a handler's event must come from: `registry.discover` refuses any other,
  and an area that needs a new event adds it here, beside the vocabulary its handlers use.
- `HandlerFn` is `Handler.run`'s type. `Handler` is what `guards/hooks.py` and
  `memory/hooks.py` build, and a consumer that holds one before registering it — a table of
  handlers, a decorator, a test double — cannot annotate the callable without this name.
- `Sink` is the protocol `dispatch.py` takes and `sink.py` implements, and `NullSink` is the
  degradation it falls back to when there is no harness data root. `doctor` reports on the tree
  those two write (`DIRECTORY`, `MARKERS`, `DIAGNOSTICS`), so the layout is published and the
  writer's own shape should be nameable beside it.

For this area, removing a name from `__all__` is not a trim in any case: `api.py` defines these
and `tests/test_surfaces.py` holds `DEFINES_ITS_OWN` areas to `imported | defined == __all__`,
so a defined name absent from the list reddens the contract. Trimming one is a decision to move
its definition into a private module, which is a different change with a different argument.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from stayfixed.config.schema import Config

__all__ = [
    "DIAGNOSTICS",
    "DIAGNOSTICS_MAX_BYTES",
    "DIRECTORY",
    "EVENTS",
    "MARKERS",
    "Decision",
    "Handler",
    "HandlerFn",
    "HookEvent",
    "HookResult",
    "NullSink",
    "Policy",
    "Sink",
]


# The five events the dispatcher carries. An area that needs a sixth adds it here deliberately;
# `registry.discover` refuses anything else, so a handler registered for "PreToolUSe" is a
# loud failure at discovery rather than a guard that never fires and tests that never notice.
EVENTS = (
    "SessionStart",
    "UserPromptSubmit",
    "UserPromptExpansion",
    "PreToolUse",
    "PostToolUse",
)


class Policy(StrEnum):
    OPEN = "open"
    CLOSED = "closed"


class Decision(StrEnum):
    DENY = "deny"


@dataclass(frozen=True)
class HookEvent:
    name: str
    session_id: str | None
    agent_id: str | None
    tool_name: str | None
    tool_input: dict[str, Any]
    cwd: Path
    project_root: Path | None
    # The name of the harness `harnesses.detect` answered; detection always answers.
    harness: str
    raw: dict[str, Any] = field(default_factory=dict, compare=False)


@dataclass
class HookResult:
    context: str | None = None
    decision: Decision | None = None
    reason: str | None = None


HandlerFn = Callable[[HookEvent, "Config | None"], HookResult]


@dataclass(frozen=True)
class Handler:
    name: str
    event: str
    policy: Policy
    run: HandlerFn
    # Handlers stay pure `(event, config) -> result`, so a handler that must run once
    # per context declares the marker key and the dispatcher owns the bookkeeping.
    once_key: str | None = None


# The sink's on-disk layout, which is a contract between two areas rather than one area's
# detail: `stayfixed.hooks.sink` writes this tree and `stayfixed.doctor` reports on it. Both used
# to reach for `sink.py` directly — doctor by a private cross-area import it wrote a paragraph
# to excuse — because a re-export could not live here without a cycle. Defining them here costs
# `sink.py` one import and gives doctor the published name it was owed.
DIRECTORY = "stayfixed"
MARKERS = "markers"
DIAGNOSTICS = "diagnostics.jsonl"
DIAGNOSTICS_MAX_BYTES = 256 * 1024


class Sink(Protocol):
    """Where the dispatcher records failures and once-per-context markers."""

    def diagnostic(self, record: dict[str, object]) -> None: ...

    def seen(self, key: str) -> bool: ...

    def mark(self, key: str) -> None: ...


class NullSink:
    """A sink that forgets rather than suppresses.

    `seen()` is always False, so `once_key` degrades from "once per context" to "every
    invocation" and every diagnostic is discarded.

    The durable, session-keyed sink now exists — `stayfixed.hooks.sink.sink_for` — and this is
    what it answers when there is nowhere to write: no harness data root, or one this process
    cannot write to. So this is the *degradation*, not the shipped default, and a handler whose
    work must genuinely happen once still cannot rely on `once_key` alone, because the
    degradation is a state any machine can be in.
    """

    def diagnostic(self, record: dict[str, object]) -> None:
        return None

    def seen(self, key: str) -> bool:
        return False

    def mark(self, key: str) -> None:
        return None
