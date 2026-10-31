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
| [P2](P2-ibm32-fidelity.md) | Is `ibm32 → float32` exactly invertible? | **FIRED** — 2,447 of 4,103 words fail | any `ibm32`-bearing production spec | D1 |
| [P3](P3-scale.md) | Does ingestion hold at survey scale? | **PASSED** 2026-08-22 | production | D2 |
| [P4](P4-portability.md) | Can a non-Python Zarr read the `headers` array? | did not fire; partly executed — see *Scope* | non-Python consumers | D3 |
| [P5](P5-irregular-geometry.md) | Does irregular geometry survive intact? | did not fire | any real survey | D5 |
| [P6](P6-revision-coverage.md) | Do rev 0/1/2/2.1 each ingest and round trip? | **FIRED** for rev 0, 2, 2.1 | legacy vintages | D6 |
| [P7](P7-prestack-chunking.md) | What is the right prestack chunking? | **FIRED** (clause 1) | prestack workflows | D4 |
| [P8](P8-cloud-object-store.md) | Does the cloud path hold? | **FIRED** (Amendment A, local object store) | cloud deployment | D7 |
| [P9](P9-sample-format-sweep.md) | Does every sample format decode exactly? | **FIRED** — five formats alter values | — | — |
| [P10](P10-scale-recalibration.md) | What wall-clock ceiling does the chain need? | Amendment C **ADOPTED** | — | — |
| [P11](P11-signal-cancellation.md) | What does a signal to `ingest`/`verify` leave running? | did not fire; orphans confirmed (D-0093) | — | — |
| [P12](P12-f3-certify.md) | Does a real delayed survey certify? | Amendment A: **release-ready** (D-0100) | — | — |
| [P13](P13-store-content-variance.md) | Which store bytes differ between ingests? | did not fire; only root `createdOn` (D-0101) | — | — |
| [P14](P14-poststack-chunking.md) | Does any of three poststack chunk shapes beat 128³ on Volve? | **REGISTERED** 2026-10-30, not run | — | D4 |
| [P15](P15-hostile-pairs.md) | Does every command stay clean on a file hostile in two ways at once? | did not fire — 0 of 223 pairs | — | D8 |
| [P16](P16-variable-extended-headers.md) | What does each command do with bytes 3505-3506 = -1? | **FIRED** — untyped upstream error on 4 of 4; refused since (D-0115) | — | D8, D70 |
| [P17](P17-linux-hostile-corpus.md) | Does the D8 corpus behave the same on Linux? | **FIRED** on a harness defect (path naming); clean on Linux since (D-0116) | — | D8 |

A probe with no pre-registration file cannot report a result. A pre-registration whose
falsifier is vague is sent back at review: **"if fidelity looks poor" is not a
falsifier; "any value where `ibm32 → float32 → ibm32` is not bit-identical" is.**
