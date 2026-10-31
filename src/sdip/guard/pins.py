"""Upstream pin verification. Spec section 3.3.

The pins are binding and they are pinned *together*: the ``ibm32`` header fix
straddles the ``segy`` 0.6.0 boundary. A version bump invalidates every certificate
issued under the previous pin.

Three separate claims, and this module keeps them separate because collapsing them
would overstate what is known (**SP8**):

1. **Version** — verified exactly against the installed distribution metadata.
2. **Artifact** — the sha256 of the wheel and sdist as recorded in ``uv.lock``.
   ``uv sync --frozen`` refuses to install anything whose bytes do not hash to this,
   so it is enforced at install time; it is read here and recorded on the certificate.
   It attests **the artifact**, not the commit.
3. **Installed files** — every file's sha256 recomputed and compared to the
   ``RECORD`` manifest the wheel shipped. This catches a site-packages edit made after
   installation, which is the realistic way a pinned dependency stops being what the
   pin says without the version changing.

4. **Commit** - every installed package file compared, offline, with probe P25's committed
   manifest of the source tree at the pinned commit (``sdip.guard._source_manifest``,
   ``DECISIONS.md`` D-0126, GeoSuite D-242). A wheel does not carry the SHA it was built
   from, so this is an attestation **by source comparison**: P25 found the files identical
   to the commit's source, and the run checks that the installed files are still those
   files. ``commit_sha_verified`` is true only when every file matches, none is missing,
   none is extra, and the pin is the one the manifest was made for. Anything else, a pin
   bump without a re-run P25 included, reports ``declared-not-runtime-verified``.

Every result states which claim it is making.
"""

from __future__ import annotations

import base64
import csv
import hashlib
import tomllib
from dataclasses import dataclass, field
from importlib.metadata import Distribution, PackageNotFoundError, version
from importlib.metadata import distribution as _distribution
from pathlib import Path

from sdip._pins import PINS, Pin
from sdip.guard._source_manifest import RECEIPT, RECEIPT_SHA256, SOURCE_MANIFEST

_CHUNK = 1 << 20

VERIFIED = "source-comparison-verified"
"""``sha_verification`` when the installed files are the pinned commit's source (P25)."""

DECLARED = "declared-not-runtime-verified"
"""``sha_verification`` otherwise: the commit SHA is declared, and nothing checked it."""


@dataclass(frozen=True, slots=True)
class FileIntegrity:
    """Result of recomputing an installed distribution against its own RECORD."""

    checked: int
    mismatched: tuple[str, ...]
    missing: tuple[str, ...]
    unhashed: int

    @property
    def ok(self) -> bool:
        """True when every hashed file in RECORD matches what is on disk."""
        return not self.mismatched and not self.missing

    def to_json(self) -> dict[str, object]:
        """Certificate-shaped mapping."""
        return {
            "files_checked": self.checked,
            "mismatched": list(self.mismatched),
            "missing": list(self.missing),
            "unhashed_entries": self.unhashed,
            "attests": "installed files match the wheel's own RECORD manifest",
            "does_not_attest": "that the wheel was built from the declared commit",
        }


