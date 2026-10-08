# tests/hooks/test_dispatch.py
from __future__ import annotations

import argparse
import asyncio
import errno
import io
import json
import os
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, cast

import pytest

from stayfixed.gitenv import _git_toplevel
from stayfixed.harnesses import CLAUDE, HARNESSES, Harness
from stayfixed.hooks.api import Decision, Handler, HookEvent, HookResult, NullSink, Policy
from stayfixed.hooks.commands import run_hook
from stayfixed.hooks.dispatch import TRUNCATION_MARK, Recorder, dispatch, read_event
from tests.gitfixture import git
from tests.ownerhome import as_owner_home

CLAUDE_ENV = {"CLAUDE_PROJECT_DIR": "/p", "CLAUDE_PLUGIN_ROOT": "/r"}


def event(name: str = "PreToolUse", **raw: object) -> HookEvent:
    payload: dict[str, object] = {
        "hook_event_name": name,
        "session_id": "s",
        "cwd": "/tmp",
        "tool_name": "Bash",
    }
    payload.update(raw)
    return read_event(payload, CLAUDE_ENV)


def handler(
    name: str,
    policy: Policy,
    result: HookResult | BaseException,
    once_key: str | None = None,
    event_name: str = "PreToolUse",
) -> Handler:
    def run(ev: HookEvent, config: object) -> HookResult:
        if isinstance(result, BaseException):
            raise result
        return result

    return Handler(name=name, event=event_name, policy=policy, run=run, once_key=once_key)


def test_contexts_are_joined_into_the_claude_shape() -> None:
    handlers = [
        handler("a", Policy.OPEN, HookResult(context="A")),
        handler("b", Policy.OPEN, HookResult(context="B")),
    ]
    outcome = dispatch(event(), handlers, config=None, harness=CLAUDE, sink=Recorder())
    assert outcome.exit_code == 0
    assert json.loads(outcome.stdout) == {
        "hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": "A\n\nB"}
    }


@pytest.mark.parametrize(
    ("registered", "other"), [("PostToolUse", "PreToolUse"), ("PreToolUse", "PostToolUse")]
)
def test_a_handler_stays_silent_on_every_event_but_its_own(registered: str, other: str) -> None:
    # `discover()` hands the dispatcher every area's handlers at once, so the event filter is
    # the only thing keeping a PostToolUse guard from refusing a PreToolUse call.
    guard = handler(
        "g", Policy.CLOSED, HookResult(decision=Decision.DENY, reason="no"), event_name=registered
    )
    assert (
        dispatch(event(registered), [guard], None, harness=CLAUDE, sink=Recorder()).exit_code == 2
    )
    silent = dispatch(event(other), [guard], None, harness=CLAUDE, sink=Recorder())
    assert silent.exit_code == 0
    assert silent.stderr == ""


def test_a_decision_that_arrived_as_a_plain_string_still_denies() -> None:
    # A handler building a HookResult dynamically hands us "deny", not Decision.DENY. `Decision` is
    # a StrEnum, so the comparison must be by value: under identity this deny would be an
    # unrecognised verdict instead, which an OPEN handler's policy swallows.
    result = HookResult(decision=cast(Decision, "deny"))
    outcome = dispatch(
        event(), [handler("a", Policy.OPEN, result)], None, harness=CLAUDE, sink=Recorder()
    )
    assert outcome.exit_code == 2
    assert outcome.decision == "deny"


def test_a_deny_from_a_handler_exits_two_with_its_reason() -> None:
    handlers = [handler("g", Policy.CLOSED, HookResult(decision=Decision.DENY, reason="no"))]
    outcome = dispatch(event(), handlers, config=None, harness=CLAUDE, sink=Recorder())
    assert outcome.exit_code == 2
    assert outcome.decision == "deny"
    assert "no" in outcome.stderr


def test_an_open_handler_that_raises_is_swallowed_and_recorded() -> None:
    recorder = Recorder()
    outcome = dispatch(
        event(),
        [handler("a", Policy.OPEN, RuntimeError("boom"))],
        None,
        harness=CLAUDE,
        sink=recorder,
    )
    assert outcome.exit_code == 0
    assert "boom" in outcome.stderr
    assert recorder.records[0]["handler"] == "a"
    assert recorder.records[0]["error"] == "RuntimeError"


def test_a_closed_handler_that_raises_refuses() -> None:
    outcome = dispatch(
        event(),
        [handler("g", Policy.CLOSED, RuntimeError("boom"))],
        None,
        harness=CLAUDE,
        sink=Recorder(),
    )
    assert outcome.exit_code == 2
    assert "boom" in outcome.stderr


def test_a_policy_that_arrived_as_a_plain_string_still_closes() -> None:
    # An area that builds a Handler dynamically hands us "closed", not Policy.CLOSED; mypy
    # cannot see that, so the cast stands in for it.
    closed = cast(Policy, "closed")
    outcome = dispatch(
        event(), [handler("g", closed, RuntimeError("boom"))], None, harness=CLAUDE, sink=Recorder()
    )
    assert outcome.exit_code == 2


