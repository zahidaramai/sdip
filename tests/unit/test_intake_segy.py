"""Intake reader for SEG-Y (``sdip intake``): both halves, every report schema-valid.

Correct files of every geometry must come back with their expected geometry and no
quarantine (the passing half, D-0088); each corruption must come back with its own code
(the failing half, G7 discipline). Every report validates against the vendored
``geosuite.intake.v1`` schema, pinned by sha256 so a silent change of the contract fails here.
All files are synthetic, built below with ``struct``; nothing is read from outside tmp_path.
"""

from __future__ import annotations

import hashlib
import json
import struct
from pathlib import Path

import pytest

from sdip.intake import qc_file
from sdip.intake.segy import HEADER_BUDGET

SCHEMA = Path(__file__).resolve().parents[1] / "contracts" / "geosuite.intake.v1.schema.json"
SCHEMA_SHA256 = "f0a3e47a8212859fc9ca36c76ac54943465635eedcbf5dd99a690aee27d7089a"
"""GeoGIS 6edead4c ``packages/contracts/geosuite.intake.v1.schema.json``."""
UPLOAD = "u-20261116-0123456789ab"
COMMIT = "0123456789abcdef0123456789abcdef01234567"


def _text(lines: list[str], ascii_: bool = False) -> bytes:
    cards = "".join(
        f"C{i + 1:2d} {line}"[:80].ljust(80) for i, line in enumerate(lines + [""] * 40)
    )[:3200]
    return cards.encode("latin-1" if ascii_ else "cp037")


def build(
    path: Path,
    traces: list[dict[str, int]],
    *,
    ns: int = 50,
    dt: int = 4000,
    fmt: int = 5,
    order: str = ">",
    text: list[str] | None = None,
    ascii_: bool = False,
    measurement: int = 1,
    extended: int = 0,
    revision: int = 0x0100,
    trailing: int = 0,
) -> Path:
    """A SEG-Y with zeroed samples and the given trace-header fields."""
    binary = bytearray(400)
    struct.pack_into(f"{order}h", binary, 16, dt)
    struct.pack_into(f"{order}H", binary, 20, ns)
    struct.pack_into(f"{order}h", binary, 24, fmt)
    struct.pack_into(f"{order}h", binary, 54, measurement)
    struct.pack_into(f"{order}H", binary, 300, revision)
    struct.pack_into(f"{order}h", binary, 302, 1)
    struct.pack_into(f"{order}h", binary, 304, extended)
    width = {1: 4, 5: 4, 8: 1, 3: 2}[fmt]
    out = bytearray(
        _text(
            text or ["SYNTHETIC SDIP INTAKE TEST", "TIME DOMAIN TWT MS", "CRS EPSG:23031"], ascii_
        )
    )
    out += binary
    out += b" " * (3200 * max(extended, 0))
    fields = {
        "ffid": (8, "i"),
        "channel": (12, "i"),
        "cdp": (20, "i"),
        "trace_id": (28, "h"),
        "offset": (36, "i"),
        "scalar": (70, "h"),
        "src_x": (72, "i"),
        "src_y": (76, "i"),
        "coord_units": (88, "h"),
        "ns": (114, "H"),
        "dt": (116, "H"),
        "cdp_x": (180, "i"),
        "cdp_y": (184, "i"),
        "inline": (188, "i"),
        "crossline": (192, "i"),
    }
    for t in traces:
        header = bytearray(240)
        values = {"trace_id": 1, "scalar": -100, "coord_units": 1, "ns": ns, "dt": dt} | t
        for name, value in values.items():
            off, code = fields[name]
            struct.pack_into(order + code, header, off, value)
        out += header + bytes(ns * width)
    out += b"\0" * trailing
    path.write_bytes(bytes(out))
    return path


def grid3d(n_il: int = 6, n_xl: int = 7) -> list[dict[str, int]]:
    return [
        {
            "inline": il,
            "crossline": xl,
            "cdp": xl,
            "cdp_x": 4_000_000 + 2500 * xl,
            "cdp_y": 60_000_000 + 2500 * il,
        }
        for il in range(100, 100 + n_il)
        for xl in range(300, 300 + n_xl)
    ]


