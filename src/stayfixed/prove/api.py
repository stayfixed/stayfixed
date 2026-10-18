"""The import surface: everything a consumer may import from this area.

A module and not the package's `__init__`, for the reason every area's surface is one: area
discovery imports a package before the submodule it wants, and the package stays empty of imports.

- `prove`, `Receipt`, `Verdict` and `Counts`: a command that runs a test command and judges it the
  way `stayfixed prove` does takes the receipt and its verdict from here, and the counts it
  carries.
- `record_gate`: `stayfixed gate`, which keeps one evidence record a run beside `prove`'s, in the
  same directory under the same key.

The protocol an adapter implements is not here: it is `stayfixed.profiles.runners`, the leaf both
the adapters and this area import. Nor is the discovery of the adapters this stayfixed ships,
`stayfixed.profiles.adapters.shipped_adapters`, beside the red-run hints' discovery: a surface
re-exports only its own area's names (`tests/test_surfaces.py`), and `profiles` is no area, so a
reader imports it from there as `prove` itself does.
"""

from stayfixed.prove.counts import Counts
from stayfixed.prove.evidence import record_gate
from stayfixed.prove.run import Receipt, Verdict, prove

__all__ = [
    "Counts",
    "Receipt",
    "Verdict",
    "prove",
    "record_gate",
]
