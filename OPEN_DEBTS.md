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

