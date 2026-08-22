"""MDIO to SEG-Y export and the round-trip driver.

Roadmap phase F3 (spec section 13). Not implemented at F0.

G3 passes only on sha256(export) == sha256(source) for the whole file.
"""

from __future__ import annotations

from sdip.errors import PhaseNotAuthorisedError

__all__ = ["PHASE", "not_yet"]

PHASE = "F3"


def not_yet(capability: str) -> PhaseNotAuthorisedError:
    """Return the error to raise for a capability that belongs to a later phase.

    SDIP refuses rather than returning a partial or unvalidated result.
    """
    return PhaseNotAuthorisedError(
        f"{capability} is roadmap phase F3 (spec section 13); "
        f"the repository is at F0. Nothing is stubbed out to look like it works."
    )
