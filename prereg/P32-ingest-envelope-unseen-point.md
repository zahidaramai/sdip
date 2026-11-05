# P32 — The ingest envelope from P28's numbers, tested on an unseen 9.6 GB point (D74)

> **SP9.** Committed **before** the run. The commit is local only until its gate passes;
> SDIP pushes it under the D-262 window. Sections above the results separator are never edited.

| Field | Value |
|---|---|
| Probe | `P32` |
| Status | `REGISTERED` |
| Registered | 2026-11-05 |
| Registered by | Claude Code session, on GeoSuite D-273 as amended (`DECISIONS.md` D-0135) |
| Related debt | `OPEN_DEBTS.md` D74; D76 (the header term) |
| Spec clause | operating contract §3.6 (bounded allocation); SP8; SP9 |

## Question

Does a memory bound written **only from P28's numbers** hold for a source size nobody has
measured? If it does, it replaces the 7.2 GiB interim as the default of `ingest`'s and
`certify`'s `--envelope-gib`.

## The bound, written now from P28 alone

Two terms:
- **The header term.** `h` = **0.2381 MB per MB**: the slope of the parsed source headers
  measured alone in P28 stage A (`axis_origin`, `prereg/P28-receipt-2026-11-05.json`). P28
  left them unstreamed (D76).
- **The fixed term.** `A` = **906.3 MB**: the largest of `peak − h × size` over P28 stage B's
  two whole-command points (1,001.7 MB at 400.68 MB; 874.3 MB at 1,602.72 MB). That covers the
  streamed arrays, which no longer grow with the file, and the interpreter. It is taken from the
  larger residual, so the bound holds at both points P28 measured.

**Bound:** `B(S) = 1.10 × (906.3 + 0.2381 × S)` MB for a source of `S` MB. The 10 % is a
margin on a memory ceiling, fixed now. It is not a tolerance on any compared value.

| Size | `B(S)` |
|---|---:|
| 4,808.16 MB (P26's `xl`, already measured: **reported, not gated**) | 2,256.3 MB |
| **9,616.32 MB (`xxl`, unseen: gated)** | **3,515.6 MB** |

## Fixture

`xxl`: 12 deterministic pieces. Piece `k` (0..11) is `make_poststack3d(n_inline=300,
n_crossline=630, n_samples=1000, inline_start=100 + 300 k)`. The file is piece 0's 3,600 header
bytes, followed by every piece's trace section in order: 2,268,000 traces, **9,616,323,600 B**.
Its sha256 is recorded in the receipt. It is built in the run root and deleted with it. It has
never been ingested.

## Method

At this registration's commit, with a clean tree, run `/usr/bin/time -l sdip ingest xxl.sgy
xxl.mdio --envelope-gib 10.0`. Peak RSS is taken from `maximum resident set size`.
`--envelope-gib 10.0` is raised for this one run only, because `xxl` (8.96 GiB) is above the
7.2 GiB interim. The raise is recorded in the receipt. Nothing else is run on the store.

## Criteria

1. **The ingest succeeds:** exit 0. A failure is a finding, asked about, and nothing changes.
2. **The bound holds:** peak RSS on `xxl` at most **3,515.6 MB**. Above it, the bound is
   reported failed, and the 7.2 GiB interim stays.
3. **The default**, adopted only if 1 and 2 hold. It is the size where `B(S)` reaches 8 GiB
   (8,589.934592 MB): 28,991 MB, which is **27.0 GiB**, rounded down to one decimal. Verify's
   40.1 GiB caps it and does not bind here.
   - `envelope.py`'s ingest model becomes `B`, with its points and terms.
   - The refusal states it: "bound 1.10 × (906 MB + 0.238 MB/MB), from P28; held at 9.6 GB
     (P32)".
   - The envelope tests change with it.

## Recorded, not gated

The wall clock; the 4.81 GB comparison above; `xxl`'s distance below the bound.

## Not in this probe

A source above 9.6 GB is not measured, so a 27.0 GiB default is a 2.8-fold extrapolation of
the bound. The header term is P28's alone, and D76 would remove it. One geometry family, one
host.

---

## Results — *appended after the run, never edited into the sections above*

| Field | Value |
|---|---|
| Run date | 2026-11-05 |
| Run commit | `124f04f`, the registration commit, clean |
| Receipt | `prereg/P32-receipt-2026-11-05.json` |
| Verdict | **Criteria 1 and 2 hold. The bound is adopted; the default is 26.9 GiB, not 27.0** |

- **`xxl`**: 9,616,323,600 B, sha256 `ee546bf9…683f419c`, never ingested before. Run with
  `sdip ingest --envelope-gib 10.0`, the raise for this one run. Exit 0, 552.1 s.
- **Criterion 1 (succeeds): holds.**
- **Criterion 2 (bound): holds.** Peak RSS **2,810.5 MB**, against a bound of 3,515.6 MB, which
  is 79.9 % of it. Reported, not gated: at 4.81 GB the bound is 2,256.3 MB and P30 measured
  1,600.5 MB.
- **Criterion 3 (default): adopted as 26.9 GiB.** The rule registered above is: the size where
  `B(S)` reaches 8 GiB, rounded **down** to one decimal. Computed exactly, that size is
  28,990.8 MB, or 26.9998 GiB, which rounds down to **26.9**.
  - **The registration's "28,991 MB, which is 27.0 GiB" was an arithmetic slip.** I rounded
    where the rule says round down, and wrote the fixed term to one decimal (906.3; exactly
    906.331).
  - The rule governs, and 26.9 is its safe side: at 27.0 GiB the bound is just past 8 GiB.
  - `envelope.py` carries the fixed term at full precision. A test holds the default where
    the rule puts it, and fails on 27.0.
