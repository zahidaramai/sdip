"""Probe P2 — `ibm32` fidelity. Pre-registration: ``prereg/P2-ibm32-fidelity.md``.

These tests do two different jobs and the difference matters.

Most of them check the probe's **machinery**: that the word plan is the pre-registered
one, that the accounting is closed, that every failure is explained. Those can be fixed
if they break.

A few pin the **measurement** — the exact counts and the exact regime boundary observed
against the binding pins. If one of those fails, nothing here should be "fixed". It means
the pinned behaviour changed, and P2 must be re-run and its result re-reported under the
new pin (spec §3.3: a pin bump invalidates every certificate issued under the old one).

The comparison is raw ``uint32`` equality throughout. There is no tolerance anywhere in
this file, and there must not be: a float comparison would report success for two
different IBM words that denote the same number, which is one of the failure modes the
probe measures.
"""

from __future__ import annotations

import json

import numpy as np
import pytest
from segy.transforms import TransformFactory

from sdip.probes import (
    DEFAULT_SEED,
    FIXED_MANTISSAS,
    REGIME_WORDS,
    build_word_plan,
    ibm32_roundtrip_sweep,
    mantissa_set,
    sweep_words,
)
from sdip.probes.ibm32 import (
    EXPONENT_CODE_COUNT,
    OVERFLOW_TO_INF,
    UNDERFLOW_TO_ZERO,
    UNEXPLAINED,
    UNNORMALISED_RENORMALISED,
    ZERO_FRACTION_CANONICALISED,
)

PRE_REGISTERED_MANTISSA_COUNT = 16
PRE_REGISTERED_SWEEP_WORDS = 4096
PRE_REGISTERED_POSITIVE_HALF = 2048

# Measured 2026-08-22 against multidimio 1.2.1 / segy 0.6.0 / Python 3.12.
MEASURED_WORDS_TESTED = 4103
MEASURED_BIT_IDENTICAL = 1656
MEASURED_FAILURES = 2447
MEASURED_MODE_COUNTS = {
    OVERFLOW_TO_INF: 920,
    UNDERFLOW_TO_ZERO: 839,
    ZERO_FRACTION_CANONICALISED: 256,
    UNNORMALISED_RENORMALISED: 252,
    "subnormal_precision_loss": 180,
}
MEASURED_SURVIVING_CODES = (0, *range(33, 97))


@pytest.fixture(scope="module")
def sweep():
    """One run of the pre-registered sweep, shared by every read-only assertion."""
    return ibm32_roundtrip_sweep()


def test_mantissa_axis_is_reproducible_from_the_committed_seed():
    """SP9: a stranger must be able to rebuild the axis from the repository alone."""
    rng = np.random.default_rng(DEFAULT_SEED)
    expected = FIXED_MANTISSAS + tuple(
        int(v) for v in rng.integers(0, 0x1000000, size=12, dtype=np.uint64)
    )
    assert mantissa_set() == expected
    assert mantissa_set() == mantissa_set(DEFAULT_SEED)


def test_mantissa_axis_carries_the_pre_registered_extremes():
    mantissas = mantissa_set()
    assert len(mantissas) == PRE_REGISTERED_MANTISSA_COUNT
    assert mantissas[:4] == (0x000000, 0x000001, 0x800000, 0xFFFFFF)
    assert all(0 <= m < 0x1000000 for m in mantissas)


def test_sweep_covers_every_exponent_code_in_both_signs():
    """Exhaustive on the exponent axis is the pre-registered sampling, not a sample."""
    words = sweep_words()
    assert words.size == PRE_REGISTERED_SWEEP_WORDS
    codes = (words >> 24) & 0x7F
    counts = np.bincount(codes, minlength=EXPONENT_CODE_COUNT)
    assert counts.size == EXPONENT_CODE_COUNT
    assert np.array_equal(counts, np.full(EXPONENT_CODE_COUNT, 32))
    signs = words >> 31
    assert int((signs == 0).sum()) == PRE_REGISTERED_POSITIVE_HALF
    assert int((signs == 1).sum()) == PRE_REGISTERED_POSITIVE_HALF


def test_the_word_plan_is_deterministic():
    first, second = build_word_plan(), build_word_plan()
    assert np.array_equal(first.words, second.words)
    assert first.labels == second.labels
    assert first.groups == second.groups


def test_the_plan_carries_every_named_regime_word():
    """The muted-zone cases the pre-registration names explicitly."""
    plan = build_word_plan()
    for label, word in REGIME_WORDS:
        index = plan.labels.index(label)
        assert int(plan.words[index]) == word


def test_the_accounting_is_closed(sweep):
    """Every tested word is either identical or a listed failure. No third bucket."""
    assert sweep.bit_identical + sweep.failure_count == sweep.words_tested
    assert sweep.words_tested == len(build_word_plan().labels)
    assert sum(sweep.tested_by_exponent_code) == sweep.words_tested
    assert sum(sweep.identical_by_exponent_code) == sweep.bit_identical


