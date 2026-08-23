# P7 — Prestack templates & chunking

| Field | Value |
|---|---|
| Probe | `P7` · Status `REGISTERED` · Registered 2026-08-22 |
| Blocks | prestack workflows |
| Related debt | `OPEN_DEBTS.md` D4 · Spec §6.5, §8 P7 |

## Question

What chunk shape does each prestack geometry actually need — and does the Equivalence
Contract hold on prestack data at all?

## Why it matters

Poststack keeps the upstream default `(128, 128, 128)` until measured otherwise, which
is a defensible inheritance. **Prestack chunking is `UNMEASURED`, and guessing it in
production is how a store becomes unusable without becoming wrong** — every read
touches every chunk, and nothing in the certificate would show it.

Prestack also matters more than the geometry table suggests: shot gathers, streamer
field records, and OBN receiver gathers are **Primary** at v1.0, not deferred.

## Method

Per geometry — streamer shot gathers, streamer field records, OBN receiver gathers,
CDP gathers:

1. Ingest with candidate chunk shapes.
2. Run all five planes on each. **Correctness first; chunking is meaningless if G2
   fails.**
3. Measure read latency for the geometry's characteristic access patterns: single
   gather, offset slice, time slice, full inline.
4. Record chunk shape, store size, and per-pattern latency for each candidate.

## Pre-registered parameters

| Parameter | Value |
|---|---|
| Geometries | streamer shot, streamer field record, OBN receiver, CDP gather |
| Candidate chunk shapes | *declared before the run, minimum 3 per geometry* |
| Read-pattern latency target | *declared before the run, per pattern* |
| N repetitions per measurement | *declared before the run* |
| Cache state | Cold, explicitly dropped between measurements |
| Comparison (correctness) | Exact. **No tolerance.** |

> Unfilled by design. **SP9** requires these fixed and committed before the run. The PR
> that authorises the run fills them and merges first.

## Falsifier

Either:

- **G2 failure on any prestack geometry** — a correctness failure, and by far the more
  serious outcome; or
- **No chunk shape meeting the declared read-pattern latency target** for a geometry.

## If it fires

- On G2 failure: the geometry is marked unsupported and D4 escalates from a performance
  debt to a correctness debt.
- On latency failure: the geometry ships with its measured best shape and the miss
  recorded on the certificate. **A slow store that is provably correct is shippable; a
  fast store that is not is not.**

---

## Amendment A — latency leg parameters, declared 2026-08-22

**Registered before any benchmark is run.** The original pre-registration left the
parameter table unfilled, and the first P7 run reported the latency leg **NOT RUN** for
exactly that reason: under **SP9**, a threshold invented after seeing a chunk shape is
not a threshold. This amendment fixes the parameters so the leg becomes runnable.

**It is an amendment, not an edit.** Nothing above is changed. A test
(`test_the_pre_registration_latency_parameters_were_never_back_filled`) asserts the
original table stays empty, and that test stays.

| Parameter | Declared value |
|---|---|
| Geometries | The four the original method names: streamer shot, streamer field record, OBN receiver, CDP gather |
| Candidate chunk shapes | **3 per geometry**: MDIO's default, a gather-contiguous shape, and a time-slice-contiguous shape |
| Read patterns | single gather · offset slice · time slice · full inline |
| **Latency target** | **≤ 2.0 s per read pattern**, cold cache, on the fixture sizes this probe uses (≤ 500 traces) |
| Repetitions | **5** per (geometry, shape, pattern); the **median** is the reported figure |
| Cache state | Cold — dropped between measurements |
| Correctness precondition | **All five planes must PASS first.** A latency figure for a store that fails G2 is meaningless and must not be reported |

**Falsifier for this leg**, unchanged in substance from the original: **no chunk shape
meeting the declared target for a geometry.**

**Why 2.0 s and why it is honest to name it now.** These fixtures are ≤ 500 traces — a
read that takes longer than two seconds on data this small indicates a chunking that
fights the access pattern, not a slow disk. The figure is deliberately generous: the leg
is meant to catch a *pathological* shape, not to rank good ones. No benchmark has been
run, and no chunk shape has been measured against any pattern, at the time this amendment
is committed.

**Scope limit stated in advance:** this measures *relative* behaviour on small synthetic
fixtures. It is **not** a production latency claim, and a shape that wins here is not
thereby validated at survey scale — that would need P3-class compute and its own
pre-registration.

