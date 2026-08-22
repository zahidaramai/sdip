"""D1's remaining half — the raw ``uint32`` view, on words the decode destroys.

Probe **P2** fired: ``ibm32 → float32`` is not exactly invertible, and **1,939 of 4,103**
swept words lose the *value* rather than merely its spelling. The pre-registration's
remedy is that the undecoded words are stored in parallel, and the only honest way to
show that remedy works is to plant words the decode is known to destroy and demonstrate
the store still holds them.

Two of P2's named words do that on their own:

* ``0x61800000`` — exponent code 97. Decodes to ``inf``. The magnitude is gone.
* ``0x00000001`` — the smallest representable IBM value. Decodes to ``0.0``.

Both are real IBM words a legacy tape can carry, and neither survives a re-encode. The
central test below plants them, ingests, and asserts the raw view returns them exactly
**while the decoded array reads ``inf`` and ``0.0``** — which is the entire justification
for the array's existence, demonstrated rather than assumed.
"""

from __future__ import annotations

import shutil

import numpy as np
import pytest
import zarr

from sdip._pins import SEGY_TRACE_HEADER_BYTES as HEADER
from sdip.equivalence import plane_4, plane_5
from sdip.export import export
from sdip.ingest import ingest
from sdip.ingest.raw_samples import (
    ARRAY_NAME,
    ATTR_CONTAINER,
    ATTR_FILL_WORD,
    ATTR_LIVE_MASK,
    ATTR_PROBE,
    ATTR_RATIONALE,
    ATTR_SOURCE_FORMAT,
    ATTR_UNDECODED,
    ATTR_WORD_LAYOUT,
    FILL_WORD,
    SAMPLE_WORD_BYTES,
    TRACE_DATA_OFFSET,
    read_source_words,
)
from tests.fixtures.generators import make_poststack3d
from tests.fixtures.generators.irregular import make_sparse_grid

pytestmark = pytest.mark.integration

OVERFLOW_WORD = 0x61800000
"""P2 ``overflow_to_inf``: exponent code 97 exceeds float32's range. Decodes to ``inf``."""

UNDERFLOW_WORD = 0x00000001
"""P2 ``underflow_to_zero``: below float32's smallest subnormal. Decodes to ``0.0``."""

NEGATIVE_ZERO_WORD = 0x80000000
"""P2 ``zero_fraction_canonicalised``: decodes to ``+0.0`` and loses its sign."""


@pytest.fixture(scope="module")
def ingested(tmp_path_factory):
    """One real ingest of the Appendix A.1 article, reused. Conversion is the slow part."""
    root = tmp_path_factory.mktemp("d1")
    article = make_poststack3d(root / "src.sgy")
    result = ingest(article.path, root / "out.mdio")
    return article, root / "out.mdio", result


def _group(store) -> zarr.Group:
    return zarr.open_group(str(store), mode="r")


def test_an_ibm32_source_gets_the_parallel_view(ingested):
    """Rev 1's standard sample format **is** ``ibm32``, so the view is not exotic."""
    _, _, result = ingested
    assert result.spec.segy_spec.trace.data.format.value == "ibm32"
    assert result.raw_samples is not None
    assert result.raw_samples.array == ARRAY_NAME
    assert result.raw_samples.sample_format == "ibm32"
    assert result.raw_samples.complete is True
    assert result.raw_samples.traces_written == 30
    assert result.to_json()["raw_sample_view"]["probe"] == "P2"


def test_the_view_is_shaped_like_amplitude_and_typed_uint32(ingested):
    """Grid read from the store's ``dimension_names``; nothing hard-codes inline/crossline."""
    _, store, _ = ingested
    group = _group(store)
    raw, amplitude = group[ARRAY_NAME], group["amplitude"]
    assert raw.shape == amplitude.shape
    assert raw.dtype == np.uint32
    assert raw.metadata.to_dict()["dimension_names"] == amplitude.metadata.to_dict().get(
        "dimension_names"
    )


