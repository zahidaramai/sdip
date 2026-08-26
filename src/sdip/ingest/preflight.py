"""Structural validation of a SEG-Y **before anything is allocated**. Spec §11.4.

    Header-declared lengths and counts are validated against actual file size before
    allocation. — §11.4

Debt **D8** built the corpus that measured what SDIP actually did with a hostile file,
and the answer was: **it handed it straight to upstream.** Of 33 malformed files, 18 came
back with an exception SDIP does not define — ``ValueError``, ``ZeroDivisionError``, a
``pydantic`` ``ValidationError``, ``SegyFileSpecMismatchError`` — and every one of them
reached the console as a traceback. The operating contract §3.6 says a malformed or hostile SEG-Y
must produce a clean error; that was an assertion with nothing behind it (``DECISIONS.md``
D-0057).

**No allocation is proportional to anything read here.** Exactly 400 bytes are read, at a
fixed offset, and the only thing done with the numbers in them is integer arithmetic
against ``st_size``. That ordering is the whole point: a declared count is
attacker-controlled until the file on disk agrees with it, and by the time upstream has
sized an array from it the check is too late to be a check.

**Big-endian, deliberately.** SEG-Y is a big-endian format and SDIP reads it as one. A
little-endian file is refused rather than guessed at — but the refusal *says* the fields
are coherent in the other byte order, because "sample format code 256" on its own sends
the reader looking for a corruption that is not there.

**What this module does not do.** It says nothing about geometry. Whether a file's index
values imply a workable grid is a question only a full trace-header pass can answer, and
probe **P5** measured MDIO answering it — ``GridTraceCountError`` on a duplicated cell,
``GridTraceSparsityError`` past a sparsity ratio of 12. Those refusals are recorded
behaviour SDIP relies on and does not re-type (``DECISIONS.md`` D-0057, ``OPEN_DEBTS`` D8).
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from sdip._pins import (
    SEGY_BINARY_HEADER_BYTES,
    SEGY_TEXTUAL_HEADER_BYTES,
    SEGY_TRACE_HEADER_BYTES,
)
from sdip.errors import UntrustedInputError

FILE_HEADER_BYTES: Final[int] = SEGY_TEXTUAL_HEADER_BYTES + SEGY_BINARY_HEADER_BYTES
"""3600. Textual then binary, at fixed offsets, in every revision."""

EXTENDED_TEXT_HEADER_BYTES: Final[int] = SEGY_TEXTUAL_HEADER_BYTES
"""Each extended textual header the binary header claims is another 3200 bytes."""

BIN_SAMPLE_INTERVAL: Final[int] = 16
"""Bytes 3217-3218, int16, microseconds."""
BIN_SAMPLES_PER_TRACE: Final[int] = 20
"""Bytes 3221-3222, int16."""
BIN_SAMPLE_FORMAT: Final[int] = 24
"""Bytes 3225-3226, int16, a code from the standard's enumeration."""
BIN_EXTENDED_TEXT_HEADERS: Final[int] = 304
"""Bytes 3505-3506, int16. ``-1`` means *variable, terminated by a stanza*."""

EXTENDED_HEADERS_VARIABLE: Final[int] = -1
"""The one negative value bytes 3505-3506 are allowed to hold (rev 2)."""


def _supported_format_codes() -> dict[int, int]:
    """Sample-format code to bytes per sample, taken from the pinned ``segy`` enum.

    Read out of upstream rather than written down here on purpose. A hardcoded list is a
    second source of truth that drifts silently from the decoder actually in use; this
    one cannot disagree with what ``segy`` 0.6.0 can decode, because it *is* what
    ``segy`` 0.6.0 can decode. §3.3: public API only.
    """
    from segy.schema import ScalarType
    from segy.standards.codes import DataSampleFormatCode

    return {
        int(code.value): int(ScalarType[code.name].dtype.itemsize) for code in DataSampleFormatCode
    }


@dataclass(frozen=True, slots=True)
class SourceLayout:
    """What the file's own headers say its trace data looks like, reconciled with its size.

    Every field here has survived the check that the file can actually contain it.
    """

    size: int
    samples_per_trace: int
    sample_interval_us: int
    sample_format_code: int
    bytes_per_sample: int
    extended_text_headers: int
    data_offset: int
    bytes_per_trace: int
    trace_count: int
    """``-1`` when the file declares a variable number of extended textual headers, which
    puts the first trace at an offset no fixed-offset arithmetic can find. See
    :func:`validate_segy_structure`."""

    @property
    def trace_count_known(self) -> bool:
        """False when the data offset is not computable from the binary header alone."""
        return self.trace_count >= 0

    def to_json(self) -> dict[str, Any]:
        """Certificate-shaped mapping of the reconciled layout."""
        return {
            "size": self.size,
            "samples_per_trace": self.samples_per_trace,
            "sample_interval_us": self.sample_interval_us,
            "sample_format_code": self.sample_format_code,
            "bytes_per_sample": self.bytes_per_sample,
            "extended_text_headers": self.extended_text_headers,
            "data_offset": self.data_offset,
            "bytes_per_trace": self.bytes_per_trace,
            "trace_count": self.trace_count,
            "trace_count_known": self.trace_count_known,
        }


def read_binary_header(path: str | Path) -> bytes:
    """Read the 400-byte binary header and nothing else.

    Raises:
        UntrustedInputError: If the file is too short to contain one.
    """
    with Path(path).open("rb") as handle:
        handle.seek(SEGY_TEXTUAL_HEADER_BYTES)
        blob = handle.read(SEGY_BINARY_HEADER_BYTES)
    if len(blob) != SEGY_BINARY_HEADER_BYTES:
        msg = (
            f"source carries {len(blob)} of the {SEGY_BINARY_HEADER_BYTES} binary-header "
            f"bytes that must follow the {SEGY_TEXTUAL_HEADER_BYTES}-byte textual header"
        )
        raise UntrustedInputError(msg)
    return blob


