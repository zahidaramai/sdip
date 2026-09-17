"""D60 through the real executable: the cases that crashed, now refused cleanly.

Each was measured as a traceback before D-0088. Run as subprocesses because a traceback on
the operator's terminal is the defect, and only the executable shows what reaches it.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import zarr

from tests.fixtures.generators.poststack3d import make_poststack3d
from tests.fixtures.generators.revisions import make_revision_poststack3d

REPO = Path(__file__).resolve().parents[2]
SDIP = str(Path(sys.executable).parent / "sdip")
REV0 = ["--revision", "0", "--override", str(REPO / "overrides" / "segy-rev0-poststack3d.toml")]


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([SDIP, *args], capture_output=True, text=True, check=False, timeout=900)


def test_a_foreign_store_handed_the_wrong_declaration_is_refused_not_a_traceback(tmp_path):
    """D60's measurement: NonSpecFieldError escaped as a traceback."""
    source = make_revision_poststack3d(tmp_path / "r0.sgy", revision=0).path
    store = tmp_path / "r0.mdio"
    assert run("ingest", str(source), str(store), *REV0).returncode == 0
    foreign = tmp_path / "foreign.mdio"
    shutil.copytree(store, foreign)
    group = zarr.open_group(str(foreign), mode="r+")
    kept = {k: v for k, v in dict(group.attrs).items() if not k.startswith("sdip")}
    group.attrs.clear()
    group.attrs.update(kept)

    proc = run("verify", "--skip-portability", "--revision", "0", str(source), str(foreign))
    assert "Traceback" not in proc.stderr, proc.stderr[-1500:]
    assert proc.returncode == 1
    assert "UpstreamRefusal" in proc.stderr
    assert "NonSpecFieldError" in proc.stderr
    assert "--override" in proc.stderr


def test_an_unknown_template_is_refused_by_name_not_a_traceback(tmp_path):
    source = make_poststack3d(tmp_path / "s.sgy", n_inline=3, n_crossline=4, n_samples=16).path
    proc = run("ingest", str(source), str(tmp_path / "s.mdio"), "--template", "NoSuchTemplate")
    assert "Traceback" not in proc.stderr, proc.stderr[-1500:]
    assert proc.returncode == 1
    assert "NoSuchTemplate" in proc.stderr


@pytest.mark.parametrize(
    ("label", "patch"),
    [
        ("truncated", lambda b: b[: 3600 + 100]),
        ("negative interval", lambda b: b[:3216] + b"\xff\x00" + b[3218:]),
    ],
)
def test_verify_runs_the_hostile_input_preflight(tmp_path, label, patch):
    """Verify parsed untrusted files with only the size envelope in front of it."""
    good = make_poststack3d(tmp_path / "good.sgy", n_inline=3, n_crossline=4, n_samples=16).path
    store = tmp_path / "good.mdio"
    assert run("ingest", str(good), str(store)).returncode == 0
    hostile = tmp_path / "hostile.sgy"
    hostile.write_bytes(patch(good.read_bytes()))

    proc = run("verify", "--skip-portability", str(hostile), str(store))
    assert "Traceback" not in proc.stderr, (label, proc.stderr[-1500:])
    assert proc.returncode == 1, label
    assert "UntrustedInputError" in proc.stderr, label
