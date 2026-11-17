"""P36 driver: run ``sdip intake`` over a local manifest, write the receipts and the figure.

Usage (from the repository root, with the ``intake`` extra or matplotlib on the path)::

    python prereg/P36_intake_matrix.py MANIFEST.json OUT_DIR TRACKED_RECEIPT.json COMMIT

``MANIFEST.json`` is machine-local and never committed: a list of
``{"label", "path", "class", "dataset"}``. Confidential entries carry a generic label.

Writes, under ``OUT_DIR`` (git-ignored): one report and one QC card per file, the full local
receipt, and ``p36_matrix.png``. Writes ``TRACKED_RECEIPT.json`` with the public entries in
full (dataset, file name, bytes, sha256, verdict, format, codes, header bytes) and, for the
confidential set, counts only (P36 "Receipt").
"""

from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path

from sdip.intake import qc_file
from sdip.intake.card import draw_card
from sdip.intake.segy import HEADER_BUDGET

STRUCTURAL_KEYS = {
    "format",
    "version",
    "counts",
    "hasCrs",
    "hasUnits",
    "hasNulls",
    "domain",
    "codes",
}


def _validator(schema_path: Path):  # noqa: ANN202
    import jsonschema

    schema = json.loads(schema_path.read_text())
    return jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker())


def run(manifest: Path, out: Path, tracked: Path, commit: str) -> None:
    """Run every manifest entry; never stop on one file's failure."""
    entries = json.loads(manifest.read_text())
    validator = _validator(Path("tests/contracts/geosuite.intake.v1.schema.json"))
    (out / "reports").mkdir(parents=True, exist_ok=True)
    rows = []
    for k, e in enumerate(entries):
        path = Path(e["path"]).expanduser()
        row = {"label": e["label"], "class": e["class"], "dataset": e.get("dataset", "")}
        try:
            oc = qc_file(
                path,
                upload_id="u-20261116-000000000036",
                member=e["label"] + Path(e["path"]).suffix,
                cls=e["class"],
                commit=commit,
            )
            rep = oc.report
            if rep["verdict"] != "REFUSED":
                rep["qcCard"] = draw_card(
                    oc, out / "cards" / f"{k:03d}-{e['label']}.png", commit=commit
                )
            errors = [err.message for err in validator.iter_errors(rep)]
            (out / "reports" / f"{k:03d}-{e['label']}.json").write_text(json.dumps(rep, indent=1))
            row |= {
                "E1": True,
                "E2": not errors,
                "E3": rep["headerBytesRead"] <= HEADER_BUDGET
                and rep["headerBytesRead"] < rep["file"]["bytes"],
                "E8": set(rep["structural"]) <= STRUCTURAL_KEYS,
                "schema_errors": errors[:3],
                "verdict": rep["verdict"],
                "format": rep["structural"]["format"],
                "codes": rep["structural"]["codes"],
                "header_bytes_read": rep["headerBytesRead"],
                "bytes": rep["file"]["bytes"],
                "sha256": rep["file"]["sha256"],
                "file": path.name,
            }
        except Exception as exc:
            row |= {
                "E1": False,
                "E2": False,
                "E3": False,
                "E8": False,
                "error": "".join(traceback.format_exception_only(exc)).strip()[:300],
            }
        rows.append(row)
        print(
            f"{k:3d} {row['label'][:40]:40s} {row.get('verdict', 'ERROR'):22s} "
            f"{row.get('format', '')}",
            flush=True,
        )
    (out / "p36_local_receipt.json").write_text(json.dumps(rows, indent=1))

    public = [r for r in rows if r["class"] == "public"]
    conf = [r for r in rows if r["class"] != "public"]
    receipt = {
        "probe": "P36",
        "sdip_commit": commit,
        "schema": "geosuite.intake.v1 (GeoGIS 6edead4c, sha256 "
        "f0a3e47a8212859fc9ca36c76ac54943465635eedcbf5dd99a690aee27d7089a)",
        "public": [
            {
                k: r.get(k)
                for k in (
                    "dataset",
                    "file",
                    "bytes",
                    "sha256",
                    "verdict",
                    "format",
                    "codes",
                    "header_bytes_read",
                    "E1",
                    "E2",
                    "E3",
                )
            }
            for r in public
        ],
        "confidential": {
            "files": len(conf),
            "meeting_E1_E2_E3_E8": sum(
                all(r.get(x) for x in ("E1", "E2", "E3", "E8")) for r in conf
            ),
        },
    }
    tracked.write_text(json.dumps(receipt, indent=1) + "\n")
    draw_matrix(rows, out / "p36_matrix.png", commit)


