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

Why the five planes alone are not the check — the measured hole (D-0067)
-----------------------------------------------------------------------
The five planes here run **export against the closure store**, and the closure store was
built *from* that export. That leg is therefore **self-consistency**: it establishes that
the exported file parses gap-free and survives an ingest unchanged, which is worth
having, but it cannot by construction disagree with the export about anything. The only
leg that compares the export to the **original** is the store-to-store comparison — and
until D-0067 that comparison walked ``group.arrays()`` and nothing else.

SDIP's authoritative raw file headers are **not arrays**. §4.3 requires the raw bytes to
be authoritative on conflict, and MDIO only writes them behind a barred variable, so
SDIP captures the 3200 textual and 400 binary bytes itself and stores them as base64
**attributes** (``sdipRawTextHeader``, ``sdipRawBinaryHeader`` — ``DECISIONS.md`` D-0021).
An array-only comparison never reads them. Measured on the 30-trace poststack fixture:
flipping one bit of the export's **binary** file header, at export offset 3300 and again
at 3450 — SEG-Y binary-header bytes 101 and 251, both inside the rev 1 unassigned region
3261-3500 so that no parsed field or trace length moves — produced ``closure PASS`` on an
export whose 400 header bytes differed from the original store's. Two of the five planes
were, in the regime this module exists for, checking nothing at all.

The **file-header leg** closes that: the two raw attributes are compared between the two
stores by byte equality, and an attribute present in one store and absent from the other
is a failure. Corruption inside the *textual* header was already caught, but only
incidentally — the flip broke the EBCDIC decode, the ingest fell back to the
header-less shape (D-0055), and the missing-array rule fired. Detection by luck is not
detection, and the leg makes both halves deliberate.

Comparisons here are ``array_equal``, byte equality and set equality. **There is no
tolerance in this module and there never will be** (§4.5, §9.5). An array or a header
present in one store and absent from the other is a failure, never a skipped
comparison — a missing array is not a match.

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
from sdip.errors import UntrustedInputError
from sdip.ingest import ingest
from sdip.ingest.file_headers import (
    ATTR_RAW_BINARY,
    ATTR_RAW_TEXT,
    read_raw_binary_from_store,
    read_raw_textual_from_store,
)
from sdip.provenance.hashing import sha256_bytes
from sdip.spec import G1Result, g1_for_spec

PLANE_KEYS: tuple[str, ...] = ("plane_1", "plane_2", "plane_3", "plane_4", "plane_5")
"""Certificate keys for the five planes, in the order they are run."""

FILE_HEADER_ATTRS: tuple[tuple[str, str, Any], ...] = (
    (ATTR_RAW_TEXT, "textual", read_raw_textual_from_store),
    (ATTR_RAW_BINARY, "binary", read_raw_binary_from_store),
)
"""The raw file-header attributes compared between the two stores, and their readers.

**One reader per attribute, never a reader that loads both.** Planes 1 and 2 are
separable claims (§4.1) and D-0028 records what happens when a reader validates the two
halves together: a defect in the textual header made Plane 2 fail, and a gate that fires
on somebody else's corruption cannot localise a fault. The same reasoning applies to a
leg that reports which header moved.
"""


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


@dataclass(frozen=True, slots=True)
class HeaderComparison:
    """One raw file header's verdict, compared between the two stores by byte equality.

    Digests rather than the bytes themselves, for the same reason
    :meth:`~sdip.ingest.file_headers.RawFileHeaders.to_json` uses them: a certificate is
    a public document and 3600 bytes of somebody's survey header does not belong in one.
    """

    attribute: str
    header: str
    in_original: bool
    in_closure: bool
    equal: bool
    detail: str
    original_bytes: int | None = None
    closure_bytes: int | None = None
    original_sha256: str | None = None
    closure_sha256: str | None = None

    @property
    def only_in_one(self) -> bool:
        """True when the attribute exists in exactly one of the two stores."""
        return self.in_original != self.in_closure

    def to_json(self) -> dict[str, Any]:
        """Certificate-shaped mapping."""
        return {
            "attribute": self.attribute,
            "header": self.header,
            "in_original_store": self.in_original,
            "in_closure_store": self.in_closure,
            "equal": self.equal,
            "detail": self.detail,
            "original_bytes": self.original_bytes,
            "closure_bytes": self.closure_bytes,
            "original_sha256": self.original_sha256,
            "closure_sha256": self.closure_sha256,
        }


def _first_differing_byte(left: bytes, right: bytes) -> int | None:
    """0-based offset of the first differing byte over the common prefix, or ``None``."""
    for offset, (a, b) in enumerate(zip(left, right, strict=False)):
        if a != b:
            return offset
    return None


def _read_header(store: Path, reader: Any) -> bytes | None:
    """Read one raw header attribute, or ``None`` when the store does not carry it.

    ``None`` is *absence*, which the caller turns into a failure. It is never a reason to
    skip the comparison: a store that lost SDIP's authoritative header bytes has lost
    §4.2's and §4.3's entire subject, and "could not read it" must not read as "matched".
    """
    try:
        return bytes(reader(store))
    except (UntrustedInputError, KeyError, FileNotFoundError):
        return None


