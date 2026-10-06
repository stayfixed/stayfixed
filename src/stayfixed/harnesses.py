"""Every harness stayfixed serves, as values in one registry.

A harness is served first by the `AGENTS.md` region, which `project.templates` renders and
every harness that reads the standard sees. Where a harness reads something better natively,
its `render_profile` renders a profile into that form. `settings` names the committed files in
which it reads hook entries, for `stayfixed assess`'s foreign-hooks probe to inventory;
`marker_dir` is the directory whose presence says a repository uses it. A harness is a value,
not a class: what this module states about a harness is one more value in `HARNESSES`, and
nothing that reads the registry changes. What it does not state yet is the list below.

The registry is also the adapter the `hooks` area answers through. `stayfixed hook` asks `detect`
which value it is running under and shapes its stdout with that value's `render`, and nothing
more: `detect` says why. A harness whose payload genuinely differs is a question to answer with
that harness's evidence when it arrives.

A value also states its reach: for each enforcement surface stayfixed has (`Surface`), the tier
at which that surface holds under this harness (`Tier`), or that it does not reach the harness at
all, with where the claim was measured. The README's table of what each agent enforces is held
equal to these values by a test, and `doctor`'s `codex-trust` row reads them, so a measurement
that moves a tier is one edit here.

A new harness is a value with a positive `detects`, its project-root variable, its `render`, its
settings files and its `reach`. What follows still lives outside the registry, spelled for
Claude Code or Codex, and a harness that differs from both in any of it is an edit there too:

- Each harness loads the plugin through a manifest of its own, `.claude-plugin/plugin.json` and
  `.codex-plugin/plugin.json`, which `scripts/release.py check` holds to one version, so another
  harness is another manifest and another entry in that check's sources.
- `hooks/hooks.json` keys its entries by Claude Code's event names and spells every command as
  `"${CLAUDE_PLUGIN_ROOT}/hooks/run-hook.sh"`, so a harness that names its events otherwise, or
  does not set `CLAUDE_PLUGIN_ROOT`, is an edit there: without that variable each command
  expands to `/hooks/run-hook.sh` and exits 127, which Claude Code reads as a non-blocking
  error, so no guard runs and nothing says so.
- `hooks/run-hook.sh` takes the directory it enters from `CLAUDE_PROJECT_DIR` alone, before any
  Python runs, so another root variable is an edit to its `root=` line and to the digest
  `hooks/hashes.json` records for it (`scripts/release.py hashes`).
- `hooks.api.DATA_ROOT_VARIABLES` names the variables the sink and `doctor` find the harness's
  data root by.
- `doctor` runs the wrapper for its `wrapper` row under `CLAUDE`'s two root variables whichever
  harness is in use, names `CLAUDE_PLUGIN_ROOT` in the remedy of the rows that find no plugin
  root, and reads `CODEX` by name in its `codex-trust` row.
- `memory session-context` writes a bundle to a `SessionStart` entry's stdout as it is, never
  through a `render`, so a harness that reads that event's output in another shape is an edit
  there.
- One hook output cap, `native_caps.hook_output_chars`, is Claude Code's and is applied under
  every harness.

Elsewhere, code that needs a harness fact asks this registry: `doctor` walks every value's
`settings` and `local_settings` for hook entries, and `attach` merges into the one file
`CLAUDE.local_settings` names. Two modules older than it still spell paths of their own, `setup`
the machine's settings file and `attach` the overlay's layout under `.claude/` and `.codex/`,
which are a machine's and the overlay's as much as a harness's.

A name `[stayfixed] agents` lists and no harness answers to is counted, never refused and never
printed: the list is repository-authored, and a project may name a harness a later stayfixed
serves.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from stayfixed.profiles import Profile


@dataclass(frozen=True)
class Rendition:
    """One file a harness reads natively, rendered from a profile."""

    artifact_id: str
    target: str
    render: Callable[[], str]


class Surface(StrEnum):
    """Where stayfixed enforces something, by how it reaches a session."""

    # A hook that refuses a command before it runs: `bg-cleanup`.
    GUARDS = "session guards"
    # A hook that adds context and refuses nothing: the test-hygiene note, the standing rules,
    # the volatile notes.
    NOTICES = "session notices"
    # The bug, documentation, plan, commit and trail checks, run by the reusable workflow.
    GATES = "repository gates"
    # The skills and the `AGENTS.md` region.
    METHOD = "methodology"


class Tier(StrEnum):
    """How strongly a surface holds under a harness."""

    BLOCKS = "blocks in the session"
    CONTEXT = "context only"
    CI = "CI only"
    INSTRUCTIONS = "instructions only"


@dataclass(frozen=True)
class Reach:
    """One surface under one harness."""

    # `None`: the surface does not reach this harness at all.
    tier: Tier | None
    # The observation the tier rests on and the public record that holds it, or "unmeasured".
    evidence: str
    # The agent and its version the observation was made on, as the README cites it, or `None`
    # where no agent takes part.
    measured_on: str | None = None


@dataclass(frozen=True)
class Harness:
    name: str
    marker_dir: str
    settings: tuple[str, ...]
    # Settings files this harness reads that a repository keeps out of git, which `doctor`
    # walks beside `settings` and `stayfixed assess` does not: they are this machine's.
    local_settings: tuple[str, ...]
    # The variable this harness names the project root in, if any. Every registered value's is
    # asked, in `project_root_variables`' order, whichever harness was detected (`detect`).
    project_dir_env: str | None
    # How the hook's stdout is shaped: (event name, joined context) -> stdout. Context only:
    # no rendering carries a decision, because a deny travels on the exit code.
    render: Callable[[str, str], str]
    # Every `Surface`, each with the tier it holds at under this harness. Compared, and left out
    # of the hash: a mapping has none, and the other fields already tell two harnesses apart.
    reach: Mapping[Surface, Reach] = field(hash=False)
    # Positive detection, for every harness but the canonical one, which is the fallback.
    detects: Callable[[Mapping[str, str], Mapping[str, Any] | None], bool] | None = None
    # The profile, and the repository-relative path of its rules file.
    render_profile: Callable[[Profile, str], Rendition] | None = None
    # The variable this harness names the plugin's own root in, if any: where `doctor` looks for
    # the installed plugin when this process cannot name it, and the one it sets when it runs the
    # wrapper.
    plugin_root_env: str | None = None


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
    does not. How far either signal can be trusted is `detect`'s to say."""
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


