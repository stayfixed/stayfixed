"""The import surface: everything a consumer may import from this area.

A module and not the package's `__init__`, for the reason `stayfixed.guards.api`,
`stayfixed.memory.api` and `stayfixed.ledger.api` all give: area discovery imports a package
before it imports the submodule it wants, so a re-export list in `__init__.py` would pull this
whole area — and with it the configuration layer — into every `discover()` call.
`tests/docs/test_surface.py` asserts the `__init__` imports nothing at all.

**Outside this area, `project` imports `trail_target` (the paragraphs on `trail_path` and
`trail_target` say why), `stayfixed.assess.gates` imports the three gate functions (the last
paragraph), and `stayfixed.assess.gates` records what the `docs` and `trail` gates read by path
through `docs_reads` and `trail_reads`; nothing imports any other name on this list**, measured
over `src/`, `scripts/` and `tests/`: this area's own tests reach `stayfixed.docs.plans`,
`stayfixed.docs.hygiene`, `stayfixed.docs.graph` and `stayfixed.docs.trail` directly, and every
other area runs the commands.
So every other name below is here on an argument rather than on a caller, and the argument is
written beside it — a surface that survives a trim with no explanation is what made the trim
necessary.

The three besides `trail_target`, the gate functions and what two of them read are checks this
area *is*, one call each: `check_budgets`, `check_links` and `check_memory_graph` each answer one
question about the documentation tree and return `Finding`s from `stayfixed.findings`, the leaf
three areas share — a consumer imports the finding shape from there, not from here.

`lint` and the `Lint` it returns are **not** here: `plan check` and the `plan` gate are this
area's own, and `plan_gate` is the one call a consumer runs.

`Finding` and `labels` are **not** here: they are `stayfixed.findings`', and a consumer imports
them from there.

**The trail half is not here.** The markers, the file name, `Trail`, `read_trail`,
`trail_path`, `render_listing`, `rebuild` and `undeclared_new_documents` stay in
`stayfixed.docs.trail`, which `docs/commands.py` and this area's own tests reach directly: no
other area reads them, and an area that needs one grows this list, in a commit that says which
area and why.

The three checks above have no importer; they stay on an argument about shape — one call per
check rather than the machinery behind it — and on `tests/test_surfaces.py`'s floor, which
refuses a surface exporting no function or record at all. Whether this area publishes at all
is a structural decision and the owner's; `ledger/api.py` records the same finding about its
own list.

**`trail_target`, for the `project` area**, which ships `trail.toml` beside the roadmap template
and must put it where `docs trail` reads it, under the *preset's* `[paths]`, a place this
configuration may never use. It is the location with no disk access, and the engine contains
every target it plans: `trail_path` contains its answer against the root, so asked there it
would refuse whenever that place passed through a symlink, and it stays in
`stayfixed.docs.trail` for this area's own commands.

**`docs_reads` and `trail_reads`, for `stayfixed assess` and `stayfixed adopt promote`**, which ask
git whether each file those gates read by path is tracked, since CI sees only those. Each lists
what its gate reads, beside the gate function it must agree with: the link targets are read by
this area's link reader, so the gate and the question cannot disagree about which files a link
names. `stayfixed.assess.gates` holds them on the gates' records.

**Three gate functions, for `stayfixed assess`.** `docs_gate`, `plan_gate` and
`trail_gate` are each `(root, config, base) -> list[Finding]`, one gate's whole composition.
`stayfixed assess` runs them as values, and this area's own commands answer with the same
functions (`docs check` with no flag, `docs trail --check`) or with the one call a function
wraps (`plan check` calls `lint`), so a command and its gate cannot drift apart.
"""

from stayfixed.docs.graph import check_memory_graph
from stayfixed.docs.hygiene import check_budgets, check_links, docs_gate, docs_reads
from stayfixed.docs.plans import plan_gate
from stayfixed.docs.trail import trail_gate, trail_reads, trail_target

__all__ = [
    "check_budgets",
    "check_links",
    "check_memory_graph",
    "docs_gate",
    "docs_reads",
    "plan_gate",
    "trail_gate",
    "trail_reads",
    "trail_target",
]
