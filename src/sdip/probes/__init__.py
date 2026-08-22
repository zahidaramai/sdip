"""Pre-registered probes. Specification §8, **SP9**.

A probe is not a gate. A gate says whether one store is sound; a probe asks whether a
property the specification *assumes* is actually true, and it is registered — criteria,
parameters, seed and falsifier committed — **before** it runs. Nothing in this package
may be tuned after a result. If a measurement contradicts the pre-registration, the
pre-registration wins and the contradiction is the finding.
"""

from __future__ import annotations

from sdip.probes.ibm32 import (
    DEFAULT_SEED,
    FALSIFIER,
    FIXED_MANTISSAS,
    PREREGISTRATION,
    PROBE_ID,
    REGIME_WORDS,
    FailingWord,
    SweepResult,
    WordPlan,
    build_word_plan,
    classify_failure,
    ibm32_roundtrip_sweep,
    mantissa_set,
    sweep_words,
)

__all__ = [
    "DEFAULT_SEED",
    "FALSIFIER",
    "FIXED_MANTISSAS",
    "PREREGISTRATION",
    "PROBE_ID",
    "REGIME_WORDS",
    "FailingWord",
    "SweepResult",
    "WordPlan",
    "build_word_plan",
    "classify_failure",
    "ibm32_roundtrip_sweep",
    "mantissa_set",
    "sweep_words",
]
