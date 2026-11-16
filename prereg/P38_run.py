"""P38 run: the VDS path on the generated F3 files; receipt and figure.

PYTHONPATH=src:. python prereg/P38_run.py VDS_DIR OUT_DIR TRACKED_RECEIPT.json COMMIT
"""

import json
import sys
from pathlib import Path

from sdip.intake import file_sha256, qc_file
from sdip.intake.card import draw_card

FILES = ("f3_sub.vds", "f3_sub_crs.vds", "f3_sub_cut.vds")


def run(vds: Path, out: Path, tracked: Path, commit: str) -> None:
    """Every file, the V gates, the figure."""
    import jsonschema

    schema = json.loads(Path("tests/contracts/geosuite.intake.v1.schema.json").read_text())
    val = jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker())
    rows = []
    for name in FILES:
        oc = qc_file(
            vds / name,
            upload_id="u-20261116-000000000038",
            member=name,
            cls="public",
            commit=commit,
        )
        rep = oc.report
        rep["qcCard"] = draw_card(oc, out / "cards" / f"{name}.png", commit=commit)
        axes = {a["name"]: a for a in oc.detail.get("probe", {}).get("axes", [])}
        crs = next((q for q in rep["questions"] if q["code"] == "CRS_UNRESOLVED"), None)
        rows.append(
            {
                "label": name,
                "bytes": rep["file"]["bytes"],
                "sha256": file_sha256(vds / name),
                "verdict": rep["verdict"],
                "codes": rep["structural"]["codes"],
                "schema_valid": not list(val.iter_errors(rep)),
                "dims": oc.detail.get("probe", {}).get("dimensionality"),
                "axes": {k: [a["samples"], a["min"], a["max"], a["unit"]] for k, a in axes.items()},
                "first_crs_source": crs["choices"][0].get("source") if crs else None,
            }
        )
        print(name, rows[-1]["verdict"], rows[-1]["codes"], rows[-1]["axes"], flush=True)
    a, b, c = rows
    want = {
        "Inline": [200, 100.0, 299.0],
        "Crossline": [300, 300.0, 599.0],
        "Sample": [462, 0.0, 1844.0],
    }

    def axes_ok(r: dict) -> bool:
        return r["dims"] == 3 and all(r["axes"].get(k, [None])[:3] == v for k, v in want.items())

    gates = {
        "V1": all(r["schema_valid"] for r in rows),
        "V2": axes_ok(a) and axes_ok(b),
        "V3": a["first_crs_source"] != "VDS SurveyCoordinateSystem CRSWkt"
        and b["first_crs_source"] == "VDS SurveyCoordinateSystem CRSWkt",
        "V4": c["verdict"] == "QUARANTINE",
        "V5": all("SDIP_VDS_INTEGRITY_UNCHECKED" in r["codes"] for r in rows),
    }
    tracked.write_text(
        json.dumps({"probe": "P38", "sdip_commit": commit, "gates": gates, "files": rows}, indent=1)
        + "\n"
    )
    print(json.dumps(gates))
    draw(rows, gates, out / "p38_vds.png", commit)


def draw(rows: list, gates: dict, png: Path, commit: str) -> None:
    """Verdict, axes and codes per file, with the gates in the title."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    colours = {
        "PASS": "#1a7f37",
        "NEEDS_INPUT": "#d4a72c",
        "QUARANTINE": "#cf222e",
        "REFUSED": "#6e2d91",
    }
    fig, ax = plt.subplots(figsize=(15, 3.2), dpi=110)
    n = len(rows)
    for i, r in enumerate(rows):
        y = n - 1 - i
        ax.text(-0.1, y + 0.4, r["label"], ha="right", va="center", family="monospace", fontsize=8)
        ax.add_patch(plt.Rectangle((0, y), 1.3, 0.8, color=colours[r["verdict"]]))
        ax.text(0.65, y + 0.4, r["verdict"], ha="center", va="center", fontsize=7, color="white")
        axes = "  ".join(f"{k} {v[1]:g}-{v[2]:g} {v[3]} ({v[0]})" for k, v in r["axes"].items())
        codes = " ".join(c for c in r["codes"] if c not in ("SDIP_GEOMETRY", "SDIP_NO_MDIO_ROUTE"))
        ax.text(1.5, y + 0.55, axes, va="center", fontsize=7, family="monospace")
        ax.text(1.5, y + 0.2, codes, va="center", fontsize=7, family="monospace", color="#57606a")
    ax.set_xlim(-2.2, 11)
    ax.set_ylim(-0.3, n + 0.2)
    ax.axis("off")
    met = " ".join(f"{k}{'+' if v else '-'}" for k, v in gates.items())
    ax.set_title(
        f"P38 SDIP VDS path (OpenVDS 3.4.9 in a linux/amd64 container, network off) on F3 sub-volumes  |  "
        f"gates {met}  |  sdip@{commit[:12]}",
        fontsize=9.5,
    )
    fig.savefig(png, bbox_inches="tight")


if __name__ == "__main__":
    run(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]), sys.argv[4])
