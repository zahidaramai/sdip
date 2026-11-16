"""Figure for the RESQML intake reader: resqpy's public example packages and synthetic hostile ones.

PYTHONPATH=src:. python prereg/intake_resqml_figure.py RESQPY_EXAMPLE_DIR OUT_DIR COMMIT
"""

import shutil
import sys
import tempfile
from pathlib import Path

from sdip.intake import qc_file
from sdip.intake.card import draw_card
from tests.unit.test_intake_resqml import crs_xml, write_epc


def main(examples: Path, out: Path, commit: str) -> None:
    """One row per package: verdict, format and codes."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    tmp = Path(tempfile.mkdtemp())
    alone = tmp / "alone"
    alone.mkdir()
    shutil.copy(examples / "block.epc", alone / "block.epc")
    cases = [
        ("resqpy block.epc + block.h5 (public)", examples / "block.epc", "public"),
        ("resqpy s_bend.epc + s_bend.h5 (public)", examples / "s_bend.epc", "public"),
        ("resqpy tic_tac_toe.epc + .h5 (public)", examples / "tic_tac_toe.epc", "public"),
        ("resqpy block.epc without its .h5", alone / "block.epc", "public"),
        (
            "synthetic, EPSG stated",
            write_epc(tmp / "a.epc", crs=crs_xml(epsg="23031")),
            "synthetic",
        ),
        (
            "synthetic, member ../evil.xml",
            write_epc(tmp / "b.epc", extra={"../evil.xml": b"<a/>"}),
            "synthetic",
        ),
        ("synthetic, symbolic link member", write_epc(tmp / "c.epc", symlink=True), "synthetic"),
        (
            "synthetic, XML entity",
            write_epc(tmp / "d.epc", extra={"x.xml": b'<!DOCTYPE a [<!ENTITY e "x">]><a/>'}),
            "synthetic",
        ),
        (
            "synthetic, 50 MB of zeros (bomb ratio)",
            write_epc(tmp / "e.epc", extra={"z.bin": bytes(50_000_000)}),
            "synthetic",
        ),
    ]
    colours = {
        "PASS": "#1a7f37",
        "NEEDS_INPUT": "#d4a72c",
        "QUARANTINE": "#cf222e",
        "REFUSED": "#6e2d91",
    }
    n = len(cases)
    fig, ax = plt.subplots(figsize=(15, 0.5 * n + 1.6), dpi=110)
    for i, (label, path, cls) in enumerate(cases):
        oc = qc_file(
            path, upload_id="u-20261116-000000000039", member=path.name, cls=cls, commit=commit
        )
        rep = oc.report
        if i == 0:
            draw_card(oc, out / "resqml_card_block.png", commit=commit)
        y = n - 1 - i
        ax.text(-0.1, y + 0.4, label, ha="right", va="center", fontsize=8)
        ax.add_patch(plt.Rectangle((0, y), 1.3, 0.8, color=colours[rep["verdict"]]))
        ax.text(0.65, y + 0.4, rep["verdict"], ha="center", va="center", fontsize=7, color="white")
        c = rep["structural"]["counts"]
        what = (
            f"cells {c.get('grid_cells', 0)} objects {c.get('objects', 0)}"
            if "objects" in c
            else ""
        )
        shown = [
            k
            for k in rep["structural"]["codes"]
            if k not in ("SDIP_GEOMETRY", "SDIP_NO_MDIO_ROUTE")
        ]
        ax.text(
            1.5,
            y + 0.4,
            f"{rep['structural']['format']:11s} {what:24s} " + " ".join(shown),
            va="center",
            fontsize=7,
            family="monospace",
        )
    ax.set_xlim(-4.2, 10)
    ax.set_ylim(-0.3, n + 0.3)
    ax.axis("off")
    ax.set_title(
        f"SDIP RESQML intake reader: resqpy public examples and hostile packages  |  sdip@{commit[:12]}",
        fontsize=10,
    )
    fig.savefig(out / "resqml_cases.png", bbox_inches="tight")


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3])