---

## Results

| Field | Value |
|---|---|
| Run date | 2026-08-22 |
| Outcome | **Falsifier clause 1 FIRED** on 3 of 7 geometries. Clause 2 **not evaluable** |
| Runner | `tests/integration/test_p7_prestack.py` — 94 tests, all passing |
| Fixtures | `tests/fixtures/generators/prestack.py`, seed `20260822`, synthetic only |
| Environment | CPython 3.12.13, macOS 26.5.2 arm64 |
| Pins | `multidimio==1.2.1`, `segy==0.6.0`, `zarr==3.3.0`, `numpy==2.5.2` |
| Barred variables | absent, asserted before anything was built |
| Comparison | exact throughout. No tolerance anywhere in the runner |
| N | 7 geometries, 64–192 traces each, all inside the 500-trace budget |

### A note on the engine this was measured against

The probe was run **twice, against two different versions of the plane checkers**, and
both readings are recorded because the first one is the finding that produced the second.

*First reading*, against `src/sdip/equivalence/planes.py` as of `484e7fa`: Planes 3, 4
and 5 each called `build_trace_map` with a hard-coded `{"inline": …, "crossline": …}`.
**No prestack geometry produced a G2 verdict at all** — six of the seven stores raised
`KeyError: 'inline'` before any comparison happened, and the seventh (`cdp_offset_3d`,
the only prestack store that keeps an inline and a crossline axis) built a **2-D map over
a 4-D grid**, returning `FAIL` on data since shown to be bit-exact.

*Second reading*, after `store_dimensions()` landed and the three call sites began reading
the grid dimensions from the store's own Zarr metadata: the tables below. This is the
reading the runner asserts.

The distinction matters and is preserved rather than tidied away: the first reading is why
the second exists, and it is the measurement behind the change.

### Verdict against the pre-registered falsifier

> Either **G2 failure on any prestack geometry**, or **no chunk shape meeting the
> declared read-pattern latency target** for a geometry.

**Clause 1 — FIRED.** Under the first reading it fired on all seven, as an inability to
evaluate. Under the second it fires on **three of seven**, and on firmer ground:

- `streamer_shot_3d_wrapped` — a **measured G2 failure**. Planes 3, 4 and 5 all `FAIL`.
- `streamer_field_3d`, `obn_receiver_3d` — **G2 not evaluable**. All three planes raise
  `UntrustedInputError`; a grid dimension has no coordinate array to resolve against, and
  `NOT_RUN` is not a pass.

**G2 holds exactly on the other four**, all five planes, exact comparison.

**Clause 2 — NOT EVALUABLE, and deliberately left that way.** The parameter table above
was never filled in: no candidate chunk shapes, no latency target, no N, no authorised
compute for a cold-cache benchmark. Under **SP9** a threshold invented after seeing a
chunk shape is not a threshold, so the latency leg **was not run**. The chunk shapes below
are observations against nothing. A test
(`test_the_pre_registration_latency_parameters_were_never_back_filled`) reads this file and
fails if the parameter table is ever back-filled.

### What was measured, and how

Two legs, because leg 1 alone cannot distinguish a declaration gap from a format
limitation.

**Leg 1 — through `sdip.ingest.ingest`.** Every geometry, its own template, nothing else
changed. **Seven refusals out of seven.** Every prestack template MDIO ships binds at
least one trace-header field the SEG-Y rev 1 standard does not name, `ingest()` builds its
spec from the revision standard, and it exposes no way to add a name. Nothing is read and
nothing is written.

**Leg 2 — the same conversion with those names declared.** SDIP's ingest sequence,
unchanged, except that the gap-free spec carries the geometry's index-field declarations
(`HeaderSpec.customize`; G1 re-run and still PASS on all seven) and a grid override is
passed where the template needs one. **This is not `sdip ingest` and no result below is
reported as one.** It exists to answer the second question: can the pinned upstream convert
this data at all? It can — seven for seven.

### Per-geometry: ingest and equivalence

