"""The `docs` and `trail` gates judge tracked files: which files they read here that CI cannot.

CI checks out what git tracks and nothing else. A built-in gate that reads files by path says which
on its record (`Gate.reads`): the `docs` gate reads `[paths] agents_md` and every file its links
name, and the `trail` gate reads `[paths] roadmap` and the `trail.toml` beside it. This module
knows no gate by name, so a built-in gate that comes to read files by path falls under the check by
declaring them. A file that is on disk here and that git does not track, an ignored one included,
is a file those gates read here and CI never sees, and so is one read through a tracked symlink
whose target is untracked or outside the repository, since git tracks the link alone and the
checkout leaves it dangling: in CI it is absent, and the gate's own finding for an absent file
(`missing-document`, `missing-link`, `roadmap-missing`, or a listing rebuilt without the states)
fails every pull request. So a verdict taken here would not be CI's verdict, and `stayfixed assess`
reports such a gate as unable to judge the tree as CI will, and `stayfixed adopt promote` never
enforces it. `stayfixed gate` asks nothing of this: it runs where CI checked out, and there the file
is simply absent.

**What is not asked.** A file a gate reads only when it is there, whose absence adds no finding,
such as the roadmap the `docs` gate reads for its prose budget, is not among its reads: one CI
cannot see can only make a verdict here stricter than CI's, never laxer. The design and plan
documents the `trail` listing names are already filtered to tracked ones by the listing itself.

**Outside a git work tree nothing is asked.** There is no index to ask and no checkout for CI to
take, so both commands judge the files as they are, as `stayfixed docs trail` lists every
document there. Inside one, a git that gives no answer is not "tracked": the gate is reported as
unable to judge, with a reason saying git did not answer, and is not promoted.

**What prints.** The reason is fixed text, and names `[paths]` keys rather than the files; the
files go to an item's `where`, through `printable`, since a link target is any name the document
wrote.
"""

from __future__ import annotations

import os
from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING

from stayfixed import fsops
from stayfixed.assess.gates import Gate, GateResult, configured
from stayfixed.assess.model import Item, item
from stayfixed.errors import StayfixedError
from stayfixed.findings import Severity
from stayfixed.gitenv import QUERY_TIMEOUT_SECONDS, git_run, in_work_tree
from stayfixed.printed import printable

if TYPE_CHECKING:
    from stayfixed.config.schema import Config

UNTRACKED = "untracked"
CASE_DIFFERS = "case-differs"
# The most links followed from one path the gates read. A named cap (CONTRIBUTING.md#named-caps),
# bounding a walk over links the repository wrote; no shipped file sets it. 40 is Linux's own
# limit on the links one lookup follows (macOS stops at 32), so a chain the filesystem follows is
# never cut short here, and one it would not follow is not read by the gates at all.
LINK_HOPS = 40
UNASKED = "could-not-look"
# A gate's `reason` when a file it reads is not tracked, or git would not say. Fixed text: the
# files are in the item beside it.
UNSEEN_REASON = (
    "could not judge this tree as CI will: it reads a file CI's checkout will not have, one "
    "git does not track under that name or a symlink that leads out of the repository; "
    "`stayfixed assess --json` names it"
)
UNASKED_REASON = (
    "could not judge this tree as CI will: git gave no answer to whether it tracks the files "
    "this gate reads; `stayfixed assess --json` names them"
)
# Commit, not "add": CI checks out commits, and a file an ignore rule matches is one plain
# `git add` refuses.
REMEDY = (
    "commit each file named, since CI checks out only what git tracks (one an ignore rule "
    "matches needs the rule removed, or `git add -f`), and point a symlink named here at a "
    "tracked file in the repository; to keep them out of git, take {gate} out of [gates] "
    "builtin instead"
)
# A name that differs from the tracked one only in case is the same file on a filesystem that
# folds case, such as macOS's default, and no file at all in a Linux checkout: the file is
# committed, so "commit it" would be advice nobody can take.
CASE_REMEDY = (
    "git tracks each file named under a name that differs from it only in case, which this "
    "filesystem ignores and CI's checkout does not: spell the link, or the [paths] value, as "
    "`git ls-files` lists the file, or rename the file in git with `git mv`"
)
UNASKED_REMEDY = (
    "run `git ls-files` here to see why git gives no answer; a git that timed out may answer "
    "once the repository is idle"
)


