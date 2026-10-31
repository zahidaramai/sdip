# P25 — Do the installed upstream files come from the pinned commits? (D9)

> **SP9.** Committed **before** either repository is fetched. The commit is local only: GeoSuite
> pushes under its own approval. Sections above the results separator are never edited.

| Field | Value |
|---|---|
| Probe | `P25` |
| Status | `REGISTERED` |
| Registered | 2026-11-01 |
| Registered by | Claude Code session, on GeoSuite's order under owner D-216; the two read-only fetches approved by GeoSuite on 2026-11-01 |
| Related debt | `OPEN_DEBTS.md` D9 (narrowed by D-0016) |
| Spec clause | operating contract §3.2 (pins are binding); SP8 |

## Question

`sdip doctor` verifies each pinned distribution's version, its artifact hash in `uv.lock`, and
every installed file against the wheel's own `RECORD`. None of that shows the wheel was built
from the declared commit, so every certificate says `commit_sha_verified: false`. **Is every
installed package file of `multidimio` 1.2.1 and `segy` 0.6.0 byte-identical to the same file
in the source tree at the pinned commit?**

## Method

1. Fetch exactly one commit of each public repository, read-only, into the run root:
   - `https://github.com/TGSAI/mdio-python.git` at `76df396e545017d2a32ee25a5f98989fa37afec4`;
   - `https://github.com/TGSAI/segy.git` at `557bceba4abce09d084a1f0b8ac466382ce5c502`.

   Each uses `git init`, then `git fetch --depth 1 <url> <sha>`, then `git checkout FETCH_HEAD`.
   `git rev-parse HEAD` must equal the declared SHA, or the run stops and reports it. Nothing
   is sent, filed or pushed (D-0089). Both trees are deleted at harvest.
2. **Compared set:** every entry in the installed `RECORD` whose path starts with the package
   directory (`mdio/` or `segy/`). Each is compared, as sha256 of its bytes, with the file at
   `src/<same path>` in the fetched tree, or `<same path>` at the tree root if the repository
   has no `src/`.
3. **Not compared, listed:** the `*.dist-info/` files (written by the build and the installer)
   and the console scripts under `bin/` (written by the installer). No source file corresponds
   to any of them.
4. **Listed, both ways:** an installed package file with no source counterpart, and a source
   file under the package directory that the wheel does not carry.

No wheel is built: the question is about content, and a rebuild would add a build backend and
its own fetches.

## Outcome classes (registered before the fetch)

Per distribution:

- **MATCH:** every file in the compared set equals its source file byte for byte, and no
  installed package file lacks a source counterpart.
- **BUILD-DIFFERENT:** every compared file present in both trees is equal, but at least one
  installed package file has no source counterpart (generated at build time), or the wheel
  leaves out source files. Each such file is listed by path. This is an honest result: **the
  commit is attested by source comparison, and the wheel is not byte-reproducible from the
  tree.** It is not a pin failure.
- **MISMATCH:** at least one file present in both differs in content. Each is listed, with
  both hashes. That is a §9 finding: it is recorded and asked about, not fixed here.

## What each outcome does

- **MATCH or BUILD-DIFFERENT:** D9 can close on commit attestation by source comparison, if
  ruled. Whether `commit_sha_verified` is then set from a committed attestation, or a new field
  is added, is a certificate-schema change and is asked, not done here.
- **MISMATCH:** D9 stays OPEN, and the difference is the finding.

## Scope

Two pinned distributions, one platform (pure-Python wheels, `py3-none-any`). Compiled
extensions are not involved. The attestation holds for the files this environment has
installed. It says nothing about a different installer or a different index.

---

## Results — *appended after the run, never edited into the sections above*
