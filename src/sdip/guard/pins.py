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

**The commit SHA is still not verified and this module never claims it is.** A wheel
does not carry the SHA it was built from, and closing that gap needs either a source
build or an upstream provenance attestation, neither of which exists under the current
pins. Every result states which claim it is making.
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

_CHUNK = 1 << 20


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
        return (
            f"{self.distribution} {self.installed_version} matches pin; "
            f"{integrity} installed files match RECORD; "
            f"commit SHA {self.declared_commit_sha[:12]} declared, not verified"
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

    version_ok = installed == pin.version
    return PinStatus(
        distribution=pin.distribution,
        expected_version=pin.version,
        installed_version=installed,
        declared_commit_sha=pin.commit_sha,
        commit_sha_verified=False,
        ok=version_ok and (integrity is None or integrity.ok),
        artifact_hashes=artifacts.get(pin.distribution, {}),
        integrity=integrity,
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
