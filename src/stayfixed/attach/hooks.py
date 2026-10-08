"""What a session hears about the overlay it is bound to — or not bound to.

This area registers it because the question is this area's: `binding_for` says whether a
repository is bound, and `unlinked_groups` whether its notes ever moved. `memory/hooks.py`
keeps its single `SessionStart` handler and the test that pins it.

Every line is fixed text with at most a count interpolated; the overlay's declared floor is
the one owner-authored string that prints, normalised the way it was validated. A repository
chooses `project.name`, `memory.groups`, `paths.memory` and its remote, and none of the four
appears here — a repository is untrusted input (principle 5), which is also why
`memory.store.refusal_reason` is not used: its text is built out of those same fields.
`MEMORY_PATH_REFUSED` is this module's own line and not `binding.MEMORY_GROUP_ESCAPES` relayed:
the refusal's text is bounded too, but a line that reaches the model is written where it is
read, and the two agree because both are fixed.

**At most once per session (`once_key`), and what it actually costs.** The matcher fires on
`startup`, `resume`, `clear`, `compact` and `fork`, and this handler runs ahead of
`worktree-link` in area-name order inside an entry whose `timeout` is ten seconds for both of
them.

`hooks/dispatch.py` banks a `once_key` only `if handler.once_key is not None and delivered`, and
`delivered` is `bool(result.context) or result.decision == Decision.DENY`. So the marker is laid
down exactly when this handler had something to say. A session that hears a line hears it once;
a **healthy** repository -- bound, linked, pushed, satisfied -- returns an empty result, banks
nothing, and is asked again on every one of those events.

And it is the healthy path that pays for the `git`, which is the opposite of what this docstring
said for three rounds. `binding_for` asks `origin_remote` on every run, at `gitenv`'s five-second
cap; `overlay_sync`'s `git status` and `git rev-list` are two seconds each and sit under `if not
lines:`, so they are reached exactly when nothing above them found anything wrong. Nine seconds
against the entry's ten, on the repository with nothing to report. The skip is real but it is
the other way round: a repository with a finding pays five seconds and not nine, because the
finding short-circuits the sync.

**So the sync is gated here, per context, rather than by changing what `once_key` means.**
`CONTINUED` says which invocations are one context asking again: on a `compact` the two extra
`git` calls are not paid and the handler answers on what the lines above already know, so a
healthy repository costs five seconds there instead of nine. Every other `source` pays --
`startup`, `resume`, `fork`, `clear`, and a payload carrying none -- so an invocation this module
cannot place in a context is treated as a new one and the nudge is never lost by default.

`resume` was in the set, and it is the case the nudge exists for. `claude --resume` and
`--continue` are a fresh launch of the harness, often days after the conversation they continue:
notes written to the overlay in that conversation are exactly what is uncommitted or unpushed by
then, and a `startup` that found the repository healthy banked no marker to say otherwise. A
`compact` is the same running process asking again within minutes, and it stays gated.
`dispatch.py`'s `once_key` semantics belong to every area's handlers and are untouched; the
five-second `origin_remote` is not gated either, because it is what decides three of the lines
above, and skipping it would drop them rather than defer them.

The cost, stated rather than hidden: an overlay that becomes unpushed *during* a session whose
`startup` found nothing to say is not reported on that session's later `compact`; the next
`resume` or `startup` reports it.
`stayfixed doctor` answers on demand, and the alternative is a pair of `git` calls re-run on every
compaction of a repository with nothing wrong with it, inside a budget shared with the handler
that links the note store.

Every import below the vocabulary is inside the handler body: `tests/test_areas.py` asserts
that discovery in a clean interpreter leaves `stayfixed.config`, `stayfixed.presets` and
`stayfixed.release` out of `sys.modules`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from stayfixed.attach import ATTACH_STORE
from stayfixed.hooks.api import Handler, HookEvent, HookResult, Policy

if TYPE_CHECKING:
    from stayfixed.config.schema import Config

# `SessionStart.source` values that are one context asking again, and the only thing this module
# reads the payload for.
#
# **What the gate rests on, and how much of it is established.** The `once_key` marker is filed
# under the session id -- `hooks/commands.py` builds the sink from `event.session_id` -- so "this
# context has already been asked" is true exactly when the invocation carries the id the marker was
# filed under. `compact` is in the set because it names the running harness continuing one
# conversation; `startup` and `fork` begin one and are out of it; `resume` is out of it because it
# is a new launch, often days later, over an overlay the conversation it continues may have left
# dirty; `clear` is out of it because a fresh conversation may carry a session id this handler has
# never answered for.
#
# **Those last two are assumptions about the harness, and this repository establishes neither.**
# `session_id` is read and passed through untouched (`hooks/dispatch.py` types it `str | None` and
# interprets nothing), no fixture here drives a real `/clear` or a real resume, and no field
# documented to this code says how ids are allocated. What they cost if they are wrong is not
# symmetric, which is why the set is drawn this way: if a `compact` arrived under a *new* id, the
# gate would skip the sync for a context that had never been asked and would lose the nudge; if a
# `clear` or a `resume` keeps the id, the whole cost is two `git` calls re-paid. So the set
# is as small as the saving allows, and a value not in it -- including a payload with no `source` at
# all -- pays: losing four seconds is recoverable and losing the one nudge a context gets is not.
# Whoever can measure the harness should replace this paragraph with the answer.
#
# The value is the harness's, it is compared against this constant, and it is never printed
# -- so nothing here touches the rule about what may reach `additionalContext`.
CONTINUED = frozenset({"compact"})
NO_OVERLAY = (
    "stayfixed: memory.mode is overlay and this machine records no overlay; "
    "run `stayfixed setup --preset recommended --overlay <path>`"
)
NOT_ASKABLE = "stayfixed: the overlay binding could not be checked on this machine"
NOT_ATTACHED = (
    "stayfixed: this repository is not attached to the overlay this machine records; "
    f"run `{ATTACH_STORE} --check`"
)
REMOTE_MISMATCH = (
    "stayfixed: the overlay records a different remote under this project's name; "
    "run `stayfixed attach --check` before trusting it"
)
# `memory.api.NO_ORIGIN_CAUSE` and `NO_ORIGIN_WAY_OUT`, the sentence every other surface says for
# a checkout with no `origin`. Spelled out rather than imported, because discovery imports this
# module and must not import the memory area; `tests/attach/test_hooks.py` holds the two equal.
NO_ORIGIN = (
    "stayfixed: this checkout has no `origin` remote, so there is nothing to bind to the overlay "
    "or to check its record against; add the `origin` remote (the one this project was bound "
    "with, when the overlay records one), then run `stayfixed attach`"
)
MEMORY_PATH_REFUSED = (
    "stayfixed: a memory path was refused for this repository, so its notes were not checked; "
    "`stayfixed doctor` says which"
)
REAL_DIRECTORIES = (
    "stayfixed: {count} memory group(s) are real directories rather than links into the overlay, "
    "so this session reads the repository's own copy; move them into the overlay and run "
    "`stayfixed attach`"
)
REQUIRES_UNREADABLE = (
    "stayfixed: the overlay's stayfixed.requires is not a form this stayfixed reads; "
    "`stayfixed doctor` says which"
)
REQUIRES = (
    "stayfixed: the overlay requires stayfixed {spec} and {running} is running; "
    "install a stayfixed that satisfies it"
)
# "Could not be counted" rather than "has no upstream": `ahead` is `None` for any non-zero or
# non-numeric answer from `rev-list @{upstream}..HEAD`, which is also a detached HEAD and a git
# that ran out of time. The missing upstream is named as the likely cause, not as the finding.
NO_UPSTREAM = (
    "stayfixed: the overlay's unpushed commits could not be counted — most often its branch has "
    "no upstream, and then nothing backs it up; it has {dirty} uncommitted change(s). Push it "
    "with -u"
)
UNPUSHED = (
    "stayfixed: the overlay has {ahead} unpushed commit(s) and {dirty} uncommitted change(s); "
    "push it so the other machine sees them"
)
# The two lines above are mutually exclusive, and that is the fix rather than a tidying.
# `Sync.ahead` is `None` when `git rev-list @{upstream}..HEAD` could not be answered, which for a
# branch with no upstream means *every* commit on it is unpushed -- the count is unknown, not
# zero. The sink read `if sync.ahead is None` and then, on the next `if`, formatted
# `ahead=sync.ahead or 0`, so a session with no upstream and a dirty tree heard "nothing backs it
# up" and "0 unpushed commit(s)" in one breath: the second sentence says the opposite of the
# first and is the one carrying a number. `NO_UPSTREAM` carries the dirty count itself so the
# no-upstream case still reports the half that is knowable, and `UNPUSHED` is reached only with
# a real `ahead` to print.


def _asked_before(event: HookEvent) -> bool:
    """Whether this invocation is a context that has already been asked (see `CONTINUED`).

    A module-level function and not an expression inside the handler, so that the one thing this
    module reads off the raw payload is in one place and named.
    """
    source = event.raw.get("source")
    return isinstance(source, str) and source in CONTINUED


def _overlay_status(event: HookEvent, config: Config | None) -> HookResult:
    from stayfixed.config.schema import OVERLAY_MODE

    if config is None or event.project_root is None or config.memory.mode != OVERLAY_MODE:
        return HookResult()
    try:
        import stayfixed
        from stayfixed.attach.binding import binding_for, unlinked_groups
        from stayfixed.config.overlay import overlay_root
        from stayfixed.config.paths import PathEscape
        from stayfixed.errors import Failure, Refusal
        from stayfixed.memory.api import MISMATCH, UNBOUND
        from stayfixed.memory.api import NO_ORIGIN as NO_ORIGIN_STATE
        from stayfixed.overlay.api import overlay_sync, requires_of, satisfies

        root = event.project_root
        try:
            overlay = overlay_root(None)
        except Failure:
            return HookResult(context=NOT_ASKABLE)
        if overlay is None:
            return HookResult(context=NO_OVERLAY)
        lines: list[str] = []
        try:
            binding = binding_for(root, config, machine=None)
        except (Failure, Refusal):
            return HookResult(context=NOT_ASKABLE)
        if binding.state == UNBOUND:
            lines.append(NOT_ATTACHED)
        elif binding.state == MISMATCH:
            lines.append(REMOTE_MISMATCH)
        elif binding.state == NO_ORIGIN_STATE:
            # The sentence every other surface says for this state, and never a mismatch's: that
            # line would send the reader to `--check` about a different remote that is not there.
            lines.append(NO_ORIGIN)
        try:
            real = unlinked_groups(root, config)
        except PathEscape:
            real = ()
            lines.append(MEMORY_PATH_REFUSED)
        if real:
            lines.append(REAL_DIRECTORIES.format(count=len(real)))
        spec = requires_of(overlay)
        if spec is not None:
            verdict = satisfies(spec, stayfixed.__version__)
            if verdict is None:
                lines.append(REQUIRES_UNREADABLE)
            elif not verdict:
                lines.append(REQUIRES.format(spec=spec, running=stayfixed.__version__))
        if not lines and not _asked_before(event):
            sync = overlay_sync(overlay)
            if sync.asked:
                if sync.ahead is None:
                    lines.append(NO_UPSTREAM.format(dirty=sync.dirty))
                elif sync.dirty > 0 or sync.ahead > 0:
                    lines.append(UNPUSHED.format(ahead=sync.ahead, dirty=sync.dirty))
        return HookResult(context="\n".join(lines)) if lines else HookResult()
    # An open handler never costs a session; `memory/hooks.py` keeps the same backstop.
    except Exception:
        return HookResult()


def register() -> list[Handler]:
    return [
        Handler(
            name="overlay-status",
            event="SessionStart",
            policy=Policy.OPEN,
            run=_overlay_status,
            once_key="overlay-status",
        )
    ]
