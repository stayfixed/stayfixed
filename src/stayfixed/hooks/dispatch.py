"""Run the handlers registered for an event and own the exit code and output shape."""

from __future__ import annotations

import copy
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import TYPE_CHECKING, Any

from stayfixed.gitenv import checkout_root
from stayfixed.harnesses import Harness, project_root_variables
from stayfixed.hooks.api import Decision, Handler, HookEvent, HookResult, Policy, Sink, first_set

if TYPE_CHECKING:
    from stayfixed.config.schema import Config

TRUNCATION_MARK = "\n[stayfixed: context truncated to the platform cap]"


@dataclass(frozen=True)
class Outcome:
    exit_code: int
    stdout: str
    stderr: str
    decision: str | None = None


@dataclass
class Recorder:
    """A sink that keeps its records and markers in memory; the tests use it."""

    records: list[dict[str, object]] = field(default_factory=list)
    marks: set[str] = field(default_factory=set)

    def diagnostic(self, record: dict[str, object]) -> None:
        self.records.append(record)

    def seen(self, key: str) -> bool:
        return key in self.marks

    def mark(self, key: str) -> None:
        self.marks.add(key)


def read_event(payload: dict[str, Any], env: Mapping[str, str]) -> HookEvent:
    """The one reading of a hook's stdin, whichever harness sent it, and never told which.

    The detected harness is one a repository can choose: a committed `.claude/settings.json`
    `env` block can set `PLUGIN_ROOT`, so an event that varied with detection would hand the
    repository the choice of what its guards read. That holds for the project root above all,
    since it decides which configuration loads and so whether a guard refuses: the root is the
    first non-empty variable among every registered harness's, asked in
    `harnesses.project_root_variables`' order, and without one the checkout `cwd` sits in
    (`gitenv.checkout_root`). Codex names none (measured in the spike record,
    `docs/plans/2026-09-05-agent-harness-p0-spikes.md`, in its *Codex plugin hooks* trial), so
    under Codex an inherited `CLAUDE_PROJECT_DIR` still names the root, as it names the directory
    `hooks/run-hook.sh` enters. The detected harness contributes its `render` to the answer and
    nothing to the event.
    """
    cwd = Path(str(payload.get("cwd") or "."))
    named = first_set(env, project_root_variables())
    tool_input = payload.get("tool_input") or {}
    session_id = payload.get("session_id")
    agent_id = payload.get("agent_id")
    tool_name = payload.get("tool_name")
    return HookEvent(
        name=str(payload.get("hook_event_name") or "unknown"),
        session_id=session_id if isinstance(session_id, str) else None,
        agent_id=agent_id if isinstance(agent_id, str) else None,
        tool_name=tool_name if isinstance(tool_name, str) else None,
        tool_input=tool_input if isinstance(tool_input, dict) else {},
        cwd=cwd,
        project_root=checkout_root(cwd) if named is None else Path(named),
        raw=dict(payload),
    )


def _clamp(render: Callable[[str, str], str], event_name: str, context: str, cap: int) -> str:
    """Fit the emitted string, envelope included, inside the platform's per-hook cap.

    Claude Code caps each hook's output string at 10,000 characters — `additionalContext`,
    `systemMessage` and plain stdout alike — and replaces anything longer with a preview and a
    file path. A bundle truncated to the cap and then wrapped in JSON therefore gets replaced
    while the truncation mark claims it was handled. The envelope's width depends on the
    harness that renders it and on the event name, and JSON escaping widens the context itself,
    so the largest prefix that still fits, as `render` (the detected harness's) shapes it, is
    searched for rather than computed. A cap that leaves no room even for the empty envelope
    emits nothing: an over-cap string would be replaced by a preview anyway.
    """
    best: str | None = None
    low, high = 0, min(len(context), cap)  # a kept character costs at least one of the cap
    while low <= high:
        keep = (low + high) // 2
        stdout = render(event_name, context[:keep] + TRUNCATION_MARK)
        if len(stdout) <= cap:
            best, low = stdout, keep + 1
        else:
            high = keep - 1
    if best is not None:
        return best
    bare = render(event_name, "")
    return bare if len(bare) <= cap else ""


class _UnrecognisedDecision(Exception):
    """A verdict `dispatch` cannot read.

    Raised rather than ignored so it travels the path a handler's exception already travels:
    the handler's own policy judges it, a CLOSED guard that misnames its deny refuses instead
    of permitting, and the reason reaches stderr — which production reads — and not only the
    sink, which today forgets (see `NullSink`).
    """

    def __init__(self, decision: object) -> None:
        super().__init__(f"unrecognised decision {decision!r}")
        self.decision = decision


class _UnrecognisedContext(Exception):
    """A `context` `dispatch` cannot join into the emitted payload.

    `HookResult.context` is typed `str | None`, but nothing stops a dynamically built result
    from carrying something else, and the join that builds the payload happens once, after
    every handler has run — outside every per-handler `try`. Raised inside the per-handler
    `try` instead, so a malformed `context` is that handler failing rather than a `TypeError`
    that takes down the whole dispatch: an OPEN handler's policy swallows it and a CLOSED
    handler's policy refuses, exactly like a malformed decision. Raised *after* the decision
    branch, never before it: a deny already read off the same result is banked first, so a
    handler that denies and carries a malformed context keeps its refusal.
    """

    def __init__(self, context: object) -> None:
        super().__init__(f"unrecognised context {context!r}")
        self.context = context


