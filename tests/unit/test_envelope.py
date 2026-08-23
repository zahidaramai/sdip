"""The declared verification-memory envelope. `DECISIONS.md` D-0063 ruling 5."""

from __future__ import annotations

from pathlib import Path

from sdip.equivalence.envelope import (
    DEFAULT_ENVELOPE_GIB,
    REASON_CODE,
    envelope_refusal,
    projected_peak_rss_mb,
)


def _sized(path: Path, size: int) -> Path:
    """A sparse file of exactly ``size`` bytes. The check reads the SIZE, never content."""
    with path.open("wb") as handle:
        handle.truncate(size)
    return path


def test_a_file_inside_the_envelope_is_not_refused(tmp_path):
    assert envelope_refusal(_sized(tmp_path / "s.sgy", 1024), envelope_gib=1.0) is None


def test_a_file_above_the_envelope_is_refused_with_a_stable_reason_code(tmp_path):
    """A caller must be able to branch on the CODE, not on the prose."""
    source = _sized(tmp_path / "big.sgy", int(2.5 * 1024**3))
    message = envelope_refusal(source, envelope_gib=1.0)
    assert message is not None
    assert message.startswith(REASON_CODE)
    # it cites the measurement rather than asserting a limit
    assert "R^2 = 0.99997" in message
    assert "D-0060" in message
    # and it names the escape hatch, so refusing is not a dead end
    assert "--envelope-gib" in message


def test_zero_disables_the_check_because_that_is_an_operator_decision(tmp_path):
    """There is no clamp. An operator who knows their machine may say so."""
    source = _sized(tmp_path / "huge.sgy", (50 * 1024**3))
    assert envelope_refusal(source, envelope_gib=0) is None
    assert envelope_refusal(source, envelope_gib=-1) is None


def test_the_default_envelope_sits_below_the_measured_breach_range(tmp_path):
    """The number sits under a range the measurements do not agree on.

    D-0060 bracketed the breach of a declared 8 GiB ceiling between **1,083 MB** (the
    synthetic fit) and **1,393 MB** (anchored on the single real survey point). A default
    set inside a range where two measurements disagree would be a guess wearing a number.
    """
    assert DEFAULT_ENVELOPE_GIB * 1024**3 < 1_083 * 1e6, "must sit under BOTH estimates"


def test_the_projection_reproduces_the_one_real_measurement_conservatively():
    """The fit over-predicts the real point, and that direction is the safe one.

    494,565,408 B was observed at **2.81-2.87 GiB**. The fit projects higher. An
    under-prediction would let a file through that then OOMs, which is the failure this
    envelope exists to prevent — so the fit is used as the conservative side of a
    bracket, never as a point estimate.
    """
    observed_gib_high = 2.87
    projected_gib = projected_peak_rss_mb(494_565_408) / 1024
    assert projected_gib > observed_gib_high, "an under-prediction would defeat the point"
    assert projected_gib < 2 * observed_gib_high, "but it must not be wild"
