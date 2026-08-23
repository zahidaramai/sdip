"""Probe **P7** — prestack templates and chunking.

Pre-registered in ``prereg/P7-prestack-chunking.md``.

Every measurement banked before this probe used **poststack** geometry: a 2-D inline by
crossline grid, one trace per cell. Prestack is not that. A shot gather is indexed by
shot point, cable and channel; a field record adds sail line and gun; an OBN receiver
gather adds a component; a CDP gather keeps inline and crossline but inserts an offset
axis between them and the samples. Shot gathers, field records and OBN receiver gathers
are **Primary** at v1.0, not deferred.

Two questions, and the first dominates: **does the Equivalence Contract hold on prestack
geometry at all?** Chunking is meaningless if G2 fails.

The order of the legs below is the answer's shape:

1. **Through SDIP's own API, no prestack geometry converts at all.** ``sdip ingest``
   builds its spec from the revision standard and offers no way to declare a field the
   standard does not name — and every prestack template binds at least one such name.
2. **With those names declared, all seven geometries convert**, so the blocker is a
   declaration surface, not the format and not the pinned upstream.
3. **The five planes were, at the time of the run, hardwired to an inline/crossline
   grid** and returned no verdict on any prestack store. That finding was acted on while
   the probe was being written; the tables below therefore carry **both readings** and
   say which engine produced each.
4. **Against the generalised planes, G2 holds on four of the seven geometries and fails
   on the other three** — once as a measured mismatch (a rebased streamer channel index)
   and twice because a grid dimension has no coordinate array to resolve against.
5. G3 round trips byte-identically on all seven, including the geometry that fails G2.
   That is the probe's most uncomfortable number and the reason G3 is not a substitute
   for G2.

A fixture that cannot be ingested is a **result**, not an obstacle, and the tables below
assert the outcome that was *measured* — the refusals included — so an upstream change
that silently alters any of them fails here rather than passing unnoticed.

``MDIO_IGNORE_CHECKS`` is **absent throughout**, asserted before anything is built.
Prestack grids are sparse and it is exactly the variable that would make this probe look
tidier than it is.

Comparison is exact everywhere. No tolerance appears in this file and none may be added.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import zarr
from segy import SegyFile
from segy.standards import get_segy_standard

from sdip.equivalence import PlaneResult, build_trace_map, plane_1, plane_2, plane_3, plane_4
from sdip.equivalence import plane_5 as plane_5_checker
from sdip.export import RoundTripResult, export
from sdip.guard.env import check_barred_env_vars
from sdip.guard.warn import WarningLedger, recording_warnings
from sdip.ingest import (
    attach_raw_file_headers,
    file_headers_persisted,
    ingest,
    read_raw_file_headers,
)
from sdip.spec.gate import G1Result, g1
from tests.fixtures.generators.prestack import (
    GEOMETRY_NAMES,
    TRACE_BUDGET,
    PrestackGeometry,
    PrestackSegy,
    build_fixture,
)

pytestmark = pytest.mark.integration

PREREGISTERED: tuple[str, ...] = (
    "streamer_shot_3d",
    "streamer_shot_3d_wrapped",
    "streamer_shot_2d",
    "streamer_field_3d",
    "obn_receiver_3d",
    "cdp_offset_3d",
    "cdp_offset_2d",
)
"""The geometry table from the generator, transcribed. Changing it after seeing a result
would break **SP9**, so a test pins it against the generator's own table."""

GRID_OVERRIDES: dict[str, dict[str, bool]] = {
    "streamer_shot_3d_wrapped": {"auto_channel_wrap": True},
    "streamer_field_3d": {"auto_shot_wrap": True},
    "obn_receiver_3d": {"calculate_shot_index": True},
}
"""Three geometries additionally need an MDIO grid override to convert at all.

``sdip.ingest.ingest`` has no parameter for these, so they are a second, independent
reason the SDIP API cannot reach prestack data — and unlike the missing field names,
this one changes what the store *contains*, not just whether it can be written.
"""


@dataclass(frozen=True, slots=True)
class PlaneOutcome:
    """One plane's outcome, including the case where it could not produce one.

    ``RAISED`` is deliberately not folded into ``FAIL``. A plane that fails has judged
    the store and found it wanting; a plane that raises has not judged it at all, and
    **``NOT_RUN`` is not a pass**. Both outcomes occur in this probe, on different
    geometries and for different reasons, and collapsing them would lose the difference
    between "the store is wrong" and "the store cannot be checked".
    """

    plane: int
    gate: str
    status: str
    detail: str


@dataclass(frozen=True, slots=True)
class GeometryRun:
    """One geometry carried as far as it goes, through both legs of the probe."""

    name: str
    article: PrestackSegy
    spec: Any
    g1: G1Result
    sdip_error: str
    store: Path
    ingested: bool
    upstream_error: str | None
    planes: tuple[PlaneOutcome, ...]
    roundtrip: RoundTripResult | None
    amplitude_shape: tuple[int, ...]
    amplitude_chunks: tuple[int, ...]
    header_chunks: tuple[int, ...]
    store_bytes: int
    arrays: tuple[str, ...]

    @property
    def geometry(self) -> PrestackGeometry:
        """The geometry descriptor."""
        return self.article.geometry

    @property
    def plane_status(self) -> list[str]:
        """Plane 1 to Plane 5 outcomes, in order."""
        return [p.status for p in self.planes]

    def plane(self, number: int) -> PlaneOutcome:
        """One plane's outcome by number."""
        return next(p for p in self.planes if p.plane == number)

    def group(self) -> Any:
        """The store, opened read-only with stock zarr."""
        return zarr.open_group(str(self.store), mode="r")

    def mask(self) -> np.ndarray:
        """The live/dead mask as booleans."""
        return np.asarray(self.group()["trace_mask"][:]).astype(bool)

    def source_headers(self) -> Any:
        """Source trace headers, read with the geometry's declared spec."""
        return SegyFile(str(self.article.path), spec=self.spec).header[:]

    def source_samples(self) -> Any:
        """Source trace samples, read with the geometry's declared spec."""
        return SegyFile(str(self.article.path), spec=self.spec).sample[:]