def _failure(exc: BaseException) -> tuple[str, dict[str, object]]:
    """The stderr reason and the sink record one handler's failure earns."""
    if isinstance(exc, _UnrecognisedDecision):
        return str(exc), {"error": "unrecognised-decision", "decision": str(exc.decision)}
    if isinstance(exc, _UnrecognisedContext):
        return str(exc), {"error": "unrecognised-context", "context": str(exc.context)}
    return f"{type(exc).__name__}: {exc}", {"error": type(exc).__name__}


def dispatch(
    event: HookEvent,
    handlers: list[Handler],
    config: Config | None,
    *,
    harness: Harness,
    sink: Sink,
    cap: int | None = None,
) -> Outcome:
    """One deny travels on one channel — the exit code — so every failure here is judged.

    `harness` is the value `harnesses.detect` answered, and it shapes an answer that lets the
    call through and nothing else: a refusal is exit 2, empty stdout and the reasons on stderr
    for every harness, and no value is asked about it, so a rendering that fails cannot cost a
    deny. `sink` and `harness` carry no default on purpose: a caller that has no durable sink
    must say so with `NullSink()` and inherit its forgetfulness, and one that has not asked which
    harness it runs under must say which it means, rather than acquire either by omission.
    """
    contexts: list[str] = []
    reasons: list[str] = []
    refuse = False
    for handler in handlers:
        if handler.event != event.name:
            continue
        if handler.once_key is not None and sink.seen(handler.once_key):
            continue
        try:
            # Purity is contractual and unenforceable, and handlers run in name order, so an
            # earlier one could blank `tool_input["command"]` under a later one's guard. Each
            # handler gets its own deep copy of the mutable views instead. `raw` is copied once
            # and `tool_input` is taken from that same copy, so the view keeps the aliasing
            # `read_event` produces (`ev.tool_input is ev.raw["tool_input"]`) rather than
            # diverging under two independent deep copies.
            raw_view = copy.deepcopy(event.raw)
            raw_tool_input = raw_view.get("tool_input")
            tool_input_view = (
                raw_tool_input
                if isinstance(raw_tool_input, dict)
                else copy.deepcopy(event.tool_input)
            )
            view = replace(event, tool_input=tool_input_view, raw=raw_view)
            result = handler.run(view, config)
            # Consuming the result belongs inside this `try`: reading `.context` off whatever a
            # handler actually returned used to raise out of `dispatch` entirely, so one later
            # handler's malformed return destroyed an earlier handler's deny.
            if not isinstance(result, HookResult):
                raise TypeError(f"returned {type(result).__name__}, not HookResult")
            # Delivery is DECIDED here and BANKED below. A handler that answered
            # with an empty result has said nothing, and spending its one delivery on that
            # would make the first unrelated Bash call of a session consume a notice meant for
            # the first failing test run. A deny is a delivery too: it reached the harness.
            # Computed here because it reads the result's fields, so it must follow the type
            # check above; the `sink.mark` that acts on it is below both validations, because
            # a result either of them rejects is a result nobody received.
            delivered = bool(result.context) or result.decision == Decision.DENY
            # The decision is read before anything else that can fail this handler. A deny is
            # the one thing a neighbouring bug must never cost, and it travels on one channel;
            # banking it here means a malformed `context` on the same result costs that handler
            # its context and a recorded failure, not its refusal. Validating `context` above
            # this branch turned a live deny into an allow, which is the very defect the
            # per-handler judging exists to prevent. The asymmetry with a malformed *decision*
            # is deliberate: there is no well-formed deny to lose there.
            if result.decision == Decision.DENY:
                reasons.append(f"{handler.name}: {result.reason or 'denied'}")
                refuse = True
            elif result.decision is not None:
                raise _UnrecognisedDecision(result.decision)
            # `context` is validated here too, and not only at the join below: the join runs
            # once after every handler, outside every per-handler `try`, so a non-string context
            # caught there would take the whole dispatch down instead of being judged by this
            # handler's own policy.
            if result.context is not None and not isinstance(result.context, str):
                raise _UnrecognisedContext(result.context)
            # The delivery is banked here, past every check that can discard this result, and
            # that placement is the whole point: marking above the two validations spent a
            # once-per-context handler's single delivery on a result that then raised into the
            # `except` below, so the context never reached `contexts`, never reached stdout,
            # and the notice was gone for the session. Above the `if` below, not inside it: a
            # deny with no context is a delivery that never appends anything, and marking at
            # the append would stop marking it. One accepted loss remains, stated rather than
            # hidden: when a NEIGHBOURING handler denies in the same dispatch, `contexts` is
            # discarded with the refusal and this handler's context never reaches the harness
            # although its delivery is spent. The alternative — marking after the join for the
            # contexts that survived into stdout — is the foundation's redesign, not this
            # line's.
            if handler.once_key is not None and delivered:
                sink.mark(handler.once_key)
            if result.context:
                contexts.append(result.context)
        except BaseException as exc:  # judged by the handler's own policy
            reason, record = _failure(exc)
            reasons.append(f"{handler.name}: {reason}")
            sink.diagnostic({"event": event.name, "handler": handler.name, **record})
            refuse = refuse or handler.policy == Policy.CLOSED
            continue
    if refuse:
        return Outcome(2, "", "stayfixed: refused: " + "; ".join(reasons) + "\n", "deny")
    stderr = ("stayfixed: " + "; ".join(reasons) + "\n") if reasons else ""
    context = "\n\n".join(contexts)
    stdout = harness.render(event.name, context)
    if cap is not None and len(stdout) > cap:
        stdout = _clamp(harness.render, event.name, context, cap)
        sink.diagnostic({"event": event.name, "handler": "*", "error": "context-truncated"})
    return Outcome(0, stdout, stderr, None)
