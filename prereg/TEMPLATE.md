# P<N> — <short name>

> **SP9.** This file is committed and pushed **before** the run. Never write a
> pre-registration after seeing a result. Better-than-expected does not tighten a gate
> post hoc; worse-than-expected does not relax one. Gates never bend in either
> direction.

| Field | Value |
|---|---|
| Probe | `P<N>` |
| Status | `REGISTERED` / `RUNNING` / `PASSED` / `FAILED` / `SUPERSEDED` |
| Registered | `YYYY-MM-DD` |
| Registered by | |
| Registration commit | *(filled by the merge that registers it)* |
| Blocks | *(what may not proceed until this clears)* |
| Related debt | `OPEN_DEBTS.md` D<N> |
| Spec clause | §<N> |

## Question

One sentence. What is actually unknown.

## Why it matters

The mechanism by which a wrong answer here causes harm downstream. If you cannot write
this paragraph, the probe is not worth running.

## Method

Exactly what will be done, in enough detail that a stranger could run it from this file
plus the repository. Name the script, the config, the seed, the fixture.

## Pre-registered parameters — fixed before the run

| Parameter | Value |
|---|---|
| N | |
| Sampling scheme | *(exhaustive, or the scheme — never chosen after seeing results)* |
| Threshold / ceiling | |
| Environment | *(pins, Python, worker count)* |

## Falsifier

**The single result that proves the hypothesis wrong.** Write it as a concrete
observable, not as a feeling. "Any value where `x → y → x` is not bit-identical", not
"if fidelity looks poor".

## If it fires

What happens. Which clause gets a `SCOPED` note, which debt opens, what stops shipping.
Decide this now, while it costs nothing.

---

## Results — *appended after the run, never edited into the sections above*

| Field | Value |
|---|---|
| Run date | |
| Run commit | |
| Environment as run | |
| Verdict | |

### Measurements

Numbers with units and N. Not conclusions.

### Verdict against the pre-registered falsifier

Did the falsifier fire, exactly as written above? Yes or no, then the evidence.

### Recorded in

`DECISIONS.md` D-NNNN · `OPEN_DEBTS.md` D<N> · `EQUIVALENCE_LEDGER.md` row #