@dataclass(frozen=True, slots=True)
class CommitAttestation:
    """Whether the installed files are the pinned commit's source, by P25's manifest."""

    verified: bool
    checked: int
    mismatched: tuple[str, ...] = ()
    missing: tuple[str, ...] = ()
    unlisted: tuple[str, ...] = ()
    reason: str = ""

    @property
    def sha_verification(self) -> str:
        """The certificate's label for this commit."""
        return VERIFIED if self.verified else DECLARED

    @property
    def basis(self) -> str | None:
        """What the verification rests on, or ``None`` when there is none."""
        if not self.verified:
            return None
        return f"source comparison P25 {RECEIPT} sha256 {RECEIPT_SHA256}, no network at run time"

    def to_json(self) -> dict[str, object]:
        """Certificate-shaped mapping."""
        return {
            "sha_verification": self.sha_verification,
            "basis": self.basis,
            "files_checked": self.checked,
            "mismatched": list(self.mismatched),
            "missing": list(self.missing),
            "unlisted": list(self.unlisted),
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class PinStatus:
    """Result of checking one binding pin against the installed environment."""

    distribution: str
    expected_version: str
    installed_version: str | None
    declared_commit_sha: str
    commit_sha_verified: bool
    ok: bool
    artifact_hashes: dict[str, str] = field(default_factory=dict)
    integrity: FileIntegrity | None = None
    attestation: CommitAttestation | None = None

    @property
    def detail(self) -> str:
        """Human-readable one-line explanation of this status."""
        if self.installed_version is None:
            return f"{self.distribution} is not installed (expected {self.expected_version})"
        if self.installed_version != self.expected_version:
            return (
                f"{self.distribution} {self.installed_version} installed, "
                f"pin requires exactly {self.expected_version}"
            )
        if self.integrity is not None and not self.integrity.ok:
            broken = list(self.integrity.mismatched) + list(self.integrity.missing)
            return (
                f"{self.distribution} {self.installed_version} does not match its own "
                f"RECORD manifest: {', '.join(broken[:3])}"
            )
        integrity = self.integrity.checked if self.integrity else 0
        commit = (
            "verified by source comparison (P25)"
            if self.commit_sha_verified
            else "declared, not verified"
        )
        return (
            f"{self.distribution} {self.installed_version} matches pin; "
            f"{integrity} installed files match RECORD; "
            f"commit SHA {self.declared_commit_sha[:12]} {commit}"
        )

    def to_json(self) -> dict[str, object]:
        """Certificate-shaped mapping for the ``env.declared_pins`` block."""
        return {
            "distribution": self.distribution,
            "expected": self.expected_version,
            "installed": self.installed_version,
            "declared_commit_sha": self.declared_commit_sha,
            "commit_sha_verified": self.commit_sha_verified,
            "artifact_hashes": dict(self.artifact_hashes),
            "installed_file_integrity": (self.integrity.to_json() if self.integrity else None),
            "commit_attestation": (self.attestation.to_json() if self.attestation else None),
            "ok": self.ok,
        }


def lockfile_artifact_hashes(lockfile: str | Path = "uv.lock") -> dict[str, dict[str, str]]:
    """Return ``{distribution: {artifact_filename: "sha256:..."}}`` from ``uv.lock``.

    These are the bytes ``uv sync --frozen`` refuses to deviate from at install time.
    Reading them here puts the enforced value on the certificate rather than leaving it
    implicit in a lockfile nobody quotes.

    Returns an empty mapping when the lockfile is absent - an installed wheel is still
    checkable against its RECORD, and a missing lockfile is not a pin failure.
    """
    path = Path(lockfile)
    if not path.is_file():
        return {}
    data = tomllib.loads(path.read_text())
    wanted = {pin.distribution for pin in PINS}
    out: dict[str, dict[str, str]] = {}
    for package in data.get("package", []):
        name = package.get("name")
        if name not in wanted:
            continue
        artifacts: dict[str, str] = {}
        sdist = package.get("sdist") or {}
        if sdist.get("hash"):
            artifacts[str(sdist.get("url", "sdist")).rsplit("/", 1)[-1]] = sdist["hash"]
        for wheel in package.get("wheels", []):
            if wheel.get("hash"):
                artifacts[str(wheel.get("url", "wheel")).rsplit("/", 1)[-1]] = wheel["hash"]
        out[name] = artifacts
    return out


def _record_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(_CHUNK):
            digest.update(block)
    return "sha256=" + base64.urlsafe_b64encode(digest.digest()).decode().rstrip("=")


def verify_installed_files(dist: Distribution) -> FileIntegrity:
    """Recompute every hashed file in ``dist``'s RECORD and compare it to disk.

    Attests that the installed files are the ones the wheel shipped. Does **not**
    attest that the wheel was built from the declared commit - nothing available at
    runtime can.

    Entries with no hash in RECORD (the RECORD file itself, and generated bytecode)
    are counted and skipped rather than treated as passing.
    """
    record = next((f for f in dist.files or [] if str(f).endswith(".dist-info/RECORD")), None)
    if record is None:  # pragma: no cover - wheel installed without a RECORD
        return FileIntegrity(checked=0, mismatched=(), missing=(), unhashed=0)

    root = Path(str(dist.locate_file(record))).parent.parent
    mismatched: list[str] = []
    missing: list[str] = []
    checked = unhashed = 0

    for row in csv.reader(Path(str(dist.locate_file(record))).read_text().splitlines()):
        if len(row) < 2 or not row[1]:
            unhashed += 1
            continue
        name, expected = row[0], row[1]
        if not expected.startswith("sha256="):
            unhashed += 1
            continue
        target = (root / name).resolve()
        if not target.is_file():
            missing.append(name)
            continue
        checked += 1
        if _record_digest(target) != expected:
            mismatched.append(name)

    return FileIntegrity(
        checked=checked,
        mismatched=tuple(sorted(mismatched)),
        missing=tuple(sorted(missing)),
        unhashed=unhashed,
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(_CHUNK):
            digest.update(block)
    return digest.hexdigest()


def attest_commit(pin: Pin) -> CommitAttestation:
    """Compare the installed package files with P25's manifest of the pinned commit's source.

    Offline: it reads the installed files and the committed manifest, nothing else. The
    commit is verified only when the manifest was made for exactly this pin, every listed
    file is installed with the listed sha256, and the distribution installs no package file
    the manifest does not list.
    """
    entry = SOURCE_MANIFEST.get(pin.distribution)
    if entry is None:
        return CommitAttestation(False, 0, reason="no P25 source manifest for this distribution")
    if (entry["version"], entry["commit_sha"]) != (pin.version, pin.commit_sha):
        return CommitAttestation(
            False,
            0,
            reason=(
                f"the P25 manifest is for {entry['version']} at {str(entry['commit_sha'])[:12]}, "
                f"the pin is {pin.version} at {pin.commit_sha[:12]}: a pin bump needs P25 re-run"
            ),
        )
    try:
        dist = _distribution(pin.distribution)
        installed_version = dist.version
    except PackageNotFoundError:
        return CommitAttestation(False, 0, reason=f"{pin.distribution} is not installed")
    if installed_version != pin.version:
        return CommitAttestation(
            False, 0, reason=f"{installed_version} is installed, the pin is {pin.version}"
        )

    files: dict[str, str] = dict(entry["files"])  # type: ignore[call-overload]
    packages = {name.split("/", 1)[0] for name in files}
    installed = {
        str(f)
        for f in dist.files or []
        if str(f).split("/", 1)[0] in packages and "__pycache__" not in str(f)
    }
    mismatched: list[str] = []
    missing: list[str] = []
    checked = 0
    for name, expected in sorted(files.items()):
        target = Path(str(dist.locate_file(name)))
        if name not in installed or not target.is_file():
            missing.append(name)
            continue
        checked += 1
        if _sha256(target) != expected:
            mismatched.append(name)
    unlisted = sorted(installed - set(files))
    verified = not mismatched and not missing and not unlisted
    reason = (
        ""
        if verified
        else (
            f"{len(mismatched)} differ, {len(missing)} missing, {len(unlisted)} not in the manifest"
        )
    )
    return CommitAttestation(
        verified, checked, tuple(mismatched), tuple(missing), tuple(unlisted), reason
    )


def _status_for(pin: Pin, artifacts: dict[str, dict[str, str]], *, deep: bool) -> PinStatus:
    try:
        installed: str | None = version(pin.distribution)
    except PackageNotFoundError:
        installed = None

    integrity: FileIntegrity | None = None
    if deep and installed == pin.version:
        try:
            integrity = verify_installed_files(_distribution(pin.distribution))
        except PackageNotFoundError:  # pragma: no cover - raced uninstall
            integrity = None

    attestation = attest_commit(pin) if installed == pin.version else None
    version_ok = installed == pin.version
    return PinStatus(
        distribution=pin.distribution,
        expected_version=pin.version,
        installed_version=installed,
        declared_commit_sha=pin.commit_sha,
        commit_sha_verified=attestation is not None and attestation.verified,
        ok=version_ok and (integrity is None or integrity.ok),
        artifact_hashes=artifacts.get(pin.distribution, {}),
        integrity=integrity,
        attestation=attestation,
    )


def check_pins(*, deep: bool = True, lockfile: str | Path = "uv.lock") -> list[PinStatus]:
    """Return the status of every binding pin, in declaration order.

    Args:
        deep: Recompute installed files against their RECORD manifest. Costs roughly
            a hundred small hashes per pinned distribution.
        lockfile: Path to ``uv.lock`` for artifact hashes.
    """
    artifacts = lockfile_artifact_hashes(lockfile)
    return [_status_for(pin, artifacts, deep=deep) for pin in PINS]