def test_the_view_carries_only_blosc_or_zstd(ingested):
    """SP3. A lossy codec here would destroy the bits the array exists to preserve."""
    _, store, _ = ingested
    codecs = {c["name"] for c in _group(store)[ARRAY_NAME].metadata.to_dict()["codecs"]}
    assert codecs <= {"bytes", "blosc", "zstd"}


def test_the_array_says_what_it_is_holding(ingested):
    """A consumer must learn the array is undecoded from the array, not from a document."""
    _, store, _ = ingested
    attrs = dict(_group(store)[ARRAY_NAME].attrs)
    assert attrs[ATTR_UNDECODED] is True
    assert attrs[ATTR_SOURCE_FORMAT] == "ibm32"
    assert attrs[ATTR_PROBE] == "P2"
    assert attrs[ATTR_FILL_WORD] == FILL_WORD
    assert "big-endian" in attrs[ATTR_WORD_LAYOUT]
    assert "CONTAINER" in attrs[ATTR_CONTAINER]
    assert "P2" in attrs[ATTR_RATIONALE]
    assert "trace_mask" in attrs[ATTR_LIVE_MASK]


def test_every_stored_word_is_the_word_in_the_source(ingested):
    """Independent of the writer's trace map: the fixture's own ordering places the traces.

    The generator writes traces in ``(inline, crossline)`` order, so ordinal *n* belongs
    at cell ``(n // n_crossline, n % n_crossline)``. Checking against that rather than
    against :func:`build_trace_map` keeps the writer's placement under an assertion it
    did not supply.
    """
    article, store, _ = ingested
    blob = article.path.read_bytes()
    stored = np.asarray(_group(store)[ARRAY_NAME][:])
    n_crossline, n_samples = len(article.crosslines), article.samples_per_trace
    stride = HEADER + n_samples * SAMPLE_WORD_BYTES

    for ordinal in range(article.trace_count):
        cell = (ordinal // n_crossline, ordinal % n_crossline)
        base = TRACE_DATA_OFFSET + ordinal * stride + HEADER
        expected = np.array(
            [
                int.from_bytes(blob[base + s * 4 : base + s * 4 + 4], "big")
                for s in range(n_samples)
            ],
            dtype=np.uint32,
        )
        assert np.array_equal(expected, stored[cell])


def test_the_round_trip_stays_byte_identical_with_the_view_present(ingested, tmp_path):
    """G3. The view is an addition to the store, not a change to what is exported."""
    article, store, result = ingested
    round_trip = export(
        store, tmp_path / "exported.sgy", result.spec.segy_spec, source=article.path
    )
    assert round_trip.byte_identical is True
    assert round_trip.status == "PASS"


def test_plane_4_reports_the_raw_leg_as_separate_evidence(ingested):
    """``raw_ibm32_*`` sits beside the decoded verdict; neither substitutes for the other."""
    article, store, result = ingested
    plane = plane_4(article.path, store, result.spec.segy_spec)
    assert plane.status == "PASS"
    assert plane.evidence["raw_ibm32_view_present"] is True
    assert plane.evidence["raw_ibm32_words_verified"] is True
    assert plane.evidence["raw_ibm32_identical"] is True
    assert plane.evidence["raw_ibm32_n"] == article.trace_count
    assert plane.evidence["raw_ibm32_mismatch_count"] == 0
    assert plane.evidence["raw_ibm32_first_difference"] is None
    # The decoded leg is untouched and still decides the verdict.
    assert plane.evidence["mismatch_count"] == 0


def test_an_absent_view_is_reported_as_unchecked_not_as_a_pass(ingested, tmp_path):
    """`NOT_RUN` is not a pass. A store with no view must not read as one that matched."""
    article, store, result = ingested
    copy = tmp_path / "no-view.mdio"
    shutil.copytree(store, copy)
    shutil.rmtree(copy / ARRAY_NAME)

    plane = plane_4(article.path, copy, result.spec.segy_spec)
    assert plane.status == "PASS"
    assert plane.evidence["raw_ibm32_view_present"] is False
    assert plane.evidence["raw_ibm32_words_verified"] is False
    assert plane.evidence["raw_ibm32_identical"] is None


def test_a_corrupted_raw_word_fails_g2d_without_touching_the_decoded_leg(ingested, tmp_path):
    """CORRECTED. This test asserted ``plane.status == "PASS"`` when first written.

    That was the design as specified: the raw leg was evidence-only so a raw pass could
    not mask a float failure. The author flagged the consequence rather than papering
    over it — **no gate failed on a corrupted raw word**, so the evidence had no G7
    control and was not a check at all.

    **The maintainer ruling went the other way** (`DECISIONS.md` D-0048). The two legs
    are now ``AND``-ed, which satisfies the original concern *and* closes the hole: a raw
    pass still cannot rescue a failed float comparison, and a raw failure now fails the
    plane. `amplitude_raw_ibm32` is the only recoverable copy of the source bits for an
    ``ibm32`` source, so a store that silently corrupted it would have been certifiable.

    The two legs stay **independent**, which is what this test now pins: the raw leg
    fails, and the decoded leg's ``mismatch_count`` stays 0. A G7 control
    (``flipped_raw_ibm32_word``) now covers it and must fail G2d and only G2d.

    The assertion is inverted rather than deleted, so the ruling is visible in the diff.
    """
    article, store, result = ingested
    copy = tmp_path / "corrupt.mdio"
    shutil.copytree(store, copy)
    group = zarr.open_group(str(copy), mode="r+")
    original = int(np.asarray(group[ARRAY_NAME][0, 0, 0]))
    group[ARRAY_NAME][0, 0, 0] = np.uint32(original ^ 0x00000001)

    plane = plane_4(article.path, copy, result.spec.segy_spec)
    assert plane.evidence["raw_ibm32_identical"] is False
    assert plane.evidence["raw_ibm32_mismatch_count"] == 1
    assert plane.evidence["raw_ibm32_first_difference"]["cell"] == [0, 0]
    assert plane.evidence["raw_ibm32_first_difference"]["first_sample"] == 0
    assert plane.status == "FAIL", "a corrupted raw word must fail G2d - it is the only "
    # The decoded leg is genuinely untouched: the two legs remain independent, and the
    # failure above comes from the raw comparison alone.
    assert plane.evidence["mismatch_count"] == 0


def test_padding_carries_the_fill_word_and_is_never_compared(tmp_path):
    """SP12. Padding is not data, and no ``uint32`` can announce itself as padding.

    A sparse grid has 54 cells no source trace maps to. They hold the fill word — which
    is ``0x00000000``, a perfectly valid IBM word for true zero — so the store's
    ``trace_mask`` is the only discriminator, exactly as it is for ``amplitude``.
    """
    article = make_sparse_grid(tmp_path / "sparse.sgy")
    store = tmp_path / "sparse.mdio"
    result = ingest(article.path, store, revision=article.revision)

    group = _group(store)
    mask = np.asarray(group["trace_mask"][:]).astype(bool)
    stored = np.asarray(group[ARRAY_NAME][:])
    assert int((~mask).sum()) == 54
    assert np.array_equal(np.unique(stored[~mask]), np.array([FILL_WORD], dtype=np.uint32))

    plane = plane_4(article.path, store, result.spec.segy_spec)
    live = plane_5(article.path, store, result.spec.segy_spec).evidence["live_cells_in_mask"]
    assert plane.evidence["raw_ibm32_n"] == live
    assert plane.evidence["raw_ibm32_identical"] is True
    assert result.raw_samples is not None
    assert result.raw_samples.traces_written == live


@pytest.fixture(scope="module")
def destroyed(tmp_path_factory):
    """A fixture whose first trace carries three words P2 measured as unrecoverable."""
    root = tmp_path_factory.mktemp("d1-extremes")
    article = make_poststack3d(root / "src.sgy", n_inline=2, n_crossline=2, n_samples=8)
    planted = (OVERFLOW_WORD, UNDERFLOW_WORD, NEGATIVE_ZERO_WORD)

    raw = bytearray(article.path.read_bytes())
    for sample, word in enumerate(planted):
        offset = TRACE_DATA_OFFSET + HEADER + sample * SAMPLE_WORD_BYTES
        raw[offset : offset + SAMPLE_WORD_BYTES] = word.to_bytes(SAMPLE_WORD_BYTES, "big")
    source = root / "planted.sgy"
    source.write_bytes(bytes(raw))

    result = ingest(source, root / "planted.mdio")
    return source, root / "planted.mdio", result, planted


def test_the_raw_view_recovers_words_the_decode_destroyed(destroyed):
    """The justification for the whole feature, measured.

    The decoded array reads ``inf``, ``0.0``, ``0.0``: the magnitude of the first word
    and the value of the second are gone, and the sign of the third with them. The raw
    view returns all three source words bit-exact, because nothing decoded them.
    """
    source, store, _, planted = destroyed
    group = _group(store)

    decoded = np.asarray(group["amplitude"][0, 0, :])
    assert np.isinf(decoded[0])  # 0x61800000 overflowed: the magnitude is gone
    assert decoded[1] == np.float32(0.0)  # 0x00000001 underflowed: the value is gone
    assert decoded[2] == np.float32(0.0)  # 0x80000000 lost its sign

    stored = np.asarray(group[ARRAY_NAME][0, 0, :])
    assert [int(w) for w in stored[: len(planted)]] == list(planted)

    # And the source really did carry those words - read independently, by offset.
    words = read_source_words(source, samples_per_trace=8)
    assert [int(w) for w in words[0, : len(planted)]] == list(planted)


def test_the_decode_is_what_lost_them_and_a_re_encode_cannot_bring_them_back(destroyed):
    """G3 fails on exactly those samples: the export writes different words back.

    This is the negative half of the claim above. If a re-encode could reconstruct the
    source word, the round trip would be byte-identical and the parallel view would be
    redundant. It is not: the exported file disagrees with the source at the planted
    words while every header byte around them comes back untouched.
    """
    source, store, result, planted = destroyed
    output = store.parent / "exported.sgy"
    round_trip = export(store, output, result.spec.segy_spec, source=source)
    assert round_trip.byte_identical is False
    assert round_trip.status == "FAIL"

    original, exported = source.read_bytes(), output.read_bytes()
    assert original[:TRACE_DATA_OFFSET] == exported[:TRACE_DATA_OFFSET]
    base = TRACE_DATA_OFFSET
    assert original[base : base + HEADER] == exported[base : base + HEADER]
    returned = [
        int.from_bytes(exported[base + HEADER + s * 4 : base + HEADER + s * 4 + 4], "big")
        for s in range(len(planted))
    ]
    assert returned != list(planted)
    for word, came_back in zip(planted, returned, strict=True):
        assert word != came_back

    # The store still holds the originals, which is the point of D1's remedy.
    stored = np.asarray(_group(store)[ARRAY_NAME][0, 0, : len(planted)])
    assert [int(w) for w in stored] == list(planted)


def test_the_float_leg_cannot_see_the_loss_and_the_raw_leg_can(destroyed):
    """Plane 4's decoded comparison **passes** on a store whose values were destroyed.

    Both sides of that comparison went through the same lossy decode, so ``inf`` equals
    ``inf`` and the plane is right to say the store matches the source *as decoded*. It
    is the raw leg that carries the recoverable evidence, and G3 that reports the loss.

    The ``RuntimeWarning`` is asserted rather than filtered (**SP6**): these words reach
    the regime that raises it, and a run that stopped raising it would be a changed
    measurement, not a quieter one.
    """
    source, store, result, _ = destroyed
    with pytest.warns(RuntimeWarning, match="overflow encountered in ibm2ieee"):
        plane = plane_4(source, store, result.spec.segy_spec)

    assert plane.status == "PASS"
    assert plane.evidence["mismatch_count"] == 0
    assert plane.evidence["raw_ibm32_words_verified"] is True
    assert plane.evidence["raw_ibm32_identical"] is True
