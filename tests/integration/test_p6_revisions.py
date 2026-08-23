"""Probe **P6** — revision coverage. rev 0, rev 1, rev 2 and rev 2.1, end to end.

The pre-registration is `prereg/P6-revision-coverage.md`. Its method, parameters and
falsifier are fixed and are not changed here to suit a result. Per revision: generate a
deterministic fixture, build the gap-free spec and assert **G1**, ingest, run all five
planes, export and compare the whole file by SHA-256 (**G3**).

    Falsifier: any revision where G1 or G3 cannot be satisfied.

**It fired.** Only rev 1 completes the leg. rev 0, rev 2 and rev 2.1 satisfy G1 and then
fail to ingest, so G3 is unreachable for three of the four revisions. `DECISIONS.md`
D-0003 banked gap-free *construction* for all four statically, and that measurement
still holds — what this file adds is that construction is not enough.

Read the asymmetry the pre-registration built in: G1 passing everywhere while ingest
fails is the *good* half of a bad result. Had G1 failed here it would have meant the
ingest path disagreed with the spec-construction path, which is a worse finding than any
of the three blockers below.

**A test in this file passing does not mean the revision works.** The tests pin the
measured state, including the three failures, so that a future change which fixes a
revision breaks a test loudly and forces the record to be updated. That is the opposite
of accepting the failure: D6 stays open for rev 0, rev 2 and rev 2.1.

The tests named ``test_diagnosis_*`` are **not** part of the pre-registered method. They
isolate each blocker to the smallest thing that causes it, because "rev 2 fails" is a
verdict and "rev 2 fails on one ``S8`` field, and would then fail again on export" is a
diagnosis. Nothing they do satisfies G1 or G3 for any revision.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from segy import SegyFile
from segy.exceptions import NonSpecFieldError
from segy.schema import ScalarType
from segy.schema.header import HeaderField

from sdip._pins import SEGY_TRACE_HEADER_BYTES
from sdip.equivalence import plane_1, plane_2, plane_3, plane_4, plane_5
from sdip.export import export
from sdip.guard.warn import WarningLedger, recording_warnings
from sdip.ingest import (
    attach_raw_file_headers,
    file_headers_persisted,
    ingest,
    read_raw_file_headers,
)
from sdip.spec import SUPPORTED_REVISIONS, build_gap_free_spec, g1_for_spec
from tests.fixtures.generators.revisions import (
    GEOMETRY_BYTES,
    SampleFormatDeclaration,
    make_revision_poststack3d,
    read_geometry,
)

pytestmark = pytest.mark.integration

PREREGISTERED_REVISIONS: tuple[float | int, ...] = (0, 1, 2, 2.1)
"""The four revisions the pre-registration names. None is skipped."""

TEMPLATE = "PostStack3DTime"
"""The MDIO template every leg ingests against. One template, four revisions."""

BLOCKED = "BLOCKED"
"""A step that could not run because an earlier one failed. Never a pass."""

ARTICLE_TRACES = 30
ARTICLE_BYTES = 14640
"""The Appendix A.1 article shape, held constant so the four legs are comparable."""

BANKED_STATIC_SPEC: dict[float | int, tuple[int, int, int]] = {
    0: (71, 60, 131),
    1: (89, 8, 97),
    2: (90, 0, 90),
    2.1: (90, 0, 90),
}
"""``(standard fields, fillers, gap-free fields)`` per revision, from `DECISIONS.md` D-0003.

Asserted here so that the spec each ingest actually used is provably the spec D-0003
measured. Without that link a P6 result would be about some other spec.
"""

MEASURED_INGEST_BLOCKER: dict[float | int, str] = {
    0: (
        "Required fields ['cdp_x', 'cdp_y', 'crossline', 'inline'] for template "
        "PostStack3DTime not found in the provided segy_spec"
    ),
    2: "Unsupported numpy dtype 'bytes64' for conversion to ScalarType",
    2.1: "Unsupported numpy dtype 'bytes64' for conversion to ScalarType",
}
"""The exact error that ends each failing leg. Pinned, so a change of cause is visible."""


@dataclass(frozen=True, slots=True)
class RevisionRun:
    """One revision's pre-registered leg, recorded whether it completed or not."""

    revision: float | int
    base_field_count: int
    field_count: int
    filler_count: int
    itemsize: int
    spec_sha256: str
    g1: str
    ingest_error: str | None
    planes: tuple[str, ...]
    g3: str
    byte_identical: bool | None
    first_difference: dict[str, Any] | None
    sample_format: SampleFormatDeclaration


