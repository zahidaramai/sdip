"""D9 closed (DECISIONS.md D-0126, GeoSuite D-242): the pinned commit is verified at run time.

Probe P25 found every installed package file of both pinned distributions byte-identical to
the source tree at the declared commit, and committed each file's sha256. At run time the
installed files are compared with that manifest, with no network. ``commit_sha_verified`` is
true only when every file matches, none is missing, none is extra, and the pin is the one the
manifest was made for. Otherwise it is false, and the label stays
``declared-not-runtime-verified``.

Both halves (D-0088): the real environment verifies, and each way the claim can be wrong
turns it off.
"""

from __future__ import annotations

import ast
import hashlib
import json
import socket
from dataclasses import replace
from pathlib import Path

import pytest

import sdip.guard.pins as pins
from sdip._pins import PINS
from sdip.guard import _source_manifest as manifest
from sdip.guard.pins import DECLARED, VERIFIED, attest_commit, check_pins
from sdip.provenance.environment import capture_environment

RECEIPT = Path(manifest.RECEIPT)


def test_the_manifest_is_the_receipt_and_the_receipt_is_the_one_named(repo_root):
    receipt = repo_root / RECEIPT
    raw = receipt.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == manifest.RECEIPT_SHA256
    distributions = json.loads(raw)["distributions"]
    by_name = {"multidimio": "multidimio-1.2.1", "segy": "segy-0.6.0"}
    for name, entry in manifest.SOURCE_MANIFEST.items():
        recorded = distributions[by_name[name]]
        assert recorded["outcome"] == "MATCH"
        assert entry["commit_sha"] == recorded["repository_commit"]
        assert entry["files"] == recorded["per_file_sha256"]


def test_the_manifest_is_made_for_the_binding_pins():
    for pin in PINS:
        entry = manifest.SOURCE_MANIFEST[pin.distribution]
        assert (entry["version"], entry["commit_sha"]) == (pin.version, pin.commit_sha)


def test_the_installed_environment_verifies_its_commits():
    for pin in PINS:
        attestation = attest_commit(pin)
        assert attestation.verified, attestation.reason
        assert attestation.sha_verification == VERIFIED
        assert attestation.checked == len(manifest.SOURCE_MANIFEST[pin.distribution]["files"])
        assert manifest.RECEIPT_SHA256 in attestation.basis
        assert "no network at run time" in attestation.basis


def test_the_check_opens_no_connection(monkeypatch):
    def refuse(*args: object, **kwargs: object) -> None:
        raise AssertionError("the commit attestation tried to open a socket")

    monkeypatch.setattr(socket, "socket", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    assert all(attest_commit(pin).verified for pin in PINS)


def test_the_pin_report_and_the_certificate_say_the_same(repo_root):
    for status in check_pins(lockfile=repo_root / "uv.lock"):
        payload = status.to_json()
        assert status.commit_sha_verified is True
        assert payload["commit_sha_verified"] is True
        assert payload["commit_attestation"]["sha_verification"] == VERIFIED
        assert "source comparison" in status.detail
    for record in capture_environment().to_json()["declared_pins"].values():
        assert record["sha_verification"] == VERIFIED
        assert manifest.RECEIPT_SHA256 in record["sha_verification_basis"]


# --- NEGATIVE CONTROLS: every way the claim can be wrong turns it off --------------------


def _files(name: str) -> dict[str, str]:
    return dict(manifest.SOURCE_MANIFEST[name]["files"])  # type: ignore[arg-type]


def _with_files(monkeypatch, name: str, files: dict[str, str]) -> None:
    patched = dict(manifest.SOURCE_MANIFEST)
    patched[name] = dict(patched[name]) | {"files": files}
    monkeypatch.setattr(pins, "SOURCE_MANIFEST", patched)


def _assert_off(attestation) -> None:
    assert attestation.verified is False
    assert attestation.sha_verification == DECLARED
    assert attestation.basis is None
    assert attestation.reason


@pytest.mark.parametrize("pin", PINS, ids=lambda p: p.distribution)
def test_one_file_that_differs_turns_it_off(monkeypatch, pin):
    files = _files(pin.distribution)
    first = sorted(files)[0]
    files[first] = "0" * 64
    _with_files(monkeypatch, pin.distribution, files)
    attestation = attest_commit(pin)
    _assert_off(attestation)
    assert attestation.mismatched == (first,)


@pytest.mark.parametrize("pin", PINS, ids=lambda p: p.distribution)
def test_a_manifest_file_not_installed_turns_it_off(monkeypatch, pin):
    files = _files(pin.distribution) | {f"{pin.distribution}/not_installed.py": "0" * 64}
    _with_files(monkeypatch, pin.distribution, files)
    attestation = attest_commit(pin)
    _assert_off(attestation)
    assert attestation.missing == (f"{pin.distribution}/not_installed.py",)


@pytest.mark.parametrize("pin", PINS, ids=lambda p: p.distribution)
def test_an_installed_file_the_source_does_not_have_turns_it_off(monkeypatch, pin):
    files = _files(pin.distribution)
    dropped = sorted(files)[-1]
    del files[dropped]
    _with_files(monkeypatch, pin.distribution, files)
    attestation = attest_commit(pin)
    _assert_off(attestation)
    assert attestation.unlisted == (dropped,)


@pytest.mark.parametrize("field", ["version", "commit_sha"])
def test_a_pin_bump_without_a_new_p25_turns_it_off(field):
    pin = PINS[0]
    bumped = replace(pin, **{field: "9.9.9" if field == "version" else "f" * 40})
    attestation = attest_commit(bumped)
    _assert_off(attestation)
    assert "P25" in attestation.reason


def test_a_pin_the_manifest_does_not_know_turns_it_off():
    _assert_off(attest_commit(replace(PINS[0], distribution="not-a-pinned-distribution")))


def test_an_unverified_commit_is_labelled_declared_everywhere(monkeypatch, repo_root):
    files = _files("segy")
    files[sorted(files)[0]] = "0" * 64
    _with_files(monkeypatch, "segy", files)
    segy = next(s for s in check_pins(lockfile=repo_root / "uv.lock") if s.distribution == "segy")
    assert segy.commit_sha_verified is False
    assert segy.to_json()["commit_attestation"]["sha_verification"] == DECLARED
    assert "declared, not verified" in segy.detail
    record = capture_environment().to_json()["declared_pins"]["segy"]
    assert record["sha_verification"] == DECLARED
    assert "sha_verification_basis" not in record


def test_the_manifest_module_is_data_only():
    """No code in the manifest: it is read, never trusted to compute anything."""
    tree = ast.parse(Path(manifest.__file__).read_text(encoding="utf-8"))
    kinds = {type(node).__name__ for node in tree.body}
    assert kinds <= {"Expr", "ImportFrom", "AnnAssign"}, kinds
