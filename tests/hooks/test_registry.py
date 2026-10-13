"""Discovery owns the event and policy vocabularies, so a mistype is not a silent no-op."""

from __future__ import annotations

from typing import cast

import pytest

from stayfixed.hooks.api import EVENTS, Handler, HookEvent, HookResult, Policy
from stayfixed.hooks.registry import UnknownHookEvent, UnknownHookPolicy, discover


class Area:
    """Stands in for `stayfixed.<area>.hooks`, which no shipped area provides yet."""

    def __init__(self, name: str, handlers: list[Handler]) -> None:
        self.__name__ = name
        self._handlers = handlers

    def register(self) -> list[Handler]:
        return self._handlers


def guard(event: str, policy: Policy = Policy.CLOSED) -> Handler:
    def run(ev: HookEvent, config: object) -> HookResult:
        return HookResult()

    return Handler(name="background-cleanup", event=event, policy=policy, run=run)


def area_of(monkeypatch: pytest.MonkeyPatch, *handlers: Handler) -> None:
    area = Area("stayfixed.example.hooks", list(handlers))
    monkeypatch.setattr("stayfixed.hooks.registry.area_modules", lambda submodule: [area])


def test_a_mistyped_event_name_is_refused_and_named(monkeypatch: pytest.MonkeyPatch) -> None:
    area_of(monkeypatch, guard("PreToolUSe"))
    with pytest.raises(UnknownHookEvent) as raised:
        discover()
    message = str(raised.value)
    assert "stayfixed.example.hooks" in message
    assert "'background-cleanup'" in message
    assert "'PreToolUSe'" in message


def test_a_handler_on_a_known_event_registers_normally(monkeypatch: pytest.MonkeyPatch) -> None:
    handler = guard("PreToolUse")
    area_of(monkeypatch, handler)
    assert discover() == [handler]


def test_the_vocabulary_is_the_six_events_the_design_table_carries() -> None:
    # An area that needs a seventh adds it to EVENTS deliberately; widening it by accident is
    # what turns a mistyped handler back into a guard that never fires. The sixth,
    # `PostToolUseFailure`, is where Claude Code delivers a command that exited non-zero.
    # Mutation: `mutations/`'s "the dispatcher stops carrying the event a failed command arrives
    # on".
    assert EVENTS == (
        "SessionStart",
        "UserPromptSubmit",
        "UserPromptExpansion",
        "PreToolUse",
        "PostToolUse",
        "PostToolUseFailure",
    )


@pytest.mark.parametrize("policy", ["CLOSED", "strict", "", 1, None])
def test_a_policy_dispatch_cannot_read_is_refused_and_named(
    monkeypatch: pytest.MonkeyPatch, policy: object
) -> None:
    # `dispatch` compares `handler.policy == Policy.CLOSED`, so a policy it cannot read is an
    # OPEN handler — a guard that fires, fails, and permits. Discovery is where that is loud,
    # exactly as a mistyped `event` already is.
    area_of(monkeypatch, guard("PreToolUse", cast(Policy, policy)))
    with pytest.raises(UnknownHookPolicy) as raised:
        discover()
    message = str(raised.value)
    assert "stayfixed.example.hooks" in message
    assert "'background-cleanup'" in message
    assert repr(policy) in message


def test_a_policy_that_arrived_as_a_plain_string_is_accepted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # `Policy` is a StrEnum and `dispatch` compares by value, so discovery must accept exactly
    # what `dispatch` accepts: an area building a Handler from a config string hands us "closed".
    handler = guard("PreToolUse", cast(Policy, "closed"))
    area_of(monkeypatch, handler)
    assert discover() == [handler]
