# P21 — Where the 3-D sparsity bound sits, and what each side of it does (D30)

> **SP9.** Committed **before** the run. The commit is local only: GeoSuite pushes under its own
> approval. Sections above the results separator are never edited.

| Field | Value |
|---|---|
| Probe | `P21` |
| Status | `REGISTERED` |
| Registered | 2026-10-31 |
| Registered by | Claude Code session, on GeoSuite's order under owner D-216 ("D30 first") |
| Related debt | `OPEN_DEBTS.md` D30 |
| Spec clause | §9.1 (barred settings), §11.4, §12 SP12 |

## Question

P5 measured two points: ratio 3.0 converts and ratio 12.0 is refused. Where exactly is the
bound? Does every grid on the accepted side certify, and is every grid on the refused side
refused cleanly? Is there any route past the bound that SDIP may take?

## What is known before the run (read from source, not measured)

The pinned `multidimio` 1.2.1 (`mdio/ingestion/grid_qc.py`) computes
`ratio = (grid cells) / (traces)` and raises `GridTraceSparsityError` when `ratio > limit`, where
`limit` is `MDIO__GRID__SPARSITY_RATIO_LIMIT` (default 10). It warns above
`MDIO__GRID__SPARSITY_RATIO_WARN` (default 2). Both settings are barred: they are in
`sdip._pins.UPSTREAM_SETTINGS`. So the only route past the bound that SDIP may not take is the
setting, and any other route would have to change the grid, which is processing (§1.3).

## Members (fixed now)

Each is written by `make_irregular` (`tests/fixtures/generators/irregular.py`, seed 20260822,
revision 1, 32 samples) from explicit index pairs. The grid is the unique inlines × the unique
crosslines.

| Member | Index pairs | Inlines × crosslines | Traces | Ratio | Expected side |
|---|---|---|---:|---:|---|
| `below_9_09` | diagonal 1..10, plus (1, 2) | 10 × 10 | 11 | 9.091 | accepted |
| `diag_10_00` | diagonal 1..10 | 10 × 10 | 10 | 10.000 | accepted (`>` is strict) |
| `swath_L36_w4` | inline i, crosslines i..i+3, i = 1..36 | 36 × 39 | 144 | 9.750 | accepted |
| `diag_10_08` | diagonal 1..11, plus (1, 2) | 11 × 11 | 12 | 10.083 | refused |
| `swath_L40_w4` | inline i, crosslines i..i+3, i = 1..40 | 40 × 43 | 160 | 10.750 | refused |
| `swath_L40_w3` | inline i, crosslines i..i+2, i = 1..40 | 40 × 42 | 120 | 14.000 | refused |
| `diag_100` | diagonal 1..100 | 100 × 100 | 100 | 100.000 | refused |

The swaths are the realistic shape: a narrow oblique acquisition strip whose bounding grid is
mostly empty.

## Method

Each member runs through the `sdip` executable at defaults (`--revision 1`, `PostStack3DTime`):
`ingest --json`, then for an accepted member `verify --json` and `certify` (in a clean empty
repository). For a refused member, `verify` and `certify` are also run, to show they refuse too.

## Pass criteria (all must hold)

1. **Accepted side** (`ratio ≤ 10`): ingest exit 0, verify PASS, and certify EQUIVALENT, with the
   only release blocker being G5 NOT_RUN (no ceilings declared). Plane 5 verifies the padding
   (SP12).
2. **Refused side** (`ratio > 10`): ingest exit 1, 0 bytes on stdout, one stderr line naming
   `GridTraceSparsityError`, no traceback, no store left carrying a provenance marker. verify
   and certify exit non-zero, with no traceback and no exit 3.
3. **The barred settings stay barred:** `sdip doctor` PASS with both `MDIO__GRID__*` settings in
   the classified list. Setting either one makes ingest refuse (exit 2) before reading the file.

## Falsifier

Any member landing on the side other than its expected one, or any criterion not holding.