def line2d(n: int = 40) -> list[dict[str, int]]:
    return [
        {
            "cdp": 1000 + i,
            "ffid": 1001 + i // 2,
            "channel": 96 - i % 96,
            "offset": -1200 + 12 * i,
            "inline": 1001 + i // 2,
            "crossline": 2100 + i,
            "cdp_x": 4_000_000 + 1250 * i,
            "cdp_y": 60_000_000,
        }
        for i in range(n)
    ]


def shots2d(shots: int = 5, channels: int = 24) -> list[dict[str, int]]:
    return [
        {
            "ffid": s,
            "channel": c + 1,
            "cdp": 2 * s + c,
            "offset": 100 + 50 * c,
            "src_x": 4_000_000 + 5000 * s,
            "src_y": 60_000_000,
            "cdp_x": 4_000_000 + 5000 * s + 2500 * c,
            "cdp_y": 60_000_000,
        }
        for s in range(1, shots + 1)
        for c in range(channels)
    ]


def cdp_gathers3d() -> list[dict[str, int]]:
    return [
        {
            "inline": il,
            "crossline": xl,
            "cdp": xl,
            "offset": off,
            "cdp_x": 4_000_000 + 2500 * xl,
            "cdp_y": 60_000_000 + 2500 * il,
        }
        for il in range(10, 13)
        for xl in range(20, 24)
        for off in (100, 300, 500, 700)
    ]


def qc(path: Path, **kw: object) -> dict:
    out = qc_file(path, upload_id=UPLOAD, member=kw.pop("member", path.name), commit=COMMIT, **kw)  # type: ignore[arg-type]
    return out.report


@pytest.fixture(scope="module")
def validator():
    jsonschema = pytest.importorskip("jsonschema")
    assert hashlib.sha256(SCHEMA.read_bytes()).hexdigest() == SCHEMA_SHA256
    schema = json.loads(SCHEMA.read_text())
    return jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker())


def codes(rep: dict) -> set[str]:
    return set(rep["structural"]["codes"])


# ---------------------------------------------------------------------------------------
# The passing half: correct files of every geometry


@pytest.mark.parametrize(
    ("builder", "kind", "template"),
    [
        (grid3d, "3d-poststack", "PostStack3DTime"),
        (line2d, "2d-poststack", "PostStack2DTime"),
        (shots2d, "2d-prestack", "StreamerShotGathers2D"),
        (cdp_gathers3d, "3d-prestack", "CdpOffsetGathers3DTime"),
    ],
)
def test_correct_geometries_are_recognised_and_routed(tmp_path, validator, builder, kind, template):
    rep = qc(build(tmp_path / "f.sgy", builder()))
    validator.validate(rep)
    assert rep["structural"]["format"] == f"segy-{kind}"
    assert rep["verdict"] == "NEEDS_INPUT"  # CRS and domain are asked, never inferred
    assert {q["code"] for q in rep["questions"]} == {"CRS_UNRESOLVED", "DOMAIN_UNKNOWN"}
    assert not [f for f in rep["findings"] if f["severity"] in ("quarantine", "refuse")], rep[
        "findings"
    ]
    route = next(f for f in rep["findings"] if f["code"] == "SDIP_MDIO_ROUTE")
    assert f"--template {template}" in route["message"]


def test_crs_candidates_come_from_the_textual_header_with_their_source(tmp_path):
    rep = qc(build(tmp_path / "f.sgy", grid3d()))
    crs = next(q for q in rep["questions"] if q["code"] == "CRS_UNRESOLVED")
    first = crs["choices"][0]
    assert first["label"] == "EPSG:23031"
    assert first["source"].startswith("SEG-Y textual header, card C03")
    assert rep["structural"]["hasCrs"] is True


def test_3d_grid_counts(tmp_path):
    rep = qc(build(tmp_path / "f.sgy", grid3d(6, 7)))
    c = rep["structural"]["counts"]
    assert (c["traces"], c["inlines"], c["crosslines"], c["grid_cells"]) == (42, 6, 7, 42)


