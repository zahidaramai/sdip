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

