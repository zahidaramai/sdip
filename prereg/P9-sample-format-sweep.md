# P9 — Sample-format decode fidelity, all formats

- **Registered:** 2026-08-23, **before the run**, per **SP9**
- **Extends:** `P2-ibm32-fidelity.md`, which covered **one** format while its title
  claims the transform generally
- **Authorised by:** `DECISIONS.md` D-0063 ruling 2
- **Status at registration:** NOT RUN

---

## Question

MDIO writes the data variable as `ScalarType.FLOAT32` **unconditionally**
(`mdio/builder/templates/base.py:449`), and `segy` sets the source format from the file's
own `data_sample_format` byte (`segy/file.py:235-239`). The decode is therefore always
`<source format> → float32`.

**For each sample format the pinned `segy` can express, can that decode alter the
value?**

## Why it matters

**P2 measured `ibm32` and the project generalised from it.** `detect_ibm32`,
`amplitude_raw_ibm32` and `ibm32_blocks_equivalence` are all keyed to one format. If
other formats lose values too, then **SP1(a)** is violated for them — a transform runs,
alters data, and the certificate declares nothing — and the `ROUNDTRIP-SCOPED` escape
hatch is unenforced where it is equally needed.

## Method

1. For every member of `segy.standards.codes.DataSampleFormatCode`, take the
   corresponding numpy dtype.
2. Build a probe vector that **straddles the `float32` exact-integer boundary**
   `2**24 = 16,777,216`: the boundary itself, ±1, ±3, the dtype's min and max, and small
   values that must survive.
3. Cast to `float32`, cast back, compare with `np.array_equal`.
4. Record, per format: exact or lossy, and the **first** differing pair.

`ibm32` is **excluded from the cast method** and carries P2's measured result instead —
its decode is a real transform, not a cast, and P2 measured it against the transform.

## Pre-registered parameters

| Parameter | Value |
|---|---|
| Formats | every member of `DataSampleFormatCode` in the pinned `segy` |
| Comparison | `np.array_equal`. **No tolerance.** |
| Boundary | `2**24 = 16,777,216` |
| N | the full probe vector per format, exhaustive over it |
| Seed | none — the vector is fixed and committed, not sampled |

## Falsifier

**The falsifier fires if any format outside `{ibm32}` alters a value.**

If it fires, `detect_ibm32` is too narrow, and every claim keyed to `ibm32` alone —
detection, the raw view, the equivalence block — is under-scoped by exactly the set of
formats that fired.

## What this probe does NOT do

**It does not license a claim about a format it has no row for.** A format the pinned
`segy` adds later belongs to neither the lossy nor the exact set and is **unclassified**,
which is the intended and visible outcome.

**It measures representability, not files.** A ratio of altered values would be an
artifact of the probe vector — a file of small integers loses nothing in any format.
**The threshold is the fact; a ratio is not.** No per-format loss ratio is reported.

## Pre-declared consequence

Per **D-0063 ruling 1**, a firing falsifier does **not** oblige a raw parallel view for
every format that fires. It obliges **detection and declaration** — leg 1 — so the
failure carries a named cause. Views are demand-driven (**ruling 7**).
