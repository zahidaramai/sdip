"""Plane checkers. Specification §4.

**There is no tolerance in this module and there never will be.** Comparisons are byte
equality or ``array_equal``. A tolerance-based comparison is a specification defect
(§4.5, §9.5), and a CI job parses this tree with ``ast`` to make sure none appears.

Phase F2 implements **Plane 1** (textual) and **Plane 2** (binary) — gates G2a and G2b.
Planes 3, 4 and 5 are F3 and are not stubbed: :func:`plane_3`, :func:`plane_4` and
:func:`plane_5` do not exist, so a caller gets an ``AttributeError`` rather than a
plausible-looking `PASS` for a check that never ran.

Every checker compares the **store** against the **source file on disk**, never against
something remembered from the ingest that produced it. A checker that validates its own
in-memory copy is a tautology: it would pass on a store that was never written.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from sdip._pins import SEGY_BINARY_HEADER_BYTES, SEGY_TEXTUAL_HEADER_BYTES
from sdip.errors import UntrustedInputError
from sdip.ingest.file_headers import (
    raw_header_node,
    read_raw_binary_from_store,
    read_raw_file_headers,
    read_raw_textual_from_store,
)
from sdip.provenance.hashing import sha256_bytes


def first_difference(left: bytes, right: bytes) -> dict[str, Any] | None:
    """Locate the first differing byte, or ``None`` when the two are identical.

    A plane that reports only *that* it failed is much less useful than one that says
    *where*. The offset is what turns a failure into a diagnosis.
    """
    if left == right:
        return None
    if len(left) != len(right):
        return {
            "kind": "length",
            "expected_bytes": len(left),
            "observed_bytes": len(right),
        }
    for offset, (a, b) in enumerate(zip(left, right, strict=True)):
        if a != b:
            return {
                "kind": "byte",
                "offset": offset,
                "expected": a,
                "observed": b,
            }
    return None  # pragma: no cover - unreachable while lengths match


@dataclass(slots=True)
class PlaneResult:
    """One plane's verdict and the evidence behind it. Certificate shape, §4.7."""

    plane: int
    gate: str
    title: str
    status: str
    evidence: dict[str, Any] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        """True only on ``PASS``. ``NOT_RUN`` is not a pass."""
        return self.status == "PASS"

    def to_json(self) -> dict[str, Any]:
        """Certificate-shaped mapping."""
        return {"status": self.status, "evidence": self.evidence}


def plane_1(source: str | Path, store: str | Path) -> PlaneResult:
    """**Plane 1 — textual header.** Gate G2a. Spec §4.2.

    The 3200-byte textual file header must be preserved **verbatim**, including
    non-conforming EBCDIC. The comparison is on raw bytes, not on a decoded string:
    decoding first would make the check pass for two byte sequences that decode alike,
    which is precisely the silent substitution §4.2 bars.

    Args:
        source: The source SEG-Y, read from disk.
        store: The MDIO store.

    Returns:
        The plane verdict, with the first differing offset when it fails.
    """
    expected = read_raw_file_headers(source).textual
    observed = read_raw_textual_from_store(store)
    difference = first_difference(expected, observed)
    return PlaneResult(
        plane=1,
        gate="G2a",
        title="Textual header preserved verbatim",
        status="PASS" if difference is None else "FAIL",
        evidence={
            "compared": "raw bytes, source vs store",
            "n": SEGY_TEXTUAL_HEADER_BYTES,
            "sampling": "exhaustive",
            "source_sha256": sha256_bytes(expected),
            "store_sha256": sha256_bytes(observed),
            "first_difference": difference,
            "note": (
                "Compared as bytes, never as a decoded string: two byte sequences that "
                "decode alike are not the same header (§4.2)."
            ),
        },
    )


def plane_2(source: str | Path, store: str | Path) -> PlaneResult:
    """**Plane 2 — binary header.** Gate G2b. Spec §4.3.

    The 400-byte binary file header must be preserved as a parsed mapping **and** as raw
    bytes, with **raw bytes authoritative on conflict**. This checks the authoritative
    half; the parsed mapping is recorded as evidence, not as the verdict.

    Args:
        source: The source SEG-Y, read from disk.
        store: The MDIO store.

    Returns:
        The plane verdict, with the first differing offset when it fails.
    """
    expected = read_raw_file_headers(source).binary
    observed = read_raw_binary_from_store(store)
    difference = first_difference(expected, observed)

    parsed_present = False
    try:
        import zarr

        node = raw_header_node(zarr.open_group(str(store), mode="r"))
        parsed_present = "binaryHeader" in dict(node.attrs)
    except (KeyError, ValueError):  # pragma: no cover - store without the variable
        parsed_present = False

    return PlaneResult(
        plane=2,
        gate="G2b",
        title="Binary header preserved; raw bytes authoritative",
        status="PASS" if difference is None else "FAIL",
        evidence={
            "compared": "raw bytes, source vs store",
            "n": SEGY_BINARY_HEADER_BYTES,
            "sampling": "exhaustive",
            "source_sha256": sha256_bytes(expected),
            "store_sha256": sha256_bytes(observed),
            "first_difference": difference,
            "parsed_mapping_present": parsed_present,
            "note": (
                "Raw bytes decide the verdict. The parsed mapping is recorded because "
                "§4.3 requires both, but it is not authoritative on conflict."
            ),
        },
    )


