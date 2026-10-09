"""The memory area's import surface: everything a consumer may import from this area.

A module and not the package's `__init__`, for one reason: `stayfixed.hooks.registry`
imports `stayfixed.memory.hooks`, which imports the package first, so a re-export list in
`__init__.py` pulls the whole area — configuration included — into every `discover()` call and
reddens `tests/test_areas.py`. Keeping the surface one level down costs a consumer six
characters and keeps discovery cheap, without a lazy `__getattr__` that would cost every
consumer its types.

**The list is what consumers outside this area import, plus what those names oblige** — not
what an area might be said to need, which is a list that grows names nothing imports. An area
that needs something absent from this list grows it deliberately, in a commit that says which
area and why — it does not import a private module of this area.

Thirty-four names are imported from outside this area today, by the `attach` and `overlay` areas
and by this repository's tests: the resolver (`resolve`, `permitted_roots` and `main_checkout`),
the overlay layout `attach` writes and `overlay` renders (`PROJECTS`, `PROJECT_RECORD`,
`STORE_DIR`, `COMMON_GROUP`), the one reader of the binding record, which `attach` reads it with
and answers its own way when it cannot (`read_binding_record`), the link tree
(`link`, `MakeUnder`, the home `attach` hands it for the harness link, `attach_main`,
`detach_main`, `harness_anchor`, `harness_link_needed`, `harness_memory_path`, `Links`,
`PartialLink`, `linked_names`, which `attach` reads to hide
every name the tree holds from git, and `link_sources`, every path the tree points at in the
overlay, which `attach` asks the length of before its first write), whether the machine records
any approval for a store that
does not exist yet (`approval_recorded`, which `attach` asks before a first link tree is built),
whether the machine's trust record can be read at all (`require_readable_record`, which `attach`
asks before its first write, since the index render and the harness link read it after), the
binding's one classifier and the states and causes it answers in (`binding_state`, `UNBOUND`,
`BOUND`, which `attach`'s own doctor row reads, `MISMATCH`, `NO_ORIGIN`, and the causes
`NO_REMOTE`, `NO_ORIGIN_CAUSE`, `NO_ORIGIN_WAY_OUT` and `DIFFERENT_REMOTE`), which `attach` answers
the binding question with instead of a second classifier of its own, the bundle slots
`tests/hooks/test_hooks_json.py` holds the hooks file to (`SLOTS`), the note store a `doctor` row
reads, resolved once per area per report (`Answers`, which the `attach` area's own `doctor.py`
creates for its row), and
the trust region `tests/test_install_path.py` asserts end to end (`DELIMITER`, `markers`). The
link graph's check is this area's own (`memory.graph`, which `memory refs` reports), so the
wiki-link grammar, the note walk and `resolved` have no reader outside it and are not here. The
overlay root the machine file records and the checkout's `origin` are the core's to answer
(`config.overlay.overlay_root`, `gitenv.origin_remote` and `gitenv.GitUnavailable`), because
`init` asks them too and the core may not import this area; the crossings still pinned are
listed in `tests/test_areas.py`.

**Ten more have no importer and stay, each for a reason written here**, because a name
kept in silence is what made this pass necessary:

- **The store, and the rest of the binding's vocabulary**: `Store` is what `resolve` returns, and a
  return type absent from a surface is a value a consumer can hold and cannot declare, which
  `tests/test_surfaces.py` derives rather than restates. `Withhold` is the other half of what
  `link`'s `harness` takes, beside the `MakeUnder` `attach` hands it, for the same reason.
  `BINDING_STATES` completes the closed vocabulary `binding_state` answers in, beside the four
  states that have a caller, for the reason the trust region's bullet below gives.

- **The rest of the trust region's vocabulary**: `wrap`, `new_nonce` and `UnsafeNote`, beside
  the `DELIMITER` and `markers` that already have a caller. Reading such a region needs
  `markers` and `DELIMITER`; producing one needs `wrap` and a nonce from `new_nonce`; a forged
  marker raises `UnsafeNote`. Publishing the reading half and hiding the writing half leaves a
  consumer able to recognise the region and unable to make one, which is the reason
  `attach/api.py` gives for `STATES` and `doctor/api.py` for `STATUSES`: half a closed
  vocabulary cannot be used by the consumer that is handed a value from it.
- **The trust gate**: `may_inject`, `changed`, `TrustState` and `UnreadableTrustRecord`. The
  project's standing constraint is that anything a repository authored reaches a model only
  after `stayfixed memory trust` and only inside a delimited region; a consumer that injects
  repository bytes therefore has to be able to *ask this area* whether it may, to honour the
  trust gate's re-prompt predicate — "a store that was trusted and is not any more" — and to
  tell "this trust record is broken" from "this store is not approved", which is the whole
  point of the class. A requirement a consumer cannot import is a requirement with no way to
  meet it, and this is the one group on this list where the cost of being wrong is a
  repository's bytes reaching a model unwrapped.

**Not here, though they look like candidates**: names with no importer in `src/`, `scripts/` or
`tests/`, no published signature naming them, and no reader reaching them by string. Each is
reachable from this area's own module, which is what `memory/commands.py`, `memory/hooks.py` and
this area's tests use; an area that comes to need one grows this list by the rule above.

- **The index group** — `INDEX_NAME`, `index_source`, `write_index`, `render_index`,
  `check_index`, `reconcile`, `Reconciliation`, `IndexCheck`. `attach`, which creates the
  symlinked index, calls none of them; the index is a command (`memory index`) and the areas
  that want one run it.
- **The notes group** — `read_note`, `render_note`, `with_index`, `write_note`, `NoteError`,
  `NoteType` — and nothing outside this area imports them. `snapshot`, `refresh_if_trusted` and
  `Snapshot` are the dance a caller of `write_note` must perform, so with `write_note` off this
  surface they have no caller here either.
- **The refs group** — `check_refs`, `unresolved`, `audience_violations`, `RefsReport`: an area
  existing is not the same as an area importing, and none imports these.
- **The inventory group** — `inventory`, `totals`, `Entry` — and nothing outside this area
  imports them.
- **The store predicates** — `in_repository`, `inside_project`, `refusal_reason`,
  `overlay_group_target` and `resolved`. `overlay_group_target` is read by `worktree.py`, one
  module over, and by nothing else, and none of the others has a reader outside this area.
- **The helpers** — `blocks`, `split`, `harness_link_parts`, with no reader outside this area.
- **The bundles group** — `fit`, `render`, and the `Bundle` and `Fit` their signatures name. The
  `bundles` row is this area's own (`memory/doctor.py`) and reads `memory.bundles` directly.

`PartialLink` and `Links` are here because `attach` imports them, and `Links` is the one name on
this list an entry names: `mutations/`'s "a type the surface names in a signature drops off the
surface".
"""

