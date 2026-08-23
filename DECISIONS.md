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

**Negative controls ship in the same commit** (the operating contract §4.2): the raw rev 0 and rev 1
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

1. the operating contract §4.2/§5 — *a gate ships its negative control in the same commit*. Under
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

---

## D-0030 — 2026-08-22 — `EQUIVALENT` issued on a real survey; D18 measured

**Measured.** The full certify chain, **including G7**, run against the real 3D poststack
survey of D-0026 — 116,532 traces, 494,565,408 bytes.

**Verdict: `EQUIVALENT`.** G1, G2 (all five planes), G3, G4 and **G7** all `PASS`;
G5 and G6 `NOT_RUN`.

**Every G7 control behaved on real data exactly as on the 30-trace article**, including
the two multi-gate ones. **One flipped bit in one sample — out of 116,648,532 samples —
failed G2d and nothing else.**

That last sentence is the project's claim, demonstrated rather than asserted: the engine
detects a single-bit defect in a half-gigabyte file, attributes it to exactly one plane,
and has been shown on that same store that every other gate is capable of failing too.

### D18 measured — and the number is bad

| Quantity | Value |
|---|---|
| Store | 362 MB |
| Controls | 8 |
| **Bytes copied by G7** | **2.83 GB** |
| **G7 wall clock** | **370.4 s — 46.3 s per control** |
| Ingest | 8.8 s · G3 export 1.3 s |
| **Total chain** | **423.4 s — G7 is 87 %** |

**G7 costs eight times the entire rest of the pipeline.** At 362 MB that is tolerable. At
a 20 GB survey it is ~160 GB of copying and hours of wall clock — and that is the point
at which an operator switches it off. **A gate that gets switched off is worse than one
that was never written** (**SP11**), so this is a correctness risk wearing a performance
costume, and D18 stays open with a measured number attached.

Candidate fixes are recorded on the debt; the cheapest correct one is to copy only the
array a control actually touches — most touch one — which would cut 2.83 GB to a few
hundred MB without weakening a single assertion.

### What this does **not** establish

- **Not probe P3, and D2 stays open.** No pre-registered memory or wall-clock ceiling, no
  pre-registered trace sample, one run. **SP9**: running a large file is not measuring
  scale behaviour, and a threshold chosen after seeing the result is not a threshold.
- **Not G6.** Determinism needs two runs.
- **One file, one vintage, one geometry, one revision**, with a perfectly regular grid and
  zero dead traces — **D5 is untouched**.

**The data is not in this repository and never will be** (D-0025). Everything derived —
store, export, report, and the certificate, which carries a source path and a source hash
— went to the firewalled `local/`.

---

## D-0031 — 2026-08-22 — Definition of done: full end-to-end validation of **both** outputs

**Decision.** Recorded now, **before** it is needed. The Principal's acceptance criterion
for the finished project is:

> **Both outputs — the MDIO store and the exported SEG-Y — must have passed full
> end-to-end validation and certification.**

This is a **release gate for v1.0.0 (F8)**, not a requirement on the current phase. It is
written down at F4 for the same reason a probe is pre-registered (**SP9**): a criterion
agreed in advance cannot be quietly softened once it is inconvenient, and *"we thought it
meant something less"* is not available to anyone later.

### The criterion, made concrete

Three arrows, each verified independently — a chain is only as good as its least-checked link:

```
  SEG-Y source  ──①──▶  MDIO store  ──②──▶  SEG-Y export  ──③──▶  MDIO store′
```

| # | Arrow | Established by | State at F4 |
|---|---|---|---|
| ① | source → store | G1, G2a–G2e, G4, **G6**, G7 | G6 missing |
| ② | store → export | G3 whole-file SHA-256 | **met** |
| ③ | export → store′ | **round-trip closure**, not yet built | **missing** |

**Arrow ③ is the one nobody asks for and the one that closes the loop.** G3 proves the
exported file is byte-identical to the source, which is the strongest possible claim
*when it holds*. But `ROUNDTRIP-SCOPED` exists precisely for sources where byte-identity
is impossible (§7 G3), and for those the export is currently trusted on a hash that was
never going to match. Re-ingesting the export and checking the resulting store against it
is what makes the exported SEG-Y a **validated artifact in its own right** rather than a
by-product.

### Release checklist — every line must be `PASS`, none may be `NOT_RUN`

| # | Requirement | State |
|---|---|---|
| 1 | All five planes `PASS` on the source → store arrow | **met** |
| 2 | **G3** byte-identical, or `ROUNDTRIP-SCOPED` with a written justification naming the non-conformance | **met** |
| 3 | **G4** portability, `mdio` never imported | **met** |
| 4 | **G7** non-vacuity, every control failing exactly its declared gates | **met** |
| 5 | **G6** determinism — two independent ingests, identical array bytes | **in progress** |
| 6 | **Round-trip closure** — the export re-ingests to an equivalent store | **not built** |
| 7 | **G5** scale, inside a **pre-registered** memory ceiling | **not built — needs P3** |
| 8 | Certificate verdict `EQUIVALENT` with **no gate `NOT_RUN`** | blocked by 5–7 |
| 9 | Probes P2, P4, P5, P6, P7, P8 discharged or explicitly scoped | **not run** |
| 10 | **D18 closed** — G7 affordable at survey scale, or it gets switched off | **open, measured** |

**Item 8 is the machine-checkable form of the whole criterion**, and it is stricter than
today's `EQUIVALENT`. The current verdict rule requires all five planes plus G7; it
tolerates G5 and G6 being `NOT_RUN`. At release, **`NOT_RUN` anywhere is a failure** — an
unrun gate is not a passing one, and a certificate with holes in it is exactly the
untrusted artifact §0 describes.

**That change is deliberately not made today.** Tightening the verdict rule now would
make every current certificate `PROVISIONAL` and would say nothing true that the `gates`
block does not already say. It is scheduled against F8 and recorded here so it cannot be
forgotten.

### What this does not do

It does not authorise building items 5–9 now. **F5 is the next phase** (probes P2, P5,
P6), each needing its own pre-registration merged before its run.

---

## D-0032 — 2026-08-22 — Pre-registrations move to a public `prereg/`; SP9 was unsatisfiable

**Decision.** Probe pre-registrations move from `docs/prereg/` to **`prereg/` at the
repository root**, tracked and pushed.

**The conflict, which was real and silent.** **SP9** requires that *"verdict criteria,
thresholds and N are committed and pushed **before** the run."* **D-0010** put `docs/` in
the publication firewall — never committed, never pushed. Every pre-registration was
therefore in a directory where SP9's requirement **could not be satisfied at all.**

Nothing failed. The files existed, they were written before their runs, and a reader of
the working copy would see nothing wrong. **The mechanism that makes a pre-registration
mean anything was simply absent**, and would have stayed absent until the first probe
result was published and somebody asked to see the commit that preceded it.

**A pre-registration is not documentation.** Its entire value is being **publicly
timestamped before the result exists** — git's commit history *is* the mechanism, not a
convenience. A pre-registration that cannot be pushed is a write-up with good intentions.
Same reasoning as the certificate schema in **D-0015**: an artifact whose purpose is to
be verifiable by a third party does not belong in a directory that third parties never
receive.

`docs/` keeps the specification, the internal companion, the runbooks, and the local-only
data register — all genuinely documentation, all genuinely internal.

**Two tests now enforce it:** every probe P1–P8 has a file in `prereg/`, and every one of
those files is **tracked in git**. The second is the one that matters — a pre-registration
absent from git is not a pre-registration.

**P3's parameters are filled in this commit, before the run they govern.** Ceilings:
**8.0 GiB peak RSS**, **900 s per file** for the full chain. `06p07ful.sgy` has already
been measured (3.11 GiB, 423 s) and **is excluded from the probe** — its numbers informed
the ceilings, which is how thresholds are set, but it cannot also be judged by them. P3
runs on files never ingested.

**What overturns it.** Nothing short of abandoning SP9.

---

## D-0033 — 2026-08-22 — `git add -A` swept unreviewed work into a public commit

**What happened.** Commit `690b05e` ("Move pre-registrations to a public prereg/") was
staged with `git add -A` while parallel work was writing files. It carried two things its
message does not mention and its author had not reviewed:

- `src/sdip/equivalence/determinism.py` — 497 lines, gate **G6**, mid-flight.
- `_g6check.py` — a throwaway verification script, now in the public history.

**It was pushed.** Nothing secret leaked — the firewall held, and `docs/`, `local/` and
every AI-assistant artifact stayed out, which is what those four layers exist for. But
the firewall is not a review process, and it was never meant to be one.

**Why this is worth an entry rather than a quiet cleanup.** The project's own rule is
that a commit message states **what was measured, under what config, with what N**
(the operating contract §4.4). A commit that silently carries 497 lines of unreviewed gate
implementation is a false record, and the append-only discipline (**SP10**) means the
remedy is a new entry, not a rewrite.

**Verified after the fact**, which is the wrong order and is stated as such:
`determinism.py` passes the tolerance/suppression `ast` audit, references no barred
variable, uses `array_equal`, excludes `zarr.json` from the byte comparison as G6
requires, is ruff- and mypy-clean, and **G6 PASSES** on the synthetic article — 2
independent ingests, 9 arrays, chunk bytes *and* values identical.

That it turned out fine is luck, not process.

**Fixes, both mechanical:**

1. `/_*.py`, `/_*.sh`, `/_*.json` are gitignored — a leading underscore at the repository
   root now means "never mine".
2. **The pre-commit hook refuses them**, which is the layer that *prevents* rather than
   detects. It is the same asymmetry as the publication firewall: `.gitignore` is
   defeated by `git add -f` and by anything already tracked; the hook is not.

**The judgement fix, which no hook can enforce:** do not `git add -A` while work is in
flight. Stage explicitly, or wait.

---

## D-0034 — 2026-08-22 — **P2 FIRED.** `ibm32 → float32` is not exactly invertible

**Result.** Probe P2 ran against the binding pins and **its falsifier fired, hard.** Of
**4,103** IBM words swept exhaustively over the exponent axis with a committed mantissa
axis and both signs, only **1,656 (40.4 %)** round-trip bit-identically. **2,447 fail.**

| Mode | N | What is lost |
|---|---|---|
| `overflow_to_inf` | 920 | **The value** — `16^(code-64)` exceeds float32's ~3.4e38 |
| `underflow_to_zero` | 839 | **The value** — below float32's smallest subnormal |
| `subnormal_precision_loss` | 180 | **Significand bits**, in the decode itself |
| `zero_fraction_canonicalised` | 256 | The spelling, and the sign of zero |
| `unnormalised_renormalised` | 252 | The spelling; the encoder always normalises |

**Zero unexplained failures** — every one is attributed to a named mechanism.
**1,939 lose the value, not merely the spelling**, and no re-encoding can reconstruct
them: the information left the pipeline at decode time.

Bit-identity requires exponent code **33–96** *and* a normalised, non-zero fraction.

**This is the most consequential measurement the project has taken.** **SP1** permits
exactly one transform and requires it *"exactly invertible, verified by round trip"*.
The one transform SDIP permits is **not** exactly invertible, and `ibm32` is the standard
SEG-Y sample format — **the default for every revision the pinned `segy` exposes**.

### What was built in response

`src/sdip/spec/transforms.py`. Two things, deliberately separate:

**1. The exposure is always declared.** Any spec carrying `ibm32` — in headers or as the
sample format — produces a `transforms_declared` entry with
**`invertibility: SCOPED`**, never `VERIFIED`, naming the measured regime. The transform
is not invertible *in general*, so the certificate says so even where it happened to be
invertible on this data.

**2. The block is conditional on G3, and getting that right mattered.** The first
implementation blocked `EQUIVALENT` whenever `ibm32` was present. That is every ingest,
including the ones whose whole file round-trips byte for byte — a rule that fires
identically on data that survived perfectly and data that was destroyed **distinguishes
nothing and would be switched off** (**SP11**).

**G3 byte-identity is the empirical answer.** If `sha256(export) == sha256(source)` over
the whole file, then every `ibm32` word in it re-encoded to the bits it came from. That is
not an argument about exponent ranges; it is a measurement of *this data*, and it is
stronger than any argument. P2's failures live at the extremes; a file that never reaches
them round-trips, and the hash proves it.

So `EQUIVALENT` is blocked exactly when the proof is absent: `ibm32` declared **and** the
round trip not byte-identical. Then the difference may be harmless re-spelling or 1,939
destroyed values, **and nothing in the output distinguishes them.**

**`ROUNDTRIP-SCOPED` is explicitly refused for this case**, and the code says so. §7 G3
wrote that clause for a *non-conforming source*, not for a transform that destroyed
measured values. An operator facing a failed hash has every incentive to reach for it;
scoping this would convert measured data loss into a paperwork exercise, which is the
precise failure §0 exists to prevent.

**D1 changes character:** from *"invertibility unverified"* to **"verified as NOT
invertible outside codes 33–96"**. It stays open and blocking, and the pre-registration's
remaining remedy — storing the raw `uint32` view in parallel — is **not built**.

**A survey-spec override declaring an `ibm32` header field must now be refused at
review.** D-0003 measured zero such fields in every standard, so that is the only route
in — and P2 has failed rather than merely not-yet-cleared.

---

## D-0035 — 2026-08-22 — **P4 did not fire.** A C++ reader read the structured headers

**Result.** **TensorStore 0.1.85** — C++, sharing no code with `zarr-python` — read
**all 97 fields** of the structured `headers` array **byte-identically**, and recovered
the planted rev-1-uncovered tail bytes to match the source. All 7 core-spec arrays read
bit-identically too.

**The falsifier — *"headers unreadable outside Python"* — did not fire.**

**But the most load-bearing observation is the opposite one**, from the same run: the
*same* reader **refused** `segy_file_header`, whose `data_type` is
`fixed_length_utf32`. One reader, one store, one dtype accepted and another rejected —
a same-run demonstration that **extension-dtype support is per-implementation, not a
property of the store.** `struct` has no Zarr v3 specification, so TensorStore's support
is an implementation choice; a reader that declines it is standards-conformant and would
still be right.

**Measured directly, and it matters more than the rejection.** SDIP's authoritative
Plane 1 and Plane 2 bytes are recoverable **with a JSON parser alone** — no zarr, no
Python, nothing — because **D-0021** stored them as base64 *attributes* in `zarr.json`
rather than as array payload. Verified: 3,200 textual bytes and 400 binary bytes read
straight out of the JSON and compared equal to the source, with the declared SHA-256
matching.

That was a correctness decision taken for §4.3's *"raw bytes authoritative"* requirement.
It turns out to also make the file headers **strictly more portable than any array-based
storage could be**, including MDIO's own. Recorded because it was not the reason for the
decision and should not be claimed as foresight.

**Scope:** one implementation, not the two the pre-registration asked for — no JRE and no
Rust toolchain on the runner, and CI has no network beyond the pinned index. **D3 narrows,
it does not close.** N = 30 traces, one revision, one geometry, local filesystem.

**On the pre-approved `uint8` header plane:** the evidence supports adopting it, but not
for the anticipated reason. The falsifier did not fire, so it is not forced. What the run
showed is that portability of `headers` rests on **one implementation's goodwill toward
an unspecified dtype**. A 2-D `uint8` plane replaces goodwill with a guarantee. Adoption
is a §12.1 maintainer decision and is **not taken here**.

---

## D-0036 — 2026-08-22 — **P5 did not fire.** Irregular geometry is handled correctly

**Result.** All four falsifier clauses hold, across ten synthetic fixtures.

| Clause | Verdict | Evidence |
|---|---|---|
| Silent duplicate overwrite | **holds** | Refused at ingest — `GridTraceCountError: 29 != 30`, no store written — **and** surfaced independently by Plane 5, naming both colliding ordinals. **Two defences, neither suppressible.** |
| Padding leaking into Plane 4 | **holds** | Plane 4 compared 27 of 81 cells on `sparse_grid`, 32 of 50 on `ragged_lines`. Padding is `NaN`; G3 byte-identical, so nothing invented reaches the export. |
| Sparsity depending on a suppressed check | **holds** | `MDIO_IGNORE_CHECKS` absent throughout, asserted three times in-test. Ratio 3.0 converts; ratio 12.0 is refused. |
| Mask cannot distinguish a measured zero from padding | **holds** | Measured zeros are live and exactly zero; padding is not live and is `NaN`. |

**Two qualifications belong with that verdict**, neither a falsifier hit: clause 3 holds
*at the ratios measured* — sparse ingest is bounded at ratio 10 and the only route past
it is the barred variable, which is not a route SDIP may take; and clause 4 holds *on the
mask* — the `headers` array pads with zeros rather than `NaN`, so for that array the mask
is the sole discriminator.

**Scope:** 20–80 traces per fixture, one template, poststack 3D, revisions 0 and 1,
sparsity sampled at 1.0 / 1.56 / 3.0 / 12.0 with nothing between 3 and 12, one duplicate
with two colliding ordinals. **Every fixture is synthetic and structurally well-formed —
a hostile or malformed irregular file is not covered** (that is §11.4 and debt D8).

---

## D-0037 — 2026-08-22 — **P6 FIRED.** Only rev 1 works end to end; the scope claim was false

**Result.** G1 passes on **all four** revisions — gap-free construction generalises
exactly as D-0003 said. **Then three of the four fail to ingest**, so G3 is not failed for
them, it is **unreachable**.

| Revision | Fields → gap-free | G1 | Ingest | G3 |
|---|---|---|---|---|
| rev 0 | 71 → 131 | **PASS** | **BLOCKED** | unreachable |
| **rev 1** | 89 → 97 | **PASS** | **PASS** | **byte-identical** |
| rev 2 | 90 → 90 | **PASS** | **BLOCKED** | unreachable |
| rev 2.1 | 90 → 90 | **PASS** | **BLOCKED** | unreachable |

**The good half of a bad result:** the ingest path did **not** disagree with the
spec-construction path, which the pre-registration flagged as the more serious of the two
possible findings. Construction generalises; **construction is not enough.**

### The three blockers, isolated to the smallest cause

**rev 0 — four absent field declarations.** `cdp_x`, `cdp_y`, `inline` and `crossline`
enter the standard at rev 1. The gap-free rev 0 spec covers bytes 181–240 with `uint8`
fillers — **correctly, under SP5** — and the template cannot find the four fields it
indexes on. The *bytes are in the file at the canonical positions*; only the declaration
is missing. Declaring them keeps the spec gap-free (G1 still PASS, 119 fields) and the
whole leg then passes, byte-identical. **That is exactly what a §6.4 survey override is,
and §6.4 is not built.** rev 0 is one specified-but-unimplemented mechanism away from
working.

