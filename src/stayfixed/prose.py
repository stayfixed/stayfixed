"""The one grammar for "a backticked path in hand-written prose".

The plan lint and the memory reference guard read different documents for different reasons
and ask them the same question: which backticked spans claim that a path exists. Two copies of
that question drift, and they drift silently: let one copy accept `.ts`/`.tsx` and the other
not, and in a repository whose front end is TypeScript a plan naming a deleted `.ts` module gets
no reference check at all, while the module that came second goes on saying in its docstring
that it shares a grammar it does not. One copy, here, is what stops that.

Four rules live here, and each is a decision rather than a default:

* the extension list, because a backticked span is a path claim only when it looks like a
  file this repository stores. The whole span is the path, so a shell command or a URL —
  both of which carry characters this class excludes — cannot match, and a trailing `:12` or
  `::name` is a location within the file rather than part of its name;
* fences are BLANKED, not deleted. Fenced code is fixture text and not prose, and deleting a
  block shifts every line below it upward by the block's height, so every report under a
  fence named a line that was not the line;
* a bare filename is prose. `config.py` is a sentence about a file, not a claim about where
  one is, and reading it as a path makes every such mention unresolvable;
* a claim that lands outside the project root is not settled against the filesystem at all.
  A shared grammar with an unshared resolution rule is the same drift in slower motion:
  `resolves_within` is where that rule is written down.

A leaf module: `docs.plans`, `docs.hygiene`, `memory.graph` and `memory.refs` import it, and
none may import another's area.
"""

from __future__ import annotations

import os.path
import re
from collections.abc import Iterator
from pathlib import Path

REFERENCE = re.compile(r"`([A-Za-z0-9_./-]+\.(?:py|sh|md|json|ya?ml|toml|tsx?))(?::\d+|::[\w.]+)?`")
FENCE = re.compile(r"^[ \t]*(`{3,}|~{3,}).*?^[ \t]*\1[ \t]*$", re.MULTILINE | re.DOTALL)
# Inline code, single-line so a stray backtick cannot swallow the lines after it. Blanked
# AFTER fences (a fence can contain backticks).
CODE_SPAN = re.compile(r"`[^`\n]*`")


def blank_fences(text: str) -> str:
    """``text`` with each fenced block replaced by its own height in blank lines."""

    return FENCE.sub(lambda match: "\n" * match.group(0).count("\n"), text)


def blank_code_spans(text: str, placeholder: str = "\x00") -> str:
    """``text`` with each inline code span replaced by ``placeholder``.

    A placeholder, not a deletion: removing a span leaves its neighbours adjacent, so
    `[[a]] `x` [[a]]` would read as a repeated link. Not for the readers of backticked paths
    (`path_references` reads spans; this erases them) — the memory graph check is the caller.
    """
    return CODE_SPAN.sub(placeholder, text)


def path_references(line: str) -> Iterator[str]:
    """Every backticked span in ``line`` that claims a path; bare filenames are prose."""

    for match in REFERENCE.finditer(line):
        target = match.group(1)
        if "/" in target:
            yield target


def resolves_within(root: Path, target: str, *, base: Path | None = None) -> Path | None:
    """Where a path claim lands, or None when it lands outside ``root``.

    The fourth rule, and the one whose absence was the drift this module exists to prevent: the
    grammar was shared and the RESOLUTION was not. A document writes whatever it likes —
    `/etc/passwd.md` and `../../../../secrets/keys.py` are both path claims by this grammar —
    and `Path(root) / "/etc/passwd.md"` discards `root` entirely, while a `..` walks out of it.
    A reader that then asks the filesystem is answering a question about the developer's disk
    instead of about this repository: a plan naming an absolute path that happens to exist
    locally passes the dead-reference lint and does not exist in CI, and the reader is an
    existence oracle for every path outside the root besides.

    Lexical, with `normpath` and never `resolve()`: `..` is collapsed without asking the
    filesystem anything, so a symlinked documents directory is not read as an escape and no
    probe is made before the decision is taken.

    ``base`` is where a RELATIVE claim is read from — a markdown link is relative to its own
    document's directory — and defaults to ``root``. Containment is judged against ``root``
    either way, so a link out of `docs/` into `src/` stays inside the project and resolves.

    `memory.refs._resolves` deliberately keeps its own rule and does not call this: a note
    quoting another host's deployment layout is prose, so an absolute path outside this
    checkout is DROPPED there rather than reported, which is a different answer from None
    meaning "do not touch the filesystem". One reader needing a different rule is why this one
    is written down rather than assumed.
    """
    landed = Path(os.path.normpath(os.path.join(str(base if base is not None else root), target)))
    return landed if landed.is_relative_to(os.path.normpath(str(root))) else None
