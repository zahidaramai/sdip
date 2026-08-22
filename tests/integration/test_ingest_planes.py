"""F2 — ingest orchestration, Planes 1 and 2, certificate v0.

Every test here runs a **real ingest** against a **real synthetic SEG-Y** and checks the
**store on disk**, never an in-memory copy from the run that produced it. A checker
validating its own memory is a tautology: it would pass on a store that was never
written.
"""

from __future__ import annotations

import base64
from pathlib import Path

import pytest
import zarr

from sdip.equivalence import issue, plane_1, plane_2, read_codec_manifest, verdict_for
from sdip.errors import DirtyTreeError, UntrustedInputError
from sdip.ingest import ingest, read_raw_file_headers, validate_source
from sdip.ingest.file_headers import ATTR_RAW_BINARY, ATTR_RAW_TEXT
from tests.fixtures.generators import PLANTED_BYTES, make_poststack3d

pytestmark = pytest.mark.integration

ISSUED_AT = "2026-08-22T00:00:00Z"


@pytest.fixture(scope="module")
def ingested(tmp_path_factory) -> tuple[Path, Path, object]:
    """One real ingest, reused. Module-scoped because conversion is the slow part."""
    root = tmp_path_factory.mktemp("f2")
    article = make_poststack3d(root / "src.sgy")
    result = ingest(article.path, root / "out.mdio")
    return article.path, root / "out.mdio", result


def test_the_article_matches_the_banked_measurement(tmp_path):
    """Spec Appendix A.1: 30 traces, 14,640 bytes."""
    article = make_poststack3d(tmp_path / "a.sgy")
    assert article.trace_count == 30
    assert article.byte_size == 14640


def test_the_fixture_is_deterministic(tmp_path):
    """SP9 / G6. A fixture that varies makes determinism unmeasurable.

    REGRESSION: ``SegyFactory.create_textual_header()`` with no argument embeds
    ``datetime.now()`` at second resolution, so two builds straddling a second boundary
    differ - flaky, not reliably broken. Every generator passes explicit text.
    """
    a = make_poststack3d(tmp_path / "a.sgy")
    b = make_poststack3d(tmp_path / "b.sgy")
    assert a.path.read_bytes() == b.path.read_bytes()


def test_ingest_runs_g1_and_records_the_spec(ingested):
    _, _, result = ingested
    assert result.g1.status == "PASS"
    assert result.spec.field_count == 97
    assert result.spec.itemsize == 240
    assert len(result.spec.fillers) == 8


def test_ingest_detects_no_read_path_corruption(ingested):
    """Spec 11.3: the source is hashed before and after."""
    _, _, result = ingested
    assert result.read_path_intact
    assert result.source_sha256 == result.source_sha256_post_read


def test_the_store_carries_all_240_header_bytes(ingested):
    """The pad_233..pad_240 fields are what a sparse spec silently drops."""
    _, store, _ = ingested
    group = zarr.open_group(str(store), mode="r")
    names = group["headers"].dtype.names
    for byte in PLANTED_BYTES:
        assert f"pad_{byte}" in names


def test_the_store_carries_both_file_headers(ingested):
    """MDIO discards both by default; SDIP enables persistence and adds raw bytes."""
    _, store, _ = ingested
    group = zarr.open_group(str(store), mode="r")
    attrs = dict(group["segy_file_header"].attrs)
    assert "textHeader" in attrs, "upstream's parsed view (§4.3 'parsed mapping')"
    assert "binaryHeader" in attrs
    assert ATTR_RAW_TEXT in attrs, "SDIP's authoritative raw bytes (§4.3)"
    assert ATTR_RAW_BINARY in attrs
    assert len(base64.b64decode(attrs[ATTR_RAW_TEXT])) == 3200
    assert len(base64.b64decode(attrs[ATTR_RAW_BINARY])) == 400


def test_plane_1_passes(ingested):
    source, store, _ = ingested
    result = plane_1(source, store)
    assert result.passed
    assert result.gate == "G2a"
    assert result.evidence["n"] == 3200
    assert result.evidence["sampling"] == "exhaustive"
    assert result.evidence["first_difference"] is None


