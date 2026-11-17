"""Intake QC of one OpenVDS file: layout and metadata only, read by OpenVDS in a container.

OpenVDS ships Linux and Windows x86-64 wheels only, so SDIP runs it in the image built from
``ci/intake-vds/`` (``openvds`` 3.4.9): networking off, root filesystem read-only, the file
bind-mounted read-only. The host side recognises a VDS by content (``HueDataStore`` magic) and
maps the probe's JSON into a ``geosuite.intake.v1`` report.

Reported: dimensions and axes (names, units, sample counts, ranges), the vertical domain from
the sample axis unit, channels and their formats, the survey grid's unit, the CRS WKT (offered as
a candidate, never taken), and the compression method (wavelet compression is lossy).

**Truncation (D-0149).** OpenVDS's layout sits at the front of the file and ``openvds.open``
accepts a cut file (P38 V4). The probe therefore runs OpenVDS's own ``HueBDS check`` first, which
reads the container's file table and index pages (no brick) and prints the allocation map. A
failed check is ``SDIP_VDS_CONTAINER_INVALID``; a mapped extent ending past the size the host
measured is ``SDIP_VDS_TRUNCATED``; a probe that reports no check is
``SDIP_VDS_INTEGRITY_UNCHECKED``. All three are ``QUARANTINE``: not checked is not passed.
Not covered: damage that keeps every extent inside the file (a flipped byte inside a brick).
OpenVDS's own reads inside the container are not counted in ``headerBytesRead``, which counts
SDIP's host-side reads only.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any, Final

from sdip.intake import report as rpt
from sdip.intake.segy import Outcome

TOOL: Final[str] = "sdip.intake.vds"
IMAGE: Final[str] = "sdip-intake-vds:3.4.9"
MAGIC: Final[bytes] = b"HueDataStore"
HEADER_BUDGET: Final[int] = 1 << 20
TIMEOUT_S: Final[int] = 300
LIBRARY: Final[dict[str, str]] = {"name": "openvds", "version": "3.4.9", "licence": "Apache-2.0"}
TIME_UNITS: Final[frozenset[str]] = frozenset({"ms", "s", "us"})
DEPTH_UNITS: Final[frozenset[str]] = frozenset({"m", "ft", "km", "usft"})

Runner = Callable[[Path], dict[str, Any]]


def is_vds(head: bytes) -> bool:
    """The content test: OpenVDS's single-file container magic."""
    return head.startswith(MAGIC)


def docker_runner(path: Path) -> dict[str, Any]:
    """Run the probe image on one file; ``{"ok": False, "unavailable": ...}`` when it cannot run."""
    docker = shutil.which("docker")
    if docker is None:
        return {"ok": False, "unavailable": "docker is not installed"}
    src = str(path.resolve())
    if "," in src or "=" in src:
        return {
            "ok": False,
            "unavailable": "the upload path holds a character the bind mount cannot carry",
        }
    cmd = [
        docker,
        "run",
        "--rm",
        "--platform",
        "linux/amd64",
        "--network",
        "none",
        "--read-only",
        "--memory",
        "2g",
        "--mount",
        f"type=bind,src={src},dst=/in/file.vds,readonly",
        IMAGE,
        "/in/file.vds",
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT_S, check=False)  # noqa: S603
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            "ok": False,
            "unavailable": f"the OpenVDS container did not run: {type(exc).__name__}",
        }
    lines = [ln for ln in proc.stdout.splitlines() if ln.startswith("{")]
    if proc.returncode != 0 or not lines:
        why = (
            "image missing"
            if "Unable to find image" in proc.stderr or "No such image" in proc.stderr
            else (f"exit {proc.returncode}")
        )
        return {"ok": False, "unavailable": f"the OpenVDS container failed ({why})"}
    out: dict[str, Any] = json.loads(lines[-1])
    return out


def integrity_findings(check: dict[str, Any] | None, size: int) -> list[dict[str, Any]]:
    """Map the probe's ``HueBDS check`` result against the size measured on the host."""
    if not isinstance(check, dict) or not check.get("checked"):
        return [
            rpt.finding(
                "SDIP_VDS_INTEGRITY_UNCHECKED",
                "quarantine",
                "the container did not check the file's allocation map, so a cut-short file "
                "cannot be ruled out: kept, not passed",
            )
        ]
    if check.get("exit") != 0:
        why = str(check.get("message") or f"exit {check.get('exit')}")
        return [
            rpt.finding(
                "SDIP_VDS_CONTAINER_INVALID",
                "quarantine",
                f"OpenVDS's own container check rejects the file ({why}); it is cut short or "
                "damaged: kept, not passed"[:400],
            )
        ]
    end = check.get("maxExtentEnd")
    if not isinstance(end, int) or isinstance(end, bool):
        return integrity_findings(None, size)
    if end > size:
        return [
            rpt.finding(
                "SDIP_VDS_TRUNCATED",
                "quarantine",
                f"the file is cut short: its own allocation map runs to byte {end:,} but the "
                f"file holds {size:,} bytes ({end - size:,} missing): kept, not passed",
            )
        ]
    return [
        rpt.finding(
            "SDIP_VDS_EXTENTS_INSIDE",
            "info",
            f"every region in the file's allocation map ({check.get('regions')}) ends inside "
            f"the file (furthest at byte {end:,} of {size:,}); a damaged byte inside a "
            "brick is not checked",
        )
    ]


