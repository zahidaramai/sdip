"""Coverage-guided fuzzing of SDIP's untrusted-input entry points (D8, probe P35).

**No dependency.** Coverage comes from CPython 3.12's ``sys.monitoring``: LINE and BRANCH events
on code under ``sdip`` and ``segy``. Each callback returns ``DISABLE``, so a location fires once
in the whole run, and an input that makes one fire has reached code no earlier input reached.
That input joins the corpus (AFL's rule). atheris needs libFuzzer, which Apple clang does not
ship, and the shared ``.venv`` takes no new package (DECISIONS.md D-0139).

**The target**, in-process, on bytes written to a file:
1. ``validate_source`` (SDIP's pre-allocation layer);
2. ``read_raw_file_headers`` and ``classify_textual_header``;
3. ``read_header_columns`` (``segy``'s parser through SDIP's blocked reader).

Steps 1 and 2 are SDIP's own: anything but an :class:`~sdip.errors.SdipError` out of them is a
**hit** (H1). Step 3 reaches upstream: an exception there is recorded, and the input goes to
the D8 child, which judges what the operator would see. A target that runs past ``alarm_s`` is
a **hit** (H2). A worker process that dies is a **hit** (H3); the supervisor reads the input
it was running from ``inflight.bin``.

**The D8 child**, unchanged: every input that joins the corpus, every one that passes step 1,
and each distinct upstream exception runs through library ``ingest`` and CLI ``ingest``,
``verify``, ``export`` and ``certify``. Any of P15's six clauses is a **hit** (H4).

Run: ``python -m tests.fuzz.coverage_fuzz RUN_ROOT --cap-s 7200`` from the repository root.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import signal
import subprocess
import sys
import time
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import Any

import numpy as np

SEED = 20261105
TOOL_ID = 3
COVERED_PACKAGES = (f"{os.sep}sdip{os.sep}", f"{os.sep}segy{os.sep}")
FILE_HEADER = 3600
TRACE_HEADER = 240
INTERESTING = (0, 1, 0x7F, 0x80, 0xFF)
INTERESTING_16 = (0, 1, -1, 0x7FFF, -0x8000, 0x0100, 0xFFFF)
INTERESTING_32 = (0, 1, -1, 0x7FFFFFFF, -0x80000000, 0x00010000)
HEADER_FIELDS = ("inline", "crossline", "delay_recording_time", "times_scalar")


# --- coverage -------------------------------------------------------------------------------


class Coverage:
    """Locations reached so far. ``fresh`` counts those first reached since the last reset."""

    def __init__(self) -> None:
        """Nothing reached yet."""
        self.locations: set[tuple[Any, ...]] = set()
        self.fresh = 0

    def _keep(self, code: Any) -> bool:
        return any(p in code.co_filename for p in COVERED_PACKAGES)

    def _line(self, code: Any, line: int) -> Any:
        if self._keep(code):
            self.locations.add((code.co_filename, code.co_qualname, "L", line))
            self.fresh += 1
        return sys.monitoring.DISABLE

    def _branch(self, code: Any, src: int, dst: int) -> Any:
        if self._keep(code):
            self.locations.add((code.co_filename, code.co_qualname, "B", src, dst))
            self.fresh += 1
        return sys.monitoring.DISABLE

    def start(self) -> None:
        """Register the callbacks and turn LINE and BRANCH events on."""
        m = sys.monitoring
        m.use_tool_id(TOOL_ID, "sdip-p35")
        m.register_callback(TOOL_ID, m.events.LINE, self._line)
        m.register_callback(TOOL_ID, m.events.BRANCH, self._branch)
        m.set_events(TOOL_ID, m.events.LINE | m.events.BRANCH)
        # A location some earlier run returned DISABLE for stays disabled across tool ids until
        # this is called, so coverage would silently start from that run's state.
        m.restart_events()

    def stop(self) -> None:
        """Turn events off and release the tool id."""
        m = sys.monitoring
        m.set_events(TOOL_ID, m.events.NO_EVENTS)
        m.free_tool_id(TOOL_ID)

    def take_fresh(self) -> int:
        """Locations first reached since the last call."""
        fresh, self.fresh = self.fresh, 0
        return fresh


# --- the target -----------------------------------------------------------------------------


def default_target(path: Path) -> dict[str, Any]:
    """Run the three steps on ``path``. Returns the outcome; raises only to report a hit."""
    from sdip.errors import SdipError
    from sdip.ingest.file_headers import classify_textual_header, read_raw_file_headers
    from sdip.ingest.orchestrator import validate_source
    from sdip.ingest.source_headers import read_header_columns
    from sdip.spec.declaration import SurveyDeclaration

    declaration = SurveyDeclaration(revision=1, template="PostStack3DTime")
    try:
        validate_source(path, declaration)
    except SdipError as exc:
        return {"outcome": "refused", "step": 1, "type": type(exc).__name__}
    spec = declaration.build_spec().segy_spec
    try:
        raw = read_raw_file_headers(path)
        classify_textual_header(raw.textual, spec.text_header)
    except SdipError as exc:
        return {"outcome": "refused", "step": 2, "type": type(exc).__name__}
    try:
        read_header_columns(path, spec, HEADER_FIELDS)
    except SdipError as exc:
        return {"outcome": "refused", "step": 3, "type": type(exc).__name__}
    except Exception as exc:  # recording the type IS the measurement
        return {
            "outcome": "upstream_raised",
            "step": 3,
            "type": type(exc).__name__,
            "message": str(exc)[:160],
        }
    return {"outcome": "admitted", "step": 3}


class HitError(Exception):
    """A target outcome that is a falsifier hit by construction (H1, H2)."""

    def __init__(self, kind: str, detail: str) -> None:
        """Record the hit's class and what was seen."""
        super().__init__(f"{kind}: {detail}")
        self.kind, self.detail = kind, detail


