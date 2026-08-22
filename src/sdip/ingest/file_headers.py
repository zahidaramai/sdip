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
from contextlib import contextmanager
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

ATTR_RAW_TEXT: Final[str] = "sdipRawTextHeader"
ATTR_RAW_BINARY: Final[str] = "sdipRawBinaryHeader"
ATTR_RAW_TEXT_SHA: Final[str] = "sdipRawTextHeaderSha256"
ATTR_RAW_BINARY_SHA: Final[str] = "sdipRawBinaryHeaderSha256"
"""SDIP's own namespace. Upstream's parsed view keeps its own keys; these are the
authoritative bytes and are named so nobody has to guess which is which."""


@contextmanager
def file_headers_persisted() -> Iterator[None]:
    """Enable MDIO's file-header persistence in STRICT mode for one call.

    Scoped and restored, so SDIP does not leave the process configured differently from
    how it found it — the same discipline applied to upstream's leaking warning filters
    (``DECISIONS.md`` D-0004).

    ``MDIO__IMPORT__SAVE_SEGY_FILE_HEADER`` is **not** a barred variable (§9.1 bars
    ``MDIO_IGNORE_CHECKS`` and ``MDIO__IMPORT__RAW_HEADERS``). The distinction is the
    direction of travel: a barred variable *weakens* a check or depends on a deprecated
    path, while this one causes **more** of the source to be preserved. Setting it is
    the opposite of the thing §9.1 forbids.
    """
    previous = os.environ.get(SAVE_FILE_HEADER_VAR)
    os.environ[SAVE_FILE_HEADER_VAR] = SAVE_FILE_HEADER_STRICT
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop(SAVE_FILE_HEADER_VAR, None)
        else:
            os.environ[SAVE_FILE_HEADER_VAR] = previous


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


def attach_raw_file_headers(store_path: str | Path, headers: RawFileHeaders) -> None:
    """Write the authoritative raw headers into the store, under SDIP's namespace.

    Uses stock ``zarr`` rather than MDIO: the attributes must be readable by a consumer
    with MDIO uninstalled (§10.3, gate G4), so they are written the way such a consumer
    would read them.
    """
    import zarr

    group = zarr.open_group(str(store_path), mode="r+")
    node = group["segy_file_header"] if "segy_file_header" in group else group
    node.attrs.update(headers.to_attrs())


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

    group = zarr.open_group(str(store_path), mode="r")
    node = group["segy_file_header"] if "segy_file_header" in group else group
    attrs = dict(node.attrs)
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