def _open_source(source: str | Path, spec: Any) -> Any:
    from segy import SegyFile

    return SegyFile(str(Path(source)), spec=spec)


def _open_store(store: str | Path) -> Any:
    import zarr

    return zarr.open_group(str(store), mode="r")


def store_dimensions(group: Any, *, variable: str = "headers") -> tuple[str, ...]:
    """Read the grid dimension names from the store itself.

    **Never hard-code these.** Planes 3, 4 and 5 originally assumed
    ``("inline", "crossline")``, which is true of poststack and false of every prestack
    geometry — probe **P7** found all three planes returning ``KeyError: 'inline'`` on
    all seven prestack stores, so the Equivalence Contract could not be evaluated for
    prestack **at all**. `NOT_RUN` is not a pass, and a checker that cannot run on a
    geometry silently declines to check it. See ``DECISIONS.md`` D-0039.

    Zarr v3 carries ``dimension_names`` in each array's metadata. It is **core-spec**, so
    reading it needs no MDIO and does not weaken G4.

    Args:
        group: An open Zarr group.
        variable: The array to read dimensions from. ``headers`` is indexed by exactly
            the grid dimensions and no sample axis, which makes it the right source.

    Returns:
        Dimension names, outermost first.

    Raises:
        UntrustedInputError: If the store declares no dimension names.
    """
    meta = group[variable].metadata.to_dict()
    names = meta.get("dimension_names")
    if not names:
        msg = (
            f"store array {variable!r} declares no dimension_names; the grid dimensions "
            "cannot be determined and no per-trace plane can be evaluated against it"
        )
        raise UntrustedInputError(msg)
    return tuple(str(n) for n in names)


def grid_coordinates(group: Any, dimensions: tuple[str, ...]) -> dict[str, Any]:
    """Coordinate values for each grid dimension, read from the store."""
    missing = [d for d in dimensions if d not in group]
    if missing:
        msg = (
            f"store declares grid dimensions {list(dimensions)} but carries no "
            f"coordinate array for {missing}"
        )
        raise UntrustedInputError(msg)
    return {d: group[d][:] for d in dimensions}


RAW_HEADER_NOTE = (
    "Second leg, ANDed into G2c's verdict. The field-wise comparison above equals byte "
    "equality only because G1 proved the gap-free spec covers all 240 bytes; this leg "
    "compares the 240 raw bytes in headers_raw_uint8 against the same bytes read from "
    "the source by raw byte offset, and has NO spec dependency at all. It exists "
    "because probe P4 measured three Zarr readers giving three different answers about "
    "the structured array's `struct` data_type - TensorStore accepts it, zarr-java "
    "refuses it, zarr-python warns - and `struct` has no Zarr v3 specification, so a "
    "reader that declines it is conformant (DECISIONS.md D-0047). The plane is the "
    "portable copy, and a portable copy nothing checks is not evidence."
)


def _raw_header_evidence(
    source: str | Path, handle: Any, group: Any, spec: Any, trace_map: Any
) -> dict[str, Any]:
    """Compare the stored ``uint8`` header plane against the source, as bytes.

    Absent array means **not checked**, never checked-and-passed: a store written before
    the plane existed carries none, and ``raw_header_bytes_verified`` says which of those
    a reader is looking at.

    Live cells only. Padding is not data (**SP12**), and the fill byte ``0x00`` is a
    valid header byte, so comparing it against anything would be comparing against a
    number nobody measured.
    """
    from sdip.ingest.header_plane import (
        ARRAY_NAME,
        read_source_header_bytes,
        sample_bytes,
        trace_data_offset,
    )

    if ARRAY_NAME not in group:
        return {
            "raw_header_plane_present": False,
            "raw_header_bytes_verified": False,
            "raw_header_bytes_identical": None,
            "raw_header_first_difference": None,
            "raw_header_note": (
                f"store carries no {ARRAY_NAME} array. Its absence is NOT evidence that "
                "the header bytes match; it means this leg did not run."
            ),
        }

    stored = np.asarray(group[ARRAY_NAME][:])
    try:
        expected_all = read_source_header_bytes(
            source,
            samples_per_trace=int(handle.samples_per_trace),
            bytes_per_sample=sample_bytes(spec),
            data_offset=trace_data_offset(handle),
        )
    except UntrustedInputError as exc:
        # Recorded rather than raised: this leg must never be able to convert the
        # field-wise comparison's verdict into an exception. A plane defect masking a
        # field finding is the exact inversion of what this evidence is for.
        return {
            "raw_header_plane_present": True,
            "raw_header_bytes_verified": False,
            "raw_header_bytes_identical": None,
            "raw_header_first_difference": None,
            "raw_header_error": f"{type(exc).__name__}: {exc}",
            "raw_header_note": RAW_HEADER_NOTE,
        }

    mismatches: list[dict[str, Any]] = []
    compared = 0
    for ordinal, cell in sorted(trace_map.ordinal_to_cell.items()):
        compared += 1
        expected = np.asarray(expected_all[ordinal], dtype=np.uint8)
        observed = np.asarray(stored[cell])
        if not np.array_equal(expected, observed):
            differing = np.flatnonzero(expected != observed)
            first = int(differing[0]) if differing.size else None
            mismatches.append(
                {
                    "source_ordinal": ordinal,
                    "cell": list(cell),
                    "byte_offset": first,
                    "expected": None if first is None else int(expected[first]),
                    "observed": None if first is None else int(observed[first]),
                    "differing_bytes": int(differing.size),
                }
            )
            if len(mismatches) >= 20:
                break

    return {
        "raw_header_plane_present": True,
        "raw_header_bytes_verified": True,
        "raw_header_bytes_identical": not mismatches,
        "raw_header_compared": "np.array_equal on uint8 bytes, source vs store - EXACT",
        "raw_header_n": compared,
        "raw_header_bytes_per_trace": int(stored.shape[-1]),
        "raw_header_sampling": "exhaustive over live traces",
        "raw_header_first_difference": mismatches[0] if mismatches else None,
        "raw_header_mismatch_count": len(mismatches),
        "raw_header_note": RAW_HEADER_NOTE,
    }


