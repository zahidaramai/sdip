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
