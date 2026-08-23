"""Probe **P7** — the latency leg, run against the parameters Amendment A declared.

Pre-registered in ``prereg/P7-prestack-chunking.md``. The original parameter table was
left unfilled, so the first P7 run reported this leg **NOT RUN**: under **SP9** a
threshold invented after seeing a chunk shape is not a threshold. Amendment A fixed the
parameters — four geometries, three candidate chunk shapes each, four read patterns, a
2.0 s target, five repetitions, the median reported, and a correctness precondition —
and was committed in ``f23a1e5`` before any benchmark existed. This module is the run.

**Every number below is bounded by the correctness precondition, not by the target.**
A latency figure for a store that fails G2 measures how fast a wrong answer arrives, so
the precondition is enforced mechanically here: a store whose five planes do not all
``PASS`` produces no figure at all, and a test asserts that no figure exists for one.

What this file is not
---------------------
It is **not** a run of ``sdip ingest``. Two independent things stop that, both measured
by ``test_p7_prestack.py`` and neither closed since:

1. ``ingest()`` builds its spec from the revision standard, and every prestack template
   binds at least one name the standard does not use. The §6.4 override mechanism now
   supplies two of those names (``offset``, ``cdp``); the streamer names — ``cable``,
   ``channel``, ``gun``, ``sail_line`` — have no committed override, and the two
   geometries that need a *calculated* dimension need an MDIO ``grid_overrides`` value
   ``ingest()`` has no parameter for.
2. ``ingest()`` takes a template **name** and resolves it internally, so a caller cannot
   hand it a template whose chunk shape has been set. **Varying the chunk shape is not
   reachable through SDIP's API at all** — asserted below, because it is a finding.

So the stores are built the way leg 2 of ``test_p7_prestack.py`` builds them: SDIP's
ingest sequence with the geometry's index fields declared, through the pinned public
``segy_to_mdio``. That is what makes the *relative* comparison between chunk shapes
admissible; it is not a claim about ``sdip ingest``.

What "cold" meant, exactly
--------------------------
``purge`` needs ``sudo`` on macOS and was not available, so the OS unified buffer cache
was **not** dropped. What was dropped, per repetition: the Zarr group is re-opened from
the path, the array handle is re-acquired, and no array, buffer or decoded chunk is
carried across repetitions. Nothing else.

That makes every figure here a **lower bound** on a genuinely cold read, which makes the
comparison against the target **one-sided and lenient**: a shape that exceeds 2.0 s under
a warm page cache would exceed it cold, so an exceedance is real; a figure under 2.0 s
does not establish that the same read is under 2.0 s from cold storage. The leg was
declared to catch a *pathological* shape rather than to rank good ones, and a lenient
one-sided test is sufficient for that and insufficient for anything else. It is stated
here rather than in a footnote because a figure whose cache state is misdescribed is
worse than no figure.

Comparison is exact everywhere. No tolerance appears in this file and none may be added.
"""

from __future__ import annotations

import inspect
import statistics
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import zarr

from sdip.equivalence import PlaneResult, plane_1, plane_2, plane_3, plane_4
from sdip.equivalence import plane_5 as plane_5_checker
from sdip.equivalence.planes import store_dimensions
from sdip.guard.env import check_barred_env_vars
from sdip.guard.warn import WarningLedger, recording_warnings
from sdip.ingest import (
    attach_raw_file_headers,
    file_headers_persisted,
    ingest,
    read_raw_file_headers,
)
from sdip.spec.gate import g1
from tests.fixtures.generators.prestack import PrestackSegy, build_fixture

pytestmark = [pytest.mark.integration, pytest.mark.slow]

# ---------------------------------------------------------------------------
# The declared parameters. Amendment A, committed f23a1e5, before this file existed.
# A test reads them back out of the pre-registration and refuses to run against any
# other values, which is the only mechanism that keeps SP9 from being a promise.
# ---------------------------------------------------------------------------