def _directory_bytes(path: Path) -> int:
    """Total size of every file in a store. Content bytes, not allocated blocks."""
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


def _outcome(plane: int, gate: str, call: Callable[[], PlaneResult]) -> PlaneOutcome:
    """Run one plane, recording an exception as an outcome rather than letting it escape.

    The broad ``except`` is the pre-registered method. A plane that cannot render a
    verdict on a geometry is a measurement in its own right, and abandoning the probe on
    the first one would lose the other six.
    """
    try:
        result = call()
    except Exception as exc:
        return PlaneOutcome(plane, gate, "RAISED", f"{type(exc).__name__}: {exc}")
    failed = result.evidence.get("failed_checks")
    return PlaneOutcome(plane, gate, result.status, "" if failed is None else str(failed))


def _sdip_leg(article: PrestackSegy, store: Path) -> str:
    """Leg 1: try the geometry through ``sdip.ingest.ingest``, and record what happens.

    Returns:
        The error text, or ``""`` if the ingest unexpectedly succeeded.
    """
    try:
        ingest(article.path, store, template=article.template)
    except Exception as exc:
        return f"{type(exc).__name__}: {exc}"
    return ""


def _upstream_leg(article: PrestackSegy, store: Path) -> tuple[bool, str | None]:
    """Leg 2: the same conversion with the geometry's index fields declared.

    This runs SDIP's ingest sequence — persist the file headers, convert through the
    pinned public API, attach SDIP's authoritative raw textual and binary headers — with
    one difference and one addition: the spec carries the geometry's index-field
    declarations, and a grid override is passed where the template needs one.

    **It is not a substitute for ``sdip ingest`` and no result below is reported as one.**
    It exists to separate two questions that leg 1 answers together: *can SDIP convert
    prestack data* (no) and *can the pinned upstream convert it* (yes). Without leg 2
    the probe could not tell a declaration gap from a format limitation.

    Returns:
        Whether the conversion succeeded, and the error text if it did not.
    """
    geom = article.geometry
    overrides = GRID_OVERRIDES.get(geom.name)
    raw = read_raw_file_headers(article.path)
    ledger = WarningLedger()
    try:
        with recording_warnings(ledger, reemit=False), file_headers_persisted():
            from mdio import GridOverrides, segy_to_mdio
            from mdio.builder.template_registry import get_template

            segy_to_mdio(
                segy_spec=article.spec(),
                mdio_template=get_template(geom.template),
                input_path=article.path,
                output_path=store,
                overwrite=True,
                grid_overrides=GridOverrides(**overrides) if overrides else None,
            )
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"
    attach_raw_file_headers(store, raw)
    return True, None


def _run(name: str, root: Path) -> GeometryRun:
    """Carry one geometry through both legs, five planes, and the round trip."""
    article = build_fixture(name, root / f"{name}.sgy")
    spec = article.spec()
    gate = g1(spec.trace.header.fields, dtype=spec.trace.header.dtype)

    sdip_error = _sdip_leg(article, root / f"{name}.sdip.mdio")

    store = root / f"{name}.mdio"
    ingested, upstream_error = _upstream_leg(article, store)
    if not ingested:
        return GeometryRun(
            name=name,
            article=article,
            spec=spec,
            g1=gate,
            sdip_error=sdip_error,
            store=store,
            ingested=False,
            upstream_error=upstream_error,
            planes=(),
            roundtrip=None,
            amplitude_shape=(),
            amplitude_chunks=(),
            header_chunks=(),
            store_bytes=0,
            arrays=(),
        )

    planes = (
        _outcome(1, "G2a", lambda: plane_1(article.path, store)),
        _outcome(2, "G2b", lambda: plane_2(article.path, store)),
        _outcome(3, "G2c", lambda: plane_3(article.path, store, spec, g1_passed=gate.passed)),
        _outcome(4, "G2d", lambda: plane_4(article.path, store, spec)),
        _outcome(5, "G2e", lambda: plane_5_checker(article.path, store, spec)),
    )
    roundtrip = export(store, root / f"{name}.back.sgy", spec, source=article.path)

    group = zarr.open_group(str(store), mode="r")
    amplitude, headers = group["amplitude"], group["headers"]
    return GeometryRun(
        name=name,
        article=article,
        spec=spec,
        g1=gate,
        sdip_error=sdip_error,
        store=store,
        ingested=True,
        upstream_error=None,
        planes=planes,
        roundtrip=roundtrip,
        amplitude_shape=tuple(int(x) for x in amplitude.shape),
        amplitude_chunks=tuple(int(x) for x in amplitude.chunks),
        header_chunks=tuple(int(x) for x in headers.chunks),
        store_bytes=_directory_bytes(store),
        arrays=tuple(sorted(group.array_keys())),
    )


