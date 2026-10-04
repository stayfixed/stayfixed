"""What could have falsified a red run, named before the diff is blamed."""

from __future__ import annotations

import importlib.util
import os
import py_compile
import shutil
import struct
import sys
import time
from pathlib import Path

import pytest

from stayfixed.config.loader import CONFIG_FILE, load
from stayfixed.config.schema import Config
from stayfixed.guards.hygiene import Hygiene, context_for, inspect, is_pytest_run, notice, red_exit
from stayfixed.guards.roots import contained_roots
from tests.gitfixture import git

# Per test: `is_pytest_run` and `red_exit` are pure, and a module-level skip would void them.
needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")

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
    root = tmp_path / "repo"
    (root / "src").mkdir(parents=True)
    (root / "src" / "mod.py").write_text("x = 1\n", encoding="utf-8")
    (root / CONFIG_FILE).write_text(CONFIG, encoding="utf-8")
    git(root, "init", "-q", "-b", "main")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "chore: seed")
    return root


def config(root: Path) -> Config:
    return load(root, machine=root.parent / "absent.toml")


def compile_module(module: Path) -> Path:
    """Compile `module` to the `__pycache__` beside it, with a timestamp header.

    `py_compile.compile(..., cfile=None)` alone is NOT enough, and the mutation oracle is what
    proved it: the oracle runs pytest under `PYTHONPYCACHEPREFIX`, which sends every cached
    `.pyc` to a scratch tree instead of to a `__pycache__` next to the source — so `inspect`
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


@needs_git
def test_a_dirty_tree_is_counted(tmp_path: Path) -> None:
    # A TRACKED file modified after its commit, never merely an untracked one: `inspect` runs
    # `git` under `gitenv.scrubbed_env()`, which keeps the real `HOME` by design, so the
    # developer's own `status.showUntrackedFiles = no` or `core.excludesFile` could hide an
    # untracked file and make this assertion environment-dependent. Reddened by mutating
    # `_dirty_count`'s `sum(...)` to `return 0`; measured.
    root = repo(tmp_path)
    (root / "src" / "mod.py").write_text("x = 2\n", encoding="utf-8")
    assert inspect(root, config(root)).dirty == 1


@needs_git
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
    assert inspect(root, config(root)).stale == 1


@needs_git
def test_a_normally_compiled_pyc_is_not_stale(tmp_path: Path) -> None:
    """The everyday case, and what a naive `pyc mtime > source mtime` gets backwards."""
    # Oracle: `mutations/`, "fresh bytecode is counted as stale".
    root = repo(tmp_path)
    # The `.pyc` must actually exist, or `stale == 0` passes by finding nothing to judge.
    assert compile_module(root / "src" / "mod.py").is_file()
    assert inspect(root, config(root)).stale == 0


@needs_git
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
    assert inspect(root, config(root)).stale == 0


@needs_git
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
    assert inspect(root, config(root)).stale == 0


@needs_git
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
    assert inspect(root, config(root)).stale == 2


@needs_git
def test_a_code_root_spelled_with_a_trailing_or_leading_slash_is_still_walked(
    tmp_path: Path,
) -> None:
    """`"src/"` and `"./tests"` are how many people write a directory, and they were dropped.

    `contained()` took on the write's component rule, which refuses a trailing `/`, a doubled
    `/` and a leading `./` because the engine cannot write through them. A code root is only
    walked, and `contained_roots` caught the refusal and moved on — so both entries left the
    hygiene counts and the citation roots with nothing saying so. They are folded before the
    question now.

    Oracle: `mutations/`, "a code root spelled with a slash is dropped again".
    """
    root = repo(tmp_path)
    (root / "tests").mkdir()
    (root / CONFIG_FILE).write_text(
        CONFIG.replace('code_roots = ["src", "tests"]', 'code_roots = ["src/", ".//tests"]'),
        encoding="utf-8",
    )
    assert contained_roots(root, config(root)) == [root / "src", root / "tests"]


@needs_git
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
    assert inspect(root, config(root)).stale == 0


@needs_git
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
    assert inspect(root, config(root)).roots == 1


@needs_git
def test_a_clean_tree_and_fresh_bytecode_say_nothing(tmp_path: Path) -> None:
    # Reddened by mutating `notice`'s `if not notes: return None` to `return LEAD`; measured.
    root = repo(tmp_path)
    assert compile_module(root / "src" / "mod.py").is_file()
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "chore: bytecode")
    assert notice(inspect(root, config(root))) is None


@needs_git
def test_the_notice_carries_counts_and_no_root_names(tmp_path: Path) -> None:
    # Reddened by mutating `notice`'s `if found.dirty:` to `if False:`; measured.
    root = repo(tmp_path)
    (root / "src" / "mod.py").write_text("x = 2\n", encoding="utf-8")
    text = notice(inspect(root, config(root)))
    assert text is not None and "1 uncommitted change(s)" in text


def test_the_notice_names_no_code_root_even_when_bytecode_is_stale() -> None:
    # Pure: the one sentence that mentions code roots is the stale one, so it is rendered
    # from a fixed `Hygiene` rather than from a tree whose stale count happens to be zero.
    # Reddened by mutating `notice`'s `if found.stale:` to `if False:`; measured. The second
    # assertion has no mutation of its own: it pins a NEGATIVE over the module's fixed
    # sentences, so the only edit that reddens it is one that puts a root name into `STALE`,
    # which is the §"repository bytes are data" rule this assertion exists to hold.
    text = notice(Hygiene(dirty=1, stale=2, roots=1))
    assert text is not None and "2 .pyc file(s)" in text
    assert "src" not in text and "tests" not in text


def test_a_git_that_cannot_answer_is_none_not_zero(tmp_path: Path) -> None:
    # Reddened by mutating `_dirty_count`'s `if completed.returncode != 0: return None` to
    # `return 0`; measured. `None` and `0` are what `test hygiene` turns into exit 2 and exit
    # 0, so collapsing them reports an unjudgeable tree as clean.
    root = tmp_path / "not-a-repo"
    (root / "src").mkdir(parents=True)
    (root / CONFIG_FILE).write_text(CONFIG, encoding="utf-8")
    assert inspect(root, config(root)).dirty is None


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
    # Reddened by mutating `_segment_runs_pytest`'s `if argv0 == PYTEST: return True` to
    # `return False`; measured.
    assert is_pytest_run(command)


@pytest.mark.parametrize(
    "command",
    [
        "ls -la",
        'echo "run pytest later" > n.md',
        "grep -m pytest notes.txt",
        "uv run --python 3.11 pytest",
    ],
)
def test_a_mention_or_an_unrecognised_launcher_is_not_a_run(command: str) -> None:
    # The last one is the documented under-report: an unrecognised wrapper leaves the note
    # undelivered, never wrongly delivered. Reddened by mutating `is_pytest_run`'s
    # `return any(...)` to `return PYTEST in command`, i.e. the substring test this whole
    # module exists to replace; measured.
    assert not is_pytest_run(command)


def test_an_unparseable_command_stays_over_inclusive() -> None:
    # Missing a REAL failed pytest run is the worse direction for a warn-only hook.
    # Reddened by mutating `is_pytest_run`'s `return PYTEST in command` fallback to
    # `return False`; measured.
    assert is_pytest_run("pytest 'unbalanced")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ({"tool_response": {"exit_code": 1}}, 1),
        ({"tool_response": {"exit_code": 0}}, None),
        ({"tool_response": {"exit_code": True}}, None),
        ({"tool_response": {"stdout": "1 failed"}}, None),
        ({"error": "Exit code 2\nFAILED tests/x.py"}, 2),
        ({"error": "Exit code 0"}, None),
        ({"error": "Cannot find module"}, None),
        # Not in the ported table, added so `_EXIT_CODE_ERROR`'s anchoring is load-bearing:
        # unanchored, a number is read out of arbitrary captured stderr, and the documented
        # shape puts `Exit code N` at the very start of `error`. Note that swapping `.match`
        # for `.search` is a NO-OP while the pattern keeps `\A` — measured — so the mutation
        # this row reddens is `re.search(r"Exit code (\d+)", error)`, anchor dropped.
        ({"error": "FAILED tests/x.py\nExit code 2"}, None),
        ({}, None),
    ],
)
def test_red_exit_reads_both_payload_shapes(raw: dict[str, object], expected: int | None) -> None:
    # The source read `tool_response.exit_code`; the hooks reference documents the
    # Bash `tool_response` without one and a non-zero exit arriving as `PostToolUseFailure`'s
    # `error` field. Both are read, so the notice is not keyed on a field one harness lacks.
    # Reddened three ways, each measured: dropping the `not isinstance(code, bool)` test (the
    # `True` row), dropping the whole `error` branch (the `Exit code 2` row), and dropping the
    # pattern's `\A` (the row above).
    assert red_exit(raw) == expected


@needs_git
def test_context_for_says_nothing_for_a_non_pytest_command(tmp_path: Path) -> None:
    # Reddened by mutating `context_for`'s `if not is_pytest_run(command): return None` away;
    # measured. The second assertion is the non-vacuity guard for the first: without it a
    # `context_for` that returned `None` unconditionally would pass.
    root = repo(tmp_path)
    (root / "src" / "mod.py").write_text("x = 2\n", encoding="utf-8")
    assert context_for("ls -la", root, config(root)) is None
    assert context_for("pytest", root, config(root)) is not None
