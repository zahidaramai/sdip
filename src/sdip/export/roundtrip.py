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
in ``TGSAI/mdio-python`` at commit ``76df396e545017d2a32ee25a5f98989fa37afec4``.
Copyright TGS, licensed under the Apache License, Version 2.0.

SDIP extends that test — which is scoped to spec-declared header fields — to the full
240-byte trace-header plane and to a whole-file SHA-256 assertion. The extension is
SDIP's; the seed is TGS's.

``NOTICE`` §3 carries the binding attribution and is the authoritative record. This
header repeats it because the obligation belongs where the code is read, not only in a
file a reader may never open.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sdip._pins import SEGY_BINARY_HEADER_BYTES, SEGY_TEXTUAL_HEADER_BYTES
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
    restored: dict[str, Any] | None = None
    """What SDIP wrote over upstream's export from the store's own records (D71, D72):
    ``binary_header_bytes`` (1-based bytes where upstream's encoding differed from the
    stored raw header), ``trace_order`` and ``traces_moved``."""

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
        if self.restored is not None:
            payload["restored"] = dict(self.restored)
        return payload


HEADER_SCOPE_RULING = "D-0098"
"""The maintainer ruling that accepts :class:`HeaderScopedRoundTrip` for release."""

REVISION_SCOPE_RULING = "D-0106"
"""The owner's ruling (OPEN_DEBTS D61) for a source whose revision word is undefined."""

SCOPE_RULINGS: frozenset[str] = frozenset({HEADER_SCOPE_RULING, REVISION_SCOPE_RULING})
"""Every ruling under which a scoped G3 may count toward release. Nothing else does."""

DEFINED_REVISION_CODES: frozenset[int] = frozenset({0x0000, 0x0100, 0x0200, 0x0201})
"""Binary-header bytes 3501-3502 for SEG-Y revisions 0, 1, 2 and 2.1."""

REV2_REVISION_CODES: frozenset[int] = frozenset({0x0200, 0x0201})
"""Revision 2 and 2.1 words. Read under a revision below 2 they lose the pair too (D68)."""

_REVISION_KEYS = ("segy_revision_major", "segy_revision_minor")


@dataclass(frozen=True, slots=True)
class HeaderScopedRoundTrip:
    """G3 for a source whose textual header does not decode: ``ROUNDTRIP-SCOPED``, unexported.

    **DECISIONS.md D-0098, closing OPEN_DEBTS D17's open half.** Such a store is written
    with the raw 3200 bytes on the root group and no ``segy_file_header`` variable (D-0055),
    so upstream's exporter cannot run, and could not reproduce the bytes if it did: it
    sanitises any character that will not encode. Whole-file byte identity is impossible
    for the source, not merely unattempted - the case §7 G3 reserves ``ROUNDTRIP-SCOPED``
    for. The justification names every offending character, measured on the file's own
    bytes, and is only issued when :func:`header_scope` finds exactly this store shape.

    **Never a pass** (``passed`` is False), and never inferred: G3 still FAILs any export
    that was made and differs. ``performed`` is False on the certificate, so no reader
    mistakes it for a round trip that happened.
    """

    non_conformance: str
    justification: str
    ruling: str = HEADER_SCOPE_RULING

    status = "ROUNDTRIP-SCOPED"
    byte_identical = False
    passed = False

    def to_json(self) -> dict[str, Any]:
        """Certificate-shaped ``roundtrip`` block: no export was made."""
        return {
            "performed": False,
            "byte_identical": False,
            "status": self.status,
            "first_difference": None,
            "scoped": {
                "non_conformance": self.non_conformance,
                "justification": self.justification,
                "ruling": self.ruling,
            },
        }


