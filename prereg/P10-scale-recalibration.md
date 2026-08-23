# P10 — Scale recalibration: the chain outgrew its declared wall-clock ceiling

- **Registered:** 2026-08-23, **before the run it governs**, per **SP9**
- **Supersedes, for wall clock only:** the 900 s ceiling in `P3-scale.md@9904bec`
- **Does NOT supersede:** P3's 8.0 GiB memory ceiling, which is **unchanged and still binding**
- **Status at registration:** NOT RUN

---

## Why this exists

`P3-scale.md` declared **900 s** for the full chain. On 2026-08-23 the chain ran
**1,168.5 s** on `06p07ful.sgy` and **G5 failed** (`DECISIONS.md` D-0073). Memory was
never in question: **3.50 GB against the declared 8.59 GB**, a 59 % margin, `rss_breach:
false`.

**The engine got more expensive and the ceiling did not move.** Between P3's declaration
and this run:

| | P3, at declaration | now | source |
|---|---|---|---|
| G7 controls | **10** | **16** | D-0051, D-0056, D-0061, D-0069 added six |
| Closure re-ingest | none | **one** | D-0067 — closure re-ingests the export |

Each G7 control copies the arrays it touches and **re-runs five planes over 116,532
traces**. G7 is the dominant term, and it grew **1.6×**.

---

## The honesty problem, stated rather than finessed

**I have seen the failing number.** A ceiling chosen after seeing the result it judges is
precisely what **SP9** forbids, and no amount of care makes a number I reverse-engineered
from 1,168.5 s a pre-registration.

So the ceiling below is derived from **three inputs, none of which is that observation**:

1. P3's **committed** 900 s, declared before any of this;
2. the **control counts**, 10 and 16 — structural facts readable from
   `src/sdip/equivalence/nonvacuity.py` at two commits;
3. one **ingest cost of 78.2 s**, measured on this same file on 2026-08-23 **before** the
   run, in the D-0052 store-cost work.

### The derivation

G7 is the dominant term, and it scales linearly in control count — each control is one
copy plus five plane runs, and the controls are of comparable cost.

```
scaled G7 growth   : 900 s x (16 / 10)          = 1440 s
added closure re-ingest: + 78.2 s               = 1518 s
declared ceiling, rounded down                  = 1500 s
```

**Rounded DOWN, not up.** Rounding up would be choosing slack, and slack chosen after a
failure is the thing SP9 exists to prevent.

### The test of whether this is a real pre-registration

**Had this arithmetic produced a number below 1,168.5 s, it would have been declared
anyway and G5 would fail again.** That is the whole content of "gates never bend in
either direction". The derivation does not consult the observation, and a reader can
check that claim against the three inputs above.

It happens to land above it. **A reader is entitled to weigh that**, which is why the
inputs, the arithmetic and the fact that I knew the failing number are all on the face of
this document rather than in its footnotes.

---

## Pre-registered parameters

| Parameter | Value |
|---|---|
| **Wall-clock ceiling** | **1500 s per file**, full chain: ingest + 5 planes + G3 + G4 + G6 + G7 + closure |
| **Memory ceiling** | **8.0 GiB peak RSS — UNCHANGED from P3.** Not recalibrated: it did not breach, and moving a limit that held would be adjusting a gate for tidiness |
| G7 control count at declaration | **16** |
| Data | `06p07ful.sgy`, 494,565,408 bytes, 116,532 traces — the file D-0073 failed on |
| N | 1 file for the acceptance run; the ceiling governs any file this size |
| Terminate on breach | yes, regardless of completion |

---

## Falsifier

**The falsifier fires if the full chain exceeds 1500 s, or if peak RSS exceeds 8.0 GiB.**

If wall clock fires: the linear-in-control-count model is **wrong**, and the correct
response is to measure the per-control cost directly rather than rescale the ceiling a
second time. **A ceiling raised twice is not a ceiling.**

If RSS fires: that is a **new** finding — this run's 3.50 GB leaves a 59 % margin, and a
breach would mean something other than the control count changed.

---

## What this does NOT license

**It does not license a third rescale.** If controls are added again, the fix is the
structural one below, not another multiplication.

