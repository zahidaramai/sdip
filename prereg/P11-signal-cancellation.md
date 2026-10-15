# P11 — What a signal to `sdip ingest` or `sdip verify` leaves running

- **Registered:** 2026-10-15, **before the run**, per **SP9**
- **Asked by:** issue #1, part (a)
- **Checked at:** `2eb674f`
- **Status at registration:** NOT RUN

---

## Question

Nothing under `src/` installs a SIGTERM or SIGINT handler, and `cli/main.py` catches
`click.Abort` only. `sdip ingest` reaches MDIO's worker pools, which MDIO builds itself
with a `spawn` context (`mdio/segy/parsers.py`, `mdio/segy/blocked_io.py`); SDIP never
holds them. `sdip verify` starts one grandchild for G4 (`equivalence/portability.py`).

**When the `sdip` process alone is sent SIGTERM or SIGINT, which of its child processes
are still running afterwards, what is their parent, does the store keep growing, and
what exit status does `sdip` return?**

The issue states, **inferred and not run**, that a SIGTERMed ingest leaves its pool
writing, reparented to `ppid=1`. This probe measures that before anything is changed
(SP8).

## Method

The harness below, run once, from a clean tree at the commit that registers it.

1. Generate a synthetic poststack source with SDIP's committed generator.
2. Ingest it once to completion, giving a store for the `verify` leg.
3. For each cell, start `sdip` in its own session, poll its process tree every 20 ms
   until a **target child** exists (ingest: a `spawn_main` worker; verify: the `-c`
   G4 grandchild), wait 0.3 s, snapshot the tree, then send the signal **to the `sdip`
   PID only**.
4. At +3 s and +15 s after the signal, record which snapshotted processes are alive,
   their parent, whether `sdip` is alive, and the store's file count and bytes.
5. Record `sdip`'s exit status. SIGKILL every survivor and record the kill.

A run whose target child is never seen (the command finished first) is **void**, recorded,
and does not count towards N.

## Pre-registered parameters

| Parameter | Value |
|---|---|
| Fixture | `make_poststack3d(n_inline=150, n_crossline=150, n_samples=1500)`, defaults otherwise |
| Cells | ingest/SIGTERM, ingest/SIGINT, verify/SIGTERM, verify/SIGINT |
| N | 3 triggered runs per cell, at most 6 attempts |
| Delivery | `os.kill(sdip_pid, sig)` — the parent only, not the process group |
| Observation | +3 s and +15 s after the signal |
| Seed | the generator's committed default |

## Falsifier

**The issue's claim is falsified if, in every triggered ingest/SIGTERM run, no pool
worker is alive at +15 s.** It is confirmed if any worker is alive at +15 s with a parent
other than the `sdip` process. Store growth after the signal is recorded as a separate
observation and is what "leaves its pool writing" means.

## What this probe does NOT do

- **Ctrl-C at a terminal** delivers SIGINT to the whole foreground process group, workers
  included. That is a different case and is not measured here.
- It measures one fixture on one machine. It says nothing about timing at survey scale.
- It does not test a fix. The acceptance test for the fix is a separate, committed test.

## Harness

Extract this block verbatim and run
`python p11_harness.py RUN_ROOT REPO_ROOT > receipt.json`. `RUN_ROOT` must not exist.