DERIVED_COORD_NOTE = (
    "Derived-array leg, AND-ed into G2c's verdict. cdp_x and cdp_y are the OUTPUT of "
    "the declared coordinate-scalar transform (DECISIONS.md D-0040), and SP1 requires a "
    "declared transform to be VERIFIED - a declared transform whose output nothing "
    "checks is half-declared. Recomputed here from the source trace headers under the "
    "declared semantics (positive scalar multiplies, negative divides) and compared with "
    "np.array_equal against the arrays a consumer actually reads (G4, section 10.3). "
    "Until 2026-08-23 nothing compared them: an external audit corrupted cdp_x and cdp_y "
    "individually and ALL FIVE PLANES still returned PASS (D-0056)."
)

DERIVED_TIME_NOTE = (
    "Derived-axis leg, AND-ed into G2d's verdict. The sample axis is recomputed from the "
    "trace-header sample interval and delay - axis[i] = delay + i * interval/1000 - and "
    "compared with np.array_equal against the stored axis. Samples are meaningless "
    "without the axis that positions them: a corrupted axis mislabels every sample in "
    "depth or time while the sample values themselves compare equal. Until 2026-08-23 "
    "nothing compared it (D-0056)."
)


def _scale_coordinate(raw: Any, scalar: int) -> Any:
    """Apply the SEG-Y coordinate scalar exactly as the declared transform defines it.

    Positive multiplies, negative divides, and 0 is treated as 1 - the convention
    :class:`~sdip.spec.transforms.CoordinateScalarTransform` documents. Division is done
    in ``float64`` because that is what the stored arrays are; this is **not** a
    tolerance, and the comparison downstream is still exact.
    """
    values = np.asarray(raw, dtype=np.float64)
    if scalar > 1:
        return values * float(scalar)
    if scalar < -1:
        return values / float(-scalar)
    return values


def _project_cell(cell: tuple[int, ...], grid: tuple[str, ...], dims: tuple[str, ...]) -> Any:
    """Project a full-grid cell onto the dimensions one array actually declares.

    A derived coordinate array is **not** necessarily indexed by the whole grid. Plane 3
    RAISED on every prestack geometry when this leg first landed, because the cell was
    used whole - and a plane that raises has not judged the store at all, which is the
    P7 failure mode over again (D-0039).

    Returns the projected index tuple, or ``None`` when the array names a dimension the
    grid does not - in which case the caller records NOT CHECKED rather than guessing.
    """
    if not dims:
        return None
    try:
        return tuple(cell[grid.index(d)] for d in dims)
    except ValueError:
        return None


def _array_dimension_names(group: Any, name: str) -> tuple[str, ...]:
    """Dimension names an array declares, or ``()`` when it declares none."""
    names = getattr(group[name].metadata, "dimension_names", None)
    return tuple(names) if names else ()


