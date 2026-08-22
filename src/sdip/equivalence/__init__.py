"""The Equivalence Engine: plane checkers, gates G1-G7, certificate issuance.

Comparisons are array_equal or byte equality. **There is no tolerance anywhere in
this package** - a tolerance-based comparison is a specification defect (§4.5, §9.5).

Phase F2 implements Planes 1 and 2 (gates G2a, G2b) and certificate v0. Planes 3, 4 and
5, and gates G3-G7, are phase F3-F4 and are **not stubbed**: they do not exist, so a
caller gets an error rather than a plausible-looking PASS for a check that never ran.
"""

from __future__ import annotations

from sdip.equivalence.certificate import (
    GATES,
    PLANE_KEYS,
    Certificate,
    issue,
    read_codec_manifest,
    verdict_for,
)
from sdip.equivalence.planes import PlaneResult, first_difference, plane_1, plane_2

__all__ = [
    "GATES",
    "PLANE_KEYS",
    "Certificate",
    "PlaneResult",
    "first_difference",
    "issue",
    "plane_1",
    "plane_2",
    "read_codec_manifest",
    "verdict_for",
]
