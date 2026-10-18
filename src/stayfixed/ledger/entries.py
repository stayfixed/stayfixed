"""A ledger: one file per entry under its register's directory, one generated index.

The index is generated from the entry files and must never be edited by hand: the entry files
are the truth, the index carries nothing of its own, so a conflict in it is always resolved by
regenerating rather than by merging text.

Frontmatter is a deliberately flat subset of YAML — `key: value` lines, an inline `[a, b]`
list of identifiers for `related`, an inline `["a", "b"]` list of double-quoted items for each
of the register's lists, no nesting — so this module reads it with the standard library alone.
Anything outside the subset raises `LedgerError` rather than parsing to a default: a bug report
that silently loses its status is worse than one that fails the guard.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from stayfixed.config.paths import contained
from stayfixed.errors import Failure
from stayfixed.fsops import read_regular_text, said
from stayfixed.identifiers import Identifiers
from stayfixed.ledger.register import ENGINE_KEYS, Register
from stayfixed.printed import quoted

# A line break on the file's own endings: LF, CRLF or a lone CR, the three `read_ledger_text`
# translates to LF. A CR is a break of its own only where no LF follows, so a CRLF is never read as
# two: read as `\r` and then `\n`, `---` CRLF `---` CRLF would close a block it never opened.
_BREAK = r"(?:\r\n|\r(?!\n)|\n)"
# The frontmatter block between its two `---` fences, then the body after one optional blank line.
_FRONTMATTER = re.compile(rf"\A---{_BREAK}(.*?){_BREAK}---{_BREAK}{_BREAK}?(.*)\Z", re.DOTALL)
_KEY_VALUE = re.compile(r"\A([a-z_]+):[ \t]*(.*)\Z")
_ISO_DATE = re.compile(r"\A\d{4}-\d{2}-\d{2}\Z")
# A value that would parse as something other than a plain string in real YAML. The subset
# stays valid YAML, so anything ambiguous is rejected rather than guessed at — which means the
# leading character class has to be YAML's whole indicator set, not the part of it this ledger
# happened to hit. A `--source` of `#412 in the tracker` written bare is the shape that proved
# it: this module's own reader hands the string back, and `yaml.safe_load` reads the value as a
# comment and the key as null, so the promise at the top of this file quietly stops holding.
# A value that *ends* in a colon is the same promise broken at the other end — `source: a:` is
# a nested mapping to a real YAML reader — so it is quoted too.
_NEEDS_QUOTING = re.compile(r"\A[-?:,\[\]{}#&*!|>'\"%@`]|: | #|:\Z")
# A C0 control character or DEL: an item a list key holds is an argv word, which a later command
# hands to a process, so neither may reach one.
_CONTROL_CHARACTER = re.compile(r"[\x00-\x1f\x7f]")

# The refusals of a list key's value. `{where}` is the entry's path as `_where` names it, `{key}`
# the list key: both the reader's own, so nothing a repository wrote reaches the line unescaped.
# Their anchor is the entry file, which anyone who can commit writes, and that author already
# controls the whole argv, so these refusals and `_CONTROL_CHARACTER` report validity (an argv a
# later runner can execute as written) and are no trust boundary.
LIST_SHAPE = '{where}: `{key}` must be an inline list of double-quoted items, like `["a", "b"]`'
EMPTY_ITEM = "{where}: `{key}` holds an empty item"
CONTROL_IN_ITEM = "{where}: `{key}` holds an item with a control character"


# An entry's `id:` line, whatever its spacing or quoting: what `renumber` rewrites to move an entry,
# and what `check` rewrites back to tell a move half done.
ID_LINE = re.compile(r"^id:.*$", re.MULTILINE)


class LedgerError(Failure):
    """A ledger file that cannot be read, or a rule that has been broken.

    A `Failure`, so the exit code 1 it carries is the frame's to map, never this module's
    (library modules raise, only `cli.py` maps).
    """


def _where(path: Path) -> str:
    """The entry's path as every `LedgerError` in this module names it. The file name is the
    repository's, so it goes through `quoted`: a crafted one arrives escaped, never as a line
    break or an escape sequence on the operator's terminal."""
    return quoted(path.as_posix())


