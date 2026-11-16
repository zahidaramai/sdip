"""Intake QC of one SEG-Y file, from its headers only, into a ``geosuite.intake.v1`` report.

What a seismic interpreter checks before trusting a SEG-Y, read without touching a sample:

- the textual header's encoding (EBCDIC or ASCII) and what it says about CRS and domain;
- the byte order, revision, sample format, sample interval and samples per trace;
- whether the file size is a whole number of traces of that length (truncation);
- trace-header geometry from a bounded sample of trace headers: 3D post-stack (inline and
  crossline vary, one trace per cell), 2D post-stack (CDP varies along one line) or pre-stack
  (several traces per cell or per shot, offsets varying);
- coordinate scalars (legal, constant), coordinate units, measurement system;
- inline/crossline ranges and the grid they imply;
- the route into an MDIO store through ``sdip ingest`` and whether the preflight admits it.

**Header budget.** The file is never read whole: 3600 bytes of file header, the extended
textual headers the binary header declares, and at most :data:`MAX_SAMPLED_TRACES` trace
headers of 240 bytes at computed offsets. Every read is counted in ``headerBytesRead``.

**Never inferred.** CRS and vertical domain are asked of the user (``CRS_UNRESOLVED``,
``DOMAIN_UNKNOWN``); words found in the textual header are offered as candidates with their
source, never chosen. Ranges, names and coordinates go in user-side messages and the QC card,
never in the ``structural`` block a model may see.
"""

from __future__ import annotations

import itertools
import math
import re
import struct
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

from sdip.intake import report as rpt

TOOL: Final[str] = "sdip.intake.segy"
HEADER_BUDGET: Final[int] = 1 << 20
"""1 MiB: file header, up to 64 extended textual headers and the sampled trace headers."""

MAX_SAMPLED_TRACES: Final[int] = 2000
CONSECUTIVE_TRACES: Final[int] = 500
"""The first traces are read in a run: gathers show themselves only in consecutive traces."""
MAX_EXTENDED_HEADERS_READ: Final[int] = 64

SEGY_SUFFIXES: Final[frozenset[str]] = frozenset({".sgy", ".segy", ".seg"})
SEGY_LIBRARY: Final[dict[str, str]] = {"name": "segy", "version": "0.6.0", "licence": "Apache-2.0"}

BYTES_PER_SAMPLE: Final[dict[int, int]] = {
    1: 4,
    2: 4,
    3: 2,
    5: 4,
    6: 8,
    8: 1,
    9: 8,
    10: 4,
    11: 2,
    12: 8,
    15: 3,
    16: 1,
}
"""SEG-Y rev 2.1 sample-format codes. The ingest route checks the pinned ``segy`` enum itself."""
FORMAT_NAMES: Final[dict[int, str]] = {
    1: "IBM float32",
    2: "int32",
    3: "int16",
    5: "IEEE float32",
    6: "IEEE float64",
    8: "int8",
    9: "int64",
    10: "uint32",
    11: "uint16",
    12: "uint64",
    15: "uint24",
    16: "uint8",
}
VALID_SCALARS: Final[frozenset[int]] = frozenset({1, 10, 100, 1000, 10000})
COORD_UNITS: Final[dict[int, str]] = {1: "length", 2: "arc seconds", 3: "decimal degrees", 4: "DMS"}
REV2_BYTE_ORDER_CONSTANT: Final[int] = 0x01020304

# trace-header fields: name -> (0-based offset, struct code)
TRACE_FIELDS: Final[dict[str, tuple[int, str]]] = {
    "ffid": (8, "i"),
    "channel": (12, "i"),
    "cdp": (20, "i"),
    "trace_id": (28, "h"),
    "offset": (36, "i"),
    "scalar": (70, "h"),
    "src_x": (72, "i"),
    "src_y": (76, "i"),
    "grp_x": (80, "i"),
    "grp_y": (84, "i"),
    "coord_units": (88, "h"),
    "ns": (114, "H"),
    "dt": (116, "H"),
    "cdp_x": (180, "i"),
    "cdp_y": (184, "i"),
    "inline": (188, "i"),
    "crossline": (192, "i"),
}

