"""D56: scaled source and group coordinates are verified, or refuse release as unverified.

**Maintainer ruling (DECISIONS.md D-0088), an explicit exception to Ruling 7.** MDIO scales
``source_coord_x/y`` and ``group_coord_x/y`` (bytes 73-88) with the same scalar as
``cdp_x/cdp_y``, and Plane 3 checked only the latter. These are the shot and receiver positions a
full-waveform consumer needs. None of the geometries can be ingested through SDIP yet, so the
stores here are built through the pinned upstream exactly as probe P7 builds them.

Measured before this change: three of the five geometries that carry them are mappable, all
four arrays addressable in each; the other two are refused by Plane 3 outright because a
calculated grid dimension has no coordinate array. And every P7 fixture used scalar 1 on round
coordinates, where no arithmetic can disagree — so the sweep below asserts that its own fixture
DOES put values off the correctly rounded quotient, or it is proving nothing.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import zarr

from sdip.equivalence.planes import plane_3
from sdip.spec.transforms import COORD_ARRAYS
from tests.fixtures.generators.poststack3d import make_poststack3d
from tests.fixtures.generators.prestack import GEOMETRIES, make_prestack
from tests.integration.test_p7_prestack import _upstream_leg

SOURCE_GROUP = {"source_coord_x", "source_coord_y", "group_coord_x", "group_coord_y"}
MAPPABLE = ("streamer_shot_3d", "streamer_shot_2d")


def _store(tmp_path: Path, name: str, scalar: int):  # noqa: ANN202
    geom = next(g for g in GEOMETRIES if g.name == name)
    article = make_prestack(
        geom, tmp_path / f"{name}.sgy", coordinate_scalar=scalar, coordinate_residues=True
    )
    store = tmp_path / f"{name}.mdio"
    ok, err = _upstream_leg(article, store)
    assert ok, err
    return article, store


def test_the_verified_arrays_are_exactly_the_ones_the_writer_scales():
    """Drift: a future MDIO that scales another array fails here until it is verified."""
    from mdio.segy.scalar import SCALE_COORDINATE_KEYS

    assert set(COORD_ARRAYS) == set(SCALE_COORDINATE_KEYS)


@pytest.mark.parametrize("scalar", [-100, -1000])
@pytest.mark.parametrize("name", MAPPABLE)
def test_source_and_group_coordinates_are_verified_exactly(tmp_path, name, scalar):
    article, store = _store(tmp_path, name, scalar)
    result = plane_3(article.path, store, article.spec(), g1_passed=True)
    evidence = result.evidence
    assert SOURCE_GROUP <= set(evidence["derived_coords_arrays"]), evidence
    assert evidence["derived_coords_mismatch_count"] == 0, evidence[
        "derived_coords_first_difference"
    ]
    assert result.status == "PASS"
    # The fixture must exercise the arithmetic: some values must sit off the quotient.
    assert evidence["derived_coords_standard_quotient_differences"] > 0


def test_a_one_ulp_corruption_of_a_group_coordinate_fails(tmp_path):
    article, store = _store(tmp_path, "streamer_shot_3d", -100)
    array = zarr.open_group(str(store), mode="r+")["group_coord_x"]
    values = np.asarray(array[:])
    flat = values.reshape(-1)
    flat[0] = np.nextafter(flat[0], np.inf)
    array[:] = flat.reshape(values.shape)
    result = plane_3(article.path, store, article.spec(), g1_passed=True)
    assert result.status == "FAIL"
    assert any(
        e["array"] == "group_coord_x" for e in result.evidence["derived_coords_mismatch_examples"]
    )


def test_a_scaled_array_that_cannot_be_verified_blocks_release(tmp_path):
    """NOT CHECKED is never checked-and-passed, and never releasable."""
    from sdip.ingest import ingest
    from sdip.spec import build_gap_free_spec

    source = make_poststack3d(tmp_path / "s.sgy", n_inline=3, n_crossline=4, n_samples=16).path
    store = tmp_path / "s.mdio"
    ingest(source, store)
    group = zarr.open_group(str(store), mode="r+")
    group.create_array("source_coord_x", shape=(2,), dtype="float64", dimension_names=["bogus"])

    result = plane_3(source, store, build_gap_free_spec(1).segy_spec, g1_passed=True)
    findings = {f["code"]: f for f in result.evidence.get("findings", [])}
    assert findings["derived_coordinate_unverified"]["blocks_release"] is True
    assert "source_coord_x" in findings["derived_coordinate_unverified"]["arrays"]
    assert result.status == "PASS", "the arrays that could be checked still decide the plane"
    assert result.evidence["derived_coords_mismatch_count"] == 0
