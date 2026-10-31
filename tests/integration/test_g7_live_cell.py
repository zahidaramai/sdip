"""D73 (probe P20): G7's controls corrupt a live trace, not grid cell 0.

Both halves (D-0088). A correct store whose first grid cell is padding passes G7; before
P20 five controls wrote that padding cell and G7 failed it. And on a full grid, where the
first live cells ARE cells (0, 0) and (0, 1), the controls write exactly what they wrote
before, so a verdict that passed before cannot move.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pytest
import zarr

from sdip.equivalence.nonvacuity import G7Result, g7
from sdip.ingest import ingest
from tests.fixtures.generators.hostile import build_mutant
from tests.fixtures.generators.poststack3d import make_poststack3d

pytestmark = [pytest.mark.integration]

MOVED = (
    "flipped_header_byte",
    "flipped_sample_bit",
    "flipped_raw_header_byte",
    "corrupted_cdp_coordinate",
    "transposed_traces",
)


def _audit(tmp_path: Path, source: Path) -> tuple[G7Result, np.ndarray]:
    store = tmp_path / "store.mdio"
    built = ingest(source, store)
    result = g7(source, store, built.spec.segy_spec, workdir=tmp_path / "g7")
    mask = np.asarray(zarr.open_group(str(store), mode="r")["trace_mask"][...]).astype(bool)
    return result, mask


def _outcomes(result: G7Result) -> dict[str, Any]:
    return {o.corruption.name: o for o in result.outcomes}


def test_a_correct_store_with_padding_at_cell_zero_passes_g7(tmp_path):
    """P18's mutant 39: a correct 6x6 grid whose cell (0, 0) is padding."""
    source = build_mutant(tmp_path / "src", 39)
    result, mask = _audit(tmp_path, source)
    assert not mask[0, 0], "the fixture must keep cell (0, 0) as padding, or this proves nothing"
    outcomes = _outcomes(result)
    failed = [n for n, o in outcomes.items() if not o.passed]
    assert failed == [], failed
    for name in MOVED:
        target = outcomes[name].target
        assert target, name
        for cell in target if name != "corrupted_cdp_coordinate" else []:
            assert mask[tuple(cell)], f"{name} wrote {cell}, which is padding"


def test_on_a_full_grid_the_controls_write_the_cells_they_always_wrote(tmp_path):
    """Invariance: the first live cells of a full grid are (0, 0) and (0, 1)."""
    source = make_poststack3d(tmp_path / "wf.sgy").path
    result, mask = _audit(tmp_path, source)
    assert mask.all()
    outcomes = _outcomes(result)
    assert all(o.passed for o in outcomes.values())
    for name in MOVED:
        expected = [[0, 0], [0, 1]] if name == "transposed_traces" else [[0, 0]]
        assert outcomes[name].target == expected, name


def test_the_target_is_on_the_certificate(tmp_path):
    source = make_poststack3d(tmp_path / "wf.sgy").path
    result, _ = _audit(tmp_path, source)
    controls = {c["name"]: c for c in result.to_json()["controls"]}
    assert controls["flipped_header_byte"]["target"] == [[0, 0]]
    assert "target" not in controls["flipped_textual_byte"]
