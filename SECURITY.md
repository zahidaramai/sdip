# Security Policy

## Reporting a vulnerability

Report privately through **GitHub Security Advisories** on this repository
(*Security → Report a vulnerability*). Please do not open a public issue for a
suspected vulnerability.

Expect an acknowledgement within **3 working days** and an assessment within **10
working days**. Coordinated disclosure is the default; we will agree a date with you
before publishing.

If you would rather not use GitHub, the maintainer contact in
[`CITATION.cff`](CITATION.cff) accepts reports.

## Supported versions

| Version | Supported |
|---|---|
| `main` (pre-release, phase F0) | ✅ |
| Tagged releases | none yet |

Until the first tagged release, `main` is the only supported version.

## Why this project has a real attack surface

**SDIP parses untrusted binary input.** A SEG-Y file is a header-length-prefixed binary
format from an arbitrary source: a tape transcription, a contractor deliverable, a
partner exchange, an email attachment. A malformed or deliberately hostile file must
produce a clean, typed error — **never** a crash, an unbounded allocation, or a write
outside the output path.

The binding rules (specification §11.4):

- **Header-declared lengths and counts are validated against actual file size before
  allocation.** A trace count or sample count read out of a header is attacker-supplied
  until it has been reconciled with the file on disk.
- **Output paths are confined. No path is ever derived from file content.** A textual
  header, a survey name, or a field value must not reach a filesystem path.
- **A fuzz corpus for the header parser is part of the test suite.** Tracked as **D8**
  in [`OPEN_DEBTS.md`](OPEN_DEBTS.md) — it is not built yet, and that debt is open
  against public release.

## Scope

**In scope**

- Crashes, hangs, or unbounded memory growth from a crafted SEG-Y or MDIO store
- Path traversal or arbitrary write from any input, including store metadata
- Any way to make `sdip certify` issue an `EQUIVALENT` verdict for a store that is not
  equivalent — this is the highest-severity class in the project, because the
  certificate is the product
- Any way to make a gate pass on a corrupted store (**SP11**, gate G7)
- Deserialisation issues reachable from store metadata

**Out of scope**

- Vulnerabilities in upstream `multidimio`, `segy`, `zarr`, or `xarray` — report those
  to their maintainers; tell us too if SDIP's usage widens the impact
- Resource exhaustion from a legitimately enormous but well-formed survey
- Anything requiring the operator to set a barred environment variable (§9.1); those
  are barred and `sdip doctor` fails on them

## A note on the certificate

A forged or wrongly issued Equivalence Certificate is a security issue, not merely a
correctness bug. The certificate is what a downstream consumer trusts instead of
re-verifying the data themselves. Treat a way to produce a false `EQUIVALENT` verdict
as you would treat an authentication bypass.