| Geometry | Template | Traces | Leg 1 — `sdip ingest` | Override | Leg 2 | P1 | P2 | P3 | P4 | P5 | G3 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `streamer_shot_3d` | StreamerShotGathers3D | 128 | `ValueError: Required fields ['cable', 'channel', 'gun'] … not found in the provided segy_spec` | — | ✓ | PASS | PASS | PASS | PASS | PASS | PASS |
| `streamer_shot_3d_wrapped` | StreamerShotGathers3D | 128 | `ValueError: Required fields ['cable', 'channel', 'gun']` | `AutoChannelWrap` | ✓ | PASS | PASS | **FAIL** | **FAIL** | **FAIL** | PASS |
| `streamer_shot_2d` | StreamerShotGathers2D | 192 | `ValueError: Required fields ['channel']` | — | ✓ | PASS | PASS | PASS | PASS | PASS | PASS |
| `streamer_field_3d` | StreamerFieldRecords3D | 128 | `ValueError: Required fields ['cable', 'channel', 'gun', 'sail_line']` | `AutoShotWrap` | ✓ | PASS | PASS | `UntrustedInputError` | `UntrustedInputError` | `UntrustedInputError` | PASS |
| `obn_receiver_3d` | ObnReceiverGathers3D | 64 | `ValueError: Required fields ['gun', 'receiver', 'shot_line']` | `CalculateShotIndex` | ✓ | PASS | PASS | `UntrustedInputError` | `UntrustedInputError` | `UntrustedInputError` | PASS |
| `cdp_offset_3d` | CdpOffsetGathers3DTime | 144 | `ValueError: Required fields ['offset']` | — | ✓ | PASS | PASS | PASS | PASS | PASS | PASS |
| `cdp_offset_2d` | CdpOffsetGathers2DTime | 160 | `ValueError: Required fields ['cdp', 'offset']` | — | ✓ | PASS | PASS | PASS | PASS | PASS | PASS |

Four gather families covered: streamer shot, streamer field record, OBN receiver, CDP
gather — the four the pre-registration names.

### Findings

**F1 — SDIP cannot ingest prestack data at all, and the blocker is a name.** Seven
geometries, seven refusals. The missing names are `cable`, `channel`, `gun`, `sail_line`,
`receiver`, `shot_line`, `offset`, `cdp`. For two of them the blocker is *only* a name:
rev 1 byte 37 is `source_to_receiver_distance`, which **is** offset, and byte 21 is
`ensemble_num`, which **is** the CDP — same bytes, same width, same meaning. `ingest()`
has no parameter that would let a caller say so. **This is the finding that blocks every
prestack workflow and it is untouched by the plane fix.**

**F2 — three geometries additionally need a grid override `ingest()` cannot pass.**
`segy_to_mdio` takes `grid_overrides`; SDIP does not forward one. For
`StreamerFieldRecords3D` and `ObnReceiverGathers3D` the override is not optional: their
`shot_index` dimension is *calculated*, and without it the conversion stops with
`ValueError: Required computed fields ['shot_index'] … not found after grid overrides`. So
a spec-declaration parameter alone would fix four of seven and leave three unreachable.

**F3 — the plane checkers were poststack-only (first reading; since fixed).** All three
per-trace planes hard-coded `{"inline": …, "crossline": …}`. On a streamer store
(`shot_point`, `cable`, `channel`) or a 2-D CDP store (`cdp`, `offset`) the lookup raised
before any comparison. `build_trace_map` itself already took a `dimensions` argument and
generalised correctly; the hard-coding was in the three call sites and nowhere else.

**F4 — the worse variant of F3: `FAIL` returned on bit-exact data (first reading).** A
`CdpOffsetGathers3DTime` store keeps an inline and a crossline axis, so the hard-coded
lookup *succeeded* and then discarded the offset axis. All six offsets in a bin claimed one
cell. `count_matches` passed — the 4-D mask really did hold 144 live cells for 144 source
traces — while `map_invertible`, `no_duplicates` and `mask_matches_map` failed. A `FAIL`
looks like a finding about the conversion and its evidence points at the traces, so this
was more dangerous than the `KeyError`. Fixed in the second reading: the store now passes
all five planes.

**F5 — the data itself is intact.** For the four geometries whose every grid dimension
exists in the source headers, the probe built the §4.6 map directly — same public
`build_trace_map`, store's own dimension coordinates — and compared exactly: map complete
and invertible, **every trace mapped, zero sample mismatches, zero header-field
mismatches**, live mask exactly equal to the mapped cell set. This was written when the
planes could not run and is kept now that they can, as an independent corroboration.
**Prestack was never a data-corruption problem; D4 stays a coverage/performance debt and
does not escalate to a correctness debt.**

