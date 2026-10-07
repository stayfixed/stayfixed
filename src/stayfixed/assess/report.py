"""What a gate run hands a person: its exit code, the platform's workflow commands, and a job
summary; and the one shape every command gives a gate's result, as a line, a table cell and a
`--json` row.

**What prints.** Counts, gate names, modes, rule ids and changed key names: stayfixed's own
vocabulary, or a name the loader bounded. A finding's `detail` can quote the repository and never
prints here. A finding's path is a name found on disk or in a diff, so it is written as an
annotation's `file=` only when it matches `PATH_VALUE`, the one grammar a path may print in;
escaping bounds a workflow command's shape, not its characters. The summary carries no path at
all.

**The platform's bound.** A step shows ten annotations per level and drops the rest without a
word, so every command goes through one emitter capped per level, and past the cap one
`::notice::` counts what was held back.

**One gate result, one shape.** `stayfixed assess`, `stayfixed gate` and `stayfixed adopt promote`
each report the gates they ran, and each does it through `gate_row` for `--json`, `gate_line`
or `findings_text` for a printed line and `count_cell` for a table, so a gate that could not
judge the tree is spelled `could not run` everywhere and carries the same keys everywhere. A
custom gate `stayfixed gate` did not start because the run had already failed is its own case in
each: its reason in place of the count, and `not run` in a table.

**What fails the run.** An enforced gate that is failing, and, when the configuration check ran,
a key the rule refused. An advisory gate's findings are annotated and never fail it, and nor does
a custom gate left waiting because the base does not have its command: the base enforces no
command it lacks.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from stayfixed.assess.gates import ALREADY_FAILED, GateResult
from stayfixed.assess.rule import ConfigVerdict, Verdict
from stayfixed.config.loader import CONFIG_FILE
from stayfixed.findings import listed
from stayfixed.printed import PATH_VALUE

ANNOTATION_CAP = 10

REFUSED_KEY = "{key} may not change this way in a pull request"
HELD = "{count} more {level} annotation(s) not shown; the job summary counts them all"
# The two answers the configuration check gives without a key: spelled once, for the printed line
# and the job summary alike.
BOOTSTRAP = "the base has no stayfixed.toml at this path, so this tree's decides"
UNCHANGED = "stayfixed.toml unchanged from the base"
# The last line of a run a gate failed: the lines are counts, and this says where what they count
# is. Fixed text, so nothing a repository wrote reaches it. A run under `--builtin` names the
# command with `--builtin` too: the line is relayed as what to run next, and a run asked to leave
# the custom gates' commands alone hands over none that runs them.
FINDINGS_ELSEWHERE = (
    "details: `stayfixed assess --json` lists every finding, and each gate's own command shows "
    "its own"
)
BUILTIN_FINDINGS_ELSEWHERE = (
    "details: `stayfixed assess --builtin --json` lists every finding of the built-in gates, and "
    "each gate's own command shows its own"
)
# A custom gate whose command the base does not have: the change added or re-commanded it, and
# it runs once it lands there.
NOT_ON_BASE = "not run until the base has this command"
# A gate that could not judge the tree, wherever its count would print: `answered` is false and
# `reason` names the command that shows why.
UNANSWERED = "could not run"


def mode(enforcing: bool) -> str:
    return "enforcing" if enforcing else "advisory"


def count_cell(result: GateResult) -> int | str:
    """A table's findings cell: the count, `UNANSWERED`, or `not run` for a gate never started."""
    if not result.ran:
        return "not run"
    return len(result.findings) if result.answered else UNANSWERED


def findings_text(result: GateResult) -> str:
    """`N finding(s)`, `UNANSWERED`, or, for a gate never started, its reason, for a printed
    line."""
    if not result.ran:
        return result.reason
    return f"{len(result.findings)} finding(s)" if result.answered else UNANSWERED


def gate_line(result: GateResult, *, enforcing: bool) -> str:
    """`<name>: <mode>, N finding(s)` or `<name>: <mode>, could not run`."""
    return f"{result.name}: {mode(enforcing)}, {findings_text(result)}"


def gate_row(result: GateResult, *, enforcing: bool) -> dict[str, Any]:
    """A gate's `--json` row, one shape for every command that runs gates. Counts, a name the
    loader bounded and the fixed `reason`; a finding's detail is never in it."""
    return {
        "name": result.name,
        "enforcing": enforcing,
        "answered": result.answered,
        "reason": result.reason,
        "count": len(result.findings),
        "failing": result.failing,
    }