**rev 0 — the sample format is unsuppliable, which is worse.** `SegyFile._update_spec()`
reads `data_sample_format` from bytes 3225–3226 **unconditionally, for every revision
including rev 0**. A genuine 1975-vintage rev 0 file carries zero there — the standard
never mandated it — and the file then does not open at all:
`ValueError: 0 is not a valid DataSampleFormatCode`. **SDIP exposes no surface through
which an operator could supply the format.** The probe's fixture reads only because
SDIP's own generator stamped the code into it. An operator-supplied sample format is a
stated requirement of P6 and **there is nowhere to state it.**

**rev 2 / 2.1 — two upstream defects, the second hidden behind the first.**
`trace_header_name` at byte 233 is an 8-character string, the only non-integer field in
the 240 bytes, and `multidimio` 1.2.1 has no `ScalarType` for it:
`Unsupported numpy dtype 'bytes64'`. **The two revisions that need no fillers — gap-free
as shipped — are the two that cannot be ingested.** Replace that one field and the ingest
runs and all five planes pass; the *export* then fails anyway, because
`mdio_spec_to_segy` injects the rev 1 `segy_revision` field into any spec lacking it, and
rev 2 carries `segy_revision_major`/`minor` over the same bytes 301–302.

**Both are raised as issues, not routed around** (§3.3 bars monkeypatching; no fork is
authorised).

### The public claim was false and is corrected

Specification §1.2 lists *"SEG-Y (rev 0, 1, 2, 2.1) → MDIO v1 / Zarr v3 ingestion"* as
in scope, and `README.md` repeated it. **Measured: only rev 1 completes.** That is
precisely the kind of unverified assertion this project exists to make impossible, and
leaving it up while knowing better would have been worse than never having probed.

The README now states measured revision support. **D6 narrows from "untested" to "rev 1
only, with three named blockers."**

---

## D-0038 — 2026-08-22 — G7 copies only what a control touches; closes D18

**Decision.** Each `Corruption` declares a `touches` set — the store subpaths it modifies.
G7 materialises a working copy by **real-copying those paths and hard-linking the rest**.

**Why not hard-link everything.** A hard link is the same inode: writing through one
would corrupt the original store — the very store being certified — silently. So the
modified paths are always real copies, and that asymmetry is the whole design.

**The safety check is not optional.** The original store's chunk files are hashed before
and after the audit; a mismatch sets `original_store_intact: False` and **fails the
gate**. A gate that could corrupt what it audits would be worse than no gate.

**Measured:** the audit still passes with all 8 controls failing exactly their declared
gates, and the original store is byte-for-byte unchanged.

**Why this was a correctness matter, not performance.** D18 measured G7 at **87 % of the
whole pipeline** — 370 s and 2.83 GB copied for a 362 MB store. At a 20 GB survey that is
~160 GB and hours, which is the point where an operator switches the gate off. **A gate
that gets switched off is worse than one that was never written** (**SP11**).

---

## D-0039 — 2026-08-22 — **P7 fired**, and the defect was ours: the planes hard-coded the grid

**Result.** Probe P7's clause 1 fired on **all seven** prestack geometries — not as a
measured mismatch, but as an **inability to evaluate**. Planes 1 and 2 passed everywhere;
Planes 3, 4 and 5 returned **no verdict at all**, dying with `KeyError: 'inline'`.

**The cause was SDIP's, not the data's and not upstream's.** All three planes called
`build_trace_map` with a hard-coded `{"inline": ..., "crossline": ...}` — true of
poststack, false of every prestack geometry. **`NOT_RUN` is not a pass**, and a checker
that cannot run on a geometry silently declines to check it. The Equivalence Contract was
not established for prestack at all, and nothing said so.

**Fix.** The planes now read `dimension_names` from the store's own **Zarr v3 metadata**.
That is core-spec, so it needs no MDIO and does not weaken G4 — and it means the planes
evaluate whatever grid the store actually has rather than the grid they assumed.

**Measured before and after, on the same seven geometries:**

| Geometry | Before | After |
|---|---|---|
| `streamer_shot_3d` | 3/4/5 `RAISED` | **all five PASS** |
| `streamer_shot_2d` | 3/4/5 `RAISED` | **all five PASS** |
| `cdp_offset_3d` | 3/4/5 raised `ValueError`/`IndexError` | **all five PASS** |
| `cdp_offset_2d` | 3/4/5 `RAISED` | **all five PASS** |
| `streamer_shot_3d_wrapped` | 3/4/5 `RAISED` | 3/4/5 **FAIL** — a real mismatch, now visible |
| `streamer_field_3d` | 3/4/5 `RAISED` | 3/4/5 `RAISED` — computed dimension |
| `obn_receiver_3d` | 3/4/5 `RAISED` | 3/4/5 `RAISED` — computed dimension |

**From 0 of 7 evaluable to 4 of 7 fully passing**, and one of the remainder now
**fails visibly** instead of failing to run — which is the more valuable half of the
change. `AutoChannelWrap` reorders traces, and a reordering that the map cannot invert
is exactly what Plane 5 exists to surface.

**The P7 test file had encoded the defect as expected behaviour**, asserting `RAISED`.
That is the same trap as D-0028: a suite entirely green while pinning a bug in place. The
expectations were corrected rather than deleted, so the change is visible in the diff,
and the table above is carried in the file with both readings.

### Two further P7 findings, recorded as debts rather than fixed here

**F1 — `sdip ingest` cannot ingest prestack at all, and the blocker is a name.** Seven
geometries, seven refusals: every prestack template binds trace-header fields the rev 1
standard does not name — `cable`, `channel`, `gun`, `sail_line`, `receiver`, `shot_line`,
`offset`, `cdp`. **For two of them the blocker is *only* a name:** rev 1 byte 37 is
`source_to_receiver_distance`, which **is** offset; byte 21 is `ensemble_num`, which
**is** the CDP. Same bytes, same width, same meaning — and `ingest()` has no parameter
that lets a caller say so. That parameter is §6.4's survey override (debt **D21**).

**F2 — three geometries need a grid override `ingest()` does not forward.**
`segy_to_mdio` accepts `grid_overrides`; SDIP does not pass one. For
`StreamerFieldRecords3D` and `ObnReceiverGathers3D` it is not optional — their
`shot_index` dimension is *calculated*. So a declaration parameter alone fixes four of
seven and leaves three unreachable.

**Leg 2 is what makes these findings actionable:** with the names declared and an
override supplied, the pinned upstream converted **all seven, with G3 byte-identical on
every one**. The format is not the obstacle. SDIP is.

**The latency half of P7 was not run**, and deliberately: no candidate chunk shapes, no
declared target, no authorised compute for a cold-cache benchmark. Under **SP9** a
threshold invented after seeing a chunk shape is not a threshold. A test now reads the
pre-registration and **fails if the parameter table is ever back-filled**.

---

## D-0040 — 2026-08-22 — The coordinate scalar was an undeclared transform. SP1(a) fixed

**Found by probe P5.** `mdio/segy/scalar.py` applies the coordinate scalar to the derived
`cdp_x` and `cdp_y` arrays — multiplying on a positive scalar, dividing on a negative one
— and `transforms_declared[]` named **only** the sample-format decode.

**SP1(a) requires every transform declared.** This one was not, on any certificate the
project has ever issued.

**No data was lost and no plane was wrong.** The raw 240-byte trace header is untouched,
so Plane 3 and G3 are unaffected and the round trip stays byte-identical. What was wrong
is the **declaration**: a consumer reading `cdp_x` gets scaled coordinates and nothing
said so. That is precisely the class of silent, undisclosed change §0.1 lists.

**Fixed.** `detect_coordinate_scalar` reads the scalar and the certificate declares the
transform with its operation, the arrays affected, and the probe that found it. An
identity scalar (0 or 1) is correctly *not* declared — it transforms nothing.

**The uniformity check is the sharper half, and it is new.** Upstream reads the scalar
from **trace 0 only** and applies it to every trace. A survey whose scalar varies between
traces — legal SEG-Y — would have one trace's scalar applied to all of them, which is a
**fabrication under SP12**, not merely an undeclared transform. SDIP now checks *every*
trace and records `uniform_across_traces` plus the distinct values found; a non-uniform
file downgrades the declaration from `VERIFIED` to `SCOPED`.

**Measured:** scalar `+100` declares `multiply`, `-100` declares `divide`, both
`VERIFIED` and uniform across 20 traces, both with G3 still byte-identical.

**Recorded, not fixed:** upstream reading trace 0 only is an upstream behaviour. SDIP
cannot change it, but it can now *tell you* when trusting it would be wrong.

---

## D-0041 — 2026-08-22 — **Consolidated status snapshot.** Where the project actually is

A dated, append-only snapshot, written because the record had grown to 40 decisions and
43 debts across seven phases and **no single entry said where the project stood**. This
one does. It supersedes nothing; it summarises.

### Phases (spec §13)

| Phase | Deliverable | State |
|---|---|---|
| **F0** | Repo skeleton, public files, `NOTICE`, `sdip doctor` | **complete** |
| **F1** | Gap-free spec generator + G1 + unit tests | **complete** |
| **F2** | Ingest orchestration, certificate v0, provenance | **complete** |
| **F3** | Equivalence Engine — five planes, G2–G4 | **complete** |
| **F4** | G7 non-vacuity suite | **complete** |
| **F5** | Probes P2, P5, P6 | **run — P2 and P6 fired** |
| **F6** | Scale and cloud: P3, P8 | **partial** — P3 in flight, **P8 NOT RUN** |
| **F7** | Prestack P7; portability P4 | **partial** — both run, both incomplete |
| **F8** | v1.0.0 public release | **not started** |

### Gates: **6 of 7 enforcing**

| Gate | State | Evidence |
|---|---|---|
| G1 | **enforcing** | Coverage 1–240, itemsize 240, no overlaps, no void gaps. All four revisions. |
| G2 (a–e) | **enforcing** | Five planes, exhaustive. 116,532 real traces × 97 fields. |
| G3 | **enforcing** | Whole-file SHA-256. Byte-identical on 494,565,408 bytes. |
| G4 | **enforcing** | Stock `zarr` + `xarray`, `mdio` never imported, asserted in a clean subprocess. |
| G5 | **pending P3** | The only gate that judges a *run* rather than an artifact. |
| G6 | **enforcing** | Two independent ingests; chunk bytes **and** array values. |
| G7 | **enforcing** | 8 corruptions, each failing exactly its declared gate set. |

### Probes

| Probe | Verdict | What it cost |
|---|---|---|
| **P1** | `PASSED` (banked) | — |
| **P2** | **FIRED** | `ibm32` is **not** exactly invertible. 1,939 of 4,103 words lose the **value**. SP1's only permitted transform does not satisfy SP1. |
| **P3** | **in flight** | 7 of 11 files, **zero breaches**, max 467 s of 900, max 2.85 GiB of 8.0. |
| **P4** | did **not** fire | A C++ reader read all 97 structured header fields byte-identically. One implementation ran, not the two asked for. |
| **P5** | did **not** fire | All four clauses hold. Duplicates refused **and** surfaced. Four of ten conditions do not convert. |
| **P6** | **FIRED (3 of 4)** | **Only rev 1 works end to end.** The §1.2 scope claim was false and is corrected. |
| **P7** | **FIRED (clause 1)** | The planes hard-coded the grid. Fixed: prestack 0/7 → 4/7. Latency half **not run**. |
| **P8** | **NOT RUN** | No credentials. A mock was **deliberately refused** — it would answer a different question. |

### Against the acceptance criterion (D-0031)

`release_readiness` reports **NOT READY**. Blocking, concretely:

1. **G5 `NOT_RUN`** — clears when P3 completes.
2. **P8 never ran.** Cloud is unmeasured and unsupported.
3. **P7's latency half never ran** — no declared target, and inventing one after seeing a
   chunk shape would violate **SP9**.
4. **P4 ran one implementation, not two** — no JRE, no Rust toolchain, no network in CI.
5. **43 open debts**, several substantive.

### The four things that actually block a release

**1. §6.4 survey spec overrides are specified and unbuilt (D21).** The highest-leverage
item on the board. One mechanism unblocks **rev 0** (D6), **four prestack geometries**
(D24), and **little-endian** (D28). Three probes independently arrived at it.

**2. The `ibm32` raw `uint32` parallel view is unbuilt (D1).** P2's own "if it fires"
clause requires it. Without it, an `ibm32` source whose round trip is not byte-identical
has bits that are **not recoverable from the output at all**.

**3. SP6 has two blind spots (D26).** `warnings_raised[]` can be empty while 2,441 samples
are destroyed — worker-process warnings never reach the parent, and `logger.warning` is
not a Python warning. This undermines a §4.7 field a consumer is meant to trust.

**4. `NOT_RUN` must become a failure at release (D20).** Currently `EQUIVALENT` tolerates
unrun gates. Honest today, wrong at release.

### What is genuinely proven

Stated plainly, because the failures above should not obscure it:

- **A byte-identical round trip on 494,565,408 bytes**, with the source digest matching a
  checksum manifest written **six years before the run**.
- **One flipped bit in one sample, out of 116,648,532, fails G2d and nothing else.**
- **G7 passes on real data**: every corruption fails exactly the gates it declares.
- **Full 240-byte header preservation costs 2.0 B/trace — 0.06 % of the store**, roughly
  10× cheaper than §5.4's own pessimistic figure.
- **The engine found four defects in itself**: the shared header reader (D-0028), the
  hard-coded grid (D-0039), the verdict ordering, and the undeclared coordinate scalar
  (D-0040). Three were found by gates, not by tests.

### Honest scope of everything above

**rev 1 only. Poststack only, except four prestack geometries reachable via leg 2.
Local filesystem only. One vintage of one survey plus synthetic fixtures. No cloud.**
Every number in this entry is reproducible from the committed record; none of it is
inferred.

---

## D-0042 — 2026-08-22 — **P3 passed. G5 enforces. All seven gates now pass.**

**Result.** Probe P3 ran against the ceilings committed in `690b05e`, **before any file
it judges was ingested**. **The falsifier did not fire.**

| Quantity | Value |
|---|---|
| Files | **11** — three vintages × four stacks |
| Source bytes | **5,440,219,488** (5.07 GiB) |
| Traces | **1,281,852** |
| Samples compared | **1,283,133,852**, exhaustive, exact equality |
| **G1 · G2a–e · G3 · G4 · G6 · G7** | **PASS on all eleven** |
| G3 byte-identical | **11 of 11** |
| Ceiling breaches | **zero** |

| Ceiling | Declared | Worst observed | Headroom |
|---|---|---|---|
| Peak RSS | 8.0 GiB | **2.87 GiB** | **64 %** |
| Wall clock per file | 900 s | **467 s** | **48 %** |

**G5 therefore PASSES, and with it every gate the specification defines.**

### The substantive observation is the flatness, not the margin

Peak RSS varied by **0.06 GiB** across eleven files of identical size — 2.81 to 2.87.
Memory tracks the **chunk working set**, not the file. That is what §7 G5's *"no
unbounded growth"* means operationally, and it is the part that would extrapolate; the
64 % headroom on its own would not.

### G7 is 84 % of the probe, and D-0038 was half a fix

| Stage | Total | Share |
|---|---|---|
| **G7** | **4,091 s** | **84 %** |
| G6 | 201 s | 4 % |
| Ingest | 104 s | 2 % |

88 corruption audits — 11 files × 8 controls — each re-running five planes. The
selective-copy fix closed the *bytes* problem; the wall clock is inherent, because G7
cannot know a gate fires without running it. **D23** stands, and the fix is parallelism,
not less auditing.

### What this does not establish, stated because the numbers invite overreach

- **One geometry.** All eleven are 249 × 468 fully populated poststack grids with **zero
  dead traces**. Every condition **P5** probes is *absent from this data*.
- **One revision.** rev 1 throughout — **D6** stands, only rev 1 works end to end.
- **One survey.** Three vintages of the same acquisition: same geometry, same vendor,
  same everything except the year.
- **Local filesystem only.** **D7** and **P8** untouched; cloud remains unmeasured.
- **5 GiB is not 20 GiB.** The flat RSS is evidence *for* extrapolating, not a
  measurement of it.

**D2 closes within that scope**, and the scope is the point: a scale result that does not
say what it did not cover is not a scale result.

### Where this leaves the release

**Seven of seven gates pass.** `release_readiness` still reports **NOT READY**, and the
remaining blockers are no longer about the engine:

1. **P8 never ran** — no credentials.
2. **P7's latency half never ran** — no declared target, and inventing one now would
   violate **SP9**.
3. **P4 ran one implementation, not two.**
4. **§6.4 survey overrides unbuilt (D21)**, the **`ibm32` raw view unbuilt (D1)**, and
   **SP6's blind spots (D26)**.

The engine is done and proven at survey scale. What remains is coverage, one unbuilt
mechanism, and two honest gaps.

---

## D-0043 — 2026-08-23 — Four agents died mid-work; the tree was assessed before resuming

**What happened.** Four parallel builds — survey overrides (D21), the `ibm32` raw view
(D1), SP6's blind spots (D26), and P4's second implementation — were all killed
simultaneously by a usage limit, mid-flight. Two had written to the tree.

**Assessed before restarting anything**, because a partial edit from a killed process is
**unreviewed work of unknown completeness**, and inheriting it silently is how a defect
gets built on:

| File | State found | Disposition |
|---|---|---|
| `src/sdip/spec/overrides.py` | 392 lines, untracked, imports cleanly, complete-looking API | **kept** — handed to the new agent as *a draft by someone else, not as trusted* |
| `src/sdip/guard/warn.py` | +72 lines: a sound docstring section, and an `import logging` that nothing used | **kept** — the unused import was the only thing failing `ruff` |
| `local/p4java/` | test store built, no Maven project | kept; `local/` is firewalled and committed nothing |

**The tree was inert, not broken: 525 tests still passed.** That is the fact that made
keeping the partial work defensible rather than reckless — had the suite been red, the
right move would have been to revert both files and start clean.

**Why keep 392 unreviewed lines at all.** Discarding them would have been the *safer*
choice and the wrong one: the module imports, its shape matches the task, and the
alternative is paying twice for the same work. The safeguard is not trusting it — the
resumed agent was told explicitly to *review it, keep what is correct, fix what is not*,
and the acceptance test it must pass is unchanged. **Provenance is a reason for scrutiny,
not for deletion.**

**Related to D-0033**, which recorded `git add -A` sweeping unreviewed work into a public
commit. Same underlying hazard — work of unknown provenance entering the tree — caught
at a different point. The lesson generalises: **know what is in the tree before you build
on it or commit it.**

