# P34 — Hostile in five ways at once: the five-class combinations, seeded, under a 2 h cap (D8)

> **SP9.** Committed **before** the run. Sections above the results separator are never edited.

| Field | Value |
|---|---|
| Probe | `P34` |
| Status | `REGISTERED` |
| Registered | 2026-11-05 |
| Registered by | Claude Code session, on GeoSuite's order of 2026-11-05 ("D8's five-way fuzz round at a 2 h cap") |
| Related debt | `OPEN_DEBTS.md` D8, NARROWED 2026-11-05 (P29): "five-way and larger combinations" open |
| Spec clause | §11.4; operating contract §3.6 |

## Question

Is every `sdip` command still clean (P15's six clauses) when a file is hostile in **five**
independent ways at once?

## Method

1. **Population.** Every unordered five-member combination of `MUTATIONS` from five
   **different** classes: **6,496** (7 classes, 23 members). The set is committed as `FIVES` in
   `tests/fixtures/generators/hostile.py`, with a test that holds its size.
2. **Order.** `FIVE_ORDER`, a permutation of `FIVES` by
   `numpy.random.default_rng(20261105).permutation`. A capped run is then a uniform sample, not
   the head of `combinations` order.
3. **Cap: 7,200 s** of wall clock, as ordered. P29 measured 1.64 s per file, so about 4,400 are
   expected to run, not all 6,496. When the cap is reached the run stops, and the count that
   ran is the N reported, as P18 registered its caps.
4. Each file goes through the unchanged D8 child (library ingest, then CLI `ingest`, `verify`,
   `export`, `certify`) against the positive control's store, and is judged by P15's
   `falsifier_hits`.
5. **Gate placement, fixed now.** The first 10 of `FIVE_ORDER` join the default suite; the
   rest are `campaign`.
6. Run at the registration commit's code, from a clean worktree.

## Pre-registered parameters

| Parameter | Value |
|---|---|
| N | 6,496 registered; the run stops at the cap |
| Seed | 20261105 |
| Cap | 7,200 s |
| Per-file timeout, memory ceiling | 300 s, 512 MiB (the D8 harness's) |
| Environment | locked environment, `multidimio` 1.2.1, `segy` 0.6.0, this host (macOS arm64) |

## Falsifier

Any five-way file meets any of P15's six clauses.

## Reported, not gated

- Outcome counts: SDIP-typed refusal, MDIO grid refusal, converted.
- Each converted file's `certify` exit code. A converted file whose `certify` exits 1 is
  diagnosed through the `sdip` executable, as P29's nine were. A cause outside D54, D55, D61
  and D71–D73 is a new finding, recorded and asked about (§9), not fixed in this probe.

## If it fires

The firing file becomes a permanent default-suite test, as the negative control for its fix.
D8 stays OPEN.

## If it does not fire

D8's "five-way" item is measured over the N that ran: a uniform sample of 6,496, or all of them
if the cap allows. Six- and seven-way combinations, coverage-guided fuzzing, x86-64 and Windows
stay open.

---

## Results — *appended after the run, never edited into the sections above*

| Field | Value |
|---|---|
| Run date | 2026-11-05 |
| Run commit | `a0fdf48`, the registration commit, from a clean `git worktree` |
| Receipt | `prereg/P34-receipt-2026-11-05.json`: every record, and the classification of both `certify` failures |
| Environment | `multidimio` 1.2.1 · `segy` 0.6.0 · CPython 3.12.13 · macOS arm64 |
| Verdict | **The falsifier did not fire.** 0 of 5,289 files met any clause |

### Measured

| Registered | Ran | Cap | Elapsed | Clauses hit |
|---:|---:|---:|---:|---:|
| 6,496 | **5,289** (cap reached) | 7,200 s | 7,201.2 s | **0** |

The cap was reached, so the N is **5,289**: the first 5,289 of `FIVE_ORDER`, which is a uniform
sample of the 6,496 (81 %). The 1,207 not reached are listed in no record and are unmeasured.
- **5,261** SDIP-typed refusals (`UntrustedInputError`).
- **26** MDIO grid refusals: 17 `GridTraceSparsityError`, 9 `GridTraceCountError`.
- **2** converted.
- Slowest 20.89 s; max peak RSS 240.1 MB, under the harness's 512 MiB.

### `certify` on the 2 converted files

Both exited 1. Each was rebuilt at `a0fdf48` and run through the `sdip` executable, as P29's
were. **Both are D54:**
- Plane 4 fails on the 32,767 us interval, so the certificate is NON-EQUIVALENT.
- Both also carry `revision_undefined`, so G3 is ROUNDTRIP-SCOPED (D61).
- G7 refuses controls on the unclean baseline, as in P29.

Nothing passed falsely, and nothing is new.

### Scope

- One 30-trace poststack base file, revision 1, macOS arm64.
- 1,207 five-way files are unmeasured.
- Not run: six- and seven-way combinations, and coverage-guided fuzzing. x86-64 and Windows are
  unmeasured.
