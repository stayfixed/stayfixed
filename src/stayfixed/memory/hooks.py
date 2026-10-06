"""Handlers this area contributes; the `hook <event>` entries in `hooks/hooks.json` invoke them.

Every import of `stayfixed.config`, `stayfixed.memory.store` and their neighbours happens **inside**
a handler body. `tests/test_areas.py` asserts that `discover()` in a clean interpreter imports
neither the configuration layer nor the presets, and discovery imports every area's `hooks` module —
so a module-level `from stayfixed.config.schema import Config` here reddens a test that belongs to
no area at all. The annotation is a string under `TYPE_CHECKING`, exactly as `stayfixed.hooks.api`
already writes it.

There is no `SessionStart` context handler here, and that absence is the design: the two
injection bundles are invoked as their own `hooks.json` entries so each gets its own platform
cap (see `bundles`). What remains is the one thing that must happen before any of them can
work — linking the store into a worktree.

Nothing a repository controls is ever put into `HookResult.context`. That field becomes
`additionalContext` in the `SessionStart` payload — model input with no delimiter, no nonce, no
trust record and no `may_inject` gate, which is precisely the channel `trust.wrap` exists to
close. `store.refusal_reason` builds its message out of raw `memory.groups` entries, and
`memory.groups` is an ordinary `stayfixed.toml` list with no schema constraint (a TOML
multi-line string carries literal newlines), so a clone reaches that text with no overlay and
no confirmation. A session-start diagnostic does not need to carry that text at all: every
message below is fixed and repository-independent, and where a `memory` command can say more
(`refusal_reason`'s detail, for instance) that is where the detail stays.

What the messages do carry is *that* something did not happen — no store, half a tree, a
refused path. A handler degrading open silently is how a half-built link tree became invisible
twice over; the fixed lines are what keep "nothing to do" and "something went wrong" apart
without putting a repository's words in front of the model.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from stayfixed.hooks.api import Handler, HookEvent, HookResult, Policy

if TYPE_CHECKING:
    from stayfixed.config.schema import Config

# Fixed, and carrying nothing the repository chose. A plain string is not an import, so
# these cost `discover()` nothing. `count` is the length of a list this module built, never a
# value the repository supplied, so interpolating it changes nothing about that.
NO_STORE = "stayfixed: no memory store for this project"
LINKED = "stayfixed: linked {count} memory path(s) into this worktree"
PARTIAL = LINKED + "; the rest could not be created"
NOT_LINKED = "stayfixed: a memory path was refused for this worktree and was not linked"
# The revocation half of the trust gate, and it gets its own line because it is its own event:
# the harness's project-memory link has just been withdrawn because this store's approval has
# lapsed, so a session that had native memory a moment ago no longer does. Reported as
# `LINKED.format(count=0)` — or not at all — it would look like "nothing to do".
REVOKED = (
    "stayfixed: this store is no longer trusted, so the harness memory link was removed — "
    "run `stayfixed memory trust --in-repo-memory` after reviewing what changed"
)
# `git` could not be run, or the machine configuration file is broken. Neither is "there is
# no store", which is why `gitenv.git_answer` tells "could not ask" from "the answer is
# nothing" and `overlay_root` raises for a file it cannot read or parse rather than
# answering `None` as for an unrecorded overlay. Saying `NO_STORE` for those would send the
# user to `stayfixed attach` for a fault that is in their machine, not in their project.
NOT_ASKABLE = "stayfixed: the memory store could not be located on this machine"
# Off a terminal the only home a hook trusts is the password database's, and the harness finds
# its memory directory through `HOME`. Where the two differ, a link made under the first is one
# the harness never reads, so none is made and the session is told; at a terminal `attach` reads
# `HOME`, which is the person's own there.
NO_HARNESS_LINK = (
    "stayfixed: HOME is not this user's home in the password database, so this hook made no "
    "harness memory link; run `stayfixed attach` from a terminal to make it"
)


def _link_worktree(event: HookEvent, config: Config | None) -> HookResult:
    if config is None or event.project_root is None:
        return HookResult()
    try:
        from stayfixed.config.machine import homes_agree, owner_home
        from stayfixed.errors import Failure, Refusal
        from stayfixed.memory.store import resolve
        from stayfixed.memory.worktree import PartialLink, link

        try:
            store = resolve(event.project_root, config)
        except Failure:
            # `GitUnavailable` and `MachineConfigError`: the store could not be *asked* about,
            # which is a different event from there not being one, and the fixed line says so.
            return HookResult(context=NOT_ASKABLE)
        if store is None:
            return HookResult(context=NO_STORE)
        # Said rather than sniffed, as `hooks.commands` says it for the machine file: a hook is
        # never a person at a terminal, so `HOME` does not choose where the harness link goes.
        # Where `HOME` is not that home, the harness looks somewhere else, so the hook makes the
        # tree's links and no harness link (`NO_HARNESS_LINK`).
        home = owner_home(interactive=False) if homes_agree() else None
        try:
            links = link(event.project_root, store, config, home=home, harness=home is not None)
        except PartialLink as partial:
            # A write failed part-way. `link` makes one symlink at a time, so the tree now
            # holds some names and not the rest — and `worktree`'s own docstring says a group
            # missing from the tree is missing from the floor the reference guard derives
            # from it, "invisible twice". Keep degrading open, and say how many were made
            # instead of letting the list die with the exception.
            return HookResult(context=PARTIAL.format(count=len(partial.created)))
        except Failure:
            # `main_checkout` runs first inside `link`, so the same "could not ask `git`" event
            # can arrive here rather than from `resolve`. One fixed line for one event.
            return HookResult(context=NOT_ASKABLE)
        except Refusal:
            # Not the same event as a disk error, and deliberately not reported as one.
            # `link` raises `PathEscape` when a repository-controlled `memory.groups` name
            # tries to leave the worktree tree; swallowing that in a blanket catch would make an
            # attempted escape indistinguishable from "nothing to do". It still must not cost
            # the session, and the refusal's message is built out of the offending name — so
            # the fixed line goes to the model and the name stays out of it, exactly as
            # `refusal_reason`'s text does.
            return HookResult(context=NOT_LINKED)
        if links.revoked:
            # Said before the count of what was linked, and instead of it: the approval that
            # lapsed is what the owner has to act on, and the two never co-occur — the same
            # gate decides both.
            return HookResult(context=REVOKED)
        lines = [LINKED.format(count=len(links.created))] if links.created else []
        if links.withheld:
            lines.append(NO_HARNESS_LINK)
        return HookResult(context="\n".join(lines)) if lines else HookResult()
    # The backstop stays broad on purpose: a memory handler never costs a session,
    # and `resolve` alone reaches `tomllib`, `subprocess` and the filesystem. Narrowing it to
    # `OSError` would let an unforeseen exception out of a `Policy.OPEN` handler. What the two
    # clauses above buy is that the two failures this function can actually produce are
    # neither silent nor the same event.
    except Exception:
        return HookResult()


def register() -> list[Handler]:
    return [
        Handler(
            name="worktree-link",
            event="SessionStart",
            policy=Policy.OPEN,
            run=_link_worktree,
        )
    ]