```python
"""P11 harness: what a signal to `sdip ingest` / `sdip verify` leaves running.

Usage: python p11_harness.py RUN_ROOT REPO_ROOT > receipt.json
Synthetic data only. Every process it observes surviving is killed at the end and the kill
is recorded; the run root is the caller's to harvest and delete.
"""

from __future__ import annotations

import hashlib
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

RUN_ROOT = Path(sys.argv[1]).resolve()
REPO = Path(sys.argv[2]).resolve()
SDIP = str(REPO / ".venv" / "bin" / "sdip")
sys.path.insert(0, str(REPO))

FIXTURE = {"n_inline": 150, "n_crossline": 150, "n_samples": 1500}
N = 3
MAX_ATTEMPTS = 6
POLL_S = 0.02
DETECT_TIMEOUT_S = 180.0
SNAP_S = (3.0, 15.0)


def ps() -> dict[int, tuple[int, str]]:
    out = subprocess.run(["ps", "-A", "-o", "pid=,ppid=,command="], capture_output=True,
                         text=True, check=True).stdout
    table = {}
    for line in out.splitlines():
        parts = line.strip().split(None, 2)
        if len(parts) == 3:
            table[int(parts[0])] = (int(parts[1]), parts[2])
    return table


def descendants(root: int, table: dict[int, tuple[int, str]]) -> dict[int, str]:
    found, frontier = {}, [root]
    while frontier:
        parent = frontier.pop()
        for pid, (ppid, cmd) in table.items():
            if ppid == parent and pid not in found:
                found[pid] = cmd
                frontier.append(pid)
    return found


def is_target(cmd: str, leg: str) -> bool:
    if "resource_tracker" in cmd:
        return False
    if leg == "ingest":
        return "spawn_main" in cmd
    return " -c " in cmd  # verify: the G4 grandchild (portability.py, argv [python, -c, ...])


def store_state(store: Path) -> tuple[int, int]:
    files = [p for p in store.rglob("*") if p.is_file()] if store.exists() else []
    return len(files), sum(p.stat().st_size for p in files)


def one_run(leg: str, sig: int, source: Path, store: Path) -> dict:
    if leg == "ingest":
        argv = [SDIP, "ingest", str(source), str(store), "--overwrite"]
    else:
        argv = [SDIP, "verify", str(source), str(store)]
    proc = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            start_new_session=True)
    t0 = time.monotonic()
    tree: dict[int, str] = {}
    while time.monotonic() - t0 < DETECT_TIMEOUT_S:
        if proc.poll() is not None:
            out, err = proc.communicate()
            return {"triggered": False, "reason": "exited before a target child was seen",
                    "returncode": proc.returncode, "stderr_tail": err.decode()[-600:]}
        tree = descendants(proc.pid, ps())
        if any(is_target(c, leg) for c in tree.values()):
            break
        time.sleep(POLL_S)
    else:
        proc.kill()
        return {"triggered": False, "reason": "no target child within timeout"}
    time.sleep(0.3)
    tree = descendants(proc.pid, ps())
    before = store_state(store)
    os.kill(proc.pid, sig)
    t_sig = time.monotonic()
    snaps = []
    for at in SNAP_S:
        time.sleep(max(0.0, at - (time.monotonic() - t_sig)))
        table = ps()
        alive = {pid: {"ppid": table[pid][0], "cmd": table[pid][1][:160]}
                 for pid in tree if pid in table}
        snaps.append({"t_after_signal_s": at, "parent_alive": proc.poll() is None,
                      "survivors": alive, "store_files_bytes": store_state(store)})
    try:
        _, err = proc.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        _, err = proc.communicate()
    killed = []
    table = ps()
    for pid in tree:
        if pid in table:
            os.kill(pid, signal.SIGKILL)
            killed.append(pid)
    return {"triggered": True, "returncode": proc.returncode,
            "stderr_tail": err.decode()[-600:],
            "tree_at_signal": {str(k): v[:160] for k, v in tree.items()},
            "store_files_bytes_at_signal": before, "snapshots": snaps,
            "cleanup_sigkilled": killed}


def main() -> None:
    from tests.fixtures.generators.poststack3d import make_poststack3d

    RUN_ROOT.mkdir(parents=True, exist_ok=False)
    source = RUN_ROOT / "p11.sgy"
    make_poststack3d(source, **FIXTURE)
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    full = RUN_ROOT / "complete.mdio"
    base = subprocess.run([SDIP, "ingest", str(source), str(full)], capture_output=True,
                          text=True, check=False)
    cells = [("ingest", signal.SIGTERM), ("ingest", signal.SIGINT),
             ("verify", signal.SIGTERM), ("verify", signal.SIGINT)]
    results = {}
    for leg, sig in cells:
        runs, attempts = [], 0
        while sum(r["triggered"] for r in runs) < N and attempts < MAX_ATTEMPTS:
            attempts += 1
            store = RUN_ROOT / f"{leg}-{sig.name}-{attempts}.mdio" if leg == "ingest" else full
            runs.append(one_run(leg, sig, source, store))
        results[f"{leg}/{sig.name}"] = runs
    print(json.dumps({"probe": "P11", "fixture": FIXTURE, "source_bytes": source.stat().st_size,
                      "source_sha256": digest, "baseline_ingest_returncode": base.returncode,
                      "N": N, "results": results}, indent=1))


if __name__ == "__main__":
    main()
```
