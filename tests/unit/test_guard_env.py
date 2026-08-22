"""Guard: barred environment variables (spec 9.1).

The negative controls here are the point. A guard that has never been shown to fire
is not a guard (SP11), and these are cheap enough that there is no excuse.
"""

from __future__ import annotations

import pytest

from sdip._pins import BARRED_ENV_VARS
from sdip.guard.env import (
    check_barred_env_vars,
    scan_source_for_barred_assignments,
    scrub_barred_env_vars,
)


def test_clean_environment_yields_no_findings(clean_env):
    assert check_barred_env_vars(clean_env) == []


@pytest.mark.parametrize("name", sorted(BARRED_ENV_VARS))
def test_each_barred_variable_is_detected(clean_env, name):
    """NEGATIVE CONTROL: setting each barred variable must be caught."""
    env = dict(clean_env) | {name: "1"}
    findings = check_barred_env_vars(env)
    assert [f.name for f in findings] == [name]
    assert findings[0].reason


@pytest.mark.parametrize("value", ["", "0", "false", "no"])
def test_presence_alone_fails_regardless_of_value(clean_env, value):
    """A barred variable set to a falsy value is still set.

    SDIP does not model upstream truthiness rules. A variable that is set at all is a
    signal the operator intended to change behaviour.
    """
    env = dict(clean_env) | {"MDIO_IGNORE_CHECKS": value}
    assert [f.name for f in check_barred_env_vars(env)] == ["MDIO_IGNORE_CHECKS"]


def test_all_barred_variables_detected_together(clean_env):
    env = dict(clean_env) | dict.fromkeys(BARRED_ENV_VARS, "1")
    assert {f.name for f in check_barred_env_vars(env)} == set(BARRED_ENV_VARS)


def test_scrub_removes_and_reports(clean_env):
    env = dict(clean_env) | dict.fromkeys(BARRED_ENV_VARS, "1")
    removed = scrub_barred_env_vars(env)
    assert set(removed) == set(BARRED_ENV_VARS)
    assert check_barred_env_vars(env) == []


def test_barred_list_matches_specification():
    """The list is binding. Drift here is a specification violation, not a refactor."""
    assert set(BARRED_ENV_VARS) == {"MDIO_IGNORE_CHECKS", "MDIO__IMPORT__RAW_HEADERS"}


def test_sdip_source_never_sets_a_barred_variable(repo_root):
    """SDIP must not set a barred variable anywhere in its own source or tests."""
    assert scan_source_for_barred_assignments(repo_root / "src") == []
    assert scan_source_for_barred_assignments(repo_root / "tests") == []


@pytest.mark.parametrize(
    "snippet",
    [
        'import os\nos.environ["MDIO_IGNORE_CHECKS"] = "1"\n',
        'import os\nos.environ.setdefault("MDIO_IGNORE_CHECKS", "1")\n',
        'import os\nos.putenv("MDIO__IMPORT__RAW_HEADERS", "1")\n',
        'monkeypatch.setenv("MDIO_IGNORE_CHECKS", "1")\n',
        'import os\nos.environ.update({"MDIO_IGNORE_CHECKS": "1"})\n',
        'from os import environ\nenviron["MDIO_IGNORE_CHECKS"] = "1"\n',
    ],
)
def test_the_assignment_scanner_actually_detects(tmp_path, snippet):
    """NEGATIVE CONTROL. A scanner never shown to fire is not a scanner (SP11)."""
    (tmp_path / "offender.py").write_text(snippet)
    assert scan_source_for_barred_assignments(tmp_path)


@pytest.mark.parametrize(
    "snippet",
    [
        '"""MDIO_IGNORE_CHECKS demotes a gate to a log line."""\n',
        "# never set MDIO__IMPORT__RAW_HEADERS\n",
        'BARRED = {"MDIO_IGNORE_CHECKS": "reason"}\n',
        'import os\nprint(os.environ.get("MDIO_IGNORE_CHECKS"))\n',
    ],
)
def test_prose_and_reads_do_not_trip_the_scanner(tmp_path, snippet):
    """A grep flags all four. Parsing is why this gate survives contact with docs."""
    (tmp_path / "innocent.py").write_text(snippet)
    assert scan_source_for_barred_assignments(tmp_path) == []
