"""The two answers every delivery row in `stayfixed doctor` reads: the overlay root this machine
records and the note store this project resolves, each asked at most once per report.

`Answers` is what each delivery area's `doctor.py` creates in its `register()`, for its own rows. A
fresh one per `register()` call is a fresh one per report, so nothing one run resolved reaches the
next — the suite runs many reports in one process. `attach` and `overlay` create theirs through
this area's `api.py`; each area resolving the overlay root for itself is one small file read.

A module of its own rather than a name in `memory/doctor.py`, which discovery imports and which is
for that alone: `memory/api.py` publishes `Answers`, and every importer of that surface would
otherwise load this area's doctor rows with it.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, TypeVar

from stayfixed.config.overlay import overlay_root
from stayfixed.errors import Failure, Refusal
from stayfixed.memory.store import Store, resolve

if TYPE_CHECKING:
    from stayfixed.doctor.api import Context

_T = TypeVar("_T")


def _answered(ask: Callable[[], _T]) -> _T | None:
    """`ask()`, or `None` when it fails the way a resolution may: a `Failure`, a `Refusal` or an
    `OSError`.

    One rule for both answers, and the one the core's context applied before the rows moved into
    the areas: a `stayfixed.toml` that makes the store refuse, or a machine file that names an
    overlay nothing can read, is a row's skip — never "this check could not run", which is red and
    gates the exit code for something the repository did not do wrong.
    """
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
            self._overlay = (_answered(lambda: overlay_root(context.machine)),)
        return self._overlay[0]

    def store(self, context: Context) -> Store | None:
        """The note store this project resolves to, or `None` when it does not resolve."""
        if self._store is None:
            self._store = (
                _answered(lambda: resolve(context.root, context.config, machine=context.machine)),
            )
        return self._store[0]