@dataclass(frozen=True)
class Unseen:
    """A gate that reads files CI cannot be shown to see: the files, whether git answered the
    question at all (when it did not, `files` are every file the gate reads), and the files git
    tracks only under a name that differs in case."""

    gate: str
    files: tuple[str, ...]  # project-relative, as found on disk
    git_answered: bool
    case_differs: tuple[str, ...] = ()  # project-relative, as read; none of them in `files`


def _reads(root: Path, config: Config, gate: Gate) -> list[Path]:
    """The files `gate` reads by path that are there now, as its record declares them."""
    wanted = gate.reads(root, config) if gate.reads is not None else []
    return [path for path in wanted if fsops.exists(path)]


@dataclass(frozen=True)
class _Listing:
    """What git tracks in the work tree the project is in: its top, the project's place below it
    (`""` at the top, else `"proj/"`), every tracked path and every directory above one, each
    relative to the top, each of those by its case-folded spelling, and every tracked path that
    differs in the work tree from the index."""

    top: Path
    prefix: str
    names: frozenset[str]
    dirs: frozenset[str]
    folded: Mapping[str, str]
    changed: frozenset[str]


def _tracked(root: Path) -> _Listing | None:
    """Every path git tracks in the work tree around `root`, the whole of it and not only under
    `root`, since a symlink in a project below the top may name a tracked file beside it, and
    which of them differ on disk, since a link is followed as it is on disk and a checkout writes
    it as git has it; `None` when git gives no answer to any of the three questions."""
    code, out = git_run(
        root, "rev-parse", "--show-toplevel", "--show-prefix", timeout=QUERY_TIMEOUT_SECONDS
    )
    lines = out.split("\n")
    if code != 0 or len(lines) < 2 or not lines[0]:
        return None
    top = Path(lines[0])
    code, out = git_run(top, "ls-files", "-z", "--cached", timeout=QUERY_TIMEOUT_SECONDS)
    if code != 0:
        return None
    names = frozenset(name for name in out.split("\0") if name)
    # Built once, so the walk asks each step in constant time: it asks every directory on every
    # path it walks, and the listing is the whole repository's.
    dirs: set[str] = set()
    for name in names:
        cut = name.rfind("/")
        while cut > 0 and name[:cut] not in dirs:
            dirs.add(name[:cut])
            cut = name.rfind("/", 0, cut)
    folded = {path.casefold(): path for path in (*names, *dirs)}
    code, out = git_run(top, "ls-files", "-z", "--modified", timeout=QUERY_TIMEOUT_SECONDS)
    if code != 0:
        return None
    changed = frozenset(name for name in out.split("\0") if name)
    return _Listing(top, lines[1], names, frozenset(dirs), folded, changed)


def _is_tracked(relative: str, listing: _Listing) -> bool:
    """A file is tracked when git lists it; a directory, when git lists a file under it."""
    return relative in listing.names or relative in listing.dirs


def _same_file(one: Path, other: Path) -> bool:
    """Whether the two names reach one file here; a name that reaches none reaches no other."""
    try:
        return os.path.samefile(one, other)
    except OSError:
        return False


def _case_differs(named: str, listing: _Listing) -> bool:
    """Whether git tracks `named` only under a spelling that differs in case, and here that
    spelling is the same file: a filesystem that folds case read one for the other. Where the
    two are different files, the one read is simply untracked."""
    here = listing.prefix + named
    spelled = listing.folded.get(here.casefold())
    if spelled is None or spelled == here:
        return False
    return _same_file(listing.top / here, listing.top / spelled)


def _parts(path: str) -> list[str]:
    """`path`'s components, as the filesystem reads them: an empty one or `.` names nothing."""
    return [part for part in path.split("/") if part not in ("", os.curdir)]


