"""**Gate G6 — determinism and reproducibility.** Specification §7 G6, §3.4.

    PASS iff two independent ingestions of the same source with the same spec and
    config produce **identical array bytes** (metadata timestamps excluded), and the
    certificate is reproducible from the committed script and config.
    Kills it: any array-content difference between runs.

**Why the gate exists.** Every other gate compares one store against one source. G6 is the
only one that asks whether the *pipeline* is a function. If two runs of the same input can
disagree, then a certificate names a store that a third party cannot recreate, and the
whole claim collapses into "it worked on the machine that issued it" — which is exactly the
thing **SP8** and **SP9** exist to forbid. A stranger reproducing the result from the
committed record alone is the project's own test of whether something happened; G6 is that
test executed rather than asserted.

What would make it vacuous
--------------------------
- **Comparing decoded values only.** Two stores can hold identical arrays and differ in
  every compressed byte — a non-deterministic codec, a shuffle filter fed a different block
  size, a differing worker count changing how a chunk was assembled. A gate that read the
  values back through a decompressor and pronounced them equal would report PASS on a store
  whose bytes nobody can reproduce, while the governing text says *array bytes*. So the
  chunk files are compared byte for byte on disk, **and** the values are compared with
  ``numpy.array_equal``, and the two are reported separately.
- **Comparing bytes only.** Byte equality is the stricter test, but when it fails the
  question "did the data change, or only its encoding?" is the first thing an operator
  needs answered. Identical values with differing compressed bytes is *partial* determinism.
  It still **fails** G6 — the governing text is not negotiable — but it is a materially
  different finding from corrupted content, and hiding it behind a bare FAIL would send
  someone hunting for a data bug that is not there.
- **Excluding too much as "metadata".** The governing text excludes metadata *timestamps*.
  Zarr v3 keeps all node metadata in ``zarr.json``, and MDIO writes ``createdOn`` into it,
  so that file — and only that file — is skipped by the chunk-byte comparison. There is no
  partial parse of it, because a parse deciding which keys are "timestamp-like" is a place
  to hide a difference. The cost is stated plainly: **G6 does not compare stored attributes**,
  which is where the raw textual and binary SEG-Y headers live. Those are Planes 1 and 2's
  job (G2a, G2b) and are measured there against the source, so this is a scope boundary, not
  a hole — but a G6 PASS is not a statement about attribute bytes.
- **Letting an unreadable array escape as a crash.** A chunk whose bytes moved may not
  decode at all — blosc raises rather than returning garbage. That is a *detected*
  difference, so the read is caught and recorded as a value divergence. An exception
  propagating out of :func:`g6` would turn a FAIL into a stack trace, and a stack trace is
  not a gate result.
- **Runs that are not independent.** Copying one store to produce the second would pass
  trivially. Each run here is a full :func:`sdip.ingest.ingest` call into its own output
  path, with the same source, spec revision and template.
- **A source too small to exercise anything.** A fixture producing one chunk per array
  barely tests the compressor and does not test chunk assembly across workers at all. G6
  reports the array and chunk counts it compared so the scope of the PASS is legible;
  determinism at 30 traces is not evidence of determinism at scale.

Worker counts are pinned in production runs and recorded on the certificate (§3.4). This
module does not set them: both runs inherit the same environment, and a G6 PASS is a
statement about that configuration, which is the configuration the certificate carries.

Nothing outside ``workdir`` is touched. Run directories this module created are removed
when it finishes; ``workdir`` itself is left alone.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from sdip.ingest import ingest

METADATA_FILENAME = "zarr.json"
"""The one file the chunk-byte comparison skips. It carries MDIO's ``createdOn``.

