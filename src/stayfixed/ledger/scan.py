"""One traversal for the three readers of ledger identifiers.

`code_mentions` reports a dangling identifier, `entry_citations` reports a citation of an entry
file that is not there, and `renumber`'s sweep rewrites both. They have to agree on what a
scannable file is, so every exclusion lives here: each time one reader held an exclusion of its
own, the pair disagreed and something was lost (a fixture the scan skipped as binary was an
unswept file to the sweep; a fixture-holding test file the scan skipped was rewritten by the
sweep while `check` reported OK over the red suite it had just created).

Git enumerates the candidates wherever it can — the question both readers ask is "what is in
the commit under review", and a walk answers a different one — and the walk is the fallback for
a root that is not the top of a checkout. Symlinks are skipped whole. A file is read once, here,
and handed to every reader as text: the readers never open a file themselves.

Where to look is the project's (`config`: the code roots and the `[paths]` values); what to look
for is the register's — its directory, its index and its identifiers.
"""

from __future__ import annotations

import os
import posixpath
import re
import stat
from collections import defaultdict
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING

from stayfixed.config.paths import PathEscape, contained
from stayfixed.fsops import read_regular_bytes, said
from stayfixed.gitenv import QUERY_TIMEOUT_SECONDS, git_run
from stayfixed.guards.api import contained_roots

if TYPE_CHECKING:
    from stayfixed.config.schema import Config
    from stayfixed.ledger.register import Register

# The repository's own top-level files, which are under no directory and so under no root:
# `pyproject.toml` and `.gitignore` each carried a live identifier once, invisible to the scan
# and unswept by `renumber`, which reported success having rewritten neither.
TOP_LEVEL = "."
# A file whose head carries this is a holder of sample identifiers — a test module's fixtures — and
# is excluded from the mention scan and from the sweep alike. A real reference inside such a file is
# invisible to the scan; that is the accepted price.
FIXTURE_MARKER = "stayfixed:ledger:fixtures"
# How far into a file the marker is looked for: a module docstring or a header comment. A named cap
# (CONTRIBUTING.md#named-caps), and no shipped file changes with it: a marker anywhere else is prose
# about the marker.
FIXTURE_MARKER_WINDOW = 2048
# Directory names neither reader walks into: vendored or generated trees that hold no reference
# anyone filed. Matched against a name found below a scanned root, never against the checkout's
# own path.
EXCLUDED_DIRNAMES = frozenset({"node_modules", ".git", ".venv", "dist", "build", "__pycache__"})
# Suffixes no identifier can be read out of or written back into.
BINARY_SUFFIXES = frozenset(
    {
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".pdf",
        ".ico",
        ".ogg",
        ".mp3",
        ".wav",
        ".pyc",
        ".zip",
        ".woff",
        ".woff2",
    }
)


@dataclass(frozen=True)
class Scanned:
    path: Path
    relative: PurePosixPath
    # `None` when the file is not text (undecodable, `error` None) or could not be read
    # (`error` names why). The sweep reports the second and skips the first, exactly as the
    # scan does — from one traversal, so the two cannot disagree.
    text: str | None
    error: str | None


def mention_roots(root: Path, config: Config) -> tuple[str, ...]:
    names = [TOP_LEVEL]
    names.extend(
        directory.relative_to(root).as_posix() for directory in contained_roots(root, config)
    )
    return tuple(names)


def document_roots(root: Path, config: Config) -> tuple[str, ...]:
    """The first path component of every `[paths]` value that has more than one: `docs` for
    the defaults. Where documents live, and where a citation of an entry file may be written."""
    found: list[str] = []
    resolved_root = root.resolve()
    for value in config.paths.as_dict().values():
        parts = PurePosixPath(value).parts
        if len(parts) < 2 or parts[0] in found:
            continue
        try:
            candidate = contained(root, parts[0], resolved_root=resolved_root)
        except PathEscape:
            continue
        if candidate.is_dir():
            found.append(parts[0])
    return tuple(found)


def citation_roots(root: Path, config: Config) -> tuple[str, ...]:
    mention = mention_roots(root, config)
    return mention + tuple(name for name in document_roots(root, config) if name not in mention)


