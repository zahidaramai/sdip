# P18 — Hostile in three ways at once, and a seeded byte-mutation search

> **SP9.** Committed **before** the run. The commit is local only: GeoSuite pushes under its own
> approval. Sections above the results separator are never edited.

| Field | Value |
|---|---|
| Probe | `P18` |
| Status | `REGISTERED` |
| Registered | 2026-10-31 |
| Registered by | Claude Code session, on GeoSuite's relay of owner D-216 |
| Blocks | nothing |
| Related debt | `OPEN_DEBTS.md` D8, residual 3 beyond pairs ("triples and mutation search") |
| Spec clause | §11.4; operating contract §3.6 |

## Question

Is every `sdip` command still clean (P15's six clauses) when a file is hostile in **three**
independent ways at once, or carries **random byte overwrites** in its structural headers?

## Why it matters

P15 showed that no pair of the D8 corpus's single hostilities breaks any command. The corpus is
hand-built: each member is a hostility someone thought of. A seeded mutation search reaches
values nobody chose. Example: a sample count that is plausible but wrong by a small amount,
combined with a trace header whose index fields disagree with it. Triples extend P15 one step.
Both are bounded samples, not proofs, and the scope says so.

## Method

### A — triples

1. **Population.** Every unordered triple of `MUTATIONS` members from three **different**
   classes: **1,177** triples (7 classes, 23 members). Composition is P15's layer order:
   trace-level, then truncation, then binary-header.
2. **Sample.** `numpy.random.default_rng(20261031).choice(1177, size=300, replace=False)` over
   the triples in `itertools.combinations` order. **N = 300.**
3. **Time cap: 1,800 s** of wall clock for the 300. If it is reached, the run stops, and the
   count that ran is the N reported.

### B — byte mutants

1. **Base.** The D8 well-formed 30-trace file.
2. **Mutant `i`**, for `i` in `0..399`: `rng = numpy.random.default_rng(20261031 + i)`.
   - `k = rng.integers(1, 9)` positions, drawn without replacement from the **structural
     bytes**: the binary header (file bytes 3200–3599) and the 240 header bytes of every
     trace.
   - Each chosen byte is overwritten with `rng.integers(0, 256)`.

   Textual-header and sample bytes are excluded. The textual header is never parsed for
   structure, and sample bytes are what Plane 4 judges, not §11.4. **N = 400.**
3. **Time cap: 2,400 s.** The same stop rule as A.

### Both

- Each file goes through the unchanged D8 child (library ingest, then CLI `ingest`, `verify`,
  `export`, `certify`) and is judged by P15's `falsifier_hits`.
- **Gate placement, fixed now.** The first 10 triples of the sample and mutants `0..9` join
  the default suite. Everything else is `campaign`.

## Pre-registered parameters

| Parameter | Value |
|---|---|
| N | 300 triples + 400 mutants, plus the positive control |
| Seed | 20261031 (triples sample); 20261031 + i (mutant i) |
| Caps | 1,800 s (triples), 2,400 s (mutants) |
| Per-file timeout, memory ceiling | 300 s, 512 MiB (the D8 harness's) |
| Environment | locked environment, `multidimio` 1.2.1, `segy` 0.6.0, this host (macOS arm64) |

## Falsifier

Any triple or mutant meets any of P15's six clauses.

## If it fires

Each firing file becomes a permanent default-suite test, as the negative control for its fix.
The defect is fixed on the branch. A fix that would change a gate or the Equivalence Contract is
stopped and asked about (§9). D8 stays OPEN.

## If it does not fire

D8 residual 3 narrows to "beyond this sample": 300 of 1,177 triples and 400 seeded mutants are
measured. Coverage-guided fuzzing and four-way combinations stay unmeasured. D8 stays OPEN for
those and for x86-64 and Windows.

---

## Results — *appended after the run, never edited into the sections above*

| Field | Value |
|---|---|
| Run date | 2026-10-31 |
| Run commit | `5aec2a0`, clean tree. Registration at `03a594b`, before the run |
| Receipt | `prereg/P18-receipt-2026-10-31.json`: every record, and the classification of every `certify` failure |
| Environment | `multidimio` 1.2.1 · `segy` 0.6.0 · CPython 3.12.13 · macOS arm64 |
| Verdict | **The falsifier did not fire.** 0 of 388 files met any clause |

### Measured

| Set | Registered | Ran | Cap | Elapsed | Clauses hit |
|---|---:|---:|---:|---:|---:|
| Triples | 300 | **300** | 1,800 s | 640.0 s | **0** |
| Mutants | 400 | **88** | 2,400 s | 2,400.4 s (cap reached before `mutant_088`) | **0** |

- **Triples:** 284 SDIP-typed refusals, 10 `GridTraceSparsityError`, 1 `GridTraceCountError`,
  5 converted. Max peak RSS 245.9 MB.
- **Mutants:** 87 converted, 1 SDIP-typed refusal. Max peak RSS 251.6 MB. Most random
  structural-byte overwrites leave a file that still converts, and each conversion runs the
  whole `certify` chain (about 27 s). That is why the cap stopped the mutant set at 88. By the
  registration, **N = 88** is what is reported.

### A finding outside the falsifier: `export` does not round-trip 24 of the 87 converted mutants

P18's clauses are about crashes and leaks, and none fired. But `certify` exited 1
(**NON-EQUIVALENT**) on 24 mutants that ingested with all five planes passing. Each was
re-ingested and exported with the `sdip` executable, and the export was diffed against the
source byte by byte:

| Cause | Mutants |
|---|---:|
| **Unassigned binary-header bytes come back as 0.** The source carries a nonzero byte at binary-header bytes 66, 97, 124, 227, 231, 249, 264, 266, 278, 279, 368, 390 or 400 (all unassigned in revision 1). The store holds it (Plane 2 PASS on the raw copy), and the export writes `0x00` | 12 |
| **Traces come back in grid order, not source order.** A mutated inline or crossline number puts the source out of grid order. Export writes the same 30 traces (identical multiset, identical file headers) in grid order | 12 |
| Export exits 2 (`mutant_022`: binary-header byte 306, the low byte of the extended-header count, changed) | 1 |

(One mutant has both of the first two causes, so the rows sum to 25 over 24 mutants.)

**G3 behaves correctly:** it fails, and the certificate says NON-EQUIVALENT. Nothing passes
falsely. What these show is that the round trip cannot reproduce two kinds of source that the
store itself holds faithfully. They are opened as debts **D71** and **D72**. The question goes
to the owner (operating contract §9, a gate failing). Nothing is fixed here.

### Scope

- 300 of 1,177 triples. 88 of 400 registered mutants (cap). One 30-trace poststack file,
  revision 1, macOS arm64.
- Not coverage-guided. No four-way combinations.
- The 24-mutant classification is a diagnosis made after the run, not a registered criterion.
