"""Gap-free SegySpec generator, survey overrides, and gate G1.

Builds a trace-header spec covering bytes 1-240 with zero gaps and zero overlaps,
emitting one ``uint8`` filler per uncovered byte (**SP4**, **SP5**). **G1** asserts the
result before any trace is read.

Roadmap phase F1 (spec §13). Survey overrides (§6.4) are not built.
"""

from __future__ import annotations

from sdip.spec.coverage import (
    ALL_BYTES,
    Coverage,
    FieldExtent,
    compute_coverage,
    declared_field_bytes,
    dtype_has_void_gaps,
    format_itemsize,
)
from sdip.spec.gate import Condition, G1Result, g1, g1_for_spec
from sdip.spec.generator import (
    FILLER_PREFIX,
    SUPPORTED_REVISIONS,
    GapFreeSpec,
    build_gap_free_spec,
    filler_fields,
)

__all__ = [
    "ALL_BYTES",
    "FILLER_PREFIX",
    "SUPPORTED_REVISIONS",
    "Condition",
    "Coverage",
    "FieldExtent",
    "G1Result",
    "GapFreeSpec",
    "build_gap_free_spec",
    "compute_coverage",
    "declared_field_bytes",
    "dtype_has_void_gaps",
    "filler_fields",
    "format_itemsize",
    "g1",
    "g1_for_spec",
]
