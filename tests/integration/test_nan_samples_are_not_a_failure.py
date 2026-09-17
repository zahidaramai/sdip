"""A correct store carrying NaN samples passes Plane 4 and G6; a changed NaN still fails.

Measured before D-0088 on this fixture: Plane 4 FAIL with ``expected: nan, observed: nan`` and G6
FAIL "values differ in amplitude" on two identical ingests.
"""

from __future__ import annotations

import struct
from pathlib import Path

import numpy as np
import pytest
import zarr

from sdip.equivalence.determinism import g6
from sdip.equivalence.planes import plane_4
from sdip.ingest import ingest
from sdip.spec import build_gap_free_spec
from sdip.spec.declaration import SurveyDeclaration
from tests.fixtures.generators.poststack3d import make_poststack3d

REV1 = SurveyDeclaration(revision=1, template="PostStack3DTime")

N_IL, N_XL, NS = 3, 4, 8


@pytest.fixture
def ieee_specials(tmp_path: Path) -> Path:
    """IEEE float32 samples including NaN, +inf, -inf and -0.0 (format code 5)."""
    fixture = make_poststack3d(tmp_path / "ibm.sgy", n_inline=N_IL, n_crossline=N_XL, n_samples=NS)
    data = bytearray(fixture.path.read_bytes())
    data[3224:3226] = struct.pack(">h", 5)
    specials = [np.nan, np.inf, -np.inf, -0.0]
    for trace in range(N_IL * N_XL):
        base = 3600 + trace * (240 + NS * 4) + 240
        for sample in range(NS):
            value = (
                specials[(trace + sample) % 4] if sample < 2 else float(trace * 4 + sample * 0.25)
            )
            data[base + sample * 4 : base + sample * 4 + 4] = struct.pack(">f", value)
    source = tmp_path / "ieee_specials.sgy"
    source.write_bytes(bytes(data))
    return source


def test_plane_4_passes_a_correct_store_carrying_nan(tmp_path, ieee_specials):
    store = tmp_path / "s.mdio"
    ingest(ieee_specials, store)
    result = plane_4(ieee_specials, store, build_gap_free_spec(1).segy_spec)
    assert result.status == "PASS", result.evidence.get("first_difference")


def test_g6_calls_two_identical_ingests_identical(tmp_path, ieee_specials):
    result = g6(ieee_specials, declaration=REV1, workdir=tmp_path / "g6")
    assert result.status == "PASS", result.summary()


def test_a_nan_with_a_different_payload_still_fails_plane_4(tmp_path, ieee_specials):
    store = tmp_path / "s.mdio"
    ingest(ieee_specials, store)
    array = zarr.open_group(str(store), mode="r+")["amplitude"]
    volume = np.asarray(array[:])
    nan_cells = np.argwhere(np.isnan(volume))
    cell = tuple(nan_cells[0])
    volume[cell] = np.array([0x7F800001], dtype=np.uint32).view(np.float32)[0]
    array[:] = volume
    result = plane_4(ieee_specials, store, build_gap_free_spec(1).segy_spec)
    assert result.status == "FAIL"