@pytest.fixture(scope="module")
def probe(tmp_path_factory) -> dict[str, GeometryRun]:
    """The whole probe, run once. Conversion is the slow part; the assertions are not."""
    assert check_barred_env_vars() == [], (
        "a barred environment variable is set. Every result below would be worthless: "
        "prestack grids are sparse and MDIO_IGNORE_CHECKS demotes the sparsity error to "
        "a log line (spec 9.1)."
    )
    root = tmp_path_factory.mktemp("p7")
    return {name: _run(name, root) for name in PREREGISTERED}


# ---------------------------------------------------------------------------
# Pre-registration discipline
# ---------------------------------------------------------------------------


def test_the_generator_table_is_the_pre_registered_table():
    """SP9. The geometries were fixed before the run and may not be edited to suit it."""
    assert GEOMETRY_NAMES == PREREGISTERED


def test_the_pre_registration_latency_parameters_were_never_back_filled(repo_root):
    """SP9, enforced rather than promised.

    The pre-registration leaves the candidate chunk shapes, the read-pattern latency
    target and N unfilled, with a note saying the PR that authorises the run fills them
    and merges first. That PR does not exist, so **the latency leg cannot be run** — a
    threshold invented after seeing a chunk shape is not a threshold.

    This test reads the parameter table and fails if anyone fills it in later, which is
    the only way the record stays honest once results are appended below it.
    """
    text = (repo_root / "prereg" / "P7-prestack-chunking.md").read_text(encoding="utf-8")
    registered = text.split("## Results")[0]
    assert "*declared before the run, minimum 3 per geometry*" in registered
    assert "*declared before the run, per pattern*" in registered
    assert "*declared before the run*" in registered


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
    """N <= 500 per fixture. P7 probes shape, not scale; P3 owns scale."""
    article = build_fixture(name, tmp_path / f"{name}.sgy")
    assert article.trace_count <= TRACE_BUDGET


@pytest.mark.parametrize("name", PREREGISTERED)
def test_declaring_the_index_fields_leaves_the_spec_gap_free(probe, name):
    """G1 still passes after customisation, which is what makes leg 2 admissible.

    ``HeaderSpec.customize`` removes any standard field the new declaration overlaps, so
    a field displaced is a field replaced and never a byte dropped. If that were not
    true the declared spec would leave header bytes uncovered, Plane 3 would be
    unsupportable on it, and leg 2 would be measuring something other than SDIP's
    contract.
    """
    run = probe[name]
    assert run.g1.status == "PASS", run.g1.summary()
    assert run.g1.coverage is not None
    assert not run.g1.coverage.uncovered
    assert not run.g1.coverage.overlaps


def test_no_barred_variable_is_set_for_any_of_it(probe):
    """SP11. Also checks no conversion failed *because* SDIP refused a barred variable."""
    assert check_barred_env_vars() == []
    for run in probe.values():
        assert "barred environment variable" not in run.sdip_error
        assert "barred environment variable" not in (run.upstream_error or "")


# ---------------------------------------------------------------------------
# Leg 1 — the SDIP API cannot reach any prestack geometry
# ---------------------------------------------------------------------------

SDIP_INGEST_ERRORS: dict[str, str] = {
    "streamer_shot_3d": "Required fields ['cable', 'channel', 'gun']",
    "streamer_shot_3d_wrapped": "Required fields ['cable', 'channel', 'gun']",
    "streamer_shot_2d": "Required fields ['channel']",
    "streamer_field_3d": "Required fields ['cable', 'channel', 'gun', 'sail_line']",
    "obn_receiver_3d": "Required fields ['gun', 'receiver', 'shot_line']",
    "cdp_offset_3d": "Required fields ['offset']",
    "cdp_offset_2d": "Required fields ['cdp', 'offset']",
}
"""Measured on 2026-08-22 against ``multidimio==1.2.1`` / ``segy==0.6.0``.

Every prestack template MDIO ships binds at least one field the SEG-Y rev 1 standard
does not name. ``sdip.ingest.ingest`` builds its spec from the revision standard and
exposes no way to add a name, so **the refusal is total**: seven geometries, seven
refusals, four gather families.
"""


@pytest.mark.parametrize("name", PREREGISTERED)
def test_no_prestack_geometry_can_be_ingested_through_the_sdip_api(probe, name):
    """**The headline result of leg 1.** Nothing prestack converts through ``sdip ingest``.

    The error names exactly what is missing, and what is missing is always a *name*:
    ``cable``, ``channel``, ``gun``, ``sail_line``, ``receiver``, ``shot_line``,
    ``offset``, ``cdp``. None of these is a SEG-Y rev 1 field name. The conversion is
    refused before a single trace is read and nothing is left behind.
    """
    run = probe[name]
    assert SDIP_INGEST_ERRORS[name] in run.sdip_error
    assert run.article.template in run.sdip_error
    assert "not found in the provided segy_spec" in run.sdip_error
    assert not (run.store.parent / f"{name}.sdip.mdio").exists(), (
        "a refused ingest must leave nothing behind"
    )


