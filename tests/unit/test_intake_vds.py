"""Intake reader for OpenVDS: the host-side mapping, with the container probe replaced by fixtures.

The probe's real output on F3 sub-volumes is measured by P38; here each probe answer, good and bad,
must map to its own report. A test that runs the container is skipped when Docker or the image is
absent (it is not part of CI).
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from sdip.intake.vds import IMAGE, qc_vds

SCHEMA = Path(__file__).resolve().parents[1] / "contracts" / "geosuite.intake.v1.schema.json"
UPLOAD = "u-20261116-0123456789ab"
COMMIT = "0123456789abcdef0123456789abcdef01234567"
GOOD = {
    "ok": True,
    "dimensionality": 3,
    "axes": [
        {"name": "Sample", "unit": "ms", "samples": 462, "min": 4.0, "max": 1848.0},
        {"name": "Crossline", "unit": "unitless", "samples": 300, "min": 300.0, "max": 599.0},
        {"name": "Inline", "unit": "unitless", "samples": 200, "min": 100.0, "max": 299.0},
    ],
    "channels": [{"name": "Amplitude", "format": "VolumeDataFormat.Format_R32"}],
    "crsWkt": None,
    "origin": [1.0, 2.0],
    "unit": "m",
    "compression": "None",
    "lossy": False,
}


def vds_file(path: Path) -> Path:
    path.write_bytes(b"HueDataStore\x00\x00\x01\x00" + bytes(64))
    return path


def qc(path: Path, probe: dict, **kw: object) -> dict:
    return qc_vds(
        path,
        upload_id=UPLOAD,
        member=path.name,
        sha256="0" * 64,
        commit=COMMIT,
        runner=lambda _p: probe,
        **kw,
    ).report  # type: ignore[arg-type]


@pytest.fixture(scope="module")
def validator():
    jsonschema = pytest.importorskip("jsonschema")
    return jsonschema.Draft202012Validator(
        json.loads(SCHEMA.read_text()), format_checker=jsonschema.FormatChecker()
    )


def codes(rep: dict) -> set[str]:
    return set(rep["structural"]["codes"])


def test_layout_maps_to_a_poststack_report(tmp_path, validator):
    rep = qc(vds_file(tmp_path / "c.vds"), GOOD)
    validator.validate(rep)
    st = rep["structural"]
    assert (st["format"], st["domain"], st["hasUnits"], st["hasCrs"]) == (
        "vds-3d-poststack",
        "time",
        True,
        False,
    )
    assert (st["counts"]["inlines"], st["counts"]["crosslines"], st["counts"]["samples"]) == (
        200,
        300,
        462,
    )
    assert [q["code"] for q in rep["questions"]] == ["CRS_UNRESOLVED"]
    assert "SDIP_VDS_INTEGRITY_UNCHECKED" in codes(rep)


def test_wkt_is_a_candidate(tmp_path):
    rep = qc(vds_file(tmp_path / "c.vds"), GOOD | {"crsWkt": 'PROJCS["ED50 / UTM zone 31N"]'})
    assert rep["questions"][0]["choices"][0]["source"] == "VDS SurveyCoordinateSystem CRSWkt"
    assert rep["structural"]["hasCrs"] is True


def test_depth_and_unknown_units(tmp_path):
    depth = [dict(GOOD["axes"][0], unit="m"), *GOOD["axes"][1:]]
    assert (
        qc(vds_file(tmp_path / "d.vds"), GOOD | {"axes": depth})["structural"]["domain"] == "depth"
    )
    odd = [dict(GOOD["axes"][0], unit="unitless"), *GOOD["axes"][1:]]
    rep = qc(vds_file(tmp_path / "u.vds"), GOOD | {"axes": odd})
    assert "DOMAIN_UNKNOWN" in {q["code"] for q in rep["questions"]}


def test_lossy_compression_is_reported(tmp_path):
    assert "SDIP_VDS_LOSSY" in codes(
        qc(vds_file(tmp_path / "c.vds"), GOOD | {"lossy": True, "compression": "Wavelet"})
    )


def test_unopenable_file_is_quarantined(tmp_path, validator):
    rep = qc(vds_file(tmp_path / "c.vds"), {"ok": False, "error": "ReadErrorException: bad layout"})
    validator.validate(rep)
    assert rep["verdict"] == "QUARANTINE"
    assert "HEADER_INVALID" in codes(rep)


def test_no_container_is_not_a_pass(tmp_path, validator):
    rep = qc(vds_file(tmp_path / "c.vds"), {"ok": False, "unavailable": "docker is not installed"})
    validator.validate(rep)
    assert rep["verdict"] == "QUARANTINE"
    assert "SDIP_VDS_READER_UNAVAILABLE" in codes(rep)


def test_not_vds_is_refused(tmp_path):
    p = tmp_path / "c.vds"
    p.write_bytes(b"nothing like it" * 10)
    assert qc(p, GOOD)["verdict"] == "REFUSED"


def test_cluster_derived_is_refused_before_the_container(tmp_path):
    called = []
    rep = qc_vds(
        vds_file(tmp_path / "c.vds"),
        upload_id=UPLOAD,
        member="c.vds",
        sha256="0" * 64,
        commit=COMMIT,
        cls="cluster-derived",
        runner=lambda p: called.append(p) or GOOD,
    ).report
    assert rep["verdict"] == "REFUSED"
    assert not called


def _image_present() -> bool:
    if shutil.which("docker") is None:
        return False
    return (
        subprocess.run(
            ["docker", "image", "inspect", IMAGE], capture_output=True, check=False
        ).returncode
        == 0
    )


@pytest.mark.skipif(
    not _image_present(), reason="needs Docker and the sdip-intake-vds image (not in CI)"
)
def test_the_container_refuses_garbage_cleanly(tmp_path):
    from sdip.intake.vds import docker_runner

    out = docker_runner(vds_file(tmp_path / "garbage.vds"))
    assert out["ok"] is False
    assert "error" in out and "unavailable" not in out  # OpenVDS ran and refused it
