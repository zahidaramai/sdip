"""Textual and binary file-header capture. Planes 1 and 2, §4.2 and §4.3.

Three measured facts about the pinned upstream shape this module, all read out of
`multidimio` 1.2.1 rather than from documentation:

**1. MDIO discards both file headers by default.**
``MDIOSettings.save_segy_file_header`` defaults to ``0`` — off. A default
``segy_to_mdio`` produces a store with **no** ``segy_file_header`` variable at all: the
3200-byte textual header and the 400-byte binary header are simply not there. Plane 1
and Plane 2 fail, and ``mdio_to_segy`` refuses outright, so G3 is unreachable too. This
is exactly the silent loss §0.1 exists to prevent, and it is the default.

**2. Mode 2 is barred by the Equivalence Contract.**
``save_segy_file_header`` mode 2 (LENIENT) runs ``sanitize_text_header``, which
*"replaces unsafe characters with spaces and pads/truncates each row"*. §4.2 is explicit:
**"Decode failure is not an ingestion failure; silent substitution is."** SDIP uses mode
**1 (STRICT)** and never mode 2.

**3. The raw binary header is gated on a barred variable.**
``rawBinaryHeader`` is written only when ``settings.raw_headers`` is set — that is
``MDIO__IMPORT__RAW_HEADERS``, barred by §9.1. So §4.3's *"raw bytes are authoritative on
conflict"* is unreachable through MDIO without violating the forbid list.

**SDIP therefore captures the raw bytes itself, straight from the source.** The first
3600 bytes of a SEG-Y are the textual header followed by the binary header, by
definition, at fixed offsets, in every revision. Reading them needs no spec, no parser,
no setting, and no barred variable — the same reasoning as §3.2: reach the goal through
a legitimate path rather than a deprecated flag.

SDIP stores both under its own attribute namespace so they cannot be confused with
upstream's parsed view, and so §4.3's *parsed mapping* **and** *raw bytes* both exist
with the raw ones unambiguously authoritative.
"""

from __future__ import annotations

import base64
import os
from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from sdip._pins import SEGY_BINARY_HEADER_BYTES, SEGY_TEXTUAL_HEADER_BYTES
from sdip.errors import UntrustedInputError
from sdip.provenance.hashing import sha256_bytes

SAVE_FILE_HEADER_VAR: Final[str] = "MDIO__IMPORT__SAVE_SEGY_FILE_HEADER"
SAVE_FILE_HEADER_STRICT: Final[str] = "1"
"""Mode 1. Persists the headers and raises on a malformed text header.

Mode 2 exists and is **never** used: it silently rewrites the text header (§4.2).
"""

SAVE_FILE_HEADER_OFF: Final[str] = "0"
"""Mode 0. Upstream's default: persists neither file header and validates nothing.

Used on exactly one path — a source whose textual header **cannot be decoded** (§4.2,
``DECISIONS.md`` D-0055). It is not a preference and never applies to a decodable
source: it costs upstream's parsed views, and the store it produces cannot be exported.
"""

TEXT_HEADER_ROWS: Final[int] = 40
TEXT_HEADER_COLS: Final[int] = 80
"""The card layout the SEG-Y standard mandates: 40 rows of 80 characters, 3200 bytes.

Fixed rather than read off the spec because the decode contract §4.2 states, and the
contract upstream enforces, are both this shape and no other. A ``TextHeaderSpec``
declaring anything else describes a file that is not a SEG-Y textual header.
"""

MAX_ASCII_ORDINAL: Final[int] = 127
"""A textual header card is 7-bit ASCII. Anything above this did not decode."""

ATTR_RAW_TEXT: Final[str] = "sdipRawTextHeader"
ATTR_RAW_BINARY: Final[str] = "sdipRawBinaryHeader"
ATTR_RAW_TEXT_SHA: Final[str] = "sdipRawTextHeaderSha256"
ATTR_RAW_BINARY_SHA: Final[str] = "sdipRawBinaryHeaderSha256"
"""SDIP's own namespace. Upstream's parsed view keeps its own keys; these are the
authoritative bytes and are named so nobody has to guess which is which."""