def _compare_file_headers(original: Path, closure: Path) -> list[HeaderComparison]:
    """Compare SDIP's authoritative raw file headers between two stores, byte for byte.

    This is the leg the array comparison cannot cover, because the bytes are attributes
    and not arrays (see the module docstring, and ``DECISIONS.md`` D-0067). Byte equality
    on the raw bytes, never a comparison of the decoded text or the parsed fields: §4.3
    makes the raw bytes authoritative on conflict, and a parsed comparison can agree
    while the bytes differ.

    Args:
        original: The store the export was produced from.
        closure: The store produced by re-ingesting the export.

    Returns:
        One comparison per attribute in :data:`FILE_HEADER_ATTRS`, in that order.
    """
    comparisons: list[HeaderComparison] = []
    for attribute, header, reader in FILE_HEADER_ATTRS:
        left, right = _read_header(original, reader), _read_header(closure, reader)
        in_left, in_right = left is not None, right is not None
        if left is None or right is None:
            present = (
                "neither store"
                if not (in_left or in_right)
                else ("the original store" if in_left else "the re-ingested store")
            )
            comparisons.append(
                HeaderComparison(
                    attribute=attribute,
                    header=header,
                    in_original=in_left,
                    in_closure=in_right,
                    equal=False,
                    detail=(
                        f"the {header} header is carried by {present}; a header SDIP "
                        "cannot read is not a header that matched"
                    ),
                    original_bytes=len(left) if left is not None else None,
                    closure_bytes=len(right) if right is not None else None,
                    original_sha256=sha256_bytes(left) if left is not None else None,
                    closure_sha256=sha256_bytes(right) if right is not None else None,
                )
            )
            continue

        equal = left == right
        if equal:
            detail = f"identical, {len(left)} bytes"
        elif len(left) != len(right):
            detail = f"length changed: {len(left)} -> {len(right)} bytes"
        else:
            offset = _first_differing_byte(left, right)
            differing = sum(1 for a, b in zip(left, right, strict=True) if a != b)
            detail = (
                f"{differing} of {len(left)} bytes differ; first at {header} header "
                f"byte {offset + 1 if offset is not None else '?'} (0-based offset "
                f"{offset})"
            )
        comparisons.append(
            HeaderComparison(
                attribute=attribute,
                header=header,
                in_original=True,
                in_closure=True,
                equal=equal,
                detail=detail,
                original_bytes=len(left),
                closure_bytes=len(right),
                original_sha256=sha256_bytes(left),
                closure_sha256=sha256_bytes(right),
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
    file_headers: list[HeaderComparison] = field(default_factory=list)
    error: str | None = None

    @property
    def failed_planes(self) -> list[PlaneResult]:
        """Planes that did not pass against the exported file."""
        return [p for p in self.planes if not p.passed]

    @property
    def differing_headers(self) -> list[str]:
        """Raw file-header attributes that did not match between the two stores."""
        return [h.attribute for h in self.file_headers if not h.equal]

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
        """True only when the export re-ingests and every leg holds.

        Four legs, all required: G1 on the rebuilt spec, the five planes against the
        export, both raw file headers, and every array.

        Emptiness is not success: zero planes, zero arrays or a short header list means
        the check did not run, and an unrun check is not a passing one (**SP11**). The
        header count is compared against :data:`FILE_HEADER_ATTRS` rather than tested for
        truthiness, so a leg that silently stopped comparing one of the two headers
        cannot be mistaken for one that compared both.
        """
        return (
            self.error is None
            and self.g1 is not None
            and self.g1.passed
            and len(self.planes) == len(PLANE_KEYS)
            and not self.failed_planes
            and len(self.file_headers) == len(FILE_HEADER_ATTRS)
            and all(h.equal for h in self.file_headers)
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
                f"against it, both raw file headers and all {len(self.arrays)} arrays are "
                "identical to the original store's"
            )
        parts: list[str] = []
        if self.failed_planes:
            parts.append("planes " + "+".join(p.gate for p in self.failed_planes) + " failed")
        if len(self.file_headers) != len(FILE_HEADER_ATTRS):
            parts.append(
                f"only {len(self.file_headers)} of {len(FILE_HEADER_ATTRS)} raw file "
                "headers were compared"
            )
        for header in (h for h in self.file_headers if not h.equal):
            parts.append(f"{header.header} file header: {header.detail}")
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
            "file_headers_compared": len(self.file_headers),
            "differing_file_headers": self.differing_headers,
            "file_headers": [h.to_json() for h in self.file_headers],
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
                "other (spec 7 G3, debt D19). The five planes here run export against "
                "the store built FROM that export, so they establish self-consistency; "
                "the file-header and array legs are the only ones that compare the "
                "export to the original store (DECISIONS.md D-0067)."
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

    Four questions, answered in order, each of which can kill the check:

    1. Does the export re-ingest at all, under a spec that passes **G1**? A file that
       cannot be parsed gap-free is not a SEG-Y anybody can consume.
    2. Do all five planes hold between the export and the store built from it? That is
       G2a-G2e run with the *exported file* as the source of truth. It is a
       **self-consistency** leg: the store came from the export, so this establishes the
       export survives an ingest, not that it agrees with the original.
    3. Do both of SDIP's authoritative raw file headers match the original store's, byte
       for byte? They are **attributes**, not arrays (D-0021), so question 4 never sees
       them - and without this leg a corrupted 400-byte binary header rode through as a
       PASS, measured (D-0067).
    4. Is every array of that store identical to the original store's, by
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
        planes pass, both raw file headers match, and every array matches.
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
    result.file_headers = _compare_file_headers(original, closure_store)
    result.arrays = _compare_stores(original, closure_store)
    return result
