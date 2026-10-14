from __future__ import annotations

import pytest

from stayfixed.scaffold.regions import RegionError, Style, drop, extract, markers, upsert

BEFORE = "# Title\n\nHand-written prose the tool must never touch.\n"


def test_markers_are_the_shapes_the_design_fixes() -> None:
    assert markers("harness", Style.MARKDOWN) == (
        "<!-- stayfixed:harness:begin -->",
        "<!-- stayfixed:harness:end -->",
    )
    assert markers("harness", Style.HASH) == (
        "# stayfixed:harness:begin",
        "# stayfixed:harness:end",
    )


def test_a_new_region_is_appended_and_the_rest_is_untouched() -> None:
    out = upsert(BEFORE, "harness", "one\ntwo", Style.MARKDOWN)
    assert out.startswith(BEFORE)
    assert extract(out, "harness", Style.MARKDOWN) == "one\ntwo"


def test_an_existing_region_is_replaced_in_place() -> None:
    once = upsert(BEFORE, "harness", "one", Style.MARKDOWN)
    twice = upsert(once + "trailing prose\n", "harness", "two", Style.MARKDOWN)
    assert extract(twice, "harness", Style.MARKDOWN) == "two"
    assert twice.startswith(BEFORE)
    assert twice.endswith("trailing prose\n")


def test_upsert_is_idempotent() -> None:
    once = upsert(BEFORE, "harness", "one", Style.MARKDOWN)
    assert upsert(once, "harness", "one", Style.MARKDOWN) == once


def test_a_body_that_ends_with_a_newline_round_trips_to_itself() -> None:
    # The stamp the engine records is the rendered body; `extract` must agree with it for a
    # template whose content ends in a newline, which every real template does.
    out = upsert(BEFORE, "harness", "one\ntwo\n", Style.MARKDOWN)
    assert extract(out, "harness", Style.MARKDOWN) == "one\ntwo"
    assert upsert(out, "harness", "one\ntwo\n", Style.MARKDOWN) == out


def test_crlf_endings_outside_the_region_survive() -> None:
    text = "# Title\r\n\r\nProse.\r\n"
    out = upsert(text, "harness", "one", Style.MARKDOWN)
    assert out.startswith("# Title\r\n\r\nProse.\r\n")
    assert extract(out, "harness", Style.MARKDOWN) == "one"


def test_an_exotic_line_separator_is_not_normalised() -> None:
    # `str.splitlines()` splits on eleven characters; a rewrite built on it silently turns a
    # form feed inside somebody's prose into a line break.
    text = "para one\x0cpara two\n"
    out = upsert(text, "harness", "one", Style.HASH)
    assert out.startswith("para one\x0cpara two\n")


def test_two_names_coexist() -> None:
    out = upsert(upsert(BEFORE, "a", "A", Style.HASH), "b", "B", Style.HASH)
    assert extract(out, "a", Style.HASH) == "A"
    assert extract(out, "b", Style.HASH) == "B"


def test_an_absent_region_extracts_as_none() -> None:
    assert extract(BEFORE, "harness", Style.MARKDOWN) is None


def test_an_indented_marker_is_still_found() -> None:
    text = BEFORE + "  <!-- stayfixed:harness:begin -->\nbody\n  <!-- stayfixed:harness:end -->\n"
    assert extract(text, "harness", Style.MARKDOWN) == "body"


def test_drop_removes_the_region_and_its_markers() -> None:
    out = drop(upsert(BEFORE, "harness", "one", Style.MARKDOWN), "harness", Style.MARKDOWN)
    assert "stayfixed" not in out
    assert out == BEFORE


def test_dropping_an_absent_region_changes_nothing() -> None:
    assert drop(BEFORE, "harness", Style.MARKDOWN) == BEFORE


def test_an_unterminated_region_refuses() -> None:
    broken = BEFORE + "<!-- stayfixed:harness:begin -->\nbody\n"
    with pytest.raises(RegionError, match="end"):
        extract(broken, "harness", Style.MARKDOWN)