@dataclass(frozen=True)
class Entry:
    """One parsed entry file. `fields` holds the register's keys outside `ENGINE_KEYS` and its
    lists, each one the register declares, with `""` for a key the file leaves empty or out;
    `lists` holds each of its lists, with `()` for one the file leaves empty or out."""

    id: str
    title: str
    status: str
    related: tuple[str, ...]
    body: str
    path: Path
    # Compared, not hashed: a dict has no hash, and the fields above already tell two entries
    # apart, so equal entries still hash equal.
    fields: Mapping[str, str] = field(hash=False)
    lists: Mapping[str, tuple[str, ...]] = field(default_factory=dict, hash=False, compare=True)

    def value(self, key: str) -> str:
        """The entry's value for one of its register's keys other than `related` and its lists;
        a `KeyError` for a list, which has no one value."""
        if key in ENGINE_KEYS and key != "related":
            return str(getattr(self, key))
        return self.fields[key]

    @property
    def number(self) -> int:
        # `parse_entry` validated the identifier against `ids.exact`, so the digits are known
        # to be there and no pattern is needed to read them back.
        return int(self.id.rsplit("-", 1)[1])


def _unquote(raw: str, *, key: str, where: Path) -> str:
    """Return the string a frontmatter value denotes, or raise."""
    if not raw.startswith('"'):
        if _NEEDS_QUOTING.search(raw):
            raise LedgerError(f"{_where(where)}: `{key}` needs double quotes around {raw!r}")
        return raw.strip()
    if len(raw) < 2 or not raw.endswith('"'):
        raise LedgerError(f"{_where(where)}: `{key}` has an unterminated quoted value")
    body = raw[1 : len(raw) - 1]
    # The final `"` closes the value only when the backslash run before it is even, since `\\`
    # is itself an escape. Testing the last two characters instead rejects this tool's own
    # output: `quote` writes a title ending in `\` as `"…\\"`, so this reader would refuse the
    # very file the renderer just wrote, and one such title would break every pass over the
    # whole ledger until a human found it.
    if (len(body) - len(body.rstrip("\\"))) % 2:
        raise LedgerError(f"{_where(where)}: `{key}` has an unterminated quoted value")
    out: list[str] = []
    index = 0
    while index < len(body):
        character = body[index]
        if character != "\\":
            out.append(character)
            index += 1
            continue
        following = body[index + 1 : index + 2]
        if following not in ('"', "\\"):
            raise LedgerError(
                f"{_where(where)}: `{key}` uses an unsupported escape `\\{following}`"
            )
        out.append(following)
        index += 2
    return "".join(out)


def _require_iso_date(value: str, *, key: str, where: Path) -> str:
    """`value` back, once it is a date that exists.

    Both halves are needed. `date.fromisoformat` alone accepts the compact `YYYYMMDD` form and
    the ISO week form (`2026-W33-1`), neither of which an index's date column or any date
    comparison here is written for, so
    the shape test keeps the extended form. The shape test alone accepts `2026-02-30` and
    `2026-13-45` — digits in the right places, days nobody can have recorded anything on — in a
    field this guard is meant to be the authority on.
    """
    if not _ISO_DATE.match(value):
        raise LedgerError(
            f"{_where(where)}: `{key}` must be an ISO date (YYYY-MM-DD), got {value!r}"
        )
    try:
        date.fromisoformat(value)
    except ValueError as error:
        raise LedgerError(
            f"{_where(where)}: `{key}` names a date that does not exist: {value!r}"
        ) from error
    return value


def _past_spaces(raw: str, index: int) -> int:
    """The first index from `index` on that is not a space: the one separator a list allows."""
    while raw[index : index + 1] == " ":
        index += 1
    return index


