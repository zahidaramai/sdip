"""`certify` on a source whose textual header does not decode: G3 ROUNDTRIP-SCOPED (D-0098).

**Maintainer ruling, closing OPEN_DEBTS D17's open half.** Such a store carries no
``segy_file_header`` variable (D-0055), so no export can be made and whole-file byte
identity is impossible. Until D-0098 ``certify`` stopped at the export with
``RoundTripUnavailableError``; measured on a real legacy survey in P12. Now G3 is
``ROUNDTRIP-SCOPED`` with every offending character named, the three checks that need an
export are ``NOT_APPLICABLE`` with the reason, every other gate runs, and the certificate
can be EQUIVALENT and release-ready.

Measured through the ``sdip`` executable, from a fresh committed repository because
``certify`` refuses a dirty tree. The negative half - that the acceptance does not leak to
any other ``ROUNDTRIP-SCOPED`` or any other unexported store - is in
``tests/unit/test_release_readiness.py`` and ``tests/unit/test_header_scope.py``.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from tests.fixtures.generators.poststack3d import make_poststack3d
from tests.fixtures.generators.undecodable import make_undecodable_textual_header

pytestmark = pytest.mark.integration

SDIP = str(Path(sys.executable).parent / "sdip")
REPO = Path(__file__).resolve().parents[2]


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
            SDIP,
            "certify",
            str(source),
            str(tmp_path / "cert.mdio"),
            "--rss-ceiling-gib",
            "8.0",
            "--wall-ceiling-s",
            "1800",
            "--certificates",
            str(certs),
        ],
        capture_output=True,
        text=True,
        check=False,
        cwd=repo,
        timeout=900,
    )
    [certificate] = list(certs.glob("*.json")) or [None]
    payload = json.loads(certificate.read_text()) if certificate else {}
    return proc, payload


def test_an_undecodable_textual_header_certifies_scoped_and_release_ready(tmp_path):
    import jsonschema

    # IEEE samples, as on the real survey that measured this (P12). An ibm32 source with
    # no export stays PROVISIONAL on P2's transform rule, which D-0098 leaves untouched -
    # see the next test.
    source = make_undecodable_textual_header(tmp_path / "legacy.sgy", sample_format="float32").path
    proc, payload = _certify(source, tmp_path)
    assert proc.returncode == 0, proc.stdout + proc.stderr[-2000:]
    assert "Traceback" not in proc.stderr

    assert payload["gates"]["G3"] == "ROUNDTRIP-SCOPED"
    roundtrip = payload["roundtrip"]
    assert roundtrip["performed"] is False
    assert roundtrip["byte_identical"] is False
    assert roundtrip["scoped"]["ruling"] == "D-0098"
    assert "card " in roundtrip["scoped"]["non_conformance"]
    assert "column " in roundtrip["scoped"]["non_conformance"]

    assert payload["roundtrip_closure"] is None
    for control in ("g3_control", "closure_control"):
        assert payload["nonvacuity"][control]["status"] == "NOT_APPLICABLE", control
    for gate in ("G1", "G2", "G4", "G5", "G6", "G7"):
        assert payload["gates"][gate] == "PASS", (gate, payload["gates"])
    assert all(p["status"] == "PASS" for p in payload["planes"].values())
    assert payload["store_digest"]["status"] == "MATCH"
    assert payload["detected_encoding"]["decode_status"] == "raw_preserved_decode_failed"

    assert payload["verdict"] == "EQUIVALENT"
    readiness = payload["release_readiness"]
    assert readiness["blocking"] == [], readiness["blocking"]
    assert readiness["release_ready"] is True

    schema = json.loads((REPO / "src/sdip/schema/sdip-certificate-v0.schema.json").read_text())
    jsonschema.validate(payload, schema)


def test_an_ibm32_source_without_an_export_stays_provisional(tmp_path):
    """D-0098 rules on the textual header only, not on P2's transform rule.

    An ibm32 decode is not proven invertible without a byte-identical round trip, and that
    is unchanged, so this one is not release-ready, and says why.
    """
    source = make_undecodable_textual_header(tmp_path / "ibm.sgy").path
    proc, payload = _certify(source, tmp_path)
    assert proc.returncode == 1, proc.stdout
    assert payload["gates"]["G3"] == "ROUNDTRIP-SCOPED"
    assert payload["verdict"] == "PROVISIONAL"
    assert payload["release_readiness"]["blocking"] == [
        "a declared transform is not provably invertible on this data"
    ]


@pytest.mark.parametrize("sample_format", ["ibm32", "float32"])
def test_a_decodable_header_round_trips_and_certifies_in_either_format(tmp_path, sample_format):
    """The other half: a conforming source never takes the scoped path, in either format.

    ``float32`` is the permanent control for the defect D-0098 found on the way: G7's
    ``deleted_raw_ibm32_array`` errored on a store with no raw view, so every IEEE source
    certified NON-EQUIVALENT (measured on 1.4.0). It is now not applicable, and named.
    """
    source = make_poststack3d(tmp_path / "plain.sgy", sample_format=sample_format).path
    proc, payload = _certify(source, tmp_path)
    assert proc.returncode == 0, proc.stdout + proc.stderr[-2000:]
    assert payload["gates"]["G3"] == "PASS"
    assert payload["roundtrip"]["performed"] is True
    assert payload["roundtrip"]["byte_identical"] is True
    assert "scoped" not in payload["roundtrip"]
    assert payload["roundtrip_closure"]["status"] == "PASS"
    assert payload["gates"]["G7"] == "PASS"
    not_applicable = {c["name"] for c in payload["nonvacuity"]["controls_not_applicable"]}
    assert ("deleted_raw_ibm32_array" in not_applicable) is (sample_format == "float32")
    assert payload["verdict"] == "EQUIVALENT"
    assert payload["release_readiness"]["release_ready"] is True, payload["release_readiness"]
