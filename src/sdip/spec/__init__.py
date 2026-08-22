"""Gap-free SegySpec generator, survey overrides, and gate G1.

Builds a trace-header spec covering bytes 1-240 with zero gaps and zero overlaps,
emitting one ``uint8`` filler per uncovered byte (**SP4**, **SP5**). **G1** asserts the
result before any trace is read.

Survey overrides (§6.4) rename and retype bytes that base spec already covered, from
committed TOML carrying cited evidence. They change labels and numeric interpretation,
never byte content — re-verified by Plane 3 (**G2c**) on every ingest.

Roadmap phase F1 (spec §13).
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
from sdip.spec.overrides import (
    ENDIANNESS_INFER,
    ENDIANNESS_VALUES,
    EVIDENCE_MIN_CHARS,
    OverrideField,
    SurveyOverride,
    SurveyOverrideError,
    apply_override,
    load_override,
    parse_override,
)

__all__ = [
    "ALL_BYTES",
    "ENDIANNESS_INFER",
    "ENDIANNESS_VALUES",
    "EVIDENCE_MIN_CHARS",
    "FILLER_PREFIX",
    "SUPPORTED_REVISIONS",
    "Condition",
    "Coverage",
    "FieldExtent",
    "G1Result",
    "GapFreeSpec",
    "OverrideField",
    "SurveyOverride",
    "SurveyOverrideError",
    "apply_override",
    "build_gap_free_spec",
    "compute_coverage",
    "declared_field_bytes",
    "dtype_has_void_gaps",
    "filler_fields",
    "format_itemsize",
    "g1",
    "g1_for_spec",
    "load_override",
    "parse_override",
]
