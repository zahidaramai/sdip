# P29 — Hostile in four ways at once: every four-class combination (D8)

> **SP9.** Committed **before** the run. The commit is local only: GeoSuite pushes under its own
> approval. Sections above the results separator are never edited.

| Field | Value |
|---|---|
| Probe | `P29` |
| Status | `REGISTERED` |
| Registered | 2026-11-05 |
| Registered by | Claude Code session, on GeoSuite's RESUME order of 2026-11-05 (work D8) |
| Related debt | `OPEN_DEBTS.md` D8, NARROWED 2026-11-01 (P22): "four-way combinations" still open |
| Spec clause | §11.4; operating contract §3.6 |

## Question

Is every `sdip` command still clean (P15's six clauses) when a file is hostile in **four**
independent ways at once?

## Method

1. **Population.** Every unordered four-member combination of `MUTATIONS` from four
   **different** classes, in `itertools.combinations` order: **N = 3,632** (7 classes, 23
   members). Composition is P15's layer order, through the unchanged `build_combination`.
   The set is committed as `QUADS` in `tests/fixtures/generators/hostile.py`, with a test that
   holds its size.
2. **Every member runs**, not a sample. **Cap 10,800 s** of wall clock. P22 measured 2.0 s per
   triple, so about 7,300 s is expected. If the cap is reached, the run stops, and the count that
   ran is the N reported.
3. Each file goes through the unchanged D8 child (library ingest, then CLI `ingest`, `verify`,
   `export`, `certify`) against the positive control's store, and is judged by P15's
   `falsifier_hits`.
4. **Gate placement, fixed now.** The first 10 members of `QUADS` join the default suite;
   the rest are `campaign`.
5. Run at the registration commit's code.

## Pre-registered parameters

| Parameter | Value |
|---|---|
| N | 3,632 |
| Cap | 10,800 s |
| Per-file timeout, memory ceiling | 300 s, 512 MiB (the D8 harness's) |
| Environment | locked environment, `multidimio` 1.2.1, `segy` 0.6.0, this host (macOS arm64) |

## Falsifier

Any four-way file meets any of P15's six clauses.

## Reported, not gated

- Outcome counts: SDIP-typed refusal, MDIO grid refusal, converted.
- Each converted file's `certify` exit code. A converted file whose `certify` exits 1 is
  diagnosed through the `sdip` executable, as P22's 26 were. A cause outside D54, D55, D61 and
  D71–D73 is a new finding, recorded and asked about (§9), not fixed in this probe.

## If it fires

The firing file becomes a permanent default-suite test, as the negative control for its fix.
D8 stays OPEN.

## If it does not fire

D8's "four-way combinations" item is measured over all 3,632. Coverage-guided fuzzing, x86-64
and Windows stay open, and D8 stays OPEN for them.

## Not in this probe

Five-, six- and seven-way combinations. One 30-trace poststack base file, revision 1.

---

## Results — *appended after the run, never edited into the sections above*

| Field | Value |
|---|---|
| Run date | 2026-11-05 |
| Run commit | `6f2e057`, the registration commit, from a clean `git worktree` |
| Receipt | `prereg/P29-receipt-2026-11-05.json`: every record, and the classification of every `certify` failure |
| Environment | `multidimio` 1.2.1 · `segy` 0.6.0 · CPython 3.12.13 · macOS arm64 |
| Verdict | **The falsifier did not fire.** 0 of 3,632 files met any clause |

### Measured

| Registered | Ran | Cap | Elapsed | Clauses hit |
|---:|---:|---:|---:|---:|
| 3,632 | **3,632** | 10,800 s | 5,944.6 s | **0** |

The cap was not reached, so every registered file ran.
- **3,575** SDIP-typed refusals (`UntrustedInputError`).
- **48** MDIO grid refusals: 32 `GridTraceSparsityError`, 16 `GridTraceCountError`.
- **9** converted.
- Slowest 41.37 s; max peak RSS 243.2 MB, under the harness's 512 MiB.

### `certify` on the 9 converted files

All 9 exited 1. Each was rebuilt at `6f2e057` and run through the `sdip` executable:
`certify` in a clean, empty git repository, with its certificate's planes, gates and G7 read.
**Every cause is an already recorded upstream limit. None is new:**

| Cause | Files | Certificate | Record |
|---|---:|---|---|
| `sample_interval_enormous`: a binary-header interval of 32,767 us, stored as whole milliseconds (`32.767` → `32.0`). Plane 4 fails | 7 | NON-EQUIVALENT | D54 |
| `revision_undefined` without the interval mutation: every plane passes; MDIO will not export | 2 | PROVISIONAL (G3 ROUNDTRIP-SCOPED, D-0106) | D61 |

Five of the seven D54 files also carry `revision_undefined`, so their G3 is ROUNDTRIP-SCOPED as
well. **G7 reports FAIL on the seven D54 files** with "baseline is not clean - clean store
already fails G2d". G7 refuses to run its controls on a store that already fails a plane. That
is its design, not a finding. In all nine the engine refused to certify, and nothing passed
falsely.

### Scope

- One 30-trace poststack base file, revision 1, macOS arm64.
- Not coverage-guided. Five-way and larger combinations are not run. x86-64 and Windows are
  unmeasured.
- The nine-file classification is a diagnosis made after the run, as the registration asked. It
  is not a gated criterion.
