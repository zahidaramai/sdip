"""SDIP - Seismic Data Ingestion & Preparation.

SEG-Y to MDIO/Zarr v3 conversion with a machine-checkable proof of 1-1 equivalence.

The product is not the file. The product is the file plus the proof. An MDIO store
without a passing Equivalence Certificate is an untrusted artifact, not an SDIP
deliverable.

Governing specification: SDIP Specification v1.0, referenced throughout by section
number. It is not distributed in this repository; every rule it imposes is restated in
``README.md``, ``CONTRIBUTING.md``, and the append-only ``DECISIONS.md``.
"""

from __future__ import annotations

from sdip._pins import PINS, SPEC_VERSION

__all__ = ["PINS", "SPEC_VERSION", "__version__"]


def _resolve_version() -> str:
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version("sdip")
    except PackageNotFoundError:  # pragma: no cover - source checkout without install
        return "0.0.0+unknown"


__version__: str = _resolve_version()