def test_for_the_cdp_geometries_the_missing_field_is_a_name_not_a_byte(probe):
    """The narrowest form of the blocker, and the one worth stating precisely.

    ``offset`` and ``cdp`` are not absent from SEG-Y rev 1. They are present, at the
    bytes the industry agrees on, under the names the standard chose: byte 37 is
    ``source_to_receiver_distance`` — which *is* offset — and byte 21 is
    ``ensemble_num`` — which *is* the CDP. Same bytes, same width, same meaning.

    So for these two geometries nothing about the data, the format or the pinned
    upstream stands in the way. A template binds by name, the standard uses a different
    name, and SDIP has no way to say they are the same bytes.
    """
    standard = {f.name: (f.byte, f.format) for f in get_segy_standard(1).trace.header.fields}
    declared = {
        f.name: (f.byte, f.fmt)
        for run in (probe["cdp_offset_3d"], probe["cdp_offset_2d"])
        for f in run.geometry.index_fields
    }
    assert declared["offset"] == standard["source_to_receiver_distance"]
    assert declared["cdp"] == standard["ensemble_num"]
    assert {"offset", "cdp"}.isdisjoint(standard)


@pytest.mark.parametrize("name", sorted(GRID_OVERRIDES))
def test_three_geometries_also_need_a_grid_override_sdip_cannot_pass(probe, name):
    """A second, independent blocker, and a heavier one than the missing names.

    ``segy_to_mdio`` takes ``grid_overrides``; ``sdip.ingest.ingest`` does not forward
    one and has no parameter for it. Two of these three geometries cannot produce their
    grid without it at all — the shot-index dimension the template declares is
    *calculated*, and the calculation only runs when the override asks for it.

    Declaring the missing field names would therefore not be enough on its own. That
    matters for how the gap gets closed: a spec-declaration parameter fixes four of the
    seven geometries and leaves three still unreachable.
    """
    run = probe[name]
    assert name in GRID_OVERRIDES
    assert run.ingested, run.upstream_error


def test_a_calculated_dimension_is_simply_absent_without_its_override(tmp_path):
    """The control for the override finding: same file, same spec, override withheld.

    ``StreamerFieldRecords3D`` declares ``shot_index`` as a calculated dimension, and
    without ``auto_shot_wrap`` no strategy produces it. The conversion stops with a
    named error rather than quietly writing a grid missing an axis, which is the right
    behaviour and is worth pinning as such.
    """
    article = build_fixture("streamer_field_3d", tmp_path / "field.sgy")
    ledger = WarningLedger()
    with pytest.raises(ValueError, match="shot_index") as raised:
        with recording_warnings(ledger, reemit=False), file_headers_persisted():
            from mdio import segy_to_mdio
            from mdio.builder.template_registry import get_template

            segy_to_mdio(
                segy_spec=article.spec(),
                mdio_template=get_template(article.template),
                input_path=article.path,
                output_path=tmp_path / "field.mdio",
                overwrite=True,
            )
    assert "Required computed fields ['shot_index']" in str(raised.value)


# ---------------------------------------------------------------------------
# Leg 2 — every geometry converts once its index fields are declared
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", PREREGISTERED)
def test_every_geometry_converts_once_its_index_fields_are_declared(probe, name):
    """Seven for seven. The blocker in leg 1 is a declaration surface, nothing deeper.

    That is the useful half of the bad news: the pinned upstream converts all four
    gather families, so closing the gap is a matter of letting a caller declare where
    its index headers live — not of forking, bumping a pin, or marking prestack
    unsupported.
    """
    run = probe[name]
    assert run.ingested, run.upstream_error
    assert run.store.exists()


# ---------------------------------------------------------------------------
# The correctness question — G2 on prestack geometry
# ---------------------------------------------------------------------------

PLANE_OUTCOMES: dict[str, tuple[str, ...]] = {
    "streamer_shot_3d": ("PASS", "PASS", "PASS", "FAIL", "PASS"),
    "streamer_shot_3d_wrapped": ("PASS", "PASS", "FAIL", "FAIL", "FAIL"),
    "streamer_shot_2d": ("PASS", "PASS", "PASS", "FAIL", "PASS"),
    "streamer_field_3d": ("PASS", "PASS", "RAISED", "RAISED", "RAISED"),
    "obn_receiver_3d": ("PASS", "PASS", "RAISED", "RAISED", "RAISED"),
    "cdp_offset_3d": ("PASS", "PASS", "PASS", "FAIL", "PASS"),
    "cdp_offset_2d": ("PASS", "PASS", "PASS", "FAIL", "PASS"),
}
"""Planes 1 and 2 in the first two columns, then 3, 4 and 5.

**Third reading, 2026-08-23 (D-0061).** Plane 4 moved from ``PASS`` to ``FAIL`` on the
four geometries that previously passed, and **the stores did not change — the engine got
stricter.** Plane 4 now requires the undecoded ``amplitude_raw_ibm32`` view to EXIST when
the source's sample format is one whose decode to ``float32`` can lose the value. These
fixtures are ``ibm32``, and P2 measured that decode as **not invertible**: 1,939 of 4,103
words lose the value.

**These stores are built by upstream ``segy_to_mdio`` directly**, not by
``sdip.ingest.ingest`` — SDIP's ingest cannot express these geometries at all (**D25**,
it does not forward ``grid_overrides``). So they carry SDIP's raw file-header attributes
but none of its sample-level mitigations, and an ``ibm32`` store with no raw view has
source bits that are **not recoverable from the output at all**.

**The new FAIL is the correct answer, not a regression.** It says something true that the
old ``PASS`` did not: these stores are evaluable, their decoded samples match, and their
original bits are gone. The prior reading is preserved below rather than overwritten.

*Second reading*, 2026-08-22 — Plane 4 ``PASS`` on those four. Correct against an engine
that treated an absent raw array as "not checked" instead of "missing" (D-0061 measured
the consequence: deleting one CHUNK failed the plane, deleting the WHOLE ARRAY passed).

**The probe was run twice against two different engines, and both readings matter.**

*First reading*, against ``planes.py`` as of ``484e7fa``: **no geometry produced a G2
verdict at all**. Planes 3, 4 and 5 each called ``build_trace_map`` with a hard-coded
``{"inline": ..., "crossline": ...}``, so on six of the seven stores the lookup raised
``KeyError: 'inline'`` before any comparison happened, and on the seventh
(``cdp_offset_3d``, the only prestack store that keeps an inline and a crossline axis) it
succeeded and then built a **2-D map over a 4-D grid** — every offset in a bin claiming
one cell, Plane 5 returning `FAIL` and Planes 3 and 4 dying on the index. That is a
`FAIL` on data now known to be bit-exact: a false negative produced by the checker.

*Second reading*, after ``store_dimensions`` landed and the three call sites began
reading the grid dimensions from the store: the table above. Four geometries now pass all
five planes. The remaining two failure modes are **not** artefacts of the checker and did
not go away with it — see the two tests below.
"""


