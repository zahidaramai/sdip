# P7 — Prestack templates & chunking

| Field | Value |
|---|---|
| Probe | `P7` · Status `REGISTERED` · Registered 2026-08-22 |
| Blocks | prestack workflows |
| Related debt | `OPEN_DEBTS.md` D4 · Spec §6.5, §8 P7 |

## Question

What chunk shape does each prestack geometry actually need — and does the Equivalence
Contract hold on prestack data at all?

## Why it matters

Poststack keeps the upstream default `(128, 128, 128)` until measured otherwise, which
is a defensible inheritance. **Prestack chunking is `UNMEASURED`, and guessing it in
production is how a store becomes unusable without becoming wrong** — every read
touches every chunk, and nothing in the certificate would show it.

Prestack also matters more than the geometry table suggests: shot gathers, streamer
field records, and OBN receiver gathers are **Primary** at v1.0, not deferred.

## Method

Per geometry — streamer shot gathers, streamer field records, OBN receiver gathers,
CDP gathers:

1. Ingest with candidate chunk shapes.
2. Run all five planes on each. **Correctness first; chunking is meaningless if G2
   fails.**
3. Measure read latency for the geometry's characteristic access patterns: single
   gather, offset slice, time slice, full inline.
4. Record chunk shape, store size, and per-pattern latency for each candidate.

## Pre-registered parameters

| Parameter | Value |
|---|---|
| Geometries | streamer shot, streamer field record, OBN receiver, CDP gather |
| Candidate chunk shapes | *declared before the run, minimum 3 per geometry* |
| Read-pattern latency target | *declared before the run, per pattern* |
| N repetitions per measurement | *declared before the run* |
| Cache state | Cold, explicitly dropped between measurements |
| Comparison (correctness) | Exact. **No tolerance.** |

> Unfilled by design. **SP9** requires these fixed and committed before the run. The PR
> that authorises the run fills them and merges first.

## Falsifier

Either:

- **G2 failure on any prestack geometry** — a correctness failure, and by far the more
  serious outcome; or
- **No chunk shape meeting the declared read-pattern latency target** for a geometry.

## If it fires

- On G2 failure: the geometry is marked unsupported and D4 escalates from a performance
  debt to a correctness debt.
- On latency failure: the geometry ships with its measured best shape and the miss
  recorded on the certificate. **A slow store that is provably correct is shippable; a
  fast store that is not is not.**
