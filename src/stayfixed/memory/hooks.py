"""Handlers this area contributes; the `hook <event>` entries in `hooks/hooks.json` invoke them.

Every import of `stayfixed.config`, `stayfixed.memory.store` and their neighbours happens **inside**
a handler body. `tests/boundaries/test_discovery.py` asserts that `discover()` in a clean
interpreter imports neither the configuration layer nor the presets, and discovery imports every
area's `hooks` module — so a module-level `from stayfixed.config.schema import Config` here reddens
a test that belongs to no area at all. The annotation is a string under `TYPE_CHECKING`, exactly
as `stayfixed.hooks.api` already writes it.

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

from typing import TYPE_CHECKING, NamedTuple

from stayfixed.hooks.api import Handler, HookEvent, HookResult, Policy

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

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


class Withheld(NamedTuple):
    """Why a hook makes no harness memory link, and what makes it for this store.

    One wording with two readers: the session-start line (`line`), and the `harness-link` row this
    area adds to `stayfixed doctor` (`memory.doctor`), which prints `cause` and `remedy` as its
    detail and remedy. Owned here, beside the hook that withholds the link, so the two never say
    different things.
    """

    cause: str
    remedy: str

    @property
    def line(self) -> str:
        return f"stayfixed: {self.cause}; {self.remedy}"


# Off a terminal the only home a hook trusts is the password database's, and the harness finds
# its memory directory through `HOME`. Where the two differ, a link made under the first is one
# the harness never reads, so none is made and the session is told what does make it. That
# depends on the store: in overlay mode `attach`, run from a terminal, links every worktree under
# the `HOME` it reads there; for any other store this hook is the only thing that makes the link,
# and it makes it only where the two homes agree.
NO_HARNESS_LINK_OVERLAY = Withheld(
    "HOME is not this user's home in the password database, so a hook makes no harness memory link",
    "run `stayfixed attach --store <overlay>/projects/<project>/memory` from a terminal to make it",
)
NO_HARNESS_LINK = Withheld(
    "HOME is not this user's home in the password database, so a hook makes no harness memory "
    "link, and no stayfixed command makes it for this store while that is so",
    "start sessions with HOME set to that home and a hook makes it",
)
NO_HARNESS_LINK_NO_HOME = Withheld(
    "the password database lists no home directory for this user, so a hook makes no harness "
    "memory link, and no stayfixed command makes it for this store",
    "start sessions as a user the password database lists a home directory for",
)
# A user the database lists no home for: no `HOME` agrees with no home, so the cause is the
# missing entry and not `HOME`, and an overlay store is still linked by `attach` from a terminal,
# under the `HOME` it reads there, which has to name a home: unset or empty, it names none, and
# `attach` refuses.
NO_HARNESS_LINK_OVERLAY_NO_HOME = Withheld(
    "the password database lists no home directory for this user, so a hook makes no harness "
    "memory link",
    "run `stayfixed attach --store <overlay>/projects/<project>/memory` from a terminal with HOME "
    "set to a home directory to make it",
)
# An empty `HOME` names no home (`config.machine.homes_agree`): the harness finds no memory
# directory of this user's through it, so no link anyone makes is one it reads, and `attach` at a
# terminal whose `HOME` is empty refuses. The way out is the same whatever the store.
NO_HARNESS_LINK_EMPTY_HOME = Withheld(
    "HOME is empty, so it names no home directory and a hook makes no harness memory link",
    "start sessions with HOME set to this user's home in the password database",
)


def _link_worktree(event: HookEvent, config: Config | None) -> HookResult:
    if config is None or event.project_root is None:
        return HookResult()
    try:
        import os

        from stayfixed.config.machine import anchor_home, homes_agree
        from stayfixed.errors import Failure, Refusal
        from stayfixed.memory.store import resolve
        from stayfixed.memory.worktree import MakeUnder, PartialLink, Withhold, link

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
        # tree's links and no harness link (`no_harness_link`).
        home = anchor_home(interactive=False) if homes_agree() else None
        try:
            links = link(
                event.project_root,
                store,
                config,
                harness=MakeUnder(home) if home is not None else Withhold(_lapsed_link_home()),
            )
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
            lines.append(no_harness_link(config, os.environ).line)
        return HookResult(context="\n".join(lines)) if lines else HookResult()
    # The backstop stays broad on purpose: a memory handler never costs a session,
    # and `resolve` alone reaches `tomllib`, `subprocess` and the filesystem. Narrowing it to
    # `OSError` would let an unforeseen exception out of a `Policy.OPEN` handler. What the two
    # clauses above buy is that the two failures this function can actually produce are
    # neither silent nor the same event.
    except Exception:
        return HookResult()


def no_harness_link(config: Config, env: Mapping[str, str]) -> Withheld:
    """Why a hook withholds the harness link, and what makes it, saying only what is true of this
    store and of `HOME` in `env`. The database is asked first: where it lists no home for this
    user, no `HOME` would let a hook make the link, so `HOME` is not the cause whatever the store.
    An empty `HOME` is asked next, since no command makes a link that the harness reads through
    it, `attach` from a terminal included."""
    from stayfixed.config.machine import home_is_empty, passwd_home
    from stayfixed.config.schema import OVERLAY_MODE

    overlay = config.memory.mode == OVERLAY_MODE
    if passwd_home() is None:
        return NO_HARNESS_LINK_OVERLAY_NO_HOME if overlay else NO_HARNESS_LINK_NO_HOME
    if home_is_empty(env):
        return NO_HARNESS_LINK_EMPTY_HOME
    return NO_HARNESS_LINK_OVERLAY if overlay else NO_HARNESS_LINK


def _lapsed_link_home() -> Path | None:
    """Where a link the harness may still read can be, for withdrawing one whose approval lapsed.

    Not a home this hook makes anything under: `HOME`, which it does not trust. A link there is
    every upgrader's state, made under `HOME` by an earlier release, and the harness keeps
    reading it after the store's approval lapses unless something takes it back. Withdrawal only
    ever removes a link pointing at this very store (`worktree._unlink`), so a `HOME` that
    direnv, mise or a devcontainer chose from a file the clone commits gains nothing from it. A
    relative `HOME` is never used: it names a directory relative to the clone this hook runs in.
    """
    import os
    from pathlib import Path

    chosen = os.environ.get("HOME")
    if not chosen or not os.path.isabs(chosen):
        return None
    return Path(chosen)


def register() -> list[Handler]:
    return [
        Handler(
            name="worktree-link",
            event="SessionStart",
            policy=Policy.OPEN,
            run=_link_worktree,
        )
    ]
