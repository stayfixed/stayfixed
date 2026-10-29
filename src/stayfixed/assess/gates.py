"""Every configured gate as a value: each built-in is its own area's gate function, and a
project's custom gate is the argv its `[gates.custom.<name>] run` configures.

A built-in's composition lives once, in its area, and that area's command answers with the same
function or with the one call it wraps, so what `run_gates` judges and what a person runs cannot
drift apart. Every gate is a `GateFn`, `(root, config, base)`, so each one is a value here
whether it reads the base or not.

A gate that could not judge the tree is not a passing gate: its result is `answered=False`, and
`failing` counts it. That is the one contract: a gate function that cannot judge raises a
`StayfixedError`, and never returns a finding that stands for "could not look", so every command
that runs gates reads one cause one way. Its `reason` is fixed text built from the gate's own
command, its name and the configured bound, never from an exception's text or the base, because
both can carry what a repository authored. A custom gate's output goes to this process's
standard error as it ran and is read by nothing here, so none of it reaches a result.

**A custom gate's process group ends with it.** Its command runs in a session of its own, and
that session's process group is ended however the command finishes — exit, timeout or
interrupt, in the order `stayfixed.processes` keeps — so nothing it left in the background in
that group writes into the tree while a later gate runs or after the result is out. A
descendant that leaves the command's process group (a new session, or a job-control shell's own
group) is not reached, and nor is one stayfixed may not signal (a sudo or setuid descendant).
On a timeout or an interrupt the group is sent SIGTERM, then SIGKILL once the command has exited
or had its grace (`stayfixed.processes.end`); the grace watches the command alone, so behind a
shell leader that dies on SIGTERM it is the leader's, and a runner `stayfixed prove` started that
ignores SIGTERM outlives it, a limit of this bound.

**Order.** The built-ins run first, in configured order: they execute nothing the repository
wrote. Then the custom gates the caller names in `first`, then every other custom gate. A custom
gate executes files the change can edit, so one that ran earlier could rewrite what a later one
executes; `stayfixed gate` names the base's enforced gates in `first`, so no other custom gate
runs before them. And it starts no custom gate at all once its run has failed (`failed`, then
`stopped`), one of the base's enforced gates included: a custom gate runs files the change can
edit in the process that holds the verdict, and a command that can rewrite that process could
turn the failure into a pass.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, TypeAlias

from stayfixed import processes
from stayfixed.docs.api import docs_gate, docs_reads, plan_gate, trail_gate, trail_reads
from stayfixed.errors import StayfixedError
from stayfixed.findings import Finding
from stayfixed.guards.api import commit_gate
from stayfixed.ledger.api import bugs_gate

if TYPE_CHECKING:
    from stayfixed.config.schema import Config

BASE = "<base>"  # where the base goes in a gate's command; the base itself is never printed
# Every gate's shape, a built-in's and a custom gate's: `(root, config, base)`, whether the gate
# reads the base or not, to its findings; a gate that cannot judge the tree raises.
GateFn: TypeAlias = "Callable[[Path, Config, str], list[Finding]]"

COULD_NOT_RUN = "could not judge this tree; `stayfixed {command}` names the cause"
CUSTOM_COULD_NOT_RUN = (
    "the command in [gates.custom.{name}] run could not start, or ran past {seconds}s"
)
CUSTOM_REMEDY = "fix what [gates.custom.{name}] run reports; its output is printed as it ran"
# A custom gate `stayfixed gate` did not start because the run had already failed: any custom gate,
# one the base enforces included, can run files the change can edit, in the process that holds
# the verdict.
ALREADY_FAILED = "the run had already failed"
STOPPED = f"not run: {ALREADY_FAILED}"


@dataclass(frozen=True)
class GateContext:
    root: Path
    config: Config
    base: str


@dataclass(frozen=True)
class GateResult:
    name: str
    findings: tuple[Finding, ...]
    answered: bool = True
    reason: str = ""
    ran: bool = True  # false for a gate `stopped` answers for: it was never started

    @property
    def failing(self) -> bool:
        """A finding fails the gate, and so does a gate that could not judge the tree."""
        return bool(self.findings) or not self.answered


def stopped(name: str) -> GateResult:
    """The result of a gate that was not started because the run had already failed: it judged
    nothing, so it is not a passing gate, and its reason says why it did not run."""
    return GateResult(name, (), False, STOPPED, ran=False)


@dataclass(frozen=True)
class Gate:
    name: str
    principle: int | None
    remedy: str
    command: str  # what a person runs for this gate, with BASE where the base goes
    run: GateFn
    # The files the gate reads by path, there or not, when an absent one changes its verdict: a
    # checkout that lacks one judges otherwise (`stayfixed.assess.tracked`). `None` for a gate that
    # reads none that way: one that reads git, or a custom gate, whose reads stayfixed cannot know.
    reads: Callable[[Path, Config], list[Path]] | None = None


BUILTIN: tuple[Gate, ...] = (
    Gate(
        "docs",
        None,
        "run `stayfixed docs check` and fix each finding; a checked document kept out of git "
        "(ignored, never added, or under [artifacts] local) drops docs from [gates] builtin "
        "instead",
        "docs check",
        docs_gate,
        docs_reads,
    ),
    Gate(
        "bugs",
        1,
        f"run `stayfixed bugs check --base {BASE}` and fix each finding",
        f"bugs check --base {BASE}",
        bugs_gate,
    ),
    Gate(
        "plan",
        2,
        f"run `stayfixed plan check --base {BASE}` and fix each plan it names",
        f"plan check --base {BASE}",
        plan_gate,
    ),
    Gate(
        "commit",
        None,
        "rewrite the named commits' messages without their attribution lines",
        f"commit check --range {BASE}..HEAD",
        commit_gate,
    ),
    Gate(
        "trail",
        None,
        "run `stayfixed docs trail` and commit the roadmap it rewrites; a roadmap kept out of "
        "git (ignored, never added, or under [artifacts] local) drops trail from [gates] builtin "
        "instead",
        "docs trail --check",
        trail_gate,
        trail_reads,
    ),
)


class _NotAnswered(Exception):
    """A custom gate that did not finish. `reason` is built from bounded values only."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _custom(name: str, argv: tuple[str, ...]) -> GateFn:
    def run(root: Path, config: Config, base: str) -> list[Finding]:
        seconds = config.gates.custom_timeout_seconds
        not_answered = _NotAnswered(CUSTOM_COULD_NOT_RUN.format(name=name, seconds=seconds))
        try:
            # S603: the project's own `[gates.custom.<name>] run`, list form, never a shell.
            # Both streams go to this process's standard error untouched, so a person and a CI
            # log see them as they ran and `--json` on standard output stays one object. A
            # session of its own puts what the command starts in one process group, unless a
            # descendant leaves it (a new session, or a job-control shell's own group), and that
            # group is ended however the command finishes: `subprocess.run(timeout=...)` kills
            # the command alone, and a test runner it started keeps writing after the gate has
            # reported.
            process = subprocess.Popen(  # noqa: S603
                list(argv),
                cwd=root,
                stdin=subprocess.DEVNULL,
                stdout=2,
                stderr=2,
                start_new_session=True,
            )
        except OSError:
            raise not_answered from None
        try:
            processes.exited(process, seconds)
        except subprocess.TimeoutExpired:
            processes.end(process)
            raise not_answered from None
        except BaseException:
            # A terminal's Ctrl-C reaches stayfixed's process group, not the command's session,
            # so an interrupted run ends the command's process group itself before it leaves.
            processes.end(process)  # on an interrupt or any other exit, as subprocess.run did
            raise
        # The command has exited, and what it started may still run: a watcher or a server left
        # in the background, still writing into the tree while a later gate runs. The exited
        # command is not reaped yet, so the group's id is still its own and reaches only its
        # descendants; then it is reaped, which reads the status it exited with.
        processes.kill_group(process)  # after an exit of its own too
        code = process.wait()
        if code == 0:
            return []
        return [Finding("exit-status", "", None, f"exited {code}")]

    return run


