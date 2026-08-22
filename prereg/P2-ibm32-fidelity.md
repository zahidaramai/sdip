# P2 — `ibm32` fidelity

| Field | Value |
|---|---|
| Probe | `P2` |
| Status | `REGISTERED` |
| Registered | 2026-08-22 |
| Blocks | **any `ibm32`-bearing production spec** |
| Related debt | `OPEN_DEBTS.md` D1 |
| Spec clause | §4.4, §8 P2, **SP1** |

## Question

Is the declared `ibm32 → float32` transform **exactly invertible** — for trace-header
fields and for trace samples — across the full IBM exponent range?

## Why it matters

`ibm32 → float32` is the **only** transform SP1 permits at v1.0. If it is not exactly
invertible, SDIP is not an identity map on the affected regime, and every claim in §4
is scoped rather than absolute.

IBM's 24-bit fraction fits IEEE binary32's 24-bit significand, so the **mantissa
argument is clean**. The exponent is not: IBM uses a base-16 exponent spanning roughly
16^±64, which exceeds float32's range of about 1.2e-38 to 3.4e38.

- Overflow → `inf`
- Underflow → subnormal, or zero

**Legacy tapes are the population at risk.** Modern acquisition rarely produces values
in these regimes; the archives SDIP exists to rescue routinely do.

## Method

1. **Exhaustive over IBM exponent codes** (all 128 values of the 7-bit exponent field)
   with a fixed, committed set of representative mantissas including the extremes:
   `0x000000`, `0x000001`, `0x800000`, `0xFFFFFF`.
2. **The denormal / muted-zone regime** explicitly, including true zero, negative zero
   if representable, and the smallest normalised IBM value.
3. Round trip each: `ibm32 → float32 → ibm32`, compared as **raw 4-byte words**, never
   as floats. A float comparison would hide exactly the bit patterns being probed.
4. Independently, run the rev 1 `ibm32` **sample format** end to end through ingest and
   export, and compare the exported file to the source by SHA-256.

## Pre-registered parameters — fixed before the run

| Parameter | Value |
|---|---|
| N (exponent codes) | 128, exhaustive |
| N (mantissas per code) | 4 fixed extremes + 12 seeded pseudorandom, seed `20260822` |
| N (total header words) | 2,048, exhaustive over the exponent axis |
| Sampling | Exhaustive on the exponent axis; fixed seed on the mantissa axis |
| Comparison | Raw `uint32` word equality. **No tolerance. No `allclose`.** |
| Environment | `multidimio` 1.2.1, `segy` 0.6.0, Python 3.12 |

## Falsifier

**Any value where `ibm32 → float32 → ibm32` is not bit-identical as a raw 4-byte word.**

One value is enough. There is no threshold and no acceptable failure rate: this probe
tests an identity claim, and an identity claim with exceptions is a scoped claim.

## If it fires

1. The affected regime is **named** in a `SCOPED` clause on every certificate issued
   for data that could contain it, stating the exponent range and the failure mode.
2. The raw `uint32` view is stored **in parallel** with the decoded `float32`, so the
   source bits are recoverable regardless of the decode.
3. `transforms_declared[].invertibility` becomes `SCOPED` rather than `VERIFIED`.
4. A new `DECISIONS.md` entry records it, and **D1 stays open** in narrowed form.

## Scope narrowing already banked — `DECISIONS.md` D-0003

**No SEG-Y standard trace header the pinned `segy` exposes — rev 0, 1, 2, or 2.1 —
declares a single `ibm32` field.** Measured, not assumed.

Consequences for this probe:

- The **header leg** can only be reached through a survey spec override (§6.4) that
  declares an `ibm32` field. Such an override **must not be accepted** until P2 clears.
- The **sample leg is untouched and remains fully blocking.** `ibm32` is a standard
  SEG-Y sample format and is the common case on legacy tapes.

This narrows where the risk lives. It does not reduce it.

---

## Results

### Run record

