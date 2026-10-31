"""D71 and D72 (probe P19): export writes back the stored binary header and the source order.

Both halves (D-0088): sources the fixes exist for round-trip byte-identically, and a store
whose recorded header or order is corrupted exports a file that is NOT the source.
"""

from __future__ import annotations

import base64
import shutil
from pathlib import Path

import numpy as np
import pytest
import zarr

from sdip.export.roundtrip import GRID_ORDER_NON_CONFORMANCE, RoundTripResult, export
from sdip.ingest import ingest
from sdip.ingest.file_headers import ATTR_RAW_BINARY, raw_header_node
from sdip.ingest.header_plane import ORDINAL_ARRAY_NAME
from tests.fixtures.generators.poststack3d import make_poststack3d
from tests.fixtures.generators.roundtrip_sources import (
    make_reversed_order,
    make_unassigned_and_reversed,
    make_unassigned_binary,
)

pytestmark = [pytest.mark.integration]

BUILDERS = {
    "B1_unassigned_binary": make_unassigned_binary,
    "B2_reversed_order": make_reversed_order,
    "B3_both": make_unassigned_and_reversed,
}


def _round_trip(tmp_path: Path, source: Path) -> tuple[RoundTripResult, Path]:
    store = tmp_path / "store.mdio"
    built = ingest(source, store)
    return export(store, tmp_path / "export.sgy", built.spec.segy_spec, source=source), store


@pytest.mark.parametrize("name", sorted(BUILDERS))
def test_each_source_round_trips_byte_identically(tmp_path, name):
    source = BUILDERS[name](tmp_path / f"{name}.sgy")
    result, _ = _round_trip(tmp_path, source)
    assert result.byte_identical, result.first_difference()
    assert result.status == "PASS"


def test_the_well_formed_file_needs_nothing_restored(tmp_path):
    source = make_poststack3d(tmp_path / "wf.sgy").path
    result, _ = _round_trip(tmp_path, source)
    assert result.byte_identical
    assert result.restored == {
        "binary_header_bytes": [],
        "trace_order": "source",
        "traces_moved": 0,
    }


def test_the_restored_bytes_are_named(tmp_path):
    source = make_unassigned_binary(tmp_path / "b1.sgy")
    result, _ = _round_trip(tmp_path, source)
    assert result.restored["binary_header_bytes"] == list(range(307, 401))


def test_a_reversed_source_moves_every_record(tmp_path):
    source = make_reversed_order(tmp_path / "b2.sgy")
    result, store = _round_trip(tmp_path, source)
    assert result.restored["trace_order"] == "source"
    assert result.restored["traces_moved"] == 30
    ordinals = np.asarray(zarr.open_group(str(store), mode="r")[ORDINAL_ARRAY_NAME][...])
    assert sorted(ordinals.ravel().tolist()) == list(range(30))


def test_a_corrupted_stored_binary_header_is_what_export_writes(tmp_path):
    """NEGATIVE CONTROL for D71: export writes the store's bytes, so a wrong byte shows."""
    source = make_poststack3d(tmp_path / "wf.sgy").path
    store = tmp_path / "store.mdio"
    built = ingest(source, store)
    node = raw_header_node(zarr.open_group(str(store), mode="r+"))
    raw = bytearray(base64.b64decode(node.attrs[ATTR_RAW_BINARY]))
    raw[367] ^= 0xFF
    node.attrs[ATTR_RAW_BINARY] = base64.b64encode(bytes(raw)).decode("ascii")
    result = export(store, tmp_path / "e.sgy", built.spec.segy_spec, source=source)
    assert not result.byte_identical
    assert result.restored["binary_header_bytes"] == [368]
    assert result.first_difference()["offset"] == 3200 + 367


def test_swapped_ordinals_export_a_file_that_is_not_the_source(tmp_path):
    """NEGATIVE CONTROL for D72: a wrong recorded order is a wrong file, and G3 says so."""
    source = make_reversed_order(tmp_path / "b2.sgy")
    store = tmp_path / "store.mdio"
    built = ingest(source, store)
    group = zarr.open_group(str(store), mode="r+")
    ordinals = np.asarray(group[ORDINAL_ARRAY_NAME][...])
    ordinals[0, 0], ordinals[0, 1] = ordinals[0, 1], ordinals[0, 0]
    group[ORDINAL_ARRAY_NAME][...] = ordinals
    result = export(store, tmp_path / "e.sgy", built.spec.segy_spec, source=source)
    assert not result.byte_identical
    assert result.status == "FAIL"


def test_a_store_without_recorded_order_is_scoped_to_grid_order(tmp_path):
    """Pass criterion C: no recorded order, order the only difference -> ROUNDTRIP-SCOPED."""
    from sdip.ingest.provenance_marker import ATTR_MITIGATIONS

    source = make_reversed_order(tmp_path / "b2.sgy")
    store = tmp_path / "store.mdio"
    built = ingest(source, store)
    shutil.rmtree(store / ORDINAL_ARRAY_NAME)
    group = zarr.open_group(str(store), mode="r+")
    group.attrs[ATTR_MITIGATIONS] = ["headers_raw_uint8"]
    result = export(store, tmp_path / "e.sgy", built.spec.segy_spec, source=source)
    assert not result.byte_identical
    assert result.status == "ROUNDTRIP-SCOPED"
    assert result.scoped["non_conformance"] == GRID_ORDER_NON_CONFORMANCE
    assert result.restored["trace_order"] == "grid"


def test_grid_order_scope_is_refused_when_more_than_order_differs(tmp_path):
    """The scope is for order only: a changed byte on top keeps G3 a FAIL."""
    source = make_reversed_order(tmp_path / "b2.sgy")
    store = tmp_path / "store.mdio"
    built = ingest(source, store)
    shutil.rmtree(store / ORDINAL_ARRAY_NAME)
    tampered = tmp_path / "tampered.sgy"
    payload = bytearray(source.read_bytes())
    payload[-1] ^= 0x01
    tampered.write_bytes(bytes(payload))
    result = export(store, tmp_path / "e.sgy", built.spec.segy_spec, source=tampered)
    assert result.status == "FAIL"
