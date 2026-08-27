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

DERIVED WORK — ATTRIBUTION AT THE POINT OF USE
----------------------------------------------
This driver is seeded from TGS's ``tests/integration/test_segy_roundtrip_teapot.py``
in ``TGSAI/mdio-python`` at commit ``a2895b53088ffacbf4bd1b9e882856cbda78e235``.
Copyright TGS, licensed under the Apache License, Version 2.0.

SDIP extends that test — which is scoped to spec-declared header fields — to the full
240-byte trace-header plane and to a whole-file SHA-256 assertion. The extension is
SDIP's; the seed is TGS's.

``NOTICE`` §3 carries the binding attribution and is the authoritative record. This
header repeats it because the obligation belongs where the code is read, not only in a
file a reader may never open.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sdip.errors import RoundTripUnavailableError
from sdip.guard.warn import WarningLedger, recording_warnings
from sdip.ingest.file_headers import UPSTREAM_FILE_HEADER_VARIABLE
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


def _assert_exportable(store: Path) -> None:
    """Refuse, cleanly and before any work, a store that cannot produce an export.

    ``mdio_to_segy`` reads the textual and binary headers off the ``segy_file_header``
    variable and raises ``MDIOMissingVariableError`` when it is absent. SDIP writes a
    store without that variable on exactly one path: a source whose textual header did
    not decode, ingested with upstream's file-header persistence off so that the header
    bytes were never rewritten (§4.2, ``DECISIONS.md`` D-0055).

    Caught here, and turned into an ``SdipError``, so the operator gets a message that
    names the cause rather than an upstream traceback about a missing variable — §11.4
    requires a malformed source to produce a clean error, and a non-conforming textual
    header is exactly such a source.

    **G3 is genuinely unreachable for such a store, not merely awkward.** Upstream's
    exporter re-encodes the stored *decoded* text back to EBCDIC, and runs
    ``sanitize_text_header`` over anything that will not encode — so even a store that
    did carry the sanitised header would export 3200 bytes that are not the source's.
    Byte identity is impossible either way; refusing says so instead of producing a
    plausible file that fails the hash.

    Raises:
        RoundTripUnavailableError: If the store carries no ``segy_file_header`` variable.
    """
    import zarr

    if UPSTREAM_FILE_HEADER_VARIABLE in zarr.open_group(str(store), mode="r"):
        return
    msg = (
        f"cannot export {store}: it carries no `{UPSTREAM_FILE_HEADER_VARIABLE}` "
        "variable, so MDIO's exporter has no textual or binary header to write. SDIP "
        "writes a store in this shape for a source whose textual header could not be "
        "decoded - the raw 3200 bytes are preserved and Plane 1 is checked against them "
        "(§4.2), but upstream's exporter would sanitise the header it wrote, so the "
        "whole-file byte identity G3 requires is not reachable for this source. G3 is "
        "therefore NOT_RUN rather than passed or failed on a guess."
    )
    raise RoundTripUnavailableError(msg)


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

    Raises:
        RoundTripUnavailableError: If the store carries no ``segy_file_header`` variable,
            which is the shape SDIP writes for a source whose textual header did not
            decode (``DECISIONS.md`` D-0055).
    """
    store_path, output_path, source_path = Path(store), Path(output), Path(source)
    _assert_exportable(store_path)
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
