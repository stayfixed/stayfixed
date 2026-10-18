"""Handlers this area contributes; the `hook <event>` entries in `hooks/hooks.json` invoke them.

Every import of `stayfixed.guards.*` and of the configuration layer happens **inside** a
handler body. `tests/boundaries/test_discovery.py` asserts that `discover()` in a clean
interpreter imports neither the configuration layer nor the presets, and discovery imports every
area's `hooks` module — so a module-level import here reddens a test that belongs to no area at
all.

`bg-cleanup` and `env-reads` are the plugin's `Policy.CLOSED` handlers. Neither catches its own
exceptions: a guard for an action with a high cost of error fails closed (principle 6), and the
dispatcher is what turns an exception from a CLOSED handler into exit 2 with a reason. `judge` and
`is_env_file` return rather than raise on any string, so what reaches that policy is a genuine
defect, not an unusual call.

**`env-reads` is closed in the dispatcher and open in the wrapper**, and that split is chosen. Its
entry in `hooks/hooks.json` is an `open` one matched on the file tools, so a wrapper that cannot
start Python lets a read through rather than refusing every file the session opens; the preset's
deny rules (`[deny] global`) still refuse the env files by their common names, which is what they
are there for. A handler that raises is still a deny.

Nothing a repository controls is put into `HookResult.context`. The restore hint is built from
the command's own text — model- or user-authored, never repository bytes — and the hygiene
notice carries counts and fixed sentences, its own and those a shipped profile's hint renders
from its counts, never a path from `stayfixed.toml`.

The guard judges with any configuration and none: a repository with no `stayfixed.toml`, or one
that does not load, is guarded as one that loads, because the guard reads nothing of it, and a
configuration that could not be read is no reason to let a call through. Only the machine owner
switches it off, in the machine file (`config.owner`); a repository never can. The hygiene note is
about the project and is silent without its configuration.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from stayfixed.hooks.api import Decision, Handler, HookEvent, HookResult, Policy

if TYPE_CHECKING:
    from stayfixed.config.session import SessionConfig

# The matcher both handlers share. Codex reports every shell-routed action as `Bash` too, as the
# spike record (`docs/plans/2026-09-05-agent-harness-p0-spikes.md`) measured in its *Codex plugin
# hooks* trial, so this one name serves both harnesses.
BASH = "Bash"

# The file tools `env-reads` judges, and the matcher of its entry in `hooks/hooks.json`: Claude
# Code's names. `Read` opens one file; `Grep` prints the lines of the file its `path` names. Codex
# reports a file read as a `Bash` call, which this guard does not parse, so it judges nothing there.
READ = "Read"
GREP = "Grep"
FILE_TOOLS = f"{READ}|{GREP}"

# What `env-reads` refuses with. Fixed words, never the path: the path names a file the repository
# chose, and the model that asked for it already has it.
ENV_READ_REFUSED = (
    "an env file may hold credentials, so stayfixed keeps it from the agent; its template "
    "(`.env.example`, `.env.sample` or `.env.template`) stays readable. The machine owner switches "
    "this guard off with `env_reads = false` under `[guards]` in the machine file"
)

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


def _bg_cleanup(event: HookEvent, session: SessionConfig) -> HookResult:
    """Judge a Bash call whatever the project's configuration, and none at all included: the guard
    reads nothing of it. The machine owner alone switches it off (`config.owner`)."""
    if not session.owner.guards.bg_cleanup:
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


def file_read_path(event: HookEvent) -> str | None:
    """The path a file tool names, or None for any other tool, no path, or a malformed input.

    `Read` names its file in `file_path` and `Grep` its file or directory in `path`; a `Grep` with
    no `path` searches the working directory, which this guard does not judge, and the preset's
    deny rules are what keep a search there out of the env files they name.
    """
    if event.tool_name == READ:
        key = "file_path"
    elif event.tool_name == GREP:
        key = "path"
    else:
        return None
    path = event.tool_input.get(key)
    return path if isinstance(path, str) else None


def _env_reads(event: HookEvent, session: SessionConfig) -> HookResult:
    """Refuse a file tool that names an env file, whatever the project's configuration, and none
    at all included. The machine owner alone switches it off (`config.owner`)."""
    if not session.owner.guards.env_reads:
        return HookResult()
    path = file_read_path(event)
    if path is None:
        return HookResult()
    import contextlib
    import os

    from stayfixed import fsops
    from stayfixed.envfiles import is_env_file

    # The last component, split on both separators: a Windows path reaches this on a POSIX parser
    # too, and `PurePosixPath` would read `C:\app\.env` as one name.
    names = [path.replace("\\", "/").rstrip("/").rpartition("/")[2]]
    # And the name it resolves to: a clone can commit `notes.txt` as a link to `.env.local`, and
    # the tool reads the file the link names. A path that cannot be resolved -- a loop, a NUL --
    # is judged by its own name alone, and the tool cannot read it either. A leading `~` is
    # expanded first, as the tool expands it, or `~/notes.txt` would be resolved under the
    # working directory, where nothing is, and the link it names would go unread.
    with contextlib.suppress(OSError, ValueError):
        names.append(fsops.resolved(event.cwd / os.path.expanduser(path)).name)
    if any(is_env_file(name) for name in names):
        return HookResult(decision=Decision.DENY, reason=ENV_READ_REFUSED)
    return HookResult()


def _test_hygiene(event: HookEvent, session: SessionConfig) -> HookResult:
    """Name what could have falsified a red test run, in the words of the profile whose runner
    failed. Never a decision: the tool has already run, and `Policy.OPEN` means a failure here
    costs the note and not the call. About the project, so silent without its configuration."""
    config = session.config
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
        Handler(name="env-reads", event="PreToolUse", policy=Policy.CLOSED, run=_env_reads),
        # The red-run note, on both events a failed command can arrive on. Claude Code delivers a
        # Bash command that exited non-zero to `PostToolUseFailure`, with `error` beginning
        # `Exit code N`, and never to `PostToolUse`. No measured harness delivers an exit code on
        # `PostToolUse`: Codex delivers a failed command there with none, so the note does not
        # speak (`red_exit` answers `None`). The registration is a placeholder for parity with
        # Codex. One `once_key`, which the dispatcher files per session: at most one
        # note per context, whichever event carries it.
        # Kept ABOVE the rows it annotates, not below them: a later change appending a handler to
        # the tail of this list would otherwise detach the comment from its subject.
        Handler(
            name="test-hygiene",
            event="PostToolUse",
            policy=Policy.OPEN,
            run=_test_hygiene,
            once_key=ONCE_TEST_HYGIENE,
        ),
        Handler(
            name="test-hygiene",
            event="PostToolUseFailure",
            policy=Policy.OPEN,
            run=_test_hygiene,
            once_key=ONCE_TEST_HYGIENE,
        ),
    ]
