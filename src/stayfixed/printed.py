"""How a name the repository chose may be printed on a line a terminal or a CI runner reads.

A repository chooses its own file names, note names, `memory.groups` entries and TOML keys, and
any of them may hold a line break followed by `::error::…`, which a GitHub Actions runner reads
from a job's output as a workflow command, or an escape sequence, which drives the reader's
terminal. `trust.wrap` marks such text as data for a model and escapes no byte for either of
those readers, so a printed name needs one of the two bounds below on its content. Both answer from
`PATH_VALUE`, the one grammar a path may print in: ASCII letters, digits, `.`, `_` and `-` in
`/`-separated segments. A name inside it prints as itself, so ordinary output is unchanged.

- `printable` withholds a name outside the grammar. It is for a line whose command also carries
  the name in `--json`, and for any line a model reads, where a name that holds spaces could
  carry readable prose.
- `quoted` escapes a name outside the grammar with `repr`. It is for a refusal, which has no
  `--json` behind it, where withholding the name would leave the operator nothing to rename.

A third bound is on a name's length rather than its content: `clipped` prints a name through
`quoted` and, past `CLIPPED_CHARS`, only its start and its length. It is for a refusal naming
something nothing upstream bounds in length, a TOML key, a label or a group.
"""

from __future__ import annotations

import re
from typing import Protocol

# The grammar a `[paths]` value must match before it may be printed anywhere; `contained()`
# decides whether it may be written, and a shape rule cannot bound a charset. It lives here, beside
# the bounds that print by it, rather than with the configuration's other grammars in
# `config.schema`: this module imports nothing from the package, so the configuration layer, which
# prints through `findings`, can import it without the two importing each other.
#
# The segment shape is part of the grammar because the two readers of a path have to agree about
# what a path is. A charset alone admitted `docs//x.md`, `docs/x/` and `./docs`: `contained()`
# read them through `Path(relative).parts`, which drops an empty component, a trailing slash and
# a leading `./` without a word, so `plan()` reported no refusal — while `fsops` splits the raw
# string and refuses all three, so `apply()` raised part-way through a pass that had already put
# earlier artifacts on disk and whose `finally` had already persisted the manifest. The value
# was never writable; only the two spellings of "a path" disagreed about saying so.
#
# So the grammar is written per segment: exactly one `/` between segments, no segment empty, and
# the lookahead per segment because the charset alone cannot say it. `.` and `..` are spelled
# entirely out of the charset the segments already use, so a segment rule without the lookahead
# admits `./docs`, `docs/../x` and `..` itself — measured, on the charset-plus-segments form this
# started from. `.hidden` and `..foo` are ordinary names and stay admitted: the lookahead refuses
# a segment that is one or two dots *and nothing else*. What is left is exactly the set
# `fsops.checked_components` accepts, intersected with the charset, and `contained()` asks that
# function for the component rule rather than keeping a second copy of it.
PATH_VALUE = re.compile(
    r"^(?!\.\.?(?:/|\Z))[A-Za-z0-9._][A-Za-z0-9._-]*(?:/(?!\.\.?(?:/|\Z))[A-Za-z0-9._-]+)*\Z"
)

# What a name outside `PATH_VALUE` prints as on a line whose command carries it in `--json`.
# Fixed text, and it says where the name itself went.
UNPRINTABLE = "<unprintable name; see --json>"


def printable(name: str, withheld: str = UNPRINTABLE) -> str:
    """`name` itself inside the path grammar, `withheld` outside it. A caller whose output has
    no `--json` to point at passes a `withheld` of its own."""
    return name if PATH_VALUE.match(name) else withheld


def quoted(name: str) -> str:
    """`name` itself inside the path grammar, its `repr` outside it.

    `repr` escapes every line break and control character, so the name arrives whole, cannot
    start a line and cannot drive a terminal."""
    return name if PATH_VALUE.match(name) else repr(name)


# How many characters of a name a refusal prints before it clips the rest to a count. A named cap
# (CONTRIBUTING.md#named-caps), and `docs/cli.md` states the number for the refusals that use it
# (`docs trail`'s stale `[states]` keys and its `[[theme]]` label, the memory store's unresolved
# groups, and what `answered` quotes from a subprocess for `overlay create`, `overlay
# publish-template`, `attach` and `setup`), so a change to either is a change to both. `quoted`
# escapes a name and does not bound its length, and a TOML key, a label or a group is bounded in
# length by nothing, so without this a refusal's line is as long as the repository makes one name.
# 120 is well past any name an operator would type, and short enough that the start still says
# which one it is.
CLIPPED_CHARS = 120


def clipped(name: str) -> str:
    """`quoted(name)`, or past `CLIPPED_CHARS` the first characters through `quoted` and the
    length: `…(N chars)`. For a refusal, where the name is the only channel and must still be
    identifiable, and where no bound on its length exists upstream."""
    if len(name) <= CLIPPED_CHARS:
        return quoted(name)
    return f"{quoted(name[:CLIPPED_CHARS])}…({len(name)} chars)"


class _Answered(Protocol):
    """What `runner.Completed` carries, named here so this leaf module imports no runner."""

    @property
    def code(self) -> int: ...
    @property
    def stdout(self) -> str: ...
    @property
    def stderr(self) -> str: ...


def answered(done: _Answered) -> str:
    """What a subprocess said about itself, its stderr before its stdout before its exit code,
    through `clipped`: what `gh`, `git`, `pre-commit` or a harness's plugin command prints is not
    text this project wrote, and a line break followed by `::error::` in it is a workflow command
    in a CI log, and an escape sequence drives a terminal. One helper, so a caller that quotes one
    cannot leave the clip out."""
    return clipped(done.stderr.strip() or done.stdout.strip() or f"exit {done.code}")
