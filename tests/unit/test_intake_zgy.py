"""Intake reader for ZGY: both halves on synthetic files written by the layout OpenZGY documents.

The writer below lays out version-3 files exactly as OpenZGY's ``meta.py`` describes them; P37
checked the reader against OpenZGY's own reader on public and generated files.
"""

from __future__ import annotations

import hashlib
import json
import struct
from pathlib import Path

import pytest

from sdip.intake import qc_file
from sdip.intake.zgy import HIST_BYTES, INFO_FORMAT, lod_sizes, lut_offsets

SCHEMA = Path(__file__).resolve().parents[1] / "contracts" / "geosuite.intake.v1.schema.json"
UPLOAD = "u-20261116-0123456789ab"
COMMIT = "0123456789abcdef0123456789abcdef01234567"


def write_zgy(
    path: Path,
    *,
    size: tuple[int, int, int] = (70, 40, 30),
    datatype: int = 6,
    vdim: int = 2,
    hdim: int = 1,
    projection: str = "ED50 / UTM zone 31N",
    corners: tuple[tuple[float, float], ...] = ((0, 0), (1000, 0), (0, 500), (1000, 500)),
    hole: bool = False,
    cut: int = 0,
    version: int = 3,
) -> Path:
    brick = (64, 64, 64)
    width = {0: 1, 2: 2, 6: 4}[datatype]
    strings = b"\x00".join([b"", b"", projection.encode(), b"m", b"ms"]) + b"\x00"
    xs = [c[0] for c in corners]
    ys = [c[1] for c in corners]
    info = struct.pack(
        INFO_FORMAT,
        *brick,
        datatype,
        0.0,
        1.0,
        bytes(16),
        bytes(16),
        bytes(16),
        datatype,
        100.0,
        300.0,
        0.0,
        1.0,
        1.0,
        4.0,
        *size,
        0,
        0,
        0,
        *size,
        0,
        0.0,
        0.0,
        0.0,
        0.0,
        0.0,
        0.0,
        0.0,
        0.0,
        0.0,
        0.0,
        3,
        0.0,
        0.0,
        0.0,
        0.0,
        100.0,
        100.0 + size[0] - 1,
        100.0,
        100.0 + size[0] - 1,
        300.0,
        300.0,
        300.0 + size[1] - 1,
        300.0 + size[1] - 1,
        *xs,
        *ys,
        hdim,
        1.0,
        vdim,
        0.001,
        len(strings),
    )
    lods = lod_sizes(size, brick)
    alpha = lut_offsets(lods, True)
    bricks = lut_offsets(lods, False)
    header = b"VBS\x00" + struct.pack("<I", version) + b"\x00" + info + strings + bytes(HIST_BYTES)
    header += bytes(8 * alpha[-1])
    lut_at = len(header)
    first = lut_at + 8 * bricks[-1]
    brick_bytes = 64 * 64 * 64 * width
    entries = [first + i * brick_bytes for i in range(bricks[-1])]
    if hole:
        entries[bricks[0]] = 0
    body = header + struct.pack(f"<{len(entries)}Q", *entries) + bytes(brick_bytes * len(entries))
    path.write_bytes(body[: len(body) - cut] if cut else body)
    return path


def qc(path: Path, **kw: object) -> dict:
    return qc_file(path, upload_id=UPLOAD, member=path.name, commit=COMMIT, **kw).report  # type: ignore[arg-type]


@pytest.fixture(scope="module")
def validator():
    jsonschema = pytest.importorskip("jsonschema")
    assert hashlib.sha256(SCHEMA.read_bytes()).hexdigest().startswith("f0a3e47a")
    return jsonschema.Draft202012Validator(
        json.loads(SCHEMA.read_text()), format_checker=jsonschema.FormatChecker()
    )


def codes(rep: dict) -> set[str]:
    return set(rep["structural"]["codes"])


