"""Source trace ordinal to grid position. Plane 5's core, Planes 3 and 4's prerequisite.

The mapping from *source trace ordinal* to *grid position* is what makes a comparison
possible at all: the source is a flat sequence of traces, the store is an N-dimensional
grid, and nothing can be compared until each source trace is located in that grid.

§4.6 requires the mapping be **stored, complete, and invertible**, and requires
**duplicate index tuples to be detected and surfaced, never silently overwritten**. Those
are the same computation, so they live together here: building the map *is* how a
duplicate is found.

**A duplicate is data loss, not a labelling problem.** Two source traces claiming the
same grid cell means one of them is not in the store, and the store carries no evidence
that it ever existed. The map records every ordinal that maps to each cell, so a
collision is visible rather than absorbed.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

import numpy as np


@dataclass(slots=True)
class TraceMap:
    """Source ordinal to grid position, with collisions preserved."""

    dimensions: tuple[str, ...]
    coordinates: dict[str, tuple[int, ...]]
    ordinal_to_cell: dict[int, tuple[int, ...]] = field(default_factory=dict)
    cell_to_ordinals: dict[tuple[int, ...], list[int]] = field(default_factory=dict)
    unmapped: list[int] = field(default_factory=list)

    @property
    def source_trace_count(self) -> int:
        """Traces present in the source."""
        return len(self.ordinal_to_cell) + len(self.unmapped)

    @property
    def duplicates(self) -> dict[tuple[int, ...], list[int]]:
        """Grid cells claimed by more than one source trace. Each one is data loss."""
        return {c: o for c, o in self.cell_to_ordinals.items() if len(o) > 1}

    @property
    def invertible(self) -> bool:
        """True when every source trace maps to a cell and no cell is claimed twice.

        Invertibility is the property §4.6 actually needs: without it, a grid position
        cannot be traced back to the source trace that produced it, so no per-trace
        claim about the store can be checked against the source.
        """
        return not self.unmapped and not self.duplicates

    def cells(self) -> set[tuple[int, ...]]:
        """Every grid cell claimed by at least one source trace."""
        return set(self.cell_to_ordinals)

    def to_json(self) -> dict[str, Any]:
        """Certificate-shaped mapping."""
        duplicates = self.duplicates
        return {
            "dimensions": list(self.dimensions),
            "source_trace_count": self.source_trace_count,
            "mapped": len(self.ordinal_to_cell),
            "unmapped_ordinals": self.unmapped[:20],
            "unmapped_count": len(self.unmapped),
            "duplicate_cells": [
                {"cell": list(cell), "source_ordinals": ordinals}
                for cell, ordinals in sorted(duplicates.items())[:20]
            ],
            "duplicate_count": len(duplicates),
            "invertible": self.invertible,
        }


def build_trace_map(
    source_headers: Any,
    coordinates: dict[str, np.ndarray],
    dimensions: tuple[str, ...] = ("inline", "crossline"),
) -> TraceMap:
    """Map every source trace to a grid cell by its index-header values.

    Args:
        source_headers: Header array read from the source with the gap-free spec.
        coordinates: Grid coordinate values per dimension, read from the store.
        dimensions: Index header names, outermost first.

    Returns:
        The map, with duplicates and unmapped traces preserved rather than resolved.
    """
    lookup = {
        name: {int(v): i for i, v in enumerate(np.asarray(values).ravel())}
        for name, values in coordinates.items()
    }
    columns = {name: np.asarray(source_headers[name]).ravel() for name in dimensions}
    n = len(next(iter(columns.values())))

    trace_map = TraceMap(
        dimensions=dimensions,
        coordinates={
            k: tuple(int(x) for x in np.asarray(v).ravel()) for k, v in coordinates.items()
        },
    )
    collisions: dict[tuple[int, ...], list[int]] = defaultdict(list)

    for ordinal in range(n):
        cell: list[int] = []
        for name in dimensions:
            value = int(columns[name][ordinal])
            index = lookup[name].get(value)
            if index is None:
                cell = []
                break
            cell.append(index)
        if not cell:
            trace_map.unmapped.append(ordinal)
            continue
        key = tuple(cell)
        trace_map.ordinal_to_cell[ordinal] = key
        collisions[key].append(ordinal)

    trace_map.cell_to_ordinals = dict(collisions)
    return trace_map
