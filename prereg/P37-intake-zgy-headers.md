# P37 — `sdip intake` on ZGY: header-only QC against the OpenZGY reader

> **SP9.** Committed **before** the run. Sections above the results separator are never edited.

| Field | Value |
|---|---|
| Probe | `P37` |
| Status | `REGISTERED` |
| Registered | 2026-11-16 |
| Registered by | Claude Code session, on GeoSuite's order (intake programme P3, SDIP lane) |
| Tool under test | `sdip intake` ZGY reader `sdip.intake.zgy` (branch `intake/p3-seismic`), SDIP's own stdlib parser |
| Oracle | OpenZGY's pure-Python reader as shipped in `pyzgy` 0.1.1 (Apache-2.0), run outside SDIP's environment |

## Question

Does SDIP's own ZGY header reader agree with the OpenZGY reader on every field it reports, and
does each corruption get its own code?

## Honest disclosure

The five public test files below were read by the reader during development (that is how a
lookup-table decoding error was found and fixed). The F3 sub-cube and its corrupted copies are
unseen.

## Set

1. **Public test files** shipped in the `pyzgy` 0.1.1 sdist (`test_data/small-{8,16,32}bit*.zgy`,
   five files). Source, sha256 and bytes go in the receipt; the sdist is deleted after the run.
2. **Generated:** an F3 sub-cube (inlines 100-299, crosslines 300-599, all 462 samples, float32)
   written with OpenZGY's writer by the committed generator `prereg/P37_make_zgy.py`, with the F3
   corner coordinates, metres, TWT in ms and the projection text found in F3's textual header;
   then two corrupted copies: the last 1,000 bytes cut off, and a copy with one brick's lookup
   entry zeroed. Generated files live in the git-ignored run root and are deleted after the run.

## Expectations (the gate)

| # | Expectation |
|---|---|
| Z1 | every report is schema-valid; no exception |
| Z2 | size, annotation origin and increment, vertical start and increment, the four corner points and the data type equal the oracle's, on all six intact files |
| Z3 | the five public files and the intact F3 sub-cube carry no `quarantine` or `refuse` finding |
| Z4 | F3 sub-cube: `structural.domain` is `time`, `hasUnits` true, and the projection text is offered as the first `CRS_UNRESOLVED` candidate; no `DOMAIN_UNKNOWN` question |
| Z5 | the cut copy is `QUARANTINE` with `TRUNCATED` |
| Z6 | the zeroed-entry copy carries `SDIP_ZGY_MISSING_BRICKS` with exactly one missing brick |
| Z7 | `headerBytesRead` ≤ 1 MiB on every file |

## Receipt

`prereg/P37-receipt-<date>.json`: per file its label, bytes, sha256, verdict, codes, header bytes
read and the field-by-field comparison with the oracle.

---

## Results, run 1 (2026-11-16, `sdip` 921cd639, receipt `P37-receipt-2026-11-16-run1.json`)

| # | Result |
|---|---|
| Z1 | met: 8/8 schema-valid, no exception |
| Z2 | **not met**: 47 of 48 field comparisons equal; the F3 sub-cube's fourth corner differs by 0.01 m in y |
| Z3 | met |
| Z4 | met: domain time, units stated, the projection text is the first CRS candidate, no domain question |
| Z5 | **not met**: the copy with its last 1,000 bytes cut came back NEEDS_INPUT, not QUARANTINE |
| Z6 | met: one missing brick |
| Z7 | met: at most 1,932 header bytes read, on the 199 MB files |

**Gate: not met.** Causes, measured:

- **Z2.** OpenZGY derives the fourth corner from the other three (it treats four points as
  three) and reports a parallelogram; SDIP reports the fourth corner as stored. The F3 grid's
  fourth corner lies 0.01 m off the parallelogram. Neither reader is wrong; the expectation
  compared a derived value with a stored one. The deviation is itself a QC fact, so the reader
  now reports it (`SDIP_ZGY_CORNER_NOT_PARALLELOGRAM`, information, with the distance).
- **Z5.** A defect in the reader: it checked only full-resolution bricks for truncation, and
  OpenZGY writes the lower-resolution bricks after them, so a cut tail lands in a level the
  reader did not check. The reader now checks every brick entry of every level.

Both fixes are re-measured on the same files as run 2 below; this run's gate stays not met.

## Results, runs 2 and 3 (2026-11-16)

Run 2 at `077d717` (receipt `P37-receipt-2026-11-16-run2.json`): Z5 met (the cut copy is
QUARANTINE on TRUNCATED); Z2 still not met, and the 0.01 m corner offset went unreported because
the new check's threshold was relative to the grid span (12.5 mm at F3's span). Run 3 at `5517656`
(receipt `P37-receipt-2026-11-16-run3.json`), threshold relative to the coordinate magnitude:

| # | Run 3 |
|---|---|
| Z1 | met |
| Z2 | **not met, as registered**: 47/48 equal; the fourth corner is stored by SDIP and derived by OpenZGY. The F3 report now says so (`SDIP_ZGY_CORNER_NOT_PARALLELOGRAM`) |
| Z3 | met |
| Z4 | met |
| Z5 | met |
| Z6 | met |
| Z7 | met |

**Gate: not met (Z2).** The expectation compared a derived value with a stored one; it is not
edited. Every other field agrees with OpenZGY on all six intact files.
