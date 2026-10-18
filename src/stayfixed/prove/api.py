"""The import surface: everything a consumer may import from this area.

A module and not the package's `__init__`, for the reason every area's surface is one: area
discovery imports a package before the submodule it wants, and the package stays empty of imports.

- `prove`, `Receipt`, `Verdict` and `Counts`: a command that runs a test command and judges it the
  way `stayfixed prove` does takes the receipt and its verdict from here, and the counts it
  carries.
- `shipped_adapters`: a reader of which runners this stayfixed can count, through the same
  discovery `prove` uses; it lives beside the red-run hints' in `stayfixed.profiles.adapters`,
  and is published here for the readers of `prove`.
- `record_gate`: `stayfixed gate`, which keeps one evidence record a run beside `prove`'s, in the
  same directory under the same key.

The protocol an adapter implements is not here: it is `stayfixed.profiles.runners`, the leaf both
the adapters and this area import.
"""

from stayfixed.profiles.adapters import shipped_adapters
from stayfixed.prove.counts import Counts
from stayfixed.prove.evidence import record_gate
from stayfixed.prove.run import Receipt, Verdict, prove

__all__ = [
    "Counts",
    "Receipt",
    "Verdict",
    "prove",
    "record_gate",
    "shipped_adapters",
]
