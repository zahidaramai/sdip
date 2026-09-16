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

    refused = run("verify", "--skip-portability", str(source), str(store))
    assert_clean(refused)
    assert refused.returncode == 2


# --- certify ----------------------------------------------------------------------------


@pytest.mark.slow
def test_certify_reaches_a_bound_certificate_for_an_override_survey(rev0, tmp_path):
    """D47 row 5: ``certify`` could not even parse ``--override``.

    ``certify`` refuses a dirty tree and reads the git state of its working directory, so
    it runs from a fresh, committed repository — the same way the container runbook
    documents it.
    """
    _, source, _ = rev0
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
        *REV0,
        "--certificates",
        str(certs),
        cwd=repo,
    )
    assert_clean(proc)
    assert "[BOUND] declaration" in proc.stdout, proc.stdout + proc.stderr
    [certificate] = list(certs.glob("*.json"))
    payload = json.loads(certificate.read_text())
    assert payload["declaration"]["status"] == "BOUND"
    assert payload["spec_id"].endswith("+segy-rev0-poststack3d@1")
    assert payload["gates"]["G3"] == "PASS"
