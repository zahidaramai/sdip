"""P37 generator: an F3 sub-cube as ZGY, written with OpenZGY's writer, and two corrupted copies.

Run OUTSIDE SDIP's environment, with OpenZGY (from the ``pyzgy`` 0.1.1 sdist, Apache-2.0) and
numpy on the path::

    python -I prereg/P37_make_zgy.py PYZGY_SRC F3_SEGY OUT_DIR

Reads F3's samples directly (revision 0, IEEE float32 big-endian, 462 samples, inline-major
with 951 crosslines per inline: measured by P36), inlines 100-299 x crosslines 300-599
(field-ok: public F3 survey index ranges). Writes ``f3_sub.zgy``, ``f3_sub_cut.zgy`` (last
1,000 bytes removed) and ``f3_sub_hole.zgy`` (the first full-resolution brick's lookup entry
zeroed), plus ``f3_sub.oracle.json`` with what OpenZGY reads back.

The projection text is set through the writer's metadata object (OpenZGY's public writer has no
argument for it); OpenZGY then writes it into the string list, and its reader reads it back.
"""

from __future__ import annotations

import json
import struct
import sys
from pathlib import Path

NS, NXL, IL0, XL0 = 462, 951, 100, 300
IL_N, XL_N = 200, 300
PROJECTION = "ED50 / UTM zone 31N (from the F3 textual header: UTM ZONE 31, ED50)"


def main(src: str, segy: str, out_dir: str) -> None:
    """Write the sub-cube and its copies."""
    sys.path.insert(0, src)
    import numpy as np
    from openzgy.api import SampleDataType, UnitDimension, ZgyReader, ZgyWriter

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    rec = np.dtype([("h", "V240"), ("s", ">f4", (NS,))])
    traces = np.memmap(segy, dtype=rec, mode="r", offset=3600)
    heads = np.memmap(segy, dtype=np.uint8, mode="r", offset=3600).reshape(-1, 240 + 4 * NS)

    def xy(il: int, xl: int) -> tuple[float, float]:
        h = bytes(heads[(il - 100) * NXL + (xl - 300)][:240])
        scalar = struct.unpack(">h", h[70:72])[0]
        f = 1 / -scalar if scalar < 0 else (scalar or 1)
        return struct.unpack(">i", h[180:184])[0] * f, struct.unpack(">i", h[184:188])[0] * f

    cube = np.empty((IL_N, XL_N, NS), dtype=np.float32)
    for k in range(IL_N):
        first = (IL0 - 100 + k) * NXL + (XL0 - 300)
        cube[k] = traces["s"][first : first + XL_N]
    corners = (
        xy(IL0, XL0),
        xy(IL0 + IL_N - 1, XL0),
        xy(IL0, XL0 + XL_N - 1),
        xy(IL0 + IL_N - 1, XL0 + XL_N - 1),
    )
    path = out / "f3_sub.zgy"
    with ZgyWriter(
        str(path),
        size=(IL_N, XL_N, NS),
        datatype=SampleDataType.float,
        zunitdim=UnitDimension.time,
        zunitname="ms",
        zunitfactor=0.001,
        zstart=0.0,
        zinc=4.0,
        hunitdim=UnitDimension.length,
        hunitname="m",
        hunitfactor=1.0,
        annotstart=(IL0, XL0),
        annotinc=(1, 1),
        corners=corners,
    ) as w:
        w._meta._ih._hprjsys = PROJECTION  # noqa: SLF001 - no public writer argument for it
        w.write((0, 0, 0), cube)
        w.finalize()
    with ZgyReader(str(path)) as r:
        oracle = {
            "size": list(r.size),
            "annotstart": list(r.annotstart),
            "annotinc": list(r.annotinc),
            "zstart": r.zstart,
            "zinc": r.zinc,
            "corners": [list(c) for c in r.corners],
            "datatype": str(r.datatype),
            "zunitdim": str(r.zunitdim),
            "hunitdim": str(r.hunitdim),
            "projection": r.meta.get("hprjsys") if hasattr(r, "meta") else None,
        }
    (out / "f3_sub.oracle.json").write_text(json.dumps(oracle, indent=1))
    data = path.read_bytes()
    (out / "f3_sub_cut.zgy").write_bytes(data[:-1000])
    # zero the first full-resolution brick entry
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from sdip.intake.zgy import (
        HIST_BYTES,
        INFO_FORMAT,
        INFO_OFFSET,
        lod_sizes,
        lut_offsets,
        parse_info,
    )

    info = parse_info(data[INFO_OFFSET : INFO_OFFSET + struct.calcsize(INFO_FORMAT)])
    lods = lod_sizes(info["size"], info["bricksize"])
    start = (
        INFO_OFFSET
        + struct.calcsize(INFO_FORMAT)
        + info["slbufsize"]
        + HIST_BYTES
        + 8 * lut_offsets(lods, True)[-1]
        + 8 * lut_offsets(lods, False)[0]
    )
    hole = bytearray(data)
    hole[start : start + 8] = bytes(8)
    (out / "f3_sub_hole.zgy").write_bytes(bytes(hole))
    print(json.dumps(oracle))


if __name__ == "__main__":
    main(*sys.argv[1:4])