from stayfixed.memory.answers import Answers
from stayfixed.memory.bundles import SLOTS
from stayfixed.memory.store import (
    BINDING_STATES,
    BOUND,
    COMMON_GROUP,
    DIFFERENT_REMOTE,
    MISMATCH,
    NO_ORIGIN,
    NO_ORIGIN_CAUSE,
    NO_ORIGIN_WAY_OUT,
    NO_REMOTE,
    PROJECT_RECORD,
    PROJECTS,
    STORE_DIR,
    UNBOUND,
    Store,
    binding_state,
    main_checkout,
    permitted_roots,
    read_binding_record,
    resolve,
)
from stayfixed.memory.trust import (
    DELIMITER,
    TrustState,
    UnreadableTrustRecord,
    UnsafeNote,
    approval_recorded,
    changed,
    markers,
    may_inject,
    new_nonce,
    require_readable_record,
    wrap,
)
from stayfixed.memory.worktree import (
    Links,
    MakeUnder,
    PartialLink,
    Withhold,
    attach_main,
    detach_main,
    harness_anchor,
    harness_link_needed,
    harness_memory_path,
    link,
    link_sources,
    linked_names,
)

__all__ = [
    "BINDING_STATES",
    "BOUND",
    "COMMON_GROUP",
    "DELIMITER",
    "DIFFERENT_REMOTE",
    "MISMATCH",
    "NO_ORIGIN",
    "NO_ORIGIN_CAUSE",
    "NO_ORIGIN_WAY_OUT",
    "NO_REMOTE",
    "PROJECTS",
    "PROJECT_RECORD",
    "SLOTS",
    "STORE_DIR",
    "UNBOUND",
    "Answers",
    "Links",
    "MakeUnder",
    "PartialLink",
    "Store",
    "TrustState",
    "UnreadableTrustRecord",
    "UnsafeNote",
    "Withhold",
    "approval_recorded",
    "attach_main",
    "binding_state",
    "changed",
    "detach_main",
    "harness_anchor",
    "harness_link_needed",
    "harness_memory_path",
    "link",
    "link_sources",
    "linked_names",
    "main_checkout",
    "markers",
    "may_inject",
    "new_nonce",
    "permitted_roots",
    "read_binding_record",
    "require_readable_record",
    "resolve",
    "wrap",
]
