"""**Probe P2 — `ibm32` fidelity.** Specification §8 P2, §4.4, **SP1**; `OPEN_DEBTS.md` D1.

Pre-registration: ``prereg/P2-ibm32-fidelity.md``. Its method, parameters and falsifier
were committed before this module existed and are not negotiable from here.

The question
------------
``ibm32 -> float32`` is the **only** transform SP1 permits at v1.0. If it is not exactly
invertible then SDIP is not an identity map on the affected regime, and every claim in
§4 is scoped rather than absolute.

The mantissa argument is clean: IBM's 24-bit fraction fits IEEE binary32's 24-bit
significand exactly. The exponent is not. IBM's exponent is base-16 and spans roughly
16^±64, which is wider than float32's ~1.2e-38 to 3.4e38 in both directions, so the top
of the IBM range has nowhere to land and the bottom lands on subnormals or on zero.

Why the comparison is on raw words
----------------------------------
Every value here is compared as a raw 4-byte ``uint32``, never as a float. That is not
pedantry; it is the whole measurement. IBM float has **redundant representations** — a
mantissa with leading zero hex digits denotes the same number as its normalised form
with a smaller exponent — so a float comparison reports equality for two different
words and hides exactly the bit patterns the probe exists to find. It would also report
``inf == inf`` for a value that overflowed, and ``0.0 == 0.0`` for one that vanished.

What is exercised
-----------------
The pinned ``segy`` library's own ``IbmFloatTransform``, reached through
``TransformFactory``, in both directions. **Not a reimplementation.** The point is to
measure what SDIP actually runs: MDIO decodes ``ibm32`` on ingest and re-encodes it on
export through this same transform, so the transform-level result and the pipeline
result are the same measurement taken at two altitudes. The end-to-end leg in
``tests/unit/test_p2_ibm32.py`` plants :func:`sweep_words` into a rev 1 SEG-Y and
confirms they agree word for word.

The overflow is a warning, and the warning is recorded
------------------------------------------------------
``ibm2ieee`` raises ``RuntimeWarning: overflow encountered in ibm2ieee`` when it runs off
the top of float32. The sweep runs inside :func:`sdip.guard.warn.recording_warnings` with
``reemit=False`` because the result **displays the ledger** — the warning appears in
:meth:`SweepResult.summary` and in :meth:`SweepResult.to_json`. That is SP6 satisfied by
recording, not by quietening: a run whose ledger is empty is a run that did not overflow.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Final

import numpy as np
from numpy.typing import NDArray
from segy.transforms import TransformFactory

from sdip.guard.warn import WarningLedger, recording_warnings

PROBE_ID: Final[str] = "P2"
"""Probe identifier, as registered in specification §8 and ``prereg/``."""

PREREGISTRATION: Final[str] = "prereg/P2-ibm32-fidelity.md"
"""The committed pre-registration this module executes. It governs; this code does not."""

FALSIFIER: Final[str] = (
    "Any value where ibm32 -> float32 -> ibm32 is not bit-identical as a raw 4-byte word."
)
"""One value is enough. There is no threshold and no acceptable failure rate."""

DEFAULT_SEED: Final[int] = 20260822
"""Pre-registered seed for the mantissa axis. Committed before the run, never re-rolled."""

EXPONENT_CODE_COUNT: Final[int] = 128
"""The IBM exponent field is 7 bits. Every one of its 128 values is tested."""

FIXED_MANTISSAS: Final[tuple[int, ...]] = (0x000000, 0x000001, 0x800000, 0xFFFFFF)
"""The pre-registered extremes: empty, smallest, half, and full 24-bit fraction."""

RANDOM_MANTISSA_COUNT: Final[int] = 12
"""Pre-registered count of seeded pseudorandom mantissas, drawn over the full 24 bits."""

IBM32_SIGN_MASK: Final[int] = 0x80000000
IBM32_EXPONENT_MASK: Final[int] = 0x7F000000
IBM32_FRACTION_MASK: Final[int] = 0x00FFFFFF
MANTISSA_SPACE: Final[int] = 0x01000000
"""IBM 32-bit field layout: 1 sign bit, 7 exponent bits, 24 fraction bits."""

FLOAT32_SMALLEST_NORMAL: Final[float] = float(np.finfo(np.float32).tiny)
"""Below this a float32 is subnormal and no longer carries a full 24-bit significand."""

REGIME_WORDS: Final[tuple[tuple[str, int], ...]] = (
    ("true_zero", 0x00000000),
    ("negative_zero", 0x80000000),
    ("smallest_normalised_positive", 0x00100000),
    ("smallest_normalised_negative", 0x80100000),
    ("smallest_representable_positive", 0x00000001),
    ("largest_magnitude_positive", 0x7FFFFFFF),
    ("largest_magnitude_negative", 0xFFFFFFFF),
)
"""The denormal / muted-zone regime, named explicitly by the pre-registration.

