"""**G7 — non-vacuity. The gate on the gates.** Specification §7 G7, **SP11**.

    For each of G2a-G2e and G3, a deliberately corrupted store must FAIL that gate and
    ONLY that gate.
    Kills it: any corruption that passes, or one that fails the wrong gate.
    A gate a corrupted store passes is not a gate. G7 failure blocks certificate
    issuance for the entire engine, not just the affected plane.

**G7 is an executable gate, not a test suite.** §4.7's certificate carries
``gates: {G7: PASS|FAIL|NOT_RUN}``, and a certificate cannot report the result of a test
that ran on somebody's laptop last Tuesday. The engine corrupts a *copy* of the store it
just certified, re-runs its own checkers against it, and puts the outcome on the
certificate for **that store**. ``tests/negative/`` holds the permanent controls that
exercise this machinery; this module is the machinery.

Why *"and only that gate"* is enforced as a **declared set**, not a single gate
--------------------------------------------------------------------------------
Two transposed traces move headers **and** samples, so G2c and G2d both fail — correctly.
A control demanding exactly one failing gate would assert something false and would be
"fixed" by weakening a checker, which is the opposite of what G7 is for.

So each control declares the **exact set** of gates it must fail, and G7 asserts the
observed set **equals** the declared set. That is strictly stronger than "at least its
own gate": it catches an over-broad checker that fails everything, **and** a narrow one
that misses the corruption, in the same assertion.

Nothing here mutates the store under test. Every corruption is applied to a copy.

Why the copy is **selective** (``OPEN_DEBTS`` D18)
--------------------------------------------------
The first implementation copied the whole store once per control. Measured on a 362 MB
survey store that is 2.83 GB copied across the eight controls and 370.4 s of wall clock —
87 % of the entire pipeline, and it scales linearly with the survey. A 20 GB survey would
copy ~160 GB. That is the point at which an operator switches the gate off, and **a gate
that gets switched off is worse than one that was never written** (SP11). The cost was
therefore a correctness risk, not a performance nuisance.

Each control now declares the store subpaths it writes (:attr:`Corruption.touches`), and
the working copy is materialised from that declaration: real copies for what the control
writes, hard links for the rest. The split is drawn where it is for **safety** rather
than for speed - :func:`_materialise` gives the measurement behind that and says plainly
what today's upstream would and would not do.

Because "the original is unchanged" is no longer self-evident from ``copytree``, it is
**measured**: :func:`g7` fingerprints the store before and after the audit, reports the
answer on :attr:`G7Result.original_store_intact`, and a failure there makes G7 FAIL.
"""

from __future__ import annotations

import base64
import os
import shutil
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

import numpy as np

from sdip.ingest.file_headers import (
    ATTR_RAW_BINARY,
    ATTR_RAW_TEXT,
    UPSTREAM_FILE_HEADER_VARIABLE,
    raw_header_node,
)
from sdip.ingest.header_plane import ARRAY_NAME as RAW_HEADER_PLANE_ARRAY
from sdip.ingest.raw_samples import ARRAY_NAME as RAW_IBM32_ARRAY

ALL_GATES: tuple[str, ...] = ("G2a", "G2b", "G2c", "G2d", "G2e", "G3")
"""Every gate G7 audits. §7 G7 names exactly these."""

_METADATA_FILENAME: Final[str] = "zarr.json"
"""Zarr v3 keeps all node metadata - including attributes - in files with this name.

They are always real copies, never links, wherever they sit in the store: an operation
can rewrite metadata without touching a single chunk - an attribute update is exactly
that - so metadata is written in more places than any ``touches`` set names. They are
kilobytes. Copying every one of them costs nothing measurable and takes a whole class of
paths out of the argument in :func:`_materialise` rather than into it.

It is also what keeps the three file-header controls honest on a store that has no
``segy_file_header`` variable (D-0055): SDIP's raw attributes then live on the **root
group**, so the corruption lands in the root ``zarr.json`` - a path no ``touches`` set
names, and one this rule has already made a real copy.
"""


def _group(store: Path) -> Any:
    import zarr

    return zarr.open_group(str(store), mode="r+")


def _rewrite_header_attr(store: Path, attr: str, mutate: Callable[[bytearray], None]) -> None:
    """Corrupt one of SDIP's authoritative raw-header attributes, wherever it lives.

    Resolved through :func:`~sdip.ingest.file_headers.raw_header_node`, the one resolver
    the reader and the writer also use. A store ingested from a source whose textual
    header did not decode carries no ``segy_file_header`` variable at all (D-0055), and a
    control that assumed one would raise instead of corrupting — G7 would then report a
    control error on a store it had never actually corrupted, which is a vacuous audit
    wearing a failure's clothes.
    """
    node = raw_header_node(_group(store))
    raw = bytearray(base64.b64decode(str(node.attrs[attr])))
    mutate(raw)
    node.attrs.update({attr: base64.b64encode(bytes(raw)).decode("ascii")})