@pytest.mark.parametrize("variant", ["little", "ascii", "int8", "ibm", "extended", "no-extension"])
def test_correct_variants_pass_without_quarantine(tmp_path, validator, variant):
    kw: dict = {}
    name = "f.sgy"
    if variant == "little":
        kw["order"] = "<"
    elif variant == "ascii":
        kw["ascii_"] = True
    elif variant == "int8":
        kw["fmt"] = 8
    elif variant == "ibm":
        kw["fmt"] = 1
    elif variant == "extended":
        kw["extended"] = 2
    else:
        name = "SURVEYFILE"
    rep = qc(build(tmp_path / name, grid3d(), **kw))
    validator.validate(rep)
    assert rep["structural"]["format"] == "segy-3d-poststack"
    assert rep["verdict"] == "NEEDS_INPUT"
    assert "SDIP_MDIO_ROUTE" in codes(rep)
    if variant == "little":
        assert "SDIP_LITTLE_ENDIAN" in codes(rep)
    if variant == "no-extension":
        assert "SDIP_NO_EXTENSION" in codes(rep)


def test_extension_contradiction_is_information_only(tmp_path, validator):
    rep = qc(build(tmp_path / "f.las", grid3d()))
    validator.validate(rep)
    assert "EXTENSION_CONTRADICTION" in codes(rep)
    assert rep["verdict"] == "NEEDS_INPUT"