def _big(binary: bytes, offset: int) -> int:
    """One big-endian int16 field out of the binary header."""
    return int(struct.unpack_from(">h", binary, offset)[0])


def _little(binary: bytes, offset: int) -> int:
    """The same field read the other way round. Used only to explain a refusal."""
    return int(struct.unpack_from("<h", binary, offset)[0])


def _byte_order_hint(binary: bytes) -> str:
    """A note appended to a refusal when the file looks coherent little-endian.

    A little-endian SEG-Y is a real file that real acquisition systems write, not a
    corruption. Saying so turns a dead end into an actionable message.
    """
    codes = _supported_format_codes()
    swapped_format = _little(binary, BIN_SAMPLE_FORMAT)
    swapped_samples = _little(binary, BIN_SAMPLES_PER_TRACE)
    if swapped_format in codes and swapped_samples > 0:
        return (
            " Read little-endian the same bytes give sample-format code "
            f"{swapped_format} and {swapped_samples} samples per trace, so this is most "
            "likely a little-endian SEG-Y. SDIP reads SEG-Y as big-endian and does not "
            "guess byte order."
        )
    return ""


def validate_segy_structure(path: str | Path, size: int) -> SourceLayout:
    """Reconcile a SEG-Y's declared counts against its actual size. Spec §11.4.

    Runs before any allocation, any spec build and any upstream call. Order matters:
    each check is a precondition of the arithmetic in the next one, so a file that fails
    an early check never reaches a later multiplication.

    Args:
        path: Source SEG-Y, already known to be a regular file of at least 3600 bytes.
        size: Its size in bytes, from ``stat``, not from the file's own headers.

    Returns:
        The reconciled layout.

    Raises:
        UntrustedInputError: On any declared count the file cannot satisfy.
    """
    binary = read_binary_header(path)
    codes = _supported_format_codes()

    samples = _big(binary, BIN_SAMPLES_PER_TRACE)
    if samples <= 0:
        msg = (
            f"binary header (bytes 3221-3222) declares {samples} samples per trace; a "
            f"trace has at least one sample.{_byte_order_hint(binary)}"
        )
        raise UntrustedInputError(msg)

    interval = _big(binary, BIN_SAMPLE_INTERVAL)
    if interval <= 0:
        msg = (
            f"binary header (bytes 3217-3218) declares a sample interval of {interval} "
            f"microseconds; the interval is a positive duration.{_byte_order_hint(binary)}"
        )
        raise UntrustedInputError(msg)

    code = _big(binary, BIN_SAMPLE_FORMAT)
    if code not in codes:
        supported = ", ".join(str(value) for value in sorted(codes))
        msg = (
            f"binary header (bytes 3225-3226) declares sample-format code {code}, which "
            f"the pinned segy 0.6.0 does not define. Supported codes: "
            f"{supported}.{_byte_order_hint(binary)}"
        )
        raise UntrustedInputError(msg)
    bytes_per_sample = codes[code]

    extended = _big(binary, BIN_EXTENDED_TEXT_HEADERS)
    if extended < EXTENDED_HEADERS_VARIABLE:
        msg = (
            f"binary header (bytes 3505-3506) declares {extended} extended textual "
            "headers; the only negative value the standard defines is -1 (variable, "
            "terminated by a stanza)"
        )
        raise UntrustedInputError(msg)

    bytes_per_trace = SEGY_TRACE_HEADER_BYTES + samples * bytes_per_sample

    if extended == EXTENDED_HEADERS_VARIABLE:
        # The first trace sits after an unknown number of 3200-byte stanzas, so no
        # fixed-offset arithmetic can locate it and the divisibility check below cannot
        # run. Refusing here would refuse a legal rev 2 file; pretending the offset is
        # 3600 would compute a trace count from the wrong place. Both are worse than
        # declaring the layout unknown and letting the parser that can read stanzas
        # decide. Recorded as the residual in OPEN_DEBTS D8.
        return SourceLayout(
            size=size,
            samples_per_trace=samples,
            sample_interval_us=interval,
            sample_format_code=code,
            bytes_per_sample=bytes_per_sample,
            extended_text_headers=extended,
            data_offset=-1,
            bytes_per_trace=bytes_per_trace,
            trace_count=-1,
        )

    declared_headers = FILE_HEADER_BYTES + extended * EXTENDED_TEXT_HEADER_BYTES
    if declared_headers >= size:
        msg = (
            f"binary header (bytes 3505-3506) declares {extended} extended textual "
            f"headers, so the file headers alone would occupy {declared_headers} bytes "
            f"of a {size}-byte file, leaving no trace data"
        )
        raise UntrustedInputError(msg)

    body = size - declared_headers
    if body % bytes_per_trace:
        msg = (
            f"source carries {body} bytes of trace data, which is not a whole number of "
            f"{bytes_per_trace}-byte traces ({SEGY_TRACE_HEADER_BYTES} header + "
            f"{samples} samples x {bytes_per_sample} bytes, format code {code}). The "
            "declared trace length and the file disagree, so no byte offset in this "
            f"file can be trusted.{_byte_order_hint(binary)}"
        )
        raise UntrustedInputError(msg)

    return SourceLayout(
        size=size,
        samples_per_trace=samples,
        sample_interval_us=interval,
        sample_format_code=code,
        bytes_per_sample=bytes_per_sample,
        extended_text_headers=extended,
        data_offset=declared_headers,
        bytes_per_trace=bytes_per_trace,
        trace_count=body // bytes_per_trace,
    )
