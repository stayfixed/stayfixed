"""Whether a Markdown file's YAML frontmatter declares hooks: text in, an answer out.

`hook-entries` names each skill, command or agent file whose frontmatter holds a top-level `hooks`
key: `doctor.hooked` finds the files and reads them, and `doctor.entries` tells the row. This module
answers that one question of a file's text and reads nothing else, no file and no YAML beyond the
keys it looks for. The runtime imports only the standard library (CONTRIBUTING.md), so there is no
YAML parser to hand the text to, and the reader below is written for the one key it finds. It
answers that a file declares none only where the frontmatter keeps to a plain subset of YAML that
it reads exactly (`_plain`); of any other it says "yes" or "cannot tell", which both name the file.
"""

from __future__ import annotations

import re
import sys
from collections.abc import Iterator
from typing import Literal

# The line that opens a frontmatter and the next one that closes it, `---` and any blanks after it,
# each ended by a line break, LF, CRLF or a lone CR (and the closing one by the end of the text
# too); and a lone CR. Each is found in the text as it stands, without splitting it into lines or
# turning its line breaks into LFs, so the text past the frontmatter costs no memory however long
# it is or however its lines end.
_FENCE = "---"
_OPENING_LINE = re.compile(r"---[^\S\r\n]*+(?:\r\n?|\n)")
_CLOSING_LINE = re.compile(r"(?<=[\r\n])---[^\S\r\n]*+(?=[\r\n]|\Z)")
_LONE_RETURN = re.compile(r"\r(?!\n)")
# The most lines of a reading and characters of a frontmatter this reader reads, named caps
# (CONTRIBUTING.md): past either, it does not read and answers "cannot tell", which names the file.
# Python keeps an object for each line of each reading, so a file of short lines at
# `fsops.REGULAR_READ_LIMIT` asked a gigabyte and more of one `doctor` run; and each reading copies
# the text, at four bytes a character once one character in it is past the Basic Multilingual Plane,
# so a file of wide lines asked three gigabytes. Ten thousand short lines ask a megabyte or two, and
# eight mebicharacters of the widest about a hundred megabytes; a frontmatter written by hand is a
# few lines. The characters are counted from the start of the file to where the frontmatter ends, as
# the file holds them, a byte-order mark and each CR among them, and the long-line tests in
# `tests/doctor/test_checks.py` stay below them. No shipped file states either; `doctor.entries`
# names both in the remedy.
LINES_READ = 10_000
CHARACTERS_READ = 1 << 23
# The fence that opens a frontmatter as Claude Code is read to find one, and the blanks and line
# breaks after it, taken whole so that the text is scanned once.
_OPENING = re.compile(r"---[\s\ufeff]*+")
# A key quoted either way: double, with backslash escapes, or single, with `''` for a quote.
#
# Every repetition in this module's patterns that a long value can reach is possessive (`*+`, `++`)
# or repeats one character: Python's `re` keeps a record for each pass of a repeated group in case
# it has to give the pass back, hundreds of bytes per character of one long value, so a file at
# `fsops.REGULAR_READ_LIMIT` asked gigabytes of one `doctor` run. A possessive repetition gives
# nothing back and keeps no record, and one of a single character keeps none either way. None of
# the possessive ones changes what is matched, since nothing after one could take back what it
# read, but one: a single-quoted scalar whose quotes never pair up as YAML reads them
# (`'hooks''`), which giving back ended at its last `''`, is no quoted scalar here, as it is none
# to YAML.
_DOUBLE_QUOTED = r'"(?:[^"\\]++|\\.)*+"'
_SINGLE_QUOTED = r"'[^']*+(?:''[^']*+)*+'"
_QUOTED = f"{_DOUBLE_QUOTED}|{_SINGLE_QUOTED}"
# One token of a flow mapping (`{name: x, hooks: {...}}`): a quoted scalar, a flow indicator, a
# comment, blanks, a plain scalar -- which holds a `:` not followed by a blank or an indicator, and
# a `#` not after a blank -- or a colon. Whatever else a line holds is one character at a time.
#
# A plain scalar is read a character at a time up to the first place it cannot go on, a blank, an
# indicator, or a colon that one of those or the end follows: a lazy repeat of one character with
# that place looked for ahead, so no group is repeated. As a possessive repeat of "a character or a
# colon not followed by a blank", it took the colon and the blank after it too on Python 3.11.0 to
# 3.11.4, which end a failed pass of it where the pass stopped (CONTRIBUTING.md, "Tests"): `{hooks:
# x}` held no key there.
_FLOW = re.compile(
    rf"(?P<quoted>{_QUOTED})|(?P<indicator>[{{}}\[\],])|(?P<comment>#[^\n]*)|(?P<blank>\s+)"
    r"|(?P<plain>[^\s{}\[\],:#\"'][^\s{}\[\],]*?(?=[\s{}\[\],]|:(?:[\s{}\[\],]|\Z)|\Z))"
    r"|(?P<colon>:)|(?P<other>.)",
    re.DOTALL,
)
# A double-quoted scalar's escapes, as YAML spells them.
_ESCAPE = re.compile(r"\\(x[0-9A-Fa-f]{2}|u[0-9A-Fa-f]{4}|U[0-9A-Fa-f]{8}|.)", re.DOTALL)
_ESCAPED = {
    "0": "\0",
    "a": "\a",
    "b": "\b",
    "t": "\t",
    "n": "\n",
    "v": "\v",
    "f": "\f",
    "r": "\r",
    "e": "\x1b",
    "N": "\x85",
    "_": "\xa0",
    "L": "\u2028",
    "P": "\u2029",
}
# The key whose presence at the top level is what this module answers for.
_HOOKS = "hooks"
# What may stand ahead of a frontmatter's top-level node and leave it the node it is: its
# properties, each a tag (`!x`, `!!map`) or an anchor (`&x`) ended by a blank or a line break, then
# any comment lines. A flow mapping behind them is still a flow mapping. Each pass is a mark, then
# runs that cannot fail, the blanks after a property's `\S*+` or a comment's `[^\n]*+` among them,
# so a pass can fail only on its first character: the shape every supported Python reads alike
# (CONTRIBUTING.md, "Tests"). The same holds for the two patterns below.
_AHEAD = re.compile(r"(?:[!&]\S*+\s*+)++(?:#[^\n]*+\s*+)*+")
# The same properties with comments among them as well as after them, which YAML reads past: the
# lines a block mapping behind them may start on.
_PROPERTY_RUN = re.compile(r"(?:[!&]\S*+\s*+|#[^\n]*+\s*+)++")
# A key's properties on its own line, each a tag or an anchor ended by blanks or the line's end; and
# the colon that ends a plain key, the first one a blank or the line's end follows. Each is one
# match over the line, never one per property or per character: a frontmatter is read up to
# `fsops.REGULAR_READ_LIMIT`, and a pattern that rescans the rest of its line at every step takes
# hours over one long line of blanks or tags.
_PROPERTIES = re.compile(r"(?:[!&][^ \t]*+[ \t]*+)*+")
_KEY_END = re.compile(r":(?=[ \t]|\Z)")
# Where a comment starts on a line, a `#` after a blank.
_COMMENT = re.compile(r"[ \t]#")
# A character Python reads as a blank or a line break and YAML does not: YAML's blanks are a space
# and a tab and its line breaks LF and CR, though YAML 1.1, which PyYAML reads, also breaks a line
# at NEL, LS and PS (`_BREAKS`). To YAML 1.2 each is a character like a letter.
_ODD = re.compile(r"[^\S \t\n]")
_BREAKS = "\x85\u2028\u2029"
# A line's leading spaces, its blanks, and a line that holds something but a comment: each asked of
# a line or of a position in the text without copying either.
_SPACES = re.compile(r" *+")
_BLANKS = re.compile(r"[ \t]*+")
_CONTENT = re.compile(r"\s*+[^\s#]")
# The tabs that lead a line.
_LEADING_TABS = re.compile(r"^\t++", re.MULTILINE)
# The plain subset of YAML a frontmatter keeps to for this reader to answer "no" (`_plain`): lines
# holding a key with a plain name (`allowed-tools:`) and, on the same line, a plain scalar, a
# scalar quoted either way, a flow sequence of such scalars (`["Read", Grep]`, `_items`), the
# opening of a block scalar (`|`, `>`, with its indicators), or no value, the lines below it then
# nested; the same lines nested, indented by spaces, and sequence entries (`- `) holding one of them
# or a value; a block scalar's text; a key's flow sequence over lines, opened on its line or the
# next, every line below it indented deeper than the key; comments; blank lines; the first line a
# key's, at the first column. Outside it are a tag, an anchor, an alias, a merge key, an explicit
# `?` key, a quoted key, a flow mapping, a directive, a document marker, any other value over
# lines, a tab in a line's indentation, a lone CR and a character YAML's versions or Python read
# otherwise (`_UNPLAIN_CHARACTER`). Inside it, the top-level keys are the keys at the first column
# whichever version of YAML reads it and whichever of the two bounds below ends it: nothing in it
# can make another, and a frontmatter cut short at a `---` within a line holds fewer.
_PLAIN_KEY = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]*+:(?=[ \t]|\Z)")
# The sequence entries a nested line opens with (`- - x`), each a dash and blanks.
_ENTRIES = re.compile(r"(?:-[ ][ ]*+)*+")
_BLOCK_HEADER = re.compile(r"[|>](?:[1-9][+-]?|[+-][1-9]?)?")
# What ends a plain scalar inside a flow sequence otherwise than as one, a pair's colon or a
# comment.
_PAIR_OR_COMMENT = re.compile(r"[ \t]#|:(?:[ \t]|\Z)")
# An item of a flow sequence: a scalar quoted either way, or the run of a plain one, its blanks
# after it included, up to the first mark that ends it or opens something else.
_QUOTED_ITEM = re.compile(_QUOTED)
_PLAIN_ITEM = re.compile(r"[^,\[\]{}\"']*+")
# The characters that open a node other than a plain scalar, or end one in a flow collection.
_INDICATORS = "-?:,[]{}#&*!|>'\"%@`"
# Any character but a tab, LF and the printable ones that every reading takes for themselves: not a
# control character, nor one Python, YAML 1.1 or a JavaScript parser reads as a blank or a line
# break (NEL, LS, PS, the Unicode spaces), nor a byte-order mark, a surrogate or a non-character.
_UNPLAIN_CHARACTER = re.compile(
    "[^\t\n -~\xa1-\u167f\u1681-\u180d\u180f-\u1fff\u200b-\u2027\u202a-\u202e\u2030-\u205e"
    "\u2060-\u2fff\u3001-\ud7ff\ue000-\ufefe\uff00-\ufffd\U00010000-\U0010ffff]"
)
# Where a flow sequence of the subset stands at the end of a line (`_items`): closed by its `]`, or
# still open, an item last or a `[` or `,` last.
_Flow = Literal["]", "item", ","]
# What one line of the subset opens: a block scalar, whose text follows on deeper lines; a key with
# no value, whose flow sequence may open on the line below; a flow sequence left open, as it stands;
# or nothing that lines below it must be read otherwise for.
_Shape = Literal["line", "block", "key", "item", ","]


