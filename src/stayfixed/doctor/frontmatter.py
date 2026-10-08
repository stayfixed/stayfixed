"""Whether a Markdown file's YAML frontmatter declares hooks: text in, an answer out.

`hook-entries` names each skill, command or agent file whose frontmatter holds a top-level `hooks`
key: `doctor.hooked` finds the files and reads them, and `doctor.entries` tells the row. This module
answers that one question of a file's text and reads nothing else, no file and no YAML beyond the
keys it looks for. The runtime imports only the standard library (CONTRIBUTING.md), so there is no
YAML parser to hand the text to, and the reader below is written for the one key it finds.
"""

from __future__ import annotations

import re
import sys

# The line that opens a frontmatter and the next one that closes it.
_FENCE = "---"
# The fence that opens a frontmatter as Claude Code is read to find one, and the blanks and line
# breaks after it, taken whole so that the text is scanned once.
_OPENING = re.compile(r"---[\s\ufeff]*+")
# A key quoted either way: double, with backslash escapes, or single, with `''` for a quote.
#
# Every repetition in this module's patterns that a long value can reach is possessive (`*+`, `++`):
# Python's `re` keeps a record for each pass of a repeated group in case it has to give the pass
# back, hundreds of bytes per character of one long value, so a file at `fsops.REGULAR_READ_LIMIT`
# asked gigabytes of one `doctor` run. A possessive repetition gives nothing back and keeps no
# record. None of them changes what is matched, since nothing after one could take back what it
# read, with one exception: a single-quoted scalar whose quotes never pair up as YAML reads them,
# which giving back ended at its last `''`. The second single-quoted alternative ends it there, in
# one scan.
_DOUBLE_QUOTED = r'"(?:[^"\\]++|\\.)*+"'
_SINGLE_QUOTED = r"'[^']*+(?:''[^']*+)*+'|'[\s\S]*'(?=')"
_QUOTED = f"{_DOUBLE_QUOTED}|{_SINGLE_QUOTED}"
# One token of a flow mapping (`{name: x, hooks: {...}}`): a quoted scalar, a flow indicator, a
# comment, blanks, a plain scalar -- which holds a `:` not followed by a blank or an indicator, and
# a `#` not after a blank -- or a colon. Whatever else a line holds is one character at a time.
_FLOW = re.compile(
    rf"(?P<quoted>{_QUOTED})|(?P<indicator>[{{}}\[\],])|(?P<comment>#[^\n]*)|(?P<blank>\s+)"
    r"|(?P<plain>[^\s{}\[\],:#\"'](?:[^\s{}\[\],:]|:(?![\s{}\[\],]|$))*+)|(?P<colon>:)|(?P<other>.)",
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
# any comment lines. A flow mapping behind them is still a flow mapping.
_AHEAD = re.compile(r"(?:[!&]\S*+(?:\s++|\Z))++(?:#[^\n]*+(?:\n\s*+|\Z))*+")
# A key's properties on its own line, each a tag or an anchor ended by blanks or the line's end; and
# the colon that ends a plain key, the first one a blank or the line's end follows. Each is one
# match over the line, never one per property or per character: a frontmatter is read up to
# `fsops.REGULAR_READ_LIMIT`, and a pattern that rescans the rest of its line at every step takes
# hours over one long line of blanks or tags.
_PROPERTIES = re.compile(r"(?:[!&][^ \t]*+(?:[ \t]++|\Z))*+")
_KEY_END = re.compile(r":(?=[ \t]|\Z)")


class _Untold:
    """The answer `_block_key` gives for a key it cannot read whole (`_UNTOLD`)."""


# A key this reader cannot read whole, which may be `hooks` for all it can tell: an alias, which
# stands for whatever its anchor named; a merge key (`<<`, plain), which a reader that honours it
# reads as every key of the mapping it names; an explicit `? ` key that is not all on its line; and
# a quoted key over several lines, which YAML folds into one.
_UNTOLD = _Untold()
_MERGE = "<<"


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


def _block_key(line: str, *, continued: bool) -> str | _Untold | None:
    """The key a block mapping's line opens with, `None` for a line that opens none, or `_UNTOLD`
    for a key the line does not hold whole.

    Past an explicit-key `? ` and any tag (`!...`) or anchor (`&...`) ahead of the key; then a
    quoted key followed by a colon, or a plain one ending at the first colon followed by a blank or
    the end of the line. An explicit key needs no colon on its line, and is read only where no line
    below it is indented deeper (`continued`), which YAML reads as more of the key: the key itself
    after a `?` or a tag alone, a block scalar's text, or a plain key folded over lines. An alias
    (`*name`), a plain merge key (`<<`) and a quote that does not close on its line are not read
    either."""
    explicit = line.startswith("?") and line[1:2] in ("", " ", "\t")
    rest = line[1:].lstrip(" \t") if explicit else line
    properties = _PROPERTIES.match(rest)
    rest = rest[properties.end() :] if properties else rest
    if rest[:1] == "*" or (explicit and continued):
        return _UNTOLD
    if rest[:1] in ('"', "'"):
        quoted = re.match(_QUOTED, rest)
        if quoted is None:
            return _UNTOLD
        after = rest[quoted.end() :].lstrip(" \t")
        return _unquoted(quoted.group()) if explicit or after.startswith(":") else None
    colon = _KEY_END.search(rest)
    if colon is not None:
        key = rest[: colon.start()].rstrip(" \t")
    elif explicit:
        key = rest.rstrip(" \t")
    else:
        return None
    return _UNTOLD if key == _MERGE else key


def _flow_keys(text: str) -> tuple[set[str], bool]:
    """The keys of the flow mapping `text` opens with, at its top level and no deeper, and whether
    any key there is one this reader cannot read whole.

    Each is a scalar right after the mapping's `{` or a `,` at its own level, past any tag or
    anchor, and followed by a colon; quoted scalars are read whole, so a brace, a comma or `hooks:`
    inside one is text. An alias, a plain merge key (`<<`), an explicit `?` key and a quoted key
    over several lines are keys it cannot read (`_UNTOLD`). Reading stops where the mapping
    closes."""
    keys: set[str] = set()
    depth: list[str] = []
    candidate: str | None = None
    at_key = False
    untold = False
    for token in _FLOW.finditer(text):
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
            if at_key and len(depth) == 1:
                untold = untold or (
                    (kind == "plain" and (value == "?" or value[0] == "*"))
                    or (kind == "plain" and value == _MERGE)
                    or (kind == "quoted" and "\n" in value)
                )
            candidate = (_unquoted(value) if kind == "quoted" else value) if at_key else None
            at_key = False
    return keys, untold


def _closes(text: str) -> int | None:
    """Where the flow collection `text` opens with closes, just past its last bracket, or `None`
    where it does not close. Quoted scalars and comments are read whole, as `_flow_keys` reads
    them, so a bracket inside one closes nothing."""
    depth = 0
    for token in _FLOW.finditer(text):
        if token.lastgroup != "indicator" or token.group() == ",":
            continue
        depth += 1 if token.group() in "{[" else -1
        if depth == 0:
            return token.end()
    return None


def _keyed(node: str) -> bool:
    """Whether the flow mapping `node` opens with is a key, a colon following where it closes
    (`{a: 1}: x`): then it is the first key of a block mapping, whose other keys are on the lines
    below, and not the frontmatter's whole node."""
    end = _closes(node)
    return end is not None and node[end:].lstrip(" \t").startswith(":")


def declares_hooks(text: str) -> bool | None:
    """Whether `text`, a skill, command or agent file, opens with a frontmatter holding a
    top-level `hooks` key; `None` where it cannot tell.

    The frontmatter is the lines between a first line of `---` and the next `---` line; without
    the closing one there is none. Line breaks are YAML's (LF, CRLF, a lone CR) and no other, and
    a byte-order mark ahead of the first line is read past. Its top level is the indentation of its
    first line that is neither blank nor a comment: a mapping in block style has its keys there,
    and one in flow style opens there with `{` (`_flow_keys`), behind any tag or anchor, unless a
    colon follows where it closes, which makes it a block mapping's first key. A key is `hooks`
    bare or quoted either way, its escapes read; nothing else of YAML is parsed.

    Claude Code may read the file otherwise, by what its program text shows rather than by a
    measured run: it may end the frontmatter at the first `---` after the opening line, wherever in
    a line that stands (`_harness_fenced`), and read a line indented by tabs as one indented by
    spaces (`_untabbed`). Where either reading may differ from this one, each is read, and the
    answer is "yes" if any of them holds `hooks` and "cannot tell" otherwise.

    It fails toward "cannot tell", never toward "no": a top-level key it cannot read whole
    (`_UNTOLD`) may be `hooks`, so where no key it reads is, the answer is `None`."""
    text = text.removeprefix(chr(0xFEFF)).replace("\r\n", "\n").replace("\r", "\n")
    fenced, harness = _fenced(text.split("\n")), _harness_fenced(text)
    readings = [fenced[0]] if fenced else []
    unsure = harness is not None and (fenced is None or harness[1] != fenced[1])
    if harness is not None and unsure:
        readings.append(harness[0].split("\n"))
    for lines in list(readings):
        if _tab_indents_a_key(lines):
            unsure = True
            readings.append(_untabbed(lines))
    answers = [_holds_hooks(lines) for lines in readings]
    if True in answers:
        return True
    if unsure:
        return None
    return answers[0] if answers else False


def _fenced(lines: list[str]) -> tuple[list[str], int] | None:
    """The frontmatter's lines between a first line of `---` and the next `---` line, and where
    the closing line starts in the text; `None` without the closing one."""
    if lines[0].rstrip() != _FENCE:
        return None
    start = 0
    for end, line in enumerate(lines[1:], 1):
        start += len(lines[end - 1]) + 1
        if line.rstrip() == _FENCE:
            return lines[1:end], start
    return None


def _harness_fenced(text: str) -> tuple[str, int] | None:
    """The frontmatter as Claude Code is read to bound it, and where its closing `---` starts:
    past a `---` that opens the text and the blanks and line breaks after it, to the first `---`
    after them, wherever in a line that stands; `None` without one. It and `_fenced` differ only
    where a `---` stands anywhere but alone on its line."""
    opening = _OPENING.match(text)
    if opening is None or "\n" not in opening.group():
        return None
    start = opening.start() + opening.group().rindex("\n") + 1
    end = text.find(_FENCE, start)
    return None if end < 0 else (text[start:end], end)


def _tab_indents_a_key(lines: list[str]) -> bool:
    """Whether a line's indentation holds a tab, which YAML does not take as indentation, and the
    line past it opens a key, which a reader taking the tab as indentation reads."""
    for line in lines:
        rest = line.lstrip(" \t")
        if "\t" in line[: len(line) - len(rest)] and _block_key(rest, continued=False) is not None:
            return True
    return False


def _untabbed(lines: list[str]) -> list[str]:
    """`lines` with each tab that leads a line read as two spaces, as Claude Code is read to
    repair a frontmatter that does not parse before it parses it again."""
    return ["  " * (len(line) - len(line.lstrip("\t"))) + line.lstrip("\t") for line in lines]


def _holds_hooks(lines: list[str]) -> bool | None:
    """Whether a frontmatter's `lines` hold a top-level `hooks` key, as `declares_hooks` reads
    one, or `None` where a key it cannot read leaves that open."""
    content = [line for line in lines if line.strip() and not line.lstrip().startswith("#")]
    if not content:
        return False
    indent = len(content[0]) - len(content[0].lstrip(" "))
    opened = "\n".join(lines[lines.index(content[0]) :])[indent:]
    ahead = _AHEAD.match(opened)
    node = opened[ahead.end() :] if ahead else opened
    if node.startswith("{") and not _keyed(node):
        keys, untold = _flow_keys(node)
    else:
        keys, untold = _block_keys(content, indent)
    if _HOOKS in keys:
        return True
    return None if untold else False


def _block_keys(content: list[str], indent: int) -> tuple[set[str], bool]:
    """The keys of a block mapping whose keys stand at `indent` among a frontmatter's `content`
    lines, and whether any is one this reader cannot read whole (`_block_key`).

    Every line at that indentation is read for a key, a line inside a quoted scalar or a flow
    collection over lines included: `description: "a` and then `hooks: x"` names the file. Telling
    such a line from a key means parsing every value above it, a nested one among them, and a
    reader that guesses wrong there skips a real `hooks` key below, so this one reads the line and
    errs toward naming the file."""
    keys: set[str] = set()
    untold = False
    for index, line in enumerate(content):
        if len(line) - len(line.lstrip(" ")) != indent:
            continue
        below = content[index + 1 : index + 2]
        continued = any(len(deeper) - len(deeper.lstrip(" ")) > indent for deeper in below)
        key = _block_key(line[indent:], continued=continued)
        if isinstance(key, str):
            keys.add(key)
        untold = untold or key is _UNTOLD
    return keys, untold