def _not_checked_out(relative: str, listing: _Listing) -> str | None:
    """What of `relative` a checkout of the tracked tree would not have, named inside the project,
    or `None` when it would have all of it.

    git tracks a symlink as the link alone, and a checkout writes the link whether or not what it
    names is there, so a tracked link says nothing about what is read through it. The path is
    walked as the filesystem walks it, one component at a time from the work tree's top: `..`
    steps back out of the directory reached so far, which is where a symlinked directory led and
    not where the link sits, and every other component must be tracked, and is followed when it
    is a symlink, a directory's included, its target read from the link's own directory. The
    first component that is untracked ends the walk, and so does a link that differs on disk
    from the one git has, which a checkout writes instead, a link whose target is absolute, a
    `..` above the top, or a link past `LINK_HOPS`, since no checkout of the repository has what
    any of them names. The name is always inside the project: each link followed renames the
    step to the path it leads to, when that climbs nowhere and stays inside the project, and
    otherwise the last such name stands; a link that leads out of the repository is named itself,
    or, when it is outside the project, the last link inside it that led there.
    """
    prefix = listing.prefix
    todo = deque(_parts(prefix + relative))
    done: list[str] = []
    named, leads, hops = relative, relative, 0
    while todo:
        part = todo.popleft()
        if part == os.pardir:
            if not done:
                return leads  # a climb above the work tree's top: no checkout has it
            done.pop()
            continue
        done.append(part)
        here = "/".join(done)
        if not _is_tracked(here, listing):
            return named  # the first untracked step
        link = listing.top / here
        if not fsops.is_symlink(link):
            continue
        if here in listing.changed:
            return named  # a link changed on disk: a checkout writes the one git has
        if here.startswith(prefix):
            leads = here[len(prefix) :]
        hops += 1
        if hops > LINK_HOPS:
            return named  # a chain longer than the walk follows
        target = os.readlink(link)
        if os.path.isabs(target):
            return leads  # a target that is absolute: no other checkout has it
        done.pop()
        todo.extendleft(reversed(_parts(target)))
        step = "/".join([*done, *todo])
        if os.pardir not in todo and step.startswith(prefix):
            named = step[len(prefix) :]
    return None


def unseen(root: Path, config: Config, gates: tuple[Gate, ...]) -> tuple[Unseen, ...]:
    """Each of `gates` that reads a file here which git does not track, or of which git would not
    say; nothing outside a git work tree."""
    if not in_work_tree(root):
        return ()
    reads: dict[str, list[str]] = {}
    for gate in gates:
        try:
            found = _reads(root, config, gate)
        except StayfixedError:
            # A path the gate refuses to read, which it answered without reaching: the trail
            # gate stops at a missing roadmap, its own finding, before it asks for `trail.toml`.
            # That result already fails, so nothing here could make it pass.
            continue
        if found:
            reads[gate.name] = [Path(os.path.relpath(path, root)).as_posix() for path in found]
    if not reads:
        return ()
    tracked = _tracked(root)
    result: list[Unseen] = []
    for name, files in reads.items():
        if tracked is None:
            result.append(Unseen(name, tuple(files), git_answered=False))
            continue
        missing = tuple(
            dict.fromkeys(n for f in files if (n := _not_checked_out(f, tracked)) is not None)
        )
        if missing:
            cased = tuple(n for n in missing if _case_differs(n, tracked))
            untracked = tuple(n for n in missing if n not in cased)
            result.append(Unseen(name, untracked, git_answered=True, case_differs=cased))
    return tuple(result)


def as_ci_sees(
    root: Path, config: Config, results: tuple[GateResult, ...]
) -> tuple[tuple[GateResult, ...], tuple[Unseen, ...]]:
    """`results` with each gate that reads a file CI cannot see turned into one that could not
    judge the tree, its findings kept; and those gates, with their files."""
    gates = configured(config)
    found = unseen(root, config, tuple(gates[r.name] for r in results if r.answered))
    by_gate = {u.gate: u for u in found}
    judged = tuple(
        replace(
            r,
            answered=False,
            reason=UNSEEN_REASON if by_gate[r.name].git_answered else UNASKED_REASON,
        )
        if r.name in by_gate
        else r
        for r in results
    )
    return judged, found


def unseen_items(found: tuple[Unseen, ...], withheld: str) -> list[Item]:
    """The inventory items for each gate: the untracked files, and apart from them the files git
    tracks under another case, or every file when git gave no answer; each a label inside the
    path grammar or `withheld`."""
    items: list[Item] = []
    for u in found:
        rows = (
            [
                (UNTRACKED, REMEDY.format(gate=u.gate), u.files),
                (CASE_DIFFERS, CASE_REMEDY, u.case_differs),
            ]
            if u.git_answered
            else [(UNASKED, UNASKED_REMEDY, u.files)]
        )
        items += [
            item(
                u.gate,
                rule,
                None,
                Severity.WARNING,
                remedy,
                [printable(f, withheld) for f in files],
            )
            for rule, remedy, files in rows
            if files
        ]
    return items
