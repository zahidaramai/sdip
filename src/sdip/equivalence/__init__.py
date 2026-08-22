"""The Equivalence Engine: plane checkers, gates G1-G7, certificate issuance.

Comparisons are array_equal or byte equality. **There is no tolerance anywhere in
this package** - a tolerance-based comparison is a specification defect (§4.5, §9.5).

Phase F3 implements **all five planes** (G2a-G2e), **G3** round trip, and **G4**
portability. **G5, G6 and G7 do not exist** and are recorded NOT_RUN - never assumed
to pass. Until G7 passes, every certificate this engine issues is unvalidated
(OPEN_DEBTS.md D11).
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
from sdip.equivalence.planes import (
    PlaneResult,
    first_difference,
    plane_1,
    plane_2,
    plane_3,
    plane_4,
    plane_5,
)
from sdip.equivalence.portability import PortabilityResult, g4
from sdip.equivalence.trace_map import TraceMap, build_trace_map

__all__ = [
    "GATES",
    "PLANE_KEYS",
    "Certificate",
    "PlaneResult",
    "PortabilityResult",
    "TraceMap",
    "build_trace_map",
    "first_difference",
    "g4",
    "issue",
    "plane_1",
    "plane_2",
    "plane_3",
    "plane_4",
    "plane_5",
    "read_codec_manifest",
    "verdict_for",
]
