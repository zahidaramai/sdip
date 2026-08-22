"""Declared transforms and the `ibm32` scope. **SP1**, spec §4.4, probe **P2**.

**SP1 permits exactly one transform** at v1.0 — the declared SEG-Y sample-format decode,
typically ``ibm32 → float32`` — and requires it to be *"exactly invertible, and verified
by round trip"*.

**Probe P2 measured it and the falsifier fired.** Of 4,103 IBM words swept exhaustively
over the exponent axis with a committed mantissa axis and both signs, **only 1,656
(40.4 %) round-trip bit-identically**. The failures are not marginal and not unexplained:

| Mode | N | What is lost |
|---|---|---|
| ``overflow_to_inf`` | 920 | **The value.** ``16^(code-64)`` exceeds float32's ~3.4e38. |
| ``underflow_to_zero`` | 839 | **The value.** Below float32's smallest subnormal. |
| ``subnormal_precision_loss`` | 180 | **Significand bits**, in the decode itself. |
| ``zero_fraction_canonicalised`` | 256 | The spelling, and the sign of zero. |
| ``unnormalised_renormalised`` | 252 | The spelling; the encoder always normalises. |

**1,939 words lose the value, not merely the spelling.** No re-encoding strategy can
reconstruct them afterwards, because the information left the pipeline at decode time.

What this module does
---------------------
It does **not** fix the transform — the loss is inherent to the target type's range, and
nothing SDIP can do inside ``float32`` will recover an exponent that does not fit.

It makes the loss **impossible to certify away**:

1. Any spec carrying ``ibm32`` is detected, in headers **and** in the sample format.
2. The certificate's ``transforms_declared`` entry is marked ``invertibility: SCOPED``,
   never ``VERIFIED``, and names the exact regime P2 measured.
3. :func:`ibm32_blocks_equivalence` refuses an ``EQUIVALENT`` verdict for such a source
   **when G3 did not achieve byte identity** — see that function for why the condition
   matters and why blocking unconditionally would be a broken gate.

**Why point 3 matters more than it looks.** G3 already catches this: a byte-identical
round trip is impossible when 2,447 words in 4,103 re-encode differently, so G3 fails and
the verdict is not ``EQUIVALENT``. The danger is the *next* step — §7 G3 permits
``ROUNDTRIP-SCOPED`` *"where the source is non-conforming in a way that makes
byte-identity impossible"*, and an operator staring at a failed hash has every incentive
to reach for it. **That escape hatch was written for a non-conforming source, not for a
transform that destroyed 1,939 values.** Scoping this round trip would convert measured
data loss into a paperwork exercise, which is the precise failure mode §0 exists to
prevent.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

IBM32_NAMES: frozenset[str] = frozenset({"ibm32", "ibm"})

BIT_IDENTICAL_EXPONENT_CODES: tuple[int, int] = (33, 96)
"""Inclusive IBM exponent-code range where P2 found bit-identity, with caveats.

