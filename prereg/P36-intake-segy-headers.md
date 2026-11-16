# P36 — `sdip intake`: header-only intake QC of every SEG-Y on the measuring machine

> **SP9.** Committed **before** the run. Sections above the results separator are never edited.

| Field | Value |
|---|---|
| Probe | `P36` |
| Status | `REGISTERED` |
| Registered | 2026-11-16 |
| Registered by | Claude Code session, on GeoSuite's order (file and image intake programme, phase P3, SDIP lane) |
| Tool under test | `sdip intake` (branch `intake/p3-seismic`), report contract `geosuite.intake.v1` (GeoGIS 6edead4c, schema sha256 `f0a3e47a…7089a`) |
| Spec clause | §11.4 (validate before allocating); operating contract §3.6 (untrusted input) |

## Question

Does the intake reader, reading **headers only**, give every SEG-Y on this machine a
schema-valid report with the geometry an interpreter would name, the right questions, and the
route into an MDIO store, without crashing and inside its header budget?

## Honest disclosure

The reader was developed against six public files, whose reports were seen before this
registration: the F3 8-bit cube, Volve line ST0299-07006, the Viking Graben shot set, the Volve
`volve10r12-full-twt-sub3d` and `-arb` files and the Marmousi2 density model. Their expectations
below were therefore written **after** seeing them; every other file is unseen.

## Set

1. **Public, named** (class `public`): F3 (1), Volve ST0299 2D lines (33), Volve 3D cubes and
   sub-cubes (9), Volve arbitrary line (1), Viking Graben (1), Marmousi2 models (3).
2. **Local-only** (class `confidential`; never in a committed record): the Sleipner 4D partial
   stacks, the `~/apgce-data` and `~/geo-dev` SEG-Y, including one extension-less file. Header
   and format QC only (GeoSuite D-514): nothing derived from them is committed; the tracked
   receipt counts them and nothing more.

## Expectations (the gate)

| # | Expectation | Applies to |
|---|---|---|
| E1 | the reader returns a report; no exception, no exit other than 0 | all |
| E2 | every report validates against the pinned schema | all |
| E3 | `headerBytesRead` ≤ 1 MiB and < file size | all |
| E4 | F3, Volve 3D cubes/sub-cubes: `segy-3d-poststack`, route `PostStack3D*` | public |
| E5 | Volve ST0299 lines and the arbitrary line: `segy-2d-poststack` | public |
| E6 | Viking Graben: `segy-2d-prestack`, shot gathers; QUARANTINE on `SDIP_COORD_UNITS_CONTRADICT` (header says decimal degrees, coordinates are metres) | public |
| E7 | Marmousi2: `segy-2d-poststack`, QUARANTINE on `ENGINE_REFUSED` (zero coordinate scalar at revision 0) | public |
| E8 | no confidential report releases a value: its `structural` block has only format, version, counts, presence flags, domain, codes | confidential |

A file that fails E4–E7 is a finding about the reader, recorded with its header evidence; the
expectation is not edited.

## Receipt

`prereg/P36-receipt-<date>.json`: per public file its dataset label, bytes, sha256, verdict,
format, codes and header bytes read; for the confidential set only the number of files and the
number meeting E1–E3 and E8.

---
