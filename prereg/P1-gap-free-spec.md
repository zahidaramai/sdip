# P1 — Gap-free spec viability

| Field | Value |
|---|---|
| Probe | `P1` |
| Status | **`PASSED`** — banked 2026-08-22 |
| Blocks | *(cleared)* |
| Related debt | — |
| Spec clause | §5, §8 P1, Appendix A.1 |

## Question

Can a trace-header specification covering all 240 bytes with zero gaps be constructed
through the upstream **public API**, persisted by MDIO, and read back byte-identically
by a consumer with neither SDIP nor MDIO installed?

## Why it mattered

If it could not, SDIP's central claim — that proprietary and undocumented byte
locations survive the crossing — would have required forking `multidimio` to keep the
deprecated `MDIO__IMPORT__RAW_HEADERS` path alive. The whole "pin, don't fork" stance
(§3.2, **SP7**) rested on this probe.

## Pre-registered falsifier

The **primary suspected falsifier**: Zarr v3 structured dtype failing at high field
count, on the assumption that a gap-free spec would need ~240 fields.

## Results — banked 2026-08-22

**It did not fire. The field count is 97, not 240** — the estimate was ~2.5× too high,
recorded as a maintainer error in Appendix A.4.

**Test article.** Synthetic 3D poststack, 5 inlines × 6 crosslines × 32 samples = 30
traces, 14,640 bytes, with known distinct values planted in header bytes 233–240 of
every trace.

**Spec.** rev 1 standard + 8 `uint8` fillers → 97 fields, itemsize 240, zero gaps.

| Test | Result |
|---|---|
| Root `zarr.json` → `zarr_format` | **3** |
| Open with stock `zarr.open_group`, `mdio` never imported | **PASS** |
| Open with stock `xarray.open_zarr`, `mdio` never imported | **PASS** — full Dataset, dims, coords |
| Codecs on disk | `bytes` + `blosc` / `zstd`, all lossless |
| Amplitude vs analytic ground truth | **exact, max abs diff 0.0** |
| Header bytes 233–240 read without `mdio` | **byte-identical** |
| SEG-Y → MDIO → SEG-Y | **byte-identical whole file** |
| SHA-256, both files | `cf6b1077c24f5ac8…`, 14,640 bytes each |

**Environment.** Python 3.12.3 · `multidimio` 1.2.1 · `segy` 0.6.0 · `zarr-python` 3.3.0
· `xarray` 2026.7.0.

## Verdict

**PASSED.** The pre-registered falsifier did not fire. The fork fallback (§8.9) stays
dormant.

## What P1 did *not* establish — read this before citing it

- **N = 30 traces.** Thirty traces is not a survey. Scale is untouched: **D2**, probe P3.
- **One revision, one geometry.** rev 1, 3D poststack only: **D6** / P6, **D5** / P5.
- **One implementation.** Python only. The `headers` array is written with
  `data_type = {"name": "struct"}`, which is **not in the Zarr v3 core specification**:
  **D3**, probe P4.
- **No engine existed.** The round trip was a hash comparison, not the five-plane
  Equivalence Contract, and no gate had a negative control: **D11**.

## Extension banked 2026-08-22 — `DECISIONS.md` D-0003

The static gap-free construction was subsequently measured for **every** revision the
pinned `segy` exposes, not just rev 1:

| Revision | Fields | Covered | Uncovered | `ibm32` | Gap-free fields |
|---|---|---|---|---|---|
| rev 0 | 71 | 180 / 240 | 181–240 | 0 | 131 |
| rev 1 | 89 | 232 / 240 | 233–240 | 0 | **97** |
| rev 2 | 90 | 240 / 240 | none | 0 | 90 |
| rev 2.1 | 90 | 240 / 240 | none | 0 | 90 |

The worst case is 131 fields. The field-count conclusion generalises across every
revision, and rev 2 / 2.1 are gap-free as shipped. This is a **static** measurement:
it is not an ingest, and P6 remains open.