**F6 — a Type B streamer store is a real G2 failure, and G3 does not see it.**
`streamer_shot_3d_wrapped` numbers channels 1–16 on cable 1 and 17–32 on cable 2 —
ordinary sequential streamer numbering. With `AutoChannelWrap`, MDIO's
`ChannelWrappingStrategy` rebases each cable to 1–N, so:

- the store's `channel` **dimension coordinate** runs 1–16, and cable 2's channel 17 is
  filed under the label 5;
- the stored `headers` array keeps the original 1–32, so no measured value is lost;
- the §4.6 map built from source header values locates **64 of 128 traces**. Plane 5 fails
  `map_complete`, `map_invertible` and `mask_matches_map`; Planes 3 and 4 fail with it;
- `channel` in the store is a **derived index that appears nowhere in the source**, while
  the certificate's `transforms_declared[]` names only the sample-format decode. Under
  **SP1** that transform is undeclared.

**And G3 passes byte-identically on this store**, because the export reads the `headers`
array. A round trip proves the bytes survived; it says nothing about whether the index a
consumer reads means what it says. Withholding the override is not a fix: the same file
then produces a 4 × 2 × 32 grid with 128 live cells and 128 invented ones — half padding,
sparsity ratio 2.0 (control test included).

**F7 — two geometries have a grid axis with no coordinate array, which leaves G2
unevaluable.** `streamer_field_3d` and `obn_receiver_3d` size their grid along
`shot_index`, a dimension MDIO **calculates** and for which it writes **no coordinate
array at all**: the Zarr metadata declares the dimension and names none of its positions.
A per-trace plane cannot resolve an index-header value against coordinates that do not
exist, so all three raise `UntrustedInputError` naming the missing array rather than
guessing an ordering. `obn_receiver_3d` additionally carries `component`, which is
*fabricated* — MDIO fills a constant 1 for every trace and logs it — a fabricated value
under **SP12**. `shot_index` is *derived* from `shot_point` and is undeclared under
**SP1**. This one is not fixable in the engine: a grid axis with no coordinate is not
addressable, by SDIP or by any other consumer.

**F8 — G3 round trips byte-identically on all seven geometries.**
`sha256(export) == sha256(source)`, whole file, every byte, including the geometry that
fails G2. Read together with F6 this is the probe's most uncomfortable number: **G3 is a
strong statement about the export path and a weak one about the store.** It would pass on
a store whose dimension coordinates were nonsense.

### Chunking — observation only

The chunk shape is the template's own `full_chunk_shape`, applied **verbatim**: never
clipped to the array, never derived from the trace count, never influenced by the file.

| Geometry | `amplitude` shape | `amplitude` chunks | `headers` chunks | chunks stored | SEG-Y bytes | store bytes |
|---|---|---|---|---|---|---|
| `streamer_shot_3d` | (4, 2, 16, 32) | (8, 1, 128, 2048) | (8, 1, 128) | 2 | 50,704 | 37,851 |
| `streamer_shot_3d_wrapped` | (4, 2, 16, 32) | (8, 1, 128, 2048) | (8, 1, 128) | 2 | 50,704 | 37,904 |
| `streamer_shot_2d` | (8, 24, 32) | (16, 32, 2048) | (16, 32) | 1 | 74,256 | 35,075 |
| `streamer_field_3d` | (1, 2, 4, 2, 8, 32) | (1, 1, 16, 1, 32, 1024) | (1, 1, 16, 1, 32) | 4 | 50,704 | 39,049 |
| `obn_receiver_3d` | (1, 8, 1, 2, 4, 32) | (1, 1, 1, 1, 512, 4096) | (1, 1, 1, 1, 512) | 16 | 27,152 | **62,033** |
| `cdp_offset_3d` | (4, 6, 6, 32) | (8, 8, 32, 512) | (8, 8, 32) | 1 | 56,592 | 33,216 |
| `cdp_offset_2d` | (20, 8, 32) | (16, 64, 1024) | (16, 64) | 2 | 62,480 | 33,742 |

Store sizes were measured twice and were identical both times; Blosc/zstd is deterministic
under the pins.

The pattern in the shapes is deliberate rather than careless. Every prestack template pins
its **gather-separating** axes at 1 — `cable`, `sail_line`, `gun`, `component`, `receiver`,
`shot_line` — and spends the whole chunk on the axes *within* a gather. A gather therefore
lands in one chunk and two cables never share one: the right shape for reading a gather,
the wrong one for reading across them. Whether that is the right trade is exactly what the
undeclared latency target would have decided, and it was not decided here.

