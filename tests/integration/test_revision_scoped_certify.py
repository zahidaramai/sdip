"""OPEN_DEBTS D61, owner ruling D-0106 - G3 for a source whose revision word is undefined.

Upstream stores such a source's binary header with one undivided ``segy_revision`` and no
major/minor pair, and its own exporter refuses a store without the pair. G3 is therefore
``ROUNDTRIP-SCOPED`` with the cause named, issued only when both halves are measured: the
source's bytes 3501-3502 hold no defined revision, and the store lacks the pair.

Both halves (D-0088): a sweep of the revision word across defined and undefined values,
each one's export actually attempted, so the scope is shown to match exactly the stores
upstream cannot export - and nothing else - rather than predicted. Then the release
decision through the executable, in both sample formats, as D-0098 was tested.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from sdip.export import export
from sdip.export.roundtrip import REVISION_SCOPE_RULING, revision_scope
from sdip.ingest import ingest
from tests.fixtures.generators.poststack3d import make_poststack3d

pytestmark = pytest.mark.integration

SDIP = str(Path(sys.executable).parent / "sdip")
REPO = Path(__file__).resolve().parents[2]


def _with_revision_word(path: Path, code: int, sample_format: str) -> Path:
    source = make_poststack3d(path, sample_format=sample_format).path
    payload = bytearray(source.read_bytes())
    payload[3500:3502] = code.to_bytes(2, "big")
    source.write_bytes(bytes(payload))
    return source


def _ingest_and_export(tmp_path: Path, code: int) -> tuple[bool, str]:
    source = _with_revision_word(tmp_path / "s.sgy", code, "float32")
    result = ingest(source, tmp_path / "o.mdio")
    scoped = revision_scope(source, tmp_path / "o.mdio") is not None
    try:
        outcome = export(
            tmp_path / "o.mdio", tmp_path / "b.sgy", result.spec.segy_spec, source=source
        ).status
    except Exception as exc:  # the upstream refusal IS the measurement
        outcome = type(exc).__name__
    return scoped, outcome


@pytest.mark.parametrize("code", [0x0300, 0x7FFF, 0xFFFF])
def test_an_undefined_revision_word_is_scoped_exactly_where_no_export_can_be_made(tmp_path, code):
    assert _ingest_and_export(tmp_path, code) == (True, "InvalidMDIOError")


@pytest.mark.parametrize("code", [0x0000, 0x0100, 0x0101])
def test_a_store_upstream_can_export_is_never_scoped(tmp_path, code):
    """A store with the revision pair goes through the ordinary byte-identity check.

    0x0101 is undefined too, but upstream splits it into a pair and exports it. The scope
    keys on the store, not the word.
    """
    assert _ingest_and_export(tmp_path, code) == (False, "PASS")


@pytest.mark.parametrize("code", [0x0200, 0x0201])
def test_a_defined_rev2_word_read_as_rev1_is_not_scoped_and_still_cannot_export(tmp_path, code):
    """Pinned as found (OPEN_DEBTS D68): D-0106 rules on undefined words only.

    A rev 2 or 2.1 word read under a revision 1 declaration also loses the pair, and stays
    a clean refusal at export until it has its own ruling.
    """
    assert _ingest_and_export(tmp_path, code) == (False, "InvalidMDIOError")


def _certify(source: Path, tmp_path: Path) -> tuple[subprocess.CompletedProcess[str], dict]:
    repo = tmp_path / "repo"
    repo.mkdir()
    for args in (
        ["init", "-q"],
        ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "i"],
    ):
        subprocess.run(["git", *args], cwd=repo, check=True)
    certs = tmp_path / "certs"
    proc = subprocess.run(
        [
            SDIP, "certify", str(source), str(tmp_path / "cert.mdio"),
            "--rss-ceiling-gib", "8.0", "--wall-ceiling-s", "1800",
            "--certificates", str(certs),
        ],
        capture_output=True, text=True, check=False, cwd=repo, timeout=900,
    )  # fmt: skip
    [certificate] = list(certs.glob("*.json")) or [None]
    return proc, json.loads(certificate.read_text()) if certificate else {}


def test_an_undefined_revision_word_certifies_scoped_and_release_ready(tmp_path):
    import jsonschema

    source = _with_revision_word(tmp_path / "rev.sgy", 0x7FFF, "float32")
    proc, payload = _certify(source, tmp_path)
    assert proc.returncode == 0, proc.stdout + proc.stderr[-2000:]
    assert "Traceback" not in proc.stderr

    roundtrip = payload["roundtrip"]
    assert payload["gates"]["G3"] == "ROUNDTRIP-SCOPED"
    assert roundtrip["performed"] is False
    assert roundtrip["scoped"]["ruling"] == REVISION_SCOPE_RULING
    assert "0x7fff" in roundtrip["scoped"]["non_conformance"]
    assert payload["roundtrip_closure"] is None
    for control in ("g3_control", "closure_control"):
        assert payload["nonvacuity"][control]["status"] == "NOT_APPLICABLE", control
    for gate in ("G1", "G2", "G4", "G5", "G6", "G7"):
        assert payload["gates"][gate] == "PASS", (gate, payload["gates"])
    assert all(p["status"] == "PASS" for p in payload["planes"].values())

    assert payload["verdict"] == "EQUIVALENT"
    assert payload["release_readiness"]["blocking"] == []
    assert payload["release_readiness"]["release_ready"] is True
    schema = json.loads((REPO / "src/sdip/schema/sdip-certificate-v0.schema.json").read_text())
    jsonschema.validate(payload, schema)


def test_an_ibm32_source_with_an_undefined_revision_word_stays_provisional(tmp_path):
    """D-0106 rules on the export only, not on P2's transform rule, exactly as D-0098."""
    source = _with_revision_word(tmp_path / "ibm.sgy", 0x7FFF, "ibm32")
    proc, payload = _certify(source, tmp_path)
    assert proc.returncode == 1, proc.stdout
    assert payload["gates"]["G3"] == "ROUNDTRIP-SCOPED"
    assert payload["verdict"] == "PROVISIONAL"
    assert payload["release_readiness"]["blocking"] == [
        "a declared transform is not provably invertible on this data"
    ]
