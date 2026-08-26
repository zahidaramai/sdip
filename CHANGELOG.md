# Changelog

All notable changes to SDIP are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

**An upstream pin bump is a MAJOR release**, because it **invalidates every certificate
issued under the previous pin** (spec §12.4, the operating contract §3.2). That is a breaking change
to the only thing this project promises, so it takes a major version and a migration note.

*Corrected at 1.0.0.* This line previously read "a minor release with a migration note",
which was written at `0.x` where the distinction does not bite. Under SemVer a minor must
be backward-compatible, and a release that voids every existing certificate is not.
Shipping 1.0 with the old wording would have published a versioning policy that
contradicts the pin policy.

## [1.1.2] — 2026-08-26

**Supersedes 1.1.1. Use this instead.** No engine change; the guarantee and the supported
surface are identical.

### Fixed

- **The 1.1.1 wheel shipped two source comments citing a document the public cannot open.**
  Found by downloading the published wheel and unzipping it — not by reading the source,
  which showed nothing wrong under the rules that existed.

  The publication firewall has four layers and **all four were working correctly. None
  could have caught it.** Every layer asks *"is this path published?"*, and for
  `src/sdip/cli/main.py` the answer is **yes, that is the point of it**. The firewall
  blocks *files*; this was inside a file that is supposed to ship.

  Independent of that, it is a documentation defect: a citation to a document the reader
  cannot open resolves to nothing for the entire audience that receives the file. Nine
  such citations now cite the operating contract or the public specification **by section**.

### Added

- **A fifth firewall layer**, scanning every published-suffix file for references to
  documents that do not ship, with its negative control in the same commit. Exemptions are
  **by path and enumerated**, never by pattern — the block-list files must be able to name
  what they block. The guard immediately caught two files that reasoning-by-hand had
  missed, which is the argument for the guard over the grep.

## [1.1.1] — 2026-08-26

**Distribution only. No engine change, and the guarantee is unchanged.**

### Added

- **Container image on GitHub Container Registry** — `ghcr.io/zahidaramai/sdip`, multi-arch
  (`linux/amd64`, `linux/arm64`), non-root. The image carries the **pinned** decoder, and
  `sdip doctor` verifies those pins **inside it**: *all 2 binding pins match; 145 installed
  files verified against RECORD.* That is the property that matters — a certificate issued
  under one decoder version says nothing about another.

  Verified end to end in the container before shipping: ingest, then `verify` returning
  G1 `PASS`, all five planes `PASS`, G4 `PASS`.

- **Wheel and sdist attached to every release**, so installing needs no registry. The
  workflow refuses to upload either if it carries an unpublishable path — **the
  publication firewall applies to distribution channels, not only to commits.**

### Not added, deliberately

**npm and NuGet.** GitHub Packages has no Python registry, and a package in either would
be a shim that still requires a Python 3.12 interpreter and the whole native stack — it
would install cleanly and **fail at first use**, in an ecosystem that cannot run the
library. That is the exact shape of failure this project exists to prevent.

### Fixed

- The publish workflow shipped an artifact check that **was never the script that was
  tested** — the verified version had a suffix guard, the shipped one did not, and it
  died opening a non-archive as a tarball.
- Building a container from a tag cut **before the Dockerfile existed** failed with a
  message that read like a path bug. The workflow now checks first and says what actually
  happened.

## [1.1.0] — 2026-08-24

**Additive only. No behaviour of v1.0.0 changed**, and the guarantee is unchanged: a
certificate still means what it meant.

### Added

- **`sdip.equivalence.scale.parametric_wall_ceiling(n_controls)`** — the G5 wall-clock
  ceiling as a **function of the work** rather than a constant, with
  `WALL_CEILING_BASE_S`, `WALL_CEILING_REFERENCE_CONTROLS` and
  `WALL_CEILING_PER_CONTROL_S` carrying their provenance.

  ```
  ceiling(n) = 1350 + 44.92 × (n − 16)
  ```

  **It is deliberately NOT a default.** `sdip certify` still requires
  `--wall-ceiling-s`, because a ceiling this tool applies on its own behalf is not one
  anybody declared (**SP9**). A test asserts the CLI does not reference it, so adopting
  it as a default becomes a deliberate act.

  **Measured over three amendments, two of them discarded** (`prereg/P10`): the first had
  no floor check and would have shipped 1,150 s; the second's floor caught 1,100 s. Both
  sit **below a run that actually happened** (1,168.55 s) and would have failed the next
  legitimate chain. Closes **D43**.

