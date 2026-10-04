"""The Python profile's red-run hint: which commands run pytest, and which bytecode is stale."""

from __future__ import annotations

import importlib.util
import os
import py_compile
import struct
import sys
import time
from pathlib import Path

import pytest

from stayfixed.config.loader import CONFIG_FILE, load
from stayfixed.config.schema import Config
from stayfixed.guards.hygiene import simple_commands
from stayfixed.guards.roots import contained_roots
from stayfixed.profiles.python.hygiene import HINT

CONFIG = """
[stayfixed]
version = "0.1.0"
state = "installed"
preset = "recommended"
profile = ""
agents = ["claude"]

[project]
name = "widget"
base_branch = "main"
release_branch = "main"

[ledger]
code_roots = ["src", "tests"]
"""


def repo(tmp_path: Path) -> Path:
    # No git repository: the walk reads files and nothing else, and the dirty count that needs
    # git belongs to the core (`tests/guards/test_hygiene.py`).
    root = tmp_path / "repo"
    (root / "src").mkdir(parents=True)
    (root / "src" / "mod.py").write_text("x = 1\n", encoding="utf-8")
    (root / CONFIG_FILE).write_text(CONFIG, encoding="utf-8")
    return root


def config(root: Path) -> Config:
    return load(root, machine=root.parent / "absent.toml")


def stale(root: Path) -> int:
    return HINT.report(root, config(root))["stale"]


def runs_pytest(command: str) -> bool:
    """The question the handler asks: does the hint recognise any simple command of `command`."""
    return any(HINT.recognises(argv) for argv in simple_commands(command))


def compile_module(module: Path) -> Path:
    """Compile `module` to the `__pycache__` beside it, with a timestamp header.

    `py_compile.compile(..., cfile=None)` alone is NOT enough, and the mutation oracle is what
    proved it: the oracle runs pytest under `PYTHONPYCACHEPREFIX`, which sends every cached
    `.pyc` to a scratch tree instead of to a `__pycache__` next to the source — so `report`
    walked the code roots, found no bytecode at all, and both bytecode tests reported `stale
    == 0`. One of them then failed on a clean tree and the other SURVIVED its mutation, which
    is the "the run ran nothing" shape of a vacuous oracle exactly.

    `invalidation_mode` is pinned for the sibling reason: `py_compile` switches to a hash-based
    header when `SOURCE_DATE_EPOCH` is set in the environment, and a hash-based `.pyc` has no
    mtime at bytes 8-12 to compare. Only the destination and the mode are pinned here — the
    header bytes are still the ones the interpreter itself writes, which is the whole point of
    compiling rather than hand-assembling one.
    """
    cache = module.parent / "__pycache__" / f"{module.stem}.{sys.implementation.cache_tag}.pyc"
    py_compile.compile(
        str(module),
        cfile=str(cache),
        doraise=True,
        invalidation_mode=py_compile.PycInvalidationMode.TIMESTAMP,
    )
    return cache


def test_stale_bytecode_is_counted(tmp_path: Path) -> None:
    """A `.pyc` is stale when the source mtime recorded in its header (bytes 8-12) no longer
    matches the source's — the condition CPython itself checks. Compile, then move the source
    forward."""
    # Oracle: `mutations/`, "stale bytecode is never counted".
    root = repo(tmp_path)
    module = root / "src" / "mod.py"
    compile_module(module)
    future = time.time() + 60
    os.utime(module, (future, future))
    assert stale(root) == 1


def test_a_normally_compiled_pyc_is_not_stale(tmp_path: Path) -> None:
    """The everyday case, and what a naive `pyc mtime > source mtime` gets backwards."""
    # Oracle: `mutations/`, "fresh bytecode is counted as stale".
    root = repo(tmp_path)
    # The `.pyc` must actually exist, or `stale == 0` passes by finding nothing to judge.
    assert compile_module(root / "src" / "mod.py").is_file()
    assert stale(root) == 0