def _past(pattern: re.Pattern[str], text: str, start: int = 0) -> int:
    """Where `pattern`, which matches wherever it is asked, ends when asked at `start` in `text`."""
    found = pattern.match(text, start)
    return found.end() if found else start


def _unquoted(token: str) -> str:
    """A quoted scalar's text: single-quoted with `''` for a quote, or double-quoted with YAML's
    backslash escapes, an escape YAML does not have read as the character after the backslash."""
    body = token[1:-1]
    if token[0] == "'":
        return body.replace("''", "'")

    def escaped(match: re.Match[str]) -> str:
        code = match.group(1)
        if len(code) > 1:
            point = int(code[1:], 16)
            return chr(point) if point <= sys.maxunicode else ""
        return _ESCAPED.get(code, code)

    return _ESCAPE.sub(escaped, body)


def _block_key(line: str, *, continued: bool) -> str | None:
    """The key a block mapping's line opens with, or `None` for a line that opens none whole.

    Past an explicit-key `? ` and any tag (`!...`) or anchor (`&...`) ahead of the key; then a
    quoted key followed by a colon, or a plain one ending at the first colon followed by a blank or
    the end of the line. An explicit key needs no colon on its line and ends where a comment
    starts (`? hooks # why`), and is read only where no line below it is indented deeper
    (`continued`), which YAML reads as more of the key: the key itself after a `?` or a tag alone, a
    block scalar's text, or a plain key folded over lines. A quote that does not close on its line
    opens no key either."""
    explicit = line.startswith("?") and line[1:2] in ("", " ", "\t")
    rest = line[1:].lstrip(" \t") if explicit else line
    properties = _PROPERTIES.match(rest)
    rest = rest[properties.end() :] if properties else rest
    if explicit and continued:
        return None
    if rest[:1] in ('"', "'"):
        quoted = re.match(_QUOTED, rest)
        if quoted is None:
            return None
        after = rest[quoted.end() :].lstrip(" \t")
        return _unquoted(quoted.group()) if explicit or after.startswith(":") else None
    if explicit:
        comment = _COMMENT.search(rest)
        rest = rest[: comment.start()] if comment else rest
    colon = _KEY_END.search(rest)
    if colon is not None:
        return rest[: colon.start()].rstrip(" \t")
    return rest.rstrip(" \t") if explicit else None


