# P13 — Which bytes of an SDIP store differ between ingests of the same source?

- **Registered:** 2026-10-15, **before the run**, per **SP9**
- **Asked by:** a consumer's request for a content-only store digest, accepted by the owner
  "measure first" (2026-10-15)
- **Status at registration:** NOT RUN

---

## Question

`sdipStoreDigest` (D-0093) covers every node's `zarr.json`, so two ingests of one source give
different digests: MDIO writes a creation time into the metadata. A consumer that re-ingests
cannot show it reproduced the same store. **Exactly which bytes differ between independent
ingests of the same source under the same declaration?** A content digest may exclude those and
nothing else.

## Method

The harness below, from a clean worktree at the commit that registers it. For each case, the
source is generated once and ingested **N = 3** times by `sdip ingest`, each a fresh process into
its own directory, 1.5 s apart. Then, across the three stores:

- every non-metadata file (chunk) is compared by SHA-256;
- every `zarr.json`, at every node, is parsed and flattened to key paths, and every key path whose
  value is not identical across the three is listed.

## Cases — the value space a store's layout depends on

| Case | Why |
|---|---|
| `ibm32` | default; carries `amplitude_raw_ibm32` |
| `float32` | IEEE; no raw view (D65) |
| `delay4` | carries `sdipSampleAxisOrigin` (D-0096) |
| `undecodable` | no `segy_file_header`; raw headers on the root group (D-0055) |
| `rev0` | rev 0 with the committed override; a different declaration |

## Pre-registered decision rule

1. **The content digest excludes exactly the varying key paths found here, and the marker's own
   attributes.** Nothing is excluded on reasoning alone; a key that did not vary is covered.
2. Every excluded key is named in the scheme's definition, with this probe as its evidence.
3. A varying key that is not a time or another per-run artefact (a path, a random identifier) is
   reported by name and **stops the build** for a ruling: excluding content would be a lie.

## Falsifier

**Any chunk file differing across ingests.** That would contradict G6 (D-0073 onward: two ingests
produce identical chunk bytes) and mean no byte-level content digest is reproducible; the build
stops and it is reported.

## What this does NOT do

- It runs one machine and one process environment; a key that varies only across machines or
  library versions is not seen. The scheme name versions the definition so that can be amended.
- It does not run on a real survey; the cases are synthetic.

## Harness

Extract verbatim and run `python p13_harness.py RUN_ROOT REPO_ROOT > receipt.json`.

```python p13
"""P13 harness: which bytes of an SDIP store differ between ingests of the same source?

Usage: python p13_harness.py RUN_ROOT REPO_ROOT > receipt.json
Synthetic data only. RUN_ROOT must not exist; the caller harvests and deletes it.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

RUN_ROOT = Path(sys.argv[1]).resolve()
REPO = Path(sys.argv[2]).resolve()
SDIP = str(REPO / ".venv" / "bin" / "sdip")
sys.path.insert(0, str(REPO))

N = 3
PAUSE_S = 1.5
CASES: dict[str, tuple[dict[str, Any], list[str]]] = {
    "ibm32": ({}, []),
    "float32": ({"sample_format": "float32"}, []),
    "delay4": ({"delay_recording_time": 4}, []),
    "undecodable": ({"undecodable": True}, []),
    "rev0": (
        {"rev0": True},
        ["--revision", "0", "--override", "overrides/segy-rev0-poststack3d.toml"],
    ),
}


def make(case: str, opts: dict[str, Any], path: Path) -> None:
    from tests.fixtures.generators.poststack3d import make_poststack3d
    from tests.fixtures.generators.revisions import make_revision_poststack3d
    from tests.fixtures.generators.undecodable import make_undecodable_textual_header

    if opts.get("undecodable"):
        make_undecodable_textual_header(path)
    elif opts.get("rev0"):
        make_revision_poststack3d(path, revision=0)
    else:
        make_poststack3d(path, **opts)


def flatten(value: Any, prefix: str = "") -> dict[str, Any]:
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for k, v in value.items():
            out.update(flatten(v, f"{prefix}/{k}"))
        return out
    return {prefix: json.dumps(value, sort_keys=True)}


def survey(store: Path) -> tuple[dict[str, str], dict[str, dict[str, Any]]]:
    chunks, metadata = {}, {}
    for path in sorted(store.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(store).as_posix()
        if path.name == "zarr.json":
            metadata[rel] = flatten(json.loads(path.read_bytes()))
        else:
            chunks[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
    return chunks, metadata


def main() -> None:
    RUN_ROOT.mkdir(parents=True, exist_ok=False)
    report: dict[str, Any] = {"probe": "P13", "N": N, "cases": {}}
    for case, (opts, flags) in CASES.items():
        source = RUN_ROOT / f"{case}.sgy"
        make(case, opts, source)
        runs = []
        for i in range(N):
            store = RUN_ROOT / f"{case}-{i}.mdio"
            proc = subprocess.run(
                [SDIP, "ingest", str(source), str(store), *flags],
                capture_output=True, text=True, check=False, cwd=REPO,
            )
            if proc.returncode != 0:
                runs.append({"error": proc.stderr[-600:]})
                continue
            runs.append(survey(store))
            time.sleep(PAUSE_S)
        good = [r for r in runs if isinstance(r, tuple)]
        if len(good) != N:
            report["cases"][case] = {"error": [r for r in runs if isinstance(r, dict)]}
            continue
        chunk_sets = [set(c) for c, _ in good]
        chunk_diff = sorted(
            rel for rel in set().union(*chunk_sets)
            if len({c.get(rel) for c, _ in good}) > 1
        )
        meta_paths: set[tuple[str, str]] = set()
        for rel in set().union(*(set(m) for _, m in good)):
            keys = set().union(*(set(m.get(rel, {})) for _, m in good))
            for key in keys:
                if len({m.get(rel, {}).get(key) for _, m in good}) > 1:
                    meta_paths.add((rel, key))
        report["cases"][case] = {
            "chunk_files": len(chunk_sets[0]),
            "chunk_files_differing": chunk_diff,
            "metadata_keys_differing": sorted(f"{rel}#{key}" for rel, key in meta_paths),
        }
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
```