def _closing_quote(raw: str, opening: int) -> int:
    """The index of the `"` that closes the quoted item opening at `opening`, or -1.

    A backslash takes the character after it along, so an escaped quote never closes the item and
    a quote after an escaped backslash does: the two escapes `_unquote` reads, which then reads the
    item itself.
    """
    index = opening + 1
    while index < len(raw):
        if raw[index] == "\\":
            index += 2
            continue
        if raw[index] == '"':
            return index
        index += 1
    return -1


def _parse_quoted_list(raw: str, *, key: str, where: Path) -> tuple[str, ...]:
    """The items of a list key's value, or raise.

    An empty value and `[]` are the empty list; otherwise `[`, double-quoted items separated by a
    comma and spaces, and `]` ending the value. Scanned, never split on `,`: an item is an argv
    word, and a comma or a bracket inside its quotes is part of it. Each quoted run goes to
    `_unquote`, so an item's escapes are a title's.
    """
    shape = LedgerError(LIST_SHAPE.format(where=_where(where), key=key))
    if not raw:
        return ()
    if not raw.startswith("["):
        raise shape
    items: list[str] = []
    index = _past_spaces(raw, 1)
    more = raw[index : index + 1] != "]"
    while more:
        if raw[index : index + 1] != '"':
            raise shape
        closing = _closing_quote(raw, index)
        if closing < 0:
            raise shape
        item = _unquote(raw[index : closing + 1], key=key, where=where)
        if not item:
            raise LedgerError(EMPTY_ITEM.format(where=_where(where), key=key))
        if _CONTROL_CHARACTER.search(item):
            raise LedgerError(CONTROL_IN_ITEM.format(where=_where(where), key=key))
        items.append(item)
        index = _past_spaces(raw, closing + 1)
        more = raw[index : index + 1] == ","
        if more:
            index = _past_spaces(raw, index + 1)
    # The `]` and nothing after it: anything else past the last item, or no `]` at all, is a list
    # this reader would otherwise end early.
    if raw[index:] != "]":
        raise shape
    return tuple(items)


def _parse_related(raw: str, *, where: Path, ids: Identifiers) -> tuple[str, ...]:
    if not raw:
        return ()
    if not (raw.startswith("[") and raw.endswith("]")):
        raise LedgerError(
            f"{_where(where)}: `related` must be an inline list like `[{ids.shape}, {ids.shape}]`"
        )
    items = [item.strip() for item in raw[1:-1].split(",") if item.strip()]
    for item in items:
        if not ids.is_identifier(item):
            raise LedgerError(
                f"{_where(where)}: `related` names {item!r}, which is not a {ids.prefix} identifier"
            )
    return tuple(items)


def _frontmatter(text: str) -> tuple[list[tuple[int, int, str]], str] | None:
    """The frontmatter lines of an entry's `text` and the body after them, or `None` for a file
    with no frontmatter block at its top.

    Each line comes as its number in the file, the offset in `text` it starts at, and the line
    without its line break. The one reader of where a value sits: `parse_entry` reads the text
    `read_ledger_text` translated to LF, and `renumber`'s sweep the text on disk, CRLF where a
    checkout's `core.autocrlf` wrote it so, and both must find a value on the same line. The fences
    are found on the file's own endings (`_BREAK`); the lines are split as `str.splitlines` splits
    them, so a frontmatter value holding U+0085, U+2028 or a vertical tab is cut into two lines
    there, the second of which is no `key: value`, and the entry is refused.
    """
    match = _FRONTMATTER.match(text)
    if match is None:
        return None
    lines: list[tuple[int, int, str]] = []
    offset = match.start(1)
    for number, piece in enumerate(match.group(1).splitlines(keepends=True), start=2):
        lines.append((number, offset, piece.splitlines()[0]))
        offset += len(piece)
    return lines, match.group(2)