def _flow_keys(text: str, start: int) -> set[str]:
    """The keys of the flow mapping that opens at `start` in `text`, at its top level and no deeper.

    Each is a scalar right after the mapping's `{` or a `,` at its own level, past any tag or
    anchor, and followed by a colon; quoted scalars are read whole, so a brace, a comma or `hooks:`
    inside one is text. Reading stops where the mapping closes."""
    keys: set[str] = set()
    depth: list[str] = []
    candidate: str | None = None
    at_key = False
    for token in _FLOW.finditer(text, start):
        kind, value = token.lastgroup, token.group()
        if kind in ("blank", "comment"):
            continue
        if kind == "indicator":
            if value in "{[":
                depth.append(value)
            elif value in "}]":
                del depth[-1:]
                if not depth:
                    break
            at_key = depth[-1:] == ["{"] and value in "{,"
            candidate = None
        elif kind == "colon":
            if candidate is not None and len(depth) == 1:
                keys.add(candidate)
            candidate, at_key = None, False
        elif at_key and kind == "plain" and value[0] in "!&":
            continue
        else:
            candidate = (_unquoted(value) if kind == "quoted" else value) if at_key else None
            at_key = False
    return keys


def _closes(text: str, start: int) -> int | None:
    """Where the flow collection that opens at `start` in `text` closes, just past its last
    bracket, or `None` where it does not close. Quoted scalars and comments are read whole, as
    `_flow_keys` reads them, so a bracket inside one closes nothing."""
    depth = 0
    for token in _FLOW.finditer(text, start):
        if token.lastgroup != "indicator" or token.group() == ",":
            continue
        depth += 1 if token.group() in "{[" else -1
        if depth == 0:
            return token.end()
    return None