@contextmanager
def _save_file_header_mode(mode: str) -> Iterator[None]:
    """Pin ``MDIO__IMPORT__SAVE_SEGY_FILE_HEADER`` for one call, then restore it.

    Scoped and restored, so SDIP does not leave the process configured differently from
    how it found it — the same discipline applied to upstream's leaking warning filters
    (``DECISIONS.md`` D-0004).

    The mode is written **explicitly on every path**, including the one that wants
    upstream's own default. An ambient value is not a default: a process that inherited
    ``…=2`` would silently sanitise the header §4.2 forbids sanitising, and the ingest
    would look like it worked.

    ``MDIO__IMPORT__SAVE_SEGY_FILE_HEADER`` is **not** a barred variable (§9.1 bars
    ``MDIO_IGNORE_CHECKS`` and ``MDIO__IMPORT__RAW_HEADERS``). The distinction is the
    direction of travel: a barred variable *weakens* a check or depends on a deprecated
    path, while this one causes **more** of the source to be preserved. Setting it is
    the opposite of the thing §9.1 forbids.
    """
    previous = os.environ.get(SAVE_FILE_HEADER_VAR)
    os.environ[SAVE_FILE_HEADER_VAR] = mode
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop(SAVE_FILE_HEADER_VAR, None)
        else:
            os.environ[SAVE_FILE_HEADER_VAR] = previous


def file_headers_persisted() -> AbstractContextManager[None]:
    """Enable MDIO's file-header persistence in STRICT mode for one call. Mode 1."""
    return _save_file_header_mode(SAVE_FILE_HEADER_STRICT)


def file_headers_not_persisted() -> AbstractContextManager[None]:
    """Pin MDIO's file-header persistence **off** for one call. Mode 0.

    The undecodable-textual-header path and nothing else (§4.2, ``DECISIONS.md``
    D-0055). Mode 1 raises on such a header and mode 2 rewrites it; mode 0 is the only
    one that lets the ingest complete without upstream substituting bytes SDIP is
    required to preserve verbatim. What it costs is recorded on the certificate, not
    hidden: no ``segy_file_header`` variable, so no parsed views and no export.
    """
    return _save_file_header_mode(SAVE_FILE_HEADER_OFF)


@dataclass(frozen=True, slots=True)
class TextualHeaderDecode:
    """Whether the raw textual header decodes, measured from the bytes themselves.

    §4.2 requires the detected encoding **recorded, never silently normalised**, and
    requires a decode failure recorded on the certificate rather than raised as an
    ingestion failure. Both need an answer that was measured on this file; before
    ``DECISIONS.md`` D-0055 the certificate asserted ``decoded`` unconditionally, which
    is a claim with no number behind it (**SP8**).
    """

    encoding: str
    """The declared encoding, from the spec the ingest ran with. Recorded, never used
    to normalise: Plane 1 compares bytes."""

    decoded: bool
    """True when the 3200 bytes decode to 40 rows of 80 printable 7-bit ASCII."""

    offending: tuple[tuple[int, int], ...]
    """``(row, column)`` of every character that failed the contract. 0-based, exhaustive."""

    reason: str
    """What failed, in one clause. Empty when :attr:`decoded`."""

    @property
    def status(self) -> str:
        """The certificate's ``decode_status`` enum value (§4.7)."""
        return "decoded" if self.decoded else "raw_preserved_decode_failed"

    def to_json(self) -> dict[str, Any]:
        """The certificate's ``detected_encoding`` block, §4.7."""
        detail = (
            "SDIP stores the raw 3200 bytes and compares them as bytes; the encoding is "
            "recorded, never used to normalise (§4.2)."
            if self.decoded
            else (
                f"{self.reason}. The raw 3200 bytes are preserved verbatim and Plane 1 "
                f"is checked against them; decode failure is not an ingestion failure, "
                f"silent substitution is (§4.2). Offending (row, column), 0-based: "
                f"{[list(p) for p in self.offending[:16]]}"
                + (f" (+{len(self.offending) - 16} more)" if len(self.offending) > 16 else "")
            )
        )
        return {"encoding": self.encoding, "decode_status": self.status, "detail": detail}