def _derived_coordinate_evidence(
    source_headers: Any, group: Any, trace_map: Any, grid: tuple[str, ...]
) -> dict[str, Any]:
    """Recompute ``cdp_x``/``cdp_y`` from the source headers and compare, exactly.

    **Absent array means NOT CHECKED, never checked-and-passed** - the same discipline
    the raw legs use. A store without a coordinate array, or a source whose spec carries
    no coordinate scalar, yields ``None`` rather than ``True``.
    """
    from sdip.spec.transforms import COORD_ARRAYS, COORD_SCALAR_FIELD, detect_coordinate_scalar

    names = getattr(getattr(source_headers, "dtype", None), "names", None) or ()
    present = [a for a in COORD_ARRAYS if a in group]
    if not present:
        return {
            "derived_coords_present": False,
            "derived_coords_verified": False,
            "derived_coords_identical": None,
            "derived_coords_note": (
                "store carries no cdp_x/cdp_y array; absence is NOT evidence they match."
            ),
        }

    transform = detect_coordinate_scalar(source_headers)
    if transform is None or COORD_SCALAR_FIELD not in names:
        return {
            "derived_coords_present": True,
            "derived_coords_verified": False,
            "derived_coords_identical": None,
            "derived_coords_note": (
                "spec declares no coordinate scalar, so the derivation cannot be "
                "reconstructed. NOT CHECKED - not checked-and-passed."
            ),
        }

    scalars = np.asarray(source_headers[COORD_SCALAR_FIELD]).ravel()
    mismatches: list[dict[str, Any]] = []
    compared = 0

    for array_name in present:
        if array_name not in names:
            return {
                "derived_coords_present": True,
                "derived_coords_verified": False,
                "derived_coords_identical": None,
                "derived_coords_note": (
                    f"source header has no {array_name!r} field; the derivation cannot "
                    "be reconstructed. NOT CHECKED."
                ),
            }
        stored = np.asarray(group[array_name][:])
        raw = np.asarray(source_headers[array_name]).ravel()
        dims = _array_dimension_names(group, array_name)
        projected = {
            ordinal: _project_cell(cell, grid, dims)
            for ordinal, cell in trace_map.ordinal_to_cell.items()
        }
        if not dims or any(v is None for v in projected.values()):
            return {
                "derived_coords_present": True,
                "derived_coords_verified": False,
                "derived_coords_identical": None,
                "derived_coords_note": (
                    f"{array_name} is indexed by {list(dims)}, which the grid "
                    f"{list(grid)} does not address. NOT CHECKED - not "
                    "checked-and-passed."
                ),
            }
        for ordinal in sorted(trace_map.ordinal_to_cell):
            index = projected[ordinal]
            compared += 1
            # Each trace's OWN scalar, never trace 0's applied to all. Upstream reads
            # trace 0 only; a survey whose scalar varies is legal SEG-Y, and applying one
            # trace's scalar to the rest would be a fabrication under SP12.
            expected = _scale_coordinate(raw[ordinal], int(scalars[ordinal]))
            observed = np.asarray(stored[index], dtype=np.float64)
            if not np.array_equal(expected, observed):
                if len(mismatches) < 20:
                    mismatches.append(
                        {
                            "array": array_name,
                            "source_ordinal": ordinal,
                            "cell": list(index),
                            "header_value": float(np.asarray(raw[ordinal], dtype=np.float64)),
                            "coordinate_scalar": int(scalars[ordinal]),
                            "expected": float(expected),
                            "observed": float(observed),
                        }
                    )

    return {
        "derived_coords_present": True,
        "derived_coords_verified": True,
        "derived_coords_identical": not mismatches,
        "derived_coords_arrays": present,
        "derived_coords_compared": "np.array_equal, recomputed from source headers - EXACT",
        "derived_coords_n": compared,
        "derived_coords_scalar_uniform": transform.uniform,
        "derived_coords_scalar_values": list(transform.distinct_values),
        "derived_coords_first_difference": mismatches[0] if mismatches else None,
        "derived_coords_mismatch_count": len(mismatches),
        "derived_coords_note": DERIVED_COORD_NOTE,
    }


def _sample_axis_name(group: Any, variable: str, grid: tuple[str, ...]) -> str | None:
    """Name of the sample axis: the data variable's dimensions minus the grid ones.

    **Read from Zarr v3 metadata, never assumed to be ``"time"``** - a depth-domain
    template names it ``depth``, and hard-coding a dimension name is exactly the defect
    probe P7 found in planes 3-5 (D-0039).

    Note it cannot come from :func:`store_dimensions`, which reports the **grid**
    dimensions and deliberately excludes the sample axis. Using its last entry compares
    the crossline array against a time progression - a mistake made and caught here
    during the D-0056 fix, and the reason this helper exists rather than an index.
    """
    if variable not in group:
        return None
    names = getattr(group[variable].metadata, "dimension_names", None)
    if not names:
        return None
    extra = [n for n in names if n not in set(grid)]
    return extra[-1] if extra else None