Zarr v3 stores every node's metadata here, so skipping it also skips stored attributes.
That exclusion is declared in the module docstring rather than narrowed by parsing, because
a parse that decides which keys count as timestamps is a place for a difference to hide.
"""


def _open_group(store: Path) -> Any:
    """Open a store read-only with stock ``zarr``.

    Stock ``zarr`` rather than ``mdio`` on purpose: G6 asks what is on disk, and reading
    through the writer's own abstraction risks normalising away the difference being
    measured.

    Args:
        store: The MDIO store directory.

    Returns:
        The opened Zarr group.
    """
    import zarr

    return zarr.open_group(str(store), mode="r")


def _array_directories(store: Path, group: Any) -> dict[str, Path]:
    """Map every array in a store to the directory holding its chunks.

    Args:
        store: The store root.
        group: The already-opened group for that store.

    Returns:
        Array name to on-disk directory. The name is the group-relative key; the path
        comes from the array's own ``path``, so a nested group resolves correctly.
    """
    return {str(name): store / str(array.path) for name, array in group.arrays()}


def _chunk_relpaths(array_dir: Path) -> tuple[str, ...]:
    """List every non-metadata file under an array directory, relative and sorted.

    Everything that is not :data:`METADATA_FILENAME` is treated as chunk content,
    including files this module does not recognise. An unexplained extra file in one run
    and not the other is a difference between the two stores and is reported as one.

    Args:
        array_dir: The array's directory. May not exist — a zero-dimensional array can
            have no chunk file at all.

    Returns:
        Sorted relative paths, empty when the directory holds no chunk files.
    """
    if not array_dir.is_dir():
        return ()
    return tuple(
        sorted(
            str(path.relative_to(array_dir))
            for path in array_dir.rglob("*")
            if path.is_file() and path.name != METADATA_FILENAME
        )
    )


def _read_values(group: Any, name: str) -> tuple[Any, str | None]:
    """Read one array's full contents, treating a failed read as a detected difference.

    A chunk that will not decode is not a passing array. Upstream raises rather than
    returning garbage — blosc reports a decompression error on a chunk whose bytes moved —
    and letting that escape would turn a FAIL into a crash. Mirrors the reasoning in
    :mod:`sdip.equivalence.nonvacuity`: a raise means the checker noticed.

    Args:
        group: The opened Zarr group.
        name: Array name within the group.

    Returns:
        ``(values, error)``. ``values`` is ``None`` when the read failed.
    """
    try:
        return group[name][...], None
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"


def _compare_chunk_bytes(left_dir: Path, right_dir: Path) -> tuple[str | None, str]:
    """Compare two array directories file by file, byte for byte.

    Args:
        left_dir: The baseline run's array directory.
        right_dir: The other run's array directory.

    Returns:
        ``(first_differing_relative_path, detail)``. The path is ``None`` when every
        chunk file is present in both runs and identical.
    """
    left_names = _chunk_relpaths(left_dir)
    right_names = _chunk_relpaths(right_dir)

    only_one_side = sorted(set(left_names) ^ set(right_names))
    if only_one_side:
        return only_one_side[0], f"chunk file present in only one run: {only_one_side[0]}"

    # One chunk in memory at a time. Reading both stores whole would make the gate's own
    # footprint scale with the survey, and byte equality does not need the whole array.
    for relative in left_names:
        left_bytes = (left_dir / relative).read_bytes()
        right_bytes = (right_dir / relative).read_bytes()
        if left_bytes != right_bytes:
            return relative, (
                f"chunk bytes differ at {relative} "
                f"({len(left_bytes)} vs {len(right_bytes)} bytes on disk)"
            )
    if not left_names:
        # Said out loud rather than reported as a match. An array whose whole content
        # lives in zarr.json - `segy_file_header` is one - has nothing on disk for the
        # byte level to compare, so "identical" there would be a claim about nothing.
        return None, "no chunk files on disk - byte level compared nothing for this array"
    return None, f"{len(left_names)} chunk file(s) identical byte for byte"


def _compare_values(left: Any, right: Any) -> tuple[bool, str]:
    """Compare two decoded arrays exactly.

    ``numpy.array_equal`` and nothing else. A tolerance here would make the gate report
    determinism it did not measure (§4.5, §9.5).

    Args:
        left: The baseline run's array contents.
        right: The other run's array contents.

    Returns:
        ``(identical, detail)``.
    """
    if left.dtype != right.dtype:
        return False, f"dtype differs: {left.dtype} vs {right.dtype}"
    if left.shape != right.shape:
        return False, f"shape differs: {left.shape} vs {right.shape}"
    if bool(np.array_equal(left, right)):
        return True, "array_equal - exact, never allclose"
    return False, "values differ under array_equal"


@dataclass(frozen=True, slots=True)
class ArrayFinding:
    """One array compared between two runs, at both levels."""

    name: str
    baseline_run: int
    other_run: int
    chunks_identical: bool
    values_identical: bool
    first_differing_chunk: str | None
    chunk_detail: str
    value_detail: str

    @property
    def passed(self) -> bool:
        """True only when the chunk bytes **and** the decoded values both match."""
        return self.chunks_identical and self.values_identical

    @property
    def partial(self) -> bool:
        """True when the values match but the compressed bytes do not.

        Partial determinism: the data survived, its encoding did not reproduce. Still a
        G6 failure, but a different diagnosis from corrupted content.
        """
        return self.values_identical and not self.chunks_identical

    def to_json(self) -> dict[str, Any]:
        """Certificate-shaped mapping."""
        return {
            "array": self.name,
            "runs": [self.baseline_run, self.other_run],
            "chunk_bytes_identical": self.chunks_identical,
            "values_identical": self.values_identical,
            "first_differing_chunk": self.first_differing_chunk,
            "chunk_detail": self.chunk_detail,
            "value_detail": self.value_detail,
            "partial_determinism": self.partial,
            "status": "PASS" if self.passed else "FAIL",
        }


@dataclass(slots=True)
class G6Result:
    """The verdict of the determinism audit."""

    runs: int = 0
    arrays: tuple[str, ...] = ()
    findings: list[ArrayFinding] = field(default_factory=list)
    error: str | None = None

    @property
    def chunk_divergences(self) -> list[str]:
        """Arrays whose on-disk chunk bytes differed between runs."""
        return sorted({f.name for f in self.findings if not f.chunks_identical})

    @property
    def value_divergences(self) -> list[str]:
        """Arrays whose decoded values differed between runs."""
        return sorted({f.name for f in self.findings if not f.values_identical})

    @property
    def first_differing_chunk(self) -> str | None:
        """The first differing chunk path found, or ``None`` when the bytes all matched."""
        for finding in self.findings:
            if finding.first_differing_chunk is not None:
                return f"{finding.name}/{finding.first_differing_chunk}"
        return None

    @property
    def partial(self) -> bool:
        """True when every value matched but some compressed bytes did not."""
        return not self.value_divergences and bool(self.chunk_divergences)

    @property
    def passed(self) -> bool:
        """True only when both levels matched for every array across every run pair.

        An empty finding list is a FAIL, not a PASS: a gate that compared nothing has
        measured nothing (**SP11**).
        """
        return self.error is None and bool(self.findings) and all(f.passed for f in self.findings)

    @property
    def status(self) -> str:
        """``"PASS"`` or ``"FAIL"``."""
        return "PASS" if self.passed else "FAIL"

    def summary(self) -> str:
        """One line naming what killed it, or what held."""
        if self.error is not None:
            return f"G6 FAIL: {self.error}"
        if not self.findings:
            return "G6 FAIL: no arrays were compared - the gate measured nothing"
        if self.passed:
            return (
                f"G6 PASS: {self.runs} independent ingests, {len(self.arrays)} arrays, "
                "chunk bytes and values identical across every run pair"
            )
        if self.partial:
            return (
                "G6 FAIL: partial determinism - values are array_equal everywhere but "
                f"compressed bytes differ in {', '.join(self.chunk_divergences)} "
                f"(first at {self.first_differing_chunk})"
            )
        parts = [f"values differ in {', '.join(self.value_divergences)}"]
        if self.chunk_divergences:
            parts.append(
                f"chunk bytes differ in {', '.join(self.chunk_divergences)} "
                f"(first at {self.first_differing_chunk})"
            )
        return "G6 FAIL: " + "; ".join(parts)

    def to_json(self) -> dict[str, Any]:
        """Certificate-shaped mapping."""
        return {
            "gate": "G6",
            "status": self.status,
            "summary": self.summary(),
            "runs": self.runs,
            "arrays_compared": list(self.arrays),
            "array_count": len(self.arrays),
            "chunk_byte_divergences": self.chunk_divergences,
            "value_divergences": self.value_divergences,
            "first_differing_chunk": self.first_differing_chunk,
            "partial_determinism": self.partial,
            "error": self.error,
            "findings": [f.to_json() for f in self.findings],
            "note": (
                "Two levels, reported separately: on-disk chunk files compared byte for "
                "byte, and decoded arrays compared with array_equal. Identical values "
                "with differing compressed bytes is partial determinism - it still FAILS "
                "G6, because the governing text says array bytes. zarr.json is skipped "
                "for the byte comparison as the metadata-timestamp exclusion (it carries "
                "createdOn), which also puts stored attributes - the raw SEG-Y file "
                "headers - outside G6's scope; those are measured by G2a and G2b."
            ),
        }


def _compare_run_pair(
    baseline: Path, other: Path, baseline_index: int, other_index: int
) -> tuple[list[ArrayFinding], str | None]:
    """Compare one pair of stores at both levels.

    Args:
        baseline: Run 0's store.
        other: The later run's store.
        baseline_index: Run 0's index, for the finding record.
        other_index: The later run's index.

    Returns:
        ``(findings, error)``. ``error`` is set only when the two stores do not even hold
        the same arrays, in which case no per-array finding is meaningful.
    """
    baseline_group = _open_group(baseline)
    other_group = _open_group(other)
    baseline_dirs = _array_directories(baseline, baseline_group)
    other_dirs = _array_directories(other, other_group)

    if set(baseline_dirs) != set(other_dirs):
        differing = sorted(set(baseline_dirs) ^ set(other_dirs))
        return [], (
            f"run {baseline_index} and run {other_index} do not hold the same arrays: "
            f"{', '.join(differing)}"
        )

    findings: list[ArrayFinding] = []
    for name in sorted(baseline_dirs):
        first_differing, chunk_detail = _compare_chunk_bytes(baseline_dirs[name], other_dirs[name])
        baseline_values, baseline_error = _read_values(baseline_group, name)
        other_values, other_error = _read_values(other_group, name)
        if baseline_error is not None or other_error is not None:
            values_identical = False
            value_detail = "array could not be read: " + "; ".join(
                f"run {index} raised {error}"
                for index, error in ((baseline_index, baseline_error), (other_index, other_error))
                if error is not None
            )
        else:
            values_identical, value_detail = _compare_values(baseline_values, other_values)
        findings.append(
            ArrayFinding(
                name=name,
                baseline_run=baseline_index,
                other_run=other_index,
                chunks_identical=first_differing is None,
                values_identical=values_identical,
                first_differing_chunk=first_differing,
                chunk_detail=chunk_detail,
                value_detail=value_detail,
            )
        )
    return findings, None


def g6(
    source: str | Path,
    spec_revision: float | int = 1,
    *,
    template: str = "PostStack3DTime",
    workdir: str | Path,
    runs: int = 2,
) -> G6Result:
    """Ingest one source several times over and compare the stores byte for byte.

    Each run is a full, independent :func:`sdip.ingest.ingest` into
    ``workdir/run_<i>.mdio``. Run 0 is then compared against every later run on two
    levels — on-disk chunk bytes, and decoded values under ``numpy.array_equal`` — and
    both results are reported, because they can disagree and the disagreement is the
    finding.

    ``zarr.json`` is excluded from the byte comparison. It is Zarr v3's node metadata and
    carries MDIO's ``createdOn``, which is the "metadata timestamps excluded" clause of
    §7 G6. Stored attributes live in the same file and are therefore outside G6's scope;
    the raw SEG-Y file headers they hold are measured by G2a and G2b instead.

    The caller must supply a ``workdir`` with no ``run_<i>.mdio`` in it. Run directories
    this function creates are removed on the way out, including after a failure;
    ``workdir`` itself is left in place.

    Args:
        source: The SEG-Y file to ingest repeatedly.
        spec_revision: SEG-Y revision passed to every run's gap-free spec build.
        template: Registered MDIO template name, identical for every run.
        workdir: Directory to hold the run stores. Created if absent. Nothing outside it
            is written.
        runs: How many independent ingests to perform. Two is the specified minimum.

    Returns:
        The gate result. ``PASS`` only when both levels match for every array across
        every run pair.

    Raises:
        ValueError: If ``runs`` is below two, or a ``run_<i>.mdio`` already exists in
            ``workdir`` — an existing store was not produced by this call and comparing
            against it would not be a measurement of this pipeline.
    """
    if runs < 2:
        msg = f"G6 compares runs against one another; runs must be at least 2, got {runs}"
        raise ValueError(msg)

    source_path = Path(source).resolve()
    work = Path(workdir)
    work.mkdir(parents=True, exist_ok=True)

    result = G6Result(runs=runs)
    created: list[Path] = []
    try:
        stores: list[Path] = []
        for index in range(runs):
            store = work / f"run_{index}.mdio"
            if store.exists():
                msg = (
                    f"{store} already exists. G6 needs a workdir it can fill itself; it "
                    "will not overwrite or adopt a store it did not create."
                )
                raise ValueError(msg)
            # Recorded before the ingest so a partially written store is still cleaned up.
            created.append(store)
            ingest(
                source_path,
                store,
                revision=spec_revision,
                template=template,
                overwrite=False,
            )
            stores.append(store)

        baseline = stores[0]
        result.arrays = tuple(sorted(_array_directories(baseline, _open_group(baseline))))
        for index in range(1, runs):
            findings, error = _compare_run_pair(baseline, stores[index], 0, index)
            result.findings.extend(findings)
            if error is not None:
                result.error = error
                break
    finally:
        for store in created:
            shutil.rmtree(store, ignore_errors=True)

    return result
