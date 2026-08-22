# DECISIONS — append-only

**SP10.** This file is append-only. A wrong entry is corrected by a **new entry citing
the original**, never by editing or deleting the original. Maintainer errors are
recorded as maintainer errors — specification Appendix A.4 sets the precedent.

Format: `D-NNNN`, date, decision, the measurement or reading behind it, and what would
overturn it.

---

## D-0001 — 2026-08-22 — Supported Python window is `>=3.12,<3.14`

**Decision.** `requires-python = ">=3.12,<3.14"`. Primary development and the CI
baseline are 3.12; 3.13 is tested in the matrix.

**Measurement.** Read from the pinned distributions' own metadata, not from
documentation:

| Package | `Requires-Python` |
|---|---|
| `multidimio` 1.2.1 | `>=3.12,<3.15` |
| `segy` 0.6.0 | `>=3.11,<3.14` |

The intersection is `>=3.12,<3.14`. Specification Appendix A banked its measurements
on Python 3.12.3; the environment reproduced here is 3.12.13.

**What overturns it.** A pin bump (§3.3), which is a maintainer decision in its own
right and would require a new entry here.

---

## D-0002 — 2026-08-22 — Upstream API claims in §3.2 verified against the pinned code

**Decision.** The "pin, don't fork" conclusion stands. No fork is authorised; the
fallback in §8.9 stays dormant.

**Measurement.** Each of the three links in the §3.2 chain was checked by importing the
pinned distributions and reading the live objects — not by reading the repository on
GitHub. All three, including the line numbers cited in §3.4, are exactly as stated:

| Claim | Cited | Observed |
|---|---|---|
| `build_mdio_header_type` derives the persisted dtype from `segy_spec.trace.header.dtype`, no whitelist | `mdio/segy/utilities.py:45` | present at `:45`; body is `to_structured_type(segy_spec.trace.header.dtype)` then `ibm32 → float32` promotion. No whitelist. |
| `HeaderField` accepts an arbitrary name at `byte >= 1`; `UINT8` is in `ScalarType` | `segy/schema/header.py:47` | present at `:47`. `ScalarType` = IBM32, INT64/32/16/8, UINT64/32/16/8, FLOAT64/32/16, STRING8. `HeaderField(name="pad_233", byte=233, format=UINT8)` constructs. `byte=0` raises `ValidationError`. |
| `HeaderSpec.customize` merges into an existing spec | `segy/schema/header.py:270` | present at `:270`, signature `(self, fields: HeaderField \| list[HeaderField]) -> None`. |

**What overturns it.** Any pin bump; re-run the verification before accepting one.

---

## D-0003 — 2026-08-22 — Header coverage measured for every revision, not just rev 1

**Decision.** Bank the full revision table. It sharpens **P6** and it narrows **P2**.

**Measurement.** Same method as Appendix A.2, applied to every standard the pinned
`segy` exposes (`REV0`, `REV1`, `REV2`, `REV21`):

| Revision | Declared fields | Bytes covered | Uncovered | Overlaps | `ibm32` fields | Gap-free field count |
|---|---|---|---|---|---|---|
| rev 0 | 71 | 180 / 240 | 181–240 (60 bytes) | 0 | **0** | **131** |
| rev 1 | 89 | 232 / 240 | 233–240 (8 bytes) | 0 | **0** | **97** |
| rev 2 | 90 | 240 / 240 | none | 0 | **0** | **90** |
| rev 2.1 | 90 | 240 / 240 | none | 0 | **0** | **90** |

Appendix A.2's rev 1 numbers are reproduced exactly (89 / 232 / 233–240 / 0 / 97).

**Three consequences.**

1. **The field-count conclusion generalises.** The worst case across all revisions is
   131 fields, not 240 — still far below any plausible structured-dtype limit. The
   suspected P1 falsifier does not fire on any revision.
2. **rev 2 and rev 2.1 are gap-free as shipped.** G1 passes with zero fillers. The
   filler mechanism is a rev 0 / rev 1 concern.
3. **P2's header leg is narrower than written.** No revision's *standard* trace header
   declares a single `ibm32` field, so `ibm32` in headers can only arrive through a
   survey spec override (§6.4). P2's sample-format leg is untouched and remains
   blocking. Recorded in `OPEN_DEBTS.md` against D1.

**What overturns it.** A `segy` pin bump changing a standard, or a survey override that
declares `ibm32` header fields — which is precisely the case P2 must clear first.

---

## D-0004 — 2026-08-22 — SP6 is implemented as suppression *detection*, not re-raising

**Decision.** `sdip.guard.warn` records observable warnings **and** detects the
installation of a suppression, classifying it against a committed list read out of the
pinned upstream source. It does not attempt to re-raise a warning suppressed inside a
dependency.

**Measurement.** `multidimio` 1.2.1 suppresses two Zarr warnings in
`mdio/core/zarr_io.py`. Read verbatim from the installed artifact:

```python
@contextmanager
def zarr_warnings_suppress_unstable_structs_v3():
    warn = r"The data type \((.*?)\) does not have a Zarr V3 specification\."
    warnings.filterwarnings("ignore", message=warn, category=UnstableSpecificationWarning)
    try:
        yield
    finally:
        pass  # the filter is never restored
```

Run, not read:

- Entering both context managers once takes `len(warnings.filters)` from **10 to 12**
  and leaves it there. Neither uses `warnings.catch_warnings()`, and both end in
  `finally: pass`, so the `ignore` filter **leaks process-globally**.
- An outer `catch_warnings(record=True)` with `simplefilter("always")` observes
  **0** of the suppressed warnings: upstream's filter is inserted at the front of the
  list and matches first.

**Why not re-raise.** Defeating a filter installed inside a dependency requires
monkeypatching, which §3.3 forbids without exception. Forking for this is not
proportionate and §8.9 stays dormant.

**What is done instead**, and it is strictly more informative than a re-raise:

1. Every warning that is *not* suppressed is observed, undeduplicated, so a per-trace
   warning is counted per trace.
2. `warnings.filters` is diffed across the guarded call. A filter that appears is
   evidence a suppression was installed and is recorded on the certificate with its
   action, category, and message regex.
3. Each detected suppression is classified `declared` — matching
   `KNOWN_UPSTREAM_SUPPRESSIONS`, read out of the pinned source — or **`UNDECLARED`**.
   An undeclared suppression appearing after a pin bump is a finding, automatically.
