"""Exact identity, correct on every value a SEG-Y can carry. OPEN_DEBTS D52, DECISIONS.md D-0088.

Every value comparison in the engine was ``np.array_equal``, which says ``NaN != NaN``. Measured:
a byte-correct store from an IEEE float32 source containing NaN failed Plane 4 with
``expected: nan, observed: nan``, and G6 called two identical ingests non-deterministic.

``equal_nan=True`` is not the fix: it calls any two NaNs equal regardless of payload, which is
looser than an identity contract. **Floating and complex arrays are compared bit for bit**, the
strictest exact comparison there is. It is correct on NaN, on every NaN payload and on the sign of
zero. Structured arrays are compared field by field, because their alignment padding carries no
value and must not decide a verdict. Everything else keeps ``np.array_equal``.

Floats are viewed as the unsigned integer of the same width, not as bytes, so the temporary a
comparison allocates is no larger than ``np.array_equal``'s at survey scale (D38).
"""

from __future__ import annotations

from typing import Any

import numpy as np

_UNSIGNED = {1: np.uint8, 2: np.uint16, 4: np.uint32, 8: np.uint64}


def _bits(array: np.ndarray) -> np.ndarray:
    contiguous = np.ascontiguousarray(array)
    unit = contiguous.dtype.itemsize
    if contiguous.dtype.kind == "c":
        unit //= 2
    return contiguous.view(_UNSIGNED.get(unit, np.uint8))


def identical(left: Any, right: Any) -> bool:
    """True only when ``left`` and ``right`` hold the same values, NaN included, exactly.

    Args:
        left: An array or scalar.
        right: An array or scalar.

    Returns:
        Whether they are identical: same shape, and for floating and complex dtypes the same
        bits; for structured dtypes every field identical; otherwise ``np.array_equal``.
    """
    a, b = np.asarray(left), np.asarray(right)
    if a.shape != b.shape:
        return False
    if a.dtype.names or b.dtype.names:
        if a.dtype.names != b.dtype.names:
            return False
        return all(identical(a[name], b[name]) for name in a.dtype.names or ())
    if a.dtype.kind in "fc" or b.dtype.kind in "fc":
        if a.dtype != b.dtype:
            return False
        return bool(np.array_equal(_bits(a), _bits(b)))
    return bool(np.array_equal(a, b))