def qc_vds(
    path: str | Path,
    *,
    upload_id: str,
    member: str,
    sha256: str,
    cls: str = rpt.DEFAULT_CLASS,
    commit: str | None = None,
    runner: Runner = docker_runner,
) -> Outcome:
    """Layout QC of one VDS file. Never raises on file content."""
    path = Path(path)
    size = path.stat().st_size
    findings: list[dict[str, Any]] = []
    questions: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    detail: dict[str, Any] = {"member": member, "class": cls, "kind": "vds"}
    commit = commit or rpt.reader_commit()
    structural: dict[str, Any] = {
        "format": "vds",
        "version": None,
        "counts": counts,
        "hasCrs": None,
        "hasUnits": None,
        "hasNulls": None,
        "domain": "unknown",
    }
    detect: dict[str, Any] = {
        "format": "vds",
        "by": f"{TOOL}@{commit[:12]}",
        "evidence": "HueDataStore magic",
    }
    with path.open("rb") as handle:
        head = handle.read(16)

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
            header_bytes_read=len(head),
            header_budget=HEADER_BUDGET,
            library=LIBRARY,
        )
        return Outcome(rep, detail)

    if not is_vds(head):
        detect["format"] = structural["format"] = "unknown"
        findings.append(
            rpt.finding(
                "UNSUPPORTED_FORMAT", "refuse", "not a single-file VDS: no HueDataStore magic"
            )
        )
        return done()
    if cls == "cluster-derived":
        findings.append(
            rpt.finding(
                "CLUSTER_RAW_REFUSED",
                "refuse",
                "the upload is classed cluster-derived; it is deleted and only its hash and "
                "size are kept",
            )
        )
        return done()
    suffix = Path(member).suffix.lower()
    if suffix and suffix != ".vds":
        detect["contradiction"] = f"extension {suffix}; content is VDS"
        findings.append(
            rpt.finding("EXTENSION_CONTRADICTION", "info", f"the extension {suffix} is not .vds")
        )

    probe = runner(path)
    detail["probe"] = probe
    if not probe.get("ok"):
        if "unavailable" in probe:
            findings.append(
                rpt.finding(
                    "SDIP_VDS_READER_UNAVAILABLE",
                    "quarantine",
                    f"{probe['unavailable']}; the layout was not read: kept, not passed",
                )
            )
        else:
            findings.extend(integrity_findings(probe.get("integrity"), size))
            findings.append(
                rpt.finding(
                    "HEADER_INVALID",
                    "quarantine",
                    f"OpenVDS cannot open the file: {probe.get('error', '?')}"[:400],
                )
            )
        return done()
    findings.extend(integrity_findings(probe.get("integrity"), size))

    axes = probe.get("axes", [])
    names = [a.get("name", "") for a in axes]
    for a in axes:
        key = {"Sample": "samples", "Inline": "inlines", "Crossline": "crosslines"}.get(
            a.get("name", "")
        )
        if key:
            counts[key] = int(a.get("samples", 0))
    counts["dimensions"] = int(probe.get("dimensionality", len(axes)))
    counts["channels"] = len(probe.get("channels", []))
    if set(names) >= {"Sample", "Inline", "Crossline"} and len(axes) == 3:
        structural["format"] = "vds-3d-poststack"
    sample = next((a for a in axes if a.get("name") in ("Sample", "Time", "Depth")), None)
    unit = (sample or {}).get("unit", "")
    structural["domain"] = (
        "time" if unit in TIME_UNITS else ("depth" if unit in DEPTH_UNITS else "unknown")
    )
    structural["hasUnits"] = bool(unit) and bool(probe.get("unit"))
    rng = ", ".join(
        f"{a.get('name')} {a.get('min'):g}-{a.get('max'):g} {a.get('unit', '')} "
        f"({a.get('samples')})"
        for a in axes
    )
    findings.append(
        rpt.finding("SDIP_GEOMETRY", "info", f"{counts['dimensions']}-D volume: {rng}"[:500])
    )
    if structural["domain"] == "unknown":
        questions.append(
            rpt.question(
                "DOMAIN_UNKNOWN",
                f"The sample axis unit is '{unit}'. Is the vertical axis time or depth?",
                [
                    {"id": "twt", "label": "time, two-way (TWT)"},
                    {"id": "owt", "label": "time, one-way (OWT)"},
                    {"id": "depth", "label": "depth"},
                ],
                subject="vertical axis",
            )
        )
    wkt = probe.get("crsWkt")
    structural["hasCrs"] = bool(wkt)
    if probe.get("origin") is not None:
        choices = (
            [
                {
                    "id": "cand0",
                    "label": str(wkt)[:200],
                    "source": "VDS SurveyCoordinateSystem CRSWkt",
                }
            ]
            if wkt
            else []
        )
        choices += [
            {"id": "epsg", "label": "Enter an EPSG code"},
            {"id": "unknown", "label": "I don't know"},
        ]
        questions.append(
            rpt.question(
                "CRS_UNRESOLVED",
                "Which coordinate reference system is the survey grid in? "
                + ("The file carries a WKT given at import." if wkt else "The file names none."),
                choices,
                subject="survey coordinate system",
            )
        )
    if probe.get("lossy"):
        findings.append(
            rpt.finding(
                "SDIP_VDS_LOSSY",
                "info",
                f"{probe.get('compression')} compression is lossy: samples are an approximation",
            )
        )
    findings.append(
        rpt.finding(
            "SDIP_NO_MDIO_ROUTE",
            "info",
            "SDIP ingests SEG-Y only: export with OpenVDS's SEGYExport (same container), "
            "then sdip ingest",
        )
    )
    return done()