def test_every_failure_is_classified(sweep):
    """An unexplained failure means the narrative is wrong, even if the verdict is not."""
    assert sweep.unexplained_failures == ()
    assert all(f.failure_mode != UNEXPLAINED for f in sweep.failures)


def test_the_measured_outcome_under_the_binding_pins(sweep):
    """THE RESULT. The pre-registered falsifier fired, and these are the numbers.

    A failure here is not a bug in this file. It means ``segy`` or ``multidimio`` no
    longer behaves as measured, and P2 must be re-run and re-reported (spec §3.3).
    """
    assert sweep.falsifier_fired is True
    assert sweep.passed is False
    assert sweep.status == "FALSIFIED"
    assert sweep.words_tested == MEASURED_WORDS_TESTED
    assert sweep.bit_identical == MEASURED_BIT_IDENTICAL
    assert sweep.failure_count == MEASURED_FAILURES
    assert sweep.failure_counts_by_mode == MEASURED_MODE_COUNTS


def test_the_pre_registered_positive_half_is_reported_on_its_own(sweep):
    """The pre-registration's N is 2,048. The sign-extended run is additional, not a swap."""
    assert sweep.group_tested["sweep_positive"] == PRE_REGISTERED_POSITIVE_HALF
    assert sweep.group_tested["sweep_negative"] == PRE_REGISTERED_POSITIVE_HALF
    assert sweep.group_identical["sweep_positive"] == 828
    assert sweep.group_identical["sweep_negative"] == 827


def test_the_regime_boundary_is_where_the_measurement_puts_it(sweep):
    """Only exponent codes 33-96 survive at all, plus the single true-zero word at 0.

    This is the range a ``SCOPED`` clause has to name. Codes 1-32 underflow, codes
    97-127 overflow, and neither returns a single bit-identical word on any mantissa
    tested.
    """
    surviving = tuple(code for code, count in enumerate(sweep.identical_by_exponent_code) if count)
    assert surviving == MEASURED_SURVIVING_CODES
    assert sweep.exponent_codes_with_no_identical_word == (
        *range(1, 33),
        *range(97, 128),
    )


def test_true_zero_survives_and_negative_zero_does_not(sweep):
    """The muted zone: an all-zero word is safe, a negative zero is not."""
    failing = {f.label for f in sweep.failures if f.group == "regime"}
    assert "true_zero" not in failing
    assert "negative_zero" in failing
    negative_zero = next(f for f in sweep.failures if f.label == "negative_zero")
    assert negative_zero.ibm_word == 0x80000000
    assert negative_zero.returned_ibm_word == 0x00000000
    assert negative_zero.failure_mode == ZERO_FRACTION_CANONICALISED


def test_the_smallest_normalised_ibm_value_vanishes(sweep):
    """16^-64 is roughly 5e-78. float32 stops at about 1e-45, so it flushes to zero."""
    smallest = next(f for f in sweep.failures if f.label == "smallest_normalised_positive")
    assert smallest.ibm_word == 0x00100000
    assert smallest.returned_ibm_word == 0x00000000
    assert smallest.failure_mode == UNDERFLOW_TO_ZERO
    assert smallest.float32_value == 0.0


def test_a_float_comparison_would_have_hidden_a_whole_failure_class(sweep):
    """NON-VACUITY for the raw-word rule (**SP11**), and the reason for it.

    IBM float has redundant representations. These words decode to *exactly* the same
    ``float32`` they started from and still come back as different 4-byte words, so an
    ``array_equal`` on the decoded floats would have scored every one of them a pass.
    """
    renormalised = [f for f in sweep.failures if f.failure_mode == UNNORMALISED_RENORMALISED]
    assert renormalised, "the redundant-representation class must be non-empty"

    to_ieee = TransformFactory.create("ibm_float", direction="to_ieee")
    words = np.array([f.ibm_word for f in renormalised], dtype=np.uint32)
    returned = np.array([f.returned_ibm_word for f in renormalised], dtype=np.uint32)
    assert not np.array_equal(words, returned)
    assert np.array_equal(to_ieee.apply(words.copy()), to_ieee.apply(returned.copy()))


def test_the_overflow_clamp_target_is_itself_a_valid_ibm_word():
    """NON-VACUITY hazard, recorded so nobody re-discovers it as a pass.

    ``ieee2ibm`` clamps an infinite input to exponent code 127 before shifting, which
    lands on the word ``0x61100000``. That word therefore round-trips **bit-identically
    while decoding to infinity**. A probe that happened to test only that word would
    report a clean pass on a value that overflowed, which is why the sweep's mantissa
    axis is committed rather than chosen after the fact.
    """
    to_ieee = TransformFactory.create("ibm_float", direction="to_ieee")
    to_ibm = TransformFactory.create("ibm_float", direction="to_ibm")
    word = np.array([0x61100000], dtype=np.uint32)
    with pytest.warns(RuntimeWarning, match="overflow encountered in ibm2ieee"):
        decoded = to_ieee.apply(word.copy())
    returned = to_ibm.apply(decoded.copy())
    assert bool(np.isinf(decoded[0]))
    assert np.array_equal(word, returned)


