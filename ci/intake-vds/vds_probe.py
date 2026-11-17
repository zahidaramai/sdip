"""Print the layout of one VDS as JSON, read through OpenVDS's public API (runs in the container).

    docker run --rm --network none -v FILE:/in/file.vds:ro sdip-intake-vds:3.4.9 /in/file.vds

Reads the layout and metadata only; no brick is requested. Exit 0 with {"ok": false, "error"}
when OpenVDS cannot open the file.

Before opening, OpenVDS's own ``HueBDS check`` reads the container's file table and index pages
and prints its allocation map (no brick is read). Its exit code, first message line and the end
of the furthest mapped extent go out as ``integrity``; the host compares that end with the size
it measured itself (D-0149: a cut that leaves the layout whole is invisible to ``openvds.open``).
"""

from __future__ import annotations

import json
import re
import subprocess
import sys

EXTENT = re.compile(r"size:\s*(\d+)\s+at offset:\s*(\d+)")


def integrity(path: str) -> dict:
    """HueBDS check: exit code, first line, mapped regions and the furthest extent end."""
    try:
        proc = subprocess.run(  # noqa: S603 - fixed argv; path is the read-only mount point
            ["HueBDS", "check", path],  # noqa: S607 - OpenVDS's tool on the image's PATH
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"checked": False, "error": type(exc).__name__}
    text = proc.stdout + proc.stderr
    ends = [int(s) + int(o) for s, o in EXTENT.findall(text)]
    first = next((ln.strip() for ln in text.splitlines() if ln.strip()), "")
    return {
        "checked": True,
        "exit": proc.returncode,
        "message": first[:300],
        "regions": len(ends),
        "maxExtentEnd": max(ends) if ends else None,
    }


def main(path: str) -> None:
    """Print the container check and the layout of one VDS as one JSON line."""
    import openvds

    check = integrity(path)
    try:
        handle = openvds.open(path, "")
    except Exception as exc:  # OpenVDS raises its own error types
        print(
            json.dumps(
                {"ok": False, "error": f"{type(exc).__name__}: {exc}"[:400], "integrity": check}
            )
        )
        return
    layout = openvds.getLayout(handle)
    axes = []
    for d in range(layout.getDimensionality()):
        a = layout.getAxisDescriptor(d)
        axes.append(
            {
                "name": a.getName(),
                "unit": a.getUnit(),
                "samples": a.getNumSamples(),
                "min": a.getCoordinateMin(),
                "max": a.getCoordinateMax(),
            }
        )
    channels = []
    for c in range(layout.getChannelCount()):
        ch = layout.getChannelDescriptor(c)
        channels.append(
            {
                "name": ch.getName(),
                "unit": ch.getUnit(),
                "format": str(ch.getFormat()),
                "min": ch.getValueRangeMin(),
                "max": ch.getValueRangeMax(),
                "noValue": ch.isUseNoValue(),
            }
        )

    def meta(category: str, name: str, kind: str) -> object:
        try:
            if kind == "s" and layout.isMetadataStringAvailable(category, name):
                return layout.getMetadataString(category, name)
            if kind == "d2" and layout.isMetadataDoubleVector2Available(category, name):
                return list(layout.getMetadataDoubleVector2(category, name))
            if kind == "b" and layout.isMetadataBLOBAvailable(category, name):
                return len(layout.getMetadataBLOB(category, name))
        except Exception:
            return None
        return None

    survey = "SurveyCoordinateSystem"
    out = {
        "ok": True,
        "integrity": check,
        "dimensionality": layout.getDimensionality(),
        "axes": axes,
        "channels": channels,
        "crsWkt": meta(survey, "CRSWkt", "s"),
        "origin": meta(survey, "Origin", "d2"),
        "inlineSpacing": meta(survey, "InlineSpacing", "d2"),
        "crosslineSpacing": meta(survey, "CrosslineSpacing", "d2"),
        "unit": meta(survey, "Unit", "s"),
        "textHeaderBytes": meta("SEGY", "TextHeader", "b"),
        "inputFileSize": meta("ImportInformation", "InputFileSize", "s"),
    }
    try:
        out["compression"] = str(openvds.getCompressionMethod(handle)).split(".")[-1]
        out["lossy"] = bool(
            openvds.compressionMethod_IsWavelet(openvds.getCompressionMethod(handle))
        )
    except Exception as exc:
        out["compression"] = f"unknown ({type(exc).__name__})"
        out["lossy"] = None
    out["metadataKeys"] = sorted(f"{k.category}/{k.name}" for k in layout.getMetadataKeys())
    openvds.close(handle)
    print(json.dumps(out))


if __name__ == "__main__":
    main(sys.argv[1])
