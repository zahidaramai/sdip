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
