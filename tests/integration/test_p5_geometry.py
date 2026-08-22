"""Probe **P5** — irregular geometry. Pre-registered in ``prereg/P5-irregular-geometry.md``.

Every measurement banked before this probe used a perfectly regular grid with zero dead
traces, so nothing in the repository said what happens to a duplicate index tuple, a
sparse grid, a ragged line, a coordinate scalar of zero, a little-endian file or a rev 0
header. Each of those is ordinary in production data and each fails **silently** if it
fails at all, which is why the probe exists.

**A fixture that cannot be ingested is a result, not an obstacle.** Four of the ten
conditions do not convert at all under the pinned ``multidimio==1.2.1``. The runner
therefore records the error and continues, and the per-condition tests below assert the
outcome that was *measured* — including the failures. That is the point: the table is a
banked measurement, so an upstream change that silently alters any of these outcomes
fails here rather than passing unnoticed.

``MDIO_IGNORE_CHECKS`` is **absent throughout**, asserted before anything is built.
Setting it is exactly how this probe would be faked: it demotes MDIO's grid-sparsity
error to a log line, and a suppressible gate is not a gate (**SP11**, spec §9.1).

Comparison is exact everywhere. No tolerance appears in this file and none may be added.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import zarr
from segy import SegyFile

from sdip.equivalence import PlaneResult, plane_1, plane_2, plane_3, plane_4, plane_5
from sdip.export import RoundTripResult, export
from sdip.guard.env import check_barred_env_vars
from sdip.ingest import ingest
from sdip.spec.generator import build_gap_free_spec
from tests.fixtures.generators.irregular import (
    FIXTURE_NAMES,
    IrregularSegy,
    build_fixture,
    make_byte_swapped,
    make_irregular,
)

pytestmark = pytest.mark.integration

PREREGISTERED: tuple[str, ...] = (
    "dead_traces",
    "duplicate_index",
    "sparse_grid",
    "ragged_lines",
    "missing_lines",
    "coord_scalar_zero",
    "coord_scalar_pos",
    "coord_scalar_neg",
    "byte_swapped",
    "rev0_minimal",
)
"""The fixture table from the pre-registration, transcribed. Changing it after seeing a
result would break **SP9**, so a test pins it against the generator's own table."""


@dataclass(frozen=True, slots=True)
class FixtureRun:
    """One condition carried as far as it goes: ingest, five planes, export."""

    name: str
    article: IrregularSegy
    store: Path
    ingested: bool
    error: str | None
    spec: Any
    planes: tuple[PlaneResult, ...]
    roundtrip: RoundTripResult | None

    @property
    def plane_status(self) -> list[str]:
        """Plane 1 to Plane 5 verdicts, in order. Empty when the ingest did not happen."""
        return [p.status for p in self.planes]

    def plane(self, number: int) -> PlaneResult:
        """One plane's result by number."""
        return next(p for p in self.planes if p.plane == number)

    def group(self) -> Any:
        """The store, opened read-only with stock zarr."""
        return zarr.open_group(str(self.store), mode="r")

    def mask(self) -> np.ndarray:
        """The live/dead mask as booleans."""
        return np.asarray(self.group()["trace_mask"][:]).astype(bool)


def _run(name: str, root: Path) -> FixtureRun:
    """Ingest one condition and carry it as far as it goes.

    The broad ``except`` is deliberate and is the pre-registered method: irregular
    geometry is exactly where a converter breaks, and a condition that refuses to
    convert is a measurement to record, not a reason to abandon the other nine.
    """
    article = build_fixture(name, root / f"{name}.sgy")
    store = root / f"{name}.mdio"
    try:
        result = ingest(article.path, store, revision=article.revision)
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        return FixtureRun(name, article, store, False, error, None, (), None)

    spec = result.spec.segy_spec
    planes = (
        plane_1(article.path, store),
        plane_2(article.path, store),
        plane_3(article.path, store, spec, g1_passed=result.g1.passed),
        plane_4(article.path, store, spec),
        plane_5(article.path, store, spec),
    )
    roundtrip = export(store, root / f"{name}.back.sgy", spec, source=article.path)
    return FixtureRun(name, article, store, True, None, spec, planes, roundtrip)


