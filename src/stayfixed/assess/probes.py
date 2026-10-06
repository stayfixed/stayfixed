"""The probes no gate runs: what an inventory reads from files and the git index alone.

Each probe is a small function over the repository, with no network and no tool run. Its id,
principle, severity and remedy live once, on its `Probe`; the function returns only what it saw,
and `run_probes` builds the items, so the attribute a test reads off `PROBES` is the attribute
an item carries.

**A probe that could not look says so.** Every git query runs under `QUERY_TIMEOUT_SECONDS`,
and an exit that is not one of that query's own answers — `git_run`'s `-1` included, which is a
timeout or a git that could not start — is `unread`. So is a file
the probe cannot read or parse, and a path through a symlink. `run_probes` turns `unread` into
one `could-not-look` warning per probe and never into "nothing found": an empty answer read
from a query that did not finish would say no secret is committed.

**No repository byte can end the inventory.** Everything a probe's reading can raise on
repository content is caught where it is read and becomes `unread`.

**Nothing here is printed.** A `where` label is a path the repository chose, a sha, or this
module's own words, and it goes to the machine-readable output only; the summary that reports
these items prints counts and this module's vocabulary.

Two inventory items are not built. Another tool's design-document directories are that tool's
convention, and stayfixed names no other tool's convention. And whether a test exercises what
its name says can be judged only by reading one stack's test files, which the inventory does not
read.
"""

from __future__ import annotations

import os
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING

from stayfixed.assess.model import Item, item
from stayfixed.config.paths import PathEscape, contained
from stayfixed.config.schema import PATH_VALUE
from stayfixed.findings import Severity
from stayfixed.gitenv import QUERY_TIMEOUT_SECONDS, git_run
from stayfixed.guards.api import contained_roots
from stayfixed.scaffold import EntriesError, judged_entries, marker_id

if TYPE_CHECKING:
    from stayfixed.config.schema import Config

COULD_NOT_LOOK = "could-not-look"
PROFILE = "profile"
PROFILE_NOT_SHIPPED = "profile-not-shipped"

COULD_NOT_LOOK_REMEDY = (
    "stayfixed could not read what `where` names; `stayfixed doctor` names a settings file it "
    "cannot read, and a git query that timed out may answer once the repository is idle"
)
# Formatted with `", ".join(profiles.shipped()) or "none"`: stayfixed's own listing.
PROFILE_NOT_SHIPPED_REMEDY = (
    "set [stayfixed] profile to a profile this stayfixed ships ({shipped}), or to an empty string"
)
# Each word spelled so this line is not one of the markers it searches for.
_MARKERS = "T[O]DO|F[I]XME|X[X]X"
_SUBJECT = re.compile(r"^([a-z]+)(\([^)]*\))?!?: ")
_ENV_KEEP = (".example", ".sample", ".template")
_CODEOWNERS = (".github/CODEOWNERS", "CODEOWNERS", "docs/CODEOWNERS")  # GitHub's order
_WORKFLOWS = ".github/workflows"
_UNOWNED = f"{_WORKFLOWS}/"
# A workflow a pull request could add, at a name no project gives one and with no prefix of
# stayfixed's, under both extensions GitHub runs: a line owns every one only by owning the
# workflows directory, or more. `stayfixed*` or `*.yml` owned a single `stayfixed-….yml` probe.
_ANY_WORKFLOWS = tuple(f"{_WORKFLOWS}/any-other-workflow.{ext}" for ext in ("yml", "yaml"))
# What reading a file the repository wrote can raise: a path through a symlink, a file that
# cannot be opened, bytes that are not UTF-8 (a `ValueError`), and a settings document the engine
# refuses, JSON nested past the parser's depth included (`scaffold.ParserLimitError`).
_UNREADABLE = (PathEscape, OSError, ValueError, EntriesError)


@dataclass(frozen=True)
class ProbeContext:
    root: Path
    config: Config
    window: int  # how many commits `commit-types` reads


@dataclass(frozen=True)
class Looked:
    where: tuple[str, ...] = ()  # what was found
    unread: tuple[str, ...] = ()  # what could not be looked at


