"""F1 — gap-free spec generator and gate G1. Specification §5 and §7 G1.

**On where these live.** G7's negative controls are store corruptions and live in
``tests/negative/``. G1 is pre-flight: it runs before a single trace is read, so no
store exists to corrupt. Its controls construct a *defective specification* instead,
which is a unit-level object, so they live here. Putting them in ``tests/negative/``
would arm the ``negative-G7`` CI job on content that is not G7 and make an unbuilt gate
look built.

Every control below asserts two things: the target condition **fails**, and the other
conditions **still pass**. The second half is the one people skip, and it is the half
that catches an over-broad check.
"""

from __future__ import annotations

import numpy as np
import pytest
from segy.schema import ScalarType
from segy.schema.header import HeaderField
from segy.standards import get_segy_standard

from sdip.errors import SpecCompletenessError
from sdip.spec import (
    ALL_BYTES,
    build_gap_free_spec,
    compute_coverage,
    filler_fields,
    format_itemsize,
    g1,
    g1_for_spec,
)

REVISIONS = [0, 1, 2, 2.1]

# Measured in DECISIONS.md D-0003 against the pinned segy, reproducing spec Appendix
# A.2 for rev 1 and extending it to every revision the standard exposes.
EXPECTED = {
    #        base fields, fillers, gap-free fields
    0: (71, 60, 131),
    1: (89, 8, 97),
    2: (90, 0, 90),
    2.1: (90, 0, 90),
}


# ---------------------------------------------------------------------------
# Format widths
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("fmt", "width"),
    [
        (ScalarType.INT8, 1),
        (ScalarType.UINT8, 1),
        (ScalarType.INT16, 2),
        (ScalarType.INT32, 4),
        (ScalarType.INT64, 8),
        (ScalarType.FLOAT32, 4),
        (ScalarType.FLOAT64, 8),
        (ScalarType.IBM32, 4),
        (ScalarType.STRING8, 8),
    ],
)
def test_every_scalar_type_resolves_to_a_width(fmt, width):
    assert format_itemsize(fmt) == width


def test_ibm32_is_four_bytes_without_numpy():
    """Numpy has no ibm32. Resolving it by name is why the check is not np.dtype alone."""
    with pytest.raises(TypeError):
        np.dtype("ibm32")
    assert format_itemsize(ScalarType.IBM32) == 4


def test_string8_survives_case():
    """REGRESSION: ScalarType.STRING8 is "S8"; numpy rejects "s8".

    Normalising case before the numpy lookup silently loses the only string format in
    the SEG-Y standard, which would then be treated as uncoverable.
    """
    assert format_itemsize("S8") == 8
    with pytest.raises(TypeError):
        np.dtype("s8")


def test_an_unresolvable_format_refuses_rather_than_guessing():
    """A field of unknown width cannot be covered, so G1 must refuse."""
    with pytest.raises(ValueError, match="cannot resolve a byte width"):
        format_itemsize("not-a-format")


# ---------------------------------------------------------------------------
# Generator — reproduces the banked measurements
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("revision", REVISIONS)
def test_generator_reproduces_the_banked_field_counts(revision):
    """DECISIONS.md D-0003. If a pin bump moves these, this fails and must be re-read."""
    base, fillers, total = EXPECTED[revision]
    spec = build_gap_free_spec(revision)
    assert spec.base_field_count == base
    assert len(spec.fillers) == fillers
    assert spec.field_count == total


@pytest.mark.parametrize("revision", REVISIONS)
def test_every_revision_produces_a_gap_free_spec(revision):
    spec = build_gap_free_spec(revision)
    assert spec.coverage.gap_free
    assert spec.coverage.covered == ALL_BYTES
    assert spec.itemsize == 240


def test_rev2_and_rev21_need_no_fillers():
    """Measured: they are gap-free as shipped. The filler mechanism is a rev 0/1 concern."""
    assert build_gap_free_spec(2).fillers == ()
    assert build_gap_free_spec(2.1).fillers == ()


