# Pre-registrations

**SP9 — pre-registration; gates never bend.** Verdict criteria, thresholds, and N are
committed and pushed **before** the run.

> **Why these live at the repository root and not in `docs/`.** `docs/` is never committed
> (`DECISIONS.md` D-0010), and a pre-registration whose whole value is being **publicly
> timestamped before the result exists** cannot live somewhere it can never be pushed.
> SP9 would have been unsatisfiable. A pre-registration is not documentation — it is a
> commitment artifact, and git's history is what makes it one. Same reasoning as the
> certificate schema in D-0015; recorded as D-0032.

## The order is not negotiable

1. PR adds `PN-short-name.md` from [`TEMPLATE.md`](TEMPLATE.md). It states the
   question, the method, the threshold, the N, and the **falsifier**.
2. **Merge it before running anything.**
3. Run the probe.
4. Second PR appends results **below** the results separator. Sections above it are
   never edited.

Never write a pre-registration after seeing a result. Better-than-expected does not
tighten a gate post hoc; worse-than-expected does not relax one.

## Register

| Probe | Question | Status | Blocks | Debt |
|---|---|---|---|---|
| [P1](P1-gap-free-spec.md) | Is a gap-free 240-byte spec viable end to end? | **PASSED** 2026-08-22 | — | — |
| [P2](P2-ibm32-fidelity.md) | Is `ibm32 → float32` exactly invertible? | `REGISTERED` | any `ibm32`-bearing production spec | D1 |
| [P3](P3-scale.md) | Does ingestion hold at survey scale? | `REGISTERED` | production | D2 |
| [P4](P4-portability.md) | Can a non-Python Zarr read the `headers` array? | `REGISTERED` | non-Python consumers | D3 |
| [P5](P5-irregular-geometry.md) | Does irregular geometry survive intact? | `REGISTERED` | any real survey | D5 |
| [P6](P6-revision-coverage.md) | Do rev 0/1/2/2.1 each ingest and round trip? | `REGISTERED` | legacy vintages | D6 |
| [P7](P7-prestack-chunking.md) | What is the right prestack chunking? | `REGISTERED` | prestack workflows | D4 |
| [P8](P8-cloud-object-store.md) | Does the cloud path hold? | `REGISTERED` | cloud deployment | D7 |

A probe with no pre-registration file cannot report a result. A pre-registration whose
falsifier is vague is sent back at review: **"if fidelity looks poor" is not a
falsifier; "any value where `ibm32 → float32 → ibm32` is not bit-identical" is.**
