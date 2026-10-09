from __future__ import annotations

import pytest

from stayfixed.errors import Refusal
from stayfixed.identifiers import Identifiers


def test_the_default_prefix_reads_and_writes_three_digit_identifiers() -> None:
    ids = Identifiers("BR")
    assert ids.is_identifier("BR-042")
    assert ids.number("BR-042") == 42
    assert ids.format(7) == "BR-007"
    assert ids.format(2345) == "BR-2345"


def test_reading_the_number_out_of_a_non_identifier_is_refused() -> None:
    # `number` is `Identifiers`' one lossy reader, and the allocator in `stayfixed.ledger.write`
    # is its first caller: it asks `is_identifier` first, so this branch is reached only by a
    # caller that does not — and a caller that guesses a number out of a filename that is not an
    # identifier hands out an occupied one.
    # Oracle: `mutations/`'s "reading the number out of a non-identifier answers zero
    # instead of refusing".
    with pytest.raises(Refusal):
        Identifiers("BR").number("BR-42")


def test_fewer_than_three_digits_is_not_an_identifier() -> None:
    # `renumber` and every reader enforce this: two digits is a different shape, and a reader
    # that accepts it counts headings and filenames that were never identifiers at all.
    # Mutation: change `{3,}` to `+` in `DIGITS` — reddens this.
    assert not Identifiers("BR").is_identifier("BR-42")


def test_a_mention_is_bounded_by_word_edges() -> None:
    ids = Identifiers("BR")
    assert ids.mention.findall("see BR-404 and XBR-405 and BR-4060x") == ["BR-404"]


def test_the_fixes_claim_shares_the_digit_rule() -> None:
    # The plan lint reads this; one `DIGITS` for the ledger and the lint, so the two cannot
    # disagree about the minimum. Mutation: build `fixes` with `\d+` — the second assertion reddens.
    ids = Identifiers("BR")
    assert ids.fixes.search("Fixes BR-042.") is not None
    assert ids.fixes.search("Fixes BR-42.") is None


def test_another_prefix_changes_every_pattern_together() -> None:
    ids = Identifiers("QA")
    assert ids.is_identifier("QA-001")
    assert not ids.is_identifier("BR-001")
    assert ids.mention.findall("QA-001 BR-001") == ["QA-001"]
    assert ids.fixes.search("Fixes QA-001") is not None and ids.fixes.search("Fixes BR-001") is None


@pytest.mark.parametrize("prefix", ["", "br", "B R", "-BR", "BR-", "TOOLONGXX", "B(R"])
def test_a_prefix_outside_the_contract_is_refused_before_it_meets_a_regex(prefix: str) -> None:
    # `id_prefix` is repository-controlled, and a repository is untrusted input. It is interpolated
    # into regular expressions and into filenames, so it is held to a shape first. Mutation: drop
    # the `PREFIX.match` check — the `B(R` case then raises `re.error` (an internal error, exit 2 by
    # accident) and the others build patterns that match nothing; this test reddens on the exception
    # type for `B(R` and on the missing refusal for the rest.
    with pytest.raises(Refusal):
        Identifiers(prefix)