**It does not reopen D38.** The verification path still fully materialises and RSS is
still linear in file size; the 1.0 GiB `sdip verify` envelope is unaffected. This
recalibrates a **time** ceiling on a file already inside the memory envelope.

---

## The structural fix, declared here and deliberately not built yet

**A bare constant went stale silently, and it will again.** The ceiling should be
expressed as a function of the control count —

```
ceiling = base + per_control x len(CONTROLS)
```

— so adding a control adjusts the budget it consumes, and the number cannot rot while
nobody is looking. Deriving `base` and `per_control` honestly needs a component
measurement of one control's cost at survey scale, which is **its own probe and its own
pre-registration**. Raised as debt **D43** rather than smuggled into this one.

---

## Amendment A — single-control cost, to make the ceiling parametric (D43)

- **Registered:** 2026-08-23, **before the run it governs**, per **SP9**
- **Authorised by:** the post-v1.0.0 ruling, D43
- **Status at registration:** NOT RUN

### Why

The body of this document declared a **flat 1500 s** and said in its own closing section
that a bare constant *"will go stale while nobody is looking"*. **It already did once** —
900 s was correct for 10 controls and wrong for 16, and the staleness surfaced as a
failed gate rather than as a warning.

**A second flat number would be the same defect with a bigger value.**

### Question

**What does one G7 control cost at survey scale**, so the ceiling can be written as a
function of the work rather than as a constant?

```
ceiling = T_base + per_control x len(CONTROLS) + t_closure
```

### Method

1. Run the full chain on `06p07ful.sgy` (494,565,408 B, 116,532 traces) instrumented to
   record **per-stage wall clock**: ingest, five planes, G4, export+G3, **each G7 control
   individually**, `g3_control`, closure, G6.
2. `T_base` := everything that is not G7 and not closure.
3. `per_control` := the **maximum** single-control time, not the mean. A ceiling built on
   the mean is breached by an unlucky ordering; the max is the bound the gate needs.
4. `t_closure` := the measured closure stage, whole.
5. Apply the **same margin discipline the body used**: derive, then round **down**.

### Pre-registered parameters

| Parameter | Value |
|---|---|
| Data | `06p07ful.sgy` — the file both prior runs used |
| N | 1 full chain, **16 individually timed controls** |
| Timing | `time.monotonic()` around each stage, recorded to JSON |
| `per_control` statistic | **maximum**, not mean |
| Memory ceiling | **8.0 GiB, unchanged.** It has never breached |
| Margin | derive, round **down**, as the body did |

### Falsifier

**The falsifier fires if the per-control times are not comparable** — specifically if
`max(control) > 3 × median(control)`.

If it fires, controls are **not** interchangeable units of work, a linear model in
`len(CONTROLS)` is the wrong shape, and the honest answer is a **per-control table**
rather than a single coefficient. **The response is not to average harder.**

### What this does NOT license

**It does not license raising the ceiling.** If the parametric form computes a number
below 1500 s, the lower number is adopted — a recalibration that can only ever loosen is
not a recalibration.

**It does not retire the flat 1500 s by edit.** That number governed the v1.0.0
certificate. It is superseded **by citation**, with both values readable, because a
ceiling that quietly changes value makes every certificate issued under it unauditable.

---

## Amendment A — results, 2026-08-23

Run after Amendment A was committed and pushed (`4cb9685`), per **SP9**.

### The falsifier did NOT fire. The linear shape is right

| statistic | value |
|---|---|
| controls applied | **15** of 16 (`fabricated_value_in_padding` n/a — full grid) |
| **max** | **42.38 s** (`flipped_sample_bit`) |
| median | 40.76 s |
| mean | 40.85 s |
| range | 38.95 – 42.38 s — **±4 %** |
| falsifier `max > 3 × median` | **42.38 > 122.27 → does not fire** |

**Controls are interchangeable units of work.** A per-control table is not needed; a
single coefficient is the right shape. That was the question Amendment A asked, and it is
answered.

### Stage costs

| stage | seconds |
|---|---|
| ingest | 77.63 |
| five planes | 41.05 |
| G4 portability | 0.85 |
| export + G3 | 0.90 |
| **G7, all 16 controls** | **612.93** |
| closure | 110.69 |

