"""Read a JSON document as an object, within the reach of this interpreter's parser.

One reader and not one per caller. The settings engine (`scaffold.entries`), `attach`'s reader of
the settings file it merges into and its reader of the ledger it wrote each parse a document a
clone may have committed, and each must answer every way that parse can fail as its own refusal:
a parse failure that escapes as a bare exception passes every caller's catch and ends a command
as an internal error, or turns a `doctor` row into "this check could not run".

Two of those ways are valid JSON rather than malformed JSON, and `json.loads` gives neither a
`JSONDecodeError`: a document nested past what the parser follows raises `RecursionError` on
every supported Python, and an integer literal longer than the interpreter converts (4,300
digits by default) a plain `ValueError`. The caller may refuse those as a kind of their own —
the settings engine does, because a harness whose parser has no such limit reads the document,
and may run the hooks in it — and words them in its own voice where its sentence says more than
what the parser met. The interpreter's own message is never used for either: it tells the reader
to raise a limit.

A leaf module: it imports nothing from `stayfixed`, so the core and a delivery area both reach it
without paying for an area.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

NESTED = "is nested deeper than this reader follows"
LONG_NUMBER = "holds a number longer than this reader converts"
# A named cap: the deepest nesting a document read here may hold, counting the top-level object
# as one. The parser's own reach differs by interpreter — measured, 992 levels on 3.11, 9,997 on
# 3.12, 9,998 on 3.13 and about 57,800 on 3.14 — and on 3.14 it passes what the rest of the
# interpreter follows: `json.dumps` overflowed at 50,000 levels and `str` at 40,000, so a document
# 3.13 refuses was read on 3.14 and then ended `detach` and the settings engine in an internal
# error when they wrote it back. Just above 3.13's reach, so 3.11 to 3.13 refuse nothing they read
# today, and 3.14 refuses what 3.13 refuses, in the same words; four times under where 3.14's `str`
# stops. No shipped file states it: a settings file nests five levels.
DEPTH_CAP = 10_000


def json_object(
    text: str,
    label: str,
    *,
    error: Callable[[str], Exception],
    limit: Callable[[str], Exception] | None = None,
    shape: Callable[[str], Exception] | None = None,
    numbers: Callable[[str], object] = int,
) -> dict[str, Any]:
    """`text` parsed as a JSON object, with each integer literal handed to `numbers`.

    `label` names the document in every sentence: `<label> is not valid JSON: <why>`, `<label>
    is not a JSON object`, and `<label>` before `NESTED` or `LONG_NUMBER` for valid JSON past the
    parser's reach. `error` builds the exception each sentence is raised as. `limit`, when a
    caller gives one, builds the exception for the parser's reach instead, and is handed the
    clause alone — `NESTED` or `LONG_NUMBER` — so the caller says whose document it is. `shape`,
    when a caller gives one, builds the exception for valid JSON that is not an object instead,
    for a caller whose sentence for that document is about what it fails to say rather than
    about how it reads: the overlay probe, whose manifest has to name the tree an overlay.

    Empty text is not an object here: a caller for which an empty file means an empty object
    answers that before it asks, and one for which it is no record at all lets it fail as JSON.
    """
    try:
        raw = json.loads(text, parse_int=numbers)
    except json.JSONDecodeError as exc:
        raise error(f"{label} is not valid JSON: {exc}") from exc
    except RecursionError:
        raise _past(label, NESTED, error, limit) from None
    except ValueError:
        # `JSONDecodeError` is a `ValueError` too, and caught above: what reaches this arm is an
        # integer literal the interpreter will not convert.
        raise _past(label, LONG_NUMBER, error, limit) from None
    if _deeper_than(raw, DEPTH_CAP):
        raise _past(label, NESTED, error, limit)
    if not isinstance(raw, dict):
        raise (error if shape is None else shape)(f"{label} is not a JSON object")
    return raw


def _deeper_than(value: object, cap: int) -> bool:
    """Whether `value` nests containers more than `cap` deep, asked without recursion: the value
    may be one the interpreter cannot recurse through, which is the question."""
    pending = [(value, 1)] if isinstance(value, dict | list) else []
    while pending:
        node, depth = pending.pop()
        children = node.values() if isinstance(node, dict) else node
        if depth > cap:
            return True
        pending.extend((child, depth + 1) for child in children if isinstance(child, dict | list))
    return False


def _past(
    label: str,
    clause: str,
    error: Callable[[str], Exception],
    limit: Callable[[str], Exception] | None,
) -> Exception:
    return error(f"{label} {clause}") if limit is None else limit(clause)