def test_a_hash_based_pyc_is_not_judged(tmp_path: Path) -> None:
    """PEP 552 bytes 8-12 are the source mtime only while bit 0 of the flags word at bytes 4-8
    is clear. In a hash-based `.pyc` they are the first half of the source's hash, and comparing
    that fragment to an mtime reports every such file as stale forever — the FALSE-ALARM
    direction, which this module's whole design note says it avoids. It is not an exotic shape:
    `py_compile` switches to it on its own under `SOURCE_DATE_EPOCH`, and `compileall
    --invalidation-mode checked-hash` produces a tree of them.
    """
    # Oracle: `mutations/`, "a hash-based .pyc is read as if it carried an mtime".
    root = repo(tmp_path)
    module = root / "src" / "mod.py"
    cache = module.parent / "__pycache__" / f"{module.stem}.{sys.implementation.cache_tag}.pyc"
    py_compile.compile(
        str(module),
        cfile=str(cache),
        doraise=True,
        invalidation_mode=py_compile.PycInvalidationMode.CHECKED_HASH,
    )
    # The file must exist, or `stale == 0` passes by finding nothing to judge — the same
    # vacuity `compile_module` was written to close.
    assert cache.is_file()
    assert stale(root) == 0


def test_a_source_mtime_past_2106_is_compared_the_way_cpython_compares_it(tmp_path: Path) -> None:
    """PEP 552's timestamp field is a uint32, so CPython masks the source mtime to 32 bits
    before writing it. Comparing the unmasked `int(st_mtime)` against that field reports a
    perfectly current `.pyc` as stale forever — the false-alarm direction again, reachable by
    a clock that ran forward, an archive unpacked with a bad timestamp, or the year 2106.

    Reddened by dropping `& _PYC_MTIME_MASK` from `_stale_bytecode`'s comparison; measured,
    and it reddened this test alone.

    Not in `mutations/`: the skip below is environmental — a filesystem that cannot store
    a post-2106 mtime clamps it — and a declared mutation whose named test can SKIP reports
    "caught" while proving nothing.
    """
    root = repo(tmp_path)
    module = root / "src" / "mod.py"
    beyond = 2**32 + 5
    os.utime(module, (beyond, beyond))
    if int(module.stat().st_mtime) != beyond:
        pytest.skip("this filesystem clamps a post-2106 mtime; the fault cannot be staged")
    # Compiled AFTER the mtime is set, so the header holds CPython's own masked value (5) and
    # the bytecode is genuinely current.
    assert compile_module(module).is_file()
    assert stale(root) == 0


def test_a_repeated_or_nested_code_root_is_walked_once(tmp_path: Path) -> None:
    """Every consumer of `contained_roots` walks each entry with `rglob` and adds up what it
    finds, so a repeated or nested entry double-counts. Measured before the pruning: with
    `code_roots = ["src", "src", "src/pkg"]` the one stale `.pyc` under `src/pkg` was reported
    three times and the one under `src` twice — `stale == 5` for two stale files, in a notice
    whose only job is to be believed about a number.

    Oracle: `mutations/`, "a code root listed twice is walked twice". Measured both ways —
    deleting BOTH pruning lines gives `stale == 5`, and the declared single-line mutation (the
    `if any(_covers(...))` guard alone) still gives `stale == 3`, because the descendant
    rebuild below it happens to collapse the exact repeat while leaving the nested root. Each
    reddened this test alone.

    The `.pyc` count is asserted beside the root list deliberately: a de-duplicated list that
    nothing counted would be a shape claim, and the doubled COUNT is the defect.
    """
    root = repo(tmp_path)
    package = root / "src" / "pkg"
    package.mkdir()
    inner = package / "deep.py"
    inner.write_text("y = 1\n", encoding="utf-8")
    for module in (root / "src" / "mod.py", inner):
        compile_module(module)
        future = time.time() + 60
        os.utime(module, (future, future))
    (root / CONFIG_FILE).write_text(
        CONFIG.replace('code_roots = ["src", "tests"]', 'code_roots = ["src", "src", "src/pkg"]'),
        encoding="utf-8",
    )
    assert contained_roots(root, config(root)) == [root / "src"]
    assert stale(root) == 2


