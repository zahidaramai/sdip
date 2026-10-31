# P15 — Hostile in two ways at once: the D8 corpus, pairwise

> **SP9.** Committed **before** the run. The commit is local only: the workspace's top ruling
> forbids a push without the owner's command, and GeoSuite pushes under its own approval.
> Sections above the results separator are never edited.

| Field | Value |
|---|---|
| Probe | `P15` |
| Status | `REGISTERED` |
| Registered | 2026-10-31 |
| Registered by | Claude Code session, on GeoSuite's relay of owner D-216 (every open debt proceeds) |
| Blocks | nothing |
| Related debt | `OPEN_DEBTS.md` D8, residual 3 ("structural, not combinatorial") |
| Spec clause | §11.4; operating contract §3.6 |

## Question

When a SEG-Y file is malformed in **two independent ways at once**, does every `sdip` command
still end in a clean refusal or a verdict? That means no crash, no traceback, no exit 3, no
unbounded allocation, no hang and no write outside the output directory.

## Why it matters

D8's corpus has 33 members, and each isolates **one** hostility on an otherwise well-formed
file. SDIP's defence is a sequence of checks (`preflight`, then upstream's parser, then MDIO's
grid checks, with D60's boundary at the CLI). A check written for one hostility can assume
that every other field is sane. One example: an arithmetic check that divides by a field
another check has not validated yet. A file built to break that assumption needs two
hostilities, and no such file has ever been run. Residual 3 says this is unmeasured.

## Method

1. **Members.** The 23 corpus members built by `_corrupt` (one mutation applied to the
   well-formed 30-trace file): classes `truncated` (4), `declared_length` (4), `count_field`
   (4), `sample_format` (4), `sample_interval` (3), `grid` (3), `path` (1). Excluded:
   - `short` and `garbage`. These replace the whole file, so there is nothing to apply a
     second mutation to.
   - `source_is_a_directory` and `source_is_a_dangling_symlink`. These are not files.
2. **Pairs.** Every unordered pair of those members from **different** classes. Different
   classes touch disjoint bytes, so neither mutation overwrites the other. **N = 223.**
3. **Composition order, fixed.** The two mutations are applied to one copy of the
   well-formed file in this layer order:
   - (1) trace-level writes;
   - (2) truncations;
   - (3) binary-header writes.

   A trace-level write finds each trace from the binary header's sample count, so it must run
   before a binary-header write can change that count. A truncation must run after the
   trace-level writes. Binary-header writes sit below byte 3600, which every truncation keeps.
   Layers:
   - trace-level: `declared_trace_samples_exceed_file`, `trace_samples_zero`,
     `trace_samples_negative`, `sample_interval_enormous`, the three `grid_*`,
     `path_bait_in_headers`;
   - truncation: the four `truncated` members;
   - binary-header: the rest.

   The single-member corpus bytes do not change. Its existing determinism test holds that.
4. **Run.** Each pair runs through the existing D8 harness unchanged: `hostile_child.py`, one
   process per pair, which drives the library ingest, then the `sdip` console entry point for
   `ingest`, `verify`, `export` and `certify`. The filesystem is snapshotted around the run,
   and peak RSS comes from `ru_maxrss`. The well-formed positive control runs through the same
   harness and must ingest, verify and export with exit 0 (SP11).
5. **Gate placement, decided now.** The exhaustive 223 run once, and the wall clock is
   recorded. If the 223 together take **≤ 600 s**, all stay in the default suite. Otherwise a
   fixed representative set stays in the default suite and the rest go under a new
   `campaign` marker, which the default run deselects as it does `benchmark`. The
   representative set is the last member of each class in `CORPUS` order: one pair per class
   pair, **21** pairs. Last, not first, because the first `truncated` member
   (`file_headers_only`) deletes every trace, which would erase the other hostility in 4 of
   the 6 class pairs it joins.

## Pre-registered parameters

