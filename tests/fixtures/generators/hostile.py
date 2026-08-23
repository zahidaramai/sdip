"""Deterministic hostile-input corpus. Debt **D8**, specification §11.4, `CLAUDE.md` §3.6.

    A malformed or hostile SEG-Y must produce a clean error - never a crash, an
    unbounded allocation, or a write outside the output path.

That property was **asserted** in the specification and in the module docstring of
:mod:`sdip.errors` long before anything measured it. **SP8** says an assertion is not a
measurement, so this module builds the files that turn it into one.

Every member is written by committed code from a fixed seed, so a stranger reproduces
the whole corpus from the repository alone (§6.6 is binding: no proprietary bytes, no
vendored binaries, nothing fetched). The corruption is applied to a **well-formed**
:func:`~tests.fixtures.generators.poststack3d.make_poststack3d` file wherever the class
allows it, because a corpus of pure noise only ever exercises the outermost check - a
file that is valid right up to the byte under test is the one that reaches the parser.

Nine classes, named on each member as ``klass``:

``short``
    Shorter than the 3600 bytes of mandatory file headers, including empty.
``truncated``
    Valid file headers, then nothing or a partial trace.
``declared_length``
    A header-declared count that the file cannot possibly satisfy. **The
    unbounded-allocation vector**: believing one of these numbers means allocating for
    it.
``count_field``
    Zero, negative, and absurd values in the sample-count fields.
``sample_format``
    A sample-format code outside the standard's enumeration.
``sample_interval``
    Zero, negative and enormous sample intervals.
``grid``
    Trace headers whose index values imply a grid far larger than the trace count.
``garbage``
    Random and constant bytes, with and without a plausible textual header.
``path``
    Content that would become a filesystem path if any output path were ever derived
    from file content, and sources that are not regular files at all.

The corpus asserts nothing by itself. :mod:`tests.negative.test_d8_hostile_corpus` is
what measures, and it carries a **well-formed positive control** through the identical
harness - without one, an ingest that refused every input unconditionally would score a
perfect result (**SP11**).
"""

from __future__ import annotations

import struct
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import numpy as np

from sdip._pins import (
    SEGY_BINARY_HEADER_BYTES,
    SEGY_TEXTUAL_HEADER_BYTES,
    SEGY_TRACE_HEADER_BYTES,
)
from tests.fixtures.generators.poststack3d import make_poststack3d

DEFAULT_SEED: Final[int] = 20260823
"""Fixed seed. Committed, so the corpus is byte-identical on every machine."""

FILE_HEADER_BYTES: Final[int] = SEGY_TEXTUAL_HEADER_BYTES + SEGY_BINARY_HEADER_BYTES
"""3600. Textual + binary, at fixed offsets, in every revision."""

SAMPLE_WORD_BYTES: Final[int] = 4
"""Width of one sample word in the formats this corpus uses."""

INT16_MAX: Final[int] = 32767
"""The widest value a SEG-Y ``int16`` count field can carry. `Absurd` is bounded by the
field, which is exactly why the interesting arithmetic is `declared x actual`."""

# Binary-header field offsets, relative to byte 3200. Written by raw offset on purpose:
# the corpus must not depend on a spec that might itself be the thing under test.
BIN_SAMPLE_INTERVAL: Final[int] = 16
"""Bytes 3217-3218, int16."""
BIN_SAMPLES_PER_TRACE: Final[int] = 20
"""Bytes 3221-3222, int16."""
BIN_SAMPLE_FORMAT: Final[int] = 24
"""Bytes 3225-3226, int16."""
BIN_REVISION: Final[int] = 300
"""Bytes 3501-3502, int16. ``0x0100`` is revision 1."""
BIN_EXT_TEXT_HEADERS: Final[int] = 304
"""Bytes 3505-3506, int16. Each extended header the file claims is another 3200 bytes
the reader is invited to skip past."""

