"""P37 run: SDIP's ZGY reader against OpenZGY's, plus the corruption cases; receipt and figure.

    python prereg/P37_run.py ORACLE.json OUT_DIR TRACKED_RECEIPT.json COMMIT LABEL=PATH...

Needs matplotlib for the figure (the ``intake`` extra).
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

from sdip.intake import file_sha256, qc_file
from sdip.intake.card import draw_card

DTYPE = {"float32": "float", "int8": "int8", "int16": "int16"}
FIELDS = ("size", "annotstart", "annotinc", "zstart", "zinc", "corners", "datatype", "projection")


def _mine(det: dict) -> dict:
    info = det["info"]
    return {
        "size": list(info["size"]),
        "annotstart": [float(v) for v in info["orig"][:2]],
        "annotinc": [float(v) for v in info["inc"][:2]],
        "zstart": float(info["orig"][2]),
        "zinc": float(info["inc"][2]),
        "corners": det["corners"],
        "datatype": DTYPE.get(det["datatype"], det["datatype"]),
        "projection": det["strings"]["projection"],
    }


def _same(field: str, a: object, b: object) -> bool:
    if field == "corners":

        def key(c: list) -> list:
            return sorted((round(x, 3), round(y, 3)) for x, y in c)

        return key(a) == key(b)  # type: ignore[arg-type]
    if isinstance(a, float) or isinstance(b, float):
        return math.isclose(float(a), float(b), abs_tol=1e-6)  # type: ignore[arg-type]
    if isinstance(a, list):
        return [float(x) for x in a] == [float(x) for x in b]  # type: ignore[union-attr]
    return a == b


def run(oracle_path: Path, out: Path, tracked: Path, commit: str, items: list[str]) -> None:
    """Every file, every field, every gate."""
    import jsonschema

    schema = json.loads(Path("tests/contracts/geosuite.intake.v1.schema.json").read_text())
    val = jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker())
    oracle = json.loads(oracle_path.read_text())
    rows = []
    for item in items:
        label, path = item.split("=", 1)
        p = Path(path)
        oc = qc_file(
            p, upload_id="u-20261116-000000000037", member=label, cls="public", commit=commit
        )
        rep = oc.report
        if rep["verdict"] != "REFUSED":
            rep["qcCard"] = draw_card(oc, out / "cards" / f"{label}.png", commit=commit)
        row = {
            "label": label,
            "bytes": rep["file"]["bytes"],
            "sha256": file_sha256(p),
            "verdict": rep["verdict"],
            "codes": rep["structural"]["codes"],
            "header_bytes_read": rep["headerBytesRead"],
            "schema_valid": not list(val.iter_errors(rep)),
            "structural": rep["structural"],
        }
        if p.name in oracle and "info" in oc.detail:
            mine = _mine(oc.detail)
            row["fields"] = {f: _same(f, mine[f], oracle[p.name][f]) for f in FIELDS}
        crs = next((q for q in rep["questions"] if q["code"] == "CRS_UNRESOLVED"), None)
        row["first_crs_candidate"] = crs["choices"][0].get("source") if crs else None
        row["questions"] = [q["code"] for q in rep["questions"]]
        row["missing_bricks"] = rep["structural"]["counts"].get("missing_bricks")
        rows.append(row)
        print(label, row["verdict"], row["codes"], row.get("fields"), flush=True)

    intact = [r for r in rows if "fields" in r]
    by = {r["label"]: r for r in rows}
    f3 = by.get("f3_sub.zgy", {})
    gates = {
        "Z1": all(r["schema_valid"] for r in rows),
        "Z2": len(intact) == 6 and all(all(r["fields"].values()) for r in intact),
        "Z3": all(
            not ({"TRUNCATED", "HEADER_INVALID", "SDIP_ZGY_VERSION_UNSUPPORTED"} & set(r["codes"]))
            and r["verdict"] in ("PASS", "PASS_WITH_ASSUMPTIONS", "NEEDS_INPUT")
            for r in intact
        ),
        "Z4": f3.get("structural", {}).get("domain") == "time"
        and f3.get("structural", {}).get("hasUnits") is True
        and f3.get("first_crs_candidate") == "ZGY projection string"
        and "DOMAIN_UNKNOWN" not in f3.get("questions", []),
        "Z5": by.get("f3_sub_cut.zgy", {}).get("verdict") == "QUARANTINE"
        and "TRUNCATED" in by.get("f3_sub_cut.zgy", {}).get("codes", []),
        "Z6": "SDIP_ZGY_MISSING_BRICKS" in by.get("f3_sub_hole.zgy", {}).get("codes", [])
        and by.get("f3_sub_hole.zgy", {}).get("missing_bricks") == 1,
        "Z7": all(r["header_bytes_read"] <= 1 << 20 for r in rows),
    }
    receipt = {
        "probe": "P37",
        "sdip_commit": commit,
        "gates": gates,
        "files": [
            {
                k: r.get(k)
                for k in (
                    "label",
                    "bytes",
                    "sha256",
                    "verdict",
                    "codes",
                    "header_bytes_read",
                    "schema_valid",
                    "fields",
                )
            }
            for r in rows
        ],
    }
    tracked.write_text(json.dumps(receipt, indent=1) + "\n")
    print(json.dumps(gates))
    draw(rows, gates, out / "p37_zgy.png", commit)


def draw(rows: list[dict], gates: dict, png: Path, commit: str) -> None:
    """Fields agreeing with OpenZGY, verdict and codes, per file."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    colours = {
        "PASS": "#1a7f37",
        "NEEDS_INPUT": "#d4a72c",
        "QUARANTINE": "#cf222e",
        "REFUSED": "#6e2d91",
    }
    n = len(rows)
    fig, ax = plt.subplots(figsize=(15, 0.55 * n + 2), dpi=110)
    for i, r in enumerate(rows):
        y = n - 1 - i
        ax.text(-0.1, y + 0.4, r["label"], ha="right", va="center", family="monospace", fontsize=8)
        for j, f in enumerate(FIELDS):
            ok = r.get("fields", {}).get(f)
            ax.add_patch(
                plt.Rectangle(
                    (j * 0.6, y),
                    0.55,
                    0.8,
                    color="#d0d7de" if ok is None else ("#1a7f37" if ok else "#cf222e"),
                )
            )
        ax.add_patch(plt.Rectangle((5.0, y), 1.2, 0.8, color=colours.get(r["verdict"], "black")))
        ax.text(5.6, y + 0.4, r["verdict"], ha="center", va="center", fontsize=7, color="white")
        codes = [c for c in r["codes"] if c not in ("SDIP_GEOMETRY", "SDIP_NO_MDIO_ROUTE")]
        ax.text(6.4, y + 0.4, " ".join(codes), va="center", fontsize=7, family="monospace")
    for j, f in enumerate(FIELDS):
        ax.text(j * 0.6 + 0.27, n + 0.1, f, rotation=35, fontsize=7, ha="left")
    ax.text(5.6, n + 0.1, "verdict", fontsize=7, ha="center")
    ax.text(6.4, n + 0.1, "codes (grey field = no oracle: corrupted copy)", fontsize=7)
    ax.set_xlim(-3.2, 13)
    ax.set_ylim(-0.4, n + 1.4)
    ax.axis("off")
    met = " ".join(f"{k}{'+' if v else '-'}" for k, v in gates.items())
    ax.set_title(
        f"P37 SDIP ZGY header reader vs OpenZGY reader (green = field equal)  |  gates {met}  |  "
        f"sdip@{commit[:12]}",
        fontsize=10,
    )
    fig.savefig(png, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    run(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]), sys.argv[4], sys.argv[5:])