@dataclass(frozen=True)
class Probe:
    id: str
    principle: int | None
    severity: Severity
    remedy: str
    run: Callable[[ProbeContext], Looked]


def _git(context: ProbeContext, *args: str, answers: tuple[int, ...] = (0,)) -> str | None:
    """Standard output, or `None` when git's exit is not one of `answers` (a timeout is -1)."""
    code, out = git_run(context.root, *args, timeout=QUERY_TIMEOUT_SECONDS)
    return out if code in answers else None


def _head(context: ProbeContext) -> str | None:
    """`HEAD`'s sha, `""` in a repository with no commit, `None` when git cannot answer."""
    out = _git(context, "rev-parse", "--verify", "--quiet", "HEAD", answers=(0, 1))
    return None if out is None else out.strip()


def _names(out: str) -> list[str]:
    """NUL-terminated names, the empty tail dropped."""
    return [name for name in out.split("\0") if name]


def _todo_markers(context: ProbeContext) -> Looked:
    """Files under the code roots that carry a marker as a word. `-z` so a name git would quote
    is never read as the quoted form."""
    roots = [
        path.relative_to(context.root).as_posix()
        for path in contained_roots(context.root, context.config)
    ]
    if not roots:
        return Looked()
    out = _git(
        context, "grep", "-I", "-l", "-z", "-w", "-E", _MARKERS, "--", *roots, answers=(0, 1)
    )
    if out is None:
        return Looked(unread=("git grep",))
    return Looked(tuple(sorted(_names(out))))


def _tracked_env(context: ProbeContext) -> Looked:
    out = _git(context, "ls-files", "-z")
    if out is None:
        return Looked(unread=("git ls-files",))
    return Looked(
        tuple(
            sorted(
                name
                for name in _names(out)
                if (base := PurePosixPath(name).name) == ".env"
                or (base.startswith(".env.") and not base.endswith(_ENV_KEEP))
            )
        )
    )


def _memory_history(context: ProbeContext) -> Looked:
    if context.config.memory.mode == "in-repo":
        return Looked()  # the store is meant to be committed
    # Every ref, not `HEAD`'s history: notes committed on one branch are readable from a clone
    # checked out on an orphan one. With no commit anywhere git answers 0 and prints nothing.
    store = context.config.paths.memory
    out = _git(context, "log", "--all", "--format=%H", "-1", "--", store)
    if out is None:
        return Looked(unread=("git log",))
    return Looked((store,) if out.strip() else ())


def _foreign_hooks(context: ProbeContext) -> Looked:
    """Settings files of the selected harnesses that hold a hook entry without stayfixed's
    marker, read by the walk `doctor`'s `hook-entries` reads them with (`scaffold.judged_entries`,
    lenient for the files a harness was measured running partly malformed): a file one names and
    the other cannot read would be two answers about one file. Every way repository content can
    make reading fail is "could not look", and so is a part of the file the walk skipped that
    could hold a command. One difference stays: this decodes strictly, so a byte that is not
    UTF-8 is "could not look" here where `doctor` reads past it."""
    from stayfixed.harnesses import LENIENT_SETTINGS, select

    harnesses, _ = select(context.config.stayfixed.agents)
    found: list[str] = []
    unread: list[str] = []
    for relative in sorted({s for h in harnesses for s in h.settings}):
        try:
            path = contained(context.root, relative)
            text = path.read_text(encoding="utf-8") if path.is_file() else ""
            # Raises `EntriesError` for a shape `doctor` names as one it could not read.
            entries, partly = judged_entries(text, lenient=relative in LENIENT_SETTINGS)
        except _UNREADABLE:
            unread.append(relative)
            continue
        if partly:
            unread.append(relative)
        if any(marker_id(placed.command) is None for placed in entries):
            found.append(relative)
    return Looked(tuple(found), tuple(unread))


def _foreign_workflows(context: ProbeContext) -> Looked:
    from stayfixed.project.api import CI_WORKFLOW

    own = PurePosixPath(CI_WORKFLOW).name
    try:
        directory = contained(context.root, _WORKFLOWS)
        names = sorted(
            p.name
            for pattern in ("*.yml", "*.yaml")
            for p in directory.glob(pattern)
            if p.name != own
        )
    except (PathEscape, OSError):
        return Looked(unread=(_WORKFLOWS,))
    return Looked(tuple(f"{_WORKFLOWS}/{name}" for name in names))


