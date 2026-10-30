"""D36, DECISIONS.md D-0110 - the sparse raw view, both halves (D-0088).

The view stores a live word exactly when the stored float32 does not re-encode to it. So the
sweep plants one word from each regime P2 named - exact, overflow, underflow, negative zero,
zero fraction with an exponent, unnormalised - and requires the view to hold exactly the
regimes that do not round-trip, Plane 4 to PASS on the correct store, and each stored word,
corrupted, to fail it. Then the view's shape: an entry out of order, out of range, on
padding, or a length mismatch, each fails; and a store in the dense layout written before
D-0110 is still verified, both ways.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import numpy as np
import pytest
import zarr

from sdip._pins import SEGY_TRACE_HEADER_BYTES as HEADER
from sdip.equivalence import plane_4
from sdip.ingest import ingest
from sdip.ingest.raw_samples import (
    ARRAY_NAME,
    INDEX_ARRAY,
    SAMPLE_WORD_BYTES,
    TRACE_DATA_OFFSET,
    WORDS_ARRAY,
    read_source_words,
)
from tests.fixtures.generators import make_poststack3d
from tests.fixtures.generators.irregular import make_sparse_grid

pytestmark = pytest.mark.integration

REGIMES = {
    "exact_normal": (0x41100000, False),  # 1.0: decodes and re-encodes exactly
    "overflow_to_inf": (0x61800000, True),  # exponent code 97
    "underflow_to_zero": (0x00000001, True),  # below float32
    "negative_zero": (0x80000000, True),  # zero fraction, sign lost
    "zero_fraction_exponent": (0x42000000, True),  # zero fraction, exponent lost
    "unnormalised": (0x42010000, True),  # leading zero hex digit, renormalised
}
"""Word and whether it fails to round-trip, per P2's classes (prereg/P2-ibm32-fidelity.md)."""


def _planted(root: Path) -> tuple[Path, Path, object]:
    article = make_poststack3d(root / "src.sgy", n_inline=2, n_crossline=2, n_samples=8)
    raw = bytearray(article.path.read_bytes())
    for sample, (word, _) in enumerate(REGIMES.values()):
        offset = TRACE_DATA_OFFSET + HEADER + sample * SAMPLE_WORD_BYTES
        raw[offset : offset + SAMPLE_WORD_BYTES] = word.to_bytes(SAMPLE_WORD_BYTES, "big")
    source = root / "planted.sgy"
    source.write_bytes(bytes(raw))
    result = ingest(source, root / "planted.mdio")
    return source, root / "planted.mdio", result


@pytest.fixture(scope="module")
def planted(tmp_path_factory):
    return _planted(tmp_path_factory.mktemp("sparse"))


def _plane(source: Path, store: Path, result) -> object:
    with pytest.warns(RuntimeWarning, match="overflow encountered in ibm2ieee"):
        return plane_4(source, store, result.spec.segy_spec)


def test_the_view_holds_exactly_the_regimes_that_do_not_round_trip(planted):
    source, store, result = planted
    view = zarr.open_group(str(store), mode="r")[ARRAY_NAME]
    expected = [s for s, (_, lossy) in enumerate(REGIMES.values()) if lossy]
    assert [int(i) for i in view[INDEX_ARRAY][:]] == expected
    words = list(REGIMES.values())
    assert [int(w) for w in view[WORDS_ARRAY][:]] == [words[s][0] for s in expected]
    assert result.raw_samples.entries == len(expected)
    assert int(read_source_words(source, samples_per_trace=8)[0, 0]) == REGIMES["exact_normal"][0]


def test_plane_4_passes_the_correct_store(planted):
    source, store, result = planted
    plane = _plane(source, store, result)
    assert plane.status == "PASS"
    assert plane.evidence["raw_ibm32_layout"] == "sparse/1"
    assert plane.evidence["raw_ibm32_entries"] == sum(lossy for _, lossy in REGIMES.values())


