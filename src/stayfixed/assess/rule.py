"""The base a change is judged against, where in it the base's `stayfixed.toml` is, and the rule
that judges the change's own `stayfixed.toml` against it.

A pull request may tighten what its base branch enforces and may not loosen it, so the base's
configuration is the one that governs the run and the change's own is judged against it. Both
halves of that depend on reading the right document, and each way of reading the wrong one ends
in the same place: a base with no `stayfixed.toml` at the project's path is the bootstrap, where
the change decides its own configuration. So nothing here reads "git did not answer" as "no
copy", and every name and path git would resolve on the caller's behalf is pinned first.

**Which commit.** In CI it is a full commit id the workflow resolved once from the remote-tracking
ref of the base branch, whose name comes from the platform or from the caller workflow's literal
input, which code owners guard (`docs/cli.md#the-reusable-workflow` names the repository
settings). Locally it is `config.layout.local_base`, the remote-tracking ref of `[project]
base_branch`, and
advice only: a local run judges nothing anyone else relies on. Either way `--base` is a full
commit id or a full `refs/…` name, never a short one, because git resolves a short name through
the tags first and a tag of the same spelling would stand in for the branch.

**Where in it.** At the project root's path inside the repository, as git spells it. A root
reached through a symlink below the repository's top, or spelled otherwise than git spells it (a
case-folding disk), is refused rather than guessed at: the base's copy would be looked for at the
place the link or the spelling names, which a change can make empty. A link above the
repository is the machine's (`/tmp` on macOS, a symlinked home) and is admitted.

**What the change may do.** Each side goes through the loader and the rule compares what it
derives, key by dotted key: each budget by its effective value, each custom gate as one key per
field. A comment, a key spelled out at its default, a reordered `enforced` or `[gates] builtin`
and `installed` beside a list that says the same are therefore no change. Every changed key gets
one verdict. The change may enforce more gates and move its state forward (`initialised`,
`adopting`, `installed`); add a gate, and drop or re-command one the base does not enforce; lower
a budget. The preset's name, the profile, the harnesses and the project's name are neutral,
because no gate reads them; every value a preset switch moves is judged by its own key. The
recorded version and the workflow pin move together as an upgrade: to exactly the running
stayfixed, never below the base's by the reader `stayfixed upgrade` refuses by, and a moved pin
only at the commit the platform says is running and a public release tag names. Any other key is
refused while the base enforces any gate, because the rule cannot know which way a free-form key
moves, and noted while it enforces none; routine upkeep under enforcement lands by a direct push
to the base branch.

The run then uses the tree's configuration, or the base's when anything was refused, and
enforces the gates either side enforces: adding the tree's never loosens, and a refusal already
fails the run. A custom gate executes only with the base's own command (`ConfigVerdict.landed`),
so a gate the change adds or re-commands waits until it lands on the base. Key names print;
values never do.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, fields, replace
from enum import StrEnum
from pathlib import Path

from stayfixed.config.loader import CONFIG_FILE, NOT_UTF8, loads
from stayfixed.config.schema import STATES, Budgets, Config, CustomGate
from stayfixed.errors import Failure, Refusal
from stayfixed.gitenv import NO_ANSWER, answer_bytes, git_run, in_work_tree
from stayfixed.semver import later

# Formatted with `[project] base_branch`, which the loader holds to the branch grammar.
BASE_UNREADABLE = (
    "the base is not in this checkout, or git could not read its stayfixed.toml, so the "
    "configuration that governs this change cannot be read; check out with full history "
    "(fetch-depth: 0), or pass a --base that exists, such as refs/heads/{branch} in a clone "
    "with no origin"
)
BASE_SHAPE = (
    "--base takes a full 40-character commit id or a full ref name starting with refs/: a "
    "shorter name is resolved by git, and a tag of the same spelling wins"
)
# The loader's own sentence for a tree copy that is not UTF-8, so the base's copy is refused in
# the words the tree's is: git hands the blob over losslessly, with a surrogate escape for each
# byte that is not UTF-8, and `tomllib` would parse those.
BASE_NOT_UTF8 = NOT_UTF8.format(path=f"the base's {CONFIG_FILE}")
# What the loader calls the base's copy, so its reason names the right file: the loader's own
# words would name `<root>/stayfixed.toml`, which is the change's copy.
BASE_COPY = f"the base's {CONFIG_FILE}"
# A refusal the base's own load raised against this tree's disk, such as a symlink the change
# planted on a path only the base's `[paths]` names: still a refusal, and said to be the base's.
# The reason is the loader's own, bounded where it was raised.
BASE_REFUSED = (
    "the base's stayfixed.toml governs this change, and loading it against this tree met a "
    "refusal: {reason}"
)
BASE_DOES_NOT_LOAD = (
    "the base's stayfixed.toml governs this change and does not load, so the change cannot be "
    "judged; fix it on the base branch by a direct push ({reason})"
)
NOT_A_REPOSITORY = (
    "the project root is not inside a git repository, so it has no base to compare with"
)
ROOT_UNANSWERED = (
    "git gave no answer about the repository the project root is in, so its base cannot be "
    f"read: {NO_ANSWER}, or git refused the repository (a checkout of dubious ownership, a "
    "worktree whose git directory is gone)"
)
ROOT_DOT_DOT = (
    "the project root is given with a `..` component, and `..` after a component that is a link "
    "is not the directory the spelling names, so the base's stayfixed.toml could be looked for "
    "in the wrong place; pass the root by its real path, with no `..`"
)
ROOT_THROUGH_SYMLINK = (
    "the project root is reached through a symlink, or git spells its path differently from the "
    "caller, so the base's stayfixed.toml would be looked for in the wrong place; pass the root by "
    "its real path"
)
BASE_REF = re.compile(r"\A(?:[0-9a-f]{40}|refs/[A-Za-z0-9._/-]+)\Z")


def _read(root: Path, *args: str, branch: str) -> str:
    """git's answer, or the run fails: "git did not answer" is never read as "no copy". The
    failure's remedy names `branch`, the configured base branch."""
    code, out = git_run(root, *args)
    if code != 0:
        raise Failure(BASE_UNREADABLE.format(branch=branch))
    return out


