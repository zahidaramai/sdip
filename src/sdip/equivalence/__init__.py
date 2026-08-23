"""The Equivalence Engine: plane checkers, gates G1-G7, certificate issuance.

Comparisons are array_equal or byte equality. **There is no tolerance anywhere in
this package** - a tolerance-based comparison is a specification defect (§4.5, §9.5).

**All seven gates exist and run**: the five planes (G2a-G2e), G3 round trip, G4
portability, G5 declared-ceiling cost, G6 determinism, and G7 non-vacuity.

**G5 is the one gate that stays NOT_RUN by default**, and deliberately: it judges a
run against a ceiling somebody committed to beforehand, so a default ceiling would be
a limit this package invented (SP9). Declare one on the command line to arm it.

A gate is **never assumed to pass**. NOT_RUN is recorded as NOT_RUN on the face of the
certificate, and ``release_readiness`` treats every NOT_RUN as blocking - so an unarmed
gate cannot be mistaken for a passing one (D-0031, OPEN_DEBTS.md D20).
"""

from __future__ import annotations

from sdip.equivalence.certificate import (
    GATES,
    PLANE_KEYS,
    Certificate,
    issue,
    read_codec_manifest,
    release_readiness,
    verdict_for,
)
from sdip.equivalence.nonvacuity import (
    ALL_GATES,
    CONTROLS,
    Corruption,
    G7Result,
    g3_control,
    g7,
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
from sdip.equivalence.scale import G5Result, g5
from sdip.equivalence.trace_map import TraceMap, build_trace_map

__all__ = [
    "ALL_GATES",
    "CONTROLS",
    "GATES",
    "PLANE_KEYS",
    "Certificate",
    "Corruption",
    "G5Result",
    "G7Result",
    "PlaneResult",
    "PortabilityResult",
    "TraceMap",
    "build_trace_map",
    "first_difference",
    "g3_control",
    "g4",
    "g5",
    "g7",
    "issue",
    "plane_1",
    "plane_2",
    "plane_3",
    "plane_4",
    "plane_5",
    "read_codec_manifest",
    "release_readiness",
    "verdict_for",
]
