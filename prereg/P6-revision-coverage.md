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

---

## Results

*Everything below this line was appended after the run. Nothing above it was edited.*

**Run 2026-08-22.** Runner `tests/integration/test_p6_revisions.py` (28 tests, all
passing). Fixtures `tests/fixtures/generators/revisions.py`. Four files, one per
revision, differing **only** in the revision: same 5 x 6 x 32 grid, same 30 traces, same
14,640 bytes, same analytic amplitudes, same planted bytes 233-240, seed `20260822`,
comparison exact with no tolerance anywhere.

**Environment.** Python 3.12.13 · Darwin 25.5.0 arm64 · `multidimio` 1.2.1 ·
`segy` 0.6.0 · `zarr` 3.3.0 · `xarray` 2026.7.0 · `numpy` 2.5.2 · `dask` 2026.7.1 ·
`numcodecs` 0.16.5.

`sdip doctor` at run time: **7 of 8 PASS** — barred variables absent, `zfpy` not
importable, both binding pins matched with 145 installed files verified against
RECORD, 51 runtime distributions scanned with no GPL/AGPL entry. The eighth,
`working-tree`, **FAILS**: the tree carries concurrent probe work in progress. **No
certificate is issued from this run and none could be** (§11.3) — a probe measures,
it does not certify.

### Verdict against the pre-registered falsifier

> **Any revision where G1 or G3 cannot be satisfied.**

**THE FALSIFIER FIRED — for three of the four revisions.** rev 0, rev 2 and rev 2.1 all
satisfy G1 and then fail to ingest, so G3 is not merely failed for them, it is
unreachable. **Only rev 1 completes the leg.**

### Per-revision result

| Revision | Standard fields | Fillers | Gap-free fields | Itemsize | G1 | G2a | G2b | G2c | G2d | G2e | G3 | Byte-identical |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| rev 0 | 71 | 60 | 131 | 240 | **PASS** | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | **BLOCKED** | n/a |
| rev 1 | 89 | 8 | 97 | 240 | **PASS** | PASS | PASS | PASS | PASS | PASS | **PASS** | **yes** |
| rev 2 | 90 | 0 | 90 | 240 | **PASS** | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | **BLOCKED** | n/a |
| rev 2.1 | 90 | 0 | 90 | 240 | **PASS** | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | **BLOCKED** | n/a |

`BLOCKED` is not `FAIL` and it is certainly not `PASS`: the step could not run because
the ingest before it did not. Every field, filler and itemsize above reproduces the
D-0003 static table exactly, which is what ties this probe to that measurement rather
than to some other spec.

**Fixture SHA-256**, 14,640 bytes each:

| Revision | Fixture SHA-256 | Spec SHA-256 (field manifest) |
|---|---|---|
| rev 0 | `5adee30eeca0371a0526a31868f891e5b8005c71045fbfa108b7474e15bb734d` | `4b8213b4ec5cb42c…` |
| rev 1 | `be4ce4375799b8ebc670526229581e73d995f03a8a3bb308141f41fc91bdd762` | `0ba58a559cdd3d1e…` |
| rev 2 | `eaf3dd30fb84025f886402da36466995b4792e119652b8dca2b13f3175062100` | `4730652236a66580…` |
| rev 2.1 | `c615caab3f9aec5464b4debd90bf512c1b111ad769e9950b81e25de109af7fdd` | `4730652236a66580…` |

rev 2 and rev 2.1 hash to the **same spec**. Their trace-header field manifests are
identical; the two revisions differ only in the binary header. Whatever P6 concludes
about one of them holds for the other by construction, not by coincidence.

### The asymmetry the pre-registration built in

G1 passed on all four. That is the *good* half of a bad result: the ingest path did not
disagree with the spec-construction path, so the more serious of the two possible
findings did not occur. Gap-free construction generalises across every revision the
pinned `segy` exposes, exactly as D-0003 said. What P6 establishes is that construction
is not enough.

### The three blockers, isolated

Each was reduced to the smallest thing that causes it. The isolating runs are the
`test_diagnosis_*` tests; **none of them is part of the pre-registered method and none
of them satisfies any gate for any revision.**

**rev 0 — four absent field declarations.**

```
ValueError: Required fields ['cdp_x', 'cdp_y', 'crossline', 'inline'] for template
PostStack3DTime not found in the provided segy_spec
```

