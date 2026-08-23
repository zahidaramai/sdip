"""F3 — the Equivalence Engine: five planes, G3 round trip, G4 portability.

**The negative controls are the point of this file.** A plane that has never been shown
to fail is not a check (**SP11**), and each control asserts two things: the target plane
**fails**, and every other plane **still passes**. The second half is the one people
skip, and it is the half that catches an over-broad checker — one that fails everything
on any corruption cannot localise a fault and gets silenced the first time it fires on
something benign.

These are the F3-scoped ancestors of the full G7 suite (F4). G7 additionally requires
every corruption to fail its gate **and only** its gate across the whole engine at once,
audited together; that audit has not been done, so **G7 remains NOT_RUN** and every
certificate this engine issues is unvalidated (`OPEN_DEBTS.md` D11).
"""

from __future__ import annotations

import numpy as np
import pytest
import zarr

from sdip.equivalence import (
    build_trace_map,
    g4,
    issue,
    plane_1,
    plane_2,
    plane_3,
    plane_4,
    plane_5,
)
from sdip.export import export
from sdip.ingest import ingest
from tests.fixtures.generators import make_poststack3d

pytestmark = pytest.mark.integration

ISSUED_AT = "2026-08-22T00:00:00Z"


@pytest.fixture(scope="module")
def article(tmp_path_factory):
    """One real ingest, reused across the read-only tests."""
    root = tmp_path_factory.mktemp("f3")
    source = make_poststack3d(root / "src.sgy")
    result = ingest(source.path, root / "out.mdio")
    return source, root / "out.mdio", result


@pytest.fixture
def fresh(tmp_path):
    """A private ingest for tests that corrupt the store."""
    source = make_poststack3d(tmp_path / "src.sgy")
    result = ingest(source.path, tmp_path / "out.mdio")
    return source, tmp_path / "out.mdio", result


def _all_planes(source, store, spec, *, g1_passed: bool = True) -> list:
    return [
        plane_1(source, store),
        plane_2(source, store),
        plane_3(source, store, spec, g1_passed=g1_passed),
        plane_4(source, store, spec),
        plane_5(source, store, spec),
    ]


# ---------------------------------------------------------------------------
# All five planes pass on a clean ingest
# ---------------------------------------------------------------------------


def test_all_five_planes_pass(article):
    source, store, result = article
    planes = _all_planes(source.path, store, result.spec.segy_spec)
    assert [p.status for p in planes] == ["PASS"] * 5
    assert [p.gate for p in planes] == ["G2a", "G2b", "G2c", "G2d", "G2e"]


def test_plane_3_compares_every_field_of_every_trace(article):
    source, store, result = article
    plane = plane_3(source.path, store, result.spec.segy_spec, g1_passed=True)
    assert plane.evidence["n"] == 30
    assert plane.evidence["field_count"] == 97
    assert plane.evidence["sampling"] == "exhaustive"
    assert plane.evidence["missing_fields_in_store"] == []


def test_plane_3_refuses_to_pass_without_g1(article):
    """NEGATIVE CONTROL, and the most important one in this file.

    Plane 3's byte-exactness claim holds only because G1 proved the spec covers all
    240 bytes. Field-wise equality over an incomplete spec proves nothing about the
    uncovered bytes, so PASS would be a claim the evidence does not support.
    """
    source, store, result = article
    plane = plane_3(source.path, store, result.spec.segy_spec, g1_passed=False)
    assert plane.status == "FAIL"
    assert "G1 did not pass" in plane.evidence["reason"]


def test_the_planted_bytes_survive(article):
    """The eight bytes rev 1 does not cover are the whole reason for a gap-free spec."""
    source, store, _ = article
    group = zarr.open_group(str(store), mode="r")
    headers = group["headers"][:]
    for ordinal in range(source.trace_count):
        i, j = divmod(ordinal, len(source.crosslines))
        for k, byte in enumerate(range(233, 241)):
            assert headers[f"pad_{byte}"][i, j] == source.planted[ordinal, k]


def test_plane_4_uses_exact_equality_not_a_tolerance(article):
    source, store, result = article
    plane = plane_4(source.path, store, result.spec.segy_spec)
    assert "EXACT, never allclose" in plane.evidence["compared"]
    assert plane.evidence["padding_excluded"] is True


def test_plane_5_reports_an_invertible_map(article):
    source, store, result = article
    plane = plane_5(source.path, store, result.spec.segy_spec)
    assert plane.evidence["checks"] == {
        "count_matches": True,
        "map_complete": True,
        "map_invertible": True,
        "no_duplicates": True,
        "mask_matches_map": True,
        # D-0061: this plane's claim is about which cells are live, which is
        # unanswerable if the mask or a grid coordinate array is simply absent.
        "no_required_array_missing": True,
        # D29 / SP12: padding is VERIFIED as padding - every cell no source trace maps
        # to holds the declared fill and nothing else. A value there came from nowhere.
        "padding_is_only_fill": True,
    }
    assert plane.evidence["padding_cells"] == 0


