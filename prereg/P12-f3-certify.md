# P12 — `sdip certify` on a real survey with a recording delay, under 1.4.0

- **Registered:** 2026-10-15, **before the run**, per **SP9**
- **Asked by:** D-0097, which recorded the survey verifying under 1.4.0 and left release
  readiness unestablished because `certify` had not been run
- **Status at registration:** NOT RUN

---

## Question

**Is the 4 ms delayed survey of D-0097 release-ready under `sdip certify` 1.4.0?** Every gate
PASS with none `NOT_RUN`, verdict `EQUIVALENT`, round-trip closure PASS, store digest `MATCH`,
nothing blocking.

## Article

An openly licensed poststack volume, fetched outside this repository and never vendored
(spec §6): 1,292,686,488 bytes, `sha256 b36494f4e9bed7216228124f43ff8901168bff8bebd4e4c4dabb80a68d568dab`,
619,101 traces (651 × 951), 462 samples at 4 ms, IEEE float32, a constant 4 ms recording
delay. Declaration: revision 1, `PostStack3DTime`, no override — the reading D-0097 verified.

## Ceilings — declared now, derived from prior measurements only

G5 needs ceilings, and a ceiling chosen after seeing the run it judges is not one (SP9). Both
are derived from P10 Amendment C's adopted figures on `06p07ful.sgy` (494,565,408 bytes,
116,532 traces, 16 controls — the count today), **not** from any `certify` of this file, which
has never been run.

| | P10 basis | scale | rule | **declared** |
|---|---|---|---|---|
| Wall clock | 1,350 s (already × 1.15) | **traces**: 619,101 / 116,532 = 5.313 | 1,350 × 5.313 = 7,172 s, round up to 50 s | **7,200 s** |
| Peak RSS | 3.50 GB measured | **bytes**: 1,292,686,488 / 494,565,408 = 2.614 | 3.50 × 2.614 × 1.15 = 10.52 GB = 9.80 GiB, round up to 0.5 GiB | **10.0 GiB** |

**Why traces for time and bytes for memory.** The planes, and G7's 16 re-runs of them, walk
the source trace by trace, so their cost follows the trace count. The one prior measurement on
this file points the same way: `sdip verify` took 181 s here against the five planes' 41-42 s
on the P10 file, a ratio of 4.3, nearer the trace ratio (5.3) than the byte ratio (2.6), and
taken as an upper bound by using 5.3. Peak memory follows the volumes materialised whole,
which is bytes (D38). Both are first estimates on a file shaped unlike the calibration file;
**a breach is a G5 FAIL and is reported as one, not re-derived.**

## Method

From this checkout at the commit that registers this file, working tree clean, nothing else
editing it for the duration:

```
sdip certify SOURCE RUN_ROOT/f3.mdio --revision 1 --template PostStack3DTime \
  --rss-ceiling-gib 10.0 --wall-ceiling-s 7200 \
  --prereg prereg/P12-f3-certify.md@<this commit> --certificates RUN_ROOT/certs
```

`RUN_ROOT` is outside the repository; the store and the certificate are written there, so the
tree stays certifiable. N = 1.

## Outcomes

- **Release-ready:** `verdict == EQUIVALENT`, `release_ready: true`, `blocking: []`.
- **Not release-ready:** the blocking reasons, verbatim. A G5 FAIL is a statement about these
  ceilings on this file, recorded with its numbers.

## What this does NOT do

- **It does not commit the certificate.** It carries the operator's local source path. Its
  `sha256` and its gate table are recorded here; the store and certificate are then deleted.
- One file, one machine, one run: no statement about other surveys or about variance.

---

## Results — 2026-10-15, at `8d3ab26`, N = 1

**Not release-ready, and not because of the delay: `certify` refused before issuing a
certificate.** Started 14:02:41Z, exited 14:06:42Z (241.21 s), exit 1, peak RSS of the `sdip`
process 4,588,404,736 B (4.27 GiB) by `/usr/bin/time -l`. No certificate was written; G5 was
never judged, so neither ceiling was reached or tested.

```
sdip: RoundTripUnavailableError: cannot export .../f3.mdio: it carries no `segy_file_header`
variable, so MDIO's exporter has no textual or binary header to write. ...
```