def _run_revision(root: Path, revision: float | int) -> RevisionRun:
    """Run the pre-registered leg for one revision and record what happened.

    An ingest failure is a **measurement**, not an error to propagate: the probe asks
    whether every revision ingests, so the run that does not ingest is data. The exact
    message is kept and asserted against :data:`MEASURED_INGEST_BLOCKER`, which is what
    stops a genuine defect in this file being recorded as a revision blocker.
    """
    work = root / f"rev{str(revision).replace('.', '_')}"
    fixture = make_revision_poststack3d(work / "src.sgy", revision=revision)
    built = build_gap_free_spec(revision)
    gate = g1_for_spec(built)

    common = {
        "revision": revision,
        "base_field_count": built.base_field_count,
        "field_count": built.field_count,
        "filler_count": len(built.fillers),
        "itemsize": built.itemsize,
        "spec_sha256": built.sha256(),
        "g1": gate.status,
        "sample_format": fixture.sample_format,
    }

    store = work / "out.mdio"
    try:
        ingest(fixture.path, store, revision=revision, template=TEMPLATE)
    except Exception as exc:
        return RevisionRun(
            ingest_error=f"{type(exc).__name__}: {exc}",
            planes=(BLOCKED,) * 5,
            g3=BLOCKED,
            byte_identical=None,
            first_difference=None,
            **common,
        )

    spec = built.segy_spec
    planes = (
        plane_1(fixture.path, store),
        plane_2(fixture.path, store),
        plane_3(fixture.path, store, spec, g1_passed=gate.passed),
        plane_4(fixture.path, store, spec),
        plane_5(fixture.path, store, spec),
    )
    roundtrip = export(store, work / "back.sgy", spec, source=fixture.path)
    return RevisionRun(
        ingest_error=None,
        planes=tuple(p.status for p in planes),
        g3=roundtrip.status,
        byte_identical=roundtrip.byte_identical,
        first_difference=roundtrip.first_difference(),
        **common,
    )


@pytest.fixture(scope="module")
def p6(tmp_path_factory) -> dict[float | int, RevisionRun]:
    """The whole probe, run once. Module-scoped because conversion is the slow part."""
    root = tmp_path_factory.mktemp("p6")
    return {revision: _run_revision(root, revision) for revision in PREREGISTERED_REVISIONS}


# ---------------------------------------------------------------------------
# The fixtures — four files that differ only in the revision
# ---------------------------------------------------------------------------


def test_the_probe_covers_every_revision_the_code_claims_to_support():
    """A probe that skips a revision proves nothing about the one it skipped."""
    assert SUPPORTED_REVISIONS == PREREGISTERED_REVISIONS


@pytest.mark.parametrize("revision", PREREGISTERED_REVISIONS)
def test_every_fixture_matches_the_article_shape(tmp_path, revision):
    """Same 30 traces and same 14,640 bytes for all four, so the legs are comparable."""
    fixture = make_revision_poststack3d(tmp_path / "a.sgy", revision=revision)
    assert fixture.trace_count == ARTICLE_TRACES
    assert fixture.byte_size == ARTICLE_BYTES


@pytest.mark.parametrize("revision", PREREGISTERED_REVISIONS)
def test_every_fixture_is_deterministic(tmp_path, revision):
    """SP9 / G6. A fixture that varies between runs makes determinism unmeasurable."""
    a = make_revision_poststack3d(tmp_path / "a.sgy", revision=revision)
    b = make_revision_poststack3d(tmp_path / "b.sgy", revision=revision)
    assert a.path.read_bytes() == b.path.read_bytes()


