"""Intake QC of one SEG-D field record (revisions 0 to 2), headers only.

Layout from the SEG-D standard (rev 1, Geophysics 59, 668-684, 1994; rev 2.1) as Seismic Unix's
``segd.h`` (Colorado School of Mines) records it: 32-byte general header blocks (BCD in block 1),
32-byte channel set descriptors, skew, extended and external header blocks, then 20-byte
demultiplexed trace headers with 32-byte extensions. No code is copied.

**Revision 3** uses 96-byte channel set descriptors that this reader does not parse: a rev 3
record gets its general-header facts and an information finding saying the rest was not
checked. **Multiplexed** formats are reported, not walked. SEG-D carries no source or receiver
coordinates (they come with SPS or P1/90 files), so no CRS question is asked of it.

Checks: a coherent general header 1 (BCD digits, date and time in range, known format code), the
revision, the header-block counts and where the first trace must start, each channel set's
channel count, type and time window, then a walk over the demultiplexed trace headers (bounded)
reconciling the file size with the declared channels (``TRUNCATED``, ``SIZE_INCONSISTENT``).
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any, Final

from sdip.intake import report as rpt
from sdip.intake.segy import Outcome, Reader

TOOL: Final[str] = "sdip.intake.segd"
HEADER_BUDGET: Final[int] = 1 << 20
BLOCK: Final[int] = 32
TRACE_HEADER: Final[int] = 20
MAX_TRACES_WALKED: Final[int] = 20000

FORMATS: Final[dict[int, tuple[str, float, bool]]] = {
    # code: (encoding, bytes per sample, demultiplexed)
    15: ("20-bit binary", 2.5, False),
    22: ("8-bit quaternary", 1, False),
    24: ("16-bit integer", 2, False),
    36: ("24-bit integer", 3, False),
    38: ("32-bit integer", 4, False),
    42: ("8-bit hexadecimal", 1, False),
    44: ("16-bit hexadecimal", 2, False),
    48: ("32-bit hexadecimal", 4, False),
    58: ("32-bit IEEE", 4, False),
    8015: ("20-bit binary", 2.5, True),
    8022: ("8-bit quaternary", 1, True),
    8024: ("16-bit integer", 2, True),
    8036: ("24-bit integer", 3, True),
    8038: ("32-bit integer", 4, True),
    8042: ("8-bit hexadecimal", 1, True),
    8044: ("16-bit hexadecimal", 2, True),
    8048: ("32-bit hexadecimal", 4, True),
    8058: ("32-bit IEEE", 4, True),
}
CHANNEL_TYPES: Final[dict[int, str]] = {
    0: "unused",
    1: "seis",
    2: "time break",
    3: "up-hole",
    4: "water break",
    5: "time counter",
    6: "external data",
    7: "other",
    8: "signature unfiltered",
    9: "auxiliary",
    0xC: "signature filtered",
}


def bcd(data: bytes) -> int | None:
    """Unsigned packed BCD, or None when a nibble is not a decimal digit."""
    out = 0
    for byte in data:
        hi, lo = byte >> 4, byte & 0xF
        if hi > 9 or lo > 9:
            return None
        out = out * 100 + hi * 10 + lo
    return out


def _nib(byte: int) -> int | None:
    return None if byte > 9 else byte


def parse_gh1(gh: bytes) -> dict[str, Any] | None:
    """General header block 1, or None when it is not coherent BCD SEG-D."""
    fmt = bcd(gh[2:4])
    year = bcd(gh[10:11])
    day_hi = _nib(gh[11] & 0xF)
    day_lo = bcd(gh[12:13])
    hms = [bcd(gh[i : i + 1]) for i in (13, 14, 15)]
    if fmt is None or year is None or day_hi is None or day_lo is None or None in hms:
        return None
    day = day_hi * 100 + day_lo
    hour, minute, second = (int(v or 0) for v in hms)
    if fmt not in FORMATS or not 1 <= day <= 366 or hour > 23 or minute > 59 or second > 59:
        return None

    def esc(b: bytes) -> int | None:
        """A BCD count, None for the FF escape that sends the reader to block 2."""
        return None if b == b"\xff" * len(b) else bcd(b)

    record_len = (
        None if (gh[25] & 0xF) == 0xF and gh[26] == 0xFF else bcd(bytes([gh[25] & 0xF, gh[26]]))
    )
    return {
        "file": esc(gh[0:2]),
        "format": fmt,
        "year": year,
        "additional": gh[11] >> 4,
        "day": day,
        "time": (hour, minute, second),
        "manufacturer": bcd(gh[16:17]),
        "base_scan_sixteenths_ms": gh[22],
        "record_type": gh[25] >> 4,
        "record_length_units": record_len,
        "scan_types": esc(gh[27:28]),
        "channel_sets": esc(gh[28:29]),
        "skew_blocks": esc(gh[29:30]),
        "extended_blocks": esc(gh[30:31]),
        "external_blocks": esc(gh[31:32]),
    }


def is_segd(head: bytes) -> bool:
    """The content test: a coherent general header block 1."""
    return len(head) >= BLOCK and parse_gh1(head[:BLOCK]) is not None


def _u(b: bytes) -> int:
    return int.from_bytes(b, "big")


def qc_segd(
    path: str | Path,
    *,
    upload_id: str,
    member: str,
    sha256: str,
    cls: str = rpt.DEFAULT_CLASS,
    commit: str | None = None,
) -> Outcome:
    """Header-only intake QC of one file believed to be SEG-D. Never raises on file content."""
    path = Path(path)
    size = path.stat().st_size
    reader = Reader(path, size)
    findings: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    detail: dict[str, Any] = {"member": member, "class": cls, "kind": "segd"}
    commit = commit or rpt.reader_commit()
    structural: dict[str, Any] = {
        "format": "segd",
        "version": None,
        "counts": counts,
        "hasCrs": False,
        "hasUnits": None,
        "hasNulls": None,
        "domain": "time",
    }
    detect: dict[str, Any] = {"format": "segd", "by": f"{TOOL}@{commit[:12]}"}

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
            questions=[],
            header_bytes_read=reader.bytes_read,
            header_budget=HEADER_BUDGET,
        )
        return Outcome(rep, detail)

    gh1_raw = reader.read(0, BLOCK)
    gh1 = parse_gh1(gh1_raw) if len(gh1_raw) == BLOCK else None
    if gh1 is None:
        detect["format"] = structural["format"] = "unknown"
        structural["domain"] = "unknown"
        findings.append(
            rpt.finding(
                "UNSUPPORTED_FORMAT",
                "refuse",
                "not SEG-D: general header block 1 is not coherent BCD",
            )
        )
        return done()
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
    if suffix and suffix not in (".segd", ".sgd", ".sd", ".raw"):
        detect["contradiction"] = f"extension {suffix} names another format; content is SEG-D"
        findings.append(
            rpt.finding(
                "EXTENSION_CONTRADICTION",
                "info",
                f"the extension {suffix} is not a SEG-D extension; the content decides",
            )
        )
    encoding, bps, demux = FORMATS[gh1["format"]]
    detail["gh1"] = gh1
    n_gh = 1 + gh1["additional"]
    revision = "0"
    gh2: bytes | None = None
    if gh1["additional"]:
        gh2 = reader.read(BLOCK, BLOCK)
        if len(gh2) < BLOCK:
            findings.append(
                rpt.finding("TRUNCATED", "quarantine", "the file ends inside the general header")
            )
            return done()
        revision = f"{gh2[10]}.{gh2[11]}"
    structural["version"] = revision
    detect["version"] = revision
    detect["evidence"] = (
        f"general header 1: format {gh1['format']:04d}, day {gh1['day']}, revision {revision}"
    )
    structural["format"] = "segd-demux" if demux else "segd-multiplexed"
    counts["format_code"] = gh1["format"]
    detail["format"] = (
        f"{gh1['format']:04d} {encoding}, {'demultiplexed' if demux else 'multiplexed'}"
    )

    def count(name: str, gh2_slice: slice) -> int | None:
        v = gh1[name]
        if v is None and gh2 is not None:
            return _u(gh2[gh2_slice])
        return None if v is None else int(v)

    scan_types = gh1["scan_types"] or 0
    channel_sets = count("channel_sets", slice(3, 5))
    extended = count("extended_blocks", slice(5, 7))
    external = count("external_blocks", slice(7, 9))
    skew = gh1["skew_blocks"] or 0
    trailer = _u(gh2[12:14]) if gh2 is not None else 0
    if channel_sets is None or extended is None or external is None:
        findings.append(
            rpt.finding(
                "HEADER_INVALID",
                "quarantine",
                "a header-block count uses the FF escape but there is no general header block 2",
            )
        )
        return done()
    counts.update(
        scan_types=scan_types,
        channel_sets=channel_sets,
        extended_blocks=extended,
        external_blocks=external,
        general_header_blocks=n_gh,
    )
    if revision.startswith("3"):
        findings.append(
            rpt.finding(
                "SDIP_SEGD_REV3_PARTIAL",
                "info",
                "SEG-D revision 3: the general headers were read; its 96-byte channel set "
                "descriptors and trace "
                "headers are not parsed by this reader, so channels and size were not checked",
            )
        )
        return _route(done, findings)
    if not demux:
        findings.append(
            rpt.finding(
                "SDIP_SEGD_MULTIPLEXED",
                "info",
                f"multiplexed format {gh1['format']:04d}: channels and size were not walked",
            )
        )
        return _route(done, findings)

    # Channel set descriptors
    cs_start = n_gh * BLOCK
    n_cs = scan_types * channel_sets
    if cs_start + n_cs * BLOCK > size or n_cs > 4096:
        findings.append(
            rpt.finding(
                "TRUNCATED" if cs_start + n_cs * BLOCK > size else "HEADER_INVALID",
                "quarantine",
                f"{n_cs} channel set descriptors cannot fit or exceed the reader's limit",
            )
        )
        return done()
    descs = reader.read(cs_start, n_cs * BLOCK)
    sets: list[dict[str, Any]] = []
    interval_ms = gh1["base_scan_sixteenths_ms"] / 16.0
    for k in range(n_cs):
        d = descs[k * BLOCK : (k + 1) * BLOCK]
        n_ch = bcd(d[8:10])
        sets.append(
            {
                "scan_type": bcd(d[0:1]),
                "set": bcd(d[1:2]),
                "start_ms": _u(d[2:4]) * 2,
                "end_ms": _u(d[4:6]) * 2,
                "channels": n_ch,
                "type": d[10] >> 4,
            }
        )
    detail["channel_sets"] = sets
    if any(s["channels"] is None for s in sets):
        findings.append(
            rpt.finding("HEADER_INVALID", "quarantine", "a channel count is not valid BCD")
        )
        return done()
    by_type = Counter()  # type: Counter[str]
    for s in sets:
        by_type[CHANNEL_TYPES.get(s["type"], f"type {s['type']}")] += s["channels"]
    detail["channels_by_type"] = dict(by_type)
    total = sum(s["channels"] for s in sets)
    counts["channels"] = total
    counts["seis_channels"] = by_type.get("seis", 0)
    counts["aux_channels"] = total - by_type.get("seis", 0)
    if interval_ms <= 0:
        findings.append(rpt.finding("HEADER_INVALID", "quarantine", "base scan interval is zero"))
        return done()
    detail["interval_ms"] = interval_ms

    data_start = cs_start + BLOCK * (n_cs + skew + extended + external)
    detail["data_start"] = data_start
    # Walk the demultiplexed trace headers.
    pos, walked, bad = data_start, 0, 0
    lengths: Counter[int] = Counter()
    while walked < min(total, MAX_TRACES_WALKED) and pos + TRACE_HEADER <= size:
        th = reader.read(pos, TRACE_HEADER)
        n_ext = th[9]
        samples = None
        if n_ext:
            ext = reader.read(pos + TRACE_HEADER, BLOCK)
            samples = _u(ext[7:10]) if len(ext) == BLOCK else None
        if not samples:
            cs_no = bcd(th[3:4])
            match = next((s for s in sets if s["set"] == cs_no), None)
            samples = round((match["end_ms"] - match["start_ms"]) / interval_ms) if match else 0
            if match is None:
                bad += 1
        stride = TRACE_HEADER + BLOCK * n_ext + int(samples * bps)
        lengths[samples] += 1
        pos += stride
        walked += 1
        if reader.bytes_read > HEADER_BUDGET - 64:
            break
    counts["traces_walked"] = walked
    detail["samples_per_trace"] = dict(lengths)
    if bad:
        findings.append(
            rpt.finding(
                "SDIP_SEGD_UNKNOWN_CHANNEL_SET",
                "quarantine",
                f"{bad} trace headers name a channel set the descriptors do not declare",
            )
        )
    if walked < total:
        findings.append(
            rpt.finding(
                "TRUNCATED" if pos + TRACE_HEADER > size else "HEADER_BUDGET",
                "quarantine" if pos + TRACE_HEADER > size else "info",
                f"{walked} of {total} declared traces found before "
                + (
                    "the end of the file"
                    if pos + TRACE_HEADER > size
                    else "the header budget ran out"
                ),
            )
        )
    else:
        end = pos + BLOCK * trailer
        if end > size:
            findings.append(
                rpt.finding(
                    "TRUNCATED",
                    "quarantine",
                    f"the {total} declared traces end at byte {end} of a {size}-byte file",
                )
            )
        elif end < size:
            rest = reader.read(end, BLOCK)
            if is_segd(rest):
                findings.append(
                    rpt.finding(
                        "SDIP_SEGD_MORE_RECORDS",
                        "info",
                        "another SEG-D record follows the first; only the first was checked",
                    )
                )
            else:
                findings.append(
                    rpt.finding(
                        "SIZE_INCONSISTENT",
                        "quarantine",
                        f"{size - end} bytes follow the declared traces and are not a SEG-D record",
                    )
                )
    kinds = ", ".join(f"{n} {t}" for t, n in by_type.items())
    findings.append(
        rpt.finding(
            "SDIP_GEOMETRY",
            "info",
            f"field record: {total} channels ({kinds}), "
            f"{gh1['format']:04d} {encoding}, base scan {interval_ms:g} ms",
        )
    )
    return _route(done, findings)


def _route(done: Any, findings: list[dict[str, Any]]) -> Outcome:
    findings.append(
        rpt.finding(
            "SDIP_SEGD_NO_COORDINATES",
            "info",
            "SEG-D records carry no source or receiver coordinates; positions come with SPS "
            "or P1/90 files",
        )
    )
    findings.append(
        rpt.finding(
            "SDIP_NO_MDIO_ROUTE",
            "info",
            "SDIP ingests SEG-Y only: convert the field records to SEG-Y with the positions "
            "merged, then sdip ingest",
        )
    )
    out: Outcome = done()
    return out