# --- the six minimum controls from §7 G7, plus G3's -------------------------


def _flip_textual_byte(store: Path) -> None:
    _rewrite_header_attr(store, ATTR_RAW_TEXT, lambda raw: raw.__setitem__(64, raw[64] ^ 0x01))


def _truncate_textual_header(store: Path) -> None:
    node = raw_header_node(_group(store))
    raw = base64.b64decode(str(node.attrs[ATTR_RAW_TEXT]))[:3100]
    node.attrs.update({ATTR_RAW_TEXT: base64.b64encode(raw).decode("ascii")})


def _flip_binary_byte(store: Path) -> None:
    _rewrite_header_attr(store, ATTR_RAW_BINARY, lambda raw: raw.__setitem__(21, raw[21] ^ 0x01))


def _flip_header_byte(store: Path) -> None:
    group = _group(store)
    headers = group["headers"][:]
    cell = tuple(0 for _ in headers.shape)
    headers["pad_240"][cell] = (int(headers["pad_240"][cell]) + 1) % 256
    group["headers"][:] = headers


def _flip_sample_bit(store: Path) -> None:
    group = _group(store)
    volume = group["amplitude"][:]
    cell = (*tuple(0 for _ in volume.shape[:-1]), 0)
    volume[cell] = (volume[cell].view(np.uint32) ^ np.uint32(1)).view(np.float32)
    group["amplitude"][:] = volume


def _invert_live_mask(store: Path) -> None:
    group = _group(store)
    mask = group["trace_mask"][:]
    cell = tuple(0 for _ in mask.shape)
    mask[cell] = 0 if mask[cell] else 1
    group["trace_mask"][:] = mask


def _drop_a_trace(store: Path) -> None:
    """Zero one trace's headers and samples and clear its mask bit.

    A Zarr store has a fixed grid, so a trace cannot be *removed* the way it can be from
    a flat SEG-Y. Dropping it means the grid cell no longer holds the trace that mapped
    to it, and the mask no longer counts it — which is exactly the observable a dropped
    trace produces, and what Plane 5's count check exists to catch.
    """
    group = _group(store)
    mask = group["trace_mask"][:]
    cell = tuple(int(i[0]) for i in np.nonzero(mask))
    mask[cell] = 0
    group["trace_mask"][:] = mask
    headers = group["headers"][:]
    for name in headers.dtype.names or ():
        headers[name][cell] = 0
    group["headers"][:] = headers
    volume = group["amplitude"][:]
    volume[cell] = 0
    group["amplitude"][:] = volume


def _transpose_two_traces(store: Path) -> None:
    group = _group(store)
    for name in ("headers", "amplitude"):
        data = group[name][:]
        # Both arrays are indexed by the same leading grid dimensions; amplitude
        # carries a trailing sample axis that a whole-cell swap moves with it.
        first = tuple(0 for _ in range(2))
        second = (*first[:-1], first[-1] + 1)
        a, b = data[first].copy(), data[second].copy()
        data[first], data[second] = b, a
        group[name][:] = data


def _flip_raw_ibm32_word(store: Path) -> None:
    """Flip one bit of one undecoded IBM word in ``amplitude_raw_ibm32``.

    The raw view is the only recoverable copy of the source bits for an ``ibm32``
    source (`OPEN_DEBTS.md` D1), so a defect in it is silent by construction: the
    decoded ``amplitude`` array is untouched and every float comparison still passes.
    Without this control, SDIP could write a corrupted raw view and no gate would notice.
    """
    import numpy as np

    group = _group(store)
    if RAW_IBM32_ARRAY not in group:
        msg = f"{RAW_IBM32_ARRAY} absent; this control applies only to an ibm32 source"
        raise KeyError(msg)
    words = group[RAW_IBM32_ARRAY][:]
    cell = (*tuple(0 for _ in words.shape[:-1]), 0)
    words[cell] = np.uint32(int(words[cell]) ^ 1)
    group[RAW_IBM32_ARRAY][:] = words


DERIVED_COORD_ARRAY: Final[str] = "cdp_x"
"""Derived coordinate array corrupted by :func:`_corrupt_cdp_coordinate`.

``cdp_x`` rather than ``cdp_y`` for no deeper reason than that one of the pair suffices
to prove the leg fires; both are checked by the leg itself.
"""