@pytest.mark.parametrize("name", PREREGISTERED)
def test_planes_1_and_2_pass_on_every_prestack_store(probe, name):
    """G2a and G2b are geometry-independent, and measurably so.

    Both compare raw file-header bytes between the source and the store. Nothing about
    a gather layout touches the 3200-byte textual header or the 400-byte binary header,
    and the measurement confirms it rather than assuming it.
    """
    run = probe[name]
    assert run.plane(1).status == "PASS"
    assert run.plane(2).status == "PASS"


@pytest.mark.parametrize("name", PREREGISTERED)
def test_the_plane_outcomes_are_the_ones_that_were_measured(probe, name):
    """The banked table. An upstream or engine change that alters any cell fails here."""
    assert tuple(probe[name].plane_status) == PLANE_OUTCOMES[name]


FULLY_INDEXED: tuple[str, ...] = (
    "streamer_shot_3d",
    "streamer_shot_2d",
    "cdp_offset_3d",
    "cdp_offset_2d",
)
"""Geometries whose every grid dimension is a value present in a source trace header.

Exactly the geometries on which G2 can hold, and — measurably — exactly those on which
it does. The three that are absent are absent for two different reasons, one per test
below.
"""


@pytest.mark.parametrize("name", FULLY_INDEXED)
def test_g2_holds_on_a_prestack_store_whose_grid_the_source_can_address(probe, name):
    """Every plane is EVALUABLE on all four gather layouts the source fully indexes.

    A streamer shot store indexed by ``(shot_point, cable, channel)``, a 2-D shot store,
    a 4-D CDP-offset store and a 2-D CDP-offset store are all judged by every plane —
    none raises, none declines. Plane 4 compares samples with ``np.array_equal``; Plane 3
    compares every declared header field in both directions; Plane 5 confirms the map is
    complete and invertible and that the live mask matches it.

    **Planes 1, 2, 3 and 5 PASS. Plane 4 FAILS, for a reason that is about these stores
    and not about prestack** — see :data:`PLANE_OUTCOMES`. They are built by upstream
    ``segy_to_mdio`` (SDIP's ingest cannot express these geometries, **D25**), so an
    ``ibm32`` source arrives with no undecoded parallel view and its original bits are
    unrecoverable. Plane 4 now says so instead of passing (**D-0061**).

    So the Equivalence Contract **is** evaluable on prestack geometry, and G2c/G2e hold
    exactly. Nothing about a gather layout is inherently unverifiable, which makes the
    failures here specific findings rather than a general limitation.
    """
    run = probe[name]
    assert run.plane_status == list(PLANE_OUTCOMES[name])
    assert [p.gate for p in run.planes] == ["G2a", "G2b", "G2c", "G2d", "G2e"]
    # the point of this test: every plane produced a verdict, none declined
    assert "RAISED" not in run.plane_status
    # and the failure is exactly the missing raw view, not a sample mismatch
    plane_4 = run.planes[3]
    assert plane_4.status == "FAIL"


def test_a_type_b_streamer_store_is_a_measured_g2_failure(probe):
    """**The falsifier's first clause, fired as a measured failure.** Spec §4.6.

    ``streamer_shot_3d_wrapped`` numbers channels 1-16 on cable 1 and 17-32 on cable 2 —
    ordinary sequential streamer numbering, what MDIO calls Type B. With
    ``auto_channel_wrap`` its ``ChannelWrappingStrategy`` **rebases every cable to 1-N**,
    so the store's ``channel`` dimension coordinate runs 1-16 and cable 2's channel 17 is
    filed under the label 5.

    Planes 3, 4 and 5 all fail, and Plane 5 names the reason precisely: the map from
    source ordinal to grid cell is **not complete** (64 of 128 traces have a channel
    number that appears nowhere on the store's channel axis), **not invertible**, and the
    live mask does not match it.

    This is not a checker artefact and it did not go away when the planes were
    generalised. It is a real property of the store: an index was rewritten during
    conversion, the certificate's ``transforms_declared[]`` names only the sample-format
    decode, and under **SP1** the permitted transform is the declared one.

    The uncomfortable part is in the last assertion. **G3 passes byte-identically on this
    store**, because the export reads the ``headers`` array — which still holds the
    original 1-32. A round trip proves the bytes survived; it says nothing about whether
    the index a consumer reads means what it says.
    """
    run = probe["streamer_shot_3d_wrapped"]
    assert [run.plane(n).status for n in (3, 4, 5)] == ["FAIL"] * 3
    assert run.plane(5).detail == "['map_complete', 'map_invertible', 'mask_matches_map']"

    assert run.roundtrip is not None
    assert run.roundtrip.status == "PASS", "byte-identical, and still a G2 failure"


