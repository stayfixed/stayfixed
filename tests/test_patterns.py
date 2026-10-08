"""Every regular expression the package compiles at import, in a shape every supported Python
reads alike.

A possessive repeat (`*+`, `++`) is how a pattern here reads a long run without the record `re`
keeps for each pass of a repeated group, and Python 3.11.0 to 3.11.4 misread some of them: after a
pass of a possessive group fails, the match goes on from wherever the pass's last repeat, choice or
lookahead left off rather than from where the pass began (fixed in 3.11.5, gh-100061 and
gh-106052). So `docs/` read as a path, and `{hooks: x}` held no key. CONTRIBUTING.md ("Tests")
states the shape that reads alike everywhere; this holds every pattern to it, and the
`checks (ubuntu-latest, 3.11.4)` leg runs the readers' own tests where the bug lives.
"""

from __future__ import annotations

import importlib
import pkgutil
import re
from typing import Any

import pytest

import stayfixed

# `re`'s own parser, private and the same from 3.11 to 3.14. It gives the shape the engine runs:
# a prefix every alternative shares is taken out ahead of the choice (`cd|cxb` is `c(?:d|xb)`),
# which puts a choice inside the pass, so the source text alone would misjudge it.
_PARSER: Any = importlib.import_module("re._parser")
_OP: Any = importlib.import_module("re._constants")
_ONE_CHARACTER = {_OP.LITERAL, _OP.NOT_LITERAL, _OP.IN, _OP.ANY}
_REPEATS = {_OP.MAX_REPEAT, _OP.MIN_REPEAT, _OP.POSSESSIVE_REPEAT}


def _one_character(item: tuple[Any, Any]) -> bool:
    return item[0] in _ONE_CHARACTER


def _repeat_of_one(item: tuple[Any, Any]) -> bool:
    if item[0] not in _REPEATS:
        return False
    body = list(item[1][2])
    return len(body) == 1 and _one_character(body[0])


def _reads_alike(alternative: list[tuple[Any, Any]]) -> bool:
    """Whether a pass can fail only before anything in it but single characters and anchors: a
    repeat of one character alone, or characters and anchors followed by repeats of one
    character that may match nothing, which cannot fail."""
    if len(alternative) == 1 and _repeat_of_one(alternative[0]):
        return True
    rest = alternative
    while rest and (_one_character(rest[0]) or rest[0][0] is _OP.AT):
        rest = rest[1:]
    return all(_repeat_of_one(item) and item[1][0] == 0 for item in rest)


def _passes(body: list[tuple[Any, Any]]) -> list[list[tuple[Any, Any]]]:
    """The alternatives a pass of a repeated `body` may take, through one group or one choice."""
    if len(body) == 1 and body[0][0] is _OP.SUBPATTERN:
        return _passes(list(body[0][1][3]))
    if len(body) == 1 and body[0][0] is _OP.BRANCH:
        return [list(alternative) for alternative in body[0][1][1]]
    return [body]


def offences(items: Any) -> list[str]:
    """What in a parsed pattern is read otherwise by Python 3.11.0 to 3.11.4, or is an atomic
    group, which keeps the record a possessive repeat exists to drop."""
    found: list[str] = []
    for op, value in items:
        if op is _OP.ATOMIC_GROUP:
            found.append("an atomic group")
            found += offences(value)
        elif op in _REPEATS:
            body = list(value[2])
            if (
                op is _OP.POSSESSIVE_REPEAT
                and not _repeat_of_one((op, value))
                and not all(_reads_alike(alternative) for alternative in _passes(body))
            ):
                found.append("a possessive repeat of a group that can fail past its first run")
            found += offences(body)
        elif op is _OP.SUBPATTERN:
            found += offences(value[3])
        elif op is _OP.BRANCH:
            for alternative in value[1]:
                found += offences(alternative)
        elif op in (_OP.ASSERT, _OP.ASSERT_NOT):
            found += offences(value[1])
        elif op is _OP.GROUPREF_EXISTS:
            found += offences(value[1])
            if value[2] is not None:
                found += offences(value[2])
    return found


def _offences_of(pattern: re.Pattern[str]) -> list[str]:
    return offences(_PARSER.parse(pattern.pattern, pattern.flags))


# The checker's own table, each shape with what it must say, from what Python 3.11.4 was measured
# to misread against 3.14: a pass that fails at or after a repeat, a lookahead or a choice it has
# entered, and the choice the parser builds out of a shared prefix. The shapes it admits are the
# ones this package uses, and a random fuzz of 50,000 patterns of those shapes against 3.14 found
# no difference on 3.11.4 where 10,000 of 50,000 unconstrained ones differed.
SHAPES = {
    r"(?:ab++)*+": False,
    r"(?:ab+)*+c": False,
    r"(?:ab?c)*+": False,
    r"(?:a(?!x)b)*+": False,
    r"(?:a(?=b)b)*+": False,
    r"(?:a(?:b|\Z))*+": False,
    r"(?:cd|cxb)*+c": False,
    r"(?:\.[a-z]++)++": False,
    r"(?>a+)": False,
    r"(?:x(?>a))*": False,
    r"[ab]*+": True,
    r"\s++": True,
    r"(?:''[^']*+)*+": True,
    r"(?:[^\"\\]++|\\.)*+": True,
    r"(?:[,\s]|\band\b|\bor\b)*+": True,
    r"(?:\.[a-z][a-z]*+)++": True,
    r"(?:[!&]\S*+\s*+|#[^\n]*+\s*+)++": True,
    r"(?:ab+)*": True,
}


@pytest.mark.parametrize("shape", sorted(SHAPES))
def test_the_shape_check_tells_what_python_3_11_4_misreads(shape: str) -> None:
    # The check below is only as good as this table: each row that should be refused fails it if
    # the check stops looking at that part of a pass, and each that should pass fails it if the
    # check refuses more than it must. No mutation is declared for it: the rows are its oracle.
    assert (not _offences_of(re.compile(shape))) is SHAPES[shape]


def _compiled() -> dict[str, re.Pattern[str]]:
    """Every pattern a module of the package holds at its top level, under the first name it was
    met by: one imported by another module is the same object, judged once."""
    patterns: dict[str, re.Pattern[str]] = {}
    for module in pkgutil.walk_packages(stayfixed.__path__, "stayfixed."):
        if module.name.endswith(".__main__"):
            continue
        for name, value in vars(importlib.import_module(module.name)).items():
            if (
                isinstance(value, re.Pattern)
                and isinstance(value.pattern, str)
                and all(value is not seen for seen in patterns.values())
            ):
                patterns[f"{module.name}.{name}"] = value
    return patterns


def test_no_pattern_repeats_a_group_in_a_shape_python_3_11_4_misreads() -> None:
    # Every pattern compiled at a module's top level, which is every one the package keeps; one a
    # function compiles from text it is handed is outside the walk. Mutations (oracle):
    # `mutations/`'s "the path grammar repeats its segments possessively", "a symbol path's parts
    # are a possessive repeat", "a flow mapping's plain scalar is a possessive repeat", "a footer's
    # words are a possessive repeat", "an owner's labels open on their possessive run", "a model's
    # words open on their possessive run", "the blanks after a frontmatter property may fail" ->
    # each reddens this.
    patterns = _compiled()
    assert len(patterns) > 50  # a walk-based assertion states its walk is non-empty
    found = {name: said for name, pattern in patterns.items() if (said := _offences_of(pattern))}
    assert found == {}
