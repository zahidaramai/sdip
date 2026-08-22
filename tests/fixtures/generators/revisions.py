"""One deterministic synthetic 3D poststack SEG-Y per revision, for probe **P6**.

P6 asks whether rev 0, 1, 2 and 2.1 each get a gap-free spec, an ingest and a round
trip. Answering that needs four fixtures that differ **only** in the revision, so that a
difference in the result is attributable to the revision and to nothing else. The
geometry, the amplitudes, the planted header bytes and the textual header are therefore
identical across all four and identical to the Appendix A.1 article: 5 inlines x
6 crosslines x 32 samples = 30 traces, seed ``20260822``.

Everything is a pure function of the arguments, for the reasons recorded in
:mod:`tests.fixtures.generators.poststack3d`: §6.6 makes the generator *be* the fixture,
and G6 requires two runs to produce identical bytes. That module's two hard-won points
apply here unchanged — ``SegyFactory.create_textual_header()`` with no argument embeds
``datetime.now()``, and it does not pad — so the text is passed explicitly and the
encoded length is asserted.

Two revision-specific facts drive everything else in this module.

**rev 0 declares nothing above byte 180.** ``cdp_x``, ``cdp_y``, ``inline`` and
``crossline`` enter the standard at rev 1. A rev-0 fixture built only from named fields
would carry no geometry at all, and P6 would be measuring an empty file rather than a
revision. So the geometry is written **by raw byte offset** at the positions every later
revision uses (181-196, big-endian ``int32``): the bytes are where a reader expects
them, and only the rev-0 *standard* declines to name them. That is exactly the situation
a real rev-0 archive presents, and it is what §6.4 survey overrides exist for.

**rev 0 declares no sample format either.** The format is operator-supplied, which under
**SP1** makes it a declared transform that must be *stated*, not assumed silently — see
:class:`SampleFormatDeclaration`, which every fixture carries.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from segy.factory import SegyFactory
from segy.standards import get_segy_standard

from sdip._pins import (
    SEGY_BINARY_HEADER_BYTES as BINARY_HEADER_BYTES,
)
from sdip._pins import (
    SEGY_TEXTUAL_HEADER_BYTES as TEXTUAL_HEADER_BYTES,
)
from sdip._pins import (
    SEGY_TRACE_HEADER_BYTES as TRACE_HEADER_BYTES,
)

# Imported, not re-derived. The article's ground truth has exactly one definition; a
# second copy here could drift, and "comparable to the P1 article" would quietly stop
# being true. `_analytic_amplitudes` is private to that module but is the article's
# closed-form expression, and copying it is the failure mode this import avoids.
from tests.fixtures.generators.poststack3d import (
    DEFAULT_SEED,
    DETERMINISTIC_TEXT,
    PLANTED_BYTES,
    _analytic_amplitudes,
)

GEOMETRY_BYTES: dict[str, int] = {
    "cdp_x": 181,
    "cdp_y": 185,
    "inline": 189,
    "crossline": 193,
}
"""Canonical start byte of each geometry field, big-endian ``int32``, 4 bytes each.

