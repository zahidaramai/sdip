"""**Gate G5 — scale.** Specification §7 G5, §11.2, probe **P3**.

    PASS iff ingestion completes at declared survey scale within a declared memory
    ceiling with no unbounded growth, and G2 holds on a pre-registered random trace
    sample plus all edge traces.
    Kills it: OOM, or peak RSS exceeding the declared ceiling.

**G5 is the only gate that cannot be evaluated from the store alone.** Every other gate
asks a question about an artifact that exists; G5 asks what the *run* cost, and a run
that already finished has taken its measurements or lost them. So this gate does not
measure anything itself — it **judges measurements the run supplied** against ceilings
that were **declared beforehand**.

That ordering is the whole of **SP9**, and it is why the ceiling is a required argument
with no default. A default would be a threshold chosen by whoever wrote this file, at a
time when nobody knew what the answer would be — which is the good case — but it would
also be a threshold nobody committed to before the run, which is the case that matters.
``prereg/P3-scale.md`` carries the ceilings for this project, timestamped by the commit
that added them.

**Sampling.** §7 G5 permits a pre-registered random sample plus all edge traces. SDIP's
planes are **exhaustive** — every trace, every field, every sample — so the sample *is*
the population and no sampling scheme is needed. The gate records that rather than
claiming a sample it did not draw.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

GIB = 1024**3


@dataclass(slots=True)
class G5Result:
    """Whether a completed run stayed inside its declared ceilings."""

    declared_rss_ceiling_bytes: int
    declared_wall_ceiling_s: float
    peak_rss_bytes: int
    wall_clock_s: float
    trace_count: int
    planes_passed: bool
    prereg_reference: str
    unbounded_growth_observed: bool = False
    findings: list[str] = field(default_factory=list)

    @property
    def rss_breach(self) -> bool:
        """True when peak RSS exceeded the declared ceiling."""
        return self.peak_rss_bytes > self.declared_rss_ceiling_bytes

    @property
    def wall_breach(self) -> bool:
        """True when wall clock exceeded the declared ceiling."""
        return self.wall_clock_s > self.declared_wall_ceiling_s

    @property
    def passed(self) -> bool:
        """True only when the run completed inside every declared ceiling."""
        return not (
            self.rss_breach
            or self.wall_breach
            or self.unbounded_growth_observed
            or not self.planes_passed
        )

    @property
    def status(self) -> str:
        """``"PASS"`` or ``"FAIL"``."""
        return "PASS" if self.passed else "FAIL"

    def summary(self) -> str:
        """One line naming what killed it, or what held."""
        if self.passed:
            return (
                f"G5 PASS: {self.trace_count:,} traces, peak RSS "
                f"{self.peak_rss_bytes / GIB:.2f} GiB of "
                f"{self.declared_rss_ceiling_bytes / GIB:.1f} GiB declared, "
                f"{self.wall_clock_s:.0f}s of {self.declared_wall_ceiling_s:.0f}s"
            )
        reasons = []
        if self.rss_breach:
            reasons.append(
                f"peak RSS {self.peak_rss_bytes / GIB:.2f} GiB exceeded the declared "
                f"{self.declared_rss_ceiling_bytes / GIB:.1f} GiB"
            )
        if self.wall_breach:
            reasons.append(
                f"wall clock {self.wall_clock_s:.0f}s exceeded the declared "
                f"{self.declared_wall_ceiling_s:.0f}s"
            )
        if self.unbounded_growth_observed:
            reasons.append("RSS trended upward with trace index rather than plateauing")
        if not self.planes_passed:
            reasons.append("a plane failed at scale")
        return "G5 FAIL: " + "; ".join(reasons)

    def to_json(self) -> dict[str, Any]:
        """Certificate-shaped mapping."""
        return {
            "gate": "G5",
            "status": self.status,
            "summary": self.summary(),
            "trace_count": self.trace_count,
            "peak_rss_bytes": self.peak_rss_bytes,
            "declared_rss_ceiling_bytes": self.declared_rss_ceiling_bytes,
            "wall_clock_s": self.wall_clock_s,
            "declared_wall_ceiling_s": self.declared_wall_ceiling_s,
            "rss_breach": self.rss_breach,
            "wall_breach": self.wall_breach,
            "unbounded_growth_observed": self.unbounded_growth_observed,
            "planes_passed": self.planes_passed,
            "sampling": "exhaustive - every trace, every field, every sample",
            "prereg": self.prereg_reference,
            "findings": list(self.findings),
            "note": (
                "Ceilings are DECLARED BEFORE THE RUN (SP9) and are a required argument "
                "with no default. A threshold nobody committed to beforehand is not a "
                "threshold. This gate judges measurements the run supplied; it does not "
                "take them."
            ),
        }


def g5(
    *,
    peak_rss_bytes: int,
    wall_clock_s: float,
    trace_count: int,
    planes_passed: bool,
    declared_rss_ceiling_bytes: int,
    declared_wall_ceiling_s: float,
    prereg_reference: str,
    unbounded_growth_observed: bool = False,
    findings: list[str] | None = None,
) -> G5Result:
    """Judge a completed survey-scale run against its pre-declared ceilings.

    Every ceiling is keyword-only and required. There is no default, because a default
    would be a threshold this file chose rather than one the operator committed to
    before the run (**SP9**).

    Args:
        peak_rss_bytes: Peak resident set size observed during the run.
        wall_clock_s: Wall clock for the run.
        trace_count: Traces ingested.
        planes_passed: Whether every plane passed at this scale.
        declared_rss_ceiling_bytes: The ceiling, declared beforehand.
        declared_wall_ceiling_s: The ceiling, declared beforehand.
        prereg_reference: Where the ceilings were declared, e.g. a path and commit.
        unbounded_growth_observed: Whether RSS trended upward with trace index.
        findings: Anything else worth recording on the certificate.

    Returns:
        The gate result.
    """
    return G5Result(
        declared_rss_ceiling_bytes=declared_rss_ceiling_bytes,
        declared_wall_ceiling_s=declared_wall_ceiling_s,
        peak_rss_bytes=peak_rss_bytes,
        wall_clock_s=wall_clock_s,
        trace_count=trace_count,
        planes_passed=planes_passed,
        prereg_reference=prereg_reference,
        unbounded_growth_observed=unbounded_growth_observed,
        findings=list(findings or []),
    )
