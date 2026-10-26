"""The import surface: everything a consumer may import from this area.

A module and not the package's `__init__`, for the reason every area's surface is one: area
discovery imports a package before the submodule it wants, and the package stays empty of imports.

- `prove`, `Receipt`, `Verdict` and `Counts`: a command that runs a test command and judges it the
  way `stayfixed prove` does takes the receipt and its verdict from here, and the counts it
  carries. The ledger is one: `stayfixed.ledger.regressions` runs each fixed bug entry's
  `regression` through `prove`, and `stayfixed.ledger.commands` counts its receipts by `Verdict`.
- `line` and `INTERRUPTED`: the ledger's `bugs regressions` prints each receipt in the one line
  `stayfixed prove` prints, and stops its set of runs at the first receipt whose reason is
  `INTERRUPTED`, since `prove` returns one for a Ctrl-C or a terminating signal rather than raising.

The protocol an adapter implements is not here: it is `stayfixed.profiles.runners`, the leaf both
the adapters and this area import. Nor is the discovery of the adapters this stayfixed ships,
`stayfixed.profiles.adapters.shipped_adapters`, beside the red-run hints' discovery: a surface
re-exports only its own area's names (`tests/test_surfaces.py`), and `profiles` is no area, so a
reader imports it from there as `prove` itself does.
"""

from stayfixed.prove.counts import Counts
from stayfixed.prove.run import INTERRUPTED, Receipt, Verdict, line, prove

__all__ = [
    "INTERRUPTED",
    "Counts",
    "Receipt",
    "Verdict",
    "line",
    "prove",
]
