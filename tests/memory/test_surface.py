"""What this area publishes. The three checks every surface is held to are
`tests/test_surfaces.py`'s; this list is the one thing that is this area's own."""

from __future__ import annotations

import stayfixed.memory.api as memory


def test_the_memory_surface_carries_what_every_consumer_reaches_for() -> None:
    # This list is the contract. A consumer that needs something absent from it grows the list
    # deliberately, in a commit that says which consumer and why — it does not import a private
    # module, and it does not get told after the fact that its import was a review finding.
    #
    # An equality, because every name below has its argument, in `api.py` or beside it here, and
    # a subset lets an export arrive unnoticed — the hole `tests/guards/test_surface.py` names.
    #
    # No entry in `mutations/`, for the reason every other area's surface test gives: the
    # mutation is adding an export, which is two lines in `api.py` — the import and the
    # `__all__` entry — and not one substituted line. Measured by hand instead: re-exporting
    # `store.refusal_reason` reddens this test and this test alone, and under the old
    # `required <= set(...)` it reddened nothing at all.
    required = {
        # the resolver and the store it yields, for attach
        "resolve",
        "Store",
        "permitted_roots",
        "main_checkout",
        # the overlay's per-project layout: attach writes it, overlay renders it
        "PROJECTS",
        "PROJECT_RECORD",
        "STORE_DIR",
        "COMMON_GROUP",
        # the one reader of the binding record, which attach reads with a policy of its own
        "read_binding_record",
        # the link tree attach builds and its `attached` row reports on
        "link",
        "attach_main",
        "detach_main",
        "harness_anchor",
        "harness_link_needed",
        "harness_memory_path",
        "Links",  # what `link` returns
        "PartialLink",  # what it raises part-way, carrying `.created`
        "linked_names",  # every name the tree holds, which attach hides from git
        # every path the tree points at in the overlay, which attach asks the length of before
        # its first write
        "link_sources",
        # the note store a doctor row reads, resolved once per area per report, for the attach
        # area's row
        "Answers",
        # the bundle slots, which tests/hooks/test_hooks_json.py holds the hooks file to
        "SLOTS",
        # the trust region, whole. Reading one needs `markers` and `DELIMITER`, which
        # tests/test_install_path.py already imports; producing one needs `wrap` and a nonce,
        # and a forged marker raises `UnsafeNote`. Half a closed vocabulary cannot be used by
        # the consumer handed a value from it.
        "markers",
        "DELIMITER",
        "wrap",
        "new_nonce",
        "UnsafeNote",
        # the trust gate. Repository bytes reach a model only after `stayfixed memory trust`
        # and only inside a delimited region, so an area that injects them has to be able to
        # ask this area whether it may, to see a store that was trusted and is not any more,
        # and to tell a broken record from an unapproved store.
        "may_inject",
        "approval_recorded",  # the gate answered for a store attach has not built yet
        "require_readable_record",  # the trust record read before attach writes anything
        # the binding's one classifier and its whole vocabulary: `attach`, `attach --check`,
        # the `attached` row and the session-start line answer the binding question with it, where
        # a second classifier in `attach` had drifted from this one
        "binding_state",
        "BINDING_STATES",
        "BOUND",
        "UNBOUND",
        "MISMATCH",
        "NO_ORIGIN",
        "NO_REMOTE",
        "NO_ORIGIN_CAUSE",
        "NO_ORIGIN_WAY_OUT",
        "DIFFERENT_REMOTE",
        "changed",
        "TrustState",
        "UnreadableTrustRecord",
    }
    assert required == set(memory.__all__)
