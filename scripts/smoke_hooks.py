#!/usr/bin/env python3
"""Feed every `hooks/hooks.json` entry the event it is filed under, through the wrapper.

    python3 scripts/smoke_hooks.py --plugin-root R --fixture F --scratch S

`R` is a plugin root — the checkout, or the copy the harness installed. One row per
entry and sample; exit 1 on any row whose exit code, stderr or stdout shape is not the one
the policy and the dispatcher's contract require.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

PLACEHOLDER = "${CLAUDE_PLUGIN_ROOT}"
# The wrapper's own fault tokens all begin with this, and every one of them is a report about
# the launcher rather than an answer from the dispatcher. A refusal that carries one is not a
# refusal the guard made.
FAULT = "SF_"
DELIMITER = "<<<stayfixed:repository-data"
# What `tests/fixtures/smoke-project`'s own store puts in front of the model, one marker per
# bundle that renders anything on it.
STANDING_RULE = "SMOKE-STANDING-RULE"
VOLATILE_NOTE = "SMOKE-VOLATILE-NOTE"
# The one `STAYFIXED_*` variable an entry keeps: the floor a test runner puts under the product's
# own bounds on `git` (`stayfixed.gitenv.FLOOR_VARIABLE`, which can only raise them). Spelled out
# rather than imported, because this script runs without `stayfixed` importable.
FLOOR_VARIABLE = "STAYFIXED_GIT_FLOOR_SECONDS"
# Counted against the shipped `hooks/hooks.json` and this fixture: nine entries, ten rows
# (`PreToolUse` carries two samples). Both are asserted because a run that executes fewer rows
# prints an identically green summary — the shape `unsampled` and `unentered` close for events
# and nothing closed for rows.
EXPECTED_ENTRIES = 9
EXPECTED_ROWS = 10


@dataclass(frozen=True)
class Sample:
    payload: dict[str, object]
    expected_code: int
    stderr_required: bool
    label: str
    # What the stderr must and must not say, because the exit code cannot tell a genuine deny
    # from a launcher fault. `hooks/run-hook.sh` maps a launcher `rc=1` under the `closed`
    # policy to exit 2 with a `SF_` token on stderr, which satisfies `expected_code=2` and
    # `stderr_required=True` byte for byte. Measured 2026-09-19: a three-line
    # `scripts/stayfixed` that writes to stderr and raises `SystemExit(1)` left the row that
    # proves the guard denies GREEN, along with twelve of the other thirteen.
    stderr_says: tuple[str, ...] = ()
    stderr_never: tuple[str, ...] = ()


SAMPLES: dict[str, tuple[Sample, ...]] = {
    "SessionStart": (Sample({"source": "startup"}, 0, False, "a session starts"),),
    "PreToolUse": (
        Sample(
            {
                "tool_name": "Bash",
                "tool_input": {"command": "sleep 300 & wait", "run_in_background": True},
            },
            2,
            True,
            "a leaking background command is refused with a reason",
            stderr_says=("refused: bg-cleanup", "backgrounded"),
            stderr_never=(FAULT,),
        ),
        Sample(
            {"tool_name": "Bash", "tool_input": {"command": "ls"}},
            0,
            False,
            "an ordinary command is allowed",
            stderr_never=(FAULT,),
        ),
    ),
    "PostToolUse": (
        Sample(
            {
                "tool_name": "Bash",
                "tool_input": {"command": "uv run pytest -q"},
                "tool_response": {"exit_code": 1},
            },
            0,
            False,
            "a failed test run is annotated, never blocked",
            stderr_never=(FAULT,),
        ),
    ),
}

# What each `memory session-context` entry must have put in front of the model, by the part of
# its command after the wrapper. An empty tuple is the other claim and not an absence: that
# part renders nothing on this fixture, so anything at all in its stdout is a finding.
#
# **Why this registry exists.** Before it, every one of these rows ran against a project with no
# memory store: `stayfixed` answered "no memory store", the wrapper degraded that to 0 under the
# `open` policy, and each row asserted an exit code it would have had if `session-context` were
# `/bin/false`. Measured 2026-09-19 on the storeless fixture: ten rows, 0 bytes of stdout, all
# green. These are the entries that carry repository bytes toward the model, which is the one
# thing the smoke scenario exists to watch.
#
# Measured 2026-09-19 against the fixture's store, trusted: standing-rules part 1 1,010,
# volatile-notes part 1 993, every other part empty — so the second and third part of each
# bundle assert that a store which fits one part says nothing in the slots after it.
INJECTED: dict[str, tuple[str, ...]] = {
    "open memory session-context --bundle standing-rules --part 1": (DELIMITER, STANDING_RULE),
    "open memory session-context --bundle standing-rules --part 2": (),
    "open memory session-context --bundle standing-rules --part 3": (),
    "open memory session-context --bundle volatile-notes --part 1": (DELIMITER, VOLATILE_NOTE),
    "open memory session-context --bundle volatile-notes --part 2": (),
    "open memory session-context --bundle volatile-notes --part 3": (),
}


def tail_of(command: str) -> str:
    """The part of a `hooks.json` command after the wrapper — what the entry actually asks."""
    return command.split("run-hook.sh")[-1].strip().lstrip('" ')


def entries(plugin_root: Path) -> list[tuple[str, str]]:
    document = json.loads((plugin_root / "hooks" / "hooks.json").read_text(encoding="utf-8"))
    return [
        (event, entry["command"])
        for event, groups in document["hooks"].items()
        for group in groups
        for entry in group["hooks"]
    ]


def fixture_repository(fixture: Path, into: Path) -> Path:
    """A copy of the fixture as a committed repository, which is what the wrapper resolves."""
    shutil.copytree(fixture, into)
    env = {
        "PATH": "/usr/bin:/bin",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_SYSTEM": os.devnull,
    }
    for args in (
        ["init", "-q", "-b", "main"],
        ["add", "-A"],
        ["-c", "user.email=a@b.c", "-c", "user.name=a", "commit", "-qm", "fixture"],
    ):
        subprocess.run(["git", "-C", str(into), *args], check=True, capture_output=True, env=env)  # noqa: S603, S607
    return into


def developer_free_env() -> dict[str, str]:
    """This process's environment with this developer's own harness and stayfixed stripped out,
    and the floor a test runner set kept: the base both smoke scripts build a session on.
    """
    return {
        k: v
        for k, v in os.environ.items()
        if k == FLOOR_VARIABLE or not k.startswith(("STAYFIXED_", "XDG_", "CLAUDE_", "PLUGIN_"))
    }


def session_env(*, plugin_root: Path, project: Path, home: Path, data: Path) -> dict[str, str]:
    """The environment a hook entry meets, with this developer's own stayfixed stripped out."""
    env = developer_free_env()
    env.update(
        {
            "HOME": str(home),
            "CLAUDE_PLUGIN_ROOT": str(plugin_root),
            "CLAUDE_PROJECT_DIR": str(project),
            "CLAUDE_PLUGIN_DATA": str(data),
        }
    )
    return env