`obn_receiver_3d` is the one worth flagging: **the only geometry whose store is larger than
its SEG-Y** (62,033 from 27,152 bytes). Its chunk is (…, 512, 4096) over data of (…, 4, 32)
— a chunk 1,024 times the size of the data it holds, sixteen times over.

Nothing in SDIP records the chunk shape on the certificate today, so a store that is
unusable for its access pattern is indistinguishable from one that is not.

### What this probe did not measure

- **Read latency, for any pattern, on any geometry.** No target was ever declared. **SP9.**
- **Whether a rebased `channel` behaves the same at survey scale**, or how a real
  streamer's channel numbering distributes across cables. One Type B fixture, 128 traces.
- **Prestack at scale.** Every fixture here is under 200 traces. P3 owns scale.
- **The remaining prestack templates** — `CdpAngleGathers*`, `CocaGathers3D*`,
  `OffsetTiles3D*`, `ReceiverGathers3D`, `ShotReceiverLineGathers3D`. Their required-field
  sets were enumerated and every one of them is missing at least one name from rev 1, so F1
  applies to them by construction, but none was built or converted.
- **G4 portability, G5, G6 and G7 on a prestack store.** Not run. In particular there is
  **no negative control for the new prestack plane behaviour** — under §5 that is owed
  before the generalised planes can be treated as trustworthy on this geometry.

---

## Results — latency leg, run 2026-08-23

This is the leg the first run reported **NOT RUN**. It is run here against Amendment A
verbatim: nothing in the parameter table was changed, no geometry was dropped, and no
figure is reported for a store whose planes did not pass.

| Field | Value |
|---|---|
| Run date | 2026-08-23 |
| Outcome | **Falsifier does not fire** on the two geometries that clear the correctness precondition. **Not evaluable** on the other two — blocked by clause 1, which fired in the first run and is not closed |
| Runner | `tests/integration/test_p7_latency.py` — 63 tests, all passing; marked `integration` and `slow` |
| Fixtures | `tests/fixtures/generators/prestack.py`, seed `20260822`, synthetic only, unchanged |
| Environment | CPython 3.12.13, macOS 26.5.2 arm64, Apple M3 Max, 14 cores, 36 GiB |
| Pins | `multidimio==1.2.1`, `segy==0.6.0`, `zarr==3.3.0`, `numpy==2.5.2` |
| Barred variables | absent, asserted before anything was built |
| Comparison | exact throughout. No tolerance anywhere in the runner |
| N | 4 geometries × 3 chunk shapes × 4 read patterns × 5 repetitions; 24–144 traces per fixture, all inside the 500-trace budget |
| Host load | **1-minute load average 9.4 on 14 cores.** Other work was running on the machine. Absolute figures are inflated by it; see "What the numbers are worth" |

### The declared parameters, and what was done with each

| Declared | Honoured as |
|---|---|
| Geometries: streamer shot, streamer field record, OBN receiver, CDP gather | `streamer_shot_3d`, `streamer_field_3d`, `obn_receiver_3d`, `cdp_offset_3d` — one fixture per family, the 3-D member in each case |
| 3 chunk shapes per geometry: MDIO's default, gather-contiguous, time-slice-contiguous | Exactly three. Default is the template's own shape, untouched; gather-contiguous pins every gather-separating axis to 1 and takes the within-gather axis and the samples whole; time-slice-contiguous takes every spatial axis whole and pins the sample axis to 1 |
| Read patterns: single gather · offset slice · time slice · full inline | Index expressions derived from **the store's own axis order**, read from Zarr metadata, never assumed. For a CDP-offset store the four are literal. For a streamer store, `offset slice` fixes the channel — the streamer's offset axis — and `full inline` fixes the outermost spatial axis, the sail-line direction |
| Latency target ≤ 2.0 s per read pattern | Applied to the **larger** of the two quantities measured: store-open plus slice |
| 5 repetitions, median reported | Exactly 5. A test asserts the reported figure is `statistics.median` of 5 samples |
| Cache state: cold, dropped between measurements | See below. **It was not fully achievable and the shortfall is stated rather than glossed** |
| Correctness precondition: all five planes PASS first | Enforced mechanically, not by discipline. The code path that produces a figure is unreachable for a store whose planes did not all pass, and a test asserts no figure exists for one |

### What "cold" meant in this run — the honest version