def test_rev0_carries_geometry_at_the_canonical_bytes(tmp_path):
    """Geometry is written by raw offset for rev 0, and read back with no spec.

    Read back with no spec involved. Without this the rev 0 leg would be measuring a
    file with no geometry at all rather than a rev 0 file.
    """
    fixture = make_revision_poststack3d(tmp_path / "rev0.sgy", revision=0)
    assert fixture.geometry_declared_by_standard is False

    geometry = read_geometry(fixture.path, fixture.trace_count, fixture.samples_per_trace)
    expected_inline = np.array([il for il, _ in fixture.geometry], dtype=np.int32)
    expected_crossline = np.array([xl for _, xl in fixture.geometry], dtype=np.int32)
    assert np.array_equal(geometry["inline"], expected_inline)
    assert np.array_equal(geometry["crossline"], expected_crossline)


def test_rev0_sample_format_is_recorded_as_operator_supplied(tmp_path):
    """**SP1.** An assumed sample format is a declared transform and must be stated.

    rev 0 defines no mandatory sample-format field, so nothing in the file is required
    to say what the samples are. The fixture assumes ``ibm32`` and says so; every later
    revision reads the same value out of a field the standard guarantees.
    """
    rev0 = make_revision_poststack3d(tmp_path / "rev0.sgy", revision=0).sample_format
    rev1 = make_revision_poststack3d(tmp_path / "rev1.sgy", revision=1).sample_format
    assert rev0.scalar_type == "ibm32"
    assert rev0.declared_by_standard is False
    assert "OPERATOR-SUPPLIED" in rev0.supplied_via
    assert rev1.scalar_type == "ibm32"
    assert rev1.declared_by_standard is True


# ---------------------------------------------------------------------------
# Step 2 — G1, and the asymmetry the pre-registration built in
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("revision", PREREGISTERED_REVISIONS)
def test_g1_passes_for_every_revision(p6, revision):
    """A G1 failure here would mean the ingest path disagrees with spec construction.

    D-0003 banked G1 as satisfiable for all four statically. This runs it on the spec
    the ingest is actually handed, which is the only version of the claim that matters.
    """
    assert p6[revision].g1 == "PASS"


@pytest.mark.parametrize("revision", PREREGISTERED_REVISIONS)
def test_the_spec_matches_the_banked_static_measurement(p6, revision):
    """Links this probe to D-0003: same revision, same fields, same fillers."""
    run = p6[revision]
    assert (run.base_field_count, run.filler_count, run.field_count) == BANKED_STATIC_SPEC[revision]
    assert run.itemsize == SEGY_TRACE_HEADER_BYTES


# ---------------------------------------------------------------------------
# Steps 3-5 — ingest, five planes, round trip
# ---------------------------------------------------------------------------


def test_rev1_completes_the_whole_leg(p6):
    """The positive control. Without one, "three revisions fail" has no baseline."""
    run = p6[1]
    assert run.ingest_error is None
    assert run.planes == ("PASS",) * 5
    assert run.g3 == "PASS"
    assert run.byte_identical is True
    assert run.first_difference is None


def test_the_falsifier_fired_for_rev_0_rev_2_and_rev_2_1(p6):
    """The falsifier fired, so **a passing assertion here means the probe FAILED**.

    It records the measured state so that a change which fixes a revision breaks here
    and forces the record to be updated. It is not an acceptance of the failure: the
    pre-registered falsifier is "any revision where G1 or G3 cannot be satisfied", three
    revisions cannot satisfy G3, and D6 stays open for all three.
    """
    satisfied_g3 = {revision for revision, run in p6.items() if run.g3 == "PASS"}
    assert satisfied_g3 == {1}

    for revision in (0, 2, 2.1):
        run = p6[revision]
        assert run.g1 == "PASS", "G1 must still hold - a G1 failure is the worse finding"
        assert run.ingest_error is not None
        assert run.planes == (BLOCKED,) * 5
        assert run.g3 == BLOCKED


@pytest.mark.parametrize("revision", sorted(MEASURED_INGEST_BLOCKER))
def test_each_blocked_ingest_fails_for_the_measured_reason(p6, revision):
    """Pins the cause, not just the failure. A different cause is a different finding."""
    error = p6[revision].ingest_error
    assert error is not None
    assert MEASURED_INGEST_BLOCKER[revision] in error


# ---------------------------------------------------------------------------
# DIAGNOSES — not part of the pre-registered method, and they satisfy no gate
# ---------------------------------------------------------------------------


