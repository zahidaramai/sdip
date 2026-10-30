"""OPEN_DEBTS D46, DECISIONS.md D-0106 - the repo-relative path, through ``sdip certify``.

A certificate records the source and store paths relative to the git working tree that
``certify`` ran in, beside the absolute paths, which stay as provenance. Measured through
the executable (the operating contract's closure rule), on a source committed inside a
throwaway repository whose outputs are ignored, so the tree is clean as ``certify``
requires.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from tests.fixtures.generators.poststack3d import make_poststack3d

pytestmark = [pytest.mark.integration, pytest.mark.slow]

SDIP = str(Path(sys.executable).parent / "sdip")


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=repo, check=True
    )


def test_certify_records_the_repo_relative_path_of_a_source_inside_the_tree(tmp_path):
    repo = tmp_path / "repo"
    (repo / "data").mkdir(parents=True)
    make_poststack3d(repo / "data" / "src.sgy")
    (repo / ".gitignore").write_text("*.mdio/\ncerts/\n")
    _git(repo, "init", "-q")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "fixture")

    proc = subprocess.run(
        [
            SDIP, "certify", "data/src.sgy", "out.mdio",
            "--rss-ceiling-gib", "8.0", "--wall-ceiling-s", "1800",
            "--certificates", "certs",
        ],
        cwd=repo, capture_output=True, text=True, check=False, timeout=900,
    )  # fmt: skip
    assert proc.returncode == 0, proc.stdout + proc.stderr[-2000:]
    [certificate] = list((repo / "certs").glob("*.json"))
    payload = json.loads(certificate.read_text())

    assert payload["source_path_repo_relative"] == "data/src.sgy"
    assert payload["output_path_repo_relative"] == "out.mdio"
    assert payload["source_path"] == str((repo / "data" / "src.sgy").resolve())
    assert payload["git"]["dirty"] is False
