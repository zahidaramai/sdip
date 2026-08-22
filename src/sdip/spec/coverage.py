"""Byte-coverage arithmetic over a SEG-Y trace-header specification.

Separated from the generator because **G1 must be able to judge a spec the generator
did not produce** — a survey override, a hand-written spec, a spec from a future
upstream version. A gate that can only assess its own output is not a gate (**SP11**).

Everything here is exact integer set arithmetic on byte positions. There is no
tolerance, no rounding, and no notion of "close enough" — see spec §4.5 and §9.5.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

import numpy as np

from sdip._pins import SEGY_TRACE_HEADER_BYTES

ALL_BYTES: frozenset[int] = frozenset(range(1, SEGY_TRACE_HEADER_BYTES + 1))
"""Bytes 1..240 inclusive. SEG-Y trace headers are 1-indexed."""


class HeaderFieldLike(Protocol):
    """The three attributes coverage arithmetic needs from a header field.

    Typed structurally so the checker never imports upstream, which keeps G1 usable
    against any object that describes a field the same way.
    """

    name: str
    byte: int
    format: Any


@dataclass(frozen=True, slots=True)
class FieldExtent:
    """One field resolved to the concrete byte positions it occupies."""

    name: str
    start: int
    size: int

    @property
    def stop(self) -> int:
        """One past the last byte this field occupies."""
        return self.start + self.size

    @property
    def positions(self) -> frozenset[int]:
        """Every byte position this field covers."""
        return frozenset(range(self.start, self.stop))

    def __str__(self) -> str:
        """``name@start`` for a one-byte field, ``name@start-last`` otherwise."""
        last = self.stop - 1
        span = f"{self.start}" if self.size == 1 else f"{self.start}-{last}"
        return f"{self.name}@{span}"


@dataclass(frozen=True, slots=True)
class Overlap:
    """Two fields claiming the same byte. Fatal to G1 in either direction."""

    byte: int
    fields: tuple[str, ...]


@dataclass(slots=True)
class Coverage:
    """The complete byte-coverage picture of a trace-header specification."""

    extents: list[FieldExtent] = field(default_factory=list)
    covered: frozenset[int] = frozenset()
    uncovered: frozenset[int] = frozenset()
    overlaps: tuple[Overlap, ...] = ()
    out_of_range: tuple[FieldExtent, ...] = ()
    itemsize: int | None = None

    @property
    def field_count(self) -> int:
        """Number of declared fields."""
        return len(self.extents)

    @property
    def gap_free(self) -> bool:
        """True iff coverage is exactly 1..240 with no overlap and nothing out of range."""
        return (
            self.covered == ALL_BYTES
            and not self.uncovered
            and not self.overlaps
            and not self.out_of_range
        )

    def uncovered_runs(self) -> tuple[tuple[int, int], ...]:
        """Uncovered bytes collapsed to ``(first, last)`` inclusive runs.

        ``(233, 240)`` reads better than eight separate integers in an error message,
        and a run is what a human recognises as "the tail of the header".
        """
        return _runs(sorted(self.uncovered))

    def to_json(self) -> dict[str, Any]:
        """Certificate-shaped mapping. This is G1's evidence."""
        return {
            "field_count": self.field_count,
            "itemsize": self.itemsize,
            "covered_bytes": len(self.covered),
            "uncovered_bytes": sorted(self.uncovered),
            "uncovered_runs": [list(r) for r in self.uncovered_runs()],
            "overlaps": [{"byte": o.byte, "fields": list(o.fields)} for o in self.overlaps],
            "out_of_range": [str(e) for e in self.out_of_range],
            "gap_free": self.gap_free,
        }


def _runs(values: Sequence[int]) -> tuple[tuple[int, int], ...]:
    if not values:
        return ()
    out: list[tuple[int, int]] = []
    start = previous = values[0]
    for value in values[1:]:
        if value == previous + 1:
            previous = value
            continue
        out.append((start, previous))
        start = previous = value
    out.append((start, previous))
    return tuple(out)


