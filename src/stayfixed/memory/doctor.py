"""This area's rows in `stayfixed doctor`: `bundles`, `store-debris` and `harness-link`.

The first two measure the note store, and the store is this area's to resolve. `doctor`'s core
discovers this module by name and asks its rows after its own (CONTRIBUTING.md, "Areas"), so the
core never resolves the store and nothing about it lives in the report's `Context`. The store comes
from the `Answers` (`memory.answers`) this module's `register()` creates, one per report, so both
rows read one answer. The third says whether a hook can make the harness memory link, which this
area's hook makes (`memory.hooks`), in that hook's own words.

Every import sits inside a function body, as in a `hooks.py`: this module is imported by
discovery, and a module-level import here would be one more thing every `doctor` run loads before
it has asked anything.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from stayfixed.doctor.api import Context, Contribution, Row
    from stayfixed.memory.answers import Answers

# When a bundle's largest part counts as "reaching the cap", as a fraction of
# `native_caps.hook_output_chars`. `doctor` reports a bundle that does not fit *and* one that
# reaches the cap, and the second needs a threshold that the first does not.
#
# A fraction and not `parts == slots`: what reaches the platform cap is a part, which the fraction
# measures, while a bundle whose last slot holds a short part still has that part's room to grow,
# so that predicate would warn on a correct installation.
# A named cap (CONTRIBUTING.md#named-caps), and the shipped file that changes with it is
# `hooks/hooks.json`, which is where a slot count is raised when this warning turns out to be
# right.
NEARLY_FULL = 0.9


def _bundles(context: Context, answers: Answers) -> Row:
    """A bundle whose notes do not fit its slots needs a human, not a wider cap.

    Raising a slot count edits `hooks/hooks.json`, which is a shipped file, so this is reported
    and never repaired. A part already close to the platform cap is the warning before that:
    one more sentence in one note and the bundle needs a slot that does not exist.
    """
    from stayfixed.doctor.api import OK, RED, SKIP, WARN, Row
    from stayfixed.findings import listed
    from stayfixed.memory.bundles import SLOTS, fit, render

    store = answers.store(context)
    if store is None:
        return Row(SKIP, "the note store does not resolve, so no bundle can be built")
    ceiling = context.config.native_caps.hook_output_chars * NEARLY_FULL
    over: list[str] = []
    full: list[str] = []
    for bundle in SLOTS:
        measured = fit(bundle, store, context.config)
        if not measured.fits:
            over.append(bundle.value)
            continue
        emitted = [
            render(bundle, store, context.config, part=n) for n in range(1, measured.parts + 1)
        ]
        if any(text is not None and len(text) >= ceiling for text in emitted):
            full.append(bundle.value)
    if over:
        return Row(
            RED,
            f"{len(over)} bundle(s) do not fit their session-start slots: {listed(over)}",
            "run `stayfixed memory fit`, then shorten or unflag the notes it names",
        )
    if full:
        return Row(
            WARN,
            f"{len(full)} bundle(s) have a part at the platform cap: {listed(full)}",
            "run `stayfixed memory fit`",
        )
    return Row(OK, "every bundle fits its slots")


def _store_debris(context: Context, answers: Answers) -> Row:
    """Files in the note store that are not notes.

    Counted and not named. A filename in the store is repository-authored in `in-repo` and
    `local-only` mode — the two the preset ships — so the count is this check's own answer and
    the remedy names the command that lists them under the trust gate. In `in-repo` mode the tree
    is the repository's too, so the walk lists at most `fsops.WALK_ENTRIES` entries, the cap every
    walk with a "could not tell" answer reads, and past it says it could not tell.
    """
    from stayfixed import fsops
    from stayfixed.doctor.api import OK, SKIP, WARN, Row

    store = answers.store(context)
    if store is None:
        return Row(SKIP, "the note store does not resolve", "")
    found = listed = 0
    for target in store.groups.values():
        for path in target.rglob("*"):
            listed += 1
            if listed > fsops.WALK_ENTRIES:
                return Row(
                    WARN,
                    f"the walk of the note store stopped after {fsops.WALK_ENTRIES:,} entries, so "
                    "it cannot say whether the store holds files that are not notes",
                    "run `stayfixed memory inventory` to see what the store holds",
                )
            if fsops.is_file(path) and path.suffix != ".md" and not path.name.startswith("."):
                found += 1
    if found:
        return Row(
            WARN,
            f"{found} file(s) in the note store are not notes",
            "run `stayfixed memory inventory` to see them, and move or delete each one",
        )
    return Row(OK, "the note store holds notes and nothing else")


def _harness_link(context: Context) -> Row:
    """Whether a hook can make the harness memory link, as far as the home it trusts goes.

    A hook trusts only the password database's home, and the harness finds its memory directory
    through `HOME`, so where the two differ the hook makes no harness link (`memory.hooks`). Asked
    of the report's environment through `config.machine.homes_agree`, the predicate the hook asks
    of its own, and told in the hook's words (`memory.hooks.no_harness_link`), so the row and the
    session-start line say one thing. The core's `ignored-env` row says which directory the machine
    files are under meanwhile; this row says what it costs the harness link, and what makes it for
    this store.
    """
    from stayfixed.config.machine import homes_agree
    from stayfixed.doctor.api import OK, WARN, Row
    from stayfixed.memory.hooks import no_harness_link

    if homes_agree(context.env):
        # Agreeing is also `HOME` unset or empty, and then it is not that home: the hook takes
        # the database's.
        if context.env.get("HOME"):
            return Row(
                OK,
                "HOME is this user's home in the password database, so a hook can make the "
                "harness memory link",
            )
        return Row(
            OK,
            "HOME is unset or empty, so a hook can make the harness memory link under this "
            "user's home in the password database",
        )
    withheld = no_harness_link(context.config)
    return Row(WARN, withheld.cause, withheld.remedy)


def register() -> Contribution:
    """This area's three rows, the two that read the store sharing one `Answers`, so the store
    resolves once for both."""
    from stayfixed.doctor.api import Contribution
    from stayfixed.memory.answers import Answers

    answers = Answers()
    return Contribution(
        checks=(
            ("bundles", lambda context: _bundles(context, answers)),
            ("store-debris", lambda context: _store_debris(context, answers)),
            ("harness-link", _harness_link),
        )
    )