`purge` needs `sudo` on macOS and was not available, so **the OS unified buffer cache was
not dropped.** What was dropped, per repetition: the Zarr group is re-opened from the
path, the array handle is re-acquired, and no array, buffer or decoded chunk is carried
from one repetition into the next. Nothing else.

Every figure below is therefore a **lower bound** on a genuinely cold read, which makes
the comparison against the target **one-sided**: a shape that exceeds 2.0 s with a warm
page cache would exceed it cold, so an exceedance would be real; a figure under 2.0 s
does **not** establish that the same read is under 2.0 s from cold storage. The amendment
declared this leg to catch a pathological shape rather than to rank good ones, and a
lenient one-sided test is sufficient for that and insufficient for anything else.

### Could the chunk shape be varied at all through the public API?

**Yes upstream, no through SDIP, and both halves are results.**

`AbstractDatasetTemplate.full_chunk_shape` is a documented public property with a public
setter, and `get_template` documents that each call returns an independent copy that can
be modified without affecting the registry. Setting it on that copy is enough: three
declared shapes produced three distinct chunk grids on all four geometries, with no
private attribute touched, no subclassing and no patching — §3.3 bars all three, and had
the shape been reachable only that way the correct outcome would have been to measure the
default alone and say so.

`sdip ingest` cannot reach it. `ingest()` takes a template **name** and resolves it
internally, so there is no object on which a caller could set the shape and no parameter
that would carry one. **Every SDIP store today ships whatever shape the template chose,
and nothing on the certificate records which shape that was.** Asserted by
`test_sdip_ingest_offers_no_way_to_choose_a_chunk_shape`.

For the same reason this leg is **not** a run of `sdip ingest` and no figure below is
reported as one. The stores are built exactly as leg 2 of the first run built them — the
geometry's index fields declared, the pinned public `segy_to_mdio`, a grid override where
the template needs one — with the chunk shape set on the template beforehand. That is
what makes the comparison *between shapes* admissible. The §6.4 override mechanism
(`src/sdip/spec/overrides.py`, D-0044) now supplies `offset` and `cdp`, which would carry
the two CDP geometries through `ingest()`; it does not supply the streamer names, and it
cannot supply a `grid_overrides` value at all, so leg 2's construction was still needed
for three of the four and was used for all four to keep them comparable.

### Per-geometry, per-shape, per-pattern

Median of 5 repetitions, milliseconds, **two independent runs reported as `A / B`** so the
run-to-run spread is visible rather than asserted away. `overhang` is chunk-buffer
elements per array element — a structural property of the store, not a latency figure.

| Geometry | Chunk shape | `amplitude` chunks | chunks | store bytes | overhang | planes | single gather | offset slice | time slice | full inline |
|---|---|---|---:|---:|---:|---|---:|---:|---:|---:|
| `streamer_shot_3d` | default (MDIO) | `(8, 1, 128, 2048)` | 2 | 37,851 | 1,024x | 5/5 PASS | 6.5 / 13.7 | 6.5 / 13.5 | 6.6 / 13.6 | 6.4 / 11.5 |
| `streamer_shot_3d` | gather-contiguous | `(1, 1, 16, 32)` | 8 | 35,019 | 1x | 5/5 PASS | **1.1 / 1.3** | 2.2 / 2.7 | 2.0 / 2.3 | 1.1 / 1.3 |
| `streamer_shot_3d` | time-slice-contiguous | `(4, 2, 16, 1)` | 32 | 38,179 | 1x | 5/5 PASS | 6.1 / 7.3 | 6.7 / 7.1 | **1.1 / 1.3** | 7.2 / 6.6 |
| `streamer_field_3d` | default (MDIO) | `(1, 1, 16, 1, 32, 1024)` | 4 | 39,049 | 512x | **blocked** | — *no figure* | — *no figure* | — *no figure* | — *no figure* |
| `streamer_field_3d` | gather-contiguous | `(1, 1, 1, 1, 8, 32)` | 16 | 38,670 | 1x | **blocked** | — *no figure* | — *no figure* | — *no figure* | — *no figure* |
| `streamer_field_3d` | time-slice-contiguous | `(1, 2, 4, 2, 8, 1)` | 32 | 40,312 | 1x | **blocked** | — *no figure* | — *no figure* | — *no figure* | — *no figure* |
| `obn_receiver_3d` | default (MDIO) | `(1, 1, 1, 1, 512, 4096)` | 16 | 62,033 | **16,384x** | **blocked** | — *no figure* | — *no figure* | — *no figure* | — *no figure* |
| `obn_receiver_3d` | gather-contiguous | `(1, 1, 1, 1, 4, 32)` | 16 | 38,238 | 1x | **blocked** | — *no figure* | — *no figure* | — *no figure* | — *no figure* |
| `obn_receiver_3d` | time-slice-contiguous | `(1, 8, 1, 2, 4, 1)` | 32 | 37,458 | 1x | **blocked** | — *no figure* | — *no figure* | — *no figure* | — *no figure* |
| `cdp_offset_3d` | default (MDIO) | `(8, 8, 32, 512)` | 1 | 33,216 | 228x | 5/5 PASS | 6.4 / 5.7 | 6.1 / 4.8 | 5.0 / 4.9 | 4.7 / 5.0 |
| `cdp_offset_3d` | gather-contiguous | `(1, 1, 6, 32)` | 24 | 34,995 | 1x | 5/5 PASS | **3.6 / 1.6** | 14.6 / 7.1 | 8.0 / 6.6 | 2.6 / 2.8 |
| `cdp_offset_3d` | time-slice-contiguous | `(4, 6, 6, 1)` | 32 | 36,327 | 1x | 5/5 PASS | 8.0 / 7.7 | 7.6 / 7.7 | **1.4 / 1.4** | 7.7 / 7.4 |

