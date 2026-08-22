"""**Round-trip closure.** Specification §7 G3, open debt **D19**.

The chain SDIP is accountable for has three arrows::

    SEG-Y source --(1)--> MDIO store --(2)--> SEG-Y export --(3)--> MDIO store'

**G3 covers arrow (2)** and asserts ``sha256(export) == sha256(source)`` for the whole
file. When that holds it is the strongest claim available, it needs no interpretation,
and nothing in this module adds to it.

**The gap is ``ROUNDTRIP-SCOPED``.** §7 G3 permits a non-byte-identical round trip *"where
the source is non-conforming in a way that makes byte-identity impossible"*. In exactly
that case the export is trusted on a hash comparison that was never going to match, and
nothing then checks that the exported file is a well-formed SEG-Y, that it parses under
the same gap-free spec, or that it carries the same measured values. A scoped verdict is
currently a statement about the *source*, not about the *export*.

**Arrow (3) closes the loop.** Re-ingest the export and verify the store that results:
G1 on the rebuilt spec, all five planes against the exported file, and every array of the
new store identical to the original store's. That makes the exported SEG-Y a **validated
artifact in its own right** rather than a by-product, and it closes the loop for
byte-identical round trips as well as scoped ones.

What this establishes that G3 does not
--------------------------------------
G3 answers *"are these two files the same bytes?"*. Closure answers *"is the file we
produced a SEG-Y that reads back to the same measured values?"* — which is the question a
consumer of the export actually has, and the only question available at all when the
hashes were never going to match. Neither subsumes the other: a byte-identical export
trivially closes, and a closing export can still fail G3.

Comparisons here are ``array_equal`` and set equality. **There is no tolerance in this
module and there never will be** (§4.5, §9.5). An array present in one store and absent
from the other is a failure, never a skipped comparison — a missing array is not a match.

Nothing here writes to the export or to the original store. Every artifact this check
creates lives under ``workdir``.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from sdip.equivalence.planes import PlaneResult, plane_1, plane_2, plane_3, plane_4, plane_5
from sdip.ingest import ingest
from sdip.spec import G1Result, g1_for_spec

PLANE_KEYS: tuple[str, ...] = ("plane_1", "plane_2", "plane_3", "plane_4", "plane_5")
"""Certificate keys for the five planes, in the order they are run."""


def _arrays_of(store: Path) -> dict[str, Any]:
    """Map array name to array node, read through stock ``zarr``.

    Stock ``zarr`` and not MDIO on purpose: this comparison must not depend on the
    library that wrote either store, or it would be checking MDIO against itself.
    """
    import zarr

    group = zarr.open_group(str(store), mode="r")
    return {str(name): node for name, node in group.arrays()}


def _difference_detail(left: np.ndarray[Any, Any], right: np.ndarray[Any, Any]) -> str:
    """Locate the first differing cell between two same-shape, same-dtype arrays.

    A comparison that reports only *that* it failed is much less useful than one that
    says *where*.
    """
    differing = np.asarray(left != right)
    flat = np.flatnonzero(differing.ravel())
    if flat.size == 0:  # pragma: no cover - only reachable on an exotic dtype
        return "arrays compare unequal but no differing cell could be located"
    cell = np.unravel_index(int(flat[0]), differing.shape)
    return (
        f"{int(flat.size)} of {int(differing.size)} cells differ; "
        f"first at {tuple(int(i) for i in cell)}"
    )


@dataclass(frozen=True, slots=True)
class ArrayComparison:
    """One array's verdict, compared between the original store and the closure store."""

    name: str
    in_original: bool
    in_closure: bool
    equal: bool
    detail: str
    original_shape: list[int] | None = None
    closure_shape: list[int] | None = None
    original_dtype: str | None = None
    closure_dtype: str | None = None

    @property
    def only_in_one(self) -> bool:
        """True when the array exists in exactly one of the two stores."""
        return self.in_original != self.in_closure

    def to_json(self) -> dict[str, Any]:
        """Certificate-shaped mapping."""
        return {
            "name": self.name,
            "in_original_store": self.in_original,
            "in_closure_store": self.in_closure,
            "equal": self.equal,
            "detail": self.detail,
            "original_shape": self.original_shape,
            "closure_shape": self.closure_shape,
            "original_dtype": self.original_dtype,
            "closure_dtype": self.closure_dtype,
        }