def trust_the_store(plugin_root: Path, project: Path, env: dict[str, str]) -> str | None:
    """Record the owner's trust for the fixture's own store, before any row runs.

    The store is repository data and nothing reaches the model out of it until somebody says
    so — which is the boundary these entries exist to exercise, and it cannot be exercised
    from the outside of it. The owner's own act is performed here, once, the way
    `smoke_exfiltration.py`'s positive control performs it, and the rows below then assert
    what came through. A failure here is a failure of the run, not a row: the six injection
    rows after it would go green on empty output.
    """
    done = subprocess.run(  # noqa: S603
        [
            sys.executable,
            str(plugin_root / "scripts" / "stayfixed"),
            "memory",
            "trust",
            "--in-repo-memory",
            "--root",
            str(project),
        ],
        input="",
        capture_output=True,
        text=True,
        check=False,
        cwd=project,
        env=env,
    )
    if done.returncode != 0:
        return (
            f"could not record trust for the fixture's store, so the injection rows would "
            f"prove nothing: rc={done.returncode}, stderr={done.stderr.strip()[:200]}"
        )
    return None


def check_entry(
    event: str,
    command: str,
    sample: Sample,
    *,
    plugin_root: Path,
    project: Path,
    home: Path,
    data: Path,
) -> str | None:
    argv = shlex.split(command.replace(PLACEHOLDER, str(plugin_root)))
    env = session_env(plugin_root=plugin_root, project=project, home=home, data=data)
    payload = {
        "session_id": "smoke",
        "cwd": str(project),
        "hook_event_name": event,
        **sample.payload,
    }
    done = subprocess.run(  # noqa: S603
        argv,
        input=json.dumps(payload),
        cwd=project,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    if done.returncode != sample.expected_code:
        return (
            f"exited {done.returncode}, expected {sample.expected_code}; "
            f"stderr: {done.stderr.strip()[:200]}"
        )
    if sample.stderr_required and not done.stderr.strip():
        return "refused with no reason on stderr"
    # The reason itself, and not merely that there was one. Without these two clauses the
    # security-bearing row cannot tell a deny the dispatcher made from any launcher fault at
    # all — a missing interpreter, an import error, a syntax error in a handler — because the
    # wrapper reports every one of them as exit 2 with something on stderr under `closed`.
    for phrase in sample.stderr_says:
        if phrase not in done.stderr:
            return f"stderr does not say {phrase!r}: {done.stderr.strip()[:200]}"
    for phrase in sample.stderr_never:
        if phrase in done.stderr:
            return f"stderr carries the launcher token {phrase!r}: {done.stderr.strip()[:200]}"
    wanted = INJECTED.get(tail_of(command))
    if wanted is not None:
        for phrase in wanted:
            if phrase not in done.stdout:
                return f"injected nothing carrying {phrase!r} ({len(done.stdout)} characters)"
        if not wanted and done.stdout.strip():
            return f"this part renders nothing on the fixture, yet emitted {len(done.stdout)}"
    # Only the dispatcher's own entries (`… hook <event>`) speak JSON; the six
    # `memory session-context` entries print a bundle as prose, which is how they inject it.
    if "hook" in argv and done.stdout.strip():
        try:
            emitted = json.loads(done.stdout)
        except json.JSONDecodeError:
            return "stdout is not JSON"
        if emitted.get("hookSpecificOutput", {}).get("hookEventName") != event:
            named = emitted.get("hookSpecificOutput", {}).get("hookEventName")
            return f"stdout names {named!r}, not {event!r}"
    return None


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ("--plugin-root", "--fixture", "--scratch"):
        parser.add_argument(flag, required=True, type=Path)
    args = parser.parse_args(argv)
    # Resolved, because every subprocess below runs with `cwd=project`: a relative plugin root
    # would be looked for inside the fixture, which is the one tree it is never in.
    args.plugin_root = args.plugin_root.resolve()
    args.fixture = args.fixture.resolve()
    args.scratch = args.scratch.resolve()
    project = fixture_repository(args.fixture, args.scratch / "project")
    home, data = args.scratch / "home", args.scratch / "data"
    home.mkdir(parents=True, exist_ok=True)
    data.mkdir(parents=True, exist_ok=True)
    wrapper = args.plugin_root / "hooks" / "run-hook.sh"
    failures = 0
    if not os.access(wrapper, os.X_OK):
        print(f"FAIL  {wrapper} is not executable")
        failures += 1
    found = entries(args.plugin_root)
    if not found:
        print("FAIL  no hook entries at all")
        return 1
    # An event with no sample would contribute zero rows and a green summary — the vacuous
    # shape this repository names; a sixth event fails here until it has a sample.
    events = {event for event, _ in found}
    unsampled = events - SAMPLES.keys()
    if unsampled:
        print(f"FAIL  no sample event for {sorted(unsampled)}")
        return 1
    # And the converse, which is the direction that fails silently. The check above catches
    # `hooks.json` GAINING an event; `hooks.json` LOSING one shrinks `found`, empties
    # `unsampled`, runs fewer rows and prints a green summary — the entry stopped being
    # tested and nothing said so. Both directions, so the set of events this run covers is
    # exactly the set the samples describe.
    unentered = SAMPLES.keys() - events
    if unentered:
        print(f"FAIL  no hook entry for {sorted(unentered)}; hooks.json lost an event")
        return 1
    # The same two directions for the entries that inject. An injection entry with no registry
    # line would be checked for its exit code alone, which is what every one of them was;
    # a registry line with no entry means `hooks.json` dropped a bundle and the run would
    # simply stop testing it.
    injecting = {tail_of(command) for _, command in found if "session-context" in command}
    unregistered = injecting - INJECTED.keys()
    if unregistered:
        print(f"FAIL  no injection registered for {sorted(unregistered)}")
        return 1
    ungathered = INJECTED.keys() - injecting
    if ungathered:
        print(f"FAIL  no hook entry for {sorted(ungathered)}; hooks.json lost a bundle")
        return 1
    untrusted = trust_the_store(
        args.plugin_root,
        project,
        session_env(plugin_root=args.plugin_root, project=project, home=home, data=data),
    )
    if untrusted:
        print(f"FAIL  {untrusted}")
        return 1
    rows = 0
    for event, command in found:
        for sample in SAMPLES.get(event, ()):
            problem = check_entry(
                event,
                command,
                sample,
                plugin_root=args.plugin_root,
                project=project,
                home=home,
                data=data,
            )
            rows += 1
            mark = "ok  " if problem is None else "FAIL"
            why = f" -> {problem}" if problem else ""
            print(f"{mark}  {event:<13} {sample.label}: {tail_of(command)}{why}")
            failures += problem is not None
    # The floor, in both quantities, and after the rows so the summary reports it. A run that
    # executed fewer rows prints the same green last line as a run that executed all of them,
    # which is how a report proves less than it claims without anybody reading it wrong.
    if (len(found), rows) != (EXPECTED_ENTRIES, EXPECTED_ROWS):
        print(
            f"FAIL  {len(found)} entries and {rows} rows, expected "
            f"{EXPECTED_ENTRIES} and {EXPECTED_ROWS}"
        )
        failures += 1
    print(f"{len(found)} entries, {rows} row(s), {failures} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