def test_a_closed_handler_that_calls_sys_exit_refuses() -> None:
    outcome = dispatch(
        event(), [handler("g", Policy.CLOSED, SystemExit(0))], None, harness=CLAUDE, sink=Recorder()
    )
    assert outcome.exit_code == 2
    assert "SystemExit" in outcome.stderr


def test_an_unrecognised_decision_under_an_open_policy_is_swallowed_with_a_reason() -> None:
    recorder = Recorder()
    result = HookResult(decision=cast(Decision, "block"))
    outcome = dispatch(
        event(), [handler("a", Policy.OPEN, result)], None, harness=CLAUDE, sink=recorder
    )
    assert outcome.exit_code == 0
    # Production reads stderr and never reads the sink, so the reason must be on both.
    assert "unrecognised decision 'block'" in outcome.stderr
    assert recorder.records[0]["error"] == "unrecognised-decision"
    assert recorder.records[0]["decision"] == "block"


@pytest.mark.parametrize("decision", ["DENY", "block", True, 7, None.__class__])
def test_an_unrecognised_decision_under_a_closed_policy_refuses(decision: object) -> None:
    # A guard that means to deny but misnames its verdict must not read as permission: the
    # malformed verdict is that handler failing, and a CLOSED handler's failure refuses.
    recorder = Recorder()
    result = HookResult(decision=cast(Decision, decision))
    outcome = dispatch(
        event(), [handler("g", Policy.CLOSED, result)], None, harness=CLAUDE, sink=recorder
    )
    assert outcome.exit_code == 2
    assert "unrecognised decision" in outcome.stderr
    assert recorder.records[0]["error"] == "unrecognised-decision"


def test_an_open_handlers_non_string_context_is_swallowed_and_a_later_one_lands() -> None:
    # `result.context` used to be joined into the payload outside every per-handler `try`, so
    # one OPEN handler's malformed context took the whole dispatch down with a TypeError instead
    # of being judged by that handler's own policy the way a malformed decision already is.
    recorder = Recorder()
    broken = handler("a-broken", Policy.OPEN, HookResult(context=cast(str, 42)))
    ok = handler("b-ok", Policy.OPEN, HookResult(context="B"))
    outcome = dispatch(event(), [broken, ok], None, harness=CLAUDE, sink=recorder)
    assert outcome.exit_code == 0
    assert "unrecognised context" in outcome.stderr
    assert recorder.records[0]["error"] == "unrecognised-context"
    assert recorder.records[0]["context"] == "42"
    assert json.loads(outcome.stdout)["hookSpecificOutput"]["additionalContext"] == "B"


def test_a_closed_handlers_non_string_context_refuses() -> None:
    recorder = Recorder()
    result = HookResult(context=cast(str, 42))
    outcome = dispatch(
        event(), [handler("g", Policy.CLOSED, result)], None, harness=CLAUDE, sink=recorder
    )
    assert outcome.exit_code == 2
    assert "unrecognised context" in outcome.stderr
    assert recorder.records[0]["error"] == "unrecognised-context"


@pytest.mark.parametrize("policy", [Policy.OPEN, Policy.CLOSED])
@pytest.mark.parametrize("decision", [Decision.DENY, "deny"], ids=["enum", "string"])
def test_a_deny_carrying_a_malformed_context_still_refuses_and_records_the_failure(
    policy: Policy, decision: object
) -> None:
    # One result carries both the deny and the malformed context, so the order the two are read
    # in decides the exit code. Validating `context` above the decision branch failed the handler
    # before its deny was ever recorded, and an OPEN handler's policy then swallowed the whole
    # result — a live deny converted into an allow by an ordinary neighbouring bug. The decision
    # is read first now, and the context failure is still judged, on top of the refusal.
    recorder = Recorder()
    result = HookResult(
        decision=cast(Decision, decision),
        reason="rm -rf / is refused",
        context=cast(str, {"n": 1}),
    )
    outcome = dispatch(event(), [handler("g", policy, result)], None, harness=CLAUDE, sink=recorder)
    assert outcome.exit_code == 2
    assert outcome.decision == "deny"
    assert "g: rm -rf / is refused" in outcome.stderr
    # Production reads stderr and never reads the sink, so the failure must reach both.
    assert "unrecognised context {'n': 1}" in outcome.stderr
    assert recorder.records[0]["error"] == "unrecognised-context"
    assert recorder.records[0]["context"] == "{'n': 1}"


def test_an_earlier_deny_survives_a_later_handlers_malformed_context() -> None:
    # Not PreToolUse: there `run_hook`'s blanket catch maps any internal error to 2 anyway, so
    # the lost deny is invisible. Everywhere else an escaped TypeError left the process at 0.
    recorder = Recorder()
    deny = handler(
        "a-deny",
        Policy.CLOSED,
        HookResult(decision=Decision.DENY, reason="no"),
        event_name="PostToolUse",
    )
    broken = handler(
        "b-broken", Policy.OPEN, HookResult(context=cast(str, 42)), event_name="PostToolUse"
    )
    outcome = dispatch(event("PostToolUse"), [deny, broken], None, harness=CLAUDE, sink=recorder)
    assert outcome.exit_code == 2
    assert outcome.decision == "deny"
    assert "a-deny: no" in outcome.stderr