def configured(config: Config) -> dict[str, Gate]:
    """Every gate `config` runs, by name, in `config.gate_names` order.

    A custom gate cites no principle, and its command is the one that runs it alone.
    """
    builtin = {gate.name: gate for gate in BUILTIN}
    gates: dict[str, Gate] = {}
    for name in config.gate_names:
        custom = config.gates.custom.get(name)
        if custom is None:
            gates[name] = builtin[name]
            continue
        gates[name] = Gate(
            name,
            None,
            CUSTOM_REMEDY.format(name=name),
            f"gate --only {name}",
            _custom(name, custom.run),
        )
    return gates


def _guarded(gate: Gate, context: GateContext) -> GateResult:
    try:
        found = gate.run(context.root, context.config, context.base)
    except _NotAnswered as exc:
        return GateResult(gate.name, (), False, exc.reason)
    except StayfixedError:
        return GateResult(gate.name, (), False, COULD_NOT_RUN.format(command=gate.command))
    except RecursionError:
        # A backstop: every reader of a repository's TOML answers a document nested past the
        # parser's recursion as unreadable, and a reader that did not would end every gate.
        return GateResult(gate.name, (), False, COULD_NOT_RUN.format(command=gate.command))
    return GateResult(gate.name, tuple(found))


def run_gates(
    context: GateContext,
    names: Sequence[str],
    *,
    first: frozenset[str] = frozenset(),
    failed: Callable[[tuple[GateResult, ...]], bool] | None = None,
) -> tuple[GateResult, ...]:
    """A result for each configured gate `names` asks for, each run once: the built-ins and the
    custom gates `first` names, then every other custom gate, each group in configured order.

    `failed` is asked, with the results so far, before each custom gate starts, those `first`
    names included; when it answers that the run has already failed, that gate is not started
    and its result is `stopped`. Otherwise one gate that does not answer never stops another. A
    name the configuration does not hold is a `KeyError`: callers validate names before they ask.
    """
    gates = configured(context.config)
    wanted = {gates[name].name for name in names}
    custom = context.config.gates.custom
    order = sorted(gates, key=lambda name: name in custom and name not in first)
    results: list[GateResult] = []
    for name in (name for name in order if name in wanted):
        if failed is not None and name in custom and failed(tuple(results)):
            results.append(stopped(name))
        else:
            results.append(_guarded(gates[name], context))
    return tuple(results)
