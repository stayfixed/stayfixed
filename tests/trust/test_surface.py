"""The trust package's `api.py` is held to the same contract every other area's is.

CONTRIBUTING states it once for all of them: the list "is what consumers actually reach for, not
what the area finds tidy"."""

from __future__ import annotations

import stayfixed.trust.api as trust


def test_the_surface_carries_what_every_consumer_reaches_for() -> None:
    # An equality and not a subset, as `tests/doctor/test_surface.py` holds its own: a subset lets
    # an export arrive unnoticed, and this surface once published three names nothing imported
    # (`Approval`'s importer, `approve` and `revoke`, which only tests called). What each name is
    # doing here is written beside it. No mutation entry, for that file's reason: the mutation is
    # adding an export, two lines in `api.py` and not one substituted line.
    required = {
        # the record as `memory` reads it: every approval (`memory.trust`), with the type it answers
        # in, whose fields `memory.trust` reads, and the refusal of a record that cannot be read
        "recorded",
        "Approval",
        "UnreadableTrust",
        # one subject's state and the vocabulary it answers in (`memory.commands`)
        "state",
        "State",
        # carrying an approval across a write stayfixed made (`memory.trust`)
        "refresh",
        # where the record lives, which `setup --approval-boundary` names
        "record_path",
        # what an area's `approvals.py` builds its kinds from (`memory.approvals`)
        "ApprovalKind",
        "KindContext",
        "Subject",
        # the approve path the `memory trust` alias runs, and what it reads off its command line
        "approve_kind",
        "kind_context",
        # the sentence asking the person at the machine for an approval (`memory`, `attach`)
        "PERSON_RUNS",
        # `setup --approval-boundary`'s advice: the deny rules, the user setting and the managed
        # settings that keep an agent's shell out of the record, and where managed settings live
        "record_deny_rules",
        "SANDBOX_ON",
        "ENFORCING_SETTINGS",
        "managed_named",
        # a write an agent's sandbox refused: telling one (`setup`), the record's refusal of one
        # (`memory`), and the one sentence every writer says it in with its two remedies
        "sandbox_refused",
        "SandboxedWrite",
        "SANDBOX_REFUSED",
        "RUN_OUTSIDE",
        "ONLY_OUTSIDE",
    }
    assert required == set(trust.__all__)
