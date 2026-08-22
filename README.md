# SDIP — Seismic Data Ingestion & Preparation

**SEG-Y → MDIO/Zarr v3, with a machine-checkable proof that nothing changed.**

[![Specification](https://img.shields.io/badge/spec-v1.0-informational)](#specification)
[![Licence](https://img.shields.io/badge/licence-Apache--2.0-blue)](LICENSE)
[![Status](https://img.shields.io/badge/status-pre--alpha%20(F0)-orange)](#status--honest-limits)

---

## The one sentence

The industry converts SEG-Y to cloud-native formats routinely and almost never proves the
conversion preserved the data.

**SDIP's contribution is not another converter. It is the receipt.**

An MDIO store without a passing Equivalence Certificate is an untrusted artifact, not an SDIP
deliverable. The product is not the file. The product is the file plus the proof.

## What goes wrong without a receipt

None of these failures are loud. They surface years later, in an inversion that will not converge
or a QC that cannot be reproduced, long after the original tape has been archived.

| Failure | How SDIP forecloses it |
|---|---|
| Trace headers dropped because they were not in a template | Gap-free spec: every ingest covers bytes 1–240, zero gaps, zero overlaps (**SP4**, gate **G1**) |
| Proprietary byte locations vanish silently | Uncovered bytes are declared `uint8` fillers and persisted — naming is metadata, byte content is the contract (**SP5**, gate **G2c**) |
| Lossy codecs enabled for a size win, never disclosed | Blosc/Zstd only; `zfpy` must not be installed; codec manifest recorded on the certificate (**SP3**) |
| Grid padding indistinguishable from measured data | Padding is not data and is excluded by the live mask (**SP12**, gate **G2e**) |
| A warning silenced upstream becomes your liability | Warnings are re-raised into the log and recorded on the certificate (**SP6**) |

## The Equivalence Contract

A store `Z` is equivalent to a source `S` **iff all five planes hold simultaneously**. Partial
satisfaction is `NON-EQUIVALENT`, never "mostly equivalent". There is no partial credit.

| Plane | Claim |
|---|---|
| 1 — Textual | 3200-byte textual header verbatim, including non-conforming EBCDIC |
| 2 — Binary | 400-byte binary header as parsed mapping **and** raw bytes; raw is authoritative |
| 3 — Trace header | All 240 header bytes per trace, bit-exact |
| 4 — Sample | Every live sample bit-exact after the declared decode — **exact equality, never `allclose`** |
| 5 — Cardinality | Counts, ordering, live mask, duplicate detection |

The five planes above are the contract in full. Each is exact: byte equality or
`array_equal`, never a tolerance.

## Reversible by construction

SDIP output is a plain Zarr v3 store. Consumers read it with stock `zarr` or `xarray` with **SDIP
and MDIO both uninstalled** — gate **G4** asserts this in a process where `mdio` is never imported.

Adopting SDIP is therefore a reversible decision. If the schema ever becomes a constraint, the data
is already in an open format and nothing needs migrating.

## 60-second quickstart

> **The only command implemented today is `doctor`.** See [Status](#status--honest-limits).

```bash
git clone https://github.com/zahidaramai/sdip && cd sdip
uv sync                 # Python >=3.12,<3.14 — the pins intersect there
uv run sdip doctor      # runs first in CI and first in every runbook
```

`doctor` asserts the barred environment variables are absent, `zfpy` is not importable, the upstream
pins match exactly, the runtime dependency tree carries no copyleft, and the working tree is clean.
If doctor fails, nothing else runs. There is no override flag.

```bash
uv run sdip doctor --json    # machine-readable, suitable as a CI artifact
```

Once the roadmap reaches F3:

```bash
sdip spec build     # gap-free spec, runs G1
sdip ingest         # SEG-Y -> MDIO   (must sit behind a __main__ guard)
sdip verify         # Equivalence Engine against a store (G2, G4)
sdip export         # MDIO -> SEG-Y
sdip certify        # full chain + round trip + certificate (G1-G7)
```

## Status — honest limits

Where a property is unmeasured this project says `UNMEASURED` and names the probe that would settle
it. Unmeasured is a status, not an embarrassment.

**Current phase: F0 — repository skeleton, public-project files, `sdip doctor`.**

| Phase | Deliverable | State |
|---|---|---|
| F0 | Repo skeleton, public files, `NOTICE`, `sdip doctor` | **in progress** |
| F1 | Gap-free spec generator + G1 | not started |
| F2 | Ingest orchestration, certificate v0, provenance | not started |
| F3 | Equivalence Engine — five planes, G2–G4 | not started |
| F4 | **G7 non-vacuity suite** — negative controls | not started |
| F5–F8 | Probes, scale, cloud, prestack, v1.0.0 release | not started |

**Until G7 passes, every certificate the engine issues is unvalidated.** F4 is not optional and is
not last. Do not publish certificates from an engine whose gates have never been shown to fail.

What has actually been measured is recorded in [`DECISIONS.md`](DECISIONS.md), including
the end-to-end gap-free result banked on a **30-trace** synthetic article. **Thirty traces
is not a survey.** Scale is open debt D2, probe P3.

Live debts: [`OPEN_DEBTS.md`](OPEN_DEBTS.md). Debts are scheduled, never cancelled.

## What SDIP does not do

- **No processing of any kind.** No filtering, scaling, resampling, regridding, muting,
  interpolation, or denoising. SDIP is an identity map with a receipt.
- **No ZGY, VDS, or SGZ ingestion.** Ruled derivative-only. ZGY carries no trace
  headers — readers *synthesise* them, and 234 of 240 bytes are zeros. ZGY sample types
  are routinely `int8`/`int16` with a linear coding range, so the data is already
  quantised before SDIP would see it. These may be read on a display or screening path
  only, flagged `DERIVATIVE`, never on a quantitative path.
- **No format invention.** SDIP adopts MDIO v1; it does not design a competing schema.
- **Compression ratio is not a KPI**, and ingestion speed is not a KPI until equivalence is proven
  at scale. A fast pipeline with an unproven contract produces untrustworthy data faster.

## Upstream pins are binding

| Package | Version | Commit |
|---|---|---|
| `multidimio` | `1.2.1` | `a2895b53088ffacbf4bd1b9e882856cbda78e235` |
| `segy` | `0.6.0` | `8e93e97db33ea4b2ce77433f6fdbef5d31ac6e78` |

Pinned **together** — the `ibm32` header fix straddles the `segy` 0.6.0 boundary. A bump invalidates
every certificate issued under the previous pin, and ships as a minor release with a migration note.

SDIP **pins and does not fork.** Full 240-byte header persistence is reachable through the
public API, independent of the deprecated `MDIO__IMPORT__RAW_HEADERS` flag. The chain was
verified against the pinned code, not read from documentation — see [`DECISIONS.md`](DECISIONS.md)
D-0002.

## Contributing

Read [`CONTRIBUTING.md`](CONTRIBUTING.md).

Two rules catch most first-time contributors:

1. **A contribution touching the engine ships its negative control in the same PR.** A gate a
   corrupted store passes is not a gate.
2. **No proprietary data in this repository, ever** — not in `tests/fixtures/`, not attached to an
   issue, not attached to a PR. Reproduce the bug with a synthetic file that has the same structural
   property. A synthetic reproducer is more useful anyway: it becomes a permanent fixture.

## Licence

Apache-2.0. See [`LICENSE`](LICENSE) and [`NOTICE`](NOTICE) — the attribution in `NOTICE` to TGS for
`mdio-python` and `segy` is a legal obligation and must survive refactors.

## Citing

See [`CITATION.cff`](CITATION.cff).
