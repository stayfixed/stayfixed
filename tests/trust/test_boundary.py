"""`trust.boundary`'s one sentence for a write an agent's sandbox refused, held to every writer."""

from __future__ import annotations

import ast

import pytest

from stayfixed.attach.write import REFRESH_REFUSED
from stayfixed.memory.commands import _NOT_REFRESHED
from stayfixed.setup.machine import SETUP_SANDBOXED
from stayfixed.trust.boundary import ONLY_OUTSIDE, RUN_OUTSIDE, SANDBOX_REFUSED
from stayfixed.trust.record import SANDBOXED
from tests.ownerhome import ROOT

# What `SANDBOX_REFUSED` says between its first two fields: the sandbox and what it refuses.
_MIDDLE = SANDBOX_REFUSED.split("{directory}")[1].split("{remedy}")[0]
# The words of it a hand-written copy would repeat, which no other sentence has reason to.
_HAND_WRITTEN = "outside the working directory"


def test_no_module_writes_the_sandbox_sentence_by_hand() -> None:
    # Four writers each wrote the sentence in their own words, and two had drifted apart while
    # the docstrings said every writer gave one. Mutation (`mutations/`'s "attach writes its
    # sandbox sentence by hand"): a string of attach's own carries the words again.
    found = []
    for path in sorted((ROOT / "src" / "stayfixed").rglob("*.py")):
        relative = path.relative_to(ROOT).as_posix()
        if relative == "src/stayfixed/trust/boundary.py":
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and _HAND_WRITTEN in node.value
            ):
                found.append(relative)
    assert found == []


@pytest.mark.parametrize(
    ("sentence", "remedy"),
    [
        (SANDBOXED, RUN_OUTSIDE.format(command="this command")),
        (SETUP_SANDBOXED, RUN_OUTSIDE.format(command="`stayfixed setup`")),
        (_NOT_REFRESHED, ONLY_OUTSIDE),
        (REFRESH_REFUSED, ONLY_OUTSIDE),
    ],
    ids=["trust-record", "setup", "memory-index", "attach"],
)
def test_every_writer_says_the_one_sentence_with_its_remedy(sentence: str, remedy: str) -> None:
    # No mutation of its own: each writer's constant is filled from the template, so a writer that
    # stopped would be a string the scan above reddens on.
    assert _MIDDLE in sentence
    assert remedy in sentence.split(_MIDDLE, 1)[1]
