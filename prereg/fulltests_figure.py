"""Full-suite outcome per test area, before and after the fixes (D-492 full test, D-531).

    python prereg/fulltests_figure.py BEFORE.xml AFTER.xml OUT.png SUMMARY.json BEFORE_SHA AFTER_SHA

Reads pytest JUnit XML; an area is the directory under tests/ (unit, negative, integration, ...).
"""

import json
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

OUTCOMES = ("passed", "failed", "error", "skipped")


def counts(xml: Path) -> dict[str, Counter]:
    """{area: Counter(outcome)} from one JUnit file."""
    out: dict[str, Counter] = {}
    for case in ET.parse(xml).iter("testcase"):  # noqa: S314 - see the import
        parts = case.get("classname", "").split(".")
        area = parts[1] if len(parts) > 2 and parts[0] == "tests" else "other"
        kids = {c.tag for c in case}
        outcome = (
            "failed"
            if "failure" in kids
            else "error"
            if "error" in kids
            else "skipped"
            if "skipped" in kids
            else "passed"
        )
        out.setdefault(area, Counter())[outcome] += 1
    return out


def main(before: Path, after: Path, png: Path, summary: Path, sha_b: str, sha_a: str) -> None:
    """Draw the two runs side by side per area; write the counts."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    runs = {"before": counts(before), "after": counts(after)}
    areas = sorted(set(runs["before"]) | set(runs["after"]))
    summary.write_text(
        json.dumps(
            {
                k: {a: dict(v.get(a, Counter())) for a in areas} | {"sha": s}
                for (k, v), s in zip(runs.items(), (sha_b, sha_a), strict=True)
            },
            indent=1,
        )
        + "\n"
    )
    colours = {"passed": "#1a7f37", "failed": "#cf222e", "error": "#8250df", "skipped": "#8c959f"}
    fig, axes = plt.subplots(1, 2, figsize=(13, 0.6 * len(areas) + 2.2), dpi=120, sharey=True)
    for ax, (name, run), sha in zip(axes, runs.items(), (sha_b, sha_a), strict=True):
        for y, area in enumerate(areas):
            c = run.get(area, Counter())
            left = 0
            for o in OUTCOMES:
                if c[o]:
                    ax.barh(y, c[o], left=left, color=colours[o])
                    left += c[o]
            ax.text(
                left,
                y,
                "  " + " ".join(f"{o[0]}{c[o]}" for o in OUTCOMES if c[o]),
                va="center",
                fontsize=8,
                family="monospace",
            )
        tot = Counter()
        for c in run.values():
            tot.update(c)
        ax.set_title(
            f"{name} @ {sha[:10]}: " + ", ".join(f"{tot[o]} {o}" for o in OUTCOMES), fontsize=9
        )
        ax.set_xlabel("tests (count)")
        ax.set_xscale("symlog", linthresh=10)
    axes[0].set_yticks(range(len(areas)))
    axes[0].set_yticklabels([f"tests/{a}" for a in areas])
    axes[0].set_ylabel("test area")
    handles = [plt.Rectangle((0, 0), 1, 1, color=colours[o]) for o in OUTCOMES]
    fig.legend(
        handles, OUTCOMES, loc="lower center", ncol=4, fontsize=8, bbox_to_anchor=(0.5, -0.02)
    )
    fig.suptitle(
        f"SDIP full suite (uv run pytest -q via gate_turn) per area, before {sha_b[:10]} "
        f"and after {sha_a[:10]}",
        fontsize=10,
    )
    png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(png, bbox_inches="tight")


if __name__ == "__main__":
    main(
        Path(sys.argv[1]),
        Path(sys.argv[2]),
        Path(sys.argv[3]),
        Path(sys.argv[4]),
        sys.argv[5],
        sys.argv[6],
    )