@pytest.fixture(scope="module")
def probe(tmp_path_factory) -> dict[str, FixtureRun]:
    """The whole probe, run once. Conversion is the slow part; the assertions are not."""
    assert check_barred_env_vars() == [], (
        "a barred environment variable is set. Every result below would be worthless: "
        "MDIO_IGNORE_CHECKS demotes the grid-sparsity error to a log line (spec 9.1)."
    )
    root = tmp_path_factory.mktemp("p5")
    return {name: _run(name, root) for name in PREREGISTERED}


# ---------------------------------------------------------------------------
# Pre-registration discipline
# ---------------------------------------------------------------------------


def test_the_generator_table_is_the_pre_registered_table():
    """SP9. The conditions were fixed before the run and may not be edited to suit it."""
    assert FIXTURE_NAMES == PREREGISTERED


def test_no_barred_variable_is_set_for_any_of_it(probe):
    """SP11. Also checks no ingest failed *because* SDIP refused a barred variable."""
    assert check_barred_env_vars() == []
    for run in probe.values():
        if run.error is not None:
            assert "barred environment variable" not in run.error


@pytest.mark.parametrize("name", PREREGISTERED)
def test_every_fixture_is_deterministic(name, tmp_path):
    """G6 / SP9. A fixture that varies between builds makes determinism unmeasurable.

    REGRESSION: ``SegyFactory.create_textual_header()`` with no argument embeds
    ``datetime.now()`` at second resolution, so two builds straddling a second boundary
    differ — flaky, not reliably broken. Every generator passes explicit text.
    """
    first = build_fixture(name, tmp_path / "a" / f"{name}.sgy")
    second = build_fixture(name, tmp_path / "b" / f"{name}.sgy")
    assert first.path.read_bytes() == second.path.read_bytes()


@pytest.mark.parametrize("name", PREREGISTERED)
def test_every_fixture_stays_inside_the_pre_registered_trace_budget(name, tmp_path):
    """N <= 200 per fixture. P5 probes correctness, not scale."""
    article = build_fixture(name, tmp_path / f"{name}.sgy")
    assert article.trace_count <= 200


# ---------------------------------------------------------------------------
# The measured outcome table
# ---------------------------------------------------------------------------

INGESTS: dict[str, str | None] = {
    "dead_traces": None,
    "duplicate_index": "GridTraceCountError",
    "sparse_grid": None,
    "ragged_lines": None,
    "missing_lines": None,
    "coord_scalar_zero": "Invalid coordinate scalar: 0",
    "coord_scalar_pos": None,
    "coord_scalar_neg": None,
    "byte_swapped": "256 is not a valid DataSampleFormatCode",
    "rev0_minimal": "Required fields ['cdp_x', 'cdp_y', 'crossline', 'inline']",
}
"""Measured on 2026-08-22 against ``multidimio==1.2.1`` / ``segy==0.6.0``. ``None`` means
the ingest succeeded; a string is a substring of the error that was actually raised.

This is a **record of what happened**, not a wish. Four conditions do not convert, and
pinning the exact error is what turns "irregular geometry sometimes fails" into a claim
a stranger can check and an upstream bump can falsify.
"""


@pytest.mark.parametrize("name", PREREGISTERED)
def test_the_ingest_outcome_is_the_one_that_was_measured(probe, name):
    expected = INGESTS[name]
    run = probe[name]
    if expected is None:
        assert run.ingested, f"{name} was measured as ingesting; it now fails: {run.error}"
    else:
        assert not run.ingested, f"{name} was measured as failing to ingest; it now succeeds"
        assert expected in (run.error or "")


@pytest.mark.parametrize("name", [n for n, e in INGESTS.items() if e is None])
def test_every_store_that_exists_passes_all_five_planes(probe, name):
    """Where a store exists at all, equivalence holds exactly. No tolerance anywhere."""
    run = probe[name]
    assert run.plane_status == ["PASS"] * 5
    assert [p.gate for p in run.planes] == ["G2a", "G2b", "G2c", "G2d", "G2e"]


