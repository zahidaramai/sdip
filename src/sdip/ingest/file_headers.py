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


def read_raw_file_headers_from_store(store_path: str | Path) -> RawFileHeaders:
    """Read SDIP's authoritative raw headers back out of a store, without MDIO.

    Raises:
        UntrustedInputError: If the store carries no SDIP raw headers.
    """
    import zarr

    group = zarr.open_group(str(store_path), mode="r")
    node = group["segy_file_header"] if "segy_file_header" in group else group
    attrs = dict(node.attrs)
    if ATTR_RAW_TEXT not in attrs or ATTR_RAW_BINARY not in attrs:
        msg = (
            f"store carries no SDIP raw file headers ({ATTR_RAW_TEXT}, "
            f"{ATTR_RAW_BINARY}). Planes 1 and 2 cannot be checked against it."
        )
        raise UntrustedInputError(msg)
    # Zarr attrs are JSON, so the values arrive typed as "any JSON value". They were
    # written as base64 strings; anything else means the store was tampered with.
    text_b64, binary_b64 = attrs[ATTR_RAW_TEXT], attrs[ATTR_RAW_BINARY]
    if not isinstance(text_b64, str) or not isinstance(binary_b64, str):
        msg = (
            f"store attributes {ATTR_RAW_TEXT}/{ATTR_RAW_BINARY} are not base64 "
            "strings; the store has been modified outside SDIP"
        )
        raise UntrustedInputError(msg)
    return RawFileHeaders(
        textual=base64.b64decode(text_b64),
        binary=base64.b64decode(binary_b64),
    )
