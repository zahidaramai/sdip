"""Probe **P4**'s mitigation — the parallel ``uint8`` trace-header plane.

**P4 ran twice against the same store and the two readers disagreed.** TensorStore 0.1.85
accepts the structured ``headers`` array's ``struct`` ``data_type`` and read 97 of 97
fields byte-identically; zarr-java 0.2.0 refuses it outright; ``zarr-python`` accepts it
with a warning (``DECISIONS.md`` D-0047). ``struct`` has **no Zarr v3 specification**, so
the reader that declines it is standards-conformant and still right.

§10.3 — *no consumer is required to install ``sdip`` or ``mdio``* — is the reason
adopting SDIP is a reversible decision, and it was resting on one implementation's
goodwill toward an unspecified dtype. A 2-D ``uint8`` array is as portable as Zarr gets.

The tests below assert four things the array has to be for that to mean anything:

1. its ``data_type`` is a plain **core-spec** string, read out of ``zarr.json``;
2. its bytes are the **source's** bytes, checked against the file by raw offset and
   against the generator's planted ground truth — not a re-serialisation of the parsed
   array, which would agree with Plane 3's field leg by construction;
3. Plane 3's byte leg **binds**: a corrupted plane fails G2c while the field leg stays
   clean;
4. it does **not** claim to fix what it does not fix (``OPEN_DEBTS`` D32).
"""

from __future__ import annotations

import json
import shutil

import numpy as np
import pytest
import zarr

from sdip._pins import SEGY_TRACE_HEADER_BYTES as HEADER
from sdip.equivalence import plane_3, plane_5
from sdip.equivalence.planes import store_dimensions
from sdip.export import export
from sdip.guard.warn import WarningLedger, recording_warnings
from sdip.ingest import attach_raw_file_headers, ingest, read_raw_file_headers
from sdip.ingest.file_headers import file_headers_persisted
from sdip.ingest.header_plane import (
    ARRAY_NAME,
    ATTR_AUTHORITATIVE,
    ATTR_BYTE_LAYOUT,
    ATTR_CONTAINER,
    ATTR_FILL_BYTE,
    ATTR_LIMITATION,
    ATTR_LIVE_MASK,
    ATTR_PROBE,
    ATTR_RATIONALE,
    ATTR_UNDECODED,
    BYTE_AXIS_NAME,
    FILL_BYTE,
    TRACE_DATA_OFFSET,
    attach_header_plane,
)
from tests.fixtures.generators import PLANTED_BYTES, make_poststack3d, read_planted
from tests.fixtures.generators.irregular import make_sparse_grid

pytestmark = pytest.mark.integration

SAMPLE_WORD_BYTES = 4
"""Rev 1's ``ibm32`` sample width. The fixture's, so the offset arithmetic below can be
written out longhand rather than borrowed from the module under test."""

PRESTACK_GEOMETRY = "streamer_shot_3d"
"""A three-dimensional grid indexed on ``shot_point``/``cable``/``channel``.

Chosen because it needs no MDIO grid override and probe P7 measured all five planes
passing on it — so a failure here is about the header plane and nothing else.
"""


@pytest.fixture(scope="module")
def ingested(tmp_path_factory):
    """One real ingest of the Appendix A.1 article, reused. Conversion is the slow part."""
    root = tmp_path_factory.mktemp("p4-plane")
    article = make_poststack3d(root / "src.sgy")
    result = ingest(article.path, root / "out.mdio")
    return article, root / "out.mdio", result


def _group(store) -> zarr.Group:
    return zarr.open_group(str(store), mode="r")


def test_every_store_gets_the_plane_unconditionally(ingested):
    """Decision 4. Every store has headers, and the portability problem is not conditional.

    The ``ibm32`` raw-sample view is written only for the one sample format whose decode
    probe P2 measured as lossy. Nothing analogous applies here: a reader that cannot
    parse ``struct`` cannot parse it for any source.
    """
    _, _, result = ingested
    assert result.header_plane is not None
    assert result.header_plane.array == ARRAY_NAME
    assert result.header_plane.bytes_per_trace == HEADER
    assert result.header_plane.traces_written == 30
    assert result.header_plane.source_trace_count == 30
    assert result.header_plane.complete is True
    assert result.to_json()["header_plane"]["probe"] == "P4"


