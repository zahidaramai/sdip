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
        f"{projected_peak_rss_mb(size) / 1024:.1f} GiB against a {CEILING_GIB:.1f} GiB "
        "ceiling. Refusing is deliberate: a process that runs out of memory is killed and "
        "returns NO verdict, which is worse than declining to start. Pass --envelope-gib "
        "to declare a larger one, or 0 to disable."
    )
