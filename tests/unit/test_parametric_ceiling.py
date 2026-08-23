"""The parametric wall-clock ceiling. `OPEN_DEBTS` D43, `prereg/P10` Amendment C."""

from __future__ import annotations

from pathlib import Path

import pytest

from sdip.equivalence.nonvacuity import CONTROLS
from sdip.equivalence.scale import (
    WALL_CEILING_BASE_S,
    WALL_CEILING_PER_CONTROL_S,
    WALL_CEILING_REFERENCE_CONTROLS,
    parametric_wall_ceiling,
)

# Every full-chain `sdip certify` wall clock ever recorded, N=5 (P10 Amendment C).
OBSERVED_S: tuple[float, ...] = (1168.55, 1115.27, 1111.72, 1116.15, 1119.15)


def test_it_bounds_every_run_ever_recorded():
    """The point of a ceiling: no run that legitimately happened may breach it.

    Two earlier derivations were **discarded** for failing exactly this — Amendment A
    computed 1,150 s and Amendment B 1,100 s, and both sit under the 1,168.55 s of a
    real certified run. A ceiling that fails a run which happened is not a ceiling; it
    is a regression waiting to be misread.
    """
    ceiling = parametric_wall_ceiling(len(CONTROLS))
    for observed in OBSERVED_S:
        assert observed <= ceiling, f"{observed}s breaches the {ceiling}s ceiling"


def test_the_base_matches_the_control_count_it_was_measured_at():
    """At the reference count the parametric term vanishes and the base stands alone."""
    assert parametric_wall_ceiling(WALL_CEILING_REFERENCE_CONTROLS) == WALL_CEILING_BASE_S
    assert len(CONTROLS) == WALL_CEILING_REFERENCE_CONTROLS, (
        "the control count moved; the base was measured at "
        f"{WALL_CEILING_REFERENCE_CONTROLS} and this test is the tripwire that says so"
    )


def test_adding_a_control_adds_its_measured_cost():
    """The whole debt, in one assertion.

    900 s was right at 10 controls and wrong at 16, and nothing noticed until a gate
    failed. The budget now moves with the work.
    """
    n = len(CONTROLS)
    assert parametric_wall_ceiling(n + 1) - parametric_wall_ceiling(n) == pytest.approx(
        WALL_CEILING_PER_CONTROL_S
    )
    assert parametric_wall_ceiling(n + 4) > parametric_wall_ceiling(n)


def test_it_retro_explains_why_the_original_900s_was_fragile():
    """P3 declared 900 s at 10 controls. The model says 10 controls need ~1,080 s.

    So that ceiling was **already under-provisioned when it was written** — which is why
    a modest growth in control count broke it rather than merely tightening it. The model
    is not just describing today; it accounts for the failure that motivated it.
    """
    assert parametric_wall_ceiling(10) > 900.0


def test_a_negative_control_count_is_refused_rather_than_returning_a_number():
    with pytest.raises(ValueError, match="non-negative"):
        parametric_wall_ceiling(-1)


def test_it_is_not_wired_in_as_a_default():
    """**SP9.** A ceiling this tool applies on its own behalf is not one anybody declared.

    `sdip certify` must still be given `--wall-ceiling-s`; this function is a calculator
    an operator uses to choose that number, not a number that chooses itself. If it ever
    becomes a default, G5 starts judging runs against a limit the tool invented.
    """
    # Read the file directly. `from sdip.cli import main` binds the FUNCTION, not the
    # module, so `.__file__` is not the CLI source - a trap this repository has hit twice.
    text = Path("src/sdip/cli/main.py").read_text(encoding="utf-8")
    assert "parametric_wall_ceiling" not in text, (
        "the CLI now references the calculator; if that is deliberate, it must still "
        "require an explicit --wall-ceiling-s rather than defaulting to it (SP9)"
    )