@pytest.mark.parametrize("policy", [Policy.CLOSED, Policy.OPEN])
@pytest.mark.parametrize("raised", [asyncio.CancelledError(), KeyboardInterrupt()], ids=type)
def test_a_base_exception_from_a_handler_is_judged_by_that_handlers_policy(
    policy: Policy, raised: BaseException
) -> None:
    # A handler that awaits anything surfaces CancelledError and a Ctrl-C mid-hook surfaces
    # KeyboardInterrupt; neither inherits Exception, so both used to escape every guard and
    # exit the process on something that is not 2 — a CLOSED guard reading as an allow.
    # CancelledError leads: a regression on it fails one test, where KeyboardInterrupt aborts
    # the whole session and would otherwise be the only signal.
    recorder = Recorder()
    outcome = dispatch(event(), [handler("g", policy, raised)], None, harness=CLAUDE, sink=recorder)
    assert outcome.exit_code == (2 if policy == Policy.CLOSED else 0)
    assert type(raised).__name__ in outcome.stderr
    assert recorder.records[0]["error"] == type(raised).__name__


def test_an_earlier_deny_survives_a_later_handlers_malformed_return() -> None:
    # Not PreToolUse: there `run_hook`'s blanket catch maps any internal error to 2 anyway, so
    # the lost deny is invisible. Everywhere else the AttributeError left the process at 0.
    recorder = Recorder()
    deny = handler(
        "a-deny",
        Policy.CLOSED,
        HookResult(decision=Decision.DENY, reason="no"),
        event_name="PostToolUse",
    )
    broken = handler("b-broken", Policy.OPEN, cast(HookResult, None), event_name="PostToolUse")
    outcome = dispatch(event("PostToolUse"), [deny, broken], None, harness=CLAUDE, sink=recorder)
    assert outcome.exit_code == 2
    assert outcome.decision == "deny"
    assert "a-deny: no" in outcome.stderr
    assert recorder.records[0] == {
        "event": "PostToolUse",
        "handler": "b-broken",
        "error": "TypeError",
    }


def test_a_null_sink_forgets_a_marker_instead_of_suppressing_it() -> None:
    # The shipped `run_hook` passes a NullSink, so this is production's `once_key` semantics.
    sink = NullSink()
    sink.mark("ledger-notes")
    assert sink.seen("ledger-notes") is False


def test_a_once_key_handler_runs_every_time_under_the_null_sink() -> None:
    runs: list[int] = []

    def count(ev: HookEvent, config: object) -> HookResult:
        runs.append(1)
        return HookResult(context="A")

    once = Handler(
        name="a", event="PreToolUse", policy=Policy.OPEN, run=count, once_key="ledger-notes"
    )
    for _ in range(2):
        dispatch(event(), [once], None, harness=CLAUDE, sink=NullSink())
    assert runs == [1, 1]


def test_policy_is_taken_from_handlers_that_failed_not_from_all_registered() -> None:
    handlers = [
        handler("g", Policy.CLOSED, HookResult()),
        handler("a", Policy.OPEN, RuntimeError("boom")),
    ]
    assert dispatch(event(), handlers, None, harness=CLAUDE, sink=Recorder()).exit_code == 0


def test_a_cap_below_the_envelope_is_recorded_and_emits_nothing() -> None:
    # No JSON envelope fits in 20 characters, so the honest output is none at all: anything
    # longer than the cap is replaced by the platform with a preview and a file path.
    recorder = Recorder()
    handlers = [handler("a", Policy.OPEN, HookResult(context="x" * 50))]
    outcome = dispatch(event(), handlers, None, harness=CLAUDE, sink=recorder, cap=20)
    assert outcome.stdout == ""
    assert recorder.records[0]["error"] == "context-truncated"


def test_context_at_a_realistic_cap_keeps_its_leading_content_and_the_mark() -> None:
    handlers = [handler("a", Policy.OPEN, HookResult(context="y" * 500))]
    outcome = dispatch(event(), handlers, None, harness=CLAUDE, sink=Recorder(), cap=200)
    context = json.loads(outcome.stdout)["hookSpecificOutput"]["additionalContext"]
    # Every kept character here is plain ASCII, so nothing widens under JSON escaping and the
    # search always lands exactly on the cap: what is left of it after the envelope and the mark
    # is the true optimum for this event name and context, not merely a value close to it.
    assert len(outcome.stdout) == 200
    assert context == "y" * (len(context) - len(TRUNCATION_MARK)) + TRUNCATION_MARK


def test_the_cap_bounds_the_emitted_string_not_the_field_inside_it() -> None:
    handlers = [handler("a", Policy.OPEN, HookResult(context="x" * 20000))]
    outcome = dispatch(event(), handlers, None, harness=CLAUDE, sink=Recorder(), cap=10000)
    assert len(outcome.stdout) <= 10000
    context = json.loads(outcome.stdout)["hookSpecificOutput"]["additionalContext"]
    assert context.endswith(TRUNCATION_MARK)


