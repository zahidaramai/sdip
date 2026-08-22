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
