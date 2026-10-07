from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from stayfixed.overlay.api import requires_of, satisfies
from stayfixed.overlay.layout import PLUGIN_MANIFEST
from stayfixed.overlay.template import template_root
from tests.parserlimits import LONG_NUMBER, NESTED


def overlay_with(root: Path, requires: object) -> Path:
    """An overlay directory whose manifest declares `requires`; the doctor, attach and setup
    suites plant their overlays with it too."""
    (root / ".claude-plugin").mkdir(parents=True, exist_ok=True)
    body: dict[str, object] = {"name": "stayfixed-overlay", "version": "0.0.0"}
    if requires is not None:
        body["stayfixed"] = {"requires": requires}
    (root / PLUGIN_MANIFEST).write_text(json.dumps(body), encoding="utf-8")
    (root / ".claude-plugin" / "marketplace.json").write_text(
        json.dumps({"name": "stayfixed-overlay-marketplace", "plugins": []}), encoding="utf-8"
    )
    return root


def test_the_shipped_template_declares_a_floor_this_reader_reads() -> None:
    spec = requires_of(template_root())
    assert spec is not None and satisfies(spec, "0.1.0") is not None


def test_an_absent_declaration_and_an_absent_manifest_both_answer_none(tmp_path: Path) -> None:
    assert requires_of(overlay_with(tmp_path / "a", None)) is None
    assert requires_of(tmp_path / "nowhere") is None
    assert requires_of(overlay_with(tmp_path / "b", " >=0.1.0 ")) == ">=0.1.0"


def test_a_manifest_whose_top_level_is_not_an_object_is_nothing_declared(tmp_path: Path) -> None:
    """`json.loads` answers for a list, a string and a number as readily as for an object.

    `raw.get` exists on none of those, so without this arm a manifest an owner can save turned
    `requires_of` into an `AttributeError` out of a function whose docstring promises `None` for
    anything it cannot read — and the two callers rest on that promise: `doctor` renders a raised
    reader as "this check could not run", and the session handler's `except Exception` swallows it
    along with every other line of the same result, `NOT_ATTACHED` included.

    Uncovered before this case, measured with `--cov-report=term-missing` over `tests/doctor
    tests/overlay tests/release`.

    Mutation (oracle): `mutations/`'s "the requires reader raises for a manifest that is not an
    object" -> each shape below raises instead of answering.
    """
    root = tmp_path / "overlay"
    (root / ".claude-plugin").mkdir(parents=True)
    for body in ("[]", '[{"stayfixed": {"requires": ">=0.1.0"}}]', '">=0.1.0"', "3", "null"):
        (root / PLUGIN_MANIFEST).write_text(body, encoding="utf-8")
        assert requires_of(root) is None, body


def test_a_manifest_past_the_parsers_reach_is_nothing_declared(tmp_path: Path) -> None:
    # Valid JSON nested past what `json.loads` follows raises `RecursionError`, which the reader's
    # `ValueError` arm does not catch, so it escaped a function whose docstring promises `None` for
    # anything it cannot read, and the session handler's backstop swallowed every other line of
    # the same result with it. An integer longer than the interpreter converts is a `ValueError`
    # and was already `None`; it is here so both limits stay answered. Mutation (oracle):
    # `mutations/`'s "the JSON object reader lets a document nested past the parser raise" ->
    # the nested case raises and this reddens.
    root = tmp_path / "overlay"
    (root / ".claude-plugin").mkdir(parents=True)
    for body in (NESTED, '{"n": ' + LONG_NUMBER + "}"):
        (root / PLUGIN_MANIFEST).write_text(body, encoding="utf-8")
        assert requires_of(root) is None, body[:8]


