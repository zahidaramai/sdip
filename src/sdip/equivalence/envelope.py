"""The declared verification-memory envelope, and the refusal above it.

**Why a refusal rather than a bigger machine.** Above some source size `sdip verify` would
need more memory than the declared 8 GiB ceiling, and a process that runs out of memory is
killed and returns **no verdict at all**. A tool that dies is worse than a tool that
declines, so `verify` refuses above a declared envelope, cites the measurement, and exits
non-zero with a reason code (``DECISIONS.md`` D-0063 ruling 5).

**How large that is was re-measured after verification stopped reading whole files.**
Until P23 the planes read the source and the store whole, and memory grew at 7.73 MB per MB
of source (D-0060). The envelope was then 1.0 GiB. P23 and P24 made Planes 3 and 4 read
block by block, and P26 measured the result at three sizes (``OPEN_DEBTS`` D38, GeoSuite
D-244). Memory now grows at about 0.18 MB per MB above a fixed 0.92 GB.

**The envelope is a declaration, not a discovery.** It is not tuned to the machine it runs
on and does not probe available memory: a limit that moves with the host is not a limit
anybody can reproduce from the committed record.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

MEASURED_POINTS: Final[tuple[tuple[int, int], ...]] = (
    (400_683_600, 1_012_170_752),
    (1_602_723_600, 1_175_601_152),
    (4_808_163_600, 1_783_169_024),
)
"""``(source bytes, peak RSS bytes)`` of ``sdip verify`` (probes P24 stage B and P26).

One synthetic poststack family, ``ibm32``, 630 crosslines by 1,000 samples, macOS arm64,
``verify --skip-portability``. Peak RSS is ``/usr/bin/time -l``'s maximum resident set size.
"""

RSS_INTERCEPT_MB: Final[float] = 919.6
RSS_SLOPE: Final[float] = 0.1779
"""``RSS_MB = 919.6 + 0.1779 x source_MB``: ordinary least squares over the three
:data:`MEASURED_POINTS`, in MB of 10^6 bytes, R² = 0.996 (P26)."""

CEILING_GIB: Final[float] = 8.0
"""The declared memory ceiling the envelope keeps `verify` under."""

DEFAULT_ENVELOPE_GIB: Final[float] = 40.1
"""Largest single source file `sdip verify` will attempt, in GiB.

The size at which the fitted line reaches the 8 GiB ceiling (43,116 MB, 40.15 GiB), rounded
**down** to one decimal so the default stays on the safe side of the line (P26). It is an
extrapolation: nothing above 4.8 GB has been measured.

