"""P35's harness, shown able to fail before it is trusted to find nothing (G7 discipline).

- A planted crash (an untyped exception on a trace-0 inline that is odd) must register as H1,
  with a reproducer minimised to the bytes that cause it.
- A planted hang under a 1 s alarm must register as H2.
- With the real target, coverage must grow past the seeds, or the guidance is vacuous.
- Mutation is deterministic for a seed.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from tests.fuzz.coverage_fuzz import FILE_HEADER, default_target, mutate, seed_corpus, worker

pytestmark = [pytest.mark.negative, pytest.mark.integration]

INLINE = slice(FILE_HEADER + 188, FILE_HEADER + 192)


def _odd_inline(path: Path) -> bool:
    raw = path.read_bytes()
    return len(raw) >= INLINE.stop and int.from_bytes(raw[INLINE], "big") % 2 == 1


def _events(root: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in (root / "events.jsonl").read_text().splitlines()]


def test_a_planted_crash_is_an_h1_hit_with_a_minimised_reproducer(tmp_path):
    def planted(path: Path) -> dict[str, Any]:
        if _odd_inline(path):
            raise ZeroDivisionError("planted")
        return default_target(path)

    worker(
        tmp_path, cap_s=1e9, alarm_s=30, restart=0, target=planted, run_child=False, max_execs=1500
    )
    hits = [e for e in _events(tmp_path) if e["event"] == "hit"]
    assert hits and all(h["kind"] == "H1" for h in hits), hits[:3]
    assert "ZeroDivisionError: planted" in hits[0]["detail"]
    kept = sorted((tmp_path / "hits").glob("H1-*.bin"))
    assert kept
    reproducer = kept[0]
    assert _odd_inline(reproducer)


def test_a_planted_hang_is_an_h2_hit(tmp_path):
    def planted(path: Path) -> dict[str, Any]:
        if _odd_inline(path):
            time.sleep(5)
        return default_target(path)

    worker(
        tmp_path, cap_s=1e9, alarm_s=1, restart=0, target=planted, run_child=False, max_execs=1500
    )
    hits = [e for e in _events(tmp_path) if e["event"] == "hit"]
    assert hits and hits[0]["kind"] == "H2", hits[:3]


def test_coverage_grows_past_the_seeds_with_the_real_target(tmp_path):
    worker(tmp_path, cap_s=1e9, alarm_s=30, restart=0, run_child=False, max_execs=600)
    events = _events(tmp_path)
    start = next(e for e in events if e["event"] == "start")
    end = next(e for e in events if e["event"] == "end")
    assert start["locations"] > 0
    assert end["locations"] > start["locations"], (start, end)
    assert any(e["event"] == "new" for e in events)
    assert not [e for e in events if e["event"] == "hit"]


def test_mutation_is_deterministic_for_a_seed(tmp_path):
    seeds = list(seed_corpus(tmp_path).values())
    one = [mutate(np.random.default_rng(7), seeds[0], seeds[1]) for _ in range(1)]
    two = [mutate(np.random.default_rng(7), seeds[0], seeds[1]) for _ in range(1)]
    assert one == two
    rng = np.random.default_rng(7)
    assert any(mutate(rng, seeds[0], seeds[1]) != seeds[0] for _ in range(20))


def test_the_seeds_are_the_registered_35(tmp_path):
    seeds = seed_corpus(tmp_path)
    assert len(seeds) == 1 + 23 + 9 + 2