def test_json_escaping_is_charged_to_the_same_budget() -> None:
    # Each kept `\n` costs two rendered characters once JSON-escaped, so of two adjacent caps one
    # leaves a budget that cannot be spent to the last character: the true optimum lands on one
    # cap and one short of the other. Asking both pins that without depending on which one is
    # odd, which the envelope's and the mark's widths decide and a rename moves. Mutations (by
    # hand): `_clamp`'s `<= cap` as `< cap` -> [1, 2]; as `<= cap + 1` -> [-1, 0]; each reddens.
    handlers = [handler("a", Policy.OPEN, HookResult(context="\n" * 500))]
    shortfall = []
    for cap in (200, 201):
        stdout = dispatch(event(), handlers, None, harness=CLAUDE, sink=Recorder(), cap=cap).stdout
        context = json.loads(stdout)["hookSpecificOutput"]["additionalContext"]
        assert context.endswith(TRUNCATION_MARK)
        assert set(context.removesuffix(TRUNCATION_MARK)) == {"\n"}
        shortfall.append(cap - len(stdout))
    assert sorted(shortfall) == [0, 1]


def test_a_once_per_context_handler_runs_once_and_is_skipped_afterwards() -> None:
    recorder = Recorder()
    once = handler("a", Policy.OPEN, HookResult(context="A"), once_key="ledger-notes")
    first = json.loads(dispatch(event(), [once], None, harness=CLAUDE, sink=recorder).stdout)
    second = json.loads(dispatch(event(), [once], None, harness=CLAUDE, sink=recorder).stdout)
    assert first["hookSpecificOutput"]["additionalContext"] == "A"
    assert "additionalContext" not in second["hookSpecificOutput"]
    assert recorder.marks == {"ledger-notes"}


def test_a_once_per_context_handler_that_says_nothing_keeps_its_one_delivery() -> None:
    """An empty result is not a delivery, so the handler is asked again.

    `dispatch` banks a `once_key` only `if handler.once_key is not None and delivered`, and
    `delivered` is `bool(result.context) or result.decision == Decision.DENY` -- spending a
    handler's single delivery on a result that said nothing would let the first unrelated Bash
    call of a session consume a notice meant for the first failing test run. That is the right
    rule and it has a consequence worth stating: a handler whose healthy answer is silence runs
    on every matching event, and pays whatever it pays to decide that, every time.
    `attach/hooks.py` is the handler that made this worth writing down -- its own docstring said
    the opposite about which path its `git` calls fall on.

    Mutation: `mutations/`'s "a silent handler spends its one delivery".
    """
    recorder = Recorder()
    silent = handler("a", Policy.OPEN, HookResult(), once_key="overlay-status")
    for _ in range(3):
        outcome = dispatch(event(), [silent], None, harness=CLAUDE, sink=recorder)
        assert "additionalContext" not in json.loads(outcome.stdout)["hookSpecificOutput"]
    assert recorder.marks == set()
    # Non-vacuous: the same handler with something to say does bank it, so this is about the
    # emptiness of the result and not about the key being ignored.
    speaking = handler("a", Policy.OPEN, HookResult(context="A"), once_key="overlay-status")
    dispatch(event(), [speaking], None, harness=CLAUDE, sink=recorder)
    assert recorder.marks == {"overlay-status"}


def test_a_handler_without_a_once_key_runs_every_time() -> None:
    recorder = Recorder()
    every = handler("a", Policy.OPEN, HookResult(context="A"))
    for _ in range(2):
        outcome = dispatch(event(), [every], None, harness=CLAUDE, sink=recorder)
        assert json.loads(outcome.stdout)["hookSpecificOutput"]["additionalContext"] == "A"
    assert recorder.marks == set()


def test_a_once_per_context_handler_that_raises_is_not_marked() -> None:
    recorder = Recorder()
    once = handler("a", Policy.OPEN, RuntimeError("boom"), once_key="ledger-notes")
    assert "boom" in dispatch(event(), [once], None, harness=CLAUDE, sink=recorder).stderr
    assert recorder.marks == set()
    assert "boom" in dispatch(event(), [once], None, harness=CLAUDE, sink=recorder).stderr


