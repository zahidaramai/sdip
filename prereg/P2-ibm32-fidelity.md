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
