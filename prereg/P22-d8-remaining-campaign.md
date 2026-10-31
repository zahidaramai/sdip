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
