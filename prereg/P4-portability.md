# P4 — Cross-implementation portability

| Field | Value |
|---|---|
| Probe | `P4` · Status `REGISTERED` · Registered 2026-08-22 |
| Blocks | non-Python consumers |
| Related debt | `OPEN_DEBTS.md` D3 · Gate **G4** · Spec §7 G4, §10.3 |

## Question

Can a **non-Python** Zarr implementation read an SDIP store — specifically the
`headers` array?

## Why it matters

§10.3 is the reason adopting SDIP is a reversible decision: consumers read the store
with stock tooling and **no consumer is required to install `sdip` or `mdio`**. G4
asserts that in Python. Whether it holds outside Python is unmeasured.

## Known risk — already measured

From Appendix A.1, read from each array's `zarr.json`:

| Array | `data_type` | Zarr v3 core spec? |
|---|---|---|
| `amplitude` | `float32` | ✅ core |
| `inline`, `crossline`, `time` | `int32` | ✅ core |
| `trace_mask` | `int8` | ✅ core |
| `cdp_x`, `cdp_y` | `float64` | ✅ core |
| **`headers`** | **`{"name": "struct"}`** | ❌ **extension — no v3 specification** |

`zarr-python` raises `UnstableSpecificationWarning` for it; MDIO suppresses that
warning — and the suppression leaks process-globally, measured in `DECISIONS.md`
D-0004. SDIP records the suppression on the certificate and detects the condition
directly from `zarr.json` instead of relying on the warning.

**Everything a consumer needs except the headers is already core-spec and portable.**
The risk is confined to one array.

## Method

Read the same store from at least two non-Python implementations:

- **zarr-java**
- **zarr-rs**
- **TensorStore** (C++/Python bindings; counts as non-`zarr-python`)

For each: open the group, list arrays, read `amplitude` and one coordinate array, then
attempt `headers`. Record exactly which operation fails and with what error.

## Pre-registered parameters

| Parameter | Value |
|---|---|
| Store | The P1 30-trace article, byte-for-byte, plus one larger store if P3 has run |
| Implementations | zarr-java, zarr-rs, TensorStore — versions recorded at run time |
| Success criterion | Group opens; every core-spec array reads bit-identically to the Python read |
| Comparison | Byte equality on the raw buffers. **No tolerance.** |

## Falsifier

**Headers unreadable outside Python.**

Note what is *not* a falsifier: a non-Python implementation failing on a **core-spec**
array. That would be a bug in that implementation, and would be reported there — not a
finding against SDIP. The probe tests SDIP's output, not other people's readers.

## If it fires — pre-approved mitigation

Write a **parallel `(n_traces, 240)` `uint8` header plane** alongside the structured
one.

- Measured cost ≈ **19 B/trace** (Appendix A.3) — the same as the structured array,
  because it is the same bytes.
- Fully **core-spec**: a 2-D `uint8` array is as portable as Zarr gets.
- Better shaped for ML consumption than a structured dtype.

**It is cheap enough that adopting it unconditionally is defensible without waiting for
this probe.** That is a maintainer decision (§12.1) and would be recorded in
`DECISIONS.md`.

---

## Results — appended 2026-08-22, never edited into the sections above

| Field | Value |
|---|---|
| Run date | 2026-08-22 |
| Run commit | `fbece9eed93a51b7486dc0aee940676a3987fbb7`, working tree dirty with concurrent unrelated work. A probe run is not a certificate; §3.5 binds `sdip certify`, not this. |
| Harness | `tests/integration/test_p4_crossimpl.py` — 17 tests, all passing, 4.9 s |
| Store | The P1 30-trace article, rebuilt from `tests.fixtures.generators.make_poststack3d` at defaults (seed 20260822) and ingested by `sdip.ingest.ingest`. 5 IL × 6 XL × 32 samples = 30 traces. |
| Environment | Python 3.12.13 · `tensorstore` 0.1.85 · `zarr-python` 3.3.0 · `numpy` 2.5.2 · `multidimio` 1.2.1 · `segy` 0.6.0 · macOS 26.5 arm64 |
| Comparison | `numpy.array_equal` **and** `ndarray.tobytes()` equality, plus dtype and shape. No tolerance. |
| Verdict | **The falsifier did not fire.** The method was only partly executed — see *Scope*. |

### Implementations

| Implementation | Language | Ran? | Note |
|---|---|---|---|
| **TensorStore 0.1.85** | C++, Python bindings | **Yes** | Compiled extension `tensorstore/_tensorstore.cpython-312-darwin.so`, asserted by the harness (**SP11**): the bindings are a shim, the `zarr.json` parser and codec pipeline are C++ that shares nothing with `zarr-python`. Apache-2.0, added to `[dependency-groups] dev` — **test-only**; the runtime tree is unchanged at 51 distributions and `sdip doctor`'s licence scan still passes. |
| zarr-java | Java | **No** | No JRE on the runner (`/usr/bin/java` is the macOS stub). CI has no network beyond the pinned package index, so a JDK cannot be fetched. **Unmeasured.** |
| zarr-rs | Rust | **No** | No `cargo`/`rustc` on the runner, same network constraint. **Unmeasured.** |

The pre-registration asked for **at least two**. One ran. That is recorded here rather
than papered over, and it is the reason this probe narrows **D3** without closing it.

`zarrs-python` was considered and rejected as a substitute: it supplies a Rust *codec
pipeline* to `zarr-python`, which keeps doing the metadata parsing. The falsifier is
about a `data_type`, so a reader that borrows `zarr-python`'s dtype handling cannot
answer it.

### Per-array measurement — TensorStore `zarr3` driver

| Array | `data_type` | v3 core? | Opens | Reads | Byte-identical to `zarr-python` |
|---|---|---|---|---|---|
| `amplitude` | `float32` | yes | ✅ | ✅ `(5,6,32)` | ✅ |
| `inline` | `int32` | yes | ✅ | ✅ `(5,)` | ✅ |
| `crossline` | `int32` | yes | ✅ | ✅ `(6,)` | ✅ |
| `time` | `int32` | yes | ✅ | ✅ `(32,)` | ✅ |
| `trace_mask` | `int8` | yes | ✅ | ✅ `(5,6)` | ✅ |
| `cdp_x` | `float64` | yes | ✅ | ✅ `(5,6)` | ✅ |
| `cdp_y` | `float64` | yes | ✅ | ✅ `(5,6)` | ✅ |
| **`headers`** | **`struct`** | **no** | ✅ *with a field selector* | ✅ **97 / 97 fields** | ✅ **97 / 97** |
| **`segy_file_header`** | **`fixed_length_utf32`** | **no** | ❌ | ❌ | n/a — array payload is empty, see below |

