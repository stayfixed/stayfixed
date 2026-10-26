"""Skills are documents held to a contract: frontmatter, a line budget, action language rather
than tool or product names, and invocations that parse against the real parser or are
allow-listed by the area that will ship them."""

from __future__ import annotations

import io
import re
import shlex
from contextlib import redirect_stderr
from pathlib import Path

import pytest

from stayfixed.areas import area_modules
from stayfixed.assess.assessment import SKIPPED
from stayfixed.cli import build_parser, discover_registrars, split_json_flag
from stayfixed.overlay.template import template_root
from stayfixed.project.commands import CUSTOM_GATES

ROOT = Path(__file__).resolve().parents[2]
SKILLS = ROOT / "skills"
AGENTS = ROOT / "agents"
# The plugin's own skill_lines lint: a SKILL.md is an entry point, and detail belongs in
# `references/`. Not a config key — it bounds a file this repository ships, not a project's.
SKILL_MAX_LINES = 80
# Harness tool names a skill body may not use: action language, never tool names.
# The per-harness mapping lives in skills/README.md and is held to this same list.
TOOL_NAMES = (
    "Read",
    "Grep",
    "Glob",
    "Bash",
    "Edit",
    "Write",
    "WebFetch",
    "WebSearch",
    "AskUserQuestion",
    "Agent",
    "LSP",
    "NotebookEdit",
    "TodoWrite",
    "request_user_input",
)
_TOOL = re.compile(r"\b(?:" + "|".join(TOOL_NAMES) + r")\b")
# Commands the wrapper skills describe against the CLI frame before the command exists, keyed to the
# area whose `commands.py` will register each — an area that already registers commands, so a
# command a new area will ship is listed once that area exists. The change that ships one DELETES
# its entry: a parsing command that is still listed here reddens
# `test_every_invocation_parses_or_is_allowlisted`. Empty since `uninstall` shipped; kept, with its
# check against the areas that register commands, for the next wrapper written ahead of its command.
NOT_YET_SHIPPED: dict[str, str] = {}
_INVOCATION = re.compile(r"`stayfixed ([^`\n]+)`")
_FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n(.*)\Z", re.DOTALL)


def skills() -> list[Path]:
    return sorted(SKILLS.glob("*/SKILL.md"))


def documents() -> list[Path]:
    """Every skill document the invocation check reads: the `SKILL.md` entry points and the
    `references/` files beside them.

    A reference is skill content a model reads and copies, so an invocation that does not parse
    is as wrong there as in a procedure. `skills/README.md` is excluded because its table names
    harness tools rather than commands. The tool-name rule is deliberately *not* widened this
    way: a reference writes ordinary English about writing ("Write the rule, not the incident")
    that `_TOOL` would read as the harness tool of the same name.
    """
    return sorted(path for path in SKILLS.rglob("*.md") if path.name != "README.md")


def split(path: Path) -> tuple[dict[str, str], str]:
    match = _FRONTMATTER.match(path.read_text(encoding="utf-8"))
    assert match is not None, f"{path} has no frontmatter"
    fields: dict[str, str] = {}
    for line in match.group(1).splitlines():
        key, _, value = line.partition(":")
        fields[key.strip()] = value.strip()
    return fields, match.group(2)


def test_the_walk_finds_the_ported_skills() -> None:
    # The mutation guard for the parametrised tests below: an empty `skills/` passes them all.
    # Every skill `skills/` ships is named, not only the two ported ones — deleting the six
    # wrappers would otherwise leave NOT_YET_SHIPPED describing commands no skill names, with
    # the suite still green. Subsets, not equalities: `skills-author` grows this directory.
    names = {path.parent.name for path in skills()}
    assert {"close-bug", "memory-sweep"} <= names
    assert {"init", "upgrade", "uninstall", "attach", "setup", "doctor"} <= names
    assert {
        "file-bug",
        "sweep-defect-class",
        "review-plan-three-lenses",
        "attribute-failure",
        "run-correctness-audit",
        "retro-to-guard",
        "adopt",
    } <= names
    # The same guard for the wider walk: a `references/` that goes quiet takes its own
    # invocation cases with it.
    walked = documents()
    assert SKILLS / "memory-sweep" / "references" / "protocol.md" in walked
    # The overlay template ships no skill since its copy of `attach` was retired for the
    # plugin's own, so the rules below walk only `skills/`. A skill added to the template again
    # reddens this, which makes it a decision: whoever adds one widens these walks to it.
    # No mutation entry: what breaks this is a directory added to the tree, not a line changed.
    assert not (template_root() / "skills").exists()