| Parameter | Value |
|---|---|
| N | 223 pairs, exhaustive over the rule above, plus the positive control |
| Commands | `ingest` (library and CLI), `verify`, `export`, `certify` |
| Per-pair timeout | 300 s (the D8 harness's existing value) |
| Memory ceiling | 512 MiB peak RSS (the D8 harness's existing value) |
| Environment | the repository's locked environment, `multidimio` 1.2.1, `segy` 0.6.0, this host |

## Falsifier

**Any one pair** for which any of the following is observed:

1. the child does not finish within 300 s, or exits without writing its report;
2. the library ingest raises an exception that is neither an `SdipError` nor one of MDIO's
   grid types (`GridTraceSparsityError`, `GridTraceCountError`) that P5 pinned;
3. any of the CLI `ingest`, `verify`, `export` or `certify` exits 3, prints `Traceback`, prints
   `internal error`, or lets an exception escape the console entry point;
4. peak RSS above 512 MiB;
5. a path created outside the declared output directory, or inside the repository;
6. a CLI exit 0 from `ingest` on a pair whose library ingest raised.

## Reported, not gated

- For each pair: which layer refused it (SDIP typed, upstream typed, or converted).
- How many pairs convert even though one member alone is refused. This is a fact about the
  composition, not a defect: two mutations can cancel out, for example a sample count matched
  to a truncation.
- How many pairs are byte-identical to one of their single members. Example:
  `file_headers_only` with any trace-level member.

## If it fires

Every firing pair becomes a permanent member of the default suite, as the negative control
for its fix (operating contract §5). The defect is fixed in `src/` on the same branch, and the
pair must then pass. D8 stays OPEN until it does. A pair whose fix would change a gate or the
Equivalence Contract is stopped and asked about (§9), not fixed.

## If it does not fire

D8 narrows: residual 3 closes for pairs, scoped to this corpus and this host. Three or more
hostilities at once, and any mutation search, stay unmeasured. Residuals 2 (no
stanza-terminated rev 2 member) and 4 (one platform) are untouched by this probe.

---

## Results — *appended after the run, never edited into the sections above*

| Field | Value |
|---|---|
| Run date | 2026-10-31 |
| Run commit | `742e102`, clean tree. Registration at `e7b5f9c`, before the run |
| Harness | the D8 child, unchanged. Each pair is judged by `falsifier_hits` in `tests/negative/test_d8_hostile_pairs.py` |
| Receipt | `prereg/P15-receipt-2026-10-31.json`: one record per pair (clauses hit, outcome, exit codes, peak RSS, seconds, source SHA-256) |
| Environment | `multidimio` 1.2.1 · `segy` 0.6.0 · CPython 3.12.13 · macOS arm64 |
| Verdict | **The falsifier did not fire. 0 of 223 pairs met any clause** |

### Measured

| | Pairs |
|---|---:|
| Refused by SDIP, typed `UntrustedInputError`, raised inside `sdip` | 191 |
| Refused by MDIO's pinned grid types (`GridTraceSparsityError` 12, `GridTraceCountError` 6) | 18 |
| Converted | 14 |
| Any CLI command exiting 3, printing a traceback or `internal error`, or escaping | **0** |
| Peak RSS above 512 MiB | **0** (max 248.9 MB) |
| A path created outside the output directory, or in the repository | **0** |
| CLI `ingest` exit 0 on a file the library refused | **0** |
| Child timeout or missing report | **0** (slowest pair 27.5 s) |

CLI exit codes across `ingest` / `verify` / `export` / `certify`:
- 209 pairs: 1 / 1 / 1 / 1;
- 9 pairs: 0 / 1 / 1 / 1;
- 5 pairs: 0 / 1 / 1 / 0.

`verify` and `export` read the positive control's store, so a converted pair is judged FAIL
against a store it did not write. That is a verdict, not a crash.

**Reported, not gated:**
- **Converted although one member alone is refused: 0.** All 14 converting pairs are made of
  two members that each convert alone.
- **Byte-identical to one of their single members: 15.** These are `file_headers_only` (which
  keeps no traces) paired with a trace-level member. Their second hostility is erased by
  construction, as the registration expected.

### Gate placement, by the registered rule

The 223 took **838.2 s**, above 600 s. The 21 representative pairs stay in the default suite.
The other 202 run under the new `campaign` marker, which the default `addopts` deselects
(`pytest -m campaign` runs them).

### Scope — read this before citing P15

- Two hostilities at once, from one corpus of 23 single mutations on one 30-trace poststack
  file. Three or more at once, and any mutation search, are unmeasured.
- One host, one platform (D8 residual 4 stands). No stanza-terminated rev 2 member (D8
  residual 2 stands).