def parse_entry(text: str, *, path: Path, register: Register) -> Entry:
    """Parse one entry file's text, raising `LedgerError` on anything ambiguous.

    `path` is never opened here — it names the file in every message this raises, and becomes
    the parsed entry's own `path`. So callers pass the form they want an operator to read: a
    repo-relative one, since these messages are printed by `check` on CI, where an absolute
    path is a runner's scratch directory nobody can act on.
    """
    ids, schema = register.ids, register.schema
    frontmatter = _frontmatter(text)
    if frontmatter is None:
        raise LedgerError(f"{_where(path)}: no `---` frontmatter block at the top of the file")
    lines, body = frontmatter
    fields: dict[str, str] = {}
    for number, _, line in lines:
        if not line.strip():
            continue
        if line[:1] in (" ", "\t"):
            raise LedgerError(f"{_where(path)}:{number}: nested frontmatter is not supported")
        key_value = _KEY_VALUE.match(line)
        if key_value is None:
            raise LedgerError(f"{_where(path)}:{number}: expected `key: value`, got {line!r}")
        key, raw = key_value.group(1), key_value.group(2).strip()
        if key not in schema.keys:
            raise LedgerError(f"{_where(path)}:{number}: unknown frontmatter key `{key}`")
        if key in fields:
            raise LedgerError(f"{_where(path)}:{number}: duplicate key `{key}`")
        fields[key] = raw

    for key in schema.required:
        if not fields.get(key):
            raise LedgerError(f"{_where(path)}: missing required frontmatter key `{key}`")
    identifier = _unquote(fields["id"], key="id", where=path)
    if not ids.is_identifier(identifier):
        raise LedgerError(f"{_where(path)}: `id` must look like {ids.shape}, got {identifier!r}")
    status = _unquote(fields["status"], key="status", where=path)
    if status not in schema.statuses:
        raise LedgerError(
            f"{_where(path)}: `status` must be one of {', '.join(schema.statuses)}, got {status!r}"
        )
    if status != schema.void:
        for key in schema.required_unless_void:
            if not fields.get(key):
                raise LedgerError(f"{_where(path)}: missing required frontmatter key `{key}`")
    # Read in the order the refusals have always come in — the level, the dates, the title, then
    # the rest in the order of the keys, the bug ledger's `area` first among them — so an entry
    # with two defects is told about the same one first.
    level = schema.level
    values: dict[str, str] = {}
    values[level] = _unquote(fields.get(level, ""), key=level, where=path)
    if values[level] and values[level] not in schema.levels:
        raise LedgerError(
            f"{_where(path)}: `{level}` must be one of {', '.join(schema.levels)}, "
            f"got {values[level]!r}"
        )
    for key in schema.dates:
        values[key] = _unquote(fields.get(key, ""), key=key, where=path)
        # Required, it is a date even when quoted empty: `found: ""` passes the presence check.
        if values[key] or key in schema.required:
            _require_iso_date(values[key], key=key, where=path)
    title = _unquote(fields["title"], key="title", where=path)
    for key in schema.scalar_keys:
        if key not in ENGINE_KEYS and key not in values:
            values[key] = _unquote(fields.get(key, ""), key=key, where=path)
    lists = {
        key: _parse_quoted_list(fields.get(key, ""), key=key, where=path) for key in schema.lists
    }

    return Entry(
        id=identifier,
        title=title,
        status=status,
        related=_parse_related(fields.get("related", ""), where=path, ids=ids),
        body=body,
        path=path,
        fields=values,
        lists=lists,
    )


def list_value_spans(text: str, lists: tuple[str, ...]) -> list[tuple[int, int]]:
    """Where the value of each of `lists` lies in an entry's frontmatter, as `(start, end)`
    offsets into `text`, in order: what `renumber`'s sweep leaves as it is.

    The lines are `parse_entry`'s own (`_frontmatter`), on the file's own line endings, so a span
    is the value that reader reads, and a file with no frontmatter block has none.
    """
    frontmatter = _frontmatter(text)
    if frontmatter is None:
        return []
    spans: list[tuple[int, int]] = []
    for _, offset, line in frontmatter[0]:
        key_value = _KEY_VALUE.match(line)
        if key_value is not None and key_value.group(1) in lists:
            spans.append((offset + key_value.start(2), offset + len(line)))
    return spans