CRS_PATTERNS: Final[tuple[tuple[str, str], ...]] = (
    (r"EPSG\s*[:#]?\s*(\d{4,5})", "EPSG:{0}"),
    (r"UTM\s*(?:ZONE)?\s*[:=]?\s*(\d{1,2})\s*([NS])?\b", "UTM zone {0}{1}"),
    (r"\b(ED\s?50|ED\s?1950|WGS\s?-?84|WGS\s?1984|NAD\s?27|NAD\s?83|ETRS\s?89|GDA\s?94)\b", "{0}"),
)
TIME_WORDS: Final[frozenset[str]] = frozenset({"TIME", "TWT", "MS", "MSEC", "MILLISECONDS"})
DEPTH_WORDS: Final[frozenset[str]] = frozenset({"DEPTH", "TVD", "TVDSS", "PSDM"})


@dataclass(slots=True)
class Reader:
    """Counts every byte read so the report can state it."""

    path: Path
    size: int
    bytes_read: int = 0

    def read(self, offset: int, length: int) -> bytes:
        """``length`` bytes at ``offset``, counted."""
        with self.path.open("rb") as handle:
            handle.seek(offset)
            blob = handle.read(length)
        self.bytes_read += len(blob)
        return blob


@dataclass(slots=True)
class Binary:
    """The binary-header fields intake QC uses, in the byte order that made them coherent."""

    order: str
    interval: int
    samples: int
    fmt: int
    fold: int
    sorting: int
    measurement: int
    revision: str
    fixed_length: int
    extended: int
    rev2_constant: bool

    @property
    def bytes_per_trace(self) -> int:
        """Trace header plus samples."""
        return 240 + self.samples * BYTES_PER_SAMPLE[self.fmt]


@dataclass(slots=True)
class Sample:
    """The sampled trace headers and what they show."""

    headers: list[dict[str, int]] = field(default_factory=list)
    indices: list[int] = field(default_factory=list)


def _printable(text: str) -> float:
    return sum(ch.isprintable() or ch in "\r\n" for ch in text) / max(len(text), 1)


def decode_textual(blob: bytes) -> tuple[str, str, float]:
    """(text, encoding, printable fraction): EBCDIC cp037 or ASCII, whichever reads cleaner."""
    ebcdic = blob.decode("cp037", errors="replace")
    ascii_ = blob.decode("latin-1", errors="replace")
    fe, fa = _printable(ebcdic), _printable(ascii_)
    # ASCII text decoded as cp037 is mostly printable too; prefer the one whose cards start "C".
    cards_e = sum(ebcdic[i] == "C" for i in range(0, len(ebcdic), 80))
    cards_a = sum(ascii_[i] == "C" for i in range(0, len(ascii_), 80))
    if (cards_a, fa) > (cards_e, fe):
        return ascii_, "ascii", fa
    return ebcdic, "ebcdic", fe


def _binary(blob: bytes, order: str) -> Binary:
    p = ">" if order == "big" else "<"

    def h(off: int) -> int:
        return int(struct.unpack_from(f"{p}h", blob, off)[0])

    raw_rev = struct.unpack_from(f"{p}H", blob, 300)[0]
    major, minor = raw_rev >> 8, raw_rev & 0xFF
    revision = f"{major}.{minor}" if raw_rev else "0"
    constant = struct.unpack_from(f"{p}I", blob, 96)[0]
    return Binary(
        order=order,
        interval=h(16),
        samples=struct.unpack_from(f"{p}H", blob, 20)[0],
        fmt=h(24),
        fold=h(26),
        sorting=h(28),
        measurement=h(54),
        revision=revision,
        fixed_length=h(302),
        extended=h(304),
        rev2_constant=constant == REV2_BYTE_ORDER_CONSTANT,
    )