@pytest.mark.parametrize("datatype", [0, 2, 6])
def test_correct_cubes_pass_without_quarantine(tmp_path, validator, datatype):
    rep = qc(write_zgy(tmp_path / "cube.zgy", datatype=datatype))
    validator.validate(rep)
    assert rep["structural"]["format"] == "zgy-3d-poststack"
    assert rep["structural"]["domain"] == "time"
    assert rep["structural"]["counts"]["bricks"] == 2
    assert not [f for f in rep["findings"] if f["severity"] in ("quarantine", "refuse")]
    assert [q["code"] for q in rep["questions"]] == [
        "CRS_UNRESOLVED"
    ]  # domain and units are stated


def test_projection_is_a_candidate_not_a_choice(tmp_path):
    rep = qc(write_zgy(tmp_path / "cube.zgy"))
    crs = rep["questions"][0]
    assert crs["choices"][0] == {
        "id": "cand0",
        "label": "ED50 / UTM zone 31N",
        "source": "ZGY projection string",
    }
    assert "UTM" not in json.dumps(rep["structural"])


def test_depth_cube_reports_depth(tmp_path):
    assert qc(write_zgy(tmp_path / "c.zgy", vdim=1))["structural"]["domain"] == "depth"


def test_unknown_domain_and_units_are_asked(tmp_path, validator):
    rep = qc(write_zgy(tmp_path / "c.zgy", vdim=0, hdim=0))
    validator.validate(rep)
    assert {"DOMAIN_UNKNOWN", "UNITS_AMBIGUOUS", "CRS_UNRESOLVED"} <= {
        q["code"] for q in rep["questions"]
    }


def test_extensionless_zgy_is_found_by_content(tmp_path):
    rep = qc(write_zgy(tmp_path / "CUBEFILE"))
    assert rep["structural"]["format"] == "zgy-3d-poststack"


def test_cut_file_is_truncated(tmp_path, validator):
    rep = qc(write_zgy(tmp_path / "c.zgy", cut=1000))
    validator.validate(rep)
    assert rep["verdict"] == "QUARANTINE"
    assert "TRUNCATED" in codes(rep)


def test_a_zeroed_entry_is_one_missing_brick(tmp_path):
    rep = qc(write_zgy(tmp_path / "c.zgy", hole=True))
    assert "SDIP_ZGY_MISSING_BRICKS" in codes(rep)
    assert rep["structural"]["counts"]["missing_bricks"] == 1


def test_version_one_is_quarantined(tmp_path, validator):
    rep = qc(write_zgy(tmp_path / "c.zgy", version=1))
    validator.validate(rep)
    assert "SDIP_ZGY_VERSION_UNSUPPORTED" in codes(rep)


def test_impossible_size_is_header_invalid(tmp_path):
    path = write_zgy(tmp_path / "c.zgy")
    data = bytearray(path.read_bytes())
    struct.pack_into("<i", data, 9 + struct.calcsize("<3iB2f16s16s16sB3f3f"), -5)  # size[0]
    path.write_bytes(bytes(data))
    assert "HEADER_INVALID" in codes(qc(path))


def test_coincident_corners_mean_no_coordinates(tmp_path):
    rep = qc(write_zgy(tmp_path / "c.zgy", corners=((5, 5),) * 4))
    assert "SDIP_NO_COORDINATES" in codes(rep)
    assert "CRS_UNRESOLVED" not in {q["code"] for q in rep["questions"]}


def test_header_budget_on_a_large_cube(tmp_path):
    # 600 x 600 x 600 float32 would be 864 MB of bricks; the reader reads headers and the LUT only.
    path = tmp_path / "big.zgy"
    small = write_zgy(tmp_path / "s.zgy")
    del small
    write_zgy(path, size=(600, 600, 64), datatype=0)
    rep = qc(path)
    assert rep["headerBytesRead"] < 1 << 20
    assert rep["structural"]["counts"]["bricks"] == 100


def test_cluster_derived_zgy_is_refused(tmp_path, validator):
    rep = qc(write_zgy(tmp_path / "c.zgy"), cls="cluster-derived")
    validator.validate(rep)
    assert rep["verdict"] == "REFUSED"
