"""**G1 — spec completeness.** Pre-flight, before any I/O. Specification §7 G1.

    PASS iff declared byte coverage == {1..240}, itemsize == 240, zero overlaps,
    zero void gaps.
    Kills it: any uncovered or doubly-covered byte.
    A failing G1 aborts ingestion before a single trace is read.

Four independent conditions, evaluated and reported **independently**. A gate that
collapses them into one boolean can tell you it failed but not what to fix, and — worse
— an over-broad check that fails everything on any defect cannot localise a fault and
gets silenced the first time it fires on something benign (**SP11**, G7's *"only its
gate"* clause applied one level down).

G1 takes fields, not a generator output, so it can judge a spec SDIP did not build: a
survey override (§6.4), a hand-written spec, a spec from a future upstream. **A gate
that can only assess its own output is not a gate.**
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from sdip._pins import SEGY_TRACE_HEADER_BYTES
from sdip.errors import SpecCompletenessError
from sdip.spec.coverage import (
    Coverage,
    HeaderFieldLike,
    compute_coverage,
    declared_field_bytes,
    dtype_has_void_gaps,
)


@dataclass(frozen=True, slots=True)
class Condition:
    """One of G1's four conditions, with the number that decided it."""

    name: str
    passed: bool
    detail: str

    def to_json(self) -> dict[str, Any]:
        """Certificate-shaped mapping."""
        return {"condition": self.name, "passed": self.passed, "detail": self.detail}


@dataclass(slots=True)
class G1Result:
    """The verdict of G1, and the evidence for it."""

    conditions: list[Condition] = field(default_factory=list)
    coverage: Coverage | None = None

    @property
    def failed(self) -> list[Condition]:
        """Conditions that did not hold."""
        return [c for c in self.conditions if not c.passed]

    @property
    def passed(self) -> bool:
        """True only when every condition holds. Gates are binary (§7)."""
        return bool(self.conditions) and not self.failed

    @property
    def status(self) -> str:
        """``"PASS"`` or ``"FAIL"``, for the certificate ``gates`` block."""
        return "PASS" if self.passed else "FAIL"

    def summary(self) -> str:
        """One line naming what killed it, or what held."""
        if self.passed:
            covered = len(self.coverage.covered) if self.coverage else 0
            fields_n = self.coverage.field_count if self.coverage else 0
            return (
                f"G1 PASS: {fields_n} fields cover bytes 1-{covered} with no gaps, "
                f"no overlaps, no void padding"
            )
        return "G1 FAIL: " + "; ".join(c.detail for c in self.failed)

    def to_json(self) -> dict[str, Any]:
        """Certificate-shaped mapping. This is G1's evidence on the certificate."""
        return {
            "gate": "G1",
            "status": self.status,
            "summary": self.summary(),
            "conditions": [c.to_json() for c in self.conditions],
            "coverage": self.coverage.to_json() if self.coverage else None,
        }

    def raise_for_status(self) -> None:
        """Raise :class:`SpecCompletenessError` if G1 did not pass.

        A failing G1 aborts ingestion **before a single trace is read**, so the error
        carries the full condition breakdown rather than a bare boolean.
        """
        if not self.passed:
            raise SpecCompletenessError(self.summary())


def g1(fields: Iterable[HeaderFieldLike], *, dtype: np.dtype[Any] | None = None) -> G1Result:
    """Run G1 against a declared field set.

    Args:
        fields: The trace-header fields the spec declares.
        dtype: The structured dtype the spec resolves to, when available. Without it
            the itemsize and void-gap conditions cannot be evaluated and are reported
            as failures rather than skipped — G1 is pre-flight for an ingestion, and
            "could not check" is not "fine".

    Returns:
        The verdict with all four conditions reported independently.
    """
    coverage = compute_coverage(fields, itemsize=int(dtype.itemsize) if dtype is not None else None)
    result = G1Result(coverage=coverage)

    runs = coverage.uncovered_runs()
    result.conditions.append(
        Condition(
            name="coverage",
            passed=not coverage.uncovered,
            detail=(
                f"bytes 1-{SEGY_TRACE_HEADER_BYTES} fully covered"
                if not coverage.uncovered
                else f"{len(coverage.uncovered)} uncovered byte(s): "
                + ", ".join(f"{a}" if a == b else f"{a}-{b}" for a, b in runs)
            ),
        )
    )

    result.conditions.append(
        Condition(
            name="no-overlaps",
            passed=not coverage.overlaps,
            detail=(
                "no byte is claimed twice"
                if not coverage.overlaps
                else f"{len(coverage.overlaps)} doubly-covered byte(s): "
                + ", ".join(f"{o.byte} by {'+'.join(o.fields)}" for o in coverage.overlaps[:5])
            ),
        )
    )

    if coverage.out_of_range:
        result.conditions.append(
            Condition(
                name="in-range",
                passed=False,
                detail=(
                    f"{len(coverage.out_of_range)} field(s) fall outside bytes "
                    f"1-{SEGY_TRACE_HEADER_BYTES}: "
                    + ", ".join(str(e) for e in coverage.out_of_range[:5])
                ),
            )
        )
    else:
        result.conditions.append(
            Condition(
                name="in-range",
                passed=True,
                detail=f"every field lies within bytes 1-{SEGY_TRACE_HEADER_BYTES}",
            )
        )

    if dtype is None:
        result.conditions.append(
            Condition(
                name="itemsize",
                passed=False,
                detail="no dtype supplied; itemsize could not be checked",
            )
        )
        result.conditions.append(
            Condition(
                name="no-void-gaps",
                passed=False,
                detail="no dtype supplied; numpy void padding could not be checked",
            )
        )
        return result

    itemsize = int(dtype.itemsize)
    result.conditions.append(
        Condition(
            name="itemsize",
            passed=itemsize == SEGY_TRACE_HEADER_BYTES,
            detail=(
                f"dtype itemsize is {itemsize}"
                if itemsize == SEGY_TRACE_HEADER_BYTES
                else f"dtype itemsize is {itemsize}, must be {SEGY_TRACE_HEADER_BYTES}"
            ),
        )
    )

    has_voids = dtype_has_void_gaps(dtype)
    result.conditions.append(
        Condition(
            name="no-void-gaps",
            passed=not has_voids,
            detail=(
                "no numpy void padding between fields"
                if not has_voids
                else (
                    "numpy inserted void padding: declared field widths sum to "
                    f"{declared_field_bytes(dtype)} "
                    f"but itemsize is {itemsize}. Those bytes are addressable by no "
                    "field and would be unrecoverable — a Plane 3 failure that looks "
                    "like success"
                )
            ),
        )
    )
    return result


def g1_for_spec(spec: Any) -> G1Result:
    """Run G1 against a :class:`~sdip.spec.generator.GapFreeSpec` or a raw SegySpec."""
    header = getattr(spec, "segy_spec", spec).trace.header
    return g1(header.fields, dtype=header.dtype)
