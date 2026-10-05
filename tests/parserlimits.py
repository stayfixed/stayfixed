"""Valid JSON past a limit of Python's parser, spelled once for every test that commits one.

A ledger, a settings file and a manifest are each a file a clone can commit, and each reader of one
caught the decoder's `JSONDecodeError` and not the two errors a valid document can raise. Node's
`JSON.parse` reads both documents below, so a harness may act on a file Python cannot read.
"""

from __future__ import annotations

# Valid JSON nested past what `json.loads` follows: it raises `RecursionError` on every supported
# Python.
NESTED = "[" * 200_000 + "]" * 200_000

# An integer literal longer than the interpreter converts, 4,300 digits by default on every
# supported Python: `json.loads` raises a plain `ValueError` for it, which is neither the
# `JSONDecodeError` nor the `RecursionError` a reader catches.
LONG_NUMBER = "1" * 5_000