**7 / 7 core-spec arrays** read bit-identically. Per the pre-registration this was never
where the risk was, and it is reported because an unchecked success criterion is not a
criterion.

### `headers` — the falsifier's own array

Opening it with no field selector raises, and the error is the finding:

```
FAILED_PRECONDITION: Error opening "zarr3" driver: Must specify a "field" that is
one of: ["trace_seq_num_line","trace_seq_num_reel","orig_field_record_num", … ]
```

**This is not the falsifier firing.** TensorStore parsed the extension `data_type`,
understood all 97 fields, and enumerated them by name; it declines to guess which one is
wanted. A reader that could not comprehend the dtype could not list its members. With a
field supplied:

- **97 of 97 fields read**, every one equal to the `zarr-python` read on values, dtype,
  shape **and raw bytes**. N = 30 traces per field — 97 reads, 2,910 values compared.
- **Header bytes 233–240** — the eight `uint8` fillers the rev 1 standard leaves
  uncovered, and the ones a sparse spec silently drops — were compared not against
  `zarr-python` but against the **planted ground truth in the source SEG-Y**: 8 fields ×
  30 traces = 240 values, all matching. That makes this evidence rather than two readers
  agreeing with each other.

The access model differs — one projection per field, no whole-record read — but §10.3's
claim is that the bytes are recoverable outside Python, and they are.

### `segy_file_header` — a real rejection that costs nothing

```
Error parsing object member "data_type": fixed_length_utf32 data type is not one of
the supported data types: bool, int2, int4, int8, uint8, int16, …, complex128, r<N>
```

TensorStore refuses the array outright. Measured consequence: **none.**

- The array's data is a **zero-length scalar string** (`shape ()`, `<U0`, value `""`).
  There is nothing in the chunks to lose.
- Everything of value is in the node's **attributes**: MDIO's parsed `textHeader` /
  `binaryHeader`, and SDIP's authoritative `sdipRawTextHeader` /
  `sdipRawBinaryHeader` (§4.3). Attributes are JSON inside `zarr.json`.
- Recovered through **TensorStore's own `KvStore`** — so the claim is that TensorStore
  reaches them, not merely that a JSON file exists on disk — giving **3,200 textual
  bytes and 400 binary bytes**, both matching the source file and both verified against
  the `…Sha256` attributes the store carries.

**Planes 1 and 2 are fully recoverable outside Python.** The unreadable dtype guards an
empty box.

### Non-vacuity