# The gates are the reusable workflow's, which runs the same under every agent: this repository's
# smoke workflow runs it against a fixture project, and no agent takes part.
_IN_CI = Reach(
    Tier.CI,
    "the reusable workflow, run on a fixture project by `.github/workflows/smoke.yml` on every "
    "change to this repository and weekly",
)
# The records the measurements below are kept in. The delivery spike's plan is not named by its
# path, which carries words this repository keeps out of its code.
_P0_SPIKES = "`docs/plans/2026-09-05-agent-harness-p0-spikes.md`"
_DELIVERY_SPIKE = "the delivery spike of 2026-10-02 in `docs/plans/`"
# What was measured of Codex's plugin hooks, which both hook surfaces rest on.
_NO_CODEX_HOOK = Reach(
    None,
    f"no plugin hook ran, with or without its hook-trust bypass flag ({_DELIVERY_SPIKE})",
    measured_on="Codex 0.160.0",
)

CLAUDE = Harness(
    name="claude",
    marker_dir=CLAUDE_DIR,
    settings=(f"{CLAUDE_DIR}/settings.json",),
    # The file `attach` merges the overlay's hook entries into.
    local_settings=(f"{CLAUDE_DIR}/settings.local.json",),
    project_dir_env="CLAUDE_PROJECT_DIR",
    render=hook_specific_output,
    reach=MappingProxyType(
        {
            Surface.GUARDS: Reach(
                Tier.BLOCKS,
                "a guard's exit 2 stopped the command unrun "
                f"({_P0_SPIKES}, the fail-closed matrix)",
                measured_on="Claude Code 2.1.261",
            ),
            Surface.NOTICES: Reach(
                Tier.CONTEXT,
                "a SessionStart hook's output arrived as context "
                f"({_P0_SPIKES}, the hook output cap trial)",
                measured_on="Claude Code 2.1.261",
            ),
            Surface.GATES: _IN_CI,
            Surface.METHOD: Reach(
                Tier.INSTRUCTIONS,
                f"the plugin's skills were listed ({_DELIVERY_SPIKE})",
                measured_on="Claude Code 2.1.285",
            ),
        }
    ),
    render_profile=_claude_rule,
    plugin_root_env="CLAUDE_PLUGIN_ROOT",
)
# Codex reads `AGENTS.md` from the root down and no other instruction file, and follows no
# import; `.codex/rules` holds command-execution policy, not instructions. The region is how a
# profile reaches it, and there is nothing further to render.
CODEX = Harness(
    name="codex",
    marker_dir=".codex",
    settings=(".codex/hooks.json",),
    local_settings=(),
    # Codex names the project root in no variable of its own (`read_event` still asks every
    # registered value's, so an inherited `CLAUDE_PROJECT_DIR` names it as it does the wrapper's).
    project_dir_env=None,
    # Claude Code's shape, and unmeasured under Codex: Codex 0.160.0 ran none of the plugin's
    # hooks, with or without its hook-trust bypass flag (`_DELIVERY_SPIKE`). A harness whose
    # output differs is a different value, never a branch inside a shared one, and a `render` of
    # its own needs more than a measured shape: `detect` says what.
    render=hook_specific_output,
    reach=MappingProxyType(
        {
            Surface.GUARDS: _NO_CODEX_HOOK,
            Surface.NOTICES: _NO_CODEX_HOOK,
            Surface.GATES: _IN_CI,
            Surface.METHOD: Reach(
                Tier.INSTRUCTIONS,
                "the plugin's skills arrived, and instructions through AGENTS.md "
                f"({_DELIVERY_SPIKE})",
                measured_on="Codex 0.160.0",
            ),
        }
    ),
    detects=_codex_detects,
    # Codex sets Claude Code's name for it too (`_codex_detects`).
    plugin_root_env="PLUGIN_ROOT",
)
# Claude Code's hook schema is the de-facto one, which other harnesses imitate, so it answers
# whatever no other value claims and detects nothing of its own.
CANONICAL = CLAUDE
# The order `init` writes into `[stayfixed] agents`.
HARNESSES: tuple[Harness, ...] = (CLAUDE, CODEX)

