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
