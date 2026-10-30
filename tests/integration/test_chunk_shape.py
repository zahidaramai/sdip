"""DECISIONS.md D-0112 - a declared chunk shape, and the chunk manifest on the certificate.

Measured through the ``sdip`` executable (the operating contract's closure rule).

Both halves. A declared shape lands on disk, the store verifies under that declaration, and
``certify`` - whose closure and G6 re-ingest from the declaration - issues on it, with a
chunk manifest that says the shape was declared. A store handed a declaration that differs
only in its chunk shape is refused (exit 2) in both directions; a shape the template cannot
take, or that is not positive integers, is refused before anything is written. And the
declaration digest of every store written before D-0112 is unchanged.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
import zarr

from sdip.equivalence.certificate import read_chunk_manifest
from sdip.spec.declaration import SurveyDeclaration
from tests.fixtures.generators.poststack3d import make_poststack3d

pytestmark = pytest.mark.integration

SDIP = str(Path(sys.executable).parent / "sdip")
SHAPE = (2, 3, 16)
"""Smaller than the 5 x 6 x 32 fixture on every axis, so edge chunks are partial."""

DIGESTS_BEFORE_D0112 = {
    (1, "PostStack3DTime"): "5bc11b36f001b01f3529afde18e989b3df846d7d03d27f4b387e3a37eace6848",
    (0, "PostStack3DDepth"): "c3093f8cbadf96d72e88f19fa3a36d0bd7ef0cd33811252e53221cc3dc9805a7",
}
"""Measured with the code at ``b2ab188``, before ``chunk_shape`` existed."""


def _sdip(*args: str | Path, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [SDIP, *map(str, args)], capture_output=True, text=True, check=False, cwd=cwd
    )


@pytest.fixture(scope="module")
def stores(tmp_path_factory) -> tuple[Path, Path, Path]:
    root = tmp_path_factory.mktemp("chunks")
    source = make_poststack3d(root / "src.sgy").path
    chunked, default = root / "chunked.mdio", root / "default.mdio"
    for store, extra in ((chunked, ["--chunks", ",".join(map(str, SHAPE))]), (default, [])):
        proc = _sdip("ingest", source, store, *extra)
        assert proc.returncode == 0, proc.stderr[-2000:]
    return source, chunked, default


# --- the declaration -------------------------------------------------------------------


@pytest.mark.parametrize(("revision", "template"), list(DIGESTS_BEFORE_D0112))
def test_a_declaration_without_a_chunk_shape_keeps_its_digest(revision, template):
    declaration = SurveyDeclaration(revision=revision, template=template)
    assert "chunk_shape" not in declaration.canonical()
    assert declaration.sha256() == DIGESTS_BEFORE_D0112[(revision, template)]


def test_a_declared_chunk_shape_is_a_different_declaration():
    plain = SurveyDeclaration(revision=1, template="PostStack3DTime")
    chunked = SurveyDeclaration(revision=1, template="PostStack3DTime", chunk_shape=SHAPE)
    assert chunked.sha256() != plain.sha256()
    assert chunked.canonical()["chunk_shape"] == list(SHAPE)
    assert "chunks 2x3x16" in chunked.summary()


@pytest.mark.parametrize("shape", [(), (0, 4, 4), (-1, 4, 4), (True, 4, 4), (4.0, 4, 4)])
def test_a_chunk_shape_that_is_not_positive_integers_is_refused(shape):
    with pytest.raises(ValueError, match="positive integers"):
        SurveyDeclaration(revision=1, template="PostStack3DTime", chunk_shape=shape)


# --- through the executable -----------------------------------------------------------


def test_the_declared_shape_is_what_the_store_holds(stores):
    _, chunked, default = stores
    group = zarr.open_group(str(chunked), mode="r")
    assert tuple(group["amplitude"].chunks) == SHAPE
    assert tuple(group["headers"].chunks) == SHAPE[:-1]
    assert tuple(zarr.open_group(str(default), mode="r")["amplitude"].chunks) == (128, 128, 128)


def test_the_chunked_store_verifies_under_its_own_declaration(stores):
    source, chunked, _ = stores
    proc = _sdip("verify", source, chunked, "--chunks", "2,3,16", "--skip-portability")
    assert proc.returncode == 0, proc.stdout[-2000:] + proc.stderr[-2000:]


@pytest.mark.parametrize(
    ("store_key", "extra"),
    [("chunked", []), ("default", ["--chunks", "2,3,16"]), ("chunked", ["--chunks", "2,3,8"])],
)
def test_a_declaration_differing_only_in_chunk_shape_is_refused(stores, store_key, extra):
    source, chunked, default = stores
    store = chunked if store_key == "chunked" else default
    proc = _sdip("verify", source, store, *extra, "--skip-portability")
    assert proc.returncode == 2, proc.stdout[-2000:] + proc.stderr[-2000:]
    assert "DeclarationMismatchError" in proc.stderr


def test_a_shape_the_template_cannot_take_is_refused_and_nothing_is_written(stores, tmp_path):
    source, _, _ = stores
    out = tmp_path / "wrong.mdio"
    proc = _sdip("ingest", source, out, "--chunks", "4,4")
    assert proc.returncode == 2, proc.stderr[-2000:]
    assert "ChunkShapeError" in proc.stderr
    assert not out.exists()


@pytest.mark.parametrize("value", ["0,4,4", "-1,4,4", "a,b,c", ""])
def test_a_malformed_chunks_option_is_a_usage_error(stores, tmp_path, value):
    source, _, _ = stores
    out = tmp_path / "bad.mdio"
    proc = _sdip("ingest", source, out, "--chunks", value)
    assert proc.returncode == 2
    assert not out.exists()


# --- the chunk manifest ---------------------------------------------------------------


def test_the_manifest_says_declared_and_lists_every_array_including_nested(stores):
    _, chunked, _ = stores
    declaration = SurveyDeclaration(revision=1, template="PostStack3DTime", chunk_shape=SHAPE)
    manifest = read_chunk_manifest(chunked, declaration)
    assert manifest["source"] == "declared"
    assert manifest["declared"] == list(SHAPE)
    assert manifest["template_default"] == [128, 128, 128]
    assert manifest["default_variable"] == "amplitude"
    assert manifest["default_variable_matches"] is True
    assert manifest["arrays"]["amplitude"] == list(SHAPE)
    group = zarr.open_group(str(chunked), mode="r")
    on_disk = {p for p, n in group.members(max_depth=None) if isinstance(n, zarr.Array)}
    assert set(manifest["arrays"]) == on_disk
    assert any("/" in p for p in on_disk), "the ibm32 raw view's arrays sit inside a group"


def test_the_manifest_says_template_default_for_an_undeclared_store(stores):
    _, _, default = stores
    manifest = read_chunk_manifest(default, SurveyDeclaration(1, "PostStack3DTime"))
    assert manifest["source"] == "template_default"
    assert manifest["declared"] is None
    assert manifest["default_variable_matches"] is True


def test_the_manifest_does_not_claim_a_shape_the_store_does_not_hold(stores):
    _, _, default = stores
    claimed = SurveyDeclaration(revision=1, template="PostStack3DTime", chunk_shape=SHAPE)
    assert read_chunk_manifest(default, claimed)["default_variable_matches"] is False


@pytest.mark.slow
def test_certify_issues_on_a_chunked_store_and_records_its_manifest(tmp_path):
    """Certify re-ingests (closure, G6) from the declaration, so the shape reaches them all."""
    repo = tmp_path / "repo"
    (repo / "data").mkdir(parents=True)
    make_poststack3d(repo / "data" / "src.sgy")
    (repo / ".gitignore").write_text("*.mdio/\ncerts/\n")
    for args in (["init", "-q"], ["add", "-A"], ["commit", "-q", "-m", "fixture"]):
        subprocess.run(
            ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=repo, check=True
        )
    proc = subprocess.run(
        [
            SDIP, "certify", "data/src.sgy", "out.mdio", "--chunks", "2,3,16",
            "--rss-ceiling-gib", "8.0", "--wall-ceiling-s", "1800", "--certificates", "certs",
        ],
        cwd=repo, capture_output=True, text=True, check=False, timeout=900,
    )  # fmt: skip
    assert proc.returncode == 0, proc.stdout[-3000:] + proc.stderr[-2000:]
    [certificate] = list((repo / "certs").glob("*.json"))
    payload = json.loads(certificate.read_text())
    manifest = payload["chunk_manifest"]
    assert manifest["source"] == "declared"
    assert manifest["arrays"]["amplitude"] == list(SHAPE)
    assert manifest["default_variable_matches"] is True
    assert payload["gates"]["G6"] == "PASS"
    assert payload["roundtrip_closure"]["status"] == "PASS"
    assert "chunks 2x3x16" in payload["declaration"]["summary"]
