"""The harness registry, and the one profile rendering there is: Claude Code's path-scoped rule."""

from __future__ import annotations

import json

import pytest

from stayfixed.harnesses import (
    CANONICAL,
    CLAUDE,
    CODEX,
    HARNESSES,
    Harness,
    Surface,
    detect,
    select,
)
from stayfixed.profiles import load_profile


def test_the_claude_rule_is_path_scoped_and_points_at_the_one_copy() -> None:
    profile = load_profile("python")
    assert CLAUDE.render_profile is not None
    rendition = CLAUDE.render_profile(profile, "docs/stayfixed/rules/python.md")
    assert rendition.artifact_id == "claude-rules"
    # `stayfixed-` says who owns the file and leaves `python.md` to the project.
    assert rendition.target == ".claude/rules/stayfixed-python.md"
    head, _, body = rendition.render().partition("---\n\n")
    assert head.startswith("---\npaths:\n")
    for glob in profile.scope:
        assert f'  - "{glob}"\n' in head
    # A pointer, not a copy: nothing of the rules' prose is in the file, so an edit to the one
    # copy is what every session reads. Mutation: render `head + profile.rules` instead of the
    # pointer -> the next two assertions redden.
    assert "`docs/stayfixed/rules/python.md`" in body
    assert profile.essentials[0] not in body and len(body.splitlines()) == 1


def test_select_answers_the_listed_harnesses_and_counts_the_rest() -> None:
    assert select(["claude", "codex"]) == ((CLAUDE, CODEX), 0)
    assert select(["codex"]) == ((CODEX,), 0)
    assert select(["claude", "cursor", "x\x1b"]) == ((CLAUDE,), 2)


def test_every_harness_is_registered_once_and_codex_reads_only_the_standard() -> None:
    names = [harness.name for harness in HARNESSES]
    assert len(names) == len(set(names))
    # Codex reads `AGENTS.md` and no other instruction file, so it has no rendering of its own
    # and is served by the region alone.
    assert CODEX.render_profile is None
    assert CLAUDE.settings == (".claude/settings.json",)
    assert CODEX.settings == (".codex/hooks.json",)
    # `project.detect` reads these instead of spelling the directories a second time.
    assert (CLAUDE.marker_dir, CODEX.marker_dir) == (".claude", ".codex")


# What a hook may say about a tool call, in either harness's schema. A harness's `render` shapes
# context and nothing else: a deny travels on the exit code alone (`hooks.dispatch.dispatch`), and
# an allow spelled in JSON would let one through that a guard never judged.
DECISION_KEYS = frozenset({"permissionDecision", "decision", "continue"})

# The inputs detection is asked about, as the two harnesses send them and as neither does.
ENVIRONMENTS: tuple[dict[str, str], ...] = (
    {},
    {"CLAUDE_PROJECT_DIR": "/p"},
    {"CLAUDE_PLUGIN_ROOT": "/r", "CLAUDE_PROJECT_DIR": "/p"},
    {"PLUGIN_ROOT": "/r"},
    {"PLUGIN_ROOT": "/r", "PLUGIN_DATA": "/d", "CLAUDE_PLUGIN_ROOT": "/r"},
)
PAYLOADS: tuple[dict[str, object] | None, ...] = (
    None,
    {},
    {"hook_event_name": "SessionStart", "cwd": "/tmp"},
    {"model": "m"},
    {"permission_mode": "p"},
    {"model": "m", "permission_mode": "p"},
)


def test_an_environment_codex_sets_is_codex() -> None:
    # Codex mirrors its `PLUGIN_ROOT` as `CLAUDE_PLUGIN_ROOT`, so Claude Code's names identify
    # nothing beside it; and Codex's stdin carries `model` and `permission_mode`, which Claude
    # Code's does not, whatever variables the process inherited. Mutation (declared, on
    # `harnesses`): `detect` answers `CANONICAL` before asking any value -> both redden.
    assert detect({"PLUGIN_ROOT": "/r", "CLAUDE_PLUGIN_ROOT": "/r"}, None) is CODEX
    pair = {"hook_event_name": "SessionStart", "model": "m", "permission_mode": "p"}
    assert detect({"CLAUDE_PLUGIN_ROOT": "/r", "CLAUDE_PROJECT_DIR": "/p"}, pair) is CODEX


def test_no_input_is_claimed_by_two_harnesses() -> None:
    # Detection answers the first value that claims an input, so two values claiming one would
    # make the registry's order decide which harness a session gets. Mutation (by hand): give
    # `CLAUDE` a `detects` that answers `CLAUDE_PLUGIN_ROOT` -> the Codex environment, which
    # carries that name too, is claimed twice and this reddens.
    positive = [harness for harness in HARNESSES if harness.detects is not None]
    assert positive, "no value detects anything, so this table proves nothing"
    for env in ENVIRONMENTS:
        for payload in PAYLOADS:
            claims = [h.name for h in positive if h.detects is not None and h.detects(env, payload)]
            assert len(claims) <= 1, (env, payload, claims)