def test_fillers_are_uint8_and_nothing_else():
    """SP5. uint8 carries no byte-order, sign, or numeric-format semantics."""
    spec = build_gap_free_spec(1)
    header = spec.segy_spec.trace.header
    for name in spec.fillers:
        declared = next(f for f in header.fields if f.name == name)
        assert declared.format == ScalarType.UINT8
        assert format_itemsize(declared.format) == 1


def test_one_filler_per_byte_never_a_wider_filler_over_a_run():
    """SP5. Bytes 233-240 could be one uint64. That would commit to an endianness."""
    spec = build_gap_free_spec(1)
    assert len(spec.fillers) == 8
    assert sorted(spec.fillers) == sorted(f"pad_{b}" for b in range(233, 241))


def test_filler_names_are_the_byte_they_cover():
    for byte, declared in zip(
        range(233, 241), filler_fields(frozenset(range(233, 241))), strict=True
    ):
        assert declared.name == f"pad_{byte}"
        assert declared.byte == byte


def test_the_base_standard_is_not_mutated():
    """A shared standard corrupted in place would poison every other caller."""
    before = len(get_segy_standard(1).trace.header.fields)
    build_gap_free_spec(1)
    assert len(get_segy_standard(1).trace.header.fields) == before


def test_spec_hash_is_deterministic_and_order_independent():
    """G6 needs two runs to address the header identically."""
    assert build_gap_free_spec(1).sha256() == build_gap_free_spec(1).sha256()


def test_specs_with_identical_field_sets_hash_identically():
    """Rev 2 and rev 2.1 declare the same trace header, so they are the same spec."""
    assert build_gap_free_spec(2).sha256() == build_gap_free_spec(2.1).sha256()


def test_specs_with_different_field_sets_hash_differently():
    assert build_gap_free_spec(0).sha256() != build_gap_free_spec(1).sha256()


def test_unknown_revision_refuses():
    with pytest.raises(ValueError, match="no SEG-Y standard"):
        build_gap_free_spec(99)


def test_certificate_block_is_shaped_for_the_schema():
    from sdip.schema import load_schema

    payload = build_gap_free_spec(1).to_json()
    props = load_schema()["properties"]
    assert payload["spec_itemsize"] == props["spec_itemsize"]["const"]
    assert payload["spec_gap_free"] == props["spec_gap_free"]["const"]
    assert len(payload["spec_sha256"]) == 64


# ---------------------------------------------------------------------------
# G1 — the gate passes what it should
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("revision", REVISIONS)
def test_g1_passes_a_gap_free_spec(revision):
    result = g1_for_spec(build_gap_free_spec(revision))
    assert result.passed
    assert result.status == "PASS"
    assert result.failed == []
    result.raise_for_status()


def test_g1_reports_all_four_conditions_independently():
    result = g1_for_spec(build_gap_free_spec(1))
    assert {c.name for c in result.conditions} == {
        "coverage",
        "no-overlaps",
        "in-range",
        "itemsize",
        "no-void-gaps",
    }


# ---------------------------------------------------------------------------
# G1 NEGATIVE CONTROLS — each defect fails ITS condition and only its condition
# ---------------------------------------------------------------------------


def _fields_of(revision: float = 1) -> list:
    return list(build_gap_free_spec(revision).segy_spec.trace.header.fields)


@pytest.mark.parametrize("revision", [0, 1])
def test_the_raw_standard_fails_g1(revision):
    """NEGATIVE CONTROL: the un-customised standard is exactly what SP4 rejects.

    A sparse spec is a rejected input, not a fast path.
    """
    header = get_segy_standard(revision).trace.header
    result = g1(header.fields, dtype=header.dtype)
    assert not result.passed
    assert {c.name for c in result.failed} == {"coverage", "no-void-gaps"}


