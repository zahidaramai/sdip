# P22 — The rest of P18: 877 triples and 312 mutants (D8)

> **SP9.** Committed **before** the run. The commit is local only: GeoSuite pushes under its own
> approval. Sections above the results separator are never edited.

| Field | Value |
|---|---|
| Probe | `P22` |
| Status | `REGISTERED` |
| Registered | 2026-11-01 |
| Registered by | Claude Code session, on GeoSuite's order under owner D-216 |
| Related debt | `OPEN_DEBTS.md` D8, residual 3 (P18 ran 300 of 1,177 triples and 88 of 400 mutants) |
| Spec clause | §11.4; operating contract §3.6 |

## Question

Do the triples and mutants P18 did not reach meet any of P15's six clauses? And now that
D71–D73 are fixed, does any converted file still certify NON-EQUIVALENT?

## Method

- **Triples:** every member of `TRIPLES` not in `TRIPLE_SAMPLE`, in `TRIPLES` order. **N = 877.**
  Composition as P15/P18. **Cap 2,700 s.** P18 measured 2.1 s per triple, so about 1,850 s is
  expected.
- **Mutants:** `build_mutant(i)` for `i = 88..399`, P18's seeds (`20261031 + i`). **N = 312.**
  **Cap 9,000 s.** P18 measured about 27 s per mutant, because most convert and run the full
  `certify` chain, so about 8,500 s is expected.
- Each file runs through the unchanged D8 child (library ingest, CLI `ingest`, `verify`,
  `export`, `certify`) and is judged by P15's `falsifier_hits`. A cap reached stops that set; the
  count that ran is the N reported.
- Run at the registration commit's code: `main` `a56a1fa` (D71, D72, D73 in).

## Falsifier

Any file meeting any of P15's six clauses.

## Reported, not gated

- Each converted file's `certify` exit code. For any converted file whose `certify` exits 1, the
  cause is diagnosed through the `sdip` executable, as P18's 24 were. A cause outside D71–D73 is
  a new finding, recorded and asked about (§9), not fixed in this probe.
- Outcome counts: SDIP-typed refusal, MDIO grid refusal, converted.

## If it fires

The firing file becomes a permanent default-suite test, as the negative control for its fix.
D8 stays OPEN.

## If it does not fire

D8 residual 3 is measured over all 1,177 triples (P18 + P22), and over all 400 registered
mutants if the cap allows. Coverage-guided fuzzing and four-way combinations stay unmeasured.
D8 stays OPEN for those and for x86-64/Windows.

---

## Results — *appended after the run, never edited into the sections above*

| Field | Value |
|---|---|
| Run date | 2026-11-01 |
| Run commit | `d78d257`, clean tree (code identical to `main` `a56a1fa`). Registration at `d78d257`, before the run |
| Receipt | `prereg/P22-receipt-2026-11-01.json`: every record, and the classification of every `certify` failure |
| Environment | `multidimio` 1.2.1 · `segy` 0.6.0 · CPython 3.12.13 · macOS arm64 |
| Verdict | **The falsifier did not fire.** 0 of 1,189 files met any clause |

### Measured

| Set | Registered | Ran | Cap | Elapsed | Clauses hit |
|---|---:|---:|---:|---:|---:|
| Triples | 877 | **877** | 2,700 s | 1,734.1 s | **0** |
| Mutants | 312 | **312** | 9,000 s | 8,527.0 s | **0** |

Neither cap was reached, so every registered file ran.

- **Triples:** 835 SDIP-typed refusals, 18 `GridTraceSparsityError`, 13 `GridTraceCountError`,
  11 converted. Slowest 28.25 s. Max peak RSS 249.6 MB.
- **Mutants:** 310 converted, 1 SDIP-typed refusal, 1 `GridTraceCountError`. Slowest 31.18 s.
  Max peak RSS 254.8 MB.

With P18, D8 residual 3 is now measured over **all 1,177 triples and all 400 registered
mutants**: 0 of 1,577 met any clause.

### `certify` on the converted files

| Set | Converted | `certify` exit 0 | `certify` exit 1 |
|---|---:|---:|---:|
| Triples | 11 | 2 | 9 |
| Mutants | 310 | 293 | 17 |

Each of the 26 exits was diagnosed through the `sdip` executable: `certify` rerun in a clean,
empty git repository and its certificate's planes read, then `ingest` and `export --source`, with
the export diffed against the source byte by byte. **Every cause is an already recorded
upstream limit. None is D71, D72 or D73, and none is new:**

| Cause | Files | Certificate | Record |
|---|---:|---|---|
| A mutated coordinate scalar (bytes 71–72) on a trace other than the first. MDIO applies trace 0's scalar to every trace, so the stored `cdp_x`/`cdp_y` for that cell is not the source's scaled value. Plane 3 fails | 16 mutants | NON-EQUIVALENT | D55, closed as a permanent Plane 3 failure |
| A binary-header sample interval that is not a whole millisecond (32,767 us in `sample_interval_enormous`; 20,640 us in `mutant_337`). MDIO stores the axis as `int32` milliseconds, so `[0, 20.64, 41.28, ...]` is stored as `[0, 20, 41, ...]`. Plane 4 fails | 6 triples, 1 mutant | NON-EQUIVALENT | D54, closed as a permanent Plane 4 failure |
| `revision_undefined` in the triple. Ingest passes every plane; MDIO refuses the export (`InvalidMDIOError: Missing revision keys from binary header`), so there is no round trip | 3 triples | PROVISIONAL (G3 round-trip-scoped, D-0106) | D61 |

In all 26 the engine refused to certify. Nothing passed falsely. 20 of the 26 exports are
byte-identical to their source: the failures are in the forward planes, not the round trip.

**D71 and D72 at scale.** In P18, 24 of 87 converted mutants failed G3 because export wrote 0
over unassigned binary-header bytes or wrote traces in grid order. In P22, **0 of 310**
converted mutants failed for either cause.

### Scope

- One 30-trace poststack file, revision 1, macOS arm64.
- Not coverage-guided. No four-way combinations. x86-64 and Windows unmeasured.
- The 26-file classification is a diagnosis made after the run, as the registration asked. It
  is not a gated criterion.