**The cause, measured with SDIP's own classifier on the file's first 3,200 bytes:** the textual
header is EBCDIC and conforms except for **one character, at row 5, column 76**, which is
non-printable after the declared EBCDIC decode. Under D-0055 such a source is ingested with
its raw 3,200 bytes preserved on the root group (raw header `sha256 601efd5d24b71feb…`) and no
`segy_file_header` variable, Plane 1 checks the raw bytes, and **G3 is unreachable**: upstream's
exporter would sanitise that character, so whole-file byte identity is impossible.

The store itself was as D-0097 reported: marker present, `sdipVersion` 1.4.0,
`sdipSampleAxisOrigin.origin_ms` 4.0, nine arrays.

**This is OPEN_DEBTS D17's open half, now measured on a real legacy vintage for the first
time** (D17 recorded it as unmeasured on one). What G3 reports for such a source —
`FAIL`, or `ROUNDTRIP-SCOPED` with the non-conformance named — is a gate ruling for the
maintainer, and `certify` cannot complete on this survey until it is made.

Run root harvested and deleted after this record.

---

## Amendment A — 2026-10-15, before the rerun it governs

**Why.** The first run stopped at the export (D17). D-0098 ruled G3 `ROUNDTRIP-SCOPED` for this
case and fixed D65, which would otherwise have failed G7 on this IEEE source. The rerun asks
the same question under that code.

**Unchanged:** the article, the declaration, **both ceilings (7,200 s, 10.0 GiB)**, N = 1,
store and certificate outside the repository, and the outcomes.

**Changed:** run from a clean worktree at the commit that registers this amendment, on branch
`d17-roundtrip-scoped`, with that worktree's `src` first on `PYTHONPATH`. The certificate's
`git.sdip_commit` names that commit; its `issued_by` reads the installed distribution's
version, 1.4.0, which is the release this branch is built on.

**Expected if D-0098 holds on this file:** G3 `ROUNDTRIP-SCOPED` naming card 6 column 77,
closure and export controls `NOT_APPLICABLE`, every other gate PASS, verdict `EQUIVALENT`,
release-ready. Anything else is reported as found.

---

## Amendment A — results, 2026-10-15, at `7f6fd72`, N = 1

**Release-ready.** Started 14:39:54Z, exited 15:29:08Z (2,954.05 s by `/usr/bin/time`), exit 0,
peak RSS of the `sdip` process 4,924,882,944 B. Certificate `sha256 a69467411143bde2…`,
`git.sdip_commit` `7f6fd72`, `dirty: false`, `issued_by: sdip 1.4.0` (the installed
distribution; the code is the branch's, as Amendment A declared).

| | |
|---|---|
| Declaration | `BOUND` |
| Store digest | `MATCH` |
| Planes 1-5 | PASS; Plane 2's non-blocking `file_revision_differs` (bytes 3501-3502 record 0.0) |
| Plane 4 axis | origin 4.0 ms (D-0096) |
| G3 | **`ROUNDTRIP-SCOPED`** — "1 character(s) are non-ASCII or non-printable after the declared ebcdic decode - card 6 column 77" (D-0098) |
| G4 | PASS |
| G5 | **PASS** — 619,101 traces, peak RSS 4.48 GiB of 10.0 GiB declared, 2,943 s of 7,200 s |
| G6 | PASS — 2 independent ingests, 9 arrays, chunk bytes and values identical |
| G7 | PASS — 13 controls each failing exactly their gates; 3 not applicable (`flipped_raw_ibm32_word`, `deleted_raw_ibm32_array`, `fabricated_value_in_padding`) |
| Closure, closure control, G3 control | `NOT_APPLICABLE` (D-0098) |
| Verdict | **`EQUIVALENT`**, `release_ready: true`, `blocking: []` |

**Both ceilings held**, with margin: 41 % of the wall clock and 45 % of the memory declared.
The trace-scaled time estimate was conservative by a factor of 2.4.

**A finding about the certificate, not the store:** it **does not validate against the
published schema.** Its coordinate-scalar transform entry (scalar −100 on this survey) carries
`arithmetic` and `applies_to: derived_arrays`, which `transforms_declared` does not admit. Every
certificate for a survey with a non-identity coordinate scalar has carried that entry since
D-0087; the schema test used a scalar of 1, which declares none. Raised as debt D66.

Store and certificate deleted after this record (Storage Law); the certificate carried the
operator's local source path and was not committed.
