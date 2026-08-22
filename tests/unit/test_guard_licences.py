"""Guard: runtime dependency-tree licence scan (spec 3.6 / 9.4).

The regression this file mostly exists to prevent is the one measured in
DECISIONS.md D-0005: a naive substring scan over the ``License`` metadata field flags
pandas, which is BSD-3-Clause, because pandas embeds a 63 KB licence text there.
"""

from __future__ import annotations

import pytest

from sdip.guard.licences import (
    MAX_LICENCE_NAME_CHARS,
    _barred_match,
    check_runtime_licences,
)


def test_runtime_tree_has_no_copyleft():
    scan = check_runtime_licences()
    assert scan.unresolved == []
    assert [r.distribution for r in scan.violations] == []
    assert scan.ok


def test_tree_is_actually_walked():
    """A scan that finds nothing because it walked nothing is not a scan (SP11)."""
    scan = check_runtime_licences()
    names = {r.distribution.lower().replace("_", "-") for r in scan.records}
    assert {"multidimio", "segy", "zarr", "xarray", "numpy", "click"} <= names
    assert len(scan.records) > 30


def test_dev_tooling_is_not_in_the_runtime_tree():
    """pytest, ruff, and mypy are dependency-groups, not Requires-Dist."""
    scan = check_runtime_licences()
    names = {r.distribution.lower() for r in scan.records}
    assert names.isdisjoint({"pytest", "ruff", "mypy", "pytest-cov"})


@pytest.mark.parametrize(
    "declaration",
    [
        "GPL-3.0-only",
        "AGPL-3.0",
        "GNU General Public License v3 (GPLv3)",
        "GNU Affero General Public License v3",
        "gpl-2.0",
    ],
)
def test_copyleft_declarations_are_caught(declaration):
    """NEGATIVE CONTROL: each copyleft spelling must match."""
    assert _barred_match((declaration,)) is not None


@pytest.mark.parametrize(
    "declaration",
    [
        "BSD-3-Clause",
        "MIT",
        "Apache-2.0",
        "MPL-2.0 AND MIT",
        "BSD-2-Clause AND Apache-2.0 WITH LLVM-exception",
        "PSF-2.0",
        "ISC License (ISCL)",
    ],
)
def test_permissive_declarations_are_not_caught(declaration):
    assert _barred_match((declaration,)) is None


def test_lgpl_is_a_distinct_token():
    r"""`\bGPL\b` must not match inside LGPL; seisio is LGPL and is only cited."""
    assert _barred_match(("LGPL-3.0-or-later",)) is None


def test_gpl_compatible_prose_is_not_a_licence_declaration():
    """The exact phrase that makes a naive scan flag pandas."""
    assert _barred_match(("GPL-compatible",)) is None


def test_pandas_is_not_flagged():
    """REGRESSION, DECISIONS.md D-0005.

    pandas 2.3.3 embeds its full 63,416-byte licence file in the ``License`` metadata
    field, including PSF text that discusses GPL compatibility at length. It is
    BSD-3-Clause and must resolve from its classifier instead.
    """
    scan = check_runtime_licences()
    pandas = next(r for r in scan.records if r.distribution.lower() == "pandas")
    assert pandas.ok
    assert pandas.barred_match is None
    assert pandas.evidence_tier == "classifier"


def test_long_license_field_is_not_treated_as_a_declaration():
    from importlib.metadata import distribution

    from sdip.guard.licences import _declarations

    blob = distribution("pandas").metadata.get("License") or ""
    assert len(blob) > MAX_LICENCE_NAME_CHARS
    declarations, tier = _declarations(distribution("pandas"))
    assert tier == "classifier"
    assert all(len(d) <= MAX_LICENCE_NAME_CHARS for d in declarations)


def test_undetermined_licences_are_allowlisted_with_cited_evidence():
    """An entry with no cited evidence is rejected at review (spec 6.4 discipline)."""
    scan = check_runtime_licences()
    for record in scan.records:
        if record.allowlisted:
            assert record.allowlist_reason
            assert len(record.allowlist_reason) > 80


def test_markers_are_evaluated_so_the_walk_invents_nothing():
    """REGRESSION, DECISIONS.md D-0005.

    Without marker evaluation this tree reports colorama, importlib_metadata, and
    inspect2 as missing runtime dependencies. All three are conditional.
    """
    scan = check_runtime_licences()
    assert scan.unresolved == []
    names = {r.distribution.lower().replace("_", "-") for r in scan.records}
    assert names.isdisjoint({"colorama", "importlib-metadata", "inspect2"})


def test_every_record_resolves_or_is_allowlisted():
    scan = check_runtime_licences()
    for record in scan.records:
        assert record.ok, f"{record.distribution}: {record.declarations}"
        assert record.undetermined is (record.evidence_tier == "none")
