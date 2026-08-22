# P3 — Scale

| Field | Value |
|---|---|
| Probe | `P3` · Status **`PASSED`** (falsifier did not fire, 2026-08-22) · Registered 2026-08-22 |
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

---

## Results — appended 2026-08-22, never edited into the sections above

| Field | Value |
|---|---|
| Run date | 2026-08-22 |
| Governed by | this file as committed in `690b05e`, **before** any file below was ingested |
| Harness | `local/run_p3.py` — local only, per `DECISIONS.md` D-0025 |
| Environment | Python 3.12.13 · `multidimio` 1.2.1 · `segy` 0.6.0 · `zarr` 3.3.0 · macOS arm64 |
| **Verdict** | **THE FALSIFIER DID NOT FIRE.** |

### Scope of the run

| Quantity | Value |
|---|---|
| Files | **11** — three vintages × four stacks, `06p07ful.sgy` excluded as declared |
| Source bytes | **5,440,219,488** (5.07 GiB) |
| Traces | **1,281,852** |
| Samples compared | **1,283,133,852** — exhaustive, exact equality, no sampling |
| Total wall clock | 4,870 s (81.2 min) |

### Per file

| File | Wall | Peak RSS | G1 | G2a–e | G3 | G4 | G6 | G7 |
|---|---|---|---|---|---|---|---|---|
| `01p07far.sgy` | 467 s | 2.81 GiB | PASS | PASS ×5 | PASS | PASS | PASS | PASS |
| `01p07ful.sgy` | 441 s | 2.85 GiB | PASS | PASS ×5 | PASS | PASS | PASS | PASS |
| `01p07mid.sgy` | 442 s | 2.85 GiB | PASS | PASS ×5 | PASS | PASS | PASS | PASS |
| `01p07nea.sgy` | 450 s | 2.85 GiB | PASS | PASS ×5 | PASS | PASS | PASS | PASS |
| `06p07far.sgy` | 450 s | 2.85 GiB | PASS | PASS ×5 | PASS | PASS | PASS | PASS |
| `06p07mid.sgy` | 451 s | 2.85 GiB | PASS | PASS ×5 | PASS | PASS | PASS | PASS |
| `06p07nea.sgy` | 436 s | 2.85 GiB | PASS | PASS ×5 | PASS | PASS | PASS | PASS |
| `94p07far.sgy` | 431 s | 2.85 GiB | PASS | PASS ×5 | PASS | PASS | PASS | PASS |
| `94p07ful.sgy` | 438 s | 2.86 GiB | PASS | PASS ×5 | PASS | PASS | PASS | PASS |
| `94p07mid.sgy` | 421 s | 2.86 GiB | PASS | PASS ×5 | PASS | PASS | PASS | PASS |
| `94p07nea.sgy` | 443 s | 2.87 GiB | PASS | PASS ×5 | PASS | PASS | PASS | PASS |

**Every G3 was byte-identical.** Eleven whole-file SHA-256 matches over 5.07 GiB.

### Against the declared ceilings

| Ceiling | Declared | Worst observed | Headroom |
|---|---|---|---|
| Peak RSS | **8.0 GiB** | **2.87 GiB** | **64 %** |
| Wall clock per file | **900 s** | **467 s** | **48 %** |

**Zero breaches.** RSS varied across the eleven files by **0.06 GiB** — 2.81 to 2.87 —
against files of identical size. That flatness is the substantive observation: memory
tracks the **chunk working set**, not the file, which is what "no unbounded growth" means
in practice. Nothing trended upward across the run.

### Verdict against the pre-registered falsifier

> Any one of: **OOM** or peak RSS above 8.0 GiB · full chain above 900 s for one file ·
> **any trace mismatch** on any plane · any difference between the two **G6** runs ·
> **G7** failing or any control not failing exactly its declared gates · **G3** not
> byte-identical with no written justification.

**None fired.**

- No OOM. Worst RSS 2.87 GiB, 36 % of ceiling.
- No timeout. Slowest file 467 s, 52 % of ceiling.
- **No trace mismatch, across 1,281,852 traces and 1,283,133,852 samples**, compared
  exhaustively with exact equality.
- **G6 passed on all eleven** — 22 independent ingests, compared on chunk bytes *and*
  array values.
- **G7 passed on all eleven** — 88 corruption audits, every control failing exactly the
  gates it declares and no others.
- **G3 byte-identical on all eleven.**

### Where the time goes, and it is not where D18 assumed

| Stage | Total | Share |
|---|---|---|
| **G7** | **4,091 s** | **84 %** |
| G6 | 201 s | 4 % |
| Ingest | 104 s | 2 % |
| Everything else | 474 s | 10 % |

**G7 is 84 % of the probe.** The selective-copy fix (D-0038) closed the *bytes* problem;
the wall clock is dominated by re-running five planes per control, which is inherent —
G7 cannot know a gate fires without running it. Recorded as debt **D23**, and the fix is
parallelism, not less auditing.

### What this establishes, and what it does not

**Establishes:** **G5 PASSES.** Ingestion completes at survey scale inside a ceiling
declared before the run, with no unbounded growth, and the full Equivalence Contract
holds on every file.

**Does not establish:**

- **One geometry.** All eleven files are 249 × 468 fully populated poststack grids with
  zero dead traces. **D5's conditions are absent from this data.**
- **One revision.** rev 1 throughout — **D6** stands.
- **One survey, three vintages.** Same acquisition, same geometry, same vendor.
- **Local filesystem only.** **D7** and probe P8 are untouched.
- **5 GiB is not 20 GiB.** Nothing here shows behaviour an order of magnitude up, and the
  flat RSS is evidence *for* extrapolating but not a measurement of it.

### Recorded in

`DECISIONS.md` D-0042 · `OPEN_DEBTS.md` D2 **CLOSED** within the scope above.

