"""The parallel ``uint8`` trace-header plane. Probe **P4**'s pre-approved mitigation.

**Probe P4 ran twice, against the same store, and the two readers disagreed.**

======================== ======================= ======================================
Reader                   ``struct`` (``headers``) ``fixed_length_utf32``
======================== ======================= ======================================
TensorStore 0.1.85 (C++) **accepts** — 97/97      refuses
zarr-java 0.2.0 (JVM)    **refuses**              refuses
``zarr-python`` 3.3.0    accepts, with a warning  accepts
======================== ======================= ======================================

Three readers, three different answers about which extension dtypes exist
(``DECISIONS.md`` D-0047, ``prereg/P4-portability.md``). **The falsifier did not fire** —
one reader that can read the headers settles that they *can* be read — but ``struct`` has
**no Zarr v3 specification**, so a reader that declines it is standards-conformant and
still right. Portability of ``headers`` therefore rests on one implementation's goodwill.

§10.3 is the reason adopting SDIP is a reversible decision: *no consumer is required to
install ``sdip`` or ``mdio``*. This module replaces goodwill with a guarantee — **a 2-D
``uint8`` array is as portable as Zarr gets** — and the pre-registration pre-approved it.

Five decisions, each of which could have gone the other way:

**1. Read from the SOURCE FILE, by raw byte offset.** Not from the decoded ``headers``
array. Re-serialising parsed fields would produce a plane that agrees with the field-wise
comparison by construction, and Plane 3's whole point in gaining this leg is a comparison
that does **not** depend on the spec. The bytes are the claim, so the bytes are what is
read: trace data begins after the file headers, and each trace is 240 header bytes then
its samples, at fixed offsets, needing no spec and no parser — the same reasoning as
:mod:`sdip.ingest.file_headers` and :mod:`sdip.ingest.raw_samples`.

**2. ``uint8``, and nothing else.** Exactly **SP5**'s argument for the filler bytes: the
dtype is a **container, not an interpretation**. ``uint8`` carries no byte-order and no
numeric-format semantics, so no decode can be applied to these bytes by accident and no
reader has to agree with SDIP about what byte 233 means in order to recover it.

**3. Shaped by the store's own grid.** The dimension names come from Zarr v3
``dimension_names`` via :func:`sdip.equivalence.planes.store_dimensions`. **Nothing here
hard-codes ``inline``/``crossline``** — that was defect D-0039, which made all three
per-trace planes unrunnable on every prestack geometry.

**4. Written unconditionally.** Unlike the ``ibm32`` raw view, which exists only for the
sample format whose decode probe P2 measured as lossy, **every store has headers and the
portability problem is not conditional**. An array written only sometimes would leave the
portability guarantee contingent on a property of the source that has nothing to do with
it.

**5. Written with stock ``zarr``, not MDIO.** §10.3 and gate G4: the entire point is a
consumer with MDIO uninstalled, so the array is written the way such a consumer reads it.

**Padding is not data (SP12).** A cell no source trace maps to keeps the fill byte
``0x00`` — which is a perfectly valid header byte — so **no fill value can announce
itself**, and the store's ``trace_mask`` is the only discriminator. That is the same
exposure ``OPEN_DEBTS`` D29 records for the structured ``headers`` array, which pads with
zeros for the same reason, and it is stated in this array's own attributes rather than
left to a document.

What this does **not** fix
--------------------------
``OPEN_DEBTS`` D32. zarr-java's ``Group.list()`` fails outright on an SDIP store, because
listing opens every child node and ``segy_file_header`` keeps ``fixed_length_utf32``:

    Failed to read node metadata for key 'segy_file_header/zarr.json':
    Cannot deserialize value of type DataType from Object value

**This plane makes the header *data* readable. It does not make the group *listable*.**
A zarr-java consumer that opens ``headers_raw_uint8`` by name gets the bytes; one that
enumerates the group first still fails, and this module does not change that.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

import numpy as np
from numpy.typing import NDArray

from sdip._pins import (
    SEGY_BINARY_HEADER_BYTES,
    SEGY_TEXTUAL_HEADER_BYTES,
    SEGY_TRACE_HEADER_BYTES,
)
from sdip.errors import UntrustedInputError

ARRAY_NAME: Final[str] = "headers_raw_uint8"
"""Name of the parallel plane. Named for what it is, next to what it shadows."""

TRACE_DATA_OFFSET: Final[int] = SEGY_TEXTUAL_HEADER_BYTES + SEGY_BINARY_HEADER_BYTES
"""First byte of the first trace header when there is no extended textual header.