## If it fires

A wrong-side member means the bound is not what the source says. That is recorded and asked
about (§9), not routed around. An unclean refusal becomes a permanent corpus test with its fix.

## If it does not fire

D30 is a measured hard limit: ratio ≤ 10 accepted and certified, ratio > 10 refused cleanly,
and no permitted route past it. Whether that **closes** D30 as an accepted limit, or keeps it open
for a future upstream change, is a ruling, asked for in the report.

---

## Results — *appended after the run, never edited into the sections above*

| Field | Value |
|---|---|
| Run date | 2026-10-31 |
| Run commit | `0e0761d`, clean tree. Registration at `b6d833f`, before the run |
| Receipt | `prereg/P21-receipt-2026-10-31.json`: every member's ingest, verify and certify, doctor, the barred-setting run |
| Verdict | **Every member landed on its registered side.** Criterion 2 **fired** before a CLI fix (a refusal spanned five stderr lines) and holds after it. Criteria 1 and 3 hold |

### Measured

| Member | Ratio | Ingest | Verify | Certify | Plane 5 padding |
|---|---:|---|---|---|---|
| `below_9_09` | 9.091 | exit 0 | PASS | **EQUIVALENT** (only G5 NOT_RUN) | verified, 89 cells |
| `diag_10_00` | 10.000 | exit 0 | PASS | **EQUIVALENT** (only G5 NOT_RUN) | verified, 90 cells |
| `swath_L36_w4` | 9.750 | exit 0 | PASS | **EQUIVALENT** (only G5 NOT_RUN) | verified, 1,260 cells |
| `diag_10_08` | 10.083 | **exit 1**, 0 B stdout, 1 `sdip:` line | exit 2 (no store) | exit 1, same line | — |
| `swath_L40_w4` | 10.750 | **exit 1**, likewise | exit 2 | exit 1 | — |
| `swath_L40_w3` | 14.000 | **exit 1**, likewise | exit 2 | exit 1 | — |
| `diag_100` | 100.000 | **exit 1**, likewise | exit 2 | exit 1 | — |

- No traceback and no exit 3 anywhere. No refused member left a store carrying a provenance
  marker.
- The refusal names the ratio: `sdip: UpstreamRefusal: GridTraceSparsityError raised in
  mdio/ingestion/grid_qc.py:69: … Sparsity ratio: 10.08 …`.
- **The bound is `ratio > 10`, strict.** 10.000 is accepted and 10.083 is refused, as the source
  says.
- **Criterion 3:** `sdip doctor` PASS ("all 12 environment variables the installed upstream
  reads are classified"). With `MDIO__GRID__SPARSITY_RATIO_LIMIT=1000` set, ingest exits **2**
  before reading the file (`BarredEnvironmentError`), and no store is created.

### Criterion 2 fired first, and what fixed it

At the registration commit, every refused member's `sdip:` line was followed by **four
continuation lines**, because MDIO's exception message carries its own line breaks. The README
promises one `sdip: <ErrorName>: <reason>` line, and consumers parse by line (GeoGIS's intake
does). The CLI boundary now writes every refusal through one helper that joins the message's
breaks with spaces (`0e0761d`). The four refused-side tests in
`tests/integration/test_d30_sparsity_bound.py` failed before it and pass after. They are the
permanent control.

### What D30 now is

A **measured hard limit**:
- ratio ≤ 10 is accepted and certifies;
- ratio > 10 is refused cleanly, in one line, by every command;
- the only route past it is a barred setting, and it is refused.

A real oblique 3-D swath sparser than about 1 in 10 of its bounding grid cannot be ingested by
SDIP at these pins. Changing the grid to fit would be processing (§1.3). Whether that **closes**
D30 as an accepted limit is a ruling, asked for in the report.

### Scope

Synthetic poststack 3-D grids, 10–160 traces, revision 1, one template, macOS arm64. The bound
is upstream's at `multidimio` 1.2.1; a pin bump could move it.