def _pathspec(name: str) -> str:
    """A scan root as git should read it.

    `TOP_LEVEL` is the one that is not a directory. `:(glob)*` is how git spells "files here and
    not below": under glob magic `*` stops at a `/`, where a bare `*` would match the whole tree
    and make every other root redundant.
    """
    return ":(glob)*" if name == TOP_LEVEL else name


def _committed_files(root: Path, names: tuple[str, ...]) -> list[Path] | None:
    """The files git would put in a commit under `names`, or `None` where git cannot answer.

    `--cached --others --exclude-standard` is tracked files plus the untracked ones that are
    not ignored: what a reference can legitimately live in, which is neither "everything on
    disk" (a build artifact is not a claim about the ledger) nor "tracked only" (a reference in
    a file the operator is about to commit still has to be swept).

    `None` rather than an empty list when `root` is not the top of a checkout, so the caller
    falls back to walking instead of silently scanning nothing — a guard that reports OK
    because it looked at no files is the failure mode this whole module exists to prevent. The
    listing itself answers the same way when git gave none — it could not be run, or ran past
    its bound: an empty answer for a failure is an empty listing, which would scan no file.
    """
    # The line ending alone, never `strip()`: a root that ends in a space is still that root.
    code, out = git_run(root, "rev-parse", "--show-toplevel", timeout=QUERY_TIMEOUT_SECONDS)
    toplevel = out.removesuffix("\n")
    if code != 0 or not toplevel or Path(toplevel).resolve() != root.resolve():
        return None
    code, listed = git_run(
        root,
        "ls-files",
        "-z",
        "--cached",
        "--others",
        "--exclude-standard",
        "--",
        *(_pathspec(n) for n in names),
        timeout=QUERY_TIMEOUT_SECONDS,
    )
    if code != 0:
        return None
    return [root / name for name in listed.split("\0") if name]


def _walked_files(root: Path, names: tuple[str, ...]) -> list[Path]:
    """Every file under `names` on disk, for a `root` git cannot speak for.

    Excluded directories are pruned from the walk rather than filtered out of its results,
    which is the difference between not reading a vendored tree and not visiting it: filtering
    still costs a stat per file, and a dev checkout's is tens of thousands of them.
    """
    candidates: list[Path] = []
    for name in names:
        if name == TOP_LEVEL:
            candidates.extend(child for child in root.iterdir() if not child.is_dir())
            continue
        base = root / name
        if not base.is_dir():
            continue
        for parent, dirnames, filenames in os.walk(base):
            here = Path(parent)
            # In place, because that list is what `os.walk` descends into next.
            dirnames[:] = [
                d for d in dirnames if d not in EXCLUDED_DIRNAMES and not (here / d).is_symlink()
            ]
            candidates.extend(here / filename for filename in filenames)
    return candidates


def is_fixture_holder(head: bytes) -> bool:
    return FIXTURE_MARKER.encode("utf-8") in head


def scannable(root: Path, names: tuple[str, ...]) -> Iterator[Scanned]:
    """Every file under `names` a reference could live in, sorted for determinism.

    Sorted keeps the first reported location of a dangling identifier stable when several
    files mention it. One `lstat` answers what a pair of `is_symlink()`/`is_file()` calls
    asked, and answers it the same way: a symlink is `S_ISLNK`, never `S_ISREG`, so it is
    skipped whole — a memory routing table shared with another checkout is exactly that, and
    following it would put a sweep's rewrite outside the tree the operator is looking at and
    outside the commit they review.
    """
    candidates = _committed_files(root, names)
    if candidates is None:
        candidates = _walked_files(root, names)
    for path in sorted(candidates):
        if path.suffix in BINARY_SUFFIXES:
            continue
        relative = PurePosixPath(path.relative_to(root).as_posix())
        try:
            if not stat.S_ISREG(path.lstat().st_mode):
                continue
            # To the read cap, by the bounded reader every reader of a committed file uses: a file
            # past it is one this scan could not read, never one read to its end.
            raw = read_regular_bytes(path)
        except OSError as error:
            yield Scanned(path, relative, None, said(error))
            continue
        if is_fixture_holder(raw[:FIXTURE_MARKER_WINDOW]):
            continue
        try:
            text: str | None = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = None
        yield Scanned(path, relative, text, None)


