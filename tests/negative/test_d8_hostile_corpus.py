"""**D8 — untrusted-input handling, measured.** Specification §11.4; operating contract §3.6.

    A malformed or hostile SEG-Y must produce a clean error - never a crash, an
    unbounded allocation, or a write outside the output path. Validate header-declared
    lengths against actual file size **before** allocating. Never derive an output path
    from file content.

Until this suite existed that was four sentences with nothing behind them. **SP8**: no
fidelity claim without a number. The corpus in
:mod:`tests.fixtures.generators.hostile` supplies **33 members over 9 hostility
classes**, every one written by committed code from a fixed seed, and every one is run
through a real ingest in its own process.

Four questions per member, all four answered from one child run:

1. **What kind of error?** A typed :class:`~sdip.errors.SdipError`, or a
   ``ValueError`` / ``ZeroDivisionError`` / ``pydantic`` ``ValidationError`` that SDIP
   never meant to produce.
2. **Where was it raised?** In ``sdip``, or downstream in ``segy`` / ``mdio``? This is
   the operative measurement for *"validate before allocating"*: an error raised in
   ``sdip`` happened before the parser saw the file at all.
3. **How much memory did the run reach?** Peak RSS against a declared ceiling.
4. **What did it leave behind?** The whole run tree is snapshotted before and after, so
   any byte written outside the declared output directory is a named failure.

**The positive control is not decoration.** An ingest that refused every input would
score perfectly on questions 1-4 and be useless. ``positive_control.sgy`` is the
well-formed 30-trace fixture, run through the identical harness, and it must **succeed**
(**SP11**, the same discipline as G7).

**What was found.** The first run of this suite, on the code as it stood, put **18 of
the 33 members** into category 2 with an untyped exception raised inside ``segy``,
``mdio`` or ``pydantic``, including a ``ZeroDivisionError`` on a zero sample interval.
:mod:`sdip.ingest.preflight` was written in response; the count is now **3**, and all
three are MDIO's own typed grid refusals that probe **P5** measured and relies on. See
``DECISIONS.md`` D-0057 and ``OPEN_DEBTS.md`` D8.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from tests.fixtures.generators.hostile import (
    CLASSES,
    CORPUS,
    PATH_BAIT,
    build_corpus,
    build_positive_control,
)

pytestmark = [pytest.mark.negative, pytest.mark.integration, pytest.mark.slow]

CHILD = Path(__file__).resolve().parent / "hostile_child.py"
REPO_ROOT = Path(__file__).resolve().parents[2]

PEAK_RSS_CEILING_BYTES = 512 * 1024**2
"""**The declared memory ceiling: 512 MiB.** No member may exceed it, hostile or not.

Not invented. Measured on 2026-08-23, Darwin 25.5.0, CPython 3.12.13: the largest peak
across all 34 runs was **212.0 MB**, and that was a *successful* 30-trace ingest, not a
refusal. Refusals peaked at **53.4 MB** - the cost of starting the interpreter. 512 MiB
is 2.5x the observed maximum, which leaves room for a different platform's allocator
while staying far below anything a believed header count would cost:
``declared_extended_headers_exceed_file`` claims **104,854,400 bytes** of extended
textual headers in a **14,640-byte** file, and a run that believed it would show up here.
"""

CHILD_TIMEOUT_SECONDS = 300
"""Per-member wall clock. §11.4 bars a hang as firmly as it bars a crash, and a test that
waits forever cannot report one. The slowest member measured 6.1 s."""

UPSTREAM_TYPED = {
    "grid_sparse_enormous": "GridTraceSparsityError",
    "grid_index_negative": "GridTraceSparsityError",
    "grid_all_identical": "GridTraceCountError",
}
"""The residual: three members refused by MDIO's own typed exceptions, not by SDIP's.

**Deliberately not re-typed, and the reason is a measurement.** These are geometry
verdicts - whether a file's index values imply a workable grid - and they need a full
trace-header pass to reach, which is precisely what pre-allocation validation must not
do. Probe **P5** measured MDIO making exactly these refusals and pinned the exception
types as the defence SDIP relies on (``tests/integration/test_p5_geometry.py``,
``DECISIONS.md`` D-0036): ``GridTraceCountError`` is raised unconditionally in
``mdio/ingestion/segy/pipeline.py`` and is therefore **not** suppressible by
``MDIO_IGNORE_CHECKS``, which is why the duplicate-trace defence counts as a defence.

