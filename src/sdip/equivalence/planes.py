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

    ok = not mismatches and not missing_fields and trace_map.invertible and raw_ok
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
        | raw_evidence,
    )


RAW_IBM32_NOTE = (
    "Second leg, reported separately and NOT part of G2d's verdict. The decoded "
    "comparison above is the gate; this one compares the undecoded uint32 words in "
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

    **The raw ``ibm32`` words are a second, separate leg.** Where the store carries the
    parallel ``amplitude_raw_ibm32`` view (``OPEN_DEBTS`` D1), the undecoded ``uint32``
    words are additionally compared against the source, and the result is recorded as
    ``raw_ibm32_words_verified`` / ``raw_ibm32_identical``. That comparison is **exactly
    invertible by construction** and therefore says something the decoded comparison
    cannot — but it does **not** decide this plane's verdict, in either direction: it
    cannot rescue a decoded mismatch, and a raw mismatch cannot convert a decoded pass
    into a failure here. G2d is defined on the decoded samples (§4.5); the raw leg is
    evidence the certificate carries alongside it, and a reader must be able to see the
    two facts separately because a store can have correct raw words and a lossy decode.
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

    ok = not mismatches and trace_map.invertible and raw_ok
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
        | raw_evidence,
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
