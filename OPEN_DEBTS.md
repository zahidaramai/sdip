# OPEN DEBTS — append-only

**SP10.** Append-only. A debt is closed by a **new entry** recording the measurement
that closed it, citing the original. Entries are never edited or deleted.

**Debts are scheduled, never cancelled.** Specification Appendix B is the v1.0
snapshot; this file is the live copy.

| Status | Meaning |
|---|---|
| `OPEN` | Unmeasured. Anything built on top of it is built on an assumption. |
| `NARROWED` | Still open, but the scope has been reduced by a measurement. |
| `CLOSED` | A measurement closed it. The closing entry names the number. |

---

## D1 — `ibm32` invertibility unverified across the full exponent range

- **Status:** `NARROWED` (2026-08-22)
- **Blocks:** production ingest of `ibm32`-bearing data
- **Probe:** P2 · **Spec:** §4.4, SP1

IBM's 24-bit fraction fits IEEE binary32's 24-bit significand, so the mantissa argument
is clean. IBM's base-16 exponent (≈16^±64) exceeds float32's range (≈1.2e-38 to
3.4e38): overflow → `inf`, underflow → subnormal or zero. Legacy tapes are the
population at risk.

**Narrowing, `DECISIONS.md` D-0003.** No SEG-Y standard trace header the pinned `segy`
exposes — rev 0, 1, 2, 2.1 — declares a single `ibm32` field. The header leg of P2 can
therefore only be reached through a survey spec override (§6.4) that declares one, and
such an override must not be accepted until P2 has cleared.

**The sample-format leg is untouched and remains fully blocking.**

---

## D2 — Scale behaviour unmeasured

- **Status:** `OPEN`
- **Blocks:** production, and any claim about the project's contribution
- **Probe:** P3 · **Spec:** §7 G5, §11.2

Everything banked in Appendix A was measured on a **30-trace** synthetic article
(5 inlines × 6 crosslines × 32 samples, 14,640 bytes). Thirty traces is not a survey.
Nothing about memory ceilings, checkpointing, wall clock, or chunk behaviour at survey
scale has been observed.

Declare the memory ceiling and wall clock **before** the run (**SP9**).

---

## D3 — `headers` array cross-implementation portability unknown

- **Status:** `OPEN`
- **Blocks:** non-Python consumers
- **Probe:** P4 · **Spec:** §7 G4, §10.3

Measured (Appendix A.1): the `headers` array is written with on-disk
`data_type = {"name": "struct"}`, which is **not in the Zarr v3 core specification**.
`amplitude`, `inline`, `crossline`, `time`, `trace_mask`, `cdp_x`, and `cdp_y` are all
core-spec dtypes and portable. Whether zarr-java, zarr-rs, or TensorStore can read the
`headers` array is unknown.

**Pre-approved mitigation** (§8, P4): write a parallel `(n_traces, 240)` `uint8` header
plane alongside the structured one — ≈19 B/trace measured, fully core-spec, and better
shaped for ML consumption. Cheap enough that adopting it unconditionally is defensible
without waiting for P4.

---

## D4 — Prestack chunking policy unmeasured

- **Status:** `OPEN`
- **Blocks:** prestack workflows
- **Probe:** P7 · **Spec:** §6.5

Poststack retains the upstream default `(128, 128, 128)` until measured otherwise.
Prestack chunking is `UNMEASURED`. **Do not guess in production.**

---

## D5 — Irregular geometry and duplicate handling untested

- **Status:** `OPEN`
- **Blocks:** any real survey
- **Probe:** P5 · **Spec:** §4.6, SP12

Dead traces, duplicate index tuples, sparse and ragged grids, missing lines,
coordinate-scalar edge cases (zero, positive, negative), byte-swapped and rev 0 files.
A silent overwrite of a duplicate, or padding leaking into Plane 4, is a **SP12**
violation, not a rough edge.

---

## D6 — rev 0 / 2 / 2.1 untested end to end

- **Status:** `NARROWED` (2026-08-22)
- **Blocks:** legacy vintages
- **Probe:** P6 · **Spec:** §5

**Narrowing, `DECISIONS.md` D-0003.** The gap-free construction has been measured
statically for every revision: rev 0 needs 60 fillers (71 → 131 fields), rev 1 needs 8
(89 → 97), and **rev 2 and rev 2.1 are already gap-free as shipped** (90 fields,
240/240 bytes, zero fillers). G1 is satisfiable on all four.

What remains open is what P6 actually asks: an **ingest and a round trip** per
revision. Static coverage is not an ingest.

---

## D7 — Cloud object store path untested

- **Status:** `OPEN`
- **Blocks:** cloud deployment
- **Probe:** P8 · **Spec:** §11.2

S3, GCS, Azure ingest and read. Auth, retry, partial-write recovery,
checkpoint-on-write. A harness that can return nothing after hours is a defect.

---

## D8 — Fuzz corpus for untrusted-input handling not built

- **Status:** `OPEN`
- **Blocks:** public release
- **Spec:** §11.4

SDIP parses binary files it did not create. A malformed or hostile SEG-Y must produce a
clean, typed error — never a crash, an unbounded allocation, or a write outside the
output path. Header-declared lengths must be validated against actual file size
**before** allocation. No output path may be derived from file content.

---

## D9 — Upstream pin commit SHAs are declared, not runtime-verified

- **Status:** `OPEN` (raised 2026-08-22)
- **Blocks:** the strength of the `env` block on every certificate
- **Spec:** §3.3, §4.7, SP8

`sdip doctor` verifies the installed **version** exactly. It cannot verify the commit
SHA: an installed wheel does not carry the SHA it was built from. Every certificate
therefore records the SHA as `"sha_verification": "declared-not-runtime-verified"`,
and `doctor --json` says so in its evidence block.

This is a real gap between what §3.3 pins and what the tooling can attest. The
artifact hashes in `uv.lock` are the strongest available substitute and are not yet
checked at runtime.

**Candidate closure:** verify the installed distributions' `RECORD` hashes against the
`uv.lock` artifact hashes in `doctor`, and state clearly that this attests *the
artifact*, not *the commit*. A commit-level attestation needs a source build or an
upstream provenance attestation, and neither is available under the current pins.

---

## D10 — Upstream leaks a process-global warnings filter

- **Status:** `OPEN` (raised 2026-08-22)
- **Blocks:** nothing in SDIP; it is an upstream finding to report (§3.3)
- **Spec:** SP6 · **Decision:** `DECISIONS.md` D-0004

`multidimio` 1.2.1's `zarr_warnings_suppress_unstable_structs_v3` and
`zarr_warnings_suppress_unstable_numcodecs_v3` (`mdio/core/zarr_io.py:20`, `:31`) call
`warnings.filterwarnings("ignore", …)` without `warnings.catch_warnings()` and end in
`finally: pass`. **Measured:** entering both once takes `len(warnings.filters)` from 10
to 12 and leaves it there — a caller that enters either one is permanently deafened to
those warnings for the remainder of the process.

SDIP contains the leak inside its own guarded calls and records the suppression on the
certificate (D-0004). The upstream defect is not routed around silently: it is to be
raised as an issue, per §3.3.

**Closure:** upstream scopes the filters, or SDIP records that it will not be fixed.

---

## D11 — G7 has not run; every certificate the engine would issue is unvalidated

- **Status:** `OPEN` (raised 2026-08-22)
- **Blocks:** **certificate issuance in every form**
- **Spec:** §7 G7, SP11 · **Phase:** F4

**A gate a corrupted store passes is not a gate.** No negative control exists yet,
because no gate exists yet. This debt is listed explicitly rather than left implicit in
the roadmap, so that no report, docstring, or commit message can describe the engine as
trustworthy before F4 completes.

Any report touching certificates must say so.

---

## D13 — The specification is not distributed with the public repository

- **Status:** `OPEN` (raised 2026-08-22)
- **Blocks:** nothing technical; it is a completeness gap in the public artifact
- **Decision:** `DECISIONS.md` D-0010

`docs/` is never published (D-0010), so a reader of the public repository cannot follow
a `§4` or `§7` reference to its source. Every rule the specification imposes on a
contribution is restated in `README.md`, `CONTRIBUTING.md`, and `DECISIONS.md`, and
`CONTRIBUTING.md` says so and invites an issue where a rule is missing from all three.

That restatement is **maintained by hand**, which means it can drift. Nothing currently
checks that a rule cited by section number is actually stated somewhere a public reader
can reach.

**Candidate closure:** either publish a redacted specification cleared against the
firewall, or add a check that every `§N` citation in a public file resolves to a rule
stated in a public file.

---

## D12 — Copyright holder and IP provenance unresolved

- **Status:** `OPEN` (raised 2026-08-22)
- **Blocks:** **the first public push.** Nothing technical.

`NOTICE` carries the literal placeholder `<<UNRESOLVED-COPYRIGHT-HOLDER>>` and CI has a
`publication-readiness` job that **fails while the placeholder is present**, so the
repository cannot be published with it unresolved by accident.

Who owns the `LICENSE` copyright line and the `NOTICE` attribution — individual or
employer — determines whether the repository can be published at all and under whose
name. It must be settled before the first public commit, not after.

The technical specification is complete and correct regardless of how this resolves.
It affects the name on the repository, not the contents of it.

---

## D12 — CLOSED 2026-08-22 — copyright holder resolved

- **Closes:** D12 above, which is left in place unedited (**SP10**)
- **Decision:** `DECISIONS.md` D-0011

The holder is **Zahid Aramai**, personally. `NOTICE` and `CITATION.cff` carry the name;
the `<<UNRESOLVED-COPYRIGHT-HOLDER>>` placeholder is gone and the
`publication-readiness` CI job passes. The repository is published at
`github.com/zahidaramai/sdip`.

**Not closed by this entry:** the employment-policy clearance the internal companion
§6 pairs with the copyright decision. That is a legal question this repository cannot
observe, and D-0011 says so explicitly rather than implying it was settled.

---