def test_a_fifo_at_the_plugin_manifest_is_unreadable_to_its_readers_without_waiting(
    tmp_path: Path,
) -> None:
    # Two readers of the overlay's plugin manifest read it with `read_text`, which waits on a FIFO
    # for a writer that never comes: `requires_of`, which the SessionStart hook asks, and
    # `owner_of`, which `overlay upgrade` asks. Both read it through `naming.manifest` now, a
    # regular file only, so a FIFO is nothing declared and no owner, and the reader itself refuses
    # it unread. `overlay_fault` reads it through `naming.manifest` too, but its answer for a FIFO
    # comes from the `is_file` gate above that read, so it holds the probe's verdict and not the
    # reader's. In a child under a timeout, so a regression fails this case rather than hanging.
    # Mutation (oracle): `mutations/`'s "an overlay manifest is read without asking what it is" ->
    # the child waits and this times out.
    root = overlay_with(tmp_path / "overlay", ">=0.1.0")
    (root / PLUGIN_MANIFEST).unlink()
    os.mkfifo(root / PLUGIN_MANIFEST)
    probe = (
        "import sys\n"
        "from pathlib import Path\n"
        "from stayfixed.overlay.api import requires_of\n"
        "from stayfixed.overlay.identity import overlay_fault\n"
        "from stayfixed.fsops import NotRegularFile\n"
        "from stayfixed.overlay.naming import manifest, owner_of\n"
        "root = Path(sys.argv[1])\n"
        "try:\n"
        "    manifest(root, '.claude-plugin/plugin.json')\n"
        "except NotRegularFile:\n"
        "    print('refused', end=' ')\n"
        "print(requires_of(root), owner_of(root), overlay_fault(root) is not None)\n"
    )
    try:
        done = subprocess.run(
            [sys.executable, "-c", probe, str(root)],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except subprocess.TimeoutExpired:
        pytest.fail("a reader of the overlay's plugin manifest waited on a FIFO")
    assert done.stdout == "refused None None True\n", done.stderr


def test_the_floor_is_compared_as_numbers_not_as_text() -> None:
    # Mutation (comment): compare `running.groups() >= floor.groups()` as strings -> the first
    # line reddens on `>=9.0.0` against `10.0.0`.
    #
    # And the boundary itself, which is the classic off-by-one site: a floor a running version
    # meets exactly is met. Mutation: `mutations/`'s "the declared floor stops being met by
    # the version that equals it".
    assert satisfies(">=9.0.0", "10.0.0") is True
    assert satisfies(">=0.1.0", "0.1.0") is True
    assert satisfies(">=0.1.0", "0.0.9") is False


@pytest.mark.parametrize("version", ["1.0.0rc1", "1.0.0.dev0", "1.0.0-rc.1", "1.0.0a1"])
def test_a_pre_release_of_the_floor_does_not_meet_it(version: str) -> None:
    # `semver.later` orders a release after its own pre-release, and the floor compared the
    # leading triple alone, so a `1.0.0rc1` build met an overlay's `>=1.0.0` that `later` says
    # it comes before: the session line and the `overlay-requires` row read it as met. The
    # floor is decided by `later` wherever `later` answers. Mutation: `mutations/`, "the
    # declared floor is met by a pre-release of it".
    assert satisfies(">=1.0.0", version) is False
    assert satisfies(">=0.9.9", version) is True


def test_a_suffix_later_leaves_unordered_still_meets_the_floor_by_its_triple() -> None:
    # The legitimate user: `.post1` and `+local` builds, which `later` declines to order against
    # the bare version, keep the answer the triple gives, a floor equal to it met. Mutation:
    # `mutations/`, "the declared floor stops being met by the version that equals it".
    assert satisfies(">=1.0.0", "1.0.0.post1") is True
    assert satisfies(">=1.0.0", "1.0.0+local") is True
    assert satisfies(">=1.0.1", "1.0.0.post1") is False


def test_any_other_form_is_unreadable_never_satisfied() -> None:
    for spec in ("~=1.0", ">1.0.0", "==0.1.0", ">=1.0", ">=a.b.c", ""):
        assert satisfies(spec, "0.1.0") is None, spec
    assert satisfies(">=0.1.0", "next") is None


def test_a_component_too_long_to_convert_is_unreadable_and_not_an_exception() -> None:
    """`satisfies` answers for every string, which is what its `None` is worth.

    CPython 3.11 refuses `int()` on a string past 4300 digits, so an unbounded `(\\d+)` in
    either pattern turned an overlay manifest an owner can mistype into a `ValueError`: red in
    `doctor` as "this check could not run", and in the session handler swallowed by the
    backstop that then dropped `NOT_ATTACHED` and every other line of the same result. The
    value is asserted rather than the crash, because the crash is the thing being removed.

    Mutation: `mutations/`'s "the version grammar stops bounding its components".
    """
    long = "9" * 5000
    assert satisfies(f">={long}.0.0", "0.1.0") is None
    assert satisfies(">=1.0.0", f"{long}.0.0") is None
    # Ten digits, which is the first length past the bound rather than the first past `int()`.
    assert satisfies(">=1234567890.0.0", "0.1.0") is None


def test_only_ascii_digits_are_a_version(tmp_path: Path) -> None:
    """`\\d` matches every Unicode decimal digit and `int()` converts them, so a floor written
    in Eastern Arabic-Indic numerals validated, compared as `>=1.0.0`, and printed back
    verbatim — `requires_of` returns the manifest's own bytes, and the session line and the
    `doctor` row print the spec they validated. A version is ASCII or it is unreadable.

    The digits are spelled as escapes so this file stays ASCII; the manifest a repository
    writes carries them as bytes, which is what the last assertion says."""
    eastern = ">=\u0661.\u0660.\u0660"
    assert satisfies(eastern, "0.1.0") is None
    assert satisfies(">=0.1.0", "\u0661.\u0660.\u0660") is None
    # Non-vacuous: the manifest really does hand this string back, which is why the verdict
    # above is what keeps it out of a line a model reads.
    assert requires_of(overlay_with(tmp_path / "eastern", eastern)) == eastern
