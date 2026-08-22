"""The raw ``uint32`` sample view. Probe **P2**'s remaining remedy, ``OPEN_DEBTS.md`` D1.

**Probe P2 fired.** Swept exhaustively over the IBM exponent axis under the binding pins,
only 1,656 of 4,103 words round-trip ``ibm32 → float32 → ibm32`` bit-identically.
**1,939 lose the value, not merely the spelling**: exponent codes 97-127 decode to
``inf``, codes 1-32 flush to zero. **No re-encoding can reconstruct them, because the
information left the pipeline at decode time** (``DECISIONS.md`` D-0034,
``prereg/P2-ibm32-fidelity.md``).

**SP1** permits exactly one transform and requires it exactly invertible. It is not. The
pre-registration's own *"if it fires"* clause names the remedy this module implements:

    The raw ``uint32`` view is stored **in parallel** with the decoded ``float32``, so
    the source bits are recoverable regardless of the decode.

Four decisions, each of which could have gone the other way and would have been wrong
if it had:

**1. Read from the SOURCE FILE, by raw byte offset.** The decoded store cannot answer
the question being asked of it — a sample that overflowed reads back as ``inf`` and an
underflowed one as ``0.0``, and neither carries the exponent that produced it. Deriving
the "raw" view from the decoded array would produce an array that agrees with itself and
proves nothing. Trace data starts at byte 3600; each trace is 240 header bytes then
``samples_per_trace x 4`` sample bytes, at fixed offsets, needing no spec and no parser —
the same reasoning as :mod:`sdip.ingest.file_headers`.

**2. ``uint32``, and nothing else.** Exactly SP5's argument for ``uint8`` fillers: the
dtype is a **container, not an interpretation**. ``uint32`` carries no float semantics,
no exponent, no bias, so no decode can be applied to it by accident and no consumer can
mistake it for a measured amplitude. Storing these words as ``float32`` would re-run the
lossy decode; storing them as a big-endian float type would invite a reader to interpret
them. The word's value is ``int.from_bytes(source_bytes, "big")`` and the source bytes
come back as ``value.to_bytes(4, "big")``.

**3. Only when the source's sample format is ``ibm32``.** A ``float32`` or ``int16``
source decodes exactly, so a parallel copy of it would double the store to restate what
``amplitude`` already holds. The array must not exist for those sources: an array that is
always present says nothing about the one case where it matters.

**4. Written with stock ``zarr``, not MDIO.** §10.3 and gate G4 require a consumer with
MDIO uninstalled to read every array it needs. This one is written the way such a
consumer reads it, and it is the *only* recoverable copy of the source bits — an
MDIO-only encoding here would put the last copy behind the dependency G4 exists to
remove.

**Padding is not data (SP12).** Cells no source trace maps to keep the fill word
``0x00000000`` — which is itself a perfectly valid IBM word for true zero. **No ``uint32``
is an invalid IBM word**, so the fill value cannot be self-identifying no matter what it
is set to, and the store's ``trace_mask`` is the only thing that distinguishes a measured
word from grid padding. It governs this array exactly as it governs ``amplitude``, which
is why Plane 4 compares live cells only and never the padding.
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

ARRAY_NAME: Final[str] = "amplitude_raw_ibm32"
"""Name of the parallel array. Named for what it is, next to what it shadows."""

SAMPLE_WORD_BYTES: Final[int] = 4
"""An ``ibm32`` sample is four bytes. The one number this module's arithmetic rests on."""

TRACE_DATA_OFFSET: Final[int] = SEGY_TEXTUAL_HEADER_BYTES + SEGY_BINARY_HEADER_BYTES
"""First byte of the first trace header. 3600 in every SEG-Y revision, by definition."""

FILL_WORD: Final[int] = 0
"""Padding cells. Not data (**SP12**) - see the module docstring on why no fill can
announce itself as such, and why ``trace_mask`` is the discriminator."""

ATTR_UNDECODED: Final[str] = "sdipRawSampleUndecoded"
ATTR_SOURCE_FORMAT: Final[str] = "sdipRawSampleSourceFormat"
ATTR_WORD_LAYOUT: Final[str] = "sdipRawSampleWordLayout"
ATTR_CONTAINER: Final[str] = "sdipRawSampleContainer"
ATTR_RATIONALE: Final[str] = "sdipRawSampleRationale"
ATTR_PROBE: Final[str] = "sdipRawSampleProbe"
ATTR_LIVE_MASK: Final[str] = "sdipRawSampleLiveMask"
ATTR_FILL_WORD: Final[str] = "sdipRawSampleFillWord"
"""SDIP's own namespace, as in :mod:`sdip.ingest.file_headers`. A consumer reading this
array must be able to learn what it is holding from the array itself."""

RATIONALE: Final[str] = (
    "Undecoded source words, stored because probe P2 measured ibm32 -> float32 as NOT "
    "exactly invertible: 2,447 of 4,103 swept words are not bit-identical after a round "
    "trip and 1,939 lose the VALUE, not merely the spelling (exponent codes 97-127 "
    "overflow to inf, codes 1-32 underflow to zero). Those values cannot be recovered "
    "from the decoded float32 by any re-encoding, because the information left the "
    "pipeline at decode time. This array is the only place the source bits survive. "
    "See prereg/P2-ibm32-fidelity.md and DECISIONS.md D-0034."
)

