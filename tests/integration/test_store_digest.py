"""The provenance marker carries a digest of the store, and correct stores MATCH it.

**DECISIONS.md D-0093, issue #1 part (b).** ``sdip ingest`` records a digest of every node
and the root metadata, less the marker's own keys, immediately before the marker is written.
This file is the **passing half** (D-0088): correct stores across every revision the writer
takes MATCH, reading a store does not move its digest, and the two states that are not a
failure - a store that predates the digest, a store SDIP did not write - say so without
failing. The failing half is ``tests/negative/test_store_digest_controls.py``.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import zarr

from sdip.ingest import ingest
from sdip.ingest.provenance_marker import ATTR_STORE_DIGEST, MARKER_KEYS
from sdip.provenance.store_digest import (
    ABSENT,
    FOREIGN,
    MATCH,
    SCHEME,
    check_store_digest,
    compute_store_digest,
)
from sdip.spec import load_override
from tests.fixtures.generators.revisions import make_revision_poststack3d

REPO = Path(__file__).resolve().parents[2]
REV0_OVERRIDE = REPO / "overrides" / "segy-rev0-poststack3d.toml"
SDIP = str(Path(sys.executable).parent / "sdip")


def _ingest(work: Path, revision: float | int) -> tuple[Path, Path]:
    fixture = make_revision_poststack3d(work / f"rev{revision}.sgy", revision=revision)
    store = work / f"rev{revision}.mdio"
    override = load_override(REV0_OVERRIDE) if revision == 0 else None
    ingest(fixture.path, store, revision=revision, override=override)
    return fixture.path, store


@pytest.fixture(scope="module")
def rev1(tmp_path_factory):
    return _ingest(tmp_path_factory.mktemp("digest"), 1)


def _drop_attrs(store: Path, *names: str) -> None:
    group = zarr.open_group(str(store), mode="r+")
    attrs = dict(group.attrs)
    for name in names:
        attrs.pop(name, None)
    group.attrs.clear()
    group.attrs.update(attrs)


@pytest.mark.parametrize("revision", [0, 1])
def test_every_revision_the_writer_takes_matches_its_own_digest(revision, tmp_path):
    """Every revision the pinned writer ingests MATCHes.

    2 and 2.1 are refused upstream before a store exists (``test_p6_revisions.py``), so
    there is no digest to take.
    """
    _, store = _ingest(tmp_path, revision)
    result = check_store_digest(store)
    assert result.status == MATCH, result.describe()
    assert result.passed


def test_the_marker_records_every_array_and_the_root(rev1):
    _, store = rev1
    group = zarr.open_group(str(store), mode="r")
    recorded = dict(group.attrs)[ATTR_STORE_DIGEST]
    assert recorded["scheme"] == SCHEME
    # sdip-store-digest/1 records an array under its path and a group under its path plus
    # "/" (compute_store_digest). D-0110 made the raw view the first nested group: the group
    # node and both of its arrays must be covered.
    expected = {
        str(node.path) + ("/" if isinstance(node, zarr.Group) else "")
        for _, node in group.members(max_depth=None)
    }
    assert set(recorded["nodes"]) == expected
    assert {
        "amplitude_raw_ibm32/",
        "amplitude_raw_ibm32/index",
        "amplitude_raw_ibm32/words",
    } <= expected
    # The raw file headers live in this array's metadata; it must be a covered node.
    assert "segy_file_header" in recorded["nodes"]
    assert len(recorded["sha256"]) == 64


def test_the_digest_excludes_only_the_marker(rev1, tmp_path):
    """Rewriting a marker attribute moves nothing; the marker cannot digest itself."""
    _, store = rev1
    copy = tmp_path / "copy.mdio"
    shutil.copytree(store, copy)
    zarr.open_group(str(copy), mode="r+").attrs.update({"sdipVersion": "0.0.0"})
    assert check_store_digest(copy).status == MATCH
    assert compute_store_digest(copy, marker_keys=MARKER_KEYS) == compute_store_digest(
        store, marker_keys=MARKER_KEYS
    )


def test_a_copy_matches_and_reading_does_not_move_it(rev1, tmp_path):
    _, store = rev1
    copy = tmp_path / "copy.mdio"
    shutil.copytree(store, copy)
    group = zarr.open_group(str(copy), mode="r")
    for _, array in group.arrays():
        array[...]
    assert check_store_digest(copy).status == MATCH


def test_a_store_that_predates_the_digest_is_absent_not_failed(rev1, tmp_path):
    _, store = rev1
    copy = tmp_path / "old.mdio"
    shutil.copytree(store, copy)
    _drop_attrs(copy, ATTR_STORE_DIGEST)
    result = check_store_digest(copy)
    assert result.status == ABSENT
    assert result.passed


def test_a_store_sdip_did_not_write_is_foreign(rev1, tmp_path):
    _, store = rev1
    copy = tmp_path / "foreign.mdio"
    shutil.copytree(store, copy)
    _drop_attrs(copy, *MARKER_KEYS)
    result = check_store_digest(copy)
    assert result.status == FOREIGN
    assert result.passed


def test_verify_reports_match_through_the_executable(rev1):
    """Measured through ``sdip``, not one layer below it (D-0087)."""
    source, store = rev1
    run = subprocess.run(
        [SDIP, "verify", "--skip-portability", str(source), str(store)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert run.returncode == 0, run.stdout + run.stderr
    assert "[MATCH] store" in run.stdout
