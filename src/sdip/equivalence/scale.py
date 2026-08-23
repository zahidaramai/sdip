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
from typing import Any, Final

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


# --- The parametric wall-clock ceiling — OPEN_DEBTS D43, prereg P10 Amendment C -------

WALL_CEILING_BASE_S: Final[float] = 1350.0
"""Measured wall-clock bound for the full ``sdip certify`` chain at **16 controls**.

`max(N=5 runs) x 1.15`, rounded up to 50 s. The margin is **1.15**, taken from
``DECISIONS.md`` **D-0074**'s published 4.6 % run-to-run variance **before** the runs
that set this number — using experience to set a threshold is how any threshold is set;
using the result it judges is what **SP9** forbids.
"""

WALL_CEILING_REFERENCE_CONTROLS: Final[int] = 16
"""Control count the base was measured at. The parametric term corrects away from it."""

WALL_CEILING_PER_CONTROL_S: Final[float] = 44.92
"""Cost of one G7 control at survey scale.

Maximum across 3 chains and 45 applied control runs (**P10 Amendment B**), where controls
proved interchangeable at `max/min = 1.05`. The **maximum**, not the mean: a ceiling built
on the mean is breached by an unlucky ordering.
"""


def parametric_wall_ceiling(n_controls: int) -> float:
    """Wall-clock ceiling in seconds for a chain running ``n_controls`` G7 controls.

    **The debt this closes.** The ceiling was a bare constant. 900 s was correct at 10
    controls and wrong at 16, and the staleness surfaced as a **failed gate** rather than
    a warning (``OPEN_DEBTS`` D43, ``DECISIONS.md`` D-0073). Adding a control now adjusts
    the budget it consumes, so the number cannot rot while nobody is looking.

    **It does NOT become a default, and that is deliberate.** ``sdip certify`` still
    requires ``--wall-ceiling-s`` on the command line, because a ceiling this tool applied
    on its own behalf is not one anybody committed to (**SP9** — the same reasoning that
    keeps G5 ``NOT_RUN`` without an explicit ceiling). This is a **calculator an operator
    uses to declare a number**, not a number that declares itself.

    **It bounds one command, on one file, on one machine.** 494,565,408 bytes, 116,532
    traces, on the hardware P10 was measured on. It is **not** a model of a different
    file — the verification-memory envelope (``D38``) is a separate limit and is
    untouched by this.

    Args:
        n_controls: How many G7 controls the chain will run, normally
            ``len(sdip.equivalence.nonvacuity.CONTROLS)``.

    Returns:
        The ceiling in seconds.

    Raises:
        ValueError: If ``n_controls`` is negative.
    """
    if n_controls < 0:
        msg = f"n_controls must be non-negative, got {n_controls}"
        raise ValueError(msg)
    delta = n_controls - WALL_CEILING_REFERENCE_CONTROLS
    return WALL_CEILING_BASE_S + WALL_CEILING_PER_CONTROL_S * delta
