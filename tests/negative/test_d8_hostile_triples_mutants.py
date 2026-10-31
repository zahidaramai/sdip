"""**D8 residual 3 beyond pairs.** Probe P18: three hostilities at once, and seeded byte mutants.

Every file runs through the unchanged D8 child and is judged by P15's six clauses
(:func:`tests.negative.test_d8_hostile_pairs.falsifier_hits`). By the registration, the first
10 sampled triples and mutants 0-9 run by default; the rest are ``campaign``.
"""

from __future__ import annotations

import pytest

from tests.fixtures.generators.hostile import (
    MUTANT_COUNT,
    TRIPLE_SAMPLE,
    TRIPLES,
    build_combination,
    build_mutant,
    mutant_name,
)
from tests.negative.test_d8_hostile_corpus import _run_one
from tests.negative.test_d8_hostile_pairs import falsifier_hits, harness  # noqa: F401

pytestmark = [pytest.mark.negative, pytest.mark.integration, pytest.mark.slow]

DEFAULT_SLICE = 10
"""Registered: the first 10 of each set run by default."""


def _marks(index: int) -> tuple[pytest.MarkDecorator, ...]:
    return () if index < DEFAULT_SLICE else (pytest.mark.campaign,)


TRIPLE_PARAMS = [
    pytest.param(t, id="+".join(t), marks=_marks(i)) for i, t in enumerate(TRIPLE_SAMPLE)
]
MUTANT_PARAMS = [pytest.param(i, id=mutant_name(i), marks=_marks(i)) for i in range(MUTANT_COUNT)]


def test_the_sets_are_the_registered_ones():
    """P18 registered 1,177 triples, a 300-triple sample, and 400 mutants."""
    assert len(TRIPLES) == 1177
    assert len(TRIPLE_SAMPLE) == 300
    assert len(set(TRIPLE_SAMPLE)) == 300
    assert set(TRIPLE_SAMPLE) <= set(TRIPLES)
    assert MUTANT_COUNT == 400


def test_a_mutant_is_deterministic_and_differs_from_the_base(tmp_path):
    """Non-vacuity for the mutant builder: same seed, same bytes; and something changed."""
    from tests.fixtures.generators.hostile import build_positive_control

    base = build_positive_control(tmp_path / "base").read_bytes()
    one = build_mutant(tmp_path / "a", 3).read_bytes()
    two = build_mutant(tmp_path / "b", 3).read_bytes()
    assert one == two
    assert one != base
    assert len(one) == len(base)


@pytest.mark.parametrize("triple", TRIPLE_PARAMS)
def test_no_triple_crashes_leaks_or_escapes(harness, triple):  # noqa: F811
    root, store = harness
    source = build_combination(root / "corpus", triple)
    hits = falsifier_hits(_run_one("+".join(triple), "triple", source, root, store))
    assert hits == [], f"{'+'.join(triple)}: {hits}"


@pytest.mark.parametrize("i", MUTANT_PARAMS)
def test_no_mutant_crashes_leaks_or_escapes(harness, i):  # noqa: F811
    root, store = harness
    source = build_mutant(root / "corpus", i)
    hits = falsifier_hits(_run_one(mutant_name(i), "mutant", source, root, store))
    assert hits == [], f"{mutant_name(i)}: {hits}"