def _compare_stores(original: Path, closure: Path) -> list[ArrayComparison]:
    """Compare every array of two stores with ``array_equal``.

    The union of both name sets is walked, not the intersection: iterating the
    intersection would silently drop an array that one store lost, which is precisely
    the defect this check exists to catch.

    Args:
        original: The store the export was produced from.
        closure: The store produced by re-ingesting the export.

    Returns:
        One comparison per array name, sorted by name.
    """
    left, right = _arrays_of(original), _arrays_of(closure)
    comparisons: list[ArrayComparison] = []

    for name in sorted(set(left) | set(right)):
        in_left, in_right = name in left, name in right
        if not (in_left and in_right):
            present = "original store" if in_left else "closure store"
            comparisons.append(
                ArrayComparison(
                    name=name,
                    in_original=in_left,
                    in_closure=in_right,
                    equal=False,
                    detail=f"present only in the {present}; a missing array is not a match",
                )
            )
            continue

        expected = np.asarray(left[name][...])
        observed = np.asarray(right[name][...])
        shapes = (list(expected.shape), list(observed.shape))
        dtypes = (str(expected.dtype), str(observed.dtype))

        if expected.dtype != observed.dtype:
            # Compared before the values: NumPy's cross-dtype comparison rules are not
            # a sound basis for an equivalence claim, and a changed dtype is itself a
            # finding rather than something to coerce past.
            equal, detail = False, f"dtype changed: {dtypes[0]} -> {dtypes[1]}"
        elif expected.shape != observed.shape:
            equal, detail = False, f"shape changed: {shapes[0]} -> {shapes[1]}"
        else:
            equal = bool(np.array_equal(expected, observed))
            detail = "identical" if equal else _difference_detail(expected, observed)

        comparisons.append(
            ArrayComparison(
                name=name,
                in_original=True,
                in_closure=True,
                equal=equal,
                detail=detail,
                original_shape=shapes[0],
                closure_shape=shapes[1],
                original_dtype=dtypes[0],
                closure_dtype=dtypes[1],
            )
        )

    return comparisons


@dataclass(slots=True)
class ClosureResult:
    """The verdict of the round-trip closure check, in certificate shape."""

    export_path: str
    original_store: str
    closure_store: str
    g1: G1Result | None = None
    planes: list[PlaneResult] = field(default_factory=list)
    arrays: list[ArrayComparison] = field(default_factory=list)
    error: str | None = None

    @property
    def failed_planes(self) -> list[PlaneResult]:
        """Planes that did not pass against the exported file."""
        return [p for p in self.planes if not p.passed]

    @property
    def differing_arrays(self) -> list[str]:
        """Arrays present in both stores whose contents are not identical."""
        return sorted(a.name for a in self.arrays if not a.equal and not a.only_in_one)

    @property
    def only_in_original(self) -> list[str]:
        """Arrays the original store has and the closure store does not."""
        return sorted(a.name for a in self.arrays if a.in_original and not a.in_closure)

    @property
    def only_in_closure(self) -> list[str]:
        """Arrays the closure store has and the original store does not."""
        return sorted(a.name for a in self.arrays if a.in_closure and not a.in_original)

    @property
    def passed(self) -> bool:
        """True only when the export re-ingests, every plane holds, and every array matches.

        Emptiness is not success: zero planes or zero arrays means the check did not run,
        and an unrun check is not a passing one (**SP11**).
        """
        return (
            self.error is None
            and self.g1 is not None
            and self.g1.passed
            and len(self.planes) == len(PLANE_KEYS)
            and not self.failed_planes
            and bool(self.arrays)
            and all(a.equal for a in self.arrays)
        )

    @property
    def status(self) -> str:
        """``"PASS"`` or ``"FAIL"``."""
        return "PASS" if self.passed else "FAIL"

    def summary(self) -> str:
        """One line naming what killed it, or what held."""
        if self.error is not None:
            return f"closure FAIL: the exported SEG-Y did not re-ingest - {self.error}"
        if self.g1 is None or not self.g1.passed:
            detail = self.g1.summary() if self.g1 else "G1 was not run"
            return f"closure FAIL: {detail}"
        if self.passed:
            return (
                f"closure PASS: the export re-ingests, all {len(self.planes)} planes hold "
                f"against it, and all {len(self.arrays)} arrays are identical to the "
                "original store's"
            )
        parts: list[str] = []
        if self.failed_planes:
            parts.append("planes " + "+".join(p.gate for p in self.failed_planes) + " failed")
        if self.differing_arrays:
            parts.append("arrays differ: " + ", ".join(self.differing_arrays))
        if self.only_in_original:
            parts.append("missing from the re-ingested store: " + ", ".join(self.only_in_original))
        if self.only_in_closure:
            parts.append("only in the re-ingested store: " + ", ".join(self.only_in_closure))
        if not parts:
            parts.append("nothing was compared, so nothing was established")
        return "closure FAIL: " + "; ".join(parts)

    def to_json(self) -> dict[str, Any]:
        """Certificate-shaped mapping."""
        return {
            "check": "roundtrip_closure",
            "status": self.status,
            "summary": self.summary(),
            "export_path": self.export_path,
            "original_store": self.original_store,
            "closure_store": self.closure_store,
            "error": self.error,
            "G1": self.g1.to_json() if self.g1 else None,
            "planes": {
                key: plane.to_json()["status"]
                for key, plane in zip(PLANE_KEYS, self.planes, strict=False)
            },
            "plane_evidence": [p.to_json() for p in self.planes],
            "arrays_compared": len(self.arrays),
            "differing_arrays": self.differing_arrays,
            "only_in_original_store": self.only_in_original,
            "only_in_closure_store": self.only_in_closure,
            "arrays": [a.to_json() for a in self.arrays],
            "note": (
                "G3 answers whether the export is byte-identical to the source. This "
                "answers whether the export is a well-formed SEG-Y that reads back to "
                "the same measured values - the only question available when the source "
                "is non-conforming and G3 is ROUNDTRIP-SCOPED. Neither subsumes the "
                "other (spec 7 G3, debt D19)."
            ),
        }


