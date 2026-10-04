"""The ledger engine: for each register it is handed, one file per entry under the register's
directory, one generated index, and the scan that keeps every identifier in the tree pointing at
an entry. The bug ledger is the register `bug_register` builds from `[paths] bugs`,
`[paths] bug_index` and `[ledger]`.

The import surface is `stayfixed.ledger.api`, not this file — see `tests/ledger/test_surface.py`
for why the package `__init__` stays empty.
"""
