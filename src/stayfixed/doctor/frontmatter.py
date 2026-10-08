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
# A key quoted either way: double, with backslash escapes, or single, with `''` for a quote.
_QUOTED = r'"(?:[^"\\]|\\.)*"|\'(?:[^\']|\'\')*\''
# One token of a flow mapping (`{name: x, hooks: {...}}`): a quoted scalar, a flow indicator, a
# comment, blanks, a plain scalar -- which holds a `:` not followed by a blank or an indicator, and
# a `#` not after a blank -- or a colon. Whatever else a line holds is one character at a time.
_FLOW = re.compile(
    rf"(?P<quoted>{_QUOTED})|(?P<indicator>[{{}}\[\],])|(?P<comment>#[^\n]*)|(?P<blank>\s+)"
    r"|(?P<plain>[^\s{}\[\],:#\"'](?:[^\s{}\[\],:]|:(?![\s{}\[\],]|$))*)|(?P<colon>:)|(?P<other>.)",
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
_AHEAD = re.compile(r"(?:[!&]\S*(?:\s+|\Z))+(?:#[^\n]*(?:\n\s*|\Z))*")


class _Untold:
    """The answer `_block_key` gives for a key it cannot read whole (`_UNTOLD`)."""


# A key this reader cannot read whole, which may be `hooks` for all it can tell: an alias, which
# stands for whatever its anchor named; an explicit `? ` key that is not all on its line; and a
# quoted key over several lines, which YAML folds into one.
_UNTOLD = _Untold()


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
    (`*name`) and a quote that does not close on its line are not read either."""
    explicit = line.startswith("?") and line[1:2] in ("", " ", "\t")
    rest = line[1:].lstrip(" \t") if explicit else line
    while rest[:1] in ("!", "&"):
        parts = re.split(r"[ \t]+", rest, maxsplit=1)
        rest = parts[1] if len(parts) == 2 else ""
    if rest[:1] == "*" or (explicit and continued):
        return _UNTOLD
    if rest[:1] in ('"', "'"):
        quoted = re.match(_QUOTED, rest)
        if quoted is None:
            return _UNTOLD
        after = rest[quoted.end() :].lstrip(" \t")
        return _unquoted(quoted.group()) if explicit or after.startswith(":") else None
    plain = re.match(r"([^\n]*?)[ \t]*:(?:[ \t]|$)", rest)
    if plain is not None:
        return plain.group(1)
    return rest.rstrip(" \t") if explicit else None


def _flow_keys(text: str) -> tuple[set[str], bool]:
    """The keys of the flow mapping `text` opens with, at its top level and no deeper, and whether
    any key there is one this reader cannot read whole.

    Each is a scalar right after the mapping's `{` or a `,` at its own level, past any tag or
    anchor, and followed by a colon; quoted scalars are read whole, so a brace, a comma or `hooks:`
    inside one is text. An alias, an explicit `?` key and a quoted key over several lines are keys
    it cannot read (`_UNTOLD`). Reading stops where the mapping closes."""
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
                    or (kind == "quoted" and "\n" in value)
                )
            candidate = (_unquoted(value) if kind == "quoted" else value) if at_key else None
            at_key = False
    return keys, untold


def declares_hooks(text: str) -> bool | None:
    """Whether `text`, a skill, command or agent file, opens with a frontmatter holding a
    top-level `hooks` key; `None` where it cannot tell.

    The frontmatter is the lines between a first line of `---` and the next `---` line; without
    the closing one there is none. Line breaks are YAML's (LF, CRLF, a lone CR) and no other, and
    a byte-order mark ahead of the first line is read past. Its top level is the indentation of its
    first line that is neither blank nor a comment: a mapping in block style has its keys there,
    and one in flow style opens there with `{` (`_flow_keys`), behind any tag or anchor. A key is
    `hooks` bare or quoted either way, its escapes read; nothing else of YAML is parsed.

    It fails toward "cannot tell", never toward "no": a top-level key it cannot read whole
    (`_UNTOLD`) may be `hooks`, so where no key it reads is, the answer is `None`."""
    lines = text.removeprefix(chr(0xFEFF)).replace("\r\n", "\n").replace("\r", "\n").split("\n")
    if lines[0].rstrip() != _FENCE:
        return False
    for end, line in enumerate(lines[1:], 1):
        if line.rstrip() == _FENCE:
            return _holds_hooks(lines[1:end])
    return False


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
    if node.startswith("{"):
        keys, untold = _flow_keys(node)
    else:
        keys, untold = set(), False
        for index, line in enumerate(content):
            if len(line) - len(line.lstrip(" ")) != indent:
                continue
            below = content[index + 1 : index + 2]
            continued = any(len(deeper) - len(deeper.lstrip(" ")) > indent for deeper in below)
            key = _block_key(line[indent:], continued=continued)
            if isinstance(key, str):
                keys.add(key)
            untold = untold or key is _UNTOLD
    if _HOOKS in keys:
        return True
    return None if untold else False