CONTAINER_NOTE: Final[str] = (
    "uint32 is a CONTAINER, not an interpretation. It carries no float semantics, no "
    "exponent and no bias, so no decode can be applied to these words by accident. "
    "Same reasoning as SP5's uint8 fillers for unknown header bytes."
)

WORD_LAYOUT: Final[str] = (
    "Each value is the big-endian IBM-360 32-bit floating-point word exactly as it "
    "appears in the source file: value == int.from_bytes(source_bytes, 'big'), and the "
    "source bytes are recovered as value.to_bytes(4, 'big'). Nothing was decoded, "
    "scaled, normalised or byte-swapped on the way in."
)

LIVE_MASK_NOTE: Final[str] = (
    "Cells no source trace maps to carry the fill word and are NOT data (SP12). No "
    "uint32 is an invalid IBM word, so the fill value cannot announce itself; the "
    "store's trace_mask is the discriminator, exactly as it is for amplitude."
)


@dataclass(frozen=True, slots=True)
class RawSampleView:
    """What the parallel raw view holds, in certificate shape."""

    array: str
    dtype: str
    shape: tuple[int, ...]
    dimensions: tuple[str, ...]
    sample_format: str
    samples_per_trace: int
    traces_written: int
    source_trace_count: int
    source_bytes_per_trace: int

    @property
    def complete(self) -> bool:
        """True when every source trace's words reached the array.

        A source trace that maps to no grid cell is Plane 5's finding, not this
        module's to resolve — but its words are then **not** in the store, and a
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
            "sample_format": self.sample_format,
            "samples_per_trace": self.samples_per_trace,
            "traces_written": self.traces_written,
            "source_trace_count": self.source_trace_count,
            "source_bytes_per_trace": self.source_bytes_per_trace,
            "complete": self.complete,
            "probe": "P2",
            "rationale": RATIONALE,
        }


def source_trace_layout(size: int, samples_per_trace: int) -> tuple[int, int]:
    """Reconcile a declared trace length against the file's actual size. Spec §11.4.

    ``samples_per_trace`` reaches this module from the store, which got it from the
    source's binary header — i.e. from the file being validated. **A length read out of
    untrusted input never drives an allocation until the file agrees with it**, so the
    only thing done with it here is arithmetic against ``size``.

    Args:
        size: Actual size of the source file in bytes.
        samples_per_trace: Declared samples per trace.

    Returns:
        ``(trace_count, bytes_per_trace)``.

    Raises:
        UntrustedInputError: If the declared length does not divide the trace data
            exactly, which means the two disagree and neither can be trusted.
    """
    if samples_per_trace <= 0:
        msg = f"declared samples_per_trace is {samples_per_trace}; must be positive"
        raise UntrustedInputError(msg)
    stride = SEGY_TRACE_HEADER_BYTES + samples_per_trace * SAMPLE_WORD_BYTES
    body = size - TRACE_DATA_OFFSET
    if body <= 0:
        msg = (
            f"source has {size} bytes, which is no more than the {TRACE_DATA_OFFSET} "
            "bytes of file headers; it carries no trace data"
        )
        raise UntrustedInputError(msg)
    if body % stride:
        msg = (
            f"source carries {body} bytes of trace data, which is not a whole number of "
            f"{stride}-byte traces ({SEGY_TRACE_HEADER_BYTES} header + {samples_per_trace} "
            f"samples x {SAMPLE_WORD_BYTES}). The declared sample count and the file "
            "disagree, so no raw word offset in this file can be trusted."
        )
        raise UntrustedInputError(msg)
    return body // stride, stride


def read_source_words(source: str | Path, *, samples_per_trace: int) -> NDArray[np.uint32]:
    """Read every trace's raw sample words straight from the source, undecoded.

    Memory-mapped rather than read: the sample area **is** the file, and materialising it
    to copy it into the store would put a survey-scale source through RAM (§11.2). The
    returned array is a big-endian ``uint32`` view over the mapping, so no byte is
    touched until a caller indexes it.

    Args:
        source: SEG-Y file.
        samples_per_trace: Declared samples per trace, reconciled against the file size
            by :func:`source_trace_layout` before any offset is computed.

    Returns:
        Shape ``(trace_count, samples_per_trace)``, one raw word per sample.

    Raises:
        UntrustedInputError: If the declared trace length and the file disagree.
    """
    path = Path(source)
    trace_count, _ = source_trace_layout(path.stat().st_size, samples_per_trace)
    record = np.dtype(
        [
            ("header", f"V{SEGY_TRACE_HEADER_BYTES}"),
            ("samples", ">u4", (samples_per_trace,)),
        ]
    )
    mapped = np.memmap(path, dtype=record, mode="r", offset=TRACE_DATA_OFFSET, shape=(trace_count,))
    words: NDArray[np.uint32] = mapped["samples"]
    return words


def open_raw_sample_view(store: str | Path) -> Any | None:
    """Open the parallel raw view on a store, or ``None`` when it carries none.

    ``None`` is the honest answer for a ``float32`` source (the view is not written) and
    for a store ingested before this array existed. A caller must distinguish *"checked
    and identical"* from *"there was nothing to check"* — conflating them would turn an
    absent array into evidence, which is exactly the ``NOT_RUN``-as-``PASS`` mistake §7
    bars.
    """
    import zarr

    group = zarr.open_group(str(store), mode="r")
    if ARRAY_NAME not in group:
        return None
    return group[ARRAY_NAME]


def attach_raw_sample_view(
    store: str | Path,
    source: str | Path,
    segy_spec: Any,
    *,
    variable: str = "amplitude",
) -> RawSampleView | None:
    """Write the raw ``uint32`` sample view alongside the decoded volume.

    Does nothing and returns ``None`` unless the spec's **sample format** is ``ibm32`` —
    see decision 3 in the module docstring.

    The grid comes from the store's own Zarr v3 ``dimension_names``; **nothing here
    hard-codes ``inline``/``crossline``**, which was defect D-0039 and made all three
    per-trace planes unrunnable on prestack.

    Placement reuses :func:`sdip.equivalence.trace_map.build_trace_map` — the same map
    Plane 4 uses to compare the decoded samples. That is deliberate: if the map disagreed
    with where MDIO actually put a trace, Plane 4's **float** leg would fail on this
    store, so the placement is already under test by an independent comparison.

    Args:
        store: The MDIO store, written in place.
        source: The SEG-Y the store was ingested from. Read by raw offset.
        segy_spec: The ``SegySpec`` the ingest ran against.
        variable: The decoded volume whose shape and dimensions this view mirrors.

    Returns:
        What was written, or ``None`` when the source is not ``ibm32``.

    Raises:
        UntrustedInputError: If the source's declared trace length and its size disagree.
    """
    # Local imports: `sdip.equivalence.planes` imports this package, so a module-level
    # import here would close the cycle at import time.
    from sdip.equivalence.planes import grid_coordinates, store_dimensions
    from sdip.equivalence.trace_map import build_trace_map
    from sdip.spec.transforms import detect_ibm32

    sample_format = detect_ibm32(segy_spec).sample_format
    if sample_format is None:
        return None

    import zarr
    from segy import SegyFile
    from zarr.codecs import BloscCodec

    group = zarr.open_group(str(store), mode="r+")
    decoded: Any = group[variable]
    shape = tuple(int(n) for n in decoded.shape)
    dimensions = tuple(str(n) for n in decoded.metadata.to_dict().get("dimension_names") or ())
    samples_per_trace = shape[-1]

    words = read_source_words(source, samples_per_trace=samples_per_trace)
    handle = SegyFile(str(Path(source)), spec=segy_spec)
    grid_dimensions = store_dimensions(group)
    trace_map = build_trace_map(
        handle.header[:], grid_coordinates(group, grid_dimensions), grid_dimensions
    )

    array = group.create_array(
        name=ARRAY_NAME,
        shape=shape,
        dtype="uint32",
        chunks=decoded.chunks,
        dimension_names=dimensions,
        fill_value=FILL_WORD,
        # Blosc/Zstd only. A lossy codec on THIS array would destroy the bits it exists
        # to preserve, and a store whose manifest carries one is void (**SP3**).
        compressors=BloscCodec(cname="zstd", clevel=5),
        attributes={
            ATTR_UNDECODED: True,
            ATTR_SOURCE_FORMAT: sample_format,
            ATTR_WORD_LAYOUT: WORD_LAYOUT,
            ATTR_CONTAINER: CONTAINER_NOTE,
            ATTR_RATIONALE: RATIONALE,
            ATTR_PROBE: "P2",
            ATTR_LIVE_MASK: LIVE_MASK_NOTE,
            ATTR_FILL_WORD: FILL_WORD,
        },
        overwrite=True,
    )

    # One hyperplane in memory at a time rather than the whole volume: this array is the
    # same size as `amplitude`, and D2 records that nothing about survey-scale memory
    # behaviour has been measured yet (probe P3).
    grouped: dict[int, list[tuple[int, tuple[int, ...]]]] = defaultdict(list)
    for ordinal, cell in trace_map.ordinal_to_cell.items():
        grouped[cell[0]].append((ordinal, cell))

    written = 0
    for outer in sorted(grouped):
        block = np.full(shape[1:], FILL_WORD, dtype=np.uint32)
        for ordinal, cell in grouped[outer]:
            block[cell[1:]] = words[ordinal]
            written += 1
        array[outer] = block

    return RawSampleView(
        array=ARRAY_NAME,
        dtype="uint32",
        shape=shape,
        dimensions=dimensions,
        sample_format=sample_format,
        samples_per_trace=samples_per_trace,
        traces_written=written,
        source_trace_count=int(words.shape[0]),
        source_bytes_per_trace=SEGY_TRACE_HEADER_BYTES + samples_per_trace * SAMPLE_WORD_BYTES,
    )
