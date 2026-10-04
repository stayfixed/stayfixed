"""Skills are documents held to a contract: frontmatter, a line budget, action language rather
than tool or product names, and invocations that parse against the real parser or are
allow-listed by the package that will ship them."""

from __future__ import annotations

import io
import re
import shlex
from contextlib import redirect_stderr
from pathlib import Path

import pytest

from stayfixed.cli import build_parser, discover_registrars, split_json_flag

ROOT = Path(__file__).resolve().parents[2]
SKILLS = ROOT / "skills"
# The skills that ship *into* an overlay. They moved under `src/stayfixed/templates/` with the
# overlay template and this walk did not follow, so the one document the invocation lint exists
# for -- that file once shipped an invocation that does not parse -- was walked by nothing while
# a model read it in every overlay a user creates. The template ships none today; the walks go
# on reading the directory, so a skill added there is held to every rule below.
TEMPLATE_SKILLS = ROOT / "src" / "stayfixed" / "templates" / "overlay" / "skills"
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
# package that ships each. The change that ships one DELETES its entry: a parsing command that is
# still listed here reddens `test_every_invocation_parses_or_is_allowlisted`. Empty since
# `uninstall` shipped; kept, with its check against `PACKAGES`, for the next wrapper written ahead
# of its command.
NOT_YET_SHIPPED: dict[str, str] = {}
PACKAGES = {"onboarding", "upgrade", "attach", "setup", "hooks-core"}
_INVOCATION = re.compile(r"`stayfixed ([^`\n]+)`")
_FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n(.*)\Z", re.DOTALL)


def skills() -> list[Path]:
    return sorted(SKILLS.glob("*/SKILL.md"))


def entry_points() -> list[Path]:
    """Every `SKILL.md` this repository ships, in the plugin **and** in the overlay template.

    `skills()` never saw the template tree, so the one skill that goes into every overlay a user
    creates was held to exactly one of the three rules `skills/README.md` states: it reached the
    invocation lint through `documents()` and was walked by nothing else. The 80-line cap, the
    frontmatter check and the harness-tool rule all parametrise over `skills()`, so that file
    passed them by not being one of their cases. It passes today on its merits; nothing was
    checking that it would tomorrow.

    `skills()` itself is left alone, because `test_the_walk_finds_the_ported_skills` and
    `test_every_reference_file_is_linked_from_its_skill` are statements about the plugin's own
    `skills/` directory and its `references/` convention, which the template does not use.
    """
    return sorted([*skills(), *TEMPLATE_SKILLS.glob("*/SKILL.md")])


def _id(path: Path) -> str:
    """A case id that is unique across both trees, which may each hold a skill of one name."""
    return str(path.parent.relative_to(ROOT))


def documents() -> list[Path]:
    """Every skill document the invocation check reads: the `SKILL.md` entry points and the
    `references/` files beside them, in the plugin's own `skills/` **and** in the overlay
    template.

    A reference is skill content a model reads and copies, so an invocation that does not parse
    is as wrong there as in a procedure. `skills/README.md` is excluded because its table names
    harness tools rather than commands. The tool-name rule is deliberately *not* widened this
    way: a reference writes ordinary English about writing ("Write the rule, not the incident")
    that `_TOOL` would read as the harness tool of the same name.

    The template's skills are walked for the same reason the plugin's are: they ship into every
    overlay a user creates and a model reads them there. Where they live is not the question the
    lint asks.
    """
    return sorted(
        path
        for tree in (SKILLS, TEMPLATE_SKILLS)
        for path in tree.rglob("*.md")
        if path.name != "README.md"
    )


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
    } <= names
    # The same guard for the wider walk: a `references/` that goes quiet takes its own
    # invocation cases with it, and so does a template tree that moves again.
    walked = documents()
    assert SKILLS / "memory-sweep" / "references" / "protocol.md" in walked
    # And the same guard for the walk the three rules above parametrise over. The template tree
    # moving again would otherwise silently take its cases with it -- which is exactly how that
    # tree came to be held to one rule of the three in the first place. It ships no skill since
    # its copy of `attach` was retired for the plugin's own, so the walks' share of it is named
    # as the empty set: a skill added there again reddens this, and is walked by the rules.
    # No mutation entry: what breaks this is a file added to the tree, not a line changed.
    from stayfixed.overlay.template import template_root

    assert TEMPLATE_SKILLS.parent == template_root()
    assert [path for path in walked if TEMPLATE_SKILLS in path.parents] == []
    assert set(entry_points()) == set(skills())


@pytest.mark.parametrize("path", entry_points(), ids=_id)
def test_every_skill_has_a_name_matching_its_directory_and_a_description(path: Path) -> None:
    fields, _ = split(path)
    assert fields["name"] == path.parent.name
    assert len(fields["description"]) > 40, "a description is what the harness matches on"


@pytest.mark.parametrize("path", entry_points(), ids=_id)
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


@pytest.mark.parametrize("path", entry_points(), ids=_id)
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


def test_the_allowlist_names_only_packages_the_design_defines() -> None:
    assert set(NOT_YET_SHIPPED.values()) <= PACKAGES


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


def test_the_init_skill_asks_before_it_runs_a_kept_file_s_custom_gates() -> None:
    # `init` adopts a clone's `stayfixed.toml`, and the adoption's first command, `stayfixed
    # assess`, runs every command its `[gates.custom]` names. `init` says so in a note, and the
    # skill names that note by its words and asks before the first `stayfixed assess`. Mutation
    # (by hand): the step's question removed -> the ask no longer comes first and this reddens.
    from stayfixed.project.commands import CUSTOM_GATES

    text = (SKILLS / "init" / "references" / "adoption.md").read_text(encoding="utf-8")
    adoption = " ".join(text.split())
    lead = CUSTOM_GATES.split("{count}", 1)[0].strip()
    first_run = adoption.index("run `stayfixed assess`")
    assert adoption.index(lead) < adoption.index("explicit yes") < first_run
    # A no still produces an assessment, through the flag that runs none of those commands:
    # before it, the only way to honour a no was to stop. Mutation (by hand): the no's command
    # back to plain `stayfixed assess` -> this reddens.
    assert "`stayfixed assess --builtin` on a no" in adoption[first_run:]
    # Without the note there is nothing to ask, and the assessment still runs: that run was the
    # tail of the if-sentence, where an agent reading "if" could skip it. It is its own branch,
    # and the relay follows both. Mutation (by hand): the `Otherwise` branch deleted -> reddens.
    otherwise = adoption.index("- Otherwise, run `stayfixed assess`.")
    assert first_run < otherwise < adoption.index("Either way, relay the summary")


def test_the_init_skill_keeps_a_no_to_the_clone_s_commands_through_the_whole_adoption() -> None:
    # After a no, the first step assessed with `--builtin`, and the closing message then handed
    # over `stayfixed adopt promote`, which runs every custom gate the clone configures: in a
    # clone the base is the clone author's, so its having the command is no brake. Every command
    # the skill names that runs gates is named with `--builtin` for a no as well. Mutation
    # (oracle): the closing step's `--builtin` dropped -> `adopt promote` has no such form and
    # this reddens.
    text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (SKILLS / "init" / "SKILL.md", *(SKILLS / "init" / "references").glob("*.md"))
    )
    words = " ".join(text.split())
    named = [
        c for c in ("stayfixed assess", "stayfixed adopt promote", "stayfixed gate") if c in words
    ]
    assert named == ["stayfixed assess", "stayfixed adopt promote"]
    for command in named:
        assert f"`{command} --builtin`" in words, command
    assert "A no holds for the whole adoption" in words
