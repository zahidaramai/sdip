"""MDIO to SEG-Y export and the round-trip driver.

**G3 passes only on ``sha256(export) == sha256(source)`` for the whole file.** A round
trip that compares parsed fields can pass while the bytes differ; this one cannot.
"""

from __future__ import annotations

from sdip.export.roundtrip import RoundTripResult, export

__all__ = ["RoundTripResult", "export"]
