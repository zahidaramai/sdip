"""P39 run: cut copies of the regenerated P38 F3 VDS, each through the `sdip intake` executable.

    python -I prereg/P39_run.py VDS_DIR OUT_DIR TRACKED_RECEIPT.json COMMIT SDIP_EXE IMAGE

VDS_DIR holds f3_sub.vds and f3_sub_crs.vds from prereg/P38_make_vds.py. Cuts are written into
VDS_DIR; the caller deletes VDS_DIR after the run.
"""

import hashlib
import json
import re
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path

REGION = re.compile(r"^(.*?)\s+size:\s*(\d+)\s+at offset:\s*(\d+)", re.MULTILINE)
TRUNC = {"SDIP_VDS_TRUNCATED", "SDIP_VDS_CONTAINER_INVALID", "SDIP_VDS_INTEGRITY_UNCHECKED"}
CUTS = (
    "store-header",
    "layout",
    "file-table",
    "index-page",
    "half",
    "data",
    "p38-cut",
    "last-byte",
)


def sha(path: Path) -> str:
    """Sha256 of one file, streamed."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def cut_offsets(path: Path, image: str) -> dict:
    """The registered rule, applied to the file's own HueBDS map."""
    text = subprocess.run(  # noqa: S603 - fixed argv built here
        [  # noqa: S607 - docker from PATH, as P38_make_vds.py
            "docker",
            "run",
            "--rm",
            "--platform",
            "linux/amd64",
            "--network",
            "none",
            "--read-only",
            "-v",
            f"{path.parent}:/in:ro",
            "--entrypoint",
            "HueBDS",
            image,
            "check",
            f"/in/{path.name}",
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    regions = [(k.strip(), int(n), int(o)) for k, n, o in REGION.findall(text)]
    size = path.stat().st_size
    if max(o + n for _k, n, o in regions) != size:
        raise SystemExit("the intact map does not end at the file size")

    def mid(pred: Callable[[str], bool], largest: bool) -> int:
        cands = [r for r in regions if pred(r[0])]
        _k, n, o = max(cands, key=lambda r: r[1]) if largest else min(cands, key=lambda r: r[2])
        return o + n // 2

    return {
        "store-header": 16,
        "layout": mid(lambda k: k.endswith("chunk"), False),
        "file-table": mid(lambda k: k == "FileTable", False),
        "index-page": mid(lambda k: k.endswith(("indexpage", "indexpages")), True),
        "half": size // 2,
        "data": mid(lambda k: k.endswith("chunks"), True),
        "p38-cut": size - 1000,
        "last-byte": size - 1,
    }


def run(vds: Path, out: Path, tracked: Path, commit: str, exe: str, image: str) -> None:
    """Every file through the executable; the T gates; the figure."""
    import jsonschema

    schema = json.loads(Path("tests/contracts/geosuite.intake.v1.schema.json").read_text())
    val = jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker())
    src = vds / "f3_sub.vds"
    offsets = cut_offsets(src, image)
    data = src.read_bytes()
    files = [("intact", vds / "f3_sub.vds", None), ("intact-crs", vds / "f3_sub_crs.vds", None)]
    for name in CUTS:
        p = vds / f"cut-{name}.vds"
        p.write_bytes(data[: offsets[name]])
        files.append((name, p, offsets[name]))
    del data
    rows = []
    for label, path, kept in files:
        t0 = time.monotonic()
        proc = subprocess.run(  # noqa: S603 - fixed argv built here
            [
                exe,
                "intake",
                str(path),
                "--upload-id",
                "u-20261117-000000000039",
                "--class",
                "public",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        wall = time.monotonic() - t0
        rep = json.loads(proc.stdout) if proc.returncode == 0 else {}
        codes = rep.get("structural", {}).get("codes", [])
        integ = next(
            (
                f["message"]
                for f in rep.get("findings", [])
                if f["code"] in TRUNC | {"SDIP_VDS_EXTENTS_INSIDE"}
            ),
            None,
        )
        rows.append(
            {
                "label": label,
                "bytes": path.stat().st_size,
                "keptBytes": kept,
                "sha256": sha(path),
                "exit": proc.returncode,
                "verdict": rep.get("verdict"),
                "codes": codes,
                "schema_valid": bool(rep) and not list(val.iter_errors(rep)),
                "integrity": integ,
                "wall_s": round(wall, 2),
            }
        )
        print(
            label,
            kept,
            rows[-1]["verdict"],
            sorted(set(codes) & (TRUNC | {"SDIP_VDS_EXTENTS_INSIDE"})),
            rows[-1]["wall_s"],
            flush=True,
        )
    ctl = [r for r in rows if r["keptBytes"] is None]
    cuts = [r for r in rows if r["keptBytes"] is not None]
    p38 = next(r for r in rows if r["label"] == "p38-cut")
    gates = {
        "T1": all(r["exit"] == 0 and r["schema_valid"] for r in rows),
        "T2": all(
            r["verdict"] == "NEEDS_INPUT"
            and "SDIP_VDS_EXTENTS_INSIDE" in r["codes"]
            and not set(r["codes"]) & TRUNC
            for r in ctl
        ),
        "T3": all(
            r["verdict"] == "QUARANTINE"
            and set(r["codes"]) & {"SDIP_VDS_TRUNCATED", "SDIP_VDS_CONTAINER_INVALID"}
            for r in cuts
        ),
        "T4": "SDIP_VDS_TRUNCATED" in p38["codes"] and "1,000 missing" in (p38["integrity"] or ""),
        "T5": all(r["wall_s"] <= 20 for r in rows),
    }
    tracked.write_text(
        json.dumps(
            {
                "probe": "P39",
                "sdip_commit": commit,
                "image": image,
                "source_bytes": src.stat().st_size,
                "gates": gates,
                "files": rows,
            },
            indent=1,
        )
        + "\n"
    )
    print(json.dumps(gates))
    draw(rows, gates, src.stat().st_size, out / "p39_vds_truncation.png", commit)


def draw(rows: list, gates: dict, size: int, png: Path, commit: str) -> None:
    """Cut point (bytes kept, log axis) against the verdict and the integrity code."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    colours = {
        "PASS": "#1a7f37",
        "NEEDS_INPUT": "#d4a72c",
        "QUARANTINE": "#cf222e",
        "REFUSED": "#6e2d91",
        None: "#57606a",
    }
    order = (
        "SDIP_VDS_TRUNCATED",
        "SDIP_VDS_CONTAINER_INVALID",
        "SDIP_VDS_INTEGRITY_UNCHECKED",
        "SDIP_VDS_EXTENTS_INSIDE",
    )
    png.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(13, 5.6), dpi=120)
    for i, r in enumerate(rows):
        y = len(rows) - 1 - i
        ax.scatter([r["bytes"]], [y], s=90, color=colours[r["verdict"]], zorder=3)
        ax.hlines(y, 1, r["bytes"], color=colours[r["verdict"]], lw=2)
        code = next((c for c in order if c in r["codes"]), "-")
        ax.text(
            size * 4,
            y,
            f"{r['verdict']}  {code}  ({r['wall_s']} s)",
            va="center",
            fontsize=8,
            family="monospace",
        )
    ax.set_yticks(range(len(rows)))
    ax.set_yticklabels(
        [f"{r['label']}  {r['bytes']:,} B" for r in reversed(rows)], family="monospace", fontsize=8
    )
    ax.axvline(size, color="#24292f", lw=0.8, ls="--")
    ax.set_xscale("log")
    ax.set_xlim(1, size * 2000)
    ax.set_xlabel("bytes kept (log scale); dashed line = intact file size")
    ax.set_ylabel("file (cut point)")
    met = " ".join(f"{k}{'+' if v else '-'}" for k, v in gates.items())
    ax.set_title(
        f"P39 VDS truncation through `sdip intake` on F3 sub-volume cuts | gates {met} | "
        f"sdip@{commit[:12]}",
        fontsize=9.5,
    )
    handles = [
        plt.Line2D([], [], marker="o", ls="", color=colours[k])
        for k in ("NEEDS_INPUT", "QUARANTINE")
    ]
    ax.legend(
        handles,
        ["NEEDS_INPUT (intact: CRS question only)", "QUARANTINE (cut detected)"],
        loc="upper center",
        bbox_to_anchor=(0.5, -0.13),
        ncol=2,
        fontsize=8,
    )
    fig.savefig(png, bbox_inches="tight")


if __name__ == "__main__":
    if sys.argv[1] == "--redraw":
        rec = json.loads(Path(sys.argv[2]).read_text())
        draw(rec["files"], rec["gates"], rec["source_bytes"], Path(sys.argv[3]), rec["sdip_commit"])
        raise SystemExit(0)
    run(
        Path(sys.argv[1]),
        Path(sys.argv[2]),
        Path(sys.argv[3]),
        sys.argv[4],
        sys.argv[5],
        sys.argv[6],
    )
