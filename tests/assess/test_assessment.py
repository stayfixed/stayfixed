"""The inventory `stayfixed assess` writes: every configured gate over the smoke fixture, each
gate finding as an item, the one serialisation, and a summary that prints counts and never a
path."""

from __future__ import annotations

import json
from pathlib import Path

from stayfixed.assess.assessment import (
    FORMAT,
    NOT_IGNORED,
    SKIPPED,
    UNNAMED,
    Assessment,
    _gate_items,
    assess,
    document,
    ignored,
    render,
    write,
)
from stayfixed.assess.gates import BUILTIN, GateResult
from stayfixed.config.layout import IGNORE_BODY
from stayfixed.findings import LISTED_LIMIT, Finding
from stayfixed.project.api import ASSESSMENT
from tests.assess.smoke import BASE, smoke_repo
from tests.cli import cli
from tests.gitfixture import git, needs_git

# One word a line, so the file is over the line budget and nothing else a word could trip.
OVER_BUDGET = "".join("word\n" for _ in range(400))


def _machine(tmp_path: Path) -> Path:
    return tmp_path / "m.toml"


def _over_budget(tmp_path: Path) -> Path:
    """The smoke copy with its `AGENTS.md` replaced by 400 one-word lines."""
    root = smoke_repo(tmp_path)
    (root / "AGENTS.md").write_text(OVER_BUDGET, encoding="utf-8")
    return root


@needs_git
def test_the_smoke_fixture_would_fail_no_gate(tmp_path: Path) -> None:
    # The closing criterion: against `BASE` every built-in judges something, and none fails.
    # No mutation of its own — each gate's finding cases hold that gate.
    root = smoke_repo(tmp_path)
    assessment = assess(root, machine=_machine(tmp_path), base=BASE)
    assert assessment.would_fail == ()
    assert tuple(g.name for g in assessment.gates) == tuple(g.name for g in BUILTIN)


@needs_git
def test_the_inventory_records_its_base_and_lands_where_git_ignores_it(tmp_path: Path) -> None:
    # Mutation: drop the `"base"` key from `document` -> the tuple below reddens on a KeyError.
    root = smoke_repo(tmp_path)
    assessment = assess(root, machine=_machine(tmp_path), base=BASE)
    write(root, assessment)
    written = json.loads((root / ASSESSMENT).read_text(encoding="utf-8"))
    assert written == json.loads(json.dumps(document(assessment)))
    assert (written["format"], written["base"], len(written["gates"])) == (FORMAT, BASE, 5)
    assert git(root, "check-ignore", "--", ASSESSMENT).strip() == ASSESSMENT


def test_the_ignore_region_keeps_the_inventory_out_of_git() -> None:
    # Mutation: drop the inventory's entry from `config.layout.LOCAL_STATE_PATHS` -> reddens.
    assert ASSESSMENT in IGNORE_BODY.splitlines()


@needs_git
def test_a_gate_finding_is_an_item_with_the_gate_s_rule_and_remedy(tmp_path: Path) -> None:
    # Mutation: `items = [i for r in results ...]` becomes `items = []` in `assess` -> the
    # comprehension below finds nothing and the equality reddens.
    root = _over_budget(tmp_path)
    assessment = assess(root, machine=_machine(tmp_path), base=BASE)
    docs = next(g for g in BUILTIN if g.name == "docs")
    found = [i for i in assessment.items if i.rule == "agents-lines"]
    assert [(i.probe, i.count, i.where) for i in found] == [
        ("docs", 1, ("AGENTS.md [agents-lines]",))
    ]
    assert found[0].remedy == docs.remedy


@needs_git
def test_the_summary_prints_counts_and_never_a_path(tmp_path: Path) -> None:
    # Declared: `mutations/`'s "the assess summary prints each finding's path instead of a count".
    root = _over_budget(tmp_path)
    summary = render(assess(root, machine=_machine(tmp_path), base=BASE))
    lines = summary.splitlines()
    assert "| docs | yes | 2 | yes |" in lines
    assert [line for line in lines if line.startswith("| docs | agents-lines | warning | 1 |")]
    assert "AGENTS.md" not in summary


@needs_git
def test_an_inventory_git_does_not_ignore_is_named_in_the_summary(tmp_path: Path) -> None:
    # Mutation: drop the `ignored(root) is False` branch in `run_assess` -> the last line is the
    # table's and the first assertion on the summary reddens.
    kept = smoke_repo(tmp_path / "kept")
    bare = smoke_repo(tmp_path / "bare")
    (bare / ".gitignore").unlink()
    git(bare, "commit", "-qam", "chore: no ignore region")
    summaries = {}
    for name, root in (("kept", kept), ("bare", bare)):
        argv = ("assess", "--base", BASE, "--json")
        code, out, err = cli(root, tmp_path, *argv, machine=_machine(tmp_path))
        assert code == 0, err
        summaries[name] = json.loads(out)["summary"]
    assert ignored(bare) is False
    assert summaries["bare"].splitlines()[-1] == NOT_IGNORED
    assert ignored(kept) is True
    assert NOT_IGNORED not in summaries["kept"]


def test_a_gate_finding_outside_the_path_grammar_is_withheld_without_pointing_at_json() -> None:
    # A gate's labels go into `assess --json` and the inventory file the adoption skill has the
    # model read, so a name outside the path grammar is withheld there as on a summary line —
    # but "see --json" would point at the very text the reader holds, so the stand-in is assess's
    # own. Mutation: build the item's `where` from `finding.label` — this reddens.
    docs = next(gate for gate in BUILTIN if gate.name == "docs")
    result = GateResult("docs", (Finding("dead-link", "docs/My Plan.md", 3, "d"),))
    (only,) = _gate_items(docs, result)
    assert only.where == (f"{UNNAMED}:3 [dead-link]",)
    assert "--json" not in UNNAMED


def test_the_custom_gates_builtin_left_out_are_named_at_most_to_the_listed_limit() -> None:
    # Custom gates are the repository's to add, so `--builtin` can leave out any number of them:
    # the summary names the first `LISTED_LIMIT` and counts the rest, and the inventory file's
    # `skipped` carries every one. Mutation (oracle): `mutations/`'s "assess names every custom gate
    # --builtin left out" -> this reddens.
    names = tuple(f"g{n:02}" for n in range(LISTED_LIMIT + 3))
    text = render(Assessment("HEAD", "main", "adopting", (), (), (), skipped=names))
    shown = ", ".join(names[:LISTED_LIMIT]) + ", and 3 more"
    assert SKIPPED.format(names=shown) in text.splitlines()
