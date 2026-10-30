"""``sdip receipt`` - the header-receipt contract, DECISIONS.md D-0107, through the executable.

Both halves: a source and the store ingested from it give a receipt whose hashes, cards and
fields are the source's own and whose store checks all MATCH (exit 0); a source with one
flipped header byte, against that same store, does not bind (exit 1). The receipt reads only:
source and store hash the same before and after, and the Markdown it writes is refused where
the contract forbids it.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from sdip.ingest import ingest
from sdip.provenance.header_receipt import KEYWORDS, SCHEMA
from tests.fixtures.generators.poststack3d import make_poststack3d

pytestmark = pytest.mark.integration

SDIP = str(Path(sys.executable).parent / "sdip")


def _run(*args: str | Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [SDIP, "receipt", *map(str, args)], capture_output=True, text=True, check=False
    )


def _tree_sha(path: Path) -> str:
    digest = hashlib.sha256()
    files = [path] if path.is_file() else sorted(p for p in path.rglob("*") if p.is_file())
    for f in files:
        digest.update(f.read_bytes())
    return digest.hexdigest()


@pytest.fixture(scope="module")
def pair(tmp_path_factory) -> tuple[Path, Path]:
    root = tmp_path_factory.mktemp("receipt")
    source = make_poststack3d(root / "data" / "src.sgy", sample_format="float32").path
    ingest(source, root / "store" / "out.mdio")
    return source, root / "store" / "out.mdio"


def test_a_receipt_of_a_source_and_its_store_is_the_sources_own_and_binds(pair, tmp_path):
    source, store = pair
    before = (_tree_sha(source), _tree_sha(store))
    proc = _run(source, store, "--json", "--markdown", tmp_path / "r.md")
    assert proc.returncode == 0, proc.stderr[-2000:]
    receipt = json.loads(proc.stdout)
    raw = source.read_bytes()

    assert receipt["schema"] == SCHEMA
    assert receipt["source"]["sha256"] == hashlib.sha256(raw).hexdigest()
    assert receipt["textual_header"]["sha256"] == hashlib.sha256(raw[:3200]).hexdigest()
    assert receipt["binary_header"]["sha256"] == hashlib.sha256(raw[3200:3600]).hexdigest()
    assert len(receipt["textual_header"]["cards"]) == 40
    fields = {f["bytes"]: f["value"] for f in receipt["binary_header"]["fields"]}
    assert fields["3217-3218"] == int.from_bytes(raw[3216:3218], "big", signed=True)
    assert fields["3225-3226"] == 5, "float32"
    assert set(receipt["mentions"]) == set(KEYWORDS)
    store_block = receipt["store"]
    assert store_block["store_digest"]["status"] == "MATCH"
    assert store_block["content_digest"]["status"] == "MATCH"
    assert store_block["raw_headers_bind"]["status"] == "MATCH"
    assert "EPSG" not in proc.stdout.upper(), "a receipt names no EPSG code"

    assert (_tree_sha(source), _tree_sha(store)) == before, "a receipt reads only"
    markdown = (tmp_path / "r.md").read_text()
    assert receipt["source"]["sha256"] in markdown
    assert "MATCH" in markdown


def test_a_flipped_header_byte_does_not_bind_and_exits_1(pair, tmp_path):
    source, store = pair
    flipped = tmp_path / "flipped.sgy"
    payload = bytearray(source.read_bytes())
    payload[100] ^= 0x01  # one byte of the textual header
    flipped.write_bytes(bytes(payload))
    proc = _run(flipped, store, "--json")
    assert proc.returncode == 1
    assert json.loads(proc.stdout)["store"]["raw_headers_bind"]["status"] == "MISMATCH"


def test_a_source_alone_gives_a_receipt_with_no_store_block(pair):
    proc = _run(pair[0], "--json")
    assert proc.returncode == 0, proc.stderr[-2000:]
    assert "store" not in json.loads(proc.stdout)


def test_markdown_never_overwrites(pair, tmp_path):
    existing = tmp_path / "r.md"
    existing.write_text("keep")
    proc = _run(pair[0], "--markdown", existing)
    assert proc.returncode == 2
    assert existing.read_text() == "keep"


@pytest.mark.parametrize("where", ["source_dir", "store"])
def test_markdown_is_refused_inside_the_source_directory_or_the_store(pair, where):
    source, store = pair
    target = (source.parent if where == "source_dir" else store) / "r.md"
    proc = _run(source, store, "--markdown", target)
    assert proc.returncode == 2
    assert not target.exists()


def test_the_mentions_are_a_keyword_match_and_not_stated_is_their_complement(pair):
    receipt = json.loads(_run(pair[0], "--json").stdout)
    for topic in receipt["not_stated"]:
        assert receipt["mentions"][topic]["cards"] == []
    stated = set(receipt["mentions"]) - set(receipt["not_stated"])
    assert all(receipt["mentions"][t]["cards"] for t in stated)
