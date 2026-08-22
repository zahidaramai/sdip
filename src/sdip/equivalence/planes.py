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
from sdip.ingest.file_headers import (
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

        group = zarr.open_group(str(store), mode="r")
        node = group["segy_file_header"] if "segy_file_header" in group else group
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


def plane_3(source: str | Path, store: str | Path, spec: Any, *, g1_passed: bool) -> PlaneResult:
    """**Plane 3 — trace header.** Gate G2c. Spec §4.4.

    For every trace, **all 240 header bytes are recoverable from the store, bit-exact.**

    The comparison is field-wise over the gap-free spec, in both directions, with
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

    trace_map = build_trace_map(
        source_headers,
        {"inline": group["inline"][:], "crossline": group["crossline"][:]},
    )

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

    ok = not mismatches and not missing_fields and trace_map.invertible
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
                "covers all 240 bytes with no gaps and no overlaps."
            ),
        },
    )


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
    """
    from sdip.equivalence.trace_map import build_trace_map

    handle = _open_source(source, spec)
    group = _open_store(store)
    source_headers = handle.header[:]
    samples = handle.sample[:]
    volume = group[variable][:]

    trace_map = build_trace_map(
        source_headers,
        {"inline": group["inline"][:], "crossline": group["crossline"][:]},
    )

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

    ok = not mismatches and trace_map.invertible
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
        },
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

    trace_map = build_trace_map(
        source_headers,
        {"inline": group["inline"][:], "crossline": group["crossline"][:]},
    )

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
