"""The declared verification-memory envelope. `DECISIONS.md` D-0063 ruling 5, re-fitted by P26.

The constants are not free parameters: each is recomputed here from the committed
measurements, so a constant edited without a measurement fails.
"""

from __future__ import annotations

import math
import subprocess
import sys
from pathlib import Path

import numpy as np

from sdip.equivalence.envelope import (
    CEILING_GIB,
    DEFAULT_ENVELOPE_GIB,
    DEFAULT_INGEST_ENVELOPE_GIB,
    INGEST_MEASURED_POINTS,
    INGEST_RSS_INTERCEPT_MB,
    INGEST_RSS_SLOPE,
    MEASURED_POINTS,
    REASON_CODE,
    RSS_INTERCEPT_MB,
    RSS_SLOPE,
    envelope_refusal,
    ingest_envelope_refusal,
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


# --- the ingest envelope (D74, GeoSuite D-245) --------------------------------------------


def test_the_ingest_points_are_p23_and_p26s_receipts(repo_root):
    import json

    p23 = json.loads((repo_root / "prereg/P23-receipt-2026-11-01.json").read_text())["ingest"]
    p26 = json.loads((repo_root / "prereg/P26-receipt-2026-11-01.json").read_text())
    assert INGEST_MEASURED_POINTS == (
        (400_683_600, p23["small"]["peak_rss_bytes"]),
        (1_602_723_600, p23["large"]["peak_rss_bytes"]),
        (p26["fixture"]["bytes"], p26["ingest"]["peak_rss_bytes"]),
    )


def test_the_ingest_constants_are_the_least_squares_fit_of_its_points():
    x = np.array([s / 1e6 for s, _ in INGEST_MEASURED_POINTS])
    y = np.array([r / 1e6 for _, r in INGEST_MEASURED_POINTS])
    slope, intercept = np.polyfit(x, y, 1)
    assert round(float(slope), 4) == INGEST_RSS_SLOPE
    assert round(float(intercept), 1) == INGEST_RSS_INTERCEPT_MB


def test_the_ingest_default_is_where_its_line_reaches_the_ceiling_rounded_down():
    ceiling_mb = CEILING_GIB * 1024**3 / 1e6
    reach_gib = (ceiling_mb - INGEST_RSS_INTERCEPT_MB) / INGEST_RSS_SLOPE * 1e6 / 1024**3
    assert math.floor(reach_gib * 10) / 10 == DEFAULT_INGEST_ENVELOPE_GIB
    assert DEFAULT_INGEST_ENVELOPE_GIB < DEFAULT_ENVELOPE_GIB, "ingest binds first"


def test_the_ingest_refusal_states_its_fit(tmp_path):
    source = _sized(tmp_path / "big.sgy", int((DEFAULT_INGEST_ENVELOPE_GIB + 0.1) * 1024**3))
    message = ingest_envelope_refusal(source, envelope_gib=DEFAULT_INGEST_ENVELOPE_GIB)
    assert message is not None and message.startswith(REASON_CODE)
    assert "refusing to ingest" in message
    assert "measured at 0.4/1.6/4.8 GB, slope 1.028 MB/MB, intercept 0.58 GB" in message
    below = _sized(tmp_path / "ok.sgy", int((DEFAULT_INGEST_ENVELOPE_GIB - 0.1) * 1024**3))
    assert ingest_envelope_refusal(below, envelope_gib=DEFAULT_INGEST_ENVELOPE_GIB) is None
    assert ingest_envelope_refusal(source, envelope_gib=0) is None


def _sdip(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    exe = str(Path(sys.executable).with_name("sdip"))
    return subprocess.run(
        [exe, *args], capture_output=True, text=True, stdin=subprocess.DEVNULL, cwd=cwd
    )


def _refused_in_one_line(run: subprocess.CompletedProcess[str]) -> None:
    assert run.returncode == 1, run.stderr[-600:]
    assert run.stdout == ""
    assert "Traceback" not in run.stderr
    lines = [line for line in run.stderr.splitlines() if line.startswith("sdip: ")]
    assert len(lines) == 1 and "refusing to ingest" in lines[0], run.stderr[-600:]


def test_sdip_ingest_refuses_above_the_default_before_writing_anything(tmp_path):
    source = _sized(tmp_path / "big.sgy", int((DEFAULT_INGEST_ENVELOPE_GIB + 0.1) * 1024**3))
    run = _sdip("ingest", str(source), str(tmp_path / "store.mdio"))
    _refused_in_one_line(run)
    assert not (tmp_path / "store.mdio").exists()


def test_sdip_certify_refuses_above_the_default_before_ingesting(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    for args in (
        ["init", "-q"],
        ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "x"],
    ):
        subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)
    source = _sized(tmp_path / "big.sgy", int((DEFAULT_INGEST_ENVELOPE_GIB + 0.1) * 1024**3))
    out = tmp_path / "store.mdio"
    run = _sdip("certify", str(source), str(out), "--certificates", str(tmp_path / "c"), cwd=repo)
    _refused_in_one_line(run)
    assert not out.exists()
    assert not (tmp_path / "c").exists()
