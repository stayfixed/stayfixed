"""`stayfixed init --questions`' schema: six questions, each default what `init --yes` alone
writes, each source one of `detect`'s phrases, and no byte a grammar rejected."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest

from stayfixed.config.loader import load
from stayfixed.config.schema import MEMORY_MODES
from stayfixed.errors import Refusal
from stayfixed.project.init import init
from stayfixed.project.questions import (
    BRANCH_PATTERN,
    FLAGS,
    NAME_PATTERN,
    OVERLAY_NEXT,
    PROPERTIES,
    card,
    questions,
)
from stayfixed.scaffold import MANIFEST_PATH
from tests.gitfixture import git, needs_git
from tests.project.repos import DOCUMENT, repository
from tests.runners import LsRemote


def _schema(tmp_path: Path, root: Path) -> dict[str, Any]:
    return questions(root, machine=tmp_path / "absent.toml")


def _defaults(schema: dict[str, Any]) -> dict[str, tuple[object, str]]:
    return {
        key: (question.get("default"), question["x-stayfixed-source"])
        for key, question in schema["properties"].items()
    }


@needs_git
@pytest.mark.parametrize("key", PROPERTIES)
def test_each_default_is_what_init_yes_alone_writes(tmp_path: Path, key: str) -> None:
    # The card promises that each default is what `init --yes` would take, and the skill asks
    # the person to confirm the card, not the file. The two are computed in two places, so each
    # is held to the other over a repository where no default is the preset's: a `develop`
    # branch, a harness directory and a profile's markers. Mutation (by hand): the card's base
    # branch taken from the preset -> the `project.base_branch` case reddens.
    root = repository(tmp_path, origin=None)
    git(root, "symbolic-ref", "HEAD", "refs/heads/develop")
    (root / ".codex").mkdir()
    (root / "pyproject.toml").write_text("[project]\nname = 'widget'\n", encoding="utf-8")
    default = _schema(tmp_path, root)["properties"][key]["default"]
    written = init(
        root, machine=tmp_path / "absent.toml", runner=LsRemote(), yes=True, dry_run=False, ci=False
    )
    assert not written.refused
    table, name = key.split(".")
    value = getattr(getattr(load(root, machine=tmp_path / "absent.toml"), table), name)
    assert (list(value) if isinstance(value, tuple) else value) == default


@needs_git
def test_the_schema_keys_are_the_stayfixed_toml_keys_the_answers_write(tmp_path: Path) -> None:
    # Mutation (by hand): the loop that sets `x-stayfixed-flag` dropped -> the last assertion
    # reddens on a `KeyError`.
    schema = _schema(tmp_path, repository(tmp_path))
    assert schema["type"] == "object"
    assert tuple(schema["properties"]) == PROPERTIES == tuple(schema["required"])
    assert len(PROPERTIES) == 6
    for key, question in schema["properties"].items():
        assert question["x-stayfixed-flag"] == FLAGS[key], key


@needs_git
def test_each_default_says_where_it_came_from(tmp_path: Path) -> None:
    # Each (default, source) pair is what `init --yes` alone takes, and says why: a default with
    # no source is one a person cannot check before accepting it. Mutation (by hand): the agents'
    # fallback reports `harness directories` -> the agents assertion reddens.
    defaults = _defaults(_schema(tmp_path, repository(tmp_path)))
    assert defaults["project.name"] == ("widget", "origin remote")
    # An `origin` with no `origin/HEAD`, as a repository created here and pushed has it: the
    # default, never the branch checked out, which may be the feature branch being adopted from.
    assert defaults["project.base_branch"] == ("main", "default")
    no_origin = _defaults(_schema(tmp_path / "b", repository(tmp_path / "b", origin=None)))
    assert no_origin["project.base_branch"] == ("main", "current branch")
    assert defaults["stayfixed.agents"] == (["claude", "codex"], "default")
    assert defaults["stayfixed.profile"] == ("", "no profile markers")


def test_the_free_text_patterns_are_anchored_for_ecma_262() -> None:
    # A JSON Schema `pattern` is ECMA-262, where Python's `\Z` is a literal `Z`: a client
    # validating against it would refuse every real name. Mutation (oracle): `ecma` returns the
    # Python pattern unchanged -> the `\Z` assertion reddens.
    for pattern in (NAME_PATTERN, BRANCH_PATTERN):
        assert pattern.endswith("$") and "\\Z" not in pattern, pattern
    # Not vacuous: the pattern still accepts a name and refuses what the grammar refuses.
    assert re.fullmatch(NAME_PATTERN, "widget")
    assert not re.fullmatch(NAME_PATTERN, "Not A Name")
    assert re.fullmatch(BRANCH_PATTERN, "release/2.x")


@needs_git
def test_the_memory_default_is_the_presets_whatever_the_machine_records(tmp_path: Path) -> None:
    # `init` takes `[memory] mode` from the preset whatever the machine records; the machine only
    # changes what the overlay option says. (`overlay_root` does not check the directory exists.)
    # Mutation (by hand): default to `overlay` when the machine records one -> the first
    # assertion reddens.
    bare = questions(repository(tmp_path / "a"), machine=tmp_path / "absent.toml")
    machine = tmp_path / "machine.toml"
    machine.write_text(f'[overlay]\nroot = "{tmp_path / "overlay"}"\n', encoding="utf-8")
    recorded = questions(repository(tmp_path / "b"), machine=machine)
    modes = [bare["properties"]["memory.mode"], recorded["properties"]["memory.mode"]]
    assert [m["default"] for m in modes] == ["local-only", "local-only"]
    assert [[o["const"] for o in m["oneOf"]] for m in modes] == [list(MEMORY_MODES)] * 2
    titles = [{o["const"]: o["title"] for o in m["oneOf"]}["overlay"] for m in modes]
    assert titles[0] != titles[1], titles


@needs_git
def test_a_machine_file_that_does_not_parse_still_yields_the_questions(tmp_path: Path) -> None:
    # The machine file changes one title, so a broken one must not cost the questions; `init`
    # reports it when it loads it. Mutation (oracle): catch `KeyError` instead of `Failure` ->
    # the machine file's refusal escapes and this reddens.
    machine = tmp_path / "machine.toml"
    machine.write_text("[overlay", encoding="utf-8")
    schema = questions(repository(tmp_path), machine=machine)
    assert tuple(schema["properties"]) == PROPERTIES
    overlay = {o["const"]: o["title"] for o in schema["properties"]["memory.mode"]["oneOf"]}
    assert overlay["overlay"] == OVERLAY_NEXT


@needs_git
def test_no_file_a_gate_reads_at_its_committed_path_is_offered_as_local(tmp_path: Path) -> None:
    # A gate reads the ledger, the roadmap and the trail where they are committed, and the
    # configuration and the ignore block work only at the root: offering one as local would be
    # offering a project a failing gate or a dead file. Mutation (by hand): `roadmap` added to
    # `LOCAL_ELIGIBLE` -> the disjointness assertion reddens.
    local = _schema(tmp_path, repository(tmp_path))["properties"]["artifacts.local"]
    assert local["default"] == []
    offered = set(local["items"]["enum"])
    assert offered
    assert not offered & {"bug-index", "ledger-audits", "roadmap", "trail", "config", "gitignore"}


@needs_git
def test_a_name_outside_the_grammar_is_left_to_ask_and_never_printed(tmp_path: Path) -> None:
    # The remote's last segment is repository-authored; outside the grammar it is neither the
    # default nor printed. Mutation (oracle): leniency keeps the name -> it becomes the default
    # and the `not in` assertions redden.
    schema = _schema(tmp_path, repository(tmp_path, origin="git@github.com:owner/Not A Name.git"))
    name = schema["properties"]["project.name"]
    assert "default" not in name and name["x-stayfixed-source"] == "not derivable"
    shown = card(schema)
    assert "not a name" not in repr(schema).lower() and "not a name" not in shown.lower()
    assert "  project.name: none; asked (not derivable; --name)\n" in shown


@needs_git
def test_the_questions_are_refused_where_init_would_refuse(tmp_path: Path) -> None:
    # A `stayfixed.toml` already answers every question, and a manifest means `init` has run:
    # asking in either case would collect answers nothing could write. Mutation (oracle): the
    # `stayfixed.toml` check disabled -> the first `raises` reddens.
    root = repository(tmp_path)
    (root / "stayfixed.toml").write_text(DOCUMENT, encoding="utf-8")
    with pytest.raises(Refusal, match=re.escape("already has a stayfixed.toml")):
        _schema(tmp_path, root)
    (root / MANIFEST_PATH).parent.mkdir(parents=True)
    (root / MANIFEST_PATH).write_text("{}", encoding="utf-8")
    with pytest.raises(Refusal, match="stayfixed upgrade"):
        _schema(tmp_path, root)
