# P14 — Poststack chunk shape against read cost, on the Volve stores

- **Registered:** 2026-10-30, **before the run**, per **SP9** · **Status at registration:** NOT RUN
- **Asked by:** the owner, on D4 (`DECISIONS.md` D-0106): *"Both: P7 prestack criterion + P14
  poststack probe"*
- **Input, not evidence:** a consumer's browser-side measurement (SFM, `docs/FRONTEND.md` §5,
  2026-09-17) of the Volve depth pair re-encoded at four shapes, which named the candidate set
  below. Its numbers are not this probe's result and are not compared against.
- **Related:** OPEN_DEBTS D4 (chunking unmeasured), P7 F12 (no store records its chunk shape,
  and `sdip ingest` offers no way to choose one)

---

## Question

Every SDIP poststack store ships MDIO's template default chunk, **128 × 128 × 128** (measured on
the F3, Volve time and Volve depth stores on record, D-0105). **Does any of 128 × 128 × 64,
64 × 256 × 64 or 64³ read the four common access patterns more cheaply than 128³, on real
poststack stores, without changing what the store holds?**

## Why it matters

A chunk is decoded whole. A shape that fits an access pattern decodes less; one that does not
decodes and discards. SDIP makes that trade silently for every consumer (P7 F11, F12). If a
shape dominates 128³, the owner has a store-layout decision to make; if none does, 128³ stays
with a measurement behind it. **Equivalence is not at stake** — a store at any shape must hold
identical values, and the precondition below enforces it.

## Articles — openly licensed, fetched outside the repository, never vendored

| Case | Source file | Bytes | sha256 | Declaration |
|---|---|---|---|---|
| `volve_time` | `ST10010ZC11_PZ_PSDM_KIRCH_FULL_T.segy` | 1,050,849,760 | `f902e2bdaa277caf93a32e5f35eae653eb8b923138db0efc1e91918ef6757b2e` | revision 1, `PostStack3DTime`, no override |
| `volve_depth` | `volve_base_2002_ST0202ZDC12.sgy` | 58,409,880 | `8bd0fc8ef159bc5ee74ee4420f066ac538b92ef9f23e540648442a18882d70f2` | revision 0, `PostStack3DDepth`, `overrides/segy-rev0-poststack3d.toml` |

Equinor Volve open data (CC BY 4.0, no resale; attribute Equinor). Hashes as re-measured on
2026-10-30 (D-0105). The harness refuses a source whose sha256 differs.

## Method

`p14_harness.py` below, extracted verbatim, from a clean worktree at the commit that registers
P14, once that commit is on `origin`. For each case and each shape:

1. **Build** the store exactly as SDIP builds one — the pinned public `segy_to_mdio` with SDIP's
   declared spec, file headers persisted (mode 1), then SDIP's raw file headers, raw sample view
   and header plane attached — with the shape set through
   `AbstractDatasetTemplate.full_chunk_shape` on the fresh template copy `get_template`
   returns (the construction P7's latency leg used; no internal is touched, §3.3). `128^3` is the
   template left untouched. `sdip ingest` cannot set a shape (F12), so this is not a run of
   `sdip ingest`, and no figure is reported as one.
2. **Precondition:** Planes 1-5 PASS on every store, **and** the decoded `amplitude` array has
   the same sha256 at every shape. No timing is taken for a case that fails either.
3. **Structure** (deterministic, no timer): per access pattern, the chunks touched, their
   compressed bytes on disk, and the decoded bytes.
4. **Timing:** two runs, A and B (B in reversed shape order). Each run starts only when the
   1-minute load average is at most a quarter of the cores, waiting up to 3 × 60 s; otherwise
   that run is recorded **void**. Each (shape, pattern): N = 5 repetitions of open-and-read, the
   group re-opened each time; the median is the figure. The OS page cache is not dropped
   (`purge` needs `sudo`), so every figure is a warm-cache lower bound.

**Access patterns** (dimensions inline, crossline, sample): `full_inline` = the middle inline;
`full_crossline` = the middle crossline; `sample_slice` = the middle sample; `window` = the
central half of inlines × central half of crosslines × the central third of samples.

## Pre-registered parameters — fixed before the run

| Parameter | Value |
|---|---|
| Shapes | `128^3` (default, comparator), `128x128x64`, `64x256x64`, `64^3` — no others, no search |
| Cases | `volve_time`, `volve_depth` |
| N | 5 per (case, shape, pattern, run); median reported |
| Runs | 2 (A, B); a void run is reported as void, not repeated beyond the 3 load checks |
| Load gate | 1-min load ≤ 0.25 × cores at the start of a run |
| "Beats" | shape S beats 128³ on pattern P when median(128³) / median(S) ≥ **1.25** in **both** runs |
| "Loses" | S loses to 128³ on P when median(S) / median(128³) ≥ 1.25 in both runs |
| Environment | the pins (`multidimio` 1.2.1, `segy` 0.6.0), CPython as `uv sync --frozen` installs, no barred variable (checked first) |

1.25 is a noise margin, not a target: P7 recorded a run-to-run factor of 2 under load 9.4, which
is why runs above the load gate are void rather than included.

## Decision rule and falsifier

**Hypothesis:** the shipped 128³ is not dominated on these stores.

**Falsifier:** on **both** cases, some single shape S beats 128³ on at least one pattern and
loses on none. If it fires, OPEN_DEBTS D4 records the dominating shape and the owner is asked
for a store-layout ruling (a chunk choice is a store change with a certificate consequence, F12);
nothing changes in SDIP on this probe alone. If it does not fire, 128³ stays, and the structure
table is recorded as the reason.

**Stop conditions:** a source hash mismatch, or a failed precondition, stops that case and is
reported; it is never routed around. Both timing runs void → the timing leg is NOT EVALUABLE and
only the structure is reported.

## What this does NOT do

- No cold-cache read, no object-store read, no browser: one machine, local disk, warm cache.
- Two stores, one machine; not a claim about every poststack survey.
- No prestack: that is P7 Amendment B.

## Harness

Extract verbatim and run
`python p14_harness.py RUN_ROOT REPO_ROOT cases.json > receipt.json`, with `cases.json` the two
rows of the article table (`name`, `source`, `sha256`, `revision`, `template`, `override` as a
repository path or null). RUN_ROOT is harvested into the results below and deleted (Storage Law).

```python p14
"""P14 harness: poststack chunk shape against read cost, on the Volve stores.

Usage: python p14_harness.py RUN_ROOT REPO_ROOT CASES_JSON > receipt.json

CASES_JSON lists the articles: [{"name", "source", "sha256", "revision", "template",
"override"}]. RUN_ROOT must not exist; the caller harvests the receipt and deletes it.
Must run from a clean worktree at the commit that registers P14 (SP9).
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import statistics
import sys
import time
from pathlib import Path
from typing import Any

SHAPES: dict[str, tuple[int, int, int] | None] = {
    "128^3": None,  # the template's own shape, untouched: what every SDIP store ships
    "128x128x64": (128, 128, 64),
    "64x256x64": (64, 256, 64),
    "64^3": (64, 64, 64),
}
PATTERNS = ("full_inline", "full_crossline", "sample_slice", "window")
REPETITIONS = 5
RUNS = ("A", "B")
LOAD_LIMIT_FRACTION = 0.25  # a run starts only when the 1-min load <= cores x this
LOAD_ATTEMPTS = 3
LOAD_WAIT_S = 60


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _index(pattern: str, shape: tuple[int, ...]) -> tuple[Any, ...]:
    n_il, n_xl, n_s = shape
    if pattern == "full_inline":
        return (n_il // 2, slice(None), slice(None))
    if pattern == "full_crossline":
        return (slice(None), n_xl // 2, slice(None))
    if pattern == "sample_slice":
        return (slice(None), slice(None), n_s // 2)
    return (
        slice(n_il // 4, 3 * n_il // 4),
        slice(n_xl // 4, 3 * n_xl // 4),
        slice(n_s // 3, 2 * n_s // 3),
    )


def _chunks_touched(index: tuple[Any, ...], shape: tuple[int, ...], chunks: tuple[int, ...]):
    """Chunk grid coordinates a read touches. Structural: no timer, no cache."""
    ranges = []
    for sel, n, c in zip(index, shape, chunks, strict=True):
        if isinstance(sel, int):
            ranges.append(range(sel // c, sel // c + 1))
        else:
            start, stop, _ = sel.indices(n)
            ranges.append(range(start // c, (stop - 1) // c + 1))
    return [(i, j, k) for i in ranges[0] for j in ranges[1] for k in ranges[2]]


def _build(case: dict[str, Any], store: Path, requested: tuple[int, int, int] | None) -> None:
    from mdio import segy_to_mdio
    from mdio.builder.template_registry import get_template

    from sdip.guard.warn import WarningLedger, recording_warnings
    from sdip.ingest import attach_raw_file_headers, read_raw_file_headers
    from sdip.ingest.file_headers import file_headers_persisted
    from sdip.ingest.header_plane import attach_header_plane
    from sdip.ingest.raw_samples import attach_raw_sample_view
    from sdip.spec.declaration import SurveyDeclaration
    from sdip.spec.overrides import load_override

    override = load_override(Path(case["override"])) if case.get("override") else None
    declaration = SurveyDeclaration(
        revision=case["revision"], template=case["template"], override=override
    )
    spec = declaration.build_spec().segy_spec
    template = get_template(case["template"])
    if requested is not None:
        template.full_chunk_shape = requested  # documented public setter on a fresh copy
    source = Path(case["source"])
    raw = read_raw_file_headers(source)
    with recording_warnings(WarningLedger(), reemit=False), file_headers_persisted():
        segy_to_mdio(
            segy_spec=spec,
            mdio_template=template,
            input_path=source,
            output_path=store,
            overwrite=False,
        )
    attach_raw_file_headers(store, raw)
    attach_raw_sample_view(store, source, spec)
    attach_header_plane(store, source, spec)


def _planes(case: dict[str, Any], store: Path) -> dict[str, str]:
    from sdip.equivalence import plane_1, plane_2, plane_3, plane_4, plane_5
    from sdip.spec.declaration import SurveyDeclaration
    from sdip.spec.gate import g1
    from sdip.spec.overrides import load_override

    override = load_override(Path(case["override"])) if case.get("override") else None
    spec = (
        SurveyDeclaration(revision=case["revision"], template=case["template"], override=override)
        .build_spec()
        .segy_spec
    )
    source = Path(case["source"])
    gate = g1(spec.trace.header.fields, dtype=spec.trace.header.dtype)
    results = {
        "plane_1": plane_1(source, store),
        "plane_2": plane_2(source, store),
        "plane_3": plane_3(source, store, spec, g1_passed=gate.passed),
        "plane_4": plane_4(source, store, spec),
        "plane_5": plane_5(source, store, spec),
    }
    return {k: v.status for k, v in results.items()}


def _structure(store: Path, pattern: str) -> dict[str, Any]:
    import zarr

    array = zarr.open_group(str(store), mode="r")["amplitude"]
    shape, chunks = tuple(array.shape), tuple(array.chunks)
    touched = _chunks_touched(_index(pattern, shape), shape, chunks)
    compressed = 0
    for i, j, k in touched:
        chunk_file = store / "amplitude" / "c" / str(i) / str(j) / str(k)
        compressed += chunk_file.stat().st_size if chunk_file.exists() else 0
    per_chunk = int(chunks[0] * chunks[1] * chunks[2] * array.dtype.itemsize)
    return {
        "chunks": list(chunks),
        "chunks_touched": len(touched),
        "compressed_bytes": compressed,
        "decoded_bytes": len(touched) * per_chunk,
    }


def _time(store: Path, pattern: str) -> list[float]:
    import numpy as np
    import zarr

    samples = []
    for _ in range(REPETITIONS):
        start = time.perf_counter()
        array = zarr.open_group(str(store), mode="r")["amplitude"]
        block = np.asarray(array[_index(pattern, tuple(array.shape))])
        samples.append(time.perf_counter() - start)
        del block, array
    return samples


def _wait_for_quiet() -> dict[str, Any]:
    limit = (os.cpu_count() or 1) * LOAD_LIMIT_FRACTION
    for attempt in range(1, LOAD_ATTEMPTS + 1):
        load = os.getloadavg()[0]
        if load <= limit:
            return {"load_1min": load, "limit": limit, "attempt": attempt, "void": False}
        time.sleep(LOAD_WAIT_S)
    return {"load_1min": os.getloadavg()[0], "limit": limit, "attempt": LOAD_ATTEMPTS, "void": True}


def main() -> None:
    import numpy as np
    import zarr

    from sdip.guard.env import check_barred_env_vars

    run_root, repo, cases_path = (Path(a).resolve() for a in sys.argv[1:4])
    if run_root.exists():
        raise SystemExit(f"RUN_ROOT {run_root} exists; P14 writes only into a fresh one")
    findings = check_barred_env_vars()
    if findings:
        raise SystemExit(f"barred variables set: {findings}")
    run_root.mkdir(parents=True)
    cases = json.loads(cases_path.read_text())
    receipt: dict[str, Any] = {
        "probe": "P14",
        "repo": str(repo),
        "python": platform.python_version(),
        "machine": platform.platform(),
        "cpu_count": os.cpu_count(),
        "cases": [],
    }
    for case in cases:
        source = Path(case["source"])
        observed = _sha256(source)
        entry: dict[str, Any] = {"name": case["name"], "source_sha256": observed, "stores": {}}
        if observed != case["sha256"]:
            entry["stopped"] = f"source sha256 {observed} != declared {case['sha256']}"
            receipt["cases"].append(entry)
            continue
        decoded_hash: dict[str, str] = {}
        for shape_name, requested in SHAPES.items():
            store = run_root / f"{case['name']}.{shape_name.replace('^', 'c')}.mdio"
            _build(case, store, requested)
            planes = _planes(case, store)
            amplitude = np.asarray(zarr.open_group(str(store), mode="r")["amplitude"][:])
            decoded_hash[shape_name] = hashlib.sha256(amplitude.tobytes()).hexdigest()
            del amplitude
            entry["stores"][shape_name] = {
                "planes": planes,
                "amplitude_sha256": decoded_hash[shape_name],
                "store_bytes": sum(f.stat().st_size for f in store.rglob("*") if f.is_file()),
                "structure": {p: _structure(store, p) for p in PATTERNS},
            }
        entry["precondition"] = {
            "all_planes_pass": all(
                s["planes"][k] == "PASS" for s in entry["stores"].values() for k in s["planes"]
            ),
            "amplitude_identical_across_shapes": len(set(decoded_hash.values())) == 1,
        }
        if all(entry["precondition"].values()):
            entry["runs"] = {}
            for run in RUNS:
                quiet = _wait_for_quiet()
                order = list(SHAPES) if run == "A" else list(reversed(SHAPES))
                timings = {
                    s: {
                        p: _time(run_root / f"{case['name']}.{s.replace('^', 'c')}.mdio", p)
                        for p in PATTERNS
                    }
                    for s in order
                }
                entry["runs"][run] = {
                    "load": quiet,
                    "median_s": {
                        s: {p: statistics.median(v) for p, v in t.items()}
                        for s, t in timings.items()
                    },
                    "samples_s": timings,
                }
        receipt["cases"].append(entry)
    json.dump(receipt, sys.stdout, indent=1, sort_keys=True)


if __name__ == "__main__":
    main()
```

---

## Results — run 2026-10-31, at `a891bf6`, N = 1 build per (case, shape)

| Field | Value |
|---|---|
| Run | 00:11:41-00:37:21 MYT, clean detached worktree at the registration commit `a891bf6` (on `origin`), harness extracted verbatim (sha256 equal to the registered text) |
| Environment | CPython 3.12.13, 14 cores, the pins, no barred variable (checked by the harness first) |
| Sources | both sha256 equal to the article table (the harness checked; neither case stopped) |
| Receipt | `prereg/P14-receipt-2026-10-31.json` (local paths removed; raw receipt sha256 `aa7df2442afbb3a4…`). Run root deleted after this record (Storage Law) |
| Verdict | **Precondition PASS on both cases. Timing leg NOT EVALUABLE: all four runs void.** Falsifier not evaluated |

**Precondition.** Every store, at every shape, Planes 1-5 PASS, and the decoded `amplitude` sha256
is identical across the four shapes (`volve_time` `b04aaa7dc2…`, `volve_depth` `1c0635f0c8…`).
Changing the chunk shape changed nothing a store holds.

**Structure** (deterministic; per pattern: chunks touched · compressed MiB read · decoded MiB):

| Case | Shape | Store bytes | full inline | full crossline | sample slice | window |
|---|---|---|---|---|---|---|
| `volve_time` | 128^3 | 1,577,867,483 | 42 · 243.9 · 336.0 | 28 · 135.9 · 224.0 | 24 · 118.0 · 192.0 | 36 · 239.4 · 288.0 |
| `volve_time` | 128x128x64 | 1,572,783,653 | 84 · 243.2 · 336.0 | 56 · 135.5 · 224.0 | 24 · 59.1 · 96.0 | 60 · 199.5 · 240.0 |
| `volve_time` | 64^3 | 1,571,080,332 | 168 · 121.4 · 168.0 | 98 · 67.4 · 98.0 | 84 · 59.1 · 84.0 | 140 · 116.2 · 140.0 |
| `volve_time` | 64x256x64 | 1,574,340,712 | 42 · 121.6 · 168.0 | 98 · 271.5 · 392.0 | 21 · 59.1 · 84.0 | 60 · 187.0 · 240.0 |
| `volve_depth` | 128^3 | 88,610,958 | 18 · 42.9 · 144.0 | 9 · 27.2 · 72.0 | 2 · 4.9 · 16.0 | 8 · 19.6 · 64.0 |
| `volve_depth` | 128x128x64 | 88,360,939 | 36 · 42.8 · 144.0 | 18 · 27.1 · 72.0 | 2 · 2.4 · 8.0 | 14 · 17.1 · 56.0 |
| `volve_depth` | 64^3 | 88,157,296 | 72 · 42.7 · 72.0 | 18 · 13.5 · 18.0 | 4 · 2.4 · 4.0 | 21 · 16.2 · 21.0 |
| `volve_depth` | 64x256x64 | 88,328,400 | 18 · 42.8 · 72.0 | 18 · 42.8 · 72.0 | 1 · 2.4 · 4.0 | 7 · 17.1 · 28.0 |
Read as the registered structure leg, nothing more. On decoded bytes, `64^3` is lowest or tied
lowest on every pattern of both cases (tied with `64x256x64` on `full_inline` in both cases and on
`sample_slice`); it decodes 2.1x to 4.0x less than `128^3` on `full_crossline` and `window`, and
touches 2.0x to 3.9x more chunks. `64x256x64` decodes the most on `volve_time`'s `full_crossline`
(392 MiB against 224 MiB for `128^3`) and ties `128^3` there on `volve_depth`. `128x128x64` halves
`sample_slice` against `128^3` on both. No shape decodes less than `128^3` on every pattern *and*
touches fewer chunks: smaller chunks trade decoded bytes for chunk count. The `volve_depth` `128^3` full-inline compressed figure, 45,007,663 B, equals the
consumer's figure for its 128³ re-encode of the same survey to the byte (consistency, not
evidence).

