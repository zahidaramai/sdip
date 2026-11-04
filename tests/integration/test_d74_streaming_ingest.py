"""D74 (probe P28): ingest's raw sample view and header plane read the source slab by slab.

Both read the whole source through a memory map until P28, so ingest memory grew with the
file at about 1.15 MB per MB. They now read each slab's live traces by explicit reads. What
they write may not change, so each is checked against an oracle built from the mapped
readers, the whole-file reads they replaced, on a store with lossy ibm32 words spread over
several slabs. A one-byte or one-word corruption must fail each oracle comparison, so the
comparisons are not vacuous.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import NoReturn

import numpy as np
import pytest
import zarr

from sdip._pins import SEGY_TRACE_HEADER_BYTES as HEADER
from sdip.ingest import header_plane, ingest, raw_samples
from sdip.ingest.header_plane import (
    ARRAY_NAME as PLANE,
)
from sdip.ingest.header_plane import (
    ORDINAL_ARRAY_NAME,
    attach_header_plane,
    read_source_header_bytes,
)
from sdip.ingest.raw_samples import (
    SAMPLE_WORD_BYTES,
    TRACE_DATA_OFFSET,
    attach_raw_sample_view,
    read_source_words,
    reconstructed_words,
)
from sdip.spec.declaration import SurveyDeclaration
from tests.fixtures.generators import make_poststack3d

pytestmark = pytest.mark.integration

LOSSY = (0x80000000, 0x42000000, 0x42010000)
"""Words whose float32 decode does not re-encode to them (P2's classes)."""

LOSSY_TRACES = (0, 9, 20, 33, 41)
"""Spread over several outermost slabs of the 6 x 7 grid."""


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    root = tmp_path_factory.mktemp("d74")
    article = make_poststack3d(root / "src.sgy", n_inline=6, n_crossline=7, n_samples=16)
    raw = bytearray(article.path.read_bytes())
    stride = HEADER + 16 * SAMPLE_WORD_BYTES
    for trace in LOSSY_TRACES:
        for k, word in enumerate(LOSSY):
            offset = TRACE_DATA_OFFSET + trace * stride + HEADER + (3 + k) * SAMPLE_WORD_BYTES
            raw[offset : offset + SAMPLE_WORD_BYTES] = word.to_bytes(SAMPLE_WORD_BYTES, "big")
    source = root / "lossy.sgy"
    source.write_bytes(bytes(raw))
    store = root / "store.mdio"
    ingest(source, store)
    return source, store


def _live_cells(store: Path) -> list[tuple[int, tuple[int, ...]]]:
    group = zarr.open_group(str(store), mode="r")
    ordinals = np.asarray(group[ORDINAL_ARRAY_NAME][:])
    live = np.asarray(group["trace_mask"][:]).astype(bool)
    return [(int(ordinals[c]), c) for c in zip(*np.nonzero(live), strict=True)]


def _plane_matches_mapping(source: Path, store: Path) -> bool:
    """The oracle: every live cell's plane row is the mapped reader's row for its trace."""
    mapped = read_source_header_bytes(source, samples_per_trace=16, bytes_per_sample=4)
    plane = np.asarray(zarr.open_group(str(store), mode="r")[PLANE][:])
    return all(np.array_equal(plane[cell], mapped[o]) for o, cell in _live_cells(store))


def _words_match_mapping(source: Path, store: Path) -> bool:
    """The oracle: every live cell's rebuilt words are the mapped reader's words."""
    mapped = read_source_words(source, samples_per_trace=16)
    rebuilt = reconstructed_words(store)
    return all(np.array_equal(rebuilt[cell], mapped[o]) for o, cell in _live_cells(store))


def test_every_cell_is_live_and_the_view_holds_the_lossy_words(built):
    _source, store = built
    assert len(_live_cells(store)) == 42
    view = zarr.open_group(str(store), mode="r")["amplitude_raw_ibm32"]
    assert view["words"].shape == (len(LOSSY_TRACES) * len(LOSSY),)


def test_the_header_plane_equals_the_whole_file_read(built):
    assert _plane_matches_mapping(*built)


def test_the_raw_sample_view_equals_the_whole_file_read(built):
    assert _words_match_mapping(*built)


def test_neither_stage_reads_through_the_mapping(built, monkeypatch):
    """The fix itself: rewriting both arrays never calls the mapped readers, and changes nothing."""
    source, store = built
    group = zarr.open_group(str(store), mode="r")
    before = (np.asarray(group[PLANE][:]), reconstructed_words(store))

    def refuse(*_args: object, **_kwargs: object) -> NoReturn:
        raise AssertionError("an ingest stage read the whole source through the mapping")

    monkeypatch.setattr(raw_samples, "read_source_words", refuse)
    monkeypatch.setattr(header_plane, "read_source_header_bytes", refuse)
    spec = SurveyDeclaration(revision=1, template="PostStack3DTime").build_spec().segy_spec
    attach_raw_sample_view(store, source, spec)
    attach_header_plane(store, source, spec)
    monkeypatch.undo()

    group = zarr.open_group(str(store), mode="r")
    assert np.array_equal(np.asarray(group[PLANE][:]), before[0])
    assert np.array_equal(reconstructed_words(store), before[1])


def test_one_flipped_header_byte_fails_the_plane_oracle(built, tmp_path):
    source, store = built
    copy = tmp_path / "flipped.mdio"
    shutil.copytree(store, copy)
    array = zarr.open_group(str(copy), mode="r+")[PLANE]
    row = np.asarray(array[2, 3])
    row[17] ^= 0x01
    array[2, 3] = row
    assert not _plane_matches_mapping(source, copy)


def test_one_changed_source_word_fails_the_words_oracle(built, tmp_path):
    source, store = built
    other = tmp_path / "other.sgy"
    raw = bytearray(source.read_bytes())
    stride = HEADER + 16 * SAMPLE_WORD_BYTES
    raw[TRACE_DATA_OFFSET + 20 * stride + HEADER + 3 * SAMPLE_WORD_BYTES] ^= 0x01
    other.write_bytes(bytes(raw))
    assert not _words_match_mapping(other, store)
