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
