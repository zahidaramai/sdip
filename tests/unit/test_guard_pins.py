"""Guard: binding upstream pins (spec 3.3)."""

from __future__ import annotations

import pytest

from sdip._pins import PINS
from sdip.guard.pins import check_pins


def test_installed_versions_match_the_binding_pins():
    statuses = check_pins()
    assert [s.distribution for s in statuses] == [p.distribution for p in PINS]
    bad = [s.detail for s in statuses if not s.ok]
    assert bad == []


def test_pins_are_exactly_the_two_the_specification_names():
    assert {p.distribution: p.version for p in PINS} == {
        "multidimio": "1.2.1",
        "segy": "0.6.0",
    }


def test_commit_shas_are_full_length_hex():
    for pin in PINS:
        assert len(pin.commit_sha) == 40
        assert all(c in "0123456789abcdef" for c in pin.commit_sha)


def test_sha_verification_is_reported_honestly():
    """SP8. A wheel does not carry the SHA it was built from; never claim otherwise.

    This is open debt D9. The test exists so that a future change which starts
    claiming verification must also change this assertion deliberately.
    """
    for status in check_pins():
        assert status.commit_sha_verified is False
        assert "declared" in status.detail or not status.ok


@pytest.mark.parametrize("distribution", ["multidimio", "segy"])
def test_pin_mismatch_is_detected(distribution, monkeypatch):
    """NEGATIVE CONTROL: a wrong installed version must fail the pin check."""
    import sdip.guard.pins as mod

    real = mod.version

    def fake(name: str) -> str:
        return "0.0.0-not-the-pin" if name == distribution else real(name)

    monkeypatch.setattr(mod, "version", fake)
    statuses = check_pins()
    failed = [s for s in statuses if not s.ok]
    assert [s.distribution for s in failed] == [distribution]
    assert "pin requires exactly" in failed[0].detail


def test_missing_distribution_is_detected(monkeypatch):
    """NEGATIVE CONTROL: an uninstalled pin must fail, not be skipped."""
    from importlib.metadata import PackageNotFoundError

    import sdip.guard.pins as mod

    def fake(name: str) -> str:
        raise PackageNotFoundError(name)

    monkeypatch.setattr(mod, "version", fake)
    statuses = check_pins()
    assert all(not s.ok for s in statuses)
    assert all("is not installed" in s.detail for s in statuses)
