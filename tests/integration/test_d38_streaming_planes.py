"""D38 (probe P23): Plane 4 reads block by block, and reports what the whole-file read did.

Plane 4's decoded leg and both raw-word legs read the whole source and the whole store at
once until P23, so verification memory grew with the file. They now walk the store's chunk
grid. Nothing they report may change, so each leg is checked against an oracle: the
whole-file loop, written out here as it stood, run on the same store. The store is chunked
into 3 x 3 blocks and corrupted in 25 cells, enough to cross every 20-example cap. That
covers the mismatch count, the examples, the first difference and the number compared,
across block boundaries, in ordinal order.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import zarr
from segy import SegyFile

from sdip._pins import SEGY_TRACE_HEADER_BYTES as HEADER
from sdip.equivalence import plane_4
from sdip.equivalence.exact import identical
from sdip.equivalence.planes import _chunk_blocks, grid_coordinates, store_dimensions
from sdip.equivalence.trace_map import build_trace_map
from sdip.errors import UntrustedInputError
from sdip.ingest import ingest
from sdip.ingest.raw_samples import (
    ARRAY_NAME,
    INDEX_ARRAY,
    SAMPLE_WORD_BYTES,
    TRACE_DATA_OFFSET,
    WORDS_ARRAY,
    read_source_words,
    read_source_words_at,
    reconstruct_block,
    reconstruct_slab,
)
from tests.fixtures.generators import make_poststack3d

pytestmark = pytest.mark.integration

LOSSY = (0x80000000, 0x42000000, 0x42010000)
"""Words whose float32 decode does not re-encode to them, without overflow (P2's classes)."""

CHUNKS = (2, 3, 16)
"""6 x 7 grid in 2 x 3 chunks: 3 x 3 = 9 blocks, the last row and column partial."""


def _source(root: Path) -> Path:
    article = make_poststack3d(root / "src.sgy", n_inline=6, n_crossline=7, n_samples=16)
    raw = bytearray(article.path.read_bytes())
    stride = HEADER + 16 * SAMPLE_WORD_BYTES
    for trace in (0, 9, 20, 33, 41):  # spread over several blocks
        for k, word in enumerate(LOSSY):
            offset = TRACE_DATA_OFFSET + trace * stride + HEADER + (3 + k) * SAMPLE_WORD_BYTES
            raw[offset : offset + SAMPLE_WORD_BYTES] = word.to_bytes(SAMPLE_WORD_BYTES, "big")
    source = root / "lossy.sgy"
    source.write_bytes(bytes(raw))
    return source


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    root = tmp_path_factory.mktemp("d38")
    source = _source(root)
    result = ingest(source, root / "store.mdio", chunk_shape=CHUNKS)
    return source, root / "store.mdio", result


def _corrupt(store: Path, count: int = 25) -> None:
    group = zarr.open_group(str(store), mode="r+")
    amplitude = np.asarray(group["amplitude"][:])
    rng = np.random.default_rng(20261101)
    cells = rng.choice(amplitude.shape[0] * amplitude.shape[1], size=count, replace=False)
    for flat in cells:
        i, j = divmod(int(flat), amplitude.shape[1])
        amplitude[i, j, int(rng.integers(0, 16))] += np.float32(1.0)
    group["amplitude"][:] = amplitude


def _as_dense(store: Path, source: Path) -> None:
    group = zarr.open_group(str(store), mode="r+")
    shape = group["amplitude"].shape
    words = read_source_words(source, samples_per_trace=shape[-1])
    dense = np.zeros(shape, dtype=np.uint32)
    for ordinal in range(words.shape[0]):
        dense[ordinal // shape[1], ordinal % shape[1]] = words[ordinal]
    del group[ARRAY_NAME]
    group.create_array(name=ARRAY_NAME, shape=shape, dtype="uint32", chunks=CHUNKS)[:] = dense


def _trace_map(source: Path, store: Path, spec: Any) -> Any:
    group = zarr.open_group(str(store), mode="r")
    dimensions = store_dimensions(group)
    headers = SegyFile(str(source), spec=spec).header[:]
    return build_trace_map(headers, grid_coordinates(group, dimensions), dimensions)


def _oracle_decoded(source: Path, store: Path, spec: Any) -> dict[str, Any]:
    """The whole-file loop Plane 4's decoded leg ran before P23."""
    samples = SegyFile(str(source), spec=spec).sample[:]
    volume = zarr.open_group(str(store), mode="r")["amplitude"][:]
    examples: list[dict[str, Any]] = []
    count = compared = 0
    for ordinal, cell in sorted(_trace_map(source, store, spec).ordinal_to_cell.items()):
        compared += 1
        expected, observed = np.asarray(samples[ordinal]), np.asarray(volume[cell])
        if not identical(expected, observed):
            differing = np.flatnonzero(expected != observed)
            first = int(differing[0])
            count += 1
            if len(examples) < 20:
                examples.append(
                    {
                        "source_ordinal": ordinal,
                        "cell": list(cell),
                        "first_sample": first,
                        "expected": float(expected[first]),
                        "observed": float(observed[first]),
                        "differing_samples": int(differing.size),
                    }
                )
    return {"n": compared, "mismatch_count": count, "mismatch_examples": examples}


def _word_record(ordinal: int, cell: Any, expected: Any, observed: Any) -> dict[str, Any]:
    differing = np.flatnonzero(expected != observed)
    first = int(differing[0])
    return {
        "source_ordinal": ordinal,
        "cell": list(cell),
        "first_sample": first,
        "expected_word": f"0x{int(expected[first]):08X}",
        "observed_word": f"0x{int(observed[first]):08X}",
        "differing_words": int(differing.size),
    }


def _oracle_dense(source: Path, store: Path, spec: Any) -> dict[str, Any]:
    """The dense raw leg before P23: ordinal order, stopping at the 20th mismatch."""
    stored = np.asarray(zarr.open_group(str(store), mode="r")[ARRAY_NAME][:])
    words = read_source_words(source, samples_per_trace=stored.shape[-1])
    mismatches: list[dict[str, Any]] = []
    compared = 0
    for ordinal, cell in sorted(_trace_map(source, store, spec).ordinal_to_cell.items()):
        compared += 1
        expected = np.asarray(words[ordinal], dtype=np.uint32)
        observed = np.asarray(stored[cell])
        if not identical(expected, observed):
            mismatches.append(_word_record(ordinal, cell, expected, observed))
            if len(mismatches) >= 20:
                break
    return {"raw_ibm32_n": compared, "mismatches": mismatches}


def _oracle_sparse(source: Path, store: Path, spec: Any) -> dict[str, Any]:
    """The sparse raw leg before P23: slab by slab, stopping after the slab that reaches 20."""
    group = zarr.open_group(str(store), mode="r")
    amplitude, view = group["amplitude"], group[ARRAY_NAME]
    shape = tuple(int(n) for n in amplitude.shape)
    words = read_source_words(source, samples_per_trace=shape[-1])
    slab = int(np.prod(shape[1:]))
    by_outer: dict[int, list[Any]] = {}
    for ordinal, cell in sorted(_trace_map(source, store, spec).ordinal_to_cell.items()):
        by_outer.setdefault(cell[0], []).append((ordinal, cell))
    mismatches: list[dict[str, Any]] = []
    compared = 0
    for outer, traces in sorted(by_outer.items()):
        rebuilt = reconstruct_slab(np.asarray(amplitude[outer]), outer, slab, view)
        for ordinal, cell in traces:
            compared += 1
            expected = np.asarray(words[ordinal], dtype=np.uint32)
            observed = rebuilt[cell[1:]]
            if not identical(expected, observed):
                mismatches.append(_word_record(ordinal, cell, expected, observed))
        if len(mismatches) >= 20:
            break
    return {"raw_ibm32_n": compared, "mismatches": mismatches}


def _assert_matches_oracle(plane: Any, decoded: dict[str, Any], raw: dict[str, Any]) -> None:
    evidence = plane.evidence
    assert evidence["n"] == decoded["n"]
    assert evidence["mismatch_count"] == decoded["mismatch_count"]
    assert evidence["mismatch_examples"] == decoded["mismatch_examples"]
    assert evidence["first_difference"] == (decoded["mismatch_examples"] or [None])[0]
    assert evidence["raw_ibm32_n"] == raw["raw_ibm32_n"]
    assert evidence["raw_ibm32_mismatch_count"] == len(raw["mismatches"])
    assert evidence["raw_ibm32_first_difference"] == (raw["mismatches"] or [None])[0]
    assert evidence["raw_ibm32_identical"] is (not raw["mismatches"])


def test_the_store_really_has_nine_blocks_and_a_sparse_view(built):
    source, store, result = built
    group = zarr.open_group(str(store), mode="r")
    assert tuple(group["amplitude"].chunks) == CHUNKS
    assert int(group[ARRAY_NAME][INDEX_ARRAY].shape[0]) > 0, "no entries: the overlay is untested"
    trace_map = _trace_map(source, store, result.spec.segy_spec)
    blocks = list(_chunk_blocks(group["amplitude"], trace_map))
    assert len(blocks) == 9
    seen = [o for *_, traces in blocks for o, _ in traces]
    assert sorted(seen) == sorted(trace_map.ordinal_to_cell), "every live trace, exactly once"


def test_a_correct_store_passes_with_the_oracles_numbers(built):
    source, store, result = built
    spec = result.spec.segy_spec
    plane = plane_4(source, store, spec)
    assert plane.status == "PASS"
    _assert_matches_oracle(
        plane, _oracle_decoded(source, store, spec), _oracle_sparse(source, store, spec)
    )


def test_a_corrupted_sparse_store_reports_what_the_whole_file_loop_reported(built, tmp_path):
    source, store, result = built
    spec = result.spec.segy_spec
    copy = tmp_path / "corrupt.mdio"
    shutil.copytree(store, copy)
    _corrupt(copy)
    plane = plane_4(source, copy, spec)
    decoded = _oracle_decoded(source, copy, spec)
    assert plane.status == "FAIL"
    assert decoded["mismatch_count"] == 25, "the corruption must cross the 20-example cap"
    _assert_matches_oracle(plane, decoded, _oracle_sparse(source, copy, spec))


def test_a_corrupted_dense_store_reports_what_the_whole_file_loop_reported(built, tmp_path):
    source, store, result = built
    spec = result.spec.segy_spec
    copy = tmp_path / "dense.mdio"
    shutil.copytree(store, copy)
    _as_dense(copy, source)
    assert plane_4(source, copy, spec).status == "PASS"
    group = zarr.open_group(str(copy), mode="r+")
    values = np.asarray(group[ARRAY_NAME][:])
    rng = np.random.default_rng(7)
    for flat in rng.choice(42, size=25, replace=False):
        values[int(flat) // 7, int(flat) % 7, int(rng.integers(0, 16))] ^= np.uint32(1)
    group[ARRAY_NAME][:] = values
    plane = plane_4(source, copy, spec)
    raw = _oracle_dense(source, copy, spec)
    assert plane.status == "FAIL"
    assert len(raw["mismatches"]) == 20 and raw["raw_ibm32_n"] < 42, "the cap must stop it"
    _assert_matches_oracle(plane, _oracle_decoded(source, copy, spec), raw)
    assert plane.evidence["raw_ibm32_layout"] == "dense"


def test_reading_words_by_ordinal_equals_the_mapping(built):
    source, _, _ = built
    mapped = read_source_words(source, samples_per_trace=16)
    wanted = np.array([0, 1, 2, 5, 9, 10, 41], dtype=np.int64)
    assert np.array_equal(read_source_words_at(source, wanted, samples_per_trace=16), mapped[wanted])
    for bad in ([3, 2], [0, 42], [-1, 4], [5, 5]):
        with pytest.raises(UntrustedInputError):
            read_source_words_at(source, np.array(bad, dtype=np.int64), samples_per_trace=16)


def test_a_block_rebuilds_the_same_words_as_its_slabs():
    rng = np.random.default_rng(11)
    amplitude = rng.standard_normal((5, 6, 8)).astype(np.float32)
    index = np.sort(rng.choice(amplitude.size, size=12, replace=False)).astype(np.uint64)
    words = rng.integers(0, 2**32, size=12, dtype=np.uint64).astype(np.uint32)
    view = {INDEX_ARRAY: index, WORDS_ARRAY: words}
    slab = 6 * 8
    whole = np.stack([reconstruct_slab(amplitude[i], i, slab, view) for i in range(5)])
    cells = np.stack(np.unravel_index(index.astype(np.int64) // 8, (5, 6)), axis=1)
    samples = index.astype(np.int64) % 8
    for i0 in range(0, 5, 2):
        for j0 in range(0, 6, 4):
            block = amplitude[i0 : i0 + 2, j0 : j0 + 4]
            rebuilt = reconstruct_block(block, (i0, j0), cells, samples, words)
            assert np.array_equal(rebuilt, whole[i0 : i0 + 2, j0 : j0 + 4])
