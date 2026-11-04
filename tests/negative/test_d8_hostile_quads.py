"""**D8, four hostilities at once.** Probe P29: every four-class combination of the corpus.

Every file runs through the unchanged D8 child and is judged by P15's six clauses
(:func:`tests.negative.test_d8_hostile_pairs.falsifier_hits`). By the registration, the first
10 members of :data:`QUADS` run by default; the rest are ``campaign``.
"""

from __future__ import annotations

import pytest

from tests.fixtures.generators.hostile import _CLASS_OF, QUADS, build_combination
from tests.negative.test_d8_hostile_corpus import _run_one
from tests.negative.test_d8_hostile_pairs import falsifier_hits, harness  # noqa: F401

pytestmark = [pytest.mark.negative, pytest.mark.integration, pytest.mark.slow]

DEFAULT_SLICE = 10
"""Registered: the first 10 quads run by default."""

QUAD_PARAMS = [
    pytest.param(q, id="+".join(q), marks=() if i < DEFAULT_SLICE else (pytest.mark.campaign,))
    for i, q in enumerate(QUADS)
]


def test_the_quad_set_is_the_registered_one():
    """P29 registered N = 3,632, each member from four different classes; drift is a new probe."""
    assert len(QUADS) == 3632
    assert len(set(QUADS)) == 3632
    assert all(len({_CLASS_OF[n] for n in q}) == 4 for q in QUADS)


def test_a_quad_carries_all_four_mutations(tmp_path):
    """Non-vacuity for the builder: a quad differs from each of its three-member subsets."""
    quad = QUADS[-1]
    whole = build_combination(tmp_path / "q", quad).read_bytes()
    for drop in range(4):
        part = tuple(n for i, n in enumerate(quad) if i != drop)
        assert build_combination(tmp_path / f"t{drop}", part).read_bytes() != whole


@pytest.mark.parametrize("quad", QUAD_PARAMS)
def test_no_quad_crashes_leaks_or_escapes(harness, quad):  # noqa: F811
    root, store = harness
    source = build_combination(root / "corpus", quad)
    hits = falsifier_hits(_run_one("+".join(quad), "quad", source, root, store))
    assert hits == [], f"{'+'.join(quad)}: {hits}"