def repository_prefix(root: Path) -> str:
    """The project root's path inside its repository, `""` at the top or `"a/b/"` below it: git's
    spelling, which is refused unless it is also the caller's."""
    lexical = root.absolute()
    if ".." in lexical.parts:
        raise Refusal(ROOT_DOT_DOT)
    code, out = git_run(lexical, "rev-parse", "--show-toplevel", "--show-prefix")
    if code != 0:
        # Read off the disk, as git finds a repository: git refuses a checkout of dubious
        # ownership exactly as it refuses a directory outside any repository.
        raise Failure(ROOT_UNANSWERED if in_work_tree(lexical) else NOT_A_REPOSITORY)
    top, _, prefix = out.partition("\n")
    # The HIGHEST ancestor that resolves to the top, not the nearest: a component linked back
    # to the top (`app -> .`) resolves to the top as well, and a spelling read below it skips it.
    chain = (*reversed(lexical.parents), lexical)
    ancestor = next((path for path in chain if path.resolve() == Path(top)), None)
    if ancestor is None:
        raise Refusal(ROOT_THROUGH_SYMLINK)
    below = lexical.parts[len(ancestor.parts) :]
    linked = any(ancestor.joinpath(*below[: n + 1]).is_symlink() for n in range(len(below)))
    spelled = "".join(f"{part}/" for part in below)
    if linked or spelled != prefix.rstrip("\n"):
        raise Refusal(ROOT_THROUGH_SYMLINK)
    return spelled