GEOMETRIES: tuple[str, ...] = (
    "streamer_shot_3d",
    "streamer_field_3d",
    "obn_receiver_3d",
    "cdp_offset_3d",
)
"""One fixture per gather family the amendment names, in the amendment's order.

Streamer shot, streamer field record, OBN receiver, CDP gather. The 2-D fixtures and
``streamer_shot_3d_wrapped`` belong to the same four families and are not additional
geometries; the wrapped one is a measured G2 failure (F6) and could produce no figure
under the precondition in any case.
"""

LATENCY_TARGET_S = 2.0
"""Declared target: at most this, per read pattern, cold cache, on fixtures <= 500 traces."""

REPETITIONS = 5
"""Declared N per (geometry, shape, pattern). The **median** is the reported figure."""

SHAPES: tuple[str, ...] = ("default", "gather_contiguous", "time_slice_contiguous")
"""The declared three: MDIO's default, a gather-contiguous shape, a time-slice-contiguous one."""

PATTERNS: tuple[str, ...] = ("single_gather", "offset_slice", "time_slice", "full_inline")
"""The declared four read patterns."""

GRID_OVERRIDES: dict[str, dict[str, bool]] = {
    "streamer_field_3d": {"auto_shot_wrap": True},
    "obn_receiver_3d": {"calculate_shot_index": True},
}
"""Transcribed from ``test_p7_prestack.py``. Without these the conversion does not happen."""


def candidate_chunk_shape(name: str, n_dims: int) -> tuple[int, ...] | None:
    """The declared chunk shape for one candidate, over an array of ``n_dims`` axes.

    ``-1`` means "the whole axis" and is expanded by the template against the measured
    dimension sizes, so a shape declared here is contiguous by construction rather than
    by a number that happens to match. The last axis is always samples; the axis before
    it is the one traces vary along *within* a gather — channel for a streamer, offset
    for a CDP gather — which is what makes these two shapes the declared opposites:

    * ``gather_contiguous`` — one chunk per gather. Every gather-separating axis pinned
      to 1, the within-gather axis and the samples whole.
    * ``time_slice_contiguous`` — one chunk per sample index. Every spatial axis whole,
      the sample axis pinned to 1.

    Args:
        name: A member of :data:`SHAPES`.
        n_dims: Number of axes on the ``amplitude`` array, samples included.

    Returns:
        The shape to set, or ``None`` for the default, which is not set at all.

    Raises:
        ValueError: If the candidate is not one of the declared three.
    """
    if name == "default":
        return None
    if name == "gather_contiguous":
        return (1,) * (n_dims - 2) + (-1, -1)
    if name == "time_slice_contiguous":
        return (-1,) * (n_dims - 1) + (1,)
    msg = f"undeclared chunk shape candidate {name!r}"
    raise ValueError(msg)


def pattern_index(name: str, n_dims: int) -> tuple[Any, ...]:
    """The declared read pattern as an index expression over ``n_dims`` axes.

    The pattern names are the amendment's and are geometry-neutral; the concrete slice
    each becomes is derived from the store's **own** axis order, read from Zarr metadata,
    never assumed. For a CDP-offset store — ``(inline, crossline, offset, time)`` — the
    four fall out literally: one CDP's gather, one constant-offset section, one time
    slice, one full inline. For a streamer store — ``(shot_point, cable, channel, time)``
    — ``offset_slice`` fixes the channel, which is the streamer's offset axis, and
    ``full_inline`` fixes the outermost spatial axis, which is the sail-line direction.

    Args:
        name: A member of :data:`PATTERNS`.
        n_dims: Number of axes on the ``amplitude`` array, samples included.

    Returns:
        An index tuple.

    Raises:
        ValueError: If the pattern is not one of the declared four.
    """
    whole = slice(None)
    if name == "single_gather":
        return (0,) * (n_dims - 2) + (whole, whole)
    if name == "offset_slice":
        return (whole,) * (n_dims - 2) + (0, whole)
    if name == "time_slice":
        return (whole,) * (n_dims - 1) + (0,)
    if name == "full_inline":
        return (0,) + (whole,) * (n_dims - 1)
    msg = f"undeclared read pattern {name!r}"
    raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class Timing:
    """One (geometry, shape, pattern) measurement: N repetitions, the median reported.

    ``open_and_read`` is the whole wait a consumer sees — opening the store from a path
    and materialising the slice. ``read_only`` excludes the open. Both are kept because
    the open is a fixed floor that does not vary with the chunk shape — measured at
    roughly 0.6 to 0.9 ms on every store in this leg — while the slice varies by more
    than an order of magnitude with it, so reporting them separately keeps the shape's
    contribution visible. The declared target is applied to ``open_and_read``, the larger
    of the two, so keeping both cannot flatter a result.
    """

    geometry: str
    shape: str
    pattern: str
    open_and_read: tuple[float, ...]
    read_only: tuple[float, ...]
    elements: int

    @property
    def median_s(self) -> float:
        """The reported figure: median of N open-and-read repetitions."""
        return statistics.median(self.open_and_read)

    @property
    def median_read_s(self) -> float:
        """Median of N slice-only repetitions."""
        return statistics.median(self.read_only)

    @property
    def meets_target(self) -> bool:
        """Whether the reported figure is inside the declared target."""
        return self.median_s <= LATENCY_TARGET_S


