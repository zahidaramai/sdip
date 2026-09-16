"""A correct store PASSES the derived-coordinate leg across the whole value space.

**The one-sided discipline this closes (DECISIONS.md D-0087).** Every G7 control proves a
gate FAILS a corrupted store. Nothing proved a gate PASSES a correct one across the values
real data carries — and the leg shipped comparing against a formula the writer does not
use. It passed every test and the survey-scale certificate, because the synthetic fixture
used multiples of 25 and the survey's coordinates happened to avoid the 12-16 disagreeing
residues. Its first run on a survey that did not was a false FAIL.

So this is the specificity half: real ingests of coordinates covering all 100 final-two-
digit residues at two magnitudes, under every negative scalar the standard allows, must
pass. Then the sensitivity half, made stricter: a one-ulp corruption must fail, the count
must be the real count, and a varying scalar — which MDIO applies from the first trace
only — must fail, because the stored coordinates are then wrong by the standard.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import numpy as np
import pytest
import zarr

from sdip.equivalence.planes import plane_3
from sdip.ingest import ingest
from sdip.spec import build_gap_free_spec
from tests.fixtures.generators.irregular import IrregularSegy, make_irregular

PAIRS = [(100 + i, 200 + j) for i in range(10) for j in range(10)]
COORDINATES = [(43_636_400 + k, 646_920_000 + (99 - k)) for k in range(100)]


def _ingest(tmp_path: Path, name: str, **kwargs: object) -> tuple[IrregularSegy, Path]:
    fixture = make_irregular(tmp_path / f"{name}.sgy", index_pairs=PAIRS, **kwargs)
    store = tmp_path / f"{name}.mdio"
    ingest(fixture.path, store)
    return fixture, store


@pytest.mark.parametrize("scalar", [-10, -100, -1000, -10000, 10])
def test_all_100_residues_pass_under_every_scalar(tmp_path, scalar):
    fixture, store = _ingest(
        tmp_path, f"s{abs(scalar)}", coordinates=COORDINATES, coordinate_scalar=scalar
    )
    result = plane_3(fixture.path, store, build_gap_free_spec(1).segy_spec, g1_passed=True)
    evidence = result.evidence
    assert evidence["derived_coords_verified"] is True
    assert evidence["derived_coords_n"] == 200
    assert evidence["derived_coords_mismatch_count"] == 0, evidence[
        "derived_coords_first_difference"
    ]
    assert result.status == "PASS"


def test_one_ulp_still_fails_and_the_count_is_the_real_count(tmp_path):
    """Exactness kept: the fix changed the formula, not the comparison.

    25 corrupted cells must be reported as 25 — the old code capped the count at 20 and
    called that the count.
    """
    fixture, store = _ingest(tmp_path, "ulp", coordinates=COORDINATES, coordinate_scalar=-100)
    copy = tmp_path / "corrupt.mdio"
    shutil.copytree(store, copy)
    array = zarr.open_group(str(copy), mode="r+")["cdp_x"]
    values = np.asarray(array[:])
    flat = values.reshape(-1)
    flat[:25] = np.nextafter(flat[:25], np.inf)
    array[:] = flat.reshape(values.shape)

    result = plane_3(fixture.path, copy, build_gap_free_spec(1).segy_spec, g1_passed=True)
    assert result.status == "FAIL"
    assert result.evidence["derived_coords_mismatch_count"] == 25
    assert len(result.evidence["derived_coords_mismatch_examples"]) == 20


def test_a_varying_scalar_fails_because_mdio_applies_the_first_traces(tmp_path):
    """A varying scalar fails, because MDIO applies trace 0's scalar to every trace.

    SEG-Y scales each trace's coordinates by that trace's own scalar, so the stored
    coordinates are then wrong by the standard, and the leg says so.
    """
    scalars = [-100 if ordinal % 2 == 0 else -10 for ordinal in range(len(PAIRS))]
    fixture, store = _ingest(tmp_path, "vary", coordinates=COORDINATES, coordinate_scalars=scalars)
    result = plane_3(fixture.path, store, build_gap_free_spec(1).segy_spec, g1_passed=True)
    assert result.status == "FAIL"
    evidence = result.evidence
    assert evidence["derived_coords_scalar_uniform"] is False
    # Exactly the traces whose scalar differs from trace 0's, in both arrays.
    assert evidence["derived_coords_mismatch_count"] == 2 * scalars.count(-10)
    assert {e["coordinate_scalar"] for e in evidence["derived_coords_mismatch_examples"]} == {-10}
