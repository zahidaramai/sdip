"""The ``uint8`` header plane — arithmetic, refusals, and what the offsets rest on.

Everything here runs without an ingest. The reader is exercised against a fixture whose
bytes are compared with plain slicing rather than with the reader itself: a reader
checked against its own output is a tautology, and this one exists precisely because the
structured ``headers`` array cannot be trusted to answer the question — probe P4 measured
a reader that will not open it at all.
"""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest
import zarr

from sdip._pins import SEGY_TEXTUAL_HEADER_BYTES as TEXTUAL
from sdip._pins import SEGY_TRACE_HEADER_BYTES as HEADER
from sdip.errors import UntrustedInputError
from sdip.ingest.header_plane import (
    ARRAY_NAME,
    BYTE_AXIS_NAME,
    TRACE_DATA_OFFSET,
    HeaderPlane,
    open_header_plane,
    read_source_header_bytes,
    sample_bytes,
    source_trace_layout,
    trace_data_offset,
)
from tests.fixtures.generators import make_poststack3d

IBM32_WORD_BYTES = 4
"""Rev 1's mandated sample width. Named so the arithmetic below is readable, and read
off the spec by :func:`sample_bytes` rather than assumed by the module under test."""


def _spec_with_format(dtype: str) -> SimpleNamespace:
    """A spec whose declared sample format has ``dtype``. Nothing else is used."""
    return SimpleNamespace(
        trace=SimpleNamespace(data=SimpleNamespace(format=SimpleNamespace(dtype=np.dtype(dtype))))
    )


def test_the_layout_is_derived_from_the_file_not_asserted(tmp_path):
    article = make_poststack3d(tmp_path / "a.sgy", n_inline=2, n_crossline=3, n_samples=8)
    count, stride = source_trace_layout(
        article.byte_size, samples_per_trace=8, bytes_per_sample=IBM32_WORD_BYTES
    )
    assert count == 6
    assert count == article.trace_count
    assert stride == HEADER + 8 * IBM32_WORD_BYTES


def test_a_declared_sample_count_the_file_contradicts_is_refused(tmp_path):
    """Spec §11.4. A length out of a header is attacker-supplied until the file agrees.

    Seven samples per trace does not divide this file. Trusting it would put every
    subsequent header offset one stride further from the truth, silently — and the bytes
    read would still be *some* bytes, which is exactly why this has to raise.
    """
    article = make_poststack3d(tmp_path / "a.sgy", n_inline=2, n_crossline=3, n_samples=8)
    with pytest.raises(UntrustedInputError, match="not a whole number"):
        source_trace_layout(
            article.byte_size, samples_per_trace=7, bytes_per_sample=IBM32_WORD_BYTES
        )


def test_a_non_positive_sample_count_is_refused():
    for declared in (0, -8):
        with pytest.raises(UntrustedInputError, match="samples_per_trace"):
            source_trace_layout(
                100_000, samples_per_trace=declared, bytes_per_sample=IBM32_WORD_BYTES
            )


def test_a_non_positive_sample_width_is_refused():
    for declared in (0, -4):
        with pytest.raises(UntrustedInputError, match="bytes_per_sample"):
            source_trace_layout(100_000, samples_per_trace=32, bytes_per_sample=declared)


def test_a_file_with_no_trace_data_is_refused():
    with pytest.raises(UntrustedInputError, match="no trace data"):
        source_trace_layout(
            TRACE_DATA_OFFSET, samples_per_trace=32, bytes_per_sample=IBM32_WORD_BYTES
        )


def test_the_sample_width_comes_from_the_declared_format_not_a_constant():
    """The plane is written for **every** store, so four bytes cannot be assumed.

    ``ibm32`` is what rev 1 mandates and what the ``uint32`` raw-sample view may hard-code,
    because that view exists only for ``ibm32`` sources. This one does not, and an
    ``int16`` source has a different distance between trace headers.
    """
    assert sample_bytes(_spec_with_format("uint32")) == 4
    assert sample_bytes(_spec_with_format("int16")) == 2
    assert sample_bytes(_spec_with_format("float64")) == 8
    assert sample_bytes(_spec_with_format("int8")) == 1


def test_the_width_of_the_pinned_rev_1_standard_is_four():
    """Read off the pinned ``segy``, not transcribed: rev 1's sample format is ``ibm32``."""
    from segy.standards import get_segy_standard

    assert sample_bytes(get_segy_standard(1)) == IBM32_WORD_BYTES


def test_a_spec_with_no_declared_sample_format_is_refused():
    with pytest.raises(UntrustedInputError, match="no sample format width"):
        sample_bytes(SimpleNamespace())


def test_a_spec_declaring_a_zero_width_sample_is_refused():
    with pytest.raises(UntrustedInputError, match="must be positive"):
        sample_bytes(_spec_with_format("V0"))