def _coherent(b: Binary, size: int) -> bool:
    return (
        b.fmt in BYTES_PER_SAMPLE
        and b.samples > 0
        and b.interval > 0
        and size >= 3600 + b.bytes_per_trace
    )


def resolve_binary(blob: bytes, size: int) -> Binary | None:
    """The byte order in which the binary header is coherent; big first, as the standard says."""
    for order in ("big", "little"):
        b = _binary(blob, order)
        if b.rev2_constant or _coherent(b, size):
            return b
    return None


def _trace_header(blob: bytes, order: str) -> dict[str, int]:
    p = ">" if order == "big" else "<"
    return {
        name: int(struct.unpack_from(p + code, blob, off)[0])
        for name, (off, code) in TRACE_FIELDS.items()
    }


def sample_traces(reader: Reader, data_offset: int, bpt: int, traces: int, order: str) -> Sample:
    """The first :data:`CONSECUTIVE_TRACES` in a run, then evenly spaced headers to the last."""
    run = min(traces, CONSECUTIVE_TRACES)
    rest = min(traces - run, MAX_SAMPLED_TRACES - run)
    idx = list(range(run))
    if rest > 0:
        step = (traces - 1 - run) / max(rest - 1, 1)
        idx += sorted({run + round(k * step) for k in range(rest)} | {traces - 1})
    out = Sample()
    for i in idx:
        blob = reader.read(data_offset + i * bpt, 240)
        if len(blob) < 240:
            break
        out.headers.append(_trace_header(blob, order))
        out.indices.append(i)
    return out


def _distinct(values: list[int]) -> list[int]:
    return sorted(set(values))


def _step(values: list[int]) -> int:
    d = _distinct(values)
    g = 0
    for a, b in itertools.pairwise(d):
        g = math.gcd(g, b - a)
    return g or 1


@dataclass(slots=True)
class Geometry:
    """What the sampled trace headers show about the acquisition and stacking geometry."""

    kind: str
    """``3d-poststack``, ``2d-poststack``, ``3d-prestack``, ``2d-prestack`` or ``unknown``."""
    gather: str | None
    """``shot`` or ``cdp`` for pre-stack."""
    evidence: str
    il: tuple[int, int, int, int] | None = None
    """(min, max, step, count) when inlines vary."""
    xl: tuple[int, int, int, int] | None = None
    cdp: tuple[int, int] | None = None


