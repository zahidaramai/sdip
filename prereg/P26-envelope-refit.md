# P26 — Verify memory at 4.8 GB, and the envelope default re-fitted on three points (D38)

> **SP9.** Committed **before** the run. The commit is local only: GeoSuite pushes under its own
> approval. Sections above the results separator are never edited.

| Field | Value |
|---|---|
| Probe | `P26` |
| Status | `REGISTERED` |
| Registered | 2026-11-01 |
| Registered by | Claude Code session, on GeoSuite's ruling D-244 (option (a) of D-0128) |
| Related debt | `OPEN_DEBTS.md` D38; `DECISIONS.md` D-0063 ruling 5, D-0128 |
| Spec clause | operating contract §3.6 (bounded allocation); SP8 |

## Question

After P23 and P24, what peak memory does `sdip verify` need for a source of about 4.8 GB?
Fitted on that and P24's two points, where does the line reach the 8.0 GiB ceiling? That size
becomes `--envelope-gib`'s default.

## Fixture

`xl` is 1,800 inlines × 630 crosslines × 1,000 samples, `ibm32`, revision 1. That is 1,134,000
traces in 4,808,163,600 bytes. One call to `make_poststack3d` would hold several copies of the
file in memory, so it is built from six deterministic pieces:
- piece `k` (0..5) is `make_poststack3d(n_inline=300, n_crossline=630, n_samples=1000,
  inline_start=100 + 300 k)`;
- the file is piece 0's 3,600 bytes of file headers, followed by the trace section of pieces 0
  to 5 in order.

Each piece's trace section is its file minus its first 3,600 bytes. The file's sha256 is
recorded. It is written into the run root and deleted at harvest.

## Method

At `main` `36c33fe`, the code P24 measured: `sdip ingest`, then `/usr/bin/time -l sdip verify
--json --skip-portability --envelope-gib 0`, peak RSS from `maximum resident set size`. This is
P23's and P24's measurement exactly.

The other two points are P24 stage B's, measured with the same code and the same command
(`prereg/P24-receipt-2026-11-01.json`):
- 400,683,600 B → 1,012,170,752 B;
- 1,602,723,600 B → 1,175,601,152 B.

**Fit:** ordinary least squares of peak RSS on source size over the three points, both in MB
(10^6 B), so `RSS_MB = i + s × source_MB`.

**Default:** the size at which the fitted line reaches 8 GiB (8,589.934592 MB), converted to
GiB (2^30 B) and rounded **down** to one decimal. Rounding down keeps the default on the safe
side of the line.

## Criteria

1. **The verify passes.** `sdip verify` exits 0 on `xl` with every plane PASS. A failure is a
   finding, asked about under section 9, and nothing is re-fitted.
2. **The line predicts the new point.** P24's two points predict about 1,611 MB for `xl`
   (957.7 + 0.1360 × 4,808.2). If the measured peak differs from that by more than 25 %, memory
   is not linear at this scale. The fit is then **not** adopted, the envelope is not changed,
   and that is reported and asked about.
3. **The fit is adopted** only if 1 and 2 hold. Then:
   - `envelope.py`'s `RSS_INTERCEPT_MB` and `RSS_SLOPE` become the fitted `i` and `s`, and
     `DEFAULT_ENVELOPE_GIB` the derived default;
   - the refusal message states the fit: "measured at 0.4/1.6/4.8 GB, slope `s` MB/MB, intercept
     `i` GB";
   - the envelope tests change with it.

## Recorded, not gated

Ingest's peak RSS and wall clock; verify's wall clock; R² of the fit.

## Not in this probe

The default is an extrapolation from 4.8 GB, and a 50 GB-class source is not measured. The
fixture is one geometry family. The default protects `verify` only, as before. The roughly 0.3
MB per MB growth of the parsed headers and trace map stays as it is (P27, if a consumer needs
it, by GeoSuite's ruling).

---

## Results — *appended after the run, never edited into the sections above*

| Field | Value |
|---|---|
| Run date | 2026-11-01 |
| Code | `main` `36c33fe`, clean. Registration `7c9a131`, before the run |
| Receipt | `prereg/P26-receipt-2026-11-01.json`: fixture hash, peaks, wall clocks, the fit, the driver |
| Verdict | **All three criteria hold; the fit is adopted** |

### Measured

`xl`: 4,808,163,600 B, sha256 `7ac9dfb2…89a30817`.

| | Peak RSS | Wall clock |
|---|---:|---:|
| `sdip ingest` (recorded, not gated) | 5,528,076,288 B | 223.4 s |
| `sdip verify --skip-portability --envelope-gib 0` | **1,783,169,024 B** | 339.3 s |

- **Criterion 1 (verify passes): HOLDS.** Exit 0, verdict PASS, all five planes PASS, G1 PASS,
  both digests MATCH.
- **Criterion 2 (within 25 % of the prediction): HOLDS.** 1,783.2 MB against 1,611.4 MB
  predicted, +10.7 %.
- **Criterion 3 (fit adopted): done.**

| Fit over 0.40 / 1.60 / 4.81 GB | Value |
|---|---|
| Slope | **0.1779 MB per MB** |
| Intercept | **919.6 MB** |
| R² | 0.996 |
| Reaches 8 GiB at | 43,106 MB = 40.15 GiB |
| **New `--envelope-gib` default** | **40.1 GiB** (was 1.0) |

`envelope.py` now carries the three points, the fitted constants and the default, and its tests
recompute each constant from the points and the points from the P24 and P26 receipts. The
refusal message states the fit: "measured at 0.4/1.6/4.8 GB, slope 0.178 MB/MB, intercept
0.92 GB".

### A finding outside the criteria: ingest memory is linear in the file

Ingest's peak RSS, recorded at three sizes by P23 and P26, is 1,008.6, 2,199.6 and 5,528.1 MB.
That is **1.03 MB per MB** of source, and the line reaches 8 GiB near a **7.8 GB** source. This
contradicts `DECISIONS.md` D-0042's statement, which D-0060 left standing for ingest, that
ingest memory "tracks the chunk working set". It also means a source that the new `verify`
default admits could not be **ingested** under the 8 GiB ceiling above about 7.8 GB. Opened as
D74 and asked (section 9). Nothing about ingest is changed here.

### Scope

One synthetic geometry family, macOS arm64. The default extrapolates the line about 8 times
past the largest source measured. `/usr/bin/time -l` reports the `sdip` process's own maximum
resident set; worker processes it spawns are not added in.