# ---------------------------------------------------------------------------
# NEGATIVE CONTROLS — each fails its plane and ONLY its plane
# ---------------------------------------------------------------------------


def _others_still_pass(planes, target: int) -> None:
    for plane in planes:
        if plane.plane == target:
            continue
        assert plane.passed, (
            f"corrupting plane {target} also failed plane {plane.plane} - the checker "
            "is over-broad and cannot localise a fault"
        )


def test_a_flipped_header_byte_fails_g2c_and_only_g2c(fresh):
    """NEGATIVE CONTROL: one flipped trace-header byte. Spec §7 G7 minimum set."""
    source, store, result = fresh
    group = zarr.open_group(str(store), mode="r+")
    headers = group["headers"][:]
    headers["pad_237"][2, 3] = (int(headers["pad_237"][2, 3]) + 1) % 256
    group["headers"][:] = headers

    planes = _all_planes(source.path, store, result.spec.segy_spec)
    plane3 = next(p for p in planes if p.plane == 3)
    assert plane3.status == "FAIL"
    assert plane3.evidence["first_difference"]["field"] == "pad_237"
    _others_still_pass(planes, target=3)


def test_a_flipped_sample_bit_fails_g2d_and_only_g2d(fresh):
    """NEGATIVE CONTROL: one flipped sample. Spec §7 G7 minimum set."""
    source, store, result = fresh
    group = zarr.open_group(str(store), mode="r+")
    volume = group["amplitude"][:]
    raw = volume[1, 2, 7].view(np.uint32) ^ np.uint32(1)
    volume[1, 2, 7] = raw.view(np.float32)
    group["amplitude"][:] = volume

    planes = _all_planes(source.path, store, result.spec.segy_spec)
    plane4 = next(p for p in planes if p.plane == 4)
    assert plane4.status == "FAIL"
    assert plane4.evidence["first_difference"]["first_sample"] == 7
    _others_still_pass(planes, target=4)


def test_an_inverted_live_mask_fails_g2e_and_only_g2e(fresh):
    """NEGATIVE CONTROL: live mask flipped on one trace. Spec §7 G7 minimum set."""
    source, store, result = fresh
    group = zarr.open_group(str(store), mode="r+")
    mask = group["trace_mask"][:]
    mask[0, 0] = 0
    group["trace_mask"][:] = mask

    planes = _all_planes(source.path, store, result.spec.segy_spec)
    plane5 = next(p for p in planes if p.plane == 5)
    assert plane5.status == "FAIL"
    assert "count_matches" in plane5.evidence["failed_checks"]
    _others_still_pass(planes, target=5)


def test_transposed_traces_fail_g2c_and_g2d_together(fresh):
    """NEGATIVE CONTROL: two traces swapped. Spec §7 G7 minimum set.

    Swapping two whole traces moves both headers and samples, so Planes 3 **and** 4
    must fail. That is not an over-broad checker: the corruption genuinely touches both
    planes, and a control that demanded only one fail would be asserting the wrong
    thing. Planes 1, 2 and 5 must still pass - the file headers are untouched and the
    cardinality is unchanged.
    """
    source, store, result = fresh
    group = zarr.open_group(str(store), mode="r+")
    for name in ("headers", "amplitude"):
        data = group[name][:]
        first, second = data[0, 0].copy(), data[0, 1].copy()
        data[0, 0], data[0, 1] = second, first
        group[name][:] = data

    planes = _all_planes(source.path, store, result.spec.segy_spec)
    by_plane = {p.plane: p for p in planes}
    assert by_plane[3].status == "FAIL"
    assert by_plane[4].status == "FAIL"
    assert by_plane[1].passed and by_plane[2].passed and by_plane[5].passed


def test_a_duplicate_index_tuple_is_surfaced_not_absorbed(article):
    """NEGATIVE CONTROL for §4.6's most dangerous case.

    A duplicate is data loss: one trace is absent from the store and nothing records
    that it existed. The map must preserve both colliding ordinals rather than resolve
    them.
    """
    source, store, result = article
    from segy import SegyFile

    handle = SegyFile(str(source.path), spec=result.spec.segy_spec)
    headers = handle.header[:]
    headers["crossline"][5] = headers["crossline"][4]

    group = zarr.open_group(str(store), mode="r")
    trace_map = build_trace_map(
        headers, {"inline": group["inline"][:], "crossline": group["crossline"][:]}
    )
    assert trace_map.duplicates
    assert not trace_map.invertible
    collided = next(iter(trace_map.duplicates.values()))
    assert 4 in collided and 5 in collided


