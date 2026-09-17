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

**Big-endian unless declared.** SEG-Y is big-endian by the revision standards SDIP's
base specs follow, and nothing is guessed: an undeclared little-endian file is refused,
and the refusal *says* the fields are coherent in the other byte order and names the
declaration that admits it, because "sample format code 256" on its own sends the reader
looking for a corruption that is not there.

**The declaration is read here, not only in the spec (D28, DECISIONS.md D-0087).** A
survey override has been able to declare ``endianness`` since 07:44 on 2026-08-23. This
module arrived two hours later reading every field big-endian without being handed that
declaration, and from then until D-0087 a little-endian file was refused *with* its
override. ``infer`` is delegated to ``segy``'s own public inference — the function ingest
itself will run — so this check and the decoder cannot reach different conclusions.

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

BYTE_ORDER_CODES: Final[dict[str, str]] = {"big": ">", "little": "<"}
"""Resolved byte orders, as ``struct`` prefixes."""

DECLARABLE_BYTE_ORDERS: Final[tuple[str, ...]] = ("big", "little", "infer")

TRACE_COORDINATE_SCALAR: Final[int] = 70
"""Trace-header bytes 71-72, int16: the scalar SEG-Y applies to bytes 73-88 and 181-188."""

MDIO_VALID_COORDINATE_SCALARS: Final[frozenset[int]] = frozenset({1, 10, 100, 1000, 10000})
"""Magnitudes the pinned multidimio 1.2.1 accepts (``mdio/segy/scalar.py``), which are the
values SEG-Y allows. Zero is accepted only from revision 2, where the standard defines it as 1."""
"""What a survey override may declare. Mirrors ``sdip.spec.overrides.ENDIANNESS_VALUES``."""


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

    endianness: str = "big"
    """The byte order every field above was read in: declared, or resolved from ``infer``."""

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
            "endianness": self.endianness,
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


def _int16(binary: bytes, offset: int, endianness: str) -> int:
    """One int16 field out of the binary header, in a resolved byte order."""
    return int(struct.unpack_from(f"{BYTE_ORDER_CODES[endianness]}h", binary, offset)[0])


def _other(endianness: str) -> str:
    return "little" if endianness == "big" else "big"


def resolve_byte_order(binary: bytes, endianness: str | None) -> str:
    """The byte order to read ``binary`` in: ``big`` or ``little``.

    ``None`` inherits the revision standard's big-endian. ``infer`` asks ``segy``, which
    checks the rev 2 byte-order constant at bytes 3297-3300 before any heuristic; its
    answer is relative to this machine's native order, so it is converted here.

    Raises:
        UntrustedInputError: If ``endianness`` is not declarable, or if ``segy`` cannot
            infer an order for this file.
    """
    if endianness is None:
        return "big"
    if endianness in BYTE_ORDER_CODES:
        return endianness
    if endianness != "infer":
        accepted = ", ".join(DECLARABLE_BYTE_ORDERS)
        msg = f"declared endianness {endianness!r} is not one of: {accepted}"
        raise UntrustedInputError(msg)

    import sys

    from segy.config import SegyFileSettings
    from segy.exceptions import SegyError
    from segy.inference import EndiannessAction, infer_endianness

    try:
        action = infer_endianness(binary, SegyFileSettings())
    # `EndiannessInferenceError` is a `SegyError`, not a `ValueError`; `NotImplementedError`
    # is what segy raises for a pairwise-swapped file. Catching the wrong base here is a
    # traceback at the CLI - the §3.6 defect - so the test pins the real hierarchy.
    except (SegyError, NotImplementedError) as exc:
        msg = f"endianness was declared 'infer' and segy could not infer it: {exc}"
        raise UntrustedInputError(msg) from exc
    native = sys.byteorder
    return native if action is EndiannessAction.KEEP else _other(native)


def _byte_order_hint(binary: bytes, endianness: str) -> str:
    """A note appended to a refusal when the file is coherent in the OTHER byte order.

    A little-endian SEG-Y is a real file that real acquisition systems write, not a
    corruption, and a wrong declaration is an operator error rather than a damaged file.
    Saying which, and naming the declaration that would admit the file, turns a dead end
    into the operator's next action.
    """
    other = _other(endianness)
    codes = _supported_format_codes()
    swapped_format = _int16(binary, BIN_SAMPLE_FORMAT, other)
    swapped_samples = _int16(binary, BIN_SAMPLES_PER_TRACE, other)
    if swapped_format in codes and swapped_samples > 0:
        return (
            f" Read {other}-endian the same bytes give sample-format code "
            f"{swapped_format} and {swapped_samples} samples per trace, so this is most "
            f"likely a {other}-endian SEG-Y read as {endianness}-endian. SDIP does not guess "
            f'byte order: declare endianness = "{other}" (or "infer") in a survey override '
            "(spec 6.4) and pass it with --override."
        )
    return ""