def _corrupt_cdp_coordinate(store: Path) -> None:
    """Shift one derived world coordinate by one unit.

    **This is the control for the hole an external audit found (D-0056).** Before the
    derived-array leg existed, corrupting ``cdp_x`` left **all five planes PASS** - and
    G4 and §10.3 promote exactly this array as what a consumer reads, so a store could
    carry corrupted world coordinates under an ``EQUIVALENT`` verdict.

    One unit, not a wild value, on purpose: a coordinate-scalar sign error - ``-100``
    meaning divide where multiply was intended - is the realistic geometry defect, and it
    is quiet. A control that only caught absurd values would not catch the real bug.
    """
    import numpy as np

    group = _group(store)
    if DERIVED_COORD_ARRAY not in group:
        msg = f"{DERIVED_COORD_ARRAY} absent; the store carries no derived coordinates"
        raise KeyError(msg)
    values = np.asarray(group[DERIVED_COORD_ARRAY][:])
    cell = tuple(0 for _ in values.shape)
    values[cell] = values[cell] + 1
    group[DERIVED_COORD_ARRAY][:] = values


def _corrupt_sample_axis(store: Path) -> None:
    """Shift the first entry of the sample axis by one unit.

    The samples themselves are untouched, so **every float comparison still passes**:
    the corruption mislabels where the samples sit in time or depth without altering
    what they are. That is precisely why the decoded leg cannot see it, and why this
    control is not redundant with ``flipped_sample_bit``.

    The axis is found from the data variable's Zarr v3 ``dimension_names`` rather than
    assumed to be ``"time"`` - a depth-domain store names it ``depth`` (D-0039).
    """
    import numpy as np

    from sdip.equivalence.planes import _sample_axis_name, store_dimensions

    group = _group(store)
    axis = _sample_axis_name(group, "amplitude", store_dimensions(group))
    if axis is None or axis not in group:
        msg = "store declares no sample axis distinct from its grid dimensions"
        raise KeyError(msg)
    values = np.asarray(group[axis][:])
    values[0] = values[0] + 1
    group[axis][:] = values


def _delete_array(store: Path, name: str) -> None:
    """Remove a whole array from the store, the way a died-midway ingest leaves it."""
    target = store / name
    if not target.exists():
        msg = f"{name} absent; nothing to delete"
        raise KeyError(msg)
    shutil.rmtree(target)


def _delete_raw_ibm32_array(store: Path) -> None:
    """Delete the entire ``amplitude_raw_ibm32`` array.

    **This is the control for D-0061, and the asymmetry is the whole point.** Deleting
    one *chunk* of this array already failed G2d; deleting the *whole array* passed,
    because an absent array was read as "not checked" rather than "missing". A store
    left this way by an ingest that died between writes certified **EQUIVALENT** while
    missing the only recoverable copy of the source bits (D1).
    """
    _delete_array(store, RAW_IBM32_ARRAY)


def _delete_raw_header_plane(store: Path) -> None:
    """Delete the entire ``headers_raw_uint8`` array. See :func:`_delete_raw_ibm32_array`."""
    _delete_array(store, RAW_HEADER_PLANE_ARRAY)


def _delete_derived_coordinate(store: Path) -> None:
    """Delete the entire ``cdp_x`` array — the declared transform's output (D-0040)."""
    _delete_array(store, DERIVED_COORD_ARRAY)


RAW_HEADER_PLANE_BYTE: Final[int] = 232
"""Byte offset flipped by :func:`_flip_raw_header_byte`. 0-based, so header byte **233**.

Deliberately inside the tail the rev 1 standard leaves unnamed — the bytes **SP4/SP5**
exist to cover and the ones a sparse spec drops silently. The existing
``flipped_header_byte`` control mutates ``pad_240`` in the *structured* array, so the two
controls touch different bytes in different arrays and neither can stand in for the other.
"""


def _flip_raw_header_byte(store: Path) -> None:
    """Flip one bit of one raw header byte in ``headers_raw_uint8``.

    The ``uint8`` plane is the copy of the trace headers a non-Python consumer can
    actually read: probe **P4** measured zarr-java refusing the structured array's
    ``struct`` ``data_type`` outright, and ``struct`` has no Zarr v3 specification, so
    that refusal is conformant (`DECISIONS.md` D-0047). A defect in the plane is silent
    by construction — the structured ``headers`` array is untouched and every field-wise
    comparison still passes. Without this control, SDIP could write a corrupted plane and
    no gate would notice.
    """
    group = _group(store)
    if RAW_HEADER_PLANE_ARRAY not in group:
        msg = f"{RAW_HEADER_PLANE_ARRAY} absent; the store carries no uint8 header plane"
        raise KeyError(msg)
    plane = group[RAW_HEADER_PLANE_ARRAY][:]
    cell = (*tuple(0 for _ in plane.shape[:-1]), RAW_HEADER_PLANE_BYTE)
    plane[cell] = np.uint8(int(plane[cell]) ^ 1)
    group[RAW_HEADER_PLANE_ARRAY][:] = plane


