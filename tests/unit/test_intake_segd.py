"""Intake reader for SEG-D: both halves on synthetic rev 2.1 demultiplexed records.

The writer follows the rev 1/2 layout as Seismic Unix's ``segd.h`` records it. No public SEG-D
file was found to check against (the standard's own site refuses automated fetches), so this
reader is measured on synthetic records only: its scope on real field data is unmeasured.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sdip.intake import qc_file

SCHEMA = Path(__file__).resolve().parents[1] / "contracts" / "geosuite.intake.v1.schema.json"
UPLOAD = "u-20261116-0123456789ab"
COMMIT = "0123456789abcdef0123456789abcdef01234567"


def b(n: int, width: int) -> bytes:
    """Packed BCD of ``n`` in ``width`` bytes."""
    digits = f"{n:0{2 * width}d}"
    return bytes(int(digits[i]) << 4 | int(digits[i + 1]) for i in range(0, 2 * width, 2))


def write_segd(
    path: Path,
    *,
    sets: tuple[tuple[int, int], ...] = ((48, 1), (2, 9)),
    fmt: int = 8058,
    end_ms: int = 1000,
    interval_16ths: int = 32,
    revision: tuple[int, int] = (2, 1),
    extended: int = 1,
    external: int = 1,
    ext_samples: bool = True,
    cut: int = 0,
    tail: bytes = b"",
    bad_day: bool = False,
) -> Path:
    gh1 = bytearray(32)
    gh1[0:2] = b(17, 1) + b(1, 1)
    gh1[2:4] = b(fmt, 2)
    gh1[10:11] = b(26, 1)
    gh1[11] = (1 << 4) | 3  # one additional general header block; day 3xx
    gh1[12:13] = b(400 if bad_day else 20, 1) if not bad_day else b"\x99"
    gh1[13:16] = b(12, 1) + b(30, 1) + b(5, 1)
    gh1[16:17] = b(13, 1)
    gh1[22] = interval_16ths
    gh1[25] = 0x80
    gh1[26] = 0x02
    gh1[27:28] = b(1, 1)
    gh1[28:29] = b(len(sets), 1)
    gh1[29:30] = b(0, 1)
    gh1[30:31] = b(extended, 1)
    gh1[31:32] = b(external, 1)
    if bad_day:
        gh1[11] = (1 << 4) | 9
    gh2 = bytearray(32)
    gh2[0:3] = (17).to_bytes(3, "big")
    gh2[10], gh2[11] = revision
    gh2[18] = 2
    out = bytearray(gh1 + gh2)
    for k, (n, ctype) in enumerate(sets):
        cs = bytearray(32)
        cs[0:1] = b(1, 1)
        cs[1:2] = b(k + 1, 1)
        cs[2:4] = (0).to_bytes(2, "big")
        cs[4:6] = (end_ms // 2).to_bytes(2, "big")
        cs[8:10] = b(n, 2)
        cs[10] = ctype << 4
        out += cs
    out += bytes(32 * (extended + external))
    width = {8058: 4, 8036: 3, 8024: 2}[fmt]
    samples = int(end_ms / (interval_16ths / 16))
    for k, (n, _) in enumerate(sets):
        for t in range(n):
            th = bytearray(20)
            th[0:2] = b(17, 2)
            th[2:3] = b(1, 1)
            th[3:4] = b(k + 1, 1)
            th[4:6] = b(t + 1, 2)
            th[9] = 1 if ext_samples else 0
            out += th
            if ext_samples:
                ext = bytearray(32)
                ext[7:10] = samples.to_bytes(3, "big")
                out += ext
            out += bytes(samples * width)
    out += tail
    path.write_bytes(bytes(out[: len(out) - cut] if cut else out))
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


@pytest.mark.parametrize("fmt", [8058, 8036, 8024])
@pytest.mark.parametrize("ext_samples", [True, False])
def test_correct_records_pass(tmp_path, validator, fmt, ext_samples):
    rep = qc(write_segd(tmp_path / "rec.segd", fmt=fmt, ext_samples=ext_samples))
    validator.validate(rep)
    assert rep["verdict"] == "PASS", rep["findings"]
    st = rep["structural"]
    assert st["format"] == "segd-demux"
    assert st["version"] == "2.1"
    assert (
        st["counts"]["channels"],
        st["counts"]["seis_channels"],
        st["counts"]["aux_channels"],
    ) == (50, 48, 2)
    assert st["counts"]["traces_walked"] == 50
    assert not rep["questions"]


def test_extensionless_record_by_content(tmp_path):
    rep = qc(write_segd(tmp_path / "00001234"))
    assert rep["structural"]["format"] == "segd-demux"


def test_a_second_record_is_noted(tmp_path):
    first = write_segd(tmp_path / "one.segd").read_bytes()
    rep = qc(write_segd(tmp_path / "two.segd", tail=first))
    assert "SDIP_SEGD_MORE_RECORDS" in codes(rep)
    assert rep["verdict"] == "PASS"


def test_revision_3_is_partial(tmp_path, validator):
    rep = qc(write_segd(tmp_path / "r3.segd", revision=(3, 1)))
    validator.validate(rep)
    assert "SDIP_SEGD_REV3_PARTIAL" in codes(rep)
    assert rep["verdict"] == "QUARANTINE"  # not checked is not passed


def test_cut_record_is_truncated(tmp_path, validator):
    rep = qc(write_segd(tmp_path / "c.segd", cut=100))
    validator.validate(rep)
    assert rep["verdict"] == "QUARANTINE"
    assert "TRUNCATED" in codes(rep)


def test_garbage_after_the_record_is_size_inconsistent(tmp_path):
    rep = qc(write_segd(tmp_path / "g.segd", tail=b"\xee" * 64))
    assert "SIZE_INCONSISTENT" in codes(rep)


def test_one_channel_too_many_declared_is_caught(tmp_path):
    path = write_segd(tmp_path / "x.segd")
    data = bytearray(path.read_bytes())
    data[64 + 8 : 64 + 10] = b(49, 2)  # first set declares 49 channels, holds 48
    path.write_bytes(bytes(data))
    rep = qc(path)
    assert rep["verdict"] == "QUARANTINE"
    assert codes(rep) & {"TRUNCATED", "SDIP_SEGD_UNKNOWN_CHANNEL_SET"}


def test_non_bcd_header_is_not_segd(tmp_path, validator):
    path = write_segd(tmp_path / "n.segd", bad_day=True)
    rep = qc(path)
    validator.validate(rep)
    assert rep["structural"]["format"] != "segd-demux"


def test_cluster_derived_record_is_refused(tmp_path, validator):
    rep = qc(write_segd(tmp_path / "c.segd"), cls="cluster-derived")
    validator.validate(rep)
    assert rep["verdict"] == "REFUSED"


def test_segy_is_not_taken_for_segd(tmp_path):
    from tests.unit.test_intake_segy import build, grid3d

    rep = qc(build(tmp_path / "f.sgy", grid3d()))
    assert rep["structural"]["format"].startswith("segy")


def test_header_budget(tmp_path):
    rep = qc(write_segd(tmp_path / "big.segd", sets=((960, 1),), end_ms=6000))
    assert rep["headerBytesRead"] < 1 << 20
    assert rep["structural"]["counts"]["traces_walked"] == 960