def _diagnostic_ingest(source: Path, store: Path, spec: Any) -> None:
    """Ingest against a **modified** spec, to isolate a blocker. Not a supported path.

    :func:`sdip.ingest.ingest` builds its own spec from a revision number, which is
    right for the product and useless for a diagnosis: isolating a blocker means
    changing the spec one field at a time and seeing what moves. This uses the same
    public helpers the orchestrator uses, so the only difference between it and a real
    ingest is the spec.

    It deliberately skips the orchestrator's pre-flight guards, and nothing it produces
    is certifiable or counts toward any gate.
    """
    raw_headers = read_raw_file_headers(source)
    with recording_warnings(WarningLedger(), reemit=False), file_headers_persisted():
        from mdio import segy_to_mdio
        from mdio.builder.template_registry import get_template

        segy_to_mdio(
            segy_spec=spec,
            mdio_template=get_template(TEMPLATE),
            input_path=source,
            output_path=store,
            overwrite=True,
        )
    attach_raw_file_headers(store, raw_headers)


def test_diagnosis_rev0_is_blocked_only_by_the_undeclared_geometry(tmp_path):
    """Only four absent field *declarations* block rev 0. Its data is fine.

    The bytes are already in the file at the canonical positions; the rev 0 standard
    simply does not name them, so the gap-free spec covers 181-240 with ``uint8``
    fillers and the template cannot find the four fields it indexes on. Declaring them
    — which is what a §6.4 survey override is for, and §6.4 is not built — makes the
    whole leg pass.

    **This does not satisfy P6 for rev 0.** The pre-registered method builds the spec
    with :func:`build_gap_free_spec` and nothing else, and under that method rev 0 does
    not ingest. What it establishes is that one specified, unbuilt mechanism closes the
    gap, and that nothing else about rev 0 is broken.
    """
    fixture = make_revision_poststack3d(tmp_path / "rev0.sgy", revision=0)
    built = build_gap_free_spec(0)
    header = built.segy_spec.trace.header
    header.customize(
        [
            HeaderField(name=name, byte=byte, format=ScalarType.INT32)
            for name, byte in GEOMETRY_BYTES.items()
        ]
    )
    assert g1_for_spec(built.segy_spec).status == "PASS", "the override must stay gap-free"
    # 131 gap-free fields, minus the 16 uint8 fillers over 181-196, plus 4 int32.
    assert len(header.fields) == 119

    store = tmp_path / "rev0.mdio"
    _diagnostic_ingest(fixture.path, store, built.segy_spec)
    planes = (
        plane_1(fixture.path, store),
        plane_2(fixture.path, store),
        plane_3(fixture.path, store, built.segy_spec, g1_passed=True),
        plane_4(fixture.path, store, built.segy_spec),
        plane_5(fixture.path, store, built.segy_spec),
    )
    # See the note at the other diagnosis site: `_diagnostic_ingest` bypasses the
    # orchestrator, so plane 4 fails only on the raw view that path never writes
    # (D-0061). The decoded samples matched.
    assert [p.status for p in planes[:3]] == ["PASS"] * 3
    assert planes[4].status == "PASS"
    assert planes[3].evidence["mismatch_count"] == 0
    assert [m["array"] for m in planes[3].evidence["missing_required_arrays"]] == [
        "amplitude_raw_ibm32"
    ]

    roundtrip = export(store, tmp_path / "rev0_back.sgy", built.segy_spec, source=fixture.path)
    assert roundtrip.byte_identical
    assert roundtrip.first_difference() is None


def test_diagnosis_rev0_needs_its_sample_format_supplied_in_the_binary_header(tmp_path):
    """The pinned reader requires binary bytes 3225-3226 for **every** revision.

    ``SegyFile._update_spec()`` reads ``data_sample_format`` unconditionally and maps it
    through ``DataSampleFormatCode``. The rev 0 fixture only opens because
    ``SegyFactory`` stamped code 1 there. A genuine rev 0 archive — where the field the
    1975 standard never mandated is zero — does not open at all, and SDIP currently has
    no surface through which an operator could supply the format instead.

    That is the sharp end of the rev 0 sample-format question: the format is not merely
    undeclared in rev 0, it is **unsuppliable** through SDIP today.
    """
    fixture = make_revision_poststack3d(tmp_path / "rev0.sgy", revision=0)
    raw = bytearray(fixture.path.read_bytes())
    assert int.from_bytes(raw[3224:3226], "big") == 1, "the generator supplied ibm32"

    raw[3224:3226] = b"\x00\x00"
    unsupplied = tmp_path / "rev0_unsupplied.sgy"
    unsupplied.write_bytes(bytes(raw))

    with pytest.raises(ValueError, match="0 is not a valid DataSampleFormatCode"):
        SegyFile(str(unsupplied), spec=build_gap_free_spec(0).segy_spec)