@dataclass(frozen=True, slots=True)
class Corruption:
    """One deliberate defect and the exact set of gates it must fail."""

    name: str
    description: str
    must_fail: frozenset[str]
    apply: Callable[[Path], None]
    clause: str
    touches: frozenset[str]
    """Store subpaths ``apply`` writes, relative to the store root, POSIX-separated.

    A **declaration of write scope**, and the working copy is built from it: everything
    named here (and everything beneath it) is a real copy; everything else is hard-linked
    from the store under audit. Under-declaring is a safety regression rather than a
    missed optimisation - it stakes the integrity of the store being certified on how
    upstream happens to write its chunks, which :func:`_materialise` explains SDIP will
    not do. There is deliberately **no default**, so a new control cannot acquire an
    empty write scope by omission, and :func:`g7` measures the store afterwards rather
    than trusting the declaration.

    Subpaths are whole Zarr nodes, not chunks. A control that assigns to a whole array
    (``group["amplitude"][:] = volume``) rewrites every chunk of it, so nothing finer
    would be honest.
    """

    def to_json(self) -> dict[str, Any]:
        """Certificate-shaped mapping."""
        return {
            "name": self.name,
            "description": self.description,
            "must_fail": sorted(self.must_fail),
            "clause": self.clause,
            "touches": sorted(self.touches),
        }


CONTROLS: tuple[Corruption, ...] = (
    Corruption(
        name="flipped_textual_byte",
        description="One bit flipped in the stored 3200-byte textual header",
        must_fail=frozenset({"G2a"}),
        apply=_flip_textual_byte,
        clause="§4.2",
        # An attribute rewrite on one node. Kilobytes, not a survey.
        touches=frozenset({UPSTREAM_FILE_HEADER_VARIABLE}),
    ),
    Corruption(
        name="truncated_textual_header",
        description="Textual header cut from 3200 to 3100 bytes",
        must_fail=frozenset({"G2a"}),
        apply=_truncate_textual_header,
        clause="§7 G7 minimum set",
        touches=frozenset({UPSTREAM_FILE_HEADER_VARIABLE}),
    ),
    Corruption(
        name="flipped_binary_byte",
        description="One bit flipped in the stored 400-byte binary header",
        must_fail=frozenset({"G2b"}),
        apply=_flip_binary_byte,
        clause="§4.3",
        touches=frozenset({UPSTREAM_FILE_HEADER_VARIABLE}),
    ),
    Corruption(
        name="flipped_header_byte",
        description="One trace-header byte incremented (pad_240, first live cell)",
        must_fail=frozenset({"G2c"}),
        apply=_flip_header_byte,
        clause="§7 G7 minimum set",
        touches=frozenset({"headers"}),
    ),
    Corruption(
        name="flipped_sample_bit",
        description="One sample's low mantissa bit flipped",
        must_fail=frozenset({"G2d"}),
        apply=_flip_sample_bit,
        clause="§7 G7 minimum set",
        touches=frozenset({"amplitude"}),
    ),
    Corruption(
        name="inverted_live_mask",
        description="Live mask flipped on one trace",
        must_fail=frozenset({"G2e"}),
        apply=_invert_live_mask,
        clause="§7 G7 minimum set",
        touches=frozenset({"trace_mask"}),
    ),
    Corruption(
        name="dropped_trace",
        description="One live trace zeroed and removed from the mask",
        must_fail=frozenset({"G2c", "G2d", "G2e"}),
        apply=_drop_a_trace,
        clause="§7 G7 minimum set",
        # Zeroes headers and samples and clears the mask bit: three arrays, all written.
        touches=frozenset({"trace_mask", "headers", "amplitude"}),
    ),
    Corruption(
        name="flipped_raw_header_byte",
        description="One bit flipped in the undecoded uint8 header plane (byte 233)",
        must_fail=frozenset({"G2c"}),
        apply=_flip_raw_header_byte,
        touches=frozenset({RAW_HEADER_PLANE_ARRAY}),
        clause="probe P4 / DECISIONS D-0047 - the portable copy of the trace headers",
    ),
    Corruption(
        name="flipped_raw_ibm32_word",
        description="One bit flipped in the undecoded uint32 sample word",
        must_fail=frozenset({"G2d"}),
        apply=_flip_raw_ibm32_word,
        touches=frozenset({RAW_IBM32_ARRAY}),
        clause="OPEN_DEBTS D1 - the only recoverable copy of the source bits",
    ),
    Corruption(
        name="transposed_traces",
        description="Two adjacent traces swapped, headers and samples together",
        must_fail=frozenset({"G2c", "G2d"}),
        apply=_transpose_two_traces,
        clause="§7 G7 minimum set",
        touches=frozenset({"headers", "amplitude"}),
    ),
    Corruption(
        name="corrupted_cdp_coordinate",
        description="One derived world coordinate shifted by one unit (cdp_x)",
        must_fail=frozenset({"G2c"}),
        apply=_corrupt_cdp_coordinate,
        touches=frozenset({DERIVED_COORD_ARRAY}),
        clause="DECISIONS D-0056 - the declared coordinate-scalar transform's output",
    ),
    Corruption(
        name="corrupted_sample_axis",
        description="First entry of the sample axis shifted by one unit",
        must_fail=frozenset({"G2d"}),
        apply=_corrupt_sample_axis,
        touches=frozenset({"time"}),
        clause="DECISIONS D-0056 - samples are meaningless without their axis",
    ),
    Corruption(
        name="deleted_raw_ibm32_array",
        description="The whole amplitude_raw_ibm32 array removed, as a died ingest leaves it",
        must_fail=frozenset({"G2d"}),
        apply=_delete_raw_ibm32_array,
        touches=frozenset({RAW_IBM32_ARRAY}),
        clause="DECISIONS D-0061 - one chunk failed, the whole array passed",
    ),
    Corruption(
        name="deleted_derived_coordinate",
        description="The whole cdp_x array removed",
        must_fail=frozenset({"G2c"}),
        apply=_delete_derived_coordinate,
        touches=frozenset({DERIVED_COORD_ARRAY}),
        clause="DECISIONS D-0061 - the declared transform's output must exist",
    ),
)
"""The permanent control set. Covers every gate in :data:`ALL_GATES` except G3.

``dropped_trace`` and ``transposed_traces`` declare multi-gate sets because that is what
they genuinely do: zeroing a trace changes its headers, its samples **and** the mask, and
swapping two traces moves headers **and** samples. Declaring a single gate for either
would assert something false.

**G3 is audited separately** by :func:`g3_control`: it needs a corrupted *export file*,
not a corrupted store, so it cannot share this machinery.
"""


