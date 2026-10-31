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
