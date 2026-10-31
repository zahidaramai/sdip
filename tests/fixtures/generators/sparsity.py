"""Grids on each side of MDIO's sparsity bound, for probe P21 (OPEN_DEBTS D30).

``ratio = unique inlines x unique crosslines / traces``. The pinned ``multidimio`` refuses a
grid whose ratio is strictly above 10. The limit is a barred upstream setting, so SDIP cannot
move it. Every member is written by :func:`make_irregular` from explicit index pairs.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Final

from tests.fixtures.generators.irregular import IrregularSegy, make_irregular

LIMIT: Final[float] = 10.0
"""MDIO's default ``MDIO__GRID__SPARSITY_RATIO_LIMIT``; refusal is ``ratio > LIMIT``."""


def _diagonal(n: int) -> list[tuple[int, int]]:
    return [(i, i) for i in range(1, n + 1)]


def _swath(length: int, width: int) -> list[tuple[int, int]]:
    """A narrow oblique strip: inline i carries crosslines i .. i + width - 1."""
    return [(i, i + j) for i in range(1, length + 1) for j in range(width)]


@dataclass(frozen=True, slots=True)
class SparsityMember:
    """One registered grid and the side of the bound it was registered on."""

    name: str
    pairs: tuple[tuple[int, int], ...]
    accepted: bool

    @property
    def ratio(self) -> float:
        """Grid cells over traces, as MDIO computes it."""
        inlines = {p[0] for p in self.pairs}
        crosslines = {p[1] for p in self.pairs}
        return len(inlines) * len(crosslines) / len(self.pairs)


MEMBERS: Final[tuple[SparsityMember, ...]] = (
    SparsityMember("below_9_09", (*_diagonal(10), (1, 2)), accepted=True),
    SparsityMember("diag_10_00", tuple(_diagonal(10)), accepted=True),
    SparsityMember("swath_L36_w4", tuple(_swath(36, 4)), accepted=True),
    SparsityMember("diag_10_08", (*_diagonal(11), (1, 2)), accepted=False),
    SparsityMember("swath_L40_w4", tuple(_swath(40, 4)), accepted=False),
    SparsityMember("swath_L40_w3", tuple(_swath(40, 3)), accepted=False),
    SparsityMember("diag_100", tuple(_diagonal(100)), accepted=False),
)
"""P21's seven members, in registration order."""


def build_member(member: SparsityMember, path: str | Path) -> IrregularSegy:
    """Write one member."""
    return make_irregular(path, index_pairs=member.pairs)
