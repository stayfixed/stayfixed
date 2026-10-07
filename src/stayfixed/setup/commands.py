"""The `setup` command: configure this machine from a preset, once.

One command and not a group with subcommands, the same shape `attach`/`detach` take: `setup`
does one of two things depending on which flags are given (the second is the per-repository
git hook `--git-hooks` installs), and neither is a subcommand of the other because a
subcommand would still need `--root` to make sense of `--git-hooks` while the machine-level
flags stay siblings of it rather than children.

`--home` and `--machine` are not test affordances bolted on afterwards: `CONTRIBUTING.md`
forbids a test from touching the developer's real `~/.claude` or `~/.config/stayfixed/`, and a
command whose only mode writes to the real ones could not be tested at all. Both default to the
real paths, exactly as `--root` defaults to the current directory elsewhere in this CLI.

`--machine` is **not** gated behind an interactive shell here, unlike `attach`/`detach`'s. That
gate is about a flag that decides which overlay a *read* trusts; `setup` is the command that
*writes* the machine file in the first place, so gating its own `--machine` would refuse the
very thing this command exists to do, on every non-interactive run — including every scripted
check of the CLI's exit codes. Scoped to `attach`/`detach` on purpose, and left there.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from stayfixed.areas import SubParsers
from stayfixed.command import HOME_HELP, SETUP_MACHINE_HELP, SETUP_ROOT_HELP
from stayfixed.errors import Failure, Refusal
from stayfixed.result import Result
from stayfixed.runner import subprocess_runner

# Imported at module scope, and not deferred into `run_setup` the way `setup.run.setup` still
# is: a test that wants to keep this command away from a real `claude`/`codex` binary has to
# monkeypatch a name it can see, and `stayfixed.setup.commands.subprocess_runner` is one hop
# rather than two — `run_setup` calling straight into `stayfixed.runner`'s own attribute
# left the patch depending on an import this module does not own the shape of. The runner was
# the `overlay` area's when that was written; it has since become the leaf module `runner.py`,
# and this sentence follows it. `commands.py` is never imported by the hook registry (only
# `hooks.py` files are, per `tests/test_areas.py`), so a module-scope import here does not
# reach the clean-interpreter `discover()` that `tests/test_areas.py` holds `hooks.py` to.

_BOTH_MODES = (
    "--git-hooks installs a hook into one repository; --preset writes machine-level files. "
    "A single run has one exit code to report, so it does only one of the two — run them "
    "separately"
)


def run_git_hooks(args: argparse.Namespace) -> Result:
    from stayfixed.guards.api import install, uninstall

    root = Path(args.root).resolve()
    if args.uninstall:
        removed = uninstall(root)
        if removed.foreign:
            summary = (
                f"left {removed.path} as it was: it is not stayfixed's hook; nothing was removed"
            )
        elif not removed.removed:
            summary = f"there is no stayfixed hook at {removed.path}; nothing was removed"
        elif removed.restored is not None:
            summary = f"removed {removed.path}; restored the foreign hook chained to it"
        else:
            summary = f"removed {removed.path}; there was no foreign hook to restore"
        data: dict[str, Any] = {
            "path": str(removed.path),
            "restored": str(removed.restored) if removed.restored is not None else None,
            "removed": removed.removed,
            "foreign": removed.foreign,
        }
        return Result(summary, data)

    installed = install(root)
    if installed.preserved is not None:
        summary = (
            f"installed the commit-message hook at {installed.path}; the hook that was there "
            f"is kept at {installed.preserved} and chained to"
        )
    elif installed.replaced:
        summary = f"reinstalled the commit-message hook at {installed.path}"
    else:
        summary = f"installed the commit-message hook at {installed.path}"
    install_data = {
        "path": str(installed.path),
        "preserved": str(installed.preserved) if installed.preserved is not None else None,
        "replaced": installed.replaced,
    }
    return Result(summary, install_data)


NO_MACHINE_HOME = (
    "the password database lists no home directory for this user, so there is no default "
    "machine configuration file; pass --machine PATH to write one, which no hook reads"
)


def run_setup(args: argparse.Namespace) -> Result:
    if args.git_hooks:
        if args.preset is not None:
            raise Refusal(_BOTH_MODES)
        return run_git_hooks(args)

    from stayfixed.config.machine import homes_agree, machine_config_path
    from stayfixed.setup.run import setup

    # `interactive=False`, like every *reader* of this file (`config.loader.load`,
    # `config.overlay.overlay_root`, `memory.trust._trust_file`) — and unlike this command until
    # now, which was the one `machine_config_path()` call in the tree taking the `isatty` sniff.
    # With `XDG_CONFIG_HOME=/xdg`, an owner running `stayfixed setup` in their own shell wrote
    # `/xdg/stayfixed/config.toml`, got exit 0, and every reader then said "no overlay root is
    # recorded in the machine configuration; run `stayfixed setup`" — the defect
    # `config.loader.load`'s docstring says it fixed ("Half a file behind a gate is not a
    # gate"), reintroduced on the write side. `--machine` itself is still honoured: a path the
    # owner typed on their own command line is not an environment variable a repository can set.
    #
    # Resolved here rather than in `register()`, so that `stayfixed setup --help` prints the
    # sentence and not whichever home directory the parser happened to be built under.
    home = Path.home() if args.home is None else Path(args.home).expanduser()
    machine = (
        machine_config_path(interactive=False)
        if args.machine is None
        else Path(args.machine).expanduser()
    )
    if machine is None:
        # Off `--machine`, the file is under the home the password database records, and this
        # user has none there; a file put under `HOME` instead would be one no hook reads.
        raise Failure(NO_MACHINE_HOME)
    report = setup(
        args.preset or "recommended",
        home=home,
        machine=machine,
        runner=subprocess_runner(),
        yes=args.yes,
        overlay=args.overlay,
        project_root=Path(args.root).resolve(),
        settings=Path(args.settings).expanduser() if args.settings else None,
    )
    data = {
        "machine_written": report.machine_written,
        "plugins_installed": list(report.plugins_installed),
        "deny_written": report.deny_written,
        "cli_on_path": report.cli_on_path,
        "overlay": str(report.overlay) if report.overlay is not None else None,
        "notes": list(report.notes),
    }
    # Where `HOME` is not the database's home, the file is not where the person may look for it,
    # so the line says which home it went under (`config.machine`'s docstring says why).
    under = (
        ", under the home the password database records for this user rather than HOME, "
        "because that is where a hook reads it"
        if args.machine is None and not homes_agree()
        else ""
    )
    summary = "; ".join(
        (
            f"machine configuration written to {machine}{under}",
            f"{len(report.plugins_installed)} plugin(s) installed",
            "deny rules merged" if report.deny_written else "deny rules unchanged",
            "stayfixed is on PATH" if report.cli_on_path else "stayfixed is not on PATH",
            f"overlay recorded at {report.overlay}" if report.overlay else "no overlay recorded",
            *report.notes,
        )
    )
    return Result(summary, data)


def register(groups: SubParsers) -> None:
    from stayfixed.setup.machine import USER_SETTINGS

    setup = groups.add_parser("setup", help="configure this machine from a preset")
    setup.add_argument(
        "--preset", default=None, help="the preset to install (default: recommended)"
    )
    setup.add_argument(
        "--yes",
        action="store_true",
        help=(
            "confirm the one irreversible act: creating an overlay repository on GitHub with "
            "--overlay create:<owner>/<name>. Nothing else asks"
        ),
    )
    # Both defaults are `None` and are resolved in `run_setup`. A path computed here is computed
    # when the parser is built, which is every run of every command — and printed by
    # `stayfixed setup --help`, where it was the developer's own home directory.
    setup.add_argument("--home", default=None, help=HOME_HELP)
    setup.add_argument(
        "--settings",
        default=None,
        help=(
            f"write the user-scope settings file here instead of <home>/{USER_SETTINGS}, "
            "for a dotfiles layout that links that file into another tree"
        ),
    )
    setup.add_argument("--machine", default=None, help=SETUP_MACHINE_HELP)
    setup.add_argument(
        "--overlay",
        default=None,
        help=(
            "record an existing overlay by path, or create one with "
            "create:<owner>/<name> (asks GitHub for a private repository from the template)"
        ),
    )
    setup.add_argument(
        "--git-hooks",
        action="store_true",
        help="install the commit-message hook into this repository instead of machine setup",
    )
    setup.add_argument(
        "--uninstall",
        action="store_true",
        help="with --git-hooks, remove the hook and restore what it chained to",
    )
    setup.add_argument("--root", default=".", help=SETUP_ROOT_HELP)
    setup.set_defaults(func=run_setup)
