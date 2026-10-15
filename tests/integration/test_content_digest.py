"""The content digest: two ingests of one source agree; a change of content does not (D-0101).

**Passing half (D-0088), through the ``sdip`` executable.** Across the five store shapes probe
P13 measured, two independent ingests record the same ``sdipContentDigest`` and different
``sdipStoreDigest`` values - the store digest still tells the two stores apart, the content
digest shows they hold the same content. Changing MDIO's root ``createdOn``, the one key P13
found varying, moves the store digest and not the content digest.

**Failing half.** A flipped chunk byte, an edited raw textual header, an edited root attribute
other than ``createdOn``, and a removed array each change the content digest and name the
change. A store written before 1.6.0 reports ``ABSENT`` and does not fail.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import zarr

from sdip.ingest.provenance_marker import ATTR_CONTENT_DIGEST, ATTR_STORE_DIGEST
from sdip.provenance.store_digest import (
    ABSENT,
    MATCH,
    MISMATCH,
    check_content_digest,
    check_store_digest,
)
from tests.fixtures.generators.poststack3d import make_poststack3d
from tests.fixtures.generators.revisions import make_revision_poststack3d
from tests.fixtures.generators.undecodable import make_undecodable_textual_header

pytestmark = pytest.mark.integration

SDIP = str(Path(sys.executable).parent / "sdip")
REPO = Path(__file__).resolve().parents[2]
REV0 = ["--revision", "0", "--override", str(REPO / "overrides" / "segy-rev0-poststack3d.toml")]


def _source(case: str, path: Path) -> tuple[Path, list[str]]:
    if case == "undecodable":
        return make_undecodable_textual_header(path).path, []
    if case == "rev0":
        return make_revision_poststack3d(path, revision=0).path, REV0
    options: dict[str, Any] = {
        "ibm32": {},
        "float32": {"sample_format": "float32"},
        "delay4": {"delay_recording_time": 4},
    }[case]
    return make_poststack3d(path, **options).path, []


def _ingest(source: Path, store: Path, flags: list[str]) -> dict[str, Any]:
    proc = subprocess.run(
        [SDIP, "ingest", str(source), str(store), *flags],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr[-2000:]
    return dict(zarr.open_group(str(store), mode="r").attrs)


@pytest.mark.parametrize("case", ["ibm32", "float32", "delay4", "undecodable", "rev0"])
def test_two_ingests_record_the_same_content_and_different_stores(tmp_path, case):
    source, flags = _source(case, tmp_path / f"{case}.sgy")
    first = _ingest(source, tmp_path / "a.mdio", flags)
    second = _ingest(source, tmp_path / "b.mdio", flags)
    assert first[ATTR_CONTENT_DIGEST]["sha256"] == second[ATTR_CONTENT_DIGEST]["sha256"]
    assert first[ATTR_STORE_DIGEST]["sha256"] != second[ATTR_STORE_DIGEST]["sha256"], (
        "the store digest must still tell two stores apart"
    )
    for store in (tmp_path / "a.mdio", tmp_path / "b.mdio"):
        assert check_content_digest(store).status == MATCH
        assert check_store_digest(store).status == MATCH


@pytest.fixture(scope="module")
def written(tmp_path_factory) -> tuple[Path, Path]:
    work = tmp_path_factory.mktemp("content")
    source, flags = _source("ibm32", work / "src.sgy")
    _ingest(source, work / "clean.mdio", flags)
    return source, work / "clean.mdio"


@pytest.fixture
def copy(written, tmp_path) -> Path:
    target = tmp_path / "copy.mdio"
    shutil.copytree(written[1], target)
    return target


def _set_root_attr(store: Path, key: str, value: Any) -> None:
    zarr.open_group(str(store), mode="r+").attrs.update({key: value})


def test_a_new_creation_time_moves_the_store_digest_and_not_the_content(copy):
    _set_root_attr(copy, "createdOn", "2099-01-01T00:00:00Z")
    assert check_store_digest(copy).status == MISMATCH
    assert check_content_digest(copy).status == MATCH


def test_a_flipped_chunk_byte_changes_the_content(copy):
    chunk = sorted(p for p in (copy / "amplitude").rglob("*") if p.name != "zarr.json")
    payload = bytearray(chunk[-1].read_bytes())
    payload[-1] ^= 0x01
    chunk[-1].write_bytes(bytes(payload))
    result = check_content_digest(copy)
    assert result.status == MISMATCH
    assert "amplitude changed" in result.changed


def test_an_edited_raw_textual_header_changes_the_content(copy):
    node = zarr.open_group(str(copy), mode="r+")["segy_file_header"]
    key = next(k for k in dict(node.attrs) if "text" in k.lower())
    value = str(node.attrs[key])
    node.attrs[key] = ("X" if value[:1] != "X" else "Y") + value[1:]
    assert "segy_file_header changed" in check_content_digest(copy).changed


def test_any_other_root_attribute_is_content(copy):
    _set_root_attr(copy, "name", "SomethingElse")
    result = check_content_digest(copy)
    assert result.status == MISMATCH
    assert "root metadata changed" in result.changed


def test_a_removed_array_changes_the_content(copy):
    del zarr.open_group(str(copy), mode="r+")["cdp_x"]
    assert "cdp_x removed" in check_content_digest(copy).changed


def test_a_store_written_before_the_content_digest_is_absent_not_failed(copy):
    group = zarr.open_group(str(copy), mode="r+")
    attrs = dict(group.attrs)
    attrs.pop(ATTR_CONTENT_DIGEST)
    group.attrs.clear()
    group.attrs.update(attrs)
    result = check_content_digest(copy)
    assert result.status == ABSENT
    assert result.passed
    assert check_store_digest(copy).status == MATCH, "the old digest is unaffected"


def test_verify_reports_both_digests_through_the_executable(written):
    source, store = written
    proc = subprocess.run(
        [SDIP, "verify", "--skip-portability", str(source), str(store)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr[-2000:]
    assert "[MATCH] store" in proc.stdout
    assert "[MATCH] content" in proc.stdout