@dataclass(frozen=True, slots=True)
class StoreRun:
    """One geometry converted at one candidate chunk shape, and what came of it.

    ``timings`` is empty **whenever the precondition is unmet**, and that is the whole
    point of the type: there is no code path that produces a latency figure for a store
    whose planes did not all pass, so the rule cannot be forgotten in a later edit.
    """

    geometry: str
    shape: str
    requested: tuple[int, ...] | None
    amplitude_shape: tuple[int, ...]
    amplitude_chunks: tuple[int, ...]
    dimensions: tuple[str, ...]
    store_bytes: int
    chunks_stored: int
    planes: tuple[tuple[int, str, str], ...]
    timings: dict[str, Timing]

    @property
    def planes_all_passed(self) -> bool:
        """The declared correctness precondition, as a single boolean."""
        return len(self.planes) == 5 and all(status == "PASS" for _, status, _ in self.planes)

    @property
    def plane_status(self) -> list[str]:
        """Plane 1 to Plane 5 outcomes, in order."""
        return [status for _, status, _ in self.planes]

    @property
    def chunk_elements(self) -> int:
        """Elements in one chunk buffer, whether or not the array fills it.

        A chunk is decoded whole. When the declared chunk overhangs the array — MDIO's
        defaults overhang these fixtures heavily — the reader still allocates and
        decompresses the full buffer to return the corner that holds data. This is a
        structural property of the store, not a latency figure, so it is recorded for
        every store including the ones the precondition bars a figure for.
        """
        total = 1
        for size in self.amplitude_chunks:
            total *= size
        return total

    @property
    def overhang(self) -> float:
        """Chunk buffer elements per array element. 1.0 when the chunk grid fits."""
        total = 1
        for size in self.amplitude_shape:
            total *= size
        return self.chunk_elements * self.chunks_stored / total


def _directory_bytes(path: Path) -> int:
    """Total size of every file in a store. Content bytes, not allocated blocks."""
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


def _outcome(plane: int, call: Callable[[], PlaneResult]) -> tuple[int, str, str]:
    """Run one plane, recording an exception as an outcome rather than letting it escape.

    ``RAISED`` is not folded into ``FAIL``: a plane that fails has judged the store, a
    plane that raises has not judged it at all, and **``NOT_RUN`` is not a pass**. Both
    occur in this probe, and either one blocks the latency figure identically.
    """
    try:
        result = call()
    except Exception as exc:
        return plane, "RAISED", f"{type(exc).__name__}: {exc}"
    failed = result.evidence.get("failed_checks")
    return plane, result.status, "" if failed is None else str(failed)