# An owner in one of the three plain shapes GitHub documents: `@user`, `@org/team`, or an
# email address. A user or an organisation is letters, digits and hyphens, starting with a
# letter or digit; a team slug adds `_` and `.`. An email is a local part of letters, digits and
# `.`, `_`, `%`, `+`, `-`, then `@`, then a domain of two or more dot-separated labels of
# letters, digits and hyphens: no brackets, quotes or commas, which GitHub is not documented to
# accept. Anything outside these shapes is read as a line GitHub skips, even where GitHub might
# accept it, and that errs on the side that warns: a skipped line can only leave an earlier
# line deciding, and a real owner on it would have owned the file anyway. No class overlaps the
# character after it, so a word of any length is matched in linear time.
_OWNER = re.compile(
    r"@[A-Za-z0-9][A-Za-z0-9-]*(?:/[A-Za-z0-9][A-Za-z0-9_.-]*)?"
    r"|[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+"
)

# How a code-owners line is read: words separated by spaces and tabs; a comment, from a `#` at
# the line's start or after a blank; a run of `*` inside a component, which matches what one `*`
# does; the wildcards between a component's runs of plain characters; any other whitespace or a
# control character, which GitHub may or may not read as a separator; and every separator
# either reading knows.
_BLANKS = re.compile(r"[ \t]+")
_COMMENT = re.compile(r"(?:^|[ \t])#")
_STAR_RUN = re.compile(r"\*{2,}")
_WILD = re.compile(r"[*?]+")
_ODD = re.compile(r"[^\S \t]|[\x00-\x08\x0b-\x1f\x7f-\x9f]")
_SEPARATORS = re.compile(r"[\s\x00-\x1f\x7f-\x9f]+")

# The steps `codeowners-scope` may take asking about the workflows a repository already has,
# counted as `_Meter` counts them, as they are taken. Every kind of step costs at most about
# what one step of `_glob`'s walk does, so the budget is a few seconds of matching whatever the
# file holds, and a file that asks little asks everything: a 20 KB file of team lines spends
# about 3,000 steps on a workflow, and 300 workflows spend a thirtieth of the budget. Past it
# the workflows not yet asked are could not look, never owned.
SCOPE_STEPS_MAX = 30_000_000

# GitHub does not load a code-owners file of 3 MB or more. Decimal megabytes: of the two
# readings it is the smaller bound, so a file between them is read as unowned, the side that
# warns.
CODEOWNERS_MAX_BYTES = 3_000_000


class _Spent(Exception):
    """A `_Meter` ran out of steps part-way through a match."""


@dataclass(slots=True)
class _Meter:
    """The steps a run of matches may still take, counted as they are taken. Each is work the
    repository chooses how much of, weighted to cost about what one step of `_glob`'s walk does:

    - every rule `_governed` visits, one step, and one more for each eight characters of the
      path its one-operation refusal searches;
    - every rule `_matches` reaches past those refusals, one step for each cell of its table;
    - every component `_glob` is asked about, one step for each of its characters;
    - every step of the walk.

    Spending past the steps raises `_Spent`. A pass over the rules and a walk are counted when
    they end, so the last of each may run past the budget by its own length."""

    left: int

    def spend(self, steps: int) -> None:
        self.left -= steps
        if self.left < 0:
            raise _Spent