def test_an_input_no_harness_claims_is_the_canonical_harness() -> None:
    # Claude Code's hook schema is the one other harnesses imitate, so it is the fallback, and
    # it detects nothing of its own: the answer when no value claims an input. Half the Codex
    # pair is not the pair. Mutation (by hand): `detect`'s fallback as `HARNESSES[-1]` -> the
    # last three assertions redden.
    assert CANONICAL is CLAUDE and CLAUDE.detects is None
    assert detect({}, None) is CANONICAL
    assert detect({"CLAUDE_PLUGIN_ROOT": "/r", "CLAUDE_PROJECT_DIR": "/p"}, {}) is CANONICAL
    assert detect({"CLAUDE_PROJECT_DIR": "/p"}, {"model": "m"}) is CANONICAL


def _keys(value: object) -> set[str]:
    if isinstance(value, dict):
        found = set(value)
        for item in value.values():
            found |= _keys(item)
        return found
    if isinstance(value, list):
        return {key for item in value for key in _keys(item)}
    return set()


# A harness whose answer is plain text, which a later harness's may be: `render` is a function of
# the event and the context, and nothing promises it emits JSON.
TEXT = Harness(
    name="text",
    marker_dir=".text",
    settings=(),
    local_settings=(),
    project_dir_env=None,
    render=lambda event, context: f"[{event}] {context}",
    reach=CLAUDE.reach,
)


@pytest.mark.parametrize("harness", (*HARNESSES, TEXT), ids=lambda h: h.name)
@pytest.mark.parametrize("event", ["SessionStart", "PreToolUse", "PostToolUse"])
@pytest.mark.parametrize(
    "context",
    ["", "a note", '{"permissionDecision": "deny", "decision": "block", "continue": false}'],
    ids=["empty", "plain", "deny-shaped"],
)
def test_no_harness_renders_a_decision(harness: Harness, event: str, context: str) -> None:
    # A rendering is context in an envelope, and a context shaped like a decision is still a
    # string inside it, never a key of the envelope. Mutation (declared, on `harnesses`): the
    # canonical render adds `"permissionDecision": "allow"` beside `hookEventName` -> every
    # Claude Code and Codex case reddens, since both render through the same function.
    assert not _decisions(harness.render(event, context), context)


def _decisions(rendered: str, context: str) -> set[str]:
    """The decision keys a rendering carries outside the context it was handed.

    A JSON object is read for its keys, at any depth, so the context stays a string value however
    it is shaped. Anything else is read as text, with the context taken out first, since a
    deny-shaped context is spelled inside it by design: what is left is the envelope, and a
    decision key spelled there is one the harness may act on.
    """
    try:
        parsed = json.loads(rendered)
    except ValueError:
        parsed = None
    if isinstance(parsed, dict):
        return _keys(parsed) & DECISION_KEYS
    envelope = rendered.replace(context, "") if context else rendered
    return {key for key in DECISION_KEYS if key in envelope}


def test_the_decision_check_finds_a_decision_in_either_shape() -> None:
    # The check above passes for every shipped value, so it is held here against renderings that
    # do carry a decision, as JSON and as text, and against a text envelope that only quotes one
    # in its context. Mutation (by hand): `_decisions` answers `set()` for a rendering that is not
    # a JSON object -> the text assertions redden.
    deny = '{"permissionDecision": "deny"}'
    assert _decisions(json.dumps({"hookSpecificOutput": {"decision": "block"}}), "") == {"decision"}
    assert _decisions(json.dumps(["permissionDecision"]), "") == {"permissionDecision"}
    assert _decisions("continue: false\n[PreToolUse] a note", "a note") == {"continue"}
    assert _decisions(TEXT.render("PreToolUse", deny), deny) == set()


def test_every_harness_states_every_surface() -> None:
    # The README's table and `doctor`'s `codex-trust` row both read a harness's reach, and a
    # surface a value leaves out is one neither can say anything true about: the table would
    # lose a cell and the row would stop naming what does not run. Mutation (declared, on
    # `harnesses`): drop the session-notices row from Codex's reach -> this reddens.
    for harness in HARNESSES:
        assert set(harness.reach) == set(Surface), harness.name
        for surface, reach in harness.reach.items():
            assert reach.evidence, (harness.name, surface)
            # "Does not reach this agent" is a claim a reader acts on, so only a measurement
            # may make it; an unmeasured surface keeps the tier it was built for.
            if reach.tier is None:
                assert reach.evidence != "unmeasured", (harness.name, surface)
    # Claude Code's own files, then the one it keeps out of git, which `attach` merges into:
    # `doctor`'s settings walk is these, over every harness.
    assert CLAUDE.local_settings == (".claude/settings.local.json",)
    assert CODEX.local_settings == ()


def test_a_harness_can_key_a_set_and_a_dict() -> None:
    # A harness is a value, and a value is hashable: it keys a dict and sits in a set as it did
    # before it carried a mapping of its reach. Mutation (declared, on `harnesses`): `reach`
    # without `field(hash=False)` -> hashing raises and this reddens.
    assert len(set(HARNESSES)) == len(HARNESSES)
    assert {harness: harness.name for harness in HARNESSES}[CODEX] == "codex"