rev 0 declares nothing above byte 180. `cdp_x`, `cdp_y`, `inline` and `crossline` enter
the standard at rev 1, so the gap-free rev 0 spec covers bytes 181-240 with 60 `uint8`
fillers — correctly, under SP5 — and the template cannot find the four fields it indexes
on. The *bytes* are in the file at the canonical positions; only the declaration is
missing. Declaring those four over 181-196 keeps the spec gap-free (G1 still PASS, 119
fields) and makes the whole leg pass: five planes PASS, export byte-identical. **That is
precisely what a §6.4 survey override is, and §6.4 is not built.** rev 0 is one
specified, unimplemented mechanism away from working, and nothing else about it is
broken.

**rev 0 — the sample format is not merely undeclared, it is unsuppliable.**

The fixture assumes **`ibm32`**, and states it: `SampleFormatDeclaration(scalar_type=
"ibm32", declared_by_standard=False)`. It is supplied by writing format code 1 into
binary header bytes 3225-3226 through `SegyFactory.create_binary_header()`, and that
choice is carried on the fixture rather than left implicit, because under **SP1** an
assumed sample format is a declared transform.

The sharper finding is what happens without that. `SegyFile._update_spec()` reads
`data_sample_format` from bytes 3225-3226 **unconditionally, for every revision
including rev 0**, and maps it through `DataSampleFormatCode`. Zero that field — which
is what a genuine 1975-vintage rev 0 file carries, the standard never having mandated it
— and the file does not open at all:

```
ValueError: 0 is not a valid DataSampleFormatCode
```

So the rev 0 fixture reads only because SDIP's own generator stamped the format into it.
A real rev 0 archive gets no further than the reader, and **SDIP today exposes no surface
through which an operator could supply the format instead.** An operator-supplied sample
format is a stated requirement of this probe and there is currently nowhere to state it.

**rev 2 and rev 2.1 — two blockers, and the second hides behind the first.**

*Blocker 1, ingest:*

```
ValueError: Unsupported numpy dtype 'bytes64' for conversion to ScalarType.
```

The rev 2 standard declares `trace_header_name` at byte 233 as an 8-character string.
It is the **only** non-integer field in the 240 bytes, and `multidimio` 1.2.1 has no
`ScalarType` for it, so the MDIO header dtype cannot be built at all. Note what this
means: rev 2 and rev 2.1 are the two revisions that need **no fillers** — they are
gap-free as shipped — and they are the two that cannot be ingested.

*Blocker 2, export:* replacing that one field with eight `uint8` lets the ingest run and
all five planes pass — and the export then fails anyway:

```
segy.exceptions.NonSpecFieldError: The header field 'segy_revision_major' is found in
field alias table as 'segy_revision_major'. However, the current SEG-Y spec does not
define this field in header fields.
```

`mdio_spec_to_segy` injects the **rev 1** `segy_revision` field into any spec whose
binary header does not contain it. rev 2 and rev 2.1 do not contain it — they carry
`segy_revision_major` and `segy_revision_minor` over the same bytes 301-302 — so the
injection removes the two fields the factory then immediately asks for. Fixing blocker 1
alone would not give rev 2 a round trip.

Both are upstream defects in the pinned `multidimio` 1.2.1. They are raised as issues,
not routed around: §3.3 bars monkeypatching and no fork is authorised. The field swap
used to expose blocker 2 is a probe instrument only — replacing a field the standard
*does* define is not gap-free spec construction, and changing it for real would be a
spec-mechanism decision under §9.

### What this run did **not** establish

- **N = 30 traces, one geometry, one template.** Scale is untouched (D2 / P3) and the
  grid is a perfect 5 x 6 (D5 / P5). A revision passing here is not a revision proven at
  survey scale.
- **One sample format.** All four fixtures are `ibm32`. Nothing here measures a revision
  under `float32`, `int16`, or any other declared format.
- **rev 1 only.** The single completed leg is the same revision, template and geometry
  P1 already banked. P6 adds no new *passing* ground; it adds three failures.
- **G7 is still NOT_RUN.** Every certificate this engine issues remains unvalidated
  (D11), so "five planes PASS" here is a measurement against an engine not yet shown
  capable of failing.

### Consequence — per "If it fires"

rev 0, rev 2 and rev 2.1 are **named as unsupported** in `README.md` and on every
certificate, and **D6 stays open for all three**. rev 1 is the only revision SDIP can
currently ingest and round trip, and that is what the record must say. SDIP does not
silently ingest a revision it cannot round trip, and none of the three is silently
ingested: each stops with a typed error before a store is written.

The status line at the top of this file still reads `REGISTERED`. Updating it, and the
D6 entry, is a maintainer action recorded in `DECISIONS.md`; this block does not edit
anything above the separator.
