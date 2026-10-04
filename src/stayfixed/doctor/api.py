"""The doctor area's import surface: everything another area may import from it.

The command module in this area is its first consumer. An area that needs something absent from
this list grows it deliberately, in a commit that says which area and why — it does not import
a private module of this area.

Every name below is here for a reason written beside it, because a surface that survives a trim
with no explanation is what made the trim necessary:

- `run_checks` is the report, and `Check` is the row it is made of — a return type absent from
  this list is a value a consumer can hold and cannot declare, which is the one thing a surface
  exists to prevent. `tests/test_surfaces.py` derives that rule rather than restating it.
- `OK`, `WARN`, `RED`, `SKIP` and the `STATUSES` they belong to are `Check.status`'s closed
  vocabulary, and the set is the export rather than the members that have a caller today, for
  the reason `attach/api.py` gives about `Binding.state`: half a closed vocabulary cannot be
  read by the consumer that gets a value from it. `tests/test_install_path.py` branches on
  `RED` and `SKIP` through this surface already.

- `Row`, `Context`, `Claims` and `Contribution` are what an area's own `doctor.py` speaks: its
  `register()` returns a `Contribution` of `(name, check)` pairs, each check takes the `Context`
  and answers a `Row`, and `Claims` is what the area put into settings files. They are defined in
  `doctor/model.py`, which imports nothing of any area, and published here because an area's
  `doctor.py` is a consumer like any other.
- `Status` is the type `Row.status` declares, for a check that decides its status before it
  builds its row: `attach`'s `attached` row and `overlay`'s `overlay-requires` do, and an
  annotation they could not import would be a type they could hold and not declare.

`plugin_root` is not here: nothing outside this area imports it, and the one test that reads it
takes it from `stayfixed.doctor.checks`, its own area's module. Nor is `SETTINGS_FILES`, the three
settings files `_hook_entries` walks: it is the walk's own input, not the report or its row, and
`checks.py` and this area's tests read it from `stayfixed.doctor.checks`. `stayfixed assess` needs
nothing from this list.
"""

from stayfixed.doctor.checks import run_checks
from stayfixed.doctor.model import (
    OK,
    RED,
    SKIP,
    STATUSES,
    WARN,
    Check,
    Claims,
    Context,
    Contribution,
    Row,
    Status,
)

__all__ = [
    "OK",
    "RED",
    "SKIP",
    "STATUSES",
    "WARN",
    "Check",
    "Claims",
    "Context",
    "Contribution",
    "Row",
    "Status",
    "run_checks",
]