@pytest.mark.parametrize("entry", range(sum(lossy for _, lossy in REGIMES.values())))
def test_each_stored_word_corrupted_fails_g2d(planted, tmp_path, entry):
    source, store, result = planted
    copy = tmp_path / "c.mdio"
    shutil.copytree(store, copy)
    words = zarr.open_group(str(copy), mode="r+")[ARRAY_NAME][WORDS_ARRAY]
    values = np.asarray(words[:])
    values[entry] ^= np.uint32(1)
    words[:] = values
    plane = _plane(source, copy, result)
    assert plane.status == "FAIL"
    assert plane.evidence["raw_ibm32_mismatch_count"] == 1
    assert plane.evidence["mismatch_count"] == 0, "the decoded leg is untouched"


def _rewrite(store: Path, index: list[int], words: list[int]) -> None:
    view = zarr.open_group(str(store), mode="r+")[ARRAY_NAME]
    for name, values, dtype in ((INDEX_ARRAY, index, "uint64"), (WORDS_ARRAY, words, "uint32")):
        del view[name]
        view.create_array(
            name=name, shape=(len(values),), dtype=dtype, chunks=(max(1, len(values)),)
        )[:] = np.asarray(values, dtype=dtype)


@pytest.mark.parametrize(
    ("mutate", "problem"),
    [
        (lambda i, w: (list(reversed(i)), list(reversed(w))), "not strictly increasing"),
        (lambda i, w: ([*i[:-1], 10**9], w), "outside amplitude"),
        (lambda i, w: (i, w[:-1]), "differ in length"),
    ],
)
def test_a_malformed_view_fails_and_is_not_repaired(planted, tmp_path, mutate, problem):
    source, store, result = planted
    copy = tmp_path / "m.mdio"
    shutil.copytree(store, copy)
    view = zarr.open_group(str(copy), mode="r")[ARRAY_NAME]
    index, words = mutate(
        [int(v) for v in view[INDEX_ARRAY][:]], [int(v) for v in view[WORDS_ARRAY][:]]
    )
    _rewrite(copy, index, words)
    plane = _plane(source, copy, result)
    assert plane.status == "FAIL"
    assert any(problem in p for p in plane.evidence["raw_ibm32_structure_problems"])


def test_an_entry_on_padding_fails(tmp_path):
    article = make_sparse_grid(tmp_path / "sparse.sgy")
    store = tmp_path / "sparse.mdio"
    result = ingest(article.path, store, revision=article.revision)
    group = zarr.open_group(str(store), mode="r")
    mask = np.asarray(group["trace_mask"][:]).astype(bool)
    pad = tuple(int(c) for c in np.argwhere(~mask)[0])
    flat = int(np.ravel_multi_index((*pad, 0), group["amplitude"].shape))
    _rewrite(store, [flat], [0x41100000])
    plane = plane_4(article.path, store, result.spec.segy_spec)
    assert plane.status == "FAIL"
    assert any("padding" in p for p in plane.evidence["raw_ibm32_structure_problems"])


def _as_dense(store: Path, source: Path) -> None:
    """Rewrite the view in the pre-D-0110 dense layout: one source word per cell."""
    group = zarr.open_group(str(store), mode="r+")
    shape = group["amplitude"].shape
    words = read_source_words(source, samples_per_trace=shape[-1])
    dense = np.zeros(shape, dtype=np.uint32)
    for ordinal in range(words.shape[0]):
        dense[ordinal // shape[1], ordinal % shape[1]] = words[ordinal]
    del group[ARRAY_NAME]
    group.create_array(name=ARRAY_NAME, shape=shape, dtype="uint32", chunks=shape)[:] = dense


def test_a_dense_store_from_before_d0110_is_still_verified_both_ways(planted, tmp_path):
    source, store, result = planted
    dense = tmp_path / "dense.mdio"
    shutil.copytree(store, dense)
    _as_dense(dense, source)
    plane = _plane(source, dense, result)
    assert plane.status == "PASS"
    assert plane.evidence["raw_ibm32_layout"] == "dense"

    group = zarr.open_group(str(dense), mode="r+")
    values = np.asarray(group[ARRAY_NAME][:])
    values[1, 1, 3] ^= np.uint32(1)
    group[ARRAY_NAME][:] = values
    assert _plane(source, dense, result).status == "FAIL"
