"""Exact comparison that is correct on every value a SEG-Y can carry, NaN included.

**D52 audit (DECISIONS.md D-0088).** Every value comparison in the engine used
``np.array_equal``, which says ``NaN != NaN``. Measured: a byte-correct store built from an IEEE
float32 source containing NaN FAILED Plane 4 (``expected: nan, observed: nan``) and G6 reported two
identical ingests as non-deterministic. IEEE-float SEG-Y with NaN exists in real data.

``equal_nan=True`` would be the wrong fix: it calls any two NaNs equal whatever their payload,
which is looser than the contract. Bit identity is the strictest exact comparison there is, and
it is correct on NaN, on the sign of zero, and on every payload.
"""

from __future__ import annotations

import numpy as np
from sdip.equivalence.exact import identical


def _nan_with_payload(payload: int) -> np.float32:
    return np.array([0x7F800000 | payload], dtype=np.uint32).view(np.float32)[0]


def test_nan_is_identical_to_the_same_nan():
    a = np.array([1.0, np.nan, 3.0], dtype=np.float32)
    assert identical(a, a.copy())
    assert not np.array_equal(a, a.copy()), "the defect this replaces, measured"


def test_a_different_nan_payload_is_not_identical():
    """Stricter than equal_nan=True, which would call these equal."""
    a = np.array([_nan_with_payload(1)], dtype=np.float32)
    b = np.array([_nan_with_payload(2)], dtype=np.float32)
    assert np.array_equal(a, b, equal_nan=True)
    assert not identical(a, b)


def test_the_sign_of_zero_is_not_ignored():
    assert not identical(np.array([0.0], np.float32), np.array([-0.0], np.float32))


def test_one_flipped_bit_is_not_identical():
    a = np.array([1.5], dtype=np.float32)
    b = (a.view(np.uint32) ^ np.uint32(1)).view(np.float32)
    assert not identical(a, b)


def test_shapes_and_dtypes_still_decide():
    assert not identical(np.zeros((2, 2), np.float32), np.zeros(4, np.float32))
    assert identical(np.arange(4, dtype=np.int32), np.arange(4, dtype=np.int32))
    assert not identical(np.arange(4, dtype=np.int32), np.arange(1, 5, dtype=np.int32))


def test_zero_dimensional_arrays_compare():
    assert identical(np.float64(np.nan), np.float64(np.nan))


def test_structured_arrays_compare_field_by_field_not_by_padding_bytes():
    aligned = np.dtype([("a", np.int8), ("b", np.float32)], align=True)
    left = np.zeros(2, dtype=aligned)
    right = np.zeros(2, dtype=aligned)
    left["b"] = np.nan
    right["b"] = np.nan
    left.view(np.uint8)[1] = 0xAB  # alignment padding, which carries no value
    assert identical(left, right)
    right["a"][0] = 1
    assert not identical(left, right)
