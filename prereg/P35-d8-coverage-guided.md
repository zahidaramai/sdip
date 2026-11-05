# P35 — Coverage-guided fuzzing of SDIP's untrusted-input entry points (D8)

> **SP9.** Committed **before** the run. Sections above the results separator are never edited.

| Field | Value |
|---|---|
| Probe | `P35` |
| Status | `REGISTERED` |
| Registered | 2026-11-05 |
| Registered by | Claude Code session, on GeoSuite's order of 2026-11-05 (tool choice accepted: stdlib coverage, no new dependency) |
| Related debt | `OPEN_DEBTS.md` D8: "coverage-guided fuzzing" open |
| Spec clause | §11.4; operating contract §3.6 |

## Question

Does input that **coverage guidance** finds, rather than input someone composed, make SDIP's
untrusted-input path crash, hang, raise an untyped exception, or let a malformed file through
unrefused?

## Tool

**No new dependency.** Coverage comes from CPython **3.12.13**'s `sys.monitoring`: LINE and
BRANCH events on code under `sdip/` and `segy/`.
- Each callback returns `DISABLE`, so a location fires once per process, and an input that fires
  any location has reached code nothing before it reached. That input joins the corpus.
- `restart_events()` runs at start, so no earlier state leaks in.

atheris was not used: it needs libFuzzer, which Apple clang does not ship, and the shared
`.venv` takes no new package (D-0139). The harness is `tests/fuzz/coverage_fuzz.py`, committed
with this registration.

## Method

- **Target, in-process,** on bytes written to a file:
  1. `validate_source`;
  2. `read_raw_file_headers` and `classify_textual_header`;
  3. `read_header_columns`, which is `segy`'s parser through SDIP's blocked reader.
- **Seeds: 35,** rebuilt from committed generators: the positive control, the 23 single
  mutations, P29's 9 converted files and P34's 2.
- **Mutations,** seeded `default_rng(20261105 + restart)`, 1 to 3 per input:
  - a bit flip;
  - an interesting byte, 16-bit or 32-bit value at a binary-header or trace-header offset;
  - a truncation or an extension;
  - a binary-header splice from another corpus input.
- **The D8 child,** unchanged, two at a time, runs:
  - every corpus addition;
  - the first input of each distinct upstream exception from step 3;
  - admitted inputs as best effort, while fewer than 8 children are queued. The rest are counted
    as `admitted_not_sent`, not run.
- **Supervisor.** The worker runs as a subprocess and is restarted if it dies. After a restart
  it replays the corpus to rebuild coverage.
- **Cap: 7,200 s** for the fuzz loop. Children already queued at the cap finish and are
  judged. The smoke run measured about 670 executions per second.
- Run at this registration's commit, from a clean tree.

## Hits (the falsifier)

| Kind | What |
|---|---|
| **H1** | an exception other than an `SdipError` out of target steps 1 or 2, which are SDIP's own pre-allocation layer |
| **H2** | the target runs past its 30 s alarm, or the worker stalls past 4 × alarm + 600 s |
| **H3** | the worker process dies |
| **H4** | any of P15's six clauses in the D8 child: an untyped library exception, a traceback, exit 3, peak RSS over 512 MiB, a file written outside the output, or CLI exit 0 on a file the library refused |

**Not hits:**
- SDIP-typed refusals at any step;
- an upstream exception at step 3 (recorded, and its input goes to the child, which judges it);
- MDIO's typed grid refusals in the child.

Each H1 reproducer is minimised by reverting byte ranges to its parent while the same kind
still fails. H2 and H3 reproducers are kept as found. All of them are written to the receipt.

## Controls, committed with the harness (`tests/negative/test_p35_harness_controls.py`)

- a planted untyped exception registers as H1, with a minimised reproducer;
- a planted hang under a 1 s alarm registers as H2;
- with the real target, coverage grows past the seeds;
- mutation is deterministic for a seed;
- the seeds are the registered 35.

All five passed before this registration.

## Reported, not gated

Coverage over time (locations, corpus, executions), outcome counts by step, child outcomes,
`admitted_not_sent`, and each distinct upstream exception.

## If it fires

Each hit's reproducer becomes a permanent default-suite test, as the negative control for its
fix, which is not built in this probe. D8 stays OPEN.

## If it does not fire

D8's "coverage-guided fuzzing" item is measured for this target, these mutators and this cap.
The child path's own coverage is not measured. The 1,207 unrun five-way files, six- and
seven-way combinations, x86-64 and Windows stay open.

---

## Results — *appended after the run, never edited into the sections above*
