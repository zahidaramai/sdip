# P31 — Which store bytes differ between ingests of a survey-scale source? (D75)

> **SP9.** Committed **before** the run. The commit is local only: GeoSuite pushes under its own
> approval. Sections above the results separator are never edited.

| Field | Value |
|---|---|
| Probe | `P31` |
| Status | `REGISTERED` |
| Registered | 2026-11-05 |
| Registered by | Claude Code session, on GeoSuite D-264 item 2 (`DECISIONS.md` D-0132) |
| Related debt | `OPEN_DEBTS.md` D75; P13; `DECISIONS.md` D-0101 |
| Spec clause | §3.4 (determinism); SP8 |

## Question

P13 measured five small store shapes and found only MDIO's root `createdOn` varying between
ingests. P28 found `amplitude`'s `statsV1` varying at 1.60 GB. **At survey scale, which chunk
files and which metadata keys differ between fresh ingests of one source under one
declaration?** `sdip-content-digest/2` may exclude those, and nothing else.

## Method

P13's harness method, unchanged. For each case, the source is generated once and ingested
**N** times by `sdip ingest`, each a fresh process into its own directory. Then, across the N
stores:
- every non-metadata file (chunk) is compared by SHA-256;
- every `zarr.json`, at every node, is parsed and flattened to key paths, and every key path
  whose value differs is listed, with its distinct values.

## Cases

| Case | Source | N | Why |
|---|---|---:|---|
| `large_ibm32` | `make_poststack3d(n_inline=600, n_crossline=630, n_samples=1000)`, P23's `large` (sha256 `2b8b7aa0…1cd3eb2e`) | 5 | the size P28 found varying; carries the raw view |
| `large_float32` | the same call with `sample_format="float32"` | 5 | IEEE samples, no raw view (D65) |
| `xl_ibm32` | P26's `xl` (sha256 `7ac9dfb2…a89a30817`) | 3 | 4.81 GB; ingest 1 is P30's measured run |

N is 5 where P28 saw three values in six ingests, and 3 at `xl`, where one ingest takes about
four minutes.

## Decision rule (pre-registered, under D-0132)

1. **The falsifier:** any chunk file differing between ingests. That contradicts G6, so the
   build stops and it is reported.
2. If the only varying key paths are MDIO's root `createdOn` and keys under `amplitude`'s
   `statsV1`, `sdip-content-digest/2` excludes exactly those. It is recorded **beside** `/1`,
   never in place, and existing bindings are not re-made.
3. Any other varying key is reported by name, and **stops the build** for a ruling.
4. No value is rounded (D-0132).

## Reported, not gated

The distinct values of every varying key; whether `count`, `sum`, `min` and `max` ever vary.

## Not in this probe

One machine and one process environment. Variation across machines or library versions is not
seen. Synthetic data only. Whether a smaller source can vary is not measured: P13's five
shapes are the small end, and this probe is the large end.

---

## Results — *appended after the run, never edited into the sections above*
