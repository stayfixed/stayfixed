"""The note store's rows in `stayfixed doctor`, and the two answers every delivery row reads.

`bundles` and `store-debris` are this area's: both measure the note store, and the store is this
area's to resolve. `doctor`'s core discovers this module by name and asks its rows after its own
(CONTRIBUTING.md, "Areas"), so the core resolves neither the store nor the overlay root, and
nothing about either lives in the report's `Context`.

`Answers` is what each delivery area's `register()` creates for its rows: the overlay root this
machine records and the note store this project resolves, each asked at most once and only when a
row reads it. A fresh one per `register()` call is a fresh one per report, so nothing one run
resolved reaches the next — the suite runs many reports in one process. `attach` and `overlay`
create their own through this area's `api.py`; each area resolving the overlay root for itself
is one small file read.

Every import sits inside a function body, as in a `hooks.py`: this module is imported by
discovery, and by `memory/api.py` for `Answers`, which every area that imports this area's surface
loads.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, TypeVar

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from stayfixed.doctor.api import Context, Contribution, Row
    from stayfixed.memory.store import Store

_T = TypeVar("_T")

# When a bundle's largest part counts as "reaching the cap", as a fraction of
# `native_caps.hook_output_chars`. `doctor` reports a bundle that does not fit *and* one that
# reaches the cap, and the second needs a threshold that the first does not.
#
# A fraction and not `parts == slots`: `preset-rules` has one slot and a preset that carries rules
# fills it, so that predicate warns on every correct installation that has any and says nothing.
# A named cap (CONTRIBUTING.md#named-caps), and the shipped file that changes with it is
# `hooks/hooks.json`, which is where a slot count is raised when this warning turns out to be
# right.
NEARLY_FULL = 0.9


def _answered(ask: Callable[[], _T]) -> _T | None:
    """`ask()`, or `None` when it fails the way a resolution may: a `Failure`, a `Refusal` or an
    `OSError`.

    One rule for both answers, and the one the core's context applied before the rows moved here:
    a `stayfixed.toml` that makes the store refuse, or a machine file that names an overlay
    nothing can read, is a row's skip — never "this check could not run", which is red and gates
    the exit code for something the repository did not do wrong.
    """
    from stayfixed.errors import Failure, Refusal

    try:
        return ask()
    except (Failure, Refusal, OSError):
        return None


class Answers:
    """The overlay root this machine records and the note store this project resolves, for one
    report, each resolved on first use and never again.

    A one-element tuple is an answer, `None` is "not asked yet", so an answer that is itself
    `None` — no overlay recorded, no store — is remembered rather than asked again.
    """

    def __init__(self) -> None:
        self._overlay: tuple[Path | None] | None = None
        self._store: tuple[Store | None] | None = None

    def overlay(self, context: Context) -> Path | None:
        """The overlay root the machine file records, whether or not anything is there."""
        if self._overlay is None:
            from stayfixed.config.overlay import overlay_root

            self._overlay = (_answered(lambda: overlay_root(context.machine)),)
        return self._overlay[0]

    def store(self, context: Context) -> Store | None:
        """The note store this project resolves to, or `None` when it does not resolve."""
        if self._store is None:
            from stayfixed.memory.store import resolve

            self._store = (
                _answered(lambda: resolve(context.root, context.config, machine=context.machine)),
            )
        return self._store[0]


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
    the remedy names the command that lists them under the trust gate.
    """
    from stayfixed.doctor.api import OK, SKIP, WARN, Row

    store = answers.store(context)
    if store is None:
        return Row(SKIP, "the note store does not resolve", "")
    found = 0
    for target in store.groups.values():
        for path in target.rglob("*"):
            if path.is_file() and path.suffix != ".md" and not path.name.startswith("."):
                found += 1
    if found:
        return Row(
            WARN,
            f"{found} file(s) in the note store are not notes",
            "run `stayfixed memory inventory` to see them, and move or delete each one",
        )
    return Row(OK, "the note store holds notes and nothing else")


def register() -> Contribution:
    """This area's two rows, sharing one `Answers`, so the store resolves once for both."""
    from stayfixed.doctor.api import Contribution

    answers = Answers()
    return Contribution(
        checks=(
            ("bundles", lambda context: _bundles(context, answers)),
            ("store-debris", lambda context: _store_debris(context, answers)),
        )
    )
