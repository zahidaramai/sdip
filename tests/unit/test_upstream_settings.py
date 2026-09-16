"""Every environment variable upstream reads is classified, and the classification is true.

**Why (DECISIONS.md D-0087).** The pinned ``segy`` and ``mdio`` read twelve environment
variables; SDIP barred two. One of the other ten, ``SEGY_OVERRIDE_BINARY_HEADER``, was
measured producing a **false PASS**: with it set during ingest and verify, 191 of 192
stored samples were wrong and ``sdip verify`` reported every plane PASS, because writer
and verifier read the source the same wrong way. The survey declaration cannot see an
input that arrives through the environment.

The registry in ``sdip._pins`` is hand-written so importing SDIP does not import MDIO. It
cannot drift silently: these tests prove, against the installed upstream,

* that it names every setting upstream defines and nothing upstream has removed;
* that each variable name really changes the setting — measured by setting it and
  instantiating the upstream model, not read off metadata;
* that each case-sensitivity claim is true in both directions, because ``segy``'s
  settings honour ``segy_override_binary_header`` in lower case and an exact-name guard
  would let it through.
"""

from __future__ import annotations

import importlib

import pytest

from sdip._pins import BAR, BARRED_ENV_VARS, RECORD, RECORDED_ENV_VARS, UPSTREAM_SETTINGS
from sdip.guard.env import check_barred_env_vars, scrub_barred_env_vars
from sdip.guard.upstream_settings import classification_gaps, introspect_upstream_settings

#: A value that is not the field's default, per setting, to show the variable is read.
SAMPLES: dict[tuple[str, str], tuple[str, object]] = {
    ("segy.config.SegyFileSettings", "endianness"): ("little", "little"),
    ("segy.config.SegyFileSettings", "storage_options"): ('{"anon": true}', {"anon": True}),
    ("segy.config.SegyHeaderOverrides", "binary_header"): (
        '{"data_sample_format": 5}',
        {"data_sample_format": 5},
    ),
    ("segy.config.SegyHeaderOverrides", "trace_header"): ('{"inline": 7}', {"inline": 7}),
    ("mdio.core.config.MDIOSettings", "export_cpus"): ("3", 3),
    ("mdio.core.config.MDIOSettings", "import_cpus"): ("3", 3),
    ("mdio.core.config.MDIOSettings", "grid_sparsity_ratio_warn"): ("99", 99.0),
    ("mdio.core.config.MDIOSettings", "grid_sparsity_ratio_limit"): ("99", 99.0),
    ("mdio.core.config.MDIOSettings", "save_segy_file_header"): ("1", 1),
    ("mdio.core.config.MDIOSettings", "raw_headers"): ("1", True),
    ("mdio.core.config.MDIOSettings", "cloud_native"): ("1", True),
    ("mdio.core.config.MDIOSettings", "ignore_checks"): ("1", True),
}


def _model(qualified: str) -> type:
    module, _, name = qualified.rpartition(".")
    return getattr(importlib.import_module(module), name)


def _clear(monkeypatch) -> None:
    import os

    for setting in UPSTREAM_SETTINGS:
        for key in list(os.environ):
            if key.upper() == setting.env.upper():
                monkeypatch.delenv(key)


def test_the_registry_names_exactly_what_upstream_defines():
    """Both directions: nothing unclassified, nothing stale."""
    gaps = classification_gaps()
    assert gaps == {"unclassified": [], "stale": [], "mismatched": []}, gaps


def test_introspection_actually_finds_the_settings_models():
    """NEGATIVE CONTROL for the test above.

    An introspection that finds nothing agrees with any registry.
    """
    discovered, unimportable = introspect_upstream_settings()
    assert unimportable == []
    found = {(s.model, s.field) for s in discovered}
    assert ("segy.config.SegyHeaderOverrides", "binary_header") in found
    assert ("mdio.core.config.MDIOSettings", "ignore_checks") in found
    assert len(found) >= 12


@pytest.mark.parametrize("setting", UPSTREAM_SETTINGS, ids=lambda s: s.env)
def test_the_variable_name_really_changes_the_setting(setting, monkeypatch):
    _clear(monkeypatch)
    raw, expected = SAMPLES[(setting.model, setting.field)]
    model = _model(setting.model)
    assert getattr(model(), setting.field) != expected, "sample equals the default"
    monkeypatch.setenv(setting.env, raw)
    assert getattr(model(), setting.field) == expected


@pytest.mark.parametrize("setting", UPSTREAM_SETTINGS, ids=lambda s: s.env)
def test_the_case_sensitivity_claim_is_true(setting, monkeypatch):
    _clear(monkeypatch)
    raw, expected = SAMPLES[(setting.model, setting.field)]
    monkeypatch.setenv(setting.env.lower(), raw)
    honoured = getattr(_model(setting.model)(), setting.field) == expected
    assert honoured is (not setting.case_sensitive)


def test_the_guard_matches_a_lower_case_segy_variable():
    """The bypass an exact-name guard would allow."""
    env = {"segy_override_binary_header": '{"data_sample_format": 5}'}
    assert [f.name for f in check_barred_env_vars(env)] == ["SEGY_OVERRIDE_BINARY_HEADER"]


def test_the_guard_does_not_invent_a_match_upstream_would_not_honour():
    """MDIO's settings are case-sensitive; a lower-case MDIO name changes nothing upstream."""
    assert check_barred_env_vars({"mdio_ignore_checks": "1"}) == []


def test_every_barred_variable_carries_a_reason_and_the_measured_one_is_barred():
    assert BARRED_ENV_VARS["SEGY_OVERRIDE_BINARY_HEADER"]
    for name in (
        "SEGY_ENDIANNESS",
        "SEGY_OVERRIDE_TRACE_HEADER",
        "MDIO__GRID__SPARSITY_RATIO_LIMIT",
        "MDIO__GRID__SPARSITY_RATIO_WARN",
        "MDIO__IMPORT__CLOUD_NATIVE",
        "MDIO_IGNORE_CHECKS",
        "MDIO__IMPORT__RAW_HEADERS",
    ):
        assert len(BARRED_ENV_VARS[name]) >= 40, name
    assert all(s.action in (BAR, RECORD, "allow") for s in UPSTREAM_SETTINGS)


def test_worker_counts_are_recorded_not_barred():
    """§3.4: worker counts are pinned and recorded on the certificate."""
    assert set(RECORDED_ENV_VARS) == {"MDIO__IMPORT__CPU_COUNT", "MDIO__EXPORT__CPU_COUNT"}


def test_scrub_removes_lower_case_spellings_too():
    env = {"segy_endianness": "little", "PATH": "/bin"}
    assert scrub_barred_env_vars(env) == ["segy_endianness"]
    assert env == {"PATH": "/bin"}