@pytest.mark.parametrize("name", [n for n, e in INGESTS.items() if e is None])
def test_every_store_that_exists_round_trips_byte_identically(probe, name):
    """G3: ``sha256(export) == sha256(source)``, whole file, no per-field reconciliation.

    Padding never reaches the export: a store with 54 invented cells still writes back
    the exact 11,808 source bytes.
    """
    run = probe[name]
    assert run.roundtrip is not None
    assert run.roundtrip.status == "PASS"
    assert run.roundtrip.byte_identical
    assert run.roundtrip.export_bytes == run.article.byte_size
    assert run.roundtrip.first_difference() is None


# ---------------------------------------------------------------------------
# dead_traces — a measured zero is not padding
# ---------------------------------------------------------------------------


def test_dead_traces_are_live_traces_that_happen_to_be_zero(probe):
    """80 traces on a complete 8 x 10 grid, every third one all zero, zero padding.

    A dead trace is *measured*. The survey recorded it and got zero. Marking it dead in
    the live mask would claim it was never acquired, which is a different — and false —
    statement about the survey.
    """
    run = probe["dead_traces"]
    article = run.article
    assert article.trace_count == 80
    assert len(article.dead_ordinals) == 27
    assert article.padding_cell_count == 0

    mask = run.mask()
    assert mask.shape == (8, 10)
    assert int(mask.sum()) == 80, "every recorded trace is live, zero-valued or not"
    assert run.plane(5).evidence["padding_cells"] == 0
    assert run.plane(4).evidence["n"] == 80, "Plane 4 compared all 80, dead ones included"


def test_a_dead_trace_is_compared_exactly_not_skipped(probe):
    """The zeros are checked, not assumed. A skipped trace is an unchecked trace."""
    run = probe["dead_traces"]
    group = run.group()
    volume = group["amplitude"][:]
    source = SegyFile(str(run.article.path), spec=run.spec)
    samples = source.sample[:]
    for ordinal in sorted(run.article.dead_ordinals)[:4]:
        row, column = divmod(ordinal, len(run.article.crosslines))
        assert np.array_equal(np.asarray(samples[ordinal]), np.asarray(volume[row, column]))
        assert not np.any(np.asarray(volume[row, column]))


# ---------------------------------------------------------------------------
# duplicate_index — the clause that loses data quietly
# ---------------------------------------------------------------------------


def test_a_duplicate_index_tuple_is_refused_at_ingest_not_overwritten(probe):
    """**The headline result.** Two traces claiming one cell stop the conversion dead.

    MDIO counts the live cells its grid produced (29) against the traces the file
    declares (30) and raises ``GridTraceCountError``. Nothing is written, so there is no
    store in which a trace could go missing.

    The error type matters as much as the refusal. ``MDIO_IGNORE_CHECKS`` gates
    ``GridTraceSparsityError`` in ``mdio/ingestion/grid_qc.py`` — **not** this one, which
    is raised unconditionally in ``mdio/ingestion/segy/pipeline.py``. The duplicate
    defence therefore does not depend on a suppressible check (**SP11**).
    """
    run = probe["duplicate_index"]
    article = run.article
    assert article.trace_count == 30
    assert article.distinct_cell_count == 29
    assert article.duplicate_pairs == ((101, 204),)
    assert article.ordinals_for(101, 204) == (10, 11)

    assert not run.ingested
    assert "GridTraceCountError" in (run.error or "")
    assert "29 != 30" in (run.error or "")
    assert not run.store.exists(), "a refused ingest must leave nothing behind"


def test_the_engine_surfaces_a_duplicate_even_if_a_store_ever_held_one(tmp_path):
    """The second line of defence, measured rather than assumed.

    Upstream refuses the duplicate today, so the engine's own detection would never be
    reached — and an undetected detector is not a detector (**SP11**). This builds the
    same geometry with the duplicate removed, ingests *that*, then runs Plane 5 with the
    **duplicate-bearing source**. That is precisely the situation a converter which
    overwrote silently would produce: 30 traces in, 29 live cells out.

    Plane 5 fails on three of its five checks and names both colliding ordinals. A
    duplicate is data loss, not a labelling problem: one trace is absent and nothing in
    the store records that it existed.
    """
    duplicated = build_fixture("duplicate_index", tmp_path / "dup.sgy")
    without = [pair for ordinal, pair in enumerate(duplicated.index_pairs) if ordinal != 11]
    deduplicated = make_irregular(tmp_path / "dedup.sgy", index_pairs=without)

    store = tmp_path / "dedup.mdio"
    result = ingest(deduplicated.path, store)
    plane = plane_5(duplicated.path, store, result.spec.segy_spec)

    assert plane.status == "FAIL"
    assert plane.evidence["failed_checks"] == ["count_matches", "map_invertible", "no_duplicates"]
    assert plane.evidence["trace_map"]["duplicate_cells"] == [
        {"cell": [1, 4], "source_ordinals": [10, 11]}
    ]
    assert plane.evidence["source_trace_count"] == 30
    assert plane.evidence["live_cells_in_mask"] == 29