Most of the 97 SEG-Y header fields are zero in this fixture, so "the two reads agree" is
a shape that several ways of being wrong would satisfy. The harness carries a permanent
negative control: one field is changed in a copy of the store through `zarr-python`, so
the chunk is legitimately re-encoded rather than corrupted, and the C++ reader must see
the change. It does — and the neighbouring field stays identical, so the control
localises rather than firing on everything (§7 G7's killer, `DECISIONS.md` D-0028).

### Verdict against the pre-registered falsifier

> **Headers unreadable outside Python.**

**It did not fire.** A C++ Zarr implementation that shares no code with `zarr-python`
read all 97 fields of the structured `headers` array byte-identically, and recovered the
planted rev-1-uncovered tail bytes to match the source SEG-Y.

The pre-registration's exclusion was not needed: **no core-spec array failed**, so
nothing here is a bug to report against another project.

### Scope — read this before citing P4

- **One implementation, not two.** zarr-java and zarr-rs are unmeasured. `struct` has
  **no Zarr v3 specification**, so TensorStore's support is an implementation choice,
  not conformance — a reader that declines it is standards-conformant and would still be
  right. This probe shows the dtype *can* be read outside Python; it cannot show it
  *will* be.
- **N = 30 traces, one revision, one geometry, local filesystem.** Scale is P3, revisions
  P6, geometry P5, object stores P8.
- **`fixed_length_utf32` was rejected by the same reader that accepted `struct`.** That
  is a same-run demonstration that extension-dtype support is per-implementation, and it
  is the most load-bearing thing this run produced.

### On the pre-approved mitigation — parallel `(n_traces, 240)` `uint8` header plane

**The evidence supports adopting it, but not for the reason the pre-registration
anticipated.** The falsifier did not fire, so the mitigation is not *forced*. What the
run did produce is a direct observation that an extension `data_type` in this same store
was refused by this same reader. Portability of `headers` therefore rests on one
implementation's goodwill toward an unspecified dtype, and a `uint8` plane replaces that
with a guarantee: a 2-D `uint8` array is as portable as Zarr gets, and it removes the
field-at-a-time access model as well.

**The cost figure is not re-derived here and should not be quoted from this run.** The
`headers` chunk on this article is 1,018 bytes for 30 traces; at N = 30 the Blosc block
overhead dominates and no per-trace compressed cost can honestly be inferred. The
Appendix A.3 ≈ 19 B/trace figure stands on its own measurement, and confirming it at
scale belongs to **P3**.

Adoption is a maintainer decision under §12.1 and is not taken here.

### Recorded in

`OPEN_DEBTS.md` D3 — **narrowed, not closed.** `DECISIONS.md` — pending a maintainer
ruling on the mitigation.

---

## Results, leg 2 — zarr-java — appended 2026-08-23, never edited into the sections above

| Field | Value |
|---|---|
| Run date | 2026-08-23 |
| Run commit | `f23a1e576a3d256367014e4f09ef2cbdcf920d1b`, working tree dirty with concurrent unrelated work. A probe run is not a certificate; §3.5 binds `sdip certify`, not this. |
| Harness | `local/p4java/` — a Maven project (`probe/`) that reads the store from the JVM and writes every array out as JSON, plus `compare.py`, which does the comparison in Python. Deliberately **not** in `tests/`: CI has no JDK and no network beyond the pinned package index, so a Java-dependent test would be a test that never runs. `local/` is in the publication firewall and is never committed. |
| Store | The P1 30-trace article, from `tests.fixtures.generators.make_poststack3d` at defaults (seed 20260822) and ingested by `sdip.ingest.ingest`. 5 IL × 6 XL × 32 samples = 30 traces. Source SEG-Y SHA-256 `be4ce4375799b8ebc670526229581e73d995f03a8a3bb308141f41fc91bdd762`, 14,640 B. Read-only throughout; the store was not modified. |
| Environment | zarr-java 0.2.0 · JDK 26.0.2.1 (Homebrew, aarch64) · Maven 3.9.16 · zarr-python 3.3.0 · numpy 2.5.2 · Python 3.12.13 · macOS 26.5 arm64 |
| Comparison | Byte equality on raw value buffers **and** `numpy.array_equal`, plus dtype and shape. No tolerance. |
| Verdict | **The falsifier did not fire** — and zarr-java did not read `headers`. Those two statements are compatible; see *Verdict* below, which does not soften either one. |

### What ran, and what it cost to get it running

| Item | Value |
|---|---|
| Maven coordinates | `dev.zarr:zarr-java:0.2.0` |
| Licence | MIT — no copyleft exposure, and it is a `local/` test-only artifact regardless |
| Published | 2026-07-29; the latest release on Maven Central at run time |
| Extra repository | `https://artifacts.unidata.ucar.edu/repository/unidata-all/`, needed for `edu.ucar:cdm-core:5.9.1`, a zarr-java transitive that is not on Maven Central |
| Codecs | JNI, not pure Java: `com.scalableminds:blosc-java:0.3-1.21.6` (c-blosc 1.21.6) and `com.github.luben:zstd-jni:1.5.5-7` |
| Native libraries | None had to be built. The bundled `libbloscjni.dylib` is a universal Mach-O carrying arm64. |
| Resolution | Clean on the first attempt. No build was fought. |

Nothing was added to `pyproject.toml`, to CI, or to `tests/`. The Python runtime dependency
tree is unchanged.

### Independence — SP11, stated with its limit

zarr-java runs in a separate OS process on the JVM. The metadata parser is Jackson-driven
Java (`dev.zarr.zarrjava.v3.ArrayMetadata`), the chunk-grid arithmetic and buffer assembly
are Java, and the array container is `ucar.ma2` from netCDF-Java. None of that is
`zarr-python`, so a `data_type` failure — the thing this probe is about — is decided by
code that shares nothing with the Python read.

The limit, stated because leaving it out would overclaim: **the innermost decompression is
not independent.** `blosc-java` is a JNI wrapper over c-blosc 1.21.6; `numcodecs` wraps
c-blosc 1.21.7.dev. Different builds of the same C library. The same caveat applies to leg
1, where TensorStore vendors its own c-blosc. What *is* independent is every layer above
the decompressor, and that is where a portability failure lives.

### Per-array measurement — zarr-java 0.2.0

| Array | `data_type` | v3 core? | Opens | Reads | Byte-identical to `zarr-python` |
|---|---|---|---|---|---|
| `amplitude` | `float32` | yes | yes | yes `(5,6,32)` | yes — 3,840 B |
| `inline` | `int32` | yes | yes | yes `(5,)` | yes — 20 B |
| `crossline` | `int32` | yes | yes | yes `(6,)` | yes — 24 B |
| `time` | `int32` | yes | yes | yes `(32,)` | yes — 128 B |
| `trace_mask` | `int8` | yes | yes | yes `(5,6)` | yes — 30 B |
| `cdp_x` | `float64` | yes | yes | yes `(5,6)` | yes — 240 B |
| `cdp_y` | `float64` | yes | yes | yes `(5,6)` | yes — 240 B |
| **`headers`** | **`struct`** | **no** | **no** | **no** | n/a — refused at metadata parse |
| **`segy_file_header`** | **`fixed_length_utf32`** | **no** | **no** | **no** | n/a — refused at metadata parse; array payload is empty |

**7 / 7 core-spec arrays** read bit-identically: 1,093 values, 4,522 bytes of array payload.
Both Blosc/Zstd and bare Zstd chunks decoded correctly, and `trace_mask`'s `bytes` codec —
written with **no** `configuration` object, which the v3 spec permits for a single-byte
data type — was handled without complaint.

Per the pre-registration this is not where the risk was, and it is reported because an
unchecked success criterion is not a criterion.

### How the comparison avoids a tolerance by construction

The Java side never emits a decimal number. Each array leaves the JVM as base64 of its raw
**little-endian value bytes in C order** — byte-for-byte the layout `ndarray.tobytes()`
produces on this host — so no float repr sits anywhere in the path where an epsilon could
hide. The Python side asserts `py.tobytes() == java_bytes`, then rebuilds an array from
those same bytes and asserts `numpy.array_equal`, plus dtype and shape. Host
little-endianness is asserted as an explicit precondition, because the byte comparison
would otherwise be meaningless rather than merely wrong.

### `headers` — the falsifier's own array

```
com.fasterxml.jackson.databind.exc.MismatchedInputException:
Cannot deserialize value of type `dev.zarr.zarrjava.v3.DataType` from Object value
(token `JsonToken.START_OBJECT`)
 (through reference chain: dev.zarr.zarrjava.v3.ArrayMetadata["data_type"])
```

The failure is in `Array.open`, during metadata deserialization. zarr-java never reaches a
chunk. `dev.zarr.zarrjava.v3.DataType` is a **closed Java enum of the eleven Zarr v3 core
types**; `{"name": "struct"}` is a JSON object where that enum expects a string, so Jackson
rejects the document. There is no field-selector escape hatch of the kind TensorStore
offered in leg 1 — the type system has nowhere to put a `struct`.

**"Cannot type it" is not "cannot see it,"** and the two were separated deliberately.
Reading the same `zarr.json` through zarr-java's own `FilesystemStore`/`StoreHandle` and
parsing it with zarr-java's own bundled Jackson reports `data_type.name == "struct"` and
enumerates **all 97 field names**, `trace_seq_num_line` through `pad_240`. The bytes are on
disk and the schema is legible as JSON. What is missing is any mapping from that schema
into zarr-java's type system.

**This is not the falsifier firing.** `struct` has **no Zarr v3 specification**. A reader
that declines an unspecified `data_type` is standards-conformant and is still right. What
this leg adds is a second, independent data point that support for the dtype is
**per-implementation goodwill** rather than conformance — and the two legs now disagree
with each other about the same array in the same store:

| Reader | `struct` (`headers`) | `fixed_length_utf32` (`segy_file_header`) |
|---|---|---|
| TensorStore 0.1.85 (C++) | accepts — 97/97 fields, byte-identical | refuses |
| zarr-java 0.2.0 (JVM) | refuses | refuses |
| `zarr-python` 3.3.0 | accepts, with `UnstableSpecificationWarning` | accepts |

Three readers, three different answers about which extension dtypes exist. That is the
argument for the pre-approved `uint8` header plane, stated as an observation rather than an
inference: portability of `headers` currently depends on which reader a consumer happens to
have, and a 2-D `uint8` array does not.

### A cost leg 1 could not have found: the group cannot be listed at all

`dev.zarr.zarrjava.v3.Group.open()` succeeds and returns the root attributes
(`apiVersion 1.2.1`, `name PostStack3DTime`, survey type, gather type). **`Group.list()` /
`listAsArray()` then fails outright**:

```
java.lang.RuntimeException: Failed to read node metadata for key
'segy_file_header/zarr.json': Cannot deserialize value of type
`dev.zarr.zarrjava.v3.DataType` from Object value (token `JsonToken.START_OBJECT`)
```

`list()` opens **every** child node, so one unparsable `data_type` takes the whole listing
down. A zarr-java consumer cannot enumerate the store through the group API — not even to
reach the seven arrays it is perfectly able to read.

The store is still usable, one level lower. `StoreHandle.listChildren()` performs a key
listing with no metadata parsing and returns all nine array names plus `zarr.json`; each
core array then opens by name. **Every core-spec measurement in the table above was taken
that way.** So the practical position for a Java consumer is: the data is fully available,
but the consumer must either know the array names or list keys rather than nodes.

Two things follow, and the second matters more than the first:

1. This is a portability cost the extension dtypes impose on arrays that have nothing to do
   with them. It is invisible to a reader without a group abstraction, which is why leg 1
   could not have produced it.
2. **The `uint8` header plane would not fix it on its own.** Replacing `struct` removes one
   of the two unparsable children; `segy_file_header`'s `fixed_length_utf32` is the other,
   and `Group.list()` stays broken while either remains. Anyone citing the mitigation as a
   portability fix should cite it for the `headers` bytes, not for group listing.

### `segy_file_header` — same refusal as leg 1, same measured cost of nothing

Refused for the same reason: `fixed_length_utf32` is not in the enum. Measured consequence:
**none.**

- The array has **no chunk directory on disk** — `segy_file_header/` contains `zarr.json`
  and nothing else. There is no payload to lose.
- Everything of value is in the node's **attributes**, which are plain JSON inside
  `zarr.json` and survive a `data_type` no reader can parse.

Recovered through **zarr-java's own store layer**, so the claim is that zarr-java reaches
them and not merely that a JSON file exists on disk:

| Quantity | Measured |
|---|---|
| `sdipRawTextHeader` | 3,200 B, byte-identical to source SEG-Y bytes 1–3200 |
| `sdipRawBinaryHeader` | 400 B, byte-identical to source SEG-Y bytes 3201–3600 |
| `sdipRawTextHeaderSha256` | matches `sha256` of the recovered Plane 1 |
| `sdipRawBinaryHeaderSha256` | matches `sha256` of the recovered Plane 2 |

**Planes 1 and 2 are fully recoverable from zarr-java.** This is the second implementation
to confirm it, and it confirms D-0021's consequence directly: storing the raw planes as
base64 attributes rather than array payload made them strictly more portable than any
array-based storage could be, because attributes need only a JSON parser.

### Non-vacuity

Every check above has the shape "the two reads agree," which several ways of being wrong
would satisfy. The harness therefore carries a negative control: in a **copy** of the store,
one `amplitude` sample is set to `-424242.0` through `zarr-python`, so the chunk is
legitimately re-encoded rather than corrupted, and the JVM reader must see the change.

- It does: the `amplitude` buffer differs, and the planted value reads back exactly.
- It **localises**: the untouched `cdp_x` buffer stays byte-identical, so the control fails
  its own target and not everything (§7 G7's killer, `DECISIONS.md` D-0028).

`compare.py` runs 55 checks and exits non-zero on any failure. All 55 pass.

`uv run pytest -q` was re-run afterwards: **617 passed, 1 failed.** The failure is
`test_p4_crossimpl.py::test_the_store_is_the_one_the_probe_registered`, leg 1's fixture
guard, and it is **not** caused by this leg — see the last bullet under *Scope*. Nothing in
leg 2 touches `src/`, `tests/`, `pyproject.toml`, or CI; its only tracked change is this
file.

### Verdict against the pre-registered falsifier

> **Headers unreadable outside Python.**

**It did not fire, and this leg does not revive it.** The falsifier is a universal claim,
and leg 1 already produced the counterexample: TensorStore read all 97 fields
byte-identically. One reader that can read them settles whether they *can* be read outside
Python. A second reader that cannot does not un-settle it.

What the second leg changes is the strength of the practical guarantee, and this is the
number to quote rather than the verdict:

**Of the two non-Python implementations now measured, `headers` is readable by one and not
the other.** Core-spec arrays are readable by both, byte-identically, with no exceptions.

The pre-registration's exclusion was again not needed: **no core-spec array failed**, so
nothing here is a bug to report against another project. `Group.list()` failing is not a
zarr-java defect either — it is the documented consequence of a store containing a
`data_type` that no specification defines.

### Method status

P4's method asked for **at least two** non-Python Zarr implementations. **Two have now
run** — TensorStore 0.1.85 (C++) and zarr-java 0.2.0 (JVM). **The method is satisfied as
pre-registered.**

`zarr-rs` remains unrun. The pre-registration said "at least two," so its absence does not
hold the method open, and it is recorded here rather than quietly dropped. A third leg
would add most value if it disagreed with both of the first two.

### Scope — read this before citing leg 2

- **N = 30 traces, one revision, one geometry, local filesystem, one host architecture.**
  Scale is P3, revisions P6, geometry P5, object stores P8. Nothing here speaks to any of
  them.
- **One version of one implementation.** zarr-java 0.2.0's `DataType` enum is closed today;
  a later release could add extension dtypes, and that would change this result without
  changing SDIP.
- **The decompressor lineage is shared with `zarr-python`** (c-blosc, different builds).
  Independence is claimed for the metadata and dtype layers, which is where the question
  lives, and not for the codec's innermost C.
- **No cost figure is derived here.** Nothing in this leg measures bytes per trace.
- **The store measured has exactly nine arrays** — the seven core-spec ones plus `headers`
  and `segy_file_header` — and was built 2026-08-22 19:32, byte-identical to leg 1's
  fixture. Leg 1's `test_the_store_is_the_one_the_probe_registered` is the tripwire for
  that assumption, and **at the time of this run it was failing**: concurrent, unrelated
  in-flight work adds a tenth array, `amplitude_raw_ibm32`, to every newly ingested store.
  A store rebuilt from the recipe below today would therefore not be the store measured
  here. That is a note for whoever reproduces this, not a finding against either leg —
  neither leg's numbers involve the tenth array.

### What this does to D3

**D3 stays `OPEN`, and the reason it stays open has changed from unmeasured to measured.**

D3's narrowing entry of 2026-08-22 gave two reasons for keeping it open. This leg
**discharges the first and confirms the second**:

1. *"Only one implementation ran."* — **Discharged.** Two have now run; P4's method is
   satisfied.
2. *"`struct` has no Zarr v3 specification, so TensorStore's support is an implementation
   choice rather than conformance."* — **Confirmed, no longer an inference.** A second
   non-Python reader in the same store refuses the same array outright. What was an
   argument from the specification is now an observation.

Newly measured and load-bearing for D3: **the extension dtypes also break group listing in
zarr-java**, and the `uint8` header plane does not fix that by itself while
`segy_file_header` keeps `fixed_length_utf32`.

Appending this to `OPEN_DEBTS.md` D3 and any ruling on the mitigation are separate
append-only records under SP10 and §12.1, and are **not made here** — this file is the
probe's record, not the debt ledger.

### Reproducing leg 2

`local/` is never committed, so this is the recipe rather than a pointer to committed code.
It needs a JDK, Maven, and network access to Maven Central and the Unidata repository, none
of which CI has.

```
export PATH="/opt/homebrew/opt/openjdk/bin:$PATH"   # JDK 26 + Maven 3.9.16
uv run python - <<'EOF'                             # __main__ guard: MDIO uses spawn
import pathlib
from tests.fixtures.generators import make_poststack3d
from sdip.ingest import ingest
if __name__ == "__main__":
    out = pathlib.Path("local/p4java"); out.mkdir(parents=True, exist_ok=True)
    a = make_poststack3d(out / "src.sgy")
    ingest(a.path, out / "store" / "poststack.mdio", overwrite=True)
EOF
# local/p4java/probe/pom.xml declares dev.zarr:zarr-java:0.2.0 and the Unidata repository;
# local/p4java/probe/src/main/java/sdip/P4ZarrJava.java dumps every array as JSON.
uv run python local/p4java/compare.py                # invokes Maven, then compares
```

---

## Addendum — appended 2026-08-23, re-banked after the store changed under the result

**SP10.** The measurement above is not withdrawn and is not edited. It was correct for
the store as it existed at run commit `fbece9ee`. The store has since gained an array,
so the table above is **scoped to pre-D1 stores** and this entry supersedes its counts.

**What changed.** The D1 remedy (`OPEN_DEBTS.md` D1, probe P2's *"if it fires"* clause)
made `sdip.ingest.raw_samples` write a parallel **`amplitude_raw_ibm32`** array —
undecoded big-endian IBM sample words, `uint32`, shaped like `amplitude`, written with
stock `zarr`. It is conditional: it exists only when the source's sample format is
`ibm32`, which the Appendix A.1 article's is. The fixture guard
`test_the_store_is_the_one_the_probe_registered` failed on the array count, which is
what it was written to do.

**Re-measured, not inherited.** The D1 author supplied a measurement of this leg. It is
not banked here on their word (**SP8**): the store was rebuilt and the array read again
through the same `_open_with_tensorstore` path as every other array in this probe.

| Array | `data_type` | v3 core? | Opens | Reads | Byte-identical to `zarr-python` |
|---|---|---|---|---|---|
| **`amplitude_raw_ibm32`** | **`uint32`** (plain string) | **yes** | ✅ | ✅ `(5,6,32)` | ✅ |

- `data_type` is the JSON string `"uint32"`, so it is core-spec and **adds nothing to the
  extension set**. The two extension arrays are still exactly `headers` and
  `segy_file_header`.
- Equal on `numpy.array_equal`, `tobytes()`, dtype and shape. No tolerance.
- **560 distinct words across 960 cells** — worth recording because an all-zero array
  would satisfy "the two reads agree" without the reader decoding anything.
- Codecs `bytes` + `blosc`, unchanged from the rest of the store.

**Revised counts.** Core-spec arrays **8 / 8** byte-identical, was 7 / 7. Store holds ten
arrays, was nine. Harness is **18 tests passing**, was 17.

**Nothing else moves.** The `headers` result (97 / 97 fields), the `segy_file_header`
rejection, the non-vacuity control and the verdict below are untouched — the new array is
core-spec, and the falsifier is about an extension `data_type`.

**The falsifier verdict is unchanged: it did not fire.**

Notably, D1 made the store *more* portable, not less: the only recoverable copy of the
raw IBM source bits landed as a core-spec `uint32` array rather than behind an extension
dtype. Had it been written as a big-endian float extension type, this probe would be
reporting a second `fixed_length_utf32`-shaped hole.

| Field | Value |
|---|---|
| Re-run date | 2026-08-23 |
| Re-run commit | `f23a1e576a3d256367014e4f09ef2cbdcf920d1b`, working tree dirty with concurrent unrelated work |
| Environment | Unchanged: `tensorstore` 0.1.85 · `zarr-python` 3.3.0 · `numpy` 2.5.2 · `multidimio` 1.2.1 · `segy` 0.6.0 |
| Scope | Unchanged. Still one implementation, N = 30 traces, one revision, one geometry, local filesystem. **D3 stays narrowed, not closed.** |

---

## Pre-registration, leg 3 — zarr-java on `headers_raw_uint8` — appended 2026-10-31, before the run

**SP9.** This section is committed before the run. The results go in a later section,
appended after it, and are never edited into this one.

| Field | Value |
|---|---|
| Leg | P4 leg 3 |
| Registered | 2026-10-31 |
| Registered by | Claude Code session, on GeoSuite's relay of owner D-216 ("every plan and debt proceeds") |
| Related debt | `OPEN_DEBTS.md` D3 |
| Spec clause | §7 G4, §10.3 |
| Push | The commit is local. The workspace's top ruling forbids a push without the owner's command, so "committed and pushed before the run" holds only as "committed before the run". Stated, not bent. |

### Question

Can the JVM reader that refused `headers` (zarr-java 0.2.0) read the `uint8` header
plane `headers_raw_uint8`, opened by path, so that every live trace's 240 header bytes
it returns equal the source SEG-Y's bytes?

### Why it matters

D-0051 built `headers_raw_uint8` as P4's pre-approved mitigation, so that trace headers
do not depend on a reader accepting the `struct` extension dtype. Its portability has
been measured through one non-Python reader only: TensorStore, in
`tests/integration/test_p4_crossimpl.py`. TensorStore also accepts `struct`, so that
crossing cannot show the mitigation doing its job. zarr-java is the reader the
mitigation exists for. Leg 2 ran on 2026-08-23 against a store that did not yet contain
the plane, so whether the mitigation works for the one reader that needs it is unmeasured.

### Method

1. **Stores, built through the product.** Two sources from committed generators, each
   ingested with the `sdip ingest` executable at defaults (template `PostStack3DTime`)
   and the source's own `--revision`:
   - `make_poststack3d` at defaults (seed 20260822): 5 IL × 6 XL × 32 samples, 30
     traces, a full grid.
   - `make_sparse_grid`: a padded grid, so padding cells exist and the live mask is
     exercised.
2. **Reader.** zarr-java 0.2.0 (`dev.zarr:zarr-java:0.2.0`, same as leg 2) on the
   Homebrew OpenJDK, in a separate JVM process. It opens `headers_raw_uint8` **by path**
   (`Array.open`), never through `Group.list()` (D32: listing fails, accepted). It also
   opens `trace_mask` by path. Each array leaves the JVM as base64 of its raw bytes in C
   order, so no number is ever printed in decimal. The harness lives in `local/p4java3/`
   (publication firewall, never committed); its full Java source and comparator are
   copied into the results section so the run can be repeated from this file.
3. **Comparison, in Python, no tolerance.**
   - (a) zarr-java bytes of `headers_raw_uint8` == `zarr-python` `tobytes()` of the same
     array, plus `numpy.array_equal`, dtype `uint8` and shape `(*grid, 240)`.
   - (b) For every cell where `trace_mask` is true (from zarr-java's own read), the
     240-byte row equals the source file's trace header bytes, read by the comparator by
     fixed offset (3600 + k × (240 + n_samples × 4)) and matched to the cell through
     the source's own inline/crossline at bytes 189–192 / 193–196. This does not use
     SDIP's reader.
   - (c) The count of live cells equals the source's trace count, and every source trace
     maps to exactly one live cell.
   - Padding cells (mask false) are **not** compared to anything (SP12). Their count is
     reported.
4. **Non-vacuity (SP11).**
   - In a **copy** of the poststack store, one byte of one live cell's row is changed
     through `zarr-python` (XOR `0xFF`, so the chunk is re-encoded, not corrupted). The
     JVM read must show the change at exactly that cell and byte, and every other byte
     must stay identical to the original read.
   - Rows must not all be equal. The count of distinct live rows is reported. An
     all-identical plane would satisfy (b) without the reader decoding anything that
     varies per trace.
5. **The product's own verdict.** `sdip verify` on each store must report PASS. This
   shows the stores are correct SDIP stores, not that zarr-java can read them.

### Pre-registered parameters

| Parameter | Value |
|---|---|
| N | Exhaustive: every cell of both stores, every source trace |
| Threshold | Byte equality on every compared byte. No tolerance |
| Reader | zarr-java 0.2.0, Homebrew OpenJDK (version recorded at run time) |
| Python side | the repository's locked environment (`uv run`), `zarr` 3.3.0 |
| Geometry | poststack 3D only. Prestack is **out of scope** and stays out of scope for this leg |

### Falsifier

**zarr-java fails to open or read `headers_raw_uint8` by path, or any byte it returns
for a live cell differs from the source SEG-Y's byte at that offset.**

### If it fires

D3 stays OPEN, reason changed to "the mitigation does not reach the JVM reader". The
failure (exception text or the differing cells) is recorded in the results and in D3.
Nothing is fixed in this leg, and nothing is filed upstream (D-0089).

### If it does not fire

D3 closes, scoped: trace-header **data** is byte-identically readable by both measured
non-Python readers through `headers_raw_uint8`. The structured `headers` array keeps the
`struct` extension dtype. That is upstream's format and is left as it is. Group listing in
zarr-java remains the accepted limit D32. The closure is recorded as a new append-only
entry in `OPEN_DEBTS.md`, scoped to N, geometry, reader version and local filesystem.


---

## Results, leg 3 — zarr-java on `headers_raw_uint8` — appended 2026-10-31, never edited into the sections above

| Field | Value |
|---|---|
| Run date | 2026-10-31 |
| Run commit | `841ae6d` (the registration commit), clean tree, worktree on branch `d3-zarr-java-header-plane` |
| Harness | `local/p4java3/` (firewall, deleted after harvest): Maven project `probe/` plus `compare.py`. Full source below |
| Receipt | `prereg/P4-leg3-receipt-2026-10-31.json`: source, array and harness SHA-256s |
| Environment | zarr-java 0.2.0 · OpenJDK 26.0.2.1 (Homebrew, aarch64) · Maven, offline against the local repository · `zarr-python` 3.3.0 · `multidimio` 1.2.1 · `segy` 0.6.0 · macOS arm64 |
| Stores | Built with the `sdip` executable: `sdip ingest --revision 1`, then `sdip verify --revision 1` → **PASS**, five planes plus G4, on both |
| Verdict | **The falsifier did not fire.** 25 checks, 0 failed |

### Measured

| Store | Source SHA-256 | `headers_raw_uint8` shape | Live / padding | Rows compared to source | Differ | Distinct rows |
|---|---|---|---|---|---|---|
| `make_poststack3d` defaults | `be4ce437…dd762` (leg 2's source, byte-identical) | `(5, 6, 240)` | 30 / 0 | 30 × 240 B | **0** | 30 |
| `make_sparse_grid` | `a27df132…ee32` | `(9, 9, 240)` | 27 / 54 | 27 × 240 B | **0** | 27 |

- zarr-java opened `headers_raw_uint8`, `trace_mask`, `inline` and `crossline` **by path**
  on both stores. `headers_raw_uint8` came back as ma2 `ubyte`.
- (a) zarr-java's bytes equal `zarr-python`'s for all four arrays on both stores: 7,200 B
  and 19,440 B of header plane, plus `array_equal`, dtype and shape.
- (b) Every live row equals the source file's 240 trace-header bytes. The bytes were read by
  fixed offset and matched to the row through the source's own bytes 189–196. SDIP's reader
  was not used.
- (c) The live cells match the source traces one to one on both stores. The 54 padding
  cells were not compared (SP12).
- **Control:** in a copy of the poststack store, byte 17 of cell `(2, 3)` was XORed with
  `0xFF` through `zarr-python`. The JVM read differed from the original at exactly
  `[[2, 3, 17]]`, by exactly that XOR.

### Verdict against the pre-registered falsifier

> zarr-java fails to open or read `headers_raw_uint8` by path, or any byte it returns for
> a live cell differs from the source SEG-Y's byte at that offset.

**It did not fire.** The reader that refuses `headers` reads the mitigation, byte for byte
against the source. With leg 1's TensorStore crossing
(`tests/integration/test_p4_crossimpl.py`), **both measured non-Python readers now read
trace-header data byte-identically through `headers_raw_uint8`.** By the pre-registered
outcome, D3 closes, scoped.

### Scope — read this before citing leg 3

- N = 57 traces in two poststack 3D stores, revision 1, `ibm32`, local filesystem, one
  host. Prestack geometries were not read by zarr-java.
- One version of one implementation (zarr-java 0.2.0).
- The structured `headers` array is unchanged and zarr-java still refuses it. The mitigation
  works around it and does not fix it.
- Group listing in zarr-java still fails (D32, accepted). A consumer must open arrays by name.
- The decompressor is not independent of `zarr-python`'s, as in leg 2 (c-blosc under both).

### Reproducing leg 3

Needs a JDK, Maven and (on a cold Maven cache) network access to Maven Central and the
Unidata repository. From the repository root:

```
mkdir -p local/p4java3/probe/src/main/java/sdip   # put the three files below in place
uv run python - <<'PY'
from pathlib import Path
from tests.fixtures.generators import make_poststack3d
from tests.fixtures.generators.irregular import make_sparse_grid
if __name__ == "__main__":
    make_poststack3d(Path("local/p4java3/post.sgy")); make_sparse_grid(Path("local/p4java3/sparse.sgy"))
PY
cd local/p4java3
for s in post sparse; do uv run sdip ingest --revision 1 $s.sgy $s.mdio; uv run sdip verify --revision 1 $s.sgy $s.mdio; done
(cd probe && PATH=/opt/homebrew/opt/openjdk/bin:$PATH mvn -q compile)
cd ../.. && uv run python local/p4java3/compare.py
```

`local/p4java3/probe/pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 http://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>sdip</groupId>
  <artifactId>p4-leg3</artifactId>
  <version>1</version>
  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>
  <repositories>
    <repository>
      <id>unidata</id>
      <url>https://artifacts.unidata.ucar.edu/repository/unidata-all/</url>
    </repository>
  </repositories>
  <dependencies>
    <dependency>
      <groupId>dev.zarr</groupId>
      <artifactId>zarr-java</artifactId>
      <version>0.2.0</version>
    </dependency>
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <groupId>org.codehaus.mojo</groupId>
        <artifactId>exec-maven-plugin</artifactId>
        <version>3.5.0</version>
        <configuration><mainClass>sdip.P4Leg3</mainClass></configuration>
      </plugin>
    </plugins>
  </build>
</project>
```

`local/p4java3/probe/src/main/java/sdip/P4Leg3.java`:

```java
package sdip;

import dev.zarr.zarrjava.store.FilesystemStore;
import dev.zarr.zarrjava.v3.Array;

import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Base64;

/** P4 leg 3: open named arrays BY PATH (never Group.list) and dump raw C-order bytes as base64. */
public final class P4Leg3 {
    public static void main(String[] args) throws Exception {
        String store = args[0];
        Path out = Path.of(args[1]);
        StringBuilder sb = new StringBuilder("{");
        for (int i = 2; i < args.length; i++) {
            String name = args[i];
            if (i > 2) sb.append(',');
            sb.append('"').append(name).append("\":{");
            try {
                Array a = Array.open(new FilesystemStore(store).resolve(name));
                ucar.ma2.Array v = a.read();
                int[] shape = v.getShape();
                Object j = v.copyTo1DJavaArray();
                byte[] raw;
                if (j instanceof byte[] b) {
                    raw = b;
                } else if (j instanceof int[] ints) {
                    ByteBuffer bb = ByteBuffer.allocate(ints.length * 4).order(ByteOrder.LITTLE_ENDIAN);
                    for (int x : ints) bb.putInt(x);
                    raw = bb.array();
                } else {
                    throw new IllegalStateException("unhandled java type " + j.getClass());
                }
                sb.append("\"ok\":true,\"ma2_type\":\"").append(v.getDataType()).append("\",\"shape\":[");
                for (int k = 0; k < shape.length; k++) { if (k > 0) sb.append(','); sb.append(shape[k]); }
                sb.append("],\"b64\":\"").append(Base64.getEncoder().encodeToString(raw)).append('"');
            } catch (Throwable t) {
                String msg = String.valueOf(t).replace("\\", "\\\\").replace("\"", "\\\"").replace("\n", "\\n");
                sb.append("\"ok\":false,\"error\":\"").append(msg).append('"');
            }
            sb.append('}');
        }
        sb.append('}');
        Files.writeString(out, sb.toString());
    }
}
```

`local/p4java3/compare.py`:

```python
"""P4 leg 3 comparator. Runs zarr-java (separate JVM), compares with no tolerance."""
import base64, json, os, shutil, subprocess, sys
from pathlib import Path
import numpy as np
import zarr

HERE = Path(__file__).resolve().parent
ENV = dict(os.environ, PATH="/opt/homebrew/opt/openjdk/bin:" + os.environ["PATH"])
ARRAYS = ["headers_raw_uint8", "trace_mask", "inline", "crossline"]
DT = {"headers_raw_uint8": np.uint8, "trace_mask": np.int8, "inline": "<i4", "crossline": "<i4"}
checks = []

def check(name, ok, detail=""):
    checks.append((name, bool(ok)))
    print(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail else ""))

def jvm_read(store, tag):
    out = HERE / f"jvm_{tag}.json"
    out.unlink(missing_ok=True)
    args = " ".join([str(store), str(out), *ARRAYS])
    subprocess.run(["mvn", "-o", "-q", "exec:java", f"-Dexec.args={args}"],
                   cwd=HERE / "probe", env=ENV, check=True)
    res = json.loads(out.read_text())
    arrs = {}
    for n in ARRAYS:
        r = res[n]
        if not r["ok"]:
            arrs[n] = r["error"]
            continue
        a = np.frombuffer(base64.b64decode(r["b64"]), dtype=DT[n]).reshape(r["shape"])
        arrs[n] = (a, r["ma2_type"])
    return arrs

def source_headers(sgy):
    b = Path(sgy).read_bytes()
    ns = int.from_bytes(b[3220:3222], "big")
    fmt = int.from_bytes(b[3224:3226], "big")
    ext = int.from_bytes(b[3504:3506], "big", signed=True)
    assert fmt in (1, 5) and ext == 0, (fmt, ext)
    stride = 240 + ns * 4
    n = (len(b) - 3600) // stride
    assert 3600 + n * stride == len(b)
    rows = {}
    for k in range(n):
        h = b[3600 + k * stride: 3600 + k * stride + 240]
        il = int.from_bytes(h[188:192], "big", signed=True)
        xl = int.from_bytes(h[192:196], "big", signed=True)
        assert (il, xl) not in rows
        rows[(il, xl)] = np.frombuffer(h, dtype=np.uint8)
    return rows

def leg(tag, sgy, store):
    print(f"--- {tag}: {store.name}")
    jv = jvm_read(store, tag)
    for n in ARRAYS:
        check(f"{tag}: zarr-java opens and reads {n} by path", not isinstance(jv[n], str),
              jv[n] if isinstance(jv[n], str) else f"ma2 {jv[n][1]}, shape {jv[n][0].shape}")
    if any(isinstance(jv[n], str) for n in ARRAYS):
        return None
    g = zarr.open_group(str(store), mode="r")
    py = g["headers_raw_uint8"][...]
    jh = jv["headers_raw_uint8"][0]
    check(f"{tag}: (a) dtype uint8 and shape (*grid,240)", py.dtype == np.uint8 and py.shape[-1] == 240 and jh.shape == py.shape, f"{py.shape}")
    check(f"{tag}: (a) zarr-java bytes == zarr-python bytes", jh.tobytes() == py.tobytes() and np.array_equal(jh, py), f"{py.nbytes} B")
    for n in ("trace_mask", "inline", "crossline"):
        check(f"{tag}: (a) {n} identical across readers", np.array_equal(jv[n][0], g[n][...]))
    mask = jv["trace_mask"][0].astype(bool)
    il, xl = jv["inline"][0], jv["crossline"][0]
    src = source_headers(sgy)
    live = list(zip(*np.nonzero(mask)))
    mapped = {(int(il[i]), int(xl[j])): (i, j) for i, j in live}
    check(f"{tag}: (c) live cells == source traces, one-to-one", len(live) == len(src) and set(mapped) == set(src),
          f"live {len(live)}, source {len(src)}, padding {mask.size - len(live)}")
    bad = [k for k, (i, j) in mapped.items() if k in src and not np.array_equal(jh[i, j], src[k])]
    check(f"{tag}: (b) every live row == source trace header bytes", not bad and len(mapped) == len(src),
          f"{len(mapped)} rows x 240 B compared, {len(bad)} differ")
    distinct = len({jh[i, j].tobytes() for i, j in live})
    check(f"{tag}: rows vary per trace (not vacuous)", distinct > 1, f"{distinct} distinct of {len(live)}")
    return jh, live

if __name__ == "__main__":
    post = leg("post", HERE / "post.sgy", HERE / "post.mdio")
    leg("sparse", HERE / "sparse.sgy", HERE / "sparse.mdio")
    # Non-vacuity: flip one byte of one live row in a COPY, through zarr-python.
    jh0, live = post
    copy = HERE / "post_flipped.mdio"
    shutil.rmtree(copy, ignore_errors=True)
    shutil.copytree(HERE / "post.mdio", copy)
    (i, j), byte = live[len(live) // 2], 17
    arr = zarr.open_array(str(copy / "headers_raw_uint8"), mode="r+")
    row = arr[i, j, :]
    row[byte] ^= 0xFF
    arr[i, j, :] = row
    jv = jvm_read(copy, "flipped")
    jh1 = jv["headers_raw_uint8"][0]
    diff = np.argwhere(jh1 != jh0)
    check("control: JVM sees the flip at exactly that cell and byte",
          diff.tolist() == [[int(i), int(j), byte]] and jh1[i, j, byte] == (jh0[i, j, byte] ^ 0xFF),
          f"differing positions {diff.tolist()}")
    shutil.rmtree(copy)
    n_fail = sum(not ok for _, ok in checks)
    print(f"{len(checks)} checks, {n_fail} failed")
    sys.exit(1 if n_fail else 0)
```
