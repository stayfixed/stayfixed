"""The advisory memory link graph: every `[[link]]` resolves, no link is immediately repeated, no
ledger identifier is bracketed. `memory refs` reports it as notices, beside the stale paths it
finds. stayfixed:ledger:fixtures — `BR-` strings here are sample data.
"""

from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from stayfixed.cli import build_parser, discover_registrars, run
from stayfixed.config.loader import load
from stayfixed.config.schema import Config
from stayfixed.memory.graph import check_memory_graph
from stayfixed.memory.notes import Walk, walk
from stayfixed.memory.store import resolve

CONFIG = """
[stayfixed]
version = "0.1.0"
state = "installed"
preset = "recommended"
profile = ""
agents = ["claude"]

[project]
name = "widget"
base_branch = "main"
release_branch = "main"

[paths]
memory = "notes"

[memory]
mode = "in-repo"
groups = ["developer", "project-stable"]
"""


def project(tmp_path: Path) -> tuple[Path, Config]:
    root = tmp_path / "widget"
    for name in ("notes/developer", "notes/project-stable"):
        (root / name).mkdir(parents=True)
    (root / "stayfixed.toml").write_text(CONFIG, encoding="utf-8")
    return root, load(root, machine=tmp_path / "m.toml")


def note(root: Path, group: str, name: str, body: str) -> None:
    (root / "notes" / group / f"{name}.md").write_text(
        f"---\nname: {name}\ndescription: d\nmetadata:\n  type: feedback\n---\n\n{body}",
        encoding="utf-8",
    )


def graph(root: Path, config: Config) -> list[tuple[str, str, str]]:
    store = resolve(root, config, machine=root.parent / "m.toml")
    assert store is not None
    walked = walk(store.path, [g for g in config.memory.groups if g in store.groups])
    return [(f.rule, f.path, f.detail) for f in check_memory_graph(store, config, walked)]


def test_a_whole_store_passes(tmp_path: Path) -> None:
    root, config = project(tmp_path)
    note(root, "developer", "a", "see [[b]] and [[protocol]]\n")
    note(root, "project-stable", "b", "see [[a]]\n")
    (root / "notes" / "protocol.md").write_text("# protocol\n", encoding="utf-8")
    assert graph(root, config) == []


def test_a_dead_link_a_repeat_and_a_bracketed_identifier_are_each_noted(tmp_path: Path) -> None:
    root, config = project(tmp_path)
    note(root, "developer", "a", "see [[gone]], [[b]] and [[b]], and [[BR-042]]\n")
    note(root, "project-stable", "b", "x\n")
    # Text order: the two link rules run over the links as written, then the repeat rule.
    assert graph(root, config) == [
        ("dead-wiki-link", "developer/a.md", "gone"),
        ("bracketed-identifier", "developer/a.md", "BR-042"),
        ("repeated-link", "developer/a.md", "b"),
    ]


def test_a_bracketed_identifier_is_the_bug_ledgers_as_the_project_configures_it(
    tmp_path: Path,
) -> None:
    # Mutation (oracle): the notice reads the default prefix whatever `[ledger] id_prefix` says
    # -> `[[DF-042]]` reads as a dead link and `[[BR-042]]` as an identifier.
    root, config = project(tmp_path)
    config = replace(config, ledger=replace(config.ledger, id_prefix="DF"))
    note(root, "developer", "a", "see [[DF-042]] and [[BR-042]]\n")
    assert graph(root, config) == [
        ("bracketed-identifier", "developer/a.md", "DF-042"),
        ("dead-wiki-link", "developer/a.md", "BR-042"),
    ]


def test_a_link_inside_a_code_span_or_fence_is_not_a_link_and_code_between_links_is_not_a_repeat(
    tmp_path: Path,
) -> None:
    # Mutation: stop blanking code spans — the `[[ -f x ]]` case reddens.
    root, config = project(tmp_path)
    note(root, "developer", "a", "`[[ -f x ]]` and\n```\n[[gone]]\n```\n[[b]] `x` [[b]]\n")
    note(root, "project-stable", "b", "x\n")
    assert graph(root, config) == []


def test_every_adjacent_repeat_form_is_noted(tmp_path: Path) -> None:
    root, config = project(tmp_path)
    note(root, "developer", "a", "[[b]], [[b]] and [[b]] or [[b]]\n")
    note(root, "project-stable", "b", "x\n")
    assert [f for f in graph(root, config) if f[0] == "repeated-link"] == [
        ("repeated-link", "developer/a.md", "b")
    ] * 3


def test_refs_reports_graph_notices_without_changing_its_exit(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # The graph is advice: the store is shared by every session on the machine, so a sibling's
    # half-finished sweep is not this tree's fault to fail on, and the exit code is the one part
    # of that promise a caller acts on without reading. A dangling `[[link]]` is a notice, counted
    # on the line and listed in `--json`; only a stale path is a finding. Mutation (declared):
    # `mutations/`'s "an advisory memory-graph notice gates the exit code".
    root, _config = project(tmp_path)
    note(root, "developer", "a", "see [[gone]]\n")
    argv = ["memory", "refs", "--root", str(root), "--machine", str(tmp_path / "m.toml")]
    assert run([*argv, "--json"], parser=build_parser(discover_registrars())) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["findings"] == []
    assert [(n["rule"], n["path"], n["detail"]) for n in data["notices"]] == [
        ("dead-wiki-link", "developer/a.md", "gone")
    ]
    assert "1 advisory link-graph notice(s)" in data["summary"]


def test_refs_walks_the_store_once_for_its_findings_and_the_graph(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The graph's notices are read from the walk `memory refs` made for its own findings, so a
    # store is read once per command, whatever the graph finds. Counted at every name the walk is
    # reachable by — the note module's own and each loaded `stayfixed` module's binding of it —
    # because a spy on the one name `memory.refs` binds left green a second walk the graph made
    # through `stayfixed.memory.notes.walk` (`mutations/`'s "the memory graph walks the store a
    # second time").
    import stayfixed.memory.notes as notes
    import stayfixed.memory.refs as refs

    root, config = project(tmp_path)
    note(root, "developer", "a", "see [[gone]]\n")
    calls: list[Path] = []

    def counted(path: Path, groups: list[str]) -> Walk:
        calls.append(path)
        return walk(path, groups)

    for module in [m for name, m in sys.modules.items() if name.startswith("stayfixed.")]:
        if getattr(module, "walk", None) is walk:
            monkeypatch.setattr(module, "walk", counted)
    # The spy reached the name `check_refs` calls and the note module's own, so a count of one is
    # not a count of none.
    assert vars(refs)["walk"] is counted
    assert notes.walk is counted
    store = resolve(root, config, machine=root.parent / "m.toml")
    assert store is not None
    report = refs.check_refs(root, config, store)
    assert [(n.rule, n.detail) for n in report.notices] == [("dead-wiki-link", "gone")]
    assert calls == [store.path]
