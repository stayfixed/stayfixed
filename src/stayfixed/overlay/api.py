"""The overlay area's import surface: everything another area may import from it.

The list is chosen from what consumers outside this area actually reach for. An area that needs
something absent from it grows it deliberately, in a commit that says which area and why — it
does not import a private module of this area.

`setup` builds an overlay and so needs `create`, `init_instance`, `target_root`, `require_overlay`
and `overlay_fault`; `Created` and `Initialised` come with the first two, because a return type
absent from this list is a value `setup` can hold and cannot declare. `attach` reads `common/claude`
and `common/codex` inside the layout (`COMMON_CLAUDE`, `COMMON_CODEX`). The runner is a leaf module
(`stayfixed.runner`), not this area's: every area that launches a program imports it from there, and
none reaches it through this surface.

Two names are here with no importer in `src/`, on purpose:

- `COMMON_MEMORY`, the third of the three `common/` directories beside `COMMON_CLAUDE` and
  `COMMON_CODEX`. The layout is what a consumer reads; publishing two thirds of it invites the
  third to be spelled again by hand, which is the drift these constants exist to stop.
- `CODEX_PLUGIN_MANIFEST`, beside `PLUGIN_MANIFEST` and `MARKETPLACE_MANIFEST`. `init_instance`
  rewrites all three and its docstring says why in as many words — "the project ships a Codex
  half of everything else and `.codex-plugin/plugin.json` left unsuffixed is that collision
  still happening, one harness over". A consumer that checks the Claude manifests and cannot
  name the Codex one reproduces exactly that bug.

`OVERLAY_FILES` is here for `scripts/check_artifacts.py`, which asks whether a built wheel
carries every template file and can only answer that against this list. It is the one consumer
outside `src/`, and the reason this docstring names it is that an earlier trim removed the
export on the strength of "nothing outside this area imports it" while that script, added in the
same branch, imported it out of `layout` — a sentence and a violation merged green together,
because `tests/test_areas.py` walked `src/` alone. It walks `scripts/` too now.

**Trimmed, when the area boundaries were drawn tight.** `COMMON` had no importer anywhere.
`CAPABILITY_FILES`, `template_root`, `templates`, `upgrade` and `OverlayUpgrade` had none outside
this area: `upgrade` is driven by this area's own command module, and the template tree was
published against a sentence predicting that the `release` package would need it,
which nothing in `stayfixed.release` does. If it ever does, it grows the list then, which is what
this docstring asks of every other area.

`PRE_COMMIT_CONFIG` and `PRE_COMMIT_HOOK` are published for `attach`, which installs the
overlay's commit-time secret scan on a machine where it is missing: the overlay ships the
configuration, and this area's own `pre-commit` row in `stayfixed doctor` asks about the same two
names, so they are spelled once, in the layout, beside the files the overlay ships.

`requires_of`, `satisfies`, `Sync` and `overlay_sync` are published for the `attach` area's
session-start handler. The floor is one grammar and two readers, and the other is this area's own
`overlay-requires` row in `stayfixed doctor` (`overlay/doctor.py`); the overlay's sync state is the
overlay's question, asked where the overlay is owned.

`later` and `RELEASE`, the order of two versions and the `X.Y.Z` grammar whole, are the core's
`stayfixed.semver`, which the floor's reader builds on; `upgrade`, `doctor` and `stayfixed gate`
import them from there.
"""

from stayfixed.overlay.create import Created, Initialised, create, init_instance, target_root
from stayfixed.overlay.identity import overlay_fault, require_overlay
from stayfixed.overlay.layout import (
    CODEX_PLUGIN_MANIFEST,
    COMMON_CLAUDE,
    COMMON_CODEX,
    COMMON_MEMORY,
    MARKETPLACE_MANIFEST,
    OVERLAY_FILES,
    PLUGIN_MANIFEST,
    PRE_COMMIT_CONFIG,
    PRE_COMMIT_HOOK,
)
from stayfixed.overlay.requires import requires_of, satisfies
from stayfixed.overlay.sync import Sync, overlay_sync

__all__ = [
    "CODEX_PLUGIN_MANIFEST",
    "COMMON_CLAUDE",
    "COMMON_CODEX",
    "COMMON_MEMORY",
    "MARKETPLACE_MANIFEST",
    "OVERLAY_FILES",
    "PLUGIN_MANIFEST",
    "PRE_COMMIT_CONFIG",
    "PRE_COMMIT_HOOK",
    "Created",
    "Initialised",
    "Sync",
    "create",
    "init_instance",
    "overlay_fault",
    "overlay_sync",
    "require_overlay",
    "requires_of",
    "satisfies",
    "target_root",
]