def _time_axis_evidence(source_headers: Any, group: Any, axis: str | None) -> dict[str, Any]:
    """Recompute the sample axis from the source headers and compare, exactly."""
    if axis is None:
        return {
            "derived_axis_present": False,
            "derived_axis_verified": False,
            "derived_axis_identical": None,
            "derived_axis_note": (
                "the store declares no sample axis distinct from its grid dimensions; "
                "NOT CHECKED - not checked-and-passed."
            ),
        }
    names = getattr(getattr(source_headers, "dtype", None), "names", None) or ()
    if axis not in group:
        return {
            "derived_axis_present": False,
            "derived_axis_verified": False,
            "derived_axis_identical": None,
            "derived_axis_note": f"store carries no {axis!r} array; NOT CHECKED.",
        }
    if "sample_interval" not in names or "delay_recording_time" not in names:
        return {
            "derived_axis_name": axis,
            "derived_axis_present": True,
            "derived_axis_verified": False,
            "derived_axis_identical": None,
            "derived_axis_note": (
                "source header lacks sample_interval or delay_recording_time, so the "
                "axis cannot be reconstructed. NOT CHECKED - not checked-and-passed."
            ),
        }

    intervals = np.unique(np.asarray(source_headers["sample_interval"]).ravel())
    delays = np.unique(np.asarray(source_headers["delay_recording_time"]).ravel())
    if intervals.size != 1 or delays.size != 1:
        # A varying interval or delay is legal SEG-Y and means the axis is not a single
        # shared progression. Recorded, never guessed at.
        return {
            "derived_axis_name": axis,
            "derived_axis_present": True,
            "derived_axis_verified": False,
            "derived_axis_identical": None,
            "derived_axis_intervals": [int(v) for v in intervals[:10]],
            "derived_axis_delays": [int(v) for v in delays[:10]],
            "derived_axis_note": (
                "sample_interval or delay_recording_time varies between traces, so a "
                "single shared axis is not derivable. NOT CHECKED."
            ),
        }

    stored = np.asarray(group[axis][:])
    interval_us = int(intervals[0])
    delay_ms = int(delays[0])
    expected = delay_ms + np.arange(stored.shape[0], dtype=np.float64) * (interval_us / 1000.0)
    observed = np.asarray(stored, dtype=np.float64)
    identical = bool(np.array_equal(expected, observed))

    first = None
    if not identical:
        differing = np.flatnonzero(expected != observed)
        if differing.size:
            i = int(differing[0])
            first = {
                "index": i,
                "expected": float(expected[i]),
                "observed": float(observed[i]),
            }

    return {
        "derived_axis_name": axis,
        "derived_axis_present": True,
        "derived_axis_verified": True,
        "derived_axis_identical": identical,
        "derived_axis_compared": "np.array_equal, recomputed from source headers - EXACT",
        "derived_axis_n": int(stored.shape[0]),
        "derived_axis_sample_interval_us": interval_us,
        "derived_axis_delay_ms": delay_ms,
        "derived_axis_first_difference": first,
        "derived_axis_note": DERIVED_TIME_NOTE,
    }