### **The derivation is INVALID, and is not adopted. Two reasons, both mine**

**1. The harness did not time what the method requires.** Amendment A defines
`T_base` as *"everything that is not G7 and not closure"*. **G6 and `g3_control` were
never instrumented** — 271.22 s of the certified chain is unaccounted for. `T_base` can
only be recovered by anchoring on a *different run's* total, which is not what the method
said to do.

**2. `N = 1` cannot set a coefficient that must hold across runs.** Working the
derivation through anyway:

```
T_base 391.64  +  per_control 42.38 × 16  +  closure 110.69  =  1180.38 s  →  1150 s
```

**1150 s breaches a run that actually happened.** The D-0073 chain took **1168.55 s** on
the same code path. Run-to-run variance is **4.6 %**, and the derivation leaves less
headroom than that.

### What is NOT being done, and why each would be wrong

**Not adopting 1150 s.** Amendment A says a computed number below 1500 s is adopted — but
that rule assumed a *sound* derivation. This one violated its own method and produces a
ceiling that fails legitimate runs. **A derivation that did not follow its method has not
produced a number; it has produced an error.**

**Not adding a variance margin now.** Inventing a `× 1.1` after seeing that 1150 is too
low is choosing slack to fit an observation — **exactly the SP9 trap this whole
recalibration exists to avoid.** A variance term must be *declared before* the run that
measures it.

**Not raising 1500 s either.** It held, twice.

### **The flat 1500 s stands.** D43 remains open

**Closing D43 requires Amendment B, declared before its run:** instrument **every** stage
including G6 and `g3_control`, run **N ≥ 3** chains, and **declare the variance statistic
in advance** — a max-of-N, or a mean plus a stated multiple of the spread.

**This is the probe working.** It established the model's shape, and it caught the
method's insufficiency **before** a number derived from it became a gate. A ceiling set
from this data would have failed the next legitimate run and looked like a regression.

---

## Amendment B — every stage, N=3, and the variance statistic declared first

- **Registered:** 2026-08-23, **before the run it governs**, per **SP9**
- **Supersedes the method of:** Amendment A, whose derivation was **invalid** — the
  harness omitted two stages and `N = 1` could not set a cross-run coefficient
- **Status at registration:** NOT RUN

### What Amendment A got right, and is not re-asked here

**Controls are interchangeable.** 15 applied controls spanned 38.95–42.38 s, **±4 %**,
`max / median = 1.04` against a 3× falsifier. **That question is closed** — a single
coefficient is the right shape, and Amendment B does not re-litigate it.

### The two defects being fixed

1. **Every stage is instrumented.** Amendment A left **G6** and **`g3_control`**
   untimed — 271.22 s of the chain, recoverable only by anchoring on a different run's
   total, which was not the declared method.
2. **N = 3, not 1.** One chain cannot set a bound that must hold across runs. Measured
   run-to-run variance is **4.6 %** (1,115.27 s and 1,168.55 s on the same code path),
   and Amendment A's derivation left less headroom than that.

### The variance statistic, declared BEFORE the data exists

**Per-stage maximum across the N runs, summed.**

```
ceiling = Σ  max_over_runs( stage_i )        for every stage, G7 counted as
          i                                   per_control_max × len(CONTROLS)
```

**Max-of-N rather than mean-plus-k-sigma, and the reason is N.** With three samples a
standard deviation is not a reliable estimate of spread, and a ceiling built on an
unreliable estimate is a guess with a decimal point. **The per-stage maximum is a bound,
not an estimate**, and summing bounds is conservative by construction: the result is
≥ any single run's total, because no run can be worst at every stage simultaneously.

### Rounding, and it is UP this time — with the reason stated

Amendment A rounded **down**, correctly: it was scaling a prior ceiling and rounding down
refused slack. **Amendment B rounds UP to the next 50 s**, because it sums measured
maxima rather than scaling a guess, and rounding a bound *down* would put the ceiling
below the very worst case it was built from. **The direction follows the derivation's
nature, not a preference.**

### Pre-registered floor constraint — the check Amendment A lacked