def _convert(article: PrestackSegy, store: Path, shape: str) -> tuple[int, ...] | None:
    """Convert one geometry at one candidate chunk shape.

    The chunk shape is set through ``AbstractDatasetTemplate.full_chunk_shape``, a
    documented public property with a public setter, on the **fresh instance**
    ``get_template`` returns — its docstring states that each call returns an independent
    copy that can be modified without affecting the registry. Nothing here reaches into
    an internal, subclasses a template, or patches a module: §3.3 bars all three, and if
    the shape were only reachable that way the correct outcome would be to measure the
    default alone and report the limitation.

    Args:
        article: The generated fixture and its declared spec.
        store: Where to write the MDIO store.
        shape: A member of :data:`SHAPES`.

    Returns:
        The shape that was requested, or ``None`` for the untouched default.
    """
    from mdio import GridOverrides, segy_to_mdio
    from mdio.builder.template_registry import get_template

    template = get_template(article.geometry.template)
    requested = candidate_chunk_shape(shape, len(template.dimension_names))
    if requested is not None:
        template.full_chunk_shape = requested

    overrides = GRID_OVERRIDES.get(article.name)
    raw = read_raw_file_headers(article.path)
    ledger = WarningLedger()
    with recording_warnings(ledger, reemit=False), file_headers_persisted():
        segy_to_mdio(
            segy_spec=article.spec(),
            mdio_template=template,
            input_path=article.path,
            output_path=store,
            overwrite=True,
            grid_overrides=GridOverrides(**overrides) if overrides else None,
        )
    attach_raw_file_headers(store, raw)
    return requested


def _time_pattern(store: Path, geometry: str, shape: str, pattern: str, n_dims: int) -> Timing:
    """Time one read pattern, N repetitions, nothing carried between them.

    Each repetition re-opens the group from the path and re-acquires the array handle, so
    no decoded chunk, buffer or array object survives into the next one. The OS page
    cache is not dropped — see the module docstring for what that does and does not
    license anyone to conclude.
    """
    index = pattern_index(pattern, n_dims)
    open_and_read: list[float] = []
    read_only: list[float] = []
    elements = 0
    for _ in range(REPETITIONS):
        start = time.perf_counter()
        group = zarr.open_group(str(store), mode="r")
        array = group["amplitude"]
        opened = time.perf_counter()
        block = np.asarray(array[index])
        done = time.perf_counter()
        open_and_read.append(done - start)
        read_only.append(done - opened)
        elements = int(block.size)
        del block, array, group
    return Timing(
        geometry=geometry,
        shape=shape,
        pattern=pattern,
        open_and_read=tuple(open_and_read),
        read_only=tuple(read_only),
        elements=elements,
    )


def _run_one(article: PrestackSegy, root: Path, shape: str) -> StoreRun:
    """Convert one geometry at one shape, judge it, and time it only if it is judged sound."""
    store = root / f"{article.name}.{shape}.mdio"
    requested = _convert(article, store, shape)

    spec = article.spec()
    gate = g1(spec.trace.header.fields, dtype=spec.trace.header.dtype)
    planes = (
        _outcome(1, lambda: plane_1(article.path, store)),
        _outcome(2, lambda: plane_2(article.path, store)),
        _outcome(3, lambda: plane_3(article.path, store, spec, g1_passed=gate.passed)),
        _outcome(4, lambda: plane_4(article.path, store, spec)),
        _outcome(5, lambda: plane_5_checker(article.path, store, spec)),
    )

    group = zarr.open_group(str(store), mode="r")
    amplitude = group["amplitude"]
    dimensions = store_dimensions(group, variable="amplitude")
    n_dims = len(amplitude.shape)

    run = StoreRun(
        geometry=article.name,
        shape=shape,
        requested=requested,
        amplitude_shape=tuple(int(x) for x in amplitude.shape),
        amplitude_chunks=tuple(int(x) for x in amplitude.chunks),
        dimensions=dimensions,
        store_bytes=_directory_bytes(store),
        chunks_stored=sum(1 for f in (store / "amplitude" / "c").rglob("*") if f.is_file()),
        planes=planes,
        timings={},
    )
    if not run.planes_all_passed:
        # The declared precondition. A latency figure for a store that fails G2 is
        # meaningless and must not be reported, so it is not produced.
        return run

    timings = {p: _time_pattern(store, article.name, shape, p, n_dims) for p in PATTERNS}
    return StoreRun(
        geometry=run.geometry,
        shape=run.shape,
        requested=run.requested,
        amplitude_shape=run.amplitude_shape,
        amplitude_chunks=run.amplitude_chunks,
        dimensions=run.dimensions,
        store_bytes=run.store_bytes,
        chunks_stored=run.chunks_stored,
        planes=run.planes,
        timings=timings,
    )