def plane_3(source: str | Path, store: str | Path, spec: Any, *, g1_passed: bool) -> PlaneResult:
    """**Plane 3 — trace header.** Gate G2c. Spec §4.4.

    For every trace, **all 240 header bytes are recoverable from the store, bit-exact.**

    Two legs, both binding.

    **Leg 1 — field-wise, over the gap-free spec**, in both directions, with
    ``array_equal``. **That is equivalent to byte equality only because the spec is
    gap-free** — every one of the 240 bytes is covered by exactly one field, so no byte
    can differ without some field differing.

    **That dependency is a precondition, not a footnote.** If G1 did not pass, the spec
    may leave bytes uncovered, field-wise equality says nothing about them, and a `PASS`
    here would be a claim the evidence does not support. So this checker refuses to
    return `PASS` without ``g1_passed``: it returns `FAIL` and says why.

    Field *naming* is metadata; byte *content* is the contract (§4.4). A byte at 233
    stored as ``pad_233`` satisfies this plane. A byte lost because no field covered it
    does not — which is exactly what G1 exists to prevent.

    **Leg 2 — byte-wise, over the ``uint8`` header plane**, with **no spec dependency at
    all**: the 240 bytes in ``headers_raw_uint8`` against the same bytes read from the
    source by raw offset. Reported separately as ``raw_header_bytes_verified`` /
    ``raw_header_bytes_identical`` / ``raw_header_first_difference``, and **ANDed into
    the verdict** exactly as the raw-sample leg is ANDed into Plane 4 (D-0049). That
    array is the portable copy of the headers — probe P4 measured a reader refusing the
    structured one — and **evidence nothing can fail is not a check** (**SP11**).

    ``None`` (array absent, correct for a store written before the plane existed) is
    **not** a failure; only an explicit ``False`` fails.

    Args:
        source: The source SEG-Y.
        store: The MDIO store.
        spec: The gap-free ``SegySpec`` used for the ingest.
        g1_passed: Whether G1 passed for that spec.

    Returns:
        The plane verdict.
    """
    from sdip.equivalence.trace_map import build_trace_map

    if not g1_passed:
        return PlaneResult(
            plane=3,
            gate="G2c",
            title="All 240 trace-header bytes recoverable, bit-exact",
            status="FAIL",
            evidence={
                "reason": (
                    "G1 did not pass, so the spec may leave header bytes uncovered. "
                    "Field-wise equality over an incomplete spec proves nothing about "
                    "the uncovered bytes, and PASS would be unsupported by the evidence."
                )
            },
        )

    handle = _open_source(source, spec)
    group = _open_store(store)
    source_headers = handle.header[:]
    store_headers = group["headers"][:]

    dimensions = store_dimensions(group)
    trace_map = build_trace_map(source_headers, grid_coordinates(group, dimensions), dimensions)

    field_names = tuple(source_headers.dtype.names or ())
    store_names = tuple(store_headers.dtype.names or ())
    missing_fields = sorted(set(field_names) - set(store_names))

    mismatches: list[dict[str, Any]] = []
    compared = 0
    for ordinal, cell in sorted(trace_map.ordinal_to_cell.items()):
        compared += 1
        for name in field_names:
            if name in missing_fields:
                continue
            expected = source_headers[name][ordinal]
            observed = store_headers[name][cell]
            if not np.array_equal(expected, observed):
                mismatches.append(
                    {
                        "source_ordinal": ordinal,
                        "cell": list(cell),
                        "field": name,
                        "expected": expected.item(),
                        "observed": observed.item(),
                    }
                )
                if len(mismatches) >= 20:
                    break
        if len(mismatches) >= 20:
            break

    # The byte leg is ANDed into the verdict, not merely reported - the same ruling
    # D-0049 made for Plane 4's raw-word leg. `headers_raw_uint8` is the copy of the
    # headers a non-Python consumer can actually read (probe P4 measured zarr-java
    # refusing the structured one), so a store that silently corrupted it while the
    # field-wise comparison passed would be certifiable with its portable copy already
    # gone. Evidence nothing can fail is not a check; it is a comment (SP11).
    #
    # `None` means the array is absent, which is what a store written before the plane
    # existed carries, and is NOT a failure. Only an explicit False fails.
    raw_evidence = _raw_header_evidence(source, handle, group, spec, trace_map)
    raw_identical = raw_evidence.get("raw_header_bytes_identical")
    raw_ok = raw_identical is not False

    # THIRD leg: the derived coordinate arrays. cdp_x/cdp_y are the OUTPUT of the
    # declared coordinate-scalar transform (D-0040), and SP1 requires a declared
    # transform to be verified - a declared transform whose output nothing checks is
    # half-declared. An external audit corrupted each of them and every plane still
    # returned PASS (D-0056); G4 promotes precisely these arrays as what a consumer
    # reads, so a store could carry corrupted world coordinates under EQUIVALENT.
    #
    # Same `None` discipline as the byte leg: absent or underivable is NOT CHECKED and
    # NOT a failure. Only an explicit False fails.
    coord_evidence = _derived_coordinate_evidence(source_headers, group, trace_map, dimensions)
    coord_ok = coord_evidence.get("derived_coords_identical") is not False

    ok = not mismatches and not missing_fields and trace_map.invertible and raw_ok and coord_ok
    return PlaneResult(
        plane=3,
        gate="G2c",
        title="All 240 trace-header bytes recoverable, bit-exact",
        status="PASS" if ok else "FAIL",
        evidence={
            "compared": "every declared field, source vs store, array_equal",
            "n": compared,
            "field_count": len(field_names),
            "sampling": "exhaustive",
            "byte_coverage_guaranteed_by": "G1 (gap-free spec: 240 of 240 bytes)",
            "missing_fields_in_store": missing_fields,
            "first_difference": mismatches[0] if mismatches else None,
            "mismatch_count": len(mismatches),
            "map_invertible": trace_map.invertible,
            "note": (
                "Field naming is metadata; byte content is the contract. Field-wise "
                "equality equals byte equality here only because G1 proved the spec "
                "covers all 240 bytes with no gaps and no overlaps - which is why the "
                "byte leg, which needs no spec, is ANDed in beside it."
            ),
        }
        | raw_evidence
        | coord_evidence,
    )


RAW_IBM32_NOTE = (
    "Second leg, AND-ed into G2d's verdict (DECISIONS.md D-0049): a raw mismatch fails "
    "this plane, and a raw pass cannot rescue a failed decoded comparison. The decoded "
    "comparison above remains the gate's definition; this leg compares the undecoded "
    "uint32 words in "
    "amplitude_raw_ibm32 against the same words read from the source by raw byte "
    "offset. It is EXACTLY invertible by construction - a uint32 is copied, not "
    "transformed - so it holds precisely where the float comparison cannot: probe P2 "
    "measured 1,939 of 4,103 ibm32 words losing the VALUE in the decode, and two "
    "decoded arrays that both read `inf` are equal without either being the source "
    "sample. A store can have correct raw words and a lossy decode; both facts belong "
    "on the certificate, and neither is allowed to stand in for the other."
)


