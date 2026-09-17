"""Every mismatch count on a certificate is the real count (OPEN_DEBTS D52 audit, D-0088).

D50 found the derived-coordinate leg appending at most 20 mismatches and reporting that list's
length as the count. Auditing every check for the same shape found three more: Plane 3's
raw-header leg, Plane 3's field comparison and Plane 4's sample comparison each BROKE OUT of
the loop at 20 — which also stopped the counter of traces compared, so a failing certificate
reported a truncated ``n`` beside ``"sampling": "exhaustive"``. The verdicts were right; the
numbers were not (SP8). Here 25 of 30 traces are corrupted in each leg and every count must say so.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import zarr

from sdip.equivalence.planes import plane_3, plane_4
from sdip.ingest import ingest
from sdip.spec import build_gap_free_spec
from tests.fixtures.generators.poststack3d import make_poststack3d

CORRUPTED = 25


@pytest.fixture
def ingested(tmp_path: Path) -> tuple[Path, Path, zarr.Group]:
    source = make_poststack3d(tmp_path / "s.sgy", n_inline=5, n_crossline=6, n_samples=16).path
    store = tmp_path / "s.mdio"
    ingest(source, store)
    return source, store, zarr.open_group(str(store), mode="r+")


def _first_cells(shape: tuple[int, ...], k: int) -> list[tuple[int, ...]]:
    grid = shape[:2]
    return [np.unravel_index(i, grid) for i in range(k)]


def test_plane_4_counts_every_trace_with_a_differing_sample(ingested):
    source, store, group = ingested
    volume = group["amplitude"][:]
    for il, xl in _first_cells(volume.shape, CORRUPTED):
        volume[il, xl, 0] = np.nextafter(volume[il, xl, 0], np.float32(np.inf))
    group["amplitude"][:] = volume

    evidence = plane_4(source, store, build_gap_free_spec(1).segy_spec).evidence
    assert evidence["mismatch_count"] == CORRUPTED
    assert evidence["n"] == 30
    assert len(evidence["mismatch_examples"]) == 20


def test_plane_3_counts_every_differing_field(ingested):
    source, store, group = ingested
    headers = group["headers"][:]
    for il, xl in _first_cells(headers.shape, CORRUPTED):
        headers["pad_240"][il, xl] = (int(headers["pad_240"][il, xl]) + 1) % 256
    group["headers"][:] = headers

    evidence = plane_3(source, store, build_gap_free_spec(1).segy_spec, g1_passed=True).evidence
    assert evidence["mismatch_count"] == CORRUPTED
    assert evidence["n"] == 30


def test_the_raw_header_leg_counts_every_trace_with_a_differing_byte(ingested):
    source, store, group = ingested
    plane = group["headers_raw_uint8"][:]
    for il, xl in _first_cells(plane.shape, CORRUPTED):
        plane[il, xl, 239] = np.uint8(int(plane[il, xl, 239]) ^ 1)
    group["headers_raw_uint8"][:] = plane

    evidence = plane_3(source, store, build_gap_free_spec(1).segy_spec, g1_passed=True).evidence
    assert evidence["raw_header_mismatch_count"] == CORRUPTED
    assert evidence["raw_header_n"] == 30
