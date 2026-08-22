"""The Equivalence Engine: five plane checkers, gates G1-G7, certificate issuance.

Roadmap phase F3 (spec section 13). Not implemented at F0.

Comparisons are array_equal or byte equality. There is no tolerance anywhere in this package - a
tolerance-based comparison is a specification defect (spec 4.5, 9.5).
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