def _raw_ibm32_evidence(source: str | Path, group: Any, trace_map: Any) -> dict[str, Any]:
    """Compare the stored raw ``ibm32`` words against the source, as ``uint32``.

    Absent array means **not checked**, never checked-and-passed: a ``float32`` source
    carries no such array by design, and so does any store written before the view
    existed. ``raw_ibm32_words_verified`` says which of those a reader is looking at.

    Live cells only. Padding is not data (**SP12**), and the fill word is a valid IBM
    word, so comparing it against anything would be comparing against a number nobody
    measured.
    """
    from sdip.ingest.raw_samples import ARRAY_NAME, read_source_words

    if ARRAY_NAME not in group:
        return {
            "raw_ibm32_view_present": False,
            "raw_ibm32_words_verified": False,
            "raw_ibm32_identical": None,
            "raw_ibm32_note": (
                f"store carries no {ARRAY_NAME} array. Written only for an ibm32 source "
                "(OPEN_DEBTS D1); its absence is NOT evidence that the raw words match."
            ),
        }

    stored = np.asarray(group[ARRAY_NAME][:])
    try:
        words = read_source_words(source, samples_per_trace=int(stored.shape[-1]))
    except UntrustedInputError as exc:
        # Recorded rather than raised: this leg must never be able to convert the
        # decoded comparison's verdict into an exception. A raw-view defect masking a
        # float finding is the exact inversion of what this evidence is for.
        return {
            "raw_ibm32_view_present": True,
            "raw_ibm32_words_verified": False,
            "raw_ibm32_identical": None,
            "raw_ibm32_error": f"{type(exc).__name__}: {exc}",
            "raw_ibm32_note": RAW_IBM32_NOTE,
        }

    mismatches: list[dict[str, Any]] = []
    compared = 0
    for ordinal, cell in sorted(trace_map.ordinal_to_cell.items()):
        compared += 1
        expected = np.asarray(words[ordinal], dtype=np.uint32)
        observed = np.asarray(stored[cell])
        if not np.array_equal(expected, observed):
            differing = np.flatnonzero(expected != observed)
            first = int(differing[0]) if differing.size else None
            mismatches.append(
                {
                    "source_ordinal": ordinal,
                    "cell": list(cell),
                    "first_sample": first,
                    "expected_word": None if first is None else f"0x{int(expected[first]):08X}",
                    "observed_word": None if first is None else f"0x{int(observed[first]):08X}",
                    "differing_words": int(differing.size),
                }
            )
            if len(mismatches) >= 20:
                break

    return {
        "raw_ibm32_view_present": True,
        "raw_ibm32_words_verified": True,
        "raw_ibm32_identical": not mismatches,
        "raw_ibm32_compared": "np.array_equal on uint32 words, source vs store - EXACT",
        "raw_ibm32_n": compared,
        "raw_ibm32_words_per_trace": int(stored.shape[-1]),
        "raw_ibm32_sampling": "exhaustive over live traces",
        "raw_ibm32_first_difference": mismatches[0] if mismatches else None,
        "raw_ibm32_mismatch_count": len(mismatches),
        "raw_ibm32_note": RAW_IBM32_NOTE,
    }


def plane_4(
    source: str | Path, store: str | Path, spec: Any, *, variable: str = "amplitude"
) -> PlaneResult:
    """**Plane 4 — sample.** Gate G2d. Spec §4.5.

    For every **live** trace, all samples bit-exact after the declared sample-format
    decode.

    **Comparison is exact equality, never ``allclose``.** A tolerance-based sample check
    is a specification defect and fails review (§4.5, §9.5). ``np.array_equal`` treats
    ``NaN != NaN``, which is correct here: two ``NaN`` payloads are not evidence of
    preservation, and a source containing ``NaN`` is a P5 finding, not something to
    paper over with ``equal_nan=True``.

    **Grid padding is not part of this plane.** A cell no source trace maps to is
    padding introduced to regularise the grid; it is **not data** (**SP12**) and is
    excluded by the live mask rather than compared against anything.

    **The raw ``ibm32`` words are a second leg, AND-ed into this plane's verdict.**
    Where the store carries the parallel ``amplitude_raw_ibm32`` view (``OPEN_DEBTS``
    D1), the undecoded ``uint32`` words are compared against the source and the result
    recorded as ``raw_ibm32_words_verified`` / ``raw_ibm32_identical``. That comparison
    is **exactly invertible by construction** and therefore says something the decoded
    comparison cannot.

    **A raw mismatch FAILS this plane** (``DECISIONS.md`` D-0049). Asymmetry is the
    point: a raw pass cannot rescue a failed decoded comparison, but a raw failure is
    still a failure. Left evidence-only, SDIP could write a corrupted
    ``amplitude_raw_ibm32`` and no gate would notice — *a portable copy nothing checks
    is not evidence.*

    This docstring, and ``RAW_IBM32_NOTE`` which ships **inside the certificate**, both
    said the opposite until 2026-08-23: that the leg was *"NOT part of G2d's verdict"*.
    D-0049 changed the code and left both strings behind. Corrected under D-0056; a
    certificate carrying a false statement about its own semantics is not a typo.

    **The time axis is verified here too** — see :func:`_time_axis_evidence`. The samples
    are meaningless without the axis that positions them.
    """
    from sdip.equivalence.trace_map import build_trace_map

    handle = _open_source(source, spec)
    group = _open_store(store)
    source_headers = handle.header[:]
    samples = handle.sample[:]
    volume = group[variable][:]

    dimensions = store_dimensions(group)
    trace_map = build_trace_map(source_headers, grid_coordinates(group, dimensions), dimensions)

    mismatches: list[dict[str, Any]] = []
    compared = 0
    for ordinal, cell in sorted(trace_map.ordinal_to_cell.items()):
        compared += 1
        expected = np.asarray(samples[ordinal])
        observed = np.asarray(volume[cell])
        if not np.array_equal(expected, observed):
            differing = np.flatnonzero(expected != observed)
            first = int(differing[0]) if differing.size else None
            mismatches.append(
                {
                    "source_ordinal": ordinal,
                    "cell": list(cell),
                    "first_sample": first,
                    "expected": None if first is None else float(expected[first]),
                    "observed": None if first is None else float(observed[first]),
                    "differing_samples": int(differing.size),
                }
            )
            if len(mismatches) >= 20:
                break

    # The raw-word leg is ANDed into the verdict, not merely reported.
    #
    # It was evidence-only when first built, on the reasoning that a raw pass must not
    # mask a float failure. AND achieves that and more: a raw pass cannot rescue a failed
    # float comparison, and a raw FAILURE now fails the plane. Left as evidence-only,
    # SDIP could write a corrupted `amplitude_raw_ibm32` and no gate would notice - which
    # is exactly the vacuity G7 exists to catch (SP11). Evidence nothing can fail is not
    # a check; it is a comment.
    #
    # `None` means the array is absent, which is correct for a non-ibm32 source and is
    # NOT a failure. Only an explicit False fails.
    raw_evidence = _raw_ibm32_evidence(source, group, trace_map)
    raw_identical = raw_evidence.get("raw_ibm32_identical")
    raw_ok = raw_identical is not False

    # THIRD leg: the sample axis. Samples are meaningless without the axis that
    # positions them - a corrupted axis mislabels every sample in depth or time while
    # the sample VALUES still compare equal, which is why the decoded leg cannot see it.
    # The axis name comes from Zarr v3 dimension metadata, never assumed to be "time":
    # hard-coding a dimension name is the defect P7 found (D-0039).
    axis_evidence = _time_axis_evidence(
        source_headers, group, _sample_axis_name(group, variable, dimensions)
    )
    axis_ok = axis_evidence.get("derived_axis_identical") is not False

    ok = not mismatches and trace_map.invertible and raw_ok and axis_ok
    return PlaneResult(
        plane=4,
        gate="G2d",
        title="Live samples bit-exact after the declared decode",
        status="PASS" if ok else "FAIL",
        evidence={
            "compared": "np.array_equal per live trace - EXACT, never allclose",
            "n": compared,
            "samples_per_trace": int(volume.shape[-1]) if volume.ndim else 0,
            "sampling": "exhaustive over live traces",
            "variable": variable,
            "padding_excluded": True,
            "first_difference": mismatches[0] if mismatches else None,
            "mismatch_count": len(mismatches),
            "note": (
                "Grid padding is not data (SP12) and is excluded by the live mask, not "
                "compared. No tolerance is applied anywhere in this comparison."
            ),
        }
        | raw_evidence
        | axis_evidence,
    )