The rev 1 layout, unchanged in rev 2 and rev 2.1, and undeclared in rev 0.
"""

GEOMETRY_FIELD_BYTES = 4
"""Every field in :data:`GEOMETRY_BYTES` is a 4-byte big-endian signed integer."""

REV0_UNDECLARED_FROM = 181
"""First trace-header byte the rev 0 standard leaves undeclared. Bytes 181-240."""


@dataclass(frozen=True, slots=True)
class SampleFormatDeclaration:
    """The sample format a fixture was written with, and where that came from (**SP1**).

    SP1 permits exactly one transform — the declared SEG-Y sample-format decode — and
    requires it to be declared rather than inferred. For rev 1 and later the declaration
    lives in the file: the standard defines binary header bytes 3225-3226 and a
    conforming writer fills them.

    **rev 0 carries no such guarantee.** The 1975 standard defines no mandatory
    sample-format field, so the format is operator-supplied. This record is what
    "supplied" means for a given fixture, and it is carried on the fixture so that a
    report can state it instead of assuming it.
    """

    scalar_type: str
    declared_by_standard: bool
    supplied_via: str


_LATER_REVISION_FORMAT = (
    "binary header bytes 3225-3226 (data_sample_format), written by "
    "SegyFactory.create_binary_header() from the revision standard's declared "
    "trace.data.format and read back by SegyFile._update_spec() on open"
)

_REV0_FORMAT = (
    "OPERATOR-SUPPLIED. SEG-Y rev 0 defines no mandatory sample-format field, so "
    "nothing in a rev 0 file is required to state the format. This fixture assumes "
    "ibm32 - the pinned segy rev 0 standard's own trace.data.format default - and "
    "supplies it by writing code 1 into binary header bytes 3225-3226 via "
    "SegyFactory.create_binary_header(). That is a choice made by the generator, not a "
    "fact read out of the revision, and SP1 requires it stated on the certificate."
)


@dataclass(frozen=True, slots=True)
class RevisionFixture:
    """A generated SEG-Y file, its revision facts, and the ground truth behind it."""

    path: Path
    revision: float | int
    inlines: tuple[int, ...]
    crosslines: tuple[int, ...]
    samples_per_trace: int
    sample_interval_us: int
    amplitudes: np.ndarray
    planted: np.ndarray
    textual_header: bytes
    binary_header: bytes
    sample_format: SampleFormatDeclaration
    geometry_declared_by_standard: bool
    base_field_count: int

    @property
    def trace_count(self) -> int:
        """Number of traces written."""
        return len(self.inlines) * len(self.crosslines)

    @property
    def byte_size(self) -> int:
        """Size of the written file."""
        return self.path.stat().st_size

    @property
    def geometry(self) -> tuple[tuple[int, int], ...]:
        """``(inline, crossline)`` per trace, in written order."""
        return tuple(
            (inline, crossline) for inline in self.inlines for crossline in self.crosslines
        )


def _geometry_values(inline: int, crossline: int) -> dict[str, int]:
    """The four geometry values for one trace. Identical across every revision."""
    return {
        "cdp_x": 1_000_000 + crossline * 25,
        "cdp_y": 2_000_000 + inline * 25,
        "inline": inline,
        "crossline": crossline,
    }


def make_revision_poststack3d(
    path: str | Path,
    *,
    revision: float | int,
    n_inline: int = 5,
    n_crossline: int = 6,
    n_samples: int = 32,
    inline_start: int = 100,
    crossline_start: int = 200,
    sample_interval_us: int = 4000,
    seed: int = DEFAULT_SEED,
    text: str = DETERMINISTIC_TEXT,
) -> RevisionFixture:
    """Write a deterministic synthetic 3D poststack SEG-Y of a given revision.

    Defaults reproduce the Appendix A.1 article shape for every revision: 5 inlines x
    6 crosslines x 32 samples = 30 traces.

    Geometry is written through named header fields where the revision declares them,
    and by raw byte offset where it does not — which is rev 0 and only rev 0. Both paths
    produce the same bytes at 181-196; :func:`read_geometry` reads them back with no
    spec involved, so the claim is evidence rather than assertion.

    Args:
        path: Where to write the file.
        revision: SEG-Y revision. ``0``, ``1``, ``2`` or ``2.1``.
        n_inline: Inline count.
        n_crossline: Crossline count.
        n_samples: Samples per trace.
        inline_start: First inline number.
        crossline_start: First crossline number.
        sample_interval_us: Sample interval in microseconds.
        seed: Seed for the planted header bytes. Fixed and committed.
        text: Textual header content. Defaults to the committed deterministic text;
            the upstream default embeds a timestamp and must never be used.

    Returns:
        The file plus the ground truth and revision facts it was built from.

    Raises:
        ValueError: If an encoded file header is not its mandated length.
    """
    target = Path(path)
    spec = get_segy_standard(revision)
    factory = SegyFactory(spec, sample_interval=sample_interval_us, samples_per_trace=n_samples)

    inlines = tuple(range(inline_start, inline_start + n_inline))
    crosslines = tuple(range(crossline_start, crossline_start + n_crossline))
    n_traces = n_inline * n_crossline

    amplitudes = _analytic_amplitudes(n_inline, n_crossline, n_samples)

    rng = np.random.default_rng(seed)
    planted = rng.integers(0, 256, size=(n_traces, len(PLANTED_BYTES)), dtype=np.uint8)

    headers = factory.create_trace_header_template(size=n_traces)
    samples = factory.create_trace_sample_template(size=n_traces)
    declared = set(headers.dtype.names or ())
    geometry_declared = GEOMETRY_BYTES.keys() <= declared

    index = 0
    for i, inline in enumerate(inlines):
        for j, crossline in enumerate(crosslines):
            if geometry_declared:
                for name, value in _geometry_values(inline, crossline).items():
                    headers[name][index] = value
            headers["coordinate_scalar"][index] = 1
            headers["trace_seq_num_line"][index] = index + 1
            samples[index] = amplitudes[i, j]
            index += 1

    textual_header = factory.create_textual_header(text)
    if len(textual_header) != TEXTUAL_HEADER_BYTES:
        msg = (
            f"textual header encoded to {len(textual_header)} bytes, must be "
            f"{TEXTUAL_HEADER_BYTES}. Upstream does not pad or validate: a short text "
            f"silently produces a malformed SEG-Y with every later offset wrong."
        )
        raise ValueError(msg)
    binary_header = factory.create_binary_header()
    if len(binary_header) != BINARY_HEADER_BYTES:  # pragma: no cover - upstream invariant
        msg = f"binary header encoded to {len(binary_header)} bytes, must be {BINARY_HEADER_BYTES}"
        raise ValueError(msg)

    payload = bytearray(factory.create_traces(headers, samples))
    stride = TRACE_HEADER_BYTES + n_samples * 4
    for trace, (inline, crossline) in enumerate((il, xl) for il in inlines for xl in crosslines):
        base = trace * stride
        if not geometry_declared:
            # rev 0 only. The bytes go where every later revision puts them; the rev 0
            # standard simply declines to name them.
            for name, value in _geometry_values(inline, crossline).items():
                start = base + GEOMETRY_BYTES[name] - 1
                payload[start : start + GEOMETRY_FIELD_BYTES] = value.to_bytes(
                    GEOMETRY_FIELD_BYTES, "big", signed=True
                )
        # Planted bytes 233-240, exactly as the Appendix A.1 article plants them.
        for k, byte_position in enumerate(PLANTED_BYTES):
            payload[base + byte_position - 1] = int(planted[trace, k])

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(textual_header + binary_header + bytes(payload))

    return RevisionFixture(
        path=target,
        revision=revision,
        inlines=inlines,
        crosslines=crosslines,
        samples_per_trace=n_samples,
        sample_interval_us=sample_interval_us,
        amplitudes=amplitudes,
        planted=planted,
        textual_header=textual_header,
        binary_header=binary_header,
        sample_format=SampleFormatDeclaration(
            scalar_type=str(spec.trace.data.format.value),
            declared_by_standard=revision != 0,
            supplied_via=_REV0_FORMAT if revision == 0 else _LATER_REVISION_FORMAT,
        ),
        geometry_declared_by_standard=geometry_declared,
        base_field_count=len(spec.trace.header.fields),
    )


def read_geometry(path: str | Path, n_traces: int, n_samples: int) -> dict[str, np.ndarray]:
    """Read the four geometry fields back out by raw byte offset, with no spec involved.

    Deliberately spec-free, for the same reason
    :func:`tests.fixtures.generators.poststack3d.read_planted` is: a reader that uses the
    spec under test cannot be evidence about that spec. This is what makes "the rev 0
    fixture does carry geometry at the canonical positions" a measurement rather than a
    claim.

    Args:
        path: The SEG-Y file.
        n_traces: Number of traces in the file.
        n_samples: Samples per trace.

    Returns:
        Field name to an ``int32`` array of one value per trace, in file order.
    """
    raw = Path(path).read_bytes()
    body = raw[TEXTUAL_HEADER_BYTES + BINARY_HEADER_BYTES :]
    stride = TRACE_HEADER_BYTES + n_samples * 4
    out = {name: np.zeros(n_traces, dtype=np.int32) for name in GEOMETRY_BYTES}
    for name, byte_position in GEOMETRY_BYTES.items():
        for trace in range(n_traces):
            start = trace * stride + byte_position - 1
            out[name][trace] = int.from_bytes(
                body[start : start + GEOMETRY_FIELD_BYTES], "big", signed=True
            )
    return out