**Override it explicitly and the refusal lifts**; there is no clamp. An operator who
knows their machine has the memory may say so, and the number they pass is recorded.
"""

REASON_CODE: Final[str] = "SDIP-E-ENVELOPE"
"""Stable reason code. Refusals carry one so a caller can branch on it, not on prose."""


def projected_peak_rss_mb(source_bytes: int) -> float:
    """Projected peak RSS in MB for verifying a source of this size."""
    return RSS_INTERCEPT_MB + RSS_SLOPE * (source_bytes / 1e6)


def envelope_refusal(source: str | Path, *, envelope_gib: float) -> str | None:
    """Return the refusal message, or ``None`` when the file is inside the envelope.

    Args:
        source: The SEG-Y file about to be verified.
        envelope_gib: The declared envelope. ``0`` or negative disables the check
            entirely, which is an explicit operator decision and is not second-guessed.

    Returns:
        A message naming the code, the sizes and the measurement, or ``None``.
    """
    if envelope_gib <= 0:
        return None
    size = Path(source).stat().st_size
    limit = int(envelope_gib * 1024**3)
    if size <= limit:
        return None
    return (
        f"{REASON_CODE}: refusing to verify a {size / 1024**3:.2f} GiB source against a "
        f"declared {envelope_gib:.2f} GiB envelope. Verification memory was measured at "
        f"0.4/1.6/4.8 GB, slope {RSS_SLOPE:.3f} MB/MB, intercept {RSS_INTERCEPT_MB / 1000:.2f} GB "
        f"(probe P26, DECISIONS.md D-0129), so this file projects to roughly "
        f"{projected_peak_rss_mb(size) / 1024:.1f} GiB against the {CEILING_GIB:.1f} GiB "
        "ceiling. Refusing is deliberate: a process that runs out of memory is killed and "
        "returns NO verdict, which is worse than declining to start. Pass --envelope-gib "
        "to declare a larger one, or 0 to disable."
    )


# --- The ingest envelope (OPEN_DEBTS D74, D76; P28, P32, P33; DECISIONS.md D-0136, D-0137) ----

INGEST_BOUND_POINTS: Final[tuple[tuple[int, int], ...]] = (
    (400_683_600, 1_001_734_144),
    (1_602_723_600, 874_266_624),
)
"""``(source bytes, peak RSS bytes)`` of the whole ``sdip ingest`` after P28
(``prereg/P28-receipt-2026-11-05.json``, stage B). The bound's fixed term is taken from these
two points, which still carried the header term, so it overestimates (SP9: written before P33's
gate)."""

INGEST_TRACE_MAP_TERM: Final[float] = 0.0871
"""MB of peak RSS per MB of source: the trace map built from the header columns, the one part
of ingest that still grows with the file once the headers are read in blocks (P33 stage A)."""

INGEST_FIXED_TERM_MB: Final[float] = 966.83
"""The larger of ``peak - INGEST_TRACE_MAP_TERM x size`` over :data:`INGEST_BOUND_POINTS`."""

INGEST_MARGIN: Final[float] = 1.10
"""A margin on the memory ceiling, fixed in the registrations. Not a tolerance on any value."""

INGEST_MEASURED_AFTER_P33: Final[tuple[tuple[int, int], ...]] = (
    (400_683_600, 816_381_952),
    (1_602_723_600, 1_023_246_336),
    (14_424_483_600, 2_065_203_200),
)
"""The whole ``sdip ingest`` at P33's stage B code. The last is P33's gate: 14.4 GB, never
ingested before the bound was written, 2,065.2 MB against 2,445.5
(``prereg/P33-receipt-2026-11-05.json``)."""

DEFAULT_INGEST_ENVELOPE_GIB: Final[float] = DEFAULT_ENVELOPE_GIB
"""Largest single source file `sdip ingest` and `sdip certify` will attempt, in GiB.

The bound ``1.10 x (966.83 + 0.0871 x size)`` reaches the 8 GiB ceiling only at 73.1 GiB, so the
default is **capped at verify's** :data:`DEFAULT_ENVELOPE_GIB` (40.1 GiB): ``certify`` runs both,
and an ingest envelope above verify's admits nothing more to it (P33 amendment B). Above 14.4 GB
it rests on the bound, not on a measurement. Override it with ``--envelope-gib``, or pass 0 to
disable it."""


def projected_ingest_peak_rss_mb(source_bytes: int) -> float:
    """The bound on peak RSS in MB for ingesting a source of this size (P33)."""
    return INGEST_MARGIN * (INGEST_FIXED_TERM_MB + INGEST_TRACE_MAP_TERM * (source_bytes / 1e6))


def ingest_envelope_refusal(source: str | Path, *, envelope_gib: float) -> str | None:
    """Return the ingest refusal message, or ``None`` when the file is inside the envelope.

    Args:
        source: The SEG-Y file about to be ingested.
        envelope_gib: The declared envelope. ``0`` or negative disables the check.

    Returns:
        A message naming the code, the sizes and the measurement, or ``None``.
    """
    if envelope_gib <= 0:
        return None
    size = Path(source).stat().st_size
    if size <= int(envelope_gib * 1024**3):
        return None
    return (
        f"{REASON_CODE}: refusing to ingest a {size / 1024**3:.2f} GiB source against a "
        f"declared {envelope_gib:.2f} GiB envelope. Ingest memory is bounded by "
        f"{INGEST_MARGIN:.2f} x ({INGEST_FIXED_TERM_MB:.0f} MB + "
        f"{INGEST_TRACE_MAP_TERM:.4f} MB/MB), from P28 and P33; held at 14.4 GB (P33; "
        "OPEN_DEBTS D76, DECISIONS.md D-0137), so this file "
        f"is bounded at roughly {projected_ingest_peak_rss_mb(size) / 1024:.1f} GiB "
        f"against the {CEILING_GIB:.1f} GiB ceiling. Refusing is deliberate: a process that "
        "runs out of memory is killed and returns NO result, which is worse than declining "
        "to start. Pass --envelope-gib to declare a larger one, or 0 to disable."
    )
