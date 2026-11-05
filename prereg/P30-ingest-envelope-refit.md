# P30 — Ingest memory at 4.8 GB after P28, and the ingest envelope re-fitted (D74)

> **SP9.** Committed **before** the run. The commit is local only: GeoSuite pushes under its own
> approval. Sections above the results separator are never edited.

| Field | Value |
|---|---|
| Probe | `P30` |
| Status | `REGISTERED` |
| Registered | 2026-11-05 |
| Registered by | Claude Code session, on GeoSuite D-264 item 1 (`DECISIONS.md` D-0132) |
| Related debt | `OPEN_DEBTS.md` D74 (NARROWED by P28) |
| Spec clause | operating contract §3.6 (bounded allocation); SP8 |

## Question

After P28, what peak memory does `sdip ingest` need for a source of about 4.8 GB? Fitted on
that and P28 stage B's two points, where does the line reach 8.0 GiB? That size replaces the
7.2 GiB interim as the default of `ingest`'s and `certify`'s `--envelope-gib`.

## Fixture

P26's `xl`, built the same way from six `make_poststack3d` pieces. It must hash to P26's
`7ac9dfb2…a89a30817` (4,808,163,600 B), or the run stops. Built in the run root and deleted at
harvest.

## Method

At this registration's commit: `/usr/bin/time -l sdip ingest xl.sgy xl.mdio`, with peak RSS
taken from `maximum resident set size`. This is P28's measurement of the whole command. This
ingest is also P31's first `xl` ingest; P31 reads its store and does not re-measure it.

The other two points are P28 stage B's (`prereg/P28-receipt-2026-11-05.json`):
- 400,683,600 B → 1,001,734,144 B;
- 1,602,723,600 B → 874,266,624 B.

**Fit:** ordinary least squares of peak RSS on source size over the three points, both in MB, so
`RSS_MB = i + s × source_MB`.

## Criteria

1. **The ingest succeeds.** Exit 0. A failure is a finding, asked about, and nothing is
   re-fitted.
2. **Memory no longer tracks the file.** The `xl` peak is **at most 1,500 MB**. Before P28 the
   line predicted about 5,530 MB here, and P26 measured 5,528 MB. Above 1,500 MB, the fit is not
   adopted and that is reported and asked about.
3. **The default**, adopted only if 1 and 2 hold:
   - If `s > 0`: the size where the line reaches 8 GiB (8,589.934592 MB), in GiB, rounded
     **down** to one decimal, **but no more than 40.1 GiB**. That is `verify`'s default, set on
     the same kind of 3-point extrapolation (D-0129). `certify` runs both commands, so an ingest
     envelope above verify's would admit nothing more to `certify`.
   - If `s ≤ 0`: 40.1 GiB, for the same reason, stated as a cap and not as a fit.
   - `envelope.py`'s ingest points and constants change with it; the refusal states the fit, or
     the cap; the envelope tests change with it.

## Recorded, not gated

Ingest wall clock; R² of the fit.

## Not in this probe

A source above 4.8 GB is not measured: any default above it is an extrapolation, and the cap
says so. One geometry family. The parsed source headers (P28: 0.24 MB per MB alone) are not
streamed.

---

## Results — *appended after the run, never edited into the sections above*

| Field | Value |
|---|---|
| Run date | 2026-11-05 |
| Run commit | `981bde5`, clean. Registration `e275698`, before the run |
| Receipt | `prereg/P30-receipt-2026-11-05.json` |
| Verdict | **Criterion 2 FAILED. The fit is not adopted; the 7.2 GiB interim stays** |

- **`xl`** (4,808,163,600 B, sha256 `7ac9dfb2…a89a30817`, matching P26): `sdip ingest` exit 0,
  peak RSS **1,600.5 MB**, 244.8 s.
- **Criterion 1 (succeeds): holds.**
- **Criterion 2 (at most 1,500 MB): FAILED**, at 1,600.5 MB. Before P28, P26 measured 5,528 MB
  here, so memory no longer tracks the file at 1.15 MB per MB. It still grows, at **0.227 MB
  per MB** between 1.60 and 4.81 GB.
- **Criterion 3 (the default): not adopted**, because criterion 2 failed. For the record only:
  OLS over the three points gives slope 0.1546 MB per MB, intercept 807.9 MB, R² 0.825. The
  line would reach 8 GiB at 46.9 GiB, so the 40.1 GiB cap would have applied.

**Diagnosis**, after the run and not gated. The growth between 1.60 and 4.81 GB matches the
parsed source headers, which P28 measured at 0.24 MB per MB and left unstreamed. P28's stage B
point plus that slope predicts 1,637.5 MB, against 1,600.5 measured. **The 1,500 MB bound was set
without that known growth. That is a registration error, and the bound stands failed.**
