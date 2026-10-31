"""**D8 residual 3: a file hostile in two ways at once.** Probe P15, see `prereg/`.

The D8 corpus isolates one hostility per file. A check written for one hostility can assume
every other field is sane, so this suite combines two corpus mutations from different classes
in one file (:data:`~tests.fixtures.generators.hostile.PAIRS`) and runs each pair through the
unchanged D8 harness: the library ingest, then ``sdip ingest``, ``verify``, ``export`` and
``certify``, in a child process, with the filesystem and peak RSS observed around it.

Every pair is judged by :func:`falsifier_hits`, the six clauses P15 registered before the run.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from sdip.ingest import ingest
from tests.fixtures.generators.hostile import (
    PAIRS,
    REPRESENTATIVE_PAIRS,
    build_pair,
    build_positive_control,
    pair_name,
)
from tests.negative.test_d8_hostile_corpus import (
    PEAK_RSS_CEILING_BYTES,
    Run,
    _run_one,
)

pytestmark = [pytest.mark.negative, pytest.mark.integration, pytest.mark.slow]

UPSTREAM_GRID_TYPES = frozenset({"GridTraceSparsityError", "GridTraceCountError"})
"""MDIO's typed grid refusals that probe P5 pinned (``DECISIONS.md`` D-0036)."""

CLI_PHASES = ("cli", "verify", "export", "certify")


def falsifier_hits(run: Run) -> list[str]:
    """Every P15 falsifier clause this run meets. Empty means the pair is clean."""
    if run.returncode != 0 or run.report is None:
        return [f"1: child exited {run.returncode} without a report: {run.stderr[-600:]}"]
    hits = []
    api = run.api
    if (
        api["outcome"] != "returned"
        and not api["is_sdip_error"]
        and api["type"] not in UPSTREAM_GRID_TYPES
    ):
        hits.append(f"2: library raised {api['module']}.{api['type']}: {api['message'][:200]}")
    for phase in CLI_PHASES:
        record = run.report[phase]
        stderr = str(record["stderr"])
        if record["escaped"] is not None:
            hits.append(f"3: {phase} let {record['escaped']} escape")
        if record["exit_code"] == 3:
            hits.append(f"3: {phase} exit 3")
        if "Traceback" in stderr:
            hits.append(f"3: {phase} printed a traceback")
        if "internal error" in stderr:
            hits.append(f"3: {phase} reported an internal error")
    if run.peak_rss > PEAK_RSS_CEILING_BYTES:
        hits.append(f"4: peak RSS {run.peak_rss} B")
    if run.created_outside_output:
        hits.append(f"5: created outside output: {sorted(run.created_outside_output)[:5]}")
    if run.created_in_repository:
        hits.append(f"5: created in repository: {sorted(run.created_in_repository)[:5]}")
    if api["outcome"] != "returned" and run.cli["exit_code"] == 0:
        hits.append("6: CLI ingest exit 0 on a file the library refused")
    return hits


@pytest.fixture(scope="module")
def harness(tmp_path_factory) -> tuple[Path, Path]:
    """A run root, and the positive control's store that verify/export/certify read."""
    root = tmp_path_factory.mktemp("d8pairs")
    control = build_positive_control(root / "corpus")
    store = root / "control.mdio"
    ingest(control, store)
    return root, store


def run_pair(root: Path, store: Path, a: str, b: str) -> Run:
    """Build one pair and run it through the D8 child."""
    source = build_pair(root / "corpus", a, b)
    return _run_one(pair_name(a, b), "pair", source, root, store)


def test_the_pair_set_is_the_registered_one():
    """P15 registered N = 223 and a 21-pair representative set; drift is a new probe."""
    assert len(PAIRS) == 223
    assert len(set(PAIRS)) == 223
    assert len(REPRESENTATIVE_PAIRS) == 21
    assert set(REPRESENTATIVE_PAIRS) <= set(PAIRS)


def test_a_pair_carries_both_mutations(tmp_path):
    """Non-vacuity for the builder: a pair differs from each of its single members."""
    from tests.fixtures.generators.hostile import CORPUS

    single = {f.name: f for f in CORPUS}
    a, b = "trace_samples_negative", "sample_interval_zero"
    pair = build_pair(tmp_path / "p", a, b).read_bytes()
    one = single[a].write(tmp_path / "a").path.read_bytes()
    two = single[b].write(tmp_path / "b").path.read_bytes()
    assert pair not in (one, two)
    differ_one = {i for i, (x, y) in enumerate(zip(pair, one, strict=True)) if x != y}
    differ_two = {i for i, (x, y) in enumerate(zip(pair, two, strict=True)) if x != y}
    assert differ_one and differ_two and not differ_one & differ_two


def test_the_positive_control_is_clean_through_the_identical_harness(harness):
    """SP11: the harness can return a clean run, so a clean pair means something."""
    root, store = harness
    from tests.fixtures.generators.hostile import build_positive_control as control

    run = _run_one("positive_control", "control", control(root / "pc"), root, store)
    assert falsifier_hits(run) == []
    assert run.ingested
    assert run.report["verify"]["exit_code"] == 0
    assert run.report["export"]["exit_code"] == 0


CAMPAIGN = pytest.mark.campaign
"""The 202 non-representative pairs: P15 measured the 223 at 838 s, above its registered
600 s, so by the registration they run under ``-m campaign`` and not in the default suite."""

PAIR_PARAMS = [
    pytest.param(a, b, id=pair_name(a, b), marks=() if (a, b) in REPRESENTATIVE_PAIRS else CAMPAIGN)
    for a, b in PAIRS
]


@pytest.mark.parametrize(("a", "b"), PAIR_PARAMS)
def test_no_pair_crashes_leaks_or_escapes(harness, a, b):
    """Every command ends in a typed refusal or a verdict on a doubly hostile file."""
    root, store = harness
    hits = falsifier_hits(run_pair(root, store, a, b))
    assert hits == [], f"{pair_name(a, b)}: {hits}"