**The computed ceiling MUST be ≥ 1,168.55 s**, the largest full-chain total ever observed
(D-0073). **If it is not, the derivation is INVALID and is discarded**, exactly as
Amendment A's was — a ceiling that fails a run which legitimately happened is not a
ceiling, it is a regression waiting to be misread.

### Pre-registered parameters

| Parameter | Value |
|---|---|
| Data | `06p07ful.sgy`, 494,565,408 B, 116,532 traces |
| **N** | **3 full chains**, every stage timed |
| Stages timed | ingest · G1 · 5 planes · G4 · export+G3 · **each control** · **`g3_control`** · closure · **G6** |
| Statistic | **per-stage maximum across the 3 runs** |
| `per_control` | maximum single-control time across **all runs and all controls** |
| Rounding | **up**, to the next 50 s |
| Floor | **≥ 1,168.55 s** or the derivation is discarded |
| Memory ceiling | **8.0 GiB, unchanged.** Never breached |

### Falsifier

**Fires if any stage's `max / min` across the three runs exceeds 1.5.**

That would mean stage costs are not reproducible enough to bound by measurement, and the
honest response is **not** a bigger multiplier — it is to report the ceiling as
unmodellable on this hardware and leave the flat 1500 s in place with that finding
attached.

### Adoption rule

If the computed ceiling clears the floor and the falsifier does not fire, **it is adopted
whether it is higher or lower than 1500 s.** The flat 1500 s is superseded **by citation,
never by edit** — it governed the v1.0.0 certificate, and a ceiling that silently changes
value makes every certificate issued under it unauditable.

---

## Amendment B — results, 2026-08-23. **Floor constraint FAILED. Derivation discarded**

Run after Amendment B was committed and pushed (`504b308`), per **SP9**. Three chains,
every stage timed including the G6 and `g3_control` that Amendment A omitted.

### The falsifier did NOT fire. Stage costs are reproducible

| stage | run 1 | run 2 | run 3 | max | max/min |
|---|---|---|---|---|---|
| ingest | 76.05 | 65.81 | 66.32 | 76.05 | **1.16** |
| five planes | 42.21 | 40.19 | 41.42 | 42.21 | 1.05 |
| G4 | 0.84 | 0.85 | 0.81 | 0.85 | 1.05 |
| export + G3 | 0.90 | 0.88 | 0.88 | 0.90 | 1.03 |
| **G7 (16 controls)** | 617.92 | 639.88 | 609.40 | 639.88 | 1.05 |
| `g3_control` | 0.80 | 0.82 | 0.82 | 0.82 | 1.03 |
| closure | 108.81 | 109.85 | 107.34 | 109.85 | 1.02 |
| **G6** | 134.73 | 133.88 | 133.00 | 134.73 | 1.01 |
| **chain total** | 982.32 | 992.21 | 960.04 | 992.21 | 1.03 |

Worst ratio **1.16** (ingest) against a 1.5 falsifier — **does not fire**. `per_control`
max across all runs and all controls: **44.92 s** (`flipped_sample_bit`).

### The derivation, and the floor it failed

```
Σ per-stage maxima (excl. G7)   365.41 s
G7 modelled  44.92 × 16     =   718.67 s
raw                             1084.09 s   → round up → 1100 s

FLOOR: must be ≥ 1168.55 s      →  1100 < 1168.55  →  FAILED
```

**Discarded, per the rule Amendment B declared before seeing any of this.** 1100 s would
breach **both** certified runs — 1,115.27 s and 1,168.55 s.

### What the floor check caught, and it is not a rounding problem

**The three probe chains took 960–992 s. `sdip certify` takes 1,115–1,169 s. A 12–22 %
gap that is not in any stage.**

**The harness measures the engine; the gate measures the command.** These chains run
back-to-back in **one process** — warm imports, hot page cache on a 494 MB source.
`sdip certify` starts cold, captures git state twice, reads the codec manifest, builds
the array manifest, computes `portable_headers`, assembles the payload and writes the
certificate. **None of that is a stage, so summing stages cannot reach it.**

**A ceiling built from summed stages will always under-predict the command it governs.**
That is a defect in the *method*, not in the measurement — and the floor constraint is the
only reason it was caught rather than shipped.