# Trace-header field offsets, relative to the start of a 240-byte trace header.
TRC_SAMPLES: Final[int] = 114
"""Bytes 115-116, int16."""
TRC_SAMPLE_INTERVAL: Final[int] = 116
"""Bytes 117-118, int16."""
TRC_INLINE: Final[int] = 188
"""Bytes 189-192, int32."""
TRC_CROSSLINE: Final[int] = 192
"""Bytes 193-196, int32."""

PATH_BAIT: Final[str] = "../../../../../../tmp/sdip_d8_escape"
"""Planted in a textual header and in trace-header bytes. §11.4: *no path is derived
from file content*. If that is ever false, this string is what makes it visible."""


@dataclass(frozen=True, slots=True)
class HostileFixture:
    """One corpus member: what it is, why it is hostile, and how to write it."""

    name: str
    klass: str
    description: str
    build: Callable[[Path], Path]

    def write(self, root: Path) -> BuiltHostile:
        """Materialise the member under ``root`` and record what was written."""
        path = self.build(root)
        size = path.stat().st_size if path.is_file() else -1
        return BuiltHostile(fixture=self, path=path, size=size)


@dataclass(frozen=True, slots=True)
class BuiltHostile:
    """A written corpus member."""

    fixture: HostileFixture
    path: Path
    size: int
    """Size in bytes, or ``-1`` when the member is deliberately not a regular file."""

    @property
    def name(self) -> str:
        """Member name."""
        return self.fixture.name

    @property
    def klass(self) -> str:
        """Hostility class."""
        return self.fixture.klass


def _well_formed(root: Path, name: str = "well_formed.sgy") -> Path:
    """Write the well-formed 30-trace fixture the corruptions are applied to."""
    return make_poststack3d(root / name).path


def _corrupt(root: Path, name: str, mutate: Callable[[bytearray], None]) -> Path:
    """Write a well-formed file, apply one byte-level mutation, and save it under ``name``.

    The mutation is the only difference from a file that ingests cleanly. That is the
    point: a corpus member which is *also* malformed somewhere else cannot show which
    check fired.
    """
    base = _well_formed(root, f".base_for_{name}")
    payload = bytearray(base.read_bytes())
    mutate(payload)
    target = root / name
    target.write_bytes(bytes(payload))
    base.unlink()
    return target


def _put_i16(payload: bytearray, offset: int, value: int) -> None:
    """Write a big-endian int16 at an absolute file offset, wrapping like the field does."""
    struct.pack_into(">h", payload, offset, value)


def _put_u16(payload: bytearray, offset: int, value: int) -> None:
    """Write a big-endian uint16 at an absolute file offset."""
    struct.pack_into(">H", payload, offset, value)


def _put_i32(payload: bytearray, offset: int, value: int) -> None:
    """Write a big-endian int32 at an absolute file offset."""
    struct.pack_into(">i", payload, offset, value)


def _trace_stride(payload: bytes) -> int:
    """Bytes per trace, read from the file's own binary header."""
    samples = struct.unpack_from(">h", payload, SEGY_TEXTUAL_HEADER_BYTES + BIN_SAMPLES_PER_TRACE)[
        0
    ]
    return SEGY_TRACE_HEADER_BYTES + samples * SAMPLE_WORD_BYTES


def _seeded_bytes(count: int, *, seed: int = DEFAULT_SEED) -> bytes:
    """``count`` pseudorandom bytes from the committed seed.

    ``numpy``'s generator, not :mod:`random`: the seed has to reproduce the same bytes
    on every interpreter build, and this is the generator the rest of the fixture code
    already uses.
    """
    return np.random.default_rng(seed).integers(0, 256, size=count, dtype=np.uint8).tobytes()


def _ebcdic_text(line: str) -> bytes:
    """A plausible 3200-byte EBCDIC textual header carrying ``line`` first.

    Plausible on purpose. A reader that rejects the file on the textual header alone
    never reaches the binary header, so every member whose hostility lives past byte
    3200 needs this to look ordinary.
    """
    rows = [line[:80].ljust(80)]
    filler = "SDIP HOSTILE CORPUS MEMBER - SYNTHETIC - NOT SURVEY DATA"
    rows += [f"C{n:>2} {filler}".ljust(80) for n in range(2, 41)]
    return "".join(rows).encode("cp037")


