# Changelog

All notable changes to SDIP are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

**An upstream pin bump is a minor release with a migration note**, because it
invalidates every certificate issued under the previous pin (spec §12.4).

## [Unreleased]

### Added — roadmap phase F0

- Repository skeleton to the layout in specification §6.3.
- All required public-project files (§6.2): `LICENSE`, `NOTICE`, `README.md`,
  `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`, `CHANGELOG.md`,
  `CITATION.cff`, `.github/`.
- Append-only records: `DECISIONS.md`, `EQUIVALENCE_LEDGER.md`, `OPEN_DEBTS.md`.
- `sdip doctor` — eight environment checks with `--json` output and no override flag:
  Python window, barred environment variables, barred packages, upstream pins,
  runtime-licence scan, working-tree cleanliness, public/proprietary firewall, and
  pre-commit hook installation.
- `sdip.guard` — forbid-list enforcement for §9: barred env vars, barred packages,
  binding pins, runtime-licence scan, and the SP6 warning ledger.
- `sdip.provenance` — streamed SHA-256 hashing, environment capture, git state.
- CI to the table in §7.8, with the jobs that can run at F0 enforcing and the rest
  declared and skipped rather than silently absent.
- Pre-registration files for probes P1–P8 (§8), registered before any run (**SP9**).
- Certificate JSON Schema v0 (§4.7).

### Firewalled

- `docs/` and every AI-assistant artifact are maintained **outside** the published
  repository. Three independent mechanisms enforce it: `.gitignore`, the
  `publication-firewall` check in `sdip doctor`, and a `firewall` CI job that scans both
  `HEAD` **and all history**. See `DECISIONS.md` D-0010.

### Measured

- Header coverage for **every** SEG-Y revision the pinned `segy` exposes, extending
  Appendix A.2 which measured rev 1 only. See `DECISIONS.md` D-0003.
- Upstream warning suppression in `multidimio` 1.2.1 leaks a process-global filter.
  See `DECISIONS.md` D-0004 — it changes how SP6 is implementable.
- The runtime dependency tree carries **no GPL or AGPL entry**: 51 distributions,
  one requiring an allowlist entry with cited evidence. See `DECISIONS.md` D-0005/D-0006.

### Published

- Copyright holder resolved and the repository published at
  `github.com/zahidaramai/sdip` under Apache-2.0. Closes `OPEN_DEBTS.md` D12; see
  `DECISIONS.md` D-0011.

### Fixed before first publication

- The five gate CI jobs were written to fail while unbuilt, which — under §7.8's "any
  failure blocks merge" — would have blocked **every** PR permanently, including the PR
  that built the gate. They now arm themselves on the presence of their own subject.
  `DECISIONS.md` D-0012, recorded as a maintainer error.

### Added — roadmap phase F1

- **Gap-free spec generator** (`sdip.spec`) implementing §5.1: one `uint8` filler per
  uncovered byte, named `pad_<byte>` (**SP5**). Never a wider filler over a run — a
  multi-byte integer would commit to an endianness for bytes whose meaning is undeclared.
- **Gate G1** — five conditions (`coverage`, `no-overlaps`, `in-range`, `itemsize`,
  `no-void-gaps`) evaluated and reported **independently**, so a failure says what to fix.
  Takes a field set rather than a generator output, so it can judge a spec SDIP did not
  build. A missing dtype is a **failure**, not a skip.
- **`sdip spec build`** with `--revision` and `--json`. Exits 1 if G1 fails.
- Negative controls in the same commit: raw rev 0/1 standards, a dropped field, a
  doubly-covered byte, an out-of-range field, a wrong itemsize, numpy void padding.
  Each asserts its condition fails **and the others still pass**.

### Measured — F1

| Revision | Base fields | Fillers | Gap-free fields | G1 |
|---|---|---|---|---|
| rev 0 | 71 | 60 | 131 | PASS |
| rev 1 | 89 | 8 | 97 | PASS |
| rev 2 / 2.1 | 90 | 0 — already gap-free | 90 | PASS |

Reproduces `DECISIONS.md` D-0003 through the generator rather than by static arithmetic.
`ScalarType.STRING8` is `"S8"` and numpy rejects `"s8"` — case is preserved and
regression-tested. See D-0018.

### Added — roadmap phase F2

- **`sdip ingest`** and the ingest orchestrator, behind the mandatory `__main__` guard —
  MDIO's header parser uses a **`spawn`** context, and without the guard the child
  re-executes the ingest and dies with `BrokenProcessPool`. Measured, not theoretical;
  there is a regression test.
- **Raw file headers preserved by SDIP itself** — the 3600 bytes are read directly from
  the source, so Planes 1 and 2 do not depend on the converter's reading of them.
- **Certificate v0** with provenance: streamed source SHA-256, environment capture, and
  git working-tree state.
- **§6.4 survey overrides** — `SurveyOverride` with **mandatory cited evidence**, G1
  re-asserted after every override, and `ibm32` **refused outright**, naming P2.

