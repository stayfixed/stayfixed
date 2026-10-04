"""The advisory memory link graph: every `[[link]]` resolves to a document in the store, no link is
immediately repeated, no ledger identifier is bracketed. Advice, never a verdict: the store is
shared by every session on the machine, so `memory refs` reports these as notices that never
change its exit code.

The wiki-link pattern is defined here, as the link graph's own grammar, and `memory.refs` reads it
for its audience check; the identifier grammar is `stayfixed.identifiers`, and what counts as prose
is `stayfixed.prose`'s. The notes come from the walk `memory.refs` already made for its own
findings, so `memory refs` reads the store once.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from stayfixed.findings import Finding
from stayfixed.identifiers import identifiers
from stayfixed.prose import blank_code_spans, blank_fences

if TYPE_CHECKING:
    from stayfixed.config.schema import Config
    from stayfixed.memory.notes import Walk
    from stayfixed.memory.store import Store

# `[[name]]` addresses a note by its stem: the one spelling, which `memory.refs` reads rather than
# respelling it.
WIKI_LINK = re.compile(r"\[\[([^\]]+)\]\]")

# Lookahead, not a plain pair match: findall consumes without overlap, so in `[[a]] [[b]] [[b]]`
# the a-b pair would eat the left half of the real b-b pair. The separator class covers the
# list forms a bulk repoint collapses into: `, `, `, and `, ` or `. Built from `WIKI_LINK` so
# the two cannot disagree about what a link is.
_REPEAT = re.compile(rf"{WIKI_LINK.pattern}(?:[,\s]|\band\b|\bor\b)*(?={WIKI_LINK.pattern})")


def check_memory_graph(store: Store, config: Config, walked: Walk) -> list[Finding]:
    """The graph's notices over `walked`, the walk of `store`'s configured groups."""
    groups = [g for g in config.memory.groups if g in store.groups]
    linkable = {p.stem for p in store.path.glob("*.md")}
    for group in groups:
        linkable |= {p.stem for p in (store.path / group).glob("*.md")}
    ids = identifiers(config)
    found: list[Finding] = []
    for note in walked.notes:
        where = note.path.relative_to(store.path).as_posix()
        # Fences first (they can contain backticks), then spans; the span placeholder keeps
        # `[[a]] `x` [[a]]` from reading as a repeat.
        text = blank_code_spans(blank_fences(note.body))
        for target in WIKI_LINK.findall(text):
            if ids.is_identifier(target):
                found.append(Finding("bracketed-identifier", where, None, target))
            elif target not in linkable:
                found.append(Finding("dead-wiki-link", where, None, target))
        for first, repeat in _REPEAT.findall(text):
            if first == repeat:
                found.append(Finding("repeated-link", where, None, first))
    return found
