from __future__ import annotations

import json

import pytest

from stayfixed.scaffold.entries import (
    EntriesError,
    apply_entries,
    mark,
    marker_id,
    owned,
    owned_ids,
)


def document(*commands: tuple[str, str]) -> str:
    return json.dumps(
        {
            "hooks": {
                event: [{"matcher": "Bash", "hooks": [{"type": "command", "command": cmd}]}]
                for event, cmd in commands
            }
        },
        indent=2,
    )


def commands_of(text: str, event: str) -> list[str]:
    # `.get("hooks", {})` and not `["hooks"]`: apply_entries drops an empty "hooks" key
    # entirely, which is exactly what the retired-id case leaves behind.
    raw = json.loads(text)
    return [
        hook["command"] for group in raw.get("hooks", {}).get(event, []) for hook in group["hooks"]
    ]


def wanted(event: str, entry_id: str, command: str) -> dict[str, list[dict[str, object]]]:
    return {
        event: [
            {
                "matcher": "Bash",
                "hooks": [{"type": "command", "command": mark(command, entry_id)}],
            }
        ]
    }


def test_marker_id_reads_the_id_a_command_claims() -> None:
    assert marker_id("run.sh hook PreToolUse  # stayfixed:bg-cleanup") == "bg-cleanup"
    assert marker_id("run.sh hook PreToolUse") is None


def test_a_marker_that_is_not_at_the_end_is_not_an_id() -> None:
    assert marker_id("run.sh  # stayfixed:bg-cleanup then more text") is None


def test_mark_is_idempotent() -> None:
    once = mark("run.sh", "bg-cleanup")
    assert mark(once, "bg-cleanup") == once


def test_a_marked_entry_is_replaced() -> None:
    before = document(("PreToolUse", mark("old.sh", "bg-cleanup")))
    after = apply_entries(before, wanted("PreToolUse", "bg-cleanup", "new.sh"))
    assert commands_of(after, "PreToolUse") == [mark("new.sh", "bg-cleanup")]


def test_a_foreign_entry_is_left_alone() -> None:
    before = document(("PreToolUse", "someone-elses-guard.sh"))
    after = apply_entries(before, wanted("PreToolUse", "bg-cleanup", "new.sh"))
    assert "someone-elses-guard.sh" in commands_of(after, "PreToolUse")


def test_a_group_mixing_a_marked_and_a_foreign_entry_keeps_the_foreign_one() -> None:
    raw = {
        "hooks": {
            "PreToolUse": [
                {
                    "matcher": "Bash",
                    "hooks": [
                        {"type": "command", "command": "theirs.sh"},
                        {"type": "command", "command": mark("old.sh", "bg-cleanup")},
                    ],
                }
            ]
        }
    }
    after = apply_entries(json.dumps(raw), wanted("PreToolUse", "bg-cleanup", "new.sh"))
    assert commands_of(after, "PreToolUse") == ["theirs.sh", mark("new.sh", "bg-cleanup")]


def test_a_retired_id_is_removed() -> None:
    before = document(("PreToolUse", mark("old.sh", "retired")))
    after = apply_entries(before, {})
    assert commands_of(after, "PreToolUse") == []
    assert "hooks" not in json.loads(after)


def test_an_event_with_no_stayfixed_entry_is_untouched() -> None:
    before = document(("PostToolUse", "theirs.sh"))
    after = apply_entries(before, wanted("PreToolUse", "bg-cleanup", "new.sh"))
    assert commands_of(after, "PostToolUse") == ["theirs.sh"]


def test_unrelated_top_level_keys_survive() -> None:
    raw = json.loads(document(("PreToolUse", "theirs.sh")))
    raw["permissions"] = {"deny": ["Read(./.env)"]}
    after = apply_entries(json.dumps(raw), wanted("PreToolUse", "bg", "new.sh"))
    assert json.loads(after)["permissions"] == {"deny": ["Read(./.env)"]}