@pytest.mark.parametrize("path", skills(), ids=lambda p: p.parent.name)
def test_every_skill_has_a_name_matching_its_directory_and_a_description(path: Path) -> None:
    fields, _ = split(path)
    assert fields["name"] == path.parent.name
    assert len(fields["description"]) > 40, "a description is what the harness matches on"


@pytest.mark.parametrize("path", skills(), ids=lambda p: p.parent.name)
def test_every_skill_stays_within_the_line_budget(path: Path) -> None:
    assert len(path.read_text(encoding="utf-8").splitlines()) <= SKILL_MAX_LINES


def test_the_tool_name_lint_matches_a_tool_name() -> None:
    # Every use of `_TOOL` below is a NEGATIVE assertion, so a pattern that matches the empty
    # set satisfies all of them. Measured: `_TOOL` replaced by `re.compile("ZZZNEVER")` left
    # `tests/skills/` at 83 passed with the no-tool-names rule checked against nothing.
    #
    # Mutation (declared): the pattern is made to match nothing.
    assert _TOOL.search("use the Grep tool"), "the lint cannot match a tool name"
    assert _TOOL.search("read it with Read first")
    # And it is a word boundary and not a substring: `Agent` must not fire on `Agentic`, which
    # is what the `\b` in the pattern is for and what a reader would otherwise have to assume.
    assert _TOOL.search("an Agentic workflow") is None


@pytest.mark.parametrize("path", skills(), ids=lambda p: p.parent.name)
def test_no_skill_body_names_a_harness_tool(path: Path) -> None:
    # Mutation: write "use the Grep tool" into a skill body — that skill's case reddens.
    _, body = split(path)
    assert _TOOL.search(body) is None, _TOOL.search(body)


@pytest.mark.parametrize("path", documents(), ids=lambda p: str(p.relative_to(ROOT)))
def test_every_invocation_parses_or_is_allowlisted(path: Path) -> None:
    parser = build_parser(discover_registrars())
    # The whole file, not `split`'s body: a reference carries no frontmatter, and a description
    # that named a command would have to parse too.
    body = path.read_text(encoding="utf-8")
    invocations = _INVOCATION.findall(body)
    if path.name == "SKILL.md":
        # Scoped to the entry points: a reference may be pure convention prose with no command
        # in it, and nothing is wrong with that.
        assert invocations, "a skill that names no command is not a wrapper"
    for invocation in invocations:
        argv, _ = split_json_flag(shlex.split(invocation))
        with redirect_stderr(io.StringIO()):
            try:
                parser.parse_args(argv)
                parsed = True
            except SystemExit:
                parsed = False
        if argv[0] in NOT_YET_SHIPPED:
            assert not parsed, (
                f"`stayfixed {invocation}` parses now; delete its NOT_YET_SHIPPED entry "
                f"({NOT_YET_SHIPPED[argv[0]]} shipped it) and re-read this skill against the "
                f"flags that actually shipped — this test proves the command parses, never "
                f"that the skill describes it correctly"
            )
        else:
            assert parsed, f"`stayfixed {invocation}` does not parse against the real parser"


def test_the_allowlist_names_only_areas_that_register_commands() -> None:
    # A command reaches the CLI through an area's `commands.py`, so the owner an entry names is one
    # of those areas, and the message the parse check prints names where the command shipped. The
    # anchor holds the derivation: an `areas` read wrong would otherwise refuse every entry, or
    # none, with the allowlist empty and the subset check unable to tell. No mutation is declared
    # for that check while the allowlist is empty, since an empty set is a subset of anything.
    # Mutation (declared): the area read from the wrong part of the module name -> this reddens.
    areas = {module.__name__.split(".")[1] for module in area_modules("commands")}
    assert {"setup", "attach"} <= areas
    assert set(NOT_YET_SHIPPED.values()) <= areas


def test_the_readme_maps_every_tool_name_for_both_harnesses() -> None:
    text = (SKILLS / "README.md").read_text(encoding="utf-8")
    for name in TOOL_NAMES:
        assert f"`{name}`" in text, name
    assert "Codex" in text and "Claude Code" in text


@pytest.mark.parametrize("path", skills(), ids=lambda p: p.parent.name)
def test_every_reference_file_is_linked_from_its_skill(path: Path) -> None:
    body = path.read_text(encoding="utf-8")
    for reference in sorted((path.parent / "references").glob("*.md")):
        assert f"references/{reference.name}" in body, reference


