"""Figure for the SEG-D intake reader: synthetic rev 2.1 records, correct and corrupted.

    PYTHONPATH=src:. python prereg/intake_segd_figure.py OUT_DIR COMMIT [REAL_DIR]

REAL_DIR (optional) holds public Crescent Valley SEG-D files 1.sgd and 100.sgd (D-0146): they are
added with a cut and a padded copy of 1.sgd made in a temporary folder.
"""

import sys
import tempfile
from pathlib import Path

from sdip.intake import qc_file
from sdip.intake.card import draw_card
from tests.unit.test_intake_segd import b, write_segd


def main(out: Path, commit: str, real: Path | None = None) -> None:
    """One row per case: verdict and codes; one QC card for the correct record."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    tmp = Path(tempfile.mkdtemp())
    first = write_segd(tmp / "one.segd").read_bytes()
    over = write_segd(tmp / "over.segd")
    data = bytearray(over.read_bytes())
    data[72:74] = b(49, 2)
    over.write_bytes(bytes(data))
    cases = [
        ("correct 8058 IEEE, 48 seis + 2 aux", write_segd(tmp / "a.segd")),
        (
            "correct 8036 24-bit, no trace extension",
            write_segd(tmp / "b.segd", fmt=8036, ext_samples=False),
        ),
        ("correct, 960 channels, 6 s", write_segd(tmp / "c.segd", sets=((960, 1),), end_ms=6000)),
        ("correct, two records in one file", write_segd(tmp / "d.segd", tail=first)),
        ("revision 3.1 (descriptors not parsed)", write_segd(tmp / "e.segd", revision=(3, 1))),
        ("last 100 bytes cut", write_segd(tmp / "f.segd", cut=100)),
        ("64 bytes of garbage appended", write_segd(tmp / "g.segd", tail=b"\xee" * 64)),
        ("one channel more declared than written", over),
        ("classed cluster-derived", write_segd(tmp / "h.segd")),
    ]
    if real is not None:
        data = (real / "1.sgd").read_bytes()
        (tmp / "cut.sgd").write_bytes(data[:-1000])
        (tmp / "pad.sgd").write_bytes(data + b"\xee" * 64)
        cases = [
            ("REAL Crescent Valley 1.sgd (CC-BY 4.0)", real / "1.sgd"),
            ("REAL Crescent Valley 100.sgd (one trace fewer)", real / "100.sgd"),
            ("REAL 1.sgd, last 1,000 bytes cut", tmp / "cut.sgd"),
            ("REAL 1.sgd, 64 bytes appended", tmp / "pad.sgd"),
            *cases,
        ]
    colours = {
        "PASS": "#1a7f37",
        "NEEDS_INPUT": "#d4a72c",
        "QUARANTINE": "#cf222e",
        "REFUSED": "#6e2d91",
    }
    fig, ax = plt.subplots(figsize=(14, 0.5 * len(cases) + 1.6), dpi=110)
    n = len(cases)
    for i, (label, path) in enumerate(cases):
        cls = (
            "cluster-derived"
            if "cluster" in label
            else ("public" if label.startswith("REAL") else "synthetic")
        )
        oc = qc_file(
            path, upload_id="u-20261116-000000000038", member=path.name, cls=cls, commit=commit
        )
        rep = oc.report
        if i == 0:
            name = "segd_card_real.png" if real is not None else "segd_card_synthetic.png"
            draw_card(oc, out / name, commit=commit)
        y = n - 1 - i
        ax.text(-0.1, y + 0.4, label, ha="right", va="center", fontsize=8)
        ax.add_patch(plt.Rectangle((0, y), 1.3, 0.8, color=colours[rep["verdict"]]))
        ax.text(0.65, y + 0.4, rep["verdict"], ha="center", va="center", fontsize=7, color="white")
        shown = [
            c
            for c in rep["structural"]["codes"]
            if c not in ("SDIP_SEGD_NO_COORDINATES", "SDIP_NO_MDIO_ROUTE")
        ]
        ax.text(
            1.5,
            y + 0.4,
            f"{rep['structural']['format']:18s} " + " ".join(shown),
            va="center",
            fontsize=7,
            family="monospace",
        )
    ax.set_xlim(-4, 9)
    ax.set_ylim(-0.3, n + 0.3)
    ax.axis("off")
    scope = (
        "2 real public Crescent Valley records + synthetic"
        if real is not None
        else "synthetic records only"
    )
    ax.set_title(
        f"SDIP SEG-D intake reader: {scope}  |  sdip@{commit[:12]}",
        fontsize=10,
    )
    fig.savefig(out / "segd_cases.png", bbox_inches="tight")


if __name__ == "__main__":
    main(Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3]) if len(sys.argv) > 3 else None)