- **A dedicated G6 determinism test** (`tests/integration/test_determinism_g6.py`) — two
  positive legs and four controls, including a control **for the controls**: identical
  stores must be reported identical, without which the other three would pass against a
  comparator that called everything different. Closes **D44**.

### Fixed

- **`CITATION.cff` shipped v1.0.0 declaring `version: 0.1.0.dev0`.** The field existed
  with a stale value, so the release bump skipped it — a citation for the released
  software named a version that was never released. Now `1.1.0`, with `date-released`
  corrected too.
- **`sdip doctor`'s environment test assumed hooks were installed.** It passed on every
  developer machine and failed on a fresh checkout. The check was right; the test was
  wrong.
- **A refusal/ingest memory comparison had no declared margin** and failed on a 0.7 %
  difference — allocator noise. Margin declared at **1.25×**, far from the value that
  failed.
- **A CI guard that failed on the correct value.** It grepped for `zahidaramai/sdip` as
  an unresolved placeholder — which it *was* when written, before the repository existed
  at that name.
- **Two CI gates that could never arm.** G4's subject matched no file while G4 was
  covered by 21 tests under other names; G6's matched no file because no such test
  existed, which is what D44 wrote.

### Infrastructure

- **CI executes.** Workflows moved into `.github/workflows/`, and the first fully green
  run in this repository's history is **15/15**. Every gate job now **arms** — no
  `NOT_RUN` remains.
- **The pin-bump rule was corrected at 1.0.0** and holds here: an upstream pin bump is a
  **major** release, because it invalidates every certificate issued under the previous
  pin.

### Unchanged, and deliberately

The supported/refused table is **identical to v1.0.0**. No format, geometry, endianness or
backend was added, because none was demanded. **A minor release that widens the supported
surface without a real file asking for it is how a narrow guarantee quietly becomes a
broad claim nobody measured.**

## [1.0.0] — 2026-08-23

**The first release, and the first Equivalence Certificate this project has issued.**

`release_ready: true`, `blocking: []`, at commit `2f33f3e` on a clean tree, against a real
survey: **494,565,408 bytes, 116,532 traces, SEG-Y rev 1, big-endian, poststack 3-D,
`ibm32`.** All seven gates `PASS`. Recorded as `EQUIVALENCE_LEDGER.md` **row 1**.

| | |
|---|---|
| G5 | 1,115.3 s of a declared 1,500 s · 3.64 GiB of a declared 8.0 GiB |
| G7 | 15 corruptions, each failing **exactly** the gates it declares and no others |
| Round-trip closure | `PASS`, and its own control caught by the file-headers leg **and no other** |
| Pre-registration | `prereg/P10-scale-recalibration.md@2f33f3e`, committed **before** the run |

### What 1.0 means here, and what it does not

**It means the guarantee is stable, not that the coverage is complete.** The version
number is about the promise: a certificate from this engine means what it says, and the
engine has been shown capable of failing on 15 distinct corruptions.

**The supported surface is deliberately narrow and every refusal carries a stable reason
code** — see the supported/refused table in `README.md`. SEG-Y **rev 2/2.1**,
**little-endian**, five of the six lossy sample formats, prestack beyond CDP-offset,
files above the 1.0 GiB verification envelope and every cloud backend are **refused, not
attempted**. That list is the release, as much as the supported one is.

**One certificate on one file is one measurement.** It is the measurement this project
was built to be able to make. It is not a claim about seismic data in general.

### Known, recorded, and not fixed

`OPEN_DEBTS.md` carries every one. The ones a reader should know before depending on this:

- **D38** — the verification path fully materialises; peak RSS is **linear in file size**
  (`R² = 0.99997`). `sdip verify` **refuses** above 1.0 GiB rather than being OOM-killed.
- **D43** — the wall-clock ceiling is a bare constant and went stale once already.
- **D41** — the lossy-decode generalisation is half done: five formats are detected and
  declared but get no raw parallel view, so they certify **`NON-EQUIVALENT` with a named
  cause** rather than silently.
- **D36** — for an `ibm32` source the store is **larger than the source**, because the
  undecoded parallel view is the only recoverable copy of the bits.
- **D14** — CI is parked in `ci/`; the badges describe enforcement that is not running.



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

[1.1.2]: https://github.com/zahidaramai/sdip/releases/tag/v1.1.2
[1.1.1]: https://github.com/zahidaramai/sdip/releases/tag/v1.1.1
[1.1.0]: https://github.com/zahidaramai/sdip/releases/tag/v1.1.0
[1.0.0]: https://github.com/zahidaramai/sdip/releases/tag/v1.0.0