@pytest.mark.parametrize("revision", [2, 2.1])
def test_diagnosis_rev2_has_two_blockers_not_one(tmp_path, revision):
    """Two blockers, and the second is invisible behind the first.

    **Blocker 1, ingest.** The rev 2 standard declares ``trace_header_name`` at byte 233
    as an 8-character string. It is the only non-integer field in the 240 bytes, and
    MDIO 1.2.1 has no ``ScalarType`` for it, so the header dtype cannot be built.

    **Blocker 2, export.** Replace that one field with eight ``uint8`` and the ingest
    runs and all five planes pass — and the export then fails anyway. MDIO's
    ``mdio_spec_to_segy`` injects the **rev 1** ``segy_revision`` field into any spec
    whose binary header lacks it, which for rev 2 and rev 2.1 overwrites bytes 301-302
    where ``segy_revision_major`` and ``segy_revision_minor`` live. The factory then
    asks for a field the injection just removed.

    Both are upstream findings, raised as issues rather than routed around (§3.3). The
    field swap here is a probe instrument only: replacing a field the standard *does*
    define is not gap-free spec construction, and it is a spec-mechanism change that
    needs a maintainer decision (§9).
    """
    fixture = make_revision_poststack3d(tmp_path / "src.sgy", revision=revision)
    built = build_gap_free_spec(revision)
    header = built.segy_spec.trace.header

    non_integer = {
        name: (dtype.str, offset + 1)
        for name, (dtype, offset) in (header.dtype.fields or {}).items()
        if dtype.kind not in "iu"
    }
    assert non_integer == {"trace_header_name": ("|S8", 233)}

    header.customize(
        [
            HeaderField(name=f"pad_{byte}", byte=byte, format=ScalarType.UINT8)
            for byte in range(233, 241)
        ]
    )
    assert g1_for_spec(built.segy_spec).status == "PASS"
    assert built.segy_spec.trace.header.dtype.itemsize == SEGY_TRACE_HEADER_BYTES

    store = tmp_path / "out.mdio"
    _diagnostic_ingest(fixture.path, store, built.segy_spec)
    planes = (
        plane_1(fixture.path, store),
        plane_2(fixture.path, store),
        plane_3(fixture.path, store, built.segy_spec, g1_passed=True),
        plane_4(fixture.path, store, built.segy_spec),
        plane_5(fixture.path, store, built.segy_spec),
    )
    # Planes 1, 2, 3 and 5 PASS: the spec blocker was the only ingest blocker, which is
    # what this diagnosis measures. Plane 4 FAILS for a reason that is about the
    # DIAGNOSTIC PATH, not the revision: `_diagnostic_ingest` bypasses the orchestrator,
    # so an ibm32 source arrives with no `amplitude_raw_ibm32` view and plane 4 now
    # requires one (D-0061). Its decoded leg is clean - `mismatch_count == 0` - so the
    # samples themselves matched, which is the fact this test is after.
    assert [p.status for p in planes[:3]] == ["PASS"] * 3, "blocker 1 was the only blocker"
    assert planes[4].status == "PASS", "blocker 1 was the only blocker"
    assert planes[3].evidence["mismatch_count"] == 0, "the decoded samples still matched"
    assert [m["array"] for m in planes[3].evidence["missing_required_arrays"]] == [
        "amplitude_raw_ibm32"
    ], "the only plane-4 failure is the view the diagnostic path never writes"

    with pytest.raises(NonSpecFieldError, match="segy_revision_major"):
        export(store, tmp_path / "back.sgy", built.segy_spec, source=fixture.path)