# The settings files whose hook entries are read as a harness was measured running them: past a
# leading UTF-8 byte-order mark, and past a scalar where an event's list, a group, a group's
# `hooks` or an entry belongs (`scaffold.judged_entries`). Claude Code 2.1.288 ran the valid hooks
# of such a file (measured on macOS, 2026-10-05, on the project's `.claude/settings.json` only;
# `.claude/settings.local.json` and `~/.claude/settings.json` are taken to be read by the same
# loader, an inference that was not measured); every other settings file -- Codex's, which no
# measurement covers -- is read as strictly as the merge that rewrites it. A path relative to the
# file's root, so `~/.claude/settings.json` is the first of these under the home directory.
LENIENT_SETTINGS: frozenset[str] = frozenset((*CLAUDE.settings, *CLAUDE.local_settings))


def project_root_variables() -> tuple[str, ...]:
    """The variables a hook's project root is read from, in the order they are asked.

    `CANONICAL`'s first, then every other registered value's in registry order, each once. The
    registry's order is the order `init` writes `agents` in, a choice about presentation, so it is
    not the precedence too: a harness registered ahead of Claude Code would otherwise move every
    Claude Code session's root to a variable of its own. Every value's is asked whichever value
    was detected, as `detect` says.
    """
    ordered = (CANONICAL, *(harness for harness in HARNESSES if harness is not CANONICAL))
    return tuple(dict.fromkeys(h.project_dir_env for h in ordered if h.project_dir_env))


def detect(env: Mapping[str, str], payload: Mapping[str, Any] | None) -> Harness:
    """The first non-canonical harness whose `detects` answers yes, else `CANONICAL`.

    The one answer to "which harness is this process running under": the `hooks` area asks it
    once, in `stayfixed hook`, and hands the answer to `dispatch` and to nothing else. It always
    answers, because a process no value claims is served the canonical shape.

    **Detection is repository-steerable, so it decides only the shape of stdout.** Neither input
    read here is the harness's alone: a committed `.claude/settings.json` `env` block reaches the
    environment, so it can set `PLUGIN_ROOT`, and the payload pair Codex is told by is fragile,
    because Claude Code's `PreToolUse` stdin already carries `permission_mode` (the spike record
    `_codex_detects` cites, in its `tool_name` trial), so a Claude Code release that adds `model`
    there would be answered as Codex. So what this answers decides nothing a handler sees and
    nothing about whether a call is refused: every payload is read by the one
    `hooks.dispatch.read_event`, into an event that does not say which value was detected; the
    project root, which decides which configuration loads, is the first variable set among every
    registered value's, `CANONICAL`'s first, whichever value was detected
    (`project_root_variables`); and a deny is exit 2 with its reason on stderr under every
    harness, and never reaches a `render`.

    **A harness gets a `render` of its own only together with a detection signal a repository
    cannot steer.** While every value renders through `CANONICAL.render`, what this answers
    changes no byte of stdout either. A value with a `render` of its own would let a repository
    choose the shape its harness receives, and a shape the harness does not read drops every
    notice without a word. So a second shape waits on a signal the wrapper controls, such as its
    argv, and never the environment or stdin; `tests/test_harnesses.py` holds every registered
    value to the canonical `render` until then.
    """
    for harness in HARNESSES:
        if harness.detects is not None and harness.detects(env, payload):
            return harness
    return CANONICAL


def select(agents: Sequence[str]) -> tuple[tuple[Harness, ...], int]:
    """The harnesses `agents` names, in registry order, and how many names none answers to."""
    listed = set(agents)
    chosen = tuple(harness for harness in HARNESSES if harness.name in listed)
    unknown = len(listed - {harness.name for harness in HARNESSES})
    return chosen, unknown