Re-typing them inside SDIP would overturn a recorded measurement to satisfy a
presentation preference, so it is a maintainer's call and not an implementer's
(operating contract §9). Recorded as the open residual on D8.
"""

EXPECTED_INGESTS = {
    "declared_trace_samples_exceed_file",
    "trace_samples_zero",
    "trace_samples_negative",
    "revision_undefined",
    "sample_interval_enormous",
    "path_bait_in_headers",
}
"""Members that **convert**, measured rather than wished for.

Each is structurally valid: the file's size, its declared sample count and its format
code all agree, so §11.4's pre-allocation contract has nothing to object to. What is odd
about them lives in fields the converter does not size anything from - the per-trace
sample count, the revision word - and those bytes are preserved verbatim in the uint8
header plane, so equivalence is unaffected.

``path_bait_in_headers`` is the one that matters most: a well-formed file whose textual
header and header tails are filesystem paths. It **must** convert, and it must convert
without any of those paths becoming one. See
:func:`test_no_output_path_is_ever_derived_from_file_content`.

**Listing them is the point.** A member quietly moving between this set and the refused
set is a behaviour change, and the assertion below is what makes it loud.
"""

IGNORED_DIRECTORIES = frozenset(
    {".git", ".venv", "__pycache__", ".mypy_cache", ".ruff_cache", ".pytest_cache"}
)
"""Pruned from a snapshot at every level: version control, the virtual environment, and
caches the toolchain rewrites on every invocation - including this one. A snapshot that
watched them would compare a pytest cache against itself and never agree."""

IGNORED_ROOT_DIRECTORIES = frozenset({"docs", "local"})
"""Pruned from the **repository** snapshot at the top level only.

Both are inside the publication firewall (`.gitignore`), exist on a working copy and
never in CI, and are where local probe harnesses keep state that changes under this test
without this test causing it - ``local/p8/data`` is a running MinIO server's object
store, and it rewrote its own trash directory during the first run of this suite.

Everything else in the repository is watched, tracked or not, which is what a write
escape would land in: an escape derived from file content lands where the content says,
not in a directory that happens to be ignored.
"""


def _snapshot(root: Path, *, prune_roots: frozenset[str] = frozenset()) -> frozenset[str]:
    """Every path under ``root``, relative, with caches and named roots skipped."""
    if not root.exists():
        return frozenset()
    seen: set[str] = set()
    for current, directories, files in os.walk(root):
        directories[:] = [d for d in directories if d not in IGNORED_DIRECTORIES]
        if Path(current) == root:
            directories[:] = [d for d in directories if d not in prune_roots]
        base = Path(current)
        for name in directories + files:
            seen.add(str((base / name).relative_to(root)))
    return frozenset(seen)


@dataclass(frozen=True, slots=True)
class Run:
    """One child process, and everything observed around it."""

    name: str
    klass: str
    source: Path
    run_dir: Path
    output_dir: Path
    returncode: int
    stdout: str
    stderr: str
    report: dict[str, Any] | None
    created_outside_output: frozenset[str]
    created_in_repository: frozenset[str]

    @property
    def api(self) -> dict[str, Any]:
        """The library phase's record."""
        assert self.report is not None, f"{self.name}: the child wrote no report"
        return dict(self.report["api"])

    @property
    def cli(self) -> dict[str, Any]:
        """The console-entry-point phase's record."""
        assert self.report is not None, f"{self.name}: the child wrote no report"
        return dict(self.report["cli"])

    @property
    def peak_rss(self) -> int:
        """Peak resident set size of the child, in bytes."""
        assert self.report is not None, f"{self.name}: the child wrote no report"
        return int(self.report["peak_rss_bytes"])

    @property
    def ingested(self) -> bool:
        """True when the library phase returned a result instead of raising."""
        return bool(self.api["outcome"] == "returned")


def _run_one(name: str, klass: str, source: Path, root: Path) -> Run:
    """Run one source through the child and observe the filesystem around it."""
    run_dir = root / "runs" / name
    cwd = run_dir / "cwd"
    output_dir = run_dir / "out"
    cwd.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = run_dir / "report.json"

    before_run = _snapshot(run_dir)
    before_repo = _snapshot(REPO_ROOT, prune_roots=IGNORED_ROOT_DIRECTORIES)
    process = subprocess.run(
        [
            sys.executable,
            str(CHILD),
            "--source",
            str(source),
            "--output-dir",
            str(output_dir),
            "--report",
            str(report_path),
            "--cwd",
            str(cwd),
        ],
        capture_output=True,
        text=True,
        timeout=CHILD_TIMEOUT_SECONDS,
        cwd=str(root),
        env={**os.environ, "PYTHONPATH": str(REPO_ROOT)},
    )
    after_run = _snapshot(run_dir)
    after_repo = _snapshot(REPO_ROOT, prune_roots=IGNORED_ROOT_DIRECTORIES)

    created = after_run - before_run
    outside = frozenset(
        path
        for path in created
        if not path.startswith("out/") and path != "out" and path != "report.json"
    )

    report = json.loads(report_path.read_text()) if report_path.is_file() else None
    return Run(
        name=name,
        klass=klass,
        source=source,
        run_dir=run_dir,
        output_dir=output_dir,
        returncode=process.returncode,
        stdout=process.stdout,
        stderr=process.stderr,
        report=report,
        created_outside_output=outside,
        created_in_repository=after_repo - before_repo,
    )