Some of these words also appear in the sweep. They are re-tested here under their own
labels rather than deduplicated away, because the pre-registration names them and a
reader looking for "what happened to negative zero" should find a row saying so.
"""

GROUP_SWEEP_POSITIVE: Final[str] = "sweep_positive"
GROUP_SWEEP_NEGATIVE: Final[str] = "sweep_negative"
GROUP_REGIME: Final[str] = "regime"

OVERFLOW_TO_INF: Final[str] = "overflow_to_inf"
UNDERFLOW_TO_ZERO: Final[str] = "underflow_to_zero"
SUBNORMAL_PRECISION_LOSS: Final[str] = "subnormal_precision_loss"
ZERO_FRACTION_CANONICALISED: Final[str] = "zero_fraction_canonicalised"
UNNORMALISED_RENORMALISED: Final[str] = "unnormalised_renormalised"
UNEXPLAINED: Final[str] = "UNEXPLAINED"

VALUE_PRESERVING_MODES: Final[frozenset[str]] = frozenset(
    {ZERO_FRACTION_CANONICALISED, UNNORMALISED_RENORMALISED}
)
"""Failure modes where the number survives and only its spelling changes.

Still failures — the falsifier is about words — but a different kind of finding from a
value that overflowed or vanished, and reported separately so the two are not conflated.
"""


def mantissa_set(seed: int = DEFAULT_SEED) -> tuple[int, ...]:
    """The pre-registered mantissa axis: four fixed extremes then twelve seeded draws.

    The draws are uniform over the **whole** 24-bit fraction space, unnormalised values
    included. Restricting them to normalised mantissas would quietly remove one of the
    two regimes the probe exists to find.

    Args:
        seed: Pre-registered seed. Changing it changes the probe.

    Returns:
        Sixteen mantissas, in the order the sweep uses them.
    """
    rng = np.random.default_rng(seed)
    drawn = rng.integers(0, MANTISSA_SPACE, size=RANDOM_MANTISSA_COUNT, dtype=np.uint64)
    return FIXED_MANTISSAS + tuple(int(value) for value in drawn)


def sweep_words(seed: int = DEFAULT_SEED) -> NDArray[np.uint32]:
    """Every word on the pre-registered sweep axes, in a fixed order.

    128 exponent codes x 16 mantissas x 2 signs = 4,096 words. The pre-registration's
    ``N = 2,048`` is the sign-positive half of this; the negative half is the same axis
    with the sign bit set and is reported alongside rather than instead.

    Args:
        seed: Pre-registered seed for the mantissa axis.

    Returns:
        The word list, as raw ``uint32``.
    """
    mantissas = mantissa_set(seed)
    return np.array(
        [
            (sign << 31) | (code << 24) | mantissa
            for code in range(EXPONENT_CODE_COUNT)
            for mantissa in mantissas
            for sign in (0, 1)
        ],
        dtype=np.uint32,
    )


@dataclass(frozen=True, slots=True)
class WordPlan:
    """The committed list of words the probe evaluates, with its provenance labels."""

    words: NDArray[np.uint32]
    groups: tuple[str, ...]
    labels: tuple[str, ...]


def build_word_plan(seed: int = DEFAULT_SEED) -> WordPlan:
    """Assemble the sweep and the named regime cases into one evaluation order.

    Args:
        seed: Pre-registered seed for the mantissa axis.

    Returns:
        The full plan: 4,096 sweep words followed by the named regime words.
    """
    sweep = sweep_words(seed)
    groups: list[str] = []
    labels: list[str] = []
    for word in sweep.tolist():
        sign = (word & IBM32_SIGN_MASK) >> 31
        code = (word & IBM32_EXPONENT_MASK) >> 24
        mantissa = word & IBM32_FRACTION_MASK
        groups.append(GROUP_SWEEP_NEGATIVE if sign else GROUP_SWEEP_POSITIVE)
        labels.append(f"e{code:03d}_m{mantissa:06X}_s{sign}")

    regime = np.array([word for _, word in REGIME_WORDS], dtype=np.uint32)
    groups.extend([GROUP_REGIME] * len(REGIME_WORDS))
    labels.extend(label for label, _ in REGIME_WORDS)

    return WordPlan(
        words=np.concatenate([sweep, regime]),
        groups=tuple(groups),
        labels=tuple(labels),
    )


def classify_failure(
    ibm_word: int,
    decoded: float,
    redecoded: float,
    returned_word: int,
) -> str:
    """Name the mechanism behind one non-identical round trip.

    Order matters. Overflow is checked first because an infinite decode says nothing
    useful about the fraction; a zero fraction is checked before underflow because those
    words are not underflowing, they are already zero and merely spelled differently.

    Args:
        ibm_word: The source word.
        decoded: Its ``float32`` decode, widened to Python ``float``.
        redecoded: The decode of ``returned_word``, widened the same way.
        returned_word: The word that came back.

    Returns:
        One of the module's failure-mode constants. :data:`UNEXPLAINED` means the
        classifier is incomplete and the result must not be reported as understood.
    """
    if np.isinf(decoded):
        return OVERFLOW_TO_INF
    if ibm_word & IBM32_FRACTION_MASK == 0:
        return ZERO_FRACTION_CANONICALISED
    if decoded == 0.0:
        return UNDERFLOW_TO_ZERO
    if abs(decoded) < FLOAT32_SMALLEST_NORMAL:
        return SUBNORMAL_PRECISION_LOSS
    if redecoded == decoded and returned_word != ibm_word:
        return UNNORMALISED_RENORMALISED
    return UNEXPLAINED


@dataclass(frozen=True, slots=True)
class FailingWord:
    """One word the round trip did not return unchanged."""

    group: str
    label: str
    exponent_code: int
    mantissa: int
    sign_bit: int
    ibm_word: int
    float32_value: float
    float32_bits: int
    returned_ibm_word: int
    failure_mode: str

    @property
    def value_preserved(self) -> bool:
        """True when the number survived and only its IBM spelling changed."""
        return self.failure_mode in VALUE_PRESERVING_MODES

    def to_json(self) -> dict[str, Any]:
        """Certificate-shaped mapping.

        ``float32_value`` is emitted as a **string**: ``inf`` is not valid JSON, and
        substituting ``null`` for it would erase the single most important thing this
        row records. ``float32_bits`` carries the same value losslessly as an integer.
        """
        return {
            "group": self.group,
            "label": self.label,
            "exponent_code": self.exponent_code,
            "mantissa": f"0x{self.mantissa:06X}",
            "sign_bit": self.sign_bit,
            "ibm_word": f"0x{self.ibm_word:08X}",
            "float32_value": repr(self.float32_value),
            "float32_bits": f"0x{self.float32_bits:08X}",
            "returned_ibm_word": f"0x{self.returned_ibm_word:08X}",
            "failure_mode": self.failure_mode,
            "value_preserved": self.value_preserved,
        }


@dataclass(slots=True)
class SweepResult:
    """P2's measurement: what was tested, what came back, and what broke."""

    seed: int
    mantissas: tuple[int, ...]
    words_tested: int
    bit_identical: int
    failures: tuple[FailingWord, ...]
    tested_by_exponent_code: tuple[int, ...]
    identical_by_exponent_code: tuple[int, ...]
    group_tested: dict[str, int] = field(default_factory=dict)
    group_identical: dict[str, int] = field(default_factory=dict)
    warnings: WarningLedger = field(default_factory=WarningLedger)
    transform_path: str = ""

    @property
    def failure_count(self) -> int:
        """Words that did not come back unchanged."""
        return len(self.failures)

    @property
    def passed(self) -> bool:
        """True only when **every** word round-tripped bit-identically.

        There is no threshold here on purpose. The pre-registered falsifier fires on a
        single value, because the claim under test is an identity claim and an identity
        claim with exceptions is a scoped claim.
        """
        return self.failure_count == 0 and self.bit_identical == self.words_tested

    @property
    def falsifier_fired(self) -> bool:
        """True when the pre-registered falsifier fired. The inverse of :attr:`passed`."""
        return not self.passed

    @property
    def status(self) -> str:
        """``"PASS"`` or ``"FALSIFIED"``."""
        return "PASS" if self.passed else "FALSIFIED"

    @property
    def failure_counts_by_mode(self) -> dict[str, int]:
        """Failure counts keyed by mechanism, largest first."""
        counter = Counter(f.failure_mode for f in self.failures)
        return dict(counter.most_common())

    @property
    def unexplained_failures(self) -> tuple[FailingWord, ...]:
        """Failures the classifier could not account for.

        **Any entry here invalidates the narrative, not the verdict.** The falsifier
        still fired on word equality; what is missing is the explanation, and a probe
        that reports an unexplained mechanism as understood is worse than one that
        reports nothing.
        """
        return tuple(f for f in self.failures if f.failure_mode == UNEXPLAINED)

    @property
    def value_preserving_failure_count(self) -> int:
        """Failures where the number survived and only its IBM spelling changed."""
        return sum(1 for f in self.failures if f.value_preserved)

    @property
    def value_destroying_failure_count(self) -> int:
        """Failures where the source value is not representable in the decode at all."""
        return self.failure_count - self.value_preserving_failure_count

    @property
    def exponent_codes_with_no_identical_word(self) -> tuple[int, ...]:
        """Exponent codes where **not one** tested word survived the round trip.

        This is the regime boundary, measured rather than derived from the format's
        arithmetic, and it is what a ``SCOPED`` clause on a certificate has to name.
        """
        return tuple(
            code
            for code, (tested, identical) in enumerate(
                zip(self.tested_by_exponent_code, self.identical_by_exponent_code, strict=True)
            )
            if tested and not identical
        )

    def summary(self) -> str:
        """A short, plain report of the verdict and the numbers behind it."""
        lines = [
            f"P2 ibm32 fidelity: {self.status}",
            f"  words tested      {self.words_tested}",
            f"  bit-identical     {self.bit_identical}",
            f"  failures          {self.failure_count} "
            f"({self.value_destroying_failure_count} lose the value, "
            f"{self.value_preserving_failure_count} preserve it and change the word)",
            f"  falsifier         {'FIRED' if self.falsifier_fired else 'did not fire'}",
        ]
        lines.extend(f"  {mode:<28}{count}" for mode, count in self.failure_counts_by_mode.items())
        blind = self.exponent_codes_with_no_identical_word
        if blind:
            lines.append(f"  exponent codes with zero survivors: {_ranges(blind)}")
        if self.unexplained_failures:
            lines.append(f"  UNEXPLAINED failures: {len(self.unexplained_failures)}")
        for record in self.warnings.observed:
            lines.append(f"  warning recorded  {record.category}: {record.message}")
        return "\n".join(lines)

    def to_json(self) -> dict[str, Any]:
        """Certificate-shaped mapping, carrying every failing word."""
        return {
            "probe": PROBE_ID,
            "prereg": PREREGISTRATION,
            "falsifier": FALSIFIER,
            "falsifier_fired": self.falsifier_fired,
            "status": self.status,
            "comparison": "raw uint32 word equality; no tolerance, no allclose",
            "transform_path": self.transform_path,
            "seed": self.seed,
            "mantissas": [f"0x{m:06X}" for m in self.mantissas],
            "words_tested": self.words_tested,
            "bit_identical": self.bit_identical,
            "failure_count": self.failure_count,
            "failure_counts_by_mode": self.failure_counts_by_mode,
            "value_preserving_failures": self.value_preserving_failure_count,
            "value_destroying_failures": self.value_destroying_failure_count,
            "unexplained_failures": len(self.unexplained_failures),
            "groups": {
                name: {
                    "tested": self.group_tested.get(name, 0),
                    "bit_identical": self.group_identical.get(name, 0),
                }
                for name in sorted(self.group_tested)
            },
            "tested_by_exponent_code": list(self.tested_by_exponent_code),
            "identical_by_exponent_code": list(self.identical_by_exponent_code),
            "exponent_codes_with_no_identical_word": list(
                self.exponent_codes_with_no_identical_word
            ),
            "failures": [f.to_json() for f in self.failures],
            "warnings": self.warnings.to_json(),
        }


