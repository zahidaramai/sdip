"""Sources that a byte-identical round trip must reproduce, built for probe P19 (D71, D72).

Each starts from the well-formed 30-trace fixture and changes only what its name says, so a
round trip that fails on one has failed on exactly that property.

- :func:`make_unassigned_binary`: binary-header bytes 307-400, unassigned in revision 1,
  carry a seeded non-zero pattern (vendor data, in a real file). Upstream's exporter writes
  them back as zeros (D71).
- :func:`make_reversed_order`: the 30 trace records in reverse order. A valid file whose
  traces are not in grid order. Upstream's exporter writes grid order (D72).
- :func:`make_unassigned_and_reversed`: both at once.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

import numpy as np

from tests.fixtures.generators.poststack3d import make_poststack3d

SEED: Final[int] = 20261031
FILE_HEADERS: Final[int] = 3600
UNASSIGNED_FIRST: Final[int] = 307
"""First binary-header byte (1-based) the revision 1 standard leaves unassigned after 3506."""


def _base(path: Path) -> bytearray:
    return bytearray(make_poststack3d(path).path.read_bytes())


def _stride(payload: bytes) -> int:
    samples = int.from_bytes(payload[3220:3222], "big")
    return 240 + samples * 4


def _with_unassigned(payload: bytearray) -> None:
    count = 400 - UNASSIGNED_FIRST + 1
    pattern = np.random.default_rng(SEED).integers(1, 256, size=count, dtype=np.uint8)
    start = 3200 + UNASSIGNED_FIRST - 1
    payload[start : start + count] = pattern.tobytes()


def _reversed(payload: bytearray) -> None:
    stride = _stride(payload)
    count = (len(payload) - FILE_HEADERS) // stride
    records = [
        payload[FILE_HEADERS + i * stride : FILE_HEADERS + (i + 1) * stride] for i in range(count)
    ]
    payload[FILE_HEADERS:] = b"".join(reversed(records))


def make_unassigned_binary(path: str | Path) -> Path:
    """B1: non-zero bytes in the unassigned tail of the binary header."""
    target = Path(path)
    payload = _base(target)
    _with_unassigned(payload)
    target.write_bytes(bytes(payload))
    return target


def make_reversed_order(path: str | Path) -> Path:
    """B2: the trace records in reverse order."""
    target = Path(path)
    payload = _base(target)
    _reversed(payload)
    target.write_bytes(bytes(payload))
    return target


def make_unassigned_and_reversed(path: str | Path) -> Path:
    """B3: B1 and B2 together."""
    target = Path(path)
    payload = _base(target)
    _with_unassigned(payload)
    _reversed(payload)
    target.write_bytes(bytes(payload))
    return target