Even inside it, a zero fraction or an unnormalised mantissa changes the word. The range
is the *necessary* condition, not a sufficient one.
"""

P2_SCOPE_NOTE: str = (
    "Probe P2 measured ibm32 -> float32 -> ibm32 exhaustively over the IBM exponent "
    "axis (N=4,103) and the falsifier fired: 2,447 words are not bit-identical. "
    "Bit-identity requires exponent code 33-96 AND a normalised, non-zero fraction. "
    "Codes 1-32 underflow to zero and codes 97-127 overflow to infinity - 1,939 words "
    "lose the VALUE, not merely the spelling, and are unrecoverable from the decoded "
    "float32 alone. Negative zero loses its sign. See prereg/P2-ibm32-fidelity.md."
)


@dataclass(frozen=True, slots=True)
class Ibm32Exposure:
    """Where a spec exposes the non-invertible ``ibm32`` transform."""

    header_fields: tuple[str, ...]
    sample_format: str | None

    @property
    def present(self) -> bool:
        """True when this spec touches ``ibm32`` anywhere."""
        return bool(self.header_fields) or self.sample_format is not None

    def to_json(self) -> dict[str, Any]:
        """Certificate-shaped ``transforms_declared`` entry."""
        return {
            "from": "ibm32",
            "to": "float32",
            "applies_to": "samples" if self.sample_format else "header_fields",
            "field_names": list(self.header_fields),
            "sample_format": self.sample_format,
            "invertibility": "SCOPED",
            "scope_note": P2_SCOPE_NOTE,
            "probe": "P2",
            "bit_identical_exponent_codes": list(BIT_IDENTICAL_EXPONENT_CODES),
            "raw_uint32_view_stored": False,
        }


def _format_name(fmt: Any) -> str:
    return str(getattr(fmt, "value", fmt)).lower()


def detect_ibm32(segy_spec: Any) -> Ibm32Exposure:
    """Find every place a SEG-Y spec exposes the ``ibm32`` transform.

    Checks the trace-header fields **and** the sample format. The sample format is the
    live risk: `DECISIONS.md` D-0003 measured **zero** ``ibm32`` fields in every standard
    trace header the pinned ``segy`` exposes, so a header exposure can only arrive
    through a survey-spec override (§6.4) — and P2 having now *failed* rather than merely
    not-yet-cleared, such an override must be refused at review.

    Args:
        segy_spec: The ``SegySpec`` an ingest will run against.

    Returns:
        Where, if anywhere, the spec exposes ``ibm32``.
    """
    fields: list[str] = []
    try:
        for field in segy_spec.trace.header.fields:
            if _format_name(field.format) in IBM32_NAMES:
                fields.append(str(field.name))
    except AttributeError:  # pragma: no cover - a spec without a header is not usable
        pass

    sample_format: str | None = None
    try:
        candidate = _format_name(segy_spec.trace.data.format)
        if candidate in IBM32_NAMES:
            sample_format = candidate
    except AttributeError:
        sample_format = None

    return Ibm32Exposure(header_fields=tuple(fields), sample_format=sample_format)


def ibm32_blocks_equivalence(segy_spec: Any, *, roundtrip_byte_identical: bool) -> tuple[bool, str]:
    """Return ``(blocked, reason)`` for an ``EQUIVALENT`` verdict on this spec.

    **Declaring the exposure and blocking on it are different things**, and conflating
    them would be wrong in a way worth stating.

    Every SEG-Y revision's standard sample format is ``ibm32``, so a rule of *"ibm32
    present, therefore blocked"* would refuse an ``EQUIVALENT`` verdict on **every**
    ingest — including the ones whose whole file round-trips byte for byte. That is not
    caution, it is a broken gate: it fires identically on data that survived perfectly
    and on data that was destroyed, so it distinguishes nothing and would be switched
    off (**SP11**).

    **G3 byte-identity is the empirical answer.** If ``sha256(export) == sha256(source)``
    over the whole file, then every ``ibm32`` word in that file re-encoded to the bits it
    came from. That is not an assumption about the transform; it is a measurement of this
    data, and it is stronger than any argument about exponent ranges. P2's failures live
    at the extremes; a file that never reaches them round-trips, and the hash proves it.

    So the block applies exactly when the proof is absent: ``ibm32`` is declared **and**
    the round trip is not byte-identical. In that case the difference may be a harmless
    re-spelling — or it may be 1,939 destroyed values, and nothing in the output can tell
    them apart, because the information left at decode time.

    The declaration is unconditional either way: ``transforms_declared`` always records
    ``invertibility: SCOPED`` with the regime named, because the transform is not
    invertible in general even when it happened to be invertible here.

    Args:
        segy_spec: The spec the ingest ran against.
        roundtrip_byte_identical: Whether G3 achieved whole-file byte identity.

    Returns:
        ``(False, "")`` when an ``EQUIVALENT`` verdict remains available; otherwise
        ``True`` and a reason naming what P2 measured.
    """
    exposure = detect_ibm32(segy_spec)
    if not exposure.present:
        return False, ""
    if roundtrip_byte_identical:
        # Proven on this data: every ibm32 word came back as the bits it went in as.
        return False, ""
    where = (
        f"sample format {exposure.sample_format}"
        if exposure.sample_format
        else f"header field(s) {', '.join(exposure.header_fields)}"
    )
    return True, (
        f"source declares ibm32 ({where}), and probe P2 measured that transform as NOT "
        f"exactly invertible: 2,447 of 4,103 words fail bit-identity and 1,939 lose the "
        f"value outright. SP1 permits only an exactly invertible transform, so an "
        f"EQUIVALENT verdict is not available while the round trip is not byte-identical "
        f"and the raw uint32 view is not stored in parallel (OPEN_DEBTS D1). The "
        f"difference may be a harmless re-spelling or 1,939 destroyed values, and "
        f"nothing in the output distinguishes them. This is NOT a candidate for "
        f"ROUNDTRIP-SCOPED: "
        f"that clause is for a non-conforming SOURCE, not for a transform that destroyed "
        f"measured values."
    )


COORD_SCALAR_FIELD = "coordinate_scalar"
COORD_ARRAYS: tuple[str, ...] = ("cdp_x", "cdp_y")


@dataclass(frozen=True, slots=True)
class CoordinateScalarTransform:
    """The coordinate-scalar transform MDIO applies to the derived coordinate arrays.

    **This is a transform on output data and SP1 requires it declared.** Probe P5 found
    it undeclared: `transforms_declared[]` named only the sample-format decode, while
    `mdio/segy/scalar.py` was multiplying (positive scalar) or dividing (negative scalar)
    the `cdp_x` and `cdp_y` arrays a consumer reads.

    **No data is lost and no plane was wrong.** The raw 240-byte trace header is
    untouched, so Plane 3 and G3 are unaffected — the round trip stays byte-identical.
    What was wrong is the *declaration*: a consumer reading `cdp_x` gets scaled
    coordinates, and nothing on the certificate said a transform had been applied.
    SP1(a) requires every transform declared, and this one was not.

    **The uniformity check is the sharper half.** Upstream reads the scalar from
    **trace 0 only** and applies it to every trace. A survey whose scalar varies between
    traces — legal SEG-Y — would have one trace's scalar applied to all of them, which
    *is* a fabrication under SP12. SDIP checks every trace and records whether they
    agree, because the alternative is trusting a single header to speak for the file.
    """

    scalar: int
    uniform: bool
    distinct_values: tuple[int, ...]
    trace_count: int

    @property
    def is_identity(self) -> bool:
        """True when the scalar leaves coordinates unchanged."""
        return self.scalar in (0, 1)

    @property
    def operation(self) -> str:
        """What the scalar does to a coordinate."""
        if self.is_identity:
            return "identity"
        return "multiply" if self.scalar > 0 else "divide"

    def to_json(self) -> dict[str, Any]:
        """Certificate-shaped ``transforms_declared`` entry."""
        return {
            "from": "int32 coordinate",
            "to": "float64 scaled coordinate",
            "applies_to": "derived_arrays",
            "field_names": list(COORD_ARRAYS),
            "coordinate_scalar": self.scalar,
            "operation": self.operation,
            "invertibility": "VERIFIED" if self.uniform else "SCOPED",
            "uniform_across_traces": self.uniform,
            "distinct_scalars_found": list(self.distinct_values),
            "traces_checked": self.trace_count,
            "scope_note": (
                "MDIO applies the coordinate scalar to the derived cdp_x/cdp_y arrays. "
                "The raw trace header is untouched, so Plane 3 and G3 are unaffected. "
                "Upstream reads the scalar from TRACE 0 ONLY and applies it to every "
                "trace; SDIP checks every trace and reports whether they agree, because "
                "a non-uniform file would have one trace's scalar applied to all of "
                "them - a fabrication under SP12. Found by probe P5."
            ),
            "probe": "P5",
        }


def detect_coordinate_scalar(source_headers: Any) -> CoordinateScalarTransform | None:
    """Read the coordinate scalar from every trace and report whether they agree.

    Args:
        source_headers: Header array read from the source with the gap-free spec.

    Returns:
        The transform, or ``None`` when the spec declares no coordinate scalar.
    """
    import numpy as np

    names = getattr(source_headers, "dtype", None)
    if names is None or COORD_SCALAR_FIELD not in (names.names or ()):
        return None
    values = np.asarray(source_headers[COORD_SCALAR_FIELD]).ravel()
    distinct = tuple(int(v) for v in np.unique(values))
    return CoordinateScalarTransform(
        scalar=int(values[0]) if values.size else 0,
        uniform=len(distinct) <= 1,
        distinct_values=distinct[:10],
        trace_count=int(values.size),
    )