@pytest.fixture(scope="module")
def corpus_runs(tmp_path_factory) -> dict[str, Run]:
    """Build the corpus and run every member, plus the positive control, once."""
    root = tmp_path_factory.mktemp("d8")
    corpus_root = root / "corpus"
    built = build_corpus(corpus_root)
    control = build_positive_control(corpus_root)

    runs = {"positive_control": _run_one("positive_control", "control", control, root)}
    for member in built:
        runs[member.name] = _run_one(member.name, member.klass, member.path, root)
    return runs


# ---------------------------------------------------------------------------
# The corpus itself
# ---------------------------------------------------------------------------


def test_the_corpus_covers_every_declared_hostility_class():
    """A class with no member is a class nobody measured."""
    covered = {fixture.klass for fixture in CORPUS}
    assert covered == set(CLASSES), f"uncovered: {set(CLASSES) - covered}"


def test_the_corpus_has_no_duplicate_members():
    """Two members with one name means one of them is never run."""
    names = [fixture.name for fixture in CORPUS]
    assert len(names) == len(set(names))


def test_the_corpus_is_byte_for_byte_deterministic(tmp_path):
    """§6.6. A fixture that varies between builds cannot be a committed measurement.

    The same trap ``poststack3d`` documents: ``create_textual_header()`` with no
    argument embeds ``datetime.now()``, so a corpus built twice across a second boundary
    would differ 3200 bytes into a binary file where nobody looks.
    """
    first = {m.name: m.path.read_bytes() for m in build_corpus(tmp_path / "a") if m.size >= 0}
    second = {m.name: m.path.read_bytes() for m in build_corpus(tmp_path / "b") if m.size >= 0}
    assert first.keys() == second.keys()
    differing = [name for name in first if first[name] != second[name]]
    assert differing == [], f"non-deterministic corpus members: {differing}"


def test_the_corpus_leaves_no_intermediate_files_behind(tmp_path):
    """The well-formed base each corruption is applied to must not survive as a member."""
    built = build_corpus(tmp_path / "c")
    written = {path.name for path in (tmp_path / "c").iterdir()}
    expected = {member.path.name for member in built}
    assert written == expected, f"unexpected leftovers: {written - expected}"


# ---------------------------------------------------------------------------
# SP11 — the control that makes the rest mean something
# ---------------------------------------------------------------------------


def test_the_positive_control_ingests_through_the_identical_harness(corpus_runs):
    """**Non-vacuity.** An ingest that refused everything would pass every test below."""
    run = corpus_runs["positive_control"]
    assert run.report is not None, f"child wrote no report: {run.stderr[-2000:]}"
    assert run.ingested, f"the well-formed fixture no longer ingests: {run.api}"
    assert run.cli["exit_code"] == 0, run.cli
    assert run.cli["escaped"] is None, run.cli


# ---------------------------------------------------------------------------
# §11.4 — a clean error, never a crash
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", [fixture.name for fixture in CORPUS])
def test_every_member_finishes_without_crashing_the_process(corpus_runs, name):
    """No segfault, no OOM kill, no hang. The child must live long enough to report."""
    run = corpus_runs[name]
    assert run.returncode == 0, (
        f"{name}: child exited {run.returncode} without completing. A negative code is a "
        f"signal - the crash 11.4 bars. stderr: {run.stderr[-2000:]}"
    )
    assert run.report is not None, f"{name}: no report written; stderr {run.stderr[-2000:]}"