def _glob(pattern: str, name: str, meter: _Meter | None = None) -> bool:
    """One path component against one pattern component: `*` is any run of characters and `?`
    is one, and everything else is itself.

    No regex, and that is the point: a run of `*` compiled one `[^/]*` each backtracks
    exponentially, and the pattern is the repository's. This walk keeps one resumption point,
    the last `*`, so it takes at most `len(pattern) * len(name)` steps whatever the pattern.

    What any match must have is asked first, in single string operations: the characters before
    the first wildcard and after the last are the name's own ends, every run of characters
    between wildcards is somewhere in the name, and every character but `*` is one of the
    name's. A component with no `?` is then answered by finding each run in turn, since the
    leftmost place a run can go leaves the most room for the rest; only one with a `?` is walked.
    """
    if meter is not None:
        meter.spend(len(pattern))
    first = min((i for i in (pattern.find("*"), pattern.find("?")) if i >= 0), default=-1)
    if first < 0:
        return pattern == name
    cut = max(pattern.rfind("*"), pattern.rfind("?")) + 1
    if (
        len(name) < len(pattern) - pattern.count("*")
        or not name.startswith(pattern[:first])
        or not name.endswith(pattern[cut:])
        or any(piece not in name for piece in _WILD.split(pattern))
    ):
        return False
    if "?" not in pattern:
        pieces = pattern.split("*")
        at, stop = len(pieces[0]), len(name) - len(pieces[-1])
        for piece in pieces[1:-1]:
            at = name.find(piece, at, stop)
            if at < 0:
                return False
            at += len(piece)
        return True
    p = n = steps = 0
    star, resume = -1, 0
    walked = True
    while n < len(name):
        steps += 1
        if p < len(pattern) and pattern[p] in ("?", name[n]):
            p, n = p + 1, n + 1
        elif p < len(pattern) and pattern[p] == "*":
            star, resume, p = p, n, p + 1
        elif star >= 0:
            resume += 1
            p, n = star + 1, resume
        else:
            walked = False
            break
    if meter is not None:
        meter.spend(steps)
    return walked and pattern[p:].strip("*") == ""


@dataclass(frozen=True, slots=True)
class _Pattern:
    """One code-owners pattern, read once: its components, whether it names directories only,
    how many components are not `**` (the fewest a matching path has), and its longest run of
    characters without a wildcard, which a matching path must hold somewhere."""

    parts: tuple[str, ...]
    directory: bool
    fixed: int
    needle: str


def _pattern(text: str) -> _Pattern:
    """The code-owners pattern `text`, as GitHub reads it.

    The grammar is gitignore's without `!` and `[]`, which GitHub does not support: a pattern
    with no `/` but a trailing one matches at any depth, and any other is rooted. A whole
    component of two or more `*` is `**`, zero or more directories, and adjacent `**` are one;
    any other run of `*` is one `*`, collapsed here so no match walks the run. A pattern
    matching a directory owns everything below it, and a trailing `/` makes it directory-only,
    so it never owns a file of that name.
    """
    anchored = text.startswith("/") or "/" in text.rstrip("/")
    parts = [
        "**" if len(part) > 1 and not part.strip("*") else _STAR_RUN.sub("*", part)
        for part in text.strip("/").split("/")
    ]
    if not anchored:
        parts.insert(0, "**")
    kept = tuple(part for i, part in enumerate(parts) if part != "**" or parts[i - 1 : i] != ["**"])
    needle = max((run for part in kept for run in _WILD.split(part)), key=len)
    return _Pattern(kept, text.endswith("/"), sum(part != "**" for part in kept), needle)


def _matches(
    pattern: _Pattern, path: str, names: tuple[str, ...], meter: _Meter | None = None
) -> bool:
    """Whether `pattern` matches the file `path`, whose components are `names`: the file
    itself, or a directory above it, which owns what is below it.

    One table rather than a recursion, filled from the pattern's end: `ahead[j]` says whether
    the rest of the pattern matches `names[j:e]` for some end `e` it may stop at. `**` as a
    whole component is zero or more components, and one or more when it is the last: `a/**` is
    everything inside `a`, never `a`. A pattern with more other components than the path has,
    or a run of characters the path does not hold, cannot match, so each is refused in one
    string operation before the table, and the table is a few cells whatever the repository
    wrote.

    One rule is GitHub's and not git's: a last component of exactly `*` matches the directory's
    own files and nothing nested (GitHub's documentation: `docs/*` owns `docs/getting-started.md`
    and not `docs/build-app/troubleshooting.md`), where gitignore would match the directory
    `docs/build-app` and everything below it. The rule is about files, so it leaves `docs/*/`
    alone: a directory-only pattern names directories, and each one it matches owns what is
    below it, as git reads it.
    """
    end = len(names)
    if pattern.fixed > end or pattern.needle not in path:
        return False
    parts, directory = pattern.parts, pattern.directory
    if meter is not None:
        meter.spend(len(parts) * (end + 1))
    first = 1 if directory or parts[-1] != "*" else end  # direct children only
    last = end - 1 if directory else end
    ahead = [first <= j <= last for j in range(end + 1)]
    for i in range(len(parts) - 1, -1, -1):
        if parts[i] == "**":
            least = 1 if i == len(parts) - 1 else 0
            ahead = [any(ahead[j + least :]) for j in range(end + 1)]
        else:
            ahead = [
                j < end and ahead[j + 1] and _glob(parts[i], names[j], meter)
                for j in range(end + 1)
            ]
        if not any(ahead):
            return False  # no start left for the components before this one
    return ahead[0]