def test_plane_2_passes(ingested):
    source, store, _ = ingested
    result = plane_2(source, store)
    assert result.passed
    assert result.gate == "G2b"
    assert result.evidence["n"] == 400
    assert result.evidence["parsed_mapping_present"] is True


# ---------------------------------------------------------------------------
# NEGATIVE CONTROLS — each corruption fails ITS gate and ONLY its gate
# ---------------------------------------------------------------------------


def _corrupt_stored_header(store: Path, attr: str, offset: int) -> None:
    group = zarr.open_group(str(store), mode="r+")
    node = group["segy_file_header"]
    raw = bytearray(base64.b64decode(node.attrs[attr]))
    raw[offset] ^= 0x01
    node.attrs.update({attr: base64.b64encode(bytes(raw)).decode("ascii")})


def test_a_flipped_textual_byte_fails_g2a_and_only_g2a(tmp_path):
    """NEGATIVE CONTROL. One bit in the textual header."""
    article = make_poststack3d(tmp_path / "src.sgy")
    store = tmp_path / "out.mdio"
    ingest(article.path, store)
    assert plane_1(article.path, store).passed

    _corrupt_stored_header(store, ATTR_RAW_TEXT, 100)

    p1, p2 = plane_1(article.path, store), plane_2(article.path, store)
    assert not p1.passed, "G2a must fail"
    assert p1.evidence["first_difference"]["offset"] == 100
    assert p2.passed, "G2b must still pass - only its gate"


def test_a_flipped_binary_byte_fails_g2b_and_only_g2b(tmp_path):
    """NEGATIVE CONTROL. One bit in the binary header."""
    article = make_poststack3d(tmp_path / "src.sgy")
    store = tmp_path / "out.mdio"
    ingest(article.path, store)

    _corrupt_stored_header(store, ATTR_RAW_BINARY, 17)

    p1, p2 = plane_1(article.path, store), plane_2(article.path, store)
    assert p2.status == "FAIL", "G2b must fail"
    assert p2.evidence["first_difference"]["offset"] == 17
    assert p1.passed, "G2a must still pass - only its gate"


def test_a_truncated_textual_header_is_refused(tmp_path):
    """NEGATIVE CONTROL: §7 G7's 'truncated textual header' control, at F2 scope."""
    article = make_poststack3d(tmp_path / "src.sgy")
    store = tmp_path / "out.mdio"
    ingest(article.path, store)

    group = zarr.open_group(str(store), mode="r+")
    node = group["segy_file_header"]
    short = base64.b64decode(node.attrs[ATTR_RAW_TEXT])[:3000]
    node.attrs.update({ATTR_RAW_TEXT: base64.b64encode(short).decode("ascii")})

    with pytest.raises(UntrustedInputError, match="3000 bytes"):
        plane_1(article.path, store)


# ---------------------------------------------------------------------------
# Untrusted input — spec 11.4
# ---------------------------------------------------------------------------


def test_a_too_short_file_is_refused_before_allocation(tmp_path):
    """NEGATIVE CONTROL: a hostile file must produce a clean typed error."""
    tiny = tmp_path / "tiny.sgy"
    tiny.write_bytes(b"\x00" * 100)
    with pytest.raises(UntrustedInputError, match="cannot be smaller"):
        validate_source(tiny)


def test_a_directory_is_refused(tmp_path):
    with pytest.raises(UntrustedInputError, match="not a regular file"):
        validate_source(tmp_path)


def test_a_header_only_file_is_refused_by_the_header_reader(tmp_path):
    partial = tmp_path / "partial.sgy"
    partial.write_bytes(b"\x00" * 3000)
    with pytest.raises(UntrustedInputError, match="must begin with"):
        read_raw_file_headers(partial)


# ---------------------------------------------------------------------------
# Certificate v0
# ---------------------------------------------------------------------------


