"""The declared verification-memory envelope. `DECISIONS.md` D-0063 ruling 5, re-fitted by P26.

The constants are not free parameters: each is recomputed here from the committed
measurements, so a constant edited without a measurement fails.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np

from sdip.equivalence.envelope import (
    CEILING_GIB,
    DEFAULT_ENVELOPE_GIB,
    MEASURED_POINTS,
    REASON_CODE,
    RSS_INTERCEPT_MB,
    RSS_SLOPE,
    envelope_refusal,
    projected_peak_rss_mb,
)


def _sized(path: Path, size: int) -> Path:
    """A sparse file of exactly ``size`` bytes. The check reads the SIZE, never content."""
    with path.open("wb") as handle:
        handle.truncate(size)
    return path


def _fit() -> tuple[float, float]:
    x = np.array([s / 1e6 for s, _ in MEASURED_POINTS])
    y = np.array([r / 1e6 for _, r in MEASURED_POINTS])
    slope, intercept = np.polyfit(x, y, 1)
    return float(slope), float(intercept)


def test_the_points_are_p24_and_p26s_receipts(repo_root):
    import json

    p24 = json.loads((repo_root / "prereg/P24-receipt-2026-11-01.json").read_text())
    p26 = json.loads((repo_root / "prereg/P26-receipt-2026-11-01.json").read_text())
    stage_b = p24["stage_b"]["whole_verify_peak_rss_bytes"]
    assert MEASURED_POINTS == (
        (400_683_600, stage_b["small"]),
        (1_602_723_600, stage_b["large"]),
        (p26["fixture"]["bytes"], p26["verify"]["peak_rss_bytes"]),
    )


def test_the_constants_are_the_least_squares_fit_of_the_points():
    slope, intercept = _fit()
    assert round(slope, 4) == RSS_SLOPE
    assert round(intercept, 1) == RSS_INTERCEPT_MB


def test_the_default_is_where_the_line_reaches_the_ceiling_rounded_down():
    reach_gib = (CEILING_GIB * 1024**3 / 1e6 - RSS_INTERCEPT_MB) / RSS_SLOPE * 1e6 / 1024**3
    assert math.floor(reach_gib * 10) / 10 == DEFAULT_ENVELOPE_GIB
    assert projected_peak_rss_mb(int(DEFAULT_ENVELOPE_GIB * 1024**3)) <= CEILING_GIB * 1024**3 / 1e6


def test_the_line_does_not_under_predict_any_point_by_much():
    """A projection far under a measured peak would let a file through that then dies."""
    for size, peak in MEASURED_POINTS:
        assert projected_peak_rss_mb(size) >= 0.9 * peak / 1e6, (size, peak)


def test_a_file_inside_the_envelope_is_not_refused(tmp_path):
    assert envelope_refusal(_sized(tmp_path / "s.sgy", 1024), envelope_gib=1.0) is None


def test_a_file_above_the_envelope_is_refused_with_a_stable_reason_code(tmp_path):
    """A caller must be able to branch on the CODE, not on the prose."""
    source = _sized(tmp_path / "big.sgy", int(2.5 * 1024**3))
    message = envelope_refusal(source, envelope_gib=1.0)
    assert message is not None
    assert message.startswith(REASON_CODE)
    # it states the fit rather than asserting a limit (GeoSuite D-244)
    assert "measured at 0.4/1.6/4.8 GB, slope 0.178 MB/MB, intercept 0.92 GB" in message
    assert "P26" in message
    # and it names the escape hatch, so refusing is not a dead end
    assert "--envelope-gib" in message


def test_the_default_refuses_above_it_and_admits_below_it(tmp_path):
    above = _sized(tmp_path / "above.sgy", int((DEFAULT_ENVELOPE_GIB + 0.1) * 1024**3))
    below = _sized(tmp_path / "below.sgy", int((DEFAULT_ENVELOPE_GIB - 0.1) * 1024**3))
    assert envelope_refusal(above, envelope_gib=DEFAULT_ENVELOPE_GIB) is not None
    assert envelope_refusal(below, envelope_gib=DEFAULT_ENVELOPE_GIB) is None


def test_zero_disables_the_check_because_that_is_an_operator_decision(tmp_path):
    """There is no clamp. An operator who knows their machine may say so."""
    source = _sized(tmp_path / "huge.sgy", (50 * 1024**3))
    assert envelope_refusal(source, envelope_gib=0) is None
    assert envelope_refusal(source, envelope_gib=-1) is None