def citation_pattern(register: Register) -> re.Pattern[str]:
    """Loose on purpose: any `…/<ledger dirname>/<PREFIX>-nnn.md`. The decision is made by
    resolving the match (`_cited_entry`), not by the pattern.

    A citation names an entry's FILE, and a tree writes that path three ways, not two: rooted
    at the repository from code, `../<dirname>/` from a sibling document, and a bare
    `<dirname>/` from a document sitting directly in the documents directory. Widening the
    pattern instead would report a plan or design document that writes a bare path inside a
    quoted example of this tool's own output; resolved against its own directory that lands
    somewhere that is not an entry path, and it drops out for the right reason rather than by
    an exclusion.
    """
    last = PurePosixPath(register.directory).name
    prefix = register.ids.prefix
    return re.compile(
        rf"(?<![\w./-])((?:\.{{1,2}}/)*(?:[\w.-]+/)*{re.escape(last)}/({re.escape(prefix)}-\d+)\.md)"
    )


def _cited_entry(
    citing: PurePosixPath, matched: str, identifier: str, directory: PurePosixPath
) -> bool:
    """Does `matched`, as written in `citing`, name an entry file under the ledger directory?

    Resolved two ways, because both are how a reader would follow it: relative to the citing
    file's own directory, and relative to the repository root. Either landing on the entry path
    makes it a citation; neither landing there means the text is not a link to an entry at all.
    """
    target = f"{directory}/{identifier}.md"
    relative = posixpath.normpath(f"{citing.parent}/{matched}")
    rooted = posixpath.normpath(matched)
    return target in (relative, rooted)


def _under(path: PurePosixPath, directory: PurePosixPath) -> bool:
    return path.parts[: len(directory.parts)] == directory.parts


def entry_citations(
    root: Path, config: Config, register: Register
) -> dict[str, list[tuple[PurePosixPath, int]]]:
    """Every citation of an entry's file, mapped to the (file, line) locations citing it.

    Two kinds of file are skipped, both because their links are not independent claims:

    * the entries themselves — a link between siblings is navigation, and `related:` in the
      frontmatter is where a sibling claims the target is filed, checked against parsed
      entries;
    * the generated index — every one of its rows is a projection of an entry file, so a row
      pointing at a file that is gone means the index is stale, which `register_gate` already
      reports with the command that repairs it. Reported here as well it would name a link in
      a file whose fix is never a hand edit.
    """
    directory = PurePosixPath(register.directory)
    index = PurePosixPath(register.index)
    pattern = citation_pattern(register)
    found: defaultdict[str, list[tuple[PurePosixPath, int]]] = defaultdict(list)
    for item in scannable(root, citation_roots(root, config)):
        if item.text is None or item.relative == index or _under(item.relative, directory):
            continue
        # One substring test decides the whole file: the pattern cannot match without the
        # ledger directory's name, and few files carry one.
        if f"{directory.name}/" not in item.text:
            continue
        for match in pattern.finditer(item.text):
            if not _cited_entry(item.relative, match.group(1), match.group(2), directory):
                continue
            found[match.group(2)].append(
                (item.relative, item.text.count("\n", 0, match.start()) + 1)
            )
    return found


def code_mentions(
    root: Path, config: Config, register: Register
) -> dict[str, list[tuple[PurePosixPath, int]]]:
    """Every identifier mentioned under the code roots, mapped to the (file, line) locations
    where it appears. Sorted traversal keeps the first location deterministic when the same
    dangling identifier is mentioned in more than one place.
    """
    ids = register.ids
    needle = f"{ids.prefix}-"
    found: defaultdict[str, list[tuple[PurePosixPath, int]]] = defaultdict(list)
    for item in scannable(root, mention_roots(root, config)):
        # One substring test decides the whole file, so the per-line regex does not run across
        # the whole repository to find the handful of files that carry one.
        if item.text is None or needle not in item.text:
            continue
        for number, line in enumerate(item.text.splitlines(), start=1):
            for identifier in set(ids.mention.findall(line)):
                found[identifier].append((item.relative, number))
    return found