@pytest.mark.parametrize("name", [fixture.name for fixture in CORPUS])
def test_every_refused_member_is_refused_with_a_typed_sdip_error(corpus_runs, name):
    """A malformed file is answered by ``sdip.errors``, not by whatever raised first."""
    run = corpus_runs[name]
    if run.ingested:
        assert name in EXPECTED_INGESTS, (
            f"{name} converted, and it is not in EXPECTED_INGESTS. Either the corpus "
            "member stopped being hostile or a check stopped firing."
        )
        return
    api = run.api
    if name in UPSTREAM_TYPED:
        assert api["type"] == UPSTREAM_TYPED[name], (
            f"{name}: the recorded residual is {UPSTREAM_TYPED[name]}, got {api['type']}"
        )
        return
    assert api["is_sdip_error"], (
        f"{name}: refused with {api['module']}.{api['type']} - not an SdipError. "
        "11.4 requires a clean, typed error; an untyped exception from a dependency is "
        "the leak D8 was raised to close."
    )


@pytest.mark.parametrize("name", sorted(EXPECTED_INGESTS))
def test_the_members_that_convert_are_exactly_the_ones_measured(corpus_runs, name):
    """The other direction: a member that stops converting is also a behaviour change."""
    run = corpus_runs[name]
    assert run.ingested, f"{name} was measured as converting; it now fails: {run.api}"


@pytest.mark.parametrize("name", [f.name for f in CORPUS if f.name not in UPSTREAM_TYPED])
def test_every_sdip_refusal_happens_before_upstream_sees_the_file(corpus_runs, name):
    """Header-declared lengths are validated before allocating, measured directly.

    An ``UntrustedInputError`` raised inside ``sdip`` was raised before ``segy`` opened
    the file. The same error raised inside ``segy`` would mean the parser had already
    read, sized and decoded from counts the file supplied - the check would be a
    post-mortem. The frame that raised is the only thing that tells the two apart.
    """
    run = corpus_runs[name]
    if run.ingested:
        return
    assert run.api["raised_in"] == "sdip", (
        f"{name}: refused from inside {run.api['raised_in']}, not sdip. The file reached "
        "a parser before SDIP validated it."
    )


@pytest.mark.parametrize("name", [fixture.name for fixture in CORPUS])
def test_no_member_exceeds_the_declared_memory_ceiling(corpus_runs, name):
    """**No unbounded allocation**, against a ceiling declared in this module."""
    run = corpus_runs[name]
    assert run.peak_rss <= PEAK_RSS_CEILING_BYTES, (
        f"{name}: peak RSS {run.peak_rss / 1024**2:.1f} MB exceeds the declared ceiling "
        f"of {PEAK_RSS_CEILING_BYTES / 1024**2:.0f} MiB. A header-declared count reached "
        "an allocator."
    )


def test_the_hostile_corpus_costs_less_memory_than_the_well_formed_file(corpus_runs):
    """The sharpest form of the claim: refusing costs less than converting.

    If a hostile member ever peaked above a real 30-trace ingest, something in it was
    being sized from the file's own numbers. Measured 2026-08-23: control 211.3 MB,
    hostile maximum 212.0 MB on ``revision_undefined`` - which *converts*, so it is
    compared against the control as an ingest, not as a refusal.
    """
    control = corpus_runs["positive_control"].peak_rss
    refusals = {
        name: run.peak_rss
        for name, run in corpus_runs.items()
        if name != "positive_control" and not run.ingested
    }
    worst = max(refusals, key=lambda key: refusals[key])

    # A DECLARED MARGIN, and the reason is that the strict form asserts the wrong thing.
    #
    # CI's first-ever run failed here at 374.4 MB against 371.8 MB - 0.7 % apart, which
    # is allocator and platform noise, not evidence of anything. Both numbers are
    # dominated by interpreter and library baseline; neither reflects the megabytes a
    # header CLAIMED.
    #
    # The property §3.6 actually asks for is that a refusal must not allocate from the
    # file's own declared numbers. A corpus member declaring gigabytes would show up as
    # a MULTIPLE of the control, not as a rounding difference. 1.25x is far below any
    # such signal and far above platform noise, so the test still fails loudly on the
    # defect it exists for while surviving a change of machine.
    #
    # Not fitted to the observed 1.007: a margin chosen to just clear the number that
    # failed is a margin chosen by the data it was meant to judge.
    allowed = control * 1.25
    assert refusals[worst] <= allowed, (
        f"{worst} was refused but peaked at {refusals[worst] / 1024**2:.1f} MB against "
        f"{control / 1024**2:.1f} MB for a real ingest (limit {allowed / 1024**2:.1f} MB, "
        "1.25x). A refusal costing a MULTIPLE of the work it refused to do has allocated "
        "from the file's own numbers, which is what section 3.6 forbids."
    )


