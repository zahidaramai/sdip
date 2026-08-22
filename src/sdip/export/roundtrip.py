"""MDIO to SEG-Y export and **gate G3 — round trip**. Specification §7 G3.

    PASS iff sha256(export) == sha256(source) for the whole file.

**Whole file, one hash, no per-field reconciliation.** A round trip that compares parsed
fields can pass while the bytes differ — different padding, a rewritten header, a
reordered extended block. The point of G3 is that it cannot: it is the check that needs
no interpretation and admits no argument.

``ROUNDTRIP-SCOPED`` exists for sources whose non-conformance makes byte-identity
impossible, and it is deliberately expensive to claim: it requires per-plane equality
**plus a written justification naming the specific non-conformance**, on the certificate.
It is never inferred from a hash mismatch — a mismatch with no justification is a
failure, full stop.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sdip.guard.warn import WarningLedger, recording_warnings
from sdip.provenance.hashing import sha256_file


@dataclass(slots=True)
class RoundTripResult:
    """Result of exporting a store back to SEG-Y and hashing both files."""

    source_path: str
    source_sha256: str
    export_path: str
    export_sha256: str
    source_bytes: int
    export_bytes: int
    scoped: dict[str, str] | None = None
    warnings: WarningLedger = field(default_factory=WarningLedger)

    @property
    def byte_identical(self) -> bool:
        """True when the exported file is byte-for-byte the source."""
        return self.source_sha256 == self.export_sha256

    @property
    def status(self) -> str:
        """G3's verdict. ``ROUNDTRIP-SCOPED`` requires a written justification."""
        if self.byte_identical:
            return "PASS"
        return "ROUNDTRIP-SCOPED" if self.scoped else "FAIL"

    @property
    def passed(self) -> bool:
        """True for a clean pass. A scoped result is not a pass."""
        return self.byte_identical

    def first_difference(self) -> dict[str, Any] | None:
        """Locate the first differing byte between source and export.

        Streamed in blocks: a survey-scale export must not be loaded into memory to be
        diagnosed (§11.2).
        """
        if self.byte_identical:
            return None
        if self.source_bytes != self.export_bytes:
            return {
                "kind": "length",
                "source_bytes": self.source_bytes,
                "export_bytes": self.export_bytes,
            }
        chunk = 1 << 20
        offset = 0
        with Path(self.source_path).open("rb") as a, Path(self.export_path).open("rb") as b:
            while True:
                left, right = a.read(chunk), b.read(chunk)
                if not left:
                    return None  # pragma: no cover - lengths already matched
                if left != right:
                    for i, (x, y) in enumerate(zip(left, right, strict=False)):
                        if x != y:
                            return {
                                "kind": "byte",
                                "offset": offset + i,
                                "expected": x,
                                "observed": y,
                                "region": _region_of(offset + i),
                            }
                offset += len(left)

    def to_json(self) -> dict[str, Any]:
        """Certificate-shaped mapping for the ``roundtrip`` block (§4.7)."""
        payload: dict[str, Any] = {
            "performed": True,
            "export_sha256": self.export_sha256,
            "export_bytes": self.export_bytes,
            "byte_identical": self.byte_identical,
            "status": self.status,
            "first_difference": self.first_difference(),
        }
        if self.scoped:
            payload["scoped"] = dict(self.scoped)
        return payload


def _region_of(offset: int) -> str:
    """Name the SEG-Y region a byte offset falls in. Turns a number into a diagnosis."""
    if offset < 3200:
        return f"textual header, byte {offset + 1} of 3200"
    if offset < 3600:
        return f"binary header, byte {offset - 3200 + 1} of 400"
    return f"trace data, {offset - 3600} bytes past the first trace"


def export(
    store: str | Path,
    output: str | Path,
    spec: Any,
    *,
    source: str | Path,
    scoped: dict[str, str] | None = None,
) -> RoundTripResult:
    """Export an MDIO store to SEG-Y and run G3 against the source.

    Args:
        store: MDIO store to export.
        output: Where to write the SEG-Y.
        spec: The gap-free ``SegySpec`` the store was ingested with. **The same spec**:
            exporting under a different spec would compare two different readings of the
            same bytes and prove nothing.
        source: The original SEG-Y, for the hash comparison.
        scoped: Optional ``{"non_conformance": ..., "justification": ...}``. Supplying
            it does not *make* a mismatch acceptable - it records why byte-identity was
            impossible for this source, and the certificate carries it verbatim.

    Returns:
        The round-trip result.
    """
    store_path, output_path, source_path = Path(store), Path(output), Path(source)
    ledger = WarningLedger()
    with recording_warnings(ledger, reemit=False):
        from mdio import mdio_to_segy

        mdio_to_segy(segy_spec=spec, input_path=store_path, output_path=output_path)

    return RoundTripResult(
        source_path=str(source_path),
        source_sha256=sha256_file(source_path),
        export_path=str(output_path),
        export_sha256=sha256_file(output_path),
        source_bytes=source_path.stat().st_size,
        export_bytes=output_path.stat().st_size,
        scoped=scoped,
        warnings=ledger,
    )
