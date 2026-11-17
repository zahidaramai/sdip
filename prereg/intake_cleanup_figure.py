"""Bytes fetched and generated for the intake readers, and bytes given back.

Storage Law, D-513 #11.

python prereg/intake_cleanup_figure.py SIZES.json FREE_BEFORE FREE_AFTER OUT.png COMMIT
"""

import json
import sys
from pathlib import Path


def main(sizes: str, before: str, after: str, png: str, commit: str) -> None:
    """One bar per item, deleted; the free-space change measured around the deletion."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    rows = json.loads(Path(sizes).read_text())
    free_b, free_a = int(Path(before).read_text()), int(Path(after).read_text())
    fig, ax = plt.subplots(figsize=(12, 4.6), dpi=110)
    labels = [r["item"] for r in rows]
    mb = [r["bytes"] / 1e6 for r in rows]
    colours = [
        "#0969da"
        if r["item"].startswith("fetched")
        else "#8250df"
        if r["item"].startswith("generated")
        else "#57606a"
        for r in rows
    ]
    ax.barh(labels, mb, color=colours)
    for y, v in enumerate(mb):
        ax.text(v, y, f" {v:,.1f} MB deleted", va="center", fontsize=8)
    ax.invert_yaxis()
    ax.set_xlabel("size (MB, 10^6 bytes)")
    total = sum(r["bytes"] for r in rows) / 1e6
    fetched = sum(r["bytes"] for r in rows if r["item"].startswith("fetched")) / 1e6
    ax.set_title(
        f"SDIP intake lane: {fetched:,.1f} MB fetched (of the 10 GB allowance), "
        f"{total:,.1f} MB deleted in all; "
        f"free space {free_b / 1e9:,.2f} -> {free_a / 1e9:,.2f} GB measured  |  sdip@{commit[:12]}",
        fontsize=9,
    )
    fig.savefig(png, bbox_inches="tight")


if __name__ == "__main__":
    main(*sys.argv[1:6])
