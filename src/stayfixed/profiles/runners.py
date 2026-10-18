"""What a test runner's adapter and the core say to each other about a run and its report.

A leaf: the adapters under `profiles/<stack>/` and the `prove` core both import it, and it imports
nothing from either, so neither reaches the other through it and no package cycle forms. It is
also the public contract an adapter stayfixed does not ship implements: `RunnerAdapter`, and the
three answers its `plan` gives.

An adapter refuses only what the command itself spells to move, replace or suppress the report,
from a short closed list of its own; it neutralises the channels stayfixed controls (the
environment it hands the runner, the entry point it runs) rather than removing them; and it names
every file in the tree that can shape the report, for the receipt to name. Everything else a file
in the tree can do is the bound's, which `docs/cli.md` states.

No entry in `mutations/` covers this module: it declares names and records and decides nothing.
Which reader a kind is read with is `stayfixed.prove.reports.read_report`'s, and what the core
does with a plan is `stayfixed.prove.run`'s; their entries cover those.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Protocol


class ReportKind(StrEnum):
    """The report formats `prove` counts, each by the format's own name and never a runner's."""

    # JUnit XML: `testcase` elements.
    JUNIT = "junit"
    # The JSON test-results report: `testResults`, each with its `assertionResults`.
    RESULTS_JSON = "results-json"
    # The test event stream: one JSON object a line, each with its `Action`.
    EVENTS = "events"


class ReportSource(StrEnum):
    """Where the report arrives: a file the runner writes at `Plan.report`, or the runner's own
    standard output, which the core copies to the caller whole and to `Plan.report`."""

    FILE = "file"
    STDOUT = "stdout"


@dataclass(frozen=True)
class Plan:
    """How to run a recognised command so that its report can be counted.

    `argv` is what is executed, its first item absolute, and `program` the realpath the adapter
    resolved for it, which the core checks again just before the launch. `kind`, `source` and
    `report` say what the report is and where it arrives; `report` lies in the scratch directory
    the core handed the plan. The run's environment is the caller's less every inherited variable
    in `scrub`, plus the command's own assignments, plus `set_env`, the last winning. `discovery`
    is the globs of the files the runner collects tests from, and `configs` of the files that
    configure it, both matched from the right (`stayfixed.prove.tree`). `drop` is the JUnit
    reader's (`stayfixed.prove.junit.read_junit`), for a testcase a runner writes that is no test.
    `verified` is false for a runner no adapter resolved.
    """

    argv: tuple[str, ...]
    program: Path
    kind: ReportKind
    source: ReportSource
    report: Path
    set_env: Mapping[str, str]
    scrub: frozenset[str]
    discovery: tuple[str, ...]
    configs: tuple[str, ...]
    drop: Callable[[Mapping[str, str]], bool] | None = None
    verified: bool = True


@dataclass(frozen=True)
class Refused:
    """The command spells something that moves, replaces or suppresses the report. `reason` is a
    constant of the adapter's module."""

    reason: str


@dataclass(frozen=True)
class Unresolved:
    """The runner's entry point does not resolve from where the command runs. `reason` is a
    constant of the adapter's module."""

    reason: str


class RunnerAdapter(Protocol):
    """One test runner, as `prove` asks about it. A stack ships its adapters as `ADAPTERS`, a
    tuple, in `profiles/<stack>/adapters.py`, and `stayfixed.prove.adapters.shipped_adapters`
    lists them."""

    @property
    def name(self) -> str:
        """The runner's name, for the receipt."""
        ...

    @property
    def forging(self) -> frozenset[str]:
        """The variables whose assignment in the command itself is refused: each one the runner
        reads to move, replace or suppress its report, or to run the tests under another
        program."""
        ...

    def recognises(self, command: Sequence[str]) -> bool:
        """Whether `command` runs this runner. `command` is what is left once the leading
        assignments, `env` and `uv run …` are read past (`guards.api.command_words`)."""
        ...

    def plan(
        self,
        launch: Sequence[str],
        command: Sequence[str],
        *,
        cwd: Path,
        root: Path,
        scratch: Path,
        environ: Mapping[str, str],
    ) -> Plan | Refused | Unresolved:
        """How to run `command`, typed in `cwd` after `launch`, in the project `root`, its report
        put under `scratch`; or why not. A pure function of its arguments and of the filesystem it
        reads: it runs nothing."""
        ...
