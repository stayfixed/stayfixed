"""Handlers this area contributes; the `hook <event>` entries in `hooks/hooks.json` invoke them.

Every import of `stayfixed.guards.*` and of the configuration layer happens **inside** a
handler body. `tests/test_areas.py` asserts that `discover()` in a clean interpreter imports
neither the configuration layer nor the presets, and discovery imports every area's `hooks`
module — so a module-level import here reddens a test that belongs to no area at all.

`bg-cleanup` is the one `Policy.CLOSED` handler in the plugin. It does not catch its own exceptions:
a guard for an action with a high cost of error fails closed (principle 6), and the dispatcher is
what turns an exception from a CLOSED handler into exit 2 with a reason. `judge` itself returns
rather than raises on any string, so what reaches that policy is a genuine defect, not an unusual
command.

Nothing a repository controls is put into `HookResult.context`. The restore hint is built from
the command's own text — model- or user-authored, never repository bytes — and the hygiene
notice carries counts and fixed sentences, its own and those a shipped profile's hint renders
from its counts, never a path from `stayfixed.toml`.

Both handlers are silent without a configuration: with no `stayfixed.toml`, no hook handler says
anything. For the guard that is a design decision, not a degradation: a repository that has not run
`stayfixed init` is not guarded.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from stayfixed.hooks.api import Decision, Handler, HookEvent, HookResult, Policy

if TYPE_CHECKING:
    from stayfixed.config.schema import Config

# The matcher both handlers share. Codex reports every shell-routed action as `Bash` too, as the
# spike record (`docs/plans/2026-09-05-agent-harness-p0-spikes.md`) measured in its *Codex plugin
# hooks* trial, so this one name serves both harnesses.
BASH = "Bash"

# The dispatcher owns the once-per-context bookkeeping, so the handler declares the key
# and stays pure. A red test run over a dirty tree is the normal state of TDD — every "run it to
# watch it fail" step would otherwise carry the same paragraph — so the note is worth one
# appearance and no more.
ONCE_TEST_HYGIENE = "test-hygiene"


def bash_command(event: HookEvent) -> str | None:
    """The command of a Bash call, or None for any other tool or a malformed input.

    A `command` that is present but not a string is allowed here and **refused** by
    `guard bg-cleanup` on the CLI, and that divergence is chosen rather than an omission. The
    CLI is the documented fail-closed row: its input is a file or a pipe somebody composed, and
    a shape it cannot read is a shape it must not guess at. This handler reads what the harness
    sends, and the harness never sends a non-string `command`; under `Policy.CLOSED` a `None`
    returned here is silence, while raising would deny a real Bash call on the strength of a
    payload shape nothing produces. Both surfaces agree on every input either actually sees.
    """
    if event.tool_name != BASH:
        return None
    command = event.tool_input.get("command")
    return command if isinstance(command, str) else None


def _bg_cleanup(event: HookEvent, config: Config | None) -> HookResult:
    if config is None:
        return HookResult()
    command = bash_command(event)
    if command is None:
        return HookResult()
    from stayfixed.guards.bgcleanup import judge

    background = event.tool_input.get("run_in_background") is True
    verdict = judge(command, background=background)
    if verdict.deny is not None:
        return HookResult(decision=Decision.DENY, reason=verdict.deny)
    return HookResult(context=verdict.hint)


def _test_hygiene(event: HookEvent, config: Config | None) -> HookResult:
    """Name what could have falsified a red test run, in the words of the profile whose runner
    failed. Never a decision: the tool has already run, and `Policy.OPEN` means a failure here
    costs the note and not the call."""
    if config is None or event.project_root is None:
        return HookResult()
    command = bash_command(event)
    if command is None:
        return HookResult()
    from stayfixed.guards.hygiene import context_for, red_exit

    if red_exit(event.raw) is None:
        return HookResult()
    return HookResult(context=context_for(command, event.project_root, config))


def register() -> list[Handler]:
    return [
        Handler(name="bg-cleanup", event="PreToolUse", policy=Policy.CLOSED, run=_bg_cleanup),
        # Per the Claude Code hooks reference, a non-zero exit arrives on `PostToolUseFailure`,
        # which `stayfixed.hooks.api.EVENTS` does not carry yet — and `registry.discover` refuses a
        # handler whose event is not in that tuple, so registering it here today would take
        # the whole plugin down. `EVENTS` is `stayfixed.hooks`' file. When it gains the
        # event, register the same handler there too:
        # Handler(name="test-hygiene", event="PostToolUseFailure", policy=Policy.OPEN,
        #         run=_test_hygiene, once_key=ONCE_TEST_HYGIENE),
        # Kept ABOVE the row it annotates, not below it: a later change appending a handler to
        # the tail of this list would otherwise detach the comment from its subject.
        Handler(
            name="test-hygiene",
            event="PostToolUse",
            policy=Policy.OPEN,
            run=_test_hygiene,
            once_key=ONCE_TEST_HYGIENE,
        ),
    ]