def classify_textual_header(raw: bytes, text_spec: Any) -> TextualHeaderDecode:
    """Decide whether the raw textual header decodes, using the ingest's own spec.

    The decode is performed by ``text_spec.decode`` — the **same** ``TextHeaderSpec``
    object handed to ``segy_to_mdio``, and the same call ``SegyFile.text_header`` makes,
    so the string judged here is byte-for-byte the string upstream would judge. Only the
    verdict is SDIP's, and it restates §4.2's contract rather than importing upstream's
    validator: §3.3 permits the public API, not a reach into a module upstream does not
    export.

    Being SDIP's own predicate, it can disagree with upstream's. The ingest is arranged
    so that either direction of disagreement is safe rather than silent — see
    :func:`sdip.ingest.orchestrator.ingest`. Agreement is measured on both fixtures
    rather than assumed (``tests/integration/test_undecodable_textheader.py``).

    Args:
        raw: The 3200 raw textual-header bytes, straight from the source.
        text_spec: The ``TextHeaderSpec`` the ingest runs with.

    Returns:
        The measured decode outcome.

    Raises:
        UntrustedInputError: If ``raw`` is not exactly 3200 bytes.
    """
    if len(raw) != SEGY_TEXTUAL_HEADER_BYTES:
        msg = f"textual header is {len(raw)} bytes, must be {SEGY_TEXTUAL_HEADER_BYTES}"
        raise UntrustedInputError(msg)

    encoding = str(getattr(text_spec.encoding, "value", text_spec.encoding))
    rows = str(text_spec.decode(raw)).split("\n")

    if len(rows) != TEXT_HEADER_ROWS:
        return TextualHeaderDecode(
            encoding=encoding,
            decoded=False,
            offending=(),
            reason=f"decoded to {len(rows)} rows, the card layout mandates {TEXT_HEADER_ROWS}",
        )
    wrong_width = [i for i, row in enumerate(rows) if len(row) != TEXT_HEADER_COLS]
    if wrong_width:
        return TextualHeaderDecode(
            encoding=encoding,
            decoded=False,
            offending=tuple((i, len(rows[i])) for i in wrong_width),
            reason=(
                f"{len(wrong_width)} row(s) are not {TEXT_HEADER_COLS} columns wide; "
                "the pairs below are (row, observed width)"
            ),
        )

    offending = tuple(
        (i, j)
        for i, row in enumerate(rows)
        for j, char in enumerate(row)
        if ord(char) > MAX_ASCII_ORDINAL or not char.isprintable()
    )
    if offending:
        return TextualHeaderDecode(
            encoding=encoding,
            decoded=False,
            offending=offending,
            reason=(
                f"{len(offending)} character(s) are non-ASCII or non-printable after the "
                f"declared {encoding} decode"
            ),
        )
    return TextualHeaderDecode(encoding=encoding, decoded=True, offending=(), reason="")


@dataclass(frozen=True, slots=True)
class RawFileHeaders:
    """The first 3600 bytes of a SEG-Y, split at the fixed boundary."""

    textual: bytes
    binary: bytes

    def __post_init__(self) -> None:
        """Reject anything that is not exactly the mandated size."""
        if len(self.textual) != SEGY_TEXTUAL_HEADER_BYTES:
            msg = (
                f"textual header is {len(self.textual)} bytes, must be {SEGY_TEXTUAL_HEADER_BYTES}"
            )
            raise UntrustedInputError(msg)
        if len(self.binary) != SEGY_BINARY_HEADER_BYTES:
            msg = f"binary header is {len(self.binary)} bytes, must be {SEGY_BINARY_HEADER_BYTES}"
            raise UntrustedInputError(msg)

    @property
    def textual_sha256(self) -> str:
        """Digest of the raw textual header."""
        return sha256_bytes(self.textual)

    @property
    def binary_sha256(self) -> str:
        """Digest of the raw binary header."""
        return sha256_bytes(self.binary)

    def to_attrs(self) -> dict[str, str]:
        """SDIP-namespaced store attributes carrying the authoritative bytes."""
        return {
            ATTR_RAW_TEXT: base64.b64encode(self.textual).decode("ascii"),
            ATTR_RAW_BINARY: base64.b64encode(self.binary).decode("ascii"),
            ATTR_RAW_TEXT_SHA: self.textual_sha256,
            ATTR_RAW_BINARY_SHA: self.binary_sha256,
        }

    def to_json(self) -> dict[str, Any]:
        """Certificate-shaped mapping. Digests, not the bytes themselves."""
        return {
            "textual_bytes": len(self.textual),
            "textual_sha256": self.textual_sha256,
            "binary_bytes": len(self.binary),
            "binary_sha256": self.binary_sha256,
        }