@pytest.fixture(scope="module")
def bench(tmp_path_factory: pytest.TempPathFactory) -> dict[tuple[str, str], StoreRun]:
    """The whole latency leg, run once: four geometries times three candidate shapes."""
    assert check_barred_env_vars() == [], (
        "a barred environment variable is set. Every figure below would be worthless: "
        "prestack grids are sparse and MDIO_IGNORE_CHECKS demotes the sparsity error to "
        "a log line (spec 9.1)."
    )
    root = tmp_path_factory.mktemp("p7-latency")
    runs: dict[tuple[str, str], StoreRun] = {}
    for name in GEOMETRIES:
        article = build_fixture(name, root / f"{name}.sgy")
        for shape in SHAPES:
            runs[name, shape] = _run_one(article, root, shape)
    return runs


# ---------------------------------------------------------------------------
# Pre-registration discipline. SP9.
# ---------------------------------------------------------------------------


def test_the_run_used_the_parameters_the_amendment_declared(repo_root):
    """The harness may not hold a target the pre-registration does not.

    Amendment A was committed before any benchmark existed, which is the whole basis on
    which this leg is admissible. That guarantee survives only if the numbers the runner
    uses are the numbers the record carries, so they are read back out of the record
    rather than trusted to agree.
    """
    text = (repo_root / "prereg" / "P7-prestack-chunking.md").read_text(encoding="utf-8")
    amendment = text.split("## Amendment A")[1].split("## Results")[0]
    assert "**≤ 2.0 s per read pattern**" in amendment
    assert "**5** per (geometry, shape, pattern); the **median**" in amendment
    assert "**3 per geometry**" in amendment
    assert "single gather · offset slice · time slice · full inline" in amendment
    assert "All five planes must PASS first" in amendment
    assert LATENCY_TARGET_S == 2.0
    assert REPETITIONS == 5
    assert len(SHAPES) == 3
    assert len(PATTERNS) == 4


def test_the_original_parameter_table_is_still_empty(repo_root):
    """The amendment is an amendment. Appending results may not back-fill the original.

    ``test_p7_prestack.py`` already asserts this; it is asserted again here because this
    is the file that had the motive to edit it.
    """
    text = (repo_root / "prereg" / "P7-prestack-chunking.md").read_text(encoding="utf-8")
    registered = text.split("## Results")[0]
    assert "*declared before the run, minimum 3 per geometry*" in registered
    assert "*declared before the run, per pattern*" in registered
    assert "*declared before the run*" in registered


def test_the_four_geometries_are_the_four_families_the_amendment_names(bench):
    """One fixture per family, and no family measured by a fixture from another one."""
    assert tuple(GEOMETRIES) == (
        "streamer_shot_3d",
        "streamer_field_3d",
        "obn_receiver_3d",
        "cdp_offset_3d",
    )
    assert set(bench) == {(g, s) for g in GEOMETRIES for s in SHAPES}


def test_no_barred_variable_is_set_for_any_of_it(bench):
    """SP11. A benchmark run with MDIO_IGNORE_CHECKS set measures a different store."""
    assert check_barred_env_vars() == []
    assert bench


# ---------------------------------------------------------------------------
# Can the chunk shape be varied at all? The leg's precondition, and a finding.
# ---------------------------------------------------------------------------


def test_sdip_ingest_offers_no_way_to_choose_a_chunk_shape():
    """**The finding that put this benchmark outside ``sdip ingest``**.

    ``ingest()`` takes a template *name* and resolves it internally, so there is no
    object on which a caller could set ``full_chunk_shape`` and no parameter that would
    carry one. Every SDIP store therefore ships whatever shape the template chose, and
    nothing on the certificate records which shape that was — so a store that is
    unusable for its access pattern is indistinguishable from one that is not.
    """
    parameters = inspect.signature(ingest).parameters
    assert "template" in parameters
    assert parameters["template"].annotation == "str"
    assert not [p for p in parameters if "chunk" in p or "shape" in p]