| Field | Value |
|---|---|
| Run date | 2026-08-22 |
| Status | `FALSIFIED` — the pre-registered falsifier **fired** |
| Repository HEAD | `fbece9eed93a51b7486dc0aee940676a3987fbb7` |
| Working tree | **dirty** at run time (concurrent unrelated work in `src/sdip/equivalence/`, `tests/`). No certificate is issued from this run; §3.5's clean-tree rule binds `sdip certify`, not a probe. Nothing outside `src/sdip/probes/`, `tests/unit/test_p2_ibm32.py` and this file was touched by P2. |
| Platform | macOS 26.5.2, arm64, CPython 3.12.13 |
| `multidimio` | 1.2.1 (binding pin) |
| `segy` | 0.6.0 (binding pin) |
| `numpy` / `numba` | 2.5.2 / 0.67.0 |
| `zarr` / `xarray` | 3.3.0 / 2026.7.0 |
| Probe code | `src/sdip/probes/ibm32.py` |
| Tests | `tests/unit/test_p2_ibm32.py` — 18 passed |
| Reproduce | `uv run pytest tests/unit/test_p2_ibm32.py -q`, or `uv run python -c "from sdip.probes import ibm32_roundtrip_sweep; print(ibm32_roundtrip_sweep().summary())"` |

**What was exercised.** The pinned `segy` library's own transform, reached through its
public factory — `TransformFactory.create("ibm_float", direction="to_ieee" / "to_ibm")`,
which dispatches to `segy.ibm.ibm2ieee` / `segy.ibm.ieee2ibm`. **Not a reimplementation.**
MDIO decodes `ibm32` on ingest and re-encodes it on export through this same pair, and
leg 4 below confirms the two altitudes give the identical answer on all 4,096 words.

Comparison is raw `uint32` equality throughout. No tolerance, no `allclose`, no float
comparison anywhere in the probe or its tests.

### Verdict against the pre-registered falsifier

> **Falsifier:** any value where `ibm32 → float32 → ibm32` is not bit-identical as a raw
> 4-byte word.

**FIRED.** Not marginally. **2,447 of 4,103 tested words** fail it.

| Quantity | N |
|---|---|
| Words evaluated (total rows) | **4,103** |
| — pre-registered sweep, sign-positive half (the registered N) | 2,048 |
| — same axes with the sign bit set | 2,048 |
| — named denormal / muted-zone regime words | 7 |
| Bit-identical | **1,656** (40.4%) |
| — of the pre-registered 2,048 | **828** (40.4%) |
| — of the sign-negative 2,048 | 827 |
| Failing | **2,447** |
| — value destroyed (not representable in `float32` at all) | 1,939 |
| — value preserved, IBM word changed | 508 |
| Unexplained failures | **0** — every failure is attributed to a named mechanism |

**No exponent code round-trips every word tested on it.** The best case is 26 of 32
(codes 39–96); the other 6 are the zero-fraction words and the unnormalised mantissas
described below.

### Failure modes

| Mode | N | Mechanism |
|---|---|---|
| `overflow_to_inf` | 920 | `16^(code-64)` exceeds `float32`'s ~3.4e38. Decode is `±inf`; re-encode clamps to exponent code 127 before shifting. |
| `underflow_to_zero` | 839 | Value below the smallest `float32` subnormal (~1.4e-45). Decode is `±0.0`; re-encode returns `0x00000000`. **The sample is gone.** |
| `zero_fraction_canonicalised` | 256 | `ibm2ieee` short-circuits on `fraction == 0` and returns `+0.0` regardless of sign or exponent. Every such word re-encodes to `0x00000000`. Value preserved, word not. |
| `unnormalised_renormalised` | 252 | IBM permits up to 3 leading zero hex digits in the fraction; `ieee2ibm` always emits the normalised form. The number is exactly preserved, the spelling is not. |
| `subnormal_precision_loss` | 180 | Decode lands on a `float32` subnormal, which no longer carries a full 24-bit significand. Bits are lost in the decode itself. |

One representative word per mode, verbatim from the run:

| IBM word | code | mantissa | sign | `float32` | returned | mode |
|---|---|---|---|---|---|---|
| `0x80000000` | 0 | `0x000000` | 1 | `0.0` | `0x00000000` | `zero_fraction_canonicalised` |
| `0x00000001` | 0 | `0x000001` | 0 | `0.0` | `0x00000000` | `underflow_to_zero` |
| `0x1B800000` | 27 | `0x800000` | 0 | `1.401298464324817e-45` | `0x21200000` | `subnormal_precision_loss` |
| `0x2301472D` | 35 | `0x01472D` | 0 | `6.00927004039443e-38` | `0x221472D0` | `unnormalised_renormalised` |
| `0x61800000` | 97 | `0x800000` | 0 | `inf` | `0x61100000` | `overflow_to_inf` |

### The regime boundary — what a `SCOPED` clause must name

Measured, not derived from the format's arithmetic:

| Exponent codes | Tested | Bit-identical | What happens |
|---|---|---|---|
| 0 | 37 | 2 | Only the all-zero word `0x00000000` survives — counted twice, once in the sweep and once as the named `true_zero` regime row |
| **1 – 32** | 832 | **0** | Total underflow. Not one word survives on any mantissa tested. |
| 27 – 32 *(subset of the row above)* | 192 | 0 | Subnormal band begins; 154 of 192 lose bits in the decode |
| 33 – 34 | 64 | 42 | First survivors appear |
| 35 – 96 | 1,984 | 1,612 | The usable band. Best case 26 of 32 per code; never 32 of 32. |
| **97 – 127** | 994 | **0** | Total overflow. Not one word survives. |

**Codes 1–32 and 97–127 — 63 of the 128 exponent codes, 49% of the exponent axis —
return zero bit-identical words.** These are the codes a legacy tape can carry and a
modern acquisition system will not produce.

### The denormal / muted-zone regime, explicitly

| Case | Word | `float32` | Returned | Result |
|---|---|---|---|---|
| True zero | `0x00000000` | `0.0` | `0x00000000` | **bit-identical** |
| Negative zero | `0x80000000` | `0.0` | `0x00000000` | FAIL — sign bit lost |
| Smallest normalised, positive | `0x00100000` | `0.0` | `0x00000000` | FAIL — flushed to zero |
| Smallest normalised, negative | `0x80100000` | `-0.0` | `0x00000000` | FAIL — flushed to zero |
| Smallest representable, positive | `0x00000001` | `0.0` | `0x00000000` | FAIL — flushed to zero |
| Largest magnitude, positive | `0x7FFFFFFF` | `inf` | `0x61100000` | FAIL — overflow |
| Largest magnitude, negative | `0xFFFFFFFF` | `-inf` | `0xE1100000` | FAIL — overflow |

A muted zone written as all-zero words survives. A muted zone written as a signed zero,
or as a very small non-zero value, does not.

### Method leg 4 — the rev 1 `ibm32` sample format, end to end

Constructed and run. The rev 1 standard's declared sample format **is** `ibm32`, so a
rev 1 fixture exercises it without any override.

- Fixture: the committed synthetic 3D poststack generator at 8 × 8 × 64 = 4,096 sample
  slots, with the **same 4,096 pre-registered sweep words** written big-endian into the
  sample area by raw byte offset. Everything else in the file — textual header, binary
  header, all 64 trace headers including the planted bytes 233–240 — left untouched.
  Synthetic and deterministic; §6's test-data policy is not strained.
- Path: `sdip.ingest.ingest` → MDIO store → `sdip.export.export`, under the binding pins.

| Measurement | Result |
|---|---|
| **G3 (`sha256(export) == sha256(source)`)** | **FAIL** |
| File size | 35,344 bytes both sides — no structural difference |
| Textual + binary header bytes | **byte-identical** |
| All 64 trace headers, 240 bytes each | **byte-identical** |
| Sample words bit-identical | **1,655 of 4,096** |
| Pipeline result vs transform-level result | **identical on all 4,096 words** |

That last row is the load-bearing one. The transform-level sweep is not evidence about a
library SDIP happens to depend on — it is evidence about SDIP, because the shipped
pipeline reproduces it word for word. The G3 failure is localised to the sample bytes and
to the decode; nothing else in the file moves.

### Non-vacuity notes (SP11)

**1. A float comparison would have scored 252 failures as passes.** The
`unnormalised_renormalised` class decodes to *exactly* the same `float32` it started
from and still returns a different 4-byte word. This is asserted directly in
`test_a_float_comparison_would_have_hidden_a_whole_failure_class`, which shows the
decoded arrays equal while the raw words differ. The pre-registration's insistence on
raw-word comparison is doing real work, not ceremony.

**2. The overflow clamp target is itself a valid IBM word.** `ieee2ibm` clamps an
infinite input to exponent code 97 with mantissa `0x100000`, i.e. `0x61100000`. That word
therefore **round-trips bit-identically while decoding to infinity**. A probe that
happened to test only that word would report a clean pass on a value that overflowed.
Recorded as `test_the_overflow_clamp_target_is_itself_a_valid_ibm_word` so nobody
re-discovers it as good news. It is also why the mantissa axis is committed in advance
rather than chosen after seeing a result.

