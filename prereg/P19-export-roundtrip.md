# P19 — `export` writes back the stored binary header and the source trace order (D71, D72)

> **SP9.** Committed **before** the run. The commit is local only: GeoSuite pushes under its own
> approval. Sections above the results separator are never edited.

| Field | Value |
|---|---|
| Probe | `P19` |
| Status | `REGISTERED` |
| Registered | 2026-10-31 |
| Authority | The owner, in this session: "Build both", answering the D71/D72 question. Matches GeoSuite's ruling of the same day |
| Related debts | `OPEN_DEBTS.md` D71, D72 |
| Spec clause | §4.3 (raw headers authoritative), §7 G3, §7 G7 |

## Question

With the two fixes built, do the 24 P18 mutants that certified NON-EQUIVALENT through G3 now
round-trip byte-identically? Does each new mechanism carry a control that fails it? And does
a store written before the index existed get an honest scoped G3, not a false PASS or a bare
FAIL?

## What is built (fixed now)

**D71 — binary header written back.** After upstream's `mdio_to_segy` writes the file, `export`
overwrites file bytes 3201–3600 with the store's `sdipRawBinaryHeader` (the source's 400 bytes,
which Plane 2 verifies). The round-trip result records every byte where upstream's encoding
differed from the stored copy. No store-format change.

**D72 — source trace order.** Ingest writes an additive array `source_trace_ordinal`:
- shaped like `trace_mask`, `int64`, written with stock `zarr`;
- each live cell holds the 0-based ordinal of its trace in the source file; padding holds `-1`;
- it is built from the same source-to-cell map Plane 3 and the raw views use;
- it is listed in the certificate's array manifest (schema v0, additive).

`export` then rewrites the trace records into ordinal order, after checking that upstream wrote
exactly one record per live cell. Plane 5 gains a leg: the stored ordinals must equal the source
map's. G7 gains a control: two live cells' ordinals swapped must fail exactly its declared gates.

**A store without the array** (written before this change) exports in grid order as before. If
its export differs from the source **only** in trace order (identical file headers, identical
multiset of trace records), G3 is `ROUNDTRIP-SCOPED` with the reason `grid order`. Any other
difference stays a FAIL.

## Method

1. **Population A: the 24 mutants.** P18 mutants `0, 9, 10, 12, 13, 16, 19, 20, 22, 26, 29, 31,
   36, 39, 43, 47, 55, 58, 65, 66, 71, 80, 83, 86`, built by `build_mutant`, each certified with
   `sdip certify` in a clean empty repository (as the D8 harness does).
2. **Population B: purpose-built sources**, each from the D8 well-formed file:
   - `B1`: binary-header bytes 307–400 (unassigned in revision 1) set to a seeded non-zero pattern;
   - `B2`: the file's traces written in reverse source order (a valid file, not in grid order);
   - `B3`: B1 and B2 together.
3. **Population C: a store without the index.** `B2` ingested by the code at `b0ca755` (before
   this change), then exported and judged by the new code.
4. **Controls.**
   - The new G7 control (swapped ordinals) runs inside every `certify` in A and B.
   - A unit test corrupts one byte of `sdipRawBinaryHeader` in a copy and shows export writes the
     corrupted byte. Plane 2 then fails it, which is already measured.

## Pass criteria (all must hold)

1. **A:** 23 of 24 mutants (all but `mutant_022`) certify with **G3 PASS** (byte-identical) and
   the round-trip closure PASS. `mutant_022` (export exit 2, a different cause) is reported and
   does not count either way.
2. **B1, B2, B3:** G3 PASS byte-identical, closure PASS, verdict EQUIVALENT.
3. **C:** G3 `ROUNDTRIP-SCOPED` with reason `grid order`. Not PASS, not FAIL.
4. **G7:** the swapped-ordinal control fails exactly its declared gates on every store in A and
   B, and every existing control still passes as before.
5. **The full default suite passes**, including the 37-member corpus and the pair, triple and
   mutant slices.

## Falsifier

Any pass criterion above not holding.

## If it fires

The failing case is recorded, and the cause is fixed on the branch if it is inside D71/D72's
design. If the fix would need a different design, for example a different source of the trace
order, it is stopped and asked about. `main` does not move until all five criteria hold.

---

## Results — *appended after the run, never edited into the sections above*