**Timing: void, not judged.** Each run's 1-minute load at its third check: `volve_time` A 4.80,
B 4.53; `volve_depth` A 12.27, B 4.90 — all above the declared 0.25 × 14 = 3.5, so every run is
void as the method requires. The harness still recorded the samples; they are in the receipt with
`"void": true` and are **not** evidence of anything. With both runs void on both cases, the
timing leg is NOT EVALUABLE and, as registered, only the structure is reported. **D4's poststack
question stays open.** A rerun of the timing leg alone needs its own amendment registered before
it (a quiet window; nothing else changed).

### Recorded in

`OPEN_DEBTS.md` D4 (unchanged: open) · this file

---

## Amendment A — 2026-10-31, before the run it governs: the timing leg, rerun in a quiet window

**Why.** The 2026-10-31 run met its precondition and recorded the structure, but all four timing
runs were void (load 4.53-12.27 against 3.5), so the timing leg was NOT EVALUABLE. Those void runs
stand as recorded above. Other sessions' critical work keeps the machine busy (GeoSuite D-222), so
no session is paused for this; the rerun waits for a quiet window instead.

**Changed — only when the run starts.** The harness is started automatically by a detached
watcher, at the commit that registers this amendment (once on `origin`), only after the 1-minute
load average has been **≤ 3.5 for 10 consecutive minutes** (sampled every 60 s). The watcher
stays armed until **2026-11-01 18:00 MYT**; if no window comes, that is recorded and nothing runs.

