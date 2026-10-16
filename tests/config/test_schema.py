from __future__ import annotations

import pytest

from stayfixed.config.schema import Budgets, NativeCaps
from stayfixed.presets import load_preset


def test_recommended_preset_carries_every_budget_and_cap_the_schema_knows() -> None:
    preset = load_preset("recommended")
    assert set(preset["budgets"]) == set(Budgets.NAMES)
    assert set(preset["native_caps"]) == set(NativeCaps.NAMES)


def test_effective_budget_is_the_configured_value_else_the_presets() -> None:
    # A configured value stands in either direction. Mutation (`mutations/`'s "a budget is still
    # only ever lowered"): the raise reads 1100.
    budgets = Budgets(
        preset={"memory_index_words": 1100, "agents_md_lines": 300, "status_lines": 50},
        configured={"agents_md_lines": 250, "memory_index_words": 5000},
    )
    assert budgets.effective("agents_md_lines") == 250
    assert budgets.effective("memory_index_words") == 5000
    assert budgets.effective("status_lines") == 50
    assert budgets.overrides == {"agents_md_lines": 250, "memory_index_words": 5000}


def test_unknown_budget_name_is_a_key_error() -> None:
    # The preset carries the name so that only the `NAMES` check can raise: with `preset={}`
    # the empty dict's own lookup raises the identical KeyError and the check is unfalsifiable.
    with pytest.raises(KeyError):
        Budgets(preset={"no_such_budget": 999}, configured={}).effective("no_such_budget")
