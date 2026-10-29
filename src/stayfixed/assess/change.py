"""`stayfixed gate`'s decisions: a change's `stayfixed.toml` judged against its base's, and the
gates run as that judgement says, returned as one `GateRun` for the command to render.

Which gates run, under whose configuration and in what order is decided here, and nowhere in the
command: the command parses its flags, asks `gate_change` once, and prints, annotates and writes
the summary from what it returns. Which base and where in it are `stayfixed.assess.base`'s, and
what the change may do is `stayfixed.assess.rule`'s.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Literal

from stayfixed.assess.base import PlatformBase, platform_base, read_base
from stayfixed.assess.gates import GateContext, run_gates
from stayfixed.assess.report import GateRun
from stayfixed.assess.rule import judge
from stayfixed.committed import repository_prefix
from stayfixed.config.layout import local_base
from stayfixed.config.loader import loads, read_document
from stayfixed.config.owner import Owner
from stayfixed.config.reading import ConfigError
from stayfixed.config.schema import CONFIG_CHECK
from stayfixed.errors import Refusal

NO_TREE_CONFIG = (
    "this tree has no stayfixed.toml at the project root, so nothing says which gates run; "
    "the run fails rather than pass a change it cannot judge"
)
NOTHING_TO_RUN = "nothing to run: no configured gate of the kind asked for"
ONLY_UNKNOWN = (
    "--only names {count} gate(s) the configuration this run uses does not have; `config` is "
    "the configuration check, and every other name is a gate from [gates]"
)


def gate_change(
    root: Path,
    *,
    base: str | None,
    platform: PlatformBase | None = None,
    only: Sequence[str] | None,
    part: Literal["builtin", "custom"] | None,
    machine: Path | None,
    owner: Owner,
    workflow_sha: str | None,
    running: str,
    released: Callable[[str], bool | None],
) -> GateRun:
    """The tree's `stayfixed.toml` judged against the base's, and the gates `only` and `part`
    ask for run as the verdict says.

    `base` is `None` for the tree's `local_base`, or for `platform`'s base when it is given:
    the platform's values, resolved here to one commit before anything reads the base, which
    the verdict and every gate then read. `only` is `--only`'s names, `None` for the
    configuration check and every configured gate; `part` is `--builtin`'s `"builtin"`,
    `--custom`'s `"custom"`, or `None` for both. `owner` is the owner's layer the command
    resolved, which every load here takes. `running` is the stayfixed running, and `workflow_sha`
    and `released` are what `judge` takes to admit a moved workflow pin.
    """
    if platform is not None:
        base = platform_base(
            platform.checkout,
            pr_base=platform.pr_base,
            base_input=platform.base_input,
            default_branch=platform.default_branch,
        )
    prefix = repository_prefix(root)
    tree_text = read_document(root)
    if tree_text is None:
        raise ConfigError(NO_TREE_CONFIG)
    # The tree's configuration is read here for its default base and the branch a base the
    # checkout lacks is named by, and kept nowhere: every later decision is the verdict's, and a
    # name for the tree's copy in scope is one a later line could pick in its place.
    tree = loads(tree_text, root, machine=machine, owner=owner)
    default, branch = local_base(tree), tree.project.base_branch
    del tree
    base = base or default
    verdict = judge(
        root,
        read_base(root, base, branch=branch, prefix=prefix),
        tree_text,
        machine=machine,
        running=running,
        workflow_sha=workflow_sha,
        released=released,
        owner=owner,
    )
    # The configuration this run uses is the verdict's: the base's when anything was refused, so
    # the names it runs, which of them are custom, and the paths and commands the gates read are
    # all the base's then. `enforcing` is both sides', so it can name a gate only the refused
    # tree defines; that gate is not run, and the refusal already fails the run.
    configured = verdict.config.gate_names
    only = tuple(dict.fromkeys(only or (CONFIG_CHECK, *configured)))
    stray = [name for name in only if name != CONFIG_CHECK and name not in configured]
    if stray:
        # Counted, never echoed: the names come from the caller workflow, which the pull request
        # can edit.
        raise Refusal(ONLY_UNKNOWN.format(count=len(stray)))
    # The workflow's two steps: the one that judges runs no command the repository wrote, and
    # the custom gates run in the next, after it passed. A name of the other kind is that
    # step's to run, so it is skipped here and not refused.
    custom = verdict.config.gates.custom
    if part == "builtin":
        only = tuple(name for name in only if name not in custom)
        # The judging step judges the configuration whatever `--only` names: `--only` comes from
        # the caller workflow, which the pull request can edit, and a leg that names one gate
        # would otherwise run it under the base's configuration and never meet the refusal.
        only = tuple(dict.fromkeys((CONFIG_CHECK, *only)))
    elif part == "custom":
        only = tuple(name for name in only if name in custom)
    # A custom gate executes only with the base's own command, and the base's enforced gates
    # run before any other: a gate the change adds or re-commands runs files it wrote, and run
    # first it could rewrite what an enforced gate executes. It waits until it lands on the base,
    # and never fails the run meanwhile, since the base enforces no command it lacks.
    waiting = tuple(name for name in only if name in custom and name not in verdict.landed)
    names = [n for n in only if n != CONFIG_CHECK and n not in waiting]
    context = GateContext(root, verdict.config, base)
    judged = CONFIG_CHECK in only
    # A custom gate, one the base enforces included, can run files the change can edit, in the
    # process that holds the verdict: on a hosted runner with passwordless `sudo`, enough to
    # rewrite or end that process. So the configuration check and the built-ins decide the run
    # first, then the base's enforced custom gates, and once it has failed no custom gate starts.
    results = run_gates(
        context,
        names,
        first=verdict.base_enforcing,
        failed=lambda done: GateRun(verdict, done, judged=judged).exit_code != 0,
    )
    return GateRun(verdict, results, judged=judged, prefix=prefix, waiting=waiting)