def test_certificate_is_provisional_at_f2(ingested):
    """F2 cannot reach EQUIVALENT, and that is enforced in code, not by discretion."""
    source, store, result = ingested
    planes = [plane_1(source, store), plane_2(source, store)]
    cert = issue(result, planes, require_clean_tree=False, issued_at=ISSUED_AT, issued_by="test")
    payload = cert.payload
    assert payload["verdict"] == "PROVISIONAL"
    assert payload["gates"]["G1"] == "PASS"
    # G2 is the conjunction of G2a-G2e. Two passing planes is not a passing G2: the
    # three unrun ones are exactly where a defect would hide.
    assert payload["gates"]["G2"] == "NOT_RUN"
    assert payload["gates"]["G7"] == "NOT_RUN"
    assert payload["planes"]["plane_3"]["status"] == "NOT_RUN"
    assert "D11" in payload["verdict_reason"]


def test_unrun_planes_are_never_assumed_to_pass(ingested):
    _source, _store, result = ingested
    cert = issue(result, [], require_clean_tree=False, issued_at=ISSUED_AT, issued_by="test")
    for key in ("plane_1", "plane_2", "plane_3", "plane_4", "plane_5"):
        assert cert.payload["planes"][key]["status"] == "NOT_RUN"
    assert cert.payload["verdict"] == "PROVISIONAL"


def test_a_failing_plane_makes_the_verdict_non_equivalent(tmp_path):
    article = make_poststack3d(tmp_path / "src.sgy")
    store = tmp_path / "out.mdio"
    result = ingest(article.path, store)
    _corrupt_stored_header(store, ATTR_RAW_TEXT, 7)
    planes = [plane_1(article.path, store), plane_2(article.path, store)]
    cert = issue(result, planes, require_clean_tree=False, issued_at=ISSUED_AT, issued_by="test")
    assert cert.payload["verdict"] == "NON-EQUIVALENT"
    assert cert.payload["gates"]["G2"] == "FAIL"


def test_certificate_refuses_a_dirty_tree(ingested, tmp_path):
    """Spec 11.3. There is no --force."""
    source, store, result = ingested
    (tmp_path / "dirty.txt").write_text("x")
    with pytest.raises(DirtyTreeError, match="no override"):
        issue(
            result,
            [plane_1(source, store)],
            root=tmp_path,
            issued_at=ISSUED_AT,
            issued_by="test",
        )


def test_codec_manifest_is_lossless(ingested):
    """SP3. Read from disk, not from what the writer intended."""
    _, store, _ = ingested
    codecs = read_codec_manifest(store)
    assert codecs
    assert not {"zfpy", "zfp", "jpeg", "jpeg2000"} & set(codecs)
    assert {"blosc", "bytes"} <= set(codecs)


def test_the_array_manifest_records_non_core_dtypes(ingested):
    """OPEN_DEBTS D3 / probe P4, detected from zarr.json without any warning."""
    source, store, result = ingested
    cert = issue(
        result,
        [plane_1(source, store)],
        require_clean_tree=False,
        issued_at=ISSUED_AT,
        issued_by="test",
    )
    manifest = {a["name"]: a["zarr_v3_core_spec"] for a in cert.payload["output_array_manifest"]}
    assert manifest["amplitude"] is True
    assert manifest["headers"] is False, "structured dtype has no Zarr v3 core spec"


@pytest.mark.parametrize(
    ("planes", "gates", "expected"),
    [
        (dict.fromkeys(range(1, 6), "PASS"), "PASS", "EQUIVALENT"),
        (dict.fromkeys(range(1, 6), "PASS"), "NOT_RUN", "PROVISIONAL"),
        ({1: "FAIL", 2: "PASS", 3: "PASS", 4: "PASS", 5: "PASS"}, "PASS", "NON-EQUIVALENT"),
    ],
)
def test_verdict_requires_g7(planes, gates, expected):
    """A store whose planes pass against an engine never shown to fail is not checked."""
    plane_map = {f"plane_{k}": v for k, v in planes.items()}
    gate_map = dict.fromkeys(["G1", "G2", "G3", "G4", "G5", "G6"], "PASS") | {"G7": gates}
    assert verdict_for(plane_map, gate_map, lossy=False) == expected


def test_a_lossy_codec_voids_the_store():
    """SP3, independent of every other check."""
    planes = {f"plane_{i}": "PASS" for i in range(1, 6)}
    gates = dict.fromkeys(["G1", "G2", "G3", "G4", "G5", "G6", "G7"], "PASS")
    assert verdict_for(planes, gates, lossy=True) == "NON-EQUIVALENT"
