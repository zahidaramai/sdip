# P5 — Irregular geometry

| Field | Value |
|---|---|
| Probe | `P5` · Status `REGISTERED` · Registered 2026-08-22 |
| Blocks | **any real survey** |
| Related debt | `OPEN_DEBTS.md` D5 · Spec §4.6, **SP12** |

## Question

Do dead traces, duplicate index tuples, sparse and ragged grids, missing lines, and
coordinate-scalar edge cases survive the crossing without silent data loss or
fabrication?

## Why it matters

The P1 article was a perfect 5 × 6 grid. **Real surveys are not.** Every one of the
conditions below is ordinary in production data, and each has a failure mode that is
silent by nature:

- A **duplicate index tuple** silently overwritten loses a trace and the loss is
  invisible in the output.
- **Grid padding** presented as sample data is fabrication (**SP12**) and looks exactly
  like a very quiet trace.
- A **sparsity check** that only passes because `MDIO_IGNORE_CHECKS` demoted it to a log
  line is not a check (**SP11**, §9.1).

## Method

Build a synthetic fixture per condition, deterministically, with a committed seed. Each
becomes a permanent fixture:

| Fixture | Condition |
|---|---|
| `dead_traces` | Live and dead traces interleaved; live mask must distinguish them |
| `duplicate_index` | Two traces with identical inline/crossline |
| `sparse_grid` | Grid with large unpopulated regions |
| `ragged_lines` | Inlines of differing crossline extent |
| `missing_lines` | Whole inlines absent from the middle of the range |
| `coord_scalar_zero` | Coordinate scalar `0` |
| `coord_scalar_pos` | Positive coordinate scalar (multiply) |
| `coord_scalar_neg` | Negative coordinate scalar (divide) |
| `byte_swapped` | Big-endian and little-endian variants of one file |
| `rev0_minimal` | rev 0, minimum viable header content |

For each: ingest, run all five planes, export, and compare.

## Pre-registered parameters

| Parameter | Value |
|---|---|
| Fixtures | 10, listed above, synthetic and committed-generator-produced |
| Seed | `20260822` |
| N traces per fixture | ≤ 200 — these probe correctness, not scale |
| Comparison | Exact. **No tolerance.** |
| Barred | `MDIO_IGNORE_CHECKS` must be **absent**; `sdip doctor` runs first |

## Falsifier

Any one of:

- **Any silent overwrite of a duplicate.** Duplicates must be *surfaced* (§4.6).
- **Any padding leaking into Plane 4.** Padding is not data (**SP12**).
- **Any sparsity handling that depends on a suppressed check.**
- Any live/dead mask that cannot distinguish a measured zero trace from padding.

## If it fires

The affected condition is named on every certificate for data that could contain it,
and D5 stays open. A duplicate-overwrite failure is the most serious of the five: it is
data loss, not a labelling problem.