def test_two_regions_of_one_name_refuse() -> None:
    doubled = upsert(BEFORE, "harness", "one", Style.MARKDOWN)
    doubled += "<!-- stayfixed:harness:begin -->\nsecond\n<!-- stayfixed:harness:end -->\n"
    with pytest.raises(RegionError, match="twice"):
        extract(doubled, "harness", Style.MARKDOWN)


def test_a_doubled_begin_marker_with_one_end_refuses() -> None:
    text = (
        BEFORE + "<!-- stayfixed:harness:begin -->\nfirst\n"
        "<!-- stayfixed:harness:begin -->\nsecond\n<!-- stayfixed:harness:end -->\n"
    )
    with pytest.raises(RegionError, match="twice"):
        extract(text, "harness", Style.MARKDOWN)


def test_a_marker_for_another_name_is_not_a_terminator() -> None:
    text = (
        BEFORE
        + "<!-- stayfixed:a:begin -->\nA\n<!-- stayfixed:b:end -->\n<!-- stayfixed:a:end -->\n"
    )
    assert extract(text, "a", Style.MARKDOWN) == "A\n<!-- stayfixed:b:end -->"


def test_an_end_marker_with_no_beginning_refuses() -> None:
    # The mirror of the unterminated case above, and the one that used to read as "region
    # absent": a begin line somebody deleted, or a merge that kept one side's end marker.
    orphaned = BEFORE + "<!-- stayfixed:harness:end -->\n"
    with pytest.raises(RegionError, match="no beginning"):
        extract(orphaned, "harness", Style.MARKDOWN)


def test_an_end_marker_with_no_beginning_refuses_instead_of_doubling_itself() -> None:
    # Why it has to refuse rather than return None. Treated as absent, `upsert` appended a fresh
    # block and left one begin against two ends — a file only `_bounds` could have written and
    # only a person can now repair, with `drop` refusing it too so `uninstall` could not finish.
    orphaned = BEFORE + "<!-- stayfixed:harness:end -->\n"
    with pytest.raises(RegionError, match="no beginning"):
        upsert(orphaned, "harness", "one", Style.MARKDOWN)
    with pytest.raises(RegionError, match="no beginning"):
        drop(orphaned, "harness", Style.MARKDOWN)


def test_an_end_marker_for_another_name_is_not_an_orphan() -> None:
    # The anti-overreach guard: the refusal is keyed on this region's own marker, so a file
    # carrying somebody else's closed region still reads as "absent" for this name.
    text = BEFORE + "<!-- stayfixed:other:end -->\n"
    assert extract(text, "harness", Style.MARKDOWN) is None


def test_a_hash_region_reads_lines_where_git_does() -> None:
    # A hash-style region lives in a file git reads (`.gitignore`, `info/exclude`), and git ends a
    # line at `\n` alone: a last line ending in a lone `\r` is one git still has to see ended, or
    # the block's first marker is glued onto it and that pattern is lost. A Markdown region keeps
    # reading a lone `\r` as a line end, which is what a Markdown reader does.
    #
    # Mutations: `mutations/`'s "a hash region reads a lone carriage return as a line end"
    # and "a hash region finds a marker across a lone carriage return".
    begin, _ = markers("x", Style.HASH)
    assert upsert("/a\n/b\r", "x", "/c", Style.HASH).startswith(f"/a\n/b\r\n{begin}\n")
    # In a file that ends its lines with `\r\n`, that last line is still ended by `\n` alone:
    # git drops one `\r` before a `\n`, so `/b\r\r\n` would read as the pattern `/b\r`.
    assert upsert("/a\r\n/b\r", "x", "/c", Style.HASH).startswith(f"/a\r\n/b\r\n{begin}\r\n")
    md_begin, _ = markers("x", Style.MARKDOWN)
    assert upsert("a\nb\r", "x", "c", Style.MARKDOWN).startswith(f"a\nb\r{md_begin}\n")
    # And a marker is a marker only on a line of its own, as git splits it: glued onto the line
    # before it by a lone `\r`, it is not one, and the end marker then has no beginning.
    with pytest.raises(RegionError, match="no beginning"):
        extract(f"/a\r{begin}\n/c\n# stayfixed:x:end\n", "x", Style.HASH)
