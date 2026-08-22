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

The register of such datasets is kept outside this repository.

---

## If you hit a bug on data you cannot share

Reproduce it with a synthetic file that has the **same structural property** — byte
layout, revision, geometry irregularity — and attach that.

A synthetic reproducer is more useful anyway: **it becomes a permanent fixture.**