**Unchanged:** the harness (verbatim, as registered), the articles, the shapes, the patterns,
N = 5, two runs, the per-run load gate (≤ 0.25 × cores at each run's start, 3 checks 60 s apart,
else void), the 1.25 "beats/loses" ratio, the falsifier and its consequence. The harness rebuilds
the stores, so the precondition and the structure are measured again; **they must equal the
results above**, and any difference is reported as a finding before any timing is read. Every
void run is recorded. Run root harvested and deleted (Storage Law).

---

## Amendment A — results, 2026-10-31, at `b9f0577`: the falsifier fires

| Field | Value |
|---|---|
| Run | 02:23:28-02:38:21 MYT, started by the detached watcher after 10 consecutive minutes at load ≤ 3.5, from a clean detached worktree at the registration commit `b9f0577` (on `origin`), harness unchanged |
| Sources | both sha256 equal to the article table (the harness checked; neither case stopped) |
| Receipt | `prereg/P14-receipt-2026-10-31-A.json` (local path removed; raw receipt sha256 `beab3c2a50f5ed22…`). Run root deleted after this record (Storage Law) |
| Verdict | **Precondition PASS on both cases; structure equal to the first run on every compared field; all four timing runs valid; the falsifier fires** |

**Finding, reported first as the amendment requires: total store bytes differ from the first run; nothing the
probe compares does.** Every amplitude sha256, every plane status, and every chunks-touched, compressed-bytes and
decoded-bytes figure for every (case, shape, pattern) equals the first run's. The only field that differs is each
store's total size, which is about 0.51 of the first run's:

