"""Every reader of a TOML document somebody else wrote, handed one nested past the parser.

`tomllib` reads nested arrays by recursion, so `a = [[[…]]]` a few thousand levels deep raises
`RecursionError`, not `TOMLDecodeError`. Uncaught, that is an internal error, the class stayfixed
keeps for its own defects; in a gate run it ended every gate, and in `stayfixed.toml` it replaced
"does not load" with a traceback's name. So each reader answers it as it answers a document that
does not parse, and each case below holds one reader to its own answer.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from stayfixed.attach import binding, write
from stayfixed.config.loader import TOO_DEEP, ConfigError, MachineConfigError, loads
from stayfixed.config.overlay import overlay_root
from stayfixed.config.owned import UnparsedDocument, rewrite
from stayfixed.docs.trail import read_trail
from stayfixed.errors import Failure
from stayfixed.memory import store
from stayfixed.project import init
from stayfixed.setup.machine import read_machine
from tests.scriptload import release

# The repository's release script, whose version check is one more reader below.
script = release()

# Past the interpreter's default recursion limit of 1000 with room to spare, on 3.11 to 3.13.
DEPTH = 2000
DEEP = "a = " + "[" * DEPTH + "]" * DEPTH + "\n"
FINE = '[stayfixed]\nversion = "0.1.0"\n\n[project]\nname = "widget"\n'


def _file(tmp_path: Path, relative: str, text: str = DEEP) -> Path:
    path = tmp_path / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _record(tmp_path: Path) -> Path:
    """The overlay's record of the project `widget`, nested past the parser."""
    return _file(tmp_path, f"overlay/{store.PROJECTS}/widget/{store.PROJECT_RECORD}")


def test_the_parser_still_recurses_at_this_depth() -> None:
    # The premise of every case below: on a `tomllib` that stopped recursing, each would pass
    # for a reason that is not the guard.
    import tomllib

    with pytest.raises(RecursionError):
        tomllib.loads(DEEP)


Case = Callable[[Path], object]


@pytest.mark.parametrize(
    ("read", "raised"),
    [
        pytest.param(lambda t: loads(DEEP, t, machine=t / "absent.toml"), ConfigError, id="loads"),
        pytest.param(
            lambda t: loads(FINE, t, machine=_file(t, "machine.toml")),
            MachineConfigError,
            id="personal",
        ),
        pytest.param(
            lambda t: rewrite(DEEP, {("stayfixed", "state"): "adopting"}),
            UnparsedDocument,
            id="owned-rewrite",
        ),
        pytest.param(lambda t: read_trail(_file(t, "docs/trail.toml")), Failure, id="trail"),
        pytest.param(
            lambda t: binding._recorded(_record(t).parents[2], "widget"), Failure, id="binding"
        ),
        pytest.param(
            lambda t: overlay_root(_file(t, "machine.toml")), MachineConfigError, id="overlay-root"
        ),
        pytest.param(
            lambda t: script._read(_file(t, "pyproject.toml").parent, script.PYPROJECT),
            script.MalformedSource,
            id="versions-read",
        ),
        pytest.param(
            lambda t: script._pyproject(_file(t, "pyproject.toml").parent),
            script.MalformedSource,
            id="versions-pyproject",
        ),
        pytest.param(
            lambda t: init._existing(_file(t, "stayfixed.toml").parent), Failure, id="init"
        ),
        pytest.param(
            lambda t: read_machine(_file(t, "machine.toml")), MachineConfigError, id="machine"
        ),
    ],
)
def test_a_reader_answers_a_document_nested_past_the_parser_as_one_that_does_not_parse(
    tmp_path: Path, read: Case, raised: type[Exception]
) -> None:
    # Mutation (declared, one per reader): the reader's `RecursionError` dropped from its catch
    # -> it escapes and this case reddens with the wrong exception.
    with pytest.raises(raised):
        read(tmp_path)


@pytest.mark.parametrize(
    ("read", "answer"),
    [
        pytest.param(lambda t: write._first_attach(_record(t)), None, id="first-attach"),
        pytest.param(
            lambda t: getattr(store._bound(_record(t).parents[2], "widget", t), "said", None),
            store.RECORD_UNREADABLE,
            id="store-bound",
        ),
    ],
)
def test_a_reader_that_degrades_on_a_broken_record_degrades_on_a_deep_one(
    tmp_path: Path, read: Case, answer: object
) -> None:
    # Two readers answer "nothing recorded" for a record they cannot parse; a deep one is such a
    # record. Mutation (declared, one per reader): `RecursionError` dropped from either catch ->
    # it escapes.
    assert read(tmp_path) == answer


def test_the_refusal_names_the_file_and_says_why_without_a_position() -> None:
    # The position `tomllib` reports is the actionable half of a parse failure; a document
    # nested past the parser has none, and the message says what it has instead.
    with pytest.raises(ConfigError) as refused:
        loads(DEEP, Path("/nowhere"), machine=Path("/nowhere/absent.toml"))
    assert str(refused.value).endswith(f"stayfixed.toml is not valid TOML {TOO_DEEP}")
