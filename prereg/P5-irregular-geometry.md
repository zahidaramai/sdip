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

---

## Results

*Everything below this separator was appended after the run. Nothing above it was edited.*

### Run record

| Field | Value |
|---|---|
| Run date | 2026-08-22 |
| Executed by | `tests/integration/test_p5_geometry.py` — 60 tests, all passing |
| Generator | `tests/fixtures/generators/irregular.py`, seed `20260822` |
| Repository commit | `fbece9e` |
| Working tree | **dirty** (14 paths, concurrent probe work). A probe result is not a certificate, so this does not invalidate the measurement, but **no certificate may be issued from this run** (§11.3). |
| Python | 3.12.13, macOS 26.5.2, arm64 |
| Pins | `multidimio==1.2.1`, `segy==0.6.0` — both verified by `sdip doctor` |
| Other | `zarr` 3.3.0, `xarray` 2026.7.0, `numpy` 2.5.2, `dask` 2026.7.1 |
| Template | `PostStack3DTime` for every fixture |

`sdip doctor` ran first, as the pre-registration requires: **7 of 8 checks PASS**, including
`barred-env-vars: none of 2 barred variables are set`. The single FAIL is `working-tree`, above.

**`MDIO_IGNORE_CHECKS` was absent for the entire run.** It is asserted absent by the module-scoped
fixture before any file is built, re-asserted after the run, and re-asserted a third time
immediately after the one condition that could have been made to pass by setting it. No test reads
or sets it; the assertion goes through `sdip.guard.env.check_barred_env_vars`.

Reproduce with:

```
uv run sdip doctor
uv run pytest tests/integration/test_p5_geometry.py -q
```

### Per-fixture results

All ten fixtures are ≤ 200 traces, 16 samples per trace, deterministic (asserted: two builds are
byte-identical). "Planes" is Plane 1 to Plane 5 in order; "G3" is whole-file SHA-256 identity.

| Fixture | Traces | Cells | Padding | Ingested | Planes | G3 | Outcome |
|---|---|---|---|---|---|---|---|
| `dead_traces` | 80 | 8×10 | 0 | yes | PASS ×5 | PASS | 27 measured-zero traces, all live in the mask |
| `duplicate_index` | 30 | 5×6 | — | **no** | — | — | `GridTraceCountError: 29 != 30` |
| `sparse_grid` | 27 | 9×9 | 54 | yes | PASS ×5 | PASS | sparsity ratio 3.0, log warning only |
| `ragged_lines` | 32 | 5×10 | 18 | yes | PASS ×5 | PASS | line lengths 10, 4, 7, 2, 9 |
| `missing_lines` | 42 | 7×6 | 0 | yes | PASS ×5 | PASS | inlines 104-106 vanish from the axis |
| `coord_scalar_zero` | 20 | 4×5 | 0 | **no** | — | — | `ValueError: Invalid coordinate scalar: 0 for file revision SegyStandard.REV1` |
| `coord_scalar_pos` | 20 | 4×5 | 0 | yes | PASS ×5 | PASS | `+100` multiplies the derived coordinate arrays |
| `coord_scalar_neg` | 20 | 4×5 | 0 | yes | PASS ×5 | PASS | `-100` divides the derived coordinate arrays |
| `byte_swapped` (little) | 20 | 4×5 | 0 | **no** | — | — | `ValueError: 256 is not a valid DataSampleFormatCode` |
| `rev0_minimal` | 20 | 4×5 | 0 | **no** | — | — | `ValueError: Required fields ['cdp_x', 'cdp_y', 'crossline', 'inline'] for template PostStack3DTime not found in the provided segy_spec` |

Two controls outside the ten:

| Control | Result |
|---|---|
| `byte_swapped` big-endian twin, identical arguments | Ingests, Planes PASS ×5, G3 PASS. The little-endian failure is attributable to byte order alone. |
| Crooked line, 12 traces, 12 unique inlines × 12 unique crosslines, sparsity ratio 12.0 | `GridTraceSparsityError` — refused. See the sparsity note below. |

**Six of ten conditions convert. Four do not.** Where a store exists at all, every plane passes
exactly and the round trip is byte-identical, including on grids where more than half the cells are
padding: `sparse_grid` exports back to its exact 11,808 source bytes and `ragged_lines` to its
13,328.

### The duplicate index tuple — what actually happens

**The duplicate is refused, not overwritten.** This is the answer the probe existed to get.

Ordinal 11 is rewritten to claim ordinal 10's `(101, 204)`. The file holds 30 traces over 29
distinct cells. MDIO builds its grid, counts 29 live cells against the 30 traces the file declares,
and raises:

```
GridTraceCountError: 29 != 30. Scanned grid trace count (29) doesn't match SEG-Y file (30).
Either indexing parameters are wrong (not unique) or SEG-Y file has duplicate traces.
```

Nothing is written. The test asserts the output path does not exist afterwards, so there is no
store in which a trace could quietly go missing.

**The error type is as important as the refusal.** `MDIO_IGNORE_CHECKS` gates
`GridTraceSparsityError` in `mdio/ingestion/grid_qc.py` and **only** that one. `GridTraceCountError`
is raised unconditionally in `mdio/ingestion/segy/pipeline.py:112` with no settings lookup in the
path. The duplicate defence therefore does not depend on a suppressible check (**SP11**).

**The engine's own detection was measured too, not assumed.** Upstream refuses the duplicate today,
so Plane 5's duplicate logic would never be reached, and an undetected detector is not a detector.
The test builds the same geometry with the duplicate removed, ingests *that*, then runs Plane 5
against the **duplicate-bearing source** — exactly the situation a converter that overwrote
silently would produce. Plane 5 fails:

```
failed_checks : ["count_matches", "map_invertible", "no_duplicates"]
duplicate_cells: [{"cell": [1, 4], "source_ordinals": [10, 11]}]
source_trace_count: 30, live_cells_in_mask: 29
```

Both colliding ordinals are named. A duplicate is data loss, not a labelling problem, and the map
preserves the collision rather than resolving it.

### Padding — what regularisation puts in the invented cells

Measured on `sparse_grid`, 27 traces in an 81-cell grid:

| Array | Padding fill | Consequence |
|---|---|---|
| `amplitude` (float32) | `NaN` | Self-announcing: no sample in this fixture decodes to `NaN`. |
| `cdp_x`, `cdp_y` (float64) | `NaN` | Same. |
| `headers` (structured int) | **zero** | `inline == 0` at a padding cell is indistinguishable **by value** from an inline somebody numbered zero. |

Plane 4 compared **27 cells, not 81**; Plane 3 likewise. Plane 5 recorded `padding_cells: 54`.
Nothing invented reaches the export: G3 is byte-identical.

The header-padding row is the one to carry forward. A structured integer dtype cannot hold `NaN`, so
for the `headers` array the live mask is the only thing between a consumer and a fabricated index
value. That is not a defect in SDIP — Plane 3 and Plane 4 both use the mask — but any downstream
reader that ignores `trace_mask` will read 54 fabricated header rows as data (**SP12**).

### The live mask distinguishes a measured zero from padding

`dead_traces` is a **complete** 8×10 grid with 27 all-zero traces interleaved, so there is no
padding anywhere and every zero in the store is a zero somebody measured. All 80 cells are live and
Plane 4 compared all 80: a dead trace is checked, not skipped.

`sparse_grid` carries both conditions at once — measured zeros at ordinals 4 and 22 sit in the same
array as 54 cells nobody recorded. Measured:

- both zero traces map to cells where `trace_mask` is true, and their samples are exactly zero;
- neither is `NaN`;
- every cell where `trace_mask` is false is `NaN` throughout.

The mask separates them, and it separates them on the mask rather than on the values.

### Sparsity — bounded, and bounded by the check that is suppressible

`sparse_grid` has a sparsity ratio of 3.0: above MDIO's warn threshold (2.0), below its error
threshold (10.0). It converted, and the notice it produced is a **`logger.warning`, not a Python
warning** — the SP6 warning ledger recorded `observed: []` for the run. The certificate's
`warnings_raised[]` would be empty for a sparse store; the sparsity shows up instead as
`padding_cells` in Plane 5's evidence.

Above ratio 10 the picture changes. A crooked line — 12 traces, each with a unique inline *and* a
unique crossline, spanning a 144-cell grid — is refused with `GridTraceSparsityError`. **That is the
error `MDIO_IGNORE_CHECKS` demotes to a log line**, and it is the single place in this probe where
the barred variable would make a failure disappear.

It was not set. The correct reading of the result is that SDIP cannot ingest grids sparser than
ratio 10, not that the check should be switched off. A 2D line or a crooked-line survey indexed on
inline and crossline falls in this category.

### Coordinate scalars

| Scalar | Ingest | Header `cdp_x` | Store `cdp_x` array |
|---|---|---|---|
| `0` | refused | — | — |
| `+100` | ok | 1,005,000 | 100,500,000.0 (× 100) |
| `-100` | ok | 1,005,000 | 10,050.0 (÷ 100) |

The multiply/divide convention is implemented correctly. The raw header value is untouched, so
Plane 3 passes and G3 is byte-identical.

Two findings sit here:

1. **Scalar `0` cannot be ingested at rev 0 or rev 1.** `mdio/segy/scalar.py` accepts `abs(scalar)`
   in `{1, 10, 100, 1000, 10000}` and normalises `0` to `1` **only for rev 2 and above**. A zero
   coordinate scalar is left undefined by the earlier standards and is written constantly in
   practice, so this closes off a large class of real files.
2. **The scaled coordinate arrays are an undeclared transform.** `cdp_x` and `cdp_y` in the store
   hold values that appear nowhere in the source, while the certificate's `transforms_declared[]`
   names only the sample-format decode. Under **SP1** the permitted transform is the *declared* one.
   Nothing is lost and nothing is wrong with the arithmetic; the gap is in what the certificate
   says.

*Read from source, not measured:* `_get_coordinate_scalar` reads the scalar from **trace 0 only**
and applies it to every trace. A file whose traces carry differing scalars would be scaled by the
first one. No fixture in this probe tests that, and it is stated here as an inference from
`mdio/segy/scalar.py`, not as a result.

### Byte order

The little-endian variant fails because `build_gap_free_spec` inherits `endianness = big` from the
revision standard and `sdip.ingest.ingest` exposes no way to change it. The little-endian binary
header is then read big-endian, sample-format code `1` arrives as `0x0100`, and the conversion dies
on `256 is not a valid DataSampleFormatCode`.

**The blocker is SDIP's, not the format's and not upstream's.** The same file was read correctly in
the same test with `spec.endianness` set to `None`, which is how the pinned `segy` infers byte order
from the binary header: 20 traces, inlines `[100 101 102 103]`, crosslines `[200 201 202 203 204]`,
all correct. The big-endian twin of the identical geometry converts, passes five planes and round
trips byte-identically.

### Revision 0

Rev 0 fails at the **template**, not at the spec, and the distinction is the finding. G1 passes for
revision 0 — the gap-free spec covers all 240 bytes, which is what fillers are for. What rev 0 does
not have is a field *named* `inline`, `crossline`, `cdp_x` or `cdp_y`; those positions were
standardised later, and under a rev 0 spec they are `pad_181` through `pad_196`. `PostStack3DTime`
binds by field name, so it cannot bind. Reading rev 0 index values needs a spec that declares those
bytes, which `ingest` does not currently accept.

### Missing inlines

Inlines 104-106 are absent from the source and absent from the store's inline axis, which reads
`[100 101 102 103 107 108 109]`. The grid is **dense**: 42 traces, 42 cells, zero padding. Nothing
is fabricated, so **SP12** holds.

Nothing records the hole either. The store is indistinguishable from a survey that only ever had
seven inlines, and an interior gap in an inline range is exactly the shape of an acquisition
problem a reader would want to see. The inline axis is the only evidence, and it is evidence a
consumer has to think to look for.

### Verdict against the pre-registered falsifier

**The falsifier does NOT fire. All four clauses hold.**

| Clause | Verdict | Evidence |
|---|---|---|
| Any silent overwrite of a duplicate | **does not fire** | Refused at ingest with `GridTraceCountError: 29 != 30`; no store written. Surfaced a second time by Plane 5, which names both colliding ordinals on cell `[1, 4]`. Neither defence depends on a suppressible check. |
| Any padding leaking into Plane 4 | **does not fire** | Plane 4 compared 27 of 81 cells on `sparse_grid` and 32 of 50 on `ragged_lines`. Padding is `NaN` in `amplitude`, `cdp_x`, `cdp_y`. G3 byte-identical, so nothing invented reaches the export. |
| Any sparsity handling that depends on a suppressed check | **does not fire** | `MDIO_IGNORE_CHECKS` absent throughout, confirmed by `sdip doctor` and by three in-test assertions. Ratio 3.0 converts with a log line; ratio 12.0 is refused. Nothing was suppressed to obtain any result above. |
| Any live/dead mask that cannot distinguish a measured zero trace from padding | **does not fire** | Measured directly on `sparse_grid`: measured zeros are live and exactly zero, padding is not live and is `NaN` throughout. |

Two qualifications belong on the record with that verdict, neither of which is a falsifier hit:

- Clause 3 holds **at the ratios measured**. Sparse ingestion is bounded at ratio 10, and the only
  route past that bound is the barred variable — which is not a route SDIP may take.
- Clause 4 holds **on the mask**. The `headers` array's padding is zero-filled rather than
  `NaN`-filled, so for that array the mask is the sole discriminator.

### Scope of this measurement

Stated so nobody reads it as broader than it is:

- N is 20 to 80 traces per fixture, 16 samples each. **Correctness, not scale.** P3 remains open.
- One template (`PostStack3DTime`), poststack 3D only. Prestack is P7.
- Revisions 0 and 1 only. Revision coverage is P6.
- Sparsity was measured at ratios 1.0, 1.56, 3.0 and 12.0. Nothing between 3.0 and 12.0 was tested.
- One duplicate, one collision, two colliding ordinals. Multi-way collisions were not tested.
- Coordinate scalars `0`, `+100`, `-100`. The rest of `{1, 10, 1000, 10000}` and the rev 2 `0`
  normalisation path were not tested.