def draw_matrix(rows: list[dict], png: Path, commit: str) -> None:
    """One row per file: verdict, format, gate columns. Confidential rows show structure only."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch

    colours = {
        "PASS": "#1a7f37",
        "PASS_WITH_ASSUMPTIONS": "#4c8c2b",
        "NEEDS_INPUT": "#d4a72c",
        "QUARANTINE": "#cf222e",
        "REFUSED": "#6e2d91",
        "ERROR": "#000000",
    }
    n = len(rows)
    fig, ax = plt.subplots(figsize=(15, 0.26 * n + 2.2), dpi=110)
    for i, r in enumerate(rows):
        y = n - 1 - i
        v = r.get("verdict", "ERROR")
        ax.add_patch(plt.Rectangle((0, y), 1, 0.85, color=colours[v]))
        for j, g in enumerate(("E1", "E2", "E3", "E8")):
            ax.add_patch(
                plt.Rectangle(
                    (1.1 + 0.32 * j, y), 0.28, 0.85, color="#1a7f37" if r.get(g) else "#cf222e"
                )
            )
        label = r["label"] if r["class"] == "public" else f"{r['label']} (confidential)"
        ax.text(-0.1, y + 0.42, label[:60], ha="right", va="center", fontsize=7, family="monospace")
        codes = [
            c
            for c in r.get("codes", [])
            if c not in ("SDIP_GEOMETRY", "CRS_UNRESOLVED", "DOMAIN_UNKNOWN")
        ]
        ax.text(
            2.5,
            y + 0.42,
            f"{r.get('format', r.get('error', ''))[:40]:28s} {' '.join(codes)[:110]}",
            va="center",
            fontsize=6.6,
            family="monospace",
        )
    ax.set_xlim(-4.2, 9.5)
    ax.set_ylim(-0.3, n + 0.6)
    ax.axis("off")
    for j, g in enumerate(("verdict", "E1", "E2", "E3", "E8")):
        ax.text(
            0.5 if j == 0 else 1.24 + 0.32 * (j - 1),
            n + 0.2,
            g,
            ha="center",
            fontsize=7,
            fontweight="bold",
        )
    ax.text(
        2.5,
        n + 0.2,
        "geometry from headers   other codes (CRS/domain questions on every file with coordinates)",
        fontsize=7,
        fontweight="bold",
    )
    ax.legend(
        handles=[Patch(color=c, label=k) for k, c in colours.items() if k != "ERROR"],
        loc="lower right",
        fontsize=7,
        ncol=5,
        bbox_to_anchor=(1.0, -0.06 * 30 / max(n, 30)),
    )
    npub = sum(r["class"] == "public" for r in rows)
    ok = sum(all(r.get(x) for x in ("E1", "E2", "E3", "E8")) for r in rows)
    ax.set_title(
        f"P36 sdip intake (header-only QC) on {n} SEG-Y files "
        f"({npub} public, {n - npub} confidential): "
        f"{ok}/{n} meet E1 report, E2 schema, E3 header budget, E8 structural-only  |  "
        f"sdip@{commit[:12]}",
        fontsize=9.5,
    )
    fig.savefig(png, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    run(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]), sys.argv[4])
