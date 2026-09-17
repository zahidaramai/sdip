"""D47 through the product path: the real ``sdip`` executable, real exit codes, real stderr.

Every closure this defect exposed had been measured one layer below the product — D28's
test read headers with ``SegyFile``, D6's revision 0 leg called the Python API — and every
one was false at the CLI. So these tests run the console script as a subprocess and assert
what an operator sees: the exit code, the verdict line, and the absence of a traceback.

Exit codes: 0 PASS, 1 a failed verdict, 2 an operator error — which a mismatched
declaration is. Reporting it as 1 would tell a script a correct conversion was corrupt.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from tests.fixtures.generators.irregular import make_byte_swapped
from tests.fixtures.generators.revisions import make_revision_poststack3d

REPO = Path(__file__).resolve().parents[2]
SDIP = str(Path(sys.executable).parent / "sdip")
REV0_OVERRIDE = str(REPO / "overrides" / "segy-rev0-poststack3d.toml")
REV0 = ["--revision", "0", "--override", REV0_OVERRIDE]


def run(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [SDIP, *args], capture_output=True, text=True, check=False, cwd=cwd, timeout=900
    )


def assert_clean(proc: subprocess.CompletedProcess[str]) -> None:
    """§3.6: a refusal is a message and a status, never a traceback."""
    assert "Traceback" not in proc.stdout + proc.stderr, proc.stderr[-2000:]


@pytest.fixture(scope="module")
def rev0(tmp_path_factory):
    work = tmp_path_factory.mktemp("cli-rev0")
    source = make_revision_poststack3d(work / "rev0.sgy", revision=0).path
    store = work / "rev0.mdio"
    proc = run("ingest", str(source), str(store), *REV0)
    assert proc.returncode == 0, proc.stderr[-2000:]
    return work, source, store


@pytest.fixture(scope="module")
def little(tmp_path_factory):
    work = tmp_path_factory.mktemp("cli-little")
    source = make_byte_swapped(work / "little.sgy", endianness="little").path
    override = work / "little-endian.toml"
    override.write_text(
        'name = "cli-little-endian"\nversion = "1"\n'
        'evidence = "Synthetic byte-swapped fixture for the D47 CLI tests; not real data."\n'
        'endianness = "little"\n'
    )
    store = work / "little.mdio"
    proc = run("ingest", str(source), str(store), "--override", str(override))
    return work, source, store, override, proc


# --- revision 0 -------------------------------------------------------------------------


def test_verify_with_the_declaration_the_store_was_written_under_passes(rev0):
    _, source, store = rev0
    proc = run("verify", "--skip-portability", str(source), str(store), *REV0)
    assert_clean(proc)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "verify: PASS" in proc.stdout
    assert "[BOUND] declaration" in proc.stdout


def test_verify_under_defaults_is_refused_not_failed(rev0):
    """D47 row 1: this was ``verify: FAIL`` on a byte-correct store."""
    _, source, store = rev0
    proc = run("verify", "--skip-portability", str(source), str(store))
    assert_clean(proc)
    assert proc.returncode == 2
    assert "DeclarationMismatchError" in proc.stderr
    assert "revision 0" in proc.stderr
    assert "segy-rev0-poststack3d@1" in proc.stderr
    assert "verify: FAIL" not in proc.stdout


def test_verify_with_the_revision_but_not_the_override_is_refused_not_a_traceback(rev0):
    """D47 row 2: this was ``NonSpecFieldError`` raised as a traceback."""
    _, source, store = rev0
    proc = run("verify", "--skip-portability", str(source), str(store), "--revision", "0")
    assert_clean(proc)
    assert proc.returncode == 2
    assert "DeclarationMismatchError" in proc.stderr


def test_verify_json_carries_the_binding(rev0):
    _, source, store = rev0
    proc = run("verify", "--skip-portability", "--json", str(source), str(store), *REV0)
    assert proc.returncode == 0, proc.stderr[-2000:]
    block = json.loads(proc.stdout)["declaration"]
    assert block["status"] == "BOUND"
    assert block["recorded_sha256"] == block["sha256"]


def test_export_with_the_declaration_round_trips_byte_identically(rev0):
    """D47 row 4: this was a traceback. G3 is a whole-file SHA-256 comparison."""
    work, source, store = rev0
    proc = run("export", str(store), str(work / "back.sgy"), "--source", str(source), *REV0)
    assert_clean(proc)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "G3: PASS" in proc.stdout


def test_export_without_the_override_is_refused_not_a_traceback(rev0):
    work, source, store = rev0
    proc = run(
        "export", str(store), str(work / "no.sgy"), "--source", str(source), "--revision", "0"
    )
    assert_clean(proc)
    assert proc.returncode == 2
    assert not (work / "no.sgy").exists(), "a refused export must write nothing"


# --- little-endian (D28, regressed by the preflight on 2026-08-23) -----------------------


def test_a_declared_little_endian_file_ingests_through_the_cli(little):
    *_, proc = little
    assert_clean(proc)
    assert proc.returncode == 0, proc.stderr[-2000:]


def test_a_little_endian_store_verifies_under_its_declaration_and_is_refused_without(little):
    _, source, store, override, _ = little
    ok = run("verify", "--skip-portability", str(source), str(store), "--override", str(override))
    assert_clean(ok)
    assert ok.returncode == 0, ok.stdout + ok.stderr
    assert "verify: PASS" in ok.stdout
    # The fixture's revision word is correct: rev 1's 0x0100, stored little-endian as 00 01.
    # Until 1.2.1 this run reported it as "revision 0.1" - the declared byte order never
    # reached Plane 2's revision check (OPEN_DEBTS D62's class).
    assert "file_revision_differs" not in ok.stdout, ok.stdout

    refused = run("verify", "--skip-portability", str(source), str(store))
    assert_clean(refused)
    assert refused.returncode == 2


def test_a_little_endian_file_whose_revision_word_does_disagree_is_still_named(little):
    """The failing half of the assertion above, through the same executable.

    The same file with its revision word zeroed, read under the same declaration: the
    finding is recorded, it does not block, and the verdict is still PASS.
    """
    work, source, _, override, _ = little
    data = bytearray(source.read_bytes())
    data[3500:3502] = b"\x00\x00"
    zeroed = work / "little_zero_word.sgy"
    zeroed.write_bytes(bytes(data))
    store = work / "little_zero_word.mdio"
    declared = ["--override", str(override)]
    assert run("ingest", str(zeroed), str(store), *declared).returncode == 0

    proc = run("verify", "--skip-portability", "--json", str(zeroed), str(store), *declared)
    assert_clean(proc)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    report = json.loads(proc.stdout)
    assert report["verdict"] == "PASS"
    [finding] = report["planes"]["plane_2"]["evidence"]["findings"]
    assert finding["code"] == "file_revision_differs"
    assert finding["file_revision"] == "0.0"
    assert finding["blocks_release"] is False


# --- certify ----------------------------------------------------------------------------


@pytest.mark.parametrize("reading", ["rev0-override-depth", "little-endian-override"])
def test_certify_is_release_ready_for_a_survey_read_under_a_declaration(
    reading, rev0, little, tmp_path
):
    """D47 row 5, then D62: ``certify`` for any reading other than the defaults.

    D47: ``certify`` could not even parse ``--override``. This test then stopped at a BOUND
    certificate with G3 PASS - and was marked ``slow``, which CI's integration gate
    excludes, so it never ran there. Under it, 1.2.0 re-ingested the export for round-trip
    closure under revision 1 and ``PostStack3DTime`` whatever the survey had been
    declared, and every such certificate read EQUIVALENT yet not release-ready, blocked by
    a closure FAIL and a closure-control FAIL on a correct store (OPEN_DEBTS D62, measured
    first on real revision 0 depth surveys). So the assertion is now the one an operator
    cares about: **release ready, nothing blocking**, with both ceilings declared so G5
    runs. Not ``slow``: this is correctness, and it gates in CI.

    ``certify`` refuses a dirty tree and reads the git state of its working directory, so
    it runs from a fresh, committed repository - the same way the container runbook
    documents it.
    """
    if reading == "rev0-override-depth":
        _, source, _ = rev0
        declared = [*REV0, "--template", "PostStack3DDepth"]
    else:
        _, source, _, override, _ = little
        declared = ["--override", str(override)]
    repo = tmp_path / "repo"
    repo.mkdir()
    for args in (
        ["init", "-q"],
        ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "i"],
    ):
        subprocess.run(["git", *args], cwd=repo, check=True)
    certs = tmp_path / "certs"
    proc = run(
        "certify",
        str(source),
        str(tmp_path / "cert.mdio"),
        *declared,
        "--rss-ceiling-gib",
        "8.0",
        "--wall-ceiling-s",
        "1800",
        "--certificates",
        str(certs),
        cwd=repo,
    )
    assert_clean(proc)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "[BOUND] declaration" in proc.stdout, proc.stdout + proc.stderr
    [certificate] = list(certs.glob("*.json"))
    payload = json.loads(certificate.read_text())
    assert payload["declaration"]["status"] == "BOUND"
    if reading == "rev0-override-depth":
        assert payload["spec_id"].endswith("+segy-rev0-poststack3d@1")
    assert payload["gates"]["G3"] == "PASS"
    closure = payload["roundtrip_closure"]
    assert closure["status"] == "PASS", closure["summary"]
    assert closure["only_in_original_store"] == [] and closure["only_in_closure_store"] == []
    # Both files' revision words are correct for their declaration - the little-endian one
    # included - so neither Plane 2 nor closure's Plane 2, which reads the export under the
    # same declaration, has a finding to record.
    assert payload["planes"]["plane_2"]["evidence"]["findings"] == []
    assert closure["planes"]["plane_2"] == "PASS"
    assert closure["plane_evidence"][1]["evidence"]["findings"] == []  # planes run in order
    control = payload["nonvacuity"]["closure_control"]
    assert control["status"] == "PASS", control.get("failure_reasons")
    assert control["baseline_clean"] is True
    assert payload["verdict"] == "EQUIVALENT"
    readiness = payload["release_readiness"]
    assert readiness["blocking"] == [], readiness["blocking"]
    assert readiness["release_ready"] is True
