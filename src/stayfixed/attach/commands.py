"""The `attach` and `detach` groups: `attach` binds a repository to the overlay, and `detach`
takes back what `attach` wrote and leaves the overlay's record of the binding in place.

Two top-level commands and not one group with two subcommands, because that is how
`docs/cli.md` lists them and the shape the skills already invoke.

**`--machine` is honoured here only from an interactive shell, and refused otherwise.**
`config/machine.py` reads neither `STAYFIXED_CONFIG` nor `XDG_CONFIG_HOME`, for any command, and
its docstring gives a reason that reaches past the variables it was written for: "Gating one of a
pair of equivalent inputs is not a partial defence, it is a redirect with a longer name". A flag
is a third member of that class — it reaches the same file for the price of a different spelling —
and this is the command that turns that file into capability: the overlay root comes from it, and
from the overlay come allow rules, hook entries, skills, agents and Codex standing rules. A
repository that tells the agent to run `stayfixed attach --machine ./vendored.toml --store
./vendored/projects/p/memory` supplies both sides of `read_binding`'s containment check out of
its own tree, and the check passes. A flag, unlike a variable, is still honoured from a
terminal, because there a person typed it.

**It refuses rather than ignoring.** A silent fallback would read the owner's real file while
the caller believed it was reading the one it named, which is the worse of the two failures.

Scoped to these two commands and deliberately not to `command.common_flags`: the other readers
of that flag take personal parameters, and rewriting a shared flag's semantics for three areas
is not this area's to do. The agent-driven path is unaffected — the `attach` skill passes
`--store` and no `--machine`, so it resolves the default path exactly as before.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import TYPE_CHECKING

from stayfixed.areas import SubParsers
from stayfixed.command import ATTACH_CHECK_HELP, command_owner, common_flags
from stayfixed.config.machine import override_is_honoured
from stayfixed.errors import Refusal
from stayfixed.printed import clipped, quoted
from stayfixed.result import Result

if TYPE_CHECKING:
    from stayfixed.attach.write import Attached

_NO_STORE = (
    "`stayfixed attach` needs --store, naming this project's own directory inside the overlay "
    "this machine records: <overlay>/projects/<project name>/memory"
)
_NO_MACHINE_OVERRIDE = (
    "--machine names the file that decides which overlay this command trusts, so here it is "
    "honoured only from an interactive shell: anywhere else the command may be an agent's, and "
    "a repository can tell an agent which file to name. Run this from a terminal, or drop the "
    "flag and let it read the machine configuration this machine records"
)


def _machine_argument(value: str | None, *, interactive: bool | None = None) -> Path | None:
    """The machine file this invocation may read, or a refusal that it may not name one.

    `interactive` is the seam `override_is_honoured` already offers: `None` asks the terminal,
    and a test says which answer it wants instead of arranging a tty.
    """
    if value is None:
        return None
    if not override_is_honoured(interactive):
        raise Refusal(_NO_MACHINE_OVERRIDE)
    return Path(value)


def _target(args: argparse.Namespace) -> tuple[Path, Path, Path | None]:
    if args.store is None:
        raise Refusal(_NO_STORE)
    return Path(args.root).resolve(), Path(args.store), _machine_argument(args.machine)


def run_attach(args: argparse.Namespace) -> Result:
    from stayfixed.attach.check import check
    from stayfixed.attach.write import attach
    from stayfixed.runner import subprocess_runner

    root, store, machine = _target(args)
    if args.check:
        # `None`, for the reason `attach` below is handed it: the real command's home is the
        # machine owner's own.
        return check(root, store=store, machine=machine, home=None, owner=command_owner(machine))
    attached = attach(
        root,
        store=store,
        machine=machine,
        runner=subprocess_runner(),
        # Explicit, as `runner` is: both parameters are keyword-required so that a caller has
        # to say which home and which runner it means, and the real command's answer is the
        # machine owner's own.
        home=None,
        owner=command_owner(machine),
    )
    data = {
        # Counts and not paths, which is the rule rather than a preference: every one of these
        # paths is built out of `paths.memory` and a `memory.groups` entry, both
        # repository-authored and neither schema-constrained, and `--json` puts `data` in front
        # of the model. `stayfixed.memory.hooks` reports the same value the same way.
        "links_created": len(attached.links.created),
        "links_revoked": len(attached.links.revoked),
        "settings_written": attached.settings_written,
        "rules_written": list(attached.rules_written),
        "binding_recorded": attached.binding_recorded,
        # The binding id's first eight characters, the only form of it ever printed: the whole id
        # is the secret a delivery's names carry.
        "binding": attached.binding,
        "notes": list(attached.notes),
        # The executable diff and the allow rules added, as the screen below names them. Each is
        # the overlay's, the owner's own, so it may be shown; `origin` is the repository's and is
        # not here, as no remote is in any `--json` of this area.
        **{
            f"{kind}_{side}": list(getattr(getattr(attached, side), kind))
            for side in ("added", "removed")
            for kind in ("hooks", "skills", "agents")
        },
        "allow_added": list(attached.allow_added),
    }
    summary = "; ".join(
        (
            f"attached: {len(attached.links.created)} link(s), "
            f"{len(attached.rules_written)} Codex rule file(s)",
            "settings merged" if attached.settings_written else "settings unchanged",
            f"binding {attached.binding} "
            + ("recorded" if attached.binding_recorded else "already recorded"),
            *attached.notes,
        )
    )
    return Result("\n".join((summary, *_screen(attached))), data)


def _screen(attached: Attached) -> list[str]:
    """The binding, then what will run that did not before and what no longer will, then the
    allow rules added: one screen, said as the run proceeds, since the overlay is the owner's and
    what it grants is shown rather than gated. Every name prints through `printed`: the remote is
    the repository's, and a hook's command or an allow rule holds spaces and may hold anything."""
    origin = "no origin remote" if attached.origin is None else f"origin {quoted(attached.origin)}"
    lines = [f"binding {attached.binding}: {origin}"]
    for side in ("added", "removed"):
        carried = getattr(attached, side)
        lines += [
            f"hook entry {side}: {quoted(event)} {clipped(command)}"
            for event, command in carried.hooks
        ]
        lines += [f"skill {side}: {quoted(name)}" for name in carried.skills]
        lines += [f"agent {side}: {quoted(name)}" for name in carried.agents]
    lines += [f"allow rule added: {clipped(rule)}" for rule in attached.allow_added]
    return lines


def run_detach(args: argparse.Namespace) -> Result:
    from stayfixed.attach.write import detach

    machine = _machine_argument(args.machine)
    removed = detach(
        Path(args.root).resolve(), machine=machine, home=None, owner=command_owner(machine)
    )
    data = {
        # Counts and not the strings, which is the same ruling `attach.check` makes about
        # `already_present` and this module makes about `project.name` two functions up — and it
        # has to be, or the three are inconsistent again. Every one of these four lists is read
        # out of `.stayfixed/local/attach.json` or out of `.claude/settings.local.json`, and both
        # are paths a clone can commit: `.gitignore` does not untrack a committed file. So they
        # are repository-authored, `--json` is what `skills/attach/SKILL.md` relays to the user,
        # and a marker id **bounded by a grammar** was already refused here on exactly this
        # reasoning. An allow rule and a settings key are less bounded than that, not more.
        "allow_removed": len(removed.allow_removed),
        "entries_removed": len(removed.entries_removed),
        "rules_removed": len(removed.rules_removed),
        "settings_keys_removed": len(removed.settings_keys_removed),
        # A count, for the reason `run_attach` gives above.
        "links_revoked": len(removed.links.revoked),
        # A count, and it has to be: besides `CREATED_DIRS`, stayfixed's own closed vocabulary,
        # this list names `paths.memory` and the directories above it, which the repository
        # configures.
        "directories_removed": len(removed.directories_removed),
        # A boolean this command computed, so it prints.
        "exclude_block_removed": removed.exclude_block_removed,
        # A boolean this command computed, so it prints.
        "exclude_block_kept": removed.exclude_block_kept,
        # A boolean this command computed, so it prints.
        "link_tree_kept": removed.link_tree_kept,
    }
    # The link tree is kept only while another checkout is attached, which keeps the block too.
    what = (
        "the exclude block and this checkout's link tree were"
        if removed.link_tree_kept
        else "the exclude block was"
    )
    kept = (
        f"; {what} kept, because another checkout of this repository is still attached"
        if removed.exclude_block_kept
        else ""
    )
    return Result(
        f"detached: {len(removed.allow_removed)} allow rule(s), "
        f"{len(removed.entries_removed)} hook entr(ies), "
        f"{len(removed.rules_removed)} Codex rule file(s), "
        f"{len(removed.links.revoked)} link(s), "
        f"{len(removed.directories_removed)} directory(ies); "
        f"the binding record was left in place{kept}",
        data,
    )


def register(groups: SubParsers) -> None:
    attach = common_flags(
        groups.add_parser("attach", help="bind this repository to the overlay and link its notes"),
        store=True,
    )
    attach.add_argument("--check", action="store_true", help=ATTACH_CHECK_HELP)
    attach.set_defaults(func=run_attach)

    detach = common_flags(
        groups.add_parser("detach", help="remove what attach added, and leave the binding")
    )
    detach.set_defaults(func=run_detach)