# --- selective materialisation of the working copy - OPEN_DEBTS D18 ---------


@dataclass(frozen=True, slots=True)
class _CopyCost:
    """What building one working copy actually moved."""

    bytes_copied: int = 0
    bytes_hardlinked: int = 0


def _is_touched(relative: str, touches: frozenset[str]) -> bool:
    """True when ``relative`` is, or lies under, a subpath the control declares it writes."""
    return any(relative == node or relative.startswith(f"{node}/") for node in touches)


def _materialise(store: Path, dest: Path, touches: frozenset[str]) -> _CopyCost:
    """Build a control's working copy at ``dest``, copying only what it will write.

    Real copies for everything under a declared ``touches`` subpath and for every
    ``zarr.json``; hard links for everything else.

    **Why a modified path must be a real copy and never a hard link.**
    A hard link is a second *name* for one inode, not a second copy of the bytes, so
    whether a write through one reaches the store under audit depends entirely on *how*
    the writer writes. Truncate-and-rewrite in place (``open(path, "wb")``) writes
    through to every name for that inode. Write-to-temp-then-rename does not: the rename
    swaps only the directory entry the writer holds.

    **Measured, not assumed** (SP8). Under the resolved ``zarr`` 3.3.0,
    ``LocalStore._put`` goes through ``_atomic_write``, which writes a ``.partial`` file
    and calls ``Path.replace``. Hard-linking a whole store, writing chunks *and*
    attributes into the copy, then re-reading the original leaves the original's inodes
    and bytes identical - so today's upstream does **not** write through, and this
    function could hard-link everything and still be correct.

    It does not, because that correctness is on loan. ``zarr`` arrives here as a
    *transitive* dependency: SDIP's binding pins are ``multidimio`` and ``segy`` (§3.2),
    and neither pins ``LocalStore``'s write strategy. Upstream reverting to an in-place
    write would silently convert G7 from an auditor of the store into a corrupter of it,
    with no signal at the SDIP boundary and a certificate issued over the damage. Copying
    the declared write scope costs a fraction of a whole-store copy and removes that
    dependency entirely, which is the trade §7 G7 exists to make.

    Hard-linking the remainder rests on a narrower and locally verifiable claim: nothing
    in the audit opens those paths for writing at all. The checkers open the store
    read-only (``mode="r"``), and a corruption writes only what it declared. That "only"
    is still a declaration, so :func:`g7` measures it afterwards rather than trusting it.

    Args:
        store: The store under audit. Read, never written.
        dest: Directory to build. Must not already exist.
        touches: Subpaths of ``store``, POSIX-separated, that the control writes.

    Returns:
        The bytes really copied and the bytes hard-linked.
    """
    copied = linked = 0
    dest.mkdir(parents=True)
    for path in sorted(store.rglob("*")):
        relative = path.relative_to(store).as_posix()
        target = dest / relative
        if path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        size = path.stat().st_size
        if path.name == _METADATA_FILENAME or _is_touched(relative, touches):
            shutil.copy2(path, target)
            copied += size
            continue
        try:
            os.link(path, target)
        except OSError:
            # Cross-device, or a filesystem without hard links. A real copy is always
            # correct here - only slower - so degrade rather than fail the gate.
            shutil.copy2(path, target)
            copied += size
        else:
            linked += size
    return _CopyCost(bytes_copied=copied, bytes_hardlinked=linked)