| Case | Shape | First run (`a891bf6`) | This run (`b9f0577`) |
|---|---|---|---|
| `volve_time` | 128^3 / 128x128x64 / 64^3 / 64x256x64 | 1,577,867,483 / 1,572,783,653 / 1,571,080,332 / 1,574,340,712 | 807,520,006 / 805,073,934 / 804,412,031 / 805,580,425 |
| `volve_depth` | same order | 88,610,958 / 88,360,939 / 88,157,296 / 88,328,400 | 45,198,423 / 45,089,653 / 44,989,123 / 45,046,716 |

The cause is D36, merged between the two runs (`7f1c5ec`). The raw `ibm32` view became sparse (D-0110), and on
Volve time it now holds 0 entries where it held one word per cell (OPEN_DEBTS D36 CLOSED: 752,628 KiB of view
before, 12 KiB after). The structure table above counts `amplitude` reads only, so it does not change. This
amendment was registered after that merge and should have expected the change; it did not, and that is recorded
here. The structure comparison and the timing were computed in the same pass; the difference does not reach
any timed quantity.

**Load at each run's start:** `volve_time` A 2.75 (3rd check), B 2.75 (1st check); `volve_depth` A 2.25 (3rd
check), B 2.47 (1st check). All four are ≤ 3.5, so all four runs are valid. Each figure is a fresh
`os.getloadavg()` read. The two equal `volve_time` values (5629/2048) were read seconds apart, inside the same
5-second load update.

**median(128³) / median(S), N = 5, runs A / B** (BEATS: ≥ 1.25 in both; LOSES: S slower by ≥ 1.25 in both):

| Case | Shape | full inline | full crossline | sample slice | window |
|---|---|---|---|---|---|
| `volve_time` | 128x128x64 | 1.00 / 1.02 | 0.98 / 1.20 | **1.74 / 1.83 BEATS** | 1.18 / 1.14 |
| `volve_time` | 64^3 | 1.28 / 1.23 | **1.34 / 1.76 BEATS** | **1.36 / 1.34 BEATS** | **1.38 / 1.33 BEATS** |
| `volve_time` | 64x256x64 | **1.81 / 1.89 BEATS** | **0.55 / 0.72 LOSES** | **1.77 / 1.84 BEATS** | 1.22 / 1.17 |
| `volve_depth` | 128x128x64 | 0.93 / 0.91 | 0.92 / 0.92 | **1.85 / 1.81 BEATS** | 1.01 / 0.98 |
| `volve_depth` | 64^3 | 0.96 / 0.92 | **1.62 / 1.66 BEATS** | **3.08 / 3.25 BEATS** | **1.27 / 1.37 BEATS** |
| `volve_depth` | 64x256x64 | **1.49 / 1.47 BEATS** | 0.87 / 0.85 | **1.71 / 1.65 BEATS** | **1.56 / 1.52 BEATS** |

