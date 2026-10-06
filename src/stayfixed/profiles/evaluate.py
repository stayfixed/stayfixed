"""A profile's checks against a repository, reading only files and the git index.

| Kind | A finding when | `located` names |
|---|---|---|
| `present` | no locator resolves | every locator's `at` |
| `absent` | some locator resolves | each `at` that resolved |
| `tracked` | a located file is neither tracked nor ignored | each `at` that found one |

A `tracked` check whose question git gave no answer to (`gitenv.NO_ANSWER`) is an outcome too,
with that `at` under `unanswered` rather than `located`: a check that could not look has not
passed.

A locator resolves when:
- its `at` names at least one regular file at or under the root, reached through no symlink
  (`contained`);
- then, when it names a `toml` key or an `ini` section or key, that key is present in a file
  that parses;
- then, when it carries a `match`, the value's text matches it.

**A value's text** is:
- a string, as written;
- a boolean, as TOML spells it (`true`);
- a number, as written;
- a list, as its items joined by one space.

That is the whole coercion, and it is what the profile's patterns are written against.

**The repository's bytes stay inside this module.** Parsing may fail, and then the locator
resolves to nothing. No exception text and no value reaches an `Outcome`. `located` carries
the profile's own `at` strings, which are the plugin's, never a file name a glob found.
"""

from __future__ import annotations

import configparser
import tomllib
from collections.abc import Callable
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any, TypeVar

from stayfixed.config.loader import UNPARSEABLE
from stayfixed.config.paths import PathEscape, contained
from stayfixed.gitenv import git_run, in_work_tree
from stayfixed.profiles.model import Check, CheckKind, Locator, Profile

_GLOB = frozenset("*?[")
_TEXT_CAP = 1024 * 1024  # a profile reads configuration files, never anything this large
_Document = TypeVar("_Document")


@dataclass(frozen=True)
class Outcome:
    check: Check
    located: tuple[str, ...]
    # The `at` strings git gave no answer for, so the check could not look there; `tracked` only.
    unanswered: tuple[str, ...] = ()


def _files(root: Path, at: str) -> list[str]:
    """Root-relative regular files `at` names, each reached through no symlink."""
    candidates = (
        [p.relative_to(root).as_posix() for p in sorted(root.glob(at))] if _GLOB & set(at) else [at]
    )
    found: list[str] = []
    for relative in candidates:
        try:
            path = contained(root, relative)
        except PathEscape:
            continue
        if path.is_file():
            found.append(relative)
    return found


def _read(root: Path, relative: str) -> str | None:
    try:
        path = contained(root, relative)
        if path.stat().st_size > _TEXT_CAP:
            return None
        return path.read_text(encoding="utf-8")
    except (PathEscape, OSError, UnicodeDecodeError):
        return None


def _text(value: Any) -> str | None:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str | int | float):
        return str(value)
    if isinstance(value, list):
        parts = [_text(item) for item in value]
        return " ".join(part for part in parts if part is not None)
    if isinstance(value, dict):
        return ""  # a table is present; it has no text of its own
    return None


def _toml_document(text: str) -> dict[str, Any] | None:
    """`text` parsed as TOML, or `None` when it will not parse.

    `RecursionError` is `tomllib`'s answer to nesting deep enough to exhaust the stack, and a
    kilobyte of `[` is enough; the file is the repository's, so it chooses that as freely as a
    syntax error.
    """
    try:
        return tomllib.loads(text)
    except UNPARSEABLE:
        return None


def _toml_value(document: dict[str, Any], dotted: str) -> str | None:
    """The text of `dotted` in `document`, or `None` when the key is absent or has no text.

    `_text` walks the nesting `tomllib` built, so it sits inside the same `RecursionError`
    guard the parse does. And it spells an integer with `str`, which raises `ValueError` past
    4,300 digits, while `tomllib` converts a hex, octal or binary literal of any length: such a
    value is one this locator cannot read, as a file that does not parse is, and resolves to
    nothing rather than ending the whole evaluation.
    """
    try:
        node: Any = document
        for part in dotted.split("."):
            if not isinstance(node, dict) or part not in node:
                return None
            node = node[part]
        return _text(node)
    except (RecursionError, ValueError):
        return None


