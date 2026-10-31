# P20 — G7's controls target the first live cell (D73)

> **SP9.** Committed **before** the build and the run. The commit is local only: GeoSuite
> pushes under its own approval. Sections above the results separator are never edited.

| Field | Value |
|---|---|
| Probe | `P20` |
| Status | `REGISTERED` |
| Registered | 2026-10-31 |
| Authority | The owner, in session: "Approve the fix", answering the D73 question. Matches GeoSuite's ruling of the same day |
| Related debt | `OPEN_DEBTS.md` D73 |
| Spec clause | §7 G7; operating contract §5 (both halves, D-0088) |

## Question

If the five controls that hard-code grid cell `(0, …, 0)` target the first **live** cell
instead, do correct stores whose cell 0 is padding pass G7? And does every store that passed
before keep exactly its verdict?

## What is built (fixed now)

- `flipped_header_byte`, `flipped_sample_bit`, `flipped_raw_header_byte` and
  `corrupted_cdp_coordinate` corrupt the **first live cell**: `trace_mask` true, in C order.
  For `cdp_x` that is the cell projected onto the array's own dimensions.
- `transposed_traces` swaps the **first two live cells**.
- Each control returns the cell or cells it wrote, and the certificate records them per
  control (`target`, additive in schema v0).
- No other control changes.
- **Invariance by construction:** when cells `(0, …, 0)` and `(0, …, 1)` are both live, the
  first two live cells *are* those cells, so the controls write exactly the bytes they wrote
  before. A unit test pins this.

## Method

1. **Population A: the 26 stores of P19**, the 23 eligible mutants plus B1, B2, B3, each
   certified with `sdip certify` in a clean empty repository by the new code. The three
   affected stores are among them: `mutant_039`, `mutant_058`, `mutant_080`.
2. **Population R: the published reference certificate's source**, `make_poststack3d` at
   defaults (the 30-trace reference, SHA-256 `be4ce437…dd762`), certified by the new code.

## Pass criteria (all must hold)

1. **The three affected mutants:** every applicable G7 control PASS, and G7 PASS. Each of the
   five changed controls records a target cell that is live.
2. **All 26:** every control PASS or not-applicable. Verdicts:
   - the 20 that were EQUIVALENT under P19 stay EQUIVALENT;
   - the 3 affected ones become EQUIVALENT, unless another blocker is named;
   - no store's G3, closure or plane statuses change from P19.
3. **R:** EQUIVALENT, G7 PASS, as the published certificate records.
4. **Invariance:** on R (full grid), the five controls' recorded targets equal the old fixed
   cells `(0, 0)` (and `(0, 1)` for the transpose).
5. **The full default suite passes.**

## Falsifier

Any pass criterion not holding.

## If it fires

The failing store is recorded. The cause is fixed on the branch if it is inside this design;
otherwise it is stopped and asked about. `main` does not move until all five hold.

---

## Results — *appended after the run, never edited into the sections above*
