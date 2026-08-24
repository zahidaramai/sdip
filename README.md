<div align="center">

# 🌊 SDIP — Seismic Data Ingestion & Preparation

### *The product is not the file. The product is the file plus the proof.*

An open-source Python toolchain that converts **SEG-Y** seismic data to **MDIO/Zarr v3** and issues a machine-checkable **Equivalence Certificate** proving the conversion changed nothing.

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

<br />

![License](https://img.shields.io/badge/license-Apache--2.0-black?style=flat-square)
![Python](https://img.shields.io/badge/python-%3E%3D3.12%2C%3C3.14-3776AB?style=flat-square&logo=python&logoColor=white)
![Made in Malaysia](https://img.shields.io/badge/made%20in-Malaysia-CC0001?style=flat-square)

</div>

---

## The problem

A seismic survey is measured once. The acquisition is gone the moment the vessel leaves, and what remains is a file — often the only copy of a subsurface nobody can go back and re-measure.

That file gets converted. SEG-Y to a cloud-native format, tape to disk, one vintage to the next. Every conversion is a chance to lose something quietly: a header field dropped because a parser did not name it, a sample altered because a decode was not exactly invertible, a trace mislabelled because a grid was regularised.

**Nothing catches it.** The conversion succeeds. The file opens. The volume looks right. The loss surfaces years later — in an inversion that will not converge, a 4D difference that is an artifact, a well tie that is off by a sample — and by then nobody can tell whether the data was always like that or whether a tool changed it in 2019.

Plenty of tools convert SEG-Y. **What has been missing is the receipt.**

---

## What SDIP does

SDIP converts SEG-Y to MDIO/Zarr v3 **and proves the conversion was an identity map on every measured value.**

The proof is a **certificate** — a JSON document, validated against a published schema, that a third party can check **without running SDIP**. It records what was compared, how, and with what result:

| Plane | The claim it settles |
|---|---|
| **Textual header** | The 3,200 bytes are preserved verbatim |
| **Binary header** | The 400 bytes are preserved; the raw bytes are authoritative |
| **Trace headers** | All **240 bytes** of every trace are recoverable, bit-exact |
| **Samples** | Every live sample is bit-exact after the declared decode |
| **Cardinality** | Trace count, ordering, live mask and duplicates all reconcile |

**All five must hold simultaneously.** There is no partial credit and no "mostly equivalent" — a store that satisfies four planes is `NON-EQUIVALENT`, and the certificate says which one failed and where.

Comparisons are **byte equality** or `array_equal`. **There is no tolerance anywhere in the engine**, because a tolerance is how a lossy path gets a passing grade.

---

## Why you would want it

**You are moving a survey and cannot re-acquire it.** The conversion either preserved the data or it did not, and "the volume looked fine" is not an answer you can hand to anyone.

**You received data from someone else.** A certificate travels with the store and can be verified independently — you do not have to trust the sender's toolchain, or run it.

**You are building on converted data.** An inversion or a 4D study inherits every defect upstream of it. A certificate turns "we think the conversion was clean" into something with a number behind it.

**You are the custodian of an archive.** Tapes degrade, formats age, and the migration you run today is the one someone audits in twenty years. SDIP writes down what it did, in a form that outlives the person who ran it.

---

## What makes the proof worth anything

**A gate a corrupted store passes is not a gate.**

The engine ships **16 permanent negative controls** — deliberate corruptions that *must* fail, each required to fail **exactly** the check it targets and no others. One flipped bit in one sample. One flipped header byte. A dropped trace. Two transposed traces. An inverted live mask. A truncated textual header. A deleted array.

If a corruption passes, or fails the wrong check, **the whole engine is treated as unvalidated** — because a checker that cannot localise a fault cannot be trusted to have found one.

That is the difference between a tool that reports success and a tool whose success means something.

---

## Getting started

```bash
git clone https://github.com/zahidaramai/sdip && cd sdip
uv sync --all-extras --dev

uv run sdip doctor          # environment sanity; runs first, always
```

Convert and certify:

```bash
uv run sdip certify survey.sgy survey.mdio \
    --rss-ceiling-gib 8.0 \
    --wall-ceiling-s 1500
```

This ingests, runs all five planes, exports back to SEG-Y, compares the whole file by SHA-256, checks the store opens with **stock `zarr` and `xarray` with MDIO uninstalled**, runs the negative controls, and writes the certificate.

> **Ingestion must sit behind `if __name__ == "__main__":`.** MDIO's header parser uses a `spawn` multiprocessing context; without the guard the child re-executes your script. This is measured, not theoretical.

| Command | What it does |
|---|---|
| `sdip doctor` | Environment sanity. If it fails, nothing else runs |
| `sdip spec build` | Build a gap-free trace-header specification |
| `sdip ingest` | SEG-Y → MDIO |
| `sdip verify` | Run the Equivalence Engine against an existing store |
| `sdip export` | MDIO → SEG-Y |
| `sdip certify` | The full chain, ending in a certificate |

---

## What it is proven on

SDIP has issued a certificate on a real survey: **494,565,408 bytes, 116,532 traces**, SEG-Y rev 1, big-endian, poststack 3-D — every check passing, from a clean working tree.

It is **deliberately narrow**. Where a format, geometry or backend has not been measured, SDIP **refuses with a named reason** rather than converting it anyway. A tool that half-works on data it does not understand produces exactly the artifact this project exists to prevent.

Everything measured is recorded in [`DECISIONS.md`](DECISIONS.md); everything not yet measured is in [`OPEN_DEBTS.md`](OPEN_DEBTS.md), each naming the experiment that would settle it. Issued certificates are indexed in [`EQUIVALENCE_LEDGER.md`](EQUIVALENCE_LEDGER.md).

---

## Not in scope, on purpose

**SDIP does not process seismic data.** No filtering, scaling, resampling, regridding, muting, interpolation or denoising. It is an identity map with a receipt, and every one of those would break the only promise it makes.

It does not invent a format either — it adopts **MDIO v1** and pins its upstream dependencies exactly, because a certificate issued under one version of a decoder says nothing about another.

---

## Contributing

Contributions are welcome under Apache-2.0 with a DCO sign-off. Start with [`CONTRIBUTING.md`](CONTRIBUTING.md) — it states the rules a change is held to, and invites an issue wherever a rule is unclear.

Security issues: [report privately](https://github.com/zahidaramai/sdip/security/advisories/new). SDIP parses binary files it did not create, so it treats untrusted input as a real attack surface — see [`SECURITY.md`](SECURITY.md).

---

## License

**Apache-2.0.** See [`LICENSE`](LICENSE) and [`NOTICE`](NOTICE).

The round-trip test fixture is adapted from [`TGSAI/mdio-python`](https://github.com/TGSAI/mdio-python) (Apache-2.0); attribution in `NOTICE` is a legal obligation and survives refactors.

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