def _keyed(text: str, start: int) -> bool:
    """Whether the flow mapping that opens at `start` in `text` is a key, a colon following where it
    closes (`{a: 1}: x`): then it is the first key of a block mapping, whose other keys are on the
    lines below, and not the frontmatter's whole node."""
    end = _closes(text, start)
    return end is not None and text.startswith(":", _past(_BLANKS, text, end))


def declares_hooks(text: str) -> bool | None:
    """Whether `text`, a skill, command or agent file, opens with a frontmatter holding a
    top-level `hooks` key; `None` where it cannot tell.

    The frontmatter is the lines between a first line of `---` and the next `---` line; without
    the closing one there is none. Line breaks are YAML's (LF, CRLF, a lone CR), and a byte-order
    mark ahead of the first line is read past.

    The answer is "no" only for a frontmatter inside the plain subset of YAML this reader reads
    exactly (`_plain`), none of whose keys at the first column is `hooks`. Any other is "yes" where
    a reading of it finds a top-level `hooks`, and "cannot tell" otherwise, so a frontmatter this
    reader may misread is named either way. So is one past `LINES_READ` or `CHARACTERS_READ`,
    which is not read.

    The readings: the frontmatter as bounded above, and as Claude Code bounds it, at the first `---`
    after the opening line wherever in a line that stands (`_harness_fenced`), as Claude Code
    2.1.293 was measured doing after a value on its line; each with every tab that leads a line read
    as two spaces too (`_untabbed`), as Claude Code 2.1.293 was measured reading a frontmatter
    indented by tabs throughout; and, where one holds a character Python reads as a blank or a line
    break and YAML does not, with each read as YAML 1.2 reads it, a character like a letter, and
    with NEL, LS and PS read as the line breaks YAML 1.1 reads them as. In each, the top level is
    the indentation of the first line that is neither blank nor a comment: a mapping in block style
    has its keys there, and one in flow style opens there with `{` (`_flow_keys`), behind any tag,
    anchor or comment and any tab after the indentation, unless a colon follows where it closes,
    which makes it a block mapping's first key. Behind a tag or an anchor alone on its line, a block
    mapping may start on a line below at an indentation of its own, and its keys are read there too.
    A key is `hooks` bare or quoted either way, its escapes read; nothing else of YAML is parsed."""
    start = 1 if text.startswith(chr(0xFEFF)) else 0
    fenced, harness = _fenced(text, start), _harness_fenced(text, start)
    ends = [bound[1] for bound in (fenced, harness) if bound is not None]
    if not ends:
        return False
    if max(ends) > CHARACTERS_READ:
        return None
    bounds = []
    if fenced is not None:
        end = fenced[1] - (2 if text.startswith("\r\n", fenced[1] - 2) else 1)
        body = _lines(text, fenced[0], max(fenced[0], end))
        lone_return = _LONE_RETURN.search(text, 0, fenced[1])
        if not lone_return and body.count("\n") < LINES_READ and _plain(body):
            return _holds_hooks(body)
        bounds.append(body)
    if harness is not None and (fenced is None or harness[1] != fenced[1]):
        bounds.append(_lines(text, *harness))
    return True if any(_holds_hooks(reading) for reading in _readings(bounds)) else None