@pytest.mark.parametrize("geometry", GEOMETRIES)
def test_the_chunk_shape_varies_through_the_public_template_property(bench, geometry):
    """The upstream **public** surface does expose it, so the leg is runnable.

    ``AbstractDatasetTemplate.full_chunk_shape`` is a documented property with a public
    setter, and ``get_template`` documents that it hands back an independent copy. Three
    distinct shapes reach three distinct stores without a single private attribute being
    touched. Had that not been true, the honest outcome would have been to measure the
    default alone and say so — §3.3 bars routing around it.
    """
    produced = {bench[geometry, shape].amplitude_chunks for shape in SHAPES}
    assert len(produced) == 3, produced
    for shape in SHAPES:
        run = bench[geometry, shape]
        if run.requested is None:
            continue
        expanded = tuple(
            size if requested == -1 else requested
            for requested, size in zip(run.requested, run.amplitude_shape, strict=True)
        )
        assert run.amplitude_chunks == expanded


@pytest.mark.parametrize("geometry", GEOMETRIES)
def test_the_declared_shapes_are_the_shapes_they_claim_to_be(bench, geometry):
    """A "gather-contiguous" shape that is not contiguous over a gather is mislabelled.

    Names in a results table are load-bearing, so each is checked against the array it
    produced rather than against the tuple that was requested.
    """
    gather = bench[geometry, "gather_contiguous"]
    assert gather.amplitude_chunks[-2:] == gather.amplitude_shape[-2:]
    assert set(gather.amplitude_chunks[:-2]) == {1}

    slab = bench[geometry, "time_slice_contiguous"]
    assert slab.amplitude_chunks[:-1] == slab.amplitude_shape[:-1]
    assert slab.amplitude_chunks[-1] == 1


@pytest.mark.parametrize("geometry", GEOMETRIES)
def test_the_chunk_shape_does_not_change_what_the_store_holds(bench, geometry):
    """Chunking is a layout decision, so it may not move a value.

    If it did, the leg would be measuring two things at once and could attribute neither.
    """
    shapes = {bench[geometry, s].amplitude_shape for s in SHAPES}
    dimensions = {bench[geometry, s].dimensions for s in SHAPES}
    verdicts = {tuple(bench[geometry, s].plane_status) for s in SHAPES}
    assert len(shapes) == 1
    assert len(dimensions) == 1
    assert len(verdicts) == 1, verdicts


# ---------------------------------------------------------------------------
# The correctness precondition. Declared, and enforced rather than promised.
# ---------------------------------------------------------------------------

PRECONDITION: dict[str, bool] = {
    "streamer_shot_3d": True,
    "streamer_field_3d": False,
    "obn_receiver_3d": False,
    "cdp_offset_3d": True,
}
"""Measured 2026-08-23. Which geometries clear the precondition, and which do not.

Transcribed from the run so an upstream change that alters it fails here rather than
quietly widening or narrowing the set of geometries that carry a figure. The two that do
not clear it are F7 from the first P7 run, unchanged: ``streamer_field_3d`` and
``obn_receiver_3d`` size their grid along ``shot_index``, a dimension MDIO calculates and
writes **no coordinate array for**, so Planes 3, 4 and 5 raise rather than guess an
ordering. That is not a chunking problem and no chunk shape reaches it.
"""


@pytest.mark.parametrize("geometry", GEOMETRIES)
@pytest.mark.parametrize("shape", SHAPES)
def test_the_precondition_verdict_is_the_one_that_was_measured(bench, geometry, shape):
    """The precondition is a measurement, so it is pinned like every other measurement."""
    run = bench[geometry, shape]
    assert run.planes_all_passed == PRECONDITION[geometry], run.planes


@pytest.mark.parametrize("geometry", GEOMETRIES)
@pytest.mark.parametrize("shape", SHAPES)
def test_no_figure_exists_for_a_store_whose_planes_did_not_all_pass(bench, geometry, shape):
    """**The declared precondition, enforced**.

    Amendment A: "A latency figure for a store that fails G2 is meaningless and must not
    be reported." Not reporting it is a discipline; not *producing* it is a mechanism,
    and only the mechanism survives a later edit by someone who has not read the
    amendment.
    """
    run = bench[geometry, shape]
    if run.planes_all_passed:
        assert set(run.timings) == set(PATTERNS)
    else:
        assert run.timings == {}


