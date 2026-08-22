"""Gap-free SegySpec generator, survey overrides, and gate G1.

Roadmap phase F1 (spec section 13). Not implemented at F0.

Builds a trace-header spec covering bytes 1-240 with zero gaps and zero overlaps, emitting one
uint8 filler per uncovered byte (SP4, SP5). G1 asserts the result before any trace is read.
"""

from __future__ import annotations

from sdip.errors import PhaseNotAuthorisedError

__all__ = ["PHASE", "not_yet"]

PHASE = "F1"


def not_yet(capability: str) -> PhaseNotAuthorisedError:
    """Return the error to raise for a capability that belongs to a later phase.

    SDIP refuses rather than returning a partial or unvalidated result.
    """
    return PhaseNotAuthorisedError(
        f"{capability} is roadmap phase F1 (spec section 13); "
        f"the repository is at F0. Nothing is stubbed out to look like it works."
    )