@pytest.mark.parametrize("name", sorted(set(GRID_OVERRIDES) - {"streamer_shot_3d_wrapped"}))
def test_a_dimension_with_no_coordinate_array_leaves_g2_unevaluable(probe, name):
    """The second failure mode: not a mismatch, an inability to judge. Spec §4.6.

    ``StreamerFieldRecords3D`` and ``ObnReceiverGathers3D`` size their grid along
    ``shot_index``, a dimension MDIO **calculates** — and for which it writes **no
    coordinate array at all**. The store declares the dimension in its Zarr metadata and
    then names none of its positions.

    A per-trace plane cannot proceed from that. Locating a source trace in the grid means
    resolving each of its index-header values against that dimension's coordinates, and
    there are none to resolve against. All three planes raise ``UntrustedInputError``
    naming the missing array rather than guessing an ordering.

    **`NOT_RUN` is not a pass**, so G2 is not established for either geometry — the same
    falsifier clause as the test above, reached the other way. The fix is not in the
    engine: it is that a grid axis with no coordinate is not addressable, by SDIP or by
    any other consumer.
    """
    run = probe[name]
    for number in (3, 4, 5):
        outcome = run.plane(number)
        assert outcome.status == "RAISED"
        assert outcome.detail.startswith("UntrustedInputError")
        assert "shot_index" in outcome.detail


# ---------------------------------------------------------------------------
# What the data itself did — measured directly, independently of the engine
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", FULLY_INDEXED)
def test_the_measured_values_are_bit_exact_independently_of_the_planes(probe, name):
    """The same claim as G2c and G2d, reached without going through the checkers.

    This comparison was written when Planes 3 and 4 could not run on a prestack store at
    all, to answer the question the probe could not otherwise answer: **is prestack a
    data problem or a checker problem?** It is kept now that the planes do run, because
    a checker and its subject agreeing is worth more when the agreement was not
    engineered — this builds the map itself, from the store's own dimension coordinates,
    and compares every trace directly.

    Every trace maps to exactly one cell, the map inverts, every declared header field
    matches, every sample matches, and the live mask marks exactly the mapped cells. The
    values were never in question; **D4 stays a coverage debt and does not escalate to a
    correctness debt.**

    Comparison is ``np.array_equal`` throughout. No tolerance.
    """
    run = probe[name]
    group = run.group()
    headers = run.source_headers()
    samples = run.source_samples()
    dimensions = run.geometry.store_dimensions

    trace_map = build_trace_map(
        headers,
        {name_: np.asarray(group[name_][:]) for name_ in dimensions},
        dimensions=dimensions,
    )
    assert trace_map.invertible
    assert not trace_map.unmapped
    assert len(trace_map.ordinal_to_cell) == run.article.trace_count

    volume = np.asarray(group["amplitude"][:])
    stored = group["headers"][:]
    field_names = tuple(headers.dtype.names or ())
    assert set(field_names) <= set(stored.dtype.names or ())

    for ordinal, cell in trace_map.ordinal_to_cell.items():
        assert np.array_equal(np.asarray(samples[ordinal]), np.asarray(volume[cell]))
        for field_name in field_names:
            assert np.array_equal(headers[field_name][ordinal], stored[field_name][cell])

    mask = run.mask()
    live = {tuple(int(i) for i in idx) for idx in zip(*np.nonzero(mask), strict=True)}
    assert live == trace_map.cells()


def test_a_type_b_streamer_store_cannot_be_mapped_from_its_source_at_all(probe):
    """The mechanism behind that G2 failure, isolated and measured directly.

    The planes report it; this shows exactly what they are reporting, without going
    through them.

    ``streamer_shot_3d_wrapped`` numbers channels 1-16 on cable 1 and 17-32 on cable 2,
    which is ordinary sequential streamer numbering and what MDIO calls Type B. With
    ``auto_channel_wrap``, ``ChannelWrappingStrategy`` rebases every cable to 1-N, so the
    store's ``channel`` **dimension coordinate** runs 1-16 and cable 2's channel 17 is
    filed under the label 5.

    Consequences, measured:

    * The stored ``headers`` array keeps the original 17-32, so no measured value is
      lost and the round trip is byte-identical.
    * The map from source ordinal to grid cell, built from source header values, locates
      **64 of 128 traces**. The other 64 have channel numbers that appear nowhere on the
      store's channel axis. §4.6 requires that map complete and invertible; it is
      neither.
    * ``channel`` in the store is therefore a **derived index that appears nowhere in
      the source**, while the certificate's ``transforms_declared[]`` names only the
      sample-format decode. Under **SP1** the permitted transform is the declared one.

    The reason this is a finding and not a curiosity: **G3 passes byte-identically on
    this store.** A round trip proves the bytes survived; it says nothing about whether
    the index a consumer reads means what it says.
    """
    run = probe["streamer_shot_3d_wrapped"]
    group = run.group()
    headers = run.source_headers()

    assert np.array_equal(np.unique(headers["channel"]), np.arange(1, 33))
    assert np.array_equal(np.asarray(group["channel"][:]), np.arange(1, 17))
    assert np.array_equal(np.unique(np.asarray(group["headers"][:]["channel"])), np.arange(1, 33))

    trace_map = build_trace_map(
        headers,
        {name: np.asarray(group[name][:]) for name in run.geometry.store_dimensions},
        dimensions=run.geometry.store_dimensions,
    )
    assert not trace_map.invertible
    assert len(trace_map.ordinal_to_cell) == 64
    assert len(trace_map.unmapped) == 64

    assert run.roundtrip is not None
    assert run.roundtrip.status == "PASS", "byte-identical, and still not faithfully indexed"


