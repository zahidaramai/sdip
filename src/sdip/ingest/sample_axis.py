"""Where the stored time axis starts: at the recording delay, when SDIP can say so exactly.

**DECISIONS.md D-0096, superseding D53's handling (D-0089).** SEG-Y bytes 109-110, scaled by
215-216, are the delay recording time: the time from source initiation to the first recorded
sample. segyio, segysak, OpenVDS, OpendTect and Madagascar start the sample axis there. The
pinned writer cannot: ``segy`` 0.6.0 builds its labels as ``arange(0, ...)`` and ``mdio``
1.2.1 offers no parameter for the origin. Until D-0096 every survey with a delay produced a
store whose samples were all correct and whose axis placed every event early, and the
store was refused release on that alone.

**The rule.** ``sdip ingest`` moves the stored ``time`` axis to start at the delay when, and
only when, all of these hold — otherwise the axis stays as the writer built it and Plane 4's
``nonzero_recording_delay`` finding still blocks release:

1. the delay is **nonzero**;
2. it is the **same on every trace** — one axis cannot carry a varying origin;
3. the sample axis is **``time``** — a recording delay is a time, and is not applied to a
   depth axis;
4. it is **exactly representable**: a whole number of milliseconds, onto an integer axis
   whose values stay in range. A shift that would round is not made (D54's reasoning).

**Not a transform of data (SP1).** No sample value, header byte or file header changes. The
axis labels are re-derived from the source's own bytes, so nothing in them is fabricated
(SP12). The export never reads the axis, so G3's whole-file identity is untouched.

**Declared, and verified independently.** The origin is recorded in the provenance marker
(``sdipSampleAxisOrigin``) only when it was applied, and Plane 4 then derives the delay from
the source itself and requires the stored axis to equal the writer's axis plus it, exactly.
The marker only says which convention its writer followed; it is never trusted for the
value. Remove it from a shifted store, or add it to an unshifted one, and Plane 4 fails.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

import numpy as np

TIME_AXIS: Final[str] = "time"
"""The only axis the origin is applied to."""

DELAY_FIELD: Final[str] = "delay_recording_time"
SCALAR_FIELD: Final[str] = "times_scalar"


def effective_delays_ms(raw: Any, scalars: Any) -> list[float]:
    """Delay recording time in true milliseconds, per distinct value. Sorted.

    Bytes 215-216 scale bytes 95-114: a positive scalar multiplies, a negative one divides,
    and zero means one.
    """
    effective: set[float] = set()
    for value, scalar in zip(np.ravel(raw), np.ravel(scalars), strict=True):
        s = int(scalar)
        if s == 0:
            s = 1
        effective.add(float(value) * s if s > 0 else float(value) / abs(s))
    return sorted(effective)


def source_delays_ms(source_headers: Any) -> list[float] | None:
    """The distinct effective delays across every trace, or ``None`` if the spec has no field."""
    names = getattr(getattr(source_headers, "dtype", None), "names", None) or ()
    if DELAY_FIELD not in names:
        return None
    raw = np.asarray(source_headers[DELAY_FIELD])
    scalars = (
        np.asarray(source_headers[SCALAR_FIELD]) if SCALAR_FIELD in names else np.zeros_like(raw)
    )
    return effective_delays_ms(raw, scalars)


@dataclass(frozen=True, slots=True)
class AxisOrigin:
    """Whether the rule applies to this source and axis, and the origin if it does."""

    applies: bool
    origin_ms: float
    delays_ms: tuple[float, ...]
    reason: str

    def marker_block(self) -> dict[str, Any] | None:
        """What the provenance marker records: the origin, only when it was applied."""
        if not self.applies:
            return None
        return {
            "axis": TIME_AXIS,
            "origin_ms": self.origin_ms,
            "source": "trace header bytes 109-110 scaled by 215-216, identical on every trace",
            "decision": "D-0096",
        }


def axis_origin(source_headers: Any, axis: str | None, axis_dtype: Any) -> AxisOrigin:
    """Apply the rule in this module's docstring. Pure: reads nothing but its arguments.

    Args:
        source_headers: Every source trace header, structured, as ``segy`` reads them.
        axis: The store's sample-axis name, or ``None`` if it declares none.
        axis_dtype: The stored axis array's dtype.

    Returns:
        The decision, with the delays seen and the reason.
    """
    delays = source_delays_ms(source_headers)
    if delays is None:
        return AxisOrigin(False, 0.0, (), "the spec names no delay recording time field")
    seen = tuple(delays[:10])
    if delays == [0.0]:
        return AxisOrigin(False, 0.0, seen, "the recording delay is zero on every trace")
    if axis != TIME_AXIS:
        return AxisOrigin(
            False, 0.0, seen, f"the sample axis is {axis!r}; a recording delay is applied to time"
        )
    if len(delays) != 1:
        return AxisOrigin(
            False, 0.0, seen, "the recording delay varies across traces; one axis has one origin"
        )
    origin = delays[0]
    dtype = np.dtype(axis_dtype)
    if not np.issubdtype(dtype, np.integer) or not origin.is_integer():
        return AxisOrigin(
            False,
            0.0,
            seen,
            f"a {origin} ms origin is not exactly representable on a {dtype} millisecond axis",
        )
    return AxisOrigin(True, origin, seen, "constant nonzero delay on a time axis, exact")


def sample_axis_name(group: Any, variable: str = "amplitude") -> str | None:
    """The data variable's dimension that is not a grid dimension, from Zarr v3 metadata.

    The grid dimensions are the ``headers`` array's; never assumed to be ``"time"`` (D-0039).
    """
    if variable not in group or "headers" not in group:
        return None
    names = getattr(group[variable].metadata, "dimension_names", None) or ()
    grid = set(getattr(group["headers"].metadata, "dimension_names", None) or ())
    extra = [n for n in names if n not in grid]
    return extra[-1] if extra else None


def decide_for_store(store: str | Path, source_headers: Any) -> AxisOrigin:
    """:func:`axis_origin` for a store on disk: reads its axis name and dtype."""
    import zarr

    group = zarr.open_group(str(store), mode="r")
    axis = sample_axis_name(group)
    node = group[axis] if axis is not None and axis in group else None
    dtype = node.dtype if isinstance(node, zarr.Array) else np.dtype("float64")
    return axis_origin(source_headers, axis, dtype)


def apply_axis_origin(store: str | Path, origin: AxisOrigin) -> None:
    """Move the stored ``time`` axis to start at ``origin``. Stock ``zarr``; checked after.

    Raises:
        ValueError: If the shifted axis would leave the stored dtype's range, or did not
            land exactly - never a rounded or wrapped axis.
    """
    import zarr

    if not origin.applies:
        return
    array = zarr.open_array(str(store), path=TIME_AXIS, mode="r+")
    before = np.asarray(array[...])
    info = np.iinfo(before.dtype)
    shifted = before.astype(np.int64) + int(origin.origin_ms)
    if shifted.min() < info.min or shifted.max() > info.max:
        msg = f"a {origin.origin_ms} ms origin takes the {before.dtype} time axis out of range"
        raise ValueError(msg)
    array[...] = shifted.astype(before.dtype)
    after = np.asarray(array[...])
    if not np.array_equal(after.astype(np.int64), shifted):
        msg = "the time axis did not store the shifted values exactly"
        raise ValueError(msg)
