"""The declared verification-memory envelope, and the refusal above it.

**Why a refusal rather than a bigger machine.** The verification path fully materialises:
``planes.py`` reads whole arrays, and Plane 4 holds the source samples **and** the store
volume at once. Peak RSS is therefore **linear in file size**, not in a chunk working
set — measured, ``R² = 0.99997`` over four runs from 51 MB to 403 MB (``DECISIONS.md``
D-0060). Streaming comparison would fix it, and it is a design lock, deliberately
deferred (``OPEN_DEBTS`` D38, D23).

Until it lands, a large file does not fail gracefully — it **OOMs**, which on most
machines means the process is killed and the operator gets no verdict at all. **A tool
that dies is worse than a tool that declines**, because a death leaves nothing to read.
So `sdip verify` refuses above a declared envelope, cites the measurement, and exits
non-zero with a reason code (``DECISIONS.md`` D-0063 ruling 5).

**The envelope is a declaration, not a discovery.** It is not tuned to the machine it
runs on and does not probe available memory: a limit that moves with the host is not a
limit anybody can reproduce from the committed record.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

RSS_INTERCEPT_MB: Final[float] = 214.7
RSS_SLOPE: Final[float] = 7.73
"""``RSS_MB = 214.7 + 7.73 x source_MB``, least squares over N=4, R² = 0.99997.

Measured on synthetic stores of 51-403 MB (D-0060). The fit **over-predicts the one real
survey data point by 32 %** — 494.6 MB observed at ~3,049 MB where the fit says ~4,040 —
so it is used as the CONSERVATIVE side of a bracket, never as a point estimate.
"""

DEFAULT_ENVELOPE_GIB: Final[float] = 1.0
"""Largest single source file `sdip verify` will attempt, in GiB.

**Chosen below the measured breach range of 1.08-1.39 GB**, not inside it. The two
estimates disagree — the synthetic fit says a declared 8 GiB ceiling breaches at
**1,083 MB**, anchoring on the single real point says **1,393 MB** — and a limit set
inside a range the measurements do not agree on would be a guess wearing a number.
1.0 GiB is under both.

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
        f"declared {envelope_gib:.2f} GiB envelope. The verification path fully "
        f"materialises, so peak RSS is LINEAR in file size - measured "
        f"RSS_MB = {RSS_INTERCEPT_MB:.1f} + {RSS_SLOPE:.2f} x source_MB, R^2 = 0.99997 "
        f"(DECISIONS.md D-0060). This file projects to roughly "
        f"{projected_peak_rss_mb(size) / 1024:.1f} GiB. Refusing is deliberate: above the "
        "envelope the process is killed and you get NO verdict, which is worse than "
        "declining to start. Streaming comparison is the fix and is deferred "
        "(OPEN_DEBTS D38). Pass --envelope-gib to declare a larger one, or 0 to disable."
    )