## D14 — Green CI does not mean the gates pass

- **Status:** `OPEN` (raised 2026-08-22)
- **Blocks:** nothing; it is a standing risk of misreading
- **Decision:** `DECISIONS.md` D-0012

The five gate jobs report `NOT_RUN` while their subject does not exist, so the build is
green with **zero gates enforced**. This is deliberate — an always-failing job would
block the PR that builds the gate (D-0012) — but it means a reader who checks only the
badge learns nothing about equivalence.

Mitigations in place: the `roadmap` CI job writes all seven gate states into every run
summary; `README.md` states the current phase and what was measured; **D11** records
that until G7 passes every certificate is unvalidated.

**Closure:** all seven gates built and enforcing, at which point green means what a
reader assumes it means.

---

## D12 — FULLY CLOSED 2026-08-22 — clearance attested

- **Closes:** the remaining half of D12, left open by the closure entry above
- **Decision:** `DECISIONS.md` D-0013

The maintainer attests that SDIP is personal work created outside the scope of any
employment and is clear to publish under a personal identity. Both halves of the
internal companion §6 pairing — copyright holder and employment-policy clearance — are
now recorded and dated.

No automated check verifies the attestation, and none could. It is recorded so the basis
for publication is written down rather than assumed.

---

## D9 — NARROWED 2026-08-22 — artifact and installed-file verification added

- **Narrows:** D9 above, left in place unedited (**SP10**)
- **Decision:** `DECISIONS.md` D-0016

Three claims are now made and kept separate: **version** verified exactly, **artifact
sha256** read from `uv.lock` where `uv sync --frozen` enforces it at install time, and
**145 installed files** recomputed against the wheels' own `RECORD` manifests.

**Still open, and this is the whole of what remains:** none of it attests that the wheel
was built from the declared commit. A wheel does not carry the SHA it was built from.
Closing that needs a source build or an upstream provenance attestation, neither of
which exists under the current pins. `commit_sha_verified` stays `False` everywhere, and
a test asserts it so a future change has to edit that assertion deliberately.

---

## D10 — REPORTED 2026-08-22 — upstream issue filed

- **Concerns:** D10 above; the debt stays `OPEN`
- **Decision:** `DECISIONS.md` D-0017