class _AlarmError(Exception):
    """The alarm interrupted the target."""


def _on_alarm(_signum: int, _frame: Any) -> None:
    raise _AlarmError


def run_target(
    target: Callable[[Path], dict[str, Any]], path: Path, alarm_s: int
) -> dict[str, Any]:
    """One execution of the target under an alarm.

    H1 is an untyped exception out of steps 1-2, which the target lets escape. H2 is the alarm.
    """
    signal.signal(signal.SIGALRM, _on_alarm)
    signal.alarm(alarm_s)
    try:
        return target(path)
    except _AlarmError:
        raise HitError("H2", f"target ran past {alarm_s} s") from None
    except Exception as exc:  # recording the type IS the measurement
        raise HitError(
            "H1", f"{type(exc).__module__}.{type(exc).__name__}: {str(exc)[:200]}"
        ) from None
    finally:
        signal.alarm(0)


# --- inputs ---------------------------------------------------------------------------------


def seed_corpus(root: Path) -> dict[str, bytes]:
    """The registered seeds, all rebuilt from committed generators.

    The positive control, the 23 single mutations, and the files P29 and P34 saw convert.
    """
    from tests.fixtures.generators.hostile import (
        MUTATIONS,
        build_combination,
        build_positive_control,
    )

    seeds = {"positive_control": build_positive_control(root / "seeds").read_bytes()}
    for name in MUTATIONS:
        seeds[name] = build_combination(root / "seeds", (name,)).read_bytes()
    for receipt in ("P29-receipt-2026-11-05.json", "P34-receipt-2026-11-05.json"):
        path = Path(__file__).resolve().parents[2] / "prereg" / receipt
        for item in json.loads(path.read_text())["certify_failures_classified"]["per_file"]:
            seeds[item] = build_combination(root / "seeds", tuple(item.split("+"))).read_bytes()
    for leftover in (root / "seeds").glob("*"):
        leftover.unlink()
    return dict(sorted(seeds.items()))


