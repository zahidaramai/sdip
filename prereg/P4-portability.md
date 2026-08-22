# P4 — Cross-implementation portability

| Field | Value |
|---|---|
| Probe | `P4` · Status `REGISTERED` · Registered 2026-08-22 |
| Blocks | non-Python consumers |
| Related debt | `OPEN_DEBTS.md` D3 · Gate **G4** · Spec §7 G4, §10.3 |

## Question

Can a **non-Python** Zarr implementation read an SDIP store — specifically the
`headers` array?

## Why it matters

§10.3 is the reason adopting SDIP is a reversible decision: consumers read the store
with stock tooling and **no consumer is required to install `sdip` or `mdio`**. G4
asserts that in Python. Whether it holds outside Python is unmeasured.

## Known risk — already measured

From Appendix A.1, read from each array's `zarr.json`:

| Array | `data_type` | Zarr v3 core spec? |
|---|---|---|
| `amplitude` | `float32` | ✅ core |
| `inline`, `crossline`, `time` | `int32` | ✅ core |
| `trace_mask` | `int8` | ✅ core |
| `cdp_x`, `cdp_y` | `float64` | ✅ core |
| **`headers`** | **`{"name": "struct"}`** | ❌ **extension — no v3 specification** |

`zarr-python` raises `UnstableSpecificationWarning` for it; MDIO suppresses that
warning — and the suppression leaks process-globally, measured in `DECISIONS.md`
D-0004. SDIP records the suppression on the certificate and detects the condition
directly from `zarr.json` instead of relying on the warning.

**Everything a consumer needs except the headers is already core-spec and portable.**
The risk is confined to one array.

## Method

Read the same store from at least two non-Python implementations:

- **zarr-java**
- **zarr-rs**
- **TensorStore** (C++/Python bindings; counts as non-`zarr-python`)

For each: open the group, list arrays, read `amplitude` and one coordinate array, then
attempt `headers`. Record exactly which operation fails and with what error.

## Pre-registered parameters

| Parameter | Value |
|---|---|
| Store | The P1 30-trace article, byte-for-byte, plus one larger store if P3 has run |
| Implementations | zarr-java, zarr-rs, TensorStore — versions recorded at run time |
| Success criterion | Group opens; every core-spec array reads bit-identically to the Python read |
| Comparison | Byte equality on the raw buffers. **No tolerance.** |

## Falsifier

**Headers unreadable outside Python.**

Note what is *not* a falsifier: a non-Python implementation failing on a **core-spec**
array. That would be a bug in that implementation, and would be reported there — not a
finding against SDIP. The probe tests SDIP's output, not other people's readers.

## If it fires — pre-approved mitigation

Write a **parallel `(n_traces, 240)` `uint8` header plane** alongside the structured
one.

- Measured cost ≈ **19 B/trace** (Appendix A.3) — the same as the structured array,
  because it is the same bytes.
- Fully **core-spec**: a 2-D `uint8` array is as portable as Zarr gets.
- Better shaped for ML consumption than a structured dtype.

**It is cheap enough that adopting it unconditionally is defensible without waiting for
this probe.** That is a maintainer decision (§12.1) and would be recorded in
`DECISIONS.md`.
