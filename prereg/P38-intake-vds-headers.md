# P38 — `sdip intake` on OpenVDS: layout QC through OpenVDS in a Linux container

> **SP9.** Committed **before** the run. Sections above the results separator are never edited.

| Field | Value |
|---|---|
| Probe | `P38` |
| Status | `REGISTERED` |
| Registered | 2026-11-16 |
| Registered by | Claude Code session, on GeoSuite's order (intake programme P3, SDIP lane; D-514 Q-A: OpenVDS in a Linux container) |
| Tool under test | `sdip intake` VDS path: content detection on the host, layout read by OpenVDS 3.4.9 (`openvds` wheel, linux/amd64) in a container run with `--network none` and the file mounted read-only |

## Question

Does the VDS path report a VDS file's layout as OpenVDS's own import wrote it (dimensions,
axes, sample format, CRS presence, compression), refuse nothing it should pass, and catch a
truncated copy, without the file leaving this machine?

## Set (generated; nothing fetched)

From the public F3 cube (on this machine): a sub-volume, inlines 100-299 x crosslines 300-599
(field-ok: public F3 survey index ranges), all 462 samples, written as SEG-Y by the committed
generator `prereg/P38_make_vds.py`, then imported by OpenVDS's own `SEGYImport` in the container:

1. `f3_sub.vds`: default import, no CRS given;
2. `f3_sub_crs.vds`: import with a CRS WKT given (`--crs-wkt`);
3. `f3_sub_cut.vds`: a copy of (1) with its last 1,000 bytes removed.

## Expectations (the gate)

| # | Expectation |
|---|---|
| V1 | every report is schema-valid; no exception; exit 0 |
| V2 | (1) and (2): three dimensions, 200 x 300 x 462 samples, inline axis 100-299, crossline axis 300-599, sample axis 0-1844 ms, as written by `SEGYImport` |
| V3 | (1) asks `CRS_UNRESOLVED`; (2) reports the stated WKT as the first CRS candidate, sourced to the VDS |
| V4 | (3) is `QUARANTINE` |
| V5 | the container runs with networking off; the report says OpenVDS's own reads are not counted in `headerBytesRead` |

## Receipt

`prereg/P38-receipt-<date>.json`: per file its label, bytes, sha256, verdict, codes and the
fields compared in V2.

---

## Results (2026-11-16, `sdip` b0a95f8, receipt `P38-receipt-2026-11-16.json`)

| # | Result |
|---|---|
| V1 | met: 3/3 schema-valid, no exception |
| V2 | **not met, as registered**: three dimensions, 200 x 300 x 462, inlines 100-299, crosslines 300-599 as expected, but the sample axis is 4-1848 ms, not 0-1844. F3's own trace headers state a delay recording time of 4 ms (bytes 109-110 of the first trace); `SEGYImport` honoured it. The expectation was wrong, the reader reported what the file holds. |
| V3 | met: no WKT in (1), so the CRS question has no candidate; (2)'s WKT is the first candidate, sourced to the VDS |
| V4 | **not met**: the cut copy came back NEEDS_INPUT. OpenVDS's layout sits at the front of the file and its public API opens the cut copy without complaint; neither a corner-brick request nor the chunk API (`prefetchVolumeChunk` would not accept its arguments from Python) showed the cut without reading the data |
| V5 | met: the container ran with `--network none` and a read-only root; every report carries `SDIP_VDS_INTEGRITY_UNCHECKED` |

**Gate: not met (V2, V4).** The reader states, in every VDS report, that truncation is not
checked. Found on the way: SDIP's SEG-Y intake reader does not report the delay recording time,
which an interpreter needs (F3 starts at 4 ms); recorded as a follow-up in D-0147.
