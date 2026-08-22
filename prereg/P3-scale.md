# P3 — Scale

| Field | Value |
|---|---|
| Probe | `P3` · Status `REGISTERED` · Registered 2026-08-22 |
| Blocks | **production**, and any public claim about the project's contribution |
| Related debt | `OPEN_DEBTS.md` D2 · Gates **G5**, **G6** · Spec §7 G5, §11.2 |

## Question

Does ingestion complete at declared survey scale, within a declared memory ceiling,
with no unbounded growth — and does the Equivalence Contract still hold on the result?

## Why it matters

Everything banked in Appendix A was measured on **30 traces**. Thirty traces is not a
survey. Every conclusion about header cost, chunking, determinism, and round-trip
fidelity is currently an extrapolation from a 14,640-byte file.

Until this probe runs, **the project must not claim its contribution publicly.**
Publishing "no open-source SEG-Y-to-Zarr tool ships a byte-level equivalence validator,
and ours does" before F4 and P3 would be exactly the kind of unverified assertion this
project exists to make impossible.

## Method

1. Declare the memory ceiling and wall clock **before** the run. Terminate on ceiling
   breach regardless of completion (§11.2).
2. Ingest at full declared survey scale with worker count pinned and recorded.
3. Sample peak RSS at a fixed interval throughout; retain the full series.
4. Run **G2** on a **pre-registered random trace sample** plus **all edge and corner
   traces** — first, last, each grid corner, first and last of each inline and crossline.
5. Run **G6**: two independent ingestions of the same source with the same spec and
   config must produce **identical array bytes**, metadata timestamps excluded.
6. Verify checkpoint-on-write: interrupt one run mid-ingest and confirm it resumes
   without loss. A harness that can return nothing after hours is a defect.

## Pre-registered parameters — fixed before the run

**Registered 2026-08-22, before the run this pre-registration governs.**

| Parameter | Declared value |
|---|---|
| Survey scale | ≥ 100,000 traces per file, ≥ 400 MB per file |
| Files under test | **Every file not already ingested** — see "Which data" below |
| **Memory ceiling** | **8.0 GiB peak RSS.** Terminate on breach regardless of completion. |
| **Wall-clock ceiling** | **900 s per file** for the full chain: ingest + 5 planes + G3 + G4 + G6 + G7 |
| Worker count | Upstream default, pinned for the run and recorded on every certificate |
| Trace sampling | **Exhaustive.** Every plane already compares every trace; no random sample is needed and none is used. |
| Edge traces | Exhaustive by construction — the exhaustive comparison includes them |
| G6 runs | 2 independent ingests per file, compared on chunk bytes **and** array values |
| RSS sampling | Peak RSS via `resource.getrusage(RUSAGE_SELF).ru_maxrss` |
| Comparison | Exact. **No tolerance anywhere.** |

### Which data, and why the ceilings are legitimate despite prior knowledge

**SP9 forbids choosing a threshold after seeing the result it judges.** It does not forbid
using experience to set one — that is how any threshold is set.

One file (`06p07ful.sgy`) has already been ingested and measured: peak RSS 3.11 GiB, full
chain 423 s. Those numbers informed the ceilings above and **that file is therefore
excluded from this probe**. P3 runs on files that have **never been ingested**, and the
ceilings are fixed in this commit before any of them is touched.

If a ceiling is breached on a file this pre-registration governs, the probe **fails**. It
does not get raised.

## Falsifier

Any one of the following, on any file this pre-registration governs:

- **OOM**, or peak RSS exceeding **8.0 GiB**.
- Full chain exceeding **900 s** for one file.
- **Any trace mismatch** on any plane — the comparison is exhaustive, so any mismatch at all.
- Any difference between the two **G6** runs, on chunk bytes or on array values.
- **G7** failing, or any control not failing exactly the gates it declares.
- **G3** not byte-identical, with no written `ROUNDTRIP-SCOPED` justification.

## If it fires

Production ingest does not proceed. D2 stays open. The failure is recorded as a
certificate with `verdict: NON-EQUIVALENT` or `PROVISIONAL` and **committed** — failures
are evidence (**SP10**).