---

## D-0044 — 2026-08-23 — §6.4 survey spec overrides built. **rev 0 now round-trips.**

**Decision.** `src/sdip/spec/overrides.py` implements §6.4: named, versioned, declarative
overrides mapping a survey to field renames and retypes over the gap-free base, each
carrying cited evidence. Threaded through `build_gap_free_spec`, `ingest()`, and both CLI
commands.

**Measured — this is P6's own diagnosis, now executed:**

| | |
|---|---|
| G1 after override | **PASS**, 119 fields |
| Planes 1–5 | **PASS ×5** |
| G3 | **PASS, byte-identical** |

**rev 0 ingests end to end for the first time.** The blocker was never the format: the
four index bytes were in the file at the canonical positions all along, and rev 0 simply
predates their standardisation, so the gap-free spec covered them as `uint8` fillers —
**correctly, under SP5** — and the template could not find fields it binds by name.

**Three probes arrived at this one mechanism.** P6 (rev 0), P7 (`offset` and `cdp`, whose
bytes already exist under other names), P5 (little-endian, unable to be declared). Three
independent failures, one missing feature.

**Four rules the implementation enforces, each from §6.4 or a probe result:**

1. **Evidence is mandatory and length-checked.** §6.4: *"an override with no cited
   evidence is rejected at review."* Enforced at load, not left to a reviewer's attention.
2. **G1 must still pass.** An override that breaks gap-freeness is refused, and the error
   says so.
3. **`ibm32` in an override is REFUSED, naming P2.** This is the sharp one. Before, an
   `ibm32` override would have been "deferred pending P2". **P2 has now failed**, so it is
   refused outright — a survey override is the *only* route by which `ibm32` can reach a
   trace header (D-0003 measured zero such fields in every standard), and that route is
   now closed.
4. **Byte content never changes.** Names and types over the same bytes; G2c re-verifies
   it on every ingest.

**Three overrides ship**, each with real evidence prose citing byte ranges and revisions:
`segy-rev0-poststack3d`, `rev1-offset-alias`, `rev1-cdp-alias`.

---

## D-0045 — 2026-08-23 — The raw `uint32` sample view is stored. **D1's remedy is built.**

**Decision.** For a source whose sample format is `ibm32`, SDIP writes
`amplitude_raw_ibm32` — the **undecoded big-endian 4-byte sample words, read from the
source file by raw offset**, shaped like `amplitude`, written with stock `zarr`.

**This is probe P2's own "if it fires" remedy.** P2 measured 1,939 of 4,103 IBM words
losing the **value** in the decode — overflow to `inf`, underflow to zero — and **no
re-encoding can reconstruct them, because the information left at decode time**. The raw
view is the only thing that makes those bits recoverable.

`uint32` is a **container, not an interpretation** — the same reasoning as SP5's `uint8`
fillers. It carries no float semantics, so no decode can be applied to it by accident.

**Plane 4 gains a second leg, reported separately and deliberately not folded into its
verdict.** The raw-word comparison is **exactly invertible by construction** — a `uint32`
is copied, not transformed — so it holds precisely where the float comparison cannot.
Keeping it separate matters: **two decoded arrays that both read `inf` are equal without
either being the source sample.** A store can have correct raw words and a lossy decode,
and neither fact is allowed to stand in for the other.

Written with stock `zarr`, not MDIO, so a consumer reads it with MDIO uninstalled (§10.3,
G4). Only written when the source is `ibm32` — no cost where there is no risk.

---

## D-0046 — 2026-08-23 — SP6 blind spot 2 closed. A warning nobody had ever seen

**Decision.** `recording_log_records()` attaches a handler for the duration of an
ingest and records what upstream **logs** at WARNING and above, alongside what it
**warns**. Two separate channels, two separate lists — flattening them would misreport
which mechanism was involved, and only one of the two is suppressible by a filter.

**Measured on a real sparse ingest**, where the ledger previously recorded nothing:

```
python warnings : 0
log records     : 2
   [WARNING] mdio.ingestion.grid_qc: Ingestion grid is sparse. Sparsity ratio: 3.00
   [WARNING] mdio.ingestion.segy.coordinates: Unexpected value in coordinate unit
             (measurement_system_code) header: 0
```

The first is the sparsity notice **probe P5 found missing**. The second is a coordinate-unit
warning **that has been raised on every ingest this project has ever run and appeared on no
certificate** — it was not suppressed, not filtered, and not noticed. Nobody was looking at
`logging`.

**Careful detail worth recording:** if the root logger has no handlers, upstream's records
currently reach stderr via `lastResort`, and attaching *any* handler silences that. The
implementation **carries `lastResort` forward** rather than replacing it — SDIP must not
leave the process quieter than it found it, which is the same discipline D-0004 applies to
the warning filters it criticises upstream for leaking.

**Blind spot 1 remains open, and is now declared rather than silent.** The ledger states
its own scope on every certificate:

```
covers: "parent-process Python warnings and parent-process log records only"
worker_process_warnings: "NOT CAPTURED - see OPEN_DEBTS D26"
```

**An empty `warnings_raised[]` can no longer be read as evidence of a quiet run.** That
does not capture the 2,441 `ibm32` overflow warnings P2 found stranded in spawn workers —
but it converts a silent gap into a declared one, which is the difference between a
certificate that misleads and one that is merely incomplete.

---

## D-0047 — 2026-08-23 — **P4's method is satisfied.** Two readers disagree about the same array

**Result.** zarr-java 0.2.0 (JVM) ran as P4's second implementation. **The method asked
for at least two; two have now run.**

| Reader | `struct` (`headers`) | `fixed_length_utf32` (`segy_file_header`) |
|---|---|---|
| TensorStore 0.1.85 (C++) | **accepts** — 97/97 fields, byte-identical | refuses |
| zarr-java 0.2.0 (JVM) | **refuses** | refuses |
| `zarr-python` 3.3.0 | accepts, with a warning | accepts |

**Three readers, three different answers about which extension dtypes exist.**

**The falsifier still did not fire, and this leg does not revive it.** *"Headers unreadable
outside Python"* is a universal claim, and leg 1 produced the counterexample. **One reader
that can read them settles whether they can be read. A second that cannot does not
un-settle it.** A reader declining an unspecified `data_type` is standards-conformant and
still right.

**The number to quote is not the verdict:** of the two non-Python implementations measured,
**`headers` is readable by one and not the other.** Core-spec arrays are readable by both,
byte-identically, with no exceptions.

**A finding leg 1 could not have produced.** `Group.list()` **fails outright** in zarr-java:

```
Failed to read node metadata for key 'segy_file_header/zarr.json':
Cannot deserialize value of type DataType from Object value
```

Listing opens every child node, so **one unparsable `data_type` takes the whole listing
down**. A zarr-java consumer cannot enumerate the store at all — not merely read one array.
**And the pre-approved `uint8` header plane would not fix that by itself**, because
`segy_file_header` keeps `fixed_length_utf32`. That materially changes the shape of the
mitigation and is recorded as debt.

**D3 stays OPEN, but its reason changed from *unmeasured* to *measured*.** What was an
argument from the specification — *"support is an implementation choice, not conformance"* —
is now an observation: a second reader refuses the same array in the same store.

---

## D-0048 — 2026-08-23 — **The published schema had been invalid for phases, and nothing checked**

**Found by the D26 agent**, which noticed its new `warnings` keys would be rejected by
`additionalProperties: false` and stopped to ask rather than editing a file outside its
allowance. Investigating that question found something much larger.

**The published certificate schema rejected the real certificate in six places:**

| Location | Rejected |
|---|---|
| root | `portability`, `nonvacuity`, `roundtrip_closure`, `determinism`, `scale`, `release_readiness`, `transform_scope_blocks_equivalence`, `transform_scope_reason` |
| `warnings` | `logged`, `logged_count`, `scope`, `suppression_count`, `undeclared_filter_count` |
| `roundtrip` | `status`, `first_difference` |
| `transforms_declared[]` | `sample_format`, `probe`, `bit_identical_exponent_codes`, `raw_uint32_view_stored` |

**Two of those — `suppression_count` and `undeclared_filter_count` — were added at
D-0022, several phases ago.** The schema has been wrong since F3.

**Why nothing caught it.** There was **no test validating a certificate against the
schema**. `jsonschema` was not installed and nothing compared the document to the
contract that describes it. Every other test passed, `sdip certify` produced
certificates, and the schema sat in the package looking authoritative.

§4.7's promise is precise about who this hurts:

> published so third parties can validate SDIP output **without running SDIP**

It was false **only for them**. Anyone running SDIP saw nothing wrong; anyone taking the
project at its word and validating externally got a spurious failure on every
certificate. **A published contract nobody checks against the thing it describes is
documentation, not a contract.**

**Fixed in the order that matters.** The guard was written **first**, watched fail, and
only then was the schema corrected — the same discipline as a negative control. It
validates the **fullest** chain the engine can run, because a sparse certificate would
pass while leaving the newest blocks — the ones most likely to have diverged —
unexercised. It reports *every* violation rather than the first, because drift arrives in
clusters and fixing one error per run is how it got this far.

`jsonschema` is a **dev** dependency. The runtime tree is licence-scanned and must not
grow: a consumer brings their own validator, which is the entire point of publishing a
schema rather than a library.

**One violation was the schema being right.** `git/dirty: False was expected` fired
because the test fixture issues from a dirty tree to run at all. §11.3 says a certificate
from a dirty tree is invalid, and the schema enforces it. The fixture now sets
`dirty: false` and says why, rather than the schema being loosened to accommodate a test.

---

## D-0049 — 2026-08-23 — The raw leg is ANDed into G2d, not merely reported

**Ruling on a question the D1 agent raised rather than decided.** It built the raw-word
comparison as **evidence only**, exactly as instructed, and then flagged the consequence:
*"a corrupted word in `amplitude_raw_ibm32` is reported and no gate fails. So this
evidence has no G7 control and is not yet a gate."*

**It was right to flag it, and the instruction was wrong.** The original reasoning was
that a raw pass must not mask a float failure. `AND` satisfies that concern completely —
a raw pass cannot rescue a failed float comparison — **and** closes the hole: a raw
failure now fails the plane.

Left as evidence-only, SDIP could write a corrupted `amplitude_raw_ibm32` and no gate
would notice. That array is **the only recoverable copy of the source bits** for an
`ibm32` source (D-0045), so such a store would be certifiable while the thing the raw
view exists to protect was already gone. **Evidence nothing can fail is not a check; it
is a comment** — and shipping one is precisely the vacuity G7 exists to catch (**SP11**).

**Measured:** a flipped raw word now fails G2d with `raw_ibm32_identical: false`, while
the decoded leg's `mismatch_count` stays **0**. The legs remain independent; both bind.

**A G7 control ships with it** — `flipped_raw_ibm32_word`, declaring `{G2d}`. Measured:
**9 controls, each failing exactly the gates it declares and no others.** A gate without
a control is what this project spent F4 refusing to ship.

`None` (array absent, correct for a non-`ibm32` source) is **not** a failure; only an
explicit `False` fails.

---

## D-0050 — 2026-08-23 — Two staleness bugs of the same shape

Both surfaced by agents working outside their own allowance and reporting rather than
patching. Both are **a constant that stopped being true**, and neither could go stale in
a way a test would notice.

**1. `raw_uint32_view_stored` was hard-coded `False`.** The moment the raw view was
built, **every `ibm32` certificate carried a false statement about its own contents.** It
is now read from the store — `ARRAY_NAME in group` — because the certificate's job is to
describe what is on disk, and the only reliable way to do that is to look.

**2. The CLI's warnings line said `0 observed` while every sample was `inf`.** It is the
exact misreading D26 exists to prevent, printed at the operator. It now shows Python
warnings **and** log records **and** the declared scope:

```
warnings      0 python warning(s), 2 log record(s), 2 suppression(s), 0 UNDECLARED
              covers: parent-process Python warnings and parent-process log records only
              workers: NOT CAPTURED - see OPEN_DEBTS D26
              [WARNING] mdio.ingestion.grid_qc: Ingestion grid is sparse...
```

**Printing counts without the scope is how a zero gets misread as quiet.** The
certificate has carried the scope since D-0046; the terminal an operator actually watches
did not.

---

## D-0051 — 2026-08-23 — The `uint8` header plane is written. Measured cheaper than promised

**Decision.** `headers_raw_uint8` — shape `(*grid, 240)`, `uint8`, the raw trace-header
bytes read from the source by offset — is written **unconditionally**, with stock `zarr`.

**Why unconditionally**, unlike the `ibm32` raw view: every store has headers, and the
portability problem is not conditional. P4 measured **three readers giving three different
answers** about the structured array's `struct` dtype — TensorStore accepts, zarr-java
refuses, `zarr-python` warns — and `struct` has **no Zarr v3 specification**, so a reader
that declines it is conformant and still right. A 2-D `uint8` array is as portable as
Zarr gets.

**Plane 3 gains a byte leg with no spec dependency at all.** Its field-wise comparison
equals byte equality *only because G1 proved the spec covers all 240 bytes*; this leg
compares the 240 raw bytes directly. It is **ANDed into G2c**, following D-0049: **a
portable copy nothing checks is not evidence.** A G7 control ships with it —
`flipped_raw_header_byte`, declaring `{G2c}`. **10 controls now**, each failing exactly
its declared set.

**Measured on 116,532 real traces — cheaper than the pre-registration promised:**

| Array | Compressed | Per trace |
|---|---|---|
| `headers` (structured) | 230,658 B | **1.98 B** |
| `headers_raw_uint8` | 1,078,722 B | **9.26 B** |

The pre-registration estimated **≈19 B/trace**. The measured figure is **less than half
that**. At N=30 the same measurement reads 164 B/trace — Blosc block overhead swamps the
signal — which is why the 30-trace article cannot produce an honest per-trace number and
this one was taken on real data.

**Known limitation, stated rather than solved.** This does **not** fix zarr-java's
`Group.list()`, which fails on `segy_file_header`'s `fixed_length_utf32` (debt **D32**).
The plane makes header *data* portable; it does not make the group *enumerable*.

---

## D-0052 — 2026-08-23 — **The store is now larger than the source.** The raw sample view costs 97 %

**Measured, and it changes a headline number this project has quoted repeatedly.**

| | Before the raw views | Now |
|---|---|---|
| Source | 494,565,408 B | 494,565,408 B |
| Store | 379,983,485 B | **747,817,814 B** |
| Ratio | **0.77×** — smaller than source | **1.51×** — larger than source |

The cause is almost entirely one array:

| Array | Per trace | Share |
|---|---|---|
| `amplitude` | 3,258.47 B | — |
| **`amplitude_raw_ibm32`** | **3,147.25 B** | **97 % of `amplitude` itself** |
| `headers_raw_uint8` | 9.26 B | negligible |
| `headers` | 1.98 B | negligible |

**The raw sample view nearly doubles the store.** That is unsurprising in hindsight —
it is the same samples, undecoded — but it was never measured, and every prior statement
about SDIP's storage cost was made before it existed.

**It is not being made optional, and the reasoning matters.** The obvious response is a
flag defaulting off. That is precisely the shape §0.1 warns about: *"lossy codecs get
enabled for a size win and never get disclosed downstream."* A convenience flag that
silently trades recoverability for disk is how the guarantee erodes — and P2 measured
**1,939 words in 4,103 losing the value**, unrecoverable from the decode alone.

**When it is genuinely redundant:** if G3 is byte-identical, nothing was lost, and the
source is itself the recovery path. But that is known only *after* export, and only while
the source still exists — which for an archive-rescue project is exactly the assumption
that fails.

**Recorded as a debt (D36) rather than acted on**, because it is a real trade-off and the
right resolution is a maintainer's, not an implementer's. **What must not happen is the
cost going unstated**, which until this measurement it was.

**Also corrected:** the frequently-quoted *"full 240-byte header preservation costs 0.06 %
of the store"* is unchanged in substance — headers are still 1.98 B/trace, and the plane
adds 9.26. **Headers were never the cost.** The samples are.

---

## D-0053 — 2026-08-23 — A certificate could attest to code that produced none of its measurements

**Found by running the release chain, not by a test.** I dirtied the tree while a
`sdip certify` run was in flight. It ran the full chain — three ingests, five planes,
export, a 494 MB SHA-256, ten G7 controls — and *then* refused. Correct refusal,
**three defects behind it.**

### 1. The soundness hole — a false provenance claim was reachable

`issue()` checked the tree at issue time only. That is not sufficient, and the gap is
not theoretical:

```
start on commit A (clean)  ->  measure everything  ->  commit midway  ->  issue on B
```

The tree is **clean at issue time**, so the check passes. Every measurement came from
the code at **A**. The certificate names **B**. **A certificate that attests
measurements to code that did not produce them is exactly the untrusted artifact §0
describes** — and this project's entire claim is that its output is reproducible from
the committed record.

**Fix:** git state is captured **before the measurements begin** and passed to `issue()`,
which now requires the commit to be unchanged. Both ends, not one.

**The negative control is the part that matters** (§5). It asserts the check is
non-vacuous by showing both sides: with a clean tree at a *moved* HEAD, `issue()` without
the baseline **succeeds** — and refuses with it. A control that only asserted the refusal
would pass against a check that refused everything.

### 2. Fail-fast — 30 minutes of compute for a knowable-in-0.4 s answer

The refusal is the last step of the chain. Now checked first as well: **0.4 s instead of
the full run**, measured. Same principle as §3.6 — validate before you allocate. The
issue-time check stays; it is the binding one.

### 3. **`main()` caught one of eight `SdipError` types.** The rest were tracebacks

`PhaseNotAuthorisedError` was handled. `DirtyTreeError`, `UntrustedInputError`,
`SpecCompletenessError`, `EquivalenceError`, `BarredEnvironmentError`,
`BarredPackageError`, `PinMismatchError`, `BarredLicenceError` all escaped the CLI
boundary as raw Python tracebacks.

**`UntrustedInputError` is the serious one.** §3.6: *"A malformed or hostile SEG-Y must
produce a clean error — never a crash."* SDIP parses binary files it did not create, and
**a traceback at the CLI boundary is the crash that clause bars.** The property was
asserted in the contract and untrue in the code.

Now catches `SdipError` — the **base class**, deliberately, so a subclass written
tomorrow is covered the day it is written rather than the day someone remembers this
list. Verified: exit `1`, message, zero tracebacks.

The test uses `_BoomError`, a subclass `main()` has never heard of, precisely to prove
the boundary catches the base and not an enumeration.

### What this says about the F0-era text

