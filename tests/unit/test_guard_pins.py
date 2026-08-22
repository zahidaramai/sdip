"""Guard: binding upstream pins (spec 3.3)."""

from __future__ import annotations

import pathlib
from typing import ClassVar

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


# ---------------------------------------------------------------------------
# Artifact hashes and installed-file integrity. OPEN_DEBTS D9 closure.
#
# Three distinct claims, kept distinct on purpose. Collapsing them would let the
# report imply the commit SHA was verified, which it never is.
# ---------------------------------------------------------------------------


def test_lockfile_artifact_hashes_are_read(repo_root):
    from sdip.guard.pins import lockfile_artifact_hashes

    hashes = lockfile_artifact_hashes(repo_root / "uv.lock")
    assert set(hashes) == {"multidimio", "segy"}
    for distribution, artifacts in hashes.items():
        assert artifacts, distribution
        for name, digest in artifacts.items():
            assert digest.startswith("sha256:"), name
            assert len(digest) == len("sha256:") + 64


def test_missing_lockfile_is_not_a_pin_failure(tmp_path):
    """An installed wheel is still checkable against RECORD without a lockfile."""
    from sdip.guard.pins import lockfile_artifact_hashes

    assert lockfile_artifact_hashes(tmp_path / "absent.lock") == {}


def test_installed_files_match_their_record(repo_root):
    statuses = check_pins(lockfile=repo_root / "uv.lock")
    for status in statuses:
        assert status.integrity is not None, status.distribution
        assert status.integrity.ok, status.integrity.mismatched
        assert status.integrity.checked > 0


def test_tampering_with_an_installed_file_is_detected(tmp_path, monkeypatch):
    """NEGATIVE CONTROL: edit a file after install, RECORD must catch it.

    This is the realistic way a pinned dependency stops being what the pin says
    without the version changing - someone edits site-packages to make a gate pass.
    """
    import base64
    import hashlib
    import shutil
    from importlib.metadata import distribution

    from sdip.guard.pins import verify_installed_files

    real = distribution("segy")
    record = next(f for f in real.files if str(f).endswith(".dist-info/RECORD"))
    src_root = pathlib.Path(str(real.locate_file(record))).parent.parent
    shutil.copytree(src_root, tmp_path / "sp", dirs_exist_ok=True)

    victim = tmp_path / "sp" / "segy" / "__init__.py"
    victim.write_text(victim.read_text() + "\n# tampered\n")

    class FakeDist:
        """Minimal stand-in that points RECORD resolution at the tampered copy."""

        files: ClassVar[list] = [record]

        def locate_file(self, name) -> pathlib.Path:
            return tmp_path / "sp" / str(name)

    result = verify_installed_files(FakeDist())
    assert not result.ok
    assert any("__init__.py" in m for m in result.mismatched)
    assert base64 and hashlib  # imports exercised by the helper under test


def test_deleting_an_installed_file_is_detected(tmp_path):
    """NEGATIVE CONTROL: a removed file must not read as passing."""
    import shutil
    from importlib.metadata import distribution

    from sdip.guard.pins import verify_installed_files

    real = distribution("segy")
    record = next(f for f in real.files if str(f).endswith(".dist-info/RECORD"))
    src_root = pathlib.Path(str(real.locate_file(record))).parent.parent
    shutil.copytree(src_root, tmp_path / "sp", dirs_exist_ok=True)
    (tmp_path / "sp" / "segy" / "__init__.py").unlink()

    class FakeDist:
        """Minimal stand-in that points RECORD resolution at the tampered copy."""

        files: ClassVar[list] = [record]

        def locate_file(self, name) -> pathlib.Path:
            return tmp_path / "sp" / str(name)

    result = verify_installed_files(FakeDist())
    assert not result.ok
    assert any("__init__.py" in m for m in result.missing)


def test_commit_sha_is_still_never_claimed_as_verified(repo_root):
    """D9 is NARROWED, not closed. The report must keep saying so."""
    for status in check_pins(lockfile=repo_root / "uv.lock"):
        assert status.commit_sha_verified is False
        payload = status.to_json()
        assert payload["commit_sha_verified"] is False
        assert payload["installed_file_integrity"]["does_not_attest"]


def test_deep_can_be_switched_off(repo_root):
    """The RECORD walk costs ~150 hashes; a caller may skip it."""
    statuses = check_pins(deep=False, lockfile=repo_root / "uv.lock")
    assert all(s.integrity is None for s in statuses)
    assert all(s.ok for s in statuses)
