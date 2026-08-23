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

## Why this table is empty

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
