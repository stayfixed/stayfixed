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

from stayfixed.config.schema import PROJECT_NAME
from stayfixed.errors import Refusal
from stayfixed.overlay.layout import CODEX_PLUGIN_MANIFEST, MARKETPLACE_MANIFEST, PLUGIN_MANIFEST

# One path segment: `config.schema.PROJECT_NAME`, the one name grammar. An owner name becomes a
# directory, half a remote path, a marketplace selector and the suffix on both manifest names, so
# it is checked once here rather than at each of those; the leading class is what keeps a value
# shaped like an option (`-flag`) out of an option's position in an argv. It is checked in this
# module rather than in `create` because the suffix grammar and the manifest-name grammar are the
# same grammar.
SEGMENT = PROJECT_NAME
# What the shipped template calls itself, and what `init_instance` suffixes.
OVERLAY_PLUGIN = "stayfixed-overlay"
OVERLAY_MARKETPLACE = "stayfixed-overlay-marketplace"


def segment(label: str, value: str) -> str:
    """`value` if it is one path segment, or a `Refusal` naming what it was for."""
    if not SEGMENT.match(value):
        raise Refusal(
            f"{label} {value!r} is not one path segment matching {SEGMENT.pattern}; it becomes a "
            "directory name, half a remote path and a marketplace selector, so it is refused "
            "rather than quoted"
        )
    return value


def _claims(value: object, expected: str) -> bool:
    """Whether a manifest's `name` is `expected`, or `expected-<owner>` after `overlay init`."""
    if not isinstance(value, str):
        return False
    if value == expected:
        return True
    suffix = value.removeprefix(f"{expected}-")
    return suffix != value and bool(SEGMENT.match(suffix))


def owner_of(root: Path) -> str | None:
    """The account `overlay init` named this overlay after, or `None` where it named nobody.

    Read from the manifests themselves, in the order `init` writes them, and from the first that
    carries a suffix: an `init` that could not write one of them still named the others. The
    marketplace is matched against its own name, because `stayfixed-overlay-marketplace-<owner>`
    also starts with the plugin's `stayfixed-overlay-`. A suffix that is not one path segment is
    not an owner; nothing read here is quoted anywhere, it only decides a rename.
    """
    for relative, expected in (
        (PLUGIN_MANIFEST, OVERLAY_PLUGIN),
        (MARKETPLACE_MANIFEST, OVERLAY_MARKETPLACE),
        (CODEX_PLUGIN_MANIFEST, OVERLAY_PLUGIN),
    ):
        try:
            document = json.loads((root / relative).read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        name = document.get("name") if isinstance(document, dict) else None
        if isinstance(name, str) and _claims(name, expected) and name != expected:
            return name.removeprefix(f"{expected}-")
    return None


def overlay_fault(root: Path) -> str | None:
    """Why `root` is not an overlay root, or `None` when it is one.

    Every string this returns is this function's own or a path the caller typed. A manifest's
    own bytes never reach it.
    """
    if not root.is_dir():
        return f"{root} is not a directory"
    for relative, expected in (
        (PLUGIN_MANIFEST, OVERLAY_PLUGIN),
        (MARKETPLACE_MANIFEST, OVERLAY_MARKETPLACE),
    ):
        path = root / relative
        if not path.is_file():
            return f"{root} does not carry the overlay layout ({relative} is missing)"
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return f"{root} carries a {relative} that cannot be read as JSON"
        if not isinstance(document, dict) or not _claims(document.get("name"), expected):
            return (
                f"{root} carries a {relative} that does not name a stayfixed overlay; its `name` "
                f"has to be {expected}, or {expected}-<owner> after `stayfixed overlay init`"
            )
    return None


def require_overlay(root: Path, *, because: str) -> None:
    """Refuse unless `root` is an overlay. `because` says what the caller was about to do."""
    fault = overlay_fault(root)
    if fault is not None:
        raise Refusal(f"{fault}; {because}")