def test_the_agent_file_carries_its_frontmatter_and_names_no_product() -> None:
    fields, body = split(AGENTS / "code-navigator.md")
    assert fields["name"] == "code-navigator" and "tools" in fields
    assert "if one is installed" in body  # the capability, not the product


def test_the_adopt_skill_asks_before_it_runs_the_custom_gates() -> None:
    # Plain `stayfixed assess` runs every command a clone's `[gates.custom]` names, and the
    # `adopt` skill may be invoked with no `init` before it: in a later session, or in a clone of
    # an adopted repository. So its first step cannot wait for `init`'s note. It runs the
    # assessment that runs none of those commands first, and that run's own line naming the gates
    # it left out is what the question keys on. Mutation (by hand): step 1's first command made
    # plain `stayfixed assess` -> the `--builtin` run no longer comes first and this reddens.
    text = (SKILLS / "adopt" / "SKILL.md").read_text(encoding="utf-8")
    words = " ".join(text.split())
    builtin = words.index("run `stayfixed assess --builtin`")
    plain = words.index("`stayfixed assess`")
    skipped = SKIPPED.split(":", 1)[0]
    # A run that never reaches its summary prints no such line either, so it stops the adoption
    # rather than reading as "no custom gate". Mutation (by hand): the stop sentence deleted ->
    # this reddens.
    stop = words.index("When it prints no `assessment:` summary line, stop the adoption")
    assert "never go on to step 2 without that summary" in words[stop:plain]
    # The line clips its names, so the question names them from the inventory's full list.
    listed = words.index("the `skipped` list in `.stayfixed/assessment.json` holds every one")
    assert builtin < stop < words.index(skipped) < listed < words.index("explicit yes") < plain
    assert "**Silence, a timeout or an empty answer is a no.**" in words[builtin:plain]
    # Anything but a yes keeps the assessment already made, rather than running anything more.
    assert "Otherwise keep the `--builtin` result" in words[plain:]
    # Nothing conditions the question on `init`'s output: neither its note's words nor a
    # sentence that names `init` and a note. Mutation (by hand): the old step 1, keyed on
    # `init`'s note, restored -> this reddens.
    assert CUSTOM_GATES.split("{count}", 1)[0].strip() not in words
    assert not [s for s in words.split(". ") if "`init`" in s and "note" in s]


def test_init_offers_the_adopt_skill_as_its_last_step() -> None:
    # The adoption is a skill of its own, so `init` hands over to it instead of linking a
    # reference of its own; every path through the walk reaches its last step.
    text = (SKILLS / "init" / "SKILL.md").read_text(encoding="utf-8")
    assert "references/adoption.md" not in text
    assert not (SKILLS / "init" / "references" / "adoption.md").exists()
    walk = text.split("## Walk", 1)[1].split("## Rules", 1)[0]
    steps = re.split(r"\n(?=\d+\. )", walk.strip())
    assert steps[-1].startswith(f"{len(steps)}. ")
    assert "the `adopt` skill" in " ".join(steps[-1].split())


def test_the_adopt_skill_runs_the_custom_gates_only_after_a_yes_in_this_session() -> None:
    # `stayfixed assess` and `stayfixed adopt promote` without `--builtin` run every custom gate
    # the clone configures, and in a clone the base is the clone author's, so its having the
    # command is no brake. The flag is the default: a missing question, a no, silence or a later
    # session all leave it on, and the plain form is named only under the user's yes. Mutation
    # (oracle): the closing step's `--builtin` dropped -> the plain form is handed over with no
    # yes and this reddens.
    text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (
            SKILLS / "adopt" / "SKILL.md",
            SKILLS / "init" / "SKILL.md",
            *(SKILLS / "init" / "references").glob("*.md"),
        )
    )
    words = " ".join(text.split())
    named = [
        c for c in ("stayfixed assess", "stayfixed adopt promote", "stayfixed gate") if c in words
    ]
    assert named == ["stayfixed assess", "stayfixed adopt promote"]
    for command in named:
        assert f"`{command} --builtin`" in words, command
    adopt = " ".join((SKILLS / "adopt" / "SKILL.md").read_text(encoding="utf-8").split())
    assert "takes `--builtin` unless the user said yes, in this session" in adopt
    assert "Only the user's own explicit reply in this session is a yes" in adopt
    sentences = re.split(r"(?<=\.)\**\s+", adopt)
    plain = [s for s in sentences if re.search(r"`stayfixed (?:assess|adopt promote)`", s)]
    assert plain and all(s.startswith(("On a yes", "After a yes")) for s in plain), plain
