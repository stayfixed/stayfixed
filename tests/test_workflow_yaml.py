"""The strict workflow reader, held to YAML where it reads and to a refusal where it does not.

Every workflow test reads `.github/workflows/` through `tests.workflow_yaml`, so a reader that
stopped early, or skipped a line it could not read, would make every one of them report clean
over the lines it missed. These cases are that reader's own: what ends a block, and what is
refused.
"""

from __future__ import annotations

import re

import pytest

from tests.workflow_yaml import Node, WorkflowYamlError, load


def _first_step(document: Node) -> dict[str, Node]:
    assert isinstance(document, dict)
    jobs = document["jobs"]
    assert isinstance(jobs, dict)
    job = jobs["one"]
    assert isinstance(job, dict)
    steps = job["steps"]
    assert isinstance(steps, list) and isinstance(steps[0], dict)
    return steps[0]


ENV_HEAD = "jobs:\n  one:\n    steps:\n      - name: a step\n        env:\n          FIRST: one\n"


@pytest.mark.parametrize("indent", [0, 4, 7, 8, 10, 12])
def test_a_comment_or_a_blank_line_never_ends_a_block(indent: int) -> None:
    # YAML ends a block at the first line of content that is not indented past its key, and a
    # comment is never content. The `env:` reader this replaced ended at the first comment it
    # met, so a key written after one was in no assertion: `BASH_ENV` after a comment at eight
    # spaces passed every case. Mutation (declared): a comment line counts as content.
    text = ENV_HEAD + " " * indent + "# a note\n\n          SECOND: two\n        run: echo\n"
    step = _first_step(load(text))
    assert step == {"name": "a step", "env": {"FIRST": "one", "SECOND": "two"}, "run": "echo"}


def test_a_key_written_twice_in_one_mapping_is_refused() -> None:
    # Whatever GitHub does with a duplicate, a reader that kept one of the two let the other
    # pass unseen: a `PYTHONPATH` into the checkout first and the good one last read as the good
    # one. Mutation (declared): the duplicate check is removed.
    with pytest.raises(WorkflowYamlError, match="twice"):
        load(ENV_HEAD + "          FIRST: again\n")


@pytest.mark.parametrize(
    ("tail", "why"),
    [
        pytest.param('          SECOND: {"a":"b"}\n', "a value this reader", id="flow-mapping"),
        pytest.param("          SECOND: &anchor two\n", "a value this reader", id="anchor"),
        pytest.param("          SECOND: *anchor\n", "a value this reader", id="alias"),
        pytest.param("          SECOND: !tag two\n", "a value this reader", id="tag"),
        pytest.param(
            "          SECOND: >\n            folded\n", "a value this reader", id="folded"
        ),
        pytest.param('          "SECOND": two\n', "not a plain key", id="quoted-key"),
        pytest.param(
            "          SECOND: two\n            continued\n",
            "continues on the next line",
            id="plain-continued",
        ),
        pytest.param(
            "          SECOND:\n              DEEP: two\n            MIDDLE: two\n",
            "nothing can own it",
            id="orphan-indentation",
        ),
        pytest.param("          SECOND: a: b\n", "reads as a mapping", id="plain-reads-as-mapping"),
        pytest.param("\tSECOND: two\n", "a tab", id="tab"),
        pytest.param("          -KEY: two\n", "not a plain key", id="not-a-key"),
        pytest.param(
            "          SECOND:\n          - two\n",
            "a sequence at its key's own indentation",
            id="sequence-at-key-indentation",
        ),
        pytest.param(
            "          SECOND: |\n        run: echo\n", "an empty block scalar", id="empty-literal"
        ),
    ],
)
def test_a_shape_outside_the_subset_is_refused_naming_its_line(tail: str, why: str) -> None:
    # Refused rather than skipped: a shape this reader does not read is a red test in front of
    # whoever wrote it, never a line passed over. Each refusal is its own: a continued plain
    # scalar with its refusal removed is still refused, as a line nothing owns, and a case that
    # asked only for "some refusal" would not see which guard had gone. Mutations (declared):
    # the plain-continuation and orphan-indentation refusals are removed.
    with pytest.raises(WorkflowYamlError, match=rf"line \d+: .*{re.escape(why)}"):
        load(ENV_HEAD + tail)


def test_a_step_spelled_as_a_flow_mapping_is_refused_rather_than_read() -> None:
    # `- {"run":"…"}` puts a whole step, script and all, on one line inside braces, and GitHub
    # reads it as a step with a script. A reader that took it for a string would hand the
    # expression check a workflow whose step has no `run`, clean. It is refused, naming its line.
    # Spelled as JSON on purpose: with no space after a colon, nothing but the brace refuses it,
    # where `{run: "…"}` is refused a second time as a plain scalar that reads as a mapping, and
    # a case written that way reddens under the mutation only on the refusal's wording. Mutation
    # (oracle): `mutations/`'s "the workflow reader reads a flow mapping as a plain scalar" -> the
    # step is read as the string it spells, `runs` finds no script in it, and this reddens.
    text = 'jobs:\n  one:\n    steps:\n      - {"run":"echo ${{ github.actor }}"}\n'
    with pytest.raises(WorkflowYamlError, match=r"line 4: a value this reader does not read"):
        load(text)


@pytest.mark.parametrize(
    "text",
    [
        pytest.param("  jobs:\n    one:\n", id="indented"),
        pytest.param("# a note\n\n  jobs:\n    one:\n", id="indented-after-a-comment"),
    ],
)
def test_a_document_that_does_not_start_at_column_0_is_refused(text: str) -> None:
    # Every key the tests look for is at column 0, and a document that starts further in would
    # have to be read by indentation this reader was never asked about. A comment and a blank
    # line ahead of it are not content, so they move nothing.
    with pytest.raises(
        WorkflowYamlError, match=r"line \d+: the document does not start at column 0"
    ):
        load(text)


def test_a_literal_block_ends_at_a_line_indented_less_even_a_comment() -> None:
    # A literal block's indentation is its first non-blank line's; a blank line inside it is
    # kept, and it ends at the first non-blank line indented less, a comment included. Mutation
    # (declared): the block does not end at a line indented less, and swallows the next key.
    text = (
        "jobs:\n  one:\n    steps:\n      - name: a step\n        run: |\n\n"
        "          first\n\n            indented\n        # a note\n        env:\n"
        "          KEY: value\n"
    )
    step = _first_step(load(text))
    assert step["run"] == "\nfirst\n\n  indented\n", step
    assert step["env"] == {"KEY": "value"}, step
