# Fixture provenance — binding

**No proprietary or restricted data enters this repository, ever** (specification §6.6).

Every fixture is one of exactly two things:

1. **Synthetic** — generated deterministically by **committed code** with a **fixed
   seed**. The generator is in the repository; the bytes may or may not be, depending
   on size.
2. **Openly licensed and redistributable** — with licence and provenance recorded in
   the table below.

**Large open datasets are fetched at test time by checksum, never vendored.**

The `fixture-policy` CI job fails on any file in `tests/fixtures/` that has no entry in
this file.

---

## Synthetic fixtures

| File / generator | Generator | Seed | Shape | Purpose | Gate |
|---|---|---|---|---|---|
| *(none yet)* | | | | | |

Synthetic fixtures are generated, not committed, wherever the generator is fast and
deterministic. A committed generator plus a fixed seed **is** the fixture: it is
smaller, it is diffable, and it cannot drift from what produced it.

## Openly licensed fixtures

| Dataset | Source | Licence | SHA-256 | Fetched at test time | Purpose |
|---|---|---|---|---|---|
| *(none yet)* | | | | | |

A vendored open dataset needs a licence column that is filled in and a URL that
resolves. If either is missing, it does not go in.

## Measurement sources — used, never entering this repository

**A measurement source is not a fixture, and putting one in the tables above would be a
false entry** — those tables describe data that either ships in the repository or is
fetched by a test. The dataset below does neither. It is recorded here because it is
named in the public record and measurements taken from it are published, so its
provenance must be auditable from the repository alone.

| Dataset | Owner | Portal | Licence | Redistributed | Used for |
|---|---|---|---|---|---|
| Sleipner CO₂ Reference Dataset — 4D seismic, 2006 vintage, full-stack volume (494,565,408 B, 116,532 traces) | The Sleipner Group — Equinor Energy AS (operator), ExxonMobil Exploration and Production Norway AS, LOTOS Exploration and Production Norge AS, KUFPEC Norway AS | [CO2DataShare](https://co2datashare.org/dataset/sleipner-4d-seismic-dataset) | Sleipner CO2 Reference Dataset License | **No — never, in any form** | At-scale certificate (ledger row 1); G5 wall-clock and RSS calibration |

**No Sleipner data is in this repository, its history, the published wheel, sdist or
container image, and no test fetches it.** What is public is measurements *about* it —
digests, byte counts, trace counts, timings — and **a digest is not data** (`D-0025`).
Attribution is in [`NOTICE`](../../NOTICE) §6, which also records the licence's
no-endorsement clause: the dataset names must not be used to promote SDIP.

Anyone reproducing the at-scale run obtains the dataset from the portal under its own
licence. **The synthetic fixtures are the reproducible path**; the at-scale run is
corroboration, and the ledger row carries the digest so the claim is checkable by anyone
who holds the same file.

## Fixtures planned, per probe

Registered here before they exist so the policy is applied at design time, not at
review time:

| Fixture | Probe | Property it carries |
|---|---|---|
| 30-trace 3D poststack, rev 1, planted bytes 233–240 | P1 | The banked Appendix A.1 article |
| `dead_traces` | P5 | Live and dead interleaved; live-mask discrimination |
| `duplicate_index` | P5 | Two traces with identical inline/crossline |
| `sparse_grid` | P5 | Large unpopulated regions |
| `ragged_lines` | P5 | Inlines of differing crossline extent |
| `missing_lines` | P5 | Whole inlines absent mid-range |
| `coord_scalar_{zero,pos,neg}` | P5 | Coordinate-scalar edge cases |
| `byte_swapped` | P5 | Big- and little-endian variants of one file |
| `rev{0,1,2,2_1}_minimal` | P6 | One fixture per revision |
| `ibm32_exponent_sweep` | P2 | Exhaustive IBM exponent codes |
| Prestack: shot, streamer field record, OBN receiver | P7 | Prestack geometries |
| Fuzz corpus for the header parser | §11.4 / D8 | Untrusted-input handling |

---

## Local-only verification data — permitted, never committed

A maintainer may verify SDIP against **real survey data licensed for local use only**.
That data is *used*, never *entered*: it lives outside the repository, everything
derived from it is written to `local/`, and `local/` is in the publication firewall
alongside `docs/`.

Three rules make this safe rather than a loophole:

1. **Nothing derived is committed — including certificates.** A certificate carries a
   source path and a source hash, so a certificate issued against restricted data is
   itself restricted.
2. **CI never depends on it.** Every committed test passes on the synthetic fixtures
   alone. A test that needs data CI cannot fetch is a test that does not run.
3. **Results are reported with their scope.** A measurement taken on such a dataset is
   real and should be recorded, naming the dataset and the N — but a single run on one
   large file is **not** a scale probe. Probe **P3** requires a pre-registration with
   declared ceilings merged *before* the run (**SP9**).

**Where the register lives, and the one thing that must not stay in it.** The register of
locally held datasets — which files a maintainer has and where — is kept **outside** this
repository: it is a list of local paths, and it is nobody else's business.

**A dataset stops being purely local the moment measurements from it are published.** Once
the public record names a dataset and carries numbers taken from it, that dataset's
provenance and attribution must be public too — otherwise the repository is asking readers
to trust a measurement whose source it will not fully identify, and any attribution the
source licence requires goes unpaid. The *path* stays private; the *identity, owner and
licence* become public. Those are different facts, and only the first is sensitive.

The one dataset this currently applies to is recorded above under
[Measurement sources](#measurement-sources--used-never-entering-this-repository), with its
attribution in [`NOTICE`](../../NOTICE) §6.

---

## If you hit a bug on data you cannot share

Reproduce it with a synthetic file that has the **same structural property** — byte
layout, revision, geometry irregularity — and attach that.

A synthetic reproducer is more useful anyway: **it becomes a permanent fixture.**
