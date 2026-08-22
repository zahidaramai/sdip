"""Shared fixtures.

Note the ``filterwarnings = ["error"]`` setting in ``pyproject.toml``: any warning
reaching pytest fails the suite unless a test opts in explicitly. That is SP6 applied
to our own code, not a style preference.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """An environment mapping with every barred variable removed."""
    from sdip._pins import BARRED_ENV_VARS

    for name in BARRED_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    return dict(os.environ)


@pytest.fixture
def git_repo(tmp_path: Path) -> Iterator[Path]:
    """A throwaway git repository with one commit, clean tree."""
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.invalid"], cwd=tmp_path, check=True
    )
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
    (tmp_path / "a.txt").write_text("a\n")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "seed", "--no-gpg-sign"], cwd=tmp_path, check=True)
    yield tmp_path


@pytest.fixture
def repo_root() -> Path:
    """Root of this repository."""
    return Path(__file__).resolve().parents[1]
