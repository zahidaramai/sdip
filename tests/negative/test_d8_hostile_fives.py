"""**D8, five hostilities at once.** Probe P34: the five-class combinations, in a seeded order.

Every file runs through the unchanged D8 child and is judged by P15's six clauses
(:func:`tests.negative.test_d8_hostile_pairs.falsifier_hits`). By the registration, the first
10 members of :data:`FIVE_ORDER` run by default; the rest are ``campaign``.
"""

from __future__ import annotations

import pytest

from tests.fixtures.generators.hostile import _CLASS_OF, FIVE_ORDER, FIVES, build_combination
from tests.negative.test_d8_hostile_corpus import _run_one
from tests.negative.test_d8_hostile_pairs import falsifier_hits, harness  # noqa: F401

pytestmark = [pytest.mark.negative, pytest.mark.integration, pytest.mark.slow]

DEFAULT_SLICE = 10
"""Registered: the first 10 of the seeded order run by default."""

FIVE_PARAMS = [
    pytest.param(f, id="+".join(f), marks=() if i < DEFAULT_SLICE else (pytest.mark.campaign,))
    for i, f in enumerate(FIVE_ORDER)
]


def test_the_five_set_and_its_order_are_the_registered_ones():
    """P34 registered N = 6,496 and a seeded permutation of them; drift is a new probe."""
    assert len(FIVES) == 6496
    assert len(set(FIVES)) == 6496
    assert all(len({_CLASS_OF[n] for n in f}) == 5 for f in FIVES)
    assert sorted(FIVE_ORDER) == sorted(FIVES)
    assert FIVE_ORDER[:3] != FIVES[:3], "the order is a permutation, not combinations order"


def test_a_five_carries_all_five_mutations(tmp_path):
    """Non-vacuity for the builder: a five differs from each of its four-member subsets."""
    five = FIVE_ORDER[0]
    whole = build_combination(tmp_path / "f", five).read_bytes()
    for drop in range(5):
        part = tuple(n for i, n in enumerate(five) if i != drop)
        assert build_combination(tmp_path / f"q{drop}", part).read_bytes() != whole


@pytest.mark.parametrize("five", FIVE_PARAMS)
def test_no_five_crashes_leaks_or_escapes(harness, five):  # noqa: F811
    root, store = harness
    source = build_combination(root / "corpus", five)
    hits = falsifier_hits(_run_one("+".join(five), "five", source, root, store))
    assert hits == [], f"{'+'.join(five)}: {hits}"