def test_the_plane_is_shaped_by_the_store_own_grid(ingested):
    """Grid read from the store's ``dimension_names``; nothing hard-codes inline/crossline.

    That was defect D-0039, which made all three per-trace planes unrunnable on every
    prestack geometry. See also
    :func:`test_the_grid_comes_from_the_store_on_a_geometry_that_is_not_inline_crossline`.
    """
    _, store, _ = ingested
    group = _group(store)
    plane, structured = group[ARRAY_NAME], group["headers"]
    assert plane.shape == (*structured.shape, HEADER)
    assert plane.dtype == np.uint8
    dimensions = plane.metadata.to_dict()["dimension_names"]
    assert tuple(dimensions) == (*store_dimensions(group), BYTE_AXIS_NAME)


def test_the_data_type_is_a_plain_core_spec_string(ingested):
    """**The whole point of the array**, read straight out of ``zarr.json``.

    A ``data_type`` that is a JSON string names a core-spec type; one that is an object
    is an extension with no Zarr v3 specification, which is what ``headers`` carries and
    what zarr-java refused. No warning from anybody is needed to establish this
    (``DECISIONS.md`` D-0004): the store is the evidence.
    """
    _, store, _ = ingested
    plane_type = json.loads((store / ARRAY_NAME / "zarr.json").read_text())["data_type"]
    structured_type = json.loads((store / "headers" / "zarr.json").read_text())["data_type"]
    assert plane_type == "uint8"
    assert isinstance(plane_type, str)
    assert not isinstance(structured_type, str), "the array this one exists to shadow"


def test_the_plane_carries_only_blosc_or_zstd(ingested):
    """SP3. A lossy codec here would destroy the bytes the array exists to preserve."""
    _, store, _ = ingested
    codecs = {c["name"] for c in _group(store)[ARRAY_NAME].metadata.to_dict()["codecs"]}
    assert codecs <= {"bytes", "blosc", "zstd"}


def test_the_array_says_what_it_is_holding(ingested):
    """A consumer must learn what this array is from the array, not from a document."""
    _, store, _ = ingested
    attrs = dict(_group(store)[ARRAY_NAME].attrs)
    assert attrs[ATTR_UNDECODED] is True
    assert attrs[ATTR_PROBE] == "P4"
    assert attrs[ATTR_FILL_BYTE] == FILL_BYTE
    assert "1-240 in source order" in attrs[ATTR_BYTE_LAYOUT]
    assert "CONTAINER" in attrs[ATTR_CONTAINER]
    assert "D-0047" in attrs[ATTR_RATIONALE]
    assert "AUTHORITATIVE for Plane 3" in attrs[ATTR_AUTHORITATIVE]
    assert "trace_mask" in attrs[ATTR_LIVE_MASK]


def test_the_array_states_the_limitation_it_does_not_fix(ingested):
    """OPEN_DEBTS D32, on the array itself rather than only in a decision record.

    zarr-java's ``Group.list()`` fails outright because ``segy_file_header`` keeps
    ``fixed_length_utf32``. **This plane does not fix that.** A consumer told the
    portability problem was solved would find out at enumeration time.
    """
    _, store, _ = ingested
    limitation = dict(_group(store)[ARRAY_NAME].attrs)[ATTR_LIMITATION]
    assert "Group.list()" in limitation
    assert "segy_file_header" in limitation
    assert "D32" in limitation


def test_every_stored_byte_is_the_byte_in_the_source(ingested):
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
        base = TRACE_DATA_OFFSET + ordinal * stride
        assert bytes(stored[cell]) == blob[base : base + HEADER]


