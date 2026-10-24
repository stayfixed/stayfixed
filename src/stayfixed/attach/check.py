"""`stayfixed attach --check`: what `attach` would do, read the way `attach` reads it, with nothing
written.

A module of its own, above everything it reads through: the binding and the permission diff
(`binding`, `permissions`), and what the real run asks before its first write, which it asks
through the writer's own planning (`write`). `write` imports `permissions` for the diff it
merges, so the preview cannot live in `permissions` without the two importing each other; here
each import runs one way, and `tests/boundaries/test_layering.py` holds the modules under
`src/stayfixed/` to a graph without a cycle, imports inside a function included.
"""

from __future__ import annotations

from pathlib import Path

from stayfixed.attach.binding import Binding, read_binding
from stayfixed.attach.permissions import codex_rules
from stayfixed.attach.write import Gates, plan_writes
from stayfixed.config.owner import Owner
from stayfixed.config.schema import Config
from stayfixed.config.session import command_config
from stayfixed.result import Result


def check(
    root: Path,
    *,
    store: Path | None,
    machine: Path | None,
    home: Path | None,
    owner: Owner | None = None,
) -> Result:
    """`attach --check`: the binding and the diff, with nothing written.

    Exit 1 on a memory group that never moved — a finding, not a refusal, because the answer is an
    act of the owner's and `attach` itself is what refuses. A moved `origin` is a note on the
    line, as the run says it (`Binding.note`), and never a finding: the remote binds nothing.

    That finding is the one this command exists to deliver early. `attach` links rather
    than moves, so a group still sitting as a real directory under `paths.memory` refuses the
    whole run — above every write, and after the owner has already been told the diff is
    clean. Reporting it here costs one walk and turns a refusal into a list of notes to move.

    The `Config` is loaded once and handed to both halves: `read_binding` takes it rather than
    loading a second one, and `unlinked_groups` needs the same `memory.groups` and
    `paths.memory` the binding was read under. Two loads could disagree, and a `--check` whose
    two halves read different documents is exactly what it exists to rule out.

    A `PathEscape` out of `unlinked_groups` propagates: `--check` refuses what `attach` would,
    rather than reporting a count for a `paths.memory` no walk could contain.

    `home` is the home the harness memory link goes under, which `plan_writes` asks about as the
    run does, and it is keyword-required for `attach`'s reason: no caller reaches the developer's
    own `~/.claude/` by leaving it out. The command passes `None`, the machine owner's own.
    `owner` is the owner's layer the command resolved (`config.loader.loads`' own).
    """
    config = command_config(root, machine=machine, owner=owner)
    binding = read_binding(root, store=store, machine=machine, config=config)
    return _report(root, config, binding, machine=machine, home=home)


def _report(
    root: Path, config: Config, binding: Binding, *, machine: Path | None, home: Path | None
) -> Result:
    """`check` past the binding: the run's gates, what the run asks before its first write where it
    would reach it, the groups and the rule files, and the report made of them."""
    # The run's gates, taken in the run's order by the run's own `Gates`, which makes what the run
    # asks between them where the run would, so a refusal or failure there ends this command with
    # the run's code and line: each of them was once left out here, and `--check` answered clean
    # over a checkout the run then stopped on. The stop is taken and reported, and the writes are
    # planned only where there was none, as the run plans them only past it.
    gates = Gates(root, config, binding)
    stops = list(gates)
    diff, real = gates.diff, gates.real
    if not stops:
        plan_writes(root, config, binding, diff, machine=machine, home=home)
    # Named and not merely counted, and on this result rather than in `PermissionDiff`: the
    # diff's two fields say what `attach` would add and what is already there, and a third of
    # another kind would blur what it means. These names come out of the overlay, so they are the
    # owner's own and may be printed.
    rules = tuple(target for target, _ in codex_rules(binding))
    summary = (
        f"{binding.state}; "
        f"{len(diff.added_allow)} allow rule(s) would be added, "
        f"{len(diff.already_present)} already present; "
        f"{len(rules)} Codex standing-rule file(s) would be placed"
    )
    if real:
        # A count and never a name: `memory.groups` is repository-authored, and this line is
        # what `skills/attach/SKILL.md` has the model relay to the user.
        summary += f"; {real} memory group(s) are real directories and would refuse the attach"
    if binding.note is not None:
        summary += f"; {binding.note}"
    if binding.fault is not None:
        summary += f"; {binding.fault}"
    if rules:
        summary += "\n" + "\n".join(f"  {target}" for target in rules)
    data = {
        # The state and the counts, this command's own; the project is named on the screen
        # `attach` prints, through `printed.quoted`.
        "state": binding.state,
        "added_allow": list(diff.added_allow),
        # A count and not the strings: this list comes out of the project's own
        # `settings.local.json`, which a clone can commit, so it is repository-authored.
        "already_present": len(diff.already_present),
        "rules_to_write": list(rules),
        # A count, for the reason `already_present` is one: the entries are repository-authored.
        "real_directories": real,
    }
    return Result(summary, data, exit_code=1 if real else 0)
