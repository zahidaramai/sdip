"""**Gate G4 — portability.** Specification §7 G4, §10.3.

    PASS iff the store opens and reads correctly with stock `zarr-python` and stock
    `xarray` in a process where `mdio` is never imported (asserted via `sys.modules`).

**This is the gate that makes adopting SDIP reversible.** §10.3: no consumer is required
to install `sdip` or `mdio`. If that ever stops being true the data is locked into a
schema, and the project's central promise — *"the data is already in an open format and
nothing needs migrating"* — is false.

**It runs in a subprocess, and it has to.** The checking process has already imported
`mdio` to do the ingest; asserting `"mdio" not in sys.modules` there would always fail,
and asserting it after a `del` would be theatre. A clean interpreter is the only honest
way to ask the question, so the child asserts the absence itself, before touching the
store, and reports what it found as JSON.

The gate also records, per array, whether its ``data_type`` is Zarr v3 **core spec** or
an extension. That is measured from ``zarr.json`` and needs no warning from anybody — the
warning MDIO suppresses is a signal, the store is the evidence (``DECISIONS.md`` D-0004).
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

CHILD_PROGRAM = r"""
import json, sys

report = {"mdio_imported_at_start": "mdio" in sys.modules, "steps": {}, "arrays": {}}
store = sys.argv[1]

try:
    import zarr
    report["zarr_version"] = zarr.__version__
    group = zarr.open_group(store, mode="r")
    names = sorted(n for n, _ in group.arrays())
    report["steps"]["zarr_open_group"] = True
    report["array_names"] = names

    for name in names:
        array = group[name]
        meta = array.metadata.to_dict()
        dt = meta.get("data_type")
        entry = {
            "data_type": dt if isinstance(dt, str) else json.loads(json.dumps(dt, default=str)),
            "zarr_v3_core_spec": isinstance(dt, str),
            "shape": list(array.shape),
        }
        try:
            values = array[...]
            entry["read"] = True
            entry["nbytes"] = int(getattr(values, "nbytes", 0))
        except Exception as exc:
            entry["read"] = False
            entry["error"] = f"{type(exc).__name__}: {exc}"
        report["arrays"][name] = entry
    report["steps"]["zarr_read_all"] = all(a.get("read") for a in report["arrays"].values())
except Exception as exc:
    report["steps"]["zarr_open_group"] = False
    report["zarr_error"] = f"{type(exc).__name__}: {exc}"

try:
    import xarray
    report["xarray_version"] = xarray.__version__
    dataset = xarray.open_zarr(store, consolidated=False)
    report["steps"]["xarray_open_zarr"] = True
    report["xarray_data_vars"] = sorted(str(v) for v in dataset.data_vars)
    report["xarray_coords"] = sorted(str(c) for c in dataset.coords)
except Exception as exc:
    report["steps"]["xarray_open_zarr"] = False
    report["xarray_error"] = f"{type(exc).__name__}: {exc}"

# Asserted LAST as well as first: an import that sneaks in via zarr or xarray would be
# just as disqualifying as one at the top, and only checking at the start would miss it.
report["mdio_imported_at_end"] = "mdio" in sys.modules
print(json.dumps(report))
"""


@dataclass(slots=True)
class PortabilityResult:
    """G4's verdict and the per-array dtype conformance it measured."""

    report: dict[str, Any] = field(default_factory=dict)
    child_returncode: int = 0
    child_stderr: str = ""

    @property
    def mdio_absent(self) -> bool:
        """True when ``mdio`` was never imported in the checking process."""
        return not self.report.get("mdio_imported_at_start", True) and not self.report.get(
            "mdio_imported_at_end", True
        )

    @property
    def non_core_arrays(self) -> list[str]:
        """Arrays whose ``data_type`` is outside the Zarr v3 core specification."""
        return sorted(
            name
            for name, meta in self.report.get("arrays", {}).items()
            if not meta.get("zarr_v3_core_spec")
        )

    @property
    def unreadable_arrays(self) -> list[str]:
        """Arrays a stock-``zarr`` consumer could not read."""
        return sorted(
            name for name, meta in self.report.get("arrays", {}).items() if not meta.get("read")
        )

    @property
    def passed(self) -> bool:
        """True only when every array a consumer needs reads without MDIO.

        A non-core ``data_type`` alone does **not** fail the gate: §7 G4's killer is
        *"any array a consumer needs being unreadable without MDIO"*. The structured
        ``headers`` array is non-core and readable by ``zarr-python``; whether any other
        implementation can read it is probe **P4**, tracked as debt **D3**, and G4 does
        not pretend to answer it.
        """
        return (
            self.mdio_absent
            and bool(self.report.get("steps", {}).get("zarr_open_group"))
            and bool(self.report.get("steps", {}).get("xarray_open_zarr"))
            and not self.unreadable_arrays
        )

    @property
    def status(self) -> str:
        """``"PASS"`` or ``"FAIL"``."""
        return "PASS" if self.passed else "FAIL"

    def to_json(self) -> dict[str, Any]:
        """Certificate-shaped mapping."""
        return {
            "gate": "G4",
            "status": self.status,
            "mdio_never_imported": self.mdio_absent,
            "steps": self.report.get("steps", {}),
            "arrays": self.report.get("arrays", {}),
            "non_core_spec_arrays": self.non_core_arrays,
            "unreadable_arrays": self.unreadable_arrays,
            "zarr_version": self.report.get("zarr_version"),
            "xarray_version": self.report.get("xarray_version"),
            "child_returncode": self.child_returncode,
            "note": (
                "A non-core data_type does not fail G4 - the killer is an array a "
                "consumer needs being unreadable without MDIO. Cross-implementation "
                "readability is probe P4 / debt D3 and is NOT measured here."
            ),
        }


def g4(store: str | Path, *, timeout: int = 300) -> PortabilityResult:
    """Run G4 in a clean subprocess that never imports ``mdio``.

    Args:
        store: The MDIO store.
        timeout: Seconds to allow the child.

    Returns:
        The gate result, including the per-array dtype conformance table.
    """
    completed = subprocess.run(  # noqa: S603 - argv list, no shell, our own interpreter
        [sys.executable, "-c", CHILD_PROGRAM, str(Path(store))],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    try:
        report = json.loads(completed.stdout)
    except json.JSONDecodeError:
        report = {"mdio_imported_at_start": True, "steps": {}, "arrays": {}}
    return PortabilityResult(
        report=report,
        child_returncode=completed.returncode,
        child_stderr=completed.stderr[-4000:],
    )