def header_scope(decode: Any, store: str | Path) -> HeaderScopedRoundTrip | None:
    """The scoped G3 for ``store``, or ``None`` when it can be exported as usual.

    Only when the ingest MEASURED the textual header as undecodable and the store carries
    no ``segy_file_header`` variable as a result. Anything else goes through :func:`export`
    and is judged on its hash.
    """
    import zarr

    if decode is None or getattr(decode, "decoded", True):
        return None
    if UPSTREAM_FILE_HEADER_VARIABLE in zarr.open_group(str(store), mode="r"):
        return None
    cells = ", ".join(f"card {row + 1} column {col + 1}" for row, col in decode.offending[:10])
    more = "" if len(decode.offending) <= 10 else f" and {len(decode.offending) - 10} more"
    return HeaderScopedRoundTrip(
        non_conformance=(
            f"textual header: {decode.reason} - {cells}{more} (declared {decode.encoding})"
        ),
        justification=(
            "the textual header does not decode to 40 cards of 80 printable characters, so "
            "the store preserves its raw 3200 bytes and carries no segy_file_header variable "
            "(D-0055). Upstream's exporter needs that variable and sanitises any character "
            "that will not encode, so a whole-file byte-identical export is impossible for "
            "this source. Planes 1-5 verify the store against the source, Plane 1 against the "
            "raw bytes. Accepted for release by maintainer ruling D-0098."
        ),
    )


def revision_scope(
    source: str | Path, store: str | Path, *, read_revision: float | int = 1
) -> HeaderScopedRoundTrip | None:
    """The scoped G3 for a source whose revision word the writer cannot carry, or ``None``.

    Two cases, both under the owner's ruling D-0106: an **undefined** word (OPEN_DEBTS D61),
    and a revision 2 or 2.1 word **read under a revision below 2** (OPEN_DEBTS D68, the
    owner: *"Extend D-0106 scope to it"*).

    **OPEN_DEBTS D61, owner ruling D-0106.** Upstream stores such a source's binary header
    with one undivided ``segy_revision`` value instead of the ``segy_revision_major`` /
    ``segy_revision_minor`` pair, and its own exporter refuses a store without the pair
    (``mdio.segy.compat.encode_segy_revision``: *"Missing revision keys from binary
    header"*). No export can be made at the pinned writer, and SDIP rewriting the stored
    header to make one would be fabrication (SP12). Issued only when **both** are measured:
    bytes 3501-3502 of the source hold no defined revision, and the store's binary header
    lacks the pair. Anything else goes through :func:`export` and is judged on its hash.
    """
    import zarr

    from sdip.ingest.file_headers import read_raw_file_headers

    code = int.from_bytes(read_raw_file_headers(source).binary[300:302], "big")
    rev2_read_low = code in REV2_REVISION_CODES and float(read_revision) < 2
    if code in DEFINED_REVISION_CODES and not rev2_read_low:
        return None
    group = zarr.open_group(str(store), mode="r")
    if UPSTREAM_FILE_HEADER_VARIABLE not in group:
        return None
    raw = group[UPSTREAM_FILE_HEADER_VARIABLE].attrs.get("binaryHeader")
    stored = dict(raw) if isinstance(raw, Mapping) else {}
    if all(key in stored for key in _REVISION_KEYS):
        return None
    what = (
        f"is a revision {code >> 8}.{code & 0xFF} word read as revision {read_revision}"
        if rev2_read_low
        else f"(major {code >> 8}, minor {code & 0xFF}) is no defined SEG-Y revision"
    )
    debt = "OPEN_DEBTS D68" if rev2_read_low else "OPEN_DEBTS D61"
    return HeaderScopedRoundTrip(
        non_conformance=(
            f"binary header bytes 3501-3502: revision word 0x{code:04x} {what}; the store "
            f"records it as segy_revision={stored.get('segy_revision')!r} without a "
            "major/minor pair"
        ),
        justification=(
            "upstream's exporter requires the binary header's revision as a major/minor pair "
            "and refuses this store ('Missing revision keys from binary header', "
            "mdio.segy.compat), so no whole-file export can be made at the pinned writer, "
            "and SDIP does not rewrite stored header values to make one (SP12). Planes 1-5 "
            "verify the store against the source, Plane 2 against the raw 400 bytes. "
            f"Accepted for release by the owner's ruling D-0106 ({debt})."
        ),
        ruling=REVISION_SCOPE_RULING,
    )


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
    from sdip.guard.env import refuse_barred_env_vars
    from sdip.guard.library_config import refuse_library_config

    # The same refusal ingest makes, for the same reason: a segy override arriving through
    # the environment changes how the store is re-encoded without appearing anywhere the
    # round trip records (D-0087).
    refuse_barred_env_vars("export")
    refuse_library_config("export")
    store_path, output_path, source_path = Path(store), Path(output), Path(source)
    _assert_exportable(store_path)
    ledger = WarningLedger()
    with recording_warnings(ledger, reemit=False):
        from mdio import mdio_to_segy

        mdio_to_segy(segy_spec=spec, input_path=store_path, output_path=output_path)

    restored: dict[str, Any] = {
        "binary_header_bytes": restore_binary_header(store_path, output_path)
    }
    moved = restore_source_order(store_path, output_path)
    if moved is None:
        restored["trace_order"] = "grid"
        if scoped is None:
            scoped = grid_order_scope(store_path, source_path, output_path)
    else:
        restored["trace_order"] = "source"
        restored["traces_moved"] = moved

    return RoundTripResult(
        source_path=str(source_path),
        source_sha256=sha256_file(source_path),
        export_path=str(output_path),
        export_sha256=sha256_file(output_path),
        source_bytes=source_path.stat().st_size,
        export_bytes=output_path.stat().st_size,
        scoped=scoped,
        warnings=ledger,
        restored=restored,
    )


