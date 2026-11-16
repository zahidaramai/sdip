"""The QC card of one seismic intake report: a PNG for the USER, drawn from headers only.

A QC card of a confidential file is confidential data: it is shown to the user, and to a
model only for ``public`` or ``synthetic`` uploads (``qcCard.release``). It is drawn from the
same sampled trace headers the report used; no sample is read.

Needs the ``intake`` extra (matplotlib).
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from sdip.intake.report import reader_commit

RELEASE = {
    "public": "full",
    "synthetic": "full",
    "internal": "nothing",
    "confidential": "nothing",
    "restricted": "nothing",
    "cluster-derived": "nothing",
}
"""A card is an image of the data: a model sees it only for public or synthetic uploads."""
VERDICT_COLOUR = {
    "PASS": "#1a7f37",
    "PASS_WITH_ASSUMPTIONS": "#4c8c2b",
    "NEEDS_INPUT": "#9a6700",
    "QUARANTINE": "#cf222e",
    "REFUSED": "#6e2d91",
}
SEVERITY_MARK = {
    "info": "i",
    "assumption": "a",
    "needs_input": "?",
    "quarantine": "Q",
    "refuse": "R",
}


def _summary(outcome: Any) -> list[str]:
    rep, det = outcome.report, outcome.detail
    st = rep["structural"]
    lines = [f"format   {st['format']}   revision {st.get('version')}"]
    if det.get("kind") == "zgy" and "info" in det:
        info = det["info"]
        lines += [
            f"size {info['size']}   bricks {info['bricksize']}   data type {det.get('datatype')}",
            f"origin {tuple(round(v, 3) for v in info['orig'])}   "
            f"step {tuple(round(v, 3) for v in info['inc'])}",
            f"units {det.get('units')}",
            f"projection: {det.get('strings', {}).get('projection') or 'none'}"[:110],
            f"bricks at full resolution: {det.get('bricks', 'not read')}",
        ]
    if det.get("kind") == "segd" and "gh1" in det:
        g = det["gh1"]
        lines += [
            f"format {det.get('format')}",
            "recorded year {:02d} day {} {:02d}:{:02d}:{:02d}".format(
                g["year"], g["day"], *g["time"]
            ),
            f"base scan {det.get('interval_ms', '?')} ms   "
            f"channels by type {det.get('channels_by_type')}",
            f"samples per trace (walked) {det.get('samples_per_trace')}   "
            f"first trace at byte {det.get('data_start')}",
        ]
    b = det.get("binary")
    if b:
        lines += [
            f"byte order {b['byte order']}   sample format {b['format']}",
            f"samples {b['samples']}   interval {b['interval']} (us or mm)   "
            f"ext. headers {b['extended headers']}",
            f"measurement system {det.get('measurement', 'not stated')}",
        ]
    c = st.get("counts", {})
    if "traces" in c:
        lines.append(f"traces {c['traces']:,}   sampled headers {c.get('sampled_headers', 0):,}")
    if "grid_cells" in c:
        lines.append(
            f"grid {c['inlines']} x {c['crosslines']} = {c['grid_cells']:,} cells   "
            f"fill {det.get('fill', 0):.3f}"
        )
    if det.get("scalars") is not None:
        lines.append(f"coordinate scalars {det['scalars']}   units {det.get('coord_units')}")
    cands = det.get("crs_candidates") or []
    if det.get("kind") is None:
        lines.append("CRS in text header: " + (", ".join(c for c, _ in cands) if cands else "none"))
        t, d = det.get("domain_words", (False, False))
        lines.append(f"text header mentions time: {t}   depth: {d}")
    if det.get("template"):
        lines.append(f"MDIO template candidate: {det['template']}")
    lines.append("")
    lines += [f"[{SEVERITY_MARK[f['severity']]}] {f['code']}" for f in rep["findings"]]
    lines += [f"[?] {q['code']}" for q in rep["questions"]]
    lines.append("")
    lines.append(
        f"header bytes read {rep['headerBytesRead']:,} of budget {rep.get('headerBudget', 0):,}"
        f"   file {rep['file']['bytes']:,} bytes"
    )
    return lines


def draw_card(outcome: Any, png: str | Path, commit: str | None = None) -> dict[str, Any]:
    """Draw the card, return the report's ``qcCard`` entry (member is the PNG's name)."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    rep, det = outcome.report, outcome.detail
    commit = (commit or reader_commit())[:12]
    fig = plt.figure(figsize=(16, 6.2), dpi=110)
    grid = fig.add_gridspec(1, 3, width_ratios=[1.55, 1, 1], wspace=0.28)
    verdict = rep["verdict"]
    fig.suptitle(
        f"SDIP intake QC card  |  {rep['file']['member']}  |  class {rep['class']}  |  "
        f"verdict {verdict}  |  sdip@{commit}",
        fontsize=11,
        color=VERDICT_COLOUR[verdict],
        fontweight="bold",
    )

    ax = fig.add_subplot(grid[0])
    ax.axis("off")
    ax.text(
        0,
        1,
        "\n".join(_summary(outcome)),
        va="top",
        ha="left",
        family="monospace",
        fontsize=7.6,
        transform=ax.transAxes,
    )

    sample = det.get("sample")
    ax2 = fig.add_subplot(grid[1])
    if sample:
        idx = sample["indices"]
        for key, colour in (("inline", "#0969da"), ("crossline", "#bf3989"), ("cdp", "#57606a")):
            vals = [h[key] for h in sample["headers"]]
            if len(set(vals)) > 1:
                ax2.plot(idx, vals, ".", ms=2, color=colour, label=f"{key} (bytes {_bytes(key)})")
        ax2.set_xlabel("trace index in file (first 500 consecutive, then evenly spaced)")
        ax2.set_ylabel("header value (index number)")
        ax2.legend(fontsize=7, loc="best")
        geo = det.get("geometry")
        ax2.set_title(f"trace-header indices: {geo.kind if geo else 'n/a'}", fontsize=9)
    else:
        ax2.axis("off")
        ax2.text(0.5, 0.5, "no trace headers read", ha="center")

    ax3 = fig.add_subplot(grid[2])
    coords = det.get("coords")
    if sample and coords and coords[2]:
        xs, ys, _ = coords
        pts = []
        for h in sample["headers"]:
            s = h["scalar"]
            f = (1 / -s) if s < 0 else (s or 1)
            pts.append((h[xs] * f, h[ys] * f))
        x0 = min(p[0] for p in pts)
        y0 = min(p[1] for p in pts)
        ax3.plot([p[0] - x0 for p in pts], [p[1] - y0 for p in pts], ".", ms=2, color="#24292f")
        ax3.set_aspect("equal", adjustable="datalim")
        unit = det.get("measurement", "unit not stated")
        ax3.set_xlabel(f"{xs} - min ({unit}, scalar applied)")
        ax3.set_ylabel(f"{ys} - min ({unit}, scalar applied)")
        ax3.set_title("footprint of sampled traces (true aspect, origin at minimum)", fontsize=9)
    elif det.get("corners") and any(x or y for x, y in det["corners"]):
        c = det["corners"]
        x0, y0 = min(p[0] for p in c), min(p[1] for p in c)
        ring = [c[0], c[1], c[3], c[2], c[0]]  # ZGY order: (i0,j0), (iN,j0), (i0,jM), (iN,jM)
        ax3.plot([p[0] - x0 for p in ring], [p[1] - y0 for p in ring], "-o", ms=3, color="#24292f")
        ax3.annotate("first inline, first crossline", (c[0][0] - x0, c[0][1] - y0), fontsize=7)
        ax3.set_aspect("equal", adjustable="datalim")
        ax3.set_xlabel("x - min (file's horizontal unit)")
        ax3.set_ylabel("y - min (file's horizontal unit)")
        ax3.set_title(
            "footprint: the four corner points (true aspect, origin at minimum)", fontsize=9
        )
    else:
        ax3.axis("off")
        ax3.text(0.5, 0.5, "no coordinates", ha="center")

    png = Path(png)
    png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(png, bbox_inches="tight")
    plt.close(fig)
    digest = hashlib.sha256(png.read_bytes()).hexdigest()
    return {"member": png.name, "sha256": digest, "release": RELEASE[rep["class"]]}


def _bytes(key: str) -> str:
    return {"inline": "189-192", "crossline": "193-196", "cdp": "21-24"}[key]
