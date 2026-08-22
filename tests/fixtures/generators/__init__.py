"""Deterministic synthetic SEG-Y generators. Specification §6.6 — binding.

**No proprietary or restricted data enters this repository, ever.** Every fixture is
generated here, by committed code, with a fixed seed. The generator *is* the fixture:
it is smaller than the bytes, it is diffable, and it cannot drift from what produced it.

Determinism is not a nicety. G6 requires two independent runs to produce identical array
bytes, and a fixture that varies between runs makes that gate unmeasurable.
"""

from __future__ import annotations

from tests.fixtures.generators.poststack3d import (
    DETERMINISTIC_TEXT,
    PLANTED_BYTES,
    SyntheticSegy,
    deterministic_text,
    make_poststack3d,
    read_planted,
)

__all__ = [
    "DETERMINISTIC_TEXT",
    "PLANTED_BYTES",
    "SyntheticSegy",
    "deterministic_text",
    "make_poststack3d",
    "read_planted",
]
