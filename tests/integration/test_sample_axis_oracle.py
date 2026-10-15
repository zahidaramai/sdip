"""Plane 4's axis leg checks the axis the writer builds; disagreements are named findings.

**Maintainer ruling (DECISIONS.md D-0087), checked against SEG-Y and the industry.**

* **The oracle is the binary header.** Rev 1 marks bytes 3217-3218 *mandatory* and the
  trace-header interval (117-118) only *highly recommended*; rev 2.x says a fixed-length
  file's trace-header interval "is ignored". MDIO, segysak, OpenVDS, OpendTect and
  Madagascar all build the axis from the binary header. The verifier used the trace
  header instead, and failed every correct store whose trace headers carry 0 — which rev
  2.x defines as *unknown*, and which real files commonly carry.
* **A disagreeing trace-header interval is a finding, not a failure.**
* **A recording delay starts the axis there, where it is exact (D-0096).** Bytes 109-110 are
  the time from source initiation to the first sample, and segyio, segysak, OpenVDS,
  OpendTect and Madagascar start the axis there; MDIO starts it at 0. Until D-0096 every
  nonzero delay was a finding that blocked release. Now ``sdip ingest`` starts the axis at a
  constant, whole-millisecond delay and Plane 4 verifies it against the source; a varying or
  fractional delay, or a depth axis, is still that blocking finding
  (``test_recording_delay_axis.py``).
* **Sub-millisecond intervals still fail.** MDIO stores the axis as int32 milliseconds and
  truncates 0.5 ms to 0; that store is genuinely wrong.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from sdip.equivalence.planes import plane_4
from sdip.ingest import ingest
from sdip.spec import build_gap_free_spec
from tests.fixtures.generators.irregular import make_irregular

PAIRS = [(100 + i, 200 + j) for i in range(3) for j in range(4)]


def _plane4(tmp_path: Path, name: str, **kwargs: object):  # noqa: ANN202
    fixture = make_irregular(tmp_path / f"{name}.sgy", index_pairs=PAIRS, **kwargs)
    store = tmp_path / f"{name}.mdio"
    ingest(fixture.path, store)
    return plane_4(fixture.path, store, build_gap_free_spec(1).segy_spec)


def _codes(result) -> dict[str, dict]:
    return {f["code"]: f for f in result.evidence.get("findings", [])}


def test_a_conformant_file_passes_with_no_findings(tmp_path):
    result = _plane4(tmp_path, "plain")
    assert result.status == "PASS", result.evidence.get("derived_axis_first_difference")
    assert result.evidence["derived_axis_identical"] is True
    assert _codes(result) == {}


def test_a_zero_trace_header_interval_passes_and_is_named(tmp_path):
    """D47's plane 4 'failure'. Zero means unknown (rev 2.x §3.3); the binary header decides."""
    result = _plane4(tmp_path, "zero", trace_sample_interval_us=0)
    assert result.status == "PASS", result.evidence.get("derived_axis_first_difference")
    finding = _codes(result)["trace_interval_unspecified"]
    assert finding["blocks_release"] is False


def test_a_differing_trace_header_interval_passes_and_is_named(tmp_path):
    result = _plane4(tmp_path, "differ", trace_sample_interval_us=2000)
    assert result.status == "PASS"
    assert _codes(result)["trace_interval_differs"]["blocks_release"] is False


@pytest.mark.parametrize(
    ("raw", "scalar", "effective"), [(100, 0, 100.0), (1000, -10, 100.0), (25, 4, 100.0)]
)
def test_a_constant_delay_starts_the_axis_in_true_milliseconds(tmp_path, raw, scalar, effective):
    """Bytes 215-216 scale bytes 109-110 (0 means 1). D-0096: the axis starts there, verified.

    Until D-0096 this asserted the blocking finding with ``delay_ms == [effective]``; the same
    arithmetic now has to land the stored axis exactly on the effective delay.
    """
    result = _plane4(
        tmp_path, f"delay{raw}_{scalar}", delay_recording_time_ms=raw, times_scalar=scalar
    )
    assert result.status == "PASS", result.evidence.get("derived_axis_first_difference")
    assert result.evidence["derived_axis_origin_ms"] == effective
    assert "nonzero_recording_delay" not in _codes(result)


@pytest.mark.parametrize("interval_us", [500, 2500])
def test_an_interval_the_stored_axis_cannot_represent_still_fails(tmp_path, interval_us):
    """MDIO truncates the axis to int32 ms. 0.5 ms becomes 0; that store is wrong."""
    result = _plane4(tmp_path, f"sub{interval_us}", sample_interval_us=interval_us)
    assert result.status == "FAIL"
    assert result.evidence["derived_axis_identical"] is False


@pytest.mark.parametrize("interval_us", [1000, 2000, 3000, 8000, 16000, 32000])
def test_every_whole_millisecond_interval_passes(tmp_path, interval_us):
    """Specificity sweep (D52): correct stores pass at every whole-millisecond interval.

    Those are the intervals the stored int32 millisecond axis can represent - not only 4 ms.
    """
    result = _plane4(tmp_path, f"ms{interval_us}", sample_interval_us=interval_us)
    assert result.status == "PASS", result.evidence.get("derived_axis_first_difference")
    assert result.evidence["derived_axis_identical"] is True