def _content_fingerprint(store: Path) -> dict[str, str]:
    """SHA-256 of every file in the store. The authoritative unchanged-ness evidence."""
    from sdip.provenance.hashing import sha256_tree

    return sha256_tree(store)


def _stat_tripwire(store: Path) -> dict[str, tuple[int, int, int]]:
    """``{relative path: (inode, size, mtime_ns)}`` - a content-free write tripwire.

    Cheap enough to run after every control, which is the point: it stops a mis-declared
    ``touches`` at the **first** control instead of letting the remaining seven compound
    the damage. A write through a hard link keeps the inode - that is what a hard link
    is - but moves ``mtime``, so the pair is the signal.

    Creating and removing the links themselves move the original's ``ctime`` (its link
    count changes) and never its ``mtime``, which is why ``ctime`` is not compared.

    This is a tripwire, not proof: a filesystem with coarse timestamps could miss a
    write. :func:`_content_fingerprint` is the proof.
    """
    signature: dict[str, tuple[int, int, int]] = {}
    for path in sorted(store.rglob("*")):
        if not path.is_file():
            continue
        info = path.stat()
        signature[path.relative_to(store).as_posix()] = (
            info.st_ino,
            info.st_size,
            info.st_mtime_ns,
        )
    return signature


def _differences(before: Mapping[str, Any], after: Mapping[str, Any]) -> list[str]:
    """Keys present in one mapping only, or mapped to different values. Sorted."""
    changed = set(before) ^ set(after)
    changed |= {key for key in before.keys() & after.keys() if before[key] != after[key]}
    return sorted(changed)


@dataclass(slots=True)
class ControlOutcome:
    """What one corruption actually did to the gates."""

    corruption: Corruption
    failed_gates: frozenset[str]
    error: str | None = None
    bytes_copied: int = 0
    """Bytes really copied to build this control's working copy."""
    bytes_hardlinked: int = 0
    """Bytes shared with the store under audit by hard link, and so never copied."""

    @property
    def passed(self) -> bool:
        """True when the observed failure set is exactly the declared one."""
        return self.error is None and self.failed_gates == self.corruption.must_fail

    @property
    def unexpected(self) -> list[str]:
        """Gates that failed but should not have. An over-broad checker."""
        return sorted(self.failed_gates - self.corruption.must_fail)

    @property
    def missed(self) -> list[str]:
        """Gates that should have failed and did not - a gate that is not a gate."""
        return sorted(self.corruption.must_fail - self.failed_gates)

    def to_json(self) -> dict[str, Any]:
        """Certificate-shaped mapping."""
        return {
            **self.corruption.to_json(),
            "observed_failures": sorted(self.failed_gates),
            "unexpected_failures": self.unexpected,
            "missed_failures": self.missed,
            "error": self.error,
            "status": "PASS" if self.passed else "FAIL",
            "bytes_copied": self.bytes_copied,
            "bytes_hardlinked": self.bytes_hardlinked,
        }