def _plain(body: str) -> bool:
    """Whether a frontmatter's `body` keeps to the plain subset this reader reads exactly (see
    `_PLAIN_KEY`): every line blank, a comment, a block scalar's text below its opening, or one
    `_plain_line` admits, the first of those a key's at the first column."""
    first = True
    scalar: int | None = None
    # The column of the key on the line before, where that key has no value, and that of the key
    # whose flow sequence is open, with where the sequence stands.
    keyed: int | None = None
    sequence: tuple[int, _Flow] | None = None
    for line in body.split("\n"):
        rest = line.lstrip(" ")
        indent = len(line) - len(rest)
        if rest.startswith("\t") or _UNPLAIN_CHARACTER.search(rest):
            return False
        opener, keyed = keyed, None
        if sequence is not None:
            if not rest or indent <= sequence[0]:
                return False
            flow = _items(line, indent, sequence[1])
            if flow is None:
                return False
            sequence = None if flow == "]" else (sequence[0], flow)
            continue
        if not rest or (scalar is not None and indent > scalar):
            continue
        scalar = None
        if rest.startswith("#"):
            continue
        if opener is not None and indent > opener and rest.startswith("["):
            flow = _items(line, indent + 1, ",")
            if flow is None:
                return False
            sequence = None if flow == "]" else (opener, flow)
            continue
        shape = _plain_line(rest, first=first)
        if shape is None or (first and indent):
            return False
        first = False
        column = indent + _past(_ENTRIES, rest)
        if shape == "block":
            scalar = indent
        elif shape == "key":
            keyed = column
        elif shape == "item" or shape == ",":
            sequence = (column, shape)
    return sequence is None


def _plain_line(rest: str, *, first: bool) -> _Shape | None:
    """What a line of the plain subset opens, `rest` being the line past its indentation, or `None`
    for one outside it: a plain key and a value or nothing, or, on any line but the first,
    sequence entries ahead of either or of a value alone, which leaves no flow sequence open."""
    entries = _ENTRIES.match(rest)
    item = rest[entries.end() :] if entries else rest
    if first and item != rest:
        return None
    key = _PLAIN_KEY.match(item)
    if key is not None:
        value = item[key.end() :].lstrip(" \t")
        return "key" if not value or value.startswith("#") else _plain_value(value)
    if first or (item == rest and item != "-"):
        return None
    if item in ("", "-") or item.startswith("#"):
        return "line"
    shape = _plain_value(item)
    return shape if shape in ("line", "block") else None