def test_without_the_wrap_override_the_same_file_becomes_a_half_padded_grid(tmp_path):
    """The control for the Type B finding. Same file, override withheld, other failure.

    Left alone, sequential channel numbering produces a 4 x 2 x 32 grid in which each
    cable occupies half the channel axis: 128 live cells and 128 invented ones, a
    sparsity ratio of 2.0. The map inverts because no index was rewritten, and the
    padding is exactly the fabrication **SP12** names — announced by the mask, not by
    the values.

    So the choice on a Type B streamer is between a store whose index is rewritten and a
    store that is half padding. Neither is wrong; both need declaring, and SDIP can
    currently express neither.
    """
    article = build_fixture("streamer_shot_3d_wrapped", tmp_path / "wrapped.sgy")
    store = tmp_path / "wrapped.mdio"
    ledger = WarningLedger()
    with recording_warnings(ledger, reemit=False), file_headers_persisted():
        from mdio import segy_to_mdio
        from mdio.builder.template_registry import get_template

        segy_to_mdio(
            segy_spec=article.spec(),
            mdio_template=get_template(article.template),
            input_path=article.path,
            output_path=store,
            overwrite=True,
        )

    group = zarr.open_group(str(store), mode="r")
    assert tuple(int(x) for x in group["amplitude"].shape) == (4, 2, 32, 32)
    assert np.array_equal(np.asarray(group["channel"][:]), np.arange(1, 33))

    mask = np.asarray(group["trace_mask"][:]).astype(bool)
    assert int(mask.sum()) == 128
    assert mask.size == 256

    headers = SegyFile(str(article.path), spec=article.spec()).header[:]
    trace_map = build_trace_map(
        headers,
        {name: np.asarray(group[name][:]) for name in article.geometry.store_dimensions},
        dimensions=article.geometry.store_dimensions,
    )
    assert trace_map.invertible
    assert len(trace_map.ordinal_to_cell) == 128


FABRICATED_DIMENSIONS: dict[str, tuple[str, ...]] = {
    "streamer_field_3d": ("shot_index",),
    "obn_receiver_3d": ("component", "shot_index"),
}
"""Store grid dimensions that exist in no source trace header. Measured 2026-08-22."""


@pytest.mark.parametrize("name", sorted(FABRICATED_DIMENSIONS))
def test_two_geometries_have_a_grid_axis_that_is_in_no_source_header(probe, name):
    """Why these two are absent from :data:`MAPPABLE`, stated as the finding it is.

    ``shot_index`` is *derived*: MDIO computes it from ``shot_point`` per line, so it
    carries source information under a new name and a new numbering. ``component`` is
    *fabricated*: the OBN template requires it, the source has no such header, and MDIO
    fills a constant 1 for every trace and says so in a log line.

    Both make the §4.6 map unbuildable from the source alone — a grid axis the source
    cannot address is an axis no source ordinal can be located along — and both are
    undeclared transforms under **SP1**. ``shot_index`` is additionally a dimension with
    **no coordinate array at all**: it sizes the grid and names nothing, so the only
    record of which shot a slice belongs to is the ``headers`` array.
    """
    run = probe[name]
    present = set(run.source_headers().dtype.names or ())
    fabricated = tuple(d for d in run.geometry.store_dimensions if d not in present)
    assert fabricated == FABRICATED_DIMENSIONS[name]
    assert "shot_index" not in run.arrays, "a grid dimension with no coordinate array"
    assert set(run.geometry.store_dimensions) - {"shot_index"} <= set(run.arrays)


# ---------------------------------------------------------------------------
# G3 — the round trip, which passes everywhere
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", PREREGISTERED)
def test_g3_round_trips_byte_identically_on_every_geometry(probe, name):
    """``sha256(export) == sha256(source)``, whole file, all seven geometries.

    Read together with the plane results this is the probe's most uncomfortable number.
    Every byte of every source file comes back — including the original channel numbers
    on the Type B store, and every one of the 240 header bytes on all seven — while
    three of the five planes never render a verdict on any of them.

    G3 is a strong statement about the export path and a **weak** one about the store: it
    would pass on a store whose dimension coordinates were nonsense, because the export
    reads the headers array. It is not a substitute for G2 and nothing here should be
    read as one.
    """
    run = probe[name]
    assert run.roundtrip is not None
    assert run.roundtrip.status == "PASS"
    assert run.roundtrip.byte_identical
    assert run.roundtrip.export_bytes == run.article.byte_size
    assert run.roundtrip.first_difference() is None


# ---------------------------------------------------------------------------
# The chunking half — observation only, no latency target was ever declared
# ---------------------------------------------------------------------------

