"""Valid JSON past a limit of Python's parser, spelled once for every test that commits one.

A ledger, a settings file and a manifest are each a file a clone can commit, and each reader of one
caught the decoder's `JSONDecodeError` and not the two errors a valid document can raise. Node's
`JSON.parse` reads both documents below, so a harness may act on a file Python cannot read.
"""

from __future__ import annotations

import json
from typing import Any

# Valid JSON nested past what `json.loads` follows: it raises `RecursionError` on every supported
# Python.
NESTED = "[" * 200_000 + "]" * 200_000

# An integer literal longer than the interpreter converts, 4,300 digits by default on every
# supported Python: `json.loads` raises a plain `ValueError` for it, which is neither the
# `JSONDecodeError` nor the `RecursionError` a reader catches.
LONG_NUMBER = "1" * 5_000

# Valid JSON nested where Python 3.14's parser still follows (about 57,800 levels, measured on
# 3.14.7) and its encoder no longer does: `json.dumps` overflowed at 50,000 levels there, and `str`
# at 40,000. On 3.11 to 3.13 the parser itself stops long before (992, 9,997 and 9,998 levels), so a
# reader meets it as `NESTED` on every supported Python only if it bounds the depth it follows.
PAST_ENCODING = "[" * 53_000 + "]" * 53_000

_ENCODE = json.dumps


def overflowing_indent(value: object, *args: Any, indent: int | None = None, **kwargs: Any) -> str:
    """An encoder that overflows wherever it is asked to indent, as Python 3.12's does on a deep
    document, and encodes as usual otherwise. Patched over `json.dumps` as well as the helper's
    own encoder, so an encode of the settings document that bypassed the helper would escape."""
    if indent is not None:
        raise RecursionError
    return _ENCODE(value, *args, **kwargs)


# Valid JSON nested five levels deep, one past the depth bound once a test lowers
# `jsonobject.DEPTH_CAP` to 4: every parser follows it, so only the shared reader's bound refuses
# it, and a reader that bypasses that reader reads it.
DEEPER_THAN_FOUR = '{"a": [[[[]]]]}'