@pytest.mark.parametrize("geometry", [g for g in GEOMETRIES if PRECONDITION[g]])
@pytest.mark.parametrize("shape", SHAPES)
def test_every_reported_figure_is_a_median_of_the_declared_repetitions(bench, geometry, shape):
    """N is 5 and the statistic is the median. Neither is negotiable after the fact."""
    run = bench[geometry, shape]
    for pattern in PATTERNS:
        timing = run.timings[pattern]
        assert len(timing.open_and_read) == REPETITIONS
        assert len(timing.read_only) == REPETITIONS
        assert timing.median_s == statistics.median(timing.open_and_read)
        assert timing.elements > 0, "a read that returned nothing is not a read"


# ---------------------------------------------------------------------------
# The verdict against the declared falsifier.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("geometry", [g for g in GEOMETRIES if PRECONDITION[g]])
def test_at_least_one_shape_meets_the_declared_target_for_the_geometry(bench, geometry):
    """**The falsifier: no chunk shape meeting the declared target for a geometry**.

    Measured 2026-08-23: it does not fire on either geometry that clears the
    precondition. Every candidate shape meets the target on every pattern, by more than
    two orders of magnitude — the expected shape of the result on fixtures under 200
    traces, and exactly why the amendment called 2.0 s deliberately generous. It catches
    a pathological shape; it does not rank good ones.

    This test fails if that stops being true, which is the point of writing it down.
    """
    survivors = [
        shape
        for shape in SHAPES
        if all(bench[geometry, shape].timings[p].meets_target for p in PATTERNS)
    ]
    assert survivors == list(SHAPES), {
        (s, p): bench[geometry, s].timings[p].median_s for s in SHAPES for p in PATTERNS
    }


@pytest.mark.parametrize("geometry", [g for g in GEOMETRIES if not PRECONDITION[g]])
def test_the_falsifier_is_not_evaluable_where_the_precondition_blocks_it(bench, geometry):
    """The other two geometries, and the honest verdict for them.

    No shape meets the target, because no shape has a figure, because the precondition
    the amendment declared forbids one. Reading that as the falsifier firing would credit
    a chunking finding to a coordinate-array finding; reading it as a pass would claim a
    measurement that does not exist. It is **not evaluable**, it is reported as such, and
    the block is clause 1 of the original falsifier — already fired, in the first run.
    """
    for shape in SHAPES:
        run = bench[geometry, shape]
        assert not run.planes_all_passed
        assert run.timings == {}
        raised = [detail for _, status, detail in run.planes if status == "RAISED"]
        assert raised, run.planes
        assert all("UntrustedInputError" in detail for detail in raised), raised


def test_the_slowest_figure_in_the_whole_run_is_far_inside_the_target(bench):
    """One number for the leg: the worst median anywhere, against the declared 2.0 s.

    Stated as its own assertion because the per-geometry verdict above can pass while the
    margin quietly erodes, and the margin is what carries the leg's real conclusion — the
    target discriminates nothing at this fixture size, and the *ordering* below is where
    the finding is.
    """
    medians = [t.median_s for run in bench.values() for t in run.timings.values()]
    assert medians
    assert max(medians) <= LATENCY_TARGET_S
    assert max(medians) < LATENCY_TARGET_S / 10


# ---------------------------------------------------------------------------
# What the shapes actually did. The falsifier is silent here; this is not.
# ---------------------------------------------------------------------------

MATCHED_PATTERN: dict[str, str] = {
    "gather_contiguous": "single_gather",
    "time_slice_contiguous": "time_slice",
}
"""Which declared shape is designed for which declared pattern.

The third candidate — MDIO's default — is designed for neither in particular, which is
what makes it the comparator: it is what a store ships with today, because
``sdip ingest`` offers no way to ask for anything else.
"""


