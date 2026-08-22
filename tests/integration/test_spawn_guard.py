"""spawn-guard regression. Specification §11.1, Appendix A.5.

MDIO's header parser uses a **`spawn`** multiprocessing context. Every entry point that
can trigger ingestion must sit behind ``if __name__ == "__main__":``. Without it the
child interpreter re-imports the calling module, re-executes the ingest, and the pool
dies with ``BrokenProcessPool``.

**Measured, not theoretical.** These tests invoke ingestion as a real script in a real
subprocess, because that is the only way to observe the failure: an in-process test
never spawns anything and would pass on code that dies immediately in production.

Do not delete these. Appendix A.5 records the original failure, and §11.1 exists
because of it.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from tests.fixtures.generators import make_poststack3d

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parents[2]

GUARDED = """
import sys
sys.path.insert(0, {root!r})
from sdip.ingest import ingest

def run():
    return ingest({source!r}, {output!r})

if __name__ == "__main__":
    result = run()
    print("G1", result.g1.status)
    print("FIELDS", result.spec.field_count)
"""

UNGUARDED = """
import sys
sys.path.insert(0, {root!r})
from sdip.ingest import ingest

# No __main__ guard. This is the defect the CI job exists to catch.
result = ingest({source!r}, {output!r})
print("G1", result.g1.status)
"""


def _run_script(body: str, tmp_path: Path, name: str) -> subprocess.CompletedProcess[str]:
    script = tmp_path / name
    script.write_text(body)
    return subprocess.run(
        [sys.executable, str(script)],
        capture_output=True,
        text=True,
        timeout=600,
        cwd=tmp_path,
        check=False,
    )


def test_guarded_script_ingests_successfully(tmp_path):
    """The positive half. Without it, the negative half proves nothing."""
    source = make_poststack3d(tmp_path / "src.sgy").path
    body = GUARDED.format(
        root=str(REPO_ROOT / "src"),
        source=str(source),
        output=str(tmp_path / "out.mdio"),
    )
    result = _run_script(body, tmp_path, "guarded.py")
    assert result.returncode == 0, result.stderr[-3000:]
    assert "G1 PASS" in result.stdout
    assert "FIELDS 97" in result.stdout
    assert (tmp_path / "out.mdio").exists()


def test_unguarded_script_does_not_silently_produce_a_store(tmp_path):
    """NEGATIVE CONTROL: an unguarded entry point must not quietly succeed.

    The failure mode §11.1 names is ``BrokenProcessPool``. What matters for the
    contract is weaker and more durable than that exact exception: an unguarded script
    must not produce a store that looks complete. Asserting the specific exception
    would couple this test to an upstream error type; asserting the *outcome* survives
    a pin bump.
    """
    source = make_poststack3d(tmp_path / "src.sgy").path
    body = UNGUARDED.format(
        root=str(REPO_ROOT / "src"),
        source=str(source),
        output=str(tmp_path / "out.mdio"),
    )
    result = _run_script(body, tmp_path, "unguarded.py")

    if result.returncode == 0:
        pytest.fail(
            "an unguarded entry point completed successfully. Either upstream no "
            "longer uses a spawn context - in which case spec 11.1 and Appendix A.5 "
            "must be re-read and this test replaced with what is true now - or the "
            "guard is being satisfied some other way. Do not delete this test to "
            "make it pass.\n"
            f"stdout: {result.stdout[-1500:]}\nstderr: {result.stderr[-1500:]}"
        )
    combined = result.stdout + result.stderr
    assert "G1 PASS" not in combined or "Error" in combined or "error" in combined