Three of these sites were stale claims, not logic: `sdip certify --help` still said *"G7
does not exist"*, `sdip.equivalence`'s docstring said *"G5, G6 and G7 do not exist"*, and
two dead `not_yet()` helpers still said *"the repository is at F0"* with **no callers at
all** — every command is built. Deleted rather than reworded; dead code carrying a false
claim is worse than no code.

**A test was pinning one of them.** `test_certify_still_documents_the_g7_ceiling`
asserted `"PROVISIONAL" in output`, which was right at F3 and wrong from F4 — the suite
was *enforcing* the stale claim. It now asserts the current bar and that `PROVISIONAL` is
**absent**. Worth noting: a green suite protected a false statement for four phases.

---

## D-0054 — 2026-08-23 — The published schema identified itself by a URL that does not exist

**Found by installing the wheel and using it as a consumer would**, not by any test in
the repository.

`README.md` makes a specific promise: *"`pip install sdip` gives a validator to a
consumer who never clones."* Verified in a clean venv from the built wheel — the schema
is readable via `importlib.resources`, and reading it **does not import `mdio`**, which
is the whole point. Both hold.

**But the schema's `$id` was:**

```
https://github.com/OWNER/sdip/blob/main/docs/certificate-schema/sdip-certificate-v0.schema.json
```

**Two independent defects in one line.** A literal **`OWNER`** placeholder; and a path
under **`docs/`**, which the publication firewall means is **never committed** — so even
with the owner corrected the URL would 404 forever.

`$id` is a JSON Schema's canonical identifier. **A published schema that names itself by
an unreachable address is the documentation-not-a-contract failure D-0033 already
recorded once**, in a different place. D-0015 moved the schema out of `docs/` into
`src/sdip/schema/`; **the `$id` did not move with it, and nothing checked.**

Now `https://raw.githubusercontent.com/zahidaramai/sdip/main/src/sdip/schema/sdip-certificate-v0.schema.json`
— a raw URL that resolves to the bytes, rather than a `blob` page that resolves to HTML.

**The test is the point, not the fix.** It asserts no `OWNER`, no `/docs/`, and that the
id's tail names the path the file actually occupies — checked for **every** version in
`SCHEMA_FILENAMES`, so a v1 schema is covered the day it is added. **Non-vacuity
verified** (**SP11**): restoring the old `$id` fails it, restoring the new one passes.

### What the build check found and did not find

The wheel and sdist were also scanned for firewall leaks. **Both clean** — no `docs/`,
no `local/`, no `CLAUDE*`. The sdist ships the four append-only records, `LICENSE` and
`NOTICE`; the wheel ships `py.typed`, the schema, `LICENSE` and `NOTICE`.

**One note on method.** My first leak scan reported `!!! LEAK !!!` on both artifacts and
was **wrong both times**: the pattern `_[a-z]*\.py$` matched every `__init__.py`, and the
wheel scan matched the string `claude` **in my own scratchpad path**, not in the archive.
A false positive that had been believed would have produced a fabricated security
finding. **SP8 cuts both ways — a scary number is a measurement too, and it gets checked
before it gets reported.**

---

## D-0055 — 2026-08-23 — **D17 closed for ingest.** An undecodable textual header no longer refuses

**Decision.** A source whose 3200-byte textual header cannot be decoded is **ingested**,
not refused. The converter runs with `MDIO__IMPORT__SAVE_SEGY_FILE_HEADER=0`, SDIP's own
authoritative raw bytes are stored as always, and the certificate records
`detected_encoding.decode_status = raw_preserved_decode_failed`. §4.2 is now satisfied on
the ingest path: *"decode failure is not an ingestion failure; silent substitution is."*

**Measured, against the pinned `multidimio` 1.2.1 / `segy` 0.6.0**, on a synthetic N=1
fixture of 12 traces with 8 planted non-conforming bytes
(`tests/fixtures/generators/undecodable.py`, deterministic, no RNG, no clock).

### What upstream actually does — all three modes, run

**Mode 1 (STRICT).** Raises. Real traceback, public entry point to raise site:

```
  File ".../mdio/converters/segy.py", line 72, in segy_to_mdio
    return _ingest_segy_to_mdio(
  File ".../mdio/ingestion/segy/pipeline.py", line 187, in segy_to_mdio
    serialize_to_mdio(
  File ".../mdio/ingestion/segy/serializer.py", line 74, in serialize_to_mdio
    xr_dataset = add_segy_file_headers(xr_dataset, file_info)
  File ".../mdio/ingestion/segy/file_headers.py", line 42, in add_segy_file_headers
    validate_text_header(text_header)
  File ".../mdio/segy/text_header.py", line 65, in validate_text_header
    raise ValueError(err)
ValueError: Invalid text header characters: non-ASCII or non-printable at row 0:
positions [0, 1, 2, 79], row 1: positions [0], row 2: positions [0], row 20:
positions [0], row 39: positions [79]
```

A plain `ValueError`, out of the public `mdio.segy_to_mdio`. **No store is written** —
measured, `output.exists()` is `False` — because the validation sits at serializer step 4
and `to_mdio` initialises the store at step 6. So the refusal is clean and leaves nothing
to clean up.

**Mode 2 (LENIENT).** Completes, and rewrites. Measured on the same fixture: the stored
`textHeader` begins `"    SDIP SYNTHETIC FIXTURE"` where the source's first card begins
`"C 1 SDIP SYNTHETIC FIXTURE"` — the offending characters replaced by spaces and the card
identifier destroyed with them. This is the silent substitution §4.2 bars, and **D-0020
stands unchanged**.

**Mode 0 (OFF).** Completes. Writes **no** `segy_file_header` variable, validates nothing,
and never touches the header bytes.

### Why mode 0 is the answer and not a loophole

Neither mode 1 nor mode 2 delivers §4.2. Mode 0 does, because SDIP does not need
upstream to preserve the textual header — **it already holds those bytes itself**
(D-0021) and writes them to the store. Plane 1 is checked against the source's own bytes
on either path. What mode 0 removes is upstream's *parsed* view, which §4.2 never asked
for and which mode 2 would only have supplied in corrupted form.

### The mode is chosen up front, not by catching the exception

`classify_textual_header` decodes the raw bytes with the **same `TextHeaderSpec` object**
handed to `segy_to_mdio` — the same call `SegyFile.text_header` makes — and applies §4.2's
contract to the result. Deciding before the call costs no second geometry scan and
couples to no upstream exception type or message (§3.3).

It is SDIP's predicate, so it can disagree with upstream's. **Both directions are safe
rather than silent**: stricter, and the ingest completes with the loss recorded on the
certificate; looser, and mode 1 raises exactly as it does today. Agreement is **measured,
not assumed** — on the non-conforming fixture SDIP names the offending cells
`[(0,0),(0,1),(0,2),(0,79),(1,0),(2,0),(20,0),(39,79)]` and upstream's own `ValueError`
names the same eight, and on the conforming fixture both accept. N=2 fixtures, 8 cells.

### `detected_encoding` was a claim; it is now a measurement

Before this entry `certificate.py` hard-coded `{"encoding": "ebcdic", "decode_status":
"decoded"}` on **every** certificate. That is a fidelity claim with no number behind it
(**SP8**), and it would have been false for exactly the legacy vintage §4.2 exists to
rescue. Both fields now come from the ingest's measurement of the file's own 3200 bytes.
A result carrying no measurement reports `unknown` / `raw_preserved_decode_failed` rather
than defaulting to `decoded`: an unmeasured decode must not read as a passing one.

### What it costs, recorded rather than hidden

- **§4.3's *parsed mapping* half is unmet** for such a store. Plane 2 still PASSes — the
  raw bytes are authoritative and they are intact — and its evidence carries
  `parsed_mapping_present: false`, which is where a reader finds this out.
- **G3 is unreachable.** `mdio_to_segy` raises `MDIOMissingVariableError` without a
  `segy_file_header` variable. `sdip.export.roundtrip.export` now refuses first, with a
  typed `RoundTripUnavailableError` that names the cause, so the operator gets a clean
  error and not an upstream traceback (§11.4). **This is not a limitation of the
  fallback**: upstream's exporter re-encodes the *decoded* text and runs
  `sanitize_text_header` over anything that will not encode, so byte identity is
  impossible for a non-conforming header under **any** mode. Mode 2 would merely have
  produced a plausible-looking wrong file instead of a refusal.
- **`sdip certify` therefore cannot complete on such a source.** It calls `export`
  unconditionally and now stops there, cleanly. Deciding what G3 should *say* about a
  source that can never round-trip — `FAIL`, or `ROUNDTRIP-SCOPED` with a written
  justification (§7 G3) — is a change to a gate, which §9 says to raise rather than
  decide alone. **Left open and narrowed in `OPEN_DEBTS.md` rather than guessed at.**

### A second store shape means a second place to be vacuous

The fallback store has no `segy_file_header`, so SDIP's raw attributes live on the **root
group**. Three pieces of code resolve that location independently — the writer, Plane 1's
reader, and G7's textual controls — and they now share one resolver, `raw_header_node`. A
control that resolved it differently would have *raised* instead of corrupting, and G7
would have reported a control error over an audit that never ran: D-0028's defect reached
by a different route.

**G7 re-run in full on the fallback store**: baseline clean, **10 of 10 controls each
failing exactly the declared gate set and no other**, store byte-identical before and
after. The two textual controls fail **G2a alone** on this shape, as on any other.

**No tolerance, no suppressed warning, no barred variable, no new dependency, no pin
bump, no fork, and no upstream internal imported.** `mdio.segy.text_header` is *not*
imported; §4.2's contract is restated in SDIP's own code, which is what §3.3 requires.

**What overturns it.** An upstream mode that persists the parsed headers *without*
rewriting the text would make mode 0 unnecessary and should be adopted; the drift tests in
`tests/integration/test_undecodable_textheader.py` fail the day upstream's behaviour moves.

---

## D-0056 — 2026-08-23 — External steward audit: four findings. **Two confirmed by my own measurement, and one of them is Tier-1**

An external audit was performed at HEAD `de08bc7`. **Every finding below was re-derived
here before being accepted** — an audit is a claim until checked, the same standard this
project applies to its own reports (§4.4).

### Finding 1 — TIER-1, CONFIRMED. The derived arrays are outside the audit surface

Reproduced independently on the 30-trace article, with `crossline` added:

| Corruption | P1 | P2 | P3 | P4 | P5 |
|---|---|---|---|---|---|
| baseline | PASS | PASS | PASS | PASS | PASS |
| **`cdp_x[0,0]` 1005000.0 → 1005001.0** | PASS | PASS | PASS | PASS | **PASS** |
| **`cdp_y[0,0]` 2002500.0 → 2002501.0** | PASS | PASS | PASS | PASS | **PASS** |
| **`time[0]` 0 → 1** | PASS | PASS | PASS | PASS | **PASS** |
| `inline[0]` 100 → 101 | PASS | PASS | FAIL | FAIL | FAIL |
| `crossline[0]` 200 → 201 | PASS | PASS | FAIL | FAIL | FAIL |

`inline`/`crossline` are audited **implicitly**, because the trace map is built from them.
**`cdp_x`, `cdp_y` and `time` are audited by nothing.** Confirmed structurally as well:
no plane names them, and none of the ten G7 controls has them in its `touches` set.

**Why this is Tier-1 on this project's own terms, not the auditor's:**

- **G4 and §10.3 promote precisely these arrays as what a consumer reads.** A store can
  carry corrupted world coordinates under an **`EQUIVALENT`** verdict.
- **`cdp_x`/`cdp_y` are the *output* of the declared coordinate-scalar transform**
  (D-0040). **SP1 requires a declared transform to be verified; a declared transform
  with an unverified output is half-declared.** A scalar sign error — `-100` meaning
  divide, the classic geometry bug — is exactly the deterministic defect that passes
  every gate today.
- **This is the third instance of a vacuity class already fixed twice**: D-0049 ANDed
  the raw sample words, and the raw header byte leg was ANDed for the same reason.
  *Evidence nothing can fail is not a check.* The derived coordinates are the same shape,
  unfixed.

**G6 does not cover it**: it compares two fresh ingests, so it catches nondeterminism, not
a deterministic derivation bug — and it does not run at all in the verify-an-existing-store
flow, which is the archival re-audit case.

### Finding 3 — CONFIRMED. A certificate-facing string contradicts the code

`RAW_IBM32_NOTE` (`planes.py:462`) tells a certificate reader the raw leg is *"reported
separately and **NOT** part of G2d's verdict"*. The `plane_4` docstring says the same. The
implementation ANDs it:

```python
ok = not mismatches and trace_map.invertible and raw_ok
```

D-0049 made that change deliberately and the note was never updated. **The false sentence
ships inside issued certificates** — `"raw_ibm32_note": RAW_IBM32_NOTE` is written into
the payload. In a project whose product is trust, **a certificate carrying a false
statement about its own semantics is not a typo.** Third staleness bug of the D-0050
shape.

**Measured, so no certificate needs superseding:** both payloads under `local/` predate
the raw view and carry no `raw_ibm32_note` at all. Checked, not assumed.

### Finding 4 — ALREADY FIXED, before the audit was received

The ledger staleness was corrected in `baa1002`. **But my correction contained its own
error**, which finding 4 has now surfaced — see the ledger's own appended correction.

### Finding 2 — mechanism CONFIRMED; the *number* is not yet honestly measured

The strongest observation in the audit: **P3's "flat 2.81–2.87 GiB across eleven files"
measured one file size eleven times.** Verified — all twelve Sleipner files are
**byte-identical in size at 494,565,408**. That is *replication*, not *scaling*: the
independent variable never varied, so the flatness is a constant, not evidence of
scale-invariance. **D2 was closed on that basis and the closure does not support the
generalisation.**

The mechanism claim is confirmed by inspection: **ten `[:]` sites in `planes.py`**, and
`plane_4` holds `handle.sample[:]` **and** `group[variable][:]` simultaneously.

**I am not adopting the ~5.8× multiplier or the ~1.4 GB breach point yet.** My first
attempt to measure it used files of 0.9–21.8 MB, where a ~0.4 GB interpreter baseline
dominates; the resulting fit **over-predicted the one real data point by 65 %**. An
extrapolation that cannot reproduce the measurement it is extrapolating from is not
evidence, and importing the auditor's number because it sounds right would be exactly
the assumption SP8 forbids. A measurement in the real size regime is running; the
correcting entry for D-0042 waits on it.

---

## D-0057 — 2026-08-23 — **SDIP validated almost nothing before handing an untrusted SEG-Y to upstream.** 18 of 33

**Debt D8, closed against a corpus.** the operating contract §3.6 and spec §11.4 both state that a
malformed or hostile SEG-Y must produce a clean error, never a crash, an unbounded
allocation, or a write outside the output path, and that *"header-declared lengths and
counts are validated against actual file size before allocation."* **Every word of that
was an assertion.** `sdip.errors.UntrustedInputError` existed and its docstring quoted
§11.4; what it was actually raised for was a file shorter than 3600 bytes, a path that
was not a regular file, and nothing else.

**33 synthetic hostile files, 9 classes, one fixed seed** — `tests/fixtures/generators/
hostile.py`, run one per process by `tests/negative/test_d8_hostile_corpus.py`.

### What the corpus measured, before any fix

| Outcome | Members | Examples |
|---|---:|---|
| Typed `UntrustedInputError` | **8** | empty file, 3599 bytes, not a regular file |
| **Untyped exception from a dependency** | **18** | `ValueError`, **`ZeroDivisionError`**, `pydantic.ValidationError`, `SegyFileSpecMismatchError`, `GridTraceSparsityError` |
| Converted | 7 | structurally valid, semantically odd |

**A zero in binary-header bytes 3217-3218 — the sample interval — produced a
`ZeroDivisionError` from inside a dependency.** That is the shape of finding D8 was
raised to look for: a one-field, two-byte edit to an otherwise valid file, and the answer
is an untyped exception and a traceback on the console.

Every one of the 18 was raised **inside `segy`, `mdio` or `pydantic`** — that is, *after*
the file had been opened, read and sized from its own numbers. The validation §11.4
requires before allocation was happening after it, in someone else's code, or not at all.

### The fix — `src/sdip/ingest/preflight.py`

Reads **exactly 400 bytes** at a fixed offset and does integer arithmetic against
`st_size`. No allocation is proportional to anything it reads. In order, because each
check is a precondition of the next: samples per trace `> 0`; sample interval `> 0`;
sample-format code present in the pinned `segy` 0.6.0 enumeration; extended textual
header count `>= -1` and not larger than the file; trace data present; and the trace data
a whole number of `240 + samples x bytes_per_sample` traces.

The format-code table is **read out of `segy.standards.codes.DataSampleFormatCode`**, not
written down. A hardcoded list is a second source of truth that drifts from the decoder
actually in use; this one cannot disagree with what the pin can decode, because it is what
the pin can decode.

**The divisibility check is not a new policy.** `raw_samples.source_trace_layout` has
applied the identical reconciliation since the raw `ibm32` view shipped, and it has run
over 116,532 real traces. D8 moves it earlier and makes it universal.

### After

| Outcome | Members | Change |
|---|---:|---|
| Typed `UntrustedInputError`, **raised inside `sdip`** | **24** | +16 |
| MDIO's typed grid errors | **3** | recorded residual |
| Untyped exception from a dependency | **0** | **-18** |
| Converted | 6 | -1 (`sample_interval_negative` now refused) |

**Peak RSS, measured per process** (Darwin 25.5.0, CPython 3.12.13):

| | Before | After |
|---|---:|---:|
| Refusal | 118.6-120.3 MB | **52.9-53.4 MB** |
| Successful ingest | 209.8-212.0 MB | 210.3-212.0 MB |

**A refusal now costs what starting the interpreter costs.** The 66 MB that disappeared
was upstream opening and parsing a file SDIP had already been told not to trust. Declared
ceiling: **512 MiB**, asserted on every member; the observed maximum is 212.0 MB and it is
a *successful* ingest.

**No unbounded allocation was ever found**, before the fix or after —
`declared_extended_headers_exceed_file` claims 104,854,400 bytes of extended headers in a
14,640-byte file and never allocated for it. The defect was the error *type* and the
traceback, not memory.

**No write escape was found.** The run tree and the repository are snapshotted around
every child process. `path_bait_in_headers` is a structurally valid file whose textual
header and trace-header tails read `../../../../../../tmp/sdip_d8_escape`; it converts, as
it must, and the bait exists nowhere on disk afterwards.

### What was deliberately **not** fixed

