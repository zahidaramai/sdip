<div align="center">

# 🌊 SDIP — Seismic Data Ingestion & Preparation

### *The product is not the file. The product is the file plus the proof.*

An open-source Python toolchain that converts **SEG-Y** seismic data to **MDIO/Zarr v3** and issues a machine-checkable **Equivalence Certificate** proving the conversion was an identity map on every measured value. Built for the subsurface data community — exploration, imaging, inversion, and archival — where a conversion nobody verified is a liability nobody priced.

<br />

## 🧊 Designed & Developed by KLCube Network Agency

### Zahid Aramai — Founder & Lead Developer

[![KLCube Network Agency](https://img.shields.io/badge/KLCube-Network_Agency-0EA5E9?style=for-the-badge&logoColor=white)](#-designed--developed-by-klcube-network-agency)
[![Lead Developer](https://img.shields.io/badge/Lead_Developer-Zahid_Aramai-0F172A?style=for-the-badge)](#-designed--developed-by-klcube-network-agency)
[![Copyright](https://img.shields.io/badge/©_2026-Zahid_Aramai-2563EB?style=for-the-badge)](NOTICE)

<br />

[![Python](https://img.shields.io/badge/Python-3.12_–_3.13-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org)
[![MDIO](https://img.shields.io/badge/MDIO-1.2.1_pinned-1E40AF?style=for-the-badge)](https://github.com/TGSAI/mdio-python)
[![Zarr](https://img.shields.io/badge/Zarr-v3-FF6F00?style=for-the-badge)](https://zarr.dev)
[![segy](https://img.shields.io/badge/segy-0.6.0_pinned-0D9488?style=for-the-badge)](https://github.com/TGSAI/segy)
[![NumPy](https://img.shields.io/badge/NumPy-2.5-013243?style=for-the-badge&logo=numpy&logoColor=white)](https://numpy.org)
[![uv](https://img.shields.io/badge/uv-managed-DE5FE9?style=for-the-badge&logo=astral&logoColor=white)](https://docs.astral.sh/uv/)

[![ci](https://github.com/zahidaramai/sdip/actions/workflows/ci.yml/badge.svg)](https://github.com/zahidaramai/sdip/actions/workflows/ci.yml)
[![dco](https://github.com/zahidaramai/sdip/actions/workflows/dco.yml/badge.svg)](https://github.com/zahidaramai/sdip/actions/workflows/dco.yml)

![Phase](https://img.shields.io/badge/roadmap_phase-F4-orange?style=flat-square)
![Tests](https://img.shields.io/badge/tests-431_passing-success?style=flat-square)
![Gates enforcing](https://img.shields.io/badge/gates_enforcing-5_of_7-yellow?style=flat-square)
![Certificates](https://img.shields.io/badge/certificates_issued-0-lightgrey?style=flat-square)
![Type checked](https://img.shields.io/badge/mypy-strict-2A6DB2?style=flat-square)
![Python](https://img.shields.io/badge/python-%3E%3D3.12%2C%3C3.14-3776AB?style=flat-square&logo=python&logoColor=white)
![License](https://img.shields.io/badge/license-Apache--2.0-black?style=flat-square)
![Made in Malaysia](https://img.shields.io/badge/made%20in-Malaysia-CC0001?style=flat-square)

[**Report a vulnerability**](https://github.com/zahidaramai/sdip/security/advisories/new) · [**Contributing**](CONTRIBUTING.md) · [**Decision record**](DECISIONS.md) · [**Open debts**](OPEN_DEBTS.md)

</div>

---

## 📑 Table of Contents

- [Overview](#-overview)
- [The Equivalence Contract](#-the-equivalence-contract)
- [Tech Stack](#-tech-stack)
- [Features](#-features)
- [The Gates](#-the-gates)
- [Command Surface](#-command-surface)
- [Project Structure](#-project-structure)
- [Getting Started](#-getting-started)
- [Available Commands](#-available-commands)
- [Quality & Verification](#-quality--verification)
- [Publication Firewall](#-publication-firewall)
- [Scope](#-scope)
- [Environment Variables](#-environment-variables)
- [CI/CD](#-cicd)
- [Upstream Pins](#-upstream-pins)
- [Security](#-security)
- [License](#-license)

---

## 🎯 Overview

The industry converts SEG-Y to cloud-native formats routinely and **almost never proves the conversion preserved the data.** Trace headers get dropped because they weren't in a template. Proprietary byte locations vanish silently. Lossy codecs get enabled for a size win and never get disclosed downstream. Padding introduced to regularise an irregular grid becomes indistinguishable from measured data.

None of these failures are loud. They surface years later, in an inversion that won't converge or a QC that can't be reproduced, long after the original tape has been archived.

**SDIP's contribution is not another converter. It is the receipt.**

| | |
|---|---|
| **Project** | SDIP — Seismic Data Ingestion & Preparation |
| **Author** | Zahid Aramai · KLCube Network Agency |
| **Licence** | Apache-2.0 |
| **Repository** | `github.com/zahidaramai/sdip` — public, open contribution |
| **Roadmap phase** | **F4** — **G7 non-vacuity**: the gate on the gates |
| **Python** | `>=3.12,<3.14` (the intersection of both upstream pins) |
| **Source** | 7,754 lines across 41 modules |
| **Tests** | 431 passing · mypy strict clean · ruff clean |
| **Gates enforcing** | **5 of 7** — G1, G2 (five planes), G3, G4, **G7**. G5 and G6 not built |
| **Certificates issued** | `EQUIVALENT` reachable and demonstrated; none committed |
| **Decision record** | 40 entries, append-only |
| **Open debts** | 43 entries, append-only — scheduled, never cancelled |

> **Read the two rows in bold before using anything here.** Zero gates enforce today. What has actually been measured is in [`DECISIONS.md`](DECISIONS.md); what has not is in [`OPEN_DEBTS.md`](OPEN_DEBTS.md). Where a property is unmeasured this project says so and names the probe that would settle it. **Unmeasured is a status, not an embarrassment.**

---

## 🔒 The Equivalence Contract

A store `Z` is **equivalent** to a source `S` **iff all five planes hold simultaneously.** Partial satisfaction is `NON-EQUIVALENT`, never "mostly equivalent". **There is no partial credit.**

| Plane | Claim | Gate |
|---|---|---|
| **1 — Textual** | 3200-byte textual header verbatim, including non-conforming EBCDIC. Decode failure is recorded; silent substitution is a defect. | `G2a` |
| **2 — Binary** | 400-byte binary header as a parsed mapping **and** as raw bytes. Raw bytes are authoritative on conflict. | `G2b` |
| **3 — Trace header** | All **240** header bytes per trace, bit-exact. Field naming is metadata; **byte content is the contract**. | `G2c` |
| **4 — Sample** | Every live sample bit-exact after the declared decode — **exact equality, never `allclose`**. | `G2d` |
| **5 — Cardinality** | Counts, ordering, live/dead mask, duplicate index tuples surfaced never silently overwritten. | `G2e` |

### The engineering guarantees behind it

- **No tolerance exists anywhere in the codebase.** Comparisons are `array_equal` or byte equality. A CI job parses the source with `ast` and fails the build on `allclose`, `isclose`, `assert_almost_equal`, `rtol=`, or `atol=`.
- **Gap-free header spec.** Every ingest runs against a spec covering bytes 1–240 with **zero gaps and zero overlaps**, asserted by `G1` *before a single trace is read*. Uncovered bytes become `uint8` fillers — `uint8` carries no byte-order or numeric-format semantics, so no endianness swap or IBM promotion can be applied to bytes whose meaning is undeclared.
- **Lossless codecs only.** Blosc family and Zstd. `zfpy` must not be installed, and `sdip doctor` fails if it is importable. A store whose codec manifest contains a lossy entry is void.
- **No fabrication.** Grid padding introduced to regularise an irregular geometry is **not data** and is excluded by the live mask. Interpolation and generative reconstruction are barred on all paths without exception.
- **No suppressed warnings.** Upstream silences two Zarr warnings; SDIP records the *suppression itself* onto the certificate and classifies it `declared` or `UNDECLARED`. See [`DECISIONS.md`](DECISIONS.md) D-0004 for why detection, not re-raising, is the honest implementation.
- **Certificates cannot be issued from a dirty tree.** There is no `--force`.

---

## 🧱 Tech Stack

| Layer | Technology | Notes |
|---|---|---|
| Language | [Python](https://www.python.org) `>=3.12,<3.14` | The intersection of both upstream pins — `multidimio` wants `>=3.12,<3.15`, `segy` wants `>=3.11,<3.14` |
| Store format | [Zarr](https://zarr.dev) v3 · [MDIO](https://github.com/TGSAI/mdio-python) v1 | Output is a plain Zarr v3 store; MDIO is a schema over it |
| SEG-Y reader | [`segy`](https://github.com/TGSAI/segy) `0.6.0` | Pinned by version **and** commit SHA |
| Converter | [`multidimio`](https://github.com/TGSAI/mdio-python) `1.2.1` | Public API only — no monkeypatching, no fork |
| Arrays | [NumPy](https://numpy.org) 2.5 · [Dask](https://dask.org) · [xarray](https://xarray.dev) | Consumers need none of SDIP or MDIO installed |
| CLI | [Click](https://click.palletsprojects.com) | Already in the `multidimio` tree — adds nothing to the licence surface |
| Tooling | [uv](https://docs.astral.sh/uv/) · [pytest](https://pytest.org) · [ruff](https://docs.astral.sh/ruff/) · [mypy](https://mypy-lang.org) strict | |

---

## ✨ Features

### Available now — phase F0

- **`sdip doctor`** — eight FAIL-severity environment checks with `--json` output and **no override flag**. Runs first in CI and first in every runbook. If doctor fails, nothing else runs.
- **Forbid-list enforcement** (`sdip.guard`) — barred environment variables, barred packages, binding upstream pins, a runtime dependency-tree licence scan, an SP6 warning ledger, and an `ast` scan proving SDIP never *sets* a barred variable.
- **Provenance capture** (`sdip.provenance`) — streamed SHA-256 (bounded regardless of input size), full environment capture, and git working-tree state including untracked files.
- **Publication firewall** — four layers, one of which prevents rather than detects. See [below](#-publication-firewall).
- **Published certificate JSON Schema v0** — shipped inside the package, so `pip install sdip` gives a validator to a consumer who never clones. `verdict: EQUIVALENT` is structurally unrepresentable unless all five planes and `G1`/`G2`/`G7` are `PASS` in the same document.

### Built but not yet armed

Every command exists and **refuses with its roadmap phase**. Nothing is stubbed out to look like it works — a command that returns a plausible result it did not compute is exactly how an untrusted artifact reaches a consumer.

```console
$ sdip certify
sdip: `sdip certify` is roadmap phase F3-F4. Until G7 passes, every certificate
      the engine issues is unvalidated. The repository is at F0; nothing is
      stubbed out to look like it works.
$ echo $?
2
```

---

## 🚦 The Gates

Gates are **binary**. No warnings-as-passes. Every gate names the number that kills it.

| Gate | Asserts | What kills it | Phase | State |
|---|---|---|---|---|
| `G1` | Byte coverage `== {1..240}`, itemsize `== 240`, zero overlaps, zero void gaps | Any uncovered or doubly-covered byte | F1 | **enforcing** |
| `G2` | The five planes, per plane | One differing byte on any plane | F2–F3 | **G2a, G2b enforcing** |
| `G3` | `sha256(export) == sha256(source)` for the whole file | Hash mismatch with no scoped justification | F3 | **enforcing** |
| `G4` | Store opens with stock `zarr` and `xarray` in a process asserting `"mdio" not in sys.modules` | Any array a consumer needs being unreadable without MDIO | F3 | **enforcing** |
| `G5` | Survey-scale ingest inside a declared memory ceiling | OOM, or peak RSS over the ceiling | F6 | not built |
| `G6` | Two independent runs produce **identical array bytes** | Any array-content difference between runs | F3 | not built |
| `G7` | **Every corruption fails its gate and only its gate** | Any corruption that passes, or one that fails the wrong gate | **F4** | **enforcing** |

### G7 is the gate on the gates

> **A gate a corrupted store passes is not a gate.**

Every equivalence check must ship a permanent negative control that **must fail it**: one flipped header byte, one flipped sample bit, one dropped trace, two transposed traces, an inverted live mask, a truncated textual header. Each corruption must fail **its** gate and **only** its gate — a checker that fails everything on any corruption looks maximally safe and is maximally useless.

**G7 now runs per store.** `sdip certify` corrupts *copies* of the store it is certifying, re-runs every checker, and records the outcome on that store's certificate — because a certificate cannot report the result of a test suite that ran on somebody's laptop last Tuesday.

Each control declares the **exact set** of gates it must fail, and the observed set must *equal* it. One assertion catches both failure modes: a **narrow** checker that misses the corruption, and an **over-broad** one that fires on somebody else's.

**It found a real defect on its first run.** Planes 1 and 2 shared a validating reader, so truncating the *textual* header also failed **G2b** — §7 G7's *"fails the wrong gate"* killer. The engine had been green on synthetic data, green on 116,532 real traces, and byte-identical on round trip, and still had two non-independent planes. Nothing else would have caught it (D-0028).

### What green CI means here

The five gate jobs **arm themselves**: each looks for its own subject in the tree and either runs the real check or reports `NOT_RUN` with its phase. A green build means *everything that exists passes*. **It does not mean the gates pass.** The `roadmap` CI job writes all seven gate states into every run summary so the distinction is visible in the run, not just in this file.

---

## 💻 Command Surface

```
sdip doctor       # env sanity: barred vars, barred packages, pins, licences,
                  # tree state, publication firewall, git hooks      [F0 — live]
sdip spec build   # generate + validate a gap-free spec; runs G1     [F1 — live]
sdip ingest       # SEG-Y -> MDIO  (must sit behind a __main__ guard) [F2 — live]
sdip verify       # Equivalence Engine against a store (G2, G4)     [F3 — live]
sdip export       # MDIO -> SEG-Y, then G3 whole-file SHA-256       [F3 — live]
sdip certify      # full chain + round trip + certificate       [F3 — live, F4]
```

---

## 📂 Project Structure

```
sdip/
├── .githooks/pre-commit          # publication firewall — the only layer that PREVENTS
├── .github/workflows/
│   ├── ci.yml                    # doctor, lint, unit, forbid-list, licence,
│   │                             # firewall, fixture-policy, gates, roadmap
│   └── dco.yml                   # every commit carries Signed-off-by
├── src/sdip/
│   ├── _pins.py                  # binding pins + forbid lists — single source of truth
│   ├── errors.py                 # typed errors; untrusted binary input never crashes
│   ├── guard/                    # forbid-list enforcement (spec §9)
│   │   ├── env.py                #   barred env vars + ast scan for assignments
│   │   ├── packages.py           #   zfpy must not be importable
│   │   ├── pins.py               #   exact version match; SHA declared, not verified
│   │   ├── licences.py           #   runtime tree scan, tiered evidence, no prose match
│   │   └── warn.py               #   SP6 ledger: detects suppression, contains the leak
│   ├── provenance/               # sha256, environment capture, git state
│   ├── schema/                   # PUBLISHED certificate JSON Schema (spec §4.7)
│   ├── cli/                      # doctor | spec | ingest | verify | export | certify
│   ├── spec/                     # gap-free SegySpec generator + G1     [F1 — live]
│   │   ├── coverage.py           #   byte arithmetic, independent of the generator
│   │   ├── generator.py          #   one uint8 filler per uncovered byte (SP5)
│   │   └── gate.py               #   G1: five conditions, judged independently
│   ├── templates/                # MDIO template registration & chunking     [F2]
│   ├── ingest/                   # orchestration + raw file-header capture [F2 — live]
│   ├── export/                   # MDIO -> SEG-Y, round-trip driver          [F3]
│   └── equivalence/              # THE ENGINE: five planes, G1–G7, certificates [F3]
├── tests/
│   ├── unit/                     # 175 tests, every guard with its negative control
│   ├── integration/              # seeded from the upstream round-trip test  [F3]
│   ├── negative/                 # G7 non-vacuity: corruptions that MUST fail [F4]
│   └── fixtures/PROVENANCE.md    # synthetic or openly licensed — binding
├── certificates/                 # issued certificates (JSON) — empty
├── DECISIONS.md                  # append-only design decision log
├── EQUIVALENCE_LEDGER.md         # append-only index of issued certificates
└── OPEN_DEBTS.md                 # unmeasured properties — scheduled, never cancelled
```

---

## 🚀 Getting Started

### Prerequisites

- **Python `>=3.12,<3.14`** — outside that window one of the two upstream pins cannot be satisfied
- **[uv](https://docs.astral.sh/uv/)** — `curl -LsSf https://astral.sh/uv/install.sh | sh`
- **git** ≥ 2.30

### Install

```bash
git clone https://github.com/zahidaramai/sdip && cd sdip
git config core.hooksPath .githooks   # required — see Publication Firewall
uv sync
uv run sdip doctor
```

Expected on a clean checkout:

```console
[PASS] python-version         Python 3.12.13 is inside the supported window
[PASS] barred-env-vars        none of 2 barred variables are set
[PASS] barred-packages        none of 1 barred modules are importable
[PASS] upstream-pins          all 2 binding pins match
[PASS] runtime-licences       51 runtime distributions scanned, no GPL/AGPL entry
[PASS] working-tree           working tree clean at ba11e78…
[PASS] publication-firewall   nothing unpublishable is tracked
[PASS] git-hooks              pre-commit firewall hook is installed and executable

doctor: PASS (8 checks)
```

`doctor` exits `1` if any check fails, and **there is no override flag** — no `--force`, no `--allow-dirty`. A dirty working tree fails it, which is the correct reading: the environment is fine and the run is not certifiable.

---

## 📜 Available Commands

| Command | Description |
|---|---|
| `uv run sdip doctor` | Eight environment checks; exits 1 on any failure |
| `uv run sdip doctor --json` | Machine-readable report, suitable as a CI artifact |
| `uv run pytest` | Full suite — 175 tests |
| `uv run sdip spec build --revision 0` | Build and validate a gap-free spec; runs G1 |
| `uv run pytest tests/negative -v` | The G7 non-vacuity suite — permanent negative controls |
| `uv run pytest tests/unit -k "actually_detects or negative"` | Just the negative controls — proof the guards fire |
| `uv run ruff check . && uv run ruff format --check .` | Lint and format |
| `uv run mypy` | Strict type check across 40 modules |
| `uv build` | Build sdist + wheel (`docs/` is excluded from both) |

---

## ✅ Quality & Verification

Only measured numbers appear here.

| Dimension | Evidence |
|---|---|
| **Unit tests** | **431 passing**, 0 failing |
| **Type checking** | `mypy --strict` clean across **40** source modules |
| **Lint / format** | `ruff check` and `ruff format --check` clean |
| **Warnings** | `filterwarnings = ["error"]` — any warning reaching pytest fails the suite |
| **Negative controls** | Every guard has one: barred env vars (6 forms), barred packages, pin mismatch, missing distribution, copyleft spellings, the pre-commit hook, and each firewall path |
| **Upstream verification** | All three API claims re-verified against the *live pinned objects*, including cited line numbers — `DECISIONS.md` D-0002 |
| **Pin integrity** | **145** installed files recomputed against the wheels' own `RECORD` manifests, plus artifact SHA-256 read from `uv.lock`. Commit SHAs remain declared-only and the report says so — D-0015 |
| **Header coverage** | Gap-free construction measured for **every** revision: rev 0 → 131 fields, rev 1 → 97, rev 2 / 2.1 → 90 (gap-free as shipped). Zero `ibm32` header fields in all four — D-0003 |
| **Revision support, end to end** | **rev 1 only.** G1 passes on all four; rev 0, 2 and 2.1 then **fail to ingest**. Construction generalises; construction is not enough — **P6 fired**, D-0037 |
| **`ibm32` invertibility** | **P2 fired.** Only **1,656 of 4,103** IBM words (40.4 %) round-trip bit-identically; **1,939 lose the value**, not just the spelling. The one transform SP1 permits is **not** exactly invertible — D-0034 |
| **Irregular geometry** | **P5 did not fire.** Duplicates refused at ingest *and* surfaced by Plane 5 — two independent defences. Padding is `NaN` and excluded from Plane 4. No suppressed check anywhere — D-0036 |
| **Cross-implementation** | **P4 did not fire.** TensorStore (C++, no shared code with `zarr-python`) read all **97** structured header fields byte-identically. The same reader **refused** `segy_file_header`'s dtype — extension support is per-implementation — D-0035 |
| **Licence scan** | **51** runtime distributions, **zero GPL/AGPL**, one allowlisted with cited evidence — D-0005 / D-0006 |
| **Reproducibility** | A fresh clone syncs, passes `doctor` 8/8, and runs the suite with no local state |
| **Real-survey validation** | Full chain — **including G7** — against a real 3D poststack survey: **116,532 traces, 494,565,408 bytes**. G1, G2, G3, G4, G7 all `PASS`; verdict **`EQUIVALENT`**. **One flipped bit in one sample, out of 116,648,532, failed G2d and nothing else** — D-0030 |
| **G7 cost** | Was 370 s / 2.83 GB — **87 % of the chain**. Now copies only what a control touches, hard-links the rest, and hashes the original before and after. **D18 closed** — D-0038 |
| **Header cost, measured on real data** | Full 240-byte preservation compressed to **2.0 B/trace (121:1)** — **0.06 % of the store**. ≈10× cheaper than §5.4's synthetic pessimistic figure |
| **Gates enforcing** | **5 of 7** — G1, G2, G3, G4, **G7**. See [The Gates](#-the-gates). |
| **Certificates issued** | `EQUIVALENT` reachable and demonstrated; none committed |

### Two defects the tests caught, recorded rather than quietly fixed

1. **`git status --porcelain` output was being stripped**, shifting every dirty path by one character (`a.txt` → `.txt`). Now `-z` parsed and unstripped. Caught by its own negative control.
2. **Two forbid-list gates were greps that fired on prose.** `pandas` embeds a **63,416-byte** licence text in its `License` metadata field — including PSF text discussing GPL compatibility — so a substring scan flags a BSD-3-Clause package as copyleft. Both gates are now `ast`-parsed with negative controls. **A gate that fires on prose is a gate that gets switched off.**

---

## 🛡️ Publication Firewall

This repository is public. Some paths are **never committed** — not with `git add -f`, not "just this once to fix a link":

```
docs/                    CLAUDE.md               AGENTS.md
.claude/                 CLAUDE.local.md         .cursor/   .aider*
.claude-session-sync.md                          .github/copilot-instructions.md
```

| # | Layer | Catches | Timing | Bypassed by |
|---|---|---|---|---|
| **1** | `.githooks/pre-commit` | staged paths | **before the commit exists** | `git commit --no-verify` |
| 2 | `.gitignore` | an accidental `git add -A` | at `git add` | `git add -f` |
| 3 | `sdip doctor` → `publication-firewall` | index **and** `HEAD` | on demand | not running it |
| 4 | CI `firewall` job | **any commit, any ref** | every PR and push | nothing in-repo |

**Only layer 1 prevents. Layers 2–4 detect.** Once a path is in a commit the only remedy is a history rewrite, because a clone receives history — `git rm --cached` removes a file from the index and leaves it in every commit that already had it.

Layer 4 deliberately does **not** declare `needs: doctor` and uses no Python: a broken environment is exactly when someone force-adds a file to make a check go away, so the layer that catches that cannot depend on the environment being healthy.

> `docs/` holds the governing specification, the probe pre-registrations, and the runbooks. Every rule it imposes on a contribution is restated in this file, [`CONTRIBUTING.md`](CONTRIBUTING.md), and [`DECISIONS.md`](DECISIONS.md). If a rule you are asked to follow appears in none of the three, **open an issue** — that is a defect in those files, not in you. Tracked as **D13**.

---

## 🧭 Scope

### In scope

- SEG-Y → MDIO v1 / Zarr v3 ingestion. **Measured revision support: rev 1 only** — see below. rev 0, 2 and 2.1 build a valid gap-free spec and pass G1, then fail to ingest for three named reasons (D-0037)
- Gap-free trace-header specification generation and management
- The Equivalence Engine, its gates, and the Equivalence Certificate
- MDIO → SEG-Y export and round-trip verification
- Poststack and prestack geometries; survey-scale chunking, memory ceilings, cloud stores
- Provenance, custody, and reproducibility metadata

### Explicitly out of scope

- **Seismic processing of any kind.** No filtering, scaling, resampling, regridding, muting, interpolation, denoising, or reconstruction. **SDIP is an identity map with a receipt.**
- **ZGY, VDS, SGZ as ingestion sources** — ruled derivative-only. ZGY carries *no trace headers*; readers synthesise them and **234 of 240 bytes are zeros**. Sample types are routinely `int8`/`int16` with a linear coding range, so the data is already quantised before SDIP would see it. Display or screening path only, flagged `DERIVATIVE`, never quantitative.
- **Interpretation data** — horizons, faults, wells, velocity models. Different problem.
- **Format invention.** SDIP adopts MDIO v1; it does not design a competing schema.

### Not KPIs

- **Compression ratio.** Size reduction is a side effect of lossless codecs, never a target that could justify a lossy path.
- **Ingestion speed**, until equivalence is proven at scale. A fast pipeline with an unproven contract has negative value — it produces untrustworthy data faster.

---

## 🔑 Environment Variables

SDIP reads **no** configuration from the environment. Two variables are **barred**, and `sdip doctor` fails if either is set — presence alone, including `=0` and `=""`.

| Variable | Why it is barred |
|---|---|
| `MDIO_IGNORE_CHECKS` | Demotes MDIO's grid-sparsity error to a log line. **A suppressible gate is not a gate.** |
| `MDIO__IMPORT__RAW_HEADERS` | Deprecated upstream for removal in 1.4. SDIP reaches full 240-byte header persistence through the **public API** instead, so depending on this flag is a specification violation even though it looks helpful. |

> **If you find one of these set, do not just unset it and move on.** Someone set it because something failed. That thing still fails. `MDIO_IGNORE_CHECKS` means a grid did not resolve — probe **P5**. `MDIO__IMPORT__RAW_HEADERS` means someone believed headers were being dropped — verify with **G2c**, not with the flag.

SDIP holds no secrets and requires no credentials. Cloud object-store access, when it lands in phase F6, uses the backend's own credential chain.

---

## ☁️ CI/CD

Every job on every PR. Any failure blocks merge.

| Job | Asserts | Gated on `doctor` |
|---|---|---|
| `doctor` | Runs first. If doctor fails, nothing else runs. | — |
| `lint / type` | `ruff check`, `ruff format --check`, `mypy --strict` | yes |
| `unit` | Full suite on Python **3.12** and **3.13** | yes |
| `forbid-list` | Barred vars absent · SDIP never *sets* one (`ast`) · `zfpy` unimportable · no tolerance (`ast`) · no suppressed warnings · **the detectors have been shown to fire** | yes |
| `licence` | No GPL/AGPL in the runtime dependency tree | yes |
| `firewall` | Nothing unpublishable at `HEAD` **or anywhere in history** | **no — deliberately** |
| `fixture-policy` | No fixture lacking an entry in `PROVENANCE.md` | yes |
| `publication-readiness` | No unresolved placeholder can reach a public repository | yes |
| `gates` | Five self-arming gate jobs: run the real check, or report `NOT_RUN` with the phase | yes |
| `roadmap` | Writes all seven gate states into every run summary | — |
| `dco` | Every commit carries `Signed-off-by` | — |

CI has no network access except the pinned package index.

---

## 📌 Upstream Pins

| Package | Version | Commit |
|---|---|---|
| [`multidimio`](https://github.com/TGSAI/mdio-python) | `1.2.1` | `a2895b53088ffacbf4bd1b9e882856cbda78e235` |
| [`segy`](https://github.com/TGSAI/segy) | `0.6.0` | `8e93e97db33ea4b2ce77433f6fdbef5d31ac6e78` |

Pinned **together** — the `ibm32` header fix straddles the `segy` 0.6.0 boundary. **A bump invalidates every certificate issued under the previous pin**, requires a maintainer decision in [`DECISIONS.md`](DECISIONS.md), and ships as a minor release with a migration note.

**SDIP pins and does not fork.** Full 240-byte header persistence is reachable through the public API, independent of the deprecated raw-headers flag — the chain was verified against the live pinned objects rather than read from documentation (D-0002). No monkeypatching, no subclassing around, no reaching into internals.

> Commit SHAs are **declared, not runtime-verified** — a wheel does not carry the SHA it was built from. Every certificate says so in its own `env` block rather than implying an attestation that did not happen. Tracked as **D9**.

---

## 🔐 Security

**[Report a vulnerability privately →](https://github.com/zahidaramai/sdip/security/advisories/new)**

SDIP parses **untrusted binary input**. A SEG-Y file is a header-length-prefixed binary format from an arbitrary source — a tape transcription, a contractor deliverable, an email attachment. A malformed or hostile file must produce a clean, typed error, never a crash, an unbounded allocation, or a write outside the output path.

**A forged or wrongly issued Equivalence Certificate is a security issue, not merely a correctness bug.** The certificate is what a downstream consumer trusts *instead of* re-verifying the data themselves. Treat a way to produce a false `EQUIVALENT` verdict as you would an authentication bypass.

Full policy, scope, and the supported-version window: [`SECURITY.md`](SECURITY.md).

---

## 📄 License

**Apache-2.0.** See [`LICENSE`](LICENSE).

[`NOTICE`](NOTICE) carries mandatory attribution to **TGS** for `mdio-python` and `segy` (Apache-2.0) and for the round-trip test the Equivalence Engine is seeded from. **That attribution is a legal obligation and must survive refactors.** `ThomasHertweck/seisio` (LGPL) is cited as design prior art with an explicit *no code copied* statement; no code has been taken from `trhallam/segysak` (GPL) or `stuliveshere/pyseis-io` (AGPL-3.0), at any size.

Contributions are accepted under Apache-2.0 with DCO sign-off — see [`CONTRIBUTING.md`](CONTRIBUTING.md). Citation metadata: [`CITATION.cff`](CITATION.cff).

---

<div align="center">

## 🧊 Designed & Developed by KLCube Network Agency

### Zahid Aramai — Founder & Lead Developer

[![KLCube Network Agency](https://img.shields.io/badge/KLCube-Network_Agency-0EA5E9?style=for-the-badge&logoColor=white)](#-designed--developed-by-klcube-network-agency)
[![Lead Developer](https://img.shields.io/badge/Lead_Developer-Zahid_Aramai-0F172A?style=for-the-badge)](#-designed--developed-by-klcube-network-agency)
[![Copyright](https://img.shields.io/badge/©_2026-Zahid_Aramai-2563EB?style=for-the-badge)](NOTICE)

<br />

Built as an open-source contribution to the subsurface data community · Kuala Lumpur, Malaysia

© 2026 **Zahid Aramai** · Licensed under Apache-2.0

*The product is not the file. The product is the file plus the proof.*

</div>