@pytest.mark.parametrize(
    "rejected",
    [
        HookResult(context=cast(str, 42)),
        HookResult(context="A", decision=cast(Decision, "block")),
    ],
    ids=["non-string-context", "unrecognised-decision"],
)
def test_a_once_per_context_handler_whose_result_is_rejected_keeps_its_one_delivery(
    rejected: HookResult,
) -> None:
    # The delivery used to be banked above the two validations that can discard the result. A
    # truthy non-string `context`, or an unrecognised decision alongside a context, marked
    # `once_key` and then raised into the per-handler `except`: the context never reached
    # `contexts`, never reached stdout, and the handler was skipped for the rest of the
    # session — its one notice spent on a result nobody received. Both arms are parametrised
    # because the two validations are separate branches and a fix to one is not a fix to both.
    #
    # Asserted from both sides, because "not marked" alone is satisfied by a handler that
    # never ran: the rejected dispatch records the failure and marks nothing, and the NEXT
    # dispatch still delivers, which is the property the mark exists to protect.
    #
    # Mutation (declared): mark immediately after `delivered` is computed -> the first
    # dispatch marks `ledger-notes`, the second is skipped, and the last two assertions
    # redden on both arms.
    recorder = Recorder()
    results = [rejected, HookResult(context="A")]

    def run(ev: HookEvent, config: object) -> HookResult:
        return results.pop(0)

    once = Handler(
        name="a", event="PreToolUse", policy=Policy.OPEN, run=run, once_key="ledger-notes"
    )
    first = dispatch(event(), [once], None, harness=CLAUDE, sink=recorder)
    assert "unrecognised" in first.stderr, first.stderr
    assert recorder.marks == set()
    second = dispatch(event(), [once], None, harness=CLAUDE, sink=recorder)
    assert json.loads(second.stdout)["hookSpecificOutput"]["additionalContext"] == "A"
    assert recorder.marks == {"ledger-notes"}


def test_a_deny_that_carries_no_context_is_still_a_delivery() -> None:
    # The mark sits above `if result.context:`, not inside it, and this is the assertion that
    # holds it there: a deny with no context appends nothing, so a mark written at the append
    # would stop marking the one case the `or result.decision == Decision.DENY` half of
    # `delivered` exists for. A deny reached the harness; it spent the delivery.
    #
    # No mutation entry of its own: moving the mark inside the `if` is the mutation, and it is
    # a change of indentation rather than a substituted line. Measured by hand instead — see
    # the fix report.
    recorder = Recorder()
    once = handler(
        "a", Policy.OPEN, HookResult(decision=Decision.DENY, reason="no"), once_key="ledger-notes"
    )
    outcome = dispatch(event(), [once], None, harness=CLAUDE, sink=recorder)
    assert outcome.exit_code == 2
    assert recorder.marks == {"ledger-notes"}


def test_one_handler_cannot_blank_what_the_next_one_reads() -> None:
    seen: list[object] = []

    def blank(ev: HookEvent, config: object) -> HookResult:
        ev.tool_input["command"] = ""
        ev.raw["tool_name"] = "Write"
        return HookResult()

    def read(ev: HookEvent, config: object) -> HookResult:
        seen.append(ev.tool_input.get("command"))
        seen.append(ev.raw.get("tool_name"))
        return HookResult()

    handlers = [
        Handler(name="a-blank", event="PreToolUse", policy=Policy.OPEN, run=blank),
        Handler(name="b-read", event="PreToolUse", policy=Policy.OPEN, run=read),
    ]
    dispatch(
        event(tool_input={"command": "rm -rf /"}), handlers, None, harness=CLAUDE, sink=Recorder()
    )
    assert seen == ["rm -rf /", "Bash"]


def test_a_handlers_view_keeps_tool_input_aliased_to_raw_like_read_event_does() -> None:
    # `read_event` makes `ev.tool_input is ev.raw["tool_input"]` true; the per-handler view
    # must preserve that aliasing, not just isolate handlers from each other, so a handler that
    # writes through `tool_input` and reads back through `raw` sees its own write.
    seen: dict[str, object] = {}

    def write_through_tool_input_read_through_raw(ev: HookEvent, config: object) -> HookResult:
        seen["aliased"] = ev.tool_input is ev.raw["tool_input"]
        ev.tool_input["command"] = "mutated"
        seen["raw_command_after"] = ev.raw["tool_input"]["command"]
        return HookResult()

    handlers = [
        Handler(
            name="a",
            event="PreToolUse",
            policy=Policy.OPEN,
            run=write_through_tool_input_read_through_raw,
        )
    ]
    dispatch(event(tool_input={"command": "ls"}), handlers, None, harness=CLAUDE, sink=Recorder())
    assert seen == {"aliased": True, "raw_command_after": "mutated"}


def test_non_string_contract_fields_become_none_instead_of_reaching_a_guard() -> None:
    ev = read_event(
        {
            "hook_event_name": "PreToolUse",
            "cwd": "/tmp",
            "session_id": 7,
            "agent_id": ["a"],
            "tool_name": {"name": "Bash"},
        },
        CLAUDE_ENV,
    )
    assert ev.session_id is None
    assert ev.agent_id is None
    assert ev.tool_name is None


def _forbidden(cwd: Path) -> Path | None:
    raise AssertionError(f"git was forked for {cwd}")


def test_a_harness_registered_first_never_takes_the_root_from_claude_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The registry's order is the order `init` writes `[stayfixed] agents` in, and adding a
    # harness ahead of Claude Code must not change which directory a Claude Code session's
    # configuration loads from. So the canonical harness's variable is asked first, whatever the
    # registry order, and the others' after it. Mutation (declared, on `harnesses`): the
    # variables are asked in registry order -> the fake's root wins and this reddens.
    project = tmp_path / "project"
    project.mkdir()
    fake = _harness(lambda name, context: context, project_dir_env="FAKE_PROJECT_DIR")
    monkeypatch.setattr("stayfixed.harnesses.HARNESSES", (fake, *HARNESSES))
    monkeypatch.setattr("stayfixed.gitenv._git_toplevel", _forbidden)
    env = {"CLAUDE_PROJECT_DIR": str(project), "FAKE_PROJECT_DIR": str(tmp_path / "elsewhere")}
    ev = read_event({"hook_event_name": "PreToolUse", "cwd": str(tmp_path)}, env)
    assert ev.project_root == project