Filed as [TGSAI/mdio-python#864](https://github.com/TGSAI/mdio-python/issues/864),
discharging the §3.3 obligation to report rather than merely route around. Every claim
in the report was re-verified against the pinned code immediately before posting.

**The debt does not close on being reported.** It closes when upstream fixes it — at
which point SDIP's containment in `guard/warn.py` should be re-read to see what is still
needed — or when upstream declines, at which point that is recorded and the containment
becomes permanent.

---

## D15 — The certificate schema had no published copy

- **Status:** `CLOSED` 2026-08-22
- **Decision:** `DECISIONS.md` D-0015

Spec §4.7 requires the certificate schema published so a third party can validate SDIP
output without running SDIP. D-0010 made `docs/` unpublishable and the only copy lived
there, so the requirement was **silently unsatisfiable** — `git ls-files` returned
nothing — and F8's "published certificate schema" deliverable was unreachable.

Closed by moving it to `src/sdip/schema/`, tracked and shipped in both wheel and sdist.
Recorded as a debt rather than a plain fix because it was a **requirement quietly
unmet**, not a task not yet started, and that failure mode is worth having on the record.

---

## D16 — Appendix A.1 lists an array a default ingest does not produce

- **Status:** `OPEN` (raised 2026-08-22)
- **Decision:** `DECISIONS.md` D-0019

Specification Appendix A.1 lists `segy_file_header` among the arrays produced by the
banked P1 run. Reproducing that article with a default `segy_to_mdio` on the pinned
versions produces **no such array**: `MDIOSettings.save_segy_file_header` defaults to
`0`.

Either A.1 was run with the setting enabled and did not record that, or upstream's
default changed between the measurement and the pin. **Unresolved, and recorded rather
than resolved:** the appendix is frozen (§12.4), and guessing which explanation is right
would be exactly the assumption SP8 forbids.

**Closure:** re-run the A.1 article under both settings and record which reproduces the
listed array set.

---

## D17 — Plane 1 does not yet preserve an undecodable textual header

- **Status:** `OPEN` (raised 2026-08-22)
- **Blocks:** ingest of non-conforming legacy vintages
- **Decision:** `DECISIONS.md` D-0020

§4.2 requires that where bytes cannot be decoded, the **raw 3200 bytes are preserved and
the decode failure is recorded on the certificate** — *"decode failure is not an
ingestion failure."*

SDIP preserves the raw bytes (D-0021), so half of that holds. But upstream mode 1
**raises** on a malformed text header, so the ingest fails rather than completing with
the failure recorded. Mode 2 would complete, by silently rewriting the header, which
§4.2 bars outright.

Neither upstream mode matches §4.2. SDIP currently takes the safe half: refuse rather
than corrupt.

**Closure:** capture and store the raw textual header **before** invoking the converter
and let the ingest proceed with `decode_status: raw_preserved_decode_failed` on the
certificate — the schema already has that enum value. Needs a fixture with a genuinely
non-conforming header, which is probe **P5** territory.

---

## D11 — CLOSED 2026-08-22 — G7 exists, runs per store, and passes

- **Closes:** D11 above, left in place unedited (**SP10**)
- **Decision:** `DECISIONS.md` D-0027, D-0028, D-0029

D11 said: *"A gate a corrupted store passes is not a gate. No negative control exists
yet, because no gate exists yet."* Both halves are now false.

**G7 is an executable gate**, not a test suite: `sdip certify` corrupts copies of the
store it is certifying, re-runs every checker, and records the outcome on that store's
certificate. Measured on the 30-trace article: baseline clean, **8 corruptions each
failing exactly the gates it declares and no others**, plus G3's own control. `PASS`.

**It found a real defect on its first run** — Planes 1 and 2 shared a validating reader,
so truncating the textual header also failed G2b, which §7 G7 names as a killer
(*"one that fails the wrong gate"*). Fixed in D-0028. The engine had been green on
synthetic data, green on 116,532 real traces, and byte-identical on round trip, and still
had two non-independent planes. Nothing but this gate would have caught it.

**What stays open.** G7 passing here is not G7 passing at survey scale under a declared
ceiling — that is **P3**, and **D2 is untouched**. G5 and G6 remain unbuilt.

---

## D18 — G7 is not yet run at survey scale

- **Status:** `OPEN` (raised 2026-08-22)
- **Blocks:** a production `EQUIVALENT` verdict on a real survey
- **Decision:** `DECISIONS.md` D-0029 · **Probe:** P3

G7 copies the store once per control. On the 30-trace article that is free. On a real
survey the store is hundreds of megabytes and there are eight controls, so a naive audit
copies the store eight times — a cost nobody has measured, and one that could make G7
impractical exactly where it matters most.

**MEASURED 2026-08-22** (`DECISIONS.md` D-0030), on a 362 MB store from a real survey:

| Quantity | Value |
|---|---|
| Bytes copied | **2.83 GB** (8 controls × 362 MB) |
| G7 wall clock | **370.4 s — 46.3 s per control** |
| Rest of the chain | 53 s |
| **G7 share of total** | **87 %** |

**G7 costs eight times the entire rest of the pipeline.** At 362 MB that is a slow
coffee. At a 20 GB survey it is ~160 GB of copying and hours of wall clock — the point at
which an operator switches it off. **A gate that gets switched off is worse than one that
was never written** (**SP11**), so this is a correctness risk wearing a performance
costume.

**Closure, cheapest correct option first:**

1. **Copy only the array a control touches.** `flipped_textual_byte` needs one attribute,
   not 362 MB; most controls touch a single array. Cuts 2.83 GB to a few hundred MB
   without weakening one assertion.
2. **Corrupt and restore in place**, verifying the restore by hash. Removes copying
   entirely, but a crash mid-audit would leave the store modified — needs a sentinel
   written first and a refusal to certify while it exists.
3. **Parallelise the controls.** Cuts wall clock, not bytes; disk is the ceiling.

---

## D19 — Round-trip closure: the exported SEG-Y is not validated as an artifact

- **Status:** `OPEN` (raised 2026-08-22)
- **Blocks:** the release criterion in `DECISIONS.md` **D-0031**, arrow ③
- **Spec:** §7 G3

**G3 proves the export is byte-identical to the source.** When it holds, that is the
strongest claim available and nothing more is needed.

`ROUNDTRIP-SCOPED` is the gap. §7 G3 permits it *"where the source is non-conforming in a
way that makes byte-identity impossible"* — and in exactly that case the exported file is
currently trusted on a hash comparison that was never going to match. Nothing checks that
the export is a well-formed SEG-Y, that it parses under the same gap-free spec, or that
it carries the same measured values.

**Closure:** re-ingest the export into a second store and verify (a) all five planes of
that store against the export, and (b) that its arrays are identical to the first store's.
That makes the exported SEG-Y a validated artifact in its own right rather than a
by-product, and it closes the loop for scoped round trips as well as byte-identical ones.

---

## D20 — At release, `NOT_RUN` must be a failure

- **Status:** `OPEN` (raised 2026-08-22), scheduled against **F8**
- **Decision:** `DECISIONS.md` D-0031 item 8

`verdict_for` currently returns `EQUIVALENT` when all five planes and G7 pass. It
tolerates **G5 and G6 being `NOT_RUN`**, which is right for today — they are not built,
and the `gates` block says so plainly on every certificate.

At release it will be wrong. **An unrun gate is not a passing one**, and a certificate
with holes in it is the untrusted artifact §0 describes. The verdict rule must tighten so
that any `NOT_RUN` yields `PROVISIONAL`.

**Not done now, deliberately:** tightening it today would make every certificate
`PROVISIONAL` while saying nothing the `gates` block does not already say. Recorded so it
cannot be forgotten at the moment it stops being cosmetic.

---

## D1 — NARROWED HARD 2026-08-22 — `ibm32` measured as NOT invertible

- **Status:** `OPEN` and **blocking**, character changed
- **Decision:** `DECISIONS.md` D-0034 · **Probe:** P2, **FIRED**

D1 said the transform was *"unverified"*. It is now **verified as not invertible**:
**2,447 of 4,103** words fail bit-identity, **1,939 losing the value** and not merely the
spelling. Bit-identity requires exponent code **33–96** with a normalised, non-zero
fraction.

**Built in response:** the exposure is always declared `SCOPED` on the certificate with
the measured regime named, and `EQUIVALENT` is blocked when `ibm32` is declared **and**
G3 did not achieve byte identity — byte identity being the empirical proof that this
data round-tripped. `ROUNDTRIP-SCOPED` is explicitly refused for this case in code.

**Still open:** the pre-registration's remaining remedy — **storing the raw `uint32` view
in parallel** — is not built. Until it is, an `ibm32` source whose round trip is not
byte-identical has bits that are **not recoverable from the output at all**.

---

## D3 — NARROWED 2026-08-22 — a C++ reader read the structured headers

- **Status:** `OPEN`
- **Decision:** `DECISIONS.md` D-0035 · **Probe:** P4, did **not** fire

TensorStore 0.1.85 read **all 97 fields** of the structured `headers` array
byte-identically. The falsifier did not fire.

**Two things keep it open.** Only one implementation ran — zarr-java and zarr-rs are
unmeasured, and `struct` has no Zarr v3 specification, so TensorStore's support is an
implementation choice rather than conformance. And the *same reader refused*
`segy_file_header`'s `fixed_length_utf32`, which is a same-run demonstration that
extension-dtype support is per-implementation.

**Measured and load-bearing:** SDIP's Plane 1 and Plane 2 bytes are recoverable **with a
JSON parser alone**, because D-0021 stored them as base64 attributes rather than array
payload. That was a correctness decision for §4.3; it also makes them strictly more
portable than any array-based storage.

---

## D5 — CLOSED 2026-08-22 — irregular geometry handled correctly

- **Decision:** `DECISIONS.md` D-0036 · **Probe:** P5, did **not** fire

All four falsifier clauses hold across ten synthetic fixtures. **A duplicate index tuple
is refused at ingest AND surfaced by Plane 5** — two independent defences, neither
suppressible. Padding is `NaN` and excluded from Plane 4. `MDIO_IGNORE_CHECKS` absent
throughout.

**Closed within its measured scope:** 20–80 traces, one template, poststack 3D, revisions
0 and 1, sparsity at 1.0/1.56/3.0/12.0, one duplicate with two colliding ordinals. Every
fixture is **synthetic and well-formed** — a hostile or malformed irregular file is D8,
not this.

---

## D6 — NARROWED HARD 2026-08-22 — only rev 1 works end to end

- **Status:** `OPEN` and blocking for legacy vintages
- **Decision:** `DECISIONS.md` D-0037 · **Probe:** P6, **FIRED for 3 of 4 revisions**

G1 passes on all four — gap-free construction generalises. **rev 0, rev 2 and rev 2.1
then fail to ingest**, so G3 is unreachable for them. Only rev 1 completes.

| Blocker | Revision | Owner |
|---|---|---|
| Template needs `cdp_x`/`cdp_y`/`inline`/`crossline`, undeclared before rev 1 | rev 0 | **SDIP** — §6.4 survey overrides are specified and **not built** |
| `data_sample_format` read unconditionally; a genuine rev 0 file carries zero there and does not open. **SDIP exposes no way to supply it.** | rev 0 | **SDIP** — no surface exists |
| `S8` `trace_header_name` has no `ScalarType` | rev 2, 2.1 | upstream — [mdio-python#865](https://github.com/TGSAI/mdio-python/issues/865) |
| rev 1 `segy_revision` injected, evicting `segy_revision_major`/`minor` | rev 2, 2.1 | upstream — [mdio-python#866](https://github.com/TGSAI/mdio-python/issues/866) |

**The public scope claim was false and is corrected.** §1.2 and `README.md` said rev 0–2.1
were supported. Only rev 1 is.

---

## D21 — Survey spec overrides (§6.4) are specified and not built

- **Status:** `OPEN` (raised 2026-08-22)
- **Blocks:** rev 0 support · **Decision:** D-0037

P6 showed rev 0 is **one specified-but-unimplemented mechanism away from working**:
declaring `cdp_x`, `cdp_y`, `inline`, `crossline` over bytes 181–196 keeps the spec
gap-free (G1 still PASS, 119 fields) and the whole leg passes byte-identically.

That declaration *is* a §6.4 survey override. The section exists; the code does not.

**Note the interaction with D1:** an override may now declare field types, and P2 has
**failed**. An override declaring an `ibm32` header field must be refused at review, not
merely deferred.

---

## D22 — No surface exists to supply a sample format for rev 0

- **Status:** `OPEN` (raised 2026-08-22)
- **Blocks:** any genuine rev 0 archive · **Decision:** D-0037

`SegyFile._update_spec()` reads `data_sample_format` from bytes 3225–3226 unconditionally
for every revision. A genuine rev 0 file carries zero there — the standard never mandated
it — and the file does not open: `ValueError: 0 is not a valid DataSampleFormatCode`.

P6's rev 0 fixture reads **only because SDIP's own generator stamped the code into it**.
An operator-supplied sample format is a stated requirement and **there is nowhere to
state it**. Under **SP1** an assumed sample format is a declared transform and must be
recorded on the certificate, so the surface has to carry it through to issuance.

---

## D18 — CLOSED 2026-08-22 — G7 copies only what a control touches

- **Decision:** `DECISIONS.md` D-0038

G7 no longer copies the whole store per control. Each control declares the store subpaths
it modifies; those are real copies and everything else is hard-linked. The original store
is hashed before and after the audit and a mismatch fails the gate — **a hard-link bug
here would corrupt the very store being certified.**

Verified on the synthetic article: G7 `PASS`, all 8 controls exact, **original store
byte-for-byte unchanged**.

---

## D7 — UNCHANGED 2026-08-22 — P8 could not run; no substitute was used

- **Status:** `OPEN`, entirely unmeasured
- **Probe:** P8, **NOT RUN**

P8 needs real S3/GCS/Azure credentials. None are available, and CI has no network beyond
the pinned package index.

**A mock was deliberately not used.** `moto`, `minio` or an in-memory filesystem would
each have produced a green result and answered a different question. P8 does not ask
*"does the object-store code path execute"*; it asks whether a run that takes hours
survives auth expiry, transient 5xx, connection reset and process kill — and whether it
can leave a **partially written store that validates as complete**. A mock does not
expire a credential mid-run or fail on the 17,000th PUT of 20,000.

Reporting a mocked pass would have been a claim that does not mean what a reader would
take it to mean (**SP8**).

**The sharpest open item**, from §11.2: *"a harness that can return nothing after hours
is a defect."* Nothing demonstrates that a killed cloud run leaves a resumable checkpoint
or an unambiguously incomplete store. A partial store that validates as complete is a
**security-class** finding — it produces a false `EQUIVALENT`.

---

## D23 — G7's cost is the plane re-runs, not the copying. D18's fix was half the problem

- **Status:** `OPEN` (raised 2026-08-22, correcting `DECISIONS.md` D-0038)

D18 measured G7 at 370 s and 2.83 GB copied on a 362 MB store and blamed the copying.
D-0038 fixed the copying — selective materialisation, hard links, verified-intact
original. **The wall clock barely moved.**

Measured on the first P3 file, 116,532 traces, with the fix in place:

| Quantity | Value |
|---|---|
| G7 | **388.1 s** for 8 controls |
| Per control | **48.5 s** |
| Plane 3 alone, on this data | ~25 s |
| Plane 4 alone | ~13 s |
| Whole rest of the chain | ~79 s |

**48.5 s per control is almost exactly the cost of running the five planes once.** The
copying is now negligible; **the audit is dominated by re-running the gates**, which is
inherent — G7 cannot know a gate fires without running it.

**D-0038's claim that D18 was closed is therefore too strong**, and this entry corrects
it (**SP10**: a wrong entry is corrected by a new one, never edited). The bytes problem is
closed. The wall-clock problem is not, and it is the one that gets a gate switched off.

**Closure:** run the controls **in parallel**. They are independent by construction — each
has its own working copy and touches nothing shared — so 8 controls across 8 workers is
roughly one control's wall clock. The disk is no longer the ceiling now that copying is
selective, which is precisely what makes parallelism available.

Note this does **not** breach P3's declared 900 s ceiling — the first file completed the
full chain in 467 s. It is a cost that scales badly, not a failure.

---

## D4 — NARROWED 2026-08-22 — prestack partially evaluable; chunking still unmeasured

- **Probe:** P7, clause 1 **FIRED** · **Decision:** `DECISIONS.md` D-0039

**Correctness half:** planes now read `dimension_names` from the store instead of
assuming `{inline, crossline}`. **4 of 7** prestack geometries fully establish the
Equivalence Contract; one **fails visibly** (`AutoChannelWrap` reorders traces); two
still raise, needing a computed dimension.

**Chunking half: still entirely unmeasured.** No candidate shapes, no declared latency
target, no authorised benchmark compute. **Do not guess in production.**

---

## D24 — `sdip ingest` cannot ingest prestack; the blocker is a name

- **Status:** `OPEN` · **Decision:** D-0039 F1

Seven geometries, seven refusals. Every prestack template binds header fields the rev 1
standard does not name. **For `offset` and `cdp` the bytes already exist** — rev 1 byte 37
is `source_to_receiver_distance` and byte 21 is `ensemble_num`, same bytes, same meaning,
different name — and `ingest()` has no parameter to say so.

**Closure:** §6.4 survey overrides (debt **D21**). One mechanism unblocks rev 0 *and* four
prestack geometries.

---

## D25 — `ingest()` does not forward `grid_overrides`

- **Status:** `OPEN` · **Decision:** D-0039 F2

`segy_to_mdio` accepts `grid_overrides`; SDIP does not pass one. `StreamerFieldRecords3D`
and `ObnReceiverGathers3D` cannot convert without it — their `shot_index` dimension is
calculated. A declaration parameter alone fixes four of seven geometries and leaves three
unreachable.

**Leg 2 proved the format is not the obstacle:** with names declared and an override
supplied, upstream converted all seven with G3 byte-identical on every one.

---

## D26 — **SP6 has two blind spots.** `warnings_raised[]` can be empty while data is lost

- **Status:** `OPEN` (raised 2026-08-22) · **Found by:** probes P2 and P5

**SP6 promises that a suppressed warning becomes a recorded liability.** Two mechanisms
defeat it, and neither involves suppression at all — the warning simply never reaches the
ledger.

**Blind spot 1 — spawned workers.** MDIO's header parser uses a `spawn` multiprocessing
context, so a warning raised inside a worker is raised in a **different process**. The
parent's `WarningLedger` sees nothing.

**Measured by P2, and it is the serious one:** on an end-to-end ingest of a fixture with
2,441 overflowing/underflowing `ibm32` sample words, `numpy` raised *"overflow encountered
in ibm2ieee"* in the workers and **`IngestResult.warnings.observed` was empty**. A
certificate for that store would have carried **no warning evidence of the loss at all** —
while §4.7's `warnings_raised[]` sat there looking reassuringly empty.

**Blind spot 2 — `logger.warning` is not a Python warning.** MDIO's grid-sparsity notice
at ratio 3.0 goes through `logging`, not `warnings`. **Measured by P5:** the ledger
recorded `observed: []` for a store with 54 padding cells. The sparsity surfaces only as
Plane 5's `padding_cells` evidence, which a reader looking at `warnings_raised[]` would
never think to check.

**Why this matters more than the suppression case D-0004 handles.** There, SDIP could at
least *detect the suppression* and declare it. Here there is nothing to detect: no filter
is installed, no warning is silenced, and the ledger is honestly empty because nothing
ever arrived.

**Closure, in order of value:**

1. **Capture worker warnings.** Pass a warnings-collecting initialiser into the pool, or
   have workers return their warnings with their results. Needs an upstream hook that
   may not exist — investigate, and if it does not, say so and record the gap on every
   certificate rather than leaving `warnings_raised[]` misleadingly empty.
2. **Attach a `logging.Handler`** for the duration of an ingest and record what upstream
   logs alongside what it warns. Cheap, and closes blind spot 2 outright.
3. Until both are closed, the certificate should state that `warnings_raised[]` covers
   **parent-process Python warnings only** — an empty list is not evidence of a quiet run.

---

## D27 — Coordinate scalar 0 blocks ingestion at rev 0 and rev 1

- **Status:** `OPEN` · **Found by:** P5

`mdio/segy/scalar.py` normalises a zero coordinate scalar to 1 **only for rev 2+**. At
rev 0 and rev 1 it raises `ValueError: Invalid coordinate scalar: 0`.

A zero coordinate scalar is **very common in real data** — it is what a writer emits when
coordinates are unscaled. SDIP cannot ingest such a file today.

---

## D28 — Little-endian SEG-Y cannot be declared to SDIP, and the blocker is ours

- **Status:** `OPEN` · **Found by:** P5

`build_gap_free_spec` inherits `endianness=big` from the standard and `ingest()` exposes
no override, so a little-endian file fails with
`ValueError: 256 is not a valid DataSampleFormatCode` — the format code read with the
wrong byte order.

**Measured:** the same file reads correctly with `spec.endianness=None`, which lets
`segy` infer it — 20 traces, correct inlines and crosslines. **The blocker is SDIP's, not
upstream's**, and the fix is a parameter.

---

## D29 — Header padding is zero-filled, not `NaN`-filled

- **Status:** `OPEN` · **Found by:** P5 · **SP12 exposure**

`amplitude`, `cdp_x` and `cdp_y` pad with `NaN`, which is unambiguous. The `headers`
array is a structured integer dtype and pads with **zeros**, so `inline == 0` at a padding
cell is indistinguishable *by value* from a real inline 0.

**SDIP's own planes are unaffected** — they use `trace_mask`, which is exact. The exposure
is for **any downstream reader that ignores the mask**, and SP12 says padding must be
distinguishable from measured data.

---

## D30 — Grids sparser than ratio 10 cannot be ingested

- **Status:** `OPEN` · **Found by:** P5

Ratio 3.0 converts with a log line; ratio 12.0 is refused with `GridTraceSparsityError`.
**A 2D or crooked-line survey indexed on inline/crossline falls in this class.**

The only route past the bound is `MDIO_IGNORE_CHECKS`, which is **barred** (§9.1) — so
this is a hard limit for SDIP, not a configuration choice. The correct answer is probably
a different template or index, not a higher ratio.

---

## D31 — The `inf` clamp is a false-pass hazard for any future `ibm32` probe

- **Status:** `OPEN` (locked in as a test) · **Found by:** P2

`ieee2ibm` clamps infinity to `0x61100000`, which is **itself a valid IBM word that
round-trips bit-identically while decoding to infinity**. A probe that happened to test
only that word would report a clean pass on a total overflow.

Locked in as a permanent test so no future narrowing of P2's sweep can reintroduce it.

---

## D2 — CLOSED 2026-08-22 — scale measured, within a declared ceiling

- **Closes:** D2 above, left unedited (**SP10**) · **Probe:** P3, falsifier did **not** fire
- **Decision:** `DECISIONS.md` D-0042

D2 said everything was measured on a **30-trace** article and that thirty traces is not a
survey. It now stands on **1,281,852 traces across 5.07 GiB in 11 files**, with
**1,283,133,852 samples compared exhaustively and exactly**, every gate passing on every
file, and **zero breaches** of ceilings declared before the run.

Worst peak RSS **2.87 GiB of 8.0 declared**; slowest file **467 s of 900**. RSS varied by
**0.06 GiB** across files of identical size — memory tracks the chunk working set, not
the file, which is what "no unbounded growth" means in practice.

**Closed within its scope, and the scope is load-bearing:** one geometry (249 × 468,
fully populated, zero dead traces), one revision (rev 1), one survey in three vintages,
local filesystem only, 5 GiB not 20 GiB. **A scale result that does not say what it did
not cover is not a scale result.**

---

## D21 — CLOSED 2026-08-23 — survey spec overrides built

- **Decision:** `DECISIONS.md` D-0044

§6.4 is implemented: named, versioned, declarative overrides with mandatory cited
evidence, G1 re-asserted after application, `ibm32` refused outright naming the failed
probe P2, and byte content unchanged by construction.

**rev 0 now ingests end to end** — G1 PASS at 119 fields, all five planes PASS, **G3
byte-identical**. Three overrides ship with real evidence prose.

---

## D6 — NARROWED FURTHER 2026-08-23 — rev 0 works; rev 2 / 2.1 remain upstream-blocked

- **Decision:** D-0044

rev 0's blocker is **gone**: the survey override declares the four index fields and the
whole leg passes byte-identically. **rev 0 and rev 1 both work end to end.**

rev 2 and 2.1 remain blocked on two upstream defects, both filed:
[#865](https://github.com/TGSAI/mdio-python/issues/865) (`S8` `trace_header_name` has no
`ScalarType`) and [#866](https://github.com/TGSAI/mdio-python/issues/866) (rev 1
`segy_revision` injected, evicting `segy_revision_major`/`minor`). Neither is SDIP's to
fix — §3.3 bars monkeypatching and no fork is authorised.

---

## D22 — CLOSED 2026-08-23 — a sample format can now be supplied

- **Decision:** D-0044

The override mechanism gives an operator a place to declare what a rev 0 file does not.
**Under SP1 an assumed sample format is a declared transform**, and the override carries
cited evidence into the certificate, which is what the record needed.

---

## D28 — CLOSED 2026-08-23 — endianness can now be declared

- **Decision:** D-0044

An override can set the spec endianness, including inferring it. P5's measured finding —
the same little-endian file reads correctly with the endianness left to `segy` — is now
reachable through a supported parameter rather than an unavailable one.

---

## D1 — CLOSED 2026-08-23 — the raw `uint32` view is stored

- **Decision:** `DECISIONS.md` D-0045 · **Probe:** P2, fired

P2's own "if it fires" remedy is built. `amplitude_raw_ibm32` holds the undecoded
big-endian sample words read from the source by raw offset, for `ibm32` sources only.

**The transform is still not invertible** — that is a property of `float32`'s range and
nothing SDIP does can change it. What has changed is that **the source bits are no longer
lost**: the 1,939 words in 4,103 that lose the value in the decode are recoverable from
the parallel view.

Plane 4 verifies the raw words against the source as a **separate leg**, exactly
invertible by construction, never folded into G2d's verdict — two decoded arrays that both
read `inf` are equal without either being the source sample.

---

## D26 — HALF CLOSED 2026-08-23 — log records captured; worker warnings declared

- **Status:** `OPEN` for blind spot 1 · **Decision:** `DECISIONS.md` D-0046

**Blind spot 2 is closed.** `recording_log_records()` captures what upstream logs at
WARNING and above, in a channel separate from Python warnings. On a real sparse ingest it
records the sparsity notice P5 found missing **and** a coordinate-unit warning that had
been raised on every ingest this project ever ran and appeared on no certificate.

**Blind spot 1 remains open but is no longer silent.** The ledger declares its own scope —
`covers: parent-process Python warnings and log records only`,
`worker_process_warnings: NOT CAPTURED`. **An empty `warnings_raised[]` can no longer be
read as evidence of a quiet run.**

---

## D32 — The `uint8` header plane would not fix group listing

- **Status:** `OPEN` (raised 2026-08-23) · **Found by:** P4 leg 2

zarr-java's `Group.list()` **fails outright** on an SDIP store: listing opens every child
node, and one unparsable `data_type` takes the whole enumeration down. **A zarr-java
consumer cannot list the store at all.**

The pre-approved mitigation — a parallel `(n_traces, 240)` `uint8` header plane — would
make the *header data* readable but **would not fix listing**, because `segy_file_header`
keeps `fixed_length_utf32`. That materially changes the mitigation's shape and was not
visible from leg 1.

**Closure:** decide whether the mitigation must also address `segy_file_header`. SDIP does
not write that array — MDIO does — but SDIP already stores its authoritative bytes as JSON
**attributes**, which every reader can parse. The question is whether the array itself
should exist in a form that does not break enumeration.

---

## D33 — The published schema was invalid for phases, unchecked

- **Status:** `CLOSED` 2026-08-23 · **Decision:** `DECISIONS.md` D-0048

The certificate schema rejected the real certificate in **six places**, two of them since
D-0022 several phases back. **Nothing caught it: no test validated a certificate against
the schema**, and `jsonschema` was not installed.

§4.7's promise — *published so third parties can validate without running SDIP* — was
false **only for third parties**. Anyone running SDIP saw nothing wrong.

Closed by writing the guard **first**, watching it fail, then correcting the schema. It
validates the fullest chain the engine can run and reports every violation at once.

**Recorded as a debt rather than a plain fix** because it was a *published contract
silently diverging from the artifact it describes*, and that failure mode is worth having
on the record: it is invisible from inside the project by construction.

---

## D34 — The raw view had no gate; now it has one

- **Status:** `CLOSED` 2026-08-23 · **Decision:** `DECISIONS.md` D-0049

The raw-word comparison was evidence-only, so **a corrupted `amplitude_raw_ibm32` failed
nothing** — and that array is the only recoverable copy of the source bits for an `ibm32`
source. A store that silently corrupted it was certifiable.

Closed by ANDing the raw leg into G2d, which keeps the original concern satisfied (a raw
pass cannot mask a float failure) and adds the missing direction. Ships with a G7 control,
`flipped_raw_ibm32_word` — **9 controls now, each failing exactly its declared set.**

---

## D35 — Worker-process warnings remain uncaptured

- **Status:** `OPEN` (carried from D26) · **Decision:** `DECISIONS.md` D-0046

Blind spot 2 is closed; **blind spot 1 is not.** Warnings raised inside MDIO's `spawn`
workers — including the 2,441 `ibm32` overflow warnings probe P2 measured — never reach
the parent process, so they appear on no certificate.

**It is now declared rather than silent.** Every certificate carries
`scope.worker_process_warnings: "NOT CAPTURED"`, and the CLI prints it. An empty
`warnings_raised[]` can no longer be read as evidence of a quiet run — but it is still
empty, and the loss it fails to record is real.

**Closure needs an upstream hook** — a pool initialiser or worker callback that lets a
caller install a filter in the child. §3.3 bars monkeypatching, so if no hook exists the
honest end state is the declaration, permanently.

---

## D36 — The raw sample view nearly doubles the store, and that is unresolved

- **Status:** `OPEN` (raised 2026-08-23) · **Decision:** `DECISIONS.md` D-0052

Measured on 116,532 real traces: `amplitude_raw_ibm32` costs **3,147 B/trace — 97 % of
`amplitude` itself**, taking the store from **0.77× the source to 1.51×**. SDIP output is
now **larger than its input**.

The header plane is not the problem: **9.26 B/trace**, less than half what the
pre-registration estimated. **Headers were never the cost. The samples are.**

**Deliberately not made optional.** A flag defaulting off is exactly the shape §0.1 warns
about — *"lossy codecs get enabled for a size win and never get disclosed downstream"* —
and P2 measured 1,939 words in 4,103 losing the value, unrecoverable from the decode.

**Closure candidates, none free:**

1. **Write it, then drop it when G3 proves byte-identity.** Sound in principle: if the
   round trip is byte-identical nothing was lost. Fragile in practice — it makes store
   contents depend on a later step, and a crash between the two leaves the expensive
   state.
2. **Store only the words that do not round-trip.** P2 measured the failing regimes
   exactly (exponent codes outside 33–96, zero fractions, unnormalised mantissas). A
   sparse view of only the at-risk words would be a fraction of the size. Needs a
   per-word check at ingest, and a sparse layout a consumer can read.
3. **Accept 1.51× and say so prominently.** Honest, and possibly correct for an
   archive-rescue tool where the source may not survive.

Option 2 is the interesting one: it is the only candidate that keeps full recoverability
*and* the size win, and P2 already supplies the predicate.


---

## D37 — `sdip doctor` reports FAIL to a consumer whose environment is fine

- **Status:** `OPEN` (raised 2026-08-23) · observed, not yet ruled on

Measured by installing the built wheel into a clean venv and running `sdip doctor` from
a directory that is not a git repository — a consumer's ordinary situation:

```
[PASS] python-version        Python 3.12.13 is inside the supported window
[PASS] barred-env-vars       none of 2 barred variables are set
[PASS] barred-packages       none of 1 barred modules are importable
[PASS] upstream-pins         all 2 binding pins match; 145 files verified against RECORD
[PASS] runtime-licences      51 distributions scanned, no GPL/AGPL entry
[FAIL] working-tree          ... is not a git repository; provenance cannot be captured
[ -- ] publication-firewall  not a git repository; nothing is tracked
[FAIL] git-hooks             .githooks/pre-commit is missing

doctor: FAIL (2 of 8 checks)
```

**Nothing crashed and every message is accurate** — the degradation is clean, which is
the half that matters most. But **the two failures are about SDIP's own development
discipline, not the consumer's environment.** `git-hooks` checks the publication
firewall's prevention layer, which exists to stop `docs/` reaching *this* repository and
is meaningless in someone else's project. `working-tree` matters only for `sdip certify`.

The documented contract is *"if doctor fails, nothing else runs."* A consumer who installs
the wheel to ingest one SEG-Y therefore reads **FAIL** and reasonably concludes their
installation is broken. It is not.

**Deliberately not fixed here.** `sdip doctor` has **no override flag** and eight
FAIL-severity checks by design, and changing which checks are severe — or adding a
`--consumer` mode — is a change to documented behaviour that §9 says to raise rather than
decide alone. Options a maintainer might weigh: scope the two repository-discipline
checks to runs inside the SDIP repository; or keep them severe and say so in the README,
so the output is expected rather than alarming.

Recorded now because the release ships this behaviour to every consumer, and an unrecorded
surprise is worse than a declared one.

---

## D17 — NARROWED 2026-08-23 — the ingest half is closed; the certify half is not

- **Narrows:** D17 above, left in place unedited (**SP10**)
- **Decision:** `DECISIONS.md` D-0055 · **Prior:** D-0020, D-0021, D-0028

D17 said Plane 1 *"does not yet preserve an undecodable textual header"*, and that
upstream mode 1 raises so *"the ingest fails rather than completing with the failure
recorded."* The second half is now false, on the measurement in D-0055.

**CLOSED — the ingest path.** Measured on a synthetic N=1 fixture, 12 traces, 8 planted
non-conforming bytes, against pinned `multidimio` 1.2.1 / `segy` 0.6.0:

| Claim | Measured |
|---|---|
| Ingest completes on a non-conforming textual header | **yes** — was `ValueError` from `segy_to_mdio` |
| Stored raw textual header vs source | **byte-identical**, 3200 of 3200 |
| Plane 1 / G2a | **PASS** |
| Plane 2 / G2b | **PASS** (raw authoritative) |
| Certificate `decode_status` | **`raw_preserved_decode_failed`** |
| Offending cells named by SDIP vs by upstream's own `ValueError` | **8 of 8 identical** |
| G7 on the fallback store shape | **PASS** — 10 of 10 controls, exact gate sets |
| Textual controls on that shape | fail **G2a alone** |

The closure path D17 proposed is the one taken, with one change: the raw bytes were
already captured before the converter ran (D-0021), so what was needed was not a capture
but a **mode choice** — upstream's file-header persistence is pinned **off** for such a
source, which is the only one of its three modes that neither refuses nor rewrites.

**Scope of the measurement.** N=1 synthetic fixture. **Unmeasured on a real
non-conforming legacy vintage**, which is the data this clause exists for and which the
test-data policy (§6) rightly keeps out of the repository. Nothing here is measured at
survey scale.

**STILL OPEN — `sdip certify` on such a source.** The store carries no
`segy_file_header` variable, so `mdio_to_segy` cannot export it and **G3 is unreachable**.
`sdip.export.roundtrip.export` now refuses with a typed `RoundTripUnavailableError`
naming the cause, so the failure is clean rather than an upstream traceback — but
`certify` calls `export` unconditionally and stops there.

This is **not** a defect in the fallback. Upstream's exporter re-encodes the *decoded*
text and sanitises anything that will not encode, so whole-file byte identity is
impossible for a non-conforming textual header under **every** mode, including the barred
mode 2. The open question is what G3 should *report* for a source that can never
round-trip:

- **`FAIL`** — truthful, and yields `NON-EQUIVALENT`; or
- **`ROUNDTRIP-SCOPED`** — which §7 G3 reserves for *"sources whose non-conformance makes
  byte-identity impossible"*, and which requires a written justification naming the
  specific non-conformance. §7 G3 also says it is **never inferred** from a mismatch.

Either is a change to a gate. **§9 requires a maintainer, so neither was chosen here.**
Note the load-bearing detail for whoever rules on it: `verdict_for` reaches `EQUIVALENT`
on planes plus G7 alone, so recording G3 as `NOT_RUN` for such a store would let it
certify as `EQUIVALENT` without a round trip ever having been attempted. That must not
happen, and it is the reason `export` refuses rather than returning a result.

**Closure for the remaining half:** a maintainer ruling on G3 for sources whose textual
header cannot be decoded, then whatever `certify` needs to honour it.

---

## D8 — **NARROWED 2026-08-23.** Corpus built; 33 members, 9 classes; one residual

- **Status:** `NARROWED` (original entry above unedited, **SP10**) · **Decision:** `DECISIONS.md` D-0057
- **Original status:** `OPEN`, blocking public release · **Spec:** §11.4

The corpus exists: `tests/fixtures/generators/hostile.py` writes **33 malformed SEG-Y
files across 9 hostility classes** from a fixed seed, and
`tests/negative/test_d8_hostile_corpus.py` runs every one of them — plus a **well-formed
positive control** (**SP11**) — through a real ingest in its own process, asserting on
error type, the frame that raised, peak RSS and the filesystem either side of the run.

**What it found.** 18 of the 33 came back with an exception SDIP does not define, raised
inside `segy`, `mdio` or `pydantic` after the file had already been read and sized from
its own numbers — including a **`ZeroDivisionError` from a zero in binary-header bytes
3217-3218**. §11.4's *"validated against actual file size before allocation"* was not
happening. `src/sdip/ingest/preflight.py` now does it, in 400 bytes and integer
arithmetic, before any allocation.

| | Before | After |
|---|---:|---:|
| Typed `UntrustedInputError`, raised inside `sdip` | 8 | **24** |
| Untyped exception from a dependency | **18** | **0** |
| MDIO's typed grid errors | (counted above) | 3 |
| Converted | 7 | 6 |
| Peak RSS on a refusal | 118.6-120.3 MB | **52.9-53.4 MB** |

**Two of §11.4's four clauses were already true and are now measured rather than
asserted:** no unbounded allocation was ever found (declared ceiling 512 MiB, observed
maximum 212.0 MB, and that is a *successful* ingest), and no write escaped the declared
output directory — `path_bait_in_headers` is a valid file whose textual header reads
`../../../../../../tmp/sdip_d8_escape`, and it converts without that path becoming one.

### What remains open

**1. Three members reach the console as a traceback.** `grid_sparse_enormous`,
`grid_index_negative` and `grid_all_identical` are refused by MDIO's
`GridTraceSparsityError` / `GridTraceCountError`. They are **deliberately not re-typed**:
these are geometry verdicts needing a full trace-header pass, and **probe P5 pinned those
exact types as the defence SDIP relies on** (`DECISIONS.md` D-0036) — `GridTraceCountError`
is raised unconditionally and is therefore not suppressible by `MDIO_IGNORE_CHECKS`.
Re-typing them would overturn a recorded measurement for a presentation preference, which
is a maintainer's call (the operating contract §9). **Candidate closure:** handle the named upstream
types at the CLI boundary only, so the library keeps raising what P5 measured while the
operator stops getting a stack trace.

**2. A file declaring a *variable* number of extended textual headers is not
reconciled.** Bytes 3505-3506 may hold `-1`, meaning *"variable, terminated by a stanza"*.
No fixed-offset arithmetic can then find the first trace, so `preflight` declares the
layout unknown and passes the file to the parser that can read stanzas rather than
guessing an offset or refusing a legal rev 2 file. The corpus has **no member for this
case** because generating a stanza-terminated rev 2 file needs writer support the pinned
`segy` 0.6.0 does not expose through its factory.

**3. The corpus is structural, not combinatorial.** 33 hand-built members, each isolating
one property, is the *"deterministic committed corpus"* the debt asked for — it is not a
fuzzer and does not claim a fuzzer's coverage. No mutation search, no coverage feedback,
no long-running campaign. A file that is hostile in two ways at once is unmeasured.

**4. Measured on one platform.** Darwin 25.5.0, CPython 3.12.13. The RSS ceiling is a
declared number checked against `ru_maxrss`, whose unit differs between Darwin and Linux;
the conversion is explicit in `tests/negative/hostile_child.py` but the *figures* have not
been reproduced on Linux.

---

## D7 — MEASURED 2026-08-23 — the cloud path is not merely untested, it is **unreachable**

- **Status:** `OPEN`, and the scope of the debt has grown
- **Probe:** P8, Amendment A local object-store leg, **RAN** · **Decision:** `DECISIONS.md` D-0058
- Prior D7 entries left in place unedited (**SP10**)

D7 has said since it was raised that cloud deployment is *unmeasured*. P8's local leg —
MinIO `RELEASE.2025-10-15T17-29-55Z` on loopback, a real S3 server, not a mock — measured
something worse:

**There is no cloud entry point, and using one silently succeeds.** Given
`s3://bucket/store.mdio`, `ingest()` returned normally and `sdip ingest` **exited 0** with
`G1 PASS`, having written a complete 20-file store to a local directory literally named
`s3:` in the working directory, with **0 objects** in the bucket. `Path(output).resolve()`
collapses the doubled slash into a relative local path. See `DECISIONS.md` D-0058.

**Known symptom, now refused.** `sdip.ingest.orchestrator.validate_output_path` rejects
any URI scheme before any work is done, with a typed `PhaseNotAuthorisedError` naming this
debt, and `tests/negative/test_object_store_output_refused.py` holds the control — 32
tests, and 12 of them fail if the check is unwired. **The refusal is not a fix for D7.**
It replaces a silent wrong write with a loud refusal; it implements nothing.

**What the leg did establish, and it narrows the remaining work.** With the path left
intact, every SDIP helper and all five planes work against MinIO **unmodified** —
`segy_to_mdio` already takes a `UPath`, and the planes call `zarr.open_group(str(store))`,
which stock `zarr` routes through `fsspec`. An object-store ingest was byte-identical to a
local-filesystem ingest of the same source: 10/10 chunk files, 11/11 arrays `array_equal`,
one differing leaf key across 12 `zarr.json` files and it is `createdOn`. **The blocker is
the two `Path(...).resolve()` calls and the CLI argument types, not the storage layer.**

**§11.2's mandatory clause is unmet.** *"Checkpoint-on-write is mandatory for any long
run."* There is no checkpoint of any kind: a killed 284 MB ingest loses everything, a
restart re-ingests from zero (36.13 s against 36.91 s fresh), and no object exists in the
store that is not an array, its metadata, or a chunk. An interrupted store also carries no
incompleteness marker — read with `mdio` absent it opens clean, returns 75–81 % fabricated
`NaN` fill values with `trace_mask` calling every trace live, and emits **zero warnings**.

**Still entirely unmeasured, and D7 remains open against all of it:** real cloud
throttling, transient 5xx, connection resets, eventual consistency, GCS, Azure, and
anything measured over hours. The longest run in the leg was 37 seconds. **No claim about
S3, GCS or Azure behaviour may cite this leg.**

**A separate finding from the same leg is not D7's** and is recorded here only so the
trail is not lost: a partially written store missing `amplitude_raw_ibm32` and
`headers_raw_uint8` passes all five planes and `sdip verify` reports `verify: PASS`. It
reproduces on the local filesystem, so it is a property of the Equivalence Engine rather
than of object storage, and it awaits a maintainer ruling under §9. See
`prereg/P8-cloud-object-store.md`.

---

## D38 — The verification path materialises whole files; the declared ceiling breaches near 1.1–1.4 GB

- **Status:** `OPEN` (raised 2026-08-23) · **Decision:** `DECISIONS.md` D-0060
- **Supersedes the reading of:** D2 (closed on a measurement that varied nothing)

**Measured, N=4, 51–403 MB:** `RSS_MB = 214.7 + 7.73 × source_MB`, **R² = 0.99997**.
Verification memory is **linear in file size**, not in a chunk working set. Ten `[:]`
sites in `planes.py`; `plane_4` holds the source samples and the store volume at once.

**P3's flat 2.81–2.87 GiB across eleven files measured one file size eleven times** — all
twelve Sleipner files are byte-identical at 494,565,408 bytes.

**Falsifier, pre-registered here before the run that would test it:** ingest and verify a
single source file of **≥ 1.5 GB** under the declared 8.0 GiB ceiling. If peak RSS stays
under the ceiling, this debt's model is wrong and the entry is corrected. If it breaches
— predicted between **1.1 GB** (synthetic fit) and **1.4 GB** (real-point anchor) — the
fix is streaming comparison, not a raised ceiling.

**Closure requires a refactor, not a patch.** Chunked comparison changes how every plane
reads its inputs, and it is explicitly **out of scope for the D-0059 change**: landing a
read-path refactor beside a new equivalence leg would make both unreviewable. Separate
design lock.

**Not a correctness defect.** Every gate's verdict is unaffected; what is affected is the
largest file the engine can verify at all, and the honesty of the D-0042 sentence that
claimed otherwise.

---

## D39 — A wall-clock assertion in the suite flakes under load

- **Status:** `OPEN` (raised 2026-08-23) · observed while validating D-0059

`test_p7_latency.py::test_a_shape_built_for_a_pattern_beats_the_default_on_that_pattern`
failed at load average **11.2** with `matched=6.33 ms` against `default=4.00 ms`, then
**passed 3/3 in isolation** on the same commit.

It is a real comparison — a chunk shape built for an access pattern should beat the
default on that pattern — but at millisecond scale on a contended machine the measurement
is noise. **CI is parked (`ci/`), so this has never run in CI**; it will flake there the
first time a runner is busy, and a flaky gate teaches people to re-run rather than read.

**Not fixed here**, because the honest options are a design choice: raise N and compare
medians, compare a ratio with a declared margin, or mark it as a benchmark excluded from
the gating suite. Each changes what the probe asserts, and P7's pre-registration is
committed.

---

## D40 — `headers_raw_uint8` can be deleted whole without failing any gate

- **Status:** `OPEN` (raised 2026-08-23) · **Decision:** `DECISIONS.md` D-0061

Corrupting one byte of the raw header plane fails **G2c**; deleting the whole array
fails nothing. The asymmetry is **deliberate for now** and the reasoning is on the
record: Plane 3's claim is that the 240 header bytes are **recoverable**, and G1
guarantees the structured array covers all 240 with zero gaps, so the claim holds with or
without the portable copy. The plane is a **portability** mitigation (D-0051), not a
recoverability one.

Requiring it unconditionally **failed seven prestack geometries that were correct** —
stores built by upstream `segy_to_mdio` legitimately carry none, and SDIP's own ingest
cannot express those geometries at all (**D25**).

**What would close it:** a marker that says *this store was written by `sdip ingest`, which
writes the header plane unconditionally*. The array's own attributes cannot serve —
they are deleted with it. A group-level provenance attribute written at ingest would, and
would also let `sdip verify` tell a partially-written SDIP store from a foreign MDIO store
it is merely inspecting. That is a store-format change and wants a maintainer ruling.

**Its G7 control was deleted rather than kept passing vacuously.** A control that fails
nothing is not a control (**SP11**).

---

## D41 — The lossy-decode generalisation is half done

- **Status:** `OPEN` (raised 2026-08-23) · **Decision:** `DECISIONS.md` D-0062

**Six of the eleven sample formats the pinned `segy` can express lose values through
MDIO's unconditional `float32` decode.** `LOSSY_DECODE_FORMATS` now records all six, and
**Plane 4's raw-view requirement is keyed to that set**, so an `int32` store missing its
raw view fails today.

**Still keyed to `ibm32` alone:**

1. **`detect_ibm32`** — should be `detect_lossy_decode(spec)`, returning the format and
   its loss class. An `int32` source emits **no `transforms_declared` entry** for a
   transform that altered values: an **SP1(a)** violation, same class as D-0040.
2. **`attach_raw_sample_view`** — writes `amplitude_raw_ibm32` only for `ibm32`. A lossy
   `int32`/`uint32`/`int64`/`uint64`/`float64` source gets **no undecoded copy at all**,
   so Plane 4 now correctly fails it and *nothing can make it pass* — the store cannot be
   made equivalent. Needs a format-parameterised view.
3. **`ibm32_blocks_equivalence`** — the `ROUNDTRIP-SCOPED` reasoning applies identically
   to the other five and is unenforced for them.
4. **One G7 control per raw view**, single-gate, in the same commit as each view (**SP11**).

**Pre-register before running (SP9):** P2 covered one format and its title claims the
transform generally. Extending it to the other five needs a merged pre-registration
first.

**Do not read `EXACT_DECODE_FORMATS` as a whitelist of safety.** It is a measurement of
integer representability, and it says nothing about a format the pinned `segy` adds
later — such a format belongs to neither set and is visible as unclassified, which is
the intended behaviour.

---

## D35 — NARROWED 2026-08-23 — worker warning **text** captured; the object still is not

- **Status:** `OPEN` (narrowed, not closed) · **Decision:** `DECISIONS.md` D-0066
- Leaves D26 and the original D35 entry above unedited (SP10).

**What changed.** A spawned worker inherits file descriptor 2 even though it cannot share
the parent's `warnings` machinery. `recovering_worker_stderr()` tees that descriptor —
copying every byte back to the real one, so nothing is swallowed and the progress bar
still renders — and recovers lines in `warnings.formatwarning`'s shape into a third
ledger list, `stderr_recovered[]`.

**Measured on the case that made this serious.** 30-trace fixture, all **960** sample
words set to `0x61800000`, real ingest under the binding pins:

| | before | after |
|---|---|---|
| samples `inf` on disk | 960 / 960 | 960 / 960 |
| `observed` | `[]` | `[]` |
| `stderr_recovered` | *did not exist* | **2** — `RuntimeWarning: overflow encountered in ibm2ieee`, `UserWarning: converting a masked element to nan` |
| stderr bytes scanned | — | 1129 |

**What is still open, precisely.** No `Warning` object crosses the process boundary, and
the seam search was re-run against the installed source rather than inherited: nothing in
`blocked_io.py:104`, `parsers.py:61`, `segy_to_mdio`'s seven parameters, or `MDIOSettings`'
eight fields reaches a worker. Text recovery is weaker in four stated ways — no object, no
process attribution, **one line per process rather than one per event** (960 words → 1
line), and worker *log records* remain uncaptured because they arrive without a
`file:lineno: Category:` prefix.

**The declaration is now testable rather than readable.** `scope` carries
`worker_warnings_captured: false` (a hardcoded literal, with a unit test forbidding it
from being wired to the recovery that does work), `worker_stderr_text_recovered`,
`worker_stderr_bytes_scanned`, `worker_stderr_recovery_truncated`,
`worker_log_records_captured: false` and
`log_records_below_effective_level_captured: false`. Three of the six are `required` in
the published schema.

**Closure, unchanged in kind:** an upstream pool initialiser or worker callback that lets
a caller install a recorder in the child. §3.3 bars monkeypatching, so if that never
arrives, the permanent end state is a recovered line plus a boolean saying it is not the
object.

---

## D19 — CLOSED 2026-08-23 — arrow ③ was passing a corrupted export

- **Status:** `CLOSED`. The original entry above is unedited (**SP10**).
- **Decision:** `DECISIONS.md` **D-0067** · **Criterion:** D-0031 arrow ③ · **Spec:** §7 G3

**D19 asked for the exported SEG-Y to be validated as an artifact in its own right, and
named the closure: re-ingest it, run the five planes against the resulting store, and
check that store's arrays against the original's.** `roundtrip_closure` did all three,
`sdip certify` called it, and `release_readiness` already treated a missing or non-PASS
result as blocking. The debt looked built.

**It was not, and the way it failed is the finding.** The check returned **PASS** on an
export whose 400-byte binary file header differed from the store's.

### What was measured

30-trace synthetic poststack fixture (seed 20260822), rev 1, `PostStack3DTime`, 11
arrays, G3 byte-identical. One bit flipped per run in the exported file; N = 7 corrupted
variants plus a clean baseline. **Five were caught. Two were not:**

| Flipped byte | What it is | Before | After |
|---|---|---|---|
| 64, 3199 | textual header | FAIL — *incidentally* | FAIL, by the header leg, naming the byte |
| 3221 | binary byte 22, `samples_per_trace` | FAIL — re-ingest refused | unchanged |
| **3300** | **binary byte 101, unassigned** | **PASS** | **FAIL** |
| **3450** | **binary byte 251, unassigned** | **PASS** | **FAIL** |
| 3600 | first trace-header byte | FAIL — arrays | unchanged |
| 3840 | first sample byte | FAIL — arrays | unchanged |

Two causes composing, both structural. The **five planes in closure run export against
the store built from that export**, so they are a self-consistency leg and cannot
disagree with the export about anything — Plane 1 and Plane 2 reported PASS on a
corrupted header as readily as on a clean one. And the one leg that did compare against
the original walked `group.arrays()`, while SDIP's authoritative raw file headers are
base64 **attributes** (D-0021), because §4.3's raw bytes are unreachable through MDIO
without a barred variable. In the `ROUNDTRIP-SCOPED` regime arrow ③ exists for, **two of
the five planes were checking nothing.**

The textual half only looked covered: a flip breaks the EBCDIC decode, the ingest falls
back to the header-less shape (D-0055) and the missing-array rule fires on the vanished
variable. **Detection by luck is not detection**, and byte 3300 has no such side effect.

### What closed it

1. A **file-header leg** in `roundtrip_closure` — byte equality on `sdipRawTextHeader`
   and `sdipRawBinaryHeader` between the two stores, one reader per attribute (D-0028),
   absence counted as failure, ANDed into `ClosureResult.passed`.
2. `closure_control` in `src/sdip/equivalence/nonvacuity.py` — closure's **first negative
   control**, appended beside `g3_control` and following its pattern because closure
   judges a *file* against a store. Flips byte 3300 of a copy under `workdir`; the export
   is left untouched and verified so by hash.
3. `tests/negative/test_closure_control.py` — **14 permanent controls**, including
   `test_closure_passed_the_corruption_before_the_file_header_leg`, which holds the
   pre-fix verdict as an executable record.

The control asserts the corruption is caught **by the file-header leg and no other**:
G1 passes, the export re-ingests, all five planes hold, every array matches, the textual
attribute is unchanged, and `differing_file_headers == ["sdipRawBinaryHeader"]`. That is
§7 G7's *"and ONLY that gate"* transposed to closure's legs, and it is what stops the
control going vacuous if the leg is later deleted.

**Cost:** one extra re-ingest of the export per `certify` — 2.14 s on the 30-trace
fixture, against 2.19 s for closure itself, 1.77 s for all 16 G7 controls and 12.78 s for
the source ingest. The clean closure run is passed in as the baseline rather than
recomputed (D18's lesson), so it is one extra ingest and not two. It scales linearly with
survey size and will want the same scrutiny D18 gave G7 once P3 sets a ceiling.

**Verified:** `ruff check`, `ruff format --check`, `mypy src` clean; 1115 passed. Three
failures in the same run belong to other in-flight work (`planes.py` Plane 5 padding
check, the `fabricated_value_in_padding` control, and a spec-override citation) and touch
nothing in this change.

---

## D42 — the closure control's own verdict is on the certificate but gates nothing

- **Status:** `OPEN` (raised 2026-08-23, at D19's closure)
- **Decision:** `DECISIONS.md` **D-0067**, final section
- **Blocks:** nothing today. **Blocks the D-0031 release criterion** if left at F8.

`release_readiness` blocks on `roundtrip_closure.status`, so **the new file-header leg
gates automatically** — a corrupted export now blocks release, which is the substance of
D19 and is done.

The **control's** verdict does not. It rides on the certificate under
`nonvacuity.closure_control`, and `release_readiness` never reads it — exactly as it never
reads `nonvacuity.g3_control`. So a `certify` run whose closure control came back `FAIL`
— meaning closure has been demonstrated **incapable of failing**, the precise definition
of a vacuous check under **SP11** — would still report `release_ready: true` with
everything else green.

**That is the same shape as the hole D19 just closed, one level up**, and it applies to
G3's control as much as to closure's.

**Left open deliberately, not overlooked.** `release_readiness` is the release gate.
Changing what it blocks on is a change to the gates, and the operating contract §9 makes that a
maintainer decision rather than a side effect of closing a debt. The fix is small — treat
a non-PASS `nonvacuity.g3_control` or `nonvacuity.closure_control` as blocking, in
`src/sdip/equivalence/certificate.py` — and it belongs to whoever owns that file.

**Scope note, so this is not read as wider than it is:** G4, G5 and G6 have no negative
controls at all. That is a different question — §7 G7's declared remit is G2a–G2e and G3,
so those three sit outside it by specification. This debt is only about controls that
exist, run, and are then not consulted.

---

## D25 — CLOSED 2026-08-23 — `ingest()` forwards `grid_overrides`

- **Closes:** D25 above, left unedited (**SP10**) · **Decision:** `DECISIONS.md` D-0065

`ingest()` takes `grid_overrides` and passes it straight to `segy_to_mdio`. **No default
is supplied.** An override changes what the store *contains*, not merely whether it can
be written, and a grid this tool chose is not one anybody declared — the same reasoning
that keeps G5's ceilings off by default (**SP9**).

---

## D24 — CLOSED 2026-08-23 — the name can now be supplied, for the two geometries a name was the blocker for

- **Closes:** D24 above, left unedited (**SP10**) · **Decision:** `DECISIONS.md` D-0065

A §6.4 alias override supplies the template's field names. Measured through
`sdip ingest` itself: **`cdp_offset_3d` and `cdp_offset_2d` ingest and pass all five
planes.**

**Two of seven, and the remaining five are not the same problem.** `offset` and `cdp` are
the standard's own words for bytes **37** and **21** — an alias supplies a label over a
byte that already exists. `cable`, `channel`, `gun`, `sail_line`, `receiver` and
`shot_line` are **not rev 1 fields under any name**: there is no byte to alias, so no
override can conjure them. Those need a real survey whose own spec declares them, and per
**D-0063 ruling 7** none is built until such a file exists. **The boundary is asserted as
a test rather than assumed** — if any of those six ever becomes a rev 1 field, it fails.

---

## D29 — CLOSED 2026-08-23 — padding is verified as padding

- **Closes:** D29 above, left unedited (**SP10**) · **Decision:** `DECISIONS.md` D-0069

**The ambiguity is not fixed and cannot be.** Measured on 18 real padding cells: floats
fill `NaN`, integers fill `0`, and there is no integer `NaN` to fill with. A downstream
reader that ignores `trace_mask` can still misread a padding zero as a measured zero.

**What was fixed is what SP12 actually asks for.** Padding was *excluded* from every
comparison — correctly; it has nothing to compare against — and therefore nothing could
catch data **appearing** there. Plane 5 now asserts every dead cell holds the declared
fill and nothing else, and the certificate records the fill per array plus whether it is
ambiguous by value, so the reliance on `trace_mask` is visible rather than inferred.

Control `fabricated_value_in_padding` → `{G2e}`, proven on both halves: it **fires** on a
ragged grid and is recorded **not applicable, by name**, on a full one.

---

## D42 — CLOSED 2026-08-23 — the controls are consulted, not merely recorded

- **Closes:** D42 above, left unedited (**SP10**) · **Decision:** `DECISIONS.md` D-0072
- **Authorised by:** the maintainer, on the §9 point D42 correctly stopped at

`release_readiness` now blocks on a non-`PASS` **or absent** `nonvacuity.g3_control` and
`nonvacuity.closure_control`. A control reporting `FAIL` means the check it audits has
been shown **incapable of failing** — the definition of a vacuous check under **SP11** —
and until now the certificate recorded that and the release gate never read it.

**Non-vacuity is asserted for the test module itself**, not just for the fix: a baseline
payload is proved release-ready first, so the five one-at-a-time tests cannot all "pass"
against a function that refuses everything.

**Scope is asserted too, so the rule is not read as wider than it is.** G4, G5 and G6
have no negative controls, and that is **by specification** — §7 G7's declared remit is
G2a–G2e and G3. This blocks on controls that exist and ran; it invents no requirement the
specification never made.

---

## D43 — The wall-clock ceiling is a bare constant, and a bare constant goes stale silently

- **Status:** `OPEN` (raised 2026-08-23) · **Decision:** `prereg/P10-scale-recalibration.md`

P3 declared **900 s** when the chain ran **10** G7 controls. Six controls and one closure
re-ingest later it ran **1,168.5 s** and G5 failed — **not because anything regressed, but
because the engine got more thorough and its budget did not follow.** The gate was right;
the number was out of date.

P10 rescales it to **1500 s**, which fixes today and **not the mechanism**. The next
control added moves the cost again and nothing will notice until a run fails.

**Closure:** express the ceiling as `base + per_control × len(CONTROLS)` so the budget
tracks the work. Deriving `base` and `per_control` requires measuring one control's cost
at survey scale — **its own probe, its own pre-registration** (**SP9**), not an appendix
to P10.

**Until then, P10 is explicit that it does not license a third rescale.** A ceiling raised
twice is not a ceiling.

---

## D43 — CLOSED 2026-08-23 — the ceiling is a function of the work

- **Closes:** D43 above, left unedited (**SP10**)
- **Decision:** `prereg/P10-scale-recalibration.md` Amendment C · `DECISIONS.md` D-0078

```
ceiling(n) = 1350 + 44.92 x (n - 16)        sdip.equivalence.scale
```

**1,350 s** = `max(N=5 certify runs) × 1.15`, rounded up to 50 s. **44.92 s** = the
maximum single-control cost across 3 chains and 45 applied control runs, where controls
proved interchangeable at `max/min = 1.05`.

**The ceiling TIGHTENED, 1500 s → 1350 s.** A recalibration that could only ever loosen
would not be one.

**It is not a default.** `sdip certify` still requires `--wall-ceiling-s`, because a
ceiling this tool applies on its own behalf is not one anybody declared (**SP9**). A test
asserts the CLI does not reference the calculator, so wiring it in becomes a deliberate
act rather than a drift.

**Three amendments, two discarded**, each by a guard declared before the data existed:
**A** had no floor check and would have shipped 1,150 s; **B** had one and stopped
1,100 s; **C** measured the command instead of summing its parts. **1,150 and 1,100 both
sit under a run that actually happened** — either would have failed the next legitimate
chain and read as a regression.

**It retro-explains the original failure.** At 10 controls the model computes **1,080.5 s**
where P3 declared **900 s** — that ceiling was already under-provisioned when written,
which is why control growth broke it rather than merely tightening it.

---

## D44 — G6 has no dedicated test; its CI gate reports NOT_RUN, accurately

- **Status:** `OPEN` (raised 2026-08-24) · **Decision:** `DECISIONS.md` D-0079

**`-k 'determinism or g6'` selects zero tests.** `g6()` runs in the certify chain and is
exercised **incidentally** inside the full-chain certificate test, but nothing tests it
directly. **A defect in `g6` that the certificate test did not happen to notice would be
caught by nothing.**

Its CI gate's subject glob `test_determinism*.py` matches no file, so the gate reports
`NOT_RUN` — **and that is the correct answer, not a bug.** The gate was deliberately left
unarmed rather than pointed at the incidental coverage: aiming it there would report a
gate as *armed* when nothing tests its subject directly, which is worse than an honest
`NOT_RUN`.

**Contrast with G4**, fixed in the same change: its subject `test_portability*.py` had
**also never matched a file**, but G4 *is* directly covered — 21 tests under other names.
That gate was mis-aimed and is now armed. **The two look identical from the CI summary and
are entirely different problems**, which is exactly why D14 says a green build does not
mean the gates pass.

**Closure:** a dedicated test for `g6` — two ingests, arrays compared, plus a negative
control that perturbs one store and requires G6 to catch it. Then point the gate at it.
Per **ruling 7** this is not capability work and needs no external file, but it is new
test surface and belongs to whoever picks up D14's remainder.

---

## D14 — NARROWED 2026-08-24 — four of five gates now arm and pass; the warning stands

- **Narrows:** D14 above, left unedited (**SP10**) · **Decision:** `DECISIONS.md` D-0080

**"Green with zero gates enforced" is no longer true.** CI executes, and the gate jobs
report:

| gate | state |
|---|---|
| integration (G2) | **armed, passing** |
| negative (G7) | **armed, passing** |
| portability (G4) | **armed, passing** — its subject had never matched a file until 2026-08-24 |
| spawn-guard | **armed, passing** |
| determinism (G6) | **`NOT_RUN`, and accurately** — see **D44** |

**What does not change is the warning itself, and it is the part worth keeping.** A green
build still means *everything that exists passes*. It does not mean the Equivalence
Contract holds on your data: the gates that matter run against **committed fixtures**, and
a certificate is issued against **a specific store from a specific source**. **CI cannot
certify anything.** A reader who checks only the badge still learns nothing about
equivalence — that is what `EQUIVALENCE_LEDGER.md` is for.

**Remaining to close:** D44, the one gate whose `NOT_RUN` is honest rather than
misconfigured.

---

## D44 — CLOSED 2026-08-24 — G6 has a dedicated test, and its gate is armed

- **Closes:** D44 above, left unedited (**SP10**) · **Decision:** `DECISIONS.md` D-0081

`tests/integration/test_determinism_g6.py`. **The filename is the fix**: the CI gate's
subject glob `test_determinism*.py` had matched nothing, so writing the test the gate
needed also armed it, with no workflow change. `-k determinism` now selects **6**.

**Two positive legs and four controls**, because a comparison that cannot fail is not a
comparison (**SP11**):

| leg | asserts |
|---|---|
| `g6()` on two real ingests | `PASS`, both levels, arrays non-empty |
| run directories cleaned up | documented behaviour, now asserted |
| flipped chunk byte | caught at the **byte** level, chunk **named** |
| changed sample value | caught at the **value** level |
| removed array | an **error**, not a per-array finding — a comparison over a subset would answer a question nobody asked |
| identical stores | **the control for the controls** — without it, all three above would pass against a comparator that called everything different |

That last row is the one that matters: it is what stops the negative controls from
passing vacuously.

**Every gate job now arms.** The gate table has no honest `NOT_RUN` left in it.
