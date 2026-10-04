"""Is this directory an overlay? One answer, for every command that has to ask.

The question was spelled two and a half ways before this module existed, and none of the three
excluded much. `setup._validate_overlay_root` asked whether two manifest *files* existed — which
the stayfixed checkout itself satisfies, and which any Claude Code plugin repository satisfies,
so the "carries the overlay's own layout" half of the machine's trust anchor was worth almost
nothing. `overlay upgrade` asked nothing at all, and wrote every shipped file — a plugin manifest, a
hooks file and a GitHub Actions workflow among them — into whatever `--root` named, which
defaults to `.`. And `create._populated` asks whether `.claude-plugin/` is a directory, which is
a third question again.

**What an overlay is, for the purpose of trusting one.** Both manifests must parse, and both
must name this tree as a stayfixed overlay: `stayfixed-overlay` and `stayfixed-overlay-marketplace`
as the shipped template writes them, or either with `-<owner>` appended as `overlay init` writes
them. That is the same pair `init_instance` renames and the harnesses install the overlay by, so
it is the tree's own claim about what it is rather than a coincidence of directory names.

It is a *structural* probe and not a security boundary, and nothing here pretends otherwise: a
repository that wants to look like an overlay can commit two manifests with those names. What it
buys is that the ordinary accidents stop — a mistyped `--root`, a project directory, the
stayfixed checkout, somebody else's plugin repository — and that the one control that does bound a
hostile clone (`setup`'s "not inside, over, or in any checkout of the project an agent works in")
is no longer standing alone.

**`create._populated` deliberately stays the weaker probe.** It answers "did a tree already
arrive here", which is what the create step's idempotence rule needs: a `gh` that gave up
mid-clone leaves a partial tree, and asking *this* question of it would answer "not an overlay"
and create the repository a second time. Two questions, two probes, and this docstring is why.

**Nothing a repository authored is quoted back.** A manifest's `name` is bytes from a directory this
process was pointed at, and a repository is untrusted input (principle 5), so the refusal says which
file failed and what it had to say, never what it actually said.
"""

from __future__ import annotations

import json
from pathlib import Path

from stayfixed.errors import Refusal
from stayfixed.overlay.naming import NAMED, SEGMENT, claims


def segment(label: str, value: str) -> str:
    """`value` if it is one path segment, or a `Refusal` naming what it was for."""
    if not SEGMENT.match(value):
        raise Refusal(
            f"{label} {value!r} is not one path segment matching {SEGMENT.pattern}; it becomes a "
            "directory name, half a remote path and a marketplace selector, so it is refused "
            "rather than quoted"
        )
    return value


def overlay_fault(root: Path) -> str | None:
    """Why `root` is not an overlay root, or `None` when it is one.

    Every string this returns is this function's own or a path the caller typed. A manifest's
    own bytes never reach it. The manifests asked are `naming.NAMED`'s probed rows.
    """
    if not root.is_dir():
        return f"{root} is not a directory"
    for row in NAMED:
        if not row.probed:
            continue
        path = root / row.path
        if not path.is_file():
            return f"{root} does not carry the overlay layout ({row.path} is missing)"
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return f"{root} carries a {row.path} that cannot be read as JSON"
        if not isinstance(document, dict) or not claims(document.get("name"), row.name):
            return (
                f"{root} carries a {row.path} that does not name a stayfixed overlay; its `name` "
                f"has to be {row.name}, or {row.name}-<owner> after `stayfixed overlay init`"
            )
    return None


def require_overlay(root: Path, *, because: str) -> None:
    """Refuse unless `root` is an overlay. `because` says what the caller was about to do."""
    fault = overlay_fault(root)
    if fault is not None:
        raise Refusal(f"{fault}; {because}")
