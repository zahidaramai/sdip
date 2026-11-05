"""``sdip-content-digest/2``: the reproducibility claim at survey scale (D75, P31, D-0135).

``/1`` less one member, ``amplitude``'s ``statsV1.sumSquares``, the only key besides root
``createdOn`` that probe P31 saw varying across 13 ingests. Recorded beside ``/1`` in
``sdipStoreDigest.contentV2``; ``/1`` is never changed.

**Passing half (D-0088), through the ``sdip`` executable.** Two ingests record the same ``/2``.
A ``sumSquares`` that differs, as P31 measured it differing at 1.60 GB, moves ``/1`` and leaves
``/2`` MATCH. Neither does a ``createdOn`` that differs. ``verify --json`` reports ``/2``.

**Failing half.** Every other change still fails ``/2``:
- a ``statsV1`` member P31 never saw varying (``sum``);
- a flipped ``amplitude`` chunk byte;
- an edited ``amplitude`` attribute outside ``statsV1``.

A store written before ``/2`` reports ``ABSENT`` and fails nothing, and the store digest and
``/1`` of such a store are unchanged by ``/2``'s presence.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import zarr

from sdip.ingest.provenance_marker import (
    ATTR_STORE_DIGEST,
    CONTENT_V2_FIELD,
    recorded_content_digest_v2,
)
from sdip.provenance.store_digest import (
    ABSENT,
    CONTENT_SCHEME_V2,
    MATCH,
    MISMATCH,
    check_content_digest,
    check_content_digest_v2,
    check_store_digest,
)
from tests.fixtures.generators.poststack3d import make_poststack3d

pytestmark = pytest.mark.integration

SDIP = str(Path(sys.executable).parent / "sdip")


def _ingest(source: Path, store: Path) -> None:
    proc = subprocess.run(
        [SDIP, "ingest", str(source), str(store)], capture_output=True, text=True, check=False
    )
    assert proc.returncode == 0, proc.stderr[-2000:]


@pytest.fixture(scope="module")
def built(tmp_path_factory) -> tuple[Path, Path]:
    root = tmp_path_factory.mktemp("v2")
    source = make_poststack3d(root / "src.sgy").path
    store = root / "a.mdio"
    _ingest(source, store)
    return source, store


@pytest.fixture
def copy(built, tmp_path) -> Path:
    target = tmp_path / "copy.mdio"
    shutil.copytree(built[1], target)
    return target


def _edit_stats(store: Path, member: str, delta: float) -> None:
    array = zarr.open_group(str(store), mode="r+")["amplitude"]
    stats: dict[str, Any] = json.loads(array.attrs["statsV1"])
    stats[member] = float(stats[member]) + delta
    array.attrs["statsV1"] = json.dumps(stats)


def test_a_fresh_store_records_v2_beside_v1_and_matches(built):
    _source, store = built
    group = zarr.open_group(str(store), mode="r")
    block = dict(group.attrs)[ATTR_STORE_DIGEST]
    assert block[CONTENT_V2_FIELD]["scheme"] == CONTENT_SCHEME_V2
    assert block["content"]["scheme"] == "sdip-content-digest/1"
    assert block[CONTENT_V2_FIELD]["sha256"] != block["content"]["sha256"]
    assert check_content_digest_v2(store).status == MATCH
    assert check_content_digest(store).status == MATCH
    assert check_store_digest(store).status == MATCH


def test_two_ingests_record_the_same_v2(built, tmp_path):
    source, store = built
    _ingest(source, tmp_path / "b.mdio")
    first = recorded_content_digest_v2(zarr.open_group(str(store), mode="r"))
    second = recorded_content_digest_v2(zarr.open_group(str(tmp_path / "b.mdio"), mode="r"))
    assert first is not None and second is not None
    assert first["sha256"] == second["sha256"]


def test_a_different_sum_of_squares_moves_v1_and_not_v2(copy):
    """P31's variation, reproduced on purpose: the value differs, the data do not."""
    _edit_stats(copy, "sumSquares", 8192.0)
    v1, v2 = check_content_digest(copy), check_content_digest_v2(copy)
    assert v1.status == MISMATCH
    assert v2.status == MATCH, v2.changed


def test_a_different_created_on_moves_neither_content_digest(copy):
    zarr.open_group(str(copy), mode="r+").attrs["createdOn"] = "1970-01-01 00:00:00+00:00"
    assert check_content_digest(copy).status == MATCH
    assert check_content_digest_v2(copy).status == MATCH
    assert check_store_digest(copy).status == MISMATCH


def test_a_different_sum_fails_v2(copy):
    """``sum`` never varied in P31, so it stays covered."""
    _edit_stats(copy, "sum", 1.0)
    result = check_content_digest_v2(copy)
    assert result.status == MISMATCH
    assert "amplitude changed" in result.changed


def test_a_flipped_amplitude_chunk_byte_fails_v2(copy):
    chunk = next(
        p for p in sorted((copy / "amplitude").rglob("*")) if p.name != "zarr.json" and p.is_file()
    )
    raw = bytearray(chunk.read_bytes())
    raw[len(raw) // 2] ^= 0x01
    chunk.write_bytes(bytes(raw))
    result = check_content_digest_v2(copy)
    assert result.status == MISMATCH
    assert "amplitude changed" in result.changed


def test_an_edited_amplitude_attribute_outside_stats_fails_v2(copy):
    zarr.open_group(str(copy), mode="r+")["amplitude"].attrs["coordinates"] = "x y"
    assert check_content_digest_v2(copy).status == MISMATCH


def test_a_store_written_before_v2_is_absent_and_nothing_else_moves(copy):
    group = zarr.open_group(str(copy), mode="r+")
    block = dict(group.attrs[ATTR_STORE_DIGEST])
    del block[CONTENT_V2_FIELD]
    group.attrs[ATTR_STORE_DIGEST] = block
    result = check_content_digest_v2(copy)
    assert result.status == ABSENT
    assert result.passed
    assert check_content_digest(copy).status == MATCH
    assert check_store_digest(copy).status == MATCH


def test_verify_reports_v2_through_the_executable(built):
    source, store = built
    proc = subprocess.run(
        [SDIP, "verify", "--json", "--skip-portability", str(source), str(store)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr[-2000:]
    report = json.loads(proc.stdout)
    assert report["content_digest_v2"]["status"] == MATCH
    assert report["content_digest_v2"]["scheme"] == CONTENT_SCHEME_V2
    assert report["content_digest"]["status"] == MATCH