def read_base(root: Path, base: str, *, branch: str, prefix: str | None = None) -> str | None:
    """The base's `stayfixed.toml` at the project's own path, or `None` when git listed nothing
    there: the bootstrap, and the only answer that means it. Any other git failure fails the run,
    and so does a copy that is not UTF-8 text, which is never parsed. `branch` is `[project]
    base_branch`, which a base the checkout lacks names as the local remedy. `prefix` is
    `repository_prefix(root)`, asked here unless the caller already has it.
    """
    if not BASE_REF.match(base):
        raise Refusal(BASE_SHAPE)
    if prefix is None:
        prefix = repository_prefix(root)
    if base.startswith("refs/"):
        # Exactly this ref: when it is missing, git would take `refs/tags/<base>` instead.
        _read(root, "show-ref", "--verify", "--quiet", "--end-of-options", base, branch=branch)
    commit = _read(
        root,
        "rev-parse",
        "--verify",
        "--quiet",
        "--end-of-options",
        f"{base}^{{commit}}",
        branch=branch,
    ).strip()
    path = f"{prefix}{CONFIG_FILE}"
    # Literal: git reads a pathspec starting `:/` as "from the top", so under a directory named
    # `:` the listing would look elsewhere, answer nothing, and make the change the bootstrap.
    # No `--` after `--end-of-options`: every argument past it is literal, and a `--` there is a
    # path, which listed a top-level file of that name.
    listed = _read(
        root,
        "--literal-pathspecs",
        "ls-tree",
        "--full-tree",
        "--name-only",
        "--end-of-options",
        commit,
        path,
        branch=branch,
    )
    if not listed:
        return None
    text = _read(root, "cat-file", "blob", "--end-of-options", f"{commit}:{path}", branch=branch)
    # The bytes git printed, read as UTF-8 the way the loader reads the tree's copy: the text
    # `git_run` decoded with the filesystem's codec is neither refused nor read the same where
    # that codec is latin-1 (Linux under a latin-1 locale), because every byte decodes.
    try:
        return answer_bytes(text).decode("utf-8")
    except UnicodeDecodeError:
        raise Failure(BASE_NOT_UTF8) from None


class Verdict(StrEnum):
    TIGHTENED = "tightened"
    NEUTRAL = "neutral"
    UPGRADE = "upgrade"
    REFUSED = "refused"
    NOTED = "noted"


@dataclass(frozen=True)
class Change:
    """One key whose derived value differs between the base and the tree. The key is a schema
    field's dotted path or a custom gate's, whose name the loader holds to a grammar, so it
    prints; the values never do."""

    key: str
    verdict: Verdict


@dataclass(frozen=True)
class ConfigVerdict:
    base_state: str | None  # None: the base has no copy at this path (the bootstrap)
    changes: tuple[Change, ...]  # sorted by key
    config: Config  # the tree's, or the base's when anything was refused
    enforcing: frozenset[str]  # the base's and the tree's
    # The base's own custom gates and enforcing set, which decide which of the run's custom
    # gates execute and in what order; none under the bootstrap.
    base_custom: Mapping[str, CustomGate] = field(default_factory=dict)
    base_enforcing: frozenset[str] = frozenset()

    @property
    def refused(self) -> bool:
        return any(change.verdict is Verdict.REFUSED for change in self.changes)

    @property
    def landed(self) -> frozenset[str]:
        """The run's custom gates whose command is the base's own, and so the ones that execute.

        A gate the change adds or re-commands is a command only the change has vouched for: run
        in the same step as the base's enforced gates, it could rewrite the files they execute
        before they run. It runs once it has landed on the base. Under the bootstrap no gate
        has, and under a refusal the run is the base's configuration, so every gate has.
        """
        custom = self.config.gates.custom
        return frozenset(
            name for name, gate in custom.items() if self.base_custom.get(name) == gate
        )


