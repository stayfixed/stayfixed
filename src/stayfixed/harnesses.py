"""Every harness stayfixed serves, as values in one registry.

A harness is served first by the `AGENTS.md` region, which `project.templates` renders and
every harness that reads the standard sees. Where a harness reads something better natively,
its `render_profile` renders a profile into that form. `settings` names the committed files in
which it reads hook entries, for `stayfixed assess`'s foreign-hooks probe to inventory;
`marker_dir` is the directory whose presence says a repository uses it. A harness is a value,
not a class: adding one is one more value in `HARNESSES`, and nothing that reads the registry
changes.

The registry is also the adapter the hooks core answers through. `stayfixed hook` asks `detect`
which value it is running under, takes the project root from that value's `project_dir_env`
when it names one, and shapes its stdout with that value's `render`. That is all a value
contributes: every payload is read one way (`hooks.dispatch.read_event`), because the harness a
process detects is one a repository can choose — a committed `.claude/settings.json` `env` block
can set `PLUGIN_ROOT` — so no value may change what a handler sees. A deny reaches no value at
all: exit 2 with the reason on stderr is the whole of a refusal for every harness. A new harness
is a value with a positive `detects`, its project-root variable and its `render`; a harness whose
payload genuinely differs is a question to answer with that harness's evidence when it arrives.

Code that needs a harness fact asks this registry. Three modules older than it still spell
their own settings files: `doctor`, `setup` and `attach`. `doctor` walks one no field here
models, the uncommitted `.claude/settings.local.json`, so moving it onto the registry is its
own change.

A name `[stayfixed] agents` lists and no harness answers to is counted, never refused and never
printed: the list is repository-authored, and a project may name a harness a later stayfixed
serves.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from stayfixed.profiles import Profile


@dataclass(frozen=True)
class Rendition:
    """One file a harness reads natively, rendered from a profile."""

    artifact_id: str
    target: str
    render: Callable[[], str]


@dataclass(frozen=True)
class Harness:
    name: str
    marker_dir: str
    settings: tuple[str, ...]
    # The variable this harness names the project root in, if any; the one datum of the
    # payload's reading that differs between harnesses today.
    project_dir_env: str | None
    # How the hook's stdout is shaped: (event name, joined context) -> stdout. Context only:
    # no rendering carries a decision, because a deny travels on the exit code.
    render: Callable[[str, str], str]
    # Positive detection, for every harness but the canonical one, which is the fallback.
    detects: Callable[[Mapping[str, str], Mapping[str, Any] | None], bool] | None = None
    # The profile, and the repository-relative path of its rules file.
    render_profile: Callable[[Profile, str], Rendition] | None = None


def hook_specific_output(event_name: str, context: str) -> str:
    """Claude Code's hook answer: the whole string a hook writes to stdout, which the harness
    caps, rather than the field inside it."""
    payload: dict[str, Any] = {"hookSpecificOutput": {"hookEventName": event_name}}
    if context:
        payload["hookSpecificOutput"]["additionalContext"] = context
    return json.dumps(payload)


def _codex_detects(env: Mapping[str, str], payload: Mapping[str, Any] | None) -> bool:
    """Measured on both harnesses in the *Codex plugin hooks* trial of the spike record
    (`docs/plans/2026-09-05-agent-harness-p0-spikes.md`): Codex sets `PLUGIN_ROOT` and
    `PLUGIN_DATA` and ALSO `CLAUDE_PLUGIN_ROOT`, so Claude Code's names alone identify nothing;
    Codex's `SessionStart` stdin also carries `model` and `permission_mode`, which Claude Code's
    does not."""
    if "PLUGIN_ROOT" in env:
        return True
    return payload is not None and {"model", "permission_mode"} <= set(payload)


CLAUDE_DIR = ".claude"
POINTER = (
    "This repository's `{name}` rules are in `{rules}`; open that file before editing a file "
    "these paths match. It is the one copy, and changes to the rules go there.\n"
)


def _claude_rule(profile: Profile, rules: str) -> Rendition:
    """A path-scoped rule whose body points at the one copy of the rules, and copies nothing.

    `paths:` is the one frontmatter field Claude Code reads in a rules file, and a rule under it
    loads when the session reads a matching file, not on every prompt. The body is one sentence
    rather than the rules themselves: a copy would drift from the file the project edits, and
    an import inside a rules file is not documented behaviour. `stayfixed-` in the file name says
    who owns it and leaves `<profile>.md` free for the project's own rule.
    """
    # `json.dumps` quotes each glob as a YAML double-quoted scalar. The globs are the profile's
    # own and carry `*`, which bare YAML would read as an alias.
    head = "---\npaths:\n" + "".join(f"  - {json.dumps(g)}\n" for g in profile.scope) + "---\n\n"
    body = POINTER.format(name=profile.name, rules=rules)
    return Rendition(
        "claude-rules", f"{CLAUDE_DIR}/rules/stayfixed-{profile.name}.md", lambda: head + body
    )


CLAUDE = Harness(
    name="claude",
    marker_dir=CLAUDE_DIR,
    settings=(f"{CLAUDE_DIR}/settings.json",),
    project_dir_env="CLAUDE_PROJECT_DIR",
    render=hook_specific_output,
    render_profile=_claude_rule,
)
# Codex reads `AGENTS.md` from the root down and no other instruction file, and follows no
# import; `.codex/rules` holds command-execution policy, not instructions. The region is how a
# profile reaches it, and there is nothing further to render.
CODEX = Harness(
    name="codex",
    marker_dir=".codex",
    settings=(".codex/hooks.json",),
    # Codex names no project root; the checkout `cwd` sits in is the one it answers for.
    project_dir_env=None,
    # Claude Code's shape, and unmeasured under Codex: Codex 0.160.0 ran none of the plugin's
    # hooks, with or without its hook-trust bypass flag (the delivery spike of 2026-10-02 in
    # `docs/plans/`). When Codex's answer is found to differ, it gets a `render` of its own here;
    # a harness whose output differs is a different value, never a branch inside a shared one.
    render=hook_specific_output,
    detects=_codex_detects,
)
# Claude Code's hook schema is the de-facto one, which other harnesses imitate, so it answers
# whatever no other value claims and detects nothing of its own.
CANONICAL = CLAUDE
# The order `init` writes into `[stayfixed] agents`.
HARNESSES: tuple[Harness, ...] = (CLAUDE, CODEX)


def registered() -> tuple[Harness, ...]:
    """The values `detect` asks, behind one function so a test can register a value of its own
    without editing the tuple every other reader shares."""
    return HARNESSES


def detect(env: Mapping[str, str], payload: Mapping[str, Any] | None) -> Harness:
    """The first non-canonical harness whose `detects` answers yes, else `CANONICAL`.

    The one answer to "which harness is this process running under": the hooks core asks it
    once, in `stayfixed hook`, and stamps the name on the event. It always answers, because a
    process no value claims is served the canonical shape, and what it answers decides how an
    answer is shaped and never what a handler sees or whether a call is refused.
    """
    for harness in registered():
        if harness.detects is not None and harness.detects(env, payload):
            return harness
    return CANONICAL


def select(agents: Sequence[str]) -> tuple[tuple[Harness, ...], int]:
    """The harnesses `agents` names, in registry order, and how many names none answers to."""
    listed = set(agents)
    chosen = tuple(harness for harness in HARNESSES if harness.name in listed)
    unknown = len(listed - {harness.name for harness in HARNESSES})
    return chosen, unknown