def test_header_budget_is_respected_and_samples_are_never_read(tmp_path):
    # 5000 traces of 1000 IEEE samples: 20 MB of samples, of which none may be read.
    traces = [
        {"inline": 1 + i // 100, "crossline": 1 + i % 100, "cdp_x": 1000 * i, "cdp_y": 7}
        for i in range(5000)
    ]
    path = build(tmp_path / "big.sgy", traces, ns=1000)
    rep = qc(path)
    assert rep["headerBytesRead"] <= HEADER_BUDGET < path.stat().st_size
    assert rep["headerBytesRead"] == 3600 + 240 * rep["structural"]["counts"]["sampled_headers"]


def test_structural_block_carries_no_values_or_names(tmp_path, validator):
    rep = qc(build(tmp_path / "secret-name.sgy", grid3d()), cls="confidential")
    validator.validate(rep)
    blob = json.dumps(rep["structural"])
    for leak in ("secret", "23031", "4000000", "60000000", "EPSG"):
        assert leak not in blob


# ---------------------------------------------------------------------------------------
# The failing half: each corruption gets its own code


def test_one_dropped_byte_is_truncation(tmp_path, validator):
    path = build(tmp_path / "f.sgy", grid3d())
    path.write_bytes(path.read_bytes()[:-1])
    rep = qc(path)
    validator.validate(rep)
    assert rep["verdict"] == "QUARANTINE"
    assert "TRUNCATED" in codes(rep)


def test_extra_bytes_with_variable_length_flag_are_size_inconsistent(tmp_path):
    path = build(tmp_path / "f.sgy", grid3d(), trailing=7)
    data = bytearray(path.read_bytes())
    struct.pack_into(">h", data, 3200 + 302, 0)  # fixed-length flag off
    path.write_bytes(bytes(data))
    assert "SIZE_INCONSISTENT" in codes(qc(path))


def test_incoherent_binary_header_is_quarantined(tmp_path, validator):
    path = build(tmp_path / "f.sgy", grid3d())
    data = bytearray(path.read_bytes())
    struct.pack_into(">h", data, 3224, 77)  # sample format code 77 in both byte orders
    struct.pack_into(">H", data, 3220, 0)
    path.write_bytes(bytes(data))
    rep = qc(path)
    validator.validate(rep)
    assert rep["verdict"] == "QUARANTINE"
    assert "HEADER_INVALID" in codes(rep)


def test_not_segy_is_refused_as_unsupported(tmp_path, validator):
    path = tmp_path / "f.sgy"
    path.write_bytes(bytes(range(256)) * 40)
    rep = qc(path)
    validator.validate(rep)
    assert rep["verdict"] == "REFUSED"
    assert codes(rep) == {"UNSUPPORTED_FORMAT"}


def test_short_file_is_refused(tmp_path, validator):
    path = tmp_path / "f.sgy"
    path.write_bytes(b"C 1" + b" " * 100)
    rep = qc(path)
    validator.validate(rep)
    assert rep["verdict"] == "REFUSED"


def test_cluster_marker_in_the_textual_header_is_refused_before_traces_are_read(
    tmp_path, validator
):
    path = build(tmp_path / "f.sgy", grid3d(), text=["SURVEY ZEBRAFIELD 3D", "TIME"])
    rep = qc(path, cluster_markers=("zebrafield",))
    validator.validate(rep)
    assert rep["verdict"] == "REFUSED"
    assert "CLUSTER_RAW_REFUSED" in codes(rep)
    assert rep["headerBytesRead"] == 3600


def test_a_marker_inside_a_longer_word_is_not_a_hit(tmp_path):
    path = build(tmp_path / "f.sgy", grid3d(), text=["SURVEY ZEBRAFIELDS 3D"])
    assert "CLUSTER_RAW_REFUSED" not in codes(qc(path, cluster_markers=("ZEBRAFIELD",)))


def test_class_cluster_derived_is_refused(tmp_path, validator):
    rep = qc(build(tmp_path / "f.sgy", grid3d()), cls="cluster-derived")
    validator.validate(rep)
    assert rep["verdict"] == "REFUSED"


def test_illegal_coordinate_scalar_is_quarantined(tmp_path, validator):
    traces = [t | {"scalar": -7} for t in grid3d()]
    rep = qc(build(tmp_path / "f.sgy", traces))
    validator.validate(rep)
    assert "SDIP_COORD_SCALAR_INVALID" in codes(rep)
    assert rep["verdict"] == "QUARANTINE"


def test_degrees_flag_with_projected_coordinates_is_a_contradiction(tmp_path):
    traces = [t | {"coord_units": 3} for t in grid3d()]
    assert "SDIP_COORD_UNITS_CONTRADICT" in codes(qc(build(tmp_path / "f.sgy", traces)))


def test_degrees_flag_with_degree_coordinates_passes(tmp_path):
    traces = [
        t
        | {"coord_units": 3, "scalar": -10000, "cdp_x": 31_0000 + t["crossline"], "cdp_y": 55_0000}
        for t in grid3d()
    ]
    assert "SDIP_COORD_UNITS_CONTRADICT" not in codes(qc(build(tmp_path / "f.sgy", traces)))


def test_a_trace_with_another_sample_count_is_quarantined(tmp_path):
    traces = grid3d()
    traces[3] = traces[3] | {"ns": 49}
    assert "SDIP_TRACE_SAMPLES_DIFFER" in codes(qc(build(tmp_path / "f.sgy", traces)))


def test_variable_extended_headers_are_quarantined(tmp_path, validator):
    path = build(tmp_path / "f.sgy", grid3d())
    data = bytearray(path.read_bytes())
    struct.pack_into(">h", data, 3200 + 304, -1)
    path.write_bytes(bytes(data))
    rep = qc(path)
    validator.validate(rep)
    assert "SDIP_VARIABLE_EXT_HEADERS" in codes(rep)


def test_duplicated_cells_in_a_poststack_grid_are_not_called_poststack(tmp_path):
    traces = grid3d()
    traces = traces + traces  # every cell twice, same offset
    rep = qc(build(tmp_path / "f.sgy", traces))
    assert rep["structural"]["format"] != "segy-3d-poststack"


def test_missing_measurement_system_asks_for_units(tmp_path):
    rep = qc(build(tmp_path / "f.sgy", grid3d(), measurement=0))
    assert "UNITS_AMBIGUOUS" in {q["code"] for q in rep["questions"]}
    assert rep["structural"]["hasUnits"] is False


def test_the_ingest_preflight_refusal_is_reported(tmp_path, validator):
    traces = [t | {"scalar": 0} for t in grid3d()]
    rep = qc(build(tmp_path / "f.sgy", traces))  # rev 1 and a zero scalar: MDIO refuses
    validator.validate(rep)
    assert "ENGINE_REFUSED" in codes(rep)
    assert "SDIP_MDIO_ROUTE" not in codes(rep)