def format_itemsize(fmt: Any) -> int:
    """Return the byte width of a SEG-Y scalar format.

    Accepts an upstream ``ScalarType``, a plain string such as ``"uint8"``, or a numpy
    dtype. ``ibm32`` is 4 bytes and has **no numpy equivalent**, so it is resolved by
    name before numpy is consulted.

    Case is preserved when handing the name to numpy. ``ScalarType.STRING8`` has the
    value ``"S8"``, and numpy accepts ``"S8"`` while rejecting ``"s8"`` — normalising
    case before the lookup silently loses the only string format in the SEG-Y standard.

    Args:
        fmt: The field's declared format.

    Returns:
        Width in bytes.

    Raises:
        ValueError: If the format cannot be resolved to a width.
    """
    name = str(getattr(fmt, "value", fmt))
    if name.lower() in {"ibm32", "ibm"}:
        return 4
    try:
        return int(np.dtype(name).itemsize)
    except TypeError as exc:
        msg = (
            f"cannot resolve a byte width for header field format {fmt!r}; "
            "a field of unknown width cannot be covered, so G1 must refuse rather "
            "than guess"
        )
        raise ValueError(msg) from exc


def extents_of(fields: Iterable[HeaderFieldLike]) -> list[FieldExtent]:
    """Resolve each declared field to the byte positions it occupies."""
    return [
        FieldExtent(name=f.name, start=int(f.byte), size=format_itemsize(f.format)) for f in fields
    ]


def compute_coverage(fields: Iterable[HeaderFieldLike], *, itemsize: int | None = None) -> Coverage:
    """Compute byte coverage, overlaps, and out-of-range fields for a field set.

    Args:
        fields: Declared header fields.
        itemsize: The resulting dtype's itemsize, when known. Recorded, and asserted
            separately by G1 — a spec can cover 1..240 and still produce a dtype of the
            wrong size if a field straddles the end.

    Returns:
        The coverage picture. Judgement is G1's job, not this function's.
    """
    extents = extents_of(fields)

    claimants: dict[int, list[str]] = {}
    out_of_range: list[FieldExtent] = []
    for extent in extents:
        if extent.start < 1 or extent.stop > SEGY_TRACE_HEADER_BYTES + 1:
            out_of_range.append(extent)
        for position in extent.positions:
            claimants.setdefault(position, []).append(extent.name)

    covered = frozenset(p for p in claimants if p in ALL_BYTES)
    overlaps = tuple(
        Overlap(byte=position, fields=tuple(names))
        for position, names in sorted(claimants.items())
        if len(names) > 1
    )
    return Coverage(
        extents=extents,
        covered=covered,
        uncovered=ALL_BYTES - covered,
        overlaps=overlaps,
        out_of_range=tuple(out_of_range),
        itemsize=itemsize,
    )


def dtype_has_void_gaps(dtype: np.dtype[Any]) -> bool:
    """True when a structured dtype has padding numpy inserted between fields.

    A numpy void gap is invisible to byte-coverage arithmetic — the fields can cover
    1..240 while the dtype numpy actually builds is larger, with unnamed padding no
    field can address. Those padding bytes would be written and would be
    unrecoverable, which is a Plane 3 failure that looks like success.
    """
    return declared_field_bytes(dtype) != int(dtype.itemsize)


def declared_field_bytes(dtype: np.dtype[Any]) -> int:
    """Sum of the widths of a structured dtype's named fields.

    Differs from ``dtype.itemsize`` exactly when numpy inserted padding, which is what
    makes it the measurement :func:`dtype_has_void_gaps` is built on.
    """
    fields = dtype.fields
    if dtype.names is None or fields is None:
        return int(dtype.itemsize)
    return sum(int(fields[name][0].itemsize) for name in dtype.names)