def _run_planes(export: Path, store: Path, spec: Any, *, g1_passed: bool) -> list[PlaneResult]:
    """Run all five planes of ``store`` against ``export``.

    A plane that raises has *detected* something about the exported file; recording that
    as anything other than a failure would be the vacuity the engine exists to avoid. So
    an exception becomes a ``FAIL`` naming the exception, and the remaining planes still
    run — one broken plane must not hide the state of the other four.
    """
    checkers: tuple[tuple[int, str, str, Any], ...] = (
        (1, "G2a", "Textual header preserved verbatim", lambda: plane_1(export, store)),
        (2, "G2b", "Binary header preserved", lambda: plane_2(export, store)),
        (
            3,
            "G2c",
            "All 240 trace-header bytes recoverable, bit-exact",
            lambda: plane_3(export, store, spec, g1_passed=g1_passed),
        ),
        (4, "G2d", "Live-trace samples bit-exact", lambda: plane_4(export, store, spec)),
        (
            5,
            "G2e",
            "Cardinality, ordering, live mask, duplicates surfaced",
            lambda: plane_5(export, store, spec),
        ),
    )

    results: list[PlaneResult] = []
    for number, gate, title, run in checkers:
        try:
            results.append(run())
        except Exception as exc:
            results.append(
                PlaneResult(
                    plane=number,
                    gate=gate,
                    title=title,
                    status="FAIL",
                    evidence={
                        "reason": (
                            f"the plane raised against the exported file: "
                            f"{type(exc).__name__}: {exc}"
                        )
                    },
                )
            )
    return results


def roundtrip_closure(
    export_path: str | Path,
    original_store: str | Path,
    spec: Any,
    *,
    spec_revision: float | int = 1,
    template: str = "PostStack3DTime",
    workdir: str | Path,
) -> ClosureResult:
    """Close the round trip: validate the exported SEG-Y as an artifact in its own right.

    Three questions, answered in order, each of which can kill the check:

    1. Does the export re-ingest at all, under a spec that passes **G1**? A file that
       cannot be parsed gap-free is not a SEG-Y anybody can consume.
    2. Do all five planes hold between the export and the store built from it? That is
       G2a-G2e run with the *exported file* as the source of truth.
    3. Is every array of that store identical to the original store's, by
       ``array_equal``? That is what makes the export equivalent to the store it came
       from, and not merely self-consistent.

    Args:
        export_path: The exported SEG-Y to validate. **Never modified.**
        original_store: The MDIO store the export was produced from. **Never modified.**
        spec: The gap-free ``SegySpec`` used for the original ingest, for the plane
            checkers. The closure ingest builds its own spec from ``spec_revision``.
        spec_revision: SEG-Y revision for the spec the re-ingest builds.
        template: Registered MDIO template name for the re-ingest.
        workdir: Directory for the closure store. Should be temporary; everything this
            check creates lives under it, and ``workdir/closure.mdio`` is removed first
            if it already exists.

    Returns:
        The closure verdict. ``PASS`` only when G1 passes on the rebuilt spec, all five
        planes pass, and every array matches.
    """
    export = Path(export_path)
    original = Path(original_store)
    work = Path(workdir)
    work.mkdir(parents=True, exist_ok=True)

    closure_store = work / "closure.mdio"
    if closure_store.exists():
        shutil.rmtree(closure_store)

    result = ClosureResult(
        export_path=str(export),
        original_store=str(original),
        closure_store=str(closure_store),
    )

    try:
        re_ingest = ingest(
            export,
            closure_store,
            revision=spec_revision,
            template=template,
            overwrite=False,
        )
    except Exception as exc:
        # Not re-raised: an export that will not re-ingest is the finding this check
        # exists to surface, and a traceback out of a certificate run reports nothing.
        result.error = f"{type(exc).__name__}: {exc}"
        return result

    # Measured from the rebuilt spec rather than read off the ingest result. The gate is
    # cheap to re-run and a remembered verdict is not evidence about the store on disk.
    result.g1 = g1_for_spec(re_ingest.spec)
    result.planes = _run_planes(export, closure_store, spec, g1_passed=result.g1.passed)
    result.arrays = _compare_stores(original, closure_store)
    return result
