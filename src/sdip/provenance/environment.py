"""Full environment capture for the certificate. Spec sections 4.7 and 11.3."""

from __future__ import annotations

import platform
import sys
from dataclasses import dataclass, field
from importlib.metadata import PackageNotFoundError, version
from typing import Any

from sdip._pins import PINS

_RECORDED = (
    "multidimio",
    "segy",
    "zarr",
    "xarray",
    "numpy",
    "dask",
    "numcodecs",
    "pandas",
    "fsspec",
)


def _version_or_none(name: str) -> str | None:
    try:
        return version(name)
    except PackageNotFoundError:
        return None


@dataclass(slots=True)
class EnvironmentCapture:
    """Everything about the interpreter and dependency set that a rerun would need."""

    python: str
    python_implementation: str
    platform: str
    machine: str
    packages: dict[str, str | None] = field(default_factory=dict)
    declared_pins: dict[str, dict[str, str]] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        """Certificate-shaped mapping."""
        return {
            "python": self.python,
            "python_implementation": self.python_implementation,
            "platform": self.platform,
            "machine": self.machine,
            "packages": dict(self.packages),
            "declared_pins": {k: dict(v) for k, v in self.declared_pins.items()},
        }


def capture_environment() -> EnvironmentCapture:
    """Capture the running environment for the certificate ``env`` block."""
    return EnvironmentCapture(
        python=platform.python_version(),
        python_implementation=platform.python_implementation(),
        platform=f"{platform.system()} {platform.release()}",
        machine=platform.machine(),
        packages={name: _version_or_none(name) for name in _RECORDED}
        | {"python_full": sys.version.split()[0]},
        declared_pins={
            pin.distribution: {
                "version": pin.version,
                "commit_sha": pin.commit_sha,
                "repository": pin.repository,
                "sha_verification": "declared-not-runtime-verified",
            }
            for pin in PINS
        },
    )