**Verdict: the falsifier fires.** On both cases a single shape beats 128³ on at least one pattern and loses on
none, and this holds for two shapes:

- **`64^3`** beats 128³ on 3 of 4 patterns in each case (crossline, sample slice and window) and loses on none.
  Full inline is not decided (1.28/1.23 and 0.96/0.92).
- **`128x128x64`** beats 128³ on sample slice in both cases and loses on none.

`64x256x64` does not qualify, because it loses on `volve_time` full crossline. The hypothesis "the shipped 128³ is
not dominated on these stores" is falsified. As registered, OPEN_DEBTS D4 records the dominating shapes and the
owner is asked for a store-layout ruling (a chunk choice is a store change with a certificate consequence, F12).
Nothing changes in SDIP on this probe alone.

**Scope, as registered:** two stores, one machine, local disk, warm cache, absolute medians of 2.6-58 ms. This is
not a claim about cold reads, object stores or every poststack survey.

### Recorded in

`OPEN_DEBTS.md` D4 (falsifiers fired; owner ruling asked) · this file

---

## Amendment B — 2026-10-31, before the run it governs: the same probe on F3 (D-0112)

**Why.** P14 Amendment A's falsifier fired on both Volve stores. The D4 ruling (`DECISIONS.md`
D-0112, relayed via GeoSuite under D-222) does not move the default on one field: *"the P14 evidence
is Volve only, and one field is one field. Register P14 Amendment B: the same criterion,
candidates 64^3 and 128×128×64 against 128^3, on the F3 store, armed for the next quiet window
with the same load gate."*

**Article.** One openly licensed poststack volume, fetched outside the repository and never
vendored. It is the F3 article of P12: 1,292,686,488 bytes,
`sha256 b36494f4e9bed7216228124f43ff8901168bff8bebd4e4c4dabb80a68d568dab`, 619,101 traces
(651 × 951), 462 samples at 4 ms, IEEE float32. Case name `f3`; declaration revision 1,
`PostStack3DTime`, no override (the reading D-0097 verified). The harness refuses a source whose
sha256 differs.

