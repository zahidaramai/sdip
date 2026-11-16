# ruff: noqa: E501 - XML literals of the synthetic packages read better unbroken
"""Intake reader for RESQML packages: both halves on synthetic EPC files built here with zipfile."""

from __future__ import annotations

import json
import stat
import zipfile
from pathlib import Path

import pytest

from sdip.intake import qc_file

SCHEMA = Path(__file__).resolve().parents[1] / "contracts" / "geosuite.intake.v1.schema.json"
UPLOAD = "u-20261116-0123456789ab"
COMMIT = "0123456789abcdef0123456789abcdef01234567"
GRID = "11111111-2222-3333-4444-555555555555"
CRS = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
EXT = "99999999-8888-7777-6666-555555555555"
NS = 'xmlns:r="http://www.energistics.org/energyml/data/resqmlv2" xmlns:eml="http://www.energistics.org/energyml/data/commonv2" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"'


def crs_xml(kind: str = "LocalDepth3dCrs", epsg: str | None = None, units: bool = True) -> str:
    projected = (
        f'<r:ProjectedCrs xsi:type="eml:ProjectedEpsgCrs"><eml:EpsgCode>{epsg}</eml:EpsgCode></r:ProjectedCrs>'
        if epsg
        else '<r:ProjectedCrs xsi:type="eml:ProjectedUnknownCrs"><eml:Unknown>Unknown</eml:Unknown></r:ProjectedCrs>'
    )
    uom = "<r:ProjectedUom>m</r:ProjectedUom><r:VerticalUom>m</r:VerticalUom>" if units else ""
    return f'<?xml version="1.0"?><r:{kind} {NS} uuid="{CRS}">{uom}{projected}</r:{kind}>'


def grid_xml(ni: int = 4, nj: int = 5, nk: int = 6, ref: str = CRS) -> str:
    return (
        f'<?xml version="1.0"?><r:IjkGridRepresentation {NS} uuid="{GRID}"><r:Ni>{ni}</r:Ni><r:Nj>{nj}</r:Nj>'
        f"<r:Nk>{nk}</r:Nk><r:LocalCrs><eml:UUID>{ref}</eml:UUID></r:LocalCrs></r:IjkGridRepresentation>"
    )


def write_epc(
    path: Path,
    *,
    crs: str | None = None,
    crs_kind: str = "LocalDepth3dCrs",
    grid: str | None = None,
    h5: bool = True,
    h5_bytes: bytes = b"\x89HDF\r\n\x1a\n" + bytes(56),
    extra: dict[str, bytes] | None = None,
    symlink: bool = False,
) -> Path:
    parts = {
        f"obj_{crs_kind}_{CRS}.xml": (crs or crs_xml(crs_kind)).encode(),
        f"obj_IjkGridRepresentation_{GRID}.xml": (grid or grid_xml()).encode(),
        f"obj_EpcExternalPartReference_{EXT}.xml": f'<?xml version="1.0"?><eml:EpcExternalPartReference {NS} uuid="{EXT}"/>'.encode(),
    }
    types = "".join(
        f'<Override PartName="/{n}" ContentType="application/x-resqml+xml;version=2.0;type=obj_{n.split("_")[1]}"/>'
        for n in parts
    )
    ct = f'<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">{types}</Types>'
    rels = (
        '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        f'<Relationship Id="Hdf5File" Type="externalResource" Target="{path.stem}.h5" TargetMode="External"/>'
        "</Relationships>"
    )
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", ct)
        for n, data in parts.items():
            z.writestr(n, data)
        z.writestr(f"_rels/obj_EpcExternalPartReference_{EXT}.xml.rels", rels)
        for n, data in (extra or {}).items():
            z.writestr(n, data)
        if symlink:
            info = zipfile.ZipInfo("link")
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            z.writestr(info, "/etc/passwd")
    if h5:
        (path.parent / f"{path.stem}.h5").write_bytes(h5_bytes)
    return path


def qc(path: Path, **kw: object) -> dict:
    return qc_file(path, upload_id=UPLOAD, member=path.name, commit=COMMIT, **kw).report  # type: ignore[arg-type]


@pytest.fixture(scope="module")
def validator():
    jsonschema = pytest.importorskip("jsonschema")
    return jsonschema.Draft202012Validator(
        json.loads(SCHEMA.read_text()), format_checker=jsonschema.FormatChecker()
    )