`blocked` is the declared correctness precondition, not an omission: **all five planes must
PASS before a latency figure means anything, and on these two geometries Planes 3, 4 and 5
raise `UntrustedInputError`.** That is F7 from the first run, unchanged and not a chunking
problem — `streamer_field_3d` and `obn_receiver_3d` size their grid along `shot_index`, a
dimension MDIO calculates and writes **no coordinate array for**, so a per-trace plane has
nothing to resolve an index-header value against. No chunk shape reaches it. The stores
were still built at all three shapes, and their planes still run, so the block is shown to
be shape-independent rather than assumed to be.

The store-open cost sits under every figure as a floor of roughly 0.6–0.9 ms and does not
vary with the chunk shape; it is included in the reported figure because the target is
better applied to the larger quantity. Slice-only medians for run A, in milliseconds:

| Geometry | Chunk shape | single gather | offset slice | time slice | full inline |
|---|---|---:|---:|---:|---:|
| `streamer_shot_3d` | default | 5.69 | 5.72 | 5.81 | 5.66 |
| `streamer_shot_3d` | gather-contiguous | 0.49 | 1.55 | 1.41 | 0.55 |
| `streamer_shot_3d` | time-slice-contiguous | 5.46 | 6.01 | 0.49 | 6.50 |
| `cdp_offset_3d` | default | 4.67 | 4.35 | 3.77 | 3.56 |
| `cdp_offset_3d` | gather-contiguous | 2.08 | 11.40 | 6.56 | 1.70 |
| `cdp_offset_3d` | time-slice-contiguous | 7.06 | 6.78 | 0.62 | 6.88 |

### Verdict against the declared falsifier

> **Falsifier for this leg:** no chunk shape meeting the declared target for a geometry.

**`streamer_shot_3d` — DOES NOT FIRE.** All three candidate shapes meet ≤ 2.0 s on all
four patterns. Worst median across both runs: 13.7 ms, which is 146x inside the target.

**`cdp_offset_3d` — DOES NOT FIRE.** All three candidate shapes meet ≤ 2.0 s on all four
patterns. Worst median across both runs: 14.6 ms, 137x inside the target.

**`streamer_field_3d` and `obn_receiver_3d` — NOT EVALUABLE.** No shape has a figure,
because the declared correctness precondition forbids one, because clause 1 of the
original falsifier fired on both in the first run and is not closed. Reading this as the
latency falsifier firing would credit a chunking finding to a coordinate-array finding;
reading it as a pass would claim a measurement that does not exist. **Neither is claimed.**
The leg is therefore **partially run**: two geometries of four measured, two blocked
upstream of measurement, and the block is stated rather than routed around. The route
around it exists and was not taken — `MDIO_IGNORE_CHECKS` is barred (§9.1), and so is
inventing an ordering for a dimension that declares none.