def restore_binary_header(store: Path, exported: Path) -> list[int]:
    """Write the store's raw 400-byte binary header over the exported file's (D71).

    Upstream's exporter re-encodes the binary header from parsed fields, so a byte no field
    names (an unassigned byte, often vendor data) comes back as ``0x00``. The store holds
    the source's own 400 bytes, verified by Plane 2 and authoritative on conflict (§4.3).
    Writing them back is not a transform: it puts the source's bytes where they were.

    Returns:
        The 1-based binary-header bytes where upstream's encoding differed from the stored
        copy, so the certificate shows exactly what was written over.
    """
    from sdip.ingest.file_headers import read_raw_binary_from_store

    raw = read_raw_binary_from_store(store)
    if len(raw) != SEGY_BINARY_HEADER_BYTES:
        msg = (
            f"the store's raw binary header is {len(raw)} bytes, not "
            f"{SEGY_BINARY_HEADER_BYTES}; it cannot be written back"
        )
        raise RoundTripUnavailableError(msg)
    with exported.open("r+b") as handle:
        handle.seek(SEGY_TEXTUAL_HEADER_BYTES)
        written = handle.read(SEGY_BINARY_HEADER_BYTES)
        differing = [i + 1 for i, (a, b) in enumerate(zip(raw, written, strict=False)) if a != b]
        if differing:
            handle.seek(SEGY_TEXTUAL_HEADER_BYTES)
            handle.write(raw)
    return differing


GRID_ORDER_NON_CONFORMANCE = "grid order"
"""G3's scope reason for a store that records no source trace order (D72, P19)."""


def _trace_records(path: Path, count: int) -> tuple[int, int]:
    """``(data_offset, stride)`` of a SEG-Y holding ``count`` trace records, by arithmetic.

    The offset comes from the binary header's extended-header count (bytes 3505-3506); the
    stride from what remains divided by ``count``, which must divide exactly.
    """
    size = path.stat().st_size
    with path.open("rb") as handle:
        handle.seek(SEGY_TEXTUAL_HEADER_BYTES + 304)
        extended = int.from_bytes(handle.read(2), "big", signed=True)
    data_offset = SEGY_TEXTUAL_HEADER_BYTES + SEGY_BINARY_HEADER_BYTES
    data_offset += max(extended, 0) * SEGY_TEXTUAL_HEADER_BYTES
    body = size - data_offset
    if count <= 0 or body <= 0 or body % count:
        msg = (
            f"{path.name}: {body} bytes of trace data do not divide into {count} trace "
            "records, so no record boundary in it can be trusted"
        )
        raise RoundTripUnavailableError(msg)
    return data_offset, body // count