@dataclass(slots=True)
class G7Result:
    """The verdict of the non-vacuity audit."""

    outcomes: list[ControlOutcome] = field(default_factory=list)
    baseline_clean: bool = False
    baseline_detail: str = ""
    original_store_intact: bool = False
    """Whether the store under audit is byte-for-byte what it was before G7 ran.

    Defaults to **False** so that no path out of :func:`g7` - including one taken by an
    exception - can leave the result claiming an integrity it never measured. It is set
    only by comparing SHA-256 over every file before and after.
    """
    original_store_detail: str = "not verified"

    @property
    def failed(self) -> list[ControlOutcome]:
        """Controls whose observed failure set did not match the declared one."""
        return [o for o in self.outcomes if not o.passed]

    @property
    def bytes_copied(self) -> int:
        """Bytes really copied across the whole audit."""
        return sum(o.bytes_copied for o in self.outcomes)

    @property
    def bytes_hardlinked(self) -> int:
        """Bytes shared by hard link across the whole audit, and so never copied."""
        return sum(o.bytes_hardlinked for o in self.outcomes)

    @property
    def whole_store_copy_bytes(self) -> int:
        """What one whole-store copy per control would have cost - the D18 baseline.

        Every control materialises the entire store one way or the other, so the two
        figures together are exactly what ``copytree`` moved before D18.
        """
        return self.bytes_copied + self.bytes_hardlinked

    @property
    def passed(self) -> bool:
        """True only when baseline, controls and the store's own integrity all held.

        The last conjunct is not decoration. The working copies share inodes with the
        store, so a mis-declared write scope would corrupt the store being certified;
        that must make the gate FAIL, not appear as a footnote under a PASS.
        """
        return (
            self.baseline_clean
            and bool(self.outcomes)
            and not self.failed
            and self.original_store_intact
        )

    @property
    def status(self) -> str:
        """``"PASS"`` or ``"FAIL"``."""
        return "PASS" if self.passed else "FAIL"

    def summary(self) -> str:
        """One line naming what killed it, or what held."""
        if not self.original_store_intact:
            # Loudest first: this one says the audit damaged the artifact being
            # certified, which outranks anything a control did or did not detect.
            return f"G7 FAIL: {self.original_store_detail}"
        if not self.baseline_clean:
            return f"G7 FAIL: baseline is not clean - {self.baseline_detail}"
        if self.passed:
            return (
                f"G7 PASS: {len(self.outcomes)} corruptions, each failing exactly the "
                "gates it must and no others"
            )
        parts = []
        for outcome in self.failed:
            if outcome.missed:
                parts.append(f"{outcome.corruption.name} PASSED {'+'.join(outcome.missed)}")
            if outcome.unexpected:
                parts.append(
                    f"{outcome.corruption.name} also failed {'+'.join(outcome.unexpected)}"
                )
            if outcome.error:
                parts.append(f"{outcome.corruption.name} errored: {outcome.error}")
        return "G7 FAIL: " + "; ".join(parts)

    def to_json(self) -> dict[str, Any]:
        """Certificate-shaped mapping."""
        return {
            "gate": "G7",
            "status": self.status,
            "summary": self.summary(),
            "baseline_clean": self.baseline_clean,
            "original_store_intact": self.original_store_intact,
            "original_store_detail": self.original_store_detail,
            "control_count": len(self.outcomes),
            "bytes_copied": self.bytes_copied,
            "bytes_hardlinked": self.bytes_hardlinked,
            "bytes_if_whole_store_copied_per_control": self.whole_store_copy_bytes,
            "controls": [o.to_json() for o in self.outcomes],
            "note": (
                "A gate a corrupted store passes is not a gate. Each control declares "
                "the exact set of gates it must fail; the observed set must equal it, "
                "which catches an over-broad checker and a narrow one alike."
            ),
        }


def _failing_gates(source: Path, store: Path, spec: Any) -> tuple[frozenset[str], str | None]:
    """Run every store-scoped gate and return the set that failed."""
    from sdip.equivalence.planes import plane_1, plane_2, plane_3, plane_4, plane_5

    checkers: tuple[tuple[str, Callable[[], Any]], ...] = (
        ("G2a", lambda: plane_1(source, store)),
        ("G2b", lambda: plane_2(source, store)),
        ("G2c", lambda: plane_3(source, store, spec, g1_passed=True)),
        ("G2d", lambda: plane_4(source, store, spec)),
        ("G2e", lambda: plane_5(source, store, spec)),
    )
    failed: set[str] = set()
    for gate, run in checkers:
        try:
            outcome = run()
            if not outcome.passed:
                failed.add(gate)
        except Exception as exc:
            # A corruption that makes a checker raise HAS been detected by it. Silently
            # treating a raise as a pass would be the exact vacuity G7 exists to catch.
            failed.add(gate)
            if gate not in {"G2a", "G2b"}:
                return frozenset(failed), f"{gate} raised {type(exc).__name__}: {exc}"
    return frozenset(failed), None


def _verify_original(result: G7Result, store: Path, before: dict[str, str]) -> None:
    """Measure whether the store under audit is byte-identical to what it was, and record it.

    Args:
        result: The result to annotate. Mutated in place.
        store: The store under audit.
        before: Its content fingerprint taken before anything in the audit ran.
    """
    changed = _differences(before, _content_fingerprint(store))
    result.original_store_intact = not changed
    result.original_store_detail = (
        f"store under audit unchanged: {len(before)} files byte-identical before and after"
        if not changed
        else (
            "the store under audit was MODIFIED by G7 itself - "
            f"{len(changed)} file(s), first: {', '.join(changed[:5])}"
        )
    )