def test_owned_covers_only_the_marked_entries() -> None:
    # The stamp the manifest records. A user's unrelated edit beside the hooks must not read
    # as a hand edit of stayfixed's own entries, or `upgrade` freezes them forever.
    with_ours = apply_entries(
        document(("PreToolUse", "theirs.sh")), wanted("PreToolUse", "bg", "x")
    )
    raw = json.loads(with_ours)
    raw["permissions"] = {"deny": ["Read(./.env)"]}
    assert owned(with_ours) == owned(json.dumps(raw))
    assert "theirs.sh" not in owned(with_ours)
    assert "stayfixed:bg" in owned(with_ours)


def test_owned_is_insensitive_to_the_key_order_inside_an_entry() -> None:
    # The load-bearing half of the stamp. Reordering the keys of an entry changes no value, so
    # the stamp must not move: if it does, the artifact reads as hand-edited for good, and the
    # next `--force` writes the same bytes back and still disagrees with the record.
    installed = apply_entries("", wanted("PreToolUse", "bg-cleanup", "new.sh"))
    raw = json.loads(installed)
    entry = raw["hooks"]["PreToolUse"][0]["hooks"][0]
    reordered = dict(reversed(list(entry.items())))
    assert list(reordered) != list(entry)
    raw["hooks"]["PreToolUse"][0]["hooks"][0] = reordered
    assert owned(json.dumps(raw)) == owned(installed)


def test_owned_ids_reports_event_by_id() -> None:
    before = document(("PreToolUse", mark("a.sh", "bg-cleanup")))
    assert owned_ids(before) == {"bg-cleanup": "PreToolUse"}


def test_a_malformed_document_refuses() -> None:
    with pytest.raises(EntriesError):
        apply_entries("{not json", {})


# Valid JSON nested past what `json.loads` follows: it raises `RecursionError` on every supported
# Python, and a settings document is a file a clone can commit.
NESTED = "[" * 200_000 + "]" * 200_000


def test_a_document_nested_past_the_parsers_reach_refuses_like_a_malformed_one() -> None:
    # `RecursionError` used to leave the engine past every caller's catch: `doctor`'s
    # `hook-entries` read "this check could not run" and `attach` ended in an internal error, on a
    # file the repository chose. Mutation (oracle): `mutations/`'s "the settings engine lets a
    # nested document raise past its refusal" -> both raise `RecursionError`.
    nested = '{"hooks": ' + NESTED + "}"
    with pytest.raises(EntriesError, match="nested deeper"):
        owned_ids(nested)
    with pytest.raises(EntriesError, match="nested deeper"):
        apply_entries(nested, {})


# An integer literal longer than the interpreter converts, 4,300 digits by default on every
# supported Python: `json.loads` raises a plain `ValueError` for it, not a `JSONDecodeError`.
LONG_NUMBER = "1" * 5_000


def test_a_document_holding_a_number_past_the_parsers_reach_refuses_like_a_malformed_one() -> None:
    # The `ValueError` left the engine past every caller's catch, as `RecursionError` did:
    # `doctor`'s `hook-entries` read "this check could not run" and `attach` ended in an internal
    # error, on a file the repository chose. Mutation (oracle): `mutations/`'s "the settings engine
    # lets a number past the parser's reach raise past its refusal" -> both raise `ValueError`.
    long = '{"hooks": {}, "n": ' + LONG_NUMBER + "}"
    with pytest.raises(EntriesError, match="number longer"):
        owned_ids(long)
    with pytest.raises(EntriesError, match="number longer"):
        apply_entries(long, {})


def test_an_empty_document_gains_the_wanted_entries() -> None:
    after = apply_entries("", wanted("PreToolUse", "bg-cleanup", "new.sh"))
    assert commands_of(after, "PreToolUse") == [mark("new.sh", "bg-cleanup")]


def test_a_group_that_is_not_an_object_refuses_rather_than_vanishing() -> None:
    # `apply_entries` writes the structure it built back over the user's file, so a shape it
    # filtered out is a shape it deleted. A non-list at `hooks.<event>` already refused; a group
    # inside that list got no such treatment.
    raw = {"hooks": {"PreToolUse": ["not a group"]}}
    with pytest.raises(EntriesError, match="not an object"):
        apply_entries(json.dumps(raw), wanted("PreToolUse", "bg-cleanup", "new.sh"))