def _structural_offset(rng: np.random.Generator, data: bytearray) -> int:
    """An offset in the binary header, or in one of the first four trace headers."""
    size = len(data)
    if size <= 3200:
        return int(rng.integers(0, size))
    if size <= FILE_HEADER or rng.random() < 0.4:
        return int(rng.integers(3200, min(size, FILE_HEADER)))
    samples = int.from_bytes(bytes(data[3220:3222]), "big")
    stride = TRACE_HEADER + 4 * samples if 0 < samples < 100_000 else TRACE_HEADER
    trace = int(rng.integers(0, 4))
    return min(size - 1, FILE_HEADER + trace * stride + int(rng.integers(0, TRACE_HEADER)))


def mutate(rng: np.random.Generator, data: bytes, other: bytes) -> bytes:
    """One seeded mutation of ``data``.

    A byte, a 16- or 32-bit interesting value, a truncation or extension, or a splice of
    ``other``'s binary header.
    """
    out = bytearray(data)
    if not out:
        return bytes(other[:FILE_HEADER])
    kind = int(rng.integers(0, 7))
    off = _structural_offset(rng, out)
    if kind == 0:
        out[off] ^= 1 << int(rng.integers(0, 8))
    elif kind == 1:
        out[off] = INTERESTING[int(rng.integers(0, len(INTERESTING)))]
    elif kind == 2 and off + 2 <= len(out):
        v = INTERESTING_16[int(rng.integers(0, len(INTERESTING_16)))]
        out[off : off + 2] = (v & 0xFFFF).to_bytes(2, "big")
    elif kind == 3 and off + 4 <= len(out):
        v = INTERESTING_32[int(rng.integers(0, len(INTERESTING_32)))]
        out[off : off + 4] = (v & 0xFFFFFFFF).to_bytes(4, "big")
    elif kind == 4:
        cut = int(rng.integers(max(1, len(out) // 2), len(out) + 1))
        del out[cut:]
    elif kind == 5:
        out.extend(out[-int(rng.integers(1, min(len(out), 4 * TRACE_HEADER) + 1)) :])
    else:
        n = min(len(out), len(other), FILE_HEADER)
        a = int(rng.integers(3200, max(3201, n)))
        out[a:n] = other[a:n]
    return bytes(out)


def minimise(fails: Callable[[bytes], bool], hit: bytes, parent: bytes) -> bytes:
    """Revert ranges of ``hit`` to ``parent`` while it still fails the same way."""
    best = bytearray(hit)
    if len(best) != len(parent):
        return bytes(best)
    width = max(1, len(best) // 2)
    while width >= 1:
        i = 0
        while i < len(best):
            trial = bytearray(best)
            trial[i : i + width] = parent[i : i + width]
            if trial != best and fails(bytes(trial)):
                best = trial
            i += width
        width //= 2
    return bytes(best)


# --- the worker -----------------------------------------------------------------------------


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _child(name: str, data: bytes, root: Path, store: Path) -> dict[str, Any]:
    from tests.negative.test_d8_hostile_corpus import _run_one
    from tests.negative.test_d8_hostile_pairs import falsifier_hits

    source = root / "child_inputs" / f"{name}.sgy"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes(data)
    run = _run_one(name, "p35", source, root, store)
    hits = falsifier_hits(run)
    report = run.report or {}
    api = report.get("api") or {}
    import shutil

    shutil.rmtree(root / "runs" / name, ignore_errors=True)
    source.unlink(missing_ok=True)
    return {
        "name": name,
        "hits": hits,
        "api": api.get("outcome"),
        "type": api.get("type"),
        "exit": {
            p: (report.get(p) or {}).get("exit_code")
            for p in ("cli", "verify", "export", "certify")
        },
        "peak_rss": report.get("peak_rss_bytes"),
    }


def worker(
    root: Path,
    cap_s: float,
    alarm_s: int,
    restart: int,
    target: Callable[[Path], dict[str, Any]] = default_target,
    run_child: bool = True,
    max_execs: int | None = None,
) -> None:
    """The fuzz loop. Appends JSON lines to ``root/events.jsonl``; returns at the cap."""
    rng = np.random.default_rng(SEED + restart)
    corpus_dir = root / "corpus"
    corpus_dir.mkdir(parents=True, exist_ok=True)
    events = (root / "events.jsonl").open("a")
    started = float((root / "started").read_text()) if (root / "started").exists() else time.time()
    (root / "started").write_text(str(started))

    def log(rec: dict[str, Any]) -> None:
        events.write(json.dumps(rec | {"t": round(time.time() - started, 2)}) + "\n")
        events.flush()

    corpus: list[tuple[str, bytes]] = []
    if restart == 0:
        for name, data in seed_corpus(root).items():
            (corpus_dir / f"{name}.bin").write_bytes(data)
    for f in sorted(corpus_dir.glob("*.bin")):
        corpus.append((f.stem, f.read_bytes()))
    scratch = root / "exec.sgy"
    inflight = root / "inflight.bin"
    cov = Coverage()
    cov.start()
    store = None
    pool = ThreadPoolExecutor(max_workers=2) if run_child else None
    pending: list[Future[dict[str, Any]]] = []
    upstream_seen: set[str] = set()
    if run_child:
        from sdip.ingest import ingest
        from tests.fixtures.generators.hostile import build_positive_control

        store = root / "control.mdio"
        if not store.exists():
            ingest(build_positive_control(root / "control_src"), store)

    def execute(name: str, data: bytes, parent: bytes | None) -> dict[str, Any] | None:
        inflight.write_bytes(data)
        (root / "inflight.json").write_text(
            json.dumps({"name": name, "parent_sha256": _sha(parent) if parent else None})
        )
        scratch.write_bytes(data)
        try:
            result = run_target(target, scratch, alarm_s)
        except HitError as hit:
            kind = hit.kind

            def fails(trial: bytes) -> bool:
                scratch.write_bytes(trial)
                try:
                    run_target(target, scratch, alarm_s)
                except HitError as again:
                    return again.kind == kind
                return False

            # A hang is kept as found: each minimisation trial of one costs a full alarm.
            small = minimise(fails, data, parent) if parent is not None and kind == "H1" else data
            (root / "hits").mkdir(exist_ok=True)
            (root / "hits" / f"{hit.kind}-{_sha(small)[:12]}.bin").write_bytes(small)
            log(
                {
                    "event": "hit",
                    "kind": hit.kind,
                    "detail": hit.detail,
                    "name": name,
                    "sha256": _sha(small),
                    "bytes": len(small),
                }
            )
            return None
        return result

    try:
        for name, data in corpus:  # replay rebuilds coverage after a restart
            execute(name, data, None)
        cov.take_fresh()
        log(
            {
                "event": "start",
                "restart": restart,
                "corpus": len(corpus),
                "locations": len(cov.locations),
            }
        )
        execs, last_sample, dropped_admitted = 0, 0.0, 0
        while time.time() - started < cap_s and (max_execs is None or execs < max_execs):
            i = int(rng.integers(0, len(corpus)))
            j = int(rng.integers(0, len(corpus)))
            parent = corpus[i][1]
            data = mutate(rng, parent, corpus[j][1])
            for _ in range(int(rng.integers(0, 3))):
                data = mutate(rng, data, corpus[j][1])
            name = f"r{restart}_x{execs}"
            result = execute(name, data, parent if len(parent) == len(data) else None)
            execs += 1
            fresh = cov.take_fresh()
            if result is None:
                continue
            send = False
            if fresh:
                (corpus_dir / f"{name}.bin").write_bytes(data)
                corpus.append((name, data))
                log(
                    {
                        "event": "new",
                        "name": name,
                        "fresh": fresh,
                        "outcome": result["outcome"],
                        "step": result.get("step"),
                        "type": result.get("type"),
                    }
                )
                send = True
            best_effort = result["outcome"] == "admitted" and not send
            if result["outcome"] == "upstream_raised":
                key = f"{result['type']}:{result.get('message', '')[:60]}"
                if key not in upstream_seen:
                    upstream_seen.add(key)
                    log(
                        {
                            "event": "upstream",
                            "name": name,
                            "type": result["type"],
                            "message": result.get("message"),
                        }
                    )
                    send = True
            if pool is not None and store is not None:
                if send:
                    pending.append(pool.submit(_child, name, data, root, store))
                elif best_effort:
                    if len(pending) < 8:
                        pending.append(pool.submit(_child, name, data, root, store))
                    else:
                        dropped_admitted += 1
            done = [f for f in pending if f.done()]
            for f in done:
                pending.remove(f)
                rec = f.result()
                log({"event": "child"} | rec)
                if rec["hits"]:
                    log({"event": "hit", "kind": "H4", "detail": rec["hits"], "name": rec["name"]})
            now = time.time() - started
            if now - last_sample >= 30:
                last_sample = now
                log(
                    {
                        "event": "sample",
                        "execs": execs,
                        "corpus": len(corpus),
                        "locations": len(cov.locations),
                        "children_pending": len(pending),
                        "admitted_not_sent": dropped_admitted,
                    }
                )
            while len(pending) > 64:  # back-pressure: the child is the slow half
                time.sleep(0.5)
                for f in [f for f in pending if f.done()]:
                    pending.remove(f)
                    rec = f.result()
                    log({"event": "child"} | rec)
                    if rec["hits"]:
                        log(
                            {
                                "event": "hit",
                                "kind": "H4",
                                "detail": rec["hits"],
                                "name": rec["name"],
                            }
                        )
    finally:
        cov.stop()
        for f in pending:  # children already queued finish; none is dropped
            rec = f.result()
            log({"event": "child"} | rec)
            if rec["hits"]:
                log({"event": "hit", "kind": "H4", "detail": rec["hits"], "name": rec["name"]})
        log(
            {
                "event": "end",
                "execs": execs,
                "corpus": len(corpus),
                "locations": len(cov.locations),
                "admitted_not_sent": dropped_admitted,
            }
        )
        if pool is not None:
            pool.shutdown(wait=True)
        events.close()
    inflight.unlink(missing_ok=True)


def supervise(root: Path, cap_s: float, alarm_s: int) -> None:
    """Restart the worker when it dies; a death is H3, a stall past 4 x alarm_s is H2."""
    root.mkdir(parents=True, exist_ok=True)
    restart = 0
    while True:
        proc = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "tests.fuzz.coverage_fuzz",
                str(root),
                "--cap-s",
                str(cap_s),
                "--alarm-s",
                str(alarm_s),
                "--worker",
                str(restart),
            ],
            cwd=Path(__file__).resolve().parents[2],
        )
        stalled = False
        while proc.poll() is None:
            time.sleep(5)
            inflight = root / "inflight.bin"
            if inflight.exists() and time.time() - inflight.stat().st_mtime > 4 * alarm_s + 600:
                proc.kill()
                proc.wait()
                stalled = True
        if proc.returncode == 0 and not stalled:
            return
        with (root / "events.jsonl").open("a") as ev:
            data = (root / "inflight.bin").read_bytes() if (root / "inflight.bin").exists() else b""
            (root / "hits").mkdir(exist_ok=True)
            (root / "hits" / f"{'H2' if stalled else 'H3'}-{_sha(data)[:12]}.bin").write_bytes(data)
            ev.write(
                json.dumps(
                    {
                        "event": "hit",
                        "kind": "H2" if stalled else "H3",
                        "detail": "worker stalled"
                        if stalled
                        else f"worker exited {proc.returncode}",
                        "sha256": _sha(data),
                        "bytes": len(data),
                    }
                )
                + "\n"
            )
        (root / "inflight.bin").unlink(missing_ok=True)
        restart += 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("root", type=Path)
    ap.add_argument("--cap-s", type=float, default=7200)
    ap.add_argument("--alarm-s", type=int, default=30)
    ap.add_argument("--worker", type=int, default=None)
    a = ap.parse_args()
    if a.worker is None:
        supervise(a.root, a.cap_s, a.alarm_s)
    else:
        worker(a.root, a.cap_s, a.alarm_s, a.worker)