def _plain_value(value: str) -> _Shape | None:
    """What a value of the plain subset opens, or `None` for one outside it: a block scalar's
    opening with its indicators, a scalar quoted either way and closed on its line, a flow sequence
    (`_items`), or a plain scalar, each with nothing after it but a comment."""
    if value[0] in "|>":
        header = _BLOCK_HEADER.match(value)
        return "block" if header and _ends(value[header.end() :]) else None
    if value[0] in "\"'":
        quoted = re.match(_QUOTED, value)
        return "line" if quoted and _ends(value[quoted.end() :]) else None
    if value[0] == "[":
        flow = _items(value, 1, ",")
        return "line" if flow == "]" else flow
    return "line" if _plain_scalar(value, flow=False) else None


def _items(line: str, start: int, last: _Flow) -> _Flow | None:
    """Where a flow sequence of the subset stands at the end of `line`, read from `start` with
    `last` last in it before; `None` where the line holds anything else.

    Its items are scalars quoted either way and closed on their line, and plain scalars with no
    pair's colon or comment in them, so nothing in it is nested; an item is followed by a `,` or
    the `]`, here or on a line below, and the `]` by nothing but a comment."""
    position = _past(_BLANKS, line, start)
    while position < len(line):
        mark = line[position]
        if mark == "]":
            return "]" if _ends(line[position + 1 :]) else None
        if mark == ",":
            last, position = ",", position + 1
        elif last == "item":
            return None
        elif mark in "\"'":
            quoted = _QUOTED_ITEM.match(line, position)
            if quoted is None:
                return None
            last, position = "item", quoted.end()
        else:
            plain = _PLAIN_ITEM.match(line, position)
            scalar = plain.group().rstrip(" \t") if plain else ""
            if not scalar or not _plain_scalar(scalar, flow=True):
                return None
            last, position = "item", position + len(scalar)
        position = _past(_BLANKS, line, position)
    return last


def _plain_scalar(scalar: str, *, flow: bool) -> bool:
    """Whether `scalar` opens a plain scalar, and, in a flow sequence, is one whole: no pair's colon
    and no comment in it."""
    opens = scalar[0] not in _INDICATORS or (
        scalar[0] in "-?:" and scalar[1:2] not in ("", " ", "\t")
    )
    return opens and not (flow and _PAIR_OR_COMMENT.search(scalar))


def _ends(after: str) -> bool:
    """Whether what follows a value on its line is nothing but blanks and a comment."""
    rest = after.lstrip(" \t")
    return not rest or (rest.startswith("#") and rest != after)


def _readings(bounds: list[str]) -> Iterator[str]:
    """Each reading of a frontmatter outside the plain subset (`declares_hooks`), one at a time, so
    that no reading is held while another is read."""
    for body in bounds:
        if body.count("\n") >= LINES_READ:
            continue
        yield from _repaired(body)
        # Read again where a line holds a character Python takes for a blank or a line break and
        # YAML does not: as YAML 1.2 reads it, a character like a letter (`&a\u3000b {hooks: x}` is
        # one anchor ahead of a flow mapping), and as YAML 1.1 reads NEL, LS and PS, a line break.
        # Each is one `translate` of the text, which keeps no record per character replaced.
        odd = {ord(found.group()): "_" for found in _ODD.finditer(body)}
        if odd:
            yield from _repaired(body.translate(odd))
            breaks = {code: "\n" for code in odd if chr(code) in _BREAKS}
            if breaks:
                broken = body.translate(odd | breaks)
                if broken.count("\n") < LINES_READ:
                    yield from _repaired(broken)


def _repaired(body: str) -> Iterator[str]:
    r"""`body`, and, wherever a tab leads a line, `body` repaired of its leading tabs: a tab ahead
    of a line holding only a tag (`\t!!map`) moves the top indentation onto the keys below it, as
    one ahead of a key does."""
    yield body
    if body.startswith("\t") or "\n\t" in body:
        yield _untabbed(body)


def _fenced(text: str, first: int) -> tuple[int, int] | None:
    """Where the frontmatter between a line of `---` at `first` in the text and the next `---` line
    starts, and where that next line starts; `None` without it. The frontmatter is the text
    between, the line break ahead of the closing line left out."""
    opening = _OPENING_LINE.match(text, first)
    if opening is None:
        return None
    closing = _CLOSING_LINE.search(text, opening.end())
    if closing is None:
        return None
    return opening.end(), closing.start()