@dataclass(frozen=True)
class _Sides:
    base: Config
    tree: Config
    running: str  # the stayfixed running this judgement: the one the workflow's pin checked out
    workflow_sha: str | None  # the commit of the reusable workflow the platform says is running
    released: Callable[[str], bool | None]  # whether a public release tag names this commit


Row = Callable[[str, _Sides], Verdict]

_ORDER = {state: index for index, state in enumerate(STATES)}
# Lists whose order no reader sees: `enforcing` is a set, and `gate_names` orders built-ins itself.
_UNORDERED = frozenset({"stayfixed.enforced", "gates.builtin"})


def _neutral(key: str, sides: _Sides) -> Verdict:
    return Verdict.NEUTRAL


def _other(key: str, sides: _Sides) -> Verdict:
    """A key the rule cannot tell the direction of: refused while the base enforces anything."""
    return Verdict.REFUSED if sides.base.stayfixed.enforcing else Verdict.NOTED


def _enforcement(key: str, sides: _Sides) -> Verdict:
    """`state` and `enforced` are one fact: every gate the base enforces still enforces, and the
    lifecycle does not move back."""
    before, after = sides.base.stayfixed, sides.tree.stayfixed
    backward = _ORDER[after.state] < _ORDER[before.state]
    if backward or not after.enforcing >= before.enforcing:
        return Verdict.REFUSED
    grew = after.enforcing > before.enforcing or after.state != before.state
    return Verdict.TIGHTENED if grew else Verdict.NEUTRAL


def _builtin_gates(key: str, sides: _Sides) -> Verdict:
    before, after = set(sides.base.gates.builtin), set(sides.tree.gates.builtin)
    if (before - after) & sides.base.stayfixed.enforcing:
        return Verdict.REFUSED
    return Verdict.TIGHTENED if after - before else Verdict.NEUTRAL


def _custom_gate(key: str, sides: _Sides) -> Verdict:
    """A custom gate's field, `gates.custom.<name>.<field>`: a gate the base enforces keeps its
    command, and one it does not may change it or go."""
    name = key.removeprefix("gates.custom.").rpartition(".")[0]
    if name not in sides.base.gates.custom:
        return Verdict.TIGHTENED
    return Verdict.REFUSED if name in sides.base.stayfixed.enforcing else Verdict.NEUTRAL


def _budget(key: str, sides: _Sides) -> Verdict:
    name = key.removeprefix("budgets.")
    lower = sides.tree.budgets.effective(name) <= sides.base.budgets.effective(name)
    return Verdict.TIGHTENED if lower else Verdict.REFUSED


def _upgrade(key: str, sides: _Sides) -> Verdict:
    """`[stayfixed] version` and `[ci] ref` are one upgrade, judged together. "Not below the
    base's" is `later`, the reader `stayfixed upgrade` refuses by, so the two agree. A moved pin
    is admitted only at the commit the platform says is running, and only when a release tag
    names it."""
    old, new, pin = sides.base.stayfixed.version, sides.tree.stayfixed.version, sides.tree.ci.ref
    at_running = new == sides.running
    upward = later(old, new) is False
    vouched = bool(sides.workflow_sha) and pin == sides.workflow_sha
    pinned = pin == sides.base.ci.ref or (vouched and sides.released(pin) is True)
    return Verdict.UPGRADE if at_running and upward and pinned else _other(key, sides)


ROWS: Mapping[str, Row] = {
    "stayfixed.state": _enforcement,
    "stayfixed.enforced": _enforcement,
    "gates.builtin": _builtin_gates,
    "stayfixed.version": _upgrade,
    "ci.ref": _upgrade,
    # Keys no gate reads. The preset's name is one: each value it moves is judged by its own row.
    "stayfixed.preset": _neutral,
    "stayfixed.profile": _neutral,
    "stayfixed.agents": _neutral,
    "project.name": _neutral,
}
PREFIX_ROWS: tuple[tuple[str, Row], ...] = (
    ("budgets.", _budget),
    ("gates.custom.", _custom_gate),
)