Three members are refused by `GridTraceSparsityError` / `GridTraceCountError` and reach
the console as a traceback. **They are left alone on purpose.** These are geometry
verdicts, reachable only after a full trace-header pass — the thing pre-allocation
validation must not do — and **probe P5 measured MDIO making exactly these refusals and
pinned the types as the defence SDIP relies on** (D-0036). `GridTraceCountError` is raised
unconditionally, so it is *not* suppressible by `MDIO_IGNORE_CHECKS`, which is the whole
reason the duplicate-trace defence counts as a defence. Re-typing them inside SDIP would
overturn a recorded measurement to satisfy a presentation preference. That is a
maintainer's call (§9), and it stays open on D8.

### One prior record updated

`test_p5_geometry.INGESTS["byte_swapped"]` moved from `"256 is not a valid
DataSampleFormatCode"` to `"most likely a little-endian SEG-Y"`. **The verdict is
unchanged** — a little-endian SEG-Y still does not convert — but the refusal moved from
`segy`, after the read, to `sdip`, before it. The message now names the byte order rather
than leaving a reader to work out why a format code read 256. P5's table is explicitly a
record of what happened, so a deliberate change updates it rather than being worked
around.

**A little-endian SEG-Y is a real file, not a corruption**, so `preflight` re-reads the
offending fields the other way round and says so when they come out coherent. That is the
difference between an error a reader can act on and one that sends them looking for
damage that is not there.

---

## D-0058 — 2026-08-23 — **`sdip ingest` accepted `s3://`, exited 0, reported `G1 PASS`, and wrote to a local directory named `s3:`.** 0 objects in the bucket

**Found by probe P8's local object-store leg** (`prereg/P8-cloud-object-store.md`,
Amendment A) against a real S3 server — MinIO `RELEASE.2025-10-15T17-29-55Z` on loopback,
`s3fs` 2026.1.0 — not a mock.

### What was measured

| Entry point | Asked for | Objects in bucket | What happened |
|---|---|---:|---|
| `ingest(src, "s3://sdip-p8/via-sdip.mdio")` | an object store | **0** | Returned **normally**, no exception. `IngestResult.output_path` = `/Users/…/seis-mdio-zarr/s3:/sdip-p8/via-sdip.mdio`. **49 paths, 20 files** written under a local directory literally named `s3:` at the process working directory. |
| `sdip ingest src s3://sdip-p8/via-cli.mdio` | an object store | **0** | **Exit code 0.** Printed `G1 PASS`, `read path intact`, and `output /…/work/s3:/sdip-p8/via-cli.mdio`. |

The cause was one line in `sdip.ingest.orchestrator.ingest`:

```python
output_path = Path(output).resolve()
```

`pathlib` collapses the doubled slash, so `s3://bucket/store.mdio` becomes the **relative**
path `s3:/bucket/store.mdio` and resolves against the working directory. No scheme is
recognised, nothing is validated, nothing raises.

### Why this is worse than a crash

**A green run and an empty bucket were indistinguishable to the operator.** Spec §11.4
bars a crash on bad input, and it equally bars *"a write outside the output path"* — which
is exactly what this was, at the operator's working directory rather than anywhere they
named. An operator running this in a container gets exit 0 and a store on ephemeral disk,
which is the situation §11.2 exists to talk about, since that disk is then discarded.

It also means **the `cloud` extra in `pyproject.toml` has never been usable**, and §11.2's
object-store requirements were never reachable through any shipped entry point. `verify`,
`export` and `certify` are equally unable to address a store: all three type the argument
as `click.Path(exists=True, file_okay=False)`, which no URI satisfies.

### The decision: refuse, do not implement

**Object-store output is debt D7 and is out of phase. This change does not implement it.**
It makes the absence audible instead of silent. `validate_output_path` in
`sdip/ingest/orchestrator.py` runs **before `Path(output)` touches the argument** — that
is, before the source is read, before the spec is built, before G1, before any allocation
— and raises `PhaseNotAuthorisedError`, an existing type whose meaning is exactly this
(*"the requested capability belongs to a later roadmap phase"*) and which the CLI boundary
already handles.

```
$ sdip ingest article.sgy s3://bucket/store.mdio
sdip: output path names the URI scheme 's3' (s3:/bucket/store.mdio). SDIP writes to the
local filesystem only; object-store output is NOT implemented (OPEN_DEBTS D7, probe P8)
and no scheme is supported, including s3://, gs://, gcs://, az://, abfs://, abfss://,
adl://, wasb://, wasbs:// and http(s)://. Refusing before any work is done. …
exit 2, and the working directory is unchanged.
```

**Every scheme is refused, not a barred list.** The failure being prevented is "SDIP
silently wrote somewhere else"; an allow-list would let the next scheme through. `file://`
is refused too — `Path("file:///tmp/x")` is the relative path `file:/tmp/x`, so it fails
the same way, and letting one scheme through because it *sounds* local would reintroduce
the defect for that scheme.

**Two forms are matched, because the mistake arrives two ways.** A library caller passes
`s3://bucket/key` intact; `click.Path(path_type=Path)` has already collapsed it to
`s3:/bucket/key` by the time the CLI reaches `ingest`. A check matching only `://` would
pass every library test and still leak from the CLI. The scheme must be **at least two
characters**, so `C:/surveys/x.mdio` is a Windows drive and is accepted; the slash is
**required**, so `my:dir/store.mdio` is a legal POSIX directory and is accepted.

### The negative control, and it fails without the fix

`tests/negative/test_object_store_output_refused.py` — **32 tests, all passing.** Disabling
the single `validate_output_path(output)` call and re-running gives **12 failed, 20
passed**: the 12 are the three assertions that measure integration rather than the
predicate — the ordering proof, the working-directory proof, and the CLI exit code. The 20
that still pass call the validator directly, which is correct, and is the reason the
integration assertions exist at all.

Three assertions per barred scheme, because any two of them pass on a broken fix:

1. It raises `PhaseNotAuthorisedError` — typed, not a traceback.
2. The CLI exit code is non-zero, no traceback reaches stderr, and **no gate prints a
   verdict** for a run that was refused.
3. **Nothing is created in the working directory.** This is the assertion that pins the
   defect: a fix that raised *after* `segy_to_mdio` ran would satisfy 1 and 2 and still
   leave the `s3:` tree on disk.

The ordering assertion passes a **source that does not exist**. If the output check ran
after `validate_source` the result would be `UntrustedInputError` about a missing file —
a passing test for a check placed too late to prevent the write. §11.4 is an ordering
requirement, so the ordering is what is asserted.

**The positive control is not decoration** (**SP11**, the discipline of G7 and of the D8
corpus). A validator refusing every path would score perfectly on 1–3 and be useless, so
`store.mdio`, `/tmp/surveys/store.mdio`, `C:/surveys/store.mdio` and `my:dir/store.mdio`
must be **accepted**, and a real local ingest through the CLI must still exit 0.

### Scope, stated plainly

**Output only.** A source given as `s3://…` is already refused cleanly by
`validate_source` (`UntrustedInputError`, "source is not a regular file") and by click's
`exists=True`, so no silent write is possible there — but the *message* names the wrong
cause, and that is left as an observation rather than widened into this change.

**D7 stays open and is untouched by this.** Nothing here makes an object store work; it
makes the fact that it does not work impossible to mistake for success.

---

## D-0059 — 2026-08-23 — The derived arrays are inside the audit surface. Tier-1 closed

Closes the Tier-1 finding of **D-0056**. Two new legs, two new G7 controls, and the two
false strings corrected.

### The measurement, before and after

| Corruption | P1 | P2 | P3 | P4 | P5 |
|---|---|---|---|---|---|
| baseline | PASS | PASS | PASS | PASS | PASS |
| `cdp_x[0,0]` +1 | PASS | PASS | **FAIL** | PASS | PASS |
| `cdp_y[0,0]` +1 | PASS | PASS | **FAIL** | PASS | PASS |
| `time[0]` +1 | PASS | PASS | PASS | **FAIL** | PASS |
| `inline[0]` +1 | PASS | PASS | FAIL | FAIL | FAIL |
| `crossline[0]` +1 | PASS | PASS | FAIL | FAIL | FAIL |

Before this change the three middle rows were **all PASS**. Each now fails **exactly
one** plane, and the baseline is untouched — the leg catches corruption without
manufacturing failures on good stores.

### What the legs actually assert

**Plane 3 (G2c) — `cdp_x`/`cdp_y`.** Recomputed from the source trace headers under the
declared coordinate-scalar semantics (positive multiplies, negative divides) and compared
with `np.array_equal`. **Each trace's own scalar**, never trace 0's applied to all:
upstream reads trace 0 only, and a survey whose scalar varies is legal SEG-Y, so applying
one trace's scalar to the rest is a fabrication under **SP12**.

**Plane 4 (G2d) — the sample axis.** Recomputed as `delay + i × interval/1000` from the
trace-header sample interval and delay. The samples themselves are untouched by an axis
corruption, so **every float comparison still passes** — which is exactly why the decoded
leg cannot see it and why this control is not redundant with `flipped_sample_bit`.

**Absent or underivable is NOT CHECKED, never checked-and-passed** — the discipline the
raw legs already use. A store with no coordinate array, a spec with no coordinate scalar,
or a source whose interval varies between traces yields `None`, and only an explicit
`False` fails.

### Two defects I introduced and caught before landing

**SP8 applies to my own work.** Both were found by running the thing, not by reading it.

1. **The baseline went FAIL on P4.** I resolved the sample axis as
   `store_dimensions(group)[-1]`, but `store_dimensions` returns the **grid** dimensions
   and deliberately excludes the sample axis — so the leg compared the `crossline` array
   against a time progression. Now resolved by subtracting the grid from the data
   variable's `dimension_names`, in `_sample_axis_name`, which exists precisely so that
   mistake cannot be repeated with an index.
2. **Plane 3 RAISED on every prestack geometry.** The leg indexed coordinate arrays with
   the full grid cell, but a coordinate array need not be indexed by the whole grid. **A
   plane that raises has not judged the store at all** — the exact P7 failure mode of
   D-0039, reintroduced by me. Fixed with `_project_cell`, which projects the cell onto
   the dimensions each array declares and returns `None` — NOT CHECKED — rather than
   guessing when the grid cannot address them.

Had I committed on the poststack table alone, the second would have shipped.

### G7: 12 controls, each failing exactly its declared set

```
control                  | declared    | observed    | extra | missed
flipped_textual_byte     | G2a         | G2a         |   -   |   -
truncated_textual_header | G2a         | G2a         |   -   |   -
flipped_binary_byte      | G2b         | G2b         |   -   |   -
flipped_header_byte      | G2c         | G2c         |   -   |   -
flipped_sample_bit       | G2d         | G2d         |   -   |   -
inverted_live_mask       | G2e         | G2e         |   -   |   -
dropped_trace            | G2c,G2d,G2e | G2c,G2d,G2e |   -   |   -
flipped_raw_header_byte  | G2c         | G2c         |   -   |   -
flipped_raw_ibm32_word   | G2d         | G2d         |   -   |   -
transposed_traces        | G2c,G2d     | G2c,G2d     |   -   |   -
corrupted_cdp_coordinate | G2c         | G2c         |   -   |   -   <- new
corrupted_sample_axis    | G2d         | G2d         |   -   |   -   <- new
```

`corrupted_cdp_coordinate` shifts a coordinate by **one unit**, not to an absurd value,
deliberately: a coordinate-scalar sign error is the realistic geometry defect and it is
quiet. A control that only caught absurd values would not catch the real bug.

### Finding 3 — the certificate no longer contradicts itself

`RAW_IBM32_NOTE` and the `plane_4` docstring both said the raw leg was *"NOT part of
G2d's verdict"* while the code AND-ed it. Both now state the asymmetry as implemented: a
raw mismatch **fails** the plane; a raw pass **cannot** rescue a failed decoded
comparison. **No certificate needs superseding** — both payloads under `local/` predate
the raw view and carry no such note. Checked, not assumed.

**Suite: 1071 passed.** ruff and mypy clean on 45 modules.

---

## D-0060 — 2026-08-23 — **D-0042's mechanism sentence is retracted for the verification path.** P3 measured a constant

Correcting entry, appended under **SP10** — D-0042 is left unedited.

### What D-0042 said, and why it is wrong

D-0042 states that **"memory tracks the chunk working set"**. That is true of the dask
ingest path and **false of the verification path**, which fully materialises.

Ten `[:]` sites in `planes.py`. `plane_4` holds `handle.sample[:]` **and**
`group[variable][:]` simultaneously — the whole source volume and the whole store volume
in memory at once.

### P3 measured replication, not scaling

**The 2.81–2.87 GiB flatness across eleven files is a constant, not evidence of
scale-invariance.** Every Sleipner file is **byte-identical in size at 494,565,408** —
verified across all twelve. The independent variable never varied. **D2 was closed on
that basis, and the closure does not support the generalisation it was read as making.**

### What I measured, and what I refuse to claim

First attempt, on 0.9–21.8 MB files: fit `RSS = 0.45 + 9.26 × source` (GB). It
**over-predicted the one real data point by 65 %**. A ~0.4 GB interpreter baseline
dominates at that scale and the slope is not resolvable. **That measurement is discarded
as unfit, not quietly averaged in.**

Second attempt, in the real regime (four runs, 51–403 MB):

| source | peak RSS |
|---|---|
| 51.4 MB | 607.1 MB |
| 102.0 MB | 1,002.6 MB |
| 201.7 MB | 1,784.3 MB |
| 402.6 MB | 3,324.6 MB |

**`RSS_MB = 214.7 + 7.73 × source_MB`, R² = 0.99997.** Verification memory is **linear in
file size**. The mechanism claim is settled.

**The breach point is a range, and I am reporting it as one:**

- from the synthetic fit — **1,083 MB**
- anchored on the single real point (494.6 MB → ~3,049 MB, ratio **6.17×**) — **1,393 MB**

The synthetic fit still over-predicts the real point by **32 %**, so the two bracket
rather than agree. **The external audit's ~1.4 GB sits at the top of that range and is
corroborated, but I am not adopting it as a single figure** — the honest statement is
**breach between roughly 1.1 and 1.4 GB**, and a 20 GB file needs on the order of
**155 GB** and OOMs outright.

### What is NOT being done here

**The streaming refactor is deliberately not attempted in this change.** It is a design
lock, not a patch: chunked comparison changes how every plane reads, and landing it
beside the Tier-1 fix would make both unreviewable. Raised as debt **D38** with the
measured falsifier.

---

## D-0061 — 2026-08-23 — **A partially written store certified `EQUIVALENT`.** Absence was read as "not checked"

Found by probe **P8** against a real MinIO object store, reproduced by me on the local
filesystem — **it is a property of the Equivalence Engine, not of S3.** The object store
is how it was found, not where it lives.

### The asymmetry, in one line

**Deleting one CHUNK of `amplitude_raw_ibm32` failed Plane 4. Deleting the WHOLE ARRAY
passed it.**

An ingest that dies after `attach_raw_file_headers` and before the sample-level writes —
reached by **2 of 3 real credential expiries**, not contrived — leaves a store missing
the **D1** and **D-0047** mitigations entirely. Measured, before the fix:

| store | P1 | P2 | P3 | P4 | P5 | verdict |
|---|---|---|---|---|---|---|
| baseline | PASS | PASS | PASS | PASS | PASS | EQUIVALENT |
| `amplitude_raw_ibm32` deleted | PASS | PASS | PASS | PASS | PASS | **EQUIVALENT** |
| `headers_raw_uint8` deleted | PASS | PASS | PASS | PASS | PASS | **EQUIVALENT** |
| **`cdp_x` deleted** | PASS | PASS | PASS | PASS | PASS | **EQUIVALENT** |
| **`time` deleted** | PASS | PASS | PASS | PASS | PASS | **EQUIVALENT** |

### I wrote two of those rows this morning

**The last two are mine**, introduced hours earlier in D-0059, the fix for the *previous*
audit. That entry says, approvingly:

> *"Absent or underivable is NOT CHECKED, never checked-and-passed — the discipline the
> raw legs already use."*

**That sentence is the defect.** `NOT CHECKED` is only honest if something downstream
refuses to certify on it. Recording it in evidence while the verdict still reads
`EQUIVALENT` **is** checked-and-passed, wearing an honest label. I inherited the pattern
from the raw legs, reproduced it faithfully, and reproduced the hole with it — the fourth
instance of the **D-0049** vacuity class, and I authored the third and fourth.

### The rule now, and where each requirement lives

Ruled by the maintainer: **extend the planes**, no sixth plane, no new gate.

| plane | requires | predicate |
|---|---|---|
| 3 (G2c) | `headers`, `cdp_x`/`cdp_y` | the **store's own** `coordinates` attribute |
| 4 (G2d) | the sample axis, `amplitude_raw_ibm32` | axis from `dimension_names`; raw view **iff the decode is lossy** |
| 5 (G2e) | `trace_mask`, every grid dimension array | `dimension_names` |

**`headers_raw_uint8` is deliberately NOT required.** Plane 3's claim is that the 240
bytes are **recoverable**, and G1 guarantees the structured array covers all 240 with no
gaps — so the claim holds with or without the portable copy. It is a **portability**
mitigation, not a recoverability one. Requiring it failed seven prestack geometries that
were entirely correct. Its control was **deleted rather than kept**: a control that fails
nothing is not a control. Tracked as **D40**.

### Three predicates I got wrong first, each caught by running it

1. **Required `headers_raw_uint8` unconditionally** — broke seven prestack geometries
   built by upstream `segy_to_mdio`, which legitimately carry none.
2. **Keyed coordinate arrays off the SOURCE header** — every rev-1 header declares
   `cdp_x`, but a shot-indexed template creates no CDP arrays, so four more geometries
   failed. The right predicate is the **store's** `coordinates` attribute, which
   **survives the deletion of the array it names** — exactly the property a completeness
   check needs: *a claim that outlives its content.*
3. **Attached the mitigations unconditionally in the latency probe** — `attach_header_plane`
   raises on the two geometries whose grid is sized along `shot_index`, a dimension MDIO
   calculates and writes no coordinate array for. That is F7, already known, and both
   already carry `PRECONDITION: False`.

### After

| store | P1 | P2 | P3 | P4 | P5 | verdict |
|---|---|---|---|---|---|---|
| baseline | PASS | PASS | PASS | PASS | PASS | EQUIVALENT |
| `amplitude_raw_ibm32` deleted | PASS | PASS | PASS | **FAIL** | PASS | NON-EQUIVALENT |
| `cdp_x` deleted | PASS | PASS | **FAIL** | PASS | PASS | NON-EQUIVALENT |
| `time` deleted | PASS | PASS | PASS | **FAIL** | PASS | NON-EQUIVALENT |

