"""The raw ``uint32`` sample view — arithmetic, refusals, and when it is NOT written.

Everything here runs without an ingest. The reader is exercised against a fixture whose
bytes are compared with ``int.from_bytes`` rather than with the reader itself: a reader
checked against its own output is a tautology, and this one exists precisely because the
decoded store cannot be trusted to answer the question.
"""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest
import zarr

from sdip._pins import SEGY_TRACE_HEADER_BYTES as HEADER
from sdip.errors import UntrustedInputError
from sdip.ingest.raw_samples import (
    ARRAY_NAME,
    SAMPLE_WORD_BYTES,
    TRACE_DATA_OFFSET,
    RawSampleView,
    attach_raw_sample_view,
    open_raw_sample_view,
    read_source_words,
    source_trace_layout,
)
from tests.fixtures.generators import make_poststack3d


def _float32_spec() -> SimpleNamespace:
    """A spec whose sample format is not ``ibm32``. Nothing else about it is used."""
    return SimpleNamespace(
        trace=SimpleNamespace(
            header=SimpleNamespace(fields=[]),
            data=SimpleNamespace(format="float32"),
        )
    )


def test_the_layout_is_derived_from_the_file_not_asserted(tmp_path):
    article = make_poststack3d(tmp_path / "a.sgy", n_inline=2, n_crossline=3, n_samples=8)
    count, stride = source_trace_layout(article.byte_size, 8)
    assert count == 6
    assert count == article.trace_count
    assert stride == HEADER + 8 * SAMPLE_WORD_BYTES


def test_a_declared_sample_count_the_file_contradicts_is_refused(tmp_path):
    """Spec §11.4. A length out of a header is attacker-supplied until the file agrees.

    Seven samples per trace does not divide this file. Trusting it would put every
    subsequent word offset one stride further from the truth, silently.
    """
    article = make_poststack3d(tmp_path / "a.sgy", n_inline=2, n_crossline=3, n_samples=8)
    with pytest.raises(UntrustedInputError, match="not a whole number"):
        source_trace_layout(article.byte_size, 7)


def test_a_non_positive_sample_count_is_refused():
    for declared in (0, -8):
        with pytest.raises(UntrustedInputError, match="must be positive"):
            source_trace_layout(100_000, declared)


def test_a_file_with_no_trace_data_is_refused():
    with pytest.raises(UntrustedInputError, match="no trace data"):
        source_trace_layout(TRACE_DATA_OFFSET, 32)


def test_the_words_are_the_source_bytes_read_big_endian(tmp_path):
    """The independent reader: ``int.from_bytes`` over the file, offset by offset."""
    article = make_poststack3d(tmp_path / "a.sgy", n_inline=2, n_crossline=2, n_samples=6)
    blob = article.path.read_bytes()
    words = read_source_words(article.path, samples_per_trace=6)

    assert words.shape == (4, 6)
    stride = HEADER + 6 * SAMPLE_WORD_BYTES
    for trace in range(4):
        for sample in range(6):
            offset = TRACE_DATA_OFFSET + trace * stride + HEADER + sample * SAMPLE_WORD_BYTES
            expected = int.from_bytes(blob[offset : offset + SAMPLE_WORD_BYTES], "big")
            assert int(words[trace, sample]) == expected


def test_the_words_are_uint32_and_carry_no_float_semantics(tmp_path):
    """SP5's argument, applied to samples: the dtype is a container, not a reading."""
    article = make_poststack3d(tmp_path / "a.sgy", n_inline=2, n_crossline=2, n_samples=4)
    words = read_source_words(article.path, samples_per_trace=4)
    assert words.dtype.kind == "u"
    assert words.dtype.itemsize == SAMPLE_WORD_BYTES


def test_reading_refuses_a_truncated_file(tmp_path):
    """A file one byte short no longer divides, and every offset in it is suspect."""
    article = make_poststack3d(tmp_path / "a.sgy", n_inline=2, n_crossline=2, n_samples=4)
    truncated = tmp_path / "short.sgy"
    truncated.write_bytes(article.path.read_bytes()[:-1])
    with pytest.raises(UntrustedInputError, match="not a whole number"):
        read_source_words(truncated, samples_per_trace=4)


def test_no_view_is_written_for_a_source_that_is_not_ibm32(tmp_path):
    """A ``float32`` source decodes exactly, so a parallel copy would restate the store.

    The store path here does not exist: nothing may be opened, created or read before
    the sample format has ruled the array out.
    """
    article = make_poststack3d(tmp_path / "a.sgy", n_inline=2, n_crossline=2, n_samples=4)
    absent = tmp_path / "never-created.mdio"
    assert attach_raw_sample_view(absent, article.path, _float32_spec()) is None
    assert not absent.exists()


def test_an_absent_view_reads_as_none_not_as_an_error(tmp_path):
    """`NOT_RUN` is not a pass: a caller must be able to tell nothing was stored."""
    zarr.open_group(str(tmp_path / "bare.mdio"), mode="w")
    assert open_raw_sample_view(tmp_path / "bare.mdio") is None


def test_a_present_view_reads_back_without_mdio(tmp_path):
    """§10.3 / G4: written with stock ``zarr``, so read with stock ``zarr``."""
    group = zarr.open_group(str(tmp_path / "store.mdio"), mode="w")
    array = group.create_array(name=ARRAY_NAME, shape=(2, 3), dtype="uint32", fill_value=0)
    array[:] = np.array([[1, 2, 3], [4, 5, 6]], dtype=np.uint32)
    opened = open_raw_sample_view(tmp_path / "store.mdio")
    assert opened is not None
    assert np.array_equal(np.asarray(opened[:]), np.asarray(array[:]))


def _view(**overrides: object) -> RawSampleView:
    fields = {
        "array": ARRAY_NAME,
        "dtype": "uint32",
        "shape": (5, 6, 32),
        "dimensions": ("inline", "crossline", "time"),
        "sample_format": "ibm32",
        "samples_per_trace": 32,
        "traces_written": 30,
        "source_trace_count": 30,
        "source_bytes_per_trace": HEADER + 32 * SAMPLE_WORD_BYTES,
    }
    return RawSampleView(**(fields | overrides))


def test_completeness_is_reported_rather_than_inferred():
    assert _view().complete is True
    assert _view(traces_written=29).complete is False


def test_the_certificate_shape_names_the_probe_that_forced_it():
    payload = _view().to_json()
    assert payload["array"] == ARRAY_NAME
    assert payload["dtype"] == "uint32"
    assert payload["sample_format"] == "ibm32"
    assert payload["probe"] == "P2"
    assert payload["complete"] is True
    assert "not be recovered" in payload["rationale"]