def classify_geometry(sample: Sample, b: Binary) -> Geometry:
    """Geometry from the sampled headers at the standard byte locations (rev 1 and 2)."""
    hs = sample.headers
    run = hs[:CONSECUTIVE_TRACES]
    il = [h["inline"] for h in hs]
    xl = [h["crossline"] for h in hs]
    cdp = [h["cdp"] for h in hs]
    il_vary, xl_vary = len(set(il)) > 1, len(set(xl)) > 1
    # A grid, not two counters: each varying index must also repeat across the other. A 2D
    # line that copies FFID and CDP into bytes 189 and 193 has both varying and neither
    # repeating (measured on a Volve ST0299 line).
    three_d = (
        il_vary and xl_vary and max(Counter(il).values()) > 1 and max(Counter(xl).values()) > 1
    )

    offsets_vary = len({h["offset"] for h in run}) > 1
    cells = Counter((h["inline"], h["crossline"]) if three_d else h["cdp"] for h in run)
    cell_repeats = sum(c > 1 for c in cells.values())
    shots = Counter(h["ffid"] for h in run)
    shot_repeats = len(run) > 1 and max(shots.values()) > 1 and len({h["channel"] for h in run}) > 1

    def rng(v: list[int]) -> tuple[int, int, int, int]:
        s = _step(v)
        return (min(v), max(v), s, (max(v) - min(v)) // s + 1)

    geo_il = rng(il) if il_vary else None
    geo_xl = rng(xl) if xl_vary else None
    geo_cdp = (min(cdp), max(cdp)) if len(set(cdp)) > 1 else None

    # Pre-stack means several traces per cell, at different offsets. FFID and channel alone
    # are not evidence: a stack may keep them from its nearest trace.
    if offsets_vary and cell_repeats:
        gather = "shot" if shot_repeats else "cdp"
        kind = "3d-prestack" if three_d else "2d-prestack"
        ev = (
            f"in the first {len(run)} traces offsets vary and "
            + f"{cell_repeats} cells repeat"
            + (
                f" (shot records over {len({h['channel'] for h in run})} channels)"
                if gather == "shot"
                else ""
            )
        )
        return Geometry(kind, gather, ev, geo_il, geo_xl, geo_cdp)
    if three_d and not cell_repeats:
        ev = (
            f"inline and crossline both vary over {len(hs)} sampled headers; "
            f"no cell repeats in the first {len(run)}"
        )
        return Geometry("3d-poststack", None, ev, geo_il, geo_xl, geo_cdp)
    if not three_d and geo_cdp and not cell_repeats:
        ev = "CDP varies along one line; inline and crossline do not both vary"
        return Geometry("2d-poststack", None, ev, geo_il, geo_xl, geo_cdp)
    ev = (
        "the standard byte locations (inline 189, crossline 193, CDP 21, offset 37) "
        "do not identify the geometry"
    )
    return Geometry("unknown", None, ev, geo_il, geo_xl, geo_cdp)


def _crs_candidates(text: str) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    upper = text.upper()
    for pattern, label in CRS_PATTERNS:
        for m in re.finditer(pattern, upper):
            line = upper.count("\n", 0, m.start()) + 1
            groups = [g or "" for g in m.groups()]
            cand = label.format(*groups).strip()
            if cand not in [c for c, _ in found]:
                found.append((cand, f"SEG-Y textual header, card C{line:02d}"))
    return found[:8]


def _domain_words(text: str) -> tuple[bool, bool]:
    words = set(re.findall(r"[A-Z]+", text.upper()))
    return bool(words & TIME_WORDS), bool(words & DEPTH_WORDS)


def _cards(text: str) -> str:
    if "\n" in text:
        return text
    return "\n".join(text[i : i + 80] for i in range(0, len(text), 80))


def _template(geo: Geometry, domain: str) -> str | None:
    d = "Time" if domain == "time" else "Depth"
    return {
        "3d-poststack": f"PostStack3D{d}",
        "2d-poststack": f"PostStack2D{d}",
        "3d-prestack": f"CdpOffsetGathers3D{d}" if geo.gather == "cdp" else "StreamerShotGathers3D",
        "2d-prestack": f"CdpOffsetGathers2D{d}" if geo.gather == "cdp" else "StreamerShotGathers2D",
    }.get(geo.kind)


@dataclass(slots=True)
class Outcome:
    """The report plus the user-side detail the QC card draws."""

    report: dict[str, Any]
    detail: dict[str, Any]


def qc_segy(
    path: str | Path,
    *,
    upload_id: str,
    member: str,
    sha256: str,
    cls: str = rpt.DEFAULT_CLASS,
    cluster_markers: tuple[str, ...] = (),
    commit: str | None = None,
) -> Outcome:
    """Header-only intake QC of one file believed to be SEG-Y. Never raises on file content."""
    path = Path(path)
    size = path.stat().st_size
    reader = Reader(path, size)
    findings: list[dict[str, Any]] = []
    questions: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    detail: dict[str, Any] = {"member": member, "class": cls}
    commit = commit or rpt.reader_commit()
    structural: dict[str, Any] = {
        "format": "segy",
        "version": None,
        "counts": counts,
        "hasCrs": None,
        "hasUnits": None,
        "hasNulls": None,
        "domain": "unknown",
    }
    detect: dict[str, Any] = {"format": "segy", "by": f"{TOOL}@{commit[:12]}"}

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
            library=SEGY_LIBRARY,
        )
        return Outcome(rep, detail)

    head = reader.read(0, 3600)
    if len(head) < 3600:
        detect["format"] = "unknown"
        structural["format"] = "unknown"
        findings.append(
            rpt.finding(
                "UNSUPPORTED_FORMAT",
                "refuse",
                f"{size} bytes: shorter than a SEG-Y file header (3600 bytes)",
            )
        )
        return done()

    text, encoding, printable = decode_textual(head[:3200])
    text = _cards(text)
    detail["textual"] = text
    binary = resolve_binary(head[3200:], size)
    if printable < 0.75 and binary is None:
        detect["format"] = "unknown"
        structural["format"] = "unknown"
        findings.append(
            rpt.finding(
                "UNSUPPORTED_FORMAT",
                "refuse",
                f"not SEG-Y: the first 3200 bytes are {printable:.0%} printable in either encoding "
                "and the binary header is coherent in neither byte order",
            )
        )
        return done()
    detect["evidence"] = f"{encoding} textual header ({printable:.0%} printable)" + (
        "; binary header coherent" if binary else "; binary header incoherent"
    )

    suffix = Path(member).suffix.lower()
    if suffix and suffix not in SEGY_SUFFIXES:
        detect["contradiction"] = f"extension {suffix} names another format; content is SEG-Y"
        findings.append(
            rpt.finding(
                "EXTENSION_CONTRADICTION",
                "info",
                f"the extension {suffix} is not a SEG-Y extension; the content decides",
            )
        )
    elif not suffix:
        findings.append(
            rpt.finding("SDIP_NO_EXTENSION", "info", "no extension; detected as SEG-Y by content")
        )

    # Raw cluster seismic: refused before anything else is read; the custodian deletes it.
    words = set(re.findall(r"[A-Z]+", text.upper()))
    hit = next((m for m in cluster_markers if m.upper() in words), None)
    if cls == "cluster-derived" or hit:
        why = (
            "the textual header names a cluster survey"
            if hit
            else "the upload is classed cluster-derived"
        )
        findings.append(
            rpt.finding(
                "CLUSTER_RAW_REFUSED",
                "refuse",
                f"raw cluster seismic: {why}; the upload is deleted and only its hash "
                "and size are kept",
            )
        )
        detail.pop("textual", None)
        return done()

    if binary is None:
        findings.append(
            rpt.finding(
                "HEADER_INVALID",
                "quarantine",
                "the binary header is coherent in neither byte order (sample format, "
                "samples per trace or interval out of range)",
            )
        )
        return done()

    structural["version"] = binary.revision
    detail["binary"] = {
        "byte order": binary.order,
        "revision": binary.revision,
        "format": f"{binary.fmt} ({FORMAT_NAMES.get(binary.fmt, '?')})",
        "interval": binary.interval,
        "samples": binary.samples,
        "extended headers": binary.extended,
        "measurement": binary.measurement,
        "sorting": binary.sorting,
        "fold": binary.fold,
    }
    counts.update(
        samples=binary.samples, sample_interval_us=binary.interval, sample_format_code=binary.fmt
    )
    if binary.order == "little":
        findings.append(
            rpt.finding(
                "SDIP_LITTLE_ENDIAN",
                "info",
                "little-endian SEG-Y"
                + (
                    " (rev 2 byte-order constant present)"
                    if binary.rev2_constant
                    else " (coherent only read little-endian)"
                )
                + '; ingest needs endianness = "little" in a survey override',
            )
        )
    if binary.fmt == 1:
        findings.append(
            rpt.finding(
                "SDIP_IBM_FLOAT",
                "info",
                "IBM float32 samples; SDIP keeps the raw IBM words beside the decoded values",
            )
        )

    extended = binary.extended
    if extended < 0:
        findings.append(
            rpt.finding(
                "SDIP_VARIABLE_EXT_HEADERS",
                "quarantine",
                "variable number of extended textual headers (-1); the first trace cannot be "
                "located by count and SDIP does not guess an offset",
            )
        )
        return done()
    if extended > MAX_EXTENDED_HEADERS_READ or 3600 + extended * 3200 >= size:
        findings.append(
            rpt.finding(
                "HEADER_INVALID",
                "quarantine",
                f"binary header declares {extended} extended textual headers, which this "
                f"{size}-byte file cannot hold with any trace",
            )
        )
        return done()
    if extended:
        ext = reader.read(3600, extended * 3200)
        detail["textual"] += "\n" + _cards(decode_textual(ext)[0])
        counts["extended_headers"] = extended

    data_offset = 3600 + extended * 3200
    bpt = binary.bytes_per_trace
    body = size - data_offset
    traces, rem = divmod(body, bpt)
    counts["traces"] = traces
    if traces == 0:
        findings.append(
            rpt.finding(
                "TRUNCATED",
                "quarantine",
                f"the headers declare {bpt}-byte traces and the file holds no complete trace",
            )
        )
        return done()
    if rem:
        code = "TRUNCATED" if binary.fixed_length else "SIZE_INCONSISTENT"
        findings.append(
            rpt.finding(
                code,
                "quarantine",
                f"{body} bytes of trace data are not a whole number of {bpt}-byte traces "
                f"({rem} bytes left over): "
                + (
                    "the last trace is cut short"
                    if code == "TRUNCATED"
                    else "either a truncated file or variable-length traces; "
                    "no offset past the first trace can be trusted"
                ),
            )
        )

    sample = sample_traces(reader, data_offset, bpt, traces, binary.order)
    hs = sample.headers
    counts["sampled_headers"] = len(hs)
    detail["sample"] = {"indices": sample.indices, "headers": hs}

    bad_len = sum(h["ns"] not in (0, binary.samples) for h in hs)
    if bad_len:
        findings.append(
            rpt.finding(
                "SDIP_TRACE_SAMPLES_DIFFER",
                "quarantine",
                f"{bad_len} of {len(hs)} sampled traces declare a sample count other than the "
                f"binary header's {binary.samples}",
            )
        )
    bad_dt = sum(h["dt"] not in (0, binary.interval) for h in hs)
    if bad_dt:
        findings.append(
            rpt.finding(
                "SDIP_TRACE_INTERVAL_DIFFERS",
                "info",
                f"{bad_dt} of {len(hs)} sampled traces declare a sample interval other than the "
                f"binary header's {binary.interval} us; the binary header governs",
            )
        )
    dead = sum(h["trace_id"] == 2 for h in hs)
    if dead:
        counts["dead_sampled"] = dead
        findings.append(
            rpt.finding(
                "SDIP_DEAD_TRACES", "info", f"{dead} of {len(hs)} sampled traces are flagged dead"
            )
        )

    geo = classify_geometry(sample, binary)
    detail["geometry"] = geo
    structural["format"] = "segy" if geo.kind == "unknown" else f"segy-{geo.kind}"
    if geo.kind.startswith("3d") and geo.il and geo.xl:
        counts["inlines"], counts["crosslines"] = geo.il[3], geo.xl[3]
        cells = geo.il[3] * geo.xl[3]
        if geo.kind == "3d-poststack":
            counts["grid_cells"] = cells
            detail["fill"] = traces / cells if cells else 0.0
    rng = []
    if geo.il:
        rng.append(f"inline {geo.il[0]}-{geo.il[1]} step {geo.il[2]}")
    if geo.xl:
        rng.append(f"crossline {geo.xl[0]}-{geo.xl[1]} step {geo.xl[2]}")
    if geo.cdp:
        rng.append(f"CDP {geo.cdp[0]}-{geo.cdp[1]}")
    findings.append(
        rpt.finding(
            "SDIP_GEOMETRY",
            "info",
            f"{geo.kind} ({geo.evidence}); "
            + (", ".join(rng) if rng else "no varying index")
            + f"; from {len(hs)} sampled headers - the full count needs "
            "the ingest's trace-header pass",
        )
    )
    if geo.kind == "3d-poststack" and detail.get("fill", 1.0) > 1.0:
        findings.append(
            rpt.finding(
                "SDIP_GRID_OVERFULL",
                "quarantine",
                f"{traces} traces exceed the {counts['grid_cells']} cells the sampled inline and "
                "crossline ranges imply: duplicated cells or a pre-stack file",
            )
        )

    # Coordinates and scalars
    use_cdp = geo.kind in ("3d-poststack", "2d-poststack") or geo.gather == "cdp"
    xs, ys = ("cdp_x", "cdp_y") if use_cdp else ("src_x", "src_y")
    coords = [(h[xs], h[ys]) for h in hs]
    if not any(x or y for x, y in coords):
        alt = ("src_x", "src_y") if use_cdp else ("cdp_x", "cdp_y")
        if any(h[alt[0]] or h[alt[1]] for h in hs):
            xs, ys = alt
            coords = [(h[xs], h[ys]) for h in hs]
    has_coords = any(x or y for x, y in coords)
    detail["coords"] = (xs, ys, has_coords)
    scalars = Counter(h["scalar"] for h in hs)
    detail["scalars"] = dict(scalars)
    illegal = sorted(s for s in scalars if s != 0 and abs(s) not in VALID_SCALARS)
    if has_coords and illegal:
        findings.append(
            rpt.finding(
                "SDIP_COORD_SCALAR_INVALID",
                "quarantine",
                f"coordinate scalar(s) {illegal} at bytes 71-72; SEG-Y allows 1, +/-10, "
                "+/-100, +/-1000, +/-10000 (0 means 1 from rev 2)",
            )
        )
    if has_coords and len(scalars) > 1:
        findings.append(
            rpt.finding(
                "SDIP_COORD_SCALAR_VARIES",
                "info",
                f"the coordinate scalar varies across sampled traces: {dict(scalars)}",
            )
        )
    if has_coords and 0 in scalars:
        findings.append(
            rpt.finding(
                "SDIP_COORD_SCALAR_ZERO",
                "info",
                "coordinate scalar 0: SEG-Y rev 2 reads it as 1; the pinned MDIO accepts it only "
                "from revision 2",
            )
        )
    units = Counter(h["coord_units"] for h in hs)
    detail["coord_units"] = {COORD_UNITS.get(u, f"unset ({u})"): n for u, n in units.items()}
    if has_coords and 3 in units:

        def scaled(v: int, s: int) -> float:
            return v / -s if s < 0 else v * (s or 1)

        big = sum(
            abs(scaled(h[xs], h["scalar"])) > 360 or abs(scaled(h[ys], h["scalar"])) > 90
            for h in hs
        )
        if big:
            # Asked, not quarantined (D-0142): P36 found the flag wrong on more than one
            # unrelated survey, and the user knows which unit the coordinates are in.
            findings.append(
                rpt.finding(
                    "SDIP_COORD_UNITS_CONTRADICT",
                    "info",
                    f"{big} of {len(hs)} sampled traces declare decimal degrees "
                    "(bytes 89-90 = 3) but carry coordinates outside +/-180 / +/-90 after "
                    "the scalar: the units flag or the coordinates are wrong",
                )
            )
            questions.append(
                rpt.question(
                    "UNITS_AMBIGUOUS",
                    "The trace headers say the coordinates are decimal degrees, but their "
                    "values are too large for degrees. Which unit are they in?",
                    [
                        {"id": "m", "label": "metres (projected)"},
                        {"id": "ft", "label": "feet (projected)"},
                        {"id": "deg", "label": "degrees (the values are wrong)"},
                    ],
                    subject="coordinates",
                )
            )
    if not has_coords:
        findings.append(
            rpt.finding(
                "SDIP_NO_COORDINATES",
                "info",
                "every sampled trace has zero coordinates at CDP and source positions; the data "
                "cannot be placed on a map from its headers",
            )
        )

    # CRS: never inferred; textual-header words are offered as candidates.
    cands = _crs_candidates(text)
    structural["hasCrs"] = bool(cands)
    detail["crs_candidates"] = cands
    if has_coords:
        choices = [{"id": f"cand{i}", "label": c, "source": s} for i, (c, s) in enumerate(cands)]
        choices += [
            {"id": "epsg", "label": "Enter an EPSG code"},
            {"id": "unknown", "label": "I don't know"},
        ]
        questions.append(
            rpt.question(
                "CRS_UNRESOLVED",
                "Which coordinate reference system are the trace coordinates in?"
                + (
                    " Candidates were found in the textual header."
                    if cands
                    else " The textual header names none."
                ),
                choices,
                subject="trace-header coordinates",
            )
        )

    # Units of length
    structural["hasUnits"] = binary.measurement in (1, 2)
    if binary.measurement in (1, 2):
        detail["measurement"] = "metres" if binary.measurement == 1 else "feet"
    elif (
        has_coords
        and set(units) <= {0, 1}
        and not any(q["code"] == "UNITS_AMBIGUOUS" for q in questions)
    ):
        questions.append(
            rpt.question(
                "UNITS_AMBIGUOUS",
                "The binary header (bytes 3255-3256) does not state metres or feet. "
                "Which unit are the "
                "coordinates and depths in?",
                [{"id": "m", "label": "metres"}, {"id": "ft", "label": "feet"}],
                subject="coordinates",
            )
        )

    # Vertical domain: asked, with what the textual header says.
    t_words, d_words = _domain_words(text)
    src = "SEG-Y textual header"
    choices = [
        {"id": "twt", "label": "time, two-way (TWT)"}
        | ({"source": src} if t_words and not d_words else {}),
        {"id": "owt", "label": "time, one-way (OWT)"},
        {"id": "depth", "label": "depth"} | ({"source": src} if d_words and not t_words else {}),
    ]
    questions.append(
        rpt.question(
            "DOMAIN_UNKNOWN",
            "Is the vertical axis time or depth? SEG-Y does not record it"
            + (
                "; the textual header mentions time."
                if t_words and not d_words
                else "; the textual header mentions depth."
                if d_words and not t_words
                else "."
            ),
            choices,
            subject="vertical axis",
        )
    )
    detail["domain_words"] = (t_words, d_words)

    # The route into an MDIO store, as today.
    template = _template(geo, "depth" if d_words and not t_words else "time")
    detail["template"] = template
    if template:
        preflight = _preflight(path, size, binary)
        if preflight:
            findings.append(
                rpt.finding(
                    "ENGINE_REFUSED", "quarantine", f"sdip ingest preflight refuses: {preflight}"
                )
            )
        else:
            needs = (
                " with a survey override naming the gather keys (spec 6.4)"
                if "prestack" in geo.kind
                else ""
            )
            needs += '; declare endianness = "little"' if binary.order == "little" else ""
            findings.append(
                rpt.finding(
                    "SDIP_MDIO_ROUTE",
                    "info",
                    f"route: sdip ingest --template {template} "
                    f"--revision {_rev_choice(binary.revision)}{needs}; "
                    "the template's Time/Depth follows the domain answer",
                )
            )
    return done()


def _rev_choice(revision: str) -> str:
    major = revision.split(".")[0]
    return {"0": "0", "1": "1", "2": "2"}.get(major, "1")


def _preflight(path: Path, size: int, binary: Binary) -> str | None:
    """The ingest preflight's refusal, or None when it admits the file. 400 + 2 bytes."""
    from sdip.errors import UntrustedInputError
    from sdip.ingest.preflight import validate_segy_structure

    try:
        validate_segy_structure(
            path, size, endianness=binary.order, revision=float(_rev_choice(binary.revision))
        )
    except UntrustedInputError as exc:
        return str(exc)[:400]
    return None
