# Store contract

What an MDIO store written by `sdip ingest` contains, for readers who open it without SDIP.

**Current layout: 1.7.0.** The machine-readable form is
[`src/sdip/schema/sdip-store-layout.json`](src/sdip/schema/sdip-store-layout.json). It ships
in the wheel beside the certificate schema, and
[`tests/integration/test_store_layout_contract.py`](tests/integration/test_store_layout_contract.py)
holds it. A real ingest must produce exactly the declared layout. The layout can change only
with a new version, a `CHANGELOG.md` entry and an update to this file, or the test fails
(`DECISIONS.md` D-0141).

A **layout** is which nodes exist and how they are typed: path, node kind, Zarr `data_type`,
number of dimensions, and the `sdip*` attribute keys. Values are not part of it. The guarded
shapes are the synthetic Appendix A.1 article (5 × 6 × 32) written as `ibm32`, as IEEE
`float32`, and as `float32` with a recording delay.

## Versioning rule

- **MINOR** (1.6 → 1.7): a node or key is added, or an SDIP-owned node changes form, and every
  store an earlier release wrote is still read and verified by the new release. The CHANGELOG
  says which older releases cannot read the new stores.
- **MAJOR**: an upstream pin bump (it invalidates every certificate), or a new release that can
  no longer verify a store an earlier release wrote.
- Each release's layout fingerprint is recorded once and never edited.

## Arrays and groups (layout 1.7.0)

Dimensions below are those of `PostStack3DTime`: *grid* is `inline × crossline`; *samples* is
`time`.

| Path | Kind | `data_type` | Shape | Written | Meaning |
|---|---|---|---|---|---|
| `amplitude` | array | `float32` | grid × samples | always | Trace samples, decoded from the source's sample format. The only transform SDIP permits, declared on the certificate. |
| `inline`, `crossline` | array | `int32` | 1-D | always | Index coordinates (MDIO). |
| `time` | array | `int32` | 1-D | always | Sample axis (MDIO). |
| `trace_mask` | array | `int8` | grid | always | 1 = a live cell holding a source trace, 0 = grid padding. Every other grid-shaped array is read through this. |
| `cdp_x`, `cdp_y` | array | `float64` | grid | always | CDP coordinates (MDIO). |
| `headers` | array | `struct` (extension) | grid | always | Trace headers decoded through the gap-free 240-byte spec (MDIO). Needs `zarr` 3.2.0 or later. |
| `segy_file_header` | array | `fixed_length_utf32` (extension) | 0-D | always | Carries the file headers as attributes, including SDIP's raw copies: `sdipRawTextHeader`, `sdipRawBinaryHeader` and their SHA-256. |
| `headers_raw_uint8` | array | `uint8` | grid × 240 | always | Each live trace's 240 header bytes exactly as in the source, undecoded. Padding is 0. Compared as bytes by Plane 3 (G2c), alongside `headers`; both must pass. |
| `source_trace_ordinal` | array | `int64` | grid | always, **since 1.7.0** | See below. |
| `amplitude_raw_ibm32` | group | — | — | `ibm32` sources only | The raw sample view, layout `sparse/1` **since 1.7.0**. In 1.6.0 and earlier it was one dense `uint32` array the shape of `amplitude`. Read the layout from the group attribute `sdipRawSampleLayout`, never from the version. |
| `amplitude_raw_ibm32/index` | array | `uint64` | k | `ibm32` sources only | Flat C-order positions in `amplitude`, sorted, live cells only. |
| `amplitude_raw_ibm32/words` | array | `uint32` | k | `ibm32` sources only | The source IBM word at each `index`. Every source word is `ieee2ibm(amplitude)` (pinned `segy` 0.6.0), then `words` written at `index`. k is often 0. |

### `source_trace_ordinal` (new in 1.7.0)

- **Value:** for a live cell, the 0-based position of its trace in the source SEG-Y file
  (`sdipSourceTraceOrder` states this in the store). For padding it is 0
  (`sdipSourceTraceOrdinalFill`), so **always read it through `trace_mask`**: 0 on a live cell
  means "first trace in the file", and 0 on padding means nothing.
- **Shape and chunks** match `headers` and `trace_mask`, with the same dimension names. Codec:
  Blosc zstd level 5.
- **Written** from the same source trace map as `headers_raw_uint8`, so the two cannot disagree
  about placement. Listed in the root `sdipMitigations`.
- **Checked:** `sdip verify` compares it with the source's own trace order (Plane 5, G2e) when it
  is present. A store without it, written before 1.7.0, verifies as before.
- **Used:** `sdip export` writes trace records back in this order. Without it, export keeps grid
  order, and where order is the only difference G3 is `ROUNDTRIP-SCOPED: grid order`.