def plane_5(source: str | Path, store: str | Path, spec: Any) -> PlaneResult:
    """**Plane 5 — cardinality and ordering.** Gate G2e. Spec §4.6.

    Four claims, checked independently so a failure says which one broke:

    1. Live-trace count in the store equals trace count in the source.
    2. The source-ordinal to grid-position mapping is **complete and invertible**.
    3. The live/dead mask distinguishes measured traces from padding **unambiguously**.
    4. Duplicate index tuples are **surfaced, never silently overwritten**.

    Claim 4 is the one that loses data quietly. Two source traces claiming one grid cell
    means one of them is not in the store and the store carries no evidence it ever
    existed — so the map preserves every colliding ordinal rather than resolving them.
    """
    from sdip.equivalence.trace_map import build_trace_map

    handle = _open_source(source, spec)
    group = _open_store(store)
    source_headers = handle.header[:]
    source_count = int(handle.num_traces)

    dimensions = store_dimensions(group)
    trace_map = build_trace_map(source_headers, grid_coordinates(group, dimensions), dimensions)

    mask = np.asarray(group["trace_mask"][:]).astype(bool)
    live_cells = {tuple(int(i) for i in idx) for idx in zip(*np.nonzero(mask), strict=True)}
    mapped_cells = trace_map.cells()

    checks = {
        "count_matches": int(mask.sum()) == source_count,
        "map_complete": not trace_map.unmapped,
        "map_invertible": trace_map.invertible,
        "no_duplicates": not trace_map.duplicates,
        "mask_matches_map": live_cells == mapped_cells,
    }
    ok = all(checks.values())

    return PlaneResult(
        plane=5,
        gate="G2e",
        title="Cardinality, ordering, live mask, duplicates surfaced",
        status="PASS" if ok else "FAIL",
        evidence={
            "compared": "trace counts, mapping invertibility, live mask, duplicates",
            "n": source_count,
            "sampling": "exhaustive",
            "source_trace_count": source_count,
            "live_cells_in_mask": int(mask.sum()),
            "padding_cells": int(mask.size - mask.sum()),
            "checks": checks,
            "failed_checks": [k for k, v in checks.items() if not v],
            "trace_map": trace_map.to_json(),
            "note": (
                "A duplicate index tuple is data loss, not a labelling problem: one "
                "trace is absent from the store and nothing records that it existed."
            ),
        },
    )