def _ranges(codes: tuple[int, ...]) -> str:
    """Collapse a sorted code list into ``a-b, c-d`` form for a readable summary."""
    if not codes:
        return "none"
    spans: list[tuple[int, int]] = []
    start = previous = codes[0]
    for code in codes[1:]:
        if code == previous + 1:
            previous = code
            continue
        spans.append((start, previous))
        start = previous = code
    spans.append((start, previous))
    return ", ".join(str(lo) if lo == hi else f"{lo}-{hi}" for lo, hi in spans)


def ibm32_roundtrip_sweep(seed: int = DEFAULT_SEED) -> SweepResult:
    """Round trip every pre-registered word through the pinned ``segy`` transforms.

    ``ibm32 -> float32 -> ibm32``, compared as raw ``uint32``. The third conversion —
    decoding the returned word again — is not part of the comparison; it is what lets
    :func:`classify_failure` tell a redundant IBM spelling apart from a lost value.

    Args:
        seed: Pre-registered seed for the mantissa axis. The default is the committed
            one; passing anything else produces a different probe, not this one.

    Returns:
        The measurement, including every failing word and the warnings the decode raised.
    """
    plan = build_word_plan(seed)
    to_ieee = TransformFactory.create("ibm_float", direction="to_ieee")
    to_ibm = TransformFactory.create("ibm_float", direction="to_ibm")

    ledger = WarningLedger()
    with recording_warnings(ledger, reemit=False):
        decoded = to_ieee.apply(plan.words.copy())
        returned = to_ibm.apply(decoded.copy())
        redecoded = to_ieee.apply(returned.copy())

    decoded_bits = decoded.view(np.uint32)
    tested = [0] * EXPONENT_CODE_COUNT
    identical = [0] * EXPONENT_CODE_COUNT
    group_tested: Counter[str] = Counter()
    group_identical: Counter[str] = Counter()
    failures: list[FailingWord] = []
    bit_identical = 0

    rows = zip(
        plan.words.tolist(),
        returned.tolist(),
        decoded.tolist(),
        redecoded.tolist(),
        decoded_bits.tolist(),
        plan.groups,
        plan.labels,
        strict=True,
    )
    for word, back, value, revalue, bits, group, label in rows:
        code = (word & IBM32_EXPONENT_MASK) >> 24
        tested[code] += 1
        group_tested[group] += 1
        if word == back:
            bit_identical += 1
            identical[code] += 1
            group_identical[group] += 1
            continue
        failures.append(
            FailingWord(
                group=group,
                label=label,
                exponent_code=code,
                mantissa=word & IBM32_FRACTION_MASK,
                sign_bit=(word & IBM32_SIGN_MASK) >> 31,
                ibm_word=word,
                float32_value=value,
                float32_bits=bits,
                returned_ibm_word=back,
                failure_mode=classify_failure(word, value, revalue, back),
            )
        )

    return SweepResult(
        seed=seed,
        mantissas=mantissa_set(seed),
        words_tested=len(plan.labels),
        bit_identical=bit_identical,
        failures=tuple(failures),
        tested_by_exponent_code=tuple(tested),
        identical_by_exponent_code=tuple(identical),
        group_tested=dict(group_tested),
        group_identical=dict(group_identical),
        warnings=ledger,
        transform_path=(
            "segy.transforms.TransformFactory.create('ibm_float', direction=...) "
            "-> segy.ibm.ibm2ieee / segy.ibm.ieee2ibm (pinned segy 0.6.0)"
        ),
    )
