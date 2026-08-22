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

from sdip._pins import SEGY_BINARY_HEADER_BYTES, SEGY_TEXTUAL_HEADER_BYTES
from sdip.ingest.file_headers import read_raw_file_headers, read_raw_file_headers_from_store
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
    observed = read_raw_file_headers_from_store(store).textual
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
    observed = read_raw_file_headers_from_store(store).binary
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