def _owns(text: str, path: str) -> bool:
    """Whether the code-owners pattern `text` matches the file `path`, as GitHub reads it."""
    return _matches(_pattern(text), path, tuple(path.split("/")))


def _exact_file(path: Path) -> bool:
    """A file under exactly this name: a case-folding filesystem answers `is_file()` for
    `codeowners` when asked for `CODEOWNERS`, and GitHub reads only the exact name."""
    return path.is_file() and path.name in os.listdir(path.parent)


def _codeowners_file(context: ProbeContext) -> tuple[str, str] | Looked:
    """The code-owners file GitHub reads, as `(its path, its text)`: the first of `_CODEOWNERS`
    that exists under its exact name, its bytes decoded as they are, since universal newlines
    would end a line at a carriage return GitHub may read as part of one. Otherwise what the
    `codeowners` probe reports: nothing owns the workflow when there is no file or GitHub would
    not load it, and a file that cannot be read is could not look."""
    for relative in _CODEOWNERS:
        try:
            path = contained(context.root, relative)
            if not _exact_file(path):
                continue
            if path.stat().st_size >= CODEOWNERS_MAX_BYTES:
                return Looked((_UNOWNED,))  # GitHub does not load it
            return relative, path.read_bytes().decode("utf-8")
        except (PathEscape, OSError, ValueError):
            return Looked(unread=(relative,))
    return Looked((_UNOWNED,))


def _rules(text: str) -> tuple[tuple[_Pattern, bool], ...]:
    """The code-owners file `text` as `(pattern, owned)` rules, each line read once, as GitHub
    reads it where it is documented and on the side that warns where it is not.

    Words are separated by spaces and tabs, and a `#` starts a comment only at the line's start
    or after a blank: GitHub documents an inline comment only after a blank, so `@owner#x` is one
    word, and not an owner. A line with an owner outside the three plain shapes decides nothing,
    as GitHub skips it. A line holding any other whitespace or control character is read without
    its owners: split on those characters, its first word may be the pattern GitHub reads and
    its owners ones it does not, and read owner-less it leaves each path it could match unowned,
    the side that warns. Lines end at a line feed, and the one carriage return a CRLF file puts
    before it is dropped; any other is such a control character, since GitHub may read it as
    part of a line rather than the end of one.

    Equal patterns match the same paths, so only the last line of each can govern one: the rules
    are one per pattern, in the order of each one's last line, which is what the last match
    wins reads.
    """
    latest: dict[str, bool] = {}
    for line in text.split("\n"):
        kept = _COMMENT.split(line.removesuffix("\r"), maxsplit=1)[0].strip(" \t")
        if not kept:
            continue
        if _ODD.search(kept):
            words = [word for word in _SEPARATORS.split(kept) if word][:1]
            owned = False
        else:
            words = _BLANKS.split(kept)
            if not all(_OWNER.fullmatch(word) for word in words[1:]):
                continue
            owned = len(words) > 1
        if words:
            latest.pop(words[0], None)
            latest[words[0]] = owned
    rules: dict[_Pattern, bool] = {}
    for written, owned in latest.items():
        pattern = _pattern(written)
        rules.pop(pattern, None)
        rules[pattern] = owned
    return tuple(rules.items())


