r"""Intake QC of one ZGY file (Schlumberger/Petrel bricked post-stack format), headers only.

The layout is the one documented in OpenZGY (Apache-2.0, ``openzgy/impl/meta.py``): an
8-byte file header (``VBS\\0`` and a version), for versions 2-4 a 1-byte offset header, the
337-byte little-endian info header, a string list, a 2064-byte histogram header, the alpha
lookup table and the brick lookup table, then the bricks. This module is SDIP's own reader of
those headers (no code copied); OpenZGY's pure-Python reader is the test oracle.

What is checked: the version; size, brick size and data type; annotation origin and increment;
the four corner points (finite, non-degenerate); horizontal and vertical unit dimension (ZGY
records time or depth, unlike SEG-Y); the projection string (offered as a CRS candidate, never
taken); the brick lookup table of full resolution: missing, constant and compressed bricks,
and bricks that end past the end of the file (truncation).
"""

from __future__ import annotations

import math
import struct
from collections.abc import Callable
from pathlib import Path
from typing import Any, Final

from sdip.intake import report as rpt
from sdip.intake.segy import Outcome, Reader

TOOL: Final[str] = "sdip.intake.zgy"
HEADER_BUDGET: Final[int] = 1 << 20
MAGIC: Final[bytes] = b"VBS\x00"
OLD_COMPRESSED: Final[bytes] = b"VCS\x00"
INFO_FORMAT: Final[str] = "<3iB2f16s16s16sB3f3f3i3i3iqddff3f3fB2d2d4f4f4d4dBdBdI"
INFO_OFFSET: Final[int] = 9
HIST_BYTES: Final[int] = 2064
MAX_STRINGS: Final[int] = 1 << 16

DATATYPES: Final[dict[int, tuple[str, int]]] = {
    0: ("int8", 1),
    1: ("uint8", 1),
    2: ("int16", 2),
    3: ("uint16", 2),
    4: ("int32", 4),
    5: ("uint32", 4),
    6: ("float32", 4),
    7: ("IBM float32", 4),
}
WIDELY_READ: Final[frozenset[int]] = frozenset({0, 2, 6})
"""The data types the public ZGY library reads; the others are legal but rarely readable."""
VERTICAL: Final[dict[int, str]] = {0: "unknown", 1: "depth", 2: "time (TWT)", 3: "time (OWT)"}
HORIZONTAL: Final[dict[int, str]] = {0: "unknown", 1: "length", 2: "arc angle"}
CODE_SHIFT: Final[int] = 56
CONSTANT: Final[int] = 0x80
COMPRESSED: Final[int] = 0xC0

FIELDS: Final[tuple[tuple[str, int], ...]] = (
    ("bricksize", 3),
    ("datatype", 1),
    ("codingrange", 2),
    ("dataid", 1),
    ("verid", 1),
    ("previd", 1),
    ("srctype", 1),
    ("orig", 3),
    ("inc", 3),
    ("size", 3),
    ("curorig", 3),
    ("cursize", 3),
    ("scnt", 1),
    ("ssum", 1),
    ("sssq", 1),
    ("smin", 1),
    ("smax", 1),
    ("srvorig", 3),
    ("srvsize", 3),
    ("gdef", 1),
    ("gazim", 2),
    ("gbinsz", 2),
    ("gpiline", 4),
    ("gpxline", 4),
    ("gpx", 4),
    ("gpy", 4),
    ("hdim", 1),
    ("hunitfactor", 1),
    ("vdim", 1),
    ("vunitfactor", 1),
    ("slbufsize", 1),
)


def is_zgy(head: bytes) -> bool:
    """The content test: the uncompressed or the old compressed magic."""
    return head[:4] in (MAGIC, OLD_COMPRESSED)


def parse_info(blob: bytes) -> dict[str, Any]:
    """The info header as a name -> value (tuple for arrays) mapping."""
    values = struct.unpack(INFO_FORMAT, blob)
    out: dict[str, Any] = {}
    i = 0
    for name, n in FIELDS:
        out[name] = values[i] if n == 1 else tuple(values[i : i + n])
        i += n
    return out


