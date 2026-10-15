"""Negative controls for the axis origin (D-0096, SP11): Plane 4 must catch every lie.

The marker says which convention the writer followed; Plane 4 derives the origin from the
source. Each control breaks the agreement one way, and each must fail **Plane 4** while
Planes 1, 2, 3 and 5 still PASS:

* the claim removed from a shifted store - the expectation reverts to 0 and the axis does
  not start there;
* the claimed origin changed - it disagrees with the source;
* the axis put back to 0 under an intact claim - the axis disagrees with the source;
* a claim forged onto a store whose source has no delay - the source supports no shift.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import zarr

from sdip.equivalence.planes import plane_1, plane_2, plane_3, plane_4, plane_5
from sdip.ingest import ingest
from sdip.ingest.provenance_marker import ATTR_SAMPLE_AXIS_ORIGIN
from sdip.spec.declaration import SurveyDeclaration
from tests.fixtures.generators.poststack3d import make_poststack3d

DECLARATION = SurveyDeclaration(revision=1, template="PostStack3DTime")


@pytest.fixture(scope="module")
def stores(tmp_path_factory):
    work = tmp_path_factory.mktemp("axis_controls")
    delayed = make_poststack3d(work / "delayed.sgy", delay_recording_time=4).path
    plain = make_poststack3d(work / "plain.sgy").path
    ingest(delayed, work / "delayed.mdio")
    ingest(plain, work / "plain.mdio")
    return {"delayed": (delayed, work / "delayed.mdio"), "plain": (plain, work / "plain.mdio")}


def _copy(store: Path, tmp_path: Path) -> Path:
    target = tmp_path / "corrupt.mdio"
    shutil.copytree(store, target)
    return target


def _set_attrs(store: Path, **changes: Any) -> None:
    group = zarr.open_group(str(store), mode="r+")
    attrs = dict(group.attrs)
    for key, value in changes.items():
        if value is None:
            attrs.pop(key, None)
        else:
            attrs[key] = value
    group.attrs.clear()
    group.attrs.update(attrs)


def _assert_only_plane_4_fails(source: Path, store: Path) -> None:
    spec = DECLARATION.build_spec().segy_spec
    fourth = plane_4(source, store, spec)
    assert fourth.status == "FAIL", fourth.evidence
    assert fourth.evidence["derived_axis_identical"] is False
    others = [
        plane_1(source, store),
        plane_2(source, store, declaration=DECLARATION),
        plane_3(source, store, spec, g1_passed=True),
        plane_5(source, store, spec),
    ]
    assert [p.status for p in others] == ["PASS"] * 4, [(p.plane, p.status) for p in others]


def test_the_clean_stores_pass(stores):
    """The baseline: without it, every control below could pass against a broken plane."""
    spec = DECLARATION.build_spec().segy_spec
    for source, store in stores.values():
        assert plane_4(source, store, spec).status == "PASS"


def test_removing_the_claim_from_a_shifted_store_fails_plane_4(stores, tmp_path):
    source, store = stores["delayed"]
    copy = _copy(store, tmp_path)
    _set_attrs(copy, **{ATTR_SAMPLE_AXIS_ORIGIN: None})
    _assert_only_plane_4_fails(source, copy)


def test_a_claimed_origin_the_source_does_not_carry_fails_plane_4(stores, tmp_path):
    source, store = stores["delayed"]
    copy = _copy(store, tmp_path)
    claim = dict(zarr.open_group(str(copy), mode="r").attrs)[ATTR_SAMPLE_AXIS_ORIGIN]
    _set_attrs(copy, **{ATTR_SAMPLE_AXIS_ORIGIN: claim | {"origin_ms": 8.0}})
    _assert_only_plane_4_fails(source, copy)


def test_an_axis_put_back_to_zero_under_the_claim_fails_plane_4(stores, tmp_path):
    source, store = stores["delayed"]
    copy = _copy(store, tmp_path)
    axis = zarr.open_array(str(copy), path="time", mode="r+")
    axis[...] = np.asarray(axis[...]) - 4
    _assert_only_plane_4_fails(source, copy)


def test_a_claim_forged_onto_an_undelayed_store_fails_plane_4(stores, tmp_path):
    source, store = stores["plain"]
    copy = _copy(store, tmp_path)
    forged = {"axis": "time", "origin_ms": 0.0, "source": "forged", "decision": "D-0096"}
    _set_attrs(copy, **{ATTR_SAMPLE_AXIS_ORIGIN: forged})
    _assert_only_plane_4_fails(source, copy)
