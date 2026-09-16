"""Plane 4's axis leg checks the axis the writer builds; disagreements are named findings.

**Maintainer ruling (DECISIONS.md D-0087), checked against SEG-Y and the industry.**

* **The oracle is the binary header.** Rev 1 marks bytes 3217-3218 *mandatory* and the
  trace-header interval (117-118) only *highly recommended*; rev 2.x says a fixed-length
  file's trace-header interval "is ignored". MDIO, segysak, OpenVDS, OpendTect and
  Madagascar all build the axis from the binary header. The verifier used the trace
  header instead, and failed every correct store whose trace headers carry 0 — which rev
  2.x defines as *unknown*, and which real files commonly carry.
* **A disagreeing trace-header interval is a finding, not a failure.**
* **A nonzero recording delay is a finding that blocks release.** Bytes 109-110 are the time
  from source initiation to the first sample. segyio, segysak, OpenVDS, OpendTect and
  Madagascar start the axis there; MDIO starts it at 0. The store is what MDIO wrote, so
  the verdict stands — but a reader would place every event at a different time than the
  store's axis says, so it cannot be released as-is.
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
def test_a_nonzero_delay_passes_the_plane_and_blocks_release(tmp_path, raw, scalar, effective):
    """Reported in true milliseconds: bytes 215-216 scale bytes 109-110 (0 means 1)."""
    result = _plane4(
        tmp_path, f"delay{raw}_{scalar}", delay_recording_time_ms=raw, times_scalar=scalar
    )
    assert result.status == "PASS"
    finding = _codes(result)["nonzero_recording_delay"]
    assert finding["blocks_release"] is True
    assert finding["delay_ms"] == [effective]


@pytest.mark.parametrize("interval_us", [500, 2500])
def test_an_interval_the_stored_axis_cannot_represent_still_fails(tmp_path, interval_us):
    """MDIO truncates the axis to int32 ms. 0.5 ms becomes 0; that store is wrong."""
    result = _plane4(tmp_path, f"sub{interval_us}", sample_interval_us=interval_us)
    assert result.status == "FAIL"
    assert result.evidence["derived_axis_identical"] is False
