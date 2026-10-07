"""What a user reads before saying yes.

The count line names every outcome including the zeros, so "nothing was skipped" is something
the report says rather than something the reader has to notice is missing.

**A removal that keeps its file says so.** A `REMOVE` with a payload takes a region or keyed
entries out of a file that holds other text, and its reason gains `PART_ONLY`, so
`remove AGENTS.md` never reads as the file going when only stayfixed's part of it did.

**Every target is printed through `printable`.** A plan reports a relocated or left-behind
artifact at the target `.stayfixed/manifest.json` recorded, and that file is committed, so the
string is repository-authored and may hold a line break or an escape sequence. A target the path
grammar accepts prints as itself; any other prints as `<artifact id>`, which is this build's own
vocabulary. The plan `apply` consumes is untouched: only what a person or an agent reads is
bounded, here, so no caller of this renderer can forget to.
"""

from __future__ import annotations

from stayfixed.printed import PATH_VALUE
from stayfixed.scaffold.model import WRITING, Action, Plan, Refused, Verb


def printable(item: Action | Refused) -> str:
    """The target as it may be printed: itself inside the path grammar, its artifact id outside."""
    return item.target if PATH_VALUE.match(item.target) else f"<{item.artifact_id}>"


# A `REMOVE` that carries a payload rewrites its file without stayfixed's region or entries, and
# the file stays; a delete command must not read as though the whole file went.
PART_ONLY = "stayfixed's part only, the file stays"


def _reason(action: Action) -> str:
    if action.verb is Verb.REMOVE and action.payload is not None:
        return f"{action.reason}; {PART_ONLY}"
    return action.reason


def render_report(planned: Plan) -> str:
    lines = [
        f"{action.verb:<14} {printable(action)}  ({_reason(action)})" for action in planned.actions
    ]
    if planned.unchanged:
        lines.append(f"{'unchanged':<14} {', '.join(sorted(planned.unchanged))}")
    if planned.refusals:
        lines.append("")
        lines.append("REFUSED — nothing will be written while any of these stands:")
        lines += [f"  {printable(r)}  ({r.reason})" for r in planned.refusals]
    created = sum(1 for a in planned.actions if a.verb is Verb.CREATE)
    updated = sum(1 for a in planned.actions if a.verb in WRITING and a.verb is not Verb.CREATE)
    removed = sum(1 for a in planned.actions if a.verb is Verb.REMOVE)
    skipped = sum(1 for a in planned.actions if a.verb is Verb.SKIP_MODIFIED)
    lines.append("")
    lines.append(
        f"{created} to create, {updated} to update, {removed} to remove, "
        f"{skipped} skipped, {len(planned.unchanged)} unchanged, {len(planned.refusals)} refused"
    )
    return "\n".join(lines)