def test_a_group_whose_hooks_value_is_not_a_list_refuses_rather_than_vanishing() -> None:
    # The shape a hand-written settings file most plausibly carries: the single entry written as
    # an object where the file format wants a list of them. Filtered away, the command inside it
    # was silently deleted and the promise that a foreign entry survives untouched was false.
    raw = {
        "hooks": {
            "PreToolUse": [
                {"matcher": "Write", "hooks": {"type": "command", "command": "theirs.sh"}}
            ]
        }
    }
    with pytest.raises(EntriesError, match="not a list"):
        apply_entries(json.dumps(raw), wanted("PreToolUse", "bg-cleanup", "new.sh"))


def test_owned_ids_refuses_the_shapes_apply_entries_refuses() -> None:
    # The provenance list reads the same structure. Under-reporting it silently would have
    # `doctor` claim stayfixed owns nothing in a file it does own.
    raw = {"hooks": {"PostToolUse": [{"matcher": "Bash", "hooks": 7}]}}
    with pytest.raises(EntriesError, match="not a list"):
        owned_ids(json.dumps(raw))


def test_an_entry_that_is_not_an_object_refuses_rather_than_vanishing() -> None:
    # The third shape, and the one that hides best: a command written as a bare string beside a
    # proper entry, inside a group whose own shape is fine. Filtered out, it was deleted without
    # a trace and the group it sat in was written back looking untouched.
    raw = {
        "hooks": {
            "PreToolUse": [
                {
                    "matcher": "Write",
                    "hooks": ["theirs.sh", {"type": "command", "command": "ok.sh"}],
                }
            ]
        }
    }
    with pytest.raises(EntriesError, match="holds an entry that is not an object"):
        apply_entries(json.dumps(raw), wanted("PreToolUse", "bg-cleanup", "new.sh"))


def test_several_well_formed_entries_in_one_group_are_not_swept_up() -> None:
    # The anti-overreach guard for the refusal above: the same group with its bare string written
    # as a proper entry must pass and must return both of them. The refusal has to key on a shape
    # that is actually malformed, never on a group holding more than one entry.
    raw = {
        "hooks": {
            "PreToolUse": [
                {
                    "matcher": "Write",
                    "hooks": [
                        {"type": "command", "command": "theirs.sh"},
                        {"type": "command", "command": "ok.sh"},
                    ],
                }
            ]
        }
    }
    after = apply_entries(json.dumps(raw), wanted("PreToolUse", "bg-cleanup", "new.sh"))
    assert commands_of(after, "PreToolUse") == [
        "theirs.sh",
        "ok.sh",
        mark("new.sh", "bg-cleanup"),
    ]


def test_a_well_formed_foreign_group_is_still_left_alone() -> None:
    # The anti-overreach guard for the two refusals above: only a shape that is actually
    # malformed refuses, and a foreign group the engine can read keeps its matcher and its place.
    raw = {
        "hooks": {
            "PreToolUse": [
                {"matcher": "Write", "hooks": [{"type": "command", "command": "theirs.sh"}]}
            ]
        }
    }
    after = apply_entries(json.dumps(raw), wanted("PreToolUse", "bg-cleanup", "new.sh"))
    groups = json.loads(after)["hooks"]["PreToolUse"]
    assert groups[0] == raw["hooks"]["PreToolUse"][0]


def test_event_keys_apply_entries_adds_land_in_sorted_order() -> None:
    # `apply_entries` dumps without `sort_keys`, so the `sorted()` it iterates is the only thing
    # fixing where a new event key lands. Without it the order is the set's, which is not stable
    # between runs, so two machines installing the same artifacts produce two different files and
    # the diff a reviewer reads is noise. An event already in the document keeps its position,
    # and the order is not the order `wanted` happens to be written in either.
    before = document(("Zed", "theirs.sh"))
    after = apply_entries(
        before,
        {
            **wanted("Beta", "b", "b.sh"),
            **wanted("Alpha", "a", "a.sh"),
            **wanted("Mid", "m", "m.sh"),
        },
    )
    assert list(json.loads(after)["hooks"]) == ["Zed", "Alpha", "Beta", "Mid"]