# ---------------------------------------------------------------------------
# G3 round trip
# ---------------------------------------------------------------------------


def test_g3_round_trip_is_byte_identical(fresh):
    """SEG-Y -> MDIO -> SEG-Y, whole-file SHA-256."""
    source, store, result = fresh
    back = store.parent / "back.sgy"
    roundtrip = export(store, back, result.spec.segy_spec, source=source.path)
    assert roundtrip.status == "PASS"
    assert roundtrip.byte_identical
    assert roundtrip.source_sha256 == roundtrip.export_sha256
    assert roundtrip.export_bytes == 14640
    assert roundtrip.first_difference() is None


def test_g3_localises_a_difference_by_segy_region(fresh):
    """NEGATIVE CONTROL: a corrupted export must fail and say where."""
    source, store, result = fresh
    back = store.parent / "back.sgy"
    roundtrip = export(store, back, result.spec.segy_spec, source=source.path)

    payload = bytearray(back.read_bytes())
    payload[3700] ^= 0x01
    back.write_bytes(bytes(payload))

    from sdip.provenance.hashing import sha256_file

    roundtrip.export_sha256 = sha256_file(back)
    assert not roundtrip.byte_identical
    assert roundtrip.status == "FAIL"
    difference = roundtrip.first_difference()
    assert difference["offset"] == 3700
    assert "trace data" in difference["region"]


def test_a_scoped_roundtrip_is_not_a_pass(fresh):
    """ROUNDTRIP-SCOPED requires a written justification and is still not byte-identity."""
    source, store, result = fresh
    back = store.parent / "back.sgy"
    roundtrip = export(
        store,
        back,
        result.spec.segy_spec,
        source=source.path,
        scoped={"non_conformance": "test", "justification": "x" * 50},
    )
    roundtrip.export_sha256 = "0" * 64
    assert roundtrip.status == "ROUNDTRIP-SCOPED"
    assert roundtrip.passed is False


# ---------------------------------------------------------------------------
# G4 portability
# ---------------------------------------------------------------------------


def test_g4_opens_the_store_without_mdio(article):
    """§10.3 — the gate that makes adopting SDIP reversible."""
    _, store, _ = article
    result = g4(store)
    assert result.status == "PASS"
    assert result.mdio_absent, "the checking process must never import mdio"
    assert result.report["steps"]["zarr_open_group"]
    assert result.report["steps"]["xarray_open_zarr"]
    assert result.unreadable_arrays == []


def test_g4_records_non_core_dtypes(article):
    """OPEN_DEBTS D3 / probe P4, measured from zarr.json with no warning involved."""
    _, store, _ = article
    result = g4(store)
    assert "headers" in result.non_core_arrays
    assert result.report["arrays"]["amplitude"]["zarr_v3_core_spec"] is True
    assert "NOT measured here" in result.to_json()["note"]


# ---------------------------------------------------------------------------
# Certificate with the full chain
# ---------------------------------------------------------------------------


def test_certificate_is_still_provisional_with_every_plane_passing(fresh):
    """The whole point of G7 being in the verdict condition.

    Five planes pass, G1 passes, G3 passes, G4 passes - and the verdict is still
    PROVISIONAL, because G7 has never run. An engine that has never been shown capable
    of failing cannot certify equivalence.
    """
    source, store, result = fresh
    planes = _all_planes(source.path, store, result.spec.segy_spec)
    roundtrip = export(store, store.parent / "rt.sgy", result.spec.segy_spec, source=source.path)
    portability = g4(store)
    certificate = issue(
        result,
        planes,
        roundtrip=roundtrip,
        portability=portability,
        require_clean_tree=False,
        issued_at=ISSUED_AT,
        issued_by="test",
    )
    payload = certificate.payload
    assert [p.status for p in planes] == ["PASS"] * 5
    assert payload["gates"] == {
        "G1": "PASS",
        "G2": "PASS",
        "G3": "PASS",
        "G4": "PASS",
        "G5": "NOT_RUN",
        "G6": "NOT_RUN",
        "G7": "NOT_RUN",
    }
    assert payload["verdict"] == "PROVISIONAL"
    assert "G7 has not run" in payload["verdict_reason"]
    assert "D11" in payload["verdict_reason"]


def test_g2_is_not_pass_until_all_five_planes_run(fresh):
    """Four passing planes and one unrun is not a passing G2.

    The unrun one is exactly where a defect would hide.
    """
    source, store, result = fresh
    partial = _all_planes(source.path, store, result.spec.segy_spec)[:4]
    certificate = issue(
        result, partial, require_clean_tree=False, issued_at=ISSUED_AT, issued_by="test"
    )
    assert certificate.payload["gates"]["G2"] == "NOT_RUN"
    assert certificate.payload["verdict"] == "PROVISIONAL"