def _harness_fenced(text: str, first: int) -> tuple[int, int] | None:
    """Where the frontmatter as Claude Code is read to bound it starts and ends in the text, where
    its closing `---` starts: past a `---` at `first` and the blanks and line breaks after it, to
    the first `---` after them, wherever in a line that stands; `None` without one. It and
    `_fenced` differ only where a `---` stands anywhere but alone on its line."""
    opening = _OPENING.match(text, first)
    if opening is None:
        return None
    last = max(text.rfind("\n", first, opening.end()), text.rfind("\r", first, opening.end()))
    end = text.find(_FENCE, last + 1) if last >= 0 else -1
    return None if end < 0 else (last + 1, end)


def _lines(text: str, start: int, end: int) -> str:
    """The text from `start` to `end`, each CRLF and each lone CR in it read as an LF: only what a
    reading reads is copied, never the whole file, whose CRLFs would cost a copy of it."""
    return text[start:end].replace("\r\n", "\n").replace("\r", "\n")


def _untabbed(body: str) -> str:
    """`body` with each tab that leads a line read as two spaces, as Claude Code is read to repair
    a frontmatter that does not parse before it parses it again."""
    return _LEADING_TABS.sub(lambda tabs: "  " * len(tabs.group()), body)


def _holds_hooks(body: str) -> bool:
    """Whether a frontmatter's `body` holds a top-level `hooks` key, as `declares_hooks` reads one.

    The node is read where it stands in `body`, never in a copy of the text from there on: a
    reading is up to `CHARACTERS_READ` long, and each copy of it would cost as much again."""
    lines = body.split("\n")
    first = next((index for index, line in enumerate(lines) if _CONTENT.match(line)), None)
    if first is None:
        return False
    content = [line for line in lines[first:] if _CONTENT.match(line)]
    indent = _past(_SPACES, content[0])
    start = sum(map(len, lines[:first])) + first + indent
    ahead = _AHEAD.match(body, start)
    node = ahead.end() if ahead else start
    # A flow mapping is read past every property and comment ahead of it, in any order, and past a
    # tab after the first line's spaces, which YAML 1.2 reads as a blank ahead of the node and not
    # as indentation (`  \t{hooks: x}`).
    bare = _past(_BLANKS, body, start)
    past = _PROPERTY_RUN.match(body, bare)
    end = past.end() if past else bare
    keys: set[str] = set()
    if body.startswith("{", end) and not _keyed(body, end):
        keys = _flow_keys(body, end)
    # The block reading is passed over only where the node is a flow mapping behind properties and
    # then comments (`_AHEAD`). Where only the reading past a comment among the properties, or past
    # a tab, finds one, which YAML parsers do not all read alike, the block reading is kept beside
    # it, so that each reading only adds keys.
    if not body.startswith("{", node) or _keyed(body, node):
        # Past a tag or an anchor alone on its line (`!!map`), the mapping starts on a line below,
        # so its keys may stand at the indentation of any line of that run.
        run = _PROPERTY_RUN.match(body, start)
        spanned = lines[first + 1 : first + 1 + body.count("\n", start, run.end())] if run else []
        starts = {_past(_SPACES, line) for line in spanned if _CONTENT.match(line)}
        keys = keys | _block_keys(content, {indent} | starts)
    return _HOOKS in keys


def _block_keys(content: list[str], indents: set[int]) -> set[str]:
    """The keys of a block mapping whose keys stand at one of `indents` among a frontmatter's
    `content` lines (`_block_key`).

    Every line at such an indentation is read for a key, a line inside a quoted scalar or a flow
    collection over lines included: `description: "a` and then `hooks: x"` names the file. Telling
    such a line from a key means parsing every value above it, a nested one among them, and a
    reader that guesses wrong there skips a real `hooks` key below, so this one reads the line and
    errs toward naming the file."""
    keys: set[str] = set()
    for index, line in enumerate(content):
        indent = len(line) - len(line.lstrip(" "))
        if indent not in indents:
            continue
        below = content[index + 1 : index + 2]
        continued = any(len(deeper) - len(deeper.lstrip(" ")) > indent for deeper in below)
        key = _block_key(line[indent:], continued=continued)
        if key is not None:
            keys.add(key)
    return keys
