# P17 — The D8 hostile corpus on a second platform: Linux in a container

> **SP9.** Committed **before** the run. The commit is local only: the workspace's top ruling
> forbids a push without the owner's command, and GeoSuite pushes under its own approval.
> Sections above the results separator are never edited.

| Field | Value |
|---|---|
| Probe | `P17` |
| Status | `REGISTERED` |
| Registered | 2026-10-31 |
| Registered by | Claude Code session, on GeoSuite's relay of owner D-216; network for the image pull and the PyPI install authorised by GeoSuite under D-222 (inbound only) |
| Blocks | nothing |
| Related debt | `OPEN_DEBTS.md` D8, residual 4 ("measured on one platform") |
| Spec clause | §11.4; operating contract §3.6 |

## Question

Do the D8 hostile corpus (37 members) and the P15 pair suite (all 223 pairs) give the same
clean outcomes on Linux as on macOS? Is the peak-RSS ceiling measured in the right unit
there?

## Why it matters

Every D8 number so far comes from one Darwin host. Two things are platform-specific:
- **`ru_maxrss`** is bytes on Darwin and kibibytes on Linux. `hostile_child.py` converts it, but
  the Linux branch has never run. A factor-of-1024 error turns the 512 MiB ceiling into either a
  formality or a permanent failure.
- **Allocator, filesystem and signal behaviour.** A crash or a hang that only Linux produces
  would be invisible.

Linux is also where most operators and CI run.

## Method

1. **Source.** `git archive` of the registration commit's tree, so the container holds exactly
   the committed files and no working-copy state. `docs/`, `local/` and `CLAUDE.md` are not in
   the archive.
2. **Image** `sdip-p17:20261031`, built from this Dockerfile (network: base pull, apt `git`,
   PyPI). The pulled base digest and `sha256(uv.lock)` go in the receipt.

   ```dockerfile
   FROM python:3.12.13-slim-bookworm
   RUN apt-get update && apt-get install -y --no-install-recommends git \
       && rm -rf /var/lib/apt/lists/*
   RUN pip install --no-cache-dir uv==0.11.17
   WORKDIR /src
   COPY . /src
   RUN uv sync --frozen
   ```

   `git` is needed because the D8 harness initialises an empty repository for `certify`'s
   clean-tree check.
3. **Run** in container `sdip-p17-run` with **`--network none`**, as CI has no network. The
   output directory is bind-mounted at `/out`. Three steps:
   - (a) `uv run pytest -p no:cacheprovider tests/negative/test_d8_hostile_corpus.py
     tests/negative/test_d8_hostile_pairs.py --junitxml=/out/default.xml`. This is the default
     selection: 37 members, plus 21 representative pairs and the pair checks.
   - (b) `uv run pytest -p no:cacheprovider tests/negative/test_d8_hostile_pairs.py -m campaign
     --junitxml=/out/campaign.xml`. These are the other 202 pairs.
   - (c) An RSS record: each of the 37 members and the positive control through the same child
     (`_run_one`), with peak RSS and outcome per member written to `/out/rss.json`.
4. **Compare** with macOS. The outcome class of each member (converted, SDIP-typed refusal,
   MDIO grid refusal) must match the recorded Darwin classification. The suite's own
   `test_the_measured_outcome_counts_are_the_ones_on_record` already asserts it.
5. **Cleanup.** After harvest, the container and the image are removed (`docker rm`,
   `docker rmi sdip-p17:20261031`). The base image is left as pulled; its digest is recorded.
   Nothing else is touched: GeoGIS and other projects run their own containers on this host.

## Pre-registered parameters

| Parameter | Value |
|---|---|
| N | 37 members + 223 pairs + the positive control |
| Platform | Linux in Docker Desktop on this host (arm64), `python:3.12.13-slim-bookworm` |
| Pins | `uv.lock` as committed (`multidimio` 1.2.1, `segy` 0.6.0), `uv sync --frozen` |
| Timeouts, ceilings | unchanged: 300 s per child, 512 MiB peak RSS |

## Falsifier

Any one of:

1. any test in (a) or (b) fails or errors;
2. on Linux, the positive control's peak RSS in (c) is outside **[32 MiB, 512 MiB]**. A
   kibibyte-as-byte error reads about 0.2 MiB; a double scaling reads about 200 GiB;
3. any member's outcome class in (c) differs from the class the Darwin suite records.

## If it fires

The failing case becomes a permanent test that runs on Linux CI. CI's `check` job is Ubuntu;
that needs confirming in the results. The defect is fixed on the branch. Anything that would
change a gate or the Equivalence Contract is stopped and asked about (§9). D8 stays OPEN.

## If it does not fire

D8 residual 4 closes for Linux on arm64 (one container, one kernel). Windows and x86-64 stay
unmeasured, and are recorded as such.

---

## Results — *appended after the run, never edited into the sections above*

| Field | Value |
|---|---|
| Run date | 2026-10-31 |
| Run commit | `38920a6` (registration), clean tree; step (a) re-run at `8c0821f` |
| Platform | Linux 6.12.76-linuxkit aarch64 (Docker Desktop), `python:3.12.13-slim-bookworm@sha256:4766d8b5…58a2`, `--network none` |
| Pins | `uv.lock` sha256 `e355c9a1…a9d7`, `uv sync --frozen`: 84 packages, `multidimio` 1.2.1, `segy` 0.6.0 |
| Receipt | `prereg/P17-receipt-2026-10-31.json`: digests, image IDs, every step's result, the per-member RSS record, deviations |
| Verdict | **FIRED on clause 1 at `38920a6`, from a defect in the measuring instrument, not in SDIP. Clean on Linux at `8c0821f`** |

### Measured at `38920a6`

| Step | Result |
|---|---|
| (a) corpus + 21 pairs | **28 failed**, 446 passed |
| (b) 202 campaign pairs | **202 passed** |
| (c) RSS record | positive control peak **364.6 MiB** (inside [32, 512] MiB); members 289.0–371.6 MiB |
| outcome classes | 28 SDIP-typed, 6 converted, 2 `GridTraceSparsityError`, 1 `GridTraceCountError`: **identical to macOS** |

All 28 failures were one test, `test_every_sdip_refusal_happens_before_upstream_sees_the_file`,
with the message *"refused from inside src, not sdip"*. The child names the package that raised
from the frame's file path, after the **first** `src`. The container's checkout is at `/src`,
so SDIP's files are `/src/src/sdip/...` and the name came out as `src`. The macOS checkout path
has no `src` above the repository, which is why the defect never showed. Step (c) classifies
the same 28 refusals as `UntrustedInputError`, raised as SDIP's own typed error.

**Clauses 2 and 3 did not fire.** The Linux `ru_maxrss` branch reads in the right unit, and
no outcome class moved.

### The fix, and the re-run

`8c0821f`: `_package_of` reads the **last** `site-packages` or `src` in the path.
`tests/unit/test_hostile_child_package_of.py` pins the container path and five others, and
keeps the old rule as its negative control: applied to `/src/src/sdip/...`, it gives `src`.

Step (a) re-run on Linux, same image, with the two changed files mounted read-only:
**481 passed, 0 failed** (the 7 new unit tests included).

### Deviations, all recorded in the receipt

1. Build 1 honoured the repository's `.dockerignore`, which keeps `tests/`, `prereg/` and
   `overrides/` out of the product image. No test ran (pytest exit 4). The build-context copy
   then had `.dockerignore` removed. `docs/`, `local/` and `CLAUDE.md` were never in the
   archive.
2. The first step (a) re-run went through `uv run`, which tried to re-sync from PyPI with no
   network. No test ran. The second re-run called `/src/.venv/bin/python -m pytest` directly.
3. The step (a) re-run mounted `8c0821f`'s two changed files over the `38920a6` tree. Step (b)
   and step (c) were not re-run: neither depends on the package name.

### Scope

- Linux aarch64 in one container on one kernel. **x86-64 and Windows are unmeasured.**
- The full suite was not run on Linux; only the D8 corpus and pair suites (and the new unit
  test). CI's `check` job runs the full suite on Ubuntu when dispatched (D-0095), and none has
  run since this change.