- Every fixture is synthetic and written by `SegyFactory`, so all ten are structurally
  well-formed. **A hostile or malformed irregular file is not covered here.**

### Findings requiring a maintainer decision

Raised, not decided — each is outside the authority of the probe that found it:

1. **Coordinate scalar `0` blocks ingestion at rev 0 and rev 1.** Common in real data. Any fix
   touches the ingest path and needs a ruling.
2. **Little-endian SEG-Y cannot be declared to SDIP.** The pinned `segy` can infer byte order; SDIP
   fixes it to big. Exposing that would be a change to the ingest API.
3. **Rev 0 index bytes cannot be bound by the stock template.** Needs either a spec-customisation
   path on `ingest` or a rev 0 template. Overlaps P6.
4. **Scaled `cdp_x`/`cdp_y` coordinate arrays are an undeclared transform (SP1).** The certificate's
   `transforms_declared[]` should name it, or the arrays should be recorded as derived.
5. **Grids sparser than ratio 10 cannot be ingested** without the barred variable. A 2D or
   crooked-line survey indexed on inline/crossline is in this class.
6. **Header padding is zero-filled, not `NaN`-filled.** A consumer ignoring `trace_mask` reads
   fabricated index values from `headers` (**SP12** exposure for downstream readers, not for SDIP's
   own planes).

Disposition of debt **D5** is left to a maintainer: the probe's own falsifier did not fire, but six
findings above bear on it, and four of the ten pre-registered conditions do not convert — one of
which, `duplicate_index`, is the correct refusal and the other three are limitations.

---

## Addendum — 2026-08-23, re-measured under the D8 preflight

Appended, not merged into the run above. The 2026-08-22 table records what was true on
2026-08-22; this records what changed and why. Nothing above this heading has been edited.

**What changed.** Closing debt D8 added `src/sdip/ingest/preflight.py`, which reconciles the binary
header's declared counts against the file size before any allocation and before upstream is called
(§11.4). **Exactly one of the ten conditions changed, and only in who refuses it.**

| Fixture | 2026-08-22 | 2026-08-23 |
|---|---|---|
| `byte_swapped` (little-endian) | `ValueError: 256 is not a valid DataSampleFormatCode`, raised inside `segy` | `UntrustedInputError`, raised by SDIP's own preflight |

The new message, measured rather than quoted:

```
UntrustedInputError: binary header (bytes 3217-3218) declares a sample interval of -24561
microseconds; the interval is a positive duration. Read little-endian the same bytes give
sample-format code 1 and 16 samples per trace, so this is most likely a little-endian SEG-Y.
SDIP reads SEG-Y as big-endian and does not guess byte order.
```

Read big-endian, the little-endian sample interval `4000` arrives as `-24561`, so preflight refuses
the file before the format-code check is reached. The other nine rows re-measured identically:
`duplicate_index` still `GridTraceCountError: 29 != 30`, `coord_scalar_zero` still
`Invalid coordinate scalar: 0 for file revision SegyStandard.REV1`, `rev0_minimal` still the missing
template fields, and the six converting conditions still convert. `MDIO_IGNORE_CHECKS` still absent.

**What did not change.** The verdict, all four falsifier clauses, and every finding above. A
little-endian SEG-Y still does not convert, and finding 2 — that the blocker is SDIP's own spec
asserting `endianness = big`, not the format and not upstream — is unaffected. The test's
independent evidence for it is untouched: `build_gap_free_spec(1).segy_spec.endianness.value` is
still asserted to be `"big"`, and the same file is still read correctly in the same test with
`spec.endianness = None`.

If anything the finding now reads more directly, because the refusal is SDIP's own typed error
naming the byte order rather than an untyped `ValueError` about a format code of 256.

**Bearing on finding 5 and the sparsity clause: none.** D8 deliberately did **not** re-type MDIO's
`GridTraceCountError` or `GridTraceSparsityError` inside SDIP, on the grounds that `DECISIONS.md`
D-0036 pins those types as the defence SDIP relies on. That is recorded as D8's open residual. The
duplicate result above therefore stands exactly as measured, including the argument that turns on
`GridTraceCountError` being raised unconditionally while only `GridTraceSparsityError` is gated by
the barred variable.

Re-measured by the P5 agent from a clean process, not accepted on report. `tests/integration/test_p5_geometry.py`: 60 passed. Two assertions in that
file were updated by the D8 agent to match, both citing `DECISIONS.md` D-0057.
