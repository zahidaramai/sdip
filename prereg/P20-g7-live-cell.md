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

| Field | Value |
|---|---|
| Run date | 2026-10-31 |
| Run commit | `aa0b68b`, clean tree. Registration at `e171443`, before the build |
| Receipt | `prereg/P20-receipt-2026-10-31.json`: every store's verdict, plane statuses, control outcomes and targets; the P19 comparison; the 2-D line below |
| Verdict | **All five pass criteria hold.** Criterion 5 is the gate on the records commit |

### Measured against the pass criteria

| # | Criterion | Result |
|---|---|---|
| 1 | the three affected mutants: G7 PASS, live targets | **Yes.** `mutant_039`, `_058` and `_080` (cell `(0, 0)` is padding in each): every control PASS. Targets `[0,5]`, `[0,3]` and `[0,1]` respectively, all live |
| 2 | all 26: controls PASS or N/A; verdicts kept or corrected; G3, closure and planes unchanged | **Yes.** 26 of 26 EQUIVALENT, all five planes PASS on every store, no control failing. Against P19, only those three verdicts moved (NON-EQUIVALENT → EQUIVALENT). G3 and closure are identical on all 26 |
| 3 | R: EQUIVALENT, G7 PASS | **Yes** |
| 4 | invariance on R | **Yes.** Targets `(0,0)` for the four single-cell controls; `(0,0)` and `(0,1)` for `transposed_traces`, exactly the old fixed cells |
| 5 | full default suite | the gate on the records commit |

### An observation outside the registration: a real 2-D line

On the same day, GeoGIS's first intake run fed SDIP a real Volve arbitrary line:
`volve10r12-full-twt-arb.sgy`, 822,600 B, 225 traces, SHA-256 `75a4bae9…af44`. It was declared
`--revision 1 --template PostStack2DTime --override overrides/rev1-cdp-alias.toml`. Its grid is
**1-D**.
- **At `403fefb`:** `certify` was NON-EQUIVALENT. `transposed_traces` raised `IndexError: too
  many indices for array: array is 1-dimensional, but 2 were indexed`, because the old control
  hard-coded the 2-D cells `(0,0)` and `(0,1)`. That is D73's class: a control that assumes the
  grid's shape.
- **At `aa0b68b`:** EQUIVALENT. `transposed_traces` swaps `[0]` and `[1]`, and G7 passes (15
  applied, 3 not applicable). G3 is `ROUNDTRIP-SCOPED` under D-0098 (two non-printable textual
  characters, so no export). The only blocker is G5 NOT_RUN.

This is one real file, not a registered population. It is recorded because it shows that the
same defect reached real data in a second form.

### Scope

26 synthetic stores (30 traces each), one published reference, and one real 2-D line, on macOS
arm64. The two controls that still name a fixed index (`inverted_live_mask`, which fails its
gate on either value, and the dense-layout branch of `flipped_raw_ibm32_word`, a legacy layout)
were outside this change and are unchanged.