def read_ledger_text(path: Path, *, where: Path) -> str:
    """One ledger file's text, or a `LedgerError` naming it.

    A condition the operator can fix — a permission bit, a stray non-UTF-8 byte in an entry —
    must not leave this area as a bare `OSError` or `UnicodeDecodeError`. `cli.run` maps a
    `Failure` to exit 1 and everything else to exit 2, and 2 is reserved for a refusal or an
    internal error: a repository condition reported as an internal error tells the operator the
    tool is broken rather than that their tree is, and there is nothing in that message for them
    to act on. `check.register_gate` has an `unreadable-entry` rule for exactly this file and
    catches this; `scan.scannable` records the same condition on `Scanned.error` instead of
    raising, because it has a whole tree to get through where this has one file.
    """
    try:
        # Entries are globbed and a clone commits them: see `fsops.open_regular` for what a
        # link to a device or a FIFO did. A refusal is an `OSError`, an entry not read.
        return read_regular_text(path)
    except UnicodeDecodeError as error:
        raise LedgerError(f"{_where(where)}: is not valid UTF-8 ({error.reason})") from error
    except OSError as error:
        raise LedgerError(f"{_where(where)}: could not be read ({said(error)})") from error


def entry_dir(root: Path, register: Register) -> Path:
    return contained(root, register.directory)


def entry_paths(root: Path, register: Register) -> list[Path]:
    """The register's entry files, sorted: every `<prefix>-*.md` in its directory.

    The one statement of which files are entries. `load_entries` parses these, and `renumber`'s
    sweep keeps the list values of these and of no other file, so a file the register does not
    read — a note beside the ledger, a `.txt` named like an entry — is swept like any text.
    """
    return sorted(entry_dir(root, register).glob(f"{register.ids.prefix}-*.md"))


def load_entries(root: Path, register: Register) -> list[Entry]:
    """Every entry under the register's directory, ordered by identifier number.

    Parsed against the repo-relative path, which is `parse_entry`'s documented contract.
    Handing it the absolute one made the writing commands describe a malformed entry by a
    path under a temporary directory while `check` described the same file repo-relatively —
    and on CI the absolute form names a runner's scratch directory nobody can act on.
    """
    entries = [
        parse_entry(
            read_ledger_text(path, where=path.relative_to(root)),
            path=path.relative_to(root),
            register=register,
        )
        for path in entry_paths(root, register)
    ]
    return sorted(entries, key=lambda entry: entry.number)


def quote(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def scalar(value: str) -> str:
    """A frontmatter value written so `_unquote` gives back this exact string.

    Every writer goes through here rather than deciding per field: a `fixed_in` of a
    backticked short commit id is the commonest value in a ledger and, unquoted, is the
    leading backtick `_NEEDS_QUOTING` refuses.
    """
    return quote(value) if _NEEDS_QUOTING.search(value) else value


def field_line(key: str, value: str) -> str:
    """`key: value`, or a bare `key:` when there is no value.

    A trailing space on an empty field is whitespace an editor may strip on save, and an entry
    file that no longer matches what the writer produced is one a later reader reports as a
    conflicting duplicate against the tool's own output.
    """
    written = scalar(value)
    return f"{key}: {written}" if written else f"{key}:"


def related_field(related: tuple[str, ...] | list[str]) -> str:
    """The `related:` line, which `field_line` cannot write.

    Its quote decision would wrap the leading `[` and turn the inline list into a string. Both
    writers needed the exception and each carried its own copy of this line, with a comment
    pointing at the other as justification — which is the argument for a third helper, not for
    a second copy. They have to stay byte-identical: a writer that compares an existing entry
    file against a rendered one reports any difference as a conflicting duplicate, so two
    spellings of this line would make the tool conflict with its own writes.
    """
    return f"related: [{', '.join(related)}]" if related else "related:"
