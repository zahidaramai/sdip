"""**Gate G6 — determinism.** `OPEN_DEBTS` D44, `DECISIONS.md` D-0081.

**G6 had no dedicated test until 2026-08-24.** ``g6()`` ran in the certify chain and was
exercised *incidentally* inside the full-chain certificate test — so a defect in it that
the certificate test did not happen to notice would have been caught by nothing. Its CI
gate reported ``NOT_RUN`` because its subject glob ``test_determinism*.py`` matched no
file. **This file is that subject**, which arms the gate without touching the workflow.

The positive leg alone would be worth little: **a comparison that cannot fail is not a
comparison** (**SP11**). So every assertion that G6 *holds* is paired with a control that
makes it *break*, and each control names the level it breaks — chunk bytes, decoded
values, or the array set — because G6 reports those separately and the separation is the
point.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import numpy as np
import pytest
import zarr

from sdip.equivalence.determinism import _compare_run_pair, g6
from sdip.ingest import ingest
from tests.fixtures.generators import make_poststack3d

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def twin_stores(tmp_path_factory) -> tuple[Path, Path, Path]:
    """One source ingested twice. The pair a control perturbs."""
    root = tmp_path_factory.mktemp("g6")
    article = make_poststack3d(root / "src.sgy")
    left, right = root / "left.mdio", root / "right.mdio"
    ingest(article.path, left)
    ingest(article.path, right)
    return article.path, left, right


def _copy(src: Path, dst: Path) -> Path:
    shutil.rmtree(dst, ignore_errors=True)
    shutil.copytree(src, dst)
    return dst


# --- the gate itself, end to end ------------------------------------------------


def test_g6_passes_on_two_independent_ingests(tmp_path):
    """The positive leg: two real ingests of one source agree at both levels."""
    article = make_poststack3d(tmp_path / "src.sgy")
    result = g6(article.path, 1, workdir=tmp_path / "work")

    assert result.status == "PASS", result.summary()
    assert result.runs == 2
    assert result.arrays, "a gate that compared no arrays measured nothing"
    assert result.chunk_divergences == []
    assert result.value_divergences == []
    assert result.first_differing_chunk is None
    assert not result.partial


def test_g6_removes_its_run_directories_but_leaves_the_workdir(tmp_path):
    """Documented behaviour, asserted: the audit cleans up after itself."""
    article = make_poststack3d(tmp_path / "src.sgy")
    work = tmp_path / "work"
    work.mkdir()
    g6(article.path, 1, workdir=work)
    assert work.is_dir()
    assert list(work.glob("run_*.mdio")) == []


# --- controls: each breaks G6 at one level, and names it ------------------------


def test_a_flipped_chunk_byte_is_caught_and_the_chunk_is_named(twin_stores, tmp_path):
    """Byte level. The decoded values may or may not move; the bytes certainly do."""
    _, left, right = twin_stores
    perturbed = _copy(right, tmp_path / "flipped.mdio")
    chunks = sorted(p for p in (perturbed / "amplitude" / "c").rglob("*") if p.is_file())
    assert chunks, "fixture has no amplitude chunk to flip"
    raw = bytearray(chunks[0].read_bytes())
    raw[-1] ^= 0x01
    chunks[0].write_bytes(bytes(raw))

    findings, error = _compare_run_pair(left, perturbed, 0, 1)
    assert error is None
    amplitude = next(f for f in findings if f.name == "amplitude")
    assert not amplitude.chunks_identical, "a flipped byte must be seen at the byte level"
    assert amplitude.first_differing_chunk is not None
    assert not amplitude.passed


def test_a_changed_value_is_caught_at_the_value_level(twin_stores, tmp_path):
    """Value level, written through zarr so the store stays internally coherent."""
    _, left, right = twin_stores
    perturbed = _copy(right, tmp_path / "valued.mdio")
    group = zarr.open_group(str(perturbed), mode="r+")
    volume = np.asarray(group["amplitude"][:])
    cell = tuple(0 for _ in volume.shape)
    volume[cell] = np.float32(volume[cell] + 1.0)
    group["amplitude"][:] = volume

    findings, error = _compare_run_pair(left, perturbed, 0, 1)
    assert error is None
    amplitude = next(f for f in findings if f.name == "amplitude")
    assert not amplitude.values_identical, "a changed sample must be seen at the value level"
    assert not amplitude.passed


def test_a_missing_array_is_an_error_not_a_per_array_finding(twin_stores, tmp_path):
    """The two stores do not even hold the same arrays, so no finding is meaningful.

    G6 says so with an error rather than reporting the arrays that happen to survive —
    a comparison over a subset would report a verdict about a question nobody asked.
    """
    _, left, right = twin_stores
    perturbed = _copy(right, tmp_path / "missing.mdio")
    shutil.rmtree(perturbed / "amplitude")

    findings, error = _compare_run_pair(left, perturbed, 0, 1)
    assert findings == []
    assert error is not None
    assert "do not hold the same arrays" in error
    assert "amplitude" in error


def test_identical_stores_are_reported_identical(twin_stores, tmp_path):
    """The non-vacuity control for the three above.

    Each control asserts a perturbation is *caught*. Without this, all three would pass
    against a comparator that reported everything as different — which would be a
    comparator that has measured nothing, in the shape SP11 exists to catch.
    """
    _, left, _ = twin_stores
    twin = _copy(left, tmp_path / "twin.mdio")

    findings, error = _compare_run_pair(left, twin, 0, 1)
    assert error is None
    assert findings, "no arrays compared"
    assert all(f.passed for f in findings), [
        (f.name, f.chunk_detail, f.value_detail) for f in findings if not f.passed
    ]