def test_the_walk_finds_the_root_through_a_git_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / ".git").mkdir()
    (tmp_path / "a" / "b").mkdir(parents=True)
    monkeypatch.setattr("stayfixed.gitenv._git_toplevel", _forbidden)
    ev = read_event({"hook_event_name": "PreToolUse", "cwd": str(tmp_path / "a" / "b")}, {})
    assert ev.project_root == tmp_path


def test_the_walk_finds_the_root_through_a_git_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A worktree and a submodule carry `.git` as a file, so `is_dir()` would miss both.
    (tmp_path / ".git").write_text("gitdir: /elsewhere/.git/worktrees/w\n", encoding="utf-8")
    (tmp_path / "a").mkdir()
    monkeypatch.setattr("stayfixed.gitenv._git_toplevel", _forbidden)
    ev = read_event({"hook_event_name": "PreToolUse", "cwd": str(tmp_path / "a")}, {})
    assert ev.project_root == tmp_path


def test_the_walk_finds_the_root_above_a_directory_too_deep_to_name_its_dot_git(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Within a few characters of the longest path, `<cwd>/.git` is past it. `Path.exists()` raised
    # on that up to Python 3.13 and answered `False` from 3.14, so under Codex, where `cwd` is the
    # payload's, every hook in such a directory was an internal error on one interpreter and
    # `PreToolUse` refused every tool call. The walk reads it as no `.git` there on every
    # interpreter and goes on to the parents. Mutations (oracle): `mutations/`'s "the path
    # predicates read a name longer than the system takes as a fault" reddens this on every
    # interpreter; "the hook's walk for .git asks pathlib what is there" reddens it up to 3.13.
    (tmp_path / ".git").mkdir()
    longest = os.pathconf(tmp_path, "PC_PATH_MAX")
    deep = tmp_path
    # Each step adds a separator and at least one character, so the loop ends whatever length
    # `tmp_path` starts at. One character short of the mark, a step of none left `deep` where it
    # was, and a 72-character `tmp_path` under Linux's 4096 met that and hung.
    while len(str(deep)) < longest - 3:
        deep = deep / ("d" * max(1, min(200, longest - 4 - len(str(deep)))))
    deep.mkdir(parents=True)
    # The premise: the path to its `.git` is one no `stat` can be handed.
    with pytest.raises(OSError) as past:
        os.stat(deep / ".git")
    assert past.value.errno == errno.ENAMETOOLONG
    monkeypatch.setattr("stayfixed.gitenv._git_toplevel", _forbidden)
    ev = read_event({"hook_event_name": "PreToolUse", "cwd": str(deep)}, {})
    assert ev.project_root == tmp_path


def test_the_walk_resolves_a_symlinked_root_the_way_git_does(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # git resolves a symlink in `cwd` before reporting the toplevel; a walk that returns the
    # unresolved directory it stopped at would report a different `project_root` for the same
    # repository depending on whether it was reached through the real path or a symlink to it.
    real_repo = tmp_path / "realrepo"
    (real_repo / ".git").mkdir(parents=True)
    (real_repo / "sub").mkdir()
    link = tmp_path / "link"
    link.symlink_to(real_repo)
    monkeypatch.setattr("stayfixed.gitenv._git_toplevel", _forbidden)
    ev = read_event({"hook_event_name": "PreToolUse", "cwd": str(link / "sub")}, {})
    assert ev.project_root == real_repo.resolve()


def test_git_is_still_asked_when_the_walk_finds_no_dot_git(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    asked: list[Path] = []

    def fake(cwd: Path) -> Path | None:
        asked.append(cwd)
        return Path("/from-git")

    monkeypatch.setattr("stayfixed.gitenv._git_toplevel", fake)
    ev = read_event({"hook_event_name": "PreToolUse", "cwd": str(tmp_path)}, {})
    assert ev.project_root == Path("/from-git")
    assert asked == [tmp_path]


def test_an_inherited_git_dir_never_reaches_the_hook_paths_git(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The memory store's git helper scrubbed and said why — "it must be a real git answer, not one
    # an inherited `GIT_DIR` produced" — while this one passed no `env=` at all. The checkout root
    # feeds *every* hook decision, so an inherited `GIT_DIR` or `GIT_WORK_TREE` made every
    # handler in the process answer for a different repository than the session is in.
    #
    # `_git_toplevel` directly, and a `cwd` with no `.git` above it: `checkout_root` tries
    # `_walk_to_git_root` first and would find the answer without ever asking `git`.
    import shutil

    if shutil.which("git") is None:
        pytest.skip("git is not installed")

    victim = tmp_path / "victim"
    victim.mkdir()
    git(victim, "init", "-q", "-b", "main")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()

    monkeypatch.setenv("GIT_DIR", str(victim / ".git"))
    monkeypatch.setenv("GIT_WORK_TREE", str(victim))
    assert _git_toplevel(elsewhere) is None


# --- the harness a hook answers through ---------------------------------------------------------
#
# Every harness's payload is read by `read_event` the same way whichever value was detected, and
# the detected value contributes the shape of its stdout to the answer and nothing to the event.
# These tests hold both halves: a handler sees one event under every answer, the value detection
# chose is the one that renders, a deny reaches no value at all, and the clamp measures the
# envelope that is actually emitted.

# Every variable either harness sets, so a test of detection is not answered by the environment
# the suite happens to run in.
HARNESS_VARIABLES = (
    "PLUGIN_ROOT",
    "PLUGIN_DATA",
    "CLAUDE_PLUGIN_ROOT",
    "CLAUDE_PLUGIN_DATA",
    "CLAUDE_PROJECT_DIR",
)


def _harness(
    render: Callable[[str, str], str],
    *,
    detects: Callable[[Mapping[str, str], Mapping[str, Any] | None], bool] | None = None,
    project_dir_env: str | None = None,
) -> Harness:
    return Harness(
        name="fake",
        marker_dir=".fake",
        settings=(),
        local_settings=(),
        project_dir_env=project_dir_env,
        render=render,
        reach=CLAUDE.reach,
        detects=detects,
    )


def _hook(
    monkeypatch: pytest.MonkeyPatch,
    event_name: str,
    payload: dict[str, object],
    probe: Handler,
    *,
    env: Mapping[str, str] | None = None,
) -> int:
    """`run_hook` in this process, with `probe` as the only handler and no harness variable but
    the ones `env` sets."""
    for variable in HARNESS_VARIABLES:
        monkeypatch.delenv(variable, raising=False)
    for variable, value in (env or {}).items():
        monkeypatch.setenv(variable, value)
    monkeypatch.setattr("stayfixed.hooks.commands.discover", lambda: [probe])
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
    return run_hook(argparse.Namespace(event=event_name))


def test_a_detected_harness_renders_its_own_answer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # A harness whose output differs is a value of its own, registered beside the others, and
    # the hook answers through the value detection chose. The handler sees the same event it
    # would under any harness, with the root from the first project-root variable set, the
    # canonical harness's asked first; here only the fake's own is set. Mutation (declared, on
    # `hooks.dispatch`): `dispatch` renders with `CANONICAL` instead of the detected harness ->
    # stdout is Claude Code's JSON and this reddens.
    fake = _harness(
        lambda name, context: f"fake:{name}:{context}",
        detects=lambda env, payload: payload is not None and "fake_session" in payload,
        project_dir_env="FAKE_PROJECT_DIR",
    )
    monkeypatch.setattr("stayfixed.harnesses.HARNESSES", (fake, *HARNESSES))
    monkeypatch.setenv("FAKE_PROJECT_DIR", str(tmp_path))
    seen: list[Path | None] = []

    def note(ev: HookEvent, config: object) -> HookResult:
        seen.append(ev.project_root)
        return HookResult(context="a note")

    probe = Handler(name="probe", event="SessionStart", policy=Policy.OPEN, run=note)
    payload: dict[str, object] = {"fake_session": "x", "cwd": str(tmp_path)}
    assert _hook(monkeypatch, "SessionStart", payload, probe) == 0
    assert capsys.readouterr().out == "fake:SessionStart:a note"
    assert seen == [tmp_path]


def test_a_handler_sees_one_event_whichever_harness_is_detected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The harness a process detects is one a repository can choose (a committed `env` block can
    # set `PLUGIN_ROOT`), so nothing a handler sees may depend on it: the same stdin and the same
    # project-root variable make the same event under Claude Code, under Codex and under a value
    # registered first, and the root is the one `CLAUDE_PROJECT_DIR` names in each, never the
    # checkout `cwd` sits in. Each run records the harness `dispatch` was handed, so the three
    # steers are known to have reached three harnesses rather than Claude Code three times.
    # Mutations (declared, on `hooks.commands`): the event is read with no environment under a
    # harness that names no root variable -> the Codex event's root is the other checkout and
    # this reddens; detection is asked with neither environment nor payload -> every run is
    # Claude Code's and this reddens.
    project = tmp_path / "project"
    project.mkdir()
    other = tmp_path / "other"
    (other / ".git").mkdir(parents=True)
    fake = _harness(
        lambda name, context: context, detects=lambda env, payload: "FAKE_HARNESS" in env
    )
    monkeypatch.setattr("stayfixed.harnesses.HARNESSES", (fake, *HARNESSES))
    monkeypatch.setattr("stayfixed.gitenv._git_toplevel", _forbidden)
    seen: list[HookEvent] = []
    detected: list[str] = []

    def answered(*args: Any, harness: Harness, **kwargs: Any) -> Any:
        detected.append(harness.name)
        return dispatch(*args, harness=harness, **kwargs)

    monkeypatch.setattr("stayfixed.hooks.commands.dispatch", answered)

    def note(ev: HookEvent, config: object) -> HookResult:
        seen.append(ev)
        return HookResult()

    probe = Handler(name="probe", event="PreToolUse", policy=Policy.OPEN, run=note)
    payload: dict[str, object] = {"cwd": str(other), "session_id": "s", "tool_name": "Bash"}
    for steer in ({}, {"PLUGIN_ROOT": "/r"}, {"FAKE_HARNESS": "1"}):
        monkeypatch.delenv("FAKE_HARNESS", raising=False)
        env = {**steer, "CLAUDE_PROJECT_DIR": str(project)}
        assert _hook(monkeypatch, "PreToolUse", payload, probe, env=env) == 0
    assert detected == ["claude", "codex", "fake"]
    assert [ev.project_root for ev in seen] == [project] * 3
    assert seen[0] == seen[1] == seen[2]


def test_an_unknown_harness_renders_the_canonical_shape(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # No harness variable and no field only Codex sends: detection still answers, with Claude
    # Code's schema, which other harnesses imitate. Pinned as the bytes a harness reads rather
    # than compared with `CANONICAL.render`, which would agree with whatever it was changed to.
    # Mutation (by hand): the canonical render's `additionalContext` misspelled -> reddens.
    (tmp_path / ".git").mkdir()
    probe = Handler(
        name="probe",
        event="PreToolUse",
        policy=Policy.OPEN,
        run=lambda ev, config: HookResult(context="a note"),
    )
    payload: dict[str, object] = {"cwd": str(tmp_path), "tool_name": "Bash"}
    assert _hook(monkeypatch, "PreToolUse", payload, probe) == 0
    assert capsys.readouterr().out == (
        '{"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": "a note"}}'
    )


def test_a_deny_never_goes_through_render() -> None:
    # A refusal is complete as exit 2 with its reason on stderr for every harness, and JSON is an
    # enhancement of an answer that lets the call through. So no harness value is asked to shape
    # a deny, and one whose rendering fails cannot cost the refusal or turn it into an internal
    # error. Mutation (declared, on `hooks.dispatch`): the refusal's stdout rendered through
    # `harness.render` -> the render raises out of `dispatch` and this reddens.
    def broken(name: str, context: str) -> str:
        raise AssertionError("a deny reached render")

    handlers = [
        handler("a-note", Policy.OPEN, HookResult(context="a note")),
        handler("probe", Policy.OPEN, HookResult(decision=Decision.DENY, reason="rm is refused")),
    ]
    outcome = dispatch(
        event(), handlers, None, harness=_harness(broken), sink=Recorder(), cap=10000
    )
    assert (outcome.exit_code, outcome.stdout) == (2, "")
    assert outcome.stderr == "stayfixed: refused: probe: rm is refused\n"
    assert "internal error" not in outcome.stderr


def test_a_clamped_answer_is_the_detected_harnesss_envelope() -> None:
    # The cap bounds the string the harness reads, so the largest prefix that fits is searched
    # for in the detected harness's own envelope; one measured against Claude Code's would be the
    # wrong width for any other. Mutation (declared, on `hooks.dispatch`): the clamp handed
    # `CANONICAL.render` -> the clamped stdout is Claude Code's JSON and this reddens.
    def wide(name: str, context: str) -> str:
        return json.dumps({"an-envelope-of-another-width": {"event": name, "text": context}})

    handlers = [handler("a", Policy.OPEN, HookResult(context="y" * 500))]
    recorder = Recorder()
    outcome = dispatch(event(), handlers, None, harness=_harness(wide), sink=recorder, cap=200)
    assert len(outcome.stdout) == 200
    text = json.loads(outcome.stdout)["an-envelope-of-another-width"]["text"]
    assert text == "y" * (len(text) - len(TRUNCATION_MARK)) + TRUNCATION_MARK
    assert recorder.records == [
        {"event": "PreToolUse", "handler": "*", "error": "context-truncated"}
    ]


def test_a_user_the_password_database_does_not_list_still_gets_an_answer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A container run under a uid with no entry has no home off a terminal, so no machine file:
    # the configuration loads with the preset's `[personal]` and the guards still answer. Read as
    # an error instead, a `closed` entry would refuse every tool call on such a machine.
    as_owner_home(monkeypatch, None)
    (tmp_path / ".git").mkdir()
    (tmp_path / "stayfixed.toml").write_text(
        '[stayfixed]\nversion = "0.1.0"\nstate = "installed"\n\n'
        '[project]\nname = "widget"\n\n[memory]\nmode = "local-only"\n',
        encoding="utf-8",
    )
    seen: list[object] = []

    def note(ev: HookEvent, config: object) -> HookResult:
        seen.append(config)
        return HookResult()

    probe = Handler(name="probe", event="PreToolUse", policy=Policy.CLOSED, run=note)
    payload: dict[str, object] = {"cwd": str(tmp_path), "tool_name": "Bash"}
    assert _hook(monkeypatch, "PreToolUse", payload, probe, env={"HOME": str(tmp_path)}) == 0
    assert len(seen) == 1 and seen[0] is not None