**G7 is 14 controls**, each failing exactly its declared set, zero extra, zero missed.
Two are new: `deleted_raw_ibm32_array` → `{G2d}`, `deleted_derived_coordinate` → `{G2c}`.

### A test was asserting the defect

`test_an_absent_view_is_reported_as_unchecked_not_as_a_pass` — **its own name said
`NOT_RUN` is not a pass, and the assertion underneath made it one.** `assert
plane.status == "PASS"`. Renamed and corrected. That is the second test found this week
pinning a claim that had become false, after `test_certify_still_documents_the_g7_ceiling`.

### Two pre-registered readings moved, and both are kept

**P7 prestack**: Plane 4 moved `PASS` → `FAIL` on four geometries. **The stores did not
change; the engine got stricter.** They are built by upstream `segy_to_mdio` because
SDIP's ingest cannot express these geometries (**D25**), so an `ibm32` store arrives with
no raw view and its original bits are **unrecoverable**. The new `FAIL` says something
true the old `PASS` did not. Both readings are recorded; neither overwritten (**SP10**).

**P7 latency**: its precondition is `planes_all_passed`, so it went un-runnable. **Fixed
by completing the fixture, not by weakening the precondition** — the probe now attaches
what `sdip.ingest.ingest` attaches, so the benchmark runs against the artefact SDIP
actually ships. All 63 latency tests pass and the figures stand.

**Suite: 1075 passed.** ruff and mypy clean on 45 modules.

---

## D-0062 — 2026-08-23 — **`ibm32` is one lossy format of six.** MDIO decodes everything to `float32`

Second external audit, verified here before acceptance.

**Root cause, read directly:** `mdio/builder/templates/base.py:449` sets
`data_type=ScalarType.FLOAT32` **unconditionally**, in the base template every other one
inherits; and `segy/file.py:235-239` sets `trace.data.format` from the file's own
`data_sample_format` byte. So the decode is always `<file format> → float32`, and
losslessness turns **only** on the 24-bit significand: every integer to `2**24` exactly,
none beyond.

**Swept over every code the pinned `segy` can express:**

| code | format | verdict | first loss |
|---|---|---|---|
| 1 | ibm32 | **LOSSY** | P2: 1,939 of 4,103 |
| 2 | int32 | **LOSSY** | `-16777217 → -16777216` |
| 3 | int16 | exact | |
| 5 | float32 | exact | identity |
| 6 | float64 | **LOSSY** | `0.1 → 0.10000000149011612` |
| 8 | int8 | exact | |
| 9 | int64 | **LOSSY** | `-16777217 → -16777216` |
| 10 | uint32 | **LOSSY** | `16777217 → 16777216` |
| 11 | uint16 | exact | |
| 12 | uint64 | **LOSSY** | `16777217 → 16777216` |
| 16 | uint8 | exact | |

**Six lossy, five exact.** The audit tabulated eight formats and four lossy; there are
**eleven**, and **`uint64` (code 12) is a sixth** it did not list, with `uint16`/`uint8`
exact.

**The threshold is the fact; a loss ratio is not.** How many values a file loses depends
entirely on the values in it — the audit measured int32 at 4/8 with a sign inversion to
`-2147483648`, I measured 3/8 with a clamp. Both are artifacts of the chosen vector.
`LOSSY_DECODE_FORMATS` therefore records **which formats can lose and the `2**24`
boundary**, never a ratio.

**Measured end to end** on a real int32 SEG-Y through SDIP: `detect_ibm32 →
sample_format=None`, no `amplitude_raw_int32`, values altered, and **`plane_4` FAIL with
20 mismatches**. *The engine detects the loss but does not diagnose, declare, or preserve
it* — `transforms_declared` would be empty for a transform that altered values, the same
**SP1(a)** class as D-0040.

**Landed here:** `LOSSY_DECODE_FORMATS` and `EXACT_DECODE_FORMATS`, and Plane 4's raw-view
requirement keyed to the **lossy set**, not to `ibm32` alone — so an int32 store missing
its raw view already fails today. **The rest of the generalisation is not done**:
`detect_ibm32` still detects only ibm32, no format-parameterised raw view is written, and
`ibm32_blocks_equivalence` still triggers on ibm32 alone. Raised as **D41**.

**Coverage gap, confirmed:** `DataSampleFormatCode` has **no code 4** (fixed-point with
gain), **7** (24-bit int) or **15** (24-bit unsigned). Those fail at spec construction
rather than corrupting — P6's coverage claim should say so rather than imply it.

---

## D-0063 — 2026-08-23 — **Scope ruling for public release: fail-safe honesty over full coverage**

Maintainer ruling, received after independent verification at HEAD `e1bf7cb`. **The
organizing principle: fail-safe honesty is release-blocking; coverage is demand-driven.
Nothing gets built for a file that does not exist yet.**

### Independent verification, banked

The steward re-ran the deletion and corruption tables rather than accepting the report:

| check | P1 | P2 | P3 | P4 | P5 |
|---|---|---|---|---|---|
| `cdp_x` value corrupted | PASS | PASS | **FAIL** | PASS | PASS |
| `time` value corrupted | PASS | PASS | FAIL | **FAIL** | PASS |
| `cdp_x` array deleted | PASS | PASS | **FAIL** | PASS | PASS |
| `time` array deleted | PASS | PASS | PASS | **FAIL** | PASS |
| `headers_raw_uint8` deleted | PASS | PASS | PASS | PASS | PASS |

Tier-1 confirmed closed. The **D40** asymmetry reproduces exactly as described.

**Test-count discrepancy resolved:** 1,075 here against 1,056 in the audit environment.
The difference is **exactly 19**, the whole of `tests/integration/test_p4_crossimpl.py`,
which is `pytest.importorskip("tensorstore")`-gated. `tensorstore` is a **dev-only**
dependency — the runtime tree is licence-scanned and must not grow — so a checkout
without the dev group collects 1,056. Nothing is environment-dependent about the
gates themselves.

### The rulings

**1. D41 is split.** Release-blocking are legs **1 and 3** only: `detect_lossy_decode`
returning format plus loss class for all six lossy formats, a `transforms_declared` entry
for **every** decode including exact ones (**SP1(a)**), and
`lossy_decode_blocks_equivalence` generalising the escape-hatch block. Certificate-side
and cheap.

**Leg 2 — format-parameterised raw views beyond `ibm32` — is NOT release-blocking.**
Current behaviour is already **fail-safe**: a lossy non-`ibm32` source fails Plane 4 and
nothing can make it pass. After leg 1 it fails **with a diagnosis**.
**`NON-EQUIVALENT`-with-named-cause is the supported outcome** for
`int32`/`uint32`/`int64`/`uint64`/`float64` at v0.1. Raw views for them are built only
when a real file arrives, each with its G7 control in the same commit. *Every raw view is
permanent maintenance for formats rare in the wild; `ibm32` is the one that matters and
it is done.*

**2. The P2 extension is pre-registered and run now** — a pure-numpy six-format sweep.
**Measurement is cheap; machinery is not.** Its result backs leg 1's diagnosis text, and
**no claim is made about any format without its sweep row.**

**3. D40 is ratified**, closing via a **group-level provenance attribute written
unconditionally by `sdip ingest`**. A store bearing the marker and missing
`headers_raw_uint8` **FAILS**; a foreign MDIO store without it keeps absence as
`NOT CHECKED`, verdict unchanged, and the certificate records `portable_headers: false`.
The deleted G7 control returns, conditioned on the marker. **The attribute earns its
store-format change twice**: it is also the provenance discriminator the retroactive-audit
case needs.

**4. D24 and D25 are in scope for v0.1.** Both blockers are self-inflicted — a name and a
kwarg — and prestack through `sdip ingest` is what makes the project usable beyond
poststack. Once ingest reaches prestack, view attachment comes free and P7's Plane 4
failures resolve on `ibm32` prestack sources.

**5. Declared-scope release. v0.1.0 as a GitHub tag; no PyPI** until external demand or
F8 — **PyPI is a support commitment, not a checkbox.** The README gains a
supported/refused table, each refusal carrying a **stable reason code and no build**:
little-endian (D28), rev 2/2.1 (D6), sparsity ratio > 10 (D30), coordinate scalar 0
(D27), cloud backends (D7), and single files above a declared verification-memory
envelope. `sdip verify` **refuses above the envelope** citing the measured multiplier,
instead of the streaming refactor, which stays deferred with **D23**.

**6. Category-B closes before the tag:** D29, D26, D19. **D31 stays locked as its test.**
Category-A beyond ruling 4 does not block and is not built.

**7. Standing anti-overengineering rule, binding from here:** no new format, geometry,
endianness or backend without a real file demanding it; every admitted capability ships
its G7 control **and its refusal path** in the same change; anything unsupported
**refuses with a reason code rather than degrading**. *Coverage is earned by demand;
honesty is not optional at any coverage.*

### The lesson kept verbatim, at the steward's instruction

> **A claim that outlives its content.**

Keying completeness on the **store's own** `coordinates` attribute rather than on the
source header is the correct general shape for **every completeness check this project
will ever write**. The attribute survives the deletion of the array it names; the source
header does not know what the store chose to build.

### The tag is not an implementer step

`v0.1.0` is a **principal decision**. The STOP is after Category-B: full suite, the
real-survey chain in `local/`, then a release-readiness report — and then a ruling.

---

## D-0064 — 2026-08-23 — **D40 closed.** A store now says who wrote it

Closes **D40** by the mechanism ruled in **D-0063 ruling 3**: a group-level provenance
marker written unconditionally by `sdip ingest`.

**What absence means depends on who wrote the store.** That is the whole of it. A missing
`headers_raw_uint8` in a store SDIP wrote is a **partially written store** — probe P8
reached exactly that state through a real credential expiry. The same absence in a
foreign MDIO store is **nothing at all**; it was never going to have one. Requiring the
array unconditionally was the obvious fix and it was measured wrong: **seven prestack
geometries that were entirely correct failed**, because SDIP's ingest cannot express
those geometries (**D25**) and their stores come from upstream `segy_to_mdio`.

**The marker declares what the writer ALWAYS attaches, not what is present.** A list of
what is present would be a tautology — it could never disagree with the store. The
completeness check compares the *declaration* against what is on disk, and a difference
is a partial write.

**On the root group, and that is load-bearing.** The attributes describing the header
plane live on the header plane, so they are deleted with it: a marker that vanishes with
the thing it vouches for cannot detect the thing's absence. This one survives the
deletion of every array beneath it — **the same shape as the `coordinates` attribute
Plane 3 keys on, and for the same reason. A claim that outlives its content.**

**Written last in the ingest, deliberately.** An ingest that dies midway therefore leaves
**no marker at all** rather than a marker promising arrays that were never written — P8's
failure mode, inverted.

**It earns the store-format change twice**, as the ruling notes. The second job is
retroactive audit: a store found on disk years from now names the SDIP that wrote it and
the upstream pins in force. A pin bump invalidates every certificate issued under the
previous pin (§3.3), and without this there is no way to tell from the artifact alone
which side of a bump it came from.

**Measured:**

| store | P3 | why |
|---|---|---|
| marked, plane deleted | **FAIL** | the writer declared it always attaches this |
| **same store, marker removed** | **PASS** | foreign store, absence is `NOT CHECKED` |

The G7 control returns as `deleted_raw_header_plane` → `{G2c}`. **15 controls**, each
failing exactly its declared set. `portable_headers` is recorded on every certificate
**including when false**, so a reader sees it rather than inferring it from an absent
field.

### The third test found asserting the defect it was named for

`test_an_absent_plane_is_reported_as_unchecked_not_as_a_pass` read *"`NOT_RUN` is not a
pass"* and asserted `plane.status == "PASS"` — after
`test_an_absent_view_is_reported_as_unchecked_not_as_a_pass` and
`test_certify_still_documents_the_g7_ceiling`. **The pattern is worth naming: a test that
states a principle in its name and contradicts it in its body passes forever and protects
the bug.** It now asserts both halves — marked fails, unmarked passes — because only the
pair shows the check is conditional rather than merely strict.

---

## D-0065 — 2026-08-23 — **D24 and D25 closed.** Prestack is reachable through SDIP's own API

**Both blockers were self-inflicted, exactly as D-0063 ruling 4 says: a name and a
kwarg.** Seven geometries produced seven refusals from SDIP's API while upstream
converted all seven — probe P7 leg 2 proved the format was never the obstacle.

**D25:** `ingest()` now forwards `grid_overrides` to `segy_to_mdio`. **No default is
supplied**, deliberately: an override changes what the store *contains*, not merely
whether it can be written, and a grid this tool chose is not one anybody declared — the
same reasoning as G5's ceilings (**SP9**).

**D24:** a §6.4 alias override supplies the template's field names. A new
`rev1-cdp-offset-alias.toml` declares both, because the 2-D template binds both and an
override should be a complete declaration rather than a partial one.

**Measured, through `sdip ingest` itself:**

| geometry | ingest | P1 | P2 | P3 | P4 | P5 |
|---|---|---|---|---|---|---|
| `cdp_offset_3d` | **OK** | PASS | PASS | PASS | PASS | PASS |
| `cdp_offset_2d` | **OK** | PASS | PASS | PASS | PASS | PASS |
| the other five | refused | — | — | — | — | — |

**Plane 4 PASSES here where it FAILS in `PLANE_OUTCOMES`, and that difference is the
whole value of closing these.** The probe's stores are built by upstream `segy_to_mdio`
and carry no undecoded parallel view, so an `ibm32` source has unrecoverable bits
(D-0061). A store **SDIP ingested** carries the view because `ingest` attaches it.
**Reaching prestack through SDIP's own API is what makes prestack certifiable rather than
merely convertible.**

### Two of seven, and the boundary is a fact about the standard

`offset` and `cdp` are the standard's own words for bytes **37** and **21** — an alias
supplies a label and nothing else, and G1 is re-asserted after it applies, so a
declaration narrower than what it displaces would uncover a byte and fail.

`cable`, `channel`, `gun`, `sail_line`, `receiver` and `shot_line` are **not rev 1 fields
under any name**. There is no byte to alias, so no override can conjure them; they need a
real survey whose own spec declares them. **Per ruling 7, none is built until such a file
exists.** The boundary is asserted as a test, not assumed: if any of those six ever
becomes a rev 1 field, it fails.

---

## D-0066 — 2026-08-23 — **D35 narrowed, not closed.** The worker's warning is now text on the certificate; the object is still gone

**Decision.** `recovering_worker_stderr()` duplicates file descriptor 2 into a pipe for
the duration of an ingest and runs a drain thread that copies every byte straight back to
the real descriptor, scanning the stream for lines in `warnings.formatwarning`'s shape.
Recovered lines land in a **third list**, `stderr_recovered[]`, never merged with
`observed[]` or `logged[]`. The ledger's scope block gains **booleans** so a consumer can
test for the remaining gap instead of reading for it.

### What was measured, before deciding anything

Probe: `local/d26_worker_warning_probe.py`, three legs, one fixture. Fixture is the
30-trace poststack article (5 × 6 × 32) with **all 960 sample words** overwritten with
`0x61800000` — 0.5 × 16³³ ≈ 2.7e39, past float32's 3.4e38 ceiling. N = 1 fixture, 960
words, 3 ingests. Binding pins, `multidimio` 1.2.1 / `segy` 0.6.0, Python 3.12.

**Leg 1 — baseline, the gap reproduced end to end:**

```
planted overflow words   : 960
inf on disk              : 960      finite on disk: 0
ledger.observed          : 0        ledger.observed matching "ibm2ieee": 0
ledger.logged            : 1        (coordinate-unit notice, mdio.ingestion.segy.coordinates)
```

Every sample in the store was destroyed and the SP6 evidence for it was an empty list.
Two warnings reached the terminal and nothing else — `RuntimeWarning: overflow
encountered in ibm2ieee` out of `numba/np/ufunc/dufunc.py:303`, and `UserWarning:
Warning: converting a masked element to nan` out of `pydantic/main.py:263`. **Two
libraries, one empty ledger** — the gap is structural, not a property of `ibm2ieee`.

**Leg 2 — file descriptor 2, teed:**

```
stderr bytes teed        : 1129
warning-shaped lines     : 2
    x1 [RuntimeWarning] overflow encountered in ibm2ieee
    x1 [UserWarning] Warning: converting a masked element to nan.
progress-bar bytes still present : True
```

**Leg 3 — the seam search, re-run against the installed source rather than inherited
from D-0046.** `mdio/segy/blocked_io.py:104` hardcodes `initializer=trace_worker_init`;
`mdio/segy/parsers.py:61` passes no initializer; `segy_to_mdio` takes
`(segy_spec, mdio_template, input_path, output_path, overwrite, grid_overrides,
segy_header_overrides)` and none of them reaches a worker; `MDIOSettings` exposes
**exactly eight** fields — `cloud_native`, `export_cpus`, `grid_sparsity_ratio_limit`,
`grid_sparsity_ratio_warn`, `ignore_checks`, `import_cpus`, `raw_headers`,
`save_segy_file_header` — two barred by §9.1 and **none a worker callback**. The workers
return `HeaderArray` and `SummaryStatistics | None`, with nowhere to carry a warning
back. **The D-0046 conclusion is confirmed: there is no public seam that makes a worker
warning into a warning object here.** A hook installed anyway is monkeypatching, §3.3.

### Why the tee is permissible where the alternatives were not

`PYTHONWARNINGS` and `sys.warnoptions` **are** inherited by a spawned child, and both were
rejected again for the same reason D-0046 gave: they change the child's *filters*, not the
*destination*. The warning still goes to the child's stderr. `PYTHONWARNINGS=error` would
additionally kill a worker on any unrelated warning — a behaviour change, not a
measurement.

Descriptor capture was rejected in D-0046 on the grounds that it "swallows the live
display for the duration of the ingest". **That objection was to a redirect. This is a
tee** — the drain thread writes every byte back to the saved descriptor before parsing it,
and leg 2 measured the progress bar still rendering. It is the same rule
`recording_log_records` already follows for `logging.lastResort`: SDIP does not leave the
process quieter than it found it. Nothing upstream is touched, nothing is monkeypatched,
no new dependency, and no barred variable.

### The four ways this is weaker than capture, recorded rather than glossed

1. **No `Warning` object** — no arguments, no `__cause__`, no stack. Four fields parsed
   out of a printed line, and the `category` is a *name*, never a class.
2. **The originating process is not recoverable from the text.** What is known is that a
   recovered line did not come from *this* process's `warnings.warn`, because
   `recording_warnings` is recording rather than emitting for the duration.
3. **It counts lines, not events.** Python's per-process `__warningregistry__` prints a
   given (message, category, module, lineno) once per worker under the default action.
   **960 overflowing words produced one line.** The line proves the loss happened; it
   does not measure it.
