"""Thin orchestration over the MDIO converter.

Roadmap phase F2 (spec section 13). Not implemented at F0.

Every entry point that can trigger ingestion must sit behind an if __name__ == '__main__' guard:
MDIO's header parser uses a spawn context (spec 11.1).
"""

from __future__ import annotations

from sdip.errors import PhaseNotAuthorisedError

__all__ = ["PHASE", "not_yet"]

PHASE = "F2"


def not_yet(capability: str) -> PhaseNotAuthorisedError:
    """Return the error to raise for a capability that belongs to a later phase.

    SDIP refuses rather than returning a partial or unvalidated result.
    """
    return PhaseNotAuthorisedError(
        f"{capability} is roadmap phase F2 (spec section 13); "
        f"the repository is at F0. Nothing is stubbed out to look like it works."
    )
