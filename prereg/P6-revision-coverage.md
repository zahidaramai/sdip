# P6 — Revision coverage

| Field | Value |
|---|---|
| Probe | `P6` · Status `REGISTERED` · Registered 2026-08-22 |
| Blocks | legacy vintages |
| Related debt | `OPEN_DEBTS.md` D6 · Spec §5, §8 P6 |

## Question

Do SEG-Y rev 0, 1, 2, and 2.1 **each** get a gap-free spec, an ingest, and a round trip?

## Why it matters

SDIP exists largely for archives, and archives are where rev 0 lives. A converter that
only handles the revision its author had on disk is the ordinary case; this probe is
what distinguishes SDIP from it.

## Already banked — static half only, `DECISIONS.md` D-0003

Gap-free **construction** has been measured for every revision the pinned `segy`
exposes:

| Revision | Fields | Covered | Uncovered | `ibm32` | Gap-free fields | G1 satisfiable |
|---|---|---|---|---|---|---|
| rev 0 | 71 | 180 / 240 | 181–240 (60 B) | 0 | 131 | ✅ |
| rev 1 | 89 | 232 / 240 | 233–240 (8 B) | 0 | 97 | ✅ |
| rev 2 | 90 | 240 / 240 | none | 0 | 90 | ✅ *(already gap-free)* |
| rev 2.1 | 90 | 240 / 240 | none | 0 | 90 | ✅ *(already gap-free)* |

**This is not an ingest.** Static coverage says the spec can be built; it says nothing
about whether the file reads, the grid resolves, or the export matches. D6 is
`NARROWED`, not closed.

## Method

Per revision:

1. Generate a synthetic fixture of that revision, deterministically, committed seed.
2. Build the gap-free spec; assert **G1**.
3. Ingest.
4. Run all five planes.
5. Export and compare by SHA-256 (**G3**).
6. Record the field count, filler count, and itemsize on the certificate.

Additionally, for rev 0 specifically: rev 0 has no standard mechanism for declaring the
sample format, so the format is operator-supplied. Record what was assumed and how, on
the certificate. **An assumed sample format is a declared transform (SP1) and must be
stated, not inferred silently.**

## Pre-registered parameters

| Parameter | Value |
|---|---|
| Revisions | 0, 1, 2, 2.1 — all four, none skipped |
| Fixtures | Synthetic, one per revision, committed generator, seed `20260822` |
| N traces per fixture | 30, matching the P1 article so results are comparable |
| Comparison | Exact. **No tolerance.** |

## Falsifier

**Any revision where G1 or G3 cannot be satisfied.**

Note the asymmetry deliberately built in: G1 is already known satisfiable for all four
statically, so a G1 failure here means the *ingest path* disagrees with the *spec
construction path* — which would be a more serious finding than a plain failure.

## If it fires

The revision is named as unsupported in `README.md` and on every certificate, and D6
stays open for that revision. SDIP does not silently ingest a revision it cannot round
trip.