@dataclass(frozen=True)
class GateRun:
    verdict: ConfigVerdict
    results: tuple[GateResult, ...]
    judged: bool  # whether the configuration check ran, and so whether a refusal counts
    prefix: str = ""  # the project root inside the repository, as `repository_prefix` gives it
    waiting: tuple[str, ...] = ()  # custom gates not run: the base does not have their command

    @property
    def blocking(self) -> tuple[str, ...]:
        """The enforced gates that are failing."""
        enforcing = self.verdict.enforcing
        return tuple(r.name for r in self.results if r.failing and r.name in enforcing)

    @property
    def exit_code(self) -> int:
        return 1 if self.blocking or (self.judged and self.verdict.refused) else 0


def _data(text: str) -> str:
    return text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def workflow_commands(run: GateRun, *, cap: int = ANNOTATION_CAP) -> list[str]:
    """One `error` per refused key, then one annotation per finding or unanswered gate, `error`
    for an enforcing gate and `warning` for an advisory one, at most `cap` per level."""
    lines: list[str] = []
    shown = {"error": 0, "warning": 0}
    held = {"error": 0, "warning": 0}

    def emit(level: str, path: str, line: int | None, message: str) -> None:
        if shown[level] >= cap:
            held[level] += 1
            return
        shown[level] += 1
        where = ""
        located = run.prefix + path if path else ""
        # Printed only inside the one grammar a path may print in: a finding's path is a name
        # found on disk or in a diff, and escaping bounds a command's shape, not its characters.
        if located and PATH_VALUE.match(located):
            where = f" file={located}" + (f",line={line}" if line is not None else "")
        lines.append(f"::{level}{where}::{_data(message)}")

    if run.judged:
        for change in run.verdict.changes:
            if change.verdict is Verdict.REFUSED:
                emit("error", CONFIG_FILE, None, REFUSED_KEY.format(key=change.key))
    for result in run.results:
        level = "error" if result.name in run.verdict.enforcing else "warning"
        if not result.answered:
            emit(level, "", None, f"{result.name}: {result.reason}")
        # A `commit` finding's path is the commit's id, and the platform would look for a file.
        located_here = result.name != "commit"
        for finding in result.findings:
            path = finding.path if located_here else ""
            emit(level, path, finding.line, f"{result.name}: {finding.rule}")
    for name in run.waiting:
        emit("warning", "", None, f"{name}: {NOT_ON_BASE}")
    for level, count in held.items():
        if count:
            lines.append(f"::notice::{HELD.format(count=count, level=level)}")
    return lines


def config_line(verdict: ConfigVerdict) -> str:
    """The configuration check's printed line: how many keys changed and which were refused, by
    name, or one of the two answers without a key."""
    if verdict.base_state is None:
        return f"config: {BOOTSTRAP}"
    if not verdict.changes:
        return f"config: {UNCHANGED}"
    refused = [c.key for c in verdict.changes if c.verdict is Verdict.REFUSED]
    line = f"config: {len(verdict.changes)} change(s), {len(refused)} refused"
    # Capped: a custom gate's key is the repository's to add, and the summary's table names each.
    return line + (f": {listed(refused)}" if refused else "")


def _outcome(result: GateResult, enforcing: bool) -> str:
    if not result.ran:
        return ALREADY_FAILED
    if not result.failing:
        return "passes"
    return "fails" if enforcing else "would fail"


def summary(run: GateRun) -> str:
    """The job summary, as markdown: each gate's mode, count and outcome, then, when the
    configuration check ran, each changed key's verdict. Counts and names only."""
    blocks: list[list[str]] = []
    if run.results or run.waiting:
        rows = ["| gate | mode | findings | verdict |", "|---|---|---|---|"]
        for result in run.results:
            enforcing = result.name in run.verdict.enforcing
            cells = (result.name, mode(enforcing), count_cell(result), _outcome(result, enforcing))
            rows.append("| {} | {} | {} | {} |".format(*cells))
        for name in run.waiting:
            enforcing = name in run.verdict.enforcing
            rows.append(f"| {name} | {mode(enforcing)} | not run | {NOT_ON_BASE} |")
        blocks.append(rows)
    if run.judged:
        if run.verdict.base_state is not None and run.verdict.changes:
            rows = ["| stayfixed.toml key | verdict |", "|---|---|"]
            rows += [f"| {c.key} | {c.verdict.value} |" for c in run.verdict.changes]
            blocks.append(rows)
        else:
            blocks.append([config_line(run.verdict)])
    return "\n\n".join("\n".join(block) for block in blocks) + "\n"
