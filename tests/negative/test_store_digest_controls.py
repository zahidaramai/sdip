"""Negative controls for the store digest (D-0093, SP11): a changed store must MISMATCH.

**The value-preserving control is the one that matters.** One chunk of ``amplitude`` is
re-encoded with a different compression level: every decoded value is identical, so all
five planes still PASS against the source, and the digest is the only check that can see
the store is no longer the one ``sdip ingest`` wrote. It fails the digest and nothing else.

The others place the digest's coverage: a flipped chunk byte, the raw file headers in an
array's metadata (the bytes a chunk-only digest would miss), an array removed or added,
and the root metadata. Each must be named in the mismatch.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
import zarr

from sdip.ingest import ingest
from sdip.provenance.store_digest import MATCH, MISMATCH, check_store_digest
from tests.fixtures.generators.poststack3d import make_poststack3d

SDIP = str(Path(sys.executable).parent / "sdip")


@pytest.fixture(scope="module")
def clean(tmp_path_factory):
    work = tmp_path_factory.mktemp("digest_controls")
    fixture = make_poststack3d(work / "clean.sgy")
    store = work / "clean.mdio"
    ingest(fixture.path, store)
    assert check_store_digest(store).status == MATCH
    return fixture.path, store


@pytest.fixture
def copy(clean, tmp_path):
    _, store = clean
    target = tmp_path / "corrupt.mdio"
    shutil.copytree(store, target)
    return target


def _first_chunk(store: Path, array: str) -> Path:
    return sorted(p for p in (store / array).rglob("*") if p.is_file() and p.name != "zarr.json")[0]


def _assert_names(store: Path, expected: str) -> None:
    result = check_store_digest(store)
    assert result.status == MISMATCH
    assert not result.passed
    assert expected in result.changed, result.changed


def test_a_value_preserving_reencode_fails_the_digest_and_only_the_digest(clean, copy):
    source, _ = clean
    # Rewrite amplitude with identical values under different codecs. Same values, same
    # shape, same chunks; different bytes on disk.
    group = zarr.open_group(str(copy), mode="r+")
    original = group["amplitude"]
    values = original[...]
    attrs = dict(original.attrs)
    dims = original.metadata.dimension_names
    del group["amplitude"]
    rewritten = group.create_array(
        "amplitude",
        shape=values.shape,
        chunks=original.chunks,
        dtype=values.dtype,
        dimension_names=dims,
        compressors=zarr.codecs.ZstdCodec(level=19),
        fill_value=original.fill_value,
    )
    rewritten[...] = values
    rewritten.attrs.update(attrs)
    assert np.array_equal(zarr.open_group(str(copy), mode="r")["amplitude"][...], values)
    _assert_names(copy, "amplitude changed")

    run = subprocess.run(
        [SDIP, "verify", "--skip-portability", str(source), str(copy)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert run.returncode == 1, run.stdout + run.stderr
    assert "[MISMATCH] store" in run.stdout
    assert "[FAIL] Plane" not in run.stdout, "the planes must not be what caught this"


def test_a_flipped_chunk_byte_is_named(copy):
    chunk = _first_chunk(copy, "amplitude")
    payload = bytearray(chunk.read_bytes())
    payload[-1] ^= 0x01
    chunk.write_bytes(bytes(payload))
    _assert_names(copy, "amplitude changed")


def test_the_raw_file_headers_in_array_metadata_are_covered(copy):
    node = zarr.open_group(str(copy), mode="r+")["segy_file_header"]
    key = next(k for k in dict(node.attrs) if "textual" in k.lower() or "Text" in k)
    value = str(node.attrs[key])
    node.attrs[key] = ("X" if value[:1] != "X" else "Y") + value[1:]
    _assert_names(copy, "segy_file_header changed")


def test_a_removed_array_is_named(copy):
    del zarr.open_group(str(copy), mode="r+")["cdp_x"]
    _assert_names(copy, "cdp_x removed")


def test_an_added_array_is_named(copy):
    zarr.open_group(str(copy), mode="r+").create_array("extra", shape=(1,), dtype="uint8")
    _assert_names(copy, "extra added")


def test_root_metadata_outside_the_marker_is_covered(copy):
    zarr.open_group(str(copy), mode="r+").attrs.update({"name": "SomethingElse"})
    _assert_names(copy, "root metadata changed")
