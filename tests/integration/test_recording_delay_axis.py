"""The stored time axis starts at the recording delay when SDIP can say so exactly (D-0096).

**The passing half (D-0088), through the ``sdip`` executable.** A sweep of correct sources
across the values the rule computes with - positive and negative delays, a scalar that
multiplies and one that divides, two sample intervals - must each ingest to an axis that
starts at the delay, record the origin in the marker, and verify with Plane 4 PASS and no
``nonzero_recording_delay`` finding. ``certify`` on one of them must be release-ready.

**Where the rule must NOT apply**, the axis stays as the writer built it, nothing is recorded,
and the blocking finding stands: a delay that varies across traces, one that is not a whole
number of milliseconds, and a depth axis. A zero delay changes nothing at all.

The failing half is ``tests/negative/test_axis_origin_controls.py``.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import zarr

from sdip.ingest.provenance_marker import ATTR_SAMPLE_AXIS_ORIGIN
from tests.fixtures.generators.poststack3d import make_poststack3d

pytestmark = pytest.mark.integration

SDIP = str(Path(sys.executable).parent / "sdip")
N_TRACES = 5 * 6
N_SAMPLES = 32


def _run(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [SDIP, *args], capture_output=True, text=True, check=False, cwd=cwd, timeout=900
    )


def _ingest(tmp_path: Path, name: str, *extra: str, **fixture: Any) -> tuple[Path, Path]:
    source = make_poststack3d(tmp_path / f"{name}.sgy", **fixture).path
    store = tmp_path / f"{name}.mdio"
    proc = _run("ingest", str(source), str(store), *extra)
    assert proc.returncode == 0, proc.stderr[-2000:]
    return source, store


def _verify(source: Path, store: Path, *extra: str) -> dict:
    proc = _run("verify", "--skip-portability", "--json", str(source), str(store), *extra)
    assert "Traceback" not in proc.stderr, proc.stderr[-2000:]
    report = json.loads(proc.stdout)
    report["returncode"] = proc.returncode
    return report


def _codes(report: dict) -> list[str]:
    return [f["code"] for f in report["planes"]["plane_4"]["evidence"].get("findings") or []]


@pytest.mark.parametrize(
    ("delay", "scalar", "interval_us", "origin_ms"),
    [
        (4, 0, 4000, 4.0),
        (100, 0, 4000, 100.0),
        (-8, 0, 4000, -8.0),
        (2, 2, 4000, 4.0),
        (8, -2, 4000, 4.0),
        (6, 0, 2000, 6.0),
    ],
)
def test_a_constant_exact_delay_starts_the_axis_there(
    tmp_path, delay, scalar, interval_us, origin_ms
):
    source, store = _ingest(
        tmp_path,
        "delayed",
        delay_recording_time=delay,
        times_scalar=scalar,
        sample_interval_us=interval_us,
    )
    group = zarr.open_group(str(store), mode="r")
    expected = origin_ms + np.arange(N_SAMPLES) * interval_us / 1000
    assert np.array_equal(np.asarray(group["time"][:], dtype=np.float64), expected)
    assert dict(group.attrs)[ATTR_SAMPLE_AXIS_ORIGIN]["origin_ms"] == origin_ms

    report = _verify(source, store)
    assert report["returncode"] == 0, report["planes"]["plane_4"]["evidence"]
    assert report["planes"]["plane_4"]["status"] == "PASS"
    assert "nonzero_recording_delay" not in _codes(report)
    assert report["planes"]["plane_4"]["evidence"]["derived_axis_origin_ms"] == origin_ms


def test_a_zero_delay_changes_nothing(tmp_path):
    source, store = _ingest(tmp_path, "zero")
    group = zarr.open_group(str(store), mode="r")
    assert ATTR_SAMPLE_AXIS_ORIGIN not in dict(group.attrs)
    assert group["time"][0] == 0
    report = _verify(source, store)
    assert report["returncode"] == 0
    assert _codes(report) == []


@pytest.mark.parametrize(
    ("label", "fixture", "extra", "reason"),
    [
        (
            "varying",
            {"delay_recording_time": tuple([4] * (N_TRACES - 1) + [8])},
            (),
            "varies across traces",
        ),
        ("fractional", {"delay_recording_time": 3, "times_scalar": -2}, (), "not exactly"),
        (
            "depth",
            {"delay_recording_time": 4},
            ("--template", "PostStack3DDepth"),
            "applied to time",
        ),
    ],
)
def test_where_the_rule_does_not_apply_the_axis_and_the_finding_stand(
    tmp_path, label, fixture, extra, reason
):
    source, store = _ingest(tmp_path, label, *extra, **fixture)
    group = zarr.open_group(str(store), mode="r")
    assert ATTR_SAMPLE_AXIS_ORIGIN not in dict(group.attrs)
    report = _verify(source, store, *extra)
    plane_4 = report["planes"]["plane_4"]
    assert plane_4["status"] == "PASS", plane_4["evidence"]
    assert plane_4["evidence"]["derived_axis_origin_ms"] == 0.0
    [finding] = [
        f for f in plane_4["evidence"]["findings"] if f["code"] == "nonzero_recording_delay"
    ]
    assert finding["blocks_release"] is True
    assert reason in finding["message"]


def test_certify_a_delayed_survey_is_release_ready(tmp_path):
    """The request's whole point: convert once, prove once, release - through ``certify``."""
    source = make_poststack3d(tmp_path / "certify.sgy", delay_recording_time=4).path
    repo = tmp_path / "repo"
    repo.mkdir()
    for args in (
        ["init", "-q"],
        ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "i"],
    ):
        subprocess.run(["git", *args], cwd=repo, check=True)
    certs = tmp_path / "certs"
    proc = _run(
        "certify",
        str(source),
        str(tmp_path / "cert.mdio"),
        "--rss-ceiling-gib",
        "8.0",
        "--wall-ceiling-s",
        "1800",
        "--certificates",
        str(certs),
        cwd=repo,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr[-2000:]
    [certificate] = list(certs.glob("*.json"))
    payload = json.loads(certificate.read_text())
    assert payload["gates"]["G3"] == "PASS"
    assert payload["roundtrip_closure"]["status"] == "PASS", payload["roundtrip_closure"]
    assert payload["planes"]["plane_4"]["evidence"]["derived_axis_origin_ms"] == 4.0
    assert payload["store_digest"]["status"] == "MATCH"
    readiness = payload["release_readiness"]
    assert readiness["blocking"] == [], readiness["blocking"]
    assert readiness["release_ready"] is True
