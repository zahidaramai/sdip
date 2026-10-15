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