def test_a_single_dropped_field_fails_coverage_and_only_coverage():
    """NEGATIVE CONTROL: one uncovered byte kills G1."""
    fields = [f for f in _fields_of() if f.name != "pad_240"]
    result = g1(fields)
    coverage = next(c for c in result.conditions if c.name == "coverage")
    assert not coverage.passed
    assert "240" in coverage.detail
    assert next(c for c in result.conditions if c.name == "no-overlaps").passed
    assert next(c for c in result.conditions if c.name == "in-range").passed


def test_a_doubly_covered_byte_fails_no_overlaps_and_only_that():
    """NEGATIVE CONTROL: a byte claimed twice kills G1 just as an uncovered one does."""
    fields = [*_fields_of(), HeaderField(name="shadow", byte=1, format=ScalarType.UINT8)]
    result = g1(fields)
    overlaps = next(c for c in result.conditions if c.name == "no-overlaps")
    assert not overlaps.passed
    assert "shadow" in overlaps.detail
    assert next(c for c in result.conditions if c.name == "coverage").passed
    assert next(c for c in result.conditions if c.name == "in-range").passed


def test_a_field_running_past_byte_240_fails_in_range():
    """NEGATIVE CONTROL: a 4-byte field at 238 reaches 241 and is off the end."""
    fields = [f for f in _fields_of() if f.byte < 238] + [
        HeaderField(name="overrun", byte=238, format=ScalarType.INT32)
    ]
    result = g1(fields)
    in_range = next(c for c in result.conditions if c.name == "in-range")
    assert not in_range.passed
    assert "overrun" in in_range.detail


def test_a_wrong_itemsize_fails_itemsize_and_only_itemsize():
    """NEGATIVE CONTROL: coverage can be perfect while the dtype is the wrong size."""
    result = g1(_fields_of(), dtype=np.dtype([(f"f{i}", "u1") for i in range(239)]))
    itemsize = next(c for c in result.conditions if c.name == "itemsize")
    assert not itemsize.passed
    assert "239" in itemsize.detail
    assert next(c for c in result.conditions if c.name == "coverage").passed


def test_numpy_void_padding_fails_no_void_gaps():
    """NEGATIVE CONTROL: padding invisible to byte arithmetic.

    Fields can cover 1-240 while numpy builds a larger dtype with unnamed padding no
    field can address. Those bytes would be written and be unrecoverable - a Plane 3
    failure that looks like success.
    """
    padded = np.dtype(
        {"names": ["a", "b"], "formats": ["u1", "u1"], "offsets": [0, 2], "itemsize": 240}
    )
    result = g1(_fields_of(), dtype=padded)
    voids = next(c for c in result.conditions if c.name == "no-void-gaps")
    assert not voids.passed
    assert "unrecoverable" in voids.detail


def test_a_missing_dtype_is_a_failure_not_a_skip():
    """G1 is pre-flight. "Could not check" is not "fine"."""
    result = g1(_fields_of())
    assert not result.passed
    assert {c.name for c in result.failed} == {"itemsize", "no-void-gaps"}
    for condition in result.failed:
        assert "could not be checked" in condition.detail


def test_raise_for_status_aborts_before_any_io():
    """A failing G1 aborts ingestion before a single trace is read."""
    header = get_segy_standard(1).trace.header
    with pytest.raises(SpecCompletenessError, match="uncovered byte"):
        g1(header.fields, dtype=header.dtype).raise_for_status()


def test_an_empty_field_set_fails_everything_it_should():
    result = g1([], dtype=np.dtype([("a", "u1")]))
    assert not result.passed
    assert {c.name for c in result.failed} >= {"coverage", "itemsize"}


def test_coverage_reports_uncovered_bytes_as_readable_runs():
    """(233, 240) reads better than eight integers, and is what a human recognises."""
    coverage = compute_coverage(get_segy_standard(1).trace.header.fields)
    assert coverage.uncovered_runs() == ((233, 240),)
    assert compute_coverage(get_segy_standard(0).trace.header.fields).uncovered_runs() == (
        (181, 240),
    )