- **Digests:** the store digest and both content digests cover it.

## Root attributes

| Key | Written | Meaning |
|---|---|---|
| `sdipWriter` | always | `sdip.ingest`. |
| `sdipVersion` | always | The SDIP release that wrote the store. **Caveat:** stores written from `main` between 2026-10-16 and the 1.7.0 release record `1.6.0` while holding the 1.7.0 layout. Tell them apart by the layout itself: `source_trace_ordinal` present, `amplitude_raw_ibm32` a group, or `contentV2` present. |
| `sdipUpstreamPins` | always | `multidimio` and `segy` versions the store was written under. |
| `sdipMitigations` | always | SDIP-added arrays: `headers_raw_uint8`, `source_trace_ordinal`. |
| `sdipDeclaration` | always | The survey declaration the store was written under: schema, SHA-256 and a one-line summary (revision, template, override). |
| `sdipSampleAxisOrigin` | non-zero recording delay | The sample axis origin: trace header bytes 109-110 scaled by 215-216, identical on every trace (D-0096). |
| `sdipStoreDigest` | always | The provenance marker below. |

### `sdipStoreDigest`

| Key | Since | Meaning |
|---|---|---|
| `scheme` | 1.3.0 | `sdip-store-digest/1`. |
| `sha256` | 1.3.0 | The **store digest**: every node's metadata and chunk bytes plus the root attributes, without the marker itself. It includes MDIO's `createdOn`, so it identifies one store, not one source. |
| `nodes` | 1.3.0 | Per-node digests the store digest is built from. |
| `root` | 1.3.0 | Digest of the covered root attributes. |
| `content` | 1.6.0 | `sdip-content-digest/1`: the store digest's coverage without `createdOn`. **It identifies a bound store.** GeoCRS, GeoGIS and SFM bindings use it. |
| `contentV2` | 1.7.0 | `sdip-content-digest/2`: `/1` without `amplitude`'s `statsV1.sumSquares`, which can differ between ingests by a few float64 ulps (D75, probe P31). **This is the value a re-ingest reproduces.** It has its own node digests. |

`sdip verify --json` reports `store_digest`, `content_digest` and `content_digest_v2`, each with a
`status` of `MATCH`, `MISMATCH` (fails) or `ABSENT` (a store written before that key existed;
reported, not failed). The certificate carries the additive `content_digest` and
`content_digest_v2` blocks.

**Content digests are reproducible within one layout, not across layouts.** Ingesting the same
source with 1.6.0 and with 1.7.0 gives different `content` values, because the arrays it
covers differ. This was measured on the A.1 article on 2026-11-08 (`DECISIONS.md` D-0141).
A digest pinned for a source must be re-pinned when the layout version changes.

## Compatibility, measured

Measured on 2026-11-08 through the `sdip` executable on the three guarded shapes. Stores
were written by the `v1.6.0` tag, by `26da323` (the commit before `cbb4f2d`), by `cbb4f2d` and
by `15519c5` (the 1.7.0 layout), in one pinned environment. `DECISIONS.md` D-0141 has the
hashes.

| Reader | Store written by | `ibm32` | `float32` | `float32` + delay |
|---|---|---|---|---|
| 1.7.0 layout (`15519c5`) | 1.6.0 | PASS, `/2` ABSENT | PASS, `/2` ABSENT | PASS |
| 1.6.0 | 1.7.0 layout | **exit 3** (internal error) | PASS | PASS |
| `26da323` (before `cbb4f2d`) | `cbb4f2d` | PASS | PASS | not run |
| `cbb4f2d` | `26da323` | PASS | PASS | not run |

- **`source_trace_ordinal` (`cbb4f2d`) is compatible in both directions.** An older reader
  ignores the extra array and does not check it.
- **1.6.0 cannot verify an `ibm32` store with the 1.7.0 layout.** It opens
  `amplitude_raw_ibm32` as an array, but it is now a group. It stops with exit 3 and gives no
  verdict, so no store passes or fails falsely. **Verify with the release that wrote the store,
  or a later one.** This also applies to any stock-zarr reader that opened the dense raw view.
- **Every 1.6.0 store is read and verified by 1.7.0.**

## Layout history

| Version | Fingerprint (sha256) | Change |
|---|---|---|
| 1.6.0 | `ef0dc586…c49d01e` | Measured from stores the `v1.6.0` tag wrote. |
| 1.7.0 | `9405230e…9b8f46b` | `amplitude_raw_ibm32` becomes a sparse group (`ab3a676`, D-0110). `source_trace_ordinal` is added (`cbb4f2d`, D72). `sdipStoreDigest.contentV2` is added (`7a2434f`, D-0135). |

The full fingerprints, and the 1.6.0 layout node by node, are in the manifest.