def test_the_plane_carries_the_bytes_the_revision_leaves_unnamed(ingested):
    """Bytes 233-240 against the generator's **planted** ground truth, not against a reader.

    ``read_planted`` uses no spec at all. Two readers agreeing with each other is not
    evidence; agreement with a value the generator put in the file is.
    """
    article, store, _ = ingested
    planted = read_planted(article.path, article.trace_count, article.samples_per_trace)
    stored = np.asarray(_group(store)[ARRAY_NAME][:])
    n_crossline = len(article.crosslines)

    for ordinal in range(article.trace_count):
        cell = (ordinal // n_crossline, ordinal % n_crossline)
        for k, byte_position in enumerate(PLANTED_BYTES):
            assert int(stored[cell][byte_position - 1]) == int(planted[ordinal, k])


def test_the_plane_holds_source_order_bytes_not_a_re_serialisation(ingested):
    """Decision 1. The plane was read from the FILE, not from the parsed array.

    A plane derived by re-serialising ``headers`` would agree with Plane 3's field leg by
    construction and prove nothing, which is the whole reason the byte leg exists. The
    evidence that it was not is the byte **order**: SEG-Y stores header fields
    big-endian, and reading the plane's slice for a field big-endian reproduces the value
    the structured array holds — which a copy of the store's own little-endian buffer
    would not.
    """
    _, store, result = ingested
    group = _group(store)
    stored = np.asarray(group[ARRAY_NAME][:])
    structured = np.asarray(group["headers"][:])
    cell = (0, 0)

    checked = 0
    for field in result.spec.segy_spec.trace.header.fields:
        if field.format.dtype.itemsize == 1:
            continue  # a single byte has no order to get wrong
        start = field.byte - 1
        raw = bytes(stored[cell][start : start + field.format.dtype.itemsize])
        big_endian = np.frombuffer(raw, dtype=field.format.dtype.newbyteorder(">"))[0]
        assert big_endian == structured[field.name][cell], field.name
        checked += 1
    assert checked > 0, "no multi-byte field was checked, so nothing was demonstrated"


def test_plane_3_reports_the_byte_leg_as_separate_evidence(ingested):
    """``raw_header_*`` sits beside the field-wise verdict; neither substitutes for it."""
    article, store, result = ingested
    plane = plane_3(article.path, store, result.spec.segy_spec, g1_passed=True)
    assert plane.status == "PASS"
    assert plane.evidence["raw_header_plane_present"] is True
    assert plane.evidence["raw_header_bytes_verified"] is True
    assert plane.evidence["raw_header_bytes_identical"] is True
    assert plane.evidence["raw_header_n"] == article.trace_count
    assert plane.evidence["raw_header_bytes_per_trace"] == HEADER
    assert plane.evidence["raw_header_mismatch_count"] == 0
    assert plane.evidence["raw_header_first_difference"] is None
    # The field leg is untouched and still reports its own numbers.
    assert plane.evidence["mismatch_count"] == 0


def test_a_corrupted_plane_byte_fails_g2c_without_touching_the_field_leg(ingested, tmp_path):
    """**The byte leg BINDS.** D-0049's ruling, applied to Plane 3.

    ``headers_raw_uint8`` is the copy of the trace headers a non-Python consumer can
    actually read. Left as evidence-only, SDIP could write a corrupted plane and no gate
    would notice — a store certifiable with its portable copy already gone. Evidence
    nothing can fail is not a check; it is a comment (**SP11**).

    The two legs stay **independent**, which is what this pins: the byte leg fails and
    the field leg's ``mismatch_count`` stays 0.
    """
    article, store, result = ingested
    copy = tmp_path / "corrupt.mdio"
    shutil.copytree(store, copy)
    group = zarr.open_group(str(copy), mode="r+")
    original = int(np.asarray(group[ARRAY_NAME][0, 0, 232]))
    group[ARRAY_NAME][0, 0, 232] = np.uint8(original ^ 0x01)

    plane = plane_3(article.path, copy, result.spec.segy_spec, g1_passed=True)
    assert plane.evidence["raw_header_bytes_identical"] is False
    assert plane.evidence["raw_header_mismatch_count"] == 1
    difference = plane.evidence["raw_header_first_difference"]
    assert difference["cell"] == [0, 0]
    assert difference["byte_offset"] == 232
    assert difference["expected"] == original
    assert difference["observed"] == original ^ 0x01
    assert difference["differing_bytes"] == 1
    assert plane.status == "FAIL", "a corrupted portable copy must fail G2c"
    # The field leg is genuinely untouched: the failure comes from the byte leg alone.
    assert plane.evidence["mismatch_count"] == 0


def test_an_absent_plane_is_reported_as_unchecked_not_as_a_pass(ingested, tmp_path):
    """`NOT_RUN` is not a pass. A store with no plane must not read as one that matched.

    ``None`` is correct for a store written before this array existed, and it does **not**
    fail the gate — only an explicit ``False`` does.
    """
    article, store, result = ingested
    copy = tmp_path / "no-plane.mdio"
    shutil.copytree(store, copy)
    shutil.rmtree(copy / ARRAY_NAME)

    plane = plane_3(article.path, copy, result.spec.segy_spec, g1_passed=True)
    assert plane.status == "PASS"
    assert plane.evidence["raw_header_plane_present"] is False
    assert plane.evidence["raw_header_bytes_verified"] is False
    assert plane.evidence["raw_header_bytes_identical"] is None
    assert plane.evidence["raw_header_first_difference"] is None


def test_the_round_trip_stays_byte_identical_with_the_plane_present(ingested, tmp_path):
    """G3. The plane is an addition to the store, not a change to what is exported."""
    article, store, result = ingested
    round_trip = export(
        store, tmp_path / "exported.sgy", result.spec.segy_spec, source=article.path
    )
    assert round_trip.byte_identical is True
    assert round_trip.status == "PASS"


def test_padding_carries_the_fill_byte_and_is_never_compared(tmp_path):
    """SP12. Padding is not data, and no ``uint8`` can announce itself as padding.

    A sparse grid has 54 cells no source trace maps to. They hold ``0x00``, which is a
    perfectly valid trace-header byte, so the store's ``trace_mask`` is the only
    discriminator — the same exposure ``OPEN_DEBTS`` D29 records for the structured array.
    """
    article = make_sparse_grid(tmp_path / "sparse.sgy")
    store = tmp_path / "sparse.mdio"
    result = ingest(article.path, store, revision=article.revision)

    group = _group(store)
    mask = np.asarray(group["trace_mask"][:]).astype(bool)
    stored = np.asarray(group[ARRAY_NAME][:])
    assert int((~mask).sum()) == 54
    assert np.array_equal(np.unique(stored[~mask]), np.array([FILL_BYTE], dtype=np.uint8))

    plane = plane_3(article.path, store, result.spec.segy_spec, g1_passed=True)
    live = plane_5(article.path, store, result.spec.segy_spec).evidence["live_cells_in_mask"]
    assert plane.evidence["raw_header_n"] == live
    assert plane.evidence["raw_header_bytes_identical"] is True
    assert result.header_plane is not None
    assert result.header_plane.traces_written == live


@pytest.fixture(scope="module")
def prestack(tmp_path_factory):
    """One prestack store, converted the way probe **P7** converts them.

    ``sdip.ingest.ingest`` cannot reach prestack geometry — it builds its spec from the
    revision standard and offers no way to declare a field the standard does not name
    (P7 leg 1) — so the conversion is driven here the way P7's leg 2 drives it, and the
    header plane is attached explicitly. The point under test is the plane's shaping, not
    the declaration gap.
    """
    from tests.fixtures.generators.prestack import build_fixture

    root = tmp_path_factory.mktemp("p4-plane-prestack")
    article = build_fixture(PRESTACK_GEOMETRY, root / f"{PRESTACK_GEOMETRY}.sgy")
    spec = article.spec()
    store = root / f"{PRESTACK_GEOMETRY}.mdio"

    raw = read_raw_file_headers(article.path)
    ledger = WarningLedger()
    with recording_warnings(ledger, reemit=False), file_headers_persisted():
        from mdio import segy_to_mdio
        from mdio.builder.template_registry import get_template

        segy_to_mdio(
            segy_spec=spec,
            mdio_template=get_template(article.geometry.template),
            input_path=article.path,
            output_path=store,
            overwrite=True,
        )
    attach_raw_file_headers(store, raw)
    written = attach_header_plane(store, article.path, spec)
    return article, store, spec, written


def test_the_grid_comes_from_the_store_on_a_geometry_that_is_not_inline_crossline(prestack):
    """Defect **D-0039**, which is why this test exists on a three-dimensional grid.

    All three per-trace planes once assumed ``("inline", "crossline")`` and returned
    ``KeyError: 'inline'`` on all seven prestack stores, so the Equivalence Contract could
    not be evaluated for prestack at all. A plane shaped by a constant would reintroduce
    exactly that.
    """
    _, store, _, written = prestack
    group = _group(store)
    dimensions = store_dimensions(group)

    assert "inline" not in dimensions
    assert len(dimensions) == 3
    assert written.dimensions == (*dimensions, BYTE_AXIS_NAME)
    assert group[ARRAY_NAME].shape == (*group["headers"].shape, HEADER)
    assert tuple(group[ARRAY_NAME].metadata.to_dict()["dimension_names"]) == written.dimensions


def test_the_byte_leg_runs_and_binds_on_prestack(prestack):
    """The leg has to be evaluable on every geometry, or it is a check only poststack gets."""
    article, store, spec, written = prestack
    plane = plane_3(article.path, store, spec, g1_passed=True)
    assert plane.status == "PASS"
    assert plane.evidence["raw_header_bytes_verified"] is True
    assert plane.evidence["raw_header_bytes_identical"] is True
    assert plane.evidence["raw_header_n"] == written.traces_written
    assert written.complete is True