### Added — phases F3, F4, F5, F7

- **The Equivalence Engine**: all five planes (G2a–G2e), **G3** whole-file round trip,
  **G4** portability in a clean subprocess, **G6** determinism, **G7** non-vacuity.
- **`sdip verify`, `sdip export`, `sdip certify`** — the full command surface is live.
- **Round-trip closure**: the exported SEG-Y validated as an artifact in its own right.
- **`release_readiness`** — the machine-checkable form of the release criterion, stricter
  than `verdict` and reported alongside it.
- Probes **P2, P3, P4, P5, P6, P7** implemented and run against pre-registrations
  committed beforehand. **P2, P6 and P7 fired.**

### Fixed — defects the engine found in itself

- **Planes 1 and 2 shared a validating reader**, so a truncated textual header failed
  **G2b** as well as G2a. Found by **G7 on its first run** (D-0028).
- **Planes 3–5 hard-coded `{inline, crossline}`** and returned no verdict at all on
  prestack. Found by **P7**; fixed by reading `dimension_names` from Zarr v3 metadata —
  prestack went **0/7 evaluable to 4/7 passing** (D-0039).
- **The coordinate scalar was an undeclared transform** on the derived `cdp_x`/`cdp_y`
  arrays — an **SP1(a) violation on every certificate ever issued**. Found by **P5**
  (D-0040).
- **Verdict ordering**: a blocked transform returned `PROVISIONAL` before checking plane
  failures, softening a real defect into an open question.

### Corrected — claims that were false

- **§1.2 and this README claimed rev 0, 1, 2 and 2.1 support.** Measured: **only rev 1
  works end to end** (D-0037).
- **SP9 was unsatisfiable** — pre-registrations lived in `docs/`, which is never
  committed. Moved to a public `prereg/` (D-0032).
- **D-0038 overclaimed** that D18 was closed: the fix addressed bytes copied, not wall
  clock (D23).

### Added — F6/F7 closure

- **`headers_raw_uint8`** — the 240 raw trace-header bytes as a plain 2-D `uint8` array,
  because three readers gave three different answers about the structured `struct` dtype
  and `struct` has no Zarr v3 specification. **9.26 B/trace**, measured on 116,532 real
  traces; the pre-registration had estimated ~19.
- **`amplitude_raw_ibm32`** — the undecoded `uint32` words, because P2 measured the
  `ibm32` decode as **not invertible**.
- **Gate G5** against ceilings declared on the command line, never a default: a ceiling
  this tool invented is not one anybody committed to (**SP9**).

### Measured — survey scale

- **11 files, 5,440,219,488 source bytes (5.07 GiB).** Every gate `PASS`. **Every `G3`
  byte-identical** — eleven whole-file SHA-256 matches. Peak RSS **2.87 GiB against a
  pre-declared 8.0 GiB ceiling**; worst wall clock **467 s against 900 s**.
- **One flipped bit in 116,648,532 samples fails `G2d` and nothing else.**
- **The store is 1.51× the source, not 0.77×.** `amplitude_raw_ibm32` costs **3,147
  B/trace — 97 % of `amplitude` itself**. Headers were never the cost; the samples are.
  Raised as debt **D36** rather than papered over with a size flag (D-0052).

### Fixed — a false provenance claim was reachable

- **`issue()` checked the working tree at issue time only.** A run that starts on commit
  A, is committed midway, and issues on a clean tree at B would attest every measurement
  to code that produced none of them. Git state is now captured **before** the
  measurements and re-checked at issue. Its negative control proves non-vacuity by
  showing `issue()` **succeeds** without the baseline in exactly that sequence (D-0053).
- **`sdip certify` ran the entire chain before refusing a dirty tree.** Now refuses in
  **0.4 s**, measured. The issue-time check stays; it is the binding one.
- **`main()` caught one of eight `SdipError` types**; the rest escaped as raw tracebacks.
  Worst for `UntrustedInputError` — §3.6 requires a hostile SEG-Y to produce a clean
  error, and a traceback is the crash that clause bars.

### Corrected — more claims that were false

- **`sdip certify --help` said "G7 does not exist"** and `sdip.equivalence`'s docstring
  said "G5, G6 and G7 do not exist". All three have existed since F4.
- **Two `not_yet()` helpers still said "the repository is at F0" with no callers at all.**
  Deleted rather than reworded — dead code carrying a false claim is worse than no code.
- **A test was pinning one of these claims.** `test_certify_still_documents_the_g7_ceiling`
  asserted `"PROVISIONAL"` appears in the help text — correct at F3, false from F4. The
  suite was *enforcing* the stale claim for four phases.
- **This changelog said "Not yet built: `sdip verify` / `sdip export` / `sdip certify`"**
  thirty lines below the entry announcing the full command surface was live, and carried
  a near-duplicate copy of its own F3–F7 block. Both corrected here.

[Unreleased]: https://github.com/zahidaramai/sdip/commits/main