def read_raw_file_headers(source: str | Path) -> RawFileHeaders:
    """Read the raw textual and binary headers straight from a SEG-Y source.

    Reads exactly 3600 bytes at fixed offsets and nothing else. No spec, no parser, no
    setting, no allocation proportional to file size — §11.4 requires that a
    header-declared length never drives an allocation, and this reads none.

    Args:
        source: SEG-Y file.

    Returns:
        The two raw headers.

    Raises:
        UntrustedInputError: If the file is too short to contain both.
    """
    total = SEGY_TEXTUAL_HEADER_BYTES + SEGY_BINARY_HEADER_BYTES
    with Path(source).open("rb") as handle:
        blob = handle.read(total)
    if len(blob) != total:
        msg = (
            f"source has {len(blob)} bytes before the first trace; a SEG-Y must begin "
            f"with {SEGY_TEXTUAL_HEADER_BYTES} textual + {SEGY_BINARY_HEADER_BYTES} binary"
        )
        raise UntrustedInputError(msg)
    return RawFileHeaders(
        textual=blob[:SEGY_TEXTUAL_HEADER_BYTES],
        binary=blob[SEGY_TEXTUAL_HEADER_BYTES:],
    )


UPSTREAM_FILE_HEADER_VARIABLE: Final[str] = "segy_file_header"
"""The scalar variable upstream hangs its parsed ``textHeader``/``binaryHeader`` on.

**Absent from a store whose textual header did not decode**, because that ingest ran
with header persistence off (``DECISIONS.md`` D-0055). Its absence is the store-level
signal that the source was non-conforming, and the reason nothing may assume it exists.
"""


def raw_header_node(group: Any) -> Any:
    """The node SDIP's authoritative raw-header attributes live on.

    Upstream's ``segy_file_header`` variable when the store has one, and the root group
    when it does not. **One resolver, used everywhere**: the reader, the writer and G7's
    textual-header controls must agree about where the bytes are, or a control would
    error on a store shape the reader handles and G7 would report a corruption it never
    applied.
    """
    if UPSTREAM_FILE_HEADER_VARIABLE in group:
        return group[UPSTREAM_FILE_HEADER_VARIABLE]
    return group


def attach_raw_file_headers(store_path: str | Path, headers: RawFileHeaders) -> None:
    """Write the authoritative raw headers into the store, under SDIP's namespace.

    Uses stock ``zarr`` rather than MDIO: the attributes must be readable by a consumer
    with MDIO uninstalled (§10.3, gate G4), so they are written the way such a consumer
    would read them.
    """
    import zarr

    raw_header_node(zarr.open_group(str(store_path), mode="r+")).attrs.update(headers.to_attrs())


def _stored_attr(store_path: str | Path, attr: str) -> bytes:
    """Read one SDIP raw-header attribute out of a store, without MDIO.

    **One attribute, not both.** Planes 1 and 2 are separable claims (§4.1), and a
    reader that loads and validates both halves makes them inseparable: a defect in the
    textual header would make the binary reader raise, so Plane 2 would fail on Plane
    1's corruption. **G7 caught exactly that** on its first run - §7 G7's killer is
    *"one that fails the wrong gate"*, and a gate that fires on someone else's
    corruption cannot localise a fault. See ``DECISIONS.md`` D-0028.
    """
    import zarr

    attrs = dict(raw_header_node(zarr.open_group(str(store_path), mode="r")).attrs)
    if attr not in attrs:
        msg = (
            f"store carries no SDIP raw file header attribute {attr}. The plane that "
            "needs it cannot be checked against this store."
        )
        raise UntrustedInputError(msg)
    value = attrs[attr]
    # Zarr attrs are JSON, so values arrive typed as "any JSON value". They were written
    # as base64 strings; anything else means the store was modified outside SDIP.
    if not isinstance(value, str):
        msg = f"store attribute {attr} is not a base64 string; modified outside SDIP"
        raise UntrustedInputError(msg)
    return base64.b64decode(value)


def read_raw_textual_from_store(store_path: str | Path) -> bytes:
    """Read only the authoritative textual header. Plane 1's reader.

    Returns the bytes **unvalidated for length**: a truncated header is Plane 1's
    finding to report with an offset, not an exception for Plane 2 to trip over.
    """
    return _stored_attr(store_path, ATTR_RAW_TEXT)


def read_raw_binary_from_store(store_path: str | Path) -> bytes:
    """Read only the authoritative binary header. Plane 2's reader."""
    return _stored_attr(store_path, ATTR_RAW_BINARY)


def read_raw_file_headers_from_store(store_path: str | Path) -> RawFileHeaders:
    """Read both authoritative raw headers, validated. For callers that need the pair.

    Planes 1 and 2 deliberately do **not** use this - see :func:`_stored_attr`.

    Raises:
        UntrustedInputError: If either header is absent or the wrong size.
    """
    return RawFileHeaders(
        textual=read_raw_textual_from_store(store_path),
        binary=read_raw_binary_from_store(store_path),
    )
