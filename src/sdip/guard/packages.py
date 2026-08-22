"""Barred packages. Spec section 9.2 / SP3.

``zfpy`` is a lossy codec. Its presence in the environment means a store could be
written lossily without the write path changing, so absence is asserted at the
environment level rather than at the call site.
"""

from __future__ import annotations

import importlib.util
from dataclasses import dataclass

from sdip._pins import BARRED_MODULES


@dataclass(frozen=True, slots=True)
class PackageFinding:
    """One barred module found importable in the current interpreter."""

    module: str
    reason: str
    origin: str | None


def check_barred_packages() -> list[PackageFinding]:
    """Return a finding for every barred module that is importable.

    Uses ``importlib.util.find_spec``, which locates a module without executing it.
    Every barred entry is a top-level name, so no parent package is imported as a
    side effect of the lookup.

    Returns:
        Findings in declaration order. Empty means the environment is clean.
    """
    findings: list[PackageFinding] = []
    for module, reason in BARRED_MODULES.items():
        try:
            spec = importlib.util.find_spec(module)
        except (ImportError, ValueError):  # pragma: no cover - broken installs
            spec = None
        if spec is not None:
            findings.append(PackageFinding(module=module, reason=reason, origin=spec.origin))
    return findings
