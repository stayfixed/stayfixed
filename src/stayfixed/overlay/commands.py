"""The `overlay` group: create an instance, and make it the owner's."""

from __future__ import annotations

import argparse
from pathlib import Path

from stayfixed.areas import SubParsers
from stayfixed.command import (
    DRY_RUN_HELP,
    INSTANCE_DIR_HELP,
    OVERLAY_ROOT_HELP,
)
from stayfixed.errors import Refusal
from stayfixed.overlay.create import TEMPLATE_REPOSITORY
from stayfixed.result import Result
from stayfixed.scaffold import render_report

# Neither source is a default, and that is the point. The GitHub path is permitted only after
# explicit confirmation, and a non-interactive caller — which in this harness is the usual one —
# can express confirmation only by naming the source. A default would turn an omitted flag into
# a repository created on somebody's account.
_NO_SOURCE = (
    "`stayfixed overlay create` needs one of --template (ask GitHub to generate a private "
    "repository from the template repository and clone it) or --local (render the shipped "
    "template here, touching no network). Neither is the default: say which one you want"
)


def run_overlay_create(args: argparse.Namespace) -> Result:
    from stayfixed.overlay.create import create
    from stayfixed.runner import subprocess_runner

    if args.source is None:
        raise Refusal(_NO_SOURCE)
    created = create(
        args.owner,
        args.name,
        source=args.source,
        root=Path(args.root).resolve(),
        runner=subprocess_runner(),
    )
    data = {"root": str(created.root), "source": created.source, "notes": list(created.notes)}
    return Result(f"overlay at {created.root} ({'; '.join(created.notes)})", data)


def run_overlay_init(args: argparse.Namespace) -> Result:
    from stayfixed.overlay.create import init_instance
    from stayfixed.runner import subprocess_runner

    result = init_instance(Path(args.root).resolve(), args.owner, runner=subprocess_runner())
    data = {"changed": list(result.changed), "notes": list(result.notes)}
    return Result("; ".join(result.notes), data)


def run_overlay_publish_template(args: argparse.Namespace) -> Result:
    from stayfixed.overlay.publish import publish_template
    from stayfixed.runner import subprocess_runner

    published = publish_template(
        args.owner, name=args.name, yes=args.yes, runner=subprocess_runner()
    )
    data = {
        "repository": published.repository,
        "changed": list(published.changed),
        "pushed": published.pushed,
        "notes": list(published.notes),
    }
    return Result(f"{published.repository}: {'; '.join(published.notes)}", data)


def run_overlay_upgrade(args: argparse.Namespace) -> Result:
    from stayfixed.overlay.upgrade import upgrade

    result = upgrade(Path(args.root).resolve(), dry_run=args.dry_run)
    # `scaffold.render_report` and not a second renderer: the report a user approves has to be
    # the one the same code path then acts on, which is the whole reason the scaffold engine
    # splits plan from apply. The decision list is appended to it rather than folded into it,
    # because it is the one thing the engine has no verb for.
    report = render_report(result.plan)
    if result.decisions:
        report += (
            "\n\nASK FIRST — these can grant a capability, so a matching hash is not consent:\n"
            + "\n".join(f"  {artifact}" for artifact in result.decisions)
        )
    data = {
        "report": report,
        "writes": result.plan.writes,
        "decisions": list(result.decisions),
        "dry_run": args.dry_run,
    }
    # A refused artifact is a finding, not a success: `apply` would raise on the whole plan, and
    # a dry run that printed a REFUSED section under exit 0 would say "nothing to do" about a
    # report that says the opposite.
    return Result(report, data, exit_code=1 if result.plan.refusals else 0)


def register(groups: SubParsers) -> None:
    overlay = groups.add_parser("overlay", help="the owner's private overlay")
    sub = overlay.add_subparsers(dest="command", metavar="<command>")

    create = sub.add_parser("create", help="create a private overlay repository, or render one")
    create.add_argument("--owner", required=True, help="the account the overlay belongs to")
    create.add_argument(
        "--name", default="stayfixed-private", help="the repository name (default: %(default)s)"
    )
    create.add_argument("--root", default=".", help=INSTANCE_DIR_HELP)
    # Mutually exclusive and neither is required, so that "neither was given" reaches the
    # command as a refusal naming both rather than as argparse's own usage error.
    source = create.add_mutually_exclusive_group()
    source.add_argument(
        "--template",
        dest="source",
        action="store_const",
        const="template",
        help="generate it on GitHub from the template repository and clone it",
    )
    source.add_argument(
        "--local",
        dest="source",
        action="store_const",
        const="local",
        help="render the shipped template here; no network call is made",
    )
    create.set_defaults(func=run_overlay_create, source=None)

    init = sub.add_parser("init", help="make a created overlay this owner's")
    init.add_argument("--owner", required=True, help="the account to name this overlay after")
    init.add_argument("--root", default=".", help=OVERLAY_ROOT_HELP)
    init.set_defaults(func=run_overlay_init)

    publish = sub.add_parser(
        "publish-template", help="publish the overlay template repository from this checkout"
    )
    publish.add_argument("--owner", required=True, help="the account to publish the template to")
    publish.add_argument(
        "--name",
        default=TEMPLATE_REPOSITORY,
        help="the repository name (default: %(default)s)",
    )
    # The gate, and it is a parameter rather than a step in a procedure: in an agent harness a
    # flag a model can type is not a control, so the three outward-facing acts — creating the
    # repository, marking it a template, pushing — all sit behind this one value.
    publish.add_argument(
        "--yes",
        action="store_true",
        help="create, mark and push; without it nothing outward-facing happens — the command "
        "renders, asks gh what exists, and reports what it would do",
    )
    publish.set_defaults(func=run_overlay_publish_template)

    upgrade = sub.add_parser("upgrade", help="refresh the files in an overlay nobody has edited")
    upgrade.add_argument("--root", default=".", help=OVERLAY_ROOT_HELP)
    upgrade.add_argument("--dry-run", action="store_true", help=DRY_RUN_HELP)
    upgrade.set_defaults(func=run_overlay_upgrade)
