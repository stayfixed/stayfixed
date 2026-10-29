"""The assess area's commands: `stayfixed assess` runs every configured gate and the inventory's
probes over the repository as it is, writes the inventory, and prints counts; `stayfixed gate`
judges a change's `stayfixed.toml` against its base's and runs the gates as that judgement says;
`stayfixed adopt promote` moves a project's gates from advisory to enforcing, one at a time, as
each passes.

Every module a handler needs is imported inside it, so discovering this area imports neither the
gates nor the presets.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import TYPE_CHECKING

from stayfixed.areas import SubParsers
from stayfixed.command import command_owner, common_flags, grammar, root_and_config
from stayfixed.result import Result

if TYPE_CHECKING:
    from stayfixed.assess.base import PlatformBase
    from stayfixed.assess.state import Transition

ASSESS_HELP = (
    "every configured gate and the inventory: what stands between this repository and enforcement"
)
# Any revision git resolves, unlike `gate` and `adopt promote`: `assess` is advice over a tree the
# person chose, and nothing it answers governs a run or writes enforcement.
BASE_HELP = (
    "the revision the plan and commit gates compare against, and bugs compares the ledger with "
    "(where HEAD forked from it), any git resolves: the inventory is advice and governs nothing; "
    "default "
    "refs/remotes/origin/<project.base_branch>"
)
ASSESS_BUILTIN_HELP = (
    "the built-in gates and the probes only: no command from [gates.custom] runs, for a "
    "repository whose commands you have not agreed to run"
)
GATE_HELP = "judge this change against the base's stayfixed.toml, then run the gates as it says"
BASE_REF_HELP = (
    "the base to compare against: a 40-character commit id or a refs/ name; "
    "default refs/remotes/origin/<project.base_branch>"
)
ONLY_HELP = "run only this gate, or `config` for the configuration check alone; repeat for several"
PR_BASE_HELP = (
    "the pull request's base as the platform reports it, empty on any other event; with "
    "--base-input and --default-branch, in place of --base"
)
BASE_INPUT_HELP = (
    "the caller workflow's base: input, empty for none; refused when it names another branch "
    "than --pr-base"
)
DEFAULT_BRANCH_HELP = "the repository's default branch, the base when the other two are empty"
PATH_HELP = (
    "the project root inside --root, as the caller workflow's path: input gives it; refused "
    "when it leaves --root"
)
# The platform's base is one form: the three flags the reusable workflow passes together, read in
# one order (`stayfixed.assess.base.platform_base`). A subset would be read as "empty" for the
# flags left out, and beside `--base` one of the two forms would be silently ignored.
PLATFORM_FLAGS = ("--pr-base", "--base-input", "--default-branch")
PLATFORM_SUBSET = (
    "--pr-base, --base-input and --default-branch are one form, the platform's base, and go "
    "together; missing: {missing}"
)
PLATFORM_AND_BASE = (
    "--base and the platform's base (--pr-base, --base-input, --default-branch) are two forms of "
    "one input; pass one"
)
WORKFLOW_SHA_HELP = (
    "the commit of the reusable workflow running, which the workflow passes from the platform; "
    "an upgrade's [ci] ref is admitted only when it equals this"
)
ANNOTATE_HELP = "also print each finding as a GitHub workflow command, capped per level"
SUMMARY_HELP = "append the summary as markdown to this file, as a job summary"
BUILTIN_HELP = (
    "the configuration check, whatever --only names, and the built-in gates only: no command "
    "from [gates.custom] runs"
)
CUSTOM_HELP = "the gates from [gates.custom] only, with no configuration check"
ADOPT_HELP = "adoption: promote gates from advisory to enforcing as they pass"
PROMOTE_HELP = "enforce the named gates if all pass now; with none named, each gate that passes"
PROMOTE_BUILTIN_HELP = (
    "the built-in gates only: no command from [gates.custom] runs, so no custom gate is "
    "promoted, for a repository whose commands you have not agreed to run"
)
GATES_HELP = "configured gate names (default: every gate not yet enforcing)"
# Formatted with `[project] base_branch`, which the loader holds to the branch grammar.
BASE_NOT_THERE = (
    "note: the base this run compares against is not in this checkout (no origin, or not "
    "fetched), so the gates that read it could not run: plan, commit, and bugs in a tree with "
    "no ledger; fetch it, or pass --base with a refs/ name or a commit id that exists, such as "
    "refs/heads/{branch}"
)
# The gates that read the base, whose not running the note may explain.
BASE_READERS = frozenset({"plan", "commit", "bugs"})
WAITING = (
    "note: a custom gate is promoted once the base's stayfixed.toml has its command, since "
    "`stayfixed gate` runs it only then; land it on the base branch first, then promote it"
)
NOT_RUN = (
    "note: --builtin ran no custom gate, and a custom gate is promoted only by a run that runs "
    "its command; without --builtin, adopt promote runs the commands [gates.custom] names"
)
# A gate `adopt promote` did not enforce because it reads a file CI's checkout will not have: one
# git does not track, or a symlink leading out of the repository. `{files}` are names found on disk,
# each through `printable`; `--json` carries them whole. `{remedy}` is the one `stayfixed assess`
# gives the same item (`stayfixed.assess.tracked`), so the two cannot drift apart.
UNTRACKED_NOTE = (
    "note: {gate} reads {files}, which CI's checkout will not have, so CI would fail {gate} on "
    "every pull request, and {gate} is not enforced; {remedy}"
)
CASE_NOTE = (
    "note: {gate} reads {files}, which git tracks only under a name that differs in case, so CI's "
    "checkout will not have them and {gate} is not enforced; {remedy}"
)
UNASKED_NOTE = (
    "note: git gave no answer to whether it tracks the files {gate} reads, so {gate} is not "
    "enforced; {remedy}"
)


def _base_missing(root: Path, base: str, unanswered: set[str]) -> bool:
    """Whether a gate that reads the base could not run, and the base is not in this checkout:
    then the note says why. The base is the parser's grammar, the loader's, or a revision a
    person typed, and is not printed."""
    from stayfixed.gitenv import git_run

    if not unanswered & BASE_READERS:
        return False
    return git_run(root, "rev-parse", "--verify", "--quiet", "--end-of-options", base)[0] != 0


def run_assess(args: argparse.Namespace) -> Result:
    from stayfixed.assess.assessment import NOT_IGNORED, assess, document, ignored, render, write

    root = Path(args.root).resolve()
    machine = Path(args.machine) if args.machine else None
    assessment = assess(
        root, machine=machine, base=args.base, builtin=args.builtin, owner=command_owner(machine)
    )
    write(root, assessment)
    summary = render(assessment)
    unanswered = {g.name for g in assessment.gates if not g.answered}
    if _base_missing(root, assessment.base, unanswered):
        summary += "\n\n" + BASE_NOT_THERE.format(branch=assessment.base_branch)
    if ignored(root) is False:
        summary += f"\n\n{NOT_IGNORED}"
    return Result(summary, document(assessment), exit_code=1 if assessment.would_fail else 0)


def _platform(args: argparse.Namespace, checkout: Path) -> PlatformBase | None:
    """The platform's base `stayfixed gate` was given, `None` when it was given `--base` or
    neither; a subset of its three flags, or the form beside `--base`, is refused."""
    from stayfixed.assess.base import PlatformBase
    from stayfixed.errors import Refusal

    given = (args.pr_base, args.base_input, args.default_branch)
    if all(value is None for value in given):
        return None
    missing = [flag for flag, value in zip(PLATFORM_FLAGS, given, strict=True) if value is None]
    if missing:
        raise Refusal(PLATFORM_SUBSET.format(missing=", ".join(missing)))
    if args.base is not None:
        raise Refusal(PLATFORM_AND_BASE)
    return PlatformBase(checkout, args.pr_base, args.base_input, args.default_branch)


def run_gate(args: argparse.Namespace) -> Result:
    from stayfixed import __version__
    from stayfixed.assess.base import platform_root
    from stayfixed.assess.change import NOTHING_TO_RUN, gate_change
    from stayfixed.assess.report import (
        BUILTIN_FINDINGS_ELSEWHERE,
        FINDINGS_ELSEWHERE,
        NOT_ON_BASE,
        config_line,
        gate_line,
        gate_row,
        mode,
        summary,
        workflow_commands,
    )
    from stayfixed.release.api import is_released
    from stayfixed.runner import subprocess_runner

    checkout = Path(args.root).absolute()
    platform = _platform(args, checkout)
    root = checkout if args.path is None else platform_root(checkout, args.path)
    machine = Path(args.machine) if args.machine else None
    # The owner's layer, once for the run: the tree's load and both of the verdict's take it, so
    # what the machine file read past is said once and not once a document.
    owner = command_owner(machine)
    runner = subprocess_runner()
    gate_run = gate_change(
        root,
        base=args.base,
        platform=platform,
        only=args.only,
        part=args.part,
        machine=machine,
        owner=owner,
        workflow_sha=args.workflow_sha,
        running=__version__,
        released=lambda sha: is_released(sha, runner, cwd=root),
    )
    verdict, results, waiting = gate_run.verdict, gate_run.results, gate_run.waiting
    lines = [config_line(verdict)] if gate_run.judged else []
    lines += [gate_line(r, enforcing=r.name in verdict.enforcing) for r in results]
    lines += [f"{name}: {mode(name in verdict.enforcing)}, {NOT_ON_BASE}" for name in waiting]
    data = {
        "config": {
            "judged": gate_run.judged,
            "changes": [{"key": c.key, "verdict": c.verdict.value} for c in verdict.changes],
            "refused": verdict.refused,
            "enforcing": sorted(verdict.enforcing),
        },
        "gates": [gate_row(r, enforcing=r.name in verdict.enforcing) for r in results],
        "not_on_base": list(waiting),
    }
    if not lines:
        # Not a refusal: the workflow runs `--custom` on every caller, most of which have no
        # gate of their own.
        return Result(NOTHING_TO_RUN, data, exit_code=0)
    if args.summary:
        # The command's one write. The path is argv: in CI the platform's job summary, which
        # stayfixed's own workflow passes, and locally a path a person typed; no value in the
        # repository chooses it.
        with Path(args.summary).open("a", encoding="utf-8") as stream:
            stream.write(summary(gate_run))
    if gate_run.exit_code and any(result.failing for result in results):
        # Only on a run that fails: an advisory gate's findings are the ordinary state of an
        # adoption, and its line already counts them.
        lines.append(BUILTIN_FINDINGS_ELSEWHERE if args.part == "builtin" else FINDINGS_ELSEWHERE)
    if args.annotate:
        lines += workflow_commands(gate_run)
    return Result("\n".join(lines), data, exit_code=gate_run.exit_code)


def _transition(transition: Transition) -> dict[str, object]:
    """`--json` for `adopt promote`: a row per gate it ran in the shape every gate command gives
    one, enforcing when this run promoted it, and the same outcomes by name."""
    from stayfixed.assess.report import gate_row

    promoted = set(transition.promoted)
    return {
        "gates": [gate_row(r, enforcing=r.name in promoted) for r in transition.results],
        "promoted": list(transition.promoted),
        "failing": transition.failing,
        "unanswered": list(transition.unanswered),
        "not_on_base": list(transition.waiting),
        "skipped": list(transition.skipped),
        "untracked": {
            u.gate: list(u.files) for u in transition.unseen if u.git_answered and u.files
        },
        "case_differs": {u.gate: list(u.case_differs) for u in transition.unseen if u.case_differs},
    }


def run_adopt_promote(args: argparse.Namespace) -> Result:
    from stayfixed.assess.report import (
        BUILTIN_FINDINGS_ELSEWHERE,
        FINDINGS_ELSEWHERE,
        findings_text,
    )
    from stayfixed.assess.state import promote
    from stayfixed.assess.tracked import CASE_REMEDY, REMEDY, UNASKED_REMEDY
    from stayfixed.config.layout import local_base
    from stayfixed.findings import listed
    from stayfixed.printed import printable

    machine = Path(args.machine) if args.machine else None
    # Once for the command: the base's copy a custom gate is promoted against loads under it too.
    owner = command_owner(machine)
    root, config = root_and_config(args, owner=owner)
    base = args.base or local_base(config)
    transition = promote(
        root, config, args.gates, base=base, machine=machine, builtin=args.builtin, owner=owner
    )
    # Gate names only: the loader holds each to a grammar, and a count is stayfixed's own.
    advisory = [f"{r.name} ({findings_text(r)})" for r in transition.results if r.failing]
    advisory += [f"{name} (not on the base)" for name in transition.waiting]
    advisory += [f"{name} (not run, as --builtin asked)" for name in transition.skipped]
    # Both lists capped, since custom gates are the repository's to add; `--json` has each.
    parts = [f"promoted: {listed(list(transition.promoted)) or 'nothing'}"]
    if advisory:
        parts.append(f"still advisory: {listed(advisory)}")
    lines = ["; ".join(parts)]
    if advisory:
        if _base_missing(root, base, set(transition.unanswered)):
            lines.append(BASE_NOT_THERE.format(branch=config.project.base_branch))
        if transition.waiting:
            lines.append(WAITING)
        if transition.skipped:
            lines.append(NOT_RUN)
        for unseen in transition.unseen:
            if not unseen.git_answered:
                lines.append(UNASKED_NOTE.format(gate=unseen.gate, remedy=UNASKED_REMEDY))
                continue
            if unseen.files:
                files = listed([printable(name) for name in unseen.files])
                remedy = REMEDY.format(gate=unseen.gate)
                lines.append(UNTRACKED_NOTE.format(gate=unseen.gate, files=files, remedy=remedy))
            if unseen.case_differs:
                cased = listed([printable(name) for name in unseen.case_differs])
                lines.append(CASE_NOTE.format(gate=unseen.gate, files=cased, remedy=CASE_REMEDY))
        lines.append(BUILTIN_FINDINGS_ELSEWHERE if args.builtin else FINDINGS_ELSEWHERE)
    data = _transition(transition)
    return Result("\n".join(lines), data, exit_code=1 if advisory else 0)


def register(groups: SubParsers) -> None:
    from stayfixed.assess.base import BASE_REF, BASE_SHAPE

    # `--base` for `stayfixed gate`, whose verdict reads the base's `stayfixed.toml`, and `adopt
    # promote`, which writes enforcement off the comparison: refused at the parser unless it is a
    # full commit id or a full `refs/` name, since git resolves a shorter name through the tags
    # first and a tag of that spelling would decide either.
    base_ref = grammar(BASE_REF, BASE_SHAPE)
    parser = common_flags(groups.add_parser("assess", help=ASSESS_HELP))
    parser.add_argument("--base", default=None, help=BASE_HELP)
    parser.add_argument("--builtin", action="store_true", help=ASSESS_BUILTIN_HELP)
    parser.set_defaults(func=run_assess)

    gate = common_flags(groups.add_parser("gate", help=GATE_HELP))
    gate.add_argument("--only", action="append", default=None, metavar="NAME", help=ONLY_HELP)
    gate.add_argument("--base", default=None, type=base_ref, help=BASE_REF_HELP)
    gate.add_argument("--pr-base", default=None, metavar="BRANCH", help=PR_BASE_HELP)
    gate.add_argument("--base-input", default=None, metavar="BRANCH", help=BASE_INPUT_HELP)
    gate.add_argument("--default-branch", default=None, metavar="BRANCH", help=DEFAULT_BRANCH_HELP)
    gate.add_argument("--path", default=None, metavar="PATH", help=PATH_HELP)
    part = gate.add_mutually_exclusive_group()
    part.add_argument(
        "--builtin", dest="part", action="store_const", const="builtin", help=BUILTIN_HELP
    )
    part.add_argument(
        "--custom", dest="part", action="store_const", const="custom", help=CUSTOM_HELP
    )
    gate.add_argument("--workflow-sha", default=None, metavar="SHA", help=WORKFLOW_SHA_HELP)
    gate.add_argument("--annotate", action="store_true", help=ANNOTATE_HELP)
    gate.add_argument("--summary", default=None, metavar="FILE", help=SUMMARY_HELP)
    gate.set_defaults(func=run_gate)

    adopt = groups.add_parser("adopt", help=ADOPT_HELP)
    adopt_sub = adopt.add_subparsers(dest="command", metavar="<command>")
    promotion = common_flags(adopt_sub.add_parser("promote", help=PROMOTE_HELP))
    promotion.add_argument("gates", nargs="*", metavar="GATE", help=GATES_HELP)
    promotion.add_argument("--base", default=None, type=base_ref, help=BASE_REF_HELP)
    promotion.add_argument("--builtin", action="store_true", help=PROMOTE_BUILTIN_HELP)
    promotion.set_defaults(func=run_adopt_promote)