@pytest.mark.parametrize("shape", sorted(MATCHED_PATTERN))
@pytest.mark.parametrize("geometry", [g for g in GEOMETRIES if PRECONDITION[g]])
def test_a_shape_built_for_a_pattern_beats_the_default_on_that_pattern(bench, geometry, shape):
    """**The leg's finding, and it is not a latency-target finding**.

    Both purpose-built shapes beat MDIO's default on the pattern they were built for, on
    both geometries that clear the precondition, in every run recorded on 2026-08-23 — by
    between 1.8x and 10.9x on the medians. Every one of those figures is more than two
    orders of magnitude inside the declared 2.0 s, so the target sees none of it, which
    is the honest reading of this leg: **the pre-registered gate is silent, and the
    ordering underneath it is not.**

    The mechanism is visible in the store rather than inferred. MDIO's default chunk
    overhangs these fixtures by a factor of hundreds, so a reader decodes a whole chunk
    buffer to return the corner of it that holds data; a shape that fits the array
    decodes what it needs. That is a property of the shape against the grid, not of the
    disk, which is why it survives a warm page cache.
    """
    pattern = MATCHED_PATTERN[shape]
    matched = bench[geometry, shape].timings[pattern].median_s
    default = bench[geometry, "default"].timings[pattern].median_s
    assert matched < default, {"matched": matched, "default": default}


@pytest.mark.parametrize("geometry", GEOMETRIES)
def test_mdio_default_chunks_overhang_every_one_of_these_fixtures(bench, geometry):
    """The structural half of the same finding, and it needs no timer.

    A chunk is decoded whole. Every default prestack chunk shape MDIO ships is larger
    than the entire fixture on at least one axis, so the store allocates and decompresses
    buffers that are mostly nothing. This is measured on all four geometries, including
    the two the precondition bars a latency figure for — an overhang is a fact about the
    store, not a claim about how fast it reads.
    """
    default = bench[geometry, "default"]
    fitted = bench[geometry, "gather_contiguous"]
    assert default.overhang > fitted.overhang
    assert default.overhang > 100.0, default.overhang


def test_the_worst_overhang_belongs_to_a_geometry_that_can_carry_no_figure(bench):
    """The uncomfortable arrangement of this leg's two halves, stated once.

    ``obn_receiver_3d`` has by far the most extreme default chunk — F7's finding, and the
    only geometry in the first P7 run whose store came out larger than its SEG-Y. It is
    also one of the two geometries whose planes cannot render a verdict, so under the
    declared precondition **the geometry with the most obviously wrong chunking is the
    one this leg is forbidden to publish a latency figure for.** That is the precondition
    working as declared, not a gap in it: the fix is a coordinate array, not a benchmark.
    """
    worst = max(bench, key=lambda key: bench[key].overhang if key[1] == "default" else -1.0)
    assert worst == ("obn_receiver_3d", "default")
    assert bench[worst].timings == {}
    assert not PRECONDITION["obn_receiver_3d"]


# ---------------------------------------------------------------------------
# What the leg can and cannot say. Written as tests so it cannot rot silently.
# ---------------------------------------------------------------------------


def test_every_fixture_stays_inside_the_pre_registered_trace_budget(bench):
    """<= 500 traces, from the amendment. P7 probes shape, not scale; P3 owns scale."""
    from tests.fixtures.generators.prestack import TRACE_BUDGET, geometry

    assert bench
    for name in GEOMETRIES:
        assert geometry(name).trace_count <= TRACE_BUDGET


def test_the_store_open_is_a_floor_under_every_figure_and_is_not_the_signal(bench):
    """The measurement's own limitation, measured rather than assumed.

    Opening a Zarr group from a path costs the same on every store here regardless of its
    chunking, so it sits under every figure as a floor. It is reported separately from
    the slice for exactly that reason: the declared target is applied to the larger
    quantity — open plus slice — so keeping both cannot flatter a result, while the
    slice-only column is where the chunk shape is visible.

    This asserts the arrangement rather than trusting it: the slice is always a proper
    part of the whole, and the floor never accounts for the spread between shapes.
    """
    for run in bench.values():
        for timing in run.timings.values():
            assert timing.median_read_s < timing.median_s

    for geometry in (g for g in GEOMETRIES if PRECONDITION[g]):
        for pattern in PATTERNS:
            by_shape = [bench[geometry, s].timings[pattern] for s in SHAPES]
            opens = [t.median_s - t.median_read_s for t in by_shape]
            spread = max(t.median_s for t in by_shape) - min(t.median_s for t in by_shape)
            assert max(opens) - min(opens) < spread
