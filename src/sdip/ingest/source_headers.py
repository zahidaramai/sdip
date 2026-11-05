"""Read only the trace-header columns a stage needs, block by block (``OPEN_DEBTS`` D76, P33).

``SegyFile(...).header[:]`` parses every trace header whole. At 240 bytes a trace that is
0.25 MB of memory per MB of source (probe P33 stage A), and ingest read it three times: for the
axis origin, and for the raw sample view's and the header plane's trace maps. Each of those
uses two to four columns. This reads only those, ``BLOCK`` traces at a time, through ``segy``'s
public ``header`` slicing (operating contract §3.3), and returns them as a structured array.
Every caller indexes it by field name, as it indexed the whole read. P33 measured the result
``array_equal`` to the whole read's columns, and the trace maps built from it identical.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any, Final

import numpy as np
from numpy.typing import NDArray

BLOCK: Final[int] = 65_536
"""Traces parsed per read. P33 measured 65,536 flat at about 135 MB of peak RSS."""


def read_header_columns(source: str | Path, segy_spec: Any, names: Iterable[str]) -> NDArray[Any]:
    """The named trace-header fields of every trace, as one structured array, read in blocks.

    A name the spec does not define is left out rather than invented, so a caller that asks
    for an optional field sees it absent, exactly as ``dtype.names`` showed it on a whole read.

    Args:
        source: The SEG-Y file.
        segy_spec: The ``SegySpec`` the ingest reads it with.
        names: Field names, in any order. Duplicates are read once.

    Returns:
        Shape ``(trace_count,)``, one field per name the spec defines, in the spec's dtypes.
    """
    from segy import SegyFile

    handle = SegyFile(str(Path(source)), spec=segy_spec)
    count = int(handle.num_traces)
    wanted = list(dict.fromkeys(names))
    block = handle.header[0 : min(BLOCK, count)]
    present = [n for n in wanted if n in (block.dtype.names or ())]
    out: NDArray[Any] = np.empty(count, dtype=[(n, block.dtype[n]) for n in present])
    for start in range(0, count, BLOCK):
        stop = min(start + BLOCK, count)
        if start:
            block = handle.header[start:stop]
        for name in present:
            out[name][start:stop] = np.asarray(block[name])
    return out