4. **Worker log records are still not captured.** A worker's `logger.warning` reaches the
   same descriptor via `logging.lastResort` but arrives as a bare message with no
   `file:lineno: Category:` prefix, indistinguishable from any other stderr text.

### The declaration is now machine-checkable, which was the second half of the ask

`scope` carries booleans beside the prose:

```
worker_warnings_captured                    : false   <- hardcoded, never computed
worker_stderr_text_recovered                : true
worker_stderr_bytes_scanned                 : 1129
worker_stderr_recovery_truncated            : false
worker_log_records_captured                 : false
log_records_below_effective_level_captured  : false
```

`worker_warnings_captured` is a **literal `False`**, not derived from `stderr_watched`,
and there is a unit test asserting exactly that. The failure mode being guarded against
is a later change wiring the two together and thereby claiming SP6 coverage the project
does not have. The claim and the capability ship in one commit or neither does.

`worker_stderr_text_recovered` distinguishes *nothing was printed* from *nobody was
listening* — the same distinction `LEDGER_SCOPE` exists to draw for `observed`.

### Bounded on untrusted input (§3.6)

Warning text can embed content derived from a SEG-Y SDIP did not create. Lines over
`MAX_STDERR_LINE_BYTES` (8 KiB) are copied through but not scanned, and the recovered
list stops at `MAX_STDERR_RECORDS` (1024) and sets `worker_stderr_recovery_truncated`.
The realistic ceiling is workers × distinct sites, so the cap is never reached in
practice — it exists so a hostile source cannot grow a certificate without bound.

### Verification

`uv run ruff check src tests`, `uv run ruff format --check src tests` (95 files) and
`uv run mypy src` (46 files) clean. `tests/unit/test_guard_warnings.py` **37 passed**,
12 new test functions; `tests/integration/test_sp6_blindspots.py` **8 passed**, running a
real ingest per fixture. Full suite **1099 passed, 3 failed** — all three failures in
other agents' concurrent uncommitted work (`planes.py`'s new `padding_is_only_fill`,
`nonvacuity.py`'s new `fabricated_value_in_padding` control, and a new
`overrides/rev1-cdp-offset-alias.toml`), none touching `guard/`, warnings, or stderr.

**No engine check and no gate was added or changed**, so `nonvacuity.py` is untouched and
the one-control-per-gate property is undisturbed. The recovery is evidence recorded on a
certificate, not a condition anything passes or fails — deliberately. A gate on
`stderr_recovered` would be a gate on text whose originating process is unknown.

**Schema.** `stderr_recovered` and `stderr_recovered_count` added to
`sdip-certificate-v0.schema.json` (`warnings` has `additionalProperties: false`), and the
six scope booleans are declared with `worker_warnings_captured`,
`worker_stderr_text_recovered` and `worker_log_records_captured` **required**.

**D35 stays open.** The warning object still does not cross the process boundary and no
pinned upstream seam can make it. What changed is that the ingest whose every sample
became `inf` now says so on its certificate instead of in terminal scrollback.

---

## D-0067 — 2026-08-23 — **D19 was not closed by `roundtrip_closure` existing.** Arrow ③ passed a corrupted export

**Decision.** `roundtrip_closure` gains a fourth leg: SDIP's two authoritative raw
file-header attributes are compared between the original store and the closure store by
**byte equality**, and the result is ANDed into `ClosureResult.passed`. A new G7-style
negative control, `closure_control`, ships in the same change and is required to fail
closure **through that leg and no other**.

### What was actually open

`OPEN_DEBTS.md` **D19** asked for the exported SEG-Y to be validated *as an artifact in
its own right*, and named the closure: re-ingest the export and verify (a) the five
planes against the resulting store and (b) that its arrays match the original store's.
`roundtrip_closure` did exactly that, `sdip certify` called it, and `release_readiness`
already treated a missing or non-PASS result as blocking. On the face of it the debt was
built.

It was not. **The check passed a corrupted export.**

### The measurement

30-trace synthetic poststack fixture (`tests/fixtures/generators/poststack3d.py`,
seed 20260822), rev 1, `PostStack3DTime`, 11 arrays, ingest → export byte-identical
(G3 PASS). One bit flipped in the exported file, one variant per run — **N = 7 corrupted
variants plus the clean baseline**:

| Flipped byte (0-based file offset) | What it is | Closure verdict *before* | Detected by |
|---|---|---|---|
| — (clean) | — | **PASS** | — |
| 64 | textual header | FAIL | missing-array rule, *incidentally* |
| 3199 | textual header, last card byte | FAIL | missing-array rule, *incidentally* |
| 3221 | binary header byte 22 (`samples_per_trace`) | FAIL | re-ingest refused, `UntrustedInputError` |
| **3300** | **binary header byte 101 — unassigned** | **PASS** | **nothing** |
| **3450** | **binary header byte 251 — unassigned** | **PASS** | **nothing** |
| 3600 | first trace-header byte | FAIL | arrays `headers`, `headers_raw_uint8` |
| 3840 | first sample byte | FAIL | array `amplitude_raw_ibm32` |

Two exports whose **400-byte binary file header differed from the store's** closed
cleanly. §4.3 makes those raw bytes *authoritative on conflict*. They were not compared.

### Why, and why it is structural rather than a slip

Two facts compose into the hole.

**The five planes in closure are a self-consistency leg.** They run *export* against the
store built *from that export*. Whatever the export says, the closure store faithfully
carries — so Plane 1 and Plane 2 report `PASS` on a corrupted header exactly as readily
as on a clean one. That leg cannot, by construction, disagree with the export about
anything. It establishes that the file parses gap-free and survives an ingest, which is
worth having and is not what D19 asked for.

**The only cross-check against the original walked `group.arrays()`.** SDIP's raw file
headers are **not arrays**. MDIO writes the raw binary header only behind
`MDIO__IMPORT__RAW_HEADERS`, which §9.1 bars, so SDIP captures the 3600 bytes itself and
stores them as base64 **attributes** (D-0021). `zarr`'s `Group.arrays()` does not yield
attributes, so nothing read them.

The consequence, stated plainly: **in the `ROUNDTRIP-SCOPED` regime arrow ③ exists for,
two of the five planes were checking nothing at all.** The textual half looked covered
only by luck — a flip breaks the EBCDIC decode, the ingest falls back to the header-less
shape (D-0055), and the missing-array rule fires on the vanished variable. Detection by
luck is not detection; byte 3300 has no such side effect and sailed through.

### Why a function existing is not a debt discharged

This is the second time on this project that reading code has agreed with a debt while
running it disagreed. The general form is worth recording: **a check is closed by the
corruption it rejects, never by the code it contains.** `roundtrip_closure` mentioned
every noun D19 used — re-ingest, five planes, every array — and still let the artifact
through. Nothing short of running a corrupted export past it would have said so, which is
exactly what §5 requires and exactly what had not been done: **closure had no negative
control.**

To be precise about the scope of that, since the tempting overstatement is wrong: G4, G5
and G6 have no negative controls either. That is not the same omission. §7 G7 names
exactly G2a–G2e and G3 as the gates it audits, so those three sit outside G7's declared
remit by specification. Closure did not — it is an **equivalence check that decides
whether a measured artifact is sound**, which is precisely the category §5's rule covers,
and it was the only one of those with nothing corrupted at it. Whether G4/G5/G6 should
acquire controls is a separate question and is not settled here.

### What was built

1. **`_compare_file_headers`** in `src/sdip/equivalence/closure.py`. Byte equality on
   `sdipRawTextHeader` and `sdipRawBinaryHeader`, one reader per attribute — never a
   reader that loads both, for D-0028's reason: a shared reader made a textual defect
   fail Plane 2, and a check that fires on someone else's corruption cannot localise a
   fault. An attribute present in one store and absent from the other is a **failure**;
   "could not read it" must never resolve to "skipped, therefore matched".
2. **`ClosureResult.passed`** requires `len(file_headers) == len(FILE_HEADER_ATTRS)` — a
   count, not a truthiness test, so a leg that quietly stopped comparing one of the two
   headers cannot pass for one that compared both (**SP11**).
3. **`closure_control`** in `src/sdip/equivalence/nonvacuity.py`, appended beside
   `g3_control` and following it: closure judges a *file* against a store, so its control
   corrupts a file. It flips byte **3300** of a **copy** under `workdir` and leaves the
   export untouched — verified by hash rather than asserted.
4. **`tests/negative/test_closure_control.py`** — 14 permanent controls, including
   `test_closure_passed_the_corruption_before_the_file_header_leg`, which keeps the
   pre-fix verdict as an executable record.

### The offset is chosen so that only the leg under test can fire

Byte 3300 is **binary-header byte 101**. Measured against the pinned `segy` 0.6.0, not
read off a standards document: byte 101 falls in no declared field of the revision **0**,
**1** or **2** binary-header specification (27, 30 and 44 fields, last ending at bytes 60,
306 and 332; byte 101 sits in a gap in all three). It moves no parsed field, no sample
format and no trace length. So the corrupted export still re-ingests, G1 still passes,
all five planes still hold, and every array still matches — and the control asserts all
of that, then asserts that `differing_file_headers == ["sdipRawBinaryHeader"]`.

**That is §7 G7's "and ONLY that gate", transposed from gates to closure's legs**, and it
is the assertion that stops the control going vacuous. A control that asserted only
*"closure FAILed"* would keep passing if the file-header leg were deleted and some
unrelated leg happened to catch the flip. This one starts failing the moment the leg it
targets stops carrying the verdict. The textual attribute is asserted **unchanged** in
the same breath, for D-0028's reason.

### On the overlap with G3, which is real and is not a defect

A flipped export byte also changes the whole-file hash, so **G3 fails on this corruption
too** whenever the round trip was byte-identical. The control declares `must_fail:
["roundtrip_closure"]` and records the overlap on
`g3_also_fires_when_byte_identical` rather than hiding it.

The overlap is not a reason to call closure redundant, and the direction matters. In the
regime closure exists for — a non-conforming source where byte-identity was never
possible — **G3 is already `ROUNDTRIP-SCOPED` before anyone corrupts anything.** It
returns the same verdict for a clean scoped export and a mangled one, so it discriminates
nothing at all. That is the whole of D19's argument and the reason arrow ③ is a separate
arrow in D-0031.

### Cost

One additional re-ingest of the export per `certify`. Measured on the 30-trace fixture:
closure 2.19 s, `closure_control` **2.14 s**, against 12.78 s for the source ingest and
1.77 s for all 16 G7 controls. The clean closure run is **passed in** as the control's
baseline rather than recomputed — `g7` refuses to interpret controls against a dirty
baseline and this does the same, but re-running a check to learn an answer already on
hand is exactly the waste D18 was about. That halves the addition: one extra ingest, not
two.

Scaling is one ingest of the export, so it tracks survey size linearly and will need the
same scrutiny D18 gave G7 when P3 sets a scale ceiling. Recorded rather than pre-empted.

### What this does NOT do

**It does not gate.** `release_readiness` blocks on `roundtrip_closure.status`, so the
new leg gates automatically — a corrupted export now blocks release, which it did not
before. But the **control's own verdict** rides on the certificate under
`nonvacuity.closure_control` and is not consulted by `release_readiness`, exactly as
`nonvacuity.g3_control` is not. A `certify` run whose closure control came back `FAIL` —
meaning closure has been shown *incapable of failing* — would still report
`release_ready: true` if everything else passed. **That is a hole of the same shape as the
one this entry closes**, one level up, and it is left open deliberately: `release_readiness`
is the release gate, changing what it blocks on is a change to the gates, and the operating contract
§9 requires that to be a maintainer decision rather than a side effect of closing D19. It
is raised in `OPEN_DEBTS.md` as **D42**, beside D19's closure entry.

It also does not touch `verdict_for`. An `EQUIVALENT` verdict has never depended on
closure and still does not.

---

## D-0069 — 2026-08-23 — **D29 closed.** Padding is now verified as padding

**Measured first**, on a ragged grid with 18 real padding cells:

| array | padding fill | ambiguous by value? |
|---|---|---|
| `amplitude` | `NaN` | no |
| `cdp_x`, `cdp_y` | `NaN` | no |
| `headers.*` (structured int) | **`0`** | **yes** |
| `headers_raw_uint8` | **`0`** | **yes** |

**SDIP cannot give an integer dtype a `NaN`.** There is no such value, so the ambiguity
between a padding zero and a measured zero is not fixable in the store's dtype. What was
fixable is the thing **SP12 actually asks for**:

> *any value in an output that did not come from the source is a defect. Grid padding is
> not data and must be excluded by the live mask.*

Padding was **excluded** from every comparison — correctly, it has nothing to compare
against — and therefore **nothing could catch data appearing there.** Plane 5 now asserts
that every cell no source trace maps to holds the **declared fill and nothing else**. Not
a comparison against the source; the weaker checkable claim that nothing was
**fabricated**.

The certificate records, per array, the fill and whether it is ambiguous by value, so a
downstream reader can see that `trace_mask` is the authoritative liveness signal rather
than infer it.

### The control, and why it needed a new outcome

`fabricated_value_in_padding` writes a real-looking sample into a dead cell. **It is
invisible to Planes 3 and 4 by construction** — both iterate the trace map, and a padding
cell is not in it.

**It cannot run on a full grid**, and neither can `flipped_raw_ibm32_word` on a store from
an exact sample format. Both previously raised, which G7 scored as a control that *failed
to apply* — so G7 would have failed on any full-grid store. That was a latent defect in
the existing `ibm32` control too, hidden only because every fixture happened to be
`ibm32`.

Added `ControlNotApplicableError`: **not a pass, not a failure, and always counted.** The
G7 result carries `controls_applied` and `controls_not_applicable` **with names and
reasons**, and the summary line names them. *A control that is never applicable anywhere
would otherwise be indistinguishable from one that passes* — which is the vacuity SP11
exists to catch, one level up again.

**Non-vacuity proven on both halves**, because only the pair shows the control is real:

| fixture | outcome |
|---|---|
| ragged grid (has padding) | **fires**, declared `{G2e}`, observed `{G2e}` |
| full grid (no padding) | **not applicable**, named, reason recorded |

**16 controls. Suite: 1118 passed.**

---

## D-0070 — 2026-08-23 — Declared scope: a supported/refused table, and a refusal above the memory envelope

**D-0063 ruling 5.** Two halves of one idea: **say what is supported, and refuse the rest
with a code rather than degrading.**

### The envelope refusal

The verification path fully materialises, so peak RSS is **linear in file size** —
`RSS_MB = 214.7 + 7.73 × source_MB`, **R² = 0.99997** (D-0060). Above the envelope the
process is **OOM-killed**, and the operator gets **no verdict at all**.

**A tool that dies is worse than a tool that declines**, because a death leaves nothing
to read. `sdip verify` now refuses above a declared envelope, **before any read**, on the
file's size alone — the same fail-before-you-allocate rule as §3.6.

**The default is 1.0 GiB, chosen UNDER a range the measurements do not agree on.** D-0060
bracketed the breach of a declared 8 GiB ceiling between **1,083 MB** (synthetic fit) and
**1,393 MB** (anchored on the one real survey point). *A default set inside a range where
two measurements disagree would be a guess wearing a number.*

**The projection is used as the conservative side of a bracket, never as a point
estimate.** It over-predicts the single real measurement by ~32 %, and that direction is
the safe one: an under-prediction would let a file through that then OOMs, which is the
exact failure this prevents. A test pins that direction.

**There is no clamp.** `--envelope-gib 0` disables the check entirely, because an
operator who knows their machine has the memory may say so, and the number they pass is
recorded. Refusing is not a dead end and the message names the escape hatch.

Verified against the real 494 MB survey: `--envelope-gib 0.1` exits **1** with
`SDIP-E-ENVELOPE`, cites the measurement, projects 3.9 GiB, and emits **no traceback**.

### The table

`README.md` gains supported and refused sections. **Every refusal carries a stable reason
code so a caller can branch on the code, not on prose.**

**The most important row is the one that is not a refusal.** `int32`, `uint32`, `int64`,
`uint64` and `float64` are **not refused** — they certify **`NON-EQUIVALENT` with a named
cause**. The decode to `float32` can alter the value (P9), no undecoded view is written
for them, so Plane 4 fails and *nothing can make it pass*. **That is fail-safe, and since
D-0062 it is diagnosed rather than silent.**

That row is the shape of every future gap: a capability is admitted **when a real file
demands it**, and every admitted capability ships **its G7 control and its refusal path
in the same change** (ruling 7). Until then the honest outcome is a **named** failure,
not a plausible one.

---

## D-0071 — 2026-08-23 — Process slip: a directory-scoped `git add` swept in an unreviewed agent file

**Recorded because D-0033 already recorded its sibling and this is the same failure in a
milder dress.**

D-0033 was `git add -A` sweeping 497 unreviewed lines into a public commit. The remedy
adopted then was *stage explicitly, never `-A`*. Commit `681de32` staged
`git add -- ... tests/` — a **directory**, not `-A` — and swept in
`tests/negative/test_closure_control.py`, written by a running agent, which I had not
read at the time.

**No harm resulted**: the file is sound, its 14 tests pass, and the finding behind it
(D-0067) is strong and has since been reviewed. **That is luck, not process.** The
content was not checked before it was published to a public repository, which is the
whole thing D-0033 exists to prevent.

**The lesson is narrower than "stage explicitly" and worth stating exactly:** a
directory-scoped `git add` is not explicit staging when agents are writing into that
directory concurrently. *Explicit means named paths, or a `git status` read immediately
before staging.* The rule as written passed while its purpose failed.

Not corrected by a revert — the content belongs in the tree and reverting would lose a
real test. Recorded so the next reader sees that the discipline slipped and how.

---

## D-0072 — 2026-08-23 — **D42 closed.** A recorded control that nothing reads is not an audit

Maintainer-authorised. **D42 correctly stopped at §9** — `release_readiness` is the
release gate, and changing what it blocks on is a gate change, not a side effect of
closing a debt.

### The hole

`release_readiness` read `gates`, `planes`, `roundtrip_closure`, the lossy-codec flag,
the transform block and the tree state. It **never read** `nonvacuity.g3_control` or
`nonvacuity.closure_control`.

Both controls corrupt an **exported file** and require a check to catch it. A control
reporting `FAIL` therefore means the check it audits **has been shown incapable of
failing** — the precise definition of a vacuous check under **SP11**. A certificate could
carry `g3_control: FAIL` beside `G3: PASS` and still report `release_ready: true`.

**The gate and its own audit could disagree, and the release criterion sided with the
gate.**