def test_the_overflow_warning_is_recorded_and_not_suppressed(sweep):
    """SP6. A run whose ledger is empty is a run that did not reach the overflow regime."""
    categories = {w.category for w in sweep.warnings.observed}
    messages = {w.message for w in sweep.warnings.observed}
    assert "RuntimeWarning" in categories
    assert "overflow encountered in ibm2ieee" in messages
    assert sweep.warnings.suppressions == []


def test_to_json_is_valid_json_and_carries_every_failing_word(sweep):
    """``inf`` is not valid JSON. The serialiser must not lose it or emit it raw."""
    payload = sweep.to_json()
    text = json.dumps(payload, allow_nan=False)
    assert "Infinity" not in text
    assert len(payload["failures"]) == sweep.failure_count
    assert payload["falsifier_fired"] is True
    assert payload["status"] == "FALSIFIED"
    first = payload["failures"][0]
    for key in ("exponent_code", "mantissa", "ibm_word", "float32_value", "returned_ibm_word"):
        assert key in first
    overflowing = next(f for f in payload["failures"] if f["failure_mode"] == OVERFLOW_TO_INF)
    assert overflowing["float32_value"] in {"inf", "-inf"}


def test_summary_states_the_verdict_and_the_regime(sweep):
    text = sweep.summary()
    assert "FALSIFIED" in text
    assert "FIRED" in text
    assert "1-32, 97-127" in text
    assert "overflow encountered in ibm2ieee" in text


@pytest.mark.integration
@pytest.mark.slow
def test_the_ibm32_sample_format_leg_end_to_end(tmp_path):
    """Method leg 4: the same words through a real ingest and export, not just the transform.

    Lives here rather than in ``tests/integration/`` only because P2's file allowance was
    scoped to the probe; it belongs beside the other ingest-driving tests.

    The fixture is a rev 1 SEG-Y — whose standard sample format **is** ``ibm32`` — with
    its 4,096 sample words overwritten by the pre-registered sweep list, big-endian, so
    the pipeline sees the exact bit patterns the transform-level leg saw. Everything
    else in the file is left alone, which is what makes the localisation below possible.
    """
    from sdip._pins import SEGY_BINARY_HEADER_BYTES, SEGY_TEXTUAL_HEADER_BYTES
    from sdip._pins import SEGY_TRACE_HEADER_BYTES as HEADER
    from sdip.export import export
    from sdip.ingest import ingest
    from tests.fixtures.generators import make_poststack3d

    words = sweep_words()
    source = make_poststack3d(tmp_path / "src.sgy", n_inline=8, n_crossline=8, n_samples=64)
    n_traces, n_samples = source.trace_count, source.samples_per_trace
    assert n_traces * n_samples == words.size

    body_start = SEGY_TEXTUAL_HEADER_BYTES + SEGY_BINARY_HEADER_BYTES
    stride = HEADER + n_samples * 4
    planted = words.reshape(n_traces, n_samples)

    raw = bytearray((tmp_path / "src.sgy").read_bytes())
    for trace in range(n_traces):
        base = body_start + trace * stride + HEADER
        raw[base : base + n_samples * 4] = planted[trace].astype(">u4").tobytes()
    (tmp_path / "planted.sgy").write_bytes(bytes(raw))

    result = ingest(tmp_path / "planted.sgy", tmp_path / "planted.mdio")
    round_trip = export(
        tmp_path / "planted.mdio",
        tmp_path / "exported.sgy",
        result.spec.segy_spec,
        source=tmp_path / "planted.sgy",
    )

    exported = (tmp_path / "exported.sgy").read_bytes()
    returned = np.stack(
        [
            np.frombuffer(
                exported[body_start + t * stride + HEADER :][: n_samples * 4], dtype=">u4"
            )
            for t in range(n_traces)
        ]
    )

    # G3 fails, and it fails on the samples alone: the file headers and every trace
    # header come back byte-identical, so the mismatch is the decode and nothing else.
    assert round_trip.byte_identical is False
    assert round_trip.status == "FAIL"
    assert raw[:body_start] == exported[:body_start]
    for trace in range(n_traces):
        base = body_start + trace * stride
        assert raw[base : base + HEADER] == exported[base : base + HEADER]

    # The pipeline reproduces the transform-level measurement word for word. Two
    # altitudes, one result - which is what makes the transform-level sweep evidence
    # about SDIP rather than evidence about a library SDIP happens to depend on.
    identical = int((planted == returned).sum())
    assert identical == 1655
    to_ieee = TransformFactory.create("ibm_float", direction="to_ieee")
    to_ibm = TransformFactory.create("ibm_float", direction="to_ibm")
    # The overflow warning is asserted rather than filtered: this word list reaches the
    # regime that raises it, and a run that stopped raising it would be a changed
    # measurement, not a quieter one.
    with pytest.warns(RuntimeWarning, match="overflow encountered in ibm2ieee"):
        decoded = to_ieee.apply(words.copy())
    transform_level = to_ibm.apply(decoded.copy())
    assert np.array_equal(returned.ravel().astype(np.uint32), transform_level)