# ---------------------------------------------------------------------------
# sparse_grid — padding is not data (SP12)
# ---------------------------------------------------------------------------


def test_padding_is_excluded_from_plane_4_rather_than_compared(probe):
    """27 traces in an 81-cell grid. Plane 4 compares 27, not 81 (**SP12**)."""
    run = probe["sparse_grid"]
    assert run.article.trace_count == 27
    assert run.article.padding_cell_count == 54

    mask = run.mask()
    assert mask.shape == (9, 9)
    assert int(mask.sum()) == 27
    assert run.plane(4).evidence["n"] == 27
    assert run.plane(4).evidence["padding_excluded"] is True
    assert run.plane(5).evidence["padding_cells"] == 54
    assert run.plane(3).evidence["n"] == 27


def test_amplitude_padding_is_nan_and_header_padding_is_zero(probe):
    """What regularisation actually puts in the invented cells. Two different answers.

    ``amplitude`` and the coordinate arrays are filled with ``NaN``, which announces
    itself: no SEG-Y sample decodes to ``NaN`` from this fixture, so a consumer that
    ignores the mask still cannot mistake padding for a reading.

    The ``headers`` array cannot hold ``NaN`` — it is a structured integer dtype — so its
    padding is **zero**, and a zero in ``inline`` is indistinguishable by value from an
    inline somebody actually numbered zero. For the header array the live mask is the
    only thing standing between a consumer and a fabricated index (**SP12**).
    """
    run = probe["sparse_grid"]
    group = run.group()
    padding = ~run.mask()

    assert np.all(np.isnan(np.asarray(group["amplitude"][:])[padding]))
    assert np.all(np.isnan(np.asarray(group["cdp_x"][:])[padding]))
    assert np.all(np.isnan(np.asarray(group["cdp_y"][:])[padding]))

    headers = group["headers"][:]
    assert np.array_equal(np.unique(headers["inline"][padding]), np.array([0]))
    assert np.array_equal(np.unique(headers["pad_233"][padding]), np.array([0], dtype=np.uint8))


def test_the_live_mask_separates_a_measured_zero_from_padding(probe):
    """The fourth falsifier clause, measured directly.

    Ordinals 4 and 22 are all-zero traces the survey recorded. They sit in the same array
    as 54 cells nobody recorded. The mask marks the first live and the second not, so the
    distinction survives — and it survives on the mask, not on the values.
    """
    run = probe["sparse_grid"]
    group = run.group()
    volume = np.asarray(group["amplitude"][:])
    mask = run.mask()

    source = SegyFile(str(run.article.path), spec=run.spec)
    headers = source.header[:]
    inlines = list(np.asarray(group["inline"][:]))
    crosslines = list(np.asarray(group["crossline"][:]))

    for ordinal in sorted(run.article.dead_ordinals):
        cell = (
            inlines.index(int(headers["inline"][ordinal])),
            crosslines.index(int(headers["crossline"][ordinal])),
        )
        assert mask[cell], "a measured zero trace is live"
        assert not np.any(volume[cell]), "and it is zero, exactly"
        assert not np.any(np.isnan(volume[cell])), "a measured zero is never NaN padding"

    assert np.all(np.isnan(volume[~mask])), "and nothing unmeasured is anything but padding"