### Why these two and not G7's

G7's controls need no clause: **G7 is a gate**, it is in `GATES`, and it is already
blocked on. These two live outside G7 because each needs a corrupted **export file**
rather than a corrupted store, so they cannot share its machinery — **and that is exactly
how they came to be recorded and never read.** The mechanism that made them necessary is
the mechanism that made them invisible.

### Absent blocks too

A missing control blocks as loudly as a failing one. `NOT_RUN` is not a pass — the lesson
three separate tests in this repository had to relearn, each having stated it in its own
name while contradicting it in its body.

### What is deliberately NOT required

**G4, G5 and G6 have no negative controls at all, and this change does not demand any.**
§7 G7's declared remit is G2a–G2e and G3, so those three sit outside it **by
specification**. Blocking on controls that do not exist would be inventing a requirement
the spec never made — and it is asserted as a test, so the boundary is pinned rather than
remembered.

### The test module proves itself first

Five tests each remove exactly one thing and assert it blocks. **A sixth asserts the
baseline is genuinely ready** — because without it, all five would "pass" against a
function that refused everything, and the module would assert nothing at all. That is the
same discipline the G7 controls are held to, applied to the tests of the release gate.

---

## D-0073 — 2026-08-23 — **First real-survey chain with everything in. `release_ready: false`, and two of the three blockers were mine**

The run that counts: commit `5cd2b98`, clean tree, 494,565,408 bytes, 116,532 traces.
**Every Category-B fix executing together for the first time.**

### Result

| | |
|---|---|
| **Planes 1–5** | **PASS** — all five |
| **G1 G2 G3 G4 G6 G7** | **PASS** |
| **G5** | **FAIL** — wall clock **1,168.5 s** against the declared **900 s** |
| Round-trip closure | **PASS** — export re-ingests, five planes hold, both raw file headers and all 11 arrays identical |
| `closure_control` | **PASS** — caught by the `file_headers` leg **and no other** |
| G7 | **PASS** — 15 corruptions each failing exactly its declared set; 1 not applicable (`fabricated_value_in_padding`, full grid) |
| Peak RSS | **3.50 GB** against the declared 8.59 GB — **no breach** |
| `worker_stderr_text_recovered` | **`true`** — D26's ratification condition is **met** |
| `portable_headers` | `true` |
| **`release_ready`** | **`false`, 3 blocking** |

### Blocker 1 — G5, and it is real

**The engine got more expensive and the ceiling did not move.** The 900 s was
pre-registered in `P3-scale.md@9904bec` when the chain ran **10** G7 controls and closure
did not re-ingest. It now runs **16** controls — each copying touched arrays and re-running
five planes over 116,532 traces — plus a closure re-ingest added by D19's fix.

**The ceiling is not being raised now.** Choosing a threshold after seeing the result it
judges is exactly what **SP9** forbids, and *"gates never bend in either direction"* is the
sentence. A larger ceiling needs a **new pre-registration committed before the re-run**,
stating the new control count as the reason. **Memory was never the problem** — 3.50 GB
against 8.59 GB, a 59 % margin.

### Blockers 2 and 3 — a defect I introduced in the D42 fix, six hours old

`g3_control NOT_RUN` and `closure_control NOT_RUN` — **on a run where the log shows both
controls executing and passing.**

`release_readiness` is computed **inside** `issue()`. The CLI attached both controls to
the payload **after** `issue()` returned. So the clause I added yesterday to make the
release gate consult them **could never see them**, on any certificate, ever. It reported
`NOT_RUN` and blocked — **fail-safe, and permanently blocking, which is its own kind of
broken.**

**This is D-0072's own lesson, landing on D-0072's own fix.** The standing law reads:
*any check that cannot share the standard control machinery gets an explicit consultation
path in the same commit, because out-of-machinery checks are structurally invisible to
the standard audit.* I built the consultation path and **wired it to a payload that did
not yet contain them.**

Fixed: `issue()` now **takes** both controls and folds them into the `nonvacuity` block
before readiness reads it. A helper carries the reasoning so the ordering constraint is
stated where it binds.

**Six unit tests passed against this the whole time**, because they construct a payload
directly and never exercise the CLI's assembly order. *The tests were right about the
logic and blind to the wiring* — which is why the real-survey chain is the acceptance
criterion and a green suite is not.

### The environment delta, named once and closed

**1,128 in the dev environment, 1,109 in the audit environment. The delta is exactly 19:
the whole of `tests/integration/test_p4_crossimpl.py`**, gated at line 77 on
`pytest.importorskip("tensorstore")` — 3 harness-integrity tests, 9 parametrised
core-array crossings (`amplitude`, `amplitude_raw_ibm32`, `headers_raw_uint8`, `inline`,
`crossline`, `time`, `trace_mask`, `cdp_x`, `cdp_y`) and 7 header/file-header boundary
tests. `tensorstore` is **dev-only** because the runtime dependency tree is licence-scanned
and must not grow. **The two counts are one fact.**

---

## D-0074 — 2026-08-23 — **`release_ready: true`.** The first one, and nothing bent to get it

Re-run of the D-0073 chain at `2f33f3e`, clean tree, same file: 494,565,408 bytes,
116,532 traces. **`blocking: []`.** Certificate `750bcb953545-20260823T081200+0000.json`,
ledger **row 1**.

| | D-0073 | this run |
|---|---|---|
| Verdict | NON-EQUIVALENT | **EQUIVALENT** |
| `release_ready` | `false`, 3 blocking | **`true`, 0 blocking** |
| G5 | **FAIL** 1,168.5 s / 900 s | **PASS** 1,115.3 s / **1,500 s** |
| `g3_control` | NOT_RUN (invisible) | **PASS** |
| `closure_control` | NOT_RUN (invisible) | **PASS** |
| everything else | PASS | PASS |

### The two control blockers were a wiring defect, and this is their first real test

`release_readiness` is computed **inside** `issue()`; the CLI attached both controls
**after** it returned, so the clause meant to consult them could never see them. Fixed in
`ad42920` by passing them in.

**Six unit tests passed against the broken version the whole time**, because they build a
payload directly and never exercise the CLI's assembly order. **This run is the first
thing that could have caught it and the first thing that confirms the fix** — which is the
argument for a survey-scale acceptance criterion, made twice by the same defect.

### G5: the model is conservative, not wrong

P10 derived **1,518 s** from `900 × (16/10) + 78.2` and declared **1,500 s** rounded down.
The run came in at **1,115.3 s — 73 % of the estimate**, a **26 % margin**.

**The linear-in-control-count model over-predicts, which is the safe direction for a
ceiling.** P10's falsifier said a breach would mean the model was wrong; it did not
breach, so the model stands as a conservative bound rather than a fitted one.

**Run-to-run variance is now known and is worth having on the record before someone reads
noise as signal:** 1,168.5 s and 1,115.3 s on the same code path, **4.6 % apart**, on a
machine under different load. Any future move smaller than that is not evidence of
anything.

**The ceiling was not chosen to fit.** Had P10's arithmetic landed below 1,115 s, G5 would
have failed again and the entry would say so. It landed above because the derivation was
conservative — the three inputs and the arithmetic are on the face of P10 precisely so a
reader can check that rather than take it.

### Memory was never the question

**3.64 GiB of 8.0 GiB declared**, a 55 % margin, unchanged in character from D-0073's
3.50 GiB. P3's memory ceiling was left untouched through the whole recalibration because
it never breached, and **moving a limit that held would be adjusting a gate for
tidiness.**

### What this certificate does and does not say

**It says:** on *this* file — SEG-Y **rev 1**, big-endian, poststack 3-D, `ibm32` — the
conversion changed nothing, and the engine that says so has been shown capable of failing
on 15 distinct corruptions, each failing exactly its declared gates.

**It does not say** anything about rev 2, little-endian, the five other lossy sample
formats, prestack geometries beyond CDP-offset, files above the 1.0 GiB verification
envelope, or any cloud backend. Those are declared refusals with reason codes, and the
supported/refused table in `README.md` is the list.

**One certificate on one file is one measurement.** It is the measurement the project was
built to be able to make, and it is not a claim about seismic data in general.

---

## D-0075 — 2026-08-23 — Citations of the operating contract retargeted; the firewall block-lists left alone

**Maintainer instruction, before the v1.0 tag: the published repository carries the
owner's name and no assistant attribution anywhere.**

**Swept first, and the identity record was already clean.** All 47 commits across all
refs: author and committer `zahidaramai <me@zahidaramai.com>`, sole trailer
`Signed-off-by: zahidaramai`. **Zero** `Co-Authored-By`, zero generated-with lines, zero
session links. Nothing to remove there.

**What the sweep did find** was a different problem, and a real one: **eight prose
citations of an operating-contract section — `§9`, `§4.2`, `§3.2` — pointing at a file
that is never published.** A reader could not follow them. They are now *"the operating
contract §N"*: the section pointer is preserved, the unreachable filename is not.

**The firewall block-lists are deliberately untouched**, and that was a maintainer
decision. `.gitignore`, `.githooks/pre-commit`, `sdip doctor`'s unpublishable list and the
CI firewall job **must name what they block in order to block it**, and the README and
CONTRIBUTING tables document that list. Moving those patterns into an untracked config
was considered and rejected: **a fresh clone would then carry no block-list, and both the
hook and the doctor check would silently degrade to nothing** — the exact shape of D-0061,
a check that cannot fail.

**Four commit messages cite the contract by filename.** Rewriting them means
`filter-branch` and a force-push over published history: **every one of the 47 SHAs
changes**, anyone who cloned gets a broken remote, and the SHA citations inside this file
stop resolving. **Not done.** The cost is real and the benefit is a filename in four
messages.

### Why this is not an SP10 violation, stated rather than assumed

`DECISIONS.md` and `OPEN_DEBTS.md` are append-only, and eight lines in them were edited.

**SP10 exists so a record cannot be rewritten to hide what happened.** Nothing here
changes a claim, a measurement, a verdict or a decision — a citation was **re-pointed from
an unreachable filename to a readable description of the same section**. The rule's
purpose is untouched by that, and its letter is satisfied by this entry: **the edit is
itself on the record, with its count and its reason.**

Had the substitution altered what any entry asserted, the correct remedy would have been a
new entry citing the original — not an edit.

---

## D-0076 — 2026-08-23 — The steward recommended v0.1.0. The principal chose v1.0.0. Recorded, scored, not relitigated

**The steward's position:** tag **v0.1.0** — *"a v0.1.0 that provably never lies about a
rev-1 poststack big-endian file is worth more than a v1.0 that handles everything and is
spot-checked."*

**The principal's decision:** **v1.0.0**. Taken, tagged, public.

**Recorded here rather than in `EQUIVALENCE_LEDGER.md`**, despite the ruling saying
"ledger": that file's own header declares it an *"append-only index of every Equivalence
Certificate"*. A version decision is not a certificate, and filing it there would break
the boundary this project defended two entries ago when it refused to enter a probe
result as a certificate.

### Scored, with a date and a criterion

| | |
|---|---|
| Criterion | **no forced breaking change becomes necessary** |
| Score date | **2026-08-23 + 12 months** |
| If no break was forced | the principal's call was right; the steward's was overcautious |
| If a break was forced | v0.1.0 would have absorbed it at no cost to anyone |

**A disagreement with a scoring date is a measurement. One without is an opinion.**

### The consequence, named because it is immediate

**1.0 semantics make D14 urgent.** At `0.x`, parked CI reads as honest immaturity. At
`1.0`, a version that *claims* maturity, anything a badge implies but does not enforce is
a **shipped overstatement**. D14 moves to the front of the queue behind D43 for that
reason alone — the code did not change, the version's meaning did.

---

## D-0077 — 2026-08-23 — v2.0.0 is a cost, not a destination. Ruling 7 reaffirmed

**The framing correction, kept because it inverts how a roadmap is usually written:**

> **A major bump is what you pay when you are forced to break a promise v1.0.0 just made.
> You never work toward it; you avoid it as long as honesty allows. A project that
> reaches v1.47.0 without ever needing v2 is a project that made good promises.**

### The actual tag roadmap

| tag | trigger | when |
|---|---|---|
| **v1.0.1** | corrections that shipped after the tag are unfetchable | **now** |
| **v1.1.0** | an external file or user arrives — a real `int32` source (D41 leg 2), little-endian demand (D28), cloud (D7), or additive certificate fields | **unknown, possibly months.** That is the correct answer |
| **v2.0.0** | a promise breaks: certificate-schema restructure that cannot be additive, or a contract change such as a sixth plane | **not planned, hopefully never** |

**Any proposal to plan toward v2.0.0 is refused by default.** Planning toward a major
version means planning to break a promise, and there is no promise here worth breaking on
a schedule.

### Ruling 7, reaffirmed as standing law

**No capability work without an external file or user.** D41 leg 2, D38, D28, D30, D7 and
D6 remain **declared refusals with reason codes**, and each refuses rather than degrades.

**After v1.0.1 the queue is empty by design.** An empty queue is not a gap to fill. The
refused list is the more valuable half of what shipped, and adding to the supported half
without demand is how a narrow guarantee becomes a broad claim nobody measured.

---

## D-0078 — 2026-08-23 — **D43 closed.** Three amendments, two discarded, and the discards were the point

`ceiling(n) = 1350 + 44.92 × (n − 16)`, in `sdip.equivalence.scale`. **Tightens the
standing ceiling by 150 s.**

### Why it took three attempts, and why that is not waste

| | method | outcome |
|---|---|---|
| **A** | scale the prior ceiling by control-count growth | **discarded** — no floor check; would have shipped **1,150 s** |
| **B** | sum per-stage maxima, N=3, every stage timed | **discarded** — floor check caught **1,100 s** |
| **C** | measure `sdip certify` end to end, N=5 | **adopted** — **1,350 s** |

**1,150 s and 1,100 s both sit below 1,168.55 s, a run that actually happened.** Either
would have failed the next legitimate chain and been read as a performance regression in
code that had not changed. **Both were caught by guards declared before the data
existed** — A's absence of one is precisely why B added it.

### What B found that C depended on

B's floor failure was not a rounding problem. **Its three chains took 960–992 s while
`sdip certify` takes 1,115–1,169 s — a 12–22 % gap living in no stage at all.** The
harness measured the *engine*; the gate measures the *command*: cold start, git state
captured twice, codec manifest, array manifest, `portable_headers`, payload assembly,
certificate write. **Summing stages cannot reach that, however many stages you add.**
C exists because B failed informatively.

### The margin, and the SP9 line it had to stay on

**1.15, declared from D-0074** — a *published, prior* measurement of 4.6 % run-to-run
variance — **not from the runs it would judge**. Using experience to set a threshold is
how any threshold is set; using the result the threshold judges is what SP9 forbids. The
dates are checkable: D-0074 predates Amendment C.

**Confirmed afterwards rather than assumed:** spread across all five runs is
`max/min = 1.051`, against the 4.6 % the margin was built on.

### It accounts for the failure that started it

At **10 controls** the model computes **1,080.5 s**; P3 declared **900 s**. **That ceiling
was already under-provisioned when it was written** — which is why control growth broke
it rather than merely tightening it. A model that only fit today's numbers would not
have said that.

### Not a default, and there is a test that keeps it so

`sdip certify` still requires `--wall-ceiling-s`. **A ceiling this tool applies on its own
behalf is not one anybody declared**, the same reasoning that keeps G5 `NOT_RUN` without
an explicit ceiling. A test asserts `parametric_wall_ceiling` appears nowhere in the CLI,
so adopting it as a default becomes a deliberate act someone has to justify.

**Scope, so it is not over-read:** one command, one file, one machine. It is **not** a
model of a different file; D38's 1.0 GiB verification envelope is a separate limit and is
untouched.

---

## D-0079 — 2026-08-24 — Running CI locally before spending on it found three defects, one of them years-shaped

**Ran every CI job on this machine before enabling GitHub Actions.** 15 job/matrix
combinations. **Three real defects, none of which could have been seen any other way** —
because **CI has never executed a step in this repository**, so nothing in it has ever
been exercised.

### 1. A guard that failed on the correct value

`publication-readiness` ran `grep 'zahidaramai/sdip'` and errored *"repository URL
placeholder is unresolved"*. **That string was a placeholder when the guard was written at
F0, before the repository existed.** The repository was then created at exactly that name,
which **made the placeholder real while the guard kept failing on it**.

Replaced with tokens that are placeholders in every world — `\bOWNER\b`, `YOUR-ORG`,
`<owner>`, `XXX-PLACEHOLDER`, `UNRESOLVED-`. **That shape would have caught the defect
that actually bit us**: the certificate schema shipped with a literal `OWNER` in its
`$id` (D-0054). The old guard could not have.

**My first replacement was over-broad** and flagged `CONTRIBUTING.md`'s DCO example,
`Your Name <you@example.com>` — correct prose teaching contributors the format. Split:
strict tokens everywhere, `example.com` only in machine-read metadata where it would be a
real defect.

Added a check the old guard lacked entirely: **the `pyproject` Homepage must match the
actual git remote.** Non-placeholder is not the same as correct, and that is verifiable
offline.

### 2. G4's gate had never been able to arm

Subject `tests/integration/test_portability*.py` — **no such file has ever existed.** The
gate reported `NOT_RUN` permanently while **G4 was covered by 21 tests under other
names**. Re-aimed at `test_p4_crossimpl.py` with `-k 'portability or crossimpl or g4'`;
it now arms and passes.

### 3. G6's gate also never armed — and there the `NOT_RUN` is correct

Same symptom, opposite cause. `-k 'determinism or g6'` selects **zero**: `g6()` is
exercised only **incidentally** inside the full-chain certificate test. **Pointing the
gate at that would report it armed when nothing tests its subject directly**, so it was
deliberately left unarmed and its note now says why. Raised as **D44**.

**Two gates, identical from the CI summary, entirely different problems.** That is D14's
warning made concrete: a green build means *everything that exists passes*.

### On the local runner itself

**It produced two false REDs before it was right**, and a false red is as misleading as a
false green. It initially ignored `if:` conditions and ran gates CI would skip, reporting
G4 and G6 as failures. It now evaluates `steps.<id>.outputs.<key>` against captured
`GITHUB_OUTPUT`, so a skip here means a skip there.

**`doctor` fails locally and that is an artifact, not a defect** — the working tree is
dirty mid-edit, and CI checks out clean. Verified by committing and re-running.

**What this cannot catch, stated rather than implied:** it runs on **macOS**, CI runs on
**ubuntu-latest**; it uses the existing checkout rather than a fresh clone; and
`actions/*` steps are skipped entirely. **A green local sweep is evidence, not proof.**