4. The filter list is restored on exit, containing the upstream leak to the guarded
   call. SDIP does not leave the interpreter quieter than it found it.
5. The underlying condition is detected without warnings at all: **G4** reads
   `zarr.json` and reports any array whose `data_type` is outside the Zarr v3 core
   specification. The warning is a signal; the store is the evidence.

**Upstream finding to raise** (§3.3: route around nothing, report it). The two
context managers in `mdio/core/zarr_io.py` mutate global warning state without
restoring it. A caller that enters either one is permanently deafened to those
warnings for the rest of the process. Tracked as **D10** in `OPEN_DEBTS.md`.

**What overturns it.** Upstream scoping the filters correctly, which would make a
plain recording context manager sufficient — but only for warnings raised *outside*
their block. Re-check on every pin bump.

---

## D-0005 — 2026-08-22 — The licence gate reads authoritative declarations only

**Decision.** The runtime-licence scan uses tiered evidence — `License-Expression`,
then `License ::` classifiers, then the `License` field **only when it is a single
line of at most 200 characters** — and matches barred tokens with word-boundary
regexes. It never substring-scans a licence *text*.

**Measurement.** A naive substring scan for `"GPL"` over the `License` metadata field
flags **`pandas` 2.3.3**, which is BSD-3-Clause. pandas embeds its full **63,416-byte**
licence file in that field, including the bundled PSF licence text, which discusses
GPL compatibility at length ("most, but not all, Python releases have also been
GPL-compatible…"). `pathlib_abc` embeds 2,278 bytes for the same reason.

A gate that fires on prose is a gate that gets switched off. Per **SP11** that makes it
worse than no gate: it trains the reader to ignore it.

Two further rules follow from the same run:

- **`LGPL` is a distinct token.** `\bGPL\b` does not match inside `LGPL`, and
  `GPL-compatible` is excluded explicitly. `seisio` is LGPL, is cited as design prior
  art only, and is not in the tree — the scan confirms that rather than assuming it.
- **Environment markers must be evaluated.** Without marker evaluation the walk of this
  tree reports `colorama`, `importlib_metadata`, and `inspect2` as missing
  dependencies. All three are conditional on platforms or interpreter versions that do
  not apply. `packaging` does the evaluation and is already a hard runtime dependency
  of `dask`, `xarray`, and `zarr`, so declaring it explicitly adds **nothing** to the
  tree being scanned.

**Result.** 51 runtime distributions, **zero GPL or AGPL entries**, one undetermined
(see D-0006).

**What overturns it.** A distribution whose only declaration is a long free-text field
naming a copyleft licence. It would land as `UNDETERMINED` — which fails the scan —
rather than passing silently, so the failure mode is safe.

---

## D-0006 — 2026-08-22 — `google-crc32c` allowlisted with cited evidence

**Decision.** `google-crc32c` is entered in `LICENCE_ALLOWLIST` with the evidence
below. It is the only entry.

**Measurement.** `google-crc32c` 1.8.0 ships **no** `License-Expression`, **no**
`License ::` classifier, and **no** `License` field. Its metadata keys are
`Author, Author-email, Description, Description-Content-Type, Dynamic, Home-page,
License-File, Metadata-Version, Name, Platform, Requires-Python, Summary, Version`.
It therefore resolves as `UNDETERMINED`, which fails the scan by design.

Evidence read from the installed artifact on 2026-08-22:

- The wheel bundles `google_crc32c-1.8.0.dist-info/licenses/LICENSE`, which is the
  verbatim Apache License 2.0.
- `Author: Google LLC`, `Home-page: https://github.com/googleapis/python-crc32c`,
  which is Apache-2.0.

**Why an allowlist and not a fourth evidence tier.** Parsing a bundled licence *text*
to identify a licence is the same substring-over-prose hazard D-0005 rejects. An
explicit entry with cited evidence is auditable; a heuristic is not. This mirrors §6.4:
**an override with no cited evidence is rejected at review.**

**What overturns it.** `google-crc32c` declaring its licence in metadata, at which
point the entry is removed by a new decision citing this one.

---

## D-0007 — 2026-08-22 — `sdip doctor` has no override flag, and the tree check is FAIL-severity

**Decision.** All seven doctor checks are FAIL-severity. Exit 0 only when every check
passes. There is no `--force`, no `--allow-dirty`, and no `WARN` status.

**Reasoning.** §11.3 states that a certificate from a dirty tree is invalid and §3.5
forbids a `--force` on `certify`. A doctor that can be talked out of the same finding
teaches the operator that the finding is negotiable, which is how §3.5 gets worked
around in practice rather than in code. Gates are binary (§7); the report type has no
`WARN` member for the same reason.

**Consequence, stated plainly.** During development the tree is usually dirty, so
`doctor` usually exits 1 on `working-tree` alone. That is the correct reading: the
environment is fine and the run is not certifiable. `--json` names the failing check,
so a runbook can distinguish the two without a flag that suppresses the finding.

**What overturns it.** Nothing short of a change to §11.3, which is a successor-version
change (§12.1).

---

## D-0008 — 2026-08-22 — Unbuilt commands refuse; they do not stub

**Decision.** `sdip spec build`, `ingest`, `verify`, `export`, and `certify` are
declared in the CLI and raise `PhaseNotAuthorisedError` naming their roadmap phase.
The subpackages under `src/sdip/` exist with the same behaviour.

**Reasoning.** §0 — an MDIO store without a passing certificate is an untrusted
artifact. A command that returns a plausible-looking result it did not compute is the
mechanism by which that happens. Refusing is louder than `NotImplementedError` and
carries the phase number, so the operator learns where the work actually is.

**What overturns it.** Implementing the command.

---

## D-0009 — 2026-08-22 — CLI framework is `click`; no new runtime dependency

**Decision.** The CLI uses `click`, declared explicitly at `>=8.4.2`.

**Reasoning.** `click` is already a hard runtime dependency of `multidimio` 1.2.1, so
declaring it adds nothing to the runtime tree the licence job scans (BSD-3-Clause).
`argparse` was the alternative and would have added nothing either, but `click` gives
subcommand grouping and `--json` handling without hand-rolled parsing, and the tree is
unchanged either way. `typer` and `rich` are present transitively via `segy` and
`multidimio` and are deliberately **not** declared: SDIP's own output is plain text
plus JSON, because a certificate pipeline is read by machines and CI logs before it is
read by a terminal.

**What overturns it.** `click` leaving the `multidimio` dependency tree at a pin bump,
which would make it a genuinely new dependency and require a fresh decision.

---

## D-0010 — 2026-08-22 — `docs/` and every AI-assistant artifact are never published

**Decision.** This repository is published on GitHub. The following are maintained on
the working copy and are **never committed, at any size, for any reason**:

- **`docs/` in full** — the governing specification, the internal companion, the
  pre-registrations, the runbooks, and the certificate schema.
- **Every AI-assistant artifact** — `CLAUDE.md`, `CLAUDE.local.md`, `AGENTS.md`,
  `.claude/`, `.claude-session-sync.md`, `.cursor/`,
  `.github/copilot-instructions.md`.

This supersedes the narrower firewall recorded implicitly in D-0007's sibling checks,
which covered only `docs/SDIP_Internal_Companion.md`. It also **reverses** the
`!CLAUDE.md` negation added earlier in the same session to defeat a machine-wide
`core.excludesFile`: that negation was correct against specification §6.3, which lists
`CLAUDE.md` in the repository layout, and is wrong against this decision. The
specification's layout is followed on the working copy; publication is narrower.

**Why three mechanisms and not one.**

| Mechanism | Catches | Defeated by |
|---|---|---|
| `.gitignore` | an accidental `git add -A` | `git add -f`; a rule added after the file was tracked |
| `sdip doctor` → `publication-firewall` | anything in the **index or `HEAD`** | not running doctor |
| CI `firewall` job | anything in **any commit reachable from any ref** | nothing in-repo |

The CI job deliberately does **not** declare `needs: doctor` and does not use Python. A
broken environment is exactly the situation in which someone force-adds a file to make
a check go away, so the job that catches that cannot depend on the environment being
healthy.

**Why history, not just the index.** `git rm --cached` removes a file from the index
and leaves it in every commit that already contained it. **A clone receives history.**
Checking `HEAD` alone would report clean while a reader who cloned still received the
file. Both the doctor check and the CI job therefore inspect commits, not only the
working state.

**Action taken.** Commit `96e75c8`, the single root commit of this repository, contained
`docs/` (16 files) and `CLAUDE.md`. It was never pushed. The branch ref was deleted and
a new root commit written from an index with those paths removed, then the reflog was
expired and the object database pruned. **No commit in this repository has ever
contained them**, which is the only state that satisfies the requirement — untracking
them going forward would not have.

**Consequence for the public repository, stated plainly.** `README.md` and
`CONTRIBUTING.md` previously linked into `docs/`. Every such link is removed rather than
left dangling, and `CONTRIBUTING.md` now says explicitly that the specification is not
distributed here, that every rule it imposes on a contribution is restated in
`README.md`, `CONTRIBUTING.md`, and this file, and that a rule which appears in none of
the three is a defect in those files. `pyproject.toml` no longer ships `/docs` in the
sdist either — the firewall has to survive `uv build` as well as `git push`.

**What overturns it.** A maintainer decision to publish a specific document, recorded
as a new entry citing this one, and removing that path from `NEVER_PUBLISH`, from
`.gitignore`, and from the CI job in the same commit.

---

## D-0011 — 2026-08-22 — Copyright holder resolved; repository published

**Decision.** The `LICENSE` copyright line and the `NOTICE` attribution are held by
**Zahid Aramai**, personally. `CITATION.cff` names the same holder. The repository is
published at `github.com/zahidaramai/sdip`, public, Apache-2.0.

**Closes** `OPEN_DEBTS.md` **D12**, which was blocking the first public push. Recorded
here rather than by editing D12: the record is append-only (**SP10**), so D12 keeps its
text and gains a closure entry beneath it.

**Note on scope, stated because it is a legal question and not a technical one.** The
internal companion §6 pairs the copyright decision with employment-policy clearance for
publishing under a personal identity. This entry records the copyright holder as
decided by the maintainer. It does **not** record that clearance was obtained, because
that is not something this repository can observe. If clearance turns out to be
required and absent, the remedy is a new entry here and a change of holder — not a
silent edit of this one.

**What overturns it.** A determination that the work is owned by an employer, which
would require a new entry, a corrected `NOTICE` and `CITATION.cff`, and a decision about
whether the repository may remain published at all.

---

## D-0012 — 2026-08-22 — Gate CI jobs arm themselves instead of failing while unbuilt

**Decision.** The five gate jobs — `integration`, `negative-G7`, `portability-G4`,
`spawn-guard`, `determinism-G6` — run on every PR, look for their own subject in the
tree, and either run the real check or report `NOT_RUN` with their roadmap phase. They
begin enforcing automatically the moment their subject file appears.

**Correcting D-0007's sibling reasoning, and an error in the F0 commit.** Those jobs
were originally written to `exit 1` with their roadmap phase, on the argument that an
absent job renders as a green check. The first half of that argument is right and
stands. The second half was wrong, and would have been wrong in a way that damaged the
project:

- Specification §7.8 states that **any failure blocks merge**.
- A job that always fails therefore blocks **every** PR, permanently — **including the
  PR that would build the very thing it is waiting for.**
- A gate that cannot be satisfied by doing the work is not strict. It is broken, and a
  broken gate gets deleted or bypassed, which leaves the project worse off than a
  missing one (**SP11**).

This was caught before the first push, while preparing the repository for publication.
It is recorded as a maintainer error, on the precedent set by Appendix A.4.

**Why self-arming rather than a checklist item.** The failure mode of "remember to
switch the job on when you build the thing" is that nobody remembers, and the gate is
discovered to have been inert only when something has already gone wrong. Keying the
job to the presence of its own subject removes the human step entirely.

**What green means now, stated so it cannot be misread.** A green build means
*everything that exists passes*. It does **not** mean the gates pass. The `roadmap` job
writes the state of all seven gates into every run summary, `README.md` states the
current phase, and `OPEN_DEBTS.md` **D11** records that **until G7 passes, every
certificate the engine issues is unvalidated**.

**What overturns it.** All seven gates existing, at which point the arming logic is
dead code and should be removed by a new entry citing this one.

---

## D-0013 — 2026-08-22 — Employment-policy clearance attested; publication cleared

**Decision.** The maintainer attests that SDIP is **personal work, created outside the
scope of any employment**, and is **clear to publish under a personal identity**.

**Closes** the second half of the pairing in the internal companion §6, which held the
copyright decision and employment-policy clearance together as jointly blocking for the
first public push. D-0011 recorded the copyright and stated explicitly that clearance
was *not* attested, because it is not something this repository can observe. This entry
records the attestation, given by the maintainer on 2026-08-22.

**What this entry is, and what it is not.** It is a record of an attestation by the
person entitled to make it. It is not a legal opinion, and no automated check verifies
it — no check could. It is recorded here so that the basis for publication is written
down and dated rather than assumed, on the same principle as every other claim in this
file: **the record says who claimed what, and when.**

**Consequence.** `NOTICE` and `CITATION.cff` name Zahid Aramai personally, consistently
with this attestation. The repository stays public at `github.com/zahidaramai/sdip`.
`OPEN_DEBTS.md` **D12** is now closed in both halves.

**What overturns it.** A determination that the work falls within an employment scope
after all. That would require a new entry citing this one, a corrected `NOTICE` and
`CITATION.cff`, and a decision on whether the repository may remain published — the
last of which is materially harder now than it was before the first push, which is
precisely why the attestation is dated.

---

## D-0014 — 2026-08-22 — Reporting runs through GitHub private advisories; no email published

**Decision.** `SECURITY.md` and `CODE_OF_CONDUCT.md` route every report through
**GitHub private vulnerability reporting**. `CITATION.cff` carries `alias: zahidaramai`
and **no email address**. GitHub private vulnerability reporting is enabled on the
repository.

**Reasoning.** `SECURITY.md` previously named the maintainer contact in `CITATION.cff`,
which meant publishing a personal email address in a machine-readable file on a public
repository — a durable, scrapable target, and a different exposure from the same address
appearing in commit author metadata where a reader has to go looking for it.

A private advisory thread is also simply the better channel for what this project
receives:

- It is **private by construction** until a fix ships, which an inbox is not.
- It gives the reporter a **durable record** and a **CVE path**.
- It has **coordinated-disclosure controls** built in.
- It has **no single point of failure** in a personal mailbox.

`SECURITY.md` says so explicitly rather than leaving the absence of an email looking
like an oversight.

**On the Code of Conduct using the same channel.** Not ideal semantically — a conduct
report is not a vulnerability report. It is chosen because it is the only channel this
repository can offer that is genuinely private, and a Code of Conduct whose reporting
address does not exist is worse than one that reuses a working private channel. Revisit
if the project gains a dedicated address.

**What overturns it.** A purpose-made address on a domain the maintainer controls, at
which point `SECURITY.md` gains it as an alternative and `CODE_OF_CONDUCT.md` moves to
it. Recorded as a new entry citing this one.

---

## D-0015 — 2026-08-22 — Certificate schema ships inside the package, not in `docs/`

**Decision.** The Equivalence Certificate JSON Schema lives at
`src/sdip/schema/sdip-certificate-v0.schema.json`, is tracked in the public repository,
and is shipped in both the wheel and the sdist. `docs/certificate-schema/` is deleted.

**The problem this closes.** Specification §4.7 requires the certificate schema to be
*"published so third parties can validate SDIP output without running SDIP."* D-0010
made `docs/` unpublishable, and the only copy was there — so `git ls-files | grep
schema.json` returned **zero**, and §4.7's requirement was silently unsatisfiable. F8
also lists "published certificate schema" as a release deliverable it could not have
reached.

**Why this is not a firewall exception.** The schema is **not documentation.** It is a
machine artifact that `sdip certify` needs at runtime to validate its own output, and
that a consumer needs to check a certificate they were handed. D-0010 bars `docs/` and
AI-assistant artifacts; it does not bar machine-readable contract artifacts, and
relocating one to where it belongs is not a hole in the firewall.

Shipping it in the package is also strictly better than shipping it in the repository
root: `pip install sdip` now carries the validator to a consumer who never clones, which
is closer to what §4.7 actually asks for than a file in a git tree.

**No validator is vendored.** `sdip.schema.load_schema()` returns the parsed document;
validating against it is the caller's choice of library. Adding a JSON Schema validator
to the runtime tree would add a dependency and a licence surface for something every
consumer already has.

**Verified.** `uv build` produces a wheel containing
`sdip/schema/sdip-certificate-v0.schema.json`, an sdist containing the same, and
**neither contains `docs/`**. A test asserts the schema is *tracked*, not merely present
on disk — "published" means a reader can obtain it.

**What overturns it.** A decision to publish `docs/`, which would make the location a
matter of taste again rather than of correctness.

---

## D-0016 — 2026-08-22 — Pin verification extended to artifacts and installed files

**Decision.** `sdip.guard.pins` now makes three separate claims and keeps them separate:

| Claim | Status | Attests |
|---|---|---|
| **Version** | verified | installed metadata matches the pin exactly |
| **Artifact sha256** | read from `uv.lock` | the bytes `uv sync --frozen` enforces at install time — **the artifact, not the commit** |
| **Installed files** | verified | every file recomputed against the wheel's own `RECORD` manifest |
| **Commit SHA** | **NOT verified** | — |

**Measured.** **145** installed files across the two pinned distributions
(`multidimio` 100, `segy` 45) recompute to their `RECORD` digests. Artifact hashes for
both the sdist and the wheel of each pin are present in `uv.lock` and are now recorded
on the certificate rather than left implicit in a lockfile nobody quotes.

**What this actually buys.** The realistic way a pinned dependency stops being what the
pin says — without the version changing and without anything else noticing — is someone
editing `site-packages` to make a gate pass. `RECORD` verification catches exactly that,
and it is cheap: roughly 150 small hashes.

**What it does not buy, stated because the temptation is to overclaim.** None of this
attests that the wheel was built from the declared commit. A wheel does not carry the
SHA it was built from. Closing that needs a source build or an upstream provenance
attestation, and neither exists under the current pins.

**D9 is therefore `NARROWED`, not closed**, and every code path keeps saying so:
`PinStatus.commit_sha_verified` is `False`, the JSON carries
`"does_not_attest": "that the wheel was built from the declared commit"`, and a test
asserts both — so a future change that starts claiming verification has to edit the
assertion deliberately.

**Negative controls** ship with it: tampering with an installed file is detected, and
deleting one is detected as `missing` rather than silently passing.

---

## D-0017 — 2026-08-22 — Upstream warning-filter leak reported

**Decision.** Filed as **[TGSAI/mdio-python#864](https://github.com/TGSAI/mdio-python/issues/864)**.

**Why it is a decision and not a chore.** §3.3 is explicit: where something appears to
need reaching into upstream internals, *"that is a finding to raise in an issue, not a
problem to route around."* SDIP routed around it in D-0004 by detecting the suppression
instead of defeating it. Routing around **and not reporting** would have left the
project quietly benefiting from knowledge of a defect it never disclosed, which is the
posture this project criticises in others.

**What was reported.** `zarr_warnings_suppress_unstable_structs_v3` and
`zarr_warnings_suppress_unstable_numcodecs_v3` call `warnings.filterwarnings("ignore",
…)` without `warnings.catch_warnings()` and end in `finally: pass`, leaking a
process-global filter. Every claim in the issue was re-verified against the pinned code
immediately before posting: no `catch_warnings` in `zarr_io`, `finally: pass` present,
`creation.py` *does* use the correct pattern, filters go 10 → 12 and stay, and an outer
`always`+`record` observes 0 suppressed warnings.

**Resolves** the reporting obligation in `OPEN_DEBTS.md` **D10**. The debt itself stays
open until upstream acts or declines — SDIP does not get to close a debt by writing
about it.

---

## D-0018 — 2026-08-22 — F1 built: gap-free spec generator and G1

**Decision.** `src/sdip/spec/` implements specification §5.1 construction and gate **G1**.
`sdip spec build` is live.

**Measured, reproducing `DECISIONS.md` D-0003 through the generator rather than by
static arithmetic:**

| Revision | Base fields | Fillers | Gap-free fields | Itemsize | G1 |
|---|---|---|---|---|---|
| rev 0 | 71 | **60** (`pad_181`…`pad_240`) | **131** | 240 | PASS |
| rev 1 | 89 | **8** (`pad_233`…`pad_240`) | **97** | 240 | PASS |
| rev 2 | 90 | **0** — already gap-free | **90** | 240 | PASS |
| rev 2.1 | 90 | **0** — already gap-free | **90** | 240 | PASS |

**Three design calls worth recording.**

**1. Coverage arithmetic is separate from the generator, and G1 is separate from both.**
G1 takes a field set, not a generator output, so it can judge a spec SDIP did not build:
a survey override (§6.4), a hand-written spec, a spec from a future upstream. **A gate
that can only assess its own output is not a gate** (**SP11**).

**2. G1's four conditions are evaluated and reported independently.** `coverage`,
`no-overlaps`, `in-range`, `itemsize`, `no-void-gaps` each carry their own verdict and
their own detail string. A gate that collapses them into one boolean can say it failed
but not what to fix — and an over-broad check that fails everything on any defect cannot
localise a fault and gets silenced the first time it fires on something benign. This is
G7's *"fails its gate and only its gate"* clause applied one level down, and the negative
controls assert both halves: the target condition fails **and** the others still pass.

**3. A missing dtype is a failure, not a skip.** Called without a dtype, G1 reports
`itemsize` and `no-void-gaps` as **failed** with detail *"could not be checked"*. G1 is
pre-flight for an ingestion; **"could not check" is not "fine"**.

**Two upstream facts found while building, both now regression-tested.**

- **`ScalarType.STRING8` has the value `"S8"`, and numpy rejects `"s8"`.** Normalising
  case before the numpy lookup silently loses the only string format in the SEG-Y
  standard, which would then read as a field of unknown width. Case is preserved; a
  test asserts `np.dtype("s8")` still raises so the hazard cannot quietly disappear.
- **`ibm32` has no numpy equivalent** and is resolved by name before numpy is consulted.

**The base standard is deep-copied before customisation.** `get_segy_standard` returns a
fresh object per call today; relying on that would let a future upstream change to
caching silently corrupt the shared standard for every other caller in the process. A
test asserts the standard is unchanged after a build.

**`spec_sha256`** hashes the field manifest — name, start byte, width — in **byte
order**, not declaration order. Two specs declaring the same fields in a different order
are the same spec. rev 2 and rev 2.1 hash identically, which is correct: they declare
the same trace header.

**Negative controls ship in the same commit** (`CLAUDE.md` §4.2): the raw rev 0 and rev 1
standards fail G1 on `coverage` and `no-void-gaps` and nothing else; one dropped field
fails `coverage` only; a doubly-covered byte fails `no-overlaps` only; a 4-byte field at
byte 238 fails `in-range`; a 239-byte dtype fails `itemsize` only; a numpy-padded dtype
fails `no-void-gaps`.

**On where G1's controls live.** In `tests/unit/`, not `tests/negative/`. G7's controls
are store corruptions; G1 runs before a single trace is read, so no store exists to
corrupt and its controls construct a defective *specification* instead. Putting them in
`tests/negative/` would arm the `negative-G7` CI job on content that is not G7 and make
an unbuilt gate look built.

**Not built at F1**, and deliberately: survey spec overrides (§6.4). They are declarative
data requiring cited evidence at review, and nothing consumes them until ingest exists.

**Status: G1 is the first gate SDIP enforces.** Six remain unbuilt, and **G7 is still
among them** — see `OPEN_DEBTS.md` D11.

---

## D-0019 — 2026-08-22 — MDIO discards both SEG-Y file headers by default

**Measured**, read out of `multidimio` 1.2.1 and confirmed by inspecting a real store:

`MDIOSettings.save_segy_file_header` **defaults to `0` — off**. A default
`segy_to_mdio` call produces a store with **no `segy_file_header` variable at all**. The
3200-byte textual header and the 400-byte binary header are simply not there.

Three consequences, none of them loud:

1. **Plane 1 and Plane 2 fail on a default ingest** — not because the data is wrong, but
   because it does not exist.
2. **G3 is unreachable.** `mdio_to_segy` raises `MDIOMissingVariableError` without that
   variable, so a default store **cannot be exported back to SEG-Y at all**.
3. Nothing warns. The ingest succeeds, the store looks complete, and the arrays a
   consumer cares about are all present.

This is precisely the failure §0.1 describes: *"None of these failures are loud. They
surface years later…"* — and it is the **default behaviour of the tool SDIP is built on.**
It is also a concrete answer to *why the project exists*, which is worth stating plainly
because the question gets asked.

**Note against Appendix A.1.** That appendix lists `segy_file_header` among the arrays
produced. Reproducing the article with a default `segy_to_mdio` on the pinned versions
produces **no such array**. Either A.1 was run with the setting enabled and did not
record that, or upstream's default changed between the measurement and the pin. Recorded
here as a discrepancy rather than resolved: the appendix is frozen (§12.4), and this
entry is the correction (**SP10**).

**Decision.** SDIP enables persistence explicitly, in **STRICT** mode, scoped to the
call. See D-0020 and D-0021.

---

## D-0020 — 2026-08-22 — `save_segy_file_header` mode 2 is barred by §4.2

**Decision.** SDIP sets `MDIO__IMPORT__SAVE_SEGY_FILE_HEADER=1` (**STRICT**) and
**never** `2` (LENIENT).

**Measured.** Mode 2 runs `mdio.segy.text_header.sanitize_text_header`, whose own
docstring says it *"replaces unsafe characters with spaces and pads/truncates each row to
80 chars"*, always returning exactly 40 rows.

§4.2 is explicit and admits no reading around it:

> If bytes cannot be decoded, the **raw 3200 bytes are preserved** and the decode failure
> is recorded on the certificate. **Decode failure is not an ingestion failure; silent
> substitution is.**

Mode 2 *is* silent substitution. A non-conforming EBCDIC header — exactly the legacy
vintage SDIP exists to rescue — would be rewritten, the store would validate, and the
original bytes would be gone.

**On setting an environment variable at all.** §9.1 bars `MDIO_IGNORE_CHECKS` and
`MDIO__IMPORT__RAW_HEADERS`. `MDIO__IMPORT__SAVE_SEGY_FILE_HEADER` is not on that list,
and the distinction is the **direction of travel**: a barred variable weakens a check or
depends on a deprecated path, while this one causes **more of the source to be
preserved**. It is the opposite of the thing §9.1 forbids. It is set through a context
manager that restores the prior value, so SDIP does not leave the process configured
differently from how it found it.

**What overturns it.** Mode 1 raises on a malformed text header, which is *also* not
what §4.2 asks for — §4.2 wants the raw bytes kept and the failure recorded, not the
ingest refused. SDIP satisfies that itself (D-0021); the mode choice only governs
upstream's parsed view. If upstream adds a mode that preserves without rewriting, revisit.

---

## D-0021 — 2026-08-22 — SDIP captures the raw file headers itself

**Decision.** SDIP reads the first 3600 bytes of the source directly and stores them in
the output under its own attribute namespace: `sdipRawTextHeader`, `sdipRawBinaryHeader`,
and a sha256 for each. **These bytes are authoritative for Planes 1 and 2.**

**Why it is necessary, not merely tidy.** §4.3 requires the binary header preserved as a
parsed mapping **and as raw bytes**, with *"raw bytes authoritative on conflict"*.
Measured: upstream writes `rawBinaryHeader` **only when `settings.raw_headers` is set** —
and that is `MDIO__IMPORT__RAW_HEADERS`, **barred by §9.1**.

So §4.3 is unreachable through MDIO without violating the forbid list. The resolution is
the same shape as §3.2's: **reach the goal through a legitimate path rather than the
deprecated flag.** The first 3600 bytes of a SEG-Y are the textual header followed by the
binary header, at fixed offsets, in every revision — reading them needs no spec, no
parser, no setting, and no barred variable. It also allocates nothing proportional to
file size, which §11.4 requires.

The result satisfies §4.3 completely: upstream's parsed mapping and SDIP's raw bytes both
exist in the store, in separate namespaces, with the authoritative one unambiguous.

Written with stock `zarr`, not MDIO, because a consumer must be able to read them with
MDIO uninstalled (§10.3, gate **G4**).

---

## D-0022 — 2026-08-22 — `once` is not `ignore`: the SP6 ledger classifies by action

**Decision.** `SuppressionRecord` carries a `kind`: **`suppression`** (`ignore` —
information destroyed) or **`deduplication`** (`once`, `module`, `default` — first
occurrence still shown). Only `ignore` counts toward `undeclared_suppressions`.

**Why it changed.** The first real ingest flagged **two UNDECLARED suppressions**, which
is the change-detector working. Investigating them found neither was a suppression:

| Site | Action | What it is |
|---|---|---|
| `xarray/conventions.py:371` | `once` | xarray deduplicating its own `decode_timedelta` FutureWarning |
| `numcodecs/checksum32.py:18` | `once` | numcodecs deduplicating its own crc32c deprecation, at **module import**, at module scope |

Both mutate global warning state and both leak, so both are worth recording. Neither
hides anything: a `once` filter shows the first occurrence.

**Flattening them into "suppression" would have cried wolf, and a ledger that cries wolf
gets ignored exactly when it matters.** SP6's concern is a *hidden liability*; a
deduplicated warning is not hidden. All four filters are now declared, and the ledger
reports `suppression_count`, `undeclared_suppression_count`, and the weaker
`undeclared_filter_count` separately.

**Bonus finding:** numcodecs installs its filter at **import time, at module scope** —
it is not scoped to any call at all, so merely importing the package changes the
process's warning behaviour.

---

## D-0023 — 2026-08-22 — The default SEG-Y textual header is non-deterministic

**Measured.** `SegyFactory.create_textual_header()` with no argument calls
`get_default_text()`, which writes
`datetime.now(tz=UTC).isoformat(timespec="seconds")` into line 6.

Two fixture builds therefore differ **whenever they straddle a second boundary**. That is
**flaky, not reliably broken**, which is the worse failure: it passes locally, fails in
CI, and the difference is 3200 bytes into a binary file where nobody looks. It would make
§6.6's *"generated deterministically by committed code"* false and **G6**'s
identical-bytes requirement unmeasurable.

**Second, nastier finding in the same call:** `create_textual_header` **does not pad or
validate**. `create_textual_header("C 1 HELLO")` returns **9 bytes**, not 3200 — every
subsequent offset in the file is then wrong and the SEG-Y is silently malformed. The
docstring says the length *"should match"* the spec and leaves it entirely to the caller.

**Decision.** Every SDIP fixture passes explicit text built to exactly 40 rows × 80
columns, and the generator **asserts the encoded header is 3200 bytes** before writing.
A test builds two fixtures across a deliberate 1.2-second sleep and asserts byte
identity — which is what would have caught this.

---

## D-0024 — 2026-08-22 — F2 built: ingest, Planes 1 and 2, certificate v0

**Decision.** `sdip ingest` is live. Gates **G2a** and **G2b** enforce. Certificate v0
issues.

**An F2 certificate cannot say `EQUIVALENT`, and that is enforced in code.**
`verdict_for` returns `EQUIVALENT` only when all five planes are `PASS` **and G7 is
`PASS`**. Planes 3–5 and gates G3–G7 do not exist at F2, so they are `NOT_RUN`, and the
best reachable verdict is `PROVISIONAL`. G7 is in the condition because *a store whose
planes pass against an engine that has never been shown capable of failing has not been
checked — it has been agreed with* (**SP11**).

**Order of operations in `ingest` is load-bearing** and is asserted by tests: refuse on
the spawn hazard → refuse if a barred variable is set → validate the source **before
allocating** → hash → build spec and **run G1 before a single trace is read** → capture
raw headers → convert → attach authoritative headers → **re-hash the source** to detect
read-path corruption.

**Planes compare the store on disk against the source file on disk.** Never against
something remembered from the ingest that produced it: a checker validating its own
memory is a tautology that would pass on a store that was never written.

**Negative controls, in the same commit:** one flipped textual byte fails **G2a and only
G2a**, reporting the exact offset; one flipped binary byte fails **G2b and only G2b**; a
truncated textual header raises; a too-short file, a directory, and a header-only file
are each refused with a typed error before anything is allocated.

**spawn-guard is a real subprocess test.** A guarded script ingests successfully; an
unguarded one must not silently produce a store. The negative control asserts the
*outcome* rather than the exact `BrokenProcessPool` type, so it survives a pin bump — and
it fails loudly with an instruction not to delete it if upstream ever stops using a spawn
context.

**Status: 2 of 7 gates enforcing** (G1, G2 — partially: G2a and G2b of five sub-gates).
**G7 is still not built** (`OPEN_DEBTS.md` D11).

---

## D-0025 — 2026-08-22 — Restricted local-only verification data; `local/` joins the firewall

**Decision.** SDIP may be verified end to end against real survey data that is
**licensed for local use only and must never be pushed**. The data is *used*, never
*entered*: it lives outside the repository, everything derived from it is written to
`local/`, and **`local/` joins the publication firewall** alongside `docs/`.

**Why `local/` and not just trusting people to be careful.** The data itself is easy to
keep out — it is gigabytes and lives elsewhere. What is easy to commit by accident is
what comes *out* of it, and the most dangerous item is the one this project is built to
produce: **a certificate carries a source path and a source hash**, so a certificate
issued against restricted data is itself restricted. `certificates/` is otherwise a
directory that is *meant* to be committed (§4.7, `EQUIVALENCE_LEDGER.md`), which makes
it exactly the wrong place to rely on judgement. A separate firewalled directory removes
the judgement call.

All four layers were changed **in the same commit**, which the contract test enforces:
`.gitignore`, `.githooks/pre-commit`, `NEVER_PUBLISH` in `sdip doctor`, and both steps
of the CI `firewall` job. A path guarded by three layers and missed by the fourth is
guarded by three, and the weakest layer is the real policy.

**Three rules that keep this from being a loophole**, stated publicly in
`tests/fixtures/PROVENANCE.md` so a contributor sees them:

1. Nothing derived is committed, **including certificates**.
2. **CI never depends on it.** Every committed test passes on the synthetic fixtures
   alone — a test that needs data CI cannot fetch is a test that does not run.
3. Results are reported **with their scope**.

**Rule 3 is the one worth spelling out.** A single ingest of one large file is a real
measurement and is worth recording. It is **not probe P3**. P3 requires a
pre-registration with declared memory and wall-clock ceilings merged **before** the run
(**SP9**), a pre-registered random trace sample plus all edge and corner traces, and two
independent runs for G6. Running a big file and calling it a scale result would be
exactly the post-hoc reasoning SP9 exists to prevent, and **D2 stays open** regardless
of how well any such run goes.

**Registered:** one dataset, recorded outside this repository with its BagIt manifest,
its own checksums, and its measured geometry. Public records may cite measurements taken
from it; they must not carry the local path.

**What overturns it.** A dataset whose licence permits redistribution *and* whose owner
permits publication, which would make it an ordinary §6.6 fixture — fetched at test time
by checksum, never vendored.

---

## D-0026 — 2026-08-22 — Engine validated end to end on a real survey

**Measured.** The full chain — ingest, five planes, G3, G4 — run against a **real 3D
poststack survey**, not a synthetic article. Recorded here because **SP8** makes a
measurement worth exactly what its scope statement says, and this one has a scope worth
stating precisely.

| Quantity | Value |
|---|---|
| Source | Real 3D poststack SEG-Y, rev 1, **494,565,408 bytes** |
| Traces | **116,532** — a 249 × 468 grid, fully populated, zero dead traces |
| Samples per trace | 1,001 at 2000 µs |
| Scale vs the banked article | **3,884× the trace count** |

**Result: every implemented gate passed.**

| Gate | Result | N |
|---|---|---|
| G1 | `PASS` | 97 fields, itemsize 240 |
| G2a / G2b | `PASS` | 3,200 / 400 bytes, exhaustive |
| **G2c** | `PASS` | **116,532 traces × 97 fields, exhaustive** |
| **G2d** | `PASS`, exact equality | **116,532 × 1,001 samples** |
| G2e | `PASS` | counts, invertible map, live mask, no duplicates |
| **G3** | **`PASS` — byte-identical** | **494,565,408 bytes** |
| G4 | `PASS`, `mdio` never imported | 9 arrays |
| **Verdict** | **`PROVISIONAL`** | G5, G6, **G7** `NOT_RUN` |

**The provenance chain is the part that makes the rest mean anything.** The source
digest matches the checksum manifest written with the data **six years before this run**;
it matches again after ingestion (no read-path corruption); and the **G3 export matches
it too**. Four identical digests across half a gigabyte.

**A better header-cost number than the specification's own.** The `headers` array
compressed to **2.0 B/trace — 121:1** on the full 240 bytes, **0.06 % of the store**.
§5.4 measured 19.4 B/trace, but on synthetic headers carrying *"a deliberately
pessimistic 12 bytes of incompressible random data"*. Real acquisition headers are far
more compressible: **≈10× cheaper than the spec's own pessimistic figure.** The cost
argument against full header preservation is not merely closed — on this data it is not
a rounding error.

Wall clock 55.1 s end to end; peak RSS 2.84 GB.

### What this is not, stated because it would be easy to overclaim

- **NOT probe P3, and D2 stays open.** No pre-registered memory or wall-clock ceiling, no
  pre-registered trace sample, no second run. **SP9**: a threshold chosen after seeing
  the result is not a threshold. Running a large file is not measuring scale behaviour.
- **NOT a G6 result.** Determinism needs two runs; this was one.
- **NOT a G7 result.** Nothing was corrupted, so nothing here shows any gate is capable
  of failing on this data. **D11 is untouched.**
- **NOT a D5 result.** The grid is perfectly regular with zero dead traces and no
  duplicates — none of the conditions P5 probes are present.
- **One file, one vintage, one geometry, one revision.**

The verdict was `PROVISIONAL` with every implemented gate green, which is the engine
behaving correctly: **G7 has never run.**

**The data is not in this repository and never will be.** It is licensed for local use
only, everything derived from it went to the firewalled `local/`, and the register naming
it is kept outside the repository (**D-0025**).

---

## D-0027 — 2026-08-22 — G7 is an executable gate, not a test suite

**Decision.** **G7 is a gate the engine runs**, in `src/sdip/equivalence/nonvacuity.py`.
It corrupts *copies* of the store it just certified, re-runs its own checkers, and puts
the outcome on the certificate for **that store**. `tests/negative/` holds the permanent
controls that exercise the machinery; it is not the machinery.

**Resolving the F3/F4 ambiguity, recorded because it was real.** Two readings were in
play and both were right about different things:

1. `CLAUDE.md` §4.2/§5 — *a gate ships its negative control in the same commit*. Under
   this, G7 is not a phase; it is a property of every engine commit.
2. Public spec §13 — F4 is a phase, and *"F4 is not optional and is not last"*.

Reading 1 is a **review rule**, and it was followed throughout F3. Reading 2 is about
something else: **§4.7's certificate carries `gates: {G7: PASS|FAIL|NOT_RUN}`**, and a
certificate cannot report the result of a test suite that ran on somebody's laptop last
Tuesday. A consumer reading a certificate is entitled to know that *this store* was
audited, not that the engine passed its tests on a fixture once.

So both hold: controls ship per commit **and** the audit is a gate that runs per store.

**"And only that gate" is enforced as a declared set.** Each control declares the exact
set of gates it must fail, and G7 asserts the observed set **equals** it. That is
strictly stronger than "at least its own gate": one assertion catches a **narrow**
checker that misses the corruption *and* an **over-broad** one that fires on someone
else's, which "at least" would not.

Two controls declare multi-gate sets because that is what they genuinely do:
`transposed_traces` moves headers **and** samples (G2c + G2d); `dropped_trace` changes
headers, samples **and** the mask (G2c + G2d + G2e). Demanding one gate for either would
assert something false and would be "fixed" by weakening a checker — the opposite of
what G7 is for.

**The baseline is checked first.** If the clean store does not pass every gate, *"the
corrupted one failed"* proves nothing, so G7 refuses before running a single control.

**A raise counts as a detection.** A corruption that makes a checker throw *has* been
detected by it. Treating a raise as a pass would be the exact vacuity G7 exists to catch.

**G7 has its own negative control** (`tests/negative/`): Plane 4 is monkeypatched blind
and G7 must **FAIL**, noticing that the flipped-sample control no longer fails G2d. SP11
applies to G7 as much as to anything else — an audit never shown to fail is not an audit.

---

## D-0028 — 2026-08-22 — G7 found a real defect on its first run

**What it found.** Truncating the **textual** header also failed **G2b**. §7 G7's killer
is explicit: *"Kills it: any corruption that passes, or one that fails the wrong gate."*
This was the second.

**Cause.** Planes 1 and 2 shared `read_raw_file_headers_from_store`, which built a
`RawFileHeaders` and validated **both** halves in `__post_init__`. A short textual header
therefore raised while Plane 2 was reading *its* half — so Plane 2 failed on Plane 1's
corruption.

**Why it matters more than it looks.** Planes 1 and 2 are **separable claims** (§4.1),
and a shared validating reader silently made them inseparable. Nothing else would have
caught it: every plane still passed on a clean store, every plane still failed on its own
corruption, and the F2 test suite asserted the *raise* — it encoded the defect as the
expected behaviour. **Only a check that asks "did anything else fail?" could find it.**

**Fix.** Each plane reads only its own attribute, unvalidated for length:
`read_raw_textual_from_store` and `read_raw_binary_from_store`. A truncation is now what
it always should have been — **a finding Plane 1 reports with a length difference**, not
an exception for Plane 2 to trip over. This also brings Plane 1 closer to §4.2, which
wants a decode failure *recorded*, not raised.

**The F2 test that asserted the old behaviour was rewritten rather than deleted**, so the
change is visible in the diff, and the corrected expectation carries a note saying why.

**This is the entire argument for G7 in one incident.** The engine was green: five planes
passing on synthetic data, five planes passing on 116,532 real traces, a byte-identical
round trip. It still had a defect that made two of its five planes non-independent, and
the first run of the gate on the gates found it in seconds.

---

## D-0029 — 2026-08-22 — F4 built; `EQUIVALENT` is now reachable

**Decision.** `sdip certify` runs G7 against the store it is certifying, and
`verdict_for` can therefore return **`EQUIVALENT`** for the first time.

**Measured on the 30-trace article:** baseline clean, then **8 corruptions, each failing
exactly the gates it declares and no others**, plus G3's own control (a flipped export
byte is detected and the file restored). **G7 `PASS`.**

**What this changes about the project's central claim.** Until today every certificate
said `PROVISIONAL` and the reason field said so: *until G7 passes, every certificate the
engine issues is unvalidated*. That is no longer the standing state — for a store whose
G7 audit passes, the engine has been shown capable of failing, on that store, for every
gate it claims.

**What it does not change.** G5 and G6 still do not exist and are `NOT_RUN`. **D2 (scale)
and D7 (cloud) are untouched.** G7 passing on a 30-trace article and on one real survey
is not G7 passing at survey scale under a declared memory ceiling — that is **P3**, and
it still requires a pre-registration merged before the run (**SP9**).

**`OPEN_DEBTS.md` D11 closes.** It said *"a gate a corrupted store passes is not a gate;
no negative control exists yet, because no gate exists yet."* Both halves are now false.
