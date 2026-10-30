"""OPEN_DEBTS D16 — which header setting reproduces Appendix A.1's array list.

A.1 lists nine arrays, ``segy_file_header`` among them. Upstream's default
(``save_segy_file_header = 0``) writes no such array. P1 banked A.1 on the same pinned
``multidimio`` 1.2.1, so the default cannot have changed in between: the question is only
which setting the run used. Both halves are measured on the committed A.1-geometry article,
through upstream's own ``segy_to_mdio`` with SDIP's gap-free spec, as P1 ran it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from sdip.ingest.file_headers import file_headers_not_persisted, file_headers_persisted
from sdip.spec.generator import build_gap_free_spec
from tests.fixtures.generators import make_poststack3d

pytestmark = pytest.mark.integration

APPENDIX_A1_ARRAYS = {
    "amplitude", "inline", "crossline", "time", "cdp_x", "cdp_y",
    "trace_mask", "headers", "segy_file_header",
}  # fmt: skip


def _arrays_written(tmp_path: Path, persisted: bool) -> set[str]:
    from mdio import segy_to_mdio
    from mdio.builder.template_registry import get_template

    article = make_poststack3d(tmp_path / "a1.sgy")
    out = tmp_path / "out.mdio"
    with file_headers_persisted() if persisted else file_headers_not_persisted():
        segy_to_mdio(
            segy_spec=build_gap_free_spec(1).segy_spec,
            mdio_template=get_template("PostStack3DTime"),
            input_path=article.path,
            output_path=out,
        )
    return {p.parent.name for p in out.glob("*/zarr.json")}


def test_the_default_setting_does_not_reproduce_appendix_a1(tmp_path):
    arrays = _arrays_written(tmp_path, persisted=False)
    assert arrays == APPENDIX_A1_ARRAYS - {"segy_file_header"}


def test_persisted_file_headers_reproduce_appendix_a1_exactly(tmp_path):
    assert _arrays_written(tmp_path, persisted=True) == APPENDIX_A1_ARRAYS