def _row(key: str) -> Row:
    if key in ROWS:
        return ROWS[key]
    return next((row for prefix, row in PREFIX_ROWS if key.startswith(prefix)), _other)


def _values(config: Config) -> dict[str, object]:
    """Every value the loader derived, by dotted key: each budget by its effective value, each
    custom gate as one key per field. `native_caps` (the preset's) and `personal` (the machine
    file's) are `Config` fields and not `stayfixed.toml` sections; both sides load under one
    machine file, so either moves only with a preset switch, and is compared like any field."""
    values: dict[str, object] = {}
    for section in fields(config):
        table = getattr(config, section.name)
        if isinstance(table, Budgets):
            values |= {f"budgets.{name}": table.effective(name) for name in Budgets.NAMES}
            continue
        for item in fields(table):
            key, value = f"{section.name}.{item.name}", getattr(table, item.name)
            if isinstance(value, Mapping):  # `gates.custom`: one key per gate and field
                for name, entry in value.items():
                    values |= {
                        f"{key}.{name}.{f.name}": getattr(entry, f.name) for f in fields(entry)
                    }
            else:
                values[key] = frozenset(value) if key in _UNORDERED else value
    return values


def read_base_gates(
    root: Path, base: str, *, branch: str, machine: Path | None
) -> Mapping[str, CustomGate]:
    """The base's custom gates by name, loaded as `judge` loads the base's copy; none when the
    base has no `stayfixed.toml` at the project's path. Raises as `read_base` and the loader do."""
    text = read_base(root, base, branch=branch)
    if text is None:
        return {}
    config = loads(text, root, machine=machine, interactive=False, label=BASE_COPY)
    return config.gates.custom


def judge(
    root: Path,
    base_text: str | None,
    tree_text: str,
    *,
    machine: Path | None,
    running: str,
    workflow_sha: str | None,
    released: Callable[[str], bool | None],
) -> ConfigVerdict:
    """The tree's `stayfixed.toml` judged against the base's, key by derived key.

    Both sides go through the loader against the tree's disk, so what is compared is what a
    command would read: a comment, a key spelled at its default and a reordered list are no
    change. `base_text` is `None` for the bootstrap, where the tree decides. The run uses the
    tree's configuration unless something was refused, then the base's; it enforces what either
    side enforces.
    """
    tree = loads(tree_text, root, machine=machine, interactive=False)
    if base_text is None:
        return ConfigVerdict(None, (), tree, tree.stayfixed.enforcing)
    try:
        base = loads(base_text, root, machine=machine, interactive=False, label=BASE_COPY)
    except Failure as exc:
        # Never the bootstrap: read as "no copy", the change would decide its own configuration.
        # The machine file is not the base's: both sides read it, and the tree's load above has
        # already answered for it. `Failure` and not `ConfigError` alone: a preset this stayfixed
        # does not ship is the preset loader's plain `Failure`, and still the base's copy.
        raise Failure(BASE_DOES_NOT_LOAD.format(reason=exc)) from None
    except Refusal as exc:
        # A symlink the change planted on a path only the base's `[paths]` names: the run fails
        # as a refusal, and the message says whose configuration met it, since the tree's own
        # `[paths]` may not name that path at all.
        raise Refusal(BASE_REFUSED.format(reason=exc)) from None
    sides = _Sides(base, tree, running, workflow_sha, released)
    before, after = _values(base), _values(tree)
    changes = tuple(
        Change(key, _row(key)(key, sides))
        for key in sorted(before.keys() | after.keys())
        if before.get(key) != after.get(key)
    )
    enforcing = base.stayfixed.enforcing | tree.stayfixed.enforcing
    verdict = ConfigVerdict(
        base.stayfixed.state,
        changes,
        tree,
        enforcing,
        base_custom=base.gates.custom,
        base_enforcing=base.stayfixed.enforcing,
    )
    return replace(verdict, config=base) if verdict.refused else verdict