def test_a_grid_sparser_than_the_upstream_limit_is_refused_outright(tmp_path):
    """The sparsity clause of the falsifier, taken to the threshold.

    ``sparse_grid`` has a sparsity ratio of 3.0 — above MDIO's warn threshold of 2.0,
    below its error threshold of 10.0 — so it converts with a **log line** and no
    suppressed check anywhere.

    A crooked line does not. Twelve traces each with a unique inline *and* a unique
    crossline span a 144-cell grid, ratio 12.0, and ``GridTraceSparsityError`` stops the
    conversion. **That is the error ``MDIO_IGNORE_CHECKS`` demotes to a log line**, so it
    is the one place in this probe where the barred variable would make a failure
    disappear. It is not set, and the correct reading of this result is that SDIP cannot
    ingest grids sparser than ratio 10 — not that the check should be switched off.
    """
    crooked = make_irregular(
        tmp_path / "crooked.sgy", index_pairs=[(100 + i, 200 + i) for i in range(12)]
    )
    assert crooked.padding_cell_count == 132

    with pytest.raises(Exception, match="very sparse") as raised:
        ingest(crooked.path, tmp_path / "crooked.mdio")
    assert type(raised.value).__name__ == "GridTraceSparsityError"
    assert check_barred_env_vars() == []


# ---------------------------------------------------------------------------
# ragged_lines and missing_lines
# ---------------------------------------------------------------------------


def test_ragged_lines_are_padded_at_the_line_ends_and_nowhere_else(probe):
    """Lines of 10, 4, 7, 2 and 9 traces in a 5 x 10 grid: 32 live, 18 padded."""
    run = probe["ragged_lines"]
    assert run.article.trace_count == 32
    assert run.article.padding_cell_count == 18

    mask = run.mask()
    assert mask.shape == (5, 10)
    assert [int(row.sum()) for row in mask] == [10, 4, 7, 2, 9]
    assert run.plane(4).evidence["n"] == 32


def test_missing_inlines_vanish_from_the_index_axis_entirely(probe):
    """Inlines 104-106 are absent from the source and absent from the store's axis.

    The result is a **dense** 7 x 6 grid with no padding at all: the store cannot be
    distinguished from a survey that only ever had seven inlines. Nothing is fabricated,
    so **SP12** holds — but nothing records the hole either, and an interior gap in an
    inline range is exactly the shape of an acquisition problem a reader would want to
    see. The store's own inline axis is the only evidence, and it is evidence a consumer
    has to think to look for.
    """
    run = probe["missing_lines"]
    group = run.group()
    assert np.array_equal(
        np.asarray(group["inline"][:]), np.array([100, 101, 102, 103, 107, 108, 109])
    )
    assert run.article.padding_cell_count == 0
    assert int(run.mask().sum()) == 42
    assert run.plane(5).evidence["padding_cells"] == 0


# ---------------------------------------------------------------------------
# Coordinate scalars
# ---------------------------------------------------------------------------


def test_a_coordinate_scalar_of_zero_is_refused_for_rev_1(probe):
    """Common in the wild, rejected by the pinned MDIO.

    ``mdio/segy/scalar.py`` accepts ``abs(scalar)`` in ``{1, 10, 100, 1000, 10000}`` and
    normalises ``0`` to ``1`` **only for rev 2 and above**. A rev 0 or rev 1 file with a
    zero scalar — which the standard leaves undefined and which vendors write constantly
    — cannot be converted at all.
    """
    run = probe["coord_scalar_zero"]
    assert not run.ingested
    assert "Invalid coordinate scalar: 0" in (run.error or "")
    assert "REV1" in (run.error or "")


@pytest.mark.parametrize(
    ("name", "scalar"), [("coord_scalar_pos", 100), ("coord_scalar_neg", -100)]
)
def test_a_nonzero_coordinate_scalar_is_applied_to_the_derived_coordinate_arrays(
    probe, name, scalar
):
    """The scalar is honoured — and the scaled result is an **undeclared transform**.

    Positive multiplies, negative divides, which is what the standard says. The raw
    header value is untouched in ``headers``, so Plane 3 and the round trip are unaffected
    and no measured value is lost.

    The finding is narrower and worth stating precisely: the store carries ``cdp_x`` and
    ``cdp_y`` **coordinate arrays** holding scaled values that appear nowhere in the
    source, while the certificate's ``transforms_declared[]`` names only the sample-format
    decode. Under **SP1** the permitted transform is the declared one; this one is real,
    correct, and undeclared.
    """
    run = probe[name]
    group = run.group()
    headers = group["headers"][:]
    raw = int(headers["cdp_x"][0, 0])
    stored = float(np.asarray(group["cdp_x"][:])[0, 0])

    assert int(headers["coordinate_scalar"][0, 0]) == scalar
    expected = float(raw) * 100.0 if scalar > 0 else float(raw) / 100.0
    assert stored == expected
    assert stored != float(raw), "the coordinate array is derived, not the source value"
    assert run.plane(3).status == "PASS", "the raw header value itself is preserved"


