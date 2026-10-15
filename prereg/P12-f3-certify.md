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
