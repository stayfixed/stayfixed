"""The memory area's import surface: everything a consumer may import from this area.

A module and not the package's `__init__`, for one measured reason: `stayfixed.hooks.registry`
imports `stayfixed.memory.hooks`, which imports the package first, so a re-export list in
`__init__.py` pulls the whole area — configuration included — into every `discover()` call and
reddens `tests/test_areas.py`. Keeping the surface one level down costs a consumer six
characters and keeps discovery cheap, without a lazy `__getattr__` that would cost every
consumer its types.

**The list is what consumers outside this area import, plus what those names oblige.** That is
a change of rule and not only of length: it used to be what the areas named in this docstring
were said to need, and this area's own history is what that produces — seventy names, of which
forty-five had no importer anywhere in `src/`, `scripts/` or `tests/`. An area that needs
something absent from this list grows it deliberately, in a commit that says which area and why
— it does not import a private module of this area.

Twenty-two names are imported from outside this area today, and the areas that reach for them
are `attach` and `doctor`: the resolver and its store (`resolve`, `Store`, `permitted_roots` and
`main_checkout`), the overlay layout `attach` writes and `overlay` renders (`PROJECTS`,
`PROJECT_RECORD`, `COMMON_GROUP`), the link tree
(`link`, `attach_main`, `detach_main`, `harness_anchor`, `harness_link_needed`,
`harness_memory_path`, `Links`, `PartialLink`, and `linked_names`, which `attach` reads to hide
every name the tree holds from git), whether the machine records any approval for a store that
does not exist yet (`approval_recorded`, which `attach` asks before a first link tree is built),
whether the machine's trust record can be read at all (`require_readable_record`, which `attach`
asks before its first write, since the index render and the harness link read it after), the
binding's one classifier and its vocabulary (`binding_state`, `BINDING_STATES` and its four
members, and the causes `NO_REMOTE`, `NO_ORIGIN_CAUSE`, `NO_ORIGIN_WAY_OUT` and
`DIFFERENT_REMOTE`), which `attach` and `doctor` answer the binding question with instead of a
second classifier of their own,
the bundles `doctor` reports on (`fit`, `render`, `SLOTS`), and the trust region
`tests/test_install_path.py` asserts end to end (`DELIMITER`, `markers`). The link graph's check
is this area's own (`memory.graph`, which `memory refs` reports), so the wiki-link grammar, the
note walk and `resolved` have no reader outside it and are not here. The overlay root the
machine file records and the checkout's `origin` are the core's to answer
(`config.overlay.overlay_root`, `gitenv.origin_remote` and `gitenv.GitUnavailable`), because
`init` asks them too and the core never imports this area.

**Nine more have no importer and stay, each for a reason written here**, because a name
kept in silence is what made this pass necessary:

- **The types those twenty-two name in their signatures**: `Bundle` and `Fit` (`fit`,
  `render`). `tests/test_surfaces.py` derives this rather than restating
  it, and a return type absent from a surface is a value a consumer can hold and cannot
  declare — the one thing a surface exists to prevent.
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

**Trimmed, by the pass that set this rule: thirty-three names**, every one of them with no importer
in `src/`, `scripts/` or `tests/`, no published signature naming it, and no reader reaching it by
string. Nothing was deleted: each is still where it was written and is reachable from this area's
own module, which is what `memory/commands.py`, `memory/hooks.py` and this area's tests already do.
What went is the claim that another area reads it.

- **The index group** — `INDEX_NAME`, `index_source`, `write_index`, `render_index`,
  `check_index`, `reconcile`, `Reconciliation`, `IndexCheck`. Published on the argument that
  `worktree.py` and `bundles.py` both present `index_source` as *the* place the per-link target
  rule reaches the index, and that neither a reader nor `attach`, which creates the symlinked
  index in the first place, could call it. `attach` calls none of them; the index is a command
  (`memory index`) and the areas that want one run it.
- **The notes group** — `read_note`, `render_note`, `with_index`, `write_note`, `NoteError`,
  `NoteType` — published for a notes consumer, and nothing outside this area imports them.
  `snapshot`, `refresh_if_trusted` and `Snapshot` went with them: they were published as the
  dance a caller of the exported `write_note` must perform, and with `write_note` gone there is
  no caller on this surface to perform it. That argument comes back with the verb if an area
  ever needs the verb.
- **The refs group** — `check_refs`, `unresolved`, `audience_violations`, `RefsReport`. The
  paragraph that said this debt was paid was measuring the wrong thing: an area existing is not
  the same as an area importing.
- **The inventory group** — `inventory`, `totals`, `Entry` — published for a skills consumer,
  and nothing outside this area imports them.
- **The store predicates** — `in_repository`, `inside_project`, `refusal_reason`,
  `overlay_group_target` and `resolved`. `in_repository` was published
  "because `inside_project` hands the reader to it in as many words", which is this surface
  citing itself; `refusal_reason` was
  published for an overlay hook that does not exist; `overlay_group_target` is read by
  `worktree.py`, one module over, and by nothing else.
- **The leftovers** — `blocks`, `split`, `harness_link_parts`. Three helpers with no argument
  beside them in the docstring this one replaces, which is how they survived. (`linked_names`
  was a fourth, and came back when `attach` began hiding the tree it names.)

`PartialLink` stays: `attach` imports it, which is what the paragraph that argued for it
predicted. `Links` stays for the same reason and is the one name on this list an entry names:
`mutations/`'s "a type the surface names in a signature drops off the surface".
"""

from stayfixed.memory.bundles import SLOTS, Bundle, Fit, fit, render
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
    UNBOUND,
    Store,
    binding_state,
    main_checkout,
    permitted_roots,
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
    PartialLink,
    attach_main,
    detach_main,
    harness_anchor,
    harness_link_needed,
    harness_memory_path,
    link,
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
    "UNBOUND",
    "Bundle",
    "Fit",
    "Links",
    "PartialLink",
    "Store",
    "TrustState",
    "UnreadableTrustRecord",
    "UnsafeNote",
    "approval_recorded",
    "attach_main",
    "binding_state",
    "changed",
    "detach_main",
    "fit",
    "harness_anchor",
    "harness_link_needed",
    "harness_memory_path",
    "link",
    "linked_names",
    "main_checkout",
    "markers",
    "may_inject",
    "new_nonce",
    "permitted_roots",
    "render",
    "require_readable_record",
    "resolve",
    "wrap",
]