# ---------------------------------------------------------------------------
# Byte order and revision 0
# ---------------------------------------------------------------------------


def test_a_little_endian_file_cannot_be_declared_to_sdip(probe):
    """The blocker is SDIP's own spec, not the format and not the pinned ``segy``.

    ``build_gap_free_spec`` inherits ``endianness = big`` from the revision standard and
    :func:`sdip.ingest.ingest` exposes no way to change it, so the little-endian binary
    header is read big-endian: sample-format code ``1`` arrives as ``0x0100`` and the
    conversion dies on ``256 is not a valid DataSampleFormatCode``.

    The same file reads correctly the moment the spec stops asserting a byte order —
    ``segy`` infers it from the binary header when ``spec.endianness is None``. So this is
    a missing declaration in SDIP, not a limitation upstream.
    """
    run = probe["byte_swapped"]
    assert run.article.endianness == "little"
    assert not run.ingested
    assert "256 is not a valid DataSampleFormatCode" in (run.error or "")
    assert build_gap_free_spec(1).segy_spec.endianness.value == "big"

    inferring = build_gap_free_spec(1)
    inferring.segy_spec.endianness = None
    handle = SegyFile(str(run.article.path), spec=inferring.segy_spec)
    headers = handle.header[:]
    assert int(handle.num_traces) == 20
    assert np.array_equal(np.unique(headers["inline"]), np.array([100, 101, 102, 103]))
    assert np.array_equal(np.unique(headers["crossline"]), np.array([200, 201, 202, 203, 204]))


def test_the_big_endian_twin_of_the_same_file_converts_and_round_trips(tmp_path):
    """The control for the byte-order finding.

    Identical arguments, identical geometry, one byte order apart. The big-endian variant
    converts, passes every plane and round trips byte-identically, so the little-endian
    failure is attributable to byte order and to nothing else in the fixture.
    """
    article = make_byte_swapped(tmp_path / "be.sgy", endianness="big")
    store = tmp_path / "be.mdio"
    result = ingest(article.path, store)
    spec = result.spec.segy_spec

    planes = [
        plane_1(article.path, store),
        plane_2(article.path, store),
        plane_3(article.path, store, spec, g1_passed=result.g1.passed),
        plane_4(article.path, store, spec),
        plane_5(article.path, store, spec),
    ]
    assert [p.status for p in planes] == ["PASS"] * 5

    roundtrip = export(store, tmp_path / "be.back.sgy", spec, source=article.path)
    assert roundtrip.status == "PASS"

    little = make_byte_swapped(tmp_path / "le.sgy", endianness="little")
    assert little.byte_size == article.byte_size
    assert little.path.read_bytes() != article.path.read_bytes()


def test_rev0_has_no_index_fields_for_the_template_to_bind(probe):
    """Rev 0 fails at the template, not at the spec. The distinction is the whole finding.

    G1 still passes for revision 0 — the gap-free spec covers all 240 bytes, because that
    is what fillers are for. What rev 0 does not have is a field *named* ``inline``,
    ``crossline``, ``cdp_x`` or ``cdp_y``: those byte positions were standardised later,
    and under a rev 0 spec they are ``pad_181`` through ``pad_196``.

    ``PostStack3DTime`` binds by field name, so it cannot bind at all. Reading rev 0 index
    values would require declaring the bytes — a customised spec — which
    :func:`sdip.ingest.ingest` does not currently accept.
    """
    run = probe["rev0_minimal"]
    assert run.article.revision == 0
    assert not run.ingested
    assert "Required fields ['cdp_x', 'cdp_y', 'crossline', 'inline']" in (run.error or "")
    assert "PostStack3DTime" in (run.error or "")

    built = build_gap_free_spec(0)
    declared = {field.name for field in built.segy_spec.trace.header.fields}
    assert {"inline", "crossline", "cdp_x", "cdp_y"}.isdisjoint(declared)
    assert {"pad_189", "pad_193"} <= declared
    assert built.coverage.gap_free, "the spec is complete; only the template cannot bind"
