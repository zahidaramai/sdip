"""Intake reader for OpenVDS: the host-side mapping, with the container probe replaced by fixtures.

The probe's real output on F3 sub-volumes is measured by P38; here each probe answer, good and bad,
must map to its own report. A test that runs the container is skipped when Docker or the image is
absent (it is not part of CI).
"""

from __future__ import annotations

import json
import re
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
    "integrity": {"checked": True, "exit": 0, "message": "", "regions": 3, "maxExtentEnd": 80},
}
SIZE = 80  # vds_file's length; GOOD's map ends exactly there


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
    assert rep["verdict"] == "NEEDS_INPUT"
    assert "SDIP_VDS_EXTENTS_INSIDE" in codes(rep)


TRUNCATION_CODES = {
    "SDIP_VDS_TRUNCATED",
    "SDIP_VDS_CONTAINER_INVALID",
    "SDIP_VDS_INTEGRITY_UNCHECKED",
}


@pytest.mark.parametrize("end", [1, 17, SIZE - 1, SIZE])
def test_a_map_inside_the_file_passes_the_check(tmp_path, validator, end):
    """Pass half (D-0088): every extent end from the first byte to the last is not a cut."""
    probe = GOOD | {"integrity": dict(GOOD["integrity"], maxExtentEnd=end)}
    rep = qc(vds_file(tmp_path / "c.vds"), probe)
    validator.validate(rep)
    assert rep["verdict"] == "NEEDS_INPUT"
    assert not codes(rep) & TRUNCATION_CODES


@pytest.mark.parametrize("end", [SIZE + 1, SIZE + 1000, 2 * SIZE, 1 << 40])
def test_a_map_past_the_end_is_truncated(tmp_path, validator, end):
    probe = GOOD | {"integrity": dict(GOOD["integrity"], maxExtentEnd=end)}
    rep = qc(vds_file(tmp_path / "c.vds"), probe)
    validator.validate(rep)
    assert rep["verdict"] == "QUARANTINE"
    assert codes(rep) & TRUNCATION_CODES == {"SDIP_VDS_TRUNCATED"}
    msg = next(f["message"] for f in rep["findings"] if f["code"] == "SDIP_VDS_TRUNCATED")
    assert f"{end - SIZE:,} missing" in msg


def test_a_failed_container_check_is_quarantined(tmp_path, validator):
    bad = {"checked": True, "exit": 1, "message": "Couldn't read index page", "regions": 0}
    rep = qc(vds_file(tmp_path / "c.vds"), GOOD | {"integrity": bad})
    validator.validate(rep)
    assert rep["verdict"] == "QUARANTINE"
    assert codes(rep) & TRUNCATION_CODES == {"SDIP_VDS_CONTAINER_INVALID"}


@pytest.mark.parametrize(
    "integ",
    [
        None,
        {"checked": False, "error": "TimeoutExpired"},
        {"checked": True, "exit": 0, "regions": 0, "maxExtentEnd": None},
        {"checked": True, "exit": 0, "regions": 1, "maxExtentEnd": True},
    ],
)
def test_no_check_is_not_a_pass(tmp_path, validator, integ):
    probe = {k: v for k, v in GOOD.items() if k != "integrity"}
    if integ is not None:
        probe["integrity"] = integ
    rep = qc(vds_file(tmp_path / "c.vds"), probe)
    validator.validate(rep)
    assert rep["verdict"] == "QUARANTINE"
    assert codes(rep) & TRUNCATION_CODES == {"SDIP_VDS_INTEGRITY_UNCHECKED"}


def test_an_unopenable_cut_file_carries_both_findings(tmp_path):
    bad = {"checked": True, "exit": 1, "message": "Couldn't read file table", "regions": 0}
    rep = qc(vds_file(tmp_path / "c.vds"), {"ok": False, "error": "x", "integrity": bad})
    assert {"SDIP_VDS_CONTAINER_INVALID", "HEADER_INVALID"} <= codes(rep)


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


CONTAINER_SKIP = pytest.mark.skipif(
    not _image_present(), reason="needs Docker and the sdip-intake-vds image (not in CI)"
)
REGION = re.compile(r"^(.*?)\s+size:\s*(\d+)\s+at offset:\s*(\d+)", re.MULTILINE)


@pytest.fixture(scope="module")
def synthetic_vds(tmp_path_factory):
    """A synthetic post-stack SEG-Y imported by OpenVDS's own SEGYImport, and its region map."""
    from tests.fixtures.generators.poststack3d import make_poststack3d

    root = tmp_path_factory.mktemp("vds")
    make_poststack3d(
        root / "s.sgy", n_inline=20, n_crossline=30, n_samples=200, sample_format="float32"
    )
    base = ["docker", "run", "--rm", "--platform", "linux/amd64", "--network", "none"]
    imp = ["-v", f"{root}:/w", "--entrypoint", "SEGYImport", IMAGE, "--vdsfile", "/w/s.vds"]
    subprocess.run(
        [*base, *imp, "/w/s.sgy"],
        capture_output=True,
        check=True,
    )
    check = subprocess.run(
        [*base, "-v", f"{root}:/in:ro", "--entrypoint", "HueBDS", IMAGE, "check", "/in/s.vds"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    regions = [(k.strip(), int(n), int(o)) for k, n, o in REGION.findall(check)]
    return root / "s.vds", regions


def cut_points(path: Path, regions: list) -> dict[str, int]:
    """Where to cut, from the file's own map.

    Inside the store header, the layout (the first chunk, offset 56), the file table, the largest
    index page, the largest data run, and one byte short of the end.
    """

    def mid(kind: str, *, largest: bool = False) -> int:
        cands = [r for r in regions if r[0].endswith(kind)]
        _k, n, o = max(cands, key=lambda r: r[1]) if largest else min(cands, key=lambda r: r[2])
        return o + n // 2

    return {
        "store header": mid("DataStoreHeader"),
        "layout": mid("chunk"),
        "file table": mid("FileTable"),
        "index page": mid("indexpage", largest=True),
        "data": mid("chunks", largest=True),
        "last byte": path.stat().st_size - 1,
    }


def intake(path: Path) -> dict:
    return qc_vds(path, upload_id=UPLOAD, member=path.name, sha256="0" * 64, commit=COMMIT).report  # type: ignore[return-value]


@CONTAINER_SKIP
def test_the_container_reads_an_intact_vds_as_whole(synthetic_vds, validator):
    """The control: OpenVDS's own import, uncut, is not quarantined and not called truncated."""
    path, regions = synthetic_vds
    assert max(o + n for _k, n, o in regions) == path.stat().st_size
    rep = intake(path)
    validator.validate(rep)
    assert rep["verdict"] == "NEEDS_INPUT"
    assert "SDIP_VDS_EXTENTS_INSIDE" in codes(rep)
    assert not codes(rep) & TRUNCATION_CODES


@CONTAINER_SKIP
@pytest.mark.parametrize(
    "where", ["store header", "layout", "file table", "index page", "data", "last byte"]
)
def test_the_container_catches_a_cut_vds(synthetic_vds, tmp_path, validator, where):
    path, regions = synthetic_vds
    at = cut_points(path, regions)[where]
    cut = tmp_path / "cut.vds"
    cut.write_bytes(path.read_bytes()[:at])
    rep = intake(cut)
    validator.validate(rep)
    assert rep["verdict"] == "QUARANTINE", (where, at, codes(rep))
    assert codes(rep) & {"SDIP_VDS_TRUNCATED", "SDIP_VDS_CONTAINER_INVALID"}, (where, at)