def test_extended_textual_headers_move_the_first_trace():
    """3600 is the offset for a file with none, which is not every file.

    Reading a file that carries them at 3600 lands mid-header on every single trace, and
    the count comes from the open source file rather than from SDIP.
    """
    assert trace_data_offset(SimpleNamespace(num_ext_text=0)) == TRACE_DATA_OFFSET
    assert trace_data_offset(SimpleNamespace(num_ext_text=2)) == TRACE_DATA_OFFSET + 2 * TEXTUAL
    # A handle that does not report the field at all is treated as carrying none, which
    # is the only reading available and is what every fixture in this repository is.
    assert trace_data_offset(SimpleNamespace()) == TRACE_DATA_OFFSET


def test_the_bytes_are_the_source_bytes_at_the_source_offsets(tmp_path):
    """The independent reader: raw slicing over the file, offset by offset.

    No spec, no parser, no reuse of the module under test — the point of the plane is
    that the bytes are the source's bytes, so the check has to be against the source.
    """
    article = make_poststack3d(tmp_path / "a.sgy", n_inline=2, n_crossline=2, n_samples=6)
    blob = article.path.read_bytes()
    plane = read_source_header_bytes(
        article.path, samples_per_trace=6, bytes_per_sample=IBM32_WORD_BYTES
    )

    assert plane.shape == (4, HEADER)
    stride = HEADER + 6 * IBM32_WORD_BYTES
    for trace in range(4):
        base = TRACE_DATA_OFFSET + trace * stride
        expected = blob[base : base + HEADER]
        assert bytes(plane[trace]) == expected


def test_the_bytes_are_uint8_and_carry_no_numeric_semantics(tmp_path):
    """SP5's argument, applied to headers: the dtype is a container, not a reading."""
    article = make_poststack3d(tmp_path / "a.sgy", n_inline=2, n_crossline=2, n_samples=4)
    plane = read_source_header_bytes(
        article.path, samples_per_trace=4, bytes_per_sample=IBM32_WORD_BYTES
    )
    assert plane.dtype == np.uint8
    assert plane.dtype.itemsize == 1
    assert plane.shape[1] == HEADER


def test_reading_refuses_a_truncated_file(tmp_path):
    """A file one byte short no longer divides, and every offset in it is suspect."""
    article = make_poststack3d(tmp_path / "a.sgy", n_inline=2, n_crossline=2, n_samples=4)
    truncated = tmp_path / "short.sgy"
    truncated.write_bytes(article.path.read_bytes()[:-1])
    with pytest.raises(UntrustedInputError, match="not a whole number"):
        read_source_header_bytes(truncated, samples_per_trace=4, bytes_per_sample=IBM32_WORD_BYTES)


def test_an_absent_plane_reads_as_none_not_as_an_error(tmp_path):
    """`NOT_RUN` is not a pass: a caller must be able to tell nothing was stored."""
    zarr.open_group(str(tmp_path / "bare.mdio"), mode="w")
    assert open_header_plane(tmp_path / "bare.mdio") is None


def test_a_present_plane_reads_back_without_mdio(tmp_path):
    """§10.3 / G4: written with stock ``zarr``, so read with stock ``zarr``."""
    group = zarr.open_group(str(tmp_path / "store.mdio"), mode="w")
    array = group.create_array(name=ARRAY_NAME, shape=(2, HEADER), dtype="uint8", fill_value=0)
    array[:] = np.arange(2 * HEADER, dtype=np.uint8).reshape(2, HEADER)
    opened = open_header_plane(tmp_path / "store.mdio")
    assert opened is not None
    assert np.array_equal(np.asarray(opened[:]), np.asarray(array[:]))


def _plane(**overrides: object) -> HeaderPlane:
    fields = {
        "array": ARRAY_NAME,
        "dtype": "uint8",
        "shape": (5, 6, HEADER),
        "dimensions": ("inline", "crossline", BYTE_AXIS_NAME),
        "bytes_per_trace": HEADER,
        "traces_written": 30,
        "source_trace_count": 30,
        "source_bytes_per_trace": HEADER + 32 * IBM32_WORD_BYTES,
    }
    return HeaderPlane(**(fields | overrides))


def test_completeness_is_reported_rather_than_inferred():
    assert _plane().complete is True
    assert _plane(traces_written=29).complete is False


def test_the_certificate_shape_names_the_probe_that_forced_it():
    payload = _plane().to_json()
    assert payload["array"] == ARRAY_NAME
    assert payload["dtype"] == "uint8"
    assert payload["bytes_per_trace"] == HEADER
    assert payload["probe"] == "P4"
    assert payload["complete"] is True
    assert payload["zarr_v3_core_spec"] is True
    assert "D-0047" in payload["rationale"]


def test_the_certificate_shape_states_what_the_plane_does_not_fix():
    """OPEN_DEBTS D32. The plane makes header data readable, not the group listable.

    Overclaiming here would be worse than not writing the array: a consumer told the
    portability problem is solved would discover otherwise at ``Group.list()``.
    """
    limitation = _plane().to_json()["limitation"]
    assert "Group.list()" in limitation
    assert "segy_file_header" in limitation
    assert "D32" in limitation
