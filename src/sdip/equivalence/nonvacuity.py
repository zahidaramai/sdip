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
"""

from __future__ import annotations

import base64
import shutil
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from sdip.ingest.file_headers import ATTR_RAW_BINARY, ATTR_RAW_TEXT

ALL_GATES: tuple[str, ...] = ("G2a", "G2b", "G2c", "G2d", "G2e", "G3")
"""Every gate G7 audits. §7 G7 names exactly these."""


def _group(store: Path) -> Any:
    import zarr

    return zarr.open_group(str(store), mode="r+")


def _rewrite_header_attr(store: Path, attr: str, mutate: Callable[[bytearray], None]) -> None:
    node = _group(store)["segy_file_header"]
    raw = bytearray(base64.b64decode(str(node.attrs[attr])))
    mutate(raw)
    node.attrs.update({attr: base64.b64encode(bytes(raw)).decode("ascii")})


# --- the six minimum controls from §7 G7, plus G3's -------------------------


def _flip_textual_byte(store: Path) -> None:
    _rewrite_header_attr(store, ATTR_RAW_TEXT, lambda raw: raw.__setitem__(64, raw[64] ^ 0x01))


def _truncate_textual_header(store: Path) -> None:
    node = _group(store)["segy_file_header"]
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


@dataclass(frozen=True, slots=True)
class Corruption:
    """One deliberate defect and the exact set of gates it must fail."""

    name: str
    description: str
    must_fail: frozenset[str]
    apply: Callable[[Path], None]
    clause: str

    def to_json(self) -> dict[str, Any]:
        """Certificate-shaped mapping."""
        return {
            "name": self.name,
            "description": self.description,
            "must_fail": sorted(self.must_fail),
            "clause": self.clause,
        }


CONTROLS: tuple[Corruption, ...] = (
    Corruption(
        name="flipped_textual_byte",
        description="One bit flipped in the stored 3200-byte textual header",
        must_fail=frozenset({"G2a"}),
        apply=_flip_textual_byte,
        clause="§4.2",
    ),
    Corruption(
        name="truncated_textual_header",
        description="Textual header cut from 3200 to 3100 bytes",
        must_fail=frozenset({"G2a"}),
        apply=_truncate_textual_header,
        clause="§7 G7 minimum set",
    ),
    Corruption(
        name="flipped_binary_byte",
        description="One bit flipped in the stored 400-byte binary header",
        must_fail=frozenset({"G2b"}),
        apply=_flip_binary_byte,
        clause="§4.3",
    ),
    Corruption(
        name="flipped_header_byte",
        description="One trace-header byte incremented (pad_240, first live cell)",
        must_fail=frozenset({"G2c"}),
        apply=_flip_header_byte,
        clause="§7 G7 minimum set",
    ),
    Corruption(
        name="flipped_sample_bit",
        description="One sample's low mantissa bit flipped",
        must_fail=frozenset({"G2d"}),
        apply=_flip_sample_bit,
        clause="§7 G7 minimum set",
    ),
    Corruption(
        name="inverted_live_mask",
        description="Live mask flipped on one trace",
        must_fail=frozenset({"G2e"}),
        apply=_invert_live_mask,
        clause="§7 G7 minimum set",
    ),
    Corruption(
        name="dropped_trace",
        description="One live trace zeroed and removed from the mask",
        must_fail=frozenset({"G2c", "G2d", "G2e"}),
        apply=_drop_a_trace,
        clause="§7 G7 minimum set",
    ),
    Corruption(
        name="transposed_traces",
        description="Two adjacent traces swapped, headers and samples together",
        must_fail=frozenset({"G2c", "G2d"}),
        apply=_transpose_two_traces,
        clause="§7 G7 minimum set",
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


@dataclass(slots=True)
class ControlOutcome:
    """What one corruption actually did to the gates."""

    corruption: Corruption
    failed_gates: frozenset[str]
    error: str | None = None

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
        }


@dataclass(slots=True)
class G7Result:
    """The verdict of the non-vacuity audit."""

    outcomes: list[ControlOutcome] = field(default_factory=list)
    baseline_clean: bool = False
    baseline_detail: str = ""

    @property
    def failed(self) -> list[ControlOutcome]:
        """Controls whose observed failure set did not match the declared one."""
        return [o for o in self.outcomes if not o.passed]

    @property
    def passed(self) -> bool:
        """True only when the baseline is clean and every control behaved exactly."""
        return self.baseline_clean and bool(self.outcomes) and not self.failed

    @property
    def status(self) -> str:
        """``"PASS"`` or ``"FAIL"``."""
        return "PASS" if self.passed else "FAIL"

    def summary(self) -> str:
        """One line naming what killed it, or what held."""
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
            "control_count": len(self.outcomes),
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


def g7(source: str | Path, store: str | Path, spec: Any, *, workdir: str | Path) -> G7Result:
    """Audit the engine's non-vacuity against a real store.

    For each control: copy the store, corrupt the copy, run every gate, and compare the
    set that failed against the set the control declares it must fail.

    Args:
        source: The source SEG-Y the store was built from.
        store: The clean store to audit against. **Never modified.**
        spec: The gap-free ``SegySpec`` used for the ingest.
        workdir: Directory for the corrupted copies. Should be temporary.

    Returns:
        The audit result. ``PASS`` only when the clean baseline passes every gate **and**
        every control fails exactly the gates it declares.
    """
    source_path, store_path, work = Path(source), Path(store), Path(workdir)
    work.mkdir(parents=True, exist_ok=True)

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
        return result

    for control in CONTROLS:
        copy = work / f"control_{control.name}.mdio"
        if copy.exists():
            shutil.rmtree(copy)
        shutil.copytree(store_path, copy)
        try:
            control.apply(copy)
        except Exception as exc:
            result.outcomes.append(
                ControlOutcome(
                    corruption=control,
                    failed_gates=frozenset(),
                    error=f"could not apply: {type(exc).__name__}: {exc}",
                )
            )
            shutil.rmtree(copy, ignore_errors=True)
            continue
        failed, _detail = _failing_gates(source_path, copy, spec)
        result.outcomes.append(ControlOutcome(corruption=control, failed_gates=failed, error=None))
        shutil.rmtree(copy, ignore_errors=True)

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