# --- short ------------------------------------------------------------------------


def _empty_file(root: Path) -> Path:
    target = root / "empty_file.sgy"
    target.write_bytes(b"")
    return target


def _one_byte(root: Path) -> Path:
    target = root / "one_byte.sgy"
    target.write_bytes(b"\x00")
    return target


def _textual_header_only(root: Path) -> Path:
    target = root / "textual_header_only.sgy"
    target.write_bytes(_ebcdic_text("C 1 TEXTUAL HEADER PRESENT - BINARY HEADER ABSENT"))
    return target


def _one_byte_short_of_file_headers(root: Path) -> Path:
    target = root / "one_byte_short_of_file_headers.sgy"
    target.write_bytes(_seeded_bytes(FILE_HEADER_BYTES - 1))
    return target


# --- truncated --------------------------------------------------------------------


def _file_headers_only(root: Path) -> Path:
    def mutate(payload: bytearray) -> None:
        del payload[FILE_HEADER_BYTES:]

    return _corrupt(root, "file_headers_only.sgy", mutate)


def _truncated_mid_trace_header(root: Path) -> Path:
    def mutate(payload: bytearray) -> None:
        del payload[FILE_HEADER_BYTES + SEGY_TRACE_HEADER_BYTES // 2 :]

    return _corrupt(root, "truncated_mid_trace_header.sgy", mutate)


def _truncated_mid_sample_block(root: Path) -> Path:
    def mutate(payload: bytearray) -> None:
        stride = _trace_stride(payload)
        del payload[FILE_HEADER_BYTES + stride + SEGY_TRACE_HEADER_BYTES + 6 :]

    return _corrupt(root, "truncated_mid_sample_block.sgy", mutate)


def _truncated_mid_sample_word(root: Path) -> Path:
    def mutate(payload: bytearray) -> None:
        del payload[len(payload) - 2 :]

    return _corrupt(root, "truncated_mid_sample_word.sgy", mutate)


# --- declared_length --------------------------------------------------------------


def _declared_samples_exceed_file(root: Path) -> Path:
    def mutate(payload: bytearray) -> None:
        _put_i16(payload, SEGY_TEXTUAL_HEADER_BYTES + BIN_SAMPLES_PER_TRACE, INT16_MAX)

    return _corrupt(root, "declared_samples_exceed_file.sgy", mutate)


def _declared_samples_exceed_file_unsigned(root: Path) -> Path:
    def mutate(payload: bytearray) -> None:
        _put_u16(payload, SEGY_TEXTUAL_HEADER_BYTES + BIN_SAMPLES_PER_TRACE, 65535)

    return _corrupt(root, "declared_samples_exceed_file_unsigned.sgy", mutate)


def _declared_trace_samples_exceed_file(root: Path) -> Path:
    def mutate(payload: bytearray) -> None:
        stride = _trace_stride(payload)
        count = (len(payload) - FILE_HEADER_BYTES) // stride
        for trace in range(count):
            _put_i16(payload, FILE_HEADER_BYTES + trace * stride + TRC_SAMPLES, INT16_MAX)

    return _corrupt(root, "declared_trace_samples_exceed_file.sgy", mutate)


def _declared_extended_headers_exceed_file(root: Path) -> Path:
    def mutate(payload: bytearray) -> None:
        _put_i16(payload, SEGY_TEXTUAL_HEADER_BYTES + BIN_EXT_TEXT_HEADERS, INT16_MAX)

    return _corrupt(root, "declared_extended_headers_exceed_file.sgy", mutate)


# --- count_field ------------------------------------------------------------------


def _samples_per_trace_zero(root: Path) -> Path:
    def mutate(payload: bytearray) -> None:
        _put_i16(payload, SEGY_TEXTUAL_HEADER_BYTES + BIN_SAMPLES_PER_TRACE, 0)

    return _corrupt(root, "samples_per_trace_zero.sgy", mutate)


def _samples_per_trace_negative(root: Path) -> Path:
    def mutate(payload: bytearray) -> None:
        _put_i16(payload, SEGY_TEXTUAL_HEADER_BYTES + BIN_SAMPLES_PER_TRACE, -1)

    return _corrupt(root, "samples_per_trace_negative.sgy", mutate)


def _trace_samples_zero(root: Path) -> Path:
    def mutate(payload: bytearray) -> None:
        stride = _trace_stride(payload)
        count = (len(payload) - FILE_HEADER_BYTES) // stride
        for trace in range(count):
            _put_i16(payload, FILE_HEADER_BYTES + trace * stride + TRC_SAMPLES, 0)

    return _corrupt(root, "trace_samples_zero.sgy", mutate)


def _trace_samples_negative(root: Path) -> Path:
    def mutate(payload: bytearray) -> None:
        stride = _trace_stride(payload)
        count = (len(payload) - FILE_HEADER_BYTES) // stride
        for trace in range(count):
            _put_i16(payload, FILE_HEADER_BYTES + trace * stride + TRC_SAMPLES, -1)

    return _corrupt(root, "trace_samples_negative.sgy", mutate)


# --- sample_format ----------------------------------------------------------------


def _sample_format_undefined(root: Path) -> Path:
    def mutate(payload: bytearray) -> None:
        _put_i16(payload, SEGY_TEXTUAL_HEADER_BYTES + BIN_SAMPLE_FORMAT, 99)

    return _corrupt(root, "sample_format_undefined.sgy", mutate)


def _sample_format_zero(root: Path) -> Path:
    def mutate(payload: bytearray) -> None:
        _put_i16(payload, SEGY_TEXTUAL_HEADER_BYTES + BIN_SAMPLE_FORMAT, 0)

    return _corrupt(root, "sample_format_zero.sgy", mutate)


def _sample_format_negative(root: Path) -> Path:
    def mutate(payload: bytearray) -> None:
        _put_i16(payload, SEGY_TEXTUAL_HEADER_BYTES + BIN_SAMPLE_FORMAT, -32768)

    return _corrupt(root, "sample_format_negative.sgy", mutate)


def _revision_undefined(root: Path) -> Path:
    def mutate(payload: bytearray) -> None:
        _put_i16(payload, SEGY_TEXTUAL_HEADER_BYTES + BIN_REVISION, INT16_MAX)

    return _corrupt(root, "revision_undefined.sgy", mutate)


# --- sample_interval --------------------------------------------------------------


def _sample_interval_zero(root: Path) -> Path:
    def mutate(payload: bytearray) -> None:
        _put_i16(payload, SEGY_TEXTUAL_HEADER_BYTES + BIN_SAMPLE_INTERVAL, 0)

    return _corrupt(root, "sample_interval_zero.sgy", mutate)


def _sample_interval_negative(root: Path) -> Path:
    def mutate(payload: bytearray) -> None:
        _put_i16(payload, SEGY_TEXTUAL_HEADER_BYTES + BIN_SAMPLE_INTERVAL, -1)

    return _corrupt(root, "sample_interval_negative.sgy", mutate)


def _sample_interval_enormous(root: Path) -> Path:
    def mutate(payload: bytearray) -> None:
        offset = SEGY_TEXTUAL_HEADER_BYTES + BIN_SAMPLE_INTERVAL
        _put_i16(payload, offset, INT16_MAX)
        stride = _trace_stride(payload)
        count = (len(payload) - FILE_HEADER_BYTES) // stride
        for trace in range(count):
            _put_i16(payload, FILE_HEADER_BYTES + trace * stride + TRC_SAMPLE_INTERVAL, INT16_MAX)

    return _corrupt(root, "sample_interval_enormous.sgy", mutate)


# --- grid -------------------------------------------------------------------------


def _grid_sparse_enormous(root: Path) -> Path:
    """Thirty real traces whose index values span a 2**24 x 2**24 lattice.

    The trace *data* is entirely well formed. The hostility is arithmetic: a converter
    that sizes a dense grid from the index range allocates roughly 2**48 cells for
    30 traces of content.
    """

    def mutate(payload: bytearray) -> None:
        stride = _trace_stride(payload)
        count = (len(payload) - FILE_HEADER_BYTES) // stride
        for trace in range(count):
            base = FILE_HEADER_BYTES + trace * stride
            _put_i32(payload, base + TRC_INLINE, trace * (1 << 24))
            _put_i32(payload, base + TRC_CROSSLINE, trace * (1 << 24))

    return _corrupt(root, "grid_sparse_enormous.sgy", mutate)


def _grid_index_negative(root: Path) -> Path:
    def mutate(payload: bytearray) -> None:
        stride = _trace_stride(payload)
        count = (len(payload) - FILE_HEADER_BYTES) // stride
        for trace in range(count):
            base = FILE_HEADER_BYTES + trace * stride
            _put_i32(payload, base + TRC_INLINE, -(1 << 30) - trace)
            _put_i32(payload, base + TRC_CROSSLINE, -(1 << 30) - trace)

    return _corrupt(root, "grid_index_negative.sgy", mutate)


def _grid_all_identical(root: Path) -> Path:
    """Every trace claims the same cell. Thirty traces, one grid position."""

    def mutate(payload: bytearray) -> None:
        stride = _trace_stride(payload)
        count = (len(payload) - FILE_HEADER_BYTES) // stride
        for trace in range(count):
            base = FILE_HEADER_BYTES + trace * stride
            _put_i32(payload, base + TRC_INLINE, 1)
            _put_i32(payload, base + TRC_CROSSLINE, 1)

    return _corrupt(root, "grid_all_identical.sgy", mutate)


# --- garbage ----------------------------------------------------------------------


def _random_bytes_throughout(root: Path) -> Path:
    target = root / "random_bytes_throughout.sgy"
    target.write_bytes(_seeded_bytes(FILE_HEADER_BYTES + 4096, seed=DEFAULT_SEED + 1))
    return target


def _plausible_text_random_body(root: Path) -> Path:
    target = root / "plausible_text_random_body.sgy"
    text = _ebcdic_text("C 1 PLAUSIBLE TEXTUAL HEADER - EVERYTHING AFTER IT IS NOISE")
    target.write_bytes(text + _seeded_bytes(SEGY_BINARY_HEADER_BYTES + 4096, seed=DEFAULT_SEED + 2))
    return target


def _all_zero_bytes(root: Path) -> Path:
    target = root / "all_zero_bytes.sgy"
    target.write_bytes(bytes(FILE_HEADER_BYTES + 4096))
    return target


def _all_ff_bytes(root: Path) -> Path:
    target = root / "all_ff_bytes.sgy"
    target.write_bytes(b"\xff" * (FILE_HEADER_BYTES + 4096))
    return target


# --- path -------------------------------------------------------------------------


def _path_bait_in_headers(root: Path) -> Path:
    """A structurally valid file whose text and header tail are filesystem paths.

    Nothing in §11.4 permits a path to come from content, so the expected outcome is
    that this file is treated exactly like any other well-formed one. The member exists
    so that *"no output path is derived from file content"* is a check with a witness
    rather than a sentence in a specification.
    """
    bait = PATH_BAIT.encode("ascii")

    def mutate(payload: bytearray) -> None:
        payload[:SEGY_TEXTUAL_HEADER_BYTES] = _ebcdic_text(f"C 1 {PATH_BAIT}")
        stride = _trace_stride(payload)
        count = (len(payload) - FILE_HEADER_BYTES) // stride
        for trace in range(count):
            base = FILE_HEADER_BYTES + trace * stride + 200
            payload[base : base + len(bait)] = bait

    return _corrupt(root, "path_bait_in_headers.sgy", mutate)


def _source_is_a_directory(root: Path) -> Path:
    target = root / "source_is_a_directory.sgy"
    target.mkdir(parents=True, exist_ok=True)
    return target


def _source_is_a_dangling_symlink(root: Path) -> Path:
    target = root / "source_is_a_dangling_symlink.sgy"
    if not target.is_symlink():
        target.symlink_to(root / "no_such_file_exists.sgy")
    return target


CORPUS: Final[tuple[HostileFixture, ...]] = (
    HostileFixture("empty_file", "short", "Zero bytes. The degenerate case.", _empty_file),
    HostileFixture(
        "one_byte", "short", "A single byte, 3599 short of the file headers.", _one_byte
    ),
    HostileFixture(
        "textual_header_only",
        "short",
        "3200 bytes of valid EBCDIC text and no binary header.",
        _textual_header_only,
    ),
    HostileFixture(
        "one_byte_short_of_file_headers",
        "short",
        "3599 bytes: the off-by-one against the 3600-byte minimum.",
        _one_byte_short_of_file_headers,
    ),
    HostileFixture(
        "file_headers_only",
        "truncated",
        "Valid 3600-byte header pair, then nothing.",
        _file_headers_only,
    ),
    HostileFixture(
        "truncated_mid_trace_header",
        "truncated",
        "Cut 120 bytes into the first trace header.",
        _truncated_mid_trace_header,
    ),
    HostileFixture(
        "truncated_mid_sample_block",
        "truncated",
        "One whole trace, then a header and six bytes of samples.",
        _truncated_mid_sample_block,
    ),
    HostileFixture(
        "truncated_mid_sample_word",
        "truncated",
        "Cut two bytes into the final 4-byte sample word.",
        _truncated_mid_sample_word,
    ),
    HostileFixture(
        "declared_samples_exceed_file",
        "declared_length",
        "Binary header declares 32767 samples per trace on a 14,640-byte file: "
        "131,308 declared bytes per trace against 11,040 bytes of trace data.",
        _declared_samples_exceed_file,
    ),
    HostileFixture(
        "declared_samples_exceed_file_unsigned",
        "declared_length",
        "Same field set to 0xFFFF - reads as 65535 unsigned, -1 signed. Whichever "
        "way the parser reads it, the file cannot satisfy it.",
        _declared_samples_exceed_file_unsigned,
    ),
    HostileFixture(
        "declared_trace_samples_exceed_file",
        "declared_length",
        "Every trace header claims 32767 samples while the binary header says 32.",
        _declared_trace_samples_exceed_file,
    ),
    HostileFixture(
        "declared_extended_headers_exceed_file",
        "declared_length",
        "32767 extended textual headers declared: 104,854,400 bytes of headers "
        "claimed by a 14,640-byte file.",
        _declared_extended_headers_exceed_file,
    ),
    HostileFixture(
        "samples_per_trace_zero",
        "count_field",
        "Binary header declares zero samples per trace.",
        _samples_per_trace_zero,
    ),
    HostileFixture(
        "samples_per_trace_negative",
        "count_field",
        "Binary header declares -1 samples per trace.",
        _samples_per_trace_negative,
    ),
    HostileFixture(
        "trace_samples_zero",
        "count_field",
        "Every trace header declares zero samples.",
        _trace_samples_zero,
    ),
    HostileFixture(
        "trace_samples_negative",
        "count_field",
        "Every trace header declares -1 samples.",
        _trace_samples_negative,
    ),
    HostileFixture(
        "sample_format_undefined",
        "sample_format",
        "Sample-format code 99, outside the standard's enumeration.",
        _sample_format_undefined,
    ),
    HostileFixture(
        "sample_format_zero",
        "sample_format",
        "Sample-format code 0, which the standard does not define.",
        _sample_format_zero,
    ),
    HostileFixture(
        "sample_format_negative",
        "sample_format",
        "Sample-format code -32768, the int16 floor.",
        _sample_format_negative,
    ),
    HostileFixture(
        "revision_undefined",
        "sample_format",
        "Revision field 0x7FFF - major 127, minor 255. No such revision exists.",
        _revision_undefined,
    ),
    HostileFixture(
        "sample_interval_zero",
        "sample_interval",
        "Zero-microsecond sample interval: a division waiting to happen.",
        _sample_interval_zero,
    ),
    HostileFixture(
        "sample_interval_negative",
        "sample_interval",
        "Negative sample interval, which would run the time axis backwards.",
        _sample_interval_negative,
    ),
    HostileFixture(
        "sample_interval_enormous",
        "sample_interval",
        "32767-microsecond interval in both the binary and every trace header.",
        _sample_interval_enormous,
    ),
    HostileFixture(
        "grid_sparse_enormous",
        "grid",
        "Thirty well-formed traces whose inline and crossline values span a "
        "2**24 x 2**24 lattice: a dense grid over that range is 2**48 cells.",
        _grid_sparse_enormous,
    ),
    HostileFixture(
        "grid_index_negative",
        "grid",
        "Inline and crossline values below -2**30.",
        _grid_index_negative,
    ),
    HostileFixture(
        "grid_all_identical",
        "grid",
        "Thirty traces all claiming grid cell (1, 1). A 1x1 grid for 30 traces.",
        _grid_all_identical,
    ),
    HostileFixture(
        "random_bytes_throughout",
        "garbage",
        "7,696 seeded pseudorandom bytes, no valid structure anywhere.",
        _random_bytes_throughout,
    ),
    HostileFixture(
        "plausible_text_random_body",
        "garbage",
        "Valid EBCDIC textual header, then noise from byte 3200 on.",
        _plausible_text_random_body,
    ),
    HostileFixture(
        "all_zero_bytes",
        "garbage",
        "7,696 zero bytes: every count field reads as zero at once.",
        _all_zero_bytes,
    ),
    HostileFixture(
        "all_ff_bytes",
        "garbage",
        "7,696 0xFF bytes: every count field reads as -1 at once.",
        _all_ff_bytes,
    ),
    HostileFixture(
        "path_bait_in_headers",
        "path",
        "Structurally valid; textual header and header tails carry a traversal path.",
        _path_bait_in_headers,
    ),
    HostileFixture(
        "source_is_a_directory",
        "path",
        "The source path is a directory, not a file.",
        _source_is_a_directory,
    ),
    HostileFixture(
        "source_is_a_dangling_symlink",
        "path",
        "The source path is a symlink to a file that does not exist.",
        _source_is_a_dangling_symlink,
    ),
)

CLASSES: Final[tuple[str, ...]] = (
    "short",
    "truncated",
    "declared_length",
    "count_field",
    "sample_format",
    "sample_interval",
    "grid",
    "garbage",
    "path",
)
"""Every hostility class the corpus must cover. A class with no member is a class
nobody measured."""


def build_corpus(root: str | Path) -> list[BuiltHostile]:
    """Write every corpus member under ``root``.

    Args:
        root: Directory to write into. Created if absent.

    Returns:
        One :class:`BuiltHostile` per member, in :data:`CORPUS` order.
    """
    target = Path(root)
    target.mkdir(parents=True, exist_ok=True)
    return [fixture.write(target) for fixture in CORPUS]


def build_positive_control(root: str | Path) -> Path:
    """Write the well-formed file that runs through the identical harness.

    **SP11.** A corpus in which every member fails is passed perfectly by an ingest that
    refuses everything. This is the member that must *succeed*, and it is what makes the
    other thirty-three mean something.
    """
    target = Path(root)
    target.mkdir(parents=True, exist_ok=True)
    return _well_formed(target, "positive_control.sgy")


if __name__ == "__main__":  # pragma: no cover - see spec 11.1
    import sys

    sys.exit("tests.fixtures.generators.hostile is a library; the corpus is built by tests.")
