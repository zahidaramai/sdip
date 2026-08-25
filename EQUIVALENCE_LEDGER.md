# EQUIVALENCE LEDGER — append-only

**SP10.** Append-only index of every Equivalence Certificate this repository has
issued. **A certificate with `verdict != EQUIVALENT` is still committed and still
indexed here.** Failures are evidence.

Certificates live in `certificates/` as JSON, validated against the published
certificate schema.

| # | Issued (UTC) | Source SHA-256 | Store | Spec | Verdict | Gates G1–G7 | Certificate |
|---|---|---|---|---|---|---|---|
| — | — | — | — | — | — | — | *no certificates issued* |

---

> ## STATUS AS OF 2026-08-25
>
> **The table below is the original F0 header and is superseded.** The Equivalence Engine
> exists, all seven gates pass, and **one certificate has been issued** — see
> **[The table, from here](#the-table-from-here)** near the end of this file for the live
> rows, and the corrections between here and there for how the record moved.
>
> `EQUIVALENCE_LEDGER.md` is append-only under **SP10**: rows and corrections are added,
> never edited. **That governs the record, not the navigation** — this pointer is added
> so the first screen does not misinform a reader who does not scroll.

---

## Why this table is empty

*(Superseded — see the status block above.)*

The Equivalence Engine does not exist yet. The repository is at roadmap phase **F0**
(specification §13); the engine is F3 and its non-vacuity suite is **F4**.

**Until G7 passes, every certificate the engine issues is unvalidated.** Do not publish
certificates from an engine whose gates have never been shown to fail. Tracked as
**D11** in `OPEN_DEBTS.md`.

## Recording rules

1. One row per issued certificate, appended in issue order. Rows are never edited.
2. A superseded or retracted certificate keeps its row; a **new row** records the
   supersession and cites the original by number.
3. `Verdict` is one of `EQUIVALENT`, `NON-EQUIVALENT`, `PROVISIONAL` — never a
   qualifier. There is no partial credit (§4.1).
4. `Gates` records all seven positionally, e.g. `PPPPP-P` with `-` for `NOT_RUN`.
5. A certificate issued under a different upstream pin is not comparable to one issued
   under this pin. A pin bump invalidates every certificate issued before it (§3.3);
   record the bump here as well as in `DECISIONS.md`.

---

## Correction — 2026-08-23 — the table is still empty, but not for the reason above

**Appended, not edited (SP10).** The section *"Why this table is empty"* above says the
Equivalence Engine *"does not exist yet"* and that the repository is at **F0**. Both were
true when written and **neither is true now.** The engine exists, all seven gates run,
and **D11 was closed on 2026-08-22** — G7 has been shown capable of failing, with ten
negative controls each failing exactly the gates it declares.

**The table is nonetheless still empty, and that is correct.** Rule 1 admits *one row per
issued certificate*, and **`sdip certify` has never completed on a clean working tree.**
No row is owed. Every run so far has been either a harness run or a run whose tree was
dirty at issue time — and §11.3 refuses those, with no `--force`.

**What has been measured is recorded elsewhere, deliberately.** The survey-scale results
— 11 files, 5,440,219,488 source bytes, every gate `PASS`, **every `G3` byte-identical** —
live in `prereg/P3-scale.md`, because they came from a probe harness rather than from
`sdip certify`. **A probe result is not a certificate and must not be entered here as
one.** Conflating the two is precisely the confusion this ledger exists to prevent.

Two payloads exist locally, at commits `706059b` and `3573e87`, carrying
`issued_at: "LOCAL-RUN"` rather than a timestamp. **They are not certificates**: they
were produced by a harness that bypassed `issue()`'s tree check, they predate
`release_readiness`, and they are held in the firewalled `local/` tree. **They are not
eligible for a row and are named here only so that their existence is on the record
rather than discovered later.**

The first row will be added when `sdip certify` issues from a clean tree.

---

## Correction to the correction — 2026-08-23 — and a policy for firewalled certificates

**Appended, never edited (SP10).** The correction above is itself partly wrong, and an
external audit surfaced it. Recorded here rather than fixed in place, because that is the
rule.

### What the entry above got wrong

It said *"Every run so far has been either a harness run or a run whose tree was dirty at
issue time."* **The second half is false.** The `EQUIVALENT` payload of D-0030 was issued
from a **clean** tree — `dirty: false`, zero dirty paths, at commit `3573e87`. The tree
check passed legitimately.

What actually disqualifies it is narrower: `issued_at` is the literal string
`"LOCAL-RUN"` and `issued_by` is `"local validation"`. A harness supplied both in place of
a timestamp. **The reason was right; the stated reason was not.**

### Policy — certificates issued against firewalled data

D-0025 registers real survey data for local use only. A store built from it, and any
certificate issued against it, **must not be published**. That creates a standing
question this ledger had left implicit, and implicit is not good enough for the record
that carries the project's central claim.

**The rule, from here:**

1. A certificate issued by `sdip certify` against firewalled data **gets a row**. The row
   carries the verdict, the gate string, the source **SHA-256**, the byte count and the
   commit — none of which is restricted — and the `source_path` column reads
   `LOCAL-ONLY (D-0025)` instead of a path. **A digest is not data.** Withholding the row
   entirely would let the public record understate what the engine has actually been
   shown to do.
2. A **harness payload is not a certificate and gets no row**, whatever its verdict. The
   test is `issued_at`: a real ISO-8601 timestamp from `sdip certify`, or nothing.
3. Rule 2 is what excludes D-0030's `EQUIVALENT`. **It is excluded on provenance, not on
   secrecy** — and that distinction is the whole point of writing this down.

### Standing disposition of the two known payloads

| Payload | Verdict | `issued_at` | Tree | Row? | Why |
|---|---|---|---|---|---|
| `local/sleipner/certificate.json` | `PROVISIONAL` | `LOCAL-RUN` | clean | **no** | rule 2 — harness provenance |
| `local/sleipner/certificate_g7.json` | `EQUIVALENT` | `LOCAL-RUN` | clean | **no** | rule 2 — harness provenance |

Both are named so their existence is on the record. **The measurements behind D-0030 are
real and stand**; what they lack is a certificate's provenance, and this ledger indexes
certificates.

**Neither carries the false `raw_ibm32_note`** described in D-0056 — both predate the raw
view. Checked, not assumed, so neither needs superseding.

---

## The table, from here

**Appended, never edited (SP10).** The header above stands unchanged; this is where rows
are recorded from now on. The two correction sections between it and here explain why it
stayed empty until 2026-08-23 and what the rules are.

| # | Issued (UTC) | Source SHA-256 | Source | Spec | Rev | Verdict | Gates G1–G7 | Ready |
|---|---|---|---|---|---|---|---|---|
| **1** | 2026-08-23T08:12:00Z | `750bcb953545a8ae2ff0555ae34543c9cd987834c840a0a26323a30fbeeffe8d` | `LOCAL-ONLY (D-0025)` · 494,565,408 B · 116,532 traces | v1.0 | 1 | **EQUIVALENT** | `PPPPPPP` | **`true`** |

**Row 1 — the first certificate this project has ever issued.**

Issued by `sdip 0.1.0.dev0` at commit **`2f33f3e`**, working tree **clean**. `release_ready:
true`, `blocking: []`.

- **All seven gates PASS.** G5 measured **1,115.3 s of a declared 1,500 s** and **3.64 GiB
  of a declared 8.0 GiB**, against `prereg/P10-scale-recalibration.md@2f33f3e` — a
  pre-registration committed **before** the run it governs (**SP9**).
- **G7:** 15 corruptions, each failing exactly the gates it declares and no others; one
  (`fabricated_value_in_padding`) recorded **not applicable** by name, because this store's
  grid is full and has no padding cell to fabricate into.
- **Round-trip closure PASS**, including the file-headers leg added at D-0067 — and its
  own control, `closure_control`, PASS, *caught by that leg and no other*.
- **`g3_control` and `closure_control` are consulted by the release gate**, not merely
  recorded (D-0072, D-0073).

**The source path reads `LOCAL-ONLY (D-0025)` and that is the policy, not a redaction of
convenience.** The digest, the byte count, the trace count, the verdict, the gate string
and the commit are all here, because **a digest is not data** — withholding the row
entirely would let the public record understate what the engine has been shown to do. The
certificate JSON itself stays in the firewalled tree.
