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
- `sdip doctor` — seven environment checks with `--json` output and no override flag:
  Python window, barred environment variables, barred packages, upstream pins,
  runtime-licence scan, working-tree cleanliness, public/proprietary firewall.
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

### Not yet built

`sdip spec build` (F1), `sdip ingest` (F2), `sdip verify` / `sdip export` /
`sdip certify` (F3–F4). Each command exists and refuses with its roadmap phase.
Nothing is stubbed out to look like it works.

[Unreleased]: https://github.com/zahidaramai/sdip/commits/main