def lod_sizes(
    size: tuple[int, int, int], brick: tuple[int, int, int]
) -> list[tuple[int, int, int]]:
    """Bricks per dimension at every level of detail, full resolution first."""
    cur = tuple((s + b - 1) // b for s, b in zip(size, brick, strict=True))
    out = [cur]
    while max(cur) > 1:
        cur = tuple((c + 1) // 2 for c in cur)
        out.append(cur)
    return out  # type: ignore[return-value]


def lut_offsets(lods: list[tuple[int, int, int]], alpha: bool) -> list[int]:
    """Entry offset of each level in a lookup table, then the table's length (coarsest first)."""
    result, pos = [], 0
    for e in reversed(lods):
        result.append(pos)
        pos += e[0] * e[1] * (1 if alpha else e[2])
    result.reverse()
    return [*result, pos]


def qc_zgy(
    path: str | Path,
    *,
    upload_id: str,
    member: str,
    sha256: str,
    cls: str = rpt.DEFAULT_CLASS,
    commit: str | None = None,
) -> Outcome:
    """Header-only intake QC of one file believed to be ZGY. Never raises on file content."""
    path = Path(path)
    size = path.stat().st_size
    reader = Reader(path, size)
    findings: list[dict[str, Any]] = []
    questions: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    detail: dict[str, Any] = {"member": member, "class": cls, "kind": "zgy"}
    commit = commit or rpt.reader_commit()
    structural: dict[str, Any] = {
        "format": "zgy",
        "version": None,
        "counts": counts,
        "hasCrs": None,
        "hasUnits": None,
        "hasNulls": None,
        "domain": "unknown",
    }
    detect: dict[str, Any] = {"format": "zgy", "by": f"{TOOL}@{commit[:12]}"}

    def done() -> Outcome:
        rep = rpt.reader_report(
            upload_id=upload_id,
            member=member,
            sha256=sha256,
            nbytes=size,
            cls=cls,
            detect=detect,
            tool=TOOL,
            commit=commit,
            structural=structural,
            findings=findings,
            questions=questions,
            header_bytes_read=reader.bytes_read,
            header_budget=HEADER_BUDGET,
        )
        return Outcome(rep, detail)

    head = reader.read(0, 8)
    if len(head) < 8 or not is_zgy(head):
        detect["format"] = structural["format"] = "unknown"
        findings.append(
            rpt.finding(
                "UNSUPPORTED_FORMAT", "refuse", "not ZGY: no VBS or VCS magic in the first 4 bytes"
            )
        )
        return done()
    version = struct.unpack_from("<I", head, 4)[0]
    structural["version"] = str(version)
    detect["version"] = str(version)
    detect["evidence"] = f"magic {head[:3].decode()} version {version}"
    if cls == "cluster-derived":
        findings.append(
            rpt.finding(
                "CLUSTER_RAW_REFUSED",
                "refuse",
                "raw cluster seismic: the upload is classed cluster-derived; the upload is "
                "deleted and only its hash and size are kept",
            )
        )
        return done()
    suffix = Path(member).suffix.lower()
    if suffix and suffix != ".zgy":
        detect["contradiction"] = f"extension {suffix} names another format; content is ZGY"
        findings.append(
            rpt.finding(
                "EXTENSION_CONTRADICTION",
                "info",
                f"the extension {suffix} is not .zgy; the content decides",
            )
        )
    if head[:4] == OLD_COMPRESSED or not 2 <= version <= 4:
        findings.append(
            rpt.finding(
                "SDIP_ZGY_VERSION_UNSUPPORTED",
                "quarantine",
                "old compressed ZGY (VCS)"
                if head[:4] == OLD_COMPRESSED
                else f"ZGY version {version}: this reader reads versions 2 to 4 (version 1 "
                "predates 2010)",
            )
        )
        return done()

    blob = reader.read(INFO_OFFSET, struct.calcsize(INFO_FORMAT))
    if len(blob) < struct.calcsize(INFO_FORMAT):
        findings.append(
            rpt.finding("TRUNCATED", "quarantine", "the file ends inside the ZGY info header")
        )
        return done()
    info = parse_info(blob)
    nil, nxl, nz = info["size"]
    bricksize = info["bricksize"]
    dtype = info["datatype"]
    detail["info"] = info
    if (
        min(info["size"]) <= 0
        or min(bricksize) <= 0
        or max(bricksize) > 1024
        or dtype not in DATATYPES
    ):
        findings.append(
            rpt.finding(
                "HEADER_INVALID",
                "quarantine",
                f"info header out of range: size {info['size']}, brick size {bricksize}, data "
                f"type {dtype}",
            )
        )
        return done()
    counts.update(inlines=nil, crosslines=nxl, samples=nz)
    name, width = DATATYPES[dtype]
    detail["datatype"] = name
    if dtype not in WIDELY_READ:
        findings.append(
            rpt.finding(
                "SDIP_ZGY_RARE_DATATYPE",
                "info",
                f"data type {name}: legal ZGY, but most ZGY readers read only int8, int16 and "
                "float32",
            )
        )
    if tuple(bricksize) != (64, 64, 64):
        findings.append(
            rpt.finding(
                "SDIP_ZGY_BRICKSIZE",
                "info",
                f"brick size {bricksize}; most readers expect 64x64x64",
            )
        )
    if not all(math.isfinite(v) for v in (*info["orig"], *info["inc"])) or 0 in info["inc"]:
        findings.append(
            rpt.finding(
                "HEADER_INVALID",
                "quarantine",
                f"annotation origin {info['orig']} or increment {info['inc']} is not finite "
                "or is zero",
            )
        )

    # Strings: source name, description, projection, horizontal and vertical unit names.
    nstr = info["slbufsize"]
    strings = ["", "", "", "", ""]
    if nstr > MAX_STRINGS:
        findings.append(
            rpt.finding(
                "HEADER_INVALID", "quarantine", f"string list of {nstr} bytes (limit {MAX_STRINGS})"
            )
        )
        return done()
    if nstr:
        raw = reader.read(INFO_OFFSET + len(blob), nstr)
        parts = raw.split(b"\x00")
        strings = [p.decode("ascii", errors="replace") for p in parts[:5]] + [""] * max(
            0, 5 - len(parts)
        )
    projection, hunit, vunit = strings[2].strip(), strings[3].strip(), strings[4].strip()
    detail["strings"] = {"projection": projection, "horizontal unit": hunit, "vertical unit": vunit}

    # Geometry
    corners = list(zip(info["gpx"], info["gpy"], strict=True))
    detail["corners"] = corners
    finite = all(math.isfinite(c) for xy in corners for c in xy)
    span = (
        max((abs(a[0] - b[0]) + abs(a[1] - b[1]) for a in corners for b in corners), default=0)
        if finite
        else 0
    )
    if not finite:
        findings.append(
            rpt.finding("HEADER_INVALID", "quarantine", "the corner coordinates are not finite")
        )
    elif span == 0:
        findings.append(
            rpt.finding(
                "SDIP_NO_COORDINATES",
                "info",
                "all four corner points coincide: the cube cannot be placed on a map",
            )
        )
    if finite and span:
        # OpenZGY treats four corners as three and derives the fourth; a stored fourth corner off
        # the parallelogram is placed differently by such readers (P37 run 1, Z2).
        c0, c1, c2, c3 = corners
        dx, dy = c3[0] - (c1[0] + c2[0] - c0[0]), c3[1] - (c1[1] + c2[1] - c0[1])
        off = math.hypot(dx, dy)
        detail["corner_off_parallelogram"] = off
        scale = max(abs(v) for xy in corners for v in xy)
        if off > 1e-9 * max(scale, 1.0):  # float64 holds ~1e-16 relative; 1e-9 is noise-free
            findings.append(
                rpt.finding(
                    "SDIP_ZGY_CORNER_NOT_PARALLELOGRAM",
                    "info",
                    f"the stored fourth corner lies {off:.3g} file units off the parallelogram "
                    "of the other three; readers that derive it (OpenZGY) place it there instead",
                )
            )
    if info["gdef"] not in (0, 2, 3):
        findings.append(
            rpt.finding(
                "SDIP_ZGY_GRID_DEFINITION",
                "info",
                f"grid definition {info['gdef']} (parametric or unknown); "
                "readers use corner points",
            )
        )
    findings.append(
        rpt.finding(
            "SDIP_GEOMETRY",
            "info",
            f"3d-poststack bricked cube {nil} x {nxl} x {nz}; inline {info['orig'][0]:g} step "
            f"{info['inc'][0]:g}, "
            f"crossline {info['orig'][1]:g} step {info['inc'][1]:g}, vertical start "
            f"{info['orig'][2]:g} step {info['inc'][2]:g}",
        )
    )
    structural["format"] = "zgy-3d-poststack"

    # Units and domain: ZGY states them; a stated value is reported, an unknown one asked.
    vdim, hdim = info["vdim"], info["hdim"]
    detail["units"] = {
        "horizontal": f"{HORIZONTAL.get(hdim, hdim)} {hunit} x{info['hunitfactor']:g}",
        "vertical": f"{VERTICAL.get(vdim, vdim)} {vunit} x{info['vunitfactor']:g}",
    }
    structural["hasUnits"] = hdim in (1, 2) and vdim in (1, 2, 3)
    structural["domain"] = {1: "depth", 2: "time", 3: "time"}.get(vdim, "unknown")
    if vdim not in (1, 2, 3):
        questions.append(
            rpt.question(
                "DOMAIN_UNKNOWN",
                "The ZGY file does not record its vertical domain. Is it time or depth?",
                [
                    {"id": "twt", "label": "time, two-way (TWT)"},
                    {"id": "owt", "label": "time, one-way (OWT)"},
                    {"id": "depth", "label": "depth"},
                ],
                subject="vertical axis",
            )
        )
    if span and hdim not in (1, 2):
        questions.append(
            rpt.question(
                "UNITS_AMBIGUOUS",
                "The ZGY file does not state the unit of its corner coordinates. Which is it?",
                [{"id": "m", "label": "metres"}, {"id": "ft", "label": "feet"}],
                subject="corner coordinates",
            )
        )
    structural["hasCrs"] = bool(projection)
    if span:
        choices = (
            [{"id": "cand0", "label": projection[:200], "source": "ZGY projection string"}]
            if projection
            else []
        )
        choices += [
            {"id": "epsg", "label": "Enter an EPSG code"},
            {"id": "unknown", "label": "I don't know"},
        ]
        questions.append(
            rpt.question(
                "CRS_UNRESOLVED",
                "Which coordinate reference system are the corner points in? "
                + (
                    "The file carries a free-text projection, which ZGY does not standardise."
                    if projection
                    else "The file names none."
                ),
                choices,
                subject="corner coordinates",
            )
        )

    # Lookup tables: where the bricks of full resolution are, and whether the file holds them.
    lods = lod_sizes((nil, nxl, nz), tuple(bricksize))
    alpha = lut_offsets(lods, True)
    bricks = lut_offsets(lods, False)
    counts["lods"] = len(lods)
    lut_start = INFO_OFFSET + len(blob) + nstr + HIST_BYTES + 8 * alpha[-1]
    lut_bytes = 8 * bricks[-1]
    if lut_start + lut_bytes > size:
        findings.append(
            rpt.finding(
                "TRUNCATED",
                "quarantine",
                f"the brick lookup table should end at byte {lut_start + lut_bytes} of a "
                f"{size}-byte file",
            )
        )
        return done()
    if reader.bytes_read + lut_bytes > HEADER_BUDGET:
        findings.append(
            rpt.finding(
                "HEADER_BUDGET",
                "info",
                f"the brick lookup table ({lut_bytes} bytes) exceeds the header budget; "
                "brick presence and truncation were not checked",
            )
        )
        return _route(done, findings)
    lut = struct.unpack(
        f"<{bricks[-1]}Q", reader.read(lut_start, lut_bytes)
    )  # coarsest level first
    full = list(lut[bricks[0] : bricks[-1]])  # plain little-endian from version 2 on
    brick_bytes = bricksize[0] * bricksize[1] * bricksize[2] * width

    def beyond(v: int) -> bool:
        """An entry whose brick starts or ends past the end of the file."""
        code = v >> CODE_SHIFT
        if v == 0 or code == CONSTANT:
            return False
        if code == COMPRESSED:
            return (v & ((1 << CODE_SHIFT) - 1)) >= size
        return bool(code) or v + brick_bytes > size

    # Every level: OpenZGY writes the lower-resolution bricks after full resolution, so a
    # cut tail lands in a level the full-resolution check never sees (P37 run 1, Z5).
    past_eof = sum(beyond(v) for v in lut)
    missing = sum(v == 0 for v in full)
    constant = sum(v >> CODE_SHIFT == CONSTANT for v in full)
    compressed = sum(v >> CODE_SHIFT == COMPRESSED for v in full)
    counts.update(
        bricks=len(full),
        missing_bricks=missing,
        constant_bricks=constant,
        compressed_bricks=compressed,
    )
    detail["bricks"] = {
        "total": len(full),
        "missing": missing,
        "constant": constant,
        "compressed": compressed,
        "past end of file": past_eof,
    }
    if past_eof:
        findings.append(
            rpt.finding(
                "TRUNCATED",
                "quarantine",
                f"{past_eof} of {len(lut)} bricks (all levels) start or end past the end "
                "of the file",
            )
        )
    if missing:
        findings.append(
            rpt.finding(
                "SDIP_ZGY_MISSING_BRICKS",
                "info",
                f"{missing} of {len(full)} full-resolution bricks were never written (read as "
                "the default value)",
            )
        )
    if compressed:
        findings.append(
            rpt.finding(
                "SDIP_ZGY_LOSSY_COMPRESSION",
                "info",
                f"{compressed} of {len(full)} bricks are ZFP-compressed: the samples are a lossy "
                "approximation of the original, and reading them needs zfp",
            )
        )
    return _route(done, findings)


def _route(done: Callable[[], Outcome], findings: list[dict[str, Any]]) -> Outcome:
    findings.append(
        rpt.finding(
            "SDIP_NO_MDIO_ROUTE",
            "info",
            "SDIP ingests SEG-Y only: export the cube to SEG-Y with a ZGY reader, then sdip "
            "ingest; "
            "the equivalence proof then covers that SEG-Y, not the ZGY",
        )
    )
    return done()