**3. SP6 — the overflow warning does not reach the parent ledger during ingest.**
`ibm2ieee` raises `RuntimeWarning: overflow encountered in ibm2ieee`. In the probe it is
observed and recorded on `SweepResult.warnings` (2 occurrences, one per decode pass) and
appears in `summary()` and `to_json()`. In a real ingest it is raised inside MDIO's
**spawned worker processes**, so it lands on the worker's stderr and the parent's
`WarningLedger` records nothing — `IngestResult.warnings.observed` was empty on the
leg 4 run despite 2,441 sample words overflowing or underflowing. A certificate issued
for `ibm32` data would therefore carry no warning evidence of the loss. Flagged as a new
finding; it is not something this probe can fix.

### Declared deviations from the pre-registration

Stated because they exist, not because they change the verdict. None of them weakens the
comparison, restricts the range, or moves the falsifier.

1. **Sign axis.** The registered N is 2,048 = 128 codes × 16 mantissas. Both signs were
   run, giving 4,096, plus the 7 named regime words. The registered 2,048 is reported
   **on its own line** (828 bit-identical) and is not replaced by the larger figure. The
   sign-negative half fails at the same rate; the extra coverage changed nothing.
2. **Mantissa draw space.** The registered text says "12 seeded pseudorandom mantissas,
   seed `20260822`" without naming the space. Draws are uniform over the **full** 24-bit
   fraction range via `numpy.random.default_rng(20260822).integers(0, 2**24, size=12)`,
   unnormalised values included. Restricting to normalised mantissas would have removed
   the `unnormalised_renormalised` class — one of the two regimes the probe exists to
   find — so the wider space is the honest reading. The 12 drawn values are
   reproducible from the committed seed and asserted by test.
3. **Regime words re-tested.** Three of the 7 named regime words also appear in the
   sweep. They are evaluated again under their own labels rather than deduplicated, so a
   reader looking for "what happened to negative zero" finds a row saying so. This is why
   the total is 4,103 rather than 4,096; group counts are reported separately so nothing
   is double-counted silently.
4. **Leg 4 fixture.** Synthetic, per §6. No legacy tape was available, and a proprietary
   one could not have entered the repository in any case. The fixture carries the
   structural property that matters — real `ibm32` sample words spanning the full
   exponent axis — which is what §6 asks a synthetic reproducer to do.
5. **Test file location.** The leg 4 end-to-end test lives in `tests/unit/` because P2's
   file allowance was scoped to the probe. It drives a real ingest and belongs in
   `tests/integration/`; it is marked `integration` and `slow` and should be relocated.

### Consequences — required follow-ups, not taken here

The pre-registration's own "If it fires" clause applies in full. These are maintainer
actions outside this probe's file allowance and are **not done**:

1. **`transforms_declared[].invertibility` must become `SCOPED`, not `VERIFIED`**, on
   every certificate for data that could contain `ibm32`.
2. **The `SCOPED` clause must name this regime**: bit-identity holds only for IBM
   exponent codes 33–96 with a normalised, non-zero fraction; codes 1–32 underflow to
   zero, codes 97–127 overflow to infinity, and negative zero loses its sign.
3. **The raw `uint32` view must be stored in parallel** with the decoded `float32`.
   With 2,447 of 4,103 words unrecoverable from the decode alone, this is the only thing
   that makes the source bits recoverable — and 1,939 of those lose the *value*, not
   merely the spelling, so no re-encoding strategy can reconstruct them afterwards.
4. **A `DECISIONS.md` entry** recording the result, and **D1 stays open in narrowed
   form**: no longer "unverified", now "verified as not invertible outside codes 33–96".
5. **The header leg remains unreachable** — `DECISIONS.md` D-0003 measured zero `ibm32`
   fields in every standard trace-header spec the pinned `segy` exposes, so it can only
   arrive via a §6.4 survey-spec override. Such an override **must not be accepted**;
   P2 has now failed rather than merely not-yet-cleared. **The sample leg is live and
   blocking**: `ibm32` is the rev 1 standard sample format, and any legacy tape ingested
   today goes through the path measured above.

### Scope of this result

Measured: the transform pair under the binding pins, exhaustively on the exponent axis
with a committed 16-value mantissa axis and both signs, N = 4,103; plus one end-to-end
ingest/export of 4,096 planted sample words on a 64-trace synthetic rev 1 fixture.

**Not measured:** behaviour under any other pin; `ibm32` in a real header field (no
standard spec declares one); survey-scale volumes (that is P3); whether any mitigation
recovers the lost values.