def g7(source: str | Path, store: str | Path, spec: Any, *, workdir: str | Path) -> G7Result:
    """Audit the engine's non-vacuity against a real store.

    For each control: materialise a working copy of the store, corrupt the copy, run every
    gate, and compare the set that failed against the set the control declares it must
    fail.

    The working copy is built from the control's declared write scope
    (:attr:`Corruption.touches`) rather than by copying the whole store, because the whole
    store copy made the gate unaffordable at survey scale and an unaffordable gate gets
    switched off (D18, SP11). The copies share unwritten bytes with the store by hard
    link, so ``store`` being unmodified is a claim with a mechanism behind it - and
    therefore one that is **measured** here, twice: a cheap ``stat`` tripwire after every
    control so a mis-declaration stops at the first one, and a SHA-256 fingerprint over
    every file before and after as the proof. Either failing makes the result FAIL.

    Args:
        source: The source SEG-Y the store was built from.
        store: The clean store to audit against. **Never modified**, and verified so.
        spec: The gap-free ``SegySpec`` used for the ingest.
        workdir: Directory for the corrupted copies. Should be temporary, and on the same
            filesystem as ``store`` if the hard links are to be usable.

    Returns:
        The audit result. ``PASS`` only when the clean baseline passes every gate, every
        control fails exactly the gates it declares, **and** the store came through the
        audit byte-for-byte unchanged.
    """
    source_path, store_path, work = Path(source), Path(store), Path(workdir)
    work.mkdir(parents=True, exist_ok=True)

    # Read both fingerprints before anything else runs, so they describe the store as it
    # was handed over rather than as G7 left it.
    before_content = _content_fingerprint(store_path)
    before_stat = _stat_tripwire(store_path)

    # The baseline matters as much as the controls. If the clean store does not pass
    # every gate, "the corrupted one failed" proves nothing at all.
    baseline, baseline_error = _failing_gates(source_path, store_path, spec)
    result = G7Result(
        baseline_clean=not baseline and baseline_error is None,
        baseline_detail=(
            "clean store passes every gate"
            if not baseline
            else f"clean store already fails {', '.join(sorted(baseline))}"
            + (f" ({baseline_error})" if baseline_error else "")
        ),
    )
    if not result.baseline_clean:
        _verify_original(result, store_path, before_content)
        return result

    for control in CONTROLS:
        copy = work / f"control_{control.name}.mdio"
        if copy.exists():
            shutil.rmtree(copy)
        cost = _materialise(store_path, copy, control.touches)
        outcome = ControlOutcome(
            corruption=control,
            failed_gates=frozenset(),
            bytes_copied=cost.bytes_copied,
            bytes_hardlinked=cost.bytes_hardlinked,
        )
        try:
            control.apply(copy)
        except Exception as exc:
            outcome.error = f"could not apply: {type(exc).__name__}: {exc}"
        else:
            outcome.failed_gates, _detail = _failing_gates(source_path, copy, spec)
        result.outcomes.append(outcome)
        shutil.rmtree(copy, ignore_errors=True)

        # Stop at the first control that wrote through a link instead of letting the
        # remaining ones compound the damage to the store being certified.
        touched = _differences(before_stat, _stat_tripwire(store_path))
        if touched:
            _verify_original(result, store_path, before_content)
            result.original_store_intact = False
            result.original_store_detail = (
                f"control {control.name} wrote into the store under audit - "
                f"{len(touched)} file(s) changed on disk, first: {', '.join(touched[:5])}; "
                f"content check says: {result.original_store_detail}"
            )
            return result

    _verify_original(result, store_path, before_content)
    return result


def g3_control(export_path: str | Path, offset: int = 3700) -> dict[str, Any]:
    """G7's control for **G3**: flip one byte of an exported SEG-Y.

    Separate from :data:`CONTROLS` because G3 compares two *files*, so its control
    corrupts an export rather than a store.

    Returns:
        ``{"detected": bool, "offset": int, ...}`` - ``detected`` must be True.
    """
    from sdip.provenance.hashing import sha256_file

    path = Path(export_path)
    before = sha256_file(path)
    payload = bytearray(path.read_bytes())
    payload[offset] ^= 0x01
    path.write_bytes(bytes(payload))
    after = sha256_file(path)
    payload[offset] ^= 0x01
    path.write_bytes(bytes(payload))
    restored = sha256_file(path)
    return {
        "name": "roundtrip_byte_change",
        "description": f"One bit flipped at byte {offset} of the exported SEG-Y",
        "must_fail": ["G3"],
        "detected": before != after,
        "restored_cleanly": restored == before,
        "offset": offset,
        "status": "PASS" if before != after and restored == before else "FAIL",
        "clause": "§7 G3",
    }