CHUNK_SHAPES: dict[str, tuple[tuple[int, ...], tuple[int, ...], tuple[int, ...]]] = {
    "streamer_shot_3d": ((4, 2, 16, 32), (8, 1, 128, 2048), (8, 1, 128)),
    "streamer_shot_3d_wrapped": ((4, 2, 16, 32), (8, 1, 128, 2048), (8, 1, 128)),
    "streamer_shot_2d": ((8, 24, 32), (16, 32, 2048), (16, 32)),
    "streamer_field_3d": ((1, 2, 4, 2, 8, 32), (1, 1, 16, 1, 32, 1024), (1, 1, 16, 1, 32)),
    "obn_receiver_3d": ((1, 8, 1, 2, 4, 32), (1, 1, 1, 1, 512, 4096), (1, 1, 1, 1, 512)),
    "cdp_offset_3d": ((4, 6, 6, 32), (8, 8, 32, 512), (8, 8, 32)),
    "cdp_offset_2d": ((20, 8, 32), (16, 64, 1024), (16, 64)),
}
"""``(amplitude shape, amplitude chunks, headers chunks)`` per geometry, measured
2026-08-22 against ``multidimio==1.2.1``.

**Observation, not a result against a threshold.** The pre-registration's latency target
was never declared, so no shape here has been shown to meet or miss anything.
"""

STORE_BYTES: dict[str, int] = {
    "streamer_shot_3d": 37851,
    "streamer_shot_3d_wrapped": 37904,
    "streamer_shot_2d": 35075,
    "streamer_field_3d": 39049,
    "obn_receiver_3d": 62033,
    "cdp_offset_3d": 33216,
    "cdp_offset_2d": 33742,
}
"""Total store bytes, measured twice and identical both times. Blosc/zstd is
deterministic under the pins, so a change here is a change in what was written."""

AMPLITUDE_CHUNK_COUNT: dict[str, int] = {
    "streamer_shot_3d": 2,
    "streamer_shot_3d_wrapped": 2,
    "streamer_shot_2d": 1,
    "streamer_field_3d": 4,
    "obn_receiver_3d": 16,
    "cdp_offset_3d": 1,
    "cdp_offset_2d": 2,
}
"""How many chunks the ``amplitude`` array is actually stored in, per geometry."""


@pytest.mark.parametrize("name", PREREGISTERED)
def test_the_chunk_shape_is_a_template_constant_not_a_function_of_the_data(probe, name):
    """What MDIO actually chose, and where the choice came from.

    In every case the chunk shape is the template's own ``full_chunk_shape``, applied
    **verbatim**: not clipped to the array, not derived from the trace count, not
    influenced by the file in any way. A 4-sample-deep fixture gets a 2048-sample chunk
    depth because that is what the template author wrote.

    The shapes are not uniformly oversized, and the pattern in them is deliberate. Every
    template pins its *gather-separating* axes at 1 — ``cable``, ``sail_line``, ``gun``,
    ``component``, ``receiver``, ``shot_line`` — and spends the whole chunk on the axes
    within a gather. So a gather lands in one chunk and two cables never share one, which
    is the right shape for reading a gather and the wrong one for reading across them.

    That is unremarkable at a few hundred traces, and it is the whole question at survey
    scale. Nothing in SDIP records the chunk shape on the certificate today, so a store
    that is unusable for its access pattern is indistinguishable from one that is not.
    """
    from mdio.builder.template_registry import get_template

    run = probe[name]
    shape, amplitude_chunks, header_chunks = CHUNK_SHAPES[name]
    assert run.amplitude_shape == shape
    assert run.amplitude_chunks == amplitude_chunks
    assert run.header_chunks == header_chunks

    declared = tuple(int(x) for x in get_template(run.article.template).full_chunk_shape)
    assert run.amplitude_chunks == declared, "the template constant, unmodified"

    counts = [-(-s // c) for s, c in zip(shape, amplitude_chunks, strict=True)]
    assert int(np.prod(counts)) == AMPLITUDE_CHUNK_COUNT[name]


@pytest.mark.parametrize("name", PREREGISTERED)
def test_the_store_size_is_the_one_that_was_measured(probe, name):
    """Recorded so a codec or chunking change shows up as a number rather than a feeling.

    The OBN store is the one to look at: 62,033 bytes from a 27,152-byte source, the only
    geometry whose store is larger than its SEG-Y. Its chunk shape is
    ``(1, 1, 1, 1, 512, 4096)`` over an array of ``(1, 8, 1, 2, 4, 32)`` — a chunk 1,024
    times the size of the data it holds, sixteen times over.
    """
    assert probe[name].store_bytes == STORE_BYTES[name]


def test_the_latency_leg_of_the_pre_registration_was_not_run(probe):
    """SP9, recorded as an assertion so it cannot be quietly forgotten.

    The pre-registration asks for read-pattern latency against a declared target, with a
    declared N and a cold cache. No target, no candidate shapes and no N were ever
    committed, and there is no authorised compute for a meaningful benchmark. Inventing
    a threshold after seeing the shapes would make the gate bend to the result, which
    **SP9** forbids in either direction.

    So the latency half of the falsifier **cannot be evaluated**, and this test exists to
    say that in the same place the chunk shapes are recorded. The shapes above are
    observations. They are not a pass.
    """
    assert set(CHUNK_SHAPES) == set(PREREGISTERED)
    assert all(run.ingested for run in probe.values())
