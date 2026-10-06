"""The one grammar for "a backticked path in hand-written prose".

The plan lint and the memory reference guard read different documents for different reasons
and ask them the same question: which backticked spans claim that a path exists. Two copies of
that question drift, and they drift silently: let one copy accept `.ts`/`.tsx` and the other
not, and in a repository whose front end is TypeScript a plan naming a deleted `.ts` module gets
no reference check at all, while the module that came second goes on saying in its docstring
that it shares a grammar it does not. One copy, here, is what stops that. A closed list of
extensions is the same drift between this grammar and every stack the list leaves out, so there
is none: a `.rs`, a `.go` or a `.java` file is claimed as a `.py` one is.

Four rules live here, and each is a decision rather than a default:

* the shape of a file name, because a backticked span is a path claim only when it looks like
  a file: a name ending in an extension that starts with a letter (`lib.rs`, `a.d.ts`, the
  dotfile `.env`), so a version such as `0.1.9` is not one. The whole span is the path, so a
  shell command or a URL — both of which carry characters this class excludes — cannot match,
  and a trailing `:12`, `:12:4` or `::symbol::path` is a location within the file rather than
  part of its name, in whichever stack's notation;
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

# The path, ending in an extension that starts with a letter; then, outside the group, a place
# in the file: a line and a column, or a symbol path of any depth. The trade of an open extension:
# a backticked `owner/lib.js` repository name or a dotted branch (`release/v1.x`) reads as one.
REFERENCE = re.compile(
    r"`([A-Za-z0-9_./-]+\.[A-Za-z][A-Za-z0-9]*)"
    r"(?::\d+(?::\d+)?|(?:::[\w.]+)+)?`"
)
FENCE = re.compile(r"^[ \t]*(`{3,}|~{3,}).*?^[ \t]*\1[ \t]*$", re.MULTILINE | re.DOTALL)
# Inline code, single-line so a stray backtick cannot swallow the lines after it. Blanked
# AFTER fences (a fence can contain backticks).
CODE_SPAN = re.compile(r"`[^`\n]*`")
# A first path component that ends in a dot and a label of two or more characters, the dot after
# some other character: a host (a Go module path's `example.com/`, a URL with no scheme), not a
# directory of this repository. A leading dot alone is a hidden directory (`.github/`), and a
# one-letter suffix is the `.d` of a directory of fragments (`changelog.d/`, `conf.d/`): both stay
# paths. Measured over this repository's plans, the `.d` exception is what keeps `changelog.d/`
# checked. A dotted top-level directory with a longer suffix (`app.config/`) reads as a host and
# is under-reported, the safe direction for a dead-reference check.
HOST = re.compile(r"[^/]*[^./]\.[A-Za-z][A-Za-z0-9-]+/")


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
    """Every backticked span in ``line`` that claims a path; bare filenames, and a span whose
    first component is a host (`HOST`), are prose."""

    for match in REFERENCE.finditer(line):
        target = match.group(1)
        if "/" in target and not HOST.match(target):
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


def present_within(root: Path, landed: Path) -> bool | None:
    """Whether the path at `landed` names something inside `root`: `True` or `False`, or `None`
    when its real path leaves `root`, so the claim is not settled at all.

    `resolves_within` is lexical, and `exists()` follows symlinks: a committed `docs/l -> /`
    made every claim under it a question about the machine, one bit of existence for any path,
    a present file passing and an absent one reported. So the answer is taken from the claim's
    real path and only inside the root's, as a claim whose spelling leaves the root is not asked
    either; a symlink that stays inside the tree is followed. A name the filesystem cannot take
    (`ENAMETOOLONG` for a 5,000-character path on Python 3.11 to 3.13) names nothing, and is
    `False` rather than an exception. The plan lint, the always-loaded document's link check and
    `memory refs` each ask it.
    """
    try:
        real = Path(os.path.realpath(landed))
        if not real.is_relative_to(os.path.realpath(root)):
            return None
        return real.exists()
    except OSError:
        return False
