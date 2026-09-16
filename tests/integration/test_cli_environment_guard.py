"""An environment variable that changes the reading is refused before any byte is read.

**The measurement this pins (DECISIONS.md D-0087).** With
``SEGY_OVERRIDE_BINARY_HEADER='{"data_sample_format": 5}'`` set for ingest and for verify,
an IBM-float source was decoded as IEEE: 191 of 192 stored samples were wrong, and
``sdip verify`` reported all five planes PASS and the declaration BOUND. ``certify`` was not
fooled — G3, closure and G7 failed — but it blamed its own controls, not the variable.

The refusal must come first, name the variable, exit 2 (an environment SDIP will not run
in is not a verdict about data), and apply to every command that reads a source or store.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests.fixtures.generators.poststack3d import make_poststack3d

SDIP = str(Path(sys.executable).parent / "sdip")
STRAY = '{"data_sample_format": 5}'


def run(*args: str, extra_env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith(("SEGY_", "MDIO"))}
    return subprocess.run(
        [SDIP, *args], capture_output=True, text=True, check=False, env=env | extra_env, timeout=900
    )


@pytest.fixture(scope="module")
def clean(tmp_path_factory):
    work = tmp_path_factory.mktemp("env-guard")
    source = make_poststack3d(work / "s.sgy", n_inline=3, n_crossline=4, n_samples=16).path
    store = work / "s.mdio"
    proc = run("ingest", str(source), str(store), extra_env={})
    assert proc.returncode == 0, proc.stderr[-2000:]
    return work, source, store


@pytest.mark.parametrize("spelling", ["SEGY_OVERRIDE_BINARY_HEADER", "segy_override_binary_header"])
def test_verify_refuses_the_variable_that_produced_the_false_pass(clean, spelling):
    _, source, store = clean
    proc = run("verify", "--skip-portability", str(source), str(store), extra_env={spelling: STRAY})
    assert "Traceback" not in proc.stderr
    assert proc.returncode == 2, proc.stdout + proc.stderr
    assert "SEGY_OVERRIDE_BINARY_HEADER" in proc.stderr
    assert "verify: PASS" not in proc.stdout


def test_without_the_variable_the_same_store_still_verifies(clean):
    """The control: the refusal is caused by the variable, not by the store."""
    _, source, store = clean
    proc = run("verify", "--skip-portability", str(source), str(store), extra_env={})
    assert proc.returncode == 0, proc.stdout + proc.stderr


@pytest.mark.parametrize(
    "command",
    [
        ["ingest", "{source}", "{work}/again.mdio"],
        ["export", "{store}", "{work}/back.sgy", "--source", "{source}"],
        ["certify", "{source}", "{work}/cert.mdio", "--certificates", "{work}/certs"],
    ],
    ids=["ingest", "export", "certify"],
)
def test_every_store_command_refuses_before_doing_anything(clean, command):
    work, source, store = clean
    argv = [a.format(work=work, source=source, store=store) for a in command]
    proc = run(*argv, extra_env={"SEGY_ENDIANNESS": "little"})
    assert "Traceback" not in proc.stderr
    assert proc.returncode == 2, proc.stdout + proc.stderr
    assert "SEGY_ENDIANNESS" in proc.stderr
    assert not (work / "again.mdio").exists()
    assert not (work / "back.sgy").exists()


def test_a_recorded_variable_is_not_refused(clean):
    """Worker counts are recorded (spec 3.4), not barred."""
    _, source, store = clean
    proc = run(
        "verify",
        "--skip-portability",
        str(source),
        str(store),
        extra_env={"MDIO__IMPORT__CPU_COUNT": "1"},
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