def validate_segy_structure(
    path: str | Path,
    size: int,
    *,
    endianness: str | None = None,
    revision: float | int = 1,
) -> SourceLayout:
    """Reconcile a SEG-Y's declared counts against its actual size. Spec §11.4.

    Runs before any allocation, any spec build and any upstream call. Order matters:
    each check is a precondition of the arithmetic in the next one, so a file that fails
    an early check never reaches a later multiplication.

    Args:
        path: Source SEG-Y, already known to be a regular file of at least 3600 bytes.
        size: Its size in bytes, from ``stat``, not from the file's own headers.
        endianness: The declared byte order (``big``, ``little``, ``infer``), or
            ``None`` for the revision standard's big-endian.
        revision: The declared SEG-Y revision. It decides whether a zero coordinate
            scalar is acceptable, exactly as it does upstream.

    Returns:
        The reconciled layout.

    Raises:
        UntrustedInputError: On any declared count the file cannot satisfy, or on a byte
            order that cannot be declared or inferred.
    """
    if endianness is not None and endianness not in DECLARABLE_BYTE_ORDERS:
        resolve_byte_order(b"", endianness)  # raises, naming the accepted values
    binary = read_binary_header(path)
    order = resolve_byte_order(binary, endianness)
    codes = _supported_format_codes()

    samples = _int16(binary, BIN_SAMPLES_PER_TRACE, order)
    if samples <= 0:
        msg = (
            f"binary header (bytes 3221-3222) declares {samples} samples per trace; a "
            f"trace has at least one sample.{_byte_order_hint(binary, order)}"
        )
        raise UntrustedInputError(msg)

    interval = _int16(binary, BIN_SAMPLE_INTERVAL, order)
    if interval <= 0:
        msg = (
            f"binary header (bytes 3217-3218) declares a sample interval of {interval} "
            f"microseconds; the interval is a positive duration.{_byte_order_hint(binary, order)}"
        )
        raise UntrustedInputError(msg)

    code = _int16(binary, BIN_SAMPLE_FORMAT, order)
    if code not in codes:
        supported = ", ".join(str(value) for value in sorted(codes))
        msg = (
            f"binary header (bytes 3225-3226) declares sample-format code {code}, which "
            f"the pinned segy 0.6.0 does not define. Supported codes: "
            f"{supported}.{_byte_order_hint(binary, order)} A survey override cannot yet "
            "declare the sample format for such a file: segy and MDIO expose that publicly, "
            "and SDIP will build it when a file that needs it arrives (OPEN_DEBTS D22)."
        )
        raise UntrustedInputError(msg)
    bytes_per_sample = codes[code]

    extended = _int16(binary, BIN_EXTENDED_TEXT_HEADERS, order)
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
            endianness=order,
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
            f"file can be trusted.{_byte_order_hint(binary, order)}"
        )
        raise UntrustedInputError(msg)

    _refuse_a_coordinate_scalar_mdio_refuses(path, declared_headers, order, revision)

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
        endianness=order,
    )


def _refuse_a_coordinate_scalar_mdio_refuses(
    path: str | Path, data_offset: int, endianness: str, revision: float | int
) -> None:
    """OPEN_DEBTS D27: refuse, with the reason, a first-trace scalar MDIO would crash on.

    The refusal is the permanent handling (DECISIONS.md D-0089), not a stopgap awaiting upstream.

    Mirrors ``mdio/segy/scalar.py`` exactly - trace 0 only, zero accepted from revision 2,
    any other magnitude outside :data:`MDIO_VALID_COORDINATE_SCALARS` refused - so this
    refuses nothing MDIO accepts. Two bytes at a fixed offset; nothing is allocated.

    Raises:
        UntrustedInputError: Naming the value, the standard's position, what the industry
            does, and why SDIP cannot follow it at the pinned writer.
    """
    with Path(path).open("rb") as handle:
        handle.seek(data_offset + TRACE_COORDINATE_SCALAR)
        blob = handle.read(2)
    scalar = int(struct.unpack(f"{BYTE_ORDER_CODES[endianness]}h", blob)[0])

    if scalar == 0:
        if float(revision) >= 2:
            return
        msg = (
            "the first trace's coordinate scalar (trace-header bytes 71-72) is 0. SEG-Y "
            "rev 2.0 and 2.1 define a zero scalar as 1, and segyio, Seismic Unix, OpenVDS "
            "and OpendTect read it that way at any revision; the pinned multidimio 1.2.1 "
            f"accepts it only from revision 2 and refuses it for a revision {revision} file. "
            "SDIP writes through multidimio's public API and does not route around it "
            "(spec 3.3), so this file cannot be ingested as declared. "
            "Debt D27, closed as a refusal."
        )
        raise UntrustedInputError(msg)
    if abs(scalar) not in MDIO_VALID_COORDINATE_SCALARS:
        msg = (
            f"the first trace's coordinate scalar (trace-header bytes 71-72) is {scalar}. "
            "SEG-Y allows 1, +/-10, +/-100, +/-1000 or +/-10000, and the pinned "
            "multidimio 1.2.1 refuses any other value."
        )
        raise UntrustedInputError(msg)