def _ini_document(text: str) -> configparser.ConfigParser | None:
    """`text` read as an INI file, or `None`.

    `configparser` refuses a file with no section header or a line it cannot read with its own
    `configparser.Error`, and the locator then resolves to nothing. Its reader is line by line
    and does not recurse, so nesting has no second failure here.
    """
    parser = configparser.ConfigParser(interpolation=None, strict=False)
    try:
        parser.read_string(text)
    except configparser.Error:
        return None
    return parser


def _ini_value(parser: configparser.ConfigParser, address: tuple[str, ...]) -> str | None:
    """The value at `address` in `parser`, `""` for a section alone, or `None`."""
    section, key = address[0], address[1] if len(address) == 2 else None
    if not parser.has_section(section):
        return None
    if key is None:
        return ""
    return parser.get(section, key) if parser.has_option(section, key) else None


def _once(
    root: Path, parse: Callable[[str], _Document | None]
) -> Callable[[str], _Document | None]:
    """`parse` of each file under `root`, read and parsed the first time a locator asks for it.
    A file that cannot be read, or will not parse, is `None` for every locator that asks."""

    @cache
    def parsed(relative: str) -> _Document | None:
        text = _read(root, relative)
        return None if text is None else parse(text)

    return parsed


class _Parsed:
    """Each file a profile's locators read, parsed once per `evaluate`: seventeen locators of the
    shipped profile read `pyproject.toml`, and each parsed it again."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.toml = _once(root, _toml_document)
        self.ini = _once(root, _ini_document)


def _resolves(parsed: _Parsed, locator: Locator) -> bool:
    for relative in _files(parsed.root, locator.at):
        value: str | None = ""
        if locator.toml is not None:
            document = parsed.toml(relative)
            value = None if document is None else _toml_value(document, locator.toml)
        elif locator.ini is not None:
            parser = parsed.ini(relative)
            value = None if parser is None else _ini_value(parser, locator.ini)
        if value is None:
            continue
        if locator.match is not None and not locator.match.search(value):
            continue
        return True
    return False


def _untracked(root: Path, relative: str) -> bool | None:
    """Untracked and not ignored: `--others` lists what the index lacks, and `--exclude-standard`
    drops what `.gitignore`, `info/exclude` and `core.excludesFile` ignore. A lockfile a library
    ignores on purpose is a decision, not a file somebody forgot to commit.

    Outside a work tree `git ls-files` exits non-zero and writes nothing to stdout, so a
    directory that is no repository answers "not untracked" and has nothing to report; no
    second probe asks it first. `code == 0` says so explicitly rather than trusting the empty
    output alone.

    `None` is `git_run`'s `-1`: git could not run or ran past its bound. That is no answer, and
    reading it as "not untracked" passed a check that never looked. So is a refusal inside a
    work tree (a worktree whose git directory is gone, a checkout of dubious ownership), which
    git answers exactly as it answers outside one: whether this is a repository is read off the
    disk, as every other probe reads it.
    """
    code, out = git_run(root, "ls-files", "--others", "--exclude-standard", "--", relative)
    if code == -1 or (code != 0 and in_work_tree(root)):
        return None
    return code == 0 and bool(out.strip())


def detects(profile: Profile, root: Path) -> bool:
    return any(_files(root, at) for at in profile.detect)


def _names(locators: list[Locator]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(locator.at for locator in locators))


def evaluate(profile: Profile, root: Path) -> list[Outcome]:
    parsed = _Parsed(root)
    outcomes: list[Outcome] = []
    for check in profile.checks:
        locators = list(check.locators)
        if check.kind is CheckKind.PRESENT:
            hits = [] if any(_resolves(parsed, loc) for loc in locators) else locators
        elif check.kind is CheckKind.ABSENT:
            hits = [loc for loc in locators if _resolves(parsed, loc)]
        else:
            hits, unanswered = [], []
            for loc in locators:
                answers = [_untracked(root, f) for f in _files(root, loc.at)]
                if True in answers:
                    hits.append(loc)
                elif None in answers:
                    unanswered.append(loc)
            if hits or unanswered:
                outcomes.append(Outcome(check, _names(hits), _names(unanswered)))
            continue
        if hits:
            outcomes.append(Outcome(check, _names(hits)))
    return outcomes