### **The flat 1500 s stands. D43 remains open**

**Twice now a derivation has been discarded rather than adopted**, and both times the
guard that caught it was pre-registered before the data existed. That is the
pre-registration mechanism doing precisely its job: **A** lacked a floor check and would
have shipped 1,150 s; **B** had one and stopped 1,100 s.

**What Amendment B did establish, and it is not nothing:**

- **Stage costs are reproducible** — worst spread 1.16 across three chains.
- **Controls are uniform**, confirmed at N=3: `per_control` max **44.92 s**.
- **G6 costs 134.73 s and `g3_control` 0.82 s** — the two stages Amendment A could not
  account for, now measured.
- **The parametric shape is sound.** What is wrong is the *anchor*, not the *slope*.

---

## Amendment C — anchor on the command, not on summed stages

- **Registered:** 2026-08-23, **before the run it governs**, per **SP9**
- **Supersedes the method of:** Amendments A and B, both discarded by their own guards
- **Status at registration:** NOT RUN

### The single change

**A and B both modelled the ceiling as a sum of instrumented stages. Both under-predicted
the command by 12–22 %**, because `sdip certify` does work that is in no stage: cold
process start, git state captured twice, codec manifest, array manifest,
`portable_headers`, payload assembly, certificate write. **Summing stages cannot reach
it, however many stages you add.**

**Amendment C measures `sdip certify` end to end** — process start to exit — and keeps the
parametric term for the one thing it is genuinely needed for: **adjusting when the control
count changes.**

```
ceiling(n) = round_up_50( max_observed_certify × 1.15 )  +  44.92 × (n − 16)
```

### The margin is 1.15, and it is declared from PRIOR knowledge

**Not from the run about to happen.** `DECISIONS.md` **D-0074**, already published,
records run-to-run variance of **4.6 %** on identical code — 1,115.27 s and 1,168.55 s.
**1.15 is that spread with headroom for a busier machine**, chosen before this run's
numbers exist and citable to an entry that predates it.

**This is the distinction Amendment A failed.** Using experience to set a threshold is how
any threshold is set; using *the result the threshold judges* is what **SP9** forbids.
The margin here rests on a published prior measurement, not on the forthcoming one.

### `per_control = 44.92 s`, carried from Amendment B

Measured across 3 chains and 45 applied control runs, `max/min` **1.05**. **Not
re-measured** — B established it, the falsifier did not fire, and re-deriving a settled
number invites fitting it.

### Pre-registered parameters

| Parameter | Value |
|---|---|
| Measurement | **`sdip certify` wall clock, process start to exit** |
| Data | `06p07ful.sgy`, 494,565,408 B, 116,532 traces |
| **N** | **3 runs**, each from a cold process on a clean tree |
| Statistic | **maximum**, over these 3 **and** the two already-recorded certified runs (N=5 total) |
| Margin | **× 1.15**, from D-0074's published 4.6 % |
| Parametric term | `+ 44.92 × (n − 16)`, from Amendment B |
| Rounding | **up**, to the next 50 s |
| Floor | **≥ 1,168.55 s** or discarded, as in B |
| Memory ceiling | **8.0 GiB, unchanged** |

### Falsifier

**Fires if any of the three runs exceeds `max_previously_observed × 1.15` = 1,343.8 s.**

That would mean the command's cost is not bounded by the variance D-0074 recorded, and the
honest response is **not** a larger margin — it is to report the wall clock as
**unbounded on this hardware** and leave the flat 1500 s standing with that finding
attached. **A margin enlarged to fit the data it failed to bound is not a margin.**

### What this still will NOT be

**It will not be a first-principles model.** It is a measured bound on one command, on one
file, on one machine, with a coefficient for control count. **It does not predict a
different file, and it must not be read as doing so** — the 1.0 GiB verification envelope
(**D38**) is a separate limit and is untouched.

**Third attempt, and stated plainly:** if this derivation also fails its floor or its
falsifier, **D43 closes as "flat ceiling, and here is why parametric is harder than it
looks"** rather than a fourth amendment. Three discarded derivations is a finding; four is
sunk cost.