**The worst overhang in the run belongs to a geometry that can carry no figure.**
`obn_receiver_3d`'s default chunk is 16,384x the data it holds, it is the only store in
this probe larger than its own SEG-Y, and it is precisely the geometry the precondition
bars from publishing a latency number. That is the precondition working as declared: the
fix there is a coordinate array, not a benchmark.

### Findings

**F9 — the pre-registered gate is silent, and the ordering underneath it is not.** Every
figure in the run is between 137x and 1,800x inside the declared 2.0 s, so the target
separates nothing. What separates cleanly is the ordering: **each purpose-built shape
beats MDIO's default on the pattern it was built for, on both measurable geometries, in
every run, by 1.8x to 10.9x.** The amendment predicted this in advance — 2.0 s was
declared "deliberately generous … meant to catch a *pathological* shape, not to rank good
ones" — and that is exactly how it behaved. **The target was not the useful instrument;
the comparison was.** A future prestack chunking gate should be registered as a
*relative* criterion, and it must be registered before it is measured.

**F10 — MDIO's default prestack chunk overhangs every one of these fixtures, by 228x to
16,384x.** A chunk is decoded whole: when the declared chunk is larger than the array, the
reader allocates and decompresses the entire buffer to return the corner of it that holds
data. `StreamerShotGathers3D` declares `(8, 1, 128, 2048)` over a `(4, 2, 16, 32)` array —
an 8 MiB buffer decoded to return 512 values. This is a property of the shape against the
grid, not of the disk, which is why it survives a warm page cache and shows up as the
5.7 ms floor under every default-shape read in the table. It is also the mechanism behind
the first run's observation that `obn_receiver_3d`'s store is larger than its SEG-Y.

**F11 — the shape that wins one pattern loses another, and the loss is measurable.**
Gather-contiguous is the fastest shape for a single gather on both geometries and the
*slowest* for an offset slice on `cdp_offset_3d` (14.6 ms against 6.1 ms for the default —
a constant-offset section touches every gather chunk in the survey). Time-slice-contiguous
inverts it. There is no shape here that wins everything, so **prestack chunking is a
declared trade against a stated access pattern, and it is a trade SDIP currently makes
silently on the user's behalf and records nowhere.**

**F12 — nothing records which shape a store was written with.** Repeated from the first
run because this leg strengthens it from an observation to a consequence: the certificate
carries no chunk manifest, `sdip ingest` accepts no chunk parameter, and two stores that
differ by a factor of ten in read cost are indistinguishable in the record. A store that
is unusable for its access pattern still certifies as equivalent — correctly, because it
*is* equivalent. Equivalence and usability are different claims and the certificate only
makes one of them.

### What the numbers are worth

The host was running other work: 1-minute load average 9.4 on 14 cores. That inflates the
absolute figures and is visible in the run-to-run spread — `streamer_shot_3d`'s default
shape reads 6.5 ms in run A and 13.7 ms in run B, a factor of two on the same store and
the same code. **No absolute figure here should be quoted as a latency of anything.** The
ordering is treated as the finding because it is measured within a single process against
the same load, and it reproduced in every run: three exploratory and two reported.

Restating the scope limit the amendment set in advance, because the result does not
weaken it: this is **relative behaviour on small synthetic fixtures.** It is not a
production latency claim; a shape that wins here is not thereby validated at survey scale;
and cold-cache behaviour on real storage is not measured at all. That would need P3-class
compute and its own pre-registration.

### What this leg did not measure

- **A genuinely cold read.** The OS page cache was not dropped. Stated above; it is the
  single largest gap in this leg.
- **Two of the four declared geometries.** `streamer_field_3d` and `obn_receiver_3d`
  cannot clear the correctness precondition, so the falsifier is not evaluable for them.
  The leg is partially run and is reported as such.
- **The 2-D fixtures and `streamer_shot_3d_wrapped`.** The amendment declares four
  geometries and they are four *families*; one 3-D fixture stands for each.
  `streamer_shot_3d_wrapped` is a measured G2 failure (F6) and could carry no figure under
  the precondition regardless.
- **Any shape other than the declared three.** No search, no tuning, no best-of. Three
  candidates were declared and three were measured.
- **Store-open cost at scale, and metadata cost with many chunks.** The 0.6–0.9 ms floor
  observed here is a constant of these fixtures, not of the format.
- **Whether `sdip ingest` should expose a chunk parameter.** F12 states the gap. Closing
  it is a design decision with a certificate consequence — a chunk manifest is a new
  certificate field — and belongs in `DECISIONS.md`, not in a probe.
