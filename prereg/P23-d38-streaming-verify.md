# P23 — Verification memory on a 1.6 GB source, before and after streaming Plane 4 (D38)

> **SP9.** Committed **before** either run. The commit is local only: GeoSuite pushes under its
> own approval. Sections above the results separator are never edited.

| Field | Value |
|---|---|
| Probe | `P23` |
| Status | `REGISTERED` |
| Registered | 2026-11-01 |
| Registered by | Claude Code session, on GeoSuite's order under owner D-216 (plan approved by GeoSuite 2026-11-01) |
| Related debt | `OPEN_DEBTS.md` D38; `DECISIONS.md` D-0060 |
| Spec clause | operating contract §3.6 (bounded allocation); SP8 |

## Question

1. **Before.** Does verifying one source of 1.5 GB or more breach the declared 8.0 GiB memory
   ceiling, as D38's linear model predicts? This is the falsifier D38 registered on
   2026-08-23, run for the first time.
2. **After.** Once Plane 4 and its raw-word leg read the source and the store block by block
   instead of whole, is peak memory bounded by the block, not by the file, and is every
   verdict and every piece of evidence unchanged?

## Fixtures

Two synthetic files from the committed `make_poststack3d` generator (default seed, revision
1, `ibm32`, 1,000 samples per trace at 4,000 us), written into the run root and deleted at
harvest:

| Name | Inlines × crosslines | Traces | Size |
|---|---|---:|---:|
| `large` | 600 × 630 | 378,000 | 1,602,723,600 B (1.60 GB) |
| `small` | 150 × 630 | 94,500 | 400,683,600 B (0.40 GB) |

Each file's sha256 is recorded in the receipt.

## Method

For each fixture: `sdip ingest` once, then `sdip verify --json --skip-portability
--envelope-gib 0 SOURCE STORE`. The envelope is disabled explicitly, because the 1.0 GiB
default refuses `large` by design. G4 is skipped because it spawns its own process, and this
probe measures the verification process. **Peak RSS** is the `maximum resident set size` that
`/usr/bin/time -l` reports for the `sdip verify` process. Wall clock is recorded and not
gated. Ingest's peak RSS is recorded and not gated.

- **Before:** at `main` `44539d9`, the code as it stands.
- **After:** at the refactor commit, on the **same** two stores and sources, without
  re-ingesting.

The refactor's scope is fixed now. Plane 4's decoded leg and both raw-word legs (dense and
`sparse/1`) iterate over the store's chunk grid on the non-sample dimensions. Each block reads
only its own store cells and only the source traces that map to them, by explicit reads and
not a memory map. No comparison changes: `np.array_equal` and exact word equality stay as
they are, and no tolerance is added. Header-sized arrays (240 bytes per trace) are still read
whole. That is about 6 % of these files, and the probe measures what it leaves.

## Criteria

**Before (D38's falsifier).** `large`'s peak RSS stays **under 8.0 GiB** (8,589,934,592 B).
If it does, D38's model is wrong and the entry is corrected. D-0060 predicts a breach,
between about 9.9 GB (anchored on the real point) and 12.6 GB (the synthetic fit).

**After, all three must hold:**

1. **Unchanged.** For both fixtures, the `sdip verify --json` document is identical before
   and after, every plane's status and evidence included, apart from fields that record time.
   The full default gate (G7's 18 controls included) passes at the refactor commit.
2. **Bounded.** `large`'s peak RSS is **at most 2.0 GiB**.
3. **Not linear in the file.** `(RSS_large − RSS_small) / (size_large − size_small)` is **at
   most 0.5** (MB of RSS per MB of source). Before the refactor D-0060 measured 7.73.

Any criterion that fails is reported as failed. The refactor is not tuned against these
numbers after the "before" run: the scope above is the whole change.

## Not in this probe

- **The 1.0 GiB `--envelope-gib` default stays.** If P23's "after" holds, whether to raise or
  remove it is a ruling (D-0063 ruling 5 set it), asked after the results. It is not changed
  here.
- `sdip certify`'s whole chain, G4, ingest memory, real survey data, prestack geometries, and
  sources above 1.6 GB are not measured.

## If "before" does not breach

D38's model is corrected with the measured number, and the refactor still runs: criteria 1–3
are independent of it.

---

## Results — *appended after the run, never edited into the sections above*

| Field | Value |
|---|---|
| Run date | 2026-11-01 |
| Commits | Registration `4b07cbd`. Before: `main` `44539d9`, clean. After: `16b85c7`, clean |
| Receipt | `prereg/P23-receipt-2026-11-01.json`: fixture hashes, every peak RSS and wall clock, and the verify JSON hashes |
| Environment | `multidimio` 1.2.1 · `segy` 0.6.0 · CPython 3.12.13 · macOS arm64, 36 GiB RAM |
| Verdict | **Before: D38's falsifier fired.** No breach. **After: criterion 1 holds; criteria 2 and 3 fail** |

### Measured

Peak RSS of `sdip verify --json --skip-portability --envelope-gib 0`, from `/usr/bin/time -l`:

| Fixture | Before | After | Before wall clock | After wall clock |
|---|---:|---:|---:|---:|
| `small` (0.40 GB) | 2,263,007,232 B | 1,006,206,976 B | 34.0 s | 28.7 s |
| `large` (1.60 GB) | **8,127,381,504 B (7.57 GiB)** | **2,253,045,760 B (2.098 GiB)** | 130.8 s | 120.0 s |
| Slope, MB of RSS per MB of source | **4.88** | **1.04** | | |

Ingest peaks, not gated: 1.01 GB (`small`) and 2.20 GB (`large`).

### Against the criteria

- **Before.** `large` peaked at 7.57 GiB, **under** the 8.0 GiB ceiling. D38's falsifier fired:
  the predicted breach (9.9 to 12.6 GB) did not happen. Verification memory is still linear in
  the file, but at 4.88 MB per MB of source on these files, not D-0060's 7.73. At 4.88, the
  8.0 GiB ceiling would be reached near 1.7 GB of source. That is an extrapolation, not a
  measurement.
- **After, criterion 1 (unchanged): HOLDS.** For both fixtures the `sdip verify --json`
  document is byte-identical before and after (same sha256). No field differs, including time
  fields. The full default gate passes at `16b85c7`: 1,898 passed.
- **After, criterion 2 (at most 2.0 GiB): FAILS.** 2.098 GiB, 4.9 % over.
- **After, criterion 3 (slope at most 0.5): FAILS.** 1.04.

The refactor was not changed after the "before" run, as registered. Peak memory on `large`
fell by 72 %, and the slope fell from 4.88 to 1.04, but verification memory still grows with
the file. What still grows is not attributed. The likely cause is the header-sized arrays and
per-trace maps that planes 3, 4 and 5 still read whole, but that is inferred, not measured.

### Scope

- One synthetic poststack geometry, `ibm32`, a `sparse/1` raw view, at two sizes, on macOS
  arm64. No real survey, no prestack, no dense raw view at scale, no source above 1.6 GB.
- `sdip verify` without G4. The whole `certify` chain was not measured.