def _governed(
    rules: tuple[tuple[_Pattern, bool], ...], path: str, meter: _Meter | None = None
) -> bool:
    """Whether the rule governing `path` names an owner: the last matching one wins, and a
    pattern with no owner leaves the path unowned. With a `meter`, every step is spent from it,
    and running out raises `_Spent`."""
    names, visited, owned = tuple(path.split("/")), 0, False
    for pattern, owns in reversed(rules):
        visited += 1
        if _matches(pattern, path, names, meter):
            owned = owns
            break
    if meter is not None:
        meter.spend(visited * (1 + len(path) // 8))
    return owned


def _codeowners(context: ProbeContext) -> Looked:
    """Whether the line governing stayfixed's workflow names an owner, in the code-owners file
    GitHub reads."""
    from stayfixed.project.api import CI_WORKFLOW

    if context.config.ci.mode == "none":
        return Looked()  # stayfixed renders no workflow to protect
    found = _codeowners_file(context)
    if isinstance(found, Looked):
        return found
    return Looked() if _governed(_rules(found[1]), CI_WORKFLOW) else Looked((_UNOWNED,))


def _codeowners_scope(context: ProbeContext) -> Looked:
    """Where stayfixed's workflow is owned, what else under `.github/` is not: a workflow a pull
    request adds, probed at a name no project gives one under both `.yml` and `.yaml`; every
    workflow the repository already has; and the code-owners file itself.

    A line owning only `stayfixed.yml` makes `codeowners` clean while a pull request can still add
    a workflow with a job named like the required check, which GitHub accepts; only a rule as
    wide as `/.github/` closes that. A later line with no owner takes an existing workflow back
    out of it, and a pull request can edit that one to the same end, so each is named: in
    `where` when its path is inside `PATH_VALUE`, and otherwise under `.github/workflows/`, since
    the name is the repository's. Silent wherever `codeowners` itself reports — no file, the
    workflow unowned, a file it could not read — so one gap is one warning; a workflows directory
    it could not list, and the workflows past `SCOPE_STEPS_MAX`, are could not look.
    """
    from stayfixed.project.api import CI_WORKFLOW

    if context.config.ci.mode == "none":
        return Looked()
    found = _codeowners_file(context)
    if isinstance(found, Looked):
        return Looked()
    relative, text = found
    rules = _rules(text)
    if not _governed(rules, CI_WORKFLOW):
        return Looked()
    existing = _foreign_workflows(context)
    meter, unowned, asked = _Meter(SCOPE_STEPS_MAX), [], 0
    try:
        for path in existing.where:
            if not _governed(rules, path, meter):
                unowned.append(path)
            asked += 1
    except _Spent:
        pass  # the rest are not asked
    unread = existing.unread or (() if asked == len(existing.where) else (_WORKFLOWS,))
    named = [path for path in unowned if PATH_VALUE.match(path)]
    added = all(_governed(rules, path) for path in _ANY_WORKFLOWS)
    where = [] if added and len(named) == len(unowned) else [_UNOWNED]
    where += named
    if not _governed(rules, relative):
        where.append(relative)
    return Looked(tuple(where), unread)


def _commit_types(context: ProbeContext) -> Looked:
    """Shas of the last `window` commits whose subject's type is outside the vocabulary. The
    records are NUL-delimited and paired by position, as the commit gate reads them: a subject
    may carry any byte but NUL, and nothing from one lands in `where`."""
    head = _head(context)
    if head is None:
        return Looked(unread=("git rev-parse",))
    if not head:
        return Looked()  # no commit yet
    out = _git(context, "log", "--no-merges", "-z", f"-n{context.window}", "--format=%H%x00%s")
    if out is None:
        return Looked(unread=("git log",))
    fields = out.split("\0")
    allowed = set(context.config.commit_messages.types)
    return Looked(
        tuple(
            fields[i]
            for i in range(0, len(fields) - 1, 2)
            if (m := _SUBJECT.match(fields[i + 1])) is None or m.group(1) not in allowed
        )
    )


PROBES: tuple[Probe, ...] = (
    Probe(
        "todo-markers",
        1,
        Severity.ADVICE,
        "file each marker that is a real defect with `stayfixed bugs new`, and delete the rest",
        _todo_markers,
    ),
    Probe(
        "tracked-env",
        None,
        Severity.WARNING,
        "remove the file from the index with `git rm --cached`, and rotate what it held",
        _tracked_env,
    ),
    Probe(
        "memory-history",
        8,
        Severity.WARNING,
        "notes committed to history stay readable in every clone; keep the store out of git",
        _memory_history,
    ),
    Probe(
        "foreign-hooks",
        5,
        Severity.ADVICE,
        "committed hooks run without a trust prompt in non-interactive sessions; keep only those "
        "you would run on every clone",
        _foreign_hooks,
    ),
    Probe(
        "foreign-workflows",
        None,
        Severity.ADVICE,
        "stayfixed's workflow runs beside these; nothing needs changing unless one repeats a gate",
        _foreign_workflows,
    ),
    Probe(
        "codeowners",
        7,
        Severity.WARNING,
        "add a CODEOWNERS line covering /.github/ and require code-owner review on the gate "
        "branch: a pull request can otherwise rewrite the workflow that judges it",
        _codeowners,
    ),
    Probe(
        "codeowners-scope",
        7,
        Severity.WARNING,
        "widen the CODEOWNERS line that owns stayfixed's workflow to /.github/, keep the file at "
        ".github/CODEOWNERS, and give an owner to each later line naming a workflow: a pull "
        "request can otherwise add or edit a workflow whose job is named like the required check",
        _codeowners_scope,
    ),
    Probe(
        "commit-types",
        None,
        Severity.ADVICE,
        "write subjects as `<type>: <intent>`, or `<type>(<area>): <intent>`, with a type from "
        "[commit_messages] types",
        _commit_types,
    ),
)


def _could_not_look(probe: str, principle: int | None, unread: tuple[str, ...]) -> Item:
    return item(probe, COULD_NOT_LOOK, principle, Severity.WARNING, COULD_NOT_LOOK_REMEDY, unread)


def _profile_items(context: ProbeContext) -> list[Item]:
    """One item per failed check of the configured profile, at the check's own level.

    An empty `[stayfixed] profile` is no profile and runs nothing. A name this build does not
    ship is one warning and the rest of the inventory still runs; a shipped profile that does
    not parse stays `ProfileError`, because that is a defect in the build. A `tracked` check git
    gave no answer for is "could not look", never an untracked file.
    """
    name = context.config.stayfixed.profile
    if not name:
        return []
    from stayfixed import profiles

    shipped = profiles.shipped()
    if name not in shipped:
        remedy = PROFILE_NOT_SHIPPED_REMEDY.format(shipped=", ".join(shipped) or "none")
        return [
            item(
                PROFILE,
                PROFILE_NOT_SHIPPED,
                None,
                Severity.WARNING,
                remedy,
                ["[stayfixed] profile"],
            )
        ]
    items: list[Item] = []
    unanswered: dict[str, None] = {}
    for outcome in profiles.evaluate(profiles.load_profile(name), context.root):
        check = outcome.check
        if outcome.located:
            items.append(
                item(PROFILE, check.id, None, check.level, check.remedy, outcome.located, count=1)
            )
        unanswered.update(dict.fromkeys(outcome.unanswered))
    if unanswered:
        items.append(_could_not_look(PROFILE, None, tuple(unanswered)))
    return items


def run_probes(context: ProbeContext) -> list[Item]:
    """Every probe's items in `PROBES` order, then the profile's: per probe, what it found (the
    probe's id is the rule) and one `could-not-look` item for what it could not read."""
    items: list[Item] = []
    for probe in PROBES:
        looked = probe.run(context)
        if looked.where:
            items.append(
                item(
                    probe.id,
                    probe.id,
                    principle=probe.principle,
                    severity=probe.severity,
                    remedy=probe.remedy,
                    where=looked.where,
                )
            )
        if looked.unread:
            items.append(_could_not_look(probe.id, probe.principle, looked.unread))
    return items + _profile_items(context)
