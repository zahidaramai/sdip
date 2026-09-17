"""D58 through the executable: a zarr setting that changes the store refuses the run first.

Measured before D-0088: with ``ZARR_DEFAULT_ZARR_FORMAT=2`` ``sdip ingest`` let MDIO write a Zarr
v2 store and only noticed afterwards, through an unrelated refusal about dimension names.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests.fixtures.generators.poststack3d import make_poststack3d

SDIP = str(Path(sys.executable).parent / "sdip")


def run(args: list[str], home: Path, extra: dict[str, str]) -> subprocess.CompletedProcess[str]:
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith(("ZARR_", "DASK_"))}
    return subprocess.run(
        [SDIP, *args],
        capture_output=True,
        text=True,
        check=False,
        timeout=900,
        env=env | {"HOME": str(home)} | extra,
    )


@pytest.fixture
def source(tmp_path: Path) -> Path:
    return make_poststack3d(tmp_path / "s.sgy", n_inline=3, n_crossline=4, n_samples=16).path


def test_a_store_format_change_is_refused_before_anything_is_written(tmp_path, source):
    out = tmp_path / "s.mdio"
    proc = run(["ingest", str(source), str(out)], tmp_path, {"ZARR_DEFAULT_ZARR_FORMAT": "2"})
    assert "Traceback" not in proc.stderr
    assert proc.returncode == 2, proc.stderr[-1200:]
    assert "default_zarr_format" in proc.stderr
    assert "ZARR_DEFAULT_ZARR_FORMAT" in proc.stderr
    assert not out.exists()


def test_the_same_setting_in_a_config_file_is_refused_and_the_file_is_named(tmp_path, source):
    config = tmp_path / "zarr.yaml"
    config.write_text("default_zarr_format: 2\n")
    out = tmp_path / "s.mdio"
    proc = run(["ingest", str(source), str(out)], tmp_path, {"ZARR_CONFIG": str(config)})
    assert proc.returncode == 2, proc.stderr[-1200:]
    assert str(config) in proc.stderr
    assert not out.exists()


def test_a_recorded_setting_does_not_refuse(tmp_path, source):
    proc = run(
        ["ingest", str(source), str(tmp_path / "s.mdio")],
        tmp_path,
        {"ZARR_ASYNC__CONCURRENCY": "2"},
    )
    assert proc.returncode == 0, proc.stderr[-1200:]