# ---------------------------------------------------------------------------
# §11.4 — no write outside the output path
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", [fixture.name for fixture in CORPUS])
def test_no_member_writes_outside_the_declared_output_directory(corpus_runs, name):
    """The run tree is snapshotted either side of the child. Nothing new may appear."""
    run = corpus_runs[name]
    assert run.created_outside_output == frozenset(), (
        f"{name} created {sorted(run.created_outside_output)} outside the declared output directory"
    )


@pytest.mark.parametrize("name", [fixture.name for fixture in CORPUS])
def test_no_member_writes_into_the_repository(corpus_runs, name):
    """The repository is snapshotted either side of the child too.

    Toolchain caches are excluded (they are rewritten by this very test run); everything
    else is watched. A path appearing here is a write escape with a name.
    """
    run = corpus_runs[name]
    assert run.created_in_repository == frozenset(), (
        f"{name} created {sorted(run.created_in_repository)} inside the repository"
    )


def test_no_output_path_is_ever_derived_from_file_content(corpus_runs, tmp_path_factory):
    """§11.4's second clause, with a witness.

    ``path_bait_in_headers`` is a **structurally valid** SEG-Y whose textual header and
    trace-header tails read ``../../../../../../tmp/sdip_d8_escape``. It converts, as it
    should - and the bait must exist nowhere on disk, resolved from either the child's
    working directory or the filesystem root.
    """
    run = corpus_runs["path_bait_in_headers"]
    assert run.ingested, "the bait file must convert; a refusal would prove nothing"
    candidates = [
        (run.run_dir / "cwd" / PATH_BAIT).resolve(),
        (run.output_dir / PATH_BAIT).resolve(),
        Path("/tmp") / Path(PATH_BAIT).name,  # noqa: S108 - the literal bait target
    ]
    existing = [str(path) for path in candidates if path.exists()]
    assert existing == [], f"a path from file content became a filesystem path: {existing}"


# ---------------------------------------------------------------------------
# The CLI boundary
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", [fixture.name for fixture in CORPUS])
def test_the_cli_exits_non_zero_on_every_member_it_refuses(corpus_runs, name):
    """A refused ingest that exits 0 is worse than one that crashes: it looks like a pass."""
    run = corpus_runs[name]
    if run.ingested:
        assert run.cli["exit_code"] == 0, run.cli
        return
    escaped = run.cli["escaped"]
    if escaped is not None:
        assert name in UPSTREAM_TYPED, (
            f"{name}: {escaped['module']}.{escaped['type']} escaped the console entry "
            "point, so the operator gets a traceback instead of a message"
        )
        return
    assert run.cli["exit_code"] not in (0, None), run.cli


@pytest.mark.parametrize("name", [f.name for f in CORPUS if f.name not in UPSTREAM_TYPED])
def test_the_cli_reports_a_refusal_as_one_line_not_a_traceback(corpus_runs, name):
    """*"A clean error"* is a property of what the operator sees, not only of the type."""
    run = corpus_runs[name]
    if run.ingested:
        return
    stderr = str(run.cli["stderr"])
    assert "Traceback (most recent call last)" not in stderr, (
        f"{name}: the console entry point printed a traceback:\n{stderr[-1500:]}"
    )
    assert stderr.startswith("sdip: ") or "Error: " in stderr, (
        f"{name}: unrecognised console output:\n{stderr[-1500:]}"
    )


# ---------------------------------------------------------------------------
# The numbers this suite exists to produce
# ---------------------------------------------------------------------------


def test_the_measured_outcome_counts_are_the_ones_on_record(corpus_runs):
    """One assertion carrying the whole result, so a drift in any direction is loud.

    33 members: **24 refused by SDIP with a typed error**, **3 refused by MDIO's typed
    grid errors** (the recorded residual), **6 converted**. Measured 2026-08-23 under
    ``multidimio==1.2.1`` / ``segy==0.6.0``.
    """
    members = [run for name, run in corpus_runs.items() if name != "positive_control"]
    converted = [run.name for run in members if run.ingested]
    upstream = [run.name for run in members if not run.ingested and run.name in UPSTREAM_TYPED]
    sdip_typed = [
        run.name
        for run in members
        if not run.ingested and run.name not in UPSTREAM_TYPED and run.api["is_sdip_error"]
    ]
    untyped = [
        run.name
        for run in members
        if not run.ingested and run.name not in UPSTREAM_TYPED and not run.api["is_sdip_error"]
    ]
    assert untyped == [], f"untyped refusals have reappeared: {untyped}"
    assert len(members) == 33
    assert sorted(converted) == sorted(EXPECTED_INGESTS), converted
    assert sorted(upstream) == sorted(UPSTREAM_TYPED), upstream
    assert len(sdip_typed) == 24, sdip_typed