**Unchanged:**
- the harness, verbatim as registered above;
- the four patterns, N = 5, two runs (A, B);
- the per-run load gate (≤ 0.25 × cores at each run's start, 3 checks 60 s apart, else void);
- the 1.25 "beats/loses" ratio;
- the precondition (Planes 1-5 PASS at every shape, amplitude identical across shapes), and its
  stop condition.

The harness still builds all four registered shapes. `64x256x64` is recorded and not judged; the
ruling names two candidates.

**When the run starts.** It is started by a detached watcher, as in Amendment A:
- at the commit that registers this amendment, once that commit is on `origin`;
- only after the 1-minute load average has been ≤ 3.5 for 10 consecutive minutes (sampled every
  60 s);
- the watcher stays armed until **2026-11-02 12:00 MYT**. If no window comes, that is recorded and
  nothing runs.

**Decision rule, on F3 alone** (a candidate *qualifies* when it beats 128³ on at least one pattern
and loses on none, with "beats" and "loses" exactly as registered above):
- **`64^3` qualifies:** as ruled, the poststack default moves from 128³ to 64³. That is a store-format
  change shipped as a MAJOR release with a migration note; GeoSuite relays the re-pin to GeoAIBrain,
  SFM and ExS. The move is its own decision entry and its own commit, made after this record and
  citing it. Nothing changes on this record alone.
- **`64^3` does not qualify:** the default stays 128³, and the disagreement between F3 and Volve is
  the record.
- **`128x128x64`** is judged by the same rule and recorded. On its own it moves nothing: the ruling
  ties the move to 64³ only.

Either void run → NOT EVALUABLE, and the default stays.

**Scope.** One more store, one machine, local disk, warm cache. Two fields are not every
poststack survey.

---

## Amendment C — 2026-10-31 07:4x MYT, before any run: start now, on the owner's order

**Why.** Amendment B's watcher waited from 03:51 to 07:41 and no 10-minute window at load ≤ 3.5
came (sampled 1-minute load 5.5-19.6). The owner, directly in this session: *"Run it at all cost!"*

**Changed — only when the run starts:** the harness is started at once from a clean worktree at
the commit that registers this amendment, once that commit is on `origin`. The 10-quiet-minutes
trigger is dropped. GeoSuite is asked to pause the suite's heavy jobs for the timing window.

**Unchanged:** everything else in Amendment B and above:
- the harness verbatim, the article, the shapes and patterns, N = 5, two runs;
- the **per-run load gate** (≤ 0.25 × cores at each run's start, 3 checks 60 s apart, else void);
- the 1.25 ratio, the decision rule and its consequence.

A run above the gate is still void and is not judged. If both runs are void, the timing leg is
NOT EVALUABLE, the default stays 128³, and only the precondition and structure are recorded.

---

## Amendment D — 2026-10-31, before any F3 timing: the harness builds through SDIP's own ingest

**What happened (no measurement).** Under Amendment C the harness started at 07:44:52 at `ea439a4`
(load 12.43) and stopped at 07:45:04 during its first F3 build:
`ValueError: Invalid text header characters: non-ASCII or non-printable at row 5`.
- **The cause is this probe's harness, not SDIP.** The harness called upstream directly with
  file-header persistence forced to STRICT (mode 1). F3's textual header does not decode (P12
  recorded this). SDIP's own ingest handles that case by choosing mode 0 and preserving the raw
  3,200 bytes (D-0055); the harness skipped that step.
- The harness also skipped SDIP's recording-delay axis step (D-0096). F3 carries a constant 4 ms
  delay; neither Volve store does.
- Nothing was built, timed or judged. This should have been caught at registration from P12's
  record, and was not.

**Changed:** `_build` only. Each store is now built by `sdip.ingest.orchestrator.ingest_declared`,
with the shape as the declaration's `chunk_shape` (D-0112), and `None` for 128³. That is the path
`sdip ingest --chunks` takes. The full harness, as it will run:

```python p14d
"""P14 harness (Amendment D): poststack chunk shape against read cost.

Usage: python p14_harness.py RUN_ROOT REPO_ROOT CASES_JSON > receipt.json

CASES_JSON lists the articles: [{"name", "source", "sha256", "revision", "template",
"override"}]. RUN_ROOT must not exist; the caller harvests the receipt and deletes it.
Must run from a clean worktree at the commit that registers P14 (SP9).
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import statistics
import sys
import time
from pathlib import Path
from typing import Any

SHAPES: dict[str, tuple[int, int, int] | None] = {
    "128^3": None,  # the template's own shape, untouched: what every SDIP store ships
    "128x128x64": (128, 128, 64),
    "64x256x64": (64, 256, 64),
    "64^3": (64, 64, 64),
}
PATTERNS = ("full_inline", "full_crossline", "sample_slice", "window")
REPETITIONS = 5
RUNS = ("A", "B")
LOAD_LIMIT_FRACTION = 0.25  # a run starts only when the 1-min load <= cores x this
LOAD_ATTEMPTS = 3
LOAD_WAIT_S = 60


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _index(pattern: str, shape: tuple[int, ...]) -> tuple[Any, ...]:
    n_il, n_xl, n_s = shape
    if pattern == "full_inline":
        return (n_il // 2, slice(None), slice(None))
    if pattern == "full_crossline":
        return (slice(None), n_xl // 2, slice(None))
    if pattern == "sample_slice":
        return (slice(None), slice(None), n_s // 2)
    return (
        slice(n_il // 4, 3 * n_il // 4),
        slice(n_xl // 4, 3 * n_xl // 4),
        slice(n_s // 3, 2 * n_s // 3),
    )


def _chunks_touched(index: tuple[Any, ...], shape: tuple[int, ...], chunks: tuple[int, ...]):
    """Chunk grid coordinates a read touches. Structural: no timer, no cache."""
    ranges = []
    for sel, n, c in zip(index, shape, chunks, strict=True):
        if isinstance(sel, int):
            ranges.append(range(sel // c, sel // c + 1))
        else:
            start, stop, _ = sel.indices(n)
            ranges.append(range(start // c, (stop - 1) // c + 1))
    return [(i, j, k) for i in ranges[0] for j in ranges[1] for k in ranges[2]]


def _build(case: dict[str, Any], store: Path, requested: tuple[int, int, int] | None) -> None:
    """Amendment D: build through SDIP's own ingest, the shape on the declaration (D-0112)."""
    from sdip.ingest.orchestrator import ingest_declared
    from sdip.spec.declaration import SurveyDeclaration
    from sdip.spec.overrides import load_override

    override = load_override(Path(case["override"])) if case.get("override") else None
    declaration = SurveyDeclaration(
        revision=case["revision"],
        template=case["template"],
        override=override,
        chunk_shape=requested,
    )
    ingest_declared(Path(case["source"]), store, declaration)


def _planes(case: dict[str, Any], store: Path) -> dict[str, str]:
    from sdip.equivalence import plane_1, plane_2, plane_3, plane_4, plane_5
    from sdip.spec.declaration import SurveyDeclaration
    from sdip.spec.gate import g1
    from sdip.spec.overrides import load_override

    override = load_override(Path(case["override"])) if case.get("override") else None
    spec = (
        SurveyDeclaration(revision=case["revision"], template=case["template"], override=override)
        .build_spec()
        .segy_spec
    )
    source = Path(case["source"])
    gate = g1(spec.trace.header.fields, dtype=spec.trace.header.dtype)
    results = {
        "plane_1": plane_1(source, store),
        "plane_2": plane_2(source, store),
        "plane_3": plane_3(source, store, spec, g1_passed=gate.passed),
        "plane_4": plane_4(source, store, spec),
        "plane_5": plane_5(source, store, spec),
    }
    return {k: v.status for k, v in results.items()}


def _structure(store: Path, pattern: str) -> dict[str, Any]:
    import zarr

    array = zarr.open_group(str(store), mode="r")["amplitude"]
    shape, chunks = tuple(array.shape), tuple(array.chunks)
    touched = _chunks_touched(_index(pattern, shape), shape, chunks)
    compressed = 0
    for i, j, k in touched:
        chunk_file = store / "amplitude" / "c" / str(i) / str(j) / str(k)
        compressed += chunk_file.stat().st_size if chunk_file.exists() else 0
    per_chunk = int(chunks[0] * chunks[1] * chunks[2] * array.dtype.itemsize)
    return {
        "chunks": list(chunks),
        "chunks_touched": len(touched),
        "compressed_bytes": compressed,
        "decoded_bytes": len(touched) * per_chunk,
    }


def _time(store: Path, pattern: str) -> list[float]:
    import numpy as np
    import zarr

    samples = []
    for _ in range(REPETITIONS):
        start = time.perf_counter()
        array = zarr.open_group(str(store), mode="r")["amplitude"]
        block = np.asarray(array[_index(pattern, tuple(array.shape))])
        samples.append(time.perf_counter() - start)
        del block, array
    return samples


def _wait_for_quiet() -> dict[str, Any]:
    limit = (os.cpu_count() or 1) * LOAD_LIMIT_FRACTION
    for attempt in range(1, LOAD_ATTEMPTS + 1):
        load = os.getloadavg()[0]
        if load <= limit:
            return {"load_1min": load, "limit": limit, "attempt": attempt, "void": False}
        time.sleep(LOAD_WAIT_S)
    return {"load_1min": os.getloadavg()[0], "limit": limit, "attempt": LOAD_ATTEMPTS, "void": True}


def main() -> None:
    import numpy as np
    import zarr

    from sdip.guard.env import check_barred_env_vars

    run_root, repo, cases_path = (Path(a).resolve() for a in sys.argv[1:4])
    if run_root.exists():
        raise SystemExit(f"RUN_ROOT {run_root} exists; P14 writes only into a fresh one")
    findings = check_barred_env_vars()
    if findings:
        raise SystemExit(f"barred variables set: {findings}")
    run_root.mkdir(parents=True)
    cases = json.loads(cases_path.read_text())
    receipt: dict[str, Any] = {
        "probe": "P14",
        "repo": str(repo),
        "python": platform.python_version(),
        "machine": platform.platform(),
        "cpu_count": os.cpu_count(),
        "cases": [],
    }
    for case in cases:
        source = Path(case["source"])
        observed = _sha256(source)
        entry: dict[str, Any] = {"name": case["name"], "source_sha256": observed, "stores": {}}
        if observed != case["sha256"]:
            entry["stopped"] = f"source sha256 {observed} != declared {case['sha256']}"
            receipt["cases"].append(entry)
            continue
        decoded_hash: dict[str, str] = {}
        for shape_name, requested in SHAPES.items():
            store = run_root / f"{case['name']}.{shape_name.replace('^', 'c')}.mdio"
            _build(case, store, requested)
            planes = _planes(case, store)
            amplitude = np.asarray(zarr.open_group(str(store), mode="r")["amplitude"][:])
            decoded_hash[shape_name] = hashlib.sha256(amplitude.tobytes()).hexdigest()
            del amplitude
            entry["stores"][shape_name] = {
                "planes": planes,
                "amplitude_sha256": decoded_hash[shape_name],
                "store_bytes": sum(f.stat().st_size for f in store.rglob("*") if f.is_file()),
                "structure": {p: _structure(store, p) for p in PATTERNS},
            }
        entry["precondition"] = {
            "all_planes_pass": all(
                s["planes"][k] == "PASS" for s in entry["stores"].values() for k in s["planes"]
            ),
            "amplitude_identical_across_shapes": len(set(decoded_hash.values())) == 1,
        }
        if all(entry["precondition"].values()):
            entry["runs"] = {}
            for run in RUNS:
                quiet = _wait_for_quiet()
                order = list(SHAPES) if run == "A" else list(reversed(SHAPES))
                timings = {
                    s: {
                        p: _time(run_root / f"{case['name']}.{s.replace('^', 'c')}.mdio", p)
                        for p in PATTERNS
                    }
                    for s in order
                }
                entry["runs"][run] = {
                    "load": quiet,
                    "median_s": {
                        s: {p: statistics.median(v) for p, v in t.items()}
                        for s, t in timings.items()
                    },
                    "samples_s": timings,
                }
        receipt["cases"].append(entry)
    json.dump(receipt, sys.stdout, indent=1, sort_keys=True)


if __name__ == "__main__":
    main()
```

**Unchanged:** everything else:
- the article, shapes, patterns, N = 5, two runs;
- the per-run load gate, the precondition and the stop conditions;
- the 1.25 ratio, the decision rule and its consequence;
- Amendment C's start rule: the harness starts at once, at the commit registering this
  amendment, once that commit is on `origin`.