3600 in every SEG-Y revision, by definition. A file carrying extended textual headers
pushes the trace data further out, which is why :func:`trace_data_offset` exists rather
than this constant being used directly.
"""

BYTE_AXIS_NAME: Final[str] = "trace_header_byte"
"""Name of the trailing axis. Zarr v3 wants one ``dimension_names`` entry per axis, and
an unnamed byte axis would leave a consumer guessing what the 240 is."""

FILL_BYTE: Final[int] = 0
"""Padding cells. Not data (**SP12**) - see the module docstring on why no fill byte can
announce itself as such, and why ``trace_mask`` is the discriminator."""

ATTR_UNDECODED: Final[str] = "sdipHeaderPlaneUndecoded"
ATTR_BYTE_LAYOUT: Final[str] = "sdipHeaderPlaneByteLayout"
ATTR_CONTAINER: Final[str] = "sdipHeaderPlaneContainer"
ATTR_RATIONALE: Final[str] = "sdipHeaderPlaneRationale"
ATTR_PROBE: Final[str] = "sdipHeaderPlaneProbe"
ATTR_AUTHORITATIVE: Final[str] = "sdipHeaderPlaneAuthoritative"
ATTR_LIVE_MASK: Final[str] = "sdipHeaderPlaneLiveMask"
ATTR_FILL_BYTE: Final[str] = "sdipHeaderPlaneFillByte"
ATTR_LIMITATION: Final[str] = "sdipHeaderPlaneLimitation"
"""SDIP's own namespace, as in :mod:`sdip.ingest.file_headers`. A consumer reading this
array must be able to learn what it is holding from the array itself."""

RATIONALE: Final[str] = (
    "The 240 raw trace-header bytes, undecoded, in a Zarr v3 CORE-SPEC dtype. Stored "
    "because probe P4 measured three Zarr readers giving three different answers about "
    "the structured `headers` array: TensorStore 0.1.85 accepts its `struct` data_type "
    "and read 97/97 fields byte-identically, zarr-java 0.2.0 refuses it outright, and "
    "zarr-python accepts it with a warning. `struct` has NO Zarr v3 specification, so a "
    "reader that declines it is conformant and still right - which leaves the "
    "portability of `headers` resting on one implementation's goodwill. Section 10.3 "
    "says no consumer is required to install sdip or mdio. A 2-D uint8 array is as "
    "portable as Zarr gets. See prereg/P4-portability.md and DECISIONS.md D-0047."
)

CONTAINER_NOTE: Final[str] = (
    "uint8 is a CONTAINER, not an interpretation. It carries no byte-order and no "
    "numeric-format semantics, so no decode can be applied to these bytes by accident "
    "and no reader has to agree with SDIP about what a byte means to recover it. Same "
    "reasoning as SP5's uint8 fillers for header bytes no revision names."
)

BYTE_LAYOUT: Final[str] = (
    "Axis -1 is trace-header bytes 1-240 in source order: element i is the byte at "
    "offset i of that trace's 240-byte header, exactly as it appears in the source "
    "file. Nothing was decoded, scaled, byte-swapped or re-serialised on the way in; "
    "the bytes were read from the file by raw offset, not from the parsed `headers` "
    "array."
)

AUTHORITATIVE_NOTE: Final[str] = (
    "AUTHORITATIVE for Plane 3 (gate G2c) alongside the structured `headers` array. "
    "Plane 3's field-wise comparison equals byte equality only because G1 proved the "
    "spec covers all 240 bytes with no gaps; this array is compared as BYTES and "
    "carries no spec dependency at all. Both legs are ANDed into G2c's verdict, so a "
    "corrupted plane fails the gate rather than being reported under a PASS."
)

LIVE_MASK_NOTE: Final[str] = (
    "Cells no source trace maps to carry the fill byte and are NOT data (SP12). 0x00 is "
    "a valid trace-header byte, so the fill value cannot announce itself; the store's "
    "trace_mask is the discriminator, exactly as it is for `headers` and `amplitude`. "
    "This is the same exposure OPEN_DEBTS D29 records for the structured array, which "
    "pads with zeros for the same reason."
)

LIMITATION_NOTE: Final[str] = (
    "This array makes the header DATA readable by any Zarr v3 reader. It does NOT make "
    "the group LISTABLE: zarr-java's Group.list() opens every child node and "
    "segy_file_header keeps the fixed_length_utf32 data_type, which it refuses. A "
    "consumer that opens this array by name gets the bytes; one that enumerates the "
    "group first still fails. See OPEN_DEBTS D32."
)


@dataclass(frozen=True, slots=True)
class HeaderPlane:
    """What the parallel header plane holds, in certificate shape."""

    array: str
    dtype: str
    shape: tuple[int, ...]
    dimensions: tuple[str, ...]
    bytes_per_trace: int
    traces_written: int
    source_trace_count: int
    source_bytes_per_trace: int

    @property
    def complete(self) -> bool:
        """True when every source trace's header bytes reached the array.

        A source trace that maps to no grid cell is Plane 5's finding, not this
        module's to resolve — but its bytes are then **not** in the store, and a
        certificate should not have to infer that from two other numbers.
        """
        return self.traces_written == self.source_trace_count

    def to_json(self) -> dict[str, Any]:
        """Certificate-shaped mapping."""
        return {
            "array": self.array,
            "dtype": self.dtype,
            "shape": list(self.shape),
            "dimensions": list(self.dimensions),
            "bytes_per_trace": self.bytes_per_trace,
            "traces_written": self.traces_written,
            "source_trace_count": self.source_trace_count,
            "source_bytes_per_trace": self.source_bytes_per_trace,
            "complete": self.complete,
            "zarr_v3_core_spec": True,
            "probe": "P4",
            "rationale": RATIONALE,
            "limitation": LIMITATION_NOTE,
        }


def sample_bytes(segy_spec: Any) -> int:
    """Bytes one sample occupies in the source, from the **declared** sample format.

    ``ibm32`` is four bytes and is what rev 1 mandates, but this plane is written for
    every store (decision 4), and an ``int16`` or ``float64`` source has a different
    stride between trace headers. Hard-coding four would put every header offset in such
    a file at the wrong place — silently, because the bytes read would still be *some*
    bytes.

    The width is read off the spec's own dtype rather than from a table SDIP maintains,
    so a format the pinned ``segy`` knows about and SDIP does not cannot go wrong here.

    Args:
        segy_spec: The ``SegySpec`` the ingest ran against.

    Returns:
        Bytes per sample.

    Raises:
        UntrustedInputError: If the spec declares no usable sample width.
    """
    try:
        width = int(segy_spec.trace.data.format.dtype.itemsize)
    except (AttributeError, TypeError, ValueError) as exc:
        msg = (
            "the SEG-Y spec declares no sample format width, so the distance between "
            "trace headers in the source cannot be computed and no header byte offset "
            "in this file can be trusted"
        )
        raise UntrustedInputError(msg) from exc
    if width <= 0:
        msg = f"declared sample width is {width} bytes; must be positive"
        raise UntrustedInputError(msg)
    return width


def trace_data_offset(handle: Any) -> int:
    """First byte of the first trace header, allowing for extended textual headers.

    3600 is the offset for a file with none, which is the common case and every fixture
    in this repository. A file carrying *E* extended textual headers pushes the trace
    data out by ``E x 3200``, and reading it at 3600 would land mid-header on every
    trace. The count comes from the open source file rather than from SDIP.

    Args:
        handle: An open ``SegyFile``.

    Returns:
        Byte offset of the first trace header.
    """
    extended = int(getattr(handle, "num_ext_text", 0) or 0)
    return TRACE_DATA_OFFSET + extended * SEGY_TEXTUAL_HEADER_BYTES


def source_trace_layout(
    size: int,
    *,
    samples_per_trace: int,
    bytes_per_sample: int,
    data_offset: int = TRACE_DATA_OFFSET,
) -> tuple[int, int]:
    """Reconcile a declared trace length against the file's actual size. Spec §11.4.

    ``samples_per_trace`` reaches this module from the source's binary header — i.e.
    from the file being validated. **A length read out of untrusted input never drives an
    allocation until the file agrees with it**, so the only thing done with it here is
    arithmetic against ``size``.

    Args:
        size: Actual size of the source file in bytes.
        samples_per_trace: Declared samples per trace.
        bytes_per_sample: Declared width of one sample, from :func:`sample_bytes`.
        data_offset: Byte offset of the first trace header, from
            :func:`trace_data_offset`.

    Returns:
        ``(trace_count, bytes_per_trace)``.

    Raises:
        UntrustedInputError: If the declared length does not divide the trace data
            exactly, which means the two disagree and neither can be trusted.
    """
    if samples_per_trace <= 0:
        msg = f"declared samples_per_trace is {samples_per_trace}; must be positive"
        raise UntrustedInputError(msg)
    if bytes_per_sample <= 0:
        msg = f"declared bytes_per_sample is {bytes_per_sample}; must be positive"
        raise UntrustedInputError(msg)
    stride = SEGY_TRACE_HEADER_BYTES + samples_per_trace * bytes_per_sample
    body = size - data_offset
    if body <= 0:
        msg = (
            f"source has {size} bytes, which is no more than the {data_offset} bytes of "
            "file headers; it carries no trace data"
        )
        raise UntrustedInputError(msg)
    if body % stride:
        msg = (
            f"source carries {body} bytes of trace data, which is not a whole number of "
            f"{stride}-byte traces ({SEGY_TRACE_HEADER_BYTES} header + {samples_per_trace} "
            f"samples x {bytes_per_sample}). The declared trace length and the file "
            "disagree, so no header byte offset in this file can be trusted."
        )
        raise UntrustedInputError(msg)
    return body // stride, stride


def read_source_header_bytes(
    source: str | Path,
    *,
    samples_per_trace: int,
    bytes_per_sample: int,
    data_offset: int = TRACE_DATA_OFFSET,
) -> NDArray[np.uint8]:
    """Read every trace's 240 header bytes straight from the source, undecoded.

    Memory-mapped rather than read: the header bytes are interleaved with the sample
    area, so materialising them by reading the file would put a survey-scale source
    through RAM (§11.2). The returned array is a ``uint8`` view over the mapping, so no
    byte is touched until a caller indexes it.

    Args:
        source: SEG-Y file.
        samples_per_trace: Declared samples per trace, reconciled against the file size
            by :func:`source_trace_layout` before any offset is computed.
        bytes_per_sample: Declared width of one sample, from :func:`sample_bytes`.
        data_offset: Byte offset of the first trace header, from
            :func:`trace_data_offset`.

    Returns:
        Shape ``(trace_count, 240)``, one row per source trace.

    Raises:
        UntrustedInputError: If the declared trace length and the file disagree.
    """
    path = Path(source)
    trace_count, _ = source_trace_layout(
        path.stat().st_size,
        samples_per_trace=samples_per_trace,
        bytes_per_sample=bytes_per_sample,
        data_offset=data_offset,
    )
    record = np.dtype(
        [
            ("header", "u1", (SEGY_TRACE_HEADER_BYTES,)),
            ("samples", f"V{samples_per_trace * bytes_per_sample}"),
        ]
    )
    mapped = np.memmap(path, dtype=record, mode="r", offset=data_offset, shape=(trace_count,))
    header_bytes: NDArray[np.uint8] = mapped["header"]
    return header_bytes


def open_header_plane(store: str | Path) -> Any | None:
    """Open the parallel header plane on a store, or ``None`` when it carries none.

    ``None`` is the honest answer for a store ingested before this array existed. A
    caller must distinguish *"checked and identical"* from *"there was nothing to
    check"* — conflating them would turn an absent array into evidence, which is exactly
    the ``NOT_RUN``-as-``PASS`` mistake §7 bars.
    """
    import zarr

    group = zarr.open_group(str(store), mode="r")
    if ARRAY_NAME not in group:
        return None
    return group[ARRAY_NAME]


def attach_header_plane(
    store: str | Path,
    source: str | Path,
    segy_spec: Any,
    *,
    variable: str = "headers",
) -> HeaderPlane:
    """Write the parallel ``uint8`` header plane alongside the structured headers.

    **Unconditional** (decision 4 in the module docstring): every store has headers, and
    a portability guarantee that applies only to some sources is not a guarantee.

    The grid comes from the store's own Zarr v3 ``dimension_names``; **nothing here
    hard-codes ``inline``/``crossline``**, which was defect D-0039 and made all three
    per-trace planes unrunnable on prestack.

    Placement reuses :func:`sdip.equivalence.trace_map.build_trace_map` — the same map
    Plane 3 uses to compare the structured headers. That is deliberate: if the map
    disagreed with where MDIO actually put a trace, Plane 3's **field** leg would fail on
    this store, so the placement is already under test by an independent comparison.

    Args:
        store: The MDIO store, written in place.
        source: The SEG-Y the store was ingested from. Read by raw offset.
        segy_spec: The ``SegySpec`` the ingest ran against.
        variable: The structured array whose shape and dimensions this plane mirrors.

    Returns:
        What was written.

    Raises:
        UntrustedInputError: If the source's declared trace length and its size disagree,
            or if the raw byte arithmetic and the pinned parser count different numbers
            of traces in it.
    """
    import zarr
    from segy import SegyFile
    from zarr.codecs import BloscCodec

    # Local imports: `sdip.equivalence.planes` imports this package, so a module-level
    # import here would close the cycle at import time.
    from sdip.equivalence.planes import grid_coordinates, store_dimensions
    from sdip.equivalence.trace_map import build_trace_map

    group = zarr.open_group(str(store), mode="r+")
    structured: Any = group[variable]
    grid_shape = tuple(int(n) for n in structured.shape)
    shape = (*grid_shape, SEGY_TRACE_HEADER_BYTES)

    grid_dimensions = store_dimensions(group, variable=variable)
    dimensions = (*grid_dimensions, BYTE_AXIS_NAME)

    handle = SegyFile(str(Path(source)), spec=segy_spec)
    samples_per_trace = int(handle.samples_per_trace)
    bytes_per_sample = sample_bytes(segy_spec)
    data_offset = trace_data_offset(handle)

    source_count, stride = source_trace_layout(
        Path(source).stat().st_size,
        samples_per_trace=samples_per_trace,
        bytes_per_sample=bytes_per_sample,
        data_offset=data_offset,
    )
    # The pinned parser counted the traces its own way. Two derivations of the same
    # number from the same file, and a disagreement means one of them is reading the file
    # at the wrong offsets - which is not a thing to resolve by picking one.
    if source_count != int(handle.num_traces):
        msg = (
            f"raw byte arithmetic finds {source_count} traces in the source while the "
            f"parser reports {int(handle.num_traces)}. The two disagree about the file's "
            "layout, so no header byte offset in it can be trusted."
        )
        raise UntrustedInputError(msg)

    raw = read_source_header_bytes(
        source,
        samples_per_trace=samples_per_trace,
        bytes_per_sample=bytes_per_sample,
        data_offset=data_offset,
    )
    trace_map = build_trace_map(
        handle.header[:], grid_coordinates(group, grid_dimensions), grid_dimensions
    )

    array = group.create_array(
        name=ARRAY_NAME,
        shape=shape,
        dtype="uint8",
        chunks=(*tuple(int(c) for c in structured.chunks), SEGY_TRACE_HEADER_BYTES),
        dimension_names=dimensions,
        fill_value=FILL_BYTE,
        # Blosc/Zstd only. A lossy codec on THIS array would destroy the bytes it exists
        # to preserve, and a store whose manifest carries one is void (**SP3**).
        compressors=BloscCodec(cname="zstd", clevel=5),
        attributes={
            ATTR_UNDECODED: True,
            ATTR_BYTE_LAYOUT: BYTE_LAYOUT,
            ATTR_CONTAINER: CONTAINER_NOTE,
            ATTR_RATIONALE: RATIONALE,
            ATTR_PROBE: "P4",
            ATTR_AUTHORITATIVE: AUTHORITATIVE_NOTE,
            ATTR_LIVE_MASK: LIVE_MASK_NOTE,
            ATTR_FILL_BYTE: FILL_BYTE,
            ATTR_LIMITATION: LIMITATION_NOTE,
        },
        overwrite=True,
    )

    # One hyperplane in memory at a time rather than the whole plane: 240 bytes per trace
    # is the same volume the structured array already occupies, and D2 records that
    # nothing about survey-scale memory behaviour was measured until P3.
    grouped: dict[int, list[tuple[int, tuple[int, ...]]]] = defaultdict(list)
    for ordinal, cell in trace_map.ordinal_to_cell.items():
        grouped[cell[0]].append((ordinal, cell))

    written = 0
    for outer in sorted(grouped):
        block = np.full(shape[1:], FILL_BYTE, dtype=np.uint8)
        for ordinal, cell in grouped[outer]:
            block[cell[1:]] = raw[ordinal]
            written += 1
        array[outer] = block

    return HeaderPlane(
        array=ARRAY_NAME,
        dtype="uint8",
        shape=shape,
        dimensions=dimensions,
        bytes_per_trace=SEGY_TRACE_HEADER_BYTES,
        traces_written=written,
        source_trace_count=source_count,
        source_bytes_per_trace=stride,
    )