def restore_source_order(store: Path, exported: Path) -> int | None:
    """Rewrite the exported trace records into the source order the store records (D72).

    Upstream writes one record per live cell in grid (C) order. That is checked, not
    assumed: every record's 240 header bytes must equal the store's ``headers_raw_uint8``
    at the cell it is taken to be. The records are then written back sorted by the
    store's ``source_trace_ordinal``, streamed one record at a time.

    Returns:
        How many records changed position, or ``None`` when the store records no source
        order (written before the array existed), in which case the file is untouched.

    Raises:
        RoundTripUnavailableError: If the store records an order but upstream's records
            cannot be matched to cells, so a reorder would be a guess.
    """
    import numpy as np
    import zarr

    from sdip.ingest.header_plane import ARRAY_NAME as HEADER_PLANE
    from sdip.ingest.header_plane import ORDINAL_ARRAY_NAME

    group = zarr.open_group(str(store), mode="r")
    if ORDINAL_ARRAY_NAME not in group:
        return None
    if HEADER_PLANE not in group:
        msg = (
            f"the store records source order but carries no {HEADER_PLANE}, so upstream's "
            "trace records cannot be matched to cells"
        )
        raise RoundTripUnavailableError(msg)
    ordinal_array: Any = group[ORDINAL_ARRAY_NAME]
    ordinals = np.asarray(ordinal_array[...])
    plane: Any = group[HEADER_PLANE]
    mask: Any = group["trace_mask"]
    live = np.argwhere(np.asarray(mask[...]).astype(bool))  # C order, as upstream writes
    count = len(live)
    data_offset, stride = _trace_records(exported, count)

    with exported.open("rb") as handle:
        for position, cell in enumerate(live):
            handle.seek(data_offset + position * stride)
            if handle.read(240) != np.asarray(plane[tuple(cell)]).tobytes():
                msg = (
                    f"exported trace record {position} does not carry the header bytes of "
                    f"grid cell {[int(i) for i in cell]}: upstream did not write live cells "
                    "in grid order, so restoring source order would be a guess"
                )
                raise RoundTripUnavailableError(msg)

    order = np.argsort(ordinals[tuple(live.T)], kind="stable")
    moved = int(np.count_nonzero(order != np.arange(count)))
    if moved == 0:
        return 0
    staging = exported.with_name(exported.name + ".sdip-order")
    with exported.open("rb") as source, staging.open("wb") as target:
        target.write(source.read(data_offset))
        for position in order:
            source.seek(data_offset + int(position) * stride)
            target.write(source.read(stride))
    staging.replace(exported)
    return moved


def grid_order_scope(store: Path, source: Path, exported: Path) -> dict[str, str] | None:
    """G3's scope for a store with no recorded source order, when order is the only change.

    ``ROUNDTRIP-SCOPED: grid order`` only if the export has the source's length and file
    headers and the same multiset of trace records. Any other difference returns ``None``,
    and G3 stays a FAIL.
    """
    import hashlib
    from collections import Counter

    import numpy as np
    import zarr

    if source.stat().st_size != exported.stat().st_size:
        return None
    mask: Any = zarr.open_group(str(store), mode="r")["trace_mask"]
    count = int(np.asarray(mask[...]).sum())
    try:
        data_offset, stride = _trace_records(exported, count)
    except RoundTripUnavailableError:
        return None
    with source.open("rb") as a, exported.open("rb") as b:
        if a.read(data_offset) != b.read(data_offset):
            return None
    tallies: list[Counter[str]] = []
    for path in (source, exported):
        tally: Counter[str] = Counter()
        with path.open("rb") as handle:
            handle.seek(data_offset)
            for _ in range(count):
                tally[hashlib.sha256(handle.read(stride)).hexdigest()] += 1
        tallies.append(tally)
    if tallies[0] != tallies[1]:
        return None
    return {
        "non_conformance": GRID_ORDER_NON_CONFORMANCE,
        "justification": (
            "The store was written before SDIP recorded source trace order (D72), so export "
            "writes upstream's grid order. The export holds the source's file headers and "
            "exactly the source's trace records, byte for byte, in a different order."
        ),
    }
