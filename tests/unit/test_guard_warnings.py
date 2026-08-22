"""Guard: SP6 warning ledger.

These tests pin the *measured* behaviour recorded in DECISIONS.md D-0004 against the
binding pins. If a pin bump changes any of it, these fail — which is the point.
"""

from __future__ import annotations

import warnings

import pytest

from sdip.guard.warn import (
    KNOWN_UPSTREAM_SUPPRESSIONS,
    WarningLedger,
    recording_warnings,
)


def test_observable_warnings_are_recorded():
    with recording_warnings(reemit=False) as ledger:
        warnings.warn("observable", UserWarning, stacklevel=1)
    assert [w.message for w in ledger.observed] == ["observable"]
    assert ledger.observed[0].category == "UserWarning"


def test_recorder_is_not_a_swallower():
    """The default re-emits, preserving the exact category and origin."""
    with pytest.warns(DeprecationWarning, match="passed through"):
        with recording_warnings() as ledger:
            warnings.warn("passed through", DeprecationWarning, stacklevel=1)
    assert [w.category for w in ledger.observed] == ["DeprecationWarning"]


def test_warnings_are_not_deduplicated():
    """A warning raised once per trace must be counted once per trace."""
    with recording_warnings(reemit=False) as ledger:
        for _ in range(5):
            warnings.warn("same message", UserWarning, stacklevel=1)
    assert len(ledger.observed) == 5


def test_upstream_suppression_is_detected_and_declared():
    """MEASURED, D-0004. Entering the upstream CM installs a filter SDIP records."""
    from mdio.core.zarr_io import zarr_warnings_suppress_unstable_structs_v3

    with recording_warnings(reemit=False) as ledger:
        with zarr_warnings_suppress_unstable_structs_v3():
            pass

    installed = ledger.suppressions_installed
    assert len(installed) == 1
    assert installed[0].action == "ignore"
    assert installed[0].category == "UnstableSpecificationWarning"
    assert installed[0].known_id == "mdio-1.2.1-unstable-structs-v3"
    assert installed[0].declared
    assert ledger.undeclared_suppressions == []


def test_an_undeclared_suppression_is_flagged():
    """NEGATIVE CONTROL: a suppression SDIP has not read must be flagged UNDECLARED.

    This is the change-detector for a pin bump that introduces a new suppression.
    """
    with recording_warnings(reemit=False) as ledger:
        warnings.filterwarnings(
            "ignore", message="a suppression nobody declared", category=FutureWarning
        )

    assert len(ledger.undeclared_suppressions) == 1
    flagged = ledger.undeclared_suppressions[0]
    assert flagged.known_id is None
    assert flagged.to_json()["status"] == "UNDECLARED"


def test_the_upstream_global_leak_is_contained():
    """MEASURED, D-0004 / OPEN_DEBTS D10.

    Upstream's context managers use filterwarnings without catch_warnings and end in
    `finally: pass`, so the ignore filter leaks process-globally. SDIP must not leave
    the interpreter quieter than it found it.
    """
    from mdio.core.zarr_io import (
        zarr_warnings_suppress_unstable_numcodecs_v3,
        zarr_warnings_suppress_unstable_structs_v3,
    )

    before = len(warnings.filters)
    with recording_warnings(reemit=False):
        with zarr_warnings_suppress_unstable_structs_v3():
            pass
        with zarr_warnings_suppress_unstable_numcodecs_v3():
            pass
    assert len(warnings.filters) == before


def test_upstream_really_does_leak_without_the_guard():
    """NEGATIVE CONTROL for the test above.

    If upstream ever scopes its filters correctly this fails, and the containment
    claim in D-0004 must be re-read rather than assumed still necessary.
    """
    from mdio.core.zarr_io import zarr_warnings_suppress_unstable_structs_v3

    with warnings.catch_warnings():  # restores state for the rest of the suite
        before = len(warnings.filters)
        with zarr_warnings_suppress_unstable_structs_v3():
            pass
        assert len(warnings.filters) == before + 1, (
            "upstream no longer leaks; re-read DECISIONS.md D-0004"
        )


def test_suppressed_warnings_are_genuinely_unobservable():
    """MEASURED, D-0004. Documents why SP6 is detection, not re-raising.

    An outer always+record observes zero suppressed warnings. If this ever starts
    passing warnings through, the SP6 implementation can be simplified — and this
    test failing is how anyone would find out.
    """
    from mdio.core.zarr_io import zarr_warnings_suppress_unstable_structs_v3
    from zarr.errors import UnstableSpecificationWarning

    with recording_warnings(reemit=False) as ledger:
        with zarr_warnings_suppress_unstable_structs_v3():
            warnings.warn(
                "The data type (struct) does not have a Zarr V3 specification.",
                UnstableSpecificationWarning,
                stacklevel=1,
            )
    assert ledger.observed == []


def test_known_suppressions_are_pinned_to_the_pinned_version():
    for entry in KNOWN_UPSTREAM_SUPPRESSIONS:
        assert entry["package"] == "multidimio"
        assert entry["version"] == "1.2.1"
        assert entry["site"]
        assert entry["message_regex"]


def test_known_suppression_regexes_match_the_installed_source():
    """The committed regexes must be the ones actually in the pinned source."""
    import inspect

    import mdio.core.zarr_io as zarr_io

    source = inspect.getsource(zarr_io)
    for entry in KNOWN_UPSTREAM_SUPPRESSIONS:
        if entry["site"].startswith("mdio/core/zarr_io.py"):
            assert entry["message_regex"] in source, entry["id"]


def test_ledger_serialises_for_a_certificate():
    ledger = WarningLedger()
    with recording_warnings(ledger, reemit=False):
        pass
    payload = ledger.to_json()
    assert payload["observed_count"] == 0
    assert payload["undeclared_suppression_count"] == 0
    assert len(payload["known_upstream_suppressions"]) == len(KNOWN_UPSTREAM_SUPPRESSIONS)
    assert "monkeypatching" in payload["sp6_scope_note"]
