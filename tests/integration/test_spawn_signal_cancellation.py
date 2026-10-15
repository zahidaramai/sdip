"""A signal to `sdip` stops every child it started and exits 128 + N (D-0093, issue #1 (a)).

Measured through the ``sdip`` executable, never one layer below it (D-0087): the
handlers are installed by the console entry point, so an in-process call would test a
path no operator takes.

**Attribution survives reparenting.** Each invocation runs with a unique environment tag,
which spawned workers inherit. A child that outlives ``sdip`` is reparented and can no
longer be found by walking the tree from ``sdip``; it can still be found by its tag
(``prereg/P11-signal-cancellation.md`` Amendment A, where the tree alone could not say
whose an orphan was).

**The failing configuration is permanent.** Before D-0093 nothing installed a handler:
SIGTERM killed ``sdip`` outright and SIGINT exited 2, the usage code. Each test asserts
the exact code, the absence of every tagged process, and - for ingest - a store with no
provenance marker, which is how an incomplete store reads.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
import uuid
from collections.abc import Callable
from pathlib import Path

import pytest
import zarr

from sdip.ingest import ingest
from sdip.ingest.provenance_marker import ATTR_WRITER
from tests.fixtures.generators.poststack3d import make_poststack3d

pytestmark = pytest.mark.integration
# Deliberately not `slow`: CI's integration lane runs `-m 'not slow'`, and a `slow`
# correctness test is how D62's certify test never ran there (D-0091).

SDIP = str(Path(sys.executable).parent / "sdip")
FIXTURE = {"n_inline": 100, "n_crossline": 100, "n_samples": 1000}
"""Enough traces that the pools are alive long enough to be signalled."""
DETECT_S = 180.0
SETTLE_S = 10.0


def _tagged(tag: str) -> dict[int, str]:
    out = subprocess.run(
        ["ps", "eww", "-A", "-o", "pid=,command="], capture_output=True, text=True, check=True
    ).stdout
    found = {}
    for line in out.splitlines():
        pid, _, command = line.strip().partition(" ")
        if f"SDIP_SIGNAL_TEST={tag}" in command:
            found[int(pid)] = command.split(" SDIP_SIGNAL_TEST=")[0][:120]
    return found


def _signal_once_child_is_live(
    argv: list[str],
    marker: str,
    sig: int,
    work: Path,
    ready: Callable[[], bool] = lambda: True,
) -> dict:
    """Start ``argv``; once a ``marker`` child is live and ``ready()``, signal ``sdip``."""
    tag = uuid.uuid4().hex
    env = dict(os.environ, SDIP_SIGNAL_TEST=tag)
    with (work / f"{tag}.out").open("wb") as out, (work / f"{tag}.err").open("wb") as err:
        proc = subprocess.Popen(argv, stdout=out, stderr=err, env=env, start_new_session=True)
        try:
            deadline = time.monotonic() + DETECT_S
            seen = False
            while time.monotonic() < deadline and proc.poll() is None:
                children = {p: c for p, c in _tagged(tag).items() if p != proc.pid}
                live = any(marker in c and "resource_tracker" not in c for c in children.values())
                if live and ready():
                    seen = True
                    break
                time.sleep(0.02)
            if not seen:
                pytest.fail(f"no live {marker!r} child to signal; sdip exited {proc.poll()}")
            os.kill(proc.pid, sig)
            code = proc.wait(timeout=60)
            time.sleep(1.0)
            deadline = time.monotonic() + SETTLE_S
            survivors = _tagged(tag)
            while survivors and time.monotonic() < deadline:
                time.sleep(0.5)
                survivors = _tagged(tag)
        finally:
            for pid in _tagged(tag):
                try:
                    os.kill(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            if proc.poll() is None:
                proc.kill()
                proc.wait()
    return {
        "code": code,
        "survivors": survivors,
        "stderr": (work / f"{tag}.err").read_text(errors="replace"),
    }


@pytest.fixture(scope="module")
def source(tmp_path_factory) -> Path:
    work = tmp_path_factory.mktemp("signals")
    return make_poststack3d(work / "signals.sgy", **FIXTURE).path


@pytest.mark.parametrize(("sig", "code"), [(signal.SIGTERM, 143), (signal.SIGINT, 130)])
def test_a_signalled_ingest_stops_its_pool_and_exits_terminated(source, tmp_path, sig, code):
    store = tmp_path / "partial.mdio"
    outcome = _signal_once_child_is_live(
        [SDIP, "ingest", str(source), str(store)], "spawn_main", sig, tmp_path
    )
    assert outcome["code"] == code, outcome["stderr"][-800:]
    assert outcome["survivors"] == {}, outcome["survivors"]
    assert "terminated by" in outcome["stderr"]
    if (store / "zarr.json").exists():
        attrs = dict(zarr.open_group(str(store), mode="r").attrs)
        assert ATTR_WRITER not in attrs, "a store cut short must not carry the marker"


def test_a_signal_while_traces_are_being_written_does_not_drain_the_queue(source, tmp_path):
    """The case the handler's ordering exists for (see ``sdip.cli.signals``).

    The trace-writing pool is entered with ``with``; unwinding through it alone would wait
    for every queued block. Signalled once amplitude chunks are on disk and a worker is
    live, ``sdip`` must stop with blocks still unwritten.
    """
    store = tmp_path / "writing.mdio"
    chunks = store / "amplitude" / "c"

    def writing() -> bool:
        return chunks.is_dir() and any(p.is_file() for p in chunks.rglob("*"))

    outcome = _signal_once_child_is_live(
        [SDIP, "ingest", str(source), str(store)], "spawn_main", signal.SIGTERM, tmp_path, writing
    )
    assert outcome["code"] == 143, outcome["stderr"][-800:]
    assert outcome["survivors"] == {}, outcome["survivors"]
    attrs = dict(zarr.open_group(str(store), mode="r").attrs)
    assert ATTR_WRITER not in attrs, "a store cut short must not carry the marker"


@pytest.fixture(scope="module")
def store(source, tmp_path_factory) -> Path:
    target = tmp_path_factory.mktemp("signals_store") / "complete.mdio"
    ingest(source, target)
    return target


def test_a_signalled_verify_stops_its_grandchild_and_exits_terminated(source, store, tmp_path):
    outcome = _signal_once_child_is_live(
        [SDIP, "verify", str(source), str(store)], " -c ", signal.SIGTERM, tmp_path
    )
    assert outcome["code"] == 143, outcome["stderr"][-800:]
    assert outcome["survivors"] == {}, outcome["survivors"]
    assert "No verdict was reached" in outcome["stderr"]