def codes(rep: dict) -> set[str]:
    return set(rep["structural"]["codes"])


def test_package_with_stated_epsg_passes(tmp_path, validator):
    rep = qc(write_epc(tmp_path / "model.epc", crs=crs_xml(epsg="23031")))
    validator.validate(rep)
    assert rep["verdict"] == "PASS", rep["findings"]
    st = rep["structural"]
    assert (st["format"], st["version"], st["domain"], st["hasCrs"], st["hasUnits"]) == (
        "resqml-epc",
        "2.0",
        "depth",
        True,
        True,
    )
    assert st["counts"]["grid_cells"] == 120
    assert st["counts"]["ijk_grids"] == 1
    assert "SDIP_RESQML_CRS_STATED" in codes(rep)
    assert "23031" not in json.dumps(st)


def test_unknown_crs_is_asked(tmp_path, validator):
    rep = qc(write_epc(tmp_path / "m.epc"))
    validator.validate(rep)
    assert [q["code"] for q in rep["questions"]] == ["CRS_UNRESOLVED"]


def test_time_crs_gives_time_domain(tmp_path):
    rep = qc(
        write_epc(
            tmp_path / "m.epc",
            crs_kind="LocalTime3dCrs",
            crs=crs_xml("LocalTime3dCrs", epsg="23031"),
        )
    )
    assert rep["structural"]["domain"] == "time"


def test_missing_units_are_asked(tmp_path):
    rep = qc(write_epc(tmp_path / "m.epc", crs=crs_xml(epsg="23031", units=False)))
    assert "UNITS_AMBIGUOUS" in {q["code"] for q in rep["questions"]}


def test_extensionless_package_by_content(tmp_path):
    rep = qc(write_epc(tmp_path / "MODEL"))
    assert rep["structural"]["format"] == "resqml-epc"


def test_missing_hdf5_companion_is_quarantined(tmp_path, validator):
    rep = qc(write_epc(tmp_path / "m.epc", h5=False))
    validator.validate(rep)
    assert rep["verdict"] == "QUARANTINE"
    assert "SDIP_RESQML_HDF5_MISSING" in codes(rep)


def test_companion_that_is_not_hdf5_is_quarantined(tmp_path):
    rep = qc(write_epc(tmp_path / "m.epc", h5_bytes=b"not hdf5 at all"))
    assert "HEADER_INVALID" in codes(rep)


def test_dangling_reference_is_counted(tmp_path):
    rep = qc(
        write_epc(tmp_path / "m.epc", grid=grid_xml(ref="00000000-0000-0000-0000-000000000000"))
    )
    assert rep["structural"]["counts"]["dangling_references"] == 1


def test_grid_without_dimensions_is_header_invalid(tmp_path):
    bad = grid_xml().replace("<r:Nk>6</r:Nk>", "")
    assert "HEADER_INVALID" in codes(qc(write_epc(tmp_path / "m.epc", grid=bad)))


@pytest.mark.parametrize(
    ("kw", "code"),
    [
        ({"extra": {"../evil.xml": b"<a/>"}}, "PATH_TRAVERSAL"),
        ({"extra": {"/abs.xml": b"<a/>"}}, "PATH_TRAVERSAL"),
        ({"symlink": True}, "SYMLINK"),
        (
            {"extra": {"x.xml": b'<?xml version="1.0"?><!DOCTYPE a [<!ENTITY e "x">]><a>&e;</a>'}},
            "XML_ENTITY",
        ),
        ({"extra": {"bomb.bin": bytes(50_000_000)}}, "ARCHIVE_BOMB"),
    ],
)
def test_hostile_packages_are_refused(tmp_path, validator, kw, code):
    rep = qc(write_epc(tmp_path / "h.epc", **kw))
    validator.validate(rep)
    assert rep["verdict"] == "REFUSED"
    assert code in codes(rep)


def test_a_plain_zip_is_not_resqml(tmp_path):
    path = tmp_path / "plain.zip"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("a.txt", "hello")
    rep = qc(path)
    assert not rep["structural"]["format"].startswith("resqml")


def test_cluster_derived_package_is_refused(tmp_path):
    assert qc(write_epc(tmp_path / "m.epc"), cls="cluster-derived")["verdict"] == "REFUSED"
