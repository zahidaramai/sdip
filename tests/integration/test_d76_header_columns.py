"""D76 (probe P33): ingest reads only the header columns it uses, in blocks.

``read_header_columns`` replaces three whole ``header[:]`` reads in ``sdip ingest``. What it
returns must be what the whole read held for those fields, across block boundaries, so the
block size is shrunk here to 7 traces to force many of them. The checks:
- equality on a regular grid, a sparse grid and a varying recording delay;
- the same trace map and the same axis-origin decision as the whole read;
- a field the spec lacks stays absent;
- one changed source header byte shows up in the columns (the read is of the file, not of a
  cache).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import zarr
from segy import SegyFile

from sdip.equivalence.planes import grid_coordinates, store_dimensions
from sdip.equivalence.trace_map import build_trace_map
from sdip.ingest import ingest, source_headers
from sdip.ingest.sample_axis import DELAY_FIELD, SCALAR_FIELD, axis_origin
from sdip.ingest.source_headers import read_header_columns
from sdip.spec.declaration import SurveyDeclaration
from tests.fixtures.generators import make_poststack3d
from tests.fixtures.generators.irregular import make_sparse_grid

pytestmark = pytest.mark.integration

SPEC = SurveyDeclaration(revision=1, template="PostStack3DTime").build_spec().segy_spec
FIELDS = ("inline", "crossline", DELAY_FIELD, SCALAR_FIELD)


@pytest.fixture(autouse=True)
def small_blocks(monkeypatch):
    monkeypatch.setattr(source_headers, "BLOCK", 7)


def _sources(root: Path) -> dict[str, Path]:
    return {
        "regular": make_poststack3d(root / "reg.sgy", n_inline=6, n_crossline=7).path,
        "sparse": make_sparse_grid(root / "sparse.sgy").path,
        "varying_delay": make_poststack3d(
            root / "delay.sgy", n_inline=3, n_crossline=5, delay_recording_time=tuple(range(15))
        ).path,
    }


@pytest.mark.parametrize("case", ["regular", "sparse", "varying_delay"])
def test_the_columns_equal_the_whole_read_across_block_boundaries(tmp_path, case):
    source = _sources(tmp_path)[case]
    whole = SegyFile(str(source), spec=SPEC).header[:]
    columns = read_header_columns(source, SPEC, FIELDS)
    assert columns.shape == (int(SegyFile(str(source), spec=SPEC).num_traces),)
    assert columns.shape[0] > 7, "the fixture must span more than one block"
    for name in FIELDS:
        assert np.array_equal(np.asarray(whole[name]), columns[name]), name
        assert columns.dtype[name] == whole.dtype[name]


@pytest.mark.parametrize("case", ["regular", "sparse"])
def test_the_trace_map_from_columns_is_the_whole_reads(tmp_path, case):
    source = _sources(tmp_path)[case]
    store = tmp_path / f"{case}.mdio"
    ingest(source, store)
    group = zarr.open_group(str(store), mode="r")
    dims = store_dimensions(group)
    coords = grid_coordinates(group, dims)
    a = build_trace_map(SegyFile(str(source), spec=SPEC).header[:], coords, dims)
    b = build_trace_map(read_header_columns(source, SPEC, dims), coords, dims)
    assert a.ordinal_to_cell == b.ordinal_to_cell
    assert a.cell_to_ordinals == b.cell_to_ordinals
    assert a.unmapped == b.unmapped


@pytest.mark.parametrize("delay", [0, 4, tuple(range(15))])
def test_the_axis_origin_decision_is_the_whole_reads(tmp_path, delay):
    source = make_poststack3d(
        tmp_path / "d.sgy", n_inline=3, n_crossline=5, delay_recording_time=delay
    ).path
    whole = axis_origin(SegyFile(str(source), spec=SPEC).header[:], "time", np.int32)
    blocked = axis_origin(
        read_header_columns(source, SPEC, (DELAY_FIELD, SCALAR_FIELD)), "time", np.int32
    )
    assert blocked == whole


def test_a_field_the_spec_lacks_stays_absent(tmp_path):
    source = _sources(tmp_path)["regular"]
    columns = read_header_columns(source, SPEC, ("inline", "no_such_field", "inline"))
    assert columns.dtype.names == ("inline",)


def test_one_changed_header_byte_shows_up_in_the_columns(tmp_path):
    source = _sources(tmp_path)["regular"]
    before = read_header_columns(source, SPEC, ("inline",))["inline"].copy()
    raw = bytearray(source.read_bytes())
    trace, stride = 9, 240 + 32 * 4
    raw[3600 + trace * stride + 191] ^= 0x01  # last byte of inline (bytes 189-192)
    source.write_bytes(bytes(raw))
    after = read_header_columns(source, SPEC, ("inline",))["inline"]
    assert int(after[trace]) != int(before[trace])
    assert np.array_equal(np.delete(after, trace), np.delete(before, trace))