def test_a_pyc_from_another_interpreter_is_not_judged(tmp_path: Path) -> None:
    """The sibling of the hash-based case, in the same false-alarm direction. A `__pycache__`
    accumulates one `.pyc` per interpreter tag and nothing removes the old ones, so a
    `mod.cpython-311.pyc` from an earlier run sits there forever recording the source mtime as
    of THAT run — while the bytecode this interpreter will actually import, compiled here and
    fresh, matches. Reading past the magic word counted the leftover and the notice then fired
    on every red run of a healthy tree. Measured before the magic check: `stale == 1`.
    """
    # Oracle: `mutations/`, "a .pyc from another interpreter is read as this one's".
    root = repo(tmp_path)
    module = root / "src" / "mod.py"
    # The CURRENT tag's bytecode, fresh — so a non-zero count can only come from the leftover.
    assert compile_module(module).is_file()
    foreign = module.parent / "__pycache__" / f"{module.stem}.cpython-311.pyc"
    # Hand-assembled rather than compiled: only one interpreter is installed in this test run,
    # so the one header shape that matters here cannot be produced by asking `py_compile` for
    # it. A magic this interpreter never writes, a timestamp-based flags word, and a recorded
    # mtime deliberately unequal to the source's — the exact shape a stale leftover has.
    #
    # DERIVED from the running magic rather than written as some released version's literal,
    # and that is not laziness: CI runs this suite on 3.11, 3.12 and 3.13, so any literal
    # naming one of them is the RUNNING interpreter's magic on that leg and the test would
    # then assert the opposite of what it means. The `!=` below is what the derivation has to
    # buy, so it is asserted rather than assumed.
    foreign_magic = bytes([importlib.util.MAGIC_NUMBER[0] ^ 0xFF]) + importlib.util.MAGIC_NUMBER[1:]
    assert len(foreign_magic) == 4
    assert foreign_magic != importlib.util.MAGIC_NUMBER
    foreign.write_bytes(
        foreign_magic
        + struct.pack("<I", 0)
        + struct.pack("<I", int(module.stat().st_mtime) - 10_000)
        + struct.pack("<I", 4)
    )
    assert stale(root) == 0


def test_only_contained_code_roots_are_scanned(tmp_path: Path) -> None:
    # `config.paths` leaves `ledger.code_roots` to its consumer; an escaping entry is
    # skipped rather than followed, and a missing one is skipped rather than raised on.
    # `outside` is CREATED, which is what makes the containment check load-bearing here: with
    # `contained()` removed, `root/../outside` is a real directory and would be walked, so the
    # assertion below fails. Without the directory the entry would be dropped by `is_dir()`
    # alone and the containment call could be deleted with the test still green.
    # Oracle: `mutations/`, "an escaping code root is followed".
    root = repo(tmp_path)
    (root.parent / "outside").mkdir()
    (root / CONFIG_FILE).write_text(
        CONFIG.replace(
            'code_roots = ["src", "tests"]', 'code_roots = ["src", "../outside", "nope"]'
        ),
        encoding="utf-8",
    )
    assert contained_roots(root, config(root)) == [root / "src"]
    assert HINT.report(root, config(root))["roots"] == 1


def test_the_note_names_no_code_root_even_when_bytecode_is_stale() -> None:
    # Pure: the one sentence that mentions code roots is the stale one, so it is rendered from
    # fixed counts rather than from a tree whose stale count happens to be zero. The second
    # assertion has no mutation of its own: it pins a NEGATIVE over the module's fixed
    # sentence, so the only edit that reddens it is one that puts a root name into `STALE`,
    # which is the "repository bytes are data" rule (CONTRIBUTING.md) this assertion exists to
    # hold. The note's exact words are pinned in `tests/profiles/test_hints.py`.
    text = HINT.note({"stale": 2, "roots": 1})
    assert text is not None and "2 .pyc file(s)" in text
    assert "src" not in text and "tests" not in text


@pytest.mark.parametrize(
    "command",
    [
        "pytest",
        ".venv/bin/python -m pytest tests/x.py",
        "python3 -mpytest",
        "PYTHONPATH=src pytest",
        'PYTHONPATH="$WT/src" "$MAIN/.venv/bin/python" -m pytest',
        "FOO=1 BAR=2 pytest",
        "env pytest -q",
        "uv run pytest -q",
        "make lint && pytest",
    ],
)
def test_a_real_pytest_invocation_is_recognised(command: str) -> None:
    # Reddened by mutating `recognises`'s `if argv0 == PYTEST: return True` to
    # `return False`; measured.
    assert runs_pytest(command)


@pytest.mark.parametrize(
    "command",
    [
        "ls -la",
        'echo "run pytest later" > n.md',
        "grep -m pytest notes.txt",
        "uv run --python 3.11 pytest",
        "cargo test",
    ],
)
def test_a_mention_or_an_unrecognised_launcher_is_not_a_run(command: str) -> None:
    # The fourth is the documented under-report: an unrecognised wrapper leaves the note
    # undelivered, never wrongly delivered. Reddened by mutating `recognises` to answer
    # `PYTEST in " ".join(argv)`, the substring test it exists to replace; measured.
    assert not runs_pytest(command)


def test_an_empty_command_is_not_a_run() -> None:
    # The scanner never hands an empty argv on, but the hint is a published shape a caller may
    # ask directly. Reddened by deleting `if not argv: return False` (`argv[0]` raises);
    # measured.
    assert HINT.recognises([]) is False
