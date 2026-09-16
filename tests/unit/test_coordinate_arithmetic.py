"""Plane 3's derived-coordinate leg reproduces the WRITER's arithmetic, exactly.

**The defect (D47, DECISIONS.md D-0087).** SEG-Y says a negative coordinate scalar is a
*divisor* and says nothing about rounding. ``mdio`` 1.2.1 implements it as multiplication
by a reciprocal — as OpenVDS and OpendTect also do — and the verifier implemented it as
division. In float64 the two disagree by one unit in the last place on 12-16 of the 100
possible final-two-digit residues at a given magnitude. Every raw header byte was
identical; the verifier reported FAIL anyway.

The fix is not a tolerance: it is the same arithmetic, so the comparison stays exact and a
single-ulp corruption of a stored cell still fails. The literal below is the reference, so
a future ``mdio`` pin that changes its arithmetic fails here rather than silently at a
consumer's survey.
"""

from __future__ import annotations

import numpy as np
import pytest

from sdip.equivalence.planes import _scale_coordinate, correctly_rounded_differences

SCALARS = (-10000, -1000, -100, -10, -1, 0, 1, 10, 100, 1000, 10000)
MAGNITUDES = (0, 1_000_000, 43_636_400, 646_920_000, 2_147_483_500)


def writer(raw: np.ndarray, scalar: int, dtype: np.dtype) -> np.ndarray:
    """``mdio`` 1.2.1, ``mdio/segy/scalar.py`` ``_apply_coordinate_scalar``, verbatim in effect.

    The array is the store's coordinate dtype, filled from the raw int32 header values
    (``mdio/ingestion/coordinates.py``); the factor is a Python scalar. A scalar of 0 never
    reaches this function upstream: rev 0/1 raise, rev 2+ normalise it to 1.
    """
    data = np.asarray(raw).astype(dtype)
    scalar = 1 if scalar == 0 else scalar
    factor = 1 / scalar if scalar < 0 else scalar
    return data * abs(factor)


@pytest.mark.parametrize("dtype", [np.float64, np.float32])
@pytest.mark.parametrize("scalar", SCALARS)
def test_every_residue_at_every_magnitude_matches_the_writer(scalar, dtype):
    raw = np.concatenate([np.arange(m, m + 100, dtype=np.int64) for m in MAGNITUDES])
    raw = raw[raw <= np.iinfo(np.int32).max].astype(np.int32)
    expected = writer(raw, scalar, np.dtype(dtype))
    observed = np.array([_scale_coordinate(v, scalar, np.dtype(dtype)) for v in raw])
    assert observed.dtype == np.dtype(dtype)
    assert np.array_equal(observed, expected), scalar


def test_the_value_that_exposed_the_defect():
    """43636410 at -100: the writer stores 436364.10000000003, not 436364.1."""
    value = _scale_coordinate(np.int32(43_636_410), -100, np.dtype(np.float64))
    assert value == 436364.10000000003
    assert value != 43_636_410 / 100


def test_the_divergence_from_the_correctly_rounded_quotient_is_counted_not_hidden():
    """The divergence from the correctly rounded quotient is recorded, not hidden.

    SEG-Y defines a divisor and no rounding rule, so this is evidence rather than a failure.
    """
    raw = np.arange(43_636_400, 43_636_500, dtype=np.int32)
    assert correctly_rounded_differences(raw, np.full(100, -100), np.dtype(np.float64)) == 16
    assert correctly_rounded_differences(raw, np.full(100, 100), np.dtype(np.float64)) == 0
