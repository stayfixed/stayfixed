"""What `stayfixed init` would ask, as a JSON Schema: `stayfixed init --questions`.

Six questions, each keyed by the `stayfixed.toml` key its answer writes. Each carries the value
`stayfixed init --yes` takes when it is not answered, where that value came from, and the flag on
`init --yes` that answers it. The schema is modelled on MCP elicitation's flat form schema, so a
client that drops `pattern` and the `x-stayfixed-*` keys can send it as a requested schema; an
agent harness's ask tool takes questions and options instead, so the `init` skill turns the
properties into questions: the first four as one confirmation of their defaults, and the rest
one at a time, within each harness's limits.

**Nothing here carries a byte a grammar rejected.** Every default comes from `detect`, which
bounds the three repository-authored strings before it returns them, from stayfixed's own
registries, or from the preset. A name outside `[project] name`'s grammar has no default at all:
it is asked, never suggested. The machine file changes one option's title and nothing else.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from stayfixed.config.schema import BRANCH_NAME, MEMORY_MODES, OVERLAY_MODE, PROJECT_NAME
from stayfixed.project.templates import LOCAL_ELIGIBLE

# Each question's `stayfixed.toml` key, and the flag on `stayfixed init --yes` that answers it.
FLAGS = {
    "project.name": "--name",
    "project.base_branch": "--base-branch",
    "stayfixed.agents": "--agent",
    "stayfixed.profile": "--profile",
    "memory.mode": "--memory-mode",
    "artifacts.local": "--local",
}
PROPERTIES = tuple(FLAGS)
SCHEMA = "https://json-schema.org/draft/2020-12/schema"
# The source of a default that nothing in the repository chose.
PRESET = "the preset's default"
MEMORY_TITLES = {
    "in-repo": "In this repository, committed with the code",
    "local-only": "On this machine only, under .stayfixed/local/",
}
OVERLAY_RECORDED = "In your private overlay, which this machine records"
OVERLAY_NEXT = "In a private overlay, which the setup skill creates or records next"
# How the card shows a question with no default: one whose value could not be derived.
UNANSWERED = "none; asked"
TAIL = (
    "each is answered by the flag its line names, on `stayfixed init --yes`; "
    "`stayfixed init --questions --json` carries them as a JSON Schema"
)


def ecma(pattern: re.Pattern[str]) -> str:
    """`pattern` as ECMA-262 reads it: Python's `\\Z` is a literal `Z` there, so the end anchor
    becomes `$`, which matches only at the end of the input without the multiline flag."""
    return pattern.pattern.removesuffix("\\Z") + "$"


NAME_PATTERN = ecma(PROJECT_NAME)
BRANCH_PATTERN = ecma(BRANCH_NAME)


def _overlay_recorded(machine: Path | None) -> bool:
    """Whether the machine file records an overlay; one that cannot be read or parsed reads as
    not recorded, because it only changes a title and `init` reports it when it loads it."""
    from stayfixed.config.overlay import overlay_root
    from stayfixed.errors import Failure

    try:
        return overlay_root(machine) is not None
    except Failure:
        return False


def questions(root: Path, *, machine: Path | None) -> dict[str, Any]:
    """The six questions `init` asks at `root`, as a JSON Schema object (draft 2020-12).

    Refused where `init --yes` with an answer would be (`init.precheck`): a manifest, or a
    `stayfixed.toml` that already answers them. Detection is lenient, so a name outside the
    grammar leaves `project.name` with no `default` rather than refusing the questions.
    """
    from stayfixed.config.loader import preset_defaults
    from stayfixed.harnesses import HARNESSES
    from stayfixed.profiles import shipped
    from stayfixed.project.detect import detect
    from stayfixed.project.init import precheck

    precheck(root, answering=True)
    found = detect(root, lenient=True)
    preset = preset_defaults(found.name or "project")
    titles = {
        **MEMORY_TITLES,
        OVERLAY_MODE: OVERLAY_RECORDED if _overlay_recorded(machine) else OVERLAY_NEXT,
    }
    name: dict[str, Any] = {"type": "string", "title": "Project name", "pattern": NAME_PATTERN}
    if found.name:
        name["default"] = found.name
    properties: dict[str, dict[str, Any]] = {
        "project.name": {**name, "x-stayfixed-source": found.sources["name"]},
        "project.base_branch": {
            "type": "string",
            "title": "The branch pull requests merge into",
            "pattern": BRANCH_PATTERN,
            "default": found.base_branch,
            "x-stayfixed-source": found.sources["base_branch"],
        },
        "stayfixed.agents": {
            "type": "array",
            "title": "Coding agents",
            "items": {"type": "string", "enum": [h.name for h in HARNESSES]},
            "minItems": 1,
            "default": list(found.agents),
            "x-stayfixed-source": found.sources["agents"],
        },
        "stayfixed.profile": {
            "type": "string",
            "title": "Stack profile",
            "oneOf": [
                {"const": "", "title": "No profile"},
                *({"const": n, "title": n} for n in shipped()),
            ],
            "default": found.profile,
            "x-stayfixed-source": found.sources["profile"],
        },
        "memory.mode": {
            "type": "string",
            "title": "Where the notes live",
            # A mode with no title is a `KeyError` here: loud, and caught by every test.
            "oneOf": [{"const": mode, "title": titles[mode]} for mode in MEMORY_MODES],
            "default": preset.memory.mode,
            "x-stayfixed-source": PRESET,
        },
        "artifacts.local": {
            "type": "array",
            "title": "Files kept out of git",
            "items": {"type": "string", "enum": list(LOCAL_ELIGIBLE)},
            "default": list(preset.artifacts.local),
            "x-stayfixed-source": PRESET,
        },
    }
    for key, flag in FLAGS.items():
        properties[key]["x-stayfixed-flag"] = flag
    return {
        "$schema": SCHEMA,
        "title": "stayfixed init",
        "type": "object",
        "properties": properties,
        "required": list(PROPERTIES),
    }


def _shown(question: dict[str, Any]) -> str:
    if "default" not in question:
        return UNANSWERED
    value = question["default"]
    shown = ", ".join(value) if isinstance(value, list) else str(value)
    return shown or "none"


def card(schema: dict[str, Any]) -> str:
    """The questions as `init --questions` prints them: each default, where it came from, and
    the flag on `init --yes` that answers it."""
    lines = ["detected:"]
    for key, question in schema["properties"].items():
        source, flag = question["x-stayfixed-source"], question["x-stayfixed-flag"]
        lines.append(f"  {key}: {_shown(question)} ({source}; {flag})")
    lines.append(TAIL)
    return "\n".join(lines)
